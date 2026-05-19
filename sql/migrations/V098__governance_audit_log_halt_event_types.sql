-- V098__governance_audit_log_halt_event_types.sql
-- P0-ENGINE-HALTSESSION-STUCK-FIX (2026-05-19) — V035 governance_audit_log
-- event_type CHECK enum 擴展，加入 3 個 halt-session audit event types：
--   1. halt_session_set            (paper_paused → true via HaltSession)
--   2. halt_session_auto_cleared   (TTL fires — daily_loss only per D1 policy)
--   3. halt_session_manual_cleared (IPC Resume / Reset / SystemMode 路徑)
--
-- 同時 bundle 入 365d retention + 30d compression policy（per MIT M-4
-- recommendation，hypertable + add_*_policy if_not_exists 冪等）。
--
-- Pattern source: V053 (REF-20 Sprint 1 Track C) — DROP+ADD with ACCESS
-- EXCLUSIVE table lock for race-free CHECK constraint replacement.
--
-- P0-ENGINE-HALTSESSION-STUCK-FIX（2026-05-19）：擴 V035 enum + bundle 保留 /
-- 壓縮政策。pattern 鏡 V053（race-free DROP+ADD 持 ACCESS EXCLUSIVE lock）。
--
-- Purpose / 目的:
--   step_6 priority 7 (SESSION DRAWDOWN) / priority 9 (DAILY LOSS) HaltSession
--   觸發 + TTL auto-clear + IPC manual clearer 三條路徑必寫
--   learning.governance_audit_log；未擴 enum 前直接 INSERT 命中 CHECK
--   constraint fail-loud，無法 audit。本 V098 補齊 3 個 event_type。
--
-- Idempotency / 冪等性:
--   local psql -f V098 ... × 2 → second run no-op via:
--     1. Guard A：v_audit_log_exists check + RAISE EXCEPTION if V035 missing.
--     2. Guard B：lease_sm_transition substring check（V054 21-value baseline
--        必存）— 防 V053 / V054 lease retrofit 未 apply 就跳 V098。
--     3. Probe existing CHECK constraint def for 3 new halt_session_* values;
--        all present → RAISE NOTICE skip.
--     4. Otherwise DROP IF EXISTS + ADD CONSTRAINT canonical 24-value list.
--     5. add_retention_policy + add_compression_policy 採 if_not_exists => true。
--
-- Guard A: enforced (V035 base table existence; RAISE if absent).
-- Guard B: enforced (V053+V054 baseline 必存 — lease_sm_transition substring check).
-- Guard C: N/A (no hot-path index added by this migration).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-19--engine_haltsession_ttl_and_watchdog_inert_probe_spec.md
--     §3.11 V098 Migration（MIT empirical PG evidence 2026-05-19 21:35 UTC）
--   memory feedback_v_migration_pg_dry_run（Linux PG dry-run × 2 mandatory）
--
-- Template source / 模板來源:
--   sql/migrations/V053__governance_audit_log_replay_event_types.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate V035 base table exists; RAISE if absent.
-- learning.governance_audit_log 必先存在（V035 必 deploy 於 V098 之前）。
-- Guard A：驗 V035 base table 存在；不存即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_audit_log_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'governance_audit_log'
    ) INTO v_audit_log_exists;

    IF NOT v_audit_log_exists THEN
        RAISE EXCEPTION
            'V098 Guard A: learning.governance_audit_log not found; V035 must deploy before V098';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B: validate V053 + V054 (lease retrofit) baseline already applied.
-- 以 'lease_sm_transition' substring 探測：此值僅由 V054 lease retrofit 引入。
-- 不在 = V053/V054 未 apply 即跳 V098，立即 RAISE EXCEPTION 防 drift。
-- Guard B：以 lease_sm_transition 探 V053+V054 已 apply；不在即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_check_def TEXT;
BEGIN
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND c.conname = 'governance_audit_log_event_type_check';

    IF v_check_def IS NULL THEN
        RAISE EXCEPTION
            'V098 Guard B: governance_audit_log_event_type_check constraint missing; V053/V054 must deploy before V098';
    END IF;

    IF position('lease_sm_transition' IN v_check_def) = 0 THEN
        RAISE EXCEPTION
            'V098 Guard B: lease_sm_transition missing in CHECK; expected V053+V054 lease retrofit applied (21-value baseline)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V035 event_type CHECK enum DROP+ADD with 24-value canonical list.
--
-- Pre-V098 (V053 14 base + V054 lease retrofit 7) = 21 values:
--    1. review_live_candidate
--    2. lease_grant
--    3. lease_auto_revoke
--    4. bulk_re_evaluation
--    5. audit_write_failed
--    6. replay_handoff_request
--    7. replay_run_started
--    8. replay_run_cancelled
--    9. replay_manifest_verify_attempted
--   10. replay_signature_test_key_blocked
--   11. replay_pid_identity_mismatch
--   12. replay_idor_admin_bypass
--   13. replay_artifact_path_traversal_blocked
--   14. replay_argv_mismatch_blocked
--   15. lease_acquire_request
--   16. lease_acquire_success
--   17. lease_acquire_fail
--   18. lease_release_consumed
--   19. lease_release_failed
--   20. lease_release_cancelled
--   21. lease_sm_transition
--
-- V098 NEW (P0-ENGINE-HALTSESSION-STUCK-FIX):
--   22. halt_session_set
--   23. halt_session_auto_cleared
--   24. halt_session_manual_cleared
--
-- Total: 24 canonical values.
--
-- Race-free pattern：BEGIN ... LOCK TABLE ... DROP+ADD ... COMMIT。
-- ACCESS EXCLUSIVE 衝突於 ROW EXCLUSIVE（INSERT 鎖）— concurrent writer
-- 阻塞至新 constraint commit，CHECK 永遠存在守門（無 race window）。
-- 冪等：第二次跑經 idempotency probe RAISE NOTICE skip。
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

DO $$
DECLARE
    v_check_def TEXT;
    v_halt_present BOOLEAN := FALSE;
BEGIN
    -- 短路探：3 個 halt_session_* 值已在 → RAISE NOTICE skip。
    -- Idempotency 短路：探 LOCK 之前完成，re-run 不阻塞 writer。
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND c.conname = 'governance_audit_log_event_type_check';

    IF v_check_def IS NOT NULL
       AND position('halt_session_set' IN v_check_def) > 0
       AND position('halt_session_auto_cleared' IN v_check_def) > 0
       AND position('halt_session_manual_cleared' IN v_check_def) > 0
    THEN
        v_halt_present := TRUE;
    END IF;

    IF v_halt_present THEN
        RAISE NOTICE 'V098: 3 halt_session_* event_types already present in CHECK; skipping';
    ELSE
        -- E2 retrofit F2 race-free pattern：ACCESS EXCLUSIVE 跨 DROP+ADD gap。
        LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;

        -- DROP existing CHECK and re-ADD with canonical 24-value list.
        EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';

        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
                -- V053 14-value base + V054 lease retrofit 7 = 21 既有:
                'review_live_candidate',
                'lease_grant',
                'lease_auto_revoke',
                'bulk_re_evaluation',
                'audit_write_failed',
                'replay_handoff_request',
                'replay_run_started',
                'replay_run_cancelled',
                'replay_manifest_verify_attempted',
                'replay_signature_test_key_blocked',
                'replay_pid_identity_mismatch',
                'replay_idor_admin_bypass',
                'replay_artifact_path_traversal_blocked',
                'replay_argv_mismatch_blocked',
                'lease_acquire_request',
                'lease_acquire_success',
                'lease_acquire_fail',
                'lease_release_consumed',
                'lease_release_failed',
                'lease_release_cancelled',
                'lease_sm_transition',
                -- V098 NEW (P0-ENGINE-HALTSESSION-STUCK-FIX):
                'halt_session_set',
                'halt_session_auto_cleared',
                'halt_session_manual_cleared'
            ));
        RAISE NOTICE 'V098: added 3 halt_session_* event_types (canonical 24-value list) under ACCESS EXCLUSIVE lock';
    END IF;
END $$;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT ON CONSTRAINT 更新反映 V098 擴展。
-- COMMENT ON CONSTRAINT updated to reflect V098 extension.
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON CONSTRAINT governance_audit_log_event_type_check
ON learning.governance_audit_log IS
'event_type allowlist (V098 24-value): V053 14 base + V054 lease retrofit 7 + '
'V098 halt_session_* 3 (P0-ENGINE-HALTSESSION-STUCK-FIX 2026-05-19) / '
'event_type allowlist (V098 24 值)：V053 14 base + V054 lease 7 + V098 halt 3。';

-- ─────────────────────────────────────────────────────────────────────────────
-- Retention + Compression policy（MIT M-4 fold-in，bundle 入 V098）。
-- Hypertable governance_audit_log 既有；policy 透過 add_*_policy(.., if_not_exists)
-- 冪等。365d retention / 30d compression 為 governance audit 合理 default。
-- Retention + Compression：if_not_exists 冪等；365d/30d 合理 governance default。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_is_hypertable BOOLEAN;
BEGIN
    -- 僅 hypertable 時跑 retention / compression（避免 V035 變體下早期 baseline
    -- 沒 hypertable 化的部署 RAISE）。
    SELECT EXISTS (
        SELECT 1 FROM timescaledb_information.hypertables
        WHERE hypertable_schema = 'learning'
          AND hypertable_name = 'governance_audit_log'
    ) INTO v_is_hypertable;

    IF v_is_hypertable THEN
        PERFORM add_retention_policy(
            'learning.governance_audit_log',
            INTERVAL '365 days',
            if_not_exists => TRUE
        );
        -- compression 須先有 ALTER TABLE ... SET (timescaledb.compress) 設定；
        -- 既有部署若已壓縮設定可直接加 policy，未設定 add_compression_policy
        -- 會 RAISE — 用 EXCEPTION block 容忍此分支（事故下不擋 V098 主路徑）。
        BEGIN
            PERFORM add_compression_policy(
                'learning.governance_audit_log',
                INTERVAL '30 days',
                if_not_exists => TRUE
            );
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'V098: add_compression_policy skipped (compression not enabled on hypertable): %', SQLERRM;
        END;
        RAISE NOTICE 'V098: retention/compression policies applied (365d/30d, hypertable confirmed)';
    ELSE
        RAISE NOTICE 'V098: governance_audit_log not a hypertable; retention/compression skipped';
    END IF;
END $$;

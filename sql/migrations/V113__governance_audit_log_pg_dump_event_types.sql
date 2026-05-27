-- V113__governance_audit_log_pg_dump_event_types.sql
-- P0-OPS-4 GAP-D（2026-05-27）— V035 governance_audit_log event_type CHECK enum
-- 擴展，加入 2 個 pg_dump audit event types：
--   1. pg_dump_completed   （trading_ai_pg_dump_cron.sh 成功；payload 含 size_bytes
--                            / md5 / duration_sec / retention_days / db / host）
--   2. pg_dump_failed      （trading_ai_pg_dump_cron.sh 失敗；payload 含 rc /
--                            duration_sec / db / host；rc 為 pg_dump exit code）
--
-- 為什麼需要 audit trail（FA business audit §C requirement）：
--   first-day live 之後 PG backup 是 RTO ≤ 4h / RPO ≤ 24h 主防線；任何 cron
--   silent fail 必須能在 governance_audit_log 找到痕跡（cron log 容易被 rotate /
--   遺失，governance_audit_log 走 365d retention + hypertable persistent）。
--
-- Pattern source：V053 (REF-20 Sprint 1 Track C) + V098 (P0-ENGINE-HALTSESSION-
-- STUCK-FIX) — DROP+ADD with ACCESS EXCLUSIVE table lock for race-free CHECK
-- constraint replacement（per E2 retrofit F2）。
--
-- P0-OPS-4 GAP-D（2026-05-27）：擴 V035 enum 加 2 個 pg_dump_* event。pattern
-- 鏡 V053 / V098（race-free DROP+ADD 持 ACCESS EXCLUSIVE lock）。
--
-- Purpose / 目的:
--   trading_ai_pg_dump_cron.sh wrapper 完成/失敗時必寫 learning.governance_audit_log
--   作 audit trail；未擴 enum 前直接 INSERT 命中 CHECK constraint fail-loud，
--   audit 寫不進去。本 V113 補齊 2 個 event_type 解 unblock cron wrapper。
--
-- Idempotency / 冪等性:
--   local psql -f V113 ... × 2 → second run no-op via:
--     1. Guard A：v_audit_log_exists check + RAISE EXCEPTION if V035 missing.
--     2. Guard B：halt_session_set substring check（V098 24-value baseline
--        必存）— 防 V053 / V054 / V098 enum 擴展未 apply 就跳 V113。
--     3. Probe existing CHECK constraint def for 2 new pg_dump_* values;
--        both present → RAISE NOTICE skip.
--     4. Otherwise DROP IF EXISTS + ADD CONSTRAINT canonical 26-value list.
--
-- Guard A: enforced（V035 base table existence；RAISE if absent）。
-- Guard B: enforced（V098 baseline 必存 — halt_session_set substring check）。
-- Guard C: N/A（無新 hot-path index）。
--
-- Spec source / 規格來源:
--   docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md
--     §2.3 + §7.2 + §10 GAP-D
--   docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md
--     §3.1 NAS 假設 hidden risk + §3.2 evaluations 表 hidden risk
--   docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-27--ops_4_gap_bd_business_acceptance_audit.md
--     §C audit trail requirement
--   memory feedback_v_migration_pg_dry_run（Linux PG dry-run × 2 mandatory）
--
-- Template source / 模板來源:
--   sql/migrations/V098__governance_audit_log_halt_event_types.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate V035 base table exists; RAISE if absent.
-- learning.governance_audit_log 必先存在（V035 必 deploy 於 V113 之前）。
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
            'V113 Guard A: learning.governance_audit_log not found; V035 must deploy before V113';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B: validate V098 (halt_session retrofit) baseline already applied。
-- 以 'halt_session_set' substring 探測：此值僅由 V098 引入。
-- 不在 = V098 未 apply 即跳 V113，立即 RAISE EXCEPTION 防 drift。
-- Guard B：以 halt_session_set 探 V098 已 apply；不在即 RAISE。
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
            'V113 Guard B: governance_audit_log_event_type_check constraint missing; V053/V054/V098 must deploy before V113';
    END IF;

    IF position('halt_session_set' IN v_check_def) = 0 THEN
        RAISE EXCEPTION
            'V113 Guard B: halt_session_set missing in CHECK; expected V098 baseline applied (24-value canonical)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V035 event_type CHECK enum DROP+ADD with 26-value canonical list.
--
-- Pre-V113 (V098 baseline) = 24 values:
--   V053 14 base + V054 lease retrofit 7 + V098 halt 3 = 24
--
-- V113 NEW (P0-OPS-4 GAP-D):
--   25. pg_dump_completed
--   26. pg_dump_failed
--
-- Total: 26 canonical values.
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
    v_pg_dump_present BOOLEAN := FALSE;
BEGIN
    -- 短路探：2 個 pg_dump_* 值已在 → RAISE NOTICE skip。
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
       AND position('pg_dump_completed' IN v_check_def) > 0
       AND position('pg_dump_failed' IN v_check_def) > 0
    THEN
        v_pg_dump_present := TRUE;
    END IF;

    IF v_pg_dump_present THEN
        RAISE NOTICE 'V113: 2 pg_dump_* event_types already present in CHECK; skipping';
    ELSE
        -- E2 retrofit F2 race-free pattern：ACCESS EXCLUSIVE 跨 DROP+ADD gap。
        LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;

        -- DROP existing CHECK and re-ADD with canonical 26-value list.
        EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';

        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
                -- V053 14-value base + V054 lease retrofit 7 + V098 halt 3 = 24 既有:
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
                'halt_session_set',
                'halt_session_auto_cleared',
                'halt_session_manual_cleared',
                -- V113 NEW (P0-OPS-4 GAP-D):
                'pg_dump_completed',
                'pg_dump_failed'
            ));
        RAISE NOTICE 'V113: added 2 pg_dump_* event_types (canonical 26-value list) under ACCESS EXCLUSIVE lock';
    END IF;
END $$;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT ON CONSTRAINT 更新反映 V113 擴展。
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON CONSTRAINT governance_audit_log_event_type_check
ON learning.governance_audit_log IS
'event_type allowlist (V113 26-value): V053 14 base + V054 lease retrofit 7 + '
'V098 halt 3 + V113 pg_dump 2 (P0-OPS-4 GAP-D 2026-05-27) / '
'event_type allowlist (V113 26 值)：V053 14 base + V054 lease 7 + V098 halt 3 + '
'V113 pg_dump 2。';

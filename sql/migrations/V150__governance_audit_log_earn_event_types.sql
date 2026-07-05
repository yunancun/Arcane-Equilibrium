-- V150__governance_audit_log_earn_event_types.sql
-- CC-3 / OOS-1（2026-07-05）— V035 governance_audit_log event_type CHECK enum
-- 擴展，加入 2 個 earn approval audit event types：
--   1. earn_stake_approval    （EarnStake intent 走 earn_router Gate E-5.5 先寫
--                               governance_audit_log 取 BIGSERIAL id；payload 含
--                               earn_direction / approval_id / intent_id /
--                               amount_usdt / engine_mode / api_scope_used）
--   2. earn_redeem_approval   （EarnRedeem intent 同上，direction=redeem）
--
-- 為什麼需要這 2 個 event_type（兌現 PA-DRIFT-6 sentinel）：
--   earn_router.rs 原本以 governance_approval_id=0 占位 sentinel 下單（audit
--   lineage 缺口，lookup_governance_approval 反查解不到真 row）。CC-3 補上
--   earn_router Gate E-5.5：Bybit place-order 之前先 raw INSERT
--   learning.governance_audit_log RETURNING id，把真 id 注入 earn_movement_log。
--   event_type 由 direction 決定分兩值（earn_audit_event_type helper），使 audit
--   lineage 於 event_type 層一級可濾、徹底閉合。未擴 enum 前直接 INSERT 命中
--   CHECK constraint fail-loud，Gate E-5.5 會 fail-closed reject 全部 earn intent
--   直到本 V150 apply（見 §7.3 部署時序：migration 必先於 engine binary）。
--
-- Pattern source / 範式來源：V053（REF-20 Sprint 1 Track C）+ V098（halt retrofit）
--   + V113（pg_dump 2 值）— DROP+ADD with ACCESS EXCLUSIVE table lock 做 race-free
--   CHECK constraint replacement（per E2 retrofit F2）。本 V150 鏡 V113。
--
-- Baseline 核實（2026-07-05，origin/main @912bffd7f）：V113 之後無任何 migration
--   修改 governance_audit_log_event_type_check（V114 唯讀 Guard probe；V137/V138
--   為別表 event_type）→ 現行 CHECK = V113 26-value canonical。
--   V150 = 26 + earn_stake_approval + earn_redeem_approval = 28-value。
--
-- Idempotency / 冪等性:
--   local psql -f V150 ... × 2 → second run no-op via:
--     1. Guard A：v_audit_log_exists check + RAISE EXCEPTION if V035 missing.
--     2. Guard B：halt_session_set + pg_dump_completed substring check（V113
--        26-value baseline 必存）— 防 V053/V054/V098/V113 enum 擴展未 apply 就跳 V150。
--     3. Probe existing CHECK constraint def for 2 new earn_*_approval values;
--        both present → RAISE NOTICE skip.
--     4. Otherwise DROP IF EXISTS + ADD CONSTRAINT canonical 28-value list.
--
-- Guard A: enforced（V035 base table existence；RAISE if absent）。
-- Guard B: enforced（V113 baseline 必存 — halt_session_set + pg_dump_completed
--          substring check）。
-- Guard C: N/A（無新 hot-path index）。
--
-- Spec source / 規格來源:
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-07-05--cc3_earn_governance_audit_id_chain_design.md
--     §7.1 V-migration 規格 + §7.2 event_type helper + §7.3 部署時序
--   memory feedback_v_migration_pg_dry_run（Linux PG dry-run × 2 mandatory）
--
-- Template source / 模板來源:
--   sql/migrations/V113__governance_audit_log_pg_dump_event_types.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate V035 base table exists; RAISE if absent.
-- learning.governance_audit_log 必先存在（V035 必 deploy 於 V150 之前）。
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
            'V150 Guard A: learning.governance_audit_log not found; V035 must deploy before V150';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard B: validate V113 (pg_dump retrofit) 26-value baseline already applied。
-- 以 'halt_session_set'（V098 引入）+ 'pg_dump_completed'（V113 引入）substring
-- 雙探：兩值皆在 = V053/V054/V098/V113 enum 擴展鏈已 apply。
-- 任一不在 = baseline 未 apply 即跳 V150，立即 RAISE EXCEPTION 防 drift。
-- Guard B：以 halt_session_set + pg_dump_completed 探 V113 baseline 已 apply；
-- 缺任一即 RAISE。
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
            'V150 Guard B: governance_audit_log_event_type_check constraint missing; V053/V054/V098/V113 must deploy before V150';
    END IF;

    IF position('halt_session_set' IN v_check_def) = 0 THEN
        RAISE EXCEPTION
            'V150 Guard B: halt_session_set missing in CHECK; expected V098 baseline applied';
    END IF;

    IF position('pg_dump_completed' IN v_check_def) = 0 THEN
        RAISE EXCEPTION
            'V150 Guard B: pg_dump_completed missing in CHECK; expected V113 baseline applied (26-value canonical)';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V035 event_type CHECK enum DROP+ADD with 28-value canonical list.
--
-- Pre-V150 (V113 baseline) = 26 values:
--   V053 14 base + V054 lease retrofit 7 + V098 halt 3 + V113 pg_dump 2 = 26
--
-- V150 NEW (CC-3 / OOS-1):
--   27. earn_stake_approval
--   28. earn_redeem_approval
--
-- Total: 28 canonical values.
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
    v_earn_present BOOLEAN := FALSE;
BEGIN
    -- 短路探：2 個 earn_*_approval 值已在 → RAISE NOTICE skip。
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
       AND position('earn_stake_approval' IN v_check_def) > 0
       AND position('earn_redeem_approval' IN v_check_def) > 0
    THEN
        v_earn_present := TRUE;
    END IF;

    IF v_earn_present THEN
        RAISE NOTICE 'V150: 2 earn_*_approval event_types already present in CHECK; skipping';
    ELSE
        -- E2 retrofit F2 race-free pattern：ACCESS EXCLUSIVE 跨 DROP+ADD gap。
        LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;

        -- DROP existing CHECK and re-ADD with canonical 28-value list.
        EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';

        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
                -- V053 14 base + V054 lease 7 + V098 halt 3 + V113 pg_dump 2 = 26 既有:
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
                'pg_dump_completed',
                'pg_dump_failed',
                -- V150 NEW (CC-3 / OOS-1):
                'earn_stake_approval',
                'earn_redeem_approval'
            ));
        RAISE NOTICE 'V150: added 2 earn_*_approval event_types (canonical 28-value list) under ACCESS EXCLUSIVE lock';
    END IF;
END $$;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT ON CONSTRAINT 更新反映 V150 擴展。
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON CONSTRAINT governance_audit_log_event_type_check
ON learning.governance_audit_log IS
'event_type allowlist (V150 28-value): V053 14 base + V054 lease retrofit 7 + '
'V098 halt 3 + V113 pg_dump 2 + V150 earn 2 (CC-3 / OOS-1 2026-07-05) / '
'event_type allowlist (V150 28 值)：V053 14 base + V054 lease 7 + V098 halt 3 + '
'V113 pg_dump 2 + V150 earn 2。';

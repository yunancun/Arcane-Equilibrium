-- V053__governance_audit_log_replay_event_types.sql
-- REF-20 Sprint 1 Track C — V035 governance_audit_log event_type CHECK enum
-- extension to allow replay-related audit emits to land as fully-typed rows
-- (not via 'audit_write_failed' + payload-discriminator fallback).
--
-- REF-20 Sprint 1 Track C — 擴充 V035 governance_audit_log event_type CHECK
-- enum，使 replay 相關 audit emit 能寫完整型別 row（不必走
-- 'audit_write_failed' + payload-discriminator fallback）。
--
-- Purpose / 目的:
--   Sprint 1 Track C IMPL adds 5 new ``event_type`` values used by
--   ``replay_routes._emit_audit_stub`` for the three E3-P0-2 / P0-4 / P0-5
--   security fixes plus pre-existing replay event types from Wave 4 P2b-T2:
--
--     1. replay_run_started                       (Wave 4 P2b-T2 — pre-existing
--                                                  emit, was via fallback enum)
--     2. replay_run_cancelled                     (Wave 4 P2b-T2 — pre-existing)
--     3. replay_manifest_verify_attempted         (Wave 4 P2b-T2 — pre-existing)
--     4. replay_signature_test_key_blocked        (Track C P0-2 NEW —
--                                                  live profile blocks test key)
--     5. replay_pid_identity_mismatch             (Track C P0-4 NEW —
--                                                  cmdline cert failed before SIGTERM)
--     6. replay_idor_admin_bypass                 (Track C P0-5a NEW —
--                                                  replay:read:any used)
--     7. replay_artifact_path_traversal_blocked   (Track C P0-5b NEW —
--                                                  Path.resolve outside allowlist)
--     8. replay_argv_mismatch_blocked             (Track A NEW — CliError on
--                                                  spawn; placeholder for
--                                                  Track A P0-3 wiring)
--
--   Wave 8 P6-S15 already extended V035 to include 'replay_handoff_request'
--   (V044). V053 ADDS to that 6-value canonical list, yielding 13 values total
--   (5 V035 base + 1 V044 P6-S15 + 7 V053 replay-track items).
--
--   Wave 8 P6-S15 已透過 V044 擴 V035，含 'replay_handoff_request'。V053 在此
--   基礎上再加 7 個 replay-track event_type，擴成 13 值 canonical list。
--
-- Why one migration / 為何單一 migration:
--   All five Track C audit emits + Track A's argv_mismatch + 3 pre-existing
--   replay events need the enum value present together. Splitting into
--   separate migrations would require staged deploy of routes vs schema
--   (race window where INSERT fails CHECK). Single V053 atomic deploy is
--   the minimal-risk path.
--
--   5 Track C audit emit + Track A argv_mismatch + 3 pre-existing replay event
--   需 enum 值同時存在。拆多個 migration 會導致 routes/schema 階梯部署，
--   INSERT 命中 CHECK 的 race window。V053 單一原子部署是最小風險路徑。
--
-- Idempotency / 幂等性:
--   local psql -f V053 ... × 2 → second run no-op via:
--     1. v_audit_log_exists check + RAISE EXCEPTION if V035 missing.
--     2. Probe existing CHECK constraint def for the 5 new values; if all
--        present already → RAISE NOTICE skip (idempotent re-run).
--     3. Otherwise DROP IF EXISTS + ADD CONSTRAINT canonical 13-value list.
--
-- Guard A: enforced (V035 base table existence check; RAISE if absent).
-- Guard B: N/A (no column type mutation; only CHECK constraint).
-- Guard C: N/A (no hot-path index added by this migration).
--
-- Spec source / 規格來源:
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
--     §"Track C" + §"§6 Cross Track 共同 helper" (PA push back 提的 V053 task T-D5)
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §11 + §12 governance audit policy (append-only, INSERT-only).
--
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V053 (allocated by Sprint 1
--   Track C task per PA design 2026-05-03).
--
-- Template source / 模板來源:
--   sql/migrations/V044__replay_handoff_idempotency_unique.sql §V035 enum extension block
--   (V053 mirrors that pattern; same canonical-list DROP+ADD approach).

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate V035 base table exists; RAISE if absent (V035 must
-- deploy before V053). V053 has no own table; only CHECK extension.
--
-- Guard A：驗 V035 base table 存在；不存即 RAISE（V035 必先 V053 後）。
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
            'V053 Guard A: learning.governance_audit_log not found; V035 must deploy before V053';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V035 governance_audit_log event_type CHECK enum DROP+ADD with 14-value list.
--
-- V035 base ships 5 values; V044 already extended to 6 (added
-- 'replay_handoff_request'). V053 extends to 14:
--
--   Pre-V053 (V044):
--     1. review_live_candidate
--     2. lease_grant
--     3. lease_auto_revoke
--     4. bulk_re_evaluation
--     5. audit_write_failed
--     6. replay_handoff_request                   (V044 P6-S15)
--
--   V053 NEW (REF-20 Sprint 1 Track A + Track C):
--     7. replay_run_started                       (Track A / Wave 4 P2b-T2)
--     8. replay_run_cancelled                     (Track A / Wave 4 P2b-T2)
--     9. replay_manifest_verify_attempted         (Track A / Wave 4 P2b-T2)
--    10. replay_signature_test_key_blocked        (Track C P0-2 NEW)
--    11. replay_pid_identity_mismatch             (Track C P0-4 NEW)
--    12. replay_idor_admin_bypass                 (Track C P0-5a NEW)
--    13. replay_artifact_path_traversal_blocked   (Track C P0-5b NEW)
--    14. replay_argv_mismatch_blocked             (Track A P0-3 NEW)
--
-- Total: 14 canonical values.
--
-- V053 透過 DROP+ADD 將 V035 event_type CHECK enum 從 6 值擴為 14 值。
--
-- ─────────────────────────────────────────────────────────────────────────────
-- E2 retrofit F2 — race-free DROP+ADD via ACCESS EXCLUSIVE table lock.
--
-- The E3 P1-3 audit (and E2 retrofit F2) flagged that any
-- ``DROP CONSTRAINT IF EXISTS ...; ADD CONSTRAINT ... CHECK (...)``
-- sequence has a window between the DROP commit-visible point and the
-- ADD commit-visible point during which a concurrent INSERT may write
-- ANY ``event_type`` value (CHECK constraint not present). For
-- ``learning.governance_audit_log`` this would let an attacker (or a
-- bug) emit unbounded event_type rows that later block legitimate
-- enum-extension migrations.
--
-- Race-free pattern: wrap the DROP+ADD pair in an explicit transaction
-- holding ``ACCESS EXCLUSIVE`` on the table; concurrent writers block
-- until the new constraint commits, so the CHECK never has a "no-rule"
-- window. ACCESS EXCLUSIVE is the only lock mode that conflicts with
-- ROW EXCLUSIVE (the lock taken by INSERT), and its commit-time
-- release atomically replaces the constraint.
--
-- The outer ``DO $$`` does the idempotency probe + RAISE NOTICE; the
-- atomic block runs INSIDE the same transaction so all-or-nothing
-- semantics extend to the constraint flip. PostgreSQL plpgsql does
-- NOT support nested BEGIN/COMMIT inside DO blocks, so the LOCK TABLE
-- + ALTER pair lives in the same DO block and the implicit transaction
-- (psql -f wraps each top-level command in its own xact by default;
-- ``\set AUTOCOMMIT off`` or wrapping in BEGIN; ... COMMIT; both work).
--
-- For maximum portability across psql autocommit settings, this
-- migration uses an explicit BEGIN; ... COMMIT; wrapper around the
-- DO block. Idempotent re-run safe: the inner probe short-circuits
-- before LOCK TABLE if the canonical 14-value list is already present.
--
-- E2 retrofit F2 — race-free DROP+ADD：透過 ACCESS EXCLUSIVE table
-- lock 包裹。E3 P1-3 audit 與 E2 retrofit F2 均 flag DROP CONSTRAINT +
-- ADD CONSTRAINT 在兩語句間有 window，concurrent INSERT 在無 CHECK 守
-- 門時可寫任何 event_type。learning.governance_audit_log 此 race 將
-- 讓 attacker / bug emit 無界 event_type，後續 enum 擴展無法收斂。
-- Race-free pattern：DROP+ADD 對置於顯式 transaction 內，先 ACCESS
-- EXCLUSIVE LOCK TABLE；concurrent writer 阻塞至新 constraint commit，
-- CHECK 永遠存在守門。idempotent 路徑短路在 LOCK TABLE 之前。
-- 同 commit 開新 ticket P2-AUDIT-V044-LOCK-TABLE-FIX 補回 V044 同樣
-- race-free retrofit（V044 P6-S15 enum 擴展未含此守門）。
-- ─────────────────────────────────────────────────────────────────────────────
BEGIN;

DO $$
DECLARE
    v_check_def TEXT;
    v_track_c_present BOOLEAN := FALSE;
BEGIN
    -- Probe existing CHECK constraint on event_type column (idempotency
    -- short-circuit BEFORE LOCK TABLE — re-runs do not block writers).
    -- 探測 event_type column 的 CHECK constraint（idempotency 短路
    -- 於 LOCK TABLE 之前 — 重跑不阻塞 writer）。
    SELECT pg_get_constraintdef(c.oid)
    INTO v_check_def
    FROM pg_constraint c
    JOIN pg_class t ON t.oid = c.conrelid
    JOIN pg_namespace n ON n.oid = t.relnamespace
    WHERE n.nspname = 'learning'
      AND t.relname = 'governance_audit_log'
      AND c.contype = 'c'
      AND pg_get_constraintdef(c.oid) LIKE '%event_type%';

    -- Idempotency: if all V053 NEW enum values already present, skip.
    -- 幂等：若 V053 NEW 全 8 值已在 → skip。
    IF v_check_def IS NOT NULL
       AND position('replay_signature_test_key_blocked' IN v_check_def) > 0
       AND position('replay_pid_identity_mismatch' IN v_check_def) > 0
       AND position('replay_idor_admin_bypass' IN v_check_def) > 0
       AND position('replay_artifact_path_traversal_blocked' IN v_check_def) > 0
       AND position('replay_argv_mismatch_blocked' IN v_check_def) > 0
       AND position('replay_run_started' IN v_check_def) > 0
       AND position('replay_run_cancelled' IN v_check_def) > 0
       AND position('replay_manifest_verify_attempted' IN v_check_def) > 0
    THEN
        v_track_c_present := TRUE;
    END IF;

    IF v_track_c_present THEN
        RAISE NOTICE 'V053: governance_audit_log event_type CHECK already extended with all REF-20 Sprint 1 replay event types; skipping';
    ELSE
        -- E2 retrofit F2: take ACCESS EXCLUSIVE on the audit table BEFORE
        -- the DROP+ADD pair so concurrent INSERT blocks across the gap
        -- (no "constraint absent" window). Lock auto-released at COMMIT.
        -- E2 retrofit F2：DROP+ADD 前先取 ACCESS EXCLUSIVE，concurrent
        -- INSERT 跨 gap 阻塞（CHECK 永遠在守門）。COMMIT 自動釋鎖。
        LOCK TABLE learning.governance_audit_log IN ACCESS EXCLUSIVE MODE;

        -- DROP existing CHECK (if any) and re-ADD with 14-value canonical list.
        -- DROP 既有 CHECK（若有）並用 14 值 canonical list 重 ADD。
        IF EXISTS (
            SELECT 1 FROM pg_constraint c
            JOIN pg_class t ON t.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = t.relnamespace
            WHERE n.nspname = 'learning'
              AND t.relname = 'governance_audit_log'
              AND c.contype = 'c'
              AND c.conname LIKE '%event_type%'
        ) THEN
            EXECUTE 'ALTER TABLE learning.governance_audit_log DROP CONSTRAINT IF EXISTS governance_audit_log_event_type_check';
            RAISE NOTICE 'V053: dropped existing event_type CHECK on learning.governance_audit_log (under ACCESS EXCLUSIVE)';
        END IF;

        ALTER TABLE learning.governance_audit_log
            ADD CONSTRAINT governance_audit_log_event_type_check
            CHECK (event_type IN (
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
                'replay_argv_mismatch_blocked'
            ));
        RAISE NOTICE 'V053: added event_type CHECK with 14-value canonical list (5 V035 base + 1 V044 P6-S15 + 8 REF-20 Sprint 1 Track A/C) under ACCESS EXCLUSIVE lock';
    END IF;
END $$;

COMMIT;

-- ─────────────────────────────────────────────────────────────────────────────
-- COMMENT ON CONSTRAINT updated to reflect V053 extension.
-- COMMENT ON CONSTRAINT 更新反映 V053 擴展。
-- (CONSTRAINT comment is optional but improves DBA discoverability.)
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON CONSTRAINT governance_audit_log_event_type_check
ON learning.governance_audit_log IS
'event_type allowlist (V053 14-value canonical): review_live_candidate / '
'lease_grant / lease_auto_revoke / bulk_re_evaluation / audit_write_failed '
'(V035 base 5) + replay_handoff_request (V044 P6-S15) + replay_run_started / '
'replay_run_cancelled / replay_manifest_verify_attempted / '
'replay_signature_test_key_blocked / replay_pid_identity_mismatch / '
'replay_idor_admin_bypass / replay_artifact_path_traversal_blocked / '
'replay_argv_mismatch_blocked (8 REF-20 Sprint 1 Track A/C). / '
'event_type allowlist (V053 14 值 canonical)：5 個 V035 base + 1 個 V044 + '
'8 個 REF-20 Sprint 1 Track A/C 新增。';

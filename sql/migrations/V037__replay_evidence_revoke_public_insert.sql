-- V037__replay_evidence_revoke_public_insert.sql
-- REF-20 R20-P2a-S4 step 3 (Wave 3, 3-PR sequence)
--
-- Purpose / 目的:
--   Tighten learning.mlde_shadow_recommendations write boundary so that
--   the only writer-shaped path is via learning.verify_replay_evidence_and_insert()
--   (V036) executed by replay_writer_role. PUBLIC loses INSERT; existing
--   producer login roles must be granted membership in replay_writer_role
--   before this migration's deploy.
--
-- 收緊 learning.mlde_shadow_recommendations 寫入邊界，使唯一寫路徑為
--   replay_writer_role 透過 V036 verify_replay_evidence_and_insert() 執行。
--   PUBLIC 失去 INSERT 權限；既有 producer 登入角色須在 V037 deploy 前先
--   GRANT replay_writer_role 才能繼續寫。
--
-- ────────────────────────────────────────────────────────────────────────
-- ⚠️ OPERATOR DEPLOY ORDER (mandatory) / Operator 部署順序 (強制):
--   1. V036 land first (verify_replay_evidence_and_insert function created,
--      replay_writer_role created, GRANT EXECUTE TO PUBLIC + replay_writer_role).
--   2. Wave 3 PR2: 4 Python producer code switched to call
--      learning.verify_replay_evidence_and_insert() instead of direct INSERT.
--      Each producer's connection role MUST be granted membership in
--      replay_writer_role BEFORE V037 land:
--          GRANT replay_writer_role TO trading_app;       -- Python writer role
--          GRANT replay_writer_role TO openclaw_app_role; -- if used
--          GRANT replay_writer_role TO <any other login role used by producers>;
--      Verify with: \du replay_writer_role
--   3. V037 land (this file): REVOKE PUBLIC INSERT + REVOKE PUBLIC EXECUTE.
--   4. After V037 deploy, the only sanctioned writers are replay_writer_role
--      members executing verify_replay_evidence_and_insert().
--
--   違反順序的後果 / Skipping the order:
--   - 若 PR2 producer 切換未完成即執行 V037 → producer 直接 INSERT 全 fail-closed
--     (permission denied) → live demo writes 全部斷流；FUP-1 LG-5 reviewer pipeline
--     break; bb_breakout / ma_crossover demo audit row stop.
--   - 若 producer login role 未獲 GRANT replay_writer_role → producer 切換後仍 fail。
-- ────────────────────────────────────────────────────────────────────────
--
-- Migration order: V036 → V037 (depends on V036's verify_replay_evidence_and_insert
--                  function existence + replay_writer_role existence).
-- Idempotency: local psql -f V037 ... × 2 → 第二次無 RAISE
--   (Guard A pre-checks current grant state; subsequent REVOKE is idempotent
--    since Postgres REVOKE is no-op if grant absent).
-- Guard A: enforced (function existence pre-check + REVOKE idempotency).
-- Guard B: N/A (no ALTER COLUMN).
-- Guard C: N/A (no index DDL).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §4.2 #4 + §3 G4
-- Reservation ledger / 預留 ledger:
--   sql/migrations/REF-20_RESERVATION.md §3 V037 row

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: pre-check V036 prerequisites + producer-switch readiness.
-- Guard A: 預檢 V036 前置 + producer 切換就緒。
--
-- Goals / 目的:
--   1. Ensure V036 already landed (verify_replay_evidence_and_insert exists).
--   2. Ensure replay_writer_role exists.
--   3. Optional warn: producer switch verification — if PUBLIC currently has
--      INSERT and replay_writer_role has 0 members, log NOTICE (operator must
--      verify producer code switched + login roles granted).
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_func_exists BOOLEAN;
    v_role_exists BOOLEAN;
    v_role_member_count INT;
    v_public_insert_present BOOLEAN;
BEGIN
    -- (1) V036 function existence check / V036 函數存在性檢查
    SELECT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'verify_replay_evidence_and_insert'
    ) INTO v_func_exists;

    IF NOT v_func_exists THEN
        RAISE EXCEPTION
            'V037 Guard A: V036 prerequisite missing — learning.verify_replay_evidence_and_insert() not found'
            USING DETAIL = 'V036 must land BEFORE V037; the verified insert function is the only sanctioned write path after this migration',
                  HINT = 'Run sql/migrations/V036__replay_evidence_source_guard.sql first';
    END IF;

    -- (2) replay_writer_role existence check
    SELECT EXISTS (
        SELECT 1 FROM pg_roles WHERE rolname = 'replay_writer_role'
    ) INTO v_role_exists;

    IF NOT v_role_exists THEN
        RAISE EXCEPTION
            'V037 Guard A: replay_writer_role missing — V036 should have created it'
            USING DETAIL = 'V036 includes idempotent CREATE ROLE replay_writer_role NOLOGIN',
                  HINT = 'Re-run V036 to provision the role';
    END IF;

    -- (3) Producer switch readiness warning (NOTICE only, not blocking).
    --     Count members of replay_writer_role; 0 members + PUBLIC INSERT
    --     present → operator likely forgot to GRANT login roles first.
    --     Warning, not RAISE — V037 may still be intentionally run on a
    --     fresh / dev-only DB without producer activity.
    SELECT count(*) INTO v_role_member_count
    FROM pg_auth_members am
    JOIN pg_roles r_role ON r_role.oid = am.roleid
    WHERE r_role.rolname = 'replay_writer_role';

    SELECT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND grantee = 'PUBLIC'
          AND privilege_type = 'INSERT'
    ) INTO v_public_insert_present;

    IF v_role_member_count = 0 AND v_public_insert_present THEN
        RAISE WARNING
            'V037 Guard A: replay_writer_role has 0 members yet PUBLIC INSERT is being revoked. After this migration, NO producer can write learning.mlde_shadow_recommendations until login roles are granted membership.'
            USING HINT = 'Operator: GRANT replay_writer_role TO <producer_login_role>; for each Python producer; verify with \\du replay_writer_role';
    END IF;

    RAISE NOTICE 'V037 Guard A: V036 prerequisites satisfied (function exists, role exists, % members)', v_role_member_count;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 1: REVOKE PUBLIC INSERT on learning.mlde_shadow_recommendations.
-- Step 1: 從 PUBLIC 撤銷 learning.mlde_shadow_recommendations 的 INSERT 權限。
--
-- Postgres REVOKE is idempotent when grant absent (no error). Re-running
-- V037 after first apply produces a no-op REVOKE; safe.
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE INSERT ON learning.mlde_shadow_recommendations FROM PUBLIC;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 2: GRANT INSERT on learning.mlde_shadow_recommendations to replay_writer_role.
-- Step 2: 將 INSERT 授予 replay_writer_role。
--
-- replay_writer_role is the only role that can INSERT directly. In practice
-- (V036 + V037 fully deployed) producers SHOULD only use the verified function;
-- this direct grant exists so that the function's INSERT inside SECURITY INVOKER
-- context succeeds (it runs as the calling role, which must have INSERT to
-- carry the underlying DML).
--
-- replay_writer_role 是唯一可 INSERT 的角色。生產實務上 producer 應僅透過
-- verified function 寫入；此 INSERT GRANT 存在，是為了在 SECURITY INVOKER
-- 模式下，function 內 INSERT 以 caller role 身分執行時能順利寫入 (caller
-- 必為 replay_writer_role 才有此權限)。
-- ─────────────────────────────────────────────────────────────────────────────
GRANT INSERT ON learning.mlde_shadow_recommendations TO replay_writer_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- Step 3: Tighten EXECUTE on verify_replay_evidence_and_insert.
-- Step 3: 收緊 verify_replay_evidence_and_insert 的 EXECUTE 權限。
--
-- V036 grants EXECUTE TO PUBLIC + replay_writer_role for non-breaking
-- producer switch. V037 revokes PUBLIC EXECUTE; only replay_writer_role
-- (and its members) can execute.
--
-- V036 因 producer 切換需非破壞性，先 GRANT EXECUTE TO PUBLIC + replay_writer_role。
-- V037 撤銷 PUBLIC EXECUTE，僅 replay_writer_role (及其成員) 可執行。
-- ─────────────────────────────────────────────────────────────────────────────
REVOKE EXECUTE ON FUNCTION learning.verify_replay_evidence_and_insert(
    TEXT, TEXT, TEXT, TEXT, TEXT,
    DOUBLE PRECISION, DOUBLE PRECISION, INTEGER, JSONB,
    BOOLEAN, BOOLEAN, TEXT,
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT
) FROM PUBLIC;

-- (replay_writer_role already has EXECUTE from V036 GRANT; idempotent re-grant
--  here for explicitness so re-running V037 after role rebuild is safe.)
GRANT EXECUTE ON FUNCTION learning.verify_replay_evidence_and_insert(
    TEXT, TEXT, TEXT, TEXT, TEXT,
    DOUBLE PRECISION, DOUBLE PRECISION, INTEGER, JSONB,
    BOOLEAN, BOOLEAN, TEXT,
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT
) TO replay_writer_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- Post-deploy verification / 部署後驗證
-- 期望狀態 / Expected state:
--   * learning.mlde_shadow_recommendations: PUBLIC has SELECT/UPDATE/DELETE
--     as before (V031 default), but NOT INSERT;
--     replay_writer_role: INSERT.
--   * learning.verify_replay_evidence_and_insert(...): EXECUTE only by
--     replay_writer_role (PUBLIC removed).
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_public_still_has_insert BOOLEAN;
    v_role_has_insert BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND grantee = 'PUBLIC'
          AND privilege_type = 'INSERT'
    ) INTO v_public_still_has_insert;

    IF v_public_still_has_insert THEN
        RAISE EXCEPTION
            'V037 post-deploy: PUBLIC still has INSERT on learning.mlde_shadow_recommendations after REVOKE'
            USING HINT = 'Possible legacy GRANT TO PUBLIC at column level; inspect with \\dp learning.mlde_shadow_recommendations';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.role_table_grants
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND grantee = 'replay_writer_role'
          AND privilege_type = 'INSERT'
    ) INTO v_role_has_insert;

    IF NOT v_role_has_insert THEN
        RAISE EXCEPTION
            'V037 post-deploy: replay_writer_role does not have INSERT after GRANT'
            USING HINT = 'Re-run V037 or GRANT INSERT manually';
    END IF;

    RAISE NOTICE 'V037 post-deploy: PUBLIC INSERT revoked, replay_writer_role INSERT granted';
END $$;

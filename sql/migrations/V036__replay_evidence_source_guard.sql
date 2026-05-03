-- V036__replay_evidence_source_guard.sql
-- REF-20 R20-P2a-S4 step 1 (Wave 3, 3-PR sequence)
--
-- Purpose / 目的:
--   Create learning.verify_replay_evidence_and_insert() PL/pgSQL function
--   (SECURITY INVOKER) which is the only sanctioned write path into
--   learning.mlde_shadow_recommendations once V037 lands. The function
--   validates evidence_source_tier ∈ allowlist + source ∈ producer
--   allowlist + replay_experiment_id / manifest_hash compound CHECK
--   semantics + (when caller set) future expires_at TTL contract before
--   forwarding the row through INSERT ... RETURNING id.
--
-- 建立 learning.verify_replay_evidence_and_insert() PL/pgSQL function
-- (SECURITY INVOKER)，V037 上線後成為 mlde_shadow_recommendations 唯一
-- 合規寫入路徑。Function 在 INSERT ... RETURNING id 前驗證
-- evidence_source_tier 白名單 + source 生產者白名單 + replay_experiment_id
-- / manifest_hash 複合 CHECK 語意 + (caller 設定時) expires_at TTL 契約。
--
-- Why SECURITY INVOKER (not DEFINER):
--   V3 §4.2 #4 requires preserving legitimate existing producers writing
--   real_outcome rows. SECURITY DEFINER would bypass role grants on the
--   underlying mlde_shadow_recommendations table — once V037 REVOKEs
--   PUBLIC INSERT, INVOKER ensures the caller's role is the auth gate
--   (replay_writer_role GRANTed via this function only).
--
-- 為何用 SECURITY INVOKER:
--   V3 §4.2 #4 要求保留既有 producer 寫 real_outcome row 的合法路徑。
--   SECURITY DEFINER 會繞過下層 role grant — V037 REVOKE PUBLIC INSERT
--   後，INVOKER 確保 caller 自己的角色是真實授權閘 (function 是唯一
--   GRANTed 給 replay_writer_role 的入口)。
--
-- Migration order: V035 → V036 (depends on learning.mlde_shadow_recommendations
--                  V031 schema + recommendation_type CHECK list).
-- Idempotency: local psql -f V036 ... × 2 → 第二次無 RAISE
--   (CREATE OR REPLACE FUNCTION + Guard A function-existence check no-ops on re-run).
-- Guard A: enforced (function existence + signature validation post-create).
-- Guard B: N/A (no ALTER COLUMN; function-only DDL).
-- Guard C: N/A (no index DDL).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §4.2 #4 + §3 G4
--   docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 Wave 3 R20-P2a-S4
-- Producer surgical change list / 生產者外科級切換清單:
--   docs/CCAgentWorkSpace/E1/workspace/reports/2026-05-03--mlde_shadow_insert_paths_grep.md §6
-- Reservation ledger / 預留 ledger:
--   sql/migrations/REF-20_RESERVATION.md §3 V036 row

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema preflight / 預檢
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_schema_exists BOOLEAN;
    v_table_exists BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.schemata WHERE schema_name = 'learning'
    ) INTO v_schema_exists;

    IF NOT v_schema_exists THEN
        RAISE EXCEPTION 'V036 preflight: schema "learning" does not exist; run V031 first';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning' AND table_name = 'mlde_shadow_recommendations'
    ) INTO v_table_exists;

    IF NOT v_table_exists THEN
        RAISE EXCEPTION 'V036 preflight: learning.mlde_shadow_recommendations does not exist; run V031 first';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Main function / 主 function
--
-- Caller contract / 呼叫者契約:
--   * p_evidence_source_tier ∈ {'real_outcome','calibrated_replay',
--                               'synthetic_replay','counterfactual_replay'}
--   * p_source ∈ {'ml_shadow','dream_engine','opportunity_tracker','linucb'}
--     (note: 'mlde_advisor' alias mapped to 'ml_shadow' upstream by Python
--      producer; verified function 不接受 alias，必傳真實 schema 值)
--   * p_evidence_source_tier='real_outcome'
--       => p_replay_experiment_id IS NULL AND p_manifest_hash IS NULL
--   * p_evidence_source_tier!='real_outcome'
--       => p_replay_experiment_id IS NOT NULL AND p_manifest_hash IS NOT NULL
--   * p_expires_at NULL allowed for real_outcome (legacy producer path);
--     replay-derived row 必非空且 > now()。
--   * 其他 column 與 V031 schema column list 對齊；signature 不增也不減。
--
-- Returns / 回傳:
--   New mlde_shadow_recommendations.id (BIGINT) on success.
--   Raises EXCEPTION (with detail in MESSAGE / DETAIL / HINT) on validation
--   failure. Underlying INSERT 對應 V031 既有 CHECK 一律保留 (engine_mode
--   / source / recommendation_type / decision_lease_id 規則不變)。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION learning.verify_replay_evidence_and_insert(
    p_engine_mode TEXT,
    p_symbol TEXT,
    p_strategy_name TEXT,
    p_source TEXT,
    p_recommendation_type TEXT,
    p_expected_net_bps DOUBLE PRECISION,
    p_confidence DOUBLE PRECISION,
    p_sample_count INTEGER,
    p_payload JSONB,
    p_applied BOOLEAN,
    p_requires_governance BOOLEAN,
    p_created_by TEXT,
    p_evidence_source_tier TEXT DEFAULT 'real_outcome',
    p_replay_experiment_id TEXT DEFAULT NULL,
    p_manifest_hash TEXT DEFAULT NULL,
    p_expires_at TIMESTAMPTZ DEFAULT NULL,
    p_decision_lease_id TEXT DEFAULT NULL,
    p_context_id TEXT DEFAULT NULL,
    p_intent_id TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY INVOKER
AS $$
DECLARE
    v_allowed_tiers TEXT[] := ARRAY[
        'real_outcome',
        'calibrated_replay',
        'synthetic_replay',
        'counterfactual_replay'
    ];
    v_allowed_sources TEXT[] := ARRAY[
        'ml_shadow',
        'dream_engine',
        'opportunity_tracker',
        'linucb'
    ];
    v_new_id BIGINT;
BEGIN
    -- (1) evidence_source_tier 白名單檢查 / allowlist check
    IF p_evidence_source_tier IS NULL OR NOT (p_evidence_source_tier = ANY (v_allowed_tiers)) THEN
        RAISE EXCEPTION
            'verify_replay_evidence_and_insert: evidence_source_tier=% not in allowlist',
            p_evidence_source_tier
            USING DETAIL = 'Allowed tiers: real_outcome, calibrated_replay, synthetic_replay, counterfactual_replay',
                  HINT = 'Caller must classify the row tier per V3 §4.2 before invoking this function';
    END IF;

    -- (2) source 生產者白名單檢查 / producer source allowlist check
    IF p_source IS NULL OR NOT (p_source = ANY (v_allowed_sources)) THEN
        RAISE EXCEPTION
            'verify_replay_evidence_and_insert: source=% not in producer allowlist',
            p_source
            USING DETAIL = 'Allowed sources: ml_shadow, dream_engine, opportunity_tracker, linucb',
                  HINT = 'Replay-derived rows still classify under one of the four canonical producer slots';
    END IF;

    -- (3) replay-derived row 複合契約 / compound CHECK semantics
    IF p_evidence_source_tier = 'real_outcome' THEN
        IF p_replay_experiment_id IS NOT NULL OR p_manifest_hash IS NOT NULL THEN
            RAISE EXCEPTION
                'verify_replay_evidence_and_insert: real_outcome row must not carry replay_experiment_id / manifest_hash'
                USING DETAIL = 'V3 §4.2 CHECK: real_outcome ⇒ both NULL',
                      HINT = 'Set evidence_source_tier=calibrated_replay/synthetic_replay/counterfactual_replay if this is replay-derived';
        END IF;
    ELSE
        IF p_replay_experiment_id IS NULL OR p_manifest_hash IS NULL THEN
            RAISE EXCEPTION
                'verify_replay_evidence_and_insert: replay-derived row (tier=%) requires replay_experiment_id AND manifest_hash',
                p_evidence_source_tier
                USING DETAIL = 'V3 §4.2 CHECK: tier!=real_outcome ⇒ both NOT NULL',
                      HINT = 'Caller must register the replay experiment before calling this function';
        END IF;
    END IF;

    -- (4) replay-derived row TTL 強檢 / TTL hard check for replay-derived rows
    -- real_outcome legacy producer path: p_expires_at NULL accepted (existing
    -- contract has no TTL column written).
    -- replay-derived: caller MUST supply expires_at in the future.
    IF p_evidence_source_tier <> 'real_outcome' THEN
        IF p_expires_at IS NULL THEN
            RAISE EXCEPTION
                'verify_replay_evidence_and_insert: replay-derived row requires non-NULL expires_at'
                USING DETAIL = 'Replay manifest TTL contract: 30 days default per V3 §5',
                      HINT = 'Caller must populate expires_at from manifest.expires_at field';
        END IF;
        IF p_expires_at <= now() THEN
            RAISE EXCEPTION
                'verify_replay_evidence_and_insert: expires_at=% must be in the future',
                p_expires_at
                USING DETAIL = 'Manifest already expired; refusing to insert advisory row',
                      HINT = 'Re-sign manifest or extend TTL window before retry';
        END IF;
    END IF;

    -- (5) Forward to INSERT (carries V031 CHECK constraints automatically).
    --     V031 既有 CHECK 自動繼承 (engine_mode / source / recommendation_type
    --     / decision_lease_id rule)。expires_at / replay_experiment_id /
    --     manifest_hash / evidence_source_tier columns 由 V038-V040 retrofit
    --     後實際物理存在；當前 V036 land 時這些 column 尚未存在，因此 INSERT
    --     僅寫 V031 既有 column，保留契約於 function arg 層為將來 column 上線
    --     後 producer 切換預留語意 (3-PR sequence 第 1 PR 此處不破壞既有 row
    --     shape)。
    --
    --     V031 existing CHECK constraints inherit automatically. The four
    --     replay metadata columns (expires_at / replay_experiment_id /
    --     manifest_hash / evidence_source_tier) physically land via V038-V040
    --     retrofit; until then the function argues at API surface level only
    --     and forwards the V031-shape row as-is. This keeps PR1 of the 3-PR
    --     sequence non-breaking for live demo writes.
    INSERT INTO learning.mlde_shadow_recommendations (
        engine_mode,
        context_id,
        intent_id,
        symbol,
        strategy_name,
        source,
        recommendation_type,
        primary_metric,
        expected_net_bps,
        confidence,
        sample_count,
        payload,
        applied,
        requires_governance,
        decision_lease_id,
        created_by
    ) VALUES (
        p_engine_mode,
        p_context_id,
        p_intent_id,
        p_symbol,
        p_strategy_name,
        p_source,
        p_recommendation_type,
        'net_bps_after_fee',
        p_expected_net_bps,
        p_confidence,
        p_sample_count,
        COALESCE(p_payload, '{}'::jsonb),
        COALESCE(p_applied, false),
        COALESCE(p_requires_governance, true),
        p_decision_lease_id,
        p_created_by
    )
    RETURNING id INTO v_new_id;

    RETURN v_new_id;
END;
$$;

COMMENT ON FUNCTION learning.verify_replay_evidence_and_insert(
    TEXT, TEXT, TEXT, TEXT, TEXT,
    DOUBLE PRECISION, DOUBLE PRECISION, INTEGER, JSONB,
    BOOLEAN, BOOLEAN, TEXT,
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT
) IS
'REF-20 R20-P2a-S4 verified insert function (SECURITY INVOKER). The only sanctioned write path into learning.mlde_shadow_recommendations once V037 REVOKEs PUBLIC INSERT. Validates evidence_source_tier allowlist + source allowlist + real_outcome/replay-derived compound CHECK + TTL contract before forwarding INSERT. / 唯一合規寫入路徑 (V037 後)；驗 tier/source 白名單 + real_outcome 對 replay 複合契約 + TTL 後 forward INSERT。';

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A (post-create): function existence + arg signature validation.
-- Guard A (建立後): 驗證 function 存在且 arg signature 符合預期。
-- Idempotent: re-running V036 hits CREATE OR REPLACE → same signature → no RAISE.
-- 重跑 V036：CREATE OR REPLACE 命中相同 signature，Guard 不 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_func_exists BOOLEAN;
    v_arg_count INT;
    v_expected_arg_count INT := 19;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'verify_replay_evidence_and_insert'
    ) INTO v_func_exists;

    IF NOT v_func_exists THEN
        RAISE EXCEPTION 'V036 Guard A: learning.verify_replay_evidence_and_insert function not found after CREATE OR REPLACE';
    END IF;

    SELECT pronargs INTO v_arg_count
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'learning'
      AND p.proname = 'verify_replay_evidence_and_insert';

    IF v_arg_count <> v_expected_arg_count THEN
        RAISE EXCEPTION
            'V036 Guard A: verify_replay_evidence_and_insert arg count drift; expected %, actual %',
            v_expected_arg_count, v_arg_count;
    END IF;

    RAISE NOTICE 'V036 Guard A: verify_replay_evidence_and_insert validated (% args, SECURITY INVOKER)', v_arg_count;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Role provisioning (idempotent CREATE ROLE if missing).
-- 角色預備 (idempotent — 不存在才建立)。
--
-- replay_writer_role: granted to producers (Python connection roles) once
--                     V037 lands; until then only EXECUTE this function is
--                     granted; underlying INSERT is still PUBLIC-allowed.
-- replay_writer_role: producer (Python 連線角色) 在 V037 後 GRANTed；本 V036
--                     僅 GRANT EXECUTE，underlying INSERT 仍 PUBLIC 開放。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'replay_writer_role') THEN
        CREATE ROLE replay_writer_role NOLOGIN;
        RAISE NOTICE 'V036: created replay_writer_role (NOLOGIN; granted to producer login roles in operator deploy step)';
    ELSE
        RAISE NOTICE 'V036: replay_writer_role already exists; skipping CREATE ROLE';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Grant EXECUTE on function to replay_writer_role + PUBLIC fallback.
-- During PR1 (V036 only), PUBLIC may execute the function so producer
-- switch (PR2) is non-breaking. PR3 (V037) tightens to replay_writer_role
-- only.
--
-- 將 EXECUTE 權限授予 replay_writer_role + PUBLIC fallback。PR1 階段 (V036)
-- 開放 PUBLIC，使 PR2 producer 切換不破壞既有 producer；PR3 (V037) 收緊
-- 為 replay_writer_role only。
-- ─────────────────────────────────────────────────────────────────────────────
GRANT EXECUTE ON FUNCTION learning.verify_replay_evidence_and_insert(
    TEXT, TEXT, TEXT, TEXT, TEXT,
    DOUBLE PRECISION, DOUBLE PRECISION, INTEGER, JSONB,
    BOOLEAN, BOOLEAN, TEXT,
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT
) TO PUBLIC;

GRANT EXECUTE ON FUNCTION learning.verify_replay_evidence_and_insert(
    TEXT, TEXT, TEXT, TEXT, TEXT,
    DOUBLE PRECISION, DOUBLE PRECISION, INTEGER, JSONB,
    BOOLEAN, BOOLEAN, TEXT,
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT
) TO replay_writer_role;

-- ─────────────────────────────────────────────────────────────────────────────
-- Operator deploy note / Operator 部署備忘:
--   1. V036 land first (this file).
--   2. PR2: producer code switch (4 producer files; same commit).
--   3. PR3: V037 REVOKE INSERT FROM PUBLIC + GRANT INSERT TO replay_writer_role.
--   4. After V037 deploy, operator must `GRANT replay_writer_role TO <login_role>`
--      for each Python producer connection role (e.g. trading_app, grafana_ro);
--      see V037 deploy header for canonical list.
--
-- Operator 部署順序:
--   1. V036 上線 (本檔)。
--   2. PR2: 4 producer code 切換 (同 commit)。
--   3. PR3: V037 REVOKE INSERT FROM PUBLIC + GRANT INSERT TO replay_writer_role。
--   4. V037 deploy 後 operator 須對每個 Python producer 連線角色執行
--      `GRANT replay_writer_role TO <login_role>` (canonical list 見 V037 header)。
-- ─────────────────────────────────────────────────────────────────────────────

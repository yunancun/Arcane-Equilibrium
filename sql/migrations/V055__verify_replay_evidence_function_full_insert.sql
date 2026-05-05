-- V055__verify_replay_evidence_function_full_insert.sql
-- REF-20 Sprint C R6-T0' (V036 PR3 retrofit; MIT P0 BLOCKER fix)
--
-- Purpose / 目的:
--   Retrofit `learning.verify_replay_evidence_and_insert()` PL/pgSQL function
--   so its INSERT body actually writes the THREE replay metadata columns that
--   physically exist on `learning.mlde_shadow_recommendations`:
--     1. `evidence_source_tier` (V038-V040: NOT NULL 4-value enum)
--     2. `replay_experiment_id`  (V051: NULLABLE UUID FK to V049)
--     3. `manifest_hash`         (V051: NULLABLE BYTEA hex digest)
--
--   V036 docstring (line 200-207) self-described "PR3 will retrofit" 4 columns
--   including `expires_at`, but **`expires_at` was never added to
--   `learning.mlde_shadow_recommendations` by any migration**. V038-V040 added
--   `evidence_source_tier`. V051 added `replay_experiment_id` + `manifest_hash`.
--   No migration adds `expires_at` to this table.
--
--   PM design clarification (Sprint C round 2):
--     - V055 INSERT body writes 3 columns (NOT 4); aligns with V051 paired
--       CHECK chk_mlde_shadow_replay_lineage which constrains exactly the
--       3-tuple (tier, replay_experiment_id, manifest_hash).
--     - `p_expires_at` argument remains in the 19-arg signature for V036
--       byte-equal. It still drives verify portion (4) TTL hard check. But
--       it does NOT persist to a row column. TTL is a two-layer guard:
--         * Write side: V055 verify portion (4) enforces NOT NULL + future
--           timestamp for non-real_outcome tier (input validation).
--         * Read side: mlde_demo_applier_evidence_filter Block B JOINs
--           replay.experiments (FK target via replay_experiment_id) and
--           reads `replay.experiments.expires_at` (V049 line 305 ADD COLUMN).
--           This is the canonical TTL source-of-truth at the experiment
--           level, NOT a per-advisory-row column.
--
--   V036 INSERT body (line 208-242) drops all 4 metadata args on the floor.
--   Result = silent corruption: V036 verify portion (line 137-191) PASSes
--   when caller supplies correct args, but the row lands with V038-V040
--   backfill default (`evidence_source_tier='real_outcome'` + 3 NULL
--   columns), passes V051 paired CHECK on the real_outcome branch, and
--   looks fine — but mlde_demo_applier evidence filter Block B never
--   promotes it because the replay tier never appears in row body. R7
--   acceptance A10-1/2/3 would go fake-green.
--
--   V055 retrofit replaces the function with the same 19-arg signature but
--   forwards 3 metadata args into the row body. Verify portion stays
--   byte-equal so behavioural contract is unchanged.
--
--   修補 `learning.verify_replay_evidence_and_insert()` PL/pgSQL function：
--   讓 INSERT body 真的寫 3 個物理存在於 `learning.mlde_shadow_recommendations`
--   的 metadata column：
--     1. `evidence_source_tier` (V038-V040：NOT NULL 4-value enum)
--     2. `replay_experiment_id`  (V051：NULLABLE UUID FK to V049)
--     3. `manifest_hash`         (V051：NULLABLE BYTEA hex digest)
--
--   V036 docstring (line 200-207) 自承「PR3 補 function body」會補 4 個
--   column 含 `expires_at`，但**任一 migration 都未對
--   `learning.mlde_shadow_recommendations` 加 `expires_at` column**。V038-V040
--   只加 `evidence_source_tier`；V051 只加 `replay_experiment_id` +
--   `manifest_hash`；無 migration 加 `expires_at` 到此表。
--
--   PM 設計澄清（Sprint C round 2）：
--     - V055 INSERT body 寫 3 column（不是 4）；與 V051 paired CHECK
--       chk_mlde_shadow_replay_lineage 約束的 3-tuple (tier,
--       replay_experiment_id, manifest_hash) 對齊。
--     - `p_expires_at` 仍保留於 19-arg signature 維持 V036 byte-equal。
--       仍走 verify portion (4) TTL 強檢路徑。但**不持久化**到 row
--       column。TTL 雙層守門：
--         * 寫端：V055 verify portion (4) 對 non-real_outcome tier
--           強制 NOT NULL + 未來時戳（input validation）。
--         * 讀端：mlde_demo_applier_evidence_filter Block B JOIN
--           replay.experiments（透 replay_experiment_id FK 取）讀
--           `replay.experiments.expires_at`（V049 line 305 ADD COLUMN）。
--           這是 experiment 層級的 canonical TTL source-of-truth，
--           **不是** per-advisory-row column。
--
--   V036 INSERT body 把 4 個 metadata args 丟掉。後果 = silent
--   corruption：V036 verify 部分 (line 137-191) 在 caller 傳對 args 時
--   PASS，但 row 走 V038-V040 backfill default (`real_outcome` + 3 NULL)
--   落地，V051 paired CHECK 走 real_outcome 分支自動 PASS，看似正常 —
--   但 mlde_demo_applier evidence filter Block B 永遠不會 promote 此 row
--   因 replay tier 從未出現在 row body。R7 acceptance A10-1/2/3 會假綠。
--
--   V055 retrofit 用相同 19-arg signature 替換 function 但把 3 個 metadata
--   args forward 進 row body。Verify 部分保持 byte-equal 以維持行為契約。
--
-- When to apply / 何時 apply:
--   Required before R6-T1+T2 (Rust fee/slippage model in apply_fill) and
--   R7 (4 producer 升級 verify_replay_evidence_and_insert with calibrated
--   metadata) IMPL begin. Without V055 R7-T1/T3 producer 升級會把 row 寫
--   成 real_outcome / NULL,NULL,NULL，A10 acceptance 假綠。
--
--   R6-T1+T2 (Rust fee/slippage model) 與 R7 (4 producer 升級) IMPL 起跑前
--   必先 apply。否則 R7 升級後 producer 寫的 row 仍是 real_outcome 路徑，
--   A10 acceptance 假綠。
--
-- Migration order / 遷移順序:
--   V036 (function PR1) → V038 → V039 → V040 (tier column 3-step retrofit)
--   → V049 (replay_experiments 22 col) → V051 (mlde_recommendations 2 new
--   replay metadata col + paired CHECK) → V055 (this; PR3 function body
--   retrofit).
--
-- Idempotency / 幂等性:
--   `CREATE OR REPLACE FUNCTION` overrides the previous body when re-run.
--   Guard A function existence + 19-arg signature check is no-op on re-run.
--
--   `CREATE OR REPLACE FUNCTION` 重跑時覆寫舊 body。Guard A function 存在
--   + 19-arg signature 檢查重跑無 RAISE。
--
-- Guard A: enforced (function existence + arg count + arg signature
--          byte-equal V036 via pg_get_function_identity_arguments).
--          Post-INSERT 4-tier path verification covered by Python sibling
--          test (see Round 5 design pivot section below).
-- Guard B: N/A (no ALTER COLUMN; function-only DDL).
-- Guard C: N/A (no index DDL).
--
-- Round 5 design pivot (2026-05-05) / Round 5 設計修正:
--   PL/pgSQL DO block 不允許 explicit SAVEPOINT / ROLLBACK TO SAVEPOINT
--   (PostgreSQL hard constraint: "unsupported transaction command in
--    PL/pgSQL"). Round 1-4 嘗試在 migration 內做 4-tier post-INSERT smoke
--   被 PG 16 deploy reject。
--
--   Decision: drop Guard A post-INSERT smoke entirely from migration.
--   4-tier path verification covered by Python sibling test
--   `test_v055_evidence_insert_fix.py` (4 case test_v055_*_path) under
--   OPENCLAW_TEST_LIVE_PG=1 environment — equivalent semantic, avoids
--   PL/pgSQL constraint.
--
--   Guard A retains 3 migration-time enforces:
--     1. function existence post-CREATE OR REPLACE
--     2. 19-arg pronargs byte-equal V036
--     3. pg_get_function_identity_arguments byte-equal V036
--
--   PL/pgSQL DO block 不允許 explicit SAVEPOINT/ROLLBACK TO SAVEPOINT
--   (PG 硬限制：unsupported transaction command in PL/pgSQL)。Round 1-4
--   嘗試 migration 內 4-tier smoke 被 PG 16 deploy reject。
--
--   Decision：drop Guard A post-INSERT smoke。4-tier path 由 Python
--   sibling test 在 OPENCLAW_TEST_LIVE_PG=1 真 PG 環境覆蓋，等價語意。
--
--   Guard A 仍保 3 條 migration-time enforce：function existence /
--   19-arg pronargs / identity_arguments byte-equal V036。
--
--   H-1 finding revisit: drop smoke entirely → 不引入 EXCEPTION block →
--   H-1 (silent skip 反模式) 仍 fixed，不退步。Future in-migration smoke
--   pattern options: PG 11+ procedure (allows COMMIT/ROLLBACK) or split
--   smoke as separate migration (V055.1 one-shot DROP). Current decision
--   trusts sibling test.
--
--   H-1 finding revisit：完全 drop smoke → 不引入 EXCEPTION block →
--   H-1（silent skip 反模式）仍 fixed，不退步。未來 migration 內 smoke
--   pattern 選項：PG 11+ procedure（允許 COMMIT/ROLLBACK）或拆 smoke 為
--   separate migration（V055.1 一次性 DROP）。當前 decision 信 sibling
--   test。
--
-- Spec source / 規格來源:
--   docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-05--ref20_r6_r7_capability_risk.md §3.5 + §8.2
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-05--ref20_sprint_c_task_dag.md §13.1 + §13.5
--   docs/execution_plan/2026-05-04--ref20_gap_closure_reality_backtest_plan_v1.md (Sprint C R6-T0')
-- Reservation ledger / 預留 ledger:
--   sql/migrations/REF-20_RESERVATION.md §3 V055 row

-- ─────────────────────────────────────────────────────────────────────────────
-- Schema preflight / 預檢
--
-- V055 retrofit 對 V036 verify_replay_evidence_and_insert function 改 body。
-- 需要 V036 / V038-V040 / V049 / V051 全已 apply 才有意義。
-- V055 retrofit overrides V036's function body. V036 / V038-V040 / V049 /
-- V051 must all be applied for V055 to make sense.
--
-- Round 2 fix (E2 finding C-1) / Round 2 修補（E2 finding C-1）：
--   `expires_at` column 的 preflight 已**移除**。它從未被任何 migration
--   加到 `learning.mlde_shadow_recommendations`，是 V036 docstring 字面
--   誤導；TTL 真實 source-of-truth 是 `replay.experiments.expires_at`
--   (V049 line 305 ADD COLUMN)，advisory row 透 V051 FK 取得。
--   The `expires_at` column preflight has been **removed**. It is not added
--   to `learning.mlde_shadow_recommendations` by any migration; the V036
--   docstring's "4 columns" wording was misleading. TTL canonical source
--   is `replay.experiments.expires_at` (V049 line 305 ADD COLUMN), which
--   advisory rows access via the V051 FK.
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_v036_function_exists BOOLEAN;
    v_evidence_tier_col_exists BOOLEAN;
    v_evidence_tier_nullable TEXT;
    v_replay_experiment_id_col_exists BOOLEAN;
    v_manifest_hash_col_exists BOOLEAN;
    v_v051_check_exists BOOLEAN;
BEGIN
    -- V036 function existence (PR1).
    SELECT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'verify_replay_evidence_and_insert'
    ) INTO v_v036_function_exists;

    IF NOT v_v036_function_exists THEN
        RAISE EXCEPTION
            'V055 preflight: learning.verify_replay_evidence_and_insert function not found. '
            'V036 must be applied before V055 retrofit.';
    END IF;

    -- V038/V040 evidence_source_tier column (NOT NULL after V040).
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND column_name = 'evidence_source_tier'
    ) INTO v_evidence_tier_col_exists;

    IF NOT v_evidence_tier_col_exists THEN
        RAISE EXCEPTION
            'V055 preflight: learning.mlde_shadow_recommendations.evidence_source_tier column missing. '
            'V038 + V039 + V040 must be applied before V055 retrofit.';
    END IF;

    SELECT is_nullable INTO v_evidence_tier_nullable
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'mlde_shadow_recommendations'
      AND column_name = 'evidence_source_tier';

    IF v_evidence_tier_nullable <> 'NO' THEN
        RAISE EXCEPTION
            'V055 preflight: evidence_source_tier is_nullable=%, expected NO. '
            'V040 must complete (SET NOT NULL) before V055 retrofit.',
            v_evidence_tier_nullable;
    END IF;

    -- V051 replay_experiment_id + manifest_hash columns. expires_at is NOT
    -- expected on this table (round 2 fix: V055 INSERT only writes 3 columns).
    -- expires_at 不在此表（round 2 fix：V055 INSERT 只寫 3 column）。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND column_name = 'replay_experiment_id'
    ) INTO v_replay_experiment_id_col_exists;

    IF NOT v_replay_experiment_id_col_exists THEN
        RAISE EXCEPTION
            'V055 preflight: learning.mlde_shadow_recommendations.replay_experiment_id column missing. '
            'V051 must be applied before V055 retrofit.';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'mlde_shadow_recommendations'
          AND column_name = 'manifest_hash'
    ) INTO v_manifest_hash_col_exists;

    IF NOT v_manifest_hash_col_exists THEN
        RAISE EXCEPTION
            'V055 preflight: learning.mlde_shadow_recommendations.manifest_hash column missing. '
            'V051 must be applied before V055 retrofit.';
    END IF;

    -- V051 paired CHECK existence (3-tuple: tier / replay_experiment_id / manifest_hash).
    -- V051 paired CHECK 約束的是 3-tuple（tier / replay_experiment_id / manifest_hash），
    -- 不含 expires_at。
    SELECT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_mlde_shadow_replay_lineage'
          AND conrelid = 'learning.mlde_shadow_recommendations'::regclass
    ) INTO v_v051_check_exists;

    IF NOT v_v051_check_exists THEN
        RAISE EXCEPTION
            'V055 preflight: chk_mlde_shadow_replay_lineage paired CHECK absent. '
            'V051 must be applied before V055 retrofit.';
    END IF;

    RAISE NOTICE 'V055 preflight: V036 + V038-V040 + V051 prerequisites verified (3 columns: evidence_source_tier + replay_experiment_id + manifest_hash); continuing to function retrofit.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- V055 retrofit / V055 修補
--
-- Same 19-arg signature as V036; verify portion (1)-(4) byte-equal V036
-- (lines 137-191). The only change is the INSERT statement body which
-- now writes the THREE metadata columns (evidence_source_tier /
-- replay_experiment_id / manifest_hash) from caller args. The
-- p_expires_at argument is still validated by verify portion (4) but is
-- NOT persisted to a row column — TTL canonical source is
-- replay.experiments.expires_at (V049) accessed via V051 FK.
--
-- 同 V036 19-arg signature；verify 部分 (1)-(4) 與 V036 byte-equal
-- (line 137-191)。唯一變動 = INSERT statement body 加 3 metadata column
-- (evidence_source_tier / replay_experiment_id / manifest_hash) 寫入。
-- p_expires_at 仍走 verify portion (4) input validation 但**不持久化**
-- 到 row column —— TTL 真實來源 = replay.experiments.expires_at (V049)
-- 透 V051 FK 取。
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
    -- (1) evidence_source_tier 白名單檢查 / allowlist check (V036 byte-equal)
    IF p_evidence_source_tier IS NULL OR NOT (p_evidence_source_tier = ANY (v_allowed_tiers)) THEN
        RAISE EXCEPTION
            'verify_replay_evidence_and_insert: evidence_source_tier=% not in allowlist',
            p_evidence_source_tier
            USING DETAIL = 'Allowed tiers: real_outcome, calibrated_replay, synthetic_replay, counterfactual_replay',
                  HINT = 'Caller must classify the row tier per V3 §4.2 before invoking this function';
    END IF;

    -- (2) source 生產者白名單檢查 / producer source allowlist check (V036 byte-equal)
    IF p_source IS NULL OR NOT (p_source = ANY (v_allowed_sources)) THEN
        RAISE EXCEPTION
            'verify_replay_evidence_and_insert: source=% not in producer allowlist',
            p_source
            USING DETAIL = 'Allowed sources: ml_shadow, dream_engine, opportunity_tracker, linucb',
                  HINT = 'Replay-derived rows still classify under one of the four canonical producer slots';
    END IF;

    -- (3) replay-derived row 複合契約 / compound CHECK semantics (V036 byte-equal)
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

    -- (4) replay-derived row TTL 強檢 / TTL hard check (V036 byte-equal).
    --     Note: p_expires_at is INPUT VALIDATED here but NOT persisted to a
    --     row column (round 2 fix per E2 finding C-1). TTL canonical
    --     source-of-truth is replay.experiments.expires_at (V049) accessed
    --     by mlde_demo_applier_evidence_filter Block B via V051 FK.
    --     注：p_expires_at 在此走 input 驗證但**不**寫入 row column（round 2 fix
    --     per E2 finding C-1）。TTL 真實 source-of-truth = replay.experiments.expires_at
    --     (V049)，由 mlde_demo_applier_evidence_filter Block B 透 V051 FK 取。
    IF p_evidence_source_tier <> 'real_outcome' THEN
        IF p_expires_at IS NULL THEN
            RAISE EXCEPTION
                'verify_replay_evidence_and_insert: replay-derived row requires non-NULL expires_at'
                USING DETAIL = 'Replay manifest TTL contract: caller-provided per Sprint C §13.2 (typically 7d for calibrated, 3d for limited); validated as input only, persisted via FK to replay.experiments.expires_at',
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

    -- (5) Forward to INSERT writing 3 metadata columns per V055 retrofit.
    --     V051 paired CHECK chk_mlde_shadow_replay_lineage enforces row-level
    --     lineage invariant on the 3-tuple (evidence_source_tier,
    --     replay_experiment_id, manifest_hash):
    --       real_outcome     ⇒ both replay_experiment_id AND manifest_hash NULL
    --       non-real_outcome ⇒ both replay_experiment_id AND manifest_hash NOT NULL
    --     The verify pre-checks above already guarantee this consistency;
    --     paired CHECK is defense-in-depth at row level.
    --
    --     `expires_at` is NOT written to mlde_shadow_recommendations (no such
    --     column on this table; round 2 fix per E2 finding C-1). Read-side
    --     consumers JOIN replay.experiments via V051 FK to access TTL.
    --
    --     V055 retrofit relative to V036: forward 3 metadata columns into row
    --     body. p_replay_experiment_id is TEXT cast to UUID to match V051
    --     column type. p_manifest_hash is TEXT (hex digest) decoded to BYTEA
    --     to match V051 column type — caller produces hex digest rather than
    --     raw bytes for IPC-boundary portability.
    --
    --     V055 retrofit 對 V036 的差異：forward 3 個 metadata column 進 row
    --     body。p_replay_experiment_id 是 TEXT cast 為 UUID 對齊 V051 column
    --     type。p_manifest_hash 是 TEXT (hex digest) 由 decode(...,'hex')
    --     轉 BYTEA 對齊 V051 column type (caller 端產 hex digest 而非 raw
    --     bytes for portability across IPC boundary)。
    --
    --     `expires_at` **不**寫入 mlde_shadow_recommendations（此表無該
    --     column；round 2 fix per E2 finding C-1）。讀端消費者 JOIN
    --     replay.experiments 透 V051 FK 取 TTL。
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
        created_by,
        -- ── V055 retrofit: 3 replay metadata columns (V036 PR3) ──
        evidence_source_tier,        -- V038-V040: NOT NULL, 4-value enum
        replay_experiment_id,        -- V051: NULLABLE UUID FK to V049
        manifest_hash                -- V051: NULLABLE BYTEA hex digest
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
        p_created_by,
        -- ── V055 retrofit: 3 replay metadata column 寫入 ──
        -- evidence_source_tier 直接 TEXT (V040 4-value CHECK enum 自動驗)
        p_evidence_source_tier,
        -- replay_experiment_id 是 TEXT 傳入，cast 為 UUID 對齊 V051 column type
        p_replay_experiment_id::UUID,
        -- manifest_hash 是 TEXT (hex digest) 傳入，decode 為 BYTEA 對齊 V051 column type
        CASE WHEN p_manifest_hash IS NULL THEN NULL ELSE decode(p_manifest_hash, 'hex') END
    )
    RETURNING id INTO v_new_id;

    RETURN v_new_id;
END;
$$;

-- COMMENT ON FUNCTION update / 函數註解 update：
-- 移除 V036 docstring「PR3 will retrofit」字眼，標記 V055 retrofit complete。
-- Strip "PR3 will retrofit" wording; mark V055 retrofit complete.
-- Round 2 fix: explicitly state V055 writes 3 columns (NOT 4); p_expires_at
-- is validated as input but not persisted (TTL via V049 FK).
-- Round 2 修補：明確說明 V055 寫 3 column（不是 4）；p_expires_at 走 input
-- 驗證但不持久化（TTL 經 V049 FK 取得）。
COMMENT ON FUNCTION learning.verify_replay_evidence_and_insert(
    TEXT, TEXT, TEXT, TEXT, TEXT,
    DOUBLE PRECISION, DOUBLE PRECISION, INTEGER, JSONB,
    BOOLEAN, BOOLEAN, TEXT,
    TEXT, TEXT, TEXT, TIMESTAMPTZ, TEXT, TEXT, TEXT
) IS
'REF-20 R20-P2a-S4 + V055 retrofit complete. Sole sanctioned write path into '
'learning.mlde_shadow_recommendations once V037 REVOKEs PUBLIC INSERT. '
'Verify portion: evidence_source_tier allowlist + source allowlist + '
'real_outcome/replay-derived compound CHECK + TTL hard check (input '
'validation only). INSERT body forwards 3 replay metadata columns '
'(evidence_source_tier / replay_experiment_id / manifest_hash) per V055 '
'retrofit. p_expires_at is validated as input but NOT persisted to a row '
'column; TTL canonical source-of-truth is replay.experiments.expires_at '
'(V049) accessed via V051 FK. / 唯一合規寫入路徑 (V037 後)；驗 tier/source '
'白名單 + real_outcome 對 replay 複合契約 + TTL（input 驗證）；V055 retrofit '
'後 INSERT body 寫入 3 個 metadata column (evidence_source_tier / '
'replay_experiment_id / manifest_hash)。p_expires_at 走 input 驗證但**不**'
'寫入 row column；TTL 真實 source-of-truth = replay.experiments.expires_at '
'(V049) 透 V051 FK 取。';

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A (post-create): function existence + 19-arg signature byte-equal V036.
-- Guard A (建立後): 驗 function 存在 + 19-arg signature 與 V036 byte-equal。
-- Idempotent: re-running V055 hits CREATE OR REPLACE → same signature → no RAISE.
-- 重跑 V055：CREATE OR REPLACE 命中相同 signature，Guard 不 RAISE。
--
-- Round 2 fix (E2 finding C-2) / Round 2 修補（E2 finding C-2）：
--   Signature drift detection switched from substring `position()` against
--   `pg_get_function_arguments()` (which contains arg name + DEFAULT clause
--   noise on PG 13+) to strict equality against
--   `pg_get_function_identity_arguments()` which returns ONLY the type list
--   (no arg name, no DEFAULT clause). The expected string is V036's
--   canonical 19-type identity_arguments output.
--
--   Signature drift 檢測從 substring `position()` 對 `pg_get_function_arguments()`
--   （含 arg name + DEFAULT clause 干擾，PG 13+）改為 strict equality 對
--   `pg_get_function_identity_arguments()`（只回 type list，0 arg name + 0
--   DEFAULT clause）。Expected 字串 = V036 的 canonical 19-type
--   identity_arguments 輸出。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_func_exists BOOLEAN;
    v_arg_count INT;
    v_expected_arg_count INT := 19;
    v_identity_args TEXT;
    -- Round 4 hotfix: PG 16 empirically returns arg names + types (no DEFAULT
    -- clause) from pg_get_function_identity_arguments. PG docs claim "stripped
    -- down" but empirical PG 16 includes arg names — Linux deploy 2026-05-05
    -- confirmed signature drift exception when expected hardcoded as pure type
    -- list. Expected string aligned to V036 declaration line 92-110 with
    -- p_<name> <type> tokens (lower-cased, comma-space separated, no DEFAULT
    -- clause). lower(...) wrapper kept for case-insensitive comparison with
    -- line 527 lower(pg_get_function_identity_arguments(p.oid)).
    -- Round 4 hotfix：PG 16 empirically pg_get_function_identity_arguments 回
    -- arg name + 型別（無 DEFAULT clause）。PG docs 聲稱 "stripped-down" 但
    -- 真實 PG 16 含 arg names — 2026-05-05 Linux deploy 確認 expected hardcode
    -- 為純 type list 觸 signature drift exception。Expected 字串對齊 V036
    -- declaration line 92-110 的 p_<name> <type> token（小寫、逗號空格分隔、
    -- 無 DEFAULT clause）。lower(...) 包裹保留與 line 527
    -- lower(pg_get_function_identity_arguments(p.oid)) case-insensitive 對齊。
    v_expected_identity_args TEXT := lower(
        'p_engine_mode text, p_symbol text, p_strategy_name text, p_source text, '
        'p_recommendation_type text, p_expected_net_bps double precision, '
        'p_confidence double precision, p_sample_count integer, p_payload jsonb, '
        'p_applied boolean, p_requires_governance boolean, p_created_by text, '
        'p_evidence_source_tier text, p_replay_experiment_id text, '
        'p_manifest_hash text, p_expires_at timestamp with time zone, '
        'p_decision_lease_id text, p_context_id text, p_intent_id text'
    );
BEGIN
    -- function existence
    SELECT EXISTS (
        SELECT 1 FROM pg_proc p
        JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'learning'
          AND p.proname = 'verify_replay_evidence_and_insert'
    ) INTO v_func_exists;

    IF NOT v_func_exists THEN
        RAISE EXCEPTION 'V055 Guard A: learning.verify_replay_evidence_and_insert function not found after CREATE OR REPLACE';
    END IF;

    -- arg count = 19 (V036 byte-equal)
    SELECT pronargs INTO v_arg_count
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'learning'
      AND p.proname = 'verify_replay_evidence_and_insert';

    IF v_arg_count <> v_expected_arg_count THEN
        RAISE EXCEPTION
            'V055 Guard A: verify_replay_evidence_and_insert arg count drift; expected %, actual %. '
            'V055 must preserve V036 19-arg signature byte-equal.',
            v_expected_arg_count, v_arg_count;
    END IF;

    -- arg signature byte-equal V036 via pg_get_function_identity_arguments.
    -- pg_get_function_identity_arguments 在 PG 16 empirically returns arg
    -- names + types (no DEFAULT clause)，與 V036 declaration line 92-110 對齊；
    -- strict equality 比對含 arg name 確保 V055 retrofit signature 不破 V036
    -- caller binding（caller side 0 改動）。
    -- pg_get_function_identity_arguments empirically returns arg names +
    -- types on PG 16 (no DEFAULT clause), aligning with V036 declaration
    -- line 92-110; strict equality including arg names ensures V055 retrofit
    -- signature does not break V036 caller binding (callers need 0 changes).
    -- (Round 4 hotfix 2026-05-05: PG docs claim "stripped-down" 但 PG 16 真實
    --  行為含 arg names — Linux deploy 觸 signature drift exception；expected
    --  string 必同步含 arg names。Lesson: future SQL ops 必先 query 真實 PG
    --  output 取格式再 hardcode expected。)
    -- (Round 4 hotfix 2026-05-05: PG docs claim "stripped-down" but PG 16
    --  empirically includes arg names — Linux deploy raised signature drift
    --  exception; expected string must include arg names too. Lesson: future
    --  SQL ops must query empirical PG output for format before hardcoding
    --  expected.)
    SELECT lower(pg_get_function_identity_arguments(p.oid)) INTO v_identity_args
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'learning'
      AND p.proname = 'verify_replay_evidence_and_insert';

    IF v_identity_args <> v_expected_identity_args THEN
        RAISE EXCEPTION
            'V055 Guard A: verify_replay_evidence_and_insert arg signature drift. '
            'Expected V036 byte-equal (19 types via pg_get_function_identity_arguments). '
            'Expected: %. Actual: %',
            v_expected_identity_args, v_identity_args;
    END IF;

    RAISE NOTICE 'V055 Guard A: verify_replay_evidence_and_insert function existence + 19-arg signature (identity_arguments byte-equal V036) verified.';
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Round 5 design pivot (2026-05-05): 4-tier post-INSERT smoke removed.
-- Round 5 設計修正（2026-05-05）：4-tier post-INSERT smoke 已移除。
--
-- PostgreSQL hard constraint: PL/pgSQL DO block forbids explicit
-- `SAVEPOINT name` and `ROLLBACK TO SAVEPOINT name`; PG raises
-- `unsupported transaction command in PL/pgSQL`. Round 1-4 attempts
-- to embed a 4-tier post-INSERT smoke inside this migration were
-- rejected by PG 16 deploy.
--
-- Decision: 4-tier path verification migrated to Python sibling test
-- `program_code/exchange_connectors/bybit_connector/control_api_v1/
--  tests/replay/test_v055_evidence_insert_fix.py` —
--   - test_v055_real_outcome_path
--   - test_v055_calibrated_replay_path
--   - test_v055_synthetic_replay_path
--   - test_v055_counterfactual_replay_path
-- and `test_v055_live_pg_*` cases under OPENCLAW_TEST_LIVE_PG=1 +
-- OPENCLAW_TEST_DSN env (Linux PG). Equivalent semantic; avoids the
-- PL/pgSQL transaction-command constraint.
--
-- Migration-time Guard A still enforces 3 invariants above:
--   1. function existence post-CREATE OR REPLACE
--   2. 19-arg pronargs byte-equal V036
--   3. pg_get_function_identity_arguments byte-equal V036
--
-- H-1 invariant preserved: by removing the SAVEPOINT block entirely,
-- no EXCEPTION block is introduced; Round 1 H-1 (silent skip 反模式)
-- finding remains fixed.
--
-- PostgreSQL 硬限制：PL/pgSQL DO block 不允許 explicit `SAVEPOINT name`
-- / `ROLLBACK TO SAVEPOINT name`；PG raise `unsupported transaction
-- command in PL/pgSQL`。Round 1-4 嘗試 migration 內 4-tier post-INSERT
-- smoke 被 PG 16 deploy reject。
--
-- Decision：4-tier path verification 遷至 Python sibling test
-- `test_v055_evidence_insert_fix.py` —
--   - test_v055_real_outcome_path
--   - test_v055_calibrated_replay_path
--   - test_v055_synthetic_replay_path
--   - test_v055_counterfactual_replay_path
-- 加 `test_v055_live_pg_*` 走 OPENCLAW_TEST_LIVE_PG=1 +
-- OPENCLAW_TEST_DSN env（Linux PG）。等價語意；避 PL/pgSQL transaction
-- command 限制。
--
-- Migration-time Guard A 仍保 3 invariants：
--   1. function existence post-CREATE OR REPLACE
--   2. 19-arg pronargs byte-equal V036
--   3. pg_get_function_identity_arguments byte-equal V036
--
-- H-1 invariant 保留：完全移除 SAVEPOINT block → 不引入 EXCEPTION block →
-- Round 1 H-1（silent skip 反模式）finding 仍 fixed。
-- ─────────────────────────────────────────────────────────────────────────────
--
-- (Round 1-4 in-migration 4-tier post-INSERT smoke block removed in round 5
-- per the design pivot section above. All path semantics preserved by
-- Python sibling test under OPENCLAW_TEST_LIVE_PG=1; see file header.)
--
-- (Round 1-4 migration 內 4-tier post-INSERT smoke block 已於 round 5
-- 移除，原因見上方 design pivot section。所有 path 語意由 Python sibling
-- test 在 OPENCLAW_TEST_LIVE_PG=1 真 PG 環境覆蓋；見檔頭。)
-- ─────────────────────────────────────────────────────────────────────────────

-- ─────────────────────────────────────────────────────────────────────────────
-- Operator deploy note / Operator 部署備忘:
--   1. V055 land first (this file; CREATE OR REPLACE FUNCTION).
--   2. After V055 deploy, R6-T1+T2 (Rust fee/slippage model in apply_fill)
--      and R7 (4 producer 升級 verify_replay_evidence_and_insert with
--      calibrated metadata) IMPL can begin without silent corruption.
--   3. R7 producer caller MUST set p_replay_experiment_id (UUID as TEXT) +
--      p_manifest_hash (hex digest as TEXT) + p_expires_at when
--      evidence_source_tier <> 'real_outcome'. p_expires_at is input-validated
--      by verify portion (4) but NOT persisted to a row column; TTL canonical
--      source-of-truth = replay.experiments.expires_at (V049) accessed via
--      V051 FK.
--   4. V055 Guard A enforces 3 invariants at deploy time: function
--      existence post-CREATE OR REPLACE + 19-arg pronargs + 19-arg
--      identity_arguments byte-equal V036 (via
--      pg_get_function_identity_arguments). 4-tier path verification is
--      covered by Python sibling test_v055_evidence_insert_fix.py
--      (test_v055_*_path 4 case + Linux PG opt-in test_v055_live_pg_*
--      under OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN env). Round 5
--      design pivot — see file header.
--
-- Operator 部署順序:
--   1. V055 上線 (本檔；CREATE OR REPLACE FUNCTION)。
--   2. V055 deploy 後，R6-T1+T2 (Rust fee/slippage in apply_fill) 與 R7
--      (4 producer 升級 verify_replay_evidence_and_insert with calibrated
--      metadata) IMPL 可起跑，0 silent corruption 風險。
--   3. R7 producer caller 在 evidence_source_tier <> 'real_outcome' 時必傳
--      p_replay_experiment_id (UUID as TEXT) + p_manifest_hash (hex digest
--      as TEXT) + p_expires_at；p_expires_at 走 verify portion (4) input
--      驗證但**不**持久化到 row column；TTL 真實 source-of-truth =
--      replay.experiments.expires_at (V049) 透 V051 FK 取。
--   4. V055 Guard A 在 deploy 時 enforce 3 invariants：function existence
--      post-CREATE OR REPLACE + 19-arg pronargs + 19-arg identity_arguments
--      byte-equal V036（透 pg_get_function_identity_arguments）。4-tier
--      path 驗證由 Python sibling test_v055_evidence_insert_fix.py
--      (test_v055_*_path 4 case + Linux PG opt-in test_v055_live_pg_*
--      在 OPENCLAW_TEST_LIVE_PG=1 + OPENCLAW_TEST_DSN env) 覆蓋。Round 5
--      design pivot — 見檔頭。
-- ─────────────────────────────────────────────────────────────────────────────

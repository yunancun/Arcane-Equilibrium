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
--   Post-INSERT 4-tier smoke runs inside a savepoint; ROLLBACK keeps PG
--   state pristine.
--
--   `CREATE OR REPLACE FUNCTION` 重跑時覆寫舊 body。Guard A function 存在
--   + 19-arg signature 檢查重跑無 RAISE。Post-INSERT 4-tier smoke 跑在
--   savepoint 內 ROLLBACK，PG 狀態保持乾淨。
--
-- Guard A: enforced (function existence + arg count + arg signature
--          byte-equal V036 via pg_get_function_identity_arguments;
--          4-tier post-INSERT smoke verifies row body 3 column matches
--          caller args).
-- Guard B: N/A (no ALTER COLUMN; function-only DDL).
-- Guard C: N/A (no index DDL).
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
-- Guard A post-INSERT smoke: 4-tier path verification.
-- Guard A post-INSERT smoke：4 path row body 驗證。
--
-- 在 SAVEPOINT 內 INSERT 4 row 各 path，SELECT 驗 row body 3 column 對齊
-- caller args，最後 ROLLBACK 不污染 production data。Mismatch RAISE EXCEPTION。
--
-- Inside a SAVEPOINT, INSERT 4 rows (one per path), SELECT row body to verify
-- the 3 columns match caller args, then ROLLBACK so no production data is
-- polluted. Any mismatch RAISE EXCEPTION.
--
-- 必驗 4 path / Must verify 4 paths:
--   1. real_outcome → tier='real_outcome', exp_id NULL, hash NULL
--   2. calibrated_replay → tier match, exp_id NOT NULL, hash NOT NULL
--   3. synthetic_replay → 同上 with synthetic_replay tier
--   4. counterfactual_replay → 同上 with counterfactual_replay tier
--
-- Round 2 fix (E2 finding H-1) / Round 2 修補（E2 finding H-1）：
--   1. path 1 real_outcome 拆出 stub experiment INSERT 之外（不依賴 FK，
--      永跑）。
--   2. inner BEGIN-END 已**移除** EXCEPTION WHEN OTHERS silent skip 模式。
--      任何 stub INSERT 或 path 2-4 INSERT 異常自然 propagate 到上層 DO $$
--      block，最終 RAISE EXCEPTION 給 psql apply 端 fail-loud（CLAUDE.md §九
--      無 silent fallthrough 原則的 SQL 等價）。
--   3. ROLLBACK TO SAVEPOINT 在 normal path（4 row INSERT 完成後）保留 —
--      是設計意圖（不污染 production data）。
--
--   1. path 1 real_outcome 拆出 stub experiment INSERT 之外（不需 FK，永跑）。
--   2. inner BEGIN-END 已**移除** EXCEPTION WHEN OTHERS silent skip。任何
--      stub INSERT / path 2-4 異常自然 propagate 上層 DO $$ block 最終
--      RAISE EXCEPTION 給 psql apply 端 fail-loud（CLAUDE.md §九 無 silent
--      fallthrough 原則的 SQL 等價）。
--   3. ROLLBACK TO SAVEPOINT 保留於 normal path（4 row INSERT 完成後）—
--      設計意圖：不污染 production data。
--
-- Round 2 fix (E2 finding M-2) / Round 2 修補（E2 finding M-2）：
--   replay.experiments stub INSERT 提供 V049 全 unconditional NOT NULL
--   column。V049 line 282-307 ADD COLUMN 全為 NULLABLE（IF NOT EXISTS 加列
--   無 NOT NULL constraint）。V041 stub bootstrap 既有 4 column 皆有 default
--   或 NULLABLE：experiment_id (PK NOT NULL) / half_life_days (V041 default
--   或要求 supply) / embargo_days (V041 default 或要求 supply) / created_at
--   (default now())。V049 conditional NOT NULL = engine_binary_sha when
--   runtime_environment='linux_trade_core' (CHECK 不是 NOT NULL；用
--   runtime_environment='mac_dev_smoke_test_only' 規避)。
--
-- Round 3 fix (E2 finding C-3) / Round 3 修補（E2 finding C-3）：
--   Round 2 stub INSERT 引用 phantom column `actor_id` 是錯的。E2 round 2
--   cross-grep 揭露：V049 line 282-307 18 ADD COLUMN list 內 line 284 真實
--   命名 `created_by`，而非 `actor_id`。V049 對 `replay.experiments` 完全
--   未加 `actor_id` column。`actor_id` 實是 `replay.run_state` 表的 column
--   (V045:199 NOT NULL)，與 `replay.experiments` schema 完全無關。
--
--   選 A 修正（最小變動）：直接刪除 stub INSERT 中的 `actor_id` column
--   reference + 對應 VALUES 位置。理由：(1) actor_id 不存在於 replay.experiments
--   schema，Linux deploy 必撞 `column "actor_id" of relation "experiments"
--   does not exist`；(2) 不引入 created_by 替代以保持最小變動；(3) status
--   是 V049 真實 column 但 NULLABLE + V049 line 384-395 chk_replay_experiments_status
--   CHECK 接受 NULL，所以保留 status='created' 寫入 OK 不必動；(4) 修正後
--   stub INSERT 寫 6 column：experiment_id / status / created_at /
--   half_life_days / embargo_days / runtime_environment，全是 V041 base 4 col
--   + V049 conditional NOT NULL bypass column，0 phantom。
--
--   stub minimal subset (round 3 corrected) = experiment_id (PK 由 caller
--   gen_random_uuid) + status (V049 5-value enum NULL OK 但寫 'created' 標記
--   smoke 來源) + created_at (V041 default now() 但顯式 supply 對齊) +
--   half_life_days (V041 既有 NULLABLE) + embargo_days (V041 既有 NULLABLE)
--   + runtime_environment='mac_dev_smoke_test_only' (V049 conditional NOT
--   NULL bypass via CHECK chk_replay_experiments_engine_sha_linux)。
--
--   V049 22 col NOT NULL set per source line N-M / V049 line 282-307 ADD COLUMN
--   全 NULLABLE（IF NOT EXISTS 加列）。Conditional NOT NULL 在 V049 line 425-433
--   chk_replay_experiments_engine_sha_linux CHECK，runtime='mac_dev_smoke_test_only'
--   時不觸發。V041 既有 4 col：experiment_id PK NOT NULL / half_life_days /
--   embargo_days / created_at。Stub minimal subset 已含全部 unconditional
--   NOT NULL（experiment_id 由 caller 傳）+ V041 既有 + V049 nullable column
--   default NULL OK。
--
--   Round 3 fix (E2 finding C-3): the round 2 stub INSERT referenced phantom
--   column `actor_id`. E2 round 2 cross-grep revealed: V049 line 282-307's
--   18 ADD COLUMN list contains `created_by` at line 284, NOT `actor_id`.
--   V049 never adds `actor_id` to `replay.experiments`. `actor_id` actually
--   belongs to `replay.run_state` (V045:199 NOT NULL), unrelated to the
--   `replay.experiments` schema.
--
--   Option A fix (minimal change): simply delete the `actor_id` column
--   reference + matching VALUES position from the stub INSERT. Rationale:
--   (1) actor_id does not exist in replay.experiments schema; Linux deploy
--   would fail with `column "actor_id" of relation "experiments" does not
--   exist`. (2) Do NOT introduce created_by as replacement — preserve
--   minimal change. (3) status is a real V049 column but NULLABLE +
--   chk_replay_experiments_status CHECK accepts NULL, so retaining
--   status='created' write is OK with no change. (4) After fix the stub
--   INSERT writes 6 columns: experiment_id / status / created_at /
--   half_life_days / embargo_days / runtime_environment — all are V041 base
--   4 col + V049 conditional NOT NULL bypass column. 0 phantom.
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_test_experiment_id UUID;
    v_test_manifest_hash_hex TEXT := '0000000000000000000000000000000000000000000000000000000000000001';
    v_test_expires_at TIMESTAMPTZ := now() + INTERVAL '7 days';
    v_inserted_id BIGINT;
    v_row_tier TEXT;
    v_row_exp_id UUID;
    v_row_hash BYTEA;
BEGIN
    -- pin a savepoint so all smoke INSERTs roll back cleanly.
    -- 設 savepoint 讓 4 個 smoke INSERT 乾淨 ROLLBACK。
    SAVEPOINT v055_smoke;

    -- ─── path 1: real_outcome (no FK dependency; always runs) ───────────────
    -- path 1 不依賴 replay.experiments FK（real_outcome ⇒ replay_experiment_id
    -- IS NULL），先跑。Round 2 fix (E2 H-1)：path 1 拆出 stub experiment INSERT
    -- 之外，永跑。
    SELECT learning.verify_replay_evidence_and_insert(
        'demo',                          -- p_engine_mode
        'BTCUSDT',                       -- p_symbol
        'ma_crossover',                  -- p_strategy_name
        'ml_shadow',                     -- p_source
        'rank',                          -- p_recommendation_type
        12.5,                            -- p_expected_net_bps
        0.65,                            -- p_confidence
        100,                             -- p_sample_count
        '{"v055":"smoke"}'::jsonb,       -- p_payload
        false,                           -- p_applied
        true,                            -- p_requires_governance
        'v055_smoke',                    -- p_created_by
        'real_outcome',                  -- p_evidence_source_tier
        NULL,                            -- p_replay_experiment_id
        NULL,                            -- p_manifest_hash
        NULL,                            -- p_expires_at
        NULL,                            -- p_decision_lease_id
        NULL,                            -- p_context_id
        NULL                             -- p_intent_id
    ) INTO v_inserted_id;

    SELECT evidence_source_tier, replay_experiment_id, manifest_hash
    INTO v_row_tier, v_row_exp_id, v_row_hash
    FROM learning.mlde_shadow_recommendations
    WHERE id = v_inserted_id;

    IF v_row_tier <> 'real_outcome' OR v_row_exp_id IS NOT NULL OR v_row_hash IS NOT NULL THEN
        RAISE EXCEPTION
            'V055 Guard A smoke real_outcome path mismatch: tier=%, exp_id=%, hash=% (expected real_outcome / NULL / NULL)',
            v_row_tier, v_row_exp_id, v_row_hash;
    END IF;

    -- ─── replay.experiments stub for path 2-4 FK / path 2-4 FK 用 stub ───────
    -- V055 retrofit smoke 需要 replay.experiments 內有一行測試 row 才能滿足
    -- V051 fk_mlde_shadow_replay_experiment FK 至 V049。我們插一個 stub
    -- experiment row (smoke savepoint 內) 然後 ROLLBACK。
    -- V055 retrofit smoke needs a stub replay.experiments row to satisfy V051 FK.
    -- We INSERT a stub inside the savepoint then ROLLBACK at the end.
    --
    -- Round 2 fix (E2 H-1)：移除 EXCEPTION WHEN OTHERS silent skip。任何 V049
    -- NOT NULL drift 必須 fail-loud 才能 catch；不再 graceful skip。
    -- Round 2 fix (E2 M-2)：minimal subset 含 V049 conditional NOT NULL 規避路徑
    -- (runtime_environment='mac_dev_smoke_test_only' 不觸發 engine_binary_sha
    -- requirement)。
    -- Round 3 fix (E2 C-3)：移除 phantom column `actor_id`。E2 round 2 cross-grep
    -- 揭露 round 2 stub INSERT 引用 `actor_id` 是 phantom（V049 line 282-307 18
    -- ADD COLUMN 真實命名 `created_by` 在 line 284，無 `actor_id`）。Linux deploy
    -- 端必撞 `column "actor_id" of relation "experiments" does not exist`。
    -- 選 A 修正：刪除 phantom column reference + VALUES 對應，保持其他 column
    -- (V041 base 4 col + V049 conditional NOT NULL bypass) 不動。`actor_id` 本就是
    -- `replay.run_state` 的 column（V045:199），與 `replay.experiments` 無關。
    --
    -- Round 2 fix (E2 H-1): EXCEPTION WHEN OTHERS silent skip removed. Any
    -- V049 NOT NULL drift must fail-loud; no more graceful skip.
    -- Round 2 fix (E2 M-2): minimal subset includes V049 conditional NOT NULL
    -- bypass path (runtime_environment='mac_dev_smoke_test_only' avoids
    -- engine_binary_sha requirement).
    -- Round 3 fix (E2 C-3): phantom column `actor_id` removed from stub INSERT.
    -- E2 round 2 cross-grep revealed the round 2 stub INSERT referenced
    -- a phantom column (V049 line 282-307's 18 ADD COLUMN list contains
    -- `created_by` at line 284, NOT `actor_id`). Linux deploy would fail with
    -- `column "actor_id" of relation "experiments" does not exist`. Option A
    -- fix: remove the phantom column reference + matching VALUES position;
    -- preserve V041 base 4 col + V049 conditional NOT NULL bypass.
    -- `actor_id` is actually a column on `replay.run_state` (V045:199), not
    -- `replay.experiments`.
    v_test_experiment_id := gen_random_uuid();

    INSERT INTO replay.experiments (
        experiment_id,
        status,
        created_at,
        half_life_days,
        embargo_days,
        runtime_environment           -- V049 conditional NOT NULL bypass via mac_dev_smoke_test_only
    ) VALUES (
        v_test_experiment_id,
        'created',                    -- V049 5-value enum (V049 line 393)
        now(),
        14.0,                         -- V041 stub field (kept by V049)
        14,                           -- V041 stub field (kept by V049)
        'mac_dev_smoke_test_only'     -- V049 line 341 enum + line 425-433 conditional NOT NULL bypass
    );

    -- ─── path 2: calibrated_replay ──────────────────────────────────────
    SELECT learning.verify_replay_evidence_and_insert(
        'demo',
        'BTCUSDT',
        'ma_crossover',
        'ml_shadow',
        'rank',
        12.5,
        0.65,
        100,
        '{"v055":"smoke"}'::jsonb,
        false,
        true,
        'v055_smoke',
        'calibrated_replay',
        v_test_experiment_id::TEXT,
        v_test_manifest_hash_hex,
        v_test_expires_at,
        NULL,
        NULL,
        NULL
    ) INTO v_inserted_id;

    SELECT evidence_source_tier, replay_experiment_id, manifest_hash
    INTO v_row_tier, v_row_exp_id, v_row_hash
    FROM learning.mlde_shadow_recommendations
    WHERE id = v_inserted_id;

    IF v_row_tier <> 'calibrated_replay' OR v_row_exp_id <> v_test_experiment_id OR v_row_hash IS NULL THEN
        RAISE EXCEPTION
            'V055 Guard A smoke calibrated_replay path mismatch: tier=%, exp_id=%, hash_is_null=% (expected calibrated_replay / non-NULL / non-NULL)',
            v_row_tier, v_row_exp_id, (v_row_hash IS NULL);
    END IF;

    -- ─── path 3: synthetic_replay ───────────────────────────────────────
    SELECT learning.verify_replay_evidence_and_insert(
        'demo',
        'BTCUSDT',
        'ma_crossover',
        'ml_shadow',
        'rank',
        12.5,
        0.65,
        100,
        '{"v055":"smoke"}'::jsonb,
        false,
        true,
        'v055_smoke',
        'synthetic_replay',
        v_test_experiment_id::TEXT,
        v_test_manifest_hash_hex,
        v_test_expires_at,
        NULL,
        NULL,
        NULL
    ) INTO v_inserted_id;

    SELECT evidence_source_tier, replay_experiment_id, manifest_hash
    INTO v_row_tier, v_row_exp_id, v_row_hash
    FROM learning.mlde_shadow_recommendations
    WHERE id = v_inserted_id;

    IF v_row_tier <> 'synthetic_replay' OR v_row_exp_id <> v_test_experiment_id OR v_row_hash IS NULL THEN
        RAISE EXCEPTION
            'V055 Guard A smoke synthetic_replay path mismatch: tier=%, exp_id=%, hash_is_null=% (expected synthetic_replay / non-NULL / non-NULL)',
            v_row_tier, v_row_exp_id, (v_row_hash IS NULL);
    END IF;

    -- ─── path 4: counterfactual_replay ──────────────────────────────────
    SELECT learning.verify_replay_evidence_and_insert(
        'demo',
        'BTCUSDT',
        'ma_crossover',
        'ml_shadow',
        'rank',
        12.5,
        0.65,
        100,
        '{"v055":"smoke"}'::jsonb,
        false,
        true,
        'v055_smoke',
        'counterfactual_replay',
        v_test_experiment_id::TEXT,
        v_test_manifest_hash_hex,
        v_test_expires_at,
        NULL,
        NULL,
        NULL
    ) INTO v_inserted_id;

    SELECT evidence_source_tier, replay_experiment_id, manifest_hash
    INTO v_row_tier, v_row_exp_id, v_row_hash
    FROM learning.mlde_shadow_recommendations
    WHERE id = v_inserted_id;

    IF v_row_tier <> 'counterfactual_replay' OR v_row_exp_id <> v_test_experiment_id OR v_row_hash IS NULL THEN
        RAISE EXCEPTION
            'V055 Guard A smoke counterfactual_replay path mismatch: tier=%, exp_id=%, hash_is_null=% (expected counterfactual_replay / non-NULL / non-NULL)',
            v_row_tier, v_row_exp_id, (v_row_hash IS NULL);
    END IF;

    -- 全 4 path 通過後 ROLLBACK，不污染 production data。
    -- All 4 paths pass; ROLLBACK so no production data is polluted.
    ROLLBACK TO SAVEPOINT v055_smoke;
    RAISE NOTICE 'V055 Guard A post-INSERT smoke: 4-tier path verification PASS (real_outcome / calibrated_replay / synthetic_replay / counterfactual_replay). All row body 3 metadata columns match caller args.';
END $$;

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
--   4. V055 Guard A smoke verifies the 3-column write path is intact at
--      deploy time + 19-arg signature byte-equal V036 (via
--      pg_get_function_identity_arguments).
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
--   4. V055 Guard A smoke 在 deploy 時驗 3-column 寫入路徑完整 + 19-arg
--      signature byte-equal V036（透 pg_get_function_identity_arguments）。
-- ─────────────────────────────────────────────────────────────────────────────

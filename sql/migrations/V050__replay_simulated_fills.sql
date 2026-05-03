-- V050__replay_simulated_fills.sql
-- Purpose / 目的:
--   Create `replay.simulated_fills` per V3 §4.1 17-column contract. This is
--   the per-fill simulated-trade artifact registry that the P3+ replay_runner
--   writes (one row per simulated order/fill lifecycle event). It is FK-bound
--   to replay.experiments (V049) by experiment_id with ON DELETE CASCADE so
--   stale fills are pruned together with the parent experiment.
--
--   The non-negotiable boundary (V3 §2 #2 / §6.2 forbidden) is: replay never
--   writes simulated rows to trading.fills. replay.simulated_fills is the
--   isolated equivalent that lives in the replay schema and is read only by
--   P3+ replay routes; existing live/demo metric code MUST NOT read from it
--   (V3 §4.1 final paragraph).
--
--   建立 V3 §4.1 17 column 契約的 `replay.simulated_fills`。本表是 P3+
--   replay_runner 寫入的 per-fill simulated-trade artifact registry（一筆
--   simulated order/fill lifecycle event 一列）。透過 experiment_id ON DELETE
--   CASCADE FK 至 replay.experiments (V049)，stale fill 與 parent experiment
--   一起 prune。
--
--   不可協商紅線（V3 §2 #2 / §6.2 forbidden）：replay 永不寫 simulated row
--   到 trading.fills。replay.simulated_fills 是隔離等價物，存於 replay
--   schema，只由 P3+ replay routes 讀取；既有 live/demo metric 代碼禁讀
--   （V3 §4.1 最末段）。
--
-- Migration order / 遷移順序:
--   V049 (replay_experiments full 22-column promotion) → V050 (this).
--   FK: simulated_fills.experiment_id REFERENCES replay.experiments(experiment_id)
--   ON DELETE CASCADE (V049 must land first; cascade ensures stale fills get
--   cleaned when experiments are pruned by S5 quota_enforcer cron).
--
--   V049（replay_experiments 完整 22 column 升級）→ V050（本檔）。FK：
--   simulated_fills.experiment_id REFERENCES replay.experiments ON DELETE
--   CASCADE（V049 必先 land；cascade 確保 S5 quota_enforcer cron 清
--   experiment 時連帶清 fill）。
--
-- Idempotency / 幂等性:
--   local psql -f V050 ... × 2 → second run no-op (Guard A IF NOT EXISTS;
--   Guard C compares index defs before re-creating).
--
-- Guard A: enforced (table existence + 17 required columns validation).
-- Guard B: N/A (fresh CREATE, no ALTER COLUMN with type drift risk).
-- Guard C: enforced (3 hot-path indexes via pg_get_indexdef compare).
--
-- Spec source / 規格來源:
--   docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
--     §4.1 (replay.simulated_fills minimum 17 columns) +
--     §2 #2 (replay never writes to trading.fills) +
--     §6.2 forbidden writes (trading.*, learning.*) +
--     §4.1 final paragraph (no replay table read by live/demo metric code)
--   docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-03--ref20_sprint1_partition_design.md
--     §2 Track D T-D2 (this task)
-- Reservation source / 編號預留:
--   sql/migrations/REF-20_RESERVATION.md §3 row V050 (buffer → land
--   per Sprint 1 Track D T-D2 task, 2026-05-03).
-- Template source / 模板來源:
--   sql/migrations/templates/schema_guard_template.sql § Guard A + Guard C

CREATE SCHEMA IF NOT EXISTS replay;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard A: validate replay.experiments (V049 land) prerequisite present, then
-- if simulated_fills already exists, validate required columns.
--
-- Guard A：先驗 V049 前置（FK 目標表）；若 simulated_fills 已存在則驗
-- 必要欄位俱在；缺即 RAISE。
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_experiments_exists BOOLEAN;
    v_table_exists BOOLEAN;
    v_missing_cols TEXT[] := ARRAY[]::TEXT[];
    v_required_cols TEXT[] := ARRAY[
        'sim_fill_id', 'experiment_id', 'intent_id', 'decision_lease_id',
        'idempotency_key', 'ts', 'ts_ms', 'symbol', 'strategy_name',
        'side', 'qty', 'price', 'fee', 'fee_rate', 'liquidity_role',
        'evidence_source_tier', 'execution_model_version',
        'ci_low_bps', 'ci_mid_bps', 'ci_high_bps', 'payload'
    ];
    v_col TEXT;
BEGIN
    -- V049 prerequisite: replay.experiments must exist for FK target.
    -- V049 前置：replay.experiments 必須存在以為 FK 目標。
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'experiments'
    ) INTO v_experiments_exists;

    IF NOT v_experiments_exists THEN
        RAISE EXCEPTION
            'V050 Guard A: replay.experiments does not exist. V049 must run before V050 '
            '(FK: replay.simulated_fills.experiment_id REFERENCES replay.experiments).';
    END IF;

    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'replay' AND table_name = 'simulated_fills'
    ) INTO v_table_exists;

    IF v_table_exists THEN
        FOREACH v_col IN ARRAY v_required_cols LOOP
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'replay'
                  AND table_name = 'simulated_fills'
                  AND column_name = v_col
            ) THEN
                v_missing_cols := array_append(v_missing_cols, v_col);
            END IF;
        END LOOP;

        IF array_length(v_missing_cols, 1) > 0 THEN
            RAISE EXCEPTION
                'V050 Guard A: replay.simulated_fills exists but missing required columns: %',
                array_to_string(v_missing_cols, ', ');
        END IF;
        RAISE NOTICE 'V050 Guard A: replay.simulated_fills already present with all required columns; continuing to index Guard C';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- CREATE TABLE replay.simulated_fills / 建立 replay.simulated_fills
--
-- Column contract (V3 §4.1 17-column) / 欄位契約（V3 §4.1 17 column）:
--   sim_fill_id              UUID primary external id (PK).
--   experiment_id            UUID FK to replay.experiments (V049) ON DELETE CASCADE.
--   intent_id                TEXT nullable lineage id from IntentProcessor output.
--   decision_lease_id        TEXT nullable METADATA only; P2 isolated replay
--                            MUST NOT acquire leases (V3 §6.2 forbidden);
--                            in P3+ this is a metadata reference only,
--                            never a runtime acquire token.
--   idempotency_key          TEXT per simulated order/fill lifecycle key.
--   ts                       TIMESTAMPTZ simulated event time (high-level).
--   ts_ms                    BIGINT simulated event time (millisecond precision).
--   symbol                   TEXT Bybit symbol.
--   strategy_name            TEXT strategy key.
--   side                     TEXT buy/sell or long/short normalized.
--   qty                      DOUBLE PRECISION simulated qty.
--   price                    DOUBLE PRECISION simulated fill price.
--   fee                      DOUBLE PRECISION modeled fee (signed: negative=cost).
--   fee_rate                 DOUBLE PRECISION maker/taker rate used.
--   liquidity_role           TEXT enum {maker, taker, unknown} CHECK.
--   evidence_source_tier     TEXT enum {calibrated_replay, synthetic_replay,
--                            counterfactual_replay} CHECK; note that
--                            'real_outcome' is NOT allowed here (this is
--                            replay-only output).
--   execution_model_version  TEXT nullable in P2; required in P3+
--                            (P3+ writer enforces app-level NOT NULL).
--   ci_low_bps               DOUBLE PRECISION nullable per-fill confidence
--                            interval lower bound; aggregate-level CI link allowed.
--   ci_mid_bps               DOUBLE PRECISION nullable mid CI.
--   ci_high_bps              DOUBLE PRECISION nullable upper CI.
--   payload                  JSONB details (book features, regime tag, etc.).
--
-- 欄位契約與上方 EN 對應；side / liquidity_role / evidence_source_tier 三 enum
-- 由 CHECK 約束強制。
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS replay.simulated_fills (
    sim_fill_id              UUID PRIMARY KEY,
    experiment_id            UUID NOT NULL REFERENCES replay.experiments(experiment_id) ON DELETE CASCADE,
    intent_id                TEXT,
    decision_lease_id        TEXT,
    idempotency_key          TEXT NOT NULL,
    ts                       TIMESTAMPTZ NOT NULL,
    ts_ms                    BIGINT NOT NULL,
    symbol                   TEXT NOT NULL,
    strategy_name            TEXT NOT NULL,
    side                     TEXT NOT NULL,
    qty                      DOUBLE PRECISION NOT NULL,
    price                    DOUBLE PRECISION NOT NULL,
    fee                      DOUBLE PRECISION NOT NULL,
    fee_rate                 DOUBLE PRECISION NOT NULL,
    liquidity_role           TEXT NOT NULL,
    evidence_source_tier     TEXT NOT NULL,
    execution_model_version  TEXT,
    ci_low_bps               DOUBLE PRECISION,
    ci_mid_bps               DOUBLE PRECISION,
    ci_high_bps              DOUBLE PRECISION,
    payload                  JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add CHECK constraints conditionally so re-runs don't error.
-- 條件式加 CHECK 約束，重跑不報錯。
DO $$
BEGIN
    -- side enum (V3 §4.1: "buy/sell or long/short normalized")
    -- We allow both spot conventions; replay_runner P3+ writer normalizes.
    -- side enum：spot (buy/sell) 與 perp (long/short) 都接受；P3+ writer 規範化。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_simulated_fills_side'
          AND conrelid = 'replay.simulated_fills'::regclass
    ) THEN
        ALTER TABLE replay.simulated_fills
            ADD CONSTRAINT chk_replay_simulated_fills_side
            CHECK (side IN ('buy', 'sell', 'long', 'short'));
        RAISE NOTICE 'V050: added CHECK chk_replay_simulated_fills_side (4-value allowlist)';
    ELSE
        RAISE NOTICE 'V050: chk_replay_simulated_fills_side already present; skipping';
    END IF;

    -- liquidity_role enum (V3 §4.1)
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_simulated_fills_liquidity_role'
          AND conrelid = 'replay.simulated_fills'::regclass
    ) THEN
        ALTER TABLE replay.simulated_fills
            ADD CONSTRAINT chk_replay_simulated_fills_liquidity_role
            CHECK (liquidity_role IN ('maker', 'taker', 'unknown'));
        RAISE NOTICE 'V050: added CHECK chk_replay_simulated_fills_liquidity_role (3-value allowlist)';
    ELSE
        RAISE NOTICE 'V050: chk_replay_simulated_fills_liquidity_role already present; skipping';
    END IF;

    -- evidence_source_tier enum: replay-derived only (excludes 'real_outcome'
    -- which is reserved for learning.mlde_shadow_recommendations real fills).
    -- evidence_source_tier enum：replay 衍生限定（不允許 'real_outcome'，後者
    -- 保留給 learning.mlde_shadow_recommendations real fill 使用）。
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_simulated_fills_evidence_tier'
          AND conrelid = 'replay.simulated_fills'::regclass
    ) THEN
        ALTER TABLE replay.simulated_fills
            ADD CONSTRAINT chk_replay_simulated_fills_evidence_tier
            CHECK (evidence_source_tier IN ('calibrated_replay', 'synthetic_replay', 'counterfactual_replay'));
        RAISE NOTICE 'V050: added CHECK chk_replay_simulated_fills_evidence_tier (3-value replay-only allowlist)';
    ELSE
        RAISE NOTICE 'V050: chk_replay_simulated_fills_evidence_tier already present; skipping';
    END IF;

    -- qty + price + fee_rate sanity
    -- qty + price + fee_rate 合理性
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_simulated_fills_qty_price'
          AND conrelid = 'replay.simulated_fills'::regclass
    ) THEN
        ALTER TABLE replay.simulated_fills
            ADD CONSTRAINT chk_replay_simulated_fills_qty_price
            CHECK (qty > 0.0 AND price > 0.0);
        RAISE NOTICE 'V050: added CHECK chk_replay_simulated_fills_qty_price (positive)';
    ELSE
        RAISE NOTICE 'V050: chk_replay_simulated_fills_qty_price already present; skipping';
    END IF;

    -- ci ordering when all three present (low <= mid <= high)
    -- ci 順序（low <= mid <= high）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'chk_replay_simulated_fills_ci_order'
          AND conrelid = 'replay.simulated_fills'::regclass
    ) THEN
        ALTER TABLE replay.simulated_fills
            ADD CONSTRAINT chk_replay_simulated_fills_ci_order
            CHECK (
                ci_low_bps IS NULL OR ci_mid_bps IS NULL OR ci_high_bps IS NULL
                OR (ci_low_bps <= ci_mid_bps AND ci_mid_bps <= ci_high_bps)
            );
        RAISE NOTICE 'V050: added CHECK chk_replay_simulated_fills_ci_order (low<=mid<=high)';
    ELSE
        RAISE NOTICE 'V050: chk_replay_simulated_fills_ci_order already present; skipping';
    END IF;

    -- per-experiment idempotency_key uniqueness (avoid duplicate fill on retry)
    -- per-experiment idempotency_key 唯一（避免重試造重複 fill）
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'uq_replay_simulated_fills_idempotency_per_experiment'
          AND conrelid = 'replay.simulated_fills'::regclass
    ) THEN
        ALTER TABLE replay.simulated_fills
            ADD CONSTRAINT uq_replay_simulated_fills_idempotency_per_experiment
            UNIQUE (experiment_id, idempotency_key);
        RAISE NOTICE 'V050: added UNIQUE uq_replay_simulated_fills_idempotency_per_experiment (experiment + idempotency_key)';
    ELSE
        RAISE NOTICE 'V050: uq_replay_simulated_fills_idempotency_per_experiment already present; skipping';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Guard C: hot-path indexes via pg_get_indexdef compare /
-- Guard C：hot-path 索引透過 pg_get_indexdef 比對
--
--   Index 1: idx_replay_simulated_fills_experiment_ts — covers
--            "list fills for experiment ordered by ts" hot path.
--   Index 2: idx_replay_simulated_fills_symbol_strategy_ts — covers
--            "fills by symbol + strategy" aggregation queries.
--   Index 3: idx_replay_simulated_fills_intent_id — covers lineage
--            JOIN to IntentProcessor output (sparse, non-NULL only).
-- ─────────────────────────────────────────────────────────────────────────────
DO $$
DECLARE
    v_idx1_def TEXT;
    v_idx2_def TEXT;
    v_idx3_def TEXT;
    v_idx1_expected TEXT := 'CREATE INDEX idx_replay_simulated_fills_experiment_ts ON replay.simulated_fills USING btree (experiment_id, ts DESC)';
    v_idx2_expected TEXT := 'CREATE INDEX idx_replay_simulated_fills_symbol_strategy_ts ON replay.simulated_fills USING btree (symbol, strategy_name, ts DESC)';
    v_idx3_expected TEXT := 'CREATE INDEX idx_replay_simulated_fills_intent_id ON replay.simulated_fills USING btree (intent_id) WHERE (intent_id IS NOT NULL)';
BEGIN
    -- Index 1
    SELECT pg_get_indexdef(c.oid) INTO v_idx1_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_simulated_fills_experiment_ts';

    IF v_idx1_def IS NULL THEN
        CREATE INDEX idx_replay_simulated_fills_experiment_ts
            ON replay.simulated_fills (experiment_id, ts DESC);
        RAISE NOTICE 'V050 Guard C: created idx_replay_simulated_fills_experiment_ts';
    ELSIF v_idx1_def <> v_idx1_expected THEN
        RAISE EXCEPTION
            'V050 Guard C: idx_replay_simulated_fills_experiment_ts drift detected. Expected: %; Got: %',
            v_idx1_expected, v_idx1_def;
    ELSE
        RAISE NOTICE 'V050 Guard C: idx_replay_simulated_fills_experiment_ts already present and matches';
    END IF;

    -- Index 2
    SELECT pg_get_indexdef(c.oid) INTO v_idx2_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_simulated_fills_symbol_strategy_ts';

    IF v_idx2_def IS NULL THEN
        CREATE INDEX idx_replay_simulated_fills_symbol_strategy_ts
            ON replay.simulated_fills (symbol, strategy_name, ts DESC);
        RAISE NOTICE 'V050 Guard C: created idx_replay_simulated_fills_symbol_strategy_ts';
    ELSIF v_idx2_def <> v_idx2_expected THEN
        RAISE EXCEPTION
            'V050 Guard C: idx_replay_simulated_fills_symbol_strategy_ts drift detected. Expected: %; Got: %',
            v_idx2_expected, v_idx2_def;
    ELSE
        RAISE NOTICE 'V050 Guard C: idx_replay_simulated_fills_symbol_strategy_ts already present and matches';
    END IF;

    -- Index 3 (partial index: intent_id IS NOT NULL only)
    SELECT pg_get_indexdef(c.oid) INTO v_idx3_def
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'replay'
      AND c.relname = 'idx_replay_simulated_fills_intent_id';

    IF v_idx3_def IS NULL THEN
        CREATE INDEX idx_replay_simulated_fills_intent_id
            ON replay.simulated_fills (intent_id)
            WHERE intent_id IS NOT NULL;
        RAISE NOTICE 'V050 Guard C: created idx_replay_simulated_fills_intent_id (partial)';
    ELSIF v_idx3_def <> v_idx3_expected THEN
        RAISE EXCEPTION
            'V050 Guard C: idx_replay_simulated_fills_intent_id drift detected. Expected: %; Got: %',
            v_idx3_expected, v_idx3_def;
    ELSE
        RAISE NOTICE 'V050 Guard C: idx_replay_simulated_fills_intent_id already present and matches';
    END IF;
END $$;

-- ─────────────────────────────────────────────────────────────────────────────
-- Column documentation / 欄位文件
-- ─────────────────────────────────────────────────────────────────────────────
COMMENT ON TABLE replay.simulated_fills IS
'REF-20 V3 §4.1 17-column simulated-fill registry. Per-fill artifact written by P3+ replay_runner. '
'NEVER written to trading.fills (V3 §2 #2). Read only by P3+ replay routes; existing live/demo metric '
'code MUST NOT JOIN here. ON DELETE CASCADE FK to replay.experiments (V049). / '
'REF-20 V3 §4.1 17 column simulated-fill registry。每筆 fill 一列由 P3+ replay_runner 寫入。'
'絕不寫至 trading.fills（V3 §2 #2）。只由 P3+ replay routes 讀取；既有 live/demo metric 代碼禁 JOIN。'
'ON DELETE CASCADE FK 至 replay.experiments (V049)。';

COMMENT ON COLUMN replay.simulated_fills.decision_lease_id IS
'V3 §4.1: METADATA only; replay (P2 isolated profile) MUST NOT acquire leases per V3 §6.2 forbidden. '
'In P3+ this references the lease that would have been acquired in live, never an actual runtime token.';

COMMENT ON COLUMN replay.simulated_fills.evidence_source_tier IS
'V3 §4.1 + §4.2: replay-only enum (calibrated_replay / synthetic_replay / counterfactual_replay). '
'real_outcome NOT allowed here (reserved for learning.mlde_shadow_recommendations real-fill rows).';

COMMENT ON COLUMN replay.simulated_fills.execution_model_version IS
'V3 §4.1: nullable in P2; required in P3+ (writer-enforced application-level NOT NULL).';

COMMENT ON COLUMN replay.simulated_fills.ci_low_bps IS
'V3 §4.1: nullable; aggregate-level CI link allowed when per-fill CI not modeled.';

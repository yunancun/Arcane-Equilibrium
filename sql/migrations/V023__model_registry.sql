-- ============================================================
-- V023: INFRA-PREBUILD-1 Part B — learning.model_registry
-- ML model registry + canary deployment metadata (2026-04-23)
-- Created per plan INFRA-PREBUILD-1 §B1
-- ============================================================
--
-- Purpose / 用途：
--   Single source-of-truth table for ML model artifacts produced by
--   `run_training_pipeline.py` (ONNX quantile predictors per
--   strategy × engine_mode). Supersedes the "symlink + filename-stamp"
--   approach of edge_predictor_spec v1 by persisting:
--
--     * Artifact provenance (path / train_date / schema_version)
--     * Acceptance report JSON (6-metric verdict from quantile_reports.py)
--     * Canary status (shadow / promoting / production / retired / rejected)
--     * Promote timestamp (when canary_status transitioned to production)
--
--   Rust `OnnxModelManager` queries this table for the currently-canonical
--   model per (strategy, engine_mode, quantile); falls back to the filename
--   _current symlink when the row is missing (graceful degradation).
--
-- Pre-build-only / 先行預備：
--   Phase 4 design doc (docs/worklogs/2026-04-18--dual_track_exit_design.md
--   §Combine Layer + Phase 4 persistent-optimisation section) calls for a
--   canary promotion engine. This migration lands the **metadata skeleton**
--   only — there is no auto-promote job yet. Operator manually issues
--   `POST /api/v1/ml/model_promote` to transition canary_status. The
--   auto-promote logic lives in Phase 4 second-half work when real models
--   produce enough shadow observations to validate the metrics.
--
-- Distinct from / 與既有表區分：
--   * `learning.decision_features` (V017)      — entry-time training data
--   * `learning.decision_shadow_fills` (V017)  — entry-time ε-greedy paper
--   * `learning.decision_shadow_exits` (V021)  — exit-time Combine shadow
--   * `learning.model_registry`        (V023)  — this table: artifact +
--                                                 canary metadata catalog
--   * Filesystem `/tmp/openclaw/models/*.onnx` — actual ONNX blobs
--                                                (symlinked via _current)
--
-- ============================================================

-- ------------------------------------------------------------
-- Schema Guard A (retrofit 2026-04-24, V023 incident postmortem)
-- ------------------------------------------------------------
-- Historical context / 歷史脈絡：
--   V023 originally shipped without this guard. V004 had pre-seeded
--   a legacy `learning.model_registry` stub without canary_status /
--   verdict columns; `CREATE TABLE IF NOT EXISTS` below silently
--   no-op'd and the table stayed in the legacy shape — Rust reads
--   on canary_status returned nothing. Resolved manually on
--   2026-04-23; this guard is retrofitted so that any future DROP
--   + partial re-apply reveals the drift immediately instead of
--   silent-no-op-ing.
--
--   V023 原無此 guard。V004 預留了缺少 canary_status / verdict 的
--   legacy stub，下方 CREATE TABLE IF NOT EXISTS 靜默跳過，導致
--   Rust 讀 canary_status 空。2026-04-23 手動修好；此 guard 回補
--   避免未來 DROP + 不完整 re-apply 再次 silent no-op。
--
-- Template source / 模板來源：
--   sql/migrations/templates/schema_guard_template.sql § Guard A
-- ------------------------------------------------------------
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name   = 'model_registry'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'strategy', 'engine_mode', 'quantile',
            'schema_version', 'train_date',
            'artifact_path', 'verdict',
            'canary_status', 'promoted_at',
            'created_at', 'updated_at'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'model_registry'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: learning.model_registry exists but missing required columns: %. '
                'This likely means a legacy V004-era stub is present. '
                'Resolve by dropping/repairing the legacy table before re-applying V023. '
                'See sql/migrations/templates/schema_guard_template.sql for details.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.model_registry (
    id                       BIGSERIAL     PRIMARY KEY,
    -- Identity (unique per row) / 身份（每列唯一）
    strategy                 TEXT          NOT NULL,
    engine_mode              TEXT          NOT NULL
        CHECK (engine_mode IN ('paper', 'demo', 'live', 'live_demo')),
    quantile                 TEXT          NOT NULL
        CHECK (quantile IN ('q10', 'q50', 'q90')),
    schema_version           TEXT          NOT NULL,      -- e.g. 'v1'
    train_date               DATE          NOT NULL,      -- when training ran

    -- Artifact / 產物
    artifact_path            TEXT          NOT NULL,      -- absolute or relative to OPENCLAW_DATA_DIR
    artifact_size_bytes      BIGINT,                      -- filled on register
    artifact_sha256          TEXT,                        -- optional integrity check

    -- Training report / 訓練報告
    acceptance_report        JSONB,                       -- full acceptance_report.json payload
    verdict                  TEXT          NOT NULL
        CHECK (verdict IN ('should_ship', 'shadow_only', 'no_ship')),

    -- Provenance / 來源可追溯
    feature_schema_hash      TEXT,                        -- aligns with decision_features.feature_schema_hash
    training_config_hash     TEXT,                        -- LightGBM / CQR hyperparams hash
    training_sample_size     INTEGER,                     -- n_train at training time

    -- Canary deployment metadata / 灰度部署元數據
    canary_status            TEXT          NOT NULL DEFAULT 'shadow'
        CHECK (canary_status IN ('shadow', 'promoting', 'production', 'retired', 'rejected')),
    promoted_at              TIMESTAMPTZ,                 -- ts when → 'production' (NULL until promote)
    retired_at               TIMESTAMPTZ,                 -- ts when → 'retired' or 'rejected'
    retirement_reason        TEXT,                        -- Brier drift / feature drift / superseded / etc.

    -- Audit / 審計
    created_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    created_by               TEXT          NOT NULL DEFAULT 'run_training_pipeline',  -- writer tag
    updated_at               TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

-- Unique key prevents re-registering the same training run twice.
-- 唯一鍵防止重複登記同一訓練。
CREATE UNIQUE INDEX IF NOT EXISTS uq_model_registry_identity
    ON learning.model_registry
    (strategy, engine_mode, quantile, schema_version, train_date);

-- Hot-path queries: "which production model for this slot?" — aim for index-only
-- scan. `canary_status, promoted_at DESC` selects the latest promoted model.
-- Rust `OnnxModelManager` hits this index every time a new close fires and a
-- shadow predict is needed.
-- 熱查詢：「這個 slot 當前的 production model 是哪個？」目標 index-only scan。
-- 用 canary_status + promoted_at DESC 取最新晉升的 model。
CREATE INDEX IF NOT EXISTS idx_model_registry_production_latest
    ON learning.model_registry
    (strategy, engine_mode, quantile, canary_status, promoted_at DESC)
    WHERE canary_status IN ('production', 'promoting');

-- Operator queries: "what's in shadow right now?" / "what got retired?"
-- Operator 查詢：目前哪些在 shadow、哪些被退役？
CREATE INDEX IF NOT EXISTS idx_model_registry_canary_status_created
    ON learning.model_registry
    (canary_status, created_at DESC);

-- Freshness check (healthcheck [9]): "latest production train_date per slot".
-- 新鮮度檢查（healthcheck [9]）：每 slot 最新 production model 的 train_date。
CREATE INDEX IF NOT EXISTS idx_model_registry_train_date
    ON learning.model_registry
    (strategy, engine_mode, train_date DESC);

-- Auto-update `updated_at` on any UPDATE (canary_status transitions especially).
-- UPDATE 時自動刷新 `updated_at`（canary_status 變化時尤其重要）。
CREATE OR REPLACE FUNCTION learning.model_registry_touch_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_model_registry_touch ON learning.model_registry;
CREATE TRIGGER trg_model_registry_touch
    BEFORE UPDATE ON learning.model_registry
    FOR EACH ROW EXECUTE FUNCTION learning.model_registry_touch_updated_at();

COMMENT ON TABLE learning.model_registry IS
    'INFRA-PREBUILD-1 Part B (2026-04-23): ML model artifact + canary '
    'deployment metadata catalog. One row per training run per '
    '(strategy, engine_mode, quantile, schema_version, train_date). '
    'Rust OnnxModelManager reads latest (promoting|production) row; '
    'falls back to filename _current symlink when empty.';

COMMENT ON COLUMN learning.model_registry.canary_status IS
    'State machine: shadow → promoting → production → retired (rejected is '
    'terminal too). Operator transitions via POST /api/v1/ml/model_promote. '
    'Auto-promote logic deferred to Phase 4 second-half per docs/references/'
    '2026-04-23--model_canary_promotion_rules_draft.md.';

COMMENT ON COLUMN learning.model_registry.verdict IS
    'From quantile_reports.py::verdict(): should_ship (n≥500 + 6 metrics pass), '
    'shadow_only (n 200–499 or partial pass), no_ship (n<200 or train fail). '
    'ONNX export only happens when verdict != no_ship; registry row only '
    'inserted for successfully-exported models.';

COMMENT ON COLUMN learning.model_registry.acceptance_report IS
    'Full JSON payload from quantile_reports.py — pinball_skill, coverage_error, '
    'decile_lift_ci, crossing_rate, lgbm_vs_linear_qr, train_serve_skew, '
    'n_train, n_val, n_test + verdict. Operator reads this when deciding '
    'to promote shadow → promoting.';

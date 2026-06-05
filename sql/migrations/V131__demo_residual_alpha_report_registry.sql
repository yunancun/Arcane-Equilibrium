-- ============================================================
-- V131: learning.demo_residual_alpha_reports
--       Demo residual alpha report durable registry
--
-- 目的：
--   P0-C/P1-C 已要求 live candidate payload 帶 canonical
--   demo_residual_alpha_report，且 replay registry manifest 承諾
--   demo_residual_alpha_report_hash。但目前 report body 只在 payload/manifest
--   路徑中流動，DB 不能由 hash 反查完整 report，source contract 也無法證明
--   「manifest hash」對應的是一份 durable、可恢復、可審計的 report body。
--
-- 本 migration 補上最小 durable registry：
--   1. learning.demo_residual_alpha_reports：完整 report body + canonical hash
--      + 主要指標 + 來源，按 (strategy, mode, hash) 去重。
--   2. learning.promotion_pipeline.demo_residual_alpha_report_hash：latest
--      promotion evidence 狀態只存 hash，不把大 JSONB 塞回 pipeline row。
--
-- 硬邊界：
--   - additive only；不改 stage，不放寬 live/demo gate，不寫 order/lease/auth。
--   - registry row 只表示 evidence body 可恢復；是否 promotion-ready 仍由
--     validator / replay registry / hidden OOS / source contract 決定。
--   - 不設 retention；report 是審計證據，不能因時間自動清掉。
--
-- Guard：
--   Guard A：既有表 shape 缺必要欄 → RAISE，避免漂移表被誤當完整。
--   Guard B：type-sensitive 欄位反射；promotion hash column 必為 text。
--   Guard C：確認 unique/index 存在，避免 source JOIN 變成多 row 或慢查。
-- ============================================================

BEGIN;

-- Guard B：若 promotion_pipeline 已有同名欄，必須是 text。
DO $$
DECLARE
    v_type TEXT;
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'promotion_pipeline'
          AND column_name = 'demo_residual_alpha_report_hash'
    ) THEN
        SELECT data_type INTO v_type
        FROM information_schema.columns
        WHERE table_schema = 'learning'
          AND table_name = 'promotion_pipeline'
          AND column_name = 'demo_residual_alpha_report_hash';

        IF v_type <> 'text' THEN
            RAISE EXCEPTION
                'V131 Guard B FAIL: learning.promotion_pipeline.demo_residual_alpha_report_hash type is %, expected text.',
                v_type;
        END IF;
    END IF;
END $$;

ALTER TABLE IF EXISTS learning.promotion_pipeline
    ADD COLUMN IF NOT EXISTS demo_residual_alpha_report_hash TEXT;

COMMENT ON COLUMN learning.promotion_pipeline.demo_residual_alpha_report_hash IS
    'Latest canonical SHA-256 hex hash of the Demo residual alpha report persisted in learning.demo_residual_alpha_reports.';

-- Guard A：既有 registry 表必須有完整欄位；缺欄代表 drift，不能靜默套用。
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'learning'
          AND table_name = 'demo_residual_alpha_reports'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'report_id',
            'first_seen_ts',
            'last_seen_ts',
            'strategy_name',
            'engine_mode',
            'report_hash',
            'report_jsonb',
            'raw_mean_bps',
            'residual_mean_bps',
            'r_beta_retention',
            'beta_edge_share',
            'psr_raw',
            'psr_residual',
            'dsr_raw',
            'dsr_residual',
            'pbo_raw',
            'pbo_residual',
            'factor_panel_hash',
            'fit_window',
            'coverage',
            'source',
            'promotion_pipeline_id',
            'created_by',
            'evidence'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name = 'demo_residual_alpha_reports'
              AND column_name = c
        );

        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'V131 Guard A FAIL: learning.demo_residual_alpha_reports exists but missing required columns: %.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.demo_residual_alpha_reports (
    report_id             BIGSERIAL   PRIMARY KEY,
    first_seen_ts         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen_ts          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    strategy_name         TEXT        NOT NULL,
    engine_mode           TEXT        NOT NULL,
    report_hash           TEXT        NOT NULL,
    report_jsonb          JSONB       NOT NULL,

    raw_mean_bps          DOUBLE PRECISION NOT NULL,
    residual_mean_bps     DOUBLE PRECISION NOT NULL,
    r_beta_retention      DOUBLE PRECISION NOT NULL,
    beta_edge_share       DOUBLE PRECISION NOT NULL,
    psr_raw               DOUBLE PRECISION NOT NULL,
    psr_residual          DOUBLE PRECISION NOT NULL,
    dsr_raw               DOUBLE PRECISION NOT NULL,
    dsr_residual          DOUBLE PRECISION NOT NULL,
    pbo_raw               DOUBLE PRECISION NOT NULL,
    pbo_residual          DOUBLE PRECISION NOT NULL,

    factor_panel_hash     TEXT        NOT NULL,
    fit_window            JSONB       NOT NULL DEFAULT '{}'::jsonb,
    coverage              JSONB       NOT NULL DEFAULT '{}'::jsonb,
    source                TEXT        NOT NULL DEFAULT 'edge_estimator_scheduler',
    promotion_pipeline_id INTEGER,
    created_by            TEXT        NOT NULL DEFAULT 'promotion_evidence',
    evidence              JSONB       NOT NULL DEFAULT '{}'::jsonb,

    CONSTRAINT demo_residual_alpha_reports_engine_mode_chk
        CHECK (engine_mode IN ('paper', 'demo', 'live_demo', 'live')),
    CONSTRAINT demo_residual_alpha_reports_report_hash_chk
        CHECK (report_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT demo_residual_alpha_reports_report_jsonb_object_chk
        CHECK (jsonb_typeof(report_jsonb) = 'object'),
    CONSTRAINT demo_residual_alpha_reports_factor_panel_hash_chk
        CHECK (length(btrim(factor_panel_hash)) > 0),
    CONSTRAINT demo_residual_alpha_reports_finite_metrics_chk
        CHECK (
            raw_mean_bps = raw_mean_bps
            AND raw_mean_bps > '-Infinity'::DOUBLE PRECISION
            AND raw_mean_bps < 'Infinity'::DOUBLE PRECISION
            AND residual_mean_bps = residual_mean_bps
            AND residual_mean_bps > '-Infinity'::DOUBLE PRECISION
            AND residual_mean_bps < 'Infinity'::DOUBLE PRECISION
            AND r_beta_retention = r_beta_retention
            AND r_beta_retention > '-Infinity'::DOUBLE PRECISION
            AND r_beta_retention < 'Infinity'::DOUBLE PRECISION
            AND beta_edge_share = beta_edge_share
            AND beta_edge_share > '-Infinity'::DOUBLE PRECISION
            AND beta_edge_share < 'Infinity'::DOUBLE PRECISION
            AND psr_raw = psr_raw
            AND psr_raw > '-Infinity'::DOUBLE PRECISION
            AND psr_raw < 'Infinity'::DOUBLE PRECISION
            AND psr_residual = psr_residual
            AND psr_residual > '-Infinity'::DOUBLE PRECISION
            AND psr_residual < 'Infinity'::DOUBLE PRECISION
            AND dsr_raw = dsr_raw
            AND dsr_raw > '-Infinity'::DOUBLE PRECISION
            AND dsr_raw < 'Infinity'::DOUBLE PRECISION
            AND dsr_residual = dsr_residual
            AND dsr_residual > '-Infinity'::DOUBLE PRECISION
            AND dsr_residual < 'Infinity'::DOUBLE PRECISION
            AND pbo_raw = pbo_raw
            AND pbo_raw > '-Infinity'::DOUBLE PRECISION
            AND pbo_raw < 'Infinity'::DOUBLE PRECISION
            AND pbo_residual = pbo_residual
            AND pbo_residual > '-Infinity'::DOUBLE PRECISION
            AND pbo_residual < 'Infinity'::DOUBLE PRECISION
        ),
    CONSTRAINT demo_residual_alpha_reports_unique_hash_per_strategy
        UNIQUE (strategy_name, engine_mode, report_hash)
);

CREATE INDEX IF NOT EXISTS idx_demo_residual_alpha_reports_hash
    ON learning.demo_residual_alpha_reports (report_hash);

CREATE INDEX IF NOT EXISTS idx_demo_residual_alpha_reports_strategy_mode_seen
    ON learning.demo_residual_alpha_reports
    (strategy_name, engine_mode, last_seen_ts DESC);

CREATE INDEX IF NOT EXISTS idx_demo_residual_alpha_reports_factor_panel_hash
    ON learning.demo_residual_alpha_reports (factor_panel_hash);

COMMENT ON TABLE learning.demo_residual_alpha_reports IS
    'Durable registry of canonical Demo residual alpha reports. Hash/body audit table only; does not authorize promotion by itself.';

COMMENT ON COLUMN learning.demo_residual_alpha_reports.report_hash IS
    'Canonical SHA-256 hex over report_jsonb using sorted keys and compact separators.';

COMMENT ON COLUMN learning.demo_residual_alpha_reports.report_jsonb IS
    'Full canonical demo_residual_alpha_report body after validator acceptance.';

-- Guard B：核心欄位型別反射。
DO $$
DECLARE
    v_bad TEXT[];
BEGIN
    SELECT array_agg(column_name || ':' || data_type) INTO v_bad
    FROM information_schema.columns
    WHERE table_schema = 'learning'
      AND table_name = 'demo_residual_alpha_reports'
      AND (
        (column_name = 'report_hash' AND data_type <> 'text')
        OR (column_name = 'report_jsonb' AND data_type <> 'jsonb')
        OR (column_name = 'raw_mean_bps' AND data_type <> 'double precision')
        OR (column_name = 'residual_mean_bps' AND data_type <> 'double precision')
        OR (column_name = 'r_beta_retention' AND data_type <> 'double precision')
        OR (column_name = 'beta_edge_share' AND data_type <> 'double precision')
        OR (column_name = 'psr_raw' AND data_type <> 'double precision')
        OR (column_name = 'psr_residual' AND data_type <> 'double precision')
        OR (column_name = 'dsr_raw' AND data_type <> 'double precision')
        OR (column_name = 'dsr_residual' AND data_type <> 'double precision')
        OR (column_name = 'pbo_raw' AND data_type <> 'double precision')
        OR (column_name = 'pbo_residual' AND data_type <> 'double precision')
        OR (column_name = 'fit_window' AND data_type <> 'jsonb')
        OR (column_name = 'coverage' AND data_type <> 'jsonb')
      );

    IF v_bad IS NOT NULL AND array_length(v_bad, 1) > 0 THEN
        RAISE EXCEPTION
            'V131 Guard B FAIL: learning.demo_residual_alpha_reports type drift: %.',
            v_bad;
    END IF;
END $$;

-- Guard C：source contract JOIN 依賴 unique/hash/index。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'demo_residual_alpha_reports_unique_hash_per_strategy'
          AND conrelid = 'learning.demo_residual_alpha_reports'::regclass
    ) THEN
        RAISE EXCEPTION
            'V131 Guard C FAIL: unique(strategy_name, engine_mode, report_hash) missing.';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE schemaname = 'learning'
          AND tablename = 'demo_residual_alpha_reports'
          AND indexname = 'idx_demo_residual_alpha_reports_hash'
    ) THEN
        RAISE EXCEPTION
            'V131 Guard C FAIL: idx_demo_residual_alpha_reports_hash missing.';
    END IF;
END $$;

COMMIT;

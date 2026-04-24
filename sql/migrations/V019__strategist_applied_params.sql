-- V019: STRATEGIST-PARAMS-PERSIST-1 (2026-04-23)
-- Persist Strategist-tuned params so engine restart restores them instead of
-- reverting to TOML baseline. Enables STRATEGIST-AUTO-PROMOTE-CRITERIA-1
-- stability counter to survive rebuilds.
-- 持久化 Strategist 調諧參數，engine restart 恢復而非 TOML baseline，
-- 支援 AUTO-PROMOTE 穩定計數器跨 rebuild。

CREATE SCHEMA IF NOT EXISTS learning;

-- ------------------------------------------------------------
-- Schema Guard A (retrofit 2026-04-24, V023 postmortem · G6-03 Wave 1)
-- ------------------------------------------------------------
-- Historical context / 歷史脈絡：
--   V019 originally shipped without this guard. If a legacy stub of
--   `learning.strategist_applied_params` had been pre-seeded (e.g. by a
--   prior aborted attempt or hot-fix patch), the `CREATE TABLE IF NOT
--   EXISTS` below would silently no-op and downstream restore reads on
--   missing columns (params_json / applied_at_ms / source) would fail
--   in confusing ways. This guard RAISEs immediately when drift is
--   detected, mirroring the V023 model_registry retrofit.
--
--   V019 原無此 guard。若 `learning.strategist_applied_params` 已有
--   legacy stub（前次中止嘗試或 hot-fix），下方 CREATE TABLE IF NOT
--   EXISTS 會靜默跳過，下游 restore 讀缺欄位時報難解錯。此 guard 主動
--   RAISE，呼應 V023 model_registry 的 retrofit。
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
          AND table_name   = 'strategist_applied_params'
    ) THEN
        SELECT array_agg(c) INTO v_missing
        FROM unnest(ARRAY[
            'id', 'engine_mode', 'strategy_name',
            'params_json', 'applied_at', 'applied_at_ms',
            'source', 'reason', 'prev_params_json'
        ]) AS c
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'learning'
              AND table_name   = 'strategist_applied_params'
              AND column_name  = c
        );
        IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
            RAISE EXCEPTION
                'schema_guard A: learning.strategist_applied_params exists but missing required columns: %. '
                'A previous migration or hot-fix likely pre-created this table with a different shape. '
                'Resolve legacy schema (DROP + re-apply V019, or ALTER ADD missing columns) before continuing. '
                'See sql/migrations/templates/schema_guard_template.sql for details.',
                v_missing;
        END IF;
    END IF;
END $$;

CREATE TABLE IF NOT EXISTS learning.strategist_applied_params (
    id              BIGSERIAL PRIMARY KEY,
    engine_mode     TEXT NOT NULL,           -- 'demo' / 'live' / 'paper'
    strategy_name   TEXT NOT NULL,
    params_json     JSONB NOT NULL,
    applied_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    applied_at_ms   BIGINT NOT NULL,         -- client ts_ms for ordering
    source          TEXT NOT NULL DEFAULT 'strategist_scheduler',  -- 'strategist_scheduler' / 'manual_promote' / 'operator_override'
    reason          TEXT,                    -- optional: 'top_deviation_pair' / 'promote_from_demo' / etc
    prev_params_json JSONB                   -- snapshot of params before this apply (audit trail)
);

CREATE INDEX IF NOT EXISTS idx_strategist_applied_engine_strategy_ts
    ON learning.strategist_applied_params (engine_mode, strategy_name, applied_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_strategist_applied_ts
    ON learning.strategist_applied_params (applied_at_ms DESC);

COMMENT ON TABLE learning.strategist_applied_params IS
    'STRATEGIST-PARAMS-PERSIST-1: audit trail + restore source for Strategist-tuned params. '
    'Latest row per (engine_mode, strategy_name) restored at engine startup.';

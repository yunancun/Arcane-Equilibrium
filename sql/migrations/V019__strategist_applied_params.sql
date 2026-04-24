-- V019: STRATEGIST-PARAMS-PERSIST-1 (2026-04-23)
-- Persist Strategist-tuned params so engine restart restores them instead of
-- reverting to TOML baseline. Enables STRATEGIST-AUTO-PROMOTE-CRITERIA-1
-- stability counter to survive rebuilds.
-- 持久化 Strategist 調諧參數，engine restart 恢復而非 TOML baseline，
-- 支援 AUTO-PROMOTE 穩定計數器跨 rebuild。

CREATE SCHEMA IF NOT EXISTS learning;

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

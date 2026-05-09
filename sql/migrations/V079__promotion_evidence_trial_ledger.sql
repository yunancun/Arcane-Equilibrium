-- V079: Promotion evidence reports + strategy trial ledger
--
-- P0-V2-NEW-3 closes the source-side DSR/PBO evidence push gap. The hourly
-- edge-estimator cycle can now persist:
--   1) latest selection-bias/tail-risk reports on learning.promotion_pipeline
--   2) per-cycle candidate trial Sharpes in learning.strategy_trial_ledger
--
-- This migration is additive only. It does not promote stages, mutate live auth,
-- or grant order authority.

ALTER TABLE IF EXISTS learning.promotion_pipeline
    ADD COLUMN IF NOT EXISTS demo_selection_bias_report JSONB,
    ADD COLUMN IF NOT EXISTS demo_tail_risk_report JSONB;

COMMENT ON COLUMN learning.promotion_pipeline.demo_selection_bias_report IS
    'Latest Demo DSR/PBO/CSCV promotion evidence report, written by the promotion evidence producer.';

COMMENT ON COLUMN learning.promotion_pipeline.demo_tail_risk_report IS
    'Latest Demo portfolio VaR/CVaR/EVT/stress promotion evidence report, written by the promotion evidence producer.';

CREATE TABLE IF NOT EXISTS learning.strategy_trial_ledger (
    trial_id        BIGSERIAL   PRIMARY KEY,
    ts              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    strategy_name   TEXT        NOT NULL,
    engine_mode     TEXT        NOT NULL,
    trial_family    TEXT        NOT NULL DEFAULT 'edge_estimator_cycle',
    candidate_key   TEXT        NOT NULL,
    observed_sharpe DOUBLE PRECISION NOT NULL,
    n_observations  INTEGER     NOT NULL,
    mean_return     DOUBLE PRECISION,
    source          TEXT        NOT NULL DEFAULT 'edge_estimator_scheduler',
    evidence        JSONB       NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT strategy_trial_ledger_engine_mode_chk
        CHECK (engine_mode IN ('paper', 'demo', 'live_demo', 'live')),
    CONSTRAINT strategy_trial_ledger_n_observations_chk
        CHECK (n_observations >= 0),
    CONSTRAINT strategy_trial_ledger_observed_sharpe_finite_chk
        CHECK (
            observed_sharpe = observed_sharpe
            AND observed_sharpe > '-Infinity'::DOUBLE PRECISION
            AND observed_sharpe < 'Infinity'::DOUBLE PRECISION
        ),
    CONSTRAINT strategy_trial_ledger_mean_return_finite_chk
        CHECK (
            mean_return IS NULL
            OR (
                mean_return = mean_return
                AND mean_return > '-Infinity'::DOUBLE PRECISION
                AND mean_return < 'Infinity'::DOUBLE PRECISION
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_strategy_trial_ledger_strategy_mode_ts
    ON learning.strategy_trial_ledger (strategy_name, engine_mode, ts DESC);

CREATE INDEX IF NOT EXISTS idx_strategy_trial_ledger_family_ts
    ON learning.strategy_trial_ledger (trial_family, ts DESC);

COMMENT ON TABLE learning.strategy_trial_ledger IS
    'Persistent K/trial_sharpes source for DSR/PBO promotion evidence. Additive audit table; does not authorize promotion by itself.';

COMMENT ON COLUMN learning.strategy_trial_ledger.candidate_key IS
    'Candidate identifier for one trial in a strategy family, usually the symbol/cell from an edge-estimator cycle.';

COMMENT ON COLUMN learning.strategy_trial_ledger.observed_sharpe IS
    'Sharpe computed from the real candidate return series and reused as persisted trial_sharpes evidence.';

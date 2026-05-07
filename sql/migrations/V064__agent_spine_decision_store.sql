-- ============================================================
-- V064: Agent Decision Spine durable store
-- MAG-032: signal -> decision -> verdict -> plan lineage tables
--
-- Purpose:
--   Persist typed Agent Spine objects without changing live trading authority.
--   The store is append/idempotent-first: objects are keyed by object_id and
--   object_type/idempotency_key, while edges give operators a direct lineage
--   query from strategy signal to StrategistDecision, GuardianVerdict, and
--   ExecutionPlan.
--
-- 目的：
--   持久化 typed Agent Spine 物件，但不改 live trading 權限。store 以 append /
--   idempotent 為先：物件由 object_id 及 object_type/idempotency_key 去重，
--   edge 讓 operator 可直接查 signal -> decision -> verdict -> plan lineage。
-- ============================================================

CREATE SCHEMA IF NOT EXISTS agent;

-- ============================================================
-- agent.decision_objects
-- Durable typed object envelope for StrategySignal, StrategistDecision,
-- GuardianVerdict, ExecutionPlan, ExecutionReport.
-- ============================================================
CREATE TABLE IF NOT EXISTS agent.decision_objects (
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    object_id           TEXT        NOT NULL,
    object_type         TEXT        NOT NULL,
    object_version      TEXT        NOT NULL,
    engine_mode         TEXT        NOT NULL,
    symbol              TEXT        NOT NULL,
    strategy            TEXT,
    signal_id           TEXT,
    decision_id         TEXT,
    verdict_id          TEXT,
    verdict_version     INTEGER,
    order_plan_id       TEXT,
    execution_report_id TEXT,
    lease_id            TEXT,
    state               TEXT        NOT NULL,
    source_agent        TEXT        NOT NULL,
    authority_mode      TEXT        NOT NULL,
    idempotency_key     TEXT        NOT NULL,
    payload_hash        TEXT        NOT NULL,
    payload             JSONB       NOT NULL,
    PRIMARY KEY (object_id),
    CONSTRAINT chk_agent_decision_objects_object_type CHECK (
        object_type IN (
            'strategy_signal',
            'strategist_decision',
            'guardian_verdict',
            'execution_plan',
            'execution_report',
            'analyst_insight'
        )
    ),
    CONSTRAINT chk_agent_decision_objects_authority_mode CHECK (
        authority_mode IN ('disabled', 'shadow', 'canary', 'primary')
    ),
    CONSTRAINT chk_agent_decision_objects_state_nonempty CHECK (length(state) > 0),
    CONSTRAINT chk_agent_decision_objects_engine_mode_nonempty CHECK (length(engine_mode) > 0),
    CONSTRAINT chk_agent_decision_objects_payload_hash_sha256 CHECK (
        payload_hash ~ '^sha256:[0-9a-f]{64}$'
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_decision_objects_type_idempotency
    ON agent.decision_objects (object_type, idempotency_key);

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_decision_objects_strategy_signal
    ON agent.decision_objects (signal_id)
    WHERE object_type = 'strategy_signal' AND signal_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_decision_objects_strategist_decision
    ON agent.decision_objects (decision_id)
    WHERE object_type = 'strategist_decision' AND decision_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_decision_objects_guardian_verdict
    ON agent.decision_objects (decision_id, verdict_version)
    WHERE object_type = 'guardian_verdict'
      AND decision_id IS NOT NULL
      AND verdict_version IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_decision_objects_execution_plan
    ON agent.decision_objects (order_plan_id)
    WHERE object_type = 'execution_plan' AND order_plan_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_decision_objects_execution_report
    ON agent.decision_objects (execution_report_id)
    WHERE object_type = 'execution_report' AND execution_report_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_agent_decision_objects_decision_id
    ON agent.decision_objects (decision_id);

CREATE INDEX IF NOT EXISTS idx_agent_decision_objects_order_plan_id
    ON agent.decision_objects (order_plan_id);

CREATE INDEX IF NOT EXISTS idx_agent_decision_objects_signal_id
    ON agent.decision_objects (signal_id);

CREATE INDEX IF NOT EXISTS idx_agent_decision_objects_created_at
    ON agent.decision_objects (created_at DESC);

-- ============================================================
-- agent.decision_edges
-- Directed links between objects. Logical FK only: ingestion may be
-- out-of-order during shadow rollout, so runtime writer stays fail-soft.
-- ============================================================
CREATE TABLE IF NOT EXISTS agent.decision_edges (
    edge_id        TEXT        NOT NULL,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    from_object_id TEXT        NOT NULL,
    to_object_id   TEXT        NOT NULL,
    edge_type      TEXT        NOT NULL,
    engine_mode    TEXT        NOT NULL,
    decision_id    TEXT,
    payload_hash   TEXT,
    details        JSONB       NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (edge_id),
    CONSTRAINT uq_agent_decision_edges_triple UNIQUE (from_object_id, to_object_id, edge_type),
    CONSTRAINT chk_agent_decision_edges_edge_type CHECK (
        edge_type IN (
            'evidence_for',
            'signal_for',
            'reviewed_by',
            'modified_by',
            'planned_by',
            'leased_by',
            'executed_by',
            'analyzed_by',
            'protective_bypass_for'
        )
    ),
    CONSTRAINT chk_agent_decision_edges_engine_mode_nonempty CHECK (length(engine_mode) > 0),
    CONSTRAINT chk_agent_decision_edges_payload_hash_sha256 CHECK (
        payload_hash IS NULL OR payload_hash ~ '^sha256:[0-9a-f]{64}$'
    )
);

CREATE INDEX IF NOT EXISTS idx_agent_decision_edges_from
    ON agent.decision_edges (from_object_id, edge_type);

CREATE INDEX IF NOT EXISTS idx_agent_decision_edges_to
    ON agent.decision_edges (to_object_id, edge_type);

CREATE INDEX IF NOT EXISTS idx_agent_decision_edges_decision_id
    ON agent.decision_edges (decision_id);

-- ============================================================
-- agent.decision_state_changes
-- Append-only state transition log. Hypertable when TimescaleDB is present.
-- ============================================================
CREATE TABLE IF NOT EXISTS agent.decision_state_changes (
    ts            TIMESTAMPTZ NOT NULL,
    transition_id TEXT        NOT NULL,
    object_id     TEXT        NOT NULL,
    object_type   TEXT        NOT NULL,
    from_state    TEXT,
    to_state      TEXT        NOT NULL,
    engine_mode   TEXT        NOT NULL,
    trigger       TEXT        NOT NULL,
    details       JSONB       NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (transition_id, ts),
    CONSTRAINT chk_agent_decision_state_changes_object_type CHECK (
        object_type IN (
            'strategy_signal',
            'strategist_decision',
            'guardian_verdict',
            'execution_plan',
            'execution_report',
            'analyst_insight'
        )
    ),
    CONSTRAINT chk_agent_decision_state_changes_to_state_nonempty CHECK (length(to_state) > 0),
    CONSTRAINT chk_agent_decision_state_changes_engine_mode_nonempty CHECK (length(engine_mode) > 0)
);

DO $$ BEGIN
IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
    PERFORM create_hypertable('agent.decision_state_changes', 'ts',
        chunk_time_interval => INTERVAL '7 days',
        if_not_exists => TRUE);
END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_agent_decision_state_changes_object_ts
    ON agent.decision_state_changes (object_id, ts DESC);

CREATE INDEX IF NOT EXISTS idx_agent_decision_state_changes_type_ts
    ON agent.decision_state_changes (object_type, ts DESC);

-- ============================================================
-- agent.execution_idempotency_keys
-- Executor duplicate-submit guard. The runtime authority flip is later; V064
-- only creates the durable reservation surface.
-- ============================================================
CREATE TABLE IF NOT EXISTS agent.execution_idempotency_keys (
    idempotency_key TEXT        NOT NULL,
    order_plan_id   TEXT        NOT NULL,
    decision_id     TEXT        NOT NULL,
    engine_mode     TEXT        NOT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status          TEXT        NOT NULL DEFAULT 'reserved',
    details         JSONB       NOT NULL DEFAULT '{}'::JSONB,
    PRIMARY KEY (idempotency_key),
    CONSTRAINT uq_agent_execution_keys_plan_mode UNIQUE (order_plan_id, engine_mode),
    CONSTRAINT uq_agent_execution_keys_decision_plan_mode UNIQUE (decision_id, order_plan_id, engine_mode),
    CONSTRAINT chk_agent_execution_keys_status CHECK (
        status IN ('reserved', 'submitted', 'accepted', 'rejected', 'failed', 'expired')
    ),
    CONSTRAINT chk_agent_execution_keys_engine_mode_nonempty CHECK (length(engine_mode) > 0)
);

CREATE INDEX IF NOT EXISTS idx_agent_execution_keys_decision_id
    ON agent.execution_idempotency_keys (decision_id);

CREATE INDEX IF NOT EXISTS idx_agent_execution_keys_first_seen
    ON agent.execution_idempotency_keys (first_seen_at DESC);

COMMENT ON TABLE agent.decision_objects IS
    'Agent Decision Spine typed object envelopes. MAG-032 durable lineage store.';
COMMENT ON TABLE agent.decision_edges IS
    'Agent Decision Spine object lineage edges. Query signal -> decision -> verdict -> plan through this table.';
COMMENT ON TABLE agent.decision_state_changes IS
    'Agent Decision Spine append-only object state transitions.';
COMMENT ON TABLE agent.execution_idempotency_keys IS
    'Agent Decision Spine execution idempotency reservations.';

-- Reference chain query / lineage 查詢範例:
-- SELECT sig.object_id AS signal_object_id,
--        dec.decision_id,
--        verdict.verdict_id,
--        plan.order_plan_id
-- FROM agent.decision_objects sig
-- JOIN agent.decision_edges sig_edge
--   ON sig_edge.from_object_id = sig.object_id
--  AND sig_edge.edge_type = 'signal_for'
-- JOIN agent.decision_objects dec
--   ON dec.object_id = sig_edge.to_object_id
-- JOIN agent.decision_edges verdict_edge
--   ON verdict_edge.from_object_id = dec.object_id
--  AND verdict_edge.edge_type = 'reviewed_by'
-- JOIN agent.decision_objects verdict
--   ON verdict.object_id = verdict_edge.to_object_id
-- JOIN agent.decision_edges plan_edge
--   ON plan_edge.from_object_id = verdict.object_id
--  AND plan_edge.edge_type = 'planned_by'
-- JOIN agent.decision_objects plan
--   ON plan.object_id = plan_edge.to_object_id
-- WHERE sig.object_type = 'strategy_signal';

-- Guard A: post-create shape verification. This catches partial deploys or
-- accidental edits before the writer ever relies on the store.
DO $$
DECLARE
    v_missing TEXT[];
BEGIN
    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'created_at','object_id','object_type','object_version','engine_mode',
        'symbol','strategy','signal_id','decision_id','verdict_id',
        'verdict_version','order_plan_id','execution_report_id','lease_id',
        'state','source_agent','authority_mode','idempotency_key',
        'payload_hash','payload'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'agent'
          AND table_name = 'decision_objects'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION 'V064 Guard A FAIL: agent.decision_objects missing columns: %', v_missing;
    END IF;

    SELECT array_agg(c) INTO v_missing
    FROM unnest(ARRAY[
        'edge_id','created_at','from_object_id','to_object_id','edge_type',
        'engine_mode','decision_id','payload_hash','details'
    ]) AS c
    WHERE NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'agent'
          AND table_name = 'decision_edges'
          AND column_name = c
    );

    IF v_missing IS NOT NULL AND array_length(v_missing, 1) > 0 THEN
        RAISE EXCEPTION 'V064 Guard A FAIL: agent.decision_edges missing columns: %', v_missing;
    END IF;

    RAISE NOTICE 'V064 Guard A PASS: Agent Spine decision store shape verified';
END $$;

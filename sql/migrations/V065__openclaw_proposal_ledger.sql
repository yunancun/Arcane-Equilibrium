-- ============================================================
-- V065: OpenClaw proposal / approval / channel-event ledger
-- OpenClaw proposal / approval / channel-event 審計帳本
--
-- Purpose:
--   OC-GW-5/6/7 durable backing tables. These tables record proposal intake,
--   operator approval/rejection intent, and channel audit traces only. They do
--   not authorize orders, live auth, config mutation, deploy, or Bybit access.
-- ============================================================

CREATE SCHEMA IF NOT EXISTS openclaw;

CREATE TABLE IF NOT EXISTS openclaw.proposals (
    proposal_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    channel TEXT NOT NULL,
    request_id TEXT NOT NULL,
    created_at_ms BIGINT NOT NULL,
    created_by JSONB NOT NULL,
    proposal_type TEXT NOT NULL CHECK (
        proposal_type IN (
            'read_only_report',
            'diagnosis_followup',
            'offline_replay',
            'config_change',
            'risk_change',
            'live_authorization',
            'deploy',
            'trade_affecting'
        )
    ),
    risk_class TEXT NOT NULL CHECK (
        risk_class IN (
            'read_only',
            'offline',
            'demo_only',
            'live_affecting',
            'mainnet_affecting'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'drafted',
            'persisted',
            'visible',
            'pending_approval',
            'completed_read_only',
            'approved',
            'rejected',
            'expired',
            'cancelled',
            'failed'
        )
    ),
    summary TEXT NOT NULL CHECK (octet_length(summary) <= 4096),
    evidence_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    required_approval_class TEXT NOT NULL CHECK (
        required_approval_class IN (
            'none',
            'operator',
            'governance',
            'live_reserved',
            'deploy_operator'
        )
    ),
    operator_action_required BOOLEAN NOT NULL,
    expires_at_ms BIGINT,
    linked_diagnosis_id TEXT,
    linked_escalation_id TEXT,
    side_effect_route TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, channel, request_id),
    CHECK (jsonb_typeof(evidence_refs) = 'array'),
    CHECK (jsonb_array_length(evidence_refs) > 0),
    CHECK (jsonb_typeof(payload) = 'object'),
    CHECK (
        required_approval_class = 'none'
        OR expires_at_ms IS NOT NULL
    ),
    CHECK (
        side_effect_route IS NULL
        OR (
            side_effect_route LIKE '/api/v1/governance/%'
            AND side_effect_route !~* '(order|cancel|close|secret|key|live-auth|session/start|risk-config|strategy-config|toml|deploy|restart|shell|migration)'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_openclaw_proposals_status_created
    ON openclaw.proposals (status, created_at_ms DESC);

CREATE INDEX IF NOT EXISTS idx_openclaw_proposals_expiry
    ON openclaw.proposals (expires_at_ms)
    WHERE status = 'pending_approval';

CREATE TABLE IF NOT EXISTS openclaw.approval_decisions (
    approval_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES openclaw.proposals(proposal_id) ON DELETE RESTRICT,
    request_id TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (
        decision IN ('approved', 'rejected', 'expired', 'denied', 'cancelled')
    ),
    decided_at_ms BIGINT NOT NULL,
    actor JSONB NOT NULL,
    auth_result TEXT NOT NULL CHECK (
        auth_result IN (
            'authenticated',
            'unauthorized',
            'expired',
            'insufficient_scope'
        )
    ),
    reason TEXT,
    delegated_route TEXT,
    governance_result_ref JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (proposal_id, request_id),
    CHECK (jsonb_typeof(actor) = 'object'),
    CHECK (
        delegated_route IS NULL
        OR delegated_route LIKE '/api/v1/governance/%'
    )
);

CREATE INDEX IF NOT EXISTS idx_openclaw_approval_decisions_proposal
    ON openclaw.approval_decisions (proposal_id, decided_at_ms DESC);

CREATE TABLE IF NOT EXISTS openclaw.channel_events (
    channel_event_id TEXT PRIMARY KEY,
    request_id TEXT NOT NULL,
    ts_ms BIGINT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('inbound', 'outbound')),
    channel TEXT NOT NULL CHECK (
        channel IN (
            'console',
            'telegram',
            'webchat',
            'mobile',
            'gateway_internal'
        )
    ),
    sender TEXT NOT NULL,
    auth_profile TEXT NOT NULL CHECK (
        auth_profile IN (
            'anonymous',
            'read_only',
            'operator',
            'live_operator',
            'service'
        )
    ),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'status_query',
            'alert_sent',
            'ack',
            'proposal_created',
            'approval_intent',
            'brief_sent',
            'diagnosis_request'
        )
    ),
    status TEXT NOT NULL CHECK (
        status IN (
            'received',
            'validated',
            'persisted',
            'dispatched',
            'acknowledged',
            'rejected',
            'failed'
        )
    ),
    linked_proposal_id TEXT REFERENCES openclaw.proposals(proposal_id) ON DELETE SET NULL,
    linked_escalation_id TEXT,
    payload_summary TEXT NOT NULL CHECK (octet_length(payload_summary) <= 4096),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_openclaw_channel_events_ts
    ON openclaw.channel_events (ts_ms DESC);

CREATE INDEX IF NOT EXISTS idx_openclaw_channel_events_proposal
    ON openclaw.channel_events (linked_proposal_id, ts_ms DESC)
    WHERE linked_proposal_id IS NOT NULL;

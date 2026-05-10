from __future__ import annotations

"""OpenClaw authority and ledger boundary contracts."""

from typing import TypeAlias


RouteSpec: TypeAlias = tuple[str, str, str]

OPENCLAW_CONTEXT_HEADERS: dict[str, str] = {
    "source": "x-openclaw-source",
    "channel": "x-openclaw-channel",
    "sender": "x-openclaw-sender",
    "auth_profile": "x-openclaw-auth-profile",
    "request_id": "x-openclaw-request-id",
}

OPENCLAW_READ_ONLY_ROUTES: tuple[RouteSpec, ...] = (
    (
        "GET",
        "/api/v1/openclaw/status",
        "OpenClaw status view",
    ),
    (
        "GET",
        "/api/v1/openclaw/self-state",
        "OpenClaw self-state view",
    ),
    (
        "GET",
        "/api/v1/openclaw/brief/latest",
        "OpenClaw latest brief view",
    ),
    (
        "GET",
        "/api/v1/openclaw/diagnostics",
        "OpenClaw diagnostics view",
    ),
    (
        "GET",
        "/api/v1/openclaw/escalations",
        "OpenClaw supervisor escalation ledger view",
    ),
)

OPENCLAW_PROPOSAL_LEDGER_ROUTES: tuple[RouteSpec, ...] = (
    (
        "GET",
        "/api/v1/openclaw/proposals",
        "OpenClaw proposal ledger view",
    ),
    (
        "POST",
        "/api/v1/openclaw/proposals",
        "OpenClaw proposal intake ledger route",
    ),
    (
        "POST",
        "/api/v1/openclaw/proposals/{proposal_id}/approve",
        "OpenClaw approval decision ledger route",
    ),
    (
        "POST",
        "/api/v1/openclaw/proposals/{proposal_id}/reject",
        "OpenClaw rejection decision ledger route",
    ),
)

OPENCLAW_ACTIVE_ROUTES: tuple[RouteSpec, ...] = (
    OPENCLAW_READ_ONLY_ROUTES + OPENCLAW_PROPOSAL_LEDGER_ROUTES
)

OPENCLAW_LEDGER_WRITE_CLASSES: tuple[str, ...] = (
    "proposal_ledger",
    "approval_decision_ledger",
    "channel_event_audit",
)

OPENCLAW_SAFE_APPROVAL_TYPES = frozenset({
    "read_only_report",
    "diagnosis_followup",
    "offline_replay",
})
OPENCLAW_SAFE_APPROVAL_RISK_CLASSES = frozenset({
    "read_only",
    "offline",
})

OPENCLAW_FORBIDDEN_SIDE_EFFECT_FRAGMENTS: tuple[str, ...] = (
    "order",
    "cancel",
    "close",
    "secret",
    "key",
    "live-auth",
    "session/start",
    "risk-config",
    "strategy-config",
    "toml",
    "deploy",
    "restart",
    "shell",
    "migration",
)


def openclaw_active_allowlist() -> list[dict[str, str]]:
    return [
        {"method": method, "path": path}
        for method, path, _label in OPENCLAW_ACTIVE_ROUTES
    ]


def build_openclaw_authority_posture() -> dict[str, object]:
    """Return OpenClaw's active authority posture without route coupling."""
    return {
        "trading_authority": "rust_openclaw_engine",
        "gateway_role": "read_only_supervisor_relay",
        "active_allowlist": openclaw_active_allowlist(),
        "deferred_workflows_enabled": True,
        "proposal_creation_enabled": True,
        "external_approval_relay_enabled": True,
        "enabled_write_classes": list(OPENCLAW_LEDGER_WRITE_CLASSES),
        "can_submit_orders": False,
        "can_cancel_orders": False,
        "can_close_positions": False,
        "can_mutate_live_config": False,
        "can_mutate_risk_config": False,
        "can_read_secrets": False,
        "can_restart_or_deploy": False,
        "requires_governance_hub_for_side_effects": True,
        "requires_decision_lease_for_execution": True,
        "request_context_required": list(OPENCLAW_CONTEXT_HEADERS.keys()),
    }


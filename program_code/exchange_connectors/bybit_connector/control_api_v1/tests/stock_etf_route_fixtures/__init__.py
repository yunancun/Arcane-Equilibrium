"""Shared fixtures and payload builders for Stock/ETF route tests."""

from .app import (
    STATIC_DIR,
    _make_authless_client,
    _make_client_with_ipc,
    client_fail_closed,
    route_module,
    stock_etf_router,
)
from .phase2_payloads import (
    API_ALLOWLIST_DENIED_ACTIONS,
    API_ALLOWLIST_PAPER_WRITE_ACTIONS,
    API_ALLOWLIST_READ_ACTIONS,
    _valid_api_allowlist,
    _valid_authorization_status,
    _valid_data_foundation_status,
    _valid_lane_status,
    _valid_phase0_status,
    _valid_policy_status,
)
from .phase3_payloads import (
    _valid_account_status,
    _valid_evidence_status,
    _valid_paper_status,
    _valid_reconciliation_status,
    _valid_scorecard_status,
    _valid_shadow_status,
    _valid_universe_status,
)
from .phase5_payloads import (
    _valid_disable_cleanup_status,
    _valid_launch_status,
    _valid_release_packet_status,
)

__all__ = [
    "API_ALLOWLIST_DENIED_ACTIONS",
    "API_ALLOWLIST_PAPER_WRITE_ACTIONS",
    "API_ALLOWLIST_READ_ACTIONS",
    "STATIC_DIR",
    "_make_authless_client",
    "_make_client_with_ipc",
    "client_fail_closed",
    "route_module",
    "stock_etf_router",
    "_valid_account_status",
    "_valid_api_allowlist",
    "_valid_authorization_status",
    "_valid_data_foundation_status",
    "_valid_disable_cleanup_status",
    "_valid_evidence_status",
    "_valid_lane_status",
    "_valid_launch_status",
    "_valid_paper_status",
    "_valid_phase0_status",
    "_valid_policy_status",
    "_valid_reconciliation_status",
    "_valid_release_packet_status",
    "_valid_scorecard_status",
    "_valid_shadow_status",
    "_valid_universe_status",
]

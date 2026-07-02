"""Source-only IBKR connector action-matrix preview tests."""

from __future__ import annotations

import sys
from pathlib import Path


SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    IbkrApiActionMatrixPreview,
    IbkrReadOnlyClient,
    IbkrReadOnlyEndpointConfig,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    blocked_api_action_matrix_fixture,
)


EXPECTED_READ_ACTIONS = [
    "server_time_read",
    "connection_health_read",
    "account_summary_snapshot_read",
    "portfolio_positions_snapshot_read",
    "contract_details_read",
    "market_data_snapshot_read",
    "market_data_subscription_read",
    "historical_bars_read",
    "open_paper_orders_read",
    "paper_executions_commissions_read",
]
EXPECTED_PAPER_WRITE_ACTIONS = [
    "paper_order_submit",
    "paper_order_cancel",
    "paper_order_replace",
]
EXPECTED_DENIED_ACTIONS = [
    "live_order_submit",
    "live_account_query",
    "account_transfer",
    "margin_enablement",
    "short_borrow",
    "options_trading",
    "cfd_trading",
    "market_data_entitlement_purchase",
    "account_management_write",
    "client_portal_web_api_use",
]
ACTION_MATRIX_KEYS = {
    "accepted",
    "asset_lane",
    "blockers",
    "broker",
    "broker_write_authority",
    "bybit_path_reused",
    "contract_id",
    "denied_action_count",
    "denied_actions",
    "environment",
    "external_surface_gate_accepted",
    "ibkr_contact_performed",
    "live_or_tiny_live_authorized",
    "network_contact_performed",
    "paper_write_action_count",
    "paper_write_actions",
    "paper_write_actions_authorized",
    "read_action_count",
    "read_actions",
    "secret_content_loaded",
    "secret_content_serialized",
    "source_version",
    "status",
}
DEFAULT_BLOCKERS = [
    "phase2_gate_not_accepted",
    "api_action_matrix_blocked_source_only",
]
RISKY_CONFIG_BLOCKERS = [
    "host_not_loopback",
    "port_not_reserved_paper_tws",
    "network_contact_requested",
    "secret_material_requested",
    "paper_channel_requested",
    "live_channel_requested",
    "bybit_path_reused",
    "account_fingerprint_present_before_phase2",
    "secret_fingerprint_present_before_phase2",
]
SIDE_EFFECT_FALSE_KEYS = {
    "accepted",
    "external_surface_gate_accepted",
    "broker_write_authority",
    "paper_write_actions_authorized",
    "ibkr_contact_performed",
    "network_contact_performed",
    "secret_content_loaded",
    "secret_content_serialized",
    "bybit_path_reused",
    "live_or_tiny_live_authorized",
}


def _assert_action_matrix_payload(
    payload: dict[str, object],
    *,
    blockers: list[str] | None = None,
) -> None:
    assert set(payload) == ACTION_MATRIX_KEYS
    assert payload["contract_id"] == IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID
    assert payload["source_version"] == 1
    assert payload["status"] == "blocked_source_only"
    assert payload["asset_lane"] == "stock_etf_cash"
    assert payload["broker"] == "ibkr"
    assert payload["environment"] == "read_only"
    assert payload["read_actions"] == EXPECTED_READ_ACTIONS
    assert payload["paper_write_actions"] == EXPECTED_PAPER_WRITE_ACTIONS
    assert payload["denied_actions"] == EXPECTED_DENIED_ACTIONS
    assert payload["read_action_count"] == len(EXPECTED_READ_ACTIONS)
    assert payload["paper_write_action_count"] == len(EXPECTED_PAPER_WRITE_ACTIONS)
    assert payload["denied_action_count"] == len(EXPECTED_DENIED_ACTIONS)
    assert payload["blockers"] == (blockers or DEFAULT_BLOCKERS)
    for key in SIDE_EFFECT_FALSE_KEYS:
        assert payload[key] is False, key


def test_ibkr_action_matrix_preview_pins_exact_source_only_buckets() -> None:
    _assert_action_matrix_payload(IbkrReadOnlyClient().api_action_matrix_preview())


def test_ibkr_action_matrix_fixture_matches_client_preview() -> None:
    client_payload = IbkrReadOnlyClient().api_action_matrix_preview()

    assert blocked_api_action_matrix_fixture() == client_payload


def test_ibkr_action_matrix_risky_config_only_expands_blockers() -> None:
    config = IbkrReadOnlyEndpointConfig(
        host="0.0.0.0",
        port=7496,
        allow_network_contact=True,
        allow_secret_material=True,
        allow_paper_channel=True,
        allow_live_channel=True,
        bybit_path_reused=True,
        account_fingerprint_hash="1" * 64,
        secret_fingerprint_hash="2" * 64,
    )

    _assert_action_matrix_payload(
        IbkrReadOnlyClient(config).api_action_matrix_preview(),
        blockers=DEFAULT_BLOCKERS + RISKY_CONFIG_BLOCKERS,
    )


def test_ibkr_action_matrix_preview_dataclass_remains_inert() -> None:
    preview = IbkrApiActionMatrixPreview()

    assert preview.contract_id == IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID
    assert preview.accepted is False
    assert preview.paper_write_actions_authorized is False
    assert preview.broker_write_authority is False
    assert preview.read_actions == tuple(EXPECTED_READ_ACTIONS)
    assert preview.paper_write_actions == tuple(EXPECTED_PAPER_WRITE_ACTIONS)
    assert preview.denied_actions == tuple(EXPECTED_DENIED_ACTIONS)

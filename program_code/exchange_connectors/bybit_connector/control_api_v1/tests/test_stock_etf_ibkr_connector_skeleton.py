"""Source-only IBKR connector skeleton contract tests."""

from __future__ import annotations

import sys
from pathlib import Path


SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IBKR_CONNECTOR_SURFACE_ID,
    IbkrPaperClientBoundary,
    IbkrReadOnlyClient,
    IbkrReadOnlyEndpointConfig,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    blocked_readonly_fixture,
)


FORBIDDEN_WRITE_METHODS = {
    "place_order",
    "submit_order",
    "submit_paper_order",
    "cancel_order",
    "cancel_all_orders",
    "cancel_paper_order",
    "replace_order",
    "replace_paper_order",
    "modify_order",
    "create_order",
}


def test_ibkr_connector_skeleton_has_no_python_broker_write_methods() -> None:
    for cls in (IbkrReadOnlyClient, IbkrPaperClientBoundary):
        assert sorted(FORBIDDEN_WRITE_METHODS.intersection(dir(cls))) == []


def test_ibkr_readonly_client_is_blocked_without_network_or_secret_side_effects() -> None:
    status = IbkrReadOnlyClient().readiness().to_dict()

    assert status["surface_id"] == IBKR_CONNECTOR_SURFACE_ID
    assert status["accepted"] is False
    assert status["status"] == "blocked_source_only"
    assert status["asset_lane"] == "stock_etf_cash"
    assert status["broker"] == "ibkr"
    assert status["network_contact_performed"] is False
    assert status["secret_content_loaded"] is False
    assert status["paper_channel_exposed"] is False
    assert status["live_channel_exposed"] is False
    assert status["order_write_method_present"] is False
    assert status["bybit_path_reused"] is False
    assert "phase2_gate_not_accepted" in status["blockers"]


def test_ibkr_readonly_config_rejects_runtime_and_live_requests() -> None:
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

    blockers = set(config.validate_source_boundary())

    assert {
        "host_not_loopback",
        "port_not_reserved_paper_tws",
        "network_contact_requested",
        "secret_material_requested",
        "paper_channel_requested",
        "live_channel_requested",
        "bybit_path_reused",
        "account_fingerprint_present_before_phase2",
        "secret_fingerprint_present_before_phase2",
    }.issubset(blockers)


def test_ibkr_connector_previews_remain_display_only() -> None:
    client = IbkrReadOnlyClient()
    paper = IbkrPaperClientBoundary()

    for payload in (
        client.connection_plan(),
        client.account_snapshot_preview(),
        client.market_data_preview(),
        client.contract_details_preview(),
        paper.lifecycle_readiness(),
        paper.fill_import_readiness(),
        blocked_readonly_fixture(),
    ):
        assert payload.get("network_contact_performed") is False
        assert payload.get("secret_content_loaded") is False
        assert payload.get("bybit_path_reused") is False
        assert payload.get("order_write_method_present", False) is False

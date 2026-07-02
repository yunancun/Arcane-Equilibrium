"""Cross-surface API allowlist bucket parity for Stock/ETF IBKR source fixtures."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from stock_etf_route_fixtures import (
    API_ALLOWLIST_DENIED_ACTIONS,
    API_ALLOWLIST_PAPER_WRITE_ACTIONS,
    API_ALLOWLIST_READ_ACTIONS,
    _make_client_with_ipc,
    _valid_account_status,
    _valid_authorization_status,
    _valid_data_foundation_status,
    _valid_disable_cleanup_status,
    _valid_evidence_status,
    _valid_lane_status,
    _valid_launch_status,
    _valid_paper_status,
    _valid_policy_status,
    _valid_reconciliation_status,
    _valid_release_packet_status,
    _valid_scorecard_status,
    _valid_shadow_status,
    _valid_universe_status,
    client_fail_closed,
)


SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID,
    IbkrReadOnlyClient,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    blocked_api_action_matrix_fixture,
)


def _assert_matches_fastapi_allowlist_buckets(payload: dict[str, object]) -> None:
    assert payload["contract_id"] == IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID
    assert payload["read_actions"] == API_ALLOWLIST_READ_ACTIONS
    assert payload["paper_write_actions"] == API_ALLOWLIST_PAPER_WRITE_ACTIONS
    assert payload["denied_actions"] == API_ALLOWLIST_DENIED_ACTIONS
    assert payload["read_action_count"] == len(API_ALLOWLIST_READ_ACTIONS)
    assert payload["paper_write_action_count"] == len(API_ALLOWLIST_PAPER_WRITE_ACTIONS)
    assert payload["denied_action_count"] == len(API_ALLOWLIST_DENIED_ACTIONS)


def _assert_fail_closed_api_allowlist_buckets(payload: dict[str, object]) -> None:
    assert payload["contract_id"] == ""
    assert payload["source_version"] == 0
    assert payload["accepted"] is False
    assert payload["blockers"] == ["ipc_unavailable"]
    assert payload["read_actions"] == []
    assert payload["paper_write_actions"] == []
    assert payload["denied_actions"] == []
    assert payload["read_action_count"] == 0
    assert payload["paper_write_action_count"] == 0
    assert payload["denied_action_count"] == 0


def test_ibkr_connector_action_matrix_matches_fastapi_readiness_allowlist() -> None:
    _assert_matches_fastapi_allowlist_buckets(
        IbkrReadOnlyClient().api_action_matrix_preview()
    )


def test_ibkr_connector_action_matrix_fixture_matches_fastapi_allowlist() -> None:
    _assert_matches_fastapi_allowlist_buckets(blocked_api_action_matrix_fixture())


@pytest.mark.parametrize(
    ("path", "payload_factory"),
    [
        ("/api/v1/stock-etf/lane-status", _valid_lane_status),
        ("/api/v1/stock-etf/data-foundation-status", _valid_data_foundation_status),
        ("/api/v1/stock-etf/policy-status", _valid_policy_status),
        ("/api/v1/stock-etf/authorization-status", _valid_authorization_status),
        ("/api/v1/stock-etf/evidence-status", _valid_evidence_status),
        ("/api/v1/stock-etf/account-status", _valid_account_status),
        ("/api/v1/stock-etf/universe-status", _valid_universe_status),
        ("/api/v1/stock-etf/shadow-status", _valid_shadow_status),
        ("/api/v1/stock-etf/paper-status", _valid_paper_status),
        ("/api/v1/stock-etf/reconciliation-status", _valid_reconciliation_status),
        ("/api/v1/stock-etf/scorecard-status", _valid_scorecard_status),
        ("/api/v1/stock-etf/launch-status", _valid_launch_status),
        ("/api/v1/stock-etf/release-packet-status", _valid_release_packet_status),
        ("/api/v1/stock-etf/disable-cleanup-status", _valid_disable_cleanup_status),
    ],
)
def test_stock_etf_status_routes_preserve_api_allowlist_buckets(
    path: str, payload_factory
) -> None:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload_factory())
    client = _make_client_with_ipc(fake_ipc)
    try:
        response = client.get(path)
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert response.status_code == 200
    _assert_matches_fastapi_allowlist_buckets(response.json()["data"]["api_allowlist"])


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/stock-etf/lane-status",
        "/api/v1/stock-etf/data-foundation-status",
        "/api/v1/stock-etf/policy-status",
        "/api/v1/stock-etf/authorization-status",
        "/api/v1/stock-etf/evidence-status",
        "/api/v1/stock-etf/account-status",
        "/api/v1/stock-etf/universe-status",
        "/api/v1/stock-etf/shadow-status",
        "/api/v1/stock-etf/paper-status",
        "/api/v1/stock-etf/reconciliation-status",
        "/api/v1/stock-etf/scorecard-status",
        "/api/v1/stock-etf/launch-status",
        "/api/v1/stock-etf/release-packet-status",
        "/api/v1/stock-etf/disable-cleanup-status",
    ],
)
def test_stock_etf_fail_closed_status_routes_preserve_api_allowlist_shape(
    client_fail_closed, path: str
) -> None:
    response = client_fail_closed.get(path)

    assert response.status_code == 200
    _assert_fail_closed_api_allowlist_buckets(response.json()["data"]["api_allowlist"])

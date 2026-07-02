"""Cross-surface API allowlist bucket parity for Stock/ETF IBKR source fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

from stock_etf_route_fixtures import (
    API_ALLOWLIST_DENIED_ACTIONS,
    API_ALLOWLIST_PAPER_WRITE_ACTIONS,
    API_ALLOWLIST_READ_ACTIONS,
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


def test_ibkr_connector_action_matrix_matches_fastapi_readiness_allowlist() -> None:
    _assert_matches_fastapi_allowlist_buckets(
        IbkrReadOnlyClient().api_action_matrix_preview()
    )


def test_ibkr_connector_action_matrix_fixture_matches_fastapi_allowlist() -> None:
    _assert_matches_fastapi_allowlist_buckets(blocked_api_action_matrix_fixture())

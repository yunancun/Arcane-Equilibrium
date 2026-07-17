"""Cross-surface session attestation safety-shape parity for Stock/ETF IBKR."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

from stock_etf_route_fixtures import (
    _make_client_with_ipc,
    _valid_account_status,
    _valid_authorization_status,
    client_fail_closed,
)


SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    IbkrReadOnlyClient,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    blocked_session_attestation_fixture,
)


SESSION_ATTESTATION_SECURITY_BASELINE = {
    "expected_contract_id": IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    "contract_id": "",
    "source_version": 0,
    "status": "BLOCKED",
    "attestation_accepted": False,
    "environment": "read_only",
    "account_fingerprint_present": False,
    "account_fingerprint_is_live": False,
    "host": "",
    "port": 0,
    "process_identity_present": False,
    "gateway_mode": "unknown",
    "secret_slot_fingerprint_present": False,
    "secret_slot_mode": "unknown",
    "secret_world_readable": False,
    "live_secret_absent_or_empty": False,
    "env_var_credential_fallback_used": False,
    "api_server_version_present": False,
    "data_tier": "unknown",
    "entitlements_fingerprint_present": False,
    "market_data_entitlement_purchase_denied": False,
    "gateway_started_at_ms": 0,
    "attested_at_ms": 0,
    "expires_at_ms": 0,
    "raw_artifact_hash_present": False,
}


def _canonical_session_attestation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "expected_contract_id": payload["expected_contract_id"],
        "contract_id": payload["contract_id"],
        "source_version": payload["source_version"],
        "status": payload["status"],
        "attestation_accepted": payload.get(
            "attestation_accepted",
            payload.get("accepted"),
        ),
        "environment": payload["environment"],
        "account_fingerprint_present": payload["account_fingerprint_present"],
        "account_fingerprint_is_live": payload["account_fingerprint_is_live"],
        "host": payload["host"],
        "port": payload["port"],
        "process_identity_present": payload["process_identity_present"],
        "gateway_mode": payload["gateway_mode"],
        "secret_slot_fingerprint_present": payload["secret_slot_fingerprint_present"],
        "secret_slot_mode": payload["secret_slot_mode"],
        "secret_world_readable": payload["secret_world_readable"],
        "live_secret_absent_or_empty": payload["live_secret_absent_or_empty"],
        "env_var_credential_fallback_used": payload[
            "env_var_credential_fallback_used"
        ],
        "api_server_version_present": payload["api_server_version_present"],
        "data_tier": payload["data_tier"],
        "entitlements_fingerprint_present": payload[
            "entitlements_fingerprint_present"
        ],
        "market_data_entitlement_purchase_denied": payload[
            "market_data_entitlement_purchase_denied"
        ],
        "gateway_started_at_ms": payload["gateway_started_at_ms"],
        "attested_at_ms": payload["attested_at_ms"],
        "expires_at_ms": payload["expires_at_ms"],
        "raw_artifact_hash_present": payload["raw_artifact_hash_present"],
    }


def _route_session_attestation(path: str, payload_factory) -> dict[str, Any]:
    fake_ipc = AsyncMock()
    fake_ipc.call = AsyncMock(return_value=payload_factory())
    client = _make_client_with_ipc(fake_ipc)
    try:
        response = client.get(path)
    finally:
        client._stock_etf_patcher.stop()  # type: ignore[attr-defined]

    assert response.status_code == 200
    return response.json()["data"]["session_attestation"]


def test_connector_and_route_session_attestation_safety_shape_match() -> None:
    payloads = [
        IbkrReadOnlyClient().session_attestation_preview(),
        blocked_session_attestation_fixture(),
        _route_session_attestation(
            "/api/v1/stock-etf/account-status",
            _valid_account_status,
        ),
    ]

    for payload in payloads:
        assert _canonical_session_attestation(payload) == (
            SESSION_ATTESTATION_SECURITY_BASELINE
        )

    # W6-S0(R17)後 authorization_status 的 session 腿=attestation producer 真值
    # (`blocked_session_attestation()`):契約身分立正(contract_id/source_version=1),
    # 與其餘三個 surface 的 raw-default 身分("" / 0)在 identity 兩欄分道;安全形
    # (BLOCKED/無指紋/attestation 不接受)仍必須跨 surface 一致。
    authorization_payload = _route_session_attestation(
        "/api/v1/stock-etf/authorization-status",
        _valid_authorization_status,
    )
    assert _canonical_session_attestation(authorization_payload) == {
        **SESSION_ATTESTATION_SECURITY_BASELINE,
        "contract_id": IBKR_SESSION_ATTESTATION_CONTRACT_ID,
        "source_version": 1,
    }


def test_fail_closed_routes_preserve_session_attestation_safety_shape(
    client_fail_closed,
) -> None:
    for path in (
        "/api/v1/stock-etf/account-status",
        "/api/v1/stock-etf/authorization-status",
    ):
        response = client_fail_closed.get(path)

        assert response.status_code == 200
        attestation = response.json()["data"]["session_attestation"]
        assert _canonical_session_attestation(attestation) == (
            SESSION_ATTESTATION_SECURITY_BASELINE
        )
        assert attestation["blockers"] == ["ipc_unavailable"]

"""Source-only IBKR connector skeleton contract tests."""

from __future__ import annotations

import ast
import sys
from pathlib import Path


SRV_ROOT = Path(__file__).resolve().parents[5]
if str(SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(SRV_ROOT))

import program_code.broker_connectors.ibkr_connector as ibkr_connector  # noqa: E402
from program_code.broker_connectors.ibkr_connector import (  # noqa: E402
    IBKR_CONNECTOR_SURFACE_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    IbkrPaperAttestationPreview,
    IbkrPaperClientBoundary,
    IbkrReadOnlyClient,
    IbkrReadOnlyEndpointConfig,
    IbkrSessionAttestationPreview,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    blocked_paper_attestation_fixture,
    blocked_readonly_fixture,
    blocked_session_attestation_fixture,
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

IBKR_CONNECTOR_DIR = SRV_ROOT / "program_code" / "broker_connectors" / "ibkr_connector"

FORBIDDEN_BYBIT_IMPORT_PREFIXES = (
    "app",
    "bybit_connector",
    "exchange_connectors.bybit_connector",
    "program_code.exchange_connectors.bybit_connector",
)

READONLY_SURFACE_KEYS = {
    "accepted",
    "account_snapshot_loaded",
    "asset_lane",
    "blockers",
    "broker",
    "bybit_path_reused",
    "contract_details_loaded",
    "environment",
    "live_channel_exposed",
    "market_data_loaded",
    "network_contact_performed",
    "order_write_method_present",
    "paper_channel_exposed",
    "secret_content_loaded",
    "status",
    "surface_id",
}

CONNECTION_PLAN_KEYS = {
    "accepted",
    "asset_lane",
    "blockers",
    "broker",
    "bybit_path_reused",
    "client_id",
    "environment",
    "host",
    "live_channel_exposed",
    "network_contact_allowed",
    "network_contact_performed",
    "paper_channel_exposed",
    "port",
    "secret_content_loaded",
    "status",
    "surface_id",
    "transport",
}

PAPER_LIFECYCLE_KEYS = READONLY_SURFACE_KEYS | {
    "paper_lifecycle_readiness",
    "python_broker_write_authority",
    "rust_authority_required",
}

FILL_IMPORT_KEYS = READONLY_SURFACE_KEYS | {
    "broker_write_authority",
    "db_apply_authority",
    "fill_import_readiness",
    "python_import_side_effects",
}

SESSION_ATTESTATION_KEYS = {
    "account_fingerprint_is_live",
    "account_fingerprint_present",
    "api_server_version_present",
    "attestation_accepted",
    "blockers",
    "bybit_path_reused",
    "contract_id",
    "data_tier",
    "entitlements_fingerprint_present",
    "environment",
    "expected_contract_id",
    "gateway_started_at_ms",
    "market_data_entitlement_purchase_denied",
    "network_contact_performed",
    "raw_artifact_hash_present",
    "secret_content_loaded",
    "secret_slot_fingerprint_present",
    "source_version",
    "status",
}

PAPER_ATTESTATION_KEYS = {
    "accepted",
    "account_fingerprint_present",
    "blockers",
    "bybit_path_reused",
    "contract_id",
    "environment",
    "expected_contract_id",
    "live_channel_exposed",
    "network_contact_performed",
    "paper_account_attestation_present",
    "paper_channel_exposed",
    "paper_order_channel_attested",
    "secret_content_loaded",
    "secret_slot_fingerprint_present",
    "session_attestation_present",
    "source_version",
}

SIDE_EFFECT_FALSE_KEYS = {
    "account_snapshot_loaded",
    "broker_write_authority",
    "bybit_path_reused",
    "contract_details_loaded",
    "db_apply_authority",
    "fill_import_readiness",
    "live_channel_exposed",
    "market_data_loaded",
    "network_contact_allowed",
    "network_contact_performed",
    "order_write_method_present",
    "paper_channel_exposed",
    "paper_lifecycle_readiness",
    "paper_account_attestation_present",
    "python_broker_write_authority",
    "python_import_side_effects",
    "secret_content_loaded",
    "session_attestation_present",
}
EXPECTED_CONNECTOR_EXPORTS = (
    "IBKR_CONNECTOR_SURFACE_ID",
    "IBKR_PAPER_ATTESTATION_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "IbkrPaperAttestationPreview",
    "IbkrPaperClientBoundary",
    "IbkrReadOnlyClient",
    "IbkrReadOnlyEndpointConfig",
    "IbkrReadOnlySurfaceStatus",
    "IbkrSessionAttestationPreview",
)
EXPECTED_READONLY_CLIENT_PUBLIC_SURFACE = {
    "account_snapshot_preview",
    "config",
    "connection_plan",
    "contract_details_preview",
    "market_data_preview",
    "readiness",
    "session_attestation_preview",
}
EXPECTED_PAPER_CLIENT_PUBLIC_SURFACE = {
    "fill_import_readiness",
    "lifecycle_readiness",
    "paper_attestation_preview",
}


def _ibkr_connector_python_files() -> list[Path]:
    return sorted(
        path
        for path in IBKR_CONNECTOR_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _imported_module_names(node: ast.Import | ast.ImportFrom) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if node.module is None:
        return []
    return [node.module]


def _is_forbidden_bybit_import(module: str) -> bool:
    return any(
        module == prefix or module.startswith(f"{prefix}.")
        for prefix in FORBIDDEN_BYBIT_IMPORT_PREFIXES
    )


def _call_name(func: ast.AST) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parent = _call_name(func.value)
        return f"{parent}.{func.attr}" if parent else func.attr
    return ""


def _declared_public_surface(cls: type) -> set[str]:
    return {name for name in vars(cls) if not name.startswith("_")}


def test_ibkr_connector_package_exports_only_source_boundary_types() -> None:
    assert tuple(ibkr_connector.__all__) == EXPECTED_CONNECTOR_EXPORTS
    for name in EXPECTED_CONNECTOR_EXPORTS:
        assert getattr(ibkr_connector, name) is not None
    assert IBKR_SESSION_ATTESTATION_CONTRACT_ID == "ibkr_session_attestation_v1"
    assert IBKR_PAPER_ATTESTATION_CONTRACT_ID == "ibkr_paper_attestation_v1"


def test_ibkr_connector_skeleton_has_no_python_broker_write_methods() -> None:
    for cls in (IbkrReadOnlyClient, IbkrPaperClientBoundary):
        assert sorted(FORBIDDEN_WRITE_METHODS.intersection(dir(cls))) == []
    assert IbkrSessionAttestationPreview().attestation_accepted is False
    assert IbkrPaperAttestationPreview().accepted is False


def test_ibkr_connector_client_public_surfaces_are_frozen_source_only() -> None:
    assert _declared_public_surface(IbkrReadOnlyClient) == EXPECTED_READONLY_CLIENT_PUBLIC_SURFACE
    assert _declared_public_surface(IbkrPaperClientBoundary) == EXPECTED_PAPER_CLIENT_PUBLIC_SURFACE


def test_ibkr_connector_skeleton_does_not_import_bybit_or_control_api_modules() -> None:
    files = _ibkr_connector_python_files()
    assert files, "expected source-only IBKR connector package files"

    violations: list[str] = []
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for module in _imported_module_names(node):
                    if _is_forbidden_bybit_import(module):
                        violations.append(f"{path}:{node.lineno}: forbidden import {module!r}")
            elif isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in {"__import__", "importlib.import_module"} and node.args:
                    arg = node.args[0]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if _is_forbidden_bybit_import(arg.value):
                            violations.append(
                                f"{path}:{node.lineno}: forbidden dynamic import {arg.value!r}"
                            )

    assert violations == []


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
        client.session_attestation_preview(),
        paper.lifecycle_readiness(),
        paper.fill_import_readiness(),
        paper.paper_attestation_preview(),
        blocked_readonly_fixture(),
        blocked_session_attestation_fixture(),
        blocked_paper_attestation_fixture(),
    ):
        assert payload.get("network_contact_performed") is False
        assert payload.get("secret_content_loaded") is False
        assert payload.get("bybit_path_reused") is False
        assert payload.get("order_write_method_present", False) is False


def test_ibkr_connector_preview_payload_shapes_are_fail_closed() -> None:
    client = IbkrReadOnlyClient()
    paper = IbkrPaperClientBoundary()
    payloads = {
        "connection_plan": (client.connection_plan(), CONNECTION_PLAN_KEYS),
        "readiness": (client.readiness().to_dict(), READONLY_SURFACE_KEYS),
        "account_snapshot": (
            client.account_snapshot_preview(),
            READONLY_SURFACE_KEYS,
        ),
        "market_data": (client.market_data_preview(), READONLY_SURFACE_KEYS),
        "contract_details": (
            client.contract_details_preview(),
            READONLY_SURFACE_KEYS,
        ),
        "session_attestation": (
            client.session_attestation_preview(),
            SESSION_ATTESTATION_KEYS,
        ),
        "paper_lifecycle": (paper.lifecycle_readiness(), PAPER_LIFECYCLE_KEYS),
        "fill_import": (paper.fill_import_readiness(), FILL_IMPORT_KEYS),
        "paper_attestation": (
            paper.paper_attestation_preview(),
            PAPER_ATTESTATION_KEYS,
        ),
        "fixture": (blocked_readonly_fixture(), READONLY_SURFACE_KEYS),
        "session_fixture": (
            blocked_session_attestation_fixture(),
            SESSION_ATTESTATION_KEYS,
        ),
        "paper_fixture": (
            blocked_paper_attestation_fixture(),
            PAPER_ATTESTATION_KEYS,
        ),
    }

    for name, (payload, expected_keys) in payloads.items():
        assert set(payload) == expected_keys, name
        if "surface_id" in payload:
            assert payload["surface_id"] == IBKR_CONNECTOR_SURFACE_ID
            assert payload["asset_lane"] == "stock_etf_cash"
            assert payload["broker"] == "ibkr"
        if "accepted" in payload:
            assert payload["accepted"] is False
        if "attestation_accepted" in payload:
            assert payload["attestation_accepted"] is False
        if "status" in payload:
            assert payload["status"] in {"blocked_source_only", "BLOCKED"}
        assert "phase2_gate_not_accepted" in payload["blockers"]
        assert len(payload["blockers"]) == len(set(payload["blockers"]))
        for key in SIDE_EFFECT_FALSE_KEYS.intersection(payload):
            assert payload[key] is False, f"{name}.{key}"

    assert "connection_plan_blocked" in payloads["connection_plan"][0]["blockers"]
    assert "account_snapshot_blocked" in payloads["account_snapshot"][0]["blockers"]
    assert "market_data_blocked" in payloads["market_data"][0]["blockers"]
    assert "contract_details_blocked" in payloads["contract_details"][0]["blockers"]
    assert "paper_lifecycle_runtime_blocked" in payloads["paper_lifecycle"][0]["blockers"]
    assert "rust_authority_required" in payloads["paper_lifecycle"][0]["blockers"]
    assert payloads["paper_lifecycle"][0]["rust_authority_required"] is True
    assert "fill_import_runtime_blocked" in payloads["fill_import"][0]["blockers"]
    assert (
        "stock_etf_paper_fill_import_request_required"
        in payloads["fill_import"][0]["blockers"]
    )
    assert (
        payloads["session_attestation"][0]["expected_contract_id"]
        == IBKR_SESSION_ATTESTATION_CONTRACT_ID
    )
    assert "session_attestation_blocked_source_only" in payloads[
        "session_attestation"
    ][0]["blockers"]
    assert (
        payloads["paper_attestation"][0]["expected_contract_id"]
        == IBKR_PAPER_ATTESTATION_CONTRACT_ID
    )
    assert "paper_attestation_blocked_source_only" in payloads[
        "paper_attestation"
    ][0]["blockers"]
    assert "paper_session_attestation_missing" in payloads[
        "paper_attestation"
    ][0]["blockers"]

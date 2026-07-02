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
    IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    IbkrPaperAttestationPreview,
    IbkrPaperClientBoundary,
    IbkrReadOnlyClient,
    IbkrReadOnlyEndpointConfig,
    IbkrReadOnlyProbeResultImportPreview,
    IbkrSessionAttestationPreview,
)
from program_code.broker_connectors.ibkr_connector.fixtures import (  # noqa: E402
    blocked_paper_attestation_fixture,
    blocked_readonly_probe_result_import_fixture,
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
IBKR_CONNECTOR_README = IBKR_CONNECTOR_DIR / "README.md"

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

READONLY_PROBE_RESULT_IMPORT_KEYS = {
    "accepted_for_import",
    "asset_lane",
    "blockers",
    "broker",
    "bybit_path_reused",
    "connector_runtime_started",
    "contract_id",
    "db_apply_performed",
    "environment",
    "evidence_writer_started",
    "ibkr_contact_performed",
    "live_or_tiny_live_authorized",
    "network_contact_performed",
    "order_routed",
    "paper_order_submitted",
    "request_artifact_present",
    "request_validated",
    "result_import_performed",
    "scorecard_writer_started",
    "secret_content_loaded",
    "secret_content_serialized",
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
    "accepted_for_import",
    "account_snapshot_loaded",
    "broker_write_authority",
    "bybit_path_reused",
    "connector_runtime_started",
    "contract_details_loaded",
    "db_apply_authority",
    "db_apply_performed",
    "evidence_writer_started",
    "fill_import_readiness",
    "ibkr_contact_performed",
    "live_channel_exposed",
    "live_or_tiny_live_authorized",
    "market_data_loaded",
    "network_contact_allowed",
    "network_contact_performed",
    "order_write_method_present",
    "order_routed",
    "paper_channel_exposed",
    "paper_lifecycle_readiness",
    "paper_order_submitted",
    "paper_account_attestation_present",
    "python_broker_write_authority",
    "python_import_side_effects",
    "request_artifact_present",
    "request_validated",
    "result_import_performed",
    "scorecard_writer_started",
    "secret_content_loaded",
    "secret_content_serialized",
    "session_attestation_present",
}
RISKY_CONFIG_BLOCKERS = (
    "host_not_loopback",
    "port_not_reserved_paper_tws",
    "network_contact_requested",
    "secret_material_requested",
    "paper_channel_requested",
    "live_channel_requested",
    "bybit_path_reused",
    "account_fingerprint_present_before_phase2",
    "secret_fingerprint_present_before_phase2",
)
EXPECTED_DEFAULT_BLOCKERS = {
    "connection_plan": (
        "phase2_gate_not_accepted",
        "connection_plan_blocked",
    ),
    "readiness": ("phase2_gate_not_accepted",),
    "account_snapshot": (
        "phase2_gate_not_accepted",
        "account_snapshot_blocked",
    ),
    "market_data": (
        "phase2_gate_not_accepted",
        "market_data_blocked",
    ),
    "contract_details": (
        "phase2_gate_not_accepted",
        "contract_details_blocked",
    ),
    "session_attestation": (
        "phase2_gate_not_accepted",
        "session_attestation_blocked_source_only",
    ),
    "readonly_probe_result_import": (
        "phase2_gate_not_accepted",
        "probe_result_import_request_blocked_source_only",
        "probe_result_import_request_artifact_missing",
    ),
    "paper_lifecycle": (
        "phase2_gate_not_accepted",
        "paper_lifecycle_runtime_blocked",
        "rust_authority_required",
        "paper_session_attestation_missing",
    ),
    "fill_import": (
        "phase2_gate_not_accepted",
        "fill_import_runtime_blocked",
        "stock_etf_paper_fill_import_request_required",
    ),
    "paper_attestation": (
        "phase2_gate_not_accepted",
        "paper_attestation_blocked_source_only",
        "paper_session_attestation_missing",
    ),
    "fixture": ("phase2_gate_not_accepted",),
    "session_fixture": (
        "phase2_gate_not_accepted",
        "session_attestation_blocked_source_only",
    ),
    "readonly_probe_result_import_fixture": (
        "phase2_gate_not_accepted",
        "probe_result_import_request_blocked_source_only",
        "probe_result_import_request_artifact_missing",
    ),
    "paper_fixture": (
        "phase2_gate_not_accepted",
        "paper_attestation_blocked_source_only",
        "paper_session_attestation_missing",
    ),
}
EXPECTED_CONNECTOR_EXPORTS = (
    "IBKR_CONNECTOR_SURFACE_ID",
    "IBKR_NON_BYBIT_API_ALLOWLIST_CONTRACT_ID",
    "IBKR_PAPER_ATTESTATION_CONTRACT_ID",
    "IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID",
    "IBKR_SESSION_ATTESTATION_CONTRACT_ID",
    "IbkrApiActionMatrixPreview",
    "IbkrPaperAttestationPreview",
    "IbkrPaperClientBoundary",
    "IbkrReadOnlyClient",
    "IbkrReadOnlyEndpointConfig",
    "IbkrReadOnlyProbeResultImportPreview",
    "IbkrReadOnlySurfaceStatus",
    "IbkrSessionAttestationPreview",
)
EXPECTED_READONLY_CLIENT_PUBLIC_SURFACE = {
    "account_snapshot_preview",
    "api_action_matrix_preview",
    "config",
    "connection_plan",
    "contract_details_preview",
    "market_data_preview",
    "readiness",
    "readonly_probe_result_import_request_preview",
    "session_attestation_preview",
}
EXPECTED_PAPER_CLIENT_PUBLIC_SURFACE = {
    "fill_import_readiness",
    "lifecycle_readiness",
    "paper_attestation_preview",
}
EXPECTED_README_REQUIRED_BOUNDARY_LINES = {
    "It is not a runtime IBKR connector.",
    "- typed blocked readiness payloads",
    "- non-secret loopback endpoint descriptors",
    "- display-only non-Bybit API action matrix previews",
    "- display-only account, market-data, contract-detail, lifecycle, and fill-import previews",
    "- display-only session and paper attestation previews",
    "- display-only readonly probe result-import request previews",
    "- static fixtures for tests",
    "- IBKR SDK imports",
    "- socket or HTTP network contact",
    "- secret reads, env secret fallback, or serialized credential material",
    "- broker write methods",
    "- paper order routing, fill import side effects, DB writes, tiny-live, or live",
    "Rust gates remain the authority for any future read-only or paper capability.",
}
FORBIDDEN_README_RUNTIME_CLAIMS = {
    "runtime-ready",
    "runtime ready",
    "ready for runtime",
    "secret slot",
    "secret-slot ready",
    "live ready",
    "tiny-live ready",
    "paper order ready",
    "place_order",
    "submit_order",
    "cancel_order",
    "replace_order",
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


def _expected_risky_blockers(surface_name: str) -> list[str]:
    return list(EXPECTED_DEFAULT_BLOCKERS[surface_name] + RISKY_CONFIG_BLOCKERS)


def test_ibkr_connector_package_exports_only_source_boundary_types() -> None:
    assert tuple(ibkr_connector.__all__) == EXPECTED_CONNECTOR_EXPORTS
    for name in EXPECTED_CONNECTOR_EXPORTS:
        assert getattr(ibkr_connector, name) is not None
    assert IBKR_SESSION_ATTESTATION_CONTRACT_ID == "ibkr_session_attestation_v1"
    assert IBKR_PAPER_ATTESTATION_CONTRACT_ID == "ibkr_paper_attestation_v1"
    assert (
        IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
        == "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    )


def test_ibkr_connector_readme_preserves_source_only_boundary() -> None:
    source = IBKR_CONNECTOR_README.read_text(encoding="utf-8")
    lower_source = source.lower()

    assert IBKR_CONNECTOR_README.exists()
    for line in EXPECTED_README_REQUIRED_BOUNDARY_LINES:
        assert line in source
    for claim in FORBIDDEN_README_RUNTIME_CLAIMS:
        assert claim not in lower_source


def test_ibkr_connector_skeleton_has_no_python_broker_write_methods() -> None:
    for cls in (IbkrReadOnlyClient, IbkrPaperClientBoundary):
        assert sorted(FORBIDDEN_WRITE_METHODS.intersection(dir(cls))) == []
    assert IbkrSessionAttestationPreview().attestation_accepted is False
    assert IbkrPaperAttestationPreview().accepted is False
    assert IbkrReadOnlyProbeResultImportPreview().accepted_for_import is False
    assert IbkrReadOnlyProbeResultImportPreview().result_import_performed is False


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
    assert status["blockers"] == list(EXPECTED_DEFAULT_BLOCKERS["readiness"])


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

    blockers = list(config.validate_source_boundary())

    assert blockers == list(RISKY_CONFIG_BLOCKERS)


def test_ibkr_connector_config_blocker_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")
    source_under_test = source.split(
        "def test_ibkr_connector_config_blocker_assertions_stay_exact",
        1,
    )[0]
    forbidden_patterns = [
        "issubset(blockers)",
        "set(config.validate_source_boundary())",
    ]
    for pattern in forbidden_patterns:
        assert pattern not in source_under_test


def test_ibkr_connector_previews_remain_display_only() -> None:
    client = IbkrReadOnlyClient()
    paper = IbkrPaperClientBoundary()

    for payload in (
        client.connection_plan(),
        client.account_snapshot_preview(),
        client.market_data_preview(),
        client.contract_details_preview(),
        client.session_attestation_preview(),
        client.readonly_probe_result_import_request_preview(),
        paper.lifecycle_readiness(),
        paper.fill_import_readiness(),
        paper.paper_attestation_preview(),
        blocked_readonly_fixture(),
        blocked_session_attestation_fixture(),
        blocked_readonly_probe_result_import_fixture(),
        blocked_paper_attestation_fixture(),
    ):
        assert payload.get("network_contact_performed") is False
        assert payload.get("secret_content_loaded") is False
        assert payload.get("secret_content_serialized", False) is False
        assert payload.get("bybit_path_reused") is False
        assert payload.get("order_write_method_present", False) is False
        assert payload.get("result_import_performed", False) is False


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
        "readonly_probe_result_import": (
            client.readonly_probe_result_import_request_preview(),
            READONLY_PROBE_RESULT_IMPORT_KEYS,
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
        "readonly_probe_result_import_fixture": (
            blocked_readonly_probe_result_import_fixture(),
            READONLY_PROBE_RESULT_IMPORT_KEYS,
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
            assert payload["status"] in {
                "blocked_source_only",
                "BLOCKED",
                "blocked_no_result_import_request_artifact",
            }
        if payload.get("contract_id") == IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID:
            assert payload["asset_lane"] == "stock_etf_cash"
            assert payload["broker"] == "ibkr"
            assert payload["environment"] == "read_only"
            assert payload["source_version"] == 1
        assert payload["blockers"] == list(EXPECTED_DEFAULT_BLOCKERS[name])
        for key in SIDE_EFFECT_FALSE_KEYS.intersection(payload):
            assert payload[key] is False, f"{name}.{key}"

    assert payloads["connection_plan"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["connection_plan"]
    )
    assert payloads["account_snapshot"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["account_snapshot"]
    )
    assert payloads["market_data"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["market_data"]
    )
    assert payloads["contract_details"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["contract_details"]
    )
    assert payloads["paper_lifecycle"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["paper_lifecycle"]
    )
    assert payloads["paper_lifecycle"][0]["rust_authority_required"] is True
    assert payloads["fill_import"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["fill_import"]
    )
    assert (
        payloads["session_attestation"][0]["expected_contract_id"]
        == IBKR_SESSION_ATTESTATION_CONTRACT_ID
    )
    assert payloads["session_attestation"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["session_attestation"]
    )
    assert (
        payloads["readonly_probe_result_import"][0]["contract_id"]
        == IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
    )
    assert payloads["readonly_probe_result_import"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["readonly_probe_result_import"]
    )
    assert (
        payloads["paper_attestation"][0]["expected_contract_id"]
        == IBKR_PAPER_ATTESTATION_CONTRACT_ID
    )
    assert payloads["paper_attestation"][0]["blockers"] == list(
        EXPECTED_DEFAULT_BLOCKERS["paper_attestation"]
    )


def test_ibkr_connector_preview_blocker_assertions_stay_exact() -> None:
    source = Path(__file__).read_text(encoding="utf-8")

    forbidden_patterns = tuple(
        "".join(parts)
        for parts in (
            (
                '"phase2_gate_not_accepted"',
                " in status",
                '["blockers"]',
            ),
            (
                "in payload",
                '["blockers"]',
            ),
            (
                "in payloads",
                '["',
            ),
            (
                "blockers = set(",
                "payload",
                '["blockers"])',
            ),
            ("RISKY_CONFIG_BLOCKERS", ".issubset"),
        )
    )

    for pattern in forbidden_patterns:
        assert pattern not in source


def test_ibkr_connector_risky_config_only_expands_blockers() -> None:
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
    client = IbkrReadOnlyClient(config)
    paper = IbkrPaperClientBoundary(config)

    payloads = {
        "connection_plan": client.connection_plan(),
        "readiness": client.readiness().to_dict(),
        "account_snapshot": client.account_snapshot_preview(),
        "market_data": client.market_data_preview(),
        "contract_details": client.contract_details_preview(),
        "session_attestation": client.session_attestation_preview(),
        "readonly_probe_result_import": (
            client.readonly_probe_result_import_request_preview()
        ),
        "paper_lifecycle": paper.lifecycle_readiness(),
        "fill_import": paper.fill_import_readiness(),
        "paper_attestation": paper.paper_attestation_preview(),
    }

    for name, payload in payloads.items():
        assert payload["blockers"] == _expected_risky_blockers(name), name
        if "accepted" in payload:
            assert payload["accepted"] is False
        if "attestation_accepted" in payload:
            assert payload["attestation_accepted"] is False
        for key in SIDE_EFFECT_FALSE_KEYS.intersection(payload):
            assert payload[key] is False, f"{name}.{key}"

from __future__ import annotations

"""
Stock/ETF IBKR readiness router.

This router is intentionally display-only. It may query the local Rust IPC
fixture for `stock_etf.get_readiness`, but it never creates secret slots,
contacts IBKR, or exposes paper/live order actions.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, Response
from fastapi.responses import RedirectResponse

from . import main_legacy as base
from .ipc_client import EngineIPCClient

logger = logging.getLogger(__name__)

stock_etf_router = APIRouter(
    prefix="/api/v1/stock-etf",
    tags=["Stock ETF IBKR / 股票 ETF IBKR"],
)

_IPC_CLIENT: EngineIPCClient | None = None
_LANE_STATUS_METHOD = "stock_etf.get_lane_status"
_READINESS_METHOD = "stock_etf.get_readiness"
_EVIDENCE_STATUS_METHOD = "stock_etf.get_evidence_status"
_UNIVERSE_STATUS_METHOD = "stock_etf.get_universe_status"
_API_ALLOWLIST_CONTRACT_ID = "non_bybit_api_allowlist_v1"
_API_ALLOWLIST_SOURCE_VERSION = 1
_API_ALLOWLIST_READ_ACTION_COUNT = 10
_API_ALLOWLIST_PAPER_WRITE_ACTION_COUNT = 3
_API_ALLOWLIST_DENIED_ACTION_COUNT = 10
_MARKET_DATA_PROVENANCE_CONTRACT_ID = "stock_market_data_provenance_v1"
_EVIDENCE_CLOCK_CONTRACT_ID = "stock_etf_evidence_clock_v1"
_PIT_UNIVERSE_CONTRACT_ID = "stock_etf_pit_universe_contract_v1"
_DENIED_OPERATIONS: tuple[str, ...] = (
    "ibkr_live_order_submit",
    "ibkr_tiny_live",
    "ibkr_margin_or_short",
    "ibkr_options_or_cfd",
    "ibkr_transfer_or_account_write",
    "ibkr_secret_slot_creation",
    "ibkr_api_contact_before_phase2_gate",
)
_NO_STORE_HEADERS: dict[str, str] = {
    "Cache-Control": "no-cache, no-store, private, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Authorization",
}
_SAFETY_FALSE_FIELDS: tuple[str, ...] = (
    "ibkr_live_enabled",
    "ibkr_call_performed",
    "secret_slot_touched",
    "order_routed",
    "bybit_ipc_reused",
)


def _apply_no_store_headers(response: Response) -> None:
    for key, value in _NO_STORE_HEADERS.items():
        response.headers[key] = value


def _phase2_fail_closed() -> dict[str, Any]:
    return {
        "external_surface_gate": {
            "status": "BLOCKED",
            "ibkr_contact_allowed": False,
            "blockers": ["ipc_unavailable"],
            "ibkr_call_performed": False,
        },
        "api_allowlist": {
            "contract_id": "",
            "source_version": 0,
            "accepted": False,
            "blockers": ["ipc_unavailable"],
            "read_action_count": 0,
            "paper_write_action_count": 0,
            "denied_action_count": 0,
            "ibkr_contact_performed": False,
            "secret_content_serialized": False,
            "bybit_live_execution_protected": False,
        },
        "policy_prerequisites": {
            "bundle_accepted": False,
            "blockers": ["ipc_unavailable"],
            "flags": {},
        },
        "immutable_pass_artifact_present": False,
        "first_ibkr_contact_allowed": False,
        "connector_enabled": False,
        "secret_slot_touched": False,
        "order_routed": False,
    }


def _readiness_fail_closed() -> dict[str, Any]:
    return {
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "default_asset_lane": "crypto_perp",
        "readonly_ready": False,
        "paper_ready": False,
        "shadow_only": True,
        "live_denied": True,
        "denial_reasons": ["ipc_unavailable"],
    }


def _market_data_provenance_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _MARKET_DATA_PROVENANCE_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
    }


def _evidence_clock_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _EVIDENCE_CLOCK_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "status": "NOT_STARTED",
        "accepted": False,
        "blockers": [reason],
        "checker_contacted_ibkr": False,
        "checker_started_connector_runtime": False,
        "checker_started_evidence_clock": False,
        "checker_wrote_scorecard": False,
        "checker_applied_db": False,
        "secret_content_serialized": False,
        "live_or_tiny_live_authorized": False,
        "ibkr_readonly_paper_connector_green_5d": False,
        "shadow_collector_green_5d": False,
    }


def _frozen_inputs_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "accepted": False,
        "blockers": [reason],
        "universe_hash_present": False,
        "benchmark_hash_present": False,
        "cost_model_hash_present": False,
        "strategy_hypothesis_hash_present": False,
        "reference_data_sources_contract_hash_present": False,
        "paper_shadow_divergence_threshold_hash_present": False,
        "gui_evidence_view_available": False,
        "daily_scorecard_regeneration_passed": False,
    }


def _dq_manifest_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "shape_accepted": False,
        "shape_blockers": [reason],
        "passes_day_quality": False,
        "trading_day": "",
        "calendar_aware_coverage_bps": 0,
        "symbol_completeness_bps": 0,
        "latency_dq_passed": False,
        "market_data_provenance_accepted": False,
        "scorecard_regeneration_passed": False,
    }


def _scorecard_fail_closed() -> dict[str, Any]:
    return {
        "writer_started": False,
        "db_apply_performed": False,
        "daily_scorecard_regeneration_passed": False,
    }


def _universe_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "expected_contract_id": _PIT_UNIVERSE_CONTRACT_ID,
        "contract_id": "",
        "source_version": 0,
        "accepted": False,
        "blockers": [reason],
        "universe_id": "",
        "universe_version": "",
        "universe_hash_present": False,
        "point_in_time_asof_ms": 0,
        "effective_from_ms": 0,
        "effective_to_ms": 0,
        "constituent_count": 0,
        "max_constituents": 0,
        "sample_constituents": [],
        "frozen_for_evidence_clock": False,
        "survivorship_bias_controls_present": False,
        "bybit_live_execution_unchanged": True,
        "ibkr_live_denied": True,
        "ibkr_contact_performed": False,
        "secret_content_serialized": False,
    }


async def _get_ipc() -> EngineIPCClient | None:
    global _IPC_CLIENT
    if _IPC_CLIENT is None:
        client = EngineIPCClient()
        try:
            connected = await client.connect()
        except Exception as exc:
            logger.warning("stock_etf: IPC connect failed: %s", exc)
            return None
        if not connected or not client.is_connected:
            logger.warning("stock_etf: IPC connect returned disconnected client")
            return None
        _IPC_CLIENT = client
    return _IPC_CLIENT


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_str(value: Any, default: str) -> str:
    return value if isinstance(value, str) and value else default


def _as_bool(value: Any) -> bool:
    return value is True


def _as_int(value: Any) -> int:
    return value if type(value) is int else 0


def _normalize_feature_flags(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "stock_etf_lane_enabled": _as_bool(source.get("stock_etf_lane_enabled")),
        "ibkr_readonly_enabled": _as_bool(source.get("ibkr_readonly_enabled")),
        "ibkr_paper_enabled": _as_bool(source.get("ibkr_paper_enabled")),
        "asset_lane_default": _as_str(source.get("asset_lane_default"), "crypto_perp"),
        "stock_etf_shadow_only": source.get("stock_etf_shadow_only") is not False,
    }


def _normalize_api_allowlist(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "read_action_count": _as_int(source.get("read_action_count")),
        "paper_write_action_count": _as_int(source.get("paper_write_action_count")),
        "denied_action_count": _as_int(source.get("denied_action_count")),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "bybit_live_execution_protected": _as_bool(
            source.get("bybit_live_execution_protected")
        ),
    }


def _normalize_market_data_provenance(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _market_data_provenance_fail_closed(reason or "missing_market_data_provenance")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _MARKET_DATA_PROVENANCE_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(source.get("connector_runtime_started")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
    }


def _normalize_evidence_clock(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _evidence_clock_fail_closed(reason or "missing_evidence_clock")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _EVIDENCE_CLOCK_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "status": _as_str(source.get("status"), "NOT_STARTED"),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "checker_contacted_ibkr": _as_bool(source.get("checker_contacted_ibkr")),
        "checker_started_connector_runtime": _as_bool(
            source.get("checker_started_connector_runtime")
        ),
        "checker_started_evidence_clock": _as_bool(
            source.get("checker_started_evidence_clock")
        ),
        "checker_wrote_scorecard": _as_bool(source.get("checker_wrote_scorecard")),
        "checker_applied_db": _as_bool(source.get("checker_applied_db")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
        "ibkr_readonly_paper_connector_green_5d": _as_bool(
            source.get("ibkr_readonly_paper_connector_green_5d")
        ),
        "shadow_collector_green_5d": _as_bool(source.get("shadow_collector_green_5d")),
    }


def _normalize_frozen_inputs(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _frozen_inputs_fail_closed(reason or "missing_frozen_inputs")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "universe_hash_present": _as_bool(source.get("universe_hash_present")),
        "benchmark_hash_present": _as_bool(source.get("benchmark_hash_present")),
        "cost_model_hash_present": _as_bool(source.get("cost_model_hash_present")),
        "strategy_hypothesis_hash_present": _as_bool(
            source.get("strategy_hypothesis_hash_present")
        ),
        "reference_data_sources_contract_hash_present": _as_bool(
            source.get("reference_data_sources_contract_hash_present")
        ),
        "paper_shadow_divergence_threshold_hash_present": _as_bool(
            source.get("paper_shadow_divergence_threshold_hash_present")
        ),
        "gui_evidence_view_available": _as_bool(
            source.get("gui_evidence_view_available")
        ),
        "daily_scorecard_regeneration_passed": _as_bool(
            source.get("daily_scorecard_regeneration_passed")
        ),
    }


def _normalize_dq_manifest(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _dq_manifest_fail_closed(reason or "missing_dq_manifest")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "shape_accepted": _as_bool(source.get("shape_accepted")),
        "shape_blockers": [str(item) for item in _as_list(source.get("shape_blockers"))],
        "passes_day_quality": _as_bool(source.get("passes_day_quality")),
        "trading_day": _as_str(source.get("trading_day"), ""),
        "calendar_aware_coverage_bps": _as_int(source.get("calendar_aware_coverage_bps")),
        "symbol_completeness_bps": _as_int(source.get("symbol_completeness_bps")),
        "latency_dq_passed": _as_bool(source.get("latency_dq_passed")),
        "market_data_provenance_accepted": _as_bool(
            source.get("market_data_provenance_accepted")
        ),
        "scorecard_regeneration_passed": _as_bool(
            source.get("scorecard_regeneration_passed")
        ),
    }


def _normalize_scorecard(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    if not source:
        return _scorecard_fail_closed()
    return {
        "writer_started": _as_bool(source.get("writer_started")),
        "db_apply_performed": _as_bool(source.get("db_apply_performed")),
        "daily_scorecard_regeneration_passed": _as_bool(
            source.get("daily_scorecard_regeneration_passed")
        ),
    }


def _normalize_universe_contract(value: Any, reason: str | None) -> dict[str, Any]:
    fallback = _universe_fail_closed(reason or "missing_pit_universe")
    source = _as_dict(value)
    if not source:
        return fallback
    return {
        "expected_contract_id": _as_str(
            source.get("expected_contract_id"),
            _PIT_UNIVERSE_CONTRACT_ID,
        ),
        "contract_id": _as_str(source.get("contract_id"), ""),
        "source_version": _as_int(source.get("source_version")),
        "accepted": _as_bool(source.get("accepted")),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))],
        "universe_id": _as_str(source.get("universe_id"), ""),
        "universe_version": _as_str(source.get("universe_version"), ""),
        "universe_hash_present": _as_bool(source.get("universe_hash_present")),
        "point_in_time_asof_ms": _as_int(source.get("point_in_time_asof_ms")),
        "effective_from_ms": _as_int(source.get("effective_from_ms")),
        "effective_to_ms": _as_int(source.get("effective_to_ms")),
        "constituent_count": _as_int(source.get("constituent_count")),
        "max_constituents": _as_int(source.get("max_constituents")),
        "sample_constituents": [
            _as_dict(item) for item in _as_list(source.get("sample_constituents"))
        ],
        "frozen_for_evidence_clock": _as_bool(source.get("frozen_for_evidence_clock")),
        "survivorship_bias_controls_present": _as_bool(
            source.get("survivorship_bias_controls_present")
        ),
        "bybit_live_execution_unchanged": _as_bool(
            source.get("bybit_live_execution_unchanged")
        ),
        "ibkr_live_denied": source.get("ibkr_live_denied") is not False,
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
    }


def _api_allowlist_contract_violations(api_allowlist: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    if not _as_bool(api_allowlist.get("accepted")):
        violations.append("api_allowlist_not_accepted")
    if _as_str(api_allowlist.get("contract_id"), "") != _API_ALLOWLIST_CONTRACT_ID:
        violations.append("api_allowlist_contract_id_mismatch")
    if _as_int(api_allowlist.get("source_version")) != _API_ALLOWLIST_SOURCE_VERSION:
        violations.append("api_allowlist_source_version_mismatch")
    if _as_int(api_allowlist.get("read_action_count")) != _API_ALLOWLIST_READ_ACTION_COUNT:
        violations.append("api_allowlist_read_action_count_mismatch")
    if (
        _as_int(api_allowlist.get("paper_write_action_count"))
        != _API_ALLOWLIST_PAPER_WRITE_ACTION_COUNT
    ):
        violations.append("api_allowlist_paper_write_action_count_mismatch")
    if _as_int(api_allowlist.get("denied_action_count")) != _API_ALLOWLIST_DENIED_ACTION_COUNT:
        violations.append("api_allowlist_denied_action_count_mismatch")
    if _as_bool(api_allowlist.get("ibkr_contact_performed")):
        violations.append("api_allowlist_ibkr_contact_performed")
    if _as_bool(api_allowlist.get("secret_content_serialized")):
        violations.append("api_allowlist_secret_content_serialized")
    if not _as_bool(api_allowlist.get("bybit_live_execution_protected")):
        violations.append("api_allowlist_bybit_live_not_protected")
    return violations


def _normalize_readiness(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    readiness = _as_dict(source.get("readiness")) or _readiness_fail_closed()
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))

    contract_violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if reason is None:
        contract_violations.extend(_api_allowlist_contract_violations(api_allowlist))
    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    readiness_state = "phase2_blocked"
    if contract_violations:
        readiness_state = "contract_violation_blocked"
    elif reason is not None:
        readiness_state = "degraded"
    elif first_contact_allowed and _as_bool(readiness.get("paper_ready")):
        readiness_state = "paper_ready"
    elif first_contact_allowed and _as_bool(readiness.get("readonly_ready")):
        readiness_state = "readonly_ready"

    denial_reasons = [
        str(item) for item in _as_list(readiness.get("denial_reasons"))
    ]
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in denial_reasons:
        denial_reasons.append(reason)

    degraded = reason is not None or bool(contract_violations)
    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "default_asset_lane": _as_str(readiness.get("default_asset_lane"), "crypto_perp"),
        "gui_authority": "display_only",
        "readiness_state": readiness_state,
        "source_readiness": {
            "asset_lane": _as_str(readiness.get("asset_lane"), "stock_etf_cash"),
            "broker": _as_str(readiness.get("broker"), "ibkr"),
            "default_asset_lane": _as_str(readiness.get("default_asset_lane"), "crypto_perp"),
            "readonly_ready": _as_bool(readiness.get("readonly_ready")),
            "paper_ready": _as_bool(readiness.get("paper_ready")),
            "shadow_only": _as_bool(readiness.get("shadow_only")),
            "live_denied": readiness.get("live_denied") is not False,
            "denial_reasons": denial_reasons,
        },
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_readiness"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": _as_bool(source.get("ibkr_call_performed")),
        "secret_slot_touched": _as_bool(source.get("secret_slot_touched")),
        "order_routed": _as_bool(source.get("order_routed")),
        "bybit_ipc_reused": _as_bool(source.get("bybit_ipc_reused")),
        "contract_violations": contract_violations,
        "degraded": degraded,
        "reason": reason,
    }


def _normalize_lane_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    flags = _normalize_feature_flags(source.get("flags"))

    contract_violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        contract_violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        contract_violations.append("broker_mismatch")
    if reason is None:
        contract_violations.extend(_api_allowlist_contract_violations(api_allowlist))

    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "phase2_blocked"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "default_asset_lane": _as_str(
            source.get("default_asset_lane"), flags["asset_lane_default"]
        ),
        "gui_authority": "display_only",
        "lane_status_state": status_state,
        "flags": flags,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_lane_status", "refresh_readiness"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": _as_bool(source.get("ibkr_call_performed")),
        "secret_slot_touched": _as_bool(source.get("secret_slot_touched")),
        "order_routed": _as_bool(source.get("order_routed")),
        "bybit_ipc_reused": _as_bool(source.get("bybit_ipc_reused")),
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }


def _evidence_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    market_data_provenance: dict[str, Any],
    evidence_clock: dict[str, Any],
    frozen_inputs: dict[str, Any],
    scorecard: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper") != "paper":
        violations.append("environment_mismatch")
    if _as_bool(source.get("phase3_started")):
        violations.append("phase3_started")
    if _as_str(market_data_provenance.get("expected_contract_id"), "") != (
        _MARKET_DATA_PROVENANCE_CONTRACT_ID
    ):
        violations.append("market_data_expected_contract_id_mismatch")
    if _as_bool(market_data_provenance.get("ibkr_contact_performed")):
        violations.append("market_data_ibkr_contact_performed")
    if _as_bool(market_data_provenance.get("connector_runtime_started")):
        violations.append("market_data_connector_runtime_started")
    if _as_bool(market_data_provenance.get("secret_content_serialized")):
        violations.append("market_data_secret_content_serialized")
    if _as_bool(market_data_provenance.get("live_or_tiny_live_authorized")):
        violations.append("market_data_live_or_tiny_live_authorized")
    if _as_str(evidence_clock.get("expected_contract_id"), "") != _EVIDENCE_CLOCK_CONTRACT_ID:
        violations.append("evidence_clock_expected_contract_id_mismatch")
    if _as_bool(evidence_clock.get("checker_contacted_ibkr")):
        violations.append("evidence_clock_contacted_ibkr")
    if _as_bool(evidence_clock.get("checker_started_connector_runtime")):
        violations.append("evidence_clock_started_connector_runtime")
    if _as_bool(evidence_clock.get("checker_started_evidence_clock")):
        violations.append("evidence_clock_started")
    if _as_bool(evidence_clock.get("checker_wrote_scorecard")):
        violations.append("evidence_clock_wrote_scorecard")
    if _as_bool(evidence_clock.get("checker_applied_db")):
        violations.append("evidence_clock_applied_db")
    if _as_bool(evidence_clock.get("secret_content_serialized")):
        violations.append("evidence_clock_secret_content_serialized")
    if _as_bool(evidence_clock.get("live_or_tiny_live_authorized")):
        violations.append("evidence_clock_live_or_tiny_live_authorized")
    if _as_bool(frozen_inputs.get("daily_scorecard_regeneration_passed")):
        violations.append("frozen_inputs_daily_scorecard_regenerated")
    if _as_bool(scorecard.get("writer_started")):
        violations.append("scorecard_writer_started")
    if _as_bool(scorecard.get("db_apply_performed")):
        violations.append("scorecard_db_apply_performed")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_evidence_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    market_data_provenance = _normalize_market_data_provenance(
        source.get("market_data_provenance"),
        reason,
    )
    evidence_clock = _normalize_evidence_clock(source.get("evidence_clock"), reason)
    frozen_inputs = _normalize_frozen_inputs(source.get("frozen_inputs"), reason)
    dq_manifest = _normalize_dq_manifest(source.get("dq_manifest"), reason)
    scorecard = _normalize_scorecard(source.get("scorecard"))

    contract_violations = _evidence_status_contract_violations(
        source,
        phase2,
        market_data_provenance,
        evidence_clock,
        frozen_inputs,
        scorecard,
        reason,
    )
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "blocked"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"
    elif _as_str(source.get("evidence_status_state"), "blocked") == "green":
        status_state = "blocked"

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "gui_authority": "display_only",
        "evidence_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase3_evidence_status_source_fixture"),
        "phase3_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "market_data_provenance": market_data_provenance,
        "evidence_clock": evidence_clock,
        "frozen_inputs": frozen_inputs,
        "dq_manifest": dq_manifest,
        "scorecard": scorecard,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_evidence_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "evidence_clock_started": False,
        "scorecard_writer_started": False,
        "db_apply_performed": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }


def _universe_status_contract_violations(
    source: dict[str, Any],
    phase2: dict[str, Any],
    universe: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if _as_str(source.get("asset_lane"), "stock_etf_cash") != "stock_etf_cash":
        violations.append("asset_lane_mismatch")
    if _as_str(source.get("broker"), "ibkr") != "ibkr":
        violations.append("broker_mismatch")
    if _as_str(source.get("environment"), "paper") != "paper":
        violations.append("environment_mismatch")
    if _as_bool(source.get("phase3_started")):
        violations.append("phase3_started")
    if _as_bool(source.get("collector_started")):
        violations.append("collector_started")
    if _as_bool(source.get("market_data_ingestion_started")):
        violations.append("market_data_ingestion_started")
    if _as_bool(source.get("db_apply_performed")):
        violations.append("db_apply_performed")
    if _as_str(universe.get("expected_contract_id"), "") != _PIT_UNIVERSE_CONTRACT_ID:
        violations.append("universe_expected_contract_id_mismatch")
    if _as_bool(universe.get("ibkr_contact_performed")):
        violations.append("universe_ibkr_contact_performed")
    if _as_bool(universe.get("secret_content_serialized")):
        violations.append("universe_secret_content_serialized")
    if not _as_bool(universe.get("bybit_live_execution_unchanged")):
        violations.append("universe_bybit_live_not_protected")
    if not _as_bool(universe.get("ibkr_live_denied")):
        violations.append("universe_ibkr_live_not_denied")
    if reason is None:
        api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
        violations.extend(_api_allowlist_contract_violations(api_allowlist))
    return violations


def _normalize_universe_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    universe = _normalize_universe_contract(source.get("universe"), reason)

    contract_violations = _universe_status_contract_violations(
        source,
        phase2,
        universe,
        reason,
    )
    blockers = [
        str(item) for item in _as_list(external_surface_gate.get("blockers"))
    ]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    status_state = "blocked"
    if contract_violations:
        status_state = "contract_violation_blocked"
    elif reason is not None:
        status_state = "degraded"
    elif _as_bool(universe.get("accepted")):
        status_state = "source_ready"

    first_contact_allowed = _as_bool(phase2.get("first_ibkr_contact_allowed"))
    immutable_artifact = _as_bool(phase2.get("immutable_pass_artifact_present"))
    connector_enabled = _as_bool(phase2.get("connector_enabled"))

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "environment": "paper",
        "gui_authority": "display_only",
        "universe_status_state": status_state,
        "phase": _as_str(source.get("phase"), "phase3_universe_status_source_fixture"),
        "phase3_started": False,
        "phase2": phase2,
        "api_allowlist": api_allowlist,
        "phase2_gate_status": _as_str(external_surface_gate.get("status"), "BLOCKED"),
        "phase2_gate_blockers": blockers,
        "first_ibkr_contact_allowed": first_contact_allowed,
        "immutable_pass_artifact_present": immutable_artifact,
        "connector_enabled": connector_enabled,
        "universe": universe,
        "ibkr_live_enabled": False,
        "stock_live_disabled": True,
        "paper_order_entry_visible": False,
        "allowed_gui_actions": ["refresh_universe_status"],
        "denied_operations": list(_DENIED_OPERATIONS),
        "ibkr_call_performed": False,
        "secret_slot_touched": False,
        "order_routed": False,
        "bybit_ipc_reused": False,
        "collector_started": False,
        "market_data_ingestion_started": False,
        "db_apply_performed": False,
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }


async def _query_stock_etf_lane_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_LANE_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _LANE_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_readiness(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_READINESS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _READINESS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_evidence_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_EVIDENCE_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _EVIDENCE_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


async def _query_stock_etf_universe_status(
    ipc: EngineIPCClient | None,
) -> tuple[dict[str, Any], str | None]:
    if ipc is None:
        return ({}, "ipc_unavailable")
    try:
        raw = await ipc.call(_UNIVERSE_STATUS_METHOD, params={})
    except Exception as exc:
        logger.warning("stock_etf: %s failed: %s", _UNIVERSE_STATUS_METHOD, exc)
        return ({}, f"ipc_error:{type(exc).__name__}")
    return (raw if isinstance(raw, dict) else {}, None)


@stock_etf_router.get("/lane-status")
async def get_stock_etf_lane_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF lane-status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_lane_status(ipc)
    return {
        "ok": True,
        "data": _normalize_lane_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_lane_status",
    }


@stock_etf_router.get("/readiness")
async def get_stock_etf_readiness(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF IBKR readiness surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_readiness(ipc)
    return {
        "ok": True,
        "data": _normalize_readiness(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_readiness",
    }


@stock_etf_router.get("/evidence-status")
async def get_stock_etf_evidence_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF evidence-status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_evidence_status(ipc)
    return {
        "ok": True,
        "data": _normalize_evidence_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_evidence_status",
    }


@stock_etf_router.get("/universe-status")
async def get_stock_etf_universe_status(
    response: Response,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only Stock/ETF PIT-universe status surface for the GUI."""
    del actor
    _apply_no_store_headers(response)
    ipc = await _get_ipc()
    raw, reason = await _query_stock_etf_universe_status(ipc)
    return {
        "ok": True,
        "data": _normalize_universe_status(raw, reason),
        "is_simulated": False,
        "data_category": "stock_etf_universe_status",
    }


@stock_etf_router.get("", include_in_schema=False)
async def stock_etf_tab_redirect(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> RedirectResponse:
    del actor
    return RedirectResponse(url="/static/tab-stock-etf.html", headers=_NO_STORE_HEADERS)

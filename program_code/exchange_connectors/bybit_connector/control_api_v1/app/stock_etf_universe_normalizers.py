from __future__ import annotations

"""PIT-universe status normalizers for the Stock/ETF display-only surface."""

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _PIT_UNIVERSE_CONTRACT_ID,
    _SAFETY_FALSE_FIELDS,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
    _universe_fail_closed,
)

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

from __future__ import annotations

"""Readiness and lane-status normalizers for the Stock/ETF display-only surface."""

from typing import Any

from .stock_etf_status_common import (
    _DENIED_OPERATIONS,
    _SAFETY_FALSE_FIELDS,
    _api_allowlist_contract_violations,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
    _normalize_api_allowlist,
    _phase2_fail_closed,
    _readiness_fail_closed,
)

def _normalize_feature_flags(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    return {
        "stock_etf_lane_enabled": _as_bool(source.get("stock_etf_lane_enabled")),
        "ibkr_readonly_enabled": _as_bool(source.get("ibkr_readonly_enabled")),
        "ibkr_paper_enabled": _as_bool(source.get("ibkr_paper_enabled")),
        "asset_lane_default": _as_str(source.get("asset_lane_default"), "crypto_perp"),
        "stock_etf_shadow_only": source.get("stock_etf_shadow_only") is not False,
    }


def _connector_skeleton_fail_closed(reason: str = "phase2_gate_not_accepted") -> dict[str, Any]:
    return {
        "surface_id": "ibkr_stock_etf_readonly_connector_skeleton_v1",
        "accepted": False,
        "status": "blocked_source_only",
        "blockers": [reason],
        "network_contact_performed": False,
        "secret_content_loaded": False,
        "paper_channel_exposed": False,
        "live_channel_exposed": False,
        "order_write_method_present": False,
        "bybit_path_reused": False,
    }


def _readonly_probe_request_fail_closed(
    reason: str = "phase2_gate_not_accepted",
) -> dict[str, Any]:
    return {
        "contract_id": "stock_etf_ibkr_readonly_probe_request_v1",
        "source_version": 1,
        "request_artifact_present": False,
        "request_validated": False,
        "accepted_for_contact": False,
        "status": "blocked_no_request_artifact",
        "blockers": [reason, "probe_request_artifact_missing"],
        "ibkr_contact_performed": False,
        "connector_runtime_started": False,
        "secret_content_serialized": False,
        "order_routed": False,
        "paper_order_submitted": False,
        "db_apply_performed": False,
        "evidence_clock_started": False,
        "bybit_path_reused": False,
        "live_or_tiny_live_authorized": False,
    }


def _normalize_connector_skeleton(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    fallback = _connector_skeleton_fail_closed()
    return {
        "surface_id": _as_str(source.get("surface_id"), fallback["surface_id"]),
        "accepted": _as_bool(source.get("accepted")),
        "status": _as_str(source.get("status"), fallback["status"]),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))]
        or list(fallback["blockers"]),
        "network_contact_performed": _as_bool(source.get("network_contact_performed")),
        "secret_content_loaded": _as_bool(source.get("secret_content_loaded")),
        "paper_channel_exposed": _as_bool(source.get("paper_channel_exposed")),
        "live_channel_exposed": _as_bool(source.get("live_channel_exposed")),
        "order_write_method_present": _as_bool(source.get("order_write_method_present")),
        "bybit_path_reused": _as_bool(source.get("bybit_path_reused")),
    }


def _normalize_readonly_probe_request(value: Any) -> dict[str, Any]:
    source = _as_dict(value)
    fallback = _readonly_probe_request_fail_closed()
    return {
        "contract_id": _as_str(source.get("contract_id"), fallback["contract_id"]),
        "source_version": _as_int(source.get("source_version"))
        if source
        else fallback["source_version"],
        "request_artifact_present": _as_bool(source.get("request_artifact_present")),
        "request_validated": _as_bool(source.get("request_validated")),
        "accepted_for_contact": _as_bool(source.get("accepted_for_contact")),
        "status": _as_str(source.get("status"), fallback["status"]),
        "blockers": [str(item) for item in _as_list(source.get("blockers"))]
        or list(fallback["blockers"]),
        "ibkr_contact_performed": _as_bool(source.get("ibkr_contact_performed")),
        "connector_runtime_started": _as_bool(source.get("connector_runtime_started")),
        "secret_content_serialized": _as_bool(source.get("secret_content_serialized")),
        "order_routed": _as_bool(source.get("order_routed")),
        "paper_order_submitted": _as_bool(source.get("paper_order_submitted")),
        "db_apply_performed": _as_bool(source.get("db_apply_performed")),
        "evidence_clock_started": _as_bool(source.get("evidence_clock_started")),
        "bybit_path_reused": _as_bool(source.get("bybit_path_reused")),
        "live_or_tiny_live_authorized": _as_bool(
            source.get("live_or_tiny_live_authorized")
        ),
    }


def _normalize_readiness(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    readiness = _as_dict(source.get("readiness")) or _readiness_fail_closed()
    phase2 = _as_dict(source.get("phase2")) or _phase2_fail_closed()
    external_surface_gate = _as_dict(phase2.get("external_surface_gate"))
    api_allowlist = _normalize_api_allowlist(phase2.get("api_allowlist"))
    readonly_probe_request = _normalize_readonly_probe_request(
        phase2.get("readonly_probe_request")
    )
    connector_skeleton = _normalize_connector_skeleton(source.get("connector_skeleton"))

    contract_violations = [
        field for field in _SAFETY_FALSE_FIELDS if _as_bool(source.get(field))
    ]
    if connector_skeleton["accepted"]:
        contract_violations.append("connector_skeleton_accepted")
    if connector_skeleton["status"] != "blocked_source_only":
        contract_violations.append("connector_skeleton_status_not_blocked")
    if readonly_probe_request["contract_id"] != "stock_etf_ibkr_readonly_probe_request_v1":
        contract_violations.append("readonly_probe_request_contract_id_mismatch")
    if readonly_probe_request["source_version"] != 1:
        contract_violations.append("readonly_probe_request_source_version_mismatch")
    if readonly_probe_request["status"] != "blocked_no_request_artifact":
        contract_violations.append("readonly_probe_request_status_not_blocked")
    for key in (
        "network_contact_performed",
        "secret_content_loaded",
        "paper_channel_exposed",
        "live_channel_exposed",
        "order_write_method_present",
        "bybit_path_reused",
    ):
        if connector_skeleton[key]:
            contract_violations.append(f"connector_skeleton_{key}")
    for key in (
        "request_artifact_present",
        "request_validated",
        "accepted_for_contact",
        "ibkr_contact_performed",
        "connector_runtime_started",
        "secret_content_serialized",
        "order_routed",
        "paper_order_submitted",
        "db_apply_performed",
        "evidence_clock_started",
        "bybit_path_reused",
        "live_or_tiny_live_authorized",
    ):
        if readonly_probe_request[key]:
            contract_violations.append(f"readonly_probe_request_{key}")
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
        "readonly_probe_request": readonly_probe_request,
        "connector_skeleton": connector_skeleton,
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

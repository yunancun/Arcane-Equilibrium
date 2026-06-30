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
_API_ALLOWLIST_CONTRACT_ID = "non_bybit_api_allowlist_v1"
_API_ALLOWLIST_SOURCE_VERSION = 1
_API_ALLOWLIST_READ_ACTION_COUNT = 10
_API_ALLOWLIST_PAPER_WRITE_ACTION_COUNT = 3
_API_ALLOWLIST_DENIED_ACTION_COUNT = 10
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


@stock_etf_router.get("", include_in_schema=False)
async def stock_etf_tab_redirect() -> RedirectResponse:
    return RedirectResponse(url="/static/tab-stock-etf.html", headers=_NO_STORE_HEADERS)

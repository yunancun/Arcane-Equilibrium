from __future__ import annotations

"""Fail-closed normalizer for Stock/ETF Phase 0 contract-packet status."""

from typing import Any

from .stock_etf_status_common import (
    _SAFETY_FALSE_FIELDS,
    _as_bool,
    _as_dict,
    _as_int,
    _as_list,
    _as_str,
)

_PHASE0_SCHEMA = "stock_etf_phase0_contract_packet_manifest_v1"
_PHASE0_STATUS = "ACCEPTED_PHASE0_CONTRACT_NO_RUNTIME_AUTHORITY"
_PHASE0_SCOPE = "paper_shadow_only"
_PHASE0_CONTRACT_COUNT = 35
_PHASE0_SAFETY_FALSE_FIELDS: tuple[str, ...] = (
    "phase1_runtime_started",
    "phase2_started",
    "phase3_started",
    "phase4_runtime_started",
    "phase5_started",
    "paper_shadow_launch_authorized",
    "tiny_live_or_live_authorized",
    "connector_runtime_started",
    "db_apply_performed",
    "evidence_clock_started",
    "scorecard_writer_started",
)


def _phase0_fail_closed(reason: str) -> dict[str, Any]:
    return {
        "schema": "",
        "generated_at": "",
        "status": "",
        "scope": "",
        "adr": "",
        "amd": "",
        "contract_packet": "",
        "accepted": False,
        "blockers": [reason],
    }


def _normalize_phase0_manifest(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    manifest = _as_dict(source.get("manifest"))
    if not manifest:
        manifest = _phase0_fail_closed(reason or "missing_phase0_manifest")

    blockers = [str(item) for item in _as_list(source.get("phase0_blockers"))]
    if reason is not None and reason not in blockers:
        blockers.append(reason)

    return {
        "schema": _as_str(manifest.get("schema"), ""),
        "generated_at": _as_str(manifest.get("generated_at"), ""),
        "status": _as_str(manifest.get("status"), ""),
        "scope": _as_str(manifest.get("scope"), ""),
        "adr": _as_str(manifest.get("adr"), ""),
        "amd": _as_str(manifest.get("amd"), ""),
        "contract_packet": _as_str(manifest.get("contract_packet"), ""),
        "accepted": _as_bool(source.get("phase0_accepted")),
        "blockers": blockers,
    }


def _phase0_contract_violations(
    source: dict[str, Any],
    manifest: dict[str, Any],
    reason: str | None,
) -> list[str]:
    violations = [
        field
        for field in (*_SAFETY_FALSE_FIELDS, *_PHASE0_SAFETY_FALSE_FIELDS)
        if _as_bool(source.get(field))
    ]
    if reason is not None:
        return violations

    if manifest["schema"] != _PHASE0_SCHEMA:
        violations.append("phase0_schema_mismatch")
    if manifest["status"] != _PHASE0_STATUS:
        violations.append("phase0_status_mismatch")
    if manifest["scope"] != _PHASE0_SCOPE:
        violations.append("phase0_scope_mismatch")
    if not manifest["accepted"]:
        violations.append("phase0_not_accepted")
    if _as_int(source.get("contract_count")) != _PHASE0_CONTRACT_COUNT:
        violations.append("phase0_contract_count_mismatch")

    api_baseline = _as_dict(source.get("api_baseline"))
    if not _as_bool(api_baseline.get("live_ports_denied")):
        violations.append("phase0_live_ports_not_denied")
    if _as_bool(api_baseline.get("ibkr_call_performed")):
        violations.append("phase0_ibkr_call_performed")

    denials = _as_dict(source.get("global_denials"))
    for field in (
        "ibkr_live",
        "tiny_live",
        "margin",
        "short",
        "options",
        "cfd",
        "transfer",
        "account_management_writes",
        "python_broker_write_authority",
        "gui_lane_authority",
        "automatic_promotion",
    ):
        if not _as_bool(denials.get(field)):
            violations.append(f"phase0_global_denial_missing:{field}")

    return violations


def _normalize_phase0_status(raw: Any, reason: str | None) -> dict[str, Any]:
    source = _as_dict(raw)
    manifest = _normalize_phase0_manifest(source, reason)
    contract_violations = _phase0_contract_violations(source, manifest, reason)
    state = "accepted_no_runtime_authority"
    if contract_violations:
        state = "contract_violation_blocked"
    elif reason is not None:
        state = "degraded"

    return {
        "api_version": "v1",
        "asset_lane": "stock_etf_cash",
        "broker": "ibkr",
        "scope": _as_str(source.get("scope"), _PHASE0_SCOPE),
        "gui_authority": "display_only",
        "phase0_status_state": state,
        "phase0_accepted": manifest["accepted"] and not contract_violations,
        "manifest": manifest,
        "contract_count": _as_int(source.get("contract_count")),
        "contracts": [str(item) for item in _as_list(source.get("contracts"))],
        "api_baseline": _as_dict(source.get("api_baseline")),
        "global_denials": _as_dict(source.get("global_denials")),
        "phase_unlock": _as_dict(source.get("phase_unlock")),
        "phase1_runtime_started": _as_bool(source.get("phase1_runtime_started")),
        "phase2_started": _as_bool(source.get("phase2_started")),
        "phase3_started": _as_bool(source.get("phase3_started")),
        "phase4_runtime_started": _as_bool(source.get("phase4_runtime_started")),
        "phase5_started": _as_bool(source.get("phase5_started")),
        "paper_shadow_launch_authorized": _as_bool(
            source.get("paper_shadow_launch_authorized")
        ),
        "tiny_live_or_live_authorized": _as_bool(
            source.get("tiny_live_or_live_authorized")
        ),
        "connector_runtime_started": _as_bool(source.get("connector_runtime_started")),
        "db_apply_performed": _as_bool(source.get("db_apply_performed")),
        "evidence_clock_started": _as_bool(source.get("evidence_clock_started")),
        "scorecard_writer_started": _as_bool(source.get("scorecard_writer_started")),
        "ibkr_call_performed": _as_bool(source.get("ibkr_call_performed")),
        "secret_slot_touched": _as_bool(source.get("secret_slot_touched")),
        "order_routed": _as_bool(source.get("order_routed")),
        "bybit_ipc_reused": _as_bool(source.get("bybit_ipc_reused")),
        "contract_violations": contract_violations,
        "degraded": reason is not None or bool(contract_violations),
        "reason": reason,
    }

#!/usr/bin/env python3
"""Diagnose current-candidate Guardian reconciler drift without order authority.

The helper consumes a GUI-derived proposed-sizing gate packet plus a read-only
runtime governance snapshot. It classifies whether runtime admission is still
blocked by Guardian / reconciler state and Decision Lease absence. It never
acquires a lease, refreshes BBO, calls Bybit, mutates runtime state, writes PG,
or grants order authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_sha256/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    file_sha256 as _sha256,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "current_candidate_guardian_reconciler_drift_diagnosis_v1"
GATE_PACKET_SCHEMA_VERSION = "current_candidate_decision_lease_guardian_gate_evidence_v1"
RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SCHEMA_VERSION = (
    "runtime_governance_ipc_readonly_snapshot_v1"
)

GATE_BLOCKED_STATUS = (
    "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_BLOCKED_BY_LOSS_CONTROL"
)
GATE_READY_STATUS = "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER"

READY_NO_ORDER_STATUS = (
    "CURRENT_CANDIDATE_GUARDIAN_RECONCILER_DRIFT_DIAGNOSIS_READY_NO_ORDER"
)
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_GUARDIAN_RECONCILER_DRIFT_DIAGNOSIS_BLOCKED_BY_LOSS_CONTROL"
)
NOT_READY_STATUS = (
    "CURRENT_CANDIDATE_GUARDIAN_RECONCILER_DRIFT_DIAGNOSIS_NOT_READY"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_GATE_PACKET_AGE_SECONDS = 6 * 60 * 60
DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS = 5 * 60

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "canonical_plan_mutation_performed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "crontab_mutation_performed",
    "decision_lease_acquire_performed",
    "decision_lease_release_performed",
    "decision_lease_emitted",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "lease_acquire_performed",
    "lease_release_performed",
    "live_authority_granted",
    "live_execution_allowed",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "placement_call_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_admission_ready",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}

BOUNDARY = (
    "read-only current-candidate Guardian/reconciler drift diagnosis; no "
    "Decision Lease acquire/release, no BBO refresh, no Guardian/Rust authority "
    "grant, no Bybit/private/order call, no order/cancel/modify, no PG read/write, "
    "no runtime/service/env/crontab mutation, no Cost Gate lowering, no "
    "live/mainnet authority, no promotion proof, and no profit proof"
)


def _upper(value: Any) -> str:
    return _str(value).replace("-", "_").replace(" ", "_").upper()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _same_float(left: Any, right: Any, tolerance: float = 1e-8) -> bool:
    left_num = _float(left)
    right_num = _float(right)
    return (
        left_num is not None
        and right_num is not None
        and abs(left_num - right_num) <= tolerance
    )


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "enabled",
            "grant",
            "granted",
            "authorize",
            "authorized",
            "ready",
        }
    return False


def _parse_dt(value: Any) -> dt.datetime | None:
    text = _str(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _parse_epoch_ms(value: Any) -> dt.datetime | None:
    number = _float(value)
    if number is None or number <= 0:
        return None
    seconds = number / 1000.0 if number > 10_000_000_000 else number
    try:
        return dt.datetime.fromtimestamp(seconds, tz=dt.timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _generated_at(payload: dict[str, Any]) -> Any:
    return payload.get("generated_at_utc") or payload.get("generated") or payload.get(
        "ts_utc"
    )


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any],
    now_utc: dt.datetime,
    max_age_seconds: int,
    required: bool,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = _generated_at(payload or {}) if present else None
    parsed = _parse_dt(generated_at) if generated_at else None
    age: float | None = None
    if parsed is not None:
        age = (now_utc - parsed).total_seconds()
    if not present:
        status = "MISSING" if required else "NOT_SUPPLIED"
    elif parsed is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age is not None and age < -60:
        status = "FROM_FUTURE"
    elif age is not None and age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "status": status,
        "present": present,
        "required": required,
        "schema_version": (payload or {}).get("schema_version") if present else None,
        "artifact_status": (payload or {}).get("status") if present else None,
        "generated_at_utc": generated_at,
        "age_seconds": round(age, 3) if age is not None else None,
        "max_age_seconds": max_age_seconds,
    }


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _recursive_authority_violations(payload: Any, prefix: str = "") -> list[str]:
    reasons: list[str] = []
    if isinstance(payload, list):
        for idx, item in enumerate(payload):
            reasons.extend(_recursive_authority_violations(item, f"{prefix}[{idx}]"))
        return reasons
    if not isinstance(payload, dict):
        return reasons
    for key, value in payload.items():
        path = f"{prefix}.{key}" if prefix else key
        if key in AUTHORITY_TRUE_KEYS and _truthy(value):
            reasons.append(f"{path}_true")
        if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
            reasons.append(f"{path}_not_none")
        if key == "order_authority" and value not in (None, "", "NOT_GRANTED"):
            reasons.append(f"{path}_not_not_granted")
        if isinstance(value, (dict, list)):
            reasons.extend(_recursive_authority_violations(value, path))
    return reasons


def _runtime_method(snapshot: dict[str, Any], method: str) -> tuple[Any, str | None]:
    methods = _dict(snapshot.get("methods"))
    entry = _dict(methods.get(method) or methods.get(method.replace(".", "_")))
    if entry:
        if entry.get("ok") is False:
            return None, f"{method}_not_ok"
        result = entry.get("result")
        if result is None and "payload" in entry:
            result = entry.get("payload")
        if result is None:
            result = entry
        return result, None
    direct_key = method.rsplit(".", 1)[-1]
    if direct_key in snapshot:
        return snapshot.get(direct_key), None
    friendly = {
        "governance.get_status": "governance_status",
        "governance.list_leases": "lease_list",
        "governance.get_risk_state": "risk_state",
    }.get(method)
    if friendly and friendly in snapshot:
        return snapshot.get(friendly), None
    return None, f"{method}_missing"


def _unwrap_result(value: Any) -> Any:
    if isinstance(value, dict) and set(value.keys()) == {"result"}:
        return value.get("result")
    return value


def _lease_list(snapshot: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    raw, reason = _runtime_method(snapshot, "governance.list_leases")
    if reason:
        return [], [reason]
    raw = _unwrap_result(raw)
    if isinstance(raw, dict):
        raw = raw.get("leases") or raw.get("items") or raw.get("result")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return [], ["governance.list_leases_not_list"]
    leases = [_dict(item) for item in raw if isinstance(item, dict)]
    reasons = []
    if len(leases) != len(raw):
        reasons.append("governance.list_leases_contains_non_object")
    return leases, reasons


def _status_and_risk(
    snapshot: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    status_raw, status_reason = _runtime_method(snapshot, "governance.get_status")
    risk_raw, risk_reason = _runtime_method(snapshot, "governance.get_risk_state")
    reasons: list[str] = []
    if status_reason:
        reasons.append(status_reason)
    if risk_reason:
        reasons.append(risk_reason)
    status = _dict(_unwrap_result(status_raw))
    risk = _dict(_unwrap_result(risk_raw))
    if not status:
        reasons.append("governance_status_missing_or_not_object")
    if not risk:
        reasons.append("governance_risk_state_missing_or_not_object")
    return status, risk, sorted(set(reasons))


def _transition_timestamp(transition: dict[str, Any]) -> dt.datetime | None:
    for key in ("timestamp_utc", "generated_at_utc", "ts_utc"):
        parsed = _parse_dt(transition.get(key))
        if parsed is not None:
            return parsed
    for key in ("timestamp_ms", "ts_ms", "created_at_ms"):
        parsed = _parse_epoch_ms(transition.get(key))
        if parsed is not None:
            return parsed
    return None


def _transition_tokens(transition: dict[str, Any]) -> set[str]:
    tokens = {
        _str(transition.get("event")).lower(),
        _str(transition.get("initiator")).lower(),
        _str(transition.get("from")).lower(),
        _str(transition.get("to")).lower(),
    }
    tokens.update(_str(item).lower() for item in _list(transition.get("reason_codes")))
    return {token for token in tokens if token}


def _transition_tail(risk_state: dict[str, Any]) -> list[dict[str, Any]]:
    for key in (
        "transitions_tail",
        "transition_tail",
        "recent_transitions",
        "transitions",
    ):
        raw = risk_state.get(key)
        if isinstance(raw, list):
            return [_dict(item) for item in raw if isinstance(item, dict)]
    history = _dict(risk_state.get("history"))
    for key in ("transitions_tail", "transition_tail", "recent_transitions"):
        raw = history.get(key)
        if isinstance(raw, list):
            return [_dict(item) for item in raw if isinstance(item, dict)]
    return []


def _transition_summary(
    transitions: list[dict[str, Any]],
    *,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    drift_indices: list[int] = []
    recovery_indices: list[int] = []
    compact: list[dict[str, Any]] = []
    for idx, transition in enumerate(transitions):
        tokens = _transition_tokens(transition)
        is_drift = "reconciler_drift" in tokens
        is_recovery = "reconciler_recovery" in tokens or "reconciler_auto_recovery" in tokens
        if is_drift:
            drift_indices.append(idx)
        if is_recovery:
            recovery_indices.append(idx)
        parsed_ts = _transition_timestamp(transition)
        compact.append(
            {
                "event": transition.get("event"),
                "from": transition.get("from"),
                "to": transition.get("to"),
                "initiator": transition.get("initiator"),
                "reason_codes": _list(transition.get("reason_codes")),
                "timestamp_utc": parsed_ts.isoformat() if parsed_ts else None,
                "is_reconciler_drift": is_drift,
                "is_reconciler_recovery": is_recovery,
            }
        )

    last_drift_index = drift_indices[-1] if drift_indices else None
    last_recovery_index = recovery_indices[-1] if recovery_indices else None
    latest_reconciler_index = None
    if drift_indices or recovery_indices:
        latest_reconciler_index = max(drift_indices + recovery_indices)
    latest = compact[latest_reconciler_index] if latest_reconciler_index is not None else None
    last_drift = compact[last_drift_index] if last_drift_index is not None else None
    last_recovery = (
        compact[last_recovery_index] if last_recovery_index is not None else None
    )
    drift_after_recovery = (
        last_drift_index is not None
        and last_recovery_index is not None
        and last_drift_index > last_recovery_index
    )
    last_drift_age_seconds = None
    if last_drift and last_drift.get("timestamp_utc"):
        parsed = _parse_dt(last_drift.get("timestamp_utc"))
        if parsed is not None:
            last_drift_age_seconds = round((now_utc - parsed).total_seconds(), 3)

    return {
        "transition_tail_count": len(compact),
        "reconciler_drift_count": len(drift_indices),
        "reconciler_recovery_count": len(recovery_indices),
        "latest_reconciler_event": latest,
        "latest_reconciler_event_is_drift": bool(
            latest and latest.get("is_reconciler_drift")
        ),
        "last_reconciler_drift": last_drift,
        "last_reconciler_recovery": last_recovery,
        "last_reconciler_drift_after_recovery": drift_after_recovery,
        "last_reconciler_drift_age_seconds": last_drift_age_seconds,
        "tail": compact,
    }


def _gate_source_reasons(packet: dict[str, Any], artifact: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if artifact.get("status") != "FRESH":
        reasons.append("gate_packet_not_fresh")
    if packet.get("schema_version") != GATE_PACKET_SCHEMA_VERSION:
        reasons.append("gate_packet_schema_version_invalid")
    if packet.get("status") not in {GATE_BLOCKED_STATUS, GATE_READY_STATUS}:
        reasons.append("gate_packet_status_not_reviewable")
    if _list(packet.get("source_blockers")):
        reasons.append("gate_packet_source_blockers_present")
    if _list(packet.get("authority_contamination_reasons")):
        reasons.append("gate_packet_authority_contamination_present")

    risk = _dict(packet.get("risk_context"))
    if risk.get("gui_risk_config_is_source_of_truth") is not True:
        reasons.append("gate_packet_gui_risk_config_not_source_of_truth")
    if risk.get("sizing_source") != "guardian_adjusted_sizing_proposal":
        reasons.append("gate_packet_not_using_guardian_adjusted_sizing_proposal")

    account_equity = _float(risk.get("account_equity_usdt"))
    resolved_cap = _float(risk.get("resolved_cap_usdt"))
    single_position_budget = _float(risk.get("single_position_budget_usdt"))
    effective_cap = _float(risk.get("effective_single_order_cap_usdt"))
    guardian_adjusted_cap = _float(
        risk.get("guardian_adjusted_cap_usdt_from_proposal")
    )
    per_trade_fraction = _float(risk.get("per_trade_risk_pct_fraction"))
    per_trade_display = _float(risk.get("per_trade_risk_pct_display"))
    position_size_max_pct = _float(risk.get("position_size_max_pct"))
    rounded_notional = _float(risk.get("rounded_notional_usdt"))

    for name, value in (
        ("account_equity_usdt", account_equity),
        ("resolved_cap_usdt", resolved_cap),
        ("single_position_budget_usdt", single_position_budget),
        ("effective_single_order_cap_usdt", effective_cap),
        ("guardian_adjusted_cap_usdt_from_proposal", guardian_adjusted_cap),
        ("per_trade_risk_pct_fraction", per_trade_fraction),
        ("per_trade_risk_pct_display", per_trade_display),
        ("position_size_max_pct", position_size_max_pct),
        ("rounded_notional_usdt", rounded_notional),
    ):
        if value is None or value <= 0:
            reasons.append(f"gate_packet_{name}_missing_or_non_positive")

    if per_trade_fraction is not None and per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_fraction_not_fraction")
    if (
        per_trade_fraction is not None
        and per_trade_display is not None
        and abs(per_trade_fraction * 100.0 - per_trade_display) > 1e-6
    ):
        reasons.append("per_trade_risk_pct_display_fraction_mismatch")
    if (
        account_equity is not None
        and per_trade_fraction is not None
        and resolved_cap is not None
        and not _same_float(account_equity * per_trade_fraction, resolved_cap)
    ):
        reasons.append("gui_resolved_cap_not_equity_times_per_trade_pct")
    if (
        account_equity is not None
        and position_size_max_pct is not None
        and single_position_budget is not None
        and not _same_float(account_equity * position_size_max_pct / 100.0, single_position_budget)
    ):
        reasons.append(
            "single_position_budget_not_equity_times_position_size_max_pct"
        )
    if (
        resolved_cap is not None
        and single_position_budget is not None
        and guardian_adjusted_cap is not None
        and effective_cap is not None
        and not _same_float(
            min(resolved_cap, single_position_budget, guardian_adjusted_cap),
            effective_cap,
        )
    ):
        reasons.append("effective_cap_not_min_of_gui_single_position_guardian")
    if (
        resolved_cap is not None
        and per_trade_display is not None
        and _same_float(resolved_cap, per_trade_display)
    ):
        reasons.append("resolved_cap_equals_gui_display_percent_not_usdt_budget")
    return sorted(set(reasons))


def _runtime_source_reasons(
    snapshot: dict[str, Any],
    artifact: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    if artifact.get("status") != "FRESH":
        reasons.append("runtime_governance_snapshot_not_fresh")
    if snapshot.get("schema_version") != RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SCHEMA_VERSION:
        reasons.append("runtime_governance_snapshot_schema_version_invalid")
    answers = _dict(snapshot.get("answers"))
    if answers.get("runtime_readonly_ipc_call_performed") is not True:
        reasons.append("runtime_readonly_ipc_call_not_marked_performed")
    for key in (
        "decision_lease_acquire_performed",
        "decision_lease_release_performed",
        "order_submission_performed",
        "runtime_mutation_performed",
        "pg_write_performed",
        "service_restart_performed",
        "global_cost_gate_lowering_recommended",
        "live_authority_granted",
    ):
        if answers.get(key) is not False:
            reasons.append(f"runtime_snapshot_{key}_not_false")
    if answers.get("main_cost_gate_adjustment") not in (None, "NONE"):
        reasons.append("runtime_snapshot_main_cost_gate_adjustment_not_none")
    return sorted(set(reasons))


def _runtime_blockers(
    *,
    status: dict[str, Any],
    risk_state: dict[str, Any],
    leases: list[dict[str, Any]],
    lease_reasons: list[str],
    status_risk_reasons: list[str],
    transition_summary: dict[str, Any],
) -> list[str]:
    blockers = list(lease_reasons) + list(status_risk_reasons)
    constraints = _dict(risk_state.get("constraints"))
    status_level = _upper(status.get("risk_level"))
    risk_level = _upper(risk_state.get("level") or status.get("risk_level"))
    if status.get("enabled") is not True:
        blockers.append("governance_status_not_enabled")
    if not risk_level:
        blockers.append("guardian_risk_level_missing")
    elif risk_level != "NORMAL":
        blockers.append("guardian_risk_state_not_normal")
    if status_level and risk_level and status_level != risk_level:
        blockers.append("governance_status_risk_level_mismatch")

    live_count = _float(status.get("lease_live_count"))
    if live_count is None:
        live_count = float(len(leases))
    if live_count <= 0:
        blockers.append("lease_live_count_zero")
    if not leases:
        blockers.append("active_decision_lease_missing")

    multiplier = _float(
        risk_state.get("position_size_multiplier")
        if risk_state.get("position_size_multiplier") is not None
        else constraints.get("position_size_multiplier")
    )
    if multiplier is None:
        blockers.append("position_size_multiplier_missing")
    elif multiplier < 1.0:
        blockers.append("position_size_multiplier_below_one")
    elif multiplier > 1.0:
        blockers.append("position_size_multiplier_would_expand_cap")

    if transition_summary.get("latest_reconciler_event_is_drift") is True:
        blockers.append("guardian_reconciler_drift_active")
    if transition_summary.get("last_reconciler_drift_after_recovery") is True:
        blockers.append("reconciler_drift_after_recovery")
    if (
        risk_level != "NORMAL"
        and transition_summary.get("reconciler_drift_count", 0) > 0
    ):
        blockers.append("guardian_reconciler_drift_tail_present")
    return sorted(set(blockers))


def build_current_candidate_guardian_reconciler_drift_diagnosis(
    *,
    gate_packet: dict[str, Any] | None,
    runtime_governance_snapshot: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_gate_packet_age_seconds: int = DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    max_runtime_snapshot_age_seconds: int = DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    if max_gate_packet_age_seconds < 60 or max_gate_packet_age_seconds > 24 * 3600:
        raise ValueError("max_gate_packet_age_seconds must be in [60, 86400]")
    if max_runtime_snapshot_age_seconds < 30 or max_runtime_snapshot_age_seconds > 3600:
        raise ValueError("max_runtime_snapshot_age_seconds must be in [30, 3600]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    gate = _dict(gate_packet)
    snapshot = _dict(runtime_governance_snapshot)
    artifacts = {
        "gate_packet": _artifact_summary(
            name="gate_packet",
            path=paths.get("gate_packet"),
            payload=gate,
            now_utc=now,
            max_age_seconds=max_gate_packet_age_seconds,
            required=True,
        ),
        "runtime_governance_snapshot": _artifact_summary(
            name="runtime_governance_snapshot",
            path=paths.get("runtime_governance_snapshot"),
            payload=snapshot,
            now_utc=now,
            max_age_seconds=max_runtime_snapshot_age_seconds,
            required=True,
        ),
    }
    candidate = _candidate_identity(_dict(gate.get("candidate")))
    risk_context = _dict(gate.get("risk_context"))
    source_reasons = _gate_source_reasons(gate, artifacts["gate_packet"])
    source_reasons.extend(
        _runtime_source_reasons(snapshot, artifacts["runtime_governance_snapshot"])
    )
    if not candidate.get("side_cell_key"):
        source_reasons.append("candidate_missing")

    authority_reasons: list[str] = []
    for name, payload in (
        ("gate_packet", gate),
        ("runtime_governance_snapshot", snapshot),
    ):
        if payload:
            authority_reasons.extend(
                f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
            )

    leases, lease_reasons = _lease_list(snapshot)
    status, risk_state, status_risk_reasons = _status_and_risk(snapshot)
    transitions = _transition_tail(risk_state)
    transition_summary = _transition_summary(transitions, now_utc=now)
    runtime_blockers = _runtime_blockers(
        status=status,
        risk_state=risk_state,
        leases=leases,
        lease_reasons=lease_reasons,
        status_risk_reasons=status_risk_reasons,
        transition_summary=transition_summary,
    )

    if authority_reasons:
        status_value = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation"
    elif source_reasons:
        status_value = NOT_READY_STATUS
        reason = "input_gate_packet_or_runtime_snapshot_not_ready"
    elif runtime_blockers:
        status_value = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "guardian_reconciler_or_decision_lease_not_ready"
    else:
        status_value = READY_NO_ORDER_STATUS
        reason = "guardian_reconciler_drift_diagnosis_ready_no_order"

    blocking_gates = sorted(set(source_reasons + authority_reasons + runtime_blockers))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status_value,
        "reason": reason,
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": artifacts,
        "source_blockers": sorted(set(source_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "runtime_blockers": runtime_blockers,
        "blocking_gates": blocking_gates,
        "blocking_gate_count": len(blocking_gates),
        "risk_context": {
            "gui_risk_config_is_source_of_truth": risk_context.get(
                "gui_risk_config_is_source_of_truth"
            ),
            "sizing_source": risk_context.get("sizing_source"),
            "account_equity_usdt": risk_context.get("account_equity_usdt"),
            "resolved_cap_usdt": risk_context.get("resolved_cap_usdt"),
            "single_position_budget_usdt": risk_context.get(
                "single_position_budget_usdt"
            ),
            "effective_single_order_cap_usdt": risk_context.get(
                "effective_single_order_cap_usdt"
            ),
            "guardian_adjusted_cap_usdt_from_proposal": risk_context.get(
                "guardian_adjusted_cap_usdt_from_proposal"
            ),
            "rounded_qty": risk_context.get("rounded_qty"),
            "rounded_notional_usdt": risk_context.get("rounded_notional_usdt"),
            "per_trade_risk_pct_fraction": risk_context.get(
                "per_trade_risk_pct_fraction"
            ),
            "per_trade_risk_pct_display": risk_context.get(
                "per_trade_risk_pct_display"
            ),
            "position_size_max_pct": risk_context.get("position_size_max_pct"),
            "gui_percent_semantics": (
                "GUI 10.0% means per_trade_risk_pct=0.1 and resolves to "
                "account_equity_usdt * 0.1; cap_usdt=10 is not global "
                "single-order risk authority"
            ),
            "effective_single_order_cap_basis": (
                "min(gui_per_trade_cap_usdt, gui_max_single_position_budget_usdt, "
                "guardian_adjusted_cap_usdt)"
            ),
        },
        "runtime_governance": {
            "status": status,
            "risk_state": risk_state,
            "lease_count": len(leases),
            "transition_summary": transition_summary,
        },
        "next_required_evidence": [
            "fresh read-only runtime governance snapshot with Guardian NORMAL and no active reconciler_drift tail",
            "fresh active current-candidate Demo Decision Lease from the reviewed Rust authority path",
            "rerun current-candidate Decision Lease / Guardian gate evidence after Guardian and lease state change",
            "refresh actual-admission BBO only after Decision Lease and Guardian gates pass",
        ],
        "answers": {
            "review_contract_ready": not source_reasons and not authority_reasons,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "runtime_readonly_ipc_call_performed": True,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "decision_lease_emitted": False,
            "guardian_risk_gate_passed_by_this_packet": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "order_submission_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    candidate = _dict(packet.get("candidate"))
    risk = _dict(packet.get("risk_context"))
    runtime = _dict(packet.get("runtime_governance"))
    risk_state = _dict(runtime.get("risk_state"))
    transition = _dict(runtime.get("transition_summary"))
    lines = [
        "# Current Candidate Guardian Reconciler Drift Diagnosis",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- GUI resolved cap USDT: `{risk.get('resolved_cap_usdt')}`",
        f"- GUI max-single-position budget USDT: `{risk.get('single_position_budget_usdt')}`",
        f"- Effective single-order cap USDT: `{risk.get('effective_single_order_cap_usdt')}`",
        f"- Guardian level: `{risk_state.get('level')}`",
        f"- Position size multiplier: `{risk_state.get('position_size_multiplier') or _dict(risk_state.get('constraints')).get('position_size_multiplier')}`",
        f"- Latest reconciler event is drift: `{transition.get('latest_reconciler_event_is_drift')}`",
        f"- Last drift after recovery: `{transition.get('last_reconciler_drift_after_recovery')}`",
        f"- Runtime lease count: `{runtime.get('lease_count')}`",
        "",
        "## Runtime Blockers",
    ]
    blockers = _list(packet.get("runtime_blockers"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Source Blockers"])
    source = _list(packet.get("source_blockers"))
    lines.extend(f"- `{reason}`" for reason in source) if source else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-packet-json", type=Path, required=True)
    parser.add_argument("--runtime-governance-snapshot-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--max-gate-packet-age-seconds",
        type=int,
        default=DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-runtime-snapshot-age-seconds",
        type=int,
        default=DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS,
    )
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_current_candidate_guardian_reconciler_drift_diagnosis(
        gate_packet=_read_json(args.gate_packet_json),
        runtime_governance_snapshot=_read_json(args.runtime_governance_snapshot_json),
        paths={
            "gate_packet": args.gate_packet_json,
            "runtime_governance_snapshot": args.runtime_governance_snapshot_json,
        },
        max_gate_packet_age_seconds=args.max_gate_packet_age_seconds,
        max_runtime_snapshot_age_seconds=args.max_runtime_snapshot_age_seconds,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

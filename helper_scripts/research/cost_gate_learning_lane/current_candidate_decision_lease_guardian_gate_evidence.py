#!/usr/bin/env python3
"""Build no-order Decision Lease and Guardian gate evidence for the current candidate.

This helper consumes a bounded Demo admission review plus a read-only runtime
governance IPC snapshot. It does not acquire/release a Decision Lease, mutate
runtime state, call Bybit, query/write PG, admit an order, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "current_candidate_decision_lease_guardian_gate_evidence_v1"
DECISION_LEASE_GATE_SCHEMA_VERSION = "current_candidate_decision_lease_gate_evidence_v1"
GUARDIAN_RISK_GATE_SCHEMA_VERSION = "current_candidate_guardian_risk_gate_evidence_v1"
RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SCHEMA_VERSION = (
    "runtime_governance_ipc_readonly_snapshot_v1"
)

ADMISSION_REVIEW_SCHEMA_VERSION = (
    "current_candidate_bounded_demo_admission_envelope_review_v1"
)
ADMISSION_REVIEW_BLOCKED_STATUS = (
    "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL"
)
ADMISSION_REVIEW_READY_STATUS = (
    "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_READY_NO_ORDER"
)

READY_NO_ORDER_STATUS = "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_READY_NO_ORDER"
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_BLOCKED_BY_LOSS_CONTROL"
)
NOT_READY_STATUS = "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DECISION_LEASE_ACTIVE_STATUS = "DECISION_LEASE_ACTIVE"
DECISION_LEASE_NOT_READY_STATUS = "DECISION_LEASE_NOT_READY"
GUARDIAN_RISK_GATE_PASS_STATUS = "GUARDIAN_RISK_GATE_PASS"
GUARDIAN_RISK_GATE_NOT_READY_STATUS = "GUARDIAN_RISK_GATE_NOT_READY"

DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS = 6 * 60 * 60
DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS = 5 * 60
RUNTIME_SNAPSHOT_SOURCE = "runtime_governance_ipc_readonly_snapshot"

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "bounded_demo_probe_authorized",
    "bybit_private_call_performed",
    "canonical_plan_mutation_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "cost_gate_lowering_recommended",
    "crontab_mutation_performed",
    "decision_lease_acquire_performed",
    "decision_lease_release_performed",
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
    "read-only runtime governance evidence review; no Decision Lease acquire or "
    "release, no Guardian/Rust authority grant, no Bybit/private/order call, no "
    "order/cancel/modify, no PG read/write, no runtime/service/env/crontab "
    "mutation, no Cost Gate lowering, no live/mainnet authority, no promotion "
    "proof, and no profit proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _int(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return default
    return parsed


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


def _parse_expiry(payload: dict[str, Any]) -> dt.datetime | None:
    for key in ("expires_at_utc", "lease_expires_at_utc", "expires_at"):
        parsed = _parse_dt(payload.get(key))
        if parsed is not None:
            return parsed
    for key in ("expires_at_ms", "lease_expires_at_ms", "expiry_ms"):
        parsed = _parse_epoch_ms(payload.get(key))
        if parsed is not None:
            return parsed
    ttl_ms = _float(payload.get("ttl_ms"))
    created = _parse_epoch_ms(payload.get("created_at_ms") or payload.get("created_ms"))
    if ttl_ms is not None and ttl_ms > 0 and created is not None:
        return created + dt.timedelta(milliseconds=ttl_ms)
    return None


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    payload: dict[str, Any] | None,
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


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _candidate_aligned(*candidates: dict[str, Any]) -> bool:
    keys = [_candidate_key(candidate) for candidate in candidates]
    if any(not key[0] for key in keys):
        return False
    return len(set(keys)) == 1


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


def _runtime_method(
    snapshot: dict[str, Any],
    method: str,
) -> tuple[Any, str | None]:
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
    reasons: list[str] = []
    if reason:
        reasons.append(reason)
        return [], reasons
    raw = _unwrap_result(raw)
    if isinstance(raw, dict):
        raw = raw.get("leases") or raw.get("items") or raw.get("result")
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        return [], ["governance.list_leases_not_list"]
    leases = [_dict(item) for item in raw if isinstance(item, dict)]
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


def _admission_source_reasons(admission: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if admission.get("schema_version") != ADMISSION_REVIEW_SCHEMA_VERSION:
        reasons.append("admission_review_schema_version_invalid")
    if admission.get("status") not in {
        ADMISSION_REVIEW_BLOCKED_STATUS,
        ADMISSION_REVIEW_READY_STATUS,
    }:
        reasons.append("admission_review_status_not_reviewable")
    answers = _dict(admission.get("answers"))
    if answers.get("review_contract_ready") is not True:
        reasons.append("admission_review_contract_not_ready")
    if answers.get("runtime_admission_ready") is not False:
        reasons.append("admission_review_runtime_admission_ready_not_false")
    if answers.get("order_admission_ready") is not False:
        reasons.append("admission_review_order_admission_ready_not_false")
    if _list(admission.get("source_blockers")):
        reasons.append("admission_review_has_source_blockers")
    if _list(admission.get("authority_contamination_reasons")):
        reasons.append("admission_review_has_authority_contamination")
    risk = _dict(admission.get("risk_semantics"))
    if risk.get("gui_risk_config_is_source_of_truth") is not True:
        reasons.append("admission_review_gui_risk_not_source_of_truth")
    if risk.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("admission_review_local_10_usdt_cap_marked_authority")
    if _float(risk.get("resolved_cap_usdt")) is None:
        reasons.append("admission_review_resolved_cap_missing")
    return sorted(set(reasons))


def _runtime_snapshot_reasons(snapshot: dict[str, Any], artifact: dict[str, Any]) -> list[str]:
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
    ):
        if answers.get(key) is not False:
            reasons.append(f"runtime_snapshot_{key}_not_false")
    return sorted(set(reasons))


def _extract_admission_context(admission: dict[str, Any]) -> dict[str, Any]:
    preview = _dict(admission.get("admission_envelope_preview"))
    risk_limits = _dict(preview.get("risk_limits"))
    order_shape = _dict(preview.get("order_shape"))
    risk = _dict(admission.get("risk_semantics"))
    candidate = _candidate_identity(
        _dict(admission.get("candidate")) or _dict(preview.get("candidate"))
    )
    return {
        "candidate": candidate,
        "resolved_cap_usdt": _float(
            risk_limits.get("per_order_cap_usdt") or risk.get("resolved_cap_usdt")
        ),
        "rounded_notional_usdt": _float(
            order_shape.get("rounded_notional_usdt")
            or risk.get("rounded_notional_usdt")
        ),
        "per_trade_risk_pct_fraction": _float(
            risk_limits.get("per_trade_risk_pct_fraction")
            or risk.get("per_trade_risk_pct_fraction")
        ),
        "per_trade_risk_pct_display": _float(
            risk_limits.get("per_trade_risk_pct_display")
            or risk.get("gui_p1_risk_trade_pct")
        ),
        "position_size_max_pct": _float(
            risk_limits.get("position_size_max_pct")
            or risk.get("position_size_max_pct")
        ),
    }


def _lease_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    metadata = _dict(payload.get("metadata"))
    return _candidate_identity(
        _dict(payload.get("candidate"))
        or _dict(metadata.get("candidate"))
        or {
            "side_cell_key": payload.get("side_cell_key") or metadata.get("side_cell_key"),
            "strategy_name": payload.get("strategy_name") or metadata.get("strategy_name"),
            "symbol": payload.get("symbol") or metadata.get("symbol"),
            "side": payload.get("side") or metadata.get("side"),
            "outcome_horizon_minutes": payload.get("outcome_horizon_minutes")
            or metadata.get("outcome_horizon_minutes"),
        }
    )


def _lease_scope(payload: dict[str, Any]) -> str:
    return _str(payload.get("scope") or _dict(payload.get("metadata")).get("scope"))


def _lease_environment(payload: dict[str, Any]) -> str:
    metadata = _dict(payload.get("metadata"))
    return _str(payload.get("environment") or metadata.get("environment")).lower()


def _lease_demo_only(payload: dict[str, Any]) -> bool:
    metadata = _dict(payload.get("metadata"))
    return payload.get("demo_only") is True or metadata.get("demo_only") is True


def _lease_status(payload: dict[str, Any]) -> str:
    return _str(
        payload.get("status")
        or payload.get("state")
        or payload.get("outcome")
        or _dict(payload.get("metadata")).get("status")
    ).upper()


def _build_decision_lease_gate(
    *,
    leases: list[dict[str, Any]],
    lease_reasons: list[str],
    status: dict[str, Any],
    candidate: dict[str, Any],
    now_utc: dt.datetime,
    snapshot_sha256: str | None,
) -> dict[str, Any]:
    blockers = list(lease_reasons)
    live_count = _int(status.get("lease_live_count"), default=len(leases))
    if live_count <= 0:
        blockers.append("lease_live_count_zero")
    if not leases:
        blockers.append("decision_lease_missing")

    selected: dict[str, Any] | None = None
    selected_expiry: dt.datetime | None = None
    examined: list[dict[str, Any]] = []
    for lease in leases:
        lease_id = _str(lease.get("lease_id") or lease.get("decision_lease_id"))
        lease_candidate = _lease_candidate(lease)
        lease_status = _lease_status(lease)
        expiry = _parse_expiry(lease)
        scope = _lease_scope(lease)
        env = _lease_environment(lease)
        demo_only = _lease_demo_only(lease)
        aligned = _candidate_aligned(candidate, lease_candidate)
        live = lease_status in {"ACTIVE", "LEASE_ACTIVE", "DECISION_LEASE_ACTIVE"}
        expires_in_future = expiry is not None and expiry > now_utc
        scope_lower = scope.lower()
        live_or_mainnet_scope = "live" in scope_lower or "mainnet" in scope_lower
        local_reasons: list[str] = []
        if not lease_id:
            local_reasons.append("lease_id_missing")
        if not live:
            local_reasons.append("lease_not_active")
        if expiry is None:
            local_reasons.append("lease_expiry_missing")
        elif not expires_in_future:
            local_reasons.append("lease_expired")
        if not aligned:
            local_reasons.append("lease_candidate_mismatch_or_missing")
        if not demo_only and env != "demo":
            local_reasons.append("lease_not_demo_scoped")
        if live_or_mainnet_scope or env in {"live", "mainnet"}:
            local_reasons.append("lease_live_or_mainnet_scope")
        examined.append(
            {
                "lease_id": lease_id or None,
                "status": lease_status or None,
                "candidate": lease_candidate,
                "candidate_matches": aligned,
                "scope": scope or None,
                "environment": env or None,
                "demo_only": demo_only,
                "expires_at_utc": expiry.isoformat() if expiry else None,
                "blocking_reasons": local_reasons,
            }
        )
        if not local_reasons and selected is None:
            selected = lease
            selected_expiry = expiry

    if selected is None:
        blockers.append("current_candidate_active_demo_decision_lease_missing")
    blockers = sorted(set(blockers))
    valid = selected is not None and not blockers
    lease_id = (
        _str(selected.get("lease_id") or selected.get("decision_lease_id"))
        if selected
        else None
    )
    return {
        "schema_version": DECISION_LEASE_GATE_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": DECISION_LEASE_ACTIVE_STATUS if valid else DECISION_LEASE_NOT_READY_STATUS,
        "source": RUNTIME_SNAPSHOT_SOURCE,
        "runtime_governance_snapshot_sha256": snapshot_sha256,
        "environment": "demo",
        "demo_only": True,
        "candidate": candidate,
        "lease_id": lease_id,
        "decision_lease_id": lease_id,
        "expires_at_utc": selected_expiry.isoformat() if selected_expiry else None,
        "lease_live_count": live_count,
        "examined_leases": examined,
        "blocking_reasons": blockers,
        "valid_for_current_candidate": valid,
        "runtime_admission_ready": False,
        "order_admission_ready": False,
        "decision_lease_acquire_performed": False,
        "decision_lease_release_performed": False,
        "answers": {
            "runtime_readonly_ipc_call_performed": True,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "runtime_mutation_performed": False,
            "order_submission_performed": False,
            "order_admission_ready": False,
            "live_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
        },
        "boundary": BOUNDARY,
    }


def _upper_level(value: Any) -> str:
    return _str(value).replace("-", "_").replace(" ", "_").upper()


def _build_guardian_risk_gate(
    *,
    status: dict[str, Any],
    risk_state: dict[str, Any],
    status_risk_reasons: list[str],
    candidate: dict[str, Any],
    resolved_cap_usdt: float | None,
    rounded_notional_usdt: float | None,
    snapshot_sha256: str | None,
    now_utc: dt.datetime,
) -> dict[str, Any]:
    blockers = list(status_risk_reasons)
    constraints = _dict(risk_state.get("constraints"))
    if status.get("enabled") is not True:
        blockers.append("governance_status_not_enabled")

    status_level = _upper_level(status.get("risk_level"))
    risk_level = _upper_level(risk_state.get("level") or status.get("risk_level"))
    if not risk_level:
        blockers.append("risk_level_missing")
    elif risk_level != "NORMAL":
        blockers.append("guardian_risk_state_not_normal")
    if status_level and status_level != risk_level:
        blockers.append("governance_status_risk_level_mismatch")

    new_entries_allowed = risk_state.get(
        "new_entries_allowed", constraints.get("new_entries_allowed")
    )
    reduce_only = risk_state.get("reduce_only", constraints.get("reduce_only"))
    active_de_risking = risk_state.get(
        "active_de_risking", constraints.get("active_de_risking")
    )
    requires_operator = risk_state.get(
        "requires_operator", constraints.get("requires_operator")
    )
    emergency_stops = risk_state.get(
        "emergency_stops", constraints.get("emergency_stops")
    )
    multiplier = _float(
        risk_state.get("position_size_multiplier")
        if risk_state.get("position_size_multiplier") is not None
        else constraints.get("position_size_multiplier")
    )

    if new_entries_allowed is not True:
        blockers.append("new_entries_not_allowed")
    if _truthy(reduce_only):
        blockers.append("risk_state_reduce_only")
    if _truthy(active_de_risking):
        blockers.append("risk_state_active_de_risking")
    if _truthy(requires_operator):
        blockers.append("risk_state_requires_operator")
    if _truthy(emergency_stops):
        blockers.append("risk_state_emergency_stop")

    if multiplier is None:
        multiplier = 1.0 if risk_level == "NORMAL" else None
    if multiplier is None or multiplier <= 0:
        blockers.append("position_size_multiplier_missing_or_non_positive")
        effective_multiplier = None
    else:
        effective_multiplier = min(multiplier, 1.0)
        if multiplier > 1.0:
            blockers.append("position_size_multiplier_would_expand_cap")

    if resolved_cap_usdt is None or resolved_cap_usdt <= 0:
        blockers.append("resolved_gui_cap_missing_or_non_positive")
    if rounded_notional_usdt is None or rounded_notional_usdt <= 0:
        blockers.append("rounded_notional_missing_or_non_positive")

    adjusted_cap = (
        resolved_cap_usdt * effective_multiplier
        if resolved_cap_usdt is not None and effective_multiplier is not None
        else None
    )
    rounded_lte_adjusted = (
        rounded_notional_usdt is not None
        and adjusted_cap is not None
        and rounded_notional_usdt <= adjusted_cap + 1e-8
    )
    if rounded_lte_adjusted is False:
        blockers.append("rounded_notional_exceeds_guardian_adjusted_cap")

    blockers = sorted(set(blockers))
    valid = not blockers
    return {
        "schema_version": GUARDIAN_RISK_GATE_SCHEMA_VERSION,
        "generated_at_utc": now_utc.isoformat(),
        "status": GUARDIAN_RISK_GATE_PASS_STATUS
        if valid
        else GUARDIAN_RISK_GATE_NOT_READY_STATUS,
        "source": RUNTIME_SNAPSHOT_SOURCE,
        "runtime_governance_snapshot_sha256": snapshot_sha256,
        "environment": "demo",
        "candidate": candidate,
        "risk_level": risk_level or None,
        "status_risk_level": status_level or None,
        "new_entries_allowed": new_entries_allowed,
        "reduce_only": reduce_only,
        "active_de_risking": active_de_risking,
        "requires_operator": requires_operator,
        "emergency_stops": emergency_stops,
        "position_size_multiplier": multiplier,
        "effective_position_size_multiplier": effective_multiplier,
        "cap_usdt": adjusted_cap,
        "risk_limits": {
            "gui_resolved_cap_usdt": resolved_cap_usdt,
            "guardian_adjusted_cap_usdt": adjusted_cap,
            "rounded_notional_usdt": rounded_notional_usdt,
            "rounded_notional_lte_guardian_adjusted_cap": rounded_lte_adjusted,
        },
        "blocking_reasons": blockers,
        "valid_for_current_candidate": valid,
        "runtime_admission_ready": False,
        "order_admission_ready": False,
        "answers": {
            "runtime_readonly_ipc_call_performed": True,
            "runtime_mutation_performed": False,
            "order_submission_performed": False,
            "order_admission_ready": False,
            "live_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
        },
        "boundary": BOUNDARY,
    }


def build_current_candidate_decision_lease_guardian_gate_evidence(
    *,
    admission_review: dict[str, Any] | None,
    runtime_governance_snapshot: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_admission_review_age_seconds: int = DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS,
    max_runtime_snapshot_age_seconds: int = DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    if max_admission_review_age_seconds < 60 or max_admission_review_age_seconds > 24 * 3600:
        raise ValueError("max_admission_review_age_seconds must be in [60, 86400]")
    if max_runtime_snapshot_age_seconds < 30 or max_runtime_snapshot_age_seconds > 3600:
        raise ValueError("max_runtime_snapshot_age_seconds must be in [30, 3600]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    admission = _dict(admission_review)
    snapshot = _dict(runtime_governance_snapshot)
    artifacts = {
        "admission_review": _artifact_summary(
            name="admission_review",
            path=paths.get("admission_review"),
            payload=admission,
            now_utc=now,
            max_age_seconds=max_admission_review_age_seconds,
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

    context = _extract_admission_context(admission)
    candidate = _candidate_identity(context["candidate"])
    source_reasons: list[str] = []
    if artifacts["admission_review"]["status"] != "FRESH":
        source_reasons.append("admission_review_not_fresh")
    source_reasons.extend(_admission_source_reasons(admission))
    source_reasons.extend(
        _runtime_snapshot_reasons(snapshot, artifacts["runtime_governance_snapshot"])
    )
    if not candidate.get("side_cell_key"):
        source_reasons.append("candidate_missing")

    authority_reasons = []
    for name, payload in (
        ("admission_review", admission),
        ("runtime_governance_snapshot", snapshot),
    ):
        if payload:
            authority_reasons.extend(
                f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
            )

    leases, lease_reasons = _lease_list(snapshot)
    status, risk_state, status_risk_reasons = _status_and_risk(snapshot)
    snapshot_sha = artifacts["runtime_governance_snapshot"]["sha256"]
    decision_gate = _build_decision_lease_gate(
        leases=leases,
        lease_reasons=lease_reasons,
        status=status,
        candidate=candidate,
        now_utc=now,
        snapshot_sha256=snapshot_sha,
    )
    guardian_gate = _build_guardian_risk_gate(
        status=status,
        risk_state=risk_state,
        status_risk_reasons=status_risk_reasons,
        candidate=candidate,
        resolved_cap_usdt=context["resolved_cap_usdt"],
        rounded_notional_usdt=context["rounded_notional_usdt"],
        snapshot_sha256=snapshot_sha,
        now_utc=now,
    )

    gate_blockers = []
    if decision_gate["valid_for_current_candidate"] is not True:
        gate_blockers.append("decision_lease_valid")
    if guardian_gate["valid_for_current_candidate"] is not True:
        gate_blockers.append("guardian_risk_gate_valid")

    if authority_reasons:
        status_value = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation"
    elif source_reasons:
        status_value = NOT_READY_STATUS
        reason = "input_admission_or_runtime_snapshot_not_ready"
    elif gate_blockers:
        status_value = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "decision_lease_or_guardian_gate_not_ready"
    else:
        status_value = READY_NO_ORDER_STATUS
        reason = "decision_lease_and_guardian_gate_evidence_ready_no_order"

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
        "runtime_admission_blockers": gate_blockers,
        "blocking_gates": sorted(set(source_reasons + authority_reasons + gate_blockers)),
        "blocking_gate_count": len(set(source_reasons + authority_reasons + gate_blockers)),
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "resolved_cap_usdt": context["resolved_cap_usdt"],
            "rounded_notional_usdt": context["rounded_notional_usdt"],
            "per_trade_risk_pct_fraction": context["per_trade_risk_pct_fraction"],
            "per_trade_risk_pct_display": context["per_trade_risk_pct_display"],
            "position_size_max_pct": context["position_size_max_pct"],
            "gui_percent_semantics": (
                "GUI 10.0% means per_trade_risk_pct=0.1; local 10 USDT "
                "bounded-probe diagnostics cannot become runtime admission cap"
            ),
        },
        "runtime_governance": {
            "status": status,
            "risk_state": risk_state,
            "lease_count": len(leases),
        },
        "decision_lease_gate_artifact": decision_gate,
        "guardian_risk_gate_artifact": guardian_gate,
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
    decision = _dict(packet.get("decision_lease_gate_artifact"))
    guardian = _dict(packet.get("guardian_risk_gate_artifact"))
    guardian_limits = _dict(guardian.get("risk_limits"))
    lines = [
        "# Current Candidate Decision Lease / Guardian Gate Evidence",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- GUI resolved cap USDT: `{risk.get('resolved_cap_usdt')}`",
        f"- Rounded notional USDT: `{risk.get('rounded_notional_usdt')}`",
        f"- Decision Lease valid: `{decision.get('valid_for_current_candidate')}`",
        f"- Guardian gate valid: `{guardian.get('valid_for_current_candidate')}`",
        f"- Risk level: `{guardian.get('risk_level')}`",
        f"- Guardian adjusted cap USDT: `{guardian_limits.get('guardian_adjusted_cap_usdt')}`",
        "",
        "## Blockers",
    ]
    blockers = _list(packet.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Decision Lease Reasons"])
    decision_reasons = _list(decision.get("blocking_reasons"))
    lines.extend(f"- `{reason}`" for reason in decision_reasons) if decision_reasons else lines.append("- none")
    lines.extend(["", "## Guardian Reasons"])
    guardian_reasons = _list(guardian.get("blocking_reasons"))
    lines.extend(f"- `{reason}`" for reason in guardian_reasons) if guardian_reasons else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-review-json", type=Path, required=True)
    parser.add_argument("--runtime-governance-snapshot-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--decision-lease-gate-json-output", type=Path)
    parser.add_argument("--guardian-risk-gate-json-output", type=Path)
    parser.add_argument(
        "--max-admission-review-age-seconds",
        type=int,
        default=DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS,
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
    packet = build_current_candidate_decision_lease_guardian_gate_evidence(
        admission_review=_read_json(args.admission_review_json),
        runtime_governance_snapshot=_read_json(args.runtime_governance_snapshot_json),
        paths={
            "admission_review": args.admission_review_json,
            "runtime_governance_snapshot": args.runtime_governance_snapshot_json,
        },
        max_admission_review_age_seconds=args.max_admission_review_age_seconds,
        max_runtime_snapshot_age_seconds=args.max_runtime_snapshot_age_seconds,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.decision_lease_gate_json_output:
        _write_json(args.decision_lease_gate_json_output, packet["decision_lease_gate_artifact"])
    if args.guardian_risk_gate_json_output:
        _write_json(args.guardian_risk_gate_json_output, packet["guardian_risk_gate_artifact"])
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

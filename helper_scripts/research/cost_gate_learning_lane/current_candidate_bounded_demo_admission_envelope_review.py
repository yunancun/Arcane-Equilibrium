#!/usr/bin/env python3
"""Review the current candidate bounded Demo admission envelope.

This helper consumes the current-candidate runtime admission handoff plus the
GUI-backed current-candidate envelope and builds a no-order review packet for a
future bounded Demo admission. It does not emit authorization, create a Decision
Lease, pass Guardian/Rust gates, mutate runtime state, call Bybit, submit
orders, lower Cost Gate, or create profit proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    AUTHORITY_PATH_PATCH_READY_STATUS,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ORDER_AUTHORITY_GRANTED,
)
from cost_gate_learning_lane.standing_demo_authorization import (
    summarize_standing_demo_authorization,
)


SCHEMA_VERSION = "current_candidate_bounded_demo_admission_envelope_review_v1"
ADMISSION_ENVELOPE_PREVIEW_SCHEMA_VERSION = (
    "current_candidate_bounded_demo_admission_envelope_preview_v1"
)
DECISION_LEASE_GATE_SCHEMA_VERSION = "current_candidate_decision_lease_gate_evidence_v1"
GUARDIAN_RISK_GATE_SCHEMA_VERSION = "current_candidate_guardian_risk_gate_evidence_v1"
DECISION_LEASE_ACTIVE_STATUS = "DECISION_LEASE_ACTIVE"
GUARDIAN_RISK_GATE_PASS_STATUS = "GUARDIAN_RISK_GATE_PASS"
RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SOURCE = "runtime_governance_ipc_readonly_snapshot"

HANDOFF_SCHEMA_VERSION = "current_candidate_runtime_admission_handoff_review_v1"
HANDOFF_READY_STATUS = "CURRENT_CANDIDATE_RUNTIME_ADMISSION_HANDOFF_READY_NO_ORDER"
HANDOFF_PREVIEW_SCHEMA_VERSION = "current_candidate_runtime_admission_envelope_preview_v1"

CURRENT_ENVELOPE_SCHEMA_VERSION = "cost_gate_current_candidate_no_order_refresh_envelope_v1"
CURRENT_ENVELOPE_READY_STATUS = (
    "CURRENT_CANDIDATE_NO_ORDER_REFRESH_ENVELOPE_READY_NO_CAPTURE_NO_AUTHORITY"
)

BOUNDED_AUTH_PACKET_SCHEMA_VERSION = "bounded_demo_probe_operator_authorization_packet_v1"
PATCH_READINESS_SCHEMA_VERSION = "bounded_demo_probe_authority_patch_readiness_v1"

BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL"
)
NOT_READY_STATUS = "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_NOT_READY"
READY_NO_ORDER_STATUS = "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_ENVELOPE_READY_NO_ORDER"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 6 * 60 * 60
DEFAULT_MAX_AUTHORIZATION_TTL_HOURS = 24
DEFAULT_MAX_FRESH_BBO_AGE_MS = 1000

GUI_CAP_SOURCE = "current_candidate_envelope.cap_resolution.resolved_cap_usdt"
GUI_RISK_SOURCE = "GUI-backed Rust RiskConfig"

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
    "no-order current-candidate bounded Demo admission envelope review; no "
    "bounded authorization emission, no Decision Lease emission, no Guardian or "
    "Rust authority grant, no Bybit/private/order call, no order/cancel/modify, "
    "no PG write, no runtime/service/env/crontab mutation, no Cost Gate lowering, "
    "no live/mainnet authority, no promotion proof, and no profit proof"
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
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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


def _same_number(left: Any, right: Any, tolerance: float = 1e-8) -> bool:
    left_num = _float(left)
    right_num = _float(right)
    return (
        left_num is not None
        and right_num is not None
        and abs(left_num - right_num) <= tolerance
    )


def _cap_lineage_reasons(
    *,
    handoff: dict[str, Any],
    current_envelope: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    preview = _dict(handoff.get("admission_envelope_preview"))
    sizing = _dict(preview.get("sizing"))
    cap_resolution = _dict(current_envelope.get("cap_resolution"))
    summary = _dict(current_envelope.get("summary"))
    handoff_cap = _float(sizing.get("cap_usdt"))
    envelope_cap = _float(cap_resolution.get("resolved_cap_usdt"))
    rounded_notional = _float(sizing.get("rounded_notional_usdt"))
    per_trade_fraction = _float(cap_resolution.get("per_trade_risk_pct_fraction"))
    per_trade_display = _float(cap_resolution.get("per_trade_risk_pct_display"))
    position_size_max = _float(cap_resolution.get("position_size_max_pct"))

    if handoff_cap is None or handoff_cap <= 0:
        reasons.append("handoff_cap_usdt_missing_or_non_positive")
    if envelope_cap is None or envelope_cap <= 0:
        reasons.append("current_envelope_resolved_cap_usdt_missing_or_non_positive")
    if handoff_cap is not None and envelope_cap is not None and not _same_number(
        handoff_cap, envelope_cap
    ):
        reasons.append("handoff_cap_mismatch_current_envelope_resolved_cap")
    if sizing.get("cap_source") != GUI_CAP_SOURCE:
        reasons.append("handoff_cap_source_not_gui_resolved_cap")
    if cap_resolution.get("risk_source_of_truth") != GUI_RISK_SOURCE:
        reasons.append("risk_source_of_truth_not_gui_backed_rust_risk_config")
    if cap_resolution.get("gui_risk_config_is_authority") is not True:
        reasons.append("gui_risk_config_not_marked_authority")
    if cap_resolution.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("bounded_probe_local_cap_marked_authority")
    if summary.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("local_10_usdt_cap_marked_global_authority")
    if cap_resolution.get("account_equity_artifact_accepted") is not True:
        reasons.append("account_equity_artifact_not_accepted")
    if per_trade_fraction is None or per_trade_fraction <= 0:
        reasons.append("per_trade_risk_pct_fraction_missing_or_non_positive")
    elif per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_fraction_not_fraction")
    if (
        per_trade_fraction is not None
        and per_trade_display is not None
        and abs((per_trade_fraction * 100.0) - per_trade_display) > 1e-6
    ):
        reasons.append("per_trade_risk_pct_display_fraction_mismatch")
    if position_size_max is None or position_size_max <= 0:
        reasons.append("position_size_max_pct_missing_or_non_positive")
    if (
        rounded_notional is not None
        and handoff_cap is not None
        and rounded_notional > handoff_cap + 1e-8
    ):
        reasons.append("rounded_notional_exceeds_gui_resolved_cap")
    return sorted(set(reasons))


def _handoff_reasons(handoff: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION:
        reasons.append("handoff_schema_version_invalid")
    if handoff.get("status") != HANDOFF_READY_STATUS:
        reasons.append("handoff_status_not_ready")
    gates = _dict(handoff.get("gates"))
    required_true = {
        "handoff_ready_no_order",
        "cap_from_gui_resolved_equity",
        "candidate_alignment",
        "construction_constructible_under_cap",
        "no_authority_contamination",
        "public_quote_public_only",
        "schema_status_ready",
    }
    for key in sorted(required_true):
        if gates.get(key) is not True:
            reasons.append(f"handoff_gate_{key}_not_true")
    for key in ("runtime_admission_ready", "order_admission_ready"):
        if gates.get(key) is not False:
            reasons.append(f"handoff_gate_{key}_not_false")
    preview = _dict(handoff.get("admission_envelope_preview"))
    if preview.get("schema_version") != HANDOFF_PREVIEW_SCHEMA_VERSION:
        reasons.append("handoff_preview_schema_version_invalid")
    if preview.get("status") != "READY_FOR_SEPARATE_RUNTIME_ADMISSION_REVIEW":
        reasons.append("handoff_preview_status_not_ready")
    if preview.get("runtime_admission_ready") is not False:
        reasons.append("handoff_preview_runtime_admission_ready_not_false")
    if preview.get("order_admission_ready") is not False:
        reasons.append("handoff_preview_order_admission_ready_not_false")
    return sorted(set(reasons))


def _current_envelope_reasons(current_envelope: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if current_envelope.get("schema_version") != CURRENT_ENVELOPE_SCHEMA_VERSION:
        reasons.append("current_envelope_schema_version_invalid")
    if current_envelope.get("status") != CURRENT_ENVELOPE_READY_STATUS:
        reasons.append("current_envelope_status_not_ready")
    if _dict(current_envelope.get("summary")).get(
        "current_candidate_no_order_refresh_envelope_ready"
    ) is not True:
        reasons.append("current_envelope_summary_ready_not_true")
    if _dict(current_envelope.get("answers")).get("order_admission_ready") is not False:
        reasons.append("current_envelope_answers_order_admission_not_false")
    return sorted(set(reasons))


def _bounded_authorization_summary(
    packet: dict[str, Any] | None,
    *,
    artifact: dict[str, Any],
    candidate: dict[str, Any],
    now_utc: dt.datetime,
    max_authorization_ttl_hours: int,
) -> dict[str, Any]:
    payload = _dict(packet)
    auth = _dict(payload.get("operator_authorization"))
    expires_at = _parse_dt(auth.get("expires_at_utc"))
    expiry_valid = (
        expires_at is not None
        and expires_at > now_utc
        and expires_at <= now_utc + dt.timedelta(hours=max_authorization_ttl_hours)
    )
    auth_candidate = _candidate_identity(
        _dict(auth.get("candidate")) or _dict(payload.get("candidate"))
    )
    if not auth_candidate.get("side_cell_key"):
        auth_candidate["side_cell_key"] = auth.get("side_cell_key")
    candidate_matches = (
        bool(auth_candidate.get("side_cell_key"))
        and auth_candidate.get("side_cell_key") == candidate.get("side_cell_key")
    )
    no_live_or_cost_gate = not (
        _truthy(payload.get("live_authority_granted"))
        or _truthy(_dict(payload.get("answers")).get("live_authority_granted"))
        or payload.get("main_cost_gate_adjustment") not in (None, "", "NONE")
        or _dict(payload.get("answers")).get("main_cost_gate_adjustment")
        not in (None, "", "NONE")
        or _truthy(payload.get("promotion_evidence"))
        or _truthy(payload.get("promotion_proof"))
    )
    valid = (
        artifact.get("status") == "FRESH"
        and payload.get("schema_version") == BOUNDED_AUTH_PACKET_SCHEMA_VERSION
        and payload.get("status") == BOUNDED_PROBE_AUTHORIZED_STATUS
        and auth.get("schema_version") == BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION
        and auth.get("status") == BOUNDED_PROBE_AUTHORIZED_STATUS
        and auth.get("order_authority") == ORDER_AUTHORITY_GRANTED
        and auth.get("probe_authority_granted") is True
        and auth.get("order_authority_granted") is True
        and _int(auth.get("max_authorized_probe_orders")) > 0
        and candidate_matches
        and expiry_valid
        and no_live_or_cost_gate
    )
    return {
        "present": artifact.get("present") is True,
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "operator_authorization_present": bool(auth),
        "authorization_id": auth.get("authorization_id") or payload.get("authorization_id"),
        "operator_id": auth.get("operator_id") or payload.get("operator_id"),
        "candidate": auth_candidate,
        "candidate_matches": candidate_matches,
        "max_authorized_probe_orders": auth.get("max_authorized_probe_orders"),
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
        "expiry_valid": expiry_valid,
        "no_live_or_cost_gate": no_live_or_cost_gate,
        "valid_for_current_candidate": valid,
    }


def _decision_lease_summary(
    payload: dict[str, Any] | None,
    *,
    artifact: dict[str, Any],
    candidate: dict[str, Any],
    now_utc: dt.datetime,
) -> dict[str, Any]:
    data = _dict(payload)
    expires_at = _parse_dt(
        data.get("expires_at_utc") or data.get("lease_expires_at_utc")
    )
    lease_candidate = _candidate_identity(_dict(data.get("candidate")))
    candidate_matches = _candidate_aligned(candidate, lease_candidate)
    status = _str(data.get("status")).upper()
    source = _str(data.get("source"))
    valid = (
        artifact.get("status") == "FRESH"
        and data.get("schema_version") == DECISION_LEASE_GATE_SCHEMA_VERSION
        and source == RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SOURCE
        and bool(data.get("lease_id") or data.get("decision_lease_id"))
        and status == DECISION_LEASE_ACTIVE_STATUS
        and expires_at is not None
        and expires_at > now_utc
        and candidate_matches
        and data.get("demo_only") is True
        and _str(data.get("environment")).lower() == "demo"
        and data.get("decision_lease_acquire_performed") is not True
        and data.get("decision_lease_release_performed") is not True
        and data.get("order_admission_ready") is not True
    )
    return {
        "present": artifact.get("present") is True,
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "source": source or None,
        "lease_id": data.get("lease_id") or data.get("decision_lease_id"),
        "candidate": lease_candidate,
        "candidate_matches": candidate_matches,
        "environment": data.get("environment"),
        "demo_only": data.get("demo_only"),
        "expires_at_utc": expires_at.isoformat() if expires_at else None,
        "blocking_reasons": _list(data.get("blocking_reasons")),
        "valid_for_current_candidate": valid,
    }


def _guardian_risk_summary(
    payload: dict[str, Any] | None,
    *,
    artifact: dict[str, Any],
    candidate: dict[str, Any],
    resolved_cap_usdt: float | None,
) -> dict[str, Any]:
    data = _dict(payload)
    risk_candidate = _candidate_identity(_dict(data.get("candidate")))
    candidate_matches = _candidate_aligned(candidate, risk_candidate)
    status = _str(data.get("status")).upper()
    source = _str(data.get("source"))
    cap = _float(data.get("cap_usdt") or _dict(data.get("risk_limits")).get("cap_usdt"))
    cap_ok = cap is not None and resolved_cap_usdt is not None and cap <= resolved_cap_usdt
    risk_limits = _dict(data.get("risk_limits"))
    adjusted_cap = _float(risk_limits.get("guardian_adjusted_cap_usdt") or cap)
    rounded_notional = _float(risk_limits.get("rounded_notional_usdt"))
    rounded_ok = (
        rounded_notional is not None
        and adjusted_cap is not None
        and rounded_notional <= adjusted_cap + 1e-8
    )
    valid = (
        artifact.get("status") == "FRESH"
        and data.get("schema_version") == GUARDIAN_RISK_GATE_SCHEMA_VERSION
        and source == RUNTIME_GOVERNANCE_IPC_SNAPSHOT_SOURCE
        and status == GUARDIAN_RISK_GATE_PASS_STATUS
        and candidate_matches
        and cap_ok
        and _str(data.get("environment")).lower() == "demo"
        and _str(data.get("risk_level")).upper() == "NORMAL"
        and data.get("new_entries_allowed") is True
        and data.get("reduce_only") is not True
        and data.get("active_de_risking") is not True
        and data.get("requires_operator") is not True
        and data.get("emergency_stops") is not True
        and rounded_ok
        and data.get("order_admission_ready") is not True
    )
    return {
        "present": artifact.get("present") is True,
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "source": source or None,
        "candidate": risk_candidate,
        "candidate_matches": candidate_matches,
        "environment": data.get("environment"),
        "risk_level": data.get("risk_level"),
        "new_entries_allowed": data.get("new_entries_allowed"),
        "cap_usdt": cap,
        "guardian_adjusted_cap_usdt": adjusted_cap,
        "rounded_notional_usdt": rounded_notional,
        "rounded_notional_lte_guardian_adjusted_cap": rounded_ok,
        "cap_lte_gui_resolved_cap": cap_ok,
        "blocking_reasons": _list(data.get("blocking_reasons")),
        "valid_for_current_candidate": valid,
    }


def _rust_authority_summary(
    payload: dict[str, Any] | None,
    *,
    artifact: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    data = _dict(payload)
    candidate_payload = _dict(data.get("candidate")) or _dict(
        _dict(data.get("placement_repair_plan")).get("candidate")
    )
    rust_candidate = _candidate_identity(candidate_payload)
    candidate_matches = _candidate_aligned(candidate, rust_candidate)
    answers = _dict(data.get("answers"))
    valid = (
        artifact.get("status") == "FRESH"
        and data.get("schema_version") == PATCH_READINESS_SCHEMA_VERSION
        and data.get("status") == AUTHORITY_PATH_PATCH_READY_STATUS
        and answers.get("rust_near_touch_authority_adapter_present") is True
        and answers.get("rust_authority_path_wiring_present") is True
        and candidate_matches
    )
    return {
        "present": artifact.get("present") is True,
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "candidate": rust_candidate,
        "candidate_matches": candidate_matches,
        "rust_near_touch_authority_adapter_present": answers.get(
            "rust_near_touch_authority_adapter_present"
        )
        is True,
        "rust_authority_path_wiring_present": answers.get(
            "rust_authority_path_wiring_present"
        )
        is True,
        "valid_for_current_candidate_review": valid,
    }


def _gate(name: str, passed: bool, reason: str, evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "passed": passed,
        "reason": reason,
        "evidence": evidence,
    }


def build_current_candidate_bounded_demo_admission_envelope_review(
    *,
    handoff: dict[str, Any] | None,
    current_envelope: dict[str, Any] | None,
    standing_demo_authorization: dict[str, Any] | None = None,
    bounded_authorization: dict[str, Any] | None = None,
    decision_lease: dict[str, Any] | None = None,
    guardian_risk_gate: dict[str, Any] | None = None,
    rust_authority_path: dict[str, Any] | None = None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    max_authorization_ttl_hours: int = DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    max_fresh_bbo_age_ms: int = DEFAULT_MAX_FRESH_BBO_AGE_MS,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds < 60 or max_artifact_age_seconds > 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in [60, 86400]")
    if max_authorization_ttl_hours < 1 or max_authorization_ttl_hours > 24 * 7:
        raise ValueError("max_authorization_ttl_hours must be in [1, 168]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    handoff_payload = _dict(handoff)
    current_payload = _dict(current_envelope)
    standing_payload = _dict(standing_demo_authorization)
    bounded_payload = _dict(bounded_authorization)
    lease_payload = _dict(decision_lease)
    guardian_payload = _dict(guardian_risk_gate)
    rust_payload = _dict(rust_authority_path)

    artifacts = {
        "handoff": _artifact_summary(
            name="handoff",
            path=paths.get("handoff"),
            payload=handoff_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=True,
        ),
        "current_envelope": _artifact_summary(
            name="current_envelope",
            path=paths.get("current_envelope"),
            payload=current_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=True,
        ),
        "standing_demo_authorization": _artifact_summary(
            name="standing_demo_authorization",
            path=paths.get("standing_demo_authorization"),
            payload=standing_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
        "bounded_authorization": _artifact_summary(
            name="bounded_authorization",
            path=paths.get("bounded_authorization"),
            payload=bounded_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
        "decision_lease": _artifact_summary(
            name="decision_lease",
            path=paths.get("decision_lease"),
            payload=lease_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
        "guardian_risk_gate": _artifact_summary(
            name="guardian_risk_gate",
            path=paths.get("guardian_risk_gate"),
            payload=guardian_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
        "rust_authority_path": _artifact_summary(
            name="rust_authority_path",
            path=paths.get("rust_authority_path"),
            payload=rust_payload,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=False,
        ),
    }

    source_reasons: list[str] = []
    for name in ("handoff", "current_envelope"):
        if artifacts[name]["status"] != "FRESH":
            source_reasons.append(f"{name}_artifact_not_fresh")
    source_reasons.extend(_handoff_reasons(handoff_payload))
    source_reasons.extend(_current_envelope_reasons(current_payload))

    candidate = _candidate_identity(_dict(handoff_payload.get("candidate")))
    current_candidate = _candidate_identity(_dict(current_payload.get("candidate")))
    preview = _dict(handoff_payload.get("admission_envelope_preview"))
    preview_candidate = _candidate_identity(_dict(preview.get("candidate")))
    candidate_alignment = _candidate_aligned(candidate, current_candidate, preview_candidate)
    if not candidate_alignment:
        source_reasons.append("candidate_alignment_failed")

    cap_reasons = _cap_lineage_reasons(
        handoff=handoff_payload,
        current_envelope=current_payload,
    )
    source_reasons.extend(cap_reasons)

    authority_reasons: list[str] = []
    for name, payload in (
        ("handoff", handoff_payload),
        ("current_envelope", current_payload),
        ("standing_demo_authorization", standing_payload),
        ("decision_lease", lease_payload),
        ("guardian_risk_gate", guardian_payload),
        ("rust_authority_path", rust_payload),
    ):
        if payload:
            authority_reasons.extend(
                f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
            )

    cap_resolution = _dict(current_payload.get("cap_resolution"))
    sizing = _dict(preview.get("sizing"))
    market = _dict(preview.get("market"))
    resolved_cap = _float(cap_resolution.get("resolved_cap_usdt"))
    rounded_notional = _float(sizing.get("rounded_notional_usdt"))
    bbo_age = _float(market.get("bbo_age_ms_at_capture"))

    standing_summary = summarize_standing_demo_authorization(
        standing_payload,
        artifacts["standing_demo_authorization"],
        now_utc=now,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
        candidate=candidate,
    )
    bounded_summary = _bounded_authorization_summary(
        bounded_payload,
        artifact=artifacts["bounded_authorization"],
        candidate=candidate,
        now_utc=now,
        max_authorization_ttl_hours=max_authorization_ttl_hours,
    )
    lease_summary = _decision_lease_summary(
        lease_payload,
        artifact=artifacts["decision_lease"],
        candidate=candidate,
        now_utc=now,
    )
    guardian_summary = _guardian_risk_summary(
        guardian_payload,
        artifact=artifacts["guardian_risk_gate"],
        candidate=candidate,
        resolved_cap_usdt=resolved_cap,
    )
    rust_summary = _rust_authority_summary(
        rust_payload,
        artifact=artifacts["rust_authority_path"],
        candidate=candidate,
    )

    review_contract_ready = not source_reasons and not authority_reasons
    standing_valid = (
        not standing_payload
        or standing_summary.get("valid_for_candidate_scoped_authorization") is True
    )
    bounded_valid = bounded_summary.get("valid_for_current_candidate") is True
    lease_valid = lease_summary.get("valid_for_current_candidate") is True
    guardian_valid = guardian_summary.get("valid_for_current_candidate") is True
    rust_valid = rust_summary.get("valid_for_current_candidate_review") is True
    fresh_bbo_at_actual_admission = False

    admission_gates = [
        _gate(
            "review_contract_ready",
            review_contract_ready,
            "handoff and GUI risk cap lineage must be fresh, aligned, and no-authority",
            {
                "source_reasons": sorted(set(source_reasons)),
                "authority_reasons": sorted(set(authority_reasons)),
            },
        ),
        _gate(
            "gui_risk_cap_lineage",
            not cap_reasons,
            "per-order cap must resolve from GUI-backed Rust RiskConfig plus accepted Demo equity",
            {
                "cap_reasons": cap_reasons,
                "risk_source_of_truth": cap_resolution.get("risk_source_of_truth"),
                "per_trade_risk_pct_fraction": cap_resolution.get(
                    "per_trade_risk_pct_fraction"
                ),
                "per_trade_risk_pct_display": cap_resolution.get(
                    "per_trade_risk_pct_display"
                ),
                "position_size_max_pct": cap_resolution.get("position_size_max_pct"),
                "resolved_cap_usdt": resolved_cap,
                "cap_source": sizing.get("cap_source"),
                "bounded_probe_local_cap_usdt_is_authority": cap_resolution.get(
                    "bounded_probe_local_cap_usdt_is_authority"
                ),
            },
        ),
        _gate(
            "standing_demo_authorization_valid_if_supplied",
            standing_valid,
            "supplied standing Demo envelope must match the current candidate and remain Demo-only",
            standing_summary,
        ),
        _gate(
            "bounded_demo_authorization_object_valid",
            bounded_valid,
            "current candidate needs an explicit bounded Demo authorization object before runtime admission",
            bounded_summary,
        ),
        _gate(
            "decision_lease_valid",
            lease_valid,
            "a current-candidate Decision Lease is required before order-capable admission",
            lease_summary,
        ),
        _gate(
            "guardian_risk_gate_valid",
            guardian_valid,
            "Guardian/risk gate must pass for the current candidate under the GUI-resolved cap",
            guardian_summary,
        ),
        _gate(
            "rust_authority_path_valid",
            rust_valid,
            "Rust authority path/readiness must match the current candidate",
            rust_summary,
        ),
        _gate(
            "fresh_bbo_refresh_at_actual_admission",
            fresh_bbo_at_actual_admission,
            "public BBO in the handoff is construction evidence only; actual admission must refresh BBO",
            {
                "bbo_age_ms_at_capture": bbo_age,
                "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
            },
        ),
    ]
    blockers = [gate["name"] for gate in admission_gates if gate["passed"] is not True]
    if authority_reasons:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation"
    elif source_reasons:
        status = NOT_READY_STATUS
        reason = "input_handoff_or_gui_cap_lineage_not_ready"
    elif blockers:
        status = BLOCKED_BY_LOSS_CONTROL_STATUS
        reason = "loss_control_runtime_admission_prerequisites_missing"
    else:
        status = READY_NO_ORDER_STATUS
        reason = "admission_envelope_review_ready_no_order"

    runtime_admission_ready = False
    order_admission_ready = False
    envelope_preview = {
        "schema_version": ADMISSION_ENVELOPE_PREVIEW_SCHEMA_VERSION,
        "status": "REVIEW_READY_NO_ORDER" if review_contract_ready else "NOT_READY",
        "candidate": candidate,
        "risk_limits": {
            "per_order_cap_usdt": resolved_cap,
            "cap_source": GUI_CAP_SOURCE,
            "risk_source_of_truth": GUI_RISK_SOURCE,
            "account_equity_usdt": cap_resolution.get("account_equity_usdt"),
            "per_trade_risk_pct_fraction": cap_resolution.get(
                "per_trade_risk_pct_fraction"
            ),
            "per_trade_risk_pct_display": cap_resolution.get(
                "per_trade_risk_pct_display"
            ),
            "position_size_max_pct": cap_resolution.get("position_size_max_pct"),
            "single_position_budget_usdt": cap_resolution.get(
                "single_position_budget_usdt"
            ),
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
        },
        "order_shape": {
            "limit_price": sizing.get("limit_price"),
            "rounded_qty": sizing.get("rounded_qty"),
            "rounded_notional_usdt": rounded_notional,
            "placement_mode": sizing.get("placement_mode"),
            "notional_lte_gui_resolved_cap": (
                rounded_notional is not None
                and resolved_cap is not None
                and rounded_notional <= resolved_cap + 1e-8
            ),
        },
        "market": {
            "best_bid": market.get("best_bid"),
            "best_ask": market.get("best_ask"),
            "bbo_age_ms_at_capture": bbo_age,
            "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
            "fresh_bbo_must_be_refreshed_at_actual_admission": True,
        },
        "runtime_admission_ready": runtime_admission_ready,
        "order_admission_ready": order_admission_ready,
        "required_gates_before_order_capable_action": [
            "bounded_demo_authorization_object_valid",
            "decision_lease_valid",
            "guardian_risk_gate_valid",
            "rust_authority_path_valid",
            "fresh_bbo_refresh_at_actual_admission",
        ],
        "boundary": "review only; no order/probe/live authority",
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": artifacts,
        "candidate_alignment": {
            "aligned": candidate_alignment,
            "handoff": candidate,
            "current_envelope": current_candidate,
            "handoff_preview": preview_candidate,
        },
        "risk_semantics": {
            "gui_risk_config_is_source_of_truth": True,
            "gui_p1_risk_trade_pct": cap_resolution.get("per_trade_risk_pct_display"),
            "per_trade_risk_pct_fraction": cap_resolution.get(
                "per_trade_risk_pct_fraction"
            ),
            "position_size_max_pct": cap_resolution.get("position_size_max_pct"),
            "account_equity_usdt": cap_resolution.get("account_equity_usdt"),
            "resolved_cap_usdt": resolved_cap,
            "cap_source": GUI_CAP_SOURCE,
            "rounded_notional_usdt": rounded_notional,
            "local_10_usdt_cap_is_global_risk_authority": False,
            "bounded_probe_local_cap_usdt_is_authority": False,
            "gui_percent_semantics": (
                "GUI 10.0% means per_trade_risk_pct=0.1; local 10 USDT "
                "bounded-probe diagnostics cannot become runtime admission cap"
            ),
        },
        "admission_envelope_preview": envelope_preview,
        "admission_gates": admission_gates,
        "runtime_admission_blockers": blockers,
        "blocking_gates": sorted(set(source_reasons + authority_reasons + blockers)),
        "blocking_gate_count": len(set(source_reasons + authority_reasons + blockers)),
        "source_blockers": sorted(set(source_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "standing_demo_authorization": standing_summary,
        "bounded_authorization": bounded_summary,
        "decision_lease": lease_summary,
        "guardian_risk_gate": guardian_summary,
        "rust_authority_path": rust_summary,
        "answers": {
            "review_contract_ready": review_contract_ready,
            "runtime_admission_ready": runtime_admission_ready,
            "order_admission_ready": order_admission_ready,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "decision_lease_emitted": False,
            "guardian_risk_gate_passed_by_this_packet": False,
            "rust_authority_granted_by_this_packet": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
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


def render_markdown(review: dict[str, Any]) -> str:
    candidate = _dict(review.get("candidate"))
    risk = _dict(review.get("risk_semantics"))
    preview = _dict(review.get("admission_envelope_preview"))
    order_shape = _dict(preview.get("order_shape"))
    lines = [
        "# Current Candidate Bounded Demo Admission Envelope Review",
        "",
        f"- Status: `{review.get('status')}`",
        f"- Reason: `{review.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- GUI P1 risk/trade: `{risk.get('gui_p1_risk_trade_pct')}%`",
        f"- Resolved GUI cap USDT: `{risk.get('resolved_cap_usdt')}`",
        f"- Rounded notional USDT: `{order_shape.get('rounded_notional_usdt')}`",
        f"- Runtime admission ready: `{_dict(review.get('answers')).get('runtime_admission_ready')}`",
        f"- Order admission ready: `{_dict(review.get('answers')).get('order_admission_ready')}`",
        "",
        "## Admission Gates",
    ]
    for gate in _list(review.get("admission_gates")):
        lines.append(f"- `{gate.get('name')}`: `{gate.get('passed')}`")
    lines.extend(["", "## Runtime Admission Blockers"])
    blockers = _list(review.get("runtime_admission_blockers"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--handoff-json", type=Path, required=True)
    parser.add_argument("--current-envelope-json", type=Path, required=True)
    parser.add_argument("--standing-demo-authorization-json", type=Path)
    parser.add_argument("--bounded-authorization-json", type=Path)
    parser.add_argument("--decision-lease-json", type=Path)
    parser.add_argument("--guardian-risk-gate-json", type=Path)
    parser.add_argument("--rust-authority-path-json", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--max-artifact-age-seconds",
        type=int,
        default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-authorization-ttl-hours",
        type=int,
        default=DEFAULT_MAX_AUTHORIZATION_TTL_HOURS,
    )
    parser.add_argument(
        "--max-fresh-bbo-age-ms",
        type=int,
        default=DEFAULT_MAX_FRESH_BBO_AGE_MS,
    )
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    review = build_current_candidate_bounded_demo_admission_envelope_review(
        handoff=_read_json(args.handoff_json),
        current_envelope=_read_json(args.current_envelope_json),
        standing_demo_authorization=_read_json(args.standing_demo_authorization_json),
        bounded_authorization=_read_json(args.bounded_authorization_json),
        decision_lease=_read_json(args.decision_lease_json),
        guardian_risk_gate=_read_json(args.guardian_risk_gate_json),
        rust_authority_path=_read_json(args.rust_authority_path_json),
        paths={
            "handoff": args.handoff_json,
            "current_envelope": args.current_envelope_json,
            "standing_demo_authorization": args.standing_demo_authorization_json,
            "bounded_authorization": args.bounded_authorization_json,
            "decision_lease": args.decision_lease_json,
            "guardian_risk_gate": args.guardian_risk_gate_json,
            "rust_authority_path": args.rust_authority_path_json,
        },
        max_artifact_age_seconds=args.max_artifact_age_seconds,
        max_authorization_ttl_hours=args.max_authorization_ttl_hours,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, review)
    if args.output:
        _write_text(args.output, render_markdown(review))
    if args.print_json:
        print(json.dumps(review, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

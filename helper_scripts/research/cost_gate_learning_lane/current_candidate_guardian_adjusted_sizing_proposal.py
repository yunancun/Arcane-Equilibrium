#!/usr/bin/env python3
"""Build a no-order Guardian-adjusted sizing proposal for the current candidate.

The helper consumes already-reviewed current-candidate admission and Guardian
gate evidence. It proposes a smaller order shape under the runtime
Guardian-adjusted cap, but it does not refresh BBO, acquire a Decision Lease,
grant authority, mutate runtime state, call Bybit, query/write PG, or submit an
order.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "current_candidate_guardian_adjusted_sizing_proposal_v1"

READY_STATUS = "CURRENT_CANDIDATE_GUARDIAN_ADJUSTED_SIZING_PROPOSAL_READY_NO_ORDER"
NOT_READY_STATUS = "CURRENT_CANDIDATE_GUARDIAN_ADJUSTED_SIZING_PROPOSAL_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

ADMISSION_REVIEW_SCHEMA_VERSION = (
    "current_candidate_bounded_demo_admission_envelope_review_v1"
)
ADMISSION_REVIEW_BLOCKED_STATUS = (
    "CURRENT_CANDIDATE_BOUNDED_DEMO_ADMISSION_BLOCKED_BY_LOSS_CONTROL"
)
GATE_EVIDENCE_SCHEMA_VERSION = (
    "current_candidate_decision_lease_guardian_gate_evidence_v1"
)
GATE_EVIDENCE_BLOCKED_STATUS = (
    "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_BLOCKED_BY_LOSS_CONTROL"
)
CONSTRUCTION_PREVIEW_SCHEMA_VERSION = "current_candidate_no_order_construction_preview_v1"
CONSTRUCTION_PREVIEW_READY_STATUS = "CURRENT_CANDIDATE_CONSTRUCTION_PREVIEW_READY_NO_ORDER"

DEFAULT_MAX_ARTIFACT_AGE_SECONDS = 24 * 60 * 60

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "bounded_demo_probe_authorized",
    "bybit_private_call_performed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cost_gate_lowering_performed",
    "decision_lease_acquire_performed",
    "decision_lease_release_performed",
    "global_cost_gate_lowering_recommended",
    "lease_acquire_performed",
    "lease_release_performed",
    "live_authority_granted",
    "live_execution_allowed",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_write_performed",
    "placement_call_performed",
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
    "no-order Guardian-adjusted sizing proposal; no fresh BBO refresh, no "
    "Decision Lease acquire/release, no Guardian/Rust authority grant, no "
    "Bybit/private/order call, no order/cancel/modify, no PG write, no "
    "runtime/service/env/crontab mutation, no Cost Gate lowering, no "
    "live/mainnet authority, and no profit proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _dec(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _round_decimal(value: Decimal | None, places: int = 8) -> float | None:
    if value is None:
        return None
    quant = Decimal("1").scaleb(-places)
    return float(value.quantize(quant))


def _same_decimal(
    left: Decimal | None,
    right: Decimal | None,
    *,
    tolerance: Decimal = Decimal("0.00000001"),
) -> bool:
    return left is not None and right is not None and abs(left - right) <= tolerance


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
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


def _admission_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if payload.get("schema_version") != ADMISSION_REVIEW_SCHEMA_VERSION:
        reasons.append("admission_review_schema_invalid")
    if payload.get("status") != ADMISSION_REVIEW_BLOCKED_STATUS:
        reasons.append("admission_review_status_not_blocked_by_loss_control")
    answers = _dict(payload.get("answers"))
    if answers.get("review_contract_ready") is not True:
        reasons.append("admission_review_contract_not_ready")
    if answers.get("runtime_admission_ready") is not False:
        reasons.append("admission_runtime_admission_ready_not_false")
    if answers.get("order_admission_ready") is not False:
        reasons.append("admission_order_admission_ready_not_false")
    if _list(payload.get("source_blockers")):
        reasons.append("admission_source_blockers_present")
    if _list(payload.get("authority_contamination_reasons")):
        reasons.append("admission_authority_contamination_present")
    return sorted(set(reasons))


def _gate_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if payload.get("schema_version") != GATE_EVIDENCE_SCHEMA_VERSION:
        reasons.append("gate_evidence_schema_invalid")
    if payload.get("status") != GATE_EVIDENCE_BLOCKED_STATUS:
        reasons.append("gate_evidence_status_not_blocked_by_loss_control")
    guardian = _dict(payload.get("guardian_risk_gate_artifact"))
    guardian_reasons = set(_list(guardian.get("blocking_reasons")))
    guardian_valid = guardian.get("valid_for_current_candidate") is True
    guardian_status = _str(guardian.get("status")).upper()
    guardian_pass = guardian_valid or guardian_status == "GUARDIAN_RISK_GATE_PASS"
    if guardian_pass:
        if guardian_reasons:
            reasons.append("guardian_gate_pass_has_blocking_reasons")
    else:
        if "rounded_notional_exceeds_guardian_adjusted_cap" not in guardian_reasons:
            reasons.append("guardian_adjusted_cap_breach_not_present")
        if guardian.get("valid_for_current_candidate") is not False:
            reasons.append("guardian_gate_not_explicitly_invalid")
    if _dict(payload.get("answers")).get("runtime_admission_ready") is not False:
        reasons.append("gate_evidence_runtime_admission_ready_not_false")
    return sorted(set(reasons))


def _construction_reasons(payload: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if payload.get("schema_version") != CONSTRUCTION_PREVIEW_SCHEMA_VERSION:
        reasons.append("construction_preview_schema_invalid")
    if payload.get("status") != CONSTRUCTION_PREVIEW_READY_STATUS:
        reasons.append("construction_preview_status_not_ready")
    construction = _dict(payload.get("construction"))
    for key in ("limit_price", "qty_step", "min_notional", "rounded_qty"):
        value = _dec(construction.get(key))
        if value is None or value <= 0:
            reasons.append(f"construction_{key}_missing_or_non_positive")
    return sorted(set(reasons))


def _risk_lineage_reasons(
    *,
    admission: dict[str, Any],
    gate_evidence: dict[str, Any],
    construction_preview: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    admission_preview = _dict(admission.get("admission_envelope_preview"))
    risk_limits = _dict(admission_preview.get("risk_limits"))
    risk = _dict(admission.get("risk_semantics"))
    guardian = _dict(gate_evidence.get("guardian_risk_gate_artifact"))
    guardian_limits = _dict(guardian.get("risk_limits"))
    construction = _dict(construction_preview.get("construction"))

    if risk.get("gui_risk_config_is_source_of_truth") is not True:
        reasons.append("admission_gui_risk_config_not_source_of_truth")
    if risk.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("admission_local_10_usdt_cap_marked_authority")
    if risk.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("admission_bounded_probe_local_cap_marked_authority")
    if risk_limits.get("bounded_probe_local_cap_usdt_is_authority") is not False:
        reasons.append("admission_risk_limits_bounded_probe_local_cap_marked_authority")
    if risk_limits.get("local_10_usdt_cap_is_global_risk_authority") is not False:
        reasons.append("admission_risk_limits_local_10_usdt_cap_marked_authority")
    if risk.get("cap_source") != "current_candidate_envelope.cap_resolution.resolved_cap_usdt":
        reasons.append("admission_risk_cap_source_not_gui_resolved_cap")
    if (
        risk_limits.get("cap_source")
        != "current_candidate_envelope.cap_resolution.resolved_cap_usdt"
    ):
        reasons.append("admission_risk_limits_cap_source_not_gui_resolved_cap")
    if risk_limits.get("risk_source_of_truth") != "GUI-backed Rust RiskConfig":
        reasons.append("admission_risk_source_not_gui_backed_rust_risk_config")

    risk_cap = _dec(risk.get("resolved_cap_usdt"))
    preview_cap = _dec(risk_limits.get("per_order_cap_usdt"))
    guardian_gui_cap = _dec(guardian_limits.get("gui_resolved_cap_usdt"))
    construction_cap = _dec(construction.get("cap_usdt"))
    cap_values = {
        "admission_risk_resolved_cap_usdt": risk_cap,
        "admission_preview_per_order_cap_usdt": preview_cap,
        "guardian_gui_resolved_cap_usdt": guardian_gui_cap,
        "construction_cap_usdt": construction_cap,
    }
    for name, value in cap_values.items():
        if value is None or value <= 0:
            reasons.append(f"{name}_missing_or_non_positive")
    if not _same_decimal(risk_cap, preview_cap):
        reasons.append("admission_risk_cap_mismatch_preview_per_order_cap")
    if not _same_decimal(risk_cap, guardian_gui_cap):
        reasons.append("admission_risk_cap_mismatch_guardian_gui_cap")
    if not _same_decimal(risk_cap, construction_cap):
        reasons.append("admission_risk_cap_mismatch_construction_cap")

    adjusted_cap = _dec(guardian_limits.get("guardian_adjusted_cap_usdt"))
    if adjusted_cap is None or adjusted_cap <= 0:
        reasons.append("guardian_adjusted_cap_missing_or_non_positive")
    elif risk_cap is not None and adjusted_cap > risk_cap:
        reasons.append("guardian_adjusted_cap_exceeds_gui_resolved_cap")

    per_trade_fraction = _dec(
        risk_limits.get("per_trade_risk_pct_fraction")
        or risk.get("per_trade_risk_pct_fraction")
    )
    per_trade_display = _dec(
        risk_limits.get("per_trade_risk_pct_display")
        or risk.get("gui_p1_risk_trade_pct")
    )
    position_size_max_pct = _dec(
        risk_limits.get("position_size_max_pct") or risk.get("position_size_max_pct")
    )
    account_equity = _dec(
        risk_limits.get("account_equity_usdt") or risk.get("account_equity_usdt")
    )
    single_position_budget = _dec(
        risk_limits.get("single_position_budget_usdt")
        or risk.get("single_position_budget_usdt")
    )
    if per_trade_fraction is None or per_trade_fraction <= 0:
        reasons.append("per_trade_risk_pct_fraction_missing_or_non_positive")
    elif per_trade_fraction > 1:
        reasons.append("per_trade_risk_pct_fraction_not_fraction")
    if per_trade_display is None or per_trade_display <= 0:
        reasons.append("per_trade_risk_pct_display_missing_or_non_positive")
    elif (
        per_trade_fraction is not None
        and per_trade_fraction > 0
        and abs((per_trade_fraction * Decimal("100")) - per_trade_display)
        > Decimal("0.000001")
    ):
        reasons.append("per_trade_risk_pct_display_fraction_mismatch")
    if position_size_max_pct is None or position_size_max_pct <= 0:
        reasons.append("position_size_max_pct_missing_or_non_positive")
    if account_equity is None or account_equity <= 0:
        reasons.append("account_equity_usdt_missing_or_non_positive")
    if single_position_budget is None or single_position_budget <= 0:
        reasons.append("single_position_budget_usdt_missing_or_non_positive")
    if (
        account_equity is not None
        and account_equity > 0
        and per_trade_fraction is not None
        and per_trade_fraction > 0
        and risk_cap is not None
    ):
        expected_cap = account_equity * per_trade_fraction
        if not _same_decimal(risk_cap, expected_cap):
            reasons.append("gui_resolved_cap_not_equity_times_per_trade_pct")
    if (
        account_equity is not None
        and account_equity > 0
        and position_size_max_pct is not None
        and position_size_max_pct > 0
        and single_position_budget is not None
    ):
        expected_single_position_budget = (
            account_equity * position_size_max_pct / Decimal("100")
        )
        if not _same_decimal(single_position_budget, expected_single_position_budget):
            reasons.append(
                "single_position_budget_not_equity_times_position_size_max_pct"
            )
    return sorted(set(reasons))


def _extract_inputs(
    admission: dict[str, Any],
    gate_evidence: dict[str, Any],
    construction_preview: dict[str, Any],
) -> dict[str, Any]:
    admission_preview = _dict(admission.get("admission_envelope_preview"))
    order_shape = _dict(admission_preview.get("order_shape"))
    risk_limits = _dict(admission_preview.get("risk_limits"))
    risk = _dict(admission.get("risk_semantics"))
    construction = _dict(construction_preview.get("construction"))
    guardian = _dict(gate_evidence.get("guardian_risk_gate_artifact"))
    guardian_limits = _dict(guardian.get("risk_limits"))
    return {
        "candidate": _candidate_identity(
            _dict(admission.get("candidate")) or _dict(construction_preview.get("candidate"))
        ),
        "gate_candidate": _candidate_identity(_dict(gate_evidence.get("candidate"))),
        "construction_candidate": _candidate_identity(
            _dict(construction_preview.get("candidate"))
        ),
        "gui_resolved_cap_usdt": _dec(
            risk_limits.get("per_order_cap_usdt")
            or guardian_limits.get("gui_resolved_cap_usdt")
        ),
        "guardian_adjusted_cap_usdt": _dec(
            guardian_limits.get("guardian_adjusted_cap_usdt") or guardian.get("cap_usdt")
        ),
        "position_size_multiplier": _dec(guardian.get("position_size_multiplier")),
        "risk_level": guardian.get("risk_level"),
        "cap_source": risk.get("cap_source") or risk_limits.get("cap_source"),
        "risk_source_of_truth": risk_limits.get("risk_source_of_truth"),
        "per_trade_risk_pct_fraction": _dec(
            risk_limits.get("per_trade_risk_pct_fraction")
            or risk.get("per_trade_risk_pct_fraction")
        ),
        "per_trade_risk_pct_display": _dec(
            risk_limits.get("per_trade_risk_pct_display")
            or risk.get("gui_p1_risk_trade_pct")
        ),
        "position_size_max_pct": _dec(
            risk_limits.get("position_size_max_pct") or risk.get("position_size_max_pct")
        ),
        "account_equity_usdt": _dec(
            risk_limits.get("account_equity_usdt") or risk.get("account_equity_usdt")
        ),
        "single_position_budget_usdt": _dec(risk_limits.get("single_position_budget_usdt")),
        "original_limit_price": _dec(order_shape.get("limit_price") or construction.get("limit_price")),
        "original_rounded_qty": _dec(
            order_shape.get("rounded_qty") or construction.get("rounded_qty")
        ),
        "original_rounded_notional_usdt": _dec(
            order_shape.get("rounded_notional_usdt")
            or construction.get("rounded_notional_usdt")
        ),
        "qty_step": _dec(construction.get("qty_step")),
        "min_notional": _dec(construction.get("min_notional")),
        "tick_size": _dec(construction.get("tick_size")),
        "placement_mode": order_shape.get("placement_mode") or construction.get("placement_mode"),
    }


def _build_sizing(inputs: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    adjusted_cap = inputs["guardian_adjusted_cap_usdt"]
    gui_cap = inputs["gui_resolved_cap_usdt"]
    single_position_budget = inputs["single_position_budget_usdt"]
    limit_price = inputs["original_limit_price"]
    qty_step = inputs["qty_step"]
    min_notional = inputs["min_notional"]
    original_qty = inputs["original_rounded_qty"]
    original_notional = inputs["original_rounded_notional_usdt"]

    for name, value in (
        ("guardian_adjusted_cap_usdt", adjusted_cap),
        ("gui_resolved_cap_usdt", gui_cap),
        ("single_position_budget_usdt", single_position_budget),
        ("limit_price", limit_price),
        ("qty_step", qty_step),
        ("min_notional", min_notional),
        ("original_rounded_qty", original_qty),
        ("original_rounded_notional_usdt", original_notional),
    ):
        if value is None or value <= 0:
            reasons.append(f"{name}_missing_or_non_positive")
    if reasons:
        return {}, sorted(set(reasons))

    min_qty = _ceil_to_step(min_notional / limit_price, qty_step)
    max_qty_under_guardian_cap = _floor_to_step(adjusted_cap / limit_price, qty_step)
    effective_single_order_cap = min(adjusted_cap, gui_cap, single_position_budget)
    max_qty_under_effective_cap = _floor_to_step(
        effective_single_order_cap / limit_price,
        qty_step,
    )
    if max_qty_under_effective_cap < min_qty:
        reasons.append("effective_single_order_cap_below_min_executable_notional")
        if max_qty_under_guardian_cap < min_qty:
            reasons.append("guardian_adjusted_cap_below_min_executable_notional")
    proposed_qty = min(original_qty, max_qty_under_effective_cap)
    proposed_notional = proposed_qty * limit_price
    if proposed_notional > adjusted_cap:
        reasons.append("proposed_notional_exceeds_guardian_adjusted_cap")
    if proposed_notional > gui_cap:
        reasons.append("proposed_notional_exceeds_gui_resolved_cap")
    if proposed_notional > single_position_budget:
        reasons.append("proposed_notional_exceeds_single_position_budget")
    if proposed_notional > effective_single_order_cap:
        reasons.append("proposed_notional_exceeds_effective_single_order_cap")
    if proposed_notional < min_notional:
        reasons.append("proposed_notional_below_min_notional")
    original_exceeds_effective_cap = (
        original_notional > adjusted_cap
        or original_notional > gui_cap
        or original_notional > single_position_budget
        or original_notional > effective_single_order_cap
    )
    if original_exceeds_effective_cap and proposed_qty >= original_qty:
        reasons.append("proposed_qty_not_reduced_from_original")

    qty_delta = proposed_qty - original_qty
    notional_delta = proposed_notional - original_notional
    reduction_pct = (Decimal("1") - (proposed_notional / original_notional)) * Decimal("100")
    cap_utilization_pct = (proposed_notional / adjusted_cap) * Decimal("100")
    effective_cap_utilization_pct = (
        proposed_notional / effective_single_order_cap
    ) * Decimal("100")
    return {
        "limit_price": _round_decimal(limit_price),
        "qty_step": _round_decimal(qty_step),
        "min_notional": _round_decimal(min_notional),
        "min_executable_qty": _round_decimal(min_qty),
        "max_qty_under_guardian_cap": _round_decimal(max_qty_under_guardian_cap),
        "max_qty_under_effective_cap": _round_decimal(max_qty_under_effective_cap),
        "single_position_budget_usdt": _round_decimal(single_position_budget),
        "effective_single_order_cap_usdt": _round_decimal(effective_single_order_cap),
        "proposed_rounded_qty": _round_decimal(proposed_qty),
        "proposed_rounded_notional_usdt": _round_decimal(proposed_notional),
        "original_rounded_qty": _round_decimal(original_qty),
        "original_rounded_notional_usdt": _round_decimal(original_notional),
        "qty_delta": _round_decimal(qty_delta),
        "notional_delta_usdt": _round_decimal(notional_delta),
        "notional_reduction_pct": _round_decimal(reduction_pct),
        "guardian_adjusted_cap_utilization_pct": _round_decimal(cap_utilization_pct),
        "effective_cap_utilization_pct": _round_decimal(effective_cap_utilization_pct),
        "notional_lte_guardian_adjusted_cap": proposed_notional <= adjusted_cap,
        "notional_lte_gui_resolved_cap": proposed_notional <= gui_cap,
        "notional_lte_single_position_budget": proposed_notional
        <= single_position_budget,
        "notional_lte_effective_single_order_cap": proposed_notional
        <= effective_single_order_cap,
        "notional_gte_min_notional": proposed_notional >= min_notional,
        "requires_fresh_bbo_before_admission": True,
        "runtime_admission_ready": False,
        "order_admission_ready": False,
    }, sorted(set(reasons))


def build_current_candidate_guardian_adjusted_sizing_proposal(
    *,
    admission_review: dict[str, Any] | None,
    gate_evidence: dict[str, Any] | None,
    construction_preview: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_seconds: int = DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    source_head: str | None = None,
    runtime_head: str | None = None,
) -> dict[str, Any]:
    if max_artifact_age_seconds < 60 or max_artifact_age_seconds > 7 * 24 * 3600:
        raise ValueError("max_artifact_age_seconds must be in [60, 604800]")
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    admission = _dict(admission_review)
    gate = _dict(gate_evidence)
    construction = _dict(construction_preview)
    artifacts = {
        "admission_review": _artifact_summary(
            name="admission_review",
            path=paths.get("admission_review"),
            payload=admission,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=True,
        ),
        "gate_evidence": _artifact_summary(
            name="gate_evidence",
            path=paths.get("gate_evidence"),
            payload=gate,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=True,
        ),
        "construction_preview": _artifact_summary(
            name="construction_preview",
            path=paths.get("construction_preview"),
            payload=construction,
            now_utc=now,
            max_age_seconds=max_artifact_age_seconds,
            required=True,
        ),
    }
    source_reasons: list[str] = []
    for name, artifact in artifacts.items():
        if artifact["status"] != "FRESH":
            source_reasons.append(f"{name}_artifact_not_fresh")
    source_reasons.extend(_admission_reasons(admission))
    source_reasons.extend(_gate_reasons(gate))
    source_reasons.extend(_construction_reasons(construction))
    source_reasons.extend(
        _risk_lineage_reasons(
            admission=admission,
            gate_evidence=gate,
            construction_preview=construction,
        )
    )

    inputs = _extract_inputs(admission, gate, construction)
    if not _candidate_aligned(
        inputs["candidate"], inputs["gate_candidate"], inputs["construction_candidate"]
    ):
        source_reasons.append("candidate_alignment_failed")

    authority_reasons: list[str] = []
    for name, payload in (
        ("admission_review", admission),
        ("gate_evidence", gate),
        ("construction_preview", construction),
    ):
        if payload:
            authority_reasons.extend(
                f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
            )

    sizing, sizing_reasons = _build_sizing(inputs)
    source_reasons.extend(sizing_reasons)
    if authority_reasons:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation"
    elif source_reasons:
        status = NOT_READY_STATUS
        reason = "input_or_sizing_not_ready"
    else:
        status = READY_STATUS
        reason = "guardian_adjusted_sizing_proposal_ready_no_order"

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": inputs["candidate"],
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": artifacts,
        "source_blockers": sorted(set(source_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "blocking_gates": sorted(set(source_reasons + authority_reasons)),
        "blocking_gate_count": len(set(source_reasons + authority_reasons)),
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "risk_source_of_truth": inputs["risk_source_of_truth"],
            "cap_source": inputs["cap_source"],
            "account_equity_usdt": _round_decimal(inputs["account_equity_usdt"]),
            "gui_resolved_cap_usdt": _round_decimal(inputs["gui_resolved_cap_usdt"]),
            "per_trade_risk_pct_fraction": _round_decimal(
                inputs["per_trade_risk_pct_fraction"]
            ),
            "per_trade_risk_pct_display": _round_decimal(
                inputs["per_trade_risk_pct_display"],
                4,
            ),
            "position_size_max_pct": _round_decimal(inputs["position_size_max_pct"], 4),
            "single_position_budget_usdt": _round_decimal(
                inputs["single_position_budget_usdt"]
            ),
            "effective_single_order_cap_basis": (
                "min(gui_per_trade_cap_usdt, gui_max_single_position_budget_usdt, "
                "guardian_adjusted_cap_usdt)"
            ),
            "guardian_risk_level": inputs["risk_level"],
            "guardian_position_size_multiplier": _round_decimal(
                inputs["position_size_multiplier"]
            ),
            "guardian_adjusted_cap_usdt": _round_decimal(
                inputs["guardian_adjusted_cap_usdt"]
            ),
            "original_rounded_notional_usdt": _round_decimal(
                inputs["original_rounded_notional_usdt"]
            ),
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "sizing_proposal": sizing,
        "required_next_gates_before_order_capable_action": [
            "fresh_actual_admission_bbo_and_instrument_refresh",
            "current_candidate_decision_lease_valid",
            "guardian_risk_gate_valid_for_proposed_sizing",
            "rust_authority_path_valid",
            "auditability_and_reconstructability_review",
        ],
        "answers": {
            "review_contract_ready": status == READY_STATUS,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "bounded_demo_probe_authorized": False,
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
    sizing = _dict(packet.get("sizing_proposal"))
    lines = [
        "# Current Candidate Guardian-Adjusted Sizing Proposal",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- GUI cap USDT: `{risk.get('gui_resolved_cap_usdt')}`",
        f"- GUI max-single-position budget USDT: `{risk.get('single_position_budget_usdt')}`",
        f"- Guardian risk level: `{risk.get('guardian_risk_level')}`",
        f"- Guardian adjusted cap USDT: `{risk.get('guardian_adjusted_cap_usdt')}`",
        f"- Effective single-order cap USDT: `{sizing.get('effective_single_order_cap_usdt')}`",
        f"- Original notional USDT: `{risk.get('original_rounded_notional_usdt')}`",
        f"- Proposed qty: `{sizing.get('proposed_rounded_qty')}`",
        f"- Proposed notional USDT: `{sizing.get('proposed_rounded_notional_usdt')}`",
        "",
        "## Blockers",
    ]
    blockers = _list(packet.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-review-json", type=Path, required=True)
    parser.add_argument("--gate-evidence-json", type=Path, required=True)
    parser.add_argument("--construction-preview-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--max-artifact-age-seconds",
        type=int,
        default=DEFAULT_MAX_ARTIFACT_AGE_SECONDS,
    )
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_current_candidate_guardian_adjusted_sizing_proposal(
        admission_review=_read_json(args.admission_review_json),
        gate_evidence=_read_json(args.gate_evidence_json),
        construction_preview=_read_json(args.construction_preview_json),
        paths={
            "admission_review": args.admission_review_json,
            "gate_evidence": args.gate_evidence_json,
            "construction_preview": args.construction_preview_json,
        },
        max_artifact_age_seconds=args.max_artifact_age_seconds,
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

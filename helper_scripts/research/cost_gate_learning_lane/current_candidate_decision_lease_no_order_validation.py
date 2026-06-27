#!/usr/bin/env python3
"""Validate current-candidate Decision Lease IPC without admitting an order.

This helper is intentionally narrower than the admission gate helper. It may
perform one bounded governance lease mutation (Production/TRADE_ENTRY acquire
followed by immediate Failed release) only with explicit CLI + env opt-in. The
output proves whether the lease IPC/Rust SM path works for the current
candidate context; it never grants order authority and must not clear the
runtime admission Decision Lease gate, because the lease is released before the
artifact is written.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping


SCHEMA_VERSION = "current_candidate_decision_lease_no_order_validation_v1"
GATE_PACKET_SCHEMA_VERSION = "current_candidate_decision_lease_guardian_gate_evidence_v1"
SIZING_PROPOSAL_SCHEMA_VERSION = "current_candidate_guardian_adjusted_sizing_proposal_v1"

DRY_RUN_READY_STATUS = (
    "CURRENT_CANDIDATE_DECISION_LEASE_NO_ORDER_VALIDATION_DRY_RUN_READY"
)
DONE_STATUS = "CURRENT_CANDIDATE_DECISION_LEASE_NO_ORDER_VALIDATION_DONE_NO_ORDER"
SOURCE_NOT_READY_STATUS = (
    "CURRENT_CANDIDATE_DECISION_LEASE_NO_ORDER_VALIDATION_SOURCE_NOT_READY"
)
BLOCKED_BY_RUNTIME_STATUS = (
    "CURRENT_CANDIDATE_DECISION_LEASE_NO_ORDER_VALIDATION_BLOCKED_BY_RUNTIME"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

GATE_BLOCKED_STATUS = "CURRENT_CANDIDATE_DECISION_LEASE_GUARDIAN_GATE_BLOCKED_BY_LOSS_CONTROL"
SIZING_READY_STATUS = "CURRENT_CANDIDATE_GUARDIAN_ADJUSTED_SIZING_PROPOSAL_READY_NO_ORDER"

LEASE_SCOPE = "TRADE_ENTRY"
LEASE_PROFILE = "Production"
LEASE_TTL_SECONDS = 5.0
LEASE_SOURCE_STAGE = "current_candidate_demo_no_order_lease_validation"
RUN_ENV = "OPENCLAW_CURRENT_CANDIDATE_DECISION_LEASE_VALIDATE"
DEFAULT_MAX_GATE_PACKET_AGE_SECONDS = 6 * 60 * 60
DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS = 24 * 60 * 60

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "allowed_to_submit_order",
    "bounded_demo_probe_authorized",
    "bybit_private_call_performed",
    "cost_gate_lowering_performed",
    "decision_lease_emitted",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "mainnet_authority_granted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "placement_call_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "runtime_admission_ready",
    "runtime_mutation_performed",
}

BOUNDARY = (
    "current-candidate no-order Decision Lease IPC validation; optional bounded "
    "governance lease acquire/release only, no order/probe/live authority, no "
    "Bybit/private/order call, no runtime config/env/service mutation, no PG "
    "write, no Cost Gate lowering, no admission gate clearing, and no profit proof"
)

IPCDispatcher = Callable[..., Awaitable[Mapping[str, Any]]]


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


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


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


def _candidate_aligned(left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_key = _candidate_key(left)
    right_key = _candidate_key(right)
    return bool(left_key[0]) and left_key == right_key


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


def _artifact_summary(
    *,
    name: str,
    path: Path | None,
    payload: dict[str, Any],
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    generated_at = payload.get("generated_at_utc") if payload else None
    parsed = _parse_dt(generated_at)
    age = (now_utc - parsed).total_seconds() if parsed is not None else None
    if not payload:
        freshness = "MISSING"
    elif parsed is None:
        freshness = "PRESENT_UNKNOWN_AGE"
    elif age is not None and age < -60:
        freshness = "FROM_FUTURE"
    elif age is not None and age > max_age_seconds:
        freshness = "STALE"
    else:
        freshness = "FRESH"
    return {
        "name": name,
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "present": bool(payload),
        "schema_version": payload.get("schema_version") if payload else None,
        "artifact_status": payload.get("status") if payload else None,
        "generated_at_utc": generated_at,
        "age_seconds": round(age, 3) if age is not None else None,
        "max_age_seconds": max_age_seconds,
        "freshness": freshness,
    }


def _sizing_context(proposal: dict[str, Any]) -> dict[str, Any]:
    risk = _dict(proposal.get("risk_context"))
    sizing = _dict(proposal.get("sizing_proposal"))
    return {
        "candidate": _candidate_identity(_dict(proposal.get("candidate"))),
        "account_equity_usdt": _float(risk.get("account_equity_usdt")),
        "gui_resolved_cap_usdt": _float(risk.get("gui_resolved_cap_usdt")),
        "single_position_budget_usdt": _float(risk.get("single_position_budget_usdt")),
        "guardian_adjusted_cap_usdt": _float(risk.get("guardian_adjusted_cap_usdt")),
        "effective_single_order_cap_usdt": _float(
            sizing.get("effective_single_order_cap_usdt")
        ),
        "per_trade_risk_pct_fraction": _float(risk.get("per_trade_risk_pct_fraction")),
        "per_trade_risk_pct_display": _float(risk.get("per_trade_risk_pct_display")),
        "position_size_max_pct": _float(risk.get("position_size_max_pct")),
        "proposed_rounded_qty": _float(sizing.get("proposed_rounded_qty")),
        "proposed_rounded_notional_usdt": _float(
            sizing.get("proposed_rounded_notional_usdt")
        ),
        "notional_lte_gui_resolved_cap": sizing.get("notional_lte_gui_resolved_cap"),
        "notional_lte_single_position_budget": sizing.get(
            "notional_lte_single_position_budget"
        ),
        "notional_lte_effective_single_order_cap": sizing.get(
            "notional_lte_effective_single_order_cap"
        ),
        "notional_lte_guardian_adjusted_cap": sizing.get(
            "notional_lte_guardian_adjusted_cap"
        ),
        "notional_gte_min_notional": sizing.get("notional_gte_min_notional"),
    }


def _source_reasons(
    *,
    gate_packet: dict[str, Any],
    sizing_proposal: dict[str, Any],
    now_utc: dt.datetime,
    max_gate_packet_age_seconds: int,
    max_sizing_proposal_age_seconds: int,
) -> tuple[list[str], dict[str, Any], dict[str, Any]]:
    reasons: list[str] = []
    gate_generated = _parse_dt(gate_packet.get("generated_at_utc"))
    sizing_generated = _parse_dt(sizing_proposal.get("generated_at_utc"))
    if gate_generated is None:
        reasons.append("gate_packet_generated_at_missing_or_invalid")
    else:
        gate_age = (now_utc - gate_generated).total_seconds()
        if gate_age < -60:
            reasons.append("gate_packet_from_future")
        elif gate_age > max_gate_packet_age_seconds:
            reasons.append("gate_packet_stale")
    if sizing_generated is None:
        reasons.append("sizing_proposal_generated_at_missing_or_invalid")
    else:
        sizing_age = (now_utc - sizing_generated).total_seconds()
        if sizing_age < -60:
            reasons.append("sizing_proposal_from_future")
        elif sizing_age > max_sizing_proposal_age_seconds:
            reasons.append("sizing_proposal_stale")
    if gate_packet.get("schema_version") != GATE_PACKET_SCHEMA_VERSION:
        reasons.append("gate_packet_schema_version_invalid")
    if gate_packet.get("status") != GATE_BLOCKED_STATUS:
        reasons.append("gate_packet_status_not_blocked_by_loss_control")
    if "decision_lease_valid" not in _list(gate_packet.get("runtime_admission_blockers")):
        reasons.append("gate_packet_decision_lease_blocker_missing")

    risk = _dict(gate_packet.get("risk_context"))
    gate_candidate = _candidate_identity(_dict(gate_packet.get("candidate")))
    if risk.get("gui_risk_config_is_source_of_truth") is not True:
        reasons.append("gate_packet_gui_risk_not_source_of_truth")
    if risk.get("sizing_source") != "guardian_adjusted_sizing_proposal":
        reasons.append("gate_packet_not_using_guardian_adjusted_sizing_proposal")
    if _float(risk.get("resolved_cap_usdt")) is None:
        reasons.append("gate_packet_gui_cap_missing")

    if sizing_proposal.get("schema_version") != SIZING_PROPOSAL_SCHEMA_VERSION:
        reasons.append("sizing_proposal_schema_version_invalid")
    if sizing_proposal.get("status") != SIZING_READY_STATUS:
        reasons.append("sizing_proposal_status_not_ready")
    if _list(sizing_proposal.get("source_blockers")):
        reasons.append("sizing_proposal_source_blockers_present")
    if _list(sizing_proposal.get("authority_contamination_reasons")):
        reasons.append("sizing_proposal_authority_contamination_present")

    sizing = _sizing_context(sizing_proposal)
    if not _candidate_aligned(gate_candidate, _dict(sizing.get("candidate"))):
        reasons.append("sizing_proposal_candidate_mismatch_gate_packet")
    if not _same_float(risk.get("resolved_cap_usdt"), sizing.get("gui_resolved_cap_usdt")):
        reasons.append("sizing_proposal_gui_cap_mismatch_gate_packet")
    if not _same_float(
        risk.get("single_position_budget_usdt"),
        sizing.get("single_position_budget_usdt"),
    ):
        reasons.append("sizing_proposal_single_position_budget_mismatch_gate_packet")
    if not _same_float(
        risk.get("effective_single_order_cap_usdt"),
        sizing.get("effective_single_order_cap_usdt"),
    ):
        reasons.append("sizing_proposal_effective_cap_mismatch_gate_packet")
    if not _same_float(
        risk.get("rounded_notional_usdt"),
        sizing.get("proposed_rounded_notional_usdt"),
    ):
        reasons.append("sizing_proposal_notional_mismatch_gate_packet")

    fraction = sizing.get("per_trade_risk_pct_fraction")
    display = sizing.get("per_trade_risk_pct_display")
    position_pct = sizing.get("position_size_max_pct")
    equity = sizing.get("account_equity_usdt")
    single_budget = sizing.get("single_position_budget_usdt")
    proposed_notional = sizing.get("proposed_rounded_notional_usdt")
    effective_cap = sizing.get("effective_single_order_cap_usdt")
    guardian_cap = sizing.get("guardian_adjusted_cap_usdt")
    gui_cap = sizing.get("gui_resolved_cap_usdt")

    if fraction is None or display is None or not _same_float(display / 100.0, fraction):
        reasons.append("gui_percent_fraction_semantics_invalid")
    if (
        equity is None
        or position_pct is None
        or single_budget is None
        or not _same_float(single_budget, equity * position_pct / 100.0, tolerance=1e-6)
    ):
        reasons.append("single_position_budget_not_gui_percent_derived")
    if (
        proposed_notional is None
        or gui_cap is None
        or single_budget is None
        or effective_cap is None
        or guardian_cap is None
    ):
        reasons.append("sizing_required_notional_or_cap_missing")
    else:
        if proposed_notional > gui_cap + 1e-8:
            reasons.append("proposed_notional_exceeds_gui_cap")
        if proposed_notional > single_budget + 1e-8:
            reasons.append("proposed_notional_exceeds_single_position_budget")
        if proposed_notional > effective_cap + 1e-8:
            reasons.append("proposed_notional_exceeds_effective_cap")
        expected_effective = min(gui_cap, single_budget, guardian_cap)
        if not _same_float(effective_cap, expected_effective, tolerance=1e-6):
            reasons.append("effective_cap_not_min_of_gui_single_position_guardian")

    for key in (
        "notional_lte_gui_resolved_cap",
        "notional_lte_single_position_budget",
        "notional_lte_effective_single_order_cap",
        "notional_lte_guardian_adjusted_cap",
        "notional_gte_min_notional",
    ):
        if sizing.get(key) is not True:
            reasons.append(f"sizing_proposal_{key}_not_true")

    return sorted(set(reasons)), gate_candidate, sizing


def _make_intent_id(candidate: dict[str, Any], now: dt.datetime) -> str:
    raw = (
        f"current_candidate_no_order_lease_validation:"
        f"{candidate.get('strategy_name')}:{candidate.get('symbol')}:"
        f"{candidate.get('side')}:{now.strftime('%Y%m%dT%H%M%SZ')}"
    )
    return re.sub(r"[^A-Za-z0-9:_.-]+", "_", raw)[:180]


def _run_lease_validation(
    *,
    intent_id: str,
    dispatcher: IPCDispatcher | None = None,
    timeout_seconds: float = 5.0,
) -> tuple[dict[str, Any], list[str]]:
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
        governance_lease_bridge as bridge,
    )

    reasons: list[str] = []
    release_ok = False
    before_release: Mapping[str, Any] | None = None
    after_release: Mapping[str, Any] | None = None
    lease_id = bridge.acquire_lease_via_ipc(
        intent_id=intent_id,
        scope=LEASE_SCOPE,
        ttl_seconds=LEASE_TTL_SECONDS,
        profile=LEASE_PROFILE,
        source_stage=LEASE_SOURCE_STAGE,
        timeout_seconds=timeout_seconds,
        dispatcher=dispatcher,
    )
    if lease_id is None:
        return {
            "intent_id": intent_id,
            "lease_id": None,
            "lease_scope": LEASE_SCOPE,
            "lease_profile": LEASE_PROFILE,
            "lease_ttl_seconds": LEASE_TTL_SECONDS,
            "source_stage": LEASE_SOURCE_STAGE,
            "acquire_ok": False,
            "release_ok": False,
            "get_before_release": None,
            "get_after_release": None,
            "released_outcome": "Failed",
        }, ["lease_acquire_failed"]
    if lease_id == "bypass":
        return {
            "intent_id": intent_id,
            "lease_id": lease_id,
            "lease_scope": LEASE_SCOPE,
            "lease_profile": LEASE_PROFILE,
            "lease_ttl_seconds": LEASE_TTL_SECONDS,
            "source_stage": LEASE_SOURCE_STAGE,
            "acquire_ok": False,
            "release_ok": False,
            "get_before_release": None,
            "get_after_release": None,
            "released_outcome": "Failed",
        }, ["production_lease_unexpected_bypass"]

    try:
        before_release = bridge.get_lease_via_ipc(
            lease_id=lease_id,
            timeout_seconds=timeout_seconds,
            dispatcher=dispatcher,
        )
        if before_release is None:
            reasons.append("lease_get_before_release_failed")
    finally:
        release_ok = bridge.release_lease_via_ipc(
            lease_id=lease_id,
            consumed=False,
            timeout_seconds=timeout_seconds,
            dispatcher=dispatcher,
        )
    if not release_ok:
        reasons.append("lease_release_failed")
    after_release = bridge.get_lease_via_ipc(
        lease_id=lease_id,
        timeout_seconds=timeout_seconds,
        dispatcher=dispatcher,
    )
    if after_release is not None:
        reasons.append("lease_still_fetchable_after_release")

    return {
        "intent_id": intent_id,
        "lease_id": lease_id,
        "lease_scope": LEASE_SCOPE,
        "lease_profile": LEASE_PROFILE,
        "lease_ttl_seconds": LEASE_TTL_SECONDS,
        "source_stage": LEASE_SOURCE_STAGE,
        "acquire_ok": True,
        "release_ok": release_ok,
        "get_before_release": dict(before_release) if isinstance(before_release, Mapping) else None,
        "get_after_release": dict(after_release) if isinstance(after_release, Mapping) else None,
        "released_outcome": "Failed",
    }, sorted(set(reasons))


def build_current_candidate_decision_lease_no_order_validation(
    *,
    gate_packet: dict[str, Any] | None,
    sizing_proposal: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    run: bool = False,
    require_env: bool = True,
    now_utc: dt.datetime | None = None,
    source_head: str | None = None,
    runtime_head: str | None = None,
    dispatcher: IPCDispatcher | None = None,
    timeout_seconds: float = 5.0,
    max_gate_packet_age_seconds: int = DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    max_sizing_proposal_age_seconds: int = DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    if max_gate_packet_age_seconds < 60 or max_gate_packet_age_seconds > 24 * 3600:
        raise ValueError("max_gate_packet_age_seconds must be in [60, 86400]")
    if (
        max_sizing_proposal_age_seconds < 60
        or max_sizing_proposal_age_seconds > 7 * 24 * 3600
    ):
        raise ValueError("max_sizing_proposal_age_seconds must be in [60, 604800]")
    paths = paths or {}
    gate = _dict(gate_packet)
    proposal = _dict(sizing_proposal)
    source_reasons, candidate, sizing = _source_reasons(
        gate_packet=gate,
        sizing_proposal=proposal,
        now_utc=now,
        max_gate_packet_age_seconds=max_gate_packet_age_seconds,
        max_sizing_proposal_age_seconds=max_sizing_proposal_age_seconds,
    )
    authority_reasons: list[str] = []
    for name, payload in (("gate_packet", gate), ("sizing_proposal", proposal)):
        authority_reasons.extend(
            f"{name}.{reason}" for reason in _recursive_authority_violations(payload)
        )
    if os.environ.get("OPENCLAW_ALLOW_MAINNET", "") == "1":
        authority_reasons.append("OPENCLAW_ALLOW_MAINNET_1_refused")

    env_enabled = os.environ.get(RUN_ENV, "") == "1"
    if run and require_env and not env_enabled:
        source_reasons.append(f"{RUN_ENV}_not_1")

    intent_id = _make_intent_id(candidate, now)
    lease_result: dict[str, Any] = {
        "intent_id": intent_id,
        "lease_id": None,
        "lease_scope": LEASE_SCOPE,
        "lease_profile": LEASE_PROFILE,
        "lease_ttl_seconds": LEASE_TTL_SECONDS,
        "source_stage": LEASE_SOURCE_STAGE,
        "acquire_ok": False,
        "release_ok": False,
        "get_before_release": None,
        "get_after_release": None,
        "released_outcome": "Failed",
    }
    runtime_reasons: list[str] = []
    if run and not source_reasons and not authority_reasons:
        lease_result, runtime_reasons = _run_lease_validation(
            intent_id=intent_id,
            dispatcher=dispatcher,
            timeout_seconds=timeout_seconds,
        )

    if authority_reasons:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation"
    elif source_reasons:
        status = SOURCE_NOT_READY_STATUS
        reason = "source_gate_or_explicit_run_guard_not_ready"
    elif not run:
        status = DRY_RUN_READY_STATUS
        reason = "dry_run_ready_for_explicit_no_order_lease_validation"
    elif runtime_reasons:
        status = BLOCKED_BY_RUNTIME_STATUS
        reason = "lease_ipc_mutating_validation_failed"
    else:
        status = DONE_STATUS
        reason = "lease_ipc_acquire_release_validated_no_order"

    mutation_performed = run and not source_reasons and not authority_reasons
    lease_released = lease_result.get("release_ok") is True
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": {
            "gate_packet": _artifact_summary(
                name="gate_packet",
                path=paths.get("gate_packet"),
                payload=gate,
                now_utc=now,
                max_age_seconds=max_gate_packet_age_seconds,
            ),
            "sizing_proposal": _artifact_summary(
                name="sizing_proposal",
                path=paths.get("sizing_proposal"),
                payload=proposal,
                now_utc=now,
                max_age_seconds=max_sizing_proposal_age_seconds,
            ),
        },
        "source_blockers": sorted(set(source_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "runtime_blockers": sorted(set(runtime_reasons)),
        "blocking_gates": sorted(set(source_reasons + authority_reasons + runtime_reasons)),
        "risk_context": {
            "gui_risk_config_is_source_of_truth": True,
            "account_equity_usdt": sizing.get("account_equity_usdt"),
            "gui_resolved_cap_usdt": sizing.get("gui_resolved_cap_usdt"),
            "single_position_budget_usdt": sizing.get("single_position_budget_usdt"),
            "guardian_adjusted_cap_usdt": sizing.get("guardian_adjusted_cap_usdt"),
            "effective_single_order_cap_usdt": sizing.get(
                "effective_single_order_cap_usdt"
            ),
            "proposed_rounded_qty": sizing.get("proposed_rounded_qty"),
            "proposed_rounded_notional_usdt": sizing.get(
                "proposed_rounded_notional_usdt"
            ),
            "per_trade_risk_pct_fraction": sizing.get("per_trade_risk_pct_fraction"),
            "per_trade_risk_pct_display": sizing.get("per_trade_risk_pct_display"),
            "position_size_max_pct": sizing.get("position_size_max_pct"),
            "gui_percent_semantics": (
                "GUI 10.0% means per_trade_risk_pct=0.1; max single position "
                "is GUI percent-derived exposure budget, not a fixed 10 USDT cap"
            ),
        },
        "decision_lease_validation": lease_result,
        "answers": {
            "review_contract_ready": not source_reasons and not authority_reasons,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "governance_lease_mutation_performed": mutation_performed,
            "decision_lease_acquire_performed": mutation_performed,
            "decision_lease_release_performed": mutation_performed and lease_released,
            "decision_lease_emitted": False,
            "lease_released_before_artifact": lease_released if mutation_performed else False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "runtime_config_mutation_performed": False,
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
    validation = _dict(packet.get("decision_lease_validation"))
    lines = [
        "# Current Candidate Decision Lease No-Order Validation",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- GUI resolved cap USDT: `{risk.get('gui_resolved_cap_usdt')}`",
        f"- GUI max-single-position budget USDT: `{risk.get('single_position_budget_usdt')}`",
        f"- Effective single-order cap USDT: `{risk.get('effective_single_order_cap_usdt')}`",
        f"- Proposed notional USDT: `{risk.get('proposed_rounded_notional_usdt')}`",
        f"- Lease scope/profile: `{validation.get('lease_scope')}` / `{validation.get('lease_profile')}`",
        f"- Lease id: `{validation.get('lease_id')}`",
        f"- Acquire/release ok: `{validation.get('acquire_ok')}` / `{validation.get('release_ok')}`",
        "",
        "## Blockers",
    ]
    blockers = _list(packet.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-packet-json", type=Path, required=True)
    parser.add_argument("--sizing-proposal-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--max-gate-packet-age-seconds",
        type=int,
        default=DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-sizing-proposal-age-seconds",
        type=int,
        default=DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS,
    )
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.run and not args.yes:
        print(
            "[REFUSED] --run requires --yes and "
            f"{RUN_ENV}=1 for bounded no-order lease mutation",
            file=sys.stderr,
        )
        return 2
    packet = build_current_candidate_decision_lease_no_order_validation(
        gate_packet=_read_json(args.gate_packet_json),
        sizing_proposal=_read_json(args.sizing_proposal_json),
        paths={
            "gate_packet": args.gate_packet_json,
            "sizing_proposal": args.sizing_proposal_json,
        },
        run=args.run,
        require_env=True,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
        timeout_seconds=args.timeout_seconds,
        max_gate_packet_age_seconds=args.max_gate_packet_age_seconds,
        max_sizing_proposal_age_seconds=args.max_sizing_proposal_age_seconds,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] in {DRY_RUN_READY_STATUS, DONE_STATUS} else 1


if __name__ == "__main__":
    raise SystemExit(main())

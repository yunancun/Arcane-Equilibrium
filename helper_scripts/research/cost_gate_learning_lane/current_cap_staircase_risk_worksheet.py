#!/usr/bin/env python3
"""Build a source-only current-cap staircase and risk worksheet.

The worksheet uses supplied no-order artifacts to compute executable AVAX
notional tiers under the current per-order cap. It does not query PG, call
Bybit, submit orders, change caps/risk, lower Cost Gate, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, InvalidOperation
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_current_cap_staircase_risk_worksheet_v1"
READY_STATUS = "CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY"
NOT_CONSTRUCTIBLE_STATUS = "CURRENT_CAP_STAIRCASE_NOT_CONSTRUCTIBLE_NO_AUTHORITY"
CONTROL_CONTRACT_NOT_READY_STATUS = "CONTROL_IDENTITY_CONTRACT_INPUT_NOT_READY"
CONSTRUCTION_INPUT_INCOMPLETE_STATUS = "CONSTRUCTION_INPUT_INCOMPLETE"
CANDIDATE_MISMATCH_STATUS = "CANDIDATE_MISMATCH"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

CONTROL_CONTRACT_SCHEMA_VERSION = "cost_gate_source_only_control_identity_contract_v1"
CONTROL_CONTRACT_READY_STATUS = "SOURCE_ONLY_CONTROL_IDENTITY_CONTRACT_READY_NO_AUTHORITY"

BOUNDARY = (
    "artifact-only current-cap staircase/risk worksheet; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, cap mutation, probe authority, order authority, live authority, "
    "or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "canonical_plan_mutation_performed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


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
        }
    return False


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


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        adjustment = data.get("main_cost_gate_adjustment")
        if adjustment not in (None, "", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
        for key in AUTHORITY_TRUE_KEYS:
            if _truthy(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _control_contract_ready(contract: dict[str, Any]) -> bool:
    return (
        contract.get("schema_version") == CONTROL_CONTRACT_SCHEMA_VERSION
        and contract.get("status") == CONTROL_CONTRACT_READY_STATUS
    )


def _candidate_from_control_contract(contract: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(contract.get("candidate"))
    if candidate:
        return candidate
    return _dict(_dict(contract.get("contract")).get("candidate_identity"))


def _candidate_from_construction(preview: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(preview.get("candidate")) or _dict(preview.get("snapshot_candidate"))
    return {
        "side_cell_key": _str(candidate.get("side_cell_key")),
        "strategy_name": _str(candidate.get("strategy_name")),
        "symbol": _str(candidate.get("symbol")),
        "side": _str(candidate.get("side")),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _candidate_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    for key in ("side_cell_key", "strategy_name", "symbol", "side"):
        if _str(left.get(key)) != _str(right.get(key)):
            return False
    left_horizon = left.get("outcome_horizon_minutes")
    right_horizon = right.get("outcome_horizon_minutes")
    return left_horizon in (None, "") or right_horizon in (None, "") or left_horizon == right_horizon


def _construction_inputs(preview: dict[str, Any]) -> dict[str, Any]:
    construction = _dict(preview.get("construction"))
    market_inputs = _dict(preview.get("market_inputs"))
    limit_price = (
        _dec(construction.get("limit_price"))
        or _dec(construction.get("post_round_limit_price"))
        or _dec(market_inputs.get("best_ask"))
        or _dec(market_inputs.get("last_price"))
        or _dec(construction.get("reference_price"))
    )
    reference_price = _dec(construction.get("reference_price")) or _dec(
        market_inputs.get("best_bid")
    )
    qty_step = _dec(construction.get("qty_step")) or _dec(market_inputs.get("qty_step"))
    min_notional = _dec(construction.get("min_notional")) or _dec(
        market_inputs.get("min_notional")
    )
    cap_usdt = _dec(construction.get("cap_usdt")) or _dec(market_inputs.get("cap_usdt"))
    tick_size = _dec(construction.get("tick_size")) or _dec(market_inputs.get("tick_size"))
    return {
        "limit_price": limit_price,
        "reference_price": reference_price,
        "qty_step": qty_step,
        "min_notional": min_notional,
        "cap_usdt": cap_usdt,
        "tick_size": tick_size,
        "source_constructible": construction.get("constructible") is True,
        "source_status": preview.get("status"),
        "blocking_gates": _list(preview.get("blocking_gates")),
        "bbo_fresh": _dict(preview.get("readiness")).get("bbo_fresh") is True,
        "instrument_status": _str(market_inputs.get("instrument_status"))
        or _str(market_inputs.get("derived_instrument_status")),
        "max_fresh_bbo_age_ms": _dec(market_inputs.get("max_fresh_bbo_age_ms")),
        "effective_bbo_age_ms": _dec(market_inputs.get("effective_bbo_age_ms")),
    }


def _ceil_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_CEILING) * step


def _floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    return (value / step).to_integral_value(rounding=ROUND_FLOOR) * step


def _build_tiers(
    *,
    limit_price: Decimal,
    qty_step: Decimal,
    min_notional: Decimal,
    cap_usdt: Decimal,
    max_tiers: int = 200,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    min_qty_by_notional = _ceil_to_step(min_notional / limit_price, qty_step)
    min_positive_qty = qty_step
    cap_qty = _floor_to_step(cap_usdt / limit_price, qty_step)
    tiers: list[dict[str, Any]] = []
    qty = min_qty_by_notional
    while qty <= cap_qty and len(tiers) < max_tiers:
        notional = qty * limit_price
        tiers.append(
            {
                "tier_index": len(tiers) + 1,
                "qty": _round_decimal(qty, 8),
                "notional_usdt": _round_decimal(notional, 8),
                "cap_utilization_pct": _round_decimal(
                    (notional / cap_usdt) * Decimal("100"),
                    4,
                ),
            }
        )
        qty += qty_step
    summary = {
        "min_positive_qty": _round_decimal(min_positive_qty, 8),
        "min_positive_qty_notional_usdt": _round_decimal(min_positive_qty * limit_price, 8),
        "min_executable_qty": _round_decimal(min_qty_by_notional, 8),
        "min_executable_notional_usdt": _round_decimal(min_qty_by_notional * limit_price, 8),
        "max_qty_under_cap": _round_decimal(cap_qty, 8),
        "max_notional_under_cap_usdt": _round_decimal(cap_qty * limit_price, 8),
        "tier_count": len(tiers),
        "fits_current_cap": bool(tiers),
        "tier_truncated": qty <= cap_qty,
    }
    return tiers, summary


def _risk_worksheet(
    *,
    cap_usdt: Decimal,
    max_notional_under_cap: Decimal | None,
    max_probe_orders_before_review: int,
    max_total_demo_notional_before_review: Decimal,
) -> dict[str, Any]:
    reserved = cap_usdt * Decimal(max_probe_orders_before_review)
    executable_reserved = (
        max_notional_under_cap * Decimal(max_probe_orders_before_review)
        if max_notional_under_cap is not None
        else None
    )
    return {
        "per_order_cap_usdt": _round_decimal(cap_usdt, 4),
        "max_probe_orders_before_review": max_probe_orders_before_review,
        "max_total_demo_notional_before_review": _round_decimal(
            max_total_demo_notional_before_review,
            4,
        ),
        "worst_case_reserved_notional_usdt": _round_decimal(reserved, 4),
        "max_executable_tier_reserved_notional_usdt": _round_decimal(
            executable_reserved,
            4,
        ),
        "fits_existing_total_review_cap": reserved <= max_total_demo_notional_before_review,
        "cap_mutation_required": False,
        "risk_mutation_required": False,
        "survival_boundary_status": "CURRENT_CAP_BOUNDS_ONLY_NO_AUTHORITY",
        "authority_required_for_any_change": "operator/QC plus PM->E3->BB for cap/risk mutation or order path",
    }


def build_current_cap_staircase_risk_worksheet(
    *,
    control_identity_contract: dict[str, Any] | None,
    construction_preview: dict[str, Any] | None,
    max_probe_orders_before_review: int = 3,
    max_total_demo_notional_before_review: float | None = 30.0,
    now_utc: dt.datetime | None = None,
    control_identity_contract_path: Path | None = None,
    construction_preview_path: Path | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    contract = _dict(control_identity_contract)
    preview = _dict(construction_preview)
    authority_ok, authority_reasons = _authority_preserved(contract, preview)
    contract_ready = _control_contract_ready(contract)
    control_candidate = _candidate_from_control_contract(contract)
    construction_candidate = _candidate_from_construction(preview)
    candidate_match = _candidate_matches(control_candidate, construction_candidate)
    inputs = _construction_inputs(preview)
    required_inputs = (
        inputs.get("limit_price"),
        inputs.get("qty_step"),
        inputs.get("min_notional"),
        inputs.get("cap_usdt"),
    )
    inputs_complete = all(
        isinstance(value, Decimal) and value > 0 for value in required_inputs
    )
    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not contract_ready:
        status = CONTROL_CONTRACT_NOT_READY_STATUS
        reason = "control_identity_contract_input_not_ready"
    elif not candidate_match:
        status = CANDIDATE_MISMATCH_STATUS
        reason = "control_contract_candidate_does_not_match_construction_preview"
    elif not inputs_complete:
        status = CONSTRUCTION_INPUT_INCOMPLETE_STATUS
        reason = "construction_preview_missing_price_qty_step_min_notional_or_cap"
    else:
        tiers, tier_summary = _build_tiers(
            limit_price=inputs["limit_price"],
            qty_step=inputs["qty_step"],
            min_notional=inputs["min_notional"],
            cap_usdt=inputs["cap_usdt"],
        )
        status = READY_STATUS if tiers else NOT_CONSTRUCTIBLE_STATUS
        reason = (
            "current_cap_staircase_and_risk_worksheet_ready"
            if tiers
            else "current_cap_does_not_fit_min_executable_tier"
        )

    tiers = []
    tier_summary: dict[str, Any] = {}
    risk: dict[str, Any] = {}
    if status in {READY_STATUS, NOT_CONSTRUCTIBLE_STATUS}:
        tiers, tier_summary = _build_tiers(
            limit_price=inputs["limit_price"],
            qty_step=inputs["qty_step"],
            min_notional=inputs["min_notional"],
            cap_usdt=inputs["cap_usdt"],
        )
        max_total = _dec(max_total_demo_notional_before_review)
        if max_total is None or max_total <= 0:
            max_total = inputs["cap_usdt"] * Decimal(max_probe_orders_before_review)
        max_notional = _dec(tier_summary.get("max_notional_under_cap_usdt"))
        risk = _risk_worksheet(
            cap_usdt=inputs["cap_usdt"],
            max_notional_under_cap=max_notional,
            max_probe_orders_before_review=max(1, int(max_probe_orders_before_review)),
            max_total_demo_notional_before_review=max_total,
        )

    bbo_refresh_required = (
        inputs.get("bbo_fresh") is not True
        or "bbo_freshness" in inputs.get("blocking_gates", [])
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_inputs": {
            "control_identity_contract_path": (
                str(control_identity_contract_path)
                if control_identity_contract_path
                else None
            ),
            "control_identity_contract_schema_version": contract.get("schema_version"),
            "control_identity_contract_status": contract.get("status"),
            "construction_preview_path": (
                str(construction_preview_path) if construction_preview_path else None
            ),
            "construction_preview_schema_version": preview.get("schema_version"),
            "construction_preview_status": preview.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "candidate_match": candidate_match,
        },
        "candidate": control_candidate if status not in {CANDIDATE_MISMATCH_STATUS, CONTROL_CONTRACT_NOT_READY_STATUS} else {},
        "construction_inputs": {
            "limit_price": _round_decimal(inputs.get("limit_price"), 8),
            "reference_price": _round_decimal(inputs.get("reference_price"), 8),
            "qty_step": _round_decimal(inputs.get("qty_step"), 8),
            "min_notional": _round_decimal(inputs.get("min_notional"), 8),
            "cap_usdt": _round_decimal(inputs.get("cap_usdt"), 8),
            "tick_size": _round_decimal(inputs.get("tick_size"), 8),
            "instrument_status": inputs.get("instrument_status"),
            "source_constructible": inputs.get("source_constructible"),
            "source_bbo_fresh": inputs.get("bbo_fresh"),
            "source_blocking_gates": inputs.get("blocking_gates"),
            "effective_bbo_age_ms": _round_decimal(inputs.get("effective_bbo_age_ms"), 4),
            "max_fresh_bbo_age_ms": _round_decimal(inputs.get("max_fresh_bbo_age_ms"), 4),
            "bbo_refresh_required_before_order_admission": bbo_refresh_required,
        },
        "cap_staircase": {
            "tiers": tiers,
            "summary": tier_summary,
            "discrete_tier_rule": "qty starts at min_notional rounded up to qty_step and increases by qty_step until existing cap is reached",
        },
        "risk_worksheet": risk,
        "summary": {
            "worksheet_ready": status in {READY_STATUS, NOT_CONSTRUCTIBLE_STATUS},
            "constructible_under_current_cap": status == READY_STATUS,
            "tier_count": tier_summary.get("tier_count", 0),
            "cap_mutation_required": False,
            "risk_mutation_required": False,
            "order_admission_ready": False,
            "bbo_refresh_required_before_order_admission": bbo_refresh_required,
            "p0_authorization_required_before_probe": True,
            "max_safe_next_action": (
                "implement_fee_slippage_maker_taker_schema_or_review_real_auth_delta"
                if status == READY_STATUS
                else "refresh_no_order_construction_preview_or_review_cap_risk_separately"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "current_cap_staircase_ready": status == READY_STATUS,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "cap_mutation_performed": False,
            "risk_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "runtime_mutation_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    risk = _dict(packet.get("risk_worksheet"))
    lines = [
        "# Current-Cap Staircase Risk Worksheet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Summary",
        "",
        f"- Constructible under current cap: `{summary.get('constructible_under_current_cap')}`",
        f"- Tier count: `{summary.get('tier_count')}`",
        f"- Order admission ready: `{summary.get('order_admission_ready')}`",
        f"- BBO refresh required before order admission: `{summary.get('bbo_refresh_required_before_order_admission')}`",
        "",
        "## Risk Worksheet",
        "",
    ]
    for key, value in risk.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Cap Tiers", "", "| tier | qty | notional USDT | cap % |", "|---:|---:|---:|---:|"])
    for tier in _list(_dict(packet.get("cap_staircase")).get("tiers")):
        lines.append(
            f"| {tier.get('tier_index')} | {tier.get('qty')} | "
            f"{tier.get('notional_usdt')} | {tier.get('cap_utilization_pct')} |"
        )
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control-identity-contract-json", type=Path, required=True)
    parser.add_argument("--construction-preview-json", type=Path, required=True)
    parser.add_argument("--max-probe-orders-before-review", type=int, default=3)
    parser.add_argument("--max-total-demo-notional-before-review", type=float, default=30.0)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_current_cap_staircase_risk_worksheet(
        control_identity_contract=_read_json(args.control_identity_contract_json),
        construction_preview=_read_json(args.construction_preview_json),
        max_probe_orders_before_review=args.max_probe_orders_before_review,
        max_total_demo_notional_before_review=args.max_total_demo_notional_before_review,
        control_identity_contract_path=args.control_identity_contract_json,
        construction_preview_path=args.construction_preview_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a source-only maker-first micro-tier placement policy.

The policy converts existing no-authority artifacts into a reviewable
post-only maker placement/skip contract for the selected AVAX candidate. It
does not read live quotes, call Bybit, query/write PG, submit orders, lower
Cost Gate, change risk/caps, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_maker_first_micro_tier_placement_policy_v1"
READY_STATUS = "MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY"
CURRENT_CAP_WORKSHEET_NOT_READY_STATUS = "CURRENT_CAP_WORKSHEET_INPUT_NOT_READY"
FEE_SCHEMA_NOT_READY_STATUS = "FEE_SCHEMA_INPUT_NOT_READY"
FRESH_BBO_READINESS_NOT_READY_STATUS = "FRESH_BBO_READINESS_INPUT_NOT_READY"
CANDIDATE_MISSING_OR_MISMATCH_STATUS = "CANDIDATE_MISSING_OR_MISMATCH"
CAP_TIER_LADDER_MISSING_STATUS = "CAP_TIER_LADDER_MISSING"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

WORKSHEET_SCHEMA_VERSION = "cost_gate_current_cap_staircase_risk_worksheet_v1"
WORKSHEET_READY_STATUS = "CURRENT_CAP_STAIRCASE_RISK_WORKSHEET_READY_NO_AUTHORITY"
FEE_SCHEMA_VERSION = "cost_gate_fee_slippage_maker_taker_schema_contract_v1"
FEE_SCHEMA_READY_STATUS = "FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY"
FRESH_BBO_SCHEMA_VERSION = "cost_gate_fresh_bbo_readonly_readiness_path_v1"
FRESH_BBO_READY_STATUS = "FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY"

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

BOUNDARY = (
    "artifact-only maker-first micro-tier placement policy; no live quote "
    "capture, PG query/write, Bybit call, private/auth/order endpoint, order, "
    "config, risk, cap, auth, runtime mutation, Cost Gate lowering, freshness "
    "gate lowering, probe authority, order authority, live authority, order "
    "admission, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_query_performed",
    "pg_write_performed",
    "placement_call_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "public_quote_capture_performed",
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
            "ready",
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


def _ready(payload: dict[str, Any], schema: str, status: str) -> bool:
    return payload.get("schema_version") == schema and payload.get("status") == status


def _candidate(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(payload.get("candidate"))
    return {key: candidate.get(key) for key in IDENTITY_FIELDS if candidate.get(key) is not None}


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(candidate.get(key) for key in IDENTITY_FIELDS)


def _candidate_match(candidates: list[dict[str, Any]]) -> bool:
    non_empty = [candidate for candidate in candidates if candidate]
    if len(non_empty) != len(candidates):
        return False
    first = _candidate_key(non_empty[0])
    return all(_candidate_key(candidate) == first for candidate in non_empty[1:])


def _tier_value(tier: dict[str, Any], key: str) -> Decimal | None:
    value = _dec(tier.get(key))
    return value if value is not None and value > 0 else None


def _normalize_tiers(worksheet: dict[str, Any]) -> list[dict[str, Any]]:
    raw_tiers = _list(_dict(worksheet.get("cap_staircase")).get("tiers"))
    tiers: list[dict[str, Any]] = []
    for raw in raw_tiers:
        tier = _dict(raw)
        tier_index = tier.get("tier_index")
        qty = _tier_value(tier, "qty")
        notional = _tier_value(tier, "notional_usdt")
        cap_pct = _tier_value(tier, "cap_utilization_pct")
        if qty is None or notional is None:
            continue
        try:
            index = int(tier_index)
        except (TypeError, ValueError):
            index = len(tiers) + 1
        tiers.append(
            {
                "tier_index": index,
                "qty": float(qty),
                "notional_usdt": float(notional),
                "cap_utilization_pct": float(cap_pct) if cap_pct is not None else None,
            }
        )
    return sorted(tiers, key=lambda item: item["tier_index"])


def _tier_priorities(tiers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    selected = tiers[:3]
    priorities: list[dict[str, Any]] = []
    roles = [
        "primary_min_exposure_mechanics_probe_after_separate_authorization",
        "secondary_micro_tier_after_clean_maker_fill_and_review",
        "tertiary_micro_tier_after_repeatability_review",
    ]
    for priority, tier in enumerate(selected, start=1):
        priorities.append(
            {
                "priority": priority,
                "tier_index": tier["tier_index"],
                "qty": tier["qty"],
                "notional_usdt": tier["notional_usdt"],
                "cap_utilization_pct": tier.get("cap_utilization_pct"),
                "role": roles[priority - 1],
                "review_only": True,
                "order_admission_ready": False,
            }
        )
    if tiers:
        ceiling = tiers[-1]
        priorities.append(
            {
                "priority": "cap_ceiling_reference_only",
                "tier_index": ceiling["tier_index"],
                "qty": ceiling["qty"],
                "notional_usdt": ceiling["notional_usdt"],
                "cap_utilization_pct": ceiling.get("cap_utilization_pct"),
                "role": "largest_existing_cap_tier_reference_not_initial_probe_size",
                "review_only": True,
                "order_admission_ready": False,
            }
        )
    return priorities


def _maker_placement_contract(
    *,
    candidate: dict[str, Any],
    worksheet: dict[str, Any],
    fee_schema: dict[str, Any],
    fresh_bbo_readiness: dict[str, Any],
    tiers: list[dict[str, Any]],
) -> dict[str, Any]:
    construction = _dict(worksheet.get("construction_inputs"))
    fee_contract = _dict(fee_schema.get("contract"))
    bbo_contract = _dict(fresh_bbo_readiness.get("contract"))
    market_gates = _dict(bbo_contract.get("freshness_and_market_data_gates"))
    maker_taker = _dict(fee_contract.get("maker_taker_policy"))
    fee_slippage = _dict(fee_contract.get("fee_slippage_policy"))
    risk_context = _dict(fee_contract.get("risk_and_cap_context")) or _dict(
        bbo_contract.get("risk_and_cap_context")
    )
    side = _str(candidate.get("side"))
    active_side_rules: dict[str, Any] = {
        "supported_candidate_side": side,
        "candidate_side_only": True,
    }
    if side.lower() == "sell":
        active_side_rules.update(
            {
                "passive_reference": "best_ask",
                "limit_price_rule": (
                    "ceil candidate best_ask to tick_size, then require "
                    "limit_price > best_bid"
                ),
                "marketable_cross_rule": "skip if post-round sell limit_price <= best_bid",
                "near_touch_maker_rule": (
                    "reviewed future construction may start at best_ask; post-only "
                    "rejection or crossing risk means skip, not taker fallback"
                ),
            }
        )
    else:
        active_side_rules.update(
            {
                "passive_reference": "best_bid",
                "limit_price_rule": (
                    "floor candidate best_bid to tick_size, then require "
                    "limit_price < best_ask"
                ),
                "marketable_cross_rule": "skip if post-round buy limit_price >= best_ask",
                "near_touch_maker_rule": "inactive unless candidate side changes by review",
            }
        )

    return {
        "candidate_identity": {
            "required_exact_fields": {key: candidate.get(key) for key in IDENTITY_FIELDS},
            "identity_rule": "all future quote, construction, order, fill, and outcome rows must exact-match this side-cell",
        },
        "tier_priority_policy": {
            "source": "current_cap_staircase_risk_worksheet.cap_staircase.tiers",
            "selection_rule": (
                "use the smallest executable current-cap tier first; larger tiers "
                "are review-only escalation candidates after clean attributed maker "
                "evidence, not initial proof"
            ),
            "tier_priorities": _tier_priorities(tiers),
            "all_existing_tiers": tiers,
            "order_admission_ready_from_this_policy": False,
        },
        "maker_first_placement_rules": {
            "mode": "post_only_maker_first_limit_or_skip",
            "time_in_force_required": "PostOnly",
            "market_order_allowed": False,
            "taker_fallback_allowed": False,
            "reduce_only_required": False,
            "candidate_side_rules": active_side_rules,
            "tick_size_required": True,
            "qty_step_required": True,
            "min_notional_required": True,
            "source_tick_size": construction.get("tick_size"),
            "source_qty_step": construction.get("qty_step"),
            "source_min_notional": construction.get("min_notional"),
            "post_only_reject_policy": "record skip/reject reason; do not retry as taker",
            "placement_call_allowed_by_this_policy": False,
        },
        "fresh_bbo_preconditions": {
            "fresh_bbo_readiness_schema": fresh_bbo_readiness.get("schema_version"),
            "max_fresh_bbo_age_ms": market_gates.get("max_fresh_bbo_age_ms"),
            "requires_public_quote_capture_first": True,
            "public_quote_capture_allowed_by_this_policy": False,
            "requires_adapter_backed_market_snapshot": True,
            "bid_ask_required": market_gates.get("bid_ask_required") is True,
            "bid_must_be_less_than_ask": market_gates.get("bid_must_be_less_than_ask")
            is True,
            "spread_bps_must_be_recorded": market_gates.get("spread_bps_must_be_recorded")
            is True,
            "instrument_status_required": market_gates.get("instrument_status_required"),
            "instrument_filters_required": market_gates.get("instrument_filters_required"),
        },
        "spread_cost_skip_policy": {
            "actual_spread_bps_required_before_order_admission": True,
            "reviewed_edge_cushion_bps_required_before_order_admission": True,
            "maker_fee_bps_required_before_outcome_proof": True,
            "taker_fee_bps_required_for_failure_analysis": True,
            "slippage_buffer_bps_required_before_order_admission": True,
            "skip_if_missing_any_required_cost_or_spread_input": True,
            "skip_formula": (
                "skip unless reviewed_expected_net_edge_bps - spread_bps - "
                "maker_fee_bps - slippage_buffer_bps > 0"
            ),
            "global_cost_gate_lowering_allowed": False,
            "freshness_gate_lowering_allowed": False,
        },
        "taker_fallback_fail_closed": {
            "taker_conversion_is_not_maker_path_success": True,
            "fully_attributed_taker_rows_require_execution_realism_review": True,
            "unattributed_or_cleanup_fills_count_for_profit_proof": False,
            "missing_liquidity_role_counts_for_profit_proof": False,
            "actual_fee_required_for_any_outcome_review": fee_slippage.get(
                "actual_fee_required"
            )
            is True,
            "actual_slippage_required_for_any_outcome_review": fee_slippage.get(
                "actual_slippage_required"
            )
            is True,
            "expected_liquidity_role": maker_taker.get(
                "expected_liquidity_role_for_bounded_probe"
            ),
        },
        "risk_and_cap_context": {
            "per_order_cap_usdt": risk_context.get("per_order_cap_usdt"),
            "max_probe_orders_before_review": risk_context.get(
                "max_probe_orders_before_review"
            ),
            "max_total_demo_notional_before_review": risk_context.get(
                "max_total_demo_notional_before_review"
            ),
            "max_executable_tier_reserved_notional_usdt": risk_context.get(
                "max_executable_tier_reserved_notional_usdt"
            ),
            "cap_mutation_required": False,
            "risk_mutation_required": False,
        },
        "failure_conditions": [
            "candidate_identity_mismatch",
            "fresh_bbo_missing_or_stale",
            "public_quote_not_adapter_backed",
            "instrument_not_trading_or_filters_missing",
            "spread_bps_missing_or_invalid",
            "reviewed_edge_cushion_missing",
            "post_round_limit_crosses_book",
            "post_only_rejected_then_retried_as_taker",
            "actual_fee_or_slippage_missing_from_outcome",
            "liquidity_role_missing",
            "unattributed_or_cleanup_fill_counted_as_proof",
            "cost_gate_or_freshness_gate_lowered",
            "runtime_or_plan_or_risk_mutation_attempted",
            "order_admission_claimed_without_separate_review",
        ],
        "future_review_requirements": [
            "review public quote capture packet before any capture",
            "rerun construction preview from adapter-backed fresh BBO snapshot",
            "obtain candidate-scoped bounded Demo authorization before any order path",
            "review order envelope with E3/BB before placement",
            "review candidate-matched maker outcomes after fees/slippage before proof",
        ],
        "max_safe_next_action": "prepare_reviewed_public_quote_capture_packet_no_capture_or_wait_real_auth_delta",
    }


def build_maker_first_micro_tier_policy(
    *,
    current_cap_worksheet: dict[str, Any] | None,
    fee_slippage_schema: dict[str, Any] | None,
    fresh_bbo_readiness: dict[str, Any] | None,
    current_cap_worksheet_path: Path | None = None,
    fee_slippage_schema_path: Path | None = None,
    fresh_bbo_readiness_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    worksheet = _dict(current_cap_worksheet)
    fee_schema = _dict(fee_slippage_schema)
    bbo_readiness = _dict(fresh_bbo_readiness)
    authority_ok, authority_reasons = _authority_preserved(
        worksheet,
        fee_schema,
        bbo_readiness,
    )
    worksheet_ready = _ready(worksheet, WORKSHEET_SCHEMA_VERSION, WORKSHEET_READY_STATUS)
    fee_ready = _ready(fee_schema, FEE_SCHEMA_VERSION, FEE_SCHEMA_READY_STATUS)
    bbo_ready = _ready(bbo_readiness, FRESH_BBO_SCHEMA_VERSION, FRESH_BBO_READY_STATUS)
    candidates = [_candidate(worksheet), _candidate(fee_schema), _candidate(bbo_readiness)]
    candidates_match = _candidate_match(candidates)
    candidate = candidates[0] if candidates_match else {}
    tiers = _normalize_tiers(worksheet)

    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not worksheet_ready:
        status = CURRENT_CAP_WORKSHEET_NOT_READY_STATUS
        reason = "current_cap_worksheet_input_not_ready"
    elif not fee_ready:
        status = FEE_SCHEMA_NOT_READY_STATUS
        reason = "fee_slippage_schema_input_not_ready"
    elif not bbo_ready:
        status = FRESH_BBO_READINESS_NOT_READY_STATUS
        reason = "fresh_bbo_readiness_input_not_ready"
    elif not candidates_match:
        status = CANDIDATE_MISSING_OR_MISMATCH_STATUS
        reason = "candidate_missing_or_mismatch_across_inputs"
    elif not tiers:
        status = CAP_TIER_LADDER_MISSING_STATUS
        reason = "current_cap_tier_ladder_missing_or_empty"
    else:
        status = READY_STATUS
        reason = "maker_first_micro_tier_policy_ready"

    contract = (
        _maker_placement_contract(
            candidate=candidate,
            worksheet=worksheet,
            fee_schema=fee_schema,
            fresh_bbo_readiness=bbo_readiness,
            tiers=tiers,
        )
        if status == READY_STATUS
        else {}
    )
    tier_priorities = _list(_dict(contract.get("tier_priority_policy")).get("tier_priorities"))
    primary_tier = _dict(tier_priorities[0]) if tier_priorities else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_inputs": {
            "current_cap_worksheet_path": (
                str(current_cap_worksheet_path) if current_cap_worksheet_path else None
            ),
            "current_cap_worksheet_schema_version": worksheet.get("schema_version"),
            "current_cap_worksheet_status": worksheet.get("status"),
            "fee_slippage_schema_path": (
                str(fee_slippage_schema_path) if fee_slippage_schema_path else None
            ),
            "fee_slippage_schema_version": fee_schema.get("schema_version"),
            "fee_slippage_schema_status": fee_schema.get("status"),
            "fresh_bbo_readiness_path": (
                str(fresh_bbo_readiness_path) if fresh_bbo_readiness_path else None
            ),
            "fresh_bbo_readiness_schema_version": bbo_readiness.get("schema_version"),
            "fresh_bbo_readiness_status": bbo_readiness.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "candidate_match": candidates_match,
            "tier_count": len(tiers),
        },
        "candidate": candidate if status == READY_STATUS else {},
        "contract": contract,
        "summary": {
            "maker_first_micro_tier_policy_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "primary_tier_index": primary_tier.get("tier_index"),
            "primary_qty": primary_tier.get("qty"),
            "primary_notional_usdt": primary_tier.get("notional_usdt"),
            "tier_priority_count": len(tier_priorities),
            "mode": "post_only_maker_first_limit_or_skip" if status == READY_STATUS else None,
            "placement_call_allowed_by_this_policy": False,
            "public_quote_capture_allowed_by_this_policy": False,
            "order_admission_ready": False,
            "p0_authorization_required_before_probe": True,
            "max_safe_next_action": (
                contract.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_inputs"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "maker_first_micro_tier_policy_ready": status == READY_STATUS,
            "public_quote_capture_performed": False,
            "placement_call_performed": False,
            "bybit_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "cookie_headers_present": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "cap_mutation_performed": False,
            "risk_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "order_admission_ready": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    contract = _dict(packet.get("contract"))
    lines = [
        "# Maker-First Micro-Tier Placement Policy",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Tier Priority Policy", ""])
    tier_policy = _dict(contract.get("tier_priority_policy"))
    if tier_policy:
        lines.append("```json")
        lines.append(
            json.dumps(
                {
                    "selection_rule": tier_policy.get("selection_rule"),
                    "tier_priorities": tier_policy.get("tier_priorities"),
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        lines.append("```")
    lines.extend(["", "## Placement And Skip Rules", ""])
    for key in (
        "maker_first_placement_rules",
        "fresh_bbo_preconditions",
        "spread_cost_skip_policy",
        "taker_fallback_fail_closed",
    ):
        section = _dict(contract.get(key))
        if not section:
            continue
        lines.append(f"### `{key}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(section, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    lines.extend(["## No-Authority Answers", ""])
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
    parser.add_argument("--current-cap-worksheet-json", type=Path, required=True)
    parser.add_argument("--fee-slippage-schema-json", type=Path, required=True)
    parser.add_argument("--fresh-bbo-readiness-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_maker_first_micro_tier_policy(
        current_cap_worksheet=_read_json(args.current_cap_worksheet_json),
        fee_slippage_schema=_read_json(args.fee_slippage_schema_json),
        fresh_bbo_readiness=_read_json(args.fresh_bbo_readiness_json),
        current_cap_worksheet_path=args.current_cap_worksheet_json,
        fee_slippage_schema_path=args.fee_slippage_schema_json,
        fresh_bbo_readiness_path=args.fresh_bbo_readiness_json,
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

#!/usr/bin/env python3
"""Shadow-evaluate the near-touch bounded Demo placement repair plan.

This artifact consumes the no-authority placement repair plan plus the latest
Demo order-to-fill touchability audit. It applies the proposed near-touch-or-skip
formula to already-observed orders and measures whether it would have reduced
the passive gap enough to create touchable learning attempts.

It does not query PG, call Bybit, submit orders, lower the Cost Gate, grant
probe/order authority, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


SHADOW_PLACEMENT_IMPACT_SCHEMA_VERSION = (
    "bounded_demo_probe_shadow_placement_impact_v1"
)
PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION = (
    "bounded_demo_probe_placement_repair_plan_v1"
)
ORDER_TOUCHABILITY_SCHEMA_VERSION = "demo_order_to_fill_gap_audit_v1"
READY_REPAIR_STATUS = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
BOUNDARY = (
    "artifact-only bounded Demo shadow placement impact; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _artifact_status(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = (
        (payload or {}).get("generated_at_utc")
        or (payload or {}).get("generated")
        or (payload or {}).get("ts_utc")
    )
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _authority_preserved(placement_repair_plan: dict[str, Any] | None) -> bool:
    payload = _dict(placement_repair_plan)
    answers = _dict(payload.get("answers"))
    plan = _dict(payload.get("placement_repair_plan"))
    boundary = _dict(plan.get("authority_boundary"))
    for source in (payload, answers, plan, boundary):
        if source.get("global_cost_gate_lowering_recommended") is True:
            return False
        if source.get("probe_authority_granted") is True:
            return False
        if source.get("order_authority_granted") is True:
            return False
        if source.get("promotion_evidence") is True:
            return False
        if source.get("promotion_proof") is True:
            return False
        if source.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
    return True


def _candidate(placement_repair_plan: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(placement_repair_plan)
    plan = _dict(payload.get("placement_repair_plan"))
    candidate = _dict(plan.get("candidate")) or _dict(payload.get("candidate"))
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _side_cell_key(order: dict[str, Any]) -> str | None:
    strategy = order.get("strategy_name")
    symbol = order.get("symbol")
    side = order.get("side")
    if not strategy or not symbol or not side:
        return None
    return f"{strategy}|{symbol}|{side}"


def _is_candidate_match(order: dict[str, Any], candidate: dict[str, Any]) -> bool:
    return (
        str(order.get("strategy_name") or "").lower()
        == str(candidate.get("strategy_name") or "").lower()
        and str(order.get("symbol") or "").upper()
        == str(candidate.get("symbol") or "").upper()
        and str(order.get("side") or "").lower()
        == str(candidate.get("side") or "").lower()
    )


def _bps(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return round((numerator / denominator) * 10_000.0, 4)


def _shadow_order(
    order: dict[str, Any],
    *,
    candidate: dict[str, Any],
    max_initial_passive_gap_bps: float | None,
) -> dict[str, Any]:
    side = str(order.get("side") or "").lower()
    bid = _float(order.get("placement_best_bid"))
    ask = _float(order.get("placement_best_ask"))
    classification = _dict(order.get("classification"))
    original_gap = (
        _float(classification.get("best_touch_gap_bps"))
        if classification
        else None
    )
    if original_gap is None:
        original_gap = _float(classification.get("placement_gap_bps"))
    max_gap = max_initial_passive_gap_bps
    candidate_match = _is_candidate_match(order, candidate)

    base = {
        "order_id": order.get("order_id"),
        "intent_id": order.get("intent_id"),
        "order_ts": order.get("order_ts"),
        "side_cell_key": _side_cell_key(order),
        "strategy_name": order.get("strategy_name"),
        "symbol": order.get("symbol"),
        "side": order.get("side"),
        "time_in_force": order.get("time_in_force"),
        "original_effective_limit_price": _round(order.get("effective_limit_price")),
        "original_best_touch_gap_bps": _round(original_gap),
        "placement_bbo_ts": order.get("placement_bbo_ts"),
        "placement_best_bid": _round(bid),
        "placement_best_ask": _round(ask),
        "candidate_match": candidate_match,
    }
    if bid is None or ask is None or bid <= 0 or ask <= 0 or bid >= ask:
        return {
            **base,
            "status": "WOULD_SKIP_INVALID_OR_MISSING_PLACEMENT_BBO",
            "reason": "valid placement BBO is required before shadow repair",
            "would_submit_under_repair": False,
            "shadow_limit_price": None,
            "shadow_initial_touch_gap_bps": None,
            "gap_reduction_bps": None,
            "future_bbo_would_cross_shadow_limit": False,
        }

    if side == "buy":
        shadow_limit = bid
        shadow_gap = _bps(ask - shadow_limit, ask)
        future_reference = _float(order.get("min_best_ask"))
        future_crossed = (
            future_reference is not None and future_reference <= shadow_limit
        )
        formula = "best_bid"
    elif side == "sell":
        shadow_limit = ask
        shadow_gap = _bps(shadow_limit - bid, bid)
        future_reference = _float(order.get("max_best_bid"))
        future_crossed = (
            future_reference is not None and future_reference >= shadow_limit
        )
        formula = "best_ask"
    else:
        return {
            **base,
            "status": "WOULD_SKIP_UNSUPPORTED_SIDE",
            "reason": "order side is neither Buy nor Sell",
            "would_submit_under_repair": False,
            "shadow_limit_price": None,
            "shadow_initial_touch_gap_bps": None,
            "gap_reduction_bps": None,
            "future_bbo_would_cross_shadow_limit": False,
        }

    would_submit = (
        max_gap is not None and shadow_gap is not None and shadow_gap <= max_gap
    )
    gap_reduction = (
        round(original_gap - shadow_gap, 4)
        if original_gap is not None and shadow_gap is not None
        else None
    )
    if would_submit:
        status = "WOULD_SUBMIT_NEAR_TOUCH"
        reason = "shadow near-touch limit satisfies max initial passive gap"
    else:
        status = "WOULD_SKIP_GAP_TOO_WIDE"
        reason = "shadow near-touch limit still exceeds max initial passive gap"
    return {
        **base,
        "status": status,
        "reason": reason,
        "would_submit_under_repair": would_submit,
        "shadow_limit_formula": formula,
        "shadow_limit_price": _round(shadow_limit),
        "shadow_initial_touch_gap_bps": _round(shadow_gap),
        "max_initial_passive_gap_bps": _round(max_gap),
        "gap_reduction_bps": gap_reduction,
        "future_bbo_reference": _round(future_reference),
        "future_bbo_would_cross_shadow_limit": future_crossed,
    }


def _summary(shadow_orders: list[dict[str, Any]]) -> dict[str, Any]:
    reviewed = len(shadow_orders)
    submit_orders = [o for o in shadow_orders if o.get("would_submit_under_repair")]
    skip_orders = [o for o in shadow_orders if not o.get("would_submit_under_repair")]
    matched = [o for o in shadow_orders if o.get("candidate_match") is True]
    matched_submit = [o for o in matched if o.get("would_submit_under_repair")]
    gaps = [
        _float(o.get("shadow_initial_touch_gap_bps"))
        for o in submit_orders
        if _float(o.get("shadow_initial_touch_gap_bps")) is not None
    ]
    reductions = [
        _float(o.get("gap_reduction_bps"))
        for o in shadow_orders
        if _float(o.get("gap_reduction_bps")) is not None
    ]
    original_gaps = [
        _float(o.get("original_best_touch_gap_bps"))
        for o in shadow_orders
        if _float(o.get("original_best_touch_gap_bps")) is not None
    ]
    status_counts: dict[str, int] = {}
    for order in shadow_orders:
        status = str(order.get("status") or "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    return {
        "reviewed_order_count": reviewed,
        "shadow_submit_count": len(submit_orders),
        "shadow_skip_count": len(skip_orders),
        "candidate_matched_order_count": len(matched),
        "candidate_matched_submit_count": len(matched_submit),
        "future_bbo_would_cross_shadow_limit_count": sum(
            1
            for order in shadow_orders
            if order.get("future_bbo_would_cross_shadow_limit") is True
        ),
        "status_counts": status_counts,
        "max_original_best_touch_gap_bps": (
            round(max(original_gaps), 4) if original_gaps else None
        ),
        "max_shadow_initial_touch_gap_bps": (
            round(max(gaps), 4) if gaps else None
        ),
        "avg_shadow_initial_touch_gap_bps": (
            round(sum(gaps) / len(gaps), 4) if gaps else None
        ),
        "max_gap_reduction_bps": (
            round(max(reductions), 4) if reductions else None
        ),
        "avg_gap_reduction_bps": (
            round(sum(reductions) / len(reductions), 4) if reductions else None
        ),
        "sample_scope": (
            "candidate_matched_runtime_sample"
            if matched
            else "current_demo_order_flow_not_candidate_matched"
        ),
    }


def _status(
    *,
    placement_artifact: dict[str, Any],
    order_artifact: dict[str, Any],
    placement_repair_plan: dict[str, Any] | None,
    authority_preserved: bool,
    summary: dict[str, Any],
) -> tuple[str, str, list[str]]:
    if authority_preserved is not True:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "placement_repair_plan_contains_authority_granting_fields",
            ["remove_authority_granting_input_before_shadow_placement_review"],
        )
    if (
        placement_artifact.get("status") != "FRESH"
        or placement_artifact.get("schema_version")
        != PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
    ):
        return (
            "PLACEMENT_REPAIR_PLAN_REQUIRED",
            "fresh_bounded_demo_probe_placement_repair_plan_v1_required",
            ["refresh_bounded_probe_placement_repair_plan_before_shadow_impact"],
        )
    if (
        order_artifact.get("status") != "FRESH"
        or order_artifact.get("schema_version") != ORDER_TOUCHABILITY_SCHEMA_VERSION
    ):
        return (
            "ORDER_TOUCHABILITY_AUDIT_REQUIRED",
            "fresh_demo_order_to_fill_gap_audit_v1_required",
            ["refresh_demo_order_to_fill_gap_audit_before_shadow_impact"],
        )

    source_status = str((_dict(placement_repair_plan)).get("status") or "")
    if source_status != READY_REPAIR_STATUS:
        return (
            "PLACEMENT_REPAIR_PLAN_NOT_READY",
            "placement_repair_plan_is_not_operator_review_ready",
            ["resolve_placement_repair_plan_status_before_shadow_impact"],
        )
    if summary.get("reviewed_order_count") == 0:
        return (
            "ORDER_TOUCHABILITY_SAMPLE_REQUIRED",
            "order_touchability_audit_has_no_orders_to_shadow",
            ["continue_demo_order_flow_until_shadow_placement_sample_exists"],
        )
    if summary.get("shadow_submit_count") == 0:
        return (
            "SHADOW_PLACEMENT_REPAIR_WOULD_SKIP_ALL_ORDERS",
            "near_touch_or_skip_rule_would_skip_all_reviewed_orders",
            ["inspect_bbo_spread_or_max_initial_gap_before_rust_patch"],
        )
    if summary.get("candidate_matched_order_count") == 0:
        return (
            "SHADOW_PLACEMENT_TOUCHABILITY_IMPROVED_SAMPLE_MISMATCH",
            "near_touch_rule_improves_current_order_flow_but_sample_is_not_candidate_matched",
            [
                "operator_review_mechanical_touchability_before_rust_patch",
                "collect_candidate_matched_bounded_demo_probe_evidence_after_authorization",
            ],
        )
    if (
        summary.get("candidate_matched_order_count")
        == summary.get("candidate_matched_submit_count")
    ):
        return (
            "SHADOW_PLACEMENT_TOUCHABILITY_REPAIR_EFFECTIVE_FOR_MATCHED_SAMPLE",
            "near_touch_rule_would_make_candidate_matched_orders_touchable",
            [
                "operator_review_existing_rust_authority_path_patch",
                "run_bounded_demo_probe_then_refresh_fill_lineage_and_execution_realism",
            ],
        )
    return (
        "SHADOW_PLACEMENT_PARTIAL_SKIP_REQUIRED",
        "near_touch_rule_would_submit_only_part_of_candidate_matched_sample",
        ["review_shadow_skips_before_rust_patch"],
    )


def build_bounded_demo_probe_shadow_placement_impact(
    *,
    order_to_fill_gap_audit: dict[str, Any] | None,
    placement_repair_plan: dict[str, Any] | None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    placement_artifact = _artifact_status(
        placement_repair_plan,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    order_artifact = _artifact_status(
        order_to_fill_gap_audit,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    authority_preserved = _authority_preserved(placement_repair_plan)
    candidate = _candidate(placement_repair_plan)
    plan = _dict((_dict(placement_repair_plan)).get("placement_repair_plan"))
    max_initial_gap = _float(plan.get("max_initial_passive_gap_bps"))
    shadow_orders = [
        _shadow_order(
            order,
            candidate=candidate,
            max_initial_passive_gap_bps=max_initial_gap,
        )
        for order in _list((_dict(order_to_fill_gap_audit)).get("orders"))
        if isinstance(order, dict)
    ]
    summary = _summary(shadow_orders)
    status, reason, next_actions = _status(
        placement_artifact=placement_artifact,
        order_artifact=order_artifact,
        placement_repair_plan=placement_repair_plan,
        authority_preserved=authority_preserved,
        summary=summary,
    )
    return {
        "schema_version": SHADOW_PLACEMENT_IMPACT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "candidate": candidate,
        "artifacts": {
            "placement_repair_plan": placement_artifact,
            "demo_order_to_fill_gap_audit": order_artifact,
        },
        "source_status": {
            "placement_repair_plan_status": (
                _dict(placement_repair_plan).get("status")
            ),
            "order_touchability_status": (
                _dict(_dict(order_to_fill_gap_audit).get("summary")).get("status")
            ),
            "authority_preserved": authority_preserved,
        },
        "shadow_summary": summary,
        "shadow_orders": shadow_orders,
        "answers": {
            "shadow_placement_improves_touchability": (
                summary.get("shadow_submit_count", 0) > 0
                and (summary.get("max_gap_reduction_bps") or 0) > 0
            ),
            "candidate_matched_runtime_sample_present": (
                summary.get("candidate_matched_order_count", 0) > 0
            ),
            "candidate_specific_alpha_proof": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("shadow_summary"))
    lines = [
        "# Bounded Demo Probe Shadow Placement Impact",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Sample scope: `{summary.get('sample_scope')}`",
        f"- Reviewed orders: `{summary.get('reviewed_order_count')}`",
        f"- Shadow submit count: `{summary.get('shadow_submit_count')}`",
        f"- Candidate-matched orders: `{summary.get('candidate_matched_order_count')}`",
        f"- Max original best-touch gap bps: `{summary.get('max_original_best_touch_gap_bps')}`",
        f"- Max shadow initial touch gap bps: `{summary.get('max_shadow_initial_touch_gap_bps')}`",
        f"- Max gap reduction bps: `{summary.get('max_gap_reduction_bps')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Next Actions",
        "",
    ]
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    lines.extend(
        [
            "",
            "## Shadow Orders",
            "",
            "| order | side-cell | shadow_status | original_gap_bps | shadow_gap_bps | reduction_bps |",
            "|---|---|---|---:|---:|---:|",
        ]
    )
    for order in packet.get("shadow_orders") or []:
        lines.append(
            "| "
            f"{order.get('order_id')} | {order.get('side_cell_key')} | "
            f"{order.get('status')} | {order.get('original_best_touch_gap_bps')} | "
            f"{order.get('shadow_initial_touch_gap_bps')} | "
            f"{order.get('gap_reduction_bps')} |"
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--order-to-fill-gap-json", type=Path)
    parser.add_argument("--placement-repair-plan-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_shadow_placement_impact(
        order_to_fill_gap_audit=_read_json(args.order_to_fill_gap_json),
        placement_repair_plan=_read_json(args.placement_repair_plan_json),
        max_artifact_age_hours=args.max_artifact_age_hours,
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not args.output and not args.json_output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

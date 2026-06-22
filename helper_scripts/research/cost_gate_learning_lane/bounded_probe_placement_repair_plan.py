#!/usr/bin/env python3
"""Build a no-authority near-touch placement repair plan for bounded Demo probes.

This artifact consumes ``bounded_demo_probe_touchability_preflight_v1``. When
the current Demo order flow is proven to be deep passive no-touch, it converts
the touchability requirements into an operator-reviewable near-touch-or-skip
placement plan.

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


PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION = (
    "bounded_demo_probe_placement_repair_plan_v1"
)
TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION = (
    "bounded_demo_probe_touchability_preflight_v1"
)
BOUNDARY = (
    "artifact-only bounded Demo probe placement repair plan; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)

REPAIR_READY_STATUS = "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE"
FILL_FLOW_READY_STATUS = "TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW"
PASSTHROUGH_BLOCKING_STATUSES = {
    "BOUNDED_PROBE_DESIGN_NOT_READY",
    "ORDER_TOUCHABILITY_AUDIT_REQUIRED",
    "FILL_PATH_RECONCILE_REQUIRED",
    "ORDER_PRICE_METADATA_REPAIR_REQUIRED",
    "BBO_COVERAGE_REPAIR_REQUIRED",
    "ORDER_TOUCHABILITY_DATA_REQUIRED",
    "TOUCHABILITY_REVIEW_REQUIRED",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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


def _authority_preserved(touchability_preflight: dict[str, Any] | None) -> bool:
    payload = _dict(touchability_preflight)
    answers = _dict(payload.get("answers"))
    design = _dict(payload.get("bounded_probe_design"))
    for source in (payload, answers, design):
        if source.get("global_cost_gate_lowering_recommended") is True:
            return False
        if source.get("probe_authority_granted") is True:
            return False
        if source.get("order_authority_granted") is True:
            return False
        if source.get("promotion_evidence") is True:
            return False
        if source.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
    return True


def _candidate(touchability_preflight: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(touchability_preflight)
    candidate = _dict(payload.get("candidate"))
    design = _dict(payload.get("bounded_probe_design"))
    return {
        "side_cell_key": candidate.get("side_cell_key") or design.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name") or design.get("strategy_name"),
        "symbol": candidate.get("symbol") or design.get("symbol"),
        "side": candidate.get("side") or design.get("side"),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or design.get("outcome_horizon_minutes")
        ),
    }


def _touchability_summary(
    touchability_preflight: dict[str, Any] | None,
) -> dict[str, Any]:
    payload = _dict(touchability_preflight)
    touch = _dict(payload.get("order_touchability"))
    placement = _dict(payload.get("placement_requirements"))
    return {
        "preflight_status": payload.get("status"),
        "preflight_reason": payload.get("reason"),
        "order_touchability_status": touch.get("status"),
        "reviewed_orders": _int(touch.get("reviewed_orders")),
        "fill_rows": _int(touch.get("fill_rows")),
        "deep_passive_no_touch_orders": _int(
            touch.get("deep_passive_no_touch_orders")
        ),
        "bbo_touched_no_fill_orders": _int(
            touch.get("bbo_touched_no_fill_orders")
        ),
        "max_best_touch_gap_bps": _round(touch.get("max_best_touch_gap_bps")),
        "min_best_touch_gap_bps": _round(touch.get("min_best_touch_gap_bps")),
        "max_initial_passive_gap_bps": _round(
            placement.get("max_initial_passive_gap_bps")
        ),
        "max_deep_no_touch_gap_bps": _round(
            placement.get("max_deep_no_touch_gap_bps")
        ),
        "max_probe_intents_before_review": _int(
            placement.get("max_probe_intents_before_review"),
            default=3,
        ),
        "max_demo_notional_usdt_per_order": _float(
            placement.get("max_demo_notional_usdt_per_order")
        ),
    }


def _status(
    *,
    artifact: dict[str, Any],
    authority_preserved: bool,
    touchability_preflight: dict[str, Any] | None,
) -> tuple[str, str, list[str]]:
    payload = _dict(touchability_preflight)
    if authority_preserved is not True:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "touchability_preflight_contains_authority_granting_fields",
            ["remove_authority_granting_input_before_placement_repair_review"],
        )
    if (
        artifact.get("status") != "FRESH"
        or artifact.get("schema_version") != TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION
    ):
        return (
            "TOUCHABILITY_PREFLIGHT_REQUIRED",
            "fresh_bounded_demo_probe_touchability_preflight_v1_required",
            ["refresh_bounded_probe_touchability_preflight_before_repair_plan"],
        )

    source_status = str(payload.get("status") or "")
    source_reason = str(payload.get("reason") or "")
    source_actions = [str(action) for action in _list(payload.get("next_actions"))]
    if source_status == REPAIR_READY_STATUS:
        return (
            "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW",
            "deep_passive_no_touch_requires_near_touch_or_skip_probe_placement",
            [
                "operator_review_near_touch_or_skip_placement_repair_plan",
                "only_after_separate_authorization_patch_existing_rust_authority_path",
                "rerun_order_to_fill_touchability_audit_after_first_repaired_probe",
            ],
        )
    if source_status == FILL_FLOW_READY_STATUS:
        return (
            "PLACEMENT_REPAIR_NOT_REQUIRED_TOUCHABILITY_REVIEW_READY",
            "fill_flow_exists_so_review_fill_quality_before_placement_repair",
            ["review_fill_quality_and_edge_capture_before_placement_repair"],
        )
    if source_status in PASSTHROUGH_BLOCKING_STATUSES:
        return (
            source_status,
            source_reason or "touchability_preflight_blocks_placement_repair_plan",
            source_actions
            or ["repair_upstream_touchability_preflight_blocker_before_placement_plan"],
        )
    return (
        "PLACEMENT_REPAIR_PLAN_NOT_READY",
        "touchability_preflight_status_does_not_require_or_allow_placement_repair",
        source_actions or ["review_touchability_preflight_before_placement_plan"],
    )


def _repair_plan(
    *,
    status: str,
    candidate: dict[str, Any],
    summary: dict[str, Any],
    max_fresh_bbo_age_ms: int,
) -> dict[str, Any]:
    max_initial_gap = summary.get("max_initial_passive_gap_bps")
    max_deep_gap = summary.get("max_deep_no_touch_gap_bps")
    ready = status == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
    return {
        "schema_version": PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION,
        "status": "OPERATOR_REVIEW_READY_NOT_ACTIVE"
        if ready
        else "NOT_ACTIVE_BLOCKED",
        "active": False,
        "requires_separate_operator_authorization": True,
        "order_mode": "post_only_near_touch_or_skip",
        "environment": "demo_or_live_demo_only",
        "implementation_target": "future_operator_approved_existing_rust_authority_path_patch",
        "execution_path": "existing_rust_authority_path_only",
        "max_fresh_bbo_age_ms": max_fresh_bbo_age_ms,
        "max_initial_passive_gap_bps": max_initial_gap,
        "max_deep_no_touch_gap_bps": max_deep_gap,
        "candidate": candidate,
        "probe_limits": {
            "max_probe_intents_before_review": summary.get(
                "max_probe_intents_before_review"
            ),
            "max_demo_notional_usdt_per_order": summary.get(
                "max_demo_notional_usdt_per_order"
            ),
        },
        "runtime_touchability_baseline": {
            "order_touchability_status": summary.get("order_touchability_status"),
            "reviewed_orders": summary.get("reviewed_orders"),
            "fill_rows": summary.get("fill_rows"),
            "deep_passive_no_touch_orders": summary.get(
                "deep_passive_no_touch_orders"
            ),
            "max_best_touch_gap_bps": summary.get("max_best_touch_gap_bps"),
            "min_best_touch_gap_bps": summary.get("min_best_touch_gap_bps"),
        },
        "pre_order_checks": [
            "fresh_bbo_snapshot_age_lte_max_fresh_bbo_age_ms",
            "instrument_tick_size_and_qty_step_loaded_from_existing_authority_path",
            "computed_post_only_limit_is_maker_side_and_not_crossing",
            "computed_best_touch_gap_bps_lte_max_initial_passive_gap_bps",
            "if_gap_exceeds_limit_skip_probe_order_and_record_touchability_block",
            "respect_max_demo_notional_usdt_per_order",
            "respect_max_probe_intents_before_review",
        ],
        "side_aware_limit_rule": {
            "Buy": {
                "post_only_limit_formula": "min(best_bid, best_ask - tick_size)",
                "touch_gap_bps_formula": "(best_ask - limit_price) / best_ask * 10000",
                "skip_if": "touch_gap_bps > max_initial_passive_gap_bps",
            },
            "Sell": {
                "post_only_limit_formula": "max(best_ask, best_bid + tick_size)",
                "touch_gap_bps_formula": "(limit_price - best_bid) / best_bid * 10000",
                "skip_if": "touch_gap_bps > max_initial_passive_gap_bps",
            },
        },
        "skip_record": {
            "record_type": "bounded_probe_touchability_block",
            "required_fields": [
                "side_cell_key",
                "symbol",
                "side",
                "bbo_ts",
                "best_bid",
                "best_ask",
                "computed_limit_price",
                "touch_gap_bps",
                "max_initial_passive_gap_bps",
                "reason",
            ],
            "reason": "probe_order_skipped_because_near_touch_requirement_not_met",
        },
        "post_order_evidence": [
            "demo_order_intent_and_order_state_rows",
            "demo_order_to_fill_gap_audit_after_probe",
            "fill_fee_slippage_rows_after_fill",
            "bounded_probe_result_review",
            "matched_blocked_signal_control_outcomes",
            "bounded_probe_execution_realism_review_if_edge_under_captured",
        ],
        "authority_boundary": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }


def build_bounded_demo_probe_placement_repair_plan(
    *,
    touchability_preflight: dict[str, Any] | None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
    max_fresh_bbo_age_ms: int = 1000,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if max_fresh_bbo_age_ms < 1 or max_fresh_bbo_age_ms > 60_000:
        raise ValueError("max_fresh_bbo_age_ms must be in [1, 60000]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    artifact = _artifact_status(
        touchability_preflight,
        now_utc=now,
        max_age_seconds=max_artifact_age_hours * 3600,
    )
    authority_preserved = _authority_preserved(touchability_preflight)
    status, reason, next_actions = _status(
        artifact=artifact,
        authority_preserved=authority_preserved,
        touchability_preflight=touchability_preflight,
    )
    candidate = _candidate(touchability_preflight)
    summary = _touchability_summary(touchability_preflight)
    repair_plan = _repair_plan(
        status=status,
        candidate=candidate,
        summary=summary,
        max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
    )
    return {
        "schema_version": PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "candidate": candidate,
        "source_touchability_preflight": {
            "artifact": artifact,
            "status": summary.get("preflight_status"),
            "reason": summary.get("preflight_reason"),
            "authority_preserved": authority_preserved,
        },
        "touchability_summary": summary,
        "placement_repair_plan": repair_plan,
        "answers": {
            "placement_repair_plan_ready_for_operator_review": (
                status == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
            ),
            "near_touch_or_skip_required": (
                status == "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
            ),
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
    summary = _dict(packet.get("touchability_summary"))
    plan = _dict(packet.get("placement_repair_plan"))
    lines = [
        "# Bounded Demo Probe Placement Repair Plan",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Order-touchability status: `{summary.get('order_touchability_status')}`",
        f"- Deep passive no-touch orders: `{summary.get('deep_passive_no_touch_orders')}`",
        f"- Max observed best-touch gap bps: `{summary.get('max_best_touch_gap_bps')}`",
        f"- Required max initial passive gap bps: `{plan.get('max_initial_passive_gap_bps')}`",
        f"- Order mode: `{plan.get('order_mode')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Next Actions",
        "",
    ]
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
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
    parser.add_argument("--touchability-preflight-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--max-fresh-bbo-age-ms", type=int, default=1000)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_placement_repair_plan(
        touchability_preflight=_read_json(args.touchability_preflight_json),
        max_artifact_age_hours=args.max_artifact_age_hours,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
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

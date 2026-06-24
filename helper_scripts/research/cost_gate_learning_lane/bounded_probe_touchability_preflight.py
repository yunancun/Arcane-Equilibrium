#!/usr/bin/env python3
"""Preflight bounded Demo probe design against order touchability evidence.

This artifact sits after a bounded Demo probe preflight packet and the Demo
order-to-fill gap audit. It converts "orders exist but did not fill" into a
machine-checkable placement-design gate before any bounded Demo probe is even
reviewed.

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


TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION = "bounded_demo_probe_touchability_preflight_v1"
SUPPORTED_BOUNDED_PROBE_PREFLIGHT_SCHEMA_VERSIONS = {
    "sealed_horizon_bounded_demo_probe_preflight_v1",
    "cost_gate_false_negative_bounded_demo_probe_preflight_v1",
}
BOUNDARY = (
    "artifact-only bounded Demo probe touchability preflight; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)

DESIGN_REVIEWABLE_STATUSES = {
    "OPERATOR_REVIEW_READY_FOR_BOUNDED_DEMO_PROBE_DESIGN",
    "READY_FOR_SEPARATE_OPERATOR_AUTHORIZATION",
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


def _design_summary(preflight: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(preflight)
    answers = _dict(payload.get("answers"))
    design = _dict(payload.get("bounded_demo_probe_design"))
    candidate = _dict(design.get("candidate"))
    limits = _dict(design.get("suggested_initial_probe_limits"))
    boundary = _dict(design.get("authority_boundary"))
    return {
        "preflight_schema_version": payload.get("schema_version"),
        "preflight_status": payload.get("status"),
        "design_schema_version": design.get("schema_version"),
        "design_status": design.get("status"),
        "side_cell_key": candidate.get("side_cell_key") or payload.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": (
            candidate.get("outcome_horizon_minutes")
            or payload.get("outcome_horizon_minutes")
        ),
        "max_probe_intents_before_review": _int(
            limits.get("max_probe_intents_before_review"),
            default=3,
        ),
        "max_demo_notional_usdt_per_order": _float(
            limits.get("max_demo_notional_usdt_per_order")
        ),
        "reviewable": (
            payload.get("schema_version")
            in SUPPORTED_BOUNDED_PROBE_PREFLIGHT_SCHEMA_VERSIONS
            and design.get("schema_version") == "bounded_demo_probe_design_v1"
            and design.get("status") in DESIGN_REVIEWABLE_STATUSES
            and bool(candidate.get("side_cell_key") or payload.get("side_cell_key"))
        ),
        "authority_preserved": _authority_preserved(payload, answers, boundary),
    }


def _authority_preserved(*sources: dict[str, Any]) -> bool:
    for source in sources:
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


def _order_touchability_summary(order_audit: dict[str, Any] | None) -> dict[str, Any]:
    payload = _dict(order_audit)
    summary = _dict(payload.get("summary"))
    counts = _dict(summary.get("counts"))
    answers = _dict(summary.get("answers"))
    orders = [_dict(row) for row in _list(payload.get("orders"))]
    gaps = [
        value
        for value in (
            _float(_dict(order.get("classification")).get("best_touch_gap_bps"))
            for order in orders
        )
        if value is not None
    ]
    classifications: dict[str, int] = {}
    for order in orders:
        status = str(
            _dict(order.get("classification")).get("status") or "UNKNOWN"
        )
        classifications[status] = classifications.get(status, 0) + 1
    return {
        "schema_version": payload.get("schema_version"),
        "status": summary.get("status"),
        "reason": summary.get("reason"),
        "next_action": summary.get("next_action"),
        "reviewed_orders": _int(counts.get("reviewed_orders")),
        "fill_rows": _int(counts.get("fill_rows")),
        "post_only_orders": _int(counts.get("post_only_orders")),
        "orders_price_missing": _int(counts.get("orders_price_missing")),
        "effective_limit_prices_inferred": _int(
            counts.get("effective_limit_prices_inferred")
        ),
        "bbo_touched_no_fill_orders": _int(
            counts.get("bbo_touched_no_fill_orders")
        ),
        "deep_passive_no_touch_orders": _int(
            counts.get("deep_passive_no_touch_orders")
        ),
        "no_bbo_coverage_orders": _int(counts.get("no_bbo_coverage_orders")),
        "passive_limits_too_deep": answers.get("passive_limits_too_deep") is True,
        "bbo_touched_without_fill": answers.get("bbo_touched_without_fill") is True,
        "fills_present": answers.get("fills_present") is True,
        "orders_present": answers.get("orders_present") is True,
        "max_best_touch_gap_bps": _round(max(gaps), 4) if gaps else None,
        "min_best_touch_gap_bps": _round(min(gaps), 4) if gaps else None,
        "classification_counts": classifications,
    }


def _touchability_status(
    *,
    preflight_artifact_status: str,
    order_artifact_status: str,
    design: dict[str, Any],
    touchability: dict[str, Any],
) -> tuple[str, str, list[str]]:
    if design["authority_preserved"] is not True:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "preflight_or_design_contains_authority_granting_fields",
            ["remove_authority_granting_input_before_touchability_review"],
        )
    if preflight_artifact_status != "FRESH" or design["reviewable"] is not True:
        return (
            "BOUNDED_PROBE_DESIGN_NOT_READY",
            "sealed_horizon_preflight_or_bounded_probe_design_is_not_reviewable",
            ["refresh_sealed_horizon_probe_preflight_before_touchability_review"],
        )
    if order_artifact_status != "FRESH" or touchability["schema_version"] != "demo_order_to_fill_gap_audit_v1":
        return (
            "ORDER_TOUCHABILITY_AUDIT_REQUIRED",
            "fresh_demo_order_to_fill_gap_audit_v1_required",
            ["run_demo_order_to_fill_gap_audit_before_bounded_probe_review"],
        )

    audit_status = str(touchability.get("status") or "")
    if audit_status == "BBO_TOUCHED_NO_FILL_RECONCILE_REQUIRED":
        return (
            "FILL_PATH_RECONCILE_REQUIRED",
            "BBO_touched_one_or_more_orders_but_no_fill_was_recorded",
            ["reconcile_exchange_ws_order_fill_path_before_any_probe_authorization"],
        )
    if audit_status == "ORDER_PRICE_METADATA_MISSING":
        return (
            "ORDER_PRICE_METADATA_REPAIR_REQUIRED",
            "order_rows_lack_effective_limit_price_metadata",
            ["repair_order_price_projection_before_bounded_probe_review"],
        )
    if audit_status == "NO_BBO_COVERAGE_FOR_ORDER_WINDOWS":
        return (
            "BBO_COVERAGE_REPAIR_REQUIRED",
            "order_windows_lack_BBO_coverage_for_touchability_review",
            ["repair_or_extend_orderbook_capture_before_bounded_probe_review"],
        )
    if audit_status in {
        "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH",
        "PASSIVE_LIMITS_NOT_TOUCHED",
    }:
        return (
            "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE",
            "current_Demo_order_flow_does_not_touch_BBO_enough_to_create_fill_backed_learning",
            [
                "revise_bounded_demo_probe_design_with_near_touch_or_skip_if_not_touchable_rules",
                "rerun_order_to_fill_touchability_audit_after_design_repair",
            ],
        )
    if audit_status == "NO_DEMO_ORDERS_TO_REVIEW":
        return (
            "ORDER_TOUCHABILITY_DATA_REQUIRED",
            "no_recent_Demo_orders_exist_to_establish_touchability_baseline",
            ["continue_demo_data_flow_monitor_until_order_rows_exist"],
        )
    if audit_status == "FILL_FLOW_PRESENT":
        return (
            "TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW",
            "fill_flow_exists_for_reviewed_Demo_orders",
            ["review_fill_quality_and_edge_capture_before_any_probe_authorization"],
        )
    return (
        "TOUCHABILITY_REVIEW_REQUIRED",
        "order_touchability_audit_has_mixed_or_unclassified_status",
        ["review_order_touchability_audit_before_bounded_probe_authorization"],
    )


def _placement_requirements(
    *,
    max_initial_passive_gap_bps: float,
    max_deep_no_touch_gap_bps: float,
    design: dict[str, Any],
    touchability: dict[str, Any],
) -> dict[str, Any]:
    return {
        "active": False,
        "requires_separate_operator_authorization": True,
        "environment": "demo_or_live_demo_only",
        "execution_path": "existing_rust_authority_path_only",
        "max_initial_passive_gap_bps": max_initial_passive_gap_bps,
        "max_deep_no_touch_gap_bps": max_deep_no_touch_gap_bps,
        "require_fresh_bbo_before_order": True,
        "post_only_allowed_only_if_gap_lte_max_initial_passive_gap_bps": True,
        "if_gap_exceeds_limit": "skip_probe_order_and_record_touchability_block",
        "require_order_to_fill_gap_audit_after_probe": True,
        "require_fill_fee_slippage_lineage_after_fill": True,
        "max_probe_intents_before_review": design.get("max_probe_intents_before_review"),
        "max_demo_notional_usdt_per_order": design.get("max_demo_notional_usdt_per_order"),
        "latest_runtime_max_best_touch_gap_bps": touchability.get("max_best_touch_gap_bps"),
        "latest_runtime_min_best_touch_gap_bps": touchability.get("min_best_touch_gap_bps"),
    }


def build_bounded_demo_probe_touchability_preflight(
    *,
    preflight: dict[str, Any] | None,
    order_to_fill_gap_audit: dict[str, Any] | None,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
    max_initial_passive_gap_bps: float = 75.0,
    max_deep_no_touch_gap_bps: float = 500.0,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")
    if max_initial_passive_gap_bps < 0 or max_initial_passive_gap_bps > 10_000:
        raise ValueError("max_initial_passive_gap_bps must be in [0, 10000]")
    if max_deep_no_touch_gap_bps < 0 or max_deep_no_touch_gap_bps > 10_000:
        raise ValueError("max_deep_no_touch_gap_bps must be in [0, 10000]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    max_age_seconds = max_artifact_age_hours * 3600
    preflight_artifact = _artifact_status(
        preflight,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    order_artifact = _artifact_status(
        order_to_fill_gap_audit,
        now_utc=now,
        max_age_seconds=max_age_seconds,
    )
    design = _design_summary(preflight)
    touchability = _order_touchability_summary(order_to_fill_gap_audit)
    status, reason, next_actions = _touchability_status(
        preflight_artifact_status=str(preflight_artifact.get("status")),
        order_artifact_status=str(order_artifact.get("status")),
        design=design,
        touchability=touchability,
    )
    placement_requirements = _placement_requirements(
        max_initial_passive_gap_bps=max_initial_passive_gap_bps,
        max_deep_no_touch_gap_bps=max_deep_no_touch_gap_bps,
        design=design,
        touchability=touchability,
    )
    return {
        "schema_version": TOUCHABILITY_PREFLIGHT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "candidate": {
            "side_cell_key": design.get("side_cell_key"),
            "strategy_name": design.get("strategy_name"),
            "symbol": design.get("symbol"),
            "side": design.get("side"),
            "outcome_horizon_minutes": design.get("outcome_horizon_minutes"),
        },
        "bounded_probe_design": design,
        "order_touchability": touchability,
        "placement_requirements": placement_requirements,
        "answers": {
            "bounded_probe_design_reviewable": design.get("reviewable") is True,
            "order_touchability_audit_fresh": order_artifact.get("status") == "FRESH",
            "current_order_flow_deep_no_touch": (
                touchability.get("status") == "PASSIVE_LIMITS_TOO_DEEP_NO_TOUCH"
            ),
            "touchability_repair_required": (
                status
                == "TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE"
            ),
            "ready_for_operator_touchability_review": (
                status == "TOUCHABILITY_GATE_READY_FOR_OPERATOR_REVIEW"
            ),
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "artifacts": {
            "sealed_horizon_probe_preflight": preflight_artifact,
            "demo_order_to_fill_gap_audit": order_artifact,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    touch = _dict(packet.get("order_touchability"))
    placement = _dict(packet.get("placement_requirements"))
    lines = [
        "# Bounded Demo Probe Touchability Preflight",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Order-touchability status: `{touch.get('status')}`",
        f"- Reviewed orders: `{touch.get('reviewed_orders')}`",
        f"- Deep passive no-touch orders: `{touch.get('deep_passive_no_touch_orders')}`",
        f"- Max observed best-touch gap bps: `{touch.get('max_best_touch_gap_bps')}`",
        f"- Required max initial passive gap bps: `{placement.get('max_initial_passive_gap_bps')}`",
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
    parser.add_argument("--preflight-json", type=Path)
    parser.add_argument("--order-to-fill-gap-json", type=Path)
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--max-initial-passive-gap-bps", type=float, default=75.0)
    parser.add_argument("--max-deep-no-touch-gap-bps", type=float, default=500.0)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_touchability_preflight(
        preflight=_read_json(args.preflight_json),
        order_to_fill_gap_audit=_read_json(args.order_to_fill_gap_json),
        max_artifact_age_hours=args.max_artifact_age_hours,
        max_initial_passive_gap_bps=args.max_initial_passive_gap_bps,
        max_deep_no_touch_gap_bps=args.max_deep_no_touch_gap_bps,
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

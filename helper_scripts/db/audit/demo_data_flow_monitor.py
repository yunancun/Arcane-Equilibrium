#!/usr/bin/env python3
"""Read-only rolling monitor for demo/live_demo data accumulation.

This wraps ``demo_order_stall_audit`` over multiple lookback windows so the
operator can tell whether demo is currently accumulating learning/order-flow
data, or whether a short empty window is only a recent gap on top of older
Cost Gate rejects / orders.

No PG writes, no Bybit calls, no orders, no risk/config/auth/runtime mutation.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from helper_scripts.db.audit import demo_order_stall_audit as order_stall  # noqa: E402
from helper_scripts.lib.pg_connect import connect_report_pg  # noqa: E402


SCHEMA_VERSION = "demo_data_flow_monitor_v1"
DEFAULT_WINDOWS = (1, 4, 24)
BOUNDARY = (
    "read-only PG SELECT via demo_order_stall_audit; no Bybit call, order, "
    "config, risk, auth, runtime, schema, or Cost Gate mutation"
)


def _as_int(value: Any) -> int:
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _classification(window: dict[str, Any]) -> dict[str, Any]:
    cls = window.get("classification")
    return cls if isinstance(cls, dict) else {}


def _counts(window: dict[str, Any]) -> dict[str, Any]:
    counts = window.get("counts")
    return counts if isinstance(counts, dict) else {}


def _answers(window: dict[str, Any]) -> dict[str, Any]:
    answers = _classification(window).get("answers")
    return answers if isinstance(answers, dict) else {}


def _observed_count(counts: dict[str, Any]) -> int:
    return sum(
        _as_int(counts.get(key))
        for key in (
            "decision_context_snapshots",
            "candidate_evaluations",
            "decision_features",
            "risk_verdicts",
            "intents",
            "orders",
            "fills",
        )
    )


def _candidate_or_reject_count(counts: dict[str, Any]) -> int:
    return sum(
        _as_int(counts.get(key))
        for key in (
            "candidate_evaluations",
            "decision_features",
            "rejected_decision_features",
            "risk_verdicts",
        )
    )


def _top_cost_gate_rejects(window: dict[str, Any]) -> int:
    total = 0
    for row in window.get("risk_reason_top") or []:
        reason = str(row.get("reason") or "").lower()
        if reason.startswith("cost_gate"):
            total += _as_int(row.get("rejected_n") or row.get("n"))
    return total


def summarize_windows(windows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(windows, key=lambda row: int(row.get("lookback_hours") or 0))
    if not ordered:
        return {
            "status": "NO_WINDOWS",
            "reason": "no lookback windows supplied",
            "next_action": "run_monitor_with_at_least_one_window",
            "answers": {},
        }

    short = ordered[0]
    broad = ordered[-1]
    short_counts = _counts(short)
    broad_counts = _counts(broad)
    short_observed = _observed_count(short_counts)
    broad_observed = _observed_count(broad_counts)
    broad_candidate_or_reject = _candidate_or_reject_count(broad_counts)
    broad_orders = _as_int(broad_counts.get("orders"))
    broad_fills = _as_int(broad_counts.get("fills"))
    broad_cost_gate_rejects = _top_cost_gate_rejects(broad)
    any_learning_stale = any(
        _answers(window).get("learning_data_flow_stale") is True
        for window in ordered
    )
    any_short_empty = short_observed == 0

    if broad_observed == 0:
        status = "NO_DEMO_DATA_ANY_WINDOW"
        reason = "no signal, candidate, risk, intent, order, or fill rows in the broadest window"
        next_action = "restore_demo_signal_pipeline_before_learning_review"
    elif any_short_empty and broad_orders > 0 and broad_fills == 0:
        status = "RECENT_WINDOW_EMPTY_PRIOR_ORDER_FLOW_NO_FILLS"
        reason = "short window is empty, but broader window has demo orders and no fills"
        next_action = "diagnose_order_to_fill_gap_and_keep_learning_monitor_running"
    elif any_short_empty and broad_cost_gate_rejects > 0:
        status = "RECENT_WINDOW_EMPTY_COST_GATE_REJECT_WALL"
        reason = "short window is empty, while broader window has Cost Gate rejected attempts"
        next_action = "restore_fresh_demo_flow_then_continue_cost_gate_learning_lane"
    elif any_short_empty and broad_candidate_or_reject > 0:
        status = "RECENT_WINDOW_EMPTY_PRIOR_CANDIDATE_OR_REJECT_DATA"
        reason = "short window is empty, while broader window has candidate/reject data"
        next_action = "watch_next_window_and_diagnose_freshness_if_gap_persists"
    elif broad_fills > 0:
        status = "DEMO_FILL_FLOW_PRESENT"
        reason = "broadest window has demo fills"
        next_action = "review_fill_outcomes_for_execution_realism"
    elif broad_orders > 0:
        status = "DEMO_ORDER_FLOW_PRESENT_NO_FILLS"
        reason = "broadest window has demo orders but no fills"
        next_action = "diagnose_order_to_fill_gap_before_cost_gate_changes"
    elif any_learning_stale:
        status = "DEMO_LEARNING_DATA_FLOW_STALE"
        reason = "learning/reject data exists but latest learning timestamp is stale"
        next_action = "restore_demo_data_flow_before_cost_gate_learning_activation"
    elif broad_cost_gate_rejects > 0:
        status = "COST_GATE_REJECT_WALL_NO_ORDER_FLOW"
        reason = "Cost Gate rejects are recorded, but orders/fills are absent"
        next_action = "activate_cost_gate_learning_lane_after_source_reconcile"
    elif broad_candidate_or_reject > 0:
        status = "CANDIDATE_OR_REJECT_DATA_ACCUMULATING"
        reason = "candidate or reject rows are accumulating"
        next_action = "continue_learning_evidence_collection"
    else:
        status = "PARTIAL_OBSERVATION_DATA_ONLY"
        reason = "observation data exists but no candidate/reject/order/fill flow is visible"
        next_action = "diagnose_signal_to_candidate_gate"

    return {
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "short_window_hours": short.get("lookback_hours"),
        "broad_window_hours": broad.get("lookback_hours"),
        "answers": {
            "short_window_empty": any_short_empty,
            "broad_window_has_any_data": broad_observed > 0,
            "broad_window_has_candidate_or_reject_data": broad_candidate_or_reject > 0,
            "cost_gate_rejects_recorded": broad_cost_gate_rejects > 0,
            "orders_present": broad_orders > 0,
            "fills_present": broad_fills > 0,
            "learning_data_flow_stale_any_window": any_learning_stale,
            "global_cost_gate_lowering_recommended": False,
            "bounded_demo_learning_lane_requires_runtime_activation": (
                broad_cost_gate_rejects > 0 and broad_fills == 0
            ),
        },
        "key_counts": {
            "short_window_observed_rows": short_observed,
            "broad_window_observed_rows": broad_observed,
            "broad_candidate_or_reject_rows": broad_candidate_or_reject,
            "broad_cost_gate_rejects": broad_cost_gate_rejects,
            "broad_orders": broad_orders,
            "broad_fills": broad_fills,
        },
    }


def compact_window(payload: dict[str, Any]) -> dict[str, Any]:
    counts = _counts(payload)
    cls = _classification(payload)
    freshness = cls.get("data_flow_freshness") or {}
    risk_category = cls.get("dominant_risk_category") or {}
    return {
        "lookback_hours": payload.get("lookback_hours"),
        "status": cls.get("status"),
        "data_accumulation_status": cls.get("data_accumulation_status"),
        "primary_blocker_stage": cls.get("primary_blocker_stage"),
        "dominant_risk_category": risk_category.get("category"),
        "dominant_risk_pct": risk_category.get("pct"),
        "data_flow_freshness_status": freshness.get("status"),
        "latest_learning_stage": freshness.get("latest_learning_stage"),
        "latest_learning_ts_utc": freshness.get("latest_learning_ts_utc"),
        "latest_learning_age_seconds": freshness.get("latest_learning_age_seconds"),
        "counts": {
            "decision_context_snapshots": _as_int(counts.get("decision_context_snapshots")),
            "candidate_evaluations": _as_int(counts.get("candidate_evaluations")),
            "decision_features": _as_int(counts.get("decision_features")),
            "rejected_decision_features": _as_int(counts.get("rejected_decision_features")),
            "risk_verdicts": _as_int(counts.get("risk_verdicts")),
            "approved_risk_verdicts": _as_int(counts.get("approved_risk_verdicts")),
            "rejected_risk_verdicts": _as_int(counts.get("rejected_risk_verdicts")),
            "intents": _as_int(counts.get("intents")),
            "orders": _as_int(counts.get("orders")),
            "fills": _as_int(counts.get("fills")),
        },
        "risk_reason_top": (payload.get("risk_reason_top") or [])[:5],
    }


def build_monitor_payload(
    *,
    engine_modes: tuple[str, ...],
    windows: list[dict[str, Any]],
    generated: str | None = None,
) -> dict[str, Any]:
    generated = generated or datetime.now(timezone.utc).isoformat(timespec="seconds")
    compact = [compact_window(window) for window in windows]
    summary = summarize_windows(compact)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": generated,
        "engine_modes": list(engine_modes),
        "summary": summary,
        "windows": compact,
        "boundary": BOUNDARY,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Demo Data Flow Monitor",
        "",
        f"- Generated: `{payload.get('generated_at_utc')}`",
        f"- Engine modes: `{','.join(payload.get('engine_modes') or [])}`",
        f"- Status: `{summary.get('status')}`",
        f"- Reason: {summary.get('reason')}",
        f"- Next action: `{summary.get('next_action')}`",
        "- Boundary: read-only PG SELECT; no Bybit/order/config/risk/auth/runtime mutation.",
        "",
        "## Window Summary",
        "",
        "| lookback_h | status | data | freshness | decisions | risk | intents | orders | fills | top risk |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---|",
    ]
    for window in payload.get("windows") or []:
        counts = window.get("counts") or {}
        top_reason = ""
        top_rows = window.get("risk_reason_top") or []
        if top_rows:
            top_reason = str(top_rows[0].get("reason") or "")[:80]
        lines.append(
            f"| {window.get('lookback_hours')} | {window.get('status')} | "
            f"{window.get('data_accumulation_status')} | "
            f"{window.get('data_flow_freshness_status')} | "
            f"{counts.get('decision_features')} | {counts.get('risk_verdicts')} | "
            f"{counts.get('intents')} | {counts.get('orders')} | "
            f"{counts.get('fills')} | {top_reason} |"
        )
    return "\n".join(lines) + "\n"


def parse_windows(values: list[int] | None) -> list[int]:
    raw = list(DEFAULT_WINDOWS) if values is None else values
    ordered = sorted(dict.fromkeys(raw))
    if not ordered:
        raise ValueError("at least one --window-hours value is required")
    for value in ordered:
        if value < 1 or value > 720:
            raise ValueError("--window-hours values must be in [1, 720]")
    return ordered


def fetch_window_payloads(
    conn: Any,
    *,
    engine_modes: tuple[str, ...],
    windows: list[int],
    top_limit: int,
    generated: str,
) -> list[dict[str, Any]]:
    payloads = []
    for hours in windows:
        cfg = order_stall.AuditConfig(
            engine_modes=engine_modes,
            lookback_hours=hours,
            top_limit=top_limit,
        )
        (
            counts,
            risk_reasons,
            eval_outcomes,
            lineage,
            context_payload_scope,
            pre_gate_drilldown,
        ) = order_stall.fetch_audit(conn, cfg)
        payloads.append(
            order_stall.build_json_payload(
                cfg,
                counts,
                risk_reasons,
                eval_outcomes,
                lineage,
                pre_gate_drilldown,
                context_payload_scope,
                generated=generated,
            )
        )
    return payloads


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--window-hours", type=int, action="append", dest="windows")
    parser.add_argument("--top-limit", type=int, default=10)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    engine_modes = tuple(args.engine_modes or ["demo", "live_demo"])
    windows = parse_windows(args.windows)
    generated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    conn = connect_report_pg(
        "demo_data_flow_monitor",
        statement_timeout_ms_default=180_000,
    )
    try:
        conn.rollback()
        conn.set_session(readonly=True, autocommit=True)
        window_payloads = fetch_window_payloads(
            conn,
            engine_modes=engine_modes,
            windows=windows,
            top_limit=args.top_limit,
            generated=generated,
        )
    finally:
        conn.close()

    payload = build_monitor_payload(
        engine_modes=engine_modes,
        windows=window_payloads,
        generated=generated,
    )
    markdown = render_markdown(payload)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    else:
        print(markdown, end="")
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=order_stall._json_default)
            + "\n",
            encoding="utf-8",
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

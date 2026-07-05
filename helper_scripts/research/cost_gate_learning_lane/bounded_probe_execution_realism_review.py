#!/usr/bin/env python3
"""Diagnose bounded demo-probe edge-capture execution gaps.

This artifact is the step after `bounded_probe_result_review.py` reports that
a positive bounded demo probe under-captured its matched blocked-signal
controls. It only reads the result-review artifact plus the JSONL learning
ledger. It does not query PG, call Bybit, submit orders, lower the Cost Gate,
grant probe/order authority, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.contract import (
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)
from cost_gate_learning_lane.proof_exclusion import proof_exclusion_reasons
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_execution_realism_review_v1"
)
BOUNDARY = (
    "artifact-only bounded demo-probe execution-realism review; no PG "
    "query/write, Bybit call, order, config, risk, auth, runtime mutation, "
    "Cost Gate lowering, probe authority, order authority, or promotion proof"
)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    parsed = _float(value)
    return round(parsed, ndigits) if parsed is not None else None


def _avg(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _generated_sort_key(row: dict[str, Any]) -> tuple[str, str]:
    return (_str(row.get("generated_at_utc")), _str(row.get("attempt_id")))


def _latest_unique_by_attempt(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in sorted(rows, key=_generated_sort_key):
        attempt_id = _str(row.get("attempt_id"))
        if not attempt_id:
            continue
        latest[attempt_id] = row
    return [latest[key] for key in sorted(latest)]


def _horizon_matches(row: dict[str, Any], horizon_minutes: Any) -> bool:
    expected = _int(horizon_minutes)
    observed = _int(row.get("horizon_minutes"))
    return expected <= 0 or observed <= 0 or observed == expected


def _is_fill_backed(row: dict[str, Any]) -> bool:
    source = _str(row.get("outcome_source")).lower()
    if "proxy" in source:
        return False
    if "fill" in source:
        return True
    for key in ("fill_id", "exec_id", "execution_id", "order_id"):
        if _str(row.get(key)):
            return True
    return False


def _entry_delay_ms(row: dict[str, Any]) -> float | None:
    event_ts = _int(row.get("event_ts_ms"))
    entry_ts = _int(row.get("entry_ts_ms"))
    if event_ts <= 0 or entry_ts <= 0 or entry_ts < event_ts:
        return None
    return float(entry_ts - event_ts)


def _matching_rows(
    ledger_rows: list[dict[str, Any]],
    *,
    side_cell_key: str,
    horizon_minutes: Any,
    record_type: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in ledger_rows:
        if _str(row.get("side_cell_key")) != side_cell_key:
            continue
        if _str(row.get("record_type")) != record_type:
            continue
        if not _horizon_matches(row, horizon_minutes):
            continue
        if _float(row.get("realized_net_bps")) is None:
            continue
        if proof_exclusion_reasons(row):
            continue
        rows.append(row)
    return _latest_unique_by_attempt(rows)


def _execution_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    nets = [
        value for value in (_float(row.get("realized_net_bps")) for row in rows)
        if value is not None
    ]
    gross = [
        value for value in (_float(row.get("gross_bps")) for row in rows)
        if value is not None
    ]
    costs = [
        value for value in (_float(row.get("cost_bps")) for row in rows)
        if value is not None
    ]
    delays = [
        value for value in (_entry_delay_ms(row) for row in rows)
        if value is not None
    ]
    fill_backed_count = sum(1 for row in rows if _is_fill_backed(row))
    proxy_count = len(rows) - fill_backed_count
    return {
        "count": len(rows),
        "avg_net_bps": _round(_avg(nets)),
        "avg_gross_bps": _round(_avg(gross)),
        "avg_cost_bps": _round(_avg(costs)),
        "avg_entry_delay_ms": _round(_avg(delays), ndigits=1),
        "fill_backed_outcome_count": fill_backed_count,
        "proxy_outcome_count": proxy_count,
        "fill_backed_pct": _round(100.0 * fill_backed_count / len(rows))
        if rows
        else None,
    }


def _authority_preserved(result_review: dict[str, Any]) -> bool:
    answers = _dict(result_review.get("answers"))
    for source in (result_review, answers):
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


def _gap_decomposition(
    *,
    probe_summary: dict[str, Any],
    control_summary: dict[str, Any],
) -> dict[str, Any]:
    probe_net = _float(probe_summary.get("avg_net_bps"))
    control_net = _float(control_summary.get("avg_net_bps"))
    probe_gross = _float(probe_summary.get("avg_gross_bps"))
    control_gross = _float(control_summary.get("avg_gross_bps"))
    probe_cost = _float(probe_summary.get("avg_cost_bps"))
    control_cost = _float(control_summary.get("avg_cost_bps"))
    probe_delay = _float(probe_summary.get("avg_entry_delay_ms"))
    control_delay = _float(control_summary.get("avg_entry_delay_ms"))
    net_gap = (
        control_net - probe_net
        if probe_net is not None and control_net is not None
        else None
    )
    gross_gap = (
        control_gross - probe_gross
        if probe_gross is not None and control_gross is not None
        else None
    )
    cost_gap = (
        probe_cost - control_cost
        if probe_cost is not None and control_cost is not None
        else None
    )
    delay_gap = (
        probe_delay - control_delay
        if probe_delay is not None and control_delay is not None
        else None
    )
    return {
        "net_capture_gap_bps": _round(net_gap),
        "gross_capture_gap_bps": _round(gross_gap),
        "cost_or_slippage_gap_bps": _round(cost_gap),
        "entry_delay_gap_ms": _round(delay_gap, ndigits=1),
    }


def _hypotheses(
    *,
    probe_summary: dict[str, Any],
    control_summary: dict[str, Any],
    gap: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    net_gap = _float(gap.get("net_capture_gap_bps")) or 0.0
    gross_gap = _float(gap.get("gross_capture_gap_bps")) or 0.0
    cost_gap = _float(gap.get("cost_or_slippage_gap_bps")) or 0.0
    delay_gap = _float(gap.get("entry_delay_gap_ms")) or 0.0
    if _int(probe_summary.get("fill_backed_outcome_count")) < _int(
        probe_summary.get("count")
    ):
        out.append({
            "kind": "fill_backed_execution_missing",
            "severity": "HIGH",
            "probe_fill_backed_pct": probe_summary.get("fill_backed_pct"),
            "next_action": "record_fill_backed_probe_execution_rows_or_l1_replay_before_cost_gate_review",
        })
    if gross_gap > 0.0:
        out.append({
            "kind": "horizon_or_signal_timing_gross_edge_gap",
            "severity": "HIGH" if gross_gap >= max(0.5, 0.5 * net_gap) else "MEDIUM",
            "gap_bps": _round(gross_gap),
            "next_action": "test_horizon_retiming_or_signal_timing_against_matched_controls",
        })
    if cost_gap > 0.0:
        out.append({
            "kind": "fee_slippage_or_fill_cost_gap",
            "severity": "HIGH" if cost_gap >= max(0.5, 0.5 * net_gap) else "MEDIUM",
            "gap_bps": _round(cost_gap),
            "next_action": "inspect_probe_fee_slippage_and_fill_quality_against_controls",
        })
    if delay_gap > 60_000.0:
        out.append({
            "kind": "entry_timing_delay_gap",
            "severity": "MEDIUM",
            "gap_ms": _round(delay_gap, ndigits=1),
            "next_action": "inspect_entry_delay_and_queue_timing_before_next_probe_budget",
        })
    if _int(control_summary.get("fill_backed_outcome_count")) < _int(
        control_summary.get("count")
    ):
        out.append({
            "kind": "matched_control_fill_backed_execution_missing",
            "severity": "MEDIUM",
            "control_fill_backed_pct": control_summary.get("fill_backed_pct"),
            "next_action": "record_or_replay_matched_control_execution_realism_before_gate_change",
        })
    if not out:
        out.append({
            "kind": "unexplained_edge_capture_gap",
            "severity": "HIGH",
            "next_action": "inspect_raw_probe_and_control_rows_before_cost_gate_review",
        })
    return out


def _first_next_action(hypotheses: list[dict[str, Any]]) -> str:
    for row in hypotheses:
        action = _str(row.get("next_action"))
        if action:
            return action
    return "inspect_bounded_probe_execution_realism_gap_before_cost_gate_review"


def build_bounded_probe_execution_realism_review(
    *,
    result_review: dict[str, Any],
    ledger_rows: list[dict[str, Any]],
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    """Build a no-authority execution-realism diagnosis for a result review."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    quality = _dict(result_review.get("evidence_quality"))
    candidate = _dict(result_review.get("candidate"))
    summary = _dict(result_review.get("probe_result_summary"))
    side_cell_key = _str(result_review.get("side_cell_key"))
    horizon_minutes = candidate.get("outcome_horizon_minutes")
    quality_status = _str(quality.get("status"))
    authority_ok = _authority_preserved(result_review)

    probe_rows = _matching_rows(
        ledger_rows,
        side_cell_key=side_cell_key,
        horizon_minutes=horizon_minutes,
        record_type=PROBE_OUTCOME_RECORD_TYPE,
    )
    control_rows = _matching_rows(
        ledger_rows,
        side_cell_key=side_cell_key,
        horizon_minutes=horizon_minutes,
        record_type=BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    )
    probe_summary = _execution_summary(probe_rows)
    control_summary = _execution_summary(control_rows)
    gap = _gap_decomposition(
        probe_summary=probe_summary,
        control_summary=control_summary,
    )

    review_floor = max(1, _int(summary.get("first_review_outcome_floor"), 3))
    if not authority_ok or _str(result_review.get("status")) == "AUTHORITY_BOUNDARY_VIOLATION":
        status = "AUTHORITY_BOUNDARY_VIOLATION"
        reason = "authority_boundary_violation_prevents_execution_realism_review"
        hypotheses: list[dict[str, Any]] = []
        next_actions = ["remove_authority_granting_input_before_any_review"]
    elif quality_status != "PROBE_UNDERPERFORMS_MATCHED_CONTROL_EXECUTION_GAP":
        status = "NO_EXECUTION_REALISM_GAP_TO_REVIEW"
        reason = "bounded_probe_result_review_does_not_report_execution_realism_gap"
        hypotheses = []
        next_actions = ["continue_standard_bounded_probe_result_review_path"]
    elif _int(probe_summary.get("count")) < review_floor:
        status = "EXECUTION_REALISM_PROBE_SAMPLE_BELOW_REVIEW_FLOOR"
        reason = "probe_outcome_rows_below_execution_realism_review_floor"
        hypotheses = []
        next_actions = ["continue_recording_probe_outcomes_before_execution_realism_review"]
    elif _int(control_summary.get("count")) < review_floor:
        status = "EXECUTION_REALISM_CONTROL_SAMPLE_BELOW_REVIEW_FLOOR"
        reason = "matched_control_rows_below_execution_realism_review_floor"
        hypotheses = []
        next_actions = ["continue_recording_matched_control_outcomes_before_execution_realism_review"]
    else:
        hypotheses = _hypotheses(
            probe_summary=probe_summary,
            control_summary=control_summary,
            gap=gap,
        )
        status = "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
        reason = "probe_under_captures_matched_control_edge_and_requires_execution_repair"
        next_actions = [_first_next_action(hypotheses)]

    return {
        "schema_version": BOUNDED_PROBE_EXECUTION_REALISM_REVIEW_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "side_cell_key": side_cell_key,
        "candidate": {
            "strategy_name": candidate.get("strategy_name"),
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "outcome_horizon_minutes": horizon_minutes,
        },
        "source_result_review": {
            "schema_version": result_review.get("schema_version"),
            "status": result_review.get("status"),
            "evidence_quality_status": quality_status,
            "generated_at_utc": result_review.get("generated_at_utc"),
            "probe_edge_capture_ratio": quality.get("probe_edge_capture_ratio"),
            "probe_execution_gap_bps": quality.get("probe_execution_gap_bps"),
            "probe_minus_control_avg_net_bps": quality.get(
                "probe_minus_control_avg_net_bps"
            ),
        },
        "probe_execution_summary": probe_summary,
        "matched_control_execution_summary": control_summary,
        "gap_decomposition": gap,
        "execution_gap_hypotheses": hypotheses,
        "answers": {
            "authority_boundary_preserved": authority_ok,
            "execution_realism_gap_confirmed": (
                status == "EXECUTION_REALISM_GAP_DIAGNOSED_REPAIR_REQUIRED"
            ),
            "fill_backed_probe_execution_available": (
                _int(probe_summary.get("fill_backed_outcome_count"))
                >= _int(probe_summary.get("count"))
                and _int(probe_summary.get("count")) > 0
            ),
            "cost_gate_or_operator_review_allowed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "next_actions": list(dict.fromkeys(next_actions)),
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    gap = _dict(packet.get("gap_decomposition"))
    probe = _dict(packet.get("probe_execution_summary"))
    control = _dict(packet.get("matched_control_execution_summary"))
    lines = [
        "# Bounded Probe Execution Realism Review",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Side-cell: `{packet.get('side_cell_key')}`",
        f"- Probe avg net bps: `{probe.get('avg_net_bps')}`",
        f"- Control avg net bps: `{control.get('avg_net_bps')}`",
        f"- Net capture gap bps: `{gap.get('net_capture_gap_bps')}`",
        f"- Gross capture gap bps: `{gap.get('gross_capture_gap_bps')}`",
        f"- Cost/slippage gap bps: `{gap.get('cost_or_slippage_gap_bps')}`",
        f"- Probe fill-backed pct: `{probe.get('fill_backed_pct')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Hypotheses",
        "",
    ]
    for row in _list(packet.get("execution_gap_hypotheses")):
        if not isinstance(row, dict):
            continue
        lines.append(
            f"- `{row.get('kind')}` severity=`{row.get('severity')}` "
            f"next=`{row.get('next_action')}`"
        )
    lines.extend(["", "## Next Actions", ""])
    for action in _list(packet.get("next_actions")):
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-review-json", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_probe_execution_realism_review(
        result_review=_read_json(args.result_review_json),
        ledger_rows=read_jsonl_ledger(args.ledger),
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

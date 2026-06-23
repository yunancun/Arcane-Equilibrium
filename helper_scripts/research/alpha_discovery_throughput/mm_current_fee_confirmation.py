#!/usr/bin/env python3
"""Build an MM current-fee confirmation packet.

This artifact separates three different claims that used to blur together:
latest current-fee-positive maker cell, repeated independent-window evidence,
and OOS / maker execution realism. It is artifact-only: no PG query/write,
Bybit call, order placement, config / risk / auth / runtime mutation, Cost Gate
lowering, probe authority, or promotion authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mm_current_fee_confirmation_packet_v1"
BOUNDARY = (
    "artifact-only MM current-fee confirmation packet; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, probe authority, or promotion authority"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


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
    out = _float(value)
    return round(out, ndigits) if out is not None else None


def _cell_key(source: str, cell: dict[str, Any]) -> str:
    source = _str(source or cell.get("source") or "fillsim")
    if cell.get("key"):
        return _str(cell.get("key"))
    if cell.get("candidate_key"):
        return _str(cell.get("candidate_key"))
    if cell.get("motif_key"):
        return _str(cell.get("motif_key"))
    name = _str(cell.get("name") or cell.get("condition") or cell.get("feature"))
    if name:
        return "|".join([source, name])
    return "|".join([
        source,
        _str(cell.get("scope") or "global"),
        _str(cell.get("symbol") or "pooled"),
        _str(cell.get("queue_position")),
        _str(cell.get("policy")),
        _str(cell.get("track")),
    ])


def _cell_rank(cell: dict[str, Any]) -> tuple[float, float, int]:
    edge = _float(cell.get("edge_before_fees_bps"))
    net = _float(cell.get("net_bps") or cell.get("net_bps_at_fee"))
    fills = _int(cell.get("n_fill_only") or cell.get("n"))
    return (
        net if net is not None else -1e9,
        edge if edge is not None else -1e9,
        fills,
    )


def _append_positive_cell(
    cells: list[dict[str, Any]],
    raw: dict[str, Any],
    *,
    source: str,
    net_key: str = "net_bps",
    current_fee_round_trip_bps: float | None = None,
) -> None:
    if not isinstance(raw, dict):
        return
    cell = dict(raw)
    net = _float(cell.get(net_key))
    edge = _float(cell.get("edge_before_fees_bps"))
    if net is None and current_fee_round_trip_bps is not None and edge is not None:
        net = edge - current_fee_round_trip_bps
    if net is None or net <= 0.0:
        return
    cell.setdefault("source", source)
    cell["net_bps"] = _round(net)
    cell.setdefault("key", _cell_key(source, cell))
    cells.append(cell)


def _current_fee_round_trip(
    fillsim: dict[str, Any] | None,
    gross_edge_cost_decomposition: dict[str, Any] | None,
) -> float | None:
    gross = _dict(gross_edge_cost_decomposition)
    fee = _dict(_dict(fillsim).get("maker_fee_sensitivity_scorecard"))
    return (
        _float(gross.get("current_fee_round_trip_bps"))
        or _float(fee.get("current_fee_round_trip_bps"))
        or (
            2.0 * _float(fee.get("current_maker_fee_bps_per_side"))
            if _float(fee.get("current_maker_fee_bps_per_side")) is not None
            else None
        )
    )


def _current_fee_positive_cells(
    fillsim: dict[str, Any] | None,
    gross_edge_cost_decomposition: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    payload = _dict(fillsim)
    gross = _dict(gross_edge_cost_decomposition)
    current_fee = _current_fee_round_trip(payload, gross)
    cells: list[dict[str, Any]] = []

    _append_positive_cell(
        cells,
        _dict(gross.get("best_sample_gated_current_fee_cell")),
        source=_str(_dict(gross.get("best_sample_gated_current_fee_cell")).get("source"))
        or "gross_edge_cost_decomposition",
        current_fee_round_trip_bps=current_fee,
    )
    _append_positive_cell(
        cells,
        _dict(gross.get("best_sample_gated_gross_cell")),
        source=_str(_dict(gross.get("best_sample_gated_gross_cell")).get("source"))
        or "gross_edge_cost_decomposition",
        current_fee_round_trip_bps=current_fee,
    )

    for source, field in (
        ("edge_scorecard", "positive_fill_only_cells_with_sample_gate"),
        ("conditional_feature_scorecard", "positive_cells_with_sample_gate"),
    ):
        for raw in _list(_dict(payload.get(source)).get(field)):
            _append_positive_cell(
                cells,
                raw,
                source=source,
                current_fee_round_trip_bps=current_fee,
            )

    fee = _dict(payload.get("maker_fee_sensitivity_scorecard"))
    current_maker_fee = _float(fee.get("current_maker_fee_bps_per_side"))
    best_break_even = _dict(fee.get("best_sample_gated_break_even_cell"))
    _append_positive_cell(
        cells,
        best_break_even,
        source=_str(best_break_even.get("source")) or "maker_fee_sensitivity_current_fee",
        current_fee_round_trip_bps=current_fee,
    )
    for scenario in _list(fee.get("scenarios")):
        if not isinstance(scenario, dict):
            continue
        scenario_fee = _float(scenario.get("maker_fee_bps_per_side"))
        if (
            current_maker_fee is not None
            and scenario_fee is not None
            and abs(scenario_fee - current_maker_fee) > 1e-9
        ):
            continue
        for raw in _list(scenario.get("positive_sample_gate_cells")):
            _append_positive_cell(
                cells,
                raw,
                source=_str(_dict(raw).get("source"))
                or "maker_fee_sensitivity_current_fee",
                net_key="net_bps_at_fee",
                current_fee_round_trip_bps=current_fee,
            )

    merged: dict[str, dict[str, Any]] = {}
    for cell in cells:
        key = _cell_key(_str(cell.get("source")) or "fillsim", cell)
        cell["key"] = key
        previous = merged.get(key)
        if previous is None or _cell_rank(cell) > _cell_rank(previous):
            merged[key] = cell
    out = list(merged.values())
    out.sort(key=_cell_rank, reverse=True)
    return out


def _history_positive_cells(fillsim_history: dict[str, Any] | None) -> list[dict[str, Any]]:
    history = _dict(fillsim_history)
    cells: list[dict[str, Any]] = []
    for row in _list(history.get("repeated_positive_keys")):
        if not isinstance(row, dict):
            continue
        cell = _dict(row.get("best_cell"))
        if not cell:
            continue
        cell = dict(cell)
        cell.setdefault("source", _str(cell.get("source")) or "history_repeated_positive")
        cell.setdefault("key", _str(row.get("key")) or _cell_key(cell["source"], cell))
        cell["history_repeat_windows"] = row.get("windows")
        cell["history_distinct_window_dates"] = row.get("distinct_window_dates")
        cells.append(cell)
    best_window = _dict(history.get("best_sample_gated_break_even_window"))
    best_cell = _dict(best_window.get("cell") or best_window.get("best_cell"))
    if best_cell and (_float(best_cell.get("net_bps")) or 0.0) > 0.0:
        cell = dict(best_cell)
        cell.setdefault("source", _str(cell.get("source")) or "history_best_current_fee")
        cell.setdefault("key", _cell_key(cell["source"], cell))
        cells.append(cell)
    return cells


def _matching_repeated_key(
    fillsim_history: dict[str, Any] | None,
    candidate_key: str,
) -> dict[str, Any]:
    if not candidate_key:
        return {}
    for row in _list(_dict(fillsim_history).get("repeated_positive_keys")):
        if isinstance(row, dict) and _str(row.get("key")) == candidate_key:
            return row
    return {}


def _maker_execution_realism_confirmed(payload: dict[str, Any] | None) -> bool:
    review = _dict(payload)
    answers = _dict(review.get("answers"))
    status = _str(review.get("status")).upper()
    if answers.get("maker_execution_realism_confirmed") is True:
        return True
    if answers.get("execution_realism_confirmed") is True:
        return True
    return status in {
        "MAKER_EXECUTION_REALISM_PASS",
        "MM_MAKER_EXECUTION_REALISM_PASS",
        "EXECUTION_REALISM_PASS",
    }


def _maker_execution_realism_status(
    *,
    repeated: bool,
    oos_confirmed: bool,
    maker_execution_realism: dict[str, Any] | None,
) -> str:
    if _maker_execution_realism_confirmed(maker_execution_realism):
        return "CONFIRMED"
    if not repeated:
        return "NOT_REACHED_REPEAT_WINDOW_REQUIRED"
    if not oos_confirmed:
        return "NOT_REACHED_OOS_REQUIRED"
    if maker_execution_realism:
        return _str(maker_execution_realism.get("status")) or "REVIEW_PRESENT_NOT_CONFIRMED"
    return "MISSING_MAKER_EXECUTION_REALISM_REVIEW"


def build_mm_current_fee_confirmation_packet(
    *,
    fillsim: dict[str, Any] | None = None,
    fillsim_history: dict[str, Any] | None = None,
    gross_edge_cost_decomposition: dict[str, Any] | None = None,
    maker_execution_realism: dict[str, Any] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    history = _dict(fillsim_history)
    cells = _current_fee_positive_cells(fillsim, gross_edge_cost_decomposition)
    cells.extend(_history_positive_cells(fillsim_history))
    cells = [cell for cell in cells if (_float(cell.get("net_bps")) or 0.0) > 0.0]
    cells.sort(key=_cell_rank, reverse=True)
    candidate = cells[0] if cells else {}
    candidate_key = _str(candidate.get("key"))
    repeated = _matching_repeated_key(history, candidate_key)
    repeated_key_count = len(_list(history.get("repeated_positive_keys")))
    candidate_repeat_windows = _int(
        repeated.get("windows") or candidate.get("history_repeat_windows")
    )
    current_fee_positive_windows = _int(
        history.get("current_fee_sample_gated_positive_windows")
    )
    walk_forward_holdout_windows = _int(
        history.get("walk_forward_holdout_confirmed_windows")
    )
    repeat_confirmed = bool(candidate_key and candidate_repeat_windows > 1)
    history_status = _str(history.get("status")).upper()
    oos_confirmed = bool(
        repeat_confirmed
        and (
            history_status == "HISTORY_REPEAT_HOLDOUT_OR_CURRENT_FEE_POSITIVE"
            or walk_forward_holdout_windows > 0
        )
    )
    maker_status = _maker_execution_realism_status(
        repeated=repeat_confirmed,
        oos_confirmed=oos_confirmed,
        maker_execution_realism=maker_execution_realism,
    )
    maker_confirmed = maker_status == "CONFIRMED"

    if not candidate:
        status = "NO_CURRENT_FEE_POSITIVE_MM_CELL"
        reason = "no_current_fee_positive_sample_gated_mm_cell"
        next_action = "continue_mm_signal_search_for_current_fee_positive_cell"
        next_gate = "current_fee_positive_sample_gated_mm_cell"
    elif not repeat_confirmed:
        status = "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW"
        reason = "candidate_not_repeated_across_independent_history_windows"
        next_action = "accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell"
        next_gate = "same_current_fee_positive_cell_repeats_across_independent_windows"
    elif not oos_confirmed:
        status = "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_OOS"
        reason = "repeated_current_fee_cell_lacks_walk_forward_holdout_confirmation"
        next_action = "build_oos_walk_forward_confirmation_for_repeated_current_fee_mm_cell"
        next_gate = "walk_forward_oos_confirmation_without_train_only_leakage"
    elif not maker_confirmed:
        status = "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_MAKER_EXECUTION_REALISM"
        reason = "repeated_oos_current_fee_cell_lacks_maker_execution_realism"
        next_action = "measure_maker_fill_probability_adverse_selection_fee_and_inventory_risk"
        next_gate = "maker_execution_realism_confirms_capture_after_cost"
    else:
        status = "MM_CURRENT_FEE_CONFIRMATION_READY_FOR_OPERATOR_REVIEW"
        reason = "repeat_oos_and_maker_execution_realism_confirmed"
        next_action = "operator_review_mm_current_fee_confirmation_without_runtime_authority"
        next_gate = "operator_review_before_any_probe_or_order_authority"

    current_fee_round_trip = _current_fee_round_trip(
        fillsim,
        gross_edge_cost_decomposition,
    )
    summary = {
        "candidate_key": candidate_key or None,
        "candidate_source": candidate.get("source"),
        "candidate_symbol": candidate.get("symbol"),
        "candidate_policy": candidate.get("policy"),
        "candidate_queue_position": candidate.get("queue_position"),
        "candidate_track": candidate.get("track"),
        "candidate_n_fill_only": candidate.get("n_fill_only") or candidate.get("n"),
        "candidate_edge_before_fees_bps": _round(candidate.get("edge_before_fees_bps")),
        "candidate_net_bps": _round(candidate.get("net_bps") or candidate.get("net_bps_at_fee")),
        "candidate_break_even_maker_fee_bps_per_side": _round(
            candidate.get("break_even_maker_fee_bps_per_side")
        ),
        "current_fee_round_trip_bps": _round(current_fee_round_trip),
        "current_fee_positive_candidate_count": len(cells),
        "history_status": history.get("status"),
        "history_reason": history.get("reason"),
        "history_valid_windows": history.get("valid_windows"),
        "history_distinct_window_dates": history.get("distinct_window_dates"),
        "history_current_fee_sample_gated_positive_windows": current_fee_positive_windows,
        "history_repeated_positive_key_count": repeated_key_count,
        "history_walk_forward_holdout_confirmed_windows": walk_forward_holdout_windows,
        "candidate_repeated_windows": candidate_repeat_windows,
        "candidate_repeated_window_sources": repeated.get("window_sources"),
        "candidate_distinct_window_dates": (
            repeated.get("distinct_window_dates")
            or candidate.get("history_distinct_window_dates")
        ),
        "repeat_window_confirmed": repeat_confirmed,
        "oos_walk_forward_confirmed": oos_confirmed,
        "maker_execution_realism_status": maker_status,
        "maker_execution_realism_confirmed": maker_confirmed,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "next_gate": next_gate,
        "summary": summary,
        "candidate": candidate or None,
        "top_current_fee_positive_cells": cells[:10],
        "answers": {
            "current_fee_positive_candidate_present": bool(candidate),
            "repeat_window_confirmed": repeat_confirmed,
            "oos_walk_forward_confirmed": oos_confirmed,
            "maker_execution_realism_confirmed": maker_confirmed,
            "ready_for_operator_review": status == "MM_CURRENT_FEE_CONFIRMATION_READY_FOR_OPERATOR_REVIEW",
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
        "global_boundaries": {
            "order_authority": "NOT_GRANTED",
            "probe_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation": "NONE",
            "promotion_evidence": False,
            "boundary": BOUNDARY,
        },
    }


def render_markdown(packet: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|")

    lines = [
        "# MM Current-Fee Confirmation Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Next action: `{packet.get('next_action')}`",
        "- Boundary: artifact-only; no order authority, no probe authority, no Cost Gate lowering.",
        "",
        "## Summary",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for key, value in _dict(packet.get("summary")).items():
        lines.append(f"| {key} | `{cell(value)}` |")
    lines.extend([
        "",
        "## Top Cells",
        "",
        "| rank | key | source | symbol | net_bps | edge_bps | fills |",
        "|---:|---|---|---|---:|---:|---:|",
    ])
    for idx, row in enumerate(_list(packet.get("top_current_fee_positive_cells")), start=1):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{idx} | {cell(row.get('key'))} | {cell(row.get('source'))} | "
            f"{cell(row.get('symbol'))} | {row.get('net_bps')} | "
            f"{row.get('edge_before_fees_bps')} | "
            f"{row.get('n_fill_only') or row.get('n')} |"
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


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
    parser.add_argument("--fillsim-json", type=Path)
    parser.add_argument("--fillsim-history-json", type=Path)
    parser.add_argument("--gross-edge-cost-decomposition-json", type=Path)
    parser.add_argument("--maker-execution-realism-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_read_json(args.fillsim_json),
        fillsim_history=_read_json(args.fillsim_history_json),
        gross_edge_cost_decomposition=_read_json(args.gross_edge_cost_decomposition_json),
        maker_execution_realism=_read_json(args.maker_execution_realism_json),
    )
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not (args.output or args.json_output or args.print_json):
        print(render_markdown(packet), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

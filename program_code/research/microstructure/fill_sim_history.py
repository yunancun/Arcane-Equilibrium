#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Aggregate multiple fill_sim JSON reports into a longer-regime scorecard.

The single-window fill_sim report is an early structural read, not a CP-3
verdict. This reducer keeps that boundary intact while making the missing
question machine-readable: do current-fee or lower-fee maker cells repeat across
independent report windows, and are any walk-forward holdout cells recurring?

It is intentionally report-only: no DB connection, no exchange call, and no
strategy/runtime mutation.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .fill_sim import MAKER_FEE_BPS, MIN_FILLS_FOR_SIGNIF, _r

DEFAULT_HISTORY_GLOB = "/tmp/openclaw/research/fillsim/history/*.json"


def _as_float(value):
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    if out != out:
        return None
    return out


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _parse_ts(value):
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _window_date(rep: dict) -> str | None:
    data = rep.get("data") or {}
    for key in ("l1_min_ts", "l1_max_ts"):
        ts = _parse_ts(data.get(key))
        if ts is not None:
            return ts.date().isoformat()
    ts = _parse_ts(rep.get("generated_at"))
    return ts.date().isoformat() if ts is not None else None


def _cell_key(source: str, cell: dict) -> str:
    name = cell.get("name") or cell.get("condition")
    if name:
        return f"{source}|{name}"
    scope = cell.get("scope") or ""
    symbol = cell.get("symbol") or "pooled"
    queue = cell.get("queue_position") or ""
    policy = cell.get("policy") or ""
    track = cell.get("track") or ""
    return f"{source}|{scope}|{symbol}|{queue}|{policy}|{track}"


def _normalize_positive_cell(source: str, cell: dict, *, net_key: str = "net_bps") -> dict | None:
    net = _as_float(cell.get(net_key))
    if net is None or net <= 0.0:
        return None
    n = _as_int(cell.get("n_fill_only", cell.get("n")), 0)
    signif_suppressed = bool(cell.get("signif_suppressed", n < MIN_FILLS_FOR_SIGNIF))
    if n < MIN_FILLS_FOR_SIGNIF or signif_suppressed:
        return None
    out = {
        "source": source,
        "key": _cell_key(source, cell),
        "name": cell.get("name"),
        "condition": cell.get("condition"),
        "symbol": cell.get("symbol"),
        "scope": cell.get("scope"),
        "queue_position": cell.get("queue_position"),
        "policy": cell.get("policy"),
        "track": cell.get("track"),
        "n_fill_only": n,
        "net_bps": _r(net, 3),
        "edge_before_fees_bps": _r(cell.get("edge_before_fees_bps"), 3),
        "break_even_maker_fee_bps_per_side": _r(
            cell.get("break_even_maker_fee_bps_per_side"),
            3,
        ),
    }
    return out


def _normalize_break_even_cell(source: str, cell: dict) -> dict | None:
    """Normalize a sample-gated lower-fee break-even cell for history grouping."""
    be = _as_float(cell.get("break_even_maker_fee_bps_per_side"))
    if be is None or be <= 0.0 or be >= MAKER_FEE_BPS:
        return None
    n = _as_int(cell.get("n_fill_only", cell.get("n")), 0)
    signif_suppressed = bool(cell.get("signif_suppressed", n < MIN_FILLS_FOR_SIGNIF))
    if n < MIN_FILLS_FOR_SIGNIF or signif_suppressed:
        return None
    origin = str(cell.get("source") or source)
    out = {
        "source": origin,
        "key": _cell_key(origin, cell),
        "name": cell.get("name"),
        "condition": cell.get("condition"),
        "symbol": cell.get("symbol"),
        "scope": cell.get("scope"),
        "queue_position": cell.get("queue_position"),
        "policy": cell.get("policy"),
        "track": cell.get("track"),
        "n_fill_only": n,
        "edge_before_fees_bps": _r(cell.get("edge_before_fees_bps"), 3),
        "break_even_maker_fee_bps_per_side": _r(be, 3),
        "fee_reduction_to_breakeven_bps_per_side": _r(MAKER_FEE_BPS - be, 3),
    }
    if "maker_fee_bps_per_side" in cell:
        out["maker_fee_bps_per_side"] = _r(cell.get("maker_fee_bps_per_side"), 3)
    if "net_bps_at_fee" in cell:
        out["net_bps_at_fee"] = _r(cell.get("net_bps_at_fee"), 3)
    return out


def _positive_cells_from_report(rep: dict) -> list[dict]:
    cells: list[dict] = []
    edge = rep.get("edge_scorecard") or {}
    for cell in edge.get("positive_fill_only_cells_with_sample_gate") or []:
        norm = _normalize_positive_cell("edge_scorecard", cell)
        if norm is not None:
            cells.append(norm)

    cond = rep.get("conditional_feature_scorecard") or {}
    for cell in cond.get("positive_cells_with_sample_gate") or []:
        norm = _normalize_positive_cell("conditional_feature_scorecard", cell)
        if norm is not None:
            cells.append(norm)

    wf = rep.get("walk_forward_feature_scorecard") or {}
    for row in wf.get("holdout_confirmed_candidates") or []:
        cell = row.get("holdout") or {}
        norm = _normalize_positive_cell("walk_forward_feature_scorecard_holdout", cell)
        if norm is not None:
            cells.append(norm)

    fee = rep.get("maker_fee_sensitivity_scorecard") or {}
    for scenario in fee.get("scenarios") or []:
        fee_side = _as_float(scenario.get("maker_fee_bps_per_side"))
        if fee_side is None or abs(fee_side - MAKER_FEE_BPS) > 1e-9:
            continue
        for cell in scenario.get("positive_sample_gate_cells") or []:
            norm = _normalize_positive_cell(
                "maker_fee_sensitivity_current_fee",
                cell,
                net_key="net_bps_at_fee",
            )
            if norm is not None:
                cells.append(norm)
    return cells


def _best_break_even_cell(rep: dict) -> dict | None:
    fee = rep.get("maker_fee_sensitivity_scorecard") or {}
    cell = fee.get("best_sample_gated_break_even_cell")
    if not cell:
        return None
    be = _as_float(cell.get("break_even_maker_fee_bps_per_side"))
    if be is None:
        return None
    out = dict(cell)
    origin = str(out.get("source") or "maker_fee_sensitivity_scorecard")
    out.setdefault("source", origin)
    out["key"] = _cell_key(origin, out)
    out["break_even_maker_fee_bps_per_side"] = _r(be, 3)
    out["fee_reduction_to_breakeven_bps_per_side"] = _r(MAKER_FEE_BPS - be, 3)
    return out


def _break_even_cells_from_report(rep: dict) -> list[dict]:
    fee = rep.get("maker_fee_sensitivity_scorecard") or {}
    candidates = []
    best = fee.get("best_sample_gated_break_even_cell")
    if best:
        candidates.append(("maker_fee_sensitivity_scorecard", best))
    for scenario in fee.get("scenarios") or []:
        for cell in scenario.get("positive_sample_gate_cells") or []:
            candidates.append(("maker_fee_sensitivity_scorecard", cell))

    by_key: dict[str, dict] = {}
    for source, cell in candidates:
        norm = _normalize_break_even_cell(source, cell)
        if norm is None:
            continue
        prev = by_key.get(norm["key"])
        if prev is None:
            by_key[norm["key"]] = norm
            continue
        prev_rank = (
            _as_float(prev.get("break_even_maker_fee_bps_per_side")) or -1e9,
            _as_float(prev.get("edge_before_fees_bps")) or -1e9,
            _as_int(prev.get("n_fill_only")),
        )
        new_rank = (
            _as_float(norm.get("break_even_maker_fee_bps_per_side")) or -1e9,
            _as_float(norm.get("edge_before_fees_bps")) or -1e9,
            _as_int(norm.get("n_fill_only")),
        )
        if new_rank > prev_rank:
            by_key[norm["key"]] = norm

    cells = list(by_key.values())
    cells.sort(
        key=lambda c: (
            _as_float(c.get("break_even_maker_fee_bps_per_side")) or -1e9,
            _as_float(c.get("edge_before_fees_bps")) or -1e9,
        ),
        reverse=True,
    )
    return cells


def _low_friction_motif_key(cell: dict) -> str:
    """Build a coarse motif key so threshold variants do not hide recurrence."""
    text = " ".join(
        str(cell.get(key) or "")
        for key in ("candidate_shape", "feature", "name", "condition")
    )
    parts = ["low_friction_motif"]
    if "spread_thin_queue_favorable_interaction_v1" in text:
        parts.append("spread_thin_queue_favorable")
    elif "spread_quiet_mid_support_interaction_v1" in text:
        parts.append("spread_quiet_mid_support")
    elif "spread_quiet_touch_interaction_v1" in text:
        parts.append("spread_quiet_touch")
    elif "spread_quiet_abs_qty_interaction_v1" in text:
        parts.append("spread_quiet_abs_qty")
    elif "spread_quiet_book_imbalance_interaction_v1" in text:
        parts.append("spread_quiet_book_imbalance")
    elif "low_friction_combo" in text:
        parts.append("spread_combo")
    else:
        parts.append(str(cell.get("candidate_shape") or cell.get("feature") or "unknown"))

    if "q0_" in text or "q_eff_" in text:
        parts.append("thin_queue")
    if "side_recent_trade_imbalance" in text:
        parts.append("recent_trade_imbalance")
    if "side_touch_size_delta_frac" in text:
        parts.append("touch_size_delta")
    if "spread_bps_delta" in text:
        parts.append("spread_delta")
    if "side_mid_move_bps" in text:
        parts.append("side_mid_move")
    if "side_book_imb" in text:
        parts.append("book_imbalance")
    if "recent_l1_update_count" in text or "recent_l1_update_intensity" in text:
        parts.append("l1_quiet_or_churn")
    if "recent_trade_count" in text or "recent_trade_abs_qty" in text:
        parts.append("recent_trade_activity")
    return "|".join(parts)


def _normalize_low_friction_near_miss_cell(source: str, cell: dict, *, current_fee: float) -> dict | None:
    """Normalize a low-friction holdout lead without promoting it to proof."""
    holdout = cell.get("holdout") if isinstance(cell.get("holdout"), dict) else {}
    train = cell.get("train") if isinstance(cell.get("train"), dict) else {}
    holdout_edge = _as_float(
        cell.get("holdout_edge_before_fees_bps")
        if "holdout_edge_before_fees_bps" in cell
        else holdout.get("edge_before_fees_bps")
    )
    if holdout_edge is None or holdout_edge <= 0.0:
        return None
    holdout_n = _as_int(
        cell.get("holdout_n_fill_only")
        if "holdout_n_fill_only" in cell
        else holdout.get("n_fill_only"),
        0,
    )
    holdout_suppressed = bool(
        cell.get(
            "holdout_signif_suppressed",
            cell.get("signif_suppressed", holdout.get("signif_suppressed", holdout_n < MIN_FILLS_FOR_SIGNIF)),
        )
    )
    sample_gated = holdout_n >= MIN_FILLS_FOR_SIGNIF and not holdout_suppressed
    train_edge = _as_float(
        cell.get("train_edge_before_fees_bps")
        if "train_edge_before_fees_bps" in cell
        else train.get("edge_before_fees_bps")
    )
    train_n = _as_int(
        cell.get("train_n_fill_only")
        if "train_n_fill_only" in cell
        else train.get("n_fill_only"),
        0,
    )
    out = {
        "source": source,
        "key": _cell_key(source, cell),
        "motif_key": _low_friction_motif_key(cell),
        "name": cell.get("name") or holdout.get("name"),
        "condition": cell.get("condition") or holdout.get("condition"),
        "feature": cell.get("feature") or holdout.get("feature"),
        "candidate_shape": cell.get("candidate_shape"),
        "threshold_source": cell.get("threshold_source"),
        "holdout_n_fill_only": holdout_n,
        "holdout_edge_before_fees_bps": _r(holdout_edge, 3),
        "holdout_net_bps": _r(
            cell.get("holdout_net_bps")
            if "holdout_net_bps" in cell
            else holdout.get("net_bps"),
            3,
        ),
        "holdout_sample_gated": sample_gated,
        "holdout_clears_current_fee_gross": bool(holdout_edge >= current_fee),
        "gap_to_current_fee_round_trip_bps": _r(current_fee - holdout_edge, 3),
        "train_n_fill_only": train_n,
        "train_edge_before_fees_bps": _r(train_edge, 3),
        "train_net_bps": _r(
            cell.get("train_net_bps")
            if "train_net_bps" in cell
            else train.get("net_bps"),
            3,
        ),
        "train_holdout_gross_positive": bool(train_edge is not None and train_edge > 0.0),
        "train_holdout_gross_current_fee_consistent": bool(
            train_edge is not None
            and train_edge >= current_fee
            and holdout_edge >= current_fee
        ),
    }
    components = cell.get("components") or holdout.get("components")
    if components:
        out["components"] = components
    return out


def _low_friction_near_miss_cells_from_report(rep: dict) -> list[dict]:
    """Extract sample-gated low-friction holdout leads from one report."""
    low = rep.get("low_friction_signal_scorecard") or {}
    failure = low.get("failure_summary") or {}
    current_fee = _as_float(
        failure.get("current_fee_round_trip_bps")
        or low.get("current_fee_round_trip_bps")
        or (rep.get("maker_fee_sensitivity_scorecard") or {}).get("current_fee_round_trip_bps")
    )
    if current_fee is None:
        current_fee = MAKER_FEE_BPS * 2.0
    candidates = []
    for key in (
        "best_sample_gated_holdout_gross_candidate",
        "best_sample_starved_current_fee_holdout_candidate",
        "best_holdout_gross_candidate",
    ):
        cell = failure.get(key)
        if isinstance(cell, dict):
            candidates.append(cell)
    for cell in failure.get("top_holdout_gross_candidates") or []:
        if isinstance(cell, dict):
            candidates.append(cell)

    by_key: dict[str, dict] = {}
    for cell in candidates:
        norm = _normalize_low_friction_near_miss_cell(
            "low_friction_signal_scorecard_holdout_near_miss",
            cell,
            current_fee=current_fee,
        )
        if norm is None:
            continue
        prev = by_key.get(norm["key"])
        if prev is None:
            by_key[norm["key"]] = norm
            continue
        prev_rank = (
            int(bool(prev.get("holdout_sample_gated"))),
            _as_float(prev.get("holdout_edge_before_fees_bps")) or -1e9,
            _as_int(prev.get("holdout_n_fill_only")),
        )
        new_rank = (
            int(bool(norm.get("holdout_sample_gated"))),
            _as_float(norm.get("holdout_edge_before_fees_bps")) or -1e9,
            _as_int(norm.get("holdout_n_fill_only")),
        )
        if new_rank > prev_rank:
            by_key[norm["key"]] = norm

    cells = list(by_key.values())
    cells.sort(
        key=lambda c: (
            int(bool(c.get("holdout_sample_gated"))),
            _as_float(c.get("holdout_edge_before_fees_bps")) or -1e9,
            _as_int(c.get("holdout_n_fill_only")),
        ),
        reverse=True,
    )
    return cells


def extract_window_summary(rep: dict, *, source_path: str | None = None) -> dict:
    """Extract comparable fields from one fill_sim report."""
    data = rep.get("data") or {}
    valid = not rep.get("abort") and _as_int(data.get("l1_rows_post_filter"), 0) > 0
    positives = _positive_cells_from_report(rep)
    walk_forward = rep.get("walk_forward_feature_scorecard") or {}
    best_be = _best_break_even_cell(rep)
    lower_fee_break_even_cells = _break_even_cells_from_report(rep)
    low_friction_near_miss_cells = _low_friction_near_miss_cells_from_report(rep)
    sample_gated_near_miss_cells = [
        cell for cell in low_friction_near_miss_cells if cell.get("holdout_sample_gated")
    ]
    sample_starved_current_fee_cells = [
        cell
        for cell in low_friction_near_miss_cells
        if not cell.get("holdout_sample_gated") and cell.get("holdout_clears_current_fee_gross")
    ]
    generated_at = rep.get("generated_at")
    return {
        "source_path": source_path,
        "generated_at": generated_at,
        "window_date": _window_date(rep),
        "valid": bool(valid),
        "abort": rep.get("abort"),
        "data": {
            "l1_rows_post_filter": data.get("l1_rows_post_filter"),
            "trades_rows": data.get("trades_rows"),
            "span_minutes": data.get("span_minutes"),
            "n_symbols": data.get("n_symbols"),
            "l1_min_ts": data.get("l1_min_ts"),
            "l1_max_ts": data.get("l1_max_ts"),
            "l1_max_age_hours": data.get("l1_max_age_hours"),
        },
        "statuses": {
            "edge_scorecard": (rep.get("edge_scorecard") or {}).get("status"),
            "conditional_feature_scorecard": (
                rep.get("conditional_feature_scorecard") or {}
            ).get("status"),
            "walk_forward_feature_scorecard": walk_forward.get("status"),
            "maker_fee_sensitivity_scorecard": (
                rep.get("maker_fee_sensitivity_scorecard") or {}
            ).get("status"),
        },
        "current_fee_sample_gated_positive_cells": positives,
        "current_fee_sample_gated_positive_count": len(positives),
        "walk_forward_holdout_confirmed_count": len(
            walk_forward.get("holdout_confirmed_candidates") or []
        ),
        "best_current_fee_positive_cell": max(
            positives,
            key=lambda c: c["net_bps"],
            default=None,
        ),
        "best_sample_gated_break_even_cell": best_be,
        "lower_fee_sample_gated_break_even_cells": lower_fee_break_even_cells[:20],
        "lower_fee_sample_gated_break_even_count": len(lower_fee_break_even_cells),
        "low_friction_near_miss_cells": low_friction_near_miss_cells[:20],
        "low_friction_sample_gated_near_miss_cells": sample_gated_near_miss_cells[:20],
        "low_friction_sample_gated_near_miss_count": len(sample_gated_near_miss_cells),
        "low_friction_sample_starved_current_fee_holdout_cells": (
            sample_starved_current_fee_cells[:20]
        ),
        "low_friction_sample_starved_current_fee_holdout_count": len(
            sample_starved_current_fee_cells
        ),
    }


def build_fill_sim_history_scorecard(
    reports: Iterable[dict],
    *,
    min_windows: int = 3,
    min_distinct_dates: int = 3,
    min_repeat_positive_windows: int = 2,
) -> dict:
    """Build a longer-regime scorecard from loaded fill_sim report dicts."""
    windows = [
        extract_window_summary(rep, source_path=rep.get("_source_path"))
        for rep in reports
    ]
    windows.sort(key=lambda w: (w.get("generated_at") or "", w.get("source_path") or ""))
    valid_windows = [w for w in windows if w["valid"]]
    distinct_dates = sorted({w["window_date"] for w in valid_windows if w["window_date"]})

    status_counts: dict[str, dict[str, int]] = {}
    for name in (
        "edge_scorecard",
        "conditional_feature_scorecard",
        "walk_forward_feature_scorecard",
        "maker_fee_sensitivity_scorecard",
    ):
        status_counts[name] = dict(Counter(
            (w["statuses"].get(name) or "MISSING") for w in valid_windows
        ))

    positive_windows = [
        w for w in valid_windows if w["current_fee_sample_gated_positive_count"] > 0
    ]
    holdout_windows = [
        w for w in valid_windows if w["walk_forward_holdout_confirmed_count"] > 0
    ]

    key_to_windows: dict[str, list[dict]] = defaultdict(list)
    for w in positive_windows:
        seen_in_window: set[str] = set()
        for cell in w["current_fee_sample_gated_positive_cells"]:
            key = cell["key"]
            if key in seen_in_window:
                continue
            seen_in_window.add(key)
            key_to_windows[key].append({"window": w, "cell": cell})

    repeated_positive_keys = []
    for key, rows in key_to_windows.items():
        if len(rows) >= min_repeat_positive_windows:
            best = max(rows, key=lambda r: r["cell"]["net_bps"])["cell"]
            repeated_positive_keys.append({
                "key": key,
                "windows": len(rows),
                "best_cell": best,
                "window_sources": [r["window"].get("source_path") for r in rows],
            })
    repeated_positive_keys.sort(
        key=lambda r: (r["windows"], r["best_cell"].get("net_bps") or -1e9),
        reverse=True,
    )

    break_even_rows = []
    for w in valid_windows:
        cell = w.get("best_sample_gated_break_even_cell")
        if not cell:
            continue
        be = _as_float(cell.get("break_even_maker_fee_bps_per_side"))
        if be is None:
            continue
        break_even_rows.append({
            "source_path": w.get("source_path"),
            "window_date": w.get("window_date"),
            "cell": cell,
            "break_even_maker_fee_bps_per_side": _r(be, 3),
        })
    break_even_rows.sort(
        key=lambda r: r["break_even_maker_fee_bps_per_side"],
        reverse=True,
    )
    best_break_even = break_even_rows[0] if break_even_rows else None

    lower_fee_windows = [
        w for w in valid_windows if w.get("lower_fee_sample_gated_break_even_count", 0) > 0
    ]
    lower_fee_dates = sorted({
        w["window_date"] for w in lower_fee_windows if w.get("window_date")
    })
    lower_fee_rows = []
    key_to_break_even_windows: dict[str, list[dict]] = defaultdict(list)
    for w in lower_fee_windows:
        seen_in_window: set[str] = set()
        for cell in w.get("lower_fee_sample_gated_break_even_cells") or []:
            key = cell.get("key")
            be = _as_float(cell.get("break_even_maker_fee_bps_per_side"))
            if not key or be is None:
                continue
            row = {
                "source_path": w.get("source_path"),
                "window_date": w.get("window_date"),
                "generated_at": w.get("generated_at"),
                "cell": cell,
                "break_even_maker_fee_bps_per_side": _r(be, 3),
            }
            lower_fee_rows.append(row)
            if key in seen_in_window:
                continue
            seen_in_window.add(key)
            key_to_break_even_windows[key].append({"window": w, "cell": cell})
    lower_fee_rows.sort(
        key=lambda r: r["break_even_maker_fee_bps_per_side"],
        reverse=True,
    )
    best_lower_fee_break_even = lower_fee_rows[0] if lower_fee_rows else None

    repeated_lower_fee_break_even_keys = []
    for key, rows in key_to_break_even_windows.items():
        if len(rows) >= min_repeat_positive_windows:
            best = max(
                rows,
                key=lambda r: (
                    _as_float(r["cell"].get("break_even_maker_fee_bps_per_side")) or -1e9,
                    _as_float(r["cell"].get("edge_before_fees_bps")) or -1e9,
                ),
            )["cell"]
            window_dates = sorted({
                r["window"].get("window_date")
                for r in rows
                if r["window"].get("window_date")
            })
            repeated_lower_fee_break_even_keys.append({
                "key": key,
                "windows": len(rows),
                "distinct_window_dates": window_dates,
                "best_cell": best,
                "window_sources": [r["window"].get("source_path") for r in rows],
            })
    repeated_lower_fee_break_even_keys.sort(
        key=lambda r: (
            r["windows"],
            len(r.get("distinct_window_dates") or []),
            _as_float((r.get("best_cell") or {}).get("break_even_maker_fee_bps_per_side")) or -1e9,
        ),
        reverse=True,
    )

    if not lower_fee_windows:
        lower_fee_stability_status = "NO_LOWER_FEE_BREAK_EVEN_WINDOWS"
        lower_fee_stability_reason = "no_sample_gated_lower_fee_break_even_cells"
    elif not repeated_lower_fee_break_even_keys:
        lower_fee_stability_status = "LOWER_FEE_BREAK_EVEN_ROTATES_OR_DATE_INSUFFICIENT"
        lower_fee_stability_reason = (
            "distinct_dates_below_min_and_no_repeated_key"
            if len(lower_fee_dates) < min_distinct_dates
            else "no_repeated_lower_fee_break_even_key"
        )
    elif len(lower_fee_dates) < min_distinct_dates:
        lower_fee_stability_status = "LOWER_FEE_BREAK_EVEN_REPEATS_BUT_DATE_INSUFFICIENT"
        lower_fee_stability_reason = "repeated_key_but_distinct_dates_below_min"
    else:
        lower_fee_stability_status = "LOWER_FEE_BREAK_EVEN_REPEATS_ACROSS_WINDOWS"
        lower_fee_stability_reason = "repeated_lower_fee_break_even_key_across_windows"

    lower_fee_break_even_stability = {
        "status": lower_fee_stability_status,
        "reason": lower_fee_stability_reason,
        "lower_fee_break_even_windows": len(lower_fee_windows),
        "distinct_window_dates": lower_fee_dates,
        "repeated_key_count": len(repeated_lower_fee_break_even_keys),
        "min_distinct_dates": int(min_distinct_dates),
        "min_repeat_positive_windows": int(min_repeat_positive_windows),
        "current_maker_fee_bps_per_side": MAKER_FEE_BPS,
        "best_lower_fee_break_even_window": best_lower_fee_break_even,
        "best_repeated_lower_fee_break_even_key": (
            repeated_lower_fee_break_even_keys[0]
            if repeated_lower_fee_break_even_keys else None
        ),
        "top_repeated_lower_fee_break_even_keys": repeated_lower_fee_break_even_keys[:10],
    }

    low_friction_near_miss_windows = [
        w for w in valid_windows if w.get("low_friction_sample_gated_near_miss_count", 0) > 0
    ]
    low_friction_near_miss_dates = sorted({
        w["window_date"] for w in low_friction_near_miss_windows if w.get("window_date")
    })
    low_friction_near_miss_rows = []
    key_to_low_friction_near_miss_windows: dict[str, list[dict]] = defaultdict(list)
    for w in low_friction_near_miss_windows:
        seen_in_window: set[str] = set()
        for cell in w.get("low_friction_sample_gated_near_miss_cells") or []:
            key = cell.get("key")
            holdout_edge = _as_float(cell.get("holdout_edge_before_fees_bps"))
            if not key or holdout_edge is None:
                continue
            row = {
                "source_path": w.get("source_path"),
                "window_date": w.get("window_date"),
                "generated_at": w.get("generated_at"),
                "cell": cell,
                "holdout_edge_before_fees_bps": _r(holdout_edge, 3),
                "gap_to_current_fee_round_trip_bps": _r(
                    cell.get("gap_to_current_fee_round_trip_bps"),
                    3,
                ),
            }
            low_friction_near_miss_rows.append(row)
            if key in seen_in_window:
                continue
            seen_in_window.add(key)
            key_to_low_friction_near_miss_windows[key].append({"window": w, "cell": cell})
    low_friction_near_miss_rows.sort(
        key=lambda r: (
            _as_float(r.get("holdout_edge_before_fees_bps")) or -1e9,
            _as_int((r.get("cell") or {}).get("holdout_n_fill_only")),
        ),
        reverse=True,
    )
    best_low_friction_near_miss = (
        low_friction_near_miss_rows[0] if low_friction_near_miss_rows else None
    )

    repeated_low_friction_near_miss_keys = []
    for key, rows in key_to_low_friction_near_miss_windows.items():
        if len(rows) >= min_repeat_positive_windows:
            best = max(
                rows,
                key=lambda r: (
                    _as_float(r["cell"].get("holdout_edge_before_fees_bps")) or -1e9,
                    _as_int(r["cell"].get("holdout_n_fill_only")),
                    _as_float(r["cell"].get("train_edge_before_fees_bps")) or -1e9,
                ),
            )["cell"]
            window_dates = sorted({
                r["window"].get("window_date")
                for r in rows
                if r["window"].get("window_date")
            })
            repeated_low_friction_near_miss_keys.append({
                "key": key,
                "windows": len(rows),
                "distinct_window_dates": window_dates,
                "best_cell": best,
                "window_sources": [r["window"].get("source_path") for r in rows],
            })
    repeated_low_friction_near_miss_keys.sort(
        key=lambda r: (
            r["windows"],
            len(r.get("distinct_window_dates") or []),
            _as_float((r.get("best_cell") or {}).get("holdout_edge_before_fees_bps")) or -1e9,
        ),
        reverse=True,
    )

    motif_to_low_friction_near_miss_windows: dict[str, list[dict]] = defaultdict(list)
    for w in low_friction_near_miss_windows:
        seen_motif_in_window: set[str] = set()
        for cell in w.get("low_friction_sample_gated_near_miss_cells") or []:
            motif_key = cell.get("motif_key")
            if not motif_key or motif_key in seen_motif_in_window:
                continue
            seen_motif_in_window.add(motif_key)
            motif_to_low_friction_near_miss_windows[motif_key].append({
                "window": w,
                "cell": cell,
            })

    repeated_low_friction_near_miss_motifs = []
    for motif_key, rows in motif_to_low_friction_near_miss_windows.items():
        if len(rows) < min_repeat_positive_windows:
            continue
        best = max(
            rows,
            key=lambda r: (
                _as_float(r["cell"].get("holdout_edge_before_fees_bps")) or -1e9,
                _as_int(r["cell"].get("holdout_n_fill_only")),
                _as_float(r["cell"].get("train_edge_before_fees_bps")) or -1e9,
            ),
        )["cell"]
        window_dates = sorted({
            r["window"].get("window_date")
            for r in rows
            if r["window"].get("window_date")
        })
        repeated_low_friction_near_miss_motifs.append({
            "motif_key": motif_key,
            "windows": len(rows),
            "distinct_window_dates": window_dates,
            "best_cell": best,
            "candidate_keys": sorted({
                str(r["cell"].get("key"))
                for r in rows
                if r["cell"].get("key")
            }),
            "window_sources": [r["window"].get("source_path") for r in rows],
        })
    repeated_low_friction_near_miss_motifs.sort(
        key=lambda r: (
            r["windows"],
            len(r.get("distinct_window_dates") or []),
            _as_float((r.get("best_cell") or {}).get("holdout_edge_before_fees_bps")) or -1e9,
        ),
        reverse=True,
    )

    sample_starved_current_fee_holdout_windows = [
        w
        for w in valid_windows
        if w.get("low_friction_sample_starved_current_fee_holdout_count", 0) > 0
    ]
    if not low_friction_near_miss_windows and not sample_starved_current_fee_holdout_windows:
        near_miss_stability_status = "NO_LOW_FRICTION_NEAR_MISS_WINDOWS"
        near_miss_stability_reason = "no_sample_gated_or_current_fee_holdout_near_miss"
    elif not repeated_low_friction_near_miss_keys:
        near_miss_stability_status = "LOW_FRICTION_NEAR_MISS_ROTATES_OR_DATE_INSUFFICIENT"
        near_miss_stability_reason = (
            "distinct_dates_below_min_and_no_repeated_key"
            if len(low_friction_near_miss_dates) < min_distinct_dates
            else "no_repeated_low_friction_near_miss_key"
        )
    elif len(low_friction_near_miss_dates) < min_distinct_dates:
        near_miss_stability_status = "LOW_FRICTION_NEAR_MISS_REPEATS_BUT_DATE_INSUFFICIENT"
        near_miss_stability_reason = "repeated_key_but_distinct_dates_below_min"
    else:
        near_miss_stability_status = "LOW_FRICTION_NEAR_MISS_REPEATS_ACROSS_WINDOWS"
        near_miss_stability_reason = "repeated_low_friction_near_miss_key_across_windows"

    low_friction_near_miss_stability = {
        "status": near_miss_stability_status,
        "reason": near_miss_stability_reason,
        "sample_gated_near_miss_windows": len(low_friction_near_miss_windows),
        "sample_starved_current_fee_holdout_windows": len(
            sample_starved_current_fee_holdout_windows
        ),
        "distinct_window_dates": low_friction_near_miss_dates,
        "repeated_key_count": len(repeated_low_friction_near_miss_keys),
        "min_distinct_dates": int(min_distinct_dates),
        "min_repeat_positive_windows": int(min_repeat_positive_windows),
        "current_maker_fee_bps_per_side": MAKER_FEE_BPS,
        "current_fee_round_trip_bps": _r(MAKER_FEE_BPS * 2.0, 3),
        "best_near_miss_window": best_low_friction_near_miss,
        "best_repeated_near_miss_key": (
            repeated_low_friction_near_miss_keys[0]
            if repeated_low_friction_near_miss_keys else None
        ),
        "top_repeated_near_miss_keys": repeated_low_friction_near_miss_keys[:10],
    }

    if not low_friction_near_miss_windows and not sample_starved_current_fee_holdout_windows:
        motif_stability_status = "NO_LOW_FRICTION_NEAR_MISS_MOTIF_WINDOWS"
        motif_stability_reason = "no_sample_gated_or_current_fee_holdout_near_miss"
    elif not repeated_low_friction_near_miss_motifs:
        motif_stability_status = "LOW_FRICTION_NEAR_MISS_MOTIF_ROTATES_OR_DATE_INSUFFICIENT"
        motif_stability_reason = (
            "distinct_dates_below_min_and_no_repeated_motif"
            if len(low_friction_near_miss_dates) < min_distinct_dates
            else "no_repeated_low_friction_near_miss_motif"
        )
    elif len(low_friction_near_miss_dates) < min_distinct_dates:
        motif_stability_status = "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_BUT_DATE_INSUFFICIENT"
        motif_stability_reason = "repeated_motif_but_distinct_dates_below_min"
    else:
        motif_stability_status = "LOW_FRICTION_NEAR_MISS_MOTIF_REPEATS_ACROSS_WINDOWS"
        motif_stability_reason = "repeated_low_friction_near_miss_motif_across_windows"

    low_friction_near_miss_motif_stability = {
        "status": motif_stability_status,
        "reason": motif_stability_reason,
        "sample_gated_near_miss_windows": len(low_friction_near_miss_windows),
        "distinct_window_dates": low_friction_near_miss_dates,
        "repeated_motif_count": len(repeated_low_friction_near_miss_motifs),
        "min_distinct_dates": int(min_distinct_dates),
        "min_repeat_positive_windows": int(min_repeat_positive_windows),
        "best_repeated_near_miss_motif": (
            repeated_low_friction_near_miss_motifs[0]
            if repeated_low_friction_near_miss_motifs else None
        ),
        "top_repeated_near_miss_motifs": repeated_low_friction_near_miss_motifs[:10],
    }

    enough_windows = len(valid_windows) >= min_windows and len(distinct_dates) >= min_distinct_dates
    if not windows:
        status = "NO_HISTORY_REPORTS"
        reason = "no_reports_loaded"
    elif not enough_windows:
        status = "HISTORY_INSUFFICIENT_WINDOWS"
        reason = "below_min_windows_or_dates"
    elif holdout_windows and repeated_positive_keys:
        status = "HISTORY_REPEAT_HOLDOUT_OR_CURRENT_FEE_POSITIVE"
        reason = "repeated_sample_gated_positive_with_holdout_signal"
    elif holdout_windows:
        status = "HISTORY_SINGLE_HOLDOUT_CONFIRMED_NEEDS_MORE_WINDOWS"
        reason = "holdout_positive_not_repeated_enough"
    elif repeated_positive_keys:
        status = "HISTORY_CURRENT_FEE_REPEAT_IN_WINDOW_NEEDS_OOS"
        reason = "current_fee_positive_repeats_but_not_walk_forward_confirmed"
    elif positive_windows:
        status = "HISTORY_SINGLE_WINDOW_CURRENT_FEE_POSITIVE_NEEDS_CONFIRMATION"
        reason = "current_fee_positive_not_repeated_enough"
    elif best_break_even and (
        _as_float(best_break_even["break_even_maker_fee_bps_per_side"]) is not None
        and _as_float(best_break_even["break_even_maker_fee_bps_per_side"]) < MAKER_FEE_BPS
    ):
        status = "HISTORY_LOWER_FEE_ONLY"
        reason = "sample_gated_cells_exist_only_below_current_fee"
    else:
        status = "HISTORY_NO_CURRENT_FEE_SAMPLE_GATED_EDGE"
        reason = "no_current_fee_positive_sample_gated_cells"

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "reason": reason,
        "thresholds": {
            "min_windows": int(min_windows),
            "min_distinct_dates": int(min_distinct_dates),
            "min_repeat_positive_windows": int(min_repeat_positive_windows),
            "min_fills_for_signif": MIN_FILLS_FOR_SIGNIF,
            "current_maker_fee_bps_per_side": MAKER_FEE_BPS,
        },
        "windows_loaded": len(windows),
        "valid_windows": len(valid_windows),
        "distinct_window_dates": distinct_dates,
        "status_counts": status_counts,
        "current_fee_sample_gated_positive_windows": len(positive_windows),
        "walk_forward_holdout_confirmed_windows": len(holdout_windows),
        "repeated_positive_keys": repeated_positive_keys[:20],
        "best_sample_gated_break_even_window": best_break_even,
        "best_break_even_windows": break_even_rows[:20],
        "lower_fee_break_even_windows": len(lower_fee_windows),
        "lower_fee_break_even_distinct_window_dates": lower_fee_dates,
        "repeated_lower_fee_break_even_keys": repeated_lower_fee_break_even_keys[:20],
        "best_lower_fee_break_even_window": best_lower_fee_break_even,
        "lower_fee_break_even_stability": lower_fee_break_even_stability,
        "low_friction_near_miss_windows": len(low_friction_near_miss_windows),
        "low_friction_near_miss_distinct_window_dates": low_friction_near_miss_dates,
        "low_friction_sample_starved_current_fee_holdout_windows": len(
            sample_starved_current_fee_holdout_windows
        ),
        "repeated_low_friction_near_miss_keys": repeated_low_friction_near_miss_keys[:20],
        "best_low_friction_near_miss_window": best_low_friction_near_miss,
        "low_friction_near_miss_stability": low_friction_near_miss_stability,
        "low_friction_near_miss_motif_stability": (
            low_friction_near_miss_motif_stability
        ),
        "window_summaries": windows,
        "note": (
            "Report-history reducer only. Current-fee repeated positives still need "
            "walk-forward/cross-regime confirmation, inventory-risk review, and formal "
            "QC/MIT/AI-E before strategy or promotion work."
        ),
    }


def load_reports(paths: Iterable[str]) -> list[dict]:
    reports = []
    for path in paths:
        try:
            with open(path, encoding="utf-8") as f:
                rep = json.load(f)
        except (OSError, ValueError):
            continue
        if not isinstance(rep, dict):
            continue
        rep = dict(rep)
        rep["_source_path"] = path
        reports.append(rep)
    return reports


def _expand_paths(patterns: Iterable[str]) -> list[str]:
    out: list[str] = []
    for pattern in patterns:
        matches = glob.glob(pattern)
        if matches:
            out.extend(matches)
        else:
            out.append(pattern)
    return sorted(dict.fromkeys(out))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Aggregate fill_sim JSON reports into a cross-window scorecard."
    )
    ap.add_argument("paths", nargs="*", help="report JSON paths or glob patterns")
    ap.add_argument("--glob", dest="globs", action="append", default=[],
                    help="additional report glob; may be repeated")
    ap.add_argument("--out", default="/tmp/openclaw/research/fillsim/fillsim_history_scorecard.json")
    ap.add_argument("--min-windows", type=int, default=3)
    ap.add_argument("--min-distinct-dates", type=int, default=3)
    ap.add_argument("--min-repeat-positive-windows", type=int, default=2)
    args = ap.parse_args(argv)

    patterns = list(args.paths) + list(args.globs or [])
    if not patterns:
        patterns = [DEFAULT_HISTORY_GLOB]
    paths = _expand_paths(patterns)
    reports = load_reports(paths)
    scorecard = build_fill_sim_history_scorecard(
        reports,
        min_windows=args.min_windows,
        min_distinct_dates=args.min_distinct_dates,
        min_repeat_positive_windows=args.min_repeat_positive_windows,
    )

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(scorecard, f, indent=2, ensure_ascii=False)
    print(json.dumps({
        "status": scorecard["status"],
        "windows_loaded": scorecard["windows_loaded"],
        "valid_windows": scorecard["valid_windows"],
        "distinct_window_dates": scorecard["distinct_window_dates"],
        "best_break_even": scorecard["best_sample_gated_break_even_window"],
        "lower_fee_break_even_stability_status": (
            scorecard.get("lower_fee_break_even_stability") or {}
        ).get("status"),
        "lower_fee_break_even_windows": scorecard.get("lower_fee_break_even_windows"),
        "repeated_lower_fee_break_even_key_count": len(
            scorecard.get("repeated_lower_fee_break_even_keys") or []
        ),
        "low_friction_near_miss_stability_status": (
            scorecard.get("low_friction_near_miss_stability") or {}
        ).get("status"),
        "low_friction_near_miss_windows": scorecard.get("low_friction_near_miss_windows"),
        "repeated_low_friction_near_miss_key_count": len(
            scorecard.get("repeated_low_friction_near_miss_keys") or []
        ),
        "low_friction_near_miss_motif_stability_status": (
            scorecard.get("low_friction_near_miss_motif_stability") or {}
        ).get("status"),
        "repeated_low_friction_near_miss_motif_count": (
            (scorecard.get("low_friction_near_miss_motif_stability") or {})
            .get("repeated_motif_count")
        ),
        "out": args.out,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

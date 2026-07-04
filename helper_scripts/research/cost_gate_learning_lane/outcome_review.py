#!/usr/bin/env python3
"""Review blocked-signal outcomes for the cost-gate demo learning lane.

This module turns accumulated ``blocked_signal_outcome`` ledger rows into a
machine-checkable review scorecard. It does not grant order authority, lower
the main Cost Gate, write PG, call Bybit, or mutate runtime config.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
from cost_gate_learning_lane.evidence_stats import (
    bh_fdr_pass,
    expected_max_under_null_bps,
    one_sided_t_p_value,
    sign_flip_selection_p_value,
)
from cost_gate_learning_lane.runtime_adapter import read_jsonl_ledger


BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION = (
    "cost_gate_demo_learning_lane_blocked_outcome_review_v3"
)
BLOCKED_OUTCOME_REVIEW_RECORD_TYPE = "blocked_signal_outcome_review"


@dataclass(frozen=True)
class BlockedOutcomeReviewConfig:
    """Fail-closed thresholds for blocked-signal review candidates."""

    min_outcomes_per_side_cell: int = 3
    min_avg_net_bps: float = 0.0
    min_net_positive_pct: float = 60.0
    # P2-8:候選面 BH-FDR 目標 false discovery rate;headline sign-flip 抽樣次數。
    fdr_q: float = 0.10
    sign_flip_b: int = 1000


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _str(value: Any) -> str:
    return str(value or "").strip()


def validate_blocked_outcome_review_config(cfg: BlockedOutcomeReviewConfig) -> None:
    if cfg.min_outcomes_per_side_cell < 1 or cfg.min_outcomes_per_side_cell > 1_000:
        raise ValueError("--min-outcomes-per-side-cell must be in [1, 1000]")
    if cfg.min_avg_net_bps < -10_000.0 or cfg.min_avg_net_bps > 10_000.0:
        raise ValueError("--min-avg-net-bps must be in [-10000, 10000]")
    if cfg.min_net_positive_pct < 0.0 or cfg.min_net_positive_pct > 100.0:
        raise ValueError("--min-net-positive-pct must be in [0, 100]")
    if not (0.0 < cfg.fdr_q < 1.0):
        raise ValueError("--fdr-q must be in (0, 1)")
    if cfg.sign_flip_b < 1 or cfg.sign_flip_b > 100_000:
        raise ValueError("--sign-flip-b must be in [1, 100000]")


def _row_sort_ts(row: dict[str, Any]) -> str:
    return _str(row.get("generated_at_utc")) or _str(row.get("exit_ts_ms"))


def _int(value: Any, default: int = 0) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return out


def _wrongful_block_score(
    *,
    outcome_count: int,
    avg_net_bps: float | None,
    net_positive_pct: float | None,
    cfg: BlockedOutcomeReviewConfig,
) -> float:
    """Rank review candidates without changing the conservative review gate."""
    if avg_net_bps is None or net_positive_pct is None:
        return 0.0
    avg_margin = avg_net_bps - cfg.min_avg_net_bps
    pct_margin = net_positive_pct - cfg.min_net_positive_pct
    if (
        outcome_count < cfg.min_outcomes_per_side_cell
        or avg_margin < 0.0
        or pct_margin < 0.0
    ):
        return 0.0
    sample_factor = min(2.0, outcome_count / cfg.min_outcomes_per_side_cell)
    return avg_margin * (net_positive_pct / 100.0) * sample_factor


def _diagnose_cost_gate_escape(
    *,
    outcome_count: int,
    avg_net_bps: float | None,
    avg_gross_bps: float | None,
    net_positive_pct: float | None,
    review_candidate: bool,
    cfg: BlockedOutcomeReviewConfig,
) -> dict[str, Any]:
    """Classify blocked outcomes into the next profit-learning action."""
    if outcome_count < cfg.min_outcomes_per_side_cell:
        return {
            "learning_diagnosis": "SAMPLE_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "continue_recording_same_side_cell_blocked_signal_outcomes"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": False,
        }

    if review_candidate:
        return {
            "learning_diagnosis": "FALSE_NEGATIVE_CANDIDATE_AFTER_COST",
            "cost_gate_escape_recommendation": (
                "operator_review_bounded_probe_authority_without_global_gate_lowering"
            ),
            "edge_amplification_required": False,
            "false_negative_candidate": True,
        }

    avg_net = avg_net_bps if avg_net_bps is not None else 0.0
    avg_gross = avg_gross_bps if avg_gross_bps is not None else 0.0
    net_positive = net_positive_pct if net_positive_pct is not None else 0.0
    if avg_gross > 0.0 and avg_net < cfg.min_avg_net_bps:
        return {
            "learning_diagnosis": "GROSS_EDGE_POSITIVE_COST_CUSHION_INSUFFICIENT",
            "cost_gate_escape_recommendation": (
                "amplify_edge_or_reduce_friction_for_same_side_cell"
            ),
            "edge_amplification_required": True,
            "false_negative_candidate": False,
        }
    if avg_net >= cfg.min_avg_net_bps and net_positive < cfg.min_net_positive_pct:
        return {
            "learning_diagnosis": "POSITIVE_EDGE_UNSTABLE_AFTER_COST",
            "cost_gate_escape_recommendation": (
                "add_regime_filter_or_matched_controls_before_probe_review"
            ),
            "edge_amplification_required": True,
            "false_negative_candidate": False,
        }
    return {
        "learning_diagnosis": "BLOCK_CONFIRMED_AFTER_COST",
        "cost_gate_escape_recommendation": (
            "keep_cost_gate_blocked_or_archive_until_new_evidence"
        ),
        "edge_amplification_required": False,
        "false_negative_candidate": False,
    }


def _optimistic_side_cell_key(side_cell_key: str) -> str:
    """side_cell_key = strategy|SYMBOL|Side → edge_estimates 的 strategy::symbol 頂層鍵。"""
    parts = side_cell_key.split("|")
    if len(parts) >= 2:
        return f"{parts[0]}::{parts[1].upper()}"
    return side_cell_key


def _review_side_cell_rows(
    side_cell_key: str,
    rows: list[dict[str, Any]],
    *,
    cfg: BlockedOutcomeReviewConfig,
    censored_count: int = 0,
    edge_estimates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    edge_estimates = edge_estimates or {}
    nets = []
    optimistic_nets = []
    gross_values = []
    cost_values = []
    horizon_counts: dict[int, int] = {}
    cost_model_version_counts: dict[str, int] = {}
    symbols = set()
    strategies = set()
    sides = set()
    latest = None
    for row in rows:
        net = _float(row.get("realized_net_bps"))
        if net is None:
            continue
        nets.append(net)
        # candidacy_flipped_by_cost_model:optimistic net(gross−4.0)供對照;
        # net_bps_optimistic 缺失(舊 legacy row 未經 overlay)則 fallback gross−4.0。
        opt = _float(row.get("net_bps_optimistic"))
        if opt is None:
            gross_for_opt = _float(row.get("gross_bps"))
            opt = gross_for_opt - 4.0 if gross_for_opt is not None else net
        optimistic_nets.append(opt)
        gross = _float(row.get("gross_bps"))
        if gross is not None:
            gross_values.append(gross)
        cost = _float(row.get("cost_bps"))
        if cost is not None:
            cost_values.append(cost)
        horizon = _int(row.get("horizon_minutes"), default=0)
        if horizon > 0:
            horizon_counts[horizon] = horizon_counts.get(horizon, 0) + 1
        # P1-2a:舊 row 缺 cost_model_version → legacy_optimistic_v0(樂觀成本，不可立案)。
        version = _str(row.get("cost_model_version")) or "legacy_optimistic_v0"
        cost_model_version_counts[version] = cost_model_version_counts.get(version, 0) + 1
        symbol = _str(row.get("symbol")).upper()
        strategy = _str(row.get("strategy_name"))
        side = _str(row.get("side"))
        if symbol:
            symbols.add(symbol)
        if strategy:
            strategies.add(strategy)
        if side:
            sides.add(side)
        if latest is None or _row_sort_ts(row) >= _row_sort_ts(latest):
            latest = row

    outcome_count = len(nets)
    positive_count = sum(1 for value in nets if value > 0.0)
    gross_positive_count = sum(1 for value in gross_values if value > 0.0)
    avg_net = sum(nets) / outcome_count if outcome_count else None
    # 樣本標準差(ddof=1)供 BH-FDR 單側 t 檢定用；n<2 無法估變異數。
    std_net = None
    if outcome_count >= 2 and avg_net is not None:
        variance = sum((value - avg_net) ** 2 for value in nets) / (outcome_count - 1)
        std_net = math.sqrt(variance)
    # F7:censored_pct = censored / (有效 + censored)。>30% → 資料品質先於統計顯著。
    total_with_censored = outcome_count + censored_count
    censored_pct = (
        censored_count / total_with_censored * 100.0 if total_with_censored else 0.0
    )
    observation_gap_suspect = censored_pct > 30.0
    net_positive_pct = (positive_count / outcome_count * 100.0) if outcome_count else None
    min_net = min(nets) if nets else None
    max_net = max(nets) if nets else None
    avg_gross = sum(gross_values) / len(gross_values) if gross_values else None
    avg_cost = sum(cost_values) / len(cost_values) if cost_values else None
    gross_positive_pct = (
        gross_positive_count / len(gross_values) * 100.0
        if gross_values
        else None
    )
    net_cost_cushion_bps = (
        avg_net - cfg.min_avg_net_bps
        if avg_net is not None
        else None
    )
    net_positive_margin_pct = (
        net_positive_pct - cfg.min_net_positive_pct
        if net_positive_pct is not None
        else None
    )
    sample_margin_count = outcome_count - cfg.min_outcomes_per_side_cell
    wrongful_block_score = _wrongful_block_score(
        outcome_count=outcome_count,
        avg_net_bps=avg_net,
        net_positive_pct=net_positive_pct,
        cfg=cfg,
    )
    dominant_horizon = None
    if horizon_counts:
        dominant_horizon = sorted(
            horizon_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[0][0]

    # P1-2a:含 legacy_optimistic_v0 row 的 cell 數字被樂觀成本污染，不可用於立案。
    legacy_optimistic_present = cost_model_version_counts.get("legacy_optimistic_v0", 0) > 0
    if observation_gap_suspect:
        # F7:資料品質缺陷先於統計顯著;高 censored 比例不得為 review candidate。
        status = "OBSERVATION_GAP_SUSPECT"
        reason = "censored_pct_above_30_data_quality_before_significance"
        review_candidate = False
    elif outcome_count < cfg.min_outcomes_per_side_cell:
        status = "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
        reason = "side_cell_below_min_blocked_outcome_sample"
        review_candidate = False
    elif legacy_optimistic_present:
        status = "LEGACY_OPTIMISTIC_COST_UNBACKFILLED"
        reason = "cell_contains_legacy_optimistic_cost_rows_not_candidacy_eligible"
        review_candidate = False
    elif (
        avg_net is not None
        and avg_net >= cfg.min_avg_net_bps
        and net_positive_pct is not None
        and net_positive_pct >= cfg.min_net_positive_pct
    ):
        status = "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
        reason = "blocked_signal_markouts_clear_review_thresholds"
        review_candidate = True
    else:
        status = "KEEP_COST_GATE_BLOCKED"
        reason = "blocked_signal_markouts_do_not_clear_review_thresholds"
        review_candidate = False

    # P1-2c:candidacy_flipped_by_cost_model = 樂觀成本過線但保守成本不過的 cell。
    avg_opt = sum(optimistic_nets) / len(optimistic_nets) if optimistic_nets else None
    opt_positive_pct = (
        sum(1 for v in optimistic_nets if v > 0.0) / len(optimistic_nets) * 100.0
        if optimistic_nets
        else None
    )
    would_pass_optimistic = (
        outcome_count >= cfg.min_outcomes_per_side_cell
        and avg_opt is not None
        and avg_opt >= cfg.min_avg_net_bps
        and opt_positive_pct is not None
        and opt_positive_pct >= cfg.min_net_positive_pct
    )
    candidacy_flipped_by_cost_model = bool(would_pass_optimistic and not review_candidate)

    # F1 fix(c):realized 矛盾標記。反事實 avg 遠高於 realized cell EV(且 realized 為負、
    # n≥10)代表 fill-at-signal-price 高估執行,不得進 candidate，改標 EXECUTION_REALISM_SUSPECT。
    edge = edge_estimates.get(_optimistic_side_cell_key(side_cell_key))
    realized_cell_ev_bps = _float(edge.get("realized_ev_bps")) if edge else None
    if realized_cell_ev_bps is None and edge:
        realized_cell_ev_bps = _float(edge.get("ev_bps"))
    realized_cell_n = _int(edge.get("n"), default=0) if edge else 0
    gap = (
        avg_net - realized_cell_ev_bps
        if (avg_net is not None and realized_cell_ev_bps is not None)
        else None
    )
    realized_contradiction = bool(
        realized_cell_n >= 10
        and realized_cell_ev_bps is not None
        and realized_cell_ev_bps < 0.0
        and gap is not None
        and gap > 50.0
    )
    if realized_contradiction:
        status = "EXECUTION_REALISM_SUSPECT"
        reason = "counterfactual_avg_contradicts_negative_realized_cell_ev"
        review_candidate = False

    diagnosis = _diagnose_cost_gate_escape(
        outcome_count=outcome_count,
        avg_net_bps=avg_net,
        avg_gross_bps=avg_gross,
        net_positive_pct=net_positive_pct,
        review_candidate=review_candidate,
        cfg=cfg,
    )

    return {
        "side_cell_key": side_cell_key,
        "status": status,
        "reason": reason,
        **diagnosis,
        "review_candidate": review_candidate,
        "outcome_count": outcome_count,
        "positive_outcome_count": positive_count,
        "gross_positive_outcome_count": gross_positive_count,
        "avg_net_bps": avg_net,
        "avg_gross_bps": avg_gross,
        "avg_cost_bps": avg_cost,
        "min_net_bps": min_net,
        "max_net_bps": max_net,
        "net_positive_pct": net_positive_pct,
        "gross_positive_pct": gross_positive_pct,
        "net_cost_cushion_bps": net_cost_cushion_bps,
        "net_positive_margin_pct": net_positive_margin_pct,
        "sample_margin_count": sample_margin_count,
        "wrongful_block_score": wrongful_block_score,
        "std_net_bps": std_net,
        "one_sided_t_p_value": one_sided_t_p_value(avg_net or 0.0, std_net, outcome_count)
        if outcome_count >= cfg.min_outcomes_per_side_cell and std_net is not None
        else None,
        "bh_fdr_pass": None,
        "censored_count": censored_count,
        "censored_pct": censored_pct,
        "observation_gap_suspect": observation_gap_suspect,
        "cost_model_version_counts": {
            key: cost_model_version_counts[key]
            for key in sorted(cost_model_version_counts)
        },
        "legacy_optimistic_cost_present": legacy_optimistic_present,
        "candidacy_flipped_by_cost_model": candidacy_flipped_by_cost_model,
        "avg_net_bps_optimistic": avg_opt,
        "realized_cell_ev_bps": realized_cell_ev_bps,
        "realized_cell_n": realized_cell_n,
        "counterfactual_vs_realized_gap_bps": gap,
        "realized_contradiction": realized_contradiction,
        "horizon_minutes": sorted(horizon_counts),
        "horizon_counts": {
            str(key): horizon_counts[key]
            for key in sorted(horizon_counts)
        },
        "dominant_horizon_minutes": dominant_horizon,
        "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
        "min_avg_net_bps": cfg.min_avg_net_bps,
        "min_net_positive_pct": cfg.min_net_positive_pct,
        "strategy_names": sorted(strategies),
        "symbols": sorted(symbols),
        "sides": sorted(sides),
        "latest_generated_at_utc": latest.get("generated_at_utc") if latest else None,
        "latest_attempt_id": latest.get("attempt_id") if latest else None,
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
    }


def _apply_bh_fdr(side_cells: list[dict[str, Any]], *, cfg: BlockedOutcomeReviewConfig) -> None:
    """P2-8(b):對 n≥min 的 cell family 跑 BH-FDR(q)，把 bh_fdr_pass 寫回 cell。

    review_candidate 再加一條 BH pass(fail-closed:BH 只會撤下不會扶正)。誠實預期：
    當前樣本(median n 小、σ≈200)幾乎必然零通過 —— 這是正確結果，未過 BH 的 cell
    只可作 exploration 排序，不得以「false-negative 證據」語言呈現。
    """
    eligible = [
        cell
        for cell in side_cells
        if cell.get("one_sided_t_p_value") is not None
    ]
    if not eligible:
        return
    p_values = [float(cell["one_sided_t_p_value"]) for cell in eligible]
    passed = bh_fdr_pass(p_values, cfg.fdr_q)
    for cell, ok in zip(eligible, passed):
        cell["bh_fdr_pass"] = bool(ok)
        if cell.get("review_candidate") and not ok:
            # BH 未過 → 撤下候選資格，改標 exploration;診斷/推薦欄同步重算以保持 packet
            # 內部一致(否則 learning_diagnosis 仍殘留 FALSE_NEGATIVE_CANDIDATE)。
            cell["review_candidate"] = False
            cell["status"] = "EXPLORATION_CANDIDATE_BH_FDR_NOT_PASSED"
            cell["reason"] = "cleared_conservative_thresholds_but_failed_bh_fdr"
            rediagnosis = _diagnose_cost_gate_escape(
                outcome_count=int(cell.get("outcome_count") or 0),
                avg_net_bps=cell.get("avg_net_bps"),
                avg_gross_bps=cell.get("avg_gross_bps"),
                net_positive_pct=cell.get("net_positive_pct"),
                review_candidate=False,
                cfg=cfg,
            )
            cell.update(rediagnosis)


def _apply_overlay(row: dict[str, Any], overlay: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """P1-2c:legacy_optimistic row 有 overlay 時，用保守成本覆蓋計算(不改原 ledger)。

    僅覆蓋 realized_net_bps/cost_bps 並打上 conservative version 標記;無 overlay 的
    legacy row 保持 legacy_optimistic_v0，由 cell 級 legacy 判準攔候選。
    """
    if not overlay or _str(row.get("cost_model_version")):
        return row
    hit = overlay.get(_str(row.get("attempt_id")))
    if not hit:
        return row
    patched = dict(row)
    patched["realized_net_bps"] = hit.get("realized_net_bps_conservative")
    patched["cost_bps"] = hit.get("cost_bps_conservative")
    patched["cost_model_version"] = hit.get("cost_model_version") or "conservative_v1"
    patched["cost_model_source"] = hit.get("cost_model_source")
    patched["cost_backfilled_by_overlay"] = True
    return patched


def build_blocked_signal_outcome_review(
    ledger_rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: BlockedOutcomeReviewConfig | None = None,
    overlay: dict[str, dict[str, Any]] | None = None,
    edge_estimates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a conservative scorecard from blocked-signal outcome rows.

    overlay: P1-2c 回填 overlay(attempt_id → 保守成本重算)，覆蓋 legacy 樂觀成本 row。
    edge_estimates: F1 fix(c) realized 矛盾標記所需的 side-cell realized EV/n(strategy::symbol)。
    """
    cfg = cfg or BlockedOutcomeReviewConfig()
    validate_blocked_outcome_review_config(cfg)
    overlay = overlay or {}
    edge_estimates = edge_estimates or {}
    generated_at = (now_utc or _utc_now()).astimezone(dt.timezone.utc)

    grouped: dict[str, list[dict[str, Any]]] = {}
    censored_grouped: dict[str, int] = {}
    invalid_outcome_row_count = 0
    for raw_row in ledger_rows:
        if _str(raw_row.get("record_type")) != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
            continue
        side_cell_key = _str(raw_row.get("side_cell_key"))
        if not side_cell_key:
            invalid_outcome_row_count += 1
            continue
        # F7:censored row 保留分母資訊但不進 nets/檢定。realized_net_bps 缺失但
        # censored=true 屬合法(觀測斷供)，計入 censored_count；非 censored 且無 net 才算畸形。
        if raw_row.get("censored") is True:
            censored_grouped[side_cell_key] = censored_grouped.get(side_cell_key, 0) + 1
            grouped.setdefault(side_cell_key, [])
            continue
        row = _apply_overlay(raw_row, overlay)
        net_bps = _float(row.get("realized_net_bps"))
        if net_bps is None:
            invalid_outcome_row_count += 1
            continue
        grouped.setdefault(side_cell_key, []).append(row)

    side_cells = [
        _review_side_cell_rows(
            key,
            rows,
            cfg=cfg,
            censored_count=censored_grouped.get(key, 0),
            edge_estimates=edge_estimates,
        )
        for key, rows in sorted(grouped.items())
    ]
    # P2-8(b):候選面 BH-FDR(q=cfg.fdr_q)。對每個 n≥min 的 cell 單側 t-test p，
    # step-up 通過集決定 bh_pass；review_candidate 資格再加 BH pass 一條(fail-closed)。
    _apply_bh_fdr(side_cells, cfg=cfg)
    side_cells = sorted(
        side_cells,
        key=lambda row: (
            0 if row["review_candidate"] else 1,
            -float(row.get("wrongful_block_score") or 0.0),
            -int(row.get("outcome_count") or 0),
            -float(row.get("avg_net_bps") or -10_000.0),
            row["side_cell_key"],
        ),
    )
    candidate_rank = 0
    for rank, row in enumerate(side_cells, start=1):
        row["review_rank"] = rank
        if row["review_candidate"]:
            candidate_rank += 1
            row["bounded_demo_probe_review_rank"] = candidate_rank
        else:
            row["bounded_demo_probe_review_rank"] = None

    # P2-8(a):K 登記(無條件)。horizon 維度納入同一 family(m=cells×horizons)。
    horizon_set = {
        horizon
        for rows in grouped.values()
        for row in rows
        for horizon in (_int(row.get("horizon_minutes"), default=0),)
        if horizon > 0
    }
    n_horizons = len(horizon_set) or 1
    selection_universe = {
        "n_side_cells": len(side_cells),
        "n_horizons": n_horizons,
        "k_effective": len(side_cells) * n_horizons,
        "selection_metric": "wrongful_block_score",
        "fdr_q": cfg.fdr_q,
    }
    # P2-8(c):headline sign-flip selection test。以 min_outcomes 以上的 cell nets
    # 建 null，p_selection ≥ 0.05 時 best 數字禁以「edge/cushion 證據」語言呈現。
    eligible_nets = [
        [float(_float(r.get("realized_net_bps"))) for r in rows if _float(r.get("realized_net_bps")) is not None]
        for rows in grouped.values()
        if len([r for r in rows if _float(r.get("realized_net_bps")) is not None])
        >= cfg.min_outcomes_per_side_cell
    ]
    eligible_nets = [c for c in eligible_nets if c]
    signflip = sign_flip_selection_p_value(eligible_nets, b=cfg.sign_flip_b)
    pooled_std = None
    all_nets = [v for c in eligible_nets for v in c]
    if len(all_nets) >= 2:
        pooled_mean = sum(all_nets) / len(all_nets)
        pooled_std = math.sqrt(
            sum((v - pooled_mean) ** 2 for v in all_nets) / (len(all_nets) - 1)
        )
    mean_n = (
        sum(len(c) for c in eligible_nets) / len(eligible_nets) if eligible_nets else 0.0
    )
    headline_selection = {
        "method": "sign_flip",
        "p_selection": signflip["p_selection"],
        "observed_best_avg_net_bps": signflip["observed_best"],
        "b": signflip["b"],
        "k": signflip["k"],
        "expected_max_under_null_bps": (
            expected_max_under_null_bps(pooled_std or 0.0, signflip["k"], mean_n)
            if pooled_std is not None
            else None
        ),
        "headline_edge_language_allowed": bool(signflip["p_selection"] < 0.05),
    }

    candidate_count = sum(1 for row in side_cells if row["review_candidate"])
    insufficient_count = sum(
        1 for row in side_cells
        if row["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    )
    blocked_count = sum(
        1 for row in side_cells
        if row["status"] == "KEEP_COST_GATE_BLOCKED"
    )
    outcome_count = sum(int(row.get("outcome_count") or 0) for row in side_cells)
    positive_count = sum(int(row.get("positive_outcome_count") or 0) for row in side_cells)
    avg_net = (
        sum(
            float(row["avg_net_bps"]) * int(row["outcome_count"])
            for row in side_cells
            if row.get("avg_net_bps") is not None
        )
        / outcome_count
        if outcome_count
        else None
    )
    net_positive_pct = (positive_count / outcome_count * 100.0) if outcome_count else None
    top_side_cell = side_cells[0] if side_cells else None
    top_candidate = next(
        (row for row in side_cells if row["review_candidate"]),
        None,
    )
    max_wrongful_block_score = (
        max(float(row.get("wrongful_block_score") or 0.0) for row in side_cells)
        if side_cells
        else 0.0
    )
    diagnosis_counts: dict[str, int] = {}
    recommendation_counts: dict[str, int] = {}
    false_negative_candidate_count = 0
    edge_amplification_required_side_cell_count = 0
    candidacy_flipped_by_cost_model_count = 0
    realized_contradiction_count = 0
    observation_gap_suspect_count = 0
    packet_cost_model_version_counts: dict[str, int] = {}
    for row in side_cells:
        if row.get("candidacy_flipped_by_cost_model") is True:
            candidacy_flipped_by_cost_model_count += 1
        if row.get("realized_contradiction") is True:
            realized_contradiction_count += 1
        if row.get("observation_gap_suspect") is True:
            observation_gap_suspect_count += 1
        for version, count in (row.get("cost_model_version_counts") or {}).items():
            packet_cost_model_version_counts[version] = (
                packet_cost_model_version_counts.get(version, 0) + count
            )
        diagnosis = _str(row.get("learning_diagnosis"))
        recommendation = _str(row.get("cost_gate_escape_recommendation"))
        if diagnosis:
            diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
        if recommendation:
            recommendation_counts[recommendation] = (
                recommendation_counts.get(recommendation, 0) + 1
            )
        if row.get("false_negative_candidate") is True:
            false_negative_candidate_count += 1
        if row.get("edge_amplification_required") is True:
            edge_amplification_required_side_cell_count += 1

    if outcome_count == 0:
        status = "NO_BLOCKED_SIGNAL_OUTCOMES"
        reason = "blocked_signal_outcome_rows_missing"
        next_trigger = "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
    elif candidate_count > 0:
        status = "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
        reason = "one_or_more_blocked_side_cells_clear_review_thresholds"
        next_trigger = "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    elif insufficient_count > 0:
        status = "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
        reason = "blocked_signal_outcome_sample_below_review_threshold"
        next_trigger = "continue_recording_and_refreshing_blocked_signal_outcomes"
    else:
        status = "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
        reason = "reviewed_blocked_side_cells_do_not_clear_thresholds"
        next_trigger = "keep_cost_gate_blocked_for_reviewed_side_cells"

    return {
        "schema_version": BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION,
        "record_type": BLOCKED_OUTCOME_REVIEW_RECORD_TYPE,
        "generated_at_utc": generated_at.isoformat(),
        "status": status,
        "reason": reason,
        "next_trigger": next_trigger,
        "side_cell_count": len(side_cells),
        "review_candidate_side_cell_count": candidate_count,
        "insufficient_sample_side_cell_count": insufficient_count,
        "keep_blocked_side_cell_count": blocked_count,
        "blocked_signal_outcome_count": outcome_count,
        "blocked_signal_positive_outcome_count": positive_count,
        "invalid_outcome_row_count": invalid_outcome_row_count,
        "avg_blocked_signal_outcome_net_bps": avg_net,
        "blocked_signal_net_positive_pct": net_positive_pct,
        "max_wrongful_block_score": max_wrongful_block_score,
        "top_side_cell_key": top_side_cell.get("side_cell_key") if top_side_cell else None,
        "top_side_cell_status": top_side_cell.get("status") if top_side_cell else None,
        "top_side_cell_learning_diagnosis": (
            top_side_cell.get("learning_diagnosis") if top_side_cell else None
        ),
        "top_side_cell_cost_gate_escape_recommendation": (
            top_side_cell.get("cost_gate_escape_recommendation")
            if top_side_cell
            else None
        ),
        "top_side_cell_wrongful_block_score": (
            top_side_cell.get("wrongful_block_score") if top_side_cell else None
        ),
        "top_side_cell_net_cost_cushion_bps": (
            top_side_cell.get("net_cost_cushion_bps") if top_side_cell else None
        ),
        "top_review_candidate_side_cell_key": (
            top_candidate.get("side_cell_key") if top_candidate else None
        ),
        "top_review_candidate_learning_diagnosis": (
            top_candidate.get("learning_diagnosis") if top_candidate else None
        ),
        "top_review_candidate_cost_gate_escape_recommendation": (
            top_candidate.get("cost_gate_escape_recommendation")
            if top_candidate
            else None
        ),
        "top_review_candidate_wrongful_block_score": (
            top_candidate.get("wrongful_block_score") if top_candidate else None
        ),
        "top_review_candidate_net_cost_cushion_bps": (
            top_candidate.get("net_cost_cushion_bps") if top_candidate else None
        ),
        "thresholds": {
            "min_outcomes_per_side_cell": cfg.min_outcomes_per_side_cell,
            "min_avg_net_bps": cfg.min_avg_net_bps,
            "min_net_positive_pct": cfg.min_net_positive_pct,
        },
        "diagnosis_counts": {
            key: diagnosis_counts[key] for key in sorted(diagnosis_counts)
        },
        "cost_gate_escape_recommendation_counts": {
            key: recommendation_counts[key]
            for key in sorted(recommendation_counts)
        },
        "false_negative_candidate_count": false_negative_candidate_count,
        "edge_amplification_required_side_cell_count": (
            edge_amplification_required_side_cell_count
        ),
        "selection_universe": selection_universe,
        "headline_selection": headline_selection,
        "candidacy_flipped_by_cost_model_count": candidacy_flipped_by_cost_model_count,
        "realized_contradiction_side_cell_count": realized_contradiction_count,
        "observation_gap_suspect_side_cell_count": observation_gap_suspect_count,
        "cost_model_version_counts": {
            key: packet_cost_model_version_counts[key]
            for key in sorted(packet_cost_model_version_counts)
        },
        "top_side_cells": side_cells[:16],
        "promotion_evidence": False,
        "order_authority": "NOT_GRANTED",
        "main_cost_gate_adjustment": "NONE",
        "boundary": (
            "blocked outcome review artifact only; proposes operator review at "
            "most; no PG, Bybit, order, config, risk, auth, runtime mutation, "
            "or main Cost Gate lowering"
        ),
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-outcomes-per-side-cell", type=int, default=3)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--min-net-positive-pct", type=float, default=60.0)
    parser.add_argument("--fdr-q", type=float, default=0.10)
    parser.add_argument("--sign-flip-b", type=int, default=1000)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = BlockedOutcomeReviewConfig(
        min_outcomes_per_side_cell=args.min_outcomes_per_side_cell,
        min_avg_net_bps=args.min_avg_net_bps,
        min_net_positive_pct=args.min_net_positive_pct,
        fdr_q=args.fdr_q,
        sign_flip_b=args.sign_flip_b,
    )
    validate_blocked_outcome_review_config(cfg)
    scorecard = build_blocked_signal_outcome_review(
        read_jsonl_ledger(args.ledger),
        cfg=cfg,
    )
    if args.output:
        _write_json(args.output, scorecard)
    if args.print_json or not args.output:
        print(json.dumps(scorecard, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""FlashDip shallow-K retune screen (read-only offline research).

This script answers the question raised by live touchability evidence:

  Current K15 FlashDip orders are structurally too deep to touch in quiet
  windows, while the read-only K ladder says K2-K6 would have touched some
  recent orders. Touchability is not profitability. This screen evaluates
  whether K2-K6 have historical edge after the same cost, tail, clustering,
  fixed-notional sizing, and OOS checks used by the existing
  tail_dislocation_meanrev research line.

Hard boundary:
  - DB access is read-only through the sibling screen.py connector.
  - Bybit private/trading/auth APIs are not used.
  - No strategy parameter, risk, order, or runtime state is changed.
  - Output is a research artifact only. A PASS here is a candidate for QC/MIT
    review, not live promotion proof.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from typing import Any, Iterable, Optional

import screen as base
import survival_safe as surv
import extend_history as ext
import prepilot_gates as gates

SHALLOW_RETUNE_VERSION = "tail_dislocation_meanrev.shallow_retune_screen.v0.1"

DEFAULT_CANDIDATE_K_GRID = (0.02, 0.03, 0.04, 0.05, 0.06)
DEFAULT_REFERENCE_K_GRID = (0.10, 0.15)
DEFAULT_HOLD_GRID = (3,)
DEFAULT_CAP_GRID: tuple[Optional[int], ...] = (3,)
DEFAULT_NOTIONAL_GRID = (0.03,)

DEFAULT_MAX_RESEARCH_NOTIONAL_FRAC = 0.03
DEFAULT_BOOTSTRAP_N = 1000
MIN_BOOT_T = 2.0


def _data_root() -> str:
    return os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw")


def _stable_seed(*parts: Any) -> int:
    blob = "|".join(str(p) for p in parts).encode("utf-8")
    return int(hashlib.sha256(blob).hexdigest()[:8], 16)


def _safe_float(x: Any) -> Optional[float]:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _ci_excludes_zero(ci: Any) -> bool:
    if not isinstance(ci, (list, tuple)) or len(ci) < 2:
        return False
    lo = _safe_float(ci[0])
    hi = _safe_float(ci[1])
    if lo is None or hi is None:
        return False
    return (lo > 0.0) or (hi < 0.0)


def _label_cap(cap: Optional[int]) -> str | int:
    return cap if cap is not None else "unlimited"


def _parse_float_csv(raw: str, *, scale: float = 1.0) -> tuple[float, ...]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        vals.append(float(part) * scale)
    if not vals:
        raise ValueError(f"empty numeric CSV: {raw!r}")
    return tuple(vals)


def _parse_int_csv(raw: str) -> tuple[int, ...]:
    vals = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        vals.append(int(part))
    if not vals:
        raise ValueError(f"empty integer CSV: {raw!r}")
    return tuple(vals)


def _parse_cap_csv(raw: str) -> tuple[Optional[int], ...]:
    vals: list[Optional[int]] = []
    for part in raw.split(","):
        part = part.strip().lower()
        if not part:
            continue
        if part in {"none", "unlimited", "inf", "all"}:
            vals.append(None)
        else:
            vals.append(int(part))
    if not vals:
        raise ValueError(f"empty cap CSV: {raw!r}")
    return tuple(vals)


def _latest_json_line(path: str) -> tuple[Optional[dict[str, Any]], Optional[str]]:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            lines = [ln.strip() for ln in fh if ln.strip()]
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"read_error:{exc}"
    for line in reversed(lines):
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj, None
    return None, "no_json_line"


def _day_clustered_significance(
    events: list[dict[str, Any]],
    *,
    ret_key: str,
    seed: int,
    bootstrap_n: int,
) -> dict[str, Any]:
    by_day: dict[str, list[float]] = {}
    for e in events:
        r = e.get(ret_key)
        if r is not None:
            by_day.setdefault(e["entry_date"], []).append(r)
    day_means = [sum(v) / len(v) for v in by_day.values()]
    n_days = len(day_means)
    if n_days < 3:
        return {"n_distinct_days": n_days, "note": "insufficient_episodes"}

    mean_day = sum(day_means) / n_days
    sd_day = base._stddev(day_means)
    naive_day_t = (mean_day / (sd_day / math.sqrt(n_days))) if (sd_day and sd_day > 0) else None
    boot1 = base._block_bootstrap_tstat(day_means, block_len=1, n_boot=bootstrap_n, seed=seed)
    boot5 = (
        base._block_bootstrap_tstat(
            day_means,
            block_len=min(5, n_days - 1),
            n_boot=bootstrap_n,
            seed=seed + 1,
        )
        if n_days >= 6
        else {"boot_t": None}
    )

    per_trade = [e[ret_key] for e in events if e.get(ret_key) is not None]
    sd_pt = base._stddev(per_trade)
    naive_pertrade_t = (
        base._mean(per_trade) / (sd_pt / math.sqrt(len(per_trade)))
        if (sd_pt and sd_pt > 0 and per_trade)
        else None
    )
    return {
        "n_per_trade": len(per_trade),
        "n_distinct_days": n_days,
        "mean_day_return": mean_day,
        "naive_pertrade_t": naive_pertrade_t,
        "naive_day_clustered_t": naive_day_t,
        "block_bootstrap_day_b1": boot1,
        "block_bootstrap_day_b5": boot5,
        "bootstrap_n": bootstrap_n,
    }


def _segment_metrics(
    events: list[dict[str, Any]],
    *,
    cap: Optional[int],
    notional_frac: float,
    lo: Optional[str],
    hi: Optional[str],
    seed_tag: str,
    bootstrap_n: int,
) -> dict[str, Any]:
    seg_events = ext._filter_events_by_date(events, lo=lo, hi=hi)
    kept = surv.apply_concurrency_cap(seg_events, cap=cap)["kept"]
    if not kept:
        return {"n_kept": 0}
    dcs = _day_clustered_significance(
        kept,
        ret_key="net_taker",
        seed=_stable_seed("shallow_retune", seed_tag, cap, notional_frac, lo or "", hi or ""),
        bootstrap_n=bootstrap_n,
    )
    b1 = dcs.get("block_bootstrap_day_b1", {})
    fn = ext.fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=notional_frac)
    ci = b1.get("ci95")
    boot_t = b1.get("boot_t")
    mdd = fn.get("max_drawdown")
    return {
        "n_kept": len(kept),
        "n_distinct_days": dcs.get("n_distinct_days"),
        "mean_net_taker_per_trade": base._mean([e["net_taker"] for e in kept]),
        "day_clustered_boot_t": boot_t,
        "day_clustered_ci95": ci,
        "day_clustered_ci_excludes_zero": _ci_excludes_zero(ci),
        "fixed_notional_maxdd": mdd,
        "fixed_notional_annret": fn.get("annualized_return"),
        "fixed_notional_sharpe": fn.get("sharpe_annualized"),
        "fixed_notional_worst_trade": fn.get("worst_single_trade"),
        "holds_segment_gate": bool(
            boot_t is not None
            and boot_t >= MIN_BOOT_T
            and _ci_excludes_zero(ci)
            and mdd is not None
            and mdd <= surv.SURVIVABLE_MAXDD
        ),
    }


def research_gate_status(
    cell: dict[str, Any],
    *,
    candidate_k_grid: Iterable[float],
    max_research_notional_frac: float,
) -> dict[str, Any]:
    """Return gate flags for a shallow-K research candidate.

    The gate is intentionally narrower than "best historical cell": it only
    applies to the live-touchability-motivated K2-K6 band and to notional that
    does not exceed the current pilot's <=3% sizing discipline.
    """
    k = float(cell["k"])
    candidate_ks = {round(float(x), 10) for x in candidate_k_grid}
    is_candidate_k = round(k, 10) in candidate_ks
    within_nf_cap = float(cell["notional_frac"]) <= max_research_notional_frac + 1e-12
    positive = bool(cell.get("positive_expectancy"))
    significant = bool(cell.get("day_clustered_significant"))
    survivable = bool(cell.get("survivable_maxdd"))
    full_pass = bool(is_candidate_k and within_nf_cap and positive and significant and survivable)
    reasons = []
    if not is_candidate_k:
        reasons.append("reference_k_not_shallow_candidate")
    if not within_nf_cap:
        reasons.append("notional_frac_above_research_cap")
    if not positive:
        reasons.append("non_positive_expectancy")
    if not significant:
        reasons.append("day_clustered_not_significant")
    if not survivable:
        reasons.append("maxdd_not_survivable")
    return {
        "is_candidate_k": is_candidate_k,
        "within_research_notional_cap": within_nf_cap,
        "positive_expectancy": positive,
        "day_clustered_significant": significant,
        "survivable_maxdd": survivable,
        "full_history_research_gate_pass": full_pass,
        "fail_reasons": reasons,
    }


def _evaluate_events_for_grid(
    events: list[dict[str, Any]],
    *,
    k: float,
    hold: int,
    cap_grid: tuple[Optional[int], ...],
    notional_grid: tuple[float, ...],
    candidate_k_grid: tuple[float, ...],
    max_research_notional_frac: float,
    bootstrap_n: int,
) -> list[dict[str, Any]]:
    cells: list[dict[str, Any]] = []
    n_events_raw = len(events)
    for cap in cap_grid:
        cap_res = surv.apply_concurrency_cap(events, cap=cap)
        kept = cap_res["kept"]
        if kept:
            dcs = _day_clustered_significance(
                kept,
                ret_key="net_taker",
                seed=_stable_seed("shallow_retune_full", k, hold, cap),
                bootstrap_n=bootstrap_n,
            )
            b1 = dcs.get("block_bootstrap_day_b1", {})
            ci = b1.get("ci95")
            boot_t = b1.get("boot_t")
            mean_net = base._mean([e["net_taker"] for e in kept])
            median_net = base._median([e["net_taker"] for e in kept])
            pct_positive = sum(1 for e in kept if e["net_taker"] > 0.0) / len(kept)
            crash_ev = [e for e in kept if ext._in_crash_window(e["entry_date"])]
            crash_returns = [e["net_taker"] for e in crash_ev if e.get("net_taker") is not None]
            dcs_summary = {
                "day_clustered_boot_t": boot_t,
                "day_clustered_ci95": ci,
                "day_clustered_ci_excludes_zero": _ci_excludes_zero(ci),
                "day_clustered_significant": bool(
                    boot_t is not None and boot_t >= MIN_BOOT_T and _ci_excludes_zero(ci)
                ),
                "naive_pertrade_t": dcs.get("naive_pertrade_t"),
                "naive_day_clustered_t": dcs.get("naive_day_clustered_t"),
                "n_distinct_days": dcs.get("n_distinct_days"),
            }
        else:
            mean_net = median_net = pct_positive = None
            crash_returns = []
            dcs_summary = {
                "day_clustered_boot_t": None,
                "day_clustered_ci95": [None, None],
                "day_clustered_ci_excludes_zero": False,
                "day_clustered_significant": False,
                "naive_pertrade_t": None,
                "naive_day_clustered_t": None,
                "n_distinct_days": 0,
            }
        for nf in notional_grid:
            fn = ext.fixed_notional_equity_curve(kept, ret_key="net_taker", notional_frac=nf)
            mdd = fn.get("max_drawdown")
            cell = {
                "strategy_family": "flash_dip_buy",
                "parameter_cell_id": f"K{int(round(k * 100))}_N{hold}_C{_label_cap(cap)}_nf{nf:g}",
                "k": k,
                "k_pct": k * 100.0,
                "hold": hold,
                "stop": None,
                "cap": _label_cap(cap),
                "notional_frac": nf,
                "n_events_raw": n_events_raw,
                "n_kept": len(kept),
                "n_dropped_by_cap": cap_res.get("n_dropped"),
                "max_concurrency_raw": cap_res.get("max_concurrency_raw"),
                "max_concurrency_capped": cap_res.get("max_concurrency_capped"),
                "mean_net_taker_per_trade": mean_net,
                "median_net_taker_per_trade": median_net,
                "pct_positive": pct_positive,
                "n_empirical_crash_window_fills": len(crash_returns),
                "empirical_crash_window_mean_net_taker": base._mean(crash_returns) if crash_returns else None,
                "empirical_crash_window_worst_net_taker": min(crash_returns) if crash_returns else None,
                "fixed_notional_maxdd": mdd,
                "fixed_notional_annret": fn.get("annualized_return"),
                "fixed_notional_sharpe": fn.get("sharpe_annualized"),
                "fixed_notional_total_return": fn.get("total_return"),
                "fixed_notional_final_equity": fn.get("final_equity"),
                "fixed_notional_cvar05_day": fn.get("cvar05_day_return"),
                "fixed_notional_worst_trade": fn.get("worst_single_trade"),
                "survivable_maxdd": bool(mdd is not None and mdd <= surv.SURVIVABLE_MAXDD),
                "positive_expectancy": bool(mean_net is not None and mean_net > 0.0),
                "sample_unit": "day_clustered_flash_dip_counterfactual",
                "evidence_boundary": "counterfactual_only_not_promotion_evidence",
                **dcs_summary,
            }
            cell["research_gate"] = research_gate_status(
                cell,
                candidate_k_grid=candidate_k_grid,
                max_research_notional_frac=max_research_notional_frac,
            )
            cells.append(cell)
    return cells


def _sort_cell_key(cell: dict[str, Any]) -> tuple[int, float, float, float]:
    gate = cell.get("research_gate", {})
    return (
        1 if gate.get("full_history_research_gate_pass") else 0,
        float(cell.get("fixed_notional_annret") or -999.0),
        float(cell.get("day_clustered_boot_t") or -999.0),
        -float(cell.get("fixed_notional_maxdd") or 999.0),
    )


def _select_finalists(grid: list[dict[str, Any]], *, max_finalists: int) -> list[dict[str, Any]]:
    candidates = [
        c for c in grid
        if c.get("research_gate", {}).get("is_candidate_k")
        and c.get("research_gate", {}).get("within_research_notional_cap")
        and c.get("n_kept", 0) > 0
    ]
    ranked = sorted(candidates, key=_sort_cell_key, reverse=True)
    return ranked[:max_finalists]


def _walk_forward_for_finalists(
    events_by_key: dict[tuple[float, int], list[dict[str, Any]]],
    finalists: list[dict[str, Any]],
    *,
    split_date: str,
    bootstrap_n: int,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for cell in finalists:
        cap = None if cell["cap"] == "unlimited" else int(cell["cap"])
        events = events_by_key[(cell["k"], cell["hold"])]
        early = _segment_metrics(
            events,
            cap=cap,
            notional_frac=float(cell["notional_frac"]),
            lo=None,
            hi=split_date,
            seed_tag=f"{cell['parameter_cell_id']}:early",
            bootstrap_n=bootstrap_n,
        )
        late = _segment_metrics(
            events,
            cap=cap,
            notional_frac=float(cell["notional_frac"]),
            lo=split_date,
            hi=None,
            seed_tag=f"{cell['parameter_cell_id']}:late",
            bootstrap_n=bootstrap_n,
        )
        out.append({
            "parameter_cell_id": cell["parameter_cell_id"],
            "config": {
                "k": cell["k"],
                "k_pct": cell["k_pct"],
                "hold": cell["hold"],
                "cap": cell["cap"],
                "notional_frac": cell["notional_frac"],
            },
            "split_date": split_date,
            "early_segment_before_split": early,
            "late_segment_from_split": late,
            "walk_forward_gate_pass": bool(
                early.get("holds_segment_gate") and late.get("holds_segment_gate")
            ),
        })
    return out


def _per_k_summary(grid: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for cell in grid:
        key = f"K{int(round(cell['k'] * 100))}"
        bucket = out.setdefault(key, {
            "k": cell["k"],
            "k_pct": cell["k_pct"],
            "n_cells": 0,
            "n_full_history_gate_pass": 0,
            "best_annret_cell": None,
            "best_research_gate_cell": None,
        })
        bucket["n_cells"] += 1
        if cell.get("research_gate", {}).get("full_history_research_gate_pass"):
            bucket["n_full_history_gate_pass"] += 1
            cur = bucket["best_research_gate_cell"]
            if cur is None or _sort_cell_key(cell) > _sort_cell_key(cur):
                bucket["best_research_gate_cell"] = cell
        cur2 = bucket["best_annret_cell"]
        if cur2 is None or float(cell.get("fixed_notional_annret") or -999.0) > float(cur2.get("fixed_notional_annret") or -999.0):
            bucket["best_annret_cell"] = cell
    return out


def _verdict(
    grid: list[dict[str, Any]],
    walk_forward: list[dict[str, Any]],
) -> dict[str, Any]:
    full_pass = [c for c in grid if c.get("research_gate", {}).get("full_history_research_gate_pass")]
    wf_pass_ids = {
        r["parameter_cell_id"] for r in walk_forward if r.get("walk_forward_gate_pass")
    }
    wf_pass = [c for c in full_pass if c["parameter_cell_id"] in wf_pass_ids]
    if wf_pass:
        status = "SHALLOW_RETUNE_RESEARCH_CANDIDATE"
        reason = "At least one K2-K6 cell passed full-history and two-sided walk-forward research gates."
    elif full_pass:
        status = "FULL_HISTORY_PASS_OOS_NOT_PROVEN"
        reason = "At least one K2-K6 cell passed full-history gates, but finalist walk-forward did not hold both ways."
    else:
        status = "NO_SHALLOW_RETUNE_EDGE"
        reason = "No K2-K6 cell passed positive-expectancy, day-clustered significance, survivable maxDD, and <=3% notional gates."
    best = sorted(wf_pass or full_pass or grid, key=_sort_cell_key, reverse=True)[:1]
    return {
        "status": status,
        "reason": reason,
        "best_cell": best[0] if best else None,
        "promotion_boundary": (
            "This artifact is counterfactual research only. It does not authorize live/demo "
            "parameter changes, restarts, order placement, or risk changes."
        ),
    }


def run_report_from_merged(
    merged: dict[str, list[dict[str, Any]]],
    funding: dict[str, dict[str, float]],
    btc_fwd: dict[tuple[int, str], float],
    btc_regime: dict[str, Optional[str]],
    meta: dict[str, Any],
    *,
    candidate_k_grid: tuple[float, ...] = DEFAULT_CANDIDATE_K_GRID,
    reference_k_grid: tuple[float, ...] = DEFAULT_REFERENCE_K_GRID,
    hold_grid: tuple[int, ...] = DEFAULT_HOLD_GRID,
    cap_grid: tuple[Optional[int], ...] = DEFAULT_CAP_GRID,
    notional_grid: tuple[float, ...] = DEFAULT_NOTIONAL_GRID,
    max_research_notional_frac: float = DEFAULT_MAX_RESEARCH_NOTIONAL_FRAC,
    split_date: str = ext.WF_SPLIT_DATE,
    max_finalists: int = 12,
    touchability_path: Optional[str] = None,
    bootstrap_n: int = DEFAULT_BOOTSTRAP_N,
) -> dict[str, Any]:
    all_k = tuple(dict.fromkeys(tuple(candidate_k_grid) + tuple(reference_k_grid)))
    grid: list[dict[str, Any]] = []
    events_by_key: dict[tuple[float, int], list[dict[str, Any]]] = {}
    for k in all_k:
        for hold in hold_grid:
            events = surv.build_events_stopped(
                merged,
                funding,
                btc_fwd,
                btc_regime,
                k=k,
                hold=hold,
                stop=None,
            )
            events_by_key[(k, hold)] = events
            grid.extend(_evaluate_events_for_grid(
                events,
                k=k,
                hold=hold,
                cap_grid=cap_grid,
                notional_grid=notional_grid,
                candidate_k_grid=candidate_k_grid,
                max_research_notional_frac=max_research_notional_frac,
                bootstrap_n=bootstrap_n,
            ))

    finalists = _select_finalists(grid, max_finalists=max_finalists)
    walk_forward = _walk_forward_for_finalists(
        events_by_key,
        finalists,
        split_date=split_date,
        bootstrap_n=bootstrap_n,
    )
    touch_path = touchability_path or os.path.join(_data_root(), "logs", "flash_dip_touchability.log")
    touch, touch_err = _latest_json_line(touch_path)
    runtime_context = {
        "path": touch_path,
        "source_ok": touch is not None,
        "source_error": touch_err,
        "latest": touch,
    }
    return {
        "version": SHALLOW_RETUNE_VERSION,
        "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "params": {
            "candidate_k_grid": list(candidate_k_grid),
            "candidate_k_pct_grid": [k * 100.0 for k in candidate_k_grid],
            "reference_k_grid": list(reference_k_grid),
            "hold_grid": list(hold_grid),
            "cap_grid": [_label_cap(c) for c in cap_grid],
            "notional_grid": list(notional_grid),
            "max_research_notional_frac": max_research_notional_frac,
            "split_date": split_date,
            "min_boot_t": MIN_BOOT_T,
            "bootstrap_n": bootstrap_n,
            "survivable_maxdd": surv.SURVIVABLE_MAXDD,
            "maker_fee_bps": base.MAKER_FEE_BPS,
            "taker_fee_bps": base.TAKER_FEE_BPS,
        },
        "data_meta": meta,
        "runtime_touchability_context": runtime_context,
        "per_k_summary": _per_k_summary(grid),
        "grid": grid,
        "finalists": finalists,
        "finalist_walk_forward": walk_forward,
        "verdict": _verdict(grid, walk_forward),
    }


def run_shallow_retune(conn, **kwargs: Any) -> dict[str, Any]:
    merged, funding, btc_fwd, btc_regime, meta = gates.build_merged_klines(conn)
    return run_report_from_merged(merged, funding, btc_fwd, btc_regime, meta, **kwargs)


def write_artifact(report: dict[str, Any], *, out_path: Optional[str]) -> str:
    if out_path is None:
        root = os.path.join(_data_root(), "research", "tail_dislocation_meanrev")
        os.makedirs(root, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_path = os.path.join(root, f"shallow_retune_screen_{stamp}.json")
    else:
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    blob = json.dumps(report, indent=2, sort_keys=True, default=str)
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(blob)
    sha = hashlib.sha256(blob.encode("utf-8")).hexdigest()
    with open(out_path + ".sha256", "w", encoding="utf-8") as fh:
        fh.write(sha + "  " + os.path.basename(out_path) + "\n")
    return out_path


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Read-only FlashDip shallow-K retune screen; writes a counterfactual research artifact."
    )
    ap.add_argument("--out", default=None)
    ap.add_argument("--k-pcts", default="2,3,4,5,6", help="candidate K values in percent")
    ap.add_argument("--reference-k-pcts", default="10,15", help="reference K values in percent")
    ap.add_argument("--holds", default="3")
    ap.add_argument("--caps", default="3")
    ap.add_argument("--notional-fracs", default="0.03")
    ap.add_argument("--max-research-notional-frac", type=float, default=DEFAULT_MAX_RESEARCH_NOTIONAL_FRAC)
    ap.add_argument("--split-date", default=ext.WF_SPLIT_DATE)
    ap.add_argument("--max-finalists", type=int, default=12)
    ap.add_argument("--bootstrap-n", type=int, default=DEFAULT_BOOTSTRAP_N)
    ap.add_argument("--touchability-path", default=None)
    args = ap.parse_args(argv)

    conn = base.connect_pg()
    try:
        report = run_shallow_retune(
            conn,
            candidate_k_grid=_parse_float_csv(args.k_pcts, scale=0.01),
            reference_k_grid=_parse_float_csv(args.reference_k_pcts, scale=0.01),
            hold_grid=_parse_int_csv(args.holds),
            cap_grid=_parse_cap_csv(args.caps),
            notional_grid=_parse_float_csv(args.notional_fracs),
            max_research_notional_frac=args.max_research_notional_frac,
            split_date=args.split_date,
            max_finalists=args.max_finalists,
            bootstrap_n=args.bootstrap_n,
            touchability_path=args.touchability_path,
        )
    finally:
        conn.close()

    out = write_artifact(report, out_path=args.out)
    verdict = report["verdict"]
    print(f"[{SHALLOW_RETUNE_VERSION}] artifact -> {out}")
    print(f"verdict={verdict['status']} reason={verdict['reason']}")
    meta = report["data_meta"]
    print(
        f"data: symbols={meta.get('n_symbols')} rest_cached={meta.get('n_rest_cached')} "
        f"range={meta.get('global_first')}..{meta.get('global_last')} span_years={meta.get('span_years')}"
    )
    print("per-K full-history gate passes:")
    for key, val in sorted(report["per_k_summary"].items()):
        best = val.get("best_research_gate_cell")
        suffix = ""
        if best:
            suffix = (
                f" best={best['parameter_cell_id']} annret={best.get('fixed_notional_annret')} "
                f"maxdd={best.get('fixed_notional_maxdd')} boot_t={best.get('day_clustered_boot_t')}"
            )
        print(f"  {key}: {val['n_full_history_gate_pass']}/{val['n_cells']}{suffix}")
    wf_pass = [r for r in report["finalist_walk_forward"] if r.get("walk_forward_gate_pass")]
    print(f"walk_forward_pass_finalists={len(wf_pass)}/{len(report['finalist_walk_forward'])}")
    print("boundary=counterfactual_only_not_promotion_evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

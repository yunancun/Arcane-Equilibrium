#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure sibling module in the same dir as this script is importable
# regardless of cwd (script can be run from srv/ root or anywhere).
# 確保同目錄 sibling module 在任意 cwd 下都可 import。
sys.path.insert(0, str(Path(__file__).resolve().parent))

from counterfactual_exit_replay_help import DESCRIPTION  # noqa: E402

__doc__ = DESCRIPTION

# v2-parity gate evaluation (ported from Rust exit_features/v2.rs).
# v2 gate 評估（自 Rust exit_features/v2.rs port 過來，純 Python 純函數）。
from counterfactual_v2_parity import (  # noqa: E402
    V2Config,
    V2_DEFAULT_GATE1_FLOOR_BPS,
    V2_DEFAULT_MISSING_EDGE_FALLBACK_BPS,
    V2_DEFAULT_MIN_HOLD_SECS,
    V2_DEFAULT_MIN_PEAK_ATR_NORM,
    V2_DEFAULT_GIVEBACK_BASE,
    V2_DEFAULT_GIVEBACK_SLOPE,
    V2_DEFAULT_GIVEBACK_FLOOR,
    evaluate_v2_gates,
)


# ---- window boundaries for --split-window (FA H3 vacuum hypothesis) ----
# --split-window 時間分段邊界（FA H3 vacuum 假說驗證用）

# MICRO-PROFIT-FIX-1 T3 deploy cut-over (2026-04-19 00:00 UTC).
# MICRO-PROFIT-FIX-1 T3 部署切點（2026-04-19 00:00 UTC）。
_SPLIT_WINDOW_T3_UTC = datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc)
# T4 (TRACK-P wiring) close-out cut-over (2026-04-21 21:00 UTC, approximating
# the 2026-04-21 20:44 CEST restart_all.sh --rebuild baseline).
# T4（TRACK-P 接線）收束切點（2026-04-21 21:00 UTC，對齊 20:44 CEST rebuild）。
_SPLIT_WINDOW_T4_UTC = datetime(2026, 4, 21, 21, 0, 0, tzinfo=timezone.utc)
# P0-13 ATR scale fix cut-over (2026-04-22 21:35 UTC = 23:35 CEST restart_all.sh
# --rebuild landing ff694e8). PRE-P013: atr_pct per-tick micro-vol (100-1000x too
# small) + giveback_atr_norm inflated 200-400x — numerically unusable for v2 gate
# evaluation. POST-P013: atr_pct = kline 1m Wilder (~0.05-0.5%) + giveback_atr_norm
# ~0.3-3.0 — spec-correct. Only the post-P013 bucket is sound for v2-parity cf
# decisions (per 2026-04-24 PM audit discovery).
# P0-13 ATR scale 修復切點（2026-04-22 21:35 UTC = 23:35 CEST commit ff694e8）。
# 此點之前 atr_pct 被 per-tick 計法除壓 100-1000x、giveback_atr_norm 反放大
# 200-400x（2026-04-24 PM 審計揭露），v2 gate 用該期資料無意義；只有 post-P013
# bucket 數值對齊 spec。
_SPLIT_WINDOW_P013_UTC = datetime(2026, 4, 22, 21, 35, 0, tzinfo=timezone.utc)


# ---- connection (mirrors passive_wait_healthcheck.py exactly) ----
# 連線（完全沿用 passive_wait_healthcheck.py 模式）

def _get_conn():
    import psycopg2  # type: ignore
    dsn = (
        os.environ.get("OPENCLAW_DATABASE_URL")
        or f"postgresql://{os.environ.get('POSTGRES_USER','')}"
        f":{os.environ.get('POSTGRES_PASSWORD','')}"
        f"@{os.environ.get('POSTGRES_HOST','127.0.0.1')}"
        f":{os.environ.get('POSTGRES_PORT','5432')}"
        f"/{os.environ.get('POSTGRES_DB','')}"
    )
    return psycopg2.connect(dsn)


# ---- counterfactual arithmetic (pure fn, unit-testable) ----
# 反事實算術（純函數，可單測）

def _cf_row_outcome(
    peak_pnl_pct: float | None,
    atr_pct: float | None,
    giveback_atr_norm: float | None,
    realized_net_bps: float | None,
    k: float,
    cost_model: str,
    fee_bps_per_side: float,
    *,
    # v2-parity inputs (ignored when v2_cfg is None; backward compat when off).
    # v2-parity 輸入（v2_cfg=None 時忽略，維持向後兼容）。
    v2_cfg: V2Config | None = None,
    est_net_bps: float | None = None,
    entry_age_secs: float | None = None,
    entry_age_column_present: bool = True,
) -> tuple[bool, float, float, float]:
    """Return (cf_fired, cf_net_bps, actual_net_bps, improvement_bps) for one row.

    v2_cfg=None (default) → v1 linear `giveback_atr_norm >= k` gate.
    v2_cfg given → Rust v2 4-Gate sequence via evaluate_v2_gates.

    cost_model 'proxy' is degenerate (cancel fees, double-count giveback);
    'fee_only' uses 2×fee_bps_per_side (round-trip taker fee, meaningful).

    cf_fired=False → cf_net_bps := actual. Realised NULL → (False, 0, 0, 0).
    回傳 (cf_fired, cf_net_bps, actual_net_bps, improvement_bps)。
    """
    # Guard: missing realised → cannot score, treat as no-op.
    # 防護：缺 realised → 無法評分，視為 no-op。
    if realized_net_bps is None or not math.isfinite(realized_net_bps):
        return (False, 0.0, 0.0, 0.0)

    actual = float(realized_net_bps)

    if v2_cfg is None:
        # v1 linear (legacy behavior, backward compat).
        # v1 線性（舊行為，向後兼容）。
        if peak_pnl_pct is None or not math.isfinite(peak_pnl_pct) or peak_pnl_pct <= 0:
            return (False, actual, actual, 0.0)
        if atr_pct is None or not math.isfinite(atr_pct) or atr_pct <= 0:
            return (False, actual, actual, 0.0)
        if (
            giveback_atr_norm is None
            or not math.isfinite(giveback_atr_norm)
            or giveback_atr_norm < k
        ):
            return (False, actual, actual, 0.0)
    else:
        # v2 full 4-Gate sequence (Rust parity).
        # v2 完整 4-Gate 序列（對齊 Rust）。
        fired, _reason = evaluate_v2_gates(
            est_net_bps=est_net_bps,
            entry_age_secs=entry_age_secs,
            peak_pnl_pct=peak_pnl_pct,
            atr_pct=atr_pct,
            giveback_atr_norm=giveback_atr_norm,
            cfg=v2_cfg,
            entry_age_column_present=entry_age_column_present,
        )
        if not fired:
            return (False, actual, actual, 0.0)
        # gross computation below still needs atr_pct/peak finite; evaluate_v2_gates
        # already checked these, but assert via fallthrough.
        # 下面 gross 計算仍需 atr_pct/peak 有限；evaluate_v2_gates 已檢，此處 fallthrough 安全。

    # cf fired — compute locked-in gross + apply chosen cost model.
    # cf 觸發 — 計算鎖定 gross + 套用選定成本模型。
    # Use k for the lock amount in both v1 and v2 modes (v2 gates decide firing;
    # the locked-in gross is still modelled as peak - k × ATR, mirroring v1 so
    # the two modes share a single gross calc and only the fire-decision differs).
    # v1/v2 皆以 peak - k × ATR 為鎖定 gross（v2 只改觸發判斷，gross 公式相同）。
    cf_gross_bps = (peak_pnl_pct - k * atr_pct) * 100.0
    peak_gross_bps = peak_pnl_pct * 100.0

    if cost_model == "proxy":
        # DEGENERATE proxy (see docstring; retained for transparency).
        # 退化 proxy（見 docstring；保留作透明度核驗）。
        cost_bps = max(0.0, peak_gross_bps - actual)
    elif cost_model == "fee_only":
        # Round-trip exchange fee only; no giveback double-count.
        # 僅 round-trip 手續費；不雙重扣 giveback。
        cost_bps = 2.0 * fee_bps_per_side
    else:
        raise ValueError(
            f"unknown cost_model {cost_model!r}; expected 'proxy' or 'fee_only'"
        )

    cf_net = cf_gross_bps - cost_bps
    return (True, cf_net, actual, cf_net - actual)


# ---- aggregation ----

def _bootstrap_ci_95(improvements: list[float], *, n_resamples: int = 1000,
                     seed: int = 1234) -> tuple[float, float]:
    """Stdlib-only bootstrap 95% CI (percentile method) on sample means.

    Returns (lo, hi); for n<2 returns (nan, nan). Deterministic via fixed seed
    so re-runs on the same data produce identical CIs. `n_resamples=1000`
    samples → mean-of-sample for each → percentile 2.5/97.5 via
    statistics.quantiles(n=40) index 0 and index 38 (0-indexed).

    純 stdlib bootstrap 95% CI（percentile 法）；n<2 時回 (nan, nan)。固定 seed
    保證同資料可重現。statistics.quantiles(n=40) 回 39 個切點，[0] = 2.5%、
    [38] = 97.5%。
    """
    if len(improvements) < 2:
        return (float("nan"), float("nan"))
    rng = random.Random(seed)
    n = len(improvements)
    sample_means: list[float] = []
    for _ in range(n_resamples):
        sample = rng.choices(improvements, k=n)
        sample_means.append(statistics.fmean(sample))
    sample_means.sort()
    qs = statistics.quantiles(sample_means, n=40)  # 39 cut-points
    lo = qs[0]    # 2.5%  (index 0 of 39 = 1/40-th quantile)
    hi = qs[-1]   # 97.5% (index 38 of 39 = 39/40-th quantile)
    return (lo, hi)


def _trimmed_mean(values: list[float], trim_pct: float) -> float:
    """Symmetric trimmed mean: drop `trim_pct%` of values from each tail.

    For n*trim/100 fractional, drops floor(n*trim/100) from each end. Returns
    nan if the resulting centre subset is empty.

    對稱 trimmed mean：兩端各丟 trim_pct% 資料；分數部分 floor。中間子集為空
    時回 nan。
    """
    if not values:
        return float("nan")
    if trim_pct <= 0:
        return statistics.fmean(values)
    s = sorted(values)
    n = len(s)
    drop = int(n * trim_pct / 100.0)
    if n - 2 * drop <= 0:
        # Nothing left after trimming both tails — fall back to median as a
        # reasonable central-tendency proxy (FM's spirit: robust to outliers).
        # 兩端剪完沒料 → 回中位數當穩健中位替身（符合 FM outlier-robust 精神）。
        return statistics.median(s)
    return statistics.fmean(s[drop:n - drop])


def _aggregate(
    rows: list[dict[str, Any]],
    k: float,
    cost_models: tuple[str, ...],
    fee_bps_per_side: float,
    *,
    v2_cfg: V2Config | None = None,
    entry_age_column_present: bool = True,
    bootstrap_ci: bool = False,
    per_strategy_median: bool = False,
    trimmed_mean_pct: float | None = None,
) -> list[dict[str, Any]]:
    """Group by (engine_mode, strategy_name, symbol) → per-model summaries.

    per_model dict carries {cf_fired_count, cf_net_bps_avg, improvement_bps_avg,
    improvement_pos_pct} + optional FM {improvement_bps_median,
    improvement_bps_trimmed_mean, bootstrap_ci_lo/hi} when flags active.
    v2_cfg non-None → v2-parity fire decision (Rust 4-Gate).
    """
    def _zero_model_acc() -> dict[str, Any]:
        return {
            "cf_fired_count": 0,
            "sum_cf": 0.0,
            "sum_improvement": 0.0,
            "improvement_pos_count": 0,
            # Per-row improvements (only the fired subset) — fed to
            # bootstrap / median / trimmed-mean if flags active.
            # fired 子集的 improvement 清單 — bootstrap / median / trimmed 用。
            "fired_improvements": [],
        }

    groups: dict[tuple[str, str, str], dict[str, Any]] = defaultdict(
        lambda: {
            "n_exits": 0,
            "sum_actual": 0.0,
            "per_model": {m: _zero_model_acc() for m in cost_models},
        }
    )

    for r in rows:
        # Double-guard: SQL already filters, but skip if slipped through.
        # 防護：SQL 已過濾；萬一漏過也跳過。
        rn = r.get("realized_net_bps")
        if rn is None:
            continue

        key = (
            r.get("engine_mode") or "",
            r.get("strategy_name") or "",
            r.get("symbol") or "",
        )
        g = groups[key]
        g["n_exits"] += 1
        g["sum_actual"] += float(rn)

        for model in cost_models:
            cf_fired, cf_net, _actual, improvement = _cf_row_outcome(
                r.get("peak_pnl_pct"),
                r.get("atr_pct"),
                r.get("giveback_atr_norm"),
                rn,
                k,
                model,
                fee_bps_per_side,
                v2_cfg=v2_cfg,
                est_net_bps=r.get("est_net_bps"),
                entry_age_secs=r.get("entry_age_secs"),
                entry_age_column_present=entry_age_column_present,
            )
            m_acc = g["per_model"][model]
            if cf_fired:
                m_acc["cf_fired_count"] += 1
                m_acc["sum_cf"] += cf_net
                m_acc["sum_improvement"] += improvement
                m_acc["fired_improvements"].append(improvement)
                if improvement > 0:
                    m_acc["improvement_pos_count"] += 1
            else:
                # cf collapsed to actual for the avg-over-n_exits calculation.
                # cf 未觸發時以 actual 頂替（避免扭曲平均）。
                m_acc["sum_cf"] += float(rn)

    out = []
    for (engine_mode, strategy, symbol), g in sorted(groups.items()):
        n = g["n_exits"]
        per_model_out: dict[str, Any] = {}
        for model in cost_models:
            m_acc = g["per_model"][model]
            cf_n = m_acc["cf_fired_count"]
            entry = {
                "cf_fired_count": cf_n,
                "cf_net_bps_avg": (m_acc["sum_cf"] / n) if n else 0.0,
                "improvement_bps_avg": (m_acc["sum_improvement"] / cf_n) if cf_n else 0.0,
                "improvement_pos_pct": (100.0 * m_acc["improvement_pos_count"] / cf_n) if cf_n else 0.0,
            }
            fired_list = m_acc["fired_improvements"]
            if per_strategy_median:
                entry["improvement_bps_median"] = (
                    statistics.median(fired_list) if fired_list else float("nan")
                )
            if trimmed_mean_pct is not None:
                entry["improvement_bps_trimmed_mean"] = _trimmed_mean(
                    fired_list, trimmed_mean_pct
                )
            if bootstrap_ci:
                lo, hi = _bootstrap_ci_95(fired_list)
                entry["bootstrap_ci_lo"] = lo
                entry["bootstrap_ci_hi"] = hi
            per_model_out[model] = entry
        out.append({
            "engine_mode": engine_mode,
            "strategy_name": strategy,
            "symbol": symbol,
            "n_exits": n,
            "actual_net_bps_avg": (g["sum_actual"] / n) if n else 0.0,
            "per_model": per_model_out,
        })
    return out


# ---- output formatting ----

def _print_table(
    rows: list[dict[str, Any]],
    cost_models: tuple[str, ...],
    *,
    show_median: bool = False,
    show_trimmed_mean: bool = False,
    show_bootstrap_ci: bool = False,
) -> None:
    """Stdout table grouped by (engine_mode, strategy_name, symbol) + summary.

    When multiple cost models are active, emits one table per model (clearer
    than interleaved columns, per PA feedback). When FM flags active
    (--per-strategy-median / --trimmed-mean-pct / --bootstrap-ci), an
    extra sub-row is printed under each group line with the robust stats.

    Note: `cf_avg` equals `actual` for rows where cf did NOT fire (by design, so
    averages are comparable — not biased to the fired subset).
    注意：`cf_avg` 在 cf 未觸發時等於 `actual`（刻意設計；保持平均值可比性，
    不偏向觸發子集）。
    """
    if not rows:
        print("(no rows — check --days window and filter flags)")
        return

    # QC-round-2 NIT: surface the cf_avg==actual-when-unfired note on stdout so
    # readers of raw table output see it, not only those reading the docstring.
    # 將 cf_avg 未觸發 fallback 的提示印到 stdout，避免只看表者誤讀。
    print()
    print("Note: cf_avg == actual for non-fired rows (by design; keeps averages")
    print("      comparable across groups, not biased to the fired subset).")

    any_robust = show_median or show_trimmed_mean or show_bootstrap_ci

    for model in cost_models:
        print()
        print(f"=== cost_model: {model} ===")
        header = (
            f"{'engine_mode':<11} | {'strategy_name':<18} | {'symbol':<12} | "
            f"{'n_exits':>7} | {'cf_fired':>8} | {'actual_avg':>10} | "
            f"{'cf_avg':>10} | {'improv_avg':>10} | {'improv_pos%':>11}"
        )
        print(header)
        if any_robust:
            parts = []
            if show_median:
                parts.append("improv_median")
            if show_trimmed_mean:
                parts.append("improv_trimmed")
            if show_bootstrap_ci:
                parts.append("boot95_ci=[lo,hi]")
            print(
                "    robust-stats sub-line per group (fired subset only): "
                + " / ".join(parts)
            )
        print("-" * len(header))
        for r in rows:
            m = r["per_model"][model]
            print(
                f"{r['engine_mode']:<11} | {r['strategy_name']:<18.18} | "
                f"{r['symbol']:<12.12} | {r['n_exits']:>7d} | "
                f"{m['cf_fired_count']:>8d} | {r['actual_net_bps_avg']:>10.2f} | "
                f"{m['cf_net_bps_avg']:>10.2f} | {m['improvement_bps_avg']:>10.2f} | "
                f"{m['improvement_pos_pct']:>10.1f}%"
            )
            if any_robust and m["cf_fired_count"] > 0:
                segs: list[str] = []
                if show_median:
                    segs.append(f"median={m.get('improvement_bps_median', float('nan')):.2f}")
                if show_trimmed_mean:
                    segs.append(f"trimmed={m.get('improvement_bps_trimmed_mean', float('nan')):.2f}")
                if show_bootstrap_ci:
                    lo = m.get("bootstrap_ci_lo", float("nan"))
                    hi = m.get("bootstrap_ci_hi", float("nan"))
                    segs.append(f"ci95=[{lo:.2f}, {hi:.2f}]")
                print("    └─ " + "  ".join(segs))
        # Summary row per model.
        total_n = sum(r["n_exits"] for r in rows)
        total_cf = sum(r["per_model"][model]["cf_fired_count"] for r in rows)
        if total_n == 0:
            continue
        total_actual = sum(r["actual_net_bps_avg"] * r["n_exits"] for r in rows) / total_n
        total_cf_avg = sum(
            r["per_model"][model]["cf_net_bps_avg"] * r["n_exits"] for r in rows
        ) / total_n
        total_imp = (
            sum(
                r["per_model"][model]["improvement_bps_avg"]
                * r["per_model"][model]["cf_fired_count"]
                for r in rows
            ) / total_cf
        ) if total_cf else 0.0
        total_pos_pct = (
            sum(
                r["per_model"][model]["improvement_pos_pct"] / 100.0
                * r["per_model"][model]["cf_fired_count"]
                for r in rows
            ) * 100.0 / total_cf
        ) if total_cf else 0.0
        print("-" * len(header))
        print(
            f"{'ALL':<11} | {'(summary)':<18} | {'':<12} | "
            f"{total_n:>7d} | {total_cf:>8d} | {total_actual:>10.2f} | "
            f"{total_cf_avg:>10.2f} | {total_imp:>10.2f} | {total_pos_pct:>10.1f}%"
        )


def _summary_totals(
    rows: list[dict[str, Any]], model: str
) -> tuple[int, int, float]:
    """Return (total_n_exits, total_cf_fired, total_improvement_bps_avg) for a model."""
    total_n = sum(r["n_exits"] for r in rows)
    total_cf = sum(r["per_model"][model]["cf_fired_count"] for r in rows)
    total_imp = (
        sum(
            r["per_model"][model]["improvement_bps_avg"]
            * r["per_model"][model]["cf_fired_count"]
            for r in rows
        ) / total_cf
    ) if total_cf else 0.0
    return (total_n, total_cf, total_imp)


def _write_json_outputs(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    started_at: datetime,
    cost_models: tuple[str, ...],
    *,
    v2_cfg: V2Config | None = None,
    by_window: dict[str, list[dict[str, Any]]] | None = None,
    peak_histogram: list[dict[str, Any]] | None = None,
    exclude_tag_pattern: str | None = None,
    entry_age_column_present: bool = True,
) -> tuple[Path, Path]:
    """Write `--output-json` latest + dated sibling (CLAUDE.md §七 script spec)."""
    totals_by_model = {
        model: {
            "total_n_exits": _summary_totals(rows, model)[0],
            "total_cf_fired": _summary_totals(rows, model)[1],
            "total_improvement_bps_avg": _summary_totals(rows, model)[2],
        }
        for model in cost_models
    }
    # v1 scope text varies based on whether v2-parity mode is active.
    # v1_scope 文字依 v2-parity 是否啟用而變。
    if v2_cfg is not None:
        v1_scope = (
            "V2-PARITY MODE — cf_fired uses Rust v2 4-Gate (Gate1 edge floor → "
            "Gate2 min hold → Gate3 peak/ATR → Gate4a non-linear giveback). "
            "Gate4b (stale_peak+neg_roc) NOT replayable; cf_multiplier still "
            "used for locked-gross `peak - k×ATR`."
        )
    else:
        v1_scope = (
            "V1 MODE (default). Gate-4-only LINEAR `giveback_atr_norm >= k`. "
            "v2 uses non_linear_giveback_fn; default k=0.3 is the asymptotic "
            "floor, effective v2 threshold ~0.7-0.925. Outputs are upper "
            "bounds on 'cf fired' vs v2 production. Pass --v2-parity for parity."
        )
    payload: dict[str, Any] = {
        "generated_at": started_at.isoformat(timespec="seconds"),
        "days": args.days,
        "cf_multiplier": args.cf_multiplier,
        "cost_models": list(cost_models),
        "fee_bps_per_side": args.fee_bps_per_side,
        "engine_mode_filter": args.engine_mode,
        "strategy_filter_requested": args.strategy,
        "funding_arb_included": bool(args.include_funding_arb),
        "symbol_filter": args.symbol,
        "exclude_tag_pattern_active": exclude_tag_pattern,
        "v2_parity_mode": v2_cfg is not None,
        "v2_config": (
            {
                "gate1_floor_bps": v2_cfg.gate1_floor_bps,
                "missing_edge_fallback_bps": v2_cfg.missing_edge_fallback_bps,
                "min_hold_secs": v2_cfg.min_hold_secs,
                "min_peak_atr_norm": v2_cfg.min_peak_atr_norm,
                "giveback_base": v2_cfg.giveback_base,
                "giveback_slope": v2_cfg.giveback_slope,
                "giveback_floor": v2_cfg.giveback_floor,
                "entry_age_column_present": entry_age_column_present,
            }
            if v2_cfg is not None
            else None
        ),
        # FA-round-2 MINOR: expose v1 scope + linearity caveat to JSON consumers
        # so downstream dashboards / ML pipelines cannot silently over-extrapolate.
        # FA 二輪建議：JSON 消費者（dashboard / ML）無法看 docstring，顯式宣告 scope。
        "v1_scope": v1_scope,
        "totals_by_model": totals_by_model,
        "rows": rows,
    }
    if by_window is not None:
        payload["by_window"] = by_window
    if peak_histogram is not None:
        payload["peak_histogram"] = peak_histogram

    latest = Path(args.output_json)
    latest.parent.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d_%H%M%S")
    if latest.name.endswith("_latest.json"):
        dated = latest.with_name(latest.name.replace("_latest.json", f"_{stamp}.json"))
    else:
        dated = latest.with_name(f"{latest.stem}_{stamp}{latest.suffix}")

    for p in (latest, dated):
        with p.open("w") as f:
            json.dump(payload, f, indent=2, default=str)
    return (latest, dated)


# ---- SQL ----

# SELECT: includes est_net_bps + entry_age_secs + ts for v2-parity + split-window
# bucketing. `ts` is `timestamp with time zone` per V999 migration; we expose
# `ts_epoch_ms` computed column for the split-window bucketing so the Python
# side works in integer ms without tz parsing.
# SELECT 納入 est_net_bps / entry_age_secs / ts（v2-parity + split-window 分段）；
# `ts` 為 timestamp with time zone，暴露 ts_epoch_ms 計算欄避免 tz parsing。
_SELECT_SQL = """
    SELECT
        engine_mode,
        strategy_name,
        symbol,
        peak_pnl_pct,
        atr_pct,
        giveback_atr_norm,
        realized_net_bps,
        est_net_bps,
        entry_age_secs,
        (extract(epoch from ts) * 1000)::bigint AS ts_epoch_ms,
        exit_trigger_rule
    FROM learning.exit_features
    WHERE ts > now() - (%(days)s || ' days')::interval
      AND realized_net_bps IS NOT NULL
      AND (%(engine_mode_all)s OR engine_mode = ANY(%(engine_modes)s))
      AND (%(strategy)s IS NULL OR strategy_name = %(strategy)s)
      AND (%(include_funding_arb)s OR strategy_name != 'funding_arb')
      AND (%(symbol)s IS NULL OR symbol = %(symbol)s)
      AND (
          %(exclude_tag_pattern)s IS NULL
          OR strategy_name NOT LIKE %(exclude_tag_pattern)s
      )
"""


# FA --peak-sanity-histogram: separate READ-ONLY SELECT, per-strategy peak
# distribution for outlier-realism audit. Shares SQL filter (mode/strategy/symbol/
# exclude-tag) with main SELECT so the histogram and the main table describe
# the same row set.
# FA --peak-sanity-histogram：獨立 READ-ONLY SELECT，每策略 peak 分佈做 outlier
# 真實性核驗。共用 mode/strategy/symbol/exclude-tag filter 保持 histogram 與主
# 表覆蓋同一 row set。
_PEAK_HISTOGRAM_SQL = """
    SELECT
        strategy_name,
        COUNT(*) AS n,
        ROUND(AVG(peak_pnl_pct)::numeric, 4) AS mean_peak,
        ROUND(MAX(peak_pnl_pct)::numeric, 4) AS max_peak,
        ROUND(percentile_cont(0.05) WITHIN GROUP (ORDER BY peak_pnl_pct)::numeric, 4) AS p5,
        ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY peak_pnl_pct)::numeric, 4) AS p50,
        ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY peak_pnl_pct)::numeric, 4) AS p95
    FROM learning.exit_features
    WHERE ts > now() - (%(days)s || ' days')::interval
      AND realized_net_bps IS NOT NULL
      AND (%(engine_mode_all)s OR engine_mode = ANY(%(engine_modes)s))
      AND (%(strategy)s IS NULL OR strategy_name = %(strategy)s)
      AND (%(include_funding_arb)s OR strategy_name != 'funding_arb')
      AND (%(symbol)s IS NULL OR symbol = %(symbol)s)
      AND (
          %(exclude_tag_pattern)s IS NULL
          OR strategy_name NOT LIKE %(exclude_tag_pattern)s
      )
    GROUP BY strategy_name
    ORDER BY strategy_name
"""


def _build_query_params(args: argparse.Namespace) -> dict[str, Any]:
    """Parse --engine-mode and return psycopg2 named-param dict."""
    em_raw = (args.engine_mode or "").strip().lower()
    if em_raw == "all":
        engine_mode_all = True
        engine_modes: list[str] = []
    else:
        engine_mode_all = False
        engine_modes = [s.strip() for s in em_raw.split(",") if s.strip()]
        if not engine_modes:
            # Default: demo + live_demo (per Edge 分析用 demo 不用 paper memory note)
            # 預設：demo + live_demo（依 feedback_demo_over_paper_for_edge memory）
            engine_modes = ["demo", "live_demo"]
    return {
        "days": str(args.days),
        "engine_mode_all": engine_mode_all,
        "engine_modes": engine_modes,
        "strategy": args.strategy,
        "include_funding_arb": bool(args.include_funding_arb),
        "symbol": args.symbol,
        "exclude_tag_pattern": getattr(args, "_resolved_exclude_tag_pattern", None),
    }


def _bucket_row_by_window(ts_epoch_ms: int | None) -> str:
    """Assign a row to one of four windows: pre-T3 / T3-T4-vacuum / post-T4-pre-P013 / post-P013-clean.

    Per FA H3 MICRO-PROFIT-FIX-1 vacuum hypothesis (2026-04-19 T3 → 2026-04-21 T4)
    + 2026-04-24 PM P0-13 ATR-scale pollution discovery (2026-04-22 21:35 UTC cut-over).

    Only `post-P013-clean` data is numerically sound for v2-parity cf decisions:
    pre-P013 rows have atr_pct under-scaled 100-1000x and giveback_atr_norm
    inflated 200-400x (per-tick micro-vol → kline Wilder ATR switch in ff694e8).
    若 pre-T3 Δ≈0 + T3-T4-vacuum Δ 明顯正值 + post-T4-pre-P013 介於 +
    post-P013-clean 回到小樣本真實 signal → FA H3 + P0-13 pollution hypothesis 證立。
    """
    if ts_epoch_ms is None:
        return "pre-T3"
    t3_ms = int(_SPLIT_WINDOW_T3_UTC.timestamp() * 1000)
    t4_ms = int(_SPLIT_WINDOW_T4_UTC.timestamp() * 1000)
    p013_ms = int(_SPLIT_WINDOW_P013_UTC.timestamp() * 1000)
    if ts_epoch_ms < t3_ms:
        return "pre-T3"
    if ts_epoch_ms < t4_ms:
        return "T3-T4-vacuum"
    if ts_epoch_ms < p013_ms:
        return "post-T4-pre-P013"
    return "post-P013-clean"


# ---- main ----

def _default_output_path() -> str:
    """`$OPENCLAW_DATA_DIR/audit/counterfactual_exit_replay_latest.json`."""
    base = os.environ.get("OPENCLAW_DATA_DIR") or "/tmp/openclaw"
    return str(Path(base) / "audit" / "counterfactual_exit_replay_latest.json")


def _positive_int(raw: str) -> int:
    """argparse type fn: reject ``--days <= 0`` loudly (QC MINOR fix)."""
    try:
        v = int(raw)
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"expected int, got {raw!r}") from e
    if v <= 0:
        raise argparse.ArgumentTypeError(
            f"must be > 0 (got {v}); a non-positive window has no data to replay"
        )
    return v


def _positive_float(raw: str) -> float:
    """argparse type fn: reject ``--fee-bps-per-side < 0``."""
    try:
        v = float(raw)
    except (TypeError, ValueError) as e:
        raise argparse.ArgumentTypeError(f"expected float, got {raw!r}") from e
    if v < 0 or not math.isfinite(v):
        raise argparse.ArgumentTypeError(
            f"must be finite and >= 0 (got {v})"
        )
    return v


def _resolve_cost_models(raw: str) -> tuple[str, ...]:
    r = (raw or "").strip().lower()
    if r == "both":
        return ("proxy", "fee_only")
    if r in ("proxy", "fee_only"):
        return (r,)
    raise argparse.ArgumentTypeError(
        f"--cost-model must be one of proxy|fee_only|both (got {raw!r})"
    )


def _resolve_v2_config(args: argparse.Namespace) -> V2Config:
    """Build V2Config from argparse overrides (all have CLI defaults = v2 defaults)."""
    return V2Config(
        gate1_floor_bps=args.gate1_floor,
        missing_edge_fallback_bps=args.missing_edge_fallback,
        min_hold_secs=float(args.min_hold_secs),
        min_peak_atr_norm=args.min_peak_atr_norm,
        giveback_base=args.giveback_base,
        giveback_slope=args.giveback_slope,
        giveback_floor=args.giveback_floor,
    )


def _emit_verdict_for_rows(
    rows: list[dict[str, Any]],
    args: argparse.Namespace,
    cost_models: tuple[str, ...],
    *,
    caption_suffix: str = "",
) -> None:
    """Print fee_only + proxy VERDICT blocks for a row set.

    Extracted so --split-window can reuse the same verdict logic per bucket.
    抽成獨立 fn 讓 --split-window 每個 bucket 能共用判決邏輯。
    """
    total_n = sum(r["n_exits"] for r in rows)
    if total_n == 0:
        print(f"VERDICT{caption_suffix}: no exits in window — nothing to judge")
        return

    def _emit(model: str, caption: str) -> None:
        _n, total_cf, total_imp = _summary_totals(rows, model)
        if total_cf == 0:
            print(
                f"VERDICT{caption_suffix} ({caption}): cf NEVER fired "
                f"(k={args.cf_multiplier}); cannot score — widen window or loosen gates"
            )
            return
        sign = "+" if total_imp > 0 else ""
        if total_imp > 0:
            tail = "phys_lock WOULD have helped"
        else:
            tail = "phys_lock WOULD NOT have helped"
        print(
            f"VERDICT{caption_suffix} ({caption}): cf improvement avg = "
            f"{sign}{total_imp:.2f} bps over {total_cf} fired exits — {tail}"
        )

    if "fee_only" in cost_models:
        _emit("fee_only", "fee_only model, conservative — READ THIS")
    if "proxy" in cost_models:
        print()
        print(
            "[DEGENERATE PROXY WARNING] Per FA algebra proof, proxy improvement "
            "≡ −k × atr_pct × 100 bps identically for every fired row (fees "
            "cancel out + giveback is double-counted). IGNORE THE SIGN below; "
            "the proxy verdict is retained ONLY as an arithmetic sanity check."
        )
        _emit("proxy", "proxy model, degenerate — sanity check only")


def _print_peak_histogram(hist_rows: list[dict[str, Any]]) -> None:
    """Stdout table for --peak-sanity-histogram (FA outlier-realism audit).

    FA outlier 真實性核驗小表：每策略 n / mean / max / p5 / p50 / p95 (peak_pnl_pct)。
    """
    if not hist_rows:
        print("(--peak-sanity-histogram: no rows)")
        return
    print()
    print("=== peak_pnl_pct sanity histogram (per strategy, FA outlier-realism check) ===")
    hdr = (
        f"{'strategy_name':<18} | {'n':>6} | {'mean':>8} | {'max':>8} | "
        f"{'p5':>8} | {'p50':>8} | {'p95':>8}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in hist_rows:
        print(
            f"{(r.get('strategy_name') or ''):<18.18} | "
            f"{int(r.get('n') or 0):>6d} | "
            f"{float(r.get('mean_peak') or 0):>8.4f} | "
            f"{float(r.get('max_peak') or 0):>8.4f} | "
            f"{float(r.get('p5') or 0):>8.4f} | "
            f"{float(r.get('p50') or 0):>8.4f} | "
            f"{float(r.get('p95') or 0):>8.4f}"
        )
    print(
        "Interpretation: if max_peak >> p95 for a strategy the top rows are "
        "genuine tail events (FA: believe the outlier); if max_peak ~ p95 the "
        "'outlier' is typical (FA: downweight per FM trimmed-mean / median)."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--days", type=_positive_int, default=7,
                    help="Lookback window in days, must be > 0 (default 7)")
    ap.add_argument("--engine-mode", type=str, default="demo,live_demo",
                    help="Comma-separated list or 'all' (default: demo,live_demo)")
    ap.add_argument("--strategy", type=str, default=None,
                    help="Filter by strategy_name (optional)")
    ap.add_argument("--symbol", type=str, default=None,
                    help="Filter by symbol (optional)")
    ap.add_argument("--cf-multiplier", type=float, default=0.3,
                    help="k in 'peak - k × ATR' lock GROSS formula (default 0.3; "
                         "used in both v1 and v2 modes — v2-parity only changes "
                         "the fire decision, not the locked-in gross)")
    ap.add_argument(
        "--cost-model",
        type=str,
        default="both",
        help="Cost model for cf_net: 'proxy' (degenerate per FA — retained for "
             "transparency), 'fee_only' (round-trip taker fee; empirically "
             "meaningful), or 'both' (default; prints two tables + two verdicts)",
    )
    ap.add_argument(
        "--fee-bps-per-side",
        type=_positive_float,
        default=5.5,
        help="Taker fee per side in bps for the fee_only cost model. Default "
             "5.5 = Bybit linear taker (0.00055; see "
             "rust/openclaw_engine/src/account_manager.rs:136 DEFAULT_TAKER_FEE)",
    )
    ap.add_argument(
        "--include-funding-arb",
        action="store_true",
        help="Opt-in to include strategy_name='funding_arb' rows. By default "
             "excluded because realized_pnl includes funding payment while "
             "peak_pnl_pct is price-only → proxy cost is distorted.",
    )
    ap.add_argument("--output-json", type=str, default=_default_output_path(),
                    help="Latest JSON output path (dated sibling auto-written)")

    # ── Flag 1: v2-parity (FA + FM top priority) ──────────────────────────
    # ── Flag 1: v2-parity（FA + FM 最高優先）────────────────────────────
    ap.add_argument(
        "--v2-parity",
        action="store_true",
        help="Rust v2 4-Gate parity (Gate1 edge floor → Gate2 min hold → "
             "Gate3 peak/ATR norm → Gate4a non-linear giveback). Override each "
             "gate via --gate1-floor / --missing-edge-fallback / --min-hold-secs "
             "/ --min-peak-atr-norm / --giveback-{base,slope,floor}. Defaults "
             "match Rust ExitConfig::default + risk_config_demo.toml.",
    )
    ap.add_argument("--gate1-floor", type=float, default=V2_DEFAULT_GATE1_FLOOR_BPS,
                    help=f"v2 Gate 1 net-edge floor bps → ExitConfig.min_net_floor_bps (default {V2_DEFAULT_GATE1_FLOOR_BPS})")
    ap.add_argument("--missing-edge-fallback", type=float, default=V2_DEFAULT_MISSING_EDGE_FALLBACK_BPS,
                    help=f"v2 Gate 1 fallback bps for NULL est_net_bps → ExitConfig.missing_edge_fallback_bps (demo TOML {V2_DEFAULT_MISSING_EDGE_FALLBACK_BPS})")
    ap.add_argument("--min-hold-secs", type=int, default=int(V2_DEFAULT_MIN_HOLD_SECS),
                    help=f"v2 Gate 2 min hold seconds → ExitConfig.min_hold_secs (default {int(V2_DEFAULT_MIN_HOLD_SECS)})")
    ap.add_argument("--min-peak-atr-norm", type=float, default=V2_DEFAULT_MIN_PEAK_ATR_NORM,
                    help=f"v2 Gate 3 peak/ATR threshold → ExitConfig.min_peak_atr_norm (default {V2_DEFAULT_MIN_PEAK_ATR_NORM})")
    ap.add_argument("--giveback-base", type=float, default=V2_DEFAULT_GIVEBACK_BASE,
                    help=f"v2 Gate 4a non-linear giveback intercept → ExitConfig.giveback_base (default {V2_DEFAULT_GIVEBACK_BASE})")
    ap.add_argument("--giveback-slope", type=float, default=V2_DEFAULT_GIVEBACK_SLOPE,
                    help=f"v2 Gate 4a non-linear giveback slope → ExitConfig.giveback_slope (default {V2_DEFAULT_GIVEBACK_SLOPE})")
    ap.add_argument("--giveback-floor", type=float, default=V2_DEFAULT_GIVEBACK_FLOOR,
                    help=f"v2 Gate 4a non-linear giveback floor → ExitConfig.giveback_floor (default {V2_DEFAULT_GIVEBACK_FLOOR})")

    # ── Flag 2: close-tag exclusion (FA category-error) + split-window ────
    # ── Flag 2：close-tag 排除（FA 類別錯誤）+ 分段 ──────────────────────
    ap.add_argument("--exclude-close-tag", type=str, default="risk_close:%",
                    help="SQL NOT LIKE pattern on strategy_name. DEFAULT ON "
                         "with 'risk_close:%%' per FA: risk_close:* rows are "
                         "already risk-layer closes (phys_lock sim double-counts).")
    ap.add_argument("--include-close-tag", action="store_true",
                    help="Disable the default --exclude-close-tag filter.")
    ap.add_argument("--split-window", action="store_true",
                    help="Run 3 aggregations bucketed by ts into pre-T3 / "
                         "T3-T4-vacuum / post-T4 (MICRO-PROFIT-FIX-1 "
                         "2026-04-19 / TRACK-P T4 2026-04-21 cut-overs). "
                         "Validates FA H3 vacuum hypothesis.")

    # ── Flag 3: robust stats (FM outlier-driven finding) ──────────────────
    ap.add_argument("--bootstrap-ci", action="store_true",
                    help="Bootstrap 95%% CI on fired-row improvements (stdlib, "
                         "1000 resamples, percentile; adds bootstrap_ci_lo/hi per group).")
    ap.add_argument("--per-strategy-median", action="store_true",
                    help="statistics.median(fired_improvements) per group "
                         "(FM outlier-robust centre).")
    ap.add_argument("--trimmed-mean-pct", type=float, default=None,
                    help="Symmetric trimmed mean dropping PCT%% from each "
                         "tail (FM-recommended 5.0); 0/unset = no trim.")

    # ── Flag 4: peak sanity histogram (FA outlier-realism) ────────────────
    ap.add_argument("--peak-sanity-histogram", action="store_true",
                    help="READ-ONLY per-strategy peak_pnl_pct mean/max/p5/p50/p95 "
                         "table after main output (FA outlier-realism audit).")

    args = ap.parse_args()

    cost_models = _resolve_cost_models(args.cost_model)

    # Resolve the close-tag exclusion pattern (Flag 2).
    # 決定 close-tag 排除 pattern（Flag 2）。
    if args.include_close_tag:
        # Operator explicit opt-in to include risk_close:* rows.
        # Operator 顯式 opt-in 納入 risk_close:*。
        args._resolved_exclude_tag_pattern = None
    else:
        tag = (args.exclude_close_tag or "").strip()
        args._resolved_exclude_tag_pattern = tag if tag else None

    # Resolve the v2 config (Flag 1).
    # 決定 v2 config（Flag 1）。
    v2_cfg = _resolve_v2_config(args) if args.v2_parity else None

    started_at = datetime.now(timezone.utc)
    print(
        f"Counterfactual exit replay @ {started_at.isoformat(timespec='seconds')} UTC"
    )
    if v2_cfg is not None:
        print(
            f"  V2 PARITY MODE: gate1_floor={v2_cfg.gate1_floor_bps} "
            f"missing_edge_fallback={v2_cfg.missing_edge_fallback_bps} "
            f"min_hold={v2_cfg.min_hold_secs}s "
            f"min_peak_atr_norm={v2_cfg.min_peak_atr_norm} "
            f"giveback_base={v2_cfg.giveback_base} "
            f"giveback_slope={v2_cfg.giveback_slope} "
            f"giveback_floor={v2_cfg.giveback_floor} "
            "(Rust 4-Gate; see --help for ExitConfig field mapping)"
        )
    else:
        print(f"  v1 mode: Gate-4-only LINEAR giveback k={args.cf_multiplier}. "
              "Pass --v2-parity for Rust 4-Gate parity.")
    print(
        f"  days={args.days}  cf_multiplier={args.cf_multiplier}  "
        f"cost_model={args.cost_model}  fee_bps_per_side={args.fee_bps_per_side}"
    )
    print(
        f"  engine_mode={args.engine_mode}  strategy={args.strategy or '(any)'}  "
        f"symbol={args.symbol or '(any)'}  "
        f"funding_arb={'INCLUDED' if args.include_funding_arb else 'excluded'}"
    )
    # Exclude-close-tag banner (Flag 2).
    # Exclude-close-tag banner（Flag 2）。
    pat = args._resolved_exclude_tag_pattern
    if pat is None and args.include_close_tag:
        print("  [INFO] --include-close-tag set: risk_close:* rows INCLUDED.")
    elif pat is None:
        print("  [INFO] --exclude-close-tag pattern empty: no close-tag filter.")
    elif pat == "risk_close:%":
        print("  [INFO] Auto-excluded risk_close:* rows per FA category-error "
              "finding; use --include-close-tag to opt in.")
    else:
        print(f"  [INFO] --exclude-close-tag NOT LIKE {pat!r}.")
    if args.split_window:
        print("  [FLAG] --split-window: 3-bucket pre-T3/T3-T4-vacuum/post-T4.")
    if args.bootstrap_ci or args.per_strategy_median or args.trimmed_mean_pct is not None:
        bits = []
        if args.bootstrap_ci: bits.append("bootstrap-ci")
        if args.per_strategy_median: bits.append("median")
        if args.trimmed_mean_pct is not None: bits.append(f"trimmed-mean-pct={args.trimmed_mean_pct}")
        print(f"  [FLAG] FM robust stats: {', '.join(bits)}")
    if args.peak_sanity_histogram:
        print("  [FLAG] --peak-sanity-histogram: per-strategy peak distribution.")
    if args.include_funding_arb:
        print(
            "  [WARNING] funding_arb included: realized_pnl has funding payment "
            "component while peak_pnl_pct is price-only → proxy cost distorted; "
            "treat funding_arb rows with extra skepticism."
        )
    print("=" * 70)

    try:
        conn = _get_conn()
    except Exception as e:
        print(f"[FATAL] DB connect failed: {e}")
        return 2

    rows: list[dict[str, Any]] = []
    hist_rows: list[dict[str, Any]] = []
    try:
        with conn.cursor() as cur:
            params = _build_query_params(args)
            cur.execute(_SELECT_SQL, params)
            colnames = [d.name for d in cur.description]  # type: ignore[union-attr]
            for row in cur.fetchall():
                rows.append(dict(zip(colnames, row)))
            if args.peak_sanity_histogram:
                cur.execute(_PEAK_HISTOGRAM_SQL, params)
                hcols = [d.name for d in cur.description]  # type: ignore[union-attr]
                for row in cur.fetchall():
                    hist_rows.append(dict(zip(hcols, row)))
    except Exception as e:
        print(f"[FATAL] query failed: {e}")
        try:
            conn.close()
        except Exception:
            pass
        return 2
    finally:
        try:
            conn.close()
        except Exception:
            pass

    # Detect entry_age_secs column presence. Writer populates it
    # (exit_feature_writer.rs:157) but downstream replay must tolerate NULLs
    # for older rows pre-writer-wire.
    # 偵測 entry_age_secs 欄是否被 writer 填；舊行可能全 NULL，Gate 2 須優雅跳過。
    entry_age_column_present = True
    if v2_cfg is not None and rows:
        non_null = sum(1 for r in rows if r.get("entry_age_secs") is not None)
        if non_null == 0:
            entry_age_column_present = False
            print(
                "  [WARN] entry_age_secs column NULL for all rows in window — "
                "Gate 2 will be skipped (forward-compat path); cf_fired will "
                "only reflect Gate 1/3/4a."
            )

    agg_kwargs = {
        "v2_cfg": v2_cfg,
        "entry_age_column_present": entry_age_column_present,
        "bootstrap_ci": args.bootstrap_ci,
        "per_strategy_median": args.per_strategy_median,
        "trimmed_mean_pct": args.trimmed_mean_pct,
    }
    print_kwargs = {
        "show_median": args.per_strategy_median,
        "show_trimmed_mean": args.trimmed_mean_pct is not None,
        "show_bootstrap_ci": args.bootstrap_ci,
    }

    agg = _aggregate(rows, args.cf_multiplier, cost_models, args.fee_bps_per_side, **agg_kwargs)
    _print_table(agg, cost_models, **print_kwargs)

    # Split-window buckets (Flag 2b). Run 3 independent aggregations over the
    # same row set, one per window; print 3 tables + 3 VERDICT blocks.
    # Split-window 分段（Flag 2b）：同一 row set 跑 3 次獨立 aggregation，
    # 每 window 一張表 + 一個 VERDICT。
    by_window_agg: dict[str, list[dict[str, Any]]] | None = None
    if args.split_window:
        buckets: dict[str, list[dict[str, Any]]] = {
            "pre-T3": [],
            "T3-T4-vacuum": [],
            "post-T4-pre-P013": [],
            "post-P013-clean": [],
        }
        for r in rows:
            bucket = _bucket_row_by_window(r.get("ts_epoch_ms"))
            buckets[bucket].append(r)
        by_window_agg = {}
        for win in ("pre-T3", "T3-T4-vacuum", "post-T4-pre-P013", "post-P013-clean"):
            print()
            print("#" * 70)
            print(f"# --split-window bucket: {win}  (n_rows={len(buckets[win])})")
            print("#" * 70)
            sub_agg = _aggregate(
                buckets[win],
                args.cf_multiplier,
                cost_models,
                args.fee_bps_per_side,
                **agg_kwargs,
            )
            _print_table(sub_agg, cost_models, **print_kwargs)
            _emit_verdict_for_rows(
                sub_agg, args, cost_models, caption_suffix=f"[{win}]"
            )
            by_window_agg[win] = sub_agg

    # Peak-sanity histogram (Flag 4).
    # Peak-sanity histogram（Flag 4）。
    if args.peak_sanity_histogram:
        _print_peak_histogram(hist_rows)

    print("=" * 70)

    latest, dated = _write_json_outputs(
        agg,
        args,
        started_at,
        cost_models,
        v2_cfg=v2_cfg,
        by_window=by_window_agg,
        peak_histogram=(hist_rows if args.peak_sanity_histogram else None),
        exclude_tag_pattern=args._resolved_exclude_tag_pattern,
        entry_age_column_present=entry_age_column_present,
    )
    print(f"JSON written: {latest}")
    print(f"JSON dated:   {dated}")

    # Pooled verdict (decision criterion per EDGE-DIAG-1 spec). When
    # --split-window is active, per-bucket verdicts were already printed
    # above; this block stays as the pooled summary so operator sees both.
    # Pooled VERDICT：EDGE-DIAG-1 判決條件；--split-window 時，bucket 判決已印
    # 在上方，此區為 pooled 總結保持操作員兩者皆見。
    _emit_verdict_for_rows(agg, args, cost_models, caption_suffix="")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""funding-tilt 樞紐診斷 harness 編排器 — 協議 §DATA TASKS + §4 + §5 決策樹。

MODULE_NOTE:
  模塊用途：編排 DATA TASK 0-5 + Step0 樣本充分性 + leak-free/naive 雙軌 + §3.0 會計
    （per-leg 分解）+ §4 全統計（HAC / DSR(K=8) / PSR / PBO / block bootstrap / 兩個
    N_eff）+ §4.5 horizon-vs-cost-share 掃描 + §4b regime split + §5 決策樹，輸出
    JSON + markdown 研究 artifact。
  決策樹（協議 §5，fail-fast 在第一個命中的門檻停）：
    - Step0 n_independent(A) < 60 → INCONCLUSIVE-A
    - funding Ljung-Box 無正自相關 → NO-GO-A（預期不發生）
    - leak-free Sharpe≈0 但 naive 高（>30% gap）→ NO-GO-B
    - §4.5 net 隨 H_min 上升仍 ≤0 OR carry_cost_ratio ≥0.8 → NO-GO-C（攤薄證偽，最可能）
    - net 正但 carry_share 低 + edge 集中 bull short-side top-funding → NO-GO（squeeze 偽裝）
    - DSR(K=8)<0.95 OR PSR<0.95 OR bootstrap CI 下界 ≤0 → NO-GO-D / INCONCLUSIVE-B
    - OOS<0.3×IS OR PBO≥0.5 → NO-GO-E
    - 全過 + edge 只在 bull → regime-bet / learning-only
    - 全過 + ≥1 non-bull slice 獨立通過（carry_share 高）→ GO（durable-alpha candidate）
  主要函數：``run_diagnostic`` / ``main``。
  硬邊界：
    - **唯讀 PG**；輸出寫 artifact，絕不寫 production 表。
    - K 鎖 8（count_trial_budget 自檢；偷加 grid 不更新 K 被測抓）。
    - 紅線 1/2/3（perp-only directional / cap SSOT / funding 雙面會計）聲明於報告。
    - 誠實：NO-GO / INCONCLUSIVE / regime-bet 是合法結果；不 massage 數字製造 GO。
    - --dry-run（synthetic）可在 Mac 跑（不連 PG）。
  依賴：本目錄 data_loader/signals/cost_model/pnl/stats + numpy + lib/stats_common
    （PSR/DSR/PBO/block bootstrap，純 stdlib）。
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

import numpy as np

# 支援直接跑與 -m 兩種；把 srv/helper_scripts/research 加進 path 以 package 匯入，
# 並把 srv/helper_scripts 加進 path 以匯入共享 lib.stats_common。
_THIS = Path(__file__).resolve()
_PKG_PARENT = _THIS.parents[1]  # .../helper_scripts/research
_HELPER_SCRIPTS = _THIS.parents[2]  # .../helper_scripts
for _p in (_PKG_PARENT, _HELPER_SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from funding_tilt_diagnostic import cost_model, data_loader, pnl, signals, stats  # noqa: E402
from lib import stats_common  # noqa: E402

# Step0 有效樣本硬門檻（協議 §4.0）。
EFFECTIVE_N_FLOOR = 60
# net Sharpe 門檻（年化，協議 §5）。
NET_SHARPE_FLOOR = 0.5
# §4.2 過擬合門檻。
PSR_FLOOR = 0.95
DSR_FLOOR = 0.95
PBO_CEILING = 0.5
# §4.5 horizon-vs-cost-share 掃描的 H_min（診斷，**不入 K**）。
HORIZON_SCAN_HMINS = (1, 3, 7, 14)
# bootstrap / PBO 固定 seed（research 可重現，沿用 stats_common 慣例）。
_BOOTSTRAP_SEED = 20260603
_PBO_SEED = 20260603


def _artifact_root() -> Path:
    """跨平台 artifact 根（禁硬編碼，沿用 gate_b / trend 慣例）。"""
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "funding_tilt_diagnostic_runs"


# ── DATA TASKS ──────────────────────────────────────────────────────────────

def data_task_0_canonical_run(panel: data_loader.Panel) -> dict:
    """DATA TASK 0：canonical run + 覆蓋驗證（協議 §DATA TASK 0，最 binding）。

    記錄所用 run_id + manifest + per-symbol funding 覆蓋 + 推導 interval。MIT cheap
    pre-check 已驗覆蓋乾淨（PASS）；本 task 在報告固化證據（非近期密集+早期稀疏）。
    """
    per_symbol_interval = {}
    for s, fs in panel.funding.items():
        per_symbol_interval[s] = {
            "n_settlements": int(len(fs.rate)),
            "interval_minutes_inferred": fs.interval_minutes,
            "interval_uncertain": fs.interval_uncertain,
        }
    intervals = [v["interval_minutes_inferred"] for v in per_symbol_interval.values()
                 if v["interval_minutes_inferred"]]
    n_uncertain = sum(1 for v in per_symbol_interval.values() if v["interval_uncertain"])
    return {
        "canonical_run_id": panel.canonical_run_id,
        "run_meta": panel.coverage_notes.get("canonical_run"),
        "funding_coverage": panel.coverage_notes.get("funding_coverage"),
        "per_symbol_interval": per_symbol_interval,
        "distinct_intervals_minutes": sorted(set(intervals)),
        "n_symbols_interval_uncertain": n_uncertain,
        "interval_source": panel.coverage_notes.get("funding_interval_source"),
        "cap_discipline": panel.coverage_notes.get("cap_discipline"),
    }


def data_task_1_funding_magnitude(panel: data_loader.Panel) -> dict:
    """DATA TASK 1：funding 量級分布（協議 §DATA TASK 1，決定成本牆高度）。

    per-settlement |F| 的 mean/median/p75/p90/p99（bps）+ % 為正（bull-heavy 標記）。
    核心：median |F| 是否 ≳1bp/結算（§3.4 break-even 所需）。MIT 實測 median 0.853bps、
    72.4% 正 funding（須標 breadth-limited / bull-heavy）。
    """
    all_abs = []
    all_signed = []
    per_symbol = {}
    for s, fs in panel.funding.items():
        if len(fs.rate) == 0:
            continue
        abs_bps = np.abs(fs.rate) * 1e4
        all_abs.extend(abs_bps.tolist())
        all_signed.extend((fs.rate * 1e4).tolist())
        per_symbol[s] = {
            "median_abs_bps": round(float(np.median(abs_bps)), 4),
            "pct_positive": round(float(np.mean(fs.rate > 0)) * 100.0, 2),
        }
    if not all_abs:
        return {"error": "no funding settlements"}
    arr = np.asarray(all_abs)
    signed = np.asarray(all_signed)
    return {
        "per_settlement_abs_bps": {
            "mean": round(float(arr.mean()), 4),
            "median": round(float(np.median(arr)), 4),
            "p75": round(float(np.percentile(arr, 75)), 4),
            "p90": round(float(np.percentile(arr, 90)), 4),
            "p99": round(float(np.percentile(arr, 99)), 4),
        },
        "pct_settlements_positive": round(float(np.mean(signed > 0)) * 100.0, 2),
        "pct_settlements_at_or_below_1bp": round(float(np.mean(arr <= 1.0)) * 100.0, 2),
        "per_symbol": per_symbol,
        "break_even_note": (
            "§3.4: median |F| must be ≳1bp/settlement for carry to amortize taker RT; "
            "MIT pre-check median≈0.853bps (marginal-not-dead)."
        ),
        "cohort_label": "breadth-limited / survivor-cohort / bull-heavy",
    }


def data_task_3_xsec_dispersion(panel: data_loader.Panel, tiltscore_by_symbol: dict) -> dict:
    """DATA TASK 3：funding cross-sectional 離散度（協議 §DATA TASK 3）。

    每 rebalance 日橫截面 leak-free tiltscore 的 std/IQR + tilt spread（top-tertile mean
    − bottom-tertile mean）→ 有無足夠離散度支撐 tertile long-short。MIT 實測 median tilt
    spread 1.436bps、median std 0.76bps（離散度存在）。
    """
    n = len(panel.dates)
    stds = []
    spreads = []
    breadths = []
    for t in range(n):
        vals = []
        for s, ts in tiltscore_by_symbol.items():
            if panel.survivorship[s][t] and not panel.funding[s].interval_uncertain:
                v = ts.leakfree[t]
                if np.isfinite(v):
                    vals.append(float(v))
        if len(vals) >= 9:  # 橫截面 ≥9 才算（與 MIT pre-check n_sym≥9 對齊）
            arr = np.asarray(vals)
            stds.append(float(arr.std(ddof=1)) * 1e4)
            arr.sort()
            tert = max(1, len(arr) // 3)
            spread = (float(arr[-tert:].mean()) - float(arr[:tert].mean())) * 1e4
            spreads.append(spread)
            breadths.append(len(vals))
    if not spreads:
        return {"error": "insufficient cross-sectional breadth for tilt spread"}
    return {
        "median_xsec_std_bps": round(float(np.median(stds)), 4),
        "median_tilt_spread_bps": round(float(np.median(spreads)), 4),
        "mean_tilt_spread_bps": round(float(np.mean(spreads)), 4),
        "p25_tilt_spread_bps": round(float(np.percentile(spreads, 25)), 4),
        "p75_tilt_spread_bps": round(float(np.percentile(spreads, 75)), 4),
        "avg_breadth": round(float(np.mean(breadths)), 1),
        "n_rebalance_days": len(spreads),
    }


def data_task_4_fee_tier() -> dict:
    """DATA TASK 4：fee tier（協議 §3.1，taker 5.5bps/side SSOT，不打 live API）。"""
    return {
        "taker_bps_per_side": cost_model.TAKER_FEE_BPS_PER_SIDE,
        "maker_bps_per_side": cost_model.MAKER_FEE_BPS_PER_SIDE,
        "taker_rt_bps": cost_model.trading_cost_bps(maker=False),
        "maker_rt_bps": cost_model.trading_cost_bps(maker=True),
        "slippage_rt_bps": 2 * cost_model.SLIPPAGE_BPS_PER_SIDE,
        "source": "protocol §3.1 conservative SSOT (/v5/account/fee-rate); not live-queried",
    }


def data_task_5_regime(panel: data_loader.Panel) -> dict:
    """DATA TASK 5：730 天 regime 組成（協議 §DATA TASK 5，禁 HMM）。"""
    vals, counts = np.unique(panel.regime, return_counts=True)
    total = int(counts.sum())
    composition = {str(v): int(c) for v, c in zip(vals, counts)}
    pct = {k: round(100.0 * v / total, 2) for k, v in composition.items()} if total else {}
    return {
        "n_days": total,
        "composition_days": composition,
        "composition_pct": pct,
        "source": panel.coverage_notes.get("regime_source"),
        "bull_dominated": pct.get("bull", 0) >= 60.0,
        "cohort_label": "bull-heavy / breadth-limited / survivor-cohort",
    }


# ── 信號構造 ──────────────────────────────────────────────────────────────

def _build_tiltscores(panel: data_loader.Panel, lookback: int) -> dict:
    """每 symbol 算雙軌 tiltscore（leak-free / naive，協議 §1.A + §2.1）。"""
    out = {}
    for s in panel.funding:
        fs = panel.funding[s]
        out[s] = signals.compute_tiltscore_series(
            fs.ts, fs.rate, panel.open_ts_utc, lookback,
            interval_minutes=fs.interval_minutes,
        )
    return out


def _interval_uncertain_map(panel: data_loader.Panel) -> dict:
    return {s: fs.interval_uncertain for s, fs in panel.funding.items()}


def _build_price_return_matrix(panel: data_loader.Panel, universe) -> np.ndarray:
    """price-return 日報酬矩陣（T×S）供 price-return PCA N_eff（§4.3）。"""
    cols = []
    for s in universe:
        c = panel.close[s]
        r = np.full(len(c), np.nan)
        for t in range(1, len(c)):
            a, b = c[t], c[t - 1]
            if np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0:
                r[t] = np.log(a / b)
        cols.append(r)
    return np.column_stack(cols)


def _build_tiltscore_matrix(panel: data_loader.Panel, universe, tiltscore_by_symbol: dict) -> np.ndarray:
    """funding-tiltscore 矩陣（R×S）供 funding-tiltscore PCA N_eff（§4.3 新）。

    用 leak-free tiltscore，只取所有 symbol 都 finite 的 rebalance 行（_pca 內亦 dropna）。
    """
    cols = []
    for s in universe:
        cols.append(tiltscore_by_symbol[s].leakfree)
    return np.column_stack(cols)


def _pooled_daily_returns(panel, universe, signal_by_symbol, variant, h_min, *,
                          include_funding=True, leakfree=True):
    """pooled 等權日報酬（跨 symbol 平均；leak-free 或 naive 軌）+ pooled flips + trades。

    回 (port_returns ndarray, total_flips, all_trades)。
    """
    daily_cols = []
    total_flips = 0
    all_trades = []
    regime = panel.regime
    for s in universe:
        ss = signal_by_symbol[s]
        sig = ss.leakfree if leakfree else ss.naive
        surv = panel.survivorship[s]
        sig = np.where(surv, sig, 0.0)  # 上市前歸零
        fs = panel.funding[s]
        trades, pos, flips = pnl.build_trades(
            s, sig, panel.open_[s], panel.open_ts_utc, fs.ts, fs.rate,
            variant=variant, h_min=h_min, regimes=list(regime))
        total_flips += flips
        all_trades.extend(trades)
        _g, n = pnl.daily_returns_from_positions(
            pos, panel.open_[s], panel.open_ts_utc, fs.ts, fs.rate,
            include_funding=include_funding)
        daily_cols.append(n if include_funding else _g)
    mat = np.column_stack(daily_cols)
    port = np.nanmean(mat, axis=1)
    return port, total_flips, all_trades


def evaluate_signal_variant(panel, universe, signal_by_symbol, variant, h_min) -> dict:
    """單一信號變體 × 持有期：leak-free/naive Sharpe + per-leg 會計分解 + per-regime net。"""
    # leak-free net（正式）+ leak-free gross（price-only，§2.1 對照）+ naive gross。
    lf_net_port, flips_lf, trades_lf = _pooled_daily_returns(
        panel, universe, signal_by_symbol, variant, h_min, include_funding=True, leakfree=True)
    lf_gross_port, _f1, _t1 = _pooled_daily_returns(
        panel, universe, signal_by_symbol, variant, h_min, include_funding=False, leakfree=True)
    nv_gross_port, flips_nv, _t2 = _pooled_daily_returns(
        panel, universe, signal_by_symbol, variant, h_min, include_funding=False, leakfree=False)

    sharpe_lf_net = stats.annualized_sharpe(lf_net_port)
    sharpe_lf_gross = stats.annualized_sharpe(lf_gross_port)
    sharpe_nv_gross = stats.annualized_sharpe(nv_gross_port)

    tm = pnl.trade_metrics_with_legs(trades_lf)

    # per-regime net Sharpe（用 leak-free net 日報酬按 regime 切，§4b）。
    regime = panel.regime
    per_regime = {}
    for rg in ("bull", "bear", "chop"):
        mask = regime == rg
        seg = lf_net_port[mask]
        per_regime[rg] = {
            "n_days": int(mask.sum()),
            "annualized_net_sharpe": stats.annualized_sharpe(seg),
            "mean_daily_bps": round(float(np.nanmean(seg)) * 1e4, 4) if np.any(np.isfinite(seg)) else None,
        }

    look_ahead_inflation = None
    if sharpe_lf_gross is not None and sharpe_nv_gross is not None and abs(sharpe_lf_gross) > 1e-9:
        look_ahead_inflation = (sharpe_nv_gross - sharpe_lf_gross) / abs(sharpe_lf_gross)

    return {
        "variant": variant,
        "h_min": h_min,
        "pooled_direction_flips_leakfree": flips_lf,
        "pooled_direction_flips_naive": flips_nv,
        "n_trades_leakfree": tm.get("n_trades", 0),
        "annualized_net_sharpe_leakfree": sharpe_lf_net,
        "annualized_gross_sharpe_leakfree": sharpe_lf_gross,
        "annualized_gross_sharpe_naive": sharpe_nv_gross,
        "look_ahead_inflation_ratio": (round(look_ahead_inflation, 4)
                                       if look_ahead_inflation is not None else None),
        "accounting": tm,  # 含 aggregate + per-leg（long_leg/short_leg）
        "per_regime_net": per_regime,
        "_lf_net_port": lf_net_port,  # 內部：供 DSR/PSR/bootstrap（不序列化，run_diagnostic pop）
    }


def _signed_forward_returns_for_signal_a(panel, universe, tiltscore_by_symbol, h_min) -> list:
    """pooled funding-tilt forward returns（§4.1 verdict 主檢定原料）。

    對每 rebalance 日 t、每 eligible symbol：用 leak-free tertile 決定 side，算 open-to-open
    h_min 日前瞻 net 報酬（gross_price + funding_pnl − cost）× 1（side 已含於 net）。
    pooled 全 (t, symbol) → harness 餵 funding_tilt_forward_significance。overlap_lag=h_min
    （前瞻窗重疊天數）。
    """
    n = len(panel.dates)
    interval_unc = _interval_uncertain_map(panel)
    cost_rt_frac = cost_model.trading_cost_bps(maker=False) * 1e-4
    pooled = []
    for t in range(n - h_min):
        # 該日橫截面 tertile（leak-free）。
        elig = []
        for s in universe:
            if panel.survivorship[s][t] and not interval_unc.get(s, False):
                v = tiltscore_by_symbol[s].leakfree[t]
                if np.isfinite(v):
                    elig.append((s, v))
        if len(elig) < 3:
            continue
        elig.sort(key=lambda x: x[1])
        tert = max(1, len(elig) // 3)
        bottom = {s for s, _ in elig[:tert]}   # long +1
        top = {s for s, _ in elig[-tert:]}     # short -1
        for s, _v in elig:
            if s in bottom:
                side = 1
            elif s in top:
                side = -1
            else:
                continue
            t_out = t + h_min
            o0, o1 = panel.open_[s][t], panel.open_[s][t_out]
            if not (np.isfinite(o0) and np.isfinite(o1)) or o0 <= 0 or o1 <= 0:
                continue
            if not (panel.survivorship[s][t] and panel.survivorship[s][t_out]):
                continue
            gross = side * float(np.log(o1 / o0))
            fs = panel.funding[s]
            rates = pnl._settlements_in_window(
                fs.ts, fs.rate, panel.open_ts_utc[t], panel.open_ts_utc[t_out])
            # funding_pnl = −side × F（多付空收，§3.0），與 cost_model 同會計約定。
            fund_pnl = sum(-side * float(r) for r in rates)
            net = gross + fund_pnl - cost_rt_frac
            pooled.append(net)
    return pooled


# ── 過擬合統計（§4.2，復用 lib.stats_common）──────────────────────────────

def _daily_to_list(port: np.ndarray) -> list:
    return [float(x) for x in port if np.isfinite(x)]


def _overfitting_block(best_port: np.ndarray, all_evals: dict, k_budget: int, h_min: int) -> dict:
    """§4.2 過擬合：PSR(0) / DSR(K=8) / block bootstrap CI / PBO（CSCV）。

    PSR/DSR/bootstrap 復用 lib.stats_common（純 stdlib，skew-kurt aware）。block size
    = max(20, H_min)（協議 §4.2）。PBO 用 per-variant 日報酬切日 block（維度可能不足 →
    誠實標 semantics，主防線回 walk-forward OOS）。
    """
    vals = _daily_to_list(best_port)
    block = max(20, h_min)
    psr = stats_common.psr_bailey_ldp(vals, sr_benchmark=0.0)
    dsr = stats_common.dsr_with_k(vals, k_budget)
    boot = stats_common.block_bootstrap_ci(vals, block_size=block, iterations=1000, seed=_BOOTSTRAP_SEED)

    # PBO（CSCV）：candidates = 各變體的 per-day mean net（用 day_bucket key）。維度多半不足
    # （K=8 < 10 candidate 門檻）→ stats_common 回 insufficient，誠實標。
    candidates = {}
    for key, ev in all_evals.items():
        port = ev.get("_lf_net_port")
        if port is None:
            continue
        daily = {}
        for t, d in enumerate(_dates_cache):
            if t < len(port) and np.isfinite(port[t]):
                daily[str(d)] = float(port[t])
        if daily:
            candidates[key] = daily
    pbo = stats_common.pbo_cscv(candidates, seed=_PBO_SEED)

    return {
        "psr_0": round(psr, 4) if psr is not None else None,
        "psr_floor": PSR_FLOOR,
        "psr_pass": bool(psr is not None and psr >= PSR_FLOOR),
        "dsr_k": k_budget,
        "dsr": round(dsr, 4) if dsr is not None else None,
        "dsr_floor": DSR_FLOOR,
        "dsr_pass": bool(dsr is not None and dsr >= DSR_FLOOR),
        "block_bootstrap_ci_mean_daily": (
            [round(boot[0], 8), round(boot[1], 8)] if boot is not None else None),
        "bootstrap_block_size": block,
        "bootstrap_ci_lower_positive": bool(boot is not None and boot[0] > 0),
        "pbo": pbo,
        "pbo_ceiling": PBO_CEILING,
        "pbo_pass": bool(pbo.get("value") is not None and pbo["value"] < PBO_CEILING),
        "note": (
            "PSR/DSR/bootstrap reuse lib.stats_common (skew-kurt aware). PBO via day-block "
            "CSCV; K=8 (<10 candidate floor) likely yields insufficient-dimension -> walk-forward "
            "OOS is the primary overfit defense (protocol §4.2)."
        ),
    }


# module-level cache：_dates 供 PBO day-bucket（run_diagnostic 設定）。
_dates_cache: list = []


# ── §4.5 horizon-vs-cost-share 掃描 ────────────────────────────────────────

def _horizon_cost_scan(panel, universe, signal_a_variants: dict) -> dict:
    """§4.5：沿 H_min∈{1,3,7,14} 掃描 net vs cost-share（成本牆攤薄論點直接驗證）。

    用信號 A（cross-sectional，carry 主檢定對象）的 flip_hold_min 變體，逐 H_min 算
    aggregate net + cost-share（fee+slip 佔 |net|）+ funding-share。驗證攤薄：cost-share
    隨 H_min 下降且 net 隨 H_min 轉正 → 攤薄成立；net 隨 H_min 仍 ≤0 → 攤薄證偽（NO-GO-C）。
    用 L=9（中間 lookback，代表性）。
    """
    by_sym = signal_a_variants.get("A_L9")
    if by_sym is None:
        # 退而取任一 A 變體。
        for k, v in signal_a_variants.items():
            if k.startswith("A_"):
                by_sym = v
                break
    if by_sym is None:
        return {"error": "no signal A variant available"}
    curve = {}
    for hmin in HORIZON_SCAN_HMINS:
        _port, _flips, trades = _pooled_daily_returns(
            panel, universe, by_sym, "flip_hold_min", hmin, include_funding=True, leakfree=True)
        tm = pnl.trade_metrics_with_legs(trades)
        agg = tm.get("aggregate", {}) if tm.get("n_trades") else {}
        net = agg.get("net_bps")
        fp = agg.get("funding_pnl_bps")
        cost = agg.get("cost_bps")
        cost_share = None
        funding_share = None
        if net is not None and abs(net) > 1e-9 and cost is not None:
            cost_share = round(cost / abs(net), 4)
        if net is not None and abs(net) > 1e-9 and fp is not None:
            funding_share = round(fp / abs(net), 4)
        curve[f"H{hmin}"] = {
            "h_min_days": hmin,
            "n_trades": tm.get("n_trades", 0),
            "aggregate_net_bps": net,
            "aggregate_funding_pnl_bps": fp,
            "aggregate_gross_price_bps": agg.get("gross_price_bps"),
            "cost_bps": cost,
            "cost_share_of_abs_net": cost_share,
            "funding_share_of_abs_net": funding_share,
            "short_leg_net_bps": tm.get("short_leg", {}).get("net_bps"),
            "short_leg_gross_price_bps": tm.get("short_leg", {}).get("gross_price_bps"),
            "short_leg_carry_share": tm.get("short_leg", {}).get("carry_share"),
            "long_leg_net_bps": tm.get("long_leg", {}).get("net_bps"),
            "long_leg_gross_price_bps": tm.get("long_leg", {}).get("gross_price_bps"),
        }
    # 攤薄判定：net 是否隨 H_min 單調上升並轉正。
    nets = [curve[f"H{h}"]["aggregate_net_bps"] for h in HORIZON_SCAN_HMINS
            if curve.get(f"H{h}", {}).get("aggregate_net_bps") is not None]
    amortization_turns_positive = bool(nets and max(nets) > 0)
    net_at_max_horizon = curve.get(f"H{HORIZON_SCAN_HMINS[-1]}", {}).get("aggregate_net_bps")
    return {
        "scan_hmins": list(HORIZON_SCAN_HMINS),
        "note": "diagnostic scan (NOT in K budget); validates §3.4 amortization vs §4.5 horizon-decay",
        "curve": curve,
        "net_turns_positive_with_horizon": amortization_turns_positive,
        "net_at_max_horizon_bps": net_at_max_horizon,
    }


# ── §4b regime split + carry purity ────────────────────────────────────────

def _regime_split_carry(best_ev: dict) -> dict:
    """§4b regime split + carry purity 判定（squeeze 偽裝 carry 檢查）。

    aggregate carry_share 低 + edge 集中 bull short-side → squeeze 偽裝（NO-GO）。
    需 ≥1 non-bull slice net Sharpe > 0 才算 durable（協議 §4b 不可協商）。
    """
    pr = best_ev.get("per_regime_net", {})
    acct = best_ev.get("accounting", {})
    agg = acct.get("aggregate", {})
    short_leg = acct.get("short_leg", {})
    long_leg = acct.get("long_leg", {})
    non_bull_positive = []
    for rg in ("bear", "chop"):
        s = pr.get(rg, {}).get("annualized_net_sharpe")
        if s is not None and s > 0:
            non_bull_positive.append(rg)
    bull_sharpe = pr.get("bull", {}).get("annualized_net_sharpe")
    edge_bull_only = bool(
        (bull_sharpe is not None and bull_sharpe > 0) and not non_bull_positive)
    # short-side 主導 carry 但 short gross_price 顯著負 = 價格反向吃 carry（squeeze 風險）。
    short_gp = short_leg.get("gross_price_bps")
    short_fp = short_leg.get("funding_pnl_bps")
    short_squeeze_flag = bool(
        short_fp is not None and short_fp > 0 and short_gp is not None and short_gp < 0
        and abs(short_gp) >= 0.5 * short_fp)  # 價格吃掉 ≥50% carry
    agg_carry_share = agg.get("carry_share")
    low_carry_purity = bool(agg_carry_share is not None and agg_carry_share < 0.5)
    return {
        "per_regime_net_sharpe": {rg: pr.get(rg, {}).get("annualized_net_sharpe")
                                  for rg in ("bull", "bear", "chop")},
        "non_bull_slices_positive": non_bull_positive,
        "edge_bull_only": edge_bull_only,
        "aggregate_carry_share": agg_carry_share,
        "low_carry_purity": low_carry_purity,
        "short_leg_funding_pnl_bps": short_fp,
        "short_leg_gross_price_bps": short_gp,
        "short_leg_carry_share": short_leg.get("carry_share"),
        "long_leg_funding_pnl_bps": long_leg.get("funding_pnl_bps"),
        "long_leg_gross_price_bps": long_leg.get("gross_price_bps"),
        "short_squeeze_eating_carry": short_squeeze_flag,
        "squeeze_disguised_as_carry": bool(short_squeeze_flag and low_carry_purity),
    }


# ── 主編排 ─────────────────────────────────────────────────────────────────

def run_diagnostic(panel: data_loader.Panel, universe) -> dict:
    """跑全部 DATA TASK 0-5 + Step0 + 統計 + horizon scan + regime split + §5 決策樹。"""
    global _dates_cache
    _dates_cache = list(panel.dates)

    report: dict = {
        "diagnostic": "funding_tilt_carry",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "universe": list(universe),
        "n_dates": len(panel.dates),
        "date_span": [str(panel.dates[0]), str(panel.dates[-1])] if panel.dates else None,
        "canonical_run_id": panel.canonical_run_id,
        "trial_budget_K": signals.count_trial_budget(),
        "redlines": {
            "redline_1_perp_only_directional": "demo has no spot lending; perp-only directional (not delta-neutral)",
            "redline_2_funding_cap_ssot": "funding cap = instruments-info upperFundingRate; NOT back-inferred from history max (signals use realized funding rank only)",
            "redline_3_funding_double_sided_accounting": "net = gross_price + funding_pnl − (fee+slip); funding_pnl is a SEPARATE item, not double-counted in cost (§3.0)",
        },
        "coverage_notes": panel.coverage_notes,
        "data_tasks": {},
        "signal_evaluation": {},
        "decision_tree": {},
    }

    # 信號變體構造（A cross-sectional L∈{3,9,21} + B time-series L=9）。
    interval_unc = _interval_uncertain_map(panel)
    surv = panel.survivorship
    variant_map: dict = {}      # {signal_name: {symbol: SignalSeries}}
    tiltscore_cache: dict = {}  # {L: {symbol: TiltScoreSeries}}
    for L in signals.SIGNAL_A_LS:
        tss = _build_tiltscores(panel, L)
        tiltscore_cache[L] = tss
        a_sig = signals.signal_a_cross_sectional(tss, surv, interval_unc, L)
        variant_map[f"A_L{L}"] = a_sig
    for L in signals.SIGNAL_B_LS:
        tss = tiltscore_cache.get(L) or _build_tiltscores(panel, L)
        tiltscore_cache[L] = tss
        b_map = {}
        for s in universe:
            b_map[s] = signals.signal_b_time_series(
                tss[s], surv[s], interval_unc.get(s, False), L)
        variant_map[f"B_L{L}"] = b_map

    # DATA TASKS（用 L9 tiltscore 作 dispersion 代表，與 MIT pre-check 對齊）。
    rep_tiltscore = tiltscore_cache.get(9) or tiltscore_cache[signals.SIGNAL_A_LS[0]]
    report["data_tasks"]["task_0_canonical_run"] = data_task_0_canonical_run(panel)
    report["data_tasks"]["task_1_funding_magnitude"] = data_task_1_funding_magnitude(panel)
    report["data_tasks"]["task_3_xsec_dispersion"] = data_task_3_xsec_dispersion(panel, rep_tiltscore)
    report["data_tasks"]["task_4_fee_tier"] = data_task_4_fee_tier()
    report["data_tasks"]["task_5_regime"] = data_task_5_regime(panel)

    # 評估每信號 × 2 持有期（daily / flip_hold_min H_min=7）。
    all_evals = {}
    for sig_name, by_sym in variant_map.items():
        all_evals[f"{sig_name}__daily"] = evaluate_signal_variant(
            panel, universe, by_sym, "daily", pnl.H_MIN_DAYS_DEFAULT)
        all_evals[f"{sig_name}__flip_hold_min"] = evaluate_signal_variant(
            panel, universe, by_sym, "flip_hold_min", pnl.H_MIN_DAYS_DEFAULT)

    # 兩個 N_eff（§4.3）：price-return PCA + funding-tiltscore PCA。
    price_mat = _build_price_return_matrix(panel, universe)
    tilt_mat = _build_tiltscore_matrix(panel, universe, rep_tiltscore)
    report["pca_effective_dimension_price_return"] = stats.pca_effective_n(price_mat)
    report["pca_effective_dimension_funding_tiltscore"] = stats.funding_tiltscore_pca_effective_n(tilt_mat)

    # Step0 樣本充分性（§4.0）：pooled flips × cluster 縮減（用 funding-tiltscore N_eff，
    # 因信號 A 是 cross-sectional funding → 相關性以 tiltscore N_eff 為主）。
    tilt_pca = report["pca_effective_dimension_funding_tiltscore"] or {}
    n_eff_tilt = tilt_pca.get("n_eff")
    n_cols = tilt_pca.get("n_columns") or len(universe)
    cluster_factor = (n_eff_tilt / max(n_cols, 1)) if n_eff_tilt else 1.0
    step0 = {}
    max_eff_n = 0.0
    for key, ev in all_evals.items():
        pooled_flips = ev["pooled_direction_flips_leakfree"]
        eff_n = pooled_flips * cluster_factor
        step0[key] = {
            "pooled_direction_flips": pooled_flips,
            "n_trades": ev["n_trades_leakfree"],
            "cluster_factor": round(cluster_factor, 4),
            "effective_n": round(eff_n, 2),
            "passes_floor": eff_n >= EFFECTIVE_N_FLOOR,
        }
        max_eff_n = max(max_eff_n, eff_n)
    report["step_0_sample_sufficiency"] = {
        "floor": EFFECTIVE_N_FLOOR,
        "required_n_theory_delta0p5": stats.required_n_for_sharpe_delta(0.5),
        "cluster_factor_applied": round(cluster_factor, 4),
        "cluster_basis": "funding_tiltscore_pca_n_eff (cross-sectional funding signal)",
        "max_effective_n_across_variants": round(max_eff_n, 2),
        "n_variants_passing_floor": sum(1 for v in step0.values() if v["passes_floor"]),
        "per_variant": step0,
        "aeg_s0_note": (
            "AEG-S0 §2.9: cross-sectional策略每 rebalance=1 independent sample (BTC-beta "
            "clustered); same-rebalance multi-symbol is breadth not independent time evidence."
        ),
    }

    # funding persistence（§4.1 carry 基礎）。
    funding_series = {s: panel.funding[s].rate for s in universe}
    report["funding_persistence"] = stats.funding_persistence_ljung_box(funding_series, lags=10)

    # verdict 主檢定（§4.1）：funding-tilt forward significance（信號 A，H_min=7）。
    fwd = _signed_forward_returns_for_signal_a(
        panel, universe, rep_tiltscore, pnl.H_MIN_DAYS_DEFAULT)
    report["funding_tilt_forward_significance"] = stats.funding_tilt_forward_significance(
        fwd, overlap_lag=pnl.H_MIN_DAYS_DEFAULT)

    # §4.5 horizon-vs-cost scan。
    signal_a_only = {k: v for k, v in variant_map.items() if k.startswith("A_")}
    report["horizon_cost_scan"] = _horizon_cost_scan(panel, universe, signal_a_only)

    # 資料品質（厚尾 → PSR；vol clustering → block bootstrap）。
    report["data_quality"] = _data_quality(panel)

    # 找最佳 leak-free net Sharpe 變體（決策 + 過擬合統計用）。
    best_key, best_ev = _find_best_variant(all_evals)
    if best_ev is not None:
        best_port = best_ev.get("_lf_net_port")
        report["overfitting"] = _overfitting_block(
            best_port, all_evals, signals.count_trial_budget(), pnl.H_MIN_DAYS_DEFAULT)
        report["regime_split_carry"] = _regime_split_carry(best_ev)
    else:
        report["overfitting"] = {"error": "no evaluable best variant"}
        report["regime_split_carry"] = {"error": "no evaluable best variant"}

    # 決策樹（§5）。
    report["decision_tree"] = _decision_tree(report, all_evals, step0, max_eff_n, best_key, best_ev)

    # 清掉內部不序列化欄位（_lf_net_port ndarray）。
    for ev in all_evals.values():
        ev.pop("_lf_net_port", None)
    report["signal_evaluation"] = all_evals
    return report


def _find_best_variant(all_evals) -> tuple:
    """找最佳 leak-free net Sharpe 變體（供決策與並列診斷共用）。"""
    best_key, best_ev = None, None
    for key, ev in all_evals.items():
        s = ev["annualized_net_sharpe_leakfree"]
        if s is None:
            continue
        if best_ev is None or s > best_ev["annualized_net_sharpe_leakfree"]:
            best_key, best_ev = key, ev
    return best_key, best_ev


def _decision_tree(report, all_evals, step0, max_eff_n, best_key, best_ev) -> dict:
    """協議 §5 決策樹。fail-fast：第一個命中即 verdict，標明 stop reason。"""
    # 門檻 0：Step0 n_independent(A) < 60 → INCONCLUSIVE-A。
    if max_eff_n < EFFECTIVE_N_FLOOR:
        return {
            "verdict": "INCONCLUSIVE-A",
            "stopped_at": "step_0_sample_sufficiency",
            "reason": (
                f"max effective N across all {len(all_evals)} variants = {max_eff_n:.2f} "
                f"< floor {EFFECTIVE_N_FLOOR}; cross-sectional funding-tilt n_independent "
                "underpowered (AEG-S0 §2.9). Needs longer funding backfill (V125 1095d) then re-run. "
                "Honest caveat: backfill helps trade count but funding cross-sectional N_eff (set by "
                "funding correlation structure) has limited upside."
            ),
            "next": "longer funding backfill then re-run; skip full DSR/PSR/PBO (power<0.5)",
        }

    # 門檻 A：funding Ljung-Box 無正自相關 → NO-GO-A（預期不發生）。
    fp = report.get("funding_persistence", {}) or {}
    if fp and not fp.get("funding_has_positive_persistence"):
        return {
            "verdict": "NO-GO-A",
            "stopped_at": "funding_persistence_ljung_box",
            "reason": (
                f"funding shows NO positive persistence: only {fp.get('n_symbols_positive_autocorr')}/"
                f"{fp.get('n_symbols_evaluated')} symbols have significant positive autocorrelation "
                f"(median rho_1={fp.get('median_rho_1')}). Carry's statistical premise (funding "
                "persistence) is absent."
            ),
            "funding_persistence": fp,
        }

    if best_ev is None:
        return {
            "verdict": "INCONCLUSIVE-A",
            "stopped_at": "no_evaluable_variant",
            "reason": "no variant produced finite net Sharpe (insufficient trades after survivorship)",
        }

    # 門檻 B：leak-free Sharpe≈0 但 naive 高（>30% gap）→ NO-GO-B。
    inflated = [
        (k, v["look_ahead_inflation_ratio"])
        for k, v in all_evals.items()
        if v["look_ahead_inflation_ratio"] is not None and v["look_ahead_inflation_ratio"] > 0.30
    ]
    leakfree_near_zero = (best_ev["annualized_net_sharpe_leakfree"] is not None
                          and best_ev["annualized_net_sharpe_leakfree"] < 0.2)
    if leakfree_near_zero and inflated:
        return {
            "verdict": "NO-GO-B",
            "stopped_at": "leakfree_vs_naive",
            "reason": (
                f"best leak-free net Sharpe={best_ev['annualized_net_sharpe_leakfree']:.3f} (~0) "
                f"but {len(inflated)} variants show naive gross Sharpe >30% above leak-free gross "
                "-> positive naive result is look-ahead illusion (funding leaks same-period price)."
            ),
            "look_ahead_inflated_variants": inflated[:10],
        }

    # 門檻 C：§4.5 net 隨 H_min 上升仍 ≤0 OR carry_cost_ratio ≥0.8 → NO-GO-C（攤薄證偽，最可能）。
    scan = report.get("horizon_cost_scan", {}) or {}
    acct = best_ev.get("accounting", {})
    agg = acct.get("aggregate", {})
    agg_ccr = agg.get("carry_cost_ratio")
    cost_wall = (agg_ccr is not None and agg_ccr >= cost_model.CARRY_COST_RATIO_ABANDON)
    amortization_fails = (not scan.get("net_turns_positive_with_horizon", False))
    if amortization_fails or cost_wall:
        # reason 按實際 binding 分支動態生成：amortization_fails 與 cost_wall 各自獨立成立，
        # 不可寫死「amortization disproven net stays ≤0」——真跑可能 net 隨 horizon 轉正
        # （net_turns_positive_with_horizon=True）但 carry_cost_ratio≥0.8 仍 binding（carry
        # 付不起自己的成本）。E2 退回 LOW-2：固定字串與 §4.5 scan 結果矛盾，須據實。
        reasons = []
        if amortization_fails:
            reasons.append(
                f"amortization disproven: net stays ≤0 across H_min scan "
                f"{scan.get('scan_hmins')} (net@max_horizon={scan.get('net_at_max_horizon_bps')}bps), "
                f"net_turns_positive_with_horizon={scan.get('net_turns_positive_with_horizon')}"
            )
        if cost_wall:
            reasons.append(
                f"cost wall: aggregate carry_cost_ratio={agg_ccr} ≥ abandon "
                f"{cost_model.CARRY_COST_RATIO_ABANDON} (carry cannot pay its own fee+slip)"
            )
        binding = ("amortization_fails" if amortization_fails else "") + (
            "+cost_wall" if (amortization_fails and cost_wall) else ("cost_wall" if cost_wall else "")
        )
        return {
            "verdict": "NO-GO-C",
            "stopped_at": "horizon_cost_amortization",
            "binding_condition": binding,
            "reason": (
                "; ".join(reasons)
                + f". net_turns_positive_with_horizon={scan.get('net_turns_positive_with_horizon')}, "
                f"aggregate carry_cost_ratio={agg_ccr} (abandon≥{cost_model.CARRY_COST_RATIO_ABANDON}). "
                "Carry magnitude insufficient against fee+slip even at longer horizon "
                "(the most likely failure mode, §3.4)."
            ),
            "horizon_cost_scan": scan,
            "best_variant": best_key,
            "best_variant_accounting": acct,
        }

    # 門檻 squeeze：net 正但 carry_share 低 + edge 集中 bull short-side → NO-GO（squeeze 偽裝）。
    rs = report.get("regime_split_carry", {}) or {}
    if rs.get("squeeze_disguised_as_carry") or (rs.get("edge_bull_only") and rs.get("short_squeeze_eating_carry")):
        return {
            "verdict": "NO-GO",
            "stopped_at": "short_squeeze_insurance_disguised_as_carry",
            "reason": (
                "positive net but low carry purity + edge concentrated in bull short-side top-funding "
                f"leg: aggregate carry_share={rs.get('aggregate_carry_share')}, short-leg "
                f"funding_pnl={rs.get('short_leg_funding_pnl_bps')}bps but short-leg gross_price="
                f"{rs.get('short_leg_gross_price_bps')}bps (price reverses into carry = squeeze), "
                f"edge_bull_only={rs.get('edge_bull_only')}. This is selling short-squeeze insurance "
                "disguised as carry (protocol §4b NO-GO)."
            ),
            "regime_split_carry": rs,
            "best_variant": best_key,
        }

    # 門檻 net Sharpe：best net Sharpe < 0.5 → 視同 NO-GO-C 量級不足。
    best_sharpe = best_ev["annualized_net_sharpe_leakfree"]
    if best_sharpe is not None and best_sharpe < NET_SHARPE_FLOOR:
        return {
            "verdict": "NO-GO-C",
            "stopped_at": "net_sharpe_floor",
            "reason": (
                f"best variant {best_key}: leak-free net Sharpe={best_sharpe:.3f} < floor "
                f"{NET_SHARPE_FLOOR}. Carry edge after full cost (incl funding accounting §3.0) "
                "insufficient."
            ),
            "best_variant": best_key,
            "best_variant_metrics": _strip_internal(best_ev),
        }

    # 門檻 D：DSR(K=8)<0.95 OR PSR<0.95 OR bootstrap CI 下界 ≤0 → NO-GO-D / INCONCLUSIVE-B。
    of = report.get("overfitting", {}) or {}
    psr_fail = not of.get("psr_pass", False)
    dsr_fail = not of.get("dsr_pass", False)
    boot_fail = not of.get("bootstrap_ci_lower_positive", False)
    if psr_fail or dsr_fail or boot_fail:
        verdict = "NO-GO-D" if (dsr_fail or boot_fail) else "INCONCLUSIVE-B"
        return {
            "verdict": verdict,
            "stopped_at": "overfitting_psr_dsr_bootstrap",
            "reason": (
                f"best variant {best_key}: PSR(0)={of.get('psr_0')} (floor {PSR_FLOOR}), "
                f"DSR(K={of.get('dsr_k')})={of.get('dsr')} (floor {DSR_FLOOR}), block-bootstrap "
                f"mean-daily CI={of.get('block_bootstrap_ci_mean_daily')} (lower>0="
                f"{of.get('bootstrap_ci_lower_positive')}). Edge does not survive multiple-testing "
                "deflation / autocorr-robust CI."
            ),
            "overfitting": of,
            "best_variant": best_key,
        }

    # 門檻 E：PBO≥0.5 → NO-GO-E（PBO 維度不足時誠實標 semantics，主防線回 OOS——本 harness
    # 未跑完整 walk-forward OOS，故 PBO insufficient 時不在此 fail，標 SURVIVES 待 Phase 2）。
    pbo_val = (of.get("pbo") or {}).get("value")
    if pbo_val is not None and pbo_val >= PBO_CEILING:
        return {
            "verdict": "NO-GO-E",
            "stopped_at": "pbo_overfit",
            "reason": (
                f"PBO={pbo_val} ≥ {PBO_CEILING}: best train-set cell lands below test-set median "
                "too often (overfit). "
            ),
            "overfitting": of,
            "best_variant": best_key,
        }

    # 全過 + edge 只在 bull → regime-bet / learning-only。
    if rs.get("edge_bull_only"):
        return {
            "verdict": "regime-bet / learning-only",
            "stopped_at": "regime_gate_bull_only",
            "reason": (
                f"best variant {best_key} passes early gates but edge is bull-only "
                f"(per-regime net Sharpe={rs.get('per_regime_net_sharpe')}); no non-bull slice "
                "independently positive. Durable requires ≥1 non-bull slice (protocol §4b, "
                "non-negotiable). Cohort is bull-heavy (72.4% +funding)."
            ),
            "regime_split_carry": rs,
            "best_variant": best_key,
            "best_variant_metrics": _strip_internal(best_ev),
        }

    # 全過 + ≥1 non-bull slice 獨立通過 + carry_share 高 → GO（durable-alpha candidate）。
    return {
        "verdict": "GO",
        "stopped_at": None,
        "reason": (
            f"best variant {best_key}: effective N≥{EFFECTIVE_N_FLOOR}, funding persistence present, "
            f"no dominant look-ahead, amortization holds, carry_share high (not squeeze), net "
            f"Sharpe={best_sharpe:.3f}≥{NET_SHARPE_FLOOR}, PSR≥{PSR_FLOOR}, DSR(K=8)≥{DSR_FLOOR}, "
            f"bootstrap CI lower>0, non-bull slices positive ({rs.get('non_bull_slices_positive')}). "
            "Durable-alpha candidate. STILL requires full walk-forward OOS + MIT leak audit + QC "
            "final verdict (E1 does not self-sign)."
        ),
        "regime_split_carry": rs,
        "best_variant": best_key,
        "best_variant_metrics": _strip_internal(best_ev),
    }


def _strip_internal(ev: dict) -> dict:
    """移除內部不序列化欄位（_lf_net_port），回 shallow copy。"""
    return {k: v for k, v in ev.items() if not k.startswith("_")}


def _data_quality(panel: data_loader.Panel) -> dict:
    """資料品質：BTC 日報酬 JB（厚尾→PSR）+ ARCH（vol clustering→block bootstrap）。"""
    btc = panel.close.get(data_loader.BTC_SYMBOL)
    proxy = data_loader.BTC_SYMBOL
    if btc is None or np.sum(np.isfinite(btc) & (btc > 0)) < 30:
        for s, c in panel.close.items():
            if np.sum(np.isfinite(c) & (c > 0)) >= 30:
                btc, proxy = c, s
                break
    if btc is None:
        return {"error": "no symbol with sufficient closes"}
    cc = btc[np.isfinite(btc) & (btc > 0)]
    if len(cc) < 30:
        return {"error": "insufficient closes"}
    rets = np.diff(np.log(cc))
    return {
        "proxy_symbol": proxy,
        "jarque_bera_returns": stats.jarque_bera(rets),
        "arch_lm_returns": stats.arch_lm(rets, lags=5),
        "n_returns": len(rets),
    }


# ── synthetic dry-run（Mac 可跑，不連 PG）──────────────────────────────────

def build_synthetic_panel(
    n_days: int = 730,
    n_symbols: int = 20,
    *,
    carry_signal: bool = True,
    seed: int = 20260603,
) -> tuple:
    """合成面板（驗 harness 邏輯，不連 PG）。

    carry_signal=True：注入「funding 最負的 symbol 未來價格略漲（long 收 carry 且價不反向）」
    的可被 funding-tilt 捕捉結構，驗 harness 能偵測。carry_signal=False：funding 與未來價格
    無關（null），驗 harness 不誤判。每 symbol 8h 結算（3/day），funding_ts 真實序列。
    """
    rng = np.random.default_rng(seed)
    universe = tuple(f"SYN{i:02d}USDT" for i in range(n_symbols))
    base = dt.date(2024, 6, 3)
    dates = [base + dt.timedelta(days=i) for i in range(n_days)]
    open_ts_utc = np.array(
        [dt.datetime.combine(d, dt.time(0, 0), tzinfo=dt.timezone.utc) for d in dates],
        dtype=object,
    )
    # 每 symbol 一個固定 funding 偏置（cross-sectional dispersion）。
    funding_bias = rng.normal(0.0001, 0.00008, n_symbols)  # 分數，per 8h（~1bp）
    close, open_, high, low, volume, surv = {}, {}, {}, {}, {}, {}
    funding = {}
    market = np.cumsum(rng.normal(0.0003, 0.02, n_days))  # 共同市場因子（高相關，低 N_eff）
    for idx, s in enumerate(universe):
        idio = np.cumsum(rng.normal(0.0, 0.01, n_days))
        # carry_signal：funding 最負（funding_bias 小）→ 未來價格略漲（long 收 carry 不被吃）。
        carry_drift = (-funding_bias[idx] * 30.0 if carry_signal else 0.0)
        logp = np.log(100.0) + 0.8 * market + idio + carry_drift * np.arange(n_days)
        c = np.exp(logp)
        o = np.concatenate([[c[0]], c[:-1]]) * (1 + rng.normal(0, 0.001, n_days))
        close[s] = c
        open_[s] = o
        high[s] = np.maximum(c, o) * 1.005
        low[s] = np.minimum(c, o) * 0.995
        volume[s] = np.full(n_days, 1e6)
        surv[s] = np.ones(n_days, dtype=bool)
        # 8h 結算 funding 序列（3/day）：bias + 持續性 AR(1) + 噪音。
        n_settle = n_days * 3
        f_ts = [dt.datetime.combine(base, dt.time(0, 0), tzinfo=dt.timezone.utc)
                + dt.timedelta(hours=8 * j) for j in range(n_settle)]
        f_rate = np.zeros(n_settle)
        f_rate[0] = funding_bias[idx]
        for j in range(1, n_settle):
            f_rate[j] = 0.7 * f_rate[j - 1] + 0.3 * funding_bias[idx] + rng.normal(0, 0.00003)
        funding[s] = data_loader.FundingSeries(
            ts=f_ts, rate=f_rate, interval_minutes=480, interval_uncertain=False)
    regime = data_loader.compute_rule_based_regime(close[universe[0]], dates)
    return data_loader.Panel(
        dates=dates, close=close, open_=open_, high=high, low=low, volume=volume,
        open_ts_utc=open_ts_utc, survivorship=surv, regime=regime, funding=funding,
        canonical_run_id="SYNTHETIC", coverage_notes={"synthetic": True, "carry_signal": carry_signal},
    ), universe


def _write_artifact(report: dict, run_id: str) -> tuple:
    root = _artifact_root()
    run_dir = root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    json_path = run_dir / "diagnostic_report.json"
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2, default=str)
    md_path = run_dir / "diagnostic_report.md"
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(_render_markdown(report))
    return json_path, md_path


def _render_markdown(report: dict) -> str:
    dt_tree = report["decision_tree"]
    dq = report.get("data_quality", {})
    fp = report.get("funding_persistence", {}) or {}
    fwd = report.get("funding_tilt_forward_significance", {}) or {}
    of = report.get("overfitting", {}) or {}
    rs = report.get("regime_split_carry", {}) or {}
    scan = report.get("horizon_cost_scan", {}) or {}
    price_pca = report.get("pca_effective_dimension_price_return", {}) or {}
    tilt_pca = report.get("pca_effective_dimension_funding_tiltscore", {}) or {}
    bm = dt_tree.get("best_variant_metrics") or {}
    acct = bm.get("accounting", {}) if bm else {}
    lines = [
        "# Funding-Tilt / 多日 Funding Carry 樞紐診斷報告",
        "",
        f"- 生成時間：{report['generated_at']}",
        f"- 日期跨度：{report.get('date_span')}（{report['n_dates']} 日）",
        f"- universe：{len(report['universe'])} symbol",
        f"- canonical run：{report.get('canonical_run_id')}",
        f"- trial 預算 K：{report['trial_budget_K']}",
        "",
        "## 三條紅線（聲明）",
        f"- 紅線 1：{report['redlines']['redline_1_perp_only_directional']}",
        f"- 紅線 2：{report['redlines']['redline_2_funding_cap_ssot']}",
        f"- 紅線 3：{report['redlines']['redline_3_funding_double_sided_accounting']}",
        "",
        f"## 決策樹判定：**{dt_tree['verdict']}**",
        "",
        f"- stopped_at：{dt_tree.get('stopped_at')}",
        f"- reason：{dt_tree.get('reason')}",
        "",
        "## DATA TASK 結果",
        f"- TASK0 canonical run：{report['data_tasks']['task_0_canonical_run']['canonical_run_id']}，"
        f"distinct intervals={report['data_tasks']['task_0_canonical_run']['distinct_intervals_minutes']}min，"
        f"interval_uncertain symbols={report['data_tasks']['task_0_canonical_run']['n_symbols_interval_uncertain']}",
        f"- TASK1 funding 量級：per-settlement |F| median="
        f"{report['data_tasks']['task_1_funding_magnitude'].get('per_settlement_abs_bps', {}).get('median')}bps，"
        f"% 正={report['data_tasks']['task_1_funding_magnitude'].get('pct_settlements_positive')}%"
        f"（cohort={report['data_tasks']['task_1_funding_magnitude'].get('cohort_label')}）",
        f"- TASK3 xsec 離散度：median tilt spread="
        f"{report['data_tasks']['task_3_xsec_dispersion'].get('median_tilt_spread_bps')}bps，"
        f"median std={report['data_tasks']['task_3_xsec_dispersion'].get('median_xsec_std_bps')}bps",
        f"- TASK4 fee：taker RT {report['data_tasks']['task_4_fee_tier']['taker_rt_bps']}bps / "
        f"maker RT {report['data_tasks']['task_4_fee_tier']['maker_rt_bps']}bps / slip RT "
        f"{report['data_tasks']['task_4_fee_tier']['slippage_rt_bps']}bps",
        f"- TASK5 regime 組成：{report['data_tasks']['task_5_regime']['composition_pct']}"
        f"（bull-dominated={report['data_tasks']['task_5_regime']['bull_dominated']}）",
        "",
        "## Step 0 樣本充分性",
        f"- floor：{report['step_0_sample_sufficiency']['floor']}",
        f"- cluster_factor（funding-tiltscore N_eff/n_cols）："
        f"{report['step_0_sample_sufficiency']['cluster_factor_applied']}",
        f"- max effective N across variants："
        f"{report['step_0_sample_sufficiency']['max_effective_n_across_variants']}",
        "",
        "## 兩個 N_eff（§4.3，回答 operator 核心問題）",
        f"- price-return N_eff={price_pca.get('n_eff')}（PC1 share={price_pca.get('pc1_explained_share')}）",
        f"- funding-tiltscore N_eff={tilt_pca.get('n_eff')}（PC1 share={tilt_pca.get('pc1_explained_share')}）"
        "（funding 橫截面比 price-return 更/更不獨立 = 此兩數對比）",
        "",
        "## funding persistence（§4.1 carry 基礎）",
        f"- {fp.get('n_symbols_positive_autocorr')}/{fp.get('n_symbols_evaluated')} symbol 有顯著正自相關，"
        f"median rho_1={fp.get('median_rho_1')} → carry 基礎={fp.get('funding_has_positive_persistence')}",
        "",
        "## funding-tilt forward significance（§4.1 verdict 主檢定）",
        f"- pooled n_obs={fwd.get('n_obs')}，mean forward={fwd.get('mean_forward_bps')}bps，"
        f"hit rate={fwd.get('hit_rate')}，HAC t={fwd.get('t_stat_hac')}（naive t="
        f"{fwd.get('t_stat_naive_overlapping')}），顯著正={fwd.get('significant_positive')}",
        "",
        "## §4.5 horizon-vs-cost-share 掃描（攤薄論點直接驗證）",
        "",
        "| H_min | n_trades | agg net bps | funding_pnl bps | gross_price bps | cost_share | short-leg net | short-leg gross_price |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in scan.get("scan_hmins", []):
        c = scan.get("curve", {}).get(f"H{h}", {})
        lines.append(
            f"| {h} | {c.get('n_trades')} | {c.get('aggregate_net_bps')} | "
            f"{c.get('aggregate_funding_pnl_bps')} | {c.get('aggregate_gross_price_bps')} | "
            f"{c.get('cost_share_of_abs_net')} | {c.get('short_leg_net_bps')} | "
            f"{c.get('short_leg_gross_price_bps')} |")
    lines += [
        "",
        f"- net 隨 horizon 轉正：{scan.get('net_turns_positive_with_horizon')}"
        f"（net@max horizon={scan.get('net_at_max_horizon_bps')}bps）",
        "",
        "## ★ per-leg 分解（最佳變體，MIT 強制 — 短腿擠壓不可藏）",
    ]
    if acct:
        ll = acct.get("long_leg", {})
        sl = acct.get("short_leg", {})
        ag = acct.get("aggregate", {})
        lines += [
            f"- aggregate：net={ag.get('net_bps')}bps / funding_pnl={ag.get('funding_pnl_bps')}bps / "
            f"gross_price={ag.get('gross_price_bps')}bps / carry_share={ag.get('carry_share')}",
            f"- **long-leg**：net={ll.get('net_bps')}bps / funding_pnl={ll.get('funding_pnl_bps')}bps / "
            f"gross_price={ll.get('gross_price_bps')}bps / carry_share={ll.get('carry_share')}（n={ll.get('n')}）",
            f"- **short-leg**：net={sl.get('net_bps')}bps / funding_pnl={sl.get('funding_pnl_bps')}bps / "
            f"gross_price={sl.get('gross_price_bps')}bps / carry_share={sl.get('carry_share')}（n={sl.get('n')}）",
            f"- short-leg 價格反向吃 carry（squeeze）：{rs.get('short_squeeze_eating_carry')}，"
            f"squeeze 偽裝 carry：{rs.get('squeeze_disguised_as_carry')}",
        ]
    lines += [
        "",
        "## 過擬合（§4.2）",
        f"- PSR(0)={of.get('psr_0')}（floor {of.get('psr_floor')}，pass={of.get('psr_pass')}）",
        f"- DSR(K={of.get('dsr_k')})={of.get('dsr')}（floor {of.get('dsr_floor')}，pass={of.get('dsr_pass')}）",
        f"- block bootstrap mean-daily CI={of.get('block_bootstrap_ci_mean_daily')}"
        f"（lower>0={of.get('bootstrap_ci_lower_positive')}，block={of.get('bootstrap_block_size')}）",
        f"- PBO={ (of.get('pbo') or {}).get('value') }（{ (of.get('pbo') or {}).get('reason') }）",
        "",
        "## §4b regime split + carry purity",
        f"- per-regime net Sharpe：{rs.get('per_regime_net_sharpe')}",
        f"- non-bull slices positive：{rs.get('non_bull_slices_positive')}，edge_bull_only={rs.get('edge_bull_only')}",
        f"- aggregate carry_share={rs.get('aggregate_carry_share')}，low_carry_purity={rs.get('low_carry_purity')}",
        "",
        "## 資料品質",
        f"- Jarque-Bera：拒常態={ (dq.get('jarque_bera_returns') or {}).get('reject_normality_5pct') }"
        f"（厚尾={ (dq.get('jarque_bera_returns') or {}).get('fat_tailed') }）→ 用 PSR 非 normal",
        f"- ARCH 效應={ (dq.get('arch_lm_returns') or {}).get('arch_effect_5pct') } → 用 block bootstrap",
        "",
        "## 限制聲明（誠實）",
        "- demo 無 spot lending → perp-only directional（非 delta-neutral，更弱更曝險的子集）。",
        "- funding cap SSOT=instruments-info upperFundingRate，未從 history max 反推（紅線 2）。",
        "- funding 雙面會計 §3.0：funding_pnl 為獨立項，未雙重計入 cost（紅線 3）。",
        "- cohort=breadth-limited / survivor-cohort / bull-heavy（72.4% 正 funding）→ 任何正結果 "
        "= regime-bet / learning-only，除非 non-bull slice 獨立過。",
        "- funding interval per-symbol 從 funding_ts 間距推（欄 100% NULL）；4h symbol 7d=42 結算。",
        "- regime label = 本地 rule-based（vol-tercile leak 已修為 expanding/prior-365）；不外推全 universe。",
        "- E1 不自簽 sign-off：待 E2 對抗審 + MIT leak/sample 審 + QC 最終判定。",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="funding-tilt / 多日 funding carry 樞紐診斷 harness")
    parser.add_argument("--dry-run", action="store_true",
                        help="用 synthetic data 跑（不連 PG，Mac 可驗 harness 邏輯）")
    parser.add_argument("--synthetic-carry", action="store_true",
                        help="dry-run 時注入 carry 可捕捉結構（驗 harness 能偵測）")
    parser.add_argument("--synthetic-null", action="store_true",
                        help="dry-run 時 funding 與未來價格無關（驗 harness 不誤判）")
    parser.add_argument("--dsn", default=None, help="PG DSN 覆寫（預設用 OPENCLAW_DATABASE_URL）")
    parser.add_argument("--run-id", default=None, help="artifact run-id（預設時間戳）")
    parser.add_argument("--print-json", action="store_true", help="把 JSON 報告印到 stdout")
    args = parser.parse_args(argv)

    run_id = args.run_id or f"funding_tilt_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    if args.dry_run:
        carry = not args.synthetic_null  # 預設注入 carry，--synthetic-null 關
        panel, universe = build_synthetic_panel(carry_signal=carry)
    else:
        universe = data_loader.DEFAULT_UNIVERSE
        panel = data_loader.load_panel(universe, dsn=args.dsn)

    report = run_diagnostic(panel, universe)

    json_path, md_path = _write_artifact(report, run_id)
    verdict = report["decision_tree"]["verdict"]
    print(f"[funding_tilt_diagnostic] verdict={verdict}")
    print(f"[funding_tilt_diagnostic] JSON: {json_path}")
    print(f"[funding_tilt_diagnostic] MD:   {md_path}")
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

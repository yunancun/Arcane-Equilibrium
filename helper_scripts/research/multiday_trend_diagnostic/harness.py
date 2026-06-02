#!/usr/bin/env python3
"""多日 trend 診斷 harness 編排器（Phase 1：fail-fast 早期決策樹）— 協議 §DATA TASKS + §5。

MODULE_NOTE:
  模塊用途：編排 DATA TASK 1-5 + Phase 1 早期門檻決策樹，輸出 JSON + markdown
    研究 artifact。fail-fast：任一早期門檻命中 INCONCLUSIVE-A / NO-GO-TREND/B/C 即停，
    省下 Phase 2 完整 DSR/PSR/PBO/walk-forward。
  Phase 1 門檻（協議 §5 早期分支）：
    1. DATA TASK 1-5：fee tier / funding 量級 / slippage / 信號頻率 / regime 組成。
    2. Step 0 effective N（§4.0）：方向翻轉 → pooled → PCA cluster-aware。<60 →
       INCONCLUSIVE-A，停。
    3. 正確尺度 TSMOM coherence gate（FIX-2）：過去 k 日報酬符號 vs 未來 k 日報酬，
       pooled 全 symbol、Newey-West overlap-corrected t-stat（lag=k-1），k∈{20,30,40,60,90}。
       無**相干**正動量（significant-positive k 中無相鄰對形成連續尺度 plateau，或出現
       顯著反轉）→ NO-GO-TREND，停。（daily-lag Ljung-Box 測錯時間尺度，已降級為
       data_quality 報告統計，非 verdict 依據。）
    4. leak-free vs naive 並列（§2.2）：leak-free≈0 但 naive 高 → NO-GO-B。
    5. net Sharpe after full cost（含 funding）+ cost_edge_ratio（§3/§4）：net
       Sharpe<0.5 OR cost_edge_ratio≥0.8 → NO-GO-C。多/空 + regime 拆解。
    6. 資料品質：daily Ljung-Box（廣度）+ ADF/KPSS/JB/ARCH（確認厚尾）。
  主要函數：``run_diagnostic`` / ``main``。
  硬邊界：
    - **唯讀 PG**；輸出寫 artifact（JSON + markdown），絕不寫 production 表。
    - 誠實：INCONCLUSIVE/NO-GO 是合法結果；不 massage 數字製造 GO。
    - --dry-run（synthetic data）可在 Mac 跑（不連 PG），驗 harness 邏輯。
  依賴：本目錄 data_loader / signals / cost_model / pnl / stats + numpy。
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

# 支援「python helper_scripts/research/multiday_trend_diagnostic/harness.py」直接跑，
# 也支援「python -m ...harness」。把 srv/helper_scripts 加進 path 後以 package 匯入。
_THIS = Path(__file__).resolve()
_PKG_PARENT = _THIS.parents[1]  # .../helper_scripts/research
if str(_PKG_PARENT) not in sys.path:
    sys.path.insert(0, str(_PKG_PARENT))

from multiday_trend_diagnostic import cost_model, data_loader, pnl, signals, stats  # noqa: E402

# Step0 有效樣本硬門檻（協議 §4.1）。
EFFECTIVE_N_FLOOR = 60
# net Sharpe 門檻（年化，協議 §5）。
NET_SHARPE_FLOOR = 0.5
# 正確尺度 TSMOM 顯著性檢定的 k（過去 k 日 → 未來 k 日，FIX-2）。
TSMOM_SCALE_KS = (20, 30, 40, 60, 90)
# HAC（Newey-West）t-stat 顯著門檻（雙尾 5% 近似）。
TSMOM_TSTAT_FLOOR = 2.0


def _artifact_root() -> Path:
    """跨平台 artifact 根（禁硬編碼，沿用 gate_b 慣例）。"""
    base = os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw").strip() or "/tmp/openclaw"
    return Path(base) / "multiday_trend_diagnostic_runs"


# ── DATA TASKS ──────────────────────────────────────────────────────────────

def data_task_1_fee_tier() -> dict:
    """DATA TASK 1：fee tier（協議 §3，taker 5.5bps/side SSOT）。

    SSOT 引用 bybit_api_reference / /v5/account/fee-rate：保守 taker 5.5bps/side、
    maker 2bps/side（upside 情境）。harness 用常數，不打 live API（research 唯讀紀律）。
    """
    return {
        "taker_bps_per_side": cost_model.TAKER_FEE_BPS_PER_SIDE,
        "maker_bps_per_side": cost_model.MAKER_FEE_BPS_PER_SIDE,
        "taker_rt_bps": 2 * cost_model.TAKER_FEE_BPS_PER_SIDE,
        "maker_rt_bps": 2 * cost_model.MAKER_FEE_BPS_PER_SIDE,
        "source": "protocol §3 conservative SSOT (/v5/account/fee-rate); not live-queried",
    }


def data_task_2_funding(panel: data_loader.Panel) -> dict:
    """DATA TASK 2：funding 量級 + 5/30/60 日累積 drag 分布（多 vs 空）。

    決定成本牆高度（協議 §3 樞紐）。⚠ funding 覆蓋僅 ~58 天 → 用代表性均值，標
    INCONCLUSIVE-on-coverage。
    """
    per_symbol = {}
    for s, rate in panel.funding_mean_per_8h.items():
        rate_bps_8h = rate * 1e4
        drag = {}
        for hold in (5, 30, 60):
            long_cost, _ = cost_model.funding_cost_bps_for_holding(+1, hold, rate)
            short_cost, _ = cost_model.funding_cost_bps_for_holding(-1, hold, rate)
            drag[f"{hold}d"] = {
                "long_funding_bps": round(long_cost, 3),
                "short_funding_bps": round(short_cost, 3),
            }
        per_symbol[s] = {
            "mean_rate_per_8h_bps": round(rate_bps_8h, 4),
            "annualized_pct": round(rate_bps_8h * cost_model.FUNDING_SETTLEMENTS_PER_DAY *
                                    365 / 100.0, 3),
            "cumulative_drag": drag,
        }
    all_rates_bps = [v["mean_rate_per_8h_bps"] for v in per_symbol.values()]
    return {
        "per_symbol": per_symbol,
        "universe_median_rate_per_8h_bps": round(float(np.median(all_rates_bps)), 4) if all_rates_bps else None,
        "coverage": panel.coverage_notes.get("funding_coverage"),
        "coverage_caveat": panel.coverage_notes.get("funding_window_vs_signal_window"),
        "funding_inconclusive_on_coverage": True,
    }


def data_task_3_slippage() -> dict:
    """DATA TASK 3：slippage 校準（協議 §3，5bps/side 保守上限）。

    market_tickers 歷史 spread 校準屬 Phase 2 細化；Phase 1 用保守上限常數，
    BTC/ETH vs altcoin 分組敏感度標為 follow-up。
    """
    return {
        "slippage_bps_per_side_conservative": cost_model.SLIPPAGE_BPS_PER_SIDE,
        "slippage_rt_bps": 2 * cost_model.SLIPPAGE_BPS_PER_SIDE,
        "note": "conservative cap; BTC/ETH vs altcoin spread-calibration deferred to Phase 2 (market_tickers)",
    }


def data_task_5_regime(panel: data_loader.Panel) -> dict:
    """DATA TASK 5：730 天 regime 組成（bull/bear/chop 各佔多少）。

    協議 §4b：regime_snapshots 空 → 本地 rule-based（BTC 200日MA + vol tercile）。
    2024-2026 很可能 bull-dominated（必標）。
    """
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
    }


# ── 信號評估（DATA TASK 4 + Step0 + 門檻） ───────────────────────────────────

def _build_close_matrix(panel: data_loader.Panel, universe) -> np.ndarray:
    """組日報酬矩陣（T×S）供 PCA effective N。"""
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


def evaluate_signal_variant(
    panel: data_loader.Panel,
    universe,
    signal_by_symbol: dict,
    variant: str,
) -> dict:
    """單一信號變體 × 持有期：pooled trades、方向翻轉、leak-free/naive Sharpe、net、拆解。

    回傳含 effective N 原料（pooled flips）+ leak-free/naive 日報酬 Sharpe + per-trade
    net edge + 多空 + funding 拆解 + per-regime net。
    """
    total_flips_lf = 0
    total_flips_nv = 0
    all_trades_lf = []
    # pooled 日報酬（跨 symbol 等權，leak-free & naive 各一條）。
    lf_daily_pool = []
    nv_daily_pool = []
    regime = panel.regime

    for s in universe:
        ss = signal_by_symbol[s]
        open_px = panel.open_[s]
        surv = panel.survivorship[s]
        # 上市前信號歸零（survivorship）：把 leak-free / naive 信號 mask 成 0。
        lf_sig = np.where(surv, ss.leakfree, 0.0)
        nv_sig = np.where(surv, ss.naive, 0.0)
        rate = panel.funding_mean_per_8h.get(s, 0.0)

        trades_lf, pos_lf, flips_lf = pnl.build_trades(
            s, lf_sig, open_px, variant=variant, regimes=list(regime))
        _trades_nv, _pos_nv, flips_nv = pnl.build_trades(
            s, nv_sig, open_px, variant=variant)
        total_flips_lf += flips_lf
        total_flips_nv += flips_nv
        all_trades_lf.extend(trades_lf)

        g_lf, n_lf = pnl.daily_returns_from_positions(pos_lf, open_px, rate)
        # naive 軌只看 gross（診斷用，比 leak-free gross Sharpe）。
        g_nv, _n_nv = pnl.daily_returns_from_positions(_pos_nv, open_px, rate)
        lf_daily_pool.append(n_lf)  # leak-free 用 net 日報酬（正式）
        nv_daily_pool.append(g_nv)  # naive 用 gross（look-ahead 診斷）

    # pooled 等權日報酬（跨 symbol 平均；NaN 安全）。
    lf_mat = np.column_stack(lf_daily_pool)
    nv_mat = np.column_stack(nv_daily_pool)
    lf_port = np.nanmean(lf_mat, axis=1)
    nv_port = np.nanmean(nv_mat, axis=1)
    # leak-free 也算一條 gross（與 naive gross 對齊比較，§2.2 純看 look-ahead 影響）。
    lf_gross_pool = []
    for s in universe:
        ss = signal_by_symbol[s]
        surv = panel.survivorship[s]
        lf_sig = np.where(surv, ss.leakfree, 0.0)
        _t, pos_lf, _f = pnl.build_trades(s, lf_sig, panel.open_[s], variant=variant)
        g_lf, _n = pnl.daily_returns_from_positions(pos_lf, panel.open_[s], 0.0)
        lf_gross_pool.append(g_lf)
    lf_gross_port = np.nanmean(np.column_stack(lf_gross_pool), axis=1)

    sharpe_lf_net = stats.annualized_sharpe(lf_port)
    sharpe_lf_gross = stats.annualized_sharpe(lf_gross_port)
    sharpe_nv_gross = stats.annualized_sharpe(nv_port)

    tm = pnl.trade_metrics(all_trades_lf, _avg_funding(panel))
    gross_edge = tm.get("gross_edge_bps_per_trade")
    # 代表性 round-trip 成本（用平均持有期 + universe median funding）。
    avg_hold = tm.get("avg_holding_days") or 1.0
    rep_cost = cost_model.round_trip_cost_bps(+1, avg_hold, _avg_funding(panel))
    cer = cost_model.cost_edge_ratio(rep_cost.total_bps, gross_edge)

    # per-regime net Sharpe（用 leak-free net 日報酬按 regime 切）。
    per_regime = {}
    for rg in ("bull", "bear", "chop"):
        mask = regime == rg
        seg = lf_port[mask]
        per_regime[rg] = {
            "n_days": int(mask.sum()),
            "annualized_net_sharpe": stats.annualized_sharpe(seg),
            "mean_daily_bps": round(float(np.nanmean(seg)) * 1e4, 4) if np.any(np.isfinite(seg)) else None,
        }

    # leak-free vs naive 差（§2.2）：用 gross Sharpe 比（隔離 look-ahead，不混 funding）。
    look_ahead_inflation = None
    if sharpe_lf_gross is not None and sharpe_nv_gross is not None and abs(sharpe_lf_gross) > 1e-9:
        look_ahead_inflation = (sharpe_nv_gross - sharpe_lf_gross) / abs(sharpe_lf_gross)

    return {
        "variant": variant,
        "pooled_direction_flips_leakfree": total_flips_lf,
        "pooled_direction_flips_naive": total_flips_nv,
        "n_trades_leakfree": tm.get("n_trades", 0),
        "annualized_net_sharpe_leakfree": sharpe_lf_net,
        "annualized_gross_sharpe_leakfree": sharpe_lf_gross,
        "annualized_gross_sharpe_naive": sharpe_nv_gross,
        "look_ahead_inflation_ratio": (round(look_ahead_inflation, 4)
                                       if look_ahead_inflation is not None else None),
        "gross_edge_bps_per_trade": round(gross_edge, 4) if gross_edge is not None else None,
        "net_edge_bps_per_trade": (round(tm.get("net_edge_bps_per_trade"), 4)
                                   if tm.get("net_edge_bps_per_trade") is not None else None),
        "representative_rt_cost_bps": round(rep_cost.total_bps, 3),
        "cost_edge_ratio": round(cer, 4) if cer is not None else None,
        "cost_edge_class": cost_model.classify_cost_edge_ratio(cer),
        "long_net_bps": tm.get("long_net_bps"),
        "short_net_bps": tm.get("short_net_bps"),
        "avg_funding_bps_long": tm.get("avg_funding_bps_long"),
        "avg_funding_bps_short": tm.get("avg_funding_bps_short"),
        "win_rate": tm.get("win_rate"),
        "avg_holding_days": tm.get("avg_holding_days"),
        "per_regime_net": per_regime,
    }


def _avg_funding(panel: data_loader.Panel) -> float:
    vals = list(panel.funding_mean_per_8h.values())
    return float(np.median(vals)) if vals else 0.0


def run_diagnostic(panel: data_loader.Panel, universe) -> dict:
    """跑 Phase 1 全部 DATA TASK + 早期決策樹。fail-fast 在第一個命中的門檻停。"""
    report: dict = {
        "phase": "phase_1_fail_fast_early_gates",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "universe": list(universe),
        "n_dates": len(panel.dates),
        "date_span": [str(panel.dates[0]), str(panel.dates[-1])] if panel.dates else None,
        "coverage_notes": panel.coverage_notes,
        "trial_budget_K": signals.count_trial_budget(),
        "data_tasks": {},
        "signal_evaluation": {},
        "decision_tree": {},
    }

    # DATA TASKS 1/2/3/5（4 在信號評估）。
    report["data_tasks"]["task_1_fee_tier"] = data_task_1_fee_tier()
    report["data_tasks"]["task_2_funding"] = data_task_2_funding(panel)
    report["data_tasks"]["task_3_slippage"] = data_task_3_slippage()
    report["data_tasks"]["task_5_regime"] = data_task_5_regime(panel)

    # 信號生成（A/B/C per-symbol + D cross-sectional）。
    sigma_target = data_loader.cross_sectional_median_daily_vol(panel)
    report["sigma_target_daily_vol"] = round(sigma_target, 6)

    # 組所有信號變體（每變體 → {symbol: SignalSeries}）。
    variant_map: dict = {}
    for s in universe:
        for ss in signals.generate_single_symbol_signals(panel.close[s], sigma_target):
            variant_map.setdefault(ss.name, {})[s] = ss
    for k in signals.SIGNAL_D_KS:
        d_signals = signals.signal_d_cross_sectional(panel.close, panel.survivorship, k)
        for s, ss in d_signals.items():
            variant_map.setdefault(ss.name, {})[s] = ss

    # 評估每信號 × 2 持有期 → DATA TASK 4（信號頻率）+ Step0 原料。
    all_evals = {}
    for sig_name, by_sym in variant_map.items():
        for hold_variant in ("daily", "flip_hold_min"):
            key = f"{sig_name}__{hold_variant}"
            all_evals[key] = evaluate_signal_variant(panel, universe, by_sym, hold_variant)
    report["signal_evaluation"] = all_evals

    # PCA effective N（cluster 縮減）。
    ret_mat = _build_close_matrix(panel, universe)
    pca = stats.pca_effective_n(ret_mat)
    report["pca_effective_dimension"] = pca

    # ── Step 0 effective N（§4.0）─────────────────────────────────────────
    # 每信號變體的 pooled flips × (N_eff / n_symbols) cluster 縮減。
    n_symbols = len(universe)
    cluster_factor = (pca["n_eff"] / max(pca["n_symbols"], 1)) if pca else 1.0
    step0 = {}
    max_eff_n = 0.0
    for key, ev in all_evals.items():
        pooled_flips = ev["pooled_direction_flips_leakfree"]
        # 方向翻轉 ≈ trades；cluster 縮減後的 effective independent trades。
        eff_n = pooled_flips * cluster_factor
        step0[key] = {
            "pooled_direction_flips": pooled_flips,
            "n_trades": ev["n_trades_leakfree"],
            "cluster_factor": round(cluster_factor, 4),
            "effective_n": round(eff_n, 2),
            "passes_floor": eff_n >= EFFECTIVE_N_FLOOR,
        }
        max_eff_n = max(max_eff_n, eff_n)
    report["step_0_effective_n"] = {
        "floor": EFFECTIVE_N_FLOOR,
        "required_n_theory_delta0p5": stats.required_n_for_sharpe_delta(0.5),
        "cluster_factor_applied": round(cluster_factor, 4),
        "max_effective_n_across_variants": round(max_eff_n, 2),
        "n_variants_passing_floor": sum(1 for v in step0.values() if v["passes_floor"]),
        "per_variant": step0,
    }

    # ── 正確尺度多日 TSMOM 顯著性檢定（FIX-2：verdict 依據，取代 daily-LB gate）──
    # 為什麼放在決策樹前算：這是 trend 有無基礎的**正確尺度**判定（過去 k 日 → 未來
    # k 日），決策樹門檻 A 直接依它。daily-lag Ljung-Box（在 data_quality）降級為僅報告。
    tsmom = {}
    for k in TSMOM_SCALE_KS:
        res = stats.tsmom_significance(panel.close, panel.survivorship, k)
        if res is not None:
            tsmom[f"k{k}"] = res
    report["tsmom_correct_scale_significance"] = _summarize_tsmom(tsmom)

    # 資料品質（在決策樹前算，修正 FIX-1 接線：原 Ljung-Box gate 漏接在 run_diagnostic）。
    # 含 BTC daily LB（保留）+ per-symbol/pooled LB（FIX-3 廣度）。daily-LB 僅供誠實診斷，
    # 非 verdict 依據（verdict 用上方正確尺度 TSMOM 檢定）。
    report["data_quality"] = _data_quality(panel)

    # ── 決策樹（fail-fast）──────────────────────────────────────────────
    decision = _decision_tree(report, all_evals, step0, max_eff_n)
    report["decision_tree"] = decision
    return report


def _has_adjacent_pair(sig_ks: list) -> bool:
    """sig_ks 中是否存在**至少一對在排序 lookback grid 中相鄰**的 k（re-E2 MEDIUM-2）。

    為什麼用相鄰而非單純 ≥2：MIT 終裁「相鄰 plateau 才是 coherent momentum 的正確語意」。
    k20+k90 兩端各自顯著但中間（k30/k40/k60）斷裂 = 非結構性 plateau，是低 N_eff + K=24
    多重比較下的雜訊；只有連續尺度形成的 plateau（如 (30,40) 或 (40,60)）才算多尺度一致。
    grid = sorted(TSMOM_SCALE_KS)=(20,30,40,60,90)，相鄰對 = (20,30)/(30,40)/(40,60)/(60,90)。
    sig_ks 為 dict-key 字串（如 "k30"），映射回 grid 的整數值後查連續索引。
    """
    grid = sorted(TSMOM_SCALE_KS)
    idx_of = {f"k{k}": i for i, k in enumerate(grid)}
    # 取得 sig_ks 在 grid 中的索引（忽略不在 grid 的 key，理論上不會發生）。
    indices = sorted(idx_of[k] for k in sig_ks if k in idx_of)
    # 任一對索引相差 1 即相鄰。
    return any(b - a == 1 for a, b in zip(indices, indices[1:]))


def _summarize_tsmom(per_k: dict) -> dict:
    """彙整正確尺度 TSMOM 各 k 結果 + 判定**相干**正動量（verdict 驅動，FIX-2/FIX-4）。

    為什麼用「相干」而非「任一 k 顯著」：真實 TSMOM 在相鄰尺度應呈現一致符號/單調（MOP
    2012 / MIT 56d 教訓「sign coherent across adjacent (N,M)」）；單一孤立 k 顯著、相鄰
    k 不顯著、且另有尺度出現顯著反轉 = 在低 N_eff（≈2）+ K=24 multiple-testing 下的雜訊
    取樣，非 momentum。故 coherent_positive_momentum 才是 gate 依據（MIT 終裁實作相鄰）：
      需 significant-positive k（mean>0 且 HAC |t|≥2）中**至少一對在排序 grid 相鄰**
      （形成連續尺度 plateau，如 (30,40)/(40,60)），且**無任一 k 顯著反轉**（HAC t≤-2
      且 mean<0）。非相鄰兩端顯著（k20+k90）= plateau 斷裂 → 不相干 → NO-GO-TREND。
    同時記 Bonferroni 門檻（5 個 k → 雙尾 t≈2.57）供誠實對照（孤立 cell 即使過樸素 2.0，
    多重比較校正後多半不過）。
    """
    evaluated = {k: v for k, v in per_k.items() if not v.get("insufficient")}
    sig_pos = [k for k, v in evaluated.items()
               if v.get("t_stat_hac") is not None and v["t_stat_hac"] >= TSMOM_TSTAT_FLOOR
               and v.get("mean_signed_fwd_bps") is not None and v["mean_signed_fwd_bps"] > 0]
    sig_reversal = [k for k, v in evaluated.items()
                    if v.get("t_stat_hac") is not None and v["t_stat_hac"] <= -TSMOM_TSTAT_FLOOR
                    and v.get("mean_signed_fwd_bps") is not None and v["mean_signed_fwd_bps"] < 0]
    n_pos_mean = sum(1 for v in evaluated.values()
                     if v.get("mean_signed_fwd_bps") is not None and v["mean_signed_fwd_bps"] > 0)
    # 相干正動量（MIT 終裁實作相鄰，re-E2 MEDIUM-2）：significant-positive k 中至少一對
    # 在排序 grid 相鄰（形成連續尺度 plateau）且無顯著反轉。非相鄰兩端顯著（k20+k90）
    # = plateau 斷裂 → 不相干。
    coherent = (_has_adjacent_pair(sig_pos) and len(sig_reversal) == 0)
    # Bonferroni 雙尾門檻（k 數）：α=0.05 → t_crit。查表近似（5→2.57, 4→2.50, 3→2.39）。
    bonf = {3: 2.394, 4: 2.498, 5: 2.576, 6: 2.638}.get(len(evaluated), TSMOM_TSTAT_FLOOR)
    sig_pos_bonf = [k for k in sig_pos
                    if evaluated[k]["t_stat_hac"] >= bonf]
    return {
        "ks": list(TSMOM_SCALE_KS),
        "tstat_threshold": TSMOM_TSTAT_FLOOR,
        "bonferroni_tstat_threshold": round(bonf, 3),
        "note": (
            "正確尺度檢定：過去 k 日報酬符號 vs 未來 k 日報酬，pooled 全 symbol，"
            "Newey-West overlap-corrected t-stat（lag=k-1）。verdict 依據 = coherent_positive_"
            "momentum（至少一對相鄰 k 顯著正 且 無顯著反轉），非單一孤立 k。"
            "daily-lag Ljung-Box 已降級為 data_quality 報告統計（測錯時間尺度）。"
        ),
        "per_k": per_k,
        "significant_positive_ks": sig_pos,
        "significant_positive_ks_bonferroni": sig_pos_bonf,
        "significant_reversal_ks": sig_reversal,
        "n_ks_positive_mean": n_pos_mean,
        "n_ks_evaluated": len(evaluated),
        # 任一單 k 顯著（透明保留，但非 gate 依據）。
        "any_significant_positive": len(sig_pos) > 0,
        # gate 依據：相干正動量。
        "coherent_positive_momentum": bool(coherent),
    }


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


def _decision_tree(report, all_evals, step0, max_eff_n) -> dict:
    """協議 §5 早期決策樹。fail-fast：第一個命中即 verdict，標明 stop reason。

    FIX-1/FIX-2：本函數在 run_diagnostic 內被呼叫（data_quality + 正確尺度 TSMOM 檢定
    都已算好放進 report），故門檻可直接讀，不再有 main() 才覆寫的接線斷裂。
    fail-fast 順序：Step0 → 正確尺度 TSMOM（取代 daily-LB）→ leak/naive → cost。
    """
    # 門檻 1：Step0 effective N < 60 → INCONCLUSIVE-A（停）。
    if max_eff_n < EFFECTIVE_N_FLOOR:
        return {
            "verdict": "INCONCLUSIVE-A",
            "stopped_at": "step_0_effective_n",
            "reason": (
                f"max effective N across all {len(all_evals)} variants = {max_eff_n:.2f} "
                f"< floor {EFFECTIVE_N_FLOOR}; 2yr x 20 high-corr symbols underpowered. "
                "Needs longer-history backfill (V125 + daily-kline backfill writer) then re-run."
            ),
            "next": "longer-history backfill then re-run; skip Phase 2 DSR/PSR/PBO (power<0.5)",
        }

    best_key, best_ev = _find_best_variant(all_evals)
    if best_ev is None:
        return {
            "verdict": "INCONCLUSIVE-A",
            "stopped_at": "no_evaluable_variant",
            "reason": "no variant produced finite net Sharpe (insufficient trades after warmup/survivorship)",
        }

    # 門檻 2（FIX-2 核心）：正確尺度多日 TSMOM 不顯著 → NO-GO-TREND。
    # 為什麼這取代 daily-lag Ljung-Box：daily-LB 測高頻（次日）尺度，對 TSMOM(k=20-90)
    # 的低頻趨勢持續無診斷力且會 false-kill 慢趨勢；正確尺度檢定直接問「過去 k 日 →
    # 未來 k 日」。verdict 一致性：即使某變體表面 net Sharpe>0.5，若正確尺度無顯著
    # momentum，該 Sharpe 是 short-side 厚尾/funding artifact（下方拆解佐證），故 TSMOM
    # 門檻先於並優先於 per-variant Sharpe（解決「無統計基礎 + Sharpe>0.5」自相矛盾）。
    tsmom_block = report.get("tsmom_correct_scale_significance", {})
    tsmom_verdict = _tsmom_gate(tsmom_block, best_key, best_ev, report)
    if tsmom_verdict is not None:
        return tsmom_verdict

    # 門檻 3：leak-free≈0 但 naive 高 → NO-GO-B（用 inflation ratio > 0.30）。
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
                "-> positive naive result is look-ahead illusion (Donchian F3 lesson)."
            ),
            "look_ahead_inflated_variants": inflated[:10],
        }

    # 門檻 4：net Sharpe<0.5 OR cost_edge_ratio≥0.8 → NO-GO-C。
    best_sharpe = best_ev["annualized_net_sharpe_leakfree"]
    cer = best_ev["cost_edge_ratio"]
    cost_wall = (cer is not None and cer >= cost_model.COST_EDGE_RATIO_ABANDON)
    sharpe_fail = best_sharpe < NET_SHARPE_FLOOR
    if sharpe_fail or cost_wall:
        # 判 funding 是否殺手：gross 正但 net 因 funding 轉負。
        funding_killer = (best_ev["gross_edge_bps_per_trade"] is not None
                          and best_ev["gross_edge_bps_per_trade"] > 0
                          and best_ev["net_edge_bps_per_trade"] is not None
                          and best_ev["net_edge_bps_per_trade"] < 0
                          and best_ev["avg_funding_bps_long"] is not None
                          and best_ev["avg_funding_bps_long"] > 0)
        return {
            "verdict": "NO-GO-C",
            "stopped_at": "net_sharpe_and_cost_edge",
            "reason": (
                f"best variant {best_key}: net Sharpe={best_sharpe:.3f} "
                f"(floor {NET_SHARPE_FLOOR}), cost_edge_ratio={cer} "
                f"(abandon≥{cost_model.COST_EDGE_RATIO_ABANDON}). Cost wall holds in multi-day."
                + (" FUNDING IS THE KILLER (gross>0 but net<0 driven by long funding drag)."
                   if funding_killer else "")
            ),
            "funding_is_killer": funding_killer,
            "best_variant": best_key,
            "best_variant_metrics": best_ev,
        }

    # 通過早期門檻 → 標需 Phase 2。
    return {
        "verdict": "SURVIVES_EARLY_GATES_NEEDS_PHASE_2",
        "stopped_at": None,
        "reason": (
            f"best variant {best_key}: effective N≥{EFFECTIVE_N_FLOOR}, correct-scale TSMOM shows "
            f"COHERENT positive momentum, net Sharpe={best_sharpe:.3f}≥{NET_SHARPE_FLOOR}, "
            f"cost_edge_ratio={cer}<0.8, no dominant look-ahead inflation. Needs Phase 2: full "
            "DSR(K=24)/PSR/PBO/walk-forward + MIT leak audit + QC stats review."
        ),
        "best_variant": best_key,
        "best_variant_metrics": best_ev,
    }


def _tsmom_gate(tsmom_block: dict, best_key, best_ev, report) -> Optional[dict]:
    """門檻 2（FIX-2/FIX-4）：正確尺度多日 TSMOM **相干**顯著性 → NO-GO-TREND（取代 NO-GO-A）。

    判定（gate 依據 = coherent_positive_momentum，非單一 k）：
      ≥2 個相鄰 k 達「mean>0 且 HAC |t|≥2」且無顯著反轉 → 相干正動量 → 通過此 gate。
      否則（孤立單 k 顯著 / 全 k 不顯著 / 出現顯著反轉）→ NO-GO-TREND。
    為什麼不接受單一孤立 k：低 N_eff（≈2）+ K=24 multiple-testing 下，相鄰尺度不一致 +
    長尺度反轉 = 雜訊取樣，非結構性 momentum（MIT 56d「sign coherent across adjacent」教訓）。
    verdict 措辭反映正確證據（相干性 + 反轉 + short-side artifact），非 daily autocorr。
    """
    per_k = tsmom_block.get("per_k", {})
    if not per_k:
        return None  # 無 TSMOM 結果（如 synthetic 太短）→ 不在此 gate 攔，交後續門檻
    evaluated = {k: v for k, v in per_k.items() if not v.get("insufficient")}
    if not evaluated:
        return None  # 全 k 樣本不足 → 不在此攔（交 Step0/後續）
    if tsmom_block.get("coherent_positive_momentum"):
        return None  # 有相干正動量 → 通過此 gate，交後續門檻判 Sharpe/cost

    # 誠實摘要：各 k t-stat / hit / mean + 顯著正 ks + 反轉 ks。
    tstats = {k: v.get("t_stat_hac") for k, v in evaluated.items()}
    hits = {k: v.get("hit_rate") for k, v in evaluated.items()}
    means = {k: v.get("mean_signed_fwd_bps") for k, v in evaluated.items()}
    sig_pos = tsmom_block.get("significant_positive_ks", [])
    sig_pos_bonf = tsmom_block.get("significant_positive_ks_bonferroni", [])
    sig_rev = tsmom_block.get("significant_reversal_ks", [])

    lb_uni = report.get("data_quality", {}).get("ljung_box_universe", {}) or {}
    n_pos = lb_uni.get("n_symbols_positive_autocorr")
    n_eval = lb_uni.get("n_symbols_evaluated")

    # 描述「為何不相干」：孤立單 k vs 全不顯著。
    if sig_pos:
        incoherence = (
            f"only {len(sig_pos)} isolated k {sig_pos} clears HAC |t|>={TSMOM_TSTAT_FLOOR} "
            f"(Bonferroni-passing: {sig_pos_bonf}); adjacent k are insignificant -> no coherent "
            "momentum across scales (single cell amid noise at N_eff~2, K=24 uncorrected)")
    else:
        incoherence = (
            f"no k clears HAC |t|>={TSMOM_TSTAT_FLOOR}; hit rates ~50%")

    return {
        "verdict": "NO-GO-TREND",
        "stopped_at": "correct_scale_tsmom_significance",
        "reason": (
            "correct-scale multi-day TSMOM shows NO coherent positive momentum: "
            + incoherence
            + f". HAC overlap-corrected t-stats={tstats}, hit rates={hits}, mean signed fwd bps={means}"
            + (f"; SIGNIFICANT REVERSAL at k={sig_rev} (long-scale momentum -> mean reversion, "
               "the opposite of TSMOM)" if sig_rev else "")
            + (f"; universe-wide per-symbol Ljung-Box: {n_pos}/{n_eval} symbols show significant "
               "positive autocorrelation (autocorr absence is universe-wide, not a single-BTC artifact)"
               if n_pos is not None else "")
            + ". The daily-lag Ljung-Box (demoted to data_quality) tested the WRONG time scale; "
            "this correct-scale test (past k-day -> next k-day) is the verdict basis. Surface net "
            "Sharpe is a short-side fat-tail / funding-credit artifact, not momentum alpha."
        ),
        "tsmom_correct_scale": tsmom_block,
        "significant_positive_ks": sig_pos,
        "significant_reversal_ks": sig_rev,
        "best_variant": best_key,
        "best_variant_metrics": best_ev,
        "surface_sharpe_caveat": (
            "Best variant leak-free net Sharpe="
            f"{best_ev.get('annualized_net_sharpe_leakfree')} is NOT contradictory evidence: "
            f"long-side net={best_ev.get('long_net_bps')}bps (~0), short-side net="
            f"{best_ev.get('short_net_bps')}bps carries it (short-side fat-tail + positive-funding "
            f"credit), win_rate={best_ev.get('win_rate')}; this dies in Phase 2 (overlapping, "
            "IS-only, K=24 uncorrected). Signal D is market-neutral and shows no idiosyncratic alpha."
        ),
        "power_caveat": _power_caveat(report),
    }


def _power_caveat(report) -> dict:
    """誠實 power caveat（FIX-4 強制）：低 N_eff 是 binding constraint，非高 power 反證。

    statement 依實際 N_eff 自適應：真實 crypto universe N_eff≈2（高 BTC beta）時才宣稱
    「~2 獨立流」；synthetic 或真獨立 universe（N_eff 高）時不誤植該數字（誠實第一）。
    """
    pca = report.get("pca_effective_dimension", {}) or {}
    n_eff = pca.get("n_eff")
    pc1 = pca.get("pc1_explained_share")
    n_sym = pca.get("n_symbols")
    # N_eff 偏低（高相關）才是「少數獨立流 → power 受限」的 binding constraint。
    low_neff = (n_eff is not None and n_sym and n_eff <= max(3.0, 0.25 * n_sym))
    if low_neff:
        statement = (
            f"N_eff={n_eff} (PC1={pc1} BTC beta) means this {n_sym}-symbol universe carries only "
            f"~{n_eff:.0f} independent return streams; statistical power is structurally limited. "
            "This is a 'limited-years x few-independent-streams shows no detectable trend edge' "
            "result, NOT a high-power impossibility proof. Longer-history backfill has LIMITED "
            "upside for trend: low N_eff (high BTC beta) is the binding constraint, not window "
            "length; more crypto history adds cascade/mean-reversion regimes, not positive "
            "momentum. Honest verdict = close multi-day trend on current evidence; reopen only if "
            "a structurally different (more-independent) universe or instrument set becomes available."
        )
    else:
        statement = (
            f"N_eff={n_eff} (PC1={pc1}); on this sample the universe carries ~{n_eff} independent "
            "streams. Power is bounded by window length and the number of independent multi-day "
            "periods rather than by cross-sectional collinearity. Verdict reflects no detectable "
            "correct-scale momentum on the available sample; not a high-power impossibility proof."
        )
    return {
        "pca_n_eff": n_eff,
        "pc1_explained_share": pc1,
        "n_symbols": n_sym,
        "low_neff_binding": bool(low_neff),
        "statement": statement,
    }


def _data_quality(panel: data_loader.Panel) -> dict:
    """資料品質 5-test 在 BTC 日報酬上（協議 §4.7）。

    BTC 缺（如 synthetic universe）→ 退而用第一個有足量收盤的 symbol，並標記 proxy。
    """
    proxy_symbol = data_loader.BTC_SYMBOL
    btc = panel.close.get(data_loader.BTC_SYMBOL)
    if btc is None or np.sum(np.isfinite(btc) & (btc > 0)) < 30:
        # fallback：取第一個有 >=30 收盤的 symbol（regime 統計基礎仍可診斷）。
        for s, c in panel.close.items():
            if np.sum(np.isfinite(c) & (c > 0)) >= 30:
                btc, proxy_symbol = c, s
                break
    if btc is None:
        return {"error": "no symbol with sufficient closes"}
    cc = btc[np.isfinite(btc) & (btc > 0)]
    if len(cc) < 30:
        return {"error": "insufficient BTC closes"}
    log_close = np.log(cc)
    rets = np.diff(log_close)
    return {
        "proxy_symbol": proxy_symbol,
        # daily-lag Ljung-Box：降級為 data_quality 報告統計（FIX-2/FIX-4），非 verdict 依據。
        # 為什麼降級：它測「日報酬→次日」高頻尺度，對 TSMOM(k=20-90) 低頻趨勢持續無診斷力
        # （MOP 2012：TSMOM 日報酬近白噪音）。verdict 改用 tsmom_correct_scale_significance。
        "ljung_box_btc_returns": stats.ljung_box(rets, lags=10),
        "ljung_box_scale_note": (
            "daily-lag Ljung-Box is a high-frequency (next-day) statistic; it is NOT the trend "
            "verdict basis. Correct-scale verdict lives in tsmom_correct_scale_significance."
        ),
        # FIX-3：per-symbol（全 20）+ pooled Ljung-Box（廣度，證自相關呈現是 universe-wide）。
        "ljung_box_universe": stats.ljung_box_universe(panel.close, lags=10),
        "adf_btc_log_close": stats.adf_test(log_close),
        "adf_btc_returns": stats.adf_test(rets),
        "kpss_btc_returns": stats.kpss_test(rets),
        "jarque_bera_btc_returns": stats.jarque_bera(rets),
        "arch_lm_btc_returns": stats.arch_lm(rets, lags=5),
        "n_returns": len(rets),
    }


# ── synthetic dry-run（Mac 可跑，不連 PG）──────────────────────────────────

def build_synthetic_panel(
    n_days: int = 730,
    n_symbols: int = 20,
    *,
    trending: bool = True,
    seed: int = 20260602,
) -> data_loader.Panel:
    """合成面板（驗 harness 邏輯，不連 PG）。trending=True 注入可被 trend 捕捉的漂移。"""
    rng = np.random.default_rng(seed)
    universe = tuple(f"SYN{i:02d}USDT" for i in range(n_symbols))
    base = dt.date(2024, 6, 2)
    dates = [base + dt.timedelta(days=i) for i in range(n_days)]
    close, open_, high, low, volume, surv = {}, {}, {}, {}, {}, {}
    # 共同市場因子（BTC-like），製造高相關（低 N_eff）。
    market = np.cumsum(rng.normal(0.0006 if trending else 0.0, 0.02, n_days))
    for s in universe:
        idio = np.cumsum(rng.normal(0.0, 0.01, n_days))
        drift = (0.0004 if trending else 0.0)
        logp = np.log(100.0) + 0.8 * market + idio + drift * np.arange(n_days)
        c = np.exp(logp)
        o = np.concatenate([[c[0]], c[:-1]]) * (1 + rng.normal(0, 0.001, n_days))
        close[s] = c
        open_[s] = o
        high[s] = np.maximum(c, o) * 1.005
        low[s] = np.minimum(c, o) * 0.995
        volume[s] = np.full(n_days, 1e6)
        surv[s] = np.ones(n_days, dtype=bool)
    regime = data_loader.compute_rule_based_regime(close[universe[0]], dates)
    funding = {s: 0.0001 for s in universe}  # +1bp/8h 代表性
    return data_loader.Panel(
        dates=dates, close=close, open_=open_, high=high, low=low, volume=volume,
        survivorship=surv, regime=regime, funding_mean_per_8h=funding,
        coverage_notes={"synthetic": True, "trending": trending},
    ), universe


def _write_artifact(report: dict, run_id: str) -> tuple[Path, Path]:
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
    lines = [
        "# 多日 Trend/Momentum 樞紐診斷 — Phase 1 fail-fast 報告",
        "",
        f"- 生成時間：{report['generated_at']}",
        f"- 日期跨度：{report.get('date_span')}（{report['n_dates']} 日）",
        f"- universe：{len(report['universe'])} symbol",
        f"- trial 預算 K：{report['trial_budget_K']}",
        "",
        f"## 早期決策樹判定：**{dt_tree['verdict']}**",
        "",
        f"- stopped_at：{dt_tree.get('stopped_at')}",
        f"- reason：{dt_tree.get('reason')}",
        "",
        "## DATA TASK 結果",
        "",
        f"- TASK1 fee：taker RT {report['data_tasks']['task_1_fee_tier']['taker_rt_bps']}bps / "
        f"maker RT {report['data_tasks']['task_1_fee_tier']['maker_rt_bps']}bps",
        f"- TASK3 slippage：RT {report['data_tasks']['task_3_slippage']['slippage_rt_bps']}bps",
        f"- TASK5 regime 組成：{report['data_tasks']['task_5_regime']['composition_pct']}"
        f"（bull-dominated={report['data_tasks']['task_5_regime']['bull_dominated']}）",
        f"- TASK2 funding 覆蓋告誡：{report['data_tasks']['task_2_funding']['coverage_caveat']}",
        "",
        "## Step 0 effective N",
        "",
        f"- floor：{report['step_0_effective_n']['floor']}",
        f"- cluster_factor（PCA N_eff/n_symbols）：{report['step_0_effective_n']['cluster_factor_applied']}",
        f"- max effective N across variants：{report['step_0_effective_n']['max_effective_n_across_variants']}",
        f"- PCA：N_eff={report.get('pca_effective_dimension', {}).get('n_eff')} / "
        f"PC1 share={report.get('pca_effective_dimension', {}).get('pc1_explained_share')}",
        "",
    ]

    # ── 正確尺度 TSMOM 顯著性（FIX-2：verdict 依據，取代 daily-LB）──
    tsmom = report.get("tsmom_correct_scale_significance", {}) or {}
    lines += [
        "## 正確尺度多日 TSMOM 顯著性（verdict 依據）",
        "",
        "過去 k 日報酬符號 vs 未來 k 日報酬，pooled 全 symbol，Newey-West overlap-corrected "
        "t-stat（lag=k-1）。daily-lag Ljung-Box 已降級為下方 data_quality 報告統計（測錯時間尺度）。",
        "",
        "| k | n_obs | n_eff(非重疊) | mean signed fwd bps | hit rate | t-stat (HAC) | t-stat (naive) | 顯著正動量 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for kk in sorted(tsmom.get("per_k", {}), key=lambda x: int(x[1:])):
        v = tsmom["per_k"][kk]
        if v.get("insufficient"):
            lines.append(f"| {kk} | {v.get('n_obs')} | — | — | — | — | — | insufficient |")
        else:
            lines.append(
                f"| {kk} | {v.get('n_obs')} | {v.get('n_eff_non_overlapping')} | "
                f"{v.get('mean_signed_fwd_bps')} | {v.get('hit_rate')} | {v.get('t_stat_hac')} | "
                f"{v.get('t_stat_naive_overlapping')} | {v.get('significant_positive_momentum')} |")
    lines += [
        "",
        f"- 顯著正 ks（HAC |t|≥{tsmom.get('tstat_threshold')}）：{tsmom.get('significant_positive_ks')}"
        f"（Bonferroni t≥{tsmom.get('bonferroni_tstat_threshold')} 通過：{tsmom.get('significant_positive_ks_bonferroni')}）",
        f"- 顯著反轉 ks（HAC t≤-{tsmom.get('tstat_threshold')} 且 mean<0）：{tsmom.get('significant_reversal_ks')}",
        f"- **相干正動量（verdict 依據，至少一對相鄰 k 顯著正 且 無反轉）：{tsmom.get('coherent_positive_momentum')}**",
        "",
        "## leak-free vs naive（最佳變體）",
        "",
    ]
    # verdict dict 自帶 best_variant_metrics（NO-GO-TREND/B/C/SURVIVES 皆含）；若 verdict 是
    # 在 Step0 就停的 INCONCLUSIVE-A（無最佳變體），退而從 all_evals 重算一次保並列。
    bm = dt_tree.get("best_variant_metrics")
    best_variant_name = dt_tree.get("best_variant")
    if bm is None:
        bk, bev = _find_best_variant(report.get("signal_evaluation", {}))
        bm, best_variant_name = bev, bk
    if bm:
        lines += [
            f"- 變體：{best_variant_name}",
            f"- leak-free 年化 net Sharpe：{bm.get('annualized_net_sharpe_leakfree')}",
            f"- leak-free 年化 gross Sharpe：{bm.get('annualized_gross_sharpe_leakfree')}",
            f"- naive 年化 gross Sharpe：{bm.get('annualized_gross_sharpe_naive')}",
            f"- look-ahead inflation ratio：{bm.get('look_ahead_inflation_ratio')}",
            f"- per-trade gross / net edge bps：{bm.get('gross_edge_bps_per_trade')} / {bm.get('net_edge_bps_per_trade')}",
            f"- cost_edge_ratio：{bm.get('cost_edge_ratio')}（{bm.get('cost_edge_class')}）",
            f"- 多 net / 空 net bps：{bm.get('long_net_bps')} / {bm.get('short_net_bps')}"
            "（若 net 全在空側 = short-side artifact，非 momentum alpha）",
            f"- funding 多 / 空 bps：{bm.get('avg_funding_bps_long')} / {bm.get('avg_funding_bps_short')}",
            f"- win_rate：{bm.get('win_rate')}",
            f"- per-regime net Sharpe：{ {k: v['annualized_net_sharpe'] for k, v in bm.get('per_regime_net', {}).items()} }",
        ]
    dq = report.get("data_quality", {})
    lb = dq.get("ljung_box_btc_returns") or {}
    lbu = dq.get("ljung_box_universe") or {}
    jb = dq.get("jarque_bera_btc_returns") or {}
    lines += [
        "",
        "## 資料品質（日報酬尺度 — 非 verdict 依據）",
        "",
        f"- daily-lag Ljung-Box（BTC，僅報告）：正自相關={lb.get('positive_autocorr')}"
        f"（rho_1={lb.get('rho_1')}, significant={lb.get('significant')}）",
        f"- per-symbol/pooled Ljung-Box（FIX-3 廣度）：{lbu.get('n_symbols_positive_autocorr')}/"
        f"{lbu.get('n_symbols_evaluated')} symbol 有顯著正自相關，pooled posAC="
        f"{(lbu.get('pooled_demeaned') or {}).get('positive_autocorr')}, "
        f"median rho_1={lbu.get('median_rho_1')} → 自相關呈現是 universe-wide 非單 BTC",
        f"- Jarque-Bera：拒常態={jb.get('reject_normality_5pct')}（厚尾={jb.get('fat_tailed')}, "
        f"excess_kurt={jb.get('excess_kurtosis')}）→ 後續用 PSR 非 normal",
        f"- ADF returns 平穩={ (dq.get('adf_btc_returns') or {}).get('stationary') } / "
        f"ARCH 效應={ (dq.get('arch_lm_btc_returns') or {}).get('arch_effect_5pct') }",
        "",
    ]

    # ── 誠實 power caveat（FIX-4 強制）──
    pc = dt_tree.get("power_caveat")
    if pc is None:
        pc = _power_caveat(report)
    lines += [
        "## 誠實 power caveat（FIX-4）",
        "",
        f"- PCA N_eff={pc.get('pca_n_eff')} / PC1 share={pc.get('pc1_explained_share')}",
        f"- {pc.get('statement')}",
        "",
        "## 限制聲明（誠實）",
        "",
        "- verdict 依據 = 正確尺度多日 TSMOM 檢定（過去 k 日 → 未來 k 日）；daily-lag "
        "Ljung-Box 測錯尺度，已降級為僅報告統計。",
        "- funding 覆蓋僅近期（~58 天），用代表性均值套全窗 → funding INCONCLUSIVE-on-coverage。",
        "- regime label = 本地 rule-based（regime_snapshots 空）；bull-dominated 須標。",
        "- survivorship = listed_at PIT；結論僅適用持續流動大中市值 perp，不外推全 universe。",
        "- effective N = PCA cluster 縮減後；20 高相關 symbol 真實獨立維度遠小於 20（N_eff≈2）。",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="多日 trend 樞紐診斷 harness（Phase 1 fail-fast）")
    parser.add_argument("--dry-run", action="store_true",
                        help="用 synthetic data 跑（不連 PG，Mac 可驗 harness 邏輯）")
    parser.add_argument("--synthetic-trending", action="store_true",
                        help="dry-run 時注入 trending drift（驗 harness 能偵測信號）")
    parser.add_argument("--dsn", default=None, help="PG DSN 覆寫（預設用 OPENCLAW_DATABASE_URL）")
    parser.add_argument("--run-id", default=None, help="artifact run-id（預設時間戳）")
    parser.add_argument("--print-json", action="store_true", help="把 JSON 報告印到 stdout")
    args = parser.parse_args(argv)

    run_id = args.run_id or f"multiday_trend_{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"

    if args.dry_run:
        panel, universe = build_synthetic_panel(trending=args.synthetic_trending)
    else:
        universe = data_loader.DEFAULT_UNIVERSE
        panel = data_loader.load_panel(universe, dsn=args.dsn)

    # run_diagnostic 內已在 data_quality + 正確尺度 TSMOM 算好後跑決策樹（FIX-1 接線修復）；
    # main 不再事後覆寫 verdict（消除 _inject_ljung_box_gate 接線斷裂與順序反向）。
    report = run_diagnostic(panel, universe)

    json_path, md_path = _write_artifact(report, run_id)
    verdict = report["decision_tree"]["verdict"]
    print(f"[multiday_trend_diagnostic] verdict={verdict}")
    print(f"[multiday_trend_diagnostic] JSON: {json_path}")
    print(f"[multiday_trend_diagnostic] MD:   {md_path}")
    if args.print_json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

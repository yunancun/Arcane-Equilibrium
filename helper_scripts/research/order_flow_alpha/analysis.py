#!/usr/bin/env python3
"""order_flow_alpha.analysis — 訂單流 alpha 3 軸研究 harness（$0 唯讀，OFFLINE）。

MODULE_NOTE
模塊用途：
  在 recorder-v2 累積的 market.trades / market.ob_top 上，做訂單流（order-flow）
  alpha 的初步 leak-free 信號檢測 + 決定性的「成本牆存活測試」。本檔是耐久交付物
  （harness 本身），數值是「指標性」初讀（單 regime、數十小時資料），多 regime 驗證
  需 1-2 週累積。最終 verdict 屬 QC，本檔只給 leak-free 量測 + 誠實成本對照，不下單、
  不實作任何交易。

  3 軸：
    Axis 1 — OFI 可預測性 + 持續性：OFI@5s/10s/30s 的 (a) 自相關（self-exciting vs
             white noise）、(b) 分位數分桶的前向 mid 報酬分佈（top/bottom decile OFI@10s
             是否預測 next 5s/15s mid move）。報每 decile 的 gross 預測 bps。
    Axis 2 — aggressor-flow clustering：buy/sell-initiated notional %、trade-direction
             run length、trade-sign autocorr @ lag 1/5/10（continuation vs reversal）。
    Axis 3 — microprice informativeness：microprice=(bid·ask_size+ask·bid_size)/(sizes)，
             microprice 是否 LEAD mid（未來 mid 是否朝當前 microprice 移動）+ 預測 bps。

  決定性測試（STEP 2，mandate-critical）：對任一有 gross 預測 edge 的軸，與「實際下單成本」
  對照——cross spread（taker ~6bp RT）或掛被動（4bp maker fee wall + queue risk）。
  報 per-signal：best-decile gross bps vs taker 成本牆，edge 是否 SURVIVE。

  REGIME-AWARE 決定性模式（--regime-split，2026-06-17 擴充）：
    決定性問題（calm 已證不過）：order-flow edge 是否在 HIGH-VOL regime（spread 變寬但 edge
    可能更寬）超過成本牆？由 regime.py（leak-free PIT 波動 regime 偵測器）把 tape 的每小時
    標 calm / elevated / high_vol，再對每個 regime 子集分別重跑 3 軸 + fee-wall（regime_split_
    decisive）。每個 regime 誠實揭露 n_hours / n_trade_rows；high_vol 樣本剛捕捉時 status=
    low_power_preliminary（指標性非定論）。current-state readout（regime_readout）恆計算：
    報窗內各 regime 小時數、是否已捕捉 high_vol 窗、若無則需多大 BTC move 才觸發。

依賴（READ-ONLY 復用 sibling 的 microstructure 資料層，不改其檔）：
  - program_code.research.microstructure.data_loader: connect / resolve_window /
    load_trades / load_obtop / liquid_symbols
  - program_code.research.microstructure.core: clean_obtop / build_grid / ofi /
    GRID_STEP_S / BETA_SYM / MIN_TRADES
  協調邊界：sibling（平行 session）擁有 fill_sim.py / mm_sizing_run.py / data_loader.py /
  core.py（CP-3 fill-sim、maker-close reprice、maker_markout instrumentation）。本檔只
  IMPORT 其 data_loader/core，0 修改；本軸與 fill-sim 正交（本檔測訊號是否存在 +
  能否負擔成本；sibling 測 maker fee wall 是 MM 的 binding constraint）。

硬邊界：
  - 純讀：sibling loader connect() 已 set_session(readonly=True)；本檔 0 寫 PG、0 order
    path、0 auth/lease/risk 觸碰、0 production code 改動。只寫 report artifact（--out）。
  - leak-free：前向報酬以 PIT realized（signal@t 只用 ≤t 資訊，target 在 [t,t+h)）；
    禁 current-bar rolling max/min；凡涉訊號做 naive-vs-leakfree 雙軌，背離即 flag。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import stats

# --- READ-ONLY 引入 sibling microstructure 資料層（不改其檔；加路徑供 import）---
# 為什麼這樣加路徑：本 harness 在 helper_scripts/research/order_flow_alpha/，
# sibling package 在 srv/program_code/research/microstructure/。向上推算 srv root
# （禁硬編 /Users 或 /home，跨平台），把 srv 加進 sys.path 後以套件路徑 import。
_THIS = os.path.realpath(__file__)
_THIS_DIR = os.path.dirname(_THIS)
_SRV_ROOT = os.path.abspath(os.path.join(_THIS, "..", "..", "..", ".."))
if _SRV_ROOT not in sys.path:
    sys.path.insert(0, _SRV_ROOT)
# 同目錄 sibling 模塊 regime.py（helper_scripts 非 package，無 __init__.py）→ 加本檔目錄。
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from program_code.research.microstructure import core as ms_core  # noqa: E402
from program_code.research.microstructure import data_loader as ms_loader  # noqa: E402

# regime 偵測器（同目錄 sibling 模塊，本 session 新增；leak-free PIT 波動 regime 標籤）。
import regime as ofa_regime  # noqa: E402

GRID_STEP_S = ms_core.GRID_STEP_S  # 5s 網格（沿用 sibling 對齊單位）
BETA_SYM = ms_core.BETA_SYM        # BTCUSDT

# --- 成本牆常數（與 14-軸結構鐵律對齊；report 內標明來源）---
# taker round-trip ~6bp（cross spread 進 + 出）；maker fee wall ~4bp（sibling 認定的
# binding constraint）。皆為「要 ACT on 訊號」的最低成本，非可選參數——這是 mandate 的
# 決定性對照標尺。bp = basis point = 1e-4。
TAKER_RT_BPS = 6.0
MAKER_RT_FEE_BPS = 4.0


# ============================================================================
# 共用：把訊號 series 對前向報酬做「分位數分桶 gross bps」+ leak guard
# ============================================================================
def _decile_forward_bps(signal: pd.Series, fwd_ret: pd.Series, n_bins: int = 10):
    """把 signal 分 n_bins 分位桶，報每桶的 mean 前向報酬（bps）+ 樣本數。

    為什麼 bps：前向報酬是 log-return，×1e4 轉 bps 便於對照成本牆。
    leak-free 前提：signal 與 fwd_ret 已由 caller 對齊成「signal@t 用 ≤t、fwd 在 [t,t+h)」。
    回傳 dict：per-bin 明細 + top/bottom decile spread（bps）。
    """
    df = pd.DataFrame({"sig": signal, "fwd": fwd_ret}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(df) < n_bins * 5:
        return {"n": int(len(df)), "insufficient": True}
    try:
        df["bin"] = pd.qcut(df["sig"], n_bins, labels=False, duplicates="drop")
    except ValueError:
        return {"n": int(len(df)), "insufficient": True, "reason": "qcut_degenerate"}
    nb = int(df["bin"].nunique())
    g = df.groupby("bin")["fwd"]
    per_bin = []
    for b, sub in g:
        per_bin.append({
            "bin": int(b),
            "n": int(len(sub)),
            "sig_mean": round(float(df.loc[df["bin"] == b, "sig"].mean()), 6),
            "fwd_bps": round(float(sub.mean()) * 1e4, 4),
        })
    top = per_bin[-1]["fwd_bps"]
    bot = per_bin[0]["fwd_bps"]
    return {
        "n": int(len(df)),
        "n_bins_effective": nb,
        "top_decile_bps": top,
        "bottom_decile_bps": bot,
        "long_short_spread_bps": round(top - bot, 4),
        "per_bin": per_bin,
    }


def _autocorr(x: np.ndarray, lag: int) -> float:
    """lag-k 自相關（Pearson on (x_t, x_{t+lag})），NaN-safe。"""
    x = np.asarray(x, dtype=float)
    if len(x) <= lag + 5:
        return float("nan")
    a, b = x[:-lag], x[lag:]
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 5:
        return float("nan")
    a, b = a[m], b[m]
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def _build_symbol_grids(tr, ob, syms):
    """per-symbol build_grid（沿用 sibling），含 mid（來自 clean_obtop）。

    回傳 dict[sym -> grid DataFrame]（index=ts），跳過 trade<MIN_TRADES 或無 mid 的 symbol。
    """
    ob_clean = ms_core.clean_obtop(ob) if not ob.empty else ob
    t0, t1 = tr["ts"].min().ceil("s"), tr["ts"].max().floor("s")
    grids = {}
    for s in syms:
        sub = tr[tr["symbol"] == s]
        if len(sub) < ms_core.MIN_TRADES:
            continue
        ob_s = ob_clean[ob_clean["symbol"] == s] if not ob_clean.empty else ob_clean
        grids[s] = ms_core.build_grid(sub, ob_s, t0, t1)
    return grids


# ============================================================================
# AXIS 1 — OFI 可預測性 + 持續性
# ============================================================================
def axis1_ofi(grids: dict) -> dict:
    """OFI@5s/10s/30s 的自相關 + decile 前向 mid 報酬。

    leak-free：ofi(w) 用 cumsum 差分 [t-w,t)（嚴格 ≤t）；前向報酬用 fwd(h, "mid")
    = log(mid_{t+h}/mid_t)（在特徵窗之後 [t,t+h)）。dual-track naive：用「同窗回溯
    報酬」(過去 h 已實現) 與 leak-free 前向對照，背離 = 無前視污染的證據。
    """
    windows = [5, 10, 30]
    horizons = [5, 15]
    out = {"per_window": {}, "decile_forward": {}, "naive_vs_leakfree": {}}

    # (a) OFI 自相關（pool 所有 symbol 的非重疊樣本，每窗 stride=w//grid 防重疊灌水）
    for w in windows:
        st = max(w // GRID_STEP_S, 1)
        ac1, ac2, ac3, npool = [], [], [], 0
        for s, g in grids.items():
            o = ms_core.ofi(g, w).dropna().values[::st]
            if len(o) < 30:
                continue
            ac1.append(_autocorr(o, 1)); ac2.append(_autocorr(o, 2)); ac3.append(_autocorr(o, 3))
            npool += len(o)
        out["per_window"][f"ofi_{w}s"] = {
            "n_symbols": int(np.isfinite(ac1).sum()) if ac1 else 0,
            "n_samples_nonoverlap": int(npool),
            "autocorr_lag1_mean": round(float(np.nanmean(ac1)), 4) if ac1 else None,
            "autocorr_lag2_mean": round(float(np.nanmean(ac2)), 4) if ac2 else None,
            "autocorr_lag3_mean": round(float(np.nanmean(ac3)), 4) if ac3 else None,
        }

    # (b) decile 前向 mid 報酬：OFI@10s 預測 next 5s / 15s mid move（pool over symbols）
    w = 10
    st = max(w // GRID_STEP_S, 1)
    for h in horizons:
        sig_all, fwd_all, fwd_naive_all = [], [], []
        for s, g in grids.items():
            if g["mid"].notna().sum() < 100:
                continue
            o = ms_core.ofi(g, w)
            f_lf = ms_core.fwd(g, h, "mid")              # leak-free 前向 [t,t+h)
            f_naive = np.log(g["mid"] / g["mid"].shift(h // GRID_STEP_S))  # naive 回溯 (past) 對照軌
            d = pd.DataFrame({"o": o, "f": f_lf, "fn": f_naive}).dropna()
            d = d.iloc[::st]  # 非重疊
            sig_all.append(d["o"].values); fwd_all.append(d["f"].values); fwd_naive_all.append(d["fn"].values)
        if not sig_all:
            out["decile_forward"][f"ofi10s_fwd{h}s"] = {"insufficient": True}
            continue
        sig = pd.Series(np.concatenate(sig_all))
        fwd_lf = pd.Series(np.concatenate(fwd_all))
        fwd_nv = pd.Series(np.concatenate(fwd_naive_all))
        res_lf = _decile_forward_bps(sig, fwd_lf)
        res_nv = _decile_forward_bps(sig, fwd_nv)
        out["decile_forward"][f"ofi10s_fwd{h}s"] = res_lf
        # dual-track 背離：leak-free 與 naive(回溯) 的 long-short spread 差；前向應 << 回溯
        # （若前向 ≈ 回溯，可疑有前視污染）。誠實對照軌，不是 alpha 宣稱。
        if not res_lf.get("insufficient") and not res_nv.get("insufficient"):
            out["naive_vs_leakfree"][f"ofi10s_fwd{h}s"] = {
                "leakfree_spread_bps": res_lf["long_short_spread_bps"],
                "naive_backward_spread_bps": res_nv["long_short_spread_bps"],
                "note": "naive=回溯(past)已實現報酬對照軌；leak-free=前向。兩者本質不同窗，"
                        "用於確認前向計算未誤引用未來 bar（前向 spread 不應鏡像回溯）。",
            }
    return out


# ============================================================================
# AXIS 2 — aggressor-flow clustering
# ============================================================================
def axis2_aggressor(tr: pd.DataFrame, syms) -> dict:
    """buy/sell-initiated notional %、run length、trade-sign autocorr @ lag 1/5/10。

    trade sign = native exchange aggressor side（Buy=+1 / Sell=-1，與 sibling sgn 一致）。
    leak-free：純逐筆 tape 統計，無前向 target，不涉前視。
    """
    out = {"per_symbol": [], "pooled": {}}
    pooled_buy_notional, pooled_sell_notional = 0.0, 0.0
    pooled_ac1, pooled_ac5, pooled_ac10, pooled_runs = [], [], [], []
    for s in syms:
        sub = tr[tr["symbol"] == s].sort_values("ts")
        if len(sub) < ms_core.MIN_TRADES:
            continue
        sign = np.where(sub["side"].values == "Buy", 1, -1)
        notional = (sub["price"].values * sub["qty"].values)
        buy_not = float(notional[sign > 0].sum())
        sell_not = float(notional[sign < 0].sum())
        tot = buy_not + sell_not
        # run length：連續同號 trade 串的平均長度（clustering 強度）
        runs = []
        cur = 1
        for i in range(1, len(sign)):
            if sign[i] == sign[i - 1]:
                cur += 1
            else:
                runs.append(cur); cur = 1
        runs.append(cur)
        mean_run = float(np.mean(runs)) if runs else float("nan")
        ac1 = _autocorr(sign, 1); ac5 = _autocorr(sign, 5); ac10 = _autocorr(sign, 10)
        out["per_symbol"].append({
            "symbol": s, "n_trades": int(len(sub)),
            "buy_notional_pct": round(buy_not / tot * 100, 2) if tot > 0 else None,
            "mean_run_length": round(mean_run, 3),
            "sign_autocorr_lag1": round(ac1, 4) if np.isfinite(ac1) else None,
            "sign_autocorr_lag5": round(ac5, 4) if np.isfinite(ac5) else None,
            "sign_autocorr_lag10": round(ac10, 4) if np.isfinite(ac10) else None,
        })
        pooled_buy_notional += buy_not; pooled_sell_notional += sell_not
        if np.isfinite(ac1): pooled_ac1.append(ac1)
        if np.isfinite(ac5): pooled_ac5.append(ac5)
        if np.isfinite(ac10): pooled_ac10.append(ac10)
        if np.isfinite(mean_run): pooled_runs.append(mean_run)
    tot = pooled_buy_notional + pooled_sell_notional
    out["pooled"] = {
        "n_symbols": len(out["per_symbol"]),
        "buy_notional_pct": round(pooled_buy_notional / tot * 100, 2) if tot > 0 else None,
        "mean_run_length_avg": round(float(np.mean(pooled_runs)), 3) if pooled_runs else None,
        "sign_autocorr_lag1_avg": round(float(np.mean(pooled_ac1)), 4) if pooled_ac1 else None,
        "sign_autocorr_lag5_avg": round(float(np.mean(pooled_ac5)), 4) if pooled_ac5 else None,
        "sign_autocorr_lag10_avg": round(float(np.mean(pooled_ac10)), 4) if pooled_ac10 else None,
        "interpretation": "正 sign-autocorr=continuation（aggressor flow 自我延續），"
                          "負=reversal。mean_run>1=有 clustering。本身不是 tradable edge，"
                          "需配合可預測前向 mid move（見 Axis 1/3）才有意義。",
    }
    return out


# ============================================================================
# AXIS 3 — microprice informativeness
# ============================================================================
def axis3_microprice(ob: pd.DataFrame, syms) -> dict:
    """microprice 是否 LEAD mid：未來 mid 是否朝當前 (microprice - mid) 方向移動。

    microprice = (bid·ask_size + ask·bid_size)/(bid_size+ask_size)（size-weighted，
    朝大 size 對側傾斜=朝即將被吃掉的那側）。
    leak-free：tilt@t = (microprice_t - mid_t)/mid_t 只用 t 的快照；target = 前向 mid
    報酬 (mid_{t+k}-mid_t)/mid_t（k 步 ob_top 取樣後，嚴格 > t）。用 ob_top 原生時序
    （非 5s 網格，因 microprice lead 在更細時標）。dual-track：對照 naive 同期相關。
    """
    out = {"per_symbol": [], "pooled": {}}
    ob_clean = ms_core.clean_obtop(ob) if not ob.empty else ob
    if ob_clean.empty:
        return {"insufficient": True, "reason": "no_clean_obtop"}
    # 前向步數（ob_top 取樣 ~250ms，k=4 ≈ 1s lead）
    K_STEPS = 4
    pooled_lf_ic, pooled_naive_ic, pooled_bps, pooled_net = [], [], [], []
    for s in syms:
        sub = ob_clean[ob_clean["symbol"] == s].sort_values("ts").reset_index(drop=True)
        if len(sub) < 200:
            continue
        bid, ask = sub["best_bid"].values, sub["best_ask"].values
        bs, as_ = sub["bid_size"].values, sub["ask_size"].values
        denom = bs + as_
        micro = np.where(denom > 0, (bid * as_ + ask * bs) / denom, np.nan)
        mid = sub["mid"].values
        # 該 symbol 自身的 full-spread（bps）= 跨 spread 捕捉 microprice 訊號的真實成本。
        # 為什麼這是關鍵：microprice 訊號是「mid 朝大-size 對側移動」，但要 ACT on 它必須
        # cross spread；若預測的 mid move < 自身 spread，就是 bid-ask bounce 假象（mid 在
        # spread 內機械反彈），不可交易。flat 6bp taker 牆對寬-spread alt 是低估，必須用
        # 自身 spread 對照。
        spread_full_bps = float(np.mean((ask - bid) / mid)) * 1e4
        # tilt@t（≤t 資訊）：microprice 相對 mid 的偏移（正=microprice 高於 mid=朝上）
        tilt = (micro - mid) / mid
        # 前向 mid 報酬（嚴格 > t）：mid_{t+K}/mid_t - 1
        fwd_mid = np.full_like(mid, np.nan)
        if len(mid) > K_STEPS:
            fwd_mid[:-K_STEPS] = mid[K_STEPS:] / mid[:-K_STEPS] - 1.0
        # naive 同期對照：tilt@t vs 同期 mid 變化（mid_t/mid_{t-K}-1），非前向
        naive_ret = np.full_like(mid, np.nan)
        if len(mid) > K_STEPS:
            naive_ret[K_STEPS:] = mid[K_STEPS:] / mid[:-K_STEPS] - 1.0  # 對齊到 t（回溯）
        d = pd.DataFrame({"tilt": tilt, "fwd": fwd_mid, "naive": naive_ret}).replace(
            [np.inf, -np.inf], np.nan).dropna()
        if len(d) < 100:
            continue
        # leak-free：tilt 預測前向 mid（Spearman IC）
        ic_lf, _ = stats.spearmanr(d["tilt"], d["fwd"])
        ic_nv, _ = stats.spearmanr(d["tilt"], d["naive"])
        # gross 預測 bps：top-decile tilt 的前向 mid move
        res = _decile_forward_bps(d["tilt"], d["fwd"])
        spread_bps = res.get("long_short_spread_bps") if not res.get("insufficient") else None
        # net = mid-to-mid 預測 move − 自身 full-spread（跨 spread 的真實成本）。
        # net>0 才是 spread-內反彈以外的真方向 alpha；net<0 = bid-ask bounce 假象。
        net_of_spread = (round(spread_bps - spread_full_bps, 4)
                         if spread_bps is not None else None)
        out["per_symbol"].append({
            "symbol": s, "n": int(len(d)),
            "leadlag_ic_leakfree": round(float(ic_lf), 4) if np.isfinite(ic_lf) else None,
            "leadlag_ic_naive_contemp": round(float(ic_nv), 4) if np.isfinite(ic_nv) else None,
            "tilt_decile_fwd_spread_bps": spread_bps,
            "own_full_spread_bps": round(spread_full_bps, 4),
            "net_edge_minus_own_spread_bps": net_of_spread,
        })
        if np.isfinite(ic_lf): pooled_lf_ic.append(float(ic_lf))
        if np.isfinite(ic_nv): pooled_naive_ic.append(float(ic_nv))
        if spread_bps is not None: pooled_bps.append(spread_bps)
        if net_of_spread is not None: pooled_net.append(net_of_spread)
    out["per_symbol"].sort(key=lambda d: -(d["leadlag_ic_leakfree"] or -9))
    out["pooled"] = {
        "n_symbols": len(out["per_symbol"]),
        "k_steps_ahead": K_STEPS,
        "approx_lead_ms": K_STEPS * 250,
        "leadlag_ic_leakfree_avg": round(float(np.mean(pooled_lf_ic)), 4) if pooled_lf_ic else None,
        "leadlag_ic_naive_contemp_avg": round(float(np.mean(pooled_naive_ic)), 4) if pooled_naive_ic else None,
        "tilt_decile_fwd_spread_bps_avg": round(float(np.mean(pooled_bps)), 4) if pooled_bps else None,
        "net_edge_minus_own_spread_bps_avg": round(float(np.mean(pooled_net)), 4) if pooled_net else None,
        "n_symbols_net_positive": int(sum(1 for v in pooled_net if v > 0)),
        "interpretation": "正 leak-free lead-lag IC = microprice tilt 領先 mid（mid 朝 "
                          "microprice 移動）。但 tilt_decile_fwd_spread_bps 是 mid-to-mid，"
                          "要 ACT 必 cross spread → 真實成本=own_full_spread_bps。"
                          "net_edge_minus_own_spread_bps<0 = 預測 move 小於自身 spread = "
                          "bid-ask bounce 假象（mid 在 spread 內機械反彈），不可交易。"
                          "naive 同期 IC ≠ 前向 IC 確認無前視污染。",
    }
    return out


# ============================================================================
# STEP 2 — 成本牆存活測試
# ============================================================================
def fee_wall_test(axis1: dict, axis3: dict) -> dict:
    """對任一有 gross 預測 edge 的訊號，對照 taker round-trip 成本牆。

    判定：best-decile gross |bps| vs TAKER_RT_BPS（6bp）。SURVIVE = gross > 成本牆。
    這是 mandate 的決定性測試：預測 +2bp 但要 6bp 成本去捕捉 = 真訊號但 uninvestable
    （與殺死前 14 軸的同一道牆）。
    """
    signals = []
    # Axis 1：OFI@10s decile spread（5s / 15s 前向）
    for key, res in axis1.get("decile_forward", {}).items():
        if isinstance(res, dict) and not res.get("insufficient"):
            gross = abs(res.get("long_short_spread_bps", 0.0))
            signals.append({
                "signal": f"OFI@10s_long_short_{key}",
                "gross_predicted_bps": res.get("long_short_spread_bps"),
                "gross_abs_bps": round(gross, 4),
            })
    # Axis 3：microprice tilt decile spread。
    # 關鍵：gross 是 mid-to-mid move，但 microprice 訊號要 ACT 必 cross spread，
    # 真實成本=訊號自身的 own_full_spread（不是 flat 6bp）。故 microprice 的「淨 edge」=
    # net_edge_minus_own_spread_bps_avg；正才有 spread-內反彈以外的真方向 alpha。
    a3 = axis3.get("pooled", {})
    if a3.get("tilt_decile_fwd_spread_bps_avg") is not None:
        gross = a3["tilt_decile_fwd_spread_bps_avg"]
        net = a3.get("net_edge_minus_own_spread_bps_avg")
        signals.append({
            "signal": "microprice_tilt_decile_spread",
            "gross_predicted_bps": gross,
            "gross_abs_bps": round(abs(gross), 4),
            "is_cross_spread_signal": True,  # 成本=自身 spread，非 flat 6bp
            "net_minus_own_spread_bps": net,
            "n_symbols_net_positive": a3.get("n_symbols_net_positive"),
        })
    verdicts = []
    for sig in signals:
        # microprice 是 cross-spread 訊號：用 net_minus_own_spread 判存活（正才存活）。
        # OFI decile 是 5s-grid 方向訊號：用 gross_abs vs taker/maker 牆判存活。
        if sig.get("is_cross_spread_signal"):
            net = sig.get("net_minus_own_spread_bps")
            survives = bool(net is not None and net > 0)
            verdicts.append({
                **sig,
                "cost_basis": "own_full_spread (cross-spread signal)",
                "survives_taker_wall": survives,
                "survives_maker_fee_wall": survives,
                "verdict": ("SURVIVES_OWN_SPREAD" if survives
                            else "ARTIFACT_BELOW_OWN_SPREAD"),
            })
            continue
        g = sig["gross_abs_bps"]
        verdicts.append({
            **sig,
            "cost_basis": "flat taker/maker wall",
            "taker_rt_cost_bps": TAKER_RT_BPS,
            "maker_rt_fee_bps": MAKER_RT_FEE_BPS,
            "survives_taker_wall": bool(g > TAKER_RT_BPS),
            "survives_maker_fee_wall": bool(g > MAKER_RT_FEE_BPS),
            "net_vs_taker_bps": round(g - TAKER_RT_BPS, 4),
            "verdict": ("SURVIVES_TAKER" if g > TAKER_RT_BPS
                        else "SURVIVES_MAKER_FEE_ONLY" if g > MAKER_RT_FEE_BPS
                        else "DOES_NOT_SURVIVE_COST_WALL"),
        })
    return {
        "cost_wall_model": {
            "taker_round_trip_bps": TAKER_RT_BPS,
            "maker_round_trip_fee_bps": MAKER_RT_FEE_BPS,
            "note": "taker=cross spread 進+出；maker=post passive 但面對 sibling 認定的 "
                    "binding maker fee wall + queue risk。要 ACT on order-flow 訊號的最低成本。",
        },
        "per_signal": verdicts,
        "any_survives_taker": any(v["survives_taker_wall"] for v in verdicts),
        "any_survives_maker_fee": any(v["survives_maker_fee_wall"] for v in verdicts),
    }


# ============================================================================
# REGIME-SPLIT 決定性測試（calm / elevated / high_vol 各跑 3 軸 + fee-wall）
# ============================================================================
def _filter_tape_by_regime(tr: pd.DataFrame, ob: pd.DataFrame, hour_regime: pd.Series, regime: str):
    """把 trade / ob_top tape 按「該筆所屬小時的 regime 標籤」過濾出指定 regime 的子集。

    leak-free：hour_regime 的小時標籤本身 PIT（regime.classify_hours 用 shift(1) RV），
    一筆 tick 落在哪小時就繼承那小時的標籤；不引用該小時內的未來。
    """
    def _mask(df):
        if df.empty:
            return df
        floored = df["ts"].dt.floor("h")
        labels = floored.map(hour_regime)
        return df[labels == regime].copy()
    return _mask(tr), _mask(ob)


def regime_split_decisive(tr, ob, sel, hour_regime) -> dict:
    """對 calm / elevated / high_vol 各 regime 分別跑 3 軸 + fee-wall test。

    決定性問題（mandate-critical）：order-flow edge 是否在 HIGH-VOL regime 超過成本牆？
    （calm 已證不過。）對每個 regime 子集重建 grids（OFI 用）→ 跑 axis1/2/3 → fee_wall_test。
    回傳 per-regime 的 axes + fee-wall verdict + n_hours / n_trade_rows（樣本量誠實揭露）。

    honesty：high-vol 窗若樣本太薄（剛捕捉），verdict 標 preliminary / low-power，不 overclaim。
    """
    hour_regime_map = {pd.Timestamp(k): v for k, v in hour_regime.items()}
    out = {}
    for rg in ("calm", "elevated", "high_vol"):
        tr_r, ob_r = _filter_tape_by_regime(tr, ob, hour_regime, rg)
        n_hours = int(sum(1 for v in hour_regime_map.values() if v == rg))
        block = {
            "n_hours_labelled": n_hours,
            "n_trade_rows": int(len(tr_r)),
            "n_obtop_rows": int(len(ob_r)),
        }
        if tr_r.empty or len(tr_r) < ms_core.MIN_TRADES:
            block["status"] = "insufficient_sample"
            out[rg] = block
            continue
        # BTC 必須在 regime 子集內（OFI grid / 一致性），否則 axis1 grid 仍可跑（不殘差化）。
        grids_r = _build_symbol_grids(tr_r, ob_r, sel)
        a1 = axis1_ofi(grids_r)
        a2 = axis2_aggressor(tr_r, sel)
        a3 = axis3_microprice(ob_r, sel)
        fw = fee_wall_test(a1, a3)
        block.update({
            "symbols_with_valid_grid": sorted(grids_r.keys()),
            "btc_present": BETA_SYM in grids_r,
            "axis1_ofi": a1,
            "axis2_aggressor_flow": a2,
            "axis3_microprice": a3,
            "fee_wall_test": fw,
        })
        # power 守衛：high_vol 窗若 < ~6 小時 / grid symbol 太少，標 low-power 不下定論。
        low_power = (rg == "high_vol" and (n_hours < 6 or len(grids_r) < 3))
        block["status"] = "low_power_preliminary" if low_power else "ok"
        out[rg] = block
    # 決定性彙總：是否有任一 regime（特別 high_vol）有訊號過牆。
    def _survives(rg):
        b = out.get(rg, {})
        fw = b.get("fee_wall_test", {})
        return bool(fw.get("any_survives_taker") or fw.get("any_survives_maker_fee"))
    out["_decisive_summary"] = {
        "high_vol_any_survives": _survives("high_vol"),
        "elevated_any_survives": _survives("elevated"),
        "calm_any_survives": _survives("calm"),
        "high_vol_status": out.get("high_vol", {}).get("status"),
        "verdict": (
            "AWAITING_VOL_EVENT" if out.get("high_vol", {}).get("status") == "insufficient_sample"
            else "HIGH_VOL_PRELIMINARY_LOW_POWER" if out.get("high_vol", {}).get("status") == "low_power_preliminary"
            else "HIGH_VOL_EDGE_SURVIVES" if _survives("high_vol")
            else "HIGH_VOL_NO_EDGE_SURVIVES"
        ),
        "note": "決定性問題：order-flow edge 是否在 high_vol regime 過成本牆。high_vol 樣本剛"
                "捕捉時 status=low_power_preliminary，verdict 是指標性非定論；最終屬 QC。",
    }
    return out


# ============================================================================
# 主流程
# ============================================================================
def run(hours, since, until, top_n, out_path, regime_split=False):
    conn = ms_loader.connect()
    try:
        since_ts, until_ts = ms_loader.resolve_window(conn, hours, since, until)
        liquid = ms_loader.liquid_symbols(conn, since_ts, until_ts, min_trades=ms_core.MIN_TRADES)
        # 取前 top_n（按窗內 trade 數），但永遠確保 BTCUSDT 在內（beta 因子需要）
        cur = conn.cursor()
        where, params = ms_loader._window_clause(since_ts, until_ts)
        cur.execute("SELECT symbol, count(*) FROM market.trades" + where
                    + " GROUP BY symbol HAVING count(*) >= %s ORDER BY count(*) DESC",
                    params + [ms_core.MIN_TRADES])
        ranked = [(r[0], r[1]) for r in cur.fetchall()]
        cur.close()
        sel = [s for s, _ in ranked[:top_n]]
        if BETA_SYM not in sel and BETA_SYM in liquid:
            sel.append(BETA_SYM)
        tr = ms_loader.load_trades(conn, since_ts, until_ts)
        tr = tr[tr["symbol"].isin(sel)].copy()
        ob = ms_loader.load_obtop(conn, since_ts, until_ts)
        ob = ob[ob["symbol"].isin(sel)].copy()
        # regime backdrop / current-state readout（恆計算，便宜；split 才額外分桶跑軸）。
        regime_readout = ofa_regime.window_regime(conn, since_ts, until_ts)
        hour_regime = None
        if regime_split:
            labelled, _thr, _spk = ofa_regime.classify_hours(conn)
            # 只取窗內的小時標籤 → Series[ts(hour) -> regime]。
            lab = labelled
            if since_ts is not None:
                lab = lab[lab["ts"] >= pd.Timestamp(since_ts)]
            if until_ts is not None:
                lab = lab[lab["ts"] < pd.Timestamp(until_ts)]
            hour_regime = pd.Series(lab["regime"].values, index=pd.DatetimeIndex(lab["ts"]))
    finally:
        conn.close()

    grids = _build_symbol_grids(tr, ob, sel)
    grid_syms = sorted(grids.keys())
    a1 = axis1_ofi(grids)
    a2 = axis2_aggressor(tr, sel)
    a3 = axis3_microprice(ob, sel)
    fw = fee_wall_test(a1, a3)

    report = {
        "harness": "order_flow_alpha.analysis",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "preliminary_caveat": "指標性初讀：單 regime、數十小時資料。harness 本身是耐久交付物；"
                              "多 regime 驗證需 1-2 週累積。最終 verdict 屬 QC。不下單、不實作交易。",
        "regime_readout": regime_readout,
        "data_readiness": {
            "window_since": since_ts.isoformat() if since_ts else None,
            "window_until": until_ts.isoformat() if until_ts else None,
            "n_liquid_symbols": len(liquid),
            "selected_symbols": sel,
            "symbols_with_valid_grid": grid_syms,
            "n_trade_rows_loaded": int(len(tr)),
            "n_obtop_rows_loaded": int(len(ob)),
            "btc_present": BETA_SYM in grids,
            "ranked_top": [{"symbol": s, "n_trades": n} for s, n in ranked[:top_n]],
        },
        "axis1_ofi": a1,
        "axis2_aggressor_flow": a2,
        "axis3_microprice": a3,
        "fee_wall_test": fw,
    }
    if regime_split and hour_regime is not None:
        report["regime_split_decisive"] = regime_split_decisive(tr, ob, sel, hour_regime)
    if out_path:
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
    return report


def main():
    ap = argparse.ArgumentParser(description="order-flow alpha 3-axis research harness ($0 read-only)")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--hours", type=float, help="相對最新資料的 N 小時窗")
    ap.add_argument("--since", type=str, help="ISO8601 起始（含）")
    ap.add_argument("--until", type=str, help="ISO8601 結束（不含）")
    ap.add_argument("--top-n", type=int, default=15, help="取窗內最活躍前 N symbol（含 BTC）")
    ap.add_argument("--out", type=str, default="", help="report JSON 輸出路徑（不給=stdout）")
    ap.add_argument("--regime-split", action="store_true",
                    help="regime-split 決定性模式：calm/elevated/high_vol 各跑 3 軸 + fee-wall")
    args = ap.parse_args()
    rep = run(args.hours, args.since, args.until, args.top_n, args.out or None,
              regime_split=args.regime_split)
    # stdout 永遠印精簡摘要（即使有 --out），供 cron/log 即時可讀
    dr = rep["data_readiness"]
    fw = rep["fee_wall_test"]
    rr = rep.get("regime_readout", {})
    summary = {
        "window": [dr["window_since"], dr["window_until"]],
        "n_liquid_symbols": dr["n_liquid_symbols"],
        "n_grid_symbols": len(dr["symbols_with_valid_grid"]),
        "n_trade_rows": dr["n_trade_rows_loaded"],
        "regime_readout": {
            "regime_hour_counts": rr.get("regime_hour_counts"),
            "has_high_vol_window": rr.get("has_high_vol_window"),
            "high_vol_hours": rr.get("high_vol_hours"),
            "trigger_note_if_no_high_vol": rr.get("trigger_note_if_no_high_vol"),
        },
        "fee_wall_summary": {
            "any_survives_taker": fw["any_survives_taker"],
            "any_survives_maker_fee": fw["any_survives_maker_fee"],
            "per_signal": [{"signal": v["signal"], "gross_bps": v["gross_predicted_bps"],
                            "verdict": v["verdict"]} for v in fw["per_signal"]],
        },
    }
    if "regime_split_decisive" in rep:
        rs = rep["regime_split_decisive"]
        summary["regime_split_decisive_summary"] = rs.get("_decisive_summary")
        summary["regime_split_per_regime"] = {
            rg: {
                "status": rs[rg].get("status"),
                "n_hours": rs[rg].get("n_hours_labelled"),
                "n_trade_rows": rs[rg].get("n_trade_rows"),
                "fee_wall": ({
                    "any_survives_taker": rs[rg]["fee_wall_test"]["any_survives_taker"],
                    "any_survives_maker_fee": rs[rg]["fee_wall_test"]["any_survives_maker_fee"],
                    "per_signal": [{"signal": v["signal"], "gross_bps": v["gross_predicted_bps"],
                                    "verdict": v["verdict"]}
                                   for v in rs[rg]["fee_wall_test"]["per_signal"]],
                } if "fee_wall_test" in rs[rg] else None),
            }
            for rg in ("calm", "elevated", "high_vol") if rg in rs
        }
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()

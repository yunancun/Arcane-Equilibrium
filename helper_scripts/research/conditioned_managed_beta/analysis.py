"""條件化 managed-beta 流（stream_F）edge-rescue 測試（純 1d kline，唯讀研究）。

MODULE_NOTE:
  模塊用途：承接 dual_stream_tail_codependence 的決定性 follow-up。前測證明
    stream_F（leak-free vol-target BTC TSMOM）standalone Sharpe = −0.18（net-negative），
    且 architecture 正交（good）。本測回答 operator 的「beta-timing 可在對的訊號/基建下成立」
    thesis 的窄門問題：一個 CONDITIONING 訊號能否把 managed-beta 流從 −0.18 翻成
    真正的正風險調整 edge？
  這是整個 arc 中**最高假陽性風險**的測試（用多個訊號 condition 單一 BTC 序列、N_eff≈1，
    教科書級 spurious-edge factory）→ **multiple-testing 紀律強制**（DSR(K) 用誠實 K），
    且一個誠實的 NEGATIVE 是預期且有價值的結果。
  PRE-REGISTERED 變體（結果出來前固定，誠實報 K）：
    V1  breadth-gate：% of 26-sym universe close>own SMA(50)(shift1)，按 tercile full/half/zero。
    V1f breadth sign-flip：低 breadth tercile 反向（short）而非 zero。
    V2  vol-regime-gate：已實現 vol tercile，low/mid ON、top OFF。
    V2f vol-regime sign-flip：top-vol tercile 反向而非 OFF。
    V3  trend-strength conviction gate：|trailing ret|/realized-vol > 門檻才取 TSMOM 曝險。
    V3f trend-strength sign-flip：低 conviction 反向而非 zero。
    （V4 cross-asset 只在從既有資料便宜可得時做；否則 skip 並說明。）
    K（顯式計數）= 上述變體數（含 V4 若做）。
  BASELINES 必須擊敗（不只擊敗 0）：(i) buy-and-hold BTC、(ii) unconditioned stream_F
    (Sharpe −0.18)、(iii) naive MA-trend。最佳變體須**實質**勝 (ii) AND 為正。
  PROTOCOL（嚴格）：walk-forward anchored-expanding（≥4 fold、≥5d embargo、OOS≥0.3·IS）；
    **禁** current-bar rolling max/min（repo trend.rs::donchian 有此 bug，不重用）；
    shift(1) everywhere；naive-vs-leakfree 雙軌（背離 >30% 旗標）；net of ~1.3bp/side。
  報 per-variant + aggregate：net annualized Sharpe + Sortino + Calmar + maxDD、
    PSR(0) skew-kurt-aware（**非** normal-z）、DSR(K)（誠實 K）、PBO via CSCV、
    block-bootstrap Sharpe 95% CI lower bound、regime-split（bull/chop/down——
    只在 bull 為正=regime-bet/learning-only per governance，**非** pass）。
  PASS BAR（全部必達）：最佳變體 net Sharpe > 0 AND PSR(0)≥0.95 AND DSR(K)≥0.90
    AND bootstrap CI lower bound > 0 AND OOS-positive AND not bull-only。
    少於全達 = NO，OHLCV-conditioning 救不了 managed-beta。
  硬邊界（研究紅線）：PG 唯讀；realized only；shift(1) everywhere；不碰 runtime/order/
    risk/auth；不修 production engine 代碼；**最終 verdict 不由本腳本下**（交 QC）。
  依賴：psycopg2 / numpy / scipy（延遲 import）。復用 dual_stream_tail_codependence
    的 build_stream_F / perf_stats / regime_labels / load_daily_closes 等 warm 原語。
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
from pathlib import Path

import numpy as np

# 復用前測的 warm harness（同目錄上一層 research/dual_stream_tail_codependence）。
_HERE = Path(__file__).resolve()
_RESEARCH = _HERE.parent.parent  # helper_scripts/research/
sys.path.insert(0, str(_RESEARCH / "dual_stream_tail_codependence"))
import analysis as ds  # noqa: E402  warm harness（stream_F / perf_stats / regime_labels）

# 與前測一致的常數（SSOT 對齊，不重定義數學）。
COST_BP_PER_SIDE = ds.COST_BP_PER_SIDE       # 1.3 bp/side
ANN = ds.ANN                                  # 365
VOL_TARGET_ANN = ds.VOL_TARGET_ANN            # 0.40
MAX_LEVERAGE = ds.MAX_LEVERAGE                # 3.0
TSMOM_LOOKBACK = ds.TSMOM_LOOKBACK            # 30
VOL_LOOKBACK = ds.VOL_LOOKBACK                # 30

# 條件訊號窗。
SMA_LOOKBACK = 50          # breadth：close > 自身 trailing SMA(50)
CONVICTION_LOOKBACK = TSMOM_LOOKBACK  # trend-strength 用同一 trailing return 窗


def build_stream_F_positions(btc_ret: np.ndarray) -> np.ndarray:
    """重算 stream_F 的**倉位序列**（與 build_stream_F 同邏輯，但回傳 pos 供 conditioning）。

    為什麼要單獨拿 pos：conditioning 是對「曝險」做門控（full/half/zero/flip），需在
    成本 haircut 前對 pos 做縮放，故必須拿到 leak-free pos 而非已淨化的 PnL。
    與 ds.build_stream_F 的 pos 計算**逐行對齊**（shift(1)、禁 current-bar），確保
    unconditioned baseline 與本函數的 gate=full 完全一致（mutation A/B 驗）。
    """
    T = len(btc_ret)
    pos = np.zeros(T)
    for t in range(T):
        mom_win = btc_ret[max(0, t - TSMOM_LOOKBACK):t]
        vol_win = btc_ret[max(0, t - VOL_LOOKBACK):t]
        if mom_win.size < TSMOM_LOOKBACK or vol_win.size < VOL_LOOKBACK:
            continue
        mom = np.nansum(mom_win)
        sgn = 1.0 if mom > 0 else (-1.0 if mom < 0 else 0.0)
        rv_ann = np.nanstd(vol_win, ddof=1) * math.sqrt(ANN)
        if not np.isfinite(rv_ann) or rv_ann <= 1e-9:
            continue
        size = float(np.clip(VOL_TARGET_ANN / rv_ann, 0.0, MAX_LEVERAGE))
        pos[t] = sgn * size
    return pos


def pnl_from_pos(pos: np.ndarray, btc_ret: np.ndarray) -> np.ndarray:
    """pos → net PnL（gross − turnover×cost），與 ds.build_stream_F 尾段同式。"""
    gross = pos * np.nan_to_num(btc_ret, nan=0.0)
    turnover = np.abs(np.diff(pos, prepend=0.0))
    cost = turnover * (COST_BP_PER_SIDE * 1e-4)
    return gross - cost


# ---------------------------------------------------------------------------
# 條件訊號（全 shift(1)，point-in-time，禁 current-bar）
# ---------------------------------------------------------------------------
def breadth_signal(returns: np.ndarray, close_mat_aligned: np.ndarray) -> np.ndarray:
    """% of universe 中 close > 自身 trailing SMA(50)，**截至 t-1**（shift(1)）。

    為什麼 shift(1)：第 t 期的 gate 只能用 t-1 收盤可知的 breadth，否則用當期收盤=前視。
    close_mat_aligned 已對齊到 returns 的日期軸（returns[t] = close[t+1]/close[t] 的當期，
      故 breadth 用 close 在 returns 索引 t 對應的「前一收盤」= close_mat_aligned[t]，
      其 SMA 用 [t-50, t-1] 不含 t → 嚴格 trailing）。
    回傳每期 breadth fraction ∈[0,1]；窗不足 = NaN。
    """
    T, N = returns.shape
    out = np.full(T, np.nan)
    # close_mat_aligned: 形如 returns 的 [T, N]，close_mat_aligned[t] = 第 t 期報酬的「起始收盤」。
    for t in range(T):
        if t < SMA_LOOKBACK + 1:
            continue
        n_above = 0
        n_valid = 0
        for j in range(N):
            # trailing SMA 窗 [t-SMA_LOOKBACK, t-1]（不含 t），與當期 close[t-1] 比。
            win = close_mat_aligned[t - SMA_LOOKBACK:t, j]
            cur = close_mat_aligned[t - 1, j]  # t-1 收盤（shift(1)：t 期 gate 只知到 t-1）
            mask = np.isfinite(win)
            if np.count_nonzero(mask) < SMA_LOOKBACK // 2 or not np.isfinite(cur):
                continue
            sma = np.mean(win[mask])
            n_valid += 1
            if cur > sma:
                n_above += 1
        if n_valid >= 4:
            out[t] = n_above / n_valid
    return out


def realized_vol_signal(btc_ret: np.ndarray) -> np.ndarray:
    """BTC 已實現年化 vol，trailing 窗 [t-VOL_LOOKBACK, t-1]（shift(1)）。"""
    T = len(btc_ret)
    out = np.full(T, np.nan)
    for t in range(T):
        win = btc_ret[max(0, t - VOL_LOOKBACK):t]
        if win.size < VOL_LOOKBACK:
            continue
        rv = np.nanstd(win, ddof=1) * math.sqrt(ANN)
        if np.isfinite(rv):
            out[t] = rv
    return out


def conviction_signal(btc_ret: np.ndarray) -> np.ndarray:
    """trend-strength = |trailing return| / trailing realized-vol（shift(1)）。

    為什麼：TSMOM 的「conviction」= 趨勢報酬相對其波動的強度（類 t-stat），高=強趨勢。
    """
    T = len(btc_ret)
    out = np.full(T, np.nan)
    for t in range(T):
        mom_win = btc_ret[max(0, t - CONVICTION_LOOKBACK):t]
        vol_win = btc_ret[max(0, t - VOL_LOOKBACK):t]
        if mom_win.size < CONVICTION_LOOKBACK or vol_win.size < VOL_LOOKBACK:
            continue
        cum = np.nansum(mom_win)
        sd = np.nanstd(vol_win, ddof=1)
        if np.isfinite(sd) and sd > 1e-12:
            out[t] = abs(cum) / (sd * math.sqrt(CONVICTION_LOOKBACK))
    return out


# ---------------------------------------------------------------------------
# 變體 gate：把 base pos 依條件訊號 tercile 做 full/half/zero/flip 縮放
# ---------------------------------------------------------------------------
def _tercile_bounds(sig: np.ndarray, ref_mask: np.ndarray) -> tuple[float, float]:
    """用 ref_mask（通常 = IS 窗，避免用全樣本 tercile 洩漏未來）算 33/67 分位。"""
    vals = sig[ref_mask & np.isfinite(sig)]
    if vals.size < 10:
        return float("nan"), float("nan")
    return float(np.quantile(vals, 1 / 3)), float(np.quantile(vals, 2 / 3))


def apply_gate(
    base_pos: np.ndarray,
    sig: np.ndarray,
    lo: float,
    hi: float,
    mode: str,
) -> np.ndarray:
    """依 sig tercile 對 base_pos 做門控。mode ∈ {breadth, breadth_flip, voloff,
    voloff_flip, conviction, conviction_flip}。

    為什麼 gate 用 IS-derived tercile bounds（lo/hi 由 caller 傳 IS 窗算）：避免用
      全樣本 tercile 把未來分位資訊洩漏進當期 gate（walk-forward 嚴格性）。
    NaN sig（暖機）→ exposure 0（fail-closed：訊號未知不冒險）。
    """
    pos = np.zeros_like(base_pos)
    for t in range(len(base_pos)):
        s = sig[t]
        if not np.isfinite(s) or not np.isfinite(lo) or not np.isfinite(hi):
            continue  # fail-closed
        if mode == "breadth":
            # 高 breadth → full、中 → half、低 → zero（趨勢順風才全曝險）。
            if s >= hi:
                pos[t] = base_pos[t]
            elif s >= lo:
                pos[t] = 0.5 * base_pos[t]
            else:
                pos[t] = 0.0
        elif mode == "breadth_flip":
            # 低 breadth tercile 反向（短）而非 zero。
            if s >= hi:
                pos[t] = base_pos[t]
            elif s >= lo:
                pos[t] = 0.5 * base_pos[t]
            else:
                pos[t] = -base_pos[t]
        elif mode == "voloff":
            # low/mid vol ON、top vol OFF。
            if s >= hi:
                pos[t] = 0.0
            else:
                pos[t] = base_pos[t]
        elif mode == "voloff_flip":
            # top vol tercile 反向而非 OFF。
            if s >= hi:
                pos[t] = -base_pos[t]
            else:
                pos[t] = base_pos[t]
        elif mode == "conviction":
            # 高 conviction → full、中 → half、低 → zero。
            if s >= hi:
                pos[t] = base_pos[t]
            elif s >= lo:
                pos[t] = 0.5 * base_pos[t]
            else:
                pos[t] = 0.0
        elif mode == "conviction_flip":
            # 低 conviction 反向而非 zero。
            if s >= hi:
                pos[t] = base_pos[t]
            elif s >= lo:
                pos[t] = 0.5 * base_pos[t]
            else:
                pos[t] = -base_pos[t]
        else:
            raise ValueError(f"unknown gate mode {mode}")
    return pos


# ---------------------------------------------------------------------------
# DSR / PSR / PBO / block-bootstrap（multiple-testing 紀律）
# ---------------------------------------------------------------------------
def deflated_sharpe(sr_hat_ann: float, n: int, skew: float, kurt: float, K: int,
                    var_sr_trials: float | None = None) -> dict:
    """Deflated Sharpe Ratio（Bailey & Lopez de Prado 2014）。

    為什麼用 DSR 而非 PSR：本測跑了 K 個變體，最佳變體的 Sharpe 有 selection bias；
      DSR 用 expected-max-of-K-Sharpe 當基準（非 0），對 multiple testing 去膨脹。
    sr_hat_ann：最佳變體的年化 Sharpe（注意：DSR 內部用每期 SR）。
    var_sr_trials：K 個 trial 的每期-SR 樣本變異（用於 E[max]）；None 時用保守上界。
    """
    from scipy import stats as sps

    sr = sr_hat_ann / math.sqrt(ANN)  # 年化 → 每期
    if var_sr_trials is None or not np.isfinite(var_sr_trials) or var_sr_trials <= 0:
        # 保守：用 PSR 的 SR 估計變異 (1/n) 當 trial 變異上界。
        var_sr_trials = 1.0 / max(n, 2)
    sigma_sr = math.sqrt(var_sr_trials)
    # E[max of K iid 標準常態] 近似（Bailey-LdP）。
    euler = 0.5772156649
    if K <= 1:
        sr0 = 0.0
    else:
        z1 = sps.norm.ppf(1 - 1.0 / K)
        z2 = sps.norm.ppf(1 - 1.0 / (K * math.e))
        sr0 = sigma_sr * ((1 - euler) * z1 + euler * z2)
    # DSR = PSR 但 benchmark 用 sr0（expected max）而非 0。
    denom = math.sqrt(max(1e-12, 1 - skew * sr + ((kurt - 1) / 4.0) * sr ** 2))
    dsr_z = ((sr - sr0) * math.sqrt(n - 1)) / denom
    return {
        "sr_per_period": sr, "sr0_expected_max": sr0,
        "sigma_sr_trial": sigma_sr, "K": K, "dsr_z": dsr_z,
        "dsr": float(sps.norm.cdf(dsr_z)),
    }


def block_bootstrap_sharpe_ci(pnl: np.ndarray, n_boot: int = 5000,
                              block: int = 10, seed: int = 20260617) -> dict:
    """circular block bootstrap 的年化 Sharpe 95% CI（保留自相關）。"""
    r = pnl[np.isfinite(pnl)]
    n = r.size
    if n < 30:
        return {"insufficient": True, "n": int(n)}
    rng = np.random.default_rng(seed)
    n_blocks = int(math.ceil(n / block))
    sharpes = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, size=n_blocks)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel() % n
        sample = r[idx[:n]]
        sd = sample.std(ddof=1)
        sharpes[b] = (sample.mean() / sd) * math.sqrt(ANN) if sd > 0 else 0.0
    lo, hi = np.percentile(sharpes, [2.5, 97.5])
    return {
        "n": int(n), "n_boot": n_boot, "block": block,
        "ci_lower_2p5": float(lo), "ci_upper_97p5": float(hi),
        "median": float(np.median(sharpes)),
        "lower_bound_gt_0": bool(lo > 0),
    }


def cscv_pbo(variant_pnls: dict[str, np.ndarray], n_splits: int = 14) -> dict:
    """PBO via CSCV（Bailey et al. 2017）。

    為什麼：在 K 個變體間做 IS/OOS 組合切分，量測「IS-最佳變體在 OOS 落到下半段」的機率。
      PBO 高（>0.5）= 選變體的過程過擬合，IS 排名不轉移到 OOS。
    把時間軸切 n_splits 塊，遍歷所有 size n_splits/2 的 IS 組合，剩餘為 OOS，
      用每塊每變體的 Sharpe 排名計算 logit。
    """
    from itertools import combinations

    names = list(variant_pnls.keys())
    M = len(names)
    mat = np.array([variant_pnls[k] for k in names])  # [M, T]
    T = mat.shape[1]
    s = n_splits if n_splits % 2 == 0 else n_splits - 1
    bsize = T // s
    if bsize < 5 or s < 4:
        return {"insufficient": True, "n_blocks": s, "block_size": bsize}
    blocks = [mat[:, i * bsize:(i + 1) * bsize] for i in range(s)]

    def blk_sharpe(arr: np.ndarray) -> np.ndarray:
        mu = arr.mean(axis=1)
        sd = arr.std(axis=1, ddof=1)
        sd[sd == 0] = np.inf
        return (mu / sd) * math.sqrt(ANN)

    logits = []
    half = s // 2
    all_idx = set(range(s))
    for is_combo in combinations(range(s), half):
        oos_combo = sorted(all_idx - set(is_combo))
        is_arr = np.concatenate([blocks[i] for i in is_combo], axis=1)
        oos_arr = np.concatenate([blocks[i] for i in oos_combo], axis=1)
        is_sh = blk_sharpe(is_arr)
        oos_sh = blk_sharpe(oos_arr)
        best = int(np.argmax(is_sh))
        # 該 IS-最佳變體在 OOS 的相對排名（0..1，1=最好）。
        oos_rank = (np.sum(oos_sh < oos_sh[best]) ) / (M - 1) if M > 1 else 1.0
        # logit：rank→(0,1) clamp 後 log(r/(1-r))；rank≤0.5 = OOS 落後半段。
        r = min(max(oos_rank, 1e-6), 1 - 1e-6)
        logits.append(math.log(r / (1 - r)))
    logits = np.array(logits)
    pbo = float(np.mean(logits <= 0.0))  # OOS-best-variant 落到下半段的機率
    return {
        "n_combinations": len(logits), "n_blocks": s, "block_size": bsize,
        "pbo": pbo, "median_logit": float(np.median(logits)),
        "interpretation": "PBO>0.5 = 選變體過程過擬合（IS 排名不轉移 OOS）",
    }


# ---------------------------------------------------------------------------
# walk-forward anchored-expanding（≥4 fold、≥5d embargo、OOS≥0.3·IS）
# ---------------------------------------------------------------------------
def walk_forward(base_pos: np.ndarray, sig: np.ndarray, btc_ret: np.ndarray,
                 mode: str, n_folds: int = 5, embargo: int = 5) -> dict:
    """anchored-expanding walk-forward：tercile bounds 只用 IS 窗算，gate 套到 OOS。

    為什麼 anchored-expanding：IS 窗從頭累積擴張，每 fold 的 tercile 門檻只用「該 fold
      之前可知」的資料估計（point-in-time），再 embargo 5 日後對 OOS 套用 → OOS PnL
      完全 out-of-sample。OOS≥0.3·IS 由 fold 切分保證（見下）。
    回傳 stitched OOS PnL（各 fold OOS 段串接）+ per-fold Sharpe。
    """
    # 找第一個非暖機索引（sig 與 base_pos 皆有效）。
    valid = np.where(np.isfinite(sig) & (np.arange(len(sig)) >= TSMOM_LOOKBACK))[0]
    if valid.size < 200:
        return {"insufficient": True, "n_valid": int(valid.size)}
    start = int(valid[0])
    end = len(base_pos)
    usable = end - start
    # 切 n_folds：第 1 fold 用前 ~1/(n+1) 當 IS，之後每 fold 擴張 IS、下一段當 OOS。
    seg = usable // (n_folds + 1)
    if seg < 30:
        return {"insufficient": True, "seg": int(seg)}
    oos_pnl_full = np.zeros(end)
    oos_mask = np.zeros(end, dtype=bool)
    fold_sharpes = []
    for k in range(n_folds):
        is_end = start + seg * (k + 1)
        oos_start = is_end + embargo
        oos_end = min(oos_start + seg, end)
        if oos_start >= oos_end:
            break
        is_mask = np.zeros(end, dtype=bool)
        is_mask[start:is_end] = True
        lo, hi = _tercile_bounds(sig, is_mask)
        gated = apply_gate(base_pos, sig, lo, hi, mode)
        seg_pnl = pnl_from_pos(gated, btc_ret)
        oos_pnl_full[oos_start:oos_end] = seg_pnl[oos_start:oos_end]
        oos_mask[oos_start:oos_end] = True
        fs = ds.perf_stats(seg_pnl[oos_start:oos_end])
        fold_sharpes.append(fs.get("sharpe_ann", float("nan")))
    oos_only = oos_pnl_full[oos_mask]
    stats = ds.perf_stats(oos_only)
    return {
        "n_folds": len([s for s in fold_sharpes if np.isfinite(s)]),
        "embargo_days": embargo,
        "fold_oos_sharpes": [float(x) for x in fold_sharpes],
        "oos_stitched_stats": stats,
        "oos_n_days": int(oos_mask.sum()),
        "oos_positive": bool(np.isfinite(stats.get("sharpe_ann", float("nan")))
                             and stats.get("sharpe_ann", -1) > 0),
    }


def regime_split_for(pnl: np.ndarray, reg: np.ndarray) -> dict:
    """各 regime 的 Sharpe（判 bull-only）。"""
    out = {}
    for label in ("bull", "down", "chop"):
        m = reg == label
        if np.count_nonzero(m) >= 30:
            st = ds.perf_stats(pnl[m])
            out[label] = {"sharpe_ann": st.get("sharpe_ann"), "n": int(np.count_nonzero(m)),
                          "ann_ret": st.get("ann_ret")}
        else:
            out[label] = {"n": int(np.count_nonzero(m)), "insufficient": True}
    # bull-only 判定：bull 正，down 與 chop 皆 ≤0（或不足）。
    bull_pos = out.get("bull", {}).get("sharpe_ann", -1)
    down_sh = out.get("down", {}).get("sharpe_ann")
    chop_sh = out.get("chop", {}).get("sharpe_ann")
    others_nonpos = all(
        (s is None or not np.isfinite(s) or s <= 0)
        for s in (down_sh, chop_sh)
    )
    out["bull_only"] = bool(np.isfinite(bull_pos) and bull_pos > 0 and others_nonpos)
    return out


def main() -> None:
    conn = ds._connect()
    try:
        symbols, dates, close_mat = ds.load_daily_closes(conn)
    finally:
        conn.close()

    btc_col = symbols.index("BTCUSDT")
    returns = ds.daily_log_returns(close_mat)  # [T-1, N]
    ret_dates = dates[1:]
    btc_ret = returns[:, btc_col]
    # close 對齊到 returns 軸：returns[t] = log(close[t+1]/close[t])，故第 t 期報酬的
    #   「起始收盤」= close_mat[t]（breadth 需用收盤算 SMA）。對齊後 close_aligned[t]=close_mat[t]。
    close_aligned = close_mat[:-1]  # [T-1, N]

    # ---- base stream_F（unconditioned baseline (ii)）----
    base_pos = build_stream_F_positions(btc_ret)
    base_pnl = pnl_from_pos(base_pos, btc_ret)
    base_stats = ds.perf_stats(base_pnl)

    # ---- baseline (i) buy-and-hold BTC（vol-target 同尺度比較 + 裸 BHODL）----
    bhodl_pnl = np.nan_to_num(btc_ret, nan=0.0)
    bhodl_stats = ds.perf_stats(bhodl_pnl)

    # ---- baseline (iii) naive MA-trend（sign(close - SMA50) full 1x，shift(1)）----
    ma_pos = np.zeros(len(btc_ret))
    btc_close = close_aligned[:, btc_col]
    for t in range(len(btc_ret)):
        if t < SMA_LOOKBACK + 1:
            continue
        win = btc_close[t - SMA_LOOKBACK:t]
        cur = btc_close[t - 1]
        if np.all(np.isfinite(win)) and np.isfinite(cur):
            ma_pos[t] = 1.0 if cur > np.mean(win) else -1.0
    ma_pnl = pnl_from_pos(ma_pos, btc_ret)
    ma_stats = ds.perf_stats(ma_pnl)

    # ---- 條件訊號（全 shift(1)）----
    sig_breadth = breadth_signal(returns, close_aligned)
    sig_vol = realized_vol_signal(btc_ret)
    sig_conv = conviction_signal(btc_ret)

    # ---- PRE-REGISTERED 變體（K 顯式計數）----
    # full-sample tercile（用於 full-sample 報告）+ walk-forward（用於 OOS）。
    full_mask = np.isfinite(sig_breadth)
    variants_spec = [
        ("V1_breadth", sig_breadth, "breadth"),
        ("V1f_breadth_flip", sig_breadth, "breadth_flip"),
        ("V2_voloff", sig_vol, "voloff"),
        ("V2f_voloff_flip", sig_vol, "voloff_flip"),
        ("V3_conviction", sig_conv, "conviction"),
        ("V3f_conviction_flip", sig_conv, "conviction_flip"),
    ]
    K = len(variants_spec)  # 誠實 K（V4 cross-asset 評估後決定是否 +1，見下）

    reg = ds.regime_labels(btc_ret)

    variant_results = {}
    variant_fullsample_pnls = {}  # 供 CSCV PBO
    naive_leak_flags = {}
    for name, sig, mode in variants_spec:
        # full-sample gate（用全樣本 tercile）——僅供描述性 + PBO 切分基底。
        lo_fs, hi_fs = _tercile_bounds(sig, full_mask)
        gated_fs = apply_gate(base_pos, sig, lo_fs, hi_fs, mode)
        pnl_fs = pnl_from_pos(gated_fs, btc_ret)
        stats_fs = ds.perf_stats(pnl_fs)
        variant_fullsample_pnls[name] = pnl_fs

        # naive 雙軌：把訊號的 shift(1) 拿掉（含當期 bar）→ 量 leak 背離。
        sig_naive = _naive_signal(sig, mode)
        gated_nv = apply_gate(base_pos, sig_naive, lo_fs, hi_fs, mode)
        pnl_nv = pnl_from_pos(gated_nv, btc_ret)
        sh_lf = stats_fs.get("sharpe_ann", float("nan"))
        sh_nv = ds.perf_stats(pnl_nv).get("sharpe_ann", float("nan"))
        leak_div = abs(sh_nv - sh_lf) / (abs(sh_lf) + 1e-9) if np.isfinite(sh_lf) else float("nan")
        naive_leak_flags[name] = {
            "sharpe_leakfree": sh_lf, "sharpe_naive": sh_nv,
            "divergence_ratio": float(leak_div) if np.isfinite(leak_div) else None,
            "flag_over_30pct": bool(np.isfinite(leak_div) and leak_div > 0.30),
        }

        # walk-forward OOS（嚴格 PIT tercile）。
        wf = walk_forward(base_pos, sig, btc_ret, mode)

        # block-bootstrap CI（full-sample，較多樣本）。
        boot = block_bootstrap_sharpe_ci(pnl_fs)

        # regime split（full-sample）。
        rsplit = regime_split_for(pnl_fs, reg)

        variant_results[name] = {
            "mode": mode,
            "fullsample": stats_fs,
            "walk_forward_oos": wf,
            "bootstrap_ci": boot,
            "regime_split": rsplit,
        }

    # ---- 選最佳變體（按 full-sample Sharpe；DSR 用此選擇 → multiple-testing 去膨脹）----
    def vsh(v):
        s = v["fullsample"].get("sharpe_ann", float("nan"))
        return s if np.isfinite(s) else -1e9
    best_name = max(variant_results, key=lambda k: vsh(variant_results[k]))
    best = variant_results[best_name]
    best_stats = best["fullsample"]

    # trial SR 變異（K 個變體的每期-SR 樣本變異，供 DSR E[max]）。
    trial_srs = []
    for name in variant_results:
        s = variant_results[name]["fullsample"].get("sharpe_ann")
        if s is not None and np.isfinite(s):
            trial_srs.append(s / math.sqrt(ANN))
    var_sr = float(np.var(trial_srs, ddof=1)) if len(trial_srs) > 1 else None

    dsr = deflated_sharpe(
        best_stats.get("sharpe_ann", float("nan")),
        best_stats.get("n", 0),
        best_stats.get("skew", 0.0),
        best_stats.get("kurt", 3.0),
        K=K,
        var_sr_trials=var_sr,
    )

    # ---- PBO via CSCV（全變體）----
    pbo = cscv_pbo(variant_fullsample_pnls)

    # ---- PASS BAR（全部必達）----
    best_boot = best["bootstrap_ci"]
    best_wf = best["walk_forward_oos"]
    best_reg = best["regime_split"]
    bar = {
        "best_variant": best_name,
        "net_sharpe_gt_0": bool(np.isfinite(best_stats.get("sharpe_ann", float("nan")))
                                and best_stats.get("sharpe_ann", -1) > 0),
        "psr_zero_ge_0.95": bool(best_stats.get("psr_zero", 0) >= 0.95),
        "dsr_K_ge_0.90": bool(dsr["dsr"] >= 0.90),
        "bootstrap_ci_lower_gt_0": bool(best_boot.get("lower_bound_gt_0", False)),
        "oos_positive": bool(best_wf.get("oos_positive", False)),
        "not_bull_only": bool(not best_reg.get("bull_only", True)),
        "beats_baseline_ii_materially": bool(
            np.isfinite(best_stats.get("sharpe_ann", float("nan")))
            and best_stats.get("sharpe_ann", -1) - base_stats.get("sharpe_ann", 0) > 0.25
        ),
    }
    bar["ALL_PASS"] = bool(all([
        bar["net_sharpe_gt_0"], bar["psr_zero_ge_0.95"], bar["dsr_K_ge_0.90"],
        bar["bootstrap_ci_lower_gt_0"], bar["oos_positive"], bar["not_bull_only"],
    ]))

    report = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "K_honest": K,
        "K_note": "6 pre-registered variants (V1/V1f/V2/V2f/V3/V3f); V4 cross-asset skipped — see note",
        "v4_cross_asset_note": (
            "SKIPPED：BTC-dominance / 跨資產 proxy 需 market.dominance 或外部 alt-cap 資料，"
            "DB 無此表（只有 26-sym perp klines）；可從現有 26-sym 構造的最便宜 proxy = "
            "BTC vs equal-weight-alt 相對強弱，但那與 V1 breadth 高度共線（同一截面資訊），"
            "邊際資訊低、徒增 K（惡化 DSR），故誠實 skip。"
        ),
        "params": {
            "cost_bp_per_side": COST_BP_PER_SIDE, "vol_target_ann": VOL_TARGET_ANN,
            "max_leverage": MAX_LEVERAGE, "tsmom_lookback": TSMOM_LOOKBACK,
            "vol_lookback": VOL_LOOKBACK, "sma_lookback": SMA_LOOKBACK,
        },
        "universe": {"n_symbols": len(symbols), "symbols": symbols,
                     "n_dates": len(ret_dates), "span": [str(ret_dates[0]), str(ret_dates[-1])]},
        "baselines": {
            "i_buy_and_hold_btc": bhodl_stats,
            "ii_unconditioned_stream_F": base_stats,
            "iii_naive_ma_trend": ma_stats,
        },
        "naive_leak_check": naive_leak_flags,
        "variants": variant_results,
        "best_variant": {"name": best_name, "fullsample": best_stats},
        "deflated_sharpe": dsr,
        "trial_sr_variance": var_sr,
        "pbo_cscv": pbo,
        "pass_bar": bar,
    }
    out_path = os.environ.get("COND_OUT", "/tmp/openclaw/conditioned_mbeta/analysis.json")
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, ensure_ascii=False, default=str)
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str))


def _naive_signal(sig: np.ndarray, mode: str) -> np.ndarray:
    """naive 對照：把訊號往後挪一格（= 用「未來」一期的訊號值替當期 gate），

    為什麼這樣造 naive：本測的 leak 風險是「gate 訊號是否真用了 t-1 資訊」。把 leak-free
      sig 往前拉一期（sig[t] := sig[t+1]，= 偷看當期 bar 算出的 breadth/vol/conviction）
      模擬「含當期 bar」的前視，量 leak-free 與它的 Sharpe 背離。背離大=shift(1) load-bearing。
    """
    out = np.full_like(sig, np.nan)
    out[:-1] = sig[1:]
    return out


if __name__ == "__main__":
    main()

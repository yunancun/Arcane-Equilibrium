"""funding-tilt 信號生成 — leak-free（funding_ts < open−ε）+ naive 雙軌。

MODULE_NOTE:
  模塊用途：實作協議 §1 的 2 信號族 + §2.1 leak-free PIT 鐵律。**每個信號同時算
    leak-free 版（正式）與 naive leak 版（僅診斷）**，供 harness 並列 Sharpe（協議
    §2.1 強制雙軌：Sharpe(naive)−Sharpe(leak-free)>30% → 強 look-ahead → NO-GO-B）。
  信號族（K=8 = 4 信號變體 × 2 持有期，協議 §1.59）：
    - A cross-sectional funding-tilt tertile long-short（K_A=3）：
      tiltscore = 過去 L 結算已實現 funding 均值，L∈{3,9,21}；每 rebalance 日橫截面
      rank → top tertile（funding 最正）= short -1 / bottom tertile（最負）= long +1。
      market-neutral，剝離 BTC beta，是「funding carry 本身有無 edge」試金石。
    - B time-series funding-extreme（per-symbol，K_B=1）：
      signal = -sign(tiltscore) 當 |tiltscore| ≥ θ（θ = 該 symbol expanding 80th pct，
      **PIT 不含未來**）；否則 flat。賭 funding-extreme mean-revert + 收 carry。
  ★ leak-free 鐵律（協議 §2.1，任一違反=結果作廢）：
    funding 結算時點才已知 → 信號在進場日 t 只能用 ``funding_ts < entry_open_ts − ε``
    的已結算 funding（ε=1 結算間隔，嚴格小於；當日 00:00 結算與開盤同時 → 保守排除）。
    為什麼對 funding 特別重要：funding 與當期價格走勢同期相關（funding 正常因多頭擁擠
    = 價格剛漲）；若洩漏當日結算，等於偷看當日價格方向 → 必虛高。
    naive 版含「進場當日結算」（look-ahead）作對照。
  主要函數：``compute_tiltscore_series`` / ``signal_a_cross_sectional`` /
    ``signal_b_time_series`` / ``count_trial_budget``。
  硬邊界：信號在某日資料不足（過去 < L 結算）→ 該日 tiltscore=NaN（不交易）；
    上市前（survivorship=False）→ signal=0（不入場、不入 rank）；interval_uncertain
    symbol 從 cross-sectional rank 排除（協議 §2.2）。
  依賴：numpy + bisect（標準庫）。import-time 零副作用。
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# 協議 §1 信號變體。
SIGNAL_A_LS = (3, 9, 21)  # cross-sectional tiltscore lookback（結算數），K_A=3
SIGNAL_B_LS = (9,)  # time-series 用單一 L（與 §1.B 的 tiltscore 同義），K_B=1
TIME_SERIES_PCT = 80.0  # time-series extreme 門檻（expanding percentile，§1.B）
# K 預算（協議 §1.59）：(K_A=3 + K_B=1) × 2 持有期 = 8。
TRIAL_BUDGET_K = 8


@dataclass
class TiltScoreSeries:
    """單 symbol 的雙軌 tiltscore 序列（per-day，對齊日期軸）。

    leakfree / naive 同長度（= 日期數 T），不足處為 NaN。
    leakfree[t] = mean(過去 L 結算 funding，funding_ts < open_ts[t] − ε)。
    naive[t]    = mean(過去 L 結算 funding，funding_ts ≤ open_ts[t]，含當日結算)。
    """

    name: str  # 例 "L3" / "L9" / "L21"
    leakfree: np.ndarray
    naive: np.ndarray
    meta: dict = field(default_factory=dict)


@dataclass
class SignalSeries:
    """單一 (信號變體, symbol) 的雙軌 target-weight 序列。

    leakfree / naive 同長度，warmup 未滿處為 NaN。target_weight ∈ {-1, 0, +1}
    （A 的 tertile / B 的 extreme），持有期變體把它轉成實際換倉序列（pnl 模塊）。
    """

    name: str  # 例 "A_L3" / "B_L9"
    family: str  # "A" / "B"
    leakfree: np.ndarray
    naive: np.ndarray
    meta: dict = field(default_factory=dict)


def compute_tiltscore_series(
    funding_ts: list,
    funding_rate: np.ndarray,
    open_ts_utc: np.ndarray,
    lookback_settlements: int,
    *,
    epsilon_settlements: int = 1,
    interval_minutes: Optional[int] = None,
) -> TiltScoreSeries:
    """算單 symbol 的雙軌 tiltscore（協議 §1.A + §2.1 leak-free 鐵律）。

    leak-free：第 t 日的 tiltscore 只用 ``funding_ts < open_ts[t] − ε`` 的最後 L 個結算
    均值（ε = epsilon_settlements × interval；嚴格小於，排除與開盤同時的當日 00:00 結算）。
    naive：用 ``funding_ts ≤ open_ts[t]`` 的最後 L 個（含當日結算，look-ahead 對照）。
    為什麼 ε 用 interval 換算：8h symbol 的 1 結算 = 480min、4h = 240min，ε 須對齊各自
    interval 才能精確排除「與開盤同時的結算」（協議 §2.2 interval 不可假設 8h）。
    funding_ts 須升序（data_loader 已 ORDER BY funding_ts）。
    """
    import datetime as _dt

    t = len(open_ts_utc)
    lf = np.full(t, np.nan, dtype=float)
    nv = np.full(t, np.nan, dtype=float)
    if not funding_ts or lookback_settlements < 1:
        return TiltScoreSeries(name=f"L{lookback_settlements}", leakfree=lf, naive=nv,
                               meta={"lookback": lookback_settlements})
    n_f = len(funding_ts)
    # ε wall-clock：interval 缺則保守用 480min（8h）——但 caller 應傳 interval。
    interval = interval_minutes if interval_minutes else 480
    eps = _dt.timedelta(minutes=epsilon_settlements * interval)
    for i in range(t):
        open_ts = open_ts_utc[i]
        # leak-free 截斷點：funding_ts < open_ts − ε（嚴格）。
        lf_cut = open_ts - eps
        # bisect_left 找第一個 >= lf_cut 的索引 → 之前的全 < lf_cut（嚴格小於）。
        lf_hi = bisect.bisect_left(funding_ts, lf_cut)
        if lf_hi >= lookback_settlements:
            seg = funding_rate[lf_hi - lookback_settlements: lf_hi]
            if np.all(np.isfinite(seg)):
                lf[i] = float(seg.mean())
        # naive 截斷點：funding_ts ≤ open_ts（含當日結算）。bisect_right 找第一個 > open_ts。
        nv_hi = bisect.bisect_right(funding_ts, open_ts)
        if nv_hi >= lookback_settlements:
            seg = funding_rate[nv_hi - lookback_settlements: nv_hi]
            if np.all(np.isfinite(seg)):
                nv[i] = float(seg.mean())
    return TiltScoreSeries(name=f"L{lookback_settlements}", leakfree=lf, naive=nv,
                           meta={"lookback": lookback_settlements, "interval_minutes": interval})


def _rank_one_day_tertile(scores: dict, eligible: list, out_map: dict, t: int) -> None:
    """單日橫截面 tertile 分組（協議 §1.A）。

    top tertile（funding 最正）= short -1；bottom tertile（最負）= long +1；mid = 0。
    為什麼 top=short：funding 最正 = 多頭擁擠/付費持有多單 → 做空收 funding；
    funding 最負 = 空頭擁擠 → 做多收 funding。market-neutral long-short。
    eligible: [(symbol, tiltscore)]（已過 survivorship + interval_certain + finite）。
    """
    if len(eligible) < 3:
        for s, _v in eligible:
            out_map[s][t] = np.nan  # 橫截面不足分 tertile → 不交易
        return
    eligible.sort(key=lambda x: x[1])  # 升序：最負在前
    n_e = len(eligible)
    tert = max(1, n_e // 3)
    bottom = {s for s, _ in eligible[:tert]}  # funding 最負 → long +1
    top = {s for s, _ in eligible[-tert:]}    # funding 最正 → short -1
    for s, _v in eligible:
        if s in top:
            out_map[s][t] = -1.0
        elif s in bottom:
            out_map[s][t] = 1.0
        else:
            out_map[s][t] = 0.0


def signal_a_cross_sectional(
    tiltscore_by_symbol: dict,
    survivorship_by_symbol: dict,
    interval_uncertain_by_symbol: dict,
    lookback: int,
) -> dict:
    """A — cross-sectional funding-tilt tertile long-short（協議 §1.A）。

    每 rebalance 日對橫截面 tiltscore rank → top tertile short / bottom long。
    leak-free / naive 各跑一次（用各自 tiltscore 軌）。
    上市前（survivorship=False）或 interval_uncertain symbol 不入 rank（協議 §2.2/§2.3）。
    回 {symbol: SignalSeries}。
    tiltscore_by_symbol: {symbol: TiltScoreSeries}。
    """
    symbols = list(tiltscore_by_symbol.keys())
    n = len(next(iter(tiltscore_by_symbol.values())).leakfree)
    lf_out = {s: np.full(n, np.nan, dtype=float) for s in symbols}
    nv_out = {s: np.full(n, np.nan, dtype=float) for s in symbols}

    for t in range(n):
        lf_elig = []
        nv_elig = []
        for s in symbols:
            surv = survivorship_by_symbol[s]
            if not surv[t] or interval_uncertain_by_symbol.get(s, False):
                lf_out[s][t] = 0.0  # 上市前/interval 不明：不入場、不入 rank
                nv_out[s][t] = 0.0
                continue
            ts = tiltscore_by_symbol[s]
            lf_v = ts.leakfree[t]
            nv_v = ts.naive[t]
            if np.isfinite(lf_v):
                lf_elig.append((s, lf_v))
            if np.isfinite(nv_v):
                nv_elig.append((s, nv_v))
        _rank_one_day_tertile(tiltscore_by_symbol, lf_elig, lf_out, t)
        _rank_one_day_tertile(tiltscore_by_symbol, nv_elig, nv_out, t)

    return {
        s: SignalSeries(name=f"A_L{lookback}", family="A", leakfree=lf_out[s],
                        naive=nv_out[s], meta={"lookback": lookback})
        for s in symbols
    }


def _expanding_percentile_threshold(abs_scores: np.ndarray, pct: float) -> np.ndarray:
    """expanding PIT percentile 門檻：thr[t] = pctile(|score[0..t-1]|, pct)（不含當日）。

    為什麼 expanding 不含當日（協議 §1.B / §2.1）：θ 是「相對自身過去分布的極端」。用
    全樣本 percentile = look-ahead leak（偷看未來分布）；只用 [0, t-1] 的已實現 |tiltscore|。
    warmup（前面樣本不足）→ thr=NaN（該日不進場）。
    """
    n = len(abs_scores)
    thr = np.full(n, np.nan, dtype=float)
    seen: list = []
    for t in range(n):
        if len(seen) >= 20:  # 至少 20 個先驗樣本才算門檻（避免早期過敏感）
            thr[t] = float(np.percentile(np.asarray(seen), pct))
        v = abs_scores[t]
        if np.isfinite(v):
            seen.append(v)
    return thr


def signal_b_time_series(
    tiltscore: TiltScoreSeries,
    survivorship: np.ndarray,
    interval_uncertain: bool,
    lookback: int,
    *,
    pct: float = TIME_SERIES_PCT,
) -> SignalSeries:
    """B — time-series funding-extreme（per-symbol，協議 §1.B）。

    signal = -sign(tiltscore) 當 |tiltscore| ≥ θ（θ = expanding {pct} percentile，PIT
    不含未來）；否則 flat（0）。方向：funding 極正 → 做空收 funding；極負 → 做多。
    leak-free / naive 各用各自 tiltscore 軌 + 各自 expanding 門檻。
    上市前 / interval_uncertain → flat（不進場）。
    """
    n = len(tiltscore.leakfree)
    lf = np.zeros(n, dtype=float)
    nv = np.zeros(n, dtype=float)
    if interval_uncertain:
        # interval 不明 → 全 flat（協議 §2.2，保守不交易）。
        return SignalSeries(name=f"B_L{lookback}", family="B", leakfree=lf, naive=nv,
                            meta={"lookback": lookback, "pct": pct,
                                  "interval_uncertain_excluded": True})
    lf_thr = _expanding_percentile_threshold(np.abs(tiltscore.leakfree), pct)
    nv_thr = np.abs(tiltscore.naive)  # naive 門檻仍用 expanding（look-ahead 只在 tiltscore 軌）
    nv_thr_expand = _expanding_percentile_threshold(nv_thr, pct)
    for t in range(n):
        if not survivorship[t]:
            continue  # 上市前 flat
        lf_v = tiltscore.leakfree[t]
        if np.isfinite(lf_v) and np.isfinite(lf_thr[t]) and abs(lf_v) >= lf_thr[t]:
            lf[t] = -1.0 if lf_v > 0 else (1.0 if lf_v < 0 else 0.0)
        nv_v = tiltscore.naive[t]
        if np.isfinite(nv_v) and np.isfinite(nv_thr_expand[t]) and abs(nv_v) >= nv_thr_expand[t]:
            nv[t] = -1.0 if nv_v > 0 else (1.0 if nv_v < 0 else 0.0)
    return SignalSeries(name=f"B_L{lookback}", family="B", leakfree=lf, naive=nv,
                        meta={"lookback": lookback, "pct": pct})


def count_trial_budget() -> int:
    """回傳信號變體 × 持有期的 trial 數（誠實計入 DSR 的 K，協議 §1.59）。

    為什麼是函數而非常數：implementer 禁止偷加 grid 不更新 K。本函數從實際枚舉的
    SIGNAL_A_LS / SIGNAL_B_LS 計算 → 若改 grid 但忘了更新 K，harness 自檢會抓到不一致。
    K = (len(A_LS) + len(B_LS)) × 2 持有期。
    """
    signal_variants = len(SIGNAL_A_LS) + len(SIGNAL_B_LS)
    holding_variants = 2
    return signal_variants * holding_variants

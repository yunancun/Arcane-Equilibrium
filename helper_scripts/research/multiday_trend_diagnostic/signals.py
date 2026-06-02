"""4 信號族生成 — leak-free（shift(1)）+ naive（含 current bar）雙軌。

MODULE_NOTE:
  模塊用途：實作協議 §1 的 4 信號族 + §2 leak-free PIT 紀律。**每個信號同時算
    leak-free 版（正式）與 naive leak 版（僅診斷）**，供 harness 並列 Sharpe（協議
    §2.2 強制雙軌：Sharpe(naive)−Sharpe(leak-free)>30% → 強 look-ahead → NO-GO-B）。
  信號族（K=24 = 12 信號變體 × 2 持有期，協議 §1）：
    - A TSMOM 符號：sign(ln(C/C_{-k}))，k∈{20,40,60,90}（K=4）
    - B vol-scaled TSMOM：sign(Σr)×(σ_target/vol)，k∈{30,60}（K=2）
    - C MA crossover：fast SMA vs slow SMA，(fast,slow)∈{(10,30),(20,60),(50,100)}（K=3）
    - D cross-sectional momentum：rank → top/bottom tertile ±1（K=3，market-neutral）
  leak-free 紀律（協議 §2，任一違反=結果作廢）：
    **shift(1) 鐵律** — leak-free 信號在第 t 日只能用 C_{t-1} 及更早收盤。
    程式上：先對收盤序列做 ``shift(1)``（C_prev[t]=C[t-1]），再算 rolling/lag/rank；
    naive 版直接用未 shift 的 C（含 C_t）作對照。
  主要函數：``signal_a`` / ``signal_b`` / ``signal_c`` / ``signal_d_cross_sectional`` /
    ``generate_all_signals``。皆回傳 ``SignalSeries``（leakfree + naive 兩條 array）。
  硬邊界：信號在某日資料不足（warmup 未滿）→ 該日 signal=NaN（不交易），不偽造 0。
    上市前（survivorship mask=False）→ signal=0（不入場、不入 rank）。
  依賴：numpy。import-time 零副作用。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np


@dataclass
class SignalSeries:
    """單一 (信號變體, 持有期變體, symbol) 的雙軌信號序列。

    leakfree / naive 同長度（= 收盤序列長度 T），warmup 未滿處為 NaN。
    target_weight 是「期望持倉方向×大小」；持有期變體把它轉成實際換倉序列。
    """

    name: str  # 例 "A_k20" / "B_k30" / "C_10_30" / "D_k30"
    family: str  # "A" / "B" / "C" / "D"
    leakfree: np.ndarray  # 正式：只用 C_{t-1} 及更早
    naive: np.ndarray  # 診斷：含 C_t（look-ahead）
    meta: dict = field(default_factory=dict)


def _shift1(close: np.ndarray) -> np.ndarray:
    """收盤序列 shift(1)：out[t] = close[t-1]，out[0]=NaN。

    為什麼這是 leak-free 的單一進入點：所有 leak-free 信號都先過此函數，確保第 t 日
    的計算根本拿不到 C_t（協議 §2 shift(1) 鐵律）。naive 版繞過此函數直接用 close。
    """
    out = np.full_like(close, np.nan, dtype=float)
    out[1:] = close[:-1]
    return out


def _rolling_mean_ending_at(series: np.ndarray, window: int) -> np.ndarray:
    """rolling mean，out[t] = mean(series[t-window+1 .. t])（含 series[t]）。

    注意：是否 leak 由「餵進來的 series 是否已 shift(1)」決定，不在此函數。
    leak-free caller 餵 shift1(close)；naive caller 餵 close。
    """
    n = len(series)
    out = np.full(n, np.nan, dtype=float)
    if window <= 0:
        return out
    # 用 cumsum 但須處理 series 內既有的 NaN（shift 產生的 head NaN）。
    for t in range(n):
        lo = t - window + 1
        if lo < 0:
            continue
        seg = series[lo: t + 1]
        if np.any(~np.isfinite(seg)):
            continue
        out[t] = float(seg.mean())
    return out


def _rolling_std_ending_at(series: np.ndarray, window: int) -> np.ndarray:
    """rolling std (ddof=1)，out[t]=std(series[t-window+1..t])。leak 由 caller 餵的 series 決定。"""
    n = len(series)
    out = np.full(n, np.nan, dtype=float)
    if window <= 1:
        return out
    for t in range(n):
        lo = t - window + 1
        if lo < 0:
            continue
        seg = series[lo: t + 1]
        if np.any(~np.isfinite(seg)):
            continue
        out[t] = float(seg.std(ddof=1))
    return out


def _log_return_lag_k(ref_close: np.ndarray, k: int) -> np.ndarray:
    """ln(ref[t] / ref[t-k])。ref 是「信號基準收盤」：leak-free 餵 shift1(close)、naive 餵 close。

    leak-free 下 ref[t]=C_{t-1}, ref[t-k]=C_{t-1-k} → 完全符合協議 signal_A 定義
    sign(ln(C_{t-1}/C_{t-1-k}))。
    """
    n = len(ref_close)
    out = np.full(n, np.nan, dtype=float)
    for t in range(n):
        if t - k < 0:
            continue
        a = ref_close[t]
        b = ref_close[t - k]
        if not (np.isfinite(a) and np.isfinite(b)) or b <= 0 or a <= 0:
            continue
        out[t] = float(np.log(a / b))
    return out


def signal_a(close: np.ndarray, k: int) -> SignalSeries:
    """A — TSMOM 符號：signal = sign(ln(C_{t-1}/C_{t-1-k}))，k∈{20,40,60,90}。"""
    lf = np.sign(_log_return_lag_k(_shift1(close), k))
    nv = np.sign(_log_return_lag_k(close, k))
    # sign(0)=0；保留 NaN（warmup）。
    return SignalSeries(name=f"A_k{k}", family="A", leakfree=lf, naive=nv, meta={"k": k})


def signal_b(close: np.ndarray, k: int, sigma_target: float, vol_window: int = 60) -> SignalSeries:
    """B — vol-scaled TSMOM：sign(Σr_{過去 k})×(σ_target/vol)，k∈{30,60}。

    協議 §1：vol_t=std(r_{t-1..t-60})；σ_target=樣本期 cross-sectional median daily vol
    （由 harness 算好傳入，不 sweep）。leak-free 下 r、vol 都只用 C_{t-1} 及更早。
    """
    lf = _vol_scaled(_shift1(close), k, sigma_target, vol_window)
    nv = _vol_scaled(close, k, sigma_target, vol_window)
    return SignalSeries(name=f"B_k{k}", family="B", leakfree=lf, naive=nv,
                        meta={"k": k, "sigma_target": sigma_target, "vol_window": vol_window})


def _vol_scaled(ref_close: np.ndarray, k: int, sigma_target: float, vol_window: int) -> np.ndarray:
    n = len(ref_close)
    # ref 已是信號基準收盤（leak-free=shift1）。日報酬 r = ln(ref[t]/ref[t-1])。
    r = np.full(n, np.nan, dtype=float)
    for t in range(1, n):
        a, b = ref_close[t], ref_close[t - 1]
        if np.isfinite(a) and np.isfinite(b) and a > 0 and b > 0:
            r[t] = float(np.log(a / b))
    vol = _rolling_std_ending_at(r, vol_window)
    sig_sum = _log_return_lag_k(ref_close, k)  # ln(ref[t]/ref[t-k]) = Σ r over k
    out = np.full(n, np.nan, dtype=float)
    for t in range(n):
        if not (np.isfinite(sig_sum[t]) and np.isfinite(vol[t])) or vol[t] <= 0:
            continue
        out[t] = float(np.sign(sig_sum[t]) * (sigma_target / vol[t]))
    return out


def signal_c(close: np.ndarray, fast_n: int, slow_n: int) -> SignalSeries:
    """C — MA crossover：fast=SMA(過去 fast_n)、slow=SMA(過去 slow_n)，不含 C_t。

    協議 §1：+1 if fast>slow else -1，(fast,slow)∈{(10,30),(20,60),(50,100)}。
    leak-free 下 fast/slow 都用 shift1(close) 的 rolling → 不含 C_t。
    """
    lf = _ma_cross(_shift1(close), fast_n, slow_n)
    nv = _ma_cross(close, fast_n, slow_n)
    return SignalSeries(name=f"C_{fast_n}_{slow_n}", family="C", leakfree=lf, naive=nv,
                        meta={"fast_n": fast_n, "slow_n": slow_n})


def _ma_cross(ref_close: np.ndarray, fast_n: int, slow_n: int) -> np.ndarray:
    fast = _rolling_mean_ending_at(ref_close, fast_n)
    slow = _rolling_mean_ending_at(ref_close, slow_n)
    n = len(ref_close)
    out = np.full(n, np.nan, dtype=float)
    for t in range(n):
        if not (np.isfinite(fast[t]) and np.isfinite(slow[t])):
            continue
        out[t] = 1.0 if fast[t] > slow[t] else -1.0
    return out


def signal_d_cross_sectional(
    close_by_symbol: dict[str, np.ndarray],
    survivorship_by_symbol: dict[str, np.ndarray],
    k: int,
) -> dict[str, SignalSeries]:
    """D — cross-sectional momentum：每日對 mom(i)=ln(C_{t-1}^i/C_{t-1-k}^i) 做橫截面 rank。

    top tertile +1 / bottom tertile -1 / mid 0，market-neutral long-short（協議 §1）。
    leak-free 下 mom 用 shift1 各 symbol 收盤；上市前（survivorship=False）不入 rank。
    回傳每 symbol 的 SignalSeries（同一日各 symbol 信號由橫截面決定）。
    """
    symbols = list(close_by_symbol.keys())
    n = len(next(iter(close_by_symbol.values())))
    # 預算每 symbol 的 leak-free / naive momentum。
    mom_lf = {s: _log_return_lag_k(_shift1(close_by_symbol[s]), k) for s in symbols}
    mom_nv = {s: _log_return_lag_k(close_by_symbol[s], k) for s in symbols}

    lf_out = {s: np.full(n, np.nan, dtype=float) for s in symbols}
    nv_out = {s: np.full(n, np.nan, dtype=float) for s in symbols}

    for t in range(n):
        _rank_one_day(t, symbols, mom_lf, survivorship_by_symbol, lf_out, use_survivorship=True)
        # naive 軌仍尊重 survivorship（look-ahead 只在「含 current bar」這一維度，
        # 不應同時製造上市前交易的第二種 leak，否則無法歸因 naive-vs-leakfree 差異來源）。
        _rank_one_day(t, symbols, mom_nv, survivorship_by_symbol, nv_out, use_survivorship=True)

    return {
        s: SignalSeries(name=f"D_k{k}", family="D", leakfree=lf_out[s], naive=nv_out[s], meta={"k": k})
        for s in symbols
    }


def _rank_one_day(t, symbols, mom_map, survivorship_by_symbol, out_map, use_survivorship: bool) -> None:
    """單日橫截面 tercile 分組（共用於 leak-free / naive）。"""
    eligible = []
    for s in symbols:
        if use_survivorship and not survivorship_by_symbol[s][t]:
            out_map[s][t] = 0.0  # 上市前：不入場、不入 rank
            continue
        m = mom_map[s][t]
        if np.isfinite(m):
            eligible.append((s, m))
    if len(eligible) < 3:
        # 橫截面樣本不足以分 tercile → 該日不交易（NaN），但已標 0 的上市前不覆蓋。
        for s, _m in eligible:
            out_map[s][t] = np.nan
        return
    eligible.sort(key=lambda x: x[1])
    n_e = len(eligible)
    tert = max(1, n_e // 3)
    bottom = {s for s, _ in eligible[:tert]}
    top = {s for s, _ in eligible[-tert:]}
    for s, _m in eligible:
        if s in top:
            out_map[s][t] = 1.0
        elif s in bottom:
            out_map[s][t] = -1.0
        else:
            out_map[s][t] = 0.0


# 協議 §1 的 12 個信號變體（不含 D 的橫截面，D 在 generate_all_signals 特殊處理）。
SIGNAL_A_KS = (20, 40, 60, 90)
SIGNAL_B_KS = (30, 60)
SIGNAL_C_PAIRS = ((10, 30), (20, 60), (50, 100))
SIGNAL_D_KS = (30, 60, 90)
# K 預算（協議 §1）：12 信號變體 × 2 持有期 = 24。
TRIAL_BUDGET_K = 24


def count_trial_budget() -> int:
    """回傳信號變體 × 持有期的 trial 數（誠實計入 DSR 的 K，協議 §1）。

    為什麼是函數而非常數：implementer 禁止偷加 grid 不更新 K。本函數從實際枚舉的
    SIGNAL_*_KS / PAIRS 計算 → 若改 grid 但忘了更新 K，harness 自檢會抓到不一致。
    """
    single_symbol_variants = len(SIGNAL_A_KS) + len(SIGNAL_B_KS) + len(SIGNAL_C_PAIRS)
    x_sectional_variants = len(SIGNAL_D_KS)
    total_signal_variants = single_symbol_variants + x_sectional_variants
    holding_variants = 2
    return total_signal_variants * holding_variants


def generate_single_symbol_signals(close: np.ndarray, sigma_target: float) -> list[SignalSeries]:
    """產出 A/B/C 三族（per-symbol）全部變體（不含 D，D 需橫截面）。"""
    out: list[SignalSeries] = []
    for k in SIGNAL_A_KS:
        out.append(signal_a(close, k))
    for k in SIGNAL_B_KS:
        out.append(signal_b(close, k, sigma_target))
    for fast_n, slow_n in SIGNAL_C_PAIRS:
        out.append(signal_c(close, fast_n, slow_n))
    return out

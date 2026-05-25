"""
MODULE_NOTE
模塊用途：M4 Stage 1 Python 端 cross-correlation 統計（SSOT 對齊 Rust
   `openclaw_core::m4_miner::cross_correlation`）。

不變量：
   - I-1 強制 shift(1) leak-free（rolling_pearson_corr 內部不重做 shift；
     caller 必須先把 feature 視為 shifted series 傳入）
   - I-2 不引 GARCH / Markov-switching / HMM（per ADR-0036）
   - 樣本 < 3 必 None（與 Rust 對齊）
   - 標準差 = 0 必 None（fail-closed）
"""
from __future__ import annotations

import math
from typing import Sequence


def pearson_corr(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Pearson correlation coefficient（pure Python 實裝 SSOT 對齊 Rust）。

    為什麼 manual 不用 scipy.pearsonr：
       - W1-B spec §5.3 三語言對齊要求 1e-4；manual 實裝確保兩語言公式 byte-by-byte 一致
       - scaffold 階段不引 scipy.stats（cron wire-up 後 Sprint 3 才接 production loader）
    """
    if len(x) != len(y) or len(x) < 3:
        return None
    n = len(x)
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    num = 0.0
    den_x = 0.0
    den_y = 0.0
    for xi, yi in zip(x, y):
        dx = xi - mean_x
        dy = yi - mean_y
        num += dx * dy
        den_x += dx * dx
        den_y += dy * dy
    den = math.sqrt(den_x * den_y)
    if den < 1e-15:
        # 標準差 0 fail-closed — 不假設 r=0 也不假設 r=1。
        return None
    r = num / den
    # 數值誤差導致 r 略超 [-1, 1]，clamp 保險。
    return max(-1.0, min(1.0, r))


def spearman_corr(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Spearman rank correlation — Pearson on average ranks。"""
    if len(x) != len(y) or len(x) < 3:
        return None
    rx = _rank(x)
    ry = _rank(y)
    return pearson_corr(rx, ry)


def _rank(values: Sequence[float]) -> list[float]:
    """平均分配 tie 的 rank（average ranking）。"""
    n = len(values)
    indexed = sorted(enumerate(values), key=lambda kv: kv[1])
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and abs(indexed[j][1] - indexed[i][1]) < 1e-12:
            j += 1
        # [i, j) 為 tie group — 平均分配 rank（1-based）。
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def rolling_pearson_corr(
    x: Sequence[float], y: Sequence[float], window: int
) -> list[float | None]:
    """Rolling Pearson correlation — 強制 shift(1) leak-free。

    output[i] 只依賴 x[i-window:i] 與 y[i-window:i]（不含 i 本身）。

    不變量：caller 必先把 feature 視為 shift(1) 後 series 再傳入；本函式不再
    做 shift（避雙重 shift bug）。對齊 Rust m4_miner::cross_correlation::rolling_pearson_corr。
    """
    n = min(len(x), len(y))
    out: list[float | None] = []
    for i in range(n):
        if i < window:
            out.append(None)
        else:
            # i-window:i — 與 Rust 完全對齊：current bar i 不包含。
            xs = x[i - window : i]
            ys = y[i - window : i]
            out.append(pearson_corr(xs, ys))
    return out


def corr_to_p_value(r: float, n: int) -> float:
    """把 Pearson r 轉成雙尾 p-value（t-distribution normal approx）。

    對齊 Rust m4_miner::cross_correlation::corr_to_p_value（同 A&S 7.1.26 erf approx）。
    """
    if n < 3 or abs(1.0 - r * r) < 1e-15:
        return 1.0
    t = r * math.sqrt((n - 2) / (1.0 - r * r))
    z = abs(t)
    phi = 0.5 * (1.0 + _erf_approx(z / math.sqrt(2.0)))
    p = 2.0 * (1.0 - phi)
    return max(0.0, min(1.0, p))


def _erf_approx(x: float) -> float:
    """Abramowitz & Stegun 7.1.26 erf 近似（precision < 1.5e-7）— 對齊 Rust 端。"""
    sign = -1.0 if x < 0 else 1.0
    x = abs(x)
    t = 1.0 / (1.0 + 0.3275911 * x)
    a1 = 0.254829592
    a2 = -0.284496736
    a3 = 1.421413741
    a4 = -1.453152027
    a5 = 1.061405429
    y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
    return sign * y

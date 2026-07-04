"""多重比較與選擇檢定純函數(P2-8)。

MODULE_NOTE:
  模塊用途：把 best-of-K 證據面的統計控制集中成純函數：BH-FDR step-up(候選面)、
    single-sided Student-t p-value(每 cell)、sign-flip selection test(headline 面)、
    E[max] 解析式 sanity 對照。全部只用標準庫，無 scipy/numpy 依賴(lane 需可離線跑)。
  主要函數：one_sided_t_p_value、bh_fdr_pass、sign_flip_selection_p_value、
    expected_max_under_null_bps。
  硬邊界：不做任何 IO/PG/runtime mutation；sign-flip 用固定 seed 的 stdlib random，
    結果可重現(測試用例 11 依賴此)。

QC spec 正本：docs/CCAgentWorkSpace/QC/workspace/reports/2026-07-04--evidence_
methodology_redesign_p12_p27_p28_f7.md §4。
"""

from __future__ import annotations

import math
import random
from typing import Sequence


def _student_t_sf(t: float, df: int) -> float:
    """Student-t 上尾 P(T_df > t)。用不完全 beta 的正則化，標準庫 math 實現。

    為什麼自實現：lane 不引入 scipy;t 分布 CDF 可由 regularized incomplete beta
    I_x(df/2, 1/2) 表達，數值上對本 lane 的 df(2..60)與 |t|(0..10)量級足夠精確。
    """
    if df <= 0:
        return float("nan")
    if not math.isfinite(t):
        return 0.0 if t > 0 else 1.0
    x = df / (df + t * t)
    # I_x(df/2, 1/2) = 雙尾質量;單尾上尾對 t>0 = 0.5*I_x，對 t<0 = 1 - 0.5*I_x。
    ib = _reg_incomplete_beta(x, df / 2.0, 0.5)
    tail = 0.5 * ib
    return tail if t >= 0.0 else 1.0 - tail


def _reg_incomplete_beta(x: float, a: float, b: float) -> float:
    """正則化不完全 beta I_x(a,b)，Lentz 連分數(Numerical Recipes betai)。"""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    ln_beta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(ln_beta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(x, a, b) / a
    return 1.0 - front * _betacf(1.0 - x, b, a) / b


def _betacf(x: float, a: float, b: float) -> float:
    tiny = 1e-30
    qab = a + b
    qap = a + 1.0
    qam = a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def one_sided_t_p_value(mean: float, std: float, n: int) -> float | None:
    """單側 t 檢定 p = P(T_{n-1} > mean/(std/sqrt(n)))。H0: μ=0，H1: μ>0。

    std=0 → mean>0 時 p=0(確定性正)、mean≤0 時 p=1;n<2 → None(無法估變異數)。
    """
    if n < 2:
        return None
    if std is None or not math.isfinite(std):
        return None
    if std <= 0.0:
        return 0.0 if mean > 0.0 else 1.0
    t = mean / (std / math.sqrt(n))
    return _student_t_sf(t, n - 1)


def bh_fdr_pass(p_values: Sequence[float], q: float) -> list[bool]:
    """Benjamini-Hochberg step-up。回傳與輸入同序的通過布林向量。

    通過集 = {i : rank(p_i) ≤ k*}，k* = max{k : p_(k) ≤ k·q/m}。
    cells 間正相依(共同市場因子)下 BH 在 PRDS 仍有效，適配本 lane。
    """
    m = len(p_values)
    if m == 0:
        return []
    indexed = sorted(range(m), key=lambda i: p_values[i])
    k_star = 0
    for rank, idx in enumerate(indexed, start=1):
        if p_values[idx] <= rank * q / m:
            k_star = rank
    passed = [False] * m
    for rank, idx in enumerate(indexed, start=1):
        if rank <= k_star:
            passed[idx] = True
    return passed


def expected_max_under_null_bps(pooled_std: float, k: int, mean_n: float) -> float:
    """E[max_K x̄] ≈ σ·√(2lnK)/√n̄，純 null 之期望最大值(解析 sanity 對照)。"""
    if k <= 1 or mean_n <= 0.0 or pooled_std <= 0.0:
        return 0.0
    return pooled_std * math.sqrt(2.0 * math.log(k)) / math.sqrt(mean_n)


def sign_flip_selection_p_value(
    cell_nets: Sequence[Sequence[float]],
    *,
    b: int = 1000,
    seed: int = 20260704,
) -> dict[str, float | int]:
    """sign-flip selection test(White Reality Check 最簡體)。

    H0:各 cell median net = 0(分布對稱假設)。B 次 within-cell 符號翻轉，重算
    max-over-K 均值統計量;p_selection = #{max*_b ≥ observed_best}/B。
    回傳 {p_selection, observed_best, b, k}。

    分布對稱假設失效模式(crypto 收益偏態)：sign-flip null 略偏，可改 centered
    bootstrap;本實現用 sign-flip(假設更少、實作最簡)並於 packet 記錄方法名。
    """
    cells = [list(c) for c in cell_nets if len(c) > 0]
    k = len(cells)
    if k == 0:
        return {"p_selection": 1.0, "observed_best": 0.0, "b": b, "k": 0}
    observed_best = max(sum(c) / len(c) for c in cells)
    rng = random.Random(seed)
    ge_count = 0
    for _ in range(b):
        max_star = -math.inf
        for c in cells:
            flipped_mean = (
                sum(v if rng.random() < 0.5 else -v for v in c) / len(c)
            )
            if flipped_mean > max_star:
                max_star = flipped_mean
        if max_star >= observed_best:
            ge_count += 1
    # +1 平滑避免 p=0(permutation p 慣例)。
    p_selection = (ge_count + 1) / (b + 1)
    return {
        "p_selection": p_selection,
        "observed_best": observed_best,
        "b": b,
        "k": k,
    }

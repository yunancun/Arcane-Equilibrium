"""
MODULE_NOTE
模塊用途：Cohen's d effect size（per W1-B spec §3.1）。

不變量：
   - pooled std 用 ddof=0（population，對齊 Rust feature_engineering + SQL stddev_pop）
   - |d| < 0.2 或 |d| >= 3.0 → 不算 medium effect（per spec §3.1 pass 條件 0.2-3.0）
"""
from __future__ import annotations

import math
from typing import Sequence


def cohens_d(group_a: Sequence[float], group_b: Sequence[float]) -> float | None:
    """計算 Cohen's d effect size between 兩 group。

    公式：d = (mean_a - mean_b) / pooled_std
    pooled_std = sqrt((var_a + var_b) / 2) — ddof=0

    為什麼 ddof=0：對齊 SQL stddev_pop + Rust m4_miner::feature_engineering
    （W1-B spec §5.3 1e-4 跨語言對齊要求）。

    為什麼 Option：兩 group 任一空、pooled_std=0 → None（fail-closed 不假設 d=0）。
    """
    a = list(group_a)
    b = list(group_b)
    if len(a) < 2 or len(b) < 2:
        return None
    mean_a = sum(a) / len(a)
    mean_b = sum(b) / len(b)
    var_a = sum((x - mean_a) ** 2 for x in a) / len(a)
    var_b = sum((x - mean_b) ** 2 for x in b) / len(b)
    pooled_var = (var_a + var_b) / 2.0
    if pooled_var <= 0.0:
        return None
    pooled_std = math.sqrt(pooled_var)
    if pooled_std < 1e-15:
        return None
    return (mean_a - mean_b) / pooled_std


def passes_cohens_d_gate(d: float | None) -> bool:
    """Cohen's d 是否通過 W1-B spec §3.1 pass 條件：0.2 <= |d| < 3.0。

    為什麼上限 3.0：|d| >= 3.0 通常表示「effect too good to be true」、
    suggestive of data leakage 或 fixture artifact（per spec §3.1）。
    """
    if d is None:
        return False
    return 0.2 <= abs(d) < 3.0

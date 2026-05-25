"""
MODULE_NOTE
模塊用途：M4 Stage 1 feature engineering validator — shift(1) leak-free 三語言
   驗證（SQL / pandas / polars 或 pure Python equivalent）。

per W1-B spec §2.1.2 + §4.3 leakage scan：
   - SQL pattern：window function ROWS BETWEEN N PRECEDING AND 1 PRECEDING（含 current 排除）
   - pandas pattern：close.shift(1).rolling(N).mean()
   - polars pattern：col("close").shift(lit(1)).rolling_mean(...)
   - pure Python：見 algorithms/cross_correlation.py rolling_pearson_corr

不變量：
   - I-1 強制：output[i] 必只依賴 values[i-window:i]（不含 values[i] 本身）
   - SQL window function 必含 `ROWS BETWEEN N PRECEDING AND 1 PRECEDING`
     不可 `ROWS BETWEEN N PRECEDING AND CURRENT ROW`（leak）
   - pandas 必 `.shift(1).rolling(N)` 不可 `.rolling(N)` 直接套
   - polars 必 `.shift(lit(1)).rolling_mean(...)` 不可省略 shift
"""
from __future__ import annotations

import math
import re
from typing import Sequence


# 為什麼這些 SQL pattern 必須 reject：
#   `ROWS BETWEEN N PRECEDING AND CURRENT ROW` 含 current bar → look-ahead bias
#   （per memory feedback_indicator_lookahead_bias 2026-04-24 P1-11 F3 RETRACT）
LEAKY_SQL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"ROWS\s+BETWEEN\s+\w+\s+PRECEDING\s+AND\s+CURRENT\s+ROW", re.IGNORECASE),
    re.compile(r"OVER\s*\(\s*PARTITION.*ORDER.*ROWS.*CURRENT\s+ROW", re.IGNORECASE | re.DOTALL),
)

# Pandas / Python 端 leak pattern：
#   `.rolling(N)` 沒先 `.shift(1)` → leak
LEAKY_PANDAS_PATTERNS: tuple[re.Pattern[str], ...] = (
    # 注意：本 regex 只能 catch 「沒有 .shift(1) 即用 .rolling(N)」這類 obvious case；
    # 真實 review 必由 E2 cold review 看 caller context（per W1-B spec §9.1 Review-1 grep）
    re.compile(r"(?<!shift\(1\)\.)rolling\(\d+\)\.(mean|std|sum|corr)\b"),
)


def is_leaky_sql(sql: str) -> bool:
    """判斷 SQL 是否含 leak pattern（含 current bar）。

    為什麼回 bool：本函式只做 binary verdict — 真正的 review 由 E2 cold grep。
    """
    return any(p.search(sql) for p in LEAKY_SQL_PATTERNS)


def is_leakfree_sql(sql: str) -> bool:
    """判斷 SQL 是否含 `ROWS BETWEEN N PRECEDING AND 1 PRECEDING` 這類 leak-free pattern。

    為什麼這條 pattern：W1-B spec §2.1.2 SQL 範式 — 排除 current bar 必由 `AND 1 PRECEDING`
    結尾（不是 `AND CURRENT ROW`）。
    """
    leakfree_pattern = re.compile(
        r"ROWS\s+BETWEEN\s+\w+\s+PRECEDING\s+AND\s+1\s+PRECEDING", re.IGNORECASE
    )
    return bool(leakfree_pattern.search(sql))


def is_leaky_pandas(code: str) -> bool:
    """粗略偵測 pandas 是否含 leak pattern。

    為什麼 quick check：W1-B spec §9.1 Review-1 grep 是權威；本函式為 caller 提供
    pre-commit hook / fixture 自驗用，不取代 E2 cold review。
    """
    return any(p.search(code) for p in LEAKY_PANDAS_PATTERNS)


def validate_shift1_pattern(
    feature_values: Sequence[float],
    forward_return_bps: Sequence[float],
    window: int,
    diff_threshold: float = 0.1,
) -> dict:
    """並列計算 leak vs leak-free 兩版 correlation，判斷是否 leak suspected。

    對齊 Rust m4_miner::feature_engineering::validate_leak_free_pattern。

    Returns dict 含：
       - leak_corr: 含 current bar 的 correlation
       - clean_corr: shift(1) 後的 correlation
       - diff: |leak_corr - clean_corr|
       - leak_suspected: diff > diff_threshold
       - insufficient_sample: window+2 不夠樣本
    """
    from helper_scripts.m4.algorithms.cross_correlation import pearson_corr

    n = min(len(feature_values), len(forward_return_bps))
    if n < window + 2:
        return {
            "leak_corr": 0.0,
            "clean_corr": 0.0,
            "diff": 0.0,
            "leak_suspected": False,
            "insufficient_sample": True,
        }
    leak_slice_f = feature_values[n - window : n]
    leak_slice_r = forward_return_bps[n - window : n]
    clean_slice_f = feature_values[n - window - 1 : n - 1]
    clean_slice_r = forward_return_bps[n - window - 1 : n - 1]
    leak_corr = pearson_corr(leak_slice_f, leak_slice_r) or 0.0
    clean_corr = pearson_corr(clean_slice_f, clean_slice_r) or 0.0
    diff = abs(leak_corr - clean_corr)
    return {
        "leak_corr": leak_corr,
        "clean_corr": clean_corr,
        "diff": diff,
        "leak_suspected": diff > diff_threshold,
        "insufficient_sample": False,
    }


def shift1_rolling_mean_pure_python(
    values: Sequence[float], window: int
) -> list[float | None]:
    """Pure Python leak-free shift(1) rolling mean。

    為什麼提供：W1-B spec §5.3 三語言對齊 — Python pandas 為 SSOT，但
    1e-4 對齊驗用 pure Python 實裝排除 pandas implementation 細節（如 ddof 預設）干擾。

    output[i] 只依賴 values[i-window:i]（不含 values[i] 本身）。
    """
    if window == 0:
        return [None] * len(values)
    out: list[float | None] = []
    for i in range(len(values)):
        if i < window:
            out.append(None)
        else:
            slice_ = values[i - window : i]
            out.append(sum(slice_) / window)
    return out


def shift1_rolling_std_pure_python(
    values: Sequence[float], window: int
) -> list[float | None]:
    """Pure Python leak-free shift(1) rolling population std（ddof=0）。

    為什麼 ddof=0：對齊 SQL stddev_pop + Rust m4_miner::feature_engineering。
    """
    if window == 0:
        return [None] * len(values)
    out: list[float | None] = []
    for i in range(len(values)):
        if i < window:
            out.append(None)
        else:
            slice_ = list(values[i - window : i])
            mean = sum(slice_) / window
            var = sum((v - mean) ** 2 for v in slice_) / window
            out.append(math.sqrt(var))
    return out

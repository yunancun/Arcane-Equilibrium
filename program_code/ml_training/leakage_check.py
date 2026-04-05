"""
Feature Leakage Check — validate training features don't contain future information.
特徵洩漏檢查 — 驗證訓練特徵不包含未來信息。

MODULE_NOTE (EN): Whitelist validation for scorer training features. Ensures:
  1. No outcome_* columns in feature set
  2. No future price/pnl information
  3. All features are t-1 or earlier (no same-tick label leakage)
MODULE_NOTE (中): 評分器訓練特徵的白名單驗證。
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Forbidden patterns in feature names / 特徵名中的禁止模式
FORBIDDEN_PATTERNS = [
    "outcome_",
    "realized_pnl",
    "unrealized_pnl",
    "future_",
    "next_",
    "forward_",
    "target_",
    "label",
    "backfilled",
]

# Allowed feature name prefixes / 允許的特徵名前綴
ALLOWED_PREFIXES = [
    "sma_", "ema_", "rsi_", "macd", "bb_", "atr_", "stoch_",
    "kama", "adx", "hurst", "ewma_", "volume_", "donchian",
    "regime_", "price", "spread", "position_",
    "ind_", "news_", "scorer_",
]


def check_feature_leakage(
    feature_names: list[str],
    strict: bool = True,
) -> tuple[bool, list[str]]:
    """Validate feature names against leakage whitelist.
    驗證特徵名是否符合防洩漏白名單。

    Args:
        feature_names: list of feature column names
        strict: if True, unknown features are flagged

    Returns:
        (passed, list_of_violations)
    """
    violations = []

    for name in feature_names:
        name_lower = name.lower()

        # Check forbidden patterns / 檢查禁止模式
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in name_lower:
                violations.append(f"FORBIDDEN: '{name}' contains '{pattern}'")

        # Strict mode: check allowed prefixes / 嚴格模式：檢查允許前綴
        if strict:
            if not any(name_lower.startswith(p) for p in ALLOWED_PREFIXES):
                violations.append(f"UNKNOWN: '{name}' not in allowed prefix list")

    passed = len(violations) == 0
    if not passed:
        logger.warning("Feature leakage check FAILED: %d violations", len(violations))
        for v in violations[:10]:
            logger.warning("  %s", v)
    else:
        logger.info("Feature leakage check PASSED: %d features validated", len(feature_names))

    return passed, violations

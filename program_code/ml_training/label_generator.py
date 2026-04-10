"""
Label Generator — compute net_pnl/ATR training labels from trading.fills.
標籤生成器 — 從 trading.fills 計算 net_pnl/ATR 訓練標籤。

MODULE_NOTE (EN): Generates regression labels for LightGBM Scorer:
  y = clip(net_pnl / max(ATR, ATR_FLOOR), -Y_MAX, Y_MAX)
  With winsorization at 1st/99th percentile and MAD-based outlier detection.
MODULE_NOTE (中): 為 LightGBM 評分器生成回歸標籤。
"""

from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# Default ATR floor percentile (rolling 30d q=0.05)
# 默認 ATR 下限分位數
DEFAULT_ATR_FLOOR_QUANTILE = 0.05
DEFAULT_ATR_FLOOR_WINDOW_DAYS = 30

# Winsorization limits / 縮尾限制
Y_MAX = 5.0  # clip labels at ±5 ATR units


@dataclass
class LabelConfig:
    """Configuration for label generation / 標籤生成配置"""
    atr_floor_quantile: float = DEFAULT_ATR_FLOOR_QUANTILE
    atr_floor_window_days: int = DEFAULT_ATR_FLOOR_WINDOW_DAYS
    y_max: float = Y_MAX
    winsorize_pct: float = 0.01  # 1st/99th percentile


def compute_atr_floor(atr_values: np.ndarray, quantile: float = 0.05) -> float:
    """Compute dynamic ATR floor as rolling quantile.
    計算動態 ATR 下限。"""
    if len(atr_values) == 0:
        return 0.001  # absolute minimum
    positive = atr_values[atr_values > 0]
    if len(positive) == 0:
        return 0.001  # all zeros — use absolute minimum / 全為零，用絕對最小值
    floor = float(np.quantile(positive, quantile))
    return max(floor, 0.001)


def generate_labels(
    net_pnl: np.ndarray,
    atr: np.ndarray,
    config: Optional[LabelConfig] = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Generate ATR-normalized labels with winsorization.
    生成 ATR 歸一化標籤。

    Returns (labels, is_extreme) where is_extreme flags MAD outliers.
    """
    cfg = config or LabelConfig()
    atr_floor = compute_atr_floor(atr, cfg.atr_floor_quantile)

    # y = net_pnl / max(ATR, floor)
    safe_atr = np.maximum(atr, atr_floor)
    raw_labels = net_pnl / safe_atr

    # Winsorize at percentiles / 在分位數處縮尾
    low = np.percentile(raw_labels, cfg.winsorize_pct * 100)
    high = np.percentile(raw_labels, (1 - cfg.winsorize_pct) * 100)
    labels = np.clip(raw_labels, low, high)

    # Final clip at ±Y_MAX / 最終裁剪
    labels = np.clip(labels, -cfg.y_max, cfg.y_max)

    # MAD-based outlier detection / 基於 MAD 的異常檢測
    median = np.median(labels)
    mad = np.median(np.abs(labels - median))
    threshold = 3.5 * mad if mad > 0 else cfg.y_max
    is_extreme = np.abs(labels - median) > threshold

    logger.info(
        "Labels generated: n=%d, mean=%.4f, std=%.4f, extremes=%d, atr_floor=%.6f",
        len(labels), labels.mean(), labels.std(), is_extreme.sum(), atr_floor,
    )

    return labels, is_extreme

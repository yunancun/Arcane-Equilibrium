"""
Label Generator — compute net_pnl/ATR training labels from trading.fills.
標籤生成器 — 從 trading.fills 計算 net_pnl/ATR 訓練標籤。

MODULE_NOTE (中):
  - generate_labels：為 LightGBM Scorer 生成回歸標籤
      y = clip(net_pnl / max(ATR, ATR_FLOOR), -Y_MAX, Y_MAX)
      含 1/99 分位 winsorize + MAD-based 異常檢測。
  - compute_class_weights（W-AUDIT-4b-M3 + P0-MIT-LABEL-CLOSE-TAG-1，2026-05-09）：
      為 ML training pool 計算 sample_weight，補正 governance reject 寫負樣本後
      reject:fill = 70:1 imbalance 對 classifier 的 dominance 偏差。
      上界 1/170 = PA spec 70× ratio + 100× 安全餘量；fill row → 1.0。
      與 V084 SQL UDF `learning.mlde_sample_weight` 邏輯對齊（DB / Python 雙寫）。

Spec：docs/CCAgentWorkSpace/PA/workspace/reports/
      2026-05-09--full_dispatch_engineering_plan.md §2.5 B-M3
"""

from __future__ import annotations

import logging
import numpy as np
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)

# W-AUDIT-4b-M3：governance reject 負樣本的 sample_weight。
# REJECTED_GOVERNANCE_TAG：reject path 寫入的 close_tag 字串
# REJECT_SAMPLE_WEIGHT：1/170 = 70× imbalance + 100× safety margin
# 與 sql/migrations/V084 UDF `learning.mlde_sample_weight` 完全一致。
REJECTED_GOVERNANCE_TAG = "rejected_governance"
REJECT_SAMPLE_WEIGHT = 1.0 / 170.0
DEFAULT_SAMPLE_WEIGHT = 1.0

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


def compute_class_weights(close_tags: np.ndarray) -> np.ndarray:
    """W-AUDIT-4b-M3：根據 close_tag 計算 sample_weight。

    governance reject 路徑寫入 'rejected_governance' close_tag 後，ML training
    pool reject:fill ≈ 70:1，未加權直接訓會讓 classifier trivially predict
    reject 而拿高準確率（虛假信號）。本函數對 reject row 加 1/170 weight，
    使 weighted reject:fill 比近 1:0.41，loss landscape 平衡。

    與 sql/migrations/V084 UDF `learning.mlde_sample_weight` 邏輯完全一致：
        - 'rejected_governance' → REJECT_SAMPLE_WEIGHT = 1/170
        - 其他（含 NULL / 'orphan_close:%' / 'adopted_close:%' /
                'shadow_fill:%' / 'abandoned:no_close_fill' / 一般 fill row）
          → DEFAULT_SAMPLE_WEIGHT = 1.0

    Args:
        close_tags: 1-D array-like，每行的 label_close_tag（可含 None / NaN）

    Returns:
        1-D ndarray same length as `close_tags`，dtype float64

    範例 / Example:
        >>> tags = np.array(['rejected_governance', 'rejected_governance', None,
        ...                  'orphan_close:reverse', ''])
        >>> w = compute_class_weights(tags)
        >>> w[0] == 1.0/170.0 and w[2] == 1.0
        True
    """
    n = len(close_tags)
    weights = np.full(n, DEFAULT_SAMPLE_WEIGHT, dtype=np.float64)

    # numpy 對 None / NaN 的 == 比較不可靠 → 逐元素檢查
    for i, tag in enumerate(close_tags):
        if tag is None:
            continue
        try:
            tag_str = str(tag)
        except Exception:
            continue
        if tag_str == REJECTED_GOVERNANCE_TAG:
            weights[i] = REJECT_SAMPLE_WEIGHT

    n_reject = int(np.sum(weights == REJECT_SAMPLE_WEIGHT))
    n_default = n - n_reject
    if n > 0:
        logger.info(
            "compute_class_weights: n=%d, reject=%d (w=%.6f), default=%d (w=%.4f)",
            n, n_reject, REJECT_SAMPLE_WEIGHT, n_default, DEFAULT_SAMPLE_WEIGHT,
        )

    return weights

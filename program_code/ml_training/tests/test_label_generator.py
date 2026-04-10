"""Tests for label_generator module / 標籤生成器測試"""

import numpy as np
import pytest

from program_code.ml_training.label_generator import (
    LabelConfig,
    compute_atr_floor,
    generate_labels,
)


def test_compute_atr_floor_basic():
    atr = np.array([0.01, 0.02, 0.03, 0.04, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0])
    floor = compute_atr_floor(atr, quantile=0.05)
    assert floor > 0
    assert floor < 0.05  # 5th percentile of the data


def test_compute_atr_floor_empty():
    floor = compute_atr_floor(np.array([]), quantile=0.05)
    assert floor == 0.001


def test_generate_labels_basic():
    np.random.seed(42)
    pnl = np.random.randn(100) * 100
    atr = np.abs(np.random.randn(100)) * 50 + 10

    labels, is_extreme = generate_labels(pnl, atr)

    assert len(labels) == 100
    assert len(is_extreme) == 100
    assert labels.max() <= 5.0  # Y_MAX
    assert labels.min() >= -5.0


def test_generate_labels_extreme_detection():
    # MAD outlier detection needs a spread of non-zero values for mad > 0.
    # Normal body: 90 samples drawn from tight range; outliers at extremes.
    # MAD 異常檢測需要非零值分佈使 mad > 0。
    rng = np.random.default_rng(42)
    body = rng.normal(0, 1, 90) * 10  # pnl ≈ N(0, 10)
    outliers = np.array([500, -500, 800, -800, 1000, -1000, 1500, -1500, 2000, -2000])
    pnl = np.concatenate([body, outliers])
    atr = np.ones(100) * 10  # labels = pnl / 10

    labels, is_extreme = generate_labels(pnl, atr)

    assert is_extreme.sum() > 0  # should flag the outlier values


def test_generate_labels_zero_atr_uses_floor():
    pnl = np.ones(10) * 50
    atr = np.zeros(10)  # all zero ATR

    labels, _ = generate_labels(pnl, atr)

    # With floor=0.001, labels = 50/0.001 = 50000 → clipped to Y_MAX=5.0
    assert labels.max() <= 5.0

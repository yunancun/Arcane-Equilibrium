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


def test_generate_labels_winsorize_bounds_train_only():
    """外傳 winsorize_bounds 杜絕 cross-fold 分位洩漏（冷審計 R2 MIT[LOW]）。

    驗證：傳入 train-fold 算好的 (low, high) 時，clip 用的是外傳門檻而非本陣列
    （含 test-fold）分位。以一個有極端值的陣列，外傳一個窄 bounds → 極端值被
    夾到外傳門檻，而非用整窗分位（後者會被極端值抬高門檻，夾不掉）。
    """
    # ATR=1 使 raw_labels == pnl；主體在 [-2, 2]，含兩個極端 ±100。
    pnl = np.concatenate([np.linspace(-2.0, 2.0, 98), np.array([100.0, -100.0])])
    atr = np.ones(100)

    # train-fold 只看主體，算得窄門檻（此處顯式給 [-2, 2]）。
    labels_bounded, _ = generate_labels(pnl, atr, winsorize_bounds=(-2.0, 2.0))
    # 外傳門檻應把極端值夾進 [-2, 2]（再經 ±Y_MAX 不變）。
    assert labels_bounded.max() <= 2.0 + 1e-9
    assert labels_bounded.min() >= -2.0 - 1e-9

    # 對照：不傳 bounds 時用本陣列 1/99 分位，極端 ±100 會抬高門檻，
    # 夾後最大值明顯 > 外傳窄門檻的結果（證明兩條路徑確實不同）。
    labels_leaky, _ = generate_labels(pnl, atr)
    assert labels_leaky.max() > labels_bounded.max()


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

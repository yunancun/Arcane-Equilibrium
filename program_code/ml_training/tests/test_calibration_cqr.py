"""Tests for EDGE-P3-1 CQR calibration additions in calibration.py.
calibration.py 中 EDGE-P3-1 CQR 校準新增函數的測試。"""
from __future__ import annotations

import math

import numpy as np
import pytest

from program_code.ml_training.calibration import (
    apply_cqr_to_quantile,
    evaluate_cqr_coverage,
    fit_cqr_offset,
    fit_cqr_trio,
    fit_isotonic_fallback,
)


def test_fit_cqr_offset_empty_returns_zero():
    assert fit_cqr_offset(np.array([]), np.array([]), alpha=0.1) == 0.0


def test_fit_cqr_offset_matches_manual_finite_sample_quantile():
    # residuals = y - p = [-4, -3, -2, -1, 0, 1, 2, 3, 4] (n=9, α=0.1)
    # Finite-sample position = ceil(0.1 * 10) / 9 = 1/9 ≈ 0.111
    # Expected: small-α quantile = ~interpolated between -4 and -3.
    # 殘差已排序；α=0.1 取有限樣本位置 ceil(0.1*10)/9 ≈ 0.111 分位。
    y = np.array([0, 1, 2, 3, 4, 5, 6, 7, 8], dtype=np.float64)
    p = np.array([4, 4, 4, 4, 4, 4, 4, 4, 4], dtype=np.float64)
    offset = fit_cqr_offset(y, p, alpha=0.1)
    # residuals = y - p sorted = [-4, -3, -2, -1, 0, 1, 2, 3, 4]
    residuals = np.sort(y - p)
    expected_level = math.ceil(0.1 * (9 + 1)) / 9
    expected = float(np.quantile(residuals, expected_level))
    assert offset == pytest.approx(expected)


def test_fit_cqr_offset_alpha_monotone():
    # Monotone α → offset (higher α gives higher quantile of residuals).
    # α 遞增 → offset 遞增（較高 α = 殘差更高分位）。
    rng = np.random.default_rng(0)
    y = rng.standard_normal(500)
    p = np.zeros(500)
    d10 = fit_cqr_offset(y, p, alpha=0.1)
    d50 = fit_cqr_offset(y, p, alpha=0.5)
    d90 = fit_cqr_offset(y, p, alpha=0.9)
    assert d10 < d50 < d90


def test_apply_cqr_to_quantile_shifts_predictions():
    p = np.array([1.0, 2.0, 3.0])
    shifted = apply_cqr_to_quantile(p, 0.5)
    assert np.allclose(shifted, [1.5, 2.5, 3.5])


def test_fit_cqr_trio_returns_three_keys():
    y = np.array([0, 1, 2, 3, 4], dtype=np.float64)
    q10 = np.zeros(5)
    q50 = np.ones(5) * 2
    q90 = np.ones(5) * 4
    offsets = fit_cqr_trio(y, q10, q50, q90)
    assert set(offsets.keys()) == {"q10", "q50", "q90"}


def test_evaluate_cqr_coverage_closes_gap():
    """Pre-calibration coverage drifts; CQR offset brings empirical ≈ alpha.
    校準前 coverage 偏離；CQR 後實證接近 nominal α。"""
    rng = np.random.default_rng(42)
    n = 2000
    # Noisy y; q10 initial guess way off (too high → coverage >> 10%).
    # 噪音 y；q10 初始估計偏高 → coverage 遠 >10%。
    y = rng.standard_normal(n)
    q10 = np.full(n, 0.5)  # way above true 10th percentile
    q50 = np.zeros(n)
    q90 = np.full(n, -0.5)  # way below true 90th percentile (inverted)
    offsets = fit_cqr_trio(y, q10, q50, q90)
    post = evaluate_cqr_coverage(y, q10, q50, q90, offsets)
    # Each quantile's calibrated empirical should be within 5pp of nominal.
    # 校準後每分位實證應在 nominal 5pp 內。
    for key, (empirical, err_pp) in post.items():
        assert err_pp < 5.0, f"{key} gap too wide: empirical={empirical} err={err_pp}"


def test_evaluate_cqr_coverage_empty_input():
    offsets = {"q10": 0.0, "q50": 0.0, "q90": 0.0}
    post = evaluate_cqr_coverage(
        np.array([]), np.array([]), np.array([]), np.array([]), offsets,
    )
    # Per-quantile empirical = 0 on empty; error = 0 (no data to evaluate).
    # 空輸入時每分位實證 = 0；錯誤 = 0。
    for key in ("q10", "q50", "q90"):
        assert post[key] == (0.0, 0.0)


def test_fit_isotonic_fallback_returns_monotone_mapping():
    sklearn = pytest.importorskip("sklearn")
    # Noisy but monotone relationship → isotonic should extract trend.
    # 噪音但單調關係 → isotonic 應能萃取趨勢。
    rng = np.random.default_rng(7)
    x = np.linspace(0, 10, 200)
    y = x + rng.standard_normal(200) * 0.5
    ir = fit_isotonic_fallback(y, x)
    assert ir is not None
    preds = ir.predict(x)
    assert len(preds) == 200
    # Monotone: sorted x → non-decreasing preds.
    # 單調性：x 排序後 preds 單調不減。
    order = np.argsort(x)
    sorted_preds = preds[order]
    diffs = np.diff(sorted_preds)
    assert (diffs >= -1e-9).all()


def test_fit_isotonic_fallback_empty_returns_none():
    pytest.importorskip("sklearn")
    assert fit_isotonic_fallback(np.array([]), np.array([])) is None

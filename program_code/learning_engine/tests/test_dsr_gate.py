"""Tests for dsr_gate (REF-20 Wave 6 P4-Q1).

dsr_gate 測試（REF-20 Wave 6 P4-Q1）。

Coverage / 覆蓋:
  1. K=1 → DSR == PSR(0) (no selection bias). /
     K=1 → DSR == PSR(0)（無選擇偏差）。
  2. K=10 → DSR < observed PSR (DSR strictly tighter than PSR for K>1). /
     K=10 → DSR < observed PSR（K>1 時 DSR 嚴於 PSR）。
  3. DSR > 0.95 → 'promote' verdict. /
     DSR > 0.95 → 'promote' 判決。
  4. DSR < 0.95 → 'block' or 'borderline' verdict. /
     DSR < 0.95 → 'block' 或 'borderline' 判決。
"""

from __future__ import annotations

import math

import pytest

from program_code.learning_engine.dsr_gate import (
    BORDERLINE_LOWER,
    DEFAULT_DSR_THRESHOLD,
    DsrGate,
    DsrResult,
    compute_dsr,
)


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: K=1 → DSR == PSR(0)
# ─────────────────────────────────────────────────────────────────────────────


def test_k1_dsr_equals_psr_at_zero():
    """K=1 (single trial, no selection) → DSR must equal PSR(0).

    K=1（單一 trial，無選擇）→ DSR 必等於 PSR(0)。

    Reason / 理由: With K=1, there is no selection bias. The expected max
    Sharpe across 1 trial under Gaussian null is 0 (E[Z] = 0). Therefore
    DSR = PSR at threshold 0 = PSR(0).

    K=1 時無選擇偏差。1 個 trial 在高斯虛無下之 E[max SR] = E[Z] = 0。
    因此 DSR = PSR 在閾值 0 = PSR(0)。
    """
    gate = DsrGate(threshold=0.95)
    result = gate.compute_dsr(
        observed_sharpe=2.0,
        n_trials=1,
        n_observations=500,
    )

    assert isinstance(result, DsrResult)
    assert result.n_trials_K == 1
    assert result.observed_sharpe == 2.0
    # K=1: trials_max_sharpe should be 0 (Gaussian E[Z] = 0).
    # K=1：trials_max_sharpe 應為 0。
    assert math.isclose(result.trials_max_sharpe, 0.0, abs_tol=1e-9)
    # DSR == PSR(0) → both compute against threshold 0.
    # DSR == PSR(0) → 兩者均針對閾值 0 計算。
    assert math.isclose(
        result.deflated_sharpe,
        result.psr_at_threshold,
        rel_tol=1e-9,
        abs_tol=1e-9,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: K=10 → DSR < PSR (selection bias makes DSR tighter)
# ─────────────────────────────────────────────────────────────────────────────


def test_k10_dsr_strictly_less_than_psr():
    """K=10 → DSR < PSR(0) due to selection bias correction.

    K=10 → DSR < PSR(0)（選擇偏差修正）。

    Reason / 理由: With K=10 trials and Gaussian null, E[max SR_k] ≈ 1.539 σ.
    PSR(SR>0) tests against threshold 0; DSR tests against threshold 1.539.
    Higher threshold → lower probability → DSR < PSR.

    K=10 trials 在高斯虛無下 E[max SR_k] ≈ 1.539 σ。
    PSR(SR>0) 針對閾值 0；DSR 針對閾值 1.539。
    閾值越高 → 機率越低 → DSR < PSR。
    """
    # Choose moderate observed Sharpe + T so that PSR(0) ≠ saturated 1.0.
    # 選溫和的 observed Sharpe + T 使 PSR(0) 不 saturate 到 1.0，
    # 否則 PSR(0) 與 DSR 兩者都會被 floor 到 1.0 而失去比較意義。
    gate = DsrGate(threshold=0.95)
    result = gate.compute_dsr(
        observed_sharpe=0.3,
        n_trials=10,
        n_observations=50,
    )

    assert result.n_trials_K == 10
    # E[max SR_k] for K=10 should be ~1.539 (Bailey-LdP Eq.8 reference value).
    # K=10 之 E[max SR_k] 應約 1.539（Bailey-LdP 第 8 式參考值）。
    assert 1.4 < result.trials_max_sharpe < 1.7, (
        f"trials_max_sharpe={result.trials_max_sharpe} outside expected ~1.539 range"
    )
    # DSR strictly less than PSR(0) due to selection bias correction.
    # DSR 嚴格小於 PSR(0)（選擇偏差修正）。
    assert result.deflated_sharpe < result.psr_at_threshold, (
        f"deflated_sharpe={result.deflated_sharpe} not < psr_at_threshold="
        f"{result.psr_at_threshold} for K=10"
    )
    # Sanity / 健全性：PSR(0) should not be saturated to 1.0 here.
    assert result.psr_at_threshold < 1.0 - 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: DSR > 0.95 → 'promote' verdict
# ─────────────────────────────────────────────────────────────────────────────


def test_dsr_above_threshold_promote():
    """High observed Sharpe + few trials → DSR > 0.95 → 'promote'.

    高觀察 Sharpe + 少 trials → DSR > 0.95 → 'promote'。

    Setup / 設定: observed Sharpe = 4.0 (very strong), K=2 (minimal selection),
    T=1000 (high power). DSR should comfortably exceed 0.95.

    設定：觀察 Sharpe = 4.0（很強），K=2（最小選擇），T=1000（高 power）。
    DSR 應穩超 0.95。
    """
    gate = DsrGate(threshold=0.95)
    result = gate.compute_dsr(
        observed_sharpe=4.0,
        n_trials=2,
        n_observations=1000,
    )

    # Assert DSR > threshold (promotion candidate).
    # 斷言 DSR > 閾值（升級候選）。
    assert result.passes_threshold, (
        f"deflated_sharpe={result.deflated_sharpe} did not exceed "
        f"threshold={DEFAULT_DSR_THRESHOLD}"
    )
    assert result.deflated_sharpe > 0.95

    verdict = gate.gate(result)
    assert verdict == "promote", f"expected 'promote', got '{verdict}'"


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: DSR < 0.95 → 'block' verdict
# ─────────────────────────────────────────────────────────────────────────────


def test_dsr_below_threshold_block():
    """Low observed Sharpe + many trials → DSR < 0.95 → 'block' / 'borderline'.

    低觀察 Sharpe + 多 trials → DSR < 0.95 → 'block' / 'borderline'。

    Setup / 設定: observed Sharpe = 1.5 (weak after K=20 trials, high
    selection bias), T=200. E[max SR_k] for K=20 ≈ 1.87 — OBSERVED < trials_max
    so DSR ≈ 0.

    設定：觀察 Sharpe = 1.5（K=20 trials 後弱，高選擇偏差），T=200。
    K=20 之 E[max SR_k] ≈ 1.87 — OBSERVED < trials_max 所以 DSR ≈ 0。
    """
    gate = DsrGate(threshold=0.95)
    result = gate.compute_dsr(
        observed_sharpe=1.5,
        n_trials=20,
        n_observations=200,
    )

    # DSR should be well below 0.95.
    # DSR 應遠低於 0.95。
    assert not result.passes_threshold
    assert result.deflated_sharpe < 0.95

    verdict = gate.gate(result)
    assert verdict in ("block", "borderline"), (
        f"expected 'block' or 'borderline', got '{verdict}'"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Edge cases / 邊緣案例（防禦性 + 不變量）
# ─────────────────────────────────────────────────────────────────────────────


def test_invalid_threshold_raises():
    """Threshold outside (0, 1) must raise ValueError.

    閾值 (0, 1) 外必拋 ValueError。
    """
    with pytest.raises(ValueError):
        DsrGate(threshold=1.5)
    with pytest.raises(ValueError):
        DsrGate(threshold=-0.1)


def test_invalid_n_trials_raises():
    """n_trials < 1 must raise.

    n_trials < 1 必拋。
    """
    gate = DsrGate()
    with pytest.raises(ValueError):
        gate.compute_dsr(observed_sharpe=2.0, n_trials=0, n_observations=100)


def test_invalid_n_observations_raises():
    """n_observations < 2 must raise (sqrt(T-1) requires T>=2).

    n_observations < 2 必拋（sqrt(T-1) 要求 T>=2）。
    """
    gate = DsrGate()
    with pytest.raises(ValueError):
        gate.compute_dsr(observed_sharpe=2.0, n_trials=5, n_observations=1)


def test_explicit_trial_sharpes_overrides_theoretical():
    """When trial_sharpes provided, sample max replaces theoretical E[max].

    當 trial_sharpes 提供時，樣本最大取代理論 E[max]。
    """
    gate = DsrGate()
    # Trial sharpes with explicit max = 3.0 — much higher than theoretical
    # E[max SR_k] for K=5 (~1.16). Our deflation should reflect this.
    # 明確 max = 3.0 — 遠高於 K=5 之理論 E[max SR_k] (~1.16)。
    result = gate.compute_dsr(
        observed_sharpe=2.0,
        n_trials=5,
        n_observations=500,
        trial_sharpes=[0.5, 1.0, 1.5, 2.0, 3.0],
    )

    # trials_max_sharpe should be the sample max (3.0), not the
    # theoretical E[max] (~1.16).
    # trials_max_sharpe 應為樣本最大 (3.0) 而非理論 E[max]。
    assert math.isclose(result.trials_max_sharpe, 3.0, abs_tol=1e-9)
    # observed (2.0) < trials_max (3.0) → DSR should be < 0.5
    # observed (2.0) < trials_max (3.0) → DSR 應 < 0.5
    assert result.deflated_sharpe < 0.5


def test_module_shortcut_matches_class():
    """Module-level compute_dsr matches DsrGate(...).compute_dsr.

    模組級 compute_dsr 須等同 DsrGate(...).compute_dsr。
    """
    a = compute_dsr(observed_sharpe=2.5, n_trials=10, n_observations=500)
    b = DsrGate(threshold=DEFAULT_DSR_THRESHOLD).compute_dsr(
        observed_sharpe=2.5, n_trials=10, n_observations=500,
    )
    assert math.isclose(a.deflated_sharpe, b.deflated_sharpe, abs_tol=1e-12)
    assert a.n_trials_K == b.n_trials_K
    assert a.passes_threshold == b.passes_threshold


def test_borderline_band_returned():
    """DSR ∈ [0.90, 0.95) should return 'borderline'.

    DSR ∈ [0.90, 0.95) 應回 'borderline'。
    """
    # Manually craft a DsrResult in borderline band to test gate() logic.
    # 手動構造 borderline 帶內的 DsrResult 以測試 gate() 邏輯。
    gate = DsrGate(threshold=0.95)
    borderline_result = DsrResult(
        observed_sharpe=2.0,
        deflated_sharpe=0.92,
        n_trials_K=5,
        psr_at_threshold=0.99,
        trials_max_sharpe=1.16,
        passes_threshold=False,
    )
    assert gate.gate(borderline_result) == "borderline"

    block_result = DsrResult(
        observed_sharpe=2.0,
        deflated_sharpe=0.50,
        n_trials_K=5,
        psr_at_threshold=0.95,
        trials_max_sharpe=1.16,
        passes_threshold=False,
    )
    assert gate.gate(block_result) == "block"

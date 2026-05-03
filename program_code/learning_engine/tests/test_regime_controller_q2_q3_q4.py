"""
Tests for regime_controller RGM-Q2 / Q3 / Q4 (REF-20 Wave 5 Batch 5B-D).
regime_controller RGM-Q2 / Q3 / Q4 測試（REF-20 Wave 5 Batch 5B-D）。

Coverage / 覆蓋（PA dispatch 12 cases + extras）:

RGM-Q2 (CUSUM):
1. No break (clean Gaussian noise) → state_after='active'.
2. CUSUM ≥ 3σ → break_detected=True; state_after='break'.
3. State transition (single-cell sequential active → break).
4. Multi-cell isolation (per-cell key independence).

RGM-Q3 (Kupiec POF):
1. n>=250 + observed≈expected → accept H0.
2. n>=250 + violations greatly above expected → reject H0.
3. n<250 → sufficient_sample=False; refuse test.
4. Cross-cell sample independence (different cells, different samples).

RGM-Q4 (PSR(0)):
1. 3 PSR all <0.95 → refit_trigger=True.
2. 1 window above 0.95 → no refit.
3. governance audit row written (callback invoked, pm_alert_emitted=True).
4. Window roll-over (most recent 3×250 from longer history).

Test invocation / 測試呼叫:
    pytest srv/program_code/learning_engine/tests/test_regime_controller_q2_q3_q4.py -v

References / 參考:
- docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md §8.4
- docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4
  R20-RGM-Q2/Q3/Q4
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Tuple

import numpy as np
import pytest

from program_code.learning_engine.regime_controller import (
    CUSUM_SIGMA_THRESHOLD,
    CusumResult,
    KUPIEC_MIN_N,
    KUPIEC_P_VALUE_THRESHOLD,
    KupiecResult,
    PSR_NUM_WINDOWS,
    PSR_THRESHOLD,
    PSR_WINDOW_SIZE,
    PsrResult,
    RegimeController,
)


# ---------------------------------------------------------------------------
# Fixtures / 共享測試夾具
# ---------------------------------------------------------------------------

CELL_KEY = "grid_trading::BTCUSDT::long"
OTHER_CELL = "bb_breakout::ETHUSDT::short"


@pytest.fixture
def controller() -> RegimeController:
    """Default-threshold controller (V3 §8.4 spec values).

    預設閾值 controller（V3 §8.4 規格值）。
    """
    return RegimeController()


# ===========================================================================
# RGM-Q2: CUSUM ±3σ break detection / RGM-Q2 CUSUM ±3σ break 偵測
# ===========================================================================


def test_cusum_no_break_on_iid_gaussian(
    controller: RegimeController,
) -> None:
    """Clean Gaussian iid → CUSUM stays <3σ → state_after='active'.

    純高斯 iid → CUSUM 維持 < 3σ → state_after='active'。
    """
    rng = np.random.default_rng(42)
    returns = rng.normal(0.0, 1.0, size=200).tolist()
    result = controller.check_cusum(CELL_KEY, returns)
    assert isinstance(result, CusumResult)
    assert result.cell_key == CELL_KEY
    assert result.n == 200
    assert result.threshold == CUSUM_SIGMA_THRESHOLD
    assert result.threshold == 3.0
    assert result.cusum_value < 3.0  # below threshold
    assert result.break_detected is False
    assert result.state_after == "active"
    # Reasons populated bilingually.
    # 雙語 reason 已填。
    assert "active" in result.reason_en or "active" in result.reason_zh
    assert "active" in result.reason_zh or "active" in result.reason_en


def test_cusum_detects_break_on_drift_shift(
    controller: RegimeController,
) -> None:
    """Strong drift (mean-shift series) → CUSUM ≥3σ → break detected.

    強 drift（mean-shift 序列）→ CUSUM ≥3σ → break。
    """
    rng = np.random.default_rng(7)
    # First half centred at 0, second half at +5σ shift.
    # The implementation removes the SAMPLE mean, but the cumulative
    # walk between the two halves still produces a >3σ CUSUM swing.
    # 前半中心 0，後半 +5σ；樣本 mean 被移除，但跨兩半累積路徑仍
    # 產生 >3σ CUSUM 擺動。
    half = rng.normal(0.0, 1.0, size=200)
    drift = rng.normal(5.0, 1.0, size=200)
    returns = np.concatenate([half, drift]).tolist()
    result = controller.check_cusum(CELL_KEY, returns)
    assert result.cusum_value > 3.0  # exceeds threshold
    assert result.break_detected is True
    assert result.state_after == "break"
    assert "break" in result.reason_en
    assert "凍結" in result.reason_zh or "break" in result.reason_zh


def test_cusum_state_transition_active_then_break(
    controller: RegimeController,
) -> None:
    """Sequential calls move state active → break with the same controller.

    順序呼叫使狀態從 active → break（同一 controller 實例）。
    """
    rng = np.random.default_rng(13)
    # First call: clean iid → active.
    iid = rng.normal(0.0, 1.0, size=300).tolist()
    r1 = controller.check_cusum(CELL_KEY, iid)
    assert r1.state_after == "active"

    # Second call: drift-shifted series on same cell → break.
    drift = (
        list(rng.normal(0.0, 1.0, size=200))
        + list(rng.normal(8.0, 1.0, size=200))
    )
    r2 = controller.check_cusum(CELL_KEY, drift)
    assert r2.state_after == "break"
    assert r2.break_detected is True


def test_cusum_multi_cell_isolation(
    controller: RegimeController,
) -> None:
    """Different cell_key → independent statistics, no cross-contamination.

    不同 cell_key → 獨立統計，無交叉汙染。
    """
    rng = np.random.default_rng(21)
    # Cell A: clean iid → active.
    iid_a = rng.normal(0.0, 1.0, size=200).tolist()
    r_a = controller.check_cusum(CELL_KEY, iid_a)
    assert r_a.state_after == "active"
    assert r_a.cell_key == CELL_KEY

    # Cell B: drift-shifted → break.
    drift_b = (
        list(rng.normal(0.0, 1.0, size=200))
        + list(rng.normal(6.0, 1.0, size=200))
    )
    r_b = controller.check_cusum(OTHER_CELL, drift_b)
    assert r_b.state_after == "break"
    assert r_b.cell_key == OTHER_CELL

    # Cell A still active when re-checked.
    # cell A 重檢仍 active。
    r_a2 = controller.check_cusum(CELL_KEY, iid_a)
    assert r_a2.state_after == "active"


def test_cusum_validates_inputs(controller: RegimeController) -> None:
    """Invalid inputs raise ValueError.

    無效輸入 raise ValueError。
    """
    with pytest.raises(ValueError, match="non-empty string"):
        controller.check_cusum("", [1.0] * 100)
    with pytest.raises(ValueError, match="must not be None"):
        controller.check_cusum(CELL_KEY, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="empty"):
        controller.check_cusum(CELL_KEY, [])
    with pytest.raises(ValueError, match="insufficient sample"):
        controller.check_cusum(CELL_KEY, [1.0] * 5)  # default min_n=30


def test_cusum_constant_series_returns_zero(
    controller: RegimeController,
) -> None:
    """Constant series → std≈0 (≤1e-12 guard) → cusum_value=0 → no break.

    常數序列 → std≈0（≤1e-12 guard）→ cusum_value=0 → 無 break。
    """
    result = controller.check_cusum(CELL_KEY, [3.14] * 100)
    # Sample std ≈ 0 (within FP tolerance; ddof=1 over identical floats).
    # 樣本 std ≈ 0（FP 容差；ddof=1 同 float）。
    assert result.sample_std < 1e-10
    # cusum_value clamped to 0 by std<=1e-12 guard.
    # std<=1e-12 guard 將 cusum_value 夾為 0。
    assert result.cusum_value == 0.0
    assert result.break_detected is False


# ===========================================================================
# RGM-Q3: Kupiec POF n>=250 / Kupiec POF n>=250
# ===========================================================================


def test_kupiec_accept_h0_when_observed_matches_expected(
    controller: RegimeController,
) -> None:
    """n=250 + observed ~ expected (5%) → accept H0.

    n=250 + observed ≈ expected (5%) → accept H0。
    """
    n = 250
    coverage_alpha = 0.05
    expected = int(n * coverage_alpha)  # 12.5 → 12 or 13
    # Construct an observed sequence with exactly 13 breaches.
    # 構造剛好 13 violation 的序列。
    breaches = [True] * 13 + [False] * (n - 13)
    result = controller.check_kupiec_pof(CELL_KEY, breaches, coverage_alpha)
    assert isinstance(result, KupiecResult)
    assert result.cell_key == CELL_KEY
    assert result.n == n
    assert result.observed_violations == 13
    assert math.isclose(result.expected_violations, expected, rel_tol=0.1)
    assert result.coverage_alpha == coverage_alpha
    assert result.sufficient_sample is True
    assert result.reject_h0 is False  # close to expected → accept
    assert result.p_value > KUPIEC_P_VALUE_THRESHOLD


def test_kupiec_reject_h0_when_violations_far_above_expected(
    controller: RegimeController,
) -> None:
    """n=250 + 50 violations (vs expected ~12.5) → reject H0.

    n=250 + 50 違反（預期 ~12.5）→ reject H0。
    """
    n = 250
    breaches = [True] * 50 + [False] * (n - 50)
    result = controller.check_kupiec_pof(CELL_KEY, breaches, 0.05)
    assert result.n == n
    assert result.observed_violations == 50
    assert result.sufficient_sample is True
    assert result.reject_h0 is True
    assert result.p_value < KUPIEC_P_VALUE_THRESHOLD
    assert result.lr_test_statistic > 3.84  # chi² 1df 5% critical = 3.84


def test_kupiec_n_below_250_skipped(
    controller: RegimeController,
) -> None:
    """n=200 < 250 → sufficient_sample=False; reject_h0=False; nan p_value.

    n=200 < 250 → sufficient_sample=False；reject_h0=False；p_value 為 NaN。
    """
    breaches = [True] * 10 + [False] * 190  # n=200
    result = controller.check_kupiec_pof(CELL_KEY, breaches, 0.05)
    assert result.n == 200
    assert result.sufficient_sample is False
    assert result.reject_h0 is False  # never reject when refused
    assert math.isnan(result.p_value)
    assert "skipped" in result.reason_en
    assert "skipped" in result.reason_zh


def test_kupiec_cross_cell_sample_independence(
    controller: RegimeController,
) -> None:
    """Different cells have independent breach samples.

    不同 cell 有獨立違反樣本。
    """
    n = 250
    # Cell A: 13 breaches (~ 5% expected) → accept.
    breaches_a = [True] * 13 + [False] * (n - 13)
    r_a = controller.check_kupiec_pof(CELL_KEY, breaches_a, 0.05)
    assert r_a.cell_key == CELL_KEY
    assert r_a.observed_violations == 13
    assert r_a.reject_h0 is False

    # Cell B: 60 breaches → reject (independent sample, NOT borrowed).
    # cell B：60 違反 → reject（獨立樣本，禁從 A 借）。
    breaches_b = [True] * 60 + [False] * (n - 60)
    r_b = controller.check_kupiec_pof(OTHER_CELL, breaches_b, 0.05)
    assert r_b.cell_key == OTHER_CELL
    assert r_b.observed_violations == 60
    assert r_b.reject_h0 is True

    # Cell A is unaffected by cell B's reject.
    # cell A 不受 cell B reject 影響。
    r_a2 = controller.check_kupiec_pof(CELL_KEY, breaches_a, 0.05)
    assert r_a2.reject_h0 is False


def test_kupiec_validates_inputs(controller: RegimeController) -> None:
    """Invalid inputs raise ValueError.

    無效輸入 raise ValueError。
    """
    with pytest.raises(ValueError, match="non-empty string"):
        controller.check_kupiec_pof("", [True] * 250, 0.05)
    with pytest.raises(ValueError, match="coverage_alpha"):
        controller.check_kupiec_pof(CELL_KEY, [True] * 250, 0.0)
    with pytest.raises(ValueError, match="coverage_alpha"):
        controller.check_kupiec_pof(CELL_KEY, [True] * 250, 1.0)
    with pytest.raises(ValueError, match="must not be None"):
        controller.check_kupiec_pof(CELL_KEY, None, 0.05)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="dtype must be bool or int"):
        controller.check_kupiec_pof(CELL_KEY, [1.5, 0.5] * 200, 0.05)


def test_kupiec_accepts_int_zero_one(controller: RegimeController) -> None:
    """Int sequence with values strictly 0/1 is accepted.

    嚴格 0/1 整數序列被接受。
    """
    n = 250
    breaches = [1] * 13 + [0] * (n - 13)
    result = controller.check_kupiec_pof(CELL_KEY, breaches, 0.05)
    assert result.observed_violations == 13
    assert result.sufficient_sample is True


# ===========================================================================
# RGM-Q4: PSR(0) across 3×250 windows / PSR(0) across 3×250 窗
# ===========================================================================


def _make_returns_with_target_psr(
    n: int,
    sharpe: float,
    seed: int = 42,
) -> np.ndarray:
    """Generate returns with approximate target Sharpe.

    產生大致目標 Sharpe 的 returns。
    """
    rng = np.random.default_rng(seed)
    base = rng.normal(0.0, 1.0, size=n)
    # Adjust mean to hit target Sharpe = mean / std.
    # 調 mean 命中目標 Sharpe = mean / std。
    base_std = np.std(base, ddof=1)
    target_mean = sharpe * base_std
    base = base - np.mean(base) + target_mean
    return base


def test_psr_3windows_refit_when_all_below_threshold(
    controller: RegimeController,
) -> None:
    """3 windows × 250 with low Sharpe → all PSR<0.95 → refit_trigger=True.

    3×250 低 Sharpe → 全 PSR<0.95 → refit_trigger=True。
    """
    # Sharpe near 0 over each window → PSR(0) ≈ 0.5 across all 3.
    # 每窗 Sharpe 接近 0 → PSR(0) ≈ 0.5。
    returns = _make_returns_with_target_psr(750, sharpe=0.0, seed=1).tolist()
    result = controller.check_psr_3windows(CELL_KEY, returns)
    assert isinstance(result, PsrResult)
    assert result.cell_key == CELL_KEY
    assert result.n_total == 750
    assert result.window_size == PSR_WINDOW_SIZE
    assert result.num_windows == PSR_NUM_WINDOWS
    assert len(result.window_psrs) == 3
    assert all(p < PSR_THRESHOLD for p in result.window_psrs)
    assert result.all_below_threshold is True
    assert result.refit_trigger is True
    assert result.sufficient_sample is True
    # No callback configured → pm_alert_emitted=False even when triggered.
    # 無 callback → 即使 trigger pm_alert_emitted=False。
    assert result.pm_alert_emitted is False


def test_psr_3windows_no_refit_when_one_window_above_threshold(
    controller: RegimeController,
) -> None:
    """1 window with high Sharpe → at least one PSR≥0.95 → no refit.

    1 窗高 Sharpe → 至少一 PSR≥0.95 → 不 refit。
    """
    # Window 0 + 1: low Sharpe (PSR < 0.95).
    # Window 2 (newest): high Sharpe (PSR ≥ 0.95).
    rng = np.random.default_rng(99)
    low_w = list(rng.normal(0.0, 1.0, size=500))  # 2 windows × 250
    # High-Sharpe window: 250 with Sharpe ~3.
    # 高 Sharpe 窗：250、Sharpe ~3。
    high_w = _make_returns_with_target_psr(250, sharpe=3.0, seed=2).tolist()
    returns = low_w + high_w
    result = controller.check_psr_3windows(CELL_KEY, returns)
    assert result.n_total == 750
    # Last window has high PSR.
    # 最新窗高 PSR。
    assert result.window_psrs[-1] >= PSR_THRESHOLD
    assert result.all_below_threshold is False
    assert result.refit_trigger is False


def test_psr_3windows_emits_pm_alert_when_callback_configured() -> None:
    """Callback invoked + pm_alert_emitted=True when refit triggered.

    refit trigger 時 callback 被呼叫 + pm_alert_emitted=True。
    """
    captured: List[Tuple[str, Dict[str, Any]]] = []

    def cb(cell_key: str, payload: Dict[str, Any]) -> None:
        captured.append((cell_key, dict(payload)))

    ctrl = RegimeController(pm_alert_callback=cb)
    returns = _make_returns_with_target_psr(750, sharpe=0.0, seed=3).tolist()
    result = ctrl.check_psr_3windows(CELL_KEY, returns)
    assert result.refit_trigger is True
    assert result.pm_alert_emitted is True
    assert len(captured) == 1
    cell_key, payload = captured[0]
    assert cell_key == CELL_KEY
    assert payload["cell_key"] == CELL_KEY
    assert payload["threshold"] == PSR_THRESHOLD
    assert payload["v3_section"] == "8.4#4"
    assert len(payload["window_psrs"]) == 3


def test_psr_3windows_window_rollover_uses_most_recent(
    controller: RegimeController,
) -> None:
    """History longer than 3×250 → uses tail 3×250.

    歷史長於 3×250 → 用尾 3×250。
    """
    # 1500 returns: first 750 high Sharpe, last 750 low Sharpe.
    # 1500 returns：前 750 高 Sharpe、後 750 低 Sharpe。
    high = _make_returns_with_target_psr(750, sharpe=3.0, seed=10).tolist()
    low = _make_returns_with_target_psr(750, sharpe=0.0, seed=11).tolist()
    returns = high + low
    result = controller.check_psr_3windows(CELL_KEY, returns)
    assert result.n_total == 1500
    # Tail-based: should pick up low-Sharpe → all_below.
    # 取尾：應抓低 Sharpe → all_below。
    assert all(p < PSR_THRESHOLD for p in result.window_psrs)
    assert result.refit_trigger is True


def test_psr_3windows_insufficient_sample(
    controller: RegimeController,
) -> None:
    """n_total < 3×250 → sufficient_sample=False, refit_trigger=False.

    n_total < 3×250 → sufficient_sample=False、refit_trigger=False。
    """
    returns = list(range(500))  # < 750
    result = controller.check_psr_3windows(CELL_KEY, returns)
    assert result.n_total == 500
    assert result.sufficient_sample is False
    assert result.refit_trigger is False
    assert result.all_below_threshold is False
    # All window PSRs are NaN placeholders.
    # 所有窗 PSR 為 NaN placeholder。
    assert all(math.isnan(p) for p in result.window_psrs)
    assert "skipped" in result.reason_en


def test_psr_3windows_callback_exception_does_not_propagate() -> None:
    """Callback raising should not propagate; pm_alert_emitted=False.

    callback raise 不傳出；pm_alert_emitted=False。
    """
    def bad_cb(cell_key: str, payload: Dict[str, Any]) -> None:
        raise RuntimeError("simulated callback failure")

    ctrl = RegimeController(pm_alert_callback=bad_cb)
    returns = _make_returns_with_target_psr(750, sharpe=0.0, seed=5).tolist()
    result = ctrl.check_psr_3windows(CELL_KEY, returns)
    assert result.refit_trigger is True
    # pm_alert_emitted=False because callback raised.
    # callback raise → pm_alert_emitted=False。
    assert result.pm_alert_emitted is False


def test_psr_3windows_validates_cell_key(
    controller: RegimeController,
) -> None:
    """Invalid cell_key raises ValueError.

    無效 cell_key raise ValueError。
    """
    with pytest.raises(ValueError, match="non-empty string"):
        controller.check_psr_3windows("", [0.0] * 750)
    with pytest.raises(ValueError, match="must not be None"):
        controller.check_psr_3windows(CELL_KEY, None)  # type: ignore[arg-type]


# ===========================================================================
# Constructor / properties — Q2/Q3/Q4 widening
# 建構子 / 屬性 — Q2/Q3/Q4 widen
# ===========================================================================


def test_constructor_defaults_match_v3_spec() -> None:
    """Default ctor exposes V3 §8.4 spec thresholds via properties.

    預設 ctor 經 properties 暴露 V3 §8.4 規格閾值。
    """
    ctrl = RegimeController()
    assert ctrl.warmup_threshold == 500
    assert ctrl.cusum_sigma_threshold == 3.0
    assert ctrl.kupiec_min_n == 250
    assert ctrl.psr_threshold == 0.95
    assert ctrl.psr_window_size == 250
    assert ctrl.psr_num_windows == 3


def test_constructor_rejects_invalid_q2_q3_q4_args() -> None:
    """Invalid Q2/Q3/Q4 ctor args raise ValueError.

    無效 Q2/Q3/Q4 ctor args raise ValueError。
    """
    with pytest.raises(ValueError, match="cusum_sigma_threshold"):
        RegimeController(cusum_sigma_threshold=0.0)
    with pytest.raises(ValueError, match="cusum_sigma_threshold"):
        RegimeController(cusum_sigma_threshold=-1.0)
    with pytest.raises(ValueError, match="kupiec_min_n"):
        RegimeController(kupiec_min_n=0)
    with pytest.raises(ValueError, match="kupiec_min_n"):
        RegimeController(kupiec_min_n=-50)
    with pytest.raises(ValueError, match="kupiec_p_value_threshold"):
        RegimeController(kupiec_p_value_threshold=0.0)
    with pytest.raises(ValueError, match="kupiec_p_value_threshold"):
        RegimeController(kupiec_p_value_threshold=1.0)
    with pytest.raises(ValueError, match="psr_threshold"):
        RegimeController(psr_threshold=0.0)
    with pytest.raises(ValueError, match="psr_threshold"):
        RegimeController(psr_threshold=1.0)
    with pytest.raises(ValueError, match="psr_window_size"):
        RegimeController(psr_window_size=0)
    with pytest.raises(ValueError, match="psr_num_windows"):
        RegimeController(psr_num_windows=0)
    with pytest.raises(ValueError, match="pm_alert_callback"):
        RegimeController(pm_alert_callback="not_callable")  # type: ignore[arg-type]


def test_module_constants_match_v3_spec() -> None:
    """Module-level constants align with V3 §8.4.

    模組級常數對齊 V3 §8.4。
    """
    assert CUSUM_SIGMA_THRESHOLD == 3.0
    assert KUPIEC_MIN_N == 250
    assert KUPIEC_P_VALUE_THRESHOLD == 0.05
    assert PSR_THRESHOLD == 0.95
    assert PSR_WINDOW_SIZE == 250
    assert PSR_NUM_WINDOWS == 3

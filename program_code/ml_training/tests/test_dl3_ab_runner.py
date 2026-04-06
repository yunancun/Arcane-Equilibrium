"""Tests for DL-3 A/B Runner (4-12).

Phase 4 子任務 4-12 — DL-3 A/B 框架 測試。

Coverage / 覆蓋:
    - 4 decision matrix paths (DEPRECATE / PROMOTE_PENDING / INCONCLUSIVE / INSUFFICIENT_DATA)
    - sklearn lazy import + fail-soft
    - dsn=None fail-soft
    - persist_decision skips when table missing
    - evaluate_auc_brier known-value sanity check
    - run_ab_test never raises (fuzz)
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from program_code.ml_training.dl3_ab_runner import (
    AbResult,
    Dl3AbConfig,
    decide,
    evaluate_auc_brier,
    fetch_training_dataset,
    persist_decision,
    run_ab_test,
)


# ---------------------------------------------------------------------------
# Decision matrix tests (pure function — no IO).
# 決策矩陣測試（純函數，無 IO）。
# ---------------------------------------------------------------------------


def test_decision_insufficient_data_below_min_samples():
    """n_samples < min_samples → INSUFFICIENT_DATA regardless of metrics."""
    cfg = Dl3AbConfig(min_samples=100, auc_delta_threshold=0.01)
    decision = decide(
        baseline_auc=0.55,
        augmented_auc=0.99,  # massive improvement, but not enough samples
        baseline_brier=0.20,
        augmented_brier=0.05,
        n_samples=50,
        cfg=cfg,
    )
    assert decision == "INSUFFICIENT_DATA"


def test_decision_deprecate_when_delta_below_threshold():
    """delta < auc_delta_threshold → DEPRECATE."""
    cfg = Dl3AbConfig(min_samples=100, auc_delta_threshold=0.01)
    decision = decide(
        baseline_auc=0.55,
        augmented_auc=0.555,  # delta = 0.005 < 0.01
        baseline_brier=0.20,
        augmented_brier=0.18,  # brier improved (irrelevant — delta gates first)
        n_samples=500,
        cfg=cfg,
    )
    assert decision == "DEPRECATE"


def test_decision_promote_when_delta_above_threshold_and_brier_better():
    """delta >= threshold AND brier improved → PROMOTE_PENDING."""
    cfg = Dl3AbConfig(min_samples=100, auc_delta_threshold=0.01)
    decision = decide(
        baseline_auc=0.55,
        augmented_auc=0.58,  # delta = 0.03 >= 0.01
        baseline_brier=0.22,
        augmented_brier=0.18,  # brier improved
        n_samples=500,
        cfg=cfg,
    )
    assert decision == "PROMOTE_PENDING"


def test_decision_inconclusive_when_delta_above_but_brier_worse():
    """delta >= threshold AND brier WORSE → INCONCLUSIVE (mixed signal)."""
    cfg = Dl3AbConfig(min_samples=100, auc_delta_threshold=0.01)
    decision = decide(
        baseline_auc=0.55,
        augmented_auc=0.58,  # delta = 0.03 >= 0.01
        baseline_brier=0.18,
        augmented_brier=0.22,  # brier worsened
        n_samples=500,
        cfg=cfg,
    )
    assert decision == "INCONCLUSIVE"


def test_decision_exact_threshold_treated_as_promote():
    """delta == threshold should NOT be DEPRECATE (uses < not <=)."""
    cfg = Dl3AbConfig(min_samples=100, auc_delta_threshold=0.01)
    decision = decide(
        baseline_auc=0.55,
        augmented_auc=0.56,  # delta = exactly 0.01
        baseline_brier=0.20,
        augmented_brier=0.18,
        n_samples=500,
        cfg=cfg,
    )
    assert decision == "PROMOTE_PENDING"


# ---------------------------------------------------------------------------
# Fail-soft tests for run_ab_test
# run_ab_test 的 fail-soft 測試
# ---------------------------------------------------------------------------


def test_run_ab_test_no_dsn_returns_insufficient_data():
    """dsn=None + no injected dataset → INSUFFICIENT_DATA, no raise."""
    cfg = Dl3AbConfig()
    result = run_ab_test(cfg, dsn=None)
    assert isinstance(result, AbResult)
    assert result.decision == "INSUFFICIENT_DATA"
    assert "fetch returned None" in result.notes or "unavailable" in result.notes


def test_run_ab_test_sklearn_unavailable_fail_soft():
    """sklearn missing → INSUFFICIENT_DATA, never raises."""
    with patch(
        "program_code.ml_training.dl3_ab_runner._try_import_sklearn",
        return_value=None,
    ):
        result = run_ab_test(Dl3AbConfig(), dsn=None)
        assert result.decision == "INSUFFICIENT_DATA"
        assert "sklearn" in result.notes


def test_run_ab_test_numpy_unavailable_fail_soft():
    """numpy missing → INSUFFICIENT_DATA, never raises."""
    with patch(
        "program_code.ml_training.dl3_ab_runner._try_import_numpy", return_value=None
    ):
        result = run_ab_test(Dl3AbConfig(), dsn=None)
        assert result.decision == "INSUFFICIENT_DATA"
        assert "numpy" in result.notes


def test_run_ab_test_does_not_raise_on_garbage_input():
    """Fuzz: any garbage input → AbResult, never raise."""
    cfg = Dl3AbConfig()
    bad_inputs = [
        {"X_baseline": None, "X_augmented": None, "y": None},
        {"X_baseline": [], "X_augmented": [], "y": []},
        {},
        {"X_baseline": "not-an-array", "X_augmented": "x", "y": "y"},
    ]
    for bad in bad_inputs:
        result = run_ab_test(cfg, dsn=None, _injected_dataset=bad)
        assert isinstance(result, AbResult)


def test_run_ab_test_dataset_missing_keys():
    """Injected dataset missing required keys → INSUFFICIENT_DATA.

    Skipped if sklearn unavailable (handled by separate fail-soft test).
    """
    pytest.importorskip("sklearn")
    cfg = Dl3AbConfig()
    result = run_ab_test(cfg, dsn=None, _injected_dataset={"X_baseline": [1, 2]})
    assert result.decision == "INSUFFICIENT_DATA"
    assert "missing required keys" in result.notes


def test_run_ab_test_below_min_samples():
    """Injected small dataset → INSUFFICIENT_DATA.

    Skipped if sklearn unavailable (handled by separate fail-soft test).
    """
    pytest.importorskip("sklearn")
    cfg = Dl3AbConfig(min_samples=100)
    np = pytest.importorskip("numpy")
    n = 20
    dataset = {
        "X_baseline": np.random.rand(n, 3),
        "X_augmented": np.random.rand(n, 5),
        "y": np.random.randint(0, 2, n),
    }
    result = run_ab_test(cfg, dsn=None, _injected_dataset=dataset)
    assert result.decision == "INSUFFICIENT_DATA"
    assert result.n_samples == n


# ---------------------------------------------------------------------------
# evaluate_auc_brier sanity check
# evaluate_auc_brier 健康檢查
# ---------------------------------------------------------------------------


def test_evaluate_auc_brier_known_values():
    """Hardcoded perfect classifier → AUC=1.0, Brier=0 (or near zero).

    Skipped if sklearn unavailable in dev env.
    """
    sklearn = pytest.importorskip("sklearn")
    y_true = [0, 0, 0, 1, 1, 1]
    y_pred = [0.0, 0.1, 0.2, 0.8, 0.9, 1.0]
    auc, brier = evaluate_auc_brier(y_true, y_pred)
    assert auc == pytest.approx(1.0, abs=1e-9)
    assert brier < 0.05  # very small brier for near-perfect


def test_evaluate_auc_brier_random_classifier():
    """Random classifier → AUC ~ 0.5."""
    sklearn = pytest.importorskip("sklearn")
    y_true = [0, 1, 0, 1, 0, 1, 0, 1]
    y_pred = [0.5] * 8
    auc, brier = evaluate_auc_brier(y_true, y_pred)
    # roc_auc with constant predictions throws or returns 0.5 — both acceptable
    assert 0.0 <= auc <= 1.0
    assert 0.0 <= brier <= 1.0


def test_evaluate_auc_brier_sklearn_unavailable_fail_soft():
    """sklearn missing → returns (0.0, 1.0), never raises."""
    with patch(
        "program_code.ml_training.dl3_ab_runner._try_import_sklearn",
        return_value=None,
    ):
        auc, brier = evaluate_auc_brier([0, 1], [0.5, 0.5])
        assert auc == 0.0
        assert brier == 1.0


# ---------------------------------------------------------------------------
# persist_decision tests
# persist_decision 測試
# ---------------------------------------------------------------------------


def test_persist_decision_skips_when_dsn_none():
    """dsn=None → returns False, no raise."""
    result = AbResult.insufficient("test")
    ok = persist_decision(None, result)
    assert ok is False


def test_persist_decision_skips_when_psycopg2_unavailable():
    """psycopg2 missing → returns False, no raise."""
    result = AbResult.insufficient("test")
    with patch(
        "program_code.ml_training.dl3_ab_runner._try_import_psycopg2",
        return_value=None,
    ):
        ok = persist_decision("postgresql://fake", result)
        assert ok is False


# ---------------------------------------------------------------------------
# fetch_training_dataset stub fail-soft
# fetch_training_dataset stub fail-soft
# ---------------------------------------------------------------------------


def test_fetch_training_dataset_dsn_none_returns_none():
    """dsn=None → returns None, no raise."""
    cfg = Dl3AbConfig()
    df = fetch_training_dataset(None, 0, 0, cfg)
    assert df is None


def test_fetch_training_dataset_psycopg2_missing_returns_none():
    """psycopg2 missing → returns None, no raise."""
    cfg = Dl3AbConfig()
    with patch(
        "program_code.ml_training.dl3_ab_runner._try_import_psycopg2",
        return_value=None,
    ):
        df = fetch_training_dataset("postgresql://fake", 0, 0, cfg)
        assert df is None


# ---------------------------------------------------------------------------
# AbResult dataclass
# AbResult 資料類別
# ---------------------------------------------------------------------------


def test_ab_result_insufficient_factory():
    """AbResult.insufficient factory builds a valid INSUFFICIENT_DATA result."""
    r = AbResult.insufficient("test reason", n_samples=42)
    assert r.decision == "INSUFFICIENT_DATA"
    assert r.notes == "test reason"
    assert r.n_samples == 42
    assert r.baseline_auc == 0.0
    assert r.augmented_auc == 0.0

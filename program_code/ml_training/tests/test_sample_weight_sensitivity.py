"""Tests for W6-5 sample_weight ratio sensitivity report helpers."""

from __future__ import annotations

import numpy as np
import pytest

from program_code.ml_training.sample_weight_sensitivity import (
    WalkForwardConfig,
    compute_ratio_sample_weights,
    cost_gate_distribution_shift,
    evaluate_sample_weight_ratio_sensitivity,
    ks_2samp_pvalue,
    population_stability_index,
    walk_forward_rolling_folds,
)


BASE_TS = 1_767_225_600.0


def test_compute_ratio_sample_weights_uses_requested_denominator():
    tags = np.array(["rejected_governance", None, "filled", "rejected_governance"], dtype=object)

    weights = compute_ratio_sample_weights(tags, 15)

    assert weights.tolist() == pytest.approx([1.0 / 15.0, 1.0, 1.0, 1.0 / 15.0])


def test_walk_forward_folds_use_purge_and_one_day_embargo():
    ts = BASE_TS + np.arange(30 * 24, dtype=np.float64) * 3600.0
    label_end = ts + 6 * 3600.0
    cfg = WalkForwardConfig(n_folds=5, train_window_days=10, test_window_days=2, embargo_days=1)

    folds = walk_forward_rolling_folds(ts, label_end, cfg)

    assert len(folds) == 5
    for train_idx, test_idx in folds:
        test_start = float(np.min(ts[test_idx]))
        assert float(np.max(label_end[train_idx])) < test_start
        assert float(np.min(ts[test_idx])) - float(np.max(ts[train_idx])) >= 18 * 3600.0


def test_psi_and_ks_are_stable_for_same_distribution():
    expected = np.linspace(-1.0, 1.0, 200)
    actual = expected.copy()

    assert population_stability_index(expected, actual) == pytest.approx(0.0, abs=1e-12)
    assert ks_2samp_pvalue(expected, actual) > 0.99


def test_cost_gate_distribution_shift_counts_pass_changes_and_b_delta():
    baseline = {
        "cell_a": {"pass": True, "B": 0.80},
        "cell_b": {"pass": False, "B": 0.50},
    }
    variant = {
        "cell_a": {"pass": False, "B": 0.70},
        "cell_b": {"pass": True, "B": 0.65},
        "cell_c": {"pass": True, "B": 0.90},
    }

    shift = cost_gate_distribution_shift(baseline, variant)

    assert shift["available"] is True
    assert shift["pass_changed_count"] == 2
    assert shift["pass_to_fail_count"] == 1
    assert shift["fail_to_pass_count"] == 1
    assert shift["new_in_variant_count"] == 1
    assert shift["b_factor_mean_delta"] == pytest.approx(0.025)
    assert shift["b_factor_max_abs_delta"] == pytest.approx(0.15)


def test_evaluate_sensitivity_returns_all_five_acceptance_metrics():
    n = 30 * 24
    ts = BASE_TS + np.arange(n, dtype=np.float64) * 3600.0
    rng = np.random.default_rng(7)
    x0 = np.sin(np.arange(n) / 18.0)
    x1 = np.cos(np.arange(n) / 21.0)
    features = np.column_stack([x0, x1, rng.normal(0.0, 0.05, n)])
    labels = 2.0 * x0 - 0.7 * x1 + rng.normal(0.0, 0.05, n)
    tags = np.where(np.arange(n) % 3 == 0, "rejected_governance", "filled")
    cells = np.where(np.arange(n) % 2 == 0, "cell_a", "cell_b")
    cfg = WalkForwardConfig(n_folds=5, train_window_days=10, test_window_days=2, embargo_days=1)

    report = evaluate_sample_weight_ratio_sensitivity(
        features,
        labels,
        ts,
        tags,
        label_end_timestamps=ts + 4 * 3600.0,
        ratio_denominators=(15, 170),
        baseline_ratio_denominator=170,
        config=cfg,
        cost_gate_cell_ids=cells,
        pass_threshold_bps=0.0,
    )

    assert report["status"] == "ok"
    assert report["report_only"] is True
    assert set(report["ratios"]) == {"1/15", "1/170"}
    for ratio_metrics in report["ratios"].values():
        assert len(ratio_metrics["per_fold"]) == 5
        assert "rmse_ci95" in ratio_metrics
        assert "is_oos_gap" in ratio_metrics
        assert "cross_fold_consistency" in ratio_metrics
        assert "prediction_drift" in ratio_metrics
        assert ratio_metrics["cost_gate_distribution_shift"]["available"] is True
    assert report["acceptance"]["missing_metric_count"] == 0

"""Report-only sample_weight ratio sensitivity checks for W6-5.

This module intentionally does not deploy models, update cron, or mutate the
production scorer path. It provides the MIT-requested acceptance metrics for
the regression scorer sample_weight question:

1. per-fold OOS RMSE + 95% CI
2. IS vs OOS RMSE gap
3. cross-fold consistency
4. prediction-distribution PSI + KS p-value
5. cost_gate decision distribution shift
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Optional

import numpy as np

from program_code.ml_training.label_generator import REJECTED_GOVERNANCE_TAG


DEFAULT_RATIO_DENOMINATORS = (15, 100, 170, 300, 500)
DEFAULT_BASELINE_RATIO_DENOMINATOR = 170
EPS = 1e-12


@dataclass(frozen=True)
class WalkForwardConfig:
    """5-fold rolling time-series CV required by W6-5."""

    n_folds: int = 5
    train_window_days: float = 10.0
    test_window_days: float = 2.0
    embargo_days: float = 1.0


FitPredictFn = Callable[
    [np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    tuple[np.ndarray, np.ndarray],
]


def compute_ratio_sample_weights(
    close_tags: np.ndarray,
    reject_denominator: int,
) -> np.ndarray:
    """Return weights where rejected_governance rows get 1/reject_denominator."""

    if reject_denominator <= 0:
        raise ValueError("reject_denominator must be positive")
    weights = np.ones(len(close_tags), dtype=np.float64)
    reject_weight = 1.0 / float(reject_denominator)
    for idx, tag in enumerate(close_tags):
        if tag is None:
            continue
        try:
            if str(tag) == REJECTED_GOVERNANCE_TAG:
                weights[idx] = reject_weight
        except Exception:
            continue
    return weights


def walk_forward_rolling_folds(
    timestamps: np.ndarray,
    label_end_timestamps: Optional[np.ndarray] = None,
    config: Optional[WalkForwardConfig] = None,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Generate rolling 10d train / 1d embargo / 2d test folds.

    Training rows are additionally purged so label_end_ts < test_start.
    Inputs may be epoch seconds or epoch milliseconds.
    """

    cfg = config or WalkForwardConfig()
    if cfg.n_folds <= 0:
        raise ValueError("n_folds must be positive")
    ts = _as_epoch_seconds(timestamps)
    if len(ts) == 0:
        return []
    order = np.argsort(ts, kind="stable")
    sorted_ts = ts[order]
    label_end = (
        _as_epoch_seconds(label_end_timestamps)[order]
        if label_end_timestamps is not None
        else sorted_ts.copy()
    )
    train_window = cfg.train_window_days * 86_400.0
    test_window = cfg.test_window_days * 86_400.0
    embargo = cfg.embargo_days * 86_400.0
    step = test_window
    first_train_start = float(sorted_ts[0])
    folds: list[tuple[np.ndarray, np.ndarray]] = []

    for fold_idx in range(cfg.n_folds):
        train_start = first_train_start + fold_idx * step
        train_end = train_start + train_window
        test_start = train_end + embargo
        test_end = test_start + test_window
        if test_start > sorted_ts[-1]:
            break
        train_mask = (
            (sorted_ts >= train_start)
            & (sorted_ts < train_end)
            & (label_end < test_start)
        )
        test_mask = (sorted_ts >= test_start) & (sorted_ts < test_end)
        train_idx = order[np.where(train_mask)[0]]
        test_idx = order[np.where(test_mask)[0]]
        if len(train_idx) == 0 or len(test_idx) == 0:
            continue
        folds.append((train_idx.astype(np.intp), test_idx.astype(np.intp)))
    return folds


def weighted_ridge_fit_predict(
    X_train: np.ndarray,
    y_train: np.ndarray,
    sample_weight_train: np.ndarray,
    X_test: np.ndarray,
    ridge_lambda: float = 1e-6,
) -> tuple[np.ndarray, np.ndarray]:
    """Small deterministic weighted-regression probe used by report dry-runs."""

    Xtr = np.asarray(X_train, dtype=np.float64)
    Xte = np.asarray(X_test, dtype=np.float64)
    ytr = np.asarray(y_train, dtype=np.float64)
    w = np.asarray(sample_weight_train, dtype=np.float64)
    if Xtr.ndim != 2 or Xte.ndim != 2:
        raise ValueError("features must be 2-D arrays")
    if len(Xtr) != len(ytr) or len(ytr) != len(w):
        raise ValueError("train features, labels, and weights must align")
    Xtr_i = np.column_stack([np.ones(len(Xtr)), Xtr])
    Xte_i = np.column_stack([np.ones(len(Xte)), Xte])
    sqrt_w = np.sqrt(np.maximum(w, EPS))
    Xw = Xtr_i * sqrt_w[:, None]
    yw = ytr * sqrt_w
    gram = Xw.T @ Xw
    penalty = np.eye(gram.shape[0], dtype=np.float64) * ridge_lambda
    penalty[0, 0] = 0.0
    beta = np.linalg.pinv(gram + penalty) @ (Xw.T @ yw)
    return Xtr_i @ beta, Xte_i @ beta


def population_stability_index(
    expected: np.ndarray,
    actual: np.ndarray,
    bins: int = 10,
) -> float:
    """Compute PSI using quantile bins from the expected distribution."""

    exp = _finite_vector(expected)
    act = _finite_vector(actual)
    if len(exp) == 0 or len(act) == 0:
        return 0.0
    quantiles = np.linspace(0.0, 1.0, bins + 1)
    edges = np.quantile(exp, quantiles)
    edges = np.unique(edges)
    if len(edges) < 2:
        return 0.0
    exp_counts, _ = np.histogram(exp, bins=edges)
    act_counts, _ = np.histogram(act, bins=edges)
    exp_pct = np.maximum(exp_counts / max(len(exp), 1), EPS)
    act_pct = np.maximum(act_counts / max(len(act), 1), EPS)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def ks_2samp_pvalue(expected: np.ndarray, actual: np.ndarray) -> float:
    """Approximate two-sample Kolmogorov-Smirnov p-value without scipy."""

    x = np.sort(_finite_vector(expected))
    y = np.sort(_finite_vector(actual))
    n = len(x)
    m = len(y)
    if n == 0 or m == 0:
        return 1.0
    values = np.concatenate([x, y])
    cdf_x = np.searchsorted(x, values, side="right") / n
    cdf_y = np.searchsorted(y, values, side="right") / m
    d_stat = float(np.max(np.abs(cdf_x - cdf_y)))
    if d_stat <= EPS:
        return 1.0
    en = math.sqrt(n * m / (n + m))
    lam = (en + 0.12 + 0.11 / max(en, EPS)) * d_stat
    terms = [
        ((-1) ** (k - 1)) * math.exp(-2.0 * (lam**2) * (k**2))
        for k in range(1, 101)
    ]
    return float(max(0.0, min(1.0, 2.0 * sum(terms))))


def cost_gate_distribution_shift(
    baseline: Mapping[str, Mapping[str, Any]],
    variant: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare cost_gate cell PASS decisions and JS shrinkage B factors."""

    base_keys = set(baseline.keys())
    variant_keys = set(variant.keys())
    common = sorted(base_keys & variant_keys)
    pass_changed = 0
    pass_to_fail = 0
    fail_to_pass = 0
    b_deltas: list[float] = []
    for cell in common:
        base_pass = _extract_pass_bool(baseline[cell])
        var_pass = _extract_pass_bool(variant[cell])
        if base_pass != var_pass:
            pass_changed += 1
            if base_pass and not var_pass:
                pass_to_fail += 1
            elif not base_pass and var_pass:
                fail_to_pass += 1
        base_b = _extract_b_factor(baseline[cell])
        var_b = _extract_b_factor(variant[cell])
        if base_b is not None and var_b is not None:
            b_deltas.append(var_b - base_b)
    return {
        "available": True,
        "source": "cost_gate_snapshot",
        "cells_compared": len(common),
        "pass_changed_count": pass_changed,
        "pass_to_fail_count": pass_to_fail,
        "fail_to_pass_count": fail_to_pass,
        "missing_in_variant_count": len(base_keys - variant_keys),
        "new_in_variant_count": len(variant_keys - base_keys),
        "b_factor_mean_delta": float(np.mean(b_deltas)) if b_deltas else 0.0,
        "b_factor_max_abs_delta": float(np.max(np.abs(b_deltas))) if b_deltas else 0.0,
    }


def evaluate_sample_weight_ratio_sensitivity(
    features: np.ndarray,
    labels: np.ndarray,
    timestamps: np.ndarray,
    close_tags: np.ndarray,
    *,
    label_end_timestamps: Optional[np.ndarray] = None,
    ratio_denominators: tuple[int, ...] = DEFAULT_RATIO_DENOMINATORS,
    baseline_ratio_denominator: int = DEFAULT_BASELINE_RATIO_DENOMINATOR,
    config: Optional[WalkForwardConfig] = None,
    fit_predict_fn: Optional[FitPredictFn] = None,
    cost_gate_cell_ids: Optional[np.ndarray] = None,
    pass_threshold_bps: float = 0.0,
    cost_gate_snapshots_by_ratio: Optional[
        Mapping[int, Mapping[str, Mapping[str, Any]]]
    ] = None,
) -> dict[str, Any]:
    """Run W6-5 report-only ratio sensitivity and return a JSON-safe report."""

    X = np.asarray(features, dtype=np.float64)
    y = np.asarray(labels, dtype=np.float64)
    tags = np.asarray(close_tags, dtype=object)
    if X.ndim != 2:
        raise ValueError("features must be a 2-D array")
    if len(X) != len(y) or len(y) != len(tags) or len(y) != len(timestamps):
        raise ValueError("features, labels, timestamps, and close_tags must align")

    folds = walk_forward_rolling_folds(timestamps, label_end_timestamps, config)
    runner = fit_predict_fn or weighted_ridge_fit_predict
    report: dict[str, Any] = {
        "status": "ok" if len(folds) == (config or WalkForwardConfig()).n_folds else "insufficient_folds",
        "report_only": True,
        "deployment": "no production cron/model artifact mutation",
        "methodology": {
            "task_type": "regression",
            "ratio_denominators": list(ratio_denominators),
            "baseline_ratio_denominator": baseline_ratio_denominator,
            "fold_count": len(folds),
            "train_window_days": (config or WalkForwardConfig()).train_window_days,
            "test_window_days": (config or WalkForwardConfig()).test_window_days,
            "embargo_days": (config or WalkForwardConfig()).embargo_days,
            "purge_rule": "training label_end_ts must be < test_start",
        },
        "ratios": {},
    }
    if not folds:
        report["acceptance"] = _acceptance_summary(report["ratios"])
        return report

    all_oos_predictions: dict[int, np.ndarray] = {}
    all_oos_indices: dict[int, np.ndarray] = {}
    for denom in ratio_denominators:
        weights = compute_ratio_sample_weights(tags, denom)
        fold_rows: list[dict[str, Any]] = []
        train_rmses: list[float] = []
        test_rmses: list[float] = []
        oos_preds: list[np.ndarray] = []
        oos_idxs: list[np.ndarray] = []
        for fold_idx, (train_idx, test_idx) in enumerate(folds):
            train_pred, test_pred = runner(
                X[train_idx],
                y[train_idx],
                weights[train_idx],
                X[test_idx],
            )
            train_rmse = _rmse(y[train_idx], train_pred)
            test_rmse = _rmse(y[test_idx], test_pred)
            train_rmses.append(train_rmse)
            test_rmses.append(test_rmse)
            oos_preds.append(np.asarray(test_pred, dtype=np.float64))
            oos_idxs.append(test_idx)
            fold_rows.append({
                "fold": fold_idx,
                "n_train": int(len(train_idx)),
                "n_test": int(len(test_idx)),
                "train_rmse": train_rmse,
                "oos_rmse": test_rmse,
                "prediction_psi": population_stability_index(train_pred, test_pred),
                "prediction_ks_pvalue": ks_2samp_pvalue(train_pred, test_pred),
            })
        all_oos_predictions[denom] = np.concatenate(oos_preds) if oos_preds else np.array([])
        all_oos_indices[denom] = np.concatenate(oos_idxs) if oos_idxs else np.array([], dtype=np.intp)
        rmse_mean, rmse_lower, rmse_upper = _mean_ci95(np.asarray(test_rmses))
        mean_train = float(np.mean(train_rmses)) if train_rmses else 0.0
        mean_oos = float(np.mean(test_rmses)) if test_rmses else 0.0
        gap_ratio = (mean_oos - mean_train) / max(abs(mean_train), EPS)
        std_mean_ratio = float(np.std(test_rmses) / max(abs(rmse_mean), EPS))
        report["ratios"][f"1/{denom}"] = {
            "per_fold": fold_rows,
            "rmse_ci95": {
                "mean": rmse_mean,
                "lower": rmse_lower,
                "upper": rmse_upper,
            },
            "is_oos_gap": {
                "mean_train_rmse": mean_train,
                "mean_oos_rmse": mean_oos,
                "gap_ratio": float(gap_ratio),
                "withdraw_baseline": bool(gap_ratio > 0.5),
            },
            "cross_fold_consistency": {
                "std_mean_ratio": std_mean_ratio,
                "shadow_blocked": bool(std_mean_ratio > 0.5),
            },
            "prediction_drift": {
                "max_psi": float(max(row["prediction_psi"] for row in fold_rows)),
                "min_ks_pvalue": float(min(row["prediction_ks_pvalue"] for row in fold_rows)),
            },
            "cost_gate_distribution_shift": {
                "available": False,
                "source": "not_evaluated",
                "reason": "cost_gate snapshots or cell ids were not supplied",
            },
        }

    _attach_cost_gate_shift_metrics(
        report,
        all_oos_predictions,
        all_oos_indices,
        baseline_ratio_denominator,
        cost_gate_snapshots_by_ratio,
        cost_gate_cell_ids,
        pass_threshold_bps,
    )
    report["acceptance"] = _acceptance_summary(report["ratios"])
    return report


def _attach_cost_gate_shift_metrics(
    report: dict[str, Any],
    all_oos_predictions: Mapping[int, np.ndarray],
    all_oos_indices: Mapping[int, np.ndarray],
    baseline_ratio_denominator: int,
    cost_gate_snapshots_by_ratio: Optional[Mapping[int, Mapping[str, Mapping[str, Any]]]],
    cost_gate_cell_ids: Optional[np.ndarray],
    pass_threshold_bps: float,
) -> None:
    if (
        cost_gate_snapshots_by_ratio
        and baseline_ratio_denominator in cost_gate_snapshots_by_ratio
    ):
        baseline_snapshot = cost_gate_snapshots_by_ratio[baseline_ratio_denominator]
        for ratio_key in report["ratios"].keys():
            denom = int(ratio_key.split("/")[1])
            variant = cost_gate_snapshots_by_ratio.get(denom)
            if variant is not None:
                report["ratios"][ratio_key]["cost_gate_distribution_shift"] = (
                    cost_gate_distribution_shift(baseline_snapshot, variant)
                )
        return

    if cost_gate_cell_ids is None or baseline_ratio_denominator not in all_oos_predictions:
        return

    cell_ids = np.asarray(cost_gate_cell_ids, dtype=object)
    base_indices = all_oos_indices[baseline_ratio_denominator]
    base_snapshot = _prediction_decision_snapshot(
        all_oos_predictions[baseline_ratio_denominator],
        cell_ids[base_indices],
        pass_threshold_bps,
    )
    for ratio_key in report["ratios"].keys():
        denom = int(ratio_key.split("/")[1])
        idxs = all_oos_indices[denom]
        snapshot = _prediction_decision_snapshot(
            all_oos_predictions[denom],
            cell_ids[idxs],
            pass_threshold_bps,
        )
        shift = cost_gate_distribution_shift(base_snapshot, snapshot)
        shift["source"] = "prediction_proxy"
        report["ratios"][ratio_key]["cost_gate_distribution_shift"] = shift


def _prediction_decision_snapshot(
    predictions: np.ndarray,
    cell_ids: np.ndarray,
    pass_threshold_bps: float,
) -> dict[str, dict[str, float | bool]]:
    snapshot: dict[str, dict[str, float | bool]] = {}
    for cell in sorted({str(c) for c in cell_ids}):
        mask = np.asarray([str(c) == cell for c in cell_ids], dtype=bool)
        vals = _finite_vector(predictions[mask])
        if len(vals) == 0:
            continue
        mean_pred = float(np.mean(vals))
        std_pred = float(np.std(vals))
        snapshot[cell] = {
            "pass": bool(mean_pred >= pass_threshold_bps),
            "B": float(1.0 / (1.0 + std_pred)),
            "mean_prediction_bps": mean_pred,
        }
    return snapshot


def _acceptance_summary(ratios: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    required = {
        "per_fold_rmse_ci": False,
        "is_oos_gap": False,
        "cross_fold_consistency": False,
        "psi_ks_prediction_drift": False,
        "cost_gate_distribution_shift": False,
    }
    for metrics in ratios.values():
        required["per_fold_rmse_ci"] |= bool(metrics.get("rmse_ci95"))
        required["is_oos_gap"] |= bool(metrics.get("is_oos_gap"))
        required["cross_fold_consistency"] |= bool(metrics.get("cross_fold_consistency"))
        drift = metrics.get("prediction_drift", {})
        required["psi_ks_prediction_drift"] |= (
            "max_psi" in drift and "min_ks_pvalue" in drift
        )
        cg_shift = metrics.get("cost_gate_distribution_shift", {})
        required["cost_gate_distribution_shift"] |= bool(cg_shift.get("available"))
    missing = [name for name, present in required.items() if not present]
    return {
        "required_metrics_present": required,
        "missing_metric_count": len(missing),
        "missing_metrics": missing,
        "mit_reject_if_missing_ge_3": bool(len(missing) >= 3),
    }


def _as_epoch_seconds(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    if len(arr) == 0:
        return arr
    finite = arr[np.isfinite(arr)]
    if len(finite) == 0:
        return arr
    if float(np.nanmedian(np.abs(finite))) > 1e12:
        return arr / 1000.0
    return arr


def _finite_vector(values: np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64)
    return arr[np.isfinite(arr)]


def _rmse(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    err = np.asarray(y_pred, dtype=np.float64) - np.asarray(y_true, dtype=np.float64)
    return float(np.sqrt(np.mean(err**2))) if len(err) else 0.0


def _mean_ci95(values: np.ndarray) -> tuple[float, float, float]:
    vals = _finite_vector(values)
    if len(vals) == 0:
        return 0.0, 0.0, 0.0
    mean = float(np.mean(vals))
    if len(vals) == 1:
        return mean, mean, mean
    stderr = float(np.std(vals, ddof=1) / math.sqrt(len(vals)))
    half = 1.96 * stderr
    return mean, mean - half, mean + half


def _extract_pass_bool(cell: Mapping[str, Any]) -> bool:
    if "pass" in cell:
        return bool(cell["pass"])
    if "passed" in cell:
        return bool(cell["passed"])
    decision = str(cell.get("decision", "")).lower()
    return decision in {"pass", "passed", "allow", "allowed"}


def _extract_b_factor(cell: Mapping[str, Any]) -> Optional[float]:
    for key in ("B", "b", "shrinkage_factor", "shrinkage_factor_B"):
        if key not in cell:
            continue
        try:
            value = float(cell[key])
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None

"""
Isotonic Calibration + Conformalized Quantile Regression (CQR) for EDGE-P3-1.
等調校準 + 保形分位回歸（CQR） — EDGE-P3-1 Stage 2 主線。

MODULE_NOTE (EN): Two modules in one:
  (1) Legacy isotonic probability calibration for scorer (ECE-targeted).
  (2) EDGE-P3-1 Stage 2 CQR one-sided marginal calibration for quantile trio
      — per Romano et al. 2019 with (n+1) finite-sample correction. Uses
      holdout residuals (y - q_pred) and shifts q_pred by the α-level
      quantile so empirical P(y ≤ q_new) ≈ α. Isotonic fallback retained
      for degenerate-quantile rescue (non-default path).
MODULE_NOTE (中): 兩個功能合併：
  (1) 傳統等調二元概率校準（ECE 目標，舊 scorer 用）。
  (2) EDGE-P3-1 Stage 2 CQR 單邊 marginal 校準（Romano 2019，(n+1) 有限樣本修正）：
      用 holdout 殘差 (y - q_pred) 的 α 分位作平移，使實證 P(y ≤ q_new) ≈ α。
      等調 fallback 保留為退化分位救援路徑（非主線）。
"""

from __future__ import annotations

import logging
import math
import pickle
from pathlib import Path
from typing import Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def calibrate_isotonic(
    raw_predictions: np.ndarray,
    actual_outcomes: np.ndarray,
    output_path: Optional[str] = None,
    blend_alpha: float = 0.3,
    existing_calibrator: Optional[object] = None,
) -> tuple[object, dict[str, float]]:
    """Fit isotonic calibration with optional blending.
    擬合等調校準，支持可選混合。

    Args:
        raw_predictions: model output scores
        actual_outcomes: binary (1=profit, 0=loss) or continuous
        output_path: save calibrator to this path
        blend_alpha: weight for new calibrator vs existing (0.3 = 30% new)
        existing_calibrator: previous calibrator for blending

    Returns:
        (calibrator, metrics_dict)
    """
    from sklearn.isotonic import IsotonicRegression

    # Convert continuous outcomes to binary for calibration
    binary = (actual_outcomes > 0).astype(float)

    calibrator = IsotonicRegression(out_of_bounds="clip")
    calibrator.fit(raw_predictions, binary)

    # Calibrated predictions / 校準預測
    calibrated = calibrator.predict(raw_predictions)

    # ECE (Expected Calibration Error) / 期望校準誤差
    n_bins = 10
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (calibrated >= bin_boundaries[i]) & (calibrated < bin_boundaries[i + 1])
        if mask.sum() > 0:
            bin_acc = binary[mask].mean()
            bin_conf = calibrated[mask].mean()
            ece += mask.sum() / len(calibrated) * abs(bin_acc - bin_conf)

    # Brier score / Brier 分數
    brier = float(np.mean((calibrated - binary) ** 2))

    metrics = {"ece": float(ece), "brier_score": brier, "n_samples": len(binary)}

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            pickle.dump(calibrator, f)
        logger.info("Calibrator saved to %s (ECE=%.4f, Brier=%.4f)", output_path, ece, brier)

    return calibrator, metrics


def apply_calibration(calibrator: object, raw_predictions: np.ndarray) -> np.ndarray:
    """Apply fitted calibrator to new predictions.
    對新預測應用已擬合的校準器。"""
    return calibrator.predict(raw_predictions)  # type: ignore


# ──────────────────────────────────────────────────────────────
# EDGE-P3-1 Stage 2: Conformalized Quantile Regression (CQR)
# ──────────────────────────────────────────────────────────────

def fit_cqr_offset(
    y_true: np.ndarray,
    q_pred: np.ndarray,
    alpha: float,
) -> float:
    """One-sided marginal CQR offset δ for quantile alpha (Romano et al. 2019).

    Residuals E_i = y_i − q_pred(x_i). Shift δ = finite-sample-corrected
    α-quantile of E. Calibrated prediction q_new(x) = q_pred(x) + δ targets
    empirical P(y ≤ q_new) ≈ α on holdout.

    Finite-sample correction: quantile level = ⌈α·(n+1)⌉ / n, clamped to
    [0, 1]. With n→∞ this collapses to the plain α-quantile. For small n
    it nudges the cut upward ensuring marginal coverage holds in expectation
    over holdout draws.

    殘差 E_i = y_i − q_pred(x_i)。取 (n+1) 有限樣本修正後的 α 分位作位移 δ。
    校準後預測 q_new(x) = q_pred(x) + δ，使 holdout 上 P(y ≤ q_new) ≈ α。
    n→∞ 時 collapse 為純 α 分位；小 n 時位置上移以期望上保證 marginal coverage。
    """
    n = len(y_true)
    if n == 0:
        return 0.0
    residuals = y_true.astype(np.float64) - q_pred.astype(np.float64)
    # Position: ⌈α·(n+1)⌉ / n with safe clamping. np.quantile interpolates linearly.
    # 位置：⌈α·(n+1)⌉ / n 並夾範圍；np.quantile 線性插值。
    q_level = math.ceil(alpha * (n + 1)) / n
    q_level = max(0.0, min(1.0, q_level))
    return float(np.quantile(residuals, q_level))


def apply_cqr_to_quantile(q_pred: np.ndarray, offset: float) -> np.ndarray:
    """Apply fitted CQR offset: q_new(x) = q_pred(x) + δ.
    套用 CQR 位移：q_new(x) = q_pred(x) + δ。"""
    return q_pred.astype(np.float64) + float(offset)


def fit_cqr_trio(
    y_holdout: np.ndarray,
    q10_pred: np.ndarray,
    q50_pred: np.ndarray,
    q90_pred: np.ndarray,
) -> Dict[str, float]:
    """Convenience: fit marginal CQR offsets for full quantile trio.

    Returns {"q10": δ10, "q50": δ50, "q90": δ90} with each δ computed by
    one-sided marginal CQR at the corresponding α.
    回傳三分位 marginal CQR 位移字典。每個 δ 以對應 α 單邊 marginal 計算。
    """
    return {
        "q10": fit_cqr_offset(y_holdout, q10_pred, 0.10),
        "q50": fit_cqr_offset(y_holdout, q50_pred, 0.50),
        "q90": fit_cqr_offset(y_holdout, q90_pred, 0.90),
    }


def evaluate_cqr_coverage(
    y_true: np.ndarray,
    q10_pred: np.ndarray,
    q50_pred: np.ndarray,
    q90_pred: np.ndarray,
    offsets: Dict[str, float],
) -> Dict[str, Tuple[float, float]]:
    """Post-calibration coverage check for a pre-fit CQR offset dict.

    Returns {"q10": (empirical, abs_err_pp), ...}. Used by acceptance report
    to verify CQR closed the coverage gap within spec §6.2 (<3pp).
    校準後 coverage 檢查：回傳每分位 (實證, 絕對 pp 誤差)；供 acceptance report 驗收。
    """
    result: Dict[str, Tuple[float, float]] = {}
    specs = (
        ("q10", 0.10, q10_pred),
        ("q50", 0.50, q50_pred),
        ("q90", 0.90, q90_pred),
    )
    for name, alpha, q_pred in specs:
        calibrated = apply_cqr_to_quantile(q_pred, offsets.get(name, 0.0))
        if len(y_true) == 0:
            result[name] = (0.0, 0.0)
            continue
        empirical = float(np.mean(y_true <= calibrated))
        result[name] = (empirical, float(abs(empirical - alpha) * 100.0))
    return result


def fit_isotonic_fallback(
    y_true: np.ndarray,
    y_pred: np.ndarray,
) -> Optional[object]:
    """Monotonic isotonic fallback when CQR produces degenerate offsets.

    Non-default rescue path: fit a monotonic mapping raw q_pred → y so that
    deficient quantile trio can still serve shadow-only traffic. Returns
    fitted IsotonicRegression or None when sklearn missing.
    CQR 退化時的單調 isotonic fallback：把 raw q_pred → y 的單調映射擬合，
    讓失敗的分位仍能服務 shadow 流量。sklearn 缺失時回 None。
    """
    try:
        from sklearn.isotonic import IsotonicRegression
    except ImportError:  # pragma: no cover
        logger.warning("sklearn.isotonic unavailable — isotonic fallback skipped")
        return None
    if len(y_true) == 0:
        return None
    ir = IsotonicRegression(out_of_bounds="clip")
    ir.fit(y_pred.astype(np.float64), y_true.astype(np.float64))
    return ir

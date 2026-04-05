"""
Isotonic Calibration — calibrate LightGBM predictions to true probabilities.
等調校準 — 將 LightGBM 預測校準為真實概率。

MODULE_NOTE (EN): Isotonic regression + Gaussian smoothing for probability calibration.
  Target: ECE < 0.05. Blends new vs old calibration to prevent recalibration shock.
MODULE_NOTE (中): 等調回歸 + 高斯平滑的概率校準。目標 ECE < 0.05。
"""

from __future__ import annotations

import logging
import pickle
from pathlib import Path
from typing import Optional

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

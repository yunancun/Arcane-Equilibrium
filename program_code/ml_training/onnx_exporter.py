"""
ONNX Exporter — convert LightGBM model to ONNX format for Rust inference.
ONNX 導出器 — 將 LightGBM 模型轉換為 ONNX 格式供 Rust 推理。

MODULE_NOTE (EN): Exports trained LightGBM model to ONNX with explicit f32 casting.
  Handles categorical features via integer encoding (no native ONNX categorical support).
  NaN sentinel values for missing features. Precision validation: max abs err < 1e-3.
MODULE_NOTE (中): 將訓練好的 LightGBM 模型導出為 ONNX，顯式 f32 轉換。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


def export_to_onnx(
    model_path: str,
    output_path: str,
    n_features: int = 34,
    validate_samples: Optional[np.ndarray] = None,
) -> dict[str, any]:
    """Export LightGBM .txt model to ONNX format.
    導出 LightGBM 模型為 ONNX 格式。

    Args:
        model_path: path to LightGBM .txt model
        output_path: path to save .onnx file
        n_features: expected input feature dimension
        validate_samples: optional samples for precision validation

    Returns:
        dict with export status + validation metrics
    """
    result = {"success": False, "output_path": output_path}

    try:
        import lightgbm as lgb
        import onnxmltools
        from onnxmltools.convert import convert_lightgbm
        from onnxmltools.convert.common.data_types import FloatTensorType
    except ImportError as e:
        result["error"] = f"Missing dependency: {e}. Install: pip install onnxmltools"
        logger.error(result["error"])
        return result

    try:
        model = lgb.Booster(model_file=model_path)

        # Convert to ONNX / 轉換為 ONNX
        initial_type = [("features", FloatTensorType([None, n_features]))]
        onnx_model = convert_lightgbm(model, initial_types=initial_type)

        # Save / 保存
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(onnx_model.SerializeToString())

        result["success"] = True
        result["n_features"] = n_features
        logger.info("ONNX model exported: %s (%d features)", output_path, n_features)

        # Precision validation / 精度驗證
        if validate_samples is not None and len(validate_samples) > 0:
            validation = validate_precision(model_path, output_path, validate_samples)
            result.update(validation)

    except Exception as e:
        result["error"] = str(e)
        logger.error("ONNX export failed: %s", e)

    return result


def validate_precision(
    lgb_model_path: str,
    onnx_path: str,
    samples: np.ndarray,
    max_abs_err: float = 1e-3,
) -> dict[str, any]:
    """Validate ONNX vs LightGBM prediction precision.
    驗證 ONNX vs LightGBM 預測精度。"""
    try:
        import lightgbm as lgb
        import onnxruntime as ort

        lgb_model = lgb.Booster(model_file=lgb_model_path)
        lgb_preds = lgb_model.predict(samples)

        sess = ort.InferenceSession(onnx_path)
        input_name = sess.get_inputs()[0].name
        onnx_preds = sess.run(None, {input_name: samples.astype(np.float32)})[0].flatten()

        abs_diff = np.abs(lgb_preds - onnx_preds)
        max_diff = float(abs_diff.max())
        mean_diff = float(abs_diff.mean())

        passed = max_diff < max_abs_err
        result = {
            "precision_max_abs_err": max_diff,
            "precision_mean_abs_err": mean_diff,
            "precision_passed": passed,
            "validation_samples": len(samples),
        }

        if passed:
            logger.info("ONNX precision PASS: max_err=%.6f < %.6f", max_diff, max_abs_err)
        else:
            logger.warning("ONNX precision FAIL: max_err=%.6f >= %.6f", max_diff, max_abs_err)

        return result

    except Exception as e:
        return {"precision_error": str(e), "precision_passed": False}

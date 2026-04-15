"""
ONNX Exporter — LightGBM → ONNX bridge for Rust tract/ort inference.
ONNX 導出器 — LightGBM → ONNX，供 Rust tract/ort 推理。

MODULE_NOTE (EN): Two export surfaces:
  (1) Legacy single-model regression export (`export_to_onnx`, path-based).
  (2) EDGE-P3-1 Stage 2 per-quantile trio export (`export_quantile_trio_to_onnx`)
      producing three independent ONNX artifacts with stable date-stamped
      filenames and per-quantile `_current` symlink swap. Target precision
      max |LGB − ONNX| < 1e-3 validated per file.
MODULE_NOTE (中): 兩個匯出介面：
  (1) 舊版單模型 regression 匯出（路徑為輸入）。
  (2) EDGE-P3-1 Stage 2 三分位匯出：各分位一個 ONNX 檔 + 日期戳檔名
      + `_current` symlink 原子換。每檔精度驗證 max|LGB−ONNX| < 1e-3。
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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


# ──────────────────────────────────────────────────────────────
# EDGE-P3-1 Stage 2: per-quantile trio export
# ──────────────────────────────────────────────────────────────

def _atomic_symlink_swap(link_path: Path, target_name: str) -> None:
    """POSIX-atomic symlink swap: symlink to tmp then os.replace → link_path.

    os.replace is atomic on POSIX filesystems; avoids a transient window where
    the `_current` symlink is missing under concurrent readers (Rust loader).
    POSIX 上 os.replace 原子；避免 Rust loader 併發讀時 symlink 消失的瞬間。
    """
    tmp = link_path.with_name(link_path.name + ".tmp_swap")
    if tmp.exists() or tmp.is_symlink():
        tmp.unlink()
    tmp.symlink_to(target_name)
    os.replace(tmp, link_path)


def _convert_booster_to_onnx(
    booster: Any,
    n_features: int,
) -> Any:
    """Convert an in-memory LightGBM booster to an ONNX ModelProto.

    Kept separate from file IO so downstream callers can validate precision
    before writing. Raises RuntimeError on missing dependency.
    將 in-memory booster 轉 ONNX ModelProto；分離檔案 IO 讓精度驗證在寫入前完成。
    """
    try:
        from onnxmltools.convert import convert_lightgbm
        from onnxmltools.convert.common.data_types import FloatTensorType
    except ImportError as e:
        raise RuntimeError(
            f"Missing onnxmltools / FloatTensorType: {e}. "
            "Install: pip install onnxmltools"
        ) from e
    initial_type = [("features", FloatTensorType([None, int(n_features)]))]
    return convert_lightgbm(booster, initial_types=initial_type)


# ONNX metadata_props keys — frozen train/serve contract (EDGE-P3-1 §7.2).
# Rust tract_backend reads these to reject mismatched artifacts at load time.
# Changing a key name requires synchronized Rust loader update.
# ONNX metadata_props 鍵名契約凍結；Rust tract_backend 依此拒絕不匹配 artifact。
_META_SCHEMA_VERSION   = "edge_p3_schema_version"
_META_SCHEMA_HASH      = "edge_p3_feature_schema_hash"
_META_DEFINITION_HASH  = "edge_p3_feature_definition_hash"
_META_ENGINE_MODE      = "edge_p3_engine_mode"
_META_STRATEGY_NAME    = "edge_p3_strategy_name"
_META_QUANTILE         = "edge_p3_quantile"
_META_TRAIN_DATE       = "edge_p3_train_date"
_META_MODEL_ID         = "edge_p3_model_id"
_META_N_FEATURES       = "edge_p3_n_features"


def _stamp_onnx_metadata(onnx_model: Any, meta: Dict[str, str]) -> None:
    """Attach metadata_props to an ONNX ModelProto in-place.

    ONNX spec: `ModelProto.metadata_props` is a repeated list of
    `StringStringEntryProto` with unique keys. Rust tract reads them via
    `InferenceModel::metadata()`. Duplicate-key defense: clear existing keys
    we own before re-appending, idempotent across re-exports.
    ONNX metadata_props 為 repeated list；寫入前先清我方 key 再 append，確保冪等。
    """
    owned_keys = set(meta.keys())
    keep = [p for p in onnx_model.metadata_props if p.key not in owned_keys]
    del onnx_model.metadata_props[:]
    onnx_model.metadata_props.extend(keep)
    for key, value in meta.items():
        if value is None:
            continue
        entry = onnx_model.metadata_props.add()
        entry.key = str(key)
        entry.value = str(value)


def _validate_booster_vs_onnx(
    booster: Any,
    onnx_path: str,
    samples: np.ndarray,
    max_abs_err: float = 1e-3,
) -> Dict[str, Any]:
    """Predict booster vs loaded ONNX on 1000 random vectors; return metrics.

    Used by `export_quantile_trio_to_onnx` as per-quantile precision gate.
    Returns dict with max/mean abs err + passed flag. 1000-row vectors are
    callers responsibility to generate (spec §6.2).
    供三分位匯出做 per-quantile 精度驗證（spec §6.2）；1000 random vector 由 caller 產生。
    """
    try:
        import onnxruntime as ort
    except ImportError as e:
        return {"precision_error": f"onnxruntime missing: {e}", "precision_passed": False}

    try:
        lgb_preds = np.asarray(booster.predict(samples), dtype=np.float64).flatten()
        sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
        input_name = sess.get_inputs()[0].name
        onnx_preds = sess.run(None, {input_name: samples.astype(np.float32)})[0]
        onnx_preds = np.asarray(onnx_preds, dtype=np.float64).flatten()
        abs_diff = np.abs(lgb_preds - onnx_preds)
        max_diff = float(abs_diff.max()) if len(abs_diff) else 0.0
        mean_diff = float(abs_diff.mean()) if len(abs_diff) else 0.0
        return {
            "precision_max_abs_err": max_diff,
            "precision_mean_abs_err": mean_diff,
            "precision_passed": bool(max_diff < max_abs_err),
            "validation_samples": int(len(samples)),
        }
    except Exception as e:  # noqa: BLE001
        return {"precision_error": str(e), "precision_passed": False}


def export_quantile_trio_to_onnx(
    models: Dict[str, Any],
    output_dir: str,
    engine_mode: str,
    strategy_name: str,
    n_features: int = 17,
    schema_version: str = "v1",
    train_date: Optional[str] = None,
    validate_samples: Optional[np.ndarray] = None,
    max_abs_err: float = 1e-3,
    feature_schema_hash: Optional[str] = None,
    feature_definition_hash: Optional[str] = None,
    model_id_prefix: str = "edge_predictor",
) -> Dict[str, Any]:
    """Export q10/q50/q90 trio, one ONNX per quantile + `_current` symlink.

    Filename convention (matches Rust loader contract, EDGE-P3-1 §7.2):
        edge_predictor_{engine_mode}_{strategy}_{quantile}_{schema_version}_{train_date}.onnx
    Plus per-quantile symlink:
        edge_predictor_{engine_mode}_{strategy}_{quantile}_{schema_version}_current.onnx
            → <latest dated file>

    Args:
        models: {"q10": booster, "q50": booster, "q90": booster}
        output_dir: artifact directory (created if absent).
        engine_mode: "paper" | "demo" | "live".
        strategy_name: e.g. "ma_crossover" / "funding_arb".
        n_features: input feature dim (17 for EDGE-P3-1 FeatureVectorV1).
        schema_version: tag for filename + forward compat.
        train_date: 'YYYY-MM-DD'; None → UTC today.
        validate_samples: 1000-vector sample matrix for precision gate.
        max_abs_err: precision threshold (spec §6.2: < 1e-3).

    Returns dict with per-quantile paths + precision metrics + overall success.
    檔名規範與 Rust loader 契約一致（§7.2）。回傳三分位路徑 + 精度指標 + 整體成功旗標。
    """
    result: Dict[str, Any] = {
        "success": False,
        "output_dir": output_dir,
        "engine_mode": engine_mode,
        "strategy_name": strategy_name,
        "schema_version": schema_version,
        "n_features": int(n_features),
        "artifacts": {},
    }

    if engine_mode not in ("paper", "demo", "live"):
        result["error"] = f"invalid engine_mode: {engine_mode!r}"
        return result
    expected = {"q10", "q50", "q90"}
    if set(models.keys()) != expected:
        result["error"] = f"models must contain exactly {sorted(expected)}, got {sorted(models.keys())}"
        return result

    # train_date normalized to YYYY-MM-DD UTC.
    if train_date is None:
        train_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    failed_quantiles: List[str] = []

    for qname, booster in models.items():
        fname = (
            f"edge_predictor_{engine_mode}_{strategy_name}_{qname}_"
            f"{schema_version}_{train_date}.onnx"
        )
        link_name = (
            f"edge_predictor_{engine_mode}_{strategy_name}_{qname}_"
            f"{schema_version}_current.onnx"
        )
        out_path = out_dir / fname
        link_path = out_dir / link_name

        entry: Dict[str, Any] = {
            "quantile": qname,
            "path": str(out_path),
            "symlink": str(link_path),
        }

        try:
            onnx_model = _convert_booster_to_onnx(booster, n_features)
            # Stamp train/serve metadata — Rust tract loader rejects artifacts
            # whose schema hash disagrees with FEATURE_NAMES_V1 compile-time
            # hash (spec §7.2 · F9 guard). Per-file, not per-trio, so each
            # quantile carries its own model_id for traceability.
            # 為每個 per-quantile 檔寫入 schema 契約 metadata；Rust tract 以此拒絕不匹配。
            model_id = f"{model_id_prefix}_{engine_mode}_{strategy_name}_{qname}_{schema_version}_{train_date}"
            _stamp_onnx_metadata(onnx_model, {
                _META_SCHEMA_VERSION:   schema_version,
                _META_SCHEMA_HASH:      feature_schema_hash or "",
                _META_DEFINITION_HASH:  feature_definition_hash or feature_schema_hash or "",
                _META_ENGINE_MODE:      engine_mode,
                _META_STRATEGY_NAME:    strategy_name,
                _META_QUANTILE:         qname,
                _META_TRAIN_DATE:       train_date,
                _META_MODEL_ID:         model_id,
                _META_N_FEATURES:       str(int(n_features)),
            })
            with open(out_path, "wb") as f:
                f.write(onnx_model.SerializeToString())
            entry["written"] = True
            entry["model_id"] = model_id
        except Exception as e:  # noqa: BLE001
            entry["written"] = False
            entry["error"] = str(e)
            failed_quantiles.append(qname)
            logger.error("ONNX conversion failed for %s: %s", qname, e)
            result["artifacts"][qname] = entry
            continue

        # Precision gate (per-file). Shadow-only / should_ship decision is in
        # quantile_reports; here we just surface the metric.
        # per-file 精度 gate；should_ship 判定在 quantile_reports。
        if validate_samples is not None and len(validate_samples) > 0:
            precision = _validate_booster_vs_onnx(
                booster, str(out_path), validate_samples, max_abs_err,
            )
            entry.update(precision)

        # Atomic symlink swap — only if write + conversion succeeded.
        # 原子 symlink 換；只在寫入 + 轉換成功後執行。
        try:
            _atomic_symlink_swap(link_path, fname)
            entry["symlink_updated"] = True
        except OSError as e:
            entry["symlink_updated"] = False
            entry["symlink_error"] = str(e)
            logger.warning("symlink swap failed for %s: %s", qname, e)

        result["artifacts"][qname] = entry

    result["train_date"] = train_date
    result["success"] = not failed_quantiles
    if failed_quantiles:
        result["failed_quantiles"] = failed_quantiles

    logger.info(
        "export_quantile_trio_to_onnx: engine=%s strategy=%s success=%s failed=%s",
        engine_mode, strategy_name, result["success"], failed_quantiles,
    )
    return result

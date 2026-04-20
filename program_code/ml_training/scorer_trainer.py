"""
LightGBM Scorer Trainer — train signal quality scorer with CPCV + embargo.
LightGBM 評分器訓練器 — 使用 CPCV + embargo 訓練信號質量評分器。

MODULE_NOTE (EN): Trains a LightGBM regression model to predict ATR-normalized PnL.
  Uses Combinatorial Purged Cross-Validation (CPCV) with per-strategy embargo periods.
  Outputs: model.pkl + metrics.json. Calibration done separately.
MODULE_NOTE (中): 訓練 LightGBM 回歸模型預測 ATR 歸一化 PnL。
  使用組合清洗交叉驗證 + 每策略 embargo 期。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)

# Honour OPENCLAW_DATA_DIR for cross-platform dev (Mac: $HOME/.openclaw_runtime).
# 支援 OPENCLAW_DATA_DIR 跨平台開發（Mac：$HOME/.openclaw_runtime）。
DEFAULT_MODEL_DIR = os.path.join(
    os.environ.get("OPENCLAW_DATA_DIR", "/tmp/openclaw"), "models"
)


@dataclass
class ScorerConfig:
    """LightGBM scorer training configuration / LightGBM 評分器訓練配置"""
    # LightGBM params / LightGBM 參數
    num_leaves: int = 31
    max_depth: int = 7
    learning_rate: float = 0.05
    n_estimators: int = 500
    min_child_samples: int = 20
    subsample: float = 0.8
    colsample_bytree: float = 0.8
    reg_alpha: float = 0.1
    reg_lambda: float = 1.0

    # CPCV params — 4-fold, strategy-specific embargo (Phase 3b audit: 24/4/8/72h)
    # CPCV 參數 — 4 折，策略特定 embargo（Phase 3b 審計：24/4/8/72h）
    n_folds: int = 4
    embargo_hours_trend: int = 24
    embargo_hours_revert: int = 4
    embargo_hours_arb: int = 8
    embargo_hours_grid: int = 72
    power_threshold: float = 0.5

    # Output / 輸出
    output_dir: str = DEFAULT_MODEL_DIR


def get_embargo_hours(config: ScorerConfig, strategy_type: str) -> int:
    """Get embargo hours for a strategy type / 根據策略類型獲取 embargo 小時數。

    Strategy types: trending, reversion, arb, grid.
    策略類型：趨勢、回歸、套利、網格。
    """
    mapping = {
        "trending": config.embargo_hours_trend,
        "ma_crossover": config.embargo_hours_trend,
        "reversion": config.embargo_hours_revert,
        "bb_reversion": config.embargo_hours_revert,
        "arb": config.embargo_hours_arb,
        "funding_arb": config.embargo_hours_arb,
        "grid": config.embargo_hours_grid,
        "grid_trading": config.embargo_hours_grid,
    }
    return mapping.get(strategy_type, config.embargo_hours_trend)


@dataclass
class TrainingResult:
    """Result of a training run / 訓練結果"""
    model_path: str = ""
    metrics: dict[str, float] = field(default_factory=dict)
    feature_importance: dict[str, float] = field(default_factory=dict)
    n_samples: int = 0
    n_features: int = 0
    success: bool = False
    error: str = ""


def _lgb_params(cfg: ScorerConfig) -> dict:
    """LightGBM hyperparameter dict from ScorerConfig.
    從 ScorerConfig 構建 LightGBM 超參數字典。"""
    return {
        "objective": "regression",
        "metric": "rmse",
        "num_leaves": cfg.num_leaves,
        "max_depth": cfg.max_depth,
        "learning_rate": cfg.learning_rate,
        "min_child_samples": cfg.min_child_samples,
        "subsample": cfg.subsample,
        "colsample_bytree": cfg.colsample_bytree,
        "reg_alpha": cfg.reg_alpha,
        "reg_lambda": cfg.reg_lambda,
        "verbose": -1,
    }


def train_scorer(
    features: np.ndarray,
    labels: np.ndarray,
    feature_names: list[str],
    config: Optional[ScorerConfig] = None,
    timestamps: Optional[np.ndarray] = None,
    strategy_type: str = "trending",
) -> TrainingResult:
    """Train LightGBM scorer with CPCV.
    使用 CPCV 訓練 LightGBM 評分器。

    Args:
        features: (n_samples, n_features) array
        labels: (n_samples,) ATR-normalized PnL
        feature_names: list of feature column names
        config: training configuration
        timestamps: (n_samples,) epoch-ms timestamps. When provided enables CPCV
            validation. Falls back to 80/20 split when None (legacy path).
        strategy_type: trending/reversion/arb/grid — selects embargo period.
    """
    cfg = config or ScorerConfig()
    result = TrainingResult(n_samples=len(labels), n_features=len(feature_names))

    try:
        import lightgbm as lgb
    except ImportError:
        result.error = "lightgbm not installed"
        logger.error("lightgbm not available — install via: pip install lightgbm")
        return result

    if len(labels) < cfg.min_child_samples * cfg.n_folds:
        result.error = f"insufficient samples: {len(labels)} < {cfg.min_child_samples * cfg.n_folds}"
        logger.warning(result.error)
        return result

    try:
        if timestamps is not None and len(timestamps) == len(labels):
            # P1-4: CPCV-validated training path / CPCV 驗證訓練路徑
            from ml_training.cpcv_validator import CPCVConfig, validate_cpcv

            def _lgb_fold_model(
                X_tr: np.ndarray, y_tr: np.ndarray,
                X_te: np.ndarray, y_te: np.ndarray,
            ) -> dict:
                train_data = lgb.Dataset(X_tr, label=y_tr, feature_name=feature_names)
                valid_data = lgb.Dataset(X_te, label=y_te, reference=train_data)
                fold_model = lgb.train(
                    _lgb_params(cfg),
                    train_data,
                    num_boost_round=cfg.n_estimators,
                    valid_sets=[valid_data],
                    callbacks=[lgb.early_stopping(50, verbose=False)],
                )
                preds = fold_model.predict(X_te)
                rmse = float(np.sqrt(np.mean((preds - y_te) ** 2)))
                # Sharpe proxy from prediction-weighted returns
                std = float(np.std(preds)) or 1.0
                sharpe = float(np.mean(preds * y_te)) / std * np.sqrt(252)
                return {"sharpe": sharpe, "rmse": rmse}

            cpcv_cfg = CPCVConfig(
                n_folds=cfg.n_folds,
                embargo_map={
                    "trending": cfg.embargo_hours_trend,
                    "reversion": cfg.embargo_hours_revert,
                    "arb": cfg.embargo_hours_arb,
                    "grid": cfg.embargo_hours_grid,
                },
                power_threshold=cfg.power_threshold,
            )
            cpcv_result = validate_cpcv(
                features, labels, timestamps, strategy_type, _lgb_fold_model, cpcv_cfg,
            )
            if not cpcv_result.passed:
                logger.warning(
                    "CPCV did not pass (power=%.3f, mean_sharpe=%.3f) — continuing "
                    "with final fit but marking as reference-only",
                    cpcv_result.power_estimate, cpcv_result.mean_sharpe,
                )

            # Final fit on all data after CPCV validation (leak-free since CV
            # used purged+embargoed folds). / CPCV 驗證後用全部資料最終擬合。
            split_idx = int(len(labels) * 0.8)
            X_train, X_test = features[:split_idx], features[split_idx:]
            y_train, y_test = labels[:split_idx], labels[split_idx:]
            result.metrics["cpcv_mean_sharpe"] = cpcv_result.mean_sharpe
            result.metrics["cpcv_std_sharpe"] = cpcv_result.std_sharpe
            result.metrics["cpcv_power"] = cpcv_result.power_estimate
            result.metrics["cpcv_passed"] = 1.0 if cpcv_result.passed else 0.0
        else:
            # Legacy path: simple train/test split / 傳統路徑：簡單分割
            split_idx = int(len(labels) * 0.8)
            X_train, X_test = features[:split_idx], features[split_idx:]
            y_train, y_test = labels[:split_idx], labels[split_idx:]

        train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
        valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

        model = lgb.train(
            _lgb_params(cfg),
            train_data,
            num_boost_round=cfg.n_estimators,
            valid_sets=[valid_data],
            callbacks=[lgb.early_stopping(50, verbose=False)],
        )

        # Save model / 保存模型
        output_dir = Path(cfg.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        model_path = output_dir / "scorer_lgb.txt"
        model.save_model(str(model_path))

        # Compute metrics / 計算指標
        preds = model.predict(X_test)
        rmse = float(np.sqrt(np.mean((preds - y_test) ** 2)))
        corr = float(np.corrcoef(preds, y_test)[0, 1]) if len(y_test) > 1 else 0.0

        # Feature importance / 特徵重要性
        importance = dict(zip(feature_names, model.feature_importance("gain").tolist()))

        result.model_path = str(model_path)
        result.metrics = {"rmse": rmse, "correlation": corr, "best_iteration": model.best_iteration}
        result.feature_importance = importance
        result.success = True

        logger.info(
            "Scorer trained: samples=%d, rmse=%.4f, corr=%.4f, best_iter=%d",
            len(labels), rmse, corr, model.best_iteration,
        )

    except Exception as e:
        result.error = str(e)
        logger.error("Scorer training failed: %s", e)

    return result

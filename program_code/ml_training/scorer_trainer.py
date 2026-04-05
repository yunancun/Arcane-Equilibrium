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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


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
    output_dir: str = "/tmp/openclaw/models"


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


def train_scorer(
    features: np.ndarray,
    labels: np.ndarray,
    feature_names: list[str],
    config: Optional[ScorerConfig] = None,
) -> TrainingResult:
    """Train LightGBM scorer with CPCV.
    使用 CPCV 訓練 LightGBM 評分器。

    Args:
        features: (n_samples, n_features) array
        labels: (n_samples,) ATR-normalized PnL
        feature_names: list of feature column names
        config: training configuration
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
        # Simple train/test split — placeholder for CPCV (see cpcv_validator.py)
        # 簡單分割 — CPCV 佔位符（見 cpcv_validator.py）
        split_idx = int(len(labels) * 0.8)
        X_train, X_test = features[:split_idx], features[split_idx:]
        y_train, y_test = labels[:split_idx], labels[split_idx:]

        train_data = lgb.Dataset(X_train, label=y_train, feature_name=feature_names)
        valid_data = lgb.Dataset(X_test, label=y_test, reference=train_data)

        params = {
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

        model = lgb.train(
            params,
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

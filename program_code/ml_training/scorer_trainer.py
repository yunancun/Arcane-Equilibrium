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
    # 狀態封頂欄位：CPCV 未通過、或 purge 後訓練樣本不足時降為 "reference_only"。
    # 為什麼是持久欄位而非僅 log warning：下游消費者（_run_legacy_scorer_pipeline /
    # metrics.json 讀者 / 晉升器）必須有一個可據以「拒絕晉升」的 reference；
    # log warning 會消失、無法被 honor，正是 Item 5 要修的缺口。
    status: str = "ok"


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


def _derive_model_status(
    cpcv_passed: bool, n_train_after_purge: int, min_train_floor: int
) -> str:
    """依 CPCV 結果與 purge 後訓練樣本數決定模型狀態封頂。

    為什麼獨立成純函式：狀態封頂是 Item 5 的核心不變量，須能在無 lightgbm 的環境
      （Mac）直接單測（train_scorer 本體依賴 lightgbm）。回傳 "ok" 或 "reference_only"。
    封頂規則（fail-closed，任一成立即降級）：
      1. CPCV 未通過 → reference_only（統計功效不足或 mean_sharpe<=0，不可據以晉升）。
      2. purge 後訓練樣本 < 最小葉節點門檻 → reference_only（holdout 指標不可信）。
    """
    if not cpcv_passed:
        return "reference_only"
    if n_train_after_purge < min_train_floor:
        return "reference_only"
    return "ok"


def _tail_holdout_train_indices(
    timestamps: np.ndarray,
    split_idx: int,
    embargo_hours: float,
    label_window_hours: float,
) -> np.ndarray:
    """為尾端 holdout 計算「清洗 + embargo」後的訓練索引。

    為什麼：最終 metrics.json 的 rmse/correlation 在尾端 holdout（split_idx 之後）上
      計算；若訓練尾段與 holdout 在時間上相鄰，訓練樣本的前視標籤窗口會滲入 holdout
      期間（temporal leakage），使 reported 指標樂觀偏誤。移除 purge_before（標籤窗口
      跨入 test）∪ embargo_before（相鄰緩衝）兩窗口內的訓練樣本即可切斷此滲漏。
    不變量：只移除訓練側（索引 < split_idx）樣本，holdout 本身不動；回傳索引全部 <
      split_idx，因此與 holdout 索引 pairwise disjoint。
    單位：與 cpcv_validator.generate_folds 保持一致，>1e12 視為毫秒並轉為秒。
    """
    n = len(timestamps)
    if split_idx <= 0 or split_idx >= n:
        # 退化分割：無可清洗的邊界，回傳原訓練索引（呼叫端另有 fail-closed 保護）。
        return np.arange(max(split_idx, 0), dtype=np.intp)

    ts = np.asarray(timestamps, dtype=np.float64)
    if ts[0] > 1e12:
        ts = ts / 1000.0

    test_start = ts[split_idx]
    embargo_sec = float(embargo_hours) * 3600.0
    purge_sec = float(label_window_hours) * 3600.0

    train_ts = ts[:split_idx]
    # 忠實複刻 cpcv_validator.generate_folds 的 purge_before ∪ embargo_before（含邊界
    # 包含性差異）：purge 用嚴格 >（標籤窗口跨入 test），embargo 用 >=（相鄰緩衝）。
    remove = (train_ts + purge_sec > test_start) | (train_ts >= test_start - embargo_sec)
    keep = ~remove
    return np.where(keep)[0].astype(np.intp)


def train_scorer(
    features: np.ndarray,
    labels: np.ndarray,
    feature_names: list[str],
    config: Optional[ScorerConfig] = None,
    timestamps: Optional[np.ndarray] = None,
    strategy_type: str = "trending",
    dsn: Optional[str] = None,
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
        dsn: PostgreSQL DSN threaded into validate_cpcv → _persist_cpcv_result
            (Item 6). None → env 解析。由 run_training_pipeline 以 config.dsn 傳入，
            統一 CPCV 持久化的 DSN 來源（OPENCLAW_DATABASE_URL 為權威）。
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
            from program_code.ml_training.cpcv_validator import CPCVConfig, validate_cpcv

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
                dsn=dsn,
            )
            # Item 5：對「最終 holdout」施加 purge + embargo，使 reported metrics.json
            # 的 rmse/correlation 來自一個已清洗的分割。原註解宣稱「final fit leak-free
            # since CV used purged folds」是誤導 —— CV 折疊確有清洗，但這裡的 80/20 最終
            # 分割沒有，訓練尾段的前視標籤會滲入 holdout 頭部。
            split_idx = int(len(labels) * 0.8)
            embargo_h = get_embargo_hours(cfg, strategy_type)
            label_window_h = cpcv_cfg.label_window_hours
            train_idx = _tail_holdout_train_indices(
                timestamps, split_idx, embargo_h, label_window_h,
            )
            if len(train_idx) == 0:
                # 為什麼 fail-closed：purge 後無任何訓練樣本，無法產出可信模型/holdout 指標。
                result.error = (
                    f"purge+embargo removed all training rows "
                    f"(split_idx={split_idx}, embargo_h={embargo_h})"
                )
                logger.warning(result.error)
                return result
            X_train, y_train = features[train_idx], labels[train_idx]
            X_test, y_test = features[split_idx:], labels[split_idx:]

            # 狀態封頂：CPCV 未通過、或 purge 後訓練樣本低於最小葉節點門檻 → reference_only。
            # 這是 Item 5 的核心：讓 cpcv_result.passed=False 真正 CAP 住模型狀態。
            result.status = _derive_model_status(
                cpcv_result.passed, len(train_idx), cfg.min_child_samples,
            )
            if result.status != "ok":
                logger.warning(
                    "Scorer capped to %s (cpcv_passed=%s, power=%.3f, mean_sharpe=%.3f, "
                    "n_train_after_purge=%d) — downstream must not promote/ship",
                    result.status, cpcv_result.passed, cpcv_result.power_estimate,
                    cpcv_result.mean_sharpe, len(train_idx),
                )
            result.metrics["cpcv_mean_sharpe"] = cpcv_result.mean_sharpe
            result.metrics["cpcv_std_sharpe"] = cpcv_result.std_sharpe
            result.metrics["cpcv_power"] = cpcv_result.power_estimate
            result.metrics["cpcv_passed"] = 1.0 if cpcv_result.passed else 0.0
            # 分割 provenance：holdout 清洗量 + 使用的 embargo 小時（寫入 metrics.json 供審計）。
            result.metrics["holdout_purged_rows"] = float(split_idx - len(train_idx))
            result.metrics["holdout_embargo_hours"] = float(embargo_h)
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
        # 用 update 而非直接賦值：CPCV branch 先前寫入的 cpcv_* / holdout_* 封頂欄位必須
        # 保留到 metrics.json，否則下游看不到「reference_only」的機器可據旗標
        # （原本 `result.metrics = {...}` 會把 cpcv_passed 等鍵整個蓋掉）。
        result.metrics.update(
            {"rmse": rmse, "correlation": corr, "best_iteration": model.best_iteration}
        )
        # ship_eligible = 下游晉升器唯一需要 honor 的布林旗標（1.0=可晉升，0.0=僅供參考）。
        # status!="ok"（CPCV 未通過 / purge 後樣本不足）→ 0.0，確保封頂被下游 honor。
        result.metrics["ship_eligible"] = 1.0 if result.status == "ok" else 0.0
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

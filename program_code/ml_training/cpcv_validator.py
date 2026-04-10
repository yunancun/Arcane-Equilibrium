"""
Combinatorial Purged Cross-Validation (CPCV) with strategy-specific embargo.
組合清洗交叉驗證 + 策略特定 embargo。

MODULE_NOTE (EN): Implements 4-fold CPCV with temporal purging and per-strategy
  embargo periods. Power guard flags low-power results as reference-only.
  Used by Optuna TPE (Phase 3b) to validate parameter configurations.
MODULE_NOTE (中): 實現 4 折 CPCV，含時間清洗和每策略 embargo 期。
  Power guard 標記低功率結果為僅供參考。用於 Optuna TPE 驗證參數配置。
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

try:
    import numpy as np
except ImportError:  # pragma: no cover
    np = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# Strategy name → category mapping / 策略名稱 → 類別映射
_STRATEGY_CATEGORY_MAP: Dict[str, str] = {
    # Trending strategies / 趨勢策略
    "ma_crossover": "trending",
    "bb_breakout": "trending",
    "momentum": "trending",
    "trend_follow": "trending",
    # Reversion strategies / 回歸策略
    "bb_reversion": "reversion",
    "mean_reversion": "reversion",
    # Arbitrage strategies / 套利策略
    "arb": "arb",
    "arbitrage": "arb",
    "funding_arb": "arb",
    # Grid strategies / 網格策略
    "grid": "grid",
    "grid_trading": "grid",
}


@dataclass
class CPCVConfig:
    """Configuration for CPCV validation.
    CPCV 驗證配置。"""

    n_folds: int = 4
    embargo_map: Dict[str, int] = field(
        default_factory=lambda: {
            "trending": 24,
            "reversion": 4,
            "arb": 8,
            "grid": 72,
        }
    )
    label_window_hours: float = 4.0  # default label window for purge / 清洗用標籤窗口
    power_threshold: float = 0.5
    min_samples_per_fold: int = 30


@dataclass
class CPCVResult:
    """Result of CPCV validation.
    CPCV 驗證結果。"""

    fold_metrics: List[Dict[str, Any]]
    mean_sharpe: float
    std_sharpe: float
    power_estimate: float
    passed: bool  # True only if power >= threshold AND mean_sharpe > 0
    n_folds: int
    embargo_hours: int
    strategy_type: str


def get_embargo_hours(strategy_type: str, config: Optional[CPCVConfig] = None) -> int:
    """Map strategy type/name to embargo hours.
    將策略類型/名稱映射到 embargo 小時數。

    Accepts either a category name (e.g. 'trending') or a specific strategy
    name (e.g. 'ma_crossover'). Falls back to max embargo if unknown.
    接受類別名稱或具體策略名稱。未知策略使用最大 embargo。
    """
    if config is None:
        config = CPCVConfig()
    embargo_map = config.embargo_map

    # Direct match on category / 直接匹配類別
    st = strategy_type.lower().strip()
    if st in embargo_map:
        return embargo_map[st]

    # Resolve specific strategy name → category / 解析具體策略名 → 類別
    category = _STRATEGY_CATEGORY_MAP.get(st)
    if category is not None and category in embargo_map:
        return embargo_map[category]

    # Unknown strategy — use max embargo as conservative default / 未知策略用最大值
    logger.warning(
        "Unknown strategy_type '%s', using max embargo %dh",
        strategy_type,
        max(embargo_map.values()),
    )
    return max(embargo_map.values())


def generate_folds(
    timestamps: np.ndarray,
    strategy_type: str,
    config: Optional[CPCVConfig] = None,
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """Generate CPCV fold indices with temporal purge + embargo.
    生成帶時間清洗 + embargo 的 CPCV 折疊索引。

    Args:
        timestamps: Sorted array of epoch seconds (or ms — auto-detected).
            排序的時間戳陣列（秒或毫秒，自動偵測）。
        strategy_type: Strategy name or category for embargo lookup.
            策略名稱或類別，用於查找 embargo。
        config: CPCV configuration. / CPCV 配置。

    Returns:
        List of (train_indices, test_indices) numpy int arrays.
        Pre-computed upfront as required by E5-O8.
        (訓練索引, 測試索引) 的列表，預先計算完成。
    """
    if np is None:
        raise ImportError("numpy is required for CPCV / numpy 為 CPCV 必需依賴")

    if config is None:
        config = CPCVConfig()

    n = len(timestamps)
    if n == 0:
        return []

    ts = timestamps.astype(np.float64).copy()

    # Auto-detect milliseconds → convert to seconds / 自動偵測毫秒 → 轉秒
    if ts[0] > 1e12:
        ts = ts / 1000.0

    embargo_hours = get_embargo_hours(strategy_type, config)
    embargo_sec = embargo_hours * 3600.0
    purge_sec = config.label_window_hours * 3600.0

    # Split into n_folds equal temporal blocks by index / 按索引分成 n_folds 等分
    fold_boundaries = np.array_split(np.arange(n), config.n_folds)

    # Pre-compute all fold time ranges / 預計算所有折疊時間範圍
    fold_start_times = np.array([ts[block[0]] for block in fold_boundaries])
    fold_end_times = np.array([ts[block[-1]] for block in fold_boundaries])

    folds: List[Tuple[np.ndarray, np.ndarray]] = []

    for test_fold_idx in range(config.n_folds):
        test_indices = fold_boundaries[test_fold_idx].astype(np.intp)
        test_start = fold_start_times[test_fold_idx]
        test_end = fold_end_times[test_fold_idx]

        # Start with all non-test indices / 從所有非測試索引開始
        train_mask = np.ones(n, dtype=bool)
        train_mask[test_indices] = False

        # Purge: remove samples whose label window crosses into test fold
        # 清洗：移除標籤窗口跨入測試折疊的樣本
        # Samples before test fold whose label extends into test
        purge_before = (ts < test_start) & (ts + purge_sec > test_start)
        # Samples after test fold whose label extends back into test
        purge_after = (ts > test_end) & (ts - purge_sec < test_end)
        train_mask[purge_before] = False
        train_mask[purge_after] = False

        # Embargo: additional buffer adjacent to test fold / Embargo：測試折疊相鄰的額外緩衝
        # Before test fold
        embargo_before = (ts >= test_start - embargo_sec) & (ts < test_start)
        # After test fold
        embargo_after = (ts > test_end) & (ts <= test_end + embargo_sec)
        train_mask[embargo_before] = False
        train_mask[embargo_after] = False

        train_indices = np.where(train_mask)[0].astype(np.intp)
        folds.append((train_indices, test_indices))

    return folds


def estimate_power(
    n_samples: int,
    n_folds: int,
    effect_size: float = 0.3,
) -> float:
    """Estimate statistical power for CPCV.
    估計 CPCV 的統計功效。

    Approximate formula: power ≈ 1 - exp(-samples_per_fold * effect_size² / 4)
    Clamped to [0, 1].
    近似公式，限定在 [0, 1] 範圍內。
    """
    if n_folds <= 0 or n_samples <= 0:
        return 0.0
    samples_per_fold = n_samples / n_folds
    raw = 1.0 - math.exp(-samples_per_fold * effect_size**2 / 4.0)
    return max(0.0, min(1.0, raw))


def validate_cpcv(
    X: np.ndarray,
    y: np.ndarray,
    timestamps: np.ndarray,
    strategy_type: str,
    model_fn: Callable[[np.ndarray, np.ndarray, np.ndarray, np.ndarray], Dict[str, Any]],
    config: Optional[CPCVConfig] = None,
    model_name: str = "lightgbm_scorer",
    model_version: str = "v1",
) -> CPCVResult:
    """Run full CPCV validation pipeline.
    執行完整 CPCV 驗證管線。

    Args:
        X: Feature matrix (n_samples, n_features). / 特徵矩陣。
        y: Target array (n_samples,). / 目標陣列。
        timestamps: Sorted epoch timestamps (n_samples,). / 排序的時間戳。
        strategy_type: Strategy name or category. / 策略名稱或類別。
        model_fn: Callable(X_train, y_train, X_test, y_test) → dict with metrics.
            Must return dict containing at least 'sharpe'. May also include
            'rmse', 'correlation', etc.
            必須返回包含 'sharpe' 的字典。
        config: CPCV configuration. / CPCV 配置。
        model_name: Model identifier for DB persistence. / 模型標識符，用於 DB 持久化。
        model_version: Model version for DB persistence. / 模型版本，用於 DB 持久化。

    Returns:
        CPCVResult with aggregated metrics and pass/fail decision.
        包含聚合指標和通過/失敗決策的結果。
    """
    if np is None:
        raise ImportError("numpy is required for CPCV / numpy 為 CPCV 必需依賴")

    if config is None:
        config = CPCVConfig()

    embargo_hours = get_embargo_hours(strategy_type, config)
    folds = generate_folds(timestamps, strategy_type, config)

    fold_metrics: List[Dict[str, Any]] = []
    sharpe_values: List[float] = []

    for fold_idx, (train_idx, test_idx) in enumerate(folds):
        X_train, y_train = X[train_idx], y[train_idx]
        X_test, y_test = X[test_idx], y[test_idx]

        metrics = model_fn(X_train, y_train, X_test, y_test)
        metrics["fold"] = fold_idx
        metrics["n_train"] = len(train_idx)
        metrics["n_test"] = len(test_idx)
        fold_metrics.append(metrics)

        sharpe_values.append(float(metrics.get("sharpe", 0.0)))

    mean_sharpe = float(np.mean(sharpe_values)) if sharpe_values else 0.0
    std_sharpe = float(np.std(sharpe_values)) if sharpe_values else 0.0

    power = estimate_power(len(y), config.n_folds)

    # Pass only if sufficient power AND positive mean Sharpe
    # 只有功效足夠且平均 Sharpe 為正才通過
    passed = (power >= config.power_threshold) and (mean_sharpe > 0)

    if power < config.power_threshold:
        logger.warning(
            "CPCV power < %.2f: results are reference-only "
            "(power=%.3f, n_samples=%d, n_folds=%d)",
            config.power_threshold,
            power,
            len(y),
            config.n_folds,
        )

    result = CPCVResult(
        fold_metrics=fold_metrics,
        mean_sharpe=mean_sharpe,
        std_sharpe=std_sharpe,
        power_estimate=power,
        passed=passed,
        n_folds=config.n_folds,
        embargo_hours=embargo_hours,
        strategy_type=strategy_type,
    )

    # Persist to PG (fail-soft) / 持久化到 PG（失敗不中斷）
    _persist_cpcv_result(result, model_name=model_name, model_version=model_version)

    return result


def _persist_cpcv_result(result: CPCVResult, model_name: str = "lightgbm_scorer", model_version: str = "v1") -> bool:
    """Write CPCV result to learning.cpcv_results. Fail-soft.
    將 CPCV 結果寫入 learning.cpcv_results。失敗不中斷。
    """
    try:
        import psycopg2
    except ImportError:
        return False

    dsn = os.environ.get("OPENCLAW_PG_DSN") or os.environ.get("PG_DSN")
    try:
        if dsn:
            conn = psycopg2.connect(dsn)
        else:
            conn = psycopg2.connect(
                host=os.getenv("PG_HOST", "127.0.0.1"),
                port=int(os.getenv("PG_PORT", "5432")),
                user=os.getenv("PG_USER", "trading_admin"),
                password=os.getenv("PG_PASS", ""),
                dbname=os.getenv("PG_DB", "trading_ai"),
                connect_timeout=5,
            )
    except Exception as e:
        logger.warning("CPCV PG connection failed (non-fatal): %s / CPCV PG 連接失敗（非致命）：%s", e, e)
        return False

    try:
        # Compute mean_accuracy from fold_metrics if available
        # 從 fold_metrics 計算 mean_accuracy（如有）
        accuracies = [
            fm.get("accuracy") for fm in result.fold_metrics
            if fm.get("accuracy") is not None
        ]
        mean_accuracy = float(np.mean(accuracies)) if accuracies and np is not None else None

        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO learning.cpcv_results
                    (model_name, model_version, n_folds, embargo_hours, strategy_type,
                     fold_metrics, mean_sharpe, std_sharpe, mean_accuracy, power_estimate, passed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    model_name, model_version, result.n_folds, result.embargo_hours,
                    result.strategy_type, json.dumps(result.fold_metrics),
                    result.mean_sharpe, result.std_sharpe, mean_accuracy,
                    result.power_estimate, result.passed,
                ),
            )
        conn.commit()
        logger.info("Persisted CPCV result: passed=%s sharpe=%.4f / 已持久化 CPCV 結果", result.passed, result.mean_sharpe)
        return True
    except Exception as e:
        logger.warning("Failed to persist CPCV result (non-fatal): %s / 持久化 CPCV 結果失敗（非致命）：%s", e, e)
        return False
    finally:
        conn.close()

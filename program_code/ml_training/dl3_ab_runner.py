"""DL-3 A/B Runner — compare Phase 3 Scorer baseline vs Scorer + DL-3 features.

DL-3 A/B 跑批 — 對比 Phase 3 Scorer baseline 與 Scorer + DL-3 特徵。

MODULE_NOTE (EN):
    Runs two parallel Scorer training pipelines on the same dataset:
    A) baseline: Phase 3b features only (Phase 3b IndicatorSnapshot columns)
    B) baseline + DL-3 forecast features (chronos/timesfm pred_mean / pred_std)

    Compares ROC-AUC and Brier score on a held-out time-ordered split. If AUC
    delta < auc_delta_threshold (default 0.01), marks DL-3 as DEPRECATE.
    Otherwise marks as PROMOTE_PENDING for AI-E final review (4-13).

    Fail-soft contract:
    - sklearn / pandas / numpy missing -> INSUFFICIENT_DATA, never raises.
    - dsn None or fetch failure -> INSUFFICIENT_DATA, never raises.
    - DB write failure -> warn + continue.
    - Any exception in run_ab_test -> caught + AbResult(decision="INSUFFICIENT_DATA").

MODULE_NOTE (中):
    在同一資料集上跑兩個 Scorer 訓練管線：
    A) baseline：只用 Phase 3b 34-dim IndicatorSnapshot 欄位
    B) baseline + DL-3 預測特徵（chronos/timesfm pred_mean / pred_std）

    在時間排序的 held-out split 比較 ROC-AUC 與 Brier score。AUC delta < 閾值
    （預設 0.01）→ DEPRECATE；否則 PROMOTE_PENDING 等 AI-E 簽核（4-13）。

    Fail-soft 合約：
    - sklearn / pandas / numpy 缺失 → INSUFFICIENT_DATA，永不 raise。
    - dsn 為 None 或 fetch 失敗 → INSUFFICIENT_DATA，永不 raise。
    - DB 寫入失敗 → warn + 繼續。
    - run_ab_test 內任何例外 → 接住 + AbResult(decision="INSUFFICIENT_DATA")。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy imports — none of these are required at import time. fail-soft.
# 延遲匯入 — 全部非匯入時必需，fail-soft。
# ---------------------------------------------------------------------------


def _try_import_numpy():
    """Lazy numpy import. None on failure. / 延遲 numpy 匯入；失敗回 None。"""
    try:
        import numpy as np  # type: ignore

        return np
    except ImportError:
        return None


def _try_import_sklearn():
    """Lazy sklearn import. Returns (LogisticRegression, roc_auc_score, brier_score_loss) or None.
    延遲 sklearn 匯入。返回三個 callable 或 None。
    """
    try:
        from sklearn.linear_model import LogisticRegression  # type: ignore
        from sklearn.metrics import brier_score_loss, roc_auc_score  # type: ignore

        return LogisticRegression, roc_auc_score, brier_score_loss
    except ImportError:
        return None


def _try_import_psycopg2():
    """Lazy psycopg2 import. None on failure. / 延遲 psycopg2 匯入；失敗回 None。"""
    try:
        import psycopg2  # type: ignore

        return psycopg2
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Config + Result dataclasses / 配置 + 結果
# ---------------------------------------------------------------------------


@dataclass
class Dl3AbConfig:
    """Configuration for DL-3 A/B run.
    DL-3 A/B 跑批配置。
    """

    auc_delta_threshold: float = 0.01  # spec: < this -> DEPRECATE
    cpcv_n_folds: int = 4  # 對齊 Phase 3b
    cpcv_embargo_hours: int = 24  # 對齊 Phase 3b trending
    min_samples: int = 100  # below this -> INSUFFICIENT_DATA
    held_out_fraction: float = 0.2  # tail fraction reserved for test
    feature_columns_baseline: list[str] = field(default_factory=list)
    feature_columns_dl3: list[str] = field(default_factory=list)


@dataclass
class AbResult:
    """Outcome of an A/B run. / A/B 跑批結果。"""

    baseline_auc: float
    augmented_auc: float
    baseline_brier: float
    augmented_brier: float
    auc_delta: float
    decision: str  # 'DEPRECATE' / 'PROMOTE_PENDING' / 'INSUFFICIENT_DATA' / 'INCONCLUSIVE'
    n_samples: int
    notes: str = ""

    @classmethod
    def insufficient(cls, reason: str, n_samples: int = 0) -> "AbResult":
        """Build a fail-soft INSUFFICIENT_DATA result. / 建構 fail-soft 結果。"""
        return cls(
            baseline_auc=0.0,
            augmented_auc=0.0,
            baseline_brier=0.0,
            augmented_brier=0.0,
            auc_delta=0.0,
            decision="INSUFFICIENT_DATA",
            n_samples=n_samples,
            notes=reason,
        )


# ---------------------------------------------------------------------------
# Decision logic / 決策邏輯
# ---------------------------------------------------------------------------


def decide(
    baseline_auc: float,
    augmented_auc: float,
    baseline_brier: float,
    augmented_brier: float,
    n_samples: int,
    cfg: Dl3AbConfig,
) -> str:
    """Pure decision function — easy to unit test.
    純決策函數 — 方便單元測試。

    Decision matrix:
    - n_samples < min_samples            -> INSUFFICIENT_DATA
    - delta < auc_delta_threshold        -> DEPRECATE
    - delta >= threshold AND brier improved -> PROMOTE_PENDING
    - else                               -> INCONCLUSIVE
    """
    if n_samples < cfg.min_samples:
        return "INSUFFICIENT_DATA"
    delta = augmented_auc - baseline_auc
    if delta < cfg.auc_delta_threshold:
        return "DEPRECATE"
    if augmented_brier <= baseline_brier:
        return "PROMOTE_PENDING"
    return "INCONCLUSIVE"


# ---------------------------------------------------------------------------
# Metric helper / 評估輔助
# ---------------------------------------------------------------------------


def evaluate_auc_brier(
    y_true: list[float], y_pred_proba: list[float]
) -> tuple[float, float]:
    """Compute (roc_auc, brier_score) for given labels and predicted probabilities.
    計算 (ROC-AUC, Brier score)。

    Fail-soft: returns (0.0, 1.0) if sklearn missing or evaluation raises.
    Fail-soft：sklearn 缺失或計算失敗時返回 (0.0, 1.0)。
    """
    sk = _try_import_sklearn()
    if sk is None:
        logger.warning("dl3_ab: sklearn unavailable, returning fail-soft metrics")
        return (0.0, 1.0)
    _, roc_auc_score, brier_score_loss = sk
    try:
        auc = float(roc_auc_score(y_true, y_pred_proba))
        brier = float(brier_score_loss(y_true, y_pred_proba))
        return (auc, brier)
    except Exception as e:
        logger.warning("dl3_ab: AUC/Brier evaluation failed: %s", e)
        return (0.0, 1.0)


# ---------------------------------------------------------------------------
# Training (simple LogisticRegression) / 訓練
# ---------------------------------------------------------------------------


def _train_simple_lr(X_train, y_train) -> Optional[Any]:
    """Train a small LogisticRegression on (X_train, y_train).
    在 (X_train, y_train) 上訓練小型 LogisticRegression。

    Returns the fitted model or None if sklearn missing / fit fails.
    返回擬合後的模型；sklearn 缺失或 fit 失敗時返回 None。
    """
    sk = _try_import_sklearn()
    if sk is None:
        return None
    LogisticRegression, _, _ = sk
    try:
        model = LogisticRegression(max_iter=200, solver="lbfgs")
        model.fit(X_train, y_train)
        return model
    except Exception as e:
        logger.warning("dl3_ab: LogisticRegression fit failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Data fetch (PG) / 資料拉取
# ---------------------------------------------------------------------------


def fetch_training_dataset(
    dsn: Optional[str],
    since_ts_ms: int,
    until_ts_ms: int,
    cfg: Dl3AbConfig,
) -> Optional[Any]:
    """Pull a (features + dl3_features + label) DataFrame from PG.

    從 PG 拉 (features + dl3_features + label) DataFrame。

    Schema assumption (documented inline; revisit when wiring real Scorer):
    JOIN trading.fills f
      ON f.context_id = c.context_id
     AND (f.strategy_name IS NULL OR f.strategy_name NOT LIKE 'unattributed:%%')
        -- F4-2 (2026-04-26): future wiring MUST keep this filter; otherwise
        -- Bybit auto-action audit rows pollute supervised labels.
        -- F4-2（2026-04-26）：未來實作必保留此過濾，否則 audit row 污染標籤。
    LEFT JOIN learning.foundation_model_features fm
      ON fm.symbol = c.symbol AND fm.time = c.time
    WHERE c.time BETWEEN since AND until

    label = (f.realized_pnl > 0)
    baseline_features = c.indicators_snapshot JSONB columns (subset)
    dl3_features = fm.forecast JSONB pred_mean / pred_std

    Fail-soft: returns None on dsn=None / psycopg2 missing / fetch failure.
    Fail-soft：dsn=None / psycopg2 缺失 / fetch 失敗時返回 None。
    """
    if dsn is None:
        logger.info("dl3_ab: dsn=None, skipping data fetch (test/dry-run mode)")
        return None
    psycopg2 = _try_import_psycopg2()
    if psycopg2 is None:
        logger.warning("dl3_ab: psycopg2 unavailable, cannot fetch dataset")
        return None
    try:
        # Real implementation deferred — query is documented above; the wiring
        # task (4-13 / wiring sweep) will fill this in once Scorer column
        # selection is finalized. For now this returns None so callers degrade
        # gracefully to INSUFFICIENT_DATA.
        # 真實實作延後 — query 已在上方文件化。wiring 階段（4-13 / wiring sweep）
        # 會在 Scorer 欄位選定後填入。當前回 None 使 caller 優雅降級。
        logger.info(
            "dl3_ab: fetch_training_dataset stub (rows %d→%d) — awaiting Scorer column finalization",
            since_ts_ms,
            until_ts_ms,
        )
        return None
    except Exception as e:
        logger.warning("dl3_ab: fetch_training_dataset failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# Main entry / 主入口
# ---------------------------------------------------------------------------


def run_ab_test(
    cfg: Dl3AbConfig,
    dsn: Optional[str] = None,
    since_ts_ms: int = 0,
    until_ts_ms: int = 0,
    _injected_dataset: Optional[Any] = None,
) -> AbResult:
    """Main A/B entry point. Always returns an AbResult; never raises.

    主 A/B 入口。永遠回傳 AbResult；絕不 raise。

    Pipeline:
        1) fetch dataset (or use _injected_dataset for tests)
        2) sklearn lazy import — fail-soft INSUFFICIENT_DATA if missing
        3) split time-ordered (last `held_out_fraction` for test)
        4) train baseline LR on baseline_features only
        5) train augmented LR on baseline + dl3 features
        6) evaluate AUC + Brier on held-out
        7) call decide() and return AbResult
    """
    try:
        np = _try_import_numpy()
        if np is None:
            return AbResult.insufficient("numpy unavailable")

        sk = _try_import_sklearn()
        if sk is None:
            return AbResult.insufficient("sklearn unavailable")

        # Step 1: dataset
        # 第 1 步：取資料集
        df = (
            _injected_dataset
            if _injected_dataset is not None
            else fetch_training_dataset(dsn, since_ts_ms, until_ts_ms, cfg)
        )
        if df is None:
            return AbResult.insufficient("dataset fetch returned None")

        # df is expected to be a numpy structured tuple OR a dict with keys
        # X_baseline, X_augmented, y. Tests inject this directly.
        # df 預期為 numpy 結構或 dict（X_baseline / X_augmented / y）。測試直接注入。
        X_baseline = df.get("X_baseline") if isinstance(df, dict) else None
        X_augmented = df.get("X_augmented") if isinstance(df, dict) else None
        y = df.get("y") if isinstance(df, dict) else None
        if X_baseline is None or X_augmented is None or y is None:
            return AbResult.insufficient("dataset missing required keys")

        n = len(y)
        if n < cfg.min_samples:
            return AbResult.insufficient(
                f"samples {n} < min {cfg.min_samples}", n_samples=n
            )

        # Step 3: time-ordered split
        # 第 3 步：時間順序切分
        split = max(1, int(n * (1.0 - cfg.held_out_fraction)))
        X_b_tr, X_b_te = X_baseline[:split], X_baseline[split:]
        X_a_tr, X_a_te = X_augmented[:split], X_augmented[split:]
        y_tr, y_te = y[:split], y[split:]

        if len(set(y_tr)) < 2 or len(set(y_te)) < 2:
            return AbResult.insufficient(
                "single-class split (cannot compute AUC)", n_samples=n
            )

        # Step 4-5: train both models
        # 第 4-5 步：訓練兩個模型
        m_baseline = _train_simple_lr(X_b_tr, y_tr)
        m_augmented = _train_simple_lr(X_a_tr, y_tr)
        if m_baseline is None or m_augmented is None:
            return AbResult.insufficient("model fit failed", n_samples=n)

        # Step 6: evaluate
        # 第 6 步：評估
        try:
            y_b_proba = m_baseline.predict_proba(X_b_te)[:, 1]
            y_a_proba = m_augmented.predict_proba(X_a_te)[:, 1]
        except Exception as e:
            return AbResult.insufficient(f"predict_proba failed: {e}", n_samples=n)

        baseline_auc, baseline_brier = evaluate_auc_brier(list(y_te), list(y_b_proba))
        augmented_auc, augmented_brier = evaluate_auc_brier(
            list(y_te), list(y_a_proba)
        )

        # Step 7: decide
        # 第 7 步：決策
        decision = decide(
            baseline_auc=baseline_auc,
            augmented_auc=augmented_auc,
            baseline_brier=baseline_brier,
            augmented_brier=augmented_brier,
            n_samples=n,
            cfg=cfg,
        )
        return AbResult(
            baseline_auc=baseline_auc,
            augmented_auc=augmented_auc,
            baseline_brier=baseline_brier,
            augmented_brier=augmented_brier,
            auc_delta=augmented_auc - baseline_auc,
            decision=decision,
            n_samples=n,
        )
    except Exception as e:
        logger.warning("dl3_ab: run_ab_test caught unexpected exception: %s", e)
        return AbResult.insufficient(f"unexpected: {e}")


# ---------------------------------------------------------------------------
# Persistence / 持久化
# ---------------------------------------------------------------------------


def persist_decision(dsn: Optional[str], result: AbResult) -> bool:
    """Write decision audit row to learning.dl3_ab_decisions.

    寫入決策審計列到 learning.dl3_ab_decisions。

    Returns True on success. Fail-soft: returns False (and logs warning) when
    dsn missing, psycopg2 missing, table missing, or write fails. Never raises.

    返回 True 表示成功。fail-soft：dsn 缺失/psycopg2 缺失/table 缺失/寫入失敗時
    回 False（並 log warning）。永不 raise。
    """
    if dsn is None:
        logger.info("dl3_ab: persist_decision skipped (dsn=None)")
        return False
    psycopg2 = _try_import_psycopg2()
    if psycopg2 is None:
        logger.warning("dl3_ab: psycopg2 unavailable, persist_decision skipped")
        return False
    try:
        conn = psycopg2.connect(dsn)
        try:
            with conn.cursor() as cur:
                # Check if table exists; if not, skip silently (4-13 may add DDL).
                # 檢查表是否存在；不存在時靜默跳過（4-13 可能補 DDL）。
                cur.execute(
                    """
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'learning' AND table_name = 'dl3_ab_decisions'
                    LIMIT 1
                    """
                )
                if cur.fetchone() is None:
                    logger.info(
                        "dl3_ab: learning.dl3_ab_decisions table missing — skipping persist"
                    )
                    return False
                cur.execute(
                    """
                    INSERT INTO learning.dl3_ab_decisions
                        (decided_at, decision, baseline_auc, augmented_auc,
                         baseline_brier, augmented_brier, auc_delta,
                         n_samples, notes)
                    VALUES (NOW(), %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        result.decision,
                        result.baseline_auc,
                        result.augmented_auc,
                        result.baseline_brier,
                        result.augmented_brier,
                        result.auc_delta,
                        result.n_samples,
                        result.notes,
                    ),
                )
                conn.commit()
                return True
        finally:
            conn.close()
    except Exception as e:
        logger.warning("dl3_ab: persist_decision failed: %s", e)
        return False

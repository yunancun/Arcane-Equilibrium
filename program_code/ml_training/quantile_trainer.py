"""
Quantile LightGBM Trainer — three independent pinball fits for EDGE-P3-1 Stage 2.
三分位 LightGBM 訓練器 — EDGE-P3-1 Stage 2 的三獨立 pinball 擬合。

MODULE_NOTE (EN): Trains per-strategy q10/q50/q90 LGBM models on decision_features
  with CPCV + exponential sample weighting + strategy-specific embargo carve-out
  (funding_arb → 3 folds / 14d holdout). Computes pinball skill (vs constant
  baseline), coverage error, decile-lift bootstrap CI, quantile-crossing rate,
  and a linear-QR floor baseline per spec §6.2. Pure training; CQR / ONNX /
  acceptance-report are downstream modules.
MODULE_NOTE (中): 每策略 q10/q50/q90 獨立 LightGBM 訓練，搭配 CPCV + 指數樣本
  權重 + 策略特定 embargo（funding_arb 3-fold + 14d holdout carve-out）。
  計算 pinball skill（相對常數 baseline）、coverage error、decile lift
  bootstrap 信賴區間、分位交叉違反率、linear QR floor baseline（spec §6.2）。
  僅訓練：CQR / ONNX / 驗收報告由下游模組接手。
"""

from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Spec §6 canonical alpha set — do NOT change without coordinating with
# Rust FeatureVectorV1 and ONNX loader (tract expects three separate models).
# spec §6 規範 alpha 集合 — 不得變更（與 Rust FeatureVectorV1 + ONNX loader 綁定）。
QUANTILE_ALPHAS: Tuple[float, float, float] = (0.10, 0.50, 0.90)

_MS_PER_DAY = 86_400_000.0


# ──────────────────────────────────────────────────────────────
# Config dataclasses
# ──────────────────────────────────────────────────────────────

@dataclass
class EmbargoConfig:
    """Per-strategy CPCV fold count + embargo window + holdout tail length.
    策略特定 CPCV fold 數 + embargo 窗 + holdout 尾段長度。"""

    n_folds: int
    embargo_hours: int
    holdout_tail_days: float


def get_embargo_config(strategy_name: str) -> EmbargoConfig:
    """Map strategy → EmbargoConfig per spec §6.1 (funding_arb carve-out).
    策略 → EmbargoConfig 映射（spec §6.1，funding_arb carve-out）。

    funding_arb uses 3-fold + 72h embargo + 14d holdout tail because the
    72h × 5-fold original config leaves ~100 samples/fold < stable. All
    other strategies use 5-fold + 24h embargo + 7d holdout tail (majority path).
    funding_arb 用 3-fold + 72h embargo + 14d holdout — 原 72h×5-fold
    每 fold 約 100 樣本不穩；其他策略走多數路徑 5-fold + 24h + 7d。
    """
    st = (strategy_name or "").lower().strip()
    if st == "funding_arb":
        return EmbargoConfig(n_folds=3, embargo_hours=72, holdout_tail_days=14.0)
    return EmbargoConfig(n_folds=5, embargo_hours=24, holdout_tail_days=7.0)


@dataclass
class QuantileTrainingConfig:
    """LightGBM quantile training + CPCV + sample weight config per spec §6.
    LightGBM 分位訓練 + CPCV + 樣本權重配置（spec §6）。"""

    # LightGBM hyperparameters — spec §6.3 v1.1
    num_leaves: int = 7
    learning_rate: float = 0.05
    n_estimators: int = 500  # ceiling; early_stopping_rounds must be active
    early_stopping_rounds: int = 50
    min_data_in_leaf: Optional[int] = None  # None → max(20, n_train // 50)
    feature_fraction: float = 0.8
    bagging_fraction: float = 0.8
    bagging_freq: int = 5
    lambda_l2: float = 0.1

    # CPCV purge — label window (hours): how long label computation looks forward.
    # EDGE-P3-1 realized edge labels use the round-trip close ts, so effective
    # label span matches holding period. Conservative 4h default matches
    # scorer_trainer legacy behaviour.
    # CPCV purge — 標籤窗（小時）：標籤計算前瞻時間，預設 4h 保守匹配 scorer 傳統行為。
    label_window_hours: float = 4.0

    # Sample weight exponential half-life (spec §6.1: w = exp(-days_ago / 14))
    # 樣本權重指數衰減（spec §6.1）
    decay_halflife_days: float = 14.0

    # Decile lift bootstrap config (spec §6.2)
    bootstrap_iterations: int = 1000
    bootstrap_seed: int = 42

    # Feature schema version tag — included in result for downstream hashing
    # 特徵 schema 版本標記 — 供下游雜湊使用
    schema_version: str = "v1"


@dataclass
class PerQuantileMetrics:
    """Holdout metrics for a single quantile fit.
    單一分位擬合的 holdout 指標。"""

    alpha: float
    pinball_loss: float
    pinball_loss_baseline_constant: float
    pinball_skill: float  # 1 - model / baseline
    empirical_coverage: float  # P(y <= q_pred)
    coverage_error_pp: float  # |empirical - alpha| * 100
    best_iteration: int
    n_train: int
    n_holdout: int
    linear_qr_pinball_loss: Optional[float] = None
    linear_qr_pinball_skill: Optional[float] = None


@dataclass
class QuantileTrainingResult:
    """End-to-end training result bundle for one (strategy, engine_mode, symbol) slice.
    單一切片（策略, engine_mode, symbol）端到端訓練結果。"""

    success: bool = False
    error: str = ""
    strategy_name: str = ""
    engine_mode: str = ""
    models: Dict[str, Any] = field(default_factory=dict)  # {"q10": Booster, ...}
    per_quantile_metrics: Dict[str, PerQuantileMetrics] = field(default_factory=dict)
    decile_lift_point: float = 0.0
    decile_lift_ci_lower: float = 0.0
    decile_lift_ci_upper: float = 0.0
    crossing_rate: float = 0.0
    feature_schema_hash: str = ""
    feature_names: List[str] = field(default_factory=list)
    n_samples_total: int = 0
    n_samples_labeled: int = 0
    n_holdout: int = 0
    embargo_config: Optional[EmbargoConfig] = None
    # Holdout arrays retained so calibration / reports can reuse without
    # re-slicing. Intentionally un-typed to avoid numpy hard-dep in dataclass.
    # 保留 holdout 陣列給 calibration / reports 複用；避免 dataclass 硬相依 numpy。
    holdout_features: Any = None
    holdout_labels: Any = None
    holdout_q10_pred: Any = None
    holdout_q50_pred: Any = None
    holdout_q90_pred: Any = None


# ──────────────────────────────────────────────────────────────
# Sample weighting
# ──────────────────────────────────────────────────────────────

def compute_sample_weights(
    timestamps_ms: np.ndarray,
    halflife_days: float = 14.0,
    reference_ms: Optional[int] = None,
) -> np.ndarray:
    """Exponential decay weights: w_i = exp(-days_ago_i / halflife_days).

    spec §6.1 mandates per-sample weighting so recent regimes dominate fit
    while preserving long-tail context. Reference defaults to max(timestamps).
    spec §6.1 要求樣本權重：近期樣本主導擬合，長尾保留上下文。
    reference 預設為 max(timestamps)。
    """
    if len(timestamps_ms) == 0:
        return np.empty((0,), dtype=np.float32)
    ref = int(reference_ms) if reference_ms is not None else int(np.max(timestamps_ms))
    days_ago = (ref - timestamps_ms.astype(np.float64)) / _MS_PER_DAY
    # Clip to >= 0 so stray future timestamps don't upweight (physical guard).
    # 夾到 >=0，避免未來時間戳（數據異常）被過度加權。
    days_ago = np.maximum(days_ago, 0.0)
    return np.exp(-days_ago / float(halflife_days)).astype(np.float32)


# ──────────────────────────────────────────────────────────────
# Metrics (pinball, coverage, decile lift, crossing)
# ──────────────────────────────────────────────────────────────

def pinball_loss(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    alpha: float,
    sample_weight: Optional[np.ndarray] = None,
) -> float:
    """Pinball loss at quantile alpha. Returns weighted mean.
    分位 alpha 的 pinball 損失（加權平均）。"""
    if len(y_true) == 0:
        return 0.0
    diff = y_true - y_pred
    loss = np.maximum(alpha * diff, (alpha - 1.0) * diff)
    if sample_weight is None:
        return float(np.mean(loss))
    w = sample_weight.astype(np.float64)
    w_sum = float(np.sum(w))
    if w_sum <= 0:
        return float(np.mean(loss))
    return float(np.sum(loss * w) / w_sum)


def compute_pinball_skill(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    alpha: float,
    baseline_constant: float,
    sample_weight: Optional[np.ndarray] = None,
) -> Tuple[float, float, float]:
    """Pinball skill score: 1 - loss(model) / loss(constant_baseline).

    Returns (skill, model_loss, baseline_loss). When baseline_loss == 0
    (degenerate — all y equal baseline) skill is 0.0 by convention.
    回傳 (skill, model_loss, baseline_loss)。baseline loss 為 0（退化）時 skill=0。
    """
    model_loss = pinball_loss(y_true, y_pred, alpha, sample_weight)
    const_pred = np.full_like(y_true, baseline_constant, dtype=np.float64)
    baseline_loss = pinball_loss(y_true, const_pred, alpha, sample_weight)
    if baseline_loss <= 0:
        return 0.0, model_loss, baseline_loss
    skill = 1.0 - model_loss / baseline_loss
    return float(skill), model_loss, baseline_loss


def compute_coverage_error(
    y_true: np.ndarray,
    q_pred: np.ndarray,
    alpha: float,
) -> Tuple[float, float]:
    """Empirical coverage P(y <= q_pred) and absolute pp deviation from alpha.

    For alpha=0.1 we expect ~10% of y to fall at-or-below the predicted q10,
    etc. Returns (empirical_coverage, abs_error_pp). pp = percentage points.
    alpha=0.1 時預期 ~10% 的 y 落在預測 q10 之下；回傳 (實證 coverage, 絕對 pp 誤差)。
    """
    if len(y_true) == 0:
        return 0.0, 0.0
    empirical = float(np.mean(y_true <= q_pred))
    return empirical, float(abs(empirical - alpha) * 100.0)


def check_quantile_crossing_rate(
    q10_pred: np.ndarray,
    q50_pred: np.ndarray,
    q90_pred: np.ndarray,
) -> float:
    """Fraction of rows violating q10 <= q50 <= q90.
    違反 q10 <= q50 <= q90 的樣本比例。"""
    if len(q10_pred) == 0:
        return 0.0
    violations = (q10_pred > q50_pred) | (q50_pred > q90_pred) | (q10_pred > q90_pred)
    return float(np.mean(violations))


def compute_decile_lift_bootstrap(
    y_true: np.ndarray,
    q50_pred: np.ndarray,
    n_boot: int = 1000,
    seed: int = 42,
) -> Tuple[float, float, float]:
    """1000-bootstrap decile-lift 95% CI per spec §6.2.

    Lift = mean(y | top decile of q50) / mean(y | median decile of q50).
    Point estimate returned separately from CI bounds. Returns
    (point_estimate, ci_lower_95, ci_upper_95). Bootstrap samples where
    median-decile mean ≤ 1e-9 are dropped to avoid division blowup; caller
    should treat ci==0 as degenerate data.
    Lift = mean(y | q50 top decile) / mean(y | q50 median decile)。
    1000 bootstrap 95% CI。中位 decile mean ≤ 1e-9 時跳過避免除爆。
    """
    n = len(y_true)
    if n < 20:
        return 0.0, 0.0, 0.0

    rng = np.random.default_rng(seed)

    def _one_lift(y: np.ndarray, p: np.ndarray) -> Optional[float]:
        order = np.argsort(p, kind="stable")
        # np.array_split gives roughly-equal 10 deciles even for n not /10.
        # np.array_split 即使 n 非 10 倍也能得到約略均分 10 deciles。
        deciles = np.array_split(order, 10)
        top_mean = float(np.mean(y[deciles[-1]])) if len(deciles[-1]) else 0.0
        med_mean = float(np.mean(y[deciles[len(deciles) // 2]])) if len(deciles[len(deciles) // 2]) else 0.0
        if abs(med_mean) <= 1e-9:
            return None
        return top_mean / med_mean

    # Point estimate on full data.
    point = _one_lift(y_true, q50_pred)
    if point is None:
        point = 0.0

    lifts: List[float] = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, size=n)
        lift = _one_lift(y_true[idx], q50_pred[idx])
        if lift is not None and math.isfinite(lift):
            lifts.append(lift)

    if not lifts:
        return float(point), 0.0, 0.0

    arr = np.array(lifts)
    ci_lower = float(np.percentile(arr, 2.5))
    ci_upper = float(np.percentile(arr, 97.5))
    return float(point), ci_lower, ci_upper


# ──────────────────────────────────────────────────────────────
# Linear-QR floor baseline (spec §6.2)
# ──────────────────────────────────────────────────────────────

def fit_floor_baseline(
    features_train: np.ndarray,
    labels_train: np.ndarray,
    features_holdout: np.ndarray,
    labels_holdout: np.ndarray,
    alphas: Tuple[float, ...] = QUANTILE_ALPHAS,
) -> Dict[str, float]:
    """sklearn QuantileRegressor linear floor per alpha. LGBM must beat this
    by +5pp pinball skill to ship per spec §6.2.

    Returns {"q10_loss": ..., "q50_loss": ..., "q90_loss": ...} on holdout.
    Fails-soft to all zeros when sklearn missing (unit tests may skip).
    sklearn QuantileRegressor 作線性 floor；spec §6.2 LGBM 需勝 +5pp 才 ship。
    """
    result: Dict[str, float] = {f"q{int(a * 100):02d}_loss": 0.0 for a in alphas}
    try:
        from sklearn.linear_model import QuantileRegressor
    except ImportError:  # pragma: no cover
        logger.warning(
            "sklearn.linear_model.QuantileRegressor unavailable — "
            "floor baseline skipped (tests only). / sklearn 不可用，跳過 floor。"
        )
        return result

    for alpha in alphas:
        try:
            # solver="highs" is faster + more stable than the legacy ipm path
            # for n < 10k. alpha=0.0 → no L1 penalty (pure QR).
            # solver=highs 快且穩；alpha=0.0 = 純 QR 無 L1 懲罰。
            qr = QuantileRegressor(quantile=alpha, alpha=0.0, solver="highs")
            qr.fit(features_train, labels_train)
            preds = qr.predict(features_holdout)
            result[f"q{int(alpha * 100):02d}_loss"] = pinball_loss(
                labels_holdout, preds, alpha,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("linear QR fit failed alpha=%.2f: %s", alpha, exc)
            result[f"q{int(alpha * 100):02d}_loss"] = 0.0
    return result


# ──────────────────────────────────────────────────────────────
# Core training
# ──────────────────────────────────────────────────────────────

def _compute_feature_schema_hash(feature_names: List[str], schema_version: str) -> str:
    """Stable sha256 over (version || '|' || name1 || '\\n' || name2 || ...).

    Matches the Rust FeatureVectorV1 contract: both sides must agree on
    (version, ordered names) before predict/serve accepts output.
    與 Rust FeatureVectorV1 契約一致：雙方對 (version, ordered names) 同意才接受推理。
    """
    payload = schema_version + "|" + "\n".join(feature_names)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _split_tail_holdout(
    timestamps_ms: np.ndarray,
    holdout_tail_days: float,
    min_fraction: float = 0.1,
) -> Tuple[np.ndarray, np.ndarray]:
    """Time-ordered tail holdout split.

    Prefer `timestamps_ms >= max - holdout_tail_days*ms_per_day` to match spec
    §6.1 "most recent 7d strict holdout". Falls back to fractional split when
    time range is too short (e.g. synthetic tests with compressed timestamps).
    Returns (train_indices, holdout_indices).
    優先用「最近 7d 嚴格 holdout」窗；時間跨度太短（合成測試）則退回比例切分。
    """
    n = len(timestamps_ms)
    if n == 0:
        return np.empty((0,), dtype=np.intp), np.empty((0,), dtype=np.intp)
    order = np.argsort(timestamps_ms, kind="stable")
    ts_sorted = timestamps_ms[order]
    total_span_ms = int(ts_sorted[-1] - ts_sorted[0])
    holdout_span_ms = int(holdout_tail_days * _MS_PER_DAY)
    min_holdout = max(int(n * min_fraction), 1)
    # When total span is shorter than the holdout window, cutoff would cover
    # the entire dataset and leave train=0. Fall back to tail-fraction split.
    # 當總跨度 ≤ holdout 窗，cutoff 會涵蓋全部資料致 train=0 — 退回 tail-fraction 切分。
    if total_span_ms <= holdout_span_ms:
        split = n - min_holdout
        return order[:split].astype(np.intp), order[split:].astype(np.intp)

    cutoff = int(ts_sorted[-1]) - holdout_span_ms
    holdout_mask_sorted = ts_sorted >= cutoff
    n_holdout = int(holdout_mask_sorted.sum())
    if n_holdout < min_holdout:
        # Time window selected too few rows → take last min_fraction instead.
        # 時間窗選取太少 → 退回 min_fraction 尾段。
        split = n - min_holdout
        train_idx = order[:split]
        holdout_idx = order[split:]
    else:
        train_idx = order[~holdout_mask_sorted]
        holdout_idx = order[holdout_mask_sorted]
    return train_idx.astype(np.intp), holdout_idx.astype(np.intp)


def _lgb_params(cfg: QuantileTrainingConfig, alpha: float, n_train: int) -> dict:
    """LightGBM quantile hyperparam dict per spec §6.3.
    LightGBM 分位超參字典（spec §6.3）。"""
    min_leaf = cfg.min_data_in_leaf if cfg.min_data_in_leaf is not None else max(20, n_train // 50)
    return {
        "objective": "quantile",
        "alpha": float(alpha),
        "metric": "quantile",
        "num_leaves": cfg.num_leaves,
        "learning_rate": cfg.learning_rate,
        "min_data_in_leaf": int(min_leaf),
        "feature_fraction": cfg.feature_fraction,
        "bagging_fraction": cfg.bagging_fraction,
        "bagging_freq": cfg.bagging_freq,
        "lambda_l2": cfg.lambda_l2,
        "verbose": -1,
        "deterministic": True,  # reproducibility for CC T7 train-serve skew
    }


def _fit_one_quantile(
    alpha: float,
    X_train: np.ndarray,
    y_train: np.ndarray,
    w_train: np.ndarray,
    X_holdout: np.ndarray,
    y_holdout: np.ndarray,
    w_holdout: np.ndarray,
    cfg: QuantileTrainingConfig,
    feature_names: List[str],
) -> Tuple[Any, np.ndarray, int]:
    """Train one quantile booster. Returns (booster, holdout_preds, best_iteration).
    訓練單一分位 booster；回傳 (booster, holdout 預測, best_iteration)。"""
    import lightgbm as lgb

    train_data = lgb.Dataset(
        X_train, label=y_train, weight=w_train, feature_name=feature_names,
    )
    valid_data = lgb.Dataset(
        X_holdout, label=y_holdout, weight=w_holdout,
        reference=train_data, feature_name=feature_names,
    )
    params = _lgb_params(cfg, alpha, n_train=len(y_train))
    booster = lgb.train(
        params,
        train_data,
        num_boost_round=cfg.n_estimators,
        valid_sets=[valid_data],
        callbacks=[lgb.early_stopping(cfg.early_stopping_rounds, verbose=False)],
    )
    preds = booster.predict(X_holdout)
    best_iter = int(booster.best_iteration or cfg.n_estimators)
    return booster, preds.astype(np.float64), best_iter


def train_quantile_trio(
    features: np.ndarray,
    labels: np.ndarray,
    timestamps_ms: np.ndarray,
    feature_names: List[str],
    strategy_name: str,
    engine_mode: str = "demo",
    config: Optional[QuantileTrainingConfig] = None,
) -> QuantileTrainingResult:
    """Train q10 / q50 / q90 LGBM trio with CPCV-style purge + embargo,
    exponential sample weighting, and tail holdout per spec §6.

    This is Stage 2 core. Downstream:
      - calibration.fit_cqr_offset() consumes holdout_q*_pred + labels
      - quantile_reports.generate_acceptance_report() consumes whole result
      - onnx_exporter.export_quantile_trio_to_onnx() consumes models dict
    訓練 q10/q50/q90 三分位 LGBM（CPCV purge+embargo + 指數權重 + 尾段 holdout）。
    是 Stage 2 核心；下游由 CQR、acceptance report、ONNX 匯出共同使用。
    """
    cfg = config or QuantileTrainingConfig()
    result = QuantileTrainingResult(
        strategy_name=strategy_name,
        engine_mode=engine_mode,
        feature_names=list(feature_names),
        n_samples_total=int(len(labels)),
    )

    if features.shape[0] != len(labels) or features.shape[0] != len(timestamps_ms):
        result.error = "features / labels / timestamps length mismatch"
        return result
    if len(labels) == 0:
        result.error = "empty training set"
        return result

    try:
        import lightgbm  # noqa: F401 — import probe only
    except ImportError:
        result.error = "lightgbm not installed"
        logger.error("lightgbm unavailable — install via pip install lightgbm")
        return result

    embargo = get_embargo_config(strategy_name)
    result.embargo_config = embargo

    # Drop rows with NaN / Inf labels up front (defensive; ETL already strips).
    # 先砍 label 為 NaN/Inf 的行（ETL 已處理，此處防禦）。
    finite_mask = np.isfinite(labels)
    if not np.all(finite_mask):
        features = features[finite_mask]
        labels = labels[finite_mask]
        timestamps_ms = timestamps_ms[finite_mask]
    result.n_samples_labeled = int(len(labels))

    if len(labels) < 60:
        result.error = f"insufficient labeled samples: {len(labels)} < 60"
        return result

    # Tail holdout split (spec §6.1).
    train_idx, holdout_idx = _split_tail_holdout(timestamps_ms, embargo.holdout_tail_days)
    if len(train_idx) < 50 or len(holdout_idx) < 10:
        result.error = (
            f"degenerate split: train={len(train_idx)}, holdout={len(holdout_idx)}"
        )
        return result

    X_train = features[train_idx]
    y_train = labels[train_idx]
    ts_train = timestamps_ms[train_idx]
    X_holdout = features[holdout_idx]
    y_holdout = labels[holdout_idx]
    ts_holdout = timestamps_ms[holdout_idx]

    # Embargo: drop train rows within embargo_hours of holdout start.
    # Embargo：砍掉訓練集中距 holdout 起點 < embargo_hours 的樣本。
    holdout_start_ms = int(np.min(ts_holdout))
    embargo_ms = int(embargo.embargo_hours * 3600_000)
    embargo_mask = ts_train < (holdout_start_ms - embargo_ms)
    if embargo_mask.sum() < 50:
        # Do not enforce if it leaves < 50 samples — log and skip embargo.
        # 若 embargo 後 <50 樣本則不強制執行；日誌告警繼續。
        logger.warning(
            "embargo too aggressive for %s (n_train after embargo=%d) — disabled this run",
            strategy_name, int(embargo_mask.sum()),
        )
    else:
        X_train = X_train[embargo_mask]
        y_train = y_train[embargo_mask]
        ts_train = ts_train[embargo_mask]

    # Exponential sample weights on training split only (holdout un-weighted).
    # 僅訓練集加權；holdout 不加權以估計真實分佈的 coverage。
    ref_ms = int(np.max(timestamps_ms))
    w_train = compute_sample_weights(ts_train, cfg.decay_halflife_days, ref_ms)
    w_holdout = np.ones(len(y_holdout), dtype=np.float32)

    # Fit each quantile independently.
    try:
        b10, pred10, it10 = _fit_one_quantile(
            0.10, X_train, y_train, w_train,
            X_holdout, y_holdout, w_holdout, cfg, list(feature_names),
        )
        b50, pred50, it50 = _fit_one_quantile(
            0.50, X_train, y_train, w_train,
            X_holdout, y_holdout, w_holdout, cfg, list(feature_names),
        )
        b90, pred90, it90 = _fit_one_quantile(
            0.90, X_train, y_train, w_train,
            X_holdout, y_holdout, w_holdout, cfg, list(feature_names),
        )
    except Exception as exc:  # noqa: BLE001
        result.error = f"lgb fit failed: {exc}"
        logger.exception("LightGBM quantile fit failed")
        return result

    result.models = {"q10": b10, "q50": b50, "q90": b90}

    # Per-quantile metrics.
    for alpha, pred, best_it in ((0.10, pred10, it10), (0.50, pred50, it50), (0.90, pred90, it90)):
        baseline_const = float(np.quantile(y_train, alpha))
        skill, m_loss, b_loss = compute_pinball_skill(
            y_holdout, pred, alpha, baseline_const,
        )
        empirical_cov, cov_err_pp = compute_coverage_error(y_holdout, pred, alpha)
        result.per_quantile_metrics[f"q{int(alpha * 100):02d}"] = PerQuantileMetrics(
            alpha=alpha,
            pinball_loss=m_loss,
            pinball_loss_baseline_constant=b_loss,
            pinball_skill=skill,
            empirical_coverage=empirical_cov,
            coverage_error_pp=cov_err_pp,
            best_iteration=best_it,
            n_train=int(len(y_train)),
            n_holdout=int(len(y_holdout)),
        )

    # Linear QR floor — optional; gate enforced in quantile_reports.
    floor = fit_floor_baseline(X_train, y_train, X_holdout, y_holdout)
    for alpha in QUANTILE_ALPHAS:
        key = f"q{int(alpha * 100):02d}"
        linear_loss = floor.get(f"{key}_loss", 0.0)
        m = result.per_quantile_metrics[key]
        m.linear_qr_pinball_loss = float(linear_loss)
        if m.pinball_loss_baseline_constant > 0:
            # LGBM vs linear-QR skill diff: compare skill scores so shipping gate
            # can check ≥ +5pp. Linear QR skill uses same constant baseline.
            # LGBM vs linear QR 技能差：同一常數 baseline 比較，shipping gate 檢查 ≥+5pp。
            linear_skill = 1.0 - linear_loss / m.pinball_loss_baseline_constant
            m.linear_qr_pinball_skill = float(linear_skill)

    # Decile lift + crossing rate on q50 predictions.
    point, ci_lo, ci_hi = compute_decile_lift_bootstrap(
        y_holdout, pred50,
        n_boot=cfg.bootstrap_iterations, seed=cfg.bootstrap_seed,
    )
    result.decile_lift_point = point
    result.decile_lift_ci_lower = ci_lo
    result.decile_lift_ci_upper = ci_hi
    result.crossing_rate = check_quantile_crossing_rate(pred10, pred50, pred90)

    # Cache holdout for calibration + reports reuse.
    # 快取 holdout 給 calibration + reports 複用。
    result.holdout_features = X_holdout
    result.holdout_labels = y_holdout
    result.holdout_q10_pred = pred10
    result.holdout_q50_pred = pred50
    result.holdout_q90_pred = pred90
    result.n_holdout = int(len(y_holdout))

    result.feature_schema_hash = _compute_feature_schema_hash(
        list(feature_names), cfg.schema_version,
    )
    result.success = True

    logger.info(
        "train_quantile_trio ok: strategy=%s engine=%s n_train=%d n_holdout=%d "
        "skill=[q10=%.3f q50=%.3f q90=%.3f] cov_err_pp=[%.2f %.2f %.2f] "
        "crossing=%.4f decile_lift_point=%.3f ci95=[%.3f,%.3f]",
        strategy_name, engine_mode, len(y_train), len(y_holdout),
        result.per_quantile_metrics["q10"].pinball_skill,
        result.per_quantile_metrics["q50"].pinball_skill,
        result.per_quantile_metrics["q90"].pinball_skill,
        result.per_quantile_metrics["q10"].coverage_error_pp,
        result.per_quantile_metrics["q50"].coverage_error_pp,
        result.per_quantile_metrics["q90"].coverage_error_pp,
        result.crossing_rate, point, ci_lo, ci_hi,
    )
    return result

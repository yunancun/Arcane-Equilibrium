"""
Quantile LightGBM Trainer — three independent pinball fits for EDGE-P3-1 Stage 2.
三分位 LightGBM 訓練器 — EDGE-P3-1 Stage 2 的三獨立 pinball 擬合。

MODULE_NOTE (EN): Trains per-strategy q10/q50/q90 LGBM models on decision_features
  using a single time-ordered TAIL HOLDOUT + a ONE-SIDED EMBARGO (train rows
  within embargo_hours before the holdout start are dropped, opening a gap) +
  exponential sample weighting. This is NOT combinatorial purged k-fold CV: there
  is no fold loop, and the strategy-specific carve-out only tunes the embargo
  window and holdout tail length (funding_arb → 72h embargo / 14d holdout). The
  tail holdout is carved into three DISJOINT partitions — early-stopping
  validation, CQR calibration, and an untouched test set — so the reported
  ship-gate metrics never share rows with model selection or calibration.
  Computes pinball skill (vs constant baseline), coverage error, decile-lift
  bootstrap CI, quantile-crossing rate, and a linear-QR floor baseline per spec
  §6.2 ON THE TEST PARTITION ONLY. Pure training; CQR / ONNX / acceptance-report
  are downstream modules.
MODULE_NOTE (中): 每策略 q10/q50/q90 獨立 LightGBM 訓練，採用「單一時間序尾段
  holdout + 單邊 embargo」（砍掉訓練集中距 holdout 起點 < embargo_hours 的樣本、
  製造間隔）＋指數樣本權重。這「不是」combinatorial purged k-fold CV：沒有 fold
  迴圈，策略特定 carve-out 只調整 embargo 窗與 holdout 尾段長度（funding_arb →
  72h embargo + 14d holdout）。尾段 holdout 再切成三個「互斥」分區：early-stopping
  驗證集、CQR 校準集、以及未被觸碰的 test 集；回報的 ship-gate 指標永不與「模型
  選擇 / 校準」共用資料列（冷審計 claim-0002 HIGH 反洩漏）。pinball skill（相對
  常數 baseline）、coverage error、decile lift bootstrap CI、分位交叉違反率、
  linear QR floor baseline（spec §6.2）一律「只在 test 分區」計算。
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

# 三分 holdout 的最小樣本地板（early-stopping validation / CQR calibration /
# reported test 各自的下限）。
# 為什麼要地板：任一分區過小會讓 LightGBM early-stopping 失去意義、CQR 位移估計
#   退化、或 test 指標高變異；但地板刻意壓低（各 10 列），避免把「本可 ship 的
#   樣本」用 degenerate-split 誤殺——真正的樣本量守門交給 quantile_reports 的
#   spec §6.5 gate（<200 → no_ship、200–499 → shadow_only），此處只保證三分區
#   都大到足以「跑得動」。低於地板 → 走下方 two-way 退路（封頂 shadow_only），
#   而非直接 no-model（見 MIN_HOLDOUT_TWO_WAY_ROWS）。
MIN_VALIDATION_ROWS = 10
MIN_CALIBRATION_ROWS = 10
MIN_TEST_ROWS = 10

# 訓練集最小列數：低於此值 LightGBM 擬合本身失去意義（min_data_in_leaf 退化）。
# three_way 與 two_way 兩條路徑共用同一 train 地板。
MIN_TRAIN_ROWS = 50

# 兩分退路（MIT Item 1 修訂）的 holdout 絕對下限。
# 背景：Item 1 反洩漏修復把尾段 holdout 切成 val/calib/test 三互斥分區、各需 ≥ 10 列
#   （holdout ≳ 40）。MIT 指出此舉「過度封鎖」：實測 n=200/250/300/350 在 span
#   3/7/60d 下 holdout≈0.1·n 使 val=5–8 < 10，三分失敗後直接 no-model —— 這相對舊
#   holdout>=10 行為是 regression，且違反 spec §6.5「低樣本 band 無論指標都要有
#   shadow_only 模型」。修訂：holdout ≥ 此下限時退回「train + 單一 holdout」兩分路徑
#   並封頂 shadow_only（見 train_quantile_trio）；低於此下限（連兩分都撐不起 early-
#   stopping / 回報）才 fail-closed。取 10 對齊 MIT 引用的舊 holdout>=10 行為，確保
#   修復不比舊行為更嚴。
MIN_HOLDOUT_TWO_WAY_ROWS = 10

# partition_mode / ship_gate_metric_source 供 acceptance report 溯源與封頂裁決：
#   three_way            → 三互斥分區、ship 資格保留、指標取自未污染 test 分區；
#   two_way_shadow_capped→ 單一 holdout 被 early-stopping / CQR / 回報共用（潛在洩漏），
#                          verdict 由 quantile_reports 硬性封頂 shadow_only，指標取自
#                          該 holdout（ship gate 因此永不消費可能洩漏的兩分指標）。
PARTITION_MODE_THREE_WAY = "three_way"
PARTITION_MODE_TWO_WAY = "two_way_shadow_capped"
SHIP_GATE_SOURCE_TEST_PARTITION = "test_partition"
SHIP_GATE_SOURCE_TWO_WAY = "holdout_two_way_shadow_capped"

# holdout 三分的比例：validation 與 calibration 各佔 25%，其餘（≈50%）全歸 test。
# 為什麼 test 佔最大：ship-gate 的 decile-lift bootstrap 需 n≥20 才非退化，且回報
#   指標的統計功效直接取決於 test 樣本數；把最大且最新的一段留給 test 可在不放寬
#   ship 門檻的前提下維持可 ship 性。
_HOLDOUT_VALIDATION_FRACTION = 0.25
_HOLDOUT_CALIBRATION_FRACTION = 0.25


# ──────────────────────────────────────────────────────────────
# Config dataclasses
# ──────────────────────────────────────────────────────────────

@dataclass
class EmbargoConfig:
    """Per-strategy one-sided embargo window + tail-holdout length.
    策略特定「單邊 embargo 窗 + 尾段 holdout 長度」。

    為什麼沒有 fold 數：本訓練器走「單一尾段 holdout + 單邊 embargo」，並非
    combinatorial purged k-fold CV，不存在 fold 迴圈；先前的 n_folds 欄位從未被
    train_quantile_trio 讀取（dead param），依「可調參數禁止假功能」原則移除。真正
    的 CPCV k-fold 在獨立模組 cpcv_validator（legacy scorer 路徑）自帶 n_folds。"""

    embargo_hours: int
    holdout_tail_days: float


def get_embargo_config(strategy_name: str) -> EmbargoConfig:
    """Map strategy → EmbargoConfig per spec §6.1 (funding_arb carve-out).
    策略 → EmbargoConfig 映射（spec §6.1，funding_arb carve-out）。

    funding_arb uses a wider 72h embargo + 14d holdout tail because its labels
    realize over a longer horizon; all other strategies use the majority path
    24h embargo + 7d holdout tail. No fold count is involved — the quantile path
    validates on a single tail holdout, not k-fold CV.
    funding_arb 用較寬的 72h embargo + 14d holdout（標籤實現週期較長）；其他策略走
    多數路徑 24h embargo + 7d holdout。不涉及 fold 數 —— 分位路徑以單一尾段 holdout
    驗證，非 k-fold CV。
    """
    st = (strategy_name or "").lower().strip()
    if st == "funding_arb":
        return EmbargoConfig(embargo_hours=72, holdout_tail_days=14.0)
    return EmbargoConfig(embargo_hours=24, holdout_tail_days=7.0)


@dataclass
class QuantileTrainingConfig:
    """LightGBM quantile training + tail-holdout/one-sided-embargo + sample weight
    config per spec §6.
    LightGBM 分位訓練 + 尾段 holdout/單邊 embargo + 樣本權重配置（spec §6）。"""

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

    # Label window (hours): how long label computation looks forward. EDGE-P3-1
    # realized edge labels use the round-trip close ts, so effective label span
    # matches holding period. Conservative 4h default matches scorer_trainer
    # legacy behaviour.
    # 標籤窗（小時）：標籤計算前瞻時間，預設 4h 保守匹配 scorer 傳統行為。
    # 注意（非 CPCV）：現行分位路徑「不」執行 label-window purge —— train 與 holdout
    #   之間的隔離只靠下方的「單邊 embargo」達成；此欄位保留供 spec 對齊與 config
    #   schema 穩定，train_quantile_trio 本身不讀取。
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
    """Test-partition metrics for a single quantile fit.
    單一分位擬合的 test 分區指標（反洩漏後，回報指標一律取自 test 分區）。"""

    alpha: float
    pinball_loss: float
    pinball_loss_baseline_constant: float
    pinball_skill: float  # 1 - model / baseline
    empirical_coverage: float  # P(y <= q_pred)
    coverage_error_pp: float  # |empirical - alpha| * 100
    best_iteration: int
    n_train: int
    # n_holdout 保留欄名以維持 report schema 相容；語意為「指標計算所在的 test
    # 分區列數」（反洩漏後 = len(y_test)），非整個尾段 holdout。
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
    feature_definition_hash: str = ""
    feature_names: List[str] = field(default_factory=list)
    n_samples_total: int = 0
    n_samples_labeled: int = 0
    # n_holdout = 整個尾段 holdout（validation + calibration + test 三分區合計），
    # 保留原語意供 report / summary 溯源；三分區各自列數見 n_validation/n_calibration/n_test。
    n_holdout: int = 0
    n_validation: int = 0
    n_calibration: int = 0
    n_test: int = 0
    # 分區模式（MIT Item 1 修訂）：
    #   "three_way"             → 尾段 holdout 大到能三分（val/calib/test 互斥、各過地板），
    #                             ship 資格保留、指標取自未污染 test 分區；
    #   "two_way_shadow_capped" → holdout 太小無法三分（sub-floor），退回「train + 單一
    #                             holdout」，單一 holdout 被 early-stopping / CQR / 回報
    #                             共用（潛在洩漏）→ 下游 verdict 硬性封頂 shadow_only。
    # 硬邊界：two_way 下 n_validation / n_calibration / n_test 皆等於整段 holdout 列數
    #   （三角色共用同一批列），三者「不」互斥；互斥性只在 three_way 成立，故不得對
    #   two_way 結果套用 three_way 的 disjointness 斷言。
    partition_mode: str = PARTITION_MODE_THREE_WAY
    # ship-gate 指標來源標記，供 acceptance report 溯源：
    #   three_way → "test_partition"（未被選模型 / 校準觸碰）；
    #   two_way   → "holdout_two_way_shadow_capped"（與選模型 / 校準共用 → 封頂 shadow_only）。
    ship_gate_metric_source: str = SHIP_GATE_SOURCE_TEST_PARTITION
    embargo_config: Optional[EmbargoConfig] = None
    # 本次 run 是否「實際」執行了 embargo。embargo_config 只記錄意圖配置；當
    # embargo 後訓練樣本 < 50 時 train_quantile_trio 會 fail-open 靜默改用未 embargo
    # 的 train set，此旗標把該事實暴露到 acceptance report，避免「配置顯示 embargo
    # 已套用、runtime 卻已停用」的隱形 leakage 觀測缺口（冷審計 R2 MIT[MEDIUM]）。
    embargo_enforced: bool = True
    # 邊界 label-realization 重疊計數：落在 holdout 起點前 embargo 窗
    #   [holdout_start - embargo_hours, holdout_start) 內、且因 embargo 未強制而
    #   「保留」在訓練集的 train 列數。
    # 語意：embargo 真正執行時這些列已被丟棄 → 計數 = 0（已隔離）；fail-open 停用
    #   embargo 時這些列殘留在 train，其 label 實現窗與 holdout 邊界重疊 = 邊界洩漏
    #   風險的直接量化。連同 embargo_enforced 一起落 acceptance report，供下游 verdict
    #   引用並封頂至 shadow_only（冷審計 R2 MIT[MEDIUM] Item 3：不得靜默丟棄 embargo）。
    embargo_overlap_count: int = 0
    # 反洩漏後改為兩組互斥快取（皆 un-typed，避免 dataclass 硬相依 numpy）：
    #   calibration_* → 供下游 fit_cqr_trio 擬合 CQR 位移（校準集，不參與指標回報）；
    #   test_*        → 供下游 evaluate_cqr_coverage 回報「CQR 後 coverage」的
    #                   未污染 test 集，亦是所有 ship-gate 指標的唯一來源。
    # 硬邊界：test_* 永不進入 fit_cqr_trio；calibration_* 永不進入指標回報 —— 否則
    #   「校準 / 選模型」與「回報 edge」再度共用資料 = 回到 claim-0002 洩漏。
    calibration_labels: Any = None
    calibration_q10_pred: Any = None
    calibration_q50_pred: Any = None
    calibration_q90_pred: Any = None
    test_labels: Any = None
    test_q10_pred: Any = None
    test_q50_pred: Any = None
    test_q90_pred: Any = None


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
    """Stable `sha256:<16 hex>` pinned byte-for-byte to Rust authority.

    Mirrors `rust/openclaw_engine/src/linucb/schema_hash.rs::compute_feature_schema_hash`
    exactly: payload is `name1\\n` || `name2\\n` || ... (trailing newline after
    each name, no version prefix), output is `sha256:` + first 16 hex chars of
    the digest. Rust is the train/serve authority — ONNX artifacts whose
    `edge_p3_feature_schema_hash` metadata disagrees with Rust's compile-time
    `FEATURE_NAMES_V1` hash are rejected at load by `tract_backend`. Emitting
    any other format here guarantees every real model gets rejected.

    `schema_version` is retained in the signature for future splits (spec may
    one day fold version into the hash payload) but is not currently mixed in;
    version drift surfaces via the separate `edge_p3_schema_version` ONNX
    metadata key and via filename convention.

    與 Rust 權威實作逐字節對齊：`name1\\n name2\\n ...` 無版本前綴；輸出 `sha256:前16hex`。
    ONNX artifact 的 schema_hash 不匹配時 `tract_backend` 直接拒載；其他格式即永拒。
    """
    del schema_version  # intentionally unused — see docstring
    hasher = hashlib.sha256()
    for name in feature_names:
        hasher.update(name.encode("utf-8"))
        hasher.update(b"\n")
    return "sha256:" + hasher.hexdigest()[:16]


def _compute_feature_definition_hash(feature_names: List[str], schema_version: str) -> str:
    """Stable definition hash for canonical EDGE-P3 features.

    The Python source of truth lives in parquet_etl next to the feature-name
    tuple consumed by load_training_data; Rust mirrors the same definition
    strings in edge_predictor/features.rs. For non-canonical feature lists,
    hash a conservative name-only definition payload so custom tests remain
    deterministic without pretending to match production FeatureVectorV1.
    """
    del schema_version
    try:
        from program_code.ml_training.parquet_etl import (
            EDGE_P3_FEATURE_DEFINITIONS,
            EDGE_P3_FEATURE_NAMES,
            compute_feature_definition_hash,
        )
    except Exception:  # pragma: no cover - import fallback for direct script mode
        EDGE_P3_FEATURE_NAMES = tuple(feature_names)  # type: ignore[assignment]
        EDGE_P3_FEATURE_DEFINITIONS = tuple(f"{name}=custom_feature_name_only" for name in feature_names)  # type: ignore[assignment]

        def compute_feature_definition_hash(items):  # type: ignore[no-redef]
            hasher = hashlib.sha256()
            for item in items:
                hasher.update(str(item).encode("utf-8"))
                hasher.update(b"\n")
            return "sha256:" + hasher.hexdigest()[:16]

    if tuple(feature_names) == tuple(EDGE_P3_FEATURE_NAMES):
        return compute_feature_definition_hash(EDGE_P3_FEATURE_DEFINITIONS)
    hasher = hashlib.sha256()
    for name in feature_names:
        hasher.update(f"{name}=custom_feature_name_only".encode("utf-8"))
        hasher.update(b"\n")
    return "sha256:" + hasher.hexdigest()[:16]


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


def _partition_holdout_three_way(
    holdout_idx: np.ndarray,
    val_fraction: float = _HOLDOUT_VALIDATION_FRACTION,
    calib_fraction: float = _HOLDOUT_CALIBRATION_FRACTION,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """把「時間升序」的尾段 holdout 再切成三個互斥、連續的時間分區。

    回傳 (val_idx, calib_idx, test_idx)：
      - val   （最舊一段）→ LightGBM early-stopping 驗證集（決定 boosting 輪數，
                即「模型選擇」）。放最舊是為了讓 test（最新）保持完全未被觸碰。
      - calib （中段）    → CQR 邊際校準集；緊鄰 test 以利 conformal 的可交換性。
      - test  （最新一段）→ 唯一用於回報 ship-gate 指標的未污染分區，符合
                spec §6.1「最近資料嚴格 holdout」意圖。

    為什麼三段必須互斥：原本單一 holdout 同時充當 early-stopping 驗證集、CQR
      校準集、以及回報 pinball / coverage / decile-lift / CQR-後-coverage 的集合，
      使「模型選擇 + 校準」與「回報的 edge」共用同批資料 = 洩漏
      （冷審計 claim-0002 HIGH）。三段互斥後，回報指標永不參與選擇或校準。

    邊界防禦：確保三段皆非空（各至少 1 列，剩餘全歸 test）；真正的「太小」由
      呼叫端的 MIN_*_ROWS degenerate-split guard fail-closed 攔下。
    """
    n = len(holdout_idx)
    if n == 0:
        empty = np.empty((0,), dtype=np.intp)
        return empty, empty.copy(), empty.copy()
    n_val = int(n * val_fraction)
    n_calib = int(n * calib_fraction)
    # 至少各留 1 列，且保證 test 至少 1 列（n_val + n_calib ≤ n - 1）。
    n_val = max(1, min(n_val, n - 2)) if n >= 3 else max(0, n - 1)
    n_calib = max(1, min(n_calib, n - n_val - 1)) if (n - n_val) >= 2 else 0
    val_idx = holdout_idx[:n_val]
    calib_idx = holdout_idx[n_val:n_val + n_calib]
    test_idx = holdout_idx[n_val + n_calib:]
    return (
        val_idx.astype(np.intp),
        calib_idx.astype(np.intp),
        test_idx.astype(np.intp),
    )


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
    X_val: np.ndarray,
    y_val: np.ndarray,
    w_val: np.ndarray,
    cfg: QuantileTrainingConfig,
    feature_names: List[str],
) -> Tuple[Any, int]:
    """Train one quantile booster. Returns (booster, best_iteration).

    X_val is used ONLY as the early-stopping validation set (i.e. to pick the
    boosting round count) and is deliberately disjoint from the calibration and
    test partitions. This function intentionally does NOT predict on any
    reporting/calibration partition — the caller does that separately so the
    rows that select the model never leak into the reported ship-gate metrics.
    X_val 僅作 early-stopping 驗證集（挑 boosting 輪數 = 模型選擇），與 calibration /
    test 分區互斥；本函式刻意不對任何「回報 / 校準」分區做 predict —— 由呼叫端另行
    在 test / calibration 分區上 predict，確保選模型的資料列不洩漏進回報指標。
    """
    import lightgbm as lgb

    train_data = lgb.Dataset(
        X_train, label=y_train, weight=w_train, feature_name=feature_names,
    )
    valid_data = lgb.Dataset(
        X_val, label=y_val, weight=w_val,
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
    best_iter = int(booster.best_iteration or cfg.n_estimators)
    return booster, best_iter


def train_quantile_trio(
    features: np.ndarray,
    labels: np.ndarray,
    timestamps_ms: np.ndarray,
    feature_names: List[str],
    strategy_name: str,
    engine_mode: str = "demo",
    config: Optional[QuantileTrainingConfig] = None,
) -> QuantileTrainingResult:
    """Train q10 / q50 / q90 LGBM trio with a single tail holdout + one-sided
    embargo, exponential sample weighting, and a three-way tail-holdout carve
    per spec §6.

    The tail holdout is carved into three disjoint partitions (see
    _partition_holdout_three_way): validation (early stopping), calibration
    (CQR), and test (reported ship-gate metrics). No holdout row informs both
    model selection/calibration and the reported skill.

    Sub-floor fallback (MIT Item 1 revision): when the tail holdout is too small
    to form three above-floor disjoint partitions (empirically n∈[200,400) short
    spans), the trainer does NOT abort to no-model. It falls back to a two-way
    path (train + a single holdout that doubles as early-stopping / CQR /
    reported set) and records partition_mode="two_way_shadow_capped" so
    quantile_reports caps the verdict at shadow_only — the ship gate never
    consumes the potentially-leaked two-way metrics, and spec §6.5's low-sample
    shadow band is preserved. Genuinely degenerate cases (train below floor or
    holdout below the two-way absolute minimum) still fail closed.
    尾段 holdout 太小無法三分時退回兩分（train + 單一 holdout）並封頂 shadow_only，
    保留 §6.5 shadow band；真正退化仍 fail-closed（見函式體 partition_mode 決策）。

    This is Stage 2 core. Downstream:
      - calibration.fit_cqr_trio() consumes calibration_q*_pred + calibration_labels
      - calibration.evaluate_cqr_coverage() reports on test_q*_pred + test_labels
      - quantile_reports.generate_acceptance_report() consumes whole result
      - onnx_exporter.export_quantile_trio_to_onnx() consumes models dict
    訓練 q10/q50/q90 三分位 LGBM（單一尾段 holdout + 單邊 embargo + 指數權重 +
    三分尾段 holdout）。
    尾段 holdout 切成三互斥分區：validation（early stopping）、calibration（CQR）、
    test（回報 ship-gate 指標）；沒有任一 holdout 列同時影響「選模型/校準」與「回報
    skill」（反洩漏 claim-0002 HIGH）。是 Stage 2 核心；下游由 CQR、acceptance
    report、ONNX 匯出共同使用。
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

    # Tail holdout split (spec §6.1), then attempt the three-way disjoint carve.
    # 尾段 holdout 切分（spec §6.1），先嘗試三互斥分區；能否成立由下方 partition_mode
    #   決策判定（不足時退回 two-way，見該區塊）。
    train_idx, holdout_idx = _split_tail_holdout(timestamps_ms, embargo.holdout_tail_days)
    val_idx, calib_idx, test_idx = _partition_holdout_three_way(holdout_idx)

    # 分區模式決策（MIT Item 1 修訂）。三種結果：
    #   (1) three_way — holdout 大到能形成三個「各自過地板」的互斥分區：維持反洩漏原行為
    #       （val=early-stopping / calib=CQR / test=回報，三者列永不重疊），指標取自未污染
    #       test 分區，ship 資格保留。
    #   (2) two_way_shadow_capped — holdout 太小無法三分（sub-floor；實測 n∈[200,400) 短跨度
    #       使 val=5–8 < 地板）：不再 abort 成 no-model（那既是相對舊 holdout>=10 的 regression，
    #       又違反 spec §6.5「低樣本 band 無論指標都要有 shadow_only 模型」）。改走「train +
    #       單一 holdout」，該 holdout 同時充當 early-stopping / CQR / 回報，指標在其上計算，
    #       並由 quantile_reports 硬性封頂 verdict=shadow_only。
    #   (3) degenerate — train 太小擬合不動、或 holdout 低於兩分退路絕對下限：fail-closed。
    # 為什麼 two_way 封頂而非放行 ship：two_way 下選模型 / 校準 / 回報共用同批列（潛在洩漏），
    #   封頂 shadow_only 即 ship gate 永不消費可能洩漏的兩分指標 → 反洩漏意圖仍守住；同時
    #   §6.5 的 shadow band 得以保留（有模型、非 no-model）。兩個約束同時滿足。
    three_way_ok = (
        len(train_idx) >= MIN_TRAIN_ROWS
        and len(val_idx) >= MIN_VALIDATION_ROWS
        and len(calib_idx) >= MIN_CALIBRATION_ROWS
        and len(test_idx) >= MIN_TEST_ROWS
    )
    if three_way_ok:
        result.partition_mode = PARTITION_MODE_THREE_WAY
        result.ship_gate_metric_source = SHIP_GATE_SOURCE_TEST_PARTITION
    elif (
        len(train_idx) >= MIN_TRAIN_ROWS
        and len(holdout_idx) >= MIN_HOLDOUT_TWO_WAY_ROWS
    ):
        # two-way 退路：三分區索引全部指向同一 holdout（early-stopping / CQR / 回報共用）。
        # 刻意放棄互斥性 → 由 verdict 封頂 shadow_only 補償（見上方 rationale 與
        # quantile_reports 的 two_way 封頂）。
        result.partition_mode = PARTITION_MODE_TWO_WAY
        result.ship_gate_metric_source = SHIP_GATE_SOURCE_TWO_WAY
        val_idx = holdout_idx
        calib_idx = holdout_idx
        test_idx = holdout_idx
    else:
        # degenerate fail-closed → success=False → 下游 verdict=no_ship。
        # 只擋「小到連兩分退路都撐不起」：train < 地板 或 holdout < 兩分絕對下限。
        # §6.5 對 <200 band 本就是 no_ship，此路徑與之一致。
        result.error = (
            f"degenerate split: train={len(train_idx)}, holdout={len(holdout_idx)}, "
            f"val={len(val_idx)}, calib={len(calib_idx)}, test={len(test_idx)}"
        )
        return result

    X_train = features[train_idx]
    y_train = labels[train_idx]
    ts_train = timestamps_ms[train_idx]
    # holdout 起點（= val 最舊列）供 embargo 使用；val/calib/test 直接由索引取，
    # embargo 只修剪 train，三分區本身不受 embargo 影響。
    ts_holdout = timestamps_ms[holdout_idx]

    X_val = features[val_idx]
    y_val = labels[val_idx]
    X_calib = features[calib_idx]
    y_calib = labels[calib_idx]
    X_test = features[test_idx]
    y_test = labels[test_idx]

    # Embargo: drop train rows within embargo_hours of holdout start.
    # Embargo：砍掉訓練集中距 holdout 起點 < embargo_hours 的樣本。
    holdout_start_ms = int(np.min(ts_holdout))
    embargo_ms = int(embargo.embargo_hours * 3600_000)
    embargo_mask = ts_train < (holdout_start_ms - embargo_ms)
    # 邊界重疊列：~embargo_mask = ts_train 落在
    #   [holdout_start - embargo, holdout_start) 的訓練列，其 label 實現窗與 holdout
    #   邊界重疊 = 潛在洩漏源。無論是否強制 embargo 皆先算出，供下游誠實記帳。
    boundary_overlap = int((~embargo_mask).sum())
    if embargo_mask.sum() < 50:
        # Do not enforce if it leaves < 50 samples — log and skip embargo.
        # 若 embargo 後 <50 樣本則不強制執行；日誌告警繼續。
        # fail-open 已停用 embargo：標記 embargo_enforced=False 使 acceptance report
        # 可誠實反映本次未套 embargo（否則 report 只見 embargo_config 意圖，誤導）。
        # 同時記錄邊界重疊列數（這些列殘留在 train = 洩漏風險），供下游 verdict 引用
        #   並封頂至 shadow_only；不得靜默丟棄 embargo（冷審計 R2 MIT[MEDIUM] Item 3）。
        result.embargo_enforced = False
        result.embargo_overlap_count = boundary_overlap
        logger.warning(
            "embargo too aggressive for %s (n_train after embargo=%d, "
            "boundary_overlap=%d) — disabled this run",
            strategy_name, int(embargo_mask.sum()), boundary_overlap,
        )
    else:
        X_train = X_train[embargo_mask]
        y_train = y_train[embargo_mask]
        ts_train = ts_train[embargo_mask]
        # embargo 真正執行 → 邊界重疊列已從 train 移除，保留計數歸 0（誠實反映已隔離）。
        result.embargo_overlap_count = 0

    # Exponential sample weights on training split only; validation set is
    # un-weighted so early stopping tracks the raw distribution.
    # 僅訓練集加權；validation 集不加權，讓 early stopping 貼近原始分佈。
    ref_ms = int(np.max(timestamps_ms))
    w_train = compute_sample_weights(ts_train, cfg.decay_halflife_days, ref_ms)
    w_val = np.ones(len(y_val), dtype=np.float32)

    # Fit each quantile independently — early stopping on the validation set only.
    # 各分位獨立擬合 —— early stopping 僅用 validation 集。
    try:
        b10, it10 = _fit_one_quantile(
            0.10, X_train, y_train, w_train,
            X_val, y_val, w_val, cfg, list(feature_names),
        )
        b50, it50 = _fit_one_quantile(
            0.50, X_train, y_train, w_train,
            X_val, y_val, w_val, cfg, list(feature_names),
        )
        b90, it90 = _fit_one_quantile(
            0.90, X_train, y_train, w_train,
            X_val, y_val, w_val, cfg, list(feature_names),
        )
    except Exception as exc:  # noqa: BLE001
        result.error = f"lgb fit failed: {exc}"
        logger.exception("LightGBM quantile fit failed")
        return result

    result.models = {"q10": b10, "q50": b50, "q90": b90}

    # Predictions on the untouched TEST partition — the ONLY source of reported
    # ship-gate metrics (pinball skill / coverage / decile-lift / crossing).
    # test 分區預測 —— 回報 ship-gate 指標的唯一來源（未參與選模型 / 校準）。
    test_pred10 = b10.predict(X_test).astype(np.float64)
    test_pred50 = b50.predict(X_test).astype(np.float64)
    test_pred90 = b90.predict(X_test).astype(np.float64)

    # Predictions on the CALIBRATION partition — consumed downstream by
    # fit_cqr_trio only (never enters reported metrics).
    # calibration 分區預測 —— 僅供下游 fit_cqr_trio，永不進入回報指標。
    calib_pred10 = b10.predict(X_calib).astype(np.float64)
    calib_pred50 = b50.predict(X_calib).astype(np.float64)
    calib_pred90 = b90.predict(X_calib).astype(np.float64)

    # Per-quantile metrics — computed on the TEST partition.
    # 各分位指標 —— 於 test 分區計算。
    for alpha, pred, best_it in ((0.10, test_pred10, it10), (0.50, test_pred50, it50), (0.90, test_pred90, it90)):
        baseline_const = float(np.quantile(y_train, alpha))
        skill, m_loss, b_loss = compute_pinball_skill(
            y_test, pred, alpha, baseline_const,
        )
        empirical_cov, cov_err_pp = compute_coverage_error(y_test, pred, alpha)
        result.per_quantile_metrics[f"q{int(alpha * 100):02d}"] = PerQuantileMetrics(
            alpha=alpha,
            pinball_loss=m_loss,
            pinball_loss_baseline_constant=b_loss,
            pinball_skill=skill,
            empirical_coverage=empirical_cov,
            coverage_error_pp=cov_err_pp,
            best_iteration=best_it,
            n_train=int(len(y_train)),
            n_holdout=int(len(y_test)),
        )

    # Linear QR floor — evaluated on the TEST partition (same set as the LGBM
    # skill it is compared against in quantile_reports); gate enforced there.
    # linear QR floor —— 於 test 分區評估（與被比較的 LGBM skill 同集），gate 在 reports。
    floor = fit_floor_baseline(X_train, y_train, X_test, y_test)
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

    # Decile lift + crossing rate on q50 TEST predictions.
    # decile lift + 交叉違反率取自 test 分區的 q50 預測。
    point, ci_lo, ci_hi = compute_decile_lift_bootstrap(
        y_test, test_pred50,
        n_boot=cfg.bootstrap_iterations, seed=cfg.bootstrap_seed,
    )
    result.decile_lift_point = point
    result.decile_lift_ci_lower = ci_lo
    result.decile_lift_ci_upper = ci_hi
    result.crossing_rate = check_quantile_crossing_rate(test_pred10, test_pred50, test_pred90)

    # Cache the two disjoint partitions for downstream reuse:
    #   calibration_* → fit_cqr_trio (CQR 位移擬合)；
    #   test_*        → evaluate_cqr_coverage 回報「CQR 後 coverage」。
    result.calibration_labels = y_calib
    result.calibration_q10_pred = calib_pred10
    result.calibration_q50_pred = calib_pred50
    result.calibration_q90_pred = calib_pred90
    result.test_labels = y_test
    result.test_q10_pred = test_pred10
    result.test_q50_pred = test_pred50
    result.test_q90_pred = test_pred90
    result.n_validation = int(len(y_val))
    result.n_calibration = int(len(y_calib))
    result.n_test = int(len(y_test))
    # n_holdout = 三分區合計（保留原語意供 report / summary 溯源）。
    result.n_holdout = int(len(holdout_idx))

    result.feature_schema_hash = _compute_feature_schema_hash(
        list(feature_names), cfg.schema_version,
    )
    result.feature_definition_hash = _compute_feature_definition_hash(
        list(feature_names), cfg.schema_version,
    )
    result.success = True

    logger.info(
        "train_quantile_trio ok: strategy=%s engine=%s n_train=%d "
        "n_val=%d n_calib=%d n_test=%d "
        "skill=[q10=%.3f q50=%.3f q90=%.3f] cov_err_pp=[%.2f %.2f %.2f] "
        "crossing=%.4f decile_lift_point=%.3f ci95=[%.3f,%.3f] (metrics on test)",
        strategy_name, engine_mode, len(y_train),
        len(y_val), len(y_calib), len(y_test),
        result.per_quantile_metrics["q10"].pinball_skill,
        result.per_quantile_metrics["q50"].pinball_skill,
        result.per_quantile_metrics["q90"].pinball_skill,
        result.per_quantile_metrics["q10"].coverage_error_pp,
        result.per_quantile_metrics["q50"].coverage_error_pp,
        result.per_quantile_metrics["q90"].coverage_error_pp,
        result.crossing_rate, point, ci_lo, ci_hi,
    )
    return result

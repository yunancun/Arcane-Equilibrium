"""dsr_gate — REF-20 Wave 6 P4-Q1 Deflated Sharpe Ratio promotion gate.

DSR(K) > 0.95 升級 gate — REF-20 Wave 6 P4-Q1 Deflated Sharpe 比率升級門檻。

MODULE_NOTE (EN): Implements Bailey & Lopez de Prado (2014) Deflated Sharpe
  Ratio (DSR) — adjusts observed Sharpe for selection bias when K candidate
  variants were explored before the best was selected. Promotion gate for
  V3 §11 P4 Exit + V3 §12 acceptance #17 (replay_cv_protocol). Pure-math
  IMPL: 0 IPC / 0 DB / 0 exchange. Output feeds
  `replay_routes.generate_handoff_verdict` advisory verdict layer.
MODULE_NOTE (中): 實作 Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio
  (DSR) — 在從 K 個候選變體中選擇最佳之前修正觀察 Sharpe 的選擇偏差。
  V3 §11 P4 Exit + V3 §12 acceptance #17 (replay_cv_protocol) 升級 gate。
  純數學 IMPL：0 IPC / 0 DB / 0 exchange。輸出餵
  `replay_routes.generate_handoff_verdict` advisory verdict 層。

V3 §8.3 + §11 P4 binding / V3 §8.3 + §11 P4 綁定:
  - "DSR(K) > 0.95 for promotion" (§8.3)
  - "DSR(K)>0.95 + PBO<0.5 (K>=10) + power gate enforced" (§12 #17)
  - K = total_candidates_K (manifest mandatory field, §8.3)

Reference / 參考:
  - Bailey, D. H., & Lopez de Prado, M. M. (2014). The Deflated Sharpe Ratio:
    Correcting for Selection Bias, Backtest Overfitting and Non-Normality.
    Journal of Portfolio Management, 40(5), 94-107.
  - Bailey, D. H., & Lopez de Prado, M. M. (2012). The Sharpe Ratio Efficient
    Frontier. Journal of Risk, 15(2), 13.

Math summary / 數學摘要:
  PSR(SR_threshold) = Probability that observed SR > SR_threshold given variance.
  PSR(SR*) = Φ((SR_obs - SR*) * sqrt((T-1) / (1 - γ3*SR_obs + (γ4-1)/4 * SR_obs²)))
    where γ3 = skew, γ4 = kurtosis (Gaussian → 0, 3).
  E[max{SR_k}_{k=1..K}] ≈ ((1-γ_E) * Φ⁻¹(1-1/K) + γ_E * Φ⁻¹(1-1/(K*e)))
    where γ_E = Euler-Mascheroni ≈ 0.5772.
  DSR = PSR(E[max SR_k]) — i.e., probability observed SR > expected best-of-K.

Wave 6 P4-Q1 scope (this commit):
  - DsrGate class with compute_dsr() + gate() pure methods.
  - DsrResult dataclass (observed_sharpe / deflated_sharpe / n_trials_K /
    psr_at_threshold / trials_max_sharpe / passes_threshold).
  - 4 pytest cases: K=1 → DSR == observed / K=10 → DSR < observed /
    DSR > 0.95 → promote / DSR < 0.95 → block.

NOT in this scope:
  - replay_routes.py call-site wiring (separate sub-task, P4 wiring wave).
  - DB INSERT replay.dsr_audit_log (P6 governance_audit_log subtask).
  - PBO < 0.5 sibling gate (P4-Q2 → pbo_gate.py).
  - cost_edge_ratio gate (P4-Q6 → cost_edge_advisor.py).

SPEC:
  - REF-20 V3 §8.3 (Selection Bias Controls)
  - REF-20 V3 §11 P4 Exit
  - REF-20 V3 §12 acceptance #17
Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md §4 R20-P4-Q1
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Literal, Optional, Sequence

import numpy as np


logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants / 常量
# ─────────────────────────────────────────────────────────────────────────────

# V3 §8.3 / §11 P4 promotion threshold.
# V3 §8.3 / §11 P4 升級閾值。
DEFAULT_DSR_THRESHOLD: float = 0.95

# Borderline band: DSR in [0.90, 0.95) returns 'borderline' for review.
# 邊緣帶：DSR 介於 [0.90, 0.95) 回 'borderline' 供 review。
BORDERLINE_LOWER: float = 0.90

# Euler-Mascheroni constant for E[max SR_k] approximation.
# Euler-Mascheroni 常數，用於 E[max SR_k] 近似。
EULER_GAMMA: float = 0.5772156649015329


# ─────────────────────────────────────────────────────────────────────────────
# Result dataclass / 結果 dataclass
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class DsrResult:
    """DSR(K) computation result.

    DSR(K) 計算結果。

    Attributes / 屬性:
        observed_sharpe: Observed in-sample Sharpe of selected (best) candidate. /
                         所選（最佳）候選的觀察樣本內 Sharpe。
        deflated_sharpe: PSR-style probability adjusted for K trials. /
                         以 K 次嘗試調整後的 PSR 式機率（即 DSR 值，0..1）。
        n_trials_K: Number of variants explored before selecting best (K). /
                    在選擇最佳前探索的變體數（K）。
        psr_at_threshold: Probability observed SR > 0 (PSR baseline). /
                          觀察 SR > 0 之機率（PSR 基線）。
        trials_max_sharpe: Expected max SR across K Gaussian trials (E[max SR_k]). /
                           K 個 Gaussian trial 之預期最大 SR。
        passes_threshold: True if deflated_sharpe > DSR threshold. /
                          deflated_sharpe > DSR 閾值時為 True。
    """

    observed_sharpe: float
    deflated_sharpe: float
    n_trials_K: int
    psr_at_threshold: float
    trials_max_sharpe: float
    passes_threshold: bool


# ─────────────────────────────────────────────────────────────────────────────
# Math helpers / 數學輔助
# ─────────────────────────────────────────────────────────────────────────────


def _normal_cdf(x: float) -> float:
    """Standard normal CDF Φ(x).

    標準常態 CDF Φ(x)。

    Uses math.erf for stdlib-only IMPL (no scipy dependency for this hot helper).
    用 math.erf 做純 stdlib IMPL（避免此熱輔助引入 scipy 依賴）。
    """
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _normal_inv_cdf(p: float) -> float:
    """Inverse standard normal CDF Φ⁻¹(p) via Beasley-Springer-Moro approximation.

    用 Beasley-Springer-Moro 近似的標準常態反 CDF Φ⁻¹(p)。

    Acuracy ~1e-7 for p ∈ (1e-7, 1 - 1e-7); sufficient for K ≤ 10000.
    準確度 ~1e-7 對 p ∈ (1e-7, 1 - 1e-7)；對 K ≤ 10000 充分。

    Note / 註: We hand-roll to avoid scipy dependency (consistent with Wave 5
    quantile_bootstrap policy). For K > 10000 use scipy.stats.norm.ppf.
    手寫避免 scipy 依賴（與 Wave 5 quantile_bootstrap 政策一致）。
    K > 10000 時改用 scipy.stats.norm.ppf。
    """
    if p <= 0.0 or p >= 1.0:
        raise ValueError(f"p={p} must be in (0, 1) for inv_cdf")

    # Beasley-Springer-Moro coefficients.
    # Beasley-Springer-Moro 係數。
    a = [
        -3.969683028665376e+01,
        2.209460984245205e+02,
        -2.759285104469687e+02,
        1.383577518672690e+02,
        -3.066479806614716e+01,
        2.506628277459239e+00,
    ]
    b = [
        -5.447609879822406e+01,
        1.615858368580409e+02,
        -1.556989798598866e+02,
        6.680131188771972e+01,
        -1.328068155288572e+01,
    ]
    c = [
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e+00,
        -2.549732539343734e+00,
        4.374664141464968e+00,
        2.938163982698783e+00,
    ]
    d = [
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e+00,
        3.754408661907416e+00,
    ]

    p_low = 0.02425
    p_high = 1.0 - p_low

    if p < p_low:
        q = math.sqrt(-2.0 * math.log(p))
        return (
            (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
            / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
        )

    if p <= p_high:
        q = p - 0.5
        r = q * q
        return (
            (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q
            / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
        )

    # Upper tail / 上尾
    q = math.sqrt(-2.0 * math.log(1.0 - p))
    return -(
        (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5])
        / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0)
    )


def _compute_expected_max_sharpe(K: int) -> float:
    """Compute E[max{SR_k}_{k=1..K}] under Gaussian null hypothesis.

    在高斯虛無假設下計算 E[max{SR_k}_{k=1..K}]。

    Bailey-Lopez de Prado (2014) Eq. 8 approximation:
      E[max SR_k] ≈ (1-γ_E) * Φ⁻¹(1 - 1/K) + γ_E * Φ⁻¹(1 - 1/(K*e))

    Bailey-Lopez de Prado (2014) 第 8 式近似。

    Note / 註: For K=1 this returns 0 (no selection). For K=10 ≈ 1.539 σ.
    註：K=1 回傳 0（無選擇）。K=10 約 1.539 σ。
    """
    if K < 1:
        raise ValueError(f"K={K} must be >= 1")
    if K == 1:
        # Single trial → no selection bias → expected max SR is 0
        # under Gaussian null (E[Z]=0).
        # 單一 trial → 無選擇偏差 → 高斯虛無下 E[Z]=0。
        return 0.0

    e = math.e
    # Φ⁻¹(1 - 1/K) and Φ⁻¹(1 - 1/(K*e))
    p1 = 1.0 - 1.0 / float(K)
    p2 = 1.0 - 1.0 / (float(K) * e)
    inv1 = _normal_inv_cdf(p1)
    inv2 = _normal_inv_cdf(p2)
    return (1.0 - EULER_GAMMA) * inv1 + EULER_GAMMA * inv2


def _compute_psr(
    observed_sharpe: float,
    sharpe_threshold: float,
    n_observations: int,
    skew: float = 0.0,
    excess_kurtosis: float = 0.0,
) -> float:
    """Probabilistic Sharpe Ratio (PSR) — Bailey & Lopez de Prado (2012).

    機率 Sharpe 比率 (PSR) — Bailey & Lopez de Prado (2012)。

    PSR(SR*) = Φ(
        (SR_obs - SR*) * sqrt(T - 1) /
        sqrt(1 - γ3 * SR_obs + (γ4 - 1) / 4 * SR_obs²)
    )

    where γ3 = skew, γ4 = kurtosis (Gaussian → γ3=0, γ4=3, so γ4-1=2).
    Excess kurtosis ke = γ4 - 3 → γ4 = ke + 3 → (γ4 - 1) = ke + 2.

    γ3 = 偏度，γ4 = 峰度（高斯 → γ3=0, γ4=3）。
    excess kurtosis ke = γ4 - 3 → (γ4 - 1) = ke + 2。

    Args / 引數:
        observed_sharpe: 樣本內觀察 Sharpe (annualized or per-period;
                         pass consistent unit). / 樣本內觀察 Sharpe。
        sharpe_threshold: 比較 baseline（DSR uses E[max SR_k]; PSR(0)
                          uses 0). / 比較基線。
        n_observations: T = number of observations (fills / periods). /
                        T = 觀察數（fills / periods）。
        skew: 樣本偏度 γ3。Gaussian = 0。
        excess_kurtosis: 樣本超額峰度 ke = γ4 - 3。Gaussian = 0。

    Returns / 回傳:
        PSR ∈ [0, 1]。

    Raises / 拋出:
        ValueError: invalid n_observations or numerical instability.
    """
    if n_observations < 2:
        raise ValueError(
            f"n_observations={n_observations} must be >= 2 for PSR (T-1 in denominator)"
        )

    # γ4 - 1 = excess_kurtosis + 2
    gamma_4_minus_1 = excess_kurtosis + 2.0

    # Variance term in denominator under sample Sharpe asymptotics.
    # 樣本 Sharpe 漸近分布之分母變異數項。
    variance_term = 1.0 - skew * observed_sharpe + (gamma_4_minus_1 / 4.0) * (observed_sharpe ** 2)
    if variance_term <= 0.0:
        # Numerical degenerate case (extreme skew/kurtosis); return PSR=0.5
        # to indicate undefined regime instead of crashing.
        # 數值退化（極端 skew/kurtosis）；回 0.5 表示未定義區間，避免 crash。
        logger.warning(
            "PSR variance_term=%s <= 0 (skew=%s, ke=%s, sr=%s); returning 0.5",
            variance_term,
            skew,
            excess_kurtosis,
            observed_sharpe,
        )
        return 0.5

    z_score = (observed_sharpe - sharpe_threshold) * math.sqrt(
        float(n_observations - 1)
    ) / math.sqrt(variance_term)

    return _normal_cdf(z_score)


# ─────────────────────────────────────────────────────────────────────────────
# DSR Gate class / DSR Gate 類別
# ─────────────────────────────────────────────────────────────────────────────


class DsrGate:
    """DSR(K) > 0.95 promotion gate per V3 §11 P4 Exit.

    依 V3 §11 P4 Exit 的 DSR(K) > 0.95 升級 gate。

    Composite gate that:
      1. Computes E[max SR_k] across K trials (selection bias correction).
      2. Computes DSR = PSR(E[max SR_k]) — probability observed SR exceeds
         best-of-K under Gaussian null.
      3. Returns 'promote' / 'borderline' / 'block' verdict.

    複合 gate：
      1. 計算 E[max SR_k] 跨 K trial（選擇偏差修正）。
      2. 計算 DSR = PSR(E[max SR_k]) — 觀察 SR 超過 K 中最佳之機率。
      3. 回 'promote' / 'borderline' / 'block' 判決。

    Usage / 使用:
        gate = DsrGate(threshold=0.95)
        result = gate.compute_dsr(
            observed_sharpe=2.5,
            n_trials=10,
            n_observations=500,
        )
        verdict = gate.gate(result)  # 'promote' / 'borderline' / 'block'
    """

    def __init__(self, threshold: float = DEFAULT_DSR_THRESHOLD) -> None:
        """Initialize gate with configurable threshold.

        以可配置閾值初始化 gate。

        Args / 引數:
            threshold: DSR threshold for promotion (V3 §8.3 default 0.95). /
                       升級用 DSR 閾值（V3 §8.3 預設 0.95）。
        """
        if not 0.0 < threshold < 1.0:
            raise ValueError(f"threshold={threshold} must be in (0, 1)")
        self.threshold = float(threshold)

    def compute_dsr(
        self,
        observed_sharpe: float,
        n_trials: int,
        n_observations: int = 100,
        trial_sharpes: Optional[Sequence[float]] = None,
        skew: float = 0.0,
        excess_kurtosis: float = 0.0,
    ) -> DsrResult:
        """Compute DSR(K) given observed Sharpe + K trials.

        給定觀察 Sharpe + K trials 計算 DSR(K)。

        Algorithm / 演算法:
          1. trials_max_sharpe = E[max SR_k] under Gaussian null (Bailey-LdP Eq.8).
             或當 trial_sharpes 提供時，使用樣本最大值（更精確）。
          2. deflated_sharpe = PSR(trials_max_sharpe; observed_sharpe, T, γ3, γ4).
          3. psr_at_threshold = PSR(0) — baseline P(SR > 0) for diagnostic.
          4. passes_threshold = (deflated_sharpe > self.threshold).

        Args / 引數:
            observed_sharpe: 樣本內觀察 Sharpe（所選最佳變體）。
            n_trials: K = number of variants explored. K=1 → DSR == PSR(0). /
                     K = 探索變體數。K=1 → DSR == PSR(0)。
            n_observations: T = number of observations (default 100). /
                           T = 觀察數（預設 100）。
            trial_sharpes: Optional explicit trial Sharpes; if provided,
                           uses sample max instead of theoretical E[max]. /
                           可選的明確 trial Sharpes；若提供則用樣本最大
                           取代理論 E[max]。
            skew: 樣本偏度 γ3（高斯 = 0）。
            excess_kurtosis: 樣本超額峰度 ke = γ4 - 3。

        Returns / 回傳:
            DsrResult with all six fields populated. /
            含全部六個欄位的 DsrResult。

        Raises / 拋出:
            ValueError: invalid n_trials or n_observations.
        """
        if n_trials < 1:
            raise ValueError(f"n_trials={n_trials} must be >= 1")
        if n_observations < 2:
            raise ValueError(
                f"n_observations={n_observations} must be >= 2 (PSR sqrt(T-1) requirement)"
            )

        # Step 1: Determine reference threshold (E[max SR_k]).
        # 步驟 1：決定參考閾值（E[max SR_k]）。
        if trial_sharpes is not None and len(trial_sharpes) > 0:
            trials_arr = np.asarray(list(trial_sharpes), dtype=np.float64)
            trials_arr = trials_arr[np.isfinite(trials_arr)]
            if len(trials_arr) == 0:
                trials_max = _compute_expected_max_sharpe(n_trials)
            else:
                # Use sample max — more accurate when trials are non-Gaussian.
                # 用樣本最大值 — 當 trials 非高斯時更準確。
                trials_max = float(np.max(trials_arr))
        else:
            trials_max = _compute_expected_max_sharpe(n_trials)

        # Step 2: Compute DSR = PSR at the deflated threshold.
        # 步驟 2：計算 DSR = PSR 在 deflated 閾值。
        deflated = _compute_psr(
            observed_sharpe=observed_sharpe,
            sharpe_threshold=trials_max,
            n_observations=n_observations,
            skew=skew,
            excess_kurtosis=excess_kurtosis,
        )

        # Step 3: PSR(0) baseline for diagnostic.
        # 步驟 3：PSR(0) 基線供診斷。
        psr_at_zero = _compute_psr(
            observed_sharpe=observed_sharpe,
            sharpe_threshold=0.0,
            n_observations=n_observations,
            skew=skew,
            excess_kurtosis=excess_kurtosis,
        )

        passes = deflated > self.threshold

        return DsrResult(
            observed_sharpe=float(observed_sharpe),
            deflated_sharpe=float(deflated),
            n_trials_K=int(n_trials),
            psr_at_threshold=float(psr_at_zero),
            trials_max_sharpe=float(trials_max),
            passes_threshold=bool(passes),
        )

    def gate(self, dsr_result: DsrResult) -> Literal["promote", "block", "borderline"]:
        """Decide promotion verdict from DsrResult.

        從 DsrResult 決定升級判決。

        Verdict logic / 判決邏輯:
          - DSR > self.threshold (default 0.95) → 'promote'
          - DSR ∈ [BORDERLINE_LOWER, self.threshold] → 'borderline' (review needed)
          - DSR < BORDERLINE_LOWER → 'block'

        Args / 引數:
            dsr_result: DsrResult from compute_dsr(). / 來自 compute_dsr() 的結果。

        Returns / 回傳:
            'promote' | 'block' | 'borderline'.
        """
        if dsr_result.passes_threshold:
            return "promote"
        if dsr_result.deflated_sharpe >= BORDERLINE_LOWER:
            return "borderline"
        return "block"


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience / 模組級便利函數
# ─────────────────────────────────────────────────────────────────────────────


def compute_dsr(
    observed_sharpe: float,
    n_trials: int,
    n_observations: int = 100,
    threshold: float = DEFAULT_DSR_THRESHOLD,
    trial_sharpes: Optional[Sequence[float]] = None,
) -> DsrResult:
    """Module-level shortcut for DsrGate.compute_dsr.

    DsrGate.compute_dsr 的模組級捷徑。
    """
    return DsrGate(threshold=threshold).compute_dsr(
        observed_sharpe=observed_sharpe,
        n_trials=n_trials,
        n_observations=n_observations,
        trial_sharpes=trial_sharpes,
    )

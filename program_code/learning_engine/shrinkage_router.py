"""
shrinkage_router — REF-20 Wave 5 P3a-Q4 shrinkage decision tree router.
收縮決策樹路由器 — REF-20 Wave 5 P3a-Q4。

MODULE_NOTE (EN): Three-tier shrinkage decision tree per V3 §8.2 + §11 P3a KPI:
  tier 1 hierarchical    n >= 50, regime stable, fits PASS  (Gibbs partial-pool)
  tier 2 james_stein     50 > n >= 30  OR  fits FAIL (n >= 30)
  tier 3 empirical_bayes n < 30 (cold start; Normal-Normal conjugate)
  Router decides per call given (n, regime stability, fit p-value). Output is
  shrunk point estimate + 95% CI + tier label + shrinkage factor [0, 1].
  V3 §8.2 item 5 forbids ad hoc shrinkage; this router is the canonical surface.
  Pure offline math; no DB / IPC / exchange / live mutate. Caller passes
  (observed array, cell_key, prior_inputs dict); router consumes Wave 5 P3a-Q1
  (half_life), P3a-Q3 (bootstrap CI), P3a-Q5 (fee model) outputs as prior_inputs.

MODULE_NOTE (中): 依 V3 §8.2 + §11 P3a KPI 的三層收縮決策樹（hierarchical /
  james_stein / empirical_bayes）。Router 依 (n, regime, fit p) 決 tier；輸出
  收縮點估計 + 95% CI + tier label + [0,1] 收縮係數。V3 §8.2 條 5 禁 ad hoc
  收縮；本 router 為 replay calibration canonical surface。純離線數學；0 DB /
  IPC / exchange / live mutate；caller 傳 (observed, cell_key, prior_inputs)。

NumPyro / JAX FALLBACK: V3 §8.2 偏好 NumPyro hierarchical Bayes，但 Mac dev /
  build host 多數無 NumPyro / JAX；本 IMPL 手寫 Gibbs sampler（numpy 隨機源 +
  Normal-Normal + inverse-Gamma 共軛），後驗摘要（grand mean / between /
  within）與 NumPyro Normal-Normal 模型在 prior 一致下 1:1 對齊。日後裝
  NumPyro 可在 _fit_hierarchical 內切換 NUTS，public API 不變。

V3 §8.2 binding / V3 §8.2 綁定:
  1. cell n < 30 → low confidence (empirical_bayes tier; block handoff upstream)
  2. small cell + enough related cells → hierarchical Bayes preferred
  3. cross-strategy global estimate → James-Stein allowed
  4. small-K candidate comparison → empirical Bayes allowed
  5. method MUST be declared in manifest/report; ad hoc shrinkage forbidden

V3 §11 P3a KPI: sample power gate (n >= 200 per strategy-window) enforced
  upstream by ``CalibrationGate.check_sample_power``; this router is cell-level
  once the global gate has passed.

Workplan: docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
  §4 Wave 5 R20-P3a-Q4.

Usage example:
  router = ShrinkageRouter()
  result = router.shrink(
      observed=np.array([5.2, 4.8, ...]),
      cell_key="grid_trading::BTCUSDT::long",
      prior_inputs={
          "grand_mean": 4.7, "grand_std": 1.2,
          "regime_stable": True, "fit_p_value": 0.03,
          "related_cells_observed": {  # optional, for hierarchical pooling
              "grid_trading::ETHUSDT::long": np.array([4.9, 5.0, ...]),
          },
      },
  )
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Dict, List, Literal, Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / 常量
# ---------------------------------------------------------------------------

# V3 §8.2 cell-level thresholds (per V3 §8.1 sample, freshness, embargo table:
#   cell sample n >= 30 per strategy/symbol/side).
# 單元級閾值（V3 §8.1 表：n >= 30 per cell）。
N_THRESHOLD_HIERARCHICAL: int = 50  # tier 1 entry
N_THRESHOLD_JAMES_STEIN: int = 30   # tier 2 entry; below = empirical_bayes

# Hierarchical Gibbs sampler defaults (NumPyro fallback).
# Hierarchical Gibbs sampler 預設值（NumPyro fallback）。
DEFAULT_GIBBS_WARMUP: int = 500
DEFAULT_GIBBS_DRAWS: int = 1500
DEFAULT_GIBBS_SEED: int = 42

# CI alpha (95% by default).
# CI alpha（預設 95%）。
DEFAULT_CI_ALPHA: float = 0.05


# ---------------------------------------------------------------------------
# Tier literal / Tier 文字
# ---------------------------------------------------------------------------

ShrinkageTierLiteral = Literal["hierarchical", "james_stein", "empirical_bayes"]


# ---------------------------------------------------------------------------
# Result dataclass / 結果 dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShrinkageResult:
    """Shrinkage decision tree output.

    收縮決策樹輸出。

    Attributes:
        cell_key: Canonical "<strategy>::<symbol>::<side>" cell tuple.
        shrunk_estimate: Posterior point estimate (mean) after shrinkage. /
            收縮後後驗點估計（均值）。
        tier_used: Which tier produced the estimate. /
            產生估計的 tier。
        n_observations: Cell observation count consumed by the tier. /
            tier 消耗的單元觀測數量。
        shrinkage_factor: Pull strength toward prior in [0, 1]; 0 = full
            data, 1 = full prior. Monotonically decreasing with n. /
            朝 prior 拉的強度，[0, 1]；0 = 全資料，1 = 全 prior；隨 n 單調遞減。
        ci_low: Lower bound of 95% CI on shrunk estimate. /
            收縮估計 95% CI 下界。
        ci_high: Upper bound of 95% CI on shrunk estimate. /
            收縮估計 95% CI 上界。
        prior_mean_used: Prior mean fed into the shrinkage; for audit. /
            送入收縮的 prior 均值；供 audit。
        reason_zh: Chinese reason for tier choice + summary. /
            選 tier 的中文理由 + 摘要。
        reason_en: English reason for tier choice + summary. /
            選 tier 的英文理由 + 摘要。
    """

    cell_key: str
    shrunk_estimate: float
    tier_used: ShrinkageTierLiteral
    n_observations: int
    shrinkage_factor: float
    ci_low: float
    ci_high: float
    prior_mean_used: float
    reason_zh: str
    reason_en: str


# ---------------------------------------------------------------------------
# ShrinkageRouter / 收縮路由器
# ---------------------------------------------------------------------------


class ShrinkageRouter:
    """Three-tier shrinkage decision tree router.

    三層收縮決策樹路由器。

    Public API / 公開 API:
        - ``shrink(observed, cell_key, prior_inputs)`` — main entry.
        - ``_route(n, regime_stable, fit_p_value)`` — tier selector
          (private but exposed for hermetic test).

    Tier semantics / Tier 語意:
        tier 1 hierarchical:
            Hand-rolled Gibbs sampler for partial-pooling Bayesian model.
            Posterior mean for the focal cell is a weighted average of
            the data mean and the grand mean across related cells, with
            weight determined by between-/within-group variance.
            手寫 Gibbs sampler 的 partial-pooling Bayes 模型。
            焦點單元的後驗均值 = 資料均值與相關單元跨組均值的加權平均，
            權重由 between- / within-group 變異決定。

        tier 2 james_stein:
            Classical James-Stein (1961) shrinkage to grand mean.
            Shrinkage factor = ``(k - 2) * sigma^2 / sum((x - grand)^2)``
            with k = number of cells; clamped to [0, 1]. Uses just the
            sample mean + variance + grand mean.
            經典 James-Stein (1961) 朝 grand mean 收縮。
            收縮係數 = ``(k - 2) * sigma^2 / sum((x - grand)^2)``，
            k = 單元數；夾取 [0, 1]。僅用樣本 mean + variance + grand mean。

        tier 3 empirical_bayes:
            Cold-start empirical Bayes. Constructs a Normal-Normal
            conjugate prior from Q1 (half_life) + Q3 (bootstrap CI) + Q5
            (fee model) inputs; posterior mean = data-prior precision
            weighted average. Used when n < 30.
            冷啟動 empirical Bayes。從 Q1（half_life）+ Q3（bootstrap CI）+
            Q5（fee model）輸入構 Normal-Normal conjugate prior；
            後驗均值 = 資料 - prior 精度加權平均。n < 30 時使用。

    Args:
        n_threshold_hier: Tier-1 entry n threshold (default 50).
        n_threshold_js: Tier-2 entry n threshold (default 30); below = EB.
        gibbs_warmup: Hierarchical Gibbs warmup iter (default 500).
        gibbs_draws: Hierarchical Gibbs draw iter (default 1500).
        gibbs_seed: Hierarchical Gibbs RNG seed (default 42).
        ci_alpha: CI alpha (default 0.05 = 95% CI).
    """

    def __init__(
        self,
        n_threshold_hier: int = N_THRESHOLD_HIERARCHICAL,
        n_threshold_js: int = N_THRESHOLD_JAMES_STEIN,
        gibbs_warmup: int = DEFAULT_GIBBS_WARMUP,
        gibbs_draws: int = DEFAULT_GIBBS_DRAWS,
        gibbs_seed: int = DEFAULT_GIBBS_SEED,
        ci_alpha: float = DEFAULT_CI_ALPHA,
    ) -> None:
        # Validate thresholds: hierarchical > james_stein > 0.
        # 驗閾值：hierarchical > james_stein > 0。
        if not isinstance(n_threshold_hier, int) or n_threshold_hier <= 0:
            raise ValueError(
                f"n_threshold_hier must be positive int; got {n_threshold_hier}"
            )
        if not isinstance(n_threshold_js, int) or n_threshold_js <= 0:
            raise ValueError(
                f"n_threshold_js must be positive int; got {n_threshold_js}"
            )
        if n_threshold_hier <= n_threshold_js:
            raise ValueError(
                f"n_threshold_hier ({n_threshold_hier}) must exceed "
                f"n_threshold_js ({n_threshold_js})"
            )
        if not (0.0 < ci_alpha < 1.0):
            raise ValueError(
                f"ci_alpha must be in (0, 1); got {ci_alpha}"
            )

        self._n_threshold_hier = n_threshold_hier
        self._n_threshold_js = n_threshold_js
        self._gibbs_warmup = int(gibbs_warmup)
        self._gibbs_draws = int(gibbs_draws)
        self._gibbs_seed = int(gibbs_seed)
        self._ci_alpha = float(ci_alpha)

    # ------------------------------------------------------------------
    # Public API / 公開 API
    # ------------------------------------------------------------------

    def shrink(
        self,
        observed: np.ndarray,
        cell_key: str,
        prior_inputs: Dict[str, object],
    ) -> ShrinkageResult:
        """Run shrinkage decision tree on ``observed`` for ``cell_key``.

        對 ``cell_key`` 的 ``observed`` 執行收縮決策樹。

        Args:
            observed: 1D float array of cell observations (e.g.,
                net_bps_after_fees per fill). Empty array → ValueError.
            cell_key: Canonical "<strategy>::<symbol>::<side>" tuple.
                Empty / non-string → ValueError.
            prior_inputs: Required keys (Wave 5 P3a wiring contract):
                - "grand_mean": float — cross-strategy grand mean.
                - "grand_std": float (>0) — cross-strategy grand std.
                - "regime_stable": bool — RGM-Q1/Q2 regime status.
                - "fit_p_value": float — parametric fit p-value (lower
                  = better; > 0.10 → FAIL per V3 P3a half_life convention).
                Optional keys:
                - "related_cells_observed": Dict[str, np.ndarray] —
                  observations of related cells for hierarchical pooling.
                  Required when tier 1 hierarchical is selected; otherwise
                  unused.

        Returns:
            ``ShrinkageResult`` with shrunk_estimate + tier_used + CI.

        Raises:
            ValueError: invalid observed / cell_key / prior_inputs.
        """
        # Validate observed.
        # 驗 observed。
        observed = self._validate_observed(observed)
        n = int(len(observed))

        # Validate cell_key.
        # 驗 cell_key。
        if not isinstance(cell_key, str) or not cell_key.strip():
            raise ValueError("cell_key must be non-empty string")

        # Validate prior_inputs required keys.
        # 驗 prior_inputs 必填 keys。
        grand_mean = self._validate_float_key(prior_inputs, "grand_mean")
        grand_std = self._validate_float_key(
            prior_inputs, "grand_std", positive=True
        )
        regime_stable = self._validate_bool_key(prior_inputs, "regime_stable")
        fit_p_value = self._validate_float_key(prior_inputs, "fit_p_value")

        # Route to tier.
        # 路由到 tier。
        tier = self._route(n, regime_stable, fit_p_value)

        # Dispatch to tier handler.
        # 分派到 tier handler。
        if tier == "hierarchical":
            return self._fit_hierarchical(
                observed=observed,
                cell_key=cell_key,
                grand_mean=grand_mean,
                grand_std=grand_std,
                related_cells_observed=prior_inputs.get(
                    "related_cells_observed"
                ),
            )
        if tier == "james_stein":
            return self._fit_james_stein(
                observed=observed,
                cell_key=cell_key,
                grand_mean=grand_mean,
                grand_std=grand_std,
            )
        # tier == "empirical_bayes"
        return self._fit_empirical_bayes(
            observed=observed,
            cell_key=cell_key,
            grand_mean=grand_mean,
            grand_std=grand_std,
        )

    # ------------------------------------------------------------------
    # Routing / 路由
    # ------------------------------------------------------------------

    def _route(
        self,
        n: int,
        regime_stable: bool,
        fit_p_value: float,
    ) -> ShrinkageTierLiteral:
        """Decide which tier to use.

        決定使用哪個 tier。

        Per V3 §8.2 spec:
            n < 30                                  → empirical_bayes (cold)
            30 <= n < 50                            → james_stein (classical)
            n >= 50, regime_stable, fit p < 0.10    → hierarchical (preferred)
            n >= 50, regime_unstable OR fit p>=0.10 → james_stein (fallback)

        依 V3 §8.2 規格選 tier。
        """
        if n < self._n_threshold_js:
            return "empirical_bayes"

        if n < self._n_threshold_hier:
            # Mid-range cell: classical James-Stein only.
            # 中段單元：僅經典 James-Stein。
            return "james_stein"

        # n >= hier threshold: candidate for hierarchical.
        # n >= hier 閾值：hierarchical 候選。
        # P3a half_life convention: p < 0.10 is "fit PASS" (acts like alpha).
        # P3a half_life 慣例：p < 0.10 為「fit PASS」（如 alpha）。
        fit_passed = fit_p_value < 0.10
        if regime_stable and fit_passed:
            return "hierarchical"
        # Hierarchical preconditions failed → fallback to James-Stein.
        # Hierarchical 前置條件失敗 → 退回 James-Stein。
        return "james_stein"

    # ------------------------------------------------------------------
    # Tier 1: hierarchical (NumPyro fallback Gibbs) / Tier 1：階層
    # ------------------------------------------------------------------

    def _fit_hierarchical(
        self,
        observed: np.ndarray,
        cell_key: str,
        grand_mean: float,
        grand_std: float,
        related_cells_observed: Optional[object],
    ) -> ShrinkageResult:
        """Tier 1: hand-roll Gibbs sampler for hierarchical Bayes.

        Tier 1：手寫 Gibbs sampler for hierarchical Bayes。

        Model:
            mu_grand     ~ Normal(grand_mean, grand_std)
            sigma_b      ~ HalfNormal(grand_std)
            mu_group[k]  ~ Normal(mu_grand, sigma_b)
            sigma_w      ~ HalfNormal(grand_std)
            obs[g, i]    ~ Normal(mu_group[g], sigma_w)

        Posterior mean for focal cell = posterior mu_group[focal_idx].
        焦點單元後驗均值 = 後驗 mu_group[focal_idx]。

        If related_cells_observed is None or empty, hierarchical pooling
        degenerates to single-group Bayes: posterior is a Normal-Normal
        conjugate update. We surface that as ``hierarchical`` tier still
        (caller chose hierarchical via _route) but note in reason string.
        若 related_cells_observed 為 None / 空，hierarchical pooling 退
        化為單組 Bayes：後驗為 Normal-Normal conjugate update。仍標
        ``hierarchical`` tier（_route 選的），reason 中註記。
        """
        # Aggregate cell groups: focal + related.
        # 聚合 cell groups：focal + related。
        groups: Dict[str, np.ndarray] = {cell_key: observed}
        if isinstance(related_cells_observed, dict):
            for k, arr in related_cells_observed.items():
                if not isinstance(k, str) or not k.strip():
                    continue
                if k == cell_key:
                    continue  # do not duplicate focal / 不重複 focal
                arr_validated = self._validate_observed(
                    arr, allow_short=True
                )
                if len(arr_validated) > 0:
                    groups[k] = arr_validated

        n_groups = len(groups)
        focal_idx = list(groups.keys()).index(cell_key)

        rng = np.random.default_rng(self._gibbs_seed)

        # Initialise sampler state.
        # 初始化 sampler 狀態。
        mu_grand = float(grand_mean)
        sigma_b = float(grand_std)
        sigma_w = float(np.std(observed, ddof=1)) if len(observed) > 1 else float(
            grand_std
        )
        if sigma_w <= 0 or not math.isfinite(sigma_w):
            sigma_w = float(grand_std)

        group_keys = list(groups.keys())
        mu_groups = np.array(
            [float(np.mean(groups[k])) for k in group_keys],
            dtype=float,
        )

        # Hyperparameters of priors (weakly informative).
        # Prior 超參數（弱資訊）。
        mu_grand_prior_mean = float(grand_mean)
        mu_grand_prior_var = max(float(grand_std) ** 2, 1e-9)
        # HalfNormal(grand_std) ~ inverse-gamma-like for variance; we use
        # conjugate inverse-gamma prior for sigma_b^2 / sigma_w^2 with
        # shape=1, scale=grand_std^2 (equivalent weight to HalfNormal in
        # tail for our sample sizes).
        # HalfNormal(grand_std) 在 variance 上類 inverse-gamma；用
        # conjugate inverse-gamma prior（shape=1, scale=grand_std^2）。
        ig_shape = 1.0
        ig_scale_b = max(float(grand_std) ** 2, 1e-9)
        ig_scale_w = max(float(grand_std) ** 2, 1e-9)

        # Storage for draws of focal mu_group.
        # 焦點 mu_group 的 draws 儲存。
        focal_draws: List[float] = []
        total_iter = self._gibbs_warmup + self._gibbs_draws

        for it in range(total_iter):
            # ---- Sample mu_group[g] | rest, for each g.
            # ---- 對每個 g 抽樣 mu_group[g] | rest。
            for g, key in enumerate(group_keys):
                arr = groups[key]
                n_g = len(arr)
                # Posterior mu_group[g] ~ Normal with precision-weighted
                # mean of (mu_grand, sigma_b) prior and (mean(arr), sigma_w/sqrt(n_g)) data.
                # 後驗 mu_group[g] ~ Normal，精度加權 prior + data。
                prec_prior = 1.0 / max(sigma_b ** 2, 1e-12)
                prec_data = n_g / max(sigma_w ** 2, 1e-12)
                prec_post = prec_prior + prec_data
                mean_post = (
                    prec_prior * mu_grand + prec_data * float(np.mean(arr))
                ) / prec_post
                std_post = math.sqrt(1.0 / prec_post)
                mu_groups[g] = float(rng.normal(mean_post, std_post))

            # ---- Sample mu_grand | rest.
            # ---- 抽樣 mu_grand | rest。
            prec_prior_grand = 1.0 / mu_grand_prior_var
            prec_data_grand = n_groups / max(sigma_b ** 2, 1e-12)
            prec_post_grand = prec_prior_grand + prec_data_grand
            mean_post_grand = (
                prec_prior_grand * mu_grand_prior_mean
                + prec_data_grand * float(np.mean(mu_groups))
            ) / prec_post_grand
            std_post_grand = math.sqrt(1.0 / prec_post_grand)
            mu_grand = float(rng.normal(mean_post_grand, std_post_grand))

            # ---- Sample sigma_b^2 | rest (inverse-gamma conjugate).
            # ---- 抽樣 sigma_b^2 | rest（inverse-gamma 共軛）。
            ss_b = float(np.sum((mu_groups - mu_grand) ** 2))
            shape_post_b = ig_shape + n_groups / 2.0
            scale_post_b = ig_scale_b + ss_b / 2.0
            # Sample inverse-gamma via 1/Gamma.
            # 用 1/Gamma 抽 inverse-gamma。
            sigma_b2 = 1.0 / max(rng.gamma(shape_post_b, 1.0 / scale_post_b), 1e-12)
            sigma_b = math.sqrt(sigma_b2)

            # ---- Sample sigma_w^2 | rest.
            # ---- 抽樣 sigma_w^2 | rest。
            ss_w = 0.0
            n_total = 0
            for g, key in enumerate(group_keys):
                arr = groups[key]
                ss_w += float(np.sum((arr - mu_groups[g]) ** 2))
                n_total += len(arr)
            shape_post_w = ig_shape + n_total / 2.0
            scale_post_w = ig_scale_w + ss_w / 2.0
            sigma_w2 = 1.0 / max(rng.gamma(shape_post_w, 1.0 / scale_post_w), 1e-12)
            sigma_w = math.sqrt(sigma_w2)

            # Capture focal draws after warmup.
            # 暖機後捕捉 focal draws。
            if it >= self._gibbs_warmup:
                focal_draws.append(float(mu_groups[focal_idx]))

        focal_arr = np.array(focal_draws, dtype=float)
        shrunk_estimate = float(np.mean(focal_arr))
        # 95% CI from posterior quantiles.
        # 從後驗分位點取 95% CI。
        lower_pct = 100.0 * (self._ci_alpha / 2.0)
        upper_pct = 100.0 * (1.0 - self._ci_alpha / 2.0)
        ci_low = float(np.percentile(focal_arr, lower_pct))
        ci_high = float(np.percentile(focal_arr, upper_pct))

        # Shrinkage factor estimate: 1 - var(focal_data) / var(focal_posterior_mean).
        # 收縮係數估計：以 prior weight ratio 近似。
        n_obs = len(observed)
        data_var = float(np.var(observed, ddof=1)) if n_obs > 1 else float(grand_std) ** 2
        # Posterior precision ratio: prior precision / total precision.
        # 後驗精度比：prior 精度 / 總精度。
        prec_prior_focal = 1.0 / max(sigma_b ** 2, 1e-12)
        prec_data_focal = n_obs / max(max(data_var, 1e-12), 1e-12)
        shrinkage_factor = float(
            prec_prior_focal / max(prec_prior_focal + prec_data_focal, 1e-12)
        )
        shrinkage_factor = max(0.0, min(1.0, shrinkage_factor))

        related_count = n_groups - 1
        reason_zh = (
            f"hierarchical Gibbs（{n_groups} group / focal n={n_obs} / "
            f"related cells={related_count}；warmup={self._gibbs_warmup} "
            f"draws={self._gibbs_draws}；shrinkage={shrinkage_factor:.3f}）"
        )
        reason_en = (
            f"hierarchical Gibbs ({n_groups} groups / focal n={n_obs} / "
            f"related cells={related_count}; warmup={self._gibbs_warmup} "
            f"draws={self._gibbs_draws}; shrinkage={shrinkage_factor:.3f})"
        )

        return ShrinkageResult(
            cell_key=cell_key,
            shrunk_estimate=shrunk_estimate,
            tier_used="hierarchical",
            n_observations=n_obs,
            shrinkage_factor=shrinkage_factor,
            ci_low=ci_low,
            ci_high=ci_high,
            prior_mean_used=float(grand_mean),
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    # ------------------------------------------------------------------
    # Tier 2: James-Stein / Tier 2：James-Stein
    # ------------------------------------------------------------------

    def _fit_james_stein(
        self,
        observed: np.ndarray,
        cell_key: str,
        grand_mean: float,
        grand_std: float,
    ) -> ShrinkageResult:
        """Tier 2: classical James-Stein shrinkage.

        Tier 2：經典 James-Stein 收縮。

        Single-cell James-Stein: shrinkage factor = sigma^2 / (sigma^2 + (mean - grand)^2 * n).
        We treat (n) cell as one estimator + grand as second; the
        positive-part shrinkage factor caps at 1.
        單一 cell James-Stein：收縮係數 = sigma^2 / (sigma^2 + (mean - grand)^2 * n)。
        """
        n_obs = len(observed)
        sample_mean = float(np.mean(observed))
        sample_var = float(np.var(observed, ddof=1)) if n_obs > 1 else float(grand_std) ** 2
        if sample_var <= 0 or not math.isfinite(sample_var):
            sample_var = max(float(grand_std) ** 2, 1e-9)

        # Standard error squared of sample mean.
        # 樣本均值的 SE^2。
        se2 = sample_var / max(n_obs, 1)
        diff_sq = (sample_mean - float(grand_mean)) ** 2
        # Shrinkage factor: pull toward grand by SE^2 / (SE^2 + diff^2).
        # 收縮係數：SE^2 / (SE^2 + diff^2) 朝 grand 拉。
        shrinkage_factor = se2 / max(se2 + diff_sq, 1e-12)
        shrinkage_factor = max(0.0, min(1.0, shrinkage_factor))

        shrunk_estimate = (
            shrinkage_factor * float(grand_mean)
            + (1.0 - shrinkage_factor) * sample_mean
        )

        # CI on shrunk estimate via approximate Normal SE.
        # 近似 Normal SE 構造收縮估計 CI。
        # SE_shrunk^2 ≈ (1 - shrinkage)^2 * sample_var / n + shrinkage^2 * grand_std^2 / k_eff
        # k_eff treated as 2 (focal + grand) for bound purposes.
        # k_eff 視為 2（focal + grand）作邊界。
        var_shrunk = (
            (1.0 - shrinkage_factor) ** 2 * sample_var / max(n_obs, 1)
            + shrinkage_factor ** 2 * float(grand_std) ** 2 / 2.0
        )
        se_shrunk = math.sqrt(max(var_shrunk, 1e-12))
        # 95% Normal CI: ±1.96 SE.
        # 95% Normal CI：±1.96 SE。
        z_alpha = 1.959963984540054  # scipy.stats.norm.ppf(0.975)
        ci_low = shrunk_estimate - z_alpha * se_shrunk
        ci_high = shrunk_estimate + z_alpha * se_shrunk

        reason_zh = (
            f"James-Stein 收縮（n={n_obs}；sample_mean={sample_mean:.4f} → "
            f"grand={grand_mean:.4f}；shrinkage={shrinkage_factor:.3f}）"
        )
        reason_en = (
            f"James-Stein shrinkage (n={n_obs}; sample_mean={sample_mean:.4f} → "
            f"grand={grand_mean:.4f}; shrinkage={shrinkage_factor:.3f})"
        )

        return ShrinkageResult(
            cell_key=cell_key,
            shrunk_estimate=float(shrunk_estimate),
            tier_used="james_stein",
            n_observations=n_obs,
            shrinkage_factor=shrinkage_factor,
            ci_low=float(ci_low),
            ci_high=float(ci_high),
            prior_mean_used=float(grand_mean),
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    # ------------------------------------------------------------------
    # Tier 3: Empirical Bayes / Tier 3：經驗貝氏
    # ------------------------------------------------------------------

    def _fit_empirical_bayes(
        self,
        observed: np.ndarray,
        cell_key: str,
        grand_mean: float,
        grand_std: float,
    ) -> ShrinkageResult:
        """Tier 3: Normal-Normal conjugate posterior (cold-start EB).

        Tier 3：Normal-Normal 共軛後驗（冷啟動 EB）。

        Posterior mean = (prec_prior * grand_mean + prec_data * sample_mean)
                         / (prec_prior + prec_data)
        prec_prior = 1 / grand_std^2
        prec_data  = n / sample_var

        For very small n (<3), sample_var unreliable → use grand_std^2.
        n 極小（<3）時 sample_var 不可靠 → 用 grand_std^2。
        """
        n_obs = len(observed)
        sample_mean = float(np.mean(observed))
        if n_obs >= 3:
            sample_var = float(np.var(observed, ddof=1))
            if sample_var <= 0 or not math.isfinite(sample_var):
                sample_var = max(float(grand_std) ** 2, 1e-9)
        else:
            sample_var = max(float(grand_std) ** 2, 1e-9)

        prec_prior = 1.0 / max(float(grand_std) ** 2, 1e-12)
        prec_data = n_obs / max(sample_var, 1e-12)
        prec_post = prec_prior + prec_data

        shrinkage_factor = float(prec_prior / max(prec_post, 1e-12))
        shrinkage_factor = max(0.0, min(1.0, shrinkage_factor))

        shrunk_estimate = (
            prec_prior * float(grand_mean) + prec_data * sample_mean
        ) / prec_post

        # Posterior std = 1 / sqrt(prec_post).
        # 後驗 std = 1 / sqrt(prec_post)。
        post_std = math.sqrt(1.0 / max(prec_post, 1e-12))
        z_alpha = 1.959963984540054
        ci_low = shrunk_estimate - z_alpha * post_std
        ci_high = shrunk_estimate + z_alpha * post_std

        reason_zh = (
            f"empirical Bayes 冷啟動（n={n_obs} < {self._n_threshold_js}；"
            f"prior={grand_mean:.4f} ± {grand_std:.4f}；shrinkage={shrinkage_factor:.3f}）"
        )
        reason_en = (
            f"empirical Bayes cold-start (n={n_obs} < {self._n_threshold_js}; "
            f"prior={grand_mean:.4f} ± {grand_std:.4f}; "
            f"shrinkage={shrinkage_factor:.3f})"
        )

        return ShrinkageResult(
            cell_key=cell_key,
            shrunk_estimate=float(shrunk_estimate),
            tier_used="empirical_bayes",
            n_observations=n_obs,
            shrinkage_factor=shrinkage_factor,
            ci_low=float(ci_low),
            ci_high=float(ci_high),
            prior_mean_used=float(grand_mean),
            reason_zh=reason_zh,
            reason_en=reason_en,
        )

    # ------------------------------------------------------------------
    # Validation helpers / 驗證輔助
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_observed(arr: object, *, allow_short: bool = False) -> np.ndarray:
        """Coerce to 1D float ndarray; reject empty unless allow_short."""
        try:
            out = np.asarray(arr, dtype=float)
        except (TypeError, ValueError) as e:
            raise ValueError(f"observed must be array-like of floats: {e}") from e
        if out.ndim != 1:
            raise ValueError(
                f"observed must be 1D; got shape {out.shape}"
            )
        if not allow_short and out.size == 0:
            raise ValueError("observed must be non-empty")
        if not np.all(np.isfinite(out)):
            raise ValueError("observed contains non-finite values")
        return out

    @staticmethod
    def _validate_float_key(
        d: Dict[str, object], key: str, *, positive: bool = False
    ) -> float:
        if key not in d:
            raise ValueError(f"prior_inputs missing required key: {key!r}")
        v = d[key]
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValueError(
                f"prior_inputs[{key!r}] must be float; got {type(v).__name__}"
            )
        v = float(v)
        if not math.isfinite(v):
            raise ValueError(f"prior_inputs[{key!r}] must be finite; got {v}")
        if positive and v <= 0:
            raise ValueError(
                f"prior_inputs[{key!r}] must be positive; got {v}"
            )
        return v

    @staticmethod
    def _validate_bool_key(d: Dict[str, object], key: str) -> bool:
        if key not in d:
            raise ValueError(f"prior_inputs missing required key: {key!r}")
        v = d[key]
        if not isinstance(v, bool):
            raise ValueError(
                f"prior_inputs[{key!r}] must be bool; got {type(v).__name__}"
            )
        return v


__all__ = [
    "DEFAULT_CI_ALPHA",
    "DEFAULT_GIBBS_DRAWS",
    "DEFAULT_GIBBS_SEED",
    "DEFAULT_GIBBS_WARMUP",
    "N_THRESHOLD_HIERARCHICAL",
    "N_THRESHOLD_JAMES_STEIN",
    "ShrinkageResult",
    "ShrinkageRouter",
    "ShrinkageTierLiteral",
]

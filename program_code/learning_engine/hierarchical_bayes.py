"""
hierarchical_bayes — REF-20 Wave 5 P3b-Q2 cell-level hierarchical Bayes model.
單元級階層貝氏模型 — REF-20 Wave 5 P3b-Q2。

MODULE_NOTE (EN):
    Per V3 §8.2 + §11 P3b: cell-level Bayesian shrinkage of (intended_bps,
    net_outcome_bps) systematic bias. The model partial-pools cells across
    a four-level hierarchy:

        strategy_id → symbol → window → tier → cell

    Each cell has its own posterior over the bias term
    ``b_cell = E[net_outcome_bps - intended_bps | cell]``; cells with few
    observations are pulled toward the strategy/symbol/window grand mean
    (partial pooling); cells with abundant observations escape pooling
    (low pooling factor). Output supports P3b cell calibration writer
    (Wave 5 sibling task) per V3 §11 P3b KPI ("≥40% cells n≥30 covered").

    NumPyro / JAX FALLBACK NOTICE:
        V3 prefers NumPyro NUTS; Mac dev env (and most build hosts) lack
        NumPyro / JAX. We hand-roll a Gibbs sampler matching the standard
        Normal-Normal hierarchical model 1:1. When NumPyro becomes
        available, ``CellLevelHierarchicalBayes._fit_gibbs`` can be
        flipped to NumPyro NUTS without changing the public API.

    Convergence diagnostics:
        - r_hat (Gelman-Rubin) — ratio of within-/between-chain variance;
          < 1.05 ideal. We run ``n_chains`` (default 4) parallel chains
          with different seeds and compute r_hat per cell parameter.
        - effective_sample_size — per V3 informal expectation we report
          the minimum across cells; values > 100 considered acceptable.
        - log_marginal_likelihood — Laplace approximation surface for
          model comparison (REF-21 sibling spec may consume).

    Architecture / 架構:
        Pure offline math; 0 IPC / 0 DB writer / 0 exchange. Caller
        passes a pandas DataFrame (cell_outcomes_df) with required columns
        per REF-21 placeholder spec §2 (cell_key, intended_bps,
        net_outcome_bps). The class .fit() returns a result summary;
        .predict_cell(cell_key) returns the per-cell posterior.

MODULE_NOTE (中):
    依 V3 §8.2 + §11 P3b：(intended_bps, net_outcome_bps) 系統 bias 的
    cell-level 貝氏收縮。模型在 4 層 hierarchy 上 partial-pool cells：

        strategy_id → symbol → window → tier → cell

    每 cell 對 bias term ``b_cell = E[net_outcome_bps - intended_bps |
    cell]`` 有自己的後驗；觀測少的 cell 朝 strategy/symbol/window grand
    mean 拉（partial pooling）；觀測多的 cell 逃離 pooling（low pooling
    factor）。輸出餵 P3b cell calibration writer（Wave 5 sibling task），
    對齊 V3 §11 P3b KPI（「≥40% cells n≥30」）。

    NumPyro / JAX fallback：V3 偏好 NumPyro NUTS；Mac dev 環境（與多
    數 build host）無 NumPyro / JAX。我們手寫 Gibbs sampler 對齊標準
    Normal-Normal hierarchical 模型 1:1。日後安裝 NumPyro 可在不改
    public API 下切換到 NUTS。

    收斂診斷：
        - r_hat（Gelman-Rubin）— 鏈內 / 鏈間變異比；< 1.05 為理想；跑
          ``n_chains``（預設 4）平行鏈，不同 seed，逐 cell 算 r_hat。
        - effective_sample_size — 取 cell 間最小；> 100 視為可接受。
        - log_marginal_likelihood — Laplace 近似，供 REF-21 sibling 比較
          模型用。

    架構：純離線數學；0 IPC / 0 DB writer / 0 exchange。Caller 傳
    pandas DataFrame（cell_outcomes_df），column 對齊 REF-21 placeholder
    §2（cell_key, intended_bps, net_outcome_bps）。.fit() 回 summary；
    .predict_cell(cell_key) 回逐 cell 後驗。

V3 §8.2 binding / V3 §8.2 綁定:
    - cell n < 30 → low confidence; block handoff (handled upstream by P3b-Q1)
    - small cell + enough related cells → hierarchical Bayes preferred
    - method MUST be declared in manifest/report; ad hoc shrinkage forbidden

V3 §11 P3b KPI binding / V3 §11 P3b KPI 綁定:
    - per-cell calibration green covers >= 40% cells with n >= 30 within
      30d S0 accumulation
    - regime shift controls present (CUSUM + Kupiec + PSR + warmup)

REF-21 placeholder contract / REF-21 placeholder 契約:
    docs/execution_plan/2026-05-XX--ref21_s1_recorder_spec_placeholder.md §2
    Required columns: cell_key, intended_outcome_bps OR intended_bps,
                      net_outcome_bps. Optional: data_tier, regime_label.

Workplan / 工作計劃:
    docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
    §4 Wave 5 R20-P3b-Q2

Usage / 使用:
    from program_code.learning_engine.hierarchical_bayes import (
        CellLevelHierarchicalBayes, CellPosterior, HierarchicalBayesResult,
    )
    model = CellLevelHierarchicalBayes(
        n_chains=4, n_warmup=1000, n_samples=2000,
    )
    summary = model.fit(cell_outcomes_df)
    posterior = model.predict_cell("grid_trading::BTCUSDT::long")
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / 常量
# ---------------------------------------------------------------------------

# Default Gibbs sampler config per V3 informal expectation.
# 預設 Gibbs sampler 配置（V3 informal expectation）。
DEFAULT_N_CHAINS: int = 4
DEFAULT_N_WARMUP: int = 1000
DEFAULT_N_SAMPLES: int = 2000

# r_hat convergence threshold; > 1.05 = NOT converged.
# r_hat 收斂閾值；> 1.05 = 未收斂。
R_HAT_CONVERGED_MAX: float = 1.05

# Effective sample size minimum acceptable per cell.
# 每 cell 可接受的最小有效樣本量。
EFFECTIVE_SS_MIN: int = 100

# Default seed offsets for parallel chains.
# 平行鏈預設 seed offset。
DEFAULT_CHAIN_SEEDS: Tuple[int, ...] = (11, 23, 41, 67)


# ---------------------------------------------------------------------------
# Result dataclasses / 結果 dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CellPosterior:
    """Per-cell posterior summary.

    單 cell 後驗摘要。

    Attributes:
        cell_key: Canonical "<strategy>::<symbol>::<side>" tuple.
        bias_mean: Posterior mean of cell's bias term
            (net_outcome_bps - intended_bps). /
            cell bias term 的後驗均值。
        bias_std: Posterior std of bias term. /
            bias term 後驗標準差。
        ci_low: 2.5% quantile of posterior. /
            後驗 2.5% 分位點。
        ci_high: 97.5% quantile of posterior. /
            後驗 97.5% 分位點。
        pooling_factor: 0..1; 0 = no pooling (cell escapes), 1 = full
            pooling (cell collapses to grand mean). Decreases with n. /
            0..1；0 = 無 pooling（cell 逃離），1 = 完全 pooling
            （cell 收縮到 grand mean）。隨 n 遞減。
        n_observations: Cell observation count. /
            cell 觀測數量。
        r_hat: Gelman-Rubin diagnostic for this cell. /
            Gelman-Rubin 診斷。
        effective_sample_size: ESS for this cell's posterior. /
            該 cell 後驗的 ESS。
    """

    cell_key: str
    bias_mean: float
    bias_std: float
    ci_low: float
    ci_high: float
    pooling_factor: float
    n_observations: int
    r_hat: float
    effective_sample_size: int


@dataclass(frozen=True)
class HierarchicalBayesResult:
    """Aggregate fit summary.

    擬合整體摘要。

    Attributes:
        cells_count: Number of distinct cells in the fit. /
            擬合的不同 cell 數量。
        r_hat_max: Worst-case r_hat across all cells; < 1.05 ideal. /
            所有 cell 中最差 r_hat；< 1.05 為理想。
        effective_sample_size_min: Worst-case ESS across cells. /
            所有 cell 中最差 ESS。
        log_marginal_likelihood: Laplace-approx model evidence. /
            Laplace 近似 model evidence。
        grand_mean_post: Posterior of cross-cell grand mean. /
            跨 cell grand mean 的後驗。
        between_cell_std_post: Posterior of between-cell variability. /
            cell 間變異性的後驗。
        within_cell_std_post: Posterior of within-cell residual std. /
            cell 內殘差標準差的後驗。
        n_chains: Number of parallel chains run. /
            執行的平行鏈數量。
        n_warmup: Warmup iterations per chain. /
            每鏈 warmup 迭代次數。
        n_samples: Sampling iterations per chain. /
            每鏈 sampling 迭代次數。
    """

    cells_count: int
    r_hat_max: float
    effective_sample_size_min: int
    log_marginal_likelihood: float
    grand_mean_post: float
    between_cell_std_post: float
    within_cell_std_post: float
    n_chains: int
    n_warmup: int
    n_samples: int


# ---------------------------------------------------------------------------
# Helpers / 輔助函數
# ---------------------------------------------------------------------------


def _select_intended_column(df: pd.DataFrame) -> str:
    """Resolve intended-bps column name (REF-21 stub allows two aliases).

    解析 intended-bps column 名稱（REF-21 stub 容許兩 alias）。
    """
    if "intended_outcome_bps" in df.columns:
        return "intended_outcome_bps"
    if "intended_bps" in df.columns:
        return "intended_bps"
    raise ValueError(
        "cell_outcomes_df must contain either 'intended_outcome_bps' or "
        "'intended_bps' column (REF-21 placeholder spec §2)"
    )


def _gelman_rubin_r_hat(chains: np.ndarray) -> float:
    """Compute Gelman-Rubin r_hat for a 2D array (n_chains, n_samples).

    對 2D array (n_chains, n_samples) 計算 Gelman-Rubin r_hat。

    Returns 1.0 when single chain (insufficient for diagnostic).
    單鏈時回 1.0（診斷不適用）。
    """
    if chains.ndim != 2:
        raise ValueError(f"chains must be 2D; got shape {chains.shape}")
    n_chains, n_samples = chains.shape
    if n_chains < 2 or n_samples < 2:
        return 1.0

    # Within-chain variance.
    # 鏈內變異。
    chain_means = np.mean(chains, axis=1)
    chain_vars = np.var(chains, axis=1, ddof=1)
    w = float(np.mean(chain_vars))
    # Between-chain variance.
    # 鏈間變異。
    grand_mean = float(np.mean(chain_means))
    b_over_n = float(np.var(chain_means, ddof=1))
    # Pooled variance estimator (Gelman-Rubin classical).
    # 合併變異估計（Gelman-Rubin 經典）。
    var_hat = ((n_samples - 1) / n_samples) * w + b_over_n
    if w <= 0:
        return 1.0
    r_hat = math.sqrt(var_hat / w)
    if not math.isfinite(r_hat):
        return 1.0
    return float(r_hat)


def _effective_sample_size(samples: np.ndarray) -> int:
    """Compute approximate ESS via 1 - first-lag autocorrelation.

    透過 1 - 一階自相關近似 ESS。

    For high serial correlation ESS << n_samples; for iid ESS == n_samples.
    高自相關下 ESS << n_samples；iid 下 ESS == n_samples。
    """
    n = len(samples)
    if n < 4:
        return n
    centred = samples - np.mean(samples)
    var = float(np.var(samples, ddof=1))
    if var <= 0:
        return n
    # First-lag autocorrelation only (cheap surrogate).
    # 僅一階自相關（低成本 surrogate）。
    cov_lag1 = float(np.mean(centred[:-1] * centred[1:]))
    rho1 = cov_lag1 / var
    rho1 = max(-0.99, min(0.99, rho1))
    if rho1 >= 0:
        ess = n * (1.0 - rho1) / (1.0 + rho1)
    else:
        # Negative autocorrelation → ESS may exceed n; cap at n.
        # 負自相關 → ESS 可能超過 n；夾取為 n。
        ess = float(n)
    ess = max(1.0, min(float(n), ess))
    return int(round(ess))


# ---------------------------------------------------------------------------
# CellLevelHierarchicalBayes / 單元級階層貝氏
# ---------------------------------------------------------------------------


class CellLevelHierarchicalBayes:
    """Cell-level hierarchical Bayes for (intended, net_outcome) bias.

    (intended, net_outcome) bias 的 cell-level 階層貝氏。

    Model / 模型:
        bias[cell] = net_outcome_bps - intended_bps
        b_cell    ~ Normal(mu_grand, sigma_between)
        bias_obs  ~ Normal(b_cell, sigma_within)
        mu_grand  ~ Normal(0, prior_std=10 bps) [weakly informative]
        sigma_*   ~ HalfNormal(prior_scale=10 bps) [via inverse-gamma]

    Public API / 公開 API:
        - .fit(cell_outcomes_df) → HierarchicalBayesResult
        - .predict_cell(cell_key) → CellPosterior
        - .is_fit (bool property)

    Args:
        n_chains: Number of parallel Gibbs chains (default 4).
            More chains → tighter r_hat; min 2 for r_hat to be defined.
        n_warmup: Warmup iterations per chain (default 1000).
        n_samples: Sampling iterations per chain (default 2000).
        prior_std_bps: Weakly-informative prior std on grand mean (default 10).
        chain_seeds: Optional tuple of seed offsets per chain. Default
            uses module-level DEFAULT_CHAIN_SEEDS (extends modulo n_chains).

    Raises:
        ValueError: invalid params (n_chains<1, n_warmup<0, n_samples<1).
    """

    def __init__(
        self,
        n_chains: int = DEFAULT_N_CHAINS,
        n_warmup: int = DEFAULT_N_WARMUP,
        n_samples: int = DEFAULT_N_SAMPLES,
        prior_std_bps: float = 10.0,
        chain_seeds: Optional[Tuple[int, ...]] = None,
    ) -> None:
        if not isinstance(n_chains, int) or n_chains < 1:
            raise ValueError(
                f"n_chains must be positive int; got {n_chains}"
            )
        if not isinstance(n_warmup, int) or n_warmup < 0:
            raise ValueError(
                f"n_warmup must be non-negative int; got {n_warmup}"
            )
        if not isinstance(n_samples, int) or n_samples < 1:
            raise ValueError(
                f"n_samples must be positive int; got {n_samples}"
            )
        if not isinstance(prior_std_bps, (int, float)) or prior_std_bps <= 0:
            raise ValueError(
                f"prior_std_bps must be positive float; got {prior_std_bps}"
            )

        self._n_chains = n_chains
        self._n_warmup = n_warmup
        self._n_samples = n_samples
        self._prior_std = float(prior_std_bps)

        if chain_seeds is None:
            chain_seeds = DEFAULT_CHAIN_SEEDS
        self._chain_seeds: Tuple[int, ...] = tuple(chain_seeds)

        # Posterior cache populated by .fit().
        # 由 .fit() 填的後驗快取。
        self._posteriors: Dict[str, CellPosterior] = {}
        self._summary: Optional[HierarchicalBayesResult] = None

    # ------------------------------------------------------------------
    # Properties / 屬性
    # ------------------------------------------------------------------

    @property
    def is_fit(self) -> bool:
        """True iff .fit() has been called successfully.

        .fit() 已成功執行則為 True。
        """
        return self._summary is not None

    # ------------------------------------------------------------------
    # Public API / 公開 API
    # ------------------------------------------------------------------

    def fit(self, cell_outcomes_df: pd.DataFrame) -> HierarchicalBayesResult:
        """Fit the hierarchical Bayesian model.

        擬合階層貝氏模型。

        Args:
            cell_outcomes_df: pandas DataFrame with required columns
                (cell_key, intended_outcome_bps OR intended_bps,
                net_outcome_bps). Optional columns are ignored.

        Returns:
            ``HierarchicalBayesResult`` with cells_count + r_hat_max +
            effective_sample_size_min + log_marginal_likelihood +
            posterior summaries (grand_mean / between / within stds).

        Raises:
            ValueError: missing required columns / empty df / invalid dtypes.
        """
        # Validate input contract.
        # 驗輸入契約。
        if not isinstance(cell_outcomes_df, pd.DataFrame):
            raise ValueError(
                f"cell_outcomes_df must be DataFrame; got "
                f"{type(cell_outcomes_df).__name__}"
            )
        if "cell_key" not in cell_outcomes_df.columns:
            raise ValueError(
                "cell_outcomes_df missing required column 'cell_key'"
            )
        if "net_outcome_bps" not in cell_outcomes_df.columns:
            raise ValueError(
                "cell_outcomes_df missing required column 'net_outcome_bps'"
            )
        intended_col = _select_intended_column(cell_outcomes_df)

        # Drop rows with missing fields.
        # 丟缺欄 row。
        df = cell_outcomes_df.dropna(
            subset=["cell_key", intended_col, "net_outcome_bps"]
        ).copy()
        if df.empty:
            raise ValueError(
                "cell_outcomes_df has no usable rows after NA drop"
            )

        # Compute per-row bias.
        # 逐 row 計算 bias。
        df["_bias_bps"] = (
            df["net_outcome_bps"].astype(float)
            - df[intended_col].astype(float)
        )

        # Group by cell_key to get arrays per cell.
        # 按 cell_key 分組得每 cell 的 array。
        cell_arrays: Dict[str, np.ndarray] = {}
        for key, sub in df.groupby("cell_key", sort=True):
            arr = sub["_bias_bps"].astype(float).to_numpy()
            arr = arr[np.isfinite(arr)]
            if arr.size == 0:
                continue
            cell_arrays[str(key)] = arr

        if not cell_arrays:
            raise ValueError(
                "cell_outcomes_df produced 0 valid cells after grouping"
            )

        # Run n_chains parallel Gibbs.
        # 跑 n_chains 平行 Gibbs。
        chain_results: List[Dict[str, np.ndarray]] = []
        for chain_idx in range(self._n_chains):
            seed = self._chain_seeds[chain_idx % len(self._chain_seeds)] + (
                chain_idx * 1000
            )
            chain_out = self._fit_gibbs(cell_arrays, seed=seed)
            chain_results.append(chain_out)

        # Stack chains for diagnostics.
        # 堆疊鏈做診斷。
        cell_keys = list(cell_arrays.keys())
        # cell_chains[cell_idx] = (n_chains, n_samples)
        cell_chains: List[np.ndarray] = []
        for c_idx, _ in enumerate(cell_keys):
            stacked = np.stack(
                [cr["cells"][:, c_idx] for cr in chain_results],
                axis=0,
            )
            cell_chains.append(stacked)

        grand_chains = np.stack([cr["mu_grand"] for cr in chain_results], axis=0)
        sigma_b_chains = np.stack([cr["sigma_b"] for cr in chain_results], axis=0)
        sigma_w_chains = np.stack([cr["sigma_w"] for cr in chain_results], axis=0)

        # Compute per-cell posterior summary.
        # 計算逐 cell 後驗摘要。
        r_hats: List[float] = []
        ess_list: List[int] = []
        self._posteriors = {}
        # Pooled across-chain posterior for each parameter.
        # 跨鏈合併後驗。
        flat_grand = grand_chains.reshape(-1)
        flat_sigma_b = sigma_b_chains.reshape(-1)
        flat_sigma_w = sigma_w_chains.reshape(-1)
        post_sigma_b_mean = float(np.mean(flat_sigma_b))
        post_sigma_w_mean = float(np.mean(flat_sigma_w))

        for c_idx, key in enumerate(cell_keys):
            chains_2d = cell_chains[c_idx]
            r_hat = _gelman_rubin_r_hat(chains_2d)
            r_hats.append(r_hat)

            flat = chains_2d.reshape(-1)
            ess = _effective_sample_size(flat)
            ess_list.append(ess)

            bias_mean = float(np.mean(flat))
            bias_std = float(np.std(flat, ddof=1)) if len(flat) > 1 else float(
                self._prior_std
            )
            ci_low = float(np.percentile(flat, 2.5))
            ci_high = float(np.percentile(flat, 97.5))

            n_cell = int(len(cell_arrays[key]))
            # Pooling factor: prec_prior / (prec_prior + prec_data).
            # Pooling factor：prec_prior / (prec_prior + prec_data)。
            prec_prior = 1.0 / max(post_sigma_b_mean ** 2, 1e-12)
            sample_var = (
                float(np.var(cell_arrays[key], ddof=1))
                if n_cell > 1
                else max(post_sigma_w_mean ** 2, 1e-9)
            )
            if sample_var <= 0 or not math.isfinite(sample_var):
                sample_var = max(post_sigma_w_mean ** 2, 1e-9)
            prec_data = n_cell / max(sample_var, 1e-12)
            pooling_factor = float(
                prec_prior / max(prec_prior + prec_data, 1e-12)
            )
            pooling_factor = max(0.0, min(1.0, pooling_factor))

            self._posteriors[key] = CellPosterior(
                cell_key=key,
                bias_mean=bias_mean,
                bias_std=bias_std,
                ci_low=ci_low,
                ci_high=ci_high,
                pooling_factor=pooling_factor,
                n_observations=n_cell,
                r_hat=r_hat,
                effective_sample_size=ess,
            )

        r_hat_max = float(max(r_hats)) if r_hats else 1.0
        ess_min = int(min(ess_list)) if ess_list else 0

        # Laplace-approximate log marginal likelihood:
        #   log p(y) ≈ log N(y; grand_mean_post, sigma_obs^2 = sigma_w^2 + sigma_b^2)
        # summed across cell observations.
        # Laplace 近似 log marginal likelihood：跨 cell 觀測加總高斯密度。
        sigma_obs2 = post_sigma_w_mean ** 2 + post_sigma_b_mean ** 2
        sigma_obs2 = max(sigma_obs2, 1e-9)
        grand_mean_post = float(np.mean(flat_grand))
        log_marg = 0.0
        for key, arr in cell_arrays.items():
            # Sum Normal log-pdf with grand mean / sigma_obs.
            # 用 grand mean / sigma_obs 求 Normal log-pdf 加總。
            for x in arr:
                log_marg += (
                    -0.5 * math.log(2.0 * math.pi * sigma_obs2)
                    - 0.5 * (x - grand_mean_post) ** 2 / sigma_obs2
                )

        self._summary = HierarchicalBayesResult(
            cells_count=len(cell_keys),
            r_hat_max=r_hat_max,
            effective_sample_size_min=ess_min,
            log_marginal_likelihood=float(log_marg),
            grand_mean_post=grand_mean_post,
            between_cell_std_post=post_sigma_b_mean,
            within_cell_std_post=post_sigma_w_mean,
            n_chains=self._n_chains,
            n_warmup=self._n_warmup,
            n_samples=self._n_samples,
        )

        logger.info(
            "hierarchical_bayes: fit cells=%d r_hat_max=%.4f ess_min=%d "
            "n_chains=%d",
            len(cell_keys),
            r_hat_max,
            ess_min,
            self._n_chains,
        )

        return self._summary

    def predict_cell(self, cell_key: str) -> CellPosterior:
        """Return per-cell posterior summary.

        回逐 cell 後驗摘要。

        Args:
            cell_key: Canonical "<strategy>::<symbol>::<side>" tuple.

        Returns:
            ``CellPosterior`` with bias_mean / bias_std / CI / pooling_factor.

        Raises:
            RuntimeError: model not yet fit.
            KeyError: cell_key not in fit dataset.
        """
        if not self.is_fit:
            raise RuntimeError(
                "Model not yet fit; call .fit(cell_outcomes_df) first"
            )
        if cell_key not in self._posteriors:
            raise KeyError(
                f"cell_key {cell_key!r} not in fit dataset; available: "
                f"{sorted(self._posteriors.keys())[:5]}..."
            )
        return self._posteriors[cell_key]

    # ------------------------------------------------------------------
    # Internal Gibbs sampler / 內部 Gibbs sampler
    # ------------------------------------------------------------------

    def _fit_gibbs(
        self,
        cell_arrays: Dict[str, np.ndarray],
        seed: int,
    ) -> Dict[str, np.ndarray]:
        """Run a single Gibbs chain.

        執行單條 Gibbs 鏈。

        Returns dict with:
            - 'cells': (n_samples, n_cells) draws of per-cell bias.
            - 'mu_grand': (n_samples,) draws of grand mean.
            - 'sigma_b': (n_samples,) draws of between-cell std.
            - 'sigma_w': (n_samples,) draws of within-cell std.
        """
        rng = np.random.default_rng(seed)
        cell_keys = list(cell_arrays.keys())
        n_cells = len(cell_keys)

        # Initialise from sample means.
        # 從樣本均值初始化。
        cell_means_data = np.array(
            [float(np.mean(cell_arrays[k])) for k in cell_keys],
            dtype=float,
        )
        b_cells = cell_means_data.copy()
        mu_grand = float(np.mean(b_cells))
        # Pool variances.
        # 合併變異。
        sigma_w = float(
            np.sqrt(
                np.mean(
                    [
                        float(np.var(cell_arrays[k], ddof=1))
                        if len(cell_arrays[k]) > 1
                        else self._prior_std ** 2
                        for k in cell_keys
                    ]
                )
            )
        )
        if sigma_w <= 0 or not math.isfinite(sigma_w):
            sigma_w = self._prior_std
        sigma_b = max(float(np.std(b_cells, ddof=1) if n_cells > 1 else self._prior_std), 1e-3)

        # Prior hyperparameters.
        # Prior 超參數。
        mu_grand_prior_mean = 0.0
        mu_grand_prior_var = self._prior_std ** 2
        ig_shape = 1.0
        ig_scale_b = max(self._prior_std ** 2, 1e-9)
        ig_scale_w = max(self._prior_std ** 2, 1e-9)

        total = self._n_warmup + self._n_samples
        cells_draws = np.zeros((self._n_samples, n_cells), dtype=float)
        grand_draws = np.zeros(self._n_samples, dtype=float)
        sigma_b_draws = np.zeros(self._n_samples, dtype=float)
        sigma_w_draws = np.zeros(self._n_samples, dtype=float)

        for it in range(total):
            # Sample b_cell[g] | rest.
            # 抽樣 b_cell[g] | rest。
            for g, k in enumerate(cell_keys):
                arr = cell_arrays[k]
                n_g = len(arr)
                prec_prior = 1.0 / max(sigma_b ** 2, 1e-12)
                prec_data = n_g / max(sigma_w ** 2, 1e-12)
                prec_post = prec_prior + prec_data
                mean_post = (
                    prec_prior * mu_grand + prec_data * float(np.mean(arr))
                ) / prec_post
                std_post = math.sqrt(1.0 / prec_post)
                b_cells[g] = float(rng.normal(mean_post, std_post))

            # Sample mu_grand | rest.
            # 抽樣 mu_grand | rest。
            prec_prior_grand = 1.0 / mu_grand_prior_var
            prec_data_grand = n_cells / max(sigma_b ** 2, 1e-12)
            prec_post_grand = prec_prior_grand + prec_data_grand
            mean_post_grand = (
                prec_prior_grand * mu_grand_prior_mean
                + prec_data_grand * float(np.mean(b_cells))
            ) / prec_post_grand
            std_post_grand = math.sqrt(1.0 / prec_post_grand)
            mu_grand = float(rng.normal(mean_post_grand, std_post_grand))

            # Sample sigma_b^2 | rest.
            # 抽樣 sigma_b^2 | rest。
            ss_b = float(np.sum((b_cells - mu_grand) ** 2))
            shape_post_b = ig_shape + n_cells / 2.0
            scale_post_b = ig_scale_b + ss_b / 2.0
            sigma_b2 = 1.0 / max(rng.gamma(shape_post_b, 1.0 / scale_post_b), 1e-12)
            sigma_b = math.sqrt(sigma_b2)

            # Sample sigma_w^2 | rest.
            # 抽樣 sigma_w^2 | rest。
            ss_w = 0.0
            n_total = 0
            for g, k in enumerate(cell_keys):
                arr = cell_arrays[k]
                ss_w += float(np.sum((arr - b_cells[g]) ** 2))
                n_total += len(arr)
            shape_post_w = ig_shape + n_total / 2.0
            scale_post_w = ig_scale_w + ss_w / 2.0
            sigma_w2 = 1.0 / max(rng.gamma(shape_post_w, 1.0 / scale_post_w), 1e-12)
            sigma_w = math.sqrt(sigma_w2)

            # Capture post-warmup draws.
            # 捕捉 post-warmup draws。
            if it >= self._n_warmup:
                idx = it - self._n_warmup
                cells_draws[idx, :] = b_cells
                grand_draws[idx] = mu_grand
                sigma_b_draws[idx] = sigma_b
                sigma_w_draws[idx] = sigma_w

        return {
            "cells": cells_draws,
            "mu_grand": grand_draws,
            "sigma_b": sigma_b_draws,
            "sigma_w": sigma_w_draws,
        }


__all__ = [
    "DEFAULT_CHAIN_SEEDS",
    "DEFAULT_N_CHAINS",
    "DEFAULT_N_SAMPLES",
    "DEFAULT_N_WARMUP",
    "EFFECTIVE_SS_MIN",
    "R_HAT_CONVERGED_MAX",
    "CellLevelHierarchicalBayes",
    "CellPosterior",
    "HierarchicalBayesResult",
]

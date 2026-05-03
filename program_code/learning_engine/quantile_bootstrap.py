"""
quantile_bootstrap — REF-20 Wave 5 P3a-Q3 Politis-Romano stationary bootstrap CI.
分位點 bootstrap 信賴區間 — REF-20 Wave 5 P3a-Q3。

MODULE_NOTE (EN): Implements Politis-Romano (1994) stationary bootstrap to
  estimate q10/q50/q90 confidence intervals for serially-correlated time series.
  Hand-rolled (no external `arch` dependency) — uses geometric block lengths
  with random starting points to preserve autocorrelation structure.
  Output feeds replay manifest's quantile estimates per V3 §8.2.
MODULE_NOTE (中): 實作 Politis-Romano (1994) 平穩 bootstrap，估計連續相關時間
  序列的 q10/q50/q90 信賴區間。手寫實作（無外部 `arch` 依賴）— 使用幾何分布
  block 長度 + 隨機起點，保留自相關結構。輸出餵 V3 §8.2 replay manifest 的
  分位點估計。

V3 §8.2 binding / V3 §8.2 綁定:
- "block bootstrap, Politis-Romano style, 1000 iterations"
- "preserve autocorrelation"
- "output 95% CI"
- "n<30 fallback parametric only if marked low_confidence and blocked from handoff"

Reference / 參考:
- Politis, D. N., & Romano, J. P. (1994). The stationary bootstrap.
  Journal of the American Statistical Association, 89(428), 1303-1313.
- Block size auto-determination: n^(1/3) heuristic per Politis-White (2004).
  Stationary bootstrap uses geometric distribution of block lengths with
  mean = block_size, ensuring stationarity in the bootstrap distribution.

Usage / 使用:
    from program_code.learning_engine.quantile_bootstrap import (
        QuantileBootstrap, BootstrapResult,
    )
    qb = QuantileBootstrap(n_iter=1000)
    result = qb.estimate_ci(returns, q=0.5, alpha=0.05)
    # result.point, result.ci_lower, result.ci_upper
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants / 常量
# ---------------------------------------------------------------------------

# Default iteration count per V3 §8.2.
# 預設迭代次數（依 V3 §8.2）。
DEFAULT_N_ITER: int = 1000

# Minimum sample size below which CI is unreliable.
# 樣本量低於此值則 CI 不可靠。
MIN_SAMPLE_SIZE: int = 30


# ---------------------------------------------------------------------------
# Result dataclass / 結果 dataclass
# ---------------------------------------------------------------------------


@dataclass
class BootstrapResult:
    """
    Bootstrap CI estimation outcome.
    Bootstrap CI 估計結果。

    Attributes / 屬性:
        point: point estimate (sample quantile from original series). /
               點估計（來自原始序列的樣本分位點）。
        ci_lower: alpha/2 percentile of bootstrap distribution. /
                  bootstrap 分布的 alpha/2 百分位點。
        ci_upper: 1-alpha/2 percentile of bootstrap distribution. /
                  bootstrap 分布的 1-alpha/2 百分位點。
        n_iter: number of bootstrap iterations performed. /
                執行的 bootstrap 迭代次數。
        block_size: mean block length used (auto if None passed in). /
                    使用的平均 block 長度（傳入 None 則自動）。
        sample_size: original series length. /
                     原始序列長度。
        low_confidence: True if sample_size < MIN_SAMPLE_SIZE. /
                        樣本量 < MIN_SAMPLE_SIZE 時為 True。
    """

    point: float
    ci_lower: float
    ci_upper: float
    n_iter: int
    block_size: int
    sample_size: int
    low_confidence: bool


# ---------------------------------------------------------------------------
# Helpers / 輔助函數
# ---------------------------------------------------------------------------


def _politis_white_block_size(n: int) -> int:
    """
    Heuristic block size: round(n^(1/3)) with min 2.
    啟發式 block 大小：round(n^(1/3))，最小 2。

    Note / 註: True Politis-White (2004) automatic selection requires fitting
    AR(p) on the series and computing optimal block from spectral density.
    The cube-root heuristic is the standard rule-of-thumb fallback when full
    spectral fit is not run; per V3 §8.2 spec it is acceptable for P3a.
    Use `round` (not `floor`) to handle Python float-power FP error
    (e.g., 1000**(1/3) = 9.99...; we want 10, not 9).
    使用 round（非 floor）處理 Python 浮點冪 FP 誤差
    （例：1000**(1/3) = 9.99...；應得 10 非 9）。
    註：完整 Politis-White (2004) 自動選擇需擬合 AR(p) 並由譜密度計算最優 block；
    立方根啟發式為標準經驗法則 fallback，依 V3 §8.2 規格在 P3a 為可接受。
    """
    # Add tiny epsilon before round to nudge perfect-cube FP errors upward.
    # 在 round 前加微小 epsilon，將完美立方 FP 誤差向上推。
    raw = n ** (1.0 / 3.0)
    rounded = int(math.floor(raw + 1e-9))
    upper_bound = max(2, n // 4)
    return max(2, min(rounded, upper_bound))


def _stationary_bootstrap_resample(
    series: np.ndarray,
    block_size: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generate one stationary bootstrap resample (Politis-Romano 1994).
    生成一次平穩 bootstrap 重抽樣（Politis-Romano 1994）。

    Algorithm / 演算法:
    - Pick random starting index i0 ~ Uniform{0, n-1}.
      隨機選起點 i0 ~ Uniform{0, n-1}。
    - For each subsequent step: with probability p=1/block_size,
      jump to a new random index; otherwise advance by 1 (wraps).
      每一步：以機率 p=1/block_size 跳新隨機起點，否則前進 1（環繞）。
    - Block lengths follow geometric distribution with mean block_size,
      preserving stationarity across the bootstrap distribution.
      Block 長度服從幾何分布、均值為 block_size，保證 bootstrap 分布平穩性。
    """
    n = len(series)
    p_jump = 1.0 / float(block_size)

    # Pre-generate jump decisions and random indices for vectorization.
    # 預先生成跳躍決策與隨機索引，便於向量化。
    jump_mask = rng.random(n) < p_jump
    random_indices = rng.integers(0, n, size=n)

    indices = np.empty(n, dtype=np.int64)
    indices[0] = random_indices[0]
    for t in range(1, n):
        if jump_mask[t]:
            indices[t] = random_indices[t]
        else:
            indices[t] = (indices[t - 1] + 1) % n

    return series[indices]


# ---------------------------------------------------------------------------
# Bootstrap class / Bootstrap 類別
# ---------------------------------------------------------------------------


class QuantileBootstrap:
    """
    Politis-Romano stationary bootstrap for quantile CI estimation.
    Politis-Romano 平穩 bootstrap，用於分位點 CI 估計。

    Block-based bootstrap preserves autocorrelation, suitable for
    serially-correlated returns / Sharpe / edge series. For IID data
    a simpler IID bootstrap would suffice; we use stationary bootstrap
    to be safe under unknown autocorrelation in fills/PnL data.
    Block-based bootstrap 保留自相關，適用於連續相關報酬 / Sharpe / edge
    序列。對 IID 資料簡單 IID bootstrap 即可；用平穩 bootstrap 在 fills/PnL
    自相關未知下更安全。
    """

    def __init__(
        self,
        n_iter: int = DEFAULT_N_ITER,
        block_size: Optional[int] = None,
        seed: Optional[int] = None,
    ) -> None:
        """
        Initialize bootstrap with configurable iteration count + block size.
        以可調迭代次數 + block 大小初始化 bootstrap。

        Args / 引數:
            n_iter: bootstrap iterations (default 1000 per V3 §8.2). /
                    bootstrap 迭代次數（V3 §8.2 預設 1000）。
            block_size: mean block length; None → auto via n^(1/3). /
                        平均 block 長度；None → 透過 n^(1/3) 自動。
            seed: optional RNG seed for reproducibility. /
                  選填 RNG seed 用於可重現性。
        """
        if n_iter < 100:
            raise ValueError(f"n_iter={n_iter} too small; minimum 100")
        self.n_iter = int(n_iter)
        self.block_size = block_size if block_size is None else int(block_size)
        self._seed = seed

    def estimate_ci(
        self,
        returns: np.ndarray,
        q: float = 0.5,
        alpha: float = 0.05,
    ) -> BootstrapResult:
        """
        Estimate quantile point + CI via stationary bootstrap.
        透過平穩 bootstrap 估計分位點點估計 + CI。

        Args / 引數:
            returns: 1D series of returns / Sharpe / edge values. /
                     報酬 / Sharpe / edge 的 1D 序列。
            q: quantile probability in (0, 1); e.g., 0.5 = median. /
               (0, 1) 內的分位點機率；例如 0.5 = 中位數。
            alpha: CI level; CI = [alpha/2 percentile, 1-alpha/2 percentile]. /
                   CI 等級；CI = [alpha/2 百分位, 1-alpha/2 百分位]。
                   Default 0.05 → 95% CI. / 預設 0.05 → 95% CI。

        Returns / 回傳:
            BootstrapResult with point estimate + lower/upper CI bounds. /
            含點估計 + 上下 CI 邊界的 BootstrapResult。

        Raises / 拋出:
            ValueError: invalid q / alpha / empty returns. /
                        無效 q / alpha / 空 returns。
        """
        if not 0.0 < q < 1.0:
            raise ValueError(f"q={q} must be in (0, 1)")
        if not 0.0 < alpha < 1.0:
            raise ValueError(f"alpha={alpha} must be in (0, 1)")

        arr = np.asarray(returns, dtype=np.float64).flatten()
        # Drop non-finite values explicitly. / 顯式丟棄非有限值。
        arr = arr[np.isfinite(arr)]

        if len(arr) == 0:
            raise ValueError("returns is empty after dropping non-finite values")

        n = len(arr)
        low_conf = n < MIN_SAMPLE_SIZE

        # Resolve block size / 解析 block 大小
        block_size = (
            self.block_size if self.block_size is not None
            else _politis_white_block_size(n)
        )
        # Sanity guard: block_size must not exceed n. / 健全性護欄：不可超過 n。
        block_size = max(1, min(block_size, n))

        rng = np.random.default_rng(self._seed)

        # Point estimate from original series. / 原始序列點估計。
        point = float(np.quantile(arr, q))

        # Bootstrap loop / Bootstrap 迴圈
        boot_quantiles = np.empty(self.n_iter, dtype=np.float64)
        for i in range(self.n_iter):
            sample = _stationary_bootstrap_resample(arr, block_size, rng)
            boot_quantiles[i] = float(np.quantile(sample, q))

        ci_lower = float(np.quantile(boot_quantiles, alpha / 2.0))
        ci_upper = float(np.quantile(boot_quantiles, 1.0 - alpha / 2.0))

        return BootstrapResult(
            point=point,
            ci_lower=ci_lower,
            ci_upper=ci_upper,
            n_iter=self.n_iter,
            block_size=block_size,
            sample_size=n,
            low_confidence=low_conf,
        )


# ---------------------------------------------------------------------------
# Module-level convenience / 模組級便利函數
# ---------------------------------------------------------------------------


def bootstrap_quantile_ci(
    returns: np.ndarray,
    q: float = 0.5,
    alpha: float = 0.05,
    n_iter: int = DEFAULT_N_ITER,
    seed: Optional[int] = None,
) -> BootstrapResult:
    """
    Module-level shortcut for QuantileBootstrap.estimate_ci.
    QuantileBootstrap.estimate_ci 的模組級捷徑。
    """
    return QuantileBootstrap(n_iter=n_iter, seed=seed).estimate_ci(
        returns, q=q, alpha=alpha,
    )


def naive_iid_quantile_ci(
    returns: np.ndarray,
    q: float = 0.5,
    alpha: float = 0.05,
    n_iter: int = DEFAULT_N_ITER,
    seed: Optional[int] = None,
) -> BootstrapResult:
    """
    Naive IID bootstrap baseline (for tightness comparison test only).
    Naive IID bootstrap 基線（僅供緊度比較測試用）。

    Note / 註: this is INCORRECT for autocorrelated data — included as a
    comparison baseline so test suite can verify stationary bootstrap
    yields tighter CI under known autocorrelation.
    註：此對自相關資料為 *錯誤* 方法 — 僅作為比較基線，使測試套件能驗證
    平穩 bootstrap 在已知自相關下產生更緊 CI。
    """
    arr = np.asarray(returns, dtype=np.float64).flatten()
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        raise ValueError("returns is empty")

    rng = np.random.default_rng(seed)
    n = len(arr)
    boot_quantiles = np.empty(n_iter, dtype=np.float64)
    for i in range(n_iter):
        idx = rng.integers(0, n, size=n)
        boot_quantiles[i] = float(np.quantile(arr[idx], q))

    point = float(np.quantile(arr, q))
    ci_lower = float(np.quantile(boot_quantiles, alpha / 2.0))
    ci_upper = float(np.quantile(boot_quantiles, 1.0 - alpha / 2.0))

    return BootstrapResult(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        n_iter=n_iter,
        block_size=1,  # IID bootstrap == block_size 1
        sample_size=n,
        low_confidence=n < MIN_SAMPLE_SIZE,
    )

"""
_regime_math — internal pure-math helpers for regime_controller (RGM-Q2/Q3/Q4).

_regime_math — regime_controller 內部純數學輔助（RGM-Q2/Q3/Q4）。

MODULE_NOTE (EN):
    Internal-use module hosting CUSUM, Kupiec POF, and PSR(0) math
    extracted from ``regime_controller.py`` to keep the controller
    surface within the 1200-LOC hard cap (CLAUDE.md §七 LOC budget).
    Underscore prefix signals "internal — do not import outside the
    learning_engine package". Public surface remains
    ``regime_controller.RegimeController``.

    All helpers are pure functions over numpy arrays; no DB / IPC /
    state. Cross-language float consistency (1e-4 tolerance) is
    Python-only here — Rust sibling will mirror via PyO3 if needed.

MODULE_NOTE (中):
    內部模組，承載從 regime_controller.py 抽出的 CUSUM / Kupiec POF /
    PSR(0) 數學，使 controller LOC 維持 1200 硬上限（CLAUDE.md §七）。
    底線前綴示意「內部用 — 不在 learning_engine 套件外 import」。
    公開 API 仍是 regime_controller.RegimeController。

    所有 helper 為 numpy 純函數；無 DB / IPC / 狀態。跨語言浮點一致
    （1e-4 容差）僅 Python 端；Rust sibling 後續 PyO3 鏡像。

SPEC binding:
- REF-20 V3 §8.4 #2 (CUSUM) — ``cusum_statistic``
- REF-20 V3 §8.4 #3 (Kupiec POF) — ``kupiec_lr_pof``
- REF-20 V3 §8.4 #4 (PSR(0)) — ``psr_zero``
"""

from __future__ import annotations

import math
from typing import Sequence, Tuple

import numpy as np

try:
    from scipy import stats as _scipy_stats  # type: ignore[import-untyped]
    _SCIPY_AVAILABLE = True
except ImportError:  # pragma: no cover
    _scipy_stats = None  # type: ignore[assignment]
    _SCIPY_AVAILABLE = False


def validate_returns(
    returns: Sequence[float],
    method_name: str,
    min_n: int,
) -> np.ndarray:
    """Convert + validate returns array.

    轉 + 驗 returns 陣列。

    Drops non-finite values; raises ValueError on empty input or
    ``n < min_n`` to enforce V3 §8.4 sample contracts.
    丟非有限值；空輸入或 n < min_n raise ValueError。
    """
    if returns is None:
        raise ValueError(f"{method_name}: returns must not be None")
    arr = np.asarray(list(returns), dtype=np.float64).flatten()
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        raise ValueError(
            f"{method_name}: returns is empty after dropping non-finite values"
        )
    if len(arr) < min_n:
        raise ValueError(
            f"{method_name}: insufficient sample (n={len(arr)} < min_n={min_n}); "
            f"V3 §8.4 spec violation"
        )
    return arr


def cusum_statistic(returns: np.ndarray) -> Tuple[float, float, float]:
    """Compute CUSUM ±σ statistic + (mean, std).

    計算 CUSUM ±σ 統計 + (mean, std)。

    Algorithm / 演算法:
        S_t = Σ_{i<=t} (x_i - μ) / σ
        return max_t |S_t / sqrt(n)|
    """
    n = len(returns)
    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1)) if n > 1 else 0.0
    if std <= 1e-12:
        # Constant series — no variability; CUSUM undefined; return 0.
        # 常數序列 — 無變異；CUSUM 未定義；回 0。
        return 0.0, mean, std
    standardised = (returns - mean) / std
    cum = np.cumsum(standardised)
    # Z-scale normalisation: divide by sqrt(n) so threshold is in σ units.
    # Z 尺度標準化：除 sqrt(n)，閾值單位為 σ。
    cum_z = cum / math.sqrt(float(n))
    max_abs = float(np.max(np.abs(cum_z)))
    return max_abs, mean, std


def kupiec_lr_pof(
    n: int,
    observed: int,
    expected_p: float,
) -> Tuple[float, float]:
    """Kupiec POF likelihood-ratio test (chi² 1df).

    Kupiec POF 概似比檢定（chi² 1df）。

    Returns ``(LR, p_value)``. LR = -2 * ln(L0/L1) where:
        L0 = p^x * (1-p)^(n-x)               under nominal p
        L1 = (x/n)^x * (1-x/n)^(n-x)          under MLE
    p_value = 1 - chi2.cdf(LR, df=1).

    回 (LR, p_value)。L0 = 名目；L1 = MLE。
    """
    if n <= 0:
        return float("nan"), float("nan")
    x = float(observed)
    p = float(expected_p)
    # x == 0 / x == n → MLE boundary; LR finite via log limits.
    # x == 0 / x == n → MLE 邊界；LR 透過 log 極限有限。
    if x == 0:
        ln_l0 = n * math.log(1.0 - p) if p < 1.0 else 0.0
        ln_l1 = 0.0
    elif x == n:
        ln_l0 = n * math.log(p) if p > 0.0 else 0.0
        ln_l1 = 0.0
    else:
        if p <= 0.0 or p >= 1.0:
            # Degenerate nominal — undefined LR.
            # 退化名目 — LR 未定義。
            return float("nan"), float("nan")
        ln_l0 = x * math.log(p) + (n - x) * math.log(1.0 - p)
        mle_p = x / float(n)
        ln_l1 = x * math.log(mle_p) + (n - x) * math.log(1.0 - mle_p)
    lr = -2.0 * (ln_l0 - ln_l1)
    if not math.isfinite(lr) or lr < 0.0:
        # Numerical floor.
        # 數值下界。
        lr = 0.0
    if _SCIPY_AVAILABLE:
        p_val = float(1.0 - _scipy_stats.chi2.cdf(lr, df=1))
    else:  # pragma: no cover
        # Fallback: chi² 1df survival = erfc(sqrt(LR/2)).
        # Fallback：chi² 1df 生存 = erfc(sqrt(LR/2))。
        p_val = float(math.erfc(math.sqrt(lr / 2.0))) if lr > 0 else 1.0
    p_val = max(0.0, min(1.0, p_val))
    return lr, p_val


def psr_zero(returns: np.ndarray) -> float:
    """PSR(0) — probability that true Sharpe > 0 given sample.

    PSR(0) — 樣本下真 Sharpe > 0 的機率。

    PSR(0) = Φ(SR_hat * sqrt(n - 1) /
               sqrt(1 - γ_3*SR_hat + (γ_4/4) * SR_hat²))

    where γ_3 = sample skewness, γ_4 = excess kurtosis.
    """
    n = len(returns)
    if n < 2:
        return float("nan")
    mean = float(np.mean(returns))
    std = float(np.std(returns, ddof=1))
    if std <= 1e-12:
        # Zero variance — degenerate; mean > 0 → cert PSR=1; mean < 0 → 0.
        # 零變異 — 退化；mean > 0 → cert PSR=1；mean < 0 → 0。
        if mean > 0:
            return 1.0
        if mean < 0:
            return 0.0
        return 0.5
    sr_hat = mean / std
    if not _SCIPY_AVAILABLE:  # pragma: no cover
        # Normal approximation only (γ_3=0, γ_4=0 excess).
        # 常態近似（γ_3=0, γ_4=0 excess）。
        z = sr_hat * math.sqrt(float(n - 1))
        return float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))
    skew = float(_scipy_stats.skew(returns, bias=False))
    kurt_excess = float(_scipy_stats.kurtosis(returns, bias=False))
    inner = 1.0 - skew * sr_hat + (kurt_excess / 4.0) * (sr_hat ** 2)
    if inner <= 0.0:
        # Singular adjustment — fall back to normal approx.
        # 奇異調整 — 退到常態近似。
        inner = 1.0
    z = sr_hat * math.sqrt(float(n - 1)) / math.sqrt(inner)
    psr = float(_scipy_stats.norm.cdf(z))
    return max(0.0, min(1.0, psr))


__all__ = [
    "cusum_statistic",
    "kupiec_lr_pof",
    "psr_zero",
    "validate_returns",
]

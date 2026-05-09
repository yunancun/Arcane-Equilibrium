"""Portfolio tail-risk primitives: historical VaR/CVaR and EVT/GPD.

This module is intentionally pure math: no DB writes, no IPC, no exchange IO.
Input returns are unit-agnostic. If callers pass fractional returns, losses are
fractions; if callers pass bps, losses are bps. Positive numbers in result
fields represent losses.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Optional, Sequence

import numpy as np

from .quantile_bootstrap import (
    DEFAULT_N_ITER,
    MIN_SAMPLE_SIZE,
    _politis_white_block_size,
    _stationary_bootstrap_resample,
)


DEFAULT_CONFIDENCE = 0.99
DEFAULT_EVT_THRESHOLD_QUANTILE = 0.95
DEFAULT_MIN_EVT_EXCESSES = 10


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _finite_array(values: Sequence[float] | np.ndarray, *, name: str) -> np.ndarray:
    arr = np.asarray(values, dtype=np.float64).flatten()
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        raise ValueError(f"{name} is empty after dropping non-finite values")
    return arr


def _validate_confidence(confidence: float) -> None:
    if not 0.5 < confidence < 1.0:
        raise ValueError(f"confidence={confidence} must be in (0.5, 1.0)")


def returns_to_losses(returns: Sequence[float] | np.ndarray) -> np.ndarray:
    """Convert profit returns into positive loss observations."""
    arr = _finite_array(returns, name="returns")
    return -arr


@dataclass(frozen=True)
class HistoricalVarCvarResult:
    confidence: float
    sample_size: int
    var_loss: float
    cvar_loss: float
    tail_count: int
    low_confidence: bool

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class EvtGpdResult:
    confidence: float
    threshold_quantile: float
    sample_size: int
    threshold_loss: float
    excess_count: int
    xi: float
    beta: float
    var_loss: float
    cvar_loss: float
    finite_cvar: bool
    low_confidence: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class TailRiskBootstrapResult:
    confidence: float
    sample_size: int
    n_iter: int
    block_size: int
    alpha: float
    var_point: float
    var_ci_lower: float
    var_ci_upper: float
    cvar_point: float
    cvar_ci_lower: float
    cvar_ci_upper: float
    low_confidence: bool

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


def _historical_from_losses(
    losses: np.ndarray,
    *,
    confidence: float,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> HistoricalVarCvarResult:
    _validate_confidence(confidence)
    losses = _finite_array(losses, name="losses")
    n = int(losses.size)
    var_loss = float(np.quantile(losses, confidence))
    tail = losses[losses >= var_loss - 1e-15]
    tail_count = int(tail.size)
    cvar_loss = float(np.mean(tail)) if tail_count > 0 else var_loss
    return HistoricalVarCvarResult(
        confidence=float(confidence),
        sample_size=n,
        var_loss=var_loss,
        cvar_loss=max(cvar_loss, var_loss),
        tail_count=tail_count,
        low_confidence=n < min_sample_size,
    )


def historical_var_cvar(
    returns: Sequence[float] | np.ndarray,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    min_sample_size: int = MIN_SAMPLE_SIZE,
) -> HistoricalVarCvarResult:
    """Compute historical VaR and CVaR/Expected Shortfall on profit returns."""
    losses = returns_to_losses(returns)
    return _historical_from_losses(
        losses, confidence=confidence, min_sample_size=min_sample_size,
    )


def evt_gpd_var_cvar(
    returns: Sequence[float] | np.ndarray,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    threshold_quantile: float = DEFAULT_EVT_THRESHOLD_QUANTILE,
    min_excesses: int = DEFAULT_MIN_EVT_EXCESSES,
) -> EvtGpdResult:
    """Fit a Peaks-over-Threshold GPD tail and estimate VaR/CVaR.

    Uses method-of-moments for a stable dependency-free GPD fit. This is less
    efficient than MLE but deterministic and robust enough for a promotion gate
    guardrail. Callers should treat ``low_confidence=True`` as fail-closed.
    """
    _validate_confidence(confidence)
    if not 0.5 < threshold_quantile < confidence:
        raise ValueError(
            "threshold_quantile must be in (0.5, confidence) for EVT tail fit"
        )
    if min_excesses < 3:
        raise ValueError("min_excesses must be >= 3")

    losses = returns_to_losses(returns)
    n = int(losses.size)
    threshold_loss = float(np.quantile(losses, threshold_quantile))
    excesses = losses[losses > threshold_loss] - threshold_loss
    excess_count = int(excesses.size)

    if excess_count < min_excesses:
        return EvtGpdResult(
            confidence=float(confidence),
            threshold_quantile=float(threshold_quantile),
            sample_size=n,
            threshold_loss=threshold_loss,
            excess_count=excess_count,
            xi=float("nan"),
            beta=float("nan"),
            var_loss=float("nan"),
            cvar_loss=float("nan"),
            finite_cvar=False,
            low_confidence=True,
            reason=f"insufficient_excesses:{excess_count}<{min_excesses}",
        )

    mean_excess = float(np.mean(excesses))
    var_excess = float(np.var(excesses, ddof=1)) if excess_count > 1 else 0.0
    if not math.isfinite(mean_excess) or mean_excess <= 0.0:
        return EvtGpdResult(
            confidence=float(confidence),
            threshold_quantile=float(threshold_quantile),
            sample_size=n,
            threshold_loss=threshold_loss,
            excess_count=excess_count,
            xi=float("nan"),
            beta=float("nan"),
            var_loss=float("nan"),
            cvar_loss=float("nan"),
            finite_cvar=False,
            low_confidence=True,
            reason="invalid_excess_mean",
        )

    if not math.isfinite(var_excess) or var_excess <= 1e-18:
        xi = 0.0
        beta = mean_excess
    else:
        xi = 0.5 * (1.0 - (mean_excess * mean_excess / var_excess))
        xi = max(-0.5, min(0.95, xi))
        beta = max(mean_excess * (1.0 - xi), 1e-12)

    p_tail = 1.0 - confidence
    p_threshold = excess_count / float(n)
    if p_tail <= 0.0 or p_threshold <= 0.0:
        var_loss = float("nan")
    elif abs(xi) < 1e-8:
        var_loss = threshold_loss + beta * math.log(p_threshold / p_tail)
    else:
        var_loss = threshold_loss + (beta / xi) * (
            (p_threshold / p_tail) ** xi - 1.0
        )

    finite_cvar = bool(math.isfinite(var_loss) and xi < 1.0)
    if finite_cvar:
        cvar_loss = var_loss + (beta + xi * (var_loss - threshold_loss)) / (1.0 - xi)
    else:
        cvar_loss = float("inf")

    return EvtGpdResult(
        confidence=float(confidence),
        threshold_quantile=float(threshold_quantile),
        sample_size=n,
        threshold_loss=threshold_loss,
        excess_count=excess_count,
        xi=float(xi),
        beta=float(beta),
        var_loss=float(var_loss),
        cvar_loss=float(cvar_loss),
        finite_cvar=bool(math.isfinite(cvar_loss)),
        low_confidence=False,
        reason="ok",
    )


def bootstrap_var_cvar_ci(
    returns: Sequence[float] | np.ndarray,
    *,
    confidence: float = DEFAULT_CONFIDENCE,
    alpha: float = 0.05,
    n_iter: int = DEFAULT_N_ITER,
    block_size: Optional[int] = None,
    seed: Optional[int] = None,
) -> TailRiskBootstrapResult:
    """Stationary block bootstrap CI for historical VaR and CVaR."""
    _validate_confidence(confidence)
    if not 0.0 < alpha < 1.0:
        raise ValueError(f"alpha={alpha} must be in (0, 1)")
    if n_iter < 100:
        raise ValueError(f"n_iter={n_iter} too small; minimum 100")

    losses = returns_to_losses(returns)
    n = int(losses.size)
    resolved_block = (
        int(block_size) if block_size is not None
        else _politis_white_block_size(n)
    )
    resolved_block = max(1, min(resolved_block, n))
    rng = np.random.default_rng(seed)

    point = _historical_from_losses(losses, confidence=confidence)
    boot_var = np.empty(n_iter, dtype=np.float64)
    boot_cvar = np.empty(n_iter, dtype=np.float64)
    for i in range(n_iter):
        sample = _stationary_bootstrap_resample(losses, resolved_block, rng)
        sampled = _historical_from_losses(sample, confidence=confidence)
        boot_var[i] = sampled.var_loss
        boot_cvar[i] = sampled.cvar_loss

    return TailRiskBootstrapResult(
        confidence=float(confidence),
        sample_size=n,
        n_iter=int(n_iter),
        block_size=int(resolved_block),
        alpha=float(alpha),
        var_point=point.var_loss,
        var_ci_lower=float(np.quantile(boot_var, alpha / 2.0)),
        var_ci_upper=float(np.quantile(boot_var, 1.0 - alpha / 2.0)),
        cvar_point=point.cvar_loss,
        cvar_ci_lower=float(np.quantile(boot_cvar, alpha / 2.0)),
        cvar_ci_upper=float(np.quantile(boot_cvar, 1.0 - alpha / 2.0)),
        low_confidence=n < MIN_SAMPLE_SIZE,
    )

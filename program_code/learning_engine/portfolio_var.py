"""Portfolio-level VaR/CVaR/EVT gate and stress scenarios.

The gate is source/test math for W-AUDIT-6c. It is intentionally pure and
side-effect free; production callers decide where to persist the returned
report. Positive loss values use the same unit as input returns.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Mapping, Optional, Sequence

import numpy as np

from .cvar import (
    DEFAULT_CONFIDENCE,
    HistoricalVarCvarResult,
    EvtGpdResult,
    TailRiskBootstrapResult,
    bootstrap_var_cvar_ci,
    evt_gpd_var_cvar,
    historical_var_cvar,
)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@dataclass(frozen=True)
class StressScenario:
    name: str
    shocks: Mapping[str, float]
    description: str

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class StressResult:
    scenario: str
    portfolio_return: float
    portfolio_loss: float
    shocks_applied: Mapping[str, float]

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class PortfolioTailRiskLimits:
    confidence: float = DEFAULT_CONFIDENCE
    max_var_loss: float = 0.05
    max_cvar_loss: float = 0.08
    max_evt_cvar_loss: float = 0.12
    max_stress_loss: float = 0.20
    min_observations: int = 200
    evt_threshold_quantile: float = 0.95
    min_evt_excesses: int = 10

    def to_dict(self) -> dict[str, Any]:
        return _json_safe(asdict(self))


@dataclass(frozen=True)
class PortfolioTailRiskReport:
    verdict: str
    passes: bool
    reasons: tuple[str, ...]
    limits: PortfolioTailRiskLimits
    historical: Optional[HistoricalVarCvarResult]
    evt: Optional[EvtGpdResult]
    bootstrap: Optional[TailRiskBootstrapResult]
    stress: tuple[StressResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "passes": self.passes,
            "reasons": list(self.reasons),
            "limits": self.limits.to_dict(),
            "historical": (
                self.historical.to_dict() if self.historical is not None else None
            ),
            "evt": self.evt.to_dict() if self.evt is not None else None,
            "bootstrap": (
                self.bootstrap.to_dict() if self.bootstrap is not None else None
            ),
            "stress": [item.to_dict() for item in self.stress],
        }


BUILTIN_STRESS_SCENARIOS: dict[str, StressScenario] = {
    "luna_2022_cascade": StressScenario(
        name="luna_2022_cascade",
        shocks={
            "crypto_beta": -0.70,
            "alt_beta": -0.85,
            "liquidity": -0.30,
            "stablecoin_depeg": -0.20,
        },
        description="2022 LUNA/UST-style crypto cascade",
    ),
    "ftx_2022_liquidity": StressScenario(
        name="ftx_2022_liquidity",
        shocks={
            "crypto_beta": -0.35,
            "alt_beta": -0.55,
            "exchange_token": -0.90,
            "liquidity": -0.40,
        },
        description="2022 FTX-style exchange/liquidity shock",
    ),
    "covid_2020_flash": StressScenario(
        name="covid_2020_flash",
        shocks={
            "crypto_beta": -0.50,
            "alt_beta": -0.60,
            "liquidity": -0.35,
        },
        description="2020 COVID-style broad liquidation shock",
    ),
}


def portfolio_returns_from_strategy_returns(
    strategy_returns: Mapping[str, Sequence[float]],
    *,
    weights: Optional[Mapping[str, float]] = None,
    normalize_weights: bool = True,
) -> np.ndarray:
    """Compose aligned strategy return series into one portfolio series."""
    if not strategy_returns:
        raise ValueError("strategy_returns must not be empty")

    keys = list(strategy_returns.keys())
    arrays = [np.asarray(strategy_returns[key], dtype=np.float64).flatten() for key in keys]
    lengths = {arr.size for arr in arrays}
    if len(lengths) != 1:
        raise ValueError("all strategy return series must have the same length")
    if next(iter(lengths)) == 0:
        raise ValueError("strategy return series must not be empty")

    matrix = np.column_stack(arrays)
    finite_rows = np.all(np.isfinite(matrix), axis=1)
    matrix = matrix[finite_rows]
    if matrix.shape[0] == 0:
        raise ValueError("portfolio returns empty after dropping non-finite rows")

    if weights is None:
        weight_vec = np.full(len(keys), 1.0 / float(len(keys)), dtype=np.float64)
    else:
        missing = [key for key in keys if key not in weights]
        if missing:
            raise ValueError(f"missing weights for strategies: {missing}")
        weight_vec = np.asarray([weights[key] for key in keys], dtype=np.float64)
        if not np.all(np.isfinite(weight_vec)):
            raise ValueError("weights must be finite")
        if normalize_weights:
            gross = float(np.sum(np.abs(weight_vec)))
            if gross <= 0.0:
                raise ValueError("gross weight exposure must be positive")
            weight_vec = weight_vec / gross

    return matrix @ weight_vec


def run_stress_scenarios(
    exposures: Mapping[str, float],
    *,
    scenarios: Optional[Mapping[str, StressScenario]] = None,
) -> tuple[StressResult, ...]:
    """Apply built-in or supplied factor-shock scenarios to factor exposures."""
    if not exposures:
        raise ValueError("stress exposures must not be empty")
    clean_exposures = {
        key: float(value)
        for key, value in exposures.items()
        if math.isfinite(float(value))
    }
    if not clean_exposures:
        raise ValueError("stress exposures are empty after dropping non-finite values")

    scenario_map = scenarios or BUILTIN_STRESS_SCENARIOS
    results: list[StressResult] = []
    for scenario in scenario_map.values():
        portfolio_return = 0.0
        shocks_applied: dict[str, float] = {}
        for factor, exposure in clean_exposures.items():
            shock = float(scenario.shocks.get(factor, 0.0))
            if shock != 0.0:
                shocks_applied[factor] = shock
            portfolio_return += exposure * shock
        results.append(
            StressResult(
                scenario=scenario.name,
                portfolio_return=float(portfolio_return),
                portfolio_loss=float(max(0.0, -portfolio_return)),
                shocks_applied=shocks_applied,
            )
        )
    return tuple(results)


class PortfolioTailRiskGate:
    """Fail-closed portfolio VaR/CVaR/EVT and stress-test gate."""

    def __init__(self, limits: Optional[PortfolioTailRiskLimits] = None) -> None:
        self._limits = limits or PortfolioTailRiskLimits()

    def evaluate(
        self,
        portfolio_returns: Sequence[float] | np.ndarray,
        *,
        stress_exposures: Optional[Mapping[str, float]] = None,
        n_bootstrap: int = 1000,
        seed: Optional[int] = None,
    ) -> PortfolioTailRiskReport:
        limits = self._limits
        arr = np.asarray(portfolio_returns, dtype=np.float64).flatten()
        arr = arr[np.isfinite(arr)]
        reasons: list[str] = []

        if arr.size < limits.min_observations:
            reasons.append(
                f"insufficient_observations:{arr.size}<{limits.min_observations}"
            )
            return PortfolioTailRiskReport(
                verdict="defer_data",
                passes=False,
                reasons=tuple(reasons),
                limits=limits,
                historical=None,
                evt=None,
                bootstrap=None,
                stress=tuple(),
            )

        historical = historical_var_cvar(arr, confidence=limits.confidence)
        evt = evt_gpd_var_cvar(
            arr,
            confidence=limits.confidence,
            threshold_quantile=limits.evt_threshold_quantile,
            min_excesses=limits.min_evt_excesses,
        )
        bootstrap = bootstrap_var_cvar_ci(
            arr,
            confidence=limits.confidence,
            n_iter=n_bootstrap,
            seed=seed,
        )

        if historical.var_loss > limits.max_var_loss:
            reasons.append(
                f"historical_var:{historical.var_loss:.6g}>{limits.max_var_loss:.6g}"
            )
        if historical.cvar_loss > limits.max_cvar_loss:
            reasons.append(
                f"historical_cvar:{historical.cvar_loss:.6g}>{limits.max_cvar_loss:.6g}"
            )

        if evt.low_confidence:
            reasons.append(f"evt:{evt.reason}")
        elif not evt.finite_cvar:
            reasons.append("evt:cvar_not_finite")
        elif evt.cvar_loss > limits.max_evt_cvar_loss:
            reasons.append(
                f"evt_cvar:{evt.cvar_loss:.6g}>{limits.max_evt_cvar_loss:.6g}"
            )

        stress_results: tuple[StressResult, ...] = tuple()
        if stress_exposures is None:
            reasons.append("stress_exposures_missing")
        else:
            stress_results = run_stress_scenarios(stress_exposures)
            for item in stress_results:
                if item.portfolio_loss > limits.max_stress_loss:
                    reasons.append(
                        f"stress:{item.scenario}:{item.portfolio_loss:.6g}>"
                        f"{limits.max_stress_loss:.6g}"
                    )

        if not reasons:
            verdict = "promote"
        elif all(
            reason.startswith("insufficient_observations")
            or reason.startswith("evt:insufficient_excesses")
            or reason == "stress_exposures_missing"
            for reason in reasons
        ):
            verdict = "defer_data"
        else:
            verdict = "block"

        return PortfolioTailRiskReport(
            verdict=verdict,
            passes=verdict == "promote",
            reasons=tuple(reasons),
            limits=limits,
            historical=historical,
            evt=evt,
            bootstrap=bootstrap,
            stress=stress_results,
        )

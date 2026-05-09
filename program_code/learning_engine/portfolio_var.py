"""Portfolio-level VaR/CVaR/EVT gate and stress scenarios.

The gate is source/test math for W-AUDIT-6c. It is intentionally pure and
side-effect free; production callers decide where to persist the returned
report. Positive loss values use the same unit as input returns.

W-AUDIT-6d #5 (2026-05-09 review)：
    `min_observations=200` 是 statistical baseline，不是 arbitrary：
    - 99% VaR 尾部需 ≥ 200 obs 才能穩定估計（n_tail = ⌊(1-0.99) × 200⌋ = 2）；
    - CVaR / Expected Shortfall 在 n=100 時 sampling variance 過大；
    - stationary block bootstrap CI 對 200+ obs 有效（_politis_white_block_size
      推薦 block_size = ⌈n^(1/3)⌉ ≈ 6 for n=200）。

    sampling unit = **per-trade fractional return**（不是日 / 小時 aggregated）：
    - `promotion_evidence.py::_return_series_from_bps()` 把 `raw_bps_series`
      除以 10_000 轉 fractional decimal，每元素是一筆 trade 的 PnL/notional；
    - 對 W-A demo 階段（22 個 fail-closed default 累積 ≈ 0 fill rate），
      可能長期返回 `verdict="defer_data"` — **這是預期 fail-closed 行為**，
      不該被誤判為 bug 並下調 min_observations。下調 → false-positive 提前
      promote 真壞策略。

    sampling unit ambiguity warning：caller 必確保 portfolio_returns 是
    **fractional return**（例如 0.005 表 0.5%）；若誤傳 percentage（0.5 表
    0.5%），max_var_loss=0.05 會永遠被超過，gate 永遠 block。
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
    """Portfolio tail-risk limits / W-AUDIT-6c gate 配置。

    sampling unit (W-AUDIT-6d #5 review)：所有 *_loss 欄位以 **fractional**
    形式傳入（0.05 表 5% loss），與 `portfolio_returns` 的 fractional return
    單位嚴格對齊。誤用 percentage（0.05 表 0.05% / 5 bps）會致 max_var_loss=0.05
    被永遠超過、gate 永遠 block。

    Limits are in *fractional* units (0.05 = 5% loss). MUST match the unit of
    `portfolio_returns` passed to `evaluate()`.

    Fields:
    - confidence: VaR 信心水平（默認 0.99 = 99%）。
    - max_var_loss: 99% 歷史 VaR 上限（fractional，0.05 = 5%）。
    - max_cvar_loss: 99% 歷史 CVaR / Expected Shortfall 上限（fractional）。
    - max_evt_cvar_loss: EVT/GPD tail CVaR 上限（fractional，比 historical CVaR
      寬，因 EVT 對極端事件更敏感）。
    - max_stress_loss: stress scenario portfolio_loss 上限（fractional）。
    - min_observations: 觸發完整 gate evaluation 所需最少 observation 數
      （W-AUDIT-6d #5 review：200 是 statistical baseline，VaR 尾部 +
      bootstrap CI + EVT excess 三方收斂的最小 sample size；下調為 false-pass
      提前 promote 風險，不接受）。
    - evt_threshold_quantile: EVT POT 閾值分位（默認 0.95 = 取 top 5%）。
    - min_evt_excesses: EVT GPD fit 所需最少 excess 數（默認 10；
      `min_observations × (1 - evt_threshold_quantile) = 200 × 0.05 = 10`，
      與 200 一致）。
    """

    confidence: float = DEFAULT_CONFIDENCE
    max_var_loss: float = 0.05
    max_cvar_loss: float = 0.08
    max_evt_cvar_loss: float = 0.12
    max_stress_loss: float = 0.20
    # W-AUDIT-6d #5 (2026-05-09 review)：見模塊頭 docstring 量化分析。
    # statistical baseline；下調風險見 promotion_evidence.py 文檔。
    # See module docstring for the quantitative justification.
    min_observations: int = 200
    evt_threshold_quantile: float = 0.95
    # W-AUDIT-6d #5: aligned with min_observations (200 × 5% = 10).
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

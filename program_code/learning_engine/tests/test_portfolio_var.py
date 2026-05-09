"""Tests for W-AUDIT-6c portfolio VaR/CVaR/EVT gate."""

from __future__ import annotations

import numpy as np
import pytest

from program_code.learning_engine.portfolio_var import (
    PortfolioTailRiskGate,
    PortfolioTailRiskLimits,
    portfolio_returns_from_strategy_returns,
    run_stress_scenarios,
)


def _mild_returns(seed: int = 42, n: int = 320) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(0.002, 0.006, size=n)


def test_portfolio_returns_from_weighted_strategy_series() -> None:
    returns = portfolio_returns_from_strategy_returns(
        {
            "grid_trading": [0.01, 0.02, 0.03],
            "ma_crossover": [-0.01, 0.00, 0.01],
        },
        weights={"grid_trading": 0.75, "ma_crossover": 0.25},
        normalize_weights=False,
    )

    assert returns.tolist() == pytest.approx([0.005, 0.015, 0.025])


def test_portfolio_returns_rejects_misaligned_series() -> None:
    with pytest.raises(ValueError, match="same length"):
        portfolio_returns_from_strategy_returns(
            {"grid_trading": [0.01, 0.02], "ma_crossover": [0.01]},
        )


def test_builtin_luna_ftx_stress_scenarios_use_positive_loss_convention() -> None:
    results = run_stress_scenarios({"crypto_beta": 1.0})
    by_name = {item.scenario: item for item in results}

    assert by_name["luna_2022_cascade"].portfolio_loss == pytest.approx(0.70)
    assert by_name["ftx_2022_liquidity"].portfolio_loss == pytest.approx(0.35)


def test_tail_risk_gate_promotes_mild_returns_with_bounded_stress_exposure() -> None:
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(
            confidence=0.99,
            max_var_loss=0.05,
            max_cvar_loss=0.08,
            max_evt_cvar_loss=0.12,
            max_stress_loss=0.20,
            min_observations=200,
            evt_threshold_quantile=0.95,
            min_evt_excesses=10,
        )
    )

    report = gate.evaluate(
        _mild_returns(),
        stress_exposures={"crypto_beta": 0.05, "liquidity": 0.02},
        n_bootstrap=120,
        seed=7,
    )

    assert report.passes
    assert report.verdict == "promote"
    assert report.historical is not None
    assert report.evt is not None
    assert report.bootstrap is not None
    assert report.to_dict()["passes"] is True


def test_tail_risk_gate_defers_without_stress_exposures() -> None:
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(min_observations=200, min_evt_excesses=10)
    )

    report = gate.evaluate(_mild_returns(), n_bootstrap=120, seed=8)

    assert not report.passes
    assert report.verdict == "defer_data"
    assert "stress_exposures_missing" in report.reasons


def test_tail_risk_gate_blocks_luna_ftx_stress_loss() -> None:
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(
            max_var_loss=0.05,
            max_cvar_loss=0.08,
            max_evt_cvar_loss=0.12,
            max_stress_loss=0.20,
            min_observations=200,
            min_evt_excesses=10,
        )
    )

    report = gate.evaluate(
        _mild_returns(),
        stress_exposures={"crypto_beta": 1.0},
        n_bootstrap=120,
        seed=9,
    )

    assert not report.passes
    assert report.verdict == "block"
    assert any(reason.startswith("stress:luna_2022_cascade") for reason in report.reasons)
    assert any(reason.startswith("stress:ftx_2022_liquidity") for reason in report.reasons)


def test_tail_risk_gate_blocks_historical_cvar_breach() -> None:
    returns = np.concatenate([_mild_returns(n=300), np.full(25, -0.20)])
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(
            max_var_loss=0.05,
            max_cvar_loss=0.08,
            max_evt_cvar_loss=0.30,
            max_stress_loss=0.50,
            min_observations=200,
            evt_threshold_quantile=0.90,
            min_evt_excesses=20,
        )
    )

    report = gate.evaluate(
        returns,
        stress_exposures={"crypto_beta": 0.05},
        n_bootstrap=120,
        seed=10,
    )

    assert not report.passes
    assert report.verdict == "block"
    assert any(reason.startswith("historical_cvar") for reason in report.reasons)


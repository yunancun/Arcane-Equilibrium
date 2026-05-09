"""Tests for W-AUDIT-6c VaR/CVaR/EVT math primitives."""

from __future__ import annotations

import numpy as np
import pytest

from program_code.learning_engine.cvar import (
    bootstrap_var_cvar_ci,
    evt_gpd_var_cvar,
    historical_var_cvar,
    returns_to_losses,
)


def test_historical_var_cvar_uses_positive_loss_convention() -> None:
    returns = np.asarray([0.03, 0.01, -0.01, -0.04, -0.07], dtype=np.float64)

    result = historical_var_cvar(returns, confidence=0.80, min_sample_size=3)

    assert result.sample_size == 5
    assert result.var_loss > 0.0
    assert result.cvar_loss >= result.var_loss
    assert result.tail_count >= 1
    assert not result.low_confidence


def test_returns_to_losses_drops_non_finite_values() -> None:
    losses = returns_to_losses([0.01, float("nan"), -0.02, float("inf")])

    assert losses.tolist() == pytest.approx([-0.01, 0.02])


def test_evt_gpd_estimates_tail_var_and_cvar() -> None:
    rng = np.random.default_rng(42)
    base = rng.normal(0.001, 0.006, size=500)
    tail = -0.03 - rng.pareto(2.5, size=50) * 0.02
    returns = np.concatenate([base, tail])

    result = evt_gpd_var_cvar(
        returns,
        confidence=0.99,
        threshold_quantile=0.90,
        min_excesses=20,
    )

    assert not result.low_confidence
    assert result.excess_count >= 20
    assert result.beta > 0.0
    assert result.var_loss > result.threshold_loss
    assert result.cvar_loss >= result.var_loss
    assert result.finite_cvar


def test_evt_gpd_low_confidence_when_tail_excesses_missing() -> None:
    rng = np.random.default_rng(7)
    returns = rng.normal(0.001, 0.004, size=80)

    result = evt_gpd_var_cvar(
        returns,
        confidence=0.99,
        threshold_quantile=0.95,
        min_excesses=10,
    )

    assert result.low_confidence
    assert result.reason.startswith("insufficient_excesses")


def test_bootstrap_var_cvar_ci_is_deterministic_with_seed() -> None:
    rng = np.random.default_rng(11)
    returns = rng.normal(0.001, 0.01, size=240)

    r1 = bootstrap_var_cvar_ci(
        returns,
        confidence=0.95,
        n_iter=120,
        seed=123,
    )
    r2 = bootstrap_var_cvar_ci(
        returns,
        confidence=0.95,
        n_iter=120,
        seed=123,
    )

    assert r1.var_point == pytest.approx(r2.var_point)
    assert r1.var_ci_lower == pytest.approx(r2.var_ci_lower)
    assert r1.var_ci_upper == pytest.approx(r2.var_ci_upper)
    assert r1.cvar_point == pytest.approx(r2.cvar_point)
    assert r1.cvar_ci_lower <= r1.cvar_point <= r1.cvar_ci_upper


def test_invalid_confidence_rejected() -> None:
    with pytest.raises(ValueError, match="confidence"):
        historical_var_cvar([0.01, -0.01], confidence=0.25)


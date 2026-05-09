"""Tests for composite strategy promotion gate."""

from __future__ import annotations

import numpy as np

from program_code.learning_engine.pbo_gate import PboGate
from program_code.learning_engine.promotion_gate import SelectionBiasPromotionGate


def _persistent_alpha_candidates(
    n_candidates: int = 6,
    n_periods: int = 64,
    seed: int = 42,
) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    return [
        float(k) * 0.05 + rng.normal(0.0, 0.05, size=n_periods)
        for k in range(n_candidates)
    ]


def _cheap_gate() -> SelectionBiasPromotionGate:
    return SelectionBiasPromotionGate(
        pbo_gate=PboGate(threshold=0.5, min_K=2, min_total_trades=20, s_slices=4)
    )


def test_composite_gate_promotes_with_high_dsr_and_low_pbo():
    result = _cheap_gate().evaluate(
        observed_sharpe=4.0,
        n_trials=6,
        n_observations=500,
        candidate_oos_returns=_persistent_alpha_candidates(),
    )

    assert result.passes
    assert result.verdict == "promote"
    assert result.dsr_verdict == "promote"
    assert result.pbo_verdict == "promote"
    assert result.cpcv_protocol == "cscv"


def test_composite_gate_defers_without_cv_returns():
    result = _cheap_gate().evaluate(
        observed_sharpe=4.0,
        n_trials=6,
        n_observations=500,
    )

    assert not result.passes
    assert result.verdict == "defer_data"
    assert result.pbo is None
    assert "pbo_missing_cpcv_returns" in result.reasons


def test_composite_gate_blocks_low_dsr():
    result = _cheap_gate().evaluate(
        observed_sharpe=0.1,
        n_trials=20,
        n_observations=200,
        candidate_oos_returns=_persistent_alpha_candidates(),
    )

    assert not result.passes
    assert result.verdict == "block"
    assert result.dsr_verdict == "block"
    assert "dsr_block" in result.reasons


def test_composite_gate_defers_insufficient_pbo_power_and_serializes_nan():
    result = SelectionBiasPromotionGate().evaluate(
        observed_sharpe=4.0,
        n_trials=10,
        n_observations=500,
        candidate_oos_returns=_persistent_alpha_candidates(
            n_candidates=10, n_periods=10,
        ),
    )

    report = result.to_dict()

    assert not result.passes
    assert result.verdict == "defer_data"
    assert result.pbo is not None
    assert result.pbo.insufficient_power
    assert "pbo_insufficient_power" in result.reasons
    assert report["pbo"]["pbo"] is None

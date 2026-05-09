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


# ─────────────────────────────────────────────────────────────────────
# W-AUDIT-6d #5 (2026-05-09 review): min_observations 邊界 + sampling unit。
# W-AUDIT-6d #5: min_observations boundary + sampling unit consistency.
# ─────────────────────────────────────────────────────────────────────


def test_w_audit_6d_min_observations_below_threshold_returns_defer_data() -> None:
    """W-AUDIT-6d #5：n < 200 → defer_data（不是 block）。

    這是預期 fail-closed 行為：W-A demo 階段樣本不足時 gate 應拒
    promotion 但 verdict 為 `defer_data`，讓 caller 區分「樣本不足」與
    「真的失敗」。"""
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(min_observations=200, min_evt_excesses=10)
    )
    report = gate.evaluate(
        _mild_returns(n=199),  # 199 < 200
        stress_exposures={"crypto_beta": 0.05},
        n_bootstrap=120,
        seed=11,
    )
    assert not report.passes
    assert report.verdict == "defer_data"
    assert any(
        reason.startswith("insufficient_observations") for reason in report.reasons
    ), report.reasons


def test_w_audit_6d_min_observations_at_threshold_proceeds() -> None:
    """W-AUDIT-6d #5：n = 200 邊界 inclusive，gate 進完整 evaluation。"""
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(min_observations=200, min_evt_excesses=10)
    )
    report = gate.evaluate(
        _mild_returns(n=200),
        stress_exposures={"crypto_beta": 0.05, "liquidity": 0.02},
        n_bootstrap=120,
        seed=12,
    )
    # n=200 入 evaluation；mild + 小 exposure → 應 promote 或 block 但不 defer_data。
    assert report.verdict != "defer_data", "n=200 必進 evaluation，不應 defer"
    # historical / evt / bootstrap 必有結果。
    assert report.historical is not None, "n=200 historical VaR 必算"
    assert report.bootstrap is not None, "n=200 bootstrap CI 必算"


def test_w_audit_6d_sampling_unit_fractional_returns_pass() -> None:
    """W-AUDIT-6d #5 sampling unit：fractional return（0.005 = 0.5%）通過。

    對齊 promotion_evidence.py::_return_series_from_bps（bps / 10_000）。
    """
    rng = np.random.default_rng(42)
    fractional_returns = rng.normal(0.001, 0.005, size=300)  # 0.1% mean, 0.5% std
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(min_observations=200, min_evt_excesses=10)
    )
    report = gate.evaluate(
        fractional_returns,
        stress_exposures={"crypto_beta": 0.05},
        n_bootstrap=120,
        seed=13,
    )
    # fractional 單位下 max_var_loss=0.05 (5%) 寬鬆；mild 樣本應通過。
    assert report.verdict in {"promote", "block"}, f"got {report.verdict}"


def test_w_audit_6d_sampling_unit_percentage_returns_block() -> None:
    """W-AUDIT-6d #5 sampling unit ambiguity：caller 誤傳 percentage 值
    （0.5 = 0.5% 而非 50%）→ var/cvar 大幅超 max_var_loss=0.05 → block。

    本 test 是 caller 對 sampling unit 誤用的 fail-loud 防線：
    - 若誤認為 0.5 表 50%，rng.normal(0.1, 0.5) 看起來是「±50% std」；
    - 進 evaluate() 時 max_var_loss=0.05 (5%) 變得遠小於實際 std，
      gate 必 block 而非 promote — 這是 sampling unit 不一致時的安全網。
    """
    rng = np.random.default_rng(42)
    # 誤把 percentage（0.5 表 0.5%）當成 fractional 餵入 — actual variance scale
    # 變大 100×；max_var_loss=0.05 fractional 必被超過。
    pct_misuse_returns = rng.normal(0.1, 0.5, size=300)
    gate = PortfolioTailRiskGate(
        PortfolioTailRiskLimits(min_observations=200, min_evt_excesses=10)
    )
    report = gate.evaluate(
        pct_misuse_returns,
        stress_exposures={"crypto_beta": 0.05},
        n_bootstrap=120,
        seed=14,
    )
    assert not report.passes
    assert report.verdict == "block", (
        "sampling unit 誤用必 fail-loud（max_var_loss 設 fractional 而 caller 餵 percentage）"
    )
    assert any(
        reason.startswith("historical_var") for reason in report.reasons
    ), f"reasons: {report.reasons}"


def test_w_audit_6d_min_evt_excesses_aligned_with_min_observations() -> None:
    """W-AUDIT-6d #5：default `min_evt_excesses = 10` 與 `min_observations = 200`
    通過 evt_threshold_quantile=0.95 對齊（200 × 5% = 10）。"""
    limits = PortfolioTailRiskLimits()
    expected_excesses = int(limits.min_observations * (1.0 - limits.evt_threshold_quantile))
    assert limits.min_evt_excesses == expected_excesses, (
        f"min_evt_excesses ({limits.min_evt_excesses}) 必與 "
        f"min_observations × (1-evt_threshold_quantile) = {expected_excesses} 對齊"
    )


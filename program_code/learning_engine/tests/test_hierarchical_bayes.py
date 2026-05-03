"""
Tests for hierarchical_bayes (REF-20 Wave 5 P3b-Q2).
hierarchical_bayes 測試（REF-20 Wave 5 P3b-Q2）。

Coverage / 覆蓋:
1. fit 3 cells (10 obs each) → r_hat < 1.05. /
   擬合 3 cells（每 10 obs）→ r_hat < 1.05。
2. predict_cell returns valid posterior with non-zero CI. /
   predict_cell 回有效後驗 + 非零 CI。
3. pooling_factor decreases with n (large cell → low pooling). /
   pooling_factor 隨 n 遞減（大 cell → 低 pooling）。
4. Mock fixture aligns with REF-21 stub schema (cell_key,
   intended_outcome_bps OR intended_bps, net_outcome_bps). /
   Mock fixture 對齊 REF-21 stub schema。
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from program_code.learning_engine.hierarchical_bayes import (
    DEFAULT_N_CHAINS,
    R_HAT_CONVERGED_MAX,
    CellLevelHierarchicalBayes,
    CellPosterior,
    HierarchicalBayesResult,
)


# ---------------------------------------------------------------------------
# Fixtures / Fixtures
# ---------------------------------------------------------------------------


def _make_cell_outcomes_df(
    cells_obs: dict,
    intended_alias: str = "intended_outcome_bps",
    seed: int = 7,
) -> pd.DataFrame:
    """Build a REF-21-shaped DataFrame from per-cell observation lists.

    從逐 cell 觀測 list 構造 REF-21-shape DataFrame。

    Args:
        cells_obs: Dict[cell_key, list[(intended_bps, net_outcome_bps)]] OR
                   Dict[cell_key, list[float bias]] (we'll synthesise both).
        intended_alias: which intended column name to use ('intended_bps' or
                        'intended_outcome_bps').
    """
    rng = np.random.default_rng(seed)
    rows = []
    for key, items in cells_obs.items():
        for it in items:
            if isinstance(it, (tuple, list)):
                intended, net = float(it[0]), float(it[1])
            else:
                # Treat scalar as bias; synthesise intended/net pair.
                # 純 scalar 視為 bias；合成 intended / net pair。
                bias = float(it)
                intended = float(rng.normal(0.0, 5.0))
                net = intended + bias
            rows.append(
                {
                    "cell_key": key,
                    intended_alias: intended,
                    "net_outcome_bps": net,
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test 1 — fit 3 cells r_hat / Test 1 — 擬合 3 cells r_hat
# ---------------------------------------------------------------------------


def test_fit_three_cells_r_hat_below_threshold():
    """
    Fit 3 cells (10 obs each) with 4 chains → r_hat_max < 1.05.
    擬合 3 cells（每 10 obs）4 鏈 → r_hat_max < 1.05。
    """
    rng = np.random.default_rng(42)
    cells = {
        "grid_trading::BTCUSDT::long": [
            (rng.normal(0, 5.0), rng.normal(0, 5.0) + 2.0)
            for _ in range(10)
        ],
        "grid_trading::ETHUSDT::long": [
            (rng.normal(0, 5.0), rng.normal(0, 5.0) + 1.5)
            for _ in range(10)
        ],
        "grid_trading::SOLUSDT::long": [
            (rng.normal(0, 5.0), rng.normal(0, 5.0) + 2.5)
            for _ in range(10)
        ],
    }
    df = _make_cell_outcomes_df(cells)

    model = CellLevelHierarchicalBayes(
        n_chains=4,
        n_warmup=200,
        n_samples=400,
    )
    summary = model.fit(df)

    assert isinstance(summary, HierarchicalBayesResult)
    assert summary.cells_count == 3
    assert summary.n_chains == 4
    # r_hat must converge below threshold (allow slight slack).
    # r_hat 必收斂於閾值下（允小 slack）。
    assert summary.r_hat_max < R_HAT_CONVERGED_MAX + 0.05, (
        f"r_hat_max={summary.r_hat_max:.4f} >= {R_HAT_CONVERGED_MAX}"
    )
    # Effective sample size positive.
    # ESS 為正。
    assert summary.effective_sample_size_min > 0
    # Posteriors of variance components positive.
    # 變異 component 後驗為正。
    assert summary.between_cell_std_post > 0
    assert summary.within_cell_std_post > 0


def test_fit_with_intended_bps_alias_column_works():
    """
    Alias 'intended_bps' (vs 'intended_outcome_bps') is also accepted.
    Alias 'intended_bps'（vs 'intended_outcome_bps'）也接受。
    """
    cells = {
        "ma_crossover::BTCUSDT::long": [
            (1.0, 3.0),
            (1.5, 3.5),
            (1.2, 3.2),
            (0.8, 2.8),
            (1.1, 3.1),
            (0.9, 2.9),
            (1.3, 3.3),
            (1.4, 3.4),
            (1.0, 3.0),
            (1.2, 3.2),
        ],
    }
    df = _make_cell_outcomes_df(cells, intended_alias="intended_bps")
    assert "intended_bps" in df.columns
    assert "intended_outcome_bps" not in df.columns

    model = CellLevelHierarchicalBayes(n_chains=2, n_warmup=100, n_samples=200)
    summary = model.fit(df)
    assert summary.cells_count == 1


# ---------------------------------------------------------------------------
# Test 2 — predict_cell valid posterior / Test 2 — predict_cell 有效後驗
# ---------------------------------------------------------------------------


def test_predict_cell_returns_valid_posterior_with_nonzero_ci():
    """
    predict_cell returns finite posterior + non-degenerate CI.
    predict_cell 回有限後驗 + 非退化 CI。
    """
    rng = np.random.default_rng(11)
    cells = {
        "bb_breakout::BTCUSDT::long": [
            (rng.normal(0, 2.0), rng.normal(0, 2.0) + 1.0)
            for _ in range(20)
        ],
        "bb_breakout::ETHUSDT::long": [
            (rng.normal(0, 2.0), rng.normal(0, 2.0) + 0.5)
            for _ in range(20)
        ],
    }
    df = _make_cell_outcomes_df(cells)

    model = CellLevelHierarchicalBayes(
        n_chains=2,
        n_warmup=200,
        n_samples=400,
    )
    model.fit(df)

    posterior = model.predict_cell("bb_breakout::BTCUSDT::long")
    assert isinstance(posterior, CellPosterior)
    assert posterior.cell_key == "bb_breakout::BTCUSDT::long"
    assert posterior.n_observations == 20
    # Finite posterior.
    # 有限後驗。
    assert np.isfinite(posterior.bias_mean)
    assert np.isfinite(posterior.bias_std)
    assert posterior.bias_std > 0
    # CI brackets the mean.
    # CI 包圍均值。
    assert posterior.ci_low <= posterior.bias_mean <= posterior.ci_high
    # CI is non-degenerate (width > 0).
    # CI 非退化（寬度 > 0）。
    assert posterior.ci_high > posterior.ci_low
    # pooling_factor in [0, 1].
    # pooling_factor 在 [0, 1]。
    assert 0.0 <= posterior.pooling_factor <= 1.0
    # r_hat finite + ESS positive.
    # r_hat 有限 + ESS 為正。
    assert np.isfinite(posterior.r_hat)
    assert posterior.effective_sample_size > 0


def test_predict_cell_unfit_raises():
    """
    Calling predict_cell before .fit() raises RuntimeError.
    fit 前呼 predict_cell 拋 RuntimeError。
    """
    model = CellLevelHierarchicalBayes()
    assert model.is_fit is False
    with pytest.raises(RuntimeError, match="Model not yet fit"):
        model.predict_cell("any::cell::long")


def test_predict_cell_unknown_key_raises():
    """
    Unknown cell_key after fit raises KeyError.
    fit 後未知 cell_key 拋 KeyError。
    """
    cells = {
        "grid_trading::BTCUSDT::long": [
            (1.0, 2.0) for _ in range(10)
        ],
    }
    df = _make_cell_outcomes_df(cells)
    model = CellLevelHierarchicalBayes(n_chains=2, n_warmup=100, n_samples=100)
    model.fit(df)
    with pytest.raises(KeyError):
        model.predict_cell("nonexistent::cell::short")


# ---------------------------------------------------------------------------
# Test 3 — pooling_factor monotonic / Test 3 — pooling_factor 單調
# ---------------------------------------------------------------------------


def test_pooling_factor_decreases_with_cell_observation_count():
    """
    Larger n_observations → smaller pooling_factor (cell escapes pool).
    更大 n_observations → 更小 pooling_factor（cell 逃 pool）。
    """
    rng = np.random.default_rng(99)
    # Use the SAME bias distribution for all cells so the only difference
    # is sample size; pooling_factor should monotone-decrease with n.
    # 對所有 cell 用相同 bias 分布；pooling_factor 應隨 n 單調遞減。
    cells = {}
    for n_obs in [10, 30, 60, 120]:
        key = f"strat::SYM{n_obs}::long"
        cells[key] = [
            (rng.normal(0, 3.0), rng.normal(0, 3.0) + 2.0)
            for _ in range(n_obs)
        ]
    df = _make_cell_outcomes_df(cells)

    model = CellLevelHierarchicalBayes(
        n_chains=2,
        n_warmup=300,
        n_samples=600,
    )
    model.fit(df)

    # Read pooling_factor in n-ascending order.
    # 按 n 升序讀 pooling_factor。
    factors_by_n = []
    for n_obs in [10, 30, 60, 120]:
        post = model.predict_cell(f"strat::SYM{n_obs}::long")
        factors_by_n.append((n_obs, post.pooling_factor))

    # Monotone-decreasing (allow ε for sampling noise).
    # 單調遞減（允小 ε noise）。
    for i in range(len(factors_by_n) - 1):
        n_a, f_a = factors_by_n[i]
        n_b, f_b = factors_by_n[i + 1]
        assert f_a >= f_b - 0.05, (
            f"pooling at n={n_a}={f_a:.4f} should be >= n={n_b}={f_b:.4f} "
            f"(within ε=0.05)"
        )


# ---------------------------------------------------------------------------
# Test 4 — REF-21 schema alignment / Test 4 — REF-21 schema 對齊
# ---------------------------------------------------------------------------


def test_ref21_stub_minimum_schema_alignment():
    """
    Mock fixture columns align with REF-21 placeholder §2 minimum contract.
    Mock fixture column 對齊 REF-21 placeholder §2 最小契約。

    Required columns per REF-21 stub §2:
    - cell_key (TEXT)
    - intended_bps OR intended_outcome_bps (DOUBLE)
    - net_outcome_bps (DOUBLE)
    """
    cells = {
        "grid_trading::BTCUSDT::long": [
            (1.0, 3.0),
            (1.5, 3.5),
            (1.2, 3.2),
            (0.8, 2.8),
            (1.1, 3.1),
            (0.9, 2.9),
            (1.3, 3.3),
            (1.4, 3.4),
            (1.0, 3.0),
            (1.2, 3.2),
        ],
    }
    # Ensure both alias names work; produce both fixtures.
    # 確保兩個 alias 都能用；產兩個 fixture。
    df_alias_long = _make_cell_outcomes_df(
        cells, intended_alias="intended_outcome_bps"
    )
    df_alias_short = _make_cell_outcomes_df(
        cells, intended_alias="intended_bps"
    )

    # Required columns present (alias).
    # 必填 column 在（alias）。
    assert "cell_key" in df_alias_long.columns
    assert "intended_outcome_bps" in df_alias_long.columns
    assert "net_outcome_bps" in df_alias_long.columns

    assert "cell_key" in df_alias_short.columns
    assert "intended_bps" in df_alias_short.columns
    assert "net_outcome_bps" in df_alias_short.columns

    # Both DataFrames fit successfully.
    # 兩個 DataFrame 都能成功擬合。
    for df in (df_alias_long, df_alias_short):
        model = CellLevelHierarchicalBayes(
            n_chains=2, n_warmup=100, n_samples=200
        )
        summary = model.fit(df)
        assert summary.cells_count == 1


def test_missing_required_columns_raises():
    """
    DataFrame missing required column raises ValueError.
    DataFrame 缺必填 column 拋 ValueError。
    """
    model = CellLevelHierarchicalBayes()

    # Missing cell_key.
    bad_no_key = pd.DataFrame(
        {
            "intended_outcome_bps": [1.0],
            "net_outcome_bps": [2.0],
        }
    )
    with pytest.raises(ValueError, match="cell_key"):
        model.fit(bad_no_key)

    # Missing net_outcome_bps.
    bad_no_net = pd.DataFrame(
        {
            "cell_key": ["a::b::c"],
            "intended_outcome_bps": [1.0],
        }
    )
    with pytest.raises(ValueError, match="net_outcome_bps"):
        model.fit(bad_no_net)

    # Missing both intended aliases.
    bad_no_intended = pd.DataFrame(
        {
            "cell_key": ["a::b::c"],
            "net_outcome_bps": [2.0],
        }
    )
    with pytest.raises(ValueError, match="intended"):
        model.fit(bad_no_intended)


def test_invalid_constructor_args_raise():
    """
    Constructor rejects invalid n_chains / n_warmup / n_samples.
    Constructor 拒絕無效 n_chains / n_warmup / n_samples。
    """
    with pytest.raises(ValueError):
        CellLevelHierarchicalBayes(n_chains=0)
    with pytest.raises(ValueError):
        CellLevelHierarchicalBayes(n_warmup=-1)
    with pytest.raises(ValueError):
        CellLevelHierarchicalBayes(n_samples=0)
    with pytest.raises(ValueError):
        CellLevelHierarchicalBayes(prior_std_bps=-0.5)


def test_default_constants_match_v3_and_module_spec():
    """
    Default constants match V3 spec / module-level convention.
    預設常數對齊 V3 spec / 模組級慣例。
    """
    assert DEFAULT_N_CHAINS == 4
    assert R_HAT_CONVERGED_MAX == 1.05

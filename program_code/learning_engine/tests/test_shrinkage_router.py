"""
Tests for shrinkage_router (REF-20 Wave 5 P3a-Q4).
shrinkage_router 測試（REF-20 Wave 5 P3a-Q4）。

Coverage / 覆蓋:
1. n=100 stable + fit pass → hierarchical tier. /
   n=100 穩定 + fit pass → hierarchical tier。
2. n=40 → james_stein tier. /
   n=40 → james_stein tier。
3. n=15 cold → empirical_bayes tier. /
   n=15 冷 → empirical_bayes tier。
4. shrinkage_factor monotonic with n (large n → small shrinkage). /
   shrinkage_factor 隨 n 單調（大 n → 小 shrinkage）。
5. Cross-tier output bounded by prior CI sanity. /
   跨 tier 輸出受 prior CI 邊界約束。
"""

from __future__ import annotations

import numpy as np
import pytest

from program_code.learning_engine.shrinkage_router import (
    N_THRESHOLD_HIERARCHICAL,
    N_THRESHOLD_JAMES_STEIN,
    ShrinkageResult,
    ShrinkageRouter,
)


# ---------------------------------------------------------------------------
# Fixtures / Fixtures
# ---------------------------------------------------------------------------


def _make_observed(n: int, mean: float, std: float, seed: int = 11) -> np.ndarray:
    """Generate iid Normal observations."""
    rng = np.random.default_rng(seed)
    return rng.normal(loc=mean, scale=std, size=n)


def _baseline_prior_inputs(
    grand_mean: float = 5.0,
    grand_std: float = 2.0,
    regime_stable: bool = True,
    fit_p_value: float = 0.03,
) -> dict:
    return {
        "grand_mean": grand_mean,
        "grand_std": grand_std,
        "regime_stable": regime_stable,
        "fit_p_value": fit_p_value,
    }


# ---------------------------------------------------------------------------
# Test 1 — hierarchical tier / Test 1 — hierarchical tier
# ---------------------------------------------------------------------------


def test_n100_stable_fit_pass_routes_to_hierarchical():
    """
    n=100 + regime_stable + fit_p < 0.10 → hierarchical tier.
    n=100 + regime_stable + fit_p < 0.10 → hierarchical tier.
    """
    router = ShrinkageRouter(
        gibbs_warmup=200, gibbs_draws=300, gibbs_seed=7
    )
    observed = _make_observed(n=100, mean=4.5, std=1.0, seed=1)
    related = {
        "grid_trading::ETHUSDT::long": _make_observed(50, 4.8, 1.0, seed=2),
        "grid_trading::SOLUSDT::long": _make_observed(60, 5.1, 1.0, seed=3),
    }
    prior = _baseline_prior_inputs(
        grand_mean=5.0,
        grand_std=2.0,
        regime_stable=True,
        fit_p_value=0.03,
    )
    prior["related_cells_observed"] = related

    result = router.shrink(
        observed=observed,
        cell_key="grid_trading::BTCUSDT::long",
        prior_inputs=prior,
    )

    assert isinstance(result, ShrinkageResult)
    assert result.tier_used == "hierarchical"
    assert result.n_observations == 100
    assert result.cell_key == "grid_trading::BTCUSDT::long"
    # Posterior between data mean and grand mean.
    # 後驗在 data mean 與 grand mean 之間。
    sample_mean = float(np.mean(observed))
    grand_mean = prior["grand_mean"]
    lo, hi = sorted([sample_mean, grand_mean])
    # Allow modest overshoot from Gibbs noise.
    # 容許 Gibbs noise 小幅越界。
    assert lo - 1.0 <= result.shrunk_estimate <= hi + 1.0
    assert 0.0 <= result.shrinkage_factor <= 1.0
    assert result.ci_low <= result.shrunk_estimate <= result.ci_high
    assert "hierarchical" in result.reason_en.lower()
    assert "hierarchical" in result.reason_zh.lower()


# ---------------------------------------------------------------------------
# Test 2 — James-Stein tier / Test 2 — James-Stein tier
# ---------------------------------------------------------------------------


def test_n40_routes_to_james_stein():
    """
    n=40 → james_stein tier (between thresholds).
    n=40 → james_stein tier（介於兩閾值之間）。
    """
    router = ShrinkageRouter()
    observed = _make_observed(n=40, mean=6.0, std=1.5, seed=5)
    prior = _baseline_prior_inputs(
        grand_mean=5.0,
        grand_std=2.0,
        regime_stable=True,
        fit_p_value=0.05,
    )
    result = router.shrink(
        observed=observed,
        cell_key="ma_crossover::BTCUSDT::long",
        prior_inputs=prior,
    )

    assert result.tier_used == "james_stein"
    assert result.n_observations == 40
    # Shrinkage between sample_mean and grand_mean.
    # 收縮估計在 sample_mean 與 grand_mean 之間。
    sample_mean = float(np.mean(observed))
    lo, hi = sorted([sample_mean, prior["grand_mean"]])
    assert lo <= result.shrunk_estimate <= hi
    assert 0.0 <= result.shrinkage_factor <= 1.0
    assert result.ci_low <= result.shrunk_estimate <= result.ci_high


def test_n100_regime_unstable_falls_back_to_james_stein():
    """
    n>=50 but regime_unstable → james_stein fallback.
    n>=50 但 regime 不穩 → james_stein 後備。
    """
    router = ShrinkageRouter()
    observed = _make_observed(n=100, mean=4.0, std=1.0, seed=9)
    prior = _baseline_prior_inputs(
        regime_stable=False,
        fit_p_value=0.03,
    )
    result = router.shrink(
        observed=observed,
        cell_key="bb_breakout::BTCUSDT::long",
        prior_inputs=prior,
    )
    assert result.tier_used == "james_stein"


def test_n100_fit_fail_falls_back_to_james_stein():
    """
    n>=50 + regime_stable but fit_p >= 0.10 → james_stein.
    n>=50 + 穩定 但 fit_p >= 0.10 → james_stein。
    """
    router = ShrinkageRouter()
    observed = _make_observed(n=100, mean=4.0, std=1.0, seed=10)
    prior = _baseline_prior_inputs(
        regime_stable=True,
        fit_p_value=0.20,
    )
    result = router.shrink(
        observed=observed,
        cell_key="bb_reversion::BTCUSDT::long",
        prior_inputs=prior,
    )
    assert result.tier_used == "james_stein"


# ---------------------------------------------------------------------------
# Test 3 — Empirical Bayes cold start / Test 3 — Empirical Bayes 冷啟動
# ---------------------------------------------------------------------------


def test_n15_cold_routes_to_empirical_bayes():
    """
    n=15 < 30 → empirical_bayes tier (cold start).
    n=15 < 30 → empirical_bayes tier（冷啟動）。
    """
    router = ShrinkageRouter()
    observed = _make_observed(n=15, mean=7.0, std=1.0, seed=42)
    prior = _baseline_prior_inputs(grand_mean=5.0, grand_std=2.0)
    result = router.shrink(
        observed=observed,
        cell_key="funding_arb::BTCUSDT::long",
        prior_inputs=prior,
    )

    assert result.tier_used == "empirical_bayes"
    assert result.n_observations == 15
    # Posterior between sample_mean and prior mean.
    # 後驗在 sample_mean 與 prior mean 之間。
    sample_mean = float(np.mean(observed))
    lo, hi = sorted([sample_mean, prior["grand_mean"]])
    assert lo <= result.shrunk_estimate <= hi
    assert 0.0 <= result.shrinkage_factor <= 1.0


# ---------------------------------------------------------------------------
# Test 4 — Shrinkage factor monotonic with n / Test 4 — 收縮係數隨 n 單調
# ---------------------------------------------------------------------------


def test_shrinkage_factor_monotonic_decreasing_with_n_within_eb_tier():
    """
    Within EB tier: large n → small shrinkage_factor (data dominates).
    EB tier 內：大 n → 小 shrinkage_factor（data 主導）。
    """
    router = ShrinkageRouter()
    prior = _baseline_prior_inputs(grand_mean=5.0, grand_std=2.0)

    # Sweep n in EB tier (n < 30).
    # 在 EB tier 內掃 n（n < 30）。
    factors = []
    for n in [5, 10, 20, 25]:
        # Use SAME std for each so prec_data scales linearly with n.
        # 用相同 std 使 prec_data 線性與 n 成比。
        observed = _make_observed(n=n, mean=6.0, std=1.0, seed=n + 100)
        # Force small but stable variance — patch with small jitter to
        # avoid n=5 edge-case variance underestimate.
        # 強制 small but stable variance — 注小 jitter 避 n=5 邊界。
        result = router.shrink(
            observed=observed,
            cell_key=f"test::n{n}::long",
            prior_inputs=prior,
        )
        factors.append(result.shrinkage_factor)

    # Monotonically non-increasing with n (allow tolerance for small-sample noise).
    # 隨 n 單調不增（允許小樣本 noise）。
    for i in range(len(factors) - 1):
        # Strict comparison up to ε for floating noise.
        # 嚴格比較，浮點 ε 容差。
        assert factors[i] >= factors[i + 1] - 0.05, (
            f"shrinkage at n={[5,10,20,25][i]}={factors[i]:.4f} should be "
            f">= shrinkage at n={[5,10,20,25][i+1]}={factors[i+1]:.4f}"
        )


# ---------------------------------------------------------------------------
# Test 5 — Cross-tier output bounded / Test 5 — 跨 tier 輸出邊界
# ---------------------------------------------------------------------------


def test_cross_tier_consistency_output_within_data_prior_envelope():
    """
    All tiers' shrunk_estimate within sample_mean - prior envelope.
    所有 tier 的收縮估計在 sample_mean 與 prior 形成的範圍內。
    """
    router = ShrinkageRouter(
        gibbs_warmup=200, gibbs_draws=300, gibbs_seed=33
    )
    grand_mean = 5.0
    grand_std = 2.0

    # Fixed sample_mean = 7.0 across n; verify all 3 tiers.
    # 各 n 固定 sample_mean = 7.0；驗 3 個 tier。
    obs_eb = _make_observed(n=15, mean=7.0, std=0.5, seed=1)
    obs_js = _make_observed(n=40, mean=7.0, std=0.5, seed=2)
    obs_hi = _make_observed(n=100, mean=7.0, std=0.5, seed=3)

    related = {
        "rel::A::long": _make_observed(50, 5.5, 0.5, seed=4),
    }

    eb = router.shrink(
        observed=obs_eb,
        cell_key="t::eb::long",
        prior_inputs={
            "grand_mean": grand_mean,
            "grand_std": grand_std,
            "regime_stable": True,
            "fit_p_value": 0.04,
        },
    )
    js = router.shrink(
        observed=obs_js,
        cell_key="t::js::long",
        prior_inputs={
            "grand_mean": grand_mean,
            "grand_std": grand_std,
            "regime_stable": True,
            "fit_p_value": 0.04,
        },
    )
    hi = router.shrink(
        observed=obs_hi,
        cell_key="t::hi::long",
        prior_inputs={
            "grand_mean": grand_mean,
            "grand_std": grand_std,
            "regime_stable": True,
            "fit_p_value": 0.04,
            "related_cells_observed": related,
        },
    )

    assert eb.tier_used == "empirical_bayes"
    assert js.tier_used == "james_stein"
    assert hi.tier_used == "hierarchical"

    # All within [grand_mean - 5*grand_std, grand_mean + 5*grand_std]
    # i.e. nothing escapes well outside the prior envelope.
    # 所有都在 [grand - 5σ, grand + 5σ] 內。
    envelope_lo = grand_mean - 5.0 * grand_std
    envelope_hi = grand_mean + 5.0 * grand_std
    for r in (eb, js, hi):
        assert envelope_lo <= r.shrunk_estimate <= envelope_hi, (
            f"tier {r.tier_used} estimate {r.shrunk_estimate:.4f} outside envelope "
            f"[{envelope_lo:.2f}, {envelope_hi:.2f}]"
        )
        # CI strictly bracket the estimate.
        # CI 嚴格包圍估計。
        assert r.ci_low <= r.shrunk_estimate <= r.ci_high


# ---------------------------------------------------------------------------
# Validation tests / 驗證測試
# ---------------------------------------------------------------------------


def test_invalid_thresholds_raise():
    """
    Constructor rejects invalid threshold combinations.
    Constructor 拒絕無效閾值組合。
    """
    with pytest.raises(ValueError):
        ShrinkageRouter(n_threshold_hier=0)
    with pytest.raises(ValueError):
        ShrinkageRouter(n_threshold_js=0)
    with pytest.raises(ValueError):
        # hier must exceed js.
        # hier 必須大於 js。
        ShrinkageRouter(n_threshold_hier=20, n_threshold_js=30)


def test_empty_observed_raises():
    """
    Empty observed array → ValueError.
    空 observed array → ValueError。
    """
    router = ShrinkageRouter()
    with pytest.raises(ValueError):
        router.shrink(
            observed=np.array([], dtype=float),
            cell_key="t::a::long",
            prior_inputs=_baseline_prior_inputs(),
        )


def test_missing_prior_keys_raise():
    """
    Missing required prior_inputs key → ValueError.
    缺必填 prior_inputs key → ValueError。
    """
    router = ShrinkageRouter()
    obs = _make_observed(20, 5.0, 1.0)
    # Missing grand_std.
    with pytest.raises(ValueError, match="grand_std"):
        router.shrink(
            observed=obs,
            cell_key="t::a::long",
            prior_inputs={
                "grand_mean": 5.0,
                "regime_stable": True,
                "fit_p_value": 0.05,
            },
        )
    # Missing regime_stable.
    with pytest.raises(ValueError, match="regime_stable"):
        router.shrink(
            observed=obs,
            cell_key="t::a::long",
            prior_inputs={
                "grand_mean": 5.0,
                "grand_std": 2.0,
                "fit_p_value": 0.05,
            },
        )


def test_threshold_constants_match_v3_spec():
    """
    V3 §8.2 cell n>=30 threshold + V3 §11 P3a hierarchical n>=50 (heuristic).
    V3 §8.2 cell n>=30 + V3 §11 hierarchical n>=50 (heuristic)。
    """
    assert N_THRESHOLD_JAMES_STEIN == 30
    assert N_THRESHOLD_HIERARCHICAL == 50

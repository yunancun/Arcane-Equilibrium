"""
P2-TEST-5: Unit tests for local_model_tools pure functions.

Tests cover pure data-transform functions (no FS, no network, no subprocess,
no DB). These functions operate solely on their inputs and return deterministic
outputs — ideal for fast, isolated unit tests.

Covered:
  - hurst_exponent: compute_hurst_exponent, _compute_rs_for_lag,
    _linear_regression_slope, classify_hurst
  - cognitive_modulator: _clamp
  - dream_engine: _confidence, _proposal_for_strategy, _payload_hash
  - evolution_engine: _count_raw_combinations, _klines_to_ohlcv
  - opportunity_tracker: _safe_direction

NOT covered (already tested in test_stub_contracts.py):
  - Signal.is_actionable / is_entry / is_exit / to_dict
  - create_default_signal_rules
  - BacktestTrade.to_dict / BacktestResult.to_dict
  - Constants (ANNUALIZATION_FACTORS, DIRECTION_*, etc.)
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

# Ensure local_model_tools is importable from the tests/ directory.
_PROGRAM_CODE = Path(__file__).resolve().parents[2] / "program_code"
if str(_PROGRAM_CODE) not in sys.path:
    sys.path.insert(0, str(_PROGRAM_CODE))


# ═══════════════════════════════════════════════════════════════════════════════
# hurst_exponent
# ═══════════════════════════════════════════════════════════════════════════════

from local_model_tools.hurst_exponent import (
    _compute_rs_for_lag,
    _linear_regression_slope,
    classify_hurst,
    compute_hurst_exponent,
)


class TestComputeHurstExponent:
    """Tests for the public compute_hurst_exponent function."""

    def test_insufficient_data_returns_neutral(self):
        """Too few prices → return 0.5 (neutral random walk)."""
        assert compute_hurst_exponent([100.0]) == 0.5
        assert compute_hurst_exponent([100.0, 101.0]) == 0.5
        # 11 prices → 10 returns, min_lag=10 → only 1 lag point → < 3 → 0.5
        short = [100.0 + i * 0.1 for i in range(11)]
        assert compute_hurst_exponent(short) == 0.5

    def test_random_walk_near_0_5(self):
        """Random walk price series should produce H near 0.5."""
        import random
        rng = random.Random(42)
        prices = [100.0]
        for _ in range(500):
            prices.append(prices[-1] * math.exp(rng.gauss(0, 0.01)))
        h = compute_hurst_exponent(prices)
        assert 0.35 < h < 0.65, f"Expected H ≈ 0.5 for random walk, got {h:.4f}"

    def test_trending_series_high_hurst(self):
        """Strong trending series should produce H > 0.60."""
        # Linear uptrend with tiny noise
        prices = [100.0 + i * 0.5 + (i % 3) * 0.01 for i in range(300)]
        h = compute_hurst_exponent(prices)
        assert h > 0.55, f"Expected H > 0.55 for trending, got {h:.4f}"

    def test_mean_reverting_series_low_hurst(self):
        """Mean-reverting series should produce H < 0.50."""
        import random
        rng = random.Random(123)
        base = 100.0
        prices = [base]
        for _ in range(300):
            # Strong mean reversion: pull back toward base with noise
            deviation = prices[-1] - base
            prices.append(prices[-1] - deviation * 0.3 + rng.gauss(0, 0.5))
        h = compute_hurst_exponent(prices)
        assert h < 0.55, f"Expected H < 0.55 for mean-reverting, got {h:.4f}"

    def test_constant_price_returns_neutral(self):
        """All identical prices → returns all 0 → H = 0.5."""
        prices = [100.0] * 200
        h = compute_hurst_exponent(prices)
        assert h == 0.5

    def test_zero_or_negative_prices_filtered(self):
        """Zero/negative prices are filtered out in return calculation."""
        # 101 valid prices (10 invalid ones filtered)
        valid = [100.0 + i * 0.1 for i in range(101)]
        prices = [0.0, -5.0] + valid  # 0 and negative filtered
        # Should still compute (101 valid prices → 100 returns)
        h = compute_hurst_exponent(prices)
        assert 0.0 <= h <= 1.0

    def test_custom_lag_params(self):
        """Custom min_lag / max_lag should be respected."""
        prices = [100.0 + i * 0.1 for i in range(200)]
        h_default = compute_hurst_exponent(prices)
        h_custom = compute_hurst_exponent(prices, min_lag=5, max_lag=50)
        assert 0.0 <= h_default <= 1.0
        assert 0.0 <= h_custom <= 1.0


class TestComputeRsForLag:
    """Tests for internal _compute_rs_for_lag helper."""

    def test_single_segment(self):
        """A single full-length segment returns one R/S value."""
        returns = [0.01, -0.005, 0.02, -0.01, 0.005]
        rs = _compute_rs_for_lag(returns, lag=5)
        assert len(rs) == 1
        assert rs[0] > 0

    def test_multiple_segments(self):
        """Two non-overlapping segments produce two R/S values."""
        import random
        rng = random.Random(42)
        returns = [rng.gauss(0.01, 0.005) for _ in range(10)] + [
            rng.gauss(-0.01, 0.005) for _ in range(10)
        ]
        rs = _compute_rs_for_lag(returns, lag=10)
        assert len(rs) == 2

    def test_insufficient_data_returns_empty(self):
        """Returns shorter than lag → empty list."""
        returns = [0.01, 0.02]
        rs = _compute_rs_for_lag(returns, lag=10)
        assert rs == []

    def test_zero_variance_segment_skipped(self):
        """Segment with zero variance (all returns equal) → no R/S added."""
        returns = [0.01, 0.01, 0.01, 0.01, 0.01]
        rs = _compute_rs_for_lag(returns, lag=5)
        # All returns equal → variance = 0 → s = 0 → skipped
        assert rs == []

    def test_r_s_monotonic_for_noisy_returns(self):
        """R/S should be >= 1 for any non-zero-variance segment."""
        import random
        rng = random.Random(99)
        returns = [rng.gauss(0, 0.01) for _ in range(100)]
        rs = _compute_rs_for_lag(returns, lag=20)
        assert len(rs) > 0
        for val in rs:
            assert val >= 1.0, f"R/S should be >= 1, got {val}"


class TestLinearRegressionSlope:
    """Tests for internal _linear_regression_slope helper."""

    def test_perfect_positive_slope(self):
        """Perfect y = 2x → slope = 2.0."""
        x = [1.0, 2.0, 3.0, 4.0, 5.0]
        y = [2.0, 4.0, 6.0, 8.0, 10.0]
        assert _linear_regression_slope(x, y) == pytest.approx(2.0)

    def test_perfect_negative_slope(self):
        """Perfect y = -x → slope = -1.0."""
        x = [1.0, 2.0, 3.0, 4.0]
        y = [-1.0, -2.0, -3.0, -4.0]
        assert _linear_regression_slope(x, y) == pytest.approx(-1.0)

    def test_single_point_returns_neutral(self):
        """Not enough data points → 0.5."""
        assert _linear_regression_slope([1.0], [1.0]) == 0.5

    def test_zero_denominator_returns_neutral(self):
        """All x values equal → denominator = 0 → 0.5."""
        x = [5.0, 5.0, 5.0]
        y = [1.0, 2.0, 3.0]
        assert _linear_regression_slope(x, y) == 0.5

    def test_flat_line_zero_slope(self):
        """All y values equal → slope = 0."""
        x = [1.0, 2.0, 3.0, 4.0]
        y = [5.0, 5.0, 5.0, 5.0]
        assert _linear_regression_slope(x, y) == pytest.approx(0.0)

    def test_noisy_line_reasonable_slope(self):
        """Noisy y = 0.5x should roughly recover slope ~0.5."""
        import random
        rng = random.Random(77)
        x = [float(i) for i in range(50)]
        y = [0.5 * xi + rng.gauss(0, 0.5) for xi in x]
        slope = _linear_regression_slope(x, y)
        assert 0.4 < slope < 0.6, f"Expected slope ≈ 0.5, got {slope:.4f}"


class TestClassifyHurst:
    """Tests for classify_hurst function."""

    def test_trending(self):
        assert classify_hurst(0.61) == "trending"
        assert classify_hurst(0.80) == "trending"
        assert classify_hurst(1.0) == "trending"

    def test_mean_reverting(self):
        assert classify_hurst(0.39) == "mean_reverting"
        assert classify_hurst(0.10) == "mean_reverting"
        assert classify_hurst(0.0) == "mean_reverting"

    def test_random_walk(self):
        assert classify_hurst(0.50) == "random_walk"
        assert classify_hurst(0.40) == "random_walk"
        assert classify_hurst(0.60) == "random_walk"

    def test_boundaries(self):
        """Test exact boundary values."""
        assert classify_hurst(0.4000001) == "random_walk"
        assert classify_hurst(0.3999999) == "mean_reverting"
        assert classify_hurst(0.6000001) == "trending"
        assert classify_hurst(0.5999999) == "random_walk"


# ═══════════════════════════════════════════════════════════════════════════════
# cognitive_modulator: _clamp
# ═══════════════════════════════════════════════════════════════════════════════

from local_model_tools.cognitive_modulator import _clamp


class TestClamp:
    """Tests for _clamp utility."""

    def test_within_range(self):
        assert _clamp(5.0, 0.0, 10.0) == 5.0

    def test_below_lower(self):
        assert _clamp(-1.0, 0.0, 10.0) == 0.0

    def test_above_upper(self):
        assert _clamp(15.0, 0.0, 10.0) == 10.0

    def test_at_boundaries(self):
        assert _clamp(0.0, 0.0, 10.0) == 0.0
        assert _clamp(10.0, 0.0, 10.0) == 10.0

    def test_negative_range(self):
        assert _clamp(-5.0, -10.0, -2.0) == -5.0
        assert _clamp(-20.0, -10.0, -2.0) == -10.0
        assert _clamp(0.0, -10.0, -2.0) == -2.0

    def test_single_point_range(self):
        """lo == hi → always returns that value."""
        assert _clamp(0.0, 5.0, 5.0) == 5.0
        assert _clamp(100.0, 5.0, 5.0) == 5.0


# ═══════════════════════════════════════════════════════════════════════════════
# dream_engine: _confidence, _proposal_for_strategy, _payload_hash
# ═══════════════════════════════════════════════════════════════════════════════

from local_model_tools.dream_engine import (
    DreamConfig,
    _confidence,
    _payload_hash,
    _proposal_for_strategy,
)


class TestConfidence:
    """Tests for _confidence(n, cfg)."""

    def test_zero_samples_minimum_confidence(self):
        """Zero samples → clamped to minimum 0.05."""
        cfg = DreamConfig(min_samples=5)
        assert _confidence(0, cfg) == 0.05

    def test_max_capped(self):
        """Large n → capped at 0.85."""
        cfg = DreamConfig(min_samples=5)
        assert _confidence(10000, cfg) == 0.85

    def test_intermediate_values(self):
        """Confidence scales linearly with n / (min_samples * 8)."""
        cfg = DreamConfig(min_samples=5)
        # denominator = 5 * 8 = 40
        assert _confidence(20, cfg) == 0.5   # 20/40 = 0.5
        assert _confidence(10, cfg) == 0.25  # 10/40 = 0.25

    def test_custom_min_samples(self):
        """Larger min_samples → slower confidence growth."""
        cfg = DreamConfig(min_samples=50)
        # denominator = 50 * 8 = 400
        assert _confidence(20, cfg) == 0.05  # 20/400 = 0.05 → clamped to min
        assert _confidence(200, cfg) == 0.5  # 200/400 = 0.5

    def test_returns_float_rounded_to_4_decimal(self):
        """Result is a float rounded to 4 decimal places."""
        cfg = DreamConfig(min_samples=7)
        result = _confidence(15, cfg)
        assert isinstance(result, float)
        # 15 / (7 * 8) = 15/56 ≈ 0.267857... → round to 0.2679
        assert result == pytest.approx(0.2679, abs=0.00005)


class TestProposalForStrategy:
    """Tests for _proposal_for_strategy lookup table."""

    def test_grid_trading(self):
        result = _proposal_for_strategy("grid_trading", -5.0)
        assert result["param_name"] == "grid_spacing_bps"
        assert result["direction"] == "widen"

    def test_ma_crossover(self):
        result = _proposal_for_strategy("ma_crossover", 10.0)
        assert result["param_name"] == "min_hold_seconds"
        assert result["direction"] == "lengthen"

    def test_bb_breakout_positive_edge(self):
        """Positive avg_bps → suggested_change_pct = 0.0."""
        result = _proposal_for_strategy("bb_breakout", 5.0)
        assert result["param_name"] == "volume_threshold"
        assert result["suggested_change_pct"] == 0.0

    def test_bb_breakout_negative_edge(self):
        """Negative avg_bps → suggested_change_pct = 0.20."""
        result = _proposal_for_strategy("bb_breakout", -3.0)
        assert result["param_name"] == "volume_threshold"
        assert result["suggested_change_pct"] == 0.20

    def test_bb_reversion(self):
        result = _proposal_for_strategy("bb_reversion", -1.0)
        assert result["direction"] == "tighten_exit_quality"

    def test_funding_arb(self):
        result = _proposal_for_strategy("funding_arb", 0.0)
        assert result["param_name"] == "min_funding_edge_bps"
        assert result["direction"] == "raise"

    def test_unknown_strategy_default(self):
        """Unknown strategy name → default fallback proposal."""
        result = _proposal_for_strategy("unknown_strategy", 1.0)
        assert result["param_name"] == "confidence_threshold"
        assert result["direction"] == "raise"
        assert result["suggested_change_pct"] == 0.05


class TestPayloadHash:
    """Tests for _payload_hash pure hash function."""

    def test_deterministic(self):
        """Same inputs → same hash."""
        h1 = _payload_hash("strat_1", "BTCUSDT", "cell_A", 42)
        h2 = _payload_hash("strat_1", "BTCUSDT", "cell_A", 42)
        assert h1 == h2

    def test_different_inputs_different_hash(self):
        """Different inputs → different hashes."""
        h1 = _payload_hash("strat_1", "BTCUSDT", "cell_A", 42)
        h2 = _payload_hash("strat_1", "BTCUSDT", "cell_B", 42)
        assert h1 != h2

    def test_different_seed_different_hash(self):
        h1 = _payload_hash("s", "BTCUSDT", "c", 1)
        h2 = _payload_hash("s", "BTCUSDT", "c", 2)
        assert h1 != h2

    def test_hex_format(self):
        """Output is a 64-character hex string (SHA-256)."""
        h = _payload_hash("s", "sym", "cell", 0)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_reproducibility(self):
        """The hash should be reproducible across calls (exact byte match)."""
        expected = _payload_hash("test", "BTCUSDT", "1h", 0)
        for _ in range(10):
            assert _payload_hash("test", "BTCUSDT", "1h", 0) == expected


# ═══════════════════════════════════════════════════════════════════════════════
# evolution_engine: _count_raw_combinations, _klines_to_ohlcv
# ═══════════════════════════════════════════════════════════════════════════════

from local_model_tools.evolution_engine import (
    ParameterGrid,
    _count_raw_combinations,
    _klines_to_ohlcv,
)


class TestCountRawCombinations:
    """Tests for _count_raw_combinations."""

    def test_empty_grids(self):
        """Empty list → 1."""
        assert _count_raw_combinations([]) == 1

    def test_single_grid(self):
        """One grid with N values → N."""
        g = ParameterGrid(name="p", values=[1, 2, 3])
        assert _count_raw_combinations([g]) == 3

    def test_multiple_grids_cartesian_product(self):
        """Two grids → product of their value counts."""
        g1 = ParameterGrid(name="a", values=[1, 2])
        g2 = ParameterGrid(name="b", values=[10, 20, 30])
        assert _count_raw_combinations([g1, g2]) == 6

    def test_three_grids(self):
        g1 = ParameterGrid(name="a", values=[1, 2])
        g2 = ParameterGrid(name="b", values=[1, 2, 3])
        g3 = ParameterGrid(name="c", values=[1, 2, 3, 4])
        assert _count_raw_combinations([g1, g2, g3]) == 24

    def test_grid_with_empty_values(self):
        """Grid with empty values → 0 total."""
        g = ParameterGrid(name="p", values=[])
        assert _count_raw_combinations([g]) == 0


class TestKlinesToOhlcv:
    """Tests for _klines_to_ohlcv data transform."""

    def test_empty_klines(self):
        """Empty input → None."""
        assert _klines_to_ohlcv([]) is None

    def test_single_kline(self):
        """Single kline → one-element arrays in each field."""
        klines = [{
            "open": 100.0, "high": 105.0, "low": 99.0,
            "close": 103.0, "volume": 1000.0,
        }]
        result = _klines_to_ohlcv(klines)
        assert result is not None
        assert result["open"] == [100.0]
        assert result["high"] == [105.0]
        assert result["low"] == [99.0]
        assert result["close"] == [103.0]
        assert result["volume"] == [1000.0]

    def test_multiple_klines(self):
        """Multiple klines → arrays in order."""
        klines = [
            {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 500.0},
            {"open": 100.5, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 600.0},
            {"open": 101.5, "high": 103.0, "low": 101.0, "close": 102.0, "volume": 700.0},
        ]
        result = _klines_to_ohlcv(klines)
        assert result is not None
        assert result["open"] == [100.0, 100.5, 101.5]
        assert result["high"] == [101.0, 102.0, 103.0]
        assert result["low"] == [99.0, 100.0, 101.0]
        assert result["close"] == [100.5, 101.5, 102.0]
        assert result["volume"] == [500.0, 600.0, 700.0]

    def test_result_keys(self):
        """Result has exactly the 5 expected keys."""
        klines = [{"open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5, "volume": 100.0}]
        result = _klines_to_ohlcv(klines)
        assert result is not None
        assert set(result.keys()) == {"open", "high", "low", "close", "volume"}

    def test_extra_fields_ignored(self):
        """Extra kline fields are ignored."""
        klines = [{
            "open": 1.0, "high": 2.0, "low": 0.5, "close": 1.5,
            "volume": 100.0, "turnover": 999.0, "extra": "ignored",
        }]
        result = _klines_to_ohlcv(klines)
        assert result is not None
        assert "turnover" not in result
        assert len(result["open"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# opportunity_tracker: _safe_direction
# ═══════════════════════════════════════════════════════════════════════════════

from local_model_tools.opportunity_tracker import _safe_direction


class TestSafeDirection:
    """Tests for _safe_direction."""

    def test_buy_returns_1(self):
        assert _safe_direction("buy") == 1
        assert _safe_direction("Buy") == 1
        assert _safe_direction("BUY") == 1

    def test_sell_returns_minus_1(self):
        assert _safe_direction("sell") == -1
        assert _safe_direction("Sell") == -1

    def test_none_returns_default_1(self):
        """None defaults to buy direction (1)."""
        assert _safe_direction(None) == 1

    def test_unknown_returns_default_1(self):
        """Unknown strings default to buy direction (1)."""
        assert _safe_direction("") == 1
        assert _safe_direction("long") == 1
        assert _safe_direction("unknown") == 1

    def test_short_returns_minus_1(self):
        """'short' direction returns -1."""
        assert _safe_direction("short") == -1
        assert _safe_direction("Short") == -1
        assert _safe_direction("SHORT") == -1

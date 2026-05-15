"""
P2-TEST-4: Unit tests for ml_training pure utility functions.

Covers pure data-transform functions (no FS, no network, no subprocess, no DB)
that lacked direct unit tests in the existing ml_training/tests/ suite.

Functions tested:
  james_stein_estimator:
    _js_shrinkage — James-Stein positive-part shrinkage core math
  edge_cluster_analysis:
    _euclidean — Euclidean distance
    _normalize_features — Min-max feature normalization
    _kmeans — Simple Lloyd's k-means clustering
    _label_clusters — Cluster naming (candidate/middle/underperformer)
  edge_estimate_validation:
    _normal_cdf — Standard normal CDF via erf
    _finite_values — Filter out NaN/inf
    _sample_mean_std — Sample mean and standard deviation
"""

from __future__ import annotations

import math

import pytest

# ── James-Stein shrinkage ──────────────────────────────────────────
from program_code.ml_training.james_stein_estimator import _js_shrinkage

# ── Edge cluster analysis ──────────────────────────────────────────
from program_code.ml_training.edge_cluster_analysis import (
    CellFeatures,
    _euclidean,
    _kmeans,
    _label_clusters,
    _normalize_features,
)

# ── Edge estimate validation helpers ───────────────────────────────
from program_code.ml_training.edge_estimate_validation import (
    _finite_values,
    _normal_cdf,
    _sample_mean_std,
)


# ═══════════════════════════════════════════════════════════════════
# _js_shrinkage — James-Stein core math
# ═══════════════════════════════════════════════════════════════════

def test_js_shrinkage_p_less_than_3_returns_raw():
    """p < 3 → JS undefined, returns raw values unchanged."""
    raw = [1.0, 2.0]
    vars_ = [0.5, 0.5]
    grand_mean = 1.5
    result = _js_shrinkage(raw, vars_, grand_mean)
    assert result == pytest.approx(raw)


def test_js_shrinkage_identical_values_no_op():
    """All raw values identical → sq_sum ≈ 0 → return raw unchanged."""
    raw = [3.0, 3.0, 3.0, 3.0]
    vars_ = [0.5, 0.5, 0.5, 0.5]
    grand_mean = 3.0
    result = _js_shrinkage(raw, vars_, grand_mean)
    assert result == pytest.approx(raw)


def test_js_shrinkage_pulls_toward_grand_mean():
    """JS shrinkage should pull extreme values toward the grand mean."""
    # Three groups: one far from grand mean, two near
    raw = [10.0, 0.0, 2.0]
    vars_ = [1.0, 1.0, 1.0]
    grand_mean = 4.0
    result = _js_shrinkage(raw, vars_, grand_mean)

    # The far value (10.0) should be pulled toward 4.0
    assert abs(result[0] - 4.0) < abs(raw[0] - 4.0)
    # The near values (0.0, 2.0) should also be pulled toward 4.0
    assert abs(result[1] - 4.0) < abs(raw[1] - 4.0)
    assert abs(result[2] - 4.0) < abs(raw[2] - 4.0)


def test_js_shrinkage_high_variance_stronger_shrinkage():
    """Higher within-group variance → larger B → stronger shrinkage toward grand mean.

    Formula B = (p-2) * pooled_var / sq_sum. Higher pooled_var → larger B →
    stronger pull toward grand_mean when B < 1, or clamped to 1 → all values = grand_mean.
    """
    raw = [50.0, -10.0, 20.0, 0.0]
    grand_mean = 15.0

    # Low variance → low B → weak shrinkage (values stay near raw)
    low_var = [0.1, 0.1, 0.1, 0.1]
    result_low = _js_shrinkage(raw, low_var, grand_mean)

    # High variance → B clamps to 1 → all values collapse to grand_mean
    high_var = [1000.0, 1000.0, 1000.0, 1000.0]
    result_high = _js_shrinkage(raw, high_var, grand_mean)

    # With high variance, values are pulled strongly toward grand_mean
    low_dev = sum(abs(r - grand_mean) for r in result_low)
    high_dev = sum(abs(r - grand_mean) for r in result_high)
    assert high_dev < low_dev
    # Each shrunk value must be closer to grand_mean than its raw value
    for r, s in zip(raw, result_high):
        assert abs(s - grand_mean) < abs(r - grand_mean)


def test_js_shrinkage_positive_part_never_overshoots():
    """Positive-part JS: B ∈ [0, 1], shrunk never overshoots grand_mean."""
    raw = [100.0, -50.0, 30.0, -20.0, 10.0]
    vars_ = [5.0, 5.0, 5.0, 5.0, 5.0]
    grand_mean = 14.0
    result = _js_shrinkage(raw, vars_, grand_mean)

    # Every shrunk value must be between raw and grand_mean (inclusive)
    for r, s in zip(raw, result):
        assert min(r, grand_mean) <= s <= max(r, grand_mean) or abs(r - s) < 1e-9, (
            f"shrunk={s} not between raw={r} and grand_mean={grand_mean}"
        )


def test_js_shrinkage_length_preserved():
    """Output length matches input length."""
    raw = [1.0, -2.0, 3.5, 0.0, -1.2, 4.0]
    vars_ = [0.5] * 6
    result = _js_shrinkage(raw, vars_, 1.0)
    assert len(result) == len(raw)


def test_js_shrinkage_symmetric_input():
    """Symmetric raw values around grand mean should stay symmetric (same B)."""
    raw = [5.0, 3.0, 1.0, -1.0, -3.0, -5.0]
    vars_ = [1.0] * 6
    grand_mean = 0.0
    result = _js_shrinkage(raw, vars_, grand_mean)
    # Symmetric around 0 should remain symmetric
    assert result[0] == pytest.approx(-result[-1])
    assert result[1] == pytest.approx(-result[-2])


# ═══════════════════════════════════════════════════════════════════
# _euclidean — Euclidean distance
# ═══════════════════════════════════════════════════════════════════

def test_euclidean_same_point_zero():
    assert _euclidean([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) == pytest.approx(0.0)


def test_euclidean_axis_aligned():
    assert _euclidean([0.0, 0.0], [3.0, 4.0]) == pytest.approx(5.0)


def test_euclidean_3d():
    dist = _euclidean([1.0, 2.0, 3.0], [4.0, 6.0, 8.0])
    expected = math.sqrt(9 + 16 + 25)  # √50 = ~7.071
    assert dist == pytest.approx(expected)


def test_euclidean_single_dimension():
    assert _euclidean([0.0], [10.0]) == pytest.approx(10.0)


# ═══════════════════════════════════════════════════════════════════
# _normalize_features — Min-max feature normalization
# ═══════════════════════════════════════════════════════════════════

def test_normalize_features_basic():
    """Features normalized to [0, 1] range for min-max dims (but not win_rate)."""
    cells = [
        CellFeatures(key="a::BTC", shrunk_bps=-5.0, combined_ev_bps=-3.0, win_rate=0.4,
                     avg_win_bps=10.0, avg_loss_bps=-10.0, n=50),
        CellFeatures(key="b::ETH", shrunk_bps=5.0, combined_ev_bps=7.0, win_rate=0.6,
                     avg_win_bps=15.0, avg_loss_bps=-5.0, n=30),
        CellFeatures(key="c::SOL", shrunk_bps=0.0, combined_ev_bps=2.0, win_rate=0.5,
                     avg_win_bps=12.0, avg_loss_bps=-8.0, n=40),
    ]
    feats = _normalize_features(cells)
    assert len(feats) == 3

    for f in feats:
        assert len(f) == 3
        # shrunk_bps_norm should be in [0, 1]
        assert 0.0 <= f[0] <= 1.0, f"shrunk_bps_norm out of range: {f[0]}"
        # win_rate already in [0, 1], passed through
        assert 0.0 <= f[1] <= 1.0
        # combined_ev_bps_norm should be in [0, 1]
        assert 0.0 <= f[2] <= 1.0, f"combined_ev_norm out of range: {f[2]}"


def test_normalize_features_single_cell():
    """Single cell → normalized to 0.0 (degenerate range → shift by 1)."""
    cells = [
        CellFeatures(key="a::BTC", shrunk_bps=3.0, combined_ev_bps=3.0, win_rate=0.55,
                     avg_win_bps=10.0, avg_loss_bps=-5.0, n=10),
    ]
    feats = _normalize_features(cells)
    assert len(feats) == 1
    # All values identical → min-max range [lo, lo] → _min_max clamps to [lo, lo+1]
    assert feats[0][0] == pytest.approx(0.0)  # (3 - 3) / 1
    assert feats[0][1] == pytest.approx(0.55)
    assert feats[0][2] == pytest.approx(0.0)


def test_normalize_features_all_same_values():
    """All cells have same shrunk_bps and combined_ev → range extended by 1."""
    cells = [
        CellFeatures(key="a::BTC", shrunk_bps=5.0, combined_ev_bps=5.0, win_rate=0.5,
                     avg_win_bps=10.0, avg_loss_bps=-10.0, n=10),
        CellFeatures(key="b::ETH", shrunk_bps=5.0, combined_ev_bps=5.0, win_rate=0.5,
                     avg_win_bps=10.0, avg_loss_bps=-10.0, n=10),
    ]
    feats = _normalize_features(cells)
    for f in feats:
        assert f[0] == pytest.approx(0.0)
        assert f[1] == pytest.approx(0.5)
        assert f[2] == pytest.approx(0.0)


# ═══════════════════════════════════════════════════════════════════
# _kmeans — Simple Lloyd's k-means
# ═══════════════════════════════════════════════════════════════════

def test_kmeans_basic_two_clusters():
    """Two well-separated clusters → k=2 assigns correctly."""
    feats = [
        [0.0, 0.0, 0.0],
        [0.1, 0.1, 0.0],
        [0.2, 0.0, 0.1],
        [10.0, 10.0, 10.0],
        [10.1, 10.1, 10.0],
        [10.2, 10.0, 10.1],
    ]
    labels = _kmeans(feats, k=2)
    assert len(labels) == 6
    # First three should be in one cluster, last three in another
    assert labels[0] == labels[1] == labels[2]
    assert labels[3] == labels[4] == labels[5]
    assert labels[0] != labels[3]


def test_kmeans_three_clusters():
    """Three well-separated clusters → k=3 assigns correctly."""
    feats = [
        [0.0, 0.0],
        [0.1, 0.1],
        [5.0, 5.0],
        [5.1, 5.1],
        [10.0, 10.0],
        [10.1, 10.1],
    ]
    labels = _kmeans(feats, k=3)
    assert len(set(labels)) == 3
    assert labels[0] == labels[1]
    assert labels[2] == labels[3]
    assert labels[4] == labels[5]


def test_kmeans_n_equals_k():
    """n == k → each point is its own cluster."""
    feats = [[1.0], [2.0], [3.0]]
    labels = _kmeans(feats, k=3)
    assert labels == [0, 1, 2]


def test_kmeans_n_less_than_k():
    """n < k → one cluster per point, no error."""
    feats = [[1.0], [2.0]]
    labels = _kmeans(feats, k=5)
    assert labels == [0, 1]


def test_kmeans_deterministic():
    """Same input → same output (deterministic initialization by sorted index)."""
    feats = [[3.0, 1.0], [1.0, 5.0], [2.0, 2.0], [5.0, 4.0], [4.0, 3.0]]
    labels1 = _kmeans(feats, k=2)
    labels2 = _kmeans(feats, k=2)
    assert labels1 == labels2


# ═══════════════════════════════════════════════════════════════════
# _label_clusters — Cluster naming
# ═══════════════════════════════════════════════════════════════════

def _make_cell(key, shrunk_bps, win_rate=0.5, combined_ev_bps=0.0, n=10):
    return CellFeatures(
        key=key, shrunk_bps=shrunk_bps, combined_ev_bps=combined_ev_bps,
        win_rate=win_rate, avg_win_bps=10.0, avg_loss_bps=-10.0, n=n,
    )


def test_label_clusters_two_clusters():
    """k=2: highest mean shrunk_bps → "candidate", lowest → "underperformer"."""
    cells = [
        _make_cell("a::BTC", shrunk_bps=5.0),
        _make_cell("b::ETH", shrunk_bps=-3.0),
    ]
    # Cluster 0 has mean 5.0, cluster 1 has mean -3.0
    labels = [0, 1]
    names = _label_clusters(cells, labels, k=2)
    assert names[0] == "candidate"
    assert names[1] == "underperformer"


def test_label_clusters_three_clusters():
    """k=3: best → "candidate", middle → "middle", worst → "underperformer"."""
    cells = [
        _make_cell("a::BTC", shrunk_bps=10.0),
        _make_cell("b::ETH", shrunk_bps=0.0),
        _make_cell("c::SOL", shrunk_bps=-5.0),
    ]
    labels = [0, 1, 2]
    names = _label_clusters(cells, labels, k=3)
    assert names[0] == "candidate"
    assert names[1] == "middle"
    assert names[2] == "underperformer"


def test_label_clusters_same_label_for_same_cluster():
    """All cells in same cluster get same label name."""
    cells = [
        _make_cell("a::BTC", shrunk_bps=2.0),
        _make_cell("b::ETH", shrunk_bps=2.0),
        _make_cell("c::SOL", shrunk_bps=2.0),
    ]
    labels = [0, 0, 1]
    names = _label_clusters(cells, labels, k=2)
    assert names[0] == names[1]
    assert names[0] != names[2]


def test_label_clusters_output_length_matches_input():
    cells = [_make_cell(f"x{i}::SYM", shrunk_bps=i - 2.0) for i in range(5)]
    labels = [0, 0, 1, 1, 1]
    names = _label_clusters(cells, labels, k=2)
    assert len(names) == len(cells)
    assert len(names) == len(labels)


# ═══════════════════════════════════════════════════════════════════
# _normal_cdf — Standard normal CDF via erf
# ═══════════════════════════════════════════════════════════════════

def test_normal_cdf_zero():
    """Φ(0) = 0.5."""
    assert _normal_cdf(0.0) == pytest.approx(0.5)


def test_normal_cdf_symmetry():
    """Φ(-x) = 1 - Φ(x)."""
    for x in [0.5, 1.0, 2.0, 3.0]:
        assert _normal_cdf(-x) == pytest.approx(1.0 - _normal_cdf(x))


def test_normal_cdf_known_values():
    """Check against known standard normal CDF values."""
    # Φ(1) ≈ 0.8413, Φ(2) ≈ 0.9772, Φ(-1) ≈ 0.1587
    assert _normal_cdf(1.0) == pytest.approx(0.841344746, abs=1e-6)
    assert _normal_cdf(2.0) == pytest.approx(0.977249868, abs=1e-6)
    assert _normal_cdf(-1.0) == pytest.approx(0.158655254, abs=1e-6)


def test_normal_cdf_large_pos():
    """Large positive → ≈ 1.0."""
    assert _normal_cdf(10.0) == pytest.approx(1.0, abs=1e-10)


def test_normal_cdf_large_neg():
    """Large negative → ≈ 0.0."""
    assert _normal_cdf(-10.0) == pytest.approx(0.0, abs=1e-10)


def test_normal_cdf_bounds():
    """CDF always in [0, 1]."""
    for x in [-100.0, -5.0, -1.0, 0.0, 1.0, 5.0, 100.0]:
        val = _normal_cdf(x)
        assert 0.0 <= val <= 1.0, f"CDF({x}) = {val} outside [0,1]"


# ═══════════════════════════════════════════════════════════════════
# _finite_values — Filter out NaN and inf
# ═══════════════════════════════════════════════════════════════════

def test_finite_values_keeps_finites():
    assert _finite_values([1.0, 2.0, 3.0]) == [1.0, 2.0, 3.0]


def test_finite_values_removes_nan():
    result = _finite_values([1.0, float("nan"), 3.0])
    assert result == [1.0, 3.0]


def test_finite_values_removes_inf():
    result = _finite_values([1.0, float("inf"), float("-inf"), 2.0])
    assert result == [1.0, 2.0]


def test_finite_values_all_bad():
    assert _finite_values([float("nan"), float("inf")]) == []


def test_finite_values_empty():
    assert _finite_values([]) == []


# ═══════════════════════════════════════════════════════════════════
# _sample_mean_std — Sample mean and std
# ═══════════════════════════════════════════════════════════════════

def test_sample_mean_std_basic():
    mean, std = _sample_mean_std([1.0, 2.0, 3.0, 4.0, 5.0])
    assert mean == pytest.approx(3.0)
    # Sample std (n-1 denominator): sqrt((4+1+0+1+4)/4) = sqrt(2.5) ≈ 1.581
    assert std == pytest.approx(math.sqrt(2.5))


def test_sample_mean_std_single_value():
    mean, std = _sample_mean_std([42.0])
    assert mean == pytest.approx(42.0)
    assert std == 0.0


def test_sample_mean_std_empty():
    mean, std = _sample_mean_std([])
    assert mean == 0.0
    assert std == 0.0


def test_sample_mean_std_identical():
    mean, std = _sample_mean_std([5.0, 5.0, 5.0, 5.0])
    assert mean == pytest.approx(5.0)
    assert std == pytest.approx(0.0)


def test_sample_mean_std_negative_values():
    mean, std = _sample_mean_std([-3.0, -1.0, 0.0, 1.0, 3.0])
    assert mean == pytest.approx(0.0)
    # Sample std: sqrt((9+1+0+1+9)/4) = sqrt(5) ≈ 2.236
    assert std == pytest.approx(math.sqrt(5.0))

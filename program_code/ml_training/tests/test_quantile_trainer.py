"""Tests for quantile_trainer — pure-numpy helpers + end-to-end (lgb-guarded).
quantile_trainer 測試 — pure-numpy 輔助 + 端到端（lgb 守衛）。"""
from __future__ import annotations

import numpy as np
import pytest

from program_code.ml_training.quantile_trainer import (
    QUANTILE_ALPHAS,
    EmbargoConfig,
    QuantileTrainingConfig,
    _compute_feature_schema_hash,
    _split_tail_holdout,
    check_quantile_crossing_rate,
    compute_coverage_error,
    compute_decile_lift_bootstrap,
    compute_pinball_skill,
    compute_sample_weights,
    get_embargo_config,
    pinball_loss,
    train_quantile_trio,
)


# ──────────────── get_embargo_config ────────────────

def test_get_embargo_config_funding_arb_carve_out():
    cfg = get_embargo_config("funding_arb")
    assert isinstance(cfg, EmbargoConfig)
    assert cfg.n_folds == 3
    assert cfg.embargo_hours == 72
    assert cfg.holdout_tail_days == 14.0


def test_get_embargo_config_default_trending():
    cfg = get_embargo_config("ma_crossover")
    assert cfg.n_folds == 5
    assert cfg.embargo_hours == 24
    assert cfg.holdout_tail_days == 7.0


def test_get_embargo_config_case_insensitive():
    assert get_embargo_config("FUNDING_ARB").n_folds == 3
    assert get_embargo_config("  Funding_Arb  ").n_folds == 3


# ──────────────── compute_sample_weights ────────────────

def test_compute_sample_weights_recent_has_higher_weight():
    ts = np.array([0, 86_400_000, 2 * 86_400_000, 3 * 86_400_000], dtype=np.int64)
    w = compute_sample_weights(ts, halflife_days=14.0)
    # reference defaults to max(ts); most-recent → weight 1.
    # 最新時間戳權重為 1。
    assert w[-1] == pytest.approx(1.0)
    assert w[0] < w[1] < w[2] < w[3]


def test_compute_sample_weights_empty_input():
    w = compute_sample_weights(np.array([], dtype=np.int64))
    assert w.shape == (0,)


def test_compute_sample_weights_future_timestamp_clipped():
    # Stray future sample should not get >1.0 weight (ref=latest of provided ts).
    # 未來戳不得超過 1.0 權重。
    ts = np.array([0, 86_400_000], dtype=np.int64)
    w = compute_sample_weights(ts, halflife_days=14.0, reference_ms=0)
    # ts[1] is 'after' ref → days_ago = -1 → clipped to 0 → w=1.
    # ts[0] = ref → w=1.
    assert w[0] == pytest.approx(1.0)
    assert w[1] == pytest.approx(1.0)


# ──────────────── pinball_loss + skill ────────────────

def test_pinball_loss_median_equals_mean_abs_error_half():
    # At alpha=0.5 pinball reduces to 0.5 * |y - y_pred|.
    # alpha=0.5 時 pinball 退化為 0.5 * |y - y_pred|。
    y = np.array([1.0, 2.0, 3.0])
    p = np.array([2.0, 2.0, 2.0])
    loss = pinball_loss(y, p, alpha=0.5)
    expected = 0.5 * np.mean(np.abs(y - p))
    assert loss == pytest.approx(expected)


def test_pinball_loss_alpha_low_penalises_overprediction():
    # alpha=0.1: underprediction (y > p) cheap; overprediction (y < p) expensive.
    # alpha=0.1：低估便宜、高估貴。
    y = np.array([5.0])
    p_over = np.array([10.0])
    p_under = np.array([0.0])
    loss_over = pinball_loss(y, p_over, alpha=0.1)
    loss_under = pinball_loss(y, p_under, alpha=0.1)
    assert loss_over > loss_under


def test_compute_pinball_skill_baseline_zero_returns_zero():
    y = np.array([5.0, 5.0, 5.0])
    p = np.array([5.0, 5.0, 5.0])
    skill, m_loss, b_loss = compute_pinball_skill(y, p, alpha=0.5, baseline_constant=5.0)
    assert skill == 0.0
    assert b_loss == 0.0


def test_compute_pinball_skill_model_beats_constant():
    # y mostly near 0, q50 model predicts 0, constant baseline = 10 (bad).
    # 模型預測接近 y，常數基線偏離；模型 skill 應為正。
    rng = np.random.default_rng(0)
    y = rng.standard_normal(500) * 0.5
    p = rng.standard_normal(500) * 0.1  # nearly-correct
    skill, m_loss, b_loss = compute_pinball_skill(y, p, alpha=0.5, baseline_constant=10.0)
    assert skill > 0.5  # model much better than baseline
    assert m_loss < b_loss


# ──────────────── coverage ────────────────

def test_compute_coverage_error_exact_match():
    y = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    q = np.full_like(y, 1.0)  # only y=1 is <= 1 → empirical = 1/10 = 0.1
    empirical, err_pp = compute_coverage_error(y, q, alpha=0.10)
    assert empirical == pytest.approx(0.1)
    assert err_pp == pytest.approx(0.0)


def test_compute_coverage_error_empty():
    empirical, err_pp = compute_coverage_error(np.array([]), np.array([]), alpha=0.1)
    assert empirical == 0.0 and err_pp == 0.0


# ──────────────── crossing ────────────────

def test_check_quantile_crossing_rate_no_violations():
    q10 = np.array([1.0, 1.0, 1.0])
    q50 = np.array([2.0, 2.0, 2.0])
    q90 = np.array([3.0, 3.0, 3.0])
    assert check_quantile_crossing_rate(q10, q50, q90) == 0.0


def test_check_quantile_crossing_rate_all_violations():
    q10 = np.array([3.0, 3.0, 3.0])
    q50 = np.array([2.0, 2.0, 2.0])
    q90 = np.array([1.0, 1.0, 1.0])
    assert check_quantile_crossing_rate(q10, q50, q90) == pytest.approx(1.0)


def test_check_quantile_crossing_rate_partial_violation():
    # One row violates q10 > q50.
    # 一個樣本 q10 > q50。
    q10 = np.array([1.0, 3.0])
    q50 = np.array([2.0, 2.0])
    q90 = np.array([3.0, 4.0])
    assert check_quantile_crossing_rate(q10, q50, q90) == pytest.approx(0.5)


# ──────────────── decile lift bootstrap ────────────────

def test_compute_decile_lift_bootstrap_small_sample_returns_zero():
    y = np.arange(10, dtype=float)
    p = np.arange(10, dtype=float)
    point, lo, hi = compute_decile_lift_bootstrap(y, p, n_boot=10)
    assert point == 0.0 and lo == 0.0 and hi == 0.0


def test_compute_decile_lift_bootstrap_strong_signal():
    # Monotone data: top decile y much larger than median decile y → lift >> 1.
    # 單調資料：top decile 的 y 遠大於中位 decile → lift >> 1。
    rng = np.random.default_rng(1)
    n = 500
    p = np.arange(n, dtype=float)
    y = p + rng.standard_normal(n) * 0.1 + 50.0  # keep median mean > 0
    point, lo, hi = compute_decile_lift_bootstrap(y, p, n_boot=200, seed=7)
    assert point > 1.5
    assert lo < hi


# ──────────────── feature schema hash ────────────────

def test_feature_schema_hash_stable_across_calls():
    names = ["a", "b", "c"]
    h1 = _compute_feature_schema_hash(names, "v1")
    h2 = _compute_feature_schema_hash(names, "v1")
    assert h1 == h2
    # Rust-parity format: `sha256:` + 16 hex chars (see quantile_trainer
    # docstring; version is NOT mixed into the payload, mirroring Rust's
    # names-only authority implementation).
    # Rust 對齊格式：`sha256:` + 16 hex；版本不入 payload。
    assert h1.startswith("sha256:")
    assert len(h1) == len("sha256:") + 16
    # Order matters (trailing \n after each name makes reordering visible).
    # 順序敏感（每名後 \n 確保重排可見）。
    assert _compute_feature_schema_hash(["b", "a", "c"], "v1") != h1


def test_feature_schema_hash_matches_rust_format_pinned():
    """Byte-for-byte parity with Rust compute_feature_schema_hash.
    Failing this test means tract_backend would reject every artifact
    produced by this trainer at load time.
    與 Rust 逐字節對齊 — 失敗即所有產出在 Rust 載入時被拒。"""
    import hashlib as _h
    names = ["price", "volume", "atr"]
    digest = _h.sha256()
    for n in names:
        digest.update(n.encode("utf-8"))
        digest.update(b"\n")
    expected = "sha256:" + digest.hexdigest()[:16]
    assert _compute_feature_schema_hash(names, "v1") == expected


# ──────────────── tail holdout split ────────────────

def test_split_tail_holdout_uses_time_window_when_long_enough():
    # 30d timestamps with 7d tail; holdout should be ~last 7d worth of rows.
    # 30d 時間戳 + 7d tail；holdout 約為最後 7d 的樣本。
    n = 300
    day_ms = 86_400_000
    ts = np.linspace(0, 30 * day_ms, n).astype(np.int64)
    train_idx, holdout_idx = _split_tail_holdout(ts, holdout_tail_days=7.0)
    # Roughly n * 7/30 ≈ 70 rows in holdout; accept wide band.
    # 約 n*7/30 ≈ 70；寬鬆容忍 ±15。
    assert 55 <= len(holdout_idx) <= 85
    assert len(train_idx) + len(holdout_idx) == n


def test_split_tail_holdout_falls_back_to_fraction_on_short_span():
    # Compressed synthetic ts (1-minute bars over 600 mins) < 7d window.
    # 合成時間戳總跨度 < 7d → fall back fractional 20%。
    n = 600
    ts = np.arange(n, dtype=np.int64) * 60_000
    train_idx, holdout_idx = _split_tail_holdout(ts, holdout_tail_days=7.0, min_fraction=0.2)
    assert len(holdout_idx) == int(n * 0.2)
    assert len(train_idx) == n - len(holdout_idx)


# ──────────────── train_quantile_trio (needs lightgbm) ────────────────

def test_train_quantile_trio_requires_matched_lengths():
    cfg = QuantileTrainingConfig()
    result = train_quantile_trio(
        features=np.zeros((100, 5), dtype=np.float32),
        labels=np.zeros(50, dtype=np.float32),
        timestamps_ms=np.zeros(100, dtype=np.int64),
        feature_names=["a", "b", "c", "d", "e"],
        strategy_name="ma_crossover",
        config=cfg,
    )
    assert not result.success
    assert "mismatch" in result.error


def test_train_quantile_trio_rejects_empty_input():
    cfg = QuantileTrainingConfig()
    result = train_quantile_trio(
        features=np.zeros((0, 5), dtype=np.float32),
        labels=np.zeros(0, dtype=np.float32),
        timestamps_ms=np.zeros(0, dtype=np.int64),
        feature_names=["a", "b", "c", "d", "e"],
        strategy_name="ma_crossover",
        config=cfg,
    )
    assert not result.success


def test_train_quantile_trio_end_to_end_synthetic():
    """End-to-end fit on deterministic synthetic data. Requires lightgbm.
    端到端合成資料擬合（需 lightgbm）。"""
    pytest.importorskip("lightgbm")

    rng = np.random.default_rng(0)
    n = 800
    n_features = 6
    X = rng.standard_normal((n, n_features)).astype(np.float32)
    # Strong first-feature signal + modest noise.
    # 首特徵強信號 + 中等噪音。
    y = (X[:, 0] * 1.5 + rng.standard_normal(n) * 0.5 + 1.0).astype(np.float32)
    ts = (np.arange(n, dtype=np.int64) * 60_000)

    cfg = QuantileTrainingConfig(
        n_estimators=60, early_stopping_rounds=10, bootstrap_iterations=50,
    )
    result = train_quantile_trio(
        features=X, labels=y, timestamps_ms=ts,
        feature_names=[f"f{i}" for i in range(n_features)],
        strategy_name="ma_crossover", engine_mode="paper", config=cfg,
    )

    assert result.success, result.error
    assert set(result.models.keys()) == {"q10", "q50", "q90"}
    # Crossing rate low on well-behaved synthetic.
    # 乾淨合成資料的違反率應低。
    assert result.crossing_rate < 0.2
    # schema hash present and in Rust-parity format (`sha256:<16 hex>`).
    # schema hash 存在且為 Rust 對齊格式。
    assert result.feature_schema_hash.startswith("sha256:")
    assert len(result.feature_schema_hash) == len("sha256:") + 16
    # q50 pinball skill should clear 0.10 threshold easily on this signal.
    # 強訊號資料 q50 pinball skill 輕鬆過 0.10。
    assert result.per_quantile_metrics["q50"].pinball_skill > 0.10

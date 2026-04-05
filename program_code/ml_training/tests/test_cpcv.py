"""Tests for CPCV validator module / CPCV 驗證器測試"""

import numpy as np

from program_code.ml_training.cpcv_validator import (
    CPCVConfig,
    generate_folds,
    get_embargo_hours,
    estimate_power,
    validate_cpcv,
)

# ── Helpers / 輔助 ──────────────────────────────────────────────

# 180 days of hourly timestamps starting from 2026-01-01 00:00 UTC
_BASE_TS = 1_767_225_600  # 2026-01-01T00:00:00Z epoch seconds
_N_HOURS = 180 * 24  # 4320 hourly samples
_TIMESTAMPS = np.arange(_N_HOURS, dtype=np.float64) * 3600.0 + _BASE_TS

_DEFAULT_CONFIG = CPCVConfig()


# ── 1. Fold count / 折疊數 ─────────────────────────────────────

def test_generate_folds_count():
    """4 folds are generated / 生成 4 個折疊"""
    folds = generate_folds(_TIMESTAMPS, "trending", _DEFAULT_CONFIG)
    assert len(folds) == 4


# ── 2. Non-overlapping test sets / 測試集不重疊 ────────────────

def test_generate_folds_non_overlapping():
    """Test indices don't overlap across folds / 測試索引跨折疊不重疊"""
    folds = generate_folds(_TIMESTAMPS, "trending", _DEFAULT_CONFIG)
    all_test = np.concatenate([test for _, test in folds])
    assert len(all_test) == len(np.unique(all_test))


# ── 3. Coverage / 覆蓋率 ──────────────────────────────────────

def test_generate_folds_covers_all():
    """Union of test indices covers all samples / 測試索引聯集覆蓋所有樣本"""
    folds = generate_folds(_TIMESTAMPS, "trending", _DEFAULT_CONFIG)
    all_test = np.sort(np.concatenate([test for _, test in folds]))
    expected = np.arange(len(_TIMESTAMPS))
    np.testing.assert_array_equal(all_test, expected)


# ── 4. Purge removes boundary samples / 清洗移除邊界樣本 ──────

def test_purge_removes_boundary_samples():
    """Train indices near fold boundary are purged / 折疊邊界附近的訓練索引被清洗"""
    config = CPCVConfig(label_window_hours=4.0, embargo_map={"trending": 0})
    folds = generate_folds(_TIMESTAMPS, "trending", config)

    # For fold 0 as test, check that the training set does NOT include
    # samples just after the test fold whose label window reaches back in
    _, test_idx = folds[0]
    train_idx = folds[0][0]
    test_end_ts = _TIMESTAMPS[test_idx[-1]]
    purge_sec = config.label_window_hours * 3600.0

    # Samples in (test_end, test_end + purge) should be removed from train
    # 在 (test_end, test_end + purge) 的樣本應該從訓練集移除
    for idx in train_idx:
        ts = _TIMESTAMPS[idx]
        if ts > test_end_ts:
            assert ts - purge_sec >= test_end_ts, (
                f"Sample at ts={ts} should have been purged "
                f"(test_end={test_end_ts}, purge_sec={purge_sec})"
            )


# ── 5. Embargo trending 24h / 趨勢策略 embargo 24h ───────────

def test_embargo_trending_24h():
    """Trending strategy applies 24h embargo / 趨勢策略使用 24h embargo"""
    assert get_embargo_hours("trending") == 24
    assert get_embargo_hours("ma_crossover") == 24

    # Verify in fold generation: train must not include 24h after test end
    config = CPCVConfig(label_window_hours=0.0)  # zero purge to isolate embargo
    folds = generate_folds(_TIMESTAMPS, "trending", config)
    _, test_idx = folds[0]
    train_idx = folds[0][0]
    test_end_ts = _TIMESTAMPS[test_idx[-1]]
    embargo_sec = 24 * 3600.0

    for idx in train_idx:
        ts = _TIMESTAMPS[idx]
        if ts > test_end_ts:
            assert ts > test_end_ts + embargo_sec, (
                f"Sample at ts={ts} within 24h embargo after test_end={test_end_ts}"
            )


# ── 6. Embargo reversion 4h / 回歸策略 embargo 4h ────────────

def test_embargo_reversion_4h():
    """Reversion strategy applies 4h embargo / 回歸策略使用 4h embargo"""
    assert get_embargo_hours("reversion") == 4
    assert get_embargo_hours("bb_reversion") == 4

    config = CPCVConfig(label_window_hours=0.0)
    folds = generate_folds(_TIMESTAMPS, "reversion", config)
    _, test_idx = folds[0]
    train_idx = folds[0][0]
    test_end_ts = _TIMESTAMPS[test_idx[-1]]
    embargo_sec = 4 * 3600.0

    for idx in train_idx:
        ts = _TIMESTAMPS[idx]
        if ts > test_end_ts:
            assert ts > test_end_ts + embargo_sec


# ── 7. Embargo grid 72h / 網格策略 embargo 72h ───────────────

def test_embargo_grid_72h():
    """Grid strategy applies 72h embargo / 網格策略使用 72h embargo"""
    assert get_embargo_hours("grid") == 72
    assert get_embargo_hours("grid_trading") == 72

    config = CPCVConfig(label_window_hours=0.0)
    folds = generate_folds(_TIMESTAMPS, "grid", config)
    _, test_idx = folds[0]
    train_idx = folds[0][0]
    test_end_ts = _TIMESTAMPS[test_idx[-1]]
    embargo_sec = 72 * 3600.0

    for idx in train_idx:
        ts = _TIMESTAMPS[idx]
        if ts > test_end_ts:
            assert ts > test_end_ts + embargo_sec


# ── 8. Embargo arb 8h / 套利策略 embargo 8h ──────────────────

def test_embargo_arb_8h():
    """Arb strategy applies 8h embargo / 套利策略使用 8h embargo"""
    assert get_embargo_hours("arb") == 8
    assert get_embargo_hours("funding_arb") == 8

    config = CPCVConfig(label_window_hours=0.0)
    folds = generate_folds(_TIMESTAMPS, "arb", config)
    _, test_idx = folds[1]
    train_idx = folds[1][0]
    test_end_ts = _TIMESTAMPS[test_idx[-1]]
    embargo_sec = 8 * 3600.0

    for idx in train_idx:
        ts = _TIMESTAMPS[idx]
        if ts > test_end_ts:
            assert ts > test_end_ts + embargo_sec


# ── 9. Power guard insufficient / 功效不足 ───────────────────

def test_power_guard_insufficient():
    """<30 samples per fold → power < 0.5 → passed=False
    每折少於 30 樣本 → 功效 < 0.5 → 不通過"""
    # 40 total samples → 10 per fold — well below min_samples_per_fold
    n_tiny = 40
    tiny_ts = np.linspace(_BASE_TS, _BASE_TS + 180 * 86400, n_tiny)
    X = np.random.RandomState(42).randn(n_tiny, 5)
    y = np.random.RandomState(42).randn(n_tiny)

    def mock_model(X_tr, y_tr, X_te, y_te):
        return {"sharpe": 0.5, "rmse": 0.1}

    result = validate_cpcv(X, y, tiny_ts, "trending", mock_model)
    assert result.power_estimate < 0.5
    assert result.passed is False


# ── 10. Full pipeline with mock model / 完整管線 ─────────────

def test_validate_cpcv_with_mock_model():
    """Full CPCV pipeline with mock model_fn / 完整 CPCV 管線搭配模擬模型"""
    n = len(_TIMESTAMPS)
    rng = np.random.RandomState(123)
    X = rng.randn(n, 10)
    y = rng.randn(n)

    call_count = 0

    def mock_model(X_tr, y_tr, X_te, y_te):
        nonlocal call_count
        call_count += 1
        # Return positive Sharpe for pass scenario
        return {
            "sharpe": 0.8 + 0.1 * call_count,
            "rmse": 0.05,
            "correlation": 0.6,
        }

    result = validate_cpcv(X, y, _TIMESTAMPS, "reversion", mock_model)

    # model_fn called once per fold / 每折調用一次模型
    assert call_count == 4
    assert result.n_folds == 4
    assert result.strategy_type == "reversion"
    assert result.embargo_hours == 4
    assert len(result.fold_metrics) == 4

    # With 4320 samples, power should be high / 4320 樣本功效應該很高
    assert result.power_estimate > 0.9

    # Mean Sharpe > 0 and high power → passed / 平均 Sharpe > 0 且高功效 → 通過
    assert result.mean_sharpe > 0
    assert result.passed is True
    assert result.std_sharpe >= 0

    # Each fold metric has injected fields / 每折指標有注入欄位
    for m in result.fold_metrics:
        assert "fold" in m
        assert "n_train" in m
        assert "n_test" in m
        assert "sharpe" in m

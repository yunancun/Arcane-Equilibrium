"""Tests for leakage_check module / 洩漏檢查測試"""

from program_code.ml_training.leakage_check import check_feature_leakage


def test_clean_features_pass():
    names = ["sma_20", "ema_12", "rsi_14", "atr_14", "price", "volume_ratio"]
    passed, violations = check_feature_leakage(names)
    assert passed
    assert len(violations) == 0


def test_outcome_column_detected():
    names = ["sma_20", "outcome_1h", "rsi_14"]
    passed, violations = check_feature_leakage(names)
    assert not passed
    assert any("outcome_" in v for v in violations)


def test_future_price_detected():
    names = ["sma_20", "future_price_1h"]
    passed, violations = check_feature_leakage(names)
    assert not passed


def test_strict_unknown_flagged():
    names = ["sma_20", "my_custom_feature"]
    passed, violations = check_feature_leakage(names, strict=True)
    assert not passed
    assert any("UNKNOWN" in v for v in violations)


def test_non_strict_unknown_allowed():
    names = ["sma_20", "my_custom_feature"]
    passed, violations = check_feature_leakage(names, strict=False)
    assert passed  # only forbidden patterns checked

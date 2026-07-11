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


# --- run_pipeline 接線測試（audit remediation item 4）-----------------------------
# 這些測試證明 leakage_check 不再是死碼：run_pipeline 在任何 fit 之前確實跑 name-pattern
# 預篩，forbidden pattern fail-closed，clean run 產出 name_pattern_check evidence。
# monkeypatch _load_dataset 與 inner pipeline 以避開 lightgbm/onnx 重依賴。

from program_code.ml_training import run_training_pipeline as rtp


def _stub_dataset(feature_names, n=32):
    """回傳 run_pipeline 期望的 5-tuple；features/timestamps 在被 stub 的路徑用不到。"""
    labels = [0.0] * n
    return None, labels, None, feature_names, None


def test_run_pipeline_forbidden_feature_name_fails_closed(monkeypatch):
    # 特徵名帶 forbidden pattern → fit 前必須 fail-closed，且不進入 dispatch。
    monkeypatch.setattr(
        rtp, "_load_dataset",
        lambda config: _stub_dataset(["adx_1h", "outcome_1h", "atr_pct"]),
    )

    def _boom(*args, **kwargs):  # 不該被呼叫：預篩失敗必須在 dispatch 前中止
        raise AssertionError("dispatch reached despite forbidden feature name")

    monkeypatch.setattr(rtp, "_run_legacy_scorer_pipeline", _boom)
    monkeypatch.setattr(rtp, "_run_quantile_pipeline", _boom)

    cfg = rtp.PipelineConfig(use_quantile_predictor=False, min_samples=5)
    res = rtp.run_pipeline(cfg)

    assert res.success is False
    assert "feature_leakage_forbidden_pattern" in res.error
    assert "feature_leakage_prescreen_failed" in res.stages_completed
    finding = res.metrics["leakage_prescreen"]
    assert finding["passed"] is False
    assert finding["source_class"] == "name_pattern_check"
    assert finding["leak_free_pit_claim"] is False


def test_run_pipeline_clean_features_emit_prescreen_evidence(monkeypatch):
    # clean 特徵集 → 預篩通過，stage 與 name_pattern_check evidence 出現在成功結果上。
    clean_names = ["adx_1h", "bb_width_pct", "atr_pct", "spread_bps"]
    monkeypatch.setattr(
        rtp, "_load_dataset", lambda config: _stub_dataset(clean_names),
    )
    monkeypatch.setattr(
        rtp, "_run_legacy_scorer_pipeline",
        lambda config, *a, **k: rtp.PipelineResult(
            success=True, stages_completed=["cpcv_training"], metrics={},
        ),
    )

    cfg = rtp.PipelineConfig(use_quantile_predictor=False, min_samples=5)
    res = rtp.run_pipeline(cfg)

    assert res.success is True
    assert "feature_leakage_prescreen" in res.stages_completed
    finding = res.metrics["leakage_prescreen"]
    assert finding["passed"] is True
    assert finding["violations"] == []
    assert finding["source_class"] == "name_pattern_check"
    assert finding["leak_free_pit_claim"] is False

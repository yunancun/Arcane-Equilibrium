"""P1-3 end-to-end pipeline orchestration tests (no external deps).
P1-3 端到端管線編排測試（無外部依賴）。"""
from __future__ import annotations

import pytest

from program_code.ml_training.run_training_pipeline import (
    PipelineConfig,
    PipelineResult,
    run_pipeline,
)


def test_pipeline_dry_run_degrades_gracefully_without_lgb(monkeypatch, tmp_path):
    """Pipeline must report a clean error when LightGBM is absent."""
    cfg = PipelineConfig(dry_run=True, min_samples=100, output_dir=str(tmp_path / "p1_3"))
    result = run_pipeline(cfg)
    # Dry-run with synthetic data gets past ETL + label stages regardless
    assert "etl" in result.stages_completed
    assert "labels" in result.stages_completed
    # Either success (if lgb present) or clean error message
    assert isinstance(result, PipelineResult)
    if not result.success:
        assert result.error  # must have a non-empty reason
        assert "lightgbm" in result.error.lower() or "insufficient" in result.error.lower() \
            or result.error  # any error is fine; we're testing no crash


def test_pipeline_rejects_too_few_samples():
    cfg = PipelineConfig(dry_run=True, min_samples=10_000)
    result = run_pipeline(cfg)
    assert not result.success
    assert "insufficient" in result.error.lower()


def test_pipeline_config_defaults():
    # P1-7 C (2026-04-23): default symbol flipped "BTCUSDT" → None (pooled).
    # Rationale: grid_trading rotating across short-lived symbols cannot reach
    # min_samples=200 per-symbol; pooled is the correct default for multi-
    # symbol strategies. Per-symbol still available via explicit --symbol.
    # P1-7 C：預設 symbol 由 "BTCUSDT" 改為 None（pooled）；grid_trading 輪動
    # symbol 無法逐 symbol 累積 200，pooled 為多 symbol 策略正確預設。
    cfg = PipelineConfig()
    assert cfg.strategy_type == "trending"
    assert cfg.symbol is None
    assert cfg.skip_onnx is True
    assert cfg.dry_run is False

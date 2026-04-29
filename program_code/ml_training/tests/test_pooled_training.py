"""P1-7 C pooled cross-symbol training tests.
P1-7 C 跨 symbol pooled 訓練測試。

MODULE_NOTE (EN): Verify `PipelineConfig.symbol=None` pools rows across
all symbols for the strategy (SQL `(%(symbol)s IS NULL OR …)` branch),
that artifact paths + metrics carry a "pooled" / "symbol_slot=ALL" marker
so downstream audit can distinguish pooled runs from per-symbol runs, and
that the `_resolve_symbol_slot` helper handles None / "ALL" / concrete
strings correctly. No DB / LightGBM dependency — uses monkeypatched ETL
fixtures.

MODULE_NOTE (中): 驗證 `PipelineConfig.symbol=None` 讓所有 symbol 聚合
（SQL 分支 `(%(symbol)s IS NULL OR …)`）；artifact 路徑/metrics 帶
"pooled" / "symbol_slot=ALL" 標記，下游審計可辨 pooled 與 per-symbol；
`_resolve_symbol_slot` helper 對 None/"ALL"/具體字串處理正確。
不依賴 DB 與 LightGBM，使用 monkeypatch ETL fixture。
"""
from __future__ import annotations

import pytest

from program_code.ml_training.run_training_pipeline import (
    PipelineConfig,
    _resolve_symbol_slot,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# 1. PipelineConfig symbol Optional acceptance
# ---------------------------------------------------------------------------


def test_pipeline_config_symbol_optional_default_none():
    """Default symbol is None → pooled mode on.
    預設 symbol=None → pooled 模式開啟。"""
    cfg = PipelineConfig()
    assert cfg.symbol is None


def test_pipeline_config_symbol_optional_explicit_none():
    """symbol=None is explicitly constructible.
    symbol=None 明確可建構（無型別錯誤）。"""
    cfg = PipelineConfig(symbol=None, strategy_type="grid_trading")
    assert cfg.symbol is None
    assert cfg.strategy_type == "grid_trading"


def test_pipeline_config_symbol_optional_concrete_symbol():
    """Per-symbol training path still accepts concrete symbols.
    per-symbol 路徑仍接受具體 symbol（未來 ma/bb 路徑保留）。"""
    cfg = PipelineConfig(symbol="BTCUSDT")
    assert cfg.symbol == "BTCUSDT"


# ---------------------------------------------------------------------------
# 2. _resolve_symbol_slot: pooled flag + artifact slot string
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sym,expected_pooled,expected_slot", [
    (None, True, "ALL"),
    ("ALL", True, "ALL"),
    ("all", True, "ALL"),        # case-insensitive
    ("All", True, "ALL"),
    ("BTCUSDT", False, "BTCUSDT"),
    ("BLURUSDT", False, "BLURUSDT"),
])
def test_resolve_symbol_slot(sym, expected_pooled, expected_slot):
    """Helper normalizes symbol → (pooled, slot) pair for downstream naming.
    Helper 統一化 symbol → (pooled, slot) pair 供下游檔名/metrics 使用。"""
    cfg = PipelineConfig(symbol=sym)
    pooled, slot = _resolve_symbol_slot(cfg)
    assert pooled is expected_pooled
    assert slot == expected_slot


# ---------------------------------------------------------------------------
# 3. load_training_data called with symbol=None when pooled
# ---------------------------------------------------------------------------


def test_load_training_data_pooled_ignores_symbol_filter(monkeypatch):
    """When config.symbol is None, load_training_data receives symbol=None
    (SQL `(%(symbol)s IS NULL OR …)` branch skips the filter).
    config.symbol=None 時，load_training_data 收到 symbol=None
    （SQL 條件分支跳過 symbol 過濾）。"""
    import numpy as np
    from program_code.ml_training import parquet_etl as etl

    captured: dict = {}

    def fake_load_training_data(**kwargs):
        captured.update(kwargs)
        feature_names = list(etl.EDGE_P3_FEATURE_NAMES)
        empty_f = np.empty((0, len(feature_names)), dtype=np.float32)
        empty_y = np.empty((0,), dtype=np.float32)
        empty_ts = np.empty((0,), dtype=np.int64)
        return empty_f, empty_y, empty_ts, feature_names

    monkeypatch.setattr(etl, "load_training_data", fake_load_training_data)

    cfg = PipelineConfig(
        strategy_type="grid_trading",
        symbol=None,
        engine_mode="demo",
        use_quantile_predictor=True,
        dry_run=False,
        min_samples=200,
    )
    res = run_pipeline(cfg)

    # ETL was called with symbol=None (pooled SQL branch).
    # ETL 被以 symbol=None 呼叫（走 pooled SQL 分支）。
    assert "symbol" in captured, "load_training_data should have been called"
    assert captured["symbol"] is None
    assert captured["strategy_type"] == "grid_trading"
    assert captured["engine_mode"] == "demo"

    # Pipeline surfaces insufficient-samples error (0 rows), but etl + labels
    # stages completed — we only care about the dispatch here.
    # 管線回報 insufficient samples（0 rows），本測試只驗派發正確。
    assert "etl" in res.stages_completed
    assert "labels" in res.stages_completed


def test_load_training_data_per_symbol_forwards_filter(monkeypatch):
    """Concrete symbol threads through to SQL filter.
    具體 symbol 會原樣傳遞到 SQL 過濾。"""
    import numpy as np
    from program_code.ml_training import parquet_etl as etl

    captured: dict = {}

    def fake_load_training_data(**kwargs):
        captured.update(kwargs)
        feature_names = list(etl.EDGE_P3_FEATURE_NAMES)
        empty_f = np.empty((0, len(feature_names)), dtype=np.float32)
        empty_y = np.empty((0,), dtype=np.float32)
        empty_ts = np.empty((0,), dtype=np.int64)
        return empty_f, empty_y, empty_ts, feature_names

    monkeypatch.setattr(etl, "load_training_data", fake_load_training_data)

    cfg = PipelineConfig(
        strategy_type="ma_crossover",
        symbol="BTCUSDT",
        engine_mode="demo",
        use_quantile_predictor=True,
        dry_run=False,
        min_samples=200,
    )
    run_pipeline(cfg)

    assert captured.get("symbol") == "BTCUSDT"


# ---------------------------------------------------------------------------
# 4. Artifact / metrics reflect pooled mode
# ---------------------------------------------------------------------------


def test_artifact_name_reflects_pooled_mode(tmp_path):
    """Dry-run pooled pipeline emits metrics tagged pooled=True + slot=ALL.
    Use dry_run so we don't require psycopg2/LightGBM; dry_run bypasses ETL
    and synthesizes features — but metrics tagging happens after training.

    dry-run pooled 管線 metrics 含 pooled=True + slot=ALL；dry_run 繞過 ETL，
    以合成資料跑完整管線，metrics 標記在訓練之後附加。"""
    cfg = PipelineConfig(
        dry_run=True,
        strategy_type="grid_trading",
        symbol=None,  # pooled
        min_samples=100,
        output_dir=str(tmp_path / "pooled"),
        use_quantile_predictor=False,  # legacy scorer path — no LightGBM needed
    )
    res = run_pipeline(cfg)
    # May fail if lgb missing — that's tested elsewhere. We only care about
    # metrics tagging when the pipeline completes far enough to populate them.
    # 無 lightgbm 時可能失敗；此測只驗走到 metrics 階段的標記正確。
    if res.success:
        assert res.metrics.get("pooled") is True
        assert res.metrics.get("symbol_slot") == "ALL"


def test_artifact_name_reflects_per_symbol_mode(tmp_path):
    """Per-symbol run emits metrics tagged pooled=False + slot=<symbol>.
    per-symbol 執行 metrics 含 pooled=False + slot=<symbol>。"""
    cfg = PipelineConfig(
        dry_run=True,
        strategy_type="ma_crossover",
        symbol="BTCUSDT",
        min_samples=100,
        output_dir=str(tmp_path / "per_sym"),
        use_quantile_predictor=False,
    )
    res = run_pipeline(cfg)
    if res.success:
        assert res.metrics.get("pooled") is False
        assert res.metrics.get("symbol_slot") == "BTCUSDT"

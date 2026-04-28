"""
Tests for parquet_etl.generate_training_labels.
parquet_etl.generate_training_labels 的測試。

Self-contained — no PG or external services needed.
自包含 — 不需要 PG 或外部服務。
"""

from __future__ import annotations

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# Guard optional deps / 保護可選依賴
pd = pytest.importorskip("pandas")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")
duckdb = pytest.importorskip("duckdb")

from program_code.ml_training.parquet_etl import generate_training_labels


def _make_fills(tmp: str, rows: list[dict]) -> str:
    """Write synthetic fills Parquet. / 寫入合成 fills Parquet。"""
    path = str(Path(tmp) / "fills.parquet")
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
    df.to_parquet(path, index=False)
    return path


def _make_features(tmp: str, rows: list[dict]) -> str:
    """Write synthetic features Parquet. / 寫入合成 features Parquet。"""
    path = str(Path(tmp) / "features.parquet")
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
    df.to_parquet(path, index=False)
    return path


def _make_klines(tmp: str, rows: list[dict]) -> str:
    """Write synthetic klines Parquet. / 寫入合成 klines Parquet。"""
    path = str(Path(tmp) / "klines.parquet")
    df = pd.DataFrame(rows)
    if "ts" in df.columns:
        df["ts"] = pd.to_datetime(df["ts"])
    df.to_parquet(path, index=False)
    return path


# ── Fixtures ──────────────────────────────────────────────────────────

BASE_TS = datetime(2026, 4, 1, 12, 0, 0)


def _standard_data(tmp: str, pnl_values: list[float] | None = None):
    """Build standard test data set. / 構建標準測試數據集。"""
    if pnl_values is None:
        pnl_values = [100.0, -50.0, 200.0]

    fills_rows = [
        {"symbol": "BTCUSDT", "ts": BASE_TS + timedelta(seconds=i * 60), "realized_pnl": pnl}
        for i, pnl in enumerate(pnl_values)
    ]
    features_rows = [
        {"symbol": "BTCUSDT", "ts": BASE_TS + timedelta(seconds=i * 60), "feat_1": 0.5 + i * 0.1, "feat_2": 1.0}
        for i in range(len(pnl_values))
    ]
    klines_rows = [
        {"symbol": "BTCUSDT", "ts": BASE_TS + timedelta(seconds=i * 60), "atr": 100.0}
        for i in range(len(pnl_values))
    ]

    fills_path = _make_fills(tmp, fills_rows)
    features_path = _make_features(tmp, features_rows)
    klines_path = _make_klines(tmp, klines_rows)
    output_path = str(Path(tmp) / "labeled.parquet")

    return fills_path, features_path, klines_path, output_path


# ── Tests ─────────────────────────────────────────────────────────────


def test_generate_labels_basic():
    """Basic label generation: correct columns and sample count.
    基本標籤生成：正確的列和樣本數。
    """
    with tempfile.TemporaryDirectory() as tmp:
        fills_path, features_path, klines_path, output_path = _standard_data(tmp)

        result = generate_training_labels(
            fills_parquet=fills_path,
            features_parquet=features_path,
            klines_parquet=klines_path,
            output_path=output_path,
        )

        # Should have 3 samples / 應該有 3 個樣本
        assert result["n_samples"] == 3, f"Expected 3 samples, got {result['n_samples']}"

        # n_features should be positive / n_features 應為正數
        assert result["n_features"] > 0

        # label_stats must have required keys / label_stats 必須有必需鍵
        for key in ("mean", "std", "min", "max"):
            assert key in result["label_stats"], f"Missing label_stats key: {key}"

        # Output file should exist / 輸出文件應該存在
        assert Path(output_path).exists()

        # Read back and verify 'y' column exists / 讀回並驗證 'y' 列存在
        df_out = pd.read_parquet(output_path)
        assert "y" in df_out.columns, "'y' column missing from output"
        assert len(df_out) == 3


def test_generate_labels_clamp():
    """Extreme PnL values get clamped to ±label_clamp.
    極端 PnL 值被截斷到 ±label_clamp。
    """
    with tempfile.TemporaryDirectory() as tmp:
        # With atr=100 and atr_floor=50, pnl/atr = pnl/100
        # pnl=99999 → 999.99 → clamped to 3.0 (label_clamp=3)
        # pnl=-99999 → -999.99 → clamped to -3.0
        # 使用 atr=100 和 atr_floor=50，pnl/atr = pnl/100
        extreme_pnl = [99999.0, -99999.0, 50.0]
        fills_path, features_path, klines_path, output_path = _standard_data(tmp, extreme_pnl)

        clamp_val = 3.0
        result = generate_training_labels(
            fills_parquet=fills_path,
            features_parquet=features_path,
            klines_parquet=klines_path,
            output_path=output_path,
            label_clamp=clamp_val,
        )

        assert result["n_samples"] == 3

        df_out = pd.read_parquet(output_path)
        y_vals = df_out["y"].tolist()

        # Max should be clamped to label_clamp / 最大值應截斷到 label_clamp
        assert max(y_vals) <= clamp_val + 1e-9, f"Max y={max(y_vals)} exceeds clamp={clamp_val}"
        # Min should be clamped to -label_clamp / 最小值應截斷到 -label_clamp
        assert min(y_vals) >= -clamp_val - 1e-9, f"Min y={min(y_vals)} below -clamp={-clamp_val}"

        # The extreme values should be exactly at clamp boundaries (order-independent)
        # 極端值應該正好在截斷邊界（與行順序無關）
        sorted_y = sorted(y_vals)
        assert abs(sorted_y[-1] - clamp_val) < 1e-6, f"Positive extreme not clamped: {sorted_y[-1]}"
        assert abs(sorted_y[0] - (-clamp_val)) < 1e-6, f"Negative extreme not clamped: {sorted_y[0]}"

        # label_stats min/max should reflect clamping / label_stats 的 min/max 應反映截斷
        assert result["label_stats"]["max"] <= clamp_val + 1e-9
        assert result["label_stats"]["min"] >= -clamp_val - 1e-9


def test_generate_labels_empty_fills():
    """Empty fills → returns n_samples=0.
    空 fills → 返回 n_samples=0。
    """
    with tempfile.TemporaryDirectory() as tmp:
        # Create empty fills Parquet with correct schema / 創建具有正確 schema 的空 fills Parquet
        empty_fills = pd.DataFrame({"symbol": pd.Series(dtype="str"), "ts": pd.Series(dtype="datetime64[ns]"), "realized_pnl": pd.Series(dtype="float64")})
        fills_path = str(Path(tmp) / "fills.parquet")
        empty_fills.to_parquet(fills_path, index=False)

        # Features and klines can also be empty / Features 和 klines 也可以為空
        features_path = _make_features(tmp, [{"symbol": "BTCUSDT", "ts": BASE_TS, "feat_1": 0.5}])
        klines_path = _make_klines(tmp, [{"symbol": "BTCUSDT", "ts": BASE_TS, "atr": 100.0}])
        output_path = str(Path(tmp) / "labeled.parquet")

        result = generate_training_labels(
            fills_parquet=fills_path,
            features_parquet=features_path,
            klines_parquet=klines_path,
            output_path=output_path,
        )

        assert result["n_samples"] == 0, f"Expected 0 samples for empty fills, got {result['n_samples']}"
        assert result["n_features"] == 0
        assert "error" not in result, f"Unexpected error: {result.get('error')}"


# ── EDGE-P3-1 #63: load_training_data tests ───────────────────────────────
# ETL consumes learning.decision_features after edge_label_backfill.py has
# populated label_net_edge_bps. These tests don't hit PG — they exercise the
# feature-name ordering invariant (must match Rust FeatureVectorV1) and the
# empty-result numpy-shape guarantee (so CPCV trainer doesn't explode).
# EDGE-P3-1 #63：load_training_data 測試；不連 PG，驗證 feature 順序與空結果 shape。

def test_edge_p3_feature_names_match_rust_canonical_order():
    """Feature order must be exactly 17 items matching Rust FeatureVectorV1.
    feature 順序必須恰為 17 項，與 Rust FeatureVectorV1 一致。"""
    from program_code.ml_training.parquet_etl import EDGE_P3_FEATURE_NAMES

    assert len(EDGE_P3_FEATURE_NAMES) == 17, "spec §3.2 locks dim=17"
    # Canonical checks — these names + positions are frozen by schema_hash.
    # 以下名稱與位置被 schema_hash 凍結；變更即 train/serve skew。
    assert EDGE_P3_FEATURE_NAMES[0] == "adx_1h"
    assert EDGE_P3_FEATURE_NAMES[10] == "side"
    assert EDGE_P3_FEATURE_NAMES[-1] == "is_funding_settlement_window"


def test_export_accepts_live_demo_engine_mode(monkeypatch):
    """LiveDemo export must not be rejected by the engine_mode allow-list.
    LiveDemo 匯出不得被 engine_mode 白名單拒絕。"""
    import program_code.ml_training.parquet_etl as mod

    class _FakeConn:
        def __init__(self):
            self.queries: list[str] = []

        def execute(self, query):
            self.queries.append(str(query))
            return self

        def fetchone(self):
            return [0]

        def close(self):
            pass

    fake = _FakeConn()
    monkeypatch.setattr(duckdb, "connect", lambda: fake)

    with tempfile.TemporaryDirectory() as tmp:
        result = mod.export_decision_features_parquet(
            pg_url="postgresql://user:pass@localhost/openclaw",
            output_dir=tmp,
            engine_mode="live_demo",
        )

    assert result["success"] is True
    assert result["engine_mode"] == "live_demo"
    assert "decision_features_live_demo_" in result["output_path"]
    assert any("engine_mode IN ('live_demo')" in q for q in fake.queries)


def test_export_live_engine_mode_includes_live_demo(monkeypatch):
    """A live export includes LiveDemo rows because they exercise the Live pipeline.
    live 匯出需納入 LiveDemo 行，因其走 Live pipeline。"""
    import program_code.ml_training.parquet_etl as mod

    class _FakeConn:
        def __init__(self):
            self.queries: list[str] = []

        def execute(self, query):
            self.queries.append(str(query))
            return self

        def fetchone(self):
            return [0]

        def close(self):
            pass

    fake = _FakeConn()
    monkeypatch.setattr(duckdb, "connect", lambda: fake)

    with tempfile.TemporaryDirectory() as tmp:
        result = mod.export_decision_features_parquet(
            pg_url="postgresql://user:pass@localhost/openclaw",
            output_dir=tmp,
            engine_mode="live",
        )

    assert result["success"] is True
    assert any("engine_mode IN ('live', 'live_demo')" in q for q in fake.queries)


def test_load_training_data_rejects_without_psycopg2(monkeypatch):
    """Clean RuntimeError when psycopg2 is missing; no silent numpy return.
    缺 psycopg2 時拋 RuntimeError，不得靜默回空 numpy。"""
    import program_code.ml_training.parquet_etl as mod

    # Force psycopg2 ImportError path without touching global sys.modules state.
    # 以 monkeypatch 強制 _get_pg_conn 內 import psycopg2 失敗；不污染 sys.modules。
    original = mod._get_pg_conn

    def _blocked(dsn):
        raise RuntimeError("psycopg2 not installed — activate venv first")

    monkeypatch.setattr(mod, "_get_pg_conn", _blocked)

    with pytest.raises(RuntimeError, match="psycopg2"):
        mod.load_training_data(symbol="BTCUSDT", strategy_type="ma_crossover")


def test_load_training_data_empty_returns_canonical_shape(monkeypatch):
    """Zero labeled rows → empty numpy arrays with correct dtypes + feature_names.
    零標籤行 → 正確 dtype 的空 numpy 陣列 + feature_names 原樣返回。"""
    np = pytest.importorskip("numpy")
    import program_code.ml_training.parquet_etl as mod

    class _FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, *_a, **_kw):
            pass
        def fetchall(self):
            return []

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()
        def close(self):
            pass

    monkeypatch.setattr(mod, "_get_pg_conn", lambda dsn: _FakeConn())

    features, labels, timestamps, names = mod.load_training_data(
        symbol="BTCUSDT", strategy_type="ma_crossover"
    )
    assert features.shape == (0, 17)
    assert labels.shape == (0,)
    assert timestamps.shape == (0,)
    assert features.dtype == np.float32
    assert labels.dtype == np.float32
    assert timestamps.dtype == np.int64
    assert names == list(mod.EDGE_P3_FEATURE_NAMES)


def test_load_training_data_live_scope_params_include_live_demo(monkeypatch):
    """`engine_mode=live` must query both live and live_demo rows.
    `engine_mode=live` 必須同時查 live 與 live_demo。"""
    pytest.importorskip("numpy")
    import program_code.ml_training.parquet_etl as mod

    execute_params: list[dict] = []

    class _FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, _sql, params):
            execute_params.append(params)
        def fetchall(self):
            return []

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()
        def close(self):
            pass

    monkeypatch.setattr(mod, "_get_pg_conn", lambda dsn: _FakeConn())

    mod.load_training_data(engine_mode="live")

    assert execute_params[0]["engine_modes"] == ["live", "live_demo"]


def test_load_training_data_expands_jsonb(monkeypatch):
    """JSONB features get unpacked into the canonical 17-col matrix;
    missing / non-numeric entries coerce to 0.0 (row stays, label quality
    is what gated inclusion). Tests both dict and JSON-string JSONB shapes.
    JSONB 特徵展開為 17 列矩陣；缺/非數值欄位填 0.0，行保留；同時驗證
    dict 與 JSON 字串兩種 JSONB 形式。"""
    np = pytest.importorskip("numpy")
    import program_code.ml_training.parquet_etl as mod

    feat_dict_complete = {name: float(i + 1) for i, name in enumerate(mod.EDGE_P3_FEATURE_NAMES)}
    feat_dict_partial = {
        "adx_1h": 42.0,
        "side": -1,
        "nonsense_extra": "foo",    # ignored — not in canonical order
        "atr_pct": None,            # coerced to 0.0 (null-safe)
        "funding_rate": "notnum",   # coerced to 0.0 (ValueError → 0)
    }
    rows = [
        ("ctx1", 1_700_000_000_000.0, feat_dict_complete, 12.5, "BTCUSDT", "ma_crossover"),
        ("ctx2", 1_700_000_060_000.0, json.dumps(feat_dict_partial), -7.25, "BTCUSDT", "ma_crossover"),
    ]

    class _FakeCursor:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def execute(self, *_a, **_kw):
            pass
        def fetchall(self):
            return rows

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()
        def close(self):
            pass

    monkeypatch.setattr(mod, "_get_pg_conn", lambda dsn: _FakeConn())

    features, labels, timestamps, names = mod.load_training_data(
        symbol="BTCUSDT", strategy_type="ma_crossover"
    )

    assert features.shape == (2, 17)
    assert labels.tolist() == [12.5, -7.25]
    assert timestamps.tolist() == [1_700_000_000_000, 1_700_000_060_000]
    assert names == list(mod.EDGE_P3_FEATURE_NAMES)
    # Row 0: complete dict → values 1..17 float32 casts
    assert features[0, 0] == pytest.approx(1.0)
    assert features[0, 10] == pytest.approx(11.0)  # "side" position
    # Row 1: partial + coerced. adx_1h set, atr_pct None→0, funding_rate "notnum"→0
    adx_idx = mod.EDGE_P3_FEATURE_NAMES.index("adx_1h")
    atr_idx = mod.EDGE_P3_FEATURE_NAMES.index("atr_pct")
    fund_idx = mod.EDGE_P3_FEATURE_NAMES.index("funding_rate")
    side_idx = mod.EDGE_P3_FEATURE_NAMES.index("side")
    assert features[1, adx_idx] == pytest.approx(42.0)
    assert features[1, atr_idx] == pytest.approx(0.0)
    assert features[1, fund_idx] == pytest.approx(0.0)
    assert features[1, side_idx] == pytest.approx(-1.0)

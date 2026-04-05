"""
Tests for parquet_etl.generate_training_labels.
parquet_etl.generate_training_labels 的測試。

Self-contained — no PG or external services needed.
自包含 — 不需要 PG 或外部服務。
"""

from __future__ import annotations

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

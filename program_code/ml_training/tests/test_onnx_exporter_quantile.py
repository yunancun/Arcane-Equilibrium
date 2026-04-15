"""Tests for onnx_exporter.export_quantile_trio_to_onnx.
onnx_exporter.export_quantile_trio_to_onnx 測試。

Heavy-dep tests (lgb + onnxmltools + onnxruntime) are gated via importorskip.
重依賴測試（lgb + onnxmltools + onnxruntime）由 importorskip 守衛。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from program_code.ml_training.onnx_exporter import export_quantile_trio_to_onnx


def test_export_rejects_invalid_engine_mode(tmp_path: Path):
    result = export_quantile_trio_to_onnx(
        models={"q10": object(), "q50": object(), "q90": object()},
        output_dir=str(tmp_path),
        engine_mode="spicy",  # invalid
        strategy_name="ma_crossover",
    )
    assert result["success"] is False
    assert "invalid engine_mode" in result["error"]


def test_export_rejects_missing_quantile(tmp_path: Path):
    result = export_quantile_trio_to_onnx(
        models={"q10": object(), "q50": object()},  # missing q90
        output_dir=str(tmp_path),
        engine_mode="demo",
        strategy_name="ma_crossover",
    )
    assert result["success"] is False
    assert "must contain exactly" in result["error"]


def test_export_end_to_end_produces_three_files_and_symlinks(tmp_path: Path):
    """Fit 3 tiny LGBM boosters, export trio, verify files + symlinks + precision.
    擬合 3 個微 LGBM booster，匯出 trio，驗檔案 + symlink + 精度。"""
    lgb = pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")
    pytest.importorskip("onnxruntime")

    rng = np.random.default_rng(0)
    n, nf = 300, 8
    X = rng.standard_normal((n, nf)).astype(np.float32)
    y = X[:, 0] + rng.standard_normal(n) * 0.1
    ds = lgb.Dataset(X, label=y)

    boosters = {}
    for qname, alpha in (("q10", 0.1), ("q50", 0.5), ("q90", 0.9)):
        boosters[qname] = lgb.train(
            {"objective": "quantile", "alpha": alpha, "verbose": -1,
             "num_leaves": 7, "deterministic": True},
            ds, num_boost_round=20,
        )

    validate_samples = rng.standard_normal((100, nf)).astype(np.float32)
    result = export_quantile_trio_to_onnx(
        models=boosters,
        output_dir=str(tmp_path),
        engine_mode="demo",
        strategy_name="ma_crossover",
        n_features=nf,
        schema_version="v1",
        train_date="2026-04-15",
        validate_samples=validate_samples,
    )

    assert result["success"] is True, result.get("error") or result.get("failed_quantiles")
    assert set(result["artifacts"].keys()) == {"q10", "q50", "q90"}

    for qname in ("q10", "q50", "q90"):
        entry = result["artifacts"][qname]
        out_path = Path(entry["path"])
        link_path = Path(entry["symlink"])
        assert out_path.exists()
        assert link_path.is_symlink()
        # Symlink should point to the dated filename (relative).
        # symlink 應指向帶日期的檔名（相對）。
        assert link_path.readlink().name == out_path.name
        # Precision gate: expect < 1e-3 on trivial synthetic.
        # 合成資料精度應 < 1e-3。
        assert entry.get("precision_passed") is True, entry


def test_export_writes_metadata_props_roundtrip(tmp_path: Path):
    """metadata_props round-trip: write trio, parse back with onnx.load, assert
    every EDGE-P3-1 frozen key is present + matches input.

    This is the train/serve contract — Rust tract loader rejects artifacts
    whose schema_hash disagrees with FEATURE_NAMES_V1 compile-time hash.
    Without this test, the Rust side would rely on hash-in-filename, which is
    brittle. metadata_props travels with the bytes.

    metadata_props 往返：寫入 trio 後以 onnx.load 讀回，斷言每個 EDGE-P3-1 凍結 key
    齊全且值一致。此為 train/serve 契約；缺此測試 Rust tract 只能靠檔名對 hash，脆弱。
    """
    lgb = pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")
    onnx = pytest.importorskip("onnx")

    rng = np.random.default_rng(2)
    n, nf = 150, 5
    X = rng.standard_normal((n, nf)).astype(np.float32)
    y = X[:, 0] + rng.standard_normal(n) * 0.1
    ds = lgb.Dataset(X, label=y)
    booster = lgb.train(
        {"objective": "quantile", "alpha": 0.5, "verbose": -1, "num_leaves": 5},
        ds, num_boost_round=10,
    )
    models = {"q10": booster, "q50": booster, "q90": booster}

    r = export_quantile_trio_to_onnx(
        models=models, output_dir=str(tmp_path),
        engine_mode="demo", strategy_name="ma_crossover",
        n_features=nf, schema_version="v1", train_date="2026-04-15",
        feature_schema_hash="sha256:frozen_hash_abc",
        feature_definition_hash="sha256:frozen_hash_abc",
    )
    assert r["success"] is True

    for qname in ("q10", "q50", "q90"):
        entry = r["artifacts"][qname]
        loaded = onnx.load(entry["path"])
        props = {p.key: p.value for p in loaded.metadata_props}
        # Frozen keys (Rust side reads these)
        assert props["edge_p3_schema_version"] == "v1"
        assert props["edge_p3_feature_schema_hash"] == "sha256:frozen_hash_abc"
        assert props["edge_p3_feature_definition_hash"] == "sha256:frozen_hash_abc"
        assert props["edge_p3_engine_mode"] == "demo"
        assert props["edge_p3_strategy_name"] == "ma_crossover"
        assert props["edge_p3_quantile"] == qname
        assert props["edge_p3_train_date"] == "2026-04-15"
        assert props["edge_p3_n_features"] == str(nf)
        # model_id is per-quantile and surfaces in result too
        expected_id = f"edge_predictor_demo_ma_crossover_{qname}_v1_2026-04-15"
        assert props["edge_p3_model_id"] == expected_id
        assert entry["model_id"] == expected_id


def test_export_metadata_definition_hash_defaults_to_schema_hash(tmp_path: Path):
    """If caller passes schema_hash but no definition_hash, exporter aliases
    the two (spec §3.3 Stage 0: definition hash = schema hash until formulas drift).

    若 caller 只傳 schema_hash，exporter 自動同值寫入 definition_hash。
    """
    lgb = pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")
    onnx = pytest.importorskip("onnx")

    rng = np.random.default_rng(3)
    n, nf = 80, 4
    X = rng.standard_normal((n, nf)).astype(np.float32)
    y = X[:, 0] + rng.standard_normal(n) * 0.1
    ds = lgb.Dataset(X, label=y)
    booster = lgb.train(
        {"objective": "quantile", "alpha": 0.5, "verbose": -1, "num_leaves": 5},
        ds, num_boost_round=5,
    )
    models = {"q10": booster, "q50": booster, "q90": booster}

    r = export_quantile_trio_to_onnx(
        models=models, output_dir=str(tmp_path),
        engine_mode="paper", strategy_name="bb_breakout",
        n_features=nf, schema_version="v1", train_date="2026-04-15",
        feature_schema_hash="sha256:schema_only",
        # feature_definition_hash NOT passed — should alias schema hash
    )
    for qname in ("q10", "q50", "q90"):
        loaded = onnx.load(r["artifacts"][qname]["path"])
        props = {p.key: p.value for p in loaded.metadata_props}
        assert props["edge_p3_feature_definition_hash"] == "sha256:schema_only"


def test_export_metadata_stamp_is_idempotent_across_reexport(tmp_path: Path):
    """Re-exporting same trio doesn't double-write owned metadata keys.

    Without the clear-before-append guard, repeated export calls would grow
    the metadata_props list with duplicate keys (ONNX spec allows but Rust
    loader would read the first and miss later updates).
    確保重複匯出不會 append 重複 key。
    """
    lgb = pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")
    onnx = pytest.importorskip("onnx")

    rng = np.random.default_rng(4)
    n, nf = 60, 4
    X = rng.standard_normal((n, nf)).astype(np.float32)
    y = X[:, 0] + rng.standard_normal(n) * 0.1
    ds = lgb.Dataset(X, label=y)
    booster = lgb.train(
        {"objective": "quantile", "alpha": 0.5, "verbose": -1, "num_leaves": 4},
        ds, num_boost_round=3,
    )
    models = {"q10": booster, "q50": booster, "q90": booster}

    r1 = export_quantile_trio_to_onnx(
        models=models, output_dir=str(tmp_path),
        engine_mode="demo", strategy_name="grid_trading",
        n_features=nf, schema_version="v1", train_date="2026-04-15",
        feature_schema_hash="sha256:first",
    )
    r2 = export_quantile_trio_to_onnx(
        models=models, output_dir=str(tmp_path),
        engine_mode="demo", strategy_name="grid_trading",
        n_features=nf, schema_version="v1", train_date="2026-04-16",
        feature_schema_hash="sha256:second",
    )
    assert r1["success"] and r2["success"]
    loaded = onnx.load(r2["artifacts"]["q10"]["path"])
    keys = [p.key for p in loaded.metadata_props]
    # Each EDGE-P3-1 key should appear exactly once.
    # 每個 EDGE-P3-1 key 只出現一次。
    owned = [k for k in keys if k.startswith("edge_p3_")]
    assert len(owned) == len(set(owned)), f"duplicate metadata keys: {owned}"
    props = {p.key: p.value for p in loaded.metadata_props}
    assert props["edge_p3_feature_schema_hash"] == "sha256:second"
    assert props["edge_p3_train_date"] == "2026-04-16"


def test_export_symlink_swap_is_idempotent(tmp_path: Path):
    """Two back-to-back exports should leave symlink pointing to the latest file.
    連續兩次匯出後 symlink 指向最新檔。"""
    lgb = pytest.importorskip("lightgbm")
    pytest.importorskip("onnxmltools")

    rng = np.random.default_rng(1)
    n, nf = 100, 4
    X = rng.standard_normal((n, nf)).astype(np.float32)
    y = X[:, 0] + rng.standard_normal(n) * 0.1
    ds = lgb.Dataset(X, label=y)
    booster = lgb.train(
        {"objective": "quantile", "alpha": 0.5, "verbose": -1, "num_leaves": 5},
        ds, num_boost_round=10,
    )
    models = {"q10": booster, "q50": booster, "q90": booster}

    r1 = export_quantile_trio_to_onnx(
        models=models, output_dir=str(tmp_path),
        engine_mode="demo", strategy_name="ma_crossover",
        n_features=nf, train_date="2026-04-15",
    )
    r2 = export_quantile_trio_to_onnx(
        models=models, output_dir=str(tmp_path),
        engine_mode="demo", strategy_name="ma_crossover",
        n_features=nf, train_date="2026-04-16",
    )
    assert r1["success"] and r2["success"]
    # For each quantile, final symlink target should be the 2026-04-16 file.
    # 各分位 symlink 最終目標為 2026-04-16 檔。
    for qname in ("q10", "q50", "q90"):
        link = Path(r2["artifacts"][qname]["symlink"])
        assert "2026-04-16" in link.readlink().name

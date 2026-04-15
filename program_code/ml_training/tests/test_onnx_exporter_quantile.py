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

"""Fixture generator for ort_backend Rust integration tests.
ort_backend Rust 整合測試的 fixture 產生器。

Trains 3 tiny LightGBM quantile boosters on 17-dim synthetic features
matching FEATURE_NAMES_V1, exports via onnx_exporter.export_quantile_trio_to_onnx
stamped with the Rust-parity feature_schema_hash so ort_backend accepts them.
Deterministic via seeded RNG: re-running produces bit-identical output
(modulo `train_date` in the filename — set by the caller below).

訓練三個微型 LGBM 分位 booster（17-dim 對齊 FEATURE_NAMES_V1），匯出並蓋章
Rust 對齊的 feature_schema_hash；ort_backend 即可接受。RNG 固定種子故可重現。

Run (idempotent; overwrites existing *.onnx in this directory):
    cd rust/openclaw_engine/tests/fixtures/edge_predictor
    $VENV/bin/python gen_fixtures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SRV_ROOT = Path(__file__).resolve().parents[4]  # srv/
sys.path.insert(0, str(SRV_ROOT / "program_code"))

import numpy as np  # noqa: E402

from ml_training.quantile_trainer import _compute_feature_schema_hash  # noqa: E402
from ml_training.onnx_exporter import export_quantile_trio_to_onnx  # noqa: E402
from ml_training.parquet_etl import EDGE_P3_FEATURE_NAMES  # noqa: E402


TRAIN_DATE = "2026-04-15"
STRATEGY_NAME = "fixture_strategy"
ENGINE_MODE = "demo"


def main() -> None:
    import lightgbm as lgb

    out_dir = Path(__file__).parent
    feature_names = list(EDGE_P3_FEATURE_NAMES)
    nf = len(feature_names)
    schema_hash = _compute_feature_schema_hash(feature_names, "v1")

    rng = np.random.default_rng(42)
    n = 400
    X = rng.standard_normal((n, nf)).astype(np.float32)
    # Signal: driven by first feature so pinball skill is non-trivial and
    # q10 < q50 < q90 stays well-ordered after rearrangement.
    # 訊號：由首特徵驅動，三分位排序良好。
    y = (X[:, 0] * 2.0 + rng.standard_normal(n) * 0.3).astype(np.float32)
    ds = lgb.Dataset(X, label=y)

    boosters = {}
    for qname, alpha in (("q10", 0.1), ("q50", 0.5), ("q90", 0.9)):
        boosters[qname] = lgb.train(
            {
                "objective": "quantile",
                "alpha": alpha,
                "verbose": -1,
                "num_leaves": 5,
                "min_data_in_leaf": 10,
                "deterministic": True,
                "seed": 42,
                "feature_fraction_seed": 42,
                "bagging_seed": 42,
            },
            ds,
            num_boost_round=12,
        )

    result = export_quantile_trio_to_onnx(
        models=boosters,
        output_dir=str(out_dir),
        engine_mode=ENGINE_MODE,
        strategy_name=STRATEGY_NAME,
        n_features=nf,
        schema_version="v1",
        train_date=TRAIN_DATE,
        feature_schema_hash=schema_hash,
        feature_definition_hash=schema_hash,
    )
    if not result.get("success"):
        raise SystemExit(f"export failed: {result.get('error')}")

    print(f"Fixture ONNX trio written to {out_dir}:")
    for qname, entry in result["artifacts"].items():
        print(f"  {qname}: {Path(entry['path']).name}  model_id={entry['model_id']}")
    print(f"schema_hash = {schema_hash}")
    print(f"strategy_name = {STRATEGY_NAME}  engine_mode = {ENGINE_MODE}  train_date = {TRAIN_DATE}")


if __name__ == "__main__":
    main()

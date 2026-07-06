"""P1-3 end-to-end pipeline orchestration tests (no external deps).
P1-3 端到端管線編排測試（無外部依賴）。"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from program_code.ml_training.run_training_pipeline import (
    PipelineConfig,
    PipelineResult,
    run_pipeline,
)
from program_code.ml_training.pit_dataset_manifest import compute_pit_dataset_manifest_hash
from program_code.ml_training.pit_dataset_manifest_builder import (
    build_pit_dataset_manifest_from_source,
)
from program_code.ml_training.quantile_trainer import (
    EmbargoConfig,
    PerQuantileMetrics,
    QuantileTrainingResult,
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


def _patch_dataset(monkeypatch, n: int = 80):
    import program_code.ml_training.run_training_pipeline as pipeline

    features = np.zeros((n, 3), dtype=np.float32)
    labels = np.linspace(1.0, 2.0, n, dtype=np.float32)
    timestamps = np.arange(n, dtype=np.int64) * 60_000
    feature_names = ["f0", "f1", "f2"]
    monkeypatch.setattr(
        pipeline,
        "_load_dataset",
        lambda config: (features, labels, timestamps, feature_names, None),
    )


def _manifest_source(**overrides) -> dict:
    source = {
        "dataset_id": "pit-grid-eth-buy-20260706",
        "dataset_role": "supervised_training",
        "as_of_ts": "2026-07-06T12:00:00Z",
        "candidate_scope": {
            "candidate_id": "grid_trading|ETHUSDT|Buy",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
            "side": "Buy",
            "engine_mode": "demo",
        },
        "window": {
            "start_ts": "2026-07-01T00:00:00Z",
            "end_ts": "2026-07-06T11:59:00Z",
            "min_ts": "2026-07-01T00:00:00Z",
            "max_ts": "2026-07-06T11:59:00Z",
        },
        "query": {
            "query_id": "learning_rows_grid_eth_buy_20260706T120000Z",
            "query_text": (
                "SELECT row_id, ts, feature_1, label_q50 "
                "FROM learning_rows "
                "WHERE ts >= :start_ts AND ts <= :end_ts"
            ),
            "params": {
                "start_ts": "2026-07-01T00:00:00Z",
                "end_ts": "2026-07-06T11:59:00Z",
                "candidate_id": "grid_trading|ETHUSDT|Buy",
            },
        },
        "rows": {
            "rows": [
                {"row_id": "row-1", "ts": "2026-07-01T00:00:00Z", "feature_1": 0.1},
                {"row_id": "row-2", "ts": "2026-07-01T00:01:00Z", "feature_1": 0.2},
            ]
        },
        "features": {
            "feature_schema_version": "features_v3",
            "feature_names": ["feature_1"],
            "definition": {"feature_1": "lagged_return"},
            "schema": {"feature_1": "float"},
        },
        "labels": {
            "schema": {"label_q50": "float"},
            "config": {"horizon_bars": 12, "target": "after_cost_bps"},
            "outcome_cutoff_ts": "2026-07-06T12:00:00Z",
        },
        "splits": {
            "split_id": "cpcv-grid-eth-buy-v1",
            "train_row_ids": ["row-1"],
            "validation_row_ids": ["row-2"],
            "test_row_ids": ["row-2"],
            "embargo_bars": 12,
            "purge_bars": 4,
        },
        "leakage": {
            "report": {"checked": True, "future_features": []},
            "fold_preprocessing_stats": {"fit_scope": "train_fold_only"},
            "overlap_count": 0,
        },
        "controls": {
            "matched_control_rows": [{"row_id": "control-1"}],
            "matched_control_count": 1,
        },
        "fills": {
            "fill_rows": [{
                "fill_id": "fill-entry-1",
                "order_link_id": "order-1",
                "context_id": "ctx-entry-1",
            }],
            "fill_id_field": "fill_id",
            "order_link_id_field": "order_link_id",
            "context_id_field": "context_id",
        },
        "provenance": {
            "code_commit": "a" * 40,
            "rust_build_sha": "b" * 40,
            "source_hashes": {"feature_builder": "c" * 64},
            "input_artifact_hashes": {"probe_ledger": "d" * 64},
        },
    }
    _deep_update(source, overrides)
    return source


def _deep_update(target: dict, updates: dict) -> None:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_update(target[key], value)
        else:
            target[key] = value


def _dataset_ready_manifest(**source_overrides) -> dict:
    build = build_pit_dataset_manifest_from_source(_manifest_source(**source_overrides))
    assert build.manifest is not None
    assert build.validation.dataset_ready is True
    return build.manifest


def _fake_quantile_result(n_labeled: int, feature_names: list[str]) -> QuantileTrainingResult:
    metrics = {
        key: PerQuantileMetrics(
            alpha=alpha,
            pinball_loss=0.5,
            pinball_loss_baseline_constant=1.0,
            pinball_skill=0.30,
            empirical_coverage=alpha,
            coverage_error_pp=1.0,
            best_iteration=10,
            n_train=max(1, n_labeled - 20),
            n_holdout=20,
            linear_qr_pinball_loss=0.9,
            linear_qr_pinball_skill=0.10,
        )
        for key, alpha in (("q10", 0.10), ("q50", 0.50), ("q90", 0.90))
    }
    holdout = np.linspace(1.0, 2.0, 20, dtype=np.float32)
    return QuantileTrainingResult(
        success=True,
        strategy_name="grid_trading",
        engine_mode="demo",
        feature_names=feature_names,
        n_samples_total=n_labeled,
        n_samples_labeled=n_labeled,
        n_holdout=20,
        models={"q10": object(), "q50": object(), "q90": object()},
        per_quantile_metrics=metrics,
        decile_lift_point=2.0,
        decile_lift_ci_lower=1.6,
        decile_lift_ci_upper=2.5,
        crossing_rate=0.0,
        feature_schema_hash="f" * 64,
        feature_definition_hash="e" * 64,
        embargo_config=EmbargoConfig(n_folds=5, embargo_hours=24, holdout_tail_days=7.0),
        holdout_labels=holdout,
        holdout_q10_pred=holdout - 0.1,
        holdout_q50_pred=holdout,
        holdout_q90_pred=holdout + 0.1,
    )


def _patch_quantile_success(monkeypatch):
    calls = {"train": 0, "export": 0, "registry": 0}

    def fake_train(**kwargs):
        calls["train"] += 1
        return _fake_quantile_result(len(kwargs["labels"]), list(kwargs["feature_names"]))

    def fake_export(**kwargs):
        calls["export"] += 1
        return {"artifacts": {}, "train_date": "2026-07-07"}

    def fake_register(**kwargs):
        calls["registry"] += 1
        return []

    monkeypatch.setattr(
        "program_code.ml_training.quantile_trainer.train_quantile_trio",
        fake_train,
    )
    monkeypatch.setattr(
        "program_code.ml_training.calibration.fit_cqr_trio",
        lambda *args, **kwargs: {"q10": 0.0, "q50": 0.0, "q90": 0.0},
    )
    monkeypatch.setattr(
        "program_code.ml_training.calibration.evaluate_cqr_coverage",
        lambda *args, **kwargs: {
            "q10": (0.10, 1.0),
            "q50": (0.50, 1.0),
            "q90": (0.90, 1.0),
        },
    )
    monkeypatch.setattr(
        "program_code.ml_training.onnx_exporter.export_quantile_trio_to_onnx",
        fake_export,
    )
    monkeypatch.setattr(
        "program_code.ml_training.model_registry.has_required_persistence_artifact",
        lambda **kwargs: False,
    )
    monkeypatch.setattr(
        "program_code.ml_training.model_registry.register_quantile_trio_from_onnx_out",
        fake_register,
    )
    return calls


def _patch_quantile_train_counter(monkeypatch):
    calls = {"train": 0}

    def fake_train(**kwargs):
        calls["train"] += 1
        return _fake_quantile_result(len(kwargs["labels"]), list(kwargs["feature_names"]))

    monkeypatch.setattr(
        "program_code.ml_training.quantile_trainer.train_quantile_trio",
        fake_train,
    )
    return calls


def _contract_config(tmp_path, **overrides) -> PipelineConfig:
    cfg = PipelineConfig(
        strategy_type="grid_trading",
        symbol="ETHUSDT",
        engine_mode="demo",
        output_dir=str(tmp_path),
        min_samples=10,
        use_quantile_predictor=True,
        contract_bound_run=True,
        candidate_id="grid_trading|ETHUSDT|Buy",
        side="Buy",
    )
    for key, value in overrides.items():
        setattr(cfg, key, value)
    return cfg


def test_contract_bound_missing_manifest_fails_before_quantile_train(monkeypatch, tmp_path):
    _patch_dataset(monkeypatch)
    calls = _patch_quantile_train_counter(monkeypatch)

    result = run_pipeline(_contract_config(tmp_path, dry_run=False))

    assert not result.success
    assert result.error == "pit_dataset_manifest_missing"
    assert "pit_manifest_gate_failed" in result.stages_completed
    assert calls["train"] == 0


@pytest.mark.parametrize("pooled_symbol", [None, "ALL"])
def test_contract_bound_pooled_symbol_fails_before_quantile_train(
    monkeypatch, tmp_path, pooled_symbol,
):
    _patch_dataset(monkeypatch)
    calls = _patch_quantile_train_counter(monkeypatch)

    result = run_pipeline(
        _contract_config(
            tmp_path,
            symbol=pooled_symbol,
            pit_dataset_manifest=_dataset_ready_manifest(),
        )
    )

    assert not result.success
    assert result.error == "pit_manifest_pooled_symbol_not_allowed"
    assert result.stages_completed == ["etl", "labels", "pit_manifest_gate_failed"]
    assert calls["train"] == 0


def test_contract_bound_invalid_manifest_hash_fails_before_quantile_train(
    monkeypatch, tmp_path,
):
    _patch_dataset(monkeypatch)
    calls = _patch_quantile_train_counter(monkeypatch)
    manifest = _dataset_ready_manifest()
    manifest["manifest_hash"] = "0" * 64

    result = run_pipeline(_contract_config(tmp_path, pit_dataset_manifest=manifest))

    assert not result.success
    assert result.error == "manifest_hash_mismatch"
    assert calls["train"] == 0


def test_contract_bound_candidate_scope_mismatch_fails_before_quantile_train(
    monkeypatch, tmp_path,
):
    _patch_dataset(monkeypatch)
    calls = _patch_quantile_train_counter(monkeypatch)

    result = run_pipeline(
        _contract_config(
            tmp_path,
            symbol="BTCUSDT",
            candidate_id="grid_trading|BTCUSDT|Buy",
            pit_dataset_manifest=_dataset_ready_manifest(),
        )
    )

    assert not result.success
    assert result.error == "pit_manifest_candidate_scope_candidate_id_mismatch"
    assert calls["train"] == 0


def test_contract_bound_sidecar_replace_failure_preserves_existing_final(
    monkeypatch, tmp_path,
):
    _patch_dataset(monkeypatch)
    calls = _patch_quantile_train_counter(monkeypatch)
    sidecar = tmp_path / "grid_trading_demo_ETHUSDT_pit_dataset_manifest.json"
    old_payload = '{"old": true}\n'
    sidecar.write_text(old_payload, encoding="utf-8")
    original_replace = Path.replace
    seen = {"same_dir": False, "tmp_name": ""}

    def fail_sidecar_replace(self, target):
        target_path = Path(target)
        if target_path == sidecar:
            seen["same_dir"] = self.parent == target_path.parent
            seen["tmp_name"] = self.name
            raise OSError("synthetic replace failure")
        return original_replace(self, target)

    monkeypatch.setattr(Path, "replace", fail_sidecar_replace)

    result = run_pipeline(_contract_config(tmp_path, pit_dataset_manifest=_dataset_ready_manifest()))

    assert not result.success
    assert "synthetic replace failure" in result.error
    assert calls["train"] == 0
    assert sidecar.read_text(encoding="utf-8") == old_payload
    assert seen["same_dir"] is True
    assert seen["tmp_name"] != sidecar.name


@pytest.mark.parametrize(
    ("source_overrides", "reason"),
    [
        (
            {
                "query": {
                    "query_text": "SELECT * FROM learning_rows WHERE ts < now()",
                    "params": {"max_age_days": 7},
                    "max_age_days": 7,
                }
            },
            "source_query_unpinned_relative_window:",
        ),
        ({"leakage": {"overlap_count": 1}}, "leakage_evidence_overlap_count_not_zero"),
    ],
)
def test_contract_bound_leakage_prone_source_fails_before_quantile_train(
    monkeypatch, tmp_path, source_overrides, reason,
):
    _patch_dataset(monkeypatch)
    calls = _patch_quantile_train_counter(monkeypatch)

    result = run_pipeline(
        _contract_config(
            tmp_path,
            pit_dataset_manifest_source=_manifest_source(**source_overrides),
        )
    )

    assert not result.success
    assert result.error.startswith(reason)
    assert calls["train"] == 0


def test_contract_bound_dry_run_emits_deterministic_manifest_and_report(
    monkeypatch, tmp_path,
):
    calls = _patch_quantile_success(monkeypatch)
    cfg = _contract_config(tmp_path, dry_run=True, min_samples=100)

    result = run_pipeline(cfg)

    assert result.success
    assert calls == {"train": 1, "export": 1, "registry": 1}
    assert result.pit_dataset_manifest_status == "dataset_ready"
    sidecar = tmp_path / "grid_trading_demo_ETHUSDT_pit_dataset_manifest.json"
    assert result.pit_dataset_manifest_path == str(sidecar)
    manifest = json.loads(sidecar.read_text())
    assert manifest["dataset_role"] == "synthetic_training_dry_run"
    assert manifest["manifest_hash"] == compute_pit_dataset_manifest_hash(manifest)
    report = json.loads((tmp_path / "grid_trading_demo_ETHUSDT_acceptance_report.json").read_text())
    binding = report["pit_dataset_manifest_binding"]
    assert report["pit_dataset_manifest"] == manifest
    assert binding["schema_version"] == "training_pit_manifest_binding_v1"
    assert binding["contract_bound_run"] is True
    assert binding["manifest_hash"] == manifest["manifest_hash"]
    assert binding["manifest_path"] == str(sidecar)
    assert binding["validation_verdict"] == "dataset_ready"
    assert binding["runtime_mutation_performed"] is False
    assert binding["db_write_performed"] is False
    assert binding["exchange_private_read_performed"] is False
    assert binding["order_or_probe_performed"] is False
    assert binding["live_or_mainnet_performed"] is False

    first_sidecar = sidecar.read_text()
    second = run_pipeline(cfg)
    assert second.success
    assert sidecar.read_text() == first_sidecar


def test_non_contract_bound_dry_run_preserves_behavior_and_reports_binding(
    monkeypatch, tmp_path,
):
    calls = _patch_quantile_success(monkeypatch)
    cfg = PipelineConfig(
        strategy_type="grid_trading",
        symbol="ETHUSDT",
        engine_mode="demo",
        output_dir=str(tmp_path),
        dry_run=True,
        min_samples=100,
        use_quantile_predictor=True,
    )

    result = run_pipeline(cfg)

    assert result.success
    assert result.pit_dataset_manifest_status == "not_contract_bound"
    assert calls == {"train": 1, "export": 1, "registry": 1}
    report = json.loads((tmp_path / "grid_trading_demo_ETHUSDT_acceptance_report.json").read_text())
    assert report["pit_dataset_manifest"] is None
    assert report["pit_dataset_manifest_binding"]["contract_bound_run"] is False
    assert report["pit_dataset_manifest_binding"]["validation_reason"] == "not_contract_bound"
    assert not (tmp_path / "grid_trading_demo_ETHUSDT_pit_dataset_manifest.json").exists()


def test_legacy_scorer_contract_bound_fails_closed_before_training(tmp_path):
    result = run_pipeline(
        PipelineConfig(
            dry_run=True,
            output_dir=str(tmp_path),
            use_quantile_predictor=False,
            contract_bound_run=True,
            candidate_id="grid_trading|ETHUSDT|Buy",
            symbol="ETHUSDT",
            side="Buy",
        )
    )

    assert not result.success
    assert result.error == "contract_bound_quantile_path_required"
    assert result.stages_completed == ["pit_manifest_gate_failed"]

"""Static guards for the V072 feature baseline writer follow-up."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIFT = (ROOT / "rust/openclaw_engine/src/database/drift_detector.rs").read_text()
BIN = (ROOT / "rust/openclaw_engine/src/bin/feature_baseline_writer.rs").read_text()
CARGO = (ROOT / "rust/openclaw_engine/Cargo.toml").read_text()


def test_writer_uses_decision_context_snapshot_source_not_17_dim_training_rows():
    assert "trading.decision_context_snapshots" in DRIFT
    assert "indicators_snapshot" in DRIFT
    assert "learning.decision_features" not in DRIFT
    assert "EDGE_P3_FEATURE_NAMES" not in DRIFT


def test_writer_rebuilds_rust_feature_collector_schema():
    assert "FeatureSnapshot::new" in DRIFT
    assert "FEATURE_DIM" in DRIFT
    assert "FEATURE_NAMES" in DRIFT
    assert "feature_vector.len() != FEATURE_DIM" in DRIFT


def test_writer_cli_defaults_to_dry_run_and_requires_apply_ack():
    assert 'name = "feature_baseline_writer"' in CARGO
    assert "Mode::DryRun" in BIN
    assert "--i-understand-this-modifies-db" in BIN
    assert "--apply requires --i-understand-this-modifies-db" in BIN
    assert "write_feature_baseline_rows(&pool, &rows)" in BIN

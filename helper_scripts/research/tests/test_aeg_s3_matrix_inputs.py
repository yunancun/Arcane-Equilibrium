"""AEG-S3 candidate-specific matrix input tests."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from aeg_candidate_metrics import REGIME_METRIC_COLUMNS
from aeg_regime_runner.artifact import LABEL_COLUMNS
from aeg_robustness_matrix import builder as matrix_builder
from aeg_s3_matrix_inputs import builder as builder_mod
from aeg_s3_matrix_inputs import harness as harness_mod


def _write_csv(path: Path, columns, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _candidate_metrics_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "candidate_metrics"
    run_dir.mkdir()
    rows = []
    for regime in ("bear", "chop"):
        rows.append({
            "run_id": "candidate_metrics",
            "candidate_id": "funding_revive",
            "strategy_family": "funding_revive",
            "parameter_cell_id": "lb21_h24h_stress2_exit1_cost5",
            "source_report_type": "aeg_candidate_metrics_direct",
            "selected_variant": "stress_unwind_event_window",
            "regime": regime,
            "n_days": "80",
            "gross_bps": "40.0",
            "cost_bps": "5.0",
            "net_bps": "35.0",
            "net_to_cost_ratio": "7.0",
            "mean_daily_bps": "1.0",
            "annualized_net_sharpe": "1.2",
            "oos_sharpe": "0.8",
            "psr_0": "0.97",
            "dsr_k": "0.0",
            "pbo": "0.55",
            "k_trials": "18",
            "n_independent": "80",
            "sample_unit": "funding_revive_event_window",
            "recent_90d_net_bps": "20.0",
            "recent_180d_net_bps": "18.0",
            "freshness_bucket": "recent_90_180_measured",
            "metric_status": "PASS",
            "reject_reasons": "[]",
        })
    _write_csv(run_dir / "candidate_regime_metrics.csv", REGIME_METRIC_COLUMNS, rows)
    (run_dir / "candidate_metrics_summary.json").write_text(
        json.dumps({
            "run_id": "candidate_metrics",
            "candidate_id": "funding_revive",
            "strategy_family": "funding_revive",
            "parameter_cell_id": "lb21_h24h_stress2_exit1_cost5",
            "row_count": 2,
            "metric_status_counts": {"PASS": 2},
            "date_span": ["2025-08-17", "2026-05-30"],
        }),
        encoding="utf-8",
    )
    return run_dir


def _regime_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "regime"
    run_dir.mkdir()
    _write_csv(
        run_dir / "regime_labels.csv",
        LABEL_COLUMNS,
        [
            {
                "classifier_version": "aeg_regime_v0.1.0",
                "run_id": "regime",
                "signal_ts": "2026-05-01T00:00:00+00:00",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "main_regime": "bear",
                "market_anchor_regime": "bear",
                "high_vol_overlay": "false",
                "overlay_flags": "{}",
                "context_bars": "300",
                "insufficient_context": "false",
                "feature_rules_digest": "digest",
            },
            {
                "classifier_version": "aeg_regime_v0.1.0",
                "run_id": "regime",
                "signal_ts": "2026-05-02T00:00:00+00:00",
                "symbol": "ETHUSDT",
                "timeframe": "1d",
                "main_regime": "chop",
                "market_anchor_regime": "range",
                "high_vol_overlay": "false",
                "overlay_flags": "{}",
                "context_bars": "300",
                "insufficient_context": "false",
                "feature_rules_digest": "digest",
            },
        ],
    )
    (run_dir / "regime_summary.json").write_text(
        json.dumps({
            "run_id": "regime",
            "label_count": 2,
            "lineage_status": "PASS",
            "healthcheck": {"status": "PASS", "message": "ok"},
        }),
        encoding="utf-8",
    )
    return run_dir


def test_builder_creates_fail_closed_candidate_specific_inputs(tmp_path):
    candidate_metrics = builder_mod.load_candidate_metrics(_candidate_metrics_dir(tmp_path))
    rows, breadth_summary, execution_payload, summary = builder_mod.build_inputs(
        candidate_metrics,
        run_id="matrix_inputs",
    )

    assert rows[0]["candidate_id"] == "funding_revive"
    assert rows[0]["breadth_cohort"] == "candidate_metrics_only"
    assert rows[0]["excluded_from_promotion"] == "true"
    assert breadth_summary["candidate_id"] == "funding_revive"
    assert breadth_summary["survivorship_healthcheck"]["status"] == "FAIL"
    assert breadth_summary["survivorship_inherited_from_fnd2"] is False
    assert execution_payload["status"] == "FAIL"
    assert "missing_evidence_source_tier" in execution_payload["reject_reasons"]
    assert summary["breadth_policy"] == "fail_closed_candidate_metrics_only_no_breadth_claim"


def test_harness_outputs_matrix_consumable_fail_closed_artifacts(tmp_path):
    candidate_metrics_dir = _candidate_metrics_dir(tmp_path)
    result = harness_mod.build_and_write(argparse.Namespace(
        run_id="matrix_inputs",
        candidate_metrics_run_dir=str(candidate_metrics_dir),
        execution_run_id=None,
        artifact_root=str(tmp_path / "out"),
        session_id=None,
        created_by_role="PM",
    ))
    breadth = matrix_builder.load_breadth_artifact(Path(result["breadth_written"]["run_dir"]))
    execution = matrix_builder.load_execution_realism(
        Path(result["execution_written"]["execution_realism_json"])
    )
    candidate_metrics = matrix_builder.load_candidate_metrics_artifact(candidate_metrics_dir)
    rows, summary = matrix_builder.build_matrix(
        run_id="matrix",
        regime_artifact=matrix_builder.load_regime_artifact(_regime_dir(tmp_path)),
        breadth_artifact=breadth,
        execution_realism=execution,
        candidate_metrics=candidate_metrics,
        strategy_family="funding_revive",
        parameter_cell_id="lb21_h24h_stress2_exit1_cost5",
    )

    assert summary["candidate_id"] == "funding_revive"
    assert summary["coverage_gate_status"] == "FAIL"
    assert summary["survivorship_mode"] == "current_survivor_or_unverified"
    assert summary["execution_realism_mode"].startswith("unverified_")
    assert summary["final_label_counts"] == {"insufficient evidence": 3}
    chop = next(row for row in rows if row["regime"] == "chop")
    reasons = json.loads(chop["reject_reasons"])
    assert "coverage_gate_not_pass" in reasons
    assert "survivorship_not_pit_verified" in reasons
    assert "missing_evidence_source_tier" in reasons
    assert "dsr_k_below_0_95" in reasons
    assert "pbo_at_or_above_0_5" in reasons


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_matrix_inputs"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "control_api_v1",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
        "execution_authority",
        "wss://stream.bybit.com",
        "urlopen",
    )
    for needle in forbidden:
        assert needle not in code

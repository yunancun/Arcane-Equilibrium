"""AEG-S2 robustness matrix builder 測試。

MODULE_NOTE:
  測試重點不是證明某候選有 alpha，而是證明 matrix builder 會把缺失證據
  fail-closed 寫進 artifact，避免 aggregate breadth 結果被誤用成 promotion verdict。
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from aeg_candidate_metrics import REGIME_METRIC_COLUMNS
from aeg_breadth_ladder.ladder import LADDER_COLUMNS
from aeg_regime_runner.artifact import LABEL_COLUMNS
from aeg_robustness_matrix import MATRIX_COLUMNS
from aeg_robustness_matrix import artifact as artifact_mod
from aeg_robustness_matrix import builder as builder_mod


def _write_csv(path: Path, columns, rows):
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _regime_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "regime_run"
    run_dir.mkdir()
    _write_csv(
        run_dir / "regime_labels.csv",
        LABEL_COLUMNS,
        [
            {
                "classifier_version": "aeg_regime_v0.1.0",
                "run_id": "regime_run",
                "signal_ts": "2026-05-01T00:00:00+00:00",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "main_regime": "bull",
                "market_anchor_regime": "bull",
                "high_vol_overlay": "false",
                "overlay_flags": "{}",
                "context_bars": "300",
                "insufficient_context": "false",
                "feature_rules_digest": "digest",
            },
            {
                "classifier_version": "aeg_regime_v0.1.0",
                "run_id": "regime_run",
                "signal_ts": "2026-05-02T00:00:00+00:00",
                "symbol": "ETHUSDT",
                "timeframe": "1d",
                "main_regime": "chop",
                "market_anchor_regime": "bull",
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
            "run_id": "regime_run",
            "label_count": 2,
            "lineage_status": "PASS",
            "healthcheck": {"status": "PASS"},
            "fnd2_run_id": "fnd2_run",
            "fnd2_universe_id": "uid",
        }),
        encoding="utf-8",
    )
    return run_dir


def _breadth_dir(tmp_path: Path, *, survivorship_pass: bool = True) -> Path:
    run_dir = tmp_path / "breadth_run"
    run_dir.mkdir()
    _write_csv(
        run_dir / "breadth_ladder.csv",
        LADDER_COLUMNS,
        [
            {
                "run_id": "breadth_run",
                "ladder_id": "ladder",
                "candidate_id": "cand_x",
                "breadth_ladder_version": "aeg_breadth_v0.1.0",
                "asof_utc": "2026-06-03T00:00:00+00:00",
                "window_start_utc": "2024-06-03T00:00:00+00:00",
                "window_end_utc": "2026-06-03T00:00:00+00:00",
                "fnd2_universe_id": "uid",
                "fnd2_run_id": "fnd2_run",
                "breadth_cohort": "core25_pinned",
                "breadth_symbol_count": "25",
                "seen_delisted_count": "0",
                "tier_quality": "ok",
                "tier_rank_pit_mode": "n/a",
                "gross_bps": "21.0",
                "cost_bps": "11.0",
                "net_bps": "10.0",
                "net_to_cost_ratio": "0.91",
                "n_independent": "24",
                "sample_unit": "non_overlapping_holding_window",
                "k_trials": "8",
                "pit_mask_source": "fnd2_alive_from_alive_to",
                "leak_free_signal": "true",
                "monotonicity_rank": "1",
                "excluded_from_promotion": "false",
            },
        ],
    )
    (run_dir / "breadth_ladder_summary.json").write_text(
        json.dumps({
            "run_id": "breadth_run",
            "candidate_id": "cand_x",
            "fnd2_run_id": "fnd2_run",
            "fnd2_universe_id": "uid",
            "verdict_hint": "insufficient_n_independent",
            "survivorship_inherited_from_fnd2": survivorship_pass,
            "delisted_proof_total": 255 if survivorship_pass else 0,
            "survivorship_healthcheck": {
                "status": "PASS" if survivorship_pass else "FAIL",
                "message": "synthetic",
            },
        }),
        encoding="utf-8",
    )
    return run_dir


def _candidate_metrics_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "candidate_metrics_run"
    run_dir.mkdir()
    _write_csv(
        run_dir / "candidate_regime_metrics.csv",
        REGIME_METRIC_COLUMNS,
        [
            {
                "run_id": "candidate_metrics_run",
                "candidate_id": "cand_x",
                "strategy_family": "multiday_trend",
                "parameter_cell_id": "k40",
                "source_report_type": "multiday_trend_diagnostic",
                "selected_variant": "tsmom_k40__daily",
                "regime": "bull",
                "n_days": "120",
                "net_bps": "3.5",
                "mean_daily_bps": "0.4",
                "annualized_net_sharpe": "0.8",
                "recent_90d_net_bps": "1.1",
                "recent_180d_net_bps": "0.9",
                "freshness_bucket": "recent_90_180_measured",
                "metric_status": "PASS",
                "reject_reasons": "[]",
            },
            {
                "run_id": "candidate_metrics_run",
                "candidate_id": "cand_x",
                "strategy_family": "multiday_trend",
                "parameter_cell_id": "k40",
                "source_report_type": "multiday_trend_diagnostic",
                "selected_variant": "tsmom_k40__daily",
                "regime": "chop",
                "n_days": "80",
                "net_bps": "1.0",
                "mean_daily_bps": "0.1",
                "annualized_net_sharpe": "0.3",
                "recent_90d_net_bps": "0.2",
                "recent_180d_net_bps": "0.4",
                "freshness_bucket": "recent_90_180_measured",
                "metric_status": "PASS",
                "reject_reasons": "[]",
            },
        ],
    )
    (run_dir / "candidate_metrics_summary.json").write_text(
        json.dumps({
            "run_id": "candidate_metrics_run",
            "candidate_id": "cand_x",
            "strategy_family": "multiday_trend",
            "parameter_cell_id": "k40",
            "row_count": 2,
            "metric_status_counts": {"PASS": 2},
        }),
        encoding="utf-8",
    )
    return run_dir


def test_matrix_fail_closed_when_regime_slice_metrics_missing(tmp_path):
    regime = builder_mod.load_regime_artifact(_regime_dir(tmp_path))
    breadth = builder_mod.load_breadth_artifact(_breadth_dir(tmp_path))
    execution = builder_mod.load_execution_realism(None)

    rows, summary = builder_mod.build_matrix(
        run_id="matrix_run",
        regime_artifact=regime,
        breadth_artifact=breadth,
        execution_realism=execution,
        strategy_family="multiday_trend",
        parameter_cell_id="k30",
    )

    assert summary["row_count"] == 3  # all_regimes + bull + chop
    assert summary["coverage_gate_status"] == "PASS"
    assert summary["feature_lineage_status"] == "PASS"
    assert summary["survivorship_mode"] == "pit_fnd2_delisted_proof"
    assert summary["final_label_counts"] == {"insufficient evidence": 3}
    assert set(rows[0]) == set(MATRIX_COLUMNS)

    aggregate = next(row for row in rows if row["regime"] == "all_regimes")
    agg_reasons = json.loads(aggregate["reject_reasons"])
    assert aggregate["net_bps"] == "10.0"
    assert "aggregate_not_regime_slice" in agg_reasons
    assert "n_independent_below_30" in agg_reasons
    assert "missing_execution_realism" in agg_reasons

    chop = next(row for row in rows if row["regime"] == "chop")
    chop_reasons = json.loads(chop["reject_reasons"])
    assert chop["net_bps"] is None
    assert "missing_regime_slice_metrics" in chop_reasons


def test_matrix_consumes_candidate_metrics_without_unit_substitution(tmp_path):
    regime = builder_mod.load_regime_artifact(_regime_dir(tmp_path))
    breadth = builder_mod.load_breadth_artifact(_breadth_dir(tmp_path))
    candidate_metrics = builder_mod.load_candidate_metrics_artifact(_candidate_metrics_dir(tmp_path))
    rows, summary = builder_mod.build_matrix(
        run_id="matrix_run",
        regime_artifact=regime,
        breadth_artifact=breadth,
        candidate_metrics=candidate_metrics,
        execution_realism={
            "status": "PASS",
            "execution_realism_mode": "calibrated_live_demo_fills_maker",
        },
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )

    assert summary["candidate_metrics_status_counts"] == {"PASS": 2}
    assert summary["upstream"]["candidate_metrics_run_id"] == "candidate_metrics_run"
    chop = next(row for row in rows if row["regime"] == "chop")
    reasons = json.loads(chop["reject_reasons"])
    assert chop["net_bps"] == "1.0"
    assert chop["is_sharpe"] == "0.3"
    assert chop["recent_90d_net_bps"] == "0.2"
    assert chop["recent_180d_net_bps"] == "0.4"
    assert chop["freshness_bucket"] == "recent_90_180_measured"
    assert "missing_regime_slice_metrics" not in reasons
    assert "missing_recent_90d_net_bps" not in reasons
    assert "missing_recent_180d_net_bps" not in reasons
    assert "missing_net_to_cost_ratio" in reasons
    assert "missing_n_independent" in reasons
    assert chop["final_label"] == "insufficient evidence"


def test_matrix_marks_unverified_survivorship_as_reject_reason(tmp_path):
    regime = builder_mod.load_regime_artifact(_regime_dir(tmp_path))
    breadth = builder_mod.load_breadth_artifact(_breadth_dir(tmp_path, survivorship_pass=False))
    rows, summary = builder_mod.build_matrix(
        run_id="matrix_run",
        regime_artifact=regime,
        breadth_artifact=breadth,
        execution_realism=builder_mod.load_execution_realism(None),
        strategy_family="x",
        parameter_cell_id="y",
    )

    assert summary["survivorship_mode"] == "current_survivor_or_unverified"
    assert all("survivorship_not_pit_verified" in json.loads(r["reject_reasons"]) for r in rows)


def test_artifact_write_all_creates_index_and_manifest(tmp_path):
    regime = builder_mod.load_regime_artifact(_regime_dir(tmp_path))
    breadth = builder_mod.load_breadth_artifact(_breadth_dir(tmp_path))
    rows, summary = builder_mod.build_matrix(
        run_id="matrix_run",
        regime_artifact=regime,
        breadth_artifact=breadth,
        execution_realism=builder_mod.load_execution_realism(None),
        strategy_family="x",
        parameter_cell_id="y",
    )
    written = artifact_mod.write_all(
        rows,
        summary,
        run_id="matrix_run",
        repo_root=Path("."),
        runtime_host="test",
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    assert (run_dir / "verdict_matrix.csv").exists()
    assert (run_dir / "verdict_matrix_summary.json").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert manifest["verdict_gate_version"] == "aeg_verdict_gate_v0.1.0"
    assert any(entry["name"] == "verdict_matrix.csv" for entry in index["artifacts"])


def test_robustness_matrix_has_no_runtime_or_db_write_route_static():
    pkg = Path(__file__).resolve().parents[1] / "aeg_robustness_matrix"
    code = "\n".join(path.read_text(encoding="utf-8") for path in pkg.glob("*.py"))
    forbidden = (
        "control_api_v1",
        "psycopg2",
        "asyncpg",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
        "OPENCLAW_ALLOW_MAINNET",
    )
    for needle in forbidden:
        assert needle not in code

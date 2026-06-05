"""AEG candidate metrics adapter 測試。"""

from __future__ import annotations

import json
from pathlib import Path

from aeg_candidate_metrics import artifact as artifact_mod
from aeg_candidate_metrics import builder as builder_mod


def _report_with_per_regime(*, include_net_and_freshness: bool = False) -> dict:
    per_regime = {
        "bull": {"n_days": 120, "mean_daily_bps": 0.4, "annualized_net_sharpe": 0.8},
        "chop": {"n_days": 80, "mean_daily_bps": -0.1, "annualized_net_sharpe": -0.2},
    }
    if include_net_and_freshness:
        for value in per_regime.values():
            value["net_bps"] = value["mean_daily_bps"]
    return {
        "phase": "phase_1_fail_fast_early_gates",
        "date_span": ["2024-06-03", "2026-06-03"],
        "decision_tree": {"verdict": "NO-GO-TREND", "best_variant": "tsmom_k40__daily"},
        "signal_evaluation": {
            "tsmom_k20__daily": {
                "annualized_net_sharpe_leakfree": 0.1,
                "per_regime_net": {"bull": {"n_days": 10}},
            },
            "tsmom_k40__daily": {
                "annualized_net_sharpe_leakfree": 0.7,
                "per_regime_net": per_regime,
                **(
                    {"recent_90d_net_bps": 1.2, "recent_180d_net_bps": 0.8}
                    if include_net_and_freshness else {}
                ),
            },
        },
    }


def test_existing_diagnostic_per_regime_missing_net_and_freshness_fails_closed():
    rows, summary = builder_mod.build_candidate_metrics(
        _report_with_per_regime(),
        run_id="metrics_run",
        candidate_id="cand_trend",
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )

    assert summary["selected_variant"] == "tsmom_k40__daily"
    assert summary["source_report_type"] == "multiday_trend_diagnostic"
    assert summary["metric_status_counts"] == {"FAIL": 2}
    bull = next(row for row in rows if row["regime"] == "bull")
    reasons = json.loads(bull["reject_reasons"])
    assert "missing_net_bps" in reasons
    assert "missing_recent_90d_net_bps" in reasons
    assert bull["mean_daily_bps"] == 0.4
    assert bull["net_bps"] is None


def test_explicit_net_and_recent_windows_can_pass():
    rows, summary = builder_mod.build_candidate_metrics(
        _report_with_per_regime(include_net_and_freshness=True),
        run_id="metrics_run",
        candidate_id="cand_trend",
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )

    assert summary["metric_status_counts"] == {"PASS": 2}
    assert summary["freshness_buckets"] == {"recent_90_180_measured": 2}
    assert all(json.loads(row["reject_reasons"]) == [] for row in rows)


def test_falls_back_to_max_sharpe_when_decision_tree_lacks_best_variant():
    report = _report_with_per_regime(include_net_and_freshness=True)
    report["diagnostic"] = "funding_tilt_carry"
    report["phase"] = None
    report["decision_tree"] = {"verdict": "NO-GO-C"}
    rows, summary = builder_mod.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_funding",
        strategy_family="funding_tilt",
        parameter_cell_id="L9",
    )

    assert summary["source_report_type"] == "funding_tilt_diagnostic"
    assert summary["selected_variant"] == "tsmom_k40__daily"
    assert len(rows) == 2


def test_artifact_write_creates_index_and_manifest(tmp_path):
    rows, summary = builder_mod.build_candidate_metrics(
        _report_with_per_regime(include_net_and_freshness=True),
        run_id="metrics_run",
        candidate_id="cand_trend",
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )
    written = artifact_mod.write_all(
        rows,
        summary,
        run_id="metrics_run",
        repo_root=Path("."),
        runtime_host="test",
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    assert (run_dir / "candidate_regime_metrics.csv").exists()
    assert (run_dir / "candidate_metrics_summary.json").exists()
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert manifest["policy"] == "no_unit_substitution_mean_daily_is_not_net_bps"
    assert any(entry["name"] == "candidate_regime_metrics.csv" for entry in index["artifacts"])


def test_candidate_metrics_has_no_runtime_or_db_write_route_static():
    pkg = Path(__file__).resolve().parents[1] / "aeg_candidate_metrics"
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
    )
    for needle in forbidden:
        assert needle not in code

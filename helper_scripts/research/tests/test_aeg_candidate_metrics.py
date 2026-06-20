"""AEG candidate metrics adapter 測試。"""

from __future__ import annotations

import json
from pathlib import Path

from aeg_candidate_metrics import artifact as artifact_mod
from aeg_candidate_metrics import builder as builder_mod


def _report_with_per_regime(
    *,
    include_net_and_freshness: bool = False,
    include_matrix_fields: bool = False,
) -> dict:
    per_regime = {
        "bull": {"n_days": 120, "mean_daily_bps": 0.4, "annualized_net_sharpe": 0.8},
        "chop": {"n_days": 80, "mean_daily_bps": -0.1, "annualized_net_sharpe": -0.2},
    }
    if include_net_and_freshness:
        per_regime["bull"]["net_bps"] = 3.5
        per_regime["chop"]["net_bps"] = 1.0
    if include_matrix_fields:
        for value in per_regime.values():
            value.update({
                "gross_bps": 7.0,
                "cost_bps": 2.0,
                "net_to_cost_ratio": 1.75,
                "oos_sharpe": 0.42,
                "psr_0": 0.96,
                "dsr_k": 0.95,
                "pbo": 0.2,
                "k_trials": 8,
                "n_independent": 45,
                "sample_unit": "non_overlapping_holding_window",
            })
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


def test_explicit_net_and_recent_windows_without_matrix_fields_still_fails_closed():
    rows, summary = builder_mod.build_candidate_metrics(
        _report_with_per_regime(include_net_and_freshness=True),
        run_id="metrics_run",
        candidate_id="cand_trend",
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )

    assert summary["metric_status_counts"] == {"FAIL": 2}
    assert summary["freshness_buckets"] == {"recent_90_180_measured": 2}
    bull = next(row for row in rows if row["regime"] == "bull")
    reasons = json.loads(bull["reject_reasons"])
    assert bull["net_bps"] == 3.5
    assert "missing_n_independent" in reasons
    assert "missing_psr_0" in reasons
    assert "missing_dsr_k" in reasons
    assert "missing_pbo" in reasons


def test_complete_matrix_fields_can_pass_without_using_n_days_as_n_independent():
    rows, summary = builder_mod.build_candidate_metrics(
        _report_with_per_regime(include_net_and_freshness=True, include_matrix_fields=True),
        run_id="metrics_run",
        candidate_id="cand_trend",
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )

    assert summary["metric_status_counts"] == {"PASS": 2}
    bull = next(row for row in rows if row["regime"] == "bull")
    assert bull["n_days"] == 120
    assert bull["n_independent"] == 45
    assert bull["sample_unit"] == "non_overlapping_holding_window"
    assert json.loads(bull["reject_reasons"]) == []


def test_falls_back_to_max_sharpe_when_decision_tree_lacks_best_variant():
    report = _report_with_per_regime(include_net_and_freshness=True, include_matrix_fields=True)
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


def test_overfitting_dsr_uses_score_not_k_budget():
    report = _report_with_per_regime(include_net_and_freshness=True)
    for value in report["signal_evaluation"]["tsmom_k40__daily"]["per_regime_net"].values():
        value.update({
            "gross_bps": 7.0,
            "cost_bps": 2.0,
            "oos_sharpe": 0.42,
            "n_independent": 45,
            "sample_unit": "non_overlapping_holding_window",
        })
    report["trial_budget_K"] = 8
    report["overfitting"] = {
        "psr_0": 0.96,
        "dsr_k": 8,
        "dsr": 0.77,
        "pbo": {"value": 0.2},
    }
    rows, summary = builder_mod.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_trend",
        strategy_family="multiday_trend",
        parameter_cell_id="k40",
    )

    assert summary["metric_status_counts"] == {"PASS": 2}
    assert rows[0]["dsr_k"] == 0.77
    assert rows[0]["k_trials"] == 8


def test_direct_candidate_regime_metrics_block_is_supported():
    rows, summary = builder_mod.build_candidate_metrics(
        {
            "candidate_regime_metrics": [
                {
                    "regime": "chop",
                    "n_days": 90,
                    "gross_bps": 6.0,
                    "cost_bps": 2.0,
                    "net_bps": 4.0,
                    "mean_daily_bps": 0.2,
                    "annualized_net_sharpe": 0.7,
                    "oos_sharpe": 0.4,
                    "psr_0": 0.96,
                    "dsr_k": 0.95,
                    "pbo": 0.2,
                    "k_trials": 8,
                    "n_independent": 45,
                    "sample_unit": "non_overlapping_holding_window",
                    "recent_90d_net_bps": 1.5,
                    "recent_180d_net_bps": 1.2,
                }
            ],
            "date_span": ["2025-12-01", "2026-06-01"],
            "selected_variant": "listing_fade_v0",
        },
        run_id="metrics_run",
        candidate_id="cand_listing",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )

    assert summary["source_report_type"] == "aeg_candidate_metrics_direct"
    assert summary["selected_variant"] == "listing_fade_v0"
    assert summary["metric_status_counts"] == {"PASS": 1}
    assert rows[0]["regime"] == "chop"
    assert rows[0]["net_to_cost_ratio"] == 2.0


def test_polymarket_leadlag_candidate_exports_fail_closed_ic_lineage():
    report = {
        "program": "polymarket_leadlag_ic",
        "query_set_version": "v2",
        "verdict": {"status": "IC_CANDIDATE_REVIEW_REQUIRED"},
        "ic_results": [{"bucket": "price_target"}, {"bucket": "other"}],
        "candidates": [
            {
                "bucket": "price_target",
                "symbol": "SOLUSDT",
                "horizon_minutes": 15,
                "n_points": 30,
                "n_nonoverlap_timestamps": 30,
                "overlap_adjusted_sample_floor": 30,
                "ic_pearson": 0.2145,
                "t_stat_hac": 6.75,
                "bh_q_value_hac_approx": 3.4e-10,
                "partial_ic_controlling_trailing_return": 0.183,
                "price_feedback_warning": True,
                "price_feedback_partial_collapse_warning": False,
            }
        ],
    }

    rows, summary = builder_mod.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="poly_sol_15m",
        strategy_family="polymarket_leadlag_ic",
        parameter_cell_id="price_target_SOLUSDT_15m",
    )

    assert summary["source_report_type"] == "polymarket_leadlag_ic"
    assert summary["selected_variant"] == "price_target|SOLUSDT|15m"
    assert summary["candidate_key"] == "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    assert summary["diagnostic_verdict"] == "IC_CANDIDATE_REVIEW_REQUIRED"
    assert summary["metric_status_counts"] == {"FAIL": 1}
    assert summary["polymarket_candidate_summary"]["t_stat_hac"] == 6.75
    row = rows[0]
    assert row["regime"] == "unmeasured"
    assert row["n_independent"] == 30
    assert row["sample_unit"] == "overlap_adjusted_ic_timestamps"
    assert row["k_trials"] == 2
    assert row["net_bps"] is None
    reasons = json.loads(row["reject_reasons"])
    assert "missing_net_bps" in reasons
    assert "missing_psr_0" in reasons
    assert "missing_n_independent" not in reasons
    assert "missing_sample_unit" not in reasons


def test_artifact_write_creates_index_and_manifest(tmp_path):
    rows, summary = builder_mod.build_candidate_metrics(
        _report_with_per_regime(include_net_and_freshness=True, include_matrix_fields=True),
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

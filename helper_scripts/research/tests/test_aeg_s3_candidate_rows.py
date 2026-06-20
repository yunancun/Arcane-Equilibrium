"""AEG-S3 candidate direct rows builder 測試。"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

from aeg_candidate_metrics import builder as candidate_builder
from aeg_s3_candidate_rows import artifact as artifact_mod
from aeg_s3_candidate_rows import builder as builder_mod


def _complete_evidence(*, with_pbo: bool = True) -> dict:
    samples = []
    regime_by_date = {}
    daily_values = {}
    for i in range(64):
        regime = "chop" if i < 32 else "bear"
        day = (date(2026, 3, 1) + timedelta(days=i)).isoformat()
        regime_by_date[day] = regime
        daily_values[day] = 0.0008
        net = 7.0 + (i % 3)
        samples.append({
            "sample_id": f"s{i}",
            "sample_ts_utc": f"{day}T00:00:00Z",
            "regime": regime,
            "independence_bucket": f"bucket-{i}",
            "gross_bps": net + 2.0,
            "cost_bps": 2.0,
            "net_bps": net,
            "is_oos": i % 2 == 0,
        })
    pbo_candidates = None
    if with_pbo:
        # Monotonic candidate scores make the train-best cell remain test-best.
        pbo_candidates = {
            f"cell_{c}": {
                (date(2026, 3, 1) + timedelta(days=d)).isoformat(): 0.0001 * c + d * 0.000001
                for d in range(64)
            }
            for c in range(12)
        }
    return {
        "candidate_id": "cand_listing",
        "strategy_family": "listing_fade",
        "parameter_cell_id": "v0",
        "selected_variant": "fade_after_pump_500bps",
        "sample_unit": "listing_event_window",
        "k_trials": 8,
        "annualization_factor": 365,
        "samples": samples,
        "daily_returns": {
            "unit": "fraction",
            "regime_by_date": regime_by_date,
            "values": daily_values,
        },
        **({"pbo_candidates": pbo_candidates} if pbo_candidates is not None else {}),
    }


def test_complete_evidence_builds_direct_report_consumed_by_candidate_metrics():
    report, summary, sample_rows, daily_rows = builder_mod.build_direct_report(
        _complete_evidence(),
        run_id="s3_run",
    )

    assert report["candidate_id"] == "cand_listing"
    assert summary["sample_count"] == 64
    assert summary["n_regime_rows"] == 2
    assert len(sample_rows) == 64
    assert len(daily_rows) == 64

    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_listing",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )
    assert adapted["source_report_type"] == "aeg_candidate_metrics_direct"
    assert adapted["metric_status_counts"] == {"PASS": 2}
    assert {row["sample_unit"] for row in rows} == {"listing_event_window"}
    assert all(row["n_independent"] == 32 for row in rows)
    assert all(row["mean_daily_bps"] == 8.0 for row in rows)


def test_direct_report_preserves_explicit_candidate_key_for_metrics_adapter():
    evidence = _complete_evidence()
    evidence["candidate_key"] = "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    report, summary, _sample_rows, _daily_rows = builder_mod.build_direct_report(
        evidence,
        run_id="s3_run",
    )

    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_listing",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )

    assert report["candidate_key"] == "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    assert summary["candidate_key"] == "polymarket_leadlag_ic|price_target|SOLUSDT|15m"
    assert rows
    assert adapted["candidate_key"] == "polymarket_leadlag_ic|price_target|SOLUSDT|15m"


def test_missing_daily_returns_does_not_synthesize_mean_daily_bps():
    evidence = _complete_evidence()
    evidence.pop("daily_returns")

    report, _summary, _sample_rows, _daily_rows = builder_mod.build_direct_report(evidence, run_id="s3_run")
    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_listing",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )

    assert adapted["metric_status_counts"] == {"FAIL": 2}
    assert all(row["mean_daily_bps"] is None for row in rows)
    reasons = json.loads(rows[0]["reject_reasons"])
    assert "missing_mean_daily_bps" in reasons


def test_missing_independence_bucket_does_not_use_row_count_as_n_independent():
    evidence = _complete_evidence()
    for row in evidence["samples"]:
        row.pop("independence_bucket")

    report, _summary, _sample_rows, _daily_rows = builder_mod.build_direct_report(evidence, run_id="s3_run")
    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_listing",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )

    assert adapted["metric_status_counts"] == {"FAIL": 2}
    assert all(row["n_independent"] is None for row in rows)
    assert "missing_n_independent" in json.loads(rows[0]["reject_reasons"])


def test_missing_pbo_inputs_fail_closed():
    report, _summary, _sample_rows, _daily_rows = builder_mod.build_direct_report(
        _complete_evidence(with_pbo=False),
        run_id="s3_run",
    )
    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="cand_listing",
        strategy_family="listing_fade",
        parameter_cell_id="v0",
    )

    assert adapted["metric_status_counts"] == {"FAIL": 2}
    assert all(row["pbo"] is None for row in rows)
    assert "missing_pbo" in json.loads(rows[0]["reject_reasons"])


def test_artifact_write_creates_direct_report_and_manifest(tmp_path):
    report, summary, sample_rows, daily_rows = builder_mod.build_direct_report(
        _complete_evidence(),
        run_id="s3_run",
    )
    written = artifact_mod.write_all(
        direct_report=report,
        summary=summary,
        sample_rows=sample_rows,
        daily_rows=daily_rows,
        run_id="s3_run",
        repo_root=Path("."),
        runtime_host="test",
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    direct = json.loads((run_dir / "candidate_direct_metrics_report.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert direct["candidate_regime_metrics"]
    assert manifest["policy"] == "explicit_sample_returns_only_no_scalar_to_series_synthesis"
    assert any(entry["name"] == "candidate_sample_returns.csv" for entry in index["artifacts"])


def test_static_no_runtime_or_db_write_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_candidate_rows"
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

"""Tests for AEG-S3 event breadth wiring."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import pytest

from aeg_s3_event_breadth import builder as builder_mod
from aeg_s3_event_breadth import harness as harness_mod


def _write_fnd2_universe(run_dir: Path) -> None:
    run_dir.mkdir()
    cols = [
        "symbol",
        "cohort_ids",
        "included",
        "alive_from_utc",
        "alive_to_utc",
        "seen_delisted",
        "recommended_tier",
        "unknown_lifetime",
        "universe_id",
        "run_id",
    ]
    rows = [
        {
            "symbol": "BTCUSDT",
            "cohort_ids": '["full_survivorship","core25_pinned"]',
            "included": "true",
            "alive_from_utc": "2024-01-01T00:00:00+00:00",
            "alive_to_utc": "",
            "seen_delisted": "false",
            "recommended_tier": "core25_pinned",
            "unknown_lifetime": "false",
            "universe_id": "uid_event",
            "run_id": "fnd2_event",
        },
        {
            "symbol": "ALTUSDT",
            "cohort_ids": '["full_survivorship","top_liquidity_40_50"]',
            "included": "true",
            "alive_from_utc": "2024-01-01T00:00:00+00:00",
            "alive_to_utc": "",
            "seen_delisted": "false",
            "recommended_tier": "top_liquidity_40_50",
            "unknown_lifetime": "false",
            "universe_id": "uid_event",
            "run_id": "fnd2_event",
        },
        {
            "symbol": "DEADUSDT",
            "cohort_ids": '["full_survivorship","historical_delisted"]',
            "included": "true",
            "alive_from_utc": "2024-01-01T00:00:00+00:00",
            "alive_to_utc": "2025-01-01T00:00:00+00:00",
            "seen_delisted": "true",
            "recommended_tier": "full_survivorship",
            "unknown_lifetime": "false",
            "universe_id": "uid_event",
            "run_id": "fnd2_event",
        },
    ]
    with open(run_dir / "universe.csv", "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    (run_dir / "universe_summary.json").write_text(json.dumps({
        "universe_id": "uid_event",
        "run_id": "fnd2_event",
        "asof_utc": "2026-06-03T00:00:00+00:00",
        "window_start_utc": "2024-01-01T00:00:00+00:00",
        "window_end_utc": "2026-06-03T00:00:00+00:00",
        "survivor_rejection_status": "PASS",
        "delisted_proof_count": 1,
    }), encoding="utf-8")


def _funding_evidence(path: Path) -> None:
    payload = {
        "schema_version": "test",
        "run_id": "funding_evidence",
        "candidate_id": "funding_revive",
        "strategy_family": "funding_revive",
        "parameter_cell_id": "cell",
        "sample_unit": "funding_revive_event_window",
        "k_trials": 18,
        "annualization_factor": 365,
        "samples": [
            {
                "sample_id": "btc",
                "sample_ts_utc": "2025-06-01T00:00:00+00:00",
                "symbol": "BTCUSDT",
                "gross_bps": 15.0,
                "cost_bps": 5.0,
                "net_bps": 10.0,
                "independence_bucket": "2025-06-01:funding_revive",
                "is_oos": False,
            },
            {
                "sample_id": "alt",
                "sample_ts_utc": "2025-06-02T00:00:00+00:00",
                "symbol": "ALTUSDT",
                "gross_bps": 25.0,
                "cost_bps": 5.0,
                "net_bps": 20.0,
                "independence_bucket": "2025-06-02:funding_revive",
                "is_oos": True,
            },
            {
                "sample_id": "dead_alive",
                "sample_ts_utc": "2024-12-01T00:00:00+00:00",
                "symbol": "DEADUSDT",
                "gross_bps": 35.0,
                "cost_bps": 5.0,
                "net_bps": 30.0,
                "independence_bucket": "2024-12-01:funding_revive",
                "is_oos": True,
            },
            {
                "sample_id": "dead_after_delist",
                "sample_ts_utc": "2025-02-01T00:00:00+00:00",
                "symbol": "DEADUSDT",
                "gross_bps": 45.0,
                "cost_bps": 5.0,
                "net_bps": 40.0,
                "independence_bucket": "2025-02-01:funding_revive",
                "is_oos": True,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def _csv_rows(path: Path) -> list[dict[str, str]]:
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_event_breadth_builds_true_fnd2_masked_ladder(tmp_path):
    fnd2_dir = tmp_path / "fnd2"
    _write_fnd2_universe(fnd2_dir)
    evidence_path = tmp_path / "funding_evidence.json"
    _funding_evidence(evidence_path)

    result = harness_mod.build_and_write(argparse.Namespace(
        run_id="event_breadth",
        candidate_evidence_json=str(evidence_path),
        fnd2_run_dir=str(fnd2_dir),
        asof=None,
        window_start=None,
        window_end=None,
        artifact_root=str(tmp_path / "out"),
        session_id=None,
        created_by_role="PM",
    ))

    summary = result["summary"]
    assert summary["candidate_id"] == "funding_revive"
    assert summary["survivorship_inherited_from_fnd2"] is True
    assert summary["survivorship_healthcheck"]["status"] == "PASS"
    assert summary["event_breadth_adapter"]["valid_sample_count"] == 4

    rows = _csv_rows(Path(result["written"]["breadth_ladder_csv"]))
    full = next(row for row in rows if row["breadth_cohort"] == "full_survivorship")
    core = next(row for row in rows if row["breadth_cohort"] == "core25_pinned")
    assert core["net_bps"] == "10"
    assert full["net_bps"] == "20"
    assert full["seen_delisted_count"] == "1"
    assert full["n_independent"] == "3"
    assert summary["per_tier_breadth"]["full_survivorship"] == 3


def test_cross_sectional_oi_delta_fails_closed():
    evidence = {
        "candidate_id": "oi_delta",
        "samples": [
            {
                "sample_ts_utc": "2025-06-01T00:00:00+00:00",
                "gross_bps": 5.0,
                "cost_bps": 1.0,
                "net_bps": 4.0,
                "top_symbols": ["BTCUSDT"],
                "bottom_symbols": ["ALTUSDT"],
            }
        ],
    }
    with pytest.raises(builder_mod.UnsupportedCandidateEvidence):
        builder_mod.EventEvidenceEvaluator(evidence)


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_event_breadth"
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

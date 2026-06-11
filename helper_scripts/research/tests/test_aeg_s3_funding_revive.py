"""AEG-S3 funding revive evidence producer 測試。"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aeg_candidate_metrics import builder as candidate_builder
from aeg_s3_candidate_rows import builder as rows_builder
from aeg_s3_funding_revive import artifact as artifact_mod
from aeg_s3_funding_revive import builder as builder_mod


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _stress_revive_panel() -> list[dict]:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict] = []
    price = 100.0
    for i in range(64):
        t0 = base + timedelta(days=i * 3)
        symbol = f"FR{i % 4:02d}USDT"
        rows.append({
            "symbol": symbol,
            "ts_utc": t0.isoformat(),
            "funding_bps": -8.0,
            "funding_zscore": -2.8,
            "price": price,
            "regime": "chop",
        })
        rows.append({
            "symbol": symbol,
            "ts_utc": (t0 + timedelta(days=1)).isoformat(),
            "funding_bps": -2.0,
            "funding_zscore": -0.5,
            "price": price,
            "regime": "chop",
        })
        rows.append({
            "symbol": symbol,
            "ts_utc": (t0 + timedelta(days=2)).isoformat(),
            "funding_bps": -1.0,
            "funding_zscore": 0.0,
            "price": price * 1.0018,
            "regime": "chop",
        })
        price *= 1.0003
    return rows


def test_panel_builds_funding_revive_evidence_consumed_by_s3_rows():
    evidence, summary = builder_mod.build_funding_revive_evidence(
        _stress_revive_panel(),
        source_path="fixture.jsonl",
        run_id="funding_revive_run",
        lookback_points=5,
        horizon_hours=24,
        stress_z=2.0,
        exit_z=1.0,
        cost_bps=5.0,
        k_trials=16,
        default_regime="chop",
        oos_start_date="2026-03-15",
    )

    assert summary["sample_count"] == 64
    assert summary["accepted_net_bps_mean"] > 10.0
    assert evidence["strategy_family"] == "funding_revive"
    assert evidence["daily_returns"]["policy"] == "mean_explicit_funding_revive_event_net_bps_by_sample_date"
    assert evidence["samples"][0]["side"] == "long"
    assert evidence["samples"][0]["funding_pnl_bps"] == 1.0

    report, _s3_summary, _sample_rows, _daily_rows = rows_builder.build_direct_report(
        evidence,
        run_id="direct_run",
    )
    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="funding_revive",
        strategy_family="funding_revive",
        parameter_cell_id=evidence["parameter_cell_id"],
    )
    assert adapted["source_report_type"] == "aeg_candidate_metrics_direct"
    assert adapted["metric_status_counts"] == {"FAIL": 1}
    assert rows[0]["n_independent"] == 64
    assert rows[0]["net_bps"] > 10.0
    assert json.loads(rows[0]["reject_reasons"]) == ["missing_pbo"]


def test_missing_regime_rejects_events_instead_of_creating_unlabeled_regime():
    payload = _stress_revive_panel()
    for row in payload:
        row.pop("regime", None)

    evidence, summary = builder_mod.build_funding_revive_evidence(
        payload,
        source_path="fixture.jsonl",
        run_id="funding_revive_run",
        lookback_points=5,
        horizon_hours=24,
        stress_z=2.0,
        exit_z=1.0,
        cost_bps=5.0,
        k_trials=16,
    )

    assert evidence["samples"] == []
    assert "daily_returns" not in evidence
    assert summary["event_reject_reasons"] == {"missing_regime": 64}


def test_positive_stress_unwind_builds_short_event_with_funding_pnl():
    base = datetime(2026, 4, 1, tzinfo=timezone.utc)
    payload = [
        {
            "symbol": "HOTUSDT",
            "ts_utc": base.isoformat(),
            "funding_bps": 7.0,
            "funding_zscore": 2.5,
            "price": 100.0,
            "regime": "bear",
        },
        {
            "symbol": "HOTUSDT",
            "ts_utc": (base + timedelta(days=1)).isoformat(),
            "funding_bps": 2.0,
            "funding_zscore": 0.5,
            "price": 100.0,
            "regime": "bear",
        },
        {
            "symbol": "HOTUSDT",
            "ts_utc": (base + timedelta(days=2)).isoformat(),
            "funding_bps": 1.0,
            "funding_zscore": 0.0,
            "price": 99.8,
            "regime": "bear",
        },
    ]

    evidence, summary = builder_mod.build_funding_revive_evidence(
        payload,
        source_path="short.jsonl",
        run_id="short",
        lookback_points=5,
        horizon_hours=24,
        stress_z=2.0,
        exit_z=1.0,
        cost_bps=5.0,
        k_trials=16,
    )

    assert summary["sample_count"] == 1
    sample = evidence["samples"][0]
    assert sample["side"] == "short"
    assert sample["gross_price_bps"] == 20.0
    assert sample["funding_pnl_bps"] == 1.0
    assert sample["net_bps"] == 16.0


def test_rolling_zscore_can_be_computed_from_raw_funding_bps():
    base = datetime(2026, 5, 1, tzinfo=timezone.utc)
    funding = [-1.0, 0.0, 1.0, -1.0, 0.0, -3.0, -0.5, -0.2]
    prices = [100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.2]
    payload = [
        {
            "symbol": "RAWUSDT",
            "ts_utc": (base + timedelta(days=i)).isoformat(),
            "funding_bps": funding[i],
            "price": prices[i],
            "regime": "chop",
        }
        for i in range(len(funding))
    ]

    evidence, summary = builder_mod.build_funding_revive_evidence(
        payload,
        source_path="raw.jsonl",
        run_id="raw",
        lookback_points=5,
        horizon_hours=24,
        stress_z=2.0,
        exit_z=1.0,
        cost_bps=1.0,
        k_trials=16,
        default_regime="chop",
    )

    assert summary["sample_count"] == 1
    assert evidence["samples"][0]["side"] == "long"
    assert evidence["samples"][0]["net_bps"] > 0.0


def test_artifact_write_creates_evidence_manifest_and_index(tmp_path):
    evidence, summary = builder_mod.build_funding_revive_evidence(
        _stress_revive_panel(),
        source_path="fixture.jsonl",
        run_id="funding_revive_run",
        lookback_points=5,
        horizon_hours=24,
        stress_z=2.0,
        exit_z=1.0,
        cost_bps=5.0,
        k_trials=16,
        default_regime="chop",
    )
    written = artifact_mod.write_all(
        evidence=evidence,
        summary=summary,
        run_id="funding_revive_run",
        repo_root=Path("."),
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    direct_input = json.loads((run_dir / "funding_revive_candidate_evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert direct_input["samples"]
    assert manifest["policy"] == "explicit_funding_revive_event_windows_only_no_db_or_tilt_reopen"
    assert any(entry["name"] == "funding_revive_candidate_evidence.json" for entry in index["artifacts"])


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_funding_revive"
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

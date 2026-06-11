"""AEG-S3 listing fade evidence producer 測試。"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

from aeg_candidate_metrics import builder as candidate_builder
from aeg_s3_candidate_rows import builder as rows_builder
from aeg_s3_listing_fade import artifact as artifact_mod
from aeg_s3_listing_fade import builder as builder_mod


def _ms(day_index: int, seconds: int = 0) -> int:
    dt = datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(days=day_index, seconds=seconds)
    return int(dt.timestamp() * 1000)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(row, sort_keys=True) for row in rows) + "\n", encoding="utf-8")


def _gate_b_run_dir(tmp_path: Path, *, slow_symbol: str | None = None) -> Path:
    run_dir = tmp_path / "gate_b_run"
    run_dir.mkdir()
    capture_lags = []
    markouts = []
    for i in range(64):
        symbol = f"NEW{i:03d}USDT"
        trigger_ms = _ms(i)
        capture_lags.append({
            "kind": "capture_lag",
            "symbol": symbol,
            "launch_time_ms": trigger_ms - 1000,
            "first_trade_event_ts_ms": trigger_ms,
            "capture_lag_ms": 1000,
            "verdict": "SLOW_CAPTURE" if symbol == slow_symbol else "PASS_CAPTURE",
        })
        entry = 1.0 + i * 0.001
        # Price falls after listing; short fade gross is positive and non-constant.
        markout_bps = -18.0 - (i % 5)
        exit_price = entry * (1.0 + markout_bps / 10_000.0)
        markouts.append({
            "kind": "markout_trigger",
            "symbol": symbol,
            "trigger_event_ts_ms": trigger_ms,
            "mid_at_trigger": entry,
        })
        markouts.append({
            "kind": "markout_fill",
            "symbol": symbol,
            "trigger_event_ts_ms": trigger_ms,
            "horizon_s": 300,
            "target_event_ts_ms": trigger_ms + 300_000,
            "filled_event_ts_ms": trigger_ms + 300_000,
            "mid_at_trigger": entry,
            "mid_at_horizon": exit_price,
            "markout_bps": markout_bps,
        })
    _write_jsonl(run_dir / "capture_lag.jsonl", capture_lags)
    _write_jsonl(run_dir / "markout.jsonl", markouts)
    return run_dir


def test_gate_b_run_builds_listing_fade_evidence_consumed_by_s3_rows(tmp_path):
    payload = builder_mod.load_gate_b_run(_gate_b_run_dir(tmp_path))
    evidence, summary = builder_mod.build_listing_fade_evidence(
        payload,
        source_type="gate_b_run",
        source_path="fixture",
        run_id="listing_run",
        horizon_s=300,
        cost_bps=2.0,
        k_trials=12,
        default_regime="chop",
        oos_start_date="2026-04-02",
    )

    assert summary["sample_count"] == 64
    assert summary["rejected_sample_count"] == 0
    assert evidence["strategy_family"] == "listing_fade"
    assert evidence["daily_returns"]["policy"] == "sum_explicit_listing_event_net_bps_by_sample_date"
    assert len(evidence["daily_returns"]["values"]) == 64

    report, _s3_summary, _sample_rows, _daily_rows = rows_builder.build_direct_report(
        evidence,
        run_id="direct_run",
    )
    rows, adapted = candidate_builder.build_candidate_metrics(
        report,
        run_id="metrics_run",
        candidate_id="listing_fade",
        strategy_family="listing_fade",
        parameter_cell_id=evidence["parameter_cell_id"],
    )
    assert adapted["source_report_type"] == "aeg_candidate_metrics_direct"
    assert adapted["metric_status_counts"] == {"FAIL": 1}
    reasons = json.loads(rows[0]["reject_reasons"])
    assert reasons == ["missing_pbo"]
    assert rows[0]["n_independent"] == 64
    assert rows[0]["mean_daily_bps"] is not None


def test_missing_regime_rejects_samples_instead_of_creating_unlabeled_regime(tmp_path):
    payload = builder_mod.load_gate_b_run(_gate_b_run_dir(tmp_path))
    evidence, summary = builder_mod.build_listing_fade_evidence(
        payload,
        source_type="gate_b_run",
        source_path="fixture",
        run_id="listing_run",
        horizon_s=300,
        cost_bps=2.0,
        k_trials=12,
    )

    assert evidence["samples"] == []
    assert "daily_returns" not in evidence
    assert summary["reject_reasons"] == {"missing_regime": 64}


def test_slow_capture_excluded_by_default_and_allowed_when_explicit(tmp_path):
    payload = builder_mod.load_gate_b_run(_gate_b_run_dir(tmp_path, slow_symbol="NEW000USDT"))
    strict_evidence, strict_summary = builder_mod.build_listing_fade_evidence(
        payload,
        source_type="gate_b_run",
        source_path="fixture",
        run_id="strict",
        horizon_s=300,
        cost_bps=2.0,
        k_trials=12,
        default_regime="chop",
    )
    loose_evidence, loose_summary = builder_mod.build_listing_fade_evidence(
        payload,
        source_type="gate_b_run",
        source_path="fixture",
        run_id="loose",
        horizon_s=300,
        cost_bps=2.0,
        k_trials=12,
        default_regime="chop",
        allow_slow_capture=True,
    )

    assert strict_summary["sample_count"] == 63
    assert strict_summary["reject_reasons"] == {"capture_verdict_not_allowed:SLOW_CAPTURE": 1}
    assert loose_summary["sample_count"] == 64
    assert len(loose_evidence["samples"]) == len(strict_evidence["samples"]) + 1


def test_capture_events_jsonl_source_computes_horizon_markout(tmp_path):
    path = tmp_path / "listing_capture_events.jsonl"
    start = _ms(0)
    _write_jsonl(path, [
        {
            "event_kind": "capture_lag",
            "symbol": "NEWUSDT",
            "event_ts_exchange_ms": start,
            "launch_time_ms": start - 1000,
            "capture_lag_ms": 1000,
            "capture_verdict": "PASS_CAPTURE",
        },
        {
            "event_kind": "public_trade",
            "symbol": "NEWUSDT",
            "event_ts_exchange_ms": start,
            "price": 1.0,
            "trade_id": "t0",
        },
        {
            "event_kind": "public_trade",
            "symbol": "NEWUSDT",
            "event_ts_exchange_ms": start + 300_000,
            "price": 0.997,
            "trade_id": "t1",
        },
    ])

    payload = builder_mod.load_capture_events_jsonl(path)
    evidence, summary = builder_mod.build_listing_fade_evidence(
        payload,
        source_type="capture_events_jsonl",
        source_path=str(path),
        run_id="events_run",
        horizon_s=300,
        cost_bps=2.0,
        k_trials=12,
        default_regime="bear",
    )

    assert summary["sample_count"] == 1
    sample = evidence["samples"][0]
    assert sample["gross_bps"] == 30.0
    assert sample["net_bps"] == 28.0
    assert sample["regime"] == "bear"


def test_artifact_write_creates_evidence_manifest_and_index(tmp_path):
    payload = builder_mod.load_gate_b_run(_gate_b_run_dir(tmp_path))
    evidence, summary = builder_mod.build_listing_fade_evidence(
        payload,
        source_type="gate_b_run",
        source_path="fixture",
        run_id="listing_run",
        horizon_s=300,
        cost_bps=2.0,
        k_trials=12,
        default_regime="chop",
    )
    written = artifact_mod.write_all(
        evidence=evidence,
        summary=summary,
        run_id="listing_run",
        repo_root=Path("."),
        artifact_root=tmp_path / "out",
        created_by_role="PM",
    )

    run_dir = Path(written["run_dir"])
    direct_input = json.loads((run_dir / "listing_fade_candidate_evidence.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    index = json.loads((run_dir / "artifact_index.json").read_text(encoding="utf-8"))
    assert direct_input["samples"]
    assert manifest["policy"] == "explicit_listing_event_windows_only_no_connection_only_samples"
    assert any(entry["name"] == "listing_fade_candidate_evidence.json" for entry in index["artifacts"])


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_listing_fade"
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

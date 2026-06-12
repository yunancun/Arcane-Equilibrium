"""Tests for AEG-S3 execution observation producers."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from aeg_s3_event_execution_realism import harness as event_exec_harness
from aeg_s3_execution_observations import builder as builder_mod
from aeg_s3_execution_observations import harness as harness_mod


def _ms(idx: int) -> int:
    ts = datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(days=idx)
    return int(ts.timestamp() * 1000)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).isoformat()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _listing_evidence(sample_count: int = 40) -> dict:
    samples = []
    for idx in range(sample_count):
        ts_ms = _ms(idx)
        symbol = f"NEW{idx:03d}USDT"
        samples.append({
            "sample_id": f"{symbol}:{ts_ms}",
            "sample_ts_utc": _iso(ts_ms),
            "regime": "chop",
            "independence_bucket": f"2026-03-{idx + 1:02d}:{symbol}",
            "gross_bps": 25.0,
            "cost_bps": 5.0,
            "net_bps": 20.0,
            "source_symbol": symbol,
            "entry_price": 1.0 + idx * 0.001,
            "exit_price": 0.998 + idx * 0.001,
        })
    return {
        "candidate_id": "listing_fade",
        "strategy_family": "listing_fade",
        "parameter_cell_id": "h300s_cost5",
        "samples": samples,
    }


def _gate_b_run_dir(tmp_path: Path, evidence: dict, *, count: int | None = None) -> Path:
    run_dir = tmp_path / "gate_b_run"
    run_dir.mkdir()
    capture_rows = []
    markout_rows = []
    publictrade_rows = []
    rows = evidence["samples"] if count is None else evidence["samples"][:count]
    for idx, sample in enumerate(rows):
        symbol = sample["source_symbol"]
        ts_ms = _ms(idx)
        entry = float(sample["entry_price"])
        capture_rows.append({
            "kind": "capture_lag",
            "symbol": symbol,
            "launch_time_ms": ts_ms - 1000,
            "first_trade_event_ts_ms": ts_ms,
            "first_trade_ingest_ts_local_ms": ts_ms + 80,
            "capture_lag_ms": 1000,
            "verdict": "PASS_CAPTURE",
        })
        markout_rows.append({
            "kind": "markout_trigger",
            "symbol": symbol,
            "trigger_event_ts_ms": ts_ms,
            "mid_at_trigger": entry,
        })
        # First minute trade notional is 1000+ USDT so a 10 USDT probe stays below 5%.
        publictrade_rows.append({
            "kind": "public_trade",
            "symbol": symbol,
            "event_ts_exchange_ms": ts_ms,
            "price": entry,
            "side": "Buy",
            "size": 500.0,
            "ingest_ts_local_ms": ts_ms + 80,
            "ingest_minus_event_ms": 80,
            "trade_id": f"{symbol}:0",
        })
        publictrade_rows.append({
            "kind": "public_trade",
            "symbol": symbol,
            "event_ts_exchange_ms": ts_ms + 30_000,
            "price": entry * 0.999,
            "side": "Sell",
            "size": 700.0,
            "ingest_ts_local_ms": ts_ms + 30_090,
            "ingest_minus_event_ms": 90,
            "trade_id": f"{symbol}:1",
        })
    _write_jsonl(run_dir / "capture_lag.jsonl", capture_rows)
    _write_jsonl(run_dir / "markout.jsonl", markout_rows)
    _write_jsonl(run_dir / "ws_publictrade.jsonl", publictrade_rows)
    return run_dir


def test_gate_b_observations_feed_event_execution_realism_pass(tmp_path):
    evidence = _listing_evidence(40)
    evidence_path = tmp_path / "listing_fade_candidate_evidence.json"
    evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
    gate_b_dir = _gate_b_run_dir(tmp_path, evidence)

    obs_result = harness_mod.build_and_write(argparse.Namespace(
        run_id="execution_obs",
        candidate_evidence_json=str(evidence_path),
        gate_b_run_dir=str(gate_b_dir),
        maker_fee_bps=2.0,
        taker_fee_bps=5.5,
        order_notional_usdt=10.0,
        evidence_source_tier="calibrated_replay",
        order_style="taker",
        slippage_floor_bps=0.5,
        capacity_window_s=60,
        allow_slow_capture=False,
        artifact_root=str(tmp_path / "out"),
        session_id=None,
        created_by_role="PM",
    ))
    assert obs_result["summary"]["observation_count"] == 40
    assert obs_result["summary"]["reject_reasons"] == {}

    exec_result = event_exec_harness.build_and_write(argparse.Namespace(
        run_id="event_execution_realism",
        candidate_evidence_json=str(evidence_path),
        execution_observations_jsonl=obs_result["written"]["execution_observations_jsonl"],
        evidence_source_tier=None,
        order_style=None,
        capacity_notional_usdt=None,
        order_availability_status=None,
        artifact_root=str(tmp_path / "out"),
        session_id=None,
        created_by_role="PM",
    ))

    payload = exec_result["payload"]
    assert payload["status"] == "PASS"
    assert payload["execution_realism_mode"] == "calibrated_calibrated_replay_taker"
    assert payload["sample_count"] == 40
    assert payload["slippage_bps_p95"] == 0.5
    assert payload["participation_rate_p95"] < 0.05
    assert payload["event_execution_summary"]["matched_observation_count"] == 40


def test_gate_b_observations_insufficient_sample_remains_fail_closed(tmp_path):
    evidence = _listing_evidence(40)
    gate_b_dir = _gate_b_run_dir(tmp_path, evidence, count=10)
    observations, summary = builder_mod.build_gate_b_observations(
        candidate_evidence=evidence,
        gate_b_payload=builder_mod.load_gate_b_run(gate_b_dir),
        source_path=str(gate_b_dir),
        maker_fee_bps=2.0,
        taker_fee_bps=5.5,
        order_notional_usdt=10.0,
        slippage_floor_bps=0.5,
    )
    assert len(observations) == 10
    assert summary["reject_reasons"] == {"missing_capture_lag": 30}


def test_gate_b_observations_reject_unsupported_candidate():
    with pytest.raises(builder_mod.UnsupportedCandidateEvidence):
        builder_mod.build_gate_b_observations(
            candidate_evidence={
                "candidate_id": "funding_revive",
                "strategy_family": "funding_revive",
                "parameter_cell_id": "cell",
                "samples": [{
                    "sample_id": "sample_1",
                    "sample_ts_utc": "2026-03-01T00:00:00+00:00",
                    "symbol": "BTCUSDT",
                    "gross_bps": 1.0,
                    "cost_bps": 1.0,
                    "net_bps": 0.0,
                }],
            },
            gate_b_payload={"capture_lag": [], "markout": [], "publictrade": []},
            source_path="fixture",
            maker_fee_bps=2.0,
            taker_fee_bps=5.5,
            order_notional_usdt=10.0,
        )


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_execution_observations"
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


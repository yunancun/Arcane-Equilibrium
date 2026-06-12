"""Tests for the AEG-S3 Gate-B evidence-chain orchestrator."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from aeg_regime_runner.artifact import LABEL_COLUMNS
from aeg_s3_gate_b_chain import harness as harness_mod


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


def _gate_b_run_dir(tmp_path: Path, *, sample_count: int = 40) -> Path:
    run_dir = tmp_path / "gate_b_run"
    run_dir.mkdir()
    capture_rows = []
    markout_rows = []
    publictrade_rows = []
    for idx in range(sample_count):
        ts_ms = _ms(idx)
        symbol = f"NEW{idx:03d}USDT"
        entry = 1.0 + idx * 0.001
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
            "kind": "markout_fill",
            "symbol": symbol,
            "trigger_event_ts_ms": ts_ms,
            "filled_event_ts_ms": ts_ms + 60_000,
            "horizon_s": 60,
            "mid_at_trigger": entry,
            "mid_at_horizon": entry * 0.9975,
            "markout_bps": -25.0,
        })
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


def _write_csv(path: Path, columns, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(columns))
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") for col in columns})


def _fnd2_dir(tmp_path: Path, *, sample_count: int = 40) -> Path:
    run_dir = tmp_path / "fnd2"
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
    rows = []
    for idx in range(sample_count):
        rows.append({
            "symbol": f"NEW{idx:03d}USDT",
            "cohort_ids": '["full_survivorship"]',
            "included": "true",
            "alive_from_utc": "2025-01-01T00:00:00+00:00",
            "alive_to_utc": "",
            "seen_delisted": "false",
            "recommended_tier": "full_survivorship",
            "unknown_lifetime": "false",
            "universe_id": "uid_gate_b_chain",
            "run_id": "fnd2_gate_b_chain",
        })
    _write_csv(run_dir / "universe.csv", cols, rows)
    (run_dir / "universe_summary.json").write_text(json.dumps({
        "universe_id": "uid_gate_b_chain",
        "run_id": "fnd2_gate_b_chain",
        "asof_utc": "2026-06-03T00:00:00+00:00",
        "window_start_utc": "2025-01-01T00:00:00+00:00",
        "window_end_utc": "2026-06-03T00:00:00+00:00",
        "survivor_rejection_status": "PROVEN_NONE_IN_WINDOW",
        "delisted_proof_count": 0,
    }), encoding="utf-8")
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
                "signal_ts": "2026-03-01T00:00:00+00:00",
                "symbol": "BTCUSDT",
                "timeframe": "1d",
                "main_regime": "chop",
                "market_anchor_regime": "range",
                "high_vol_overlay": "false",
                "overlay_flags": "{}",
                "context_bars": "300",
                "insufficient_context": "false",
                "feature_rules_digest": "digest",
            }
        ],
    )
    (run_dir / "regime_summary.json").write_text(json.dumps({
        "run_id": "regime",
        "label_count": 1,
        "lineage_status": "PASS",
        "healthcheck": {"status": "PASS", "message": "ok"},
    }), encoding="utf-8")
    return run_dir


def _base_args(tmp_path: Path, *, sample_count: int = 40) -> dict:
    return {
        "run_id": "gate_b_chain",
        "gate_b_run_dir": str(_gate_b_run_dir(tmp_path, sample_count=sample_count)),
        "horizon_s": 60,
        "round_trip_cost_bps": 5.0,
        "k_trials": 12,
        "order_notional_usdt": 10.0,
        "candidate_id": "listing_fade",
        "regime_by_date_json": None,
        "default_regime": "chop",
        "oos_start_date": None,
        "allow_slow_capture": False,
        "include_default_pbo_grid": False,
        "pbo_grid_json": None,
        "maker_fee_bps": 2.0,
        "taker_fee_bps": 5.5,
        "evidence_source_tier": "calibrated_replay",
        "order_style": "taker",
        "slippage_floor_bps": 0.5,
        "capacity_window_s": 60,
        "fnd2_run_dir": None,
        "regime_run_dir": None,
        "asof": None,
        "window_start": None,
        "window_end": None,
        "artifact_root": str(tmp_path / "out"),
        "session_id": None,
        "created_by_role": "PM",
    }


def _pbo_grid_json(tmp_path: Path) -> Path:
    path = tmp_path / "listing_pbo_grid.json"
    path.write_text(json.dumps({
        "cells": [
            {"horizon_s": 60, "cost_bps": float(cost), "parameter_cell_id": f"h60_cost{cost}"}
            for cost in range(10)
        ]
    }), encoding="utf-8")
    return path


def test_gate_b_chain_runs_to_execution_realism(tmp_path):
    args = _base_args(tmp_path)
    args["pbo_grid_json"] = str(_pbo_grid_json(tmp_path))
    result = harness_mod.build_and_write(argparse.Namespace(**args))
    summary = result["summary"]

    assert summary["chain_status"] == "COMPLETE_EXECUTION_REALISM_PASS"
    assert summary["gate_snapshot"]["listing_sample_count"] == 40
    assert summary["gate_snapshot"]["listing_pbo_status"] == "produced_candidate_grid"
    assert summary["gate_snapshot"]["execution_observation_count"] == 40
    assert summary["gate_snapshot"]["execution_realism_status"] == "PASS"
    assert Path(summary["outputs"]["candidate_evidence_json"]).exists()
    assert Path(summary["outputs"]["execution_observations_jsonl"]).exists()
    assert Path(summary["outputs"]["execution_realism_json"]).exists()
    assert Path(result["written"]["summary"]).exists()


def test_gate_b_chain_runs_full_formal_matrix_when_inputs_are_provided(tmp_path):
    args = _base_args(tmp_path)
    args["pbo_grid_json"] = str(_pbo_grid_json(tmp_path))
    args["fnd2_run_dir"] = str(_fnd2_dir(tmp_path))
    args["regime_run_dir"] = str(_regime_dir(tmp_path))

    result = harness_mod.build_and_write(argparse.Namespace(**args))
    summary = result["summary"]

    assert summary["chain_status"] == "COMPLETE_MATRIX_NON_PROMOTABLE"
    assert summary["outputs"]["event_breadth_run_dir"] is not None
    assert summary["outputs"]["formal_matrix_run_dir"] is not None
    assert summary["gate_snapshot"]["listing_pbo_status"] == "produced_candidate_grid"
    assert summary["gate_snapshot"]["execution_realism_status"] == "PASS"
    assert result["candidate_rows"]["summary"]["pbo_status"] == "measured"
    assert result["matrix"]["summary"]["coverage_gate_status"] == "PASS"
    assert result["matrix"]["summary"]["survivorship_mode"] == "pit_fnd2_proven_none"
    assert result["matrix"]["summary"]["final_label_counts"]


def test_gate_b_chain_requires_both_matrix_inputs(tmp_path):
    args = _base_args(tmp_path)
    args["fnd2_run_dir"] = str(_fnd2_dir(tmp_path))
    with pytest.raises(ValueError, match="formal_matrix_requires_both"):
        harness_mod.build_and_write(argparse.Namespace(**args))


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_gate_b_chain"
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

"""Tests for the AEG-S3 Gate-B preflight locator."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aeg_s3_gate_b_preflight import harness as harness_mod


def _ms(idx: int) -> int:
    ts = datetime(2026, 3, 1, tzinfo=timezone.utc) + timedelta(days=idx)
    return int(ts.timestamp() * 1000)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _gate_b_run(root: Path, *, sample_count: int) -> Path:
    run_dir = root / "listing_24h_synthetic"
    run_dir.mkdir(parents=True)
    capture_rows = []
    markout_rows = []
    publictrade_rows = []
    for idx in range(sample_count):
        ts_ms = _ms(idx)
        symbol = f"NEW{idx:03d}USDT"
        capture_rows.append({
            "kind": "capture_lag",
            "symbol": symbol,
            "launch_time_ms": ts_ms - 1000,
            "first_trade_event_ts_ms": ts_ms,
            "first_trade_ingest_ts_local_ms": ts_ms + 80,
            "capture_lag_ms": 1000,
            "verdict": "PASS_CAPTURE",
        })
        for horizon_s in (30, 60, 300):
            markout_rows.append({
                "kind": "markout_fill",
                "symbol": symbol,
                "trigger_event_ts_ms": ts_ms,
                "filled_event_ts_ms": ts_ms + horizon_s * 1000,
                "horizon_s": horizon_s,
                "mid_at_trigger": 1.0,
                "mid_at_horizon": 0.997,
                "markout_bps": -30.0,
            })
        publictrade_rows.append({
            "kind": "public_trade",
            "symbol": symbol,
            "event_ts_exchange_ms": ts_ms,
            "price": 1.0,
            "side": "Buy",
            "size": 500.0,
            "ingest_ts_local_ms": ts_ms + 80,
            "ingest_minus_event_ms": 80,
            "trade_id": f"{symbol}:0",
        })
    _write_jsonl(run_dir / "capture_lag.jsonl", capture_rows)
    _write_jsonl(run_dir / "markout.jsonl", markout_rows)
    _write_jsonl(run_dir / "ws_publictrade.jsonl", publictrade_rows)
    return run_dir


def _fnd2_run(root: Path) -> Path:
    run_dir = root / "fnd2_real"
    run_dir.mkdir(parents=True)
    (run_dir / "universe.csv").write_text("symbol,included\nBTCUSDT,true\n", encoding="utf-8")
    (run_dir / "universe_summary.json").write_text(json.dumps({
        "run_id": "fnd2_real",
        "universe_id": "uid",
        "included_count": 1,
        "survivor_rejection_status": "PROVEN_NONE_IN_WINDOW",
    }), encoding="utf-8")
    return run_dir


def _regime_run(root: Path) -> Path:
    run_dir = root / "regime_real"
    run_dir.mkdir(parents=True)
    (run_dir / "regime_labels.csv").write_text("symbol,main_regime\nBTCUSDT,chop\n", encoding="utf-8")
    (run_dir / "regime_summary.json").write_text(json.dumps({
        "run_id": "regime_real",
        "classifier_version": "aeg_regime_v0.1.0",
        "healthcheck": {"status": "PASS"},
    }), encoding="utf-8")
    return run_dir


def _gate_watch_latest(
    root: Path,
    *,
    status: str = "WATCH_ONLY",
    generated_at: datetime | None = None,
    candidates: list[dict] | None = None,
) -> Path:
    generated_at = generated_at or datetime.now(timezone.utc)
    candidate_counts = {
        "alertable": 0,
        "schedule": 0,
        "start_now": 0,
        "total": len(candidates or []),
        "watch_only": 1 if status == "WATCH_ONLY" else 0,
    }
    for candidate in candidates or []:
        action = candidate.get("recommended_action")
        if action == "START_GATE_B_NOW":
            candidate_counts["start_now"] += 1
            candidate_counts["alertable"] += 1
        elif action == "SCHEDULE_GATE_B_WINDOW":
            candidate_counts["schedule"] += 1
            candidate_counts["alertable"] += 1
        elif action == "OPERATOR_REVIEW":
            candidate_counts["alertable"] += 1
    path = root / "gate_b_watch_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "generated_at_utc": generated_at.isoformat().replace("+00:00", "Z"),
        "status": status,
        "candidate_counts": candidate_counts,
        "alerts_sent": 0,
        "source_health": {
            "announcements": {"ok": True, "count": 1, "error": None},
            "prelaunch": {"ok": True, "count": 0, "error": None},
        },
        "probe_preconditions": ["operator_manual_start", "isolated_run_dir"],
        "boundary": "alert-only; no probe autostart; no trading/runtime/DB mutation",
        "candidates": candidates or [{
            "symbol": "BPUSDT",
            "source": "market_instruments_info",
            "trigger_type": "prelaunch_active",
            "priority": "P2",
            "recommended_action": "WATCH_CONVERSION",
            "action_reason": "old_continuous_prelaunch_age_h=1000.0",
            "should_alert": False,
            "status": "PreLaunch",
            "cur_auction_phase": "ContinuousTrading",
            "launch_time_utc": "2026-03-16T00:00:00Z",
        }],
    }), encoding="utf-8")
    return path


def _actionable_candidate(action: str) -> dict:
    return {
        "symbol": "ABCUSDT",
        "source": "announcements_new_crypto",
        "trigger_type": "announcement_pre_market_listing",
        "priority": "P1",
        "recommended_action": action,
        "action_reason": "synthetic_window",
        "should_alert": True,
        "event_time_utc": "2026-06-13T06:30:00Z",
        "suggested_probe": {
            "suggested_probe_start_utc": "2026-06-13T00:30:00Z",
            "suggested_probe_duration_seconds": 86400,
        },
        "title": "Bybit to List Pre-Market Perpetuals for ABCUSDT",
        "url": "https://announcements.bybit.com/en-US/article/synthetic/",
    }


def _args(
    tmp_path: Path,
    *,
    gate_b_run_dir: Path,
    fnd2_run_dir: Path | None,
    regime_run_dir: Path | None,
    gate_watch_latest_json: Path | None = None,
) -> dict:
    watch_path = gate_watch_latest_json or _gate_watch_latest(tmp_path / "watch")
    return {
        "run_id": "preflight",
        "chain_run_id": None,
        "gate_b_root": None,
        "alpha_history_root": str(tmp_path / "alpha"),
        "artifact_root": str(tmp_path / "out"),
        "gate_b_run_dir": str(gate_b_run_dir),
        "fnd2_run_dir": str(fnd2_run_dir) if fnd2_run_dir else None,
        "regime_run_dir": str(regime_run_dir) if regime_run_dir else None,
        "horizon_s": 60,
        "round_trip_cost_bps": 5.0,
        "k_trials": 12,
        "default_regime": "chop",
        "allow_slow_capture": False,
        "order_notional_usdt": 1.0,
        "slippage_floor_bps": 1.0,
        "no_default_pbo_grid": False,
        "min_listing_samples": 30,
        "gate_watch_latest_json": str(watch_path),
        "gate_watch_max_age_hours": 4.0,
        "session_id": None,
        "created_by_role": "PM",
    }


def test_preflight_ready_builds_full_chain_command(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=35)
    fnd2 = _fnd2_run(tmp_path / "alpha")
    regime = _regime_run(tmp_path / "alpha")

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=regime,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "PASS_READY_FOR_FULL_CHAIN"
    assert summary["listing_preview"]["sample_count"] == 35
    assert summary["listing_preview"]["pbo_status"] == "produced_candidate_grid"
    assert summary["gate_watch"]["artifact_status"] == "WATCH_ONLY"
    assert summary["gate_watch"]["operator_action"] == "WAIT_FOR_ACTIONABLE_WATCH"
    assert "--include-default-pbo-grid" in summary["recommended_command"]["shell"]
    assert "--fnd2-run-dir" in summary["recommended_command"]["argv"]
    assert summary["recommended_command"]["operator_recommended"] is True
    assert summary["recommended_command"]["operator_status"] == "RUNNABLE_FOR_RESEARCH_REVIEW"
    assert Path(result["written"]["summary"]).exists()


def test_preflight_sample_below_gate_is_warn_not_blocked(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=2)
    fnd2 = _fnd2_run(tmp_path / "alpha")
    regime = _regime_run(tmp_path / "alpha")

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=regime,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "READY_BUT_SAMPLE_BELOW_GATE"
    assert summary["listing_preview"]["sample_count"] == 2
    assert summary["recommended_command"]["shell"]
    assert summary["recommended_command"]["operator_recommended"] is False
    assert summary["recommended_command"]["operator_status"] == "HOLD_WAIT_FOR_ACTIONABLE_WATCH"
    assert any(row["status"] == "WARN" for row in summary["checks"])


def test_preflight_actionable_start_watch_builds_probe_hint(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=35)
    fnd2 = _fnd2_run(tmp_path / "alpha")
    regime = _regime_run(tmp_path / "alpha")
    watch = _gate_watch_latest(
        tmp_path / "watch",
        status="ACTIONABLE_START_NOW",
        candidates=[_actionable_candidate("START_GATE_B_NOW")],
    )

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=regime,
        gate_watch_latest_json=watch,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "PASS_READY_FOR_FULL_CHAIN"
    assert summary["gate_watch"]["operator_action"] == "START_ISOLATED_24H_PROBE"
    assert summary["gate_watch"]["probe_command_hints"][0]["symbol"] == "ABCUSDT"
    assert "aeg_gate_b_probe.py" in summary["gate_watch"]["probe_command_hints"][0]["shell"]
    assert summary["recommended_command"]["operator_recommended"] is False
    assert summary["recommended_command"]["operator_status"] == "RUN_ISOLATED_PROBE_BEFORE_FULL_CHAIN"


def test_preflight_actionable_schedule_watch_builds_probe_hint(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=35)
    fnd2 = _fnd2_run(tmp_path / "alpha")
    regime = _regime_run(tmp_path / "alpha")
    watch = _gate_watch_latest(
        tmp_path / "watch",
        status="ACTIONABLE_SCHEDULE",
        candidates=[_actionable_candidate("SCHEDULE_GATE_B_WINDOW")],
    )

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=regime,
        gate_watch_latest_json=watch,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "PASS_READY_FOR_FULL_CHAIN"
    assert summary["gate_watch"]["operator_action"] == "SCHEDULE_ISOLATED_24H_PROBE"
    assert summary["gate_watch"]["candidate_counts"]["schedule"] == 1
    assert summary["recommended_command"]["operator_recommended"] is False
    assert summary["recommended_command"]["operator_status"] == "RUN_ISOLATED_PROBE_BEFORE_FULL_CHAIN"


def test_preflight_blocks_stale_gate_watch_artifact(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=35)
    fnd2 = _fnd2_run(tmp_path / "alpha")
    regime = _regime_run(tmp_path / "alpha")
    stale_time = datetime.now(timezone.utc) - timedelta(hours=6)
    watch = _gate_watch_latest(tmp_path / "watch", generated_at=stale_time)

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=regime,
        gate_watch_latest_json=watch,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "BLOCKED_PRECHECK_FAILED"
    assert summary["gate_watch"]["stale"] is True
    assert summary["recommended_command"]["operator_recommended"] is False
    assert summary["recommended_command"]["operator_status"] == "BLOCKED_PRECHECK_FAILED"
    assert any(row["message"] == "gate_watch_latest_json_stale_or_missing_generated_at" for row in summary["checks"])


def test_preflight_blocks_malformed_gate_watch_artifact(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=35)
    fnd2 = _fnd2_run(tmp_path / "alpha")
    regime = _regime_run(tmp_path / "alpha")
    watch = tmp_path / "watch" / "gate_b_watch_latest.json"
    watch.parent.mkdir(parents=True)
    watch.write_text("{not json", encoding="utf-8")

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=regime,
        gate_watch_latest_json=watch,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "BLOCKED_PRECHECK_FAILED"
    assert summary["gate_watch"]["artifact_status"] == "MALFORMED"
    assert any(row["message"] == "gate_watch_latest_json_malformed" for row in summary["checks"])


def test_preflight_blocks_missing_regime_artifact(tmp_path):
    gate_b = _gate_b_run(tmp_path / "gate_b", sample_count=35)
    fnd2 = _fnd2_run(tmp_path / "alpha")

    result = harness_mod.build_and_write(argparse.Namespace(**_args(
        tmp_path,
        gate_b_run_dir=gate_b,
        fnd2_run_dir=fnd2,
        regime_run_dir=None,
    )))
    summary = result["summary"]

    assert summary["readiness_status"] == "BLOCKED_PRECHECK_FAILED"
    assert summary["selected_artifacts"]["regime_run_dir"] is None
    assert summary["recommended_command"]["shell"] is None
    assert summary["recommended_command"]["operator_recommended"] is False
    assert summary["recommended_command"]["operator_status"] == "UNAVAILABLE"


def test_static_no_runtime_or_db_route():
    pkg = Path(__file__).resolve().parents[1] / "aeg_s3_gate_b_preflight"
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

"""Tests for cost-gate demo learning-lane policy artifacts."""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path
import subprocess

from alpha_discovery_throughput.discovery_loop import build_discovery_plan
from alpha_discovery_throughput.runtime_runner import collect_cost_gate_learning_lane_arm
from cost_gate_learning_lane.policy import (
    DEMO_LEARNING_LANE_SCHEMA_VERSION,
    LearningLanePolicyConfig,
    build_plan_from_file,
    build_plan_from_payload,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
    read_price_observations,
)
from cost_gate_learning_lane.outcome_refresh import (
    OutcomeRefreshSelection,
    build_cost_gate_outcome_refresh_batch,
    build_price_rows_from_pg_for_refresh,
    refresh_cost_gate_outcomes_from_price_rows,
)
from cost_gate_learning_lane.outcome_review import (
    BlockedOutcomeReviewConfig,
    build_blocked_signal_outcome_review,
)
from cost_gate_learning_lane.status import (
    ACTIVATION_PREFLIGHT_SCHEMA_VERSION,
    REQUIRED_SOURCE_RELATIVE_PATHS,
    build_cost_gate_learning_lane_activation_preflight,
    summarize_cost_gate_learning_lane_writer_config,
    summarize_cost_gate_learning_lane_source,
)
from cost_gate_learning_lane.price_observations import (
    PriceObservationBuildConfig,
    build_price_observation_artifact,
    build_market_klines_observation_sql,
    build_price_observations_from_rows,
    fetch_market_kline_price_rows,
    required_price_observation_windows,
    write_price_observation_artifact,
)
from cost_gate_learning_lane.runtime_adapter import (
    ADMIT_DECISION,
    ORDER_AUTHORITY_GRANTED,
    RuntimeAdmissionConfig,
    build_ledger_record,
    evaluate_probe_admission,
    normalize_reject_reason_code,
    read_jsonl_ledger,
    append_jsonl_ledger,
)


def _scorecard_payload(generated_at: str = "2026-06-21T10:00:00+00:00") -> dict:
    rows = [
        {
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 486,
            "avg_gross_bps": 101.9788,
            "p50_gross_bps": 49.421,
            "p90_gross_bps": 211.0,
            "avg_net_bps": 97.9788,
            "gross_positive_pct": 90.0,
            "net_positive_pct": 86.01,
            "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
            "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
        },
        {
            "strategy_name": "ma_crossover",
            "symbol": "NEARUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 244,
            "avg_gross_bps": 20.2197,
            "p50_gross_bps": 13.2,
            "p90_gross_bps": 31.0,
            "avg_net_bps": 16.2197,
            "gross_positive_pct": 100.0,
            "net_positive_pct": 99.95,
            "learning_lane_action": "LEARNING_PROBE_CANDIDATE",
            "learning_lane_reason": "avg_net_positive_and_median_gross_clears_friction",
        },
        {
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Buy",
            "reject_reason_code": "cost_gate_js_demo_negative_edge",
            "n": 300,
            "avg_gross_bps": -31.7434,
            "p50_gross_bps": -29.6769,
            "p90_gross_bps": -2.0,
            "avg_net_bps": -35.7434,
            "gross_positive_pct": 2.0,
            "net_positive_pct": 0.0,
            "learning_lane_action": "BLOCK_CONFIRMED",
            "learning_lane_reason": "avg_net_nonpositive_and_low_net_positive_rate",
        },
        {
            "strategy_name": "grid_trading",
            "symbol": "OPUSDT",
            "side": "Sell",
            "reject_reason_code": "cost_gate_atr_unavailable",
            "n": 500,
            "avg_gross_bps": 8.0,
            "p50_gross_bps": 6.0,
            "p90_gross_bps": 20.0,
            "avg_net_bps": 4.0,
            "gross_positive_pct": 70.0,
            "net_positive_pct": 60.0,
            "learning_lane_action": "DATA_COVERAGE_BLOCKER",
            "learning_lane_reason": "reject_reason_requires_data_fix_not_probe",
        },
    ]
    return {
        "generated_at_utc": generated_at,
        "coverage": {"decision_features": 1000, "features_joined_outcomes": 0},
        "learning_lane_scorecard": {
            "schema_version": "cost_gate_reject_counterfactual_v2",
            "status": "LEARNING_LANE_PROBE_CANDIDATES_PRESENT",
            "outcome_path_status": "OUTCOME_PATH_STALLED_FOR_FEATURE_REJECTS",
            "action_counts": {
                "LEARNING_PROBE_CANDIDATE": 2,
                "BLOCK_CONFIRMED": 1,
                "DATA_COVERAGE_BLOCKER": 1,
            },
            "probe_candidates": rows[:2],
            "rows": rows,
        },
    }


class _FakeKlineCursor:
    description = [("symbol",), ("ts_ms",), ("close",)]

    def __init__(self, conn):
        self.conn = conn
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params):
        self.conn.executions.append((sql, params))
        self._rows = self.conn.rows_by_symbol.get(params[0], [])

    def fetchall(self):
        return self._rows


class _FakeKlineConn:
    def __init__(self, rows_by_symbol):
        self.rows_by_symbol = rows_by_symbol
        self.executions = []

    def cursor(self):
        return _FakeKlineCursor(self)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )


def _git_output(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        text=True,
        capture_output=True,
    )
    return proc.stdout.strip()


def _write_required_source_files(repo: Path) -> None:
    for rel in REQUIRED_SOURCE_RELATIVE_PATHS:
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".sh":
            path.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            path.chmod(0o755)
        else:
            path.write_text('"""fixture source file."""\n', encoding="utf-8")


def _init_source_repo_with_origin(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    repo = tmp_path / "repo"
    remote.mkdir()
    repo.mkdir()
    _git(remote, "init", "--bare")
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test User")
    _write_required_source_files(repo)
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-u", "origin", "main")
    return repo, remote


def test_policy_plan_keeps_main_gate_closed_and_selects_only_probe_candidates():
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=4, max_total_probe_orders=4),
    )

    assert plan["schema_version"] == DEMO_LEARNING_LANE_SCHEMA_VERSION
    assert plan["status"] == "READY_FOR_DEMO_LEARNING_PROBE"
    assert plan["gate_status"] == "OPERATOR_REVIEW"
    assert plan["main_cost_gate_adjustment"] == "NONE"
    assert plan["order_authority"] == "NOT_GRANTED"
    assert plan["learning_gate_adjustment"] == (
        "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING"
    )
    assert [row["side_cell_key"] for row in plan["probe_candidates"]] == [
        "ma_crossover|ETHUSDT|Sell",
        "ma_crossover|NEARUSDT|Sell",
    ]
    assert {row["probe_proposal"]["mode"] for row in plan["probe_candidates"]} == {
        "demo_only_learning_probe"
    }
    assert all(
        row["guardrails"]["main_cost_gate_adjustment"] == "NONE"
        for row in plan["probe_candidates"]
    )
    assert plan["do_not_probe_side_cells"][0]["side_cell_key"] == (
        "ma_crossover|BTCUSDT|Buy"
    )
    assert plan["data_coverage_tasks"][0]["side_cell_key"] == "grid_trading|OPUSDT|Sell"


def test_policy_plan_waits_on_stale_scorecard(tmp_path: Path):
    path = tmp_path / "scorecard.json"
    path.write_text(json.dumps(_scorecard_payload("2026-06-20T00:00:00+00:00")), encoding="utf-8")

    plan = build_plan_from_file(
        path,
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_scorecard_age_hours=6),
    )

    assert plan["status"] == "WAIT_FOR_SCORECARD_REFRESH"
    assert plan["gate_status"] == "WAIT"
    assert plan["source"]["source_error"] == "stale_scorecard"
    assert plan["selected_probe_candidate_count"] == 0
    assert plan["probe_candidates"] == []
    assert plan["main_cost_gate_adjustment"] == "NONE"


def test_policy_plan_waits_on_future_scorecard_timestamp():
    plan = build_plan_from_payload(
        _scorecard_payload("2026-06-21T12:00:01+00:00"),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )

    assert plan["status"] == "WAIT_FOR_SCORECARD_REFRESH"
    assert plan["gate_status"] == "WAIT"
    assert plan["source"]["source_error"] == "future_scorecard_generated_at"
    assert plan["selected_probe_candidate_count"] == 0
    assert plan["probe_candidates"] == []
    assert plan["main_cost_gate_adjustment"] == "NONE"


def test_alpha_discovery_does_not_mark_cost_gate_plan_ready_without_runtime_ledger(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    plan_path = data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    scorecard = discovery["profitability_blocker_scorecard"]
    row = scorecard["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_learning_loop_not_seen"
    assert scorecard["status"] == "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    assert row["arm_id"] == "cost_gate_demo_learning_lane"
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == "cost_gate_learning_loop_not_running"
    assert row["next_trigger"] == (
        "sync_source_install_learning_lane_cron_enable_runtime_writer_then_observe_reject_rows"
    )
    assert row["operator_actionable"] is False
    assert row["engineering_actionable"] is True
    assert row["main_cost_gate_adjustment"] == "NONE"
    assert row["order_authority"] == "NOT_GRANTED"
    assert row["ledger_status"] == "MISSING"
    assert row["learning_loop_status"] == "NOT_SEEN"
    assert row["learning_loop_heartbeat_present"] is False
    assert row["admission_decision_count"] == 0
    assert row["probe_candidates"][0]["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"


def test_alpha_discovery_surfaces_learning_loop_running_without_ledger_rows(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    heartbeat = data_dir / "cron_heartbeat" / "cost_gate_learning_lane.last_fire"
    heartbeat.parent.mkdir(parents=True)
    heartbeat.write_text("", encoding="utf-8")
    heartbeat_ts = dt.datetime(2026, 6, 21, 11, 4, tzinfo=dt.timezone.utc).timestamp()
    os.utime(heartbeat, (heartbeat_ts, heartbeat_ts))
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "check": "cost_gate_learning_lane",
            "ledger_row_count": 0,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
            "review_next_trigger": (
                "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
            ),
        })
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_learning_loop_running_no_ledger_rows"
    assert row["primary_blocker"] == "cost_gate_learning_loop_running_but_no_reject_rows"
    assert row["next_trigger"] == (
        "verify_runtime_ledger_writer_enabled_or_wait_for_cost_gate_rejects"
    )
    assert row["ledger_status"] == "MISSING"
    assert row["learning_loop_status"] == "RUNNING_NO_LEDGER_ROWS"
    assert row["learning_loop_heartbeat_present"] is True
    assert row["learning_loop_last_ledger_row_count"] == 0
    assert row["learning_loop_last_review_status"] == "NO_BLOCKED_SIGNAL_OUTCOMES"


def test_activation_preflight_reports_not_accumulating_without_runtime_artifacts(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["schema_version"] == ACTIVATION_PREFLIGHT_SCHEMA_VERSION
    assert preflight["status"] == "NOT_ACCUMULATING"
    assert preflight["reason"] == "plan_present_but_writer_cron_or_ledger_not_observed"
    assert preflight["answers"]["has_accumulated_ledger_rows"] is False
    assert preflight["answers"]["currently_accumulating_evidence"] is False
    assert preflight["answers"]["cost_gate_rejects_recorded"] is False
    assert preflight["answers"]["silent_drop_risk"] is True
    assert preflight["ledger"]["ledger_status"] == "MISSING"
    assert preflight["learning_loop"]["learning_loop_status"] == "NOT_SEEN"
    assert preflight["plan"]["main_cost_gate_adjustment"] == "NONE"
    assert preflight["plan"]["order_authority"] == "NOT_GRANTED"
    assert "probe_ledger_jsonl" in preflight["missing_links"]


def test_writer_config_reports_enabled_env_file_paths(tmp_path: Path):
    data_dir = tmp_path / "data"
    plan_path = tmp_path / "runtime_plan.json"
    ledger_path = tmp_path / "runtime_ledger.jsonl"
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "\n".join(
            [
                'export OPENCLAW_DEMO_LEARNING_LANE_WRITER="true"',
                f"OPENCLAW_DEMO_LEARNING_LANE_PLAN={plan_path}",
                f"OPENCLAW_DEMO_LEARNING_LANE_LEDGER='{ledger_path}'",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    config = summarize_cost_gate_learning_lane_writer_config(
        data_dir,
        env_file=env_file,
        require_writer_enabled=True,
    )

    assert config["writer_config_status"] == "ENABLED"
    assert config["writer_enabled"] is True
    assert config["writer_required_for_activation"] is True
    assert config["writer_env_source"] == "env_file"
    assert config["plan_path"] == str(plan_path)
    assert config["plan_path_source"] == "env_override"
    assert config["ledger_path"] == str(ledger_path)
    assert config["ledger_path_source"] == "env_override"


def test_writer_config_reports_invalid_enable_value(tmp_path: Path):
    config = summarize_cost_gate_learning_lane_writer_config(
        tmp_path,
        env={"OPENCLAW_DEMO_LEARNING_LANE_WRITER": "maybe"},
    )

    assert config["writer_config_status"] == "INVALID"
    assert config["writer_enabled"] is None
    assert config["writer_bool_error"] == "invalid_bool"


def test_activation_preflight_can_require_runtime_writer_enabled(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER=0\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        runtime_env_file=env_file,
        require_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["writer_config"]["writer_config_status"] == "DISABLED"
    assert preflight["answers"]["runtime_writer_enabled"] is False
    assert preflight["answers"]["runtime_writer_config_required"] is True
    assert preflight["answers"]["writer_disabled_or_unset_drop_risk"] is True
    assert "runtime_writer_not_enabled" in preflight["activation_blockers"]
    assert preflight["answers"]["activation_ready"] is False


def test_activation_preflight_accepts_runtime_writer_enabled_env_file(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    data_dir = tmp_path / "data"
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    env_file = tmp_path / "runtime.env"
    env_file.write_text(
        "OPENCLAW_DEMO_LEARNING_LANE_WRITER=1\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        runtime_env_file=env_file,
        require_writer_enabled=True,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["writer_config"]["writer_config_status"] == "ENABLED"
    assert preflight["answers"]["runtime_writer_enabled"] is True
    assert preflight["answers"]["runtime_writer_config_required"] is True
    assert preflight["answers"]["writer_disabled_or_unset_drop_risk"] is False
    assert "runtime_writer_not_enabled" not in preflight["activation_blockers"]


def test_activation_preflight_reports_loop_running_without_ledger_rows(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    heartbeat = data_dir / "cron_heartbeat" / "cost_gate_learning_lane.last_fire"
    heartbeat.parent.mkdir(parents=True)
    heartbeat.write_text("", encoding="utf-8")
    heartbeat_ts = dt.datetime(2026, 6, 21, 11, 4, tzinfo=dt.timezone.utc).timestamp()
    os.utime(heartbeat, (heartbeat_ts, heartbeat_ts))
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "check": "cost_gate_learning_lane",
            "ledger_row_count": 0,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
        })
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "LOOP_RUNNING_NO_LEDGER_ROWS"
    assert preflight["reason"] == "learning_loop_recent_but_no_probe_ledger_rows"
    assert preflight["learning_loop"]["learning_loop_status"] == "RUNNING_NO_LEDGER_ROWS"
    assert preflight["answers"]["silent_drop_risk"] is True
    assert "runtime_ledger_writer_or_recent_cost_gate_reject_rows" in preflight["missing_links"]


def test_activation_preflight_routes_admission_only_ledger_to_outcome_refresh(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    (lane_dir / "probe_ledger.jsonl").write_text(
        json.dumps(
            {
                "record_type": "probe_admission_decision",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
            }
        )
        + "\n",
        encoding="utf-8",
    )
    log = data_dir / "logs" / "cost_gate_learning_lane.log"
    log.parent.mkdir(parents=True)
    log.write_text(
        json.dumps({
            "ts_utc": "2026-06-21T11:04:00Z",
            "ledger_row_count": 1,
            "refresh_rc": 0,
            "review_rc": 0,
            "review_status": "NO_BLOCKED_SIGNAL_OUTCOMES",
        })
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "ADMISSION_ONLY_NEEDS_OUTCOME_REFRESH"
    assert preflight["answers"]["has_accumulated_ledger_rows"] is True
    assert preflight["answers"]["currently_accumulating_evidence"] is True
    assert preflight["answers"]["cost_gate_rejects_recorded"] is True
    assert preflight["answers"]["silent_drop_risk"] is False
    assert preflight["ledger"]["ledger_status"] == "ADMISSION_ROWS_PRESENT"
    assert preflight["next_actions"] == [
        "run_cost_gate_outcome_refresh_for_blocked_signal_outcomes"
    ]


def test_activation_preflight_routes_capture_error_rows_to_writer_config_fix(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    (lane_dir / "probe_ledger.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
                "record_type": "probe_capture_error",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ADMISSION_NOT_EVALUATED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
                "runtime_state": {"risk_state": "NORMAL"},
                "capture_error": "read plan /tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json failed: missing",
                "reason": "runtime_admission_evaluation_failed",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "CAPTURE_ERRORS_NEED_OPERATOR_FIX"
    assert preflight["reason"] == "rejects_captured_but_admission_evaluation_failed"
    assert preflight["answers"]["has_accumulated_ledger_rows"] is True
    assert preflight["answers"]["cost_gate_rejects_recorded"] is True
    assert preflight["answers"]["admission_evaluation_errors_recorded"] is True
    assert preflight["answers"]["silent_drop_risk"] is False
    assert preflight["ledger"]["ledger_status"] == "CAPTURE_ERRORS_PRESENT"
    assert preflight["ledger"]["capture_error_count"] == 1
    assert preflight["ledger"]["captured_reject_count"] == 1
    assert preflight["ledger"]["latest_admission_decision"] == "ADMISSION_NOT_EVALUATED"
    assert "read plan" in preflight["ledger"]["latest_capture_error"]
    assert "demo_learning_lane_plan_or_writer_config" in preflight["missing_links"]


def test_activation_preflight_surfaces_blocked_outcome_review_candidate(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    ledger_rows = [
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T12:15:00+00:00",
            "attempt_id": "blocked-1",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "realized_net_bps": 12.5,
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T13:15:00+00:00",
            "attempt_id": "blocked-2",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "realized_net_bps": 4.0,
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T14:15:00+00:00",
            "attempt_id": "blocked-3",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "realized_net_bps": -1.0,
        },
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "REVIEW_CANDIDATE_OPERATOR_REVIEW"
    assert preflight["answers"]["blocked_signal_outcomes_recorded"] is True
    assert preflight["answers"]["blocked_signal_profitability_review_available"] is True
    assert preflight["ledger"]["blocked_signal_outcome_review_status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    )
    assert preflight["next_actions"] == [
        "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    ]


def test_activation_preflight_fails_closed_when_source_files_missing(
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo_root,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["status"] == "SOURCE_NOT_READY"
    assert preflight["source"]["source_ready"] is False
    assert preflight["source"]["source_status"] == "MISSING_FILES"
    assert "source_sync" in preflight["missing_links"]


def test_source_summary_blocks_activation_when_checkout_dirty(tmp_path: Path):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    dirty_path = repo / "helper_scripts/research/cost_gate_learning_lane/status.py"
    dirty_path.write_text('"""dirty fixture source file."""\n', encoding="utf-8")

    source = summarize_cost_gate_learning_lane_source(repo)

    assert source["source_status"] == "READY"
    assert source["source_ready"] is True
    assert source["source_activation_status"] == "DIRTY"
    assert source["source_activation_ready"] is False
    assert source["git_status"] == "DIRTY"
    assert source["git_dirty_path_count"] == 1
    assert source["git_behind_count"] == 0


def test_source_summary_blocks_activation_when_checkout_behind_upstream(
    tmp_path: Path,
):
    repo, remote = _init_source_repo_with_origin(tmp_path)
    other = tmp_path / "other"
    subprocess.run(
        ["git", "clone", "--branch", "main", str(remote), str(other)],
        check=True,
        text=True,
        capture_output=True,
    )
    _git(other, "config", "user.email", "test@example.invalid")
    _git(other, "config", "user.name", "Test User")
    extra = other / "extra.txt"
    extra.write_text("new upstream commit\n", encoding="utf-8")
    _git(other, "add", "extra.txt")
    _git(other, "commit", "-m", "upstream")
    _git(other, "push", "origin", "main")
    _git(repo, "fetch", "origin")

    source = summarize_cost_gate_learning_lane_source(repo)

    assert source["source_status"] == "READY"
    assert source["source_ready"] is True
    assert source["source_activation_status"] == "BEHIND_UPSTREAM"
    assert source["source_activation_ready"] is False
    assert source["git_status"] == "BEHIND_UPSTREAM"
    assert source["git_ahead_count"] == 0
    assert source["git_behind_count"] == 1


def test_source_summary_honors_expected_head_when_checkout_matches(
    tmp_path: Path,
):
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    head = _git_output(repo, "rev-parse", "HEAD")

    source = summarize_cost_gate_learning_lane_source(repo, expected_head=head[:12])

    assert source["source_status"] == "READY"
    assert source["source_activation_status"] == "SYNCED_CLEAN"
    assert source["source_activation_ready"] is True
    assert source["git_status"] == "SYNCED_CLEAN"
    assert source["expected_head_status"] == "MATCH"
    assert source["expected_head_matches"] is True


def test_source_summary_blocks_activation_when_expected_head_mismatches(
    tmp_path: Path,
):
    repo, _remote = _init_source_repo_with_origin(tmp_path)

    source = summarize_cost_gate_learning_lane_source(
        repo,
        expected_head="deadbee",
    )

    assert source["source_status"] == "READY"
    assert source["source_activation_status"] == "EXPECTED_HEAD_MISMATCH"
    assert source["source_activation_ready"] is False
    assert source["git_status"] == "EXPECTED_HEAD_MISMATCH"
    assert source["expected_head_status"] == "MISMATCH"
    assert source["expected_head_matches"] is False
    assert source["expected_head_error"] == (
        "current_git_head_does_not_match_expected_head"
    )


def test_activation_preflight_reports_expected_head_mismatch_blocker(
    tmp_path: Path,
):
    data_dir = tmp_path / "data"
    repo, _remote = _init_source_repo_with_origin(tmp_path)
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )

    preflight = build_cost_gate_learning_lane_activation_preflight(
        data_dir,
        repo_root=repo,
        expected_head="deadbee",
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )

    assert preflight["source"]["expected_head_status"] == "MISMATCH"
    assert preflight["answers"]["runtime_source_ready_for_activation"] is False
    assert "expected_source_head_mismatch" in preflight["activation_blockers"]
    assert "source_checkout_not_synced_clean" in preflight["activation_blockers"]


def test_alpha_discovery_keeps_stale_cost_gate_plan_as_source_health_blocker(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    plan_path = data_dir / "cost_gate_learning_lane" / "demo_learning_lane_plan_latest.json"
    plan_path.parent.mkdir(parents=True)
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 23, 11, 5, tzinfo=dt.timezone.utc),
        max_age_seconds=60,
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 23, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "BLOCK"
    assert discovery["arms"][0]["reason"] == "source_not_healthy"
    assert row["blocker_class"] == "source_health"
    assert row["primary_blocker"] == "source_not_healthy:stale_artifact"


def test_alpha_discovery_surfaces_cost_gate_ledger_progress(tmp_path: Path):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    ledger_path = lane_dir / "probe_ledger.jsonl"
    ledger_path.write_text(
        json.dumps(
            {
                "record_type": "probe_admission_decision",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
            }
        )
        + "\n"
        + json.dumps(
            {
                "record_type": "blocked_signal_outcome",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "realized_net_bps": 12.5,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_blocked_outcomes_below_review_gate"
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_WAIT_OR_SAMPLE_GATED"
    )
    assert row["blocker_class"] == "sample_gate"
    assert row["primary_blocker"] == "cost_gate_blocked_signal_outcomes_accumulating"
    assert row["next_trigger"] == (
        "continue_recording_and_refreshing_blocked_signal_outcomes"
    )
    assert row["ledger_status"] == "BLOCKED_SIGNAL_OUTCOMES_PRESENT"
    assert row["admission_decision_count"] == 1
    assert row["order_authority_not_granted_count"] == 1
    assert row["blocked_signal_outcome_count"] == 1
    assert row["blocked_signal_positive_outcome_count"] == 1
    assert row["avg_blocked_signal_outcome_net_bps"] == 12.5
    assert row["blocked_signal_net_positive_pct"] == 100.0
    assert row["blocked_signal_outcome_review_status"] == (
        "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    )
    assert row["blocked_signal_outcome_review"]["review_candidate_side_cell_count"] == 0


def test_alpha_discovery_surfaces_cost_gate_capture_errors(tmp_path: Path):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    (lane_dir / "probe_ledger.jsonl").write_text(
        json.dumps(
            {
                "schema_version": "cost_gate_demo_learning_lane_adapter_v1",
                "record_type": "probe_capture_error",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ADMISSION_NOT_EVALUATED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
                "runtime_state": {"risk_state": "NORMAL"},
                "capture_error": "parse plan /tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json failed: expected value",
                "reason": "runtime_admission_evaluation_failed",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_capture_errors_present"
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == (
        "cost_gate_rejects_captured_but_admission_not_evaluated"
    )
    assert row["next_trigger"] == "inspect_demo_learning_lane_plan_and_writer_config"
    assert row["ledger_status"] == "CAPTURE_ERRORS_PRESENT"
    assert row["capture_error_count"] == 1
    assert row["captured_reject_count"] == 1
    assert "parse plan" in row["latest_capture_error"]


def test_alpha_discovery_routes_positive_blocked_outcome_review_candidate(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    ledger_rows = [
        {
            "record_type": "probe_admission_decision",
            "generated_at_utc": "2026-06-21T11:02:00+00:00",
            "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-admission",
            "decision": "ORDER_AUTHORITY_NOT_GRANTED",
            "allowed_to_submit_order": False,
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "event": _selected_reject_event(),
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T12:15:00+00:00",
            "attempt_id": "blocked-1",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
            "realized_net_bps": 12.5,
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T13:15:00+00:00",
            "attempt_id": "blocked-2",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
            "realized_net_bps": 4.0,
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T14:15:00+00:00",
            "attempt_id": "blocked-3",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "source_admission_decision": "ORDER_AUTHORITY_NOT_GRANTED",
            "realized_net_bps": -1.0,
        },
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "READY_FOR_PROBE"
    assert discovery["arms"][0]["reason"] == "cost_gate_blocked_outcome_review_candidate"
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "ACTIONABLE_PROBE_READY"
    )
    assert row["blocker_class"] == "probe_ready"
    assert row["primary_blocker"] == (
        "cost_gate_blocked_signal_outcomes_need_demo_probe_authority_review"
    )
    assert row["next_trigger"] == (
        "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    )
    assert row["blocked_signal_outcome_review_status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    )
    assert row["blocked_signal_outcome_review"]["review_candidate_side_cell_count"] == 1
    assert row["blocked_signal_outcome_review"]["top_side_cells"][0]["status"] == (
        "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    )


def test_alpha_discovery_blocks_when_blocked_outcome_review_fails_thresholds(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    ledger_rows = [
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T12:15:00+00:00",
            "attempt_id": "blocked-1",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "realized_net_bps": -3.0,
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T13:15:00+00:00",
            "attempt_id": "blocked-2",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "realized_net_bps": -1.0,
        },
        {
            "record_type": "blocked_signal_outcome",
            "generated_at_utc": "2026-06-21T14:15:00+00:00",
            "attempt_id": "blocked-3",
            "side_cell_key": "ma_crossover|ETHUSDT|Sell",
            "strategy_name": "ma_crossover",
            "symbol": "ETHUSDT",
            "side": "Sell",
            "realized_net_bps": 0.5,
        },
    ]
    (lane_dir / "probe_ledger.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in ledger_rows),
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "BLOCK"
    assert discovery["arms"][0]["reason"] == (
        "cost_gate_blocked_outcomes_confirm_current_block"
    )
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    )
    assert row["blocker_class"] == "rejected_no_edge"
    assert row["primary_blocker"] == (
        "cost_gate_blocked_signal_outcomes_confirm_current_block"
    )
    assert row["next_trigger"] == "keep_cost_gate_blocked_for_reviewed_side_cells"
    assert row["operator_actionable"] is False
    assert row["engineering_actionable"] is False
    assert row["blocked_signal_outcome_review_status"] == (
        "NO_DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    )


def test_alpha_discovery_routes_admission_only_ledger_to_price_observation_builder(
    tmp_path: Path,
):
    data_dir = tmp_path
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
    )
    lane_dir = data_dir / "cost_gate_learning_lane"
    lane_dir.mkdir(parents=True)
    (lane_dir / "demo_learning_lane_plan_latest.json").write_text(
        json.dumps(plan),
        encoding="utf-8",
    )
    (lane_dir / "probe_ledger.jsonl").write_text(
        json.dumps(
            {
                "record_type": "probe_admission_decision",
                "generated_at_utc": "2026-06-21T11:02:00+00:00",
                "attempt_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
                "decision": "ORDER_AUTHORITY_NOT_GRANTED",
                "allowed_to_submit_order": False,
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "event": _selected_reject_event(),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    arm = collect_cost_gate_learning_lane_arm(
        data_dir,
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    discovery = build_discovery_plan(
        [arm],
        now_utc=dt.datetime(2026, 6, 21, 11, 5, tzinfo=dt.timezone.utc),
    )
    row = discovery["profitability_blocker_scorecard"]["arms"][0]

    assert discovery["arms"][0]["action"] == "RUN_READ_ONLY_CAPTURE"
    assert discovery["arms"][0]["reason"] == "cost_gate_admission_rows_without_refresh_loop"
    assert discovery["profitability_blocker_scorecard"]["status"] == (
        "NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED"
    )
    assert row["blocker_class"] == "data_coverage"
    assert row["primary_blocker"] == (
        "cost_gate_rejects_recorded_but_outcome_refresh_loop_not_running"
    )
    assert row["next_trigger"] == (
        "install_learning_lane_cron_or_run_outcome_refresh"
    )
    assert row["ledger_status"] == "ADMISSION_ROWS_PRESENT"
    assert row["admission_decision_count"] == 1
    assert row["blocked_signal_outcome_count"] == 0


def _selected_reject_event() -> dict:
    return {
        "strategy_name": "ma_crossover",
        "symbol": "ETHUSDT",
        "side": "Sell",
        "reject_reason_code": "cost_gate_js_demo_negative_edge",
        "engine_mode": "live_demo",
        "ts_ms": 1_782_037_200_000,
        "context_id": "ctx-demo-ma_crossover-ETHUSDT-1782037200000",
        "signal_id": "sig-demo-ma_crossover-ETHUSDT-1782037200000",
    }


def _runtime_plan(*, order_authority: str = "NOT_GRANTED") -> dict:
    plan = build_plan_from_payload(
        _scorecard_payload(),
        now_utc=dt.datetime(2026, 6, 21, 11, tzinfo=dt.timezone.utc),
        cfg=LearningLanePolicyConfig(max_probe_side_cells=2, max_total_probe_orders=4),
    )
    plan["order_authority"] = order_authority
    return plan


def test_runtime_adapter_matches_candidate_but_keeps_current_plan_no_order_authority():
    decision = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert decision["allowed_to_submit_order"] is False
    assert decision["no_order_authority"] is True
    assert decision["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert decision["runtime_state"]["remaining_probe_orders"] == 2
    assert decision["plan_summary"]["main_cost_gate_adjustment"] == "NONE"
    assert decision["reason"] == "plan_matches_candidate_but_artifact_has_no_order_authority"


def test_runtime_adapter_admits_only_when_plan_and_adapter_explicitly_authorize():
    decision = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == ADMIT_DECISION
    assert decision["allowed_to_submit_order"] is True
    assert decision["no_order_authority"] is False


def test_runtime_adapter_rejects_future_plan_timestamp():
    plan = _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED)
    plan["generated_at_utc"] = "2026-06-21T12:00:01+00:00"

    decision = evaluate_probe_admission(
        plan,
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )

    assert decision["decision"] == "PLAN_STALE_OR_MISSING_GENERATED_AT"
    assert decision["allowed_to_submit_order"] is False
    assert decision["reason"] == "plan_generated_at_missing_or_too_old"


def test_runtime_adapter_blocks_unselected_side_cell_and_non_negative_cost_gate_reason():
    plan = _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED)
    unselected = {
        **_selected_reject_event(),
        "symbol": "BTCUSDT",
        "side": "Buy",
    }
    not_cost_gate_negative = {
        **_selected_reject_event(),
        "reject_reason_code": "cost_gate_atr_unavailable",
    }

    assert evaluate_probe_admission(
        plan,
        unselected,
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )["decision"] == "SIDE_CELL_NOT_SELECTED"
    assert evaluate_probe_admission(
        plan,
        not_cost_gate_negative,
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )["decision"] == "REJECT_REASON_NOT_ELIGIBLE"


def test_runtime_adapter_enforces_budget_cooldown_and_failed_outcome_disable():
    plan = _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED)
    event = _selected_reject_event()
    prior_admit = {
        "record_type": "probe_admission_decision",
        "decision": ADMIT_DECISION,
        "side_cell_key": "ma_crossover|ETHUSDT|Sell",
        "ts_ms": 1_782_039_600_000,
    }
    now = dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc)

    cooldown = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=[prior_admit],
        now_utc=now,
        adapter_enabled=True,
    )
    assert cooldown["decision"] == "COOLDOWN_ACTIVE"

    exhausted = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=[
            {**prior_admit, "ts_ms": 1_782_033_000_000},
            {**prior_admit, "ts_ms": 1_782_034_000_000},
        ],
        now_utc=now,
        adapter_enabled=True,
    )
    assert exhausted["decision"] == "PROBE_BUDGET_EXHAUSTED"

    failed_outcomes = evaluate_probe_admission(
        plan,
        event,
        ledger_rows=[
            {
                "record_type": "probe_outcome",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "realized_net_bps": -8.0,
            },
            {
                "record_type": "probe_outcome",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "realized_net_bps": -3.0,
            },
        ],
        now_utc=now,
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=2),
        adapter_enabled=True,
    )
    assert failed_outcomes["decision"] == "REALIZED_PROBE_OUTCOMES_FAIL_LEARNING_THRESHOLD"


def test_runtime_adapter_ledger_record_round_trips_jsonl(tmp_path: Path):
    path = tmp_path / "probe_ledger.jsonl"
    decision = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    append_jsonl_ledger(path, build_ledger_record(decision))
    rows = read_jsonl_ledger(path)

    assert len(rows) == 1
    assert rows[0]["record_type"] == "probe_admission_decision"
    assert rows[0]["decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert rows[0]["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"


def test_runtime_adapter_builds_markout_outcome_only_for_admitted_probe():
    admitted = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "last_price": 2000.0,
        },
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(admitted), build_ledger_record(not_granted)]

    outcomes = build_probe_outcome_records(
        ledger,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 1980.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["record_type"] == "probe_outcome"
    assert outcome["attempt_id"] == _selected_reject_event()["context_id"]
    assert outcome["side_cell_key"] == "ma_crossover|ETHUSDT|Sell"
    assert outcome["outcome_source"] == "market_markout_proxy"
    assert outcome["promotion_evidence"] is False
    assert round(outcome["gross_bps"], 6) == 100.0
    assert round(outcome["realized_net_bps"], 6) == 96.0


def test_runtime_adapter_builds_blocked_signal_outcome_for_not_granted_reject():
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]

    outcomes = build_blocked_signal_outcome_records(
        ledger,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )

    assert len(outcomes) == 1
    outcome = outcomes[0]
    assert outcome["record_type"] == "blocked_signal_outcome"
    assert outcome["source_admission_decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert outcome["allowed_to_submit_order"] is False
    assert outcome["outcome_source"] == "market_markout_proxy_for_blocked_signal"
    assert outcome["promotion_evidence"] is False
    assert round(outcome["gross_bps"], 6) == -50.0
    assert round(outcome["realized_net_bps"], 6) == -54.0


def test_price_observation_windows_target_unlabeled_blocked_signals_only():
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]

    windows = required_price_observation_windows(
        ledger,
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )

    assert len(windows) == 1
    window = windows[0]
    assert window["target_outcome_record_type"] == "blocked_signal_outcome"
    assert window["source_admission_decision"] == "ORDER_AUTHORITY_NOT_GRANTED"
    assert window["attempt_id"] == _selected_reject_event()["context_id"]
    assert window["symbol"] == "ETHUSDT"
    assert window["start_ts_ms"] == 1_782_037_200_000
    assert window["exit_target_ts_ms"] == 1_782_040_800_000
    assert window["end_ts_ms"] == 1_782_041_100_000

    completed = {
        "record_type": "blocked_signal_outcome",
        "attempt_id": _selected_reject_event()["context_id"],
    }
    assert required_price_observation_windows(ledger + [completed]) == []


def test_price_observation_builder_filters_rows_and_writes_adapter_compatible_artifact(
    tmp_path: Path,
):
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]
    windows = required_price_observation_windows(
        ledger,
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )
    source_rows = [
        {
            "symbol": "ETHUSDT",
            "open_time_ms": 1_782_037_140_000,
            "close_time_ms": 1_782_037_200_000,
            "close": "2000.0",
        },
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "price": 2010.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "price": 2010.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_041_200_000, "close": 2012.0},
        {"symbol": "BTCUSDT", "ts_ms": 1_782_040_800_000, "close": 100_000.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_000_000},
    ]

    observations = build_price_observations_from_rows(source_rows, windows)

    assert observations == [
        {
            "schema_version": "cost_gate_demo_learning_lane_price_observations_v1",
            "record_type": "price_observation",
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_037_200_000,
            "close": 2000.0,
            "source": "local_price_row",
        },
        {
            "schema_version": "cost_gate_demo_learning_lane_price_observations_v1",
            "record_type": "price_observation",
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_040_800_000,
            "close": 2010.0,
            "source": "local_price_row",
        },
    ]

    artifact = build_price_observation_artifact(
        ledger,
        source_rows,
        now_utc=dt.datetime(2026, 6, 21, 12, 15, tzinfo=dt.timezone.utc),
        cfg=PriceObservationBuildConfig(horizon_minutes=60, max_entry_delay_ms=300_000),
    )
    assert artifact["window_count"] == 1
    assert artifact["observation_count"] == 2
    assert artifact["observations"] == observations

    json_path = tmp_path / "price_observations.json"
    jsonl_path = tmp_path / "price_observations.jsonl"
    write_price_observation_artifact(json_path, artifact)
    write_price_observation_artifact(jsonl_path, artifact)

    assert read_price_observations(json_path) == observations
    assert read_price_observations(jsonl_path) == observations


def test_price_observation_pg_adapter_is_read_only_and_feeds_observation_builder():
    sql = build_market_klines_observation_sql()
    lowered = sql.lower()
    assert "market.klines" in sql
    for token in ("insert", "update", "delete", "alter", "drop"):
        assert token not in lowered

    windows = [
        {
            "symbol": "ETHUSDT",
            "start_ts_ms": 1_782_037_200_000,
            "end_ts_ms": 1_782_041_100_000,
        },
        {
            "symbol": "BTCUSDT",
            "start_ts_ms": 1_782_037_200_000,
            "end_ts_ms": 1_782_037_260_000,
        },
    ]
    conn = _FakeKlineConn(
        {
            "ETHUSDT": [
                ("ETHUSDT", 1_782_037_200_000, 2000.0),
                ("ETHUSDT", 1_782_040_800_000, 2010.0),
            ],
            "BTCUSDT": [("BTCUSDT", 1_782_037_200_000, 100_000.0)],
        }
    )

    rows = fetch_market_kline_price_rows(conn, windows, timeframe="1m")

    assert [params[0] for _sql, params in conn.executions] == ["BTCUSDT", "ETHUSDT"]
    assert all(params[1] == "1m" for _sql, params in conn.executions)
    assert all(params[2].tzinfo == dt.timezone.utc for _sql, params in conn.executions)
    assert rows == [
        {
            "symbol": "BTCUSDT",
            "ts_ms": 1_782_037_200_000,
            "close": 100_000.0,
            "timeframe": "1m",
            "source": "pg_market_klines",
        },
        {
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_037_200_000,
            "close": 2000.0,
            "timeframe": "1m",
            "source": "pg_market_klines",
        },
        {
            "symbol": "ETHUSDT",
            "ts_ms": 1_782_040_800_000,
            "close": 2010.0,
            "timeframe": "1m",
            "source": "pg_market_klines",
        },
    ]

    observations = build_price_observations_from_rows(rows, windows)
    assert observations[0]["source"] == "pg_market_klines"
    assert observations[0]["timeframe"] == "1m"


def test_outcome_refresh_dry_run_append_and_idempotent_blocked_signal_rows(
    tmp_path: Path,
):
    ledger_path = tmp_path / "probe_ledger.jsonl"
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    append_jsonl_ledger(ledger_path, build_ledger_record(not_granted))
    price_rows = [
        {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
        {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
    ]
    selection = OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0)
    now = dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc)

    dry_run = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        append_ledger=False,
    )

    assert dry_run["record_type"] == "cost_gate_outcome_refresh_batch"
    assert dry_run["append_requested"] is False
    assert dry_run["appended_to_ledger"] is False
    assert dry_run["blocked_signal_outcome_count"] == 1
    assert dry_run["outcome_count"] == 1
    assert len(read_jsonl_ledger(ledger_path)) == 1

    appended = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        append_ledger=True,
    )
    rows = read_jsonl_ledger(ledger_path)

    assert appended["append_requested"] is True
    assert appended["appended_to_ledger"] is True
    assert appended["appended_outcome_count"] == 1
    assert len(rows) == 2
    assert rows[1]["record_type"] == "blocked_signal_outcome"
    assert rows[1]["promotion_evidence"] is False
    assert round(rows[1]["realized_net_bps"], 6) == -54.0

    rerun = refresh_cost_gate_outcomes_from_price_rows(
        ledger_path,
        price_rows,
        now_utc=now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        append_ledger=True,
    )
    assert rerun["window_count"] == 0
    assert rerun["outcome_count"] == 0
    assert rerun["appended_outcome_count"] == 0
    assert len(read_jsonl_ledger(ledger_path)) == 2


def test_outcome_refresh_pg_price_rows_feed_batch_without_duplicate_queries():
    not_granted = evaluate_probe_admission(
        _runtime_plan(),
        _selected_reject_event(),
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(not_granted)]
    selection = OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0)
    conn = _FakeKlineConn(
        {
            "ETHUSDT": [
                ("ETHUSDT", 1_782_037_200_000, 2000.0),
                ("ETHUSDT", 1_782_040_800_000, 2010.0),
            ],
        }
    )

    price_rows = build_price_rows_from_pg_for_refresh(
        ledger,
        selection=selection,
        outcome_cfg=outcome_cfg,
        timeframe="1m",
        conn=conn,
    )
    batch = build_cost_gate_outcome_refresh_batch(
        ledger,
        price_rows,
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source="pg_market_klines",
    )

    assert [params[0] for _sql, params in conn.executions] == ["ETHUSDT"]
    assert batch["price_source"] == "pg_market_klines"
    assert batch["price_observation_count"] == 2
    assert batch["blocked_signal_outcome_count"] == 1
    assert batch["observations"][0]["source"] == "pg_market_klines"
    assert batch["observations"][0]["timeframe"] == "1m"

    completed = ledger + [
        {
            "record_type": "blocked_signal_outcome",
            "attempt_id": _selected_reject_event()["context_id"],
        }
    ]
    no_window_conn = _FakeKlineConn({"ETHUSDT": []})
    assert build_price_rows_from_pg_for_refresh(
        completed,
        selection=selection,
        outcome_cfg=outcome_cfg,
        timeframe="1m",
        conn=no_window_conn,
    ) == []
    assert no_window_conn.executions == []


def test_blocked_signal_outcome_review_scorecard_is_conservative():
    scorecard = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "generated_at_utc": "2026-06-21T12:15:00+00:00",
                "attempt_id": "blocked-1",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "realized_net_bps": 12.5,
            },
            {
                "record_type": "blocked_signal_outcome",
                "generated_at_utc": "2026-06-21T13:15:00+00:00",
                "attempt_id": "blocked-2",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "realized_net_bps": 4.0,
            },
            {
                "record_type": "blocked_signal_outcome",
                "generated_at_utc": "2026-06-21T14:15:00+00:00",
                "attempt_id": "blocked-3",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "realized_net_bps": -1.0,
            },
        ],
        now_utc=dt.datetime(2026, 6, 21, 14, 30, tzinfo=dt.timezone.utc),
        cfg=BlockedOutcomeReviewConfig(
            min_outcomes_per_side_cell=3,
            min_avg_net_bps=0.0,
            min_net_positive_pct=60.0,
        ),
    )

    assert scorecard["status"] == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
    assert scorecard["next_trigger"] == (
        "operator_review_blocked_outcome_scorecard_before_demo_probe_authority"
    )
    assert scorecard["review_candidate_side_cell_count"] == 1
    assert scorecard["promotion_evidence"] is False
    assert scorecard["order_authority"] == "NOT_GRANTED"
    side_cell = scorecard["top_side_cells"][0]
    assert side_cell["status"] == "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATE"
    assert side_cell["outcome_count"] == 3
    assert round(side_cell["avg_net_bps"], 6) == 5.166667
    assert round(side_cell["net_positive_pct"], 6) == 66.666667

    insufficient = build_blocked_signal_outcome_review(
        [
            {
                "record_type": "blocked_signal_outcome",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "realized_net_bps": 12.5,
            }
        ],
        cfg=BlockedOutcomeReviewConfig(min_outcomes_per_side_cell=3),
    )
    assert insufficient["status"] == "COLLECT_MORE_BLOCKED_SIGNAL_OUTCOMES"
    assert insufficient["review_candidate_side_cell_count"] == 0


def test_runtime_adapter_outcome_rows_are_idempotent_and_feed_disable():
    admitted = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "last_price": 2000.0,
        },
        now_utc=dt.datetime(2026, 6, 21, 11, 10, tzinfo=dt.timezone.utc),
        adapter_enabled=True,
    )
    ledger = [build_ledger_record(admitted)]
    first_outcome = build_probe_outcome_records(
        ledger,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    assert len(first_outcome) == 1

    duplicate = build_probe_outcome_records(
        ledger + first_outcome,
        [
            {"symbol": "ETHUSDT", "ts_ms": 1_782_037_200_000, "close": 2000.0},
            {"symbol": "ETHUSDT", "ts_ms": 1_782_040_800_000, "close": 2010.0},
        ],
        now_utc=dt.datetime(2026, 6, 21, 12, 11, tzinfo=dt.timezone.utc),
        cfg=ProbeOutcomeConfig(horizon_minutes=60, cost_bps=4.0),
    )
    assert duplicate == []

    disabled = evaluate_probe_admission(
        _runtime_plan(order_authority=ORDER_AUTHORITY_GRANTED),
        {
            **_selected_reject_event(),
            "context_id": "ctx-demo-ma_crossover-ETHUSDT-1782044400000",
            "ts_ms": 1_782_044_400_000,
        },
        ledger_rows=ledger + first_outcome,
        now_utc=dt.datetime(2026, 6, 21, 13, 30, tzinfo=dt.timezone.utc),
        cfg=RuntimeAdmissionConfig(min_failed_outcomes_to_disable=1),
        adapter_enabled=True,
    )
    assert disabled["decision"] == "REALIZED_PROBE_OUTCOMES_FAIL_LEARNING_THRESHOLD"
    assert disabled["runtime_state"]["completed_outcome_count"] == 1


def test_runtime_adapter_normalizes_cost_gate_negative_reason_text():
    assert normalize_reject_reason_code(
        "cost_gate(JS-demo): negative edge -15.2 bps blocked"
    ) == "cost_gate_js_demo_negative_edge"

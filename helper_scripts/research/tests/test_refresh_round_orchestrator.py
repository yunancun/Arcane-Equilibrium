from __future__ import annotations

import datetime as dt
import json

from cost_gate_learning_lane import refresh_round_orchestrator as mod


NOW = dt.datetime(2026, 7, 4, 21, 0, tzinfo=dt.timezone.utc)


def test_round_plan_has_exactly_two_stop_points() -> None:
    plan = mod.build_round_plan(round_id="r1", now_utc=NOW)
    assert plan["round_id"] == "r1"
    assert plan["stop_points"] == [mod.STOP_E3_BB_REVIEW, mod.STOP_OPERATOR_SIGNATURE]
    stops = [s["step"] for s in plan["steps"] if s["stop"] is not None]
    assert stops == ["e3_bb_review", "operator_signature"]
    # 步驟 index 連續、初態全 PENDING。
    assert [s["index"] for s in plan["steps"]] == list(range(len(plan["steps"])))
    assert all(s["state"] == mod.STEP_STATE_PENDING for s in plan["steps"])


def test_non_stop_step_done_is_accepted_and_appended(tmp_path) -> None:
    ledger = tmp_path / "refresh_round_ledger.jsonl"
    result = mod.advance_round(
        round_id="r1",
        step="fetch_origin",
        state=mod.STEP_STATE_DONE,
        ledger_path=ledger,
        now_utc=NOW,
        duration_seconds=1.5,
    )
    assert result["accepted"] is True
    entry = json.loads(ledger.read_text().splitlines()[-1])
    assert entry["step"] == "fetch_origin"
    assert entry["state"] == "DONE"
    assert entry["stop_point"] is None
    assert entry["duration_seconds"] == 1.5


def test_stop_point_cannot_be_marked_done_without_human(tmp_path) -> None:
    ledger = tmp_path / "l.jsonl"
    result = mod.advance_round(
        round_id="r1",
        step="operator_signature",
        state=mod.STEP_STATE_DONE,
        ledger_path=ledger,
        now_utc=NOW,
        human_intervention=False,
    )
    assert result["accepted"] is False
    assert "stop_point_marked_done_without_human_intervention" in result["blocking_reasons"]
    # 仍記一條 FAILED 到 ledger(可審計，不靜默吞)。
    entry = json.loads(ledger.read_text().splitlines()[-1])
    assert entry["state"] == "FAILED"


def test_stop_point_done_with_human_intervention_accepted(tmp_path) -> None:
    ledger = tmp_path / "l.jsonl"
    result = mod.advance_round(
        round_id="r1",
        step="operator_signature",
        state=mod.STEP_STATE_DONE,
        ledger_path=ledger,
        now_utc=NOW,
        human_intervention=True,
        detail="operator typed-confirm at 21:00Z",
    )
    assert result["accepted"] is True
    entry = json.loads(ledger.read_text().splitlines()[-1])
    assert entry["human_intervention"] is True
    assert entry["stop_point"] == mod.STOP_OPERATOR_SIGNATURE


def test_stop_point_awaiting_human_state_accepted(tmp_path) -> None:
    ledger = tmp_path / "l.jsonl"
    result = mod.advance_round(
        round_id="r1",
        step="e3_bb_review",
        state=mod.STEP_STATE_STOP,
        ledger_path=ledger,
        now_utc=NOW,
    )
    assert result["accepted"] is True
    entry = json.loads(ledger.read_text().splitlines()[-1])
    assert entry["state"] == "STOP_AWAITING_HUMAN"
    assert entry["stop_point"] == mod.STOP_E3_BB_REVIEW


def test_unknown_step_rejected(tmp_path) -> None:
    ledger = tmp_path / "l.jsonl"
    result = mod.advance_round(
        round_id="r1",
        step="not_a_real_step",
        state=mod.STEP_STATE_DONE,
        ledger_path=ledger,
        now_utc=NOW,
    )
    assert result["accepted"] is False
    assert any(r.startswith("unknown_step:") for r in result["blocking_reasons"])


def test_dry_run_does_not_write_ledger(tmp_path) -> None:
    ledger = tmp_path / "l.jsonl"
    result = mod.advance_round(
        round_id="r1",
        step="fetch_origin",
        state=mod.STEP_STATE_DONE,
        ledger_path=ledger,
        now_utc=NOW,
        write=False,
    )
    assert result["accepted"] is True
    assert not ledger.exists()

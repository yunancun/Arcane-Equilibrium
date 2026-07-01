from __future__ import annotations

import datetime as dt

from cost_gate_learning_lane import source_stability_window_guard as mod


NOW = dt.datetime(2026, 7, 1, 8, 0, tzinfo=dt.timezone.utc)
PREV = dt.datetime(2026, 7, 1, 7, 58, tzinfo=dt.timezone.utc)
HEAD = "80d40d2cae881c70ab166a7826e7375eb67addef"
NOORDER_BLOCKER_ID = "P0-CURRENT-CANDIDATE-NOORDER-REFRESH-CURRENT-HEAD-E3-BB-REQUEST"


def _state(**overrides) -> dict:
    payload = {
        "collected_at_utc": NOW.isoformat(),
        "repo_root": "/repo",
        "head": HEAD,
        "origin_main": HEAD,
        "status_short_branch": "## main...origin/main",
        "worktree_clean": True,
        "dirty_paths": [],
    }
    payload.update(overrides)
    return payload


def _previous(**overrides) -> dict:
    payload = {
        "schema_version": mod.SCHEMA_VERSION,
        "generated_at_utc": PREV.isoformat(),
        "source_state": _state(collected_at_utc=PREV.isoformat()),
    }
    payload.update(overrides)
    return payload


def test_first_sample_records_no_approval() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        now_utc=NOW,
    )

    assert packet["status"] == mod.SAMPLE_STATUS
    assert packet["active_blocker_id"] == mod.ACTIVE_BLOCKER_ID
    assert packet["answers"]["source_stability_window_ready"] is False
    assert packet["answers"]["approval_granted_by_this_packet"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["max_safe_next_action"] == "RECHECK_SOURCE_AFTER_QUIET_WINDOW_NO_RUNTIME_ACTION"


def test_first_sample_blocks_dirty_source_state() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(worktree_clean=False, dirty_paths=[" M TODO.md"]),
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "worktree_dirty" in packet["blockers"]
    assert packet["answers"]["source_stability_window_ready"] is False
    assert packet["max_safe_next_action"] == "RESOLVE_SOURCE_BLOCKERS_NO_RUNTIME_ACTION"


def test_ready_after_matching_quiet_window() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=_previous(),
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    assert packet["status"] == mod.READY_STATUS
    assert packet["blockers"] == []
    assert packet["quiet_elapsed_seconds"] == 120.0
    assert packet["answers"]["source_stability_window_ready"] is True
    assert packet["max_safe_next_action"] == "REGENERATE_CURRENT_HEAD_E3_BB_REQUEST"


def test_blocks_when_head_drifts_from_previous_sample() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(head="new", origin_main="new"),
        previous_guard=_previous(),
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "previous_source_head_mismatch" in packet["blockers"]
    assert "previous_origin_main_mismatch" in packet["blockers"]
    assert packet["answers"]["source_stability_window_ready"] is False


def test_blocks_dirty_worktree() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(worktree_clean=False, dirty_paths=[" M TODO.md"]),
        previous_guard=_previous(),
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "worktree_dirty" in packet["blockers"]


def test_blocks_dirty_previous_sample() -> None:
    previous = _previous(
        source_state=_state(
            collected_at_utc=PREV.isoformat(),
            worktree_clean=False,
            dirty_paths=[" M TODO.md"],
        )
    )

    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=previous,
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "previous_sample_worktree_dirty" in packet["blockers"]
    assert packet["answers"]["source_stability_window_ready"] is False


def test_blocks_wrong_schema_previous_sample() -> None:
    previous = _previous(schema_version="not_source_stability_window_guard_v1")

    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=previous,
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "previous_guard_schema_mismatch" in packet["blockers"]
    assert packet["answers"]["source_stability_window_ready"] is False


def test_blocks_head_origin_mismatch() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(origin_main="different"),
        previous_guard=_previous(),
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "head_origin_mismatch" in packet["blockers"]


def test_blocks_before_quiet_window_elapsed() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=_previous(),
        min_quiet_seconds=180,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "quiet_window_not_elapsed" in packet["blockers"]


def test_blocks_invalid_min_quiet_seconds() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=_previous(),
        min_quiet_seconds=0,
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "min_quiet_seconds_invalid" in packet["blockers"]
    assert packet["answers"]["source_stability_window_ready"] is False


def test_blocks_required_source_head_mismatch() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=_previous(),
        min_quiet_seconds=60,
        required_source_head="required",
        required_origin_main="required",
        now_utc=NOW,
    )

    assert packet["status"] == mod.BLOCKED_STATUS
    assert "required_source_head_mismatch" in packet["blockers"]
    assert "required_origin_main_mismatch" in packet["blockers"]


def test_all_trading_authority_answers_stay_false_when_ready() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        previous_guard=_previous(),
        min_quiet_seconds=60,
        now_utc=NOW,
    )

    for key, value in packet["answers"].items():
        if key == "source_stability_window_ready":
            assert value is True
        else:
            assert value is False


def test_active_blocker_id_can_bind_noorder_refresh_scope() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        active_blocker_id=NOORDER_BLOCKER_ID,
        now_utc=NOW,
    )

    assert packet["status"] == mod.SAMPLE_STATUS
    assert packet["active_blocker_id"] == NOORDER_BLOCKER_ID
    assert packet["answers"]["approval_granted_by_this_packet"] is False
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["max_safe_next_action"] == "RECHECK_SOURCE_AFTER_QUIET_WINDOW_NO_RUNTIME_ACTION"
    assert f"- Active blocker: `{NOORDER_BLOCKER_ID}`" in mod.render_markdown(packet)


def test_blank_active_blocker_id_falls_back_to_compatibility_default() -> None:
    packet = mod.build_source_stability_window_guard(
        current_source_state=_state(),
        active_blocker_id="  ",
        now_utc=NOW,
    )

    assert packet["active_blocker_id"] == mod.ACTIVE_BLOCKER_ID

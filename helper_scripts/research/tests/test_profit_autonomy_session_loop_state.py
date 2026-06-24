"""Tests for profit-first session-loop anti-repeat checkpoints."""

from __future__ import annotations

import datetime as dt

from profit_autonomy_loop.session_loop_state import (
    build_session_loop_state_packet,
    render_markdown,
)


HEAD = "29cb3dbe6053d86a913bc04ab97e209e4001b646"


def _base_state() -> dict:
    return {
        "session_goal": "Profit-first Demo-learning Autonomy Improvement Loop",
        "active_blocker_id": "P0-PROFIT-EVIDENCE-QUALITY",
        "blocker_goal": "clean order/fill evidence quality",
        "profit_relevance": "bounded demo proof needs reconstructable fills",
        "completed_blockers": [],
        "blocked_blockers": [],
        "previous_report_paths": {
            "P0-PROFIT-EVIDENCE-QUALITY": [
                "docs/CCAgentWorkSpace/PM/workspace/reports/old.md"
            ]
        },
        "source_head": HEAD,
        "runtime_timestamp": "2026-06-24T01:53:48Z",
        "pg_snapshot_timestamp": "2026-06-24T01:53:48Z",
        "artifact_mtimes": {"cost_gate": "2026-06-24T01:45:00Z"},
        "operator_action_required": False,
        "new_evidence_delta_required": True,
        "new_evidence_delta_found": False,
        "acceptance_criteria": "do not repeat without evidence delta",
        "ordered_blockers": [
            "P0-PROFIT-EVIDENCE-QUALITY",
            "P0-PROFIT-CANDIDATE-SELECTION",
            "P1-LEARNING-LOOP-CLOSURE",
        ],
        "previous_evidence_snapshots": {
            "P0-PROFIT-EVIDENCE-QUALITY": {
                "source_head": HEAD,
                "runtime_timestamp": "2026-06-24T01:53:48Z",
                "pg_snapshot_timestamp": "2026-06-24T01:53:48Z",
                "artifact_mtimes": {"cost_gate": "2026-06-24T01:45:00Z"},
                "operator_authorization_revision": None,
            }
        },
    }


def test_checkpoint_noops_when_active_blocker_already_completed() -> None:
    state = _base_state()
    state["completed_blockers"] = ["P0-PROFIT-EVIDENCE-QUALITY"]

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "NO-OP_ALREADY_DONE"
    assert packet["dispatch_allowed"] is False
    assert packet["next_blocker_id"] == "P0-PROFIT-CANDIDATE-SELECTION"


def test_checkpoint_noops_when_previous_report_has_no_evidence_delta() -> None:
    packet = build_session_loop_state_packet(
        _base_state(),
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "NO-OP_NO_EVIDENCE_DELTA"
    assert packet["anti_repeat_decision"] == (
        "previous_report_exists_and_supplied_evidence_snapshot_has_no_delta"
    )
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["pg_query_performed"] is False
    assert packet["answers"]["probe_authority_granted"] is False


def test_checkpoint_blocks_after_repeated_operator_authorization_block() -> None:
    state = _base_state()
    state["blocked_blockers"] = ["P0-PROFIT-EVIDENCE-QUALITY"]
    state["blocked_reasons"] = {
        "P0-PROFIT-EVIDENCE-QUALITY": "operator authorization required"
    }
    state["consecutive_block_counts"] = {"P0-PROFIT-EVIDENCE-QUALITY": 2}
    state["source_only_progress_blockers"] = ["P1-LEARNING-LOOP-CLOSURE"]

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "BLOCKED_BY_OPERATOR_ACTION"
    assert packet["dispatch_allowed"] is False
    assert packet["next_blocker_id"] == "P0-PROFIT-CANDIDATE-SELECTION"


def test_checkpoint_blocks_after_repeated_runtime_authorization_block() -> None:
    state = _base_state()
    state["blocked_blockers"] = ["P0-PROFIT-CANDIDATE-SELECTION"]
    state["active_blocker_id"] = "P0-PROFIT-CANDIDATE-SELECTION"
    state["blocked_reasons"] = {
        "P0-PROFIT-CANDIDATE-SELECTION": "runtime write permission blocked"
    }
    state["consecutive_block_counts"] = {"P0-PROFIT-CANDIDATE-SELECTION": 2}

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "BLOCKED_BY_RUNTIME_AUTHORIZATION"
    assert packet["dispatch_allowed"] is False


def test_checkpoint_allows_declared_source_only_progress() -> None:
    state = _base_state()
    state["active_blocker_id"] = "P1-LEARNING-LOOP-CLOSURE"
    state["source_only_progress_blockers"] = ["P1-LEARNING-LOOP-CLOSURE"]
    state["source_only_scope_id"] = "learning_ssot_decision_packet"
    state["previous_report_paths"] = {}
    state["previous_evidence_snapshots"] = {}

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )
    markdown = render_markdown(packet)

    assert packet["status"] == "DONE_WITH_CONCERNS"
    assert packet["dispatch_allowed"] is True
    assert packet["anti_repeat_decision"] == (
        "source_only_progress_allowed_for_active_blocker"
    )
    assert "no git/runtime/crontab/service/PG/Bybit inspection" in markdown


def test_checkpoint_does_not_let_blocked_p0_self_override_with_source_only_flag() -> None:
    state = _base_state()
    state["blocked_blockers"] = ["P0-PROFIT-EVIDENCE-QUALITY"]
    state["blocked_reasons"] = {
        "P0-PROFIT-EVIDENCE-QUALITY": "operator authorization required"
    }
    state["source_only_progress_blockers"] = ["P0-PROFIT-EVIDENCE-QUALITY"]
    state["source_only_scope_id"] = "p0_source_guard"
    state["source_only_allowed_blockers"] = ["P0-PROFIT-EVIDENCE-QUALITY"]

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "BLOCKED_BY_OPERATOR_ACTION"
    assert packet["dispatch_allowed"] is False
    assert packet["anti_repeat_decision"] == "active_blocker_blocked_by_operator_action"


def test_checkpoint_detects_structured_exchange_snapshot_delta() -> None:
    state = _base_state()
    state["exchange_snapshot"] = {
        "bybit_open_order_inventory_revision": "rev-b",
        "position_count": 1,
    }
    state["open_order_snapshot"] = {
        "exchange_open_order_count": 34,
        "deep_postonly_order_count": 33,
    }
    state["fill_lineage_snapshot"] = {
        "unattributed_fill_count": 2,
        "candidate_matched_fill_count": 0,
    }
    state["previous_evidence_snapshots"]["P0-PROFIT-EVIDENCE-QUALITY"][
        "exchange_snapshot"
    ] = {
        "bybit_open_order_inventory_revision": "rev-a",
        "position_count": 1,
    }
    state["previous_evidence_snapshots"]["P0-PROFIT-EVIDENCE-QUALITY"][
        "open_order_snapshot"
    ] = {
        "exchange_open_order_count": 35,
        "deep_postonly_order_count": 34,
    }
    state["previous_evidence_snapshots"]["P0-PROFIT-EVIDENCE-QUALITY"][
        "fill_lineage_snapshot"
    ] = {
        "unattributed_fill_count": 2,
        "candidate_matched_fill_count": 0,
    }

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "DONE_WITH_CONCERNS"
    assert packet["dispatch_allowed"] is True
    assert packet["anti_repeat_decision"] == (
        "supplied_evidence_snapshot_delta_allows_active_blocker_progress"
    )
    assert packet["evidence_snapshot_delta_found"] is True
    assert packet["answers"]["new_evidence_delta_found"] is True


def test_checkpoint_detects_exchange_only_snapshot_delta() -> None:
    state = _base_state()
    state["exchange_snapshot"] = {
        "bybit_open_order_inventory_revision": "rev-b",
        "position_count": 1,
    }
    state["previous_evidence_snapshots"]["P0-PROFIT-EVIDENCE-QUALITY"][
        "exchange_snapshot"
    ] = {
        "bybit_open_order_inventory_revision": "rev-a",
        "position_count": 1,
    }

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "DONE_WITH_CONCERNS"
    assert packet["anti_repeat_decision"] == (
        "supplied_evidence_snapshot_delta_allows_active_blocker_progress"
    )
    assert packet["evidence_snapshot_delta_found"] is True


def test_checkpoint_fails_closed_on_authority_bearing_state() -> None:
    state = _base_state()
    state["global_cost_gate_lowering_recommended"] = "true"

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "BLOCKED_BY_OPERATOR_ACTION"
    assert packet["anti_repeat_decision"] == (
        "authority_boundary_violation_in_supplied_loop_state"
    )
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False


def test_checkpoint_does_not_treat_supplied_readonly_evidence_as_authority() -> None:
    state = _base_state()
    state["new_evidence_delta_found"] = True
    state["bybit_call_performed"] = True
    state["pg_query_performed"] = True

    packet = build_session_loop_state_packet(
        state,
        now_utc=dt.datetime(2026, 6, 24, 7, tzinfo=dt.timezone.utc),
    )

    assert packet["status"] == "DONE_WITH_CONCERNS"
    assert packet["dispatch_allowed"] is True
    assert packet["answers"]["bybit_call_performed"] is False
    assert packet["answers"]["pg_query_performed"] is False

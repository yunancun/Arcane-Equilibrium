from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

from cost_gate_learning_lane.bounded_probe_operator_authorization import (
    FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED_STATUS,
    OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION,
    READY_REVIEW_STATUS,
    STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
    STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
    build_bounded_demo_probe_operator_authorization,
    expected_bounded_demo_probe_operator_authorization_typed_confirm,
)
from cost_gate_learning_lane.bounded_probe_operator_authorization_cli import render_markdown
from cost_gate_learning_lane.contract import (
    AUTHORITY_PATH_PATCH_READY_STATUS,
    BOUNDED_PROBE_AUTHORIZED_STATUS,
    BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
    ORDER_AUTHORITY_GRANTED,
)


NOW = dt.datetime(2026, 6, 23, 12, 0, tzinfo=dt.timezone.utc)
SIDE_CELL = "ma_crossover|BTCUSDT|Sell"


def _preflight(**overrides) -> dict:
    payload = {
        "schema_version": "sealed_horizon_bounded_demo_probe_preflight_v1",
        "generated_at_utc": "2026-06-23T11:55:00+00:00",
        "status": "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
        "reason": "all_pre_authorization_gates_passed_without_authority_grant",
        "side_cell_key": SIDE_CELL,
        "outcome_horizon_minutes": 240,
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "bounded_demo_probe_design": {
            "status": "READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION",
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
            "suggested_initial_probe_limits": {
                "active": False,
                "requires_separate_operator_authorization": True,
                "max_probe_intents_before_review": 3,
                "max_demo_notional_usdt_per_order": 10,
                "max_total_demo_notional_usdt_before_review": 30,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
        "answers": {
            "ready_for_operator_bounded_demo_probe_authorization": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _placement_plan(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
        "generated_at_utc": "2026-06-23T11:56:00+00:00",
        "status": "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW",
        "reason": "deep_passive_no_touch_requires_near_touch_or_skip_probe_placement",
        "candidate": {
            "side_cell_key": SIDE_CELL,
            "strategy_name": "ma_crossover",
            "symbol": "BTCUSDT",
            "side": "Sell",
            "outcome_horizon_minutes": 240,
        },
        "placement_repair_plan": {
            "schema_version": "bounded_demo_probe_placement_repair_plan_v1",
            "status": "OPERATOR_REVIEW_READY_NOT_ACTIVE",
            "active": False,
            "requires_separate_operator_authorization": True,
            "order_mode": "post_only_near_touch_or_skip",
            "max_fresh_bbo_age_ms": 1000,
            "max_initial_passive_gap_bps": 75.0,
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
            "probe_limits": {
                "max_probe_intents_before_review": 3,
                "max_demo_notional_usdt_per_order": 10.0,
            },
            "authority_boundary": {
                "global_cost_gate_lowering_recommended": False,
                "main_cost_gate_adjustment": "NONE",
                "probe_authority_granted": False,
                "order_authority_granted": False,
                "promotion_evidence": False,
            },
        },
        "answers": {
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _readiness(**overrides) -> dict:
    payload = {
        "schema_version": "bounded_demo_probe_authority_patch_readiness_v1",
        "generated_at_utc": "2026-06-23T11:57:00+00:00",
        "status": AUTHORITY_PATH_PATCH_READY_STATUS,
        "reason": "source_contains_required_near_touch_authority_adapter_and_evidence_hooks",
        "placement_repair_plan": {
            "candidate": {
                "side_cell_key": SIDE_CELL,
                "strategy_name": "ma_crossover",
                "symbol": "BTCUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            },
        },
        "answers": {
            "rust_near_touch_authority_adapter_present": True,
            "rust_authority_path_wiring_present": True,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def _standing_demo_authorization(**overrides) -> dict:
    payload = {
        "schema_version": STANDING_DEMO_AUTHORIZATION_SCHEMA_VERSION,
        "generated_at_utc": "2026-06-23T11:58:00+00:00",
        "status": STANDING_DEMO_AUTHORIZATION_ACTIVE_STATUS,
        "standing_authorization_id": "standing-demo-session-001",
        "operator_id": "operator-test",
        "environment": "demo",
        "scope": "demo_api_only_bounded_probe",
        "demo_only": True,
        "candidate_scoping_required": True,
        "max_authorized_probe_orders_per_candidate": 2,
        "expires_at_utc": "2026-06-23T18:00:00+00:00",
        "answers": {
            "demo_only": True,
            "candidate_scoping_required": True,
            "live_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        },
    }
    payload.update(overrides)
    return payload


def test_missing_preflight_fails_closed_without_authorization() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=None,
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        now_utc=NOW,
    )

    assert packet["schema_version"] == OPERATOR_AUTHORIZATION_PACKET_SCHEMA_VERSION
    assert packet["status"] == "SEALED_HORIZON_PREFLIGHT_NOT_READY"
    assert packet["operator_authorization"] is None
    assert packet["answers"]["operator_authorization_object_emitted"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False


def test_ready_inputs_produce_review_packet_not_authorization() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="defer",
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == READY_REVIEW_STATUS
    assert packet["blocking_gate_count"] == 0
    assert packet["operator_authorization"] is None
    assert packet["answers"]["ready_for_operator_authorization_review"] is True
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["typed_confirm_expected"] is None
    assert packet["typed_confirm_readiness"] == "MISSING_AUTHORIZATION_FIELDS"
    assert packet["typed_confirm_template"] == (
        "authorize_bounded_demo_probe:"
        "ma_crossover|BTCUSDT|Sell:<max_authorized_probe_orders<=3>:<authorization_id>"
    )
    assert "Bounded Demo Probe Operator Authorization" in markdown
    assert "authorize_bounded_demo_probe" in markdown
    assert ":0:" not in markdown


def test_wrong_typed_confirm_does_not_emit_authorization() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="authorize",
        operator_id="operator-test",
        authorization_id="auth-bounded-probe-001",
        max_authorized_probe_orders=2,
        expires_at_utc="2026-06-23T18:00:00+00:00",
        typed_confirm="authorize_bounded_demo_probe:wrong:2:auth-bounded-probe-001",
        now_utc=NOW,
    )

    assert packet["status"] == "TYPED_CONFIRM_REQUIRED"
    assert packet["operator_authorization"] is None
    assert "typed_confirm_matches" in packet["blocking_gates"]
    assert packet["answers"]["bounded_demo_probe_authorized"] is False


def test_authorize_emits_runtime_compatible_operator_authorization() -> None:
    typed_confirm = expected_bounded_demo_probe_operator_authorization_typed_confirm(
        SIDE_CELL,
        2,
        "auth-bounded-probe-001",
    )
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="authorize",
        operator_id="operator-test",
        authorization_id="auth-bounded-probe-001",
        max_authorized_probe_orders=2,
        expires_at_utc="2026-06-23T18:00:00+00:00",
        typed_confirm=typed_confirm,
        now_utc=NOW,
    )

    auth = packet["operator_authorization"]

    assert packet["status"] == BOUNDED_PROBE_AUTHORIZED_STATUS
    assert packet["answers"]["operator_authorization_object_emitted"] is True
    assert packet["answers"]["plan_mutation_performed"] is False
    assert packet["answers"]["order_submission_performed"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert auth["schema_version"] == BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION
    assert auth["status"] == BOUNDED_PROBE_AUTHORIZED_STATUS
    assert auth["authorization_id"] == "auth-bounded-probe-001"
    assert auth["operator_id"] == "operator-test"
    assert auth["side_cell_key"] == SIDE_CELL
    assert auth["authority_path_readiness_status"] == AUTHORITY_PATH_PATCH_READY_STATUS
    assert auth["main_cost_gate_adjustment"] == "NONE"
    assert auth["order_authority"] == ORDER_AUTHORITY_GRANTED
    assert auth["max_authorized_probe_orders"] == 2
    assert auth["probe_authority_granted"] is True
    assert auth["order_authority_granted"] is True
    assert auth["promotion_evidence"] is False


def test_standing_demo_authorization_emits_candidate_scoped_authorization() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=_standing_demo_authorization(),
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    auth = packet["operator_authorization"]

    assert packet["status"] == BOUNDED_PROBE_AUTHORIZED_STATUS
    assert packet["typed_confirm_provided"] is False
    assert packet["typed_confirm_matches"] is False
    assert packet["authorization_confirmation_source"] == "standing_demo_authorization"
    assert packet["operator_id"] == "operator-test"
    assert packet["answers"]["operator_authorization_object_emitted"] is True
    assert packet["answers"]["active_runtime_probe_authority"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert packet["answers"]["standing_demo_authorization_valid"] is True
    assert auth["schema_version"] == BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION
    assert auth["authorization_id"] == "auth-bounded-probe-standing-001"
    assert auth["operator_id"] == "operator-test"
    assert auth["side_cell_key"] == SIDE_CELL
    assert auth["max_authorized_probe_orders"] == 1
    assert auth["main_cost_gate_adjustment"] == "NONE"
    assert auth["promotion_evidence"] is False
    assert packet["standing_demo_authorization"][
        "valid_for_candidate_scoped_authorization"
    ] is True


def test_live_contaminated_standing_demo_authorization_fails_closed() -> None:
    standing = _standing_demo_authorization(
        environment="live",
        answers={
            "demo_only": False,
            "candidate_scoping_required": True,
            "live_authority_granted": True,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        },
    )

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=standing,
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["operator_authorization"] is None
    assert "standing_demo_authorization_safe" in packet["blocking_gates"]
    assert packet["answers"]["operator_authorization_object_emitted"] is False


def test_wrong_typed_confirm_takes_precedence_over_standing_authorization() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=_standing_demo_authorization(),
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        typed_confirm="authorize_bounded_demo_probe:wrong:1:auth-bounded-probe-standing-001",
        now_utc=NOW,
    )

    assert packet["status"] == "TYPED_CONFIRM_REQUIRED"
    assert packet["operator_authorization"] is None
    assert packet["authorization_confirmation_source"] is None
    assert packet["answers"]["standing_demo_authorization_valid"] is False
    assert "typed_confirm_matches" in packet["blocking_gates"]


def test_standing_demo_operator_mismatch_fails_closed() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=_standing_demo_authorization(),
        decision="authorize",
        operator_id="different-operator",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "STANDING_DEMO_AUTHORIZATION_OPERATOR_MISMATCH"
    assert packet["operator_authorization"] is None
    assert "standing_demo_operator_matches" in packet["blocking_gates"]


def test_standing_demo_scope_must_be_bounded_probe_specific() -> None:
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=_standing_demo_authorization(scope="demo_api_all"),
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "TYPED_CONFIRM_REQUIRED"
    assert packet["operator_authorization"] is None
    assert packet["standing_demo_authorization"]["scope_valid"] is False
    assert packet["answers"]["standing_demo_authorization_valid"] is False


def test_nested_runtime_authority_in_standing_demo_authorization_fails_closed() -> None:
    standing = _standing_demo_authorization(
        audit={
            "nested": [
                {
                    "active_runtime_order_authority": True,
                }
            ]
        }
    )

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=standing,
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["operator_authorization"] is None
    assert "authority_boundary_preserved" in packet["blocking_gates"]


def test_truthy_authority_string_in_standing_demo_authorization_fails_closed() -> None:
    standing = _standing_demo_authorization(
        answers={
            "demo_only": True,
            "candidate_scoping_required": True,
            "live_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": "true",
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        }
    )

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=standing,
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert packet["operator_authorization"] is None
    assert packet["answers"]["operator_authorization_object_emitted"] is False


def test_top_level_standing_demo_flags_cannot_be_overridden_by_answers() -> None:
    standing = _standing_demo_authorization(
        demo_only=False,
        candidate_scoping_required=False,
        answers={
            "demo_only": True,
            "candidate_scoping_required": True,
            "live_authority_granted": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
        },
    )

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=standing,
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "TYPED_CONFIRM_REQUIRED"
    assert packet["operator_authorization"] is None
    assert packet["standing_demo_authorization"]["demo_only"] is False
    assert packet["standing_demo_authorization"]["candidate_scoping_required"] is False
    assert packet["answers"]["standing_demo_authorization_valid"] is False


def test_top_level_standing_demo_cap_is_required() -> None:
    standing = _standing_demo_authorization(max_authorized_probe_orders_per_candidate=None)
    standing["answers"]["max_authorized_probe_orders_per_candidate"] = 2

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        standing_demo_authorization=standing,
        decision="authorize",
        authorization_id="auth-bounded-probe-standing-001",
        max_authorized_probe_orders=1,
        expires_at_utc="2026-06-23T17:00:00+00:00",
        now_utc=NOW,
    )

    assert packet["status"] == "TYPED_CONFIRM_REQUIRED"
    assert packet["operator_authorization"] is None
    assert packet["standing_demo_authorization"][
        "max_authorized_probe_orders_per_candidate"
    ] is None
    assert packet["answers"]["standing_demo_authorization_valid"] is False


def test_standing_demo_cli_input_emits_authorization(tmp_path) -> None:
    preflight = tmp_path / "preflight.json"
    placement = tmp_path / "placement.json"
    readiness = tmp_path / "readiness.json"
    standing = tmp_path / "standing.json"
    out = tmp_path / "out.json"
    generated_at = (
        dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=1)
    ).isoformat()
    expires_at = (
        dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)
    ).isoformat()
    preflight.write_text(
        json.dumps(_preflight(generated_at_utc=generated_at)),
        encoding="utf-8",
    )
    placement.write_text(
        json.dumps(_placement_plan(generated_at_utc=generated_at)),
        encoding="utf-8",
    )
    readiness.write_text(
        json.dumps(_readiness(generated_at_utc=generated_at)),
        encoding="utf-8",
    )
    standing.write_text(
        json.dumps(
            _standing_demo_authorization(
                generated_at_utc=generated_at,
                expires_at_utc=expires_at,
            )
        ),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "cost_gate_learning_lane.bounded_probe_operator_authorization_cli",
            "--preflight-json",
            str(preflight),
            "--placement-repair-plan-json",
            str(placement),
            "--authority-patch-readiness-json",
            str(readiness),
            "--standing-demo-authorization-json",
            str(standing),
            "--decision",
            "authorize",
            "--authorization-id",
            "auth-bounded-probe-standing-001",
            "--max-authorized-probe-orders",
            "1",
            "--expires-at-utc",
            expires_at,
            "--json-output",
            str(out),
        ],
        check=True,
        cwd=tmp_path,
        env=env,
        text=True,
    )

    assert result.returncode == 0
    packet = json.loads(out.read_text(encoding="utf-8"))
    assert packet["status"] == BOUNDED_PROBE_AUTHORIZED_STATUS
    assert packet["authorization_confirmation_source"] == "standing_demo_authorization"
    assert packet["artifacts"]["standing_demo_authorization"]["sha256"]


def test_excessive_budget_and_expired_authorization_are_blocked() -> None:
    typed_confirm = expected_bounded_demo_probe_operator_authorization_typed_confirm(
        SIDE_CELL,
        4,
        "auth-bounded-probe-001",
    )
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="authorize",
        operator_id="operator-test",
        authorization_id="auth-bounded-probe-001",
        max_authorized_probe_orders=4,
        expires_at_utc="2026-06-23T11:00:00+00:00",
        typed_confirm=typed_confirm,
        now_utc=NOW,
    )

    assert packet["status"] == "PROBE_BUDGET_REQUIRED_OR_EXCEEDS_SOURCE_LIMIT"
    assert packet["operator_authorization"] is None
    assert "probe_budget_valid" in packet["blocking_gates"]
    assert "authorization_expiry_valid" in packet["blocking_gates"]


def test_mismatched_side_cell_blocks_authorization_review() -> None:
    readiness = _readiness(
        placement_repair_plan={
            "candidate": {
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "strategy_name": "ma_crossover",
                "symbol": "ETHUSDT",
                "side": "Sell",
                "outcome_horizon_minutes": 240,
            }
        }
    )
    packet = build_bounded_demo_probe_operator_authorization(
        preflight=_preflight(),
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=readiness,
        now_utc=NOW,
    )

    assert packet["status"] == "CANDIDATE_ALIGNMENT_MISMATCH"
    assert "candidate_alignment" in packet["blocking_gates"]
    assert packet["operator_authorization"] is None


def test_authority_granting_input_fails_closed() -> None:
    preflight = _preflight()
    preflight["answers"]["order_authority_granted"] = True

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=preflight,
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        now_utc=NOW,
    )

    assert packet["status"] == "AUTHORITY_BOUNDARY_VIOLATION"
    assert "authority_boundary_preserved" in packet["blocking_gates"]
    assert packet["operator_authorization"] is None


def test_false_negative_preflight_schema_can_reach_review_packet() -> None:
    preflight = _preflight()
    preflight["schema_version"] = (
        "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
    )
    preflight["candidate"] = {
        "side_cell_key": SIDE_CELL,
        "strategy_name": "ma_crossover",
        "symbol": "BTCUSDT",
        "side": "Sell",
        "outcome_horizon_minutes": 240,
        "source_kind": "cost_gate_false_negative_after_cost",
    }

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=preflight,
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="defer",
        now_utc=NOW,
    )

    assert packet["status"] == READY_REVIEW_STATUS
    assert packet["operator_authorization"] is None
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False


def test_false_negative_preflight_operator_review_required_is_labeled() -> None:
    preflight = _preflight(
        schema_version="cost_gate_false_negative_bounded_demo_probe_preflight_v1",
        status="OPERATOR_REVIEW_REQUIRED",
        reason="false_negative_operator_review_approved_for_preflight missing",
        blocking_gates=["false_negative_operator_review_approved_for_preflight"],
        answers={
            "ready_for_operator_bounded_demo_probe_authorization": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    )

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=preflight,
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="defer",
        now_utc=NOW,
    )

    assert packet["status"] == FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED_STATUS
    assert packet["operator_authorization"] is None
    assert packet["blocking_gates"] == ["false_negative_preflight_ready"]
    assert packet["typed_confirm_expected"] is None
    assert packet["typed_confirm_readiness"] == "PREFLIGHT_NOT_READY"
    assert packet["typed_confirm_template"] == (
        "authorize_bounded_demo_probe:"
        "ma_crossover|BTCUSDT|Sell:<max_authorized_probe_orders<=3>:<authorization_id>"
    )
    assert packet["preflight"]["schema_version"] == (
        "cost_gate_false_negative_bounded_demo_probe_preflight_v1"
    )
    assert packet["answers"]["operator_authorization_object_emitted"] is False
    assert packet["answers"]["bounded_demo_probe_authorized"] is False
    assert packet["answers"]["active_runtime_probe_authority"] is False
    assert packet["answers"]["active_runtime_order_authority"] is False
    assert packet["answers"]["global_cost_gate_lowering_recommended"] is False
    assert packet["next_actions"] == [
        "operator_review_false_negative_candidate_with_exact_preflight_confirm"
    ]


def test_preflight_not_ready_suppresses_exact_typed_confirm_even_with_auth_fields() -> None:
    preflight = _preflight(
        schema_version="cost_gate_false_negative_bounded_demo_probe_preflight_v1",
        status="OPERATOR_REVIEW_REQUIRED",
        reason="false_negative_operator_review_approved_for_preflight missing",
        blocking_gates=["false_negative_operator_review_approved_for_preflight"],
        answers={
            "ready_for_operator_bounded_demo_probe_authorization": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
    )

    packet = build_bounded_demo_probe_operator_authorization(
        preflight=preflight,
        placement_repair_plan=_placement_plan(),
        authority_patch_readiness=_readiness(),
        decision="authorize",
        operator_id="operator-test",
        authorization_id="auth-bounded-probe-001",
        max_authorized_probe_orders=2,
        expires_at_utc="2026-06-23T18:00:00+00:00",
        typed_confirm=(
            "authorize_bounded_demo_probe:"
            "ma_crossover|BTCUSDT|Sell:2:auth-bounded-probe-001"
        ),
        now_utc=NOW,
    )
    markdown = render_markdown(packet)

    assert packet["status"] == FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED_STATUS
    assert packet["operator_authorization"] is None
    assert packet["typed_confirm_expected"] is None
    assert packet["typed_confirm_matches"] is False
    assert packet["typed_confirm_readiness"] == "PREFLIGHT_NOT_READY"
    assert "ma_crossover|BTCUSDT|Sell:2:auth-bounded-probe-001" not in markdown
    assert "NOT_AVAILABLE_UNTIL_AUTHORIZATION_FIELDS_AND_PREFLIGHT_READY" in markdown

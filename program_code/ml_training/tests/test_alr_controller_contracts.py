from __future__ import annotations

import copy

import pytest

from ml_training.alr_controller_contracts import (
    ALR_EFFECT_REVIEW_FIELD,
    ALR_LOOP_STATE_PACKET_FIELD,
    ALR_WORK_ITEM_FIELD,
    BOUNDARY_LABEL,
    BOUNDARY_VALIDATED_WITH_CONCERNS,
    OUTCOME_ADVANCED,
    OUTCOME_ADVANCED_WITH_CONCERNS,
    OUTCOME_BLOCKED_BOUNDARY,
    OUTCOME_DEFER_EVIDENCE,
    OUTCOME_ROTATED,
    OUTCOME_STOP_NO_EDGE,
    OUTCOME_STOP_RETENTION_RISK,
    STATUS_DEFER_EVIDENCE,
    STATUS_NO_EDGE,
    STATUS_RETENTION_RISK,
    STATUS_ROTATED,
    AlrControllerContractError,
    build_alr_effect_review,
    build_alr_loop_state_packet,
    build_alr_work_item,
    compute_alr_loop_state_packet_hash,
    compute_alr_work_item_hash,
    extract_alr_effect_review,
    extract_alr_loop_state_packet,
    extract_alr_work_item,
    validate_alr_effect_review,
    validate_alr_loop_state_packet,
    validate_alr_work_item,
)


ACCEPTED_CONCERN = "ADR/AMD text NOT_APPLIED; no governance authority granted"


def _item(index: int, **overrides) -> dict:
    kwargs = {
        "work_item_id": f"alr-work-{index}",
        "row_id": f"row-{index}",
        "title": f"ALR row {index}",
        "source_refs": {"todo_id": "P0-AIML-ALR-CONTROLLER-CONTRACTS"},
    }
    kwargs.update(overrides)
    return build_alr_work_item(**kwargs)


def test_builds_and_validates_each_packet_type_and_extractors() -> None:
    work_item = _item(1)
    review = build_alr_effect_review(work_item=work_item)
    loop_packet = build_alr_loop_state_packet(work_items=[work_item])

    assert validate_alr_work_item(work_item).valid is True
    assert validate_alr_effect_review(review).valid is True
    loop_validation = validate_alr_loop_state_packet(loop_packet)
    assert loop_validation.valid is True
    assert loop_validation.outcome == OUTCOME_ADVANCED
    assert extract_alr_work_item({ALR_WORK_ITEM_FIELD: work_item}) == work_item
    assert extract_alr_effect_review({ALR_EFFECT_REVIEW_FIELD: review}) == review
    assert extract_alr_loop_state_packet({ALR_LOOP_STATE_PACKET_FIELD: loop_packet}) == loop_packet
    assert extract_alr_work_item({"workItem": work_item}) is None


def test_selector_emits_first_unblocked_row_not_later_row() -> None:
    first = _item(1)
    second = _item(2)
    packet = build_alr_loop_state_packet(work_items=[first, second])

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED
    assert validation.selected_work_item_id == "alr-work-1"
    assert packet["selected_work_item"]["work_item_id"] == "alr-work-1"


def test_real_queue_status_flow_selects_first_active_after_done_with_concerns() -> None:
    done = _item(1, state="DONE_WITH_CONCERNS", status="DONE_WITH_CONCERNS")
    active = _item(2, state="ACTIVE", status="ACTIVE")
    later = _item(3, state="ACTIVE", status="ACTIVE")
    packet = build_alr_loop_state_packet(work_items=[done, active, later])

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED
    assert validation.selected_work_item_id == "alr-work-2"
    assert packet["selection_reason"] == "active_without_blockers"


def test_waiting_queue_row_only_selectable_when_conditions_satisfied() -> None:
    waiting = _item(1, state="WAITING_CONTROLLER", status="WAITING_CONTROLLER")
    packet = build_alr_loop_state_packet(work_items=[waiting])
    assert validate_alr_loop_state_packet(packet).outcome == OUTCOME_DEFER_EVIDENCE

    waiting["conditions_satisfied"] = True
    waiting["work_item_hash"] = compute_alr_work_item_hash(waiting)
    ready_packet = build_alr_loop_state_packet(work_items=[waiting])
    validation = validate_alr_loop_state_packet(ready_packet)
    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED
    assert ready_packet["selection_reason"] == "waiting_conditions_satisfied"


def test_deferred_p0_queue_row_returns_defer_evidence() -> None:
    item = _item(1, state="DEFERRED_P0", status="DEFERRED_P0")
    packet = build_alr_loop_state_packet(work_items=[item])

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_DEFER_EVIDENCE


def test_advanced_when_first_ready_row_has_no_concerns() -> None:
    packet = build_alr_loop_state_packet(work_items=[_item(1)])

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED
    assert validation.reason == "ok"


def test_advanced_with_concerns_when_boundary_has_accepted_no_authority_wording() -> None:
    item = _item(
        1,
        boundary_status=BOUNDARY_VALIDATED_WITH_CONCERNS,
        concerns=[ACCEPTED_CONCERN],
    )
    packet = build_alr_loop_state_packet(work_items=[item])

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED_WITH_CONCERNS


def test_boundary_validated_with_concerns_rejects_unaccepted_concern() -> None:
    with pytest.raises(
        AlrControllerContractError,
        match="boundary_concerns_not_accepted_no_authority_wording",
    ):
        _item(
            1,
            boundary_status=BOUNDARY_VALIDATED_WITH_CONCERNS,
            concerns=["looks okay but needs review"],
        )


def test_boundary_concern_requires_not_applied_wording() -> None:
    with pytest.raises(
        AlrControllerContractError,
        match="boundary_concerns_not_accepted_no_authority_wording",
    ):
        _item(
            1,
            boundary_status=BOUNDARY_VALIDATED_WITH_CONCERNS,
            concerns=["no governance authority for ADR/AMD proposal text"],
        )


def test_boundary_concern_accepts_all_required_tokens() -> None:
    item = _item(
        1,
        boundary_status=BOUNDARY_VALIDATED_WITH_CONCERNS,
        concerns=["ADR/AMD text NOT_APPLIED; no governance authority granted"],
    )

    validation = validate_alr_work_item(item)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED_WITH_CONCERNS


def test_boundary_concerns_reject_mixed_valid_and_unsafe_followup() -> None:
    with pytest.raises(
        AlrControllerContractError,
        match="boundary_concerns_not_accepted_no_authority_wording",
    ):
        _item(
            1,
            boundary_status=BOUNDARY_VALIDATED_WITH_CONCERNS,
            concerns=[
                "ADR/AMD text NOT_APPLIED; no governance authority granted",
                "future apply/live authority followup",
            ],
        )


def test_defer_evidence_for_evidence_blocked_deferred_queue() -> None:
    item = _item(
        1,
        state="DEFERRED",
        status=STATUS_DEFER_EVIDENCE,
        blockers=["evidence_blocked"],
    )
    packet = build_alr_loop_state_packet(work_items=[item])

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_DEFER_EVIDENCE


def test_rotated_for_source_hash_drift_blocker() -> None:
    item = _item(1, status=STATUS_ROTATED, blockers=["source_hash_drift"])
    packet = build_alr_loop_state_packet(work_items=[item])

    assert validate_alr_loop_state_packet(packet).outcome == OUTCOME_ROTATED


def test_stop_no_edge_for_no_edge_blocker() -> None:
    item = _item(1, status=STATUS_NO_EDGE, blockers=["no_edge"])
    packet = build_alr_loop_state_packet(work_items=[item])

    assert validate_alr_loop_state_packet(packet).outcome == OUTCOME_STOP_NO_EDGE


def test_stop_retention_risk_for_retention_risk_blocker() -> None:
    item = _item(1, status=STATUS_RETENTION_RISK, blockers=["retention_risk"])
    packet = build_alr_loop_state_packet(work_items=[item])

    assert validate_alr_loop_state_packet(packet).outcome == OUTCOME_STOP_RETENTION_RISK


def test_blocked_boundary_for_wrong_boundary_label() -> None:
    item = _item(1)
    item["boundary_label"] = "WRONG"
    item["work_item_hash"] = compute_alr_work_item_hash(item)

    validation = validate_alr_work_item(item)

    assert validation.valid is False
    assert validation.outcome == OUTCOME_BLOCKED_BOUNDARY
    assert validation.reason == "boundary_label_mismatch"


@pytest.mark.parametrize(
    "alias",
    [
        "runtime_authority_granted",
        "order_allowed",
        "probe_allowed",
        "live_enabled",
        "promotion_enabled",
        "latest_consumed",
        "apply_allowed",
        "delete_allowed",
        "cost_gate_lowered",
    ],
)
def test_truthy_authority_flags_fail_boundary(alias: str) -> None:
    item = _item(1)
    item["metadata"] = {alias: True}
    item["work_item_hash"] = compute_alr_work_item_hash(item)

    validation = validate_alr_work_item(item)

    assert validation.valid is False
    assert validation.outcome == OUTCOME_BLOCKED_BOUNDARY
    assert validation.authority_boundary_violation is True


def test_loop_packet_truthy_authority_alias_fails_closed() -> None:
    item = _item(1)
    packet = build_alr_loop_state_packet(work_items=[item])
    packet["metadata"] = {"service_restart_allowed": "true"}
    packet["packet_hash"] = compute_alr_loop_state_packet_hash(packet)

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is False
    assert validation.outcome == OUTCOME_BLOCKED_BOUNDARY
    assert validation.authority_boundary_violation is True


def test_hash_mismatch_fails_closed() -> None:
    packet = build_alr_loop_state_packet(work_items=[_item(1)])
    packet["packet_hash"] = "a" * 64

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is False
    assert "packet_hash_mismatch" in validation.reasons


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("state", "RUNNING", "state_unknown"),
        ("status", "UNKNOWN_DONE", "status_unknown"),
    ],
)
def test_unknown_state_or_status_fails_closed(field: str, value: str, reason: str) -> None:
    item = _item(1)
    item[field] = value
    item["work_item_hash"] = compute_alr_work_item_hash(item)

    validation = validate_alr_work_item(item)

    assert validation.valid is False
    assert reason in validation.reasons


def test_explicit_false_disabled_no_authority_strings_remain_safe() -> None:
    falsey_authority_strings = {
        "runtime_authority_granted": "disabled",
        "order_allowed": "false",
        "probe_allowed": "0",
        "live_enabled": "denied",
        "promotion_enabled": "off",
        "latest_consumed": "none",
        "apply_allowed": "no",
        "delete_allowed": "disabled",
        "cost_gate_lowered": "false",
    }
    item = _item(1)
    item["metadata"] = falsey_authority_strings
    item["no_authority"]["runtime"] = "disabled"
    item["no_authority"]["order"] = "false"
    item["work_item_hash"] = compute_alr_work_item_hash(item)

    validation = validate_alr_work_item(item)

    assert validation.valid is True
    assert validation.outcome == OUTCOME_ADVANCED


def test_malformed_hash_fails_closed() -> None:
    item = _item(1)
    item["work_item_hash"] = "not-a-hash"

    validation = validate_alr_work_item(item)

    assert validation.valid is False
    assert "work_item_hash_malformed" in validation.reasons


def test_effect_review_advanced_with_concerns_requires_accepted_no_authority_wording() -> None:
    item = _item(1)

    with pytest.raises(
        AlrControllerContractError,
        match="advanced_with_concerns_missing_no_authority_wording",
    ):
        build_alr_effect_review(
            work_item=item,
            outcome=OUTCOME_ADVANCED_WITH_CONCERNS,
            concerns=["plain concern"],
        )

    review = build_alr_effect_review(
        work_item=item,
        outcome=OUTCOME_ADVANCED_WITH_CONCERNS,
        concerns=[ACCEPTED_CONCERN],
    )
    assert validate_alr_effect_review(review).valid is True


def test_hash_excludes_only_own_hash_field() -> None:
    item = _item(1)
    same = copy.deepcopy(item)
    same["work_item_hash"] = "f" * 64
    assert compute_alr_work_item_hash(same) == compute_alr_work_item_hash(item)
    changed = copy.deepcopy(item)
    changed["source_refs"]["extra_hash"] = "e" * 64
    assert compute_alr_work_item_hash(changed) != compute_alr_work_item_hash(item)


def test_loop_state_packet_exports_required_loop_contract_fields() -> None:
    packet = build_alr_loop_state_packet(work_items=[_item(1)])

    required_fields = {
        "schema",
        "created_at",
        "repo_head_before",
        "repo_head_after",
        "selected_work_item",
        "selection_reason",
        "state",
        "next_state",
        "next_action",
        "stop_reason",
        "owned_files",
        "verification_commands",
        "candidate_matched_fills_count",
        "proof_packet_ready_count",
        "reward_ledger_ready_count",
        "effect_review_ready",
        "model_training_performed",
        "serving_authority_granted",
        "llm_authority",
        "runtime_authority",
        "exchange_authority",
        "trading_authority",
        "boundary_escalation_required",
        "dispatch_tooling_available",
        "dispatch_blocker",
    }
    assert required_fields.issubset(packet.keys())
    for authority_field in (
        "model_training_performed",
        "serving_authority_granted",
        "llm_authority",
        "runtime_authority",
        "exchange_authority",
        "trading_authority",
    ):
        assert packet[authority_field] is False
    assert validate_alr_loop_state_packet(packet).valid is True


def test_loop_state_packet_missing_schema_fails_closed() -> None:
    packet = build_alr_loop_state_packet(work_items=[_item(1)])
    packet.pop("schema")
    packet["packet_hash"] = compute_alr_loop_state_packet_hash(packet)

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is False
    assert "schema_missing" in validation.reasons


def test_loop_state_packet_missing_required_field_fails_closed() -> None:
    packet = build_alr_loop_state_packet(work_items=[_item(1)])
    packet.pop("created_at")
    packet["packet_hash"] = compute_alr_loop_state_packet_hash(packet)

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is False
    assert "created_at_missing" in validation.reasons


@pytest.mark.parametrize(
    "authority_field",
    [
        "model_training_performed",
        "serving_authority_granted",
        "llm_authority",
        "runtime_authority",
        "exchange_authority",
        "trading_authority",
    ],
)
def test_loop_state_packet_true_authority_booleans_fail_closed(authority_field: str) -> None:
    packet = build_alr_loop_state_packet(work_items=[_item(1)])
    packet[authority_field] = True
    packet["packet_hash"] = compute_alr_loop_state_packet_hash(packet)

    validation = validate_alr_loop_state_packet(packet)

    assert validation.valid is False
    assert OUTCOME_BLOCKED_BOUNDARY == validation.outcome
    assert validation.authority_boundary_violation is True or (
        f"{authority_field}_not_false" in validation.reasons
    )

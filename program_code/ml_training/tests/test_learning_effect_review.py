from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

import pytest

from ml_training.learning_effect_review import (
    DECISION_CONTINUE,
    DECISION_PROMOTE_REVIEW_ONLY,
    DECISION_ROLLBACK,
    DECISION_STOP_EVIDENCE,
    DECISION_STOP_LOSS_CONTROL,
    DECISION_STOP_NO_EDGE,
    LEARNING_EFFECT_REVIEW_FIELD,
    LearningEffectReviewError,
    build_learning_effect_review_packet,
    compute_learning_effect_review_hash,
    extract_learning_effect_review,
    validate_learning_effect_review,
)
from ml_training.reward_ledger import compute_reward_record_hash

_REWARD_LEDGER_TEST_PATH = Path(__file__).with_name("test_reward_ledger.py")
_REWARD_LEDGER_SPEC = importlib.util.spec_from_file_location(
    "_learning_effect_review_reward_ledger_fixtures",
    _REWARD_LEDGER_TEST_PATH,
)
assert _REWARD_LEDGER_SPEC is not None
_reward_ledger_fixtures = importlib.util.module_from_spec(_REWARD_LEDGER_SPEC)
assert _REWARD_LEDGER_SPEC.loader is not None
_REWARD_LEDGER_SPEC.loader.exec_module(_reward_ledger_fixtures)
_build_record = _reward_ledger_fixtures._build_record
_valid_envelope = _reward_ledger_fixtures._valid_envelope
_valid_proof_packet = _reward_ledger_fixtures._valid_proof_packet


def _record(index: int, *, net_bps: float = 4.2, net_usdt: float | None = None) -> dict:
    context_id = f"ctx-entry-{index}"
    proof = _valid_proof_packet(
        candidate_identity={"context_id": context_id},
        execution_identity={
            "order_link_id": f"oc_dm_1782040200000_{index}_0deadbeef",
            "fill_ids": [f"fill-entry-{index}", f"fill-exit-{index}"],
            "entry_context_id": context_id,
            "exit_context_id": f"ctx-exit-{index}",
        },
        cost_identity={
            "realized_net_pnl_bps": net_bps,
            "realized_net_pnl_usdt": net_usdt if net_usdt is not None else net_bps / 10,
        },
    )
    return _build_record(proof_packet=proof, demo_mutation_envelope=_valid_envelope(proof))


def _loss_limits(**overrides) -> dict:
    limits = {
        "max_cumulative_loss_bps": 20.0,
        "max_cumulative_loss_usdt": 5.0,
        "max_single_record_loss_bps": 10.0,
        "max_consecutive_negative_windows": 2,
        "breach": False,
    }
    limits.update(overrides)
    return limits


def _controls(**overrides) -> dict:
    controls = {
        "matched_control_required": True,
        "matched_control_ids": ["control-1", "control-2"],
        "regime_labels_required": True,
        "regime_labels": {"trend": "sideways", "volatility": "medium"},
        "oos_required": True,
        "repeat_required_for_promotion": True,
        "control_outperformance_bps": 7.5,
        "mutation_effect_status": "passed",
    }
    controls.update(overrides)
    return controls


def _tags(**overrides) -> dict:
    tags = {
        "oos": True,
        "repeat": True,
        "repeat_count": 2,
        "regime_tag": "sideways_medium_vol",
    }
    tags.update(overrides)
    return tags


def _packet(records=None, **kwargs) -> dict:
    return build_learning_effect_review_packet(
        reward_records=records or [_record(1), _record(2), _record(3)],
        loss_limits=kwargs.pop("loss_limits", _loss_limits()),
        controls=kwargs.pop("controls", _controls()),
        oos_repeat_tags=kwargs.pop("oos_repeat_tags", _tags()),
        review_policy=kwargs.pop("review_policy", {"min_sample_count": 2}),
        acceptance_report_refs=kwargs.pop("acceptance_report_refs", None),
        **kwargs,
    )


def test_profitable_after_cost_repeat_promote_review_only() -> None:
    packet = _packet()

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_PROMOTE_REVIEW_ONLY
    assert packet["review_only"] is True
    assert packet["no_authority"]["promotion_review_only"] is True
    denied = {k: v for k, v in packet["no_authority"].items() if k != "promotion_review_only"}
    assert all(value is False for value in denied.values())


def test_positive_after_cost_but_not_repeat_ready_continues() -> None:
    packet = _packet(oos_repeat_tags=_tags(repeat=False, repeat_count=1))

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_CONTINUE
    assert validation.reason == "positive_after_cost_repeat_not_ready"


def test_negative_ev_stops_no_edge_after_loss_controls_pass() -> None:
    packet = _packet(records=[_record(1, net_bps=-1.0), _record(2, net_bps=-2.0)])

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_NO_EDGE
    assert validation.reason == "after_cost_ev_negative"


def test_no_matched_fills_invalid_reward_input_builder_raises() -> None:
    record = _record(1)
    record["execution_identity"]["fill_ids"] = []
    record["record_hash"] = compute_reward_record_hash(record)

    with pytest.raises(LearningEffectReviewError, match="execution_identity_fill_ids_missing"):
        _packet(records=[record])


def test_insufficient_sample_stops_evidence() -> None:
    packet = _packet(records=[_record(1)], review_policy={"min_sample_count": 2})

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert validation.reason == "sample_count_below_minimum"


def test_missing_controls_stop_evidence() -> None:
    packet = _packet(controls=_controls(matched_control_ids=[], regime_labels={}))

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert "matched_controls_missing" in validation.reasons
    assert "regime_labels_missing" in validation.reasons


def test_failed_mutation_effect_rolls_back_review_only() -> None:
    packet = _packet(controls=_controls(mutation_effect_status="failed"))

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_ROLLBACK
    assert validation.reason == "mutation_effect_failed"


def test_loss_limit_breach_preempts_negative_ev() -> None:
    packet = _packet(
        records=[_record(1, net_bps=-12.0), _record(2, net_bps=4.0)],
        loss_limits=_loss_limits(),
    )

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_LOSS_CONTROL
    assert validation.reason == "single_record_loss_bps_breached"


def test_authority_alias_injection_invalidates_boundary() -> None:
    packet = _packet()
    packet["metadata"] = {"order_allowed": True, "model_reload": True}
    packet["review_hash"] = compute_learning_effect_review_hash(packet)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is False
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert validation.authority_boundary_violation is True
    assert validation.reason.startswith("authority_boundary_violation:")


@pytest.mark.parametrize(
    "alias",
    [
        "trade_allowed",
        "trading_enabled",
        "enable_trading",
        "execution_authority_granted",
    ],
)
def test_trading_execution_authority_aliases_invalidate_boundary(alias: str) -> None:
    packet = _packet()
    packet["metadata"] = {alias: True}
    packet["source_artifacts"]["reward_records"][0]["metadata"] = {alias: "true"}
    packet["review_hash"] = compute_learning_effect_review_hash(packet)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is False
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert validation.authority_boundary_violation is True
    assert validation.reason.startswith("authority_boundary_violation:")


@pytest.mark.parametrize(
    ("location", "alias", "grant"),
    [
        ("metadata", "trade_allowed", "allowed"),
        ("metadata", "trade_allowed", "allow"),
        ("source_artifact", "execution_authority_granted", "active"),
        ("source_artifact", "execution_allowed", "approved"),
    ],
)
def test_authority_alias_string_grants_invalidate_after_rehash(
    location: str,
    alias: str,
    grant: str,
) -> None:
    packet = _packet()
    if location == "metadata":
        packet["metadata"] = {alias: grant}
    else:
        packet["source_artifacts"]["reward_records"][0]["metadata"] = {alias: grant}
    packet["review_hash"] = compute_learning_effect_review_hash(packet)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is False
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert validation.authority_boundary_violation is True
    assert validation.reason.startswith("authority_boundary_violation:")


def test_authority_alias_explicit_false_strings_remain_safe() -> None:
    packet = _packet()
    packet["metadata"] = {
        "trade_allowed": "false",
        "trading_enabled": "0",
        "execution_authority_granted": "disabled",
        "execution_allowed": "denied",
    }
    packet["review_hash"] = compute_learning_effect_review_hash(packet)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_PROMOTE_REVIEW_ONLY


def test_review_hash_mismatch_rejected() -> None:
    packet = _packet()
    packet["effect_metrics"]["net_pnl_bps_sum"] = 999.0

    validation = validate_learning_effect_review(packet)

    assert validation.valid is False
    assert validation.decision == DECISION_PROMOTE_REVIEW_ONLY
    assert validation.reason == "review_hash_mismatch"


@pytest.mark.parametrize(
    ("mutator", "reason"),
    [
        (
            lambda packet: packet["inputs"]["reward_ledger_refs"].pop(),
            "reward_ledger_refs_set_mismatch",
        ),
        (
            lambda packet: packet["inputs"]["reward_ledger_refs"].append(
                {"record_id": "forged", "record_hash": "f" * 64}
            ),
            "reward_ledger_refs_set_mismatch",
        ),
        (
            lambda packet: packet["inputs"].__setitem__("proof_packet_refs", ["f" * 64]),
            "proof_packet_refs_set_mismatch",
        ),
        (
            lambda packet: packet["inputs"].__setitem__("mutation_envelope_refs", ["e" * 64]),
            "mutation_envelope_refs_set_mismatch",
        ),
    ],
)
def test_ref_sets_must_match_embedded_reward_records_after_rehash(mutator, reason: str) -> None:
    packet = _packet()
    mutator(packet)
    packet["decision"] = DECISION_STOP_EVIDENCE
    packet["decision_reasons"] = [reason]
    packet["review_hash"] = compute_learning_effect_review_hash(packet)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert reason in validation.reasons


@pytest.mark.parametrize(
    ("loss_limits", "reason"),
    [
        (_loss_limits(breach="true"), "loss_limits_explicit_breach"),
        (
            {k: v for k, v in _loss_limits().items() if k != "max_cumulative_loss_usdt"},
            "loss_limits_max_cumulative_loss_usdt_missing",
        ),
        (
            {k: v for k, v in _loss_limits().items() if k != "max_consecutive_negative_windows"},
            "loss_limits_max_consecutive_negative_windows_missing",
        ),
        (
            _loss_limits(max_consecutive_negative_windows="2"),
            "loss_limits_malformed",
        ),
    ],
)
def test_malformed_loss_limits_stop_before_profitable_decision(
    loss_limits: dict,
    reason: str,
) -> None:
    packet = _packet(loss_limits=loss_limits)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_LOSS_CONTROL
    assert validation.reason == reason


def test_duplicate_reward_record_id_builder_raises() -> None:
    record = _record(1)
    duplicate = copy.deepcopy(record)

    with pytest.raises(LearningEffectReviewError, match="record_id_duplicate"):
        _packet(records=[record, duplicate])


def test_mixed_candidate_rejected_by_builder() -> None:
    first = _record(1)
    second = _record(2)
    second["candidate_identity"]["symbol"] = "BTCUSDT"
    second["record_hash"] = compute_reward_record_hash(second)

    with pytest.raises(LearningEffectReviewError, match="candidate_identity_symbol_mismatch"):
        _packet(records=[first, second])


def test_acceptance_report_hash_mismatch_when_required() -> None:
    packet = _packet(
        acceptance_report_refs=[{"path": "docs/source-report.md"}],
        review_policy={"min_sample_count": 2, "acceptance_report_required": True},
    )
    packet["inputs"]["acceptance_report_refs"][0]["acceptance_report_hash"] = "0" * 64
    packet["decision"] = DECISION_STOP_EVIDENCE
    packet["decision_reasons"] = ["acceptance_report_hash_mismatch"]
    packet["review_hash"] = compute_learning_effect_review_hash(packet)

    validation = validate_learning_effect_review(packet)

    assert validation.valid is True
    assert validation.decision == DECISION_STOP_EVIDENCE
    assert validation.reason == "acceptance_report_hash_mismatch"


def test_extract_reads_canonical_field_only() -> None:
    packet = _packet()

    assert extract_learning_effect_review({LEARNING_EFFECT_REVIEW_FIELD: packet}) == packet
    assert extract_learning_effect_review({"review": packet}) is None

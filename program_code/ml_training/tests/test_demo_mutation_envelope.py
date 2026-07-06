from __future__ import annotations

from pathlib import Path

import pytest

from ml_training.demo_mutation_envelope import (
    APPLICATION_STATUS_DRY_RUN,
    APPLICATION_STATUS_FAILED,
    APPLICATION_STATUS_SKIPPED,
    DEMO_MUTATION_ENVELOPE_FIELD,
    DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION,
    STATUS_AUDIT_ONLY,
    STATUS_COUNTABLE,
    STATUS_INVALID,
    build_demo_mutation_envelope,
    compute_demo_mutation_envelope_hash,
    extract_demo_mutation_envelope,
    stable_sha256_json,
    validate_demo_mutation_envelope,
)


def _valid_envelope(**overrides) -> dict:
    args = {
        "source_proposal_or_recommendation_id": "mlde-shadow-rec-123",
        "source_payload": {
            "recommendation_id": "mlde-shadow-rec-123",
            "strategy_name": "grid_trading",
            "symbol": "ETHUSDT",
        },
        "application_type": "strategy_params",
        "target": "grid_trading",
        "previous_snapshot": {"conf_scale": 1.0, "cooldown_ms": 120_000},
        "proposed_patch": {"conf_scale": 1.05},
        "max_delta_policy": {
            "policy_id": "demo_mutation_max_delta_policy_v1",
            "max_delta_pct": 0.10,
        },
        "governance_verdict": {
            "verdict": "approved_for_review",
            "review_allowed": True,
            "governance_packet_hash": "a" * 64,
        },
        "rollback_handle": {
            "rollback_id": "rollback-demo-123",
            "available": True,
            "snapshot_hash": "b" * 64,
        },
        "ipc_response": {"status": "applied", "result": {"accepted": True}},
        "ipc_response_status": "applied",
        "post_change_review": {
            "status": "passed",
            "review_hash": "c" * 64,
        },
        "proof_linkage": {
            "valid": True,
            "proof_packet_hash": "d" * 64,
        },
    }
    args.update(overrides)
    return build_demo_mutation_envelope(**args)


def test_valid_envelope_validates_and_hash_is_key_order_stable() -> None:
    envelope = _valid_envelope()

    validation = validate_demo_mutation_envelope(envelope)

    assert envelope["schema_version"] == DEMO_MUTATION_ENVELOPE_SCHEMA_VERSION
    assert validation.valid is True
    assert validation.status == STATUS_COUNTABLE
    assert validation.effective_learning_countable is True
    assert envelope["effective_learning_countable"] is True
    assert envelope["envelope_sha256"] == compute_demo_mutation_envelope_hash(envelope)
    assert extract_demo_mutation_envelope({DEMO_MUTATION_ENVELOPE_FIELD: envelope}) == envelope
    assert extract_demo_mutation_envelope({"envelope": envelope}) is None

    reordered = {
        "countability": envelope["countability"],
        "envelope_status": envelope["envelope_status"],
        "effective_learning_countable": envelope["effective_learning_countable"],
        "answers": dict(reversed(list(envelope["answers"].items()))),
        "proof_linkage": dict(reversed(list(envelope["proof_linkage"].items()))),
        "post_change_review": dict(reversed(list(envelope["post_change_review"].items()))),
        "ipc_response_status": envelope["ipc_response_status"],
        "ipc_response_hash": envelope["ipc_response_hash"],
        "rollback_handle": dict(reversed(list(envelope["rollback_handle"].items()))),
        "governance_verdict": dict(reversed(list(envelope["governance_verdict"].items()))),
        "max_delta_policy": dict(reversed(list(envelope["max_delta_policy"].items()))),
        "bounded_delta": [dict(reversed(list(envelope["bounded_delta"][0].items())))],
        "proposed_patch": dict(reversed(list(envelope["proposed_patch"].items()))),
        "previous_snapshot": dict(reversed(list(envelope["previous_snapshot"].items()))),
        "application": dict(reversed(list(envelope["application"].items()))),
        "target": envelope["target"],
        "application_type": envelope["application_type"],
        "source": dict(reversed(list(envelope["source"].items()))),
        "source_payload_hash": envelope["source_payload_hash"],
        "source_proposal_or_recommendation_id": envelope[
            "source_proposal_or_recommendation_id"
        ],
        "engine_mode": envelope["engine_mode"],
        "envelope_id": envelope["envelope_id"],
        "schema_version": envelope["schema_version"],
        "envelope_sha256": envelope["envelope_sha256"],
    }

    assert compute_demo_mutation_envelope_hash(envelope) == compute_demo_mutation_envelope_hash(
        reordered
    )
    assert stable_sha256_json({"b": 2, "a": {"x": True}}) == stable_sha256_json(
        {"a": {"x": True}, "b": 2}
    )


def test_e2_none_max_delta_bound_is_audit_only_not_countable() -> None:
    envelope = _valid_envelope(
        max_delta_policy={
            "policy_id": "demo_mutation_max_delta_policy_v1",
            "max_delta_pct": None,
        }
    )

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False
    assert envelope["effective_learning_countable"] is False
    assert "bounded_delta[0]_max_delta_policy_not_concrete" in validation.reasons
    assert "bounded_delta[0]_outside_max_delta_policy" in validation.reasons


def test_explicit_finite_max_delta_bound_remains_countable() -> None:
    envelope = _valid_envelope(
        max_delta_policy={
            "policy_id": "demo_mutation_absolute_delta_policy_v1",
            "max_delta": 0.10,
        }
    )

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_COUNTABLE
    assert validation.effective_learning_countable is True
    assert envelope["bounded_delta"][0]["max_delta"] == 0.10
    assert envelope["bounded_delta"][0]["within_policy"] is True


@pytest.mark.parametrize("bad_bound", [None, "nan", "inf", "not-a-number", -0.01, False])
def test_nonconcrete_max_delta_bounds_cannot_count(bad_bound: object) -> None:
    envelope = _valid_envelope(
        bounded_delta=[
            {
                "path": "conf_scale",
                "previous_value_present": True,
                "previous_value": 1.0,
                "proposed_value": 1.05,
                "delta": 0.05,
                "delta_pct": 0.05,
                "max_delta_pct": bad_bound,
                "within_policy": True,
            }
        ]
    )

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False
    assert "bounded_delta[0]_max_delta_policy_not_concrete" in validation.reasons


@pytest.mark.parametrize("engine_mode", ["paper", "live", "live_demo", "mainnet"])
def test_non_demo_live_or_mainnet_scope_rejected_or_non_countable(engine_mode: str) -> None:
    envelope = _valid_envelope(engine_mode=engine_mode)

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.effective_learning_countable is False
    assert validation.status == STATUS_INVALID
    assert validation.reason.startswith("non_demo_scope:")


@pytest.mark.parametrize(
    "alias_payload",
    [
        {"metadata": {"orderAuthorityGranted": True}},
        {"metadata": {"runtimeMutationAllowed": True}},
        {"metadata": {"databaseWriteAllowed": True}},
        {"metadata": {"costGateLowered": True}},
        {"metadata": {"strategyConfigWriteAllowed": True}},
        {"metadata": {"demoMutationAuthorityGranted": True}},
        {"metadata": {"secretAccess": True}},
        {"metadata": {"mainnetAccess": True}},
        {"metadata": [{"nestedGrant": {"dbWriteAllowed": "granted"}}]},
    ],
)
def test_nested_camel_case_authority_alias_rejected(alias_payload: dict) -> None:
    envelope = _valid_envelope()
    envelope.update(alias_payload)
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is False
    assert validation.status == STATUS_INVALID
    assert validation.authority_boundary_violation is True
    assert validation.reason.startswith("authority_boundary_violation:")


@pytest.mark.parametrize(
    "scope_payload",
    [
        {"metadata": {"candidateScope": "live"}},
        {"metadata": {"candidateEngineMode": "live_demo"}},
        {"metadata": [{"candidateEnvironment": "mainnet"}]},
        {"metadata": {"candidateEnv": "production"}},
    ],
)
def test_prefixed_non_demo_scope_alias_rejected(scope_payload: dict) -> None:
    envelope = _valid_envelope()
    envelope.update(scope_payload)
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is False
    assert validation.status == STATUS_INVALID
    assert validation.reason.startswith("non_demo_scope:")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"proposed_patch": {}},
        {"dedupe": True},
        {"dry_run": True},
        {"application_status": APPLICATION_STATUS_DRY_RUN},
        {"application_status": APPLICATION_STATUS_SKIPPED},
        {"application_status": APPLICATION_STATUS_FAILED},
        {"rollback_handle": None},
        {"proof_linkage": None},
        {"post_change_review": None},
    ],
)
def test_non_effective_cases_cannot_count(kwargs: dict) -> None:
    envelope = _valid_envelope(**kwargs)

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False
    assert envelope["effective_learning_countable"] is False


@pytest.mark.parametrize(
    "kwargs",
    [
        {
            "bounded_delta": [
                {
                    "path": "conf_scale",
                    "proposed_value": 1.05,
                    "delta": 0.05,
                    "max_delta_pct": 0.10,
                    "within_policy": True,
                }
            ]
        },
        {
            "bounded_delta": [
                {
                    "path": "conf_scale",
                    "previous_value": 1.0,
                    "delta": 0.05,
                    "max_delta_pct": 0.10,
                    "within_policy": True,
                }
            ]
        },
        {
            "bounded_delta": [
                {
                    "path": "conf_scale",
                    "previous_value": 1.0,
                    "proposed_value": 1.05,
                    "max_delta_pct": 0.10,
                    "within_policy": True,
                }
            ]
        },
    ],
)
def test_missing_previous_proposed_or_delta_cannot_count(kwargs: dict) -> None:
    envelope = _valid_envelope(**kwargs)

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is True
    assert validation.status == STATUS_AUDIT_ONLY
    assert validation.effective_learning_countable is False


def test_claimed_countable_without_required_evidence_is_invalid() -> None:
    envelope = _valid_envelope(rollback_handle=None)
    envelope["effective_learning_countable"] = True
    envelope["envelope_sha256"] = compute_demo_mutation_envelope_hash(envelope)

    validation = validate_demo_mutation_envelope(envelope)

    assert validation.valid is False
    assert validation.status == STATUS_INVALID
    assert validation.reason == "effective_learning_countable_claim_not_supported"


def test_no_forbidden_imports_or_side_effect_calls_in_helper() -> None:
    source = Path("program_code/ml_training/demo_mutation_envelope.py").read_text(
        encoding="utf-8"
    )

    forbidden = [
        "requests",
        "httpx",
        "urllib",
        "psycopg2",
        "asyncpg",
        "subprocess",
        "one_shot_ipc_call",
        "ipc_dispatch",
        "place_order",
        "create_order",
        "cancel_order",
        "submit_order",
        "INSERT INTO",
        "UPDATE learning",
        "DELETE FROM",
    ]
    for needle in forbidden:
        assert needle not in source

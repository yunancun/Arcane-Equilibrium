from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ML_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ML_ROOT.parents[1]
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from aiml_gate_receipt_validator import (  # noqa: E402
    aiml_effect_classifier_digest,
    artifact_self_digest,
    classify_required_effects,
    evidence_environment_identity_digest,
    github_policy_attestation_identity_digest,
    landing_scope_identity_digest,
    PROGRAM_GOVERNANCE_PATHS,
    S0_3_EXACT_OWNED_PATHS,
    SCHEMA_DIR,
    SCHEMA_FILES,
    session_attempt_identity_digest,
    terminal_receipt_sink_contract,
    validate_aiml_artifact,
)

import agent_governance_sealed_build as _sb  # noqa: E402 (HELPER_DIR 由 validator import 時已入 path)

# 共用 fixture builders(2000 行治理拆分:program-adoption / S2.4 測試已拆至 sibling 檔;
# builders 逐字搬入非收集的 testkit 模組)。
from ml_training.tests.aiml_gate_receipt_validator_testkit import (  # noqa: E402
    DIGEST_A,
    DIGEST_B,
    DIGEST_C,
    DIGEST_D,
    DIGEST_E,
    HEAD_A,
    _dependency_graph,
    _github_policy_attestation,
    _post_merge_attempt,
    _session_attempt,
)


NORMALIZER_PATH = (
    "helper_scripts/maintenance_scripts/agent_governance_closure_inputs.py"
)
EVIDENCE_VALIDATOR_PATH = (
    "helper_scripts/maintenance_scripts/agent_governance_evidence.py"
)


def test_closure_input_normalizer_is_bound_by_s0_3_source_manifests() -> None:
    assert NORMALIZER_PATH in PROGRAM_GOVERNANCE_PATHS
    assert NORMALIZER_PATH in S0_3_EXACT_OWNED_PATHS


def test_closure_evidence_validator_is_bound_by_s0_3_source_manifests() -> None:
    assert EVIDENCE_VALIDATOR_PATH in PROGRAM_GOVERNANCE_PATHS
    assert EVIDENCE_VALIDATOR_PATH in S0_3_EXACT_OWNED_PATHS


# S0.3 修改了 agent_governance_execution.py 的 compile_context carve-out，
# 該檔必須同時被 governance manifest 綁定並列為 S0.3 owned path，否則
# 採納 receipt 可在不綁定此已變更 governance 檔的情況下通過（E2 P1）。
EXECUTION_COMPILER_PATH = (
    "helper_scripts/maintenance_scripts/agent_governance_execution.py"
)


def test_closure_execution_compiler_is_bound_by_s0_3_source_manifests() -> None:
    assert EXECUTION_COMPILER_PATH in PROGRAM_GOVERNANCE_PATHS
    assert EXECUTION_COMPILER_PATH in S0_3_EXACT_OWNED_PATHS


def _landing_scope() -> dict:
    environment = {
        "environment_id": DIGEST_A,
        "mode": "DEMO",
        "account_or_simulator": "bybit-demo",
        "fee_schedule": "demo-fees-v1",
        "execution_policy": "advisory-only-v1",
    }
    environment["environment_id"] = evidence_environment_identity_digest(environment)
    scope = {
        "schema_version": "landing_scope_v1",
        "landing_scope_id": DIGEST_A,
        "scope_kind": "INSTANCE",
        "platform_scope": {
            "venue": "BYBIT_DEMO",
            "instrument_class": "PERPETUAL",
            "strategy_family": "scanner_advisory",
        },
        "policy_surface_id": DIGEST_B,
        "decision_cells": [
            {
                "symbol": "BTCUSDT",
                "side": "LONG",
                "horizon": "5m",
                "regime": "NORMAL",
            }
        ],
        "evidence_environments": [environment],
        "promotion_edges": [],
    }
    scope["landing_scope_id"] = landing_scope_identity_digest(scope)
    return scope


def test_landing_scope_accepts_exact_platform_cell_and_environment_identity() -> None:
    assert validate_aiml_artifact(_landing_scope()) == []


def test_landing_scope_rejects_unsorted_or_duplicate_decision_cells() -> None:
    unsorted_scope = _landing_scope()
    unsorted_scope["decision_cells"] = [
        {"symbol": "ETHUSDT", "side": "LONG", "horizon": "5m", "regime": "NORMAL"},
        {"symbol": "BTCUSDT", "side": "LONG", "horizon": "5m", "regime": "NORMAL"},
    ]
    unsorted_scope["landing_scope_id"] = landing_scope_identity_digest(
        unsorted_scope
    )
    duplicate_scope = deepcopy(unsorted_scope)
    duplicate_scope["decision_cells"] = [
        deepcopy(unsorted_scope["decision_cells"][1]),
        deepcopy(unsorted_scope["decision_cells"][1]),
    ]
    duplicate_scope["landing_scope_id"] = landing_scope_identity_digest(
        duplicate_scope
    )

    assert "landing scope decision_cells must be sorted and unique" in (
        validate_aiml_artifact(unsorted_scope)
    )
    assert any(
        "not unique" in error
        for error in validate_aiml_artifact(duplicate_scope)
    )


def test_landing_scope_rejects_promotion_edge_to_unknown_environment() -> None:
    scope = _landing_scope()
    scope["promotion_edges"] = [{
        "from_environment_id": scope["evidence_environments"][0]["environment_id"],
        "to_environment_id": DIGEST_A,
        "authority_receipt_digest": DIGEST_B,
    }]
    scope["landing_scope_id"] = landing_scope_identity_digest(scope)

    assert "landing scope promotion edge references an unknown environment" in (
        validate_aiml_artifact(scope)
    )


def test_landing_scope_rejects_self_promotion_edge() -> None:
    scope = _landing_scope()
    environment_id = scope["evidence_environments"][0]["environment_id"]
    scope["promotion_edges"] = [{
        "from_environment_id": environment_id,
        "to_environment_id": environment_id,
        "authority_receipt_digest": DIGEST_B,
    }]
    scope["landing_scope_id"] = landing_scope_identity_digest(scope)

    assert "landing scope promotion edge cannot target itself" in (
        validate_aiml_artifact(scope)
    )


def test_landing_scope_rejects_cyclic_environment_promotion() -> None:
    scope = _landing_scope()
    second = {
        "environment_id": DIGEST_A,
        "mode": "SHADOW",
        "account_or_simulator": "shadow-simulator",
        "fee_schedule": "shadow-fees-v1",
        "execution_policy": "shadow-only-v1",
    }
    second["environment_id"] = evidence_environment_identity_digest(second)
    scope["evidence_environments"] = sorted(
        [scope["evidence_environments"][0], second],
        key=lambda environment: environment["environment_id"],
    )
    first_id, second_id = [
        environment["environment_id"]
        for environment in scope["evidence_environments"]
    ]
    scope["promotion_edges"] = sorted(
        [
            {
                "from_environment_id": first_id,
                "to_environment_id": second_id,
                "authority_receipt_digest": DIGEST_A,
            },
            {
                "from_environment_id": second_id,
                "to_environment_id": first_id,
                "authority_receipt_digest": DIGEST_B,
            },
        ],
        key=lambda edge: (
            edge["from_environment_id"],
            edge["to_environment_id"],
            edge["authority_receipt_digest"],
        ),
    )
    scope["landing_scope_id"] = landing_scope_identity_digest(scope)

    assert "landing scope promotion graph contains a cycle" in (
        validate_aiml_artifact(scope)
    )


def test_session_attempt_binds_claim_lease_source_paths_and_governance_generation() -> None:
    assert validate_aiml_artifact(
        _session_attempt(), now="2026-07-21T09:00:00Z"
    ) == []


def test_expired_active_attempt_requires_recovery_state() -> None:
    expired = _session_attempt()
    expired["self_digest"] = artifact_self_digest(expired)
    errors = validate_aiml_artifact(expired, now="2026-07-21T13:00:00Z")
    assert "expired session attempt must enter RECOVERY_REQUIRED" in errors

    expired["status"] = "RECOVERY_REQUIRED"
    expired["self_digest"] = artifact_self_digest(expired)
    assert validate_aiml_artifact(
        expired, now="2026-07-21T13:00:00Z"
    ) == []


def test_session_attempt_rejects_out_of_order_lease_timestamps() -> None:
    attempt = _session_attempt()
    attempt["lease"]["heartbeat_at"] = "2026-07-21T13:00:00Z"
    attempt["self_digest"] = artifact_self_digest(attempt)

    assert "session attempt lease timestamps are out of order" in (
        validate_aiml_artifact(attempt, now="2026-07-21T09:00:00Z")
    )


def test_session_attempt_rejects_writer_overflow_and_path_overlap() -> None:
    paths = sorted([
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/schemas/aiml_gate_receipts/landing_scope_v1.schema.json",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
    ])
    overflow = _session_attempt()
    overflow["path_manifest"] = paths
    overflow["work_package"]["owned_path_manifest"] = paths
    overflow["dag_nodes"] = [
        {
            "node_id": f"writer-{index}",
            "node_class": "work",
            "permission": "source_writer",
            "requires": [],
            "writer_paths": [path],
        }
        for index, path in enumerate(paths)
    ]
    overflow["native_admission"]["node_id"] = "writer-0"
    overflow["self_digest"] = artifact_self_digest(overflow)
    assert "session attempt admits more than two writer nodes" in (
        validate_aiml_artifact(overflow, now="2026-07-21T09:00:00Z")
    )

    overlap = deepcopy(overflow)
    overlap["dag_nodes"] = overlap["dag_nodes"][:2]
    overlap["dag_nodes"][1]["writer_paths"] = [paths[0]]
    overlap["self_digest"] = artifact_self_digest(overlap)
    assert "session attempt writer path ownership overlaps" in (
        validate_aiml_artifact(overlap, now="2026-07-21T09:00:00Z")
    )


def test_session_attempt_rejects_unsorted_or_out_of_manifest_writer_paths() -> None:
    attempt = _session_attempt()
    paths = sorted([
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
    ])
    attempt["path_manifest"] = paths
    attempt["work_package"]["owned_path_manifest"] = paths
    attempt["dag_nodes"][0]["writer_paths"] = list(reversed(paths))
    attempt["self_digest"] = artifact_self_digest(attempt)
    assert "session attempt writer path ownership must be sorted and unique" in (
        validate_aiml_artifact(attempt, now="2026-07-21T09:00:00Z")
    )

    attempt["dag_nodes"][0]["writer_paths"] = [
        "program_code/ml_training/schemas/aiml_gate_receipts/landing_scope_v1.schema.json"
    ]
    attempt["self_digest"] = artifact_self_digest(attempt)
    assert "session attempt writer paths exceed path_manifest" in (
        validate_aiml_artifact(attempt, now="2026-07-21T09:00:00Z")
    )


def test_session_attempt_rejects_attempt_bootstrap_or_native_binding_drift() -> None:
    attempt_key_drift = _session_attempt()
    attempt_key_drift["attempt_key"]["attempt"] = 9
    attempt_key_drift["attempt_id"] = session_attempt_identity_digest(
        attempt_key_drift
    )
    attempt_key_drift["self_digest"] = artifact_self_digest(attempt_key_drift)
    assert "session attempt_key differs from its canonical row fields" in (
        validate_aiml_artifact(
            attempt_key_drift, now="2026-07-21T09:00:00Z"
        )
    )

    bootstrap_drift = _session_attempt()
    bootstrap_drift["bootstrap_admission"]["writer_lease_id"] = "other-lease"
    bootstrap_drift["self_digest"] = artifact_self_digest(bootstrap_drift)
    assert "session bootstrap writer lease binding is invalid" in (
        validate_aiml_artifact(bootstrap_drift, now="2026-07-21T09:00:00Z")
    )

    native_drift = _session_attempt()
    native_drift["native_admission"]["permission"] = "read_only"
    native_drift["self_digest"] = artifact_self_digest(native_drift)
    assert "session native admission does not match exactly one DAG node" in (
        validate_aiml_artifact(native_drift, now="2026-07-21T09:00:00Z")
    )


def test_dependency_graph_accepts_current_and_immutable_receipt_lineage() -> None:
    assert validate_aiml_artifact(
        _dependency_graph(), now="2026-07-21T09:30:00Z"
    ) == []


def test_current_state_ttl_is_stale_at_expiry_and_invalidates_root() -> None:
    errors = validate_aiml_artifact(
        _dependency_graph(), now="2026-07-21T10:00:00Z"
    )

    assert "receipt github-repository-state CURRENT_STATE_TTL is stale" in errors
    assert "receipt dependency graph root is invalidated by dependency state" in errors


def test_effect_time_authority_rejects_effect_at_expiry() -> None:
    graph = _dependency_graph()
    authority = next(
        receipt for receipt in graph["receipts"]
        if receipt["receipt_id"] == "github-policy"
    )
    authority["effect_at"] = authority["expires_at"]
    graph["self_digest"] = artifact_self_digest(graph)

    assert (
        "receipt github-policy EFFECT_TIME_AUTHORITY effect is outside its window"
        in validate_aiml_artifact(graph, now="2026-07-21T09:30:00Z")
    )


def test_immutable_consumed_effect_rejects_authority_or_time_substitution() -> None:
    graph = _dependency_graph()
    consumed_effect = next(
        receipt for receipt in graph["receipts"]
        if receipt["receipt_id"] == "S0.3"
    )
    consumed_effect["authority_receipt_digest"] = DIGEST_A
    graph["self_digest"] = artifact_self_digest(graph)
    assert "receipt S0.3 immutable effect authority binding is invalid" in (
        validate_aiml_artifact(graph, now="2026-07-21T09:30:00Z")
    )

    graph = _dependency_graph()
    consumed_effect = next(
        receipt for receipt in graph["receipts"]
        if receipt["receipt_id"] == "S0.3"
    )
    consumed_effect["consumed_at"] = "2026-07-21T09:29:59Z"
    graph["self_digest"] = artifact_self_digest(graph)
    assert "receipt S0.3 IMMUTABLE_CONSUMED_EFFECT time binding is invalid" in (
        validate_aiml_artifact(graph, now="2026-07-21T09:30:00Z")
    )


def test_immutable_lineage_rejects_expiry_or_effect_fields() -> None:
    graph = _dependency_graph()
    lineage = next(
        receipt for receipt in graph["receipts"]
        if receipt["receipt_id"] == "S0.1"
    )
    lineage["expires_at"] = "2026-07-22T00:00:00Z"
    graph["self_digest"] = artifact_self_digest(graph)

    assert "receipt S0.1 IMMUTABLE_LINEAGE fields are invalid" in (
        validate_aiml_artifact(graph, now="2026-07-21T09:30:00Z")
    )


def _effect_authority_only_graph() -> dict:
    graph = _dependency_graph()
    graph["receipts"] = [
        receipt for receipt in graph["receipts"]
        if receipt["receipt_id"] != "github-repository-state"
    ]
    graph["edges"] = [
        edge for edge in graph["edges"]
        if edge["dependency_receipt_id"] != "github-repository-state"
    ]
    graph["self_digest"] = artifact_self_digest(graph)
    return graph


def test_natural_authority_expiry_survives_but_revocation_invalidates_root() -> None:
    legally_consumed = _effect_authority_only_graph()
    assert validate_aiml_artifact(
        legally_consumed, now="2026-07-21T11:00:00Z"
    ) == []

    for state in ("REVOKED", "COMPROMISED"):
        invalidated = deepcopy(legally_consumed)
        authority = next(
            receipt for receipt in invalidated["receipts"]
            if receipt["receipt_id"] == "github-policy"
        )
        authority["state"] = state
        invalidated["self_digest"] = artifact_self_digest(invalidated)
        errors = validate_aiml_artifact(
            invalidated, now="2026-07-21T11:00:00Z"
        )
        assert f"receipt github-policy is {state.lower()}" in errors
        assert "receipt dependency graph root is invalidated by dependency state" in errors


def test_s0_3_source_build_cannot_downgrade_post_merge_external_attestation() -> None:
    classification = classify_required_effects(
        _session_attempt(),
        classified_at="2026-07-21T09:00:00Z",
    )

    assert classification["required_effects"] == [
        {
            "effect_class": "EXTERNAL_READONLY_ATTESTATION",
            "status": "DEFERRED_TO_POST_MERGE_FINALIZATION",
            "adapter_id": "github_repository_policy_attestation_v1",
            "actor_node_id": "github_policy_observer",
            "rollback_contract": "NOT_APPLICABLE_READ_ONLY",
            "independent_postcheck_node_id": "aiml_program_adoption_validator",
        }
    ]
    assert validate_aiml_artifact(classification) == []


def test_required_effect_classifier_rejects_unknown_session_instead_of_none() -> None:
    unknown = deepcopy(_session_attempt())
    unknown["session_id"] = "S9.9"

    with pytest.raises(ValueError, match="unsupported AIML work package"):
        classify_required_effects(
            unknown,
            classified_at="2026-07-21T09:00:00Z",
        )


def test_required_effect_classifier_rejects_missing_work_package() -> None:
    attempt = _session_attempt()
    attempt.pop("work_package")

    with pytest.raises(ValueError, match="work_package is required"):
        classify_required_effects(
            attempt,
            classified_at="2026-07-21T09:00:00Z",
        )


def test_required_effect_classifier_rejects_forbidden_ml_runtime_path_under_allowed_prefix() -> None:
    attempt = _session_attempt()
    forbidden_path = (
        "docs/execution_plan/ai_ml_landing/ML5-runtime-deploy.md"
    )
    attempt["path_manifest"] = [forbidden_path]
    attempt["work_package"]["owned_path_manifest"] = [forbidden_path]

    with pytest.raises(ValueError, match="forbidden owned path"):
        classify_required_effects(
            attempt,
            classified_at="2026-07-21T09:00:00Z",
        )


def test_required_effect_classifier_rejects_prefix_path_traversal() -> None:
    attempt = _session_attempt()
    traversal_path = "docs/execution_plan/ai_ml_landing/../../unowned.md"
    attempt["path_manifest"] = [traversal_path]
    attempt["work_package"]["owned_path_manifest"] = [traversal_path]

    with pytest.raises(ValueError, match="forbidden owned path"):
        classify_required_effects(
            attempt,
            classified_at="2026-07-21T09:00:00Z",
        )


@pytest.mark.parametrize("mutation", ["missing", "extra"])
def test_required_effect_classifier_requires_exact_direct_interfaces(
    mutation: str,
) -> None:
    attempt = _session_attempt()
    interfaces = attempt["work_package"]["direct_interfaces"]
    if mutation == "missing":
        interfaces.pop()
    else:
        interfaces.append("runtime_deploy_adapter_v1")

    with pytest.raises(ValueError, match="direct_interfaces differ from exact"):
        classify_required_effects(
            attempt,
            classified_at="2026-07-21T09:00:00Z",
        )


def test_required_effect_classifier_rejects_generic_side_effect_relabel() -> None:
    attempt = _session_attempt()
    attempt["work_package"]["side_effect_class"] = "none"

    with pytest.raises(ValueError, match="generic side_effect_class is invalid"):
        classify_required_effects(
            attempt,
            classified_at="2026-07-21T09:00:00Z",
        )


def test_required_effect_classification_rejects_caller_downgrade_to_none() -> None:
    classification = classify_required_effects(
        _session_attempt(),
        classified_at="2026-07-21T09:00:00Z",
    )
    classification["required_effects"] = [{
        "effect_class": "NONE",
        "status": "NOT_REQUIRED",
        "adapter_id": "none",
        "actor_node_id": "none",
        "rollback_contract": "NOT_APPLICABLE_NO_EFFECT",
        "independent_postcheck_node_id": "none",
    }]

    assert "AIML required effects differ from classifier output" in (
        validate_aiml_artifact(classification)
    )


def test_post_merge_classifier_derives_external_attestation_from_exact_facts() -> None:
    classification = classify_required_effects(
        _post_merge_attempt(),
        classified_at="2026-07-21T09:00:00Z",
    )

    assert classification["required_effects"][0]["status"] == "REQUIRED_PENDING"
    assert classification["required_effects"][0]["effect_class"] == (
        "EXTERNAL_READONLY_ATTESTATION"
    )
    assert validate_aiml_artifact(classification) == []


@pytest.mark.parametrize(
    "side_effect_class", ["public_web_read", "private_external_contact"]
)
def test_post_merge_classifier_rejects_contact_as_attestation_proof(
    side_effect_class: str,
) -> None:
    attempt = _post_merge_attempt()
    attempt["work_package"]["side_effect_class"] = side_effect_class

    with pytest.raises(ValueError, match="generic side_effect_class is invalid"):
        classify_required_effects(
            attempt,
            classified_at="2026-07-21T09:00:00Z",
        )


# Finding 3:相位條件 lease 不變量鎖。SOURCE_BUILD 持 writer lease 且禁 read_only
# admission;POST_MERGE 為唯讀收尾,禁任何 writer lease 且必須攜 read_only admission。
def test_post_merge_attempt_binds_read_only_admission_without_writer_lease() -> None:
    assert validate_aiml_artifact(
        _post_merge_attempt(), now="2026-07-21T09:30:00Z"
    ) == []


def test_post_merge_attempt_rejects_residual_writer_lease() -> None:
    attempt = _post_merge_attempt()
    attempt["lease"] = {
        "lease_id": "lease-s0-3-attempt-2",
        "epoch": 2,
        "acquired_at": "2026-07-21T09:00:00Z",
        "heartbeat_at": "2026-07-21T09:15:00Z",
        "expires_at": "2026-07-21T10:00:00Z",
    }
    attempt["self_digest"] = artifact_self_digest(attempt)

    assert any(
        "matches forbidden not-schema" in error
        for error in validate_aiml_artifact(attempt, now="2026-07-21T09:30:00Z")
    )


def test_post_merge_attempt_rejects_residual_bootstrap_writer_lease_id() -> None:
    attempt = _post_merge_attempt()
    attempt["bootstrap_admission"]["writer_lease_id"] = "lease-s0-3-attempt-2"
    attempt["self_digest"] = artifact_self_digest(attempt)

    assert any(
        "$.bootstrap_admission: matches forbidden not-schema" in error
        for error in validate_aiml_artifact(attempt, now="2026-07-21T09:30:00Z")
    )


def test_post_merge_read_only_admission_rejects_heartbeat_before_admission() -> None:
    attempt = _post_merge_attempt()
    attempt["read_only_admission"]["heartbeat_at"] = "2026-07-21T08:59:00Z"
    attempt["self_digest"] = artifact_self_digest(attempt)

    assert "post-merge read-only admission timestamps are out of order" in (
        validate_aiml_artifact(attempt, now="2026-07-21T09:30:00Z")
    )


def test_source_build_attempt_rejects_read_only_admission() -> None:
    attempt = _session_attempt()
    attempt["read_only_admission"] = {
        "epoch": 1,
        "admitted_at": "2026-07-21T08:38:09Z",
        "heartbeat_at": "2026-07-21T08:38:09Z",
        "read_only": True,
    }
    attempt["self_digest"] = artifact_self_digest(attempt)

    assert any(
        "matches forbidden not-schema" in error
        for error in validate_aiml_artifact(attempt, now="2026-07-21T09:00:00Z")
    )


def test_terminal_sink_is_contract_only_until_s1_2_implements_it() -> None:
    contract = terminal_receipt_sink_contract()

    assert contract["status"] == "CONTRACT_ONLY"
    assert contract["allowed_terminal_receipt_types"] == [
        "aiml_module_landed_for_trading_receipt_v1",
        "aiml_platform_no_candidate_receipt_v1",
    ]
    assert contract["implementation_owner_session"] == "S1.2"
    assert contract["implementation_paths"] == []
    assert contract["actor_contract"]["same_actor_allowed"] is False
    assert validate_aiml_artifact(contract) == []


def test_github_ruleset_attestation_accepts_zero_approval_with_exact_denials() -> None:
    assert validate_aiml_artifact(
        _github_policy_attestation(), now="2026-07-21T11:30:00Z"
    ) == []


def test_github_ruleset_attestation_rejects_missing_required_checks() -> None:
    attestation = _github_policy_attestation()
    attestation["ruleset"]["required_checks"] = []
    attestation["attestation_id"] = github_policy_attestation_identity_digest(
        attestation
    )
    attestation["self_digest"] = artifact_self_digest(attestation)

    assert any(
        "required_checks" in error and "shorter than minItems" in error
        for error in validate_aiml_artifact(
            attestation, now="2026-07-21T09:30:00Z"
        )
    )


def test_github_ruleset_attestation_rejects_secret_like_content() -> None:
    attestation = _github_policy_attestation()
    attestation["evidence_captures"][0]["url"] += (
        "?access_token=github_pat_1234567890abcdefghijklmnop"
    )
    attestation["attestation_id"] = github_policy_attestation_identity_digest(
        attestation
    )
    attestation["self_digest"] = artifact_self_digest(attestation)

    assert "GitHub repository-policy attestation contains secret-like content" in (
        validate_aiml_artifact(attestation, now="2026-07-21T09:30:00Z")
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("non_fast_forward_allowed", True),
        ("deletion_allowed", True),
        ("bypass_actors", ["RepositoryRole:admin"]),
        ("current_user_can_bypass", "always"),
    ],
)
def test_github_ruleset_attestation_rejects_force_delete_or_bypass(
    field: str,
    value: object,
) -> None:
    attestation = _github_policy_attestation()
    attestation["ruleset"][field] = value
    attestation["attestation_id"] = github_policy_attestation_identity_digest(
        attestation
    )
    attestation["self_digest"] = artifact_self_digest(attestation)

    assert validate_aiml_artifact(attestation, now="2026-07-21T09:30:00Z")


def test_github_ruleset_attestation_rejects_stale_effect_time() -> None:
    attestation = _github_policy_attestation()
    attestation["effect_at"] = attestation["expires_at"]
    attestation["attestation_id"] = github_policy_attestation_identity_digest(
        attestation
    )
    attestation["self_digest"] = artifact_self_digest(attestation)

    assert (
        "GitHub repository-policy effect time is outside its authority window"
        in validate_aiml_artifact(attestation, now="2026-07-21T10:05:00Z")
    )


def test_github_ruleset_attestation_rejects_default_branch_exclusion() -> None:
    attestation = _github_policy_attestation()
    attestation["ruleset"]["ref_excludes"] = ["~DEFAULT_BRANCH"]
    attestation["attestation_id"] = github_policy_attestation_identity_digest(
        attestation
    )
    attestation["self_digest"] = artifact_self_digest(attestation)

    assert "GitHub ruleset excludes the default branch" in validate_aiml_artifact(
        attestation,
        now="2026-07-21T09:30:00Z",
    )


# ── S2-WP1(S2.3 LR2 delegation + digest-drift guard;B.1 tests a-e) ───────────
_S23_RECEIPTS_DIR = REPO_ROOT / "docs/execution_plan/ai_ml_landing/receipts"


def _committed_s23_pair() -> tuple[dict, dict]:
    sealed = json.loads(
        (_S23_RECEIPTS_DIR / "S2.3-sealed-build-receipt-v1.json").read_text(encoding="utf-8")
    )
    identity = json.loads(
        (_S23_RECEIPTS_DIR / "S2.3-expected-identity-receipt-v1.json").read_text(encoding="utf-8")
    )
    return sealed, identity


def _wallclock_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def test_classifier_digest_is_byte_frozen_after_registering_s23_schemas() -> None:
    # (d) digest-drift guard:註冊新 schema 只動 SCHEMA_FILES(schema 查找),不動
    # aiml_effect_classifier_digest() 的六個 S0.3 常量輸入 → 分類身分 digest 位元不變。
    assert aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )


def test_s23_and_v2_schema_files_resolve_via_schema_files() -> None:
    # (e) 兩份 S2.3 schema(+ v2 source-compat)皆經 SCHEMA_FILES 解析到磁碟上的真實檔。
    for key in (
        "sealed_build_receipt_v1",
        "expected_identity_receipt_v1",
        "source_compatibility_receipt_v2",
    ):
        assert key in SCHEMA_FILES, key
        assert (SCHEMA_DIR / SCHEMA_FILES[key]).is_file(), key


def test_central_gate_passes_committed_s23_receipts_at_any_wallclock() -> None:
    # (a) round-trip + 無 freshness time-bomb:S2.3 是 BUILD-IDENTITY / source 產物(非 effect-class)。
    # committed receipt 帶固定 30-min TTL,但中央閘刻意不施加 wall-clock 新鮮度窗 → 在真牆鐘 now、
    # now=None、及不傳 now 皆 validate == []。真 recency 證明留在 learning-runtime-sealed-build CI job。
    sealed, identity = _committed_s23_pair()
    wallclock = _wallclock_now()  # 遠超 receipt 的 00:00–00:30Z 窗
    for receipt in (sealed, identity):
        assert validate_aiml_artifact(receipt, now=wallclock) == []
        assert validate_aiml_artifact(receipt, now=None) == []
        assert validate_aiml_artifact(receipt) == []


def test_central_gate_round_trips_freshly_built_s23_receipts_at_wallclock() -> None:
    # SSOT builder 造的 S2.3 receipt 亦經中央閘委派 validate == [](真牆鐘,不 gate 新鮮度)。
    sealed, identity = _sb.emit_s23_receipts(observation_time="2026-07-24T00:00:00+00:00")
    wallclock = _wallclock_now()
    assert validate_aiml_artifact(sealed, now=wallclock) == []
    assert validate_aiml_artifact(identity, now=wallclock) == []


def test_central_gate_rejects_sealed_const_false_forgery_regardless_of_clock() -> None:
    # (b) forgery:翻 load_verified_on_target=True 後只重封外層 self_digest → 中央閘拒(與時鐘無關)。
    # 斷言「精確欄位 + 訊息」,避免未來 refactor 讓它以別的錯誤誤過(E4 nit-1)。
    sealed, _identity = _committed_s23_pair()
    forged = deepcopy(sealed)
    assert forged["native_library_inventory"], "committed lock projects native libs"
    forged["native_library_inventory"][0]["load_verified_on_target"] = True
    forged["self_digest"] = _sb.receipt_digest(forged)
    for errs in (validate_aiml_artifact(forged, now=_wallclock_now()),
                 validate_aiml_artifact(forged, now=None)):
        assert any(
            "native_library_inventory[0].load_verified_on_target: expected const False" in e
            for e in errs
        ), errs


def test_central_gate_rejects_identity_production_flag_forgery_regardless_of_clock() -> None:
    # (b) forgery:翻 production_provisioned.uid=True 後只重封外層 self_digest → 中央閘拒(精確訊息)。
    _sealed, identity = _committed_s23_pair()
    forged = deepcopy(identity)
    forged["production_provisioned"]["uid"] = True
    forged["self_digest"] = _sb.receipt_digest(forged)
    for errs in (validate_aiml_artifact(forged, now=_wallclock_now()),
                 validate_aiml_artifact(forged, now=None)):
        assert any(
            "production_provisioned.uid: expected const False" in e for e in errs
        ), errs


def test_v2_dependency_lock_shape_guard_rejects_malformed_object() -> None:
    # E4 nit-2b(直接單測 Python 形狀 guard;schema 通常先攔,此處直呼確保 guard 自身有牙):
    # dependency_lock 非 {spec_digest, lock_digest} 物件 → 特定訊息;正確形狀 → 無錯。
    from aiml_gate_receipt_validator import (
        _source_compatibility_receipt_v2_dependency_lock_errors as _guard,
    )

    def _artifact(dependency_lock: object) -> dict:
        return {
            "learning_runtime_manifest": {
                "training_contract": {"components": {"dependency_lock": dependency_lock}}
            }
        }

    for bad in (
        None,
        "x",
        {"spec_digest": "a"},
        {"spec_digest": "a", "lock_digest": "b", "extra": "c"},
    ):
        errs = _guard(_artifact(bad))
        assert any(
            "dependency_lock must be a {spec_digest, lock_digest} object" in e for e in errs
        ), (bad, errs)
    ok = _artifact({"spec_digest": "sha256:" + "a" * 64, "lock_digest": "sha256:" + "b" * 64})
    assert _guard(ok) == []


# ── S2.4 · WP4 · W0(W0b)admission / wave-exit schema + derivation ─────────────
import hashlib as _hashlib  # noqa: E402
import subprocess as _subprocess  # noqa: E402

import aiml_gate_receipt_validator as _w0  # noqa: E402


def _w0_current_head() -> str:
    return _subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _w0_admission_receipt() -> dict:
    module_bytes = (REPO_ROOT / _w0._TRUSTED_HOST_MODULE_PATH).read_bytes()
    test_bytes = (REPO_ROOT / _w0._TRUSTED_HOST_TEST_PATH).read_bytes()
    receipt = {
        "schema_version": "s2_4_source_admission_receipt_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "work_package": "WP4",
        "wave": "W0",
        "source_head": _w0_current_head(),
        "predecessor_heads": dict(_w0._PREDECESSOR_HEADS),
        "three_head_projection_digest": _w0.three_head_projection_digest(),
        "trust_pin_digests": {
            "trusted_host_module_blob": _w0.git_blob_sha1(module_bytes),
            "trusted_host_module_sha256": "sha256:" + _hashlib.sha256(module_bytes).hexdigest(),
            "independent_test_blob": _w0.git_blob_sha1(test_bytes),
            "independent_test_sha256": "sha256:" + _hashlib.sha256(test_bytes).hexdigest(),
            "operator_fingerprint": _w0._OPERATOR_FINGERPRINT,
        },
        "s2_0_driver_reachability_proof": {
            "adapter_id": "pg_observer_bootstrap_adapter_v1",
            "registry_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
            "unconditional_production_pending_removed": True,
            "driver_protocol_present": True,
            "production_success_status": "APPLIED",
        },
        "wp3_system_unit_alignment_proof": {
            "lifecycle_owner": "host_system_manager",
            "systemctl_user_absent": True,
            "role": "aiml_engine_scanner",
            "database": "trading_ai",
        },
        "frozen_classifier_digest": _w0.aiml_effect_classifier_digest(),
        "component_classifier_v1_digest": _w0.aiml_component_effect_class_matrix_digest(),
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        # 由 code-owned W0 負向測試清單「重算」而得(綁定非回聲);見 derive_source_admission_status。
        "negative_tests_pass": _w0.w0_negative_test_manifest_digest(),
    }
    receipt["self_digest"] = _w0.artifact_self_digest(receipt)
    return receipt


def _w0_wave_exit_receipt(admission: dict) -> dict:
    receipt = {
        "schema_version": "s2_4_wave_exit_receipt_v1",
        "wave": "W0",
        "predecessor_wave_receipt_digest": None,
        "source_admission_receipt_digest": admission["self_digest"],
        "source_head": admission["source_head"],
        "owned_path_manifest_digest": _w0.canonical_digest(sorted(_w0._W0_OWNED_PATHS)),
        # T1(a):owned_path_diff_digest 由 W0 owned-path 內容投影再導出(非任意佔位字面量)。
        "owned_path_diff_digest": _w0.w0_owned_path_diff_digest(),
        "exported_abi_digest": _w0.canonical_digest(_w0._W0_EXPORTED_ABI),
        # T1(b):test/capture/review 三類皆為「非空」合法 digest list(空/任意值不得導 PASS)。
        "test_digests": [_w0.canonical_digest(["w0-tests"])],
        "capture_digests": [_w0.canonical_digest(["w0-capture"])],
        "review_fragment_digests": [_w0.canonical_digest(["w0-review"])],
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    receipt["self_digest"] = _w0.artifact_self_digest(receipt)
    return receipt


def test_w0_schema_files_resolve_via_schema_files() -> None:
    for key in ("s2_4_source_admission_receipt_v1", "s2_4_wave_exit_receipt_v1"):
        assert key in SCHEMA_FILES, key
        assert (SCHEMA_DIR / SCHEMA_FILES[key]).is_file(), key


def test_w0_admission_round_trip_and_self_digest() -> None:
    receipt = _w0_admission_receipt()
    # canonical self-digest binds the whole receipt (integrity only).
    assert receipt["self_digest"] == artifact_self_digest(receipt)
    # central gate derives ADMITTED → validate returns [].
    assert validate_aiml_artifact(receipt) == []
    assert _w0.derive_source_admission_status(receipt) == {
        "status": "ADMITTED",
        "reasons": [],
    }


def test_w0_wave_exit_round_trip_and_self_digest() -> None:
    admission = _w0_admission_receipt()
    wave_exit = _w0_wave_exit_receipt(admission)
    assert wave_exit["self_digest"] == artifact_self_digest(wave_exit)
    # central gate validates the self-contained structure.
    assert validate_aiml_artifact(wave_exit) == []
    # full PASS with the bound admission pair.
    assert _w0.derive_wave_exit_status(
        wave_exit, source_admission_receipt=admission
    ) == {"status": "PASS", "reasons": []}


def test_frozen_classifier_pin_holds_after_w0_schema_files_additions() -> None:
    # the SCHEMA_FILES additions (schema lookup) leave the six S0.3 classifier constants
    # untouched → the frozen digest is byte-identical to the contract's pin.
    assert aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert len(PROGRAM_GOVERNANCE_PATHS) == len(set(PROGRAM_GOVERNANCE_PATHS))


def test_w0_central_gate_rejects_self_declared_status() -> None:
    receipt = _w0_admission_receipt()
    receipt["status"] = "ADMITTED"
    receipt["self_digest"] = artifact_self_digest(receipt)
    # closed schema (additionalProperties:false) rejects the extra caller field.
    assert validate_aiml_artifact(receipt) != []
    # derivation also rejects it independently, before any re-derivation.
    result = _w0.derive_source_admission_status(receipt)
    assert result["status"] == "NOT_ADMITTED"
    assert any("must not self-declare status" in r for r in result["reasons"])


def test_w0_derivation_tamper_rejections() -> None:
    base = _w0_admission_receipt()
    # (a) tamper the S2.0 registry-status echo in the receipt.
    a = deepcopy(base)
    a["s2_0_driver_reachability_proof"]["registry_status"] = "declared_production_apply_disabled"
    a["self_digest"] = artifact_self_digest(a)
    ra = _w0.derive_source_admission_status(a)
    assert ra["status"] == "NOT_ADMITTED"
    assert any("s2_0_driver_reachability_proof" in r for r in ra["reasons"])
    # (b) tamper the WP3 role property.
    b = deepcopy(base)
    b["wp3_system_unit_alignment_proof"]["role"] = "postgres"
    b["self_digest"] = artifact_self_digest(b)
    rb = _w0.derive_source_admission_status(b)
    assert rb["status"] == "NOT_ADMITTED"
    assert any("wp3_system_unit_alignment_proof.role" in r for r in rb["reasons"])
    # (c) tamper the wave-exit owned-path manifest → NOT_PASS.
    wave_exit = _w0_wave_exit_receipt(base)
    wave_exit["owned_path_manifest_digest"] = "sha256:" + "0" * 64
    wave_exit["self_digest"] = artifact_self_digest(wave_exit)
    rc = _w0.derive_wave_exit_status(wave_exit, source_admission_receipt=base)
    assert rc["status"] == "NOT_PASS"
    assert any("owned_path_manifest_digest" in r for r in rc["reasons"])

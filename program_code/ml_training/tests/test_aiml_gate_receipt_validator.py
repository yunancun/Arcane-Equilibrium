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
    artifact_self_digest,
    canonical_digest,
    classify_required_effects,
    evidence_environment_identity_digest,
    github_policy_attestation_identity_digest,
    landing_scope_identity_digest,
    PROGRAM_GOVERNANCE_PATHS,
    program_adoption_identity_digest,
    S0_3_EXACT_OWNED_PATHS,
    S0_DEPENDENCY_DIGESTS,
    session_attempt_identity_digest,
    terminal_receipt_sink_contract,
    validate_aiml_artifact,
    validate_program_adoption_receipt,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64
HEAD_A = "a" * 40
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


def _session_attempt() -> dict:
    attempt = {
        "schema_version": "session_attempt_v1",
        "attempt_id": DIGEST_A,
        "session_id": "S0.3",
        "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
        "cohort_epoch": "PROGRAM",
        "attempt": 1,
        "attempt_key": {
            "session_id": "S0.3",
            "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
            "cohort_epoch": "PROGRAM",
            "attempt": 1,
        },
        "attempt_phase": "SOURCE_BUILD",
        "status": "IN_PROGRESS",
        "owner": "PM",
        "lease": {
            "lease_id": "lease-s0-3-attempt-1",
            "epoch": 1,
            "acquired_at": "2026-07-21T08:38:09Z",
            "expires_at": "2026-07-21T12:38:09Z",
            "heartbeat_at": "2026-07-21T08:38:09Z",
        },
        "source": {
            "branch": "agent/aiml-s0-3-adoption-v1",
            "worktree": "/tmp/aiml-s0-3-adoption-v1",
            "baseline_head": HEAD_A,
            "checkpoint_head": HEAD_A,
        },
        "path_manifest": ["program_code/ml_training/aiml_gate_receipt_validator.py"],
        "work_package": {
            "work_package_id": "AIML-S0.3-GOVERNANCE-ADOPTION",
            "phase": "SOURCE_BUILD",
            "side_effect_class": "repo_write",
            "runtime_claim": False,
            "owned_path_manifest": [
                "program_code/ml_training/aiml_gate_receipt_validator.py"
            ],
            "direct_interfaces": [
                "agent_governance_registry_v1",
                "agent_governance_route_task",
                "agent_governance_validate_closure",
                "aiml_receipt_dependency_graph_v1",
                "aiml_required_effect_classification_v1",
                "github_repository_policy_attestation_v1",
                "landing_scope_v1",
                "program_adoption_receipt_v1",
                "session_attempt_v1",
                "terminal_receipt_sink_v1",
            ],
        },
        "dependency_generations": [
            {
                "session_id": "S0.2",
                "schema_version": "serving_authority_receipt_v1",
                "receipt_digest": DIGEST_B,
            }
        ],
        "bootstrap_admission": {
            "task_id": "AIML-S0-3-GOVERNANCE-V1",
            "task_contract_digest": DIGEST_A,
            "dag_digest": DIGEST_B,
            "context_artifact_digest": "sha256:" + "c" * 64,
            "baseline_head": HEAD_A,
            "writer_lease_id": "lease-s0-3-attempt-1",
        },
        "native_admission": {
            "node_id": "implementation",
            "role": "E1",
            "native_agent": "E1-writer",
            "node_class": "work",
            "permission": "source_writer",
        },
        "dag_nodes": [
            {
                "node_id": "implementation",
                "node_class": "work",
                "permission": "source_writer",
                "requires": ["pa_design"],
                "writer_paths": [
                    "program_code/ml_training/aiml_gate_receipt_validator.py"
                ],
            }
        ],
        "semantic_rechecks": ["focused AIML governance tests"],
        "ci_classifier": {
            "classifier_digest": DIGEST_A,
            "selected_workflows": [],
            "invocation_history": [],
            "failure_fingerprints": [],
        },
        "effect_classification_digest": DIGEST_B,
        "created_at": "2026-07-21T08:40:00Z",
        "self_digest": DIGEST_A,
    }
    attempt["attempt_id"] = session_attempt_identity_digest(attempt)
    attempt["self_digest"] = artifact_self_digest(attempt)
    return attempt


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


def _dependency_graph() -> dict:
    graph = {
        "schema_version": "aiml_receipt_dependency_graph_v1",
        "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
        "root_receipt_id": "S0.3",
        "generated_at": "2026-07-21T09:00:00Z",
        "receipts": [
            {
                "receipt_id": "S0.1",
                "receipt_schema_version": "planning_documents_published_v1",
                "receipt_digest": DIGEST_A,
                "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
                "validity_class": "IMMUTABLE_LINEAGE",
                "state": "ACTIVE",
                "observed_at": "2026-07-21T07:00:00Z",
                "valid_from": None,
                "expires_at": None,
                "effect_at": None,
                "consumed_at": None,
                "authority_receipt_digest": None,
            },
            {
                "receipt_id": "S0.2",
                "receipt_schema_version": "serving_authority_receipt_v1",
                "receipt_digest": DIGEST_B,
                "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
                "validity_class": "IMMUTABLE_LINEAGE",
                "state": "ACTIVE",
                "observed_at": "2026-07-21T08:00:00Z",
                "valid_from": None,
                "expires_at": None,
                "effect_at": None,
                "consumed_at": None,
                "authority_receipt_digest": None,
            },
            {
                "receipt_id": "github-repository-state",
                "receipt_schema_version": "github_repository_state_v1",
                "receipt_digest": DIGEST_C,
                "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
                "validity_class": "CURRENT_STATE_TTL",
                "state": "ACTIVE",
                "observed_at": "2026-07-21T09:00:00Z",
                "valid_from": "2026-07-21T09:00:00Z",
                "expires_at": "2026-07-21T10:00:00Z",
                "effect_at": None,
                "consumed_at": None,
                "authority_receipt_digest": None,
            },
            {
                "receipt_id": "github-policy",
                "receipt_schema_version": "github_repository_policy_attestation_v1",
                "receipt_digest": DIGEST_D,
                "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
                "validity_class": "EFFECT_TIME_AUTHORITY",
                "state": "ACTIVE",
                "observed_at": "2026-07-21T09:00:00Z",
                "valid_from": "2026-07-21T09:00:00Z",
                "expires_at": "2026-07-21T10:00:00Z",
                "effect_at": "2026-07-21T09:30:00Z",
                "consumed_at": None,
                "authority_receipt_digest": None,
            },
            {
                "receipt_id": "S0.3",
                "receipt_schema_version": "program_adoption_receipt_v1",
                "receipt_digest": DIGEST_E,
                "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
                "validity_class": "IMMUTABLE_CONSUMED_EFFECT",
                "state": "ACTIVE",
                "observed_at": "2026-07-21T09:00:00Z",
                "valid_from": None,
                "expires_at": None,
                "effect_at": "2026-07-21T09:30:00Z",
                "consumed_at": "2026-07-21T09:30:00Z",
                "authority_receipt_digest": DIGEST_D,
            },
        ],
        "edges": [
            {
                "consumer_receipt_id": "S0.3",
                "dependency_receipt_id": "S0.1",
                "consumed_at": "2026-07-21T09:00:00Z",
            },
            {
                "consumer_receipt_id": "S0.3",
                "dependency_receipt_id": "S0.2",
                "consumed_at": "2026-07-21T09:00:00Z",
            },
            {
                "consumer_receipt_id": "S0.3",
                "dependency_receipt_id": "github-repository-state",
                "consumed_at": "2026-07-21T09:30:00Z",
            },
            {
                "consumer_receipt_id": "S0.3",
                "dependency_receipt_id": "github-policy",
                "consumed_at": "2026-07-21T09:30:00Z",
            },
        ],
        "self_digest": DIGEST_A,
    }
    graph["self_digest"] = artifact_self_digest(graph)
    return graph


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


def _post_merge_attempt() -> dict:
    attempt = deepcopy(_session_attempt())
    attempt["attempt"] = 2
    attempt["attempt_key"]["attempt"] = 2
    attempt["attempt_phase"] = "POST_MERGE_FINALIZATION"
    attempt["status"] = "IN_PROGRESS"
    attempt["lease"] = {
        "lease_id": "lease-s0-3-attempt-2",
        "epoch": 2,
        "acquired_at": "2026-07-21T09:00:00Z",
        "heartbeat_at": "2026-07-21T09:15:00Z",
        "expires_at": "2026-07-21T10:00:00Z",
    }
    attempt["source"]["baseline_head"] = "b" * 40
    attempt["source"]["checkpoint_head"] = "b" * 40
    attempt["path_manifest"] = []
    attempt["work_package"] = {
        "work_package_id": "AIML-S0.3-GOVERNANCE-ADOPTION",
        "phase": "POST_MERGE_FINALIZATION",
        "side_effect_class": "none",
        "runtime_claim": False,
        "owned_path_manifest": [],
        "direct_interfaces": [
            "aiml_program_adoption_validator",
            "github_repository_policy_attestation_v1",
            "program_adoption_receipt_v1",
        ],
    }
    attempt["bootstrap_admission"]["baseline_head"] = "b" * 40
    attempt["bootstrap_admission"]["writer_lease_id"] = (
        "lease-s0-3-attempt-2"
    )
    attempt["native_admission"] = {
        "node_id": "pm_finalization",
        "role": "PM",
        "native_agent": "PM",
        "node_class": "controller",
        "permission": "orchestrator",
    }
    attempt["dag_nodes"] = [{
        "node_id": "pm_finalization",
        "node_class": "controller",
        "permission": "orchestrator",
        "requires": ["business_acceptance"],
        "writer_paths": [],
    }]
    attempt["created_at"] = "2026-07-21T09:00:00Z"
    attempt["attempt_id"] = session_attempt_identity_digest(attempt)
    attempt["self_digest"] = artifact_self_digest(attempt)
    return attempt


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


def _github_policy_attestation() -> dict:
    attestation = {
        "schema_version": "github_repository_policy_attestation_v1",
        "attestation_id": DIGEST_A,
        "repository": {
            "repository_id": 123456,
            "full_name": "example/tradebot",
            "default_branch": "main",
        },
        "reviewed_head": HEAD_A,
        "merge_head": "b" * 40,
        "ruleset": {
            "ruleset_id": 9876,
            "name": "main-protection",
            "target": "branch",
            "enforcement": "active",
            "ref_includes": ["~DEFAULT_BRANCH"],
            "ref_excludes": [],
            "pull_request_required": True,
            "required_approving_review_count": 0,
            "required_checks": [
                {"context": "governance", "integration_id": None}
            ],
            "strict_required_status_checks_policy": True,
            "bypass_actors": [],
            "current_user_can_bypass": "never",
            "deletion_allowed": False,
            "non_fast_forward_allowed": False,
        },
        "observer_node_id": "github_policy_observer",
        "validator_node_id": "aiml_program_adoption_validator",
        "observation_method": "GITHUB_API_READONLY",
        "evidence_captures": [
            {
                "url": "https://api.github.com/repos/example/tradebot/branches/main/protection",
                "response_digest": DIGEST_B,
                "captured_at": "2026-07-21T09:05:00Z",
            }
        ],
        "validity_class": "EFFECT_TIME_AUTHORITY",
        "observed_at": "2026-07-21T09:05:00Z",
        "valid_from": "2026-07-21T09:05:00Z",
        "effect_at": "2026-07-21T09:30:00Z",
        "expires_at": "2026-07-21T10:05:00Z",
        "self_digest": DIGEST_A,
    }
    attestation["attestation_id"] = github_policy_attestation_identity_digest(
        attestation
    )
    attestation["self_digest"] = artifact_self_digest(attestation)
    return attestation


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


def _program_adoption_bundle() -> tuple[dict, dict]:
    source_attempt = _session_attempt()
    source_attempt["status"] = "MERGED"
    source_attempt["self_digest"] = artifact_self_digest(source_attempt)

    final_attempt = _post_merge_attempt()
    final_attempt["status"] = "FINALIZED"
    classification = classify_required_effects(
        final_attempt,
        classified_at="2026-07-21T09:00:00Z",
    )
    final_attempt["effect_classification_digest"] = classification["self_digest"]
    final_attempt["self_digest"] = artifact_self_digest(final_attempt)

    github_attestation = _github_policy_attestation()
    github_attestation["reviewed_head"] = source_attempt["source"]["checkpoint_head"]
    github_attestation["merge_head"] = final_attempt["source"]["baseline_head"]
    github_attestation["attestation_id"] = github_policy_attestation_identity_digest(
        github_attestation
    )
    github_attestation["self_digest"] = artifact_self_digest(github_attestation)

    document_paths = (
        "TODO.md",
        "docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-19--ai_ml_true_state_and_engineering_plan.md",
        "docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-20--ai_ml_completion_coverage_and_delivery_audit.md",
        "docs/CLAUDE_CHANGELOG.md",
        "docs/_indexes/document_index.md",
        "docs/_indexes/initiative_index.md",
        "docs/adr/0049-scanner-driven-alr-operational-shadow.md",
        "docs/adr/0050-development-agent-governance.md",
        "docs/adr/0051-registry-authorized-advisory-model-serving.md",
        "docs/agents/ai-ml-landing-delivery-protocol.md",
        "docs/agents/development-agent-governance.md",
        "docs/execution_plan/2026-07-19--ai_ml_long_lived_repair_and_landing_plan.md",
        "docs/execution_plan/ai_ml_landing/PROGRESS.md",
        "docs/governance_dev/SPECIFICATION_REGISTER.md",
        "docs/governance_dev/amendments/2026-07-21--AMD-2026-07-21-01-aiml-advisory-serving-authority.md",
    )
    schema_paths = tuple(
        f"program_code/ml_training/schemas/aiml_gate_receipts/{name}.schema.json"
        for name in (
            "aiml_receipt_dependency_graph_v1",
            "aiml_required_effect_classification_v1",
            "github_repository_policy_attestation_v1",
            "landing_scope_v1",
            "program_adoption_receipt_v1",
            "session_attempt_v1",
            "terminal_receipt_sink_v1",
        )
    )
    governance_paths = (
        ".codex/agent_registry_v1.json",
        "helper_scripts/maintenance_scripts/agent_governance.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_adoption.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure_inputs.py",
        "helper_scripts/maintenance_scripts/agent_governance_evidence.py",
        "helper_scripts/maintenance_scripts/agent_governance_execution.py",
        "helper_scripts/maintenance_scripts/agent_governance_registry.py",
        "helper_scripts/maintenance_scripts/agent_governance_routing.py",
        "helper_scripts/maintenance_scripts/agent_governance_vocabulary.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
        "tests/structure/test_agent_governance_aiml_adoption.py",
    )
    review_nodes = {
        "CC": "constitutional_gate",
        "E2": "independent_review",
        "E3": "security_gate",
        "E4": "regression",
        "MIT": "data_ml_review",
        "QA": "business_acceptance",
        "R4": "docs_integrity_review",
    }

    receipt = {
        "schema_version": "program_adoption_receipt_v1",
        "adoption_id": DIGEST_A,
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "terminal_state": "PROGRAM_ADOPTED",
        "session_id": "S0.3",
        "scope_ref": {"kind": "PROGRAM", "landing_scope_id": None},
        "cohort_epoch": "PROGRAM",
        "attempt": 2,
        "attempt_phase": "POST_MERGE_FINALIZATION",
        "source_build_attempt_id": source_attempt["attempt_id"],
        "finalization_attempt_id": final_attempt["attempt_id"],
        "dependency_receipts": [
            {
                "session_id": session_id,
                "receipt_digest": receipt_digest,
            }
            for session_id, receipt_digest in sorted(S0_DEPENDENCY_DIGESTS.items())
        ],
        "document_manifest": [
            {"path": path, "digest": canonical_digest(path)}
            for path in document_paths
        ],
        "schema_manifest": [
            {"path": path, "digest": canonical_digest(path)}
            for path in schema_paths
        ],
        "governance_manifest": [
            {"path": path, "digest": canonical_digest(path)}
            for path in governance_paths
        ],
        "reviewed_head": source_attempt["source"]["checkpoint_head"],
        "merge_head": final_attempt["source"]["baseline_head"],
        "github_policy_attestation_digest": github_attestation["self_digest"],
        "required_effect_classification_digest": classification["self_digest"],
        "receipt_dependency_graph_digest": DIGEST_A,
        "terminal_sink_contract_digest": terminal_receipt_sink_contract()[
            "self_digest"
        ],
        "review_bindings": [
            {
                "role": role,
                "node_id": node_id,
                "verdict": "PASS",
                "generation_digest": canonical_digest(f"{role}:{node_id}"),
            }
            for role, node_id in review_nodes.items()
        ],
        "validator_binding": {
            "node_id": "aiml_program_adoption_validator",
            "kind": "NON_CALL_VALIDATOR",
            "implementation_digest": canonical_digest(
                "program_code/ml_training/aiml_gate_receipt_validator.py"
            ),
        },
        "authority_limits": {
            "source_adoption_only": True,
            "runtime_authority_granted": False,
            "postgres_authority_granted": False,
            "deploy_authority_granted": False,
            "migration_authority_granted": False,
            "broker_authority_granted": False,
            "order_authority_granted": False,
            "ml5_implementation_authority_granted": False,
            "ml6_implementation_authority_granted": False,
            "direct_model_authority_granted": False,
        },
        "validity_class": "IMMUTABLE_CONSUMED_EFFECT",
        "issued_at": "2026-07-21T09:30:00Z",
        "self_digest": DIGEST_A,
    }
    receipt["adoption_id"] = program_adoption_identity_digest(receipt)

    graph = _dependency_graph()
    for node in graph["receipts"]:
        if node["receipt_id"] in S0_DEPENDENCY_DIGESTS:
            node["receipt_digest"] = S0_DEPENDENCY_DIGESTS[node["receipt_id"]]
            node["validity_class"] = "IMMUTABLE_LINEAGE"
            node["valid_from"] = None
            node["expires_at"] = None
            node["effect_at"] = None
            node["consumed_at"] = None
            node["authority_receipt_digest"] = None
        elif node["receipt_id"] == "github-policy":
            node["receipt_digest"] = github_attestation["self_digest"]
            node["observed_at"] = github_attestation["observed_at"]
            node["valid_from"] = github_attestation["valid_from"]
            node["effect_at"] = github_attestation["effect_at"]
            node["expires_at"] = github_attestation["expires_at"]
        elif node["receipt_id"] == "S0.3":
            node["receipt_digest"] = receipt["adoption_id"]
            node["authority_receipt_digest"] = github_attestation["self_digest"]
            node["effect_at"] = receipt["issued_at"]
            node["consumed_at"] = receipt["issued_at"]
    graph["generated_at"] = receipt["issued_at"]
    graph["self_digest"] = artifact_self_digest(graph)
    receipt["receipt_dependency_graph_digest"] = graph["self_digest"]
    receipt["self_digest"] = artifact_self_digest(receipt)

    artifacts = {
        "s0_1_receipt": json.loads((
            REPO_ROOT
            / "docs/execution_plan/ai_ml_landing/receipts/"
            "S0.1-planning-documents-published-v1.json"
        ).read_text(encoding="utf-8")),
        "s0_2_receipt": json.loads((
            REPO_ROOT
            / "docs/execution_plan/ai_ml_landing/receipts/"
            "S0.2-serving-authority-receipt-v1.json"
        ).read_text(encoding="utf-8")),
        "source_attempt": source_attempt,
        "finalization_attempt": final_attempt,
        "effect_classification": classification,
        "dependency_graph": graph,
        "github_attestation": github_attestation,
        "terminal_sink_contract": terminal_receipt_sink_contract(),
    }
    return receipt, artifacts


def _resign_program_bundle(receipt: dict, artifacts: dict) -> None:
    receipt["adoption_id"] = program_adoption_identity_digest(receipt)
    graph = artifacts["dependency_graph"]
    next(
        node for node in graph["receipts"] if node["receipt_id"] == "S0.3"
    )["receipt_digest"] = receipt["adoption_id"]
    graph["self_digest"] = artifact_self_digest(graph)
    receipt["receipt_dependency_graph_digest"] = graph["self_digest"]
    receipt["self_digest"] = artifact_self_digest(receipt)


def _accept_source_manifest(
    _reviewed_head: str,
    _merge_head: str,
    _path_to_digest: dict[str, str],
) -> bool:
    return True


def test_program_adoption_rejects_unknown_schema_or_extra_field() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["schema_version"] = "program_adoption_receipt_v2"

    unknown_errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )
    assert any("unsupported AIML artifact schema_version" in error for error in unknown_errors)

    receipt, artifacts = _program_adoption_bundle()
    receipt["unexpected_authority"] = True
    extra_errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )
    assert any("unexpected property unexpected_authority" in error for error in extra_errors)


def test_program_adoption_rejects_signed_payload_tamper() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["document_manifest"][0]["digest"] = canonical_digest("tampered")

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any("program adoption_id is invalid" in error for error in errors)
    assert any("program adoption receipt self_digest is invalid" in error for error in errors)


def test_program_adoption_rejects_resigned_s0_dependency_substitution() -> None:
    receipt, artifacts = _program_adoption_bundle()
    substitute_digest = canonical_digest("substituted-S0.1-receipt")
    receipt["dependency_receipts"][0]["receipt_digest"] = substitute_digest
    next(
        node
        for node in artifacts["dependency_graph"]["receipts"]
        if node["receipt_id"] == "S0.1"
    )["receipt_digest"] = substitute_digest
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any("not the exact S0.1/S0.2 lineage" in error for error in errors)


def test_program_adoption_rejects_tampered_checked_in_s0_1_receipt() -> None:
    receipt, artifacts = _program_adoption_bundle()
    artifacts["s0_1_receipt"]["status"] = "TAMPERED"

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "s0_1_receipt self_digest does not bind the complete canonical receipt"
        in error
        for error in errors
    )


def test_program_adoption_rejects_resigned_s0_2_predecessor_substitution() -> None:
    receipt, artifacts = _program_adoption_bundle()
    predecessor = artifacts["s0_2_receipt"]
    predecessor["receipt_type"] = "substituted_serving_authority_receipt_v1"
    predecessor["self_digest"] = artifact_self_digest(predecessor)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "s0_2_receipt receipt_type differs from exact S0 lineage" in error
        for error in errors
    )
    assert any(
        "s0_2_receipt digest differs from hardcoded S0 lineage" in error
        for error in errors
    )
    assert not any(
        "s0_2_receipt self_digest does not bind" in error for error in errors
    )


def test_program_adoption_rejects_non_s0_3_receipt() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["session_id"] = "S0.4"
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any("session_id" in error and "S0.3" in error for error in errors)


def test_program_adoption_rejects_resigned_final_attempt_number_substitution() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["attempt"] = 3
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert "program adoption finalization attempt number binding is invalid" in errors


def test_program_adoption_rejects_premerge_source_attempt() -> None:
    receipt, artifacts = _program_adoption_bundle()
    source_attempt = artifacts["source_attempt"]
    source_attempt["status"] = "IN_PROGRESS"
    source_attempt["self_digest"] = artifact_self_digest(source_attempt)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert "program adoption requires merged S0.3 source-build attempt 1" in errors


@pytest.mark.parametrize(
    ("head_field", "expected_error"),
    [
        (
            "reviewed_head",
            "program adoption reviewed_head differs from source-build checkpoint",
        ),
        (
            "merge_head",
            "program adoption merge_head differs from finalization baseline",
        ),
    ],
)
def test_program_adoption_rejects_resigned_head_drift(
    head_field: str,
    expected_error: str,
) -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt[head_field] = "c" * 40
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert expected_error in errors


@pytest.mark.parametrize(
    ("digest_field", "expected_fragment"),
    [
        ("github_policy_attestation_digest", "GitHub policy attestation binding"),
        (
            "required_effect_classification_digest",
            "required-effect classification binding",
        ),
        ("terminal_sink_contract_digest", "terminal sink contract binding"),
    ],
)
def test_program_adoption_rejects_resigned_artifact_digest_drift(
    digest_field: str,
    expected_fragment: str,
) -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt[digest_field] = canonical_digest(f"drift:{digest_field}")
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(expected_fragment in error for error in errors)


def test_program_adoption_rejects_dependency_graph_digest_drift() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["receipt_dependency_graph_digest"] = canonical_digest("graph-drift")
    receipt["self_digest"] = artifact_self_digest(receipt)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert "program adoption dependency-graph binding is invalid" in errors


@pytest.mark.parametrize(
    "manifest_field",
    ["document_manifest", "schema_manifest", "governance_manifest"],
)
def test_program_adoption_rejects_resigned_manifest_path_drift(
    manifest_field: str,
) -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt[manifest_field][0]["path"] = "substituted/path"
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        f"{manifest_field} paths differ from exact contract" in error
        for error in errors
    )


def test_program_adoption_requires_post_merge_attempt_and_exact_s0_lineage() -> None:
    receipt, artifacts = _program_adoption_bundle()

    assert receipt["program_id"] == "AIML-LONG-LIVED-LANDING-V2"
    assert validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda artifact: artifact is artifacts[
            "github_attestation"
        ],
        source_manifest_verifier=_accept_source_manifest,
    ) == []


def test_program_adoption_source_verifier_receives_heads_and_complete_manifest() -> None:
    receipt, artifacts = _program_adoption_bundle()
    calls: list[tuple[str, str, dict[str, str]]] = []

    def capture_source_manifest(
        reviewed_head: str,
        merge_head: str,
        path_to_digest: dict[str, str],
    ) -> bool:
        calls.append((reviewed_head, merge_head, path_to_digest))
        return True

    assert validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=capture_source_manifest,
    ) == []
    expected_manifest = {
        item["path"]: item["digest"]
        for field in (
            "document_manifest",
            "schema_manifest",
            "governance_manifest",
        )
        for item in receipt[field]
    }
    assert calls == [
        (receipt["reviewed_head"], receipt["merge_head"], expected_manifest)
    ]


def test_program_adoption_rejects_absent_false_or_failing_source_verifier() -> None:
    receipt, artifacts = _program_adoption_bundle()

    def failing_source_verifier(
        _reviewed_head: str,
        _merge_head: str,
        _path_to_digest: dict[str, str],
    ) -> bool:
        raise RuntimeError("source verification transport failed")

    missing_errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
    )
    assert (
        "program adoption requires caller-supplied source manifest verification"
        in missing_errors
    )
    for verifier in (
        lambda _reviewed, _merge, _manifest: False,
        failing_source_verifier,
    ):
        errors = validate_program_adoption_receipt(
            receipt,
            artifacts=artifacts,
            now="2026-07-21T09:30:00Z",
            external_verifier=lambda _artifact: True,
            source_manifest_verifier=verifier,
        )
        assert "program adoption source manifest verification failed" in errors


def test_program_adoption_rejects_resigned_correct_path_blob_digest_drift() -> None:
    receipt, artifacts = _program_adoption_bundle()
    expected_manifest = {
        item["path"]: item["digest"]
        for field in (
            "document_manifest",
            "schema_manifest",
            "governance_manifest",
        )
        for item in receipt[field]
    }
    receipt["document_manifest"][0]["digest"] = canonical_digest(
        "substituted-blob-at-correct-path"
    )
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=(
            lambda _reviewed, _merge, manifest: manifest == expected_manifest
        ),
    )

    assert "program adoption source manifest verification failed" in errors
    assert not any("adoption_id is invalid" in error for error in errors)
    assert not any("self_digest is invalid" in error for error in errors)


def test_program_adoption_rejects_absent_or_false_external_github_verifier() -> None:
    receipt, artifacts = _program_adoption_bundle()

    def failing_verifier(_artifact: dict) -> bool:
        raise RuntimeError("verification transport failed")

    assert "program adoption requires caller-supplied external GitHub verification" in (
        validate_program_adoption_receipt(
            receipt,
            artifacts=artifacts,
            now="2026-07-21T09:30:00Z",
            source_manifest_verifier=_accept_source_manifest,
        )
    )
    assert "program adoption external GitHub verification failed" in (
        validate_program_adoption_receipt(
            receipt,
            artifacts=artifacts,
            now="2026-07-21T09:30:00Z",
            external_verifier=lambda _artifact: False,
            source_manifest_verifier=_accept_source_manifest,
        )
    )
    assert "program adoption external GitHub verification failed" in (
        validate_program_adoption_receipt(
            receipt,
            artifacts=artifacts,
            now="2026-07-21T09:30:00Z",
            external_verifier=failing_verifier,
            source_manifest_verifier=_accept_source_manifest,
        )
    )


def test_program_adoption_external_verifier_receives_complete_attestation() -> None:
    receipt, artifacts = _program_adoption_bundle()

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda artifact: artifact is artifacts["github_attestation"],
        source_manifest_verifier=_accept_source_manifest,
    )

    assert "program adoption external GitHub verification failed" not in errors

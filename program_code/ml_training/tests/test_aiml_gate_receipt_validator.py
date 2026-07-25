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
    canonical_digest,
    classify_required_effects,
    evidence_environment_identity_digest,
    github_policy_attestation_identity_digest,
    landing_scope_identity_digest,
    PROGRAM_GOVERNANCE_PATHS,
    program_adoption_identity_digest,
    S0_3_EXACT_OWNED_PATHS,
    S0_DEPENDENCY_DIGESTS,
    SCHEMA_DIR,
    SCHEMA_FILES,
    session_attempt_identity_digest,
    terminal_receipt_sink_contract,
    validate_aiml_artifact,
    validate_program_adoption_receipt,
)

import agent_governance_sealed_build as _sb  # noqa: E402 (HELPER_DIR 由 validator import 時已入 path)


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
    # POST_MERGE 收尾不再持有 writer lease,改以唯讀 admission 記錄存活心跳。
    del attempt["lease"]
    attempt["read_only_admission"] = {
        "epoch": 2,
        "admitted_at": "2026-07-21T09:00:00Z",
        "heartbeat_at": "2026-07-21T09:15:00Z",
        "read_only": True,
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
            "aiml_trusted_host_finalizer_v1",
            "github_repository_policy_attestation_v1",
            "program_adoption_receipt_v1",
        ],
    }
    attempt["bootstrap_admission"]["baseline_head"] = "b" * 40
    del attempt["bootstrap_admission"]["writer_lease_id"]
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
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_common.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_git.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_github.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_github_pr.py",
        "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure_time.py",
        "helper_scripts/maintenance_scripts/agent_governance_closure_inputs.py",
        "helper_scripts/maintenance_scripts/agent_governance_evidence.py",
        "helper_scripts/maintenance_scripts/agent_governance_execution.py",
        "helper_scripts/maintenance_scripts/agent_governance_registry.py",
        "helper_scripts/maintenance_scripts/agent_governance_routing.py",
        "helper_scripts/maintenance_scripts/agent_governance_vocabulary.py",
        "program_code/ml_training/aiml_gate_receipt_validator.py",
        "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
        "tests/structure/test_agent_governance_aiml_adoption.py",
        "tests/structure/test_agent_governance_aiml_trusted_host.py",
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
    # review_generation 綁定 merge_head 的完整 repo 位元代;採納 fragment 的
    # final_generation 必須逐一等於它。
    review_generation = {
        "source_head": final_attempt["source"]["baseline_head"],
        "dirty_diff_hash": canonical_digest("adoption-review-dirty"),
        "untracked_relevant_hash": canonical_digest("adoption-review-untracked"),
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
                "fragment_id": f"frag-{node_id}",
            }
            for role, node_id in review_nodes.items()
        ],
        "review_generation": review_generation,
        "review_generation_digest": canonical_digest(review_generation),
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


def _fast_forward_program_adoption_bundle() -> tuple[dict, dict]:
    """令 finalization baseline == source checkpoint,形成 reviewed==merge 的 fast-forward。"""

    receipt, artifacts = _program_adoption_bundle()
    reviewed_head = receipt["reviewed_head"]

    final_attempt = artifacts["finalization_attempt"]
    final_attempt["source"]["baseline_head"] = reviewed_head
    final_attempt["source"]["checkpoint_head"] = reviewed_head
    final_attempt["bootstrap_admission"]["baseline_head"] = reviewed_head
    final_attempt["self_digest"] = artifact_self_digest(final_attempt)

    github = artifacts["github_attestation"]
    github["merge_head"] = reviewed_head
    github["attestation_id"] = github_policy_attestation_identity_digest(github)
    github["self_digest"] = artifact_self_digest(github)

    graph = artifacts["dependency_graph"]
    next(
        node for node in graph["receipts"] if node["receipt_id"] == "github-policy"
    )["receipt_digest"] = github["self_digest"]
    next(
        node for node in graph["receipts"] if node["receipt_id"] == "S0.3"
    )["authority_receipt_digest"] = github["self_digest"]

    receipt["merge_head"] = reviewed_head
    receipt["github_policy_attestation_digest"] = github["self_digest"]
    # review_generation 綁定 merge_head,fast-forward 後同步為 reviewed_head。
    receipt["review_generation"]["source_head"] = reviewed_head
    receipt["review_generation_digest"] = canonical_digest(
        receipt["review_generation"]
    )
    _resign_program_bundle(receipt, artifacts)
    return receipt, artifacts


# _accept_source_manifest 模擬 host 對 SourceManifestVerifier 的強契約:回傳 True
# 代表 merge_head 為 reviewed_head 的後代(自反:兩者相等亦通過)且各 path 的 blob
# 相符。_SOURCE_ANCESTRY 依 _program_adoption_bundle 的 fixture 建模——reviewed=a*40
# 被合入 merge=b*40。
_SOURCE_ANCESTRY = {HEAD_A: {HEAD_A, "b" * 40}}


def _merge_head_descends_from_reviewed(reviewed_head: str, merge_head: str) -> bool:
    if reviewed_head == merge_head:
        return True
    return merge_head in _SOURCE_ANCESTRY.get(reviewed_head, set())


def _accept_source_manifest(
    reviewed_head: str,
    merge_head: str,
    _path_to_digest: dict[str, str],
) -> bool:
    return _merge_head_descends_from_reviewed(reviewed_head, merge_head)


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
    if head_field == "merge_head":
        # 讓 review_generation 隨 merge_head 一致,隔離 reviewed/merge 交叉綁定檢查,
        # 避免 review_generation 綁定 merge_head 的檢查提前失敗而遮蔽交叉綁定訊息。
        receipt["review_generation"]["source_head"] = "c" * 40
        receipt["review_generation_digest"] = canonical_digest(
            receipt["review_generation"]
        )
    _resign_program_bundle(receipt, artifacts)

    # 本例隔離 reviewed/merge 交叉綁定檢查,故用寬鬆(永真)source verifier,避免
    # 祖裔感知的 _accept_source_manifest 因 head 漂移提前失敗而遮蔽交叉綁定訊息;
    # 祖裔義務由專屬的 non-descending / fast-forward 測試涵蓋。
    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=lambda _reviewed, _merge, _manifest: True,
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


# Finding 2:祖裔義務。host verifier 回傳 True 必須代表 merge_head 為 reviewed_head
# 的後代(審過的樹確實被合入採納樹);非後代則採納失敗,自反(fast-forward)通過。
def test_program_adoption_rejects_merge_head_not_descending_from_reviewed_head() -> None:
    receipt, artifacts = _program_adoption_bundle()

    def non_descending_ancestry_verifier(
        reviewed_head: str,
        merge_head: str,
        _path_to_digest: dict[str, str],
    ) -> bool:
        # 主機建模的祖裔關係中 merge_head 並非 reviewed_head 的後代,強契約不成立。
        descendants = {reviewed_head: {reviewed_head}}
        return merge_head in descendants.get(reviewed_head, set())

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=non_descending_ancestry_verifier,
    )

    assert "program adoption source manifest verification failed" in errors
    assert not any("adoption_id is invalid" in error for error in errors)
    assert not any("self_digest is invalid" in error for error in errors)


def test_program_adoption_accepts_fast_forward_reviewed_equals_merge_head() -> None:
    receipt, artifacts = _fast_forward_program_adoption_bundle()

    assert receipt["reviewed_head"] == receipt["merge_head"]
    assert validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    ) == []


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


# 以下為 S0.3 採納閘門 fail-closed 不變量的負向回歸鎖。行為已正確，這些測試
# 只斷言「弱化 schema/邏輯會被擋下」，每例僅變動單一欄位並在必要處重新簽章，
# 使失敗來自被鎖定的規則而非附帶的 digest 不一致。


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_adoption_only", False),
        ("runtime_authority_granted", True),
        ("postgres_authority_granted", True),
        ("deploy_authority_granted", True),
        ("migration_authority_granted", True),
        ("broker_authority_granted", True),
        ("order_authority_granted", True),
        ("ml5_implementation_authority_granted", True),
        ("ml6_implementation_authority_granted", True),
        ("direct_model_authority_granted", True),
    ],
)
def test_program_adoption_rejects_widened_authority_limits(
    field: str,
    value: bool,
) -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["authority_limits"][field] = value
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        f"authority_limits.{field}" in error and "expected const" in error
        for error in errors
    )


def test_program_adoption_rejects_short_review_bindings() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["review_bindings"] = receipt["review_bindings"][:6]
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "review_bindings" in error and "shorter than minItems" in error
        for error in errors
    )


def test_program_adoption_rejects_substituted_review_binding_node() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["review_bindings"][0]["node_id"] = "substituted_node"
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "review bindings are incomplete or substituted" in error
        for error in errors
    )


def test_program_adoption_rejects_review_binding_role_set_swap() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["review_bindings"] = [
        binding
        for binding in receipt["review_bindings"]
        if binding["role"] != "QA"
    ]
    receipt["review_bindings"].append({
        "role": "E2",
        "node_id": "independent_review_duplicate",
        "verdict": "PASS",
        "fragment_id": "frag-independent_review_duplicate",
    })
    _resign_program_bundle(receipt, artifacts)

    assert len(receipt["review_bindings"]) == 7
    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "review bindings are incomplete or substituted" in error
        for error in errors
    )


# Finding 1(受 receipt 保護):review_generation 綁定 merge_head 與唯一 fragment_id。
def test_program_adoption_rejects_review_generation_not_bound_to_merge_head() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["review_generation"]["source_head"] = "c" * 40
    receipt["review_generation_digest"] = canonical_digest(receipt["review_generation"])
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "review generation is not bound to merge_head" in error for error in errors
    )


def test_program_adoption_rejects_review_generation_digest_drift() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["review_generation_digest"] = canonical_digest("review-generation-drift")
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "review generation digest is invalid" in error for error in errors
    )


def test_program_adoption_rejects_duplicate_review_binding_fragment_ids() -> None:
    receipt, artifacts = _program_adoption_bundle()
    receipt["review_bindings"][1]["fragment_id"] = receipt["review_bindings"][0][
        "fragment_id"
    ]
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "review binding fragment ids are not unique" in error for error in errors
    )


@pytest.mark.parametrize(
    ("edge", "expected_fragment"),
    [
        (
            {
                "consumer_receipt_id": "S0.1",
                "dependency_receipt_id": "S0.3",
                "consumed_at": "2026-07-21T09:30:00Z",
            },
            "receipt dependency graph contains a cycle",
        ),
        (
            {
                "consumer_receipt_id": "S0.1",
                "dependency_receipt_id": "S0.1",
                "consumed_at": "2026-07-21T09:30:00Z",
            },
            "cannot depend on itself",
        ),
        (
            {
                "consumer_receipt_id": "S0.3",
                "dependency_receipt_id": "S9.9",
                "consumed_at": "2026-07-21T09:30:00Z",
            },
            "receipt dependency edge references an unknown receipt",
        ),
    ],
    ids=["cycle", "self_edge", "unknown_receipt"],
)
def test_program_adoption_rejects_dependency_graph_edge_integrity_violation(
    edge: dict,
    expected_fragment: str,
) -> None:
    receipt, artifacts = _program_adoption_bundle()
    artifacts["dependency_graph"]["edges"].append(deepcopy(edge))
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(expected_fragment in error for error in errors)


def test_program_adoption_rejects_dependency_graph_duplicate_receipt_id() -> None:
    receipt, artifacts = _program_adoption_bundle()
    graph = artifacts["dependency_graph"]
    duplicate = deepcopy(
        next(node for node in graph["receipts"] if node["receipt_id"] == "S0.1")
    )
    duplicate["receipt_digest"] = canonical_digest("duplicate-s0-1-node")
    graph["receipts"].append(duplicate)
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "receipt dependency graph ids are not unique" in error
        for error in errors
    )


def test_program_adoption_rejects_dependency_graph_duplicate_receipt_digest() -> None:
    receipt, artifacts = _program_adoption_bundle()
    graph = artifacts["dependency_graph"]
    s0_1_digest = next(
        node for node in graph["receipts"] if node["receipt_id"] == "S0.1"
    )["receipt_digest"]
    next(
        node
        for node in graph["receipts"]
        if node["receipt_id"] == "github-repository-state"
    )["receipt_digest"] = s0_1_digest
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "receipt dependency graph digests are not unique" in error
        for error in errors
    )


def test_program_adoption_rejects_dependency_graph_absent_root() -> None:
    receipt, artifacts = _program_adoption_bundle()
    artifacts["dependency_graph"]["root_receipt_id"] = "S9.9"
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "receipt dependency graph root is absent" in error for error in errors
    )


def test_program_adoption_rejects_dependency_graph_mixed_scopes() -> None:
    receipt, artifacts = _program_adoption_bundle()
    graph = artifacts["dependency_graph"]
    next(
        node for node in graph["receipts"] if node["receipt_id"] == "S0.1"
    )["scope_ref"] = {"kind": "LANDING_SCOPE", "landing_scope_id": DIGEST_A}
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "receipt dependency graph mixes landing scopes" in error
        for error in errors
    )


def test_program_adoption_rejects_dependency_graph_future_dated_receipt() -> None:
    receipt, artifacts = _program_adoption_bundle()
    graph = artifacts["dependency_graph"]
    next(
        node for node in graph["receipts"] if node["receipt_id"] == "S0.2"
    )["observed_at"] = "2026-07-21T09:45:00Z"
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any("receipt S0.2 is future-dated" in error for error in errors)


def test_program_adoption_rejects_dependency_graph_tampered_self_digest() -> None:
    receipt, artifacts = _program_adoption_bundle()
    # 故意不重新簽章:被鎖定的規則正是圖的 self_digest 必須綁定其正規內容。
    artifacts["dependency_graph"]["self_digest"] = canonical_digest(
        "dependency-graph-self-digest-tamper"
    )

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "receipt dependency graph self_digest is invalid" in error
        for error in errors
    )


def test_program_adoption_rejects_missing_required_receipt_field() -> None:
    receipt, artifacts = _program_adoption_bundle()
    # 缺漏必填欄位在 schema 層即短路,因此不需重新簽章。
    receipt.pop("issued_at")

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any(
        "missing required property issued_at" in error for error in errors
    )


def test_program_adoption_rejects_dependency_graph_validity_class_outside_enum() -> None:
    # program adoption receipt 的 validity_class 是 const,而依賴圖各 receipt 的
    # validity_class 才是 enum,故 enum 越界的 schema wiring 在此鎖定。
    receipt, artifacts = _program_adoption_bundle()
    graph = artifacts["dependency_graph"]
    next(
        node for node in graph["receipts"] if node["receipt_id"] == "S0.1"
    )["validity_class"] = "NOT_A_REAL_VALIDITY_CLASS"
    _resign_program_bundle(receipt, artifacts)

    errors = validate_program_adoption_receipt(
        receipt,
        artifacts=artifacts,
        now="2026-07-21T09:30:00Z",
        external_verifier=lambda _artifact: True,
        source_manifest_verifier=_accept_source_manifest,
    )

    assert any("value is outside enum" in error for error in errors)


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


# ── S2.4 · WP4 · W1 · CP2a(capability-probe + prepare 契約 schema)─────────────
# 這 14 份 closed schema 皆屬「契約」:round-trip 乾淨、additionalProperties 拒外鍵、
# unsigned core 排除 id/auth/self_digest、const-false 生產旗標與 allOf 有牙(不得斷言 runtime PASS)。
_CP2A_D = "sha256:" + "a" * 64
_CP2A_D2 = "sha256:" + "b" * 64
_CP2A_GIT = "0" * 40
_CP2A_TS = "2026-07-24T00:00:00+00:00"
_CP2A_PROBE_HEX = "c" * 64
_CP2A_PREP_HEX = "d" * 64
_CP2A_PROBE_ID = "s2-4-probe-" + _CP2A_PROBE_HEX
_CP2A_PREP_ID = "s2-4-prepare-" + _CP2A_PREP_HEX
_CP2A_UNIT = "arcane-aiml-s2-4-probe-" + _CP2A_PROBE_HEX + ".service"
_CP2A_STAGING = "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared/" + _CP2A_PREP_ID


def _cp2a_probe_core() -> dict:
    return {
        "schema_version": "s2_4_capability_probe_core_v1",
        "probe_scope": "PREPARE_SANDBOX",
        "transient_unit_property_digest": _CP2A_D,
        "host_cgroup_identity": {
            "host": "trade-core",
            "cgroup_manager_scope": "system_manager",
            "cgroup_root_pattern": "/sys/fs/cgroup/system.slice",
        },
        "cleanup_budget": {"max_cleanup_seconds": 30, "max_cgroup_drain_seconds": 10},
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "created_at": _CP2A_TS,
    }


def _cp2a_prepare_core() -> dict:
    return {
        "schema_version": "s2_4_prepare_core_v1",
        "staging_root_device_inode": {
            "staging_parent_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/prepared",
            "device": 66306,
            "inode": 12345,
        },
        "resource_budget": {"max_bytes": 1048576, "max_seconds": 600},
        "fetch_budget": {"max_fetch_bytes": 524288, "max_fetch_seconds": 300, "max_artifacts": 32},
        "build_budget": {"max_build_bytes": 524288, "max_build_seconds": 600},
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "created_at": _CP2A_TS,
    }


def _cp2a_fixtures() -> dict:
    probe_core = _cp2a_probe_core()
    probe_core_digest = canonical_digest(probe_core)
    prepare_core = _cp2a_prepare_core()
    prepare_core_digest = canonical_digest(prepare_core)
    staging_locator = {"staging_root": _CP2A_STAGING, "device": 66306, "inode": 22222}

    artifacts: dict[str, dict] = {}

    artifacts["s2_4_capability_probe_core_v1"] = probe_core

    artifacts["s2_4_capability_probe_intent_v1"] = {
        "schema_version": "s2_4_capability_probe_intent_v1",
        "route_class": "s2_4_capability_probe_intent",
        "core": probe_core,
        "core_digest": probe_core_digest,
        "probe_id": _CP2A_PROBE_ID,
        "route_surface": {
            "required_effect_class": "HOST_CAPABILITY_PROBE",
            "runtime_effect": True,
            "service": "transient_probe_only",
            "risk": "high",
            "runtime_claim": True,
            "probe_budget_bound": True,
            "cleanup_budget_bound": True,
        },
        "forbidden_surfaces": {
            "persistent_unit_write": False,
            "persistent_unit_enable": False,
            "persistent_unit_start": False,
            "daemon_reload": False,
            "pg": False,
            "migration": False,
            "secret": False,
            "credential_install": False,
            "host_identity": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "profile_identity": "aiml-s2-capability-probe-operator-v1",
            "signature_namespace": "arcane-equilibrium-aiml-s2-capability-probe",
            "max_ttl_seconds": 600,
        },
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["network_sandbox_capability_attestation_v1"] = {
        "schema_version": "network_sandbox_capability_attestation_v1",
        "scope": "PREPARE_SANDBOX",
        "probe_id": _CP2A_PROBE_ID,
        "probe_core_digest": probe_core_digest,
        "transient_unit_property_digest": _CP2A_D,
        "observed_sandbox_capability_digest": _CP2A_D2,
        "network_isolation_verified": True,
        "evidence_class": "PLATFORM_ATTESTED",
        "production_posture": {
            "is_runtime_production_pass": False,
            "production_apply_performed": False,
            "running_attested": False,
            "nine_authorities_false": True,
        },
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_capability_probe_effect_receipt_v1"] = {
        "schema_version": "s2_4_capability_probe_effect_receipt_v1",
        "probe_id": _CP2A_PROBE_ID,
        "probe_core_digest": probe_core_digest,
        "probe_scope": "PREPARE_SANDBOX",
        "authorization_id": _CP2A_D,
        "authorization_digest": _CP2A_D2,
        "derived_unit_name": _CP2A_UNIT,
        "transient_unit_lifecycle": {
            "invocation_id": "abc123",
            "unit_created": True,
            "unit_observed": True,
            "stopped_after_grace": True,
            "reset_failed": True,
            "removed": True,
            "zero_residue_verified": True,
        },
        "journal_digest": _CP2A_D,
        "consumed_replay_entry_digest": _CP2A_D2,
        "postcheck_digest": _CP2A_D,
        "rollback_digest": _CP2A_D2,
        "network_sandbox_capability_attestation_digest": _CP2A_D,
        "terminal_status": "TERMINAL_CLEAN",
        "evidence_class": "PLATFORM_ATTESTED",
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "trusted_host_time": _CP2A_TS,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_capability_probe_journal_v1"] = {
        "schema_version": "s2_4_capability_probe_journal_v1",
        "probe_id": _CP2A_PROBE_ID,
        "derived_unit_name": _CP2A_UNIT,
        "scope": "PREPARE_SANDBOX",
        "transient_unit_property_digest": _CP2A_D,
        "expected_invocation_id_pattern": "^[0-9a-f]{32}$",
        "cleanup_rollback_digest": _CP2A_D2,
        "entries": [
            {
                "seq": 0,
                "state": "APPLYING",
                "pre_state_digest": _CP2A_D,
                "post_state_digest": _CP2A_D2,
                "fsynced": True,
                "recorded_at": _CP2A_TS,
            }
        ],
        "terminal": True,
        "journal_integrity": {
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
        "outer_checksum": _CP2A_D,
        "self_digest": _CP2A_D2,
    }

    artifacts["s2_4_capability_probe_postcheck_v1"] = {
        "schema_version": "s2_4_capability_probe_postcheck_v1",
        "status": "PASS",
        "probe_id": _CP2A_PROBE_ID,
        "probe_core_digest": probe_core_digest,
        "derived_unit_name": _CP2A_UNIT,
        "verifier_node": "ops-verifier",
        "applier_node": "probe-applier",
        "stopped_confirmed": True,
        "reset_failed_confirmed": True,
        "removed_confirmed": True,
        "no_surviving_unit": True,
        "no_surviving_cgroup": True,
        "no_surviving_process": True,
        "verifier_capture_digest": _CP2A_D,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D2,
    }

    artifacts["s2_4_capability_probe_rollback_v1"] = {
        "schema_version": "s2_4_capability_probe_rollback_v1",
        "status": "CLEANED_EXACT",
        "probe_id": _CP2A_PROBE_ID,
        "derived_unit_name": _CP2A_UNIT,
        "pre_state_digest": _CP2A_D,
        "post_state_digest": _CP2A_D2,
        "stop_operation": "transient_unit_stop",
        "cgroup_drain_operation": "bounded_cgroup_drain",
        "reset_failed_operation": "reset_failed",
        "remove_operation": "transient_unit_remove",
        "cgroup_drain_bounded": True,
        "unit_absent": True,
        "cgroup_absent": True,
        "task_files_absent": True,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_prepare_core_v1"] = prepare_core

    artifacts["s2_4_prepare_intent_v1"] = {
        "schema_version": "s2_4_prepare_intent_v1",
        "route_class": "s2_4_prepare_intent",
        "core": prepare_core,
        "core_digest": prepare_core_digest,
        "prepare_id": _CP2A_PREP_ID,
        "route_surface": {
            "required_effect_class": "LEARNING_RUNTIME_PREPARE",
            "runtime_effect": True,
            "service": "transient_builder_only",
            "risk": "high",
            "runtime_claim": True,
            "staging_budget_bound": True,
            "fetch_budget_bound": True,
            "build_budget_bound": True,
            "cleanup_budget_bound": True,
        },
        "forbidden_surfaces": {
            "apply_publish": False,
            "persistent_unit_write": False,
            "persistent_unit_enable": False,
            "persistent_unit_start": False,
            "daemon_reload": False,
            "pg": False,
            "migration": False,
            "secret": False,
            "credential_install": False,
            "host_identity": False,
            "opt_publish": False,
            "etc_write": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "profile_identity": "aiml-s2-install-prepare-operator-v1",
            "signature_namespace": "arcane-equilibrium-aiml-s2-install-prepare",
            "max_ttl_seconds": 900,
        },
        "source_lock_closure_identity": {
            "source_compatibility_receipt_digest": _CP2A_D,
            "sealed_build_receipt_digest": _CP2A_D2,
            "identity_contract_digest": _CP2A_D,
        },
        "application_manifest_digest": _CP2A_D2,
        "prepare_sandbox_probe_receipt_digest": _CP2A_D,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    prepared_bundle = {
        "schema_version": "s2_4_prepared_install_bundle_v1",
        "prepare_id": _CP2A_PREP_ID,
        "artifact_locators": [{"locator": "blobs/sha256/aaa", "content_digest": _CP2A_D}],
        "base_runtime_tree_manifest_digest": _CP2A_D,
        "base_runtime_tree_digest": _CP2A_D2,
        "application_bundle_manifest_digest": _CP2A_D,
        "application_bundle_digest": _CP2A_D2,
        "launch_bundle_manifest_digest": _CP2A_D,
        "launch_bundle_digest": _CP2A_D2,
        "native_import_proof_digest": _CP2A_D,
        "staging_locator": staging_locator,
        "staging_root_owned_nonwritable": True,
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "created_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }
    artifacts["s2_4_prepared_install_bundle_v1"] = prepared_bundle

    artifacts["s2_4_prepare_effect_receipt_v1"] = {
        "schema_version": "s2_4_prepare_effect_receipt_v1",
        "prepare_id": _CP2A_PREP_ID,
        "prepare_core_digest": prepare_core_digest,
        "authorization_id": _CP2A_D,
        "authorization_digest": _CP2A_D2,
        "prepared_install_bundle_digest": _CP2A_D,
        "staging_locator": staging_locator,
        "journal_digest": _CP2A_D,
        "consumed_replay_entry_digest": _CP2A_D2,
        "postcheck_digest": _CP2A_D,
        "rollback_digest": _CP2A_D2,
        "terminal_status": "PREPARED",
        "evidence_class": "PLATFORM_ATTESTED",
        "source_head": _CP2A_GIT,
        "target_host": "trade-core",
        "trusted_host_time": _CP2A_TS,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_prepare_journal_v1"] = {
        "schema_version": "s2_4_prepare_journal_v1",
        "prepare_id": _CP2A_PREP_ID,
        "staging_root": _CP2A_STAGING,
        "entries": [
            {
                "seq": 0,
                "state": "PREPARING",
                "pre_state_digest": _CP2A_D,
                "post_state_digest": _CP2A_D2,
                "fsynced": True,
                "recorded_at": _CP2A_TS,
            }
        ],
        "terminal": True,
        "journal_integrity": {
            "preparing_fsynced_before_staging_create": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
        "outer_checksum": _CP2A_D,
        "self_digest": _CP2A_D2,
    }

    artifacts["s2_4_prepare_postcheck_v1"] = {
        "schema_version": "s2_4_prepare_postcheck_v1",
        "status": "PASS",
        "prepare_id": _CP2A_PREP_ID,
        "prepare_core_digest": prepare_core_digest,
        "verifier_node": "ops-verifier",
        "applier_node": "prepare-applier",
        "zero_residue_outside_staging": True,
        "staging_root_owned_nonwritable": True,
        "residue_scan_digest": _CP2A_D,
        "verifier_capture_digest": _CP2A_D2,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    artifacts["s2_4_prepare_rollback_v1"] = {
        "schema_version": "s2_4_prepare_rollback_v1",
        "status": "CLEANED_EXACT",
        "prepare_id": _CP2A_PREP_ID,
        "staging_root": _CP2A_STAGING,
        "pre_state_digest": _CP2A_D,
        "post_state_digest": _CP2A_D2,
        "task_owned_only": True,
        "staging_delta_removed": True,
        "staging_absent": True,
        "observed_at": _CP2A_TS,
        "expires_at": _CP2A_TS,
        "self_digest": _CP2A_D,
    }

    # 每份帶 self_digest 者以 canonical self-digest 重封(完整性;非生產者身分)。
    for artifact in artifacts.values():
        if "self_digest" in artifact:
            artifact["self_digest"] = artifact_self_digest(artifact)
    return artifacts


_CP2A_KEYS = (
    "s2_4_capability_probe_core_v1",
    "s2_4_capability_probe_intent_v1",
    "s2_4_capability_probe_effect_receipt_v1",
    "s2_4_capability_probe_journal_v1",
    "s2_4_capability_probe_postcheck_v1",
    "s2_4_capability_probe_rollback_v1",
    "network_sandbox_capability_attestation_v1",
    "s2_4_prepare_core_v1",
    "s2_4_prepare_intent_v1",
    "s2_4_prepare_effect_receipt_v1",
    "s2_4_prepare_journal_v1",
    "s2_4_prepare_postcheck_v1",
    "s2_4_prepare_rollback_v1",
    "s2_4_prepared_install_bundle_v1",
)
_CP2A_CORE_KEYS = ("s2_4_capability_probe_core_v1", "s2_4_prepare_core_v1")


def test_cp2a_schema_files_resolve_to_real_files() -> None:
    for key in _CP2A_KEYS:
        assert key in SCHEMA_FILES, key
        assert (SCHEMA_DIR / SCHEMA_FILES[key]).is_file(), key
    assert len(_CP2A_KEYS) == 14


@pytest.mark.parametrize("key", _CP2A_KEYS)
def test_cp2a_round_trip_validates_clean(key: str) -> None:
    fixture = _cp2a_fixtures()[key]
    assert validate_aiml_artifact(fixture) == [], key
    # closed schema: every top-level schema_version const matches its SCHEMA_FILES key.
    assert fixture["schema_version"] == key


@pytest.mark.parametrize("key", _CP2A_KEYS)
def test_cp2a_additional_properties_extra_key_rejected(key: str) -> None:
    fixture = deepcopy(_cp2a_fixtures()[key])
    fixture["__unexpected_extra__"] = "x"
    if "self_digest" in fixture:
        fixture["self_digest"] = artifact_self_digest(fixture)
    errors = validate_aiml_artifact(fixture)
    assert any("unexpected property" in e or "__unexpected_extra__" in e for e in errors), (key, errors)


@pytest.mark.parametrize("key", _CP2A_KEYS)
def test_cp2a_self_digest_binds_integrity_when_present(key: str) -> None:
    fixture = _cp2a_fixtures()[key]
    if "self_digest" not in fixture:
        pytest.skip(f"{key} is an unsigned core / journal-inner artifact")
    assert fixture["self_digest"] == artifact_self_digest(fixture)


@pytest.mark.parametrize("key", _CP2A_CORE_KEYS)
def test_cp2a_unsigned_core_excludes_id_auth_self_digest(key: str) -> None:
    # §5.1:core 是被簽名對象,其 digest 導 id → core 不得含 id/authorization/self_digest。
    schema = json.loads((SCHEMA_DIR / SCHEMA_FILES[key]).read_text(encoding="utf-8"))
    props = set(schema["properties"])
    required = set(schema["required"])
    forbidden = {
        "self_digest",
        "probe_id",
        "prepare_id",
        "derived_id",
        "authorization",
        "authorization_id",
        "authorization_digest",
        "authorization_set",
        "intent_id",
        "core_digest",
    }
    assert not (props & forbidden), (key, props & forbidden)
    assert not (required & forbidden), (key, required & forbidden)
    fixture = _cp2a_fixtures()[key]
    assert not (set(fixture) & forbidden), (key, set(fixture) & forbidden)


def test_cp2a_receipts_and_attestation_pin_no_runtime_production_pass() -> None:
    # 契約鐵律:任何 receipt/attestation 不得斷言 runtime/production PASS。
    fixtures = _cp2a_fixtures()
    # effect receipts:九 authority const-false + production_apply_performed/running_attested const-false。
    for key in ("s2_4_capability_probe_effect_receipt_v1", "s2_4_prepare_effect_receipt_v1"):
        forged = deepcopy(fixtures[key])
        forged["production_authority_flags"]["production_apply_performed"] = True
        forged["self_digest"] = artifact_self_digest(forged)
        errs = validate_aiml_artifact(forged)
        assert any("production_apply_performed" in e for e in errs), (key, errs)
    # network_sandbox attestation:is_runtime_production_pass const-false。
    forged = deepcopy(fixtures["network_sandbox_capability_attestation_v1"])
    forged["production_posture"]["is_runtime_production_pass"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    errs = validate_aiml_artifact(forged)
    assert any("is_runtime_production_pass" in e for e in errs), errs


def test_cp2a_terminal_and_pass_conditionals_have_teeth() -> None:
    fixtures = _cp2a_fixtures()
    # probe receipt:TERMINAL_CLEAN 要求 removed/reset_failed/zero_residue 皆 true。
    forged = deepcopy(fixtures["s2_4_capability_probe_effect_receipt_v1"])
    forged["transient_unit_lifecycle"]["removed"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("removed" in e for e in validate_aiml_artifact(forged))
    # probe postcheck:PASS 要求 no_surviving_unit 為 true。
    forged = deepcopy(fixtures["s2_4_capability_probe_postcheck_v1"])
    forged["no_surviving_unit"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("no_surviving_unit" in e for e in validate_aiml_artifact(forged))
    # prepare postcheck:PASS 要求 zero_residue_outside_staging 為 true。
    forged = deepcopy(fixtures["s2_4_prepare_postcheck_v1"])
    forged["zero_residue_outside_staging"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("zero_residue_outside_staging" in e for e in validate_aiml_artifact(forged))


def test_cp2a_route_intents_forbid_cross_route_surfaces() -> None:
    fixtures = _cp2a_fixtures()
    # probe intent:任一 §4:285 forbidden surface 翻 true → 拒(結構性,injection 前)。
    forged = deepcopy(fixtures["s2_4_capability_probe_intent_v1"])
    forged["forbidden_surfaces"]["pg"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("pg" in e for e in validate_aiml_artifact(forged))
    # prepare intent:APPLY/opt/etc 面翻 true → 拒。
    forged = deepcopy(fixtures["s2_4_prepare_intent_v1"])
    forged["forbidden_surfaces"]["opt_publish"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("opt_publish" in e for e in validate_aiml_artifact(forged))


def test_cp2a_frozen_pins_unchanged_after_schema_files_additions() -> None:
    # 加 14 個 SCHEMA_FILES 查找鍵不動 S0.3 classifier / v1|v2 component matrix / PROGRAM_SCHEMA_PATHS。
    from aiml_gate_receipt_validator import (
        aiml_component_effect_class_matrix_digest,
        aiml_component_effect_class_matrix_v2_digest,
        PROGRAM_SCHEMA_PATHS,
    )

    assert aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    assert aiml_component_effect_class_matrix_v2_digest() == (
        "sha256:01d3062c79725b32b7c1468d02013a0df28dfeba1cf29d513cbf3bd6b4143c64"
    )
    assert len(PROGRAM_SCHEMA_PATHS) == 7


# ── S2.4 · WP4 · W1 · CP2b(install/APPLY + component-effect + authorization + PG-topology 契約)──
# 這 16 份 closed schema 皆屬「契約」:round-trip 乾淨、additionalProperties 拒外鍵、unsigned
# aggregate core 排除 plan_id/idempotency_key/auth/self_digest、const-false 生產旗標與 allOf 有牙、
# install-plan 前置拒跨面、operator authorization 四 profile↔namespace 綁定、pg-topology 不自證判定。
_CP2B_D = "sha256:" + "a" * 64
_CP2B_D2 = "sha256:" + "b" * 64
_CP2B_GIT = "0" * 40
_CP2B_TS = "2026-07-24T00:00:00+00:00"
_CP2B_PLAN_HEX = "e" * 64
_CP2B_PLAN_ID = "s2-4-" + _CP2B_PLAN_HEX
_CP2B_CLASSES = (
    "HOST_IDENTITY_INSTALL",
    "PG_ROLE_ACL_MIGRATION",
    "CREDENTIAL_INSTALL",
    "LEARNING_RUNTIME",
    "ENGINE_SCANNER",
)
_CP2B_SSHSIG = "-----BEGIN SSH SIGNATURE-----\n" + "AAAA" * 12 + "\n-----END SSH SIGNATURE-----\n"


def _cp2b_install_plan_core() -> dict:
    return {
        "schema_version": "s2_4_install_plan_core_v1",
        "apply_rows": [
            {"component_effect_class": c, "component_intent_digest": _CP2B_D}
            for c in _CP2B_CLASSES
        ],
        "prepare_receipt_digest": _CP2B_D,
        "topology_pre_digest": _CP2B_D2,
        "hba_delta_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D2,
        "source_head": _CP2B_GIT,
        "target_host": "trade-core",
        "created_at": _CP2B_TS,
    }


def _cp2b_fixtures() -> dict:
    core = _cp2b_install_plan_core()
    core_digest = canonical_digest(core)

    artifacts: dict[str, dict] = {}
    artifacts["s2_4_install_plan_core_v1"] = core

    artifacts["s2_4_install_plan_v1"] = {
        "schema_version": "s2_4_install_plan_v1",
        "route_class": "s2_4_install_plan",
        "core": core,
        "core_digest": core_digest,
        "plan_id": _CP2B_PLAN_ID,
        "idempotency_key": _CP2B_PLAN_ID,
        "route_surface": {
            "aggregate_coordinator": True,
            "runtime_effect": True,
            "service": "system_unit_install_inactive",
            "pg": True,
            "migration": True,
            "secret": True,
            "risk": "critical",
            "runtime_claim": True,
            "apply_rows": list(_CP2B_CLASSES),
        },
        "forbidden_surfaces": {
            "prepare_fetch": False,
            "prepare_build": False,
            "arbitrary_shell": False,
            "arbitrary_sql": False,
            "arbitrary_path": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "aggregate": {
                "profile_identity": "aiml-s2-install-operator-v1",
                "signature_namespace": "arcane-equilibrium-aiml-s2-install",
                "max_ttl_seconds": 900,
            },
            "pg_migration": {
                "profile_identity": "aiml-s2-pg-migration-operator-v1",
                "signature_namespace": "arcane-equilibrium-aiml-s2-pg-migration",
                "max_ttl_seconds": 900,
            },
        },
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_effect_receipt_v1"] = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "idempotency_key": _CP2B_PLAN_ID,
        "status": "APPLIED_INACTIVE",
        "aggregate_authorization_id": _CP2B_D,
        "aggregate_authorization_digest": _CP2B_D2,
        "pg_authorization_id": _CP2B_D,
        "pg_authorization_digest": _CP2B_D2,
        "prepare_sandbox_probe_receipt_digest": _CP2B_D,
        "installed_unit_probe_receipt_digest": _CP2B_D2,
        "prepare_result_digest": _CP2B_D,
        "prepare_postcheck_digest": _CP2B_D2,
        "apply_row_results": [
            {"component_effect_class": c, "result_digest": _CP2B_D, "postcheck_digest": _CP2B_D2}
            for c in _CP2B_CLASSES
        ],
        "reverse_compensation_chain_digest": _CP2B_D,
        "journal_digest": _CP2B_D2,
        "unit_state": {"loaded": True, "disabled": True, "inactive": True},
        "service_flags": {
            "service_enabled": False,
            "service_active": False,
            "service_started_by_s2_4": False,
        },
        "evidence_class": "PLATFORM_ATTESTED",
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "source_head": _CP2B_GIT,
        "target_host": "trade-core",
        "trusted_host_time": _CP2B_TS,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_journal_v1"] = {
        "schema_version": "s2_4_install_journal_v1",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "idempotency_key": _CP2B_PLAN_ID,
        "expected_pre_state_digest": _CP2B_D,
        "aggregate_rollback_digest": _CP2B_D2,
        "entries": [
            {
                "seq": 0,
                "step_index": 0,
                "state": "APPLYING",
                "pre_state_digest": _CP2B_D,
                "post_state_digest": _CP2B_D2,
                "fsynced": True,
                "recorded_at": _CP2B_TS,
            }
        ],
        "terminal": True,
        "journal_integrity": {
            "applying_fsynced_before_effect": True,
            "same_filesystem_atomic_rename": True,
            "file_fsynced": True,
            "parent_dir_fsynced": True,
        },
        "outer_checksum": _CP2B_D,
        "self_digest": _CP2B_D2,
    }

    artifacts["s2_4_install_postcheck_v1"] = {
        "schema_version": "s2_4_install_postcheck_v1",
        "status": "PASS",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "verifier_node": "ops-verifier",
        "applier_node": "install-applier",
        "probe_lineage_verified": True,
        "prepare_lineage_verified": True,
        "plan_lineage_verified": True,
        "idempotency_verified": True,
        "pre_state_lineage_verified": True,
        "all_apply_rows_satisfied": True,
        "verifier_capture_digest": _CP2B_D,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_rollback_v1"] = {
        "schema_version": "s2_4_install_rollback_v1",
        "status": "COMPENSATED_EXACT",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "pre_state_digest": _CP2B_D,
        "post_state_digest": _CP2B_D2,
        "reverse_ops": [
            {"component_effect_class": c, "per_row_rollback_digest": _CP2B_D, "ownership_verified": True}
            for c in reversed(_CP2B_CLASSES)
        ],
        "ownership_aware": True,
        "exact_pre_state_restored": True,
        "daemon_reload_reasserted": True,
        "hba_reload_reasserted": True,
        "observer_role_preserved": True,
        "no_secret_reconstructed": True,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_install_step_result_v1"] = {
        "schema_version": "s2_4_install_step_result_v1",
        "plan_id": _CP2B_PLAN_ID,
        "step_index": 0,
        "component_effect_class": "HOST_IDENTITY_INSTALL",
        "state": "APPLIED",
        "pre_state_digest": _CP2B_D,
        "post_state_digest": _CP2B_D2,
        "task_owned_delta_digest": _CP2B_D,
        "apply_evidence_digest": _CP2B_D2,
        "postcheck_evidence_digest": _CP2B_D,
        "compensation_intent_digest": None,
        "compensation_result_digest": None,
        "observed_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_intent_v1"] = {
        "schema_version": "s2_4_component_effect_intent_v1",
        "component_effect_class": "PG_ROLE_ACL_MIGRATION",
        "install_plan_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D2,
        "required_intent_fields": {
            "topology_attestation_digest": _CP2B_D,
            "acl_manifest_digest": _CP2B_D2,
            "pg_migration_permit_digest": _CP2B_D,
            "admin_handle_descriptor_digest": _CP2B_D2,
        },
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_result_v1"] = {
        "schema_version": "s2_4_component_effect_result_v1",
        "component_effect_class": "CREDENTIAL_INSTALL",
        "install_plan_digest": _CP2B_D,
        "status": "SATISFIED",
        "applied_state_digest": _CP2B_D,
        "postcheck_digest": _CP2B_D2,
        "rollback_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D2,
        "post_state_digest": _CP2B_D,
        "evidence_class": "PLATFORM_ATTESTED",
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
        "observed_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_postcheck_v1"] = {
        "schema_version": "s2_4_component_effect_postcheck_v1",
        "status": "PASS",
        "component_effect_class": "ENGINE_SCANNER",
        "install_plan_digest": _CP2B_D,
        "verifier_node": "ops-verifier",
        "applier_node": "install-applier",
        "observed_subject_digest": _CP2B_D,
        "applied_state_verified": True,
        "pre_state_lineage_verified": True,
        "verifier_capture_digest": _CP2B_D2,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_component_effect_rollback_v1"] = {
        "schema_version": "s2_4_component_effect_rollback_v1",
        "status": "COMPENSATED_EXACT",
        "component_effect_class": "LEARNING_RUNTIME",
        "install_plan_digest": _CP2B_D,
        "pre_state_digest": _CP2B_D,
        "post_state_digest": _CP2B_D2,
        "ownership_aware": True,
        "exact_pre_state_restored": True,
        "no_secret_reconstructed": True,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_operator_authorization_v1"] = {
        "schema_version": "s2_4_operator_authorization_v1",
        "profile_identity": "aiml-s2-install-operator-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-install",
        "authorization_id": _CP2B_D,
        "payload_fields": ["domain", "authorization_id", "plan_core_digest", "plan_id"],
        "issued_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "sshsig_armored": _CP2B_SSHSIG,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_authorization_replay_ledger_v1"] = {
        "schema_version": "s2_4_authorization_replay_ledger_v1",
        "ledger_path": "/var/lib/arcane-equilibrium/aiml/install/s2_4/authorization-replay-ledger.json",
        "entries": [
            {
                "seq": 0,
                "prev_entry_digest": None,
                "authorization_id": _CP2B_D,
                "authorization_digest": _CP2B_D2,
                "profile_identity": "aiml-s2-install-operator-v1",
                "consumed_at": _CP2B_TS,
                "entry_digest": _CP2B_D,
                "fsynced": True,
            }
        ],
        "append_only": True,
        "self_digest": _CP2B_D,
    }

    artifacts["s2_4_pg_hba_delta_v1"] = {
        "schema_version": "s2_4_pg_hba_delta_v1",
        "plan_id": _CP2B_PLAN_ID,
        "plan_core_digest": core_digest,
        "cluster_identity_ref": _CP2B_D,
        "pre_hba_digest": _CP2B_D,
        "delta": {
            "operation": "ADD_ROW",
            "normalized_row": "host trading_ai aiml_engine_scanner 127.0.0.1/32 scram-sha-256",
            "insertion_anchor": "after:local all all",
        },
        "post_hba_digest": _CP2B_D2,
        "effective_rule": {
            "source": "127.0.0.1/32",
            "database": "trading_ai",
            "user": "aiml_engine_scanner",
            "method": "scram-sha-256",
        },
        "reload_operation": "pg_hba_reload",
        "rollback_projection_digest": _CP2B_D,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["pg_topology_attestation_v1"] = {
        "schema_version": "pg_topology_attestation_v1",
        "target_host": "trade-core",
        "source_head": _CP2B_GIT,
        "topology_status": "PG_TOPOLOGY_EVIDENCE_CAPTURED",
        "derived_verdict": None,
        "runtime_listener": {
            "socket_inode": 123,
            "owning_pid": 10,
            "owning_uid": 0,
            "executable_digest": _CP2B_D,
            "cgroup": "/system.slice/postgresql.service",
            "endpoint": "127.0.0.1:5432",
        },
        "proxy_hops": [],
        "admin_endpoint": {"endpoint_class": "attested_local_socket", "handle_class": "local_admin_handle"},
        "cluster_identity": {
            "system_identifier": "7000000000000000000",
            "server_version": "16.2",
            "database_oid": 16400,
            "postmaster_identity": "postmaster-pid-9",
            "reload_operation_id": "reload-op-1",
        },
        "file_identities": {
            "data_dir": {"device": 66306, "inode": 1, "path": "/var/lib/pgsql/16/data", "digest": _CP2B_D},
            "config_file": {"device": 66306, "inode": 2, "path": "/pg/postgresql.conf", "digest": _CP2B_D2},
            "hba_file": {"device": 66306, "inode": 3, "path": "/pg/pg_hba.conf", "digest": _CP2B_D},
        },
        "effective_hba_rule": {
            "source": "127.0.0.1/32",
            "database": "trading_ai",
            "user": "aiml_engine_scanner",
            "method": "scram-sha-256",
        },
        "end_to_end_reaches_cluster": True,
        "listener_config_digest": _CP2B_D,
        "proxy_config_digest": _CP2B_D2,
        "cluster_identity_digest": _CP2B_D,
        "observed_at": _CP2B_TS,
        "expires_at": _CP2B_TS,
        "self_digest": _CP2B_D,
    }

    artifacts["pg_topology_runtime_guard_v1"] = {
        "schema_version": "pg_topology_runtime_guard_v1",
        "guard_path": "/etc/arcane-equilibrium/aiml/engine-scanner/topology-runtime-guard.json",
        "cluster_identity_row_digest": _CP2B_D,
        "plan_topology_digest": _CP2B_D2,
        "runtime_endpoint": {"host": "127.0.0.1", "port": 5432, "dbname": "trading_ai"},
        "system_identifier": "7000000000000000000",
        "database_oid": 16400,
        "server_major_version": 16,
        "binding_nonce": "host-nonce-abc123",
        "expected_topology_values_digest": _CP2B_D,
        "self_digest": _CP2B_D,
    }

    for artifact in artifacts.values():
        if "self_digest" in artifact:
            artifact["self_digest"] = artifact_self_digest(artifact)
    return artifacts


_CP2B_KEYS = (
    "s2_4_install_plan_core_v1",
    "s2_4_install_plan_v1",
    "s2_4_install_effect_receipt_v1",
    "s2_4_install_journal_v1",
    "s2_4_install_postcheck_v1",
    "s2_4_install_rollback_v1",
    "s2_4_install_step_result_v1",
    "s2_4_component_effect_intent_v1",
    "s2_4_component_effect_result_v1",
    "s2_4_component_effect_postcheck_v1",
    "s2_4_component_effect_rollback_v1",
    "s2_4_operator_authorization_v1",
    "s2_4_authorization_replay_ledger_v1",
    "s2_4_pg_hba_delta_v1",
    "pg_topology_attestation_v1",
    "pg_topology_runtime_guard_v1",
)
_CP2B_CORE_KEYS = ("s2_4_install_plan_core_v1",)


def test_cp2b_schema_files_resolve_to_real_files() -> None:
    for key in _CP2B_KEYS:
        assert key in SCHEMA_FILES, key
        assert (SCHEMA_DIR / SCHEMA_FILES[key]).is_file(), key
    assert len(_CP2B_KEYS) == 16
    # CP2a(14)+ CP2b(16)加上既有基線 → 中央 SCHEMA_FILES 委派表 = 65。
    assert len(SCHEMA_FILES) == 65


@pytest.mark.parametrize("key", _CP2B_KEYS)
def test_cp2b_round_trip_validates_clean(key: str) -> None:
    fixture = _cp2b_fixtures()[key]
    assert validate_aiml_artifact(fixture) == [], key
    assert fixture["schema_version"] == key


@pytest.mark.parametrize("key", _CP2B_KEYS)
def test_cp2b_additional_properties_extra_key_rejected(key: str) -> None:
    fixture = deepcopy(_cp2b_fixtures()[key])
    fixture["__unexpected_extra__"] = "x"
    if "self_digest" in fixture:
        fixture["self_digest"] = artifact_self_digest(fixture)
    errors = validate_aiml_artifact(fixture)
    assert any("unexpected property" in e or "__unexpected_extra__" in e for e in errors), (key, errors)


@pytest.mark.parametrize("key", _CP2B_KEYS)
def test_cp2b_self_digest_binds_integrity_when_present(key: str) -> None:
    fixture = _cp2b_fixtures()[key]
    if "self_digest" not in fixture:
        pytest.skip(f"{key} carries no self_digest")
    assert fixture["self_digest"] == artifact_self_digest(fixture)


@pytest.mark.parametrize("key", _CP2B_CORE_KEYS)
def test_cp2b_unsigned_core_excludes_id_auth_self_digest(key: str) -> None:
    # §5.1:aggregate core 是被簽名對象,其 digest 導 plan_id 且 idempotency_key=plan_id → core
    # 不得含 plan_id/idempotency_key/authorization/self_digest(與 probe/prepare core 排除導出 id 同構)。
    schema = json.loads((SCHEMA_DIR / SCHEMA_FILES[key]).read_text(encoding="utf-8"))
    props = set(schema["properties"])
    required = set(schema["required"])
    forbidden = {
        "self_digest",
        "plan_id",
        "idempotency_key",
        "derived_id",
        "authorization",
        "authorization_id",
        "authorization_digest",
        "authorization_set",
        "core_digest",
    }
    assert not (props & forbidden), (key, props & forbidden)
    assert not (required & forbidden), (key, required & forbidden)
    fixture = _cp2b_fixtures()[key]
    assert not (set(fixture) & forbidden), (key, set(fixture) & forbidden)


def test_cp2b_receipt_and_row_result_pin_no_runtime_production_pass() -> None:
    # 契約鐵律:install effect receipt 與每個 component-effect row result 不得斷言 runtime/production PASS。
    fixtures = _cp2b_fixtures()
    for key in ("s2_4_install_effect_receipt_v1", "s2_4_component_effect_result_v1"):
        forged = deepcopy(fixtures[key])
        forged["production_authority_flags"]["production_apply_performed"] = True
        forged["self_digest"] = artifact_self_digest(forged)
        assert any("production_apply_performed" in e for e in validate_aiml_artifact(forged)), key
        forged = deepcopy(fixtures[key])
        forged["production_authority_flags"]["running_attested"] = True
        forged["self_digest"] = artifact_self_digest(forged)
        assert any("running_attested" in e for e in validate_aiml_artifact(forged)), key
    # install effect receipt:service_enabled/active/started_by_s2_4 皆 const-false。
    forged = deepcopy(fixtures["s2_4_install_effect_receipt_v1"])
    forged["service_flags"]["service_enabled"] = True
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("service_enabled" in e for e in validate_aiml_artifact(forged))


def test_cp2b_terminal_and_pass_conditionals_have_teeth() -> None:
    fixtures = _cp2b_fixtures()
    # install effect receipt:APPLIED_INACTIVE 要求 unit loaded/disabled/inactive 皆 true。
    forged = deepcopy(fixtures["s2_4_install_effect_receipt_v1"])
    forged["unit_state"]["inactive"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("inactive" in e for e in validate_aiml_artifact(forged))
    # install postcheck:PASS 要求 all_apply_rows_satisfied 為 true。
    forged = deepcopy(fixtures["s2_4_install_postcheck_v1"])
    forged["all_apply_rows_satisfied"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("all_apply_rows_satisfied" in e for e in validate_aiml_artifact(forged))
    # install rollback:COMPENSATED_EXACT 要求 exact_pre_state_restored 為 true。
    forged = deepcopy(fixtures["s2_4_install_rollback_v1"])
    forged["exact_pre_state_restored"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("exact_pre_state_restored" in e for e in validate_aiml_artifact(forged))
    # component postcheck:PASS 要求 applied_state_verified 為 true。
    forged = deepcopy(fixtures["s2_4_component_effect_postcheck_v1"])
    forged["applied_state_verified"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("applied_state_verified" in e for e in validate_aiml_artifact(forged))
    # component rollback:COMPENSATED_EXACT 要求 ownership_aware 為 true。
    forged = deepcopy(fixtures["s2_4_component_effect_rollback_v1"])
    forged["ownership_aware"] = False
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("ownership_aware" in e for e in validate_aiml_artifact(forged))


def test_cp2b_install_plan_forbids_cross_route_surfaces() -> None:
    # install plan:§4:287 forbidden surface(PREPARE fetch/build、任意 shell/SQL/path、broker/order)
    # 任一翻 true → 結構性拒(node injection 前)。
    fixtures = _cp2b_fixtures()
    for surface in ("prepare_build", "arbitrary_shell", "arbitrary_sql", "arbitrary_path", "broker_or_order"):
        forged = deepcopy(fixtures["s2_4_install_plan_v1"])
        forged["forbidden_surfaces"][surface] = True
        forged["self_digest"] = artifact_self_digest(forged)
        assert any(surface in e for e in validate_aiml_artifact(forged)), surface


def test_cp2b_component_intent_binds_required_fields_per_class() -> None:
    # §4 row ABI:每 class 的 required_intent_fields 少一個 → 拒(per-class allOf 有牙)。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["s2_4_component_effect_intent_v1"])
    del forged["required_intent_fields"]["acl_manifest_digest"]
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("acl_manifest_digest" in e for e in validate_aiml_artifact(forged))
    # 換到 CREDENTIAL_INSTALL class,缺 encrypted_blob_digest → 拒。
    forged = deepcopy(fixtures["s2_4_component_effect_intent_v1"])
    forged["component_effect_class"] = "CREDENTIAL_INSTALL"
    forged["required_intent_fields"] = {"credential_name": "engine-scanner-db", "host_identity_digest": _CP2B_D}
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("encrypted_blob_digest" in e for e in validate_aiml_artifact(forged))


def test_cp2b_operator_authorization_binds_profile_to_namespace() -> None:
    # §9.1:四 profile↔namespace 精確配對,錯配 → 拒;profile_identity 越界 enum → 拒。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["s2_4_operator_authorization_v1"])
    forged["signature_namespace"] = "arcane-equilibrium-aiml-s2-pg-migration"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("signature_namespace" in e for e in validate_aiml_artifact(forged))
    forged = deepcopy(fixtures["s2_4_operator_authorization_v1"])
    forged["profile_identity"] = "aiml-s2-rogue-operator-v1"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("enum" in e for e in validate_aiml_artifact(forged))


def test_cp2b_pg_topology_cannot_self_declare_verdict() -> None:
    # §8.2:pg_topology_attestation 僅載證據,derived_verdict 恆 const null;caller 帶任何判定 → 拒。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["pg_topology_attestation_v1"])
    forged["derived_verdict"] = "PASS"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("derived_verdict" in e for e in validate_aiml_artifact(forged))
    # topology_status 只是觀測類,無 PASS 值可選(越界即拒)。
    forged = deepcopy(fixtures["pg_topology_attestation_v1"])
    forged["topology_status"] = "PASS"
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("enum" in e for e in validate_aiml_artifact(forged))


def test_cp2b_pg_hba_delta_add_row_requires_normalized_row() -> None:
    # §5.1:HBA delta ADD_ROW 必帶 normalized_row + insertion_anchor;缺 → 拒。
    fixtures = _cp2b_fixtures()
    forged = deepcopy(fixtures["s2_4_pg_hba_delta_v1"])
    del forged["delta"]["normalized_row"]
    forged["self_digest"] = artifact_self_digest(forged)
    assert any("normalized_row" in e for e in validate_aiml_artifact(forged))


def test_cp2b_frozen_pins_unchanged_after_schema_files_additions() -> None:
    # 加 16 個 SCHEMA_FILES 查找鍵不動 S0.3 classifier / v1|v2 component matrix / PROGRAM_SCHEMA_PATHS。
    from aiml_gate_receipt_validator import (
        aiml_component_effect_class_matrix_digest,
        aiml_component_effect_class_matrix_v2_digest,
        PROGRAM_SCHEMA_PATHS,
    )

    assert aiml_effect_classifier_digest() == (
        "sha256:1cf8c021b066ceeb364e968add074d263cb28d63db421fdc40620e9904d0ddbc"
    )
    assert aiml_component_effect_class_matrix_digest() == (
        "sha256:22d78882a2dace9ceb640b74b2a5dca2f2a8cc05861720f5ab25c5c9ac86c445"
    )
    assert aiml_component_effect_class_matrix_v2_digest() == (
        "sha256:01d3062c79725b32b7c1468d02013a0df28dfeba1cf29d513cbf3bd6b4143c64"
    )
    assert len(PROGRAM_SCHEMA_PATHS) == 7

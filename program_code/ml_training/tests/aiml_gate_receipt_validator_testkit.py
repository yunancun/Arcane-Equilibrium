"""test_aiml_gate_receipt_validator* 共用 fixture builders(非收集模組)。

2000 行治理拆分:S0.3 session-attempt / dependency-graph / post-merge / GitHub attestation
builders 與共用 digest 常量自 test_aiml_gate_receipt_validator.py 逐字搬入,供三個 sibling
測試模組匯入;本檔名不以 test_ 開頭,pytest 不收集。
"""

from __future__ import annotations

import sys
from copy import deepcopy
from pathlib import Path


ML_ROOT = Path(__file__).resolve().parents[1]
if str(ML_ROOT) not in sys.path:
    sys.path.insert(0, str(ML_ROOT))

from aiml_gate_receipt_validator import (  # noqa: E402
    artifact_self_digest,
    github_policy_attestation_identity_digest,
    session_attempt_identity_digest,
)


DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64
DIGEST_D = "sha256:" + "d" * 64
DIGEST_E = "sha256:" + "e" * 64
HEAD_A = "a" * 40


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

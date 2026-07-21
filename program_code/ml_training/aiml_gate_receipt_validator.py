#!/usr/bin/env python3
"""Fail-closed stdlib validation for AI/ML landing governance artifacts."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

from agent_governance_schema import schema_subset_errors  # noqa: E402


SCHEMA_DIR = Path(__file__).resolve().parent / "schemas" / "aiml_gate_receipts"
SCHEMA_FILES = {
    "aiml_required_effect_classification_v1": "aiml_required_effect_classification_v1.schema.json",
    "github_repository_policy_attestation_v1": "github_repository_policy_attestation_v1.schema.json",
    "aiml_receipt_dependency_graph_v1": "aiml_receipt_dependency_graph_v1.schema.json",
    "landing_scope_v1": "landing_scope_v1.schema.json",
    "program_adoption_receipt_v1": "program_adoption_receipt_v1.schema.json",
    "session_attempt_v1": "session_attempt_v1.schema.json",
    "terminal_receipt_sink_v1": "terminal_receipt_sink_v1.schema.json",
}

S0_DEPENDENCY_DIGESTS = {
    "S0.1": "sha256:8fc9417f984025deabdc1b83ace95921ccfff1acb26a1b29243fc0a0a5ba79ad",
    "S0.2": "sha256:0115dbd3dc62d84e183aae5a28cbfd252eb45ecee51a652d8a4a155f14dfb41a",
}
S0_PREDECESSOR_CONTRACTS = {
    "s0_1_receipt": {
        "session_id": "S0.1",
        "receipt_type": "planning_documents_published_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "self_digest": S0_DEPENDENCY_DIGESTS["S0.1"],
    },
    "s0_2_receipt": {
        "session_id": "S0.2",
        "receipt_type": "serving_authority_receipt_v1",
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "self_digest": S0_DEPENDENCY_DIGESTS["S0.2"],
    },
}
PROGRAM_DOCUMENT_PATHS = (
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
PROGRAM_SCHEMA_PATHS = tuple(
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
PROGRAM_GOVERNANCE_PATHS = (
    ".codex/agent_registry_v1.json",
    "helper_scripts/maintenance_scripts/agent_governance.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_adoption.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_common.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_git.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_github.py",
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
PROGRAM_REVIEW_NODES = {
    "CC": "constitutional_gate",
    "E2": "independent_review",
    "E3": "security_gate",
    "E4": "regression",
    "MIT": "data_ml_review",
    "QA": "business_acceptance",
    "R4": "docs_integrity_review",
}

AIML_EFFECT_CLASSIFIER_RULES = {
    "S0.3": {
        "effect_class": "EXTERNAL_READONLY_ATTESTATION",
        "adapter_id": "github_repository_policy_attestation_v1",
        "actor_node_id": "github_policy_observer",
        "rollback_contract": "NOT_APPLICABLE_READ_ONLY",
        "independent_postcheck_node_id": "aiml_program_adoption_validator",
    }
}
S0_3_WORK_PACKAGE_ID = "AIML-S0.3-GOVERNANCE-ADOPTION"
S0_3_DIRECT_INTERFACES_BY_PHASE = {
    "SOURCE_BUILD": (
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
    ),
    "POST_MERGE_FINALIZATION": (
        "aiml_program_adoption_validator",
        "aiml_trusted_host_finalizer_v1",
        "github_repository_policy_attestation_v1",
        "program_adoption_receipt_v1",
    ),
}
S0_3_SIDE_EFFECT_BY_PHASE = {
    "SOURCE_BUILD": "repo_write",
    "POST_MERGE_FINALIZATION": "none",
}
S0_3_EXACT_OWNED_PATHS = {
    ".codex/agent_registry_v1.json",
    "TODO.md",
    "docs/adr/0050-development-agent-governance.md",
    "docs/agents/ai-ml-landing-delivery-protocol.md",
    "docs/agents/development-agent-governance.md",
    "docs/execution_plan/2026-07-19--ai_ml_long_lived_repair_and_landing_plan.md",
    "docs/execution_plan/ai_ml_landing/PROGRESS.md",
    "helper_scripts/maintenance_scripts/agent_governance.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_adoption.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_common.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_git.py",
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_github.py",
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
}
S0_3_OWNED_PATH_PREFIXES = (
    ".codex/schemas/",
    "docs/execution_plan/ai_ml_landing/",
    "program_code/ml_training/schemas/aiml_gate_receipts/",
)
S0_3_FORBIDDEN_FACT_RE = re.compile(
    r"(?:^|[^a-z0-9])(?:runtime|pg|postgres|deploy|broker|order|ml5|ml6|"
    r"migration|rust|bybit|ibkr)(?:[^a-z0-9]|$)",
    re.IGNORECASE,
)
GITHUB_SECRET_LIKE_RE = re.compile(
    r"(?:github_pat_|gh[pousr]_[A-Za-z0-9]{12,})|"
    r"(?:access[_-]?token|auth(?:orization)?|client[_-]?secret|password|"
    r"private[_-]?key)\s*[:=]|(?:basic|bearer)\s+[A-Za-z0-9._~+/=-]{12,}",
    re.IGNORECASE,
)

ExternalAttestationVerifier = Callable[[dict[str, Any]], bool]
# SourceManifestVerifier 是 caller/host 提供的來源清單驗證能力,簽章為
# (reviewed_head, merge_head, {path: sha256}) -> bool。回傳 True 是一項強契約,
# 必須同時成立:
#   1. reviewed_head 與 merge_head 兩者在 repo 皆存在;
#   2. `git merge-base --is-ancestor reviewed_head merge_head`(自反:兩者相等亦
#      通過),即 merge_head 為 reviewed_head 的後代或同一 commit,審過的樹確實被
#      合入採納樹;
#   3. 清單中每個 path 於 merge_head 的 blob sha256 與所給 digest 完全相符。
# 保持回傳 bool 以免簽章變動;祖裔義務由本 docstring 規範並由測試強制。離線 CLI
# 無此可信主機能力,故無法自證 PASS——此為刻意保留的可信主機委派。
SourceManifestVerifier = Callable[[str, str, dict[str, str]], bool]


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_digest(value: Any) -> str:
    """Return the canonical sha256 identity used by AIML governance artifacts."""

    return "sha256:" + hashlib.sha256(_canonical_bytes(value)).hexdigest()


def artifact_self_digest(artifact: dict[str, Any]) -> str:
    """Hash an immutable artifact while excluding its self-referential field."""

    return canonical_digest({
        key: value for key, value in artifact.items() if key != "self_digest"
    })


def landing_scope_identity_digest(scope: dict[str, Any]) -> str:
    """Bind the complete scope, cell coverage, environment and promotion graph."""

    projection = {
        field: scope.get(field)
        for field in (
            "scope_kind",
            "platform_scope",
            "policy_surface_id",
            "decision_cells",
            "evidence_environments",
            "promotion_edges",
        )
    }
    return canonical_digest(projection)


def evidence_environment_identity_digest(environment: dict[str, Any]) -> str:
    """Bind one declared evidence environment independently of list position."""

    return canonical_digest({
        key: value
        for key, value in environment.items()
        if key != "environment_id"
    })


def _canonical_list_is_sorted_unique(values: list[Any]) -> bool:
    identities = [_canonical_bytes(value) for value in values]
    return identities == sorted(set(identities))


def _contains_github_secret_like_content(value: Any) -> bool:
    if isinstance(value, str):
        return GITHUB_SECRET_LIKE_RE.search(value) is not None
    if isinstance(value, list):
        return any(_contains_github_secret_like_content(item) for item in value)
    if isinstance(value, dict):
        return any(
            _contains_github_secret_like_content(key)
            or _contains_github_secret_like_content(item)
            for key, item in value.items()
        )
    return False


def _directed_graph_has_cycle(adjacency: dict[str, set[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        if any(visit(next_node) for next_node in adjacency.get(node, set())):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in adjacency)


def session_attempt_identity_digest(attempt: dict[str, Any]) -> str:
    """Bind the row key and phase that fence one durable Session attempt."""

    return canonical_digest({
        "attempt_key": attempt.get("attempt_key"),
        "attempt_phase": attempt.get("attempt_phase"),
    })


def aiml_effect_classifier_digest() -> str:
    """Identify the fail-closed S0.3 classifier rules, independent of PM input."""

    return canonical_digest({
        "effect_rules": AIML_EFFECT_CLASSIFIER_RULES,
        "work_package_id": S0_3_WORK_PACKAGE_ID,
        "direct_interfaces_by_phase": S0_3_DIRECT_INTERFACES_BY_PHASE,
        "side_effect_by_phase": S0_3_SIDE_EFFECT_BY_PHASE,
        "exact_owned_paths": sorted(S0_3_EXACT_OWNED_PATHS),
        "owned_path_prefixes": S0_3_OWNED_PATH_PREFIXES,
    })


def _effect_classification_identity_digest(classification: dict[str, Any]) -> str:
    return canonical_digest({
        key: value
        for key, value in classification.items()
        if key not in {"classification_id", "self_digest"}
    })


def _s0_3_owned_path(path: str) -> bool:
    if (
        not path
        or path.startswith("/")
        or "\\" in path
        or any(segment in {"", ".", ".."} for segment in path.split("/"))
    ):
        return False
    if S0_3_FORBIDDEN_FACT_RE.search(path):
        return False
    return path in S0_3_EXACT_OWNED_PATHS or any(
        path.startswith(prefix) for prefix in S0_3_OWNED_PATH_PREFIXES
    )


def _s0_3_work_package_errors(
    work_package: Any,
    *,
    session_id: Any,
    attempt_phase: Any,
    attempt_paths: Any,
) -> list[str]:
    if session_id != "S0.3":
        return [f"unsupported AIML work package session: {session_id}"]
    if not isinstance(work_package, dict):
        return ["AIML work_package is required"]
    phase = work_package.get("phase")
    if phase not in S0_3_SIDE_EFFECT_BY_PHASE or phase != attempt_phase:
        return ["AIML work_package phase is invalid"]
    errors: list[str] = []
    if work_package.get("work_package_id") != S0_3_WORK_PACKAGE_ID:
        errors.append("unsupported AIML work_package_id")
    if work_package.get("side_effect_class") != S0_3_SIDE_EFFECT_BY_PHASE[phase]:
        errors.append("AIML work_package generic side_effect_class is invalid")
    if work_package.get("runtime_claim") is not False:
        errors.append("AIML S0.3 work_package runtime_claim must be false")
    owned_paths = work_package.get("owned_path_manifest")
    if not isinstance(owned_paths, list):
        errors.append("AIML work_package owned_path_manifest is invalid")
    else:
        if owned_paths != sorted(set(owned_paths)):
            errors.append("AIML work_package owned_path_manifest must be sorted and unique")
        if owned_paths != attempt_paths:
            errors.append("AIML work_package paths differ from attempt path_manifest")
        if phase == "SOURCE_BUILD" and not owned_paths:
            errors.append("AIML source-build work_package requires owned paths")
        if phase == "POST_MERGE_FINALIZATION" and owned_paths:
            errors.append("AIML post-merge finalization cannot own source paths")
        if any(not isinstance(path, str) or not _s0_3_owned_path(path) for path in owned_paths):
            errors.append("AIML work_package contains a forbidden owned path")
    interfaces = work_package.get("direct_interfaces")
    expected_interfaces = list(S0_3_DIRECT_INTERFACES_BY_PHASE[phase])
    if interfaces != expected_interfaces:
        errors.append(
            "AIML work_package direct_interfaces differ from exact phase contract"
        )
    return errors


def classify_required_effects(
    attempt: dict[str, Any], *, classified_at: str
) -> dict[str, Any]:
    """Derive AIML-required effects; callers cannot supply or downgrade them."""

    session_id = attempt.get("session_id")
    phase = attempt.get("attempt_phase")
    work_package = attempt.get("work_package")
    work_package_errors = _s0_3_work_package_errors(
        work_package,
        session_id=session_id,
        attempt_phase=phase,
        attempt_paths=attempt.get("path_manifest"),
    )
    if work_package_errors:
        raise ValueError("; ".join(work_package_errors))
    rule = AIML_EFFECT_CLASSIFIER_RULES.get(str(session_id))
    if rule is None:
        raise ValueError(f"unsupported AIML work package session: {session_id}")
    effects = [{
        "effect_class": rule["effect_class"],
        "status": (
            "DEFERRED_TO_POST_MERGE_FINALIZATION"
            if phase == "SOURCE_BUILD"
            else "REQUIRED_PENDING"
        ),
        "adapter_id": rule["adapter_id"],
        "actor_node_id": rule["actor_node_id"],
        "rollback_contract": rule["rollback_contract"],
        "independent_postcheck_node_id": rule[
            "independent_postcheck_node_id"
        ],
    }]
    classification: dict[str, Any] = {
        "schema_version": "aiml_required_effect_classification_v1",
        "classification_id": "sha256:" + "0" * 64,
        "session_attempt_id": attempt.get("attempt_id"),
        "session_id": session_id,
        "attempt_phase": phase,
        "classified_inputs": json.loads(json.dumps(work_package)),
        "classifier_digest": aiml_effect_classifier_digest(),
        "required_effects": effects,
        "classified_at": classified_at,
        "self_digest": "sha256:" + "0" * 64,
    }
    classification["classification_id"] = _effect_classification_identity_digest(
        classification
    )
    classification["self_digest"] = artifact_self_digest(classification)
    return classification


def _terminal_receipt_sink_body() -> dict[str, Any]:
    return {
        "schema_version": "terminal_receipt_sink_v1",
        "sink_id": "terminal_receipt_sink_v1",
        "status": "CONTRACT_ONLY",
        "authority": "terminal_candidate_validators_only",
        "destination_class": "EXTERNAL_IMMUTABLE_WORM",
        "allowed_terminal_receipt_types": [
            "aiml_module_landed_for_trading_receipt_v1",
            "aiml_platform_no_candidate_receipt_v1",
        ],
        "append_intent_schema_version": "terminal_receipt_append_intent_v1",
        "append_result_schema_version": "terminal_receipt_append_result_v1",
        "readback_ack_schema_version": "terminal_receipt_readback_ack_v1",
        "actor_contract": {
            "append_actor_class": "DEDICATED_APPEND_ACTOR",
            "readback_verifier_class": "INDEPENDENT_READBACK_VERIFIER",
            "same_actor_allowed": False,
        },
        "idempotency_key_fields": [
            "landing_scope_id",
            "terminal_state",
            "terminal_payload_digest",
        ],
        "payload_binding_fields": [
            "final_source_head",
            "landing_scope_id",
            "learning_runtime_digest",
            "terminal_payload_digest",
            "terminal_state",
        ],
        "implementation_owner_session": "S1.2",
        "implementation_paths": [],
    }


def terminal_receipt_sink_contract() -> dict[str, Any]:
    """Return S0.3's non-executable sink contract; S1.2 owns implementation."""

    contract = _terminal_receipt_sink_body()
    contract["self_digest"] = artifact_self_digest(contract)
    return contract


def github_policy_attestation_identity_digest(attestation: dict[str, Any]) -> str:
    """Bind repository, exact heads, observed policy, provenance and validity window."""

    return canonical_digest({
        key: value
        for key, value in attestation.items()
        if key not in {"attestation_id", "self_digest"}
    })


def program_adoption_identity_digest(receipt: dict[str, Any]) -> str:
    """Return the pre-graph adoption identity used as the dependency-graph root.

    The graph digest is intentionally excluded: the graph binds this adoption
    identity as its root, while the completed receipt binds the graph digest.
    This gives both directions without a self-digest cycle.
    """

    return canonical_digest({
        key: value
        for key, value in receipt.items()
        if key not in {
            "adoption_id", "receipt_dependency_graph_digest", "self_digest"
        }
    })


def _github_policy_attestation_errors(
    attestation: dict[str, Any], *, now: str | datetime | None
) -> list[str]:
    errors: list[str] = []
    if _contains_github_secret_like_content(attestation):
        errors.append(
            "GitHub repository-policy attestation contains secret-like content"
        )
    try:
        if isinstance(now, str):
            evaluated_at = _parse_timestamp(now)
        elif isinstance(now, datetime):
            if now.tzinfo is None:
                raise ValueError("now must be timezone-aware")
            evaluated_at = now
        else:
            evaluated_at = datetime.now(timezone.utc)
        observed_at = _parse_timestamp(attestation["observed_at"])
        expires_at = _parse_timestamp(attestation["expires_at"])
        valid_from = _parse_timestamp(attestation["valid_from"])
        effect_at = _parse_timestamp(attestation["effect_at"])
        if observed_at > evaluated_at:
            errors.append("GitHub repository-policy attestation is future-dated")
        if not observed_at <= valid_from <= effect_at < expires_at:
            errors.append(
                "GitHub repository-policy effect time is outside its authority window"
            )
        if any(
            _parse_timestamp(capture["captured_at"]) > observed_at
            for capture in attestation["evidence_captures"]
        ):
            errors.append("GitHub evidence capture postdates the attested observation")
    except (TypeError, ValueError) as error:
        errors.append(f"GitHub repository-policy timestamp is invalid: {error}")
    if attestation["observer_node_id"] == attestation["validator_node_id"]:
        errors.append("GitHub policy observer and adoption validator must be independent")
    ruleset = attestation["ruleset"]
    expected_checks = sorted(
        ruleset["required_checks"],
        key=lambda check: (check["context"], check["integration_id"] or -1),
    )
    if ruleset["required_checks"] != expected_checks:
        errors.append("GitHub required checks must be in canonical sorted order")
    if ruleset["ref_includes"] != sorted(ruleset["ref_includes"]) or ruleset[
        "ref_excludes"
    ] != sorted(ruleset["ref_excludes"]):
        errors.append("GitHub ruleset ref conditions must be sorted")
    if "~DEFAULT_BRANCH" in ruleset["ref_excludes"]:
        errors.append("GitHub ruleset excludes the default branch")
    if attestation["attestation_id"] != github_policy_attestation_identity_digest(
        attestation
    ):
        errors.append("GitHub repository-policy attestation_id is invalid")
    if attestation["self_digest"] != artifact_self_digest(attestation):
        errors.append("GitHub repository-policy attestation self_digest is invalid")
    return errors


def _program_adoption_receipt_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if receipt["adoption_id"] != program_adoption_identity_digest(receipt):
        errors.append("program adoption_id is invalid")
    if receipt["self_digest"] != artifact_self_digest(receipt):
        errors.append("program adoption receipt self_digest is invalid")
    dependencies = {
        item["session_id"]: item["receipt_digest"]
        for item in receipt["dependency_receipts"]
    }
    if dependencies != S0_DEPENDENCY_DIGESTS:
        errors.append("program adoption dependencies are not the exact S0.1/S0.2 lineage")
    for field, expected_paths in (
        ("document_manifest", PROGRAM_DOCUMENT_PATHS),
        ("schema_manifest", PROGRAM_SCHEMA_PATHS),
        ("governance_manifest", PROGRAM_GOVERNANCE_PATHS),
    ):
        paths = [item["path"] for item in receipt[field]]
        if paths != list(expected_paths):
            errors.append(f"program adoption {field} paths differ from exact contract")
    review_nodes = {
        item["role"]: item["node_id"] for item in receipt["review_bindings"]
    }
    if (
        len(review_nodes) != len(receipt["review_bindings"])
        or review_nodes != PROGRAM_REVIEW_NODES
    ):
        errors.append("program adoption review bindings are incomplete or substituted")
    # 每個 reviewer 綁定一個唯一的 role_fragment id;採納收尾不得讓兩個 reviewer 共用
    # 同一 fragment 佯裝獨立審查。
    fragment_ids = [item["fragment_id"] for item in receipt["review_bindings"]]
    if len(set(fragment_ids)) != len(fragment_ids):
        errors.append("program adoption review binding fragment ids are not unique")
    # review_generation 綁定 merge_head 的完整 repo 位元代(source_head==merge_head),
    # 其 digest 為正規雜湊,採納 fragment 的 final_generation 必須逐一等於它。
    review_generation = receipt["review_generation"]
    if receipt["review_generation_digest"] != canonical_digest(review_generation):
        errors.append("program adoption review generation digest is invalid")
    if review_generation["source_head"] != receipt["merge_head"]:
        errors.append("program adoption review generation is not bound to merge_head")
    if receipt["terminal_sink_contract_digest"] != terminal_receipt_sink_contract()[
        "self_digest"
    ]:
        errors.append("program adoption terminal sink contract binding is invalid")
    governance_digests = {
        item["path"]: item["digest"] for item in receipt["governance_manifest"]
    }
    if receipt["validator_binding"]["implementation_digest"] != governance_digests.get(
        "program_code/ml_training/aiml_gate_receipt_validator.py"
    ):
        errors.append("program adoption non-call validator implementation binding is invalid")
    return errors


def _s0_predecessor_receipt_errors(
    artifact_name: str,
    receipt: Any,
) -> list[str]:
    expected = S0_PREDECESSOR_CONTRACTS[artifact_name]
    if not isinstance(receipt, dict):
        return [f"{artifact_name} must be a complete receipt object"]
    errors: list[str] = []
    for field in ("session_id", "receipt_type", "program_id"):
        if receipt.get(field) != expected[field]:
            errors.append(f"{artifact_name} {field} differs from exact S0 lineage")
    claimed_digest = receipt.get("self_digest")
    if claimed_digest != artifact_self_digest(receipt):
        errors.append(
            f"{artifact_name} self_digest does not bind the complete canonical receipt"
        )
    if claimed_digest != expected["self_digest"]:
        errors.append(f"{artifact_name} digest differs from hardcoded S0 lineage")
    return errors


def validate_program_adoption_receipt(
    receipt: Any,
    *,
    artifacts: dict[str, Any],
    now: str | datetime | None = None,
    external_verifier: ExternalAttestationVerifier | None = None,
    source_manifest_verifier: SourceManifestVerifier | None = None,
) -> list[str]:
    """Validate the only S0.3 path that can issue ``PROGRAM_ADOPTED``.

    This is the canonical cross-artifact semantic validator used by governance
    closure.  Registry, routing and closure may select/call it but must not
    duplicate these AIML adoption rules.

    ``source_manifest_verifier`` is mandatory and fail-closed: a missing verifier
    or any non-``True`` return (including a raised exception) rejects the
    receipt.  Returning ``True`` is a strengthened obligation — the host must have
    confirmed that ``reviewed_head`` and ``merge_head`` both exist, that
    ``git merge-base --is-ancestor reviewed_head merge_head`` holds (reflexive:
    ``reviewed_head == merge_head`` is accepted as a fast-forward), and that every
    manifest ``path`` resolves at ``merge_head`` to the exact declared blob
    ``sha256``.  The reviewed/merge cross-binds below feed the exact heads handed
    to that obligation; the offline CLI has no such host capability.
    """

    errors = [
        f"program adoption receipt invalid: {error}"
        for error in validate_aiml_artifact(receipt, now=now)
    ]
    github_candidate = artifacts.get("github_attestation")
    if external_verifier is None:
        errors.append(
            "program adoption requires caller-supplied external GitHub verification"
        )
    elif not isinstance(github_candidate, dict):
        errors.append("program adoption external GitHub artifact is absent")
    else:
        try:
            externally_verified = external_verifier(github_candidate)
        except Exception:  # pragma: no cover - boundary failure is fail-closed
            externally_verified = False
        if externally_verified is not True:
            errors.append("program adoption external GitHub verification failed")
    if source_manifest_verifier is None:
        errors.append(
            "program adoption requires caller-supplied source manifest verification"
        )
    else:
        try:
            manifest_items = [
                item
                for field in (
                    "document_manifest",
                    "schema_manifest",
                    "governance_manifest",
                )
                for item in receipt[field]
            ]
            source_manifest = {
                item["path"]: item["digest"] for item in manifest_items
            }
            if len(source_manifest) != len(manifest_items):
                raise ValueError("source manifest paths are not unique")
            # reviewed_head/merge_head 是下方(reviewed_head==source-build
            # checkpoint、merge_head==finalization baseline)交叉綁定過的確切 head,
            # 於此餵給主機祖裔義務:主機須確認 merge_head 為 reviewed_head 的後代
            # (自反相等亦可),且各 path 於 merge_head 的 blob 與清單 digest 相符。
            source_verified = source_manifest_verifier(
                receipt["reviewed_head"],
                receipt["merge_head"],
                source_manifest,
            )
        except Exception:  # pragma: no cover - boundary failure is fail-closed
            source_verified = False
        if source_verified is not True:
            errors.append("program adoption source manifest verification failed")
    required_artifacts = {
        "s0_1_receipt",
        "s0_2_receipt",
        "source_attempt",
        "finalization_attempt",
        "effect_classification",
        "dependency_graph",
        "github_attestation",
        "terminal_sink_contract",
    }
    if set(artifacts) != required_artifacts:
        errors.append(
            "program adoption artifact inventory mismatch: "
            f"missing={sorted(required_artifacts - set(artifacts))} "
            f"extra={sorted(set(artifacts) - required_artifacts)}"
        )
        return errors
    for name, artifact in artifacts.items():
        if name in S0_PREDECESSOR_CONTRACTS:
            errors.extend(
                f"program adoption {error}"
                for error in _s0_predecessor_receipt_errors(name, artifact)
            )
            continue
        errors.extend(
            f"program adoption {name} invalid: {error}"
            for error in validate_aiml_artifact(artifact, now=now)
        )
    if errors or not isinstance(receipt, dict):
        return errors

    source_attempt = artifacts["source_attempt"]
    final_attempt = artifacts["finalization_attempt"]
    classification = artifacts["effect_classification"]
    graph = artifacts["dependency_graph"]
    github = artifacts["github_attestation"]
    terminal_sink = artifacts["terminal_sink_contract"]

    program_scope_ref = {"kind": "PROGRAM", "landing_scope_id": None}
    if receipt["scope_ref"] != program_scope_ref or any(
        artifact["scope_ref"] != program_scope_ref
        for artifact in (source_attempt, final_attempt, graph)
    ):
        errors.append("program adoption requires the PROGRAM null scope_ref throughout")
    if not (
        source_attempt["session_id"] == "S0.3"
        and source_attempt["attempt"] == 1
        and source_attempt["attempt_phase"] == "SOURCE_BUILD"
        and source_attempt["status"] == "MERGED"
    ):
        errors.append("program adoption requires merged S0.3 source-build attempt 1")
    if not (
        final_attempt["session_id"] == "S0.3"
        and final_attempt["attempt"] >= 2
        and final_attempt["attempt_phase"] == "POST_MERGE_FINALIZATION"
        and final_attempt["status"] == "FINALIZED"
    ):
        errors.append("program adoption requires a finalized post-merge S0.3 attempt")
    if receipt["source_build_attempt_id"] != source_attempt["attempt_id"]:
        errors.append("program adoption source-build attempt binding is invalid")
    if receipt["finalization_attempt_id"] != final_attempt["attempt_id"]:
        errors.append("program adoption finalization attempt binding is invalid")
    if receipt["attempt"] != final_attempt["attempt"]:
        errors.append("program adoption finalization attempt number binding is invalid")
    # reviewed_head/merge_head 交叉綁定:分別必須等於 source-build checkpoint 與
    # finalization baseline。這兩個確切 head 是上方 source_manifest_verifier 祖裔
    # 義務(merge_head 為 reviewed_head 後代 + blob 相符)的輸入。
    if receipt["reviewed_head"] != source_attempt["source"]["checkpoint_head"]:
        errors.append("program adoption reviewed_head differs from source-build checkpoint")
    if receipt["merge_head"] != final_attempt["source"]["baseline_head"]:
        errors.append("program adoption merge_head differs from finalization baseline")
    if github["reviewed_head"] != receipt["reviewed_head"] or github[
        "merge_head"
    ] != receipt["merge_head"]:
        errors.append("GitHub policy attestation is not bound to reviewed/merge heads")
    if receipt["github_policy_attestation_digest"] != github["self_digest"]:
        errors.append("program adoption GitHub policy attestation binding is invalid")
    if receipt["required_effect_classification_digest"] != classification[
        "self_digest"
    ]:
        errors.append("program adoption required-effect classification binding is invalid")
    if final_attempt["effect_classification_digest"] != classification["self_digest"]:
        errors.append("finalization attempt does not bind required-effect classification")
    if classification["session_attempt_id"] != final_attempt["attempt_id"] or (
        classification["required_effects"] != [{
            **AIML_EFFECT_CLASSIFIER_RULES["S0.3"],
            "status": "REQUIRED_PENDING",
        }]
    ):
        errors.append("program adoption requires exact post-merge external attestation classification")
    if receipt["receipt_dependency_graph_digest"] != graph["self_digest"]:
        errors.append("program adoption dependency-graph binding is invalid")
    if receipt["terminal_sink_contract_digest"] != terminal_sink["self_digest"]:
        errors.append("program adoption terminal sink contract artifact binding is invalid")
    graph_receipts = {
        item["receipt_id"]: item["receipt_digest"]
        for item in graph["receipts"]
    }
    if graph["root_receipt_id"] != "S0.3" or graph_receipts.get("S0.3") != (
        receipt["adoption_id"]
    ):
        errors.append("program adoption dependency graph root is invalid")
    if {
        key: graph_receipts.get(key) for key in S0_DEPENDENCY_DIGESTS
    } != S0_DEPENDENCY_DIGESTS:
        errors.append("program adoption dependency graph lacks exact S0 lineage")
    if graph_receipts.get("github-policy") != github["self_digest"]:
        errors.append("program adoption dependency graph substitutes GitHub authority")
    try:
        issued_at = _parse_timestamp(receipt["issued_at"])
        if isinstance(now, str):
            evaluated_at = _parse_timestamp(now)
        elif isinstance(now, datetime):
            evaluated_at = now
        else:
            evaluated_at = datetime.now(timezone.utc)
        if issued_at > evaluated_at:
            errors.append("program adoption receipt is future-dated")
        if _parse_timestamp(github["effect_at"]) != issued_at:
            errors.append("program adoption issuance differs from GitHub authority effect time")
    except (TypeError, ValueError) as error:
        errors.append(f"program adoption timestamp is invalid: {error}")
    return errors


def _load_schema(schema_version: str) -> dict[str, Any]:
    filename = SCHEMA_FILES.get(schema_version)
    if filename is None:
        raise ValueError(f"unsupported AIML artifact schema_version: {schema_version}")
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone missing")
    return parsed


def _dependency_graph_errors(
    graph: dict[str, Any], *, now: str | datetime | None
) -> list[str]:
    errors: list[str] = []
    if isinstance(now, str):
        evaluated_at = _parse_timestamp(now)
    elif isinstance(now, datetime):
        if now.tzinfo is None:
            raise ValueError("now must be timezone-aware")
        evaluated_at = now
    else:
        evaluated_at = datetime.now(timezone.utc)

    receipts = graph["receipts"]
    ids = [receipt["receipt_id"] for receipt in receipts]
    if len(ids) != len(set(ids)):
        errors.append("receipt dependency graph ids are not unique")
    by_id = {receipt["receipt_id"]: receipt for receipt in receipts}
    if graph["root_receipt_id"] not in by_id:
        errors.append("receipt dependency graph root is absent")
    if any(receipt["scope_ref"] != graph["scope_ref"] for receipt in receipts):
        errors.append("receipt dependency graph mixes landing scopes")
    if graph["scope_ref"] != {"kind": "PROGRAM", "landing_scope_id": None}:
        errors.append("S0 receipt dependency graph requires the PROGRAM null scope_ref")

    invalid: set[str] = set()
    digest_ids: dict[str, str] = {}
    for receipt in receipts:
        receipt_id = receipt["receipt_id"]
        receipt_digest = receipt["receipt_digest"]
        if receipt_digest in digest_ids:
            errors.append("receipt dependency graph digests are not unique")
            invalid.add(receipt_id)
        digest_ids[receipt_digest] = receipt_id
        observed_at = _parse_timestamp(receipt["observed_at"])
        if observed_at > evaluated_at:
            errors.append(f"receipt {receipt_id} is future-dated")
            invalid.add(receipt_id)
        validity_class = receipt["validity_class"]
        valid_from = receipt["valid_from"]
        expires = receipt["expires_at"]
        effect = receipt["effect_at"]
        consumed = receipt["consumed_at"]
        authority_digest = receipt["authority_receipt_digest"]
        if receipt["state"] != "ACTIVE":
            errors.append(f"receipt {receipt_id} is {receipt['state'].lower()}")
            invalid.add(receipt_id)
        if validity_class == "CURRENT_STATE_TTL":
            if (
                valid_from is None
                or expires is None
                or any(value is not None for value in (effect, consumed, authority_digest))
            ):
                errors.append(
                    f"receipt {receipt_id} CURRENT_STATE_TTL fields are invalid"
                )
                invalid.add(receipt_id)
            elif not (
                observed_at <= _parse_timestamp(valid_from)
                <= evaluated_at
                < _parse_timestamp(expires)
            ):
                errors.append(f"receipt {receipt_id} CURRENT_STATE_TTL is stale")
                invalid.add(receipt_id)
        elif validity_class == "EFFECT_TIME_AUTHORITY":
            if (
                valid_from is None
                or expires is None
                or effect is None
                or consumed is not None
                or authority_digest is not None
            ):
                errors.append(
                    f"receipt {receipt_id} EFFECT_TIME_AUTHORITY fields are invalid"
                )
                invalid.add(receipt_id)
            elif not (
                observed_at <= _parse_timestamp(valid_from)
                <= _parse_timestamp(effect)
                < _parse_timestamp(expires)
            ):
                errors.append(
                    f"receipt {receipt_id} EFFECT_TIME_AUTHORITY effect is outside its window"
                )
                invalid.add(receipt_id)
        elif validity_class == "IMMUTABLE_CONSUMED_EFFECT":
            if (
                any(value is not None for value in (valid_from, expires))
                or effect is None
                or consumed is None
                or authority_digest is None
            ):
                errors.append(
                    f"receipt {receipt_id} IMMUTABLE_CONSUMED_EFFECT fields are invalid"
                )
                invalid.add(receipt_id)
            elif not (
                observed_at
                <= _parse_timestamp(effect)
                <= _parse_timestamp(consumed)
                <= evaluated_at
            ):
                errors.append(
                    f"receipt {receipt_id} IMMUTABLE_CONSUMED_EFFECT time binding is invalid"
                )
                invalid.add(receipt_id)
        elif validity_class == "IMMUTABLE_LINEAGE":
            if any(
                value is not None
                for value in (
                    valid_from, expires, effect, consumed, authority_digest
                )
            ):
                errors.append(
                    f"receipt {receipt_id} IMMUTABLE_LINEAGE fields are invalid"
                )
                invalid.add(receipt_id)

    adjacency: dict[str, set[str]] = {receipt_id: set() for receipt_id in ids}
    for edge in graph["edges"]:
        consumer = edge["consumer_receipt_id"]
        dependency = edge["dependency_receipt_id"]
        if consumer not in by_id or dependency not in by_id:
            errors.append("receipt dependency edge references an unknown receipt")
            continue
        if consumer == dependency:
            errors.append(f"receipt {consumer} cannot depend on itself")
            invalid.add(consumer)
            continue
        adjacency[consumer].add(dependency)
        consumed_at = _parse_timestamp(edge["consumed_at"])
        authority = by_id[dependency]
        observed_at = _parse_timestamp(authority["observed_at"])
        valid_from = authority["valid_from"]
        expires = authority["expires_at"]
        lower_bound = (
            _parse_timestamp(valid_from) if valid_from is not None else observed_at
        )
        if consumed_at < lower_bound or (
            expires is not None and consumed_at >= _parse_timestamp(expires)
        ):
            errors.append(
                f"receipt {consumer} consumed dependency {dependency} outside its validity window"
            )
            invalid.add(consumer)
        if (
            authority["validity_class"] == "EFFECT_TIME_AUTHORITY"
            and authority["effect_at"] != edge["consumed_at"]
        ):
            errors.append(
                f"receipt {consumer} effect time differs from authority {dependency}"
            )
            invalid.add(consumer)

    for receipt in receipts:
        if receipt["validity_class"] != "IMMUTABLE_CONSUMED_EFFECT":
            continue
        receipt_id = receipt["receipt_id"]
        authority_id = digest_ids.get(str(receipt["authority_receipt_digest"]))
        if authority_id is None:
            errors.append(
                f"receipt {receipt_id} immutable effect authority digest is unknown"
            )
            invalid.add(receipt_id)
            continue
        authority = by_id[authority_id]
        if (
            authority["validity_class"] != "EFFECT_TIME_AUTHORITY"
            or authority["effect_at"] != receipt["effect_at"]
            or authority_id not in adjacency.get(receipt_id, set())
        ):
            errors.append(
                f"receipt {receipt_id} immutable effect authority binding is invalid"
            )
            invalid.add(receipt_id)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(receipt_id: str) -> None:
        if receipt_id in visited:
            return
        if receipt_id in visiting:
            errors.append("receipt dependency graph contains a cycle")
            invalid.add(receipt_id)
            return
        visiting.add(receipt_id)
        for dependency in adjacency.get(receipt_id, set()):
            visit(dependency)
        visiting.remove(receipt_id)
        visited.add(receipt_id)

    for receipt_id in ids:
        visit(receipt_id)

    changed = True
    while changed:
        changed = False
        for consumer, dependencies in adjacency.items():
            if consumer not in invalid and dependencies.intersection(invalid):
                invalid.add(consumer)
                changed = True
    if graph["root_receipt_id"] in invalid:
        errors.append("receipt dependency graph root is invalidated by dependency state")
    if graph["self_digest"] != artifact_self_digest(graph):
        errors.append("receipt dependency graph self_digest is invalid")
    return errors


def validate_aiml_artifact(
    artifact: Any, *, now: str | datetime | None = None
) -> list[str]:
    """Validate one typed artifact without third-party schema dependencies."""

    if not isinstance(artifact, dict):
        return ["AIML artifact must be an object"]
    schema_version = artifact.get("schema_version")
    if not isinstance(schema_version, str):
        return ["AIML artifact schema_version must be a string"]
    try:
        schema = _load_schema(schema_version)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    errors = schema_subset_errors(artifact, schema, schema)
    if errors:
        return errors
    if schema_version == "landing_scope_v1" and artifact["landing_scope_id"] != (
        landing_scope_identity_digest(artifact)
    ):
        errors.append("landing_scope_id does not bind the exact landing scope identity")
    if schema_version == "landing_scope_v1" and any(
        environment["environment_id"] != evidence_environment_identity_digest(
            environment
        )
        for environment in artifact["evidence_environments"]
    ):
        errors.append("evidence_environment identity digest is invalid")
    if schema_version == "landing_scope_v1" and not _canonical_list_is_sorted_unique(
        artifact["decision_cells"]
    ):
        errors.append("landing scope decision_cells must be sorted and unique")
    if schema_version == "landing_scope_v1":
        environment_ids = {
            environment["environment_id"]
            for environment in artifact["evidence_environments"]
        }
        if any(
            edge["from_environment_id"] not in environment_ids
            or edge["to_environment_id"] not in environment_ids
            for edge in artifact["promotion_edges"]
        ):
            errors.append(
                "landing scope promotion edge references an unknown environment"
            )
        if any(
            edge["from_environment_id"] == edge["to_environment_id"]
            for edge in artifact["promotion_edges"]
        ):
            errors.append("landing scope promotion edge cannot target itself")
        promotion_graph = {environment_id: set() for environment_id in environment_ids}
        for edge in artifact["promotion_edges"]:
            if (
                edge["from_environment_id"] in promotion_graph
                and edge["to_environment_id"] in promotion_graph
            ):
                promotion_graph[edge["from_environment_id"]].add(
                    edge["to_environment_id"]
                )
        if _directed_graph_has_cycle(promotion_graph):
            errors.append("landing scope promotion graph contains a cycle")
    if schema_version == "session_attempt_v1":
        scope_ref = artifact["scope_ref"]
        if artifact["session_id"].startswith("S0.") and scope_ref != {
            "kind": "PROGRAM",
            "landing_scope_id": None,
        }:
            errors.append("S0.x session attempt requires the PROGRAM null scope_ref")
        if (
            scope_ref["kind"] == "PROGRAM"
            and scope_ref["landing_scope_id"] is not None
        ) or (
            scope_ref["kind"] == "LANDING_SCOPE"
            and scope_ref["landing_scope_id"] is None
        ):
            errors.append("session attempt scope_ref kind and landing_scope_id disagree")
        if artifact["attempt_id"] != session_attempt_identity_digest(artifact):
            errors.append("attempt_id does not bind the exact Session attempt identity")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("session attempt self_digest is invalid")
        expected_attempt_key = {
            "session_id": artifact["session_id"],
            "scope_ref": artifact["scope_ref"],
            "cohort_epoch": artifact["cohort_epoch"],
            "attempt": artifact["attempt"],
        }
        if artifact["attempt_key"] != expected_attempt_key:
            errors.append("session attempt_key differs from its canonical row fields")
        bootstrap = artifact["bootstrap_admission"]
        attempt_phase = artifact["attempt_phase"]
        if bootstrap["baseline_head"] != artifact["source"]["baseline_head"]:
            errors.append("session bootstrap baseline differs from source baseline")
        # 只有 SOURCE_BUILD 持有 writer lease;此時 lease.lease_id 與
        # bootstrap.writer_lease_id 必須互綁。POST_MERGE 為唯讀收尾,schema 已禁止
        # 兩者出現,故此綁定僅在 SOURCE_BUILD 生效。
        if attempt_phase == "SOURCE_BUILD" and (
            bootstrap["writer_lease_id"] != artifact["lease"]["lease_id"]
        ):
            errors.append("session bootstrap writer lease binding is invalid")
        errors.extend(_s0_3_work_package_errors(
            artifact["work_package"],
            session_id=artifact["session_id"],
            attempt_phase=artifact["attempt_phase"],
            attempt_paths=artifact["path_manifest"],
        ))
        if artifact["path_manifest"] != sorted(set(artifact["path_manifest"])):
            errors.append("session attempt path_manifest must be sorted and unique")
        writer_paths = [
            path
            for node in artifact["dag_nodes"]
            for path in node["writer_paths"]
        ]
        writer_nodes = [
            node for node in artifact["dag_nodes"] if node["writer_paths"]
        ]
        if len(writer_nodes) > 2:
            errors.append("session attempt admits more than two writer nodes")
        if any(
            node["writer_paths"] != sorted(set(node["writer_paths"]))
            for node in writer_nodes
        ):
            errors.append("session attempt writer path ownership must be sorted and unique")
        if len(writer_paths) != len(set(writer_paths)):
            errors.append("session attempt writer path ownership overlaps")
        if not set(writer_paths).issubset(set(artifact["path_manifest"])):
            errors.append("session attempt writer paths exceed path_manifest")
        native = artifact["native_admission"]
        matching_native_nodes = [
            node
            for node in artifact["dag_nodes"]
            if node["node_id"] == native["node_id"]
            and node["node_class"] == native["node_class"]
            and node["permission"] == native["permission"]
        ]
        if len(matching_native_nodes) != 1:
            errors.append("session native admission does not match exactly one DAG node")
        if attempt_phase == "SOURCE_BUILD":
            try:
                acquired_at = _parse_timestamp(artifact["lease"]["acquired_at"])
                heartbeat_at = _parse_timestamp(artifact["lease"]["heartbeat_at"])
                expires_at = _parse_timestamp(artifact["lease"]["expires_at"])
                if not acquired_at <= heartbeat_at < expires_at:
                    errors.append("session attempt lease timestamps are out of order")
                if isinstance(now, str):
                    evaluated_at = _parse_timestamp(now)
                elif isinstance(now, datetime):
                    if now.tzinfo is None:
                        raise ValueError("now must be timezone-aware")
                    evaluated_at = now
                else:
                    evaluated_at = datetime.now(timezone.utc)
                if (
                    evaluated_at >= expires_at
                    and artifact["status"] in {"CLAIMED", "IN_PROGRESS"}
                ):
                    errors.append("expired session attempt must enter RECOVERY_REQUIRED")
            except (TypeError, ValueError) as error:
                errors.append(f"session attempt lease timestamp is invalid: {error}")
        elif attempt_phase == "POST_MERGE_FINALIZATION":
            # 收尾階段不得殘留任何 writer lease;唯讀 admission 必須 read_only=true,
            # 且 admitted_at <= heartbeat_at(心跳不得早於納入時刻)。schema 已強制
            # read_only_admission 存在,此處為防禦性複核。
            if "lease" in artifact:
                errors.append("post-merge finalization attempt cannot hold a writer lease")
            if "writer_lease_id" in bootstrap:
                errors.append(
                    "post-merge finalization bootstrap cannot hold a writer lease id"
                )
            read_only_admission = artifact["read_only_admission"]
            if read_only_admission["read_only"] is not True:
                errors.append("post-merge finalization requires a read-only admission")
            try:
                admitted_at = _parse_timestamp(read_only_admission["admitted_at"])
                heartbeat_at = _parse_timestamp(read_only_admission["heartbeat_at"])
                if not admitted_at <= heartbeat_at:
                    errors.append(
                        "post-merge read-only admission timestamps are out of order"
                    )
            except (TypeError, ValueError) as error:
                errors.append(
                    f"post-merge read-only admission timestamp is invalid: {error}"
                )
    if schema_version == "aiml_receipt_dependency_graph_v1":
        try:
            errors.extend(_dependency_graph_errors(artifact, now=now))
        except (TypeError, ValueError) as error:
            errors.append(f"receipt dependency graph timestamp is invalid: {error}")
    if schema_version == "aiml_required_effect_classification_v1":
        if artifact["classification_id"] != _effect_classification_identity_digest(
            artifact
        ):
            errors.append("AIML effect classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML effect classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_effect_classifier_digest():
            errors.append("AIML effect classifier digest is not admitted")
        expected = classify_required_effects(
            {
                "session_id": artifact["session_id"],
                "attempt_id": artifact["session_attempt_id"],
                "attempt_phase": artifact["attempt_phase"],
                "path_manifest": artifact["classified_inputs"][
                    "owned_path_manifest"
                ],
                "work_package": artifact["classified_inputs"],
            },
            classified_at=artifact["classified_at"],
        )
        if artifact["required_effects"] != expected["required_effects"]:
            errors.append("AIML required effects differ from classifier output")
    if schema_version == "terminal_receipt_sink_v1":
        expected_contract = terminal_receipt_sink_contract()
        if artifact != expected_contract:
            errors.append(
                "terminal_receipt_sink_v1 must remain the exact S0.3 contract-only declaration"
            )
    if schema_version == "github_repository_policy_attestation_v1":
        errors.extend(_github_policy_attestation_errors(artifact, now=now))
    if schema_version == "program_adoption_receipt_v1":
        errors.extend(_program_adoption_receipt_errors(artifact))
    return errors

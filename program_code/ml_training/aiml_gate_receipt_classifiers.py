"""S0.3 classifier + v1/v2 component-effect 矩陣下層(facade 2000 行治理拆分;WP4 S2.4)。

這是 ``aiml_gate_receipt_validator``(facade)的**下層**:凍結的 S0.3 effect-classifier 常量
(AIML_EFFECT_CLASSIFIER_RULES / S0_3_*)與其 digest、S1 landing sibling work-package 檢查、
S1.2 v1 與 S2.4 v2 兩套七類 component-effect 矩陣及其 sibling 分類器。全部為逐位元組等值搬移,
S0.3 / v1 / v2 三個分類身分 digest 保持 byte-frozen(拆分前後重算相等);消費者「只」匯入 facade。

**循環相依處理。** 本模組 top-level 只匯入 sibling 下層 ``aiml_gate_receipt_schema_core``,
絕不匯入 facade。
"""

from __future__ import annotations

import json
import re
from typing import Any

from aiml_gate_receipt_schema_core import artifact_self_digest, canonical_digest


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


# S1 formal-closure Wave A:generalized landing attempt 的 sibling work-package 檢查。刻意 NOT
# 呼叫 _s0_3_work_package_errors——它把 S0.3 const(work_package_id / direct_interfaces / side_effect
# / runtime_claim=false)全數硬綁。這裡只做結構檢查(sorted/unique owned paths、path⊆manifest、
# 相位一致、路徑安全)且 side_effect_class/runtime_claim 已被寬鬆化,S0.3 分類身分因此完全不受影響。
AIML_LANDING_SIDE_EFFECT_CLASSES = {"repo_write", "none", "target_host_probe"}


def _aiml_landing_owned_path(path: Any) -> bool:
    if not isinstance(path, str) or not path or path.startswith("/") or "\\" in path:
        return False
    return not any(segment in {"", ".", ".."} for segment in path.split("/"))


def _aiml_landing_work_package_errors(
    work_package: Any,
    *,
    attempt_phase: Any,
    attempt_paths: Any,
) -> list[str]:
    if not isinstance(work_package, dict):
        return ["AIML landing work_package is required"]
    phase = work_package.get("phase")
    if phase not in {"SOURCE_BUILD", "POST_MERGE_FINALIZATION"} or phase != attempt_phase:
        return ["AIML landing work_package phase is invalid"]
    errors: list[str] = []
    if not isinstance(work_package.get("work_package_id"), str) or not work_package.get(
        "work_package_id"
    ):
        errors.append("AIML landing work_package_id must be a non-empty string")
    if work_package.get("side_effect_class") not in AIML_LANDING_SIDE_EFFECT_CLASSES:
        errors.append("AIML landing work_package side_effect_class is not admitted")
    if not isinstance(work_package.get("runtime_claim"), bool):
        errors.append("AIML landing work_package runtime_claim must be boolean")
    owned_paths = work_package.get("owned_path_manifest")
    if not isinstance(owned_paths, list):
        errors.append("AIML landing work_package owned_path_manifest is invalid")
    else:
        if owned_paths != sorted(set(owned_paths)):
            errors.append("AIML landing work_package owned_path_manifest must be sorted and unique")
        if owned_paths != attempt_paths:
            errors.append("AIML landing work_package paths differ from attempt path_manifest")
        if phase == "SOURCE_BUILD" and not owned_paths:
            errors.append("AIML landing source-build work_package requires owned paths")
        if phase == "POST_MERGE_FINALIZATION" and owned_paths:
            errors.append("AIML landing post-merge finalization cannot own source paths")
        if any(not _aiml_landing_owned_path(path) for path in owned_paths):
            errors.append("AIML landing work_package contains an unsafe owned path")
    interfaces = work_package.get("direct_interfaces")
    if not isinstance(interfaces, list) or not interfaces or any(
        not isinstance(item, str) or not item for item in interfaces
    ):
        errors.append("AIML landing work_package direct_interfaces must be a non-empty string list")
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


# --------------------------------------------------------------------------- #
# S1.2 (LR0B) 七類 component effect 的宣告式 vocabulary/matrix + sibling 分類器。
# 這是 plan §LR0B 要求的 typed 七類擁有權/allowlist 矩陣:每類 → 必綁的 exact-intent
# 欄位 + recovery 契約 + adapter 綁定。新增一類是「資料編輯」,不是新程式碼。此矩陣與其
# digest 與 S0.3 的 AIML_EFFECT_CLASSIFIER_RULES / aiml_effect_classifier_digest 完全
# 獨立(sibling),故 S0.3 保持 byte-frozen(見 §0 凍結約束)。
# --------------------------------------------------------------------------- #
AIML_COMPONENT_EFFECT_CLASS_MATRIX: dict[str, dict[str, Any]] = {
    "CREDENTIAL_ROTATION": {
        "required_intent_fields": [
            "secret_slot_target", "role_target", "old_fingerprint",
            "new_fingerprint", "rotation_order", "old_credential_rejection_proof",
        ],
        "recovery_contract": "rollback_or_forward_only",
        "adapter_id": "credential_rotation_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "credential_rotation_actor",
        "independent_postcheck_node_id": "credential_rotation_ops_postcheck",
    },
    "PG_ROLE_ACL_MIGRATION": {
        "required_intent_fields": [
            "migration_id", "migration_checksum", "role_acl_delta",
            "pre_state_digest", "transactional_or_double_apply", "recovery",
        ],
        "recovery_contract": "rollback_or_approved_forward",
        "adapter_id": "pg_role_acl_migration_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "pg_role_acl_migration_actor",
        "independent_postcheck_node_id": "pg_role_acl_migration_ops_postcheck",
    },
    "ENGINE_SCANNER": {
        "required_intent_fields": [
            "binary_digest", "unit", "env_digest", "config_digest",
            "stop_start_order", "readiness_deadman_checks", "prior_bundle_rollback",
        ],
        "recovery_contract": "prior_bundle_rollback",
        "adapter_id": "engine_scanner_deploy_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "engine_scanner_deploy_actor",
        "independent_postcheck_node_id": "engine_scanner_ops_postcheck",
    },
    "LEARNING_RUNTIME": {
        "required_intent_fields": [
            "runtime_identity", "dependency_manifest_digest",
            "mount_network_socket_secret_surface", "exact_rollback",
        ],
        "recovery_contract": "exact_rollback",
        "adapter_id": "learning_runtime_deploy_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "learning_runtime_deploy_actor",
        "independent_postcheck_node_id": "learning_runtime_ops_postcheck",
    },
    "CONTROLLER_WORKERS": {
        "required_intent_fields": [
            "unit_slice_cgroup_uid_pgrole_set", "queue_fencing_state",
            "start_order", "drain_rollback",
        ],
        "recovery_contract": "drain_rollback",
        "adapter_id": "controller_workers_deploy_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "controller_workers_deploy_actor",
        "independent_postcheck_node_id": "controller_workers_ops_postcheck",
    },
    "RETENTION_APPLY": {
        "required_intent_fields": [
            "tombstone_object_set", "deleter_identity", "restore_capacity",
            "interruption_recovery",
        ],
        "recovery_contract": "interruption_recovery_and_postcheck",
        "adapter_id": "retention_apply_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "retention_apply_actor",
        "independent_postcheck_node_id": "retention_apply_ops_postcheck",
    },
    # 唯一在 S1.2 落地並 disposable-proven 的具體 adapter(見 §5)。
    "TERMINAL_RECEIPT_APPEND": {
        "required_intent_fields": [
            "destination_class", "terminal_payload_digest", "final_source_head",
            "landing_scope_id", "learning_runtime_digest", "terminal_state",
            "append_actor", "idempotency_key", "independent_readback_ack",
        ],
        "recovery_contract": "interruption_retry_same_idempotency_key",
        "adapter_id": "terminal_receipt_sink_adapter_v1",
        "adapter_binding_status": "IMPLEMENTED_DISPOSABLE",
        "actor_node_id": "terminal_receipt_append_actor",
        "independent_postcheck_node_id": "terminal_receipt_independent_readback_verifier",
    },
}
# 每一類都攜帶的不可調 OPS/PM/獨立性契約旗標:「施加 effect 的 actor 不能是其唯一驗證者」。
AIML_COMPONENT_EFFECT_CLASS_INVARIANTS = {
    "requires_ops_preflight": True,
    "requires_pm_operator_approved_intent": True,
    "requires_independent_ops_postcheck": True,
    "applier_is_not_sole_verifier": True,
}


def aiml_component_effect_class_matrix_digest() -> str:
    """Identify the 7-class component-effect matrix, independent of S0.3.

    Analogue of ``aiml_effect_classifier_digest`` but a **separate** digest so
    the S0.3 classifier stays byte-frozen.
    """

    return canonical_digest({
        "component_effect_class_matrix": AIML_COMPONENT_EFFECT_CLASS_MATRIX,
        "class_invariants": AIML_COMPONENT_EFFECT_CLASS_INVARIANTS,
    })


def _component_effect_class_identity_digest(classification: dict[str, Any]) -> str:
    return canonical_digest({
        key: value
        for key, value in classification.items()
        if key not in {"classification_id", "self_digest"}
    })


def _component_effect_surface_tokens() -> frozenset[str]:
    # 任一 component 的 adapter/actor/postcheck 節點 id 都是「碰到 effectful 面」的標記。
    tokens: set[str] = set()
    for row in AIML_COMPONENT_EFFECT_CLASS_MATRIX.values():
        tokens.add(row["adapter_id"])
        tokens.add(row["actor_node_id"])
        tokens.add(row["independent_postcheck_node_id"])
    return frozenset(tokens)


def _component_surfaces_touched(
    owned_path_manifest: Any, direct_interfaces: Any
) -> set[str]:
    tokens = _component_effect_surface_tokens()
    touched: set[str] = set()
    for collection in (owned_path_manifest, direct_interfaces):
        if isinstance(collection, list):
            for item in collection:
                if isinstance(item, str) and item in tokens:
                    touched.add(item)
    return touched


def classify_component_required_effects(
    work_package: Any, *, classified_at: str
) -> dict[str, Any]:
    """Derive a component's required effect from the matrix; block source-only.

    The required ``effect_class`` / ``adapter_id`` / ``actor_node_id`` /
    ``rollback_contract`` / ``independent_postcheck_node_id`` /
    ``required_intent_fields`` are looked up in
    ``AIML_COMPONENT_EFFECT_CLASS_MATRIX``; the caller cannot supply or downgrade
    them.  This is the enforcement point for "a Session cannot self-declare an
    effectful component row as source-only" — it **raises** (never emits a
    ``NONE`` classification) when:

    * ``component_effect_class`` is ``NONE``/omitted/unknown yet the
      ``owned_path_manifest``/``direct_interfaces`` intersect a component surface;
    * the declared ``declared_adapter_id`` is not the matrix adapter for the class;
    * the ``declared_intent_fields`` are not exactly the matrix intent contract.
    """

    if not isinstance(work_package, dict):
        raise ValueError("component work_package is required")
    declared_class = work_package.get("component_effect_class")
    matrix_row = (
        AIML_COMPONENT_EFFECT_CLASS_MATRIX.get(str(declared_class))
        if declared_class is not None
        else None
    )
    if matrix_row is None:
        # NONE/缺失/未知類:若其 owned paths / direct interfaces 碰到任一 component
        # 面,即為「effectful 面偽裝成 source-only」的繞過 → fail-closed raise。
        touched = _component_surfaces_touched(
            work_package.get("owned_path_manifest"),
            work_package.get("direct_interfaces"),
        )
        if touched:
            raise ValueError(
                "component work-package touches effectful component surface(s) "
                f"{sorted(touched)} but declares component_effect_class="
                f"{declared_class!r}; an effectful class cannot be source-only"
            )
        raise ValueError(
            f"unsupported component_effect_class: {declared_class!r}"
        )
    declared_adapter = work_package.get("declared_adapter_id")
    if declared_adapter != matrix_row["adapter_id"]:
        raise ValueError(
            f"declared_adapter_id {declared_adapter!r} is not the admitted adapter "
            f"for {declared_class}"
        )
    declared_fields = work_package.get("declared_intent_fields")
    if not isinstance(declared_fields, list) or sorted(declared_fields) != sorted(
        matrix_row["required_intent_fields"]
    ):
        raise ValueError(
            f"declared_intent_fields do not match the exact {declared_class} "
            "intent contract"
        )
    required_effects = [{
        "effect_class": declared_class,
        "status": "REQUIRED_PENDING",
        "adapter_id": matrix_row["adapter_id"],
        "actor_node_id": matrix_row["actor_node_id"],
        "rollback_contract": matrix_row["recovery_contract"],
        "independent_postcheck_node_id": matrix_row["independent_postcheck_node_id"],
        "required_intent_fields": list(matrix_row["required_intent_fields"]),
        "adapter_binding_status": matrix_row["adapter_binding_status"],
    }]
    classification: dict[str, Any] = {
        "schema_version": "aiml_component_effect_classification_v1",
        "classification_id": "sha256:" + "0" * 64,
        "component_work_package_id": work_package.get("component_work_package_id"),
        "classified_inputs": json.loads(json.dumps(work_package)),
        "classifier_digest": aiml_component_effect_class_matrix_digest(),
        "required_effects": required_effects,
        "classified_at": classified_at,
        "self_digest": "sha256:" + "0" * 64,
    }
    classification["classification_id"] = _component_effect_class_identity_digest(
        classification
    )
    classification["self_digest"] = artifact_self_digest(classification)
    return classification


# --------------------------------------------------------------------------- #
# S2.4(WP4·W1)七類 install-source-seam component effect 的 v2 vocabulary/matrix +
# sibling 分類器。這是 S2.4 §4 要求的 typed 七類擁有權/allowlist 矩陣:每類 → 必綁的
# exact §4 ABI(adapter_id / actor / 獨立 postcheck / rollback 契約 / required intent
# 欄位)。此為「新增一版矩陣=資料編輯」,不是動 v1。此 v2 矩陣與其 digest 與 v1 component
# matrix、與 S0.3 的 aiml_effect_classifier_digest 全部獨立(sibling),故 v1 與 S0.3 都
# 保持 byte-frozen(見 §0 凍結約束)。recovery_contract 逐字綁 §4 rollback schema id;
# adapter_binding_status 為 v2 唯一綁定值 AUTHORITY_LOCKED_PRODUCTION_CAPABLE(可達的
# 契約強制 + authority-lock;可執行 host-driver ABI 屬後續 wave,絕不在此處隱含)。
# --------------------------------------------------------------------------- #
AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2: dict[str, dict[str, Any]] = {
    "HOST_CAPABILITY_PROBE": {
        "required_intent_fields": [
            "probe_scope", "transient_unit_property_digest", "host_cgroup_identity",
            "cleanup_budget", "expiry",
        ],
        "recovery_contract": "s2_4_capability_probe_rollback_v1",
        "adapter_id": "s2_4_capability_probe_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_capability_probe_actor",
        "independent_postcheck_node_id": "s2_4_capability_probe_postcheck_v1",
    },
    "HOST_IDENTITY_INSTALL": {
        "required_intent_fields": [
            "plan", "uid_gid_directory_manifest", "pre_state", "expiry",
        ],
        "recovery_contract": "s2_4_host_identity_rollback_v1",
        "adapter_id": "s2_4_host_identity_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_host_identity_actor",
        "independent_postcheck_node_id": "s2_4_host_identity_postcheck_v1",
    },
    "PG_ROLE_ACL_MIGRATION": {
        "required_intent_fields": [
            "plan", "topology", "acl_manifest", "pg_migration_permit",
            "admin_handle_descriptor", "pre_state", "expiry",
        ],
        "recovery_contract": "s2_4_pg_acl_rollback_v1",
        "adapter_id": "s2_4_pg_role_acl_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_pg_admin_actor",
        "independent_postcheck_node_id": "s2_4_pg_acl_postcheck_v1",
    },
    "CREDENTIAL_INSTALL": {
        "required_intent_fields": [
            "plan", "credential_name", "encrypted_blob_digest", "host_identity",
            "pre_state", "expiry",
        ],
        "recovery_contract": "s2_4_credential_rollback_v1",
        "adapter_id": "s2_4_credential_install_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_host_secret_actor",
        "independent_postcheck_node_id": "s2_4_credential_postcheck_v1",
    },
    "LEARNING_RUNTIME_PREPARE": {
        "required_intent_fields": [
            "prepare_core", "prepare_authorization", "staging_root_device_inode",
            "resource_budget", "expiry",
        ],
        "recovery_contract": "s2_4_prepare_rollback_v1",
        "adapter_id": "s2_4_prepare_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_prepare_actor",
        "independent_postcheck_node_id": "s2_4_prepare_postcheck_v1",
    },
    "LEARNING_RUNTIME": {
        "required_intent_fields": [
            "plan", "prepare_receipt", "base_app_launch_manifests_and_target_paths",
            "pre_state", "expiry",
        ],
        "recovery_contract": "s2_4_runtime_rollback_v1",
        "adapter_id": "s2_4_runtime_install_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_host_runtime_actor",
        "independent_postcheck_node_id": "s2_4_runtime_postcheck_v1",
    },
    "ENGINE_SCANNER": {
        "required_intent_fields": [
            "plan", "unit_policy_evidence_manifests", "inactive_post_state",
            "pre_state", "expiry",
        ],
        "recovery_contract": "s2_4_engine_scanner_rollback_v1",
        "adapter_id": "s2_4_engine_scanner_install_adapter_v1",
        "adapter_binding_status": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
        "actor_node_id": "s2_4_host_service_actor",
        "independent_postcheck_node_id": "s2_4_engine_scanner_postcheck_v1",
    },
}
# 與 v1 相同的四條 OPS/PM/獨立性契約旗標:「施加 effect 的 actor 不能是其唯一驗證者」。
AIML_COMPONENT_EFFECT_CLASS_V2_INVARIANTS = {
    "requires_ops_preflight": True,
    "requires_pm_operator_approved_intent": True,
    "requires_independent_ops_postcheck": True,
    "applier_is_not_sole_verifier": True,
}


def aiml_component_effect_class_matrix_v2_digest() -> str:
    """Identify the 7-class S2.4 v2 component-effect matrix, independent of v1/S0.3.

    Analogue of ``aiml_component_effect_class_matrix_digest`` but a **separate**
    digest so the v1 component matrix and the S0.3 classifier stay byte-frozen.
    """

    return canonical_digest({
        "component_effect_class_matrix": AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2,
        "class_invariants": AIML_COMPONENT_EFFECT_CLASS_V2_INVARIANTS,
    })


def _component_effect_surface_tokens_v2() -> frozenset[str]:
    # 任一 v2 component 的 adapter/actor/postcheck 節點 id 都是「碰到 effectful 面」的標記。
    tokens: set[str] = set()
    for row in AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2.values():
        tokens.add(row["adapter_id"])
        tokens.add(row["actor_node_id"])
        tokens.add(row["independent_postcheck_node_id"])
    return frozenset(tokens)


def _component_surfaces_touched_v2(
    owned_path_manifest: Any, direct_interfaces: Any
) -> set[str]:
    tokens = _component_effect_surface_tokens_v2()
    touched: set[str] = set()
    for collection in (owned_path_manifest, direct_interfaces):
        if isinstance(collection, list):
            for item in collection:
                if isinstance(item, str) and item in tokens:
                    touched.add(item)
    return touched


def classify_component_required_effects_v2(
    work_package: Any, *, classified_at: str
) -> dict[str, Any]:
    """Derive a v2 component's required effect from the v2 matrix; block source-only.

    Structural clone of ``classify_component_required_effects`` but resolving the
    exact ``adapter_id`` / ``actor_node_id`` / ``rollback_contract`` /
    ``independent_postcheck_node_id`` / ``required_intent_fields`` in
    ``AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2``; the caller cannot supply or
    downgrade them.  It **raises** (never emits a ``NONE`` classification) when:

    * ``component_effect_class`` is ``NONE``/omitted/unknown yet the
      ``owned_path_manifest``/``direct_interfaces`` intersect a v2 component surface;
    * the declared ``declared_adapter_id`` is not the matrix adapter for the class;
    * the ``declared_intent_fields`` are not exactly the matrix intent contract.
    """

    if not isinstance(work_package, dict):
        raise ValueError("component work_package is required")
    declared_class = work_package.get("component_effect_class")
    matrix_row = (
        AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2.get(str(declared_class))
        if declared_class is not None
        else None
    )
    if matrix_row is None:
        # NONE/缺失/未知類:若其 owned paths / direct interfaces 碰到任一 v2 component
        # 面,即為「effectful 面偽裝成 source-only」的繞過 → fail-closed raise。
        touched = _component_surfaces_touched_v2(
            work_package.get("owned_path_manifest"),
            work_package.get("direct_interfaces"),
        )
        if touched:
            raise ValueError(
                "component work-package touches effectful component surface(s) "
                f"{sorted(touched)} but declares component_effect_class="
                f"{declared_class!r}; an effectful class cannot be source-only"
            )
        raise ValueError(
            f"unsupported component_effect_class: {declared_class!r}"
        )
    declared_adapter = work_package.get("declared_adapter_id")
    if declared_adapter != matrix_row["adapter_id"]:
        raise ValueError(
            f"declared_adapter_id {declared_adapter!r} is not the admitted adapter "
            f"for {declared_class}"
        )
    declared_fields = work_package.get("declared_intent_fields")
    if not isinstance(declared_fields, list) or sorted(declared_fields) != sorted(
        matrix_row["required_intent_fields"]
    ):
        raise ValueError(
            f"declared_intent_fields do not match the exact {declared_class} "
            "intent contract"
        )
    required_effects = [{
        "effect_class": declared_class,
        "status": "REQUIRED_PENDING",
        "adapter_id": matrix_row["adapter_id"],
        "actor_node_id": matrix_row["actor_node_id"],
        "rollback_contract": matrix_row["recovery_contract"],
        "independent_postcheck_node_id": matrix_row["independent_postcheck_node_id"],
        "required_intent_fields": list(matrix_row["required_intent_fields"]),
        "adapter_binding_status": matrix_row["adapter_binding_status"],
    }]
    classification: dict[str, Any] = {
        "schema_version": "aiml_component_effect_classification_v2",
        "classification_id": "sha256:" + "0" * 64,
        "component_work_package_id": work_package.get("component_work_package_id"),
        "classified_inputs": json.loads(json.dumps(work_package)),
        "classifier_digest": aiml_component_effect_class_matrix_v2_digest(),
        "required_effects": required_effects,
        "classified_at": classified_at,
        "self_digest": "sha256:" + "0" * 64,
    }
    classification["classification_id"] = _component_effect_class_identity_digest(
        classification
    )
    classification["self_digest"] = artifact_self_digest(classification)
    return classification

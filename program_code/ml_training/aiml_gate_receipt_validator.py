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
    # S1.1(LR0A)disposable PG 唯讀身分 receipt——central-validator 委派登記。
    "pg_readonly_identity_receipt_v1": "pg_readonly_identity_receipt_v1.schema.json",
    # S1.2(LR0B)WORM 終端 sink 的 append intent/result + 獨立 readback ACK。
    "terminal_receipt_append_intent_v1": "terminal_receipt_append_intent_v1.schema.json",
    "terminal_receipt_append_result_v1": "terminal_receipt_append_result_v1.schema.json",
    "terminal_receipt_readback_ack_v1": "terminal_receipt_readback_ack_v1.schema.json",
    # S1.2(LR0B)七類 component effect 的 sibling 分類 artifact(不動 S0.3 分類)。
    "aiml_component_effect_classification_v1": "aiml_component_effect_classification_v1.schema.json",
    # S2.4(WP4·W1)——additive:七類 S2.4 install-seam component effect 的 v2 sibling 分類
    # artifact(不動 v1 component matrix/schema)。加這鍵純為 schema 查找,絕不進入
    # aiml_effect_classifier_digest() 的六個 S0.3 常量輸入(見 :46-48/§7.2),S0.3 分類身分不動;
    # 亦不改 PROGRAM_SCHEMA_PATHS 與 v1 component matrix/digest。中央閘依 exact schema_version
    # 分派並拒跨版本 digest;required_effects 由 AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2 再導出。
    "aiml_component_effect_classification_v2": "aiml_component_effect_classification_v2.schema.json",
    # S1.5(LR0B)每元件 deploy adapter 的 typed intent/result + 獨立 postcheck attestation
    # + effect-seams-ready rollup;central-validator 委派給 S1.5 module 的 self-validating 檢查。
    "component_effect_intent_v1": "component_effect_intent_v1.schema.json",
    "component_effect_result_v1": "component_effect_result_v1.schema.json",
    "component_effect_postcheck_attestation_v1": "component_effect_postcheck_attestation_v1.schema.json",
    "effect_seams_ready_receipt_v1": "effect_seams_ready_receipt_v1.schema.json",
    # S1 formal-closure Wave A(S1.6B)——additive:generalized landing attempt row、target-host
    # 選擇 receipt(中央閘只結構驗)、typed 探針 intent、與專屬 target-host effect result。加這些鍵
    # 純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的輸入(見 §7.2),S0.3 分類身分不動。
    "aiml_landing_session_attempt_v1": "aiml_landing_session_attempt_v1.schema.json",
    "learning_runtime_choice_receipt_target_host_v1": "learning_runtime_choice_receipt_target_host_v1.schema.json",
    "target_host_disposable_runtime_probe_intent_v1": "target_host_disposable_runtime_probe_intent_v1.schema.json",
    "target_host_effect_result_v1": "target_host_effect_result_v1.schema.json",
    # S2.2A(LR1)scoped source-compatibility receipt——中央閘結構驗 + 下方 identity 交叉檢查。
    "source_compatibility_receipt_v1": "source_compatibility_receipt_v1.schema.json",
    # S2.3(LR2)——additive:sealed-build 與 expected-identity receipt。加這兩鍵純為 schema
    # 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入(見 :46-48/§7.2),
    # S0.3 分類身分不動。中央閘只做離線結構/整合/身分綁定/新鮮度委派驗(委派給
    # agent_governance_sealed_build 的 SSOT validators);真 offline-install 證明留在既有綠燈
    # `learning-runtime-sealed-build` CI job。
    "sealed_build_receipt_v1": "sealed_build_receipt_v1.schema.json",
    "expected_identity_receipt_v1": "expected_identity_receipt_v1.schema.json",
    # S2.2A(LR1)v2 source-compatibility receipt——內嵌 learning_runtime_manifest_v2,
    # dependency_lock 由 scalar 升為 {spec_digest, lock_digest} 物件並併入 parquet_etl COMPUTE。
    "source_compatibility_receipt_v2": "source_compatibility_receipt_v2.schema.json",
    # S2.0(WP2)——additive:生產唯讀 PG observer-bootstrap 的 typed intent/result/獨立 postcheck/
    # rollback。加這四鍵純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量
    # 輸入(見 :46-48/§7.2),S0.3 分類身分不動。中央閘只做離線結構/整合/新鮮度委派驗(委派給
    # agent_governance_pg_observer_bootstrap 的 SSOT validators);production apply 在有 exact
    # operator SSHSIG 前恆 fail-closed(EXTERNAL_VERIFICATION_PENDING),真 apply 屬 S2.0 EFFECT session。
    "pg_observer_bootstrap_intent_v1": "pg_observer_bootstrap_intent_v1.schema.json",
    "pg_observer_bootstrap_result_v1": "pg_observer_bootstrap_result_v1.schema.json",
    "pg_observer_bootstrap_postcheck_v1": "pg_observer_bootstrap_postcheck_v1.schema.json",
    "pg_observer_bootstrap_rollback_v1": "pg_observer_bootstrap_rollback_v1.schema.json",
    # S2.1(WP3)——additive:ALR quiesce fence 的 typed intent/observation/result/rollback。加這四鍵
    # 純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入(見 :46-48/§7.2),
    # S0.3 分類身分不動。中央閘只做離線結構/整合/新鮮度委派驗(委派給 agent_governance_alr_quiesce_fence
    # 的 SSOT validators);production/live fence 在有 S2.0@EFFECT_DONE + exact operator SSHSIG 前恆
    # fail-closed(EXTERNAL_VERIFICATION_PENDING),真 fence 屬 S2.1 EFFECT session。
    "quiesce_intent_v1": "quiesce_intent_v1.schema.json",
    "quiesce_observation_v1": "quiesce_observation_v1.schema.json",
    "quiesce_result_v1": "quiesce_result_v1.schema.json",
    "quiesce_rollback_v1": "quiesce_rollback_v1.schema.json",
    # S2.4(WP4·W0)——additive:source-implementation admission receipt 與 per-wave exit
    # receipt。加這兩鍵純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量
    # 輸入(見 :46-48/§7.2),S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1 component matrix。
    # 中央閘「不」讓 caller 自證 status——委派給 derive_source_admission_status /
    # derive_wave_exit_status 由 repo 獨立再導出 ADMITTED/PASS(caller 帶 status/admitted/pass/done
    # 一律先拒);此為 source-seam 完整性再導出,通過「不」等於認證任何 runtime(九 authority 全 false)。
    "s2_4_source_admission_receipt_v1": "s2_4_source_admission_receipt_v1.schema.json",
    "s2_4_wave_exit_receipt_v1": "s2_4_wave_exit_receipt_v1.schema.json",
    # S2.4(WP4·W1·CP2a)——additive:capability-probe 家族(HOST_CAPABILITY_PROBE row,§4/§5.1)
    # 與 prepare 家族(LEARNING_RUNTIME_PREPARE row)的 PREPARE->sign->APPLY 契約 schema:unsigned
    # core(排除 id/authorization/self_digest,digest 導 id)、closed route-class intent、terminal
    # effect receipt、WAL journal、獨立 postcheck、per-row rollback,加 network_sandbox 能力 attestation
    # 與 prepared-install bundle(base/app/launch manifest 僅以 digest-string 綁,manifest schema 屬 W2)。
    # 加這 14 鍵純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入
    # (見 :46-48/§7.2),S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component matrix/digest。
    # 全為契約:無 schema 斷言 runtime/production PASS,九 authority 於 receipt 皆 const-false,
    # secret 一律以 digest/handle 綁,絕不含明文;真 driver/effect/routing 屬後續 CP3-CP6/W2-W6。
    "s2_4_capability_probe_core_v1": "s2_4_capability_probe_core_v1.schema.json",
    "s2_4_capability_probe_intent_v1": "s2_4_capability_probe_intent_v1.schema.json",
    "s2_4_capability_probe_effect_receipt_v1": "s2_4_capability_probe_effect_receipt_v1.schema.json",
    "s2_4_capability_probe_journal_v1": "s2_4_capability_probe_journal_v1.schema.json",
    "s2_4_capability_probe_postcheck_v1": "s2_4_capability_probe_postcheck_v1.schema.json",
    "s2_4_capability_probe_rollback_v1": "s2_4_capability_probe_rollback_v1.schema.json",
    "network_sandbox_capability_attestation_v1": "network_sandbox_capability_attestation_v1.schema.json",
    "s2_4_prepare_core_v1": "s2_4_prepare_core_v1.schema.json",
    "s2_4_prepare_intent_v1": "s2_4_prepare_intent_v1.schema.json",
    "s2_4_prepare_effect_receipt_v1": "s2_4_prepare_effect_receipt_v1.schema.json",
    "s2_4_prepare_journal_v1": "s2_4_prepare_journal_v1.schema.json",
    "s2_4_prepare_postcheck_v1": "s2_4_prepare_postcheck_v1.schema.json",
    "s2_4_prepare_rollback_v1": "s2_4_prepare_rollback_v1.schema.json",
    "s2_4_prepared_install_bundle_v1": "s2_4_prepared_install_bundle_v1.schema.json",
    # S2.4(WP4·W1·CP2b)——additive:install/APPLY 家族的聚合協調契約 schema:unsigned aggregate
    # plan-core(排除 plan_id/idempotency_key/authorization/self_digest,digest 導 plan_id;
    # idempotency_key=plan_id 屬導出值故移出 core 落於 plan 物件,與 probe/prepare core 排除其導出 id
    # 同構)、closed route-class install-plan、immutable install effect receipt(§10.2 ABI status 含
    # APPLIED_INACTIVE,內嵌兩 scoped probe receipt + prepare 結果/postcheck + 五 APPLY row 結果/postcheck
    # + 一逆向補償鏈 + 終端 journal)、APPLY WAL journal、聚合獨立 postcheck、逆向補償鏈 rollback、
    # per-step typed result;五 APPLY row(HOST_IDENTITY_INSTALL/PG_ROLE_ACL_MIGRATION/CREDENTIAL_INSTALL/
    # LEARNING_RUNTIME/ENGINE_SCANNER)的 typed intent/result/postcheck/rollback;四 profile SSHSIG
    # operator authorization、hash-chained replay ledger、signed HBA delta、attested pg-topology(僅載
    # 證據,derived_verdict 恆 const null=不自證判定)與 root-owned pg-topology runtime guard(dbname
    # 屬性化不凍結)。加這 16 鍵純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3
    # 常量輸入(見 :46-48/§7.2),S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component
    # matrix/digest。全為契約:無 schema 斷言 runtime/production PASS,九 authority 於 receipt/result 皆
    # const-false,secret 一律以 digest/handle/名稱綁(無明文);真 driver/routing/profile 常量/per-row
    # ABI 綁定屬後續 CP3-CP6/W2-W6。
    "s2_4_install_plan_core_v1": "s2_4_install_plan_core_v1.schema.json",
    "s2_4_install_plan_v1": "s2_4_install_plan_v1.schema.json",
    "s2_4_install_effect_receipt_v1": "s2_4_install_effect_receipt_v1.schema.json",
    "s2_4_install_journal_v1": "s2_4_install_journal_v1.schema.json",
    "s2_4_install_postcheck_v1": "s2_4_install_postcheck_v1.schema.json",
    "s2_4_install_rollback_v1": "s2_4_install_rollback_v1.schema.json",
    "s2_4_install_step_result_v1": "s2_4_install_step_result_v1.schema.json",
    "s2_4_component_effect_intent_v1": "s2_4_component_effect_intent_v1.schema.json",
    "s2_4_component_effect_result_v1": "s2_4_component_effect_result_v1.schema.json",
    "s2_4_component_effect_postcheck_v1": "s2_4_component_effect_postcheck_v1.schema.json",
    "s2_4_component_effect_rollback_v1": "s2_4_component_effect_rollback_v1.schema.json",
    "s2_4_operator_authorization_v1": "s2_4_operator_authorization_v1.schema.json",
    "s2_4_authorization_replay_ledger_v1": "s2_4_authorization_replay_ledger_v1.schema.json",
    "s2_4_pg_hba_delta_v1": "s2_4_pg_hba_delta_v1.schema.json",
    "pg_topology_attestation_v1": "pg_topology_attestation_v1.schema.json",
    "pg_topology_runtime_guard_v1": "pg_topology_runtime_guard_v1.schema.json",
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


def _now_text(now: str | datetime | None) -> str | None:
    # 委派給 adapter validator(其 now 契約為 str|None)前,把 now 正規化為字串。
    if isinstance(now, datetime):
        return now.isoformat()
    if isinstance(now, str):
        return now
    return None


# --------------------------------------------------------------------------- #
# S2.4 · WP4 · W0(W0b)source-admission / wave-exit 中央「再導出」機制。
#
# 契約鐵則:receipt 只帶 evidence,status「絕不」由 caller 宣告。derive_* 以 repo 內獨立重算
# 每一欄位——§1.2 effect-DAG 三投影、§9.1 四 trust pin、S2.0 driver-reachability seam、WP3
# system-level property(property 非 exact unit-name,PM §7#4)、frozen S0.3 classifier + v1
# component matrix——ADMITTED/PASS 由重算相符「導出」;caller 帶 status/admitted/pass/done 於
# derivation 前即拒(§10.5 #27)。此機制與 aiml_effect_classifier_digest() 的六個 S0.3 常量、
# PROGRAM_SCHEMA_PATHS、AIML_COMPONENT_EFFECT_CLASS_MATRIX 完全「只讀不改」,故分類身分保持
# byte-frozen(§0 凍結約束)。它證的是 source-seam 完整性,「不」認證任何 runtime——九 authority /
# production_apply_performed / running_attested 恆 false。
# --------------------------------------------------------------------------- #
_PROGRAM_EFFECT_DAG = "S2.0→S2.4→S2.5A→S2.1→S2.5B→S2.2B"
_THREE_HEAD_PROJECTION_PATHS = (
    "TODO.md",
    "docs/execution_plan/ai_ml_landing/PROGRESS.md",
    "docs/agents/ai-ml-landing-delivery-protocol.md",
)
# §1.2 的兩個 W0 predecessor merge(admission 的固定祖先);兩者皆須為 receipt.source_head 的
# 祖先(local-checkout 拓撲證,非 runtime)。PR#132 = effect-DAG 投影;PR#134 = WP3 system-unit 對齊。
_PREDECESSOR_HEADS = {
    "program_dag_projection_merge": "4915be30c4214f8a3d591b7f9259169cdb65c75b",
    "wp3_system_unit_merge": "e514f1e761ab9c1965a133f1f113e2e7ccd854df",
}
# §9.1 operator 信任根指紋(out-of-scope pin;W0 只再驗、絕不改 trusted-host 模組/測試/指紋)。
_OPERATOR_FINGERPRINT = "SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ"
_TRUSTED_HOST_MODULE_PATH = (
    "helper_scripts/maintenance_scripts/agent_governance_aiml_trusted_host.py"
)
_TRUSTED_HOST_TEST_PATH = "tests/structure/test_agent_governance_aiml_trusted_host.py"
_S2_0_ADAPTER_ID = "pg_observer_bootstrap_adapter_v1"
_S2_0_EXPECTED_REGISTRY_STATUS = "AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
# WP3 system-level PROPERTY:role / systemctl --user 缺席由 WP3 executable 常量 + allowlist 動態
# 再導出;database 則「不」硬編鏡像常量,改由消費端權威 DSN(alr_event_consumer._LOCAL_DSN_REQUIRED
# 的 dbname,§10.4 runtime-DB 不可變 + _validate_local_dsn 強制)於導出期再讀取——若消費端 DSN 漂移,
# admission 隨之失敗(T7)。見 _consumer_authoritative_database()。
_ALR_CONSUMER_MODULE_PATH = "program_code/ml_training/alr_event_consumer.py"
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}
# §4.1 W0 exported-ABI delta(wave-exit exported_abi_digest 綁定的固定投影)。
_W0_EXPORTED_ABI = {
    "s2_0_adapter_binding": "AUTHORITY_LOCKED_PRODUCTION_CAPABLE",
    "s2_0_production_success_status": "APPLIED",
    "s2_0_production_driver_protocol": "ObserverBootstrapProductionDriver",
    "source_admission": "s2_4_source_admission_receipt_v1(status=ADMITTED)",
    "wave_exit": "s2_4_wave_exit_receipt_v1(status=PASS)",
}
# §5 W0 owned-path allowlist(wave-exit owned_path_manifest_digest 綁定的固定投影)。
_W0_OWNED_PATHS = (
    ".codex/agent_registry_v1.json",
    "helper_scripts/maintenance_scripts/agent_governance_pg_observer_bootstrap.py",
    "program_code/ml_training/aiml_gate_receipt_validator.py",
    "program_code/ml_training/schemas/aiml_gate_receipts/pg_observer_bootstrap_result_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/s2_4_source_admission_receipt_v1.schema.json",
    "program_code/ml_training/schemas/aiml_gate_receipts/s2_4_wave_exit_receipt_v1.schema.json",
    "program_code/ml_training/tests/test_aiml_gate_receipt_validator.py",
    "tests/structure/test_agent_governance_pg_observer_bootstrap.py",
    "tests/structure/test_s2_4_w0_admission.py",
)
# §3.1 W0 負向測試清單:admission 的 negative_tests_pass 必須「重導出」等於本清單的正規
# digest,而非只通過形狀檢查(否則偽造 receipt 可帶任意 digest 仍導出 ADMITTED,verdict 便
# 暗示 W0 負向測試已驗,實則從未綁定)。此為 code-owned 常量——恰好列出
# tests/structure/test_s2_4_w0_admission.py 內每一支負向(reject_/tamper_)測試的確切函式名
# (舊 effect-chain / systemctl --user / 自證 status / 逐欄竄改拒絕),已排序去重。
_W0_NEGATIVE_TEST_MANIFEST = (
    "test_reject_old_effect_chain_if_reintroduced_into_a_projection",
    "test_reject_self_declared_admission_status",
    "test_reject_self_declared_wave_exit_status",
    "test_reject_wp3_systemctl_user_production_path_from_executable_constants",
    "test_tamper_component_classifier_v1_digest_breaks_admission",
    "test_tamper_driver_reachability_flag_breaks_admission",
    "test_tamper_frozen_classifier_digest_breaks_admission",
    "test_tamper_negative_tests_pass_breaks_admission",
    "test_tamper_non_ancestor_source_head_breaks_admission",
    "test_tamper_operator_fingerprint_breaks_admission",
    "test_tamper_predecessor_head_breaks_admission",
    "test_tamper_production_flag_true_breaks_admission",
    "test_tamper_projection_digest_breaks_admission",
    "test_tamper_trust_pin_breaks_admission",
)
_CALLER_STATUS_KEYS = ("admitted", "done", "pass", "status")


def w0_negative_test_manifest_digest() -> str:
    """W0 負向測試清單的正規 digest(admission negative_tests_pass 綁定的固定投影)。"""

    return canonical_digest(list(_W0_NEGATIVE_TEST_MANIFEST))


def git_blob_sha1(data: bytes) -> str:
    """Reproduce ``git hash-object`` (blob) so trust-pin blob ids re-hash offline."""

    hasher = hashlib.sha1()
    hasher.update(b"blob " + str(len(data)).encode("ascii") + b"\x00")
    hasher.update(data)
    return hasher.hexdigest()


def _git_is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    """Local-checkout ancestry proof(fail-closed)。只證 repo 拓撲,不是 runtime 認證。"""

    import subprocess

    if re.fullmatch(r"[0-9a-f]{40}", ancestor) is None or re.fullmatch(
        r"[0-9a-f]{7,40}", descendant
    ) is None:
        return False
    try:
        proc = subprocess.run(
            [
                "git", "-C", str(repo_root), "merge-base", "--is-ancestor",
                ancestor, descendant,
            ],
            capture_output=True,
            timeout=30,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _git_head(repo_root: Path) -> str | None:
    """回傳 repo_root 目前 checkout 的 HEAD 40-hex commit(fail-closed:git 錯誤回 None)。

    T2:admission 的 source_head 必須「等於」目前 checkout HEAD(而非只是兩固定 predecessor 的後代)。
    所有證據皆由目前 checkout 再導出,故若 receipt 宣稱某世代卻從另一世代導出 ADMITTED,即為漂移——
    綁定 HEAD 令 admission 與其真正再導出的樹一致。
    """

    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    head = proc.stdout.strip()
    return head if re.fullmatch(r"[0-9a-f]{40}", head) else None


def _consumer_authoritative_database(repo_root: Path = REPO_ROOT) -> str | None:
    """由消費端權威 DSN 常量(alr_event_consumer._LOCAL_DSN_REQUIRED['dbname'])再導出期望 database(T7)。

    以 AST 解析 module 源碼取常量(而非硬編鏡像字面量,亦不重匯入其龐大依賴鏈/循環 import),故若消費端
    的 authoritative DSN 漂移(dbname 改動或 _validate_local_dsn 契約變更),admission 的 database 再導出
    隨之改變、令帶舊 database 的 receipt 失敗。fail-closed:讀不到常量回 None。
    """

    import ast

    try:
        source = (repo_root / _ALR_CONSUMER_MODULE_PATH).read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, ValueError):
        return None
    for node in tree.body:
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
            continue
        if not any(
            isinstance(target, ast.Name) and target.id == "_LOCAL_DSN_REQUIRED"
            for target in node.targets
        ):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            if (
                isinstance(key, ast.Constant)
                and key.value == "dbname"
                and isinstance(value, ast.Constant)
                and isinstance(value.value, str)
            ):
                return value.value
    return None


def _read_three_head_texts(repo_root: Path) -> dict[str, str]:
    return {
        rel: (repo_root / rel).read_text(encoding="utf-8")
        for rel in _THREE_HEAD_PROJECTION_PATHS
    }


def _projection_effect_dag_errors(texts: dict[str, str]) -> list[str]:
    """Require the canonical NEW apply-order in every projection text(§10.5 #20)。

    一份把 canonical apply-order 換回舊鏈(``S2.1@EFFECT_DONE``-before-``S2.4``)的 projection
    會因 NEW 鏈缺席而被拒。刻意「不」以「舊鏈子串出現」判拒——真 PROGRESS.md changelog 會同時
    載明舊→新兩鏈作歷史,單以子串判會誤傷。
    """

    return [
        f"three_head_projection missing the canonical §1.2 effect DAG in {path}"
        for path, text in sorted(texts.items())
        if _PROGRAM_EFFECT_DAG not in text
    ]


def three_head_projection_digest(repo_root: Path = REPO_ROOT) -> str:
    """Canonical digest of the §1.2 effect-DAG over the projections that carry it.

    數值依「再讀」而變:缺任一投影 → present set 縮小 → digest 改變(且 derivation 另以
    :func:`_projection_effect_dag_errors` 明確報缺)。
    """

    texts = _read_three_head_texts(repo_root)
    present = sorted(rel for rel, text in texts.items() if _PROGRAM_EFFECT_DAG in text)
    return canonical_digest({
        "effect_dag": _PROGRAM_EFFECT_DAG,
        "present_projections": present,
    })


def w0_owned_path_diff_digest(repo_root: Path = REPO_ROOT) -> str:
    """W0 owned-path 內容投影 digest(wave-exit owned_path_diff_digest 綁定的再導出;T1)。

    對每個 W0 owned path 讀目前 checkout 的 blob sha256(缺檔記 None),故任一 owned 檔位元改動都會改變
    此值——arbitrary/empty 值無法通過 W0 完成閘。與 owned_path_manifest_digest 同套 canonical_digest 機制,
    只是綁「內容」而非「路徑集合」。此為 SOURCE-seam 內容綁定,非 runtime 認證。
    """

    projection: dict[str, str | None] = {}
    for rel in sorted(_W0_OWNED_PATHS):
        try:
            projection[rel] = "sha256:" + hashlib.sha256(
                (repo_root / rel).read_bytes()
            ).hexdigest()
        except OSError:
            projection[rel] = None
    return canonical_digest(projection)


def _trust_pin_errors(pins: Any, repo_root: Path) -> list[str]:
    if not isinstance(pins, dict):
        return ["admission trust_pin_digests must be an object"]
    try:
        module_bytes = (repo_root / _TRUSTED_HOST_MODULE_PATH).read_bytes()
        test_bytes = (repo_root / _TRUSTED_HOST_TEST_PATH).read_bytes()
    except OSError as error:
        return [f"admission trust-pin blobs unreadable: {error}"]
    expected = {
        "trusted_host_module_blob": git_blob_sha1(module_bytes),
        "trusted_host_module_sha256": "sha256:" + hashlib.sha256(module_bytes).hexdigest(),
        "independent_test_blob": git_blob_sha1(test_bytes),
        "independent_test_sha256": "sha256:" + hashlib.sha256(test_bytes).hexdigest(),
        "operator_fingerprint": _OPERATOR_FINGERPRINT,
    }
    errors = [
        f"admission trust pin {key} does not re-hash to the §9.1 trust root"
        for key, value in expected.items()
        if pins.get(key) != value
    ]
    # 交叉綁定:指紋必須真的釘在 trusted-host 模組源碼裡(而非只在 receipt 中自洽)。
    if _OPERATOR_FINGERPRINT not in module_bytes.decode("utf-8", "replace"):
        errors.append("admission operator_fingerprint is not pinned in the trusted-host module source")
    return errors


# T4 behavioral probe:合成 production intent 的固定自洽時鐘/來源(刻意「不」用牆鐘/真 HEAD——探針
# 只驗 reachable 閘的執行,非新鮮度;自洽 now==created_at 落在 TTL 內故非 time-bomb;source_head 為合成
# 40-hex,與真 repo 無關)。target_host="trade-core" 已知通過 step 2(非 Mac/dev/loopback 標記)。
_S2_0_PROBE_CLOCK = "2026-01-01T00:00:00+00:00"
_S2_0_PROBE_SOURCE_HEAD = "0" * 40


def _unconditional_production_pending_removed(observer: Any) -> bool:
    """行為+結構雙證 S2.0 生產閘為 reachable-but-authority-locked(取代 signature-only 檢查;T4)。

    Codex 指出:僅憑 ``driver`` 參數存在於簽章來導出此旗標,會被「保留參數卻重引入無條件 pending
    return」的回歸繞過。故改為:
      (a) BEHAVIORAL——以 ``driver=None`` + 合成 VALID production intent + 無 operator SSHSIG 實跑
          ``apply_observer_bootstrap``:reachable §6 閘真執行過 step 2/2.5 並抵達 step 3,回 typed
          ``EXTERNAL_VERIFICATION_PENDING``(``AUTHORIZATION_REJECTED`` class)、``production_apply_performed``
          恆 false、零變更(driver=None 從不 mutate;離線無法偽造 operator SSHSIG,故止於 step 3——這正是
          honesty boundary)。若閘被改成 pre-step-2 的無條件 pending,reason 便不再是 AUTHORIZATION_REJECTED
          → (a) 失敗。
      (b) STRUCTURAL——靜態確認 module 源碼帶 step 5 的 ``if driver is None:`` reachable 分支且回具體
          「reachable but authority-locked: no host production driver」pending。step 5 需先過 step 3
          (真 SSHSIG),離線不可達,故此步以「gate 結構」靜態兌現(fix 明允的 fallback)。
    兩者皆成立才回 True;任一例外一律 fail-closed 回 False。
    """

    try:
        intent = observer.build_pg_observer_bootstrap_intent(
            target_class="production",
            target_host="trade-core",
            database="openclaw",
            observer_role="aiml_observer_ro",
            observed_schema="learning",
            observed_relations=["alr_consumer_events"],
            socket_dir="/var/run/postgresql",
            auth_mapping="pg_hba_ident_local",
            applier_node_id="observer_apply_actor",
            postcheck_node_id="observer_ops_postcheck",
            created_at=_S2_0_PROBE_CLOCK,
            ttl_seconds=900,
            source_head=_S2_0_PROBE_SOURCE_HEAD,
        )
        result = observer.apply_observer_bootstrap(
            intent,
            None,
            None,
            now=_S2_0_PROBE_CLOCK,
            source_head=_S2_0_PROBE_SOURCE_HEAD,
            driver=None,
        )
    except Exception:  # noqa: BLE001 - 探針任何逸出 = fail-closed 未證
        return False
    if not isinstance(result, dict):
        return False
    boundary = result.get("boundary") or {}
    behavioral_ok = (
        result.get("status") == "EXTERNAL_VERIFICATION_PENDING"
        and boundary.get("production_apply_performed") is False
        and "AUTHORIZATION_REJECTED" in str(result.get("failure_reason"))
    )
    try:
        module_source = Path(observer.__file__).read_text(encoding="utf-8")
    except (OSError, TypeError, ValueError):
        return False
    structural_ok = (
        "if driver is None:" in module_source
        and "reachable but authority-locked: no host production driver" in module_source
    )
    return bool(behavioral_ok and structural_ok)


def _s2_0_reachability_errors(proof: Any, repo_root: Path) -> list[str]:
    if not isinstance(proof, dict):
        return ["admission s2_0_driver_reachability_proof must be an object"]
    errors: list[str] = []
    registry_status: Any = None
    try:
        registry = json.loads(
            (repo_root / ".codex" / "agent_registry_v1.json").read_text(encoding="utf-8")
        )
        registry_status = (
            registry.get("effect_adapters", {})
            .get(_S2_0_ADAPTER_ID, {})
            .get("status")
        )
    except (OSError, json.JSONDecodeError) as error:
        errors.append(f"admission S2.0 registry adapter unreadable: {error}")

    import agent_governance_pg_observer_bootstrap as _observer

    expected = {
        "adapter_id": _S2_0_ADAPTER_ID,
        "registry_status": registry_status,
        # T4:行為+結構探針(非僅簽章)證 reachable §6 閘真執行且 driver-None 分支 authority-locked。
        "unconditional_production_pending_removed": _unconditional_production_pending_removed(
            _observer
        ),
        "driver_protocol_present": hasattr(_observer, "ObserverBootstrapProductionDriver"),
        "production_success_status": "APPLIED"
        if "APPLIED" in _observer.RESULT_STATUSES
        else None,
    }
    if registry_status != _S2_0_EXPECTED_REGISTRY_STATUS:
        errors.append(
            "admission S2.0 adapter registry_status is not AUTHORITY_LOCKED_PRODUCTION_CAPABLE"
        )
    errors.extend(
        f"admission s2_0_driver_reachability_proof.{key} does not re-derive"
        for key, value in expected.items()
        if proof.get(key) != value
    )
    return errors


def _wp3_system_unit_property_errors(proof: Any, repo_root: Path = REPO_ROOT) -> list[str]:
    if not isinstance(proof, dict):
        return ["admission wp3_system_unit_alignment_proof must be an object"]
    import agent_governance_alr_quiesce_inventory as _inventory

    systemd_is_system_level = _inventory.SYSTEMD == "/usr/bin/systemctl"
    try:
        # executable 再導出:allowlist 對任何 ``--user`` 形一律拒(§8.3/PR#134 system-level 語意)。
        _inventory._assert_allowlisted_systemctl(
            [_inventory.SYSTEMD, "--user", "show", _inventory.UNIT_NAME]
        )
    except _inventory.QuiesceHostReadError:
        # T5:只有 allowlist 的「預期拒絕型」例外才算 --user 形被擋下(system-level 語意成立)。
        user_form_rejected = True
    except Exception as error:  # noqa: BLE001
        # T5:任何「非預期」例外(如回歸引入的 TypeError/AttributeError)不得被誤讀為「--user 被拒」的
        # 證據——否則壞掉的 allowlist 會偽證 system-level property。fail-closed:直接記非導出 reason。
        return [
            "admission wp3_system_unit_alignment_proof --user allowlist probe raised an "
            f"unexpected (non-allowlist) error: {error!r}"
        ]
    else:
        # allowlist 竟接受 ``--user`` 形 → 非系統級語意 → user_form_rejected=False(下方 property 導出失敗)。
        user_form_rejected = False
    systemctl_user_absent = systemd_is_system_level and user_form_rejected
    # T7:database 由消費端權威 DSN 常量再導出(非硬編鏡像);讀不到即 fail-closed。
    expected_database = _consumer_authoritative_database(repo_root)
    if expected_database is None:
        return [
            "admission wp3_system_unit_alignment_proof.database cannot be re-derived from the ALR "
            "consumer authoritative DSN (_LOCAL_DSN_REQUIRED)"
        ]
    # property 非 exact unit-name:刻意「不」綁 UNIT_NAME(§7#4 unit-name 分歧 defer 至 W2)。
    expected = {
        "lifecycle_owner": "host_system_manager" if systemctl_user_absent else "unknown",
        "systemctl_user_absent": systemctl_user_absent,
        "role": _inventory.ALR_CONNECTION_ROLE,
        "database": expected_database,
    }
    return [
        f"admission wp3_system_unit_alignment_proof.{key} does not re-derive the WP3 system-level property"
        for key, value in expected.items()
        if proof.get(key) != value
    ]


def derive_source_admission_status(
    receipt: Any,
    *,
    repo_root: Path = REPO_ROOT,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """Independently re-derive the S2.4/WP4/W0 source-admission status (§3.1).

    回傳 ``{"status": "ADMITTED"|"NOT_ADMITTED", "reasons": [...]}``。每一欄位皆由 ``repo_root``
    重算並與 receipt 比對;全部相符且九 authority 全 false 才 ADMITTED,否則回 typed 非-ADMITTED
    reason list。caller 帶 status/admitted/pass/done 於 derivation 前即拒(§10.5 #27)。``now``
    刻意不作 wall-clock 新鮮度窗(source-admission 為 build-identity 證據,無 timestamp 欄位——
    以 wall-clock 判窗會變 time-bomb;真新鮮度由 wave/closure lane 綁 source_head 拓撲保證)。
    """

    if not isinstance(receipt, dict):
        return {"status": "NOT_ADMITTED", "reasons": ["admission receipt must be an object"]}
    declared = sorted(key for key in _CALLER_STATUS_KEYS if key in receipt)
    if declared:
        return {
            "status": "NOT_ADMITTED",
            "reasons": [
                "admission receipt must not self-declare status "
                f"({', '.join(declared)}); the central validator derives ADMITTED"
            ],
        }
    # T3:derive_source_admission_status 被 derive_wave_exit_status 「直接」呼叫(未經 validate_aiml_artifact),
    # 該路徑先前「不」施加 closed schema 的 additionalProperties:false。故在此(caller-status 預檢後、任何再導出前)
    # 自行跑一次 s2_4_source_admission_receipt_v1 的 closed-schema 子集驗——任一 forbidden property(self_digest 會把
    # 任意鍵一併雜湊,故不會被 self_digest 檢查抓到)即回 NOT_ADMITTED,杜絕帶額外欄位的 admission 導出 ADMITTED→PASS。
    try:
        _admission_schema = _load_schema("s2_4_source_admission_receipt_v1")
        _schema_errors = schema_subset_errors(receipt, _admission_schema, _admission_schema)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "NOT_ADMITTED",
            "reasons": [f"admission closed-schema is unloadable: {error}"],
        }
    if _schema_errors:
        return {"status": "NOT_ADMITTED", "reasons": _schema_errors}
    reasons: list[str] = []
    if receipt.get("schema_version") != "s2_4_source_admission_receipt_v1":
        reasons.append("admission schema_version is not s2_4_source_admission_receipt_v1")
    if receipt.get("work_package") != "WP4" or receipt.get("wave") != "W0":
        reasons.append("admission work_package/wave must be WP4/W0")
    if receipt.get("self_digest") != artifact_self_digest(receipt):
        reasons.append("admission self_digest does not bind the canonical receipt")
    source_head = receipt.get("source_head")
    if receipt.get("predecessor_heads") != _PREDECESSOR_HEADS:
        reasons.append("admission predecessor_heads differ from the exact §1.2 W0 lineage")
    if not (isinstance(source_head, str) and re.fullmatch(r"[0-9a-f]{40}", source_head)):
        reasons.append("admission source_head must be a 40-hex commit")
    else:
        # T2:source_head 必須「等於」目前 checkout HEAD——所有證據皆由此 checkout 再導出,若 receipt 宣稱
        # 另一世代卻從當前樹導 ADMITTED 即為漂移。predecessor 祖裔檢查仍保留(下方),兩者並存。
        head = _git_head(repo_root)
        if head is None:
            reasons.append(
                "admission source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
            )
        elif source_head != head:
            reasons.append(
                "admission source_head is not the current checkout HEAD "
                "(evidence is re-derived from HEAD; a claimed-generation mismatch is drift)"
            )
        for name, predecessor in _PREDECESSOR_HEADS.items():
            if not _git_is_ancestor(repo_root, predecessor, source_head):
                reasons.append(
                    f"admission predecessor {name} is not an ancestor of source_head"
                )
    try:
        texts = _read_three_head_texts(repo_root)
    except OSError as error:
        reasons.append(f"admission three-head projection unreadable: {error}")
    else:
        reasons.extend(_projection_effect_dag_errors(texts))
        if receipt.get("three_head_projection_digest") != three_head_projection_digest(
            repo_root
        ):
            reasons.append("admission three_head_projection_digest does not re-derive")
    reasons.extend(_trust_pin_errors(receipt.get("trust_pin_digests"), repo_root))
    reasons.extend(
        _s2_0_reachability_errors(receipt.get("s2_0_driver_reachability_proof"), repo_root)
    )
    reasons.extend(
        _wp3_system_unit_property_errors(
            receipt.get("wp3_system_unit_alignment_proof"), repo_root
        )
    )
    if receipt.get("frozen_classifier_digest") != aiml_effect_classifier_digest():
        reasons.append(
            "admission frozen_classifier_digest does not re-derive to the frozen S0.3 classifier"
        )
    if receipt.get("component_classifier_v1_digest") != aiml_component_effect_class_matrix_digest():
        reasons.append("admission component_classifier_v1_digest does not re-derive")
    if receipt.get("production_authority_flags") != _ALL_FALSE_PRODUCTION_FLAGS:
        reasons.append(
            "admission production_authority_flags must all be false (nine authorities / apply / running)"
        )
    # 綁定(而非只驗形狀):negative_tests_pass 必須重導出等於 code-owned W0 負向測試清單的
    # 正規 digest。任意形狀合法卻不符清單的 digest 一律拒——admission 因此真正背書 W0 負向測試
    # 身分,而非讓偽造 receipt 帶任意 digest 佯裝負向測試已驗。
    if receipt.get("negative_tests_pass") != w0_negative_test_manifest_digest():
        reasons.append(
            "admission negative_tests_pass does not re-derive to the W0 negative-test manifest"
        )
    return {
        "status": "ADMITTED" if not reasons else "NOT_ADMITTED",
        "reasons": reasons,
    }


_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


def _nonempty_digest_list_ok(value: Any) -> bool:
    # T1:非空 list 且每項皆為合法 sha256 digest(拒 empty/非 list/含畸形項)。
    return (
        isinstance(value, list)
        and len(value) > 0
        and all(isinstance(item, str) and _DIGEST_RE.fullmatch(item) for item in value)
    )


def _wave_exit_structural_errors(
    receipt: dict[str, Any], repo_root: Path = REPO_ROOT
) -> list[str]:
    """Self-contained wave-exit re-derivations(不需綁定 admission 物件即可在中央閘檢查)。"""

    reasons: list[str] = []
    if receipt.get("schema_version") != "s2_4_wave_exit_receipt_v1":
        reasons.append("wave-exit schema_version is not s2_4_wave_exit_receipt_v1")
    if receipt.get("self_digest") != artifact_self_digest(receipt):
        reasons.append("wave-exit self_digest does not bind the canonical receipt")
    if receipt.get("production_authority_flags") != _ALL_FALSE_PRODUCTION_FLAGS:
        reasons.append("wave-exit production_authority_flags must all be false")
    if receipt.get("wave") != "W0":
        # W0b 只導出 W0 wave-exit;W1+ 各 wave 於其自身 owned path 擴充 derivation。
        reasons.append("wave-exit derivation is only implemented for W0 in W0b")
        return reasons
    if receipt.get("predecessor_wave_receipt_digest") is not None:
        reasons.append(
            "W0 wave-exit has no predecessor wave (predecessor_wave_receipt_digest must be null)"
        )
    if receipt.get("exported_abi_digest") != canonical_digest(_W0_EXPORTED_ABI):
        reasons.append("wave-exit exported_abi_digest does not equal the W0 ABI delta")
    if receipt.get("owned_path_manifest_digest") != canonical_digest(sorted(_W0_OWNED_PATHS)):
        reasons.append("wave-exit owned_path_manifest_digest is not the exact W0 owned-path set")
    # T1(a):owned_path_diff_digest 綁定到 W0 owned-path 內容投影的再導出(同 owned_path_manifest_digest
    # 的 canonical_digest 機制),故 arbitrary/empty 值無法通過 W0 完成閘。
    if receipt.get("owned_path_diff_digest") != w0_owned_path_diff_digest(repo_root):
        reasons.append(
            "wave-exit owned_path_diff_digest does not re-derive the W0 owned-path content projection"
        )
    # T1(b):test/capture/review 三類證據必為「非空」的合法 digest list——empty/arbitrary 不得導出 PASS。
    # 誠實邊界:每一支 test/capture/review 的「PLATFORM-ATTESTED 綁定」屬下游 EFFECT/closure 關切(離線
    # 結構驗無法認證其真跑過);此處只擋「空/畸形證據仍導 PASS」的洞,不冒充已認證 runtime。
    for field in ("test_digests", "capture_digests", "review_fragment_digests"):
        if not _nonempty_digest_list_ok(receipt.get(field)):
            reasons.append(
                f"wave-exit {field} must be a non-empty list of sha256 digests "
                "(empty/arbitrary evidence must not derive PASS)"
            )
    return reasons


def derive_wave_exit_status(
    receipt: Any,
    *,
    repo_root: Path = REPO_ROOT,
    now: str | datetime | None = None,
    source_admission_receipt: Any = None,
) -> dict[str, Any]:
    """Independently re-derive the W0 wave-exit status (§3.2).

    回傳 ``{"status": "PASS"|"NOT_PASS", "reasons": [...]}``。W0 的 PASS 需:綁定的
    ``source_admission_receipt`` 再導出 ADMITTED 且其 self_digest == 本 receipt 綁定的
    ``source_admission_receipt_digest``、owned-path/ABI/flags 再導出相符、source_head 一致。
    caller 帶 status/pass/done 於 derivation 前即拒(§10.3/§10.5 #27)。

    邊界(必要非充分):中央閘 :func:`validate_aiml_artifact` 對 wave-exit 只做 STRUCTURAL-ONLY
    再導出(不綁 admission 物件),乾淨的 ``[]`` 結果「不」等於 W0 PASS——它未驗
    ``source_admission_receipt_digest`` 是否綁到一份真能再導出 ADMITTED 的 admission。真正的
    PASS 只能由「本函式帶 ``source_admission_receipt=<已導出 ADMITTED 的 admission>``」授予
    (鏡射 CLAUDE.md standalone-CLI / typed-authority 邊界:離線結構驗無法自證 PASS)。
    """

    if not isinstance(receipt, dict):
        return {"status": "NOT_PASS", "reasons": ["wave-exit receipt must be an object"]}
    declared = sorted(key for key in _CALLER_STATUS_KEYS if key in receipt)
    if declared:
        return {
            "status": "NOT_PASS",
            "reasons": [
                "wave-exit receipt must not self-declare status "
                f"({', '.join(declared)}); the central validator derives PASS"
            ],
        }
    # T3:此路徑亦不經 validate_aiml_artifact,故在此自行跑 wave-exit 的 closed-schema 子集驗
    # (additionalProperties:false + minItems),任一 forbidden property / 空證據 list 即回 NOT_PASS。
    try:
        _wave_schema = _load_schema("s2_4_wave_exit_receipt_v1")
        _schema_errors = schema_subset_errors(receipt, _wave_schema, _wave_schema)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {
            "status": "NOT_PASS",
            "reasons": [f"wave-exit closed-schema is unloadable: {error}"],
        }
    if _schema_errors:
        return {"status": "NOT_PASS", "reasons": _schema_errors}
    reasons = _wave_exit_structural_errors(receipt, repo_root)
    if receipt.get("wave") != "W0":
        return {"status": "NOT_PASS", "reasons": reasons}
    if source_admission_receipt is None:
        reasons.append(
            "W0 wave-exit requires the bound source_admission_receipt to re-derive ADMITTED"
        )
    else:
        admission = derive_source_admission_status(
            source_admission_receipt, repo_root=repo_root, now=now
        )
        # T6:綁定的 admission 若非 ADMITTED 或根本不是 dict(list/str/None),立即回 typed NOT_PASS——
        # 在任何 .get(...) 之前護欄,杜絕 non-dict 綁定物件觸發 AttributeError。
        if admission["status"] != "ADMITTED" or not isinstance(source_admission_receipt, dict):
            reasons.append(
                "wave-exit bound source_admission_receipt does not derive ADMITTED: "
                + "; ".join(admission["reasons"])
            )
            return {"status": "NOT_PASS", "reasons": reasons}
        if source_admission_receipt.get("self_digest") != receipt.get(
            "source_admission_receipt_digest"
        ):
            reasons.append(
                "wave-exit source_admission_receipt_digest does not bind the derived admission receipt"
            )
        if source_admission_receipt.get("source_head") != receipt.get("source_head"):
            reasons.append("wave-exit source_head differs from the bound admission receipt")
    return {
        "status": "PASS" if not reasons else "NOT_PASS",
        "reasons": reasons,
    }


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
    if schema_version == "aiml_landing_session_attempt_v1":
        # S1 formal-closure Wave A:generalized S1+ attempt。結構鏡射 session_attempt_v1 但
        # 走 sibling _aiml_landing_work_package_errors(不含 S0.3 const 等式),並新增 classifier-
        # derived required_effects / actor!=verifier / closure_binding 綁定。§13 C6:session_id 為裸
        # "S0" 或起始 "S0." 一律拒(鏡射 S0 session 家族全集 {"S0"} ∪ {"S0.*"})——寬鬆的 S1 schema
        # 不得用來重表任何 S0.x attempt(裸 "S0" 亦不得漏網)。
        scope_ref = artifact["scope_ref"]
        if artifact["session_id"] == "S0" or artifact["session_id"].startswith("S0."):
            errors.append(
                "aiml_landing_session_attempt_v1 cannot re-express an S0.x session "
                "(S0.* attempts use the sealed session_attempt_v1 with frozen const pins)"
            )
        if (
            scope_ref["kind"] == "PROGRAM"
            and scope_ref["landing_scope_id"] is not None
        ) or (
            scope_ref["kind"] == "LANDING_SCOPE"
            and scope_ref["landing_scope_id"] is None
        ):
            errors.append("landing session attempt scope_ref kind and landing_scope_id disagree")
        if artifact["attempt_id"] != session_attempt_identity_digest(artifact):
            errors.append("landing attempt_id does not bind the exact Session attempt identity")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("landing session attempt self_digest is invalid")
        expected_attempt_key = {
            "session_id": artifact["session_id"],
            "scope_ref": artifact["scope_ref"],
            "cohort_epoch": artifact["cohort_epoch"],
            "attempt": artifact["attempt"],
        }
        if artifact["attempt_key"] != expected_attempt_key:
            errors.append("landing session attempt_key differs from its canonical row fields")
        bootstrap = artifact["bootstrap_admission"]
        attempt_phase = artifact["attempt_phase"]
        if bootstrap["baseline_head"] != artifact["source"]["baseline_head"]:
            errors.append("landing session bootstrap baseline differs from source baseline")
        if attempt_phase == "SOURCE_BUILD" and (
            bootstrap["writer_lease_id"] != artifact["lease"]["lease_id"]
        ):
            errors.append("landing session bootstrap writer lease binding is invalid")
        errors.extend(_aiml_landing_work_package_errors(
            artifact["work_package"],
            attempt_phase=artifact["attempt_phase"],
            attempt_paths=artifact["path_manifest"],
        ))
        if artifact["path_manifest"] != sorted(set(artifact["path_manifest"])):
            errors.append("landing session attempt path_manifest must be sorted and unique")
        writer_paths = [
            path
            for node in artifact["dag_nodes"]
            for path in node["writer_paths"]
        ]
        writer_nodes = [
            node for node in artifact["dag_nodes"] if node["writer_paths"]
        ]
        if len(writer_nodes) > 2:
            errors.append("landing session attempt admits more than two writer nodes")
        if any(
            node["writer_paths"] != sorted(set(node["writer_paths"]))
            for node in writer_nodes
        ):
            errors.append("landing session attempt writer path ownership must be sorted and unique")
        if len(writer_paths) != len(set(writer_paths)):
            errors.append("landing session attempt writer path ownership overlaps")
        if not set(writer_paths).issubset(set(artifact["path_manifest"])):
            errors.append("landing session attempt writer paths exceed path_manifest")
        native = artifact["native_admission"]
        matching_native_nodes = [
            node
            for node in artifact["dag_nodes"]
            if node["node_id"] == native["node_id"]
            and node["node_class"] == native["node_class"]
            and node["permission"] == native["permission"]
        ]
        if len(matching_native_nodes) != 1:
            errors.append("landing session native admission does not match exactly one DAG node")
        if attempt_phase == "SOURCE_BUILD":
            try:
                acquired_at = _parse_timestamp(artifact["lease"]["acquired_at"])
                heartbeat_at = _parse_timestamp(artifact["lease"]["heartbeat_at"])
                expires_at = _parse_timestamp(artifact["lease"]["expires_at"])
                if not acquired_at <= heartbeat_at < expires_at:
                    errors.append("landing session attempt lease timestamps are out of order")
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
                    errors.append("expired landing session attempt must enter RECOVERY_REQUIRED")
            except (TypeError, ValueError) as error:
                errors.append(f"landing session attempt lease timestamp is invalid: {error}")
        elif attempt_phase == "POST_MERGE_FINALIZATION":
            if "lease" in artifact:
                errors.append("landing post-merge finalization attempt cannot hold a writer lease")
            if "writer_lease_id" in bootstrap:
                errors.append(
                    "landing post-merge finalization bootstrap cannot hold a writer lease id"
                )
            read_only_admission = artifact["read_only_admission"]
            if read_only_admission["read_only"] is not True:
                errors.append("landing post-merge finalization requires a read-only admission")
        # --- S1 classifier-derived effect binding + explicit closure binding ---
        adapter_id = artifact["adapter_id"]
        if artifact["actor_node"] == artifact["independent_postcheck_node"]:
            errors.append(
                "landing session attempt actor_node must differ from independent_postcheck_node"
            )
        if any(
            effect.get("adapter_id") != adapter_id
            for effect in artifact["required_effects"]
        ):
            errors.append(
                "landing session attempt required_effects adapter_id must equal the attempt adapter_id"
            )
        closure_binding = artifact["closure_binding"]
        for digest_field in ("closure_packet_digest", "effect_receipt_digest"):
            if not re.fullmatch(
                r"sha256:[0-9a-f]{64}", str(closure_binding.get(digest_field, ""))
            ):
                errors.append(
                    f"landing session attempt closure_binding {digest_field} is not a sha256 digest"
                )
        if closure_binding.get("effect_adapter_id") != adapter_id:
            errors.append(
                "landing session attempt closure_binding effect_adapter_id must equal the attempt adapter_id"
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
    if schema_version == "aiml_component_effect_classification_v1":
        # sibling 分類 artifact:重算 required_effects 並比對(拒偽造 required_effects
        # 或不符的 classifier_digest),結構等同 S0.3 分類分支但指向 sibling 分類器。
        if artifact["classification_id"] != _component_effect_class_identity_digest(
            artifact
        ):
            errors.append("AIML component effect classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML component effect classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_component_effect_class_matrix_digest():
            errors.append("AIML component effect classifier digest is not admitted")
        if artifact["component_work_package_id"] != artifact["classified_inputs"][
            "component_work_package_id"
        ]:
            errors.append("AIML component classification work-package id is not bound")
        try:
            expected = classify_component_required_effects(
                artifact["classified_inputs"],
                classified_at=artifact["classified_at"],
            )
        except ValueError as error:
            # NONE-block / adapter-substitution / 缺欄位 → fail-closed。
            errors.append(f"AIML component effect classification is not admitted: {error}")
        else:
            if artifact["required_effects"] != expected["required_effects"]:
                errors.append(
                    "AIML component required effects differ from classifier output"
                )
    if schema_version == "aiml_component_effect_classification_v2":
        # S2.4(WP4·W1)v2 sibling 分類 artifact:結構等同 v1 分支但指向 v2 分類器與 v2
        # 矩陣 digest。跨版本互拒為自動性——v1 artifact 帶 v1 digest 而此分支要 v2 digest,
        # 反之亦然;classifier_digest 不符即 fail-closed(下方 negative test 另補顯式反例)。
        if artifact["classification_id"] != _component_effect_class_identity_digest(
            artifact
        ):
            errors.append("AIML component effect v2 classification_id is invalid")
        if artifact["self_digest"] != artifact_self_digest(artifact):
            errors.append("AIML component effect v2 classification self_digest is invalid")
        if artifact["classifier_digest"] != aiml_component_effect_class_matrix_v2_digest():
            errors.append("AIML component effect v2 classifier digest is not admitted")
        if artifact["component_work_package_id"] != artifact["classified_inputs"][
            "component_work_package_id"
        ]:
            errors.append("AIML component v2 classification work-package id is not bound")
        try:
            expected = classify_component_required_effects_v2(
                artifact["classified_inputs"],
                classified_at=artifact["classified_at"],
            )
        except ValueError as error:
            # NONE-block / adapter-substitution / 缺欄位 → fail-closed。
            errors.append(
                f"AIML component effect v2 classification is not admitted: {error}"
            )
        else:
            if artifact["required_effects"] != expected["required_effects"]:
                errors.append(
                    "AIML component v2 required effects differ from classifier output"
                )
    if schema_version == "pg_readonly_identity_receipt_v1":
        # S1.1 central-validator wiring(CC review note D2):委派給 S1.1 validator 並
        # 強制傳 now;只接受 disposable-real/attested receipt,結構手搭的 stub 由 S1.1
        # validator 拒絕(它重算 source/schema sha256、要求 disposable_local、PASS 需真
        # 25006 等 runtime facts)。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "pg_readonly identity receipt requires now for freshness at the central gate"
            )
        else:
            import agent_governance_pg_readonly_identity as _pg_readonly
            errors.extend(
                _pg_readonly.validate_pg_readonly_identity_receipt(
                    artifact, now=now_text
                )
            )
    if schema_version in {
        "terminal_receipt_append_intent_v1",
        "terminal_receipt_append_result_v1",
        "terminal_receipt_readback_ack_v1",
    }:
        # S1.2 WORM sink:委派給 disposable adapter 的 self-validated 結構/整合/新鮮度
        # 檢查(standalone;跨 intent/result/ack 綁定由 adapter 測試以成對 artifact 驗證)。
        # 與 pg_readonly 分支同樣強制 now:陳舊 intent/result/ack 於中央閘 fail-closed。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "terminal receipt WORM artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_terminal_receipt_sink as _worm_sink
            if schema_version == "terminal_receipt_append_intent_v1":
                errors.extend(
                    _worm_sink.validate_terminal_receipt_append_intent(
                        artifact, now=now_text
                    )
                )
            elif schema_version == "terminal_receipt_append_result_v1":
                errors.extend(
                    _worm_sink.validate_terminal_receipt_append_result(
                        artifact, now=now_text
                    )
                )
            else:
                errors.extend(
                    _worm_sink.validate_terminal_receipt_readback_ack(
                        artifact, now=now_text
                    )
                )
                # P1-A:standalone(未配對 result)的 POSITIVE 獨立讀回 ACK,中央閘無配對
                # result 可綁定 verifier↔append actor,無法證明其獨立性 → fail-closed 拒絕。
                # 負向 ACK 或自陳 same_actor_violation=true 仍可 standalone 通過。
                if (
                    artifact.get("ack") is True
                    and artifact.get("same_actor_violation") is False
                ):
                    errors.append(
                        "readback ack independence cannot be verified without its "
                        "paired result"
                    )
    if schema_version in {
        "component_effect_intent_v1",
        "component_effect_result_v1",
        "component_effect_postcheck_attestation_v1",
        "effect_seams_ready_receipt_v1",
    }:
        # S1.5 每元件 deploy adapter:委派給 disposable module 的 self-validating 結構/整合/
        # 新鮮度檢查(standalone;跨 intent/result/attestation/rollup 綁定由 module 測試以成對
        # artifact 驗證)。與 pg_readonly / WORM 分支同樣強制 now:陳舊 artifact 於中央閘 fail-closed。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "component effect artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_component_effects as _component_effects
            if schema_version == "component_effect_intent_v1":
                errors.extend(
                    _component_effects.validate_component_effect_intent(artifact, now=now_text)
                )
            elif schema_version == "component_effect_result_v1":
                errors.extend(
                    _component_effects.validate_component_effect_result(artifact, now=now_text)
                )
            elif schema_version == "component_effect_postcheck_attestation_v1":
                errors.extend(
                    _component_effects.validate_postcheck_attestation(artifact, now=now_text)
                )
            else:
                errors.extend(
                    _component_effects.validate_effect_seams_ready_receipt(artifact, now=now_text)
                )
    if schema_version in {
        "pg_observer_bootstrap_intent_v1",
        "pg_observer_bootstrap_result_v1",
        "pg_observer_bootstrap_postcheck_v1",
        "pg_observer_bootstrap_rollback_v1",
    }:
        # S2.0(WP2)生產唯讀 PG observer-bootstrap SOURCE adapter:委派給 SSOT module 的自驗
        # 結構/整合/新鮮度檢查(standalone;跨 intent/result/postcheck/rollback 綁定由 module 測試
        # 以成對 artifact 驗證)。與 pg_readonly / WORM / component-effect 分支同樣強制 now:陳舊
        # artifact 於中央閘 fail-closed。
        #
        # ⚠ SOURCE-TRUTH 邊界(S2.0 EFFECT session 消費者請注意):此委派只證 receipt 的「內部自洽
        # + 結構 + 離線 SSHSIG 結構」(offline-structure 模式);validate_aiml_artifact 通過「不」等於
        # 證明真對生產 PG apply 過。production apply 現為 reachable 但 authority-locked:source/Mac/test
        # lane(driver=None)恆回 EXTERNAL_VERIFICATION_PENDING 零 mutation;真 APPLIED 僅由 S2.0 EFFECT
        # session 的真 host driver + platform-attested 證據簽發,且需 out-of-band 信任主機驗證(離線通過
        # 仍「不」證明真 apply 過)。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "observer bootstrap artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_pg_observer_bootstrap as _observer
            if schema_version == "pg_observer_bootstrap_intent_v1":
                errors.extend(_observer.validate_pg_observer_bootstrap_intent(artifact, now=now_text))
            elif schema_version == "pg_observer_bootstrap_result_v1":
                errors.extend(_observer.validate_pg_observer_bootstrap_result(artifact, now=now_text))
            elif schema_version == "pg_observer_bootstrap_postcheck_v1":
                errors.extend(_observer.validate_pg_observer_bootstrap_postcheck(artifact, now=now_text))
            else:
                errors.extend(_observer.validate_pg_observer_bootstrap_rollback(artifact, now=now_text))
    if schema_version in {
        "quiesce_intent_v1",
        "quiesce_observation_v1",
        "quiesce_result_v1",
        "quiesce_rollback_v1",
    }:
        # S2.1(WP3)ALR quiesce fence SOURCE adapter:委派給 SSOT module 的自驗結構/整合/新鮮度檢查
        # (standalone;跨 intent/observation/result/rollback 綁定由 module 測試以成對 artifact 驗證)。
        # 與 pg_observer / component-effect 分支同樣強制 now:陳舊 artifact 於中央閘 fail-closed。
        #
        # ⚠ SOURCE-TRUTH 邊界(S2.1 EFFECT session 消費者請注意):此委派只證 receipt 的「內部自洽 +
        # 結構 + 離線 SSHSIG 結構」;validate_aiml_artifact 通過「不」等於證明真對 live ALR 施加過 fence——
        # production/live fence 恆為 EXTERNAL_VERIFICATION_PENDING(fail-closed)直到 S2.0@EFFECT_DONE 與一張
        # platform-attested 的 out-of-band operator SSHSIG 存在,且 EFFECT fence 排在 S2.4/S2.5 之後。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "quiesce artifact requires now for freshness at the central gate"
            )
        else:
            import agent_governance_alr_quiesce_fence as _quiesce
            if schema_version == "quiesce_intent_v1":
                errors.extend(_quiesce.validate_quiesce_fence_intent(artifact, now=now_text))
            elif schema_version == "quiesce_observation_v1":
                errors.extend(_quiesce.validate_quiesce_observation(artifact, now=now_text))
            elif schema_version == "quiesce_result_v1":
                errors.extend(_quiesce.validate_quiesce_fence_result(artifact, now=now_text))
            else:
                errors.extend(_quiesce.validate_quiesce_rollback(artifact, now=now_text))
    if schema_version == "learning_runtime_choice_receipt_target_host_v1":
        # S1 formal-closure Wave A(S1.6B):把 target-host 選擇 receipt 加入中央 SCHEMA_FILES 委派
        # 登記,但中央離線閘只做「結構/整合/新鮮度」驗(require_target_host_attested=False)——CLAUDE.md
        # 明言 standalone CLI 無法認證 PASS。真「已背書」閘(EMBEDDED governed command_capture_v2)由
        # closure/trusted-host lane 以 require_target_host_attested=True 執行(見 target-host effect
        # sibling)。與 pg_readonly / WORM / component-effect 分支同樣強制 now:陳舊 receipt 於中央閘 fail-closed。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "target-host choice receipt requires now for freshness at the central gate"
            )
        else:
            import agent_governance_target_host_choice as _th_choice
            errors.extend(_th_choice.validate_target_host_choice_receipt(
                artifact, now=now_text, require_target_host_attested=False
            ))
    if schema_version == "target_host_effect_result_v1":
        # S1.6B 專屬 effect result(§13 C1):委派給 sibling module,對內嵌 choice receipt 以
        # require_target_host_attested=True 嚴格驗(§13 C4——這條 lane 的嚴格 attestation 是唯一
        # 真實執法)。中央閘無 closure baseline,故不傳 expected_source_head(結構+嵌入嚴格驗)。
        now_text = _now_text(now)
        if now_text is None:
            errors.append(
                "target-host effect result requires now for freshness at the central gate"
            )
        else:
            import agent_governance_target_host_effects as _th_effects
            errors.extend(_th_effects.validate_target_host_effect_result(
                artifact, now=now_text
            ))
    if schema_version == "target_host_disposable_runtime_probe_intent_v1":
        # S1.6B typed intent 為離線結構授權(SCHEMA_FILES 委派)。schema 無法比較兩欄位,故此處補上
        # schema description 已載明的 applier != independent verifier 不變量:applier_node_id 必須不同於
        # postcheck_node_id。其餘結構(const/pattern/enum/ttl 上限等)由上方 schema_subset_errors 強制。
        if artifact["applier_node_id"] == artifact["postcheck_node_id"]:
            errors.append(
                "target-host probe intent applier_node_id must differ from postcheck_node_id"
            )
    if schema_version == "github_repository_policy_attestation_v1":
        errors.extend(_github_policy_attestation_errors(artifact, now=now))
    if schema_version == "program_adoption_receipt_v1":
        errors.extend(_program_adoption_receipt_errors(artifact))
    if schema_version == "source_compatibility_receipt_v1":
        errors.extend(_source_compatibility_receipt_errors(artifact))
    if schema_version in {"sealed_build_receipt_v1", "expected_identity_receipt_v1"}:
        # S2.3(LR2)sealed-build / expected-identity 是 BUILD-IDENTITY / source 產物
        # (content-addressed、可重算、production_running_attested=false、observation_owner=
        # S2.5_LR6)——與 source_compatibility receipt 同類、非 effect-class。故中央閘只做離線
        # 結構/整合/const-false/S1.3·S1.4 ground-truth 身分綁定/self_digest 委派驗,「刻意不施加
        # wall-clock 新鮮度窗」:committed build 證據帶固定 30-min TTL,若以真牆鐘 now 判窗會過期成
        # time-bomb,任何以 wall-clock now 呼叫中央閘的 closure/CI/S2.4 消費者都會誤拒 committed 證據。
        # 真正的 recency 證明留在既有綠燈 `learning-runtime-sealed-build` CI job。故傳 now=None
        # (mirror S2.3 CLI + offline 測試對這兩類 receipt 的既有處置);SSOT 內部仍驗 ttl 範圍與
        # observed<expires 等結構性時間不變量,只是不做 wall-clock 窗判。亦刻意不傳 lock_path 與配對
        # sealed(不重跑 lock 封閉 re-derivation、不做 F2c 配對):同屬 CI job 的 offline-install 證明。
        #
        # ⚠ SOURCE-TRUTH 邊界(WP4/WP5 消費者請注意):此委派(及下方 source_compatibility_receipt_v2
        # 分支)只證 receipt 的「內部自洽 + 結構」(offline-structure 模式);validate_aiml_artifact
        # 通過「不」等於證明 receipt 與真 repo/真 lock 相符。build-identity receipt 的 source-truth
        # 綁定在別處:(i) launcher 端的 recompute-from-checkout(alr_event_consumer.
        # try_build_learning_runtime_manifest_v2)+ operator pin,與 (ii) `learning-runtime-sealed-build`
        # CI job 內 verify_lock_closure(lock_path=) 對真 lock 的 re-derivation。
        import agent_governance_sealed_build as _sealed_build
        if schema_version == "sealed_build_receipt_v1":
            errors.extend(
                _sealed_build.validate_sealed_build_receipt(artifact, now=None)
            )
        else:
            errors.extend(
                _sealed_build.validate_expected_identity_receipt(artifact, now=None)
            )
    if schema_version == "source_compatibility_receipt_v2":
        # v2 沿用「版本無關」的內層反偽造重算:_source_compatibility_receipt_errors 由 manifest
        # 自身 schema_version 驅動 self_digest 重算,且 training_contract.digest 綁定整個
        # components(含 dependency_lock 物件)→ 偽造內層 dependency_lock 而只重封外層 self_digest
        # 必被抓。另補 v2 專屬 dependency_lock 物件形狀檢查(spec/lock 兩子 digest)。
        # ⚠ 同上 SOURCE-TRUTH 邊界:此為 internal-consistency + structure 驗,非 source-truth——
        # dependency_lock 的 spec/lock 子 digest 是內嵌值,離線閘無法重算真檔;真檔綁定在 launcher
        # recompute-from-checkout 與 sealed-build CI job 的 verify_lock_closure。
        errors.extend(_source_compatibility_receipt_errors(artifact))
        errors.extend(_source_compatibility_receipt_v2_dependency_lock_errors(artifact))
    if schema_version == "s2_4_source_admission_receipt_v1":
        # S2.4(WP4·W0)source-admission:closed schema 已禁 caller status;此處委派給
        # derive_source_admission_status 由 repo 完整再導出(source-seam 自足)。非 ADMITTED →
        # 把 typed reasons 併入 errors。此再導出只證 source-seam 完整性,「不」認證任何 runtime。
        result = derive_source_admission_status(artifact, repo_root=REPO_ROOT, now=now)
        if result["status"] != "ADMITTED":
            errors.extend(result["reasons"])
    if schema_version == "s2_4_wave_exit_receipt_v1":
        # S2.4(WP4·W0)wave-exit:此中央閘分支為 STRUCTURAL-ONLY——無綁定 admission 對象,故只驗
        # 「自足」再導出(caller-status 拒 + self_digest + flags + W0 的 ABI/owned-path/predecessor-null),
        # 「不」驗 source_admission_receipt_digest 是否綁到一份真能再導出 ADMITTED 的 admission。
        # ⚠ 乾淨的 [] 結果「不」等於 W0 PASS:帶 bogus source_admission_receipt_digest 的 wave-exit
        # 仍會回 []。完整 PASS 必須由 derive_wave_exit_status(source_admission_receipt=<已導 ADMITTED>)
        # 授予——mirror CLAUDE.md standalone-CLI / typed-authority 邊界(離線結構驗無法自證 PASS)。
        declared = sorted(key for key in _CALLER_STATUS_KEYS if key in artifact)
        if declared:
            errors.append(
                "wave-exit receipt must not self-declare status "
                f"({', '.join(declared)}); the central validator derives PASS"
            )
        else:
            errors.extend(_wave_exit_structural_errors(artifact))
    return errors


def _source_compatibility_receipt_errors(artifact: dict[str, Any]) -> list[str]:
    """S2.2A(LR1):receipt 完整性 + 內層 digest 反偽造重算 + 身分綁定交叉檢查。

    內層 capture_contract.digest / training_contract.digest / 清單 self_digest 都必須由
    各自的 inputs / components 「重算」得出——直接沿用 SSOT 模塊的構造 helper(而非在此
    另寫一份),使 validator 與 module 不可能分歧;否則偽造內層 inputs/components 而只重封
    外層 self_digest 的 receipt 會誤過。
    """
    from ml_training.learning_runtime_manifest import (  # noqa: E402 (lazy:避免循環 import)
        capture_contract_digest as _lrm_capture_digest,
        manifest_self_digest as _lrm_self_digest,
        training_contract_digest as _lrm_training_digest,
    )

    errors: list[str] = []
    manifest = artifact["learning_runtime_manifest"]
    capture = manifest["capture_contract"]
    training = manifest["training_contract"]
    if artifact["self_digest"] != artifact_self_digest(artifact):
        errors.append("source-compatibility receipt self_digest is invalid")
    # 內層反偽造:capture/training digest 必須由自己的 inputs/components 重算得出。
    if capture["digest"] != _lrm_capture_digest(
        capture["inputs"], capture["snapshot_feature_schema_version"]
    ):
        errors.append("capture_contract.digest does not bind its inputs")
    if training["digest"] != _lrm_training_digest(training["components"]):
        errors.append("training_contract.digest does not bind its components")
    if manifest["self_digest"] != _lrm_self_digest(
        manifest["schema_version"],
        manifest["boundary"],
        capture["digest"],
        training["digest"],
    ):
        errors.append("learning_runtime_manifest self_digest is invalid")
    if artifact["learning_runtime_digest"] != manifest["self_digest"]:
        errors.append("learning_runtime_digest does not bind the manifest self_digest")
    if artifact["capture_contract_digest"] != capture["digest"]:
        errors.append("capture_contract_digest does not bind the manifest")
    if artifact["training_contract_digest"] != training["digest"]:
        errors.append("training_contract_digest does not bind the manifest")
    if artifact["migration_fingerprints"] != training["components"]["migration_fingerprints"]:
        errors.append("migration_fingerprints do not bind the manifest components")
    return errors


def _source_compatibility_receipt_v2_dependency_lock_errors(
    artifact: dict[str, Any],
) -> list[str]:
    """v2 專屬:training components 的 dependency_lock 必為 {spec_digest, lock_digest} 物件。

    子 digest 的 sha256 形狀由 v2 schema($defs/dependency_lock)在 schema_subset 階段強制;
    反偽造(不可竄改 spec/lock digest 而只重封外層)由上方版本無關的
    ``_source_compatibility_receipt_errors`` 經 training_contract.digest 綁定整個 components 保證。
    此處僅補一道 Python 層形狀斷言(schema 已保證,故為 defense-in-depth)。
    """
    manifest = artifact["learning_runtime_manifest"]
    components = manifest["training_contract"]["components"]
    dependency_lock = components.get("dependency_lock")
    if not isinstance(dependency_lock, dict) or set(dependency_lock) != {
        "spec_digest",
        "lock_digest",
    }:
        return [
            "source_compatibility_receipt_v2 dependency_lock must be a "
            "{spec_digest, lock_digest} object"
        ]
    return []

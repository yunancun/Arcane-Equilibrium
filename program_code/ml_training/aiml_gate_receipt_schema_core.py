"""AI/ML gate-receipt 中央 validator 的 schema/digest 核心下層(facade 2000 行治理拆分;WP4 S2.4)。

這是 ``aiml_gate_receipt_validator``(facade)的**下層**:canonical digest 基元、schema 註冊表
(SCHEMA_DIR/SCHEMA_FILES)、S0 program lineage 常量、GitHub secret-like 檢測、時間戳解析與
receipt dependency-graph 結構驗。facade 已超過 2000 行治理上限;把「純常量 + 純函式」逐位元組
搬入本模組,對外 ABI 不變——所有名稱仍經 facade re-export,消費者「只」匯入 facade。

**凍結約束不變。** 本模組為逐位元組等值搬移:PROGRAM_SCHEMA_PATHS 與所有 S0 常量值不動,
故 S0.3/v1/v2/§9.1/W0 各身分 digest 全數 byte-frozen(拆分前後重算相等)。

**循環相依處理。** 本模組 top-level 絕不匯入 facade 或任何 sibling 葉模組。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def resolve_facade():
    """以 sys.modules 為準解析「既載入」的 facade 模組(頂層名優先,dotted 形次之)。

    2000 行治理拆分後,facade(aiml_gate_receipt_validator)可能以頂層名或
    package 形(ml_training.aiml_gate_receipt_validator)被載入。leaf 內的延遲
    facade 讀取若硬編頂層名,在「只有 package 形已載入」的行程裡會惰性創建第二份
    完整 facade 拷貝,使針對 package 形模組物件的 monkeypatch 縫被繞過(E2 P1-1)。
    本解析器只回傳既載入的模組:頂層名存在取頂層(兩形並存時的確定性優先序);
    否則取排序後第一個 dotted 形;兩者皆無才回退為頂層 import(leaf 被單獨載入
    的邊緣情形,行為與拆分前一致)。
    """

    module = sys.modules.get("aiml_gate_receipt_validator")
    if module is not None:
        return module
    for name in sorted(sys.modules):
        if name.endswith(".aiml_gate_receipt_validator"):
            module = sys.modules[name]
            if module is not None:
                return module
    import aiml_gate_receipt_validator as module
    return module


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
    # S2.4(WP4·W2a)——additive:engine-scanner 的 closed PG ACL manifest(§2.1)。加這鍵純為
    # schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入(見 :46-48/§7.2),
    # S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component matrix/digest。中央閘只做
    # 結構驗 + self_digest 反偽造重算;與 static SQL inventory 的 exact-match 裁決委派給
    # agent_governance_s2_4_install.derive_engine_scanner_privilege_split(caller 不可自證)。
    "pg_acl_manifest_v1": "pg_acl_manifest_v1.schema.json",
    # S2.4(WP4·W2b·§8.1)——additive:checked-in runtime-closure allowlist 與由它產出的
    # application_bundle_manifest_v1(§8.1 第 3 內容身分 application_bundle_digest)。加這兩鍵
    # 純為 schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入
    # (見 :46-48/§7.2),S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component
    # matrix/digest。中央閘只做結構驗 + self_digest 反偽造重算;closure 與靜態 import 閉包的
    # 雙向 exact-match、effect-capable/broker/credential deny、committed-blob 溯源裁決全部
    # 委派給 agent_governance_s2_4_install(caller 不可自證);runtime 整樹重算屬
    # ml_training.alr_application_identity(兩側共用同一 canonical 文件構造點)。
    "application_bundle_runtime_closure_v1": (
        "application_bundle_runtime_closure_v1.schema.json"
    ),
    "application_bundle_manifest_v1": "application_bundle_manifest_v1.schema.json",
    # S2.4(WP4·W2c·§8.1 #2/#4)——additive:base_runtime_tree_manifest_v1(self_digest ==
    # base_runtime_tree_digest,PREPARE staging 樹身分)與 launch_bundle_manifest_v1
    # (self_digest == launch_bundle_digest,launches/<64-hex> 葉名契約)。加這兩鍵純為
    # schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入
    # (見 :46-48/§7.2),S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component
    # matrix/digest。中央閘只做結構驗 + self_digest 反偽造重算 + canonical 排序(委派
    # aiml_gate_receipt_wave_w2.w2_manifest_artifact_errors);真樹走訪/builder 溯源屬
    # agent_governance_s2_4_render(caller 提供樹;絕不觸生產路徑,不自證 runtime)。
    "base_runtime_tree_manifest_v1": "base_runtime_tree_manifest_v1.schema.json",
    "launch_bundle_manifest_v1": "launch_bundle_manifest_v1.schema.json",
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


# --------------------------------------------------------------------------- #
# W2 P1-5(review):owned-path 內容投影必須綁「被宣稱的那個 commit 的 blob」,而不是
# 工作樹當下的位元組。舊機制讀 working tree:任一 owned 檔有 staged/unstaged 改動時,
# receipt 記的是未變的 HEAD,投影 hash 的卻是髒位元組——驗證端 hash 同一棵髒樹於是照樣
# PASS,而該 commit 的乾淨 checkout 永遠重現不出那份 receipt。改由 ``git cat-file``
# 自 bound head 讀 blob:投影因此是該 commit 的函數,任何人 checkout 它都重算得出同值。
# fail-closed:git 不可用/commit 不存在/路徑不在該樹 → 該路徑記 None(投影變值 → 導出失敗)。
# --------------------------------------------------------------------------- #
def _git_stdout(repo_root: Path, arguments: list[str]) -> str | None:
    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), *arguments],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def resolve_commit_head(repo_root: Path, source_head: str | None = None) -> str | None:
    """把 ``source_head``(或 HEAD)解析為 40-hex commit;不可解析即 None(fail-closed)。"""

    revision = source_head if source_head is not None else "HEAD"
    if re.fullmatch(r"[0-9a-f]{7,40}", str(revision)) is None and revision != "HEAD":
        return None
    stdout = _git_stdout(repo_root, ["rev-parse", f"{revision}^{{commit}}"])
    if stdout is None:
        return None
    head = stdout.strip()
    return head if re.fullmatch(r"[0-9a-f]{40}", head) else None


def owned_path_blob_projection(
    repo_root: Path,
    paths: tuple[str, ...] | list[str],
    *,
    source_head: str | None = None,
) -> dict[str, str | None]:
    """{owned path: sha256 of its blob **at the bound commit**}(缺席/不可讀記 None)。

    以單一 ``git cat-file --batch`` 進程串流讀取(N 個路徑不再是 N 個子行程);
    ``<commit>:<path>`` 形的 revision 直接把路徑解析到那棵樹,故工作樹狀態完全不參與。
    """

    import subprocess

    ordered = sorted(paths)
    projection: dict[str, str | None] = {rel: None for rel in ordered}
    head = resolve_commit_head(repo_root, source_head)
    if head is None:
        return projection
    request = "".join(f"{head}:{rel}\n" for rel in ordered).encode("utf-8")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "--batch"],
            input=request,
            capture_output=True,
            timeout=180,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return projection
    if proc.returncode != 0:
        return projection
    stream = proc.stdout
    offset = 0
    for rel in ordered:
        newline = stream.find(b"\n", offset)
        if newline < 0:
            break
        header = stream[offset:newline].decode("utf-8", "replace").split(" ")
        offset = newline + 1
        if len(header) != 3 or header[1] != "blob":
            # "missing" / "ambiguous" / 非 blob(目錄、submodule)→ fail-closed 記 None。
            continue
        try:
            size = int(header[2])
        except ValueError:
            break
        payload = stream[offset : offset + size]
        offset += size + 1  # 每筆物件後接一個換行
        projection[rel] = "sha256:" + hashlib.sha256(payload).hexdigest()
    return projection


def owned_path_blob_projection_digest(
    repo_root: Path,
    paths: tuple[str, ...] | list[str],
    *,
    source_head: str | None = None,
) -> str:
    """owned-path commit-blob 投影的 canonical digest(W0/W1/W2 共用同一把尺)。"""

    return canonical_digest(
        owned_path_blob_projection(repo_root, paths, source_head=source_head)
    )


def owned_scope_worktree_delta(
    repo_root: Path,
    paths: tuple[str, ...] | list[str],
    *,
    source_head: str | None = None,
) -> list[str] | None:
    """owned scope 內 index/worktree 與 bound commit 的差異路徑(不可判定回 None)。

    P1-5 的可見性面:投影已綁 commit blob,故髒工作樹不再污染 digest;但「這份 receipt
    是從一棵髒工作樹發射的」本身是事實,必須可被看見而不是靜默。
    """

    ordered = sorted(paths)
    head = resolve_commit_head(repo_root, source_head)
    if head is None:
        return None
    stdout = _git_stdout(
        repo_root, ["status", "--porcelain", "-z", "--", *ordered]
    )
    if stdout is None:
        return None
    return sorted({
        record[3:] for record in stdout.split("\0") if len(record) > 3
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

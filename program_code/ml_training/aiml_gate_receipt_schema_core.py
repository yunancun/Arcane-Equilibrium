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
    # S2.4(WP4·W5·§9.2)——additive:dependency-freshness refresh attestation。§10.1 明列此
    # 路徑,§9.2 令它成為「過期 S2.2A/S2.3/S1.3 **source** 身分」唯一的補救途徑。加這鍵純為
    # schema 查找,絕不進入 aiml_effect_classifier_digest() 的六個 S0.3 常量輸入
    # (見 :46-48/§7.2),S0.3 分類身分不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component
    # matrix/digest。中央閘「不」讓 caller 自證 status——委派給
    # aiml_gate_receipt_s2_4_contracts.derive_dependency_refresh_status,由**驗證端自己**在
    # current_source_head 上重跑該 dependency 的 producer/語義再算並與原 receipt 比對
    # (caller 帶 status/admitted/pass/done 一律先拒)。§9.2 的硬線由同一支閘的封閉分類表
    # 執法:runtime/topology/prepare/auth 證據永不可 refresh-by-reference。
    "s2_4_dependency_refresh_attestation_v1": (
        "s2_4_dependency_refresh_attestation_v1.schema.json"
    ),
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


def commit_blob_bytes(
    repo_root: Path,
    paths: tuple[str, ...] | list[str],
    *,
    source_head: str | None = None,
) -> dict[str, bytes | None]:
    """{path: 該路徑在 bound commit 的 blob **位元組**}(缺席/不可讀記 None)。

    以單一 ``git cat-file --batch`` 進程串流讀取(N 個路徑不再是 N 個子行程);
    ``<commit>:<path>`` 形的 revision 直接把路徑解析到那棵樹,故工作樹狀態完全不參與。
    這是 P1-5 修正尺的**唯一**讀取原語:digest 投影與(W5 §9.2)commit-tree 物化都由它導出。
    """

    import subprocess

    ordered = sorted(paths)
    blobs: dict[str, bytes | None] = {rel: None for rel in ordered}
    head = resolve_commit_head(repo_root, source_head)
    if head is None:
        return blobs
    request = "".join(f"{head}:{rel}\n" for rel in ordered).encode("utf-8")
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "--batch"],
            input=request,
            capture_output=True,
            timeout=180,
        )
    except (OSError, ValueError, subprocess.SubprocessError):
        return blobs
    if proc.returncode != 0:
        return blobs
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
        blobs[rel] = stream[offset : offset + size]
        offset += size + 1  # 每筆物件後接一個換行
    return blobs


def owned_path_blob_projection(
    repo_root: Path,
    paths: tuple[str, ...] | list[str],
    *,
    source_head: str | None = None,
) -> dict[str, str | None]:
    """{owned path: sha256 of its blob **at the bound commit**}(缺席/不可讀記 None)。"""

    return {
        rel: (None if payload is None else "sha256:" + hashlib.sha256(payload).hexdigest())
        for rel, payload in commit_blob_bytes(
            repo_root, paths, source_head=source_head
        ).items()
    }


def materialize_commit_paths(
    repo_root: Path,
    paths: tuple[str, ...] | list[str],
    target: Path,
    *,
    source_head: str | None = None,
) -> list[str]:
    """把 bound commit 的 blob 逐一寫進 ``target`` 下的同名相對路徑;回傳**缺席**路徑清單。

    用途(W5 §9.2):讓 producer 在一棵「由該 commit 的 blob 組成」的樹上重跑,於是重算值
    是那個 commit 的函式,而不是工作樹當下位元組的函式。缺席清單非空即由呼叫端 fail-closed。
    """

    blobs = commit_blob_bytes(repo_root, paths, source_head=source_head)
    missing: list[str] = []
    for rel, payload in blobs.items():
        if payload is None:
            missing.append(rel)
            continue
        destination = Path(target) / rel
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    return sorted(missing)


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


# S2.4 §9.2:每一列所指的**那份 artifact** 到底是哪個 schema(code-owned;caller 的 evidence_class
# 字串只是標籤)。四個 permit 列都是同一支 §9.1 授權 artifact,差別在 profile/scope,那一層
# 由 _s2_4_operator_authorization_errors 執法;兩個 capability-probe 列是同一支終端 probe
# effect receipt,scope 差異在其內嵌的 network_sandbox_capability_attestation_v1。
S2_4_NEVER_REFRESHABLE_SCHEMAS: dict[str, tuple[str, ...]] = {
    "APPLY_AGGREGATE_AUTHORIZATION": ("s2_4_operator_authorization_v1",),
    "CAPABILITY_PROBE_AUTHORIZATION": ("s2_4_operator_authorization_v1",),
    "CAPABILITY_PROBE_RECEIPT_INSTALLED_UNIT": ("s2_4_capability_probe_effect_receipt_v1",),
    "CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX": ("s2_4_capability_probe_effect_receipt_v1",),
    "PG_MIGRATION_AUTHORIZATION": ("s2_4_operator_authorization_v1",),
    "PG_TOPOLOGY_ATTESTATION": ("pg_topology_attestation_v1",),
    "PREPARED_BUNDLE": ("s2_4_prepared_install_bundle_v1",),
    "PREPARE_AUTHORIZATION": ("s2_4_operator_authorization_v1",),
    "S2_0_EFFECT_RECEIPT": ("pg_observer_bootstrap_result_v1",),
}


class program_code_on_path:
    """只在需要 ``ml_training.*`` package 匯入的那一小段開窗,離開時只收回自己放的那筆。

    W5 review P2-E:``program_code`` 一旦在 import 期進 sys.path,engine-scanner 進程的
    top-level namespace 就多出 broker/exchange/dashboard 等套件;那必須是決策而非副作用
    (§10.1.1 #4)。本 context manager 把它縮成函式局部效果。
    """

    def __init__(self) -> None:
        self._entry = str(Path(__file__).resolve().parents[1])
        self._inserted = False

    def __enter__(self) -> None:
        if self._entry not in sys.path:
            sys.path.insert(0, self._entry)
            self._inserted = True

    def __exit__(self, *_exc: Any) -> None:
        if self._inserted and self._entry in sys.path:
            sys.path.remove(self._entry)
        self._inserted = False


# ── §9.2 語義主體(semantic subject)投影 —— W5 對抗審計 P1-A ─────────────────────
# 舊表把 S1.3 / S2.3 兩族的「語義 digest」定義成 (schema 檔雜湊, producer 檔雜湊),而後者
# 逐位元組等於 refresh 已經另欄綁住的 ``producer_module_digest``——
# ``agent_governance_sealed_build.source_sha256()`` 與
# ``agent_governance_identity_acl_contract.source_sha256()`` 都是 ``_file_sha256(SOURCE_PATH)``。
# 於是那兩族的「獨立復現 producer/semantic checks」實際上只證了「兩個檔案沒變」:被證的**主體**
# (sealed runtime 的內容身分、S1.3 的身分/ACL 投影、expected-component 身分、鏈到的 sealed
# receipt)一個都沒有進到比對裡,把 expected-identity receipt 的 ``runtime_content_digest`` 或
# ``sealed_build_digest`` 換掉,復現照樣 DEPENDENCY_REFRESH_ADMITTED。
#
# 下面兩支函式把每一族的語義主體改成「該 producer 真正產出的內容」,並成對提供:
#   :func:`recompute_dependency_semantic_subjects` —— 在 bound commit 物化樹上重跑 producer;
#   :func:`dependency_semantic_subject_values`    —— 從原 receipt 的**內容**投影出同形值
#                                                    (絕不是它自報的某個 digest 欄位)。
# 兩邊逐欄相等才算復現成功,故任一主體漂移都必須重新觀測而不能被刷新。
_S1_3_HOST_UID_KEYS = (
    "component", "uid_label", "non_root", "oci_socket_access", "dbus_authority",
    "least_privilege_caps", "production_uid_provisioned",
)
_S1_3_PG_ROLE_KEYS = (
    "component", "role_name", "privilege_class", "is_superuser",
    "forbidden_attrs_all_false", "is_reader", "writer_for_reader",
    "production_role_provisioned",
)
_S1_3_AUTH_KEYS = (
    "method", "local_only", "trust_from_anywhere", "wide_cidr", "ident_map",
    "production_hba_installed",
)
_S1_3_SOCKET_KEYS = (
    "component", "socket_dir_label", "world_readable", "world_writable",
    "owner_uid_label", "group_label", "production_socket_provisioned",
)
_S1_3_ROTATION_KEYS = ("secret_slot_target", "role_target", "rotation_order")
_S1_3_LOADING_KEYS = ("no_plaintext_ingress", "loader_kind")
_S1_3_ROLLBACK_KEYS = (
    "change_id", "change_kind", "pre_state_digest", "rollback_action", "recovery",
)
# S2.3 expected-identity 的 sealed 對象在 repo 內是一個**已提交**的固定路徑,故它是該族
# producer 的輸入之一,可由 bound commit 物化並重算(§9.2 的復現因此蓋得到 sealed_build_digest)。
S2_3_SEALED_BUILD_RECEIPT_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.3-sealed-build-receipt-v1.json"
)


def s1_3_identity_projection(contract_like: Any) -> dict[str, Any]:
    """S1.3 身分/ACL 契約的 **code-owned 不變骨架**(receipt 與 canonical contract 同形)。

    刻意排除「隨一次 disposable 觀測而變」的欄位——各 facet 的 ``evidence_class``、socket 的
    ``mode``/``mode_source``、rotation 的舊憑證拒絕證明與兩個 slot 指紋:它們是那一次觀測的
    產物,不是 S1.3 契約釘住的身分。剩下每一欄都由 ``canonical_identity_acl_contract`` 的
    code-owned 表決定,故可在 bound commit 上原封重算。
    """

    if not isinstance(contract_like, dict):
        return {}

    def _rows(key: str, fields: tuple[str, ...]) -> list[dict[str, Any]] | None:
        value = contract_like.get(key)
        if not isinstance(value, list):
            return None
        return [
            {field: row.get(field) for field in fields}
            for row in value
            if isinstance(row, dict)
        ]

    auth = contract_like.get("auth_mapping")
    secret = contract_like.get("secret_lifecycle")
    secret = secret if isinstance(secret, dict) else {}
    rotation = secret.get("rotation")
    loading = secret.get("protected_loading")
    return {
        "host_uid_topology": _rows("host_uid_topology", _S1_3_HOST_UID_KEYS),
        "pg_role_topology": _rows("pg_role_topology", _S1_3_PG_ROLE_KEYS),
        "auth_mapping": (
            {field: auth.get(field) for field in _S1_3_AUTH_KEYS}
            if isinstance(auth, dict) else None
        ),
        "socket_dir_acl": _rows("socket_dir_acl", _S1_3_SOCKET_KEYS),
        "secret_lifecycle": {
            "rotation": (
                {field: rotation.get(field) for field in _S1_3_ROTATION_KEYS}
                if isinstance(rotation, dict) else None
            ),
            "protected_loading": (
                {field: loading.get(field) for field in _S1_3_LOADING_KEYS}
                if isinstance(loading, dict) else None
            ),
            "plaintext_ingress": secret.get("plaintext_ingress"),
            "production_credential_rotated": secret.get("production_credential_rotated"),
        },
        "rollback": _rows("rollback", _S1_3_ROLLBACK_KEYS),
    }


def _s1_3_negative_kinds_digest(cases: Any) -> str | None:
    """S1.3 receipt 自帶的 negative-ACL 種類集合投影(over_grant_kind 的排序去重)。"""

    if not isinstance(cases, list):
        return None
    kinds = sorted({
        case.get("over_grant_kind")
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("over_grant_kind"), str)
    })
    return canonical_digest(kinds)


def dependency_semantic_subject_values(
    dependency_class: Any, receipt: Any
) -> dict[str, Any]:
    """從**原 receipt 自身的內容**投影出各語義主體(與重算端逐欄同形;缺項記 None)。"""

    if not isinstance(receipt, dict):
        return {}
    name = str(dependency_class)
    if name == "S2_2A_SOURCE_COMPATIBILITY":
        return {
            field: receipt.get(field)
            for field in (
                "capture_contract_digest", "learning_runtime_digest",
                "training_contract_digest",
            )
        }
    if name == "S1_3_IDENTITY_CONTRACT":
        return {
            "identity_projection_digest": canonical_digest(
                s1_3_identity_projection(receipt)
            ),
            "negative_acl_kinds_digest": _s1_3_negative_kinds_digest(
                receipt.get("negative_acl_cases")
            ),
            "schema_sha256": receipt.get("schema_sha256"),
            "source_sha256": receipt.get("source_sha256"),
        }
    if name == "S2_3_EXPECTED_IDENTITY":
        negatives = receipt.get("negative_acl_binding")
        rollback = receipt.get("rollback_binding")
        components = receipt.get("expected_component_identities")
        return {
            "expected_component_identities_digest": (
                canonical_digest(components) if isinstance(components, list) else None
            ),
            "rollback_binding_digest": (
                rollback.get("rollback_digest") if isinstance(rollback, dict) else None
            ),
            "runtime_content_digest": receipt.get("runtime_content_digest"),
            "s1_3_negatives_digest": (
                negatives.get("s1_3_negatives_digest")
                if isinstance(negatives, dict) else None
            ),
            "schema_sha256": receipt.get("schema_sha256"),
            "sealed_build_digest": receipt.get("sealed_build_digest"),
            "source_sha256": receipt.get("source_sha256"),
        }
    inventory = receipt.get("native_library_inventory")
    return {
        "closure_hash": receipt.get("closure_hash"),
        "native_library_inventory_digest": (
            canonical_digest(inventory) if isinstance(inventory, list) else None
        ),
        "runtime_content_digest": receipt.get("runtime_content_digest"),
        "schema_sha256": receipt.get("schema_sha256"),
        "source_sha256": receipt.get("source_sha256"),
    }


def _helper_scripts_on_path() -> None:
    """producer SSOT 都住在 ``helper_scripts/maintenance_scripts``;缺席時就地補上。"""

    helper = str(Path(__file__).resolve().parents[2] / "helper_scripts" / "maintenance_scripts")
    if helper not in sys.path:
        sys.path.insert(0, helper)


def _sealed_runtime_content_digest(sealed: Any, tree: Path) -> str:
    """由物化樹的 lock/spec 重算 sealed runtime 的內容身分(closure + native + launch + target)。"""

    closure = sealed.verify_lock_closure(
        tree / "requirements-ml.lock", tree / "requirements-ml.txt"
    )
    inventory = sealed.project_native_inventory(closure)
    return sealed.runtime_content_digest(
        closure_hash=closure["closure_hash"],
        isolated_launch_config=sealed._launch_block(),
        native_lib_inventory_digest=sealed._native_inventory_digest(inventory),
        python_version=sealed.TARGET_PYTHON_VERSION,
        target_platform=sealed.TARGET_PLATFORM,
    )


def recompute_dependency_semantic_subjects(
    dependency_class: str, original_schema_version: str, tree: Path, head: str
) -> dict[str, str]:
    """在**物化出來的 commit 樹**上跑各族 producer 的語義主體再算(anchor 全落在 ``tree``)。

    S2.3/S1.3 的 public helper 是 module-level anchored + ``lru_cache``
    (``source_sha256()`` 永遠 hash 它自己那顆 ``__file__``),故檔案雜湊改以各模組**自己的**
    ``_file_sha256`` 施於物化樹的同名路徑——同一支雜湊函式、不同 anchor,語義逐字相同而
    ``repo_root`` 真的生效(P1-B)。純常量投影(expected-component 身分、S1.3 骨架、negative
    種類、rollback 綁定)沒有檔案輸入,由 clean-tree 閘覆蓋其 producer 程式碼那一半(P1-A 殘留 i)。
    """

    _helper_scripts_on_path()
    if dependency_class == "S2_2A_SOURCE_COMPATIBILITY":
        with program_code_on_path():
            from ml_training.learning_runtime_manifest import (  # noqa: E402 (lazy)
                build_learning_runtime_manifest as _build_v1,
                build_learning_runtime_manifest_v2 as _build_v2,
            )

        builder = _build_v2 if original_schema_version.endswith("_v2") else _build_v1
        # repo_source_head 顯式傳入:物化樹沒有 .git,而 head 早已由 bound commit 決定。
        manifest = builder(tree, repo_source_head=head)
        return {
            "capture_contract_digest": manifest["capture_contract"]["digest"],
            "learning_runtime_digest": manifest["self_digest"],
            "training_contract_digest": manifest["training_contract"]["digest"],
        }
    if dependency_class == "S1_3_IDENTITY_CONTRACT":
        import agent_governance_identity_acl_contract as _s1_3  # noqa: E402 (lazy)

        contract = _s1_3.canonical_identity_acl_contract()
        return {
            "identity_projection_digest": canonical_digest(
                s1_3_identity_projection(contract)
            ),
            "negative_acl_kinds_digest": _s1_3_negative_kinds_digest(
                _s1_3.build_negative_acl_cases(contract)
            ),
            "schema_sha256": _s1_3._file_sha256(
                tree / _s1_3.SCHEMA_PATH.relative_to(_s1_3.REPO_ROOT)
            ),
            "source_sha256": _s1_3._file_sha256(
                tree / _s1_3.SOURCE_PATH.relative_to(_s1_3.REPO_ROOT)
            ),
        }
    import agent_governance_sealed_build as _sealed  # noqa: E402 (lazy)

    source_sha = _sealed._file_sha256(
        tree / _sealed.SOURCE_PATH.relative_to(_sealed.REPO_ROOT)
    )
    runtime_digest = _sealed_runtime_content_digest(_sealed, tree)
    if dependency_class == "S2_3_EXPECTED_IDENTITY":
        sealed_receipt = json.loads(
            (tree / S2_3_SEALED_BUILD_RECEIPT_REL).read_text(encoding="utf-8")
        )
        return {
            "expected_component_identities_digest": canonical_digest(
                _sealed.expected_component_identities()
            ),
            "rollback_binding_digest": _sealed._rollback_binding()["rollback_digest"],
            "runtime_content_digest": runtime_digest,
            "s1_3_negatives_digest": _sealed.s1_3_negatives_digest(),
            "schema_sha256": _sealed._file_sha256(
                tree / _sealed.EXPECTED_IDENTITY_SCHEMA_PATH.relative_to(_sealed.REPO_ROOT)
            ),
            "sealed_build_digest": _sealed.receipt_digest(sealed_receipt),
            "source_sha256": source_sha,
        }
    closure = _sealed.verify_lock_closure(
        tree / "requirements-ml.lock", tree / "requirements-ml.txt"
    )
    return {
        "closure_hash": closure["closure_hash"],
        "native_library_inventory_digest": _sealed._native_inventory_digest(
            _sealed.project_native_inventory(closure)
        ),
        "runtime_content_digest": runtime_digest,
        "schema_sha256": _sealed._file_sha256(
            tree / _sealed.SEALED_SCHEMA_PATH.relative_to(_sealed.REPO_ROOT)
        ),
        "source_sha256": source_sha,
    }


# ── §10.3 W5 誠實面:未關閉義務帳本(pure data;由 aiml_gate_receipt_wave_w5 引用)──────
# 2000 行治理拆分:W5 投影葉把這份純資料常量搬入本下層模組(逐位元組等值搬移,零語義變更),
# 與 S2_4_NEVER_REFRESHABLE_SCHEMAS 同屬「S2.4 code-owned 常量表」一類。單一真相來源仍是
# ``_W5_EXPORTED_ABI["remaining_owned_obligations"]``——它就是本清單物件本身。
S2_4_W5_REMAINING_OWNED_OBLIGATIONS: list[dict[str, Any]] = [
    {
        "obligation_id": "ENCRYPTED_BLOB_DIGEST_ORDERING",
        "typed_status": "OPEN_DESIGN_QUESTION",
        "owner_wave": "W6",
        "spec_refs": ["§5.1", "§7"],
        "statement": (
            "CREDENTIAL_INSTALL's signed intent must carry encrypted_blob_digest, but that "
            "digest is the hash of non-deterministic `systemd-creds encrypt` output. W5 "
            "confirms the question is unchanged: the fail-closed encrypt-then-compare "
            "binding still holds and no source change can decide whether the intent is "
            "signed before or after the encryption runs. It is an operator/W6 sequencing "
            "decision about a real host."
        ),
        "w5_provides": "nothing new; carried forward unchanged from W3/W4",
    },
    {
        "obligation_id": "OBSERVER_SPACE_PRE_STATE_DIGEST",
        "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
        "owner_wave": "W6B",
        "spec_refs": ["§5.2", "§5.4", "§6"],
        "statement": (
            "The plan-side digest space is defined and enforced (W4b). The observer side "
            "still needs a W6B postcheck driver contract requiring the verifier to return "
            "canonical_digest over the SAME code-owned per-row pre-state projection shape. "
            "W5 cannot close it: verifying that contract needs a real host observer, and no "
            "runtime evidence exists anywhere in S2.4."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "PRIOR_LINEAGE_ENTRY_IDENTITY",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§5.1", "§9.1"],
        "statement": (
            "APPLY requires a non-empty replay ledger but cannot verify WHICH permits the "
            "prior entries consumed, because probe_id/prepare_id are not carried in the "
            "install plan. Closing it needs either the W6B runner threading the probe/"
            "PREPARE authorization ids into the APPLY inputs, or a s2_4_install_plan_core_v1 "
            "field — a schema change §10.4 forbids the worker from choosing. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "PLAN_EXPIRY_OUTSIDE_SIGNED_CORE",
        "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
        "owner_wave": "W6B",
        "spec_refs": ["§9", "§9.2", "§10.4", "§10.5 #28"],
        "statement": (
            "s2_4_install_plan_v1.expires_at lives outside core, so it is not covered by the "
            "operator signature. The reachable half is closed (expired plan refused before "
            "any lock/mutation; every TTL bound derived from each artifact's own "
            "expires_at). Moving expires_at inside core is a s2_4_install_plan_core_v1 "
            "schema change §10.4 forbids. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "INSTALLED_UNIT_PROBE_CORE_BINDING",
        "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
        "owner_wave": "W6B",
        "spec_refs": ["§6", "§10.4", "§10.5 #36"],
        "statement": (
            "expected_installed_unit_probe_core_digest is optional at the API and MANDATORY "
            "for the W6 runner; omission is visible as "
            "UNVERIFIED_NO_EXPECTED_VALUE_SUPPLIED on every verdict. Closing it means the "
            "W6B runner always supplying it or adding a plan-core field. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "EFFECT_RECEIPT_RECONCILE_BINDING",
        "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
        "owner_wave": "W6B",
        "spec_refs": ["§5.2", "§10.4"],
        "statement": (
            "s2_4_install_effect_receipt_v1 has no field for the startup-reconcile verdict "
            "and the schema is additionalProperties:false. W4b binds all three signals into "
            "the durable evidence set beside the journal; a consumer holding only the "
            "receipt still cannot re-derive the reconcile verdict. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "STARTUP_RECONCILE_SURFACE_ABSENT",
        "typed_status": "OPEN_BY_DESIGN_W6_RUNNER_PRECONDITION",
        "owner_wave": "W6",
        "spec_refs": ["§5.2", "§10.5 #39"],
        "statement": (
            "A host driver not wrapped by JournalRoutedDriver has no durable journal "
            "surface, so reconcile_before_new_intent returns "
            "STARTUP_RECONCILE_SURFACE_ABSENT with admits_new_work=None. The W6 runner MUST "
            "inject a journal-routed driver into the probe and PREPARE entry points. "
            "Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "STARTUP_JOURNAL_PARENTS_MUST_PREEXIST",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§5.2"],
        "statement": (
            "On a fresh host the three §5.2 journal parents do not exist, so startup "
            "reconciliation returns RECOVERY_REQUIRED and nothing in S2.4 can start until "
            "an operator pre-creates .../s2_4, .../s2_4/probes and .../s2_4/prepared "
            "root-owned 0700. This is an OPERATOR PRECONDITION for the W6 runbook, not a "
            "defect to be fixed by giving the journal surface a mkdir capability. "
            "Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "RECEIPT_EMISSION_PENDING_IS_NOT_A_RECEIPT_RETRY",
        "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
        "owner_wave": "W6B",
        "spec_refs": ["§10.5 #8", "§10.5 #14"],
        "statement": (
            "A terminal, complete install can permanently have no receipt: the journal does "
            "not carry the row result/postcheck digests the receipt binds, so "
            "ALREADY_APPLIED_IDEMPOTENT cannot reconstruct it. Actually emitting the "
            "receipt on retry is an artifact-shape decision belonging to the W6B runner. "
            "Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "STRANDED_WAL_TEMP_FILES_ARE_REPORT_ONLY",
        "typed_status": "PARTIALLY_PROVIDED_BY_W4B",
        "owner_wave": "W6B",
        "spec_refs": ["§5.2"],
        "statement": (
            "The §5.2 startup enumeration matches, lists and names stranded WAL temp "
            "residue and blocks new work while it exists, but §5.2 forbids this surface "
            "from renaming or removing anything, so clearing it is an operator runbook "
            "step. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        # 對抗審計第二輪的更正:上一版把它由 W4 的 NOT_PROVIDED_BY_W4B 軟化成
        # PARTIALLY_PROVIDED_BY_W4B,而它自己的 statement 逐字寫著「BOTH halves W4
        # named are still open」。W5 沒有提供這兩半的任何一半,只是**記錄**了一條 W4 漏記
        # 的、更弱的 driver-clock 關係;那是 w5_provides 的內容,不是 typed_status 的。
        "obligation_id": "ATTESTATION_EXPIRY_AND_HOST_TIME_ARE_NOT_CROSS_CHECKED",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§9.1", "§10.2"],
        "statement": (
            "W5 reviewed this one line by line because it READS like a source fix. It is "
            "not, and W5's first draft of this correction was itself wrong and is recorded "
            "here rather than silently rewritten. BOTH halves W4 named are still open. "
            "(a) Nothing compares the OBSERVED moment against attestation_expires_at: "
            "derive_apply_attestation_status deliberately excludes the caller's now, so an "
            "attestation whose own expiry has passed still verifies as long as its SIGNED "
            "trusted_host_time sits inside both permit windows. (b) The attestation's "
            "SIGNED trusted_host_time is still never reconciled with the value "
            "driver.trusted_host_time() returned for the same transaction — verified by "
            "reading agent_governance_s2_4_install_evidence.derive_apply_attestation_status, "
            "which compares the signed time only against attestation_expires_at, the 900s "
            "attestation TTL and the two permit windows. What DOES exist, and what W4's "
            "statement omitted, is a DIFFERENT and weaker relation that W5 adds to the "
            "record: agent_governance_s2_4_install_driver._trusted_host_time_reasons "
            "cross-checks driver.trusted_host_time() against the observed moment under the "
            "§9.1 PERMIT_CLOCK_SKEW_SECONDS ceiling (regression: "
            "test_c18_the_trusted_host_time_is_cross_checked_against_the_observed_time). "
            "That bounds the DRIVER's clock, not the attestation's signed value. The "
            "residual is therefore smaller than W4 implied but non-zero: the signed "
            "trusted_host_time is still bounded indirectly, because it must fall inside two "
            "independently signed permit windows that are themselves capped at 900s. "
            "Closing either half needs a decision about WHICH clock is authoritative for "
            "the observed moment on a real host (§9.1 says the host's, and on a real host "
            "the two values come from the same clock); in a source lane where both are "
            "fixtures the question is unanswerable, and wiring the caller's now into the "
            "freshness derivation would REVERSE the W4b property that freshness comes only "
            "from the SIGNED trusted_host_time."
        ),
        "w5_provides": (
            "the line-verified confirmation that both halves are still open (W4's statement "
            "stands), the previously unrecorded driver-clock skew ceiling and its named "
            "regression, the observation that the two 900s permit windows bound the residual, "
            "and the explicit reason this is not a source change"
        ),
    },
    {
        # 對抗審計第二輪:上一版把這一條**整列刪掉**,理由寫在測試裡(「已由 W4b 在源碼線
        # 交付」)。W4 交出來的 typed_status 是 VERIFIER_PROVIDED_BY_W4B_ATTESTATION_PENDING
        # ——verifier 有了,`ATTESTATION_PENDING` 那一半(在真主機上**取得**一份簽章)仍是活的
        # 殘留,而殘留活著的義務不得因為它的前半已交付就被丟掉。
        "obligation_id": "ATTESTED_EVIDENCE_CLASS_VERIFIER",
        "typed_status": "VERIFIER_PROVIDED_BY_W4B_ATTESTATION_PENDING",
        "owner_wave": "W6B",
        "spec_refs": ["§6", "§9.1", "§10.2", "§10.5 #13", "§10.5 #14"],
        "statement": (
            "W4b delivered the VERIFIER: s2_4_install_apply_attestation_v1 with a distinct "
            "attestor identity and namespace over the same §9.1 trust root, a real "
            "signature verification, exact-plan binding, applier != verifier, row-results "
            "equality and freshness derived only from the SIGNED trusted_host_time. What "
            "remains open is unchanged and still live: OBTAINING a real attestation needs a "
            "trusted host holding the §9.1 private key, so on Mac/source/disposable lanes "
            "no attestation is produced and every driver terminates at "
            "SOURCE_SIMULATION_PASS with all nine authorities false. W5 adds no attestation "
            "and holds no key material, so the pending half is exactly as W4 left it. "
            "Carried rather than dropped: a row whose residual is live is not closed by its "
            "other half having been delivered."
        ),
        "w5_provides": (
            "nothing new; carried forward unchanged from W4 with its typed status intact "
            "after the previous W5 draft removed the row entirely"
        ),
    },
    {
        "obligation_id": "ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§9.1", "§10.2"],
        "statement": (
            "One physical Ed25519 key roots both the four operator permit profiles and the "
            "apply attestation. Domain separation is namespace-level and real; CUSTODY is "
            "not separated. The fix is a separate attestor keypair with its own pinned "
            "fingerprint, which is a W6 key-custody decision about a real host. W5 confirms "
            "no source change can establish it: the source lane has no key material at all."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "REPLAY_LEDGER_CONSUME_ONCE_IS_A_FILESYSTEM_PROPERTY",
        "typed_status": "OPEN_HONEST_BOUNDARY",
        "owner_wave": "W6B",
        "spec_refs": ["§9.1", "§10.5 #8"],
        "statement": (
            "Ledger rollback and forking are prevented by the root-owned 0700 parent, the "
            "0600 mode and the exclusive install lock, not cryptographically. Closing it "
            "needs a monotonic counter in trusted storage or an attestor-signed ledger "
            "head. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    {
        "obligation_id": "STARTUP_RECONCILE_LANE_PATHS",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§5.2"],
        "statement": (
            "Enumeration sees every non-terminal journal in the three parents, but the "
            "caller's paths still decide which lane receives the independent observation "
            "digest and per-lane ownership key. Closing that half means the W6B runner "
            "passing the probe_id/prepare_id-derived paths it already holds. Unchanged."
        ),
        "w5_provides": "nothing new; owner unchanged",
    },
    # ── W5 自審新增的四項 ────────────────────────────────────────────────────
    {
        "obligation_id": "DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "PM",
        "spec_refs": ["§3", "§10.4", "§11.3"],
        "statement": (
            "The §9.2 gate itself is now built and load-bearing (schema, central branch, "
            "verifier-side recomputation, builder, tests), so §11.2's 'complete source "
            "inventory' is no longer false and §10.5 #28's first half is PROVEN. What is "
            "NOT closed is the receipt binding: §3 requires the terminal "
            "s2_4_install_effect_receipt_v1 to reference 'source_admission_receipt, W0-W5 "
            "wave-chain and DEPENDENCY-REFRESH digests', and that closed "
            "additionalProperties:false schema has no field for them — a consumer holding "
            "only the install receipt cannot see which refreshes admitted the expired "
            "source identities. Adding the field is an exported-schema change §10.4 "
            "forbids the worker from choosing, exactly like PLAN_EXPIRY_OUTSIDE_SIGNED_CORE "
            "and EFFECT_RECEIPT_RECONCILE_BINDING. Correction (adversarial round 2): the "
            "previous wording of this row ended 'the refresh verdicts are reachable only "
            "through derive_source_dependency_admission_status at APPLY time', which was "
            "FALSE — nothing at APPLY time calls it. That sentence is retired and the "
            "measured fact now lives in its own row, "
            "SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE. What is true here is "
            "narrower: even once a call site exists, the terminal receipt still has nowhere "
            "to carry the refresh digests §3 names."
        ),
        "w5_provides": (
            "the complete §9.2 gate (four refreshable classes, nine never-refreshable "
            "classes, verifier-side reproduction, one-refresh rule) and the exact residual: "
            "the terminal receipt has nowhere to carry the refresh digests §3 names"
        ),
    },
    {
        "obligation_id": "DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE",
        "typed_status": "PARTIALLY_PROVIDED_BY_W5",
        "owner_wave": "W6",
        "spec_refs": ["§9.1", "§9.2"],
        "statement": (
            "§9.2 requires an INDEPENDENT replay. W5 makes two halves of that structural "
            "and one half declarative, and says which is which. STRUCTURAL: the semantic "
            "digests are recomputed BY THE VERIFIER from the BLOBS OF THE BOUND COMMIT — "
            "the producer input set is materialised out of git into a scratch tree and the "
            "producer is run there, so the working tree is not an input — and they must "
            "equal both the refresh's claim and the original's own values, so a refresh "
            "can never be minted from the original digest; and reproduced_at must be "
            "strictly after the original's own expiry, which only binds because the "
            "original is itself validated by its family validator (a hand-written original "
            "picks its own expiry, so before that check the strictly-after rule was "
            "structural in appearance only). Both statements were FALSE before the W5 "
            "adversarial review: the recomputation read Path.read_bytes() from the working "
            "tree while the head came from git metadata, so restoring pre-drift bytes in "
            "the working tree alone (no commit, no git add) reproduced a drifted identity "
            "and reached DEPENDENCY_REFRESH_ADMITTED; and the original receipt was checked "
            "only for isinstance/schema_version/self-referential digest. TWO RESIDUALS "
            "REMAIN, both scoped: (i) materialisation covers the bytes the producer HASHES, "
            "not the producer code the verifying PROCESS has already imported — that half "
            "rests on the clean-tree gate over the same input set plus producer_module_digest "
            "being taken from the bound commit, and a verifier wanting full isolation must "
            "run FROM the clone rather than pass repo_root at it; (ii) the input set is "
            "code-owned, and for S2.2A a missing entry fails loudly (the materialised tree "
            "is all the producer can see, so an incomplete set raises missing_input) while "
            "for S1.3/S2.3 an incomplete set would silently narrow only the clean-tree gate. "
            "DECLARATIVE: that the reproducing NODE differs from the producing node rests on "
            "reproducer_caller not equalling the original's producer label, which a hostile "
            "producer can simply relabel. The source lane holds no key material at all (see "
            "ATTESTOR_KEY_IS_NOT_SEPARATE_FROM_THE_PERMIT_KEY), so node custody cannot be "
            "established here; closing it means a per-node attestor identity, which is a "
            "W6 key-custody decision about real hosts. A second, smaller asymmetry is "
            "recorded rather than hidden: source_compatibility_receipt_v1/v2 carry no "
            "'caller' or 'platform' field at all, so for S2.2A the producer label degrades "
            "to session_id ('S2.2A') and the platform component of the projection is null."
        ),
        "w5_provides": (
            "the commit-bound recomputation, the clean-tree gate over the producer input "
            "set, the family-validator authentication of the original, and the exact "
            "statement of the two residuals and of what a relabelling producer could do"
        ),
    },
    {
        "obligation_id": "ENCODED_SECRET_SCAN_MISSES_COMPOSITE_PAYLOADS",
        "typed_status": "RECORDED_NOT_CLOSED",
        "owner_wave": "W6B",
        "spec_refs": ["§10.5 #15"],
        "statement": (
            "assert_no_secret_material derives six encoded forms of each sentinel and looks "
            "for them as SUBSTRINGS. That finds a payload which is exactly the encoded "
            "secret, which is the case W5's own tests exercise. It does NOT find a "
            "composite payload b64(prefix + secret). The arithmetic, stated so the next "
            "reader need not rediscover it: base64 consumes three input bytes per four "
            "output chars, so b64(prefix + secret) contains b64(secret) as a substring only "
            "when len(prefix) % 3 == 0. Two of the three byte alignments therefore evade "
            "the scan entirely. Closing it means adding the two shifted cores per sentinel: "
            "for alignment a in {1, 2}, encode a filler bytes followed by the secret, drop "
            "the first {1: 2, 2: 3} characters (those mix filler bits) and drop the last "
            "character when (a + len(secret)) % 3 != 0 (it carries zero-padding bits the "
            "real successor byte would supply), then match the remaining core. base32, "
            "base85, unpadded base64, percent-encoding, \\\\uXXXX escapes and PEM line "
            "wrapping are not covered at all and need a decode-then-rescan pass rather than "
            "more precomputed forms. W5 SURFACED this and does NOT close it: "
            "agent_governance_s2_4_credential.py is not a W5-owned path (§10.1.1), the "
            "shifted cores are short for short sentinels so a minimum-core-length rule has "
            "to be designed with the false-positive blast radius of a fail-closed scanner "
            "in mind, and the six uncovered encodings leave the obligation open either way."
        ),
        "w5_provides": (
            "the finding, the exact alignment arithmetic and the prescription (shifted "
            "cores at prefix lengths 0/1/2 plus a decode-then-rescan pass, with a "
            "composite-offset test at each alignment), and the honest reason it is not "
            "closed here"
        ),
    },
    {
        "obligation_id": "PROGRAM_CODE_IS_ON_THE_SCANNER_PATH_VIA_W4",
        "typed_status": "PARTIALLY_PROVIDED_BY_W5",
        "owner_wave": "PM",
        "spec_refs": ["§10.1.1"],
        "statement": (
            "Making program_code/ importable widens the top-level namespace of every "
            "process that loads the facade — broker_connectors, exchange_connectors, "
            "dashboard and ai_agents all become resolvable in the engine-scanner process. "
            "No shadowing or hijack was found, but under §10.1.1 condition 4 that has to be "
            "a decision rather than an import side effect. W5 removed its own two "
            "occurrences: the contracts leaf now opens the path inside the one function "
            "that needs the ml_training package import and removes it again, and the W5 "
            "projection leaf never needed it at all. The process-level property is still "
            "NOT achieved, and W5 says so rather than claiming a closure it did not reach: "
            "aiml_gate_receipt_wave_w4.py does the same insertion at import time, it "
            "predates W5 (it is present at the merge base e98520cad), and it is a W4-owned "
            "path. Unifying it is the same PM path-scope call as "
            "OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM."
        ),
        "w5_provides": (
            "the two W5-owned occurrences removed, a leaf-scoped regression that fails if "
            "either returns, and the line-verified statement that W4 still holds the "
            "namespace open"
        ),
    },
    {
        "obligation_id": "PR_SET_DUMPABLE_IS_DECLARED_NOT_ENFORCED",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "W6B",
        "spec_refs": ["§7", "§10.5 #26"],
        "statement": (
            "§10.5 #26 requires PR_SET_DUMPABLE=0 to be LOAD-BEARING. It is not. "
            "PROCESS_HARDENING_CONTRACT['pr_set_dumpable'] = 0 is a declared constant that "
            "appears in exactly two projection dicts and in nothing else: "
            "derive_host_credential_capability_status checks systemd_creds_available, "
            "tpm2_available and decryption_name_verification and never looks at it, and no "
            "driver protocol method observes it. The pre-existing test named "
            "test_process_hardening_contract_is_load_bearing asserts the constant equals "
            "itself, which is exactly the failure mode this wave was sent to find. The "
            "other four clauses of #26 ARE load-bearing: --with-key=host+tpm2 is enforced "
            "through tpm2_available, the encrypted-blob fingerprint is re-derived and "
            "compared, the closed eight-key DSN set is enforced, and LimitCORE=0 plus the "
            "PG*/LD*/PYTHON* scrub are enforced by the unit's byte-equality check. Closing "
            "this one means observing prctl(PR_GET_DUMPABLE) on the applier and refusing "
            "when it is not 0 — a driver-protocol and host-observation change, i.e. "
            "production implementation on a real host, not a test."
        ),
        "w5_provides": (
            "the finding, the exact reason the existing test is tautological, and the "
            "honest classification of §10.5 #26 as PARTIALLY PROVEN"
        ),
    },
    {
        "obligation_id": "S2_5_LIFECYCLE_FIXTURES_DO_NOT_EXIST",
        "typed_status": "OUT_OF_WP4_SCOPE",
        "owner_wave": "S2.5A",
        "spec_refs": ["§10.5 #29", "§11.3"],
        "statement": (
            "§10.5 #29's second clause says 'S2.5 fixtures own `enable --now`, "
            "enabled/reboot persistence and rollback-to-disabled'. No S2.5 source or "
            "fixture exists in this repository, so that clause has no owner in WP4 and "
            "cannot be satisfied here. What W5 CAN and does prove is the S2.4 half: the "
            "aggregate driver surface refuses enable/start/restart/kill, the closed "
            "postcheck and receipt schemas carry no runtime-directory or "
            "decrypted-credential property, and an enabled or active observation is never "
            "a success. The clause is recorded rather than counted as covered."
        ),
        "w5_provides": (
            "the S2.4 half as a live re-derivation and the explicit statement that the S2.5 "
            "half has no owner in this work package"
        ),
    },
    {
        "obligation_id": "SOURCE_IDENTITY_FRESHNESS_HAS_NO_PRODUCTION_CALL_SITE",
        "typed_status": "NOT_PROVIDED_BY_W5",
        "owner_wave": "PM",
        "spec_refs": ["§8", "§9.2", "§10.1.1", "§10.4", "§10.5 #28"],
        "statement": (
            "§9.2 says the central validator accepts an expired source-identity receipt "
            "only together with one current refresh attestation. That rule is implemented "
            "(derive_source_dependency_admission_status) and has ZERO production callers: "
            "the projection measures the whole S2.4 governance surface and finds the name "
            "only in the two W5 test files and in this projection leaf. Measured "
            "consequence: validate_aiml_artifact returns [] for all three genuinely "
            "expired shipped receipts (S2.2A compatibility, S2.3 sealed-build, S2.3 "
            "expected-identity, the latter two expiring 2026-07-24T00:30Z) with no refresh "
            "present. W5 does NOT wire it, and says exactly why rather than shipping a "
            "half-wiring. (1) The only APPLY-time consumer of a §9.2 source identity is "
            "agent_governance_s2_4_host_identity.s2_3_expected_identity_reasons, called "
            "from the HOST_IDENTITY_INSTALL row; it reads the S2.3 artifact from a fixed "
            "repository path and checks status/self_digest/three identity fields, deriving "
            "no freshness. That module is a W3-owned path (§10.1.1), and its verdict is "
            "folded live into the W3 exported ABI, so adding a fail-closed freshness reason "
            "there permanently breaks the W3 wave exit — the shipped receipts ARE expired "
            "and nothing anywhere carries a refresh to admit them. (2) PREPARE only ever "
            "receives the DIGESTS of these receipts (build_prepare_intent's "
            "source_lock_closure_identity), never the objects, so §9.2's verifier-side "
            "replay — which is defined over the ORIGINAL artifact — cannot run there "
            "without a new plumbing field. (3) Making validate_aiml_artifact wall-clock-"
            "expire committed build-identity receipts is the documented time bomb that "
            "branch deliberately refuses (a fixed 30-minute TTL on committed evidence would "
            "make every offline/CI consumer reject it), and it still could not admit a "
            "refresh, because a single-artifact entry point has nowhere to receive one. "
            "Closing this needs a PM decision about WHERE the refresh enters APPLY, which "
            "is the same exported-schema question as "
            "DEPENDENCY_REFRESH_RECEIPT_BINDING_ABSENT."
        ),
        "w5_provides": (
            "the complete §9.2 gate, the measured zero-call-site fact folded live into this "
            "wave's ABI, a two-way latch that breaks the wave exit if the row is deleted "
            "while the fact holds OR kept once a production call site appears, and the "
            "retirement of the false sentence that previously claimed APPLY reached it"
        ),
    },
    {
        "obligation_id": "EMITTED_EVIDENCE_DIGESTS_ARE_UNAUTHENTICATED",
        "typed_status": "RECORDED_NOT_CLOSED",
        "owner_wave": "PM",
        "spec_refs": ["§10.3", "§10.5 #27", "§11.3"],
        "statement": (
            "The W0->W5 chain proves nothing about whether tests ran or a review happened. "
            "validate_emit_evidence checks exactly three things — a non-empty object, a "
            "non-empty list of non-empty objects, and a secret scan — and the wave-exit "
            "schema constrains test_digests / capture_digests / review_fragment_digests "
            "with minItems:1 and a sha256 hex pattern and nothing else, so the entire chain "
            "derives PASS on sha256:111...1. This is pre-existing across W0-W4 and W5 does "
            "not retrofit it, but it becomes load-bearing the moment S2.4@SOURCE_READY is "
            "declared FROM the chain, which is what W5 is for. It is not closable in the "
            "source lane, and the reason is structural rather than budgetary: a "
            "packet-local artifact cannot authenticate its own execution. A canonical "
            "self-digest proves integrity only — never who produced a result nor that a "
            "command ran — so an execution claim needs ORCHESTRATOR_BOUND controller facts "
            "or PLATFORM_OR_EXTERNAL_ATTESTED telemetry (CLAUDE.md evidence assurance). "
            "Nor can W5 raise the bar by binding the digests to something it can recompute: "
            "the only thing a source-lane verifier can independently recompute is "
            "repository content, and the receipt ALREADY binds exactly that through "
            "owned_path_diff_digest over the bound commit's blobs. Requiring test_digests "
            "to repeat those blob digests would add a shape rule and zero assurance, so W5 "
            "refuses to add a check that reads like a gate and is not one. What a green "
            "chain licenses is therefore SOURCE structure at a head, never 'the tests were "
            "executed'."
        ),
        "w5_provides": (
            "the finding, the exact structural reason it cannot be closed here, a live "
            "measurement of what actually constrains the three evidence fields (including "
            "the positive controls proving the emit guard is not vacuous), and a latch "
            "requiring this row while a fabricated digest still satisfies every constraint"
        ),
    },
    {
        "obligation_id": "EXPECTED_TOPOLOGY_IS_CALLER_SUPPLIED_AND_UNSIGNED",
        "typed_status": "RECORDED_NOT_ABSORBED",
        "owner_wave": "PM",
        "spec_refs": ["§8.2", "§10.1.1", "§10.2", "§10.4", "§10.5 #25"],
        "statement": (
            "expected_topology sits in ROW_PAYLOAD_ALLOWLIST['PG_ROLE_ACL_MIGRATION'] "
            "beside acl_manifest and topology_attestation, but unlike those two it is bound "
            "to NOTHING: s2_4_component_effect_intent_v1's PG branch requires only "
            "topology_attestation_digest / acl_manifest_digest / pg_migration_permit_digest "
            "/ admin_handle_descriptor_digest, so no signature covers what the caller says "
            "it expects. Control flow, verified line by line. A caller cannot DELETE the "
            "check: derive_pg_topology_status calls _hba_projection_reasons, which returns "
            "'expected signed HBA projection is missing' when expected.hba_projection is "
            "absent, so an omitted or empty expected_topology is PG_TOPOLOGY_UNPROVEN. But "
            "a caller CAN WEAKEN it two ways. (a) Every baseline comparison is guarded by "
            "`expected.get(field) is not None` — listener_config_digest, proxy_config_"
            "digest, cluster_identity_digest, source_head and target_host — so omitting a "
            "key silently skips that drift comparison. (b) hba_projection.entries is the "
            "caller's own list, and the attested effective rule only has to be a member of "
            "it, so a caller can declare a wide-CIDR or trust rule acceptable. Severity is "
            "bounded but real: the attestation itself IS digest-bound to the signed intent, "
            "so a weakened expectation cannot substitute a different observation — it can "
            "only stop drift from being noticed. W5 does NOT remove the key, and says why: "
            "agent_governance_s2_4_install_driver.py is a W4-owned path and "
            "agent_governance_s2_4_topology.py / _apply.py are W3-owned (§10.1.1); removing "
            "it with no replacement source makes every aggregate PG row permanently "
            "PG_TOPOLOGY_UNPROVEN and breaks the W4b test kit, because nothing else "
            "supplies an HBA projection; and the correct replacement is plan-derived, not "
            "code-owned — s2_4_install_plan_core_v1 ALREADY binds topology_pre_digest and "
            "hba_delta_digest, and the signed s2_4_pg_hba_delta_v1 already carries the "
            "exact effective_rule, so the fix is to thread that signed delta into the row "
            "and derive expected_topology from it. That is a row-ABI/plumbing change §10.4 "
            "puts on PM, exactly like PRIOR_LINEAGE_ENTRY_IDENTITY. Note the same shape in "
            "the existing fixtures: _w3_topology_expected builds its 'expected' FROM the "
            "attestation, so today even the W3 lane's baseline is self-fulfilling."
        ),
        "w5_provides": (
            "the finding, the exact two weakening paths and the exact reason omission is "
            "not one of them, the bound on its severity, and the plan-derived prescription "
            "naming the fields that already exist"
        ),
    },
    {
        "obligation_id": "OWNED_PATH_PROJECTION_RULER_IS_NOT_UNIFORM",
        "typed_status": "RECORDED_NOT_ABSORBED",
        "owner_wave": "PM",
        "spec_refs": ["§10.3"],
        "statement": (
            "W0/W1/W2 and W5 project owned-path content from the BOUND COMMIT's blobs "
            "(owned_path_blob_projection_digest), which is the corrected form W2's review "
            "landed after finding that a projection over working-tree bytes lets a receipt "
            "certifying an unchanged HEAD be self-consistent on a dirty tree. W3 and W4 "
            "still hash working-tree bytes through their own _file_sha256. Every wave "
            "remains internally self-consistent, so no chain derivation is wrong today, but "
            "two different rulers are in use across one receipt chain. W5 does not change "
            "aiml_gate_receipt_wave_w3.py or _w4.py: they are W3/W4-owned files and "
            "unifying them is a PM path-scope call, not a test-writer's."
        ),
        "w5_provides": (
            "the corrected ruler for W5's own projection plus owned_scope_worktree_delta "
            "visibility, and this explicit record of the divergence"
        ),
    },
]


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

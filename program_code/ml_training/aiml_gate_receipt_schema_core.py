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
    "s2e_launch_genesis_receipt_v1": "s2e_launch_genesis_receipt_v1.schema.json",
    "s2e_launch_wave_receipt_v1": "s2e_launch_wave_receipt_v1.schema.json",
    "receipt_carrier_attestation_v1": "receipt_carrier_attestation_v1.schema.json",
    "s2e_launch_acceptance_review_bundle_v1": (
        "s2e_launch_acceptance_review_bundle_v1.schema.json"
    ),
    "s2e_disposable_test_effect_chain_v1": (
        "s2e_disposable_test_effect_chain_v1.schema.json"
    ),
    "s2e_launch_predecessor_consumption_ledger_v1": (
        "s2e_launch_predecessor_consumption_ledger_v1.schema.json"
    ),
    "s2e_launch_consumption_bootstrap_authority_v1": (
        "s2e_launch_consumption_bootstrap_authority_v1.schema.json"
    ),
    "s2e_durability_anchor_attestation_v1": (
        "s2e_durability_anchor_attestation_v1.schema.json"
    ),
    "s2e_predecessor_registry_attestation_v1": (
        "s2e_predecessor_registry_attestation_v1.schema.json"
    ),
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
    # S2.5(WP5·design §5/§6)——additive:running-attestation seam 的五個 typed schema 與
    # additive v3 component-effect 分類 artifact。加這六鍵純為 schema 查找,絕不進入
    # aiml_effect_classifier_digest() 的六個 S0.3 常量輸入(見 :46-48/§7.2),S0.3 分類身分
    # 不動;亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2 component matrix/digest。中央閘依 exact
    # schema_version 委派 aiml_gate_receipt_s2_5.validate_s2_5_artifact(結構/整合/新鮮度/
    # attestor 驗簽面);五個 s2_5 artifact 全屬 §9.2 never-refreshable(runtime 觀測類:
    # 只可重新觀測,永不可 refresh-by-reference)。乾淨 [] 只證結構,「不」證任何 unit 真的
    # enabled/running——attested status 唯一由 trusted-host attestor SSHSIG 解鎖(key custody
    # 鎖產線),九項 authority 恆 false。
    "s2_5_start_core_v1": "s2_5_start_core_v1.schema.json",
    "s2_5_start_intent_v1": "s2_5_start_intent_v1.schema.json",
    "s2_5_running_attestation_v1": "s2_5_running_attestation_v1.schema.json",
    "s2_5_final_attestation_v1": "s2_5_final_attestation_v1.schema.json",
    "s2_5_rollback_drill_receipt_v1": "s2_5_rollback_drill_receipt_v1.schema.json",
    # S2.5(WP5 tranche 1b·E3 P1-3)——additive:S2.5 自己的 hash-chained replay ledger
    # (鏡 sibling s2_4_authorization_replay_ledger_v1;consume-once 的 durable 契約)。
    # 同上:純 schema 查找,不進 S0.3 classifier 輸入,不動 PROGRAM_SCHEMA_PATHS。
    "s2_5_authorization_replay_ledger_v1": (
        "s2_5_authorization_replay_ledger_v1.schema.json"
    ),
    # S2E.LW1:identity-bound S2.5 unresolved-recovery chain.  These are source contracts;
    # off-root anchor/unresolved-manifest persistence remains a later host-runtime slice.
    "s2_5_recovery_host_capture_v1": (
        "s2_5_recovery_host_capture_v1.schema.json"
    ),
    "s2_5_recovery_intent_v1": "s2_5_recovery_intent_v1.schema.json",
    "s2_5_recovery_result_v1": "s2_5_recovery_result_v1.schema.json",
    "s2_5_recovery_postcheck_v1": "s2_5_recovery_postcheck_v1.schema.json",
    "s2_5_recovery_rollback_v1": "s2_5_recovery_rollback_v1.schema.json",
    "aiml_component_effect_classification_v3": (
        "aiml_component_effect_classification_v3.schema.json"
    ),
    # S2.2B(WP5 tranche 2·S2.5 design §10)——additive:LR1 runtime revalidation 的
    # ingestion-compatibility receipt(effect class REMOTE_READONLY;唯一可發 LR1 runtime
    # DONE 的 row,runtime-DONE 消費 S2.5B@EFFECT_DONE)。加這鍵純為 schema 查找,絕不進
    # aiml_effect_classifier_digest() 的六個 S0.3 常量輸入(見 §7.2),S0.3 分類身分不動;
    # 亦不改 PROGRAM_SCHEMA_PATHS 與 v1/v2/v3 component matrix/digest。中央閘依 exact
    # schema_version 委派 aiml_gate_receipt_s2_2b.validate_s2_2b_artifact(S2.2A 三值鏈
    # 重算 + s2_5_final_attestation 全套重驗含 attestor 驗簽 + V151-V160 逐項 revalidation
    # 導出式結果)。乾淨 [] 不證任何 runtime;九項 authority 恆 false。
    "ingestion_compatibility_receipt_v1": "ingestion_compatibility_receipt_v1.schema.json",
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
def _git_run(repo_root: Path, arguments: list[str]) -> tuple[str, str] | None:
    """跑一次 git,回 ``(stdout, stderr)``;非零離開/無法執行回 ``None``。

    W5 對抗審計第三輪 P2:舊版把 stderr 整個丟掉,於是「repo 不屬於當前 uid」這個最可能
    的真實主機故障(git 自己會印 ``detected dubious ownership … git config --global --add
    safe.directory <path>``)在 operator 眼裡只剩「git is unreadable」。stderr 是 git 唯一
    給出補救指令的地方,必須被帶出來。
    """

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
    if proc.returncode != 0:
        return None
    return proc.stdout, proc.stderr


def _git_stdout(repo_root: Path, arguments: list[str]) -> str | None:
    outcome = _git_run(repo_root, arguments)
    return None if outcome is None else outcome[0]


def git_failure_detail(repo_root: Path) -> str | None:
    """git 為什麼讀不了這棵樹(取 ``rev-parse`` 的 stderr 首行);讀得了回 ``None``。

    只在 fail-closed 路徑上被呼叫,用來把 git 自己的補救指令原文帶進 typed reason。
    """

    import subprocess

    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--git-dir"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except OSError as error:
        return f"git could not be executed: {error}"
    except (ValueError, subprocess.SubprocessError) as error:
        return f"git invocation failed: {error}"
    if proc.returncode == 0:
        return None
    first = next(
        (line.strip() for line in proc.stderr.splitlines() if line.strip()), ""
    )
    return first or f"git exited {proc.returncode} with no diagnostic"


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


def git_is_shallow_repository(repo_root: Path) -> bool:
    """這棵 repo 是不是淺 clone(CI 預設 ``fetch-depth: 1``)。

    W5 對抗審計第三輪 P2:淺樹上 ``merge-base --is-ancestor`` 對不在 graft 裡的物件回非零,
    而那不是「不是祖先」,是「這裡沒有那個物件」。呼叫端據此把訊息從一個假結論換成真補救。
    """

    return (_git_stdout(repo_root, ["rev-parse", "--is-shallow-repository"]) or "").strip() == "true"


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


def _is_safe_repo_relative_path(rel: Any) -> bool:
    """該字串可否安全地(a)進 ``git cat-file --batch`` 請求串流、(b)當作寫檔的相對路徑。

    拒:非字串/空字串、含 ``\\n``(會把 ``--batch`` 的請求與回應串流錯開)、絕對路徑、
    含 ``..`` 或 ``.`` 節、以及 Windows 磁碟機形。純結構判定,不碰檔案系統。
    """

    if not isinstance(rel, str) or not rel:
        return False
    if "\n" in rel or "\r" in rel or "\0" in rel:
        return False
    if rel.startswith("/") or rel.startswith("\\") or ":" in rel.split("/", 1)[0]:
        return False
    parts = rel.split("/")
    return all(part not in ("", ".", "..") for part in parts)


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
    # W5 對抗審計第三輪 P2:``--batch`` 是換行分隔的請求串流,而 ``materialize_commit_paths``
    # 會把回應寫成 ``target / rel``。今天每一條路徑都來自 code-owned 表,故不可達;但這裡是
    # 驗證路徑上的一個寫檔原語,不安全的形狀必須在原語層就拒(而不是靠呼叫端全都乖)。
    if any(not _is_safe_repo_relative_path(rel) for rel in ordered):
        return blobs
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
    root = Path(target).resolve()
    missing: list[str] = []
    for rel, payload in blobs.items():
        if payload is None:
            missing.append(rel)
            continue
        destination = (root / rel).resolve()
        # containment:寫入點必須真的落在 ``target`` 之下。``commit_blob_bytes`` 已在原語層
        # 拒掉 ``..``/絕對路徑/換行,這裡是第二道(symlink 造成的逃逸只有 resolve 看得見)。
        if root != destination and root not in destination.parents:
            raise ValueError(
                f"refusing to materialise {rel!r} outside the scratch tree {root}"
            )
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
    """owned scope 內**工作樹位元組**與 bound commit blob 不相等的路徑(不可判定回 None)。

    P1-5 的可見性面:投影已綁 commit blob,故髒工作樹不再污染 digest;但「這份 receipt
    是從一棵髒工作樹發射的」本身是事實,必須可被看見而不是靜默。

    W5 對抗審計第三輪 P1-A(E2/E3/OPS 三方同結論):舊版用 ``git status --porcelain`` 當
    oracle,那有三個各自獨立的洞——(1)``git status`` **永遠**比對 HEAD,而本函式收的是
    ``source_head``,於是一份綁了非 HEAD commit 的 receipt 會拿「與 HEAD 無差異」當成
    「與 bound commit 無差異」;(2)``git update-index --assume-unchanged`` /
    ``--skip-worktree`` 會讓被改過的檔案在 ``git status`` 中完全消失,而 index 旗標與
    ``core.trustctime`` 都住在正被見證的那棵樹裡面;(3)rename 記錄的 ``-z`` 形是
    ``R  <new>\\0<old>\\0``,舊版的 ``record[3:]`` 對兩半各切一次,於是印出根本不存在的路徑。
    改為**內容定址**:逐一 hash 工作樹位元組,與 :func:`owned_path_blob_projection` 自 bound
    commit 取得的同一把尺比對。index 無關、git config 無關,``source_head`` 與 HEAD 的分歧
    也在同一刀下消失。不可讀 / 該 commit 無此 blob 一律計入差異(fail-closed)。
    """

    ordered = sorted(paths)
    head = resolve_commit_head(repo_root, source_head)
    if head is None:
        return None
    committed = owned_path_blob_projection(repo_root, ordered, source_head=head)
    root = Path(repo_root)
    delta: set[str] = set()
    for rel in ordered:
        expected = committed.get(rel)
        try:
            payload = (root / rel).read_bytes()
        except OSError:
            observed = None
        else:
            observed = "sha256:" + hashlib.sha256(payload).hexdigest()
        if expected is None or observed is None or observed != expected:
            delta.add(rel)
    return sorted(delta)


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

# ── §9.2 原 source 身分的**已提交**位置 —— W5 對抗審計第三輪 P1-B ───────────────────
# §9.2 的新鮮度裁決讀的是原 receipt 自己的 ``observation_time``/``expires_at``,而那兩欄在
# caller 手上:E2 在**真的**已出貨 receipt 上只改這兩個時間戳並重封 self_digest,家族驗證器
# 全過,三族一律導出 SOURCE_DEPENDENCY_FRESH——整個 §9.2 閘就這樣被跳過。家族驗證器認證的是
# 形狀,不是那個窗。這裡把窗綁回**那個 commit 的 blob**:三族的原身分在 repo 內都是已提交的
# 固定路徑,故「這份 evidence 是不是那份被提交的 artifact」是驗證端自己算得出來的。
#
# S1.3 沒有已提交的 receipt(它是一次性 disposable 觀測),所以它的窗**仍然**是 caller 自選
# 的。那個不對稱不被隱藏:見 obligation ``DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED``。
S2_4_COMMITTED_SOURCE_IDENTITY_PATHS: dict[str, tuple[str, ...]] = {
    "S1_3_IDENTITY_CONTRACT": (),
    "S2_2A_SOURCE_COMPATIBILITY": (
        "docs/execution_plan/ai_ml_landing/receipts/"
        "S2.2A-source-compatibility-receipt-v1.json",
        "docs/execution_plan/ai_ml_landing/receipts/"
        "S2.2A-source-compatibility-receipt-v2.json",
    ),
    "S2_3_EXPECTED_IDENTITY": (
        "docs/execution_plan/ai_ml_landing/receipts/S2.3-expected-identity-receipt-v1.json",
    ),
    "S2_3_SEALED_BUILD": (S2_3_SEALED_BUILD_RECEIPT_REL,),
}


# ── §9.2 可刷新 / 永不可刷新的 evidence 分類表(2000 行治理拆分:自 contracts 葉逐位元組
# 搬入,零語義變更;contracts 逐名再導出以維持既有匯入面)────────────────────────
# §9.2 第一列:**可**以一份獨立重算的 refresh 續命的三族 source 身分。每列宣告
#   original_schema_versions —— 允許的原 receipt schema(封閉;不含 refresh 自身)
#   semantic_digest_fields  —— 該族的 exact 語義**主體**集(refresh 必須逐項復現)
#   producer_module         —— 驗證端重跑的 producer SSOT 模組(其 blob 亦被 refresh 綁)
#
# W5 對抗審計 P1-A:S1.3 / S2.3 兩族原本的主體集是 ("schema_sha256", "source_sha256"),而
# ``source_sha256`` 逐位元組等於 refresh 另欄已綁的 ``producer_module_digest``(兩支
# producer 的 source_sha256() 都是 ``_file_sha256(SOURCE_PATH)``),於是「獨立復現 producer/
# semantic checks」退化成「兩個檔案沒變」——被證的主體一個都不在裡面。現在每一族都逐項復現
# 該 producer **真正產出的內容**(見 schema_core 的 recompute/extract 成對投影)。
S2_4_DEPENDENCY_REFRESH_CLASSES = {
    "S1_3_IDENTITY_CONTRACT": {
        "original_schema_versions": ("identity_acl_contract_receipt_v1",),
        "semantic_digest_fields": (
            "identity_projection_digest",
            "negative_acl_kinds_digest",
            "schema_sha256",
            "source_sha256",
        ),
        "producer_module": (
            "helper_scripts/maintenance_scripts/agent_governance_identity_acl_contract.py"
        ),
    },
    "S2_2A_SOURCE_COMPATIBILITY": {
        "original_schema_versions": (
            "source_compatibility_receipt_v1",
            "source_compatibility_receipt_v2",
        ),
        "semantic_digest_fields": (
            "capture_contract_digest",
            "learning_runtime_digest",
            "training_contract_digest",
        ),
        "producer_module": "program_code/ml_training/learning_runtime_manifest.py",
    },
    "S2_3_EXPECTED_IDENTITY": {
        "original_schema_versions": ("expected_identity_receipt_v1",),
        "semantic_digest_fields": (
            "expected_component_identities_digest",
            "rollback_binding_digest",
            "runtime_content_digest",
            "s1_3_negatives_digest",
            "schema_sha256",
            "sealed_build_digest",
            "source_sha256",
        ),
        "producer_module": (
            "helper_scripts/maintenance_scripts/agent_governance_sealed_build.py"
        ),
    },
    "S2_3_SEALED_BUILD": {
        "original_schema_versions": ("sealed_build_receipt_v1",),
        "semantic_digest_fields": (
            "closure_hash",
            "native_library_inventory_digest",
            "runtime_content_digest",
            "schema_sha256",
            "source_sha256",
        ),
        "producer_module": (
            "helper_scripts/maintenance_scripts/agent_governance_sealed_build.py"
        ),
    },
}
# 四族原 receipt 各自的**成功**狀態(S2.2A 兩版是 const SOURCE_READY;S2.3/S1.3 三族的
# schema enum 是 ["PASS","FAIL"],故 FAIL 必須被顯式擋掉而不是靠 schema)。
_DEPENDENCY_EVIDENCE_SUCCESS_STATUSES = frozenset({"PASS", "SOURCE_READY"})
# §9.2 其餘各列:**永不**可以引用刷新的證據。值為該列自己的補救文字(§10.5 #28 後半)。
S2_4_NEVER_REFRESHABLE_EVIDENCE = {
    "APPLY_AGGREGATE_AUTHORIZATION": (
        "the aggregate operator permit is newly signed only after W6A, the topology/HBA/"
        "network evidence and the final plan core exist; it is never refreshed or chained"
    ),
    "CAPABILITY_PROBE_AUTHORIZATION": (
        "a capability-probe permit is newly signed for one exact scope/core before each "
        "probe; it cannot authorize PREPARE/APPLY or the other scope"
    ),
    "CAPABILITY_PROBE_RECEIPT_INSTALLED_UNIT": (
        "the INSTALLED_UNIT capability-probe receipt is freshly authorized/observed only "
        "after W6A against the exact rendered unit/host"
    ),
    "CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX": (
        "the PREPARE_SANDBOX capability-probe receipt is freshly authorized/observed "
        "immediately before W6A against fixed prepare sandbox properties"
    ),
    "PG_MIGRATION_AUTHORIZATION": (
        "the PG-migration operator permit is newly signed only after W6A; it is never "
        "refreshed or chained"
    ),
    "PG_TOPOLOGY_ATTESTATION": (
        "pg_topology_attestation_v1 is always freshly observed; no refresh-by-reference"
    ),
    "PREPARED_BUNDLE": (
        "the prepared bundle is freshly re-hashed and inside its own expiry; otherwise "
        "rerun PREPARE"
    ),
    "PREPARE_AUTHORIZATION": (
        "the PREPARE permit is newly signed after the final prepare core and PREPARE-scope "
        "probe receipt exist, before W6A; it is never refreshed or chained"
    ),
    "S2_0_EFFECT_RECEIPT": (
        "the S2.0 effect receipt is a fresh production observation; rerun the S2.0 effect/"
        "postcheck if expired"
    ),
}


_OWNED_SCOPE_REASON_TAIL = "wave-exit owned scope is not at the bound source_head"


def owned_scope_reason_prefix(wave: Any) -> str:
    """該 wave 的 owned-scope reason 具名前綴(測試據此分離,而不是靠字串比對全文)。"""

    return f"{wave} {_OWNED_SCOPE_REASON_TAIL}"


def owned_scope_delta_reasons(
    wave: Any,
    paths: tuple[str, ...] | list[str],
    repo_root: Path,
    *,
    source_head: str | None = None,
) -> list[str]:
    """該 wave 的 owned scope 是否真的就在它自己綁定的那個 commit 上(不可判定亦 fail-closed)。

    W5 對抗審計第三輪 P1-D:這段裁決原本**只有 W5 有**(measured:w2/w3/w4 consumed=0,
    w5 consumed=1),而 W2 擁有 operator 真正執行的四支腳本(``agent_governance_s2_4_install``
    / ``_render`` / ``_sql_scan`` / ``_emit_sink``),於是一份綁了 ``source_head`` 的 W2
    wave-exit 可以從一棵那四支被本地改過的樹導出 PASS。比對是**內容定址**的
    (見 :func:`owned_scope_worktree_delta`):index 旗標(``--assume-unchanged`` /
    ``--skip-worktree``)、``core.trustctime`` 與 ``source_head`` ≠ HEAD 三條繞道都不存在。
    """

    prefix = owned_scope_reason_prefix(wave)
    delta = owned_scope_worktree_delta(repo_root, paths, source_head=source_head)
    if delta is None:
        detail = git_failure_detail(repo_root)
        return [
            f"{prefix}: the {wave} owned scope cannot be compared against the bound commit "
            f"(git is unreadable: {detail or 'no diagnostic'}), so the receipt cannot assert "
            "that its owned scope IS that commit (fail-closed)"
        ]
    if delta:
        return [
            f"{prefix}: {delta} differ in content from the bound commit. The owned-path "
            "projection is taken from the commit blobs, so a dirty owned scope is invisible "
            "in owned_path_diff_digest; a wave-exit receipt that binds source_head is "
            "asserting its owned scope IS that head — commit or revert these paths, then "
            "re-derive this receipt"
        ]
    return []


def committed_source_identity_digests(
    dependency_class: Any, repo_root: Path, *, source_head: str | None = None
) -> list[str] | None:
    """該族在 bound commit 上**已提交**身分的 canonical digest 集合。

    回 ``None`` 表示「這一族在此 repo 沒有可比對的已提交身分」(S1.3 恆如此;一棵不含那些
    路徑的隔離樹亦然),與「有,但一個都對不上」是兩件不同的事,故不能用空 list 代表。
    """

    paths = S2_4_COMMITTED_SOURCE_IDENTITY_PATHS.get(str(dependency_class))
    if not paths:
        return None
    blobs = commit_blob_bytes(Path(repo_root), paths, source_head=source_head)
    digests: list[str] = []
    for rel in sorted(paths):
        payload = blobs.get(rel)
        if payload is None:
            continue
        try:
            digests.append(artifact_self_digest(json.loads(payload.decode("utf-8"))))
        except (ValueError, UnicodeDecodeError):
            continue
    return digests or None


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


# ── §10.3 W5 誠實面:未關閉義務帳本 ────────────────────────────────────────────
# 2000 行治理拆分(第三輪):純資料清單移入 ``aiml_gate_receipt_w5_obligations``,本葉逐名
# 再導出以維持既有匯入面(W5 投影葉與 validator facade 都自此取用)。零語義變更。
from aiml_gate_receipt_w5_obligations import (  # noqa: E402
    S2_4_W5_REMAINING_OWNED_OBLIGATIONS,
)


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

"""S2.4(WP4·W1)per-row ABI / install-lineage / §9.1 授權 profile 下層(facade 2000 行治理拆分)。

這是 ``aiml_gate_receipt_validator``(facade)的**下層**:CP3 的五 APPLY row §4 逐行 ABI 綁定
(derive_component_intent_binding)、route-class core 再導出、install plan/aggregate-lineage 謂詞,
與 CP4 的四 §9.1 operator-authorization trust profile + 離線驗證分支。全部為逐位元組等值搬移,
``s2_4_authorization_profiles_digest`` 保持 byte-frozen;消費者「只」匯入 facade。

**循環相依處理與 monkeypatch 縫。** 本模組 top-level 只匯入 sibling 下層與 out-of-scope 的
trusted-host 模組,絕不匯入 facade;唯一的 facade 讀點在 ``_s2_4_operator_authorization_errors``
函式內**延遲匯入** facade 讀 pinned 信任根副本——CP4 測試 monkeypatch 的注入點是 facade 模組
物件(拆分前的「本模組 global」縫),延遲匯入保持該縫逐字有效。
"""

from __future__ import annotations

import base64
import binascii
import hmac
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))
# §9.2 的 producer 重算需以 package 形匯入 ml_training.learning_runtime_manifest(與 facade
# 的 _source_compatibility_receipt_errors 同一形,避免同模組被載成兩份)。
# W5 review P2-E:該路徑**不**在 import 期入 sys.path——本葉在 engine-scanner 的 runtime
# import 閉包內,於 import 期把 ``program_code`` 加進 top-level namespace 會讓 broker/
# exchange/dashboard 等套件在 scanner 進程中可被匯入,那必須是決策而非副作用(§10.1.1 #4)。
# 改由 schema_core 的 ``program_code_on_path`` 在需要它的函式內開窗、離開時收回自己那筆。

# 唯讀消費 S2.4 §9.1 SSHSIG 信任根與離線公鑰驗簽基元(同 facade 姿態;不反向匯入 facade)。
import agent_governance_aiml_trusted_host as _trusted_host  # noqa: E402

from aiml_gate_receipt_schema_core import (  # noqa: E402
    _canonical_bytes,
    _now_text,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
    S2_3_SEALED_BUILD_RECEIPT_REL,
    S2_4_COMMITTED_SOURCE_IDENTITY_PATHS,
    S2_4_DEPENDENCY_REFRESH_CLASSES,
    S2_4_NEVER_REFRESHABLE_EVIDENCE,
    S2_4_NEVER_REFRESHABLE_SCHEMAS,
    _DEPENDENCY_EVIDENCE_SUCCESS_STATUSES,
    committed_source_identity_digests,
    dependency_semantic_subject_values,
    materialize_commit_paths,
    owned_path_blob_projection,
    owned_scope_worktree_delta,
    program_code_on_path,
    recompute_dependency_semantic_subjects,
    resolve_commit_head,
    resolve_facade as _resolve_facade,
)
from aiml_gate_receipt_classifiers import (  # noqa: E402
    AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2,
)


# --------------------------------------------------------------------------- #
# S2.4(WP4·W1·CP3)per-row ABI 綁定 + aggregate-lineage 謂詞。此區只「讀」CP1 凍結的
# v2 矩陣(digest sha256:01d3062c…3c64 不動),在 CP2 的 closed-schema 之上再導出 §4:251-257
# 逐行 ABI 綁定,並補齊 JSON schema 無法表達的次序/唯一/exact-set/lineage 契約。全為離線
# 結構驗:「不」執行任何東西、「不」斷言 runtime/production PASS,九 authority 不受影響。
# --------------------------------------------------------------------------- #
# 五個 APPLY row 的 §4 class 次序(§5.1 required order)。兩個前置(HOST_CAPABILITY_PROBE /
# LEARNING_RUNTIME_PREPARE)不是 install-plan component,故不在此序;它們走各自 probe/prepare
# core+intent(見 s2_4_capability_probe_intent_v1 / s2_4_prepare_intent_v1)。
S2_4_APPLY_ROW_CLASS_ORDER = (
    "HOST_IDENTITY_INSTALL",
    "PG_ROLE_ACL_MIGRATION",
    "CREDENTIAL_INSTALL",
    "LEARNING_RUNTIME",
    "ENGINE_SCANNER",
)
# §10.1 W1 schemas-dir additions:29 支 s2_4_* + v2 classifier + topology/network 三支。
# (2026-07-27 §10.1.1 治理搬移:逐位元組自 facade 遷入本葉以守住 2000 行上限,facade 以
# ``_W1_SCHEMA_FILENAMES`` 逐名 re-export,值與次序不動 → W1 owned-path 投影 digest 不變。
# 這是 **W1** 波的歷史加列清單,不是「當前 S2.4 schema 全集」——W5 新增的 §9.2 refresh
# schema 刻意**不**入此列,否則會把後來的變更倒寫進 W1 的 exported ABI。)
S2_4_W1_SCHEMA_FILENAMES = (
    "aiml_component_effect_classification_v2.schema.json",
    "network_sandbox_capability_attestation_v1.schema.json",
    "pg_topology_attestation_v1.schema.json",
    "pg_topology_runtime_guard_v1.schema.json",
    "s2_4_authorization_replay_ledger_v1.schema.json",
    "s2_4_capability_probe_core_v1.schema.json",
    "s2_4_capability_probe_effect_receipt_v1.schema.json",
    "s2_4_capability_probe_intent_v1.schema.json",
    "s2_4_capability_probe_journal_v1.schema.json",
    "s2_4_capability_probe_postcheck_v1.schema.json",
    "s2_4_capability_probe_rollback_v1.schema.json",
    "s2_4_component_effect_intent_v1.schema.json",
    "s2_4_component_effect_postcheck_v1.schema.json",
    "s2_4_component_effect_result_v1.schema.json",
    "s2_4_component_effect_rollback_v1.schema.json",
    "s2_4_install_effect_receipt_v1.schema.json",
    "s2_4_install_journal_v1.schema.json",
    "s2_4_install_plan_core_v1.schema.json",
    "s2_4_install_plan_v1.schema.json",
    "s2_4_install_postcheck_v1.schema.json",
    "s2_4_install_rollback_v1.schema.json",
    "s2_4_install_step_result_v1.schema.json",
    "s2_4_operator_authorization_v1.schema.json",
    "s2_4_pg_hba_delta_v1.schema.json",
    "s2_4_prepare_core_v1.schema.json",
    "s2_4_prepare_effect_receipt_v1.schema.json",
    "s2_4_prepare_intent_v1.schema.json",
    "s2_4_prepare_journal_v1.schema.json",
    "s2_4_prepare_postcheck_v1.schema.json",
    "s2_4_prepare_rollback_v1.schema.json",
    "s2_4_prepared_install_bundle_v1.schema.json",
    "s2_4_source_admission_receipt_v1.schema.json",
    "s2_4_wave_exit_receipt_v1.schema.json",
)
# §4 逐行 required_intent_fields 的三個 common token(plan/pre_state/expiry)落在
# s2_4_component_effect_intent_v1 的頂層欄位;全部 5 個 APPLY 矩陣列都含這三 token。
_S2_4_APPLY_INTENT_COMMON_TOKEN_FIELDS = {
    "plan": "install_plan_digest",
    "pre_state": "pre_state_digest",
    "expiry": "expires_at",
}
# 每個 APPLY class 的 class-specific §4 token -> intent 的 required_intent_fields 物件鍵。此表把
# §4 prose token 逐一綁到具體 intent 欄位鍵,使 derive_component_intent_binding 能「重建」該 intent
# 的完整 §4 token 集並與凍結 v2 矩陣列比對。它同時是 schema 縫的封口點:intent schema 的
# required_intent_fields $def 以 additionalProperties:false 列全 12 個 digest 鍵為「可選」,只在
# allOf 條件式強制「該類必含」某些鍵,卻不禁一個 HOST intent 夾帶 PG 的 topology_attestation_digest;
# 這裡以「exact 鍵集」把跨類夾帶的縫關閉。此表逐位元組對齊凍結矩陣列的 token(見下方
# _assert 於 import 期不做,改由 test #1 斷言),矩陣本身仍 CP1-frozen、此處只讀。
_S2_4_APPLY_INTENT_CLASS_TOKEN_FIELDS = {
    "HOST_IDENTITY_INSTALL": {
        "uid_gid_directory_manifest": "uid_gid_directory_manifest_digest",
    },
    "PG_ROLE_ACL_MIGRATION": {
        "topology": "topology_attestation_digest",
        "acl_manifest": "acl_manifest_digest",
        "pg_migration_permit": "pg_migration_permit_digest",
        "admin_handle_descriptor": "admin_handle_descriptor_digest",
    },
    "CREDENTIAL_INSTALL": {
        "credential_name": "credential_name",
        "encrypted_blob_digest": "encrypted_blob_digest",
        "host_identity": "host_identity_digest",
    },
    "LEARNING_RUNTIME": {
        "prepare_receipt": "prepare_effect_receipt_digest",
        "base_app_launch_manifests_and_target_paths": "base_app_launch_target_manifest_digest",
    },
    "ENGINE_SCANNER": {
        "unit_policy_evidence_manifests": "unit_policy_evidence_manifest_digest",
        "inactive_post_state": "inactive_post_state_digest",
    },
}


def derive_component_intent_binding(intent: Any) -> dict[str, Any]:
    """從一份 s2_4_component_effect_intent_v1 導出其 §4 逐行 ABI 綁定並強制 exact intent-field 集。

    給定一份 APPLY-row intent artifact,依凍結的 v2 矩陣(CP1)把其 ``component_effect_class``
    綁到 exact ``adapter_id`` / ``actor_node_id`` / ``independent_postcheck_node_id`` /
    ``recovery_contract``(rollback 契約 id)/ ``adapter_binding_status``,並重建該 intent 的完整
    §4 required_intent_fields token 集——頂層 install_plan_digest/pre_state_digest/expires_at 三個
    common token 加上 required_intent_fields 物件的 class-specific 鍵——要求其恰等於
    ``sorted(矩陣列["required_intent_fields"])``。caller 無法供給或降級 adapter/actor/postcheck/
    rollback:它們由矩陣導出,此函式即權威(swapped adapter/downgraded status 無從發生於此 intent)。

    以下任一縫皆 raise ``ValueError``(typed 拒絕):
      * ``component_effect_class`` 不是五個 APPLY row 之一(未知/前置類/缺失);
      * required_intent_fields 夾帶跨類額外鍵(schema additionalProperties 縫)或缺 class 必要鍵;
      * 頂層 plan/pre_state/expiry 任一缺失(schema 已 required;防禦式)。
    """

    if not isinstance(intent, dict):
        raise ValueError("component effect intent must be an object")
    declared_class = intent.get("component_effect_class")
    class_token_fields = _S2_4_APPLY_INTENT_CLASS_TOKEN_FIELDS.get(str(declared_class))
    matrix_row = AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2.get(str(declared_class))
    if class_token_fields is None or matrix_row is None:
        raise ValueError(
            f"component effect intent class {declared_class!r} is not one of the five "
            "S2.4 APPLY rows"
        )
    declared_intent_fields = intent.get("required_intent_fields")
    if not isinstance(declared_intent_fields, dict):
        raise ValueError(
            "component effect intent required_intent_fields must be an object"
        )
    # exact class-specific 鍵集(關閉 schema 允許跨類夾帶額外 digest 鍵的縫)。
    expected_keys = set(class_token_fields.values())
    present_keys = set(declared_intent_fields)
    if present_keys != expected_keys:
        extra = sorted(present_keys - expected_keys)
        missing = sorted(expected_keys - present_keys)
        raise ValueError(
            f"{declared_class} required_intent_fields do not match the exact §4 row "
            f"set (extra={extra}, missing={missing})"
        )
    # 三個 common token 必在頂層(schema 已 required;防禦式再驗)。
    missing_common = sorted(
        token
        for token, field in _S2_4_APPLY_INTENT_COMMON_TOKEN_FIELDS.items()
        if field not in intent
    )
    if missing_common:
        raise ValueError(
            f"{declared_class} intent is missing top-level field(s) for §4 common "
            f"token(s) {missing_common}"
        )
    # 重建完整 §4 token 集並與凍結矩陣列比對(此即 per-row ABI 綁定的等式核心)。
    reconstructed = set(_S2_4_APPLY_INTENT_COMMON_TOKEN_FIELDS) | set(class_token_fields)
    if sorted(reconstructed) != sorted(matrix_row["required_intent_fields"]):
        raise ValueError(
            f"{declared_class} reconstructed §4 intent-field set does not equal the "
            "frozen v2 matrix row"
        )
    return {
        "component_effect_class": declared_class,
        "adapter_id": matrix_row["adapter_id"],
        "actor_node_id": matrix_row["actor_node_id"],
        "independent_postcheck_node_id": matrix_row["independent_postcheck_node_id"],
        "recovery_contract": matrix_row["recovery_contract"],
        "adapter_binding_status": matrix_row["adapter_binding_status"],
        "required_intent_fields": list(matrix_row["required_intent_fields"]),
    }


def _s2_4_route_core_rederivation_errors(
    artifact: dict[str, Any], *, id_field: str, id_prefix: str
) -> list[str]:
    """§5.1:route-class artifact 攜帶 unsigned core 時,中央閘再導出 core_digest/derived id/self_digest。

    ``core_digest = canonical_digest(core)``;``derived_id = id_prefix + hex(core_digest)``。
    core 是被簽名對象,其 digest 導 id,故 core「不」含任何導出 id/self_digest(schema 已以
    additionalProperties:false 保證,此處為再導出而非自證)。
    """

    errors: list[str] = []
    core = artifact.get("core")
    if not isinstance(core, dict):
        return ["route-class artifact core must be an object"]
    expected_core_digest = canonical_digest(core)
    if artifact.get("core_digest") != expected_core_digest:
        errors.append("route-class core_digest does not bind the canonical core")
    expected_id = id_prefix + expected_core_digest.split(":", 1)[1]
    if artifact.get(id_field) != expected_id:
        errors.append(f"{id_field} does not re-derive from the core digest")
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        errors.append("route-class artifact self_digest is invalid")
    return errors


def _s2_4_install_plan_apply_rows_errors(artifact: dict[str, Any]) -> list[str]:
    """install plan 的 core.apply_rows 與 route_surface.apply_rows 必為五類 exact 次序(schema 無 prefixItems)。"""

    errors: list[str] = []
    core = artifact.get("core")
    if isinstance(core, dict) and isinstance(core.get("apply_rows"), list):
        core_classes = tuple(
            row.get("component_effect_class")
            for row in core["apply_rows"]
            if isinstance(row, dict)
        )
        if core_classes != S2_4_APPLY_ROW_CLASS_ORDER:
            errors.append(
                "install plan core apply_rows are not the five required classes in "
                f"§5.1 order (got {list(core_classes)})"
            )
    surface = artifact.get("route_surface")
    if isinstance(surface, dict) and isinstance(surface.get("apply_rows"), list):
        if tuple(surface["apply_rows"]) != S2_4_APPLY_ROW_CLASS_ORDER:
            errors.append(
                "install plan route_surface apply_rows are not the five required "
                f"classes in §5.1 order (got {surface['apply_rows']})"
            )
    return errors


def derive_install_lineage_status(
    install_effect_receipt: Any, *, install_plan: Any = None
) -> dict[str, Any]:
    """離線結構謂詞:聚合協調 install 交易的 lineage 是否 SATISFIED(§4:259-264)。

    僅做結構/次序/唯一/綁定驗——「不」執行任何東西、「不」斷言 runtime PASS。JSON schema 無
    ``prefixItems`` 故無法強制五 APPLY row 的 class 次序與唯一,亦無法保證兩 scoped probe receipt
    digest 相異;此謂詞補齊,消費 ``s2_4_install_effect_receipt_v1``(可選再交叉綁 ``s2_4_install_plan_v1``):

      * 恰 5 個 APPLY row,class 依序 == ``S2_4_APPLY_ROW_CLASS_ORDER`` 且 unique-by-class
        (缺一列/重複類/亂序/多第六列皆非 SATISFIED);
      * 兩 scoped capability-probe receipt digest(PREPARE_SANDBOX + INSTALLED_UNIT)存在且相異
        (同一 digest = 同一 probe 充當兩 scope = 未 distinct);
      * PREPARE 結果 + PREPARE postcheck digest 存在;
      * 一條逆向補償鏈 digest 存在。
    交叉綁定 plan 時再驗 plan_id/idempotency_key 與 receipt 一致、plan.core.apply_rows 五類 exact 次序。
    回 ``{"status": "SATISFIED"|"NOT_SATISFIED", "reasons": [...]}``;此謂詞絕不簽發 runtime/production 判定。
    """

    reasons: list[str] = []
    if not isinstance(install_effect_receipt, dict):
        return {
            "status": "NOT_SATISFIED",
            "reasons": ["install effect receipt must be an object"],
        }
    receipt = install_effect_receipt

    rows = receipt.get("apply_row_results")
    if not isinstance(rows, list):
        reasons.append("install lineage apply_row_results must be a list")
        classes: list[Any] = []
    else:
        classes = [
            row.get("component_effect_class") if isinstance(row, dict) else None
            for row in rows
        ]
    if len(classes) != 5:
        reasons.append(
            f"install lineage requires exactly five APPLY rows (got {len(classes)})"
        )
    duplicated = sorted(
        {c for c in classes if c is not None and classes.count(c) > 1}
    )
    if duplicated:
        reasons.append(
            f"install lineage APPLY rows contain duplicated class(es) {duplicated}"
        )
    if len(classes) == 5 and not duplicated:
        if set(classes) != set(S2_4_APPLY_ROW_CLASS_ORDER):
            reasons.append(
                "install lineage APPLY rows are not exactly the five required classes"
            )
        elif tuple(classes) != S2_4_APPLY_ROW_CLASS_ORDER:
            reasons.append(
                "install lineage APPLY rows are out of the required §5.1 class order "
                f"(got {classes}, want {list(S2_4_APPLY_ROW_CLASS_ORDER)})"
            )

    prepare_sandbox = receipt.get("prepare_sandbox_probe_receipt_digest")
    installed_unit = receipt.get("installed_unit_probe_receipt_digest")
    if not isinstance(prepare_sandbox, str) or not isinstance(installed_unit, str):
        reasons.append(
            "install lineage requires two scoped capability-probe receipt digests "
            "(PREPARE_SANDBOX + INSTALLED_UNIT)"
        )
    elif prepare_sandbox == installed_unit:
        reasons.append(
            "install lineage scoped probe receipts share one digest; the "
            "PREPARE_SANDBOX and INSTALLED_UNIT scopes must be distinct"
        )
    for field, label in (
        ("prepare_result_digest", "PREPARE result"),
        ("prepare_postcheck_digest", "PREPARE postcheck"),
        ("reverse_compensation_chain_digest", "reverse compensation chain"),
    ):
        if not isinstance(receipt.get(field), str):
            reasons.append(f"install lineage requires a {label} digest")

    if install_plan is not None:
        reasons.extend(_install_lineage_plan_binding_errors(install_plan, receipt))

    return {
        "status": "SATISFIED" if not reasons else "NOT_SATISFIED",
        "reasons": reasons,
    }


def _install_lineage_plan_binding_errors(
    install_plan: Any, receipt: dict[str, Any]
) -> list[str]:
    """交叉綁定:plan_id/idempotency_key 與 receipt 一致 + plan.core.apply_rows 五類 exact 次序。"""

    errors: list[str] = []
    if not isinstance(install_plan, dict):
        return ["install lineage plan cross-binding requires a plan object"]
    if install_plan.get("plan_id") != receipt.get("plan_id"):
        errors.append("install lineage plan_id does not match the effect receipt")
    if install_plan.get("idempotency_key") != receipt.get("idempotency_key"):
        errors.append(
            "install lineage plan idempotency_key does not match the effect receipt"
        )
    errors.extend(_s2_4_install_plan_apply_rows_errors(install_plan))
    return errors


# --------------------------------------------------------------------------- #
# S2.4(WP4·W1·CP4)四 operator-authorization 信任 profile + 離線驗證分支(§9.1)。
#
# 四個 domain-separated profile(capability-probe / prepare / apply-aggregate / pg-migration)
# 共用**同一把**已審 §9.1 Ed25519 實體信任根(公鑰 == trusted-host 的 TRUSTED_EXECUTION_PUBLIC_KEY,
# 必符指紋 SHA256:uGJ9veN7PoE6BBgfsSP2aiMndrwgbt7o/7/YfdzNzCQ),以 **identity + namespace** 做
# domain separation:一張以某 profile namespace 簽的授權於別 profile 下因 identity/namespace 不符
# 而被拒。此常量是 v2 profile 契約的 code-owned SSOT(routing/registry/closure 於 CP5 再導出並綁
# canonical_digest(projection),cross-consumer test 斷言各投影 digest 相等)。
#
# 誠實界線(**只證離線結構/完整性/信任根綁定,不證 runtime 真偽**):此區呼叫 out-of-scope 的
# agent_governance_aiml_trusted_host 驗證基元對 pinned 公鑰做**離線公鑰驗簽**——證「此 payload 由 §9.1
# 私鑰持有者簽過(簽章完整 + 綁到信任根)」,但**不**證真 operator 於 runtime 對真語義 payload
# (綁真 plan/probe 值 + replay-ledger 消費 + 平台背書)簽了——後者屬 W6A/W6B EFFECT session。九
# authority 不受影響;凍結 S0.3 classifier / v1·v2 matrix / PROGRAM_SCHEMA_PATHS 一律「只讀不改」。
#
# §9 TTL 註記(delta):§9.1 只數值釘定 APPLY/PG 上限 900 秒、skew 60 秒;PROBE/PREPARE 僅以不等式
# (probe+cleanup+postcheck+safety_margin / fetch+build+postcheck+rollback+safety_margin)描述「自有
# 有界預算」而未給數字。此處對 PROBE/PREPARE 採 §9.1 全域「Maximum … TTL is 15 minutes」同一 900 秒
# 保守上限(skew 60 秒),釘入 profile digest;真正更緊的 per-probe/per-prepare 預算屬 W6 EFFECT 收緊。
# --------------------------------------------------------------------------- #
S2_4_OPERATOR_AUTHORIZATION_SCHEMA_VERSION = "s2_4_operator_authorization_v1"
# §9.1 實體信任根:公鑰/指紋沿用 trusted-host 已審常量(import 期綁定;測試以 monkeypatch 這兩個
# **本模組**副本注入丟棄式鑰,不觸碰 trusted-host 模組本身)。
S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY = _trusted_host.TRUSTED_EXECUTION_PUBLIC_KEY
S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT = _trusted_host.EXPECTED_EXECUTION_SIGNER_FINGERPRINT
S2_4_AUTHORIZATION_PROFILES: dict[str, dict[str, Any]] = {
    "capability_probe": {
        "profile_identity": "aiml-s2-capability-probe-operator-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-capability-probe",
        # §9.1 CAPABILITY PROBE ordered payload(follow §9.1:用 `scope` 非 task 稿的
        # `probe_scope`;用 `output_derived_unit_digest_or_null` 非 `output_unit_digest_or_null`)。
        "payload_fields": (
            "domain", "authorization_id", "probe_core_digest", "probe_id",
            "scope", "source_head", "target_host", "transient_unit_property_digest",
            "output_derived_unit_digest_or_null", "cleanup_rollback_digest",
            "issued_at", "expires_at",
        ),
        "max_ttl_seconds": 900,
        "skew_seconds": 60,
    },
    "prepare": {
        "profile_identity": "aiml-s2-install-prepare-operator-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-install-prepare",
        "payload_fields": (
            "domain", "authorization_id", "prepare_core_digest", "prepare_id",
            "source_head", "target_host", "prepare_sandbox_probe_receipt_digest",
            "staging_parent_identity", "prepare_rollback_digest",
            "issued_at", "expires_at",
        ),
        "max_ttl_seconds": 900,
        "skew_seconds": 60,
    },
    "apply_aggregate": {
        "profile_identity": "aiml-s2-install-operator-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-install",
        "payload_fields": (
            "domain", "authorization_id", "plan_core_digest", "plan_id",
            "source_head", "target_host", "prepare_receipt_digest",
            "topology_pre_digest", "installed_unit_probe_receipt_digest",
            "hba_delta_digest", "pre_state_digest", "aggregate_rollback_digest",
            "idempotency_key", "issued_at", "expires_at",
        ),
        "max_ttl_seconds": 900,
        "skew_seconds": 60,
    },
    "pg_migration": {
        "profile_identity": "aiml-s2-pg-migration-operator-v1",
        "signature_namespace": "arcane-equilibrium-aiml-s2-pg-migration",
        "payload_fields": (
            "domain", "authorization_id", "plan_core_digest", "plan_id",
            "source_head", "target_host", "topology_pre_digest",
            "installed_unit_probe_receipt_digest", "pg_acl_digest", "hba_delta_digest",
            "pg_pre_state_digest", "pg_rollback_digest", "idempotency_key",
            "issued_at", "expires_at",
        ),
        "max_ttl_seconds": 900,
        "skew_seconds": 60,
    },
}
_S2_4_PROFILE_BY_IDENTITY = {
    row["profile_identity"]: row for row in S2_4_AUTHORIZATION_PROFILES.values()
}
# S2.4-AMEND-1(§9.1 profile threading;obligation 26):class→artifact 解析除 schema_version
# 外再綁一個**判別欄位**。四個 permit 列共用同一份 s2_4_operator_authorization_v1、兩個
# capability-probe 列共用同一份 probe effect receipt(many-to-one),唯一能把「這一列所指
# 之物」分開的是 §9.1 profile_identity / probe_scope。值由凍結的
# :data:`S2_4_AUTHORIZATION_PROFILES` **導出**(絕不手抄字串,故不可能與 byte-frozen 的
# §9.1 profiles digest 漂移);probe 兩列的 scope 是 schema required 欄位 ``probe_scope``。
# 表**外**的 class(四個可刷新族、PG_TOPOLOGY_ATTESTATION、PREPARED_BUNDLE、
# S2_0_EFFECT_RECEIPT)各自的 schema_version 已一對一,無需判別欄位。
S2_4_EVIDENCE_CLASS_DISCRIMINATORS: dict[str, tuple[str, str]] = {
    "APPLY_AGGREGATE_AUTHORIZATION": (
        "profile_identity",
        S2_4_AUTHORIZATION_PROFILES["apply_aggregate"]["profile_identity"],
    ),
    "PREPARE_AUTHORIZATION": (
        "profile_identity", S2_4_AUTHORIZATION_PROFILES["prepare"]["profile_identity"],
    ),
    "PG_MIGRATION_AUTHORIZATION": (
        "profile_identity",
        S2_4_AUTHORIZATION_PROFILES["pg_migration"]["profile_identity"],
    ),
    "CAPABILITY_PROBE_AUTHORIZATION": (
        "profile_identity",
        S2_4_AUTHORIZATION_PROFILES["capability_probe"]["profile_identity"],
    ),
    "CAPABILITY_PROBE_RECEIPT_INSTALLED_UNIT": ("probe_scope", "INSTALLED_UNIT"),
    "CAPABILITY_PROBE_RECEIPT_PREPARE_SANDBOX": ("probe_scope", "PREPARE_SANDBOX"),
}
_SSH_SIGNATURE_ARMOR_MARKERS = (
    "-----BEGIN SSH SIGNATURE-----",
    "-----END SSH SIGNATURE-----",
)


# --------------------------------------------------------------------------- #
# S2.4(WP4·W4a)PERMIT_PLAN_BINDING —— authorization_id 由 profile 具名的 exact payload 導出。
#
# W3 記錄的 obligation:授權物件只帶 ``authorization_id`` 與 payload_fields 的**名字**,從不帶
# plan/intent 的**值**,任何閘也不從 intent 再導出 ``authorization_id``——故一張簽好的 permit 在
# TTL 內可授權該類別的**任意** intent,§10.5 #36「rejected by profile-specific SSHSIG」由構造上
# 無法滿足。W4a 的修法:
#
#   payload_binding      = {field: 該 field 的 exact 值 | field ∈ payload_fields \ {authorization_id}}
#   authorization_id     = canonical_digest({domain, profile_identity, signature_namespace,
#                                            payload_fields, payload_binding})
#
# 兩層閘缺一不可:
#   (a) :func:`_s2_4_authorization_payload_binding_errors`(無條件,由 CP4 授權驗證呼叫)——
#       ``authorization_id`` 必須由**它自己攜帶的** payload_binding 再導出,且 payload_binding 的
#       鍵集恰為 profile 的 payload_fields 減 authorization_id,``domain`` 必等於簽章 namespace、
#       ``issued_at``/``expires_at`` 必等於頂層值。permit 因此**不可**被重新指向另一份 payload;
#   (b) :func:`derive_permit_plan_binding_status`(每個消費閘各自呼叫)——payload_binding 必須
#       逐欄等於消費端**獨立再導出**的期望值(probe/prepare 由 intent core 全量導出;APPLY row
#       由 intent 的 plan 參照導出)。intent 替換於是在 driver 接觸之前即 AUTHORIZATION_REJECTED。
#
# ``authorization_id`` 的 domain 常量把此導出與任何別的 digest 空間分開(同一組值在別的語義下
# 不會碰撞出同一 id)。誠實界線不變:此為離線結構/綁定驗,**不**認證真 operator 於 runtime 簽了
# 真語義 payload(W6A/W6B),九 authority 不受影響。
# --------------------------------------------------------------------------- #
S2_4_AUTHORIZATION_ID_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-operator-authorization-id-v1"
)
# payload_fields 中唯一「自指」的 token:id 由其餘 payload 導出,故不可含自己。
S2_4_AUTHORIZATION_ID_SELF_FIELD = "authorization_id"
# payload_binding 中必須與頂層授權欄位逐位元組一致的兩個 token(§9.1 payload 尾二項)。
_S2_4_AUTHORIZATION_TOP_LEVEL_BOUND_FIELDS = ("issued_at", "expires_at")
# payload_binding 中唯一允許為 null 的 token(§9.1 CAPABILITY PROBE payload)。
_S2_4_AUTHORIZATION_NULLABLE_BINDING_FIELDS = ("output_derived_unit_digest_or_null",)
PERMIT_PLAN_BINDING_STATUS_VERIFIED = "PERMIT_PLAN_BINDING_VERIFIED"
PERMIT_PLAN_BINDING_STATUS_REJECTED = "PERMIT_PLAN_BINDING_REJECTED"


def authorization_payload_binding_fields(profile: Any) -> tuple[str, ...]:
    """該 profile 的 payload_binding 鍵集(§9.1 ordered payload 減去自指的 authorization_id)。

    ``profile`` 可為 :data:`S2_4_AUTHORIZATION_PROFILES` 的鍵(``capability_probe`` …)或
    ``profile_identity`` 字串;都不是即 raise ``ValueError``(fail-closed,絕不回空集)。
    """

    row = S2_4_AUTHORIZATION_PROFILES.get(str(profile)) or _S2_4_PROFILE_BY_IDENTITY.get(
        str(profile)
    )
    if row is None:
        raise ValueError(
            f"{profile!r} is not one of the four §9.1 S2.4 authorization profiles"
        )
    return tuple(
        field
        for field in row["payload_fields"]
        if field != S2_4_AUTHORIZATION_ID_SELF_FIELD
    )


def s2_4_authorization_identity_digest(
    *,
    profile_identity: Any,
    signature_namespace: Any,
    payload_fields: Any,
    payload_binding: Any,
) -> str:
    """§9.1 的 ``authorization_id`` 導出(domain-separated;簽章附上之前即可算)。

    id 綁 profile 身分 + 簽章 namespace + ordered payload token list + 每個 token 的 exact 值;
    任一項改動(換 plan core digest、換 probe scope、換 host、改 TTL 窗)都得到不同的 id。
    """

    return canonical_digest({
        "domain": S2_4_AUTHORIZATION_ID_DOMAIN,
        "profile_identity": profile_identity,
        "signature_namespace": signature_namespace,
        "payload_fields": list(payload_fields or []),
        "payload_binding": payload_binding,
    })


def derive_authorization_id(authorization: Any) -> str:
    """從一份(未簽或已簽)授權物件再導出其 ``authorization_id``。"""

    if not isinstance(authorization, dict):
        raise ValueError("authorization must be an object")
    return s2_4_authorization_identity_digest(
        profile_identity=authorization.get("profile_identity"),
        signature_namespace=authorization.get("signature_namespace"),
        payload_fields=authorization.get("payload_fields"),
        payload_binding=authorization.get("payload_binding"),
    )


def build_s2_4_operator_authorization(
    profile_key: str,
    *,
    payload_binding: dict[str, Any],
    issued_at: str,
    expires_at: str,
) -> dict[str, Any]:
    """組出**未簽**的授權物件,其 ``authorization_id`` 已由 payload_binding 導出(§9.1 次序)。

    ``payload_binding`` 必須恰含該 profile 的 payload token(減 authorization_id);``domain``
    與 ``issued_at``/``expires_at`` 由本函式填入 code-owned 值,caller 無從讓三者與頂層不一致。
    簽名者接著對 :func:`_s2_4_operator_authorization_signed_bytes` 的 canonical bytes 簽 SSHSIG。
    """

    profile = S2_4_AUTHORIZATION_PROFILES.get(profile_key)
    if profile is None:
        raise ValueError(f"{profile_key!r} is not an S2.4 authorization profile key")
    expected = set(authorization_payload_binding_fields(profile_key))
    binding = dict(payload_binding or {})
    binding["domain"] = profile["signature_namespace"]
    binding["issued_at"] = issued_at
    binding["expires_at"] = expires_at
    if set(binding) != expected:
        raise ValueError(
            f"{profile_key} payload_binding must be exactly {sorted(expected)} "
            f"(got {sorted(binding)})"
        )
    artifact: dict[str, Any] = {
        "schema_version": S2_4_OPERATOR_AUTHORIZATION_SCHEMA_VERSION,
        "profile_identity": profile["profile_identity"],
        "signature_namespace": profile["signature_namespace"],
        "authorization_id": "",
        "payload_fields": list(profile["payload_fields"]),
        "payload_binding": binding,
        "issued_at": issued_at,
        "expires_at": expires_at,
    }
    artifact["authorization_id"] = derive_authorization_id(artifact)
    return artifact


def _s2_4_authorization_payload_binding_errors(artifact: dict[str, Any]) -> list[str]:
    """PERMIT_PLAN_BINDING 第 (a) 層:permit 必須綁到它自己攜帶的 exact payload。"""

    profile = _S2_4_PROFILE_BY_IDENTITY.get(artifact.get("profile_identity"))
    if profile is None:
        return []  # profile 解析失敗已由呼叫端回報,不重複。
    errors: list[str] = []
    binding = artifact.get("payload_binding")
    if not isinstance(binding, dict):
        return [
            "s2_4 operator authorization payload_binding must be an object carrying the "
            "exact signed value of every payload field except authorization_id "
            "(a permit that names fields without binding their values authorizes any "
            "intent of its class inside its TTL)"
        ]
    expected_fields = set(
        authorization_payload_binding_fields(profile["profile_identity"])
    )
    present = set(str(key) for key in binding)
    if present != expected_fields:
        errors.append(
            "s2_4 operator authorization payload_binding key set is not the profile's "
            f"exact §9.1 payload minus authorization_id (extra="
            f"{sorted(present - expected_fields)}, missing="
            f"{sorted(expected_fields - present)})"
        )
    for field, value in sorted(binding.items()):
        if value is None and str(field) not in _S2_4_AUTHORIZATION_NULLABLE_BINDING_FIELDS:
            errors.append(
                f"s2_4 operator authorization payload_binding[{field!r}] must not be null"
            )
    if "domain" in binding and binding.get("domain") != profile["signature_namespace"]:
        errors.append(
            "s2_4 operator authorization payload_binding['domain'] is not the profile's "
            "signature namespace (§9.1 domain separation)"
        )
    for field in _S2_4_AUTHORIZATION_TOP_LEVEL_BOUND_FIELDS:
        if field in binding and binding.get(field) != artifact.get(field):
            errors.append(
                f"s2_4 operator authorization payload_binding[{field!r}] does not equal the "
                "top-level authorization field (the signed window must be the recorded window)"
            )
    if not errors and artifact.get("authorization_id") != derive_authorization_id(artifact):
        errors.append(
            "s2_4 operator authorization authorization_id does not re-derive from its own "
            "profile/namespace/payload_fields/payload_binding (§9.1: the id is derived from "
            "the unsigned payload before the SSHSIG is attached)"
        )
    return errors


def derive_permit_plan_binding_status(
    authorization: Any,
    *,
    expected_payload_binding: Any,
    profile_key: Any = None,
) -> dict[str, Any]:
    """PERMIT_PLAN_BINDING 第 (b) 層:permit 是否綁到**這一份** intent/plan(§10.5 #36)。

    ``expected_payload_binding`` 是消費閘從 intent core / install plan **獨立再導出**的
    ``{payload field: 期望值}``(可為 profile payload 的子集——消費端只比對它自己能導出的欄位;
    它導不出的欄位仍由第 (a) 層釘死在 permit 的 id 內,故 permit 整體仍只綁一份 payload)。

    回 ``{"status": PERMIT_PLAN_BINDING_VERIFIED|PERMIT_PLAN_BINDING_REJECTED, "reasons": [...],
    "derived_authorization_id": …}``。任一欄位不符、payload_binding 缺該欄位、id 不再導出、
    profile 不符即 REJECTED(絕不半通過)。
    """

    verdict: dict[str, Any] = {
        "status": PERMIT_PLAN_BINDING_STATUS_REJECTED,
        "reasons": [],
        "derived_authorization_id": None,
    }
    if not isinstance(authorization, dict):
        verdict["reasons"] = ["permit plan binding requires an authorization object"]
        return verdict
    if not isinstance(expected_payload_binding, dict) or not expected_payload_binding:
        verdict["reasons"] = [
            "permit plan binding requires a non-empty independently derived expected "
            "payload binding (an empty expectation would authorize any intent)"
        ]
        return verdict
    reasons = list(_s2_4_authorization_payload_binding_errors(authorization))
    if profile_key is not None:
        profile = S2_4_AUTHORIZATION_PROFILES.get(str(profile_key))
        if profile is None:
            reasons.append(f"{profile_key!r} is not an S2.4 authorization profile key")
        elif authorization.get("profile_identity") != profile["profile_identity"]:
            reasons.append(
                f"permit profile_identity is not the required {profile['profile_identity']}"
            )
    binding = authorization.get("payload_binding")
    if isinstance(binding, dict):
        for field in sorted(expected_payload_binding):
            expected_value = expected_payload_binding[field]
            if field not in binding:
                reasons.append(
                    f"permit payload_binding is missing {field!r}; the permit is not bound "
                    "to this plan/intent"
                )
            elif binding[field] != expected_value:
                reasons.append(
                    f"permit payload_binding[{field!r}] does not equal the independently "
                    "re-derived value for this plan/intent (intent substitution under one "
                    "signed permit is AUTHORIZATION_REJECTED, §10.5 #36)"
                )
    try:
        verdict["derived_authorization_id"] = derive_authorization_id(authorization)
    except ValueError as error:
        reasons.append(str(error))
    if reasons:
        verdict["reasons"] = reasons
        return verdict
    verdict["status"] = PERMIT_PLAN_BINDING_STATUS_VERIFIED
    return verdict


def s2_4_authorization_profiles_digest() -> str:
    """釘選四 §9.1 trust profile(identity/namespace/ordered payload/max-TTL/skew)為 canonical digest。

    任一 profile 的 identity/namespace 被悄悄重拼字、payload token 增刪/亂序、TTL 或 skew 被改動皆令此
    digest 漂移,被 CP4 test #17 的硬編釘選拒。此即 code-owned profile 契約的完整性錨。
    """

    return canonical_digest({
        key: {
            "profile_identity": row["profile_identity"],
            "signature_namespace": row["signature_namespace"],
            "payload_fields": list(row["payload_fields"]),
            "max_ttl_seconds": row["max_ttl_seconds"],
            "skew_seconds": row["skew_seconds"],
        }
        for key, row in S2_4_AUTHORIZATION_PROFILES.items()
    })


def _sshsig_armor_body_is_strict_base64(value: str) -> bool:
    """去 armor(剝 BEGIN/END 標記列 + 換行後串接)得純 body,判斷是否嚴格標準 base64。

    真 ``ssh-keygen -Y sign`` armor body 去 armor 後為合法標準 base64,``b64decode(validate=True)``
    成功;plaintext 憑證形(``password=…`` 的 ``=`` 落中段、``bearer\\nAAAA`` 長度不可解)一律失敗。
    非字串 / 空 body / 不可 decode 一律回 False(fail-closed)。
    """

    if not isinstance(value, str):
        return False
    body = "".join(
        line for line in value.split("\n") if line not in _SSH_SIGNATURE_ARMOR_MARKERS
    )
    if not body:
        return False
    try:
        base64.b64decode(body, validate=True)
    except (binascii.Error, ValueError):
        return False
    return True


def _s2_4_operator_authorization_signed_bytes(artifact: dict[str, Any]) -> bytes:
    """離線可重建的被簽 canonical payload:排除 ``sshsig_armored`` 與 ``self_digest`` 兩個後綁欄位。

    §9.1 的 ``domain || authorization_id || … `` 是 W6 runtime 真 operator 簽的**語義** payload(綁真
    plan/probe 值),離線中央閘拿不到那些值;此處對授權物件自身(除簽章與整合 digest 外)取 canonical
    bytes 作為被驗 payload,令 throwaway-key 正例能完整測 CODE 驗簽路徑而不冒充 runtime 真偽。build 端
    以同一投影簽章,故兩側逐位元組一致。
    """

    return _canonical_bytes({
        key: value
        for key, value in artifact.items()
        if key not in {"sshsig_armored", "self_digest"}
    })


def _s2_4_operator_authorization_errors(
    artifact: dict[str, Any], *, now: str | datetime | None = None
) -> list[str]:
    """離線驗一份 ``s2_4_operator_authorization_v1``(§9.1)——結構/完整性/信任根綁定,fail-closed。

    驗:(a) ``profile_identity`` 恰解析為一列 :data:`S2_4_AUTHORIZATION_PROFILES`;(b) ``signature_namespace``
    與 ``payload_fields`` 逐位元組等於該 profile 的 §9.1 值/ordered list;(c) ``self_digest`` 完整性;
    (d) armored SSHSIG 之 body 嚴格 base64 且 ≤16 KiB;(e) ``expires_at - issued_at`` ≤ profile max-TTL
    (strict ``>`` 拒)且 issued<expires 相干,now 若提供再驗 skew 內新鮮度;(f) 信任根綁定——pinned 公鑰
    指紋以 ``hmac.compare_digest`` 比對 pinned 指紋,且 armored SSHSIG 在 exact identity+namespace 下對
    pinned 公鑰驗過 canonical payload(呼叫 out-of-scope ``_verify_ssh_signature``,與 W0a operator 授權同姿態)。

    **誠實界線**:此離線公鑰驗簽只證簽章完整 + 信任根綁定,「不」宣稱真 operator 於 runtime 簽了真語義
    payload(W6A/W6B EFFECT)。任一項不符即回非空 reasons(絕不半通過)。
    """

    profile = _S2_4_PROFILE_BY_IDENTITY.get(artifact.get("profile_identity"))
    if profile is None:
        return [
            "s2_4 operator authorization profile_identity is not one of the four "
            "§9.1 trust profiles"
        ]
    errors: list[str] = []
    if artifact.get("signature_namespace") != profile["signature_namespace"]:
        errors.append(
            "s2_4 operator authorization signature_namespace does not match the profile"
        )
    if list(artifact.get("payload_fields") or []) != list(profile["payload_fields"]):
        errors.append(
            "s2_4 operator authorization payload_fields do not match the profile's "
            "exact §9.1 ordered list"
        )
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        errors.append("s2_4 operator authorization self_digest is invalid")
    # W4a PERMIT_PLAN_BINDING 第 (a) 層(無條件):id 必須由它自己攜帶的 exact payload 再導出。
    errors.extend(_s2_4_authorization_payload_binding_errors(artifact))
    armored = artifact.get("sshsig_armored")
    if not isinstance(armored, str) or len(armored.encode("utf-8")) > 16 * 1024:
        errors.append(
            "s2_4 operator authorization sshsig_armored must be a string of at "
            "most 16 KiB"
        )
    elif not _sshsig_armor_body_is_strict_base64(armored):
        errors.append(
            "s2_4 operator authorization sshsig_armored body is not strict base64"
        )
    try:
        issued = _parse_timestamp(artifact["issued_at"])
        expires = _parse_timestamp(artifact["expires_at"])
        if not issued < expires:
            errors.append(
                "s2_4 operator authorization issued_at must precede expires_at"
            )
        if (expires - issued).total_seconds() > profile["max_ttl_seconds"]:
            errors.append(
                "s2_4 operator authorization TTL exceeds the profile ceiling "
                f"({profile['max_ttl_seconds']}s)"
            )
        now_text = _now_text(now)
        if now_text is not None:
            current = _parse_timestamp(now_text)
            skew = profile["skew_seconds"]
            if not (issued.timestamp() - skew) <= current.timestamp() < expires.timestamp():
                errors.append(
                    "s2_4 operator authorization is not currently within its freshness window"
                )
    except (KeyError, TypeError, ValueError):
        errors.append("s2_4 operator authorization timestamps are invalid")
    # 信任根綁定:pinned 公鑰指紋必等於 pinned 指紋(hmac.compare_digest),且 armored SSHSIG 在 exact
    # identity+namespace 下對 pinned 公鑰驗過 canonical payload。經 resolve_facade() 讀「既載入」的
    # facade 信任根副本(頂層/ package 形皆命中同一物件,monkeypatch 縫在兩種 import 形下都逐字有效;
    # 硬編頂層名會在 package-form 行程惰性創建第二份 facade 拷貝而繞過 patch——E2 P1-1),
    # 驗簽基元一律取自 out-of-scope trusted-host(真驗證邏輯,不 monkeypatch)。
    _facade = _resolve_facade()
    public_key = _facade.S2_4_OPERATOR_TRUST_ROOT_PUBLIC_KEY
    fingerprint = _facade.S2_4_OPERATOR_TRUST_ROOT_FINGERPRINT
    try:
        actual_fingerprint = _trusted_host.ssh_public_key_fingerprint(public_key)
    except ValueError:
        actual_fingerprint = ""
    if not hmac.compare_digest(actual_fingerprint, fingerprint):
        errors.append("s2_4 operator authorization trust-root fingerprint mismatch")
    if isinstance(armored, str) and not _trusted_host._verify_ssh_signature(
        _s2_4_operator_authorization_signed_bytes(artifact),
        armored.encode("utf-8"),
        public_key=public_key,
        identity=profile["profile_identity"],
        namespace=profile["signature_namespace"],
    ):
        errors.append("s2_4 operator authorization SSH signature is invalid")
    return errors


# --------------------------------------------------------------------------- #
# S2.4(WP4·W1)§9.1 replay-ledger 語義驗 + 授權↔ledger 消費綁定謂詞。
#
# 兩層分工(對齊 schema description 與 CP4 測試既定行為):
#   * `_s2_4_replay_ledger_errors` —— ledger 自身的 hash-chain 完整性(逐 entry 重算
#     entry_digest、genesis prev=null、後續 prev 鏈住前一 entry_digest、seq == index、
#     self_digest)。「不」在此拒同一 authorization_id 的多筆消費——重複消費是「對某張授權
#     的消費裁決」,屬下方謂詞;裸 ledger 帶重複 id 但鏈完整仍是結構合法的歷史紀錄。
#   * `derive_authorization_replay_binding` —— 驗證層的消費語義(§9.1:Duplicate …
#     entries return AUTHORIZATION_REJECTED):一張授權必須引用「未被消費」的 replay id
#     才可消費;同 id 已消費(consuming twice)拒;同 id 綁到不同授權/plan
#     (same-id-different-plan,以 entry.authorization_digest ≠ 該授權 self_digest 判)拒。
#
# 誠實界線:此為離線驗證層語義,「不」是 runtime 消費(真 fsync/install-lock/append 屬
# W6A/W6B EFFECT);有效簽章 + 未消費 replay id 在 source lane 也「絕不」產生 applied/
# production 狀態——謂詞恆帶 typed `production_effect: EXTERNAL_VERIFICATION_PENDING`。
# --------------------------------------------------------------------------- #
def _s2_4_replay_ledger_errors(artifact: dict[str, Any]) -> list[str]:
    """離線重算一份 ``s2_4_authorization_replay_ledger_v1`` 的 hash-chain 完整性(fail-closed)。"""

    if not isinstance(artifact, dict):
        return ["replay ledger must be an object"]
    errors: list[str] = []
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        errors.append("replay ledger self_digest is invalid")
    entries = artifact.get("entries")
    if not isinstance(entries, list) or not entries:
        return errors + ["replay ledger entries must be a non-empty list"]
    previous_digest: Any = None
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"replay ledger entry[{index}] must be an object")
            return errors
        expected_digest = canonical_digest(
            {key: value for key, value in entry.items() if key != "entry_digest"}
        )
        if entry.get("entry_digest") != expected_digest:
            errors.append(
                f"replay ledger entry[{index}] entry_digest does not re-derive its "
                "canonical entry bytes"
            )
        if entry.get("seq") != index:
            errors.append(
                f"replay ledger entry[{index}] seq is out of order (append-only chain)"
            )
        if index == 0:
            if entry.get("prev_entry_digest") is not None:
                errors.append(
                    "replay ledger genesis entry prev_entry_digest must be null"
                )
        elif entry.get("prev_entry_digest") != previous_digest:
            errors.append(
                f"replay ledger entry[{index}] prev_entry_digest does not chain the "
                "previous entry_digest (duplicate/reordered/truncated chain)"
            )
        previous_digest = entry.get("entry_digest")
    return errors


def derive_authorization_replay_binding(
    authorization: Any,
    replay_ledger: Any,
    *,
    now: str | datetime | None = None,
) -> dict[str, Any]:
    """驗證層消費裁決:此授權「現在」可否消費其 replay id(§9.1;fail-closed)。

    回 ``{"status": "UNCONSUMED_AUTHORIZATION_VALID"|"AUTHORIZATION_REJECTED", "reasons": [...],
    "production_effect": "EXTERNAL_VERIFICATION_PENDING"}``:

      * 授權自身必須全過 :func:`_s2_4_operator_authorization_errors`(profile/簽章/信任根/TTL;
        ``now`` 傳入時再驗新鮮窗——過期/未生效授權在此拒);
      * ledger 自身必須全過 :func:`_s2_4_replay_ledger_errors`(斷鏈/亂序/竄改拒);
      * ledger 中同 ``authorization_id`` 的既有 entry:
          - 0 筆 → 未消費,可消費(UNCONSUMED_AUTHORIZATION_VALID);
          - 1 筆且 ``authorization_digest`` == 本授權 ``self_digest`` → 已消費過一次,
            再消費即 consuming-twice → 拒;
          - 1 筆但 ``authorization_digest`` ≠ 本授權 ``self_digest`` → 同 replay id 已綁到
            「不同」授權/plan(same-id-different-plan)→ 拒;
          - ≥2 筆 → ledger 已含重複消費 → 拒。
      * ``profile_identity`` 與既有 entry 的 profile 不符亦拒(跨 profile 挪用縫)。

    **誠實界線**:UNCONSUMED_AUTHORIZATION_VALID 只是離線驗證層裁決;真消費(fsync/install
    lock/append)與任何 applied/production 狀態屬 W6A/W6B EFFECT——回傳恆帶 typed
    ``production_effect: EXTERNAL_VERIFICATION_PENDING``,source lane 無從以有效簽章換取
    applied/production。**W6 driver 義務(E3 P2-1)**:本謂詞對「caller 供給的 ledger 物件」
    裁決,無從偵測 stale-prefix/fork snapshot;真消費決策必須錨定 install lock 下讀取的
    exact runtime ledger head,絕不可用呼叫端傳入的 ledger 快照代替。

    新鮮窗 fail-closed(E2 P2-1/E3 P2-2):``now`` 省略時默認「真實 wall clock」——消費裁決
    本質是 runtime 決策,過期授權不得因 caller 忘傳 now 而被判 VALID(對齊
    ``_dependency_graph_errors`` 的 wall-clock 默認先例)。
    """

    if now is None:
        now = datetime.now(timezone.utc)
    verdict: dict[str, Any] = {
        "status": "AUTHORIZATION_REJECTED",
        "reasons": [],
        # source lane 恆值:離線驗證絕不授予 production(§6/§10.2 typed fail-closed)。
        "production_effect": "EXTERNAL_VERIFICATION_PENDING",
    }
    if not isinstance(authorization, dict):
        verdict["reasons"] = ["authorization must be an object"]
        return verdict
    reasons = _s2_4_operator_authorization_errors(authorization, now=now)
    # E3 P2-3:authorization_id 形狀防禦——缺失/非字串/空值即拒,杜絕「信任根簽了缺 id 的
    # 畸形授權 → 恆匹配零筆 entry → 永遠 UNCONSUMED」的縫。
    authorization_id_value = authorization.get("authorization_id")
    if not isinstance(authorization_id_value, str) or not authorization_id_value.strip():
        reasons.append("authorization_id must be a non-empty string")
    if not isinstance(replay_ledger, dict):
        reasons.append("replay ledger must be an object")
        verdict["reasons"] = reasons
        return verdict
    reasons.extend(_s2_4_replay_ledger_errors(replay_ledger))
    if reasons:
        verdict["reasons"] = reasons
        return verdict
    authorization_id = authorization.get("authorization_id")
    matches = [
        entry
        for entry in replay_ledger.get("entries", [])
        if isinstance(entry, dict)
        and entry.get("authorization_id") == authorization_id
    ]
    if len(matches) >= 2:
        reasons.append(
            "replay id has duplicated consumption entries in the ledger "
            "(consuming twice is AUTHORIZATION_REJECTED)"
        )
    elif len(matches) == 1:
        entry = matches[0]
        if entry.get("authorization_digest") != authorization.get("self_digest"):
            reasons.append(
                "replay id is already bound to a DIFFERENT authorization/plan "
                "(same-id-different-plan is AUTHORIZATION_REJECTED)"
            )
        elif entry.get("profile_identity") != authorization.get("profile_identity"):
            reasons.append(
                "replay id was consumed under a different profile identity "
                "(cross-profile substitution is AUTHORIZATION_REJECTED)"
            )
        else:
            reasons.append(
                "authorization replay id is already consumed; a consumed "
                "authorization is never released (consuming twice is "
                "AUTHORIZATION_REJECTED)"
            )
    if reasons:
        verdict["reasons"] = reasons
        return verdict
    verdict["status"] = "UNCONSUMED_AUTHORIZATION_VALID"
    return verdict


# --------------------------------------------------------------------------- #
# S2.4(WP4·W5·§9.2)dependency freshness——過期 **source** 身分的唯一補救途徑。
#
# §9.2 對三族 source 身分(S2.2A compatibility / S2.3 sealed-build·expected-identity /
# S1.3 contract)的原文是:
#
#   「exact source/content identities; if their original observation TTL is elapsed, an
#     independently recomputed ``s2_4_dependency_refresh_attestation_v1`` must bind the
#     original digest, current exact head, reproduced semantic digests and a new short
#     expiry」
#   「The central validator accepts an expired source-identity receipt only together with
#     one current refresh attestation that independently replays its producer/semantic
#     checks. A refresh cannot refresh another refresh, cannot change any semantic digest
#     and cannot substitute for runtime observation.」
#
# 三個設計後果,逐條落成結構(而非欄位):
#
# 1. **「independently reproduced」不是 caller 能宣稱的東西。** 本閘「不」採信
#    ``reproduced_semantic_digests``:它由**驗證端自己**重跑該 dependency 的 producer SSOT
#    (S2.2A 走 learning_runtime_manifest 的 v1/v2 builder;S2.3/S1.3 走 sealed-build /
#    identity-acl 的 source·schema sha 與 lock closure),再與(a)refresh 宣稱值 (b)原 receipt
#    自己的語義欄位**兩邊**比對。重算的位元組取自 **bound commit 的 blob**(物化成臨時樹後
#    在其上跑 producer),不是工作樹——W5 review P1-A:兩者混用時,「commit 已漂移、只在工作樹
#    把舊位元組放回去」即可讓驗證端與偽造者 hash 到同一棵髒樹而雙雙通過,而該 commit 的乾淨
#    checkout 永遠復現不出。同一輸入集合另受 clean-tree 閘約束(見 reproduce_… docstring)。
# 2. **同一個節點、同一次觀測產不出 refresh。** ``reproduction.reproduced_at`` 必須嚴格晚於
#    原 receipt 自己的到期時刻——而該到期值只有在原 receipt 本身經家族驗證器認證後才不在
#    偽造者手上(W5 review P1-C:原 receipt 現由 validate_aiml_artifact / S1.3 SSOT 驗證器
#    逐項驗,且其自帶 self_digest 必須綁住自身位元組)。``reproducer_identity`` /
#    ``original_producer_identity`` 以**同一個** projection 函式各自再導出後必須相異;
#    ``reproducer_caller`` 亦不得等於原 receipt 的 producer 標籤。誠實界線:source lane 沒有
#    任何 key custody,故「不同節點」的宣告半邊只是宣告(見 W5 obligation
#    DEPENDENCY_REFRESH_REPRODUCER_NODE_IS_DECLARATIVE)。
# 3. **refresh 不能 refresh 另一份 refresh、也不能代替 runtime 觀測。** 前者由 schema 的封閉
#    ``original_schema_version`` enum(不含本 schema)加本閘的具名檢查雙重擋;後者由
#    :data:`S2_4_NEVER_REFRESHABLE_EVIDENCE` 封閉表執法——§9.2 表中「always freshly
#    observed / freshly authorized / freshly re-hashed / newly signed…never refreshed or
#    chained」那幾列,遞交任何 refresh 一律 typed 拒(§10.5 #28 後半、§12 #15)。
#
# **簽章判斷(worker 判斷,顯式記錄):本 artifact 不帶 SSHSIG。** §9.2 對 refresh 只要求
# 四項綁定(original digest / current exact head / reproduced semantic digests / new short
# expiry),通篇未提簽章;同一張表在真的要求簽章的列上一律明寫 “newly signed”
# (probe / PREPARE / aggregate / PG 四種授權)。§9.1 又把可重用該物理金鑰的 profile 封閉成
# **恰四**個 domain-separated 身分/namespace,refresh 不在其中;§10.4 明令 worker 不得自選
# exported schema/status/adapter 身分,§12 #15 明令「No arbitrary SSHSIG public key」。再者
# 授權是「授予效果」並經 replay ledger 一次性消費,refresh 則什麼也不授予——它只是「這次重算
# 復現了」的證據,其完整性由 canonical self-digest 提供,其真確性由**驗證端自己重算**提供
# (§9.1 原文:「A self-digest is integrity evidence, not producer authenticity」;對 refresh
# 而言 producer authenticity 正是被 independent replay 取代的那一項)。一份簽了名卻復現不出
# 的 refresh 仍必須被拒,一份沒簽名卻復現得出的 refresh 已載明 §9.2 要求的全部資訊——故加簽
# 只會多一個 §9.1 未授權的 namespace,不會多一分保證。
# --------------------------------------------------------------------------- #
S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION = "s2_4_dependency_refresh_attestation_v1"
S2_4_DEPENDENCY_REFRESH_METHOD = "INDEPENDENT_REPOSITORY_RECOMPUTATION"
DEPENDENCY_REFRESH_STATUS_ADMITTED = "DEPENDENCY_REFRESH_ADMITTED"
DEPENDENCY_REFRESH_STATUS_REJECTED = "DEPENDENCY_REFRESH_REJECTED"
DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN = "DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN"
DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED = "DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED"
SOURCE_DEPENDENCY_STATUS_FRESH = "SOURCE_DEPENDENCY_FRESH"
SOURCE_DEPENDENCY_STATUS_ADMITTED_BY_REFRESH = "SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH"
SOURCE_DEPENDENCY_STATUS_EXPIRED_NO_REFRESH = "SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH"
SOURCE_DEPENDENCY_STATUS_REJECTED = "SOURCE_DEPENDENCY_REJECTED"
# §9.2「a new short expiry」:沿用 §9.1 對 permit 的同一保守上限(900s),不自創新窗。
MAX_DEPENDENCY_REFRESH_TTL_SECONDS = 900
# S2.2A receipt 自身「不帶」 expires_at/ttl_seconds(只有 generated_at_utc),故其「original
# observation TTL」是 code-owned 常量,而非 caller 可調值;取 S2.3/S1.3 兩族 schema 自己的
# TTL 天花板(3600s)為同一保守窗。
S2_2A_OBSERVATION_TTL_SECONDS = 3600

def dependency_producer_input_paths(dependency_class: Any) -> tuple[str, ...]:
    """該 §9.2 族的 producer **輸入位元組全集**(repo 相對路徑;含 producer SSOT 自身)。

    兩個用途共用同一份:(a)要物化 bound commit 的哪些 blob 才夠讓 producer 在隔離樹上跑完;
    (b)clean-tree 閘看哪些路徑。S2.2A 直接取 producer 自己的凍結 allowlist 常量(絕不另抄一
    份)。完備性不是宣稱:物化樹只含此集合,producer 少一個輸入就 ``missing_input:``
    fail-closed,故「集合不完整」在 S2.2A 上會爆,不是靜默降級。
    """

    row = S2_4_DEPENDENCY_REFRESH_CLASSES.get(str(dependency_class))
    if row is None:
        raise ValueError(
            f"{dependency_class!r} is not one of the §9.2 refreshable source-identity classes"
        )
    paths: set[str] = {row["producer_module"]}
    schema_dir = "program_code/ml_training/schemas/aiml_gate_receipts"
    identity_producer = (
        "helper_scripts/maintenance_scripts/agent_governance_identity_acl_contract.py"
    )
    if dependency_class == "S2_2A_SOURCE_COMPATIBILITY":
        with program_code_on_path():
            from ml_training import learning_runtime_manifest as _lrm  # noqa: E402 (lazy)
        paths.update(_lrm.CAPTURE_INPUTS)
        paths.update(_lrm.LEARNING_CODE_INPUTS_V2)
        paths.update(_lrm.MIGRATION_INPUTS)
        paths.update({
            _lrm.REGIME_OOS_LABEL_CONTRACT,
            _lrm.POLICY_TEMPLATE,
            _lrm.DEPENDENCY_LOCK_SPEC_FILE,
            _lrm.DEPENDENCY_LOCK_LOCK_FILE,
            # feature 面的兩個常量與 hash 函式來自被 **import** 的葉、不是被 hash 的檔;物化樹
            # 幫不上這種輸入,故由 clean-tree 閘覆蓋它(見 reproduce_… 的第二半)。
            "program_code/ml_training/edge_feature_schema_contract.py",
        })
    elif dependency_class == "S1_3_IDENTITY_CONTRACT":
        paths.add(f"{schema_dir}/identity_acl_contract_receipt_v1.schema.json")
    elif dependency_class == "S2_3_EXPECTED_IDENTITY":
        paths.update({
            f"{schema_dir}/expected_identity_receipt_v1.schema.json",
            # expected-component 身分/negative 種類/rollback 綁定都是 S1.3 常量的投影,
            # 而 sealed_build_digest 的對象是 repo 內那份**已提交**的 sealed receipt。
            identity_producer,
            S2_3_SEALED_BUILD_RECEIPT_REL,
            "requirements-ml.lock",
            "requirements-ml.txt",
        })
    else:
        paths.update({
            f"{schema_dir}/sealed_build_receipt_v1.schema.json",
            "requirements-ml.lock",
            "requirements-ml.txt",
        })
    return tuple(sorted(paths))


def _utc_text(value: Any) -> str:
    """把任意可解析時間戳正規成 UTC ISO 字串(``Z`` 與 ``+00:00`` 兩形視為同一時刻)。"""

    return _parse_timestamp(str(value)).astimezone(timezone.utc).isoformat()


def dependency_producer_identity(
    *, caller: Any, observation_time: Any, platform: Any
) -> str:
    """producer 身分投影(原 receipt 與 reproducer **共用同一形狀**,故兩者可直接比較)。"""

    return canonical_digest({
        "caller": caller,
        "observation_time": _utc_text(observation_time),
        "platform": platform,
    })


def _original_producer_fields(original: Any) -> dict[str, Any] | None:
    """從原 receipt **自身**導出 producer 三元組(caller / observation_time / platform)。

    S2.3(sealed-build、expected-identity)與 S1.3 三族都帶 ``caller``/``platform``/
    ``observation_time``;S2.2A 兩版只有 ``session_id``/``generated_at_utc``(無 caller、
    無 platform),故其 caller 標籤退化為 session_id、platform 為 ``None``。此不對稱是
    schema 事實,不是本閘的選擇——W5 obligation 逐字記錄它。"""

    if not isinstance(original, dict):
        return None
    caller = original.get("caller")
    if not isinstance(caller, str) or not caller.strip():
        caller = original.get("session_id")
    observed = original.get("observation_time") or original.get("generated_at_utc")
    if not isinstance(caller, str) or not isinstance(observed, str):
        return None
    return {
        "caller": caller,
        "observation_time": observed,
        "platform": original.get("platform"),
    }


def dependency_original_observation_window(original: Any) -> tuple[str, str] | None:
    """原 receipt 自己的 (observed_at, expires_at);S2.2A 以 code-owned TTL 導出到期。"""

    if not isinstance(original, dict):
        return None
    observed = original.get("observation_time")
    expires = original.get("expires_at")
    if isinstance(observed, str) and isinstance(expires, str):
        return observed, expires
    generated = original.get("generated_at_utc")
    if isinstance(generated, str) and str(
        original.get("schema_version", "")
    ).startswith("source_compatibility_receipt_"):
        try:
            moment = _parse_timestamp(generated)
        except (TypeError, ValueError):
            return None
        return generated, (
            moment + timedelta(seconds=S2_2A_OBSERVATION_TTL_SECONDS)
        ).astimezone(timezone.utc).isoformat()
    return None


def dependency_class_for_schema_version(schema_version: Any) -> str | None:
    """該原 receipt schema 屬於哪一個 §9.2 可刷新族(不屬於任何一族回 ``None``)。"""

    for name, row in S2_4_DEPENDENCY_REFRESH_CLASSES.items():
        if schema_version in row["original_schema_versions"]:
            return name
    return None


@lru_cache(maxsize=32)
def _reproduce_at_commit(
    dependency_class: str, schema_version: str, root_text: str, head: str,
    inputs: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """在 bound commit 的物化樹上重算(記憶化;鍵已完全決定輸出:乾淨樹的位元組即該 commit 的
    位元組,而記憶化只在 clean-tree 閘通過後才發生)。回 tuple 形以免呼叫端共享可變 dict。"""

    with tempfile.TemporaryDirectory(prefix="s2-4-dependency-refresh-") as scratch:
        tree = Path(scratch)
        missing = materialize_commit_paths(Path(root_text), inputs, tree, source_head=head)
        if missing:
            raise ValueError(
                f"the bound commit {head} carries no blob for {missing}; the "
                f"{dependency_class} producer inputs are not reproducible at that commit"
            )
        return tuple(sorted(recompute_dependency_semantic_subjects(
            dependency_class, schema_version, tree, head
        ).items()))


def reproduce_dependency_semantic_digests(
    dependency_class: Any,
    *,
    original_schema_version: Any,
    repo_root: Path = REPO_ROOT,
    source_head: str | None = None,
) -> dict[str, str]:
    """**驗證端自己**在 ``repo_root`` 的 **bound commit** 上重跑該 dependency 的語義再算。

    這是 §9.2「independently replays its producer/semantic checks」的實體:每一個值都由
    **那個 commit 的 blob** 重算得出,呼叫端遞交的任何值都不參與。無法重算即 raise
    ``ValueError``(fail-closed;絕不回半份或空 dict)。

    W5 review P1-A(承 W2 P1-5 同一裁決)。舊版 head 取自 git metadata、位元組卻取自檔案
    系統,於是「commit 已漂移、攻擊者只在工作樹把舊位元組放回去(不 commit、不 git add)」
    就能讓復現成功,而該 commit 的乾淨 checkout 永遠復現不出。現在兩半都堵:(1)把該族
    producer 的輸入位元組全集自 bound commit 物化成一棵臨時樹,producer 在那棵樹上跑——
    工作樹不是輸入;(2)clean-tree 閘:``repo_root`` 的 index/worktree 在該輸入集合上必須與
    bound commit 無差異,否則 typed 拒——物化樹擋不住「被 import 進來的 producer 程式碼」
    這類輸入(feature schema 葉、producer SSOT 自身),那一半由此閘覆蓋。
    """

    row = S2_4_DEPENDENCY_REFRESH_CLASSES.get(str(dependency_class))
    if row is None:
        raise ValueError(
            f"{dependency_class!r} is not one of the §9.2 refreshable source-identity classes"
        )
    if original_schema_version not in row["original_schema_versions"]:
        raise ValueError(
            f"{original_schema_version!r} is not an original schema of {dependency_class}"
        )
    root = Path(repo_root)
    head = resolve_commit_head(root, source_head)
    if head is None:
        raise ValueError(
            f"the bound commit of {root} is unresolvable; a §9.2 reproduction is only "
            "defined against a commit (fail-closed)"
        )
    inputs = dependency_producer_input_paths(dependency_class)
    delta = owned_scope_worktree_delta(root, inputs, source_head=head)
    if delta is None:
        raise ValueError(
            "the index/worktree state of the producer input set is undecidable (fail-closed)"
        )
    if delta:
        raise ValueError(
            f"the {dependency_class} producer input set differs from the bound commit "
            f"{head} in the index/worktree ({delta}); a reproduction performed against a "
            "dirty tree is not a function of the bound commit and can never be repeated "
            "from a clean checkout of it"
        )
    return dict(_reproduce_at_commit(
        str(dependency_class), str(original_schema_version), str(root), head, inputs
    ))


def dependency_evidence_schema_versions(evidence_class: Any) -> tuple[str, ...] | None:
    """該 §9.2 evidence class 的 **code-owned** 允許 schema_version 集合(未知類別回 None)。

    W5 review P2-D:``evidence_class`` 只是 caller 遞交的字串;不把它綁到「那份 artifact 該是
    什麼 schema」,兩鍵 dict 冠上 ``PG_TOPOLOGY_ATTESTATION`` 也能導出 SOURCE_DEPENDENCY_FRESH
    ——正好違反該列的 “always freshly observed”。
    """

    row = S2_4_DEPENDENCY_REFRESH_CLASSES.get(evidence_class)
    if row is not None:
        return tuple(row["original_schema_versions"])
    return S2_4_NEVER_REFRESHABLE_SCHEMAS.get(evidence_class)


def _committed_source_identity_errors(
    receipt: dict[str, Any], dependency_class: str, repo_root: Path
) -> list[str]:
    """這份原 source 身分是不是 bound commit 上**那一份已提交的** artifact(P1-B)。

    §9.2 的新鮮度完全由原 receipt 自帶的 ``observation_time``/``expires_at`` 決定,而那兩欄
    在 caller 手上;家族驗證器認證形狀,不認證窗。三族的原身分在 repo 內都是已提交的固定
    路徑,所以「它是不是那一份」是驗證端算得出來的——這才是把窗從 caller 手上拿回來的東西。

    ``committed_source_identity_digests`` 回 ``None`` = 這一族在這棵樹的 bound commit 上沒有
    可比對的已提交身分(S1.3 恆如此;隔離測試樹亦然);那時窗仍是 caller 自選的,而該殘留由
    ``DEPENDENCY_OBSERVATION_WINDOW_IS_CALLER_AUTHORED`` 逐字記錄,不在此靜默拒。
    """

    committed = committed_source_identity_digests(dependency_class, Path(repo_root))
    if committed is None:
        return []
    if artifact_self_digest(receipt) in committed:
        return []
    return [
        "the supplied "
        f"{receipt.get('schema_version')!r} is not the artifact committed at the bound "
        f"commit ({list(S2_4_COMMITTED_SOURCE_IDENTITY_PATHS.get(dependency_class) or ())}); "
        "§9.2's freshness verdict is read off observation_time/expires_at, which are the "
        "caller's own fields, so a receipt that is not the committed one carries a "
        "caller-authored observation window and no §9.2 verdict can be derived from it"
    ]


def _dependency_evidence_receipt_errors(
    receipt: Any, expected: tuple[str, ...], *, now: Any, repo_root: Path = REPO_ROOT,
    evidence_class: Any = None,
) -> list[str]:
    """這份 evidence 真的是它被冠上的那個 artifact 嗎(schema 身分 + 家族驗證器 + 自摘要)。

    W5 review P1-C/P2-D:``artifact_self_digest(x)`` 是自指的(攻擊者兩邊都遞交),只能證
    「refresh 綁的是這份 x」,證不了「x 是某個 session 真的產出過的東西」。真憑據是家族驗證器
    (exact 欄位集、adapter/observation owner 身分、S1.3 逐元件再投影、≥10 個 over-grant
    negative-ACL、所有 production/running attested flag 必為 false)加上 x 自帶的
    ``self_digest`` 必須等於它自己的 canonical 投影。"""

    if not isinstance(receipt, dict):
        return ["the bound source-identity receipt object must be an object"]
    schema_version = receipt.get("schema_version")
    if schema_version not in expected:
        return [
            f"the bound receipt is a {schema_version!r}, which is not one of the artifacts "
            f"this evidence class names ({list(expected)}); a caller-supplied evidence_class "
            "label is never the proof of what the artifact is"
        ]
    errors: list[str] = []
    # S2.4-AMEND-1(obligation 26):schema_version 對了不代表**是那一列所指之物**——四個
    # permit 列 / 兩個 probe 列 many-to-one 映到同一份 schema,判別欄位在此執法。
    discriminator = (
        S2_4_EVIDENCE_CLASS_DISCRIMINATORS.get(evidence_class)
        if evidence_class is not None else None
    )
    if discriminator is not None and receipt.get(discriminator[0]) != discriminator[1]:
        errors.append(
            f"the bound receipt carries {discriminator[0]}="
            f"{receipt.get(discriminator[0])!r}, not {discriminator[1]!r}; a genuine "
            f"artifact of the wrong §9.1 profile/scope is not the artifact "
            f"{evidence_class} names (§9.1 / §9.2)"
        )
    if schema_version == "identity_acl_contract_receipt_v1":
        # S1.3 的家族驗證器未登記在中央 SCHEMA_FILES(其 schema 由 SSOT 模組自持),故直接委派。
        import agent_governance_identity_acl_contract as _s1_3  # noqa: E402 (lazy)

        errors.extend(_s1_3.validate_identity_acl_contract_receipt(receipt))
    else:
        errors.extend(_resolve_facade().validate_aiml_artifact(receipt, now=now))
    if "self_digest" in receipt and receipt["self_digest"] != artifact_self_digest(receipt):
        errors.append(
            "the bound receipt's own self_digest does not bind its canonical bytes; it was "
            "hand-written or edited after emission"
        )
    # W5 對抗審計第二輪:三族 S2.3/S1.3 receipt 的 status 是 enum ["PASS","FAIL"],而家族驗證器
    # 預設 require_success=False,於是把已發射的 receipt 翻成 status=FAIL(補一個 failure_reason
    # 讓 schema 過關)照樣可被刷新。§9.2 續的是「**過期**的 source 身分」,不是「失敗的觀測」:
    # 一份自陳 FAIL 的 artifact 沒有可延長的身分,只能重新觀測。只施於**可刷新**的四族
    # (never-refreshable 那九列的 artifact 例如 pg_topology_attestation_v1 根本沒有 status 欄)。
    dependency_class = dependency_class_for_schema_version(schema_version)
    if dependency_class is not None and (
        receipt.get("status") not in _DEPENDENCY_EVIDENCE_SUCCESS_STATUSES
    ):
        errors.append(
            f"the bound source-identity receipt carries status {receipt.get('status')!r}; "
            "§9.2 extends the life of an EXPIRED identity, never of a failed observation"
        )
    if dependency_class is not None:
        errors.extend(
            _committed_source_identity_errors(receipt, dependency_class, Path(repo_root))
        )
    return errors


def _dependency_refresh_structural_errors(artifact: dict[str, Any]) -> list[str]:
    """§9.2 refresh 的**自足**結構驗:中央閘手上沒有原 receipt 時仍必須成立的那一半。

    facade 的 ``validate_aiml_artifact`` 分支委派本函式;完整裁決(含原 receipt 綁定、head、
    producer 獨立性、驗證端重算比對)恆由 :func:`derive_dependency_refresh_status` 授予。
    """

    errors: list[str] = []
    if artifact["self_digest"] != artifact_self_digest(artifact):
        errors.append("dependency refresh self_digest does not bind the canonical artifact")
    row = S2_4_DEPENDENCY_REFRESH_CLASSES.get(artifact["dependency_class"])
    if row is None:
        return errors + ["dependency_class is not a §9.2 refreshable source-identity class"]
    if artifact["original_schema_version"] not in row["original_schema_versions"]:
        errors.append(
            "original_schema_version does not belong to the declared dependency_class"
        )
    expected = set(row["semantic_digest_fields"])
    if set(artifact["reproduced_semantic_digests"]) != expected:
        errors.append(
            "reproduced_semantic_digests is not the exact §9.2 semantic-digest field set "
            f"of {artifact['dependency_class']}"
        )
    if any(
        value == artifact["original_receipt_digest"]
        for value in artifact["reproduced_semantic_digests"].values()
    ):
        errors.append(
            "a reproduced semantic digest merely re-asserts original_receipt_digest; §9.2 "
            "requires an independently recomputed semantic digest"
        )
    reproduction = artifact["reproduction"]
    if reproduction["reproducer_identity"] == reproduction["original_producer_identity"]:
        errors.append(
            "the refresh's producer projection equals the original's; a refresh cannot be "
            "the original observation restated (§9.2)"
        )
    return errors


def build_s2_4_dependency_refresh_attestation(
    original_receipt: dict[str, Any],
    *,
    reproducer_caller: str,
    reproducer_platform: dict[str, Any],
    reproduced_at: str,
    refresh_ttl_seconds: int = MAX_DEPENDENCY_REFRESH_TTL_SECONDS,
    repo_root: Path = REPO_ROOT,
    current_source_head: str | None = None,
) -> dict[str, Any]:
    """組出一份 §9.2 refresh:語義 digest **一律**由驗證端重算填入,caller 無從遞交。

    builder 與閘共用同一支 :func:`reproduce_dependency_semantic_digests`,故「能建出來」本身
    就代表持有當前 head 的源碼樹且復現成功;建構 ≠ 認可,PASS 恆由
    :func:`derive_dependency_refresh_status` 導出(receipt 不帶任何 status 欄位)。
    """

    if not isinstance(original_receipt, dict):
        raise ValueError("original receipt must be an object")
    original_schema_version = original_receipt.get("schema_version")
    if original_schema_version == S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION:
        raise ValueError("§9.2: a refresh cannot refresh another refresh")
    dependency_class = dependency_class_for_schema_version(original_schema_version)
    if dependency_class is None:
        raise ValueError(
            f"{original_schema_version!r} is not a §9.2 refreshable source identity"
        )
    window = dependency_original_observation_window(original_receipt)
    if window is None:
        raise ValueError("original receipt carries no resolvable observation window")
    producer = _original_producer_fields(original_receipt)
    if producer is None:
        raise ValueError("original receipt carries no resolvable producer identity")
    head = current_source_head or _resolve_facade()._git_head(Path(repo_root))
    if head is None:
        raise ValueError("repo HEAD is unreadable; a refresh cannot bind a current head")
    producer_module = S2_4_DEPENDENCY_REFRESH_CLASSES[dependency_class]["producer_module"]
    producer_module_digest = owned_path_blob_projection(
        Path(repo_root), [producer_module], source_head=head
    )[producer_module]
    if producer_module_digest is None:
        raise ValueError(
            "the producer SSOT module has no blob at the bound commit; a refresh cannot "
            "bind a producer identity that commit does not contain"
        )
    ttl = int(refresh_ttl_seconds)
    reproduced_moment = _parse_timestamp(reproduced_at)
    artifact: dict[str, Any] = {
        "schema_version": S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION,
        "program_id": "AIML-LONG-LIVED-LANDING-V2",
        "work_package": "WP4",
        "dependency_class": dependency_class,
        "original_schema_version": original_schema_version,
        "original_receipt_digest": artifact_self_digest(original_receipt),
        "original_observed_at": window[0],
        "original_expires_at": window[1],
        "current_source_head": head,
        "producer_module_digest": producer_module_digest,
        "reproduced_semantic_digests": reproduce_dependency_semantic_digests(
            dependency_class,
            original_schema_version=original_schema_version,
            repo_root=repo_root,
            source_head=head,
        ),
        "reproduction": {
            "method": S2_4_DEPENDENCY_REFRESH_METHOD,
            "reproduced_at": reproduced_at,
            "reproducer_caller": reproducer_caller,
            "reproducer_platform": dict(reproducer_platform),
            "reproducer_identity": dependency_producer_identity(
                caller=reproducer_caller,
                observation_time=reproduced_at,
                platform=dict(reproducer_platform),
            ),
            "original_producer_identity": dependency_producer_identity(**producer),
        },
        "expires_at": (
            reproduced_moment + timedelta(seconds=ttl)
        ).astimezone(timezone.utc).isoformat(),
        "refresh_ttl_seconds": ttl,
        "production_authority_flags": {
            "nine_authorities_false": True,
            "production_apply_performed": False,
            "running_attested": False,
        },
    }
    artifact["self_digest"] = artifact_self_digest(artifact)
    return artifact


def derive_dependency_refresh_status(
    refresh: Any,
    *,
    original_receipt: Any,
    now: str | datetime | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """§9.2:這份 refresh 是否**獨立復現**了那份過期 source 身分(typed;caller 不可自證)。

    回 ``{"status": DEPENDENCY_REFRESH_ADMITTED|DEPENDENCY_REFRESH_REJECTED, "reasons": [...],
    "dependency_class": …, "reproduced_semantic_digests": <驗證端重算值或 None>,
    "admits_expired_source_identity": bool}``。

    新鮮窗 fail-closed:``now`` 省略時取真實 wall clock(鏡 derive_authorization_replay_binding)。
    """

    if now is None:
        now = datetime.now(timezone.utc)
    verdict: dict[str, Any] = {
        "status": DEPENDENCY_REFRESH_STATUS_REJECTED,
        "reasons": [],
        "dependency_class": None,
        "reproduced_semantic_digests": None,
        "admits_expired_source_identity": False,
    }
    if not isinstance(refresh, dict):
        verdict["reasons"] = ["dependency refresh attestation must be an object"]
        return verdict
    facade = _resolve_facade()
    declared = sorted(key for key in facade._CALLER_STATUS_KEYS if key in refresh)
    if declared:
        verdict["reasons"] = [
            "dependency refresh attestation must not self-declare status "
            f"({', '.join(declared)}); the central validator derives "
            "DEPENDENCY_REFRESH_ADMITTED from an independent recomputation"
        ]
        return verdict
    try:
        schema = facade._load_schema(S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION)
        schema_errors = facade.schema_subset_errors(refresh, schema, schema)
    except Exception as error:  # noqa: BLE001 - schema 不可讀即 fail-closed
        verdict["reasons"] = [f"dependency refresh closed-schema is unloadable: {error}"]
        return verdict
    if schema_errors:
        verdict["reasons"] = schema_errors
        return verdict
    reasons: list[str] = []
    if refresh["self_digest"] != artifact_self_digest(refresh):
        reasons.append("dependency refresh self_digest does not bind the canonical artifact")
    dependency_class = refresh["dependency_class"]
    verdict["dependency_class"] = dependency_class
    row = S2_4_DEPENDENCY_REFRESH_CLASSES.get(dependency_class)
    original_schema_version = refresh["original_schema_version"]
    if row is None:
        verdict["reasons"] = [
            f"{dependency_class!r} is not a §9.2 refreshable source-identity class"
        ]
        return verdict
    if original_schema_version not in row["original_schema_versions"]:
        reasons.append(
            f"original_schema_version {original_schema_version!r} does not belong to "
            f"{dependency_class} (allowed: {list(row['original_schema_versions'])})"
        )
    if not isinstance(original_receipt, dict):
        verdict["reasons"] = reasons + [
            "the original source-identity receipt object is required: §9.2's replay is "
            "performed by the verifier over the ORIGINAL artifact, never over its digest"
        ]
        return verdict
    if original_receipt.get("schema_version") == S2_4_DEPENDENCY_REFRESH_SCHEMA_VERSION:
        reasons.append(
            "§9.2: a refresh cannot refresh another refresh (the bound original is itself "
            "an s2_4_dependency_refresh_attestation_v1)"
        )
    elif original_receipt.get("schema_version") != original_schema_version:
        reasons.append(
            "the bound original receipt is a different schema than original_schema_version "
            f"({original_receipt.get('schema_version')!r} != {original_schema_version!r})"
        )
    original_digest = artifact_self_digest(original_receipt)
    if refresh["original_receipt_digest"] != original_digest:
        reasons.append(
            "original_receipt_digest does not bind the supplied original receipt "
            "(a substituted source identity is not the identity being refreshed)"
        )
    # ── 原 receipt 必須先是「某個 session 真的產出過的那份 artifact」(W5 review P1-C)──
    # 少了這一段,一份手寫的、任何 S2.3 session 都沒產過的 "original"(可自帶
    # running_attested:true、可自選 observation_time/expires_at)照樣拿得到
    # DEPENDENCY_REFRESH_ADMITTED;連「reproduced_at 必須晚於原證據到期」這條結構性反自我
    # 刷新控制也一起失效——它只有在 original_expires_at 不在攻擊者手上時才是結構性的。
    reasons.extend(
        _dependency_evidence_receipt_errors(
            original_receipt, tuple(row["original_schema_versions"]), now=None,
            repo_root=Path(repo_root),
        )
    )
    # ── §9.2「current exact head」──────────────────────────────────────────────
    head = facade._git_head(Path(repo_root))
    if head is None:
        reasons.append(
            "current_source_head cannot be bound: repo HEAD is unreadable (fail-closed)"
        )
    elif refresh["current_source_head"] != head:
        reasons.append(
            "current_source_head is not the current checkout HEAD; §9.2 requires the "
            "reproduction to be performed at the exact current head"
        )
    # ── 原 receipt 自己的觀測窗必須被逐字綁住 ──────────────────────────────────
    window = dependency_original_observation_window(original_receipt)
    if window is None:
        reasons.append("the original receipt carries no resolvable observation window")
    else:
        try:
            if _utc_text(refresh["original_observed_at"]) != _utc_text(window[0]):
                reasons.append(
                    "original_observed_at is not the original receipt's own observation time"
                )
            if _utc_text(refresh["original_expires_at"]) != _utc_text(window[1]):
                reasons.append(
                    "original_expires_at is not the original receipt's own expiry"
                )
        except (TypeError, ValueError) as error:
            reasons.append(f"original observation window is unparseable: {error}")
    # ── producer 模組身分:驗證端取該族 producer SSOT 在 **bound commit** 的 blob ──────
    producer_module_digest = owned_path_blob_projection(
        Path(repo_root), [row["producer_module"]], source_head=head
    )[row["producer_module"]]
    if producer_module_digest is None:
        reasons.append(
            f"producer module {row['producer_module']} has no blob at the bound commit"
        )
    elif refresh["producer_module_digest"] != producer_module_digest:
        reasons.append(
            "producer_module_digest is not the current-head blob of "
            f"{row['producer_module']}; the replay did not run the reviewed producer"
        )
    # ── §9.2 的核心:語義 digest 由**驗證端**重算,再與 refresh 與原 receipt 兩邊比對 ──
    try:
        reproduced = reproduce_dependency_semantic_digests(
            dependency_class,
            original_schema_version=original_schema_version,
            repo_root=repo_root,
            source_head=head,
        )
    except Exception as error:  # noqa: BLE001 - 重算不出即 fail-closed
        reproduced = None
        reasons.append(
            "the verifier could not independently reproduce the semantic digests at the "
            f"current head: {error}"
        )
    verdict["reproduced_semantic_digests"] = reproduced
    claimed = refresh["reproduced_semantic_digests"]
    expected_fields = set(row["semantic_digest_fields"])
    if set(claimed) != expected_fields:
        reasons.append(
            "reproduced_semantic_digests is not the exact §9.2 semantic-digest field set of "
            f"{dependency_class} (extra={sorted(set(claimed) - expected_fields)}, "
            f"missing={sorted(expected_fields - set(claimed))})"
        )
    if any(value == refresh["original_receipt_digest"] for value in claimed.values()):
        reasons.append(
            "a reproduced semantic digest merely re-asserts original_receipt_digest; §9.2 "
            "requires an INDEPENDENTLY RECOMPUTED semantic digest, not a copy of the "
            "original receipt identity"
        )
    if reproduced is not None:
        # W5 對抗審計 P1-A:與原 receipt 的比對走 **內容投影**,不是同名欄位。舊碼用
        # ``original_receipt.get(field)``,於是只有 receipt 恰好自帶同名 digest 欄位的主體
        # 才被比到;expected-component 身分、S1.3 身分骨架、sealed 對象這些「內容型」主體
        # 完全沒有進到比對裡,把它們換掉照樣刷新成功。
        subjects = dependency_semantic_subject_values(dependency_class, original_receipt)
        for field in sorted(expected_fields):
            recomputed = reproduced.get(field)
            if claimed.get(field) != recomputed:
                reasons.append(
                    f"reproduced_semantic_digests[{field!r}] does not equal the verifier's "
                    "own recomputation at the current head"
                )
            if subjects.get(field) != recomputed:
                reasons.append(
                    f"the original receipt's {field!r} subject is no longer reproducible at "
                    "the current head; §9.2 forbids a refresh from changing any semantic "
                    "digest — the dependency must be re-observed, not refreshed"
                )
    # ── 獨立性:同一次觀測 / 同一個 producer 標籤都不得換到 refresh ─────────────
    reproduction = refresh["reproduction"]
    if reproduction["method"] != S2_4_DEPENDENCY_REFRESH_METHOD:
        reasons.append("reproduction.method is not the §9.2 independent-recomputation method")
    producer_fields = _original_producer_fields(original_receipt)
    if producer_fields is None:
        reasons.append("the original receipt carries no resolvable producer identity")
    else:
        original_identity = dependency_producer_identity(**producer_fields)
        if reproduction["original_producer_identity"] != original_identity:
            reasons.append(
                "reproduction.original_producer_identity is not the producer projection the "
                "verifier derives from the original receipt"
            )
        if reproduction["reproducer_caller"] == producer_fields["caller"]:
            reasons.append(
                "the refresh is produced by the same node/caller that produced the original "
                f"({producer_fields['caller']!r}); §9.2 requires an INDEPENDENT replay"
            )
        try:
            reproducer_identity = dependency_producer_identity(
                caller=reproduction["reproducer_caller"],
                observation_time=reproduction["reproduced_at"],
                platform=reproduction["reproducer_platform"],
            )
        except (TypeError, ValueError) as error:
            reproducer_identity = None
            reasons.append(f"reproducer identity is unprojectable: {error}")
        if reproducer_identity is not None:
            if reproduction["reproducer_identity"] != reproducer_identity:
                reasons.append(
                    "reproduction.reproducer_identity is not the projection of its own "
                    "carried caller/platform/reproduced_at"
                )
            elif reproducer_identity == original_identity:
                reasons.append(
                    "the refresh's producer projection equals the original's; a refresh "
                    "cannot be the original observation restated (§9.2)"
                )
    # ── 時間:復現必須在原證據到期之後、觀測時刻之前;新窗必須短且未過期 ────────
    moment = None
    try:
        moment = _parse_timestamp(_now_text(now) or str(now))
    except (TypeError, ValueError) as error:
        reasons.append(f"the observed moment is unparseable: {error}")
    try:
        reproduced_at = _parse_timestamp(refresh["reproduction"]["reproduced_at"])
        expires_at = _parse_timestamp(refresh["expires_at"])
        if window is not None and reproduced_at <= _parse_timestamp(window[1]):
            reasons.append(
                "reproduction.reproduced_at is not strictly after the original evidence's "
                "own expiry; a replay inside the original observation window is the same "
                "observation restated, not an independent reproduction (§9.2)"
            )
        if int((expires_at - reproduced_at).total_seconds()) != int(
            refresh["refresh_ttl_seconds"]
        ):
            reasons.append(
                "refresh_ttl_seconds does not equal expires_at - reproduced_at; the new "
                "short expiry must be exactly the declared window (§9.2)"
            )
        if int(refresh["refresh_ttl_seconds"]) > MAX_DEPENDENCY_REFRESH_TTL_SECONDS:
            reasons.append(
                "the refresh window exceeds the §9.2 'new short expiry' ceiling of "
                f"{MAX_DEPENDENCY_REFRESH_TTL_SECONDS}s"
            )
        if moment is not None:
            if reproduced_at > moment:
                reasons.append("reproduction.reproduced_at is in the future")
            if expires_at <= moment:
                reasons.append(
                    "the refresh attestation is itself expired; §9.2 admits an expired "
                    "source identity only together with a CURRENT refresh"
                )
    except (TypeError, ValueError) as error:
        reasons.append(f"refresh timestamps are unparseable: {error}")
    if reasons:
        verdict["reasons"] = sorted(set(reasons))
        return verdict
    verdict["status"] = DEPENDENCY_REFRESH_STATUS_ADMITTED
    verdict["admits_expired_source_identity"] = True
    return verdict


def derive_source_dependency_admission_status(
    *,
    evidence_class: Any,
    receipt: Any,
    refresh: Any = None,
    now: str | datetime | None = None,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """§9.2 的分類裁決:這份 dependency 證據現在可否被 S2.4 採信(typed;fail-closed)。

    三條互斥路徑:

    * ``evidence_class`` 落在 :data:`S2_4_NEVER_REFRESHABLE_EVIDENCE` —— 遞交**任何** refresh
      一律 ``DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN``(§10.5 #28 後半、§12 #15);未過期
      即 FRESH,過期即 ``DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED``(只能重新觀測/重簽)。
    * ``evidence_class`` 落在 :data:`S2_4_DEPENDENCY_REFRESH_CLASSES` —— 未過期 FRESH;過期且
      **恰一份** refresh 通過獨立復現才 ``SOURCE_DEPENDENCY_ADMITTED_BY_REFRESH``;零份是
      ``SOURCE_DEPENDENCY_EXPIRED_NO_REFRESH``,兩份以上直接拒(§9.2:「one current refresh」)。
    * 其他 —— 未知類別一律拒(封閉表,不預設放行)。
    """

    if now is None:
        now = datetime.now(timezone.utc)
    verdict: dict[str, Any] = {
        "status": SOURCE_DEPENDENCY_STATUS_REJECTED,
        "reasons": [],
        "evidence_class": evidence_class,
        "refresh_admitted": False,
        "runtime_observation_substituted": False,
    }
    refreshes: list[Any]
    if refresh is None:
        refreshes = []
    elif isinstance(refresh, (list, tuple)):
        refreshes = list(refresh)
    else:
        refreshes = [refresh]
    if evidence_class in S2_4_NEVER_REFRESHABLE_EVIDENCE and refreshes:
        # refresh-by-reference 的 typed 拒絕先於一切:這一列**任何** refresh 都不合法,
        # 與那份 evidence 自身是否合格無關(§9.2 / §10.5 #28 後半 / §12 #15)。
        verdict["status"] = DEPENDENCY_REFRESH_BY_REFERENCE_FORBIDDEN
        verdict["reasons"] = [
            f"{evidence_class} can never be refreshed by reference: "
            f"{S2_4_NEVER_REFRESHABLE_EVIDENCE[evidence_class]} (§9.2 / §10.5 #28 / §12 #15)"
        ]
        return verdict
    # ── 這份 evidence 必須真的是 evidence_class 所指的那份 artifact(W5 review P2-D)─────
    # 兩條分支都在此之後才可能給出 FRESH:少了它,``{"expires_at": "2099-…"}`` 冠上
    # PG_TOPOLOGY_ATTESTATION 就能導出 SOURCE_DEPENDENCY_FRESH。
    expected_schemas = dependency_evidence_schema_versions(evidence_class)
    if expected_schemas is None:
        verdict["reasons"] = [
            f"{evidence_class!r} is not a §9.2 dependency-freshness class; the table is "
            "closed and an unknown class is never admitted"
        ]
        return verdict
    # now=None:此處只驗「身分/結構/完整性」。牆鐘新鮮度是下面 §9.2 自己的分支要裁的事,
    # 若在此把 now 交給家族驗證器,一份**真的**但已過期的證據會被判成「不是那份 artifact」,
    # DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED 這條 §9.2 語義就再也走不到。
    receipt_errors = _dependency_evidence_receipt_errors(
        receipt, expected_schemas, now=None, repo_root=Path(repo_root),
        evidence_class=evidence_class,
    )
    if receipt_errors:
        verdict["reasons"] = receipt_errors
        return verdict
    if evidence_class in S2_4_NEVER_REFRESHABLE_EVIDENCE:
        expires = receipt.get("expires_at") if isinstance(receipt, dict) else None
        try:
            if expires is None:
                raise ValueError("evidence carries no expires_at")
            fresh = _parse_timestamp(str(expires)) > _parse_timestamp(
                _now_text(now) or str(now)
            )
        except (TypeError, ValueError) as error:
            verdict["reasons"] = [
                f"{evidence_class} freshness cannot be derived: {error} (fail-closed)"
            ]
            return verdict
        if fresh:
            verdict["status"] = SOURCE_DEPENDENCY_STATUS_FRESH
            return verdict
        verdict["status"] = DEPENDENCY_EVIDENCE_REOBSERVATION_REQUIRED
        verdict["reasons"] = [
            f"{evidence_class} is expired and cannot be refreshed by reference: "
            f"{S2_4_NEVER_REFRESHABLE_EVIDENCE[evidence_class]}"
        ]
        return verdict
    # 未知類別已在上方 expected_schemas is None 被封閉表擋下,此處必為可刷新族。
    window = dependency_original_observation_window(receipt)
    if window is None:
        verdict["reasons"] = [
            f"{evidence_class} carries no resolvable observation window (fail-closed)"
        ]
        return verdict
    try:
        moment = _parse_timestamp(_now_text(now) or str(now))
        expired = _parse_timestamp(window[1]) <= moment
    except (TypeError, ValueError) as error:
        verdict["reasons"] = [f"{evidence_class} freshness is unparseable: {error}"]
        return verdict
    if len(refreshes) > 1:
        verdict["reasons"] = [
            "§9.2 admits an expired source identity together with exactly ONE current "
            f"refresh attestation; {len(refreshes)} were supplied"
        ]
        return verdict
    if not expired:
        verdict["status"] = SOURCE_DEPENDENCY_STATUS_FRESH
        return verdict
    if not refreshes:
        verdict["status"] = SOURCE_DEPENDENCY_STATUS_EXPIRED_NO_REFRESH
        verdict["reasons"] = [
            f"{evidence_class} observation TTL is elapsed and no refresh attestation was "
            "supplied; §9.2 admits it only together with one independently reproduced "
            "s2_4_dependency_refresh_attestation_v1"
        ]
        return verdict
    outcome = derive_dependency_refresh_status(
        refreshes[0], original_receipt=receipt, now=now, repo_root=repo_root
    )
    verdict["reasons"] = list(outcome["reasons"])
    if outcome["status"] != DEPENDENCY_REFRESH_STATUS_ADMITTED:
        return verdict
    if outcome["dependency_class"] != evidence_class:
        verdict["reasons"] = [
            "the refresh attests a different dependency class than the evidence being "
            f"admitted ({outcome['dependency_class']!r} != {evidence_class!r})"
        ]
        return verdict
    verdict["status"] = SOURCE_DEPENDENCY_STATUS_ADMITTED_BY_REFRESH
    verdict["refresh_admitted"] = True
    return verdict

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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
if str(HELPER_DIR) not in sys.path:
    sys.path.insert(0, str(HELPER_DIR))

# 唯讀消費 S2.4 §9.1 SSHSIG 信任根與離線公鑰驗簽基元(同 facade 姿態;不反向匯入 facade)。
import agent_governance_aiml_trusted_host as _trusted_host  # noqa: E402

from aiml_gate_receipt_schema_core import (  # noqa: E402
    _canonical_bytes,
    _now_text,
    _parse_timestamp,
    artifact_self_digest,
    canonical_digest,
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
_SSH_SIGNATURE_ARMOR_MARKERS = (
    "-----BEGIN SSH SIGNATURE-----",
    "-----END SSH SIGNATURE-----",
)


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

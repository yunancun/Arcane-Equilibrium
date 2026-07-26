#!/usr/bin/env python3
"""S2.4(WP4·W3b)五個 APPLY component-effect 的 typed 主機 driver 葉(§4 row ABI / §5.3 / §5.4)。

每個 v2 class 一支進入點,逐一綁定凍結矩陣的 exact adapter / actor / 獨立 postcheck /
rollback 契約(綁定由中央 :func:`derive_component_intent_binding` 再導出,caller 不可自證):

===========================  =====================================================
``HOST_IDENTITY_INSTALL``    :func:`apply_s2_4_host_identity`
``PG_ROLE_ACL_MIGRATION``    :func:`apply_s2_4_pg_role_acl`
``CREDENTIAL_INSTALL``       :func:`apply_s2_4_credential_install`
``LEARNING_RUNTIME``         :func:`apply_s2_4_learning_runtime`
``ENGINE_SCANNER``           :func:`apply_s2_4_engine_scanner_unit`
===========================  =====================================================

共同姿態(逐條鏡 W3a probe / W3b prepare):

- **source lane 零 effect**:``driver=None`` 一律回 typed ``EXTERNAL_VERIFICATION_PENDING``
  且 ``mutation_performed=False``、零 driver 接觸;真主機動作全部經注入的 Protocol;
- **raw ingress 全拒**(硬邊界 4):任何 caller 遞交的 shell / SQL / unit 文本 / 任意目的地
  路徑 / 秘密鍵在 driver 接觸之前即 ``RAW_INGRESS_REJECTED``;target 路徑、grant SQL、
  unit bytes 一律由 **code + 封閉 manifest** 導出;
- **§10.5 #31**:host identity effect 只能分類為 ``HOST_IDENTITY_INSTALL``,且其授權必須
  含 aggregate permit——**PG permit 永遠無法授權 host user/group/directory 變更**;
- **§5.3 pre-existing-state 矩陣**與 **§5.4 ownership-aware 補償**見
  :mod:`agent_governance_s2_4_component`(本葉的共用機制,依 2000 行治理拆出並逐名 re-export)。

誠實界線:本葉「不」認證任何 runtime——九 authority / production_apply_performed /
running_attested 恆 false;真 EFFECT(aggregate 交易 / install lock / WAL / replay 落盤)
屬 W4/W6B。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_4_credential as _credential  # noqa: E402
import agent_governance_s2_4_prepare as _prepare  # noqa: E402
import agent_governance_s2_4_render as _render  # noqa: E402
import agent_governance_s2_4_topology as _topology  # noqa: E402

# 依 2000 行治理拆分下沉至 agent_governance_s2_4_component,此處逐名 re-export
# (消費者的 ``apply.<name>`` 匯入面與常量值皆不變)。
from agent_governance_s2_4_component import (  # noqa: E402,F401
    APPLY_AGGREGATE_NAMESPACE,
    APPLY_AGGREGATE_PROFILE,
    COMPENSATION_STATUS_EXACT,
    COMPENSATION_STATUS_NOT_COMPENSATED,
    COMPENSATION_STATUS_NOT_REOBSERVED,
    COMPENSATION_STATUS_RECOVERY_REQUIRED,
    COMPONENT_CLASSES,
    COMPONENT_EVIDENCE_TTL_SECONDS,
    COMPONENT_RAW_INGRESS_KEYS,
    COMPONENT_REQUIRED_PROFILES,
    COMPONENT_STATUS_AUTHORIZATION_REJECTED,
    COMPONENT_STATUS_BUNDLE_INVALID,
    COMPONENT_STATUS_CREDENTIAL_UNSATISFIED,
    COMPONENT_STATUS_FAILED,
    COMPONENT_STATUS_NOOP_VERIFIED,
    COMPONENT_STATUS_PENDING,
    COMPONENT_STATUS_POSTCHECK_ROLLED_BACK,
    COMPONENT_STATUS_PREEXISTING_UNOWNED,
    COMPONENT_STATUS_PRECHECK_FAILED,
    COMPONENT_STATUS_PRESTATE_MISMATCH,
    COMPONENT_STATUS_RAW_INGRESS_REJECTED,
    COMPONENT_STATUS_RECOVERY_REQUIRED,
    COMPONENT_STATUS_REQUEST_REJECTED,
    COMPONENT_STATUS_SATISFIED,
    COMPONENT_STATUS_SECRET_LEAK_BLOCKED,
    COMPONENT_STATUS_TOPOLOGY_UNPROVEN,
    COMPONENT_TYPED_STATUSES,
    EVIDENCE_CLASS_ATTESTED,
    EVIDENCE_CLASS_STATUS_RECORDED,
    EVIDENCE_CLASS_STATUS_SELF_DECLARATION_REFUSED,
    EVIDENCE_CLASS_STRUCTURAL_ONLY,
    FORBIDDEN_UNIT_LIFECYCLE_METHODS,
    OWNERSHIP_EVIDENCE_REQUIRED_FIELDS,
    PG_MIGRATION_NAMESPACE,
    PG_MIGRATION_PROFILE,
    POST_COMPENSATION_POSTCHECK_CONFIRMED,
    POST_COMPENSATION_POSTCHECK_DISPROVED,
    POST_COMPENSATION_POSTCHECK_UNAVAILABLE,
    POST_COMPENSATION_POSTCHECK_UNPROVEN,
    ComponentContractError,
    _ALL_FALSE_PRODUCTION_FLAGS,
    _DIGEST_RE,
    _Journal,
    _apply_permit_internal_derivation_reasons,
    _authorization_set_reasons,
    _build_postcheck,
    _build_result,
    _build_rollback,
    _compensating_failure,
    _component_precheck,
    _finish_row,
    _iso,
    _pending_verdict,
    _resolve_now,
    _subject_digest,
    _verdict,
    apply_permit_payload_binding,
    build_component_effect_intent,
    capture_pre_compensation_observation,
    classify_ownership_only,
    classify_pre_state,
    compensation_outcome,
    compensation_with_independent_postcheck,
    component_raw_ingress_reasons,
    component_row_abi,
    derive_compensation_status,
    derive_host_identity_effect_class_status,
    derive_recorded_evidence_class,
    independent_post_compensation_postcheck,
    normalize_compensation,
    ownership_binding_present,
    ownership_binding_reasons,
    ownership_evidence_reasons,
    redact_driver_error,
    scan_serializable_surface,
)
# W3b 的兩個姊妹葉亦於此彙總 re-export,讓 install 上層只需一個匯入面。
from agent_governance_s2_4_prepare import (  # noqa: E402,F401
    PREPARE_PUBLICATION_DENY_ROOTS, PREPARE_STAGING_PARENT, PREPARE_TYPED_STATUSES,
    PrepareContractError, PrepareDriver, build_prepare_core, build_prepare_intent,
    build_prepared_install_bundle, derive_prepare_route_surface_status,
    derive_prepared_bundle_status, prepare_abi_projection, prepare_id_for_core,
    prepare_journal_path, prepare_raw_ingress_reasons, prepare_route_surface_contract,
    prepare_s2_4_install_bundle, prepare_sandbox_contract, prepare_sandbox_contract_digest,
    prepared_staging_root,
)
from agent_governance_s2_4_credential import (  # noqa: E402,F401
    CLOSED_DSN_KEYS, CREDENTIAL_SLOT_PATH, FORBIDDEN_DSN_KEYS, CredentialContractError,
    CredentialInstallDriver, SealedSecretHandle, SecretBroker, SecretMaterialLeak,
    assert_no_secret_material, closed_dsn_key_contract, credential_abi_projection,
    derive_closed_dsn_key_status, derive_host_credential_capability_status,
    encrypted_credential_fingerprint,
)

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest



# 依 §10.1.1 的 2000 行治理下沉至 agent_governance_s2_4_host_identity,此處逐名 re-export
# (消費者的 ``apply.<name>`` 匯入面與常量值皆不變)。
from agent_governance_s2_4_host_identity import (  # noqa: E402,F401
    ENGINE_SCANNER_HOME,
    ENGINE_SCANNER_IDENTITY_CONTRACT,
    ENGINE_SCANNER_IDENTITY_NAME,
    ENGINE_SCANNER_SHELL,
    HOST_IDENTITY_STATIC_DIRECTORIES,
    HOST_IDENTITY_SYSTEM_ID_MAX,
    HOST_IDENTITY_SYSTEM_ID_MIN,
    S2_3_ENGINE_SCANNER_COMPONENT,
    S2_3_ENGINE_SCANNER_PG_ROLE,
    S2_3_EXPECTED_IDENTITY_REL,
    HostIdentityDriver,
    _compensate_host_identity,
    _host_identity_contract_reasons,
    _normalize_directory,
    _normalize_identity,
    _uid_gid_collision_reasons,
    apply_s2_4_host_identity,
    build_uid_gid_directory_manifest,
    host_identity_abi_projection,
    host_identity_desired_state,
    host_identity_directory_tree,
    s2_3_expected_identity_reasons,
)

# §8.1:三個不可變安裝根;digest 葉名由內容身分導出,caller 永不遞交路徑。
INSTALL_ROOTS = {
    "base_runtime_tree_digest": "/opt/arcane-equilibrium/aiml/runtimes",
    "application_bundle_digest": "/opt/arcane-equilibrium/aiml/apps",
    "launch_bundle_digest": "/opt/arcane-equilibrium/aiml/launches",
}
IMMUTABLE_TREE_MODES = {"parent": "0755", "leaf": "0555", "data_file": "0444", "executable": "0555"}
# §8.3:unit / policy / evidence / guard 的固定路徑面。
UNIT_FRAGMENT_PATH = "/etc/systemd/system/arcane-equilibrium-aiml-engine-scanner.service"
CANDIDATE_POLICY_PATH = "/etc/arcane-equilibrium/aiml/engine-scanner/candidate-policy.json"
CANDIDATE_EVIDENCE_DIR = ENGINE_SCANNER_HOME + "/candidate-evidence"
# §10.5 #21:reviewed policy template 的 in-repo 位置(renderer 的唯一輸入來源)。
CANDIDATE_POLICY_TEMPLATE_REL = "helper_scripts/deploy/openclaw-alr-candidate-policy.template.json"
CANDIDATE_POLICY_STATUS_REQUIRED = "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
INACTIVE_UNIT_POSTSTATE = {
    "LoadState": "loaded",
    "ActiveState": "inactive",
    "UnitFileState": "disabled",
    "NeedDaemonReload": "no",
    "FragmentPath": UNIT_FRAGMENT_PATH,
    "DropInPaths": "",
}


# --------------------------------------------------------------------------- #
# 2) PG_ROLE_ACL_MIGRATION
# --------------------------------------------------------------------------- #
class PgRoleAclDriver(Protocol):
    """PG role/ACL 的固定操作面;**沒有**任何 raw-SQL 入口,也沒有 host 變更方法。"""

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None: ...

    def observe_role(self, *, role_name: str) -> dict[str, Any] | None:
        """回 ``{attributes, grants}``;角色不存在回 ``None``。"""
        ...

    def create_role_with_sealed_password(
        self, *, role_name: str, secret_handle: Any, operation_id: str
    ) -> None:
        """固定 parameterized create-role;密碼只經 sealed handle 傳遞。"""
        ...

    def apply_manifest_grants(self, *, generated_statements: list[str]) -> None:
        """套用**由封閉 manifest 生成**的 REVOKE/GRANT 序列(caller 無從遞交 SQL)。"""
        ...

    def observe_grants(self, *, role_name: str) -> dict[str, Any]: ...

    def observe_public_defaults(
        self, *, database: str, schemas: list[str]
    ) -> dict[str, Any]:
        """§5.4:擷取本 plan 將要動到的 PUBLIC 預設權限**前態**(非秘密),供 exact 還原。"""
        ...

    def revoke_manifest_grants(self, *, generated_statements: list[str]) -> None: ...

    def restore_public_defaults(self, *, generated_statements: list[str]) -> None:
        """只把本 plan 自 PUBLIC 收走、且前態確實存在的那些預設權限還原回去。"""
        ...

    def drop_task_owned_role(self, *, role_name: str) -> None: ...

    def independent_postcheck(
        self, *, component_effect_class: str, install_plan_digest: str, applier_node: str
    ) -> dict[str, Any]: ...

    def trusted_host_time(self) -> str: ...


def generate_manifest_grant_statements(manifest: dict[str, Any]) -> list[str]:
    """唯一 SQL 產生點:委派 W2a 的 ``generate_engine_scanner_grant_sql``(封閉 manifest 導出)。"""

    import agent_governance_s2_4_install as _install  # 延遲匯入避免 import 循環

    return list(_install.generate_engine_scanner_grant_sql(manifest))


def generate_manifest_revoke_statements(manifest: dict[str, Any]) -> list[str]:
    """補償序列:只收回本 plan 由 manifest 授出的那些 grant(絕不動既有權限)。"""

    role = manifest["role_name"]
    statements = [
        f'REVOKE ALL ON TABLE "{entry["name"].split(".", 1)[0]}"."{entry["name"].split(".", 1)[1]}" '
        f'FROM "{role}"'
        for entry in manifest["tables"]
    ]
    statements.extend(
        f'REVOKE ALL ON SCHEMA "{entry["name"]}" FROM "{role}"' for entry in manifest["schemas"]
    )
    statements.append(
        f'REVOKE ALL PRIVILEGES ON DATABASE "{manifest["database"]["name"]}" FROM "{role}"'
    )
    return statements


def public_default_surfaces(manifest: dict[str, Any]) -> list[dict[str, str]]:
    """本 plan 會自 ``PUBLIC`` 收走的預設權限面(與 W2a 生成器的前向序列一一對應)。

    ``closed_boundary.database_temp/database_create/schema_create`` 宣稱為 false 時,前向序列
    會 ``REVOKE ... FROM PUBLIC``——那是**移除**而非新增,故 §5.4 的 exact 還原必須把它算成
    本 plan 的 task-owned delta 之一,並在補償時依**擷取的前態**原樣復原。
    """

    boundary = manifest["closed_boundary"]
    database = manifest["database"]["name"]
    surfaces: list[dict[str, str]] = []
    if boundary["database_temp"] is False:
        surfaces.append({"kind": "database", "privilege": "TEMPORARY", "object": database})
    if boundary["database_create"] is False:
        surfaces.append({"kind": "database", "privilege": "CREATE", "object": database})
    if boundary["schema_create"] is False:
        surfaces.extend(
            {"kind": "schema", "privilege": "CREATE", "object": entry["name"]}
            for entry in manifest["schemas"]
        )
    return surfaces


def public_default_surface_key(surface: dict[str, str]) -> str:
    """``kind:object:privilege`` —— PUBLIC 前態擷取的封閉鍵名(唯一構造點)。"""

    return f'{surface["kind"]}:{surface["object"]}:{surface["privilege"]}'


def public_default_pre_state_keys(manifest: dict[str, Any]) -> list[str]:
    """本 plan 會自 ``PUBLIC`` 收走的**精確**鍵集(擷取必須逐鍵覆蓋,不多不少)。"""

    return sorted(public_default_surface_key(surface) for surface in public_default_surfaces(manifest))


def derive_public_default_pre_state_status(
    manifest: dict[str, Any], public_pre_state: Any
) -> dict[str, Any]:
    """§5.4:PUBLIC 前態擷取的**變更前**分類——缺鍵/多鍵/非布林一律 UNPROVEN。

    這是 ``exact_pre_state_restored`` 的真正前提:driver 回 ``None``/``{}``/半份 dict 時,
    「缺鍵 = 未持有」的舊解讀會讓補償一條 restore 都不發、卻仍宣稱 exact 還原,把
    ``trading_ai`` 上的 PUBLIC 永久剝光(W3 review E2 P1-5)。故本函式改採
    「缺鍵 = 無法證明」,並在任何一個 plan 會剝除的面上無法證明時 fail-closed。
    """

    expected = public_default_pre_state_keys(manifest)
    if not isinstance(public_pre_state, dict):
        return {
            "status": "PUBLIC_PRESTATE_UNPROVEN",
            "reasons": [
                "the PUBLIC default-privilege pre-state capture is not an object; the plan "
                "revokes PUBLIC surfaces it then cannot prove it may restore"
            ],
            "held_surfaces": [],
            "plan_strips": expected,
        }
    observed_keys = sorted(str(key) for key in public_pre_state)
    reasons: list[str] = []
    missing = sorted(set(expected) - set(observed_keys))
    extra = sorted(set(observed_keys) - set(expected))
    if missing:
        reasons.append(
            f"the PUBLIC pre-state capture is missing {missing}; a surface this plan revokes "
            "from PUBLIC must be captured before the forward revoke or it can never be exactly "
            "restored (a missing key is NOT evidence that PUBLIC did not hold it)"
        )
    if extra:
        reasons.append(
            f"the PUBLIC pre-state capture carries out-of-plan surfaces {extra}; compensation "
            "must never restore a privilege this plan never took"
        )
    non_boolean = sorted(
        key for key in observed_keys if not isinstance(public_pre_state[key], bool)
    )
    if non_boolean:
        reasons.append(
            f"the PUBLIC pre-state capture carries non-boolean values for {non_boolean}"
        )
    if reasons:
        return {
            "status": "PUBLIC_PRESTATE_UNPROVEN", "reasons": reasons,
            "held_surfaces": [], "plan_strips": expected,
        }
    return {
        "status": "PUBLIC_PRESTATE_CAPTURED",
        "reasons": [],
        "held_surfaces": sorted(key for key in expected if public_pre_state[key] is True),
        "plan_strips": expected,
    }


def generate_public_default_restore_statements(
    manifest: dict[str, Any], public_pre_state: Any
) -> list[str]:
    """只還原「前態確實存在、且被本 plan 自 PUBLIC 收走」的預設權限(其餘一律不動)。

    ``public_pre_state`` 形如 ``{"database:trading_ai:TEMPORARY": True, ...}``:前態為假的面
    絕不被「還原」成真——補償永不授出本 plan 沒有拿走過的權限。

    **前態必須逐鍵完整**:任何一個 plan 會剝除的面缺鍵/非布林即
    ``ComponentContractError``——絕不把「缺鍵」默默當成「未持有」而少發還原語句。
    """

    if not isinstance(public_pre_state, dict):
        raise ComponentContractError("public_default_pre_state_not_captured")
    statements: list[str] = []
    for surface in public_default_surfaces(manifest):
        key = public_default_surface_key(surface)
        held = public_pre_state.get(key)
        if not isinstance(held, bool):
            raise ComponentContractError("public_default_pre_state_incomplete")
        if held is not True:
            continue
        keyword = "DATABASE" if surface["kind"] == "database" else "SCHEMA"
        statements.append(
            f'GRANT {surface["privilege"]} ON {keyword} "{surface["object"]}" TO PUBLIC'
        )
    return statements


def apply_s2_4_pg_role_acl(
    intent: Any,
    authorization_set: Any = None,
    driver: "PgRoleAclDriver | None" = None,
    *,
    acl_manifest: Any = None,
    topology_attestation: Any = None,
    expected_topology: Any = None,
    secret_handle: Any = None,
    operation_id: str = "s2-4-pg-role-acl",
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    ownership_evidence: Any = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-pg-admin-applier",
) -> dict[str, Any]:
    """``PG_ROLE_ACL_MIGRATION``:只用 W2 封閉 ACL manifest 與其生成 SQL(caller SQL 無入口)。"""

    reject, row_abi = _component_precheck(
        intent, authorization_set, replay_ledger,
        expected_class="PG_ROLE_ACL_MIGRATION", now=now,
        ingress_payloads=(), ownership_evidence=ownership_evidence,
    )
    if reject is not None:
        return reject
    fields = intent["required_intent_fields"]
    if not isinstance(acl_manifest, dict) or acl_manifest.get("self_digest") != fields[
        "acl_manifest_digest"
    ]:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the supplied pg_acl_manifest_v1 does not bind the acl_manifest_digest in the "
                "signed component intent"
            ],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
        )
    manifest_errors = central_validator.validate_aiml_artifact(acl_manifest)
    if manifest_errors:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED, manifest_errors,
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
        )
    if not isinstance(topology_attestation, dict) or topology_attestation.get(
        "self_digest"
    ) != fields["topology_attestation_digest"]:
        return _verdict(
            COMPONENT_STATUS_TOPOLOGY_UNPROVEN,
            [
                "the supplied pg_topology_attestation_v1 does not bind the digest in the signed "
                "component intent"
            ],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
        )
    topology = _topology.derive_pg_topology_status(
        topology_attestation, expected=expected_topology or {}, now=now
    )
    if topology["status"] != _topology.TOPOLOGY_STATUS_PROVEN:
        return _verdict(
            COMPONENT_STATUS_TOPOLOGY_UNPROVEN, topology["reasons"],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
        )
    try:
        grant_statements = generate_manifest_grant_statements(acl_manifest)
        revoke_statements = generate_manifest_revoke_statements(acl_manifest)
    except ValueError as error:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the closed ACL manifest could not generate its grant sequence: "
                f"{redact_driver_error(error)}"
            ],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
        )
    if driver is None:
        return _pending_verdict("PG_ROLE_ACL_MIGRATION", row_abi)

    tick = clock or (lambda: datetime.now(timezone.utc))
    journal = _Journal(driver, tick, "PG_ROLE_ACL_MIGRATION")
    role = acl_manifest["role_name"]
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    created_role = False
    database = acl_manifest["database"]["name"]
    schemas = [entry["name"] for entry in acl_manifest["schemas"]]
    try:
        observed_role = driver.observe_role(role_name=role)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"pg role pre-state observation failed: {redact_driver_error(error)}"],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    # §5.4:擷取本 plan 將自 PUBLIC 收走的預設權限前態(非秘密),供 exact 還原。
    try:
        public_pre_state = driver.observe_public_defaults(database=database, schemas=schemas)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "PUBLIC default-privilege pre-state observation failed: "
                f"{redact_driver_error(error)}"
            ],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    # §5.4:PUBLIC 前態必須在前向 REVOKE **之前**逐鍵分類;無法證明即零變更 typed 拒。
    public_status = derive_public_default_pre_state_status(acl_manifest, public_pre_state)
    if public_status["status"] != "PUBLIC_PRESTATE_CAPTURED":
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            public_status["reasons"] + [
                "the plan would strip PUBLIC surfaces it cannot prove it may take; no revoke is "
                "issued (§5.4)"
            ],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    captured_public = {key: bool(public_pre_state[key]) for key in public_status["plan_strips"]}
    public_restore = generate_public_default_restore_statements(acl_manifest, captured_public)
    if observed_role is not None:
        reject = _pre_existing_pg_role_verdict(
            driver, role=role, row_abi=row_abi, ownership_evidence=ownership_evidence,
            captured_public=captured_public, plan_strips=public_status["plan_strips"],
        )
        if reject is not None:
            return reject
        # 既有且逐位元等於前一次 S2.4 run 留下的狀態 → 零變更 NOOP(絕不重跑前向 grant,
        # 因為那會讓補償把一個既有角色剝光——§5.4 要求既有資源原樣還原而非 drop)。
        return _finish_row(
            status=COMPONENT_STATUS_NOOP_VERIFIED, reasons=[],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver=driver,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=pre_state_digest,
            applied_state_digest=_subject_digest(
                {"role": role, "grants": driver.observe_grants(role_name=role)}
            ),
            journal=journal, applier_node=applier_node, clock=tick,
            mutation_performed=False,
            compensate=lambda: compensation_outcome(compensated=True, reobserved=True),
        )

    def _compensate() -> dict[str, Any]:
        return _compensate_pg(
            driver, revoke_statements, public_restore, created_role, role,
            database=database, schemas=schemas, captured_public=captured_public,
        )

    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        if observed_role is None:
            if secret_handle is None:
                raise ComponentContractError("pg_role_requires_sealed_secret_handle")
            driver.create_role_with_sealed_password(
                role_name=role, secret_handle=secret_handle, operation_id=operation_id
            )
            created_role = True
        driver.apply_manifest_grants(generated_statements=list(grant_statements))
        observed_grants = driver.observe_grants(role_name=role)
        applied = {"role": role, "grants": observed_grants}
        journal.write("APPLIED", pre_state_digest, _subject_digest(applied))
    except Exception as error:  # noqa: BLE001
        return _compensating_failure(
            reason=f"pg role/ACL apply failed: {redact_driver_error(error)}",
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"role": role, "grants": None}),
            journal=journal, clock=tick, compensate=_compensate,
            driver=driver, applier_node=applier_node,
        )
    return _finish_row(
        status=COMPONENT_STATUS_SATISFIED, reasons=[],
        component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver=driver,
        plan_digest=plan_digest, pre_state_digest=pre_state_digest,
        post_state_digest=_subject_digest(applied),
        applied_state_digest=_subject_digest(applied), journal=journal,
        applier_node=applier_node, clock=tick, mutation_performed=True,
        compensate=_compensate, observed_subjects=applied,
    )


def _pre_existing_pg_role_verdict(
    driver: Any,
    *,
    role: str,
    row_abi: dict[str, Any],
    ownership_evidence: Any,
    captured_public: dict[str, bool],
    plan_strips: list[str],
) -> dict[str, Any] | None:
    """§5.3/§5.4:既有 PG role 的變更前分類;可以繼續(NOOP)時回 ``None``。

    S2.4 對既有角色只有兩條合法出路:**逐位元等於前一次 S2.4 run 的 applied 狀態**
    (→ 零變更 NOOP),或**零變更 typed 拒**。舊行為(task-owned 就直接重跑
    ``apply_manifest_grants``)沒有擷取角色的既有 grant/屬性,補償又因 ``created_role=False``
    不 drop、也不還原前向 ``ALTER ROLE``——結果是把一個既有角色剝光(W3 review E2 P1-6)。
    """

    ownership = (ownership_evidence or {}).get("pg_role")
    if not ownership_binding_present(ownership):
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                f"pg role {role} already exists without matching S2.4 ownership evidence; "
                "S2.4 never adopts, re-passwords or overwrites an unowned role"
            ],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    try:
        observed_grants = driver.observe_grants(role_name=role)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"pg role grant pre-state observation failed: {redact_driver_error(error)}"],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    # E2 P2-D:這一步只裁決**擁有權**(NOOP_VERIFIED vs PREEXISTING_UNOWNED_STATE)。
    # PG 沒有可宣告的 desired grant-set 供逐欄比對——真正的漂移偵測是下方對前一份 S2.4
    # receipt 的 applied_state_digest 重導出。原本把同一物件同時當 observed/desired 傳入,
    # 讀起來像在偵測漂移,實際上結構上永遠不可能回 PRESTATE_MISMATCH;改為顯式的
    # 擁有權裁決,語義與行為一致。
    state = classify_ownership_only(
        observed_subject={"role": role, "grants": observed_grants},
        ownership_evidence=ownership,
    )
    reasons: list[str] = []
    if ownership.get("applied_state_digest") != _subject_digest(
        {"role": role, "grants": observed_grants}
    ):
        reasons.append(
            f"pg role {role} exists and is task-owned, but the observed role/grant state does "
            "not re-derive the applied_state_digest of the prior S2.4 receipt; S2.4 will not "
            "mutate a role whose prior grants and attributes it cannot exactly restore"
        )
    still_held = sorted(key for key in plan_strips if captured_public.get(key) is True)
    if still_held:
        reasons.append(
            f"pg role {role} is task-owned but PUBLIC still holds {still_held}; a re-apply of "
            "the forward PUBLIC revoke cannot be compensated exactly against a pre-existing role"
        )
    if state["state"] != "NOOP_VERIFIED":
        reasons.extend(state["reasons"])
    if reasons:
        return _verdict(
            COMPONENT_STATUS_PRESTATE_MISMATCH, reasons,
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    return None


def _compensate_pg(
    driver: Any,
    revoke_statements: list[str],
    public_restore_statements: list[str],
    created_role: bool,
    role: str,
    *,
    database: str,
    schemas: list[str],
    captured_public: dict[str, bool],
) -> dict[str, Any]:
    """§5.4:收回本 plan 授出的 grant、原樣還原本 plan 自 PUBLIC 收走的預設權限;
    新建角色才 drop,既有角色一律原樣還原。``aiml_observer_ro`` 永不被觸及。

    補償跑完之後**再觀測** PUBLIC 預設權限與角色存在性,逐鍵比對擷取的前態;不相符即
    ``reobserved=False`` → ``RECOVERY_REQUIRED``(永不憑「沒拋例外」宣稱 exact 還原)。
    """

    ok = True
    try:
        driver.revoke_manifest_grants(generated_statements=list(revoke_statements))
    except Exception:  # noqa: BLE001
        ok = False
    if public_restore_statements:
        try:
            driver.restore_public_defaults(
                generated_statements=list(public_restore_statements)
            )
        except Exception:  # noqa: BLE001
            ok = False
    if created_role:
        try:
            driver.drop_task_owned_role(role_name=role)
        except Exception:  # noqa: BLE001
            ok = False
    reobserved: bool | None
    try:
        after = driver.observe_public_defaults(database=database, schemas=schemas)
        reobserved = isinstance(after, dict) and all(
            after.get(key) is value for key, value in captured_public.items()
        )
        if created_role and driver.observe_role(role_name=role) is not None:
            reobserved = False
    except Exception:  # noqa: BLE001 - 無法再觀測 = 不宣稱 exact
        reobserved = None
    return compensation_outcome(compensated=ok, reobserved=reobserved)


# --------------------------------------------------------------------------- #
# 3) CREDENTIAL_INSTALL
# --------------------------------------------------------------------------- #
def apply_s2_4_credential_install(
    intent: Any,
    authorization_set: Any = None,
    driver: "_credential.CredentialInstallDriver | None" = None,
    *,
    dsn_handle: Any = None,
    operation_id: str = "s2-4-credential-install",
    mode: str = "FIRST_PROVISION",
    previous_encrypted_blob_digest: str | None = None,
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    ownership_evidence: Any = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-host-secret-applier",
) -> dict[str, Any]:
    """``CREDENTIAL_INSTALL``:systemd-creds 加密託管的兩把 handle 交接(§7 / §10.5 #26/#32)。"""

    reject, row_abi = _component_precheck(
        intent, authorization_set, replay_ledger,
        expected_class="CREDENTIAL_INSTALL", now=now, ingress_payloads=(),
        ownership_evidence=ownership_evidence,
    )
    if reject is not None:
        return reject
    if mode not in {"FIRST_PROVISION", "ROTATION"}:
        return _verdict(
            COMPONENT_STATUS_REQUEST_REJECTED,
            [f"credential mode {mode!r} is not FIRST_PROVISION or ROTATION"],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi,
        )
    fields = intent["required_intent_fields"]
    if fields["credential_name"] != _credential.CREDENTIAL_UNIT_NAME:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                f"credential_name must be the fixed slot name {_credential.CREDENTIAL_UNIT_NAME!r} "
                "(§7; worker-selected credential names are rejected)"
            ],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi,
        )
    if driver is None:
        return _pending_verdict("CREDENTIAL_INSTALL", row_abi)

    tick = clock or (lambda: datetime.now(timezone.utc))
    journal = _Journal(driver, tick, "CREDENTIAL_INSTALL")
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    slot_path = _credential.CREDENTIAL_SLOT_PATH
    try:
        capability = driver.host_credential_capability()
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_CREDENTIAL_UNSATISFIED,
            [f"host credential capability could not be observed: {redact_driver_error(error)}"],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    capability_status = _credential.derive_host_credential_capability_status(capability)
    if capability_status["status"] != "HOST_CREDENTIAL_CAPABILITY_SATISFIED":
        return _verdict(
            COMPONENT_STATUS_CREDENTIAL_UNSATISFIED,
            capability_status["reasons"]
            + ["encrypted credential custody could not be established; zero PG/unit mutation"],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    try:
        observed_slot = driver.observe_credential_slot(slot_path=slot_path)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"credential slot pre-state observation failed: {redact_driver_error(error)}"],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    # §5.3:``task_owned`` 是 driver 的自報,必須另有 digest 綁定的 S2.4 receipt/journal
    # 佐證才成立;一個裸 dict(甚至 ``{}``)絕不足以把 PREEXISTING_UNOWNED 換成放行。
    # A7:光是「兩個欄位長得像 digest」也不夠——它們必須**逐位元等於 driver 為這個 slot
    # 報回的** 前一份 S2.4 receipt / journal digest,否則兩個 sha256:000…0 就能收養一個
    # 既有的憑證槽。driver 報不出那對 digest 的既有 slot 一律不被收養。
    slot_ownership_reasons = ownership_binding_reasons(
        (ownership_evidence or {}).get("credential_slot"),
        subject="credential_slot",
        expected_journal_digest=(
            observed_slot.get("journal_digest") if isinstance(observed_slot, dict) else None
        ),
        expected_receipt_digest=(
            observed_slot.get("s2_4_receipt_digest")
            if isinstance(observed_slot, dict) else None
        ),
    ) if isinstance(observed_slot, dict) else ["credential slot is absent"]
    owned = (
        isinstance(observed_slot, dict)
        and bool(observed_slot.get("task_owned"))
        and not slot_ownership_reasons
        and isinstance(observed_slot.get("journal_digest"), str)
        and isinstance(observed_slot.get("s2_4_receipt_digest"), str)
    )
    if observed_slot is not None and not owned:
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                "the credential slot already exists without matching S2.4 task ownership; "
                "no read, backup, adoption or rotation is performed (§5.3)"
            ] + (slot_ownership_reasons if isinstance(observed_slot, dict) else []),
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    if mode == "ROTATION" and not owned:
        return _verdict(
            COMPONENT_STATUS_PRESTATE_MISMATCH,
            [
                "ROTATION requires a prior task-owned encrypted slot; first provisioning must "
                "not be mislabelled as a rotation (§4 CREDENTIAL_ROTATION boundary)"
            ],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    if mode == "FIRST_PROVISION" and observed_slot is not None:
        return _verdict(
            COMPONENT_STATUS_PRESTATE_MISMATCH,
            ["FIRST_PROVISION requires an absent credential slot"],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    prior_digest = (
        str(observed_slot.get("encrypted_blob_digest")) if isinstance(observed_slot, dict) else None
    ) or previous_encrypted_blob_digest
    if dsn_handle is None:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the credential actor requires the broker's sealed closed-DSN handle; a caller "
                "secret value is never accepted"
            ],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        encrypted = driver.encrypt_credential(
            name=_credential.CREDENTIAL_UNIT_NAME,
            with_key=_credential.CREDENTIAL_ENCRYPT_KEY_ARG.split("=", 1)[1],
            dsn_handle=dsn_handle,
            operation_id=operation_id,
        )
        blob_digest = str((encrypted or {}).get("encrypted_blob_digest"))
        if _DIGEST_RE.fullmatch(blob_digest) is None:
            raise ComponentContractError("encrypted_blob_digest_invalid")
        if blob_digest != fields["encrypted_blob_digest"]:
            raise ComponentContractError("encrypted_blob_digest_does_not_bind_intent")
        installed = driver.install_encrypted_slot(
            slot_path=slot_path, encrypted_blob_digest=blob_digest,
            owner=_credential.CREDENTIAL_SLOT_OWNER, group=_credential.CREDENTIAL_SLOT_GROUP,
            mode=_credential.CREDENTIAL_SLOT_MODE,
        )
        slot_reasons = _credential_slot_reasons(installed, blob_digest)
        if slot_reasons:
            raise ComponentContractError("; ".join(slot_reasons))
        fingerprint = _credential.encrypted_credential_fingerprint(
            encrypted_blob_digest=blob_digest
        )
        applied = {
            "slot_path": slot_path,
            "encrypted_credential_fingerprint": fingerprint,
            "owner": _credential.CREDENTIAL_SLOT_OWNER,
            "mode": _credential.CREDENTIAL_SLOT_MODE,
            "mode_of_operation": mode,
        }
        journal.write("APPLIED", pre_state_digest, _subject_digest(applied))
        login = driver.independent_login_postcheck(
            slot_path=slot_path, role=_topology.RUNTIME_ROLE,
            endpoint=dict(_topology.RUNTIME_ENDPOINT), applier_node=applier_node,
        )
        login_reasons = _login_postcheck_reasons(login, applier_node)
        if login_reasons:
            raise ComponentContractError("; ".join(login_reasons))
        # E2 P2-E:成功 verdict 必須在 sentinel **仍存活**時建構並掃描。原本 _finish_row
        # 落在 finally 之後,而 active_secret_sentinels() 會跳過已 zeroize 的 buffer——於是
        # 唯一真正握有 closed DSN 的這一列,成功路徑的掃描剛好沒有任何 live sentinel,
        # 「每一份 verdict 都在 sentinel 存活下被掃描」的不變量恰恰在此處破掉。
        verdict = _finish_row(
            status=COMPONENT_STATUS_SATISFIED, reasons=[],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver=driver,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest(applied),
            applied_state_digest=_subject_digest(applied), journal=journal,
            applier_node=applier_node, clock=tick, mutation_performed=True,
            compensate=lambda: _compensate_credential(driver, slot_path, mode, prior_digest),
            observed_subjects=applied,
        )
        verdict["encrypted_credential_fingerprint"] = fingerprint
    except Exception as error:  # noqa: BLE001
        return _compensating_failure(
            reason=f"credential install failed: {redact_driver_error(error)}",
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"slot_path": slot_path, "state": "partial"}),
            journal=journal, clock=tick,
            compensate=lambda: _compensate_credential(driver, slot_path, mode, prior_digest),
            driver=driver, applier_node=applier_node,
        )
    finally:
        if hasattr(dsn_handle, "zeroize"):
            dsn_handle.zeroize()
    return verdict


def _credential_slot_reasons(installed: Any, blob_digest: str) -> list[str]:
    if not isinstance(installed, dict):
        return ["encrypted slot installation did not return an observation"]
    reasons: list[str] = []
    if installed.get("encrypted_blob_digest") != blob_digest:
        reasons.append("the installed slot does not carry the encrypted blob that was produced")
    if str(installed.get("owner")) != _credential.CREDENTIAL_SLOT_OWNER:
        reasons.append("the encrypted slot is not root-owned")
    if str(installed.get("mode")) != _credential.CREDENTIAL_SLOT_MODE:
        reasons.append("the encrypted slot mode is not 0600")
    if installed.get("plaintext_written") is True:
        reasons.append("a plaintext credential file was written; §7 forbids any plaintext path")
    return reasons


def _login_postcheck_reasons(login: Any, applier_node: str) -> list[str]:
    """§7 #3:經 systemd credential 託管解密並實證 end-to-end SCRAM 登入(相異 verifier)。"""

    if not isinstance(login, dict):
        return ["independent credential login postcheck did not return an object"]
    reasons: list[str] = []
    if str(login.get("verifier_node", "")) in {"", applier_node}:
        reasons.append("credential login postcheck verifier_node must differ from the applier")
    if login.get("decrypted_via_credential_custody") is not True:
        reasons.append("the postcheck did not decrypt through systemd credential custody")
    if login.get("login_verified") is not True:
        reasons.append(
            "the postcheck did not prove an end-to-end SCRAM login as aiml_engine_scanner"
        )
    dsn_status = _credential.derive_closed_dsn_key_status(login.get("observed_dsn_keys"))
    if dsn_status["status"] != "CLOSED_DSN_ACCEPTED":
        reasons.extend(dsn_status["reasons"])
    return reasons


def _compensate_credential(
    driver: Any, slot_path: str, mode: str, prior_digest: str | None
) -> dict[str, Any]:
    """§7:first-provision 移除新 slot;rotation 原樣復原前一份**密文**(絕不重建明文)。

    本 row 的補償**本身就是**再觀測:``restore_previous_slot`` / ``remove_task_owned_slot``
    的回傳即是補償後的 slot 觀測,故 ``reobserved`` 與 ``compensated`` 同源同真。
    """

    try:
        if mode == "ROTATION" and prior_digest:
            observed = driver.restore_previous_slot(
                slot_path=slot_path, previous_encrypted_blob_digest=prior_digest
            )
            restored = bool(
                isinstance(observed, dict)
                and observed.get("encrypted_blob_digest") == prior_digest
            )
            return compensation_outcome(compensated=restored, reobserved=restored)
        observed = driver.remove_task_owned_slot(slot_path=slot_path)
        removed = bool(isinstance(observed, dict) and observed.get("slot_absent"))
        return compensation_outcome(compensated=removed, reobserved=removed)
    except Exception:  # noqa: BLE001
        return compensation_outcome(compensated=False, reobserved=None)


# --------------------------------------------------------------------------- #
# 4) LEARNING_RUNTIME
# --------------------------------------------------------------------------- #
class RuntimeInstallDriver(Protocol):
    """不可變樹發佈的固定操作面;target 路徑由內容 digest 導出,caller 永不遞交路徑。"""

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None: ...

    def rehash_staging(self, *, staging_root: str) -> dict[str, Any]:
        """獨立重算 staging 的三個內容身分(APPLY 端不信任 PREPARE 的自報)。"""
        ...

    def observe_tree(self, *, target_root: str) -> dict[str, Any] | None: ...

    def publish_tree(
        self, *, staging_root: str, target_root: str, expected_digest: str, subtree: str
    ) -> dict[str, Any]:
        """同檔案系統原子發佈;回發佈後觀測(含 mode/owner/digest)。"""
        ...

    def remove_tree(self, *, target_root: str) -> None: ...

    def independent_postcheck(
        self, *, component_effect_class: str, install_plan_digest: str, applier_node: str
    ) -> dict[str, Any]: ...

    def trusted_host_time(self) -> str: ...


def install_target_root(*, identity_field: str, digest: str) -> str:
    """§8.1:三個安裝根的 digest 葉名由內容身分導出(``':'`` 不入路徑)。"""

    root = INSTALL_ROOTS.get(identity_field)
    if root is None:
        raise ComponentContractError("unknown_install_identity_field")
    if not isinstance(digest, str) or _DIGEST_RE.fullmatch(digest) is None:
        raise ComponentContractError("install_target_digest_invalid")
    return f"{root}/{digest.split(':', 1)[1]}"


def apply_s2_4_learning_runtime(
    intent: Any,
    authorization_set: Any = None,
    driver: "RuntimeInstallDriver | None" = None,
    *,
    prepared_bundle: Any = None,
    prepare_effect_receipt: Any = None,
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    ownership_evidence: Any = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-host-runtime-applier",
) -> dict[str, Any]:
    """``LEARNING_RUNTIME``:把已備妥的 base/app/launch 三樹不可變地發佈到固定 ``/opt`` 根。"""

    reject, row_abi = _component_precheck(
        intent, authorization_set, replay_ledger,
        expected_class="LEARNING_RUNTIME", now=now,
        ownership_evidence=ownership_evidence,
    )
    if reject is not None:
        return reject
    fields = intent["required_intent_fields"]
    if not isinstance(prepare_effect_receipt, dict) or prepare_effect_receipt.get(
        "self_digest"
    ) != fields["prepare_effect_receipt_digest"]:
        return _verdict(
            COMPONENT_STATUS_BUNDLE_INVALID,
            [
                "the supplied prepare effect receipt does not bind the digest in the signed "
                "component intent"
            ],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi,
        )
    bundle_status = _prepare.derive_prepared_bundle_status(
        prepared_bundle, prepare_effect_receipt, now=now
    )
    if bundle_status["status"] != "PREPARED_BUNDLE_VALID":
        return _verdict(
            COMPONENT_STATUS_BUNDLE_INVALID, bundle_status["reasons"],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi,
        )
    targets = {
        field: install_target_root(identity_field=field, digest=prepared_bundle[field])
        for field in INSTALL_ROOTS
    }
    derived_manifest = {
        "targets": targets,
        "immutable_modes": dict(IMMUTABLE_TREE_MODES),
        "base_runtime_tree_manifest_digest": prepared_bundle["base_runtime_tree_manifest_digest"],
        "application_bundle_manifest_digest": prepared_bundle["application_bundle_manifest_digest"],
        "launch_bundle_manifest_digest": prepared_bundle["launch_bundle_manifest_digest"],
    }
    if canonical_digest(derived_manifest) != fields["base_app_launch_target_manifest_digest"]:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the code-derived base/app/launch target manifest does not equal the digest bound "
                "into the signed intent (target paths are derived from content identities, never "
                "supplied by the caller)"
            ],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi,
        )
    if driver is None:
        return _pending_verdict("LEARNING_RUNTIME", row_abi)

    tick = clock or (lambda: datetime.now(timezone.utc))
    journal = _Journal(driver, tick, "LEARNING_RUNTIME")
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    staging_root = prepared_bundle["staging_locator"]["staging_root"]
    published: list[str] = []
    try:
        rehashed = driver.rehash_staging(staging_root=staging_root)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_BUNDLE_INVALID,
            [f"independent staging re-hash failed: {redact_driver_error(error)}"],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver_engaged=True,
        )
    rehash_reasons = [
        f"independently re-hashed staging {field} does not equal the prepared bundle identity"
        for field in INSTALL_ROOTS
        if (rehashed or {}).get(field) != prepared_bundle[field]
    ]
    if rehash_reasons:
        return _verdict(
            COMPONENT_STATUS_BUNDLE_INVALID, rehash_reasons,
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver_engaged=True,
        )
    try:
        pre_trees = {
            field: driver.observe_tree(target_root=target) for field, target in targets.items()
        }
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"install-root pre-state observation failed: {redact_driver_error(error)}"],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver_engaged=True,
        )
    # §5.3:三個安裝根逐一過同一條 classify_pre_state;NOOP 的樹**不再發佈**——舊行為會把
    # 一棵 task-owned 既有樹重新發佈,補償再把它 remove 掉(§5.4 只准移除證明為 absent 的
    # 新增物,W3 review E2 P1-6)。
    tree_states = {
        field: classify_pre_state(
            observed=_normalize_tree(pre_trees[field]),
            desired={"digest": prepared_bundle[field]},
            ownership_evidence=(ownership_evidence or {}).get(targets[field]),
        )
        for field in sorted(targets)
    }
    blocked = [
        (field, state) for field, state in tree_states.items()
        if state["state"] not in {"ABSENT", "NOOP_VERIFIED"}
    ]
    if blocked:
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                f"{targets[field]} already exists without matching S2.4 ownership evidence; "
                "the immutable install root is never adopted or overwritten"
                for field, _state in blocked
            ] + [reason for _field, state in blocked for reason in state["reasons"]],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver_engaged=True,
        )
    if all(state["state"] == "NOOP_VERIFIED" for state in tree_states.values()):
        return _finish_row(
            status=COMPONENT_STATUS_NOOP_VERIFIED, reasons=[],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver=driver,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=pre_state_digest,
            applied_state_digest=_subject_digest({"targets": targets, "observed": pre_trees}),
            journal=journal, applier_node=applier_node, clock=tick, mutation_performed=False,
            compensate=lambda: compensation_outcome(compensated=True, reobserved=True),
        )
    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        observed_trees: dict[str, Any] = {}
        for field, target in sorted(targets.items()):
            if tree_states[field]["state"] == "NOOP_VERIFIED":
                observed_trees[field] = pre_trees[field]
                continue
            result = driver.publish_tree(
                staging_root=staging_root, target_root=target,
                expected_digest=prepared_bundle[field], subtree=field,
            )
            published.append(target)
            tree_reasons = _immutable_tree_reasons(result, prepared_bundle[field], target)
            if tree_reasons:
                raise ComponentContractError("; ".join(tree_reasons))
            observed_trees[field] = result
        applied = {"targets": targets, "observed": observed_trees}
        journal.write("APPLIED", pre_state_digest, _subject_digest(applied))
    except Exception as error:  # noqa: BLE001
        return _compensating_failure(
            reason=f"immutable tree publication failed: {redact_driver_error(error)}",
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"targets": targets, "state": "partial"}),
            journal=journal, clock=tick,
            compensate=lambda: _compensate_trees(driver, published),
            driver=driver, applier_node=applier_node,
        )
    return _finish_row(
        status=COMPONENT_STATUS_SATISFIED, reasons=[],
        component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver=driver,
        plan_digest=plan_digest, pre_state_digest=pre_state_digest,
        post_state_digest=_subject_digest(applied),
        applied_state_digest=_subject_digest(applied), journal=journal,
        applier_node=applier_node, clock=tick, mutation_performed=True,
        compensate=lambda: _compensate_trees(driver, published),
        observed_subjects=applied,
    )


def _immutable_tree_reasons(observed: Any, expected_digest: str, target: str) -> list[str]:
    """§8.1:root:root、葉 0555、資料 0444、無 ACL、無 symlink、digest 逐一相符。"""

    if not isinstance(observed, dict):
        return [f"{target} publication did not return an observation"]
    reasons: list[str] = []
    if observed.get("digest") != expected_digest:
        reasons.append(f"{target} content digest does not equal the prepared identity")
    if str(observed.get("owner")) != "root" or str(observed.get("group")) != "root":
        reasons.append(f"{target} is not root:root owned")
    if str(observed.get("mode")) != IMMUTABLE_TREE_MODES["leaf"]:
        reasons.append(f"{target} leaf mode is not {IMMUTABLE_TREE_MODES['leaf']}")
    if observed.get("extended_acls") is True:
        reasons.append(f"{target} carries extended ACLs (forbidden)")
    if observed.get("symlinks_present") is True:
        reasons.append(f"{target} contains symlinks (forbidden)")
    if observed.get("same_filesystem_atomic_publish") is not True:
        reasons.append(f"{target} was not published atomically on the same filesystem")
    if observed.get("service_writable") is True:
        reasons.append(f"{target} is writable by the service identity (traverse/read only)")
    return reasons


def _normalize_tree(observed: Any) -> dict[str, Any] | None:
    """安裝根前態的封閉投影(內容身分即該樹的身分)。"""

    if not isinstance(observed, dict):
        return None
    return {"digest": observed.get("digest")}


def _compensate_trees(driver: Any, published: list[str]) -> dict[str, Any]:
    """§5.4:只移除本次真正發佈的樹,並在移除後**再觀測**確認其確實不存在。"""

    ok = True
    for target in reversed(published):
        try:
            driver.remove_tree(target_root=target)
        except Exception:  # noqa: BLE001
            ok = False
    reobserved: bool | None = True
    try:
        for target in published:
            if driver.observe_tree(target_root=target) is not None:
                reobserved = False
    except Exception:  # noqa: BLE001 - 無法再觀測 = 不宣稱 exact
        reobserved = None
    return compensation_outcome(compensated=ok, reobserved=reobserved)


# --------------------------------------------------------------------------- #
# 5) ENGINE_SCANNER
# --------------------------------------------------------------------------- #
class EngineScannerInstallDriver(Protocol):
    """unit/policy/guard/evidence 的固定操作面。

    **刻意沒有** enable / start / restart / signal 任何方法:S2.4 安裝後保持 disabled+inactive,
    ``enable --now`` 屬 S2.5A。:func:`assert_no_unit_lifecycle_surface` 另作執行期硬檢。
    """

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None: ...

    def observe_unit(self) -> dict[str, Any] | None: ...

    def observe_policy_file(self, *, path: str) -> dict[str, Any] | None:
        """回 candidate policy 檔的 ``{path, owner, group, mode, digest}``;不存在回 ``None``。"""
        ...

    def observe_topology_guard(self, *, path: str) -> dict[str, Any] | None:
        """回 topology guard 檔的同形觀測;不存在回 ``None``。"""
        ...

    def observe_evidence_directory(self, *, path: str) -> dict[str, Any] | None:
        """回 candidate evidence 目錄的 ``{path, owner, group, mode, empty}``;不存在回 ``None``。"""
        ...

    def install_unit_fragment(self, *, fragment_path: str, unit_text: str) -> dict[str, Any]:
        """安裝由 W2c renderer 產生的 unit bytes(caller 無從遞交 unit 文本)。"""
        ...

    def daemon_reload(self) -> None: ...

    def install_policy_file(
        self, *, path: str, policy_bytes: bytes, owner: str, group: str, mode: str
    ) -> dict[str, Any]: ...

    def install_topology_guard(
        self, *, path: str, guard_bytes: bytes, owner: str, group: str, mode: str
    ) -> dict[str, Any]: ...

    def create_evidence_directory(
        self, *, path: str, owner: str, group: str, mode: str
    ) -> dict[str, Any]: ...

    def remove_unit_fragment(self, *, fragment_path: str) -> None: ...

    def remove_policy_file(self, *, path: str) -> None: ...

    def remove_topology_guard(self, *, path: str) -> None: ...

    def remove_evidence_directory(self, *, path: str) -> None: ...

    def independent_postcheck(
        self, *, component_effect_class: str, install_plan_digest: str, applier_node: str
    ) -> dict[str, Any]: ...

    def trusted_host_time(self) -> str: ...


def _bytes_digest(payload: bytes) -> str:
    """落盤位元組的內容身分(檔案觀測與期望狀態共用的同一形)。"""

    import hashlib

    return "sha256:" + hashlib.sha256(bytes(payload)).hexdigest()


def engine_scanner_desired_subjects(
    *, policy_bytes: bytes, guard_bytes: bytes, unit_text: str
) -> dict[str, dict[str, Any]]:
    """§8.3:ENGINE_SCANNER row 四個 subject 的 code-owned 期望狀態(caller 不可選)。"""

    return {
        "policy": {
            "path": CANDIDATE_POLICY_PATH, "owner": "root",
            "group": ENGINE_SCANNER_IDENTITY_NAME, "mode": "0440",
            "digest": _bytes_digest(policy_bytes),
        },
        "guard": {
            "path": _topology.TOPOLOGY_GUARD_PATH, "owner": "root",
            "group": ENGINE_SCANNER_IDENTITY_NAME, "mode": "0440",
            "digest": _bytes_digest(guard_bytes),
        },
        "evidence": {
            "path": CANDIDATE_EVIDENCE_DIR, "owner": ENGINE_SCANNER_IDENTITY_NAME,
            "group": ENGINE_SCANNER_IDENTITY_NAME, "mode": "0700", "empty": True,
        },
        "unit": {**INACTIVE_UNIT_POSTSTATE, "fragment_digest": canonical_digest(unit_text)},
    }


def _normalize_engine_scanner_subject(
    subject: str, observed: Any, desired: dict[str, Any]
) -> dict[str, Any] | None:
    """把觀測收斂成與期望狀態**同鍵集**的投影(多餘欄位不參與分類)。"""

    if not isinstance(observed, dict):
        return None
    return {key: observed.get(key) for key in desired}


def canonical_guard_bytes(guard: dict[str, Any]) -> bytes:
    """§8.2 guard 檔的 deterministic 落盤位元組(consumer 端 self-digest 重讀的同一形)。"""

    return (
        json.dumps(dict(guard), ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def assert_no_unit_lifecycle_surface(driver: Any) -> list[str]:
    """§8.3:driver 上出現任何 enable/start/restart/signal 面即 typed 拒(絕不呼叫)。"""

    present = sorted(
        name for name in FORBIDDEN_UNIT_LIFECYCLE_METHODS if hasattr(driver, name)
    )
    if not present:
        return []
    return [
        f"the engine-scanner install driver exposes forbidden lifecycle operations {present}; "
        "S2.4 installs the unit inactive and never enables, starts, restarts or signals it "
        "(S2.5A owns `enable --now`)"
    ]


def apply_s2_4_engine_scanner_unit(
    intent: Any,
    authorization_set: Any = None,
    driver: "EngineScannerInstallDriver | None" = None,
    *,
    unit_fields: Any = None,
    candidate_policy_budgets: Any = None,
    topology_guard: Any = None,
    repo_root: Path = REPO_ROOT,
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    ownership_evidence: Any = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-host-service-applier",
) -> dict[str, Any]:
    """``ENGINE_SCANNER``:安裝 rendered unit + daemon-reload,**永不** enable/start。"""

    reject, row_abi = _component_precheck(
        intent, authorization_set, replay_ledger,
        expected_class="ENGINE_SCANNER", now=now,
        ingress_payloads=(unit_fields, candidate_policy_budgets),
        ownership_evidence=ownership_evidence,
    )
    if reject is not None:
        return reject
    fields = intent["required_intent_fields"]
    try:
        unit_text = _render.render_engine_scanner_unit(unit_fields)
    except Exception as error:  # noqa: BLE001 - renderer 的 typed 拒絕
        code = getattr(error, "code", error)
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"the unit renderer rejected the supplied contract fields: {code}"],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    try:
        policy_bytes, policy_config_hash = _render.render_candidate_policy(
            repo_root / CANDIDATE_POLICY_TEMPLATE_REL, candidate_policy_budgets
        )
    except Exception as error:  # noqa: BLE001 - §10.5 #21:任何 placeholder/null/漂移都在變更之前失敗
        code = getattr(error, "code", error)
        return _verdict(
            CANDIDATE_POLICY_STATUS_REQUIRED,
            [
                f"the candidate policy could not be rendered from the reviewed template: {code} "
                "(a missing, placeholder or mismatched configuration fails before any host mutation)"
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    policy_verdict = _render.derive_candidate_policy_status(policy_bytes, policy_config_hash)
    if policy_verdict["status"] != "PASS":
        return _verdict(
            CANDIDATE_POLICY_STATUS_REQUIRED, policy_verdict["reasons"],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    unit_verdict = _render.derive_rendered_unit_status(unit_text)
    if unit_verdict["status"] != "PASS":
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED, unit_verdict["reasons"],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    if not isinstance(topology_guard, dict) or topology_guard.get("schema_version") != (
        "pg_topology_runtime_guard_v1"
    ):
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            ["the ENGINE_SCANNER row requires the rendered pg_topology_runtime_guard_v1"],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    guard_errors = central_validator.validate_aiml_artifact(topology_guard)
    if guard_errors:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED, guard_errors,
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    manifests = {
        "unit_digest": canonical_digest(unit_text),
        "policy_config_hash": policy_config_hash,
        "guard_digest": topology_guard["self_digest"],
        "evidence_directory": CANDIDATE_EVIDENCE_DIR,
    }
    if canonical_digest(manifests) != fields["unit_policy_evidence_manifest_digest"]:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the code-derived unit/policy/evidence manifest does not equal the digest bound "
                "into the signed intent"
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    if canonical_digest(INACTIVE_UNIT_POSTSTATE) != fields["inactive_post_state_digest"]:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the signed inactive post-state digest is not the §8.3 loaded/inactive/disabled "
                "projection"
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )
    if driver is None:
        return _pending_verdict("ENGINE_SCANNER", row_abi)
    lifecycle = assert_no_unit_lifecycle_surface(driver)
    if lifecycle:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED, lifecycle,
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
        )

    tick = clock or (lambda: datetime.now(timezone.utc))
    journal = _Journal(driver, tick, "ENGINE_SCANNER")
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    installed: list[str] = []
    guard_bytes = canonical_guard_bytes(topology_guard)
    desired_subjects = engine_scanner_desired_subjects(
        policy_bytes=policy_bytes, guard_bytes=guard_bytes, unit_text=unit_text
    )
    # §5.3 / 硬邊界 11:四個 subject(policy / guard / evidence / unit)全部走同一條
    # classify_pre_state。舊行為只分類 unit,policy/guard/evidence 一律無條件安裝——
    # 一份既有的 operator policy 檔會被靜默覆寫、再被補償刪掉(W3 review E2 P1-3)。
    try:
        observed_subjects = {
            "policy": driver.observe_policy_file(path=CANDIDATE_POLICY_PATH),
            "guard": driver.observe_topology_guard(path=_topology.TOPOLOGY_GUARD_PATH),
            "evidence": driver.observe_evidence_directory(path=CANDIDATE_EVIDENCE_DIR),
            "unit": driver.observe_unit(),
        }
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "engine-scanner unit/policy/guard/evidence pre-state observation failed: "
                f"{redact_driver_error(error)}"
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver_engaged=True,
        )
    subject_states = {
        subject: classify_pre_state(
            observed=_normalize_engine_scanner_subject(
                subject, observed_subjects[subject], desired_subjects[subject]
            ),
            desired=desired_subjects[subject],
            ownership_evidence=(ownership_evidence or {}).get(subject),
        )
        for subject in sorted(desired_subjects)
    }
    drifted = [
        (subject, state) for subject, state in subject_states.items()
        if state["state"] == "PRESTATE_MISMATCH"
    ]
    if drifted:
        return _verdict(
            COMPONENT_STATUS_PRESTATE_MISMATCH,
            [f"{subject}: {reason}" for subject, state in drifted for reason in state["reasons"]]
            + [
                "an existing engine-scanner unit/policy/guard/evidence subject drifted from the "
                "signed desired state; S2.4 never overwrites it (§5.3/§5.4)"
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver_engaged=True,
        )
    unowned = [
        (subject, state) for subject, state in subject_states.items()
        if state["state"] == "PREEXISTING_UNOWNED_STATE"
    ]
    if unowned:
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                f"{desired_subjects[subject]['path'] if 'path' in desired_subjects[subject] else UNIT_FRAGMENT_PATH}"
                " already exists without matching S2.4 ownership evidence; no adoption or "
                "overwrite is performed"
                for subject, _state in unowned
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver_engaged=True,
        )
    if all(state["state"] == "NOOP_VERIFIED" for state in subject_states.values()):
        return _finish_row(
            status=COMPONENT_STATUS_NOOP_VERIFIED, reasons=[],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver=driver,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=pre_state_digest,
            applied_state_digest=_subject_digest(
                {"unit": observed_subjects["unit"], "manifests": manifests}
            ),
            journal=journal, applier_node=applier_node, clock=tick, mutation_performed=False,
            compensate=lambda: compensation_outcome(compensated=True, reobserved=True),
        )
    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        if subject_states["policy"]["state"] == "ABSENT":
            driver.install_policy_file(
                path=CANDIDATE_POLICY_PATH, policy_bytes=policy_bytes, owner="root",
                group=ENGINE_SCANNER_IDENTITY_NAME, mode="0440",
            )
            installed.append("policy")
        if subject_states["guard"]["state"] == "ABSENT":
            driver.install_topology_guard(
                path=_topology.TOPOLOGY_GUARD_PATH, guard_bytes=guard_bytes,
                owner="root", group=ENGINE_SCANNER_IDENTITY_NAME, mode="0440",
            )
            installed.append("guard")
        if subject_states["evidence"]["state"] == "ABSENT":
            evidence = driver.create_evidence_directory(
                path=CANDIDATE_EVIDENCE_DIR, owner=ENGINE_SCANNER_IDENTITY_NAME,
                group=ENGINE_SCANNER_IDENTITY_NAME, mode="0700",
            )
            installed.append("evidence")
            if not isinstance(evidence, dict) or evidence.get("empty") is not True:
                raise ComponentContractError(
                    "candidate_evidence_directory_must_be_empty_on_install"
                )
        if subject_states["unit"]["state"] == "ABSENT":
            driver.install_unit_fragment(fragment_path=UNIT_FRAGMENT_PATH, unit_text=unit_text)
            installed.append("unit")
            driver.daemon_reload()
        observed_unit = driver.observe_unit()
        unit_reasons = _inactive_unit_reasons(observed_unit, unit_text)
        if unit_reasons:
            raise ComponentContractError("; ".join(unit_reasons))
        applied = {"unit": observed_unit, "manifests": manifests}
        journal.write("APPLIED", pre_state_digest, _subject_digest(applied))
    except Exception as error:  # noqa: BLE001
        return _compensating_failure(
            reason=f"engine-scanner unit install failed: {redact_driver_error(error)}",
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"unit": UNIT_FRAGMENT_PATH, "state": "partial"}),
            journal=journal, clock=tick,
            compensate=lambda: _compensate_engine_scanner(driver, installed),
            driver=driver, applier_node=applier_node,
        )
    return _finish_row(
        status=COMPONENT_STATUS_SATISFIED, reasons=[],
        component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver=driver,
        plan_digest=plan_digest, pre_state_digest=pre_state_digest,
        post_state_digest=_subject_digest(applied),
        applied_state_digest=_subject_digest(applied), journal=journal,
        applier_node=applier_node, clock=tick, mutation_performed=True,
        compensate=lambda: _compensate_engine_scanner(driver, installed),
        observed_subjects=applied,
    )


def _inactive_unit_reasons(observed: Any, unit_text: str) -> list[str]:
    """§8.3 postcheck:loaded / inactive / disabled / no drop-in / exact fragment digest。"""

    if not isinstance(observed, dict):
        return ["unit post-state observation did not return an object"]
    reasons = [
        f"unit {key} is {observed.get(key)!r}, expected {value!r}"
        for key, value in INACTIVE_UNIT_POSTSTATE.items()
        if observed.get(key) != value
    ]
    if observed.get("fragment_digest") != canonical_digest(unit_text):
        reasons.append("the installed fragment bytes do not equal the rendered unit")
    shadowing = observed.get("shadowing_paths")
    if shadowing:
        reasons.append(f"a higher-precedence unit shadows the exact path: {shadowing}")
    if observed.get("started_by_s2_4") is True:
        reasons.append("S2.4 must never start the installed long-lived service")
    return reasons


def _compensate_engine_scanner(driver: Any, installed: list[str]) -> dict[str, Any]:
    """§5.4 逆序補償;unit bytes 回滾後必須再跑一次 typed daemon-reload。

    只移除本次分類為 ABSENT 而真正安裝的 subject(既有的 policy/guard/evidence/unit 永不
    被刪),補償後逐一**再觀測**確認其確實不存在,不相符即 ``reobserved=False``。
    """

    ok = True
    actions = {
        "unit": lambda: driver.remove_unit_fragment(fragment_path=UNIT_FRAGMENT_PATH),
        "evidence": lambda: driver.remove_evidence_directory(path=CANDIDATE_EVIDENCE_DIR),
        "guard": lambda: driver.remove_topology_guard(path=_topology.TOPOLOGY_GUARD_PATH),
        "policy": lambda: driver.remove_policy_file(path=CANDIDATE_POLICY_PATH),
    }
    observers = {
        "unit": lambda: driver.observe_unit(),
        "evidence": lambda: driver.observe_evidence_directory(path=CANDIDATE_EVIDENCE_DIR),
        "guard": lambda: driver.observe_topology_guard(path=_topology.TOPOLOGY_GUARD_PATH),
        "policy": lambda: driver.observe_policy_file(path=CANDIDATE_POLICY_PATH),
    }
    unit_rolled_back = False
    for name in reversed(installed):
        try:
            actions[name]()
            unit_rolled_back = unit_rolled_back or name == "unit"
        except Exception:  # noqa: BLE001
            ok = False
    if unit_rolled_back:
        try:
            driver.daemon_reload()
        except Exception:  # noqa: BLE001
            ok = False
    reobserved: bool | None = True
    try:
        for name in installed:
            if observers[name]() is not None:
                reobserved = False
    except Exception:  # noqa: BLE001 - 無法再觀測 = 不宣稱 exact
        reobserved = None
    return compensation_outcome(compensated=ok, reobserved=reobserved)


# --------------------------------------------------------------------------- #
# W3 exported-ABI 折入面
# --------------------------------------------------------------------------- #
def apply_abi_projection() -> dict[str, Any]:
    """W3 exported-ABI 的五 APPLY row 面(骨架 + row ABI/路徑導出的活再導出)。"""

    try:
        row_abis = {name: component_row_abi(name) for name in COMPONENT_CLASSES}
    except Exception:  # noqa: BLE001 - 任何逸出 = fail-closed 未證
        row_abis = None
    try:
        target_probe = {
            field: install_target_root(identity_field=field, digest="sha256:" + "0" * 64)
            for field in INSTALL_ROOTS
        }
    except Exception:  # noqa: BLE001
        target_probe = None
    return {
        "component_entrypoints": {
            "HOST_IDENTITY_INSTALL": (
                "agent_governance_s2_4_host_identity.apply_s2_4_host_identity"
            ),
            "PG_ROLE_ACL_MIGRATION": "agent_governance_s2_4_apply.apply_s2_4_pg_role_acl",
            "CREDENTIAL_INSTALL": "agent_governance_s2_4_apply.apply_s2_4_credential_install",
            "LEARNING_RUNTIME": "agent_governance_s2_4_apply.apply_s2_4_learning_runtime",
            "ENGINE_SCANNER": "agent_governance_s2_4_apply.apply_s2_4_engine_scanner_unit",
        },
        "component_driver_protocols": [
            "agent_governance_s2_4_host_identity.HostIdentityDriver",
            "agent_governance_s2_4_apply.PgRoleAclDriver",
            "agent_governance_s2_4_credential.CredentialInstallDriver",
            "agent_governance_s2_4_apply.RuntimeInstallDriver",
            "agent_governance_s2_4_apply.EngineScannerInstallDriver",
        ],
        "component_typed_statuses": list(COMPONENT_TYPED_STATUSES),
        "component_row_abis": row_abis,
        "component_required_profiles": {
            name: list(profiles) for name, profiles in COMPONENT_REQUIRED_PROFILES.items()
        },
        "component_raw_ingress_keys": list(COMPONENT_RAW_INGRESS_KEYS),
        "forbidden_unit_lifecycle_methods": list(FORBIDDEN_UNIT_LIFECYCLE_METHODS),
        # §8 / S2.3:HOST_IDENTITY 葉的 ABI 面(契約 digest + UID/GID 三重把關)。
        **host_identity_abi_projection(),
        # §5.3/§5.4:ownership_evidence 的封閉形狀與補償 typed 三分的活再導出。
        "ownership_evidence_required_fields": list(OWNERSHIP_EVIDENCE_REQUIRED_FIELDS),
        "bare_ownership_object_rejected": bool(
            ownership_evidence_reasons({"unit": {}})
        ),
        "compensation_statuses": [
            COMPENSATION_STATUS_EXACT,
            COMPENSATION_STATUS_NOT_REOBSERVED,
            COMPENSATION_STATUS_NOT_COMPENSATED,
            COMPENSATION_STATUS_RECOVERY_REQUIRED,
        ],
        "absent_exception_does_not_claim_exact": (
            derive_compensation_status(
                compensation_outcome(compensated=True, reobserved=None)
            )[0] == COMPENSATION_STATUS_NOT_REOBSERVED
        ),
        # §10.2:自報 attested evidence_class 一律被閘拒(fixture 無法鑄造 runtime 信任)。
        "self_declared_attested_evidence_class_refused": (
            derive_recorded_evidence_class(
                type("_SelfDeclared", (), {"evidence_class": "PLATFORM_ATTESTED"})()
            )["recorded_evidence_class"] == EVIDENCE_CLASS_STRUCTURAL_ONLY
        ),
        "engine_scanner_pre_state_subjects": ["evidence", "guard", "policy", "unit"],
        "install_roots": dict(INSTALL_ROOTS),
        "install_target_probe": target_probe,
        "immutable_tree_modes": dict(IMMUTABLE_TREE_MODES),
        "inactive_unit_post_state": dict(INACTIVE_UNIT_POSTSTATE),
        "unit_fragment_path": UNIT_FRAGMENT_PATH,
        "candidate_policy_path": CANDIDATE_POLICY_PATH,
        "candidate_evidence_dir": CANDIDATE_EVIDENCE_DIR,
        "schema_ids": [
            "s2_4_component_effect_intent_v1",
            "s2_4_component_effect_postcheck_v1",
            "s2_4_component_effect_result_v1",
            "s2_4_component_effect_rollback_v1",
        ],
    }

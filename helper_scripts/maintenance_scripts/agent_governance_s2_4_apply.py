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
    COMPONENT_STATUS_TOPOLOGY_UNPROVEN,
    COMPONENT_TYPED_STATUSES,
    FORBIDDEN_UNIT_LIFECYCLE_METHODS,
    PG_MIGRATION_NAMESPACE,
    PG_MIGRATION_PROFILE,
    ComponentContractError,
    _ALL_FALSE_PRODUCTION_FLAGS,
    _DIGEST_RE,
    _Journal,
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
    build_component_effect_intent,
    classify_pre_state,
    component_raw_ingress_reasons,
    component_row_abi,
    derive_host_identity_effect_class_status,
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


# ── §8/§8.1/§8.3 host identity 與靜態目錄樹(worker 不得選)──────────────────────
ENGINE_SCANNER_IDENTITY_NAME = "aiml-engine-scanner"
ENGINE_SCANNER_HOME = "/var/lib/arcane-equilibrium/aiml/engine-scanner"
ENGINE_SCANNER_SHELL = "/usr/sbin/nologin"
ENGINE_SCANNER_IDENTITY_CONTRACT = {
    "name": ENGINE_SCANNER_IDENTITY_NAME,
    "group": ENGINE_SCANNER_IDENTITY_NAME,
    "home": ENGINE_SCANNER_HOME,
    "shell": ENGINE_SCANNER_SHELL,
    "password_locked": True,
    "supplementary_groups": [],
    "account_expiry": None,
    "system_account": True,
    "interactive_login": False,
}
HOST_IDENTITY_STATIC_DIRECTORIES = (
    {"path": "/opt/arcane-equilibrium/aiml/apps", "owner": "root", "group": "root", "mode": "0755"},
    {"path": "/opt/arcane-equilibrium/aiml/launches", "owner": "root", "group": "root", "mode": "0755"},
    {"path": "/opt/arcane-equilibrium/aiml/runtimes", "owner": "root", "group": "root", "mode": "0755"},
    {
        "path": "/etc/arcane-equilibrium/aiml/engine-scanner",
        "owner": "root",
        "group": ENGINE_SCANNER_IDENTITY_NAME,
        "mode": "0750",
    },
    {
        "path": ENGINE_SCANNER_HOME,
        "owner": ENGINE_SCANNER_IDENTITY_NAME,
        "group": ENGINE_SCANNER_IDENTITY_NAME,
        "mode": "0700",
    },
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
# 1) HOST_IDENTITY_INSTALL
# --------------------------------------------------------------------------- #
class HostIdentityDriver(Protocol):
    """host 身分/靜態目錄的固定操作面;caller 永不遞交 shell 或任意路徑。"""

    evidence_class: str

    def journal_transition(self, *, entry: dict[str, Any]) -> None: ...

    def observe_identity(self, *, name: str) -> dict[str, Any] | None:
        """回 passwd/shadow/group/NSS 觀測;不存在回 ``None``。"""
        ...

    def create_system_account(
        self, *, name: str, uid: int, gid: int, home: str, shell: str
    ) -> None:
        """建立 system account(locked password、無 supplementary group、無到期)。"""
        ...

    def remove_system_account(self, *, name: str) -> None: ...

    def observe_directory(self, *, path: str) -> dict[str, Any] | None: ...

    def create_directory(self, *, path: str, owner: str, group: str, mode: str) -> None: ...

    def remove_directory(self, *, path: str) -> None: ...

    def independent_postcheck(
        self, *, component_effect_class: str, install_plan_digest: str, applier_node: str
    ) -> dict[str, Any]: ...

    def trusted_host_time(self) -> str: ...


def host_identity_desired_state(*, uid: int, gid: int) -> dict[str, Any]:
    """§8 的 code-owned 期望身分(UID/GID 由被簽 manifest 供給,其餘全部凍結)。"""

    desired = dict(ENGINE_SCANNER_IDENTITY_CONTRACT)
    desired["uid"] = int(uid)
    desired["gid"] = int(gid)
    return desired


def host_identity_directory_tree() -> list[dict[str, Any]]:
    return [dict(entry) for entry in HOST_IDENTITY_STATIC_DIRECTORIES]


def build_uid_gid_directory_manifest(*, uid: int, gid: int) -> dict[str, Any]:
    """被 intent 以 digest 綁定的 UID/GID/目錄 manifest(唯一構造點)。"""

    return {
        "schema_version": "s2_4_uid_gid_directory_manifest_v1_informal",
        "identity": host_identity_desired_state(uid=uid, gid=gid),
        "static_directories": host_identity_directory_tree(),
    }


def apply_s2_4_host_identity(
    intent: Any,
    authorization_set: Any = None,
    driver: "HostIdentityDriver | None" = None,
    *,
    uid_gid_directory_manifest: Any = None,
    now: str | datetime | None = None,
    replay_ledger: Any = None,
    ownership_evidence: Any = None,
    clock: Callable[[], datetime] | None = None,
    applier_node: str = "s2-4-host-identity-applier",
) -> dict[str, Any]:
    """``HOST_IDENTITY_INSTALL``:exact S2.3 身分 + 靜態目錄樹;屬性漂移在變更之前即停手。"""

    reject, row_abi = _component_precheck(
        intent, authorization_set, replay_ledger,
        expected_class="HOST_IDENTITY_INSTALL", now=now,
    )
    if reject is not None:
        return reject
    fields = intent["required_intent_fields"]
    if not isinstance(uid_gid_directory_manifest, dict) or canonical_digest(
        uid_gid_directory_manifest
    ) != fields["uid_gid_directory_manifest_digest"]:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [
                "the supplied UID/GID/directory manifest does not re-derive the digest bound "
                "into the signed component intent"
            ],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi,
        )
    desired_identity = uid_gid_directory_manifest.get("identity")
    desired_dirs = uid_gid_directory_manifest.get("static_directories")
    contract_reasons = _host_identity_contract_reasons(desired_identity, desired_dirs)
    if contract_reasons:
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED, contract_reasons,
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi,
        )
    if driver is None:
        return _pending_verdict("HOST_IDENTITY_INSTALL", row_abi)

    tick = clock or (lambda: datetime.now(timezone.utc))
    journal = _Journal(driver, tick)
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    created_dirs: list[str] = []
    created_account = False
    try:
        observed_identity = driver.observe_identity(name=desired_identity["name"])
        identity_state = classify_pre_state(
            observed=_normalize_identity(observed_identity),
            desired=_normalize_identity(desired_identity),
            ownership_evidence=(ownership_evidence or {}).get("identity"),
        )
        observed_dirs = {
            entry["path"]: driver.observe_directory(path=entry["path"]) for entry in desired_dirs
        }
        dir_states = {
            entry["path"]: classify_pre_state(
                observed=_normalize_directory(observed_dirs[entry["path"]]),
                desired=_normalize_directory(entry),
                ownership_evidence=(ownership_evidence or {}).get(entry["path"]),
            )
            for entry in desired_dirs
        }
    except Exception as error:  # noqa: BLE001 - 觀測逸出 = 零變更 typed 失敗
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"host identity pre-state observation failed: {error}"],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    # §10.5 #37:任何 service-account / 目錄屬性漂移在第一次變更之前失敗。漂移(PRESTATE_MISMATCH)
    # 的優先序高於「未擁有」——只要任一 subject 漂移,整個 row 就停手,不論其他 subject 的狀態。
    blocking = [("identity", identity_state)] + sorted(dir_states.items())
    drifted = [(label, state) for label, state in blocking if state["state"] == "PRESTATE_MISMATCH"]
    if drifted:
        return _verdict(
            COMPONENT_STATUS_PRESTATE_MISMATCH,
            [f"{label}: {reason}" for label, state in drifted for reason in state["reasons"]]
            + ["service-account/directory attribute drift fails before any mutation (§10.5 #37)"],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    unowned = [
        (label, state) for label, state in blocking
        if state["state"] == "PREEXISTING_UNOWNED_STATE"
    ]
    if unowned:
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [f"{label}: {reason}" for label, state in unowned for reason in state["reasons"]],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    if identity_state["state"] == "NOOP_VERIFIED" and all(
        state["state"] == "NOOP_VERIFIED" for state in dir_states.values()
    ):
        return _finish_row(
            status=COMPONENT_STATUS_NOOP_VERIFIED, reasons=[],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver=driver,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=pre_state_digest,
            applied_state_digest=_subject_digest(uid_gid_directory_manifest),
            journal=journal, applier_node=applier_node, clock=tick,
            mutation_performed=False, compensate=lambda: True,
        )
    absent_state = _subject_digest({"identity": None, "directories": {}})
    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        if identity_state["state"] == "ABSENT":
            driver.create_system_account(
                name=desired_identity["name"],
                uid=int(desired_identity["uid"]),
                gid=int(desired_identity["gid"]),
                home=desired_identity["home"],
                shell=desired_identity["shell"],
            )
            created_account = True
        for entry in desired_dirs:
            if dir_states[entry["path"]]["state"] == "ABSENT":
                driver.create_directory(
                    path=entry["path"], owner=entry["owner"], group=entry["group"],
                    mode=entry["mode"],
                )
                created_dirs.append(entry["path"])
        applied = {
            "identity": _normalize_identity(driver.observe_identity(name=desired_identity["name"])),
            "directories": {
                entry["path"]: _normalize_directory(driver.observe_directory(path=entry["path"]))
                for entry in desired_dirs
            },
        }
        journal.write("APPLIED", pre_state_digest, _subject_digest(applied))
    except Exception as error:  # noqa: BLE001
        return _compensating_failure(
            reason=f"host identity apply failed: {error}",
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=absent_state, journal=journal, clock=tick,
            compensate=lambda: _compensate_host_identity(
                driver, created_account, created_dirs, desired_identity["name"]
            ),
        )
    expected = {
        "identity": _normalize_identity(desired_identity),
        "directories": {entry["path"]: _normalize_directory(entry) for entry in desired_dirs},
    }
    if applied != expected:
        return _compensating_failure(
            reason=(
                "the observed post-apply host identity/directory tree does not equal the signed "
                "desired state"
            ),
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest(applied), journal=journal, clock=tick,
            compensate=lambda: _compensate_host_identity(
                driver, created_account, created_dirs, desired_identity["name"]
            ),
        )
    return _finish_row(
        status=COMPONENT_STATUS_SATISFIED, reasons=[],
        component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver=driver,
        plan_digest=plan_digest, pre_state_digest=pre_state_digest,
        post_state_digest=_subject_digest(applied),
        applied_state_digest=_subject_digest(applied), journal=journal,
        applier_node=applier_node, clock=tick, mutation_performed=True,
        compensate=lambda: _compensate_host_identity(
            driver, created_account, created_dirs, desired_identity["name"]
        ),
        observed_subjects=applied,
    )


def _host_identity_contract_reasons(identity: Any, directories: Any) -> list[str]:
    """被簽 manifest 必須逐欄等於 §8 的 code-owned 身分/目錄契約。"""

    reasons: list[str] = []
    if not isinstance(identity, dict):
        return ["uid/gid manifest identity must be an object"]
    for key, value in ENGINE_SCANNER_IDENTITY_CONTRACT.items():
        if identity.get(key) != value:
            reasons.append(
                f"host identity {key}={identity.get(key)!r} is not the §8 contract value {value!r}"
            )
    for key in ("uid", "gid"):
        value = identity.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            reasons.append(f"host identity {key} must be a positive integer from the signed plan")
    if not isinstance(directories, list) or [
        {k: entry.get(k) for k in ("path", "owner", "group", "mode")}
        for entry in directories
        if isinstance(entry, dict)
    ] != host_identity_directory_tree():
        reasons.append(
            "the static directory manifest is not the exact §8/§8.1 owner/mode tree "
            "(worker-selected directories or modes are rejected)"
        )
    return reasons


def _normalize_identity(observed: Any) -> dict[str, Any] | None:
    if not isinstance(observed, dict):
        return None
    keys = tuple(ENGINE_SCANNER_IDENTITY_CONTRACT) + ("uid", "gid")
    return {key: observed.get(key) for key in keys}


def _normalize_directory(observed: Any) -> dict[str, Any] | None:
    if not isinstance(observed, dict):
        return None
    return {key: observed.get(key) for key in ("path", "owner", "group", "mode")}


def _compensate_host_identity(
    driver: Any, created_account: bool, created_dirs: list[str], name: str
) -> bool:
    """§5.4 ownership-aware:只移除本次證明為 absent 且已標 task-owned 的新增物。"""

    ok = True
    for path in reversed(created_dirs):
        try:
            driver.remove_directory(path=path)
        except Exception:  # noqa: BLE001
            ok = False
    if created_account:
        try:
            driver.remove_system_account(name=name)
        except Exception:  # noqa: BLE001
            ok = False
    return ok


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


def generate_public_default_restore_statements(
    manifest: dict[str, Any], public_pre_state: Any
) -> list[str]:
    """只還原「前態確實存在、且被本 plan 自 PUBLIC 收走」的預設權限(其餘一律不動)。

    ``public_pre_state`` 形如 ``{"database:trading_ai:TEMPORARY": True, ...}``:前態為假的面
    絕不被「還原」成真——補償永不授出本 plan 沒有拿走過的權限。
    """

    held = public_pre_state if isinstance(public_pre_state, dict) else {}
    statements: list[str] = []
    for surface in public_default_surfaces(manifest):
        key = f'{surface["kind"]}:{surface["object"]}:{surface["privilege"]}'
        if held.get(key) is not True:
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
        ingress_payloads=(),
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
            [f"the closed ACL manifest could not generate its grant sequence: {error}"],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
        )
    if driver is None:
        return _pending_verdict("PG_ROLE_ACL_MIGRATION", row_abi)

    tick = clock or (lambda: datetime.now(timezone.utc))
    journal = _Journal(driver, tick)
    role = acl_manifest["role_name"]
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    created_role = False
    try:
        observed_role = driver.observe_role(role_name=role)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"pg role pre-state observation failed: {error}"],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    if observed_role is not None:
        ownership = (ownership_evidence or {}).get("pg_role")
        if not (
            isinstance(ownership, dict)
            and ownership.get("s2_4_receipt_digest")
            and ownership.get("journal_digest")
        ):
            return _verdict(
                COMPONENT_STATUS_PREEXISTING_UNOWNED,
                [
                    f"pg role {role} already exists without matching S2.4 ownership evidence; "
                    "S2.4 never adopts, re-passwords or overwrites an unowned role"
                ],
                component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
                driver_engaged=True,
            )
    # §5.4:擷取本 plan 將自 PUBLIC 收走的預設權限前態(非秘密),供 exact 還原。
    try:
        public_pre_state = driver.observe_public_defaults(
            database=acl_manifest["database"]["name"],
            schemas=[entry["name"] for entry in acl_manifest["schemas"]],
        )
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"PUBLIC default-privilege pre-state observation failed: {error}"],
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi, driver_engaged=True,
        )
    public_restore = generate_public_default_restore_statements(acl_manifest, public_pre_state)

    def _compensate() -> bool:
        return _compensate_pg(driver, revoke_statements, public_restore, created_role, role)

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
            reason=f"pg role/ACL apply failed: {error}",
            component_effect_class="PG_ROLE_ACL_MIGRATION", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"role": role, "grants": None}),
            journal=journal, clock=tick, compensate=_compensate,
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


def _compensate_pg(
    driver: Any,
    revoke_statements: list[str],
    public_restore_statements: list[str],
    created_role: bool,
    role: str,
) -> bool:
    """§5.4:收回本 plan 授出的 grant、原樣還原本 plan 自 PUBLIC 收走的預設權限;
    新建角色才 drop,既有角色一律原樣還原。``aiml_observer_ro`` 永不被觸及。"""

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
    return ok


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
    journal = _Journal(driver, tick)
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    slot_path = _credential.CREDENTIAL_SLOT_PATH
    try:
        capability = driver.host_credential_capability()
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_CREDENTIAL_UNSATISFIED,
            [f"host credential capability could not be observed: {error}"],
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
            [f"credential slot pre-state observation failed: {error}"],
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    owned = (
        isinstance(observed_slot, dict)
        and bool(observed_slot.get("task_owned"))
        and isinstance((ownership_evidence or {}).get("credential_slot"), dict)
    )
    if observed_slot is not None and not owned:
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                "the credential slot already exists without matching S2.4 task ownership; "
                "no read, backup, adoption or rotation is performed (§5.3)"
            ],
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
    except Exception as error:  # noqa: BLE001
        return _compensating_failure(
            reason=f"credential install failed: {error}",
            component_effect_class="CREDENTIAL_INSTALL", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"slot_path": slot_path, "state": "partial"}),
            journal=journal, clock=tick,
            compensate=lambda: _compensate_credential(driver, slot_path, mode, prior_digest),
        )
    finally:
        if hasattr(dsn_handle, "zeroize"):
            dsn_handle.zeroize()
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
) -> bool:
    """§7:first-provision 移除新 slot;rotation 原樣復原前一份**密文**(絕不重建明文)。"""

    try:
        if mode == "ROTATION" and prior_digest:
            observed = driver.restore_previous_slot(
                slot_path=slot_path, previous_encrypted_blob_digest=prior_digest
            )
            return bool(
                isinstance(observed, dict)
                and observed.get("encrypted_blob_digest") == prior_digest
            )
        observed = driver.remove_task_owned_slot(slot_path=slot_path)
        return bool(isinstance(observed, dict) and observed.get("slot_absent"))
    except Exception:  # noqa: BLE001
        return False


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
    journal = _Journal(driver, tick)
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    staging_root = prepared_bundle["staging_locator"]["staging_root"]
    published: list[str] = []
    try:
        rehashed = driver.rehash_staging(staging_root=staging_root)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_BUNDLE_INVALID,
            [f"independent staging re-hash failed: {error}"],
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
            [f"install-root pre-state observation failed: {error}"],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver_engaged=True,
        )
    for field, observed in pre_trees.items():
        if observed is None:
            continue
        ownership = (ownership_evidence or {}).get(targets[field])
        if isinstance(ownership, dict) and ownership.get("s2_4_receipt_digest") and (
            observed.get("digest") == prepared_bundle[field]
        ):
            continue
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                f"{targets[field]} already exists without matching S2.4 ownership evidence; "
                "the immutable install root is never adopted or overwritten"
            ],
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi, driver_engaged=True,
        )
    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        observed_trees: dict[str, Any] = {}
        for field, target in sorted(targets.items()):
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
            reason=f"immutable tree publication failed: {error}",
            component_effect_class="LEARNING_RUNTIME", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"targets": targets, "state": "partial"}),
            journal=journal, clock=tick,
            compensate=lambda: _compensate_trees(driver, published),
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


def _compensate_trees(driver: Any, published: list[str]) -> bool:
    ok = True
    for target in reversed(published):
        try:
            driver.remove_tree(target_root=target)
        except Exception:  # noqa: BLE001
            ok = False
    return ok


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
    journal = _Journal(driver, tick)
    plan_digest = intent["install_plan_digest"]
    pre_state_digest = intent["pre_state_digest"]
    installed: list[str] = []
    try:
        pre_unit = driver.observe_unit()
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"unit pre-state observation failed: {error}"],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver_engaged=True,
        )
    if pre_unit is not None and not isinstance(
        (ownership_evidence or {}).get("unit"), dict
    ):
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED,
            [
                f"{UNIT_FRAGMENT_PATH} already exists without matching S2.4 ownership evidence; "
                "no adoption or overwrite is performed"
            ],
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi, driver_engaged=True,
        )
    try:
        journal.write("APPLYING", pre_state_digest, pre_state_digest)
        driver.install_policy_file(
            path=CANDIDATE_POLICY_PATH, policy_bytes=policy_bytes, owner="root",
            group=ENGINE_SCANNER_IDENTITY_NAME, mode="0440",
        )
        installed.append("policy")
        driver.install_topology_guard(
            path=_topology.TOPOLOGY_GUARD_PATH,
            guard_bytes=canonical_guard_bytes(topology_guard),
            owner="root", group=ENGINE_SCANNER_IDENTITY_NAME, mode="0440",
        )
        installed.append("guard")
        evidence = driver.create_evidence_directory(
            path=CANDIDATE_EVIDENCE_DIR, owner=ENGINE_SCANNER_IDENTITY_NAME,
            group=ENGINE_SCANNER_IDENTITY_NAME, mode="0700",
        )
        installed.append("evidence")
        if not isinstance(evidence, dict) or evidence.get("empty") is not True:
            raise ComponentContractError("candidate_evidence_directory_must_be_empty_on_install")
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
            reason=f"engine-scanner unit install failed: {error}",
            component_effect_class="ENGINE_SCANNER", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=_subject_digest({"unit": UNIT_FRAGMENT_PATH, "state": "partial"}),
            journal=journal, clock=tick,
            compensate=lambda: _compensate_engine_scanner(driver, installed),
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


def _compensate_engine_scanner(driver: Any, installed: list[str]) -> bool:
    """§5.4 逆序補償;unit bytes 回滾後必須再跑一次 typed daemon-reload。"""

    ok = True
    actions = {
        "unit": lambda: driver.remove_unit_fragment(fragment_path=UNIT_FRAGMENT_PATH),
        "evidence": lambda: driver.remove_evidence_directory(path=CANDIDATE_EVIDENCE_DIR),
        "guard": lambda: driver.remove_topology_guard(path=_topology.TOPOLOGY_GUARD_PATH),
        "policy": lambda: driver.remove_policy_file(path=CANDIDATE_POLICY_PATH),
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
    return ok


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
            "HOST_IDENTITY_INSTALL": "agent_governance_s2_4_apply.apply_s2_4_host_identity",
            "PG_ROLE_ACL_MIGRATION": "agent_governance_s2_4_apply.apply_s2_4_pg_role_acl",
            "CREDENTIAL_INSTALL": "agent_governance_s2_4_apply.apply_s2_4_credential_install",
            "LEARNING_RUNTIME": "agent_governance_s2_4_apply.apply_s2_4_learning_runtime",
            "ENGINE_SCANNER": "agent_governance_s2_4_apply.apply_s2_4_engine_scanner_unit",
        },
        "component_driver_protocols": [
            "agent_governance_s2_4_apply.HostIdentityDriver",
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
        "host_identity_contract_digest": canonical_digest({
            "identity": ENGINE_SCANNER_IDENTITY_CONTRACT,
            "static_directories": host_identity_directory_tree(),
        }),
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

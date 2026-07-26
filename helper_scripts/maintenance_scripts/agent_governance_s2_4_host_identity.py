#!/usr/bin/env python3
"""S2.4(WP4·W3b)``HOST_IDENTITY_INSTALL`` row 的 typed 主機 driver 葉(§8 / §10.5 #31/#37)。

依 §10.1.1 的 2000 行治理自 :mod:`agent_governance_s2_4_apply` 拆出的**行為守恆**葉;
apply 上層逐名 re-export,消費者的 ``apply.<name>`` 匯入面與常量值皆不變。

本葉承載 §8 的 code-owned service-account 契約與它的三重 UID/GID 把關:

1. **S2.3 cross-check**:``uid_label`` / ``pg_role`` / ``non_root`` 逐欄比對 repo 內的
   ``expected_identity_receipt_v1``(caller 既不遞交路徑也不遞交內容);
2. **system-account 區間**:被簽 manifest 的數值 uid/gid 必須落在
   ``[HOST_IDENTITY_SYSTEM_ID_MIN, HOST_IDENTITY_SYSTEM_ID_MAX]``;
3. **變更前碰撞觀測**:該數值若已屬於別的帳號/群組即 typed 拒(零變更)。

誠實界線:S2.3 artifact **沒有**數值 UID/GID 欄位,故數值本身無法 pin 到 S2.3;
本葉不宣稱它做得到(見 :func:`s2_3_expected_identity_reasons` 的 docstring)。
九 authority / production_apply_performed / running_attested 恆 false。
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
from agent_governance_s2_4_component import (  # noqa: E402
    COMPONENT_STATUS_NOOP_VERIFIED,
    COMPONENT_STATUS_PREEXISTING_UNOWNED,
    COMPONENT_STATUS_PRECHECK_FAILED,
    COMPONENT_STATUS_PRESTATE_MISMATCH,
    COMPONENT_STATUS_SATISFIED,
    _Journal,
    _compensating_failure,
    _component_precheck,
    _finish_row,
    _pending_verdict,
    _subject_digest,
    _verdict,
    classify_pre_state,
    compensation_outcome,
    derive_compensation_status,
    ownership_evidence_reasons,
    redact_driver_error,
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
# §8 / S2.3:UID/GID 的 code-owned 合法區間。
#
# 誠實界線(load-bearing):S2.3 的 ``expected_identity_receipt_v1`` **不帶數值 UID/GID**
# ——它只綁 ``uid_label``/``pg_role``/``non_root``,並明載 ``production_provisioned.uid=false``。
# 因此「把數值 UID pin 到 S2.3」在今天的 artifact 面上不可能;可證的最強形式是三重:
#   (1) 對 S2.3 artifact 逐欄 cross-check 標籤/角色/non-root 面(非 caller 值);
#   (2) 數值必須落在 system-account 配置區間(排除 root 與一切人類/服務既有低號身分);
#   (3) 對主機做「該 UID/GID 是否已被別的帳號佔用」的**變更前**觀測,碰撞即 typed 拒。
# 少了 (3),一份把 uid=gid=26 寫進被簽 manifest 的 plan 會讓 scanner 身分與 postgres 共用
# UID——kernel 眼中 scanner **就是** postgres(local socket peer-auth + data dir 讀取),
# 整條 PG_ROLE_ACL_MIGRATION 邊界形同虛設(W3 review E3 P1-3)。
HOST_IDENTITY_SYSTEM_ID_MIN = 100
HOST_IDENTITY_SYSTEM_ID_MAX = 999
# S2.3 expected-identity artifact 的 in-repo 位置(caller 永不遞交此路徑或其內容)。
S2_3_EXPECTED_IDENTITY_REL = (
    "docs/execution_plan/ai_ml_landing/receipts/S2.3-expected-identity-receipt-v1.json"
)
S2_3_ENGINE_SCANNER_COMPONENT = "engine_scanner"
S2_3_ENGINE_SCANNER_PG_ROLE = "aiml_engine_scanner"
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

    def observe_account_by_uid(self, *, uid: int) -> dict[str, Any] | None:
        """反查:該數值 UID 目前屬於誰(``{"name": ...}``);無人佔用回 ``None``。"""
        ...

    def observe_group_by_gid(self, *, gid: int) -> dict[str, Any] | None:
        """反查:該數值 GID 目前屬於哪個群組;無人佔用回 ``None``。"""
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
        ownership_evidence=ownership_evidence,
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
    journal = _Journal(driver, tick, "HOST_IDENTITY_INSTALL")
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
            [f"host identity pre-state observation failed: {redact_driver_error(error)}"],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    # §10.5 #37 之前:數值 UID/GID 的**佔用**觀測(pre-state 分類只按名字比對,擋不住
    # 「另一個帳號已經持有這個數字」的提權路徑)。
    try:
        collisions = _uid_gid_collision_reasons(driver, desired_identity)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_PRECHECK_FAILED,
            [f"uid/gid occupancy observation failed: {redact_driver_error(error)}"],
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi, driver_engaged=True,
        )
    if collisions:
        return _verdict(
            COMPONENT_STATUS_PREEXISTING_UNOWNED, collisions,
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
            mutation_performed=False,
            compensate=lambda: compensation_outcome(compensated=True, reobserved=True),
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
            reason=f"host identity apply failed: {redact_driver_error(error)}",
            component_effect_class="HOST_IDENTITY_INSTALL", row_abi=row_abi,
            plan_digest=plan_digest, pre_state_digest=pre_state_digest,
            post_state_digest=absent_state, journal=journal, clock=tick,
            compensate=lambda: _compensate_host_identity(
                driver, created_account, created_dirs, desired_identity["name"]
            ),
            driver=driver, applier_node=applier_node,
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
            driver=driver, applier_node=applier_node,
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
        if not isinstance(value, int) or isinstance(value, bool):
            reasons.append(f"host identity {key} must be an integer from the signed plan")
            continue
        # §8:system-account 配置區間之外(含 0=root 與一切低號既有身分)一律拒。
        if not (HOST_IDENTITY_SYSTEM_ID_MIN <= value <= HOST_IDENTITY_SYSTEM_ID_MAX):
            reasons.append(
                f"host identity {key}={value} is outside the system-account range "
                f"[{HOST_IDENTITY_SYSTEM_ID_MIN}, {HOST_IDENTITY_SYSTEM_ID_MAX}]; a signed "
                "manifest can never place the scanner identity on root or on an existing "
                "low-numbered service identity (a shared UID makes the scanner that account "
                "to the kernel and bypasses the PG_ROLE_ACL_MIGRATION boundary)"
            )
    reasons.extend(s2_3_expected_identity_reasons())
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


def s2_3_expected_identity_reasons(repo_root: Path = REPO_ROOT) -> list[str]:
    """§8 / S2.3:把 §8 的凍結身分契約 cross-check 回 S2.3 的 expected-identity artifact。

    artifact 從 repo 的固定路徑讀取(caller 既不遞交路徑也不遞交內容),且必須:
    ``status == PASS``、``self_digest`` 就地重算相符、``engine_scanner`` 分量的
    ``uid_label`` / ``pg_role`` / ``non_root`` 逐欄等於本模組凍結的值。

    誠實界線:S2.3 artifact **沒有**數值 UID/GID 欄位(``production_provisioned.uid`` 明載
    false),故本函式無法、也不宣稱把數值 pin 到 S2.3;數值面的把關由
    :data:`HOST_IDENTITY_SYSTEM_ID_MIN` / :data:`HOST_IDENTITY_SYSTEM_ID_MAX` 區間
    與 :func:`_uid_gid_collision_reasons` 的變更前碰撞觀測承擔。
    """

    path = repo_root / S2_3_EXPECTED_IDENTITY_REL
    try:
        artifact = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return [
            "the S2.3 expected-identity receipt could not be read from the repository; the "
            "HOST_IDENTITY_INSTALL row cannot cross-check its identity contract (fail-closed)"
        ]
    if not isinstance(artifact, dict):
        return ["the S2.3 expected-identity receipt is not an object"]
    reasons: list[str] = []
    if artifact.get("status") != "PASS":
        reasons.append("the S2.3 expected-identity receipt does not carry status=PASS")
    if artifact.get("self_digest") != artifact_self_digest(artifact):
        reasons.append("the S2.3 expected-identity receipt self_digest does not re-derive")
    components = artifact.get("expected_component_identities")
    component = None
    if isinstance(components, list):
        for entry in components:
            if isinstance(entry, dict) and entry.get("component") == S2_3_ENGINE_SCANNER_COMPONENT:
                component = entry
                break
    if component is None:
        reasons.append(
            "the S2.3 expected-identity receipt carries no engine_scanner component identity"
        )
        return reasons
    if component.get("uid_label") != ENGINE_SCANNER_IDENTITY_NAME:
        reasons.append(
            f"the S2.3 engine_scanner uid_label is {component.get('uid_label')!r}, not the §8 "
            f"contract name {ENGINE_SCANNER_IDENTITY_NAME!r}"
        )
    if component.get("pg_role") != S2_3_ENGINE_SCANNER_PG_ROLE:
        reasons.append("the S2.3 engine_scanner pg_role does not equal the §8 runtime role")
    if component.get("non_root") is not True:
        reasons.append("the S2.3 engine_scanner identity is not declared non-root")
    return reasons


def _uid_gid_collision_reasons(driver: Any, desired_identity: dict[str, Any]) -> list[str]:
    """變更之前:被簽的數值 UID/GID 若已屬於**別的**帳號/群組即 typed 拒(零變更)。"""

    name = desired_identity["name"]
    group = desired_identity["group"]
    reasons: list[str] = []
    uid_owner = driver.observe_account_by_uid(uid=int(desired_identity["uid"]))
    if isinstance(uid_owner, dict) and str(uid_owner.get("name")) != str(name):
        reasons.append(
            f"uid {desired_identity['uid']} is already held by account "
            f"{uid_owner.get('name')!r}; S2.4 never shares a UID with an existing account "
            "(a shared UID makes the scanner that account to the kernel)"
        )
    gid_owner = driver.observe_group_by_gid(gid=int(desired_identity["gid"]))
    if isinstance(gid_owner, dict) and str(gid_owner.get("name")) != str(group):
        reasons.append(
            f"gid {desired_identity['gid']} is already held by group "
            f"{gid_owner.get('name')!r}; S2.4 never shares a GID with an existing group"
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
) -> dict[str, Any]:
    """§5.4 ownership-aware:只移除本次證明為 absent 且已標 task-owned 的新增物。

    補償跑完之後**再觀測一次**:每個被移除的目錄/帳號都必須真的觀測不到,才回
    ``reobserved=True``。「沒有拋例外」永遠不足以宣稱 exact 還原(E2 P1-4)。
    """

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
    reobserved: bool | None = True
    try:
        for path in created_dirs:
            if driver.observe_directory(path=path) is not None:
                reobserved = False
        if created_account and driver.observe_identity(name=name) is not None:
            reobserved = False
    except Exception:  # noqa: BLE001 - 無法再觀測 = 不宣稱 exact
        reobserved = None
    return compensation_outcome(compensated=ok, reobserved=reobserved)


def host_identity_abi_projection() -> dict[str, Any]:
    """W3 exported-ABI 的 HOST_IDENTITY 面(§8 契約 + 三重 UID/GID 把關的活再導出)。"""

    return {
        "host_identity_entrypoint": (
            "agent_governance_s2_4_host_identity.apply_s2_4_host_identity"
        ),
        "host_identity_driver_protocol": (
            "agent_governance_s2_4_host_identity.HostIdentityDriver"
        ),
        "host_identity_contract_digest": canonical_digest({
            "identity": ENGINE_SCANNER_IDENTITY_CONTRACT,
            "static_directories": host_identity_directory_tree(),
        }),
        "host_identity_system_id_range": [
            HOST_IDENTITY_SYSTEM_ID_MIN, HOST_IDENTITY_SYSTEM_ID_MAX
        ],
        "s2_3_expected_identity_path": S2_3_EXPECTED_IDENTITY_REL,
        "s2_3_expected_identity_cross_check_reasons": s2_3_expected_identity_reasons(),
        "s2_3_pins_numeric_uid_gid": False,
        "uid_gid_occupancy_observers": ["observe_account_by_uid", "observe_group_by_gid"],
        # uid=gid=26(建模主機上的 postgres)必須在任何 driver 接觸之前被區間閘擋下。
        "postgres_uid_rejected_by_range": bool(
            _host_identity_contract_reasons(
                host_identity_desired_state(uid=26, gid=26), host_identity_directory_tree()
            )
        ),
    }

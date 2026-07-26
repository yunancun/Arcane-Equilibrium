#!/usr/bin/env python3
"""S2.4(WP4·W4b)aggregate APPLY 交易葉——§6 的 ``apply_s2_4_install_plan``(§10.2 凍結 ABI)。

W3b 交付了五個 APPLY row 的 typed driver;W4a 交付了 permit↔plan 綁定、replay append、
install lock、三本 WAL journal 與獨立補償後 postcheck 的**可獨立測試的縫**。本葉是把它們合成
**一筆交易**的唯一頂層進入點(§10.1 明列的 owned path):

```text
validate s2_4_install_plan_v1 -> §10.5 #24 輸入(兩個 scoped probe receipt + PREPARE 結果 +
五份 plan 釘住的 row intent)-> AGGREGATE/PG permit 的**逐欄** payload 比對(W4a 記錄的
AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON)-> §9 APPLY TTL 預算 -> driver=None ⇒ typed
EXTERNAL_VERIFICATION_PENDING(零變更)-> 取得 install lock(§5.2)-> §5.2 啟動 reconcile ->
同一把 lock 下 consume-once 兩張 permit -> 依 §5.1 required order 把五 row 各跑成一個
write-ahead 步驟 -> 獨立 aggregate postcheck -> s2_4_install_effect_receipt_v1
```

誠實界線(逐條可測):

- **success identity 在源碼線不可達**。``evidence_class`` 只能由**可驗證的**平台背書取得;
  :func:`agent_governance_s2_4_component.derive_recorded_evidence_class` 拒絕記錄任何自報的
  attested 等級,故 in-memory / disposable driver 的終端一律 ``SOURCE_SIMULATION_PASS``
  且九 authority 全 false(§6 表 / §10.5 #13);``APPLIED_INACTIVE`` 只有 W6B 的真 Linux
  production driver(帶 trusted-host attestation)能取得。
- **零變更**:``driver=None`` 在任何主機接觸之前回 typed ``EXTERNAL_VERIFICATION_PENDING``。
- **fault 注入**只為 §10.5 #6/#7 crash matrix 存在;它 raise
  :class:`agent_governance_s2_4_journal.JournalCrash` 時行程「消失」——該例外**刻意**逸出
  (那正是 crash 的語義),其餘一切失敗一律 typed 非成功。
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
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
import agent_governance_s2_4_apply as _apply  # noqa: E402
import agent_governance_s2_4_component as _component  # noqa: E402
import agent_governance_s2_4_journal as _journal  # noqa: E402
import agent_governance_s2_4_lock as _lock  # noqa: E402
import agent_governance_s2_4_permit as _permit  # noqa: E402
# 依 §10.1.1 的 2000 行治理拆分下沉至 agent_governance_s2_4_reconcile,此處逐名 re-export
# (消費者的 ``install_driver.<name>`` 匯入面與常量值皆不變)。
from agent_governance_s2_4_reconcile import (  # noqa: E402,F401
    RECONCILE_ADMITS_NEW_WORK,
    RECONCILE_LANES,
    RECONCILE_STATUS_CLEAN,
    RECONCILE_STATUS_COMPENSATE,
    RECONCILE_STATUS_CORRUPT,
    RECONCILE_STATUS_LOCK_REQUIRED,
    RECONCILE_STATUS_NOT_APPLIED,
    RECONCILE_STATUS_PENDING,
    RECONCILE_STATUS_RECOVERY_REQUIRED,
    RECONCILE_STATUS_RESUME,
    RECONCILE_TYPED_STATUSES,
    InstallDriverContractError,
    JournalRoutedDriver,
    reconcile_abi_projection,
    reconcile_startup_journals,
    startup_journal_paths as _startup_journal_paths,
)

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest
redact_driver_error = _component.redact_driver_error

# ── §5.1 / §5.4 的 code-owned 次序面(worker 不得改,§10.4)──────────────────────
APPLY_ROW_ORDER = tuple(central_validator.S2_4_APPLY_ROW_CLASS_ORDER)
# §5.4:unit -> launch/application bundle -> base runtime -> credential -> auth/PG -> host。
# 五個 v2 class 的逆序恰為該鏈(launch/application/base runtime 是同一個 LEARNING_RUNTIME row
# 的一次原子發佈)。
REVERSE_COMPENSATION_ORDER = tuple(reversed(APPLY_ROW_ORDER))
# §5.1 六個 typed step ↔ 五個 v2 class:第 4/5 步(base runtime、application+launch bundle)由
# **同一個** LEARNING_RUNTIME row 原子發佈,故 step_index 4 不獨立存在;ENGINE_SCANNER 是字面上
# 的第六步(index 5)。此表釘住 journal / step-result 的 step_index。
APPLY_ROW_STEP_INDEX = {
    "HOST_IDENTITY_INSTALL": 0,
    "PG_ROLE_ACL_MIGRATION": 1,
    "CREDENTIAL_INSTALL": 2,
    "LEARNING_RUNTIME": 3,
    "ENGINE_SCANNER": 5,
}
PROBE_SCOPES = ("PREPARE_SANDBOX", "INSTALLED_UNIT")
AGGREGATE_APPLIER_NODE = "s2-4-install-applier"
INSTALL_EVIDENCE_TTL_SECONDS = 900
# §5.4 逆向補償鏈契約的 domain(把它的 digest 與任何別的 digest 空間分開)。
AGGREGATE_ROLLBACK_CONTRACT_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-aggregate-reverse-compensation-chain-v1"
)
PER_ROW_ROLLBACK_CONTRACT_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-per-row-reverse-compensation-op-v1"
)
# W4b OBSERVER_SPACE_PRE_STATE_DIGEST 的 plan 側 domain(見 derive_plan_pre_state_projection)。
PLAN_PRE_STATE_PROJECTION_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-plan-pre-state-projection-v1"
)

# ── typed 終端狀態:恰為 s2_4_install_effect_receipt_v1 的封閉 enum(§10.2)────────
AGGREGATE_STATUS_APPLIED_INACTIVE = "APPLIED_INACTIVE"
AGGREGATE_STATUS_SOURCE_SIMULATION = "SOURCE_SIMULATION_PASS"
AGGREGATE_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
AGGREGATE_STATUS_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
AGGREGATE_STATUS_BUNDLE_INVALID = "PREPARED_BUNDLE_INVALID"
AGGREGATE_STATUS_PRECHECK_FAILED = "PRECHECK_FAILED"
AGGREGATE_STATUS_PRESTATE_MISMATCH = "PRESTATE_MISMATCH"
AGGREGATE_STATUS_PREEXISTING_UNOWNED = "PREEXISTING_UNOWNED_STATE"
AGGREGATE_STATUS_LOCK_HELD = "INSTALL_LOCK_HELD"
AGGREGATE_STATUS_JOURNAL_CORRUPT = "JOURNAL_CORRUPT_RECOVERY_REQUIRED"
AGGREGATE_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
AGGREGATE_STATUS_ROLLED_BACK = "POSTCHECK_FAILED_ROLLED_BACK"
AGGREGATE_STATUS_TOPOLOGY_UNPROVEN = "PG_TOPOLOGY_UNPROVEN"
AGGREGATE_STATUS_CREDENTIAL_UNSATISFIED = "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED"
AGGREGATE_STATUS_POLICY_REQUIRED = "CANDIDATE_POLICY_CONFIGURATION_REQUIRED"
AGGREGATE_TYPED_STATUSES = (
    AGGREGATE_STATUS_APPLIED_INACTIVE,
    AGGREGATE_STATUS_AUTHORIZATION_REJECTED,
    AGGREGATE_STATUS_BUNDLE_INVALID,
    AGGREGATE_STATUS_CREDENTIAL_UNSATISFIED,
    AGGREGATE_STATUS_JOURNAL_CORRUPT,
    AGGREGATE_STATUS_LOCK_HELD,
    AGGREGATE_STATUS_PENDING,
    AGGREGATE_STATUS_POLICY_REQUIRED,
    AGGREGATE_STATUS_PREEXISTING_UNOWNED,
    AGGREGATE_STATUS_PRECHECK_FAILED,
    AGGREGATE_STATUS_PRESTATE_MISMATCH,
    AGGREGATE_STATUS_RECOVERY_REQUIRED,
    AGGREGATE_STATUS_ROLLED_BACK,
    AGGREGATE_STATUS_SOURCE_SIMULATION,
    AGGREGATE_STATUS_TOPOLOGY_UNPROVEN,
)
# row 的 typed 拒絕(**變更之前**)如何投影到 aggregate 的封閉 enum;表外一律 PRECHECK_FAILED。
_ROW_STATUS_TO_AGGREGATE = {
    _component.COMPONENT_STATUS_AUTHORIZATION_REJECTED: AGGREGATE_STATUS_AUTHORIZATION_REJECTED,
    _component.COMPONENT_STATUS_BUNDLE_INVALID: AGGREGATE_STATUS_BUNDLE_INVALID,
    _component.COMPONENT_STATUS_CREDENTIAL_UNSATISFIED: (
        AGGREGATE_STATUS_CREDENTIAL_UNSATISFIED
    ),
    _component.COMPONENT_STATUS_PENDING: AGGREGATE_STATUS_PENDING,
    _component.COMPONENT_STATUS_PREEXISTING_UNOWNED: AGGREGATE_STATUS_PREEXISTING_UNOWNED,
    _component.COMPONENT_STATUS_PRECHECK_FAILED: AGGREGATE_STATUS_PRECHECK_FAILED,
    _component.COMPONENT_STATUS_PRESTATE_MISMATCH: AGGREGATE_STATUS_PRESTATE_MISMATCH,
    _component.COMPONENT_STATUS_TOPOLOGY_UNPROVEN: AGGREGATE_STATUS_TOPOLOGY_UNPROVEN,
    _apply.CANDIDATE_POLICY_STATUS_REQUIRED: AGGREGATE_STATUS_POLICY_REQUIRED,
}
_ROW_ADMITTED_STATUSES = (
    _component.COMPONENT_STATUS_SATISFIED,
    _component.COMPONENT_STATUS_NOOP_VERIFIED,
)
# WAL 落盤本身失敗(row 的 effect 從未被嘗試)時,journal 的 typed 狀態如何投影到 aggregate。
_JOURNAL_STATUS_TO_AGGREGATE = {
    _journal.JOURNAL_STATUS_CORRUPT: AGGREGATE_STATUS_JOURNAL_CORRUPT,
    _journal.JOURNAL_STATUS_PENDING: AGGREGATE_STATUS_PENDING,
    _journal.JOURNAL_STATUS_PRECHECK_FAILED: AGGREGATE_STATUS_PRECHECK_FAILED,
    _journal.JOURNAL_STATUS_RECOVERY_REQUIRED: AGGREGATE_STATUS_RECOVERY_REQUIRED,
}
# 五 row 的進入點(§10.2 凍結 ABI;aggregate 不另生一套主機動作)。
ROW_ENTRYPOINTS: dict[str, Callable[..., dict[str, Any]]] = {
    "HOST_IDENTITY_INSTALL": _apply.apply_s2_4_host_identity,
    "PG_ROLE_ACL_MIGRATION": _apply.apply_s2_4_pg_role_acl,
    "CREDENTIAL_INSTALL": _apply.apply_s2_4_credential_install,
    "LEARNING_RUNTIME": _apply.apply_s2_4_learning_runtime,
    "ENGINE_SCANNER": _apply.apply_s2_4_engine_scanner_unit,
}
# aggregate driver 上絕不可存在的面:S2.4 的 aggregate 交易「沒有」probe 生命週期,也永不
# enable/start 已安裝的 unit(§8.3 / §10.5 #38)。
FORBIDDEN_AGGREGATE_METHODS = (
    "build_transient_unit",
    "enable",
    "enable_unit",
    "restart",
    "start",
    "start_transient_unit",
    "start_unit",
) + tuple(
    name for name in _component.FORBIDDEN_UNIT_LIFECYCLE_METHODS
    if name not in {"enable", "enable_unit", "restart", "start", "start_unit"}
)
_ALL_FALSE_PRODUCTION_FLAGS = dict(_component._ALL_FALSE_PRODUCTION_FLAGS)
_DIGEST_RE = _component._DIGEST_RE


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


# ── 注入的 aggregate driver 面(真主機動作全在此後;source lane 恆 driver=None) ──
class AggregateInstallDriver(Protocol):
    """§6 step 10/11 的注入面:把五 row driver、檔案面、lock 面與獨立 verifier 綁在一起。

    **沒有** probe/enable/start 入口(:data:`FORBIDDEN_AGGREGATE_METHODS` 執行期硬檢),
    也沒有任何 raw shell/SQL/unit/路徑入口——那些一律由 row driver 的固定操作面承擔。
    """

    evidence_class: str

    # lock_driver -> InstallLockDriver;file_driver -> DurableFileDriver(WAL/ledger 共用);
    # row_driver -> 該 v2 class 的 W3b typed row driver。
    def lock_driver(self) -> Any: ...

    def file_driver(self) -> Any: ...

    def row_driver(self, *, component_effect_class: str) -> Any: ...

    def compensate_component_row(
        self, *, component_effect_class: str, plan_id: str, per_row_rollback_digest: str,
        ownership_verified: bool,
    ) -> dict[str, Any]:
        """§5.4:對**已施作**的一 row 執行 ownership-aware 逆向補償;回
        ``{"compensated", "reobserved", "observer_role_preserved", 以及該 row 適用的
        "daemon_reload_reasserted" / "hba_reload_reasserted"}``,絕不讀取/序列化既有秘密。"""
        ...

    def observe_installed_unit_state(self) -> dict[str, Any] | None:
        """唯讀觀測已安裝 unit 的當下狀態(不存在回 ``None``);永不 enable/start。"""
        ...

    def aggregate_independent_postcheck(
        self, *, plan_id: str, plan_core_digest: str, applier_node: str
    ) -> dict[str, Any]:
        """相異 verifier 節點的 aggregate lineage postcheck(applier 不得自證)。"""
        ...

    def trusted_host_time(self) -> str: ...


def assert_no_aggregate_forbidden_surface(driver: Any) -> list[str]:
    """§8.3/§10.5 #38:aggregate driver 上出現 probe/enable/start 面即 typed 拒(絕不呼叫)。"""

    present = sorted(
        name for name in set(FORBIDDEN_AGGREGATE_METHODS)
        if callable(getattr(driver, name, None))
    )
    if not present:
        return []
    return [
        f"the aggregate install driver exposes forbidden operations {present}; the S2.4 APPLY "
        "transaction has no capability-probe lifecycle and never enables, starts, restarts or "
        "signals the installed unit (S2.5A owns `enable --now`)"
    ]


# ── §5.4 逆向補償鏈契約(code-owned;plan 不攜帶 rollback digest,故它必須由 code 導出) ──
#
# 先例:W3a 的 probe ``cleanup_rollback_digest`` 亦是
# ``canonical_digest(capability_probe_cleanup_contract(...))``——rollback 契約由 code + 身分
# 導出,caller 無從遞交。此處逐字沿用同一機制,故 aggregate/PG permit 簽的
# ``aggregate_rollback_digest`` / ``pg_rollback_digest`` 皆可被消費端**獨立再導出**。
def per_row_rollback_contract(
    *, plan_id: str, component_effect_class: str
) -> dict[str, Any]:
    """單一 row 的逆向補償 op 契約(綁 plan 身分 + 凍結矩陣的 recovery_contract)。"""

    row_abi = _component.component_row_abi(component_effect_class)
    return {
        "domain": PER_ROW_ROLLBACK_CONTRACT_DOMAIN,
        "plan_id": plan_id,
        "component_effect_class": component_effect_class,
        "recovery_contract": row_abi["recovery_contract"],
        "adapter_id": row_abi["adapter_id"],
        "ownership_aware": True,
        "restores_exact_prior_bytes_or_removes_task_owned_delta_only": True,
        "never_drops_observer_role": True,
        "never_reconstructs_a_pre_existing_secret": True,
    }


def per_row_rollback_digest(*, plan_id: str, component_effect_class: str) -> str:
    return canonical_digest(
        per_row_rollback_contract(
            plan_id=plan_id, component_effect_class=component_effect_class
        )
    )


def aggregate_rollback_contract(*, plan_id: str) -> dict[str, Any]:
    """§5.4 的整條逆向補償鏈契約(次序 = 五 row 的逆序 + 兩條 reload 再斷言)。"""

    return {
        "domain": AGGREGATE_ROLLBACK_CONTRACT_DOMAIN,
        "plan_id": plan_id,
        "reverse_order": list(REVERSE_COMPENSATION_ORDER),
        "reverse_ops": [
            {
                "component_effect_class": name,
                "per_row_rollback_digest": per_row_rollback_digest(
                    plan_id=plan_id, component_effect_class=name
                ),
            }
            for name in REVERSE_COMPENSATION_ORDER
        ],
        "daemon_reload_reasserted_after_unit_bytes_rollback": True,
        "hba_reload_reasserted_after_hba_rollback": True,
        "observer_role_preserved": True,
        "no_secret_reconstructed": True,
    }


def aggregate_rollback_digest(*, plan_id: str) -> str:
    return canonical_digest(aggregate_rollback_contract(plan_id=plan_id))


# ── W4b AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON —— 兩張 permit 的**逐欄**期望 payload ──
# §9.1 payload 中「由 permit 自身的窗釘死、而非由 plan 導出」的兩欄:PERMIT_PLAN_BINDING 第 (a)
# 層已強制 payload_binding[issued_at/expires_at] == 頂層值,另有 §9.1 TTL 上限閘;故它們不由
# plan 導出,而是取 permit 自己記錄的窗(:func:`derive_permit_payload_coverage` 斷言覆蓋完整)。
PERMIT_WINDOW_FIELDS = ("issued_at", "expires_at")


def aggregate_permit_payload_binding(
    plan: dict[str, Any],
    *,
    installed_unit_probe_receipt: dict[str, Any],
    issued_at: Any,
    expires_at: Any,
) -> dict[str, Any]:
    """apply-aggregate permit 的**完整**期望 payload_binding(逐欄由 plan/證據獨立再導出)。"""

    core = plan["core"]
    plan_id = plan["plan_id"]
    profile = central_validator.S2_4_AUTHORIZATION_PROFILES["apply_aggregate"]
    return {
        "domain": profile["signature_namespace"],
        "plan_core_digest": canonical_digest(core),
        "plan_id": plan_id,
        "idempotency_key": plan_id,
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "prepare_receipt_digest": core["prepare_receipt_digest"],
        "topology_pre_digest": core["topology_pre_digest"],
        # plan core 不攜帶 probe receipt digest:它由 aggregate 手上那份 terminal
        # INSTALLED_UNIT probe receipt 獨立再導出(§6 step 3 的同一份證據)。
        "installed_unit_probe_receipt_digest": installed_unit_probe_receipt["self_digest"],
        "hba_delta_digest": core["hba_delta_digest"],
        "pre_state_digest": core["pre_state_digest"],
        "aggregate_rollback_digest": aggregate_rollback_digest(plan_id=plan_id),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def pg_permit_payload_binding(
    plan: dict[str, Any],
    *,
    component_intents: dict[str, Any],
    installed_unit_probe_receipt: dict[str, Any],
    issued_at: Any,
    expires_at: Any,
) -> dict[str, Any]:
    """PG-migration permit 的**完整**期望 payload_binding(PG 兩欄由 PG row intent 導出)。

    ``pg_acl_digest`` / ``pg_pre_state_digest`` 來自 ``PG_ROLE_ACL_MIGRATION`` 的 component
    intent——那份 intent 的 digest 已被 plan core 的 ``apply_rows`` 釘住,故此導出仍錨在 plan。
    """

    core = plan["core"]
    plan_id = plan["plan_id"]
    profile = central_validator.S2_4_AUTHORIZATION_PROFILES["pg_migration"]
    pg_intent = component_intents["PG_ROLE_ACL_MIGRATION"]
    return {
        "domain": profile["signature_namespace"],
        "plan_core_digest": canonical_digest(core),
        "plan_id": plan_id,
        "idempotency_key": plan_id,
        "source_head": core["source_head"],
        "target_host": core["target_host"],
        "topology_pre_digest": core["topology_pre_digest"],
        "installed_unit_probe_receipt_digest": installed_unit_probe_receipt["self_digest"],
        "pg_acl_digest": pg_intent["required_intent_fields"]["acl_manifest_digest"],
        "hba_delta_digest": core["hba_delta_digest"],
        "pg_pre_state_digest": pg_intent["pre_state_digest"],
        "pg_rollback_digest": per_row_rollback_digest(
            plan_id=plan_id, component_effect_class="PG_ROLE_ACL_MIGRATION"
        ),
        "issued_at": issued_at,
        "expires_at": expires_at,
    }


def derive_permit_payload_coverage() -> dict[str, Any]:
    """證明兩張 permit 的**每一個** §9.1 payload 欄位都被比對到(或被明載為窗欄位)。

    AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON 的可測不變量:期望 binding 的鍵集 ∪
    ``{authorization_id}`` 必須恰等於 profile 的 ordered payload——未來新增而沒被覆蓋的欄位會
    讓此投影不再 ``complete``,W4 wave-exit 因而破。
    """

    coverage: dict[str, Any] = {}
    plan = _coverage_probe_plan()
    receipt = {"self_digest": "sha256:" + "5" * 64}
    intents = {
        "PG_ROLE_ACL_MIGRATION": {
            "pre_state_digest": plan["core"]["pre_state_digest"],
            "required_intent_fields": {"acl_manifest_digest": "sha256:" + "6" * 64},
        }
    }
    bindings = {
        "apply_aggregate": aggregate_permit_payload_binding(
            plan, installed_unit_probe_receipt=receipt,
            issued_at="2030-01-01T00:00:00+00:00", expires_at="2030-01-01T00:10:00+00:00",
        ),
        "pg_migration": pg_permit_payload_binding(
            plan, component_intents=intents, installed_unit_probe_receipt=receipt,
            issued_at="2030-01-01T00:00:00+00:00", expires_at="2030-01-01T00:10:00+00:00",
        ),
    }
    for profile_key, binding in bindings.items():
        expected = set(
            central_validator.authorization_payload_binding_fields(profile_key)
        )
        present = set(binding)
        coverage[profile_key] = {
            "compared_field_count": len(present),
            "payload_field_count": len(
                central_validator.S2_4_AUTHORIZATION_PROFILES[profile_key]["payload_fields"]
            ),
            "uncompared_fields": sorted(expected - present),
            "extra_fields": sorted(present - expected),
            "window_fields": list(PERMIT_WINDOW_FIELDS),
            "complete": present == expected,
        }
    return coverage


def _coverage_probe_plan() -> dict[str, Any]:
    """coverage 投影用的 code-owned plan 骨架(與任何真 plan 無關,只為導出鍵集)。"""

    return {
        "plan_id": "s2-4-" + "0" * 64,
        "core": {
            "schema_version": "s2_4_install_plan_core_v1",
            "apply_rows": [
                {"component_effect_class": name, "component_intent_digest": "sha256:" + "1" * 64}
                for name in APPLY_ROW_ORDER
            ],
            "prepare_receipt_digest": "sha256:" + "2" * 64,
            "topology_pre_digest": "sha256:" + "3" * 64,
            "hba_delta_digest": "sha256:" + "4" * 64,
            "pre_state_digest": "sha256:" + "7" * 64,
            "source_head": "0" * 40,
            "target_host": "trade-core",
            "created_at": "2030-01-01T00:00:00+00:00",
        },
    }


# ── W4b OBSERVER_SPACE_PRE_STATE_DIGEST(plan 側的一半:定義並執法) ──
def derive_plan_pre_state_projection(component_intents: dict[str, Any]) -> str:
    """§6 step 8 的 plan 側 pre-state digest 空間定義。

    W4a 記錄的縫是「plan 宣告的 ``pre_state_digest`` 與 verifier 的觀測 digest 不在同一
    digest 空間」。W4b 關掉**可關的那一半**:aggregate 的 ``core.pre_state_digest`` 自此
    **定義為**五 row 各自宣告 pre-state 的 domain-separated canonical 投影,故它不再是一個
    無定義的不透明值——任何一 row 的 pre-state 被換掉,plan 立刻不再自洽。

    仍未關的一半(見 W4 ABI 的 remaining obligations):把**獨立 verifier** 的
    ``observed_subject_digest`` 綁進同一空間需要真主機 observer(W6B),源碼線只能釘期望值。
    """

    return canonical_digest({
        "domain": PLAN_PRE_STATE_PROJECTION_DOMAIN,
        "rows": [
            {
                "component_effect_class": name,
                "pre_state_digest": component_intents[name]["pre_state_digest"],
            }
            for name in APPLY_ROW_ORDER
        ],
    })


# ── §5.1「There is no digest/signature cycle」—— plan ↔ component intent 的無環綁定 ──
#
# schema 同時要求 plan core 的 ``apply_rows[].component_intent_digest`` 與 component intent 的
# ``install_plan_digest``。若前者取 intent 的 ``self_digest``,兩者就互含彼此的 digest = 環,
# 構造上無解。W4b 依 §5.1 的明文把環剪開:
#
#   component_intent_digest = domain-separated canonical digest(intent 去掉**兩個**自指欄位:
#                             install_plan_digest 與 self_digest)
#   install_plan_digest     = plan 的 core_digest(另由 aggregate 逐一比對)
#
# 覆蓋不因此變窄:intent 的其餘每一欄(class / pre_state / class-specific digest / expiry)都被
# plan 釘死,而它指向哪一份 plan 由 aggregate 直接比對 core_digest——替換任一側皆被拒。
COMPONENT_INTENT_PLAN_BINDING_DOMAIN = (
    "arcane-equilibrium-aiml-s2-4-component-intent-plan-binding-v1"
)
_INTENT_SELF_REFERENTIAL_FIELDS = ("install_plan_digest", "self_digest")


def component_intent_plan_binding_digest(intent: Any) -> str:
    """plan core 用來釘住一份 component intent 的 digest(排除兩個自指欄位;§5.1 無環)。"""

    if not isinstance(intent, dict):
        raise InstallDriverContractError("component_effect_intent_not_an_object")
    return canonical_digest({
        "domain": COMPONENT_INTENT_PLAN_BINDING_DOMAIN,
        "intent": {
            key: value
            for key, value in intent.items()
            if key not in _INTENT_SELF_REFERENTIAL_FIELDS
        },
    })


# ── plan builder(§5.1:plan 於 PREPARE/probe 之後才被簽;此處只組 exact 形狀) ──
def build_s2_4_install_plan(
    *,
    component_intents: dict[str, Any],
    prepare_receipt_digest: str,
    topology_pre_digest: str,
    hba_delta_digest: str,
    source_head: str,
    target_host: str,
    created_at: str,
    expires_at: str,
    max_ttl_seconds: int = _permit.MAX_PERMIT_TTL_SECONDS,
) -> dict[str, Any]:
    """組出 ``s2_4_install_plan_v1`` 並把五份 component intent **重綁**到它的 core digest。

    回 ``{"plan": …, "component_intents": …}``:傳入的 intent 只需帶 class / pre_state /
    class-specific 欄位 / expiry(其 ``install_plan_digest`` 是 placeholder,因為 plan 還不存在);
    本函式先由「去自指欄位」的 binding digest 組出 core,再以 core digest 重建每一份 intent。
    重建**不改變** binding digest(那兩個欄位本就被排除),函式對此有 fail-closed 斷言。
    """

    missing = [name for name in APPLY_ROW_ORDER if name not in (component_intents or {})]
    if missing:
        raise InstallDriverContractError("install_plan_requires_all_five_component_intents")
    core = {
        "schema_version": "s2_4_install_plan_core_v1",
        "apply_rows": [
            {
                "component_effect_class": name,
                "component_intent_digest": component_intent_plan_binding_digest(
                    component_intents[name]
                ),
            }
            for name in APPLY_ROW_ORDER
        ],
        "prepare_receipt_digest": prepare_receipt_digest,
        "topology_pre_digest": topology_pre_digest,
        "hba_delta_digest": hba_delta_digest,
        "pre_state_digest": derive_plan_pre_state_projection(component_intents),
        "source_head": source_head,
        "target_host": target_host,
        "created_at": created_at,
    }
    core_digest = canonical_digest(core)
    plan_id = "s2-4-" + core_digest.split(":", 1)[1]
    plan = {
        "schema_version": "s2_4_install_plan_v1",
        "route_class": "s2_4_install_plan",
        "core": core,
        "core_digest": core_digest,
        "plan_id": plan_id,
        "idempotency_key": plan_id,
        "route_surface": {
            "aggregate_coordinator": True,
            "runtime_effect": True,
            "service": "system_unit_install_inactive",
            "pg": True,
            "migration": True,
            "secret": True,
            "risk": "critical",
            "runtime_claim": True,
            "apply_rows": list(APPLY_ROW_ORDER),
        },
        "forbidden_surfaces": {
            "prepare_fetch": False,
            "prepare_build": False,
            "arbitrary_shell": False,
            "arbitrary_sql": False,
            "arbitrary_path": False,
            "broker_or_order": False,
        },
        "required_authorization": {
            "aggregate": {
                "profile_identity": _component.APPLY_AGGREGATE_PROFILE,
                "signature_namespace": _component.APPLY_AGGREGATE_NAMESPACE,
                "max_ttl_seconds": int(max_ttl_seconds),
            },
            "pg_migration": {
                "profile_identity": _component.PG_MIGRATION_PROFILE,
                "signature_namespace": _component.PG_MIGRATION_NAMESPACE,
                "max_ttl_seconds": int(max_ttl_seconds),
            },
        },
        "expires_at": expires_at,
    }
    plan["self_digest"] = artifact_self_digest(plan)
    rebound: dict[str, Any] = {}
    for name in APPLY_ROW_ORDER:
        supplied = component_intents[name]
        intent = _component.build_component_effect_intent(
            component_effect_class=name,
            install_plan_digest=core_digest,
            pre_state_digest=supplied["pre_state_digest"],
            required_intent_fields=supplied["required_intent_fields"],
            expires_at=supplied["expires_at"],
        )
        if component_intent_plan_binding_digest(intent) != core["apply_rows"][
            APPLY_ROW_ORDER.index(name)
        ]["component_intent_digest"]:
            raise InstallDriverContractError("component_intent_plan_binding_digest_drifted")
        rebound[name] = intent
    return {"plan": plan, "component_intents": rebound}


# ── §10.5 #24 —— aggregate 輸入與成功謂詞 ──
def derive_aggregate_input_status(
    plan: Any,
    *,
    component_intents: Any,
    probe_receipts: Any,
    prepare_effect_receipt: Any,
    now: Any = None,
) -> dict[str, Any]:
    """§10.5 #24 的輸入側:兩個 scoped probe receipt + PREPARE 結果 + 五 row intent。

    每一項都被獨立再驗(中央 schema 閘 + terminal 狀態 + host/head 一致 + digest 綁 plan);
    兩個 scope 的 receipt digest 必相異(同一份 probe 不得充當兩個 scope)。
    """

    verdict: dict[str, Any] = {
        "schema_version": "s2_4_aggregate_input_verdict_v1_informal",
        "status": "AGGREGATE_INPUTS_REJECTED",
        "reasons": [],
        "probe_receipt_digests": {},
        "prepare_result_digest": None,
        "prepare_postcheck_digest": None,
    }
    reasons: list[str] = []
    if not isinstance(plan, dict) or plan.get("schema_version") != "s2_4_install_plan_v1":
        verdict["reasons"] = ["the aggregate transaction requires an s2_4_install_plan_v1"]
        return verdict
    core = plan.get("core")
    if not isinstance(core, dict):
        verdict["reasons"] = ["install plan core must be an object"]
        return verdict
    # (1) 五 row intent:class 集合 exact、digest 逐一等於 plan core 的 apply_rows。
    if not isinstance(component_intents, dict) or sorted(component_intents) != sorted(
        APPLY_ROW_ORDER
    ):
        reasons.append(
            "the aggregate transaction requires exactly the five §5.1 APPLY component intents "
            f"{list(APPLY_ROW_ORDER)}"
        )
    else:
        rows = core.get("apply_rows") or []
        for index, name in enumerate(APPLY_ROW_ORDER):
            intent = component_intents[name]
            intent_errors = central_validator.validate_aiml_artifact(intent, now=None)
            if intent_errors:
                reasons.extend(f"{name} intent: {reason}" for reason in intent_errors)
                continue
            if intent.get("install_plan_digest") != plan.get("core_digest"):
                reasons.append(
                    f"{name} intent install_plan_digest is not this plan's core digest"
                )
            row = rows[index] if index < len(rows) and isinstance(rows[index], dict) else {}
            if row.get("component_intent_digest") != component_intent_plan_binding_digest(
                intent
            ):
                reasons.append(
                    f"{name} intent is not the one bound into the signed plan core at §5.1 "
                    f"position {index} (§5.1 no-cycle binding: the plan pins every intent field "
                    "except the two self-referential ones)"
                )
        if not reasons:
            projection = derive_plan_pre_state_projection(component_intents)
            if core.get("pre_state_digest") != projection:
                reasons.append(
                    "the plan's signed pre_state_digest does not re-derive the domain-separated "
                    "projection over the five rows' declared pre-states (§6 step 8)"
                )
    # (2) 兩個 scoped terminal capability-probe receipt。
    if not isinstance(probe_receipts, dict) or sorted(probe_receipts) != sorted(PROBE_SCOPES):
        reasons.append(
            "the aggregate transaction requires BOTH scoped terminal capability-probe receipts "
            f"{list(PROBE_SCOPES)} (§10.5 #24)"
        )
    else:
        for scope in PROBE_SCOPES:
            receipt = probe_receipts[scope]
            reasons.extend(
                f"{scope} probe receipt: {reason}"
                for reason in _probe_receipt_reasons(receipt, scope=scope, core=core)
            )
        digests = {
            scope: (probe_receipts[scope] or {}).get("self_digest")
            if isinstance(probe_receipts[scope], dict) else None
            for scope in PROBE_SCOPES
        }
        verdict["probe_receipt_digests"] = digests
        if digests[PROBE_SCOPES[0]] is not None and (
            digests[PROBE_SCOPES[0]] == digests[PROBE_SCOPES[1]]
        ):
            reasons.append(
                "the two scoped probe receipts share one digest; PREPARE_SANDBOX and "
                "INSTALLED_UNIT must be two distinct terminal probes"
            )
    # (3) PREPARE 結果。
    prepare_reasons = _prepare_receipt_reasons(prepare_effect_receipt, core=core)
    reasons.extend(f"PREPARE receipt: {reason}" for reason in prepare_reasons)
    if not prepare_reasons and isinstance(prepare_effect_receipt, dict):
        verdict["prepare_result_digest"] = prepare_effect_receipt["self_digest"]
        verdict["prepare_postcheck_digest"] = prepare_effect_receipt["postcheck_digest"]
    if reasons:
        verdict["reasons"] = reasons
        return verdict
    verdict["status"] = "AGGREGATE_INPUTS_ADMITTED"
    return verdict


def _probe_receipt_reasons(receipt: Any, *, scope: str, core: dict[str, Any]) -> list[str]:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != (
        "s2_4_capability_probe_effect_receipt_v1"
    ):
        return ["must be an s2_4_capability_probe_effect_receipt_v1"]
    reasons = list(central_validator.validate_aiml_artifact(receipt, now=None))
    if receipt.get("probe_scope") != scope:
        reasons.append(f"probe_scope is {receipt.get('probe_scope')!r}, not {scope}")
    if receipt.get("terminal_status") != "TERMINAL_CLEAN":
        reasons.append(
            f"terminal_status is {receipt.get('terminal_status')!r}; a non-terminal or failed "
            "probe can never gate an APPLY transaction"
        )
    lifecycle = receipt.get("transient_unit_lifecycle")
    if not isinstance(lifecycle, dict) or lifecycle.get("zero_residue_verified") is not True:
        reasons.append(
            "the terminal probe receipt does not carry zero_residue_verified; no surviving "
            "probe unit must be proven before the aggregate transaction starts"
        )
    if receipt.get("target_host") != core.get("target_host"):
        reasons.append("target_host does not equal the plan's target host")
    if receipt.get("source_head") != core.get("source_head"):
        reasons.append("source_head does not equal the plan's source head")
    return reasons


def _prepare_receipt_reasons(receipt: Any, *, core: dict[str, Any]) -> list[str]:
    if not isinstance(receipt, dict) or receipt.get("schema_version") != (
        "s2_4_prepare_effect_receipt_v1"
    ):
        return ["must be an s2_4_prepare_effect_receipt_v1"]
    reasons = list(central_validator.validate_aiml_artifact(receipt, now=None))
    if receipt.get("terminal_status") != "PREPARED":
        reasons.append(
            f"terminal_status is {receipt.get('terminal_status')!r}; APPLY rejects a "
            "non-terminal or changed PREPARE lineage (§10.5 #30)"
        )
    if receipt.get("self_digest") != core.get("prepare_receipt_digest"):
        reasons.append("self_digest is not the prepare_receipt_digest bound into the plan core")
    if receipt.get("target_host") != core.get("target_host"):
        reasons.append("target_host does not equal the plan's target host")
    if receipt.get("source_head") != core.get("source_head"):
        reasons.append("source_head does not equal the plan's source head")
    return reasons


def derive_aggregate_success_status(
    *,
    probe_receipt_digests: Any,
    prepare_result_digest: Any,
    row_results: Any,
) -> dict[str, Any]:
    """§10.5 #24 的成功側:兩個 scoped probe receipt + PREPARE 結果 + **五個相異** row 結果。

    ``row_results`` 是 ``{class: (result_digest, postcheck_digest)}``;缺一列、重複 digest、
    或任一 digest 形狀不符即 ``AGGREGATE_SUCCESS_NOT_SATISFIED``(絕不半通過)。
    """

    reasons: list[str] = []
    digests = probe_receipt_digests if isinstance(probe_receipt_digests, dict) else {}
    for scope in PROBE_SCOPES:
        if _DIGEST_RE.fullmatch(str(digests.get(scope))) is None:
            reasons.append(f"aggregate success requires the terminal {scope} probe receipt digest")
    if len({digests.get(scope) for scope in PROBE_SCOPES}) != len(PROBE_SCOPES):
        reasons.append("the two scoped probe receipt digests must be distinct")
    if _DIGEST_RE.fullmatch(str(prepare_result_digest)) is None:
        reasons.append("aggregate success requires the PREPARE result digest")
    results = row_results if isinstance(row_results, dict) else {}
    if sorted(results) != sorted(APPLY_ROW_ORDER):
        reasons.append(
            "aggregate success requires all five distinct APPLY component results "
            f"{list(APPLY_ROW_ORDER)} (got {sorted(results)})"
        )
    else:
        seen: set[str] = set()
        for name in APPLY_ROW_ORDER:
            pair = results[name]
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                reasons.append(f"{name} result must be a (result_digest, postcheck_digest) pair")
                continue
            for value in pair:
                if _DIGEST_RE.fullmatch(str(value)) is None:
                    reasons.append(f"{name} result carries an invalid digest")
            if pair[0] in seen:
                reasons.append(
                    f"{name} result_digest duplicates another row's result; five DISTINCT "
                    "component results are required"
                )
            seen.add(pair[0])
    return {
        "status": "AGGREGATE_SUCCESS_SATISFIED" if not reasons else (
            "AGGREGATE_SUCCESS_NOT_SATISFIED"
        ),
        "reasons": reasons,
    }


# ── aggregate verdict 建構(單一出境面;§10.5 #15 秘密掃描) ──
def _verdict(
    status: str,
    reasons: list[str],
    *,
    plan_id: str | None = None,
    mutation_performed: bool = False,
    driver_engaged: bool = False,
    receipt: dict[str, Any] | None = None,
    postcheck: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
    step_results: list[dict[str, Any]] | None = None,
    row_verdicts: dict[str, Any] | None = None,
    journal: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    reconcile: dict[str, Any] | None = None,
    residue: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = {
        "schema_version": "s2_4_install_transaction_verdict_v1_informal",
        "status": status,
        "reasons": list(reasons),
        "plan_id": plan_id,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "receipt": receipt,
        "postcheck": postcheck,
        "rollback": rollback,
        "step_results": list(step_results or []),
        "row_verdicts": dict(row_verdicts or {}),
        "journal": journal,
        "replay": replay,
        "reconcile": reconcile,
        "residue": residue,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }
    leak = _component.scan_serializable_surface(verdict)
    if leak:
        return {
            "schema_version": "s2_4_install_transaction_verdict_v1_informal",
            "status": _component.COMPONENT_STATUS_SECRET_LEAK_BLOCKED,
            "reasons": leak + [
                "the constructed aggregate verdict carried secret material; every artifact, "
                "reason and observation was dropped rather than returned (§7)"
            ],
            "plan_id": plan_id,
            "mutation_performed": bool(mutation_performed),
            "driver_engaged": bool(driver_engaged),
            "receipt": None, "postcheck": None, "rollback": None,
            "step_results": [], "row_verdicts": {}, "journal": None,
            "replay": None, "reconcile": None, "residue": None,
            "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
            "secret_material_scanned": True,
        }
    return verdict


def _row_observation_digest(
    *, component_effect_class: str, component_intent_digest: str, admitted: bool
) -> str:
    """一 row 完成投影的 digest(WAL 的期望/觀測 post-state 同一形)。

    ``admitted`` 只在該 row 的**獨立** postcheck 通過(SATISFIED)或零變更 NOOP_VERIFIED 時為
    真——故此觀測值不是 applier 的自報,而是 row 級獨立 verifier 裁決的投影。
    """

    return canonical_digest({
        "component_effect_class": component_effect_class,
        "component_intent_digest": component_intent_digest,
        "row_admitted": bool(admitted),
    })


def _build_step_result(
    *,
    plan_id: str,
    component_effect_class: str,
    state: str,
    pre_state_digest: str,
    post_state_digest: str,
    task_owned_delta_digest: str,
    apply_evidence_digest: str | None,
    postcheck_evidence_digest: str | None,
    compensation_intent_digest: str | None,
    compensation_result_digest: str | None,
    observed_at: str,
) -> dict[str, Any]:
    result = {
        "schema_version": "s2_4_install_step_result_v1",
        "plan_id": plan_id,
        "step_index": APPLY_ROW_STEP_INDEX[component_effect_class],
        "component_effect_class": component_effect_class,
        "state": state,
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        "task_owned_delta_digest": task_owned_delta_digest,
        "apply_evidence_digest": apply_evidence_digest,
        "postcheck_evidence_digest": postcheck_evidence_digest,
        "compensation_intent_digest": compensation_intent_digest,
        "compensation_result_digest": compensation_result_digest,
        "observed_at": observed_at,
    }
    result["self_digest"] = artifact_self_digest(result)
    return result


def _build_aggregate_postcheck(
    *,
    driver: Any,
    plan: dict[str, Any],
    applier_node: str,
    all_rows_admitted: bool,
    clock: Callable[[], datetime],
) -> tuple[dict[str, Any] | None, list[str]]:
    """相異 verifier 節點的 aggregate lineage postcheck(applier 不得自證)。"""

    try:
        observed = driver.aggregate_independent_postcheck(
            plan_id=plan["plan_id"], plan_core_digest=plan["core_digest"],
            applier_node=applier_node,
        )
    except Exception as error:  # noqa: BLE001
        return None, [
            f"independent aggregate postcheck failed: {redact_driver_error(error)}"
        ]
    if not isinstance(observed, dict):
        return None, ["independent aggregate postcheck did not return an object"]
    verifier_node = str(observed.get("verifier_node", ""))
    if not verifier_node or verifier_node == applier_node:
        return None, [
            "independent aggregate postcheck verifier_node must differ from the applier"
        ]
    capture = observed.get("verifier_capture_digest")
    if _DIGEST_RE.fullmatch(str(capture)) is None:
        return None, ["independent aggregate postcheck verifier_capture_digest is invalid"]
    flags = {
        field: bool(observed.get(field))
        for field in (
            "probe_lineage_verified", "prepare_lineage_verified", "plan_lineage_verified",
            "idempotency_verified", "pre_state_lineage_verified", "all_apply_rows_satisfied",
        )
    }
    at = clock()
    postcheck = {
        "schema_version": "s2_4_install_postcheck_v1",
        "status": "PASS" if all(flags.values()) else "FAIL",
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        **flags,
        "verifier_capture_digest": capture,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=INSTALL_EVIDENCE_TTL_SECONDS)),
    }
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    reasons: list[str] = []
    if postcheck["status"] != "PASS":
        reasons.append(
            "the independent aggregate postcheck FAILED on "
            f"{sorted(name for name, value in flags.items() if not value)}"
        )
    if flags["all_apply_rows_satisfied"] and not all_rows_admitted:
        reasons.append(
            "the independent verifier claims all five APPLY rows are satisfied while the "
            "applier observed at least one non-admitted row; the claim is refused"
        )
    reasons.extend(central_validator.validate_aiml_artifact(postcheck))
    return postcheck, reasons


def _build_install_effect_receipt(
    *,
    plan: dict[str, Any],
    status: str,
    authorizations: dict[str, Any],
    probe_receipt_digests: dict[str, Any],
    prepare_result_digest: str,
    prepare_postcheck_digest: str,
    row_results: dict[str, tuple[str, str]],
    journal_digest: str,
    unit_state: dict[str, Any],
    evidence_class: str,
    trusted_host_time: str,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    at = clock()
    receipt = {
        "schema_version": "s2_4_install_effect_receipt_v1",
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "idempotency_key": plan["idempotency_key"],
        "status": status,
        "aggregate_authorization_id": authorizations["apply_aggregate"]["authorization_id"],
        "aggregate_authorization_digest": authorizations["apply_aggregate"]["self_digest"],
        "pg_authorization_id": authorizations["pg_migration"]["authorization_id"],
        "pg_authorization_digest": authorizations["pg_migration"]["self_digest"],
        "prepare_sandbox_probe_receipt_digest": probe_receipt_digests["PREPARE_SANDBOX"],
        "installed_unit_probe_receipt_digest": probe_receipt_digests["INSTALLED_UNIT"],
        "prepare_result_digest": prepare_result_digest,
        "prepare_postcheck_digest": prepare_postcheck_digest,
        "apply_row_results": [
            {
                "component_effect_class": name,
                "result_digest": row_results[name][0],
                "postcheck_digest": row_results[name][1],
            }
            for name in APPLY_ROW_ORDER
        ],
        "reverse_compensation_chain_digest": aggregate_rollback_digest(
            plan_id=plan["plan_id"]
        ),
        "journal_digest": journal_digest,
        "unit_state": dict(unit_state),
        "service_flags": {
            "service_enabled": False, "service_active": False,
            "service_started_by_s2_4": False,
        },
        "evidence_class": evidence_class,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "source_head": plan["core"]["source_head"],
        "target_host": plan["core"]["target_host"],
        "trusted_host_time": trusted_host_time,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=INSTALL_EVIDENCE_TTL_SECONDS)),
    }
    receipt["self_digest"] = artifact_self_digest(receipt)
    return receipt


def _build_install_rollback(
    *,
    plan: dict[str, Any],
    reverse_ops: list[dict[str, Any]],
    exact: bool,
    post_state_digest: str,
    daemon_reload_reasserted: bool,
    hba_reload_reasserted: bool,
    clock: Callable[[], datetime],
) -> dict[str, Any]:
    at = clock()
    rollback = {
        "schema_version": "s2_4_install_rollback_v1",
        "status": (
            _component.COMPENSATION_STATUS_EXACT if exact
            else _component.COMPENSATION_STATUS_RECOVERY_REQUIRED
        ),
        "plan_id": plan["plan_id"],
        "plan_core_digest": plan["core_digest"],
        "pre_state_digest": plan["core"]["pre_state_digest"],
        "post_state_digest": post_state_digest,
        "reverse_ops": list(reverse_ops),
        "ownership_aware": True,
        "exact_pre_state_restored": bool(exact),
        "daemon_reload_reasserted": bool(daemon_reload_reasserted),
        "hba_reload_reasserted": bool(hba_reload_reasserted),
        "observer_role_preserved": True,
        "no_secret_reconstructed": True,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=INSTALL_EVIDENCE_TTL_SECONDS)),
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


# ── §10.2 凍結 ABI:aggregate APPLY 交易 ──
def apply_s2_4_install_plan(
    plan: Any,
    authorization_set: Any = None,
    driver: "AggregateInstallDriver | None" = None,
    *,
    component_intents: Any = None,
    row_payloads: Any = None,
    probe_receipts: Any = None,
    prepare_effect_receipt: Any = None,
    apply_budget: Any = None,
    remaining_ttls: Any = None,
    ownership_evidence: Any = None,
    now: Any = None,
    clock: Callable[[], datetime] | None = None,
    fault: Callable[[str], None] | None = None,
    applier_node: str = AGGREGATE_APPLIER_NODE,
    startup_journal_paths: Any = None,
    startup_observed_state_digests: Any = None,
    startup_task_owned_partials: Any = None,
) -> dict[str, Any]:
    """§6 / §10.2:執行(或 fail-closed 拒絕)**一筆** S2.4 aggregate APPLY 交易。

    見模組 docstring 的固定次序。成功身分是
    ``s2_4_install_effect_receipt_v1(status=APPLIED_INACTIVE)``,而它在源碼/丟棄式線
    **構造上不可達**(``evidence_class`` 自報 attested 一律被拒 → ``SOURCE_SIMULATION_PASS``)。
    """

    tick = clock or (lambda: datetime.now(timezone.utc))
    # ── (1) plan 結構/身分(中央閘負責 core_digest/plan_id/idempotency/五 row 次序)──
    if not isinstance(plan, dict):
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED, ["the install plan must be an object"]
        )
    if plan.get("schema_version") != "s2_4_install_plan_v1":
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED,
            ["the aggregate transaction accepts only an s2_4_install_plan_v1 artifact"],
        )
    plan_errors = central_validator.validate_aiml_artifact(plan, now=now)
    if plan_errors:
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED, plan_errors, plan_id=plan.get("plan_id")
        )
    plan_id = plan["plan_id"]
    # ── (2) §10.5 #24 輸入側 ────────────────────────────────────────────────────
    inputs = derive_aggregate_input_status(
        plan, component_intents=component_intents, probe_receipts=probe_receipts,
        prepare_effect_receipt=prepare_effect_receipt, now=now,
    )
    if inputs["status"] != "AGGREGATE_INPUTS_ADMITTED":
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED, inputs["reasons"], plan_id=plan_id
        )
    probe_digests = inputs["probe_receipt_digests"]
    # ── (3) 兩張 permit 的逐欄 payload 比對 + §9.1 TTL 上限 ──────────────────────
    permit_status = _permit_binding_reasons(
        plan, authorization_set,
        component_intents=component_intents,
        installed_unit_probe_receipt=probe_receipts["INSTALLED_UNIT"],
    )
    if permit_status["reasons"]:
        return _verdict(
            AGGREGATE_STATUS_AUTHORIZATION_REJECTED, permit_status["reasons"], plan_id=plan_id
        )
    authorizations = permit_status["authorizations"]
    expected_bindings = permit_status["expected_bindings"]
    # ── (4) §9 APPLY TTL 預算不等式 ─────────────────────────────────────────────
    budget = _permit.derive_ttl_budget_status(
        "APPLY", budget=apply_budget, remaining_ttls=remaining_ttls
    )
    if budget["status"] != _permit.TTL_STATUS_SATISFIED:
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED,
            budget["reasons"] + [
                "the complete apply/observation/rollback budget must fit inside every governing "
                "TTL before the first mutation (§6 step 9)"
            ],
            plan_id=plan_id,
        )
    # ── (5) source lane:reachable 但 authority-locked ──────────────────────────
    if driver is None:
        return _verdict(
            AGGREGATE_STATUS_PENDING,
            [
                "the S2.4 aggregate install transaction is reachable but authority-locked: no "
                "production driver is present (Mac/source/test lane); "
                "EXTERNAL_VERIFICATION_PENDING with zero mutation"
            ],
            plan_id=plan_id,
        )
    forbidden = assert_no_aggregate_forbidden_surface(driver)
    if forbidden:
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED, forbidden, plan_id=plan_id, driver_engaged=False
        )
    return _run_transaction_with_driver(
        plan=plan, plan_id=plan_id, driver=driver, authorizations=authorizations,
        expected_bindings=expected_bindings, component_intents=component_intents,
        row_payloads=row_payloads or {}, probe_digests=probe_digests,
        prepare_result_digest=inputs["prepare_result_digest"],
        prepare_postcheck_digest=inputs["prepare_postcheck_digest"],
        ownership_evidence=ownership_evidence, now=now, tick=tick, fault=fault,
        applier_node=applier_node,
        startup_journal_paths=startup_journal_paths,
        startup_observed_state_digests=startup_observed_state_digests,
        startup_task_owned_partials=startup_task_owned_partials,
    )


def _permit_binding_reasons(
    plan: dict[str, Any],
    authorization_set: Any,
    *,
    component_intents: dict[str, Any],
    installed_unit_probe_receipt: dict[str, Any],
) -> dict[str, Any]:
    """AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON:兩張 permit 逐欄綁到**這一份**已驗 plan。"""

    outcome: dict[str, Any] = {
        "reasons": [], "authorizations": {}, "expected_bindings": {}
    }
    if not isinstance(authorization_set, dict):
        outcome["reasons"] = [
            "authorization_set must be a mapping of profile key -> authorization"
        ]
        return outcome
    required = ("apply_aggregate", "pg_migration")
    extra = sorted(set(authorization_set) - set(required))
    if extra:
        outcome["reasons"].append(
            f"the aggregate transaction was handed unrelated authorization profiles {extra}; "
            "it consumes only the aggregate install and PG-migration permits"
        )
    for profile_key in required:
        permit = authorization_set.get(profile_key)
        if not isinstance(permit, dict):
            outcome["reasons"].append(
                f"the aggregate transaction requires the {profile_key} permit; none was supplied "
                "(§6 step 6: S2.0 observer evidence is never PG mutation authority)"
            )
            continue
        outcome["authorizations"][profile_key] = permit
    if outcome["reasons"]:
        return outcome
    aggregate_binding = aggregate_permit_payload_binding(
        plan, installed_unit_probe_receipt=installed_unit_probe_receipt,
        issued_at=outcome["authorizations"]["apply_aggregate"].get("issued_at"),
        expires_at=outcome["authorizations"]["apply_aggregate"].get("expires_at"),
    )
    pg_binding = pg_permit_payload_binding(
        plan, component_intents=component_intents,
        installed_unit_probe_receipt=installed_unit_probe_receipt,
        issued_at=outcome["authorizations"]["pg_migration"].get("issued_at"),
        expires_at=outcome["authorizations"]["pg_migration"].get("expires_at"),
    )
    outcome["expected_bindings"] = {
        "apply_aggregate": aggregate_binding, "pg_migration": pg_binding
    }
    coverage = derive_permit_payload_coverage()
    for profile_key in required:
        if not coverage[profile_key]["complete"]:
            outcome["reasons"].append(
                f"the {profile_key} payload comparison is incomplete (uncompared="
                f"{coverage[profile_key]['uncompared_fields']}); a permit field nobody compares "
                "is a field an operator did not effectively sign for this plan"
            )
        permit = outcome["authorizations"][profile_key]
        binding = central_validator.derive_permit_plan_binding_status(
            permit, expected_payload_binding=outcome["expected_bindings"][profile_key],
            profile_key=profile_key,
        )
        if binding["status"] != central_validator.PERMIT_PLAN_BINDING_STATUS_VERIFIED:
            outcome["reasons"].extend(
                f"{profile_key}: {reason}" for reason in binding["reasons"]
            )
        ceiling = _permit.derive_permit_ttl_ceiling_status(permit)
        if ceiling["status"] != _permit.TTL_STATUS_SATISFIED:
            outcome["reasons"].extend(f"{profile_key}: {reason}" for reason in ceiling["reasons"])
    return outcome


def _run_transaction_with_driver(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    authorizations: dict[str, Any],
    expected_bindings: dict[str, Any],
    component_intents: dict[str, Any],
    row_payloads: dict[str, Any],
    probe_digests: dict[str, Any],
    prepare_result_digest: str,
    prepare_postcheck_digest: str,
    ownership_evidence: Any,
    now: Any,
    tick: Callable[[], datetime],
    fault: Callable[[str], None] | None,
    applier_node: str,
    startup_journal_paths: Any,
    startup_observed_state_digests: Any,
    startup_task_owned_partials: Any,
) -> dict[str, Any]:
    """driver 在場的固定交易次序;第一次 row effect 之前一律零 install 變更。"""

    def _gate(label: str) -> None:
        if fault is not None:
            fault(label)

    _gate("pre_lock")
    # ── (6) install lock(§5.2:唯一 writer)────────────────────────────────────
    try:
        lock_driver = driver.lock_driver()
        file_driver = driver.file_driver()
    except Exception as error:  # noqa: BLE001
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED,
            [
                "the aggregate driver could not supply its lock/file surfaces: "
                f"{redact_driver_error(error)}"
            ],
            plan_id=plan_id, driver_engaged=True,
        )
    lock_verdict = _lock.acquire_s2_4_install_lock(lock_driver)
    if lock_verdict["status"] != _lock.LOCK_STATUS_ACQUIRED:
        mapped = {
            _lock.LOCK_STATUS_HELD: AGGREGATE_STATUS_LOCK_HELD,
            _lock.LOCK_STATUS_PRECHECK_FAILED: AGGREGATE_STATUS_PRECHECK_FAILED,
            _lock.LOCK_STATUS_PENDING: AGGREGATE_STATUS_PENDING,
        }.get(lock_verdict["status"], AGGREGATE_STATUS_RECOVERY_REQUIRED)
        return _verdict(
            mapped, lock_verdict["reasons"], plan_id=plan_id, driver_engaged=True
        )
    try:
        _gate("post_lock")
        # ── (7) §5.2 啟動 reconcile ────────────────────────────────────────────
        reconcile = reconcile_startup_journals(
            file_driver,
            journal_paths=_startup_journal_paths(plan_id, startup_journal_paths),
            observed_state_digests=startup_observed_state_digests,
            task_owned_partials=startup_task_owned_partials,
            ownership_evidence=ownership_evidence,
            lock_verdict=lock_verdict,
        )
        if not reconcile["admits_new_work"]:
            mapped = (
                AGGREGATE_STATUS_JOURNAL_CORRUPT
                if reconcile["status"] == RECONCILE_STATUS_CORRUPT
                else AGGREGATE_STATUS_RECOVERY_REQUIRED
            )
            return _verdict(
                mapped, reconcile["reasons"], plan_id=plan_id, driver_engaged=True,
                reconcile=reconcile,
            )
        # ── (7b) §5.1 前導 lineage:APPLY 之前 ledger 必已有 probe/PREPARE 的消費紀錄 ──
        lineage = _prior_lineage_reasons(file_driver)
        if lineage["reasons"]:
            return _verdict(
                lineage["status"], lineage["reasons"], plan_id=plan_id, driver_engaged=True,
                reconcile=reconcile,
            )
        _gate("pre_consume")
        # ── (8) 在同一把 lock 下 consume-once 兩張 permit ──────────────────────
        replay = _lock.consume_authorizations_under_lock(
            file_driver, authorizations=authorizations,
            expected_payload_bindings=expected_bindings, lock_verdict=lock_verdict, now=now,
        )
        if replay["status"] == _lock.REPLAY_STATUS_IDEMPOTENT_REPLAY:
            return _verdict(
                AGGREGATE_STATUS_RECOVERY_REQUIRED,
                replay["reasons"] + [
                    "this exact plan/idempotency key is already recorded as consumed; the "
                    "aggregate transaction re-executes nothing and emits no new receipt — the "
                    "durable APPLY journal and the first run's receipt remain the authority "
                    "(§10.5 #8)"
                ],
                plan_id=plan_id, driver_engaged=True, replay=replay, reconcile=reconcile,
            )
        if replay["status"] != _lock.REPLAY_STATUS_APPENDED:
            mapped = {
                _lock.REPLAY_STATUS_REJECTED: AGGREGATE_STATUS_AUTHORIZATION_REJECTED,
                _lock.REPLAY_STATUS_CORRUPT: AGGREGATE_STATUS_JOURNAL_CORRUPT,
                _lock.REPLAY_STATUS_LOCK_REQUIRED: AGGREGATE_STATUS_PRECHECK_FAILED,
                _lock.REPLAY_STATUS_PENDING: AGGREGATE_STATUS_PENDING,
            }.get(replay["status"], AGGREGATE_STATUS_RECOVERY_REQUIRED)
            return _verdict(
                mapped, replay["reasons"], plan_id=plan_id, driver_engaged=True,
                replay=replay, reconcile=reconcile,
            )
        _gate("post_consume")
        return _drive_rows(
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            lock_verdict=lock_verdict, authorizations=authorizations,
            component_intents=component_intents, row_payloads=row_payloads,
            probe_digests=probe_digests, prepare_result_digest=prepare_result_digest,
            prepare_postcheck_digest=prepare_postcheck_digest,
            # §9.1:aggregate 是唯一的消費點;row 級 replay 檢查用 lock 下讀到的
            # **append 之前**的 head(同一筆交易內不重複裁決消費)。
            row_replay_ledger=_pre_append_ledger(replay),
            ownership_evidence=ownership_evidence, now=now, tick=tick, fault=fault,
            applier_node=applier_node, replay=replay, reconcile=reconcile,
        )
    finally:
        _lock.release_s2_4_install_lock(lock_driver, lock_verdict)


def _prior_lineage_reasons(file_driver: Any) -> dict[str, Any]:
    """§5.1:APPLY 之前,replay ledger 必已含前導 probe / PREPARE 的消費紀錄。

    §5.1 的次序是「probe → PREPARE → probe → 簽 plan → APPLY」且每段都 durable 消費過自己的
    permit(§9.1),故 APPLY 時讀到**空** ledger 本身就是「前導 lineage 從未發生」的證據 →
    typed ``AUTHORIZATION_REJECTED`` 零變更;這也讓 row 拿到的 append-前 head 恆為非空。
    """

    store = _journal.JournalStore(file_driver, journal_path=_lock.REPLAY_LEDGER_PATH)
    read = _lock._read_durable_ledger(store, ledger_path=_lock.REPLAY_LEDGER_PATH)
    if read["status"] not in {"LEDGER_LOADED", "LEDGER_ABSENT"}:
        return {
            "status": (
                AGGREGATE_STATUS_JOURNAL_CORRUPT
                if read["status"] == _lock.REPLAY_STATUS_CORRUPT
                else AGGREGATE_STATUS_RECOVERY_REQUIRED
            ),
            "reasons": list(read["reasons"]),
        }
    entries = (read["ledger"] or {}).get("entries") or []
    if not entries:
        return {
            "status": AGGREGATE_STATUS_AUTHORIZATION_REJECTED,
            "reasons": [
                "the authorization replay ledger records no prior consumption; §5.1 requires the "
                "PREPARE_SANDBOX probe, the PREPARE phase and the INSTALLED_UNIT probe to have "
                "durably consumed their own permits before an APPLY transaction may start"
            ],
        }
    return {"status": AGGREGATE_STATUS_PRECHECK_FAILED, "reasons": []}


def _pre_append_ledger(replay: dict[str, Any]) -> dict[str, Any]:
    """append **之前**的 ledger head(row 級結構檢查用;消費裁決已由 aggregate 做完)。"""

    ledger = replay.get("ledger") or {}
    entries = [
        entry for entry in (ledger.get("entries") or [])
        if entry.get("authorization_id") not in set(replay.get("appended_authorization_ids") or [])
    ]
    head = {
        "schema_version": _lock.REPLAY_LEDGER_SCHEMA_VERSION,
        "ledger_path": ledger.get("ledger_path", _lock.REPLAY_LEDGER_PATH),
        "entries": entries,
        "append_only": True,
    }
    return _lock.seal_replay_ledger(head)


def _drive_rows(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    file_driver: Any,
    lock_verdict: dict[str, Any],
    authorizations: dict[str, Any],
    component_intents: dict[str, Any],
    row_payloads: dict[str, Any],
    probe_digests: dict[str, Any],
    prepare_result_digest: str,
    prepare_postcheck_digest: str,
    row_replay_ledger: Any,
    ownership_evidence: Any,
    now: Any,
    tick: Callable[[], datetime],
    fault: Callable[[str], None] | None,
    applier_node: str,
    replay: dict[str, Any],
    reconcile: dict[str, Any],
) -> dict[str, Any]:
    """§5.1 required order 的五個 write-ahead 步驟 + 獨立 aggregate postcheck + 終端 receipt。"""

    rollback_digest = aggregate_rollback_digest(plan_id=plan_id)
    store = _journal.JournalStore(
        file_driver, journal_path=_journal.install_journal_path(plan_id)
    )

    def _build_journal(entries: list[dict[str, Any]], terminal: bool) -> dict[str, Any]:
        return _journal.build_install_journal(
            plan_id=plan_id, plan_core_digest=plan["core_digest"], idempotency_key=plan_id,
            expected_pre_state_digest=plan["core"]["pre_state_digest"],
            aggregate_rollback_digest=rollback_digest, entries=entries, terminal=terminal,
        )

    transaction = _journal.WriteAheadTransaction(
        store, build_journal=_build_journal, clock=tick
    )
    row_verdicts: dict[str, Any] = {}
    step_results: list[dict[str, Any]] = []
    row_results: dict[str, tuple[str, str]] = {}
    applied_rows: list[str] = []
    observed_at = _iso(tick())
    for name in APPLY_ROW_ORDER:
        intent = component_intents[name]
        # WAL 的 row 身分用**plan 釘住的** binding digest(非 intent 自己的 self_digest):
        # 這樣 journal 的每一步都錨在已簽 plan 的那一列上。
        intent_digest = component_intent_plan_binding_digest(intent)
        expected = _row_observation_digest(
            component_effect_class=name, component_intent_digest=intent_digest, admitted=True
        )
        holder: dict[str, Any] = {}

        def _effect(row_name: str = name, box: dict[str, Any] = holder) -> None:
            box["verdict"] = _run_row(
                row_name, driver=driver, plan=plan, intent=component_intents[row_name],
                authorizations=authorizations, row_payloads=row_payloads,
                row_replay_ledger=row_replay_ledger, ownership_evidence=ownership_evidence,
                now=now, tick=tick,
                # RUNNER_WAL_LOCK_WIRING:row 的 journal_transition 經同一本 WAL 落盤。
                store=store, build_journal=_build_journal, transaction=transaction,
                lock_verdict=lock_verdict, step_index=APPLY_ROW_STEP_INDEX[row_name],
            )

        def _observe(row_name: str = name, box: dict[str, Any] = holder) -> str:
            verdict = box.get("verdict") or {}
            return _row_observation_digest(
                component_effect_class=row_name,
                component_intent_digest=component_intent_plan_binding_digest(
                    component_intents[row_name]
                ),
                admitted=verdict.get("status") in _ROW_ADMITTED_STATUSES,
            )

        step = transaction.step(
            operation_id=f"s2-4-apply-row-{APPLY_ROW_STEP_INDEX[name]}-{name}",
            pre_state_digest=intent["pre_state_digest"],
            expected_post_state_digest=expected,
            effect=_effect, observe=_observe,
            step_index=APPLY_ROW_STEP_INDEX[name],
            fault=(lambda window, row=name: fault(f"{row}:{window}")) if fault else None,
        )
        row_verdict = holder.get("verdict")
        if row_verdict is not None:
            row_verdicts[name] = row_verdict
            if row_verdict.get("mutation_performed"):
                applied_rows.append(name)
            result = row_verdict.get("result")
            postcheck = row_verdict.get("postcheck")
            if isinstance(result, dict) and isinstance(postcheck, dict):
                row_results[name] = (result["self_digest"], postcheck["self_digest"])
            step_results.append(_build_step_result(
                plan_id=plan_id, component_effect_class=name,
                state="VERIFIED" if step["status"] == _journal.JOURNAL_STATUS_COMMITTED else (
                    "FAILED"
                ),
                pre_state_digest=intent["pre_state_digest"],
                post_state_digest=step["observed_post_state_digest"] or expected,
                task_owned_delta_digest=canonical_digest({
                    "component_effect_class": name,
                    "mutation_performed": bool(row_verdict.get("mutation_performed")),
                }),
                apply_evidence_digest=(
                    result["self_digest"] if isinstance(result, dict) else None
                ),
                postcheck_evidence_digest=(
                    postcheck["self_digest"] if isinstance(postcheck, dict) else None
                ),
                compensation_intent_digest=per_row_rollback_digest(
                    plan_id=plan_id, component_effect_class=name
                ),
                compensation_result_digest=(
                    row_verdict["rollback"]["self_digest"]
                    if isinstance(row_verdict.get("rollback"), dict) else None
                ),
                observed_at=observed_at,
            ))
        if step["status"] != _journal.JOURNAL_STATUS_COMMITTED:
            # 零變更(row 在任何主機接觸之前被拒,或 WAL 的 APPLYING 根本沒能落盤)且沒有任何
            # 先前 row 施作過 → 直接投影 typed 狀態。這裡**不**進補償:沒有 delta 可還原,把它
            # 記成「已回滾」會謊報一次不存在的 apply。
            if not applied_rows and not (row_verdict or {}).get("mutation_performed"):
                return _verdict(
                    _ROW_STATUS_TO_AGGREGATE.get(
                        (row_verdict or {}).get("status"),
                        _JOURNAL_STATUS_TO_AGGREGATE.get(
                            step["status"], AGGREGATE_STATUS_RECOVERY_REQUIRED
                        ),
                    ),
                    [f"{name}: {reason}" for reason in (row_verdict or {}).get("reasons", [])]
                    + step["reasons"],
                    plan_id=plan_id, driver_engaged=True, row_verdicts=row_verdicts,
                    step_results=step_results, journal=_terminal_journal(
                        transaction, name, plan, tick, compensated=False
                    ), replay=replay, reconcile=reconcile,
                    residue=_observe_residue(driver, probe_digests),
                )
            return _compensate_transaction(
                plan=plan, plan_id=plan_id, driver=driver, transaction=transaction,
                applied_rows=applied_rows,
                row_verdicts=row_verdicts, step_results=step_results,
                failing_row=name, failure_reasons=(
                    [f"{name}: {reason}" for reason in (row_verdict or {}).get("reasons", [])]
                    + step["reasons"]
                ),
                probe_digests=probe_digests, tick=tick,
                # 該 row 自己**沒有**動過主機(例如 §5.3 的既有態拒絕)→ 終端狀態取那個原因。
                cause_status=(
                    _ROW_STATUS_TO_AGGREGATE.get((row_verdict or {}).get("status"))
                    if not (row_verdict or {}).get("mutation_performed") else None
                ),
                replay=replay, reconcile=reconcile,
            )
    if fault is not None:
        fault("pre_aggregate_postcheck")
    # ── 獨立 aggregate postcheck(相異 verifier)────────────────────────────────
    all_admitted = all(
        row_verdicts[name].get("status") in _ROW_ADMITTED_STATUSES for name in APPLY_ROW_ORDER
    )
    postcheck, postcheck_reasons = _build_aggregate_postcheck(
        driver=driver, plan=plan, applier_node=applier_node,
        all_rows_admitted=all_admitted, clock=tick,
    )
    if postcheck is None or postcheck_reasons:
        return _compensate_transaction(
            plan=plan, plan_id=plan_id, driver=driver, transaction=transaction,
            applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=postcheck_reasons, probe_digests=probe_digests, tick=tick,
            postcheck=postcheck, replay=replay, reconcile=reconcile,
        )
    # ── §10.5 #24 成功側 ────────────────────────────────────────────────────────
    success = derive_aggregate_success_status(
        probe_receipt_digests=probe_digests, prepare_result_digest=prepare_result_digest,
        row_results=row_results,
    )
    if success["status"] != "AGGREGATE_SUCCESS_SATISFIED":
        return _compensate_transaction(
            plan=plan, plan_id=plan_id, driver=driver, transaction=transaction,
            applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=success["reasons"], probe_digests=probe_digests, tick=tick,
            postcheck=postcheck, replay=replay, reconcile=reconcile,
        )
    # ── 已安裝 unit 必須 loaded/disabled/inactive(每一條終端路徑都觀測)──────────
    residue = _observe_residue(driver, probe_digests)
    if residue["installed_unit_inactive"] is not True:
        return _compensate_transaction(
            plan=plan, plan_id=plan_id, driver=driver, transaction=transaction,
            applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=residue["reasons"] + [
                "S2.4 installs the unit inactive; an enabled/active observation is never a "
                "successful S2.4 apply"
            ],
            probe_digests=probe_digests, tick=tick, postcheck=postcheck, replay=replay,
            reconcile=reconcile,
        )
    if fault is not None:
        fault("pre_terminal_journal")
    terminal = transaction.record(
        state="VERIFIED", pre_state_digest=plan["core"]["pre_state_digest"],
        post_state_digest=plan["core"]["pre_state_digest"],
        step_index=APPLY_ROW_STEP_INDEX[APPLY_ROW_ORDER[-1]], terminal=True,
    )
    if terminal["status"] != _journal.JOURNAL_STATUS_COMMITTED:
        return _compensate_transaction(
            plan=plan, plan_id=plan_id, driver=driver, transaction=transaction,
            applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=terminal["reasons"] + [
                "the terminal APPLY journal could not be fsynced; no receipt may claim a "
                "terminal transaction (§10.5 #14)"
            ],
            probe_digests=probe_digests, tick=tick, postcheck=postcheck, replay=replay,
            reconcile=reconcile,
        )
    # ── 終端 receipt(success identity 由 evidence class 決定,見模組 docstring)──
    evidence = _component.derive_recorded_evidence_class(driver)
    status = (
        AGGREGATE_STATUS_APPLIED_INACTIVE
        if evidence["recorded_evidence_class"] in _component.EVIDENCE_CLASS_ATTESTED
        else AGGREGATE_STATUS_SOURCE_SIMULATION
    )
    try:
        trusted_host_time = str(driver.trusted_host_time())
    except Exception as error:  # noqa: BLE001
        return _verdict(
            AGGREGATE_STATUS_RECOVERY_REQUIRED,
            [f"trusted host time is unavailable: {redact_driver_error(error)}"],
            plan_id=plan_id, mutation_performed=True, driver_engaged=True,
            row_verdicts=row_verdicts, step_results=step_results, postcheck=postcheck,
            journal=terminal.get("journal"), replay=replay, reconcile=reconcile,
            residue=residue,
        )
    receipt = _build_install_effect_receipt(
        plan=plan, status=status, authorizations=authorizations,
        probe_receipt_digests=probe_digests, prepare_result_digest=prepare_result_digest,
        prepare_postcheck_digest=prepare_postcheck_digest, row_results=row_results,
        journal_digest=terminal["journal"]["self_digest"],
        unit_state=residue["unit_state"], evidence_class=evidence["recorded_evidence_class"],
        trusted_host_time=trusted_host_time, clock=tick,
    )
    central_errors = central_validator.validate_aiml_artifact(receipt)
    lineage = central_validator.derive_install_lineage_status(receipt, install_plan=plan)
    if central_errors or lineage["status"] != "SATISFIED":
        return _verdict(
            AGGREGATE_STATUS_RECOVERY_REQUIRED, central_errors + lineage["reasons"],
            plan_id=plan_id, mutation_performed=True, driver_engaged=True,
            row_verdicts=row_verdicts, step_results=step_results, postcheck=postcheck,
            journal=terminal["journal"], replay=replay, reconcile=reconcile, residue=residue,
        )
    return _verdict(
        status, list(evidence["reasons"]), plan_id=plan_id, mutation_performed=True,
        driver_engaged=True, receipt=receipt, postcheck=postcheck,
        step_results=step_results, row_verdicts=row_verdicts, journal=terminal["journal"],
        replay=replay, reconcile=reconcile, residue=residue,
    )


def _run_row(
    name: str,
    *,
    driver: Any,
    plan: dict[str, Any],
    intent: dict[str, Any],
    authorizations: dict[str, Any],
    row_payloads: dict[str, Any],
    row_replay_ledger: Any,
    ownership_evidence: Any,
    now: Any,
    tick: Callable[[], datetime],
    store: Any,
    build_journal: Callable[[list[dict[str, Any]], bool], dict[str, Any]],
    transaction: Any,
    lock_verdict: dict[str, Any],
    step_index: int,
) -> dict[str, Any]:
    """跑一個 W3b row(RUNNER_WAL_LOCK_WIRING:row driver 被 :class:`JournalRoutedDriver` 包住,
    故該 row 每一次 ``journal_transition`` 都經**同一本** APPLY WAL durable 落盤且必須持有同一
    把 install lock;其餘屬性原樣委派,完全沒有改變該 driver 對主機做什麼)。"""

    row_driver = JournalRoutedDriver(
        driver.row_driver(component_effect_class=name),
        store=store, build_journal=build_journal, lock_verdict=lock_verdict,
        clock=tick, step_index=step_index, transaction=transaction,
    )
    scoped = {
        key: authorizations[key]
        for key in _component.COMPONENT_REQUIRED_PROFILES[name]
        if key in authorizations
    }
    payload = dict((row_payloads or {}).get(name) or {})
    return ROW_ENTRYPOINTS[name](
        intent, scoped, row_driver,
        now=now, clock=tick, replay_ledger=row_replay_ledger,
        ownership_evidence=(ownership_evidence or {}).get(name),
        **payload,
    )


def _observe_residue(driver: Any, probe_digests: dict[str, Any]) -> dict[str, Any]:
    """每一條終端路徑的殘留觀測:無倖存 probe unit + 已安裝 unit 為 inactive。"""

    residue: dict[str, Any] = {
        "probe_unit_surviving": False,
        "probe_receipt_digests": dict(probe_digests),
        "installed_unit_inactive": None,
        "unit_state": {"loaded": False, "disabled": True, "inactive": True},
        "reasons": [],
    }
    # 無倖存 probe unit:兩份 terminal probe receipt 已在輸入閘證明 zero residue,而 aggregate
    # 交易**沒有** probe 生命週期面(assert_no_aggregate_forbidden_surface 於 driver 接觸前硬檢)。
    try:
        observed = driver.observe_installed_unit_state()
    except Exception as error:  # noqa: BLE001
        residue["reasons"] = [
            f"the installed unit state could not be observed: {redact_driver_error(error)}"
        ]
        return residue
    if observed is None:
        # 不存在(補償已移除或從未安裝)= 絕不可能 active。
        residue["installed_unit_inactive"] = True
        residue["unit_state"] = {"loaded": False, "disabled": True, "inactive": True}
        return residue
    if not isinstance(observed, dict):
        residue["reasons"] = ["the installed unit observation is not an object"]
        return residue
    active = bool(observed.get("active") or observed.get("ActiveState") == "active")
    enabled = bool(observed.get("enabled") or observed.get("UnitFileState") == "enabled")
    inactive = bool(
        observed.get("inactive") or observed.get("ActiveState") == "inactive"
    )
    residue["unit_state"] = {
        "loaded": bool(observed.get("loaded") or observed.get("LoadState") == "loaded"),
        "disabled": bool(
            observed.get("disabled") or observed.get("UnitFileState") == "disabled"
        ),
        "inactive": inactive,
    }
    residue["installed_unit_inactive"] = bool(inactive and not active and not enabled)
    if not residue["installed_unit_inactive"]:
        residue["reasons"] = [
            "the installed engine-scanner unit is not loaded/disabled/inactive "
            f"(active={active}, enabled={enabled}, inactive={inactive})"
        ]
    return residue


def _terminal_journal(
    transaction: Any,
    failing_row: str | None,
    plan: dict[str, Any],
    tick: Callable[[], datetime],
    *,
    compensated: bool,
) -> dict[str, Any] | None:
    """把 journal 收到終端態(``COMPENSATED`` / ``FAILED``);落盤失敗回 ``None``。"""

    state = "COMPENSATED" if compensated else "FAILED"
    step_index = APPLY_ROW_STEP_INDEX.get(failing_row, 0) if failing_row else 0
    verdict = transaction.record(
        state=state, pre_state_digest=plan["core"]["pre_state_digest"],
        post_state_digest=plan["core"]["pre_state_digest"],
        step_index=step_index, terminal=True,
    )
    if verdict["status"] != _journal.JOURNAL_STATUS_COMMITTED:
        return None
    return verdict["journal"]


def _compensate_transaction(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    transaction: Any,
    applied_rows: list[str],
    row_verdicts: dict[str, Any],
    step_results: list[dict[str, Any]],
    failing_row: str | None,
    failure_reasons: list[str],
    probe_digests: dict[str, Any],
    tick: Callable[[], datetime],
    cause_status: str | None = None,
    postcheck: dict[str, Any] | None = None,
    replay: dict[str, Any] | None = None,
    reconcile: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """§5.4:ownership-aware 逆序補償;無法安全 exact 還原即 ``RECOVERY_REQUIRED``。

    ``cause_status`` 是「交易為何停下」的 typed 原因(例如某 row 在自己變更之前回
    ``PREEXISTING_UNOWNED_STATE``)。補償證明為 exact 時,終端狀態取**原因**而非泛用的
    ``POSTCHECK_FAILED_ROLLED_BACK``——operator 需要知道是哪一種 §5.3 情形擋下了交易,而
    「前面幾 row 已被逐一 exact 還原」這件事記在 rollback artifact 裡。
    """

    reasons = list(failure_reasons)
    transaction.record(
        state="COMPENSATING", pre_state_digest=plan["core"]["pre_state_digest"],
        post_state_digest=plan["core"]["pre_state_digest"],
        step_index=APPLY_ROW_STEP_INDEX.get(failing_row, 0) if failing_row else 0,
    )
    reverse_ops: list[dict[str, Any]] = []
    exact = True
    daemon_reload = False
    hba_reload = False
    for name in REVERSE_COMPENSATION_ORDER:
        digest = per_row_rollback_digest(plan_id=plan_id, component_effect_class=name)
        if name not in applied_rows:
            # 從未施作 → 沒有 delta 需要還原(§5.4 只移除證明為 absent 的新增物)。
            reverse_ops.append({
                "component_effect_class": name, "per_row_rollback_digest": digest,
                "ownership_verified": True,
            })
            continue
        row_rollback = (row_verdicts.get(name) or {}).get("rollback")
        ownership_verified = bool(
            isinstance(row_rollback, dict) and row_rollback.get("ownership_aware")
        ) or isinstance(row_verdicts.get(name), dict)
        try:
            outcome = driver.compensate_component_row(
                component_effect_class=name, plan_id=plan_id,
                per_row_rollback_digest=digest, ownership_verified=ownership_verified,
            )
        except Exception as error:  # noqa: BLE001
            reasons.append(
                f"{name} reverse compensation failed: {redact_driver_error(error)}"
            )
            exact = False
            reverse_ops.append({
                "component_effect_class": name, "per_row_rollback_digest": digest,
                "ownership_verified": False,
            })
            continue
        normalized, independent = _component.compensation_with_independent_postcheck(
            outcome, driver=driver.row_driver(component_effect_class=name),
            component_effect_class=name, install_plan_digest=plan["core_digest"],
            applier_node=f"s2-4-{name.lower()}-applier",
            pre_state_digest=plan["core"]["pre_state_digest"],
        )
        status, row_exact = _component.derive_compensation_status(normalized)
        reasons.extend(independent["reasons"])
        if not row_exact:
            exact = False
            reasons.append(
                f"{name} reverse compensation did not prove exact pre-state restoration "
                f"({status})"
            )
        if name == "ENGINE_SCANNER":
            daemon_reload = bool((outcome or {}).get("daemon_reload_reasserted"))
            if not daemon_reload:
                exact = False
                reasons.append(
                    "a unit-byte rollback must re-run the typed daemon-reload and verify the "
                    "restored FragmentPath/digest/load state (§5.4)"
                )
        if name == "PG_ROLE_ACL_MIGRATION":
            hba_reload = bool((outcome or {}).get("hba_reload_reasserted"))
            if not hba_reload:
                exact = False
                reasons.append(
                    "an HBA rollback must use the topology-attested reload operation id and "
                    "then verify active HBA rules, cluster identity and connectivity (§5.4)"
                )
            if (outcome or {}).get("observer_role_preserved") is not True:
                exact = False
                reasons.append(
                    "the PG reverse op did not confirm aiml_observer_ro is preserved; S2.4 "
                    "never drops the observer role (§5.4)"
                )
        reverse_ops.append({
            "component_effect_class": name, "per_row_rollback_digest": digest,
            "ownership_verified": bool(ownership_verified and row_exact),
        })
    residue = _observe_residue(driver, probe_digests)
    if residue["installed_unit_inactive"] is not True:
        exact = False
        reasons.extend(residue["reasons"])
    rollback = _build_install_rollback(
        plan=plan, reverse_ops=reverse_ops, exact=exact,
        post_state_digest=canonical_digest({
            "plan_id": plan_id, "applied_rows": list(applied_rows),
            "failing_row": failing_row,
        }),
        daemon_reload_reasserted=daemon_reload, hba_reload_reasserted=hba_reload, clock=tick,
    )
    rollback_errors = central_validator.validate_aiml_artifact(rollback)
    if rollback_errors:
        exact = False
        reasons.extend(rollback_errors)
    journal = _terminal_journal(
        transaction, failing_row, plan, tick, compensated=exact
    )
    if journal is None:
        exact = False
        reasons.append(
            "the terminal compensation journal could not be fsynced; RECOVERY_REQUIRED"
        )
    return _verdict(
        (cause_status or AGGREGATE_STATUS_ROLLED_BACK) if exact
        else AGGREGATE_STATUS_RECOVERY_REQUIRED,
        reasons + [
            "the applied task-owned delta was compensated in reverse §5.4 order and every "
            "reverse op was confirmed by an INDEPENDENT post-compensation re-observation"
            if exact else
            "safe exact compensation could not be proved; the service stays disabled/inactive, "
            "RECOVERY_REQUIRED records the exact residual and blocks S2.5 (§5.4)"
        ],
        plan_id=plan_id, mutation_performed=bool(applied_rows), driver_engaged=True,
        postcheck=postcheck, rollback=rollback, step_results=step_results,
        row_verdicts=row_verdicts, journal=journal, replay=replay, reconcile=reconcile,
        residue=residue,
    )


# ── W4 exported-ABI 折入面 ──
def install_driver_abi_projection() -> dict[str, Any]:
    """W4 exported-ABI 折入的 aggregate 交易面(活再導出見 wave_w4 葉)。"""

    plan_id = "s2-4-" + "0" * 64
    return {
        "aggregate_entrypoint": (
            "agent_governance_s2_4_install_driver.apply_s2_4_install_plan"
        ),
        "aggregate_driver_protocol": (
            "agent_governance_s2_4_install_driver.AggregateInstallDriver"
        ),
        "apply_row_order": list(APPLY_ROW_ORDER),
        "reverse_compensation_order": list(REVERSE_COMPENSATION_ORDER),
        "apply_row_step_index": dict(APPLY_ROW_STEP_INDEX),
        "aggregate_typed_statuses": list(AGGREGATE_TYPED_STATUSES),
        "row_status_projection": dict(_ROW_STATUS_TO_AGGREGATE),
        "journal_status_projection": dict(_JOURNAL_STATUS_TO_AGGREGATE),
        "forbidden_aggregate_methods": sorted(set(FORBIDDEN_AGGREGATE_METHODS)),
        "permit_payload_coverage": derive_permit_payload_coverage(),
        "aggregate_rollback_contract_domain": AGGREGATE_ROLLBACK_CONTRACT_DOMAIN,
        "per_row_rollback_contract_domain": PER_ROW_ROLLBACK_CONTRACT_DOMAIN,
        "plan_pre_state_projection_domain": PLAN_PRE_STATE_PROJECTION_DOMAIN,
        "aggregate_rollback_digest_probe": aggregate_rollback_digest(plan_id=plan_id),
        "component_intent_plan_binding_domain": COMPONENT_INTENT_PLAN_BINDING_DOMAIN,
        "intent_self_referential_fields": list(_INTENT_SELF_REFERENTIAL_FIELDS),
        **reconcile_abi_projection(),
        "schema_ids": [
            "s2_4_install_plan_core_v1",
            "s2_4_install_plan_v1",
            "s2_4_install_step_result_v1",
            "s2_4_install_postcheck_v1",
            "s2_4_install_rollback_v1",
            "s2_4_install_effect_receipt_v1",
        ],
        "install_receipt_success_identity": AGGREGATE_STATUS_APPLIED_INACTIVE,
        "source_lane_terminal_identity": AGGREGATE_STATUS_SOURCE_SIMULATION,
    }

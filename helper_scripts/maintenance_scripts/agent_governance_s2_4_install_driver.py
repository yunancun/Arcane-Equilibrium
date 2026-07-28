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
import agent_governance_s2_4_install_evidence as _evidence  # noqa: E402
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
# 依 §10.1.1 的 2000 行治理拆分,plan 組裝 / permit payload 綁定 / rollback 契約三組**純導出**
# 下沉至 agent_governance_s2_4_install_plan,此處逐名 re-export(消費者的
# ``install_driver.<name>`` 匯入面與常量值皆不變)。
from agent_governance_s2_4_install_plan import (  # noqa: E402,F401
    AGGREGATE_ROLLBACK_CONTRACT_DOMAIN,
    APPLY_ROW_ORDER,
    COMPONENT_INTENT_PLAN_BINDING_DOMAIN,
    PERMIT_WINDOW_FIELDS,
    PER_ROW_ROLLBACK_CONTRACT_DOMAIN,
    PLAN_PRE_STATE_PROJECTION_DOMAIN,
    PROBE_CORE_BINDING_UNVERIFIED,
    PROBE_CORE_BINDING_VERIFIED,
    PROBE_SCOPES,
    REVERSE_COMPENSATION_ORDER,
    _INTENT_SELF_REFERENTIAL_FIELDS,
    _prepare_receipt_reasons,
    _probe_receipt_reasons,
    aggregate_permit_payload_binding,
    aggregate_rollback_contract,
    aggregate_rollback_digest,
    build_s2_4_install_plan,
    component_intent_plan_binding_digest,
    derive_aggregate_input_status,
    derive_aggregate_success_status,
    derive_permit_payload_coverage,
    derive_plan_expected_topology,
    derive_plan_pre_state_projection,
    hba_delta_plan_binding_digest,
    per_row_rollback_contract,
    per_row_rollback_digest,
    pg_permit_payload_binding,
    PLAN_EXPECTED_TOPOLOGY_DERIVED,
)
# 證據 artifact builders(§10.1.1 拆分至證據葉;此處逐名 re-export 保匯入面不變)。
from agent_governance_s2_4_install_evidence import (  # noqa: E402,F401
    _build_aggregate_postcheck,
    _build_install_effect_receipt,
    _build_install_rollback,
    _build_step_result,
    _row_observation_digest,
)

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
AGGREGATE_APPLIER_NODE = "s2-4-install-applier"
INSTALL_EVIDENCE_TTL_SECONDS = 900
# §10.2:五 row 的 **exact** payload allowlist。``**payload`` 直接展進凍結的 row ABI,所以未
# 加白名單時 ``repo_root`` / ``applier_node`` / ``now`` / ``replay_ledger`` /
# ``ownership_evidence`` / ``clock`` 全都能從頂層進入點被覆寫——其中 ``applier_node`` 正是
# applier≠verifier 分離的載重欄位(component/apply 三處以它判斷「applier 不得自證」),
# 一旦可被 caller 指定,那條分離就只是名義上的。此表之外的鍵一律零變更 typed 拒。
ROW_PAYLOAD_ALLOWLIST: dict[str, tuple[str, ...]] = {
    "HOST_IDENTITY_INSTALL": ("uid_gid_directory_manifest",),
    # S2.4-AMEND-2(obligation 25):``expected_topology`` 自 allowlist 移除——它曾是唯一不被
    # 任何簽章綁定的 caller key;改由 ``hba_delta``(簽章 core 的 hba_delta_digest 所指之物)
    # 進場,expected 在 ``_run_row`` 由 plan 導出後 code-owned 注入。caller 再遞交
    # ``expected_topology`` 即走既有 allowlist typed 拒(PRECHECK_FAILED,零變更)。
    "PG_ROLE_ACL_MIGRATION": (
        "acl_manifest", "topology_attestation", "hba_delta", "secret_handle",
        "operation_id",
    ),
    "CREDENTIAL_INSTALL": (
        "dsn_handle", "operation_id", "mode", "previous_encrypted_blob_digest",
    ),
    "LEARNING_RUNTIME": ("prepared_bundle", "prepare_effect_receipt"),
    "ENGINE_SCANNER": ("unit_fields", "candidate_policy_budgets", "topology_guard"),
}
# 每一 row 的 applier 身分是 code-owned 的(與各 row ABI 的預設逐字相同,但此處**顯式**傳,
# 於是它永遠不是一個「caller 沒覆寫才成立」的預設值)。
ROW_APPLIER_NODES = {
    "HOST_IDENTITY_INSTALL": "s2-4-host-identity-applier",
    "PG_ROLE_ACL_MIGRATION": "s2-4-pg-admin-applier",
    "CREDENTIAL_INSTALL": "s2-4-host-secret-applier",
    "LEARNING_RUNTIME": "s2-4-host-runtime-applier",
    "ENGINE_SCANNER": "s2-4-host-service-applier",
}


def _row_payload_allowlist_reasons(row_payloads: Any) -> list[str]:
    """§10.2:row payload 只接受該 row 的 exact allowlist 鍵(code-owned 欄位永不可被遞交)。"""

    if row_payloads is None:
        return []
    if not isinstance(row_payloads, dict):
        return ["row_payloads must be a mapping of component_effect_class -> payload object"]
    reasons: list[str] = []
    unknown = sorted(set(row_payloads) - set(APPLY_ROW_ORDER))
    if unknown:
        reasons.append(
            f"row_payloads names classes outside the five §5.1 APPLY rows {unknown}"
        )
    for name in APPLY_ROW_ORDER:
        payload = row_payloads.get(name)
        if payload is None:
            continue
        if not isinstance(payload, dict):
            reasons.append(f"row_payloads[{name!r}] must be an object")
            continue
        extra = sorted(set(payload) - set(ROW_PAYLOAD_ALLOWLIST[name]))
        if extra:
            reasons.append(
                f"row_payloads[{name!r}] carries keys outside the frozen row ABI allowlist "
                f"{extra}; repo_root/applier_node/now/clock/replay_ledger/ownership_evidence "
                "are code-owned and can never be supplied through the aggregate entry point"
            )
    return reasons


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
# ── 只存在於**交易 verdict**、絕不出現在 receipt 的兩個終端(§10.5 #8 / #14)────────
#
# 這兩條路徑都**不簽發** receipt,故它們不在(也不可能在)凍結的
# ``s2_4_install_effect_receipt_v1`` status enum 內;把它們塞進 AGGREGATE_TYPED_STATUSES 會
# 破壞「typed 狀態必為 receipt enum 子集」這個 W4 wave-exit 不變量。verdict 自身是 informal 的
# code-owned 形狀,所以它的終端集合是 receipt enum 的**嚴格超集**——這正是誠實的形狀。
AGGREGATE_STATUS_ALREADY_APPLIED = "ALREADY_APPLIED_IDEMPOTENT"
AGGREGATE_STATUS_RECEIPT_PENDING = "RECEIPT_EMISSION_PENDING"
# durable APPLY journal 的 typed 判讀:只有「載入成功 + terminal + 同一 plan_id + VERIFIED」
# 才是「第一次執行真的完成」的證據;其餘一律未證(見 :func:`_load_terminal_journal`)。
APPLY_JOURNAL_TERMINAL_VERIFIED = "APPLY_JOURNAL_TERMINAL_VERIFIED"
APPLY_JOURNAL_UNPROVEN = "APPLY_JOURNAL_COMPLETION_UNPROVEN"
# §10.5 #36 的 probe-core 綁定在 verdict 上的 typed 可見性(E8:被略過必須留痕;兩個「已裁決」
# 的值由 install_plan 葉持有,此處 re-export 並補上「輸入側還沒跑到」的第三態)。
PROBE_CORE_BINDING_NOT_EVALUATED = "PROBE_CORE_BINDING_NOT_EVALUATED"
PROBE_CORE_BINDING_STATUSES = (
    PROBE_CORE_BINDING_NOT_EVALUATED,
    PROBE_CORE_BINDING_UNVERIFIED,
    PROBE_CORE_BINDING_VERIFIED,
)
AGGREGATE_TRANSACTION_ONLY_STATUSES = (
    AGGREGATE_STATUS_ALREADY_APPLIED,
    AGGREGATE_STATUS_RECEIPT_PENDING,
)
AGGREGATE_ALL_TYPED_STATUSES = (
    AGGREGATE_TYPED_STATUSES + AGGREGATE_TRANSACTION_ONLY_STATUSES
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
    lock_release: dict[str, Any] | None = None,
    attestation: dict[str, Any] | None = None,
    evidence_set: dict[str, Any] | None = None,
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
        "lock_release": lock_release,
        "attestation": attestation,
        "evidence_set": evidence_set,
        # E8:§10.5 #36 的 probe-core 綁定是**選配輸入**,所以「沒被檢查」與「檢查通過」在
        # verdict 上必須看得出差別;預設 NOT_EVALUATED,由頂層進入點在輸入側裁決後覆寫。
        "probe_core_binding": PROBE_CORE_BINDING_NOT_EVALUATED,
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
            "lock_release": None, "attestation": None, "evidence_set": None,
            "probe_core_binding": PROBE_CORE_BINDING_NOT_EVALUATED,
            "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
            "secret_material_scanned": True,
        }
    return verdict


def _with_probe_core_binding(verdict: dict[str, Any], status: str) -> dict[str, Any]:
    """把 §10.5 #36 的 probe-core 綁定裁決貼到出境 verdict 上(E8:略過必須留痕)。"""

    verdict = dict(verdict)
    verdict["probe_core_binding"] = status
    return verdict


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
    expected_installed_unit_probe_core_digest: Any = None,
    dependency_refreshes: Any = None,
) -> dict[str, Any]:
    """§6 / §10.2:執行(或 fail-closed 拒絕)**一筆** S2.4 aggregate APPLY 交易。

    見模組 docstring 的固定次序。成功身分是
    ``s2_4_install_effect_receipt_v1(status=APPLIED_INACTIVE)``——它由**已驗簽的**
    ``s2_4_install_apply_attestation_v1`` 解鎖(見 :mod:`agent_governance_s2_4_install_evidence`),
    而不是 driver 自報的 ``evidence_class``;沒有背書的一律 ``SOURCE_SIMULATION_PASS``。
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
    # ── (1b) plan 自身的新鮮度 ─────────────────────────────────────────────────
    #
    # 誠實界線(remaining obligation ``PLAN_EXPIRY_OUTSIDE_SIGNED_CORE``):``expires_at`` 不在
    # ``core`` 內,故它**不被** operator 的簽章覆蓋——把它改到 2040 年不會動到 ``core_digest``,
    # 兩張 permit 仍然驗得過。能在此關掉的是「已過期的 plan 仍被執行」;把它移進 core 需要
    # ``s2_4_install_plan_core_v1`` 的 schema 變更(§10.4 禁止 worker 自行選擇)。
    plan_expiry = _evidence.resolve_now(plan.get("expires_at"))
    observed_now = _evidence.resolve_now(now)
    if plan_expiry is None or observed_now is None:
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED,
            ["the install plan expiry window is unparseable; fail-closed with zero mutation"],
            plan_id=plan_id,
        )
    if plan_expiry <= observed_now:
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED,
            [
                f"the install plan expired at {plan['expires_at']}; §9.2/§10.5 #28 forbid "
                "refreshing expired install evidence by reference"
            ],
            plan_id=plan_id,
        )
    # ── (1c) 五 row payload 的 exact allowlist(§10.2 凍結 row ABI 的 splat 面)────
    payload_reasons = _row_payload_allowlist_reasons(row_payloads)
    if payload_reasons:
        return _verdict(
            AGGREGATE_STATUS_PRECHECK_FAILED, payload_reasons, plan_id=plan_id
        )
    # ── (2) §10.5 #24 輸入側 ────────────────────────────────────────────────────
    inputs = derive_aggregate_input_status(
        plan, component_intents=component_intents, probe_receipts=probe_receipts,
        prepare_effect_receipt=prepare_effect_receipt, now=now,
        expected_installed_unit_probe_core_digest=(
            expected_installed_unit_probe_core_digest
        ),
    )
    probe_core_binding = inputs["probe_core_binding"]
    if inputs["status"] != "AGGREGATE_INPUTS_ADMITTED":
        return _with_probe_core_binding(
            _verdict(AGGREGATE_STATUS_PRECHECK_FAILED, inputs["reasons"], plan_id=plan_id),
            probe_core_binding,
        )
    probe_digests = inputs["probe_receipt_digests"]
    # ── (2b) §9.2 source-dependency ingress(S2.4-AMEND-1)──────────────────────
    #
    # 純 precheck(零 driver、零 mutation),在任何 effect 語義之前;放在 ``driver is None``
    # 之前 → source lane 同樣走閘(閘在所有 lane 載重)。原身分由驗證端自 bound commit 的
    # blob 讀出,caller 只遞交 refresh;(1b) 已解析出 ``observed_now``,新鮮度有真時刻可用。
    admissions = _evidence.derive_apply_source_dependency_admissions(
        repo_root=REPO_ROOT, now=_iso(observed_now),
        dependency_refreshes=dependency_refreshes,
    )
    if admissions["status"] != _evidence.SOURCE_DEPENDENCIES_ADMITTED:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_PRECHECK_FAILED,
                list(admissions["reasons"]) + [
                    "§9.2: an expired source identity is admitted only together with one "
                    "current, independently reproduced refresh; forged/stale/absent "
                    "refreshes are refused with zero mutation"
                ],
                plan_id=plan_id,
            ),
            probe_core_binding,
        )
    dependency_refresh_digests = admissions["dependency_refresh_digests"]
    # ── (3) 兩張 permit 的簽章/信任根 + 逐欄 payload 比對 + §9.1 TTL 上限 ────────
    #
    # E19:此處**必須**傳已解析的觀測時刻,不是 caller 的原始 ``now``。
    # ``_s2_4_operator_authorization_errors`` 在 ``now is None`` 時整段跳過新鮮度檢查,而
    # ``now`` 的 ABI 預設就是 ``None``——於是「先驗簽再取 lock」這個 hoist 對一張**已過期**
    # 的合法簽章完全無效:它照樣 flock install lock、跑啟動 reconcile、讀 ledger 與 journal,
    # 正是這個 hoist 宣稱要擋掉的次序。``observed_now`` 在 (1b) 已經解析過(``now=None``
    # 時即當下 UTC),所以此處永遠有一個真的時刻可用。
    permit_status = _permit_binding_reasons(
        plan, authorization_set,
        component_intents=component_intents,
        installed_unit_probe_receipt=probe_receipts["INSTALLED_UNIT"],
        now=_iso(observed_now),
    )
    if permit_status["reasons"]:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_AUTHORIZATION_REJECTED, permit_status["reasons"],
                plan_id=plan_id,
            ),
            probe_core_binding,
        )
    authorizations = permit_status["authorizations"]
    expected_bindings = permit_status["expected_bindings"]
    # ── (4) §9 APPLY TTL 預算不等式(bound 由**每一份證據自己的** expires_at 導出)──
    ttls = _evidence.derive_apply_remaining_ttls(
        plan=plan, component_intents=component_intents, probe_receipts=probe_receipts,
        prepare_effect_receipt=prepare_effect_receipt, authorizations=authorizations,
        row_payloads=row_payloads, now=now, caller_remaining_ttls=remaining_ttls,
    )
    if ttls["status"] != _evidence.TTL_DERIVATION_STATUS_DERIVED:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_PRECHECK_FAILED,
                ttls["reasons"] + [
                    "every §9 remaining-TTL bound is derived from the evidence's own "
                    "expires_at; a caller-supplied value may only make the bound tighter "
                    "(§6 step 9)"
                ],
                plan_id=plan_id,
            ),
            probe_core_binding,
        )
    budget = _permit.derive_ttl_budget_status(
        "APPLY", budget=apply_budget, remaining_ttls=ttls["effective"]
    )
    if budget["status"] != _permit.TTL_STATUS_SATISFIED:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_PRECHECK_FAILED,
                budget["reasons"] + [
                    "the complete apply/observation/rollback budget must fit inside every "
                    "governing TTL before the first mutation (§6 step 9)"
                ],
                plan_id=plan_id,
            ),
            probe_core_binding,
        )
    # ── (4b) S2.4-AMEND-2 hoist(Codex-3):PG row 的 plan-derived expected_topology ──
    #
    # 原本在第二 row(PG_ROLE_ACL_MIGRATION)執行時才導出——那時 HOST_IDENTITY_INSTALL
    # 已 mutate,無效 plan 輸入得靠 §5.4 補償收拾。前置到 precheck(driver 未 engage,
    # driver=None 的 source lane 同樣走到):失敗即 typed PRECHECK_FAILED **零 mutation**;
    # 成功結果傳給 row-time 注入,不重複導出。置於 (4) 之後而非 (2) 緊鄰:缺 attestation
    # 的 payload 必須先落在 E10 的 underived-TTL-bound 拒絕上(那支既有回歸不得被本 hoist
    # 遮蔽),兩者都在任何 driver/lock/mutation 之前。
    pg_payload = (row_payloads or {}).get("PG_ROLE_ACL_MIGRATION") or {}
    derived_expected = derive_plan_expected_topology(
        plan=plan,
        hba_delta=pg_payload.get("hba_delta") if isinstance(pg_payload, dict) else None,
        topology_attestation=(
            pg_payload.get("topology_attestation") if isinstance(pg_payload, dict) else None
        ),
        now=_iso(observed_now),
    )
    if derived_expected["status"] != PLAN_EXPECTED_TOPOLOGY_DERIVED:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_PRECHECK_FAILED,
                list(derived_expected["reasons"]) + [
                    "the PG row's expected topology is derived from the signed plan "
                    "(core.hba_delta_digest + core.topology_pre_digest) before any host "
                    "contact; an invalid plan input is refused with zero mutation, never "
                    "repaired by compensation (§8.2 / §10.5 #25)"
                ],
                plan_id=plan_id,
            ),
            probe_core_binding,
        )
    pg_expected_topology = derived_expected["expected_topology"]
    # ── (5) source lane:reachable 但 authority-locked ──────────────────────────
    if driver is None:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_PENDING,
                [
                    "the S2.4 aggregate install transaction is reachable but authority-locked: "
                    "no production driver is present (Mac/source/test lane); "
                    "EXTERNAL_VERIFICATION_PENDING with zero mutation"
                ],
                plan_id=plan_id,
            ),
            probe_core_binding,
        )
    forbidden = assert_no_aggregate_forbidden_surface(driver)
    if forbidden:
        return _with_probe_core_binding(
            _verdict(
                AGGREGATE_STATUS_PRECHECK_FAILED, forbidden, plan_id=plan_id,
                driver_engaged=False,
            ),
            probe_core_binding,
        )
    return _with_probe_core_binding(
        _run_transaction_with_driver(
            plan=plan, plan_id=plan_id, driver=driver, authorizations=authorizations,
            expected_bindings=expected_bindings, component_intents=component_intents,
            row_payloads=row_payloads or {}, probe_digests=probe_digests,
            prepare_result_digest=inputs["prepare_result_digest"],
            prepare_postcheck_digest=inputs["prepare_postcheck_digest"],
            dependency_refresh_digests=dependency_refresh_digests,
            pg_expected_topology=pg_expected_topology,
            ownership_evidence=ownership_evidence, now=now, tick=tick, fault=fault,
            applier_node=applier_node,
            startup_journal_paths=startup_journal_paths,
            startup_observed_state_digests=startup_observed_state_digests,
            startup_task_owned_partials=startup_task_owned_partials,
        ),
        probe_core_binding,
    )


def _permit_binding_reasons(
    plan: dict[str, Any],
    authorization_set: Any,
    *,
    component_intents: dict[str, Any],
    installed_unit_probe_receipt: dict[str, Any],
    now: Any = None,
) -> dict[str, Any]:
    """AGGREGATE_PLAN_PAYLOAD_FULL_COMPARISON:兩張 permit 逐欄綁到**這一份**已驗 plan。

    §6 固定「step 6 驗兩張 fresh SSHSIG → step 7 取 install lock」。此處因而**先**跑
    :func:`aiml_gate_receipt_validator._s2_4_operator_authorization_errors`(profile 常量 /
    payload↔id 綁定 / TTL / 新鮮窗 / §9.1 信任根指紋 / 真 SSHSIG),再做結構性 plan 綁定。
    過去第一次簽章驗證發生在 ``consume_authorizations_under_lock`` 內部,也就是**取得 lock、
    跑完啟動 reconcile、讀完 ledger 之後**——一張未簽的 permit 因此能一路走到在主機上建立並
    flock ``/run/lock/arcane-equilibrium-aiml-s2-4-install.lock``,verdict 還記 ``driver_engaged
    =True``。lock 下的再驗證仍然保留:它是 consume 時的閘,不是唯一的閘。
    """

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
    # §6 step 6:任何 plan 綁定之前,先證明這兩張 permit 真的被 §9.1 信任根簽過。
    for profile_key in required:
        signature_errors = central_validator._s2_4_operator_authorization_errors(
            outcome["authorizations"][profile_key], now=now
        )
        if signature_errors:
            outcome["reasons"].extend(
                f"{profile_key}: {reason}" for reason in signature_errors
            )
    if outcome["reasons"]:
        outcome["reasons"].append(
            "an unsigned or untrusted permit is AUTHORIZATION_REJECTED before the install lock "
            "is created or flocked, before startup reconciliation and before the replay ledger "
            "is read (§6 step 6 precedes step 7); driver_engaged stays false"
        )
        return outcome
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
    dependency_refresh_digests: dict[str, Any],
    pg_expected_topology: dict[str, Any],
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
        outcome = _transaction_under_lock(
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            lock_verdict=lock_verdict, authorizations=authorizations,
            expected_bindings=expected_bindings, component_intents=component_intents,
            row_payloads=row_payloads, probe_digests=probe_digests,
            prepare_result_digest=prepare_result_digest,
            prepare_postcheck_digest=prepare_postcheck_digest,
            dependency_refresh_digests=dependency_refresh_digests,
            pg_expected_topology=pg_expected_topology,
            ownership_evidence=ownership_evidence, now=now, tick=tick, fault=fault,
            applier_node=applier_node, startup_journal_paths=startup_journal_paths,
            startup_observed_state_digests=startup_observed_state_digests,
            startup_task_owned_partials=startup_task_owned_partials, gate=_gate,
        )
    except BaseException:
        # 崩潰(JournalCrash)也必須把 FD 放掉;它的 typed verdict 不存在,故不再加工。
        _lock.release_s2_4_install_lock(lock_driver, lock_verdict)
        raise
    # §5.2:release 是一個**有 typed 結果**的動作。過去它的回值被 ``finally`` 丟掉,於是
    # ``INSTALL_LOCK_RECOVERY_REQUIRED``(例如 ``close()`` 拋例外 = FD 可能仍持有 flock)
    # 完全不可見——一筆帶著未釋放 lock 的交易照樣簽出 receipt。
    release = _lock.release_s2_4_install_lock(lock_driver, lock_verdict)
    return _fold_lock_release(outcome, release, plan_id=plan_id)


def _fold_lock_release(
    outcome: dict[str, Any], release: dict[str, Any], *, plan_id: str
) -> dict[str, Any]:
    """把 install-lock 的釋放結果折進交易 verdict(未乾淨釋放 → 永遠不是乾淨成功)。"""

    outcome = dict(outcome)
    outcome["lock_release"] = dict(release)
    if release.get("status") == _lock.LOCK_STATUS_RELEASED:
        return outcome
    return _verdict(
        AGGREGATE_STATUS_RECOVERY_REQUIRED,
        list(outcome.get("reasons") or []) + list(release.get("reasons") or []) + [
            "the exclusive install lock was not cleanly released "
            f"(release status {release.get('status')!r}); the next runner cannot safely assume "
            "it is the only writer, so this transaction is RECOVERY_REQUIRED and emits no "
            "receipt (§5.2)"
        ],
        plan_id=plan_id,
        mutation_performed=bool(outcome.get("mutation_performed")),
        driver_engaged=True,
        postcheck=outcome.get("postcheck"), rollback=outcome.get("rollback"),
        step_results=outcome.get("step_results"), row_verdicts=outcome.get("row_verdicts"),
        journal=outcome.get("journal"), replay=outcome.get("replay"),
        reconcile=outcome.get("reconcile"), residue=outcome.get("residue"),
        lock_release=dict(release),
    )


def _transaction_under_lock(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    file_driver: Any,
    lock_verdict: dict[str, Any],
    authorizations: dict[str, Any],
    expected_bindings: dict[str, Any],
    component_intents: dict[str, Any],
    row_payloads: dict[str, Any],
    probe_digests: dict[str, Any],
    prepare_result_digest: str,
    prepare_postcheck_digest: str,
    dependency_refresh_digests: dict[str, Any],
    pg_expected_topology: dict[str, Any],
    ownership_evidence: Any,
    now: Any,
    tick: Callable[[], datetime],
    fault: Callable[[str], None] | None,
    applier_node: str,
    startup_journal_paths: Any,
    startup_observed_state_digests: Any,
    startup_task_owned_partials: Any,
    gate: Callable[[str], None],
) -> dict[str, Any]:
    """握著 install lock 的那一段(step 7-11);呼叫端負責釋放並折入釋放結果。"""

    _gate = gate
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
        extra: list[str] = []
        if reconcile["status"] == RECONCILE_STATUS_COMPENSATE:
            # 誠實面:aggregate **不**執行啟動補償。它把 typed 收斂結果原樣交出,由持有
            # 三段生命週期的 W6 runner 依 §5.4 逆序補償後再重跑;所以「startup reconcile
            # 會逆序補償」這句話在本進入點上並不成立(見 startup_reconcile_contract)。
            extra = [
                "startup reconciliation found a task-owned partial with a valid journal "
                "ownership binding; the aggregate APPLY entry point does NOT itself run the "
                "§5.4 reverse compensation — it returns RECOVERY_REQUIRED with the typed "
                "lane verdict so the W6 runner (which owns probe/PREPARE/APPLY) compensates "
                "and re-runs. Zero new mutation was performed here"
            ]
        return _verdict(
            mapped, list(reconcile["reasons"]) + extra, plan_id=plan_id,
            driver_engaged=True, reconcile=reconcile,
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
        # §10.5 #8 稱這叫 idempotent replay,不是事故——**但只有在 durable 證據證明第一次
        # 執行真的收在終端 VERIFIED 時**。已消費的 permit 只證明「有人開始過」,絕不證明
        # 「有人完成過」:permit consume 之後、第一筆 APPLY journal 之前崩潰的行程留下的正是
        # 「ledger 有紀錄、journal 不存在」;跑到一半崩掉的留下的是「journal 非終端」。這兩種
        # 都是主機狀態未知 + 兩張 permit 已燒掉,若回 ALREADY_APPLIED 並宣稱「不需操作員介入」,
        # 那是把一台半途主機講成完工。
        durable = _load_terminal_journal(file_driver, plan_id)
        if durable["status"] != APPLY_JOURNAL_TERMINAL_VERIFIED:
            return _verdict(
                AGGREGATE_STATUS_RECOVERY_REQUIRED,
                replay["reasons"] + durable["reasons"] + [
                    "BOTH operator permits for this plan are already durably consumed, but no "
                    "terminal VERIFIED APPLY journal proves the first run completed; the host "
                    "state is UNPROVEN. The burnt permits cannot be replayed, so this plan can "
                    "never be applied again — an operator must independently establish the "
                    "host state, compensate any residue and mint a NEW signed plan with fresh "
                    "permits (§5.2/§9.1). RECOVERY_REQUIRED with zero new mutation"
                ],
                plan_id=plan_id, driver_engaged=True, replay=replay, reconcile=reconcile,
                journal=durable["journal"],
            )
        return _verdict(
            AGGREGATE_STATUS_ALREADY_APPLIED,
            replay["reasons"] + [
                "this exact plan/idempotency key is already recorded as consumed AND the "
                "durable APPLY journal for it is terminal in state VERIFIED; the aggregate "
                "transaction re-executes nothing and emits no new receipt — that terminal "
                "journal is the authority (§10.5 #8). This is an idempotent replay, NOT a "
                "recovery incident: the host state is proven complete by the journal. Honest "
                "boundary: a first-run s2_4_install_effect_receipt_v1 exists only if the first "
                "run got past receipt emission; a first run that terminated at "
                "RECEIPT_EMISSION_PENDING never emitted one, and this replay cannot "
                "reconstruct it (the journal does not carry the five row result/postcheck "
                "digests the receipt binds)"
            ],
            plan_id=plan_id, driver_engaged=True, replay=replay, reconcile=reconcile,
            journal=durable["journal"],
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
        dependency_refresh_digests=dependency_refresh_digests,
        pg_expected_topology=pg_expected_topology,
        # §9.1:aggregate 是唯一的消費點;row 級 replay 檢查用 lock 下讀到的
        # **append 之前**的 head(同一筆交易內不重複裁決消費)。
        row_replay_ledger=_pre_append_ledger(replay),
        ownership_evidence=ownership_evidence, now=now, tick=tick, fault=fault,
        applier_node=applier_node, replay=replay, reconcile=reconcile,
    )


def _load_terminal_journal(file_driver: Any, plan_id: str) -> dict[str, Any]:
    """在 lock 下讀回這一份 plan 的 durable APPLY journal,並判它是否**證明**交易已完成。

    回 ``{"status", "journal", "terminal_state", "reasons"}``。只有四件事同時成立才回
    :data:`APPLY_JOURNAL_TERMINAL_VERIFIED`:

      1. journal 讀得回來(``JOURNAL_LOADED``——``ABSENT``/``CORRUPT``/``PRECHECK_FAILED``
         都不是「完成」的證據,而是「不知道」);
      2. ``terminal is True``(journal 自己宣告本本已收尾);
      3. ``plan_id`` 就是**這一份** plan(讀到別份 plan 的 journal 不證明本份的任何事);
      4. 終端 state 是 ``VERIFIED``。

    對 ``COMPENSATED`` 的顯式裁決:**不**admit。終端 ``COMPENSATED`` 的意思是本次 task-owned
    delta 已被逆序移除——安裝**沒有**發生,主機回到前態,而兩張 permit 已經燒掉。把它讀成
    ``ALREADY_APPLIED_IDEMPOTENT``(「無需操作員介入」)會對 on-call 謊報一次不存在的安裝;
    正確的下一步是操作員簽一份新 plan。``FAILED`` 更明確:§5.4 的 ``FAILED`` 恰好記錄「補償
    無法被證明為 exact」的確切殘留。兩者都停在 RECOVERY_REQUIRED。
    """

    outcome: dict[str, Any] = {
        "status": APPLY_JOURNAL_UNPROVEN,
        "journal": None,
        "terminal_state": None,
        "reasons": [],
    }
    store = _journal.JournalStore(
        file_driver, journal_path=_journal.install_journal_path(plan_id)
    )
    read = store.load()
    if read["status"] != _journal.JOURNAL_STATUS_LOADED:
        outcome["reasons"] = [
            "the durable APPLY journal for this plan could not be read back "
            f"({read['status']}), so nothing proves the first run reached a terminal "
            "VERIFIED state"
        ] + list(read["reasons"])
        return outcome
    journal = read["journal"]
    outcome["journal"] = journal
    state = _journal.journal_terminal_state(journal)
    outcome["terminal_state"] = state
    reasons: list[str] = []
    if (journal or {}).get("terminal") is not True:
        reasons.append(
            "the durable APPLY journal for this plan is NOT terminal: the first run consumed "
            "both permits and then stopped mid-transaction, so an unknown number of the five "
            "§5.1 rows are applied on the host with no rollback artifact"
        )
    if (journal or {}).get("plan_id") != plan_id:
        reasons.append(
            "the durable APPLY journal read back at this plan's path does not name this "
            f"plan_id ({(journal or {}).get('plan_id')!r}); it proves nothing about this plan"
        )
    if state != "VERIFIED":
        reasons.append(
            f"the durable APPLY journal terminal state is {state!r}, not 'VERIFIED'; only "
            "VERIFIED means the transaction completed. 'COMPENSATED' means the task-owned "
            "delta was REMOVED (the install never landed) and 'FAILED' means compensation "
            "could not be proved exact (§5.4 records the exact residual) — neither is an "
            "already-applied install"
        )
    if reasons:
        outcome["reasons"] = reasons
        return outcome
    outcome["status"] = APPLY_JOURNAL_TERMINAL_VERIFIED
    return outcome


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
    dependency_refresh_digests: dict[str, Any],
    pg_expected_topology: dict[str, Any],
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
                pg_expected_topology=pg_expected_topology,
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
                task_owned_delta_digest=_task_owned_delta_digest(name, row_verdict),
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
                    evidence_set=None,
                )
            return _compensate_transaction(
                plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
                transaction=transaction, applied_rows=applied_rows,
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
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            transaction=transaction, applied_rows=applied_rows,
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
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            transaction=transaction, applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=success["reasons"], probe_digests=probe_digests, tick=tick,
            postcheck=postcheck, replay=replay, reconcile=reconcile,
        )
    # ── 已安裝 unit 必須被**觀測到** loaded/disabled/inactive ─────────────────────
    #
    # C1:「觀測不到」與「觀測到 active」是兩件事。過去 ``_observe_residue`` 吞掉每一個例外、
    # 留下 ``installed_unit_inactive=None``,而這裡用 ``is not True`` 判,於是一次 TimeoutError
    # 會把一筆**已完整驗證**的安裝整個拆掉(unit fragment + daemon-reload、三棵 runtime 樹、
    # credential slot、PG role/ACL/HBA + reload、uid/gid 與目錄),終端訊息卻仍宣稱「補償後經
    # 獨立確認」。把一份正確的安裝原封不動留著,嚴格優於因讀取失敗而拆掉 PG 與憑證狀態。
    residue = _observe_residue(driver, probe_digests)
    if residue["observation_status"] == _evidence.RESIDUE_OBSERVATION_UNAVAILABLE:
        return _verdict(
            AGGREGATE_STATUS_RECOVERY_REQUIRED,
            list(residue["reasons"]) + [
                "the installed unit state is UNOBSERVABLE, which is not evidence that it is "
                "active; nothing was compensated and the applied state is left intact for the "
                "operator to inspect (§5.4)"
            ],
            plan_id=plan_id, mutation_performed=bool(applied_rows), driver_engaged=True,
            row_verdicts=row_verdicts, step_results=step_results, postcheck=postcheck,
            journal=_terminal_journal(transaction, None, plan, tick, compensated=False),
            replay=replay, reconcile=reconcile, residue=residue,
        )
    # C16:成功路徑要求**正面**觀測(loaded 且 inactive 且未 enabled)。``absent ⇒ 絕不可能
    # active`` 只在補償路徑成立;放在成功路徑上,一筆「什麼都沒裝」的交易也會被記成終端成功。
    success_residue_reasons = _evidence.success_path_residue_reasons(residue)
    if success_residue_reasons:
        return _compensate_transaction(
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            transaction=transaction, applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=success_residue_reasons + [
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
        # E12:終端 entry 的 subject 是 plan 級前態,涵蓋整筆交易而非最後一列。
        component_effect_class=_journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
    )
    if terminal["status"] != _journal.JOURNAL_STATUS_COMMITTED:
        return _compensate_transaction(
            plan=plan, plan_id=plan_id, driver=driver, file_driver=file_driver,
            transaction=transaction, applied_rows=applied_rows,
            row_verdicts=row_verdicts, step_results=step_results, failing_row=None,
            failure_reasons=terminal["reasons"] + [
                "the terminal APPLY journal could not be fsynced; no receipt may claim a "
                "terminal transaction (§10.5 #14)"
            ],
            probe_digests=probe_digests, tick=tick, postcheck=postcheck, replay=replay,
            reconcile=reconcile,
        )
    # ── 終端 receipt ────────────────────────────────────────────────────────────
    #
    # C8(b):journal 已終端**之後**的每一個失敗都不是「主機狀態不明」——主機是正確且完整的,
    # 沒有任何東西需要補償,缺的只是那份 receipt(它是一本 durable 終端 journal 的**投影**,
    # 不是第二次 effect)。故它們回可重試的 ``RECEIPT_EMISSION_PENDING``,重試落在
    # ``ALREADY_APPLIED_IDEMPOTENT`` 並帶回同一份 journal digest,不重新消費任何 permit。
    def _receipt_pending(reasons: list[str]) -> dict[str, Any]:
        # C19/C20:即使 receipt 還沒投影出來,「哪幾列施作過 + 終端 journal + 啟動
        # reconcile 裁決 + 獨立殘留觀測」也必須是 durable 事實。
        evidence_set = _commit_evidence_set(
            file_driver=file_driver, plan=plan,
            terminal_status=AGGREGATE_STATUS_RECEIPT_PENDING,
            step_results=step_results, rollback=None, journal=terminal.get("journal"),
            reconcile=reconcile, residue=residue, receipt=None,
            applied_rows=applied_rows, observed_at=observed_at,
        )
        return _verdict(
            AGGREGATE_STATUS_RECEIPT_PENDING,
            list(reasons) + _evidence_set_reasons(evidence_set) + [  # noqa: E501
                "the APPLY transaction is DURABLY TERMINAL and the host is complete; only the "
                "receipt projection is missing. Re-running this exact signed plan re-executes "
                "nothing (ALREADY_APPLIED_IDEMPOTENT) and returns the terminal journal digest, "
                "so no new permits are consumed and nothing is compensated. Honest boundary "
                "(E9): the retry does NOT emit the missing receipt either — an "
                "s2_4_install_effect_receipt_v1 binds the five row result/postcheck digests, "
                "the probe/PREPARE lineage and the attestation-derived evidence_class, none of "
                "which the durable journal carries, so this install will never have a receipt. "
                "'Retryable' here means only that re-running is safe, not that the receipt is "
                "recoverable; the terminal journal plus the durable evidence set are the "
                "authority a downstream reader must bind to"
            ],
            plan_id=plan_id, mutation_performed=True, driver_engaged=True,
            row_verdicts=row_verdicts, step_results=step_results, postcheck=postcheck,
            journal=terminal.get("journal"), replay=replay, reconcile=reconcile,
            residue=residue,
            evidence_set=evidence_set,
        )

    try:
        trusted_host_time = str(driver.trusted_host_time())
    except Exception as error:  # noqa: BLE001
        return _receipt_pending(
            [f"trusted host time is unavailable: {redact_driver_error(error)}"]
        )
    # C18:permit 的新鮮度權威必須是**主機**的時間,不是 caller 的時鐘。兩者不得相差超過 §9.1
    # 的 skew,且必須落在兩張 permit 自己的窗內——否則「permit 還沒過期」這句話只是 caller 說的。
    clock_reasons = _trusted_host_time_reasons(
        trusted_host_time, now=now, tick=tick, authorizations=authorizations
    )
    if clock_reasons:
        return _receipt_pending(clock_reasons)
    # C12:``APPLIED_INACTIVE`` 由**已驗簽的** s2_4_install_apply_attestation_v1 解鎖,而不是
    # driver 自報的 evidence_class(後者在 in-process 無法與 fixture 區分,故 W3 起一律拒收)。
    produced = _evidence.collect_driver_apply_attestation(driver)
    attestation = _evidence.derive_apply_attestation_status(
        produced["attestation"], produced["signature"], plan=plan,
        applier_node=applier_node, verifier_node=postcheck["verifier_node"],
        row_results=row_results, installed_unit_state=residue["unit_state"],
        authorizations=authorizations,
    )
    attestation["reasons"] = list(produced["reasons"]) + list(attestation["reasons"])
    evidence = _component.derive_recorded_evidence_class(
        driver,
        attestation_verified=(
            attestation["status"] == _evidence.ATTESTATION_STATUS_VERIFIED
        ),
        attested_evidence_class=attestation["evidence_class"],
    )
    status = (
        AGGREGATE_STATUS_APPLIED_INACTIVE
        if evidence["recorded_evidence_class"] in _component.EVIDENCE_CLASS_ATTESTED
        else AGGREGATE_STATUS_SOURCE_SIMULATION
    )
    receipt = _build_install_effect_receipt(
        plan=plan, status=status, authorizations=authorizations,
        probe_receipt_digests=probe_digests, prepare_result_digest=prepare_result_digest,
        prepare_postcheck_digest=prepare_postcheck_digest,
        dependency_refresh_digests=dependency_refresh_digests, row_results=row_results,
        journal_digest=terminal["journal"]["self_digest"],
        unit_state=residue["unit_state"], evidence_class=evidence["recorded_evidence_class"],
        trusted_host_time=trusted_host_time, clock=tick,
    )
    central_errors = central_validator.validate_aiml_artifact(receipt)
    lineage = central_validator.derive_install_lineage_status(receipt, install_plan=plan)
    if central_errors or lineage["status"] != "SATISFIED":
        return _receipt_pending(central_errors + lineage["reasons"])
    evidence_set = _commit_evidence_set(
        file_driver=file_driver, plan=plan, terminal_status=status,
        step_results=step_results, rollback=None, journal=terminal["journal"],
        reconcile=reconcile, residue=residue, receipt=receipt, applied_rows=applied_rows,
        observed_at=observed_at,
    )
    return _verdict(
        status,
        list(evidence["reasons"]) + list(attestation["reasons"])
        + _evidence_set_reasons(evidence_set),
        plan_id=plan_id,
        mutation_performed=True, driver_engaged=True, receipt=receipt, postcheck=postcheck,
        step_results=step_results, row_verdicts=row_verdicts, journal=terminal["journal"],
        replay=replay, reconcile=reconcile, residue=residue, attestation=attestation,
        evidence_set=evidence_set,
    )


def _task_owned_delta_digest(name: str, row_verdict: dict[str, Any]) -> str:
    """§5.2/§5.4:step entry 必須記錄**這一列真正擁有的 subject**,而不是一個布林的雜湊。

    舊值是 ``canonical_digest({component_effect_class, mutation_performed})``——五列的可能取值
    只有十種,任何兩次同 class 同 bool 的 apply 都得到同一個 digest,所以 §5.4 的「只移除
    journal 記錄了擁有權的路徑」這個謂詞根本無法由 journal 支持。此處改記該列獨立 verifier
    實際觀測到的 subject 集合(``observed_subjects`` 的鍵)與其 per-subject digest。
    """

    subjects = row_verdict.get("observed_subjects")
    enumerated = (
        {key: canonical_digest(subjects[key]) for key in sorted(subjects)}
        if isinstance(subjects, dict) else None
    )
    return canonical_digest({
        "domain": "arcane-equilibrium-aiml-s2-4-task-owned-delta-v1",
        "component_effect_class": name,
        "mutation_performed": bool(row_verdict.get("mutation_performed")),
        "task_owned_subjects": sorted(enumerated) if enumerated else [],
        "task_owned_subject_digests": enumerated,
    })


def _trusted_host_time_reasons(
    trusted_host_time: str,
    *,
    now: Any,
    tick: Callable[[], datetime],
    authorizations: dict[str, Any],
) -> list[str]:
    """§9.1:主機報的時間必須與觀測時間互相印證,且落在兩張 permit 自己的窗內。"""

    host_moment = _evidence.resolve_now(trusted_host_time)
    if host_moment is None:
        return [
            "the driver's trusted_host_time is unparseable; permit freshness cannot be "
            "anchored to the host clock"
        ]
    observed = _evidence.resolve_now(now) if now is not None else tick()
    if observed is None:
        return ["the observed time is unparseable; fail-closed"]
    skew = abs((host_moment - observed).total_seconds())
    reasons: list[str] = []
    if skew > _permit.PERMIT_CLOCK_SKEW_SECONDS:
        reasons.append(
            f"the trusted host time differs from the observed time by {int(skew)}s, more than "
            f"the §9.1 clock skew ceiling of {_permit.PERMIT_CLOCK_SKEW_SECONDS}s; permit "
            "freshness would be decided by the caller's clock alone"
        )
    for profile_key in ("apply_aggregate", "pg_migration"):
        permit = (authorizations or {}).get(profile_key)
        issued = _evidence.resolve_now((permit or {}).get("issued_at"))
        expires = _evidence.resolve_now((permit or {}).get("expires_at"))
        if issued is None or expires is None:
            reasons.append(f"the {profile_key} permit window is unreadable")
            continue
        if not issued <= host_moment < expires:
            reasons.append(
                f"the trusted host time is outside the {profile_key} permit window; the host "
                "clock says this permit is not currently valid"
            )
    return reasons


def _commit_evidence_set(
    *,
    file_driver: Any,
    plan: dict[str, Any],
    terminal_status: str,
    step_results: list[dict[str, Any]],
    rollback: dict[str, Any] | None,
    journal: dict[str, Any] | None,
    reconcile: dict[str, Any] | None,
    residue: dict[str, Any] | None,
    receipt: dict[str, Any] | None,
    applied_rows: list[str],
    observed_at: str,
) -> dict[str, Any]:
    """把 durable 證據集落盤並回其 typed 結果(落盤失敗不改變交易的終端判斷,但被記進 verdict)。"""

    evidence = _evidence.build_install_evidence_set(
        plan=plan, terminal_status=terminal_status, step_results=step_results,
        rollback=rollback, journal=journal, reconcile=reconcile, residue=residue,
        receipt=receipt, applied_rows=applied_rows, observed_at=observed_at,
    )
    commit = _evidence.commit_install_evidence_set(file_driver, evidence)
    return {
        "status": commit["status"],
        "reasons": list(commit["reasons"]),
        "path": _evidence.install_evidence_set_path(plan["plan_id"]),
        "self_digest": evidence["self_digest"],
        "applied_rows": list(applied_rows),
    }


def _evidence_set_reasons(evidence_set: dict[str, Any] | None) -> list[str]:
    """E11:durable 證據集**沒落盤**必須出現在 verdict 的 reasons,不能只躺在一個角落欄位。

    ``EFFECT_RECEIPT_RECONCILE_BINDING`` 這條義務宣稱「receipt ↔ 終端 journal ↔ 啟動 reconcile
    裁決 ↔ 獨立殘留觀測」被一份 durable artifact 綁在一起。落盤失敗時那份 artifact 根本不存在,
    而終端狀態與 receipt 完全不變——於是「綁定不存在」這件事在證據上是**靜默**的:下游拿到一份
    看起來乾淨的成功 verdict,卻沒有任何檔案可以讓它驗證那個綁定。此處把它講出來。
    """

    if evidence_set is None:
        return []
    if evidence_set.get("status") == _evidence.EVIDENCE_SET_STATUS_COMMITTED:
        return []
    return list(evidence_set.get("reasons") or []) + [
        "the durable install evidence set could not be written to "
        f"{evidence_set.get('path')!r} (status {evidence_set.get('status')!r}); the terminal "
        "status and any receipt above are UNCHANGED, but the EFFECT_RECEIPT_RECONCILE_BINDING "
        "artifact that binds receipt <-> terminal journal <-> startup reconcile verdict <-> "
        "independent residue observation does NOT exist on this host, so a downstream reader "
        "cannot verify that binding from evidence"
    ]


def _run_row(
    name: str,
    *,
    driver: Any,
    plan: dict[str, Any],
    intent: dict[str, Any],
    authorizations: dict[str, Any],
    row_payloads: dict[str, Any],
    pg_expected_topology: dict[str, Any],
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
    # C15:payload 只保留該 row 的 exact allowlist 鍵(頂層進入點已 typed 拒過一次;此處是
    # 第二道,確保任何內部呼叫路徑也無法把 code-owned 欄位 splat 進凍結的 row ABI)。
    supplied = (row_payloads or {}).get(name) or {}
    payload = {
        key: value for key, value in supplied.items()
        if key in ROW_PAYLOAD_ALLOWLIST[name]
    }
    if name == "PG_ROLE_ACL_MIGRATION":
        # S2.4-AMEND-2(obligation 25)+ Codex-3 hoist:expected_topology 已在 aggregate
        # precheck(step (2c),driver 未 engage)由簽章 plan 導出——此處只注入前置結果
        # (code-owned、非 caller 預設,與 ``applier_node`` 同款),不重複導出;
        # ``hba_delta`` 仍不得 splat 進凍結的 row ABI。row 函式簽名不動。
        payload.pop("hba_delta", None)
        payload["expected_topology"] = pg_expected_topology
    return ROW_ENTRYPOINTS[name](
        intent, scoped, row_driver,
        now=now, clock=tick, replay_ledger=row_replay_ledger,
        ownership_evidence=(ownership_evidence or {}).get(name),
        # applier≠verifier 的分離欄位是 code-owned 的,不是「caller 沒覆寫才成立」的預設值。
        applier_node=ROW_APPLIER_NODES[name],
        **payload,
    )


def _observe_residue(driver: Any, probe_digests: dict[str, Any]) -> dict[str, Any]:
    """每一條終端路徑的殘留觀測(委派 :func:`agent_governance_s2_4_install_evidence`)。

    回值帶 typed 的 ``observation_status``:``OBSERVED_INACTIVE`` / ``OBSERVED_ACTIVE`` /
    ``OBSERVED_ABSENT`` / ``OBSERVATION_UNAVAILABLE``。呼叫端**必須**分辨最後一種——
    「讀不到」不是「觀測到 active」,更不是可以據以拆掉整筆安裝的證據。
    """

    return _evidence.observe_install_residue(driver, probe_digests)


def _terminal_journal(
    transaction: Any,
    failing_row: str | None,
    plan: dict[str, Any],
    tick: Callable[[], datetime],
    *,
    compensated: bool,
) -> dict[str, Any] | None:
    """把 journal 收到終端態(``COMPENSATED`` / ``FAILED``);落盤失敗回 ``None``。

    E12:``step_index`` 在沒有 failing row 時退回 0,而 journal 葉會由 ``step_index=0`` 推出
    ``HOST_IDENTITY_INSTALL``——一次涵蓋五列的交易級收尾因此被記成第 0 列的事。終端 entry 的
    pre/post 都是 plan 級前態,本來就不屬於任何一 row 的 digest 空間,故它明確宣告交易級 scope。
    """

    state = "COMPENSATED" if compensated else "FAILED"
    step_index = APPLY_ROW_STEP_INDEX.get(failing_row, 0) if failing_row else 0
    verdict = transaction.record(
        state=state, pre_state_digest=plan["core"]["pre_state_digest"],
        post_state_digest=plan["core"]["pre_state_digest"],
        step_index=step_index, terminal=True,
        component_effect_class=_journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
    )
    if verdict["status"] != _journal.JOURNAL_STATUS_COMMITTED:
        return None
    return verdict["journal"]


def _compensate_transaction(
    *,
    plan: dict[str, Any],
    plan_id: str,
    driver: Any,
    file_driver: Any,
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
    # C6:``COMPENSATING`` 與 ``APPLYING`` 是同一種東西——一次**破壞性**的外部 effect 的
    # write-ahead 記錄。它的回值過去被丟掉,於是短寫時 durable journal 裡完全沒有
    # COMPENSATING,五 row 卻已經被逐一補償,verdict 還記成乾淨的 POSTCHECK_FAILED_ROLLED_BACK;
    # 若行程在此消失,WAL 的最後一筆是某 row 的 ``VERIFYING``,重啟的 runner 會對一台已被
    # 部分拆解的主機收斂出 ``RESUME_VERIFICATION``。commit 沒成功就一列都不補償。
    compensating = transaction.record(
        state="COMPENSATING", pre_state_digest=plan["core"]["pre_state_digest"],
        post_state_digest=plan["core"]["pre_state_digest"],
        step_index=APPLY_ROW_STEP_INDEX.get(failing_row, 0) if failing_row else 0,
        # E12:COMPENSATING 覆蓋的是**整條**逆序鏈,不是 step_index 指的那一列。
        component_effect_class=_journal.ENTRY_SCOPE_AGGREGATE_TRANSACTION,
    )
    if compensating["status"] != _journal.JOURNAL_STATUS_COMMITTED:
        residue = _observe_residue(driver, probe_digests)
        return _verdict(
            AGGREGATE_STATUS_RECOVERY_REQUIRED,
            reasons + list(compensating["reasons"]) + [
                "the COMPENSATING write-ahead record could not be durably committed, so NO "
                "reverse compensation was attempted: an un-journalled compensation would leave "
                f"the applied rows {list(applied_rows)} destroyed with no durable evidence, and "
                "a restarting runner would reconcile a partially torn-down host to "
                "RESUME_VERIFICATION (§5.2)"
            ],
            plan_id=plan_id, mutation_performed=bool(applied_rows), driver_engaged=True,
            postcheck=postcheck, step_results=step_results, row_verdicts=row_verdicts,
            replay=replay, reconcile=reconcile, residue=residue,
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
        # C7:``or isinstance(row_verdicts.get(name), dict)`` 對任何產生過 verdict 的 row 恆為
        # 真,而一個 row 只有產生 verdict 才可能進 applied_rows——於是 §5.4 的 ownership-aware
        # 條件從未被計算,production driver 永遠收到「ownership 已驗」。fallback 移除:唯一的
        # 判準是該 row 自己的 rollback artifact 宣告了 ownership_aware。
        row_rollback = (row_verdicts.get(name) or {}).get("rollback")
        ownership_verified = bool(
            isinstance(row_rollback, dict) and row_rollback.get("ownership_aware")
        )
        if not ownership_verified:
            reasons.append(
                f"{name} has no per-row rollback artifact declaring ownership_aware, so the "
                "§5.4 ownership-aware condition is NOT established for its reverse op"
            )
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
        # C2:``row_driver()`` 在這裡是**主機部分施作時**唯一沒有被 try/except 包住的呼叫,
        # 一個 untyped RuntimeError 會直接逸出 §10.2 的凍結 ABI——恰好在最不能逸出的時刻。
        try:
            row_driver = driver.row_driver(component_effect_class=name)
        except Exception as error:  # noqa: BLE001
            exact = False
            reasons.append(
                f"{name} row driver was unavailable during compensation: "
                f"{redact_driver_error(error)}; the reverse op cannot be independently "
                "re-observed, so exact restoration is not claimed"
            )
            reverse_ops.append({
                "component_effect_class": name, "per_row_rollback_digest": digest,
                "ownership_verified": False,
            })
            continue
        # C3:row 級呼叫點早就傳了 ``pre_compensation_observed_digest``,aggregate 級沒有,
        # 於是「回同一常量的 verifier 等於沒真的再看一次」這道檢查在交易層是空的。
        normalized, independent = _component.compensation_with_independent_postcheck(
            outcome, driver=row_driver,
            component_effect_class=name, install_plan_digest=plan["core_digest"],
            applier_node=f"s2-4-{name.lower()}-applier",
            pre_state_digest=plan["core"]["pre_state_digest"],
            pre_compensation_observed_digest=(
                ((row_verdicts.get(name) or {}).get("postcheck") or {})
                .get("observed_subject_digest")
            ),
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
        if residue["observation_status"] == _evidence.RESIDUE_OBSERVATION_UNAVAILABLE:
            reasons.append(
                "the post-compensation unit observation was UNAVAILABLE, not negative; no "
                "result may claim an independently confirmed clean residue"
            )
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
    status = (
        (cause_status or AGGREGATE_STATUS_ROLLED_BACK) if exact
        else AGGREGATE_STATUS_RECOVERY_REQUIRED
    )
    # C20:失敗之後「哪幾列施作過」必須是 durable 事實。step_results / rollback 過去只活在
    # 回傳的 verdict 欄位裡,journal 只記 step_index 而不記 class,終端的
    # COMPENSATING/COMPENSATED 也只帶一個 step_index——operator 因此無法從證據判斷五列的實況。
    evidence_set = _commit_evidence_set(
        file_driver=file_driver, plan=plan, terminal_status=status,
        step_results=step_results, rollback=rollback, journal=journal,
        reconcile=reconcile, residue=residue, receipt=None, applied_rows=applied_rows,
        observed_at=_iso(tick()),
    )
    return _verdict(
        status,
        reasons + _evidence_set_reasons(evidence_set) + [
            "the applied task-owned delta was compensated in reverse §5.4 order and every "
            "reverse op was confirmed by an INDEPENDENT post-compensation re-observation"
            if exact else
            "safe exact compensation could not be proved; the service stays disabled/inactive, "
            "RECOVERY_REQUIRED records the exact residual and blocks S2.5 (§5.4)"
        ],
        plan_id=plan_id, mutation_performed=bool(applied_rows), driver_engaged=True,
        postcheck=postcheck, rollback=rollback, step_results=step_results,
        row_verdicts=row_verdicts, journal=journal, replay=replay, reconcile=reconcile,
        residue=residue, evidence_set=evidence_set,
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
        # 只存在於 verdict、永不簽發 receipt 的兩個終端(故不在凍結 receipt enum 內)。
        "aggregate_transaction_only_statuses": list(AGGREGATE_TRANSACTION_ONLY_STATUSES),
        "row_payload_allowlist": {
            name: list(keys) for name, keys in ROW_PAYLOAD_ALLOWLIST.items()
        },
        "row_applier_nodes": dict(ROW_APPLIER_NODES),
        **_evidence.install_evidence_abi_projection(),
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

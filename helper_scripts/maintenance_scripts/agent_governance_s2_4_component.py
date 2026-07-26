#!/usr/bin/env python3
"""S2.4(WP4·W3b)五個 APPLY component-effect 的**共用**契約機制葉(§4 / §5.3 / §5.4)。

由 :mod:`agent_governance_s2_4_apply` 依 2000 行治理拆出;apply 上層逐名 re-export,
消費者匯入面不變。本葉不含任何 row 專屬的主機動作,只含五 row 共用的:

- typed 終端狀態集與 result-schema 的封閉 enum 投影;
- caller raw-ingress 掃描(硬邊界 4)與 §4 逐 row ABI 的凍結矩陣再導出;
- ``s2_4_component_effect_intent_v1`` 建構與 §10.5 #31 的 host-identity 分類謂詞;
- 授權集合驗證(§6 step 6:aggregate + 必要時 PG permit;PG permit 永不代替 aggregate);
- §5.3 pre-existing-state 決策矩陣;
- WAL 轉移記錄器與 result / 獨立 postcheck / rollback 三個 artifact 的建構;
- 共用收尾:``_finish_row``(postcheck 失敗即逆向補償)與 ``_compensating_failure``。

九 authority / production_apply_performed / running_attested 恆 false。
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parents[2]
HELPER_DIR = REPO_ROOT / "helper_scripts" / "maintenance_scripts"
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
PROGRAM_CODE_DIR = REPO_ROOT / "program_code"
for _candidate in (HELPER_DIR, ML_TRAINING_DIR, PROGRAM_CODE_DIR):
    if str(_candidate) not in sys.path:
        sys.path.insert(0, str(_candidate))

import aiml_gate_receipt_validator as central_validator  # noqa: E402
import agent_governance_s2_4_credential as _credential  # noqa: E402

canonical_digest = central_validator.canonical_digest
artifact_self_digest = central_validator.artifact_self_digest
# §7/§10.5 #15:秘密掃描與例外紅字化的唯一來源(credential 葉只依賴中央 validator,無循環)。
redact_driver_error = _credential.redact_driver_error
scan_serializable_surface = _credential.scan_serializable_surface


# ── §4 / §9.1 code-owned 契約常量 ───────────────────────────────────────────────
COMPONENT_CLASSES = (
    "HOST_IDENTITY_INSTALL",
    "PG_ROLE_ACL_MIGRATION",
    "CREDENTIAL_INSTALL",
    "LEARNING_RUNTIME",
    "ENGINE_SCANNER",
)
APPLY_AGGREGATE_PROFILE = "aiml-s2-install-operator-v1"
APPLY_AGGREGATE_NAMESPACE = "arcane-equilibrium-aiml-s2-install"
PG_MIGRATION_PROFILE = "aiml-s2-pg-migration-operator-v1"
PG_MIGRATION_NAMESPACE = "arcane-equilibrium-aiml-s2-pg-migration"
# §6 step 6:aggregate permit 覆蓋全交易;PG row 另需更窄的 PG-migration permit。
# §10.5 #31:host/credential/runtime/unit row **絕不**能只憑 PG permit 放行。
COMPONENT_REQUIRED_PROFILES: dict[str, tuple[str, ...]] = {
    "HOST_IDENTITY_INSTALL": ("apply_aggregate",),
    "PG_ROLE_ACL_MIGRATION": ("apply_aggregate", "pg_migration"),
    "CREDENTIAL_INSTALL": ("apply_aggregate",),
    "LEARNING_RUNTIME": ("apply_aggregate",),
    "ENGINE_SCANNER": ("apply_aggregate",),
}
COMPONENT_EVIDENCE_TTL_SECONDS = 900

# ── typed 終端狀態(§10.2;無別名可把其一變成 success)──────────────────────────
COMPONENT_STATUS_SATISFIED = "SATISFIED"
COMPONENT_STATUS_NOOP_VERIFIED = "NOOP_VERIFIED"
COMPONENT_STATUS_PENDING = "EXTERNAL_VERIFICATION_PENDING"
COMPONENT_STATUS_AUTHORIZATION_REJECTED = "AUTHORIZATION_REJECTED"
COMPONENT_STATUS_REQUEST_REJECTED = "COMPONENT_REQUEST_REJECTED"
COMPONENT_STATUS_RAW_INGRESS_REJECTED = "RAW_INGRESS_REJECTED"
COMPONENT_STATUS_PRECHECK_FAILED = "PRECHECK_FAILED"
COMPONENT_STATUS_PRESTATE_MISMATCH = "PRESTATE_MISMATCH"
COMPONENT_STATUS_PREEXISTING_UNOWNED = "PREEXISTING_UNOWNED_STATE"
COMPONENT_STATUS_TOPOLOGY_UNPROVEN = "PG_TOPOLOGY_UNPROVEN"
COMPONENT_STATUS_BUNDLE_INVALID = "PREPARED_BUNDLE_INVALID"
COMPONENT_STATUS_CREDENTIAL_UNSATISFIED = "HOST_CREDENTIAL_CAPABILITY_UNSATISFIED"
COMPONENT_STATUS_POSTCHECK_ROLLED_BACK = "POSTCHECK_FAILED_ROLLED_BACK"
COMPONENT_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"
COMPONENT_STATUS_FAILED = "FAILED"
# §10.5 #15:任何即將被回傳的 verdict/artifact 掃出秘密材料即以此 typed 狀態 fail-closed
# (絕不回傳被污染的結構,也絕不讓 SecretMaterialLeak 從 fail-closed 閘中逸出)。
COMPONENT_STATUS_SECRET_LEAK_BLOCKED = "SECRET_MATERIAL_LEAK_BLOCKED"
COMPONENT_TYPED_STATUSES = (
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
)
# result schema 的封閉 enum(verdict 的細分 typed status 於此投影到 artifact)。
_RESULT_STATUS_ENUM = {
    COMPONENT_STATUS_SATISFIED: "SATISFIED",
    COMPONENT_STATUS_NOOP_VERIFIED: "NOOP_VERIFIED",
    COMPONENT_STATUS_PREEXISTING_UNOWNED: "PREEXISTING_UNOWNED_STATE",
    COMPONENT_STATUS_PRESTATE_MISMATCH: "PRESTATE_MISMATCH",
    COMPONENT_STATUS_RECOVERY_REQUIRED: "RECOVERY_REQUIRED",
}
# 硬邊界 4:caller 絕不得經任何鍵遞交 raw shell/SQL/unit 文本/任意目的地路徑/秘密。
#
# 「目的地」路徑鍵才入本表(``target_root`` / ``fragment_path`` / ``slot_path`` …):code-owned
# 契約物件(如靜態目錄樹)內的結構性 ``path`` 欄位不是 caller 自由面——它必須逐欄等於
# :func:`host_identity_directory_tree`,任何 worker 自選目錄在 exactness 比對即 typed 拒。
COMPONENT_RAW_INGRESS_KEYS = (
    "argv",
    "command",
    "commands",
    "dsn",
    "fragment_path",
    "grant_sql",
    "install_root",
    "password",
    "role_password",
    "script",
    "secret",
    "shell",
    "slot_path",
    "sql",
    "staging_root",
    "statements",
    "target_path",
    "target_root",
    "unit_bytes",
    "unit_text",
)
# §8.3:安裝後絕不可存在於 driver 上的生命週期操作面(ENGINE_SCANNER row 硬檢)。
FORBIDDEN_UNIT_LIFECYCLE_METHODS = (
    "enable",
    "enable_unit",
    "kill",
    "reload_or_restart",
    "restart",
    "restart_unit",
    "send_signal",
    "signal",
    "start",
    "start_unit",
    "try_restart",
)

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_ALL_FALSE_PRODUCTION_FLAGS = {
    "nine_authorities_false": True,
    "production_apply_performed": False,
    "running_attested": False,
}
# §5.3/§5.4:ownership_evidence 的封閉形狀——每個 subject 都必須帶 digest 形狀的 receipt +
# journal 綁定。裸 ``{}`` / ``{"x": {}}`` / 非 digest 字串一律不成立(絕不把
# PREEXISTING_UNOWNED_STATE 換成放行)。
OWNERSHIP_EVIDENCE_REQUIRED_FIELDS = ("journal_digest", "s2_4_receipt_digest")
# §10.2:evidence_class 的封閉集合;attested 兩級只能由**可驗證的**平台背書取得。
EVIDENCE_CLASS_STRUCTURAL_ONLY = "STRUCTURAL_ONLY"
EVIDENCE_CLASS_ATTESTED = ("PLATFORM_ATTESTED", "PLATFORM_OR_EXTERNAL_ATTESTED")
EVIDENCE_CLASS_STATUS_RECORDED = "EVIDENCE_CLASS_RECORDED"
EVIDENCE_CLASS_STATUS_SELF_DECLARATION_REFUSED = "EVIDENCE_CLASS_SELF_DECLARATION_REFUSED"
# §5.4:補償結果的三分——「沒有拋例外」不等於「前態已被 exact 還原」。
COMPENSATION_STATUS_EXACT = "COMPENSATED_EXACT"
COMPENSATION_STATUS_NOT_REOBSERVED = "COMPENSATED_NOT_REOBSERVED"
COMPENSATION_STATUS_NOT_COMPENSATED = "NOT_COMPENSATED"
COMPENSATION_STATUS_RECOVERY_REQUIRED = "RECOVERY_REQUIRED"

class ComponentContractError(ValueError):
    """component-effect 契約層硬錯誤(帶 typed ``code``)。"""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


# --------------------------------------------------------------------------- #
# 共用:raw ingress / row ABI / 授權 / pre-state 矩陣 / artifact builders
# --------------------------------------------------------------------------- #
def component_raw_ingress_reasons(*payloads: Any) -> list[str]:
    """硬邊界 4:掃出 caller 夾帶的 raw shell/SQL/unit/目的地路徑/秘密鍵即 typed 拒。

    掃描對象只有 **caller 自由塑形**的載荷(intent 的 required_intent_fields、renderer 欄位、
    policy 預算)。code-owned 契約物件(UID/GID 目錄樹、target manifest)不入此掃描:它們的
    每一欄都要逐位元組等於本模組凍結的契約,worker 自選值在那一步就是 typed 拒,對它們做
    「危險鍵名」掃描只會把 ``shell`` / ``path`` 這類**合法結構欄位**誤判。
    """

    reasons: list[str] = []

    def _walk(node: Any, trail: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key) in COMPONENT_RAW_INGRESS_KEYS:
                    reasons.append(
                        f"caller-provided raw ingress key {trail}{key!r} is rejected: no S2.4 "
                        "component driver accepts caller shell, SQL, unit text, secrets or "
                        "arbitrary filesystem paths"
                    )
                _walk(value, f"{trail}{key}.")
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item, trail)

    for payload in payloads:
        _walk(payload, "")
    return reasons


def component_row_abi(component_effect_class: Any) -> dict[str, Any]:
    """凍結 v2 矩陣的 exact row ABI(adapter/actor/postcheck node/rollback 契約)。"""

    row = central_validator.AIML_COMPONENT_EFFECT_CLASS_MATRIX_V2.get(
        str(component_effect_class)
    )
    if row is None or str(component_effect_class) not in COMPONENT_CLASSES:
        raise ComponentContractError("component_effect_class_not_an_apply_row")
    return {
        "component_effect_class": str(component_effect_class),
        "adapter_id": row["adapter_id"],
        "actor_node_id": row["actor_node_id"],
        "independent_postcheck_node_id": row["independent_postcheck_node_id"],
        "recovery_contract": row["recovery_contract"],
        "adapter_binding_status": row["adapter_binding_status"],
        "required_intent_fields": list(row["required_intent_fields"]),
        "required_authorization_profiles": list(
            COMPONENT_REQUIRED_PROFILES[str(component_effect_class)]
        ),
    }


def build_component_effect_intent(
    *,
    component_effect_class: str,
    install_plan_digest: str,
    pre_state_digest: str,
    required_intent_fields: dict[str, Any],
    expires_at: str,
) -> dict[str, Any]:
    """closed ``s2_4_component_effect_intent_v1``(class-specific 鍵集由中央閘再導出執法)。"""

    intent = {
        "schema_version": "s2_4_component_effect_intent_v1",
        "component_effect_class": component_effect_class,
        "install_plan_digest": install_plan_digest,
        "pre_state_digest": pre_state_digest,
        "required_intent_fields": dict(required_intent_fields),
        "expires_at": expires_at,
    }
    intent["self_digest"] = artifact_self_digest(intent)
    return intent


def derive_host_identity_effect_class_status(
    *, subject_kind: str, declared_class: Any
) -> dict[str, Any]:
    """§10.5 #31:host user/group/directory subject 只能分類為 ``HOST_IDENTITY_INSTALL``。"""

    host_subjects = {"host_user", "host_group", "host_directory"}
    if subject_kind not in host_subjects:
        return {
            "status": "NOT_A_HOST_IDENTITY_SUBJECT",
            "reasons": [f"{subject_kind!r} is not a host user/group/directory subject"],
        }
    if declared_class == "HOST_IDENTITY_INSTALL":
        return {"status": "HOST_IDENTITY_CLASSIFICATION_ADMITTED", "reasons": []}
    return {
        "status": "HOST_IDENTITY_CLASSIFICATION_REJECTED",
        "reasons": [
            f"a {subject_kind} effect declared component_effect_class={declared_class!r}; "
            "host identity effects classify only as HOST_IDENTITY_INSTALL and a PG permit "
            "can never authorize host user/group/directory mutation (§10.5 #31)"
        ],
    }


def _authorization_set_reasons(
    authorization_set: Any,
    replay_ledger: Any,
    *,
    component_effect_class: str,
    now: str | datetime | None,
) -> list[str]:
    """逐 profile 驗 §9.1 授權並綁 replay 消費;缺 aggregate permit 即明文點名 PG-permit 縫。"""

    required = COMPONENT_REQUIRED_PROFILES[component_effect_class]
    if not isinstance(authorization_set, dict):
        return ["authorization_set must be a mapping of profile key -> authorization"]
    reasons: list[str] = []
    supplied = sorted(authorization_set)
    for profile_key in required:
        authorization = authorization_set.get(profile_key)
        if not isinstance(authorization, dict):
            if profile_key == "apply_aggregate" and "pg_migration" in supplied:
                reasons.append(
                    f"{component_effect_class} is missing the aggregate install permit; the "
                    "supplied PG-migration permit cannot authorize this row (a PG permit "
                    "never authorizes host user/group/directory mutation, §10.5 #31)"
                )
            else:
                reasons.append(
                    f"{component_effect_class} requires the {profile_key} authorization; none was supplied"
                )
            continue
        profile = central_validator.S2_4_AUTHORIZATION_PROFILES[profile_key]
        if authorization.get("profile_identity") != profile["profile_identity"]:
            reasons.append(
                f"{profile_key} authorization profile_identity is not {profile['profile_identity']}"
            )
        if authorization.get("signature_namespace") != profile["signature_namespace"]:
            reasons.append(f"{profile_key} authorization signature_namespace is not the {profile_key} namespace")
        if replay_ledger is None:
            reasons.append(
                f"{profile_key} authorization replay-consumption cannot be proved without the "
                "authorization replay ledger (fail-closed)"
            )
            continue
        replay = central_validator.derive_authorization_replay_binding(
            authorization, replay_ledger, now=now
        )
        if replay["status"] != "UNCONSUMED_AUTHORIZATION_VALID":
            reasons.extend(f"{profile_key}: {reason}" for reason in replay["reasons"])
    extra = sorted(set(supplied) - set(required))
    if extra:
        reasons.append(
            f"{component_effect_class} was handed unrelated authorization profiles {extra}; "
            "each row consumes only its own admitted permits"
        )
    return reasons


def ownership_binding_present(evidence: Any) -> bool:
    """單一 subject 的 ownership 綁定是否成立(兩個欄位都必須是 digest 形狀)。"""

    if not isinstance(evidence, dict):
        return False
    for field in OWNERSHIP_EVIDENCE_REQUIRED_FIELDS:
        value = evidence.get(field)
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            return False
    return True


def ownership_evidence_reasons(ownership_evidence: Any) -> list[str]:
    """§5.3/§5.4:``ownership_evidence`` 的統一形狀驗證(driver 接觸之前)。

    caller 遞交的必須是「subject → 證據物件」的映射,且每一筆都逐欄綁 digest 形狀的
    ``s2_4_receipt_digest`` + ``journal_digest``。裸 ``dict``、``{}`` 的 subject 值、
    或任何非 digest 字串一律 typed 拒——**絕不**讓一個空物件把
    ``PREEXISTING_UNOWNED_STATE`` 轉成放行(W3 review E2 P1-3 / E3 P1-1)。
    """

    if ownership_evidence is None:
        return []
    if not isinstance(ownership_evidence, dict):
        return [
            "ownership_evidence must be a mapping of subject -> {s2_4_receipt_digest, "
            "journal_digest}; S2.4 never adopts pre-existing state on an unvalidated value"
        ]
    reasons: list[str] = []
    for subject in sorted(str(key) for key in ownership_evidence):
        evidence = ownership_evidence[subject]
        if not isinstance(evidence, dict):
            reasons.append(f"ownership_evidence[{subject!r}] must be an object")
            continue
        for field in OWNERSHIP_EVIDENCE_REQUIRED_FIELDS:
            value = evidence.get(field)
            if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
                reasons.append(
                    f"ownership_evidence[{subject!r}].{field} must be a sha256 digest bound to "
                    "the prior S2.4 receipt/journal (a bare object never proves task ownership)"
                )
    return reasons


def derive_recorded_evidence_class(driver: Any) -> dict[str, Any]:
    """把 driver **自報**的 ``evidence_class`` 收斂成「可被記錄」的等級(§10.2)。

    誠實界線:``evidence_class`` 是注入物件上的一個自報欄位——in-process 沒有任何方法
    能把 fixture 與真主機 driver 區分開(兩者都能寫 ``evidence_class =
    "PLATFORM_ATTESTED"``)。故本閘**拒絕**憑自報就記錄 attested 等級:W3 沒有(也不該有)
    trusted-host attestation 的驗證面,那屬 W4/W6;在此之前一律記錄
    ``STRUCTURAL_ONLY`` 並附 typed 說明。這是「閘拒絕自證」而非「接受自證」。
    """

    declared = str(getattr(driver, "evidence_class", EVIDENCE_CLASS_STRUCTURAL_ONLY))
    if declared in EVIDENCE_CLASS_ATTESTED:
        return {
            "status": EVIDENCE_CLASS_STATUS_SELF_DECLARATION_REFUSED,
            "declared_evidence_class": declared,
            "recorded_evidence_class": EVIDENCE_CLASS_STRUCTURAL_ONLY,
            "reasons": [
                f"the injected driver self-declares evidence_class={declared!r}; a self-declared "
                "attested class is never recorded because nothing in-process can distinguish a "
                "fixture from a real host driver. W3 records STRUCTURAL_ONLY until a trusted-host "
                "platform attestation verifier exists (W4/W6 obligation)"
            ],
        }
    return {
        "status": EVIDENCE_CLASS_STATUS_RECORDED,
        "declared_evidence_class": declared,
        "recorded_evidence_class": (
            declared if declared == EVIDENCE_CLASS_STRUCTURAL_ONLY else EVIDENCE_CLASS_STRUCTURAL_ONLY
        ),
        "reasons": [],
    }


def compensation_outcome(*, compensated: bool, reobserved: bool | None) -> dict[str, Any]:
    """§5.4:補償的 typed 結果——``compensated`` 只說「動作沒拋例外」,
    ``reobserved`` 才說「補償後的**再觀測**是否等於擷取的前態」。"""

    return {
        "compensated": bool(compensated),
        "reobserved": None if reobserved is None else bool(reobserved),
    }


def normalize_compensation(value: Any) -> dict[str, Any]:
    """把補償回傳值(dict 或 legacy bool)收斂成 :func:`compensation_outcome` 形。"""

    if isinstance(value, dict) and "compensated" in value:
        return compensation_outcome(
            compensated=bool(value.get("compensated")), reobserved=value.get("reobserved")
        )
    return compensation_outcome(compensated=bool(value), reobserved=None)


def derive_compensation_status(compensation: dict[str, Any]) -> tuple[str, bool]:
    """回 ``(rollback_status, exact_pre_state_restored)``。

    ``COMPENSATED_EXACT`` **只**在補償跑完且再觀測確認等於前態時成立;再觀測矛盾即
    ``RECOVERY_REQUIRED``;protocol 無法再觀測即 ``COMPENSATED_NOT_REOBSERVED``
    (不宣稱 exact)。「沒有拋例外」永遠不足以宣稱 exact(W3 review E2 P1-4)。
    """

    compensated = bool(compensation.get("compensated"))
    reobserved = compensation.get("reobserved")
    if not compensated:
        return (COMPENSATION_STATUS_RECOVERY_REQUIRED, False)
    if reobserved is True:
        return (COMPENSATION_STATUS_EXACT, True)
    if reobserved is False:
        return (COMPENSATION_STATUS_RECOVERY_REQUIRED, False)
    return (COMPENSATION_STATUS_NOT_REOBSERVED, False)


def classify_pre_state(
    *, observed: Any, desired: Any, ownership_evidence: Any
) -> dict[str, Any]:
    """§5.3 決策矩陣:第一次變更之前把每個資源分類。"""

    if observed is None:
        return {"state": "ABSENT", "reasons": []}
    if observed == desired:
        if ownership_binding_present(ownership_evidence):
            return {"state": "NOOP_VERIFIED", "reasons": []}
        return {
            "state": "PREEXISTING_UNOWNED_STATE",
            "reasons": [
                "the exact desired state exists without matching S2.4 ownership evidence; "
                "no adoption is performed"
            ],
        }
    drift = sorted(
        key
        for key in set(desired if isinstance(desired, dict) else {})
        | set(observed if isinstance(observed, dict) else {})
        if (observed or {}).get(key) != (desired or {}).get(key)
    ) if isinstance(desired, dict) and isinstance(observed, dict) else []
    return {
        "state": "PRESTATE_MISMATCH",
        "reasons": [
            "pre-existing state differs from the signed desired state"
            + (f" (drifted attributes: {drift})" if drift else "")
            + "; no overwrite is performed"
        ],
    }


def classify_ownership_only(
    *, observed_subject: Any, ownership_evidence: Any
) -> dict[str, Any]:
    """只裁決擁有權的 §5.3 分支(E2 P2-D:語義與行為一致)。

    有些資源沒有可逐欄比對的「signed desired state」——PG 的既有 grant-set 就是一例,
    它的漂移偵測靠的是對前一份 S2.4 receipt 之 ``applied_state_digest`` 的重導出,而不是
    欄位比對。這些 row 過去以 ``observed == desired`` 呼叫 :func:`classify_pre_state`,
    讀起來像在偵測漂移,結構上卻永遠不可能回 ``PRESTATE_MISMATCH``。本函式把該意圖寫明:
    absent → ``ABSENT``;存在且有 S2.4 擁有權證據 → ``NOOP_VERIFIED``;存在但無證據 →
    ``PREEXISTING_UNOWNED_STATE``(不收養、不覆寫)。漂移由呼叫端的 digest 重導出負責。
    """

    if observed_subject is None:
        return {"state": "ABSENT", "reasons": []}
    if ownership_binding_present(ownership_evidence):
        return {"state": "NOOP_VERIFIED", "reasons": []}
    return {
        "state": "PREEXISTING_UNOWNED_STATE",
        "reasons": [
            "the resource exists without matching S2.4 ownership evidence; "
            "no adoption is performed"
        ],
    }


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _resolve_now(now: str | datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    return central_validator._parse_timestamp(now)


def _verdict(
    status: str,
    reasons: list[str],
    *,
    component_effect_class: str,
    row_abi: dict[str, Any] | None = None,
    mutation_performed: bool = False,
    driver_engaged: bool = False,
    result: dict[str, Any] | None = None,
    postcheck: dict[str, Any] | None = None,
    rollback: dict[str, Any] | None = None,
    journal_entries: list[dict[str, Any]] | None = None,
    observed_subjects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    verdict = {
        "schema_version": "s2_4_component_effect_run_verdict_v1_informal",
        "status": status,
        "reasons": list(reasons),
        "component_effect_class": component_effect_class,
        "row_abi": row_abi,
        "mutation_performed": bool(mutation_performed),
        "driver_engaged": bool(driver_engaged),
        "blocks_aggregate": status not in {
            COMPONENT_STATUS_SATISFIED, COMPONENT_STATUS_NOOP_VERIFIED
        },
        "result": result,
        "postcheck": postcheck,
        "rollback": rollback,
        "journal_entries": list(journal_entries or []),
        "observed_subjects": observed_subjects,
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "secret_material_scanned": True,
    }
    # §10.5 #15:這是五個 APPLY row **唯一**的 verdict 建構點,也是 result / postcheck /
    # rollback / journal / observed_subjects 的唯一出境面。任一處出現進程內活哨兵的秘密
    # 材料(或其常見編碼形)即整份丟棄,只回一個不帶任何被污染結構的 typed 拒絕。
    leak_reasons = scan_serializable_surface(verdict)
    if leak_reasons:
        return {
            "schema_version": "s2_4_component_effect_run_verdict_v1_informal",
            "status": COMPONENT_STATUS_SECRET_LEAK_BLOCKED,
            "reasons": leak_reasons + [
                "the constructed component-effect verdict carried secret material; every "
                "artifact, reason and observation was dropped rather than returned (§7)"
            ],
            "component_effect_class": component_effect_class,
            "row_abi": row_abi,
            "mutation_performed": bool(mutation_performed),
            "driver_engaged": bool(driver_engaged),
            "blocks_aggregate": True,
            "result": None,
            "postcheck": None,
            "rollback": None,
            "journal_entries": [],
            "observed_subjects": None,
            "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
            "secret_material_scanned": True,
        }
    return verdict


def _component_precheck(
    intent: Any,
    authorization_set: Any,
    replay_ledger: Any,
    *,
    expected_class: str,
    now: str | datetime | None,
    ingress_payloads: tuple[Any, ...] = (),
    ownership_evidence: Any = None,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """driver 接觸之前的共同閘;回 ``(reject_verdict|None, row_abi|None)``。"""

    if not isinstance(intent, dict):
        return (
            _verdict(
                COMPONENT_STATUS_REQUEST_REJECTED,
                ["component effect intent must be an object"],
                component_effect_class=expected_class,
            ),
            None,
        )
    declared = intent.get("component_effect_class")
    if declared != expected_class:
        return (
            _verdict(
                COMPONENT_STATUS_REQUEST_REJECTED,
                [
                    f"this driver applies only {expected_class} rows; the intent declares "
                    f"{declared!r} (cross-class substitution is rejected before any host contact)"
                ],
                component_effect_class=expected_class,
            ),
            None,
        )
    schema_errors = central_validator.validate_aiml_artifact(intent, now=None)
    if schema_errors:
        return (
            _verdict(
                COMPONENT_STATUS_REQUEST_REJECTED,
                schema_errors,
                component_effect_class=expected_class,
            ),
            None,
        )
    row_abi = component_row_abi(expected_class)
    # §5.3:ownership_evidence 的形狀在任何 driver 接觸之前統一驗證(五 row 一致)。
    ownership_reasons = ownership_evidence_reasons(ownership_evidence)
    if ownership_reasons:
        return (
            _verdict(
                COMPONENT_STATUS_REQUEST_REJECTED,
                ownership_reasons,
                component_effect_class=expected_class,
                row_abi=row_abi,
            ),
            row_abi,
        )
    ingress = component_raw_ingress_reasons(intent.get("required_intent_fields"), *ingress_payloads)
    if ingress:
        return (
            _verdict(
                COMPONENT_STATUS_RAW_INGRESS_REJECTED,
                ingress,
                component_effect_class=expected_class,
                row_abi=row_abi,
            ),
            row_abi,
        )
    authorization_reasons = _authorization_set_reasons(
        authorization_set, replay_ledger, component_effect_class=expected_class, now=now
    )
    if authorization_reasons:
        return (
            _verdict(
                COMPONENT_STATUS_AUTHORIZATION_REJECTED,
                authorization_reasons,
                component_effect_class=expected_class,
                row_abi=row_abi,
            ),
            row_abi,
        )
    now_dt = _resolve_now(now)
    try:
        expires = central_validator._parse_timestamp(intent["expires_at"])
    except (KeyError, TypeError, ValueError):
        return (
            _verdict(
                COMPONENT_STATUS_REQUEST_REJECTED,
                ["component effect intent expires_at is invalid"],
                component_effect_class=expected_class,
                row_abi=row_abi,
            ),
            row_abi,
        )
    if now_dt >= expires:
        return (
            _verdict(
                COMPONENT_STATUS_REQUEST_REJECTED,
                ["component effect intent is expired"],
                component_effect_class=expected_class,
                row_abi=row_abi,
            ),
            row_abi,
        )
    return (None, row_abi)


def _pending_verdict(component_effect_class: str, row_abi: dict[str, Any]) -> dict[str, Any]:
    return _verdict(
        COMPONENT_STATUS_PENDING,
        [
            f"{component_effect_class} is reachable but authority-locked: no host driver is "
            "present (Mac/source/test lane); EXTERNAL_VERIFICATION_PENDING with zero mutation"
        ],
        component_effect_class=component_effect_class,
        row_abi=row_abi,
    )


def _build_result(
    *,
    component_effect_class: str,
    install_plan_digest: str,
    status: str,
    applied_state_digest: str,
    postcheck_digest: str,
    rollback_digest: str,
    pre_state_digest: str,
    post_state_digest: str,
    evidence_class: str,
    observed_at: str,
) -> dict[str, Any]:
    result = {
        "schema_version": "s2_4_component_effect_result_v1",
        "component_effect_class": component_effect_class,
        "install_plan_digest": install_plan_digest,
        "status": _RESULT_STATUS_ENUM.get(status, "FAILED"),
        "applied_state_digest": applied_state_digest,
        "postcheck_digest": postcheck_digest,
        "rollback_digest": rollback_digest,
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        # evidence_class 已由 derive_recorded_evidence_class 收斂(自報 attested 一律被拒)。
        "evidence_class": (
            evidence_class
            if evidence_class == EVIDENCE_CLASS_STRUCTURAL_ONLY
            else EVIDENCE_CLASS_STRUCTURAL_ONLY
        ),
        "production_authority_flags": dict(_ALL_FALSE_PRODUCTION_FLAGS),
        "observed_at": observed_at,
    }
    result["self_digest"] = artifact_self_digest(result)
    return result


def _build_postcheck(
    *,
    driver: Any,
    component_effect_class: str,
    install_plan_digest: str,
    applier_node: str,
    clock: Callable[[], datetime],
) -> tuple[dict[str, Any] | None, list[str]]:
    """相異 verifier 節點的獨立 per-row postcheck(applier 不得自證)。"""

    try:
        observed = driver.independent_postcheck(
            component_effect_class=component_effect_class,
            install_plan_digest=install_plan_digest,
            applier_node=applier_node,
        )
    except Exception as error:  # noqa: BLE001
        return None, [
            f"independent {component_effect_class} postcheck failed: "
            f"{redact_driver_error(error)}"
        ]
    if not isinstance(observed, dict):
        return None, [f"independent {component_effect_class} postcheck did not return an object"]
    verifier_node = str(observed.get("verifier_node", ""))
    if not verifier_node or verifier_node == applier_node:
        return None, ["independent postcheck verifier_node must differ from the applier"]
    for field in ("observed_subject_digest", "verifier_capture_digest"):
        value = observed.get(field)
        if not isinstance(value, str) or _DIGEST_RE.fullmatch(value) is None:
            return None, [f"independent postcheck {field} is invalid"]
    at = clock()
    flags = {
        "applied_state_verified": bool(observed.get("applied_state_verified")),
        "pre_state_lineage_verified": bool(observed.get("pre_state_lineage_verified")),
    }
    postcheck = {
        "schema_version": "s2_4_component_effect_postcheck_v1",
        "status": "PASS" if all(flags.values()) else "FAIL",
        "component_effect_class": component_effect_class,
        "install_plan_digest": install_plan_digest,
        "verifier_node": verifier_node,
        "applier_node": applier_node,
        "observed_subject_digest": observed["observed_subject_digest"],
        **flags,
        "verifier_capture_digest": observed["verifier_capture_digest"],
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=COMPONENT_EVIDENCE_TTL_SECONDS)),
    }
    postcheck["self_digest"] = artifact_self_digest(postcheck)
    return postcheck, (
        [] if postcheck["status"] == "PASS" else [f"independent {component_effect_class} postcheck FAILED"]
    )


def _build_rollback(
    *,
    component_effect_class: str,
    install_plan_digest: str,
    pre_state_digest: str,
    post_state_digest: str,
    compensation: dict[str, Any],
    ownership_aware: bool,
    clock: Callable[[], datetime],
    mutation_performed: bool = True,
) -> dict[str, Any]:
    """§5.4:rollback 契約 artifact。

    ``status`` / ``exact_pre_state_restored`` **只**由 :func:`derive_compensation_status`
    自實際再觀測導出;沒有再觀測就不得宣稱 ``COMPENSATED_EXACT``。
    ``mutation_performed=False``(從未動過主機)時,不存在需要還原的 delta,
    故 rollback 記 ``NOT_COMPENSATED`` 且不宣稱 exact。
    """

    at = clock()
    if not mutation_performed:
        status, exact = (COMPENSATION_STATUS_NOT_COMPENSATED, False)
    else:
        status, exact = derive_compensation_status(compensation)
    rollback = {
        "schema_version": "s2_4_component_effect_rollback_v1",
        "status": status,
        "component_effect_class": component_effect_class,
        "install_plan_digest": install_plan_digest,
        "pre_state_digest": pre_state_digest,
        "post_state_digest": post_state_digest,
        "ownership_aware": bool(ownership_aware),
        "exact_pre_state_restored": bool(exact),
        # §5.4:補償永不讀取/序列化/重建任何既有秘密。
        "no_secret_reconstructed": True,
        "observed_at": _iso(at),
        "expires_at": _iso(at + timedelta(seconds=COMPONENT_EVIDENCE_TTL_SECONDS)),
    }
    rollback["self_digest"] = artifact_self_digest(rollback)
    return rollback


class _Journal:
    """per-row 的 WAL 轉移記錄器(真持久化屬 W4;此處保「先寫後做」語義)。"""

    def __init__(self, driver: Any, clock: Callable[[], datetime]) -> None:
        self.driver = driver
        self.clock = clock
        self.entries: list[dict[str, Any]] = []

    def write(self, state: str, pre: str, post: str) -> None:
        entry = {
            "seq": len(self.entries),
            "state": state,
            "pre_state_digest": pre,
            "post_state_digest": post,
            "fsynced": True,
            "recorded_at": _iso(self.clock()),
        }
        self.driver.journal_transition(entry=entry)
        self.entries.append(entry)


def _subject_digest(payload: Any) -> str:
    return canonical_digest(payload)


# --------------------------------------------------------------------------- #
# 共用收尾:獨立 postcheck → result/rollback;postcheck 失敗即逆向補償。
# --------------------------------------------------------------------------- #
def _finish_row(
    *,
    status: str,
    reasons: list[str],
    component_effect_class: str,
    row_abi: dict[str, Any],
    driver: Any,
    plan_digest: str,
    pre_state_digest: str,
    post_state_digest: str,
    applied_state_digest: str,
    journal: _Journal,
    applier_node: str,
    clock: Callable[[], datetime],
    mutation_performed: bool,
    compensate: Callable[[], Any],
    observed_subjects: Any = None,
) -> dict[str, Any]:
    postcheck, postcheck_reasons = _build_postcheck(
        driver=driver, component_effect_class=component_effect_class,
        install_plan_digest=plan_digest, applier_node=applier_node, clock=clock,
    )
    evidence = derive_recorded_evidence_class(driver)
    if postcheck is None or postcheck["status"] != "PASS":
        compensation = (
            normalize_compensation(compensate()) if mutation_performed
            else compensation_outcome(compensated=True, reobserved=True)
        )
        rollback = _build_rollback(
            component_effect_class=component_effect_class, install_plan_digest=plan_digest,
            pre_state_digest=pre_state_digest, post_state_digest=post_state_digest,
            compensation=compensation, ownership_aware=True, clock=clock,
            mutation_performed=mutation_performed,
        )
        compensated = bool(compensation["compensated"])
        try:
            journal.write(
                "COMPENSATED" if compensated else "FAILED", post_state_digest, pre_state_digest
            )
        except Exception as error:  # noqa: BLE001
            postcheck_reasons = postcheck_reasons + [
                f"compensation journal failed: {redact_driver_error(error)}"
            ]
            compensated = False
        # 補償未跑完、或再觀測**反證**了 exact 還原,一律 RECOVERY_REQUIRED;
        # 只有「跑完 + 再觀測相符」或「protocol 無法再觀測」才停在 rolled-back。
        final = (
            COMPONENT_STATUS_POSTCHECK_ROLLED_BACK
            if compensated and compensation["reobserved"] is not False
            else COMPONENT_STATUS_RECOVERY_REQUIRED
        )
        return _verdict(
            final, postcheck_reasons + reasons,
            component_effect_class=component_effect_class, row_abi=row_abi,
            mutation_performed=mutation_performed, driver_engaged=True,
            postcheck=postcheck, rollback=rollback,
            journal_entries=journal.entries, observed_subjects=observed_subjects,
        )
    try:
        journal.write("VERIFIED", post_state_digest, post_state_digest)
    except Exception as error:  # noqa: BLE001
        return _verdict(
            COMPONENT_STATUS_RECOVERY_REQUIRED,
            [f"terminal journal transition failed: {redact_driver_error(error)}"],
            component_effect_class=component_effect_class, row_abi=row_abi,
            mutation_performed=mutation_performed, driver_engaged=True, postcheck=postcheck,
            journal_entries=journal.entries,
        )
    rollback = _build_rollback(
        component_effect_class=component_effect_class, install_plan_digest=plan_digest,
        pre_state_digest=pre_state_digest, post_state_digest=post_state_digest,
        compensation=compensation_outcome(compensated=False, reobserved=None),
        ownership_aware=True, clock=clock, mutation_performed=False,
    )
    result = _build_result(
        component_effect_class=component_effect_class, install_plan_digest=plan_digest,
        status=status, applied_state_digest=applied_state_digest,
        postcheck_digest=postcheck["self_digest"], rollback_digest=rollback["self_digest"],
        pre_state_digest=pre_state_digest, post_state_digest=post_state_digest,
        evidence_class=evidence["recorded_evidence_class"],
        observed_at=str(driver.trusted_host_time()),
    )
    central_errors = (
        central_validator.validate_aiml_artifact(result)
        + central_validator.validate_aiml_artifact(postcheck)
        + central_validator.validate_aiml_artifact(rollback)
    )
    if central_errors:
        return _verdict(
            COMPONENT_STATUS_RECOVERY_REQUIRED, central_errors,
            component_effect_class=component_effect_class, row_abi=row_abi,
            mutation_performed=mutation_performed, driver_engaged=True,
            postcheck=postcheck, rollback=rollback, journal_entries=journal.entries,
        )
    return _verdict(
        status, list(reasons) + list(evidence["reasons"]),
        component_effect_class=component_effect_class, row_abi=row_abi,
        mutation_performed=mutation_performed, driver_engaged=True, result=result,
        postcheck=postcheck, rollback=rollback, journal_entries=journal.entries,
        observed_subjects=observed_subjects,
    )


def _compensating_failure(
    *,
    reason: str,
    component_effect_class: str,
    row_abi: dict[str, Any],
    plan_digest: str,
    pre_state_digest: str,
    post_state_digest: str,
    journal: _Journal,
    clock: Callable[[], datetime],
    compensate: Callable[[], Any],
) -> dict[str, Any]:
    """apply 中途失敗:ownership-aware 逆向補償;無法 exact 還原即 ``RECOVERY_REQUIRED``。"""

    compensation = normalize_compensation(compensate())
    rollback = _build_rollback(
        component_effect_class=component_effect_class, install_plan_digest=plan_digest,
        pre_state_digest=pre_state_digest, post_state_digest=post_state_digest,
        compensation=compensation, ownership_aware=True, clock=clock,
    )
    compensated = bool(compensation["compensated"])
    reobserved = compensation["reobserved"]
    try:
        journal.write(
            "COMPENSATED" if compensated else "FAILED", post_state_digest, pre_state_digest
        )
    except Exception as error:  # noqa: BLE001
        reason = f"{reason}; compensation journal failed: {redact_driver_error(error)}"
        compensated = False
    if not compensated:
        outcome_reason = "exact compensation was impossible; RECOVERY_REQUIRED blocks S2.5"
    elif reobserved is True:
        outcome_reason = (
            "the task-owned delta was compensated in reverse order and re-observed equal to the "
            "captured pre-state"
        )
    elif reobserved is False:
        outcome_reason = (
            "compensation ran without raising, but the post-compensation re-observation does not "
            "equal the captured pre-state; RECOVERY_REQUIRED blocks S2.5"
        )
    else:
        outcome_reason = (
            "the task-owned delta was compensated in reverse order, but this row's driver "
            "protocol could not re-observe it; exactness is not claimed"
        )
    return _verdict(
        COMPONENT_STATUS_FAILED if compensated and reobserved is not False
        else COMPONENT_STATUS_RECOVERY_REQUIRED,
        [reason, outcome_reason],
        component_effect_class=component_effect_class, row_abi=row_abi,
        mutation_performed=True, driver_engaged=True, rollback=rollback,
        journal_entries=journal.entries,
    )

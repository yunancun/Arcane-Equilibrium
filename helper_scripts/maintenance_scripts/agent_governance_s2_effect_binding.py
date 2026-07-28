"""S2E.1:六段 S2 effect DAG 的 closure effect-binding sibling(鏡 P0-B/target-host 家族)。

職責(PA 設計「Closure/rollback binding」節):

* ``validate_s2_effect_evidence`` —— 一份 closure evidence wrapper 的 receipt 級驗:
  receipt 的實際重算委派中央 AIML 閘
  ``aiml_gate_receipt_validator.validate_aiml_artifact``。**誠實界線(CC-C #1)**:中央閘
  對 ``pg_observer_bootstrap_result_v1`` / ``quiesce_result_v1`` /
  ``ingestion_compatibility_receipt_v1`` / ``s2_4_install_effect_receipt_v1`` 有語義委派
  或 self_digest 反偽造分支,但對 ``s2_4_capability_probe_effect_receipt_v1`` 與
  ``s2_4_prepare_effect_receipt_v1`` 今日**只有 closed-schema 結構驗**(無語義委派、
  不重算 self_digest);``s2_5_running_attestation_v1`` / ``s2_5_final_attestation_v1``
  亦無 schema_version 專屬分支。故三個 s2_4 step(W6A/W6B PROBE、W6A PREPARE)與兩個
  S2.5 step 在中央閘實得只有結構驗——本模組在同一縫補一次 self_digest 反偽造重算作為
  最低限度整合性,但這**不等同**語義委派:s2_4/s2_5 的語義門(permit 消耗、replay
  ledger、attestor、trusted-host time)仍全在 adapter 層,不在 closure。
  本模組另補 wrapper↔receipt 綁定、closure baseline head 綁定與 production 成功集判定
  ——``RECOVERY_REQUIRED`` / ``EXTERNAL_VERIFICATION_PENDING`` / source-simulation 頂點
  永不換算 closure PASS。
* ``validate_s2_effect_binding`` —— closure admission。**S2.0 與 S2.1 一律先委派(不是
  取代)既有 per-step closure 硬門**(``validate_pg_observer_bootstrap_binding`` /
  ``validate_quiesce_fence_binding``,見 ``_DELEGATED_STEP_BINDINGS``),其 errors 併入
  回傳;那兩個 predicate 提供本模組沒有的 operator authorization 對
  intent_id/intent_digest/source_head 精確綁定、receipt 內嵌 independent postcheck 的
  各自 validator 驗、``postcheck.verifier_node != receipt.apply_actor_node``、以及
  三方 digest 交叉核(receipt 內嵌 ``verifier_capture_digest`` == ops_postcheck evidence
  ``digest`` == 其內嵌 ``command_capture_v2.record_digest``,且 capture node_id ≠ applier)。
  本模組自身只做 S2 共通的 route⇔receipt⇔claim 綁定:route 有該 step 的 adapter 節點
  ⇔ 恰一 valid receipt;receipt 暴露的上游/permit digest 必等於 route claim admission;
  intent authority_ref cross-bind(鏡 effects.py 通用 deploy 同型;S2.2B 無 intent
  artifact,上游錨由 claim 綁定取代——唯一合法上游 = s2_5_final_attestation_v1);獨立
  ops_postcheck 必為 contract 白名單 kind、必晚於 effect 完成、acceptance 必同綁 receipt
  + postcheck。

⚠ SOURCE-TRUTH 邊界:route 層無法驗 head/freshness/permit 真偽是設計事實——閉合在
adapter(SSHSIG/attestor/replay-ledger)與 closure(out-of-band 信任主機驗證)層;本
模組乾淨 ``[]`` 「不」證任何 runtime 真的施加過。rollback 綁定不新造:各 adapter 的
rollback schema 已在 registry,route 節點 metadata 帶出 result/rollback schema version。
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import agent_governance_alr_quiesce_fence as quiesce_fence
import agent_governance_pg_observer_bootstrap as pg_observer
from agent_governance_routing import (
    S2_EFFECT_STEPS,
    _s2_effect_step,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"

# 固定 environment 標籤(鏡 target_host 常量先例):S2 效果面全綁 trade-core 的 AIML S2 DAG。
S2_EFFECT_ENVIRONMENT = "trade_core_aiml_s2"

S2_ADAPTER_IDS = frozenset(
    contract["adapter_id"] for contract in S2_EFFECT_STEPS.values()
)

# per-step receipt 契約。欄位語義:
#   receipt_schema_version / status_field / success_statuses —— 成功集只認可 closure-PASS 的
#       production/attested 語義;SOURCE_SIMULATION_PASS / SOURCE_REVALIDATION_PASS 是
#       source-lane 頂點,RECOVERY_REQUIRED / EXTERNAL_VERIFICATION_PENDING 是失敗頂點,
#       都不是 EFFECT 收據。
#   closure_pass_blocked_reason —— 非 None 時該 step 今日**無任何**可 closure-PASS 的 status
#       (success_statuses 必為空集),success 判定回 typed error 而非靜默通過;同時該 step
#       不要求 runtime_contact/CHANGED(無可達的成功頂點,要求它只會製造假語義)。
#   claim_receipt_bindings —— route claim admission ↔ receipt 頂層 digest 欄位(含 permit)。
#   declaration_only_claims —— 該 step 的 claim 在 receipt 內**確無**對應 digest 欄位可綁,
#       刻意只作 route 層宣告(其真偽閉合在 adapter 層 permit 消耗/replay ledger);由測試
#       釘「bindings ∪ declaration_only ∪ {selector} == route inventory」把空綁定釘成刻意。
#   postcheck_kind —— 獨立 ops_postcheck evidence 的 kind 白名單。
#   postcheck_receipt_binding —— postcheck payload 內必等於 receipt self_digest 的 dotted
#       欄位;None = 該 step 的三方交叉核由下方 _DELEGATED_STEP_BINDINGS 的既有硬門提供。
_OPS_POSTCHECK_KIND = "ops_postcheck_v1"
_OPS_POSTCHECK_RECEIPT_BINDING = "payload.effect_receipt_digest"
_CAPTURE_POSTCHECK_KIND = "command_capture_v2"


def _probe_contract(*, declaration_only_claims: frozenset[str]) -> dict[str, Any]:
    """W6A/W6B probe 共用 schema 但 claim inventory 不同 → 每次鑄一份獨立契約。

    (舊碼 ``dict(_PROBE_CONTRACT)`` 是淺拷貝,兩 step 會共享同一個
    ``claim_receipt_bindings`` dict;此 factory 讓兩 step 的可變子物件真正分離。)
    """

    return {
        "receipt_schema_version": "s2_4_capability_probe_effect_receipt_v1",
        "status_field": "terminal_status",
        "success_statuses": frozenset({"TERMINAL_CLEAN"}),
        "closure_pass_blocked_reason": None,
        "intent_schema_version": "s2_4_capability_probe_intent_v1",
        "intent_id_field": "probe_id",
        "intent_digest_field": "probe_core_digest",
        "started_field": "observed_at",
        "observed_field": "observed_at",
        "expiry_field": "expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {
            "s2_4_probe_authorization": "authorization_digest",
        },
        "declaration_only_claims": declaration_only_claims,
        "postcheck_kind": _OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    }


S2_STEP_RECEIPT_CONTRACTS: dict[str, dict[str, Any]] = {
    "S2_0_APPLY": {
        "receipt_schema_version": "pg_observer_bootstrap_result_v1",
        "status_field": "status",
        # 成功集**刻意不含** production ``APPLIED``:既有硬門
        # validate_pg_observer_bootstrap_binding 只認 APPLIED_ROLLED_BACK_EXACT(拋棄式
        # 邏輯證明),而把 production APPLIED 納入 closure PASS 需要「out-of-band
        # trusted-host 驗證 runtime apply 真的發生」,那是 S2.0 EFFECT session 的工作
        # (docs/execution_plan/ai_ml_landing/design/S2.4-W0a-authenticity-hardening.md
        # §「Genuinely EFFECT-only, out of W0a scope」)。封包自帶的收據無法認證自己被執行
        # (Typed Authority Matrix)。
        "success_statuses": frozenset({"APPLIED_ROLLED_BACK_EXACT"}),
        "closure_pass_blocked_reason": None,
        "intent_schema_version": "pg_observer_bootstrap_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        # operator authorization 是內嵌物件而非頂層 digest 欄位:其對 intent_id /
        # intent_digest / source_head 的精確綁定由委派的既有硬門
        # (operator_authorization_binding_errors)提供,不在本模組重複實作。
        "claim_receipt_bindings": {},
        "declaration_only_claims": frozenset({"s2_0_operator_authorization"}),
        "postcheck_kind": _CAPTURE_POSTCHECK_KIND,
        "postcheck_receipt_binding": None,
    },
    "S2_4_W6A_PROBE": _probe_contract(
        declaration_only_claims=frozenset({"s2_0_effect_receipt"}),
    ),
    "S2_4_W6A_PREPARE": {
        "receipt_schema_version": "s2_4_prepare_effect_receipt_v1",
        "status_field": "terminal_status",
        "success_statuses": frozenset({"PREPARED"}),
        "closure_pass_blocked_reason": None,
        "intent_schema_version": "s2_4_prepare_intent_v1",
        "intent_id_field": "prepare_id",
        "intent_digest_field": "prepare_core_digest",
        "started_field": "observed_at",
        "observed_field": "observed_at",
        "expiry_field": "expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {
            "s2_4_prepare_authorization": "authorization_digest",
        },
        "declaration_only_claims": frozenset({
            "s2_0_effect_receipt", "s2_4_prepare_sandbox_probe_receipt",
        }),
        "postcheck_kind": _OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    },
    "S2_4_W6B_PROBE": _probe_contract(
        declaration_only_claims=frozenset({
            "s2_0_effect_receipt", "s2_4_prepare_effect_receipt",
        }),
    ),
    "S2_4_W6B_APPLY": {
        "receipt_schema_version": "s2_4_install_effect_receipt_v1",
        "status_field": "status",
        "success_statuses": frozenset({"APPLIED_INACTIVE"}),
        "closure_pass_blocked_reason": None,
        "intent_schema_version": "s2_4_install_plan_v1",
        "intent_id_field": "plan_id",
        "intent_digest_field": "plan_core_digest",
        "started_field": "observed_at",
        "observed_field": "observed_at",
        "expiry_field": "expires_at",
        "host_field": "target_host",
        # receipt 頂層暴露的上游/permit digest 必等於 route claim admission。
        # prepare_result_digest 的真身是 **PREPARE effect receipt 的 self_digest**
        # (producer:agent_governance_s2_4_install_plan._aggregate_admission_verdict,
        # `verdict["prepare_result_digest"] = prepare_effect_receipt["self_digest"]`),
        # 不是 s2_4_prepared_install_bundle_v1 的 digest;claim key 因此命名為
        # s2_4_prepare_effect_receipt,與設計「上一步 terminal receipt digest = 下一 route
        # claim input」一致。雙 permit(registry s2_4_install_adapter_v1:aggregate + 窄
        # PG-migration profile)各自綁到 receipt 的對應 authorization digest 欄位。
        "claim_receipt_bindings": {
            "s2_4_install_authorization": "aggregate_authorization_digest",
            "s2_4_pg_migration_authorization": "pg_authorization_digest",
            "s2_4_prepare_effect_receipt": "prepare_result_digest",
            "s2_4_installed_unit_probe_receipt": "installed_unit_probe_receipt_digest",
        },
        "declaration_only_claims": frozenset({"s2_0_effect_receipt"}),
        "postcheck_kind": _OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    },
    "S2_5A_START": {
        "receipt_schema_version": "s2_5_running_attestation_v1",
        "status_field": "status",
        "success_statuses": frozenset({"RUNNING_ATTESTED"}),
        "closure_pass_blocked_reason": None,
        "intent_schema_version": "s2_5_start_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        # s2_5_running_attestation_v1 頂層無 permit / 上游 receipt digest 欄位
        # (s2_4_install_effect_receipt_digest 只存在於 s2_5_start_intent_v1 的
        # required_intent_fields);兩個 claim 皆 declaration-only,其消耗由 adapter 層驗。
        "claim_receipt_bindings": {},
        "declaration_only_claims": frozenset({
            "s2_5a_start_permit", "s2_4_install_effect_receipt",
        }),
        "postcheck_kind": _OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    },
    "S2_1_DRILL": {
        "receipt_schema_version": "quiesce_result_v1",
        "status_field": "status",
        # ── CC-B(normative_policy × implementation_contract 跨類 DRIFT,不由本模組單方換算)──
        # CC dissent 原文要點:``QUIESCED_STATIC_GUARDS_HELD`` 被 quiesce_result_v1.schema.json
        # 規定 ⇒ ``target_class=disposable_local`` 且 ``evidence_class=LOCAL_REPRODUCIBLE``,
        # 且該 schema 的 boundary 物件無條件 ``production_fence_performed: false``。把它放進
        # closure 成功集,等於在「明知未對 production 施加 fence」的收據上簽發 runtime_contact
        # PASS——那是把 disposable 模擬件換算成 EFFECT PASS。binding module 不得單方消解此
        # DRIFT。
        # 裁決(PM,方案 i):移除該 status,本 step 今日**無**可 closure-PASS 的成功頂點。
        "success_statuses": frozenset(),
        "closure_pass_blocked_reason": (
            "quiesce_result_v1 has no production/attested success status today "
            "(its evidence_class enum is only LOCAL_REPRODUCIBLE/STRUCTURAL_ONLY and its "
            "boundary is unconditionally production_fence_performed=false); "
            "QUIESCED_STATIC_GUARDS_HELD is a disposable_local logic proof and is never "
            "converted into a runtime_contact closure PASS. S2.1 closure PASS stays blocked "
            "until a later wave adds a production fence success status to that schema"
        ),
        "intent_schema_version": "quiesce_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {},
        "declaration_only_claims": frozenset({
            "s2_1_operator_authorization", "s2_0_effect_receipt",
            "s2_4_install_effect_receipt", "s2_5a_running_attestation",
        }),
        "postcheck_kind": _CAPTURE_POSTCHECK_KIND,
        "postcheck_receipt_binding": None,
    },
    "S2_5B_FINAL": {
        "receipt_schema_version": "s2_5_final_attestation_v1",
        "status_field": "status",
        "success_statuses": frozenset({"FINAL_ATTESTED"}),
        "closure_pass_blocked_reason": None,
        "intent_schema_version": "s2_5_start_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        # 命名非機械對應處錨定 registry:s2_5_final_attestation_adapter_v1 authority 明文
        # 「the exact S2.5A s2_5_running_attestation_v1 digest」= pre_drill_attestation_digest。
        "claim_receipt_bindings": {
            "s2_1_drill_receipt": "s2_1_drill_receipt_digest",
            "s2_5a_running_attestation": "pre_drill_attestation_digest",
        },
        "declaration_only_claims": frozenset({"s2_5b_final_permit"}),
        "postcheck_kind": _OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    },
    "S2_2B_RUNTIME_DONE": {
        "receipt_schema_version": "ingestion_compatibility_receipt_v1",
        "status_field": "status",
        "success_statuses": frozenset({"RUNTIME_COMPATIBILITY_ATTESTED"}),
        "closure_pass_blocked_reason": None,
        # identity-only:無 intent artifact(可執行 runtime observer/attestor 屬 S2E.4);
        # 上游錨由 claim 綁定取代——唯一合法上游 = s2_5_final_attestation_v1。
        "intent_schema_version": None,
        "started_field": "manifest_revalidation.observed_at",
        "observed_field": "manifest_revalidation.observed_at",
        "expiry_field": "manifest_revalidation.evidence_expires_at",
        "host_field": "s2_5_final_attestation.target_host",
        "claim_receipt_bindings": {
            "s2_5b_final_attestation": "s2_5_final_attestation_digest",
        },
        "declaration_only_claims": frozenset({"s2_2b_observation_authorization"}),
        "postcheck_kind": _OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    },
}
# CC-A:S2.0/S2.1 的既有 per-step closure 硬門——本模組**委派**,絕不取代。缺少它們時
# 本模組完全沒有:operator authorization 對 intent_id/intent_digest/source_head 的精確綁定、
# receipt 內嵌 independent postcheck 經各自 validator 驗、applier != verifier、三方 digest
# 交叉核(內嵌 verifier_capture_digest == ops_postcheck evidence digest ==
# command_capture_v2.record_digest 且 capture node ≠ applier)、以及 kind 白名單。
_DELEGATED_STEP_BINDINGS = {
    "S2_0_APPLY": pg_observer.validate_pg_observer_bootstrap_binding,
    "S2_1_DRILL": quiesce_fence.validate_quiesce_fence_binding,
}
S2_RECEIPT_SCHEMA_VERSIONS = frozenset(
    contract["receipt_schema_version"]
    for contract in S2_STEP_RECEIPT_CONTRACTS.values()
)
# 中央 AIML 閘今日**沒有** schema_version 專屬分支(=無語義委派、不重算 self_digest)的
# S2 receipt schema;由測試對中央閘原始碼釘住此清單,漂移即紅。
_CENTRAL_GATE_SELF_DIGEST_GAP_SCHEMAS = frozenset({
    "s2_4_capability_probe_effect_receipt_v1",
    "s2_4_prepare_effect_receipt_v1",
    "s2_5_running_attestation_v1",
    "s2_5_final_attestation_v1",
})


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def _get(payload: Any, dotted_field: str) -> Any:
    """按 dotted path 取欄位(S2.2B 的時間/host 欄位在巢狀物件內)。"""

    value = payload
    for part in dotted_field.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _receipt_validation_errors(receipt: dict[str, Any], *, now: Any) -> list[str]:
    """receipt 實際重算委派中央 AIML 閘(其內對部分 schema 再委派各 per-step SSOT 葉)。

    誠實界線(CC-C #1):中央閘只對部分 S2 schema 有語義委派/self_digest 反偽造分支;
    ``s2_4_capability_probe_effect_receipt_v1`` / ``s2_4_prepare_effect_receipt_v1`` /
    兩個 s2_5 attestation schema 今日只得 closed-schema 結構驗。此處對「中央閘不重算
    self_digest」的 schema 補一次 canonical 反偽造重算作為最低整合性——這**不是**語義
    委派,那些 step 的語義門仍在 adapter 層。

    測試可 monkeypatch 此縫作結構綁定測試;真委派由 sentinel 測試釘住。
    """

    if str(ML_TRAINING_DIR) not in sys.path:
        sys.path.insert(0, str(ML_TRAINING_DIR))
    import aiml_gate_receipt_validator as central_validator
    from aiml_gate_receipt_schema_core import artifact_self_digest

    errors = list(central_validator.validate_aiml_artifact(receipt, now=now))
    if errors:
        return errors
    if receipt.get("schema_version") in _CENTRAL_GATE_SELF_DIGEST_GAP_SCHEMAS and (
        receipt.get("self_digest") != artifact_self_digest(receipt)
    ):
        errors.append(
            "receipt self_digest does not bind the canonical receipt "
            "(the central AIML gate has no self_digest recompute for this schema)"
        )
    return errors


def s2_effect_step_for_receipt(receipt: Any) -> str | None:
    """由 receipt schema(probe 另按 scope)導出唯一 step;不可導出 → None(fail-closed)。"""

    if not isinstance(receipt, dict):
        return None
    schema_version = receipt.get("schema_version")
    candidates = [
        step for step, contract in S2_STEP_RECEIPT_CONTRACTS.items()
        if contract["receipt_schema_version"] == schema_version
    ]
    if len(candidates) == 1:
        return candidates[0]
    for step in candidates:
        if S2_EFFECT_STEPS[step].get("probe_scope") == receipt.get("probe_scope"):
            return step
    return None


def build_s2_effect_evidence(receipt: dict[str, Any]) -> dict[str, Any]:
    """把一份 S2 receipt 包進 closure evidence envelope(不改變身分)。

    ⚠ 今日**沒有 production caller**:真 evidence wrapper 由 S2 EFFECT session 的
    closure 產生器鑄造,本函式是 ``validate_s2_effect_evidence`` 的正例建構子/參照實作
    (測試用),故其輸出必須逐欄等於 validate 端要求的 wrapper 綁定。
    """

    step = s2_effect_step_for_receipt(receipt)
    if step is None:
        raise ValueError("S2 effect receipt step is not derivable")
    contract = S2_STEP_RECEIPT_CONTRACTS[step]
    adapter_id = S2_EFFECT_STEPS[step]["adapter_id"]
    return {
        "id": f"effect:{adapter_id}:{step}",
        "scope": "runtime",
        "kind": "effect_adapter_result_v1",
        "digest": receipt.get("self_digest"),
        "observed_at": _get(receipt, contract["observed_field"]),
        "expiry": _get(receipt, contract["expiry_field"]),
        "host": _get(receipt, contract["host_field"]),
        "environment": S2_EFFECT_ENVIRONMENT,
        "source": adapter_id,
        "receipt": receipt,
    }


def validate_s2_effect_evidence(
    evidence: dict[str, Any], *, expected_source_head: str
) -> tuple[list[str], dict[str, Any] | None]:
    """receipt 級驗 + wrapper↔receipt 綁定;成功集外的 status 永不進 valid_receipts。"""

    receipt = evidence.get("receipt")
    if not isinstance(receipt, dict):
        return ["S2 effect evidence missing canonical receipt payload"], None
    step = s2_effect_step_for_receipt(receipt)
    if step is None:
        return [
            "S2 effect receipt step is not derivable from schema_version/probe_scope"
        ], None
    contract = S2_STEP_RECEIPT_CONTRACTS[step]
    adapter_id = S2_EFFECT_STEPS[step]["adapter_id"]
    errors = [
        f"S2 {step} receipt invalid: {error}"
        for error in _receipt_validation_errors(
            receipt, now=_get(receipt, contract["observed_field"])
        )
    ]
    status = _get(receipt, contract["status_field"])
    blocked = contract["closure_pass_blocked_reason"]
    if blocked is not None:
        # CC-B:該 step 今日無任何可 closure-PASS 的 status;走到 success 判定必回 typed
        # error(絕不靜默把 disposable 模擬件換算成 EFFECT PASS)。
        errors.append(f"S2 {step} has no closure-admissible success status: {blocked}")
    elif status not in contract["success_statuses"]:
        # route admission 永遠不是 apply 授權:RECOVERY_REQUIRED /
        # EXTERNAL_VERIFICATION_PENDING / source-simulation 頂點在 closure 一律拒。
        errors.append(
            f"S2 {step} receipt status {status!r} is not a closure-admissible "
            "production success (RECOVERY_REQUIRED/EXTERNAL_VERIFICATION_PENDING/"
            "source-simulation never convert to PASS)"
        )
    if receipt.get("source_head") != expected_source_head:
        errors.append("S2 effect receipt source_head does not match closure baseline")
    if "adapter_id" in receipt and receipt.get("adapter_id") != adapter_id:
        errors.append("S2 effect receipt adapter_id does not match the step adapter")
    bindings = {
        "source": adapter_id,
        "digest": receipt.get("self_digest"),
        "host": _get(receipt, contract["host_field"]),
        "environment": S2_EFFECT_ENVIRONMENT,
        "observed_at": _get(receipt, contract["observed_field"]),
        "expiry": _get(receipt, contract["expiry_field"]),
        "kind": "effect_adapter_result_v1",
        "scope": "runtime",
    }
    for field, expected in bindings.items():
        if evidence.get(field) != expected:
            errors.append(f"S2 effect evidence {field} is not receipt-bound")
    return errors, receipt if not errors else None


def _delegated_binding_errors(
    step: str,
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """委派該 step 的既有 per-step closure 硬門(CC-A);無委派者回 []。

    這是**附加**閘不是替代閘:本模組只做 S2 共通的 route⇔receipt⇔claim 綁定,operator
    authorization 精確綁定 / 內嵌 postcheck validator / applier != verifier / 三方 digest
    交叉核一律由被委派的 predicate 執法。測試可 monkeypatch 此縫作結構綁定測試;真委派
    由 sentinel 與 typed 負例釘住。
    """

    delegate = _DELEGATED_STEP_BINDINGS.get(step)
    if delegate is None:
        return []
    return list(delegate(
        packet, route, fragments_by_node, evidence_by_id, valid_receipts,
    ))


def validate_s2_effect_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """closure admission:step 由 route claim admission 導出,絕不借通用 deploy 證據。"""

    try:
        step = _s2_effect_step(
            route.get("task_facts", {}).get("claim_inputs", {}) or {}
        )
    except ValueError as error:
        return [f"S2 closure route is invalid: {error}"]
    if step is None:
        return ["S2 closure route did not admit an S2 effect step"]
    contract = S2_STEP_RECEIPT_CONTRACTS[step]
    adapter_id = S2_EFFECT_STEPS[step]["adapter_id"]
    # CC-A:先跑既有 per-step closure 硬門(委派,不取代),其 errors 併入回傳。
    errors: list[str] = list(_delegated_binding_errors(
        step, packet, route, fragments_by_node, evidence_by_id, valid_receipts,
    ))
    blocked = contract["closure_pass_blocked_reason"]
    if blocked is not None:
        errors.append(f"S2 {step} has no closure-admissible success status: {blocked}")
    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    if len(effect_nodes) != 1 or effect_nodes[0].get("id") != adapter_id:
        errors.append(
            "S2 closure route did not select exactly the admitted step adapter node"
        )
    elif effect_nodes[0].get("effect_step") != step:
        errors.append("S2 closure route adapter node step differs from claim admission")

    # 恰一 valid receipt 屬本 step;任何其他 receipt(跨 step/未路由)一律拒收。
    matching: list[tuple[str, dict[str, Any]]] = []
    for evidence_id, receipt in valid_receipts.items():
        if s2_effect_step_for_receipt(receipt) == step:
            matching.append((evidence_id, receipt))
        else:
            errors.append(
                "S2 closure contains an effect receipt not routed to the admitted "
                f"step: {evidence_id}"
            )
    if len(matching) != 1:
        errors.append(f"S2 closure PASS requires exactly one {step} effect receipt")
        return errors
    receipt_id, receipt = matching[0]

    # claim↔receipt digest 綁定:receipt 暴露的上游 digest 必等於 route claim admission
    # (§1.2-corrected DAG 次序:上一步 terminal receipt digest = 本 route 的 claim input)。
    claims = route.get("task_facts", {}).get("claim_inputs", {}) or {}
    for claim_key, receipt_field in contract["claim_receipt_bindings"].items():
        if _get(receipt, receipt_field) != claims.get(claim_key):
            errors.append(
                f"S2 {step} receipt {receipt_field} is not claim-bound to {claim_key}"
            )

    # intent authority cross-bind(鏡 effects.py 通用 deploy 同型;receipt 無
    # intent_expires_at 欄位,TTL/expiry 真偽由 adapter 層 permit/replay-ledger 閉合)。
    if contract["intent_schema_version"] is not None:
        intent_source = (
            f"{contract['intent_schema_version']}:"
            f"{_get(receipt, contract['intent_id_field'])}"
        )
        intent_refs = [
            ref for ref in packet.get("authority_refs", [])
            if ref.get("class") == "claim_evidence"
            and ref.get("source") == intent_source
        ]
        if len(intent_refs) != 1 or intent_refs[0].get("digest") != _get(
            receipt, contract["intent_digest_field"]
        ):
            errors.append(f"S2 {step} effect receipt lacks exact intent authority")
        else:
            try:
                if _parse_time(
                    str(intent_refs[0].get("observed_at", ""))
                ) > _parse_time(str(_get(receipt, contract["started_field"]))):
                    errors.append(
                        f"S2 {step} intent authority was observed after effect start"
                    )
            except (TypeError, ValueError):
                errors.append(f"S2 {step} intent authority timestamp is invalid")

    # 獨立 ops_postcheck(applier != verifier):恰一 runtime postcheck evidence,kind 必在
    # contract 白名單、payload 必交叉綁 receipt self_digest(E2-P1-2;鏡 P0-B 的
    # operation_receipt cross-bind 與通用 deploy 的 effect_receipt_digest 綁定),晚於
    # effect 完成;acceptance 必同綁 receipt + postcheck(缺一即非 PASS)。
    # 註:S2.0/S2.1 的 postcheck_receipt_binding 為 None——那兩步的三方 digest 交叉核
    # (receipt 內嵌 verifier_capture_digest == evidence digest == command_capture_v2
    # record_digest,且 capture node ≠ applier)由上方委派的既有硬門提供。
    fragment = fragments_by_node.get("ops_postcheck", {})
    postchecks = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
        and evidence_by_id[ref].get("kind") == contract["postcheck_kind"]
    ]
    if len(postchecks) != 1:
        errors.append(
            "S2 closure requires exactly one independent ops_postcheck runtime evidence "
            f"of kind {contract['postcheck_kind']}"
        )
    else:
        postcheck = postchecks[0]
        receipt_binding = contract["postcheck_receipt_binding"]
        if receipt_binding is not None and _get(postcheck, receipt_binding) != (
            receipt.get("self_digest")
        ):
            errors.append(
                f"S2 ops_postcheck {receipt_binding} is not bound to the effect receipt "
                "self_digest"
            )
        try:
            if _parse_time(str(postcheck.get("observed_at", ""))) < _parse_time(
                str(_get(receipt, contract["observed_field"]))
            ):
                errors.append("S2 ops_postcheck predates the effect receipt completion")
        except (TypeError, ValueError):
            errors.append("S2 ops_postcheck timestamps are invalid")
        accepted = any(
            item.get("status") == "PASS"
            and {receipt_id, postcheck.get("id")}.issubset(
                set(item.get("evidence_refs", []))
            )
            for item in packet.get("acceptance", [])
        )
        if not accepted:
            errors.append(
                "S2 passed acceptance must bind the effect receipt and the "
                "independent ops_postcheck"
            )
    if blocked is None:
        # CC-B:closure PASS 被阻塞的 step 不得要求 runtime_contact/CHANGED——那會在無可達
        # 成功頂點的情況下逼出假的 runtime-contact 語義。
        if packet.get("side_effects", {}).get("runtime_contact") is not True:
            errors.append("S2 successful effect must record runtime_contact=true")
        if packet.get("disposition") != "CHANGED":
            errors.append("S2 successful effect closure disposition must be CHANGED")
    return errors

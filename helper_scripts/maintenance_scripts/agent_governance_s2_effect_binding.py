"""S2E.1:六段 S2 effect DAG 的 closure effect-binding sibling(鏡 P0-B/target-host 家族)。

職責(PA 設計「Closure/rollback binding」節):

* ``validate_s2_effect_evidence`` —— 一份 closure evidence wrapper 的 receipt 級驗:
  receipt 的實際重算委派中央 AIML 閘
  ``aiml_gate_receipt_validator.validate_aiml_artifact``。**誠實界線(CC-C)**:中央閘對
  ``pg_observer_bootstrap_result_v1`` / ``quiesce_result_v1`` /
  ``ingestion_compatibility_receipt_v1`` / ``s2_4_install_effect_receipt_v1`` 有頂層
  schema_version 分支,對 ``s2_5_running_attestation_v1`` / ``s2_5_final_attestation_v1``
  則以 ``startswith("s2_5_")`` **委派葉** ``aiml_gate_receipt_s2_5.validate_s2_5_artifact``
  ——葉內逐 schema 專屬分支,第一件事就是 self_digest 反偽造重算,另有 observer_gate、
  freshness、五 running dimension、precheck、attestor SSHSIG 驗簽(即兩個 s2_5 schema
  **不是**「只有結構驗」)。今日真正**沒有**任何分支(=無語義委派、不重算 self_digest)
  的只有 ``s2_4_capability_probe_effect_receipt_v1`` 與 ``s2_4_prepare_effect_receipt_v1``
  ——三個 s2_4 step(W6A/W6B PROBE、W6A PREPARE)在中央閘實得只有 closed-schema 結構驗,
  本模組在同一縫補一次 self_digest 反偽造重算作為最低限度整合性,但這**不等同**語義
  委派:s2_4 的語義門(permit 消耗、replay ledger、trusted-host time)仍在 adapter 層。
  本模組另補 wrapper↔receipt 綁定、closure baseline head 綁定與 production 成功集判定
  ——``RECOVERY_REQUIRED`` / ``EXTERNAL_VERIFICATION_PENDING`` / source-simulation 頂點
  永不換算 closure PASS。
* ``validate_s2_effect_binding`` —— closure admission。**四個 step 一律先委派(不是取代)
  既有 per-step closure 硬門**(見 ``_DELEGATED_STEP_BINDINGS``:S2.0
  ``validate_pg_observer_bootstrap_binding`` / S2.1 ``validate_quiesce_fence_binding`` /
  S2.5A 與 S2.5B 的 §6 ``aiml_gate_receipt_s2_5.validate_s2_5_attestation_binding``,後者
  經 ``_s2_5_attestation_binding_errors`` 適配),其 errors 併入回傳;那些 predicate 提供
  本模組沒有的 operator authorization / intent 精確綁定、OPS preflight fragment 語義、
  receipt 內嵌 independent postcheck 的各自 validator 驗、``verifier_node !=
  apply_actor_node``、以及三方 digest 交叉核(receipt 內嵌 ``verifier_capture_digest`` ==
  ops_postcheck capture evidence ``digest`` == 其內嵌 ``command_capture_v2.record_digest``,
  且 capture node_id ≠ applier)。
  本模組自身只做 S2 共通的 route⇔receipt⇔claim 綁定 **與 effect-DAG 傳遞性阻塞**
  (見下):route 有該 step 的 adapter 節點
  ⇔ 恰一 valid receipt;receipt 暴露的上游/permit digest 必等於 route claim admission;
  intent authority_ref cross-bind(鏡 effects.py 通用 deploy 同型;S2.2B 無 intent
  artifact,上游錨由 claim 綁定取代——唯一合法上游 = s2_5_final_attestation_v1);獨立
  ops_postcheck 必為 contract 白名單 kind、artifact 反偽造重算並交叉綁 receipt
  self_digest、必晚於 effect 完成、acceptance 必同綁 receipt + postcheck。

── effect-DAG 傳遞性阻塞(Codex-1;誠實後果:今日**九步全部**不可 closure-PASS)──────
``closure_pass_blocked_reason`` 原本只擋「該 step 自己」。但 S2 是一條 DAG,``S2_4_W6A_PROBE``
的 route claim inventory 帶著 ``s2_0_effect_receipt``——而 route 層只驗它「是一個合法 sha256
且與 receipt 欄位對得上」,contract 明標 declaration-only,``run_s2_4_capability_probe()`` 也
不收 S2.0 receipt/digest。於是一個 authorized W6A probe 可以在**沒有任何已驗證 S2.0 前置**的
情況下 closure-PASS,繞過已宣告的 effect DAG。處置:**任何 step 只要其 effect-DAG 傳遞上游
含一個帶 ``closure_pass_blocked_reason`` 的 step,該 step 自身亦不可 closure-PASS**(typed
error 明述阻塞鏈)。上游表不手抄——從既有 route claim inventory(``S2_CLAIM_KEYS_BY_STEP``)
導出,見 ``_UPSTREAM_RECEIPT_CLAIM_PRODUCERS``。

實務後果誠實記錄:S2.0 是全鏈的根且今日 blocked,S2.1 亦 blocked ⇒
**今日沒有任何一個 S2 step 能 closure PASS**(八步因 S2.0 傳遞性阻塞,S2.0 自身直接阻塞;
S2.5B/S2.2B 另加 S2.1 一條鏈)。這是正確的——S2 closure
lane 不該在根前置不可驗證時讓下游可 PASS。解除方式不是放寬本模組,而是各自 EFFECT session
的 out-of-band trusted-host 驗證讓 S2.0/S2.1 真的取得 production 成功頂點。

route admission 側的新規則(NEW-P2-C,實作在 ``agent_governance_routing`` 的 S2 selector
分支):**S2 effect lane 一律強制 ``authority`` 表面**——各 side_effect_class 的 FORWARD
規則只要求 pg|runtime_effect|service(+install 另需 secret),沒有這條硬性要求,W6B APPLY
(裝 unit + PG migration)與 S2.5A(起 production service)會在**無 constitutional gate**
的 DAG 下 admitted。缺 authority 面 ⇒ typed ValueError(鏡 P0-B effect lane 的同型要求)。

📎 registry invariant 讀法(NEW-P2-F;PM 已裁 registry 字串不改):九條 S2 adapter invariant
寫「no route_task effect node or closure effect binding is injected **before** the S2.x EFFECT
session」,而 route 今日確實會注入 effect 節點——兩者不矛盾,因為
**S2 effect selector claim admission 就是該 adapter 的 EFFECT session 開始**(那是「EFFECT
session」在 route 層唯一的機器定義,見 ``agent_governance_routing`` 的 S2 selector 分支)。
invariant 禁止的是 admission **之前**的注入,而 source lane(selector 缺席)零 effect 節點
注入正是它。故「釘 invariant 字串」與「斷言 admission 後有注入」兩組測試同時為真。

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
    S2_CLAIM_KEYS_BY_STEP,
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
#       ── S2.0 與 S2.1 的處置對稱性(CC-A1 裁決,方案 i;CC 指「不對稱且無記錄」)──
#       兩步同一條理由、同一種處置:各自 result schema 今日唯一可達的「成功」status
#       (S2.0 = APPLIED_ROLLED_BACK_EXACT / S2.1 = QUIESCED_STATIC_GUARDS_HELD)都被自己的
#       schema 釘死成 target_class=disposable_local + evidence_class=LOCAL_REPRODUCIBLE,
#       且 boundary 明文 production_apply_performed / production_fence_performed = false
#       ——那是拋棄式邏輯證明,不得被本模組單方換算成 production DAG 步驟的
#       runtime_contact=true / disposition=CHANGED。真 production 頂點(S2.0 的 APPLIED /
#       S2.1 的未來 production fence status)都需要各自 EFFECT session 的 out-of-band
#       trusted-host 驗證,本波不可達。故兩步一律 success_statuses=frozenset() +
#       closure_pass_blocked_reason,而非「收窄成功集」——收窄仍會讓一份拋棄式收據換到
#       EFFECT_DONE。另見兩步 postcheck_kind 註(其 command_capture_v2 runtime 形狀今日在
#       closure_packet_v1 亦不可表示,與本處置同向)。
#   effect_dag_upstream_steps —— 該 step 的 effect-DAG **傳遞**上游 step 集合(Codex-1);
#       由下方 ``_UPSTREAM_RECEIPT_CLAIM_PRODUCERS`` × route claim inventory 導出後回填,
#       **不在字面表內手抄**。上游若有任一 blocked step,本 step 亦不可 closure-PASS。
#   claim_receipt_bindings —— route claim admission ↔ receipt 頂層 digest 欄位(含 permit)。
#   declaration_only_claims —— 該 step 的 claim 在 receipt 內**確無**對應 digest 欄位可綁,
#       刻意只作 route 層宣告(其真偽閉合在 adapter 層 permit 消耗/replay ledger);由測試
#       釘「bindings ∪ declaration_only ∪ {selector} == route inventory」把空綁定釘成刻意。
#   postcheck_kind —— 獨立 ops_postcheck evidence 的 kind 白名單。
#   postcheck_receipt_binding —— postcheck 內必等於 receipt self_digest 的 dotted 欄位;
#       None = 該 step 的三方交叉核由下方 _DELEGATED_STEP_BINDINGS 的既有硬門提供。
#
# ── NEW-P1-A:evidence 形狀必須在 closure_packet_v1 真的可表示 ──────────────────────
# `.codex/schemas/closure_packet_v1.schema.json` 的 `$defs/evidence` 是 additionalProperties:
# false 且**沒有** `payload` 欄位;`kind == "ops_postcheck_v1"` 另被強制 `operation_receipt`
# 且該物件只能是 `opsDeployPostcheck`(adapter_id const deploy_adapter_v1)或 `opsP0bPostcheck`
# (const p0b_alr_rollforward_adapter_v1)——兩者都不是 S2 adapter。舊碼的
# `payload.effect_receipt_digest` 因此在任何 schema-valid 封包上恆為 None(fail-closed 但
# 功能性倒退:整條 S2 closure PASS 路徑不可滿足)。
# 修法採可表示的先例 S1.6B target-host(`agent_governance_target_host_effects`:自訂 kind +
# schema 允許的 `artifact` + `artifact.self_digest` ↔ wrapper `digest`):S2 用自己的
# `s2_effect_ops_postcheck_v1` kind,綁定改走 `artifact.effect_receipt_digest`,零 registry
# schema 改動(自訂 kind 不落在 evidence 的任何 kind-條件臂,只受 runtime scope 的
# host/environment/observed_at/expiry 要求)。參照建構子 = build_s2_effect_ops_postcheck_evidence,
# 由測試以真驗證器 `agent_governance_schema.schema_subset_errors` 釘住 schema-valid。
#
# ⚠ 已知且刻意保留的 evidence 形狀限制(S2.0 / S2.1):那兩步的既有硬門
# (validate_pg_observer_bootstrap_binding / validate_quiesce_fence_binding)要求 ops_postcheck
# fragment 內恰一 `kind == "command_capture_v2"` 且 `scope == "runtime"` 的 evidence,而
# closure_packet_v1 對 `command_capture_v2` 釘死 `scope: const "test"` ⇒ 該形狀今日在封包裡
# **不可表示**。本波不改那兩個既有 predicate 的語義(其測試為既有面),亦不放寬 registry
# schema 的 command_capture_v2 scope const;此限制與 CC-A1/CC-B 的處置同向且無實害——S2.0 與
# S2.1 今日皆為 closure_pass_blocked_reason step(無可達成功頂點),不可表示的 evidence 形狀
# 只影響一個本來就不可能發生的 PASS。真 EFFECT session 要解此結,須另立 S2 專屬 capture kind
# (鏡 target_host_verifier_command_capture_v2)或修 registry schema,屬 S2E 後續波。
S2_OPS_POSTCHECK_KIND = "s2_effect_ops_postcheck_v1"
# ── Codex-2 / E2-RES-3:獨立 postcheck 的**確切 bytes** 必經 out-of-band host verifier ──
# 本模組(與委派的 §6 硬門)對這份 artifact 只做 caller 可控的 canonical self-digest 重算 +
# 自報 ``status == PASS``;OPS fragment 也只綁它的 evidence ID。故拿到真 effect receipt 後,
# 封包產生者可以用**同一個 evidence ID** 換上一份新鮮自封的 PASS postcheck,宣稱獨立運維驗證
# 跑過(含 W6B 安裝與 PG migration 之後)——self_digest 只證「這份內容沒被改過」,永不證
# 「誰產生了它 / 它真的跑過」(CLAUDE Typed Authority Matrix)。修法:把這個 kind 掛進
# closure 的 execution-attestation 候選枚舉(closure 端收集,
# agent_governance_execution_attestation 端認證),與 effect receipt 同樣必須被 host verifier
# 認證,否則 closure 不得 PASS。
# ⚠ 誠實殘留:今日的 S0.3/S1 signed-bundle verifier
# (agent_governance_aiml_trusted_host.ALLOWED_EXECUTION_KINDS)不含本 kind ⇒ 該 verifier 認證
# 不了它。這是 fail-closed 方向(等同「S2 lane 今日不可 PASS」的其他理由),不是靜默放行;
# 要讓真 S2 EFFECT session 可 PASS,須另行(經審)擴充該 verifier 表面,不由本波單方放寬。
S2_CLOSURE_ATTESTED_POSTCHECK_KINDS = frozenset({S2_OPS_POSTCHECK_KIND})
_OPS_POSTCHECK_RECEIPT_BINDING = "artifact.effect_receipt_digest"
_CAPTURE_POSTCHECK_KIND = "command_capture_v2"
# ── NEW-P3-H:postcheck artifact 的 exact field set(先例 target_host POSTCHECK_FIELDS)──
# 沒有這條時,一份 ``{schema_version, effect_receipt_digest, <任意鍵>, self_digest}`` 的手搓
# artifact 就能過關——self_digest 只證「這份內容沒被改過」,不證「這份內容是一份 postcheck」;
# 且 effect_step/source_head/host/observed_at 可填任意值 = 死欄位。本集合同時是參照建構子
# ``build_s2_effect_ops_postcheck_evidence`` 的輸出欄位集(由測試釘兩端等值,漂移即紅)。
_S2_OPS_POSTCHECK_ARTIFACT_FIELDS = frozenset({
    "schema_version", "status", "effect_step", "effect_receipt_digest",
    "verifier_node", "source_head", "host", "observed_at", "self_digest",
})
# NEW-P1-B:獨立 postcheck 唯一可背書 closure 的自報結論(先例明文 `status must be PASS`)。
_S2_OPS_POSTCHECK_PASS_STATUS = "PASS"

# CC-A2:S2.5A/S2.5B 委派 §6 attestation binding 所需的三個載體(同樣只用 closure_packet_v1
# 真有的欄位:evidence.artifact 與 role_fragment.payload;OPS fragment 的 payload_kind 由
# registry 釘成 operation_review_fragment_v1,故 preflight artifact 掛在 payload 的具名鍵下)。
S2_5_INTENT_EVIDENCE_KIND = "s2_5_start_intent_v1"
S2_5_VERIFIER_CAPTURE_KIND = "s2_effect_verifier_command_capture_v2"
S2_5_OPS_PREFLIGHT_PAYLOAD_KEY = "s2_5_ops_preflight"


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
        "postcheck_kind": S2_OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    }


S2_STEP_RECEIPT_CONTRACTS: dict[str, dict[str, Any]] = {
    "S2_0_APPLY": {
        "receipt_schema_version": "pg_observer_bootstrap_result_v1",
        "status_field": "status",
        # ── CC-A1(與 S2.1/CC-B 同型的跨類 DRIFT,不由本模組單方換算)──
        # 舊碼把成功集收窄成 {APPLIED_ROLLED_BACK_EXACT} 仍重演同一缺陷:
        # pg_observer_bootstrap_result_v1.schema.json 規定該 status ⇒
        # target_class const disposable_local + evidence_class const LOCAL_REPRODUCIBLE,
        # 且 status != APPLIED 的 else 臂 ⇒ boundary.production_apply_performed const false。
        # 而本模組對成功 step 強制 runtime_contact=true + disposition=CHANGED、wrapper 另蓋
        # environment=trade_core_aiml_s2——一份拋棄式收據於是可讓 DAG 全鏈前置的 S2.0 記成
        # EFFECT_DONE。裁決(PM,方案 i,與 S2.1 對稱):本 step 今日**無**可 closure-PASS
        # 的成功頂點。
        "success_statuses": frozenset(),
        "closure_pass_blocked_reason": (
            "pg_observer_bootstrap_result_v1 has no closure-admissible production success "
            "status today: APPLIED_ROLLED_BACK_EXACT is schema-pinned to "
            "target_class=disposable_local / evidence_class=LOCAL_REPRODUCIBLE and its "
            "boundary is production_apply_performed=false (the schema's non-APPLIED else "
            "arm), so it is a throwaway logic proof and is never converted into the "
            "runtime_contact/CHANGED semantics of a production DAG step; a production "
            "APPLIED needs the out-of-band trusted-host verification that the runtime "
            "apply actually happened, which is S2.0 EFFECT-session work "
            "(design/S2.4-W0a-authenticity-hardening.md, 'Genuinely EFFECT-only, out of "
            "W0a scope') and is unreachable in this wave"
        ),
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
        "postcheck_kind": S2_OPS_POSTCHECK_KIND,
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
        # E2-P2(記錄用):receipt 另有 ``prepare_sandbox_probe_receipt_digest`` /
        # ``prepare_postcheck_digest`` 兩個上游 digest 欄位,但 W6B APPLY 的 route claim
        # inventory **刻意沒有**對應 claim key——PREPARE_SANDBOX probe 是 W6A 那一步的
        # claim,到 W6B APPLY 時其真偽已由 adapter 層透過 prepare_result_digest(= PREPARE
        # effect receipt 的 self_digest)遞移閉合;在 route 層再要求一次只會製造重複宣告。
        "claim_receipt_bindings": {
            "s2_4_install_authorization": "aggregate_authorization_digest",
            "s2_4_pg_migration_authorization": "pg_authorization_digest",
            "s2_4_prepare_effect_receipt": "prepare_result_digest",
            "s2_4_installed_unit_probe_receipt": "installed_unit_probe_receipt_digest",
        },
        "declaration_only_claims": frozenset({"s2_0_effect_receipt"}),
        "postcheck_kind": S2_OPS_POSTCHECK_KIND,
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
        # CC-A2:本 step 的硬門不止於此——委派的 §6 attestation binding 另要求 intent
        # 載體、OPS preflight fragment(unit_inactive_confirmed 必為 true)與 verifier
        # capture 三方核(record_digest 重算 + capture node != apply_actor_node)。
        "claim_receipt_bindings": {},
        "declaration_only_claims": frozenset({
            "s2_5a_start_permit", "s2_4_install_effect_receipt",
        }),
        "postcheck_kind": S2_OPS_POSTCHECK_KIND,
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
        "postcheck_kind": S2_OPS_POSTCHECK_KIND,
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
        "postcheck_kind": S2_OPS_POSTCHECK_KIND,
        "postcheck_receipt_binding": _OPS_POSTCHECK_RECEIPT_BINDING,
    },
}

# ── Codex-1:effect-DAG 傳遞性阻塞的上游表 ─────────────────────────────────────────
# 每個「上游收據/認證」claim key ↔ 產出該收據的 step。claim key 命名本身就編碼了
# §1.2-corrected DAG 次序(「上一步 terminal receipt digest = 下一 route 的 claim input」,
# 見 agent_governance_routing.S2_CLAIM_KEYS_BY_STEP 註),故 per-step 的上游集合一律**從既有
# route claim inventory 導出**而非在契約表手抄:route 增刪一個上游 claim,本表自動跟隨。
# 其餘 claim key 都是 authorization/permit(非上游 step 產物),由測試以
# 「`_receipt`/`_attestation` 尾碼 ⇔ 在本表內」的封閉集守衛釘住,新 claim key 未分類即紅。
_UPSTREAM_RECEIPT_CLAIM_PRODUCERS: dict[str, str] = {
    "s2_0_effect_receipt": "S2_0_APPLY",
    "s2_4_prepare_sandbox_probe_receipt": "S2_4_W6A_PROBE",
    "s2_4_prepare_effect_receipt": "S2_4_W6A_PREPARE",
    "s2_4_installed_unit_probe_receipt": "S2_4_W6B_PROBE",
    "s2_4_install_effect_receipt": "S2_4_W6B_APPLY",
    "s2_5a_running_attestation": "S2_5A_START",
    "s2_1_drill_receipt": "S2_1_DRILL",
    "s2_5b_final_attestation": "S2_5B_FINAL",
}


def _direct_upstream_steps(step: str) -> set[str]:
    """該 step 的**直接**上游 step(= 其 route claim inventory 內的上游收據 claim 的產出者)。"""

    return {
        _UPSTREAM_RECEIPT_CLAIM_PRODUCERS[claim_key]
        for claim_key in S2_CLAIM_KEYS_BY_STEP[step]
        if claim_key in _UPSTREAM_RECEIPT_CLAIM_PRODUCERS
    }


def _transitive_upstream_steps(step: str) -> frozenset[str]:
    """傳遞閉包;visited 集讓 claim inventory 萬一成環也只是收斂,不會無限遞迴。"""

    seen: set[str] = set()
    pending = list(_direct_upstream_steps(step))
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(_direct_upstream_steps(current))
    return frozenset(seen)


S2_EFFECT_DAG_UPSTREAM_STEPS: dict[str, frozenset[str]] = {
    step: _transitive_upstream_steps(step) for step in S2_STEP_RECEIPT_CONTRACTS
}
for _step, _upstream_steps in S2_EFFECT_DAG_UPSTREAM_STEPS.items():
    S2_STEP_RECEIPT_CONTRACTS[_step]["effect_dag_upstream_steps"] = _upstream_steps


def s2_closure_block_errors(step: str) -> list[str]:
    """該 step 今日**不可 closure-PASS** 的全部 typed 理由(自身 + effect-DAG 傳遞上游)。

    自身面 = 既有 ``closure_pass_blocked_reason``(CC-A1/CC-B:成功集為空,disposable 模擬件
    永不換算 EFFECT PASS)。傳遞面(Codex-1)= 上游任一 step 被阻塞時,本 step 也不可 PASS
    ——route 對上游 receipt claim 只驗「是合法 sha256」,adapter 亦不收上游 receipt,故沒有這
    條時一個 authorized W6A probe 能在零已驗證 S2.0 前置下 closure-PASS,繞過已宣告的 DAG。

    誠實後果:S2.0 是全鏈的根且今日 blocked ⇒ 今日**九步全部**回非空列表(= 零步可 PASS)。
    遍歷序取契約表宣告序(= DAG 次序),讓阻塞鏈的輸出穩定可比。
    """

    errors: list[str] = []
    blocked = S2_STEP_RECEIPT_CONTRACTS[step]["closure_pass_blocked_reason"]
    if blocked is not None:
        errors.append(f"S2 {step} has no closure-admissible success status: {blocked}")
    upstream_steps = S2_STEP_RECEIPT_CONTRACTS[step]["effect_dag_upstream_steps"]
    for upstream in S2_STEP_RECEIPT_CONTRACTS:
        if upstream == step or upstream not in upstream_steps:
            continue
        reason = S2_STEP_RECEIPT_CONTRACTS[upstream]["closure_pass_blocked_reason"]
        if reason is not None:
            errors.append(
                f"S2 {step} cannot reach a closure PASS: its effect-DAG upstream "
                f"{upstream} is blocked ({reason})"
            )
    return errors


S2_RECEIPT_SCHEMA_VERSIONS = frozenset(
    contract["receipt_schema_version"]
    for contract in S2_STEP_RECEIPT_CONTRACTS.values()
)
# 中央 AIML 閘今日**沒有** schema_version 專屬分支(=無語義委派、不重算 self_digest)的
# S2 receipt schema;由測試對中央閘**與其委派葉**的原始碼釘住此清單,漂移即紅。
# CC-C:兩個 s2_5 attestation schema 曾被誤列於此——中央閘以 startswith("s2_5_") 委派
# aiml_gate_receipt_s2_5.validate_s2_5_artifact,葉內對兩者各有專屬分支且第一件事就是
# self_digest 反偽造重算(另有 observer_gate/freshness/五 dimension/precheck/attestor SSHSIG
# 驗簽)。清單因此只剩真正無分支的兩個 s2_4 schema。
_CENTRAL_GATE_SELF_DIGEST_GAP_SCHEMAS = frozenset({
    "s2_4_capability_probe_effect_receipt_v1",
    "s2_4_prepare_effect_receipt_v1",
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


def _artifact_self_digest(artifact: dict[str, Any]) -> str:
    """canonical self-digest(排除 ``self_digest`` 本身);與收據家族用同一把尺。"""

    if str(ML_TRAINING_DIR) not in sys.path:
        sys.path.insert(0, str(ML_TRAINING_DIR))
    from aiml_gate_receipt_schema_core import artifact_self_digest

    return artifact_self_digest(artifact)


def _receipt_validation_errors(receipt: dict[str, Any], *, now: Any) -> list[str]:
    """receipt 實際重算委派中央 AIML 閘(其內對部分 schema 再委派各 per-step SSOT 葉)。

    誠實界線(CC-C):中央閘對部分 S2 schema 有頂層分支、對 ``s2_5_*`` 以 startswith 委派
    葉(葉內逐 schema 分支且重算 self_digest);今日只有
    ``s2_4_capability_probe_effect_receipt_v1`` / ``s2_4_prepare_effect_receipt_v1`` 完全
    沒有分支,只得 closed-schema 結構驗。此處對這兩個 schema 補一次 canonical 反偽造重算
    作為最低整合性——這**不是**語義委派,那兩步的語義門仍在 adapter 層。

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


def build_s2_effect_ops_postcheck_evidence(
    receipt: dict[str, Any],
    *,
    verifier_node: str,
    observed_at: str,
    evidence_id: str = "s2-effect-ops-postcheck",
) -> dict[str, Any]:
    """獨立 ops_postcheck 的參照建構子(NEW-P1-A;鏡 build_target_host_closure_evidence)。

    產出 **closure_packet_v1 可表示** 的 runtime evidence:自訂 kind
    ``s2_effect_ops_postcheck_v1`` + schema 允許的 ``artifact``,``artifact.self_digest``
    ↔ wrapper ``digest``,``artifact.effect_receipt_digest`` ↔ effect receipt self_digest。
    與 ``build_s2_effect_evidence`` 同樣今日無 production caller(真封包由 S2 EFFECT
    session 鑄造),存在的意義是讓 validate 端要求的形狀有一份可被真 schema 驗證器檢查的
    正本。S2.0/S2.1 的 postcheck 走既有硬門要求的 runtime ``command_capture_v2`` 形狀,
    今日不可表示(見契約表註),此處 typed 拒絕而不偽造一個 S2 形狀。
    """

    step = s2_effect_step_for_receipt(receipt)
    if step is None:
        raise ValueError("S2 effect receipt step is not derivable")
    contract = S2_STEP_RECEIPT_CONTRACTS[step]
    if contract["postcheck_receipt_binding"] is None:
        raise ValueError(
            f"S2 {step} independent postcheck is the delegated hard gate's runtime "
            "command_capture_v2 shape, which closure_packet_v1 pins to scope=test; it "
            "is not representable today and is never rebuilt as an S2 postcheck artifact"
        )
    artifact = {
        "schema_version": S2_OPS_POSTCHECK_KIND,
        "status": "PASS",
        "effect_step": step,
        "effect_receipt_digest": receipt.get("self_digest"),
        "verifier_node": verifier_node,
        "source_head": receipt.get("source_head"),
        "host": _get(receipt, contract["host_field"]),
        "observed_at": observed_at,
    }
    artifact["self_digest"] = _artifact_self_digest(artifact)
    return {
        "id": evidence_id,
        "scope": "runtime",
        "kind": S2_OPS_POSTCHECK_KIND,
        "digest": artifact["self_digest"],
        "observed_at": observed_at,
        "expiry": _get(receipt, contract["expiry_field"]),
        "host": _get(receipt, contract["host_field"]),
        "environment": S2_EFFECT_ENVIRONMENT,
        "source": "ops_postcheck",
        "artifact": artifact,
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
        # 誠實界線(Codex-1):本函式是**收據級**驗,只執法「這份收據自己」的可 closure-PASS
        # 性;effect-DAG 傳遞性阻塞屬 closure admission(它要 route 的 claim admission 才
        # 知道 DAG 位置),一律在 validate_s2_effect_binding 執法。一份 W6A probe 收據本身
        # 可以完全合法 —— 不可 PASS 的是「在未驗證 S2.0 前置下的那個 closure」,把它記成
        # 「收據無效」會是假陳述。無旁路風險:closure 對任何 S2 receipt 必經
        # validate_s2_effect_binding(route 無該 adapter 節點時通用分支以 unrouted 拒收)。
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


def _s2_5_attestation_binding_errors(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """CC-A2:S2.5A/S2.5B 委派既有 §6 硬門(``validate_s2_5_attestation_binding``)的適配層。

    該 predicate 的呼叫形狀是 ``intent × ops_preflight × receipt × verifier_capture``,不是
    closure 的五參數形狀,故此處負責從封包取出三個載體再轉譯其 verdict:

    * intent —— 恰一 ``s2_5_start_intent_v1`` kind 的 evidence,``digest`` 必等於內嵌
      artifact 的 ``self_digest``(否則 wrapper 可指向一份與 artifact 無關的 intent)。
    * ops_preflight —— OPS ``ops_preflight`` fragment 的 ``payload`` 具名鍵(fragment 的
      payload_kind 由 registry 釘死 operation_review_fragment_v1,故不能整個換掉)。
    * verifier_capture —— ops_postcheck fragment 內、kind ``s2_effect_verifier_command_capture_v2``
      的 runtime evidence,``digest`` 必等於內嵌 record 的 ``record_digest``;缺席時傳 None,
      由 §6 自己走 typed 分支(receipt 帶 verifier_capture_digest 而 capture 缺席 = 單側主張,
      §6 判 REJECTED;兩側皆缺 = EXTERNAL_VERIFICATION_PENDING)。

    ``now``(NEW-P2-G)—— **必取自封包的 ``adjudicated_at``,不得取自收據自報時刻**。舊碼傳
    ``receipt["completed_at"]``,而 ``completed_at`` 與 ``evidence_expires_at`` 同在該收據內、
    同一方(被驗方)控制 ⇒ §6 的新鮮度面結構性恆過(被驗方永遠能自報一個早於自己 expiry 的
    完成時刻)。``adjudicated_at`` 是 ``closure_packet_v1`` 的 required 頂層欄位、屬驗方時鐘;
    缺席或不可解析 ⇒ typed error 且 ``now`` 傳 None,由葉自己 fail-closed(葉對 None 直接回
    「requires now for freshness」)。

    只有 ``S2_5_ATTESTATION_BINDING_VERIFIED`` 才是零錯誤;``EXTERNAL_VERIFICATION_PENDING``
    與 ``..._REJECTED`` 一律換算成 typed closure error(PENDING 永不是 PASS)。
    """

    if str(ML_TRAINING_DIR) not in sys.path:
        sys.path.insert(0, str(ML_TRAINING_DIR))
    import aiml_gate_receipt_s2_5 as s2_5_leaf

    errors: list[str] = []
    receipts = [
        receipt for receipt in valid_receipts.values()
        if isinstance(receipt, dict)
        and str(receipt.get("schema_version", "")).startswith("s2_5_")
    ]
    if len(receipts) != 1:
        return [
            "S2.5 attestation binding requires exactly one s2_5 attestation receipt"
        ]
    receipt = receipts[0]

    intent: dict[str, Any] | None = None
    intent_evidence = [
        evidence for evidence in evidence_by_id.values()
        if isinstance(evidence, dict)
        and evidence.get("kind") == S2_5_INTENT_EVIDENCE_KIND
    ]
    if len(intent_evidence) != 1:
        errors.append(
            "S2.5 attestation binding requires exactly one "
            f"{S2_5_INTENT_EVIDENCE_KIND} evidence carrying the canonical start intent"
        )
    else:
        candidate = intent_evidence[0].get("artifact")
        if not isinstance(candidate, dict) or intent_evidence[0].get("digest") != (
            candidate.get("self_digest")
        ):
            errors.append(
                "S2.5 attestation binding intent evidence digest is not bound to the "
                "embedded start intent self_digest"
            )
        if isinstance(candidate, dict):
            intent = candidate

    preflight_payload = (
        fragments_by_node.get("ops_preflight", {}) or {}
    ).get("payload") or {}
    ops_preflight = preflight_payload.get(S2_5_OPS_PREFLIGHT_PAYLOAD_KEY)
    if not isinstance(ops_preflight, dict):
        errors.append(
            "S2.5 attestation binding requires the OPS preflight fragment payload key "
            f"{S2_5_OPS_PREFLIGHT_PAYLOAD_KEY}"
        )
        ops_preflight = None

    verifier_capture: dict[str, Any] | None = None
    fragment = fragments_by_node.get("ops_postcheck", {}) or {}
    capture_evidence = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
        and evidence_by_id[ref].get("kind") == S2_5_VERIFIER_CAPTURE_KIND
    ]
    if len(capture_evidence) > 1:
        errors.append(
            "S2.5 attestation binding requires at most one "
            f"{S2_5_VERIFIER_CAPTURE_KIND} evidence in the ops_postcheck fragment"
        )
    elif capture_evidence:
        record = capture_evidence[0].get("artifact")
        if not isinstance(record, dict) or capture_evidence[0].get("digest") != (
            record.get("record_digest")
        ):
            errors.append(
                "S2.5 attestation binding verifier capture evidence digest is not bound "
                "to the embedded command_capture_v2 record_digest"
            )
        if isinstance(record, dict):
            verifier_capture = record

    # NEW-P2-G:新鮮度時鐘取驗方(closure 裁決時刻),絕不取被驗方自報的 completed_at。
    adjudicated_at = packet.get("adjudicated_at") if isinstance(packet, dict) else None
    try:
        _parse_time(str(adjudicated_at))
    except (TypeError, ValueError):
        errors.append(
            "S2.5 attestation binding requires a parseable closure packet "
            "adjudicated_at as the §6 freshness clock (the receipt's own completed_at "
            "is verified-party time and would make the expiry face vacuously true)"
        )
        adjudicated_at = None

    verdict = s2_5_leaf.validate_s2_5_attestation_binding(
        intent=intent,
        ops_preflight=ops_preflight,
        receipt=receipt,
        verifier_capture=verifier_capture,
        now=adjudicated_at,
    )
    if verdict.get("status") != s2_5_leaf.S2_5_BINDING_VERIFIED:
        errors.append(
            "S2.5 §6 attestation binding is not VERIFIED "
            f"({verdict.get('status')}): "
            + "; ".join(str(reason) for reason in verdict.get("reasons", []))
        )
    return errors


# CC-A:四個 step 的既有 per-step closure 硬門——本模組**委派**,絕不取代。缺少它們時
# 本模組完全沒有:operator authorization 對 intent_id/intent_digest/source_head 的精確綁定、
# receipt 內嵌 independent postcheck 經各自 validator 驗、applier != verifier、三方 digest
# 交叉核(內嵌 verifier_capture_digest == ops_postcheck evidence digest ==
# command_capture_v2.record_digest 且 capture node ≠ applier)、以及 kind 白名單。
# CC-A2:S2.5A/S2.5B 是「啟動 / 最終認證 production systemd service」兩步,原本只有
# declaration-only claim(不要求 ops_preflight fragment、無 verifier_capture 三方核、無
# applier != verifier)。既有的 §6 硬門 aiml_gate_receipt_s2_5.validate_s2_5_attestation_binding
# (自述鏡 validate_pg_observer_bootstrap_binding)此前不在本表、全 repo 只有自己的測試呼叫,
# 現由上方適配層接入。
_DELEGATED_STEP_BINDINGS = {
    "S2_0_APPLY": pg_observer.validate_pg_observer_bootstrap_binding,
    "S2_1_DRILL": quiesce_fence.validate_quiesce_fence_binding,
    "S2_5A_START": _s2_5_attestation_binding_errors,
    "S2_5B_FINAL": _s2_5_attestation_binding_errors,
}


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
    try:
        return list(delegate(
            packet, route, fragments_by_node, evidence_by_id, valid_receipts,
        ))
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
        # NEW-P3-F:被委派者拿到畸形封包時可能拋例外(它們是為自己的 EFFECT session 寫的,
        # 未必對任意輸入全 typed)。closure admission 不得讓裸 traceback 逸出呼叫端——鏡
        # agent_governance_closure 對 route_task 的處理,轉成 typed error(fail-closed:
        # 例外一律計為錯誤,絕不當成「委派通過」)。
        return [
            f"S2 {step} delegated per-step closure gate raised "
            f"{type(error).__name__}: {error}"
        ]


def _ops_postcheck_artifact_errors(
    postcheck: dict[str, Any],
    receipt: dict[str, Any],
    contract: dict[str, Any],
    *,
    step: str,
) -> list[str]:
    """獨立 ops_postcheck 的 artifact 面(NEW-P1-A / NEW-P1-B / NEW-P3-H)。

    ``postcheck_receipt_binding is None``(S2.0/S2.1)時本函式不執法:那兩步的 postcheck
    形狀與三方交叉核歸委派的既有硬門。其餘 step 一律要求(逐條鏡先例
    ``agent_governance_target_host_effects:640-686``):**exact field set**、``schema_version``
    等於 evidence kind、**``status`` 必為 PASS**、``self_digest`` canonical 反偽造重算成立且
    等於 wrapper ``digest``(否則 artifact 可被整段替換而 wrapper 照舊)、綁定欄位等於 effect
    receipt 的 ``self_digest``,其餘欄位逐一綁到 admitted step / receipt / wrapper 的對應值。

    ⚠ NEW-P1-B 的教訓(先例採用不完整):artifact 自報的 ``status`` 若從不被讀,一份明說
    「我驗失敗」的獨立 postcheck(合法重封、所有 digest 全對)仍會背書 closure PASS。而對
    四個 s2_4 step 與 S2.2B 來說本函式是**唯一**的 postcheck 執法面(那些 step 在
    ``_DELEGATED_STEP_BINDINGS`` 內沒有硬門),其中含 W6B APPLY(裝 unit + PG migration)。

    誠實界線:本函式**不**驗 applier != verifier——s2_4 家族收據頂層沒有 apply actor node
    欄位可比,其分離閉合在 adapter 層;此處只要求 ``verifier_node`` 非空(先例同型)。
    """

    receipt_binding = contract["postcheck_receipt_binding"]
    if receipt_binding is None:
        return []
    artifact = postcheck.get("artifact")
    if not isinstance(artifact, dict):
        return [
            "S2 ops_postcheck must embed the canonical postcheck artifact "
            f"({contract['postcheck_kind']})"
        ]
    errors: list[str] = []
    if set(artifact) != _S2_OPS_POSTCHECK_ARTIFACT_FIELDS:
        errors.append(
            "S2 ops_postcheck artifact fields are not exact "
            f"({sorted(_S2_OPS_POSTCHECK_ARTIFACT_FIELDS)})"
        )
    if artifact.get("schema_version") != contract["postcheck_kind"]:
        errors.append(
            "S2 ops_postcheck artifact schema_version does not match the evidence kind"
        )
    if artifact.get("status") != _S2_OPS_POSTCHECK_PASS_STATUS:
        errors.append(
            "S2 ops_postcheck artifact status must be PASS (an independent postcheck "
            "that reports its own failure never endorses a closure PASS)"
        )
    if artifact.get("self_digest") != _artifact_self_digest(artifact):
        errors.append(
            "S2 ops_postcheck artifact self_digest does not bind the canonical artifact"
        )
    if postcheck.get("digest") != artifact.get("self_digest"):
        errors.append(
            "S2 ops_postcheck evidence digest is not the postcheck artifact self_digest"
        )
    if _get(postcheck, receipt_binding) != receipt.get("self_digest"):
        errors.append(
            f"S2 ops_postcheck {receipt_binding} is not bound to the effect receipt "
            "self_digest"
        )
    # NEW-P3-H:其餘欄位不得是死欄位(舊碼填任意值全過)——逐一綁 admitted step / receipt /
    # wrapper 的對應值。
    for field, expected, message in (
        ("effect_step", step, "is not the admitted step"),
        (
            "source_head", receipt.get("source_head"),
            "is not bound to the effect source head",
        ),
        (
            "host", _get(receipt, contract["host_field"]),
            "is not bound to the effect target host",
        ),
        (
            "observed_at", postcheck.get("observed_at"),
            "is not bound to the evidence wrapper observed_at",
        ),
    ):
        if artifact.get(field) != expected:
            errors.append(f"S2 ops_postcheck artifact {field} {message}")
    verifier_node = artifact.get("verifier_node")
    if not (isinstance(verifier_node, str) and verifier_node):
        errors.append("S2 ops_postcheck artifact must carry a non-empty verifier_node")
    return errors


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
    # CC-A1/CC-B(自身)+ Codex-1(effect-DAG 傳遞上游):兩者皆令本 step 不可 closure-PASS。
    # 今日 S2.0 是全鏈的根且 blocked ⇒ 九步全部在此拿到非空列表(誠實後果,見模組 docstring)。
    blocked = contract["closure_pass_blocked_reason"]
    errors.extend(s2_closure_block_errors(step))
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

    # 獨立 ops_postcheck:恰一 runtime postcheck evidence,kind 必在 contract 白名單、
    # artifact 必反偽造重算並交叉綁 receipt self_digest(NEW-P1-A 的可表示形狀,鏡
    # target-host 的 artifact.self_digest ↔ wrapper digest 先例),晚於 effect 完成;
    # acceptance 必同綁 receipt + postcheck(缺一即非 PASS)。
    # 誠實界線(CC-A2 對 :582-588 舊註 overclaim 的更正):本段**不**驗 applier != verifier
    # ——它只比 scope/source/kind 與 digest 綁定,手上沒有 node 身分比對。applier != verifier
    # 只存在於被委派的 per-step 硬門(S2.0/S2.1 的既有 predicate、S2.5A/S2.5B 的 §6 attestation
    # binding);s2_4 家族的收據頂層沒有 apply actor node 欄位可比,其 applier/verifier 分離
    # 閉合在 adapter 層。舊註另稱「鏡 P0-B 的 operation_receipt cross-bind」亦為假:本段從未
    # 觸碰 operation_receipt(那是通用 deploy/P0-B 的 ops_postcheck_v1 形狀)。
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
        errors.extend(
            _ops_postcheck_artifact_errors(postcheck, receipt, contract, step=step)
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
        # Codex-1:此處刻意只看**自身** blocked,不看傳遞上游——被傳遞阻塞的 step 自己的
        # effect 確實接觸過 runtime(收據是真 production 頂點),要求 runtime_contact=true 仍
        # 是誠實記錄;不可 PASS 由上方 typed 阻塞鏈負責,不靠削弱這兩條記帳要求。
        if packet.get("side_effects", {}).get("runtime_contact") is not True:
            errors.append("S2 successful effect must record runtime_contact=true")
        if packet.get("disposition") != "CHANGED":
            errors.append("S2 successful effect closure disposition must be CHANGED")
    return errors

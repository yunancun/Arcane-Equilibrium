"""S2E.1:六段 S2 effect DAG 的 closure effect-binding sibling(鏡 P0-B/target-host 家族)。

職責(PA 設計「Closure/rollback binding」節):

* ``validate_s2_effect_evidence`` —— 一份 closure evidence wrapper 的 receipt 級驗:
  receipt 的實際重算**全部委派**既有 per-step validators(經中央 AIML 閘
  ``aiml_gate_receipt_validator.validate_aiml_artifact``,其內再委派
  pg_observer_bootstrap / alr_quiesce_fence / s2_4 / s2_5 / s2_2b 各 SSOT 葉),本模組
  只補 wrapper↔receipt 綁定、closure baseline head 綁定與 production 成功集判定——
  ``RECOVERY_REQUIRED`` / ``EXTERNAL_VERIFICATION_PENDING`` / source-simulation 頂點
  永不換算 closure PASS。
* ``validate_s2_effect_binding`` —— closure admission:route 有該 step 的 adapter 節點
  ⇔ 恰一 valid receipt;receipt 暴露的上游 digest 必等於 route claim admission;intent
  authority_ref cross-bind(鏡 effects.py 通用 deploy 同型;S2.2B 無 intent artifact,
  上游錨由 claim 綁定取代——唯一合法上游 = s2_5_final_attestation_v1);獨立 ops_postcheck
  必晚於 effect 完成且 acceptance 必同綁 receipt + postcheck。

⚠ SOURCE-TRUTH 邊界:route 層無法驗 head/freshness/permit 真偽是設計事實——閉合在
adapter(SSHSIG/attestor/replay-ledger)與 closure(out-of-band 信任主機驗證)層;本
模組乾淨 ``[]`` 「不」證任何 runtime 真的施加過。rollback 綁定不新造:各 adapter 的
rollback schema 已在 registry,route 節點 metadata 帶出 result/rollback schema version。
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from agent_governance_routing import (
    S2_EFFECT_STEPS,
    _s2_effect_step,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ML_TRAINING_DIR = REPO_ROOT / "program_code" / "ml_training"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

# 固定 environment 標籤(鏡 target_host 常量先例):S2 效果面全綁 trade-core 的 AIML S2 DAG。
S2_EFFECT_ENVIRONMENT = "trade_core_aiml_s2"

S2_ADAPTER_IDS = frozenset(
    contract["adapter_id"] for contract in S2_EFFECT_STEPS.values()
)

# per-step receipt 契約:schema/成功 status/身分與時間欄位/claim↔receipt digest 綁定。
# 成功集只認 production 語義(APPLIED/TERMINAL_CLEAN/PREPARED/APPLIED_INACTIVE/
# RUNNING_ATTESTED/QUIESCED_STATIC_GUARDS_HELD/FINAL_ATTESTED/RUNTIME_COMPATIBILITY_ATTESTED);
# SOURCE_SIMULATION_PASS / SOURCE_REVALIDATION_PASS 是 source-lane 頂點,不是 EFFECT 收據。
_PROBE_CONTRACT = {
    "receipt_schema_version": "s2_4_capability_probe_effect_receipt_v1",
    "status_field": "terminal_status",
    "success_statuses": frozenset({"TERMINAL_CLEAN"}),
    "intent_schema_version": "s2_4_capability_probe_intent_v1",
    "intent_id_field": "probe_id",
    "intent_digest_field": "probe_core_digest",
    "started_field": "observed_at",
    "observed_field": "observed_at",
    "expiry_field": "expires_at",
    "host_field": "target_host",
    "claim_receipt_bindings": {},
}
S2_STEP_RECEIPT_CONTRACTS: dict[str, dict[str, Any]] = {
    "S2_0_APPLY": {
        "receipt_schema_version": "pg_observer_bootstrap_result_v1",
        "status_field": "status",
        "success_statuses": frozenset({"APPLIED"}),
        "intent_schema_version": "pg_observer_bootstrap_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {},
    },
    "S2_4_W6A_PROBE": dict(_PROBE_CONTRACT),
    "S2_4_W6A_PREPARE": {
        "receipt_schema_version": "s2_4_prepare_effect_receipt_v1",
        "status_field": "terminal_status",
        "success_statuses": frozenset({"PREPARED"}),
        "intent_schema_version": "s2_4_prepare_intent_v1",
        "intent_id_field": "prepare_id",
        "intent_digest_field": "prepare_core_digest",
        "started_field": "observed_at",
        "observed_field": "observed_at",
        "expiry_field": "expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {},
    },
    "S2_4_W6B_PROBE": dict(_PROBE_CONTRACT),
    "S2_4_W6B_APPLY": {
        "receipt_schema_version": "s2_4_install_effect_receipt_v1",
        "status_field": "status",
        "success_statuses": frozenset({"APPLIED_INACTIVE"}),
        "intent_schema_version": "s2_4_install_plan_v1",
        "intent_id_field": "plan_id",
        "intent_digest_field": "plan_core_digest",
        "started_field": "observed_at",
        "observed_field": "observed_at",
        "expiry_field": "expires_at",
        "host_field": "target_host",
        # receipt 頂層暴露的上游 digest 必等於 route claim admission(prepare_result_digest
        # = s2_4_prepared_install_bundle_v1 digest;registry s2_4_install_adapter_v1)。
        "claim_receipt_bindings": {
            "s2_4_prepared_bundle": "prepare_result_digest",
            "s2_4_installed_unit_probe_receipt": "installed_unit_probe_receipt_digest",
        },
    },
    "S2_5A_START": {
        "receipt_schema_version": "s2_5_running_attestation_v1",
        "status_field": "status",
        "success_statuses": frozenset({"RUNNING_ATTESTED"}),
        "intent_schema_version": "s2_5_start_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {},
    },
    "S2_1_DRILL": {
        "receipt_schema_version": "quiesce_result_v1",
        "status_field": "status",
        "success_statuses": frozenset({"QUIESCED_STATIC_GUARDS_HELD"}),
        "intent_schema_version": "quiesce_intent_v1",
        "intent_id_field": "intent_id",
        "intent_digest_field": "intent_digest",
        "started_field": "started_at",
        "observed_field": "completed_at",
        "expiry_field": "evidence_expires_at",
        "host_field": "target_host",
        "claim_receipt_bindings": {},
    },
    "S2_5B_FINAL": {
        "receipt_schema_version": "s2_5_final_attestation_v1",
        "status_field": "status",
        "success_statuses": frozenset({"FINAL_ATTESTED"}),
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
    },
    "S2_2B_RUNTIME_DONE": {
        "receipt_schema_version": "ingestion_compatibility_receipt_v1",
        "status_field": "status",
        "success_statuses": frozenset({"RUNTIME_COMPATIBILITY_ATTESTED"}),
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
    },
}
S2_RECEIPT_SCHEMA_VERSIONS = frozenset(
    contract["receipt_schema_version"]
    for contract in S2_STEP_RECEIPT_CONTRACTS.values()
)


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
    """實際重算全部委派中央 AIML 閘(其內再委派各 per-step SSOT 葉)。

    測試可 monkeypatch 此縫作結構綁定測試;真委派由 sentinel 測試釘住。
    """

    if str(ML_TRAINING_DIR) not in sys.path:
        sys.path.insert(0, str(ML_TRAINING_DIR))
    import aiml_gate_receipt_validator as central_validator
    return central_validator.validate_aiml_artifact(receipt, now=now)


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
    """把一份 S2 receipt 包進 closure evidence envelope(不改變身分)。"""

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
    if status not in contract["success_statuses"]:
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
    errors: list[str] = []
    contract = S2_STEP_RECEIPT_CONTRACTS[step]
    adapter_id = S2_EFFECT_STEPS[step]["adapter_id"]
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

    # 獨立 ops_postcheck(applier != verifier):恰一 runtime postcheck evidence,晚於
    # effect 完成;acceptance 必同綁 receipt + postcheck(缺一即非 PASS)。
    fragment = fragments_by_node.get("ops_postcheck", {})
    postchecks = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
    ]
    if len(postchecks) != 1:
        errors.append(
            "S2 closure requires exactly one independent ops_postcheck runtime evidence"
        )
    else:
        postcheck = postchecks[0]
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
    if packet.get("side_effects", {}).get("runtime_contact") is not True:
        errors.append("S2 successful effect must record runtime_contact=true")
    if packet.get("disposition") != "CHANGED":
        errors.append("S2 successful effect closure disposition must be CHANGED")
    return errors

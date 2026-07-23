"""Purpose-built admission and closure bindings for the S1.6B target-host effect.

把 S1.6B target-host 探針(今日為 disjoint self-validating harness)接成一條 closure-admissible
effect seam:一個專屬 ``target_host_effect_result_v1``(非通用 ``effect_adapter_result_v1``,見
§13 C1),內嵌 typed ``learning_runtime_choice_receipt_target_host_v1`` 並以其 ``self_digest`` 綁定,
新增 build/validate + self-digest,以及 closure 端 evidence/binding 檢查(mirror
``agent_governance_p0b_effects``),讓 ``agent_governance_closure.py`` 核心零改動。

**§13 C4(真正的執法點)**:``validate_target_host_effect_result`` 對內嵌的 choice receipt 一律以
``validate_target_host_choice_receipt(receipt, now=…, require_success=True,
require_target_host_attested=True)`` 嚴格驗證(當 effect 宣稱 PASS 或呼叫端 ``require_success``);
STRUCTURAL_ONLY / 裸 digest / 未附 governed on-host ``command_capture_v2`` 的 receipt 於此 effect lane
被拒。中央離線閘對「單獨的 choice receipt」只做結構檢查(``require_target_host_attested=False``),故此處
的嚴格閘是唯一的真實執法。離線僅結構接受非認證(CLAUDE.md):真確性由受信主機重放內嵌 capture 確立。
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import agent_governance_target_host_choice as _th_choice
from agent_governance_schema import schema_subset_errors


TARGET_HOST_ADAPTER_ID = "target_host_disposable_runtime_probe_adapter_v1"
RESULT_SCHEMA_VERSION = "target_host_effect_result_v1"
INTENT_SCHEMA_VERSION = "target_host_disposable_runtime_probe_intent_v1"
CHOICE_RECEIPT_SCHEMA_VERSION = "learning_runtime_choice_receipt_target_host_v1"
# closure runtime evidence 需要非空 environment(closure.py:221);本 effect 無 target_environment,
# 故 wrapper environment 綁到一個常量身分(非交易環境;僅拋棄式 target-host 探針)。
TARGET_HOST_EFFECT_ENVIRONMENT = "trade_core_target_host_probe"
EFFECT_STATUS_PASS = "TARGET_HOST_DISPOSABLE_PROBE_PASS"
EFFECT_STATUS_FAILED = "FAILED"

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEAD_RE = re.compile(r"^[0-9a-f]{40}$")
SCHEMA_DIR = (
    Path(__file__).resolve().parents[2]
    / "program_code/ml_training/schemas/aiml_gate_receipts"
)
RESULT_SCHEMA_PATH = SCHEMA_DIR / "target_host_effect_result_v1.schema.json"
INTENT_SCHEMA_PATH = SCHEMA_DIR / "target_host_disposable_runtime_probe_intent_v1.schema.json"

RESULT_FIELDS = frozenset({
    "schema_version", "adapter_id", "effect_status", "intent_id", "intent_digest",
    "target_host", "source_head", "applier_node_id", "postcheck_verifier_node_id",
    "choice_receipt_digest", "choice_receipt", "approved_by", "approved_at",
    "started_at", "completed_at", "intent_expires_at", "evidence_expires_at",
    "failure_reason", "receipt_digest",
})


@lru_cache(maxsize=1)
def _result_schema() -> dict[str, Any]:
    return json.loads(RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _intent_schema() -> dict[str, Any]:
    return json.loads(INTENT_SCHEMA_PATH.read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical(value)).hexdigest()


def _parse_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timezone is required")
    return parsed


def target_host_effect_receipt_digest(receipt: dict[str, Any]) -> str:
    """Hash every result field except the self-referential receipt_digest."""

    return _digest({
        key: value for key, value in receipt.items() if key != "receipt_digest"
    })


def _fixed_path_candidate(choice_receipt: dict[str, Any]) -> dict[str, Any]:
    probes = choice_receipt.get("candidate_probes")
    if not isinstance(probes, list):
        return {}
    return next(
        (
            block for block in probes
            if isinstance(block, dict)
            and block.get("candidate_id") == "content_addressed_fixed_path"
        ),
        {},
    )


def build_target_host_effect_result(
    *,
    choice_receipt: dict[str, Any],
    intent_id: str,
    intent_digest: str,
    source_head: str,
    approved_by: str,
    approved_at: str,
    started_at: str,
    completed_at: str,
    intent_expires_at: str,
    evidence_expires_at: str,
    effect_status: str | None = None,
    failure_reason: str | None = None,
) -> dict[str, Any]:
    """Project one embedded target-host choice receipt into the dedicated effect result.

    ``applier_node_id`` / ``postcheck_verifier_node_id`` / ``target_host`` 皆由內嵌 receipt 派生
    (非自由參數);``effect_status`` 預設由 receipt 是否 PASS 且無 failure_reason 導出。
    """

    fixed = _fixed_path_candidate(choice_receipt)
    host_identity = choice_receipt.get("host_identity") or {}
    derived_status = (
        EFFECT_STATUS_PASS
        if choice_receipt.get("status") == "PASS" and failure_reason is None
        else EFFECT_STATUS_FAILED
    )
    receipt: dict[str, Any] = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "adapter_id": TARGET_HOST_ADAPTER_ID,
        "effect_status": effect_status or derived_status,
        "intent_id": intent_id,
        "intent_digest": intent_digest,
        "target_host": host_identity.get("expected_host"),
        "source_head": source_head,
        "applier_node_id": fixed.get("apply_actor_node"),
        "postcheck_verifier_node_id": fixed.get("postcheck_verifier_node"),
        "choice_receipt_digest": choice_receipt.get("self_digest"),
        "choice_receipt": copy.deepcopy(choice_receipt),
        "approved_by": approved_by,
        "approved_at": approved_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "intent_expires_at": intent_expires_at,
        "evidence_expires_at": evidence_expires_at,
        "failure_reason": failure_reason,
    }
    receipt["receipt_digest"] = target_host_effect_receipt_digest(receipt)
    return receipt


def validate_target_host_effect_result(
    receipt: Any,
    *,
    now: str | None,
    expected_source_head: str | None = None,
    require_success: bool = False,
) -> list[str]:
    """Validate the dedicated result structure/integrity + the STRICT embedded-attestation gate.

    ``expected_source_head=None`` 為中央離線閘(無 closure baseline):跳過 source_head 綁定,
    仍做 schema/digest/嵌入 receipt 嚴格驗證/applier!=verifier/時間序。closure/evidence 路徑則傳入
    真 baseline head 並 ``require_success=True``。
    """

    if not isinstance(receipt, dict):
        return ["target-host effect result must be an object"]
    schema = _result_schema()
    errors = [
        f"target-host effect result schema violation: {error}"
        for error in schema_subset_errors(receipt, schema, schema)
    ]
    if set(receipt) != RESULT_FIELDS:
        errors.append(
            "target-host effect result fields mismatch: "
            f"missing={sorted(RESULT_FIELDS - set(receipt))} "
            f"extra={sorted(set(receipt) - RESULT_FIELDS)}"
        )
    if receipt.get("schema_version") != RESULT_SCHEMA_VERSION:
        errors.append("target-host effect result schema_version is invalid")
    if receipt.get("adapter_id") != TARGET_HOST_ADAPTER_ID:
        errors.append("target-host effect result adapter_id is invalid")
    if receipt.get("effect_status") not in {EFFECT_STATUS_PASS, EFFECT_STATUS_FAILED}:
        errors.append("target-host effect result effect_status is invalid")
    if receipt.get("receipt_digest") != target_host_effect_receipt_digest(receipt):
        errors.append("target-host effect result receipt_digest mismatch")
    if expected_source_head is not None and receipt.get("source_head") != expected_source_head:
        errors.append("target-host effect result source_head differs from closure baseline")
    if receipt.get("applier_node_id") == receipt.get("postcheck_verifier_node_id"):
        errors.append("target-host effect result applier must differ from postcheck verifier")

    status = receipt.get("effect_status")
    success = status == EFFECT_STATUS_PASS
    strict = bool(success or require_success)
    choice = receipt.get("choice_receipt")
    if not isinstance(choice, dict):
        errors.append("target-host effect result lacks an embedded choice receipt")
    else:
        if choice.get("schema_version") != CHOICE_RECEIPT_SCHEMA_VERSION:
            errors.append("target-host effect result embedded receipt schema_version is invalid")
        if receipt.get("choice_receipt_digest") != choice.get("self_digest"):
            errors.append(
                "target-host effect result choice_receipt_digest must equal the embedded "
                "choice receipt self_digest (digest and artifact cannot be decoupled)"
            )
        # §13 C4:嚴格 attestation 是這條 lane 唯一的真實執法(中央離線閘只結構驗)。
        errors.extend(
            f"target-host effect embedded choice receipt invalid: {error}"
            for error in _th_choice.validate_target_host_choice_receipt(
                choice,
                now=now,
                require_success=strict,
                require_target_host_attested=strict,
            )
        )
        host_identity = choice.get("host_identity") or {}
        if receipt.get("target_host") != host_identity.get("expected_host") or (
            receipt.get("target_host") != host_identity.get("observed_host")
        ):
            errors.append("target-host effect result target_host is not receipt-host-bound")
        fixed = _fixed_path_candidate(choice)
        if receipt.get("applier_node_id") != fixed.get("apply_actor_node"):
            errors.append("target-host effect result applier_node_id is not receipt-applier-bound")
        if receipt.get("postcheck_verifier_node_id") != fixed.get("postcheck_verifier_node"):
            errors.append("target-host effect result postcheck_verifier_node_id is not receipt-verifier-bound")

    failure_reason = receipt.get("failure_reason")
    if success:
        if failure_reason is not None:
            errors.append("PASS target-host effect result cannot carry a failure_reason")
    else:
        if not isinstance(failure_reason, str) or not failure_reason.strip():
            errors.append("FAILED target-host effect result requires a non-empty failure_reason")
    if require_success and not success:
        errors.append("target-host effect result does not prove a successful probe apply")

    try:
        approved = _parse_time(str(receipt.get("approved_at", "")))
        started = _parse_time(str(receipt.get("started_at", "")))
        completed = _parse_time(str(receipt.get("completed_at", "")))
        intent_expiry = _parse_time(str(receipt.get("intent_expires_at", "")))
        evidence_expiry = _parse_time(str(receipt.get("evidence_expires_at", "")))
        if not approved <= started <= completed < intent_expiry:
            errors.append("target-host effect result approval/start/completion order is invalid")
        if not completed < evidence_expiry <= completed + timedelta(minutes=15):
            errors.append("target-host effect result evidence TTL exceeds fifteen minutes")
    except (TypeError, ValueError):
        errors.append("target-host effect result timestamps are invalid")
    return errors


def build_target_host_effect_evidence(receipt: dict[str, Any]) -> dict[str, Any]:
    """Wrap a dedicated result in the closure evidence envelope without changing identity."""

    return {
        "id": f"effect:{receipt['adapter_id']}:{receipt['intent_id']}",
        "scope": "runtime",
        "kind": "effect_adapter_result_v1",
        "digest": receipt["receipt_digest"],
        "observed_at": receipt["completed_at"],
        "expiry": receipt["evidence_expires_at"],
        "host": receipt["target_host"],
        "environment": TARGET_HOST_EFFECT_ENVIRONMENT,
        "source": receipt["adapter_id"],
        "receipt": receipt,
    }


def validate_target_host_effect_evidence(
    evidence: dict[str, Any], *, expected_source_head: str
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate the dedicated result and every wrapper-to-receipt binding."""

    receipt = evidence.get("receipt")
    now = receipt.get("completed_at") if isinstance(receipt, dict) else None
    errors = validate_target_host_effect_result(
        receipt, now=now, expected_source_head=expected_source_head, require_success=True,
    )
    if not isinstance(receipt, dict):
        return errors, None
    bindings = {
        "source": receipt.get("adapter_id"),
        "digest": receipt.get("receipt_digest"),
        "host": receipt.get("target_host"),
        "observed_at": receipt.get("completed_at"),
        "expiry": receipt.get("evidence_expires_at"),
    }
    for field, expected in bindings.items():
        if evidence.get(field) != expected:
            errors.append(f"target-host effect evidence {field} is not receipt-bound")
    if evidence.get("environment") != TARGET_HOST_EFFECT_ENVIRONMENT:
        errors.append("target-host effect evidence environment is not the exact probe environment")
    if evidence.get("kind") != "effect_adapter_result_v1" or evidence.get("scope") != "runtime":
        errors.append("target-host effect evidence wrapper is invalid")
    return errors, receipt if not errors else None


def validate_target_host_effect_binding(
    packet: dict[str, Any],
    route: dict[str, Any],
    fragments_by_node: dict[str, dict[str, Any]],
    evidence_by_id: dict[str, dict[str, Any]],
    valid_receipts: dict[str, dict[str, Any]],
) -> list[str]:
    """Closure admission for one target-host probe effect; never borrow generic deploy proof."""

    errors: list[str] = []
    matching = [
        (evidence_id, receipt) for evidence_id, receipt in valid_receipts.items()
        if receipt.get("adapter_id") == TARGET_HOST_ADAPTER_ID
    ]
    if len(matching) != 1:
        return ["target-host closure PASS requires exactly one target-host effect receipt"]
    receipt_id, receipt = matching[0]
    effect_nodes = [
        node for node in route.get("nodes", [])
        if node.get("kind") == "effect_adapter" and node.get("mandatory")
    ]
    if not any(node.get("id") == TARGET_HOST_ADAPTER_ID for node in effect_nodes):
        errors.append("target-host effect receipt is not routed to the exact target-host adapter node")

    intent_source = f"{INTENT_SCHEMA_VERSION}:{receipt.get('intent_id')}"
    intent_refs = [
        ref for ref in packet.get("authority_refs", [])
        if ref.get("class") == "claim_evidence" and ref.get("source") == intent_source
    ]
    if len(intent_refs) != 1 or intent_refs[0].get("digest") != receipt.get("intent_digest"):
        errors.append("target-host effect receipt lacks exact intent authority")
    else:
        if intent_refs[0].get("expiry") != receipt.get("intent_expires_at"):
            errors.append("target-host intent authority expiry mismatch")
        try:
            if _parse_time(str(intent_refs[0].get("observed_at", ""))) > _parse_time(
                str(receipt.get("started_at", ""))
            ):
                errors.append("target-host intent authority was observed after effect start")
        except (TypeError, ValueError):
            errors.append("target-host intent authority timestamp is invalid")

    # 獨立驗證者(ops_postcheck)綁自己的 runtime 殘留掃描證據;applier(adapter 節點)!= verifier。
    fragment = fragments_by_node.get("ops_postcheck", {})
    postchecks = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
    ]
    if len(postchecks) != 1:
        errors.append("target-host closure requires exactly one independent ops_postcheck")
    else:
        verifier_node = postchecks[0].get("verifier_node") or postchecks[0].get("source")
        if verifier_node == receipt.get("applier_node_id"):
            errors.append("target-host ops_postcheck verifier must differ from the applier node")

    accepted = bool(postchecks) and any(
        item.get("status") == "PASS"
        and {receipt_id, postchecks[0].get("id")}.issubset(set(item.get("evidence_refs", [])))
        for item in packet.get("acceptance", [])
    )
    if not accepted:
        errors.append(
            "target-host passed acceptance does not bind the effect receipt plus independent ops_postcheck"
        )
    if packet.get("side_effects", {}).get("runtime_contact") is not True:
        errors.append("target-host successful effect must record runtime_contact=true")
    if packet.get("disposition") != "CHANGED":
        errors.append("target-host successful effect closure must be CHANGED")
    return errors

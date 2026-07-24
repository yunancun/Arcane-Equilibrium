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
TARGET_HOST_OPS_POSTCHECK_KIND = "target_host_ops_postcheck_v1"
TARGET_HOST_VERIFIER_CAPTURE_KIND = "target_host_verifier_command_capture_v2"
TARGET_HOST_CLOSURE_EVIDENCE_KINDS = frozenset({
    TARGET_HOST_OPS_POSTCHECK_KIND,
    TARGET_HOST_VERIFIER_CAPTURE_KIND,
})
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
    "choice_receipt_digest", "choice_receipt", "verifier_capture_digest",
    "approved_by", "approved_at",
    "started_at", "completed_at", "intent_expires_at", "evidence_expires_at",
    "failure_reason", "receipt_digest",
})

# choice 內嵌 independent_postcheck seam note 綁定 distinct verifier capture digest 的固定前綴
# (見 agent_governance_target_host_apply._embed_verifier_capture_binding)。closure 端據此把
# 結構化 ``verifier_capture_digest`` 與 note 內的持久綁定交叉核對,兩者必一致。
VERIFIER_CAPTURE_NOTE_PREFIX = "distinct verifier capture digest: "
POSTCHECK_FIELDS = frozenset({
    "schema_version", "status", "verifier_node", "verifier_capture_digest",
    "residue_observation", "source_head", "host", "observed_at",
    "evidence_refs", "self_digest",
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


def _independent_postcheck_seam(choice_receipt: dict[str, Any]) -> dict[str, Any]:
    """Return the embedded fixed-path ``independent_postcheck`` seam block (or {})."""

    seams = _fixed_path_candidate(choice_receipt).get("seams")
    if not isinstance(seams, list):
        return {}
    return next(
        (
            seam for seam in seams
            if isinstance(seam, dict)
            and seam.get("seam_id") == _th_choice.SEAM_INDEPENDENT_POSTCHECK
        ),
        {},
    )


def _note_bound_verifier_capture_digest(choice_receipt: dict[str, Any]) -> str | None:
    """Extract the distinct-verifier capture digest durably bound into the seam note, or None.

    ``_embed_verifier_capture_binding`` 以固定前綴把驗證者的相異 capture digest 綁進 upgraded choice
    的 independent_postcheck seam ``note``;此處反解出該 digest,供結構化 ``verifier_capture_digest`` 與
    note 綁定交叉核對(兩者必一致,否則 receipt 遭竄改/欄位脫鉤)。
    """

    note = _independent_postcheck_seam(choice_receipt).get("note")
    if not isinstance(note, str) or VERIFIER_CAPTURE_NOTE_PREFIX not in note:
        return None
    tail = note.rsplit(VERIFIER_CAPTURE_NOTE_PREFIX, 1)[1].strip()
    candidate = tail.split()[0] if tail else ""
    return candidate if DIGEST_RE.fullmatch(candidate) else None


def _is_clean_residue(residue: Any) -> bool:
    """A postcheck residue observation is clean iff every teardown flag is exactly True."""

    return isinstance(residue, dict) and all(
        residue.get(flag) is True for flag in _th_choice.RESIDUE_OBSERVATION_KEYS
    )


def _postcheck_digest(artifact: dict[str, Any]) -> str:
    return _digest({
        key: value for key, value in artifact.items() if key != "self_digest"
    })


def build_target_host_closure_evidence(
    receipt: dict[str, Any],
    verifier_capture: dict[str, Any],
    residue_observation: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build schema-valid runtime wrappers for the independent postcheck and capture.

    The governed verifier capture was compiled under its own OPS context, so it is
    deliberately wrapped as a target-host artifact rather than misrepresented as a
    closure-native ``command_capture_v2``.  The effect receipt authenticates its
    record digest and the closure cross-binds the exact bytes below.
    """

    capture_id = "target-host-verifier-capture"
    capture_completed = str(verifier_capture.get("completed_at", ""))
    expiry = str(receipt.get("evidence_expires_at", ""))
    capture_evidence = {
        "id": capture_id,
        "scope": "runtime",
        "kind": TARGET_HOST_VERIFIER_CAPTURE_KIND,
        "digest": verifier_capture.get("record_digest"),
        "observed_at": capture_completed,
        "expiry": expiry,
        "host": receipt.get("target_host"),
        "environment": TARGET_HOST_EFFECT_ENVIRONMENT,
        "source": "ops_postcheck",
        "artifact": copy.deepcopy(verifier_capture),
    }
    postcheck_artifact = {
        "schema_version": TARGET_HOST_OPS_POSTCHECK_KIND,
        "status": "PASS",
        "verifier_node": receipt.get("postcheck_verifier_node_id"),
        "verifier_capture_digest": verifier_capture.get("record_digest"),
        "residue_observation": copy.deepcopy(residue_observation),
        "source_head": receipt.get("source_head"),
        "host": receipt.get("target_host"),
        "observed_at": capture_completed,
        "evidence_refs": [capture_id],
    }
    postcheck_artifact["self_digest"] = _postcheck_digest(postcheck_artifact)
    postcheck_evidence = {
        "id": "target-host-ops-postcheck",
        "scope": "runtime",
        "kind": TARGET_HOST_OPS_POSTCHECK_KIND,
        "digest": postcheck_artifact["self_digest"],
        "observed_at": capture_completed,
        "expiry": expiry,
        "host": receipt.get("target_host"),
        "environment": TARGET_HOST_EFFECT_ENVIRONMENT,
        "source": "ops_postcheck",
        "artifact": postcheck_artifact,
    }
    return postcheck_evidence, capture_evidence


def _validate_verifier_capture_evidence(
    evidence: dict[str, Any],
    *,
    expected_digest: str | None,
    applier_capture_digest: Any,
    applier_capture: dict[str, Any],
    applier_node: Any,
    verifier_node: Any,
    expected_host: Any,
    expected_source_head: Any,
    expected_expiry: Any,
) -> list[str]:
    """Validate the third evidence entry: the distinct verifier's own governed command_capture_v2.

    要求:(1) evidence.digest == ops_postcheck 引用的 capture digest;(2) 內嵌 record 通過
    ``agent_governance_command_capture_v2.validate_governed_command_capture`` 的完整 **offline** 結構/
    綁定/self-digest 驗(RECORD_FIELDS 完整、``trust_tier==LOCAL_REPRODUCIBLE``、
    ``effect_enforcement=="repository_policy_only"``、**禁自報 ``host_sandbox_attestation_ref``**、
    execution-task/node/argv/authorization/generation 一致、``record_digest==self-digest``)——一個內容空殼
    stub 於此被拒;(3) ``record_digest`` == 該 digest;(4) 與 applier 的 on-host capture digest 相異
    (distinct process + capture);(5) capturer role/node/native_agent 與 applier capture 及 applier 節點相異。
    是否**真跑過**(replay 真確性)由受信主機重放認證,非本 offline 閘(CLAUDE.md:離線結構接受非認證)。
    """

    errors: list[str] = []
    if evidence.get("digest") != expected_digest:
        errors.append("verifier capture evidence digest is not the ops_postcheck-referenced capture digest")
    if evidence.get("kind") != TARGET_HOST_VERIFIER_CAPTURE_KIND:
        errors.append("verifier capture evidence kind is invalid")
    if evidence.get("scope") != "runtime":
        errors.append("verifier capture evidence scope must be runtime")
    if evidence.get("host") != expected_host:
        errors.append("verifier capture evidence host is not effect-receipt-bound")
    if evidence.get("environment") != TARGET_HOST_EFFECT_ENVIRONMENT:
        errors.append("verifier capture evidence environment is invalid")
    if evidence.get("source") != "ops_postcheck":
        errors.append("verifier capture evidence source is invalid")
    if evidence.get("expiry") != expected_expiry:
        errors.append("verifier capture evidence expiry is not effect-receipt-bound")
    capture = evidence.get("artifact")
    if not isinstance(capture, dict):
        errors.append("verifier capture evidence must embed the governed command_capture_v2 record")
        return errors
    import agent_governance_command_capture_v2 as _cap

    # 完整 offline governed 驗證(reexecute=False;不觸 fs replay):這是 CLAUDE.md 的 offline 結構接受閘。
    # 它擋掉 E2 揪出的空殼 stub(缺 RECORD_FIELDS、自報 host_sandbox、trust_tier/effect_enforcement 不符)。
    errors.extend(
        f"verifier command_capture_v2 invalid: {error}"
        for error in _cap.validate_governed_command_capture(capture)
    )
    if str(capture.get("record_digest")) != str(expected_digest):
        errors.append("verifier command_capture_v2 record_digest must equal the referenced capture digest")
    if evidence.get("observed_at") != capture.get("completed_at"):
        errors.append("verifier capture evidence observed_at must equal capture completion")
    for boundary in ("repository_before", "repository_after"):
        repository = capture.get(boundary)
        if (
            isinstance(repository, dict)
            and repository.get("source_head") != expected_source_head
        ):
            errors.append(
                f"verifier command_capture_v2 {boundary} source_head differs from effect source head"
            )
    # P1(Codex):capture 必須由「宣告的 postcheck 驗證者節點」產生——僅「非 applier」不足,否則任一
    # 無關的 read-only capture 都可被塞進來支撐偽造的 postcheck。綁 capturer node_id == 宣告 verifier node。
    if capture.get("node_id") != verifier_node:
        errors.append(
            "verifier command_capture_v2 node_id must equal the declared ops_postcheck verifier node "
            "(the capture must be produced by the purported residue verifier, not an unrelated node)"
        )
    if str(expected_digest) == str(applier_capture_digest):
        errors.append(
            "verifier capture must differ from the applier on-host capture (distinct process + capture)"
        )
    if capture.get("node_id") == applier_capture.get("node_id"):
        errors.append("verifier command_capture_v2 node_id must differ from the applier capture node_id")
    if capture.get("native_agent") == applier_capture.get("native_agent"):
        errors.append("verifier command_capture_v2 native_agent must differ from the applier capture native_agent")
    if capture.get("node_id") == applier_node:
        errors.append("verifier command_capture_v2 node_id must differ from the applier node")
    return errors


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
    verifier_capture_digest: str | None = None,
) -> dict[str, Any]:
    """Project one embedded target-host choice receipt into the dedicated effect result.

    ``applier_node_id`` / ``postcheck_verifier_node_id`` / ``target_host`` 皆由內嵌 receipt 派生
    (非自由參數);``effect_status`` 預設由 receipt 是否 PASS 且無 failure_reason 導出。
    ``verifier_capture_digest`` 是 distinct 驗證者的 governed on-host residue capture(command_capture_v2)
    的 record_digest:applier 自跑必為 ``None``(尚無獨立驗證者),經
    ``attach_distinct_verifier_postcheck`` 升 BINDING 時才由驗證者的相異 capture 派生填入。closure 端
    以此結構化欄位對「effect receipt / postcheck evidence / verifier capture」三者交叉綁定。
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
        "verifier_capture_digest": verifier_capture_digest,
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
        # 結構化 verifier_capture_digest 必與內嵌 seam 狀態一致:independent_postcheck 已由 distinct
        # 驗證者附掛(PASSED)⇒ 必為 sha256 且 == seam note 綁定的相異 capture digest;否則(applier 自跑,
        # DEFERRED)⇒ 必為 None。這讓「已升 BINDING」與結構化欄位/持久 note 綁定三者不可脫鉤。
        vcd = receipt.get("verifier_capture_digest")
        ip_verdict = _independent_postcheck_seam(choice).get("verdict")
        note_digest = _note_bound_verifier_capture_digest(choice)
        if ip_verdict == _th_choice.SEAM_VERDICT_PASSED:
            if not DIGEST_RE.fullmatch(str(vcd or "")):
                errors.append(
                    "target-host effect result with an attached (PASSED) independent_postcheck must "
                    "carry a sha256 verifier_capture_digest"
                )
            elif note_digest != vcd:
                errors.append(
                    "target-host effect result verifier_capture_digest must equal the distinct-verifier "
                    "capture digest durably bound into the independent_postcheck seam note"
                )
        elif vcd is not None:
            errors.append(
                "target-host effect result verifier_capture_digest must be null when the "
                "independent_postcheck is not an attached distinct-verifier PASS"
            )

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

    # ── P1(Codex):獨立驗證者 ops_postcheck 不能只憑 ``source==ops_postcheck`` 標籤過關。它必須綁定
    #    「驗證者自己產生並通過驗證的 command_capture_v2」,並與 effect receipt 的結構化
    #    ``verifier_capture_digest`` 及該 capture 三者 digest 交叉一致;applier 與 verifier 在
    #    role/node/process/capture 皆須相異;殘留必須全清(非零殘留 fail-closed);acceptance 必須同時
    #    綁 effect receipt + ops_postcheck + verifier capture 三份 evidence。
    choice = receipt.get("choice_receipt") if isinstance(receipt.get("choice_receipt"), dict) else {}
    applier_node = receipt.get("applier_node_id")
    applier_capture_digest = choice.get("target_host_capture_digest")
    applier_capture = choice.get("target_host_capture") if isinstance(choice.get("target_host_capture"), dict) else {}
    receipt_verifier_digest = receipt.get("verifier_capture_digest")

    fragment = fragments_by_node.get("ops_postcheck", {})
    postcheck_wrappers = [
        evidence_by_id[ref] for ref in fragment.get("evidence_refs", [])
        if ref in evidence_by_id
        and evidence_by_id[ref].get("scope") == "runtime"
        and evidence_by_id[ref].get("source") == "ops_postcheck"
        and evidence_by_id[ref].get("kind") == TARGET_HOST_OPS_POSTCHECK_KIND
    ]
    postcheck_wrapper = postcheck_wrappers[0] if len(postcheck_wrappers) == 1 else None
    postcheck = (
        postcheck_wrapper.get("artifact")
        if isinstance(postcheck_wrapper, dict)
        and isinstance(postcheck_wrapper.get("artifact"), dict)
        else None
    )
    verifier_capture_ev: dict[str, Any] | None = None
    if postcheck is None:
        errors.append("target-host closure requires exactly one independent ops_postcheck")
    else:
        if set(postcheck) != POSTCHECK_FIELDS:
            errors.append("target-host ops_postcheck artifact fields are not exact")
        if postcheck.get("schema_version") != TARGET_HOST_OPS_POSTCHECK_KIND:
            errors.append("target-host ops_postcheck schema_version is invalid")
        if postcheck.get("status") != "PASS":
            errors.append("target-host ops_postcheck status must be PASS")
        if postcheck.get("self_digest") != _postcheck_digest(postcheck):
            errors.append("target-host ops_postcheck self_digest is invalid")
        if postcheck_wrapper.get("digest") != postcheck.get("self_digest"):
            errors.append("target-host ops_postcheck wrapper digest differs from artifact")
        for field, expected in (
            ("host", receipt.get("target_host")),
            ("environment", TARGET_HOST_EFFECT_ENVIRONMENT),
            ("source", "ops_postcheck"),
            ("observed_at", postcheck.get("observed_at")),
            ("expiry", receipt.get("evidence_expires_at")),
        ):
            if postcheck_wrapper.get(field) != expected:
                errors.append(f"target-host ops_postcheck wrapper {field} is not receipt-bound")
        # (a) closure PASS 需要已升 BINDING 的 effect receipt:結構化 verifier_capture_digest 非空。
        if not DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")):
            errors.append(
                "target-host effect receipt lacks a bound verifier_capture_digest; a PASS closure requires "
                "the distinct-verifier-upgraded effect result (applier self-run alone cannot close)"
            )
        # (b) verifier node 為宣告的 postcheck 節點且 != applier。
        verifier_node = postcheck.get("verifier_node")
        if not (isinstance(verifier_node, str) and verifier_node):
            errors.append("target-host ops_postcheck must carry a non-empty verifier_node")
        elif verifier_node == applier_node:
            errors.append("target-host ops_postcheck verifier must differ from the applier node")
        elif verifier_node != receipt.get("postcheck_verifier_node_id"):
            errors.append(
                "target-host ops_postcheck verifier_node must equal the effect receipt postcheck_verifier_node_id"
            )
        # (c) ops_postcheck 綁 source_head / host / observed_at,且 residue 全清(非零殘留 fail-closed)。
        if postcheck.get("source_head") != receipt.get("source_head"):
            errors.append("target-host ops_postcheck source_head is not bound to the effect source head")
        if postcheck.get("host") != receipt.get("target_host"):
            errors.append("target-host ops_postcheck host is not bound to the effect target host")
        if not (isinstance(postcheck.get("observed_at"), str) and postcheck.get("observed_at")):
            errors.append("target-host ops_postcheck must carry an observation time (observed_at)")
        if not _is_clean_residue(postcheck.get("residue_observation")):
            errors.append(
                "target-host ops_postcheck must record a fully clean residue_observation "
                "(a nonzero/absent residue observation fails closed)"
            )
        # (d) ops_postcheck 攜帶的 verifier_capture_digest 與 effect receipt 結構化欄位一致。
        pc_capture_digest = postcheck.get("verifier_capture_digest")
        if not DIGEST_RE.fullmatch(str(pc_capture_digest or "")):
            errors.append("target-host ops_postcheck must reference a sha256 verifier capture digest")
        elif DIGEST_RE.fullmatch(str(receipt_verifier_digest or "")) and pc_capture_digest != receipt_verifier_digest:
            errors.append(
                "target-host ops_postcheck verifier_capture_digest must equal the effect receipt verifier_capture_digest"
            )
        # (e) verifier capture 為第三份 evidence:內嵌 command_capture_v2 通過驗證、digest 綁定,且
        #     capturer role/node/capture 與 applier 相異。
        cap_refs = [
            evidence_by_id[ref] for ref in postcheck.get("evidence_refs", [])
            if ref in evidence_by_id
            and evidence_by_id[ref].get("scope") == "runtime"
            and evidence_by_id[ref].get("kind") == TARGET_HOST_VERIFIER_CAPTURE_KIND
        ]
        if len(cap_refs) != 1:
            errors.append("target-host ops_postcheck must reference exactly one verifier command capture evidence")
        else:
            verifier_capture_ev = cap_refs[0]
            errors.extend(_validate_verifier_capture_evidence(
                verifier_capture_ev,
                expected_digest=pc_capture_digest,
                applier_capture_digest=applier_capture_digest,
                applier_capture=applier_capture,
                applier_node=applier_node,
                verifier_node=verifier_node,
                expected_host=receipt.get("target_host"),
                expected_source_head=receipt.get("source_head"),
                expected_expiry=receipt.get("evidence_expires_at"),
            ))

    # (f) acceptance PASS 必同時綁 effect receipt + ops_postcheck + verifier capture 三份 evidence id。
    required_ids = {receipt_id}
    if postcheck_wrapper is not None:
        required_ids.add(postcheck_wrapper.get("id"))
    if verifier_capture_ev is not None:
        required_ids.add(verifier_capture_ev.get("id"))
    accepted = (
        postcheck is not None
        and verifier_capture_ev is not None
        and any(
            item.get("status") == "PASS"
            and required_ids.issubset(set(item.get("evidence_refs", [])))
            for item in packet.get("acceptance", [])
        )
    )
    if not accepted:
        errors.append(
            "target-host passed acceptance must bind the effect receipt + independent ops_postcheck "
            "+ verifier capture"
        )
    if packet.get("side_effects", {}).get("runtime_contact") is not True:
        errors.append("target-host successful effect must record runtime_contact=true")
    if packet.get("disposition") != "CHANGED":
        errors.append("target-host successful effect closure must be CHANGED")
    return errors

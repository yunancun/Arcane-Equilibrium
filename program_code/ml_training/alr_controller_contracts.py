"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 ALR controller source-only offline P0/P1 contract。
主要函數：build_alr_work_item、build_alr_effect_review、
build_alr_loop_state_packet、validate_*、compute_*_hash、extract_*。
依賴：僅 Python 標準庫；不讀 DB、不連 runtime、不呼叫交易所、不讀
``_latest``、不做 proof/promotion/delete/apply/Cost Gate/order/probe/live/mainnet。
硬邊界：本模塊中的 runtime/db/pg/ipc/bybit/mcp/scheduler/service/env/latest/
proof/promotion/delete/apply/cost_gate/order/probe/live/mainnet 等字串只作
boundary-denial vocabulary，用來 fail-closed 掃描 authority expansion；不是
任何權限或執行路徑。
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any


BOUNDARY_LABEL = "SOURCE_ONLY_OFFLINE_P0_P1"

ALR_WORK_ITEM_FIELD = "alr_work_item"
ALR_EFFECT_REVIEW_FIELD = "alr_effect_review"
ALR_LOOP_STATE_PACKET_FIELD = "alr_loop_state_packet"

ALR_WORK_ITEM_SCHEMA_VERSION = "alr_work_item_v1"
ALR_EFFECT_REVIEW_SCHEMA_VERSION = "alr_effect_review_v1"
ALR_LOOP_STATE_PACKET_SCHEMA_VERSION = "alr_loop_state_packet_v1"

STATE_READY = "READY"
STATE_DEFERRED = "DEFERRED"
STATE_BLOCKED = "BLOCKED"
STATE_ROTATED = "ROTATED"
STATE_ACTIVE = "ACTIVE"
STATE_DONE = "DONE"
STATE_DONE_WITH_CONCERNS = "DONE_WITH_CONCERNS"
STATE_DEFERRED_P0 = "DEFERRED_P0"
_ALLOWED_STATES = {
    STATE_READY,
    STATE_DEFERRED,
    STATE_BLOCKED,
    STATE_ROTATED,
    STATE_ACTIVE,
    STATE_DONE,
    STATE_DONE_WITH_CONCERNS,
    STATE_DEFERRED_P0,
}

STATUS_READY = "READY"
STATUS_DEFER_EVIDENCE = "DEFER_EVIDENCE"
STATUS_ROTATED = "ROTATED"
STATUS_NO_EDGE = "NO_EDGE"
STATUS_RETENTION_RISK = "RETENTION_RISK"
STATUS_BOUNDARY_BLOCKED = "BOUNDARY_BLOCKED"
STATUS_ACTIVE = "ACTIVE"
STATUS_DONE = "DONE"
STATUS_DONE_WITH_CONCERNS = "DONE_WITH_CONCERNS"
STATUS_DEFERRED_P0 = "DEFERRED_P0"
_ALLOWED_STATUSES = {
    STATUS_READY,
    STATUS_DEFER_EVIDENCE,
    STATUS_ROTATED,
    STATUS_NO_EDGE,
    STATUS_RETENTION_RISK,
    STATUS_BOUNDARY_BLOCKED,
    STATUS_ACTIVE,
    STATUS_DONE,
    STATUS_DONE_WITH_CONCERNS,
    STATUS_DEFERRED_P0,
}

OUTCOME_ADVANCED = "ADVANCED"
OUTCOME_ADVANCED_WITH_CONCERNS = "ADVANCED_WITH_CONCERNS"
OUTCOME_DEFER_EVIDENCE = "DEFER_EVIDENCE"
OUTCOME_ROTATED = "ROTATED"
OUTCOME_STOP_NO_EDGE = "STOP_NO_EDGE"
OUTCOME_STOP_RETENTION_RISK = "STOP_RETENTION_RISK"
OUTCOME_BLOCKED_BOUNDARY = "BLOCKED_BOUNDARY"
_ALLOWED_OUTCOMES = {
    OUTCOME_ADVANCED,
    OUTCOME_ADVANCED_WITH_CONCERNS,
    OUTCOME_DEFER_EVIDENCE,
    OUTCOME_ROTATED,
    OUTCOME_STOP_NO_EDGE,
    OUTCOME_STOP_RETENTION_RISK,
    OUTCOME_BLOCKED_BOUNDARY,
}

BOUNDARY_VALIDATED = "BOUNDARY_VALIDATED"
BOUNDARY_VALIDATED_WITH_CONCERNS = "BOUNDARY_VALIDATED_WITH_CONCERNS"
_ALLOWED_BOUNDARY_STATUSES = {
    BOUNDARY_VALIDATED,
    BOUNDARY_VALIDATED_WITH_CONCERNS,
}

_HEX64_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_NO_AUTHORITY_CONCERN_RE = re.compile(
    r"(adr|amd).*?(not[_ -]?applied|no[_ -]?apply|text[_ -]?not[_ -]?applied)"
    r".*?(no[_ -]?governance[_ -]?authority|no[_ -]?authority)",
    re.IGNORECASE,
)
_TRUTHY_STRINGS = {
    "1",
    "true",
    "yes",
    "y",
    "on",
    "enabled",
    "enable",
    "grant",
    "granted",
    "allow",
    "allowed",
    "active",
    "approved",
    "present",
}
_FALSE_STRINGS = {
    "",
    "0",
    "false",
    "no",
    "n",
    "off",
    "disabled",
    "disable",
    "deny",
    "denied",
    "none",
    "null",
    "not_applicable",
    "n/a",
}
_AUTHORITY_TRUE_KEYS = set(
    """
    runtime runtime_allowed runtime_authority runtime_authority_granted
    runtime_mutation runtime_mutation_allowed runtime_mutation_performed
    db db_read db_read_allowed db_read_performed db_write db_write_allowed
    db_write_performed db_migration db_migration_allowed db_migration_performed
    pg pg_read_allowed pg_write_allowed ipc ipc_allowed ipc_authority_granted
    bybit bybit_allowed bybit_contact_performed mcp mcp_allowed mcp_server_started
    scheduler scheduler_allowed scheduler_enabled service service_allowed
    service_restart_allowed service_restart_performed env env_mutation_allowed
    env_mutation_performed latest latest_allowed latest_consumed latest_promotion_allowed
    proof proof_allowed proof_authority_granted promotion promotion_allowed
    promotion_authority_granted promotion_enabled delete delete_allowed
    delete_performed apply apply_allowed apply_performed cost_gate cost_gate_allowed
    cost_gate_change cost_gate_change_performed cost_gate_lowered
    cost_gate_lowering_allowed order order_allowed order_authority_granted
    order_or_probe_allowed order_or_probe_performed probe probe_allowed
    probe_authority_granted live live_allowed live_authority_granted live_enabled
    mainnet mainnet_allowed mainnet_enabled live_or_mainnet_performed
    exchange_contact_performed private_read_allowed private_read_performed
    trade_allowed trading_allowed trading_enabled enable_trading
    execution_authority_granted execution_permission_granted execution_allowed
    """.split()
)
_AUTHORITY_KEY_TERMS = tuple(
    """
    runtime db pg ipc bybit mcp scheduler service env latest proof promotion delete
    apply cost cost_gate order probe live mainnet exchange private trade trading
    execution
    """.split()
)
_AUTHORITY_ACTION_TERMS = tuple(
    """
    allow allowed author authority change consume consumed contact delete deploy enable
    enabled grant granted lower lowering mutate mutation perform performed promote
    promotion read reload restart start started touch use used write
    """.split()
)
_NO_AUTHORITY_KEYS = tuple(
    """
    runtime db pg ipc bybit mcp scheduler service env latest proof promotion delete
    apply cost_gate order probe live mainnet exchange_contact private_read
    runtime_mutation db_read db_write db_migration env_mutation service_restart
    order_or_probe live_or_mainnet
    """.split()
)
_EVIDENCE_BLOCKERS = {
    "evidence_blocked",
    "evidence_deferred",
    "defer_evidence",
    "deferred_queue",
    "missing_evidence",
}
_ROTATED_BLOCKERS = {"rotated", "source_hash_drift", "source_drift", "hash_drift"}
_NO_EDGE_BLOCKERS = {"no_edge", "stop_no_edge", "after_cost_edge_missing"}
_RETENTION_RISK_BLOCKERS = {
    "retention_risk",
    "stop_retention_risk",
    "retention_window_risk",
}
_OWNED_FILES = (
    "program_code/ml_training/alr_controller_contracts.py",
    "program_code/ml_training/tests/test_alr_controller_contracts.py",
)
_VERIFICATION_COMMANDS = (
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m py_compile "
    "program_code/ml_training/alr_controller_contracts.py",
    "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=program_code python3 -m pytest -q "
    "program_code/ml_training/tests/test_alr_controller_contracts.py -p no:cacheprovider",
)
_LOOP_REQUIRED_FIELDS = (
    "schema",
    "created_at",
    "repo_head_before",
    "repo_head_after",
    "selected_work_item",
    "selection_reason",
    "state",
    "next_state",
    "next_action",
    "stop_reason",
    "owned_files",
    "verification_commands",
    "candidate_matched_fills_count",
    "proof_packet_ready_count",
    "reward_ledger_ready_count",
    "effect_review_ready",
    "model_training_performed",
    "serving_authority_granted",
    "llm_authority",
    "runtime_authority",
    "exchange_authority",
    "trading_authority",
    "boundary_escalation_required",
    "dispatch_tooling_available",
    "dispatch_blocker",
)
_LOOP_FALSE_AUTHORITY_FIELDS = (
    "model_training_performed",
    "serving_authority_granted",
    "llm_authority",
    "runtime_authority",
    "exchange_authority",
    "trading_authority",
)


@dataclass(frozen=True)
class AlrContractValidation:
    """ALR source-only contract 驗證結果；invalid 一律 fail closed。"""

    valid: bool
    outcome: str
    reason: str
    reasons: tuple[str, ...]
    selected_work_item_id: str = ""
    boundary_label: str = BOUNDARY_LABEL
    authority_boundary_violation: bool = False


class AlrControllerContractError(ValueError):
    """Caller-provided source-only packet cannot be built safely."""


def extract_alr_work_item(mapping: Any) -> Any:
    """只讀 canonical ``alr_work_item`` 頂層欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(ALR_WORK_ITEM_FIELD)


def extract_alr_effect_review(mapping: Any) -> Any:
    """只讀 canonical ``alr_effect_review`` 頂層欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(ALR_EFFECT_REVIEW_FIELD)


def extract_alr_loop_state_packet(mapping: Any) -> Any:
    """只讀 canonical ``alr_loop_state_packet`` 頂層欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(ALR_LOOP_STATE_PACKET_FIELD)


def compute_alr_work_item_hash(packet: Mapping[str, Any]) -> str:
    """Canonical JSON sha256；只排除本 packet 頂層 ``work_item_hash``。"""
    return _hash_without_own_field(packet, "work_item_hash")


def compute_alr_effect_review_hash(packet: Mapping[str, Any]) -> str:
    """Canonical JSON sha256；只排除本 packet 頂層 ``review_hash``。"""
    return _hash_without_own_field(packet, "review_hash")


def compute_alr_loop_state_packet_hash(packet: Mapping[str, Any]) -> str:
    """Canonical JSON sha256；只排除本 packet 頂層 ``packet_hash``。"""
    return _hash_without_own_field(packet, "packet_hash")


def build_alr_work_item(
    *,
    work_item_id: str,
    row_id: str,
    title: str,
    state: str = STATE_READY,
    status: str = STATUS_READY,
    blockers: Sequence[str] | None = None,
    concerns: Sequence[str] | None = None,
    boundary_status: str = BOUNDARY_VALIDATED,
    boundary_label: str = BOUNDARY_LABEL,
    source_refs: Mapping[str, Any] | None = None,
    no_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """建立 canonical ``alr_work_item_v1``；所有輸入僅為 caller source data。"""
    _ensure_sequence("blockers", blockers or ())
    _ensure_sequence("concerns", concerns or ())
    if source_refs is not None and not isinstance(source_refs, Mapping):
        raise AlrControllerContractError("source_refs_not_mapping")
    packet: dict[str, Any] = {
        "schema_version": ALR_WORK_ITEM_SCHEMA_VERSION,
        "boundary_label": boundary_label,
        "work_item_id": str(work_item_id),
        "row_id": str(row_id),
        "title": str(title),
        "state": str(state),
        "status": str(status),
        "blockers": [str(item) for item in (blockers or [])],
        "concerns": [str(item) for item in (concerns or [])],
        "boundary_status": str(boundary_status),
        "source_refs": copy.deepcopy(dict(source_refs or {})),
        "no_authority": _no_authority_flags(no_authority),
    }
    packet["work_item_hash"] = compute_alr_work_item_hash(packet)
    validation = validate_alr_work_item(packet)
    if not validation.valid:
        raise AlrControllerContractError(validation.reason)
    return packet


def build_alr_effect_review(
    *,
    work_item: Mapping[str, Any],
    outcome: str | None = None,
    concerns: Sequence[str] | None = None,
    evidence_refs: Sequence[Mapping[str, Any]] | None = None,
    boundary_label: str = BOUNDARY_LABEL,
    no_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """建立 canonical ``alr_effect_review_v1``；不授予任何 apply/promotion authority。"""
    item_validation = validate_alr_work_item(work_item)
    selected_outcome = outcome or item_validation.outcome
    _ensure_sequence("concerns", concerns or ())
    if evidence_refs is not None:
        _ensure_sequence("evidence_refs", evidence_refs)
        if any(not isinstance(ref, Mapping) for ref in evidence_refs):
            raise AlrControllerContractError("evidence_ref_not_mapping")
    packet: dict[str, Any] = {
        "schema_version": ALR_EFFECT_REVIEW_SCHEMA_VERSION,
        "boundary_label": boundary_label,
        "work_item_ref": {
            "work_item_id": _text(work_item.get("work_item_id")),
            "row_id": _text(work_item.get("row_id")),
            "work_item_hash": compute_alr_work_item_hash(work_item),
        },
        "outcome": str(selected_outcome),
        "concerns": [str(item) for item in (concerns or work_item.get("concerns") or [])],
        "evidence_refs": [copy.deepcopy(dict(ref)) for ref in (evidence_refs or [])],
        "no_authority": _no_authority_flags(no_authority),
    }
    packet["review_hash"] = compute_alr_effect_review_hash(packet)
    validation = validate_alr_effect_review(packet)
    if not validation.valid:
        raise AlrControllerContractError(validation.reason)
    return packet


def build_alr_loop_state_packet(
    *,
    work_items: Sequence[Mapping[str, Any]],
    loop_id: str = "alr:source_only_offline_p0_p1",
    created_at: str = "source_only_offline",
    repo_head_before: str = "source_only_offline",
    repo_head_after: str = "source_only_offline",
    dispatch_tooling_available: bool = False,
    dispatch_blocker: str = "source_only_offline_no_dispatch_tooling",
    boundary_label: str = BOUNDARY_LABEL,
    no_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """建立 ``alr_loop_state_packet_v1``，selector 只取第一個 unblocked queue row。"""
    _ensure_sequence("work_items", work_items)
    items = [copy.deepcopy(dict(item)) for item in work_items]
    selected_item, outcome, reasons = select_first_unblocked_alr_row(items)
    selected_ref = _selected_ref(selected_item) if selected_item is not None else {}
    stop_reason = "" if outcome in {OUTCOME_ADVANCED, OUTCOME_ADVANCED_WITH_CONCERNS} else reasons[0]
    packet: dict[str, Any] = {
        "schema": ALR_LOOP_STATE_PACKET_SCHEMA_VERSION,
        "schema_version": ALR_LOOP_STATE_PACKET_SCHEMA_VERSION,
        "boundary_label": boundary_label,
        "loop_id": str(loop_id),
        "selector": "first_ready_without_blockers",
        "created_at": str(created_at),
        "repo_head_before": str(repo_head_before),
        "repo_head_after": str(repo_head_after),
        "work_items": items,
        "selected_work_item": selected_ref,
        "selection_reason": reasons[0],
        "state": "SELECTED" if selected_ref else "EMPTY",
        "next_state": _next_state(outcome),
        "next_action": _next_action(outcome),
        "stop_reason": stop_reason,
        "owned_files": list(_OWNED_FILES),
        "verification_commands": list(_VERIFICATION_COMMANDS),
        "candidate_matched_fills_count": 0,
        "proof_packet_ready_count": 0,
        "reward_ledger_ready_count": 0,
        "effect_review_ready": outcome in {OUTCOME_ADVANCED, OUTCOME_ADVANCED_WITH_CONCERNS},
        "model_training_performed": False,
        "serving_authority_granted": False,
        "llm_authority": False,
        "runtime_authority": False,
        "exchange_authority": False,
        "trading_authority": False,
        "boundary_escalation_required": outcome == OUTCOME_BLOCKED_BOUNDARY,
        "dispatch_tooling_available": bool(dispatch_tooling_available),
        "dispatch_blocker": str(dispatch_blocker),
        "outcome": outcome,
        "decision_reasons": list(reasons),
        "no_authority": _no_authority_flags(no_authority),
    }
    packet["packet_hash"] = compute_alr_loop_state_packet_hash(packet)
    validation = validate_alr_loop_state_packet(packet)
    if not validation.valid:
        raise AlrControllerContractError(validation.reason)
    return packet


def validate_alr_work_item(packet: Any) -> AlrContractValidation:
    """驗證 ``alr_work_item_v1``；任一 authority expansion 或 schema drift fail closed。"""
    if packet is None:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, "alr_work_item_missing")
    if not isinstance(packet, Mapping):
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, "alr_work_item_not_mapping")

    boundary_reasons = _boundary_reasons(packet)
    if boundary_reasons:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, boundary_reasons[0], boundary_reasons)

    reasons: list[str] = []
    loop_contract_reasons: list[str] = []
    if _text(packet.get("schema_version")) != ALR_WORK_ITEM_SCHEMA_VERSION:
        reasons.append("schema_version_unknown")
    if not _queue_state_allowed(_text(packet.get("state"))):
        reasons.append("state_unknown")
    if not _queue_status_allowed(_text(packet.get("status"))):
        reasons.append("status_unknown")
    if not _text(packet.get("work_item_id")):
        reasons.append("work_item_id_missing")
    if not _text(packet.get("row_id")):
        reasons.append("row_id_missing")
    if not _text(packet.get("title")):
        reasons.append("title_missing")
    reasons.extend(_list_reasons("blockers", packet.get("blockers")))
    reasons.extend(_list_reasons("concerns", packet.get("concerns")))
    boundary_status = _text(packet.get("boundary_status"))
    if boundary_status not in _ALLOWED_BOUNDARY_STATUSES:
        reasons.append("boundary_status_unknown")
    elif boundary_status == BOUNDARY_VALIDATED_WITH_CONCERNS and not _accepted_concerns(
        packet.get("concerns")
    ):
        reasons.append("boundary_concerns_not_accepted_no_authority_wording")
    if not isinstance(packet.get("source_refs"), Mapping):
        reasons.append("source_refs_not_mapping")
    reasons.extend(_no_authority_reasons(_mapping(packet.get("no_authority"))))
    reasons.extend(_hash_reasons(packet, "work_item_hash", compute_alr_work_item_hash))

    if reasons:
        return _result(False, _outcome_from_item(packet, boundary_valid=False), reasons[0], reasons)
    outcome, outcome_reasons = _item_outcome(packet)
    return _result(True, outcome, outcome_reasons[0], outcome_reasons, _text(packet.get("work_item_id")))


def validate_alr_effect_review(packet: Any) -> AlrContractValidation:
    """驗證 ``alr_effect_review_v1``；review outcome 仍只能是 source-only decision。"""
    if packet is None:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, "alr_effect_review_missing")
    if not isinstance(packet, Mapping):
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, "alr_effect_review_not_mapping")

    boundary_reasons = _boundary_reasons(packet)
    if boundary_reasons:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, boundary_reasons[0], boundary_reasons)

    reasons: list[str] = []
    if _text(packet.get("schema_version")) != ALR_EFFECT_REVIEW_SCHEMA_VERSION:
        reasons.append("schema_version_unknown")
    outcome = _text(packet.get("outcome"))
    if outcome not in _ALLOWED_OUTCOMES:
        reasons.append("outcome_unknown")
    concerns = packet.get("concerns")
    reasons.extend(_list_reasons("concerns", concerns))
    if outcome == OUTCOME_ADVANCED_WITH_CONCERNS and not _accepted_concerns(concerns):
        reasons.append("advanced_with_concerns_missing_no_authority_wording")
    work_item_ref = _mapping(packet.get("work_item_ref"))
    if not _text(work_item_ref.get("work_item_id")):
        reasons.append("work_item_ref_work_item_id_missing")
    if not _text(work_item_ref.get("row_id")):
        reasons.append("work_item_ref_row_id_missing")
    if not _is_hash(_text(work_item_ref.get("work_item_hash"))):
        reasons.append("work_item_ref_hash_malformed")
    reasons.extend(_list_reasons("evidence_refs", packet.get("evidence_refs")))
    if isinstance(packet.get("evidence_refs"), list):
        for ref in packet["evidence_refs"]:
            if not isinstance(ref, Mapping):
                reasons.append("evidence_ref_not_mapping")
    reasons.extend(_no_authority_reasons(_mapping(packet.get("no_authority"))))
    reasons.extend(_hash_reasons(packet, "review_hash", compute_alr_effect_review_hash))

    if reasons:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, reasons[0], reasons)
    return _result(True, outcome, "ok", (), _text(work_item_ref.get("work_item_id")))


def validate_alr_loop_state_packet(packet: Any) -> AlrContractValidation:
    """驗證 ``alr_loop_state_packet_v1`` 並重算 first-unblocked selector。"""
    if packet is None:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, "alr_loop_state_packet_missing")
    if not isinstance(packet, Mapping):
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, "alr_loop_state_packet_not_mapping")

    boundary_reasons = _boundary_reasons(packet)
    if boundary_reasons:
        return _result(False, OUTCOME_BLOCKED_BOUNDARY, boundary_reasons[0], boundary_reasons)

    reasons: list[str] = []
    if _text(packet.get("schema")) != ALR_LOOP_STATE_PACKET_SCHEMA_VERSION:
        reasons.append("schema_unknown")
    if _text(packet.get("schema_version")) != ALR_LOOP_STATE_PACKET_SCHEMA_VERSION:
        reasons.append("schema_version_unknown")
    if _text(packet.get("selector")) != "first_ready_without_blockers":
        reasons.append("selector_unknown")
    if not _text(packet.get("loop_id")):
        reasons.append("loop_id_missing")
    outcome = _text(packet.get("outcome"))
    if outcome not in _ALLOWED_OUTCOMES:
        reasons.append("outcome_unknown")
    loop_contract_reasons = _loop_contract_reasons(packet)
    reasons.extend(loop_contract_reasons)

    work_items_value = packet.get("work_items")
    if not isinstance(work_items_value, Sequence) or isinstance(
        work_items_value, (str, bytes, bytearray)
    ):
        reasons.append("work_items_not_sequence")
        work_items: list[Mapping[str, Any]] = []
    else:
        work_items = [item for item in work_items_value if isinstance(item, Mapping)]
        if len(work_items) != len(work_items_value):
            reasons.append("work_item_not_mapping")

    for index, item in enumerate(work_items):
        validation = validate_alr_work_item(item)
        if not validation.valid:
            reasons.append(f"work_items[{index}]:{validation.reason}")
            if validation.authority_boundary_violation:
                return _result(
                    False,
                    OUTCOME_BLOCKED_BOUNDARY,
                    reasons[0],
                    reasons,
                    authority_boundary_violation=True,
                )

    selected_item, expected_outcome, expected_reasons = select_first_unblocked_alr_row(
        work_items
    )
    expected_selected = _selected_ref(selected_item) if selected_item is not None else {}
    if _mapping(packet.get("selected_work_item")) != expected_selected:
        reasons.append("selected_work_item_mismatch")
    if outcome != expected_outcome:
        reasons.append("outcome_mismatch")
    if _text(packet.get("selection_reason")) != (expected_reasons[0] if expected_reasons else ""):
        reasons.append("selection_reason_mismatch")
    if tuple(str(item) for item in packet.get("decision_reasons", ())) != expected_reasons:
        reasons.append("decision_reasons_mismatch")

    reasons.extend(_no_authority_reasons(_mapping(packet.get("no_authority"))))
    reasons.extend(_hash_reasons(packet, "packet_hash", compute_alr_loop_state_packet_hash))

    selected_id = _text(expected_selected.get("work_item_id"))
    if reasons:
        failed_outcome = (
            OUTCOME_BLOCKED_BOUNDARY
            if loop_contract_reasons
            else expected_outcome
        )
        return _result(False, failed_outcome, reasons[0], reasons, selected_id)
    return _result(True, expected_outcome, "ok", (), selected_id)


def select_first_unblocked_alr_row(
    work_items: Sequence[Mapping[str, Any]],
) -> tuple[Mapping[str, Any] | None, str, tuple[str, ...]]:
    """Return first selectable queue item, else the first fail-closed queue outcome."""
    first_blocked_outcome: tuple[Mapping[str, Any], str, tuple[str, ...]] | None = None
    for item in work_items:
        validation = validate_alr_work_item(item)
        if not validation.valid:
            return item, OUTCOME_BLOCKED_BOUNDARY, (validation.reason,)
        outcome, reasons = _item_outcome(item)
        if reasons == ("done_row_skipped",):
            continue
        if outcome in {OUTCOME_ADVANCED, OUTCOME_ADVANCED_WITH_CONCERNS}:
            return item, outcome, reasons
        if first_blocked_outcome is None:
            first_blocked_outcome = (item, outcome, reasons)
    if first_blocked_outcome is not None:
        return first_blocked_outcome
    return None, OUTCOME_DEFER_EVIDENCE, ("queue_empty",)


def _item_outcome(item: Mapping[str, Any]) -> tuple[str, tuple[str, ...]]:
    if _is_done_row(item):
        return OUTCOME_DEFER_EVIDENCE, ("done_row_skipped",)
    outcome = _outcome_from_item(item, boundary_valid=True)
    if outcome == OUTCOME_ADVANCED_WITH_CONCERNS:
        return outcome, ("ready_with_accepted_boundary_concerns",)
    if outcome == OUTCOME_ADVANCED:
        if _queue_value_startswith(item, "WAITING_"):
            return outcome, ("waiting_conditions_satisfied",)
        if _queue_value_is(item, STATUS_ACTIVE):
            return outcome, ("active_without_blockers",)
        return outcome, ("ready_without_blockers",)
    normalized_blockers = _normalized_blockers(item)
    reason = sorted(normalized_blockers)[0] if normalized_blockers else _text(item.get("status"))
    return outcome, (reason or "blocked",)


def _outcome_from_item(item: Mapping[str, Any], *, boundary_valid: bool) -> str:
    if not boundary_valid:
        return OUTCOME_BLOCKED_BOUNDARY
    state = _text(item.get("state"))
    status = _text(item.get("status"))
    blockers = _normalized_blockers(item)
    if _is_done_row(item):
        return OUTCOME_DEFER_EVIDENCE
    if blockers & _ROTATED_BLOCKERS or state == STATE_ROTATED or status == STATUS_ROTATED:
        return OUTCOME_ROTATED
    if blockers & _NO_EDGE_BLOCKERS or status == STATUS_NO_EDGE:
        return OUTCOME_STOP_NO_EDGE
    if blockers & _RETENTION_RISK_BLOCKERS or status == STATUS_RETENTION_RISK:
        return OUTCOME_STOP_RETENTION_RISK
    if (
        blockers & _EVIDENCE_BLOCKERS
        or state == STATE_DEFERRED
        or status == STATUS_DEFER_EVIDENCE
        or state == STATE_DEFERRED_P0
        or status == STATUS_DEFERRED_P0
        or state == STATE_BLOCKED
    ):
        return OUTCOME_DEFER_EVIDENCE
    if _queue_value_startswith(item, "WAITING_") and not _waiting_conditions_satisfied(item):
        return OUTCOME_DEFER_EVIDENCE
    if (
        (state in {STATE_READY, STATE_ACTIVE} or status in {STATUS_READY, STATUS_ACTIVE})
        or (_queue_value_startswith(item, "WAITING_") and _waiting_conditions_satisfied(item))
    ) and not blockers:
        if _text(item.get("boundary_status")) == BOUNDARY_VALIDATED_WITH_CONCERNS:
            return OUTCOME_ADVANCED_WITH_CONCERNS
        return OUTCOME_ADVANCED
    return OUTCOME_DEFER_EVIDENCE


def _boundary_reasons(packet: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if _text(packet.get("boundary_label")) != BOUNDARY_LABEL:
        reasons.append("boundary_label_mismatch")
    authority_violations = _authority_violations(packet)
    if authority_violations:
        reasons.extend(f"authority_boundary_violation:{item}" for item in authority_violations)
    return reasons


def _loop_contract_reasons(packet: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for field in _LOOP_REQUIRED_FIELDS:
        if field not in packet:
            reasons.append(f"{field}_missing")
    for field in ("created_at", "repo_head_before", "repo_head_after", "state", "next_state", "next_action"):
        if field in packet and not _text(packet.get(field)):
            reasons.append(f"{field}_missing")
    if "stop_reason" in packet and not isinstance(packet.get("stop_reason"), str):
        reasons.append("stop_reason_not_string")
    if "dispatch_blocker" in packet and not isinstance(packet.get("dispatch_blocker"), str):
        reasons.append("dispatch_blocker_not_string")
    for field in ("owned_files", "verification_commands"):
        value = packet.get(field)
        if not isinstance(value, list) or any(not _text(item) for item in value):
            reasons.append(f"{field}_invalid")
    for field in (
        "candidate_matched_fills_count",
        "proof_packet_ready_count",
        "reward_ledger_ready_count",
    ):
        value = packet.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            reasons.append(f"{field}_invalid")
    for field in (
        "effect_review_ready",
        "boundary_escalation_required",
        "dispatch_tooling_available",
    ):
        if field in packet and not isinstance(packet.get(field), bool):
            reasons.append(f"{field}_not_bool")
    for field in _LOOP_FALSE_AUTHORITY_FIELDS:
        if packet.get(field) is not False:
            reasons.append(f"{field}_not_false")
    return reasons


def _queue_state_allowed(value: str) -> bool:
    return value in _ALLOWED_STATES or value.startswith("WAITING_")


def _queue_status_allowed(value: str) -> bool:
    return value in _ALLOWED_STATUSES or value.startswith("WAITING_")


def _queue_value_is(item: Mapping[str, Any], value: str) -> bool:
    return _text(item.get("state")) == value or _text(item.get("status")) == value


def _queue_value_startswith(item: Mapping[str, Any], prefix: str) -> bool:
    return _text(item.get("state")).startswith(prefix) or _text(item.get("status")).startswith(prefix)


def _is_done_row(item: Mapping[str, Any]) -> bool:
    return _queue_value_is(item, STATE_DONE) or _queue_value_is(item, STATE_DONE_WITH_CONCERNS)


def _waiting_conditions_satisfied(item: Mapping[str, Any]) -> bool:
    conditions = item.get("conditions")
    waiting_conditions = item.get("waiting_conditions")
    if isinstance(conditions, Mapping):
        if conditions.get("satisfied") is True:
            return True
        items = conditions.get("items")
        if isinstance(items, Sequence) and not isinstance(items, (str, bytes, bytearray)):
            return bool(items) and all(
                isinstance(entry, Mapping) and entry.get("satisfied") is True
                for entry in items
            )
    if isinstance(waiting_conditions, Mapping):
        if waiting_conditions.get("satisfied") is True:
            return True
    return item.get("conditions_satisfied") is True


def _authority_violations(value: Any, path: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            norm = _normalized_key(key_text)
            child_path = f"{path}.{key_text}"
            if not norm.startswith(("no_", "not_", "deny_", "denial_")):
                if _is_authority_expansion_key(norm) and _authority_value_grants(child):
                    violations.append(child_path)
            violations.extend(_authority_violations(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            violations.extend(_authority_violations(child, f"{path}[{index}]"))
    return sorted(set(violations))


def _is_authority_expansion_key(norm_key: str) -> bool:
    if norm_key in _AUTHORITY_TRUE_KEYS:
        return True
    if norm_key in _AUTHORITY_KEY_TERMS:
        return True
    has_authority_term = any(term in norm_key for term in _AUTHORITY_KEY_TERMS)
    has_authority_action = any(action in norm_key for action in _AUTHORITY_ACTION_TERMS)
    return has_authority_term and has_authority_action


def _authority_value_grants(value: Any) -> bool:
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in _FALSE_STRINGS:
            return False
        return normalized in _TRUTHY_STRINGS
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and float(value) != 0.0
    if isinstance(value, Mapping):
        return any(_authority_value_grants(child) for child in value.values())
    if isinstance(value, list):
        return any(_authority_value_grants(child) for child in value)
    return value is not None


def _no_authority_flags(overrides: Mapping[str, Any] | None) -> dict[str, Any]:
    flags: dict[str, Any] = {key: False for key in _NO_AUTHORITY_KEYS}
    if overrides:
        flags.update(copy.deepcopy(dict(overrides)))
    return flags


def _no_authority_reasons(no_authority: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in _NO_AUTHORITY_KEYS:
        if key not in no_authority:
            reasons.append(f"no_authority_{key}_missing")
        elif not _explicitly_denied(no_authority.get(key)):
            reasons.append(f"no_authority_{key}_not_denied")
    return reasons


def _explicitly_denied(value: Any) -> bool:
    if value is False or value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() in _FALSE_STRINGS
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return math.isfinite(float(value)) and float(value) == 0.0
    return False


def _hash_without_own_field(packet: Mapping[str, Any], field: str) -> str:
    payload = copy.deepcopy(dict(packet))
    payload.pop(field, None)
    return _stable_sha256_json(payload)


def _hash_reasons(
    packet: Mapping[str, Any],
    field: str,
    compute_hash,
) -> list[str]:
    value = _text(packet.get(field))
    if not value:
        return [f"{field}_missing"]
    if not _is_hash(value):
        return [f"{field}_malformed"]
    try:
        computed = compute_hash(packet)
    except (TypeError, ValueError):
        return [f"{field}_uncomputable"]
    if _strip_hash(value) != computed:
        return [f"{field}_mismatch"]
    return []


def _selected_ref(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        "work_item_id": _text(item.get("work_item_id")),
        "row_id": _text(item.get("row_id")),
        "work_item_hash": compute_alr_work_item_hash(item),
    }


def _normalized_blockers(item: Mapping[str, Any]) -> set[str]:
    blockers = item.get("blockers")
    if not isinstance(blockers, Sequence) or isinstance(blockers, (str, bytes, bytearray)):
        return set()
    return {_normalized_key(str(blocker)) for blocker in blockers if _text(blocker)}


def _accepted_concerns(value: Any) -> bool:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return False
    nonblank = [str(item) for item in value if _text(item)]
    return bool(nonblank) and all(_accepted_concern(item) for item in nonblank)


def _accepted_concern(value: str) -> bool:
    normalized = _normalized_key(value)
    has_adr_amd = "adr" in normalized or "amd" in normalized
    has_not_applied = (
        "not_applied" in normalized
        or "no_apply" in normalized
        or "no_applied" in normalized
    )
    has_no_authority = (
        "no_governance_authority" in normalized
        or "no_authority" in normalized
        or "no_governance" in normalized and "authority" in normalized
    )
    return has_adr_amd and has_not_applied and has_no_authority


def _next_state(outcome: str) -> str:
    if outcome in {OUTCOME_ADVANCED, OUTCOME_ADVANCED_WITH_CONCERNS}:
        return "READY_FOR_NEXT_SOURCE_ONLY_ROW"
    if outcome == OUTCOME_ROTATED:
        return "ROTATED"
    if outcome in {OUTCOME_STOP_NO_EDGE, OUTCOME_STOP_RETENTION_RISK}:
        return "STOPPED"
    if outcome == OUTCOME_BLOCKED_BOUNDARY:
        return "BLOCKED_BOUNDARY"
    return "DEFERRED_EVIDENCE"


def _next_action(outcome: str) -> str:
    if outcome in {OUTCOME_ADVANCED, OUTCOME_ADVANCED_WITH_CONCERNS}:
        return "advance_selected_work_item_source_only"
    if outcome == OUTCOME_ROTATED:
        return "rotate_source_only_queue"
    if outcome == OUTCOME_STOP_NO_EDGE:
        return "stop_no_edge_source_only"
    if outcome == OUTCOME_STOP_RETENTION_RISK:
        return "stop_retention_risk_source_only"
    if outcome == OUTCOME_BLOCKED_BOUNDARY:
        return "escalate_boundary_blocker"
    return "defer_until_evidence_available"


def _list_reasons(field: str, value: Any) -> list[str]:
    if not isinstance(value, list):
        return [f"{field}_not_list"]
    if any(not _text(item) for item in value):
        return [f"{field}_contains_blank"]
    return []


def _ensure_sequence(name: str, value: Any) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise AlrControllerContractError(f"{name}_not_sequence")


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def _normalized_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.strip().lower()).strip("_")


def _is_hash(value: str) -> bool:
    return bool(_HEX64_RE.fullmatch(_text(value)))


def _strip_hash(value: str) -> str:
    text = _text(value)
    return text[7:] if text.startswith("sha256:") else text


def _stable_sha256_json(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result(
    valid: bool,
    outcome: str,
    reason: str,
    reasons: Sequence[str] | None = None,
    selected_work_item_id: str = "",
    *,
    authority_boundary_violation: bool = False,
) -> AlrContractValidation:
    all_reasons = tuple(reasons or (() if reason == "ok" else (reason,)))
    return AlrContractValidation(
        valid=valid,
        outcome=outcome,
        reason=reason,
        reasons=all_reasons,
        selected_work_item_id=selected_work_item_id,
        authority_boundary_violation=authority_boundary_violation
        or any(item.startswith("authority_boundary_violation:") for item in all_reasons),
    )

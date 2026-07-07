"""
MODULE_NOTE
模塊用途：AI/ML roadmap 的 learning_effect_review_v1 source-only stop-loop contract。
主要函數：build_learning_effect_review_packet、validate_learning_effect_review、
compute_learning_effect_review_hash、extract_learning_effect_review。
依賴：僅 Python 標準庫與 reward_ledger source-only validator；不讀 DB、
不連 runtime、不呼叫交易所。
硬邊界：本模塊只產生 review-only 決策包；不可授予 promotion、order、
probe、Cost Gate、runtime、live/mainnet、model reload 或 symlink authority。
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

from .reward_ledger import (
    REWARD_RECORD_READY,
    compute_reward_record_hash,
    validate_reward_batch,
    validate_reward_record,
)


LEARNING_EFFECT_REVIEW_FIELD = "learning_effect_review"
LEARNING_EFFECT_REVIEW_SCHEMA_VERSION = "learning_effect_review_v1"

DECISION_CONTINUE = "continue"
DECISION_ROLLBACK = "rollback"
DECISION_ROTATE_CANDIDATE = "rotate_candidate"
DECISION_STOP_LOSS_CONTROL = "stop_loss_control"
DECISION_STOP_NO_EDGE = "stop_no_edge"
DECISION_STOP_EVIDENCE = "stop_evidence"
DECISION_PROMOTE_REVIEW_ONLY = "promote_review_only"

_ALLOWED_DECISIONS = {
    DECISION_CONTINUE,
    DECISION_ROLLBACK,
    DECISION_ROTATE_CANDIDATE,
    DECISION_STOP_LOSS_CONTROL,
    DECISION_STOP_NO_EDGE,
    DECISION_STOP_EVIDENCE,
    DECISION_PROMOTE_REVIEW_ONLY,
}
_HEX64_RE = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$")
_TRUTHY_STRINGS = {"1", "true", "yes", "y", "on", "enabled", "grant", "granted"}
_FALSE_STRINGS = {"", "0", "false", "no", "n", "off", "disabled", "deny", "denied", "none", "null"}
_AUTHORITY_TRUE_KEYS = set(
    """
    cost_gate_change cost_gate_change_performed cost_gate_lowered
    cost_gate_lowering_allowed db_migration_allowed db_migration_performed
    db_read_allowed db_read_performed db_write_allowed db_write_performed
    deploy_allowed deploy_performed exchange_contact_performed
    exchange_private_read_performed live_allowed live_authority_granted live_enabled
    live_or_mainnet_performed mainnet_allowed mainnet_enabled mcp_server_started
    model_reload model_reload_allowed model_reload_performed order_allowed
    order_authority_granted order_or_probe_allowed order_or_probe_performed
    private_read_allowed private_read_performed probe_allowed
    probe_authority_granted promotion_allowed promotion_authority_granted
    promotion_enabled runtime_mutation_allowed runtime_mutation_performed
    secret_access_allowed secret_access_performed serving_reload_allowed
    serving_reload_performed symlink_promotion_allowed symlink_promotion_performed
    trade_allowed trading_allowed trading_enabled enable_trading
    execution_authority_granted execution_permission_granted execution_allowed
    """.split()
)
_AUTHORITY_KEY_TERMS = tuple(
    "cost cost_gate db deploy exchange execution live mainnet mcp model order private "
    "probe promotion runtime secret serving symlink trade trading".split()
)
_AUTHORITY_ACTION_TERMS = tuple(
    "allow allowed author change deploy enable enabled grant granted lower "
    "lowering mutat perform performed reload start started write".split()
)
_AUTHORITY_ACTION_TOKENS = {"read"}
_NO_AUTHORITY_KEYS = tuple(
    "runtime_mutation db_read db_write db_migration exchange_contact private_read "
    "secret_access order_or_probe cost_gate_change deploy live_or_mainnet promotion "
    "model_reload serving_reload symlink_promotion".split()
)
_CANDIDATE_FIELDS = ("candidate_id", "strategy_name", "symbol", "side")


@dataclass(frozen=True)
class LearningEffectReviewValidation:
    """Learning effect review 驗證結果；所有決策都維持 review-only。"""

    valid: bool
    decision: str
    reason: str
    reasons: tuple[str, ...]
    review_only: bool = True
    authority_boundary_violation: bool = False


class LearningEffectReviewError(ValueError):
    """Caller-provided source artifacts cannot build a review packet."""


def extract_learning_effect_review(mapping: Any) -> Any:
    """只讀 canonical ``learning_effect_review`` 欄位，不接受 alias。"""
    if not isinstance(mapping, Mapping):
        return None
    return mapping.get(LEARNING_EFFECT_REVIEW_FIELD)


def compute_learning_effect_review_hash(packet: Mapping[str, Any]) -> str:
    """對 review packet 做 canonical JSON sha256；頂層 ``review_hash`` 不入 hash。"""
    payload = copy.deepcopy(dict(packet))
    payload.pop("review_hash", None)
    return _stable_sha256_json(payload)


def build_learning_effect_review_packet(
    *,
    reward_records: Sequence[Mapping[str, Any]],
    loss_limits: Mapping[str, Any],
    controls: Mapping[str, Any],
    oos_repeat_tags: Mapping[str, Any],
    acceptance_report_refs: Sequence[Mapping[str, Any]] | None = None,
    review_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """從 caller 提供的 reward_ledger_v1 records 建立 review-only stop-loop packet。"""
    if not isinstance(reward_records, Sequence) or isinstance(
        reward_records, (str, bytes, bytearray)
    ):
        raise LearningEffectReviewError("reward_records_not_sequence")
    records = [copy.deepcopy(dict(record)) for record in reward_records]
    if not records:
        raise LearningEffectReviewError("reward_records_missing")

    batch_validation = validate_reward_batch(records)
    if not batch_validation.reward_ready:
        raise LearningEffectReviewError(batch_validation.reason)

    for name, value in (
        ("loss_limits", loss_limits),
        ("controls", controls),
        ("oos_repeat_tags", oos_repeat_tags),
        ("review_policy", review_policy or {}),
    ):
        if not isinstance(value, Mapping):
            raise LearningEffectReviewError(f"{name}_not_mapping")

    acceptance_refs = [copy.deepcopy(dict(ref)) for ref in (acceptance_report_refs or [])]
    policy = dict(review_policy or {})
    candidate = _candidate_from_records(records)
    if candidate is None:
        raise LearningEffectReviewError("mixed_candidate_identity")

    reward_refs = []
    proof_refs: list[str] = []
    mutation_refs: list[str] = []
    for record in records:
        record_hash = compute_reward_record_hash(record)
        reward_refs.append({"record_id": str(record["record_id"]), "record_hash": record_hash})
        lineage = _mapping(record.get("lineage"))
        proof_hash = _strip_hash(_text(lineage.get("proof_packet_hash")))
        mutation_hash = _strip_hash(_text(lineage.get("mutation_envelope_hash")))
        if proof_hash:
            proof_refs.append(proof_hash)
        if mutation_hash:
            mutation_refs.append(mutation_hash)

    acceptance_normalized = [_normalize_acceptance_report_ref(ref) for ref in acceptance_refs]
    metrics = _effect_metrics(records, controls, oos_repeat_tags)
    packet: dict[str, Any] = {
        "schema_version": LEARNING_EFFECT_REVIEW_SCHEMA_VERSION,
        "review_id": f"effect:{candidate['candidate_id']}:{_stable_sha256_json(reward_refs)[:16]}",
        "review_only": True,
        "decision": DECISION_STOP_EVIDENCE,
        "decision_reasons": [],
        "candidate_identity": candidate,
        "inputs": {
            "reward_ledger_refs": reward_refs,
            "proof_packet_refs": sorted(set(proof_refs)),
            "mutation_envelope_refs": sorted(set(mutation_refs)),
            "acceptance_report_refs": acceptance_normalized,
        },
        "effect_metrics": metrics,
        "controls": copy.deepcopy(dict(controls)),
        "loss_limits": copy.deepcopy(dict(loss_limits)),
        "oos_repeat_tags": copy.deepcopy(dict(oos_repeat_tags)),
        "review_policy": policy,
        "source_artifacts": {"reward_records": records},
        "no_authority": _review_only_no_authority(),
    }
    decision, reasons, _ = _decide(packet)
    packet["decision"] = decision
    packet["decision_reasons"] = reasons
    packet["review_hash"] = compute_learning_effect_review_hash(packet)
    return packet


def validate_learning_effect_review(packet: Any) -> LearningEffectReviewValidation:
    """驗證 ``learning_effect_review_v1`` packet 並重算 fail-closed 決策。"""
    if packet is None:
        return _result(False, DECISION_STOP_EVIDENCE, "learning_effect_review_missing")
    if not isinstance(packet, Mapping):
        return _result(False, DECISION_STOP_EVIDENCE, "learning_effect_review_not_mapping")

    authority_violations = _authority_violations(packet)
    if authority_violations:
        return _result(
            False,
            DECISION_STOP_EVIDENCE,
            f"authority_boundary_violation:{authority_violations[0]}",
            tuple(f"authority_boundary_violation:{item}" for item in authority_violations),
            authority_boundary_violation=True,
        )

    structural_reasons: list[str] = []
    if _text(packet.get("schema_version")) != LEARNING_EFFECT_REVIEW_SCHEMA_VERSION:
        structural_reasons.append("schema_version_unknown")
    if packet.get("review_only") is not True:
        structural_reasons.append("review_only_not_true")
    if _text(packet.get("decision")) not in _ALLOWED_DECISIONS:
        structural_reasons.append("decision_unknown")
    structural_reasons.extend(_no_authority_reasons(_mapping(packet.get("no_authority"))))

    review_hash = _text(packet.get("review_hash"))
    if not review_hash:
        structural_reasons.append("review_hash_missing")
    elif not _is_hash(review_hash):
        structural_reasons.append("review_hash_malformed")
    else:
        try:
            computed_hash = compute_learning_effect_review_hash(packet)
        except (TypeError, ValueError):
            structural_reasons.append("review_hash_uncomputable")
        else:
            if _strip_hash(review_hash) != computed_hash:
                structural_reasons.append("review_hash_mismatch")

    decision, reasons, structurally_valid_decision = _decide(packet)
    if _text(packet.get("decision")) != decision:
        structural_reasons.append("decision_mismatch")
    declared_reasons = tuple(str(item) for item in packet.get("decision_reasons", ()))
    if declared_reasons != reasons:
        structural_reasons.append("decision_reasons_mismatch")

    if structural_reasons:
        return _result(False, decision, structural_reasons[0], structural_reasons)
    return _result(structurally_valid_decision, decision, reasons[0], reasons)


def _decide(packet: Mapping[str, Any]) -> tuple[str, tuple[str, ...], bool]:
    records = _reward_records(packet)
    batch_reasons, batch_authority_violation = _reward_batch_reasons(records)
    if batch_authority_violation:
        return DECISION_STOP_EVIDENCE, tuple(batch_reasons), False
    if batch_reasons:
        return DECISION_STOP_EVIDENCE, tuple(batch_reasons), False

    loss_reasons = _loss_limit_reasons(records, _mapping(packet.get("loss_limits")))
    if loss_reasons:
        return DECISION_STOP_LOSS_CONTROL, tuple(loss_reasons), True

    evidence_reasons = _evidence_reasons(packet, records)
    if evidence_reasons:
        return DECISION_STOP_EVIDENCE, tuple(evidence_reasons), True

    policy = _mapping(packet.get("review_policy"))
    metrics = _mapping(packet.get("effect_metrics"))
    min_sample_count = int(_number(policy.get("min_sample_count")) or 1)
    sample_count = int(_number(metrics.get("sample_count")) or 0)
    if sample_count < min_sample_count:
        return DECISION_STOP_EVIDENCE, ("sample_count_below_minimum",), True

    mutation_status = _text(metrics.get("mutation_effect_status")).lower()
    control_outperformance = _number(metrics.get("control_outperformance_bps"))
    if mutation_status == "failed":
        return DECISION_ROLLBACK, ("mutation_effect_failed",), True
    if (
        _bool(policy.get("control_outperformance_required"), default=True)
        and control_outperformance is not None
        and control_outperformance < 0
    ):
        return DECISION_ROLLBACK, ("control_outperformance_negative",), True

    net_bps_sum = float(_number(metrics.get("net_pnl_bps_sum")) or 0.0)
    edge_floor_bps = float(_number(policy.get("edge_floor_bps")) or 0.0)
    if net_bps_sum < 0:
        return DECISION_STOP_NO_EDGE, ("after_cost_ev_negative",), True
    if net_bps_sum <= edge_floor_bps:
        if _bool(policy.get("rotate_candidate_allowed"), default=False):
            return DECISION_ROTATE_CANDIDATE, ("after_cost_edge_below_floor_rotate",), True
        return DECISION_STOP_NO_EDGE, ("after_cost_edge_below_floor",), True

    if (
        _bool(policy.get("repeat_required_for_promotion"), default=True)
        and _bool(metrics.get("repeat_status") == "passed", default=False) is False
    ):
        return DECISION_CONTINUE, ("positive_after_cost_repeat_not_ready",), True

    return (
        DECISION_PROMOTE_REVIEW_ONLY,
        ("profitable_after_cost_repeat_ready_for_operator_review",),
        True,
    )


def _reward_batch_reasons(records: Sequence[Mapping[str, Any]]) -> tuple[list[str], bool]:
    if not records:
        return ["reward_records_missing"], False
    batch_validation = validate_reward_batch(records)
    if not batch_validation.reward_ready:
        return [batch_validation.reason, *batch_validation.reasons], (
            batch_validation.authority_boundary_violation
        )
    ready_records = [
        record
        for record in records
        if _text(record.get("verdict")) == REWARD_RECORD_READY
        and validate_reward_record(record).reward_ready
    ]
    if not ready_records:
        return ["no_reward_record_ready_records"], False
    if _candidate_from_records(records) is None:
        return ["mixed_candidate_identity"], False
    return [], False


def _loss_limit_reasons(
    records: Sequence[Mapping[str, Any]],
    loss_limits: Mapping[str, Any],
) -> list[str]:
    if not loss_limits:
        return ["loss_limits_missing"]
    if _truthy_breach(loss_limits):
        return ["loss_limits_explicit_breach"]
    required_fields = (
        "max_cumulative_loss_bps",
        "max_cumulative_loss_usdt",
        "max_single_record_loss_bps",
        "max_consecutive_negative_windows",
        "breach",
    )
    missing_fields = [field for field in required_fields if field not in loss_limits]
    if missing_fields:
        return [f"loss_limits_{missing_fields[0]}_missing"]
    net_bps_values = [_reward_number(record, "net_pnl_bps") or 0.0 for record in records]
    net_usdt_values = [_reward_number(record, "net_pnl_usdt") or 0.0 for record in records]
    if not net_bps_values:
        return ["loss_limits_no_reward_values"]
    max_cumulative_loss_bps = _number(loss_limits.get("max_cumulative_loss_bps"))
    max_cumulative_loss_usdt = _number(loss_limits.get("max_cumulative_loss_usdt"))
    max_single_loss_bps = _number(loss_limits.get("max_single_record_loss_bps"))
    max_consecutive_negative = _integer(loss_limits.get("max_consecutive_negative_windows"))
    if (
        max_cumulative_loss_bps is None
        or max_cumulative_loss_usdt is None
        or max_single_loss_bps is None
        or max_consecutive_negative is None
        or not isinstance(loss_limits.get("breach"), bool)
    ):
        return ["loss_limits_malformed"]
    if sum(net_bps_values) < -abs(float(max_cumulative_loss_bps)):
        return ["cumulative_loss_bps_breached"]
    if sum(net_usdt_values) < -abs(float(max_cumulative_loss_usdt)):
        return ["cumulative_loss_usdt_breached"]
    if min(net_bps_values) < -abs(float(max_single_loss_bps)):
        return ["single_record_loss_bps_breached"]
    if _max_consecutive_negative(net_bps_values) > max_consecutive_negative:
        return ["consecutive_negative_windows_breached"]
    return []


def _evidence_reasons(packet: Mapping[str, Any], records: Sequence[Mapping[str, Any]]) -> list[str]:
    reasons: list[str] = []
    inputs = _mapping(packet.get("inputs"))
    metrics = _mapping(packet.get("effect_metrics"))
    controls = _mapping(packet.get("controls"))
    policy = _mapping(packet.get("review_policy"))
    tags = _mapping(packet.get("oos_repeat_tags"))
    source_artifacts = _mapping(packet.get("source_artifacts"))

    reward_refs = inputs.get("reward_ledger_refs")
    if not isinstance(reward_refs, Sequence) or isinstance(reward_refs, (str, bytes)) or not reward_refs:
        reasons.append("reward_ledger_refs_missing")
    else:
        if _reward_ref_set(reward_refs, reasons) != _expected_reward_ref_set(records):
            reasons.append("reward_ledger_refs_set_mismatch")

    expected_proof_refs = _expected_lineage_hash_set(records, "proof_packet_hash")
    supplied_proof_refs = _hash_ref_set(inputs.get("proof_packet_refs"), "proof_packet_refs", reasons)
    if not supplied_proof_refs:
        reasons.append("proof_packet_refs_missing")
    elif supplied_proof_refs != expected_proof_refs:
        reasons.append("proof_packet_refs_set_mismatch")

    expected_mutation_refs = _expected_lineage_hash_set(records, "mutation_envelope_hash")
    supplied_mutation_refs = _hash_ref_set(
        inputs.get("mutation_envelope_refs"), "mutation_envelope_refs", reasons
    )
    if not supplied_mutation_refs:
        reasons.append("mutation_envelope_refs_missing")
    elif supplied_mutation_refs != expected_mutation_refs:
        reasons.append("mutation_envelope_refs_set_mismatch")
    if _bool(policy.get("acceptance_report_required"), default=False):
        refs = inputs.get("acceptance_report_refs")
        if not isinstance(refs, Sequence) or isinstance(refs, (str, bytes)) or not refs:
            reasons.append("acceptance_report_refs_missing")
    for ref in inputs.get("acceptance_report_refs", []) or []:
        if not isinstance(ref, Mapping):
            reasons.append("acceptance_report_ref_not_mapping")
            continue
        try:
            _normalize_acceptance_report_ref(ref)
        except ValueError as exc:
            reasons.append(str(exc))

    if source_artifacts.get("reward_records") != list(records):
        reasons.append("source_artifacts_reward_records_mismatch")

    if not all((_mapping(record.get("execution_identity")).get("fill_ids") or []) for record in records):
        reasons.append("no_matched_fills")
    if _number(metrics.get("matched_control_count")) is None or int(
        _number(metrics.get("matched_control_count")) or 0
    ) <= 0:
        reasons.append("matched_control_count_missing")
    if _bool(controls.get("matched_control_required"), default=True) and not controls.get(
        "matched_control_ids"
    ):
        reasons.append("matched_controls_missing")
    if _bool(controls.get("regime_labels_required"), default=True) and not controls.get(
        "regime_labels"
    ):
        reasons.append("regime_labels_missing")
    if _bool(controls.get("oos_required"), default=True) and not _bool(tags.get("oos")):
        reasons.append("oos_required_missing")
    if any(_mapping(record.get("controls")).get("proof_exclusions") for record in records):
        reasons.append("proof_exclusions_present")
    return reasons


def _effect_metrics(
    records: Sequence[Mapping[str, Any]],
    controls: Mapping[str, Any],
    oos_repeat_tags: Mapping[str, Any],
) -> dict[str, Any]:
    net_bps = [_reward_number(record, "net_pnl_bps") or 0.0 for record in records]
    net_usdt = [_reward_number(record, "net_pnl_usdt") or 0.0 for record in records]
    matched_controls = list(controls.get("matched_control_ids") or [])
    return {
        "sample_count": len(records),
        "net_pnl_bps_sum": sum(net_bps),
        "net_pnl_usdt_sum": sum(net_usdt),
        "net_pnl_bps_mean": sum(net_bps) / len(net_bps) if net_bps else 0.0,
        "positive_sample_count": sum(1 for value in net_bps if value > 0),
        "negative_sample_count": sum(1 for value in net_bps if value < 0),
        "matched_control_count": len(matched_controls),
        "control_outperformance_bps": controls.get("control_outperformance_bps", 0.0),
        "mutation_effect_status": _text(controls.get("mutation_effect_status") or "passed"),
        "oos_status": "passed" if _bool(oos_repeat_tags.get("oos")) else "missing",
        "repeat_status": "passed" if _bool(oos_repeat_tags.get("repeat")) else "missing",
    }


def _candidate_from_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    candidate: dict[str, Any] | None = None
    for record in records:
        current = {
            field: _text(_mapping(record.get("candidate_identity")).get(field))
            for field in _CANDIDATE_FIELDS
        }
        if not all(current.values()):
            return None
        if candidate is None:
            candidate = current
        elif any(candidate[field] != current[field] for field in _CANDIDATE_FIELDS):
            return None
    return candidate


def _reward_records(packet: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    artifacts = _mapping(packet.get("source_artifacts"))
    records = artifacts.get("reward_records")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return []
    return [record for record in records if isinstance(record, Mapping)]


def _normalize_acceptance_report_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    claimed_hash = _text(ref.get("acceptance_report_hash") or ref.get("report_hash"))
    payload = copy.deepcopy(dict(ref))
    payload.pop("acceptance_report_hash", None)
    payload.pop("report_hash", None)
    computed = _stable_sha256_json(payload)
    if claimed_hash and _strip_hash(claimed_hash) != computed:
        raise ValueError("acceptance_report_hash_mismatch")
    normalized = copy.deepcopy(dict(ref))
    normalized.pop("report_hash", None)
    normalized["acceptance_report_hash"] = computed
    return normalized


def _review_only_no_authority() -> dict[str, bool]:
    flags = {key: False for key in _NO_AUTHORITY_KEYS}
    flags["promotion_review_only"] = True
    return flags


def _no_authority_reasons(no_authority: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    for key in _NO_AUTHORITY_KEYS:
        if key not in no_authority:
            reasons.append(f"no_authority_{key}_missing")
        elif no_authority.get(key) is not False:
            reasons.append(f"no_authority_{key}_not_false")
    if no_authority.get("promotion_review_only") is not True:
        reasons.append("no_authority_promotion_review_only_not_true")
    return reasons


def _expected_reward_ref_set(records: Sequence[Mapping[str, Any]]) -> set[tuple[str, str]]:
    return {
        (str(record["record_id"]), compute_reward_record_hash(record))
        for record in records
    }


def _reward_ref_set(value: Any, reasons: list[str]) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        reasons.append("reward_ledger_refs_not_sequence")
        return refs
    for ref in value:
        if not isinstance(ref, Mapping):
            reasons.append("reward_ledger_ref_not_mapping")
            continue
        record_id = _text(ref.get("record_id"))
        record_hash = _strip_hash(_text(ref.get("record_hash")))
        if not record_id or not _is_hash(record_hash):
            reasons.append("reward_ledger_ref_malformed")
            continue
        item = (record_id, record_hash)
        if item in refs:
            reasons.append("reward_ledger_ref_duplicate")
        refs.add(item)
    if len(refs) != len(value):
        reasons.append("reward_ledger_refs_duplicate_or_malformed")
    return refs


def _expected_lineage_hash_set(
    records: Sequence[Mapping[str, Any]],
    field: str,
) -> set[str]:
    refs: set[str] = set()
    for record in records:
        item = _strip_hash(_text(_mapping(record.get("lineage")).get(field)))
        if _is_hash(item):
            refs.add(item)
    return refs


def _hash_ref_set(value: Any, field_name: str, reasons: list[str]) -> set[str]:
    refs: set[str] = set()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        reasons.append(f"{field_name}_not_sequence")
        return refs
    for item in value:
        item_hash = _strip_hash(_text(item))
        if not _is_hash(item_hash):
            reasons.append(f"{field_name}_malformed")
            continue
        if item_hash in refs:
            reasons.append(f"{field_name}_duplicate")
        refs.add(item_hash)
    if len(refs) != len(value):
        reasons.append(f"{field_name}_duplicate_or_malformed")
    return refs


def _authority_violations(value: Any, path: str = "$") -> list[str]:
    violations: list[str] = []
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_text = str(key)
            norm = _normalized_key(key_text)
            child_path = f"{path}.{key_text}"
            if not norm.startswith(("no_", "not_")):
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
    tokens = set(_key_tokens(norm_key))
    has_authority_term = any(term in norm_key for term in _AUTHORITY_KEY_TERMS)
    has_authority_action = any(
        action in norm_key for action in _AUTHORITY_ACTION_TERMS
    ) or bool(tokens & _AUTHORITY_ACTION_TOKENS)
    return has_authority_term and has_authority_action


def _truthy_breach(loss_limits: Mapping[str, Any]) -> bool:
    for key, value in loss_limits.items():
        if "breach" in _normalized_key(str(key)) and _truthy(value):
            return True
    return False


def _authority_value_grants(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in _FALSE_STRINGS
    return _truthy(value)


def _reward_number(record: Mapping[str, Any], field: str) -> float | None:
    return _number(_mapping(record.get("reward")).get(field))


def _max_consecutive_negative(values: Sequence[float]) -> int:
    current = 0
    max_seen = 0
    for value in values:
        if value < 0:
            current += 1
            max_seen = max(max_seen, current)
        else:
            current = 0
    return max_seen


def _bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return bool(value)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in _TRUTHY_STRINGS
    return bool(value)


def _is_hash(value: str) -> bool:
    return bool(_HEX64_RE.match(value))


def _strip_hash(value: str) -> str:
    return value.removeprefix("sha256:")


def _stable_sha256_json(value: Any) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return parsed


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    if value < 0:
        return None
    return value


def _normalized_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.strip().lower()).strip("_")


def _key_tokens(norm_key: str) -> list[str]:
    return [token for token in norm_key.split("_") if token]


def _result(
    valid: bool,
    decision: str,
    reason: str,
    reasons: tuple[str, ...] | list[str] = (),
    *,
    authority_boundary_violation: bool = False,
) -> LearningEffectReviewValidation:
    normalized = tuple(str(item) for item in reasons) or (reason,)
    return LearningEffectReviewValidation(
        valid=valid,
        decision=decision,
        reason=reason,
        reasons=normalized,
        review_only=True,
        authority_boundary_violation=authority_boundary_violation,
    )

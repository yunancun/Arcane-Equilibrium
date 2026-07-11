"""Fail-closed, source-only handoff from a selected WP2 candidate to proof inputs.

This module deliberately does not construct a proof packet, receipt, reward, or
durable record.  It only binds caller-supplied immutable artifacts and reports
whether the pre-existing proof/reward contracts may be considered next.  It
never grants order, runtime, promotion, or training authority.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

from ml_training.alr_operational_repository import (
    AlrOperationalError,
    build_candidate_learning_projection_plan,
)
from ml_training.proof_packet_contract import (
    INVALID as PROOF_INVALID,
    NO_MATCHED_FILLS,
    PROOF_READY,
    compute_proof_packet_hash,
    validate_proof_packet,
)
from ml_training.reward_ledger import (
    compute_reward_record_hash,
    validate_reward_record,
)


CANDIDATE_PROOF_ADAPTER_SCHEMA_VERSION = "candidate_proof_adapter_v1"
SELECTION_PROOF_BINDING_SCHEMA_VERSION = "candidate_proof_selection_binding_v1"

READY_FOR_REWARD_VALIDATION = "READY_FOR_REWARD_VALIDATION"
PENDING_EVIDENCE = "PENDING_EVIDENCE"
INVALID = "INVALID"

_NO_AUTHORITY = {
    "exchange_authority": False,
    "trading_authority": False,
    "order_or_probe_authority": False,
    "decision_lease_authority": False,
    "cost_gate_authority": False,
    "proof_authority": False,
    "serving_authority": False,
    "promotion_authority": False,
    "latest_authority": False,
}
_AUTHORITY_COUNTERS = {
    "exchange_contact_count": 0,
    "trading_action_count": 0,
    "order_or_probe_count": 0,
    "decision_lease_count": 0,
    "cost_gate_change_count": 0,
    "proof_claim_count": 0,
    "serving_or_promotion_count": 0,
}
_BINDING_FIELDS = {
    "schema_version",
    "projection_hash",
    "artifact_hash",
    "decision_hash",
    "source_set_hash",
    "handoff_hash",
    "candidate_id",
    "context_id",
    "selected_candidate",
    "binding_hash",
}


def derive_selected_candidate_proof_identity(
    selected_candidate: Mapping[str, Any],
) -> dict[str, str]:
    """Derive, never invent, the proof identity from the selected WP2 row.

    ``candidate_id`` uses the already-authoritative candidate-v2 formula.  The
    projection only carries context hashes, not a raw execution context, so the
    bridge uses a namespaced hash of that immutable map as ``context_id``.  A
    caller may copy these values into a proof binding, but cannot choose them.
    """
    identity = _mapping(selected_candidate.get("identity"))
    context_hashes = _mapping(selected_candidate.get("context_hashes"))
    if not identity or not context_hashes:
        raise ValueError("selected_candidate_identity_or_context_missing")
    return {
        "candidate_id": _canonical_sha256(
            {
                "schema_version": "cost_gate_learning_candidate_v2",
                "identity": copy.deepcopy(dict(identity)),
                "context_hashes": copy.deepcopy(dict(context_hashes)),
            }
        ),
        "context_id": "candidate_context:"
        + _canonical_sha256(
            {
                "schema_version": "candidate_proof_context_v1",
                "context_hashes": copy.deepcopy(dict(context_hashes)),
            }
        ),
    }


def compute_selection_proof_binding_hash(binding: Mapping[str, Any]) -> str:
    """Hash an immutable caller-supplied selection/proof identity binding."""
    payload = copy.deepcopy(dict(binding))
    payload.pop("binding_hash", None)
    return _canonical_sha256(payload)


def compute_candidate_proof_adapter_hash(adapter: Mapping[str, Any]) -> str:
    """Hash the adapter summary without its self-hash."""
    payload = copy.deepcopy(dict(adapter))
    payload.pop("adapter_hash", None)
    return _canonical_sha256(payload)


def adapt_candidate_proof(
    *,
    projection: Mapping[str, Any],
    selection_proof_binding: Mapping[str, Any] | None,
    proof_packet: Mapping[str, Any] | None = None,
    reward_records: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Summarize immutable proof inputs without creating proof or reward facts.

    A ``proof_packet`` and ``reward_records`` remain caller-created inputs.  A
    missing packet is a pending external-evidence state, while an invalid,
    mismatched, or ambiguous input is rejected.  The function is pure and does
    not inspect a repository, database, runtime, or broker.
    """
    try:
        plan = build_candidate_learning_projection_plan(projection)
    except (AlrOperationalError, TypeError, ValueError) as exc:
        return _invalid("projection_invalid:" + str(exc))

    if plan["decision_code"] != "QUALIFIED_CANDIDATE_SELECTED":
        return _invalid("projection_not_qualified_candidate")
    if not isinstance(plan.get("handoff"), Mapping) or not _text(
        _mapping(plan.get("handoff")).get("handoff_hash")
    ):
        return _invalid("projection_handoff_missing")
    try:
        binding = _validate_binding(plan, selection_proof_binding)
    except ValueError as exc:
        return _pending_or_invalid(str(exc))

    projection_refs = _projection_refs(plan)
    if proof_packet is not None and not isinstance(proof_packet, Mapping):
        return _build_result(
            status=INVALID,
            reasons=("proof_packet_not_mapping",),
            projection_refs=projection_refs,
            binding=binding,
            proof=_proof_summary(proof_packet),
            rewards=[],
        )
    proof_summary = _proof_summary(proof_packet)
    reward_summaries, reward_reasons = _reward_summaries(reward_records)

    if proof_packet is None:
        if reward_reasons:
            return _build_result(
                status=INVALID,
                reasons=reward_reasons,
                projection_refs=projection_refs,
                binding=binding,
                proof=proof_summary,
                rewards=reward_summaries,
            )
        return _build_result(
            status=PENDING_EVIDENCE,
            reasons=("proof_packet_missing",),
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )

    proof_validation = validate_proof_packet(proof_packet)
    if proof_validation.verdict == PROOF_INVALID:
        return _build_result(
            status=INVALID,
            reasons=(
                *("proof_packet:" + reason for reason in proof_validation.reasons),
                *reward_reasons,
            ),
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )

    binding_reasons = _proof_binding_reasons(
        proof_packet,
        plan=plan,
        binding=binding,
    )
    if binding_reasons:
        return _build_result(
            status=INVALID,
            reasons=(*binding_reasons, *reward_reasons),
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )
    if reward_reasons:
        return _build_result(
            status=INVALID,
            reasons=reward_reasons,
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )

    if proof_validation.verdict == NO_MATCHED_FILLS:
        if reward_summaries:
            return _build_result(
                status=INVALID,
                reasons=("no_matched_fills_has_reward_records",),
                projection_refs=projection_refs,
                binding=binding,
                proof=proof_summary,
                rewards=reward_summaries,
            )
        return _build_result(
            status=NO_MATCHED_FILLS,
            reasons=("external_execution_receipts_pending",),
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )
    if proof_validation.verdict != PROOF_READY:
        return _build_result(
            status=PENDING_EVIDENCE,
            reasons=(
                *("proof_packet:" + reason for reason in proof_validation.reasons),
                "external_execution_receipts_pending",
            ),
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )

    reward_match_reasons = _reward_match_reasons(
        reward_records,
        proof_packet=proof_packet,
        binding=binding,
    )
    if reward_match_reasons:
        return _build_result(
            status=INVALID,
            reasons=reward_match_reasons,
            projection_refs=projection_refs,
            binding=binding,
            proof=proof_summary,
            rewards=reward_summaries,
        )
    return _build_result(
        status=READY_FOR_REWARD_VALIDATION,
        reasons=("source_only_no_durable_receipt_attestation",),
        projection_refs=projection_refs,
        binding=binding,
        proof=proof_summary,
        rewards=reward_summaries,
    )


def _validate_binding(
    plan: Mapping[str, Any], value: Mapping[str, Any] | None
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("selection_proof_binding_missing")
    if set(value) != _BINDING_FIELDS:
        raise ValueError("selection_proof_binding_fields_invalid")
    if value.get("schema_version") != SELECTION_PROOF_BINDING_SCHEMA_VERSION:
        raise ValueError("selection_proof_binding_schema_invalid")
    if value.get("binding_hash") != compute_selection_proof_binding_hash(value):
        raise ValueError("selection_proof_binding_hash_mismatch")
    selected = plan["artifact"]["canonical_payload"]["selected_candidate"]
    if not isinstance(selected, Mapping):
        raise ValueError("projection_selected_candidate_missing")
    handoff = plan.get("handoff")
    if not isinstance(handoff, Mapping) or not _text(handoff.get("handoff_hash")):
        raise ValueError("projection_handoff_missing")
    selected_identity = derive_selected_candidate_proof_identity(selected)
    expected = {
        "projection_hash": plan["projection_hash"],
        "artifact_hash": plan["artifact"]["artifact_hash"],
        "decision_hash": plan["decision_hash"],
        "source_set_hash": plan["source_set_hash"],
        "handoff_hash": handoff["handoff_hash"],
    }
    for key, expected_value in expected.items():
        if value.get(key) != expected_value:
            raise ValueError("selection_proof_binding_" + key + "_mismatch")
    for key, expected_value in selected_identity.items():
        if value.get(key) != expected_value:
            raise ValueError("selection_proof_binding_" + key + "_mismatch")
    if value.get("selected_candidate") != selected:
        raise ValueError("selection_proof_binding_selected_candidate_mismatch")
    return copy.deepcopy(dict(value))


def _proof_binding_reasons(
    proof_packet: Mapping[str, Any], *, plan: Mapping[str, Any], binding: Mapping[str, Any]
) -> tuple[str, ...]:
    reasons: list[str] = []
    candidate = _mapping(proof_packet.get("candidate_identity"))
    if candidate.get("candidate_id") != binding["candidate_id"]:
        reasons.append("proof_packet_candidate_id_mismatch")
    if candidate.get("context_id") != binding["context_id"]:
        reasons.append("proof_packet_context_id_mismatch")
    selected_identity = _mapping(_mapping(binding.get("selected_candidate")).get("identity"))
    for key, expected in selected_identity.items():
        if key in candidate and candidate.get(key) != expected:
            reasons.append("proof_packet_selected_identity_" + str(key) + "_mismatch")
    input_hashes = _mapping(_mapping(proof_packet.get("provenance")).get("input_artifact_hashes"))
    expected_hashes = {
        "candidate_projection_artifact_hash": plan["artifact"]["artifact_hash"],
        "candidate_projection_decision_hash": plan["decision_hash"],
        "candidate_projection_handoff_hash": binding["handoff_hash"],
    }
    for key, expected in expected_hashes.items():
        if input_hashes.get(key) != expected:
            reasons.append("proof_packet_" + key + "_mismatch")
    pit_scope = _mapping(
        _mapping(_mapping(proof_packet.get("provenance")).get("pit_dataset_manifest")).get(
            "candidate_scope"
        )
    )
    if pit_scope:
        for key in ("candidate_id", "strategy_name", "symbol", "side"):
            if pit_scope.get(key) != candidate.get(key):
                reasons.append("proof_packet_pit_candidate_scope_" + key + "_mismatch")
    pit_manifest = _mapping(_mapping(proof_packet.get("provenance")).get("pit_dataset_manifest"))
    if pit_manifest:
        pit_as_of = _parse_utc_z(pit_manifest.get("as_of_ts"))
        decision = _mapping(plan["artifact"]["canonical_payload"].get("decision"))
        decision_at = _parse_utc_z(decision.get("evaluated_at"))
        if pit_as_of is None or decision_at is None:
            reasons.append("proof_packet_pit_or_decision_time_invalid")
        elif pit_as_of > decision_at:
            reasons.append("proof_packet_pit_after_projection_decision")
    return tuple(reasons)


def _proof_summary(packet: Any) -> dict[str, Any]:
    if packet is None:
        return {"present": False, "proof_packet_hash": None, "verdict": None, "reasons": ["proof_packet_missing"]}
    if not isinstance(packet, Mapping):
        return {"present": True, "proof_packet_hash": None, "computed_proof_packet_hash": None, "verdict": PROOF_INVALID, "reasons": ["proof_packet_not_mapping"]}
    validation = validate_proof_packet(packet)
    return {
        "present": True,
        "proof_packet_hash": _stable_text_or_none(packet.get("proof_packet_hash")),
        "computed_proof_packet_hash": _proof_packet_hash_or_none(packet),
        "verdict": validation.verdict,
        "reasons": list(validation.reasons),
    }


def _reward_summaries(
    records: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], tuple[str, ...]]:
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        return [], ("reward_records_not_sequence",)
    summaries: list[dict[str, Any]] = []
    reasons: list[str] = []
    seen_hashes: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            reasons.append("reward_record_%d_not_mapping" % index)
            continue
        validation = validate_reward_record(record)
        record_hash = _stable_text_or_none(record.get("record_hash"))
        if record_hash and record_hash in seen_hashes:
            reasons.append("reward_record_hash_duplicate")
        if record_hash:
            seen_hashes.add(record_hash)
        if not validation.reward_ready:
            reasons.extend("reward_record_%d:%s" % (index, reason) for reason in validation.reasons)
        summaries.append(
            {
                "record_hash": record_hash,
                "computed_record_hash": _reward_record_hash_or_none(record),
                "verdict": validation.verdict,
                "reasons": list(validation.reasons),
            }
        )
    summaries.sort(
        key=lambda item: (
            item["computed_record_hash"] is None,
            item["computed_record_hash"] or "",
            item["record_hash"] or "",
        )
    )
    return summaries, tuple(reasons)


def _reward_match_reasons(
    records: Sequence[Mapping[str, Any]], *, proof_packet: Mapping[str, Any], binding: Mapping[str, Any]
) -> tuple[str, ...]:
    proof_hash = _proof_packet_hash_or_none(proof_packet)
    reasons: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            continue
        lineage = _mapping(record.get("lineage"))
        candidate = _mapping(record.get("candidate_identity"))
        if not proof_hash or lineage.get("proof_packet_hash") != proof_hash:
            reasons.append("reward_record_%d_proof_packet_hash_mismatch" % index)
        if candidate.get("candidate_id") != binding["candidate_id"]:
            reasons.append("reward_record_%d_candidate_id_mismatch" % index)
        if candidate.get("context_id") != binding["context_id"]:
            reasons.append("reward_record_%d_context_id_mismatch" % index)
    return tuple(reasons)


def _projection_refs(plan: Mapping[str, Any]) -> dict[str, Any]:
    handoff = plan.get("handoff")
    return {
        "projection_hash": plan["projection_hash"],
        "artifact_kind": plan["artifact"]["artifact_kind"],
        "artifact_hash": plan["artifact"]["artifact_hash"],
        "decision_hash": plan["decision_hash"],
        "source_set_hash": plan["source_set_hash"],
        "handoff_hash": handoff.get("handoff_hash") if isinstance(handoff, Mapping) else None,
        "durable_receipt_status": "unverified_source_only",
    }


def _build_result(
    *, status: str, reasons: Sequence[str], projection_refs: Mapping[str, Any], binding: Mapping[str, Any], proof: Mapping[str, Any], rewards: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": CANDIDATE_PROOF_ADAPTER_SCHEMA_VERSION,
        "status": status,
        "reasons": sorted(set(str(reason) for reason in reasons)),
        "projection_refs": copy.deepcopy(dict(projection_refs)),
        "selection_binding": copy.deepcopy(dict(binding)),
        "proof": copy.deepcopy(dict(proof)),
        "reward_records": copy.deepcopy(list(rewards)),
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    result["proof_input_hash"] = _canonical_sha256(
        {
            "projection_refs": result["projection_refs"],
            "selection_binding_hash": binding["binding_hash"],
            "proof_packet_hash": _mapping(proof).get("computed_proof_packet_hash"),
            "reward_record_hashes": [
                _mapping(record).get("computed_record_hash") for record in rewards
            ],
        }
    )
    result["adapter_hash"] = compute_candidate_proof_adapter_hash(result)
    return result


def _invalid(reason: str) -> dict[str, Any]:
    return _bare_result(INVALID, reason)


def _pending_or_invalid(reason: str) -> dict[str, Any]:
    status = PENDING_EVIDENCE if reason.endswith("_missing") else INVALID
    return _bare_result(status, reason)


def _bare_result(status: str, reason: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": CANDIDATE_PROOF_ADAPTER_SCHEMA_VERSION,
        "status": status,
        "reasons": [reason],
        "projection_refs": None,
        "selection_binding": None,
        "proof": None,
        "reward_records": [],
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    result["proof_input_hash"] = None
    result["adapter_hash"] = compute_candidate_proof_adapter_hash(result)
    return result


def _canonical_sha256(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _stable_text_or_none(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _proof_packet_hash_or_none(packet: Mapping[str, Any]) -> str | None:
    try:
        return compute_proof_packet_hash(packet)
    except (TypeError, ValueError):
        return None


def _reward_record_hash_or_none(record: Mapping[str, Any]) -> str | None:
    try:
        return compute_reward_record_hash(record)
    except (TypeError, ValueError):
        return None


def _parse_utc_z(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


__all__ = [
    "CANDIDATE_PROOF_ADAPTER_SCHEMA_VERSION",
    "SELECTION_PROOF_BINDING_SCHEMA_VERSION",
    "READY_FOR_REWARD_VALIDATION",
    "PENDING_EVIDENCE",
    "NO_MATCHED_FILLS",
    "INVALID",
    "adapt_candidate_proof",
    "compute_candidate_proof_adapter_hash",
    "compute_selection_proof_binding_hash",
    "derive_selected_candidate_proof_identity",
]

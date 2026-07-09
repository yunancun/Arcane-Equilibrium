"""Pure P2-5 ProofPacket/RewardLedger feedback and deferred-target rotation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ml_training.alr_outcome_bridge import (
    OUTCOME_ADVANCED,
    OUTCOME_BLOCKED_BOUNDARY,
    OUTCOME_DEFER_EVIDENCE,
    build_alr_outcome_bridge_packet,
    validate_alr_outcome_bridge_packet,
)


OUTPUT_SCHEMA_VERSION = "alr_outcome_feedback_v1"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
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


@dataclass(frozen=True)
class AlrOutcomeFeedbackValidation:
    valid: bool
    reason: str
    reasons: tuple[str, ...] = ()


class AlrOutcomeFeedbackError(ValueError):
    """A run cannot consume proof/reward feedback outside the ALR boundary."""


def compute_outcome_feedback_hash(result: Mapping[str, Any]) -> str:
    """Canonical hash of the feedback bundle excluding its top-level hash."""
    payload = copy.deepcopy(dict(result))
    payload.pop("feedback_hash", None)
    return _canonical_sha256(payload)


def build_outcome_feedback(
    *,
    run: Mapping[str, Any],
    candidate_artifact: Mapping[str, Any],
    proof_packet: Mapping[str, Any] | None = None,
    reward_records: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build one hash-bound feedback decision without granting proof authority.

    Empty inputs are deliberate: absence becomes a durable `DEFER_EVIDENCE`
    feedback record and asks the consumer to rotate to the next target.  Caller
    supplied proof/reward records are validated solely by the existing pure
    bridge and never make this module a promotion or serving authority.
    """
    run_hash = _required_hash(run.get("run_hash"), "run_hash")
    candidate_hash = _required_hash(
        run.get("candidate_artifact_hash"), "candidate_artifact_hash"
    )
    candidate_scope = _candidate_scope(candidate_artifact)
    _require_false(candidate_artifact.get("serving_ready"), "candidate_serving_ready")
    _require_false(candidate_artifact.get("promotion_ready"), "candidate_promotion_ready")

    if any(not isinstance(record, Mapping) for record in reward_records):
        raise AlrOutcomeFeedbackError("reward_record_not_mapping")
    proof = {} if proof_packet is None else copy.deepcopy(dict(proof_packet))
    records = [copy.deepcopy(dict(record)) for record in reward_records]
    bridge = build_alr_outcome_bridge_packet(
        proof_packet=proof,
        reward_records=records,
    )
    bridge_validation = validate_alr_outcome_bridge_packet(bridge)
    if bridge_validation.authority_boundary_violation:
        status = "BLOCKED_BOUNDARY"
    elif bridge_validation.outcome == OUTCOME_ADVANCED:
        status = "EVIDENCE_OBSERVED_NO_PROMOTION"
    elif bridge_validation.outcome == OUTCOME_DEFER_EVIDENCE:
        status = "DEFER_EVIDENCE"
    elif bridge_validation.outcome == OUTCOME_BLOCKED_BOUNDARY:
        status = "BLOCKED_BOUNDARY"
    else:
        raise AlrOutcomeFeedbackError("bridge_outcome_invalid")

    bridge_payload = {
        "schema_version": "alr_outcome_bridge_artifact_v1",
        "run_hash": run_hash,
        "candidate_artifact_hash": candidate_hash,
        "bridge": bridge,
    }
    bridge_artifact_hash = _canonical_sha256(bridge_payload)
    gaps = _evidence_gaps(bridge, candidate_artifact)
    feedback_payload = {
        "schema_version": "alr_outcome_feedback_event_v1",
        "run_hash": run_hash,
        "candidate_artifact_hash": candidate_hash,
        "candidate_scope": candidate_scope,
        "bridge_artifact_hash": bridge_artifact_hash,
        "bridge_hash": bridge["bridge_hash"],
        "feedback_status": status,
        "bridge_outcome": bridge_validation.outcome,
        "proof_packet_present": proof_packet is not None,
        "reward_record_count": len(records),
        "evidence_gaps": gaps,
        "proof_ready": False,
        "promotion_ready": False,
        "serving_ready": False,
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    feedback_artifact_hash = _canonical_sha256(feedback_payload)
    rotation_payload = {
        "schema_version": "alr_target_rotation_v1",
        "run_hash": run_hash,
        "feedback_artifact_hash": feedback_artifact_hash,
        "feedback_status": status,
        "rotate_next_target": status == "DEFER_EVIDENCE",
        "global_stop": status == "BLOCKED_BOUNDARY",
        "rotation_reason": "outcome_evidence_missing"
        if status == "DEFER_EVIDENCE"
        else "evidence_observed_no_promotion"
        if status == "EVIDENCE_OBSERVED_NO_PROMOTION"
        else "boundary_blocked",
        "no_authority": dict(_NO_AUTHORITY),
    }
    rotation_artifact_hash = _canonical_sha256(rotation_payload)
    artifacts = [
        _artifact("outcome_bridge", bridge_artifact_hash, bridge_payload),
        _artifact("outcome_feedback", feedback_artifact_hash, feedback_payload),
        _artifact("target_rotation", rotation_artifact_hash, rotation_payload),
    ]
    edges = [
        _edge(candidate_hash, bridge_artifact_hash, "candidate_outcome_bridge"),
        _edge(bridge_artifact_hash, feedback_artifact_hash, "bridge_feedback"),
        _edge(feedback_artifact_hash, rotation_artifact_hash, "feedback_rotation"),
    ]
    result: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "run_hash": run_hash,
        "candidate_artifact_hash": candidate_hash,
        "bridge": bridge,
        "feedback": feedback_payload,
        "rotation": rotation_payload,
        "artifacts": artifacts,
        "provenance_edges": edges,
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    result["feedback_hash"] = compute_outcome_feedback_hash(result)
    return result


def validate_outcome_feedback(result: Mapping[str, Any]) -> AlrOutcomeFeedbackValidation:
    """Validate the feedback bundle before its append-only repository persists it."""
    if not isinstance(result, Mapping):
        return _invalid("result_not_mapping")
    reasons: list[str] = []
    if result.get("schema_version") != OUTPUT_SCHEMA_VERSION:
        reasons.append("schema_version_invalid")
    if result.get("feedback_hash") != compute_outcome_feedback_hash(result):
        reasons.append("feedback_hash_mismatch")
    if not _all_false(result.get("no_authority")):
        reasons.append("no_authority_not_false")
    if not _all_zero(result.get("authority_counters")):
        reasons.append("authority_counters_not_zero")
    try:
        _required_hash(result.get("run_hash"), "run_hash")
        _required_hash(result.get("candidate_artifact_hash"), "candidate_artifact_hash")
    except AlrOutcomeFeedbackError as exc:
        reasons.append(str(exc))

    bridge = result.get("bridge")
    if not isinstance(bridge, Mapping):
        reasons.append("bridge_missing")
        bridge_outcome = None
    else:
        bridge_validation = validate_alr_outcome_bridge_packet(bridge)
        bridge_outcome = bridge_validation.outcome
        if not bridge_validation.valid and not bridge_validation.authority_boundary_violation:
            reasons.append(f"bridge_invalid:{bridge_validation.reason}")
    feedback = result.get("feedback")
    if not isinstance(feedback, Mapping):
        reasons.append("feedback_missing")
    else:
        expected_status = _status_for_outcome(bridge_outcome)
        if feedback.get("feedback_status") != expected_status:
            reasons.append("feedback_status_mismatch")
        if feedback.get("proof_ready") is not False:
            reasons.append("feedback_proof_ready_invalid")
        if feedback.get("promotion_ready") is not False:
            reasons.append("feedback_promotion_ready_invalid")
        if feedback.get("serving_ready") is not False:
            reasons.append("feedback_serving_ready_invalid")
        if not _all_false(feedback.get("no_authority")):
            reasons.append("feedback_no_authority_invalid")
        if not _all_zero(feedback.get("authority_counters")):
            reasons.append("feedback_authority_counters_invalid")
    rotation = result.get("rotation")
    if not isinstance(rotation, Mapping):
        reasons.append("rotation_missing")
    else:
        expected_status = _status_for_outcome(bridge_outcome)
        if rotation.get("rotate_next_target") is not (expected_status == "DEFER_EVIDENCE"):
            reasons.append("rotation_target_mismatch")
        if rotation.get("global_stop") is not (expected_status == "BLOCKED_BOUNDARY"):
            reasons.append("rotation_stop_mismatch")
        if not _all_false(rotation.get("no_authority")):
            reasons.append("rotation_no_authority_invalid")
    if not isinstance(result.get("artifacts"), list) or len(result["artifacts"]) != 3:
        reasons.append("artifacts_invalid")
    if not isinstance(result.get("provenance_edges"), list) or len(result["provenance_edges"]) != 3:
        reasons.append("provenance_edges_invalid")
    if reasons:
        return _invalid(*reasons)
    return AlrOutcomeFeedbackValidation(True, "ok", ())


def _status_for_outcome(outcome: Any) -> str:
    if outcome == OUTCOME_ADVANCED:
        return "EVIDENCE_OBSERVED_NO_PROMOTION"
    if outcome == OUTCOME_DEFER_EVIDENCE:
        return "DEFER_EVIDENCE"
    return "BLOCKED_BOUNDARY"


def _candidate_scope(candidate_artifact: Mapping[str, Any]) -> dict[str, str]:
    scope = candidate_artifact.get("candidate_scope")
    if not isinstance(scope, Mapping):
        raise AlrOutcomeFeedbackError("candidate_scope_invalid")
    required = ("candidate_id", "strategy_name", "symbol", "side", "engine_mode")
    if any(not isinstance(scope.get(key), str) or not scope[key] for key in required):
        raise AlrOutcomeFeedbackError("candidate_scope_invalid")
    return {key: str(scope[key]) for key in required}


def _evidence_gaps(bridge: Mapping[str, Any], candidate_artifact: Mapping[str, Any]) -> list[str]:
    gaps = [str(item) for item in bridge.get("decision_reasons", ()) if isinstance(item, str)]
    after_cost = candidate_artifact.get("after_cost_evaluation")
    if isinstance(after_cost, Mapping):
        gaps.extend(
            str(item)
            for item in after_cost.get("missing_evidence", ())
            if isinstance(item, str)
        )
    return sorted(set(gaps))


def _artifact(kind: str, artifact_hash: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifact_kind": kind,
        "artifact_hash": artifact_hash,
        "canonical_payload": copy.deepcopy(dict(payload)),
    }


def _edge(from_hash: str, to_hash: str, edge_role: str) -> dict[str, str]:
    payload = {
        "from_artifact_hash": from_hash,
        "to_artifact_hash": to_hash,
        "edge_role": edge_role,
    }
    payload["edge_hash"] = _canonical_sha256(payload)
    return payload


def _required_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise AlrOutcomeFeedbackError(f"{field}_invalid")
    return value


def _require_false(value: Any, field: str) -> None:
    if value is not False:
        raise AlrOutcomeFeedbackError(f"{field}_invalid")


def _all_false(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(value) and all(_all_false(item) for item in value.values())
    if isinstance(value, list):
        return all(_all_false(item) for item in value)
    return value is False


def _all_zero(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(value) and all(
        isinstance(item, int) and not isinstance(item, bool) and item == 0
        for item in value.values()
    )


def _canonical_sha256(value: Any) -> str:
    try:
        payload = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AlrOutcomeFeedbackError("canonical_json_invalid") from exc
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _invalid(*reasons: str) -> AlrOutcomeFeedbackValidation:
    return AlrOutcomeFeedbackValidation(False, reasons[0], tuple(reasons))

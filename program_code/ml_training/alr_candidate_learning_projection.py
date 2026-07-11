"""Pure bridge from scanner context plus R3 evidence to one WP2 decision node."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ml_training.alr_candidate_evidence_adapter import (
    validate_candidate_selection_row_v2,
)
from ml_training.alr_candidate_learning_arbiter import (
    build_candidate_learning_decision,
)


PROJECTION_SCHEMA_VERSION = "alr_candidate_learning_projection_v2"
DECISION_SCHEMA_VERSION = "alr_candidate_learning_decision_v2"
ARTIFACT_SCHEMA_VERSION = "alr_candidate_learning_projection_artifact_v2"
EVIDENCE_SCHEMA_VERSION = "alr_candidate_evidence_snapshot_v2"
HANDOFF_SCHEMA_VERSION = "alr_candidate_board_handoff_v1"
CANDIDATE_SCHEMA_VERSION = "cost_gate_learning_candidate_v2"
ARBITER_INPUT_SCHEMA_VERSION = "alr_candidate_arbiter_input_v2"
_SELECTION_SCHEMA_VERSION = "cost_gate_learning_candidate_selection_v2"
_SELECTION_FIELDS = (
    "schema_version",
    "candidate_id",
    "candidate_family_key",
    "stable_cohort_hash",
    "candidate_identity",
    "identity_complete",
    "arbiter_input",
    "arbiter_input_complete",
    "selection_eligible",
    "blockers",
)

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
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


class AlrCandidateLearningProjectionError(ValueError):
    """The immutable scanner source set cannot identify a decision node."""


def build_candidate_aware_learning_projection(
    *,
    source_head: str,
    cycles: Sequence[Mapping[str, Any]],
    evidence_snapshot: Mapping[str, Any],
    prior_decisions: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Build a decision-only projection; never a PIT dataset or training run."""
    if not isinstance(source_head, str) or not _HEX40.fullmatch(source_head):
        raise AlrCandidateLearningProjectionError("source_head_invalid")
    normalized_cycles = _normalize_cycles(cycles)
    source_hashes = [cycle["source_hash"] for cycle in normalized_cycles]
    source_set_hash = _canonical_sha256(source_hashes)
    evidence = _normalize_evidence_snapshot(evidence_snapshot)
    candidate_rows = (
        [_normalize_candidate_row(row) for row in evidence["candidate_rows"]]
        if evidence["source_status"] == "READY"
        else []
    )
    candidate_rows.sort(key=_canonical_sha256)
    normalized_prior = _normalized_mappings(prior_decisions, "prior_decisions_invalid")
    normalized_prior.sort(key=_canonical_sha256)
    normalized_policy = (
        copy.deepcopy(dict(policy)) if isinstance(policy, Mapping) else {}
    )
    raw_decision = build_candidate_learning_decision(
        source_head=source_head,
        scanner_research_seeds=_scanner_research_seeds(normalized_cycles),
        candidate_evidence_board=candidate_rows,
        prior_decisions=normalized_prior,
        policy=normalized_policy,
    )
    decision_code = _decision_code(raw_decision, evidence["source_status"])
    ready_evidence_time = (
        evidence["handoff_evidence"].get("evaluated_at")
        if evidence["source_status"] == "READY"
        else None
    )
    evaluated_at = _decision_time(
        raw_decision.get("evaluated_at"),
        ready_evidence_time,
        normalized_cycles[-1]["source_ts"],
    )
    handoff = _build_handoff_identity(
        evidence=evidence,
        source_head=source_head,
        source_set_hash=source_set_hash,
        source_identities=[
            {
                "source_hash": cycle["source_hash"],
                "source_key": cycle["source_key"],
                "source_ts": cycle["source_ts"],
            }
            for cycle in normalized_cycles
        ],
        evaluated_at=evaluated_at,
        policy=normalized_policy,
        policy_config_hash=raw_decision.get("policy_hash"),
        prior_decisions=normalized_prior,
    )
    selected_candidate = (
        copy.deepcopy(raw_decision.get("selected_candidate"))
        if decision_code == "QUALIFIED_CANDIDATE_SELECTED"
        else None
    )
    selected_collection_target = (
        copy.deepcopy(raw_decision.get("selected_collection_target"))
        if decision_code
        == "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES"
        else None
    )
    assessed = raw_decision.get("evaluated_candidates")
    if not isinstance(assessed, list):
        assessed = []
    decision: dict[str, Any] = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "decision_code": decision_code,
        "evaluated_at": evaluated_at,
        "source_head": source_head,
        "source_set_hash": source_set_hash,
        "evidence_source_status": evidence["source_status"],
        "evidence_selection_hash": evidence["selection_hash"],
        "candidate_set_hash": evidence["candidate_set_hash"],
        "policy_hash": raw_decision.get("policy_hash"),
        "selected_candidate": selected_candidate,
        "selected_collection_target": selected_collection_target,
        "candidate_count": len(assessed),
        "eligible_candidate_count": sum(
            int(
                isinstance(item, Mapping)
                and item.get("state") == "DECISION_READY"
                and item.get("eligible") is True
            )
            for item in assessed
        ),
        "evaluated_candidates": copy.deepcopy(assessed),
        "training_run_created": False,
        "model_training_performed": False,
        "serving_ready": False,
        "promotion_ready": False,
        "order_or_probe_created": False,
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    decision["decision_hash"] = _canonical_sha256(decision)

    artifact_kind = (
        "learning_target"
        if decision_code == "QUALIFIED_CANDIDATE_SELECTED"
        else "target_rotation"
    )
    artifact_payload: dict[str, Any] = {
        "schema_version": ARTIFACT_SCHEMA_VERSION,
        "decision_code": decision_code,
        "decision_hash": decision["decision_hash"],
        "selected_candidate": selected_candidate,
        "selected_collection_target": selected_collection_target,
        "decision": copy.deepcopy(decision),
        "source_refs": {
            "evidence_source_status": evidence["source_status"],
            "evidence_selection_hash": evidence["selection_hash"],
            "candidate_set_hash": evidence["candidate_set_hash"],
            "handoff": handoff,
        },
        "training_run_created": False,
        "model_training_performed": False,
        "serving_ready": False,
        "promotion_ready": False,
        "order_or_probe_created": False,
        "next_stage": "WP4_VERSIONED_TRAINING_SCHEMA_REQUIRED",
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    artifact_hash = _canonical_sha256(artifact_payload)
    artifact = {
        "artifact_kind": artifact_kind,
        "artifact_hash": artifact_hash,
        "canonical_payload": artifact_payload,
    }
    edges = [
        _edge(source_hash, artifact_hash)
        for source_hash in source_hashes
    ]
    projection: dict[str, Any] = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "source_head": source_head,
        "source_set": {
            "source_set_hash": source_set_hash,
            "source_hashes": source_hashes,
            "source_count": len(source_hashes),
            "as_of_ts": normalized_cycles[-1]["source_ts"],
            "source_identities": [
                {
                    "source_hash": cycle["source_hash"],
                    "source_key": cycle["source_key"],
                    "source_ts": cycle["source_ts"],
                }
                for cycle in normalized_cycles
            ],
        },
        "decision": decision,
        "artifact": artifact,
        "provenance_edges": edges,
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    projection["projection_hash"] = _canonical_sha256(projection)
    return projection


def _normalize_cycles(
    cycles: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if (
        not isinstance(cycles, Sequence)
        or isinstance(cycles, (str, bytes, bytearray))
        or not cycles
    ):
        raise AlrCandidateLearningProjectionError("cycles_invalid")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in cycles:
        if not isinstance(raw, Mapping):
            raise AlrCandidateLearningProjectionError("cycle_invalid")
        source_hash = raw.get("source_hash")
        source_key = raw.get("source_key")
        source_ts = raw.get("source_ts")
        payload = raw.get("canonical_payload")
        if not isinstance(source_hash, str) or not _HEX64.fullmatch(source_hash):
            raise AlrCandidateLearningProjectionError("cycle_source_hash_invalid")
        if source_hash in seen:
            raise AlrCandidateLearningProjectionError("cycle_source_hash_duplicate")
        if not isinstance(source_key, str) or not source_key:
            raise AlrCandidateLearningProjectionError("cycle_source_key_invalid")
        canonical_ts = _canonical_utc_z(source_ts)
        if not isinstance(payload, Mapping):
            raise AlrCandidateLearningProjectionError("cycle_payload_invalid")
        normalized.append(
            {
                "source_hash": source_hash,
                "source_key": source_key,
                "source_ts": canonical_ts,
                "canonical_payload": copy.deepcopy(dict(payload)),
            }
        )
        seen.add(source_hash)
    normalized.sort(
        key=lambda item: (item["source_ts"], item["source_key"], item["source_hash"])
    )
    return normalized


def _normalize_evidence_snapshot(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return _invalid_evidence("EVIDENCE_SNAPSHOT_INVALID", value)
    raw = copy.deepcopy(dict(value))
    declared_hash = raw.get("snapshot_hash")
    semantic = {key: item for key, item in raw.items() if key != "snapshot_hash"}
    computed_hash = _canonical_sha256(semantic)
    if not _is_hash(declared_hash) or declared_hash != computed_hash:
        return _invalid_evidence("SNAPSHOT_HASH_MISMATCH", raw)
    if raw.get("schema_version") != EVIDENCE_SCHEMA_VERSION:
        return _invalid_evidence("EVIDENCE_SNAPSHOT_SCHEMA_INVALID", raw)
    status = raw.get("source_status")
    if not isinstance(status, str) or not status:
        return _invalid_evidence("EVIDENCE_SOURCE_STATUS_INVALID", raw)
    if raw.get("latest_alias_used") is not False:
        return _invalid_evidence("LATEST_ALIAS_INVALID", raw)
    if status != "READY":
        if (
            raw.get("candidate_universe_complete") is not False
            or raw.get("selection_allowed") is not False
            or raw.get("candidate_rows") != []
        ):
            return _invalid_evidence("EVIDENCE_NONREADY_PAYLOAD_INVALID", raw)
        return {
            "source_status": status,
            "selection_hash": None,
            "candidate_set_hash": None,
            "candidate_rows": [],
            "handoff_evidence": {
                "schema_version": raw["schema_version"],
                "source_status": status,
                "source_content_sha256": None,
                "board_hash": None,
                "selection_hash": None,
                "audit_hash": None,
                "candidate_set_hash": None,
                "generated_at": _optional_utc_z(raw.get("generated_at")),
                "evaluated_at": _optional_utc_z(raw.get("evaluated_at")),
                "cost_source_payload_sha256": None,
                "cost_normalized_projection_sha256": None,
                "cost_source_asof_utc": None,
            },
        }
    selection_hash = raw.get("selection_hash")
    candidate_set_hash = raw.get("candidate_set_hash")
    rows = raw.get("candidate_rows")
    if (
        not _is_hash(selection_hash)
        or not _is_hash(candidate_set_hash)
        or raw.get("candidate_universe_complete") is not True
        or raw.get("selection_allowed") is not True
        or not isinstance(rows, list)
        or not all(isinstance(row, Mapping) for row in rows)
    ):
        return _invalid_evidence("EVIDENCE_SNAPSHOT_INCOMPLETE", raw)
    try:
        semantic_rows = [
            _semantic_candidate_row(row)
            for row in rows
        ]
        candidate_ids = [row["candidate_id"] for row in semantic_rows]
        if len(candidate_ids) != len(set(candidate_ids)):
            return _invalid_evidence("EVIDENCE_CANDIDATE_ID_DUPLICATE", raw)
        semantic_rows.sort(
            key=lambda row: (row["candidate_id"], _canonical_sha256(row))
        )
    except (KeyError, TypeError, ValueError):
        return _invalid_evidence("EVIDENCE_CANDIDATE_ROWS_INVALID", raw)
    expected_selection_hash = _canonical_sha256(
        {
            "schema_version": _SELECTION_SCHEMA_VERSION,
            "candidate_rows": semantic_rows,
        }
    )
    if selection_hash != expected_selection_hash:
        return _invalid_evidence("EVIDENCE_SELECTION_HASH_MISMATCH", raw)
    if candidate_set_hash != _canonical_sha256(semantic_rows):
        return _invalid_evidence("CANDIDATE_SET_HASH_MISMATCH", raw)
    generated_at = _optional_utc_z(raw.get("generated_at"))
    evaluated_at = _optional_utc_z(raw.get("evaluated_at"))
    cost_source_asof = raw.get("cost_source_asof_utc")
    if cost_source_asof is not None:
        cost_source_asof = _optional_utc_z(cost_source_asof)
    if (
        generated_at is None
        or evaluated_at is None
        or not _is_hash(raw.get("source_content_sha256"))
        or not _is_hash(raw.get("board_hash"))
        or not _is_hash(raw.get("audit_hash"))
        or cost_source_asof is None
        and raw.get("cost_source_asof_utc") is not None
        or raw.get("cost_source_payload_sha256") is not None
        and not _is_hash(raw.get("cost_source_payload_sha256"))
        or raw.get("cost_normalized_projection_sha256") is not None
        and not _is_hash(raw.get("cost_normalized_projection_sha256"))
    ):
        return _invalid_evidence("EVIDENCE_HANDOFF_METADATA_INVALID", raw)
    return {
        "source_status": "READY",
        "selection_hash": selection_hash,
        "candidate_set_hash": candidate_set_hash,
        "candidate_rows": [copy.deepcopy(dict(row)) for row in rows],
        "handoff_evidence": {
            "schema_version": raw["schema_version"],
            "source_status": "READY",
            "source_content_sha256": raw["source_content_sha256"],
            "board_hash": raw["board_hash"],
            "selection_hash": selection_hash,
            "audit_hash": raw["audit_hash"],
            "candidate_set_hash": candidate_set_hash,
            "generated_at": generated_at,
            "evaluated_at": evaluated_at,
            "cost_source_payload_sha256": raw.get("cost_source_payload_sha256"),
            "cost_normalized_projection_sha256": raw.get(
                "cost_normalized_projection_sha256"
            ),
            "cost_source_asof_utc": cost_source_asof,
        },
    }


def _invalid_evidence(status: str, observed: Any) -> dict[str, Any]:
    return {
        "source_status": status,
        "selection_hash": None,
        "candidate_set_hash": None,
        "candidate_rows": [],
        "handoff_evidence": {
            "schema_version": EVIDENCE_SCHEMA_VERSION,
            "source_status": status,
            "source_content_sha256": None,
            "board_hash": None,
            "selection_hash": None,
            "audit_hash": None,
            "candidate_set_hash": None,
            "generated_at": None,
            "evaluated_at": None,
            "cost_source_payload_sha256": None,
            "cost_normalized_projection_sha256": None,
            "cost_source_asof_utc": None,
        },
    }


def _build_handoff_identity(
    *,
    evidence: Mapping[str, Any],
    source_head: str,
    source_set_hash: str,
    source_identities: list[dict[str, str]],
    evaluated_at: str,
    policy: Mapping[str, Any],
    policy_config_hash: Any,
    prior_decisions: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind only validated immutable inputs that can change a projection."""
    evidence_view = evidence.get("handoff_evidence")
    if not isinstance(evidence_view, Mapping):
        raise AlrCandidateLearningProjectionError("handoff_evidence_missing")
    normalized_evidence = copy.deepcopy(dict(evidence_view))
    source_status = evidence.get("source_status")
    if normalized_evidence.get("source_status") != source_status:
        raise AlrCandidateLearningProjectionError("handoff_evidence_status_mismatch")
    if source_status == "READY":
        generated_at = _canonical_utc_z(normalized_evidence.get("generated_at"))
        evidence_evaluated_at = _canonical_utc_z(
            normalized_evidence.get("evaluated_at")
        )
        if evidence_evaluated_at != evaluated_at or generated_at > evaluated_at:
            raise AlrCandidateLearningProjectionError("handoff_time_causality_invalid")
        cost_asof = normalized_evidence.get("cost_source_asof_utc")
        if cost_asof is not None and _canonical_utc_z(cost_asof) > generated_at:
            raise AlrCandidateLearningProjectionError("handoff_cost_time_causality_invalid")
    cursor = copy.deepcopy(source_identities[-1])
    identity = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "evidence": normalized_evidence,
        "source_head": source_head,
        "source_set_hash": source_set_hash,
        "source_cursor": cursor,
        "decision_time": evaluated_at,
        "policy_input_hash": _canonical_sha256(dict(policy)),
        "policy_config_hash": policy_config_hash,
        "prior_decisions_hash": _canonical_sha256(prior_decisions),
    }
    return {**identity, "handoff_hash": _canonical_sha256(identity)}


def _normalize_candidate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    status, semantic = validate_candidate_selection_row_v2(row)
    if (
        status is not None
        or semantic is None
        or semantic.get("arbiter_input_complete") is not True
    ):
        return {}
    blockers = semantic.get("blockers")
    if (
        isinstance(blockers, list)
        and "TAIL_COST_NOT_FULLY_RECOMPUTABLE" in blockers
    ):
        # Tail completeness is selection material but is not a field in the frozen
        # arbiter input v2 seam. Preserve one fail-closed assessment rather than
        # laundering the complete typed input into a selectable candidate.
        return {}
    typed = semantic.get("arbiter_input")
    return copy.deepcopy(dict(typed)) if isinstance(typed, Mapping) else {}


def _semantic_candidate_row(row: Mapping[str, Any]) -> dict[str, Any]:
    status, semantic = validate_candidate_selection_row_v2(row)
    if status is not None or semantic is None:
        raise ValueError(status or "candidate_row_invalid")
    return semantic


def _scanner_research_seeds(
    cycles: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    occurrences: Counter[str] = Counter()
    novelty: Counter[str] = Counter()
    for cycle in cycles:
        payload = cycle["canonical_payload"]
        candidates = payload.get("candidates")
        if isinstance(candidates, list):
            for candidate in candidates:
                if isinstance(candidate, Mapping):
                    symbol = candidate.get("symbol")
                    if isinstance(symbol, str) and symbol:
                        occurrences[symbol] += 1
        added = payload.get("added")
        if isinstance(added, list):
            for symbol in added:
                if isinstance(symbol, str) and symbol:
                    novelty[symbol] += 1
    return [
        {
            "symbol": symbol,
            "recurrence": occurrences[symbol],
            "novelty": novelty[symbol],
        }
        for symbol in sorted(set(occurrences) | set(novelty))
    ]


def _decision_code(raw: Mapping[str, Any], source_status: str) -> str:
    if source_status != "READY":
        return "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    if raw.get("policy_config_hash") is None:
        return "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    decision = raw.get("decision_code") or raw.get("decision")
    mapping = {
        "QUALIFIED_CANDIDATE_SELECTED": "QUALIFIED_CANDIDATE_SELECTED",
        "NO_QUALIFIED_CANDIDATE_COLLECT": (
            "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES"
        ),
        "NO_QUALIFIED_CANDIDATE_REPAIR": "NO_QUALIFIED_CANDIDATE_REPAIR_DATA",
    }
    if decision in mapping:
        return mapping[str(decision)]
    assessments = raw.get("evaluated_candidates")
    if isinstance(assessments, list):
        if any(
            isinstance(item, Mapping) and item.get("metrics") is None
            for item in assessments
        ):
            return "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
        states = {
            item.get("state") for item in assessments if isinstance(item, Mapping)
        }
        if "WAIT_COOLDOWN" in states:
            return "NO_QUALIFIED_CANDIDATE_WAIT_COOLDOWN"
        if "EXTERNAL_GAP" in states:
            return "NO_QUALIFIED_CANDIDATE_EXTERNAL_GAP"
        if "REPAIR_DATA_QUALITY" in states:
            return "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    return "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION"


def _decision_time(*values: Any) -> str:
    for value in values:
        normalized = _optional_utc_z(value)
        if normalized is not None:
            return normalized
    raise AlrCandidateLearningProjectionError("decision_time_missing")


def _edge(source_hash: str, artifact_hash: str) -> dict[str, str]:
    body = {
        "from_artifact_hash": source_hash,
        "to_artifact_hash": artifact_hash,
        "edge_role": "training_input",
    }
    return {**body, "edge_hash": _canonical_sha256(body)}


def _normalized_mappings(value: Any, reason: str) -> list[dict[str, Any]]:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes, bytearray))
        or not all(isinstance(item, Mapping) for item in value)
    ):
        raise AlrCandidateLearningProjectionError(reason)
    return [copy.deepcopy(dict(item)) for item in value]


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise AlrCandidateLearningProjectionError("canonical_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _canonical_utc_z(value: Any) -> str:
    normalized = _optional_utc_z(value)
    if normalized is None:
        raise AlrCandidateLearningProjectionError("source_ts_invalid")
    return normalized


def _optional_utc_z(value: Any) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.fullmatch(value))

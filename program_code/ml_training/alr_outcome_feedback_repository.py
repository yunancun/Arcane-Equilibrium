"""Append-only persistence for P2-5 outcome feedback and rotation artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ml_training.alr_outcome_feedback import validate_outcome_feedback


_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_KINDS = {"outcome_bridge", "outcome_feedback", "target_rotation"}
_EDGE_ROLES = {"candidate_outcome_bridge", "bridge_feedback", "feedback_rotation"}


class AlrOutcomeFeedbackRepositoryError(ValueError):
    """Outcome feedback cannot become an immutable ALR ledger record."""


class AlrOutcomeFeedbackConflict(AlrOutcomeFeedbackRepositoryError):
    """A run already has a different immutable feedback decision."""


def build_feedback_persistence_plan(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one pure feedback bundle for append-only PostgreSQL persistence."""
    validation = validate_outcome_feedback(result)
    if not validation.valid:
        raise AlrOutcomeFeedbackRepositoryError(
            f"feedback_validation_failed:{validation.reason}"
        )
    run_hash = _required_hash(result.get("run_hash"), "run_hash")
    candidate_hash = _required_hash(
        result.get("candidate_artifact_hash"), "candidate_artifact_hash"
    )
    feedback = _required_mapping(result.get("feedback"), "feedback")
    rotation = _required_mapping(result.get("rotation"), "rotation")
    feedback_status = feedback.get("feedback_status")
    if feedback_status not in {
        "DEFER_EVIDENCE",
        "EVIDENCE_OBSERVED_NO_PROMOTION",
        "BLOCKED_BOUNDARY",
    }:
        raise AlrOutcomeFeedbackRepositoryError("feedback_status_invalid")
    bridge_outcome = feedback.get("bridge_outcome")
    if bridge_outcome not in {"DEFER_EVIDENCE", "ADVANCED", "BLOCKED_BOUNDARY"}:
        raise AlrOutcomeFeedbackRepositoryError("bridge_outcome_invalid")
    if not isinstance(feedback.get("proof_packet_present"), bool):
        raise AlrOutcomeFeedbackRepositoryError("proof_packet_present_invalid")
    reward_record_count = feedback.get("reward_record_count")
    if (
        isinstance(reward_record_count, bool)
        or not isinstance(reward_record_count, int)
        or reward_record_count < 0
    ):
        raise AlrOutcomeFeedbackRepositoryError("reward_record_count_invalid")
    if rotation.get("rotate_next_target") is not (feedback_status == "DEFER_EVIDENCE"):
        raise AlrOutcomeFeedbackRepositoryError("rotation_target_invalid")
    if rotation.get("global_stop") is not (feedback_status == "BLOCKED_BOUNDARY"):
        raise AlrOutcomeFeedbackRepositoryError("rotation_stop_invalid")

    artifacts = _artifacts(result.get("artifacts"))
    artifacts_by_kind = {artifact["artifact_kind"]: artifact for artifact in artifacts}
    if set(artifacts_by_kind) != _ARTIFACT_KINDS:
        raise AlrOutcomeFeedbackRepositoryError("artifact_kinds_invalid")
    bridge_hash = artifacts_by_kind["outcome_bridge"]["artifact_hash"]
    feedback_hash = artifacts_by_kind["outcome_feedback"]["artifact_hash"]
    rotation_hash = artifacts_by_kind["target_rotation"]["artifact_hash"]
    if feedback.get("bridge_artifact_hash") != bridge_hash:
        raise AlrOutcomeFeedbackRepositoryError("bridge_artifact_ref_invalid")
    if rotation.get("feedback_artifact_hash") != feedback_hash:
        raise AlrOutcomeFeedbackRepositoryError("feedback_artifact_ref_invalid")
    edges = _edges(result.get("provenance_edges"), candidate_hash, artifacts)
    return {
        "run_hash": run_hash,
        "candidate_artifact_hash": candidate_hash,
        "feedback_artifact_hash": feedback_hash,
        "bridge_artifact_hash": bridge_hash,
        "rotation_artifact_hash": rotation_hash,
        "feedback_status": feedback_status,
        "bridge_outcome": bridge_outcome,
        "proof_packet_present": feedback["proof_packet_present"],
        "reward_record_count": reward_record_count,
        "rotate_next_target": rotation["rotate_next_target"],
        "global_stop": rotation["global_stop"],
        "no_authority": _all_false_mapping(result.get("no_authority"), "no_authority"),
        "authority_counters": _all_zero_mapping(
            result.get("authority_counters"), "authority_counters"
        ),
        "artifacts": artifacts,
        "edges": edges,
    }


def persist_outcome_feedback(connection: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    """Insert a feedback decision once; replay returns `DUPLICATE` without mutation."""
    plan = build_feedback_persistence_plan(result)
    try:
        with connection.cursor() as cursor:
            existing = _find_feedback(cursor, plan["run_hash"])
            if existing is not None:
                if existing != plan["feedback_artifact_hash"]:
                    raise AlrOutcomeFeedbackConflict("run_feedback_conflict")
                connection.commit()
                return _result("DUPLICATE", plan)
            for artifact in plan["artifacts"]:
                _insert_artifact(cursor, artifact)
            for edge in plan["edges"]:
                _insert_edge(cursor, edge)
            cursor.execute(
                "INSERT INTO learning.alr_outcome_feedback_events "
                "(feedback_artifact_hash, run_hash, candidate_artifact_hash, "
                "bridge_artifact_hash, rotation_artifact_hash, feedback_status, "
                "bridge_outcome, proof_packet_present, reward_record_count, "
                "rotate_next_target, global_stop, no_authority, authority_counters) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
                "ON CONFLICT (run_hash) DO NOTHING RETURNING feedback_artifact_hash",
                (
                    plan["feedback_artifact_hash"],
                    plan["run_hash"],
                    plan["candidate_artifact_hash"],
                    plan["bridge_artifact_hash"],
                    plan["rotation_artifact_hash"],
                    plan["feedback_status"],
                    plan["bridge_outcome"],
                    plan["proof_packet_present"],
                    plan["reward_record_count"],
                    plan["rotate_next_target"],
                    plan["global_stop"],
                    _canonical_json(plan["no_authority"]),
                    _canonical_json(plan["authority_counters"]),
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raced = _find_feedback(cursor, plan["run_hash"])
                if raced != plan["feedback_artifact_hash"]:
                    raise AlrOutcomeFeedbackConflict("run_feedback_conflict")
                connection.commit()
                return _result("DUPLICATE", plan)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _result("PERSISTED", plan)


def fetch_unreviewed_outcome_runs(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    """Read bounded P2-4 runs that have no durable P2-5 feedback event yet."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
        raise AlrOutcomeFeedbackRepositoryError("feedback_fetch_limit_invalid")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT run.run_hash, run.candidate_artifact_hash, "
            "candidate.canonical_payload AS candidate_artifact "
            "FROM learning.alr_training_runs AS run "
            "JOIN learning.alr_artifact_nodes AS candidate "
            "ON candidate.artifact_hash = run.candidate_artifact_hash "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM learning.alr_outcome_feedback_events AS feedback "
            "WHERE feedback.run_hash = run.run_hash"
            ") ORDER BY run.created_at ASC, run.run_hash ASC LIMIT %s",
            (limit,),
        )
        rows = cursor.fetchall()
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise AlrOutcomeFeedbackRepositoryError("feedback_fetch_rows_invalid")
    return [dict(row) for row in rows]


def _find_feedback(cursor: Any, run_hash: str) -> str | None:
    cursor.execute(
        "SELECT feedback_artifact_hash FROM learning.alr_outcome_feedback_events "
        "WHERE run_hash = %s",
        (run_hash,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    value = row["feedback_artifact_hash"] if isinstance(row, Mapping) else row[0]
    return _required_hash(value, "existing_feedback_hash")


def _insert_artifact(cursor: Any, artifact: Mapping[str, Any]) -> None:
    cursor.execute(
        "INSERT INTO learning.alr_artifact_nodes "
        "(artifact_hash, artifact_kind, canonical_payload) VALUES (%s, %s, %s::jsonb) "
        "ON CONFLICT (artifact_hash) DO NOTHING",
        (
            artifact["artifact_hash"],
            artifact["artifact_kind"],
            _canonical_json(artifact["canonical_payload"]),
        ),
    )


def _insert_edge(cursor: Any, edge: Mapping[str, Any]) -> None:
    cursor.execute(
        "INSERT INTO learning.alr_provenance_edges "
        "(edge_hash, from_artifact_hash, to_artifact_hash, edge_role) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (edge_hash) DO NOTHING",
        (
            edge["edge_hash"],
            edge["from_artifact_hash"],
            edge["to_artifact_hash"],
            edge["edge_role"],
        ),
    )


def _artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(_ARTIFACT_KINDS):
        raise AlrOutcomeFeedbackRepositoryError("artifacts_invalid")
    seen_hashes: set[str] = set()
    artifacts: list[dict[str, Any]] = []
    for artifact in value:
        if not isinstance(artifact, Mapping):
            raise AlrOutcomeFeedbackRepositoryError("artifact_not_mapping")
        kind = artifact.get("artifact_kind")
        if kind not in _ARTIFACT_KINDS:
            raise AlrOutcomeFeedbackRepositoryError("artifact_kind_invalid")
        artifact_hash = _required_hash(artifact.get("artifact_hash"), "artifact_hash")
        payload = artifact.get("canonical_payload")
        if artifact_hash in seen_hashes or not isinstance(payload, Mapping):
            raise AlrOutcomeFeedbackRepositoryError("artifact_payload_invalid")
        if artifact_hash != _canonical_sha256(payload):
            raise AlrOutcomeFeedbackRepositoryError("artifact_hash_mismatch")
        seen_hashes.add(artifact_hash)
        artifacts.append(
            {
                "artifact_kind": kind,
                "artifact_hash": artifact_hash,
                "canonical_payload": copy.deepcopy(dict(payload)),
            }
        )
    return artifacts


def _edges(
    value: Any,
    candidate_hash: str,
    artifacts: Sequence[Mapping[str, Any]],
) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != len(_EDGE_ROLES):
        raise AlrOutcomeFeedbackRepositoryError("edges_invalid")
    valid_hashes = {candidate_hash} | {str(item["artifact_hash"]) for item in artifacts}
    edges: list[dict[str, str]] = []
    seen_hashes: set[str] = set()
    for edge in value:
        if not isinstance(edge, Mapping):
            raise AlrOutcomeFeedbackRepositoryError("edge_not_mapping")
        edge_hash = _required_hash(edge.get("edge_hash"), "edge_hash")
        from_hash = _required_hash(edge.get("from_artifact_hash"), "edge_from_hash")
        to_hash = _required_hash(edge.get("to_artifact_hash"), "edge_to_hash")
        role = edge.get("edge_role")
        if (
            role not in _EDGE_ROLES
            or from_hash == to_hash
            or from_hash not in valid_hashes
            or to_hash not in valid_hashes
        ):
            raise AlrOutcomeFeedbackRepositoryError("edge_invalid")
        if edge_hash != _canonical_sha256(
            {
                "from_artifact_hash": from_hash,
                "to_artifact_hash": to_hash,
                "edge_role": role,
            }
        ) or edge_hash in seen_hashes:
            raise AlrOutcomeFeedbackRepositoryError("edge_hash_invalid")
        seen_hashes.add(edge_hash)
        edges.append(
            {
                "edge_hash": edge_hash,
                "from_artifact_hash": from_hash,
                "to_artifact_hash": to_hash,
                "edge_role": role,
            }
        )
    if {edge["edge_role"] for edge in edges} != _EDGE_ROLES:
        raise AlrOutcomeFeedbackRepositoryError("edge_roles_incomplete")
    return edges


def _all_false_mapping(value: Any, field: str) -> dict[str, bool]:
    if not isinstance(value, Mapping) or not value or any(item is not False for item in value.values()):
        raise AlrOutcomeFeedbackRepositoryError(f"{field}_invalid")
    return {str(key): False for key in value}


def _all_zero_mapping(value: Any, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or not value:
        raise AlrOutcomeFeedbackRepositoryError(f"{field}_invalid")
    if any(not isinstance(item, int) or isinstance(item, bool) or item != 0 for item in value.values()):
        raise AlrOutcomeFeedbackRepositoryError(f"{field}_invalid")
    return {str(key): 0 for key in value}


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrOutcomeFeedbackRepositoryError(f"{field}_invalid")
    return value


def _required_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise AlrOutcomeFeedbackRepositoryError(f"{field}_invalid")
    return value


def _result(status: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "run_hash": plan["run_hash"],
        "feedback_artifact_hash": plan["feedback_artifact_hash"],
        "feedback_status": plan["feedback_status"],
        "rotate_next_target": plan["rotate_next_target"],
        "global_stop": plan["global_stop"],
        "no_authority": dict(plan["no_authority"]),
        "authority_counters": dict(plan["authority_counters"]),
    }


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

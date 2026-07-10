"""Append-only repository for P2-4 scanner statistical experiment artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta, timezone
from typing import Any

from ml_training.pit_dataset_manifest import compute_pit_dataset_manifest_hash
from ml_training.alr_scanner_statistical_experiment import (
    validate_scanner_statistical_experiment,
)


SOURCE_TABLE = "trading.scanner_snapshots"
RUN_KIND = "scanner_novelty_statistical_baseline"
RUN_STATUS = "DEFER_EVIDENCE"
SUPPRESSION_ARTIFACT_KIND = "target_rotation"
SUPPRESSION_SCHEMA_VERSION = "alr_equivalent_defer_suppression_v1"
MAX_DEFER_SUPPRESSION_SECONDS = 1800
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_ARTIFACT_KINDS = {
    "learning_target",
    "pit_dataset",
    "statistical_experiment",
    "candidate_artifact",
    "defer_evidence",
}
_EDGE_ROLES = {
    "training_input",
    "target_dataset",
    "dataset_experiment",
    "experiment_candidate",
    "candidate_defer_evidence",
}


class AlrOperationalError(ValueError):
    """A P2-4 run cannot be accepted as append-only ALR evidence."""


class AlrOperationalConflict(AlrOperationalError):
    """A source-set identity already points to a different immutable run."""


def build_statistical_run_plan(result: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one research-only experiment for immutable storage."""
    validation = validate_scanner_statistical_experiment(result)
    if not validation.valid:
        raise AlrOperationalError(f"experiment_validation_failed:{validation.reason}")

    source_head = _required_hash(result.get("source_head"), "source_head", length=40)
    source_set = _required_mapping(result.get("source_set"), "source_set")
    source_set_hash = _required_hash(source_set.get("source_set_hash"), "source_set_hash")
    source_hashes = _hash_list(source_set.get("source_hashes"), "source_hashes")
    if len(source_hashes) != int(source_set.get("cycle_count", 0)):
        raise AlrOperationalError("source_count_mismatch")
    if _canonical_sha256(source_hashes) != source_set_hash:
        raise AlrOperationalError("source_set_hash_mismatch")
    source_identities = _source_identities(
        source_set.get("source_identities"),
        source_hashes=source_hashes,
    )
    as_of_ts = _canonical_utc_z(source_set.get("as_of_ts"))
    as_of_time = _parse_utc_z(as_of_ts)
    if as_of_time != max(
        _parse_utc_z(identity["source_ts"]) for identity in source_identities
    ):
        raise AlrOperationalError("source_set_as_of_mismatch")

    run = _required_mapping(result.get("run"), "run")
    run_hash = _required_hash(run.get("run_hash"), "run_hash")
    if run.get("run_kind") != RUN_KIND:
        raise AlrOperationalError("run_kind_invalid")
    if run.get("run_status") != RUN_STATUS:
        raise AlrOperationalError("run_status_invalid")
    if run.get("source_set_hash") != source_set_hash:
        raise AlrOperationalError("run_source_set_mismatch")
    computed_run_hash = _canonical_sha256({key: value for key, value in run.items() if key != "run_hash"})
    if run_hash != computed_run_hash:
        raise AlrOperationalError("run_hash_mismatch")

    artifacts = _artifacts(result.get("artifacts"))
    artifacts_by_kind = {artifact["artifact_kind"]: artifact for artifact in artifacts}
    if set(artifacts_by_kind) != _ARTIFACT_KINDS:
        raise AlrOperationalError("artifact_kinds_invalid")
    _validate_run_artifact_refs(run, artifacts_by_kind)
    candidate_payload = _required_mapping(
        artifacts_by_kind["candidate_artifact"]["canonical_payload"],
        "candidate_payload",
    )
    defer_payload = _required_mapping(
        artifacts_by_kind["defer_evidence"]["canonical_payload"],
        "defer_payload",
    )
    decision_fingerprint = _required_hash(
        candidate_payload.get("decision_fingerprint"),
        "decision_fingerprint",
    )
    fingerprint_components = _required_mapping(
        candidate_payload.get("decision_fingerprint_components"),
        "decision_fingerprint_components",
    )
    if decision_fingerprint != _canonical_sha256(fingerprint_components):
        raise AlrOperationalError("decision_fingerprint_mismatch")
    decision_policy_hash = _required_hash(
        candidate_payload.get("decision_policy_hash"),
        "decision_policy_hash",
    )
    if fingerprint_components.get("decision_policy_hash") != decision_policy_hash:
        raise AlrOperationalError("decision_policy_hash_mismatch")
    if fingerprint_components.get("source_head") != source_head:
        raise AlrOperationalError("decision_source_head_mismatch")
    reevaluation_policy = _required_mapping(
        fingerprint_components.get("reevaluation_policy"),
        "reevaluation_policy",
    )
    if _canonical_sha256(reevaluation_policy) != decision_policy_hash:
        raise AlrOperationalError("decision_policy_payload_hash_mismatch")
    suppression_seconds = reevaluation_policy.get("max_suppression_seconds")
    if (
        isinstance(suppression_seconds, bool)
        or not isinstance(suppression_seconds, int)
        or not 1 <= suppression_seconds <= MAX_DEFER_SUPPRESSION_SECONDS
    ):
        raise AlrOperationalError("decision_suppression_ttl_invalid")
    if (
        reevaluation_policy.get("decision") != "DEFER_EVIDENCE"
        or reevaluation_policy.get("rotation_required") is not True
        or reevaluation_policy.get("global_stop") is not False
        or reevaluation_policy.get("freshness_basis") != "source_event_time"
        or reevaluation_policy.get("require_distinct_source_set") is not True
        or reevaluation_policy.get("legacy_packet_reuse_allowed") is not False
    ):
        raise AlrOperationalError("decision_reevaluation_policy_invalid")
    if (
        defer_payload.get("decision_fingerprint") != decision_fingerprint
        or defer_payload.get("decision_policy_hash") != decision_policy_hash
    ):
        raise AlrOperationalError("defer_decision_fingerprint_mismatch")
    candidate_evaluated_at = _canonical_utc_z(
        candidate_payload.get("evaluated_at")
    )
    defer_evaluated_at = _canonical_utc_z(defer_payload.get("evaluated_at"))
    if candidate_evaluated_at != as_of_ts:
        raise AlrOperationalError("candidate_evaluated_at_mismatch")
    if defer_evaluated_at != as_of_ts:
        raise AlrOperationalError("defer_evaluated_at_mismatch")
    candidate_next_due_at = _canonical_utc_z(
        candidate_payload.get("next_evaluation_due_at")
    )
    defer_next_due_at = _canonical_utc_z(
        defer_payload.get("next_evaluation_due_at")
    )
    expected_next_due_at = (
        as_of_time + timedelta(seconds=suppression_seconds)
    ).isoformat().replace("+00:00", "Z")
    if candidate_next_due_at != expected_next_due_at:
        raise AlrOperationalError("candidate_next_evaluation_due_at_mismatch")
    if defer_next_due_at != expected_next_due_at:
        raise AlrOperationalError("defer_next_evaluation_due_at_mismatch")
    if (
        candidate_payload.get("target_artifact_hash")
        != artifacts_by_kind["learning_target"]["artifact_hash"]
        or candidate_payload.get("pit_dataset_manifest_hash")
        != artifacts_by_kind["pit_dataset"]["artifact_hash"]
        or candidate_payload.get("statistical_experiment_hash")
        != artifacts_by_kind["statistical_experiment"]["artifact_hash"]
        or defer_payload.get("candidate_artifact_hash")
        != artifacts_by_kind["candidate_artifact"]["artifact_hash"]
    ):
        raise AlrOperationalError("decision_artifact_reference_mismatch")
    edges = _edges(result.get("provenance_edges"), artifacts, source_hashes)

    no_authority = _all_false_mapping(result.get("no_authority"), "no_authority")
    authority_counters = _all_zero_mapping(
        result.get("authority_counters"), "authority_counters"
    )
    if (
        candidate_payload.get("no_authority") != no_authority
        or defer_payload.get("no_authority") != no_authority
    ):
        raise AlrOperationalError("decision_no_authority_mismatch")
    return {
        "run_hash": run_hash,
        "run_kind": RUN_KIND,
        "run_status": RUN_STATUS,
        "source_head": source_head,
        "source_set_hash": source_set_hash,
        "source_count": len(source_hashes),
        "source_hashes": source_hashes,
        "source_identities": source_identities,
        "as_of_ts": as_of_ts,
        "decision_fingerprint": decision_fingerprint,
        "decision_policy_hash": decision_policy_hash,
        "decision_fingerprint_components": copy.deepcopy(
            dict(fingerprint_components)
        ),
        "target_artifact_hash": run["target_artifact_hash"],
        "pit_dataset_artifact_hash": run["pit_dataset_artifact_hash"],
        "experiment_artifact_hash": run["experiment_artifact_hash"],
        "candidate_artifact_hash": run["candidate_artifact_hash"],
        "defer_artifact_hash": run["defer_artifact_hash"],
        "artifacts": artifacts,
        "edges": edges,
        "no_authority": no_authority,
        "authority_counters": authority_counters,
    }


def persist_statistical_run(connection: Any, result: Mapping[str, Any]) -> dict[str, Any]:
    """Persist a run once; same source-set replay is an immutable duplicate."""
    plan = build_statistical_run_plan(result)
    try:
        with connection.cursor() as cursor:
            existing = _find_run(cursor, plan)
            if existing is not None:
                if existing != plan["run_hash"]:
                    raise AlrOperationalConflict("source_set_run_conflict")
                connection.commit()
                return _result("DUPLICATE", plan)

            reusable = _find_reusable_defer(cursor, plan)
            if reusable is not None:
                suppression = _build_suppression_artifact(plan, reusable)
                existing_suppression = _find_artifact_payload(
                    cursor,
                    suppression["artifact_hash"],
                )
                if existing_suppression is not None:
                    if existing_suppression != suppression["canonical_payload"]:
                        raise AlrOperationalConflict(
                            "suppression_artifact_hash_conflict"
                        )
                    if not _suppression_edges_complete(
                        cursor,
                        suppression["source_edges"],
                    ):
                        raise AlrOperationalConflict(
                            "suppression_artifact_lineage_incomplete"
                        )
                    connection.commit()
                    return _suppression_result(
                        plan,
                        suppression,
                        duplicate=True,
                    )
                artifact_rows_written = int(
                    _insert_artifact(cursor, suppression)
                )
                provenance_rows_written = 0
                for edge in suppression["source_edges"]:
                    provenance_rows_written += int(_insert_edge(cursor, edge))
                if (
                    artifact_rows_written != 1
                    or provenance_rows_written
                    != len(suppression["source_edges"])
                ):
                    raise AlrOperationalConflict(
                        "suppression_write_count_incomplete"
                    )
                connection.commit()
                return _suppression_result(
                    plan,
                    suppression,
                    artifact_rows_written=artifact_rows_written,
                    provenance_rows_written=provenance_rows_written,
                )

            artifact_rows_written = 0
            defer_artifact_rows_written = 0
            payload_bytes_written = 0
            for artifact in plan["artifacts"]:
                inserted = _insert_artifact(cursor, artifact)
                artifact_rows_written += int(inserted)
                if inserted:
                    payload_bytes_written += len(
                        _canonical_json(
                            artifact["canonical_payload"]
                        ).encode("utf-8")
                    )
                    defer_artifact_rows_written += int(
                        artifact["artifact_kind"] == "defer_evidence"
                    )
            provenance_rows_written = 0
            source_rows_consumed = 0
            for edge in plan["edges"]:
                inserted = _insert_edge(cursor, edge)
                provenance_rows_written += int(inserted)
                if inserted and edge["edge_role"] == "training_input":
                    source_rows_consumed += 1

            cursor.execute(
                "INSERT INTO learning.alr_training_runs "
                "(run_hash, source_set_hash, run_kind, run_status, source_head, source_count, "
                "target_artifact_hash, pit_dataset_artifact_hash, experiment_artifact_hash, "
                "candidate_artifact_hash, defer_artifact_hash, no_authority, authority_counters) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb) "
                "ON CONFLICT (source_set_hash, run_kind) DO NOTHING RETURNING run_hash",
                (
                    plan["run_hash"],
                    plan["source_set_hash"],
                    plan["run_kind"],
                    plan["run_status"],
                    plan["source_head"],
                    plan["source_count"],
                    plan["target_artifact_hash"],
                    plan["pit_dataset_artifact_hash"],
                    plan["experiment_artifact_hash"],
                    plan["candidate_artifact_hash"],
                    plan["defer_artifact_hash"],
                    _canonical_json(plan["no_authority"]),
                    _canonical_json(plan["authority_counters"]),
                ),
            )
            inserted = cursor.fetchone()
            if inserted is None:
                raced = _find_run(cursor, plan)
                if raced != plan["run_hash"]:
                    raise AlrOperationalConflict("source_set_run_conflict")
                connection.commit()
                return _result(
                    "DUPLICATE",
                    plan,
                    artifact_rows_written=artifact_rows_written,
                    provenance_rows_written=provenance_rows_written,
                    defer_artifact_rows_written=defer_artifact_rows_written,
                    payload_bytes_written=payload_bytes_written,
                    source_rows_consumed=source_rows_consumed,
                )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _result(
        "PERSISTED",
        plan,
        artifact_rows_written=artifact_rows_written,
        provenance_rows_written=provenance_rows_written,
        run_rows_written=1,
        defer_artifact_rows_written=defer_artifact_rows_written,
        payload_bytes_written=payload_bytes_written,
        source_rows_consumed=source_rows_consumed,
    )


def fetch_untrained_scanner_cycles(connection: Any, *, limit: int) -> list[dict[str, Any]]:
    """Read only ALR-ledger scanner cycles without a P2-4 training-input edge."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 3 <= limit <= 64:
        raise AlrOperationalError("untrained_fetch_limit_invalid")
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT source.source_hash, source.source_key, source.source_ts, "
            "node.canonical_payload "
            "FROM learning.alr_source_events AS source "
            "JOIN learning.alr_artifact_nodes AS node "
            "ON node.artifact_hash = source.source_hash "
            "WHERE source.source_table = %s AND NOT EXISTS ("
            "SELECT 1 FROM learning.alr_provenance_edges AS edge "
            "WHERE edge.from_artifact_hash = source.source_hash "
            "AND edge.edge_role = 'training_input'"
            ") ORDER BY source.source_ts ASC, source.source_scan_id ASC LIMIT %s",
            (SOURCE_TABLE, limit),
        )
        rows = cursor.fetchall()
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise AlrOperationalError("untrained_fetch_rows_invalid")
    normalized: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["source_ts"] = _canonical_utc_z(item.get("source_ts"))
        normalized.append(item)
    return normalized


def _find_reusable_defer(
    cursor: Any,
    plan: Mapping[str, Any],
) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT run.run_hash, run.candidate_artifact_hash, run.defer_artifact_hash, "
        "candidate.canonical_payload AS candidate_payload, "
        "defer.canonical_payload AS defer_payload "
        "FROM learning.alr_training_runs AS run "
        "JOIN learning.alr_artifact_nodes AS candidate "
        "ON candidate.artifact_hash = run.candidate_artifact_hash "
        "JOIN learning.alr_artifact_nodes AS defer "
        "ON defer.artifact_hash = run.defer_artifact_hash "
        "WHERE run.run_status = 'DEFER_EVIDENCE' "
        "AND run.run_kind = %s "
        "AND run.source_head = %s "
        "AND candidate.canonical_payload ->> 'decision_fingerprint' = %s "
        "AND candidate.canonical_payload ->> 'decision_policy_hash' = %s "
        "ORDER BY run.created_at DESC, run.run_hash DESC LIMIT 1",
        (
            plan["run_kind"],
            plan["source_head"],
            plan["decision_fingerprint"],
            plan["decision_policy_hash"],
        ),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    candidate_payload = _required_mapping(
        _row_field(row, 3, "candidate_payload"),
        "reusable_candidate_payload",
    )
    defer_payload = _required_mapping(
        _row_field(row, 4, "defer_payload"),
        "reusable_defer_payload",
    )
    if (
        candidate_payload.get("candidate_status") != "CHALLENGER_RESEARCH_ONLY"
        or candidate_payload.get("decision_fingerprint")
        != plan["decision_fingerprint"]
        or candidate_payload.get("decision_policy_hash")
        != plan["decision_policy_hash"]
        or candidate_payload.get("no_authority") != plan["no_authority"]
        or defer_payload.get("status") != "DEFER_EVIDENCE"
        or defer_payload.get("decision_fingerprint") != plan["decision_fingerprint"]
        or defer_payload.get("decision_policy_hash") != plan["decision_policy_hash"]
        or defer_payload.get("rotate_next_target") is not True
        or defer_payload.get("global_stop") is not False
        or defer_payload.get("no_authority") != plan["no_authority"]
    ):
        return None
    evaluated_at = _parse_utc_z(candidate_payload.get("evaluated_at"))
    next_due_at = _parse_utc_z(candidate_payload.get("next_evaluation_due_at"))
    current_as_of = _parse_utc_z(plan["as_of_ts"])
    if current_as_of < evaluated_at or current_as_of >= next_due_at:
        return None
    return {
        "run_hash": _required_hash(
            _row_field(row, 0, "run_hash"),
            "reusable_run_hash",
        ),
        "candidate_artifact_hash": _required_hash(
            _row_field(row, 1, "candidate_artifact_hash"),
            "reusable_candidate_hash",
        ),
        "defer_artifact_hash": _required_hash(
            _row_field(row, 2, "defer_artifact_hash"),
            "reusable_defer_hash",
        ),
        "evaluated_at": evaluated_at.isoformat().replace("+00:00", "Z"),
        "next_evaluation_due_at": next_due_at.isoformat().replace(
            "+00:00", "Z"
        ),
        "prior_decision_age_seconds": int(
            (current_as_of - evaluated_at).total_seconds()
        ),
    }


def _build_suppression_artifact(
    plan: Mapping[str, Any],
    reusable: Mapping[str, Any],
) -> dict[str, Any]:
    payload = {
        "schema_version": SUPPRESSION_SCHEMA_VERSION,
        "source_set_hash": plan["source_set_hash"],
        "source_identities": copy.deepcopy(list(plan["source_identities"])),
        "decision_fingerprint": plan["decision_fingerprint"],
        "decision_policy_hash": plan["decision_policy_hash"],
        "decision_fingerprint_components": copy.deepcopy(
            dict(plan["decision_fingerprint_components"])
        ),
        "reason": "IDENTICAL_CANDIDATE_REGIME_EVIDENCE_BLOCKERS_WITHIN_TTL",
        "reused_decision_ref": {
            "run_hash": reusable["run_hash"],
            "candidate_artifact_hash": reusable["candidate_artifact_hash"],
            "defer_artifact_hash": reusable["defer_artifact_hash"],
        },
        "reused_decision_refs": [
            reusable["run_hash"],
            reusable["candidate_artifact_hash"],
            reusable["defer_artifact_hash"],
        ],
        "prior_decision_age_seconds": reusable["prior_decision_age_seconds"],
        "next_evaluation_due_at": reusable["next_evaluation_due_at"],
        "action": "SUPPRESS_EQUIVALENT_DEFER_AND_ROTATE",
        "run_created": False,
        "feedback_created": False,
        "defer_artifact_created": False,
        "no_authority": copy.deepcopy(dict(plan["no_authority"])),
        "authority_counters": copy.deepcopy(dict(plan["authority_counters"])),
    }
    artifact_hash = _canonical_sha256(payload)
    source_edges = [
        _suppression_edge(identity["source_hash"], artifact_hash)
        for identity in plan["source_identities"]
    ]
    return {
        "artifact_kind": SUPPRESSION_ARTIFACT_KIND,
        "artifact_hash": artifact_hash,
        "canonical_payload": payload,
        "source_edges": source_edges,
    }


def _suppression_edge(source_hash: str, artifact_hash: str) -> dict[str, str]:
    edge = {
        "from_artifact_hash": source_hash,
        "to_artifact_hash": artifact_hash,
        "edge_role": "training_input",
    }
    edge["edge_hash"] = _canonical_sha256(edge)
    return edge


def _find_run(cursor: Any, plan: Mapping[str, Any]) -> str | None:
    cursor.execute(
        "SELECT run_hash FROM learning.alr_training_runs "
        "WHERE source_set_hash = %s AND run_kind = %s",
        (plan["source_set_hash"], plan["run_kind"]),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    value = row["run_hash"] if isinstance(row, Mapping) else row[0]
    return _required_hash(value, "existing_run_hash")


def _find_artifact_payload(cursor: Any, artifact_hash: str) -> dict[str, Any] | None:
    cursor.execute(
        "SELECT canonical_payload FROM learning.alr_artifact_nodes "
        "WHERE artifact_hash = %s",
        (artifact_hash,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    payload = _row_field(row, 0, "canonical_payload")
    if not isinstance(payload, Mapping):
        raise AlrOperationalError("existing_artifact_payload_invalid")
    return copy.deepcopy(dict(payload))


def _suppression_edges_complete(
    cursor: Any,
    edges: Sequence[Mapping[str, str]],
) -> bool:
    edge_hashes = [edge["edge_hash"] for edge in edges]
    cursor.execute(
        "SELECT count(*) FROM learning.alr_provenance_edges "
        "WHERE edge_hash = ANY(%s)",
        (edge_hashes,),
    )
    row = cursor.fetchone()
    count = _row_field(row, 0, "count") if row is not None else None
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise AlrOperationalError("suppression_edge_count_invalid")
    return count == len(edge_hashes)


def _insert_artifact(cursor: Any, artifact: Mapping[str, Any]) -> bool:
    cursor.execute(
        "INSERT INTO learning.alr_artifact_nodes "
        "(artifact_hash, artifact_kind, canonical_payload) VALUES (%s, %s, %s::jsonb) "
        "ON CONFLICT (artifact_hash) DO NOTHING RETURNING artifact_hash",
        (
            artifact["artifact_hash"],
            artifact["artifact_kind"],
            _canonical_json(artifact["canonical_payload"]),
        ),
    )
    row = cursor.fetchone()
    if row is None:
        return False
    inserted_hash = _required_hash(
        _row_field(row, 0, "artifact_hash"),
        "inserted_artifact_hash",
    )
    if inserted_hash != artifact["artifact_hash"]:
        raise AlrOperationalError("inserted_artifact_hash_mismatch")
    return True


def _insert_edge(cursor: Any, edge: Mapping[str, Any]) -> bool:
    cursor.execute(
        "INSERT INTO learning.alr_provenance_edges "
        "(edge_hash, from_artifact_hash, to_artifact_hash, edge_role) "
        "VALUES (%s, %s, %s, %s) ON CONFLICT (edge_hash) DO NOTHING "
        "RETURNING edge_hash",
        (
            edge["edge_hash"],
            edge["from_artifact_hash"],
            edge["to_artifact_hash"],
            edge["edge_role"],
        ),
    )
    row = cursor.fetchone()
    if row is None:
        return False
    inserted_hash = _required_hash(
        _row_field(row, 0, "edge_hash"),
        "inserted_edge_hash",
    )
    if inserted_hash != edge["edge_hash"]:
        raise AlrOperationalError("inserted_edge_hash_mismatch")
    return True


def _artifacts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) != len(_ARTIFACT_KINDS):
        raise AlrOperationalError("artifacts_invalid")
    artifacts: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    for artifact in value:
        if not isinstance(artifact, Mapping):
            raise AlrOperationalError("artifact_not_mapping")
        kind = artifact.get("artifact_kind")
        if kind not in _ARTIFACT_KINDS:
            raise AlrOperationalError("artifact_kind_invalid")
        artifact_hash = _required_hash(artifact.get("artifact_hash"), "artifact_hash")
        if artifact_hash in seen_hashes:
            raise AlrOperationalError("artifact_hash_duplicate")
        payload = artifact.get("canonical_payload")
        if not isinstance(payload, Mapping):
            raise AlrOperationalError("artifact_payload_invalid")
        expected_hash = (
            compute_pit_dataset_manifest_hash(payload)
            if kind == "pit_dataset"
            else _canonical_sha256(payload)
        )
        if artifact_hash != expected_hash:
            raise AlrOperationalError("artifact_hash_mismatch")
        seen_hashes.add(artifact_hash)
        artifacts.append(
            {
                "artifact_kind": kind,
                "artifact_hash": artifact_hash,
                "canonical_payload": copy.deepcopy(dict(payload)),
            }
        )
    return artifacts


def _validate_run_artifact_refs(
    run: Mapping[str, Any], artifacts_by_kind: Mapping[str, Mapping[str, Any]]
) -> None:
    expected = {
        "target_artifact_hash": "learning_target",
        "pit_dataset_artifact_hash": "pit_dataset",
        "experiment_artifact_hash": "statistical_experiment",
        "candidate_artifact_hash": "candidate_artifact",
        "defer_artifact_hash": "defer_evidence",
    }
    for field, kind in expected.items():
        value = _required_hash(run.get(field), field)
        if value != artifacts_by_kind[kind]["artifact_hash"]:
            raise AlrOperationalError(f"run_artifact_ref_mismatch:{field}")


def _edges(
    value: Any,
    artifacts: Sequence[Mapping[str, Any]],
    source_hashes: Sequence[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise AlrOperationalError("provenance_edges_invalid")
    valid_nodes = set(source_hashes) | {str(artifact["artifact_hash"]) for artifact in artifacts}
    edges: list[dict[str, str]] = []
    seen_hashes: set[str] = set()
    for edge in value:
        if not isinstance(edge, Mapping):
            raise AlrOperationalError("provenance_edge_not_mapping")
        edge_hash = _required_hash(edge.get("edge_hash"), "edge_hash")
        from_hash = _required_hash(edge.get("from_artifact_hash"), "edge_from_hash")
        to_hash = _required_hash(edge.get("to_artifact_hash"), "edge_to_hash")
        role = edge.get("edge_role")
        if role not in _EDGE_ROLES or from_hash == to_hash:
            raise AlrOperationalError("provenance_edge_invalid")
        if from_hash not in valid_nodes or to_hash not in valid_nodes:
            raise AlrOperationalError("provenance_edge_node_unknown")
        expected_hash = _canonical_sha256(
            {
                "from_artifact_hash": from_hash,
                "to_artifact_hash": to_hash,
                "edge_role": role,
            }
        )
        if edge_hash != expected_hash or edge_hash in seen_hashes:
            raise AlrOperationalError("provenance_edge_hash_invalid")
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
        raise AlrOperationalError("provenance_edge_roles_incomplete")
    if sum(edge["edge_role"] == "training_input" for edge in edges) != len(source_hashes):
        raise AlrOperationalError("training_input_edges_incomplete")
    return edges


def _all_false_mapping(value: Any, field: str) -> dict[str, bool]:
    if not isinstance(value, Mapping) or not value or any(item is not False for item in value.values()):
        raise AlrOperationalError(f"{field}_invalid")
    return {str(key): False for key in value}


def _all_zero_mapping(value: Any, field: str) -> dict[str, int]:
    if not isinstance(value, Mapping) or not value:
        raise AlrOperationalError(f"{field}_invalid")
    if any(not isinstance(item, int) or isinstance(item, bool) or item != 0 for item in value.values()):
        raise AlrOperationalError(f"{field}_invalid")
    return {str(key): 0 for key in value}


def _hash_list(value: Any, field: str) -> list[str]:
    if not isinstance(value, list) or len(value) < 3:
        raise AlrOperationalError(f"{field}_invalid")
    result = [_required_hash(item, field) for item in value]
    if len(set(result)) != len(result):
        raise AlrOperationalError(f"{field}_duplicate")
    return result


def _source_identities(
    value: Any,
    *,
    source_hashes: Sequence[str],
) -> list[dict[str, str]]:
    if not isinstance(value, list) or len(value) != len(source_hashes):
        raise AlrOperationalError("source_identities_invalid")
    identities: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            raise AlrOperationalError("source_identity_invalid")
        source_hash = _required_hash(item.get("source_hash"), "source_identity_hash")
        source_key = item.get("source_key")
        if not isinstance(source_key, str) or not source_key:
            raise AlrOperationalError("source_identity_key_invalid")
        identities.append(
            {
                "source_hash": source_hash,
                "source_key": source_key,
                "source_ts": _canonical_utc_z(item.get("source_ts")),
            }
        )
    if [item["source_hash"] for item in identities] != list(source_hashes):
        raise AlrOperationalError("source_identity_hash_order_mismatch")
    return identities


def _required_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AlrOperationalError(f"{field}_invalid")
    return value


def _required_hash(value: Any, field: str, *, length: int = 64) -> str:
    if not isinstance(value, str):
        raise AlrOperationalError(f"{field}_invalid")
    expression = _HEX40_RE if length == 40 else _HEX64_RE
    if not expression.fullmatch(value):
        raise AlrOperationalError(f"{field}_invalid")
    return value


def _canonical_utc_z(value: Any) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise AlrOperationalError("source_ts_invalid")
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if not isinstance(value, str) or not value.endswith("Z") or not value.strip():
        raise AlrOperationalError("source_ts_invalid")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlrOperationalError("source_ts_invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise AlrOperationalError("source_ts_invalid")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_utc_z(value: Any) -> datetime:
    canonical = _canonical_utc_z(value)
    return datetime.fromisoformat(canonical.replace("Z", "+00:00")).astimezone(
        timezone.utc
    )


def _row_field(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        return row.get(key)
    try:
        return row[index]
    except (IndexError, KeyError, TypeError) as exc:
        raise AlrOperationalError("repository_row_invalid") from exc


def _suppression_result(
    plan: Mapping[str, Any],
    suppression: Mapping[str, Any],
    *,
    duplicate: bool = False,
    artifact_rows_written: int = 0,
    provenance_rows_written: int = 0,
) -> dict[str, Any]:
    payload = suppression["canonical_payload"]
    return {
        "status": "DUPLICATE_SUPPRESSION"
        if duplicate
        else "SUPPRESSED_EQUIVALENT_DEFER",
        "run_hash": None,
        "source_set_hash": plan["source_set_hash"],
        "source_count": plan["source_count"],
        "run_status": "DEFER_WRITE_SUPPRESSED",
        "suppression_artifact_hash": suppression["artifact_hash"],
        "decision_writes_suppressed": 1,
        "duplicate_retries": int(duplicate),
        "source_rows_consumed": provenance_rows_written,
        "artifact_rows_written": artifact_rows_written,
        "provenance_rows_written": provenance_rows_written,
        "run_rows_written": 0,
        "feedback_rows_written": 0,
        "defer_artifact_rows_written": 0,
        "payload_bytes_written": len(_canonical_json(payload).encode("utf-8"))
        if artifact_rows_written
        else 0,
        "no_authority": dict(plan["no_authority"]),
        "authority_counters": dict(plan["authority_counters"]),
    }


def _result(
    status: str,
    plan: Mapping[str, Any],
    *,
    artifact_rows_written: int = 0,
    provenance_rows_written: int = 0,
    run_rows_written: int = 0,
    defer_artifact_rows_written: int = 0,
    payload_bytes_written: int = 0,
    source_rows_consumed: int = 0,
) -> dict[str, Any]:
    return {
        "status": status,
        "run_hash": plan["run_hash"],
        "source_set_hash": plan["source_set_hash"],
        "source_count": plan["source_count"],
        "run_status": plan["run_status"],
        "decision_writes_suppressed": 0,
        "duplicate_retries": int(status == "DUPLICATE"),
        "source_rows_consumed": source_rows_consumed,
        "artifact_rows_written": artifact_rows_written,
        "provenance_rows_written": provenance_rows_written,
        "run_rows_written": run_rows_written,
        "feedback_rows_written": 0,
        "defer_artifact_rows_written": defer_artifact_rows_written,
        "payload_bytes_written": payload_bytes_written,
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

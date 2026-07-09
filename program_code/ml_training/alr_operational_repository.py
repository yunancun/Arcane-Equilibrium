"""Append-only repository for P2-4 scanner statistical experiment artifacts."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any

from ml_training.pit_dataset_manifest import compute_pit_dataset_manifest_hash
from ml_training.alr_scanner_statistical_experiment import (
    validate_scanner_statistical_experiment,
)


SOURCE_TABLE = "trading.scanner_snapshots"
RUN_KIND = "scanner_novelty_statistical_baseline"
RUN_STATUS = "DEFER_EVIDENCE"
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
    edges = _edges(result.get("provenance_edges"), artifacts, source_hashes)

    no_authority = _all_false_mapping(result.get("no_authority"), "no_authority")
    authority_counters = _all_zero_mapping(
        result.get("authority_counters"), "authority_counters"
    )
    return {
        "run_hash": run_hash,
        "run_kind": RUN_KIND,
        "run_status": RUN_STATUS,
        "source_head": source_head,
        "source_set_hash": source_set_hash,
        "source_count": len(source_hashes),
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

            for artifact in plan["artifacts"]:
                _insert_artifact(cursor, artifact)
            for edge in plan["edges"]:
                _insert_edge(cursor, edge)

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
                return _result("DUPLICATE", plan)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return _result("PERSISTED", plan)


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
    return [dict(row) for row in rows]


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


def _result(status: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "run_hash": plan["run_hash"],
        "source_set_hash": plan["source_set_hash"],
        "source_count": plan["source_count"],
        "run_status": plan["run_status"],
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

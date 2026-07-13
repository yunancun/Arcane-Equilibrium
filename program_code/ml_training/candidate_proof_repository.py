"""Read-only repository reconstruction for selected-candidate proof inputs.

The V153 outcome-feedback schema is bound to V152 training runs.  This module
therefore reads existing immutable rows but deliberately creates no new node,
edge, event, run, proof, reward, receipt, model, registry, serving, or trading
state.  Its receipt is an in-memory validation result only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

from ml_training.alr_operational_repository import (
    AlrOperationalError,
    build_candidate_learning_projection_plan,
)
from ml_training.alr_outcome_bridge import validate_alr_outcome_bridge_packet
from ml_training.candidate_proof_adapter import (
    INVALID,
    NO_MATCHED_FILLS,
    PENDING_EVIDENCE,
    READY_FOR_REWARD_VALIDATION,
    SELECTION_PROOF_BINDING_SCHEMA_VERSION,
    adapt_candidate_proof,
    compute_selection_proof_binding_hash,
    derive_selected_candidate_proof_identity,
)
from ml_training.reward_ledger import compute_reward_record_hash


BATCH_SCHEMA_VERSION = "candidate_proof_repository_batch_v1"
RECEIPT_SCHEMA_VERSION = "candidate_proof_repository_receipt_v1"
PROJECTION_ARTIFACT_SCHEMA_VERSION = (
    "alr_candidate_learning_projection_artifact_v2"
)
OUTCOME_BRIDGE_ARTIFACT_SCHEMA_VERSION = "alr_outcome_bridge_artifact_v1"
SOURCE_TABLE = "trading.scanner_snapshots"

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
_PROJECTION_KINDS = ("learning_target", "target_rotation")
_MAX_PROJECTION_LINEAGE_ROWS = 64
_BRIDGE_PAYLOAD_FIELDS = {
    "schema_version",
    "run_hash",
    "candidate_artifact_hash",
    "bridge",
}
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


class CandidateProofRepositoryError(ValueError):
    """Durable source rows cannot be reconstructed without ambiguity."""


def discover_candidate_proof_receipts(
    connection: Any,
    *,
    limit: int,
) -> dict[str, Any]:
    """Discover one current candidate and validate bounded proof inputs.

    ``limit + 1`` is read so a truncated evidence window never becomes a false
    pending or positive receipt.  The only caller-controlled value is the
    resource bound; all candidate, lineage, binding, proof, and reward identity
    comes from hash-checked repository rows.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64:
        raise CandidateProofRepositoryError("candidate_proof_limit_invalid")

    metrics = _empty_metrics()
    with connection.cursor() as cursor:
        row = _fetch_latest_projection(cursor)
        if row is None:
            return _batch(
                status="NO_CURRENT_SELECTED_CANDIDATE",
                receipts=[],
                metrics=metrics,
            )
        metrics["candidate_projection_rows_read"] = 1
        projection, plan, lineage_fingerprint = _reconstruct_projection(
            cursor,
            row,
            metrics=metrics,
        )
        if plan["decision_code"] != "QUALIFIED_CANDIDATE_SELECTED":
            return _batch(
                status="NO_CURRENT_SELECTED_CANDIDATE",
                receipts=[],
                metrics=metrics,
            )

        binding = _selection_binding(plan)
        bridge_rows = _fetch_matching_outcome_bridges(
            cursor,
            projection_artifact_hash=plan["artifact"]["artifact_hash"],
            limit=limit + 1,
        )
        if not isinstance(bridge_rows, list):
            raise CandidateProofRepositoryError("outcome_bridge_rows_invalid")
        metrics["outcome_bridge_rows_scanned"] = len(bridge_rows)
        if len(bridge_rows) > limit:
            return _batch(
                status="SCHEMA_REQUIRED_OVERFLOW",
                receipts=[],
                metrics=metrics,
            )
        bridge_fingerprint = _bridge_rows_fingerprint(bridge_rows)

        if not bridge_rows:
            adapter = adapt_candidate_proof(
                projection=projection,
                selection_proof_binding=binding,
            )
            receipt = _receipt(
                plan=plan,
                adapter=adapter,
                proof_packet=None,
                source_reward_records=[],
                canonical_reward_records=[],
                bridge_sources=[],
            )
            receipts = [receipt]
        else:
            receipts = _evidence_receipts(
                bridge_rows,
                projection=projection,
                plan=plan,
                binding=binding,
            )

        _assert_repository_snapshot_unchanged(
            cursor,
            expected_artifact_hash=plan["artifact"]["artifact_hash"],
            expected_lineage_fingerprint=lineage_fingerprint,
            expected_bridge_fingerprint=bridge_fingerprint,
            bridge_limit=limit + 1,
            metrics=metrics,
        )

    _record_receipt_metrics(metrics, receipts)
    return _batch(status="READY", receipts=receipts, metrics=metrics)


def _fetch_latest_projection(cursor: Any) -> Any:
    cursor.execute(
        "SELECT artifact_hash, artifact_kind, canonical_payload, created_at "
        "FROM learning.alr_artifact_nodes "
        "/* candidate-proof:latest-projection */ "
        "WHERE artifact_kind = ANY(%s) AND ("
        "canonical_payload ->> 'schema_version' LIKE %s "
        "OR canonical_payload #>> '{decision,schema_version}' LIKE %s"
        ") "
        "ORDER BY created_at DESC, artifact_hash DESC LIMIT 1",
        (
            list(_PROJECTION_KINDS),
            "alr_candidate_learning_projection_artifact_%",
            "alr_candidate_learning_decision_%",
        ),
    )
    return cursor.fetchone()


def _assert_repository_snapshot_unchanged(
    cursor: Any,
    *,
    expected_artifact_hash: str,
    expected_lineage_fingerprint: Sequence[tuple[str, ...]],
    expected_bridge_fingerprint: Sequence[tuple[str, str]],
    bridge_limit: int,
    metrics: dict[str, int],
) -> None:
    """Recheck every append-sensitive identity in one PostgreSQL snapshot."""
    cursor.execute(
        "WITH latest AS ("
        "SELECT artifact_hash FROM learning.alr_artifact_nodes "
        "WHERE artifact_kind = ANY(%s) AND ("
        "canonical_payload ->> 'schema_version' LIKE %s "
        "OR canonical_payload #>> '{decision,schema_version}' LIKE %s"
        ") ORDER BY created_at DESC, artifact_hash DESC LIMIT 1"
        "), bridge_window AS ("
        "SELECT bridge.artifact_hash, bridge.canonical_payload, bridge.created_at "
        "FROM learning.alr_artifact_nodes AS bridge CROSS JOIN latest "
        "WHERE bridge.artifact_kind = 'outcome_bridge' "
        "AND bridge.canonical_payload #>> "
        "'{bridge,source_artifacts,proof_packet,provenance,input_artifact_hashes,"
        "candidate_projection_artifact_hash}' = latest.artifact_hash "
        "ORDER BY bridge.created_at, bridge.artifact_hash LIMIT %s"
        "), lineage_window AS ("
        "SELECT edge.edge_hash, edge.from_artifact_hash, edge.to_artifact_hash, "
        "edge.edge_role, source.source_table, source.source_key, source.source_ts, "
        "source.source_hash FROM learning.alr_provenance_edges AS edge "
        "CROSS JOIN latest LEFT JOIN learning.alr_source_events AS source "
        "ON source.source_table = %s "
        "AND source.source_hash = edge.from_artifact_hash "
        "WHERE edge.to_artifact_hash = latest.artifact_hash "
        "ORDER BY source.source_ts, source.source_key, source.source_hash, "
        "edge.edge_hash LIMIT %s"
        ") SELECT latest.artifact_hash AS head_artifact_hash, "
        "COALESCE((SELECT jsonb_agg(jsonb_build_object("
        "'edge_hash', edge_hash, "
        "'from_artifact_hash', from_artifact_hash, "
        "'to_artifact_hash', to_artifact_hash, "
        "'edge_role', edge_role, "
        "'source_table', source_table, "
        "'source_key', source_key, "
        "'source_ts', source_ts, "
        "'source_hash', source_hash"
        ") ORDER BY source_ts, source_key, source_hash, edge_hash) "
        "FROM lineage_window), '[]'::jsonb) "
        "AS lineage_rows, "
        "COALESCE((SELECT jsonb_agg(jsonb_build_object("
        "'artifact_hash', bridge.artifact_hash, "
        "'canonical_payload', bridge.canonical_payload"
        ") ORDER BY bridge.created_at, bridge.artifact_hash) "
        "FROM bridge_window AS bridge), '[]'::jsonb) AS bridge_rows "
        "FROM latest /* candidate-proof:snapshot-recheck */",
        (
            list(_PROJECTION_KINDS),
            "alr_candidate_learning_projection_artifact_%",
            "alr_candidate_learning_decision_%",
            bridge_limit,
            SOURCE_TABLE,
            _MAX_PROJECTION_LINEAGE_ROWS + 1,
        ),
    )
    snapshot = cursor.fetchone()
    if snapshot is None:
        raise CandidateProofRepositoryError("candidate_repository_snapshot_changed")
    metrics["candidate_projection_rows_read"] += 1
    actual_hash = _required_hash(
        _row_field(snapshot, 0, "head_artifact_hash"),
        "candidate_projection_head_artifact_hash",
    )
    if actual_hash != expected_artifact_hash:
        raise CandidateProofRepositoryError("candidate_repository_snapshot_changed")
    lineage_rows = _row_field(snapshot, 1, "lineage_rows")
    bridge_rows = _row_field(snapshot, 2, "bridge_rows")
    if not isinstance(lineage_rows, list) or not isinstance(bridge_rows, list):
        raise CandidateProofRepositoryError("candidate_snapshot_rows_invalid")
    _, _, lineage_fingerprint = _validate_projection_lineage(
        lineage_rows,
        artifact_hash=actual_hash,
    )
    bridge_fingerprint = _bridge_rows_fingerprint(bridge_rows)
    metrics["projection_edge_rows_rechecked"] = len(lineage_rows)
    metrics["source_event_rows_rechecked"] = len(lineage_rows)
    metrics["outcome_bridge_rows_rechecked"] = len(bridge_rows)
    if (
        list(lineage_fingerprint) != list(expected_lineage_fingerprint)
        or list(bridge_fingerprint) != list(expected_bridge_fingerprint)
    ):
        raise CandidateProofRepositoryError("candidate_repository_snapshot_changed")


def _fetch_projection_lineage(cursor: Any, artifact_hash: str) -> list[Any]:
    cursor.execute(
        "SELECT edge.edge_hash, edge.from_artifact_hash, edge.to_artifact_hash, "
        "edge.edge_role, source.source_table, source.source_key, source.source_ts, "
        "source.source_hash "
        "FROM learning.alr_provenance_edges AS edge "
        "/* candidate-proof:projection-lineage */ "
        "LEFT JOIN learning.alr_source_events AS source "
        "ON source.source_table = %s AND source.source_hash = edge.from_artifact_hash "
        "WHERE edge.to_artifact_hash = %s "
        "ORDER BY source.source_ts ASC, source.source_key ASC, "
        "source.source_hash ASC, edge.edge_hash ASC LIMIT %s",
        (
            SOURCE_TABLE,
            artifact_hash,
            _MAX_PROJECTION_LINEAGE_ROWS + 1,
        ),
    )
    return cursor.fetchall()


def _fetch_matching_outcome_bridges(
    cursor: Any,
    *,
    projection_artifact_hash: str,
    limit: int,
) -> list[Any]:
    cursor.execute(
        "SELECT artifact_hash, canonical_payload, created_at "
        "FROM learning.alr_artifact_nodes "
        "/* candidate-proof:outcome-bridges */ "
        "WHERE artifact_kind = 'outcome_bridge' "
        "AND canonical_payload #>> "
        "'{bridge,source_artifacts,proof_packet,provenance,input_artifact_hashes,"
        "candidate_projection_artifact_hash}' = %s "
        "ORDER BY created_at ASC, artifact_hash ASC LIMIT %s",
        (
            projection_artifact_hash,
            limit,
        ),
    )
    return cursor.fetchall()


def _reconstruct_projection(
    cursor: Any,
    row: Any,
    *,
    metrics: dict[str, int],
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, ...]]]:
    artifact_hash = _required_hash(
        _row_field(row, 0, "artifact_hash"),
        "candidate_projection_artifact_hash",
    )
    artifact_kind = _row_field(row, 1, "artifact_kind")
    payload = _row_field(row, 2, "canonical_payload")
    if artifact_kind not in _PROJECTION_KINDS or not isinstance(payload, Mapping):
        raise CandidateProofRepositoryError("candidate_projection_artifact_invalid")
    canonical_payload = copy.deepcopy(dict(payload))
    if canonical_payload.get("schema_version") != PROJECTION_ARTIFACT_SCHEMA_VERSION:
        raise CandidateProofRepositoryError("candidate_projection_schema_invalid")
    if _canonical_sha256(canonical_payload) != artifact_hash:
        raise CandidateProofRepositoryError(
            "candidate_projection_artifact_hash_mismatch"
        )

    lineage_rows = _fetch_projection_lineage(cursor, artifact_hash)
    metrics["projection_edge_rows_read"] = len(lineage_rows)
    metrics["source_event_rows_read"] = len(lineage_rows)
    identities, edges, lineage_fingerprint = _validate_projection_lineage(
        lineage_rows,
        artifact_hash=artifact_hash,
    )
    decision = canonical_payload.get("decision")
    if not isinstance(decision, Mapping):
        raise CandidateProofRepositoryError("candidate_projection_decision_missing")
    source_head = decision.get("source_head")
    if not isinstance(source_head, str) or not _HEX40_RE.fullmatch(source_head):
        raise CandidateProofRepositoryError("candidate_projection_source_head_invalid")
    source_hashes = [item["source_hash"] for item in identities]
    projection: dict[str, Any] = {
        "schema_version": "alr_candidate_learning_projection_v2",
        "source_head": source_head,
        "source_set": {
            "source_set_hash": decision.get("source_set_hash"),
            "source_hashes": source_hashes,
            "source_count": len(source_hashes),
            "as_of_ts": max(
                identities,
                key=lambda item: datetime.fromisoformat(
                    item["source_ts"].replace("Z", "+00:00")
                ),
            )["source_ts"],
            "source_identities": identities,
        },
        "decision": copy.deepcopy(dict(decision)),
        "artifact": {
            "artifact_kind": artifact_kind,
            "artifact_hash": artifact_hash,
            "canonical_payload": canonical_payload,
        },
        "provenance_edges": edges,
        "no_authority": copy.deepcopy(canonical_payload.get("no_authority")),
        "authority_counters": copy.deepcopy(
            canonical_payload.get("authority_counters")
        ),
    }
    projection["projection_hash"] = _canonical_sha256(projection)
    try:
        plan = build_candidate_learning_projection_plan(projection)
    except (AlrOperationalError, TypeError, ValueError) as exc:
        raise CandidateProofRepositoryError(
            "candidate_projection_lineage_invalid:" + str(exc)
        ) from exc
    return projection, plan, lineage_fingerprint


def _validate_projection_lineage(
    rows: Any,
    *,
    artifact_hash: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[tuple[str, ...]]]:
    if not isinstance(rows, list):
        raise CandidateProofRepositoryError("candidate_projection_lineage_rows_invalid")
    if len(rows) > _MAX_PROJECTION_LINEAGE_ROWS:
        raise CandidateProofRepositoryError(
            "candidate_projection_lineage_schema_required_overflow"
        )
    if not rows:
        raise CandidateProofRepositoryError("candidate_projection_lineage_missing")
    identities: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    fingerprints: list[tuple[str, ...]] = []
    seen_edges: set[str] = set()
    seen_sources: set[str] = set()
    seen_identities: set[tuple[str, str, str]] = set()
    for row in rows:
        edge_hash = _required_hash(
            _row_field(row, 0, "edge_hash"),
            "candidate_projection_lineage_edge_hash",
        )
        from_hash = _required_hash(
            _row_field(row, 1, "from_artifact_hash"),
            "candidate_projection_lineage_from_hash",
        )
        to_hash = _required_hash(
            _row_field(row, 2, "to_artifact_hash"),
            "candidate_projection_lineage_to_hash",
        )
        edge_role = _row_field(row, 3, "edge_role")
        source_table = _row_field(row, 4, "source_table")
        source_key = _required_text(
            _row_field(row, 5, "source_key"),
            "candidate_projection_lineage_source_key",
        )
        source_ts = _canonical_utc_z(
            _row_field(row, 6, "source_ts"),
            "candidate_projection_lineage_source_ts",
        )
        source_hash = _required_hash(
            _row_field(row, 7, "source_hash"),
            "candidate_projection_lineage_source_hash",
        )
        edge = {
            "from_artifact_hash": from_hash,
            "to_artifact_hash": to_hash,
            "edge_role": str(edge_role),
        }
        identity_key = (source_ts, source_key, source_hash)
        if (
            edge_role != "training_input"
            or source_table != SOURCE_TABLE
            or from_hash != source_hash
            or to_hash != artifact_hash
            or edge_hash != _canonical_sha256(edge)
            or edge_hash in seen_edges
            or source_hash in seen_sources
            or identity_key in seen_identities
        ):
            raise CandidateProofRepositoryError("candidate_projection_lineage_invalid")
        seen_edges.add(edge_hash)
        seen_sources.add(source_hash)
        seen_identities.add(identity_key)
        edges.append({**edge, "edge_hash": edge_hash})
        identities.append(
            {
                "source_hash": source_hash,
                "source_key": source_key,
                "source_ts": source_ts,
            }
        )
        fingerprints.append(
            (
                edge_hash,
                from_hash,
                to_hash,
                str(edge_role),
                str(source_table),
                source_key,
                source_ts,
                source_hash,
            )
        )
    order = sorted(
        range(len(identities)),
        key=lambda index: (
            identities[index]["source_ts"],
            identities[index]["source_key"],
            identities[index]["source_hash"],
            edges[index]["edge_hash"],
        ),
    )
    return (
        [identities[index] for index in order],
        [edges[index] for index in order],
        [fingerprints[index] for index in order],
    )


def _bridge_rows_fingerprint(rows: Any) -> list[tuple[str, str]]:
    if not isinstance(rows, list):
        raise CandidateProofRepositoryError("outcome_bridge_rows_invalid")
    fingerprints: list[tuple[str, str]] = []
    for row in rows:
        artifact_hash = _required_hash(
            _row_field(row, 0, "artifact_hash"),
            "outcome_bridge_artifact_hash",
        )
        payload = _row_field(row, 1, "canonical_payload")
        if not isinstance(payload, Mapping):
            raise CandidateProofRepositoryError("outcome_bridge_payload_invalid")
        fingerprints.append((artifact_hash, _canonical_sha256(payload)))
    return sorted(fingerprints)


def _selection_binding(plan: Mapping[str, Any]) -> dict[str, Any]:
    payload = _mapping(_mapping(plan.get("artifact")).get("canonical_payload"))
    selected = payload.get("selected_candidate")
    handoff = plan.get("handoff")
    if not isinstance(selected, Mapping) or not isinstance(handoff, Mapping):
        raise CandidateProofRepositoryError("candidate_selection_binding_missing")
    identity = derive_selected_candidate_proof_identity(selected)
    binding: dict[str, Any] = {
        "schema_version": SELECTION_PROOF_BINDING_SCHEMA_VERSION,
        "projection_hash": plan["projection_hash"],
        "artifact_hash": _mapping(plan.get("artifact")).get("artifact_hash"),
        "decision_hash": plan.get("decision_hash"),
        "source_set_hash": plan.get("source_set_hash"),
        "handoff_hash": handoff.get("handoff_hash"),
        "candidate_id": identity["candidate_id"],
        "context_id": identity["context_id"],
        "selected_candidate": copy.deepcopy(dict(selected)),
    }
    binding["binding_hash"] = compute_selection_proof_binding_hash(binding)
    return binding


def _evidence_receipts(
    rows: Sequence[Any],
    *,
    projection: Mapping[str, Any],
    plan: Mapping[str, Any],
    binding: Mapping[str, Any],
) -> list[dict[str, Any]]:
    by_input_hash: dict[str, dict[str, Any]] = {}
    for row in rows:
        source = _validated_bridge_source(row)
        canonical_rewards = sorted(
            source["reward_records"],
            key=_reward_sort_key,
        )
        adapter = adapt_candidate_proof(
            projection=projection,
            selection_proof_binding=binding,
            proof_packet=source["proof_packet"],
            reward_records=canonical_rewards,
        )
        proof_input_hash = adapter.get("proof_input_hash")
        if not isinstance(proof_input_hash, str) or not _HEX64_RE.fullmatch(
            proof_input_hash
        ):
            raise CandidateProofRepositoryError("proof_input_hash_invalid")
        bridge_sources = [
            {
                "artifact_hash": source["artifact_hash"],
                "bridge_hash": source["bridge_hash"],
                "run_hash": source["run_hash"],
                "candidate_artifact_hash": source["candidate_artifact_hash"],
            }
        ]
        receipt = _receipt(
            plan=plan,
            adapter=adapter,
            proof_packet=source["proof_packet"],
            source_reward_records=source["reward_records"],
            canonical_reward_records=canonical_rewards,
            bridge_sources=bridge_sources,
        )
        existing = by_input_hash.get(proof_input_hash)
        if existing is None:
            by_input_hash[proof_input_hash] = receipt
            continue
        if (
            existing["adapter_result"] != receipt["adapter_result"]
            or existing["canonical_adapter_inputs"]
            != receipt["canonical_adapter_inputs"]
        ):
            raise CandidateProofRepositoryError(
                "proof_input_semantic_hash_conflict"
            )
        refs = existing["repository_sources"]["outcome_bridge_container_refs"]
        refs.extend(bridge_sources)
        refs.sort(key=lambda item: (item["artifact_hash"], item["bridge_hash"]))
        existing["repository_sources"]["outcome_bridge_artifact_hashes"] = [
            item["artifact_hash"] for item in refs
        ]
        existing["repository_sources"]["bridge_hashes"] = [
            item["bridge_hash"] for item in refs
        ]
        existing["exact_source_containers"].extend(
            receipt["exact_source_containers"]
        )
        existing["exact_source_containers"].sort(
            key=lambda item: item["outcome_bridge_artifact_hash"]
        )
        existing["receipt_hash"] = _receipt_hash(existing)
    return sorted(
        by_input_hash.values(),
        key=lambda item: (
            str(_mapping(item.get("adapter_result")).get("proof_input_hash")),
            str(item.get("receipt_hash")),
        ),
    )


def _validated_bridge_source(row: Any) -> dict[str, Any]:
    artifact_hash = _required_hash(
        _row_field(row, 0, "artifact_hash"),
        "outcome_bridge_artifact_hash",
    )
    payload = _row_field(row, 1, "canonical_payload")
    if not isinstance(payload, Mapping) or set(payload) != _BRIDGE_PAYLOAD_FIELDS:
        raise CandidateProofRepositoryError("outcome_bridge_payload_invalid")
    canonical_payload = copy.deepcopy(dict(payload))
    if (
        canonical_payload.get("schema_version")
        != OUTCOME_BRIDGE_ARTIFACT_SCHEMA_VERSION
    ):
        raise CandidateProofRepositoryError("outcome_bridge_schema_invalid")
    if _canonical_sha256(canonical_payload) != artifact_hash:
        raise CandidateProofRepositoryError("outcome_bridge_artifact_hash_mismatch")
    run_hash = _required_hash(
        canonical_payload.get("run_hash"),
        "outcome_bridge_run_hash",
    )
    candidate_hash = _required_hash(
        canonical_payload.get("candidate_artifact_hash"),
        "outcome_bridge_candidate_artifact_hash",
    )
    bridge = canonical_payload.get("bridge")
    if not isinstance(bridge, Mapping):
        raise CandidateProofRepositoryError("outcome_bridge_packet_missing")
    validation = validate_alr_outcome_bridge_packet(bridge)
    if not validation.valid:
        raise CandidateProofRepositoryError(
            "outcome_bridge_packet_invalid:" + validation.reason
        )
    bridge_hash = _required_hash(
        bridge.get("bridge_hash"),
        "outcome_bridge_hash",
    )
    source_artifacts = bridge.get("source_artifacts")
    if (
        not isinstance(source_artifacts, Mapping)
        or set(source_artifacts) != {"proof_packet", "reward_records"}
    ):
        raise CandidateProofRepositoryError(
            "outcome_bridge_source_artifacts_invalid"
        )
    proof = source_artifacts.get("proof_packet")
    rewards = source_artifacts.get("reward_records")
    if not isinstance(proof, Mapping):
        raise CandidateProofRepositoryError("outcome_bridge_proof_packet_invalid")
    if not isinstance(rewards, list) or not all(
        isinstance(item, Mapping) for item in rewards
    ):
        raise CandidateProofRepositoryError("outcome_bridge_reward_records_invalid")
    return {
        "artifact_hash": artifact_hash,
        "bridge_hash": bridge_hash,
        "run_hash": run_hash,
        "candidate_artifact_hash": candidate_hash,
        "proof_packet": copy.deepcopy(dict(proof)),
        "reward_records": [copy.deepcopy(dict(item)) for item in rewards],
    }


def _receipt(
    *,
    plan: Mapping[str, Any],
    adapter: Mapping[str, Any],
    proof_packet: Mapping[str, Any] | None,
    source_reward_records: Sequence[Mapping[str, Any]],
    canonical_reward_records: Sequence[Mapping[str, Any]],
    bridge_sources: Sequence[Mapping[str, str]],
) -> dict[str, Any]:
    if adapter.get("status") not in {
        PENDING_EVIDENCE,
        NO_MATCHED_FILLS,
        READY_FOR_REWARD_VALIDATION,
        INVALID,
    }:
        raise CandidateProofRepositoryError("candidate_proof_adapter_status_invalid")
    projection_refs = adapter.get("projection_refs")
    selection_binding = adapter.get("selection_binding")
    if not isinstance(projection_refs, Mapping) or not isinstance(
        selection_binding, Mapping
    ):
        raise CandidateProofRepositoryError("candidate_proof_adapter_binding_invalid")
    refs = [copy.deepcopy(dict(item)) for item in bridge_sources]
    refs.sort(key=lambda item: (item["artifact_hash"], item["bridge_hash"]))
    proof_summary = _mapping(adapter.get("proof"))
    reward_summaries = adapter.get("reward_records")
    if not isinstance(reward_summaries, list):
        raise CandidateProofRepositoryError("candidate_proof_reward_summary_invalid")
    receipt: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "status": adapter["status"],
        "reasons": copy.deepcopy(list(adapter.get("reasons", []))),
        "projection_identity_status": "RECONSTRUCTED_FROM_HASH_VALIDATED_ROWS",
        "original_ephemeral_projection_hash_attested": False,
        "projection_refs": copy.deepcopy(dict(projection_refs)),
        "selection_binding": copy.deepcopy(dict(selection_binding)),
        "repository_sources": {
            "projection_artifact_hash": _mapping(plan.get("artifact")).get(
                "artifact_hash"
            ),
            "source_artifact_hashes": copy.deepcopy(
                list(plan.get("source_hashes", []))
            ),
            "projection_edge_hashes": [
                item["edge_hash"] for item in plan.get("edges", [])
            ],
            "outcome_bridge_artifact_hashes": [
                item["artifact_hash"] for item in refs
            ],
            "bridge_hashes": [item["bridge_hash"] for item in refs],
            "outcome_bridge_container_refs": refs,
            "proof_packet_hash": proof_summary.get(
                "computed_proof_packet_hash"
            ),
            "reward_record_hashes": [
                _mapping(item).get("computed_record_hash")
                for item in reward_summaries
            ],
        },
        "source_artifacts": {
            "proof_packet": None
            if proof_packet is None
            else copy.deepcopy(dict(proof_packet)),
            "reward_records": [
                copy.deepcopy(dict(item)) for item in source_reward_records
            ],
        },
        "canonical_adapter_inputs": {
            "normalization": "REWARD_RECORDS_SORTED_BY_COMPUTED_DECLARED_AND_PAYLOAD_HASH",
            "proof_packet": None
            if proof_packet is None
            else copy.deepcopy(dict(proof_packet)),
            "reward_records": [
                copy.deepcopy(dict(item)) for item in canonical_reward_records
            ],
        },
        "exact_source_containers": [
            {
                "outcome_bridge_artifact_hash": item["artifact_hash"],
                "source_artifacts": {
                    "proof_packet": None
                    if proof_packet is None
                    else copy.deepcopy(dict(proof_packet)),
                    "reward_records": [
                        copy.deepcopy(dict(record))
                        for record in source_reward_records
                    ],
                },
            }
            for item in refs
        ],
        "adapter_result": copy.deepcopy(dict(adapter)),
        "durability": {
            "source_container": "HASH_VALIDATED_APPEND_ONLY_ROW"
            if refs
            else "NO_MATCHING_HASH_VALIDATED_ROW",
            "runtime_or_exchange_attested": False,
            "receipt_persisted": False,
        },
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }
    receipt["receipt_hash"] = _receipt_hash(receipt)
    return receipt


def _receipt_hash(receipt: Mapping[str, Any]) -> str:
    payload = copy.deepcopy(dict(receipt))
    payload.pop("receipt_hash", None)
    return _canonical_sha256(payload)


def compute_candidate_proof_repository_receipt_hash(
    receipt: Mapping[str, Any],
) -> str:
    """Recompute an in-memory receipt identity without granting persistence."""
    if not isinstance(receipt, Mapping):
        raise CandidateProofRepositoryError("candidate_proof_receipt_not_mapping")
    return _receipt_hash(receipt)


def _reward_sort_key(record: Mapping[str, Any]) -> tuple[str, str, str]:
    try:
        computed = compute_reward_record_hash(record)
    except (TypeError, ValueError):
        computed = "~"
    declared = record.get("record_hash")
    declared_text = declared if isinstance(declared, str) else "~"
    return computed, declared_text, _canonical_sha256(record)


def _record_receipt_metrics(
    metrics: dict[str, int],
    receipts: Sequence[Mapping[str, Any]],
) -> None:
    metrics["receipts_built"] = len(receipts)
    for receipt in receipts:
        status = receipt.get("status")
        if status == PENDING_EVIDENCE:
            metrics["pending_receipts"] += 1
        elif status == NO_MATCHED_FILLS:
            metrics["no_fill_receipts"] += 1
        elif status == READY_FOR_REWARD_VALIDATION:
            metrics["ready_for_reward_validation_receipts"] += 1
        elif status == INVALID:
            metrics["invalid_receipts"] += 1
        else:
            raise CandidateProofRepositoryError("receipt_status_invalid")


def _empty_metrics() -> dict[str, int]:
    return {
        "candidate_projection_rows_read": 0,
        "source_event_rows_read": 0,
        "projection_edge_rows_read": 0,
        "source_event_rows_rechecked": 0,
        "projection_edge_rows_rechecked": 0,
        "outcome_bridge_rows_scanned": 0,
        "outcome_bridge_rows_rechecked": 0,
        "receipts_built": 0,
        "pending_receipts": 0,
        "no_fill_receipts": 0,
        "ready_for_reward_validation_receipts": 0,
        "invalid_receipts": 0,
        "rows_written": 0,
        "payload_bytes_written": 0,
    }


def _batch(
    *,
    status: str,
    receipts: Sequence[Mapping[str, Any]],
    metrics: Mapping[str, int],
) -> dict[str, Any]:
    return {
        "schema_version": BATCH_SCHEMA_VERSION,
        "status": status,
        "receipts": [copy.deepcopy(dict(item)) for item in receipts],
        "metrics": copy.deepcopy(dict(metrics)),
        "no_authority": dict(_NO_AUTHORITY),
        "authority_counters": dict(_AUTHORITY_COUNTERS),
    }


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise CandidateProofRepositoryError("canonical_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _required_hash(value: Any, field: str) -> str:
    if not isinstance(value, str) or not _HEX64_RE.fullmatch(value):
        raise CandidateProofRepositoryError(field + "_invalid")
    return value


def _required_text(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
    ):
        raise CandidateProofRepositoryError(field + "_invalid")
    return value


def _canonical_utc_z(value: Any, field: str) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise CandidateProofRepositoryError(field + "_invalid")
        parsed = value.astimezone(timezone.utc)
    elif isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(
                value.replace("Z", "+00:00") if value.endswith("Z") else value
            )
        except ValueError as exc:
            raise CandidateProofRepositoryError(field + "_invalid") from exc
        if parsed.tzinfo is None:
            raise CandidateProofRepositoryError(field + "_invalid")
        parsed = parsed.astimezone(timezone.utc)
    else:
        raise CandidateProofRepositoryError(field + "_invalid")
    # Candidate projections deliberately bind scanner identities at whole-second
    # precision.  PostgreSQL TIMESTAMPTZ readback retains the source row's
    # fractional seconds, so normalize the catalog value to the producer's
    # canonical contract before reconstructing and re-hashing the projection.
    return parsed.isoformat(timespec="seconds").replace("+00:00", "Z")


def _row_field(row: Any, index: int, key: str) -> Any:
    if isinstance(row, Mapping):
        if key not in row:
            raise CandidateProofRepositoryError(key + "_missing")
        return row[key]
    try:
        return row[index]
    except (IndexError, KeyError, TypeError) as exc:
        raise CandidateProofRepositoryError(key + "_missing") from exc


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}

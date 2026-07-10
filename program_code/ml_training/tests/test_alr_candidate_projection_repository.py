from __future__ import annotations

import copy
import hashlib
import json
from typing import Any

import pytest

from ml_training.alr_operational_repository import (
    AlrOperationalConflict,
    AlrOperationalError,
    build_candidate_learning_projection_plan,
    fetch_recent_candidate_projection_decisions,
    persist_candidate_learning_projection,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _projection(*, selected: bool = False) -> dict[str, Any]:
    source_hashes = ["1" * 64, "2" * 64]
    decision_code = (
        "QUALIFIED_CANDIDATE_SELECTED"
        if selected
        else "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES"
    )
    selected_candidate = (
        {
            "candidate_family_key": "a" * 64,
            "candidate_eval_id": "b" * 64,
            "state": "DECISION_READY",
        }
        if selected
        else None
    )
    selected_collection_target = (
        None
        if selected
        else {
            "candidate_family_key": "c" * 64,
            "state": "COLLECT_DISTINCT_ENTRIES",
            "passive_only": True,
        }
    )
    decision = {
        "schema_version": "alr_candidate_learning_decision_v1",
        "decision_code": decision_code,
        "evaluated_at": "2026-07-10T12:00:00Z",
        "selected_candidate": selected_candidate,
        "selected_collection_target": selected_collection_target,
        "candidate_count": 3,
        "eligible_candidate_count": int(selected),
        "no_authority": {
            "exchange_authority": False,
            "trading_authority": False,
            "order_or_probe_authority": False,
            "decision_lease_authority": False,
            "cost_gate_authority": False,
            "proof_authority": False,
            "serving_authority": False,
            "promotion_authority": False,
            "latest_authority": False,
        },
        "authority_counters": {
            "exchange_contact_count": 0,
            "trading_action_count": 0,
            "order_or_probe_count": 0,
            "decision_lease_count": 0,
            "cost_gate_change_count": 0,
            "proof_claim_count": 0,
            "serving_or_promotion_count": 0,
        },
    }
    decision["decision_hash"] = _sha(decision)
    artifact_kind = "learning_target" if selected else "target_rotation"
    payload = {
        "schema_version": "alr_candidate_learning_projection_artifact_v1",
        "decision_code": decision_code,
        "decision_hash": decision["decision_hash"],
        "decision": copy.deepcopy(decision),
        "selected_candidate": selected_candidate,
        "selected_collection_target": selected_collection_target,
        "source_refs": {
            "scanner_source_set_hash": _sha(source_hashes),
            "evidence_source_status": "READY",
            "evidence_snapshot_hash": "d" * 64,
            "evidence_content_sha256": "e" * 64,
            "evidence_board_hash": "f" * 64,
            "latest_alias_used": False,
        },
        "training_run_created": False,
        "model_training_performed": False,
        "serving_ready": False,
        "promotion_ready": False,
        "order_or_probe_created": False,
        "next_stage": "WP4_VERSIONED_TRAINING_SCHEMA_REQUIRED",
        "no_authority": copy.deepcopy(decision["no_authority"]),
        "authority_counters": copy.deepcopy(decision["authority_counters"]),
    }
    artifact_hash = _sha(payload)
    edges = []
    for source_hash in source_hashes:
        edge = {
            "from_artifact_hash": source_hash,
            "to_artifact_hash": artifact_hash,
            "edge_role": "training_input",
        }
        edge["edge_hash"] = _sha(edge)
        edges.append(edge)
    result = {
        "schema_version": "alr_candidate_learning_projection_v1",
        "source_head": "9" * 40,
        "source_set": {
            "source_set_hash": _sha(source_hashes),
            "source_hashes": source_hashes,
            "source_count": len(source_hashes),
        },
        "decision": decision,
        "artifact": {
            "artifact_kind": artifact_kind,
            "artifact_hash": artifact_hash,
            "canonical_payload": payload,
        },
        "provenance_edges": edges,
        "no_authority": copy.deepcopy(decision["no_authority"]),
        "authority_counters": copy.deepcopy(decision["authority_counters"]),
    }
    result["projection_hash"] = _sha(result)
    return result


def _rehash_projection(projection: dict[str, Any]) -> None:
    payload = projection["artifact"]["canonical_payload"]
    artifact_hash = _sha(payload)
    projection["artifact"]["artifact_hash"] = artifact_hash
    for edge in projection["provenance_edges"]:
        edge["to_artifact_hash"] = artifact_hash
        edge_body = {
            "from_artifact_hash": edge["from_artifact_hash"],
            "to_artifact_hash": edge["to_artifact_hash"],
            "edge_role": edge["edge_role"],
        }
        edge["edge_hash"] = _sha(edge_body)
    projection["projection_hash"] = _sha(
        {key: value for key, value in projection.items() if key != "projection_hash"}
    )


class _Connection:
    def __init__(self) -> None:
        self.artifacts: dict[str, dict[str, Any]] = {}
        self.artifact_kinds: dict[str, str] = {}
        self.edges: dict[str, tuple[str, str, str]] = {}
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_edge_number: int | None = None
        self.edge_attempts = 0
        self.decision_payloads: list[dict[str, Any]] = []
        self._snapshot: tuple[dict[str, Any], dict[str, str], dict[str, Any]] | None = None

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1
        self._snapshot = None

    def rollback(self) -> None:
        self.rollbacks += 1
        if self._snapshot is not None:
            self.artifacts, self.artifact_kinds, self.edges = copy.deepcopy(
                self._snapshot
            )
            self._snapshot = None


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.row: Any = None

    def __enter__(self) -> "_Cursor":
        if self.connection._snapshot is None:
            self.connection._snapshot = copy.deepcopy(
                (
                    self.connection.artifacts,
                    self.connection.artifact_kinds,
                    self.connection.edges,
                )
            )
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        assert params is not None
        if "artifact_kind = ANY" in sql:
            self.row = [
                {"canonical_payload": payload}
                for payload in self.connection.decision_payloads[: int(params[2])]
            ]
        elif "SELECT canonical_payload FROM learning.alr_artifact_nodes" in sql:
            payload = self.connection.artifacts.get(str(params[0]))
            self.row = None if payload is None else {"canonical_payload": payload}
        elif "SELECT count(*) FROM learning.alr_provenance_edges" in sql:
            self.row = (sum(str(item) in self.connection.edges for item in params[0]),)
        elif "INSERT INTO learning.alr_artifact_nodes" in sql:
            artifact_hash = str(params[0])
            if artifact_hash in self.connection.artifacts:
                self.row = None
            else:
                self.connection.artifacts[artifact_hash] = json.loads(str(params[2]))
                self.connection.artifact_kinds[artifact_hash] = str(params[1])
                self.row = (artifact_hash,)
        elif "INSERT INTO learning.alr_provenance_edges" in sql:
            self.connection.edge_attempts += 1
            if self.connection.fail_edge_number == self.connection.edge_attempts:
                raise RuntimeError("injected_edge_failure")
            edge_hash = str(params[0])
            if edge_hash in self.connection.edges:
                self.row = None
            else:
                self.connection.edges[edge_hash] = (
                    str(params[1]),
                    str(params[2]),
                    str(params[3]),
                )
                self.row = (edge_hash,)
        else:  # pragma: no cover - catches accidental schema expansion
            raise AssertionError(f"unexpected_sql:{sql}")

    def fetchone(self) -> Any:
        return self.row

    def fetchall(self) -> Any:
        return self.row


def test_builds_no_run_plan_for_rotation_and_selected_target() -> None:
    rotation = build_candidate_learning_projection_plan(_projection())
    target = build_candidate_learning_projection_plan(_projection(selected=True))

    assert rotation["artifact"]["artifact_kind"] == "target_rotation"
    assert target["artifact"]["artifact_kind"] == "learning_target"
    assert "run" not in rotation
    assert "run_kind" not in rotation
    assert rotation["artifact"]["canonical_payload"]["training_run_created"] is False


def test_missing_evidence_source_can_persist_honest_durable_abstention() -> None:
    projection = _projection()
    refs = projection["artifact"]["canonical_payload"]["source_refs"]
    refs.update(
        {
            "evidence_source_status": "DIRECTORY_MISSING",
            "evidence_content_sha256": None,
            "evidence_board_hash": None,
        }
    )
    _rehash_projection(projection)

    plan = build_candidate_learning_projection_plan(projection)

    assert plan["decision_code"].startswith("NO_QUALIFIED_CANDIDATE_")
    assert plan["artifact"]["canonical_payload"]["source_refs"][
        "evidence_source_status"
    ] == "DIRECTORY_MISSING"


def test_persists_projection_once_then_replay_is_duplicate_without_training_run() -> None:
    connection = _Connection()
    projection = _projection()

    first = persist_candidate_learning_projection(connection, projection)
    second = persist_candidate_learning_projection(connection, projection)

    assert first == {
        "status": "PERSISTED",
        "artifact_hash": projection["artifact"]["artifact_hash"],
        "artifact_rows_written": 1,
        "provenance_rows_written": 2,
        "payload_bytes_written": len(
            json.dumps(
                projection["artifact"]["canonical_payload"],
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        ),
        "source_rows_consumed": 2,
        "training_run_rows_written": 0,
        "model_training_performed": False,
    }
    assert second["status"] == "DUPLICATE"
    assert second["artifact_rows_written"] == 0
    assert second["provenance_rows_written"] == 0
    assert second["training_run_rows_written"] == 0
    assert connection.commits == 2
    sql = "\n".join(call[0] for call in connection.calls).upper()
    assert "ALR_TRAINING_RUNS" not in sql
    assert "UPDATE " not in sql
    assert "DELETE " not in sql


def test_duplicate_fails_closed_when_existing_lineage_is_incomplete() -> None:
    connection = _Connection()
    projection = _projection()
    persist_candidate_learning_projection(connection, projection)
    connection.edges.pop(next(iter(connection.edges)))

    with pytest.raises(
        AlrOperationalConflict,
        match="candidate_projection_lineage_incomplete",
    ):
        persist_candidate_learning_projection(connection, projection)

    assert connection.rollbacks == 1


def test_projection_write_rolls_back_artifact_and_edges_atomically() -> None:
    connection = _Connection()
    connection.fail_edge_number = 2

    with pytest.raises(RuntimeError, match="injected_edge_failure"):
        persist_candidate_learning_projection(connection, _projection())

    assert connection.artifacts == {}
    assert connection.edges == {}
    assert connection.rollbacks == 1


@pytest.mark.parametrize(
    ("path", "value", "reason"),
    (
        (("artifact", "canonical_payload", "training_run_created"), True, "candidate_projection_training_claim_invalid"),
        (("artifact", "canonical_payload", "model_training_performed"), True, "candidate_projection_training_claim_invalid"),
        (("artifact", "canonical_payload", "source_refs", "latest_alias_used"), True, "candidate_projection_latest_alias_invalid"),
        (("no_authority", "trading_authority"), True, "candidate_projection_authority_invalid"),
        (("authority_counters", "order_or_probe_count"), 1, "candidate_projection_authority_invalid"),
    ),
)
def test_rejects_training_latest_or_authority_claims(
    path: tuple[str, ...],
    value: object,
    reason: str,
) -> None:
    projection = _projection()
    cursor: dict[str, Any] = projection
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value

    with pytest.raises(AlrOperationalError, match=reason):
        build_candidate_learning_projection_plan(projection)


def test_rejects_hash_tampering_or_kind_decision_mismatch() -> None:
    tampered = _projection()
    tampered["artifact"]["canonical_payload"]["source_refs"][
        "evidence_content_sha256"
    ] = "0" * 64
    with pytest.raises(AlrOperationalError, match="candidate_projection_artifact_hash_mismatch"):
        build_candidate_learning_projection_plan(tampered)

    wrong_kind = _projection(selected=True)
    wrong_kind["artifact"]["artifact_kind"] = "target_rotation"
    with pytest.raises(AlrOperationalError, match="candidate_projection_artifact_kind_mismatch"):
        build_candidate_learning_projection_plan(wrong_kind)


@pytest.mark.parametrize("mutation", ("missing", "partial", "different"))
def test_rejects_artifact_without_exact_self_describing_decision(
    mutation: str,
) -> None:
    projection = _projection()
    payload = projection["artifact"]["canonical_payload"]
    if mutation == "missing":
        payload.pop("decision")
    elif mutation == "partial":
        payload["decision"] = {
            "decision_code": projection["decision"]["decision_code"],
            "decision_hash": projection["decision"]["decision_hash"],
        }
    else:
        payload["decision"]["candidate_count"] += 1
    _rehash_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_payload_mismatch",
    ):
        build_candidate_learning_projection_plan(projection)


def test_reads_bounded_recent_candidate_history_for_cooldown_without_mutation() -> None:
    connection = _Connection()
    projection = _projection()
    payload = projection["artifact"]["canonical_payload"]
    payload["decision"] = copy.deepcopy(projection["decision"])
    payload["decision"]["evaluated_at"] = "2026-07-10T12:00:00Z"
    payload["decision"]["selected_collection_target"] = {
        "candidate_family_key": "c" * 64,
        "family_key": "c" * 64,
        "material_fingerprint": "d" * 64,
        "state": "COLLECT_DISTINCT_ENTRIES",
    }
    connection.decision_payloads = [payload]

    rows = fetch_recent_candidate_projection_decisions(connection, limit=32)

    assert rows == [
        {
            "family_key": "c" * 64,
            "material_fingerprint": "d" * 64,
            "decision_ts_s": 1_783_684_800,
        }
    ]
    sql, params = connection.calls[-1]
    assert "artifact_kind = ANY" in sql
    assert params == (
        ["learning_target", "target_rotation"],
        "alr_candidate_learning_projection_artifact_v1",
        32,
    )
    assert "UPDATE" not in sql.upper()
    assert "DELETE" not in sql.upper()


def test_candidate_history_malformed_selected_target_fails_closed() -> None:
    connection = _Connection()
    projection = _projection()
    payload = projection["artifact"]["canonical_payload"]
    payload["decision"] = copy.deepcopy(projection["decision"])
    payload["decision"]["evaluated_at"] = "2026-07-10T12:00:00Z"
    payload["decision"]["selected_collection_target"] = {
        "family_key": "c" * 64,
        "material_fingerprint": None,
    }
    connection.decision_payloads = [payload]

    with pytest.raises(AlrOperationalError, match="candidate_projection_history_invalid"):
        fetch_recent_candidate_projection_decisions(connection, limit=32)

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
    source_identities = [
        {
            "source_hash": source_hashes[0],
            "source_key": "scanner-cycle-1",
            "source_ts": "2026-07-10T11:00:00Z",
        },
        {
            "source_hash": source_hashes[1],
            "source_key": "scanner-cycle-2",
            "source_ts": "2026-07-10T12:00:00Z",
        },
    ]
    decision_code = (
        "QUALIFIED_CANDIDATE_SELECTED"
        if selected
        else "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES"
    )
    family_key = ("a" if selected else "c") * 64
    evaluation_id = "b" * 64
    material_fingerprint = "d" * 64
    state = "DECISION_READY" if selected else "COLLECT_DISTINCT_ENTRIES"
    metrics = {
        "n_eff": "30.000000000000000000",
        "median_distinct_entries_7d": "5.000000000000000000",
        "expected_new_entries": "35.000000000000000000",
        "information_gain": "1.000000000000000000",
        "gate_progress": "1.000000000000000000",
        "ambiguity": "0.000000000000000000",
        "quality": "1.000000000000000000",
        "compute": "0.050000000000000000",
        "storage": "0.050000000000000000",
        "resource": "0.100000000000000000",
        "portfolio_redundancy": "0.100000000000000000",
        "day_coverage": "1.000000000000000000",
        "day_deficit": "0.000000000000000000",
        "regime_coverage": "1.000000000000000000",
        "regime_deficit": "0.000000000000000000",
        "bull_share": "0.500000000000000000",
        "evi": "0.500000000000000000",
    }
    assessment = {
        "family_key": family_key,
        "evaluation_id": evaluation_id,
        "material_fingerprint": material_fingerprint,
        "identity": {"symbol": "BTCUSDT"},
        "context_hashes": {"data": "3" * 64},
        "proof_stage": 6,
        "next_gap": {"kind": "NONE", "code": "PROOF_COMPLETE"},
        "learning_only": False,
        "state": state,
        "eligible": selected,
        "blocker_codes": [] if selected else ["N_EFF_BELOW_30"],
        "portfolio_assumption": "MEASURED",
        "scanner_context": {
            "novelty": "0.000000000000000000",
            "recurrence": "0.000000000000000000",
        },
        "metrics": metrics,
        "rank": 1,
    }
    selection_view = {
        "family_key": family_key,
        "candidate_family_key": family_key,
        "evaluation_id": evaluation_id,
        "candidate_eval_id": evaluation_id,
        "material_fingerprint": material_fingerprint,
        "state": state,
        "identity": copy.deepcopy(assessment["identity"]),
        "context_hashes": copy.deepcopy(assessment["context_hashes"]),
        "proof_stage": assessment["proof_stage"],
        "next_gap": copy.deepcopy(assessment["next_gap"]),
        "blocker_codes": list(assessment["blocker_codes"]),
        "metrics": copy.deepcopy(metrics),
        "portfolio_assumption": assessment["portfolio_assumption"],
        "learning_only": assessment["learning_only"],
        "evi": metrics["evi"],
    }
    selected_candidate = copy.deepcopy(selection_view) if selected else None
    selected_collection_target = None if selected else copy.deepcopy(selection_view)
    decision = {
        "schema_version": "alr_candidate_learning_decision_v2",
        "decision_code": decision_code,
        "evaluated_at": "2026-07-10T12:00:00Z",
        "source_head": "9" * 40,
        "source_set_hash": _sha(source_hashes),
        "evidence_source_status": "READY",
        "evidence_selection_hash": "d" * 64,
        "candidate_set_hash": "e" * 64,
        "policy_hash": "f" * 64,
        "selected_candidate": selected_candidate,
        "selected_collection_target": selected_collection_target,
        "candidate_count": 1,
        "eligible_candidate_count": int(selected),
        "evaluated_candidates": [assessment],
        "training_run_created": False,
        "model_training_performed": False,
        "serving_ready": False,
        "promotion_ready": False,
        "order_or_probe_created": False,
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
        "schema_version": "alr_candidate_learning_projection_artifact_v2",
        "decision_code": decision_code,
        "decision_hash": decision["decision_hash"],
        "decision": copy.deepcopy(decision),
        "selected_candidate": selected_candidate,
        "selected_collection_target": selected_collection_target,
        "source_refs": {
            "evidence_source_status": "READY",
            "evidence_selection_hash": "d" * 64,
            "candidate_set_hash": "e" * 64,
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
        "schema_version": "alr_candidate_learning_projection_v2",
        "source_head": "9" * 40,
        "source_set": {
            "source_set_hash": _sha(source_hashes),
            "source_hashes": source_hashes,
            "source_count": len(source_hashes),
            "as_of_ts": "2026-07-10T12:00:00Z",
            "source_identities": source_identities,
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


def _rehash_projection_hash_only(projection: dict[str, Any]) -> None:
    projection["projection_hash"] = _sha(
        {key: value for key, value in projection.items() if key != "projection_hash"}
    )


def _rehash_decision_and_projection(projection: dict[str, Any]) -> None:
    decision = projection["decision"]
    decision.pop("decision_hash", None)
    decision["decision_hash"] = _sha(decision)
    payload = projection["artifact"]["canonical_payload"]
    payload["decision"] = copy.deepcopy(decision)
    payload["decision_hash"] = decision["decision_hash"]
    payload["decision_code"] = decision["decision_code"]
    payload["selected_candidate"] = copy.deepcopy(decision["selected_candidate"])
    payload["selected_collection_target"] = copy.deepcopy(
        decision["selected_collection_target"]
    )
    _rehash_projection(projection)


def _history_artifact(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_hash": projection["artifact"]["artifact_hash"],
        "artifact_kind": projection["artifact"]["artifact_kind"],
        "canonical_payload": copy.deepcopy(
            projection["artifact"]["canonical_payload"]
        ),
    }


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
        self.decision_artifacts: list[dict[str, Any]] = []
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
            self.row = copy.deepcopy(
                [
                    artifact
                    for artifact in self.connection.decision_artifacts
                    if artifact["canonical_payload"]["decision"].get(
                        "selected_candidate"
                    )
                    is not None
                    or artifact["canonical_payload"]["decision"].get(
                        "selected_collection_target"
                    )
                    is not None
                ][: int(params[2])]
            )
        elif "SELECT artifact_kind, canonical_payload" in sql:
            artifact_hash = str(params[0])
            payload = self.connection.artifacts.get(artifact_hash)
            self.row = (
                None
                if payload is None
                else {
                    "artifact_kind": self.connection.artifact_kinds.get(
                        artifact_hash
                    ),
                    "canonical_payload": payload,
                }
            )
        elif "SELECT canonical_payload FROM learning.alr_artifact_nodes" in sql:
            payload = self.connection.artifacts.get(str(params[0]))
            self.row = None if payload is None else {"canonical_payload": payload}
        elif "SELECT edge_hash, from_artifact_hash" in sql:
            self.row = [
                {
                    "edge_hash": edge_hash,
                    "from_artifact_hash": self.connection.edges[edge_hash][0],
                    "to_artifact_hash": self.connection.edges[edge_hash][1],
                    "edge_role": self.connection.edges[edge_hash][2],
                }
                for edge_hash in params[0]
                if edge_hash in self.connection.edges
            ]
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


def test_rejects_fully_rehashed_projection_top_level_extension() -> None:
    projection = _projection()
    projection["unexpected"] = True
    _rehash_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_fields_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    ("scope", "remove", "expected_error"),
    (
        ("source_set", False, "candidate_projection_source_set_fields_invalid"),
        ("source_set", True, "candidate_projection_source_set_fields_invalid"),
        ("source_identity", False, "candidate_projection_source_identity_fields_invalid"),
        ("source_identity", True, "candidate_projection_source_identity_fields_invalid"),
        ("decision", False, "candidate_projection_decision_fields_invalid"),
        ("decision", True, "candidate_projection_decision_fields_invalid"),
        ("artifact", False, "candidate_projection_artifact_fields_invalid"),
        ("artifact", True, "candidate_projection_artifact_fields_invalid"),
        ("payload", False, "candidate_projection_artifact_payload_fields_invalid"),
        ("payload", True, "candidate_projection_artifact_payload_fields_invalid"),
        ("edge", False, "candidate_projection_edge_fields_invalid"),
        ("edge", True, "candidate_projection_edge_fields_invalid"),
    ),
)
def test_rejects_fully_rehashed_extra_or_missing_nested_projection_fields(
    scope: str,
    remove: bool,
    expected_error: str,
) -> None:
    projection = _projection()
    if scope == "source_set":
        target = projection["source_set"]
        key = "as_of_ts"
    elif scope == "source_identity":
        target = projection["source_set"]["source_identities"][0]
        key = "source_key"
    elif scope == "decision":
        target = projection["decision"]
        key = "policy_hash"
    elif scope == "artifact":
        target = projection["artifact"]
        key = "artifact_kind"
    elif scope == "payload":
        target = projection["artifact"]["canonical_payload"]
        key = "next_stage"
    else:
        target = projection["provenance_edges"][0]
        key = "edge_role"
    if remove:
        target.pop(key)
    else:
        target["unexpected"] = True

    if scope == "decision":
        _rehash_decision_and_projection(projection)
    elif scope == "payload":
        _rehash_projection(projection)
    else:
        _rehash_projection_hash_only(projection)

    with pytest.raises(AlrOperationalError, match=expected_error):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        (
            "reordered",
            "candidate_projection_source_identity_hash_order_mismatch",
        ),
        (
            "forged_hash",
            "candidate_projection_source_identity_hash_order_mismatch",
        ),
        (
            "identity_timestamp",
            "candidate_projection_source_identity_ts_invalid",
        ),
        (
            "as_of_timestamp",
            "candidate_projection_source_set_as_of_invalid",
        ),
        (
            "stale_as_of",
            "candidate_projection_source_set_as_of_mismatch",
        ),
    ),
)
def test_rejects_forged_source_identity_order_and_noncanonical_timestamps(
    mutation: str,
    expected_error: str,
) -> None:
    projection = _projection()
    source_set = projection["source_set"]
    identities = source_set["source_identities"]
    if mutation == "reordered":
        source_set["source_identities"] = list(reversed(identities))
    elif mutation == "forged_hash":
        identities[0]["source_hash"] = identities[1]["source_hash"]
    elif mutation == "identity_timestamp":
        identities[0]["source_ts"] = "2026-07-10T11:00:00+00:00"
    elif mutation == "as_of_timestamp":
        source_set["as_of_ts"] = "2026-07-10T12:00:00.000000Z"
    else:
        source_set["as_of_ts"] = "2026-07-10T11:00:00Z"
    _rehash_projection_hash_only(projection)

    with pytest.raises(AlrOperationalError, match=expected_error):
        build_candidate_learning_projection_plan(projection)


def test_rejects_fully_rehashed_noncanonical_source_order() -> None:
    projection = _projection()
    source_set = projection["source_set"]
    source_set["source_hashes"] = list(reversed(source_set["source_hashes"]))
    source_set["source_identities"] = list(
        reversed(source_set["source_identities"])
    )
    source_set["source_set_hash"] = _sha(source_set["source_hashes"])
    projection["decision"]["source_set_hash"] = source_set["source_set_hash"]
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_source_identity_order_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize("tie_break", ("source_key", "source_hash"))
def test_rejects_fully_rehashed_noncanonical_source_tuple_tie_break(
    tie_break: str,
) -> None:
    projection = _projection()
    source_set = projection["source_set"]
    identities = source_set["source_identities"]
    identities[0]["source_ts"] = "2026-07-10T12:00:00Z"
    if tie_break == "source_key":
        identities[0]["source_key"] = "scanner-cycle-b"
        identities[1]["source_key"] = "scanner-cycle-a"
        _rehash_projection_hash_only(projection)
    else:
        identities[0]["source_key"] = "scanner-cycle"
        identities[1]["source_key"] = "scanner-cycle"
        source_set["source_hashes"] = list(reversed(source_set["source_hashes"]))
        source_set["source_identities"] = list(reversed(identities))
        source_set["source_set_hash"] = _sha(source_set["source_hashes"])
        projection["decision"]["source_set_hash"] = source_set["source_set_hash"]
        _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_source_identity_order_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_rehashed_noncanonical_decision_timestamp() -> None:
    projection = _projection()
    projection["decision"]["evaluated_at"] = "2026-07-10T12:00:00+00:00"
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_evaluated_at_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_rehashed_decision_time_before_source_as_of() -> None:
    projection = _projection()
    projection["decision"]["evaluated_at"] = "2026-07-10T11:59:59Z"
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_before_source",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_rehashed_nonproducer_decision_code() -> None:
    projection = _projection()
    decision = projection["decision"]
    decision.update(
        {
            "decision_code": "NO_QUALIFIED_CANDIDATE_FABRICATED",
            "selected_collection_target": None,
            "candidate_count": 0,
            "eligible_candidate_count": 0,
            "evaluated_candidates": [],
        }
    )
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_code_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    ("field", "value", "expected_error"),
    (
        (
            "source_head",
            "8" * 40,
            "candidate_projection_decision_source_head_mismatch",
        ),
        (
            "source_set_hash",
            "f" * 64,
            "candidate_projection_decision_source_set_mismatch",
        ),
    ),
)
def test_rejects_rehashed_decision_with_unbound_projection_source(
    field: str,
    value: str,
    expected_error: str,
) -> None:
    projection = _projection()
    projection["decision"][field] = value
    _rehash_decision_and_projection(projection)

    with pytest.raises(AlrOperationalError, match=expected_error):
        build_candidate_learning_projection_plan(projection)


def test_missing_evidence_source_can_persist_honest_durable_abstention() -> None:
    projection = _projection()
    payload = projection["artifact"]["canonical_payload"]
    refs = payload["source_refs"]
    refs.update(
        {
            "evidence_source_status": "DIRECTORY_MISSING",
            "evidence_selection_hash": None,
            "candidate_set_hash": None,
        }
    )
    decision = projection["decision"]
    decision.update(
        {
            "decision_code": "NO_QUALIFIED_CANDIDATE_REPAIR_DATA",
            "evidence_source_status": "DIRECTORY_MISSING",
            "evidence_selection_hash": None,
                "candidate_set_hash": None,
                "selected_collection_target": None,
                "candidate_count": 0,
                "eligible_candidate_count": 0,
                "evaluated_candidates": [],
            }
        )
    decision.pop("decision_hash")
    decision["decision_hash"] = _sha(decision)
    payload.update(
        {
            "decision_code": decision["decision_code"],
            "decision_hash": decision["decision_hash"],
            "selected_collection_target": None,
            "decision": copy.deepcopy(decision),
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


def test_selected_projection_replay_rejects_existing_wrong_artifact_kind() -> None:
    connection = _Connection()
    projection = _projection(selected=True)
    persist_candidate_learning_projection(connection, projection)
    artifact_hash = projection["artifact"]["artifact_hash"]
    connection.artifact_kinds[artifact_hash] = "target_rotation"

    with pytest.raises(
        AlrOperationalConflict,
        match="candidate_projection_artifact_hash_conflict",
    ):
        persist_candidate_learning_projection(connection, projection)

    assert connection.rollbacks == 1


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


def test_duplicate_fails_closed_when_edge_content_drifted_under_same_hash() -> None:
    connection = _Connection()
    projection = _projection()
    persist_candidate_learning_projection(connection, projection)
    edge_hash = next(iter(connection.edges))
    _, to_hash, role = connection.edges[edge_hash]
    connection.edges[edge_hash] = ("f" * 64, to_hash, role)

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
        (("artifact", "canonical_payload", "source_refs", "latest_alias_used"), True, "candidate_projection_source_refs_invalid"),
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


@pytest.mark.parametrize(
    "field",
    (
        "training_run_created",
        "model_training_performed",
        "serving_ready",
        "promotion_ready",
        "order_or_probe_created",
    ),
)
def test_rejects_fully_rehashed_decision_false_claim_contradiction(
    field: str,
) -> None:
    projection = _projection()
    projection["decision"][field] = True
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_training_claim_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    "field",
    (
        "training_run_created",
        "model_training_performed",
        "serving_ready",
        "promotion_ready",
        "order_or_probe_created",
    ),
)
def test_rejects_fully_rehashed_artifact_payload_false_claim_contradiction(
    field: str,
) -> None:
    projection = _projection()
    projection["artifact"]["canonical_payload"][field] = True
    _rehash_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_training_claim_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    "field",
    (
        "training_run_created",
        "model_training_performed",
        "serving_ready",
        "promotion_ready",
        "order_or_probe_created",
    ),
)
def test_rejects_fully_rehashed_mutually_consistent_but_effectful_claims(
    field: str,
) -> None:
    projection = _projection()
    projection["decision"][field] = True
    projection["artifact"]["canonical_payload"][field] = True
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_training_claim_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    "mutation",
    (
        "candidate_count",
        "eligible_count",
        "rank",
        "eligible_state",
        "selected_view",
    ),
)
def test_rejects_rehashed_decision_count_rank_or_selection_drift(
    mutation: str,
) -> None:
    projection = _projection(selected=True)
    decision = projection["decision"]
    if mutation == "candidate_count":
        decision["candidate_count"] += 1
    elif mutation == "eligible_count":
        decision["eligible_candidate_count"] = 0
    elif mutation == "rank":
        decision["evaluated_candidates"][0]["rank"] = 2
    elif mutation == "eligible_state":
        decision["evaluated_candidates"][0]["eligible"] = False
    else:
        decision["selected_candidate"]["material_fingerprint"] = "0" * 64
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_rehashed_boolean_assessment_rank() -> None:
    projection = _projection(selected=True)
    projection["decision"]["evaluated_candidates"][0]["rank"] = True
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_type_loose_embedded_decision_rank_drift() -> None:
    projection = _projection(selected=True)
    embedded = projection["artifact"]["canonical_payload"]["decision"]
    embedded["evaluated_candidates"][0]["rank"] = True
    _rehash_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_payload_mismatch",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_rehashed_assessment_extension() -> None:
    projection = _projection(selected=True)
    projection["decision"]["evaluated_candidates"][0]["unexpected"] = True
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize(
    "mutation",
    (
        "metrics_extra",
        "metrics_missing",
        "metrics_nonfinite",
        "metrics_noncanonical",
        "scanner_extra",
        "scanner_noncanonical",
        "proof_stage_out_of_range",
    ),
)
def test_rejects_rehashed_assessment_ranking_input_drift(mutation: str) -> None:
    projection = _projection(selected=True)
    assessment = projection["decision"]["evaluated_candidates"][0]
    if mutation == "metrics_extra":
        assessment["metrics"]["unexpected"] = "0.000000000000000000"
    elif mutation == "metrics_missing":
        assessment["metrics"].pop("quality")
    elif mutation == "metrics_nonfinite":
        assessment["metrics"]["quality"] = "Infinity"
    elif mutation == "metrics_noncanonical":
        assessment["metrics"]["quality"] = "1.0"
    elif mutation == "scanner_extra":
        assessment["scanner_context"]["unexpected"] = "0.000000000000000000"
    elif mutation == "scanner_noncanonical":
        assessment["scanner_context"]["novelty"] = "0.0"
    else:
        assessment["proof_stage"] = 999
    selected = projection["decision"]["selected_candidate"]
    selected["metrics"] = copy.deepcopy(assessment["metrics"])
    selected["evi"] = assessment["metrics"].get("evi")
    selected["proof_stage"] = assessment["proof_stage"]
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_cooldown_field_outside_wait_state() -> None:
    projection = _projection(selected=True)
    projection["decision"]["evaluated_candidates"][0][
        "cooldown_remaining_seconds"
    ] = 60
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_wait_assessment_requires_exact_cooldown_field() -> None:
    projection = _projection()
    decision = projection["decision"]
    assessment = decision["evaluated_candidates"][0]
    assessment["state"] = "WAIT_COOLDOWN"
    assessment["blocker_codes"] = ["COOLDOWN_ACTIVE"]
    decision["decision_code"] = "NO_QUALIFIED_CANDIDATE_WAIT_COOLDOWN"
    decision["selected_collection_target"] = None
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)

    assessment["cooldown_remaining_seconds"] = 60
    _rehash_decision_and_projection(projection)

    plan = build_candidate_learning_projection_plan(projection)
    assert plan["decision_code"] == "NO_QUALIFIED_CANDIDATE_WAIT_COOLDOWN"


@pytest.mark.parametrize(
    ("state", "decision_code", "metrics_none"),
    (
        ("REPAIR_DATA_QUALITY", "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION", False),
        ("WAIT_COOLDOWN", "NO_QUALIFIED_CANDIDATE_EXTERNAL_GAP", False),
        ("EXTERNAL_GAP", "NO_QUALIFIED_CANDIDATE_REPAIR_DATA", False),
        ("MADE_UP_STATE", "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION", False),
        ("INELIGIBLE", "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION", True),
    ),
)
def test_rejects_rehashed_assessment_state_or_decision_priority_drift(
    state: str,
    decision_code: str,
    metrics_none: bool,
) -> None:
    projection = _projection()
    decision = projection["decision"]
    assessment = decision["evaluated_candidates"][0]
    assessment["state"] = state
    assessment["eligible"] = False
    if metrics_none:
        assessment["metrics"] = None
    decision["decision_code"] = decision_code
    decision["selected_collection_target"] = None
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_ready_candidate_wins_even_when_an_invalid_assessment_has_no_metrics() -> None:
    projection = _projection(selected=True)
    decision = projection["decision"]
    decision["evaluated_candidates"].append(
        {
            "family_key": None,
            "evaluation_id": None,
            "material_fingerprint": None,
            "identity": None,
            "state": "INELIGIBLE",
            "eligible": False,
            "blocker_codes": ["ARBITER_INPUT_NOT_MAPPING"],
            "portfolio_assumption": None,
            "scanner_context": {
                "novelty": "0.000000000000000000",
                "recurrence": "0.000000000000000000",
            },
            "metrics": None,
            "rank": 2,
        }
    )
    decision["candidate_count"] = 2
    _rehash_decision_and_projection(projection)

    plan = build_candidate_learning_projection_plan(projection)

    assert plan["decision_code"] == "QUALIFIED_CANDIDATE_SELECTED"

    ready, ineligible = decision["evaluated_candidates"]
    ineligible["rank"] = 1
    ready["rank"] = 2
    decision["evaluated_candidates"] = [ineligible, ready]
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_mixed_ineligible_shapes_require_canonical_repository_order() -> None:
    projection = _projection()
    decision = projection["decision"]
    valid = decision["evaluated_candidates"][0]
    valid.update(
        {
            "state": "INELIGIBLE",
            "eligible": False,
            "blocker_codes": ["ZERO_RESOURCE_NO_COLLECTION"],
            "rank": 1,
        }
    )
    invalid = {
        "family_key": None,
        "evaluation_id": None,
        "material_fingerprint": None,
        "identity": None,
        "state": "INELIGIBLE",
        "eligible": False,
        "blocker_codes": ["ARBITER_INPUT_NOT_MAPPING"],
        "portfolio_assumption": None,
        "scanner_context": {
            "novelty": "0.000000000000000000",
            "recurrence": "0.000000000000000000",
        },
        "metrics": None,
        "rank": 2,
    }
    decision.update(
        {
            "decision_code": "NO_QUALIFIED_CANDIDATE_REPAIR_DATA",
            "selected_collection_target": None,
            "candidate_count": 2,
            "eligible_candidate_count": 0,
            "evaluated_candidates": [valid, invalid],
        }
    )
    _rehash_decision_and_projection(projection)

    plan = build_candidate_learning_projection_plan(projection)
    assert plan["decision_code"] == "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"

    valid["rank"] = 2
    invalid["rank"] = 1
    decision["evaluated_candidates"] = [invalid, valid]
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_rehashed_assessment_rank_rewrite_selecting_lower_candidate() -> None:
    projection = _projection(selected=True)
    decision = projection["decision"]
    first = decision["evaluated_candidates"][0]
    second = copy.deepcopy(first)
    second.update(
        {
            "family_key": "0" * 64,
            "evaluation_id": "1" * 64,
            "material_fingerprint": "2" * 64,
            "proof_stage": 5,
            "rank": 2,
        }
    )
    second_view = copy.deepcopy(decision["selected_candidate"])
    second_view.update(
        {
            "family_key": second["family_key"],
            "candidate_family_key": second["family_key"],
            "evaluation_id": second["evaluation_id"],
            "candidate_eval_id": second["evaluation_id"],
            "material_fingerprint": second["material_fingerprint"],
            "proof_stage": second["proof_stage"],
        }
    )
    decision["evaluated_candidates"] = [first, second]
    decision["candidate_count"] = 2
    decision["eligible_candidate_count"] = 2
    _rehash_decision_and_projection(projection)
    build_candidate_learning_projection_plan(projection)

    second["rank"] = 1
    first["rank"] = 2
    decision["evaluated_candidates"] = [second, first]
    decision["selected_candidate"] = second_view
    _rehash_decision_and_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_decision_semantics_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


@pytest.mark.parametrize("scope", ("projection", "decision", "payload"))
@pytest.mark.parametrize("field", ("no_authority", "authority_counters"))
@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_candidate_authority_keysets_are_exact_at_every_layer(
    scope: str,
    field: str,
    mutation: str,
) -> None:
    projection = _projection()
    target = (
        projection
        if scope == "projection"
        else projection["decision"]
        if scope == "decision"
        else projection["artifact"]["canonical_payload"]
    )
    mapping = target[field]
    if mutation == "missing":
        mapping.pop(next(iter(mapping)))
    else:
        mapping["unexpected"] = False if field == "no_authority" else 0
    if scope == "projection":
        _rehash_projection_hash_only(projection)
    elif scope == "decision":
        _rehash_decision_and_projection(projection)
    else:
        _rehash_projection(projection)

    with pytest.raises(
        AlrOperationalError,
        match="candidate_projection_authority_invalid",
    ):
        build_candidate_learning_projection_plan(projection)


def test_rejects_hash_tampering_or_kind_decision_mismatch() -> None:
    tampered = _projection()
    tampered["artifact"]["artifact_hash"] = "0" * 64
    with pytest.raises(AlrOperationalError, match="candidate_projection_artifact_hash_mismatch"):
        build_candidate_learning_projection_plan(tampered)

    wrong_kind = _projection(selected=True)
    wrong_kind["artifact"]["artifact_kind"] = "target_rotation"
    with pytest.raises(AlrOperationalError, match="candidate_projection_artifact_kind_mismatch"):
        build_candidate_learning_projection_plan(wrong_kind)


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    (
        ("missing", "candidate_projection_artifact_payload_fields_invalid"),
        ("partial", "candidate_projection_decision_payload_mismatch"),
        ("different", "candidate_projection_decision_payload_mismatch"),
    ),
)
def test_rejects_artifact_without_exact_self_describing_decision(
    mutation: str,
    expected_error: str,
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
        match=expected_error,
    ):
        build_candidate_learning_projection_plan(projection)


def test_reads_bounded_recent_candidate_history_for_cooldown_without_mutation() -> None:
    connection = _Connection()
    projection = _projection()
    _rehash_decision_and_projection(projection)
    connection.decision_artifacts = [_history_artifact(projection)]

    rows = fetch_recent_candidate_projection_decisions(connection, limit=32)

    assert rows == [
        {
            "decision_schema_version": "alr_candidate_learning_decision_v2",
            "family_key": "c" * 64,
            "material_fingerprint": "d" * 64,
            "decision_ts_s": 1_783_684_800,
        }
    ]
    sql, params = connection.calls[-1]
    assert "artifact_kind = ANY" in sql
    assert params == (
        ["learning_target", "target_rotation"],
        "alr_candidate_learning_projection_artifact_v2",
        32,
    )
    assert "UPDATE" not in sql.upper()
    assert "DELETE" not in sql.upper()


def test_unselected_history_rows_cannot_exhaust_limit_before_selected_prior() -> None:
    connection = _Connection()
    waits: list[dict[str, Any]] = []
    for index in range(64):
        projection = _projection()
        decision = projection["decision"]
        assessment = decision["evaluated_candidates"][0]
        assessment.update(
            {
                "state": "WAIT_COOLDOWN",
                "eligible": False,
                "blocker_codes": ["COOLDOWN_ACTIVE"],
                "cooldown_remaining_seconds": index + 1,
            }
        )
        decision.update(
            {
                "decision_code": "NO_QUALIFIED_CANDIDATE_WAIT_COOLDOWN",
                "selected_collection_target": None,
                "eligible_candidate_count": 0,
            }
        )
        _rehash_decision_and_projection(projection)
        waits.append(_history_artifact(projection))
    selected = _projection(selected=True)
    _rehash_decision_and_projection(selected)
    connection.decision_artifacts = [*waits, _history_artifact(selected)]

    rows = fetch_recent_candidate_projection_decisions(connection, limit=64)

    assert len(rows) == 1
    assert rows[0]["family_key"] == "a" * 64
    sql, _ = connection.calls[-1]
    assert "selected_candidate" in sql
    assert "selected_collection_target" in sql


def test_candidate_history_explicitly_ignores_v1_rows_even_if_driver_returns_them() -> None:
    connection = _Connection()
    projection = _projection()
    artifact = _history_artifact(projection)
    artifact["canonical_payload"]["schema_version"] = (
        "alr_candidate_learning_projection_artifact_v1"
    )
    artifact["canonical_payload"]["decision"]["schema_version"] = (
        "alr_candidate_learning_decision_v1"
    )
    connection.decision_artifacts = [artifact]

    rows = fetch_recent_candidate_projection_decisions(connection, limit=32)

    assert rows == []


def test_candidate_history_malformed_selected_target_fails_closed() -> None:
    connection = _Connection()
    projection = _projection()
    projection["decision"]["selected_collection_target"] = {
        "family_key": "c" * 64,
        "material_fingerprint": None,
    }
    _rehash_decision_and_projection(projection)
    connection.decision_artifacts = [_history_artifact(projection)]

    with pytest.raises(AlrOperationalError, match="candidate_projection_history_invalid"):
        fetch_recent_candidate_projection_decisions(connection, limit=32)


@pytest.mark.parametrize(
    "mutation",
    (
        "artifact_hash",
        "decision_hash",
        "payload_extra",
        "decision_effect_claim",
        "payload_effect_claim",
        "authority",
        "authority_shape",
        "source_binding",
    ),
)
def test_candidate_history_rejects_non_self_consistent_v2_artifact(
    mutation: str,
) -> None:
    connection = _Connection()
    projection = _projection()
    _rehash_decision_and_projection(projection)
    artifact = _history_artifact(projection)
    payload = artifact["canonical_payload"]
    if mutation == "artifact_hash":
        artifact["artifact_hash"] = "0" * 64
    elif mutation == "decision_hash":
        payload["decision"]["evaluated_at"] = "2026-07-10T12:00:01Z"
        artifact["artifact_hash"] = _sha(payload)
    elif mutation == "payload_extra":
        payload["unexpected"] = True
        artifact["artifact_hash"] = _sha(payload)
    elif mutation == "decision_effect_claim":
        payload["decision"]["model_training_performed"] = True
        payload["decision"].pop("decision_hash")
        payload["decision"]["decision_hash"] = _sha(payload["decision"])
        payload["decision_hash"] = payload["decision"]["decision_hash"]
        artifact["artifact_hash"] = _sha(payload)
    elif mutation == "payload_effect_claim":
        payload["model_training_performed"] = True
        artifact["artifact_hash"] = _sha(payload)
    elif mutation == "authority":
        payload["no_authority"]["trading_authority"] = True
        artifact["artifact_hash"] = _sha(payload)
    elif mutation == "authority_shape":
        payload["no_authority"].pop("trading_authority")
        artifact["artifact_hash"] = _sha(payload)
    else:
        payload["source_refs"]["candidate_set_hash"] = "0" * 64
        artifact["artifact_hash"] = _sha(payload)
    connection.decision_artifacts = [artifact]

    with pytest.raises(AlrOperationalError, match="candidate_projection_history_invalid"):
        fetch_recent_candidate_projection_decisions(connection, limit=32)

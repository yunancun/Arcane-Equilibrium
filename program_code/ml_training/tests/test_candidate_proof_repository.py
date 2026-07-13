from __future__ import annotations

import copy
import hashlib
import inspect
import json
from datetime import datetime, timezone
from typing import Any

import pytest

from ml_training.alr_outcome_bridge import (
    build_alr_outcome_bridge_packet,
    compute_alr_outcome_bridge_hash,
)
from ml_training.candidate_proof_adapter import (
    NO_MATCHED_FILLS,
    PENDING_EVIDENCE,
    READY_FOR_REWARD_VALIDATION,
)
from ml_training.candidate_proof_repository import (
    CandidateProofRepositoryError,
    discover_candidate_proof_receipts,
)
from ml_training.reward_ledger import compute_reward_record_hash
from ml_training.proof_packet_contract import compute_proof_packet_hash
from ml_training.tests.test_alr_candidate_projection_repository import (
    _projection,
    _with_handoff,
)
from ml_training.tests.test_candidate_proof_adapter import (
    _binding,
    _bound_no_fill_packet,
    _bound_ready_packet,
    _bound_reward_record,
    _selected_projection,
)


def _sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _projection_row(projection: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_hash": projection["artifact"]["artifact_hash"],
        "artifact_kind": projection["artifact"]["artifact_kind"],
        "canonical_payload": copy.deepcopy(
            projection["artifact"]["canonical_payload"]
        ),
        "created_at": "2026-07-10T12:00:00Z",
    }


def _lineage_rows(projection: dict[str, Any]) -> list[dict[str, Any]]:
    identities = {
        item["source_hash"]: item for item in projection["source_set"]["source_identities"]
    }
    rows: list[dict[str, Any]] = []
    for edge in projection["provenance_edges"]:
        identity = identities[edge["from_artifact_hash"]]
        rows.append(
            {
                **copy.deepcopy(edge),
                "source_table": "trading.scanner_snapshots",
                "source_key": identity["source_key"],
                "source_ts": identity["source_ts"],
                "source_hash": identity["source_hash"],
            }
        )
    return rows


def _bridge_row(
    proof_packet: dict[str, Any],
    reward_records: list[dict[str, Any]],
    *,
    salt: str = "a",
) -> dict[str, Any]:
    bridge = build_alr_outcome_bridge_packet(
        proof_packet=proof_packet,
        reward_records=reward_records,
    )
    payload = {
        "schema_version": "alr_outcome_bridge_artifact_v1",
        "run_hash": salt * 64,
        "candidate_artifact_hash": ("b" if salt != "b" else "c") * 64,
        "bridge": bridge,
    }
    return {
        "artifact_hash": _sha(payload),
        "canonical_payload": payload,
        "created_at": "2026-07-10T12:01:00Z",
    }


class _Connection:
    def __init__(
        self,
        projection: dict[str, Any],
        *,
        prior_projection_rows: list[dict[str, Any]] | None = None,
        bridge_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.projection_rows = [
            _projection_row(projection),
            *(copy.deepcopy(prior_projection_rows) if prior_projection_rows else []),
        ]
        self.primary_artifact_hash = projection["artifact"]["artifact_hash"]
        self.lineage_by_artifact = {
            projection["artifact"]["artifact_hash"]: _lineage_rows(projection)
        }
        self.bridge_rows = copy.deepcopy(bridge_rows or [])
        self.recheck_projection_row: dict[str, Any] | None = None
        self.recheck_lineage_rows: list[dict[str, Any]] | None = None
        self.recheck_bridge_rows: list[dict[str, Any]] | None = None
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> "_Cursor":
        return _Cursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _Cursor:
    def __init__(self, connection: _Connection) -> None:
        self.connection = connection
        self.rows: Any = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        assert params is not None
        if "candidate-proof:snapshot-recheck" in sql:
            head = (
                self.connection.recheck_projection_row
                or self.connection.projection_rows[0]
            )
            head_hash = (
                head["artifact_hash"] if isinstance(head, dict) else head[0]
            )
            lineage = (
                self.connection.recheck_lineage_rows
                if self.connection.recheck_lineage_rows is not None
                else self.connection.lineage_by_artifact.get(
                    self.connection.primary_artifact_hash, []
                )
            )
            bridges = (
                self.connection.recheck_bridge_rows
                if self.connection.recheck_bridge_rows is not None
                else self.connection.bridge_rows
            )
            self.rows = {
                "head_artifact_hash": head_hash,
                "lineage_rows": copy.deepcopy(lineage),
                "bridge_rows": copy.deepcopy(
                    bridges[
                        : next(item for item in params if isinstance(item, int))
                    ]
                ),
            }
        elif "candidate-proof:latest-projection" in sql:
            self.rows = [copy.deepcopy(self.connection.projection_rows[0])]
        elif "candidate-proof:projection-lineage" in sql:
            artifact_hash = str(params[1])
            self.rows = copy.deepcopy(
                self.connection.lineage_by_artifact.get(artifact_hash, [])
            )
        elif "candidate-proof:outcome-bridges" in sql:
            self.rows = copy.deepcopy(self.connection.bridge_rows[: int(params[-1])])
        else:  # pragma: no cover - catches accidental repository expansion
            raise AssertionError(f"unexpected_sql:{sql}")

    def fetchone(self) -> Any:
        if isinstance(self.rows, dict):
            return self.rows
        return None if not self.rows else self.rows[0]

    def fetchall(self) -> Any:
        return self.rows


def test_reconstructs_selected_projection_and_returns_pending_zero_write_receipt() -> None:
    projection = _selected_projection()
    connection = _Connection(projection)

    batch = discover_candidate_proof_receipts(connection, limit=8)

    assert batch["status"] == "READY"
    assert len(batch["receipts"]) == 1
    receipt = batch["receipts"][0]
    assert receipt["status"] == PENDING_EVIDENCE
    assert receipt["projection_identity_status"] == (
        "RECONSTRUCTED_FROM_HASH_VALIDATED_ROWS"
    )
    assert receipt["original_ephemeral_projection_hash_attested"] is False
    assert receipt["projection_refs"]["artifact_hash"] == projection["artifact"][
        "artifact_hash"
    ]
    assert receipt["selection_binding"] == _binding(projection)
    assert receipt["source_artifacts"] == {
        "proof_packet": None,
        "reward_records": [],
    }
    assert receipt["durability"] == {
        "source_container": "NO_MATCHING_HASH_VALIDATED_ROW",
        "runtime_or_exchange_attested": False,
        "receipt_persisted": False,
    }
    assert receipt["adapter_result"]["projection_refs"][
        "durable_receipt_status"
    ] == "unverified_source_only"
    assert set(receipt["no_authority"].values()) == {False}
    assert set(receipt["authority_counters"].values()) == {0}
    assert batch["metrics"]["rows_written"] == 0
    assert batch["metrics"]["payload_bytes_written"] == 0
    assert connection.commits == connection.rollbacks == 0
    assert batch["metrics"]["candidate_projection_rows_read"] == 2
    assert batch["metrics"]["projection_edge_rows_rechecked"] == 2
    assert batch["metrics"]["source_event_rows_rechecked"] == 2
    sql = "\n".join(item[0] for item in connection.calls).upper()
    assert "INSERT " not in sql
    assert "UPDATE " not in sql
    assert "DELETE " not in sql


def test_mapping_and_tuple_cursor_rows_have_repository_parity() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    connection = _Connection(
        projection,
        bridge_rows=[_bridge_row(proof, [])],
    )
    projection_row = connection.projection_rows[0]
    connection.projection_rows[0] = (
        projection_row["artifact_hash"],
        projection_row["artifact_kind"],
        projection_row["canonical_payload"],
        projection_row["created_at"],
    )
    connection.lineage_by_artifact[connection.primary_artifact_hash] = [
        (
            row["edge_hash"],
            row["from_artifact_hash"],
            row["to_artifact_hash"],
            row["edge_role"],
            row["source_table"],
            row["source_key"],
            row["source_ts"],
            row["source_hash"],
        )
        for row in connection.lineage_by_artifact[connection.primary_artifact_hash]
    ]
    bridge_row = connection.bridge_rows[0]
    connection.bridge_rows[0] = (
        bridge_row["artifact_hash"],
        bridge_row["canonical_payload"],
        bridge_row["created_at"],
    )

    batch = discover_candidate_proof_receipts(connection, limit=8)

    assert batch["status"] == "READY"
    assert batch["receipts"][0]["status"] == READY_FOR_REWARD_VALIDATION


def test_subsecond_timestamptz_lineage_reconstructs_whole_second_projection() -> None:
    projection = _selected_projection()
    connection = _Connection(projection)
    artifact_hash = connection.primary_artifact_hash
    for row in connection.lineage_by_artifact[artifact_hash]:
        canonical = datetime.fromisoformat(
            row["source_ts"].replace("Z", "+00:00")
        ).astimezone(timezone.utc)
        row["source_ts"] = canonical.replace(microsecond=123_000)

    batch = discover_candidate_proof_receipts(connection, limit=8)

    assert batch["status"] == "READY"
    assert batch["receipts"][0]["status"] == PENDING_EVIDENCE
    assert batch["metrics"]["source_event_rows_read"] == 2


def test_hash_validated_bridge_uses_internal_binding_and_exact_source_bytes() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    rewards = [
        _bound_reward_record(proof, window_id="window-b"),
        _bound_reward_record(proof, window_id="window-a"),
    ]
    connection = _Connection(
        projection,
        bridge_rows=[_bridge_row(proof, list(reversed(rewards)))],
    )

    batch = discover_candidate_proof_receipts(connection, limit=8)

    receipt = batch["receipts"][0]
    assert receipt["status"] == READY_FOR_REWARD_VALIDATION
    assert receipt["selection_binding"] == binding
    assert receipt["source_artifacts"]["proof_packet"] == proof
    stored_rewards = connection.bridge_rows[0]["canonical_payload"]["bridge"][
        "source_artifacts"
    ]["reward_records"]
    assert receipt["source_artifacts"]["reward_records"] == stored_rewards
    assert receipt["exact_source_containers"][0]["source_artifacts"][
        "reward_records"
    ] == stored_rewards
    canonical_reward_hashes = [
        compute_reward_record_hash(item)
        for item in receipt["canonical_adapter_inputs"]["reward_records"]
    ]
    assert canonical_reward_hashes == sorted(canonical_reward_hashes)
    assert receipt["durability"]["source_container"] == (
        "HASH_VALIDATED_APPEND_ONLY_ROW"
    )
    assert receipt["durability"]["receipt_persisted"] is False
    assert receipt["repository_sources"]["outcome_bridge_artifact_hashes"] == [
        connection.bridge_rows[0]["artifact_hash"]
    ]


def test_valid_no_fill_is_a_non_reward_receipt() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_no_fill_packet(projection, binding)
    batch = discover_candidate_proof_receipts(
        _Connection(projection, bridge_rows=[_bridge_row(proof, [])]),
        limit=8,
    )

    receipt = batch["receipts"][0]
    assert receipt["status"] == NO_MATCHED_FILLS
    assert receipt["source_artifacts"]["reward_records"] == []
    assert batch["metrics"]["no_fill_receipts"] == 1
    assert batch["metrics"]["ready_for_reward_validation_receipts"] == 0


def test_reward_permutation_keeps_exact_containers_and_one_canonical_receipt() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    rewards = [
        _bound_reward_record(proof, window_id="window-a"),
        _bound_reward_record(proof, window_id="window-b"),
    ]
    rows = [
        _bridge_row(proof, rewards, salt="a"),
        _bridge_row(proof, list(reversed(rewards)), salt="b"),
    ]

    batch = discover_candidate_proof_receipts(
        _Connection(projection, bridge_rows=rows),
        limit=8,
    )

    assert len(batch["receipts"]) == 1
    receipt = batch["receipts"][0]
    assert len(receipt["exact_source_containers"]) == 2
    exact_orders = [
        [item["record_hash"] for item in source["source_artifacts"]["reward_records"]]
        for source in receipt["exact_source_containers"]
    ]
    assert exact_orders == [
        [item["record_hash"] for item in rewards],
        [item["record_hash"] for item in reversed(rewards)],
    ]
    canonical_hashes = [
        compute_reward_record_hash(item)
        for item in receipt["canonical_adapter_inputs"]["reward_records"]
    ]
    assert canonical_hashes == sorted(canonical_hashes)


def test_hash_valid_bridge_with_projection_mismatch_is_invalid_not_pending() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    proof["provenance"]["input_artifact_hashes"][
        "candidate_projection_decision_hash"
    ] = "f" * 64
    proof["proof_packet_hash"] = compute_proof_packet_hash(proof)

    batch = discover_candidate_proof_receipts(
        _Connection(projection, bridge_rows=[_bridge_row(proof, [])]),
        limit=8,
    )

    assert batch["receipts"][0]["status"] == "INVALID"
    assert batch["metrics"]["invalid_receipts"] == 1
    assert batch["metrics"]["pending_receipts"] == 0


def test_newer_valid_rotation_suppresses_stale_selected_projection() -> None:
    selected = _selected_projection()
    rotation = _with_handoff(_projection(selected=False))
    connection = _Connection(
        rotation,
        prior_projection_rows=[_projection_row(selected)],
    )

    batch = discover_candidate_proof_receipts(connection, limit=8)

    assert batch["status"] == "NO_CURRENT_SELECTED_CANDIDATE"
    assert batch["receipts"] == []
    assert batch["metrics"]["candidate_projection_rows_read"] == 1
    assert not any(
        "candidate-proof:outcome-bridges" in sql for sql, _ in connection.calls
    )


def test_candidate_family_query_sees_unknown_newer_schema_and_fails_closed() -> None:
    projection = _selected_projection()
    connection = _Connection(projection)
    connection.projection_rows[0]["canonical_payload"]["schema_version"] = (
        "alr_candidate_learning_projection_artifact_v999"
    )

    with pytest.raises(CandidateProofRepositoryError, match="schema"):
        discover_candidate_proof_receipts(connection, limit=8)

    sql = next(
        statement
        for statement, _ in connection.calls
        if "candidate-proof:latest-projection" in statement
    )
    assert "schema_version' LIKE" in sql
    assert "{decision,schema_version}" in sql


def test_rotation_appended_during_read_cannot_yield_stale_receipt() -> None:
    selected = _selected_projection()
    connection = _Connection(selected)
    rotation = _with_handoff(_projection(selected=False))
    connection.recheck_projection_row = _projection_row(rotation)

    with pytest.raises(CandidateProofRepositoryError, match="snapshot_changed"):
        discover_candidate_proof_receipts(connection, limit=8)


def test_lineage_or_bridge_append_during_read_cannot_yield_receipt() -> None:
    selected = _selected_projection()
    binding = _binding(selected)
    proof = _bound_ready_packet(selected, binding)

    lineage_connection = _Connection(selected)
    artifact_hash = selected["artifact"]["artifact_hash"]
    lineage_connection.recheck_lineage_rows = copy.deepcopy(
        lineage_connection.lineage_by_artifact[artifact_hash]
    )
    extra = copy.deepcopy(lineage_connection.recheck_lineage_rows[0])
    extra["edge_hash"] = "f" * 64
    lineage_connection.recheck_lineage_rows.append(extra)
    with pytest.raises(CandidateProofRepositoryError, match="lineage|snapshot"):
        discover_candidate_proof_receipts(lineage_connection, limit=8)

    bridge_connection = _Connection(
        selected,
        bridge_rows=[_bridge_row(proof, [])],
    )
    bridge_connection.recheck_bridge_rows = [
        *copy.deepcopy(bridge_connection.bridge_rows),
        _bridge_row(proof, [], salt="c"),
    ]
    with pytest.raises(CandidateProofRepositoryError, match="snapshot_changed"):
        discover_candidate_proof_receipts(bridge_connection, limit=8)


@pytest.mark.parametrize("mutation", ("missing", "extra", "edge", "ambiguous"))
def test_missing_extra_drifted_or_ambiguous_lineage_fails_closed(
    mutation: str,
) -> None:
    projection = _selected_projection()
    connection = _Connection(projection)
    artifact_hash = projection["artifact"]["artifact_hash"]
    rows = connection.lineage_by_artifact[artifact_hash]
    if mutation == "missing":
        rows.pop()
    elif mutation == "extra":
        extra = copy.deepcopy(rows[0])
        extra["edge_hash"] = "f" * 64
        rows.append(extra)
    elif mutation == "edge":
        rows[0]["edge_role"] = "candidate_outcome_bridge"
    else:
        rows.append(copy.deepcopy(rows[0]))

    with pytest.raises(CandidateProofRepositoryError, match="lineage"):
        discover_candidate_proof_receipts(connection, limit=8)


def test_source_key_whitespace_drift_is_not_normalized() -> None:
    projection = _selected_projection()
    connection = _Connection(projection)
    artifact_hash = projection["artifact"]["artifact_hash"]
    connection.lineage_by_artifact[artifact_hash][0]["source_key"] = (
        " " + connection.lineage_by_artifact[artifact_hash][0]["source_key"]
    )

    with pytest.raises(CandidateProofRepositoryError, match="source_key"):
        discover_candidate_proof_receipts(connection, limit=8)


def test_lineage_is_bounded_initially_and_in_snapshot_recheck() -> None:
    projection = _selected_projection()
    artifact_hash = projection["artifact"]["artifact_hash"]

    initial = _Connection(projection)
    initial.lineage_by_artifact[artifact_hash] = [
        copy.deepcopy(initial.lineage_by_artifact[artifact_hash][0])
        for _ in range(65)
    ]
    with pytest.raises(
        CandidateProofRepositoryError,
        match="lineage_schema_required_overflow",
    ):
        discover_candidate_proof_receipts(initial, limit=8)
    lineage_call = next(
        (sql, params)
        for sql, params in initial.calls
        if "candidate-proof:projection-lineage" in sql
    )
    assert "LIMIT %s" in lineage_call[0]
    assert lineage_call[1][-1] == 65

    recheck = _Connection(projection)
    recheck.recheck_lineage_rows = [
        copy.deepcopy(recheck.lineage_by_artifact[artifact_hash][0])
        for _ in range(65)
    ]
    with pytest.raises(
        CandidateProofRepositoryError,
        match="lineage_schema_required_overflow",
    ):
        discover_candidate_proof_receipts(recheck, limit=8)
    snapshot_call = next(
        (sql, params)
        for sql, params in recheck.calls
        if "candidate-proof:snapshot-recheck" in sql
    )
    assert "lineage_window" in snapshot_call[0]
    assert 65 in snapshot_call[1]


def test_tampered_claimed_bridge_cannot_become_positive_receipt() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    bridge = _bridge_row(proof, [])
    bridge["canonical_payload"]["run_hash"] = "f" * 64

    with pytest.raises(CandidateProofRepositoryError, match="bridge_artifact_hash"):
        discover_candidate_proof_receipts(
            _Connection(projection, bridge_rows=[bridge]),
            limit=8,
        )


def test_rehashed_bridge_authority_injection_fails_closed() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    row = _bridge_row(proof, [])
    bridge = row["canonical_payload"]["bridge"]
    bridge["order_authority_granted"] = True
    bridge["bridge_hash"] = compute_alr_outcome_bridge_hash(bridge)
    row["artifact_hash"] = _sha(row["canonical_payload"])

    with pytest.raises(CandidateProofRepositoryError, match="authority_boundary"):
        discover_candidate_proof_receipts(
            _Connection(projection, bridge_rows=[row]),
            limit=8,
        )


def test_wrong_schema_claimed_bridge_is_explicitly_rejected_not_pending() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    row = _bridge_row(proof, [])
    row["canonical_payload"]["schema_version"] = "unsupported_bridge_v999"
    row["artifact_hash"] = _sha(row["canonical_payload"])

    with pytest.raises(CandidateProofRepositoryError, match="schema"):
        discover_candidate_proof_receipts(
            _Connection(projection, bridge_rows=[row]),
            limit=8,
        )


def test_bounded_overflow_is_explicit_schema_required_not_false_progress() -> None:
    projection = _selected_projection()
    binding = _binding(projection)
    proof = _bound_ready_packet(projection, binding)
    rows = [_bridge_row(proof, [], salt=character) for character in ("a", "b", "c")]

    batch = discover_candidate_proof_receipts(
        _Connection(projection, bridge_rows=rows),
        limit=2,
    )

    assert batch["status"] == "SCHEMA_REQUIRED_OVERFLOW"
    assert batch["receipts"] == []
    assert batch["metrics"]["outcome_bridge_rows_scanned"] == 3
    assert batch["metrics"]["rows_written"] == 0


def test_public_api_exposes_no_caller_substitution_inputs() -> None:
    signature = inspect.signature(discover_candidate_proof_receipts)
    assert list(signature.parameters) == ["connection", "limit"]
    projection = _selected_projection()
    with pytest.raises(TypeError):
        discover_candidate_proof_receipts(  # type: ignore[call-arg]
            _Connection(projection),
            limit=8,
            projection=projection,
        )

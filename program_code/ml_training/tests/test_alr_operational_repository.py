from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

import ml_training.alr_scanner_statistical_experiment as experiment_module
from ml_training.alr_operational_repository import (
    AlrOperationalConflict,
    build_statistical_run_plan,
    fetch_untrained_scanner_cycles,
    persist_statistical_run,
)
from ml_training.alr_scanner_statistical_experiment import (
    build_scanner_statistical_experiment,
)


def _result(
    *,
    source_head: str = "a" * 40,
    source_offset: int = 0,
    date: str = "2026-07-09",
    extra_novelty: bool = False,
) -> dict[str, Any]:
    cycles = []
    for ordinal in range(1, 5):
        identity = ordinal + source_offset
        cycles.append(
            {
                "source_hash": f"{identity:064x}",
                "source_key": f"scan-{identity}|{date}T12:0{ordinal}:00Z",
                "source_ts": f"{date}T12:0{ordinal}:00Z",
                "canonical_payload": {
                    "ts": f"{date}T12:0{ordinal}:00Z",
                    "scan_id": f"scan-{identity}",
                    "active_symbols": ["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"],
                    "added": ["ALPHAUSDT"]
                    if ordinal == 1 or (extra_novelty and ordinal == 2)
                    else [],
                    "removed": [],
                    "rejected_count": 0,
                    "scan_duration_ms": 5,
                    "candidates": [
                        {"symbol": symbol, "final_score": ordinal}
                        for symbol in ("ALPHAUSDT", "BETAUSDT", "GAMMAUSDT")
                    ],
                    "config": {"scanner_revision": "v1"},
                },
            }
        )
    return build_scanner_statistical_experiment(source_head=source_head, cycles=cycles)


def test_builds_append_only_deferred_statistical_run_plan() -> None:
    plan = build_statistical_run_plan(_result())

    assert plan["run_kind"] == "scanner_novelty_statistical_baseline"
    assert plan["run_status"] == "DEFER_EVIDENCE"
    assert plan["source_count"] == 4
    assert len(plan["artifacts"]) == 5
    assert len(plan["edges"]) == 8
    assert all(value is False for value in plan["no_authority"].values())
    assert all(value == 0 for value in plan["authority_counters"].values())


class _LedgerConnection:
    def __init__(self) -> None:
        self.runs: dict[str, str] = {}
        self.artifacts: dict[str, str] = {}
        self.artifact_payloads: dict[str, dict[str, Any]] = {}
        self.run_records: list[dict[str, str]] = []
        self.edges: set[str] = set()
        self.untrained_rows: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0
        self.fail_on_suppression_edge_number: int | None = None
        self.suppression_edge_attempts = 0
        self._transaction_snapshot: dict[str, Any] | None = None

    def cursor(self) -> "_LedgerCursor":
        return _LedgerCursor(self)

    def commit(self) -> None:
        self.commits += 1
        self._transaction_snapshot = None

    def rollback(self) -> None:
        self.rollbacks += 1
        if self._transaction_snapshot is not None:
            self.runs = self._transaction_snapshot["runs"]
            self.artifacts = self._transaction_snapshot["artifacts"]
            self.artifact_payloads = self._transaction_snapshot["artifact_payloads"]
            self.run_records = self._transaction_snapshot["run_records"]
            self.edges = self._transaction_snapshot["edges"]
            self._transaction_snapshot = None

    def begin_for_test(self) -> None:
        if self._transaction_snapshot is None:
            self._transaction_snapshot = {
                "runs": copy.deepcopy(self.runs),
                "artifacts": copy.deepcopy(self.artifacts),
                "artifact_payloads": copy.deepcopy(self.artifact_payloads),
                "run_records": copy.deepcopy(self.run_records),
                "edges": copy.deepcopy(self.edges),
            }


class _LedgerCursor:
    def __init__(self, connection: _LedgerConnection) -> None:
        self.connection = connection
        self.row: Any = None

    def __enter__(self) -> "_LedgerCursor":
        self.connection.begin_for_test()
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        if "SELECT count(*) FROM learning.alr_provenance_edges" in sql:
            self.row = (
                sum(edge_hash in self.connection.edges for edge_hash in params[0]),
            )
        elif "SELECT canonical_payload FROM learning.alr_artifact_nodes" in sql:
            payload = self.connection.artifact_payloads.get(str(params[0]))
            self.row = None if payload is None else {"canonical_payload": payload}
        elif "candidate.canonical_payload AS candidate_payload" in sql:
            self.row = None
            for run in reversed(self.connection.run_records):
                candidate = self.connection.artifact_payloads[
                    run["candidate_artifact_hash"]
                ]
                if (
                    params[0] == "scanner_novelty_statistical_baseline"
                    and candidate.get("decision_fingerprint") == params[2]
                    and candidate.get("decision_policy_hash") == params[3]
                    and candidate.get("decision_fingerprint_components", {}).get(
                        "source_head"
                    )
                    == params[1]
                ):
                    self.row = {
                        **run,
                        "candidate_payload": candidate,
                        "defer_payload": self.connection.artifact_payloads[
                            run["defer_artifact_hash"]
                        ],
                    }
                    break
        elif "SELECT run_hash FROM learning.alr_training_runs" in sql:
            self.row = self.connection.runs.get(str(params[0]))
            if self.row is not None:
                self.row = (self.row,)
        elif "FROM learning.alr_source_events AS source" in sql:
            self.row = self.connection.untrained_rows
        elif "INSERT INTO learning.alr_artifact_nodes" in sql:
            artifact_hash = str(params[0])
            if artifact_hash in self.connection.artifacts:
                self.row = None
            else:
                self.connection.artifacts[artifact_hash] = str(params[1])
                self.connection.artifact_payloads[artifact_hash] = json.loads(
                    str(params[2])
                )
                self.row = (artifact_hash,)
        elif "INSERT INTO learning.alr_provenance_edges" in sql:
            target_kind = self.connection.artifacts.get(str(params[2]))
            if target_kind == "target_rotation":
                self.connection.suppression_edge_attempts += 1
                if (
                    self.connection.fail_on_suppression_edge_number
                    == self.connection.suppression_edge_attempts
                ):
                    raise RuntimeError("injected_suppression_edge_failure")
            edge_hash = str(params[0])
            if edge_hash in self.connection.edges:
                self.row = None
            else:
                self.connection.edges.add(edge_hash)
                self.row = (edge_hash,)
        elif "INSERT INTO learning.alr_training_runs" in sql:
            source_set_hash = str(params[1])
            run_hash = str(params[0])
            existing = self.connection.runs.setdefault(source_set_hash, run_hash)
            self.row = (run_hash,) if existing == run_hash else None
            if existing == run_hash and not any(
                item["run_hash"] == run_hash
                for item in self.connection.run_records
            ):
                self.connection.run_records.append(
                    {
                        "run_hash": run_hash,
                        "candidate_artifact_hash": str(params[9]),
                        "defer_artifact_hash": str(params[10]),
                    }
                )

    def fetchone(self) -> Any:
        return self.row

    def fetchall(self) -> Any:
        return self.row


def test_persists_one_run_then_normalizes_replay_to_duplicate() -> None:
    connection = _LedgerConnection()
    result = _result()

    first = persist_statistical_run(connection, result)
    second = persist_statistical_run(connection, result)

    assert first["status"] == "PERSISTED"
    assert second["status"] == "DUPLICATE"
    assert len(connection.runs) == 1
    assert len(connection.artifacts) == 5
    assert len(connection.edges) == 8
    assert connection.commits == 2
    assert not any(
        token in sql.upper()
        for sql, _ in connection.calls
        for token in ("UPDATE ", "DELETE ")
    )


def test_write_metrics_count_only_rows_inserted_after_artifact_dedup() -> None:
    connection = _LedgerConnection()
    result = _result()
    preexisting = result["artifacts"][0]
    connection.artifacts[preexisting["artifact_hash"]] = preexisting[
        "artifact_kind"
    ]
    connection.artifact_payloads[preexisting["artifact_hash"]] = copy.deepcopy(
        preexisting["canonical_payload"]
    )

    persisted = persist_statistical_run(connection, result)

    assert persisted["status"] == "PERSISTED"
    assert persisted["artifact_rows_written"] == 4
    assert persisted["provenance_rows_written"] == 8
    assert persisted["run_rows_written"] == 1
    assert persisted["defer_artifact_rows_written"] == 1
    assert persisted["payload_bytes_written"] == sum(
        len(
            json.dumps(
                artifact["canonical_payload"],
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        )
        for artifact in result["artifacts"][1:]
    )


def test_equivalent_defer_emits_one_suppression_artifact_without_another_run() -> None:
    connection = _LedgerConnection()
    first = persist_statistical_run(connection, _result())
    equivalent = persist_statistical_run(
        connection,
        _result(source_offset=10),
    )

    assert first["status"] == "PERSISTED"
    assert equivalent["status"] == "SUPPRESSED_EQUIVALENT_DEFER"
    assert equivalent["decision_writes_suppressed"] == 1
    assert equivalent["source_rows_consumed"] == 4
    assert equivalent["artifact_rows_written"] == 1
    assert equivalent["run_rows_written"] == 0
    assert equivalent["feedback_rows_written"] == 0
    assert equivalent["defer_artifact_rows_written"] == 0
    assert len(connection.runs) == 1
    assert list(connection.artifacts.values()).count("target_rotation") == 1
    assert list(connection.artifacts.values()).count("candidate_artifact") == 1
    assert list(connection.artifacts.values()).count("defer_evidence") == 1
    suppression = connection.artifact_payloads[
        equivalent["suppression_artifact_hash"]
    ]
    assert suppression["run_created"] is False
    assert suppression["feedback_created"] is False
    assert suppression["defer_artifact_created"] is False
    assert len(suppression["source_identities"]) == 4
    assert len(suppression["reused_decision_refs"]) == 3
    assert all(value is False for value in suppression["no_authority"].values())
    assert all(value == 0 for value in suppression["authority_counters"].values())


def test_equivalent_defer_from_a_different_source_head_is_reevaluated() -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result(source_head="a" * 40))

    different_head = persist_statistical_run(
        connection,
        _result(source_head="b" * 40, source_offset=10),
    )

    assert different_head["status"] == "PERSISTED"
    assert len(connection.runs) == 2
    assert list(connection.artifacts.values()).count("target_rotation") == 0


def test_equivalent_defer_suppression_retry_is_idempotent() -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result())
    equivalent = _result(source_offset=10)

    first = persist_statistical_run(connection, equivalent)
    retry = persist_statistical_run(connection, equivalent)

    assert first["status"] == "SUPPRESSED_EQUIVALENT_DEFER"
    assert retry["status"] == "DUPLICATE_SUPPRESSION"
    assert retry["duplicate_retries"] == 1
    assert retry["artifact_rows_written"] == 0
    assert retry["provenance_rows_written"] == 0
    assert list(connection.artifacts.values()).count("target_rotation") == 1


def test_suppression_retry_fails_closed_if_lineage_is_incomplete() -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result())
    equivalent = _result(source_offset=10)
    first = persist_statistical_run(connection, equivalent)
    suppression_hash = first["suppression_artifact_hash"]
    suppression_edges = [
        edge_hash
        for edge_hash in connection.edges
        if any(
            call_params is not None
            and len(call_params) >= 3
            and call_params[0] == edge_hash
            and call_params[2] == suppression_hash
            for _, call_params in connection.calls
        )
    ]
    connection.edges.remove(suppression_edges[0])

    with pytest.raises(
        AlrOperationalConflict,
        match="suppression_artifact_lineage_incomplete",
    ):
        persist_statistical_run(connection, equivalent)

    assert connection.rollbacks == 1


def test_equivalent_defer_is_reevaluated_after_bounded_ttl() -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result())

    after_ttl = persist_statistical_run(
        connection,
        _result(source_offset=10, date="2026-07-10"),
    )

    assert after_ttl["status"] == "PERSISTED"
    assert after_ttl["decision_writes_suppressed"] == 0
    assert len(connection.runs) == 2
    assert list(connection.artifacts.values()).count("target_rotation") == 0


def test_semantic_evidence_delta_forces_normal_reevaluation() -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result())

    changed = persist_statistical_run(
        connection,
        _result(source_offset=10, extra_novelty=True),
    )

    assert changed["status"] == "PERSISTED"
    assert changed["decision_writes_suppressed"] == 0
    assert len(connection.runs) == 2


def test_rejects_source_set_as_of_that_is_not_latest_source_identity() -> None:
    result = _result()
    result["source_set"]["as_of_ts"] = "2026-07-09T12:03:00Z"
    result["experiment_hash"] = (
        experiment_module.compute_scanner_statistical_experiment_hash(result)
    )

    with pytest.raises(
        ValueError,
        match="source_set_as_of_mismatch",
    ):
        build_statistical_run_plan(result)


def test_rejects_candidate_evaluation_time_not_bound_to_source_set() -> None:
    result = _result()
    candidate = next(
        artifact
        for artifact in result["artifacts"]
        if artifact["artifact_kind"] == "candidate_artifact"
    )
    old_candidate_hash = candidate["artifact_hash"]
    candidate["canonical_payload"]["evaluated_at"] = "2026-07-09T12:03:59Z"
    new_candidate_hash = experiment_module._canonical_sha256(
        candidate["canonical_payload"]
    )
    candidate["artifact_hash"] = new_candidate_hash
    result["run"]["candidate_artifact_hash"] = new_candidate_hash
    result["run"]["run_hash"] = experiment_module._canonical_sha256(
        {
            key: value
            for key, value in result["run"].items()
            if key != "run_hash"
        }
    )
    for edge in result["provenance_edges"]:
        if edge["to_artifact_hash"] == old_candidate_hash:
            edge["to_artifact_hash"] = new_candidate_hash
        if edge["from_artifact_hash"] == old_candidate_hash:
            edge["from_artifact_hash"] = new_candidate_hash
        edge["edge_hash"] = experiment_module._canonical_sha256(
            {
                "from_artifact_hash": edge["from_artifact_hash"],
                "to_artifact_hash": edge["to_artifact_hash"],
                "edge_role": edge["edge_role"],
            }
        )
    result["experiment_hash"] = (
        experiment_module.compute_scanner_statistical_experiment_hash(result)
    )

    with pytest.raises(
        ValueError,
        match="candidate_evaluated_at_mismatch",
    ):
        build_statistical_run_plan(result)


@pytest.mark.parametrize(
    ("artifact_kind", "field", "value", "reason"),
    (
        (
            "candidate_artifact",
            "next_evaluation_due_at",
            "2026-07-09T12:34:01Z",
            "candidate_next_evaluation_due_at_mismatch",
        ),
        (
            "defer_evidence",
            "evaluated_at",
            "2026-07-09T12:03:59Z",
            "defer_evaluated_at_mismatch",
        ),
        (
            "defer_evidence",
            "next_evaluation_due_at",
            "2026-07-09T12:34:01Z",
            "defer_next_evaluation_due_at_mismatch",
        ),
    ),
)
def test_rejects_decision_timestamps_outside_source_bound_ttl(
    artifact_kind: str,
    field: str,
    value: str,
    reason: str,
) -> None:
    result = _result()
    artifact = next(
        item
        for item in result["artifacts"]
        if item["artifact_kind"] == artifact_kind
    )
    old_hash = artifact["artifact_hash"]
    artifact["canonical_payload"][field] = value
    new_hash = experiment_module._canonical_sha256(
        artifact["canonical_payload"]
    )
    artifact["artifact_hash"] = new_hash
    run_field = (
        "candidate_artifact_hash"
        if artifact_kind == "candidate_artifact"
        else "defer_artifact_hash"
    )
    result["run"][run_field] = new_hash
    result["run"]["run_hash"] = experiment_module._canonical_sha256(
        {
            key: item
            for key, item in result["run"].items()
            if key != "run_hash"
        }
    )
    for edge in result["provenance_edges"]:
        if edge["to_artifact_hash"] == old_hash:
            edge["to_artifact_hash"] = new_hash
        if edge["from_artifact_hash"] == old_hash:
            edge["from_artifact_hash"] = new_hash
        edge["edge_hash"] = experiment_module._canonical_sha256(
            {
                "from_artifact_hash": edge["from_artifact_hash"],
                "to_artifact_hash": edge["to_artifact_hash"],
                "edge_role": edge["edge_role"],
            }
        )
    result["experiment_hash"] = (
        experiment_module.compute_scanner_statistical_experiment_hash(result)
    )

    with pytest.raises(ValueError, match=reason):
        build_statistical_run_plan(result)


def test_decision_policy_delta_forces_normal_reevaluation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result())
    changed_policy = {
        **experiment_module._DEFER_DECISION_POLICY,
        "schema_version": "alr_defer_decision_policy_v2_test",
    }
    monkeypatch.setattr(
        experiment_module,
        "_DEFER_DECISION_POLICY",
        changed_policy,
    )

    changed = persist_statistical_run(
        connection,
        _result(source_offset=10),
    )

    assert changed["status"] == "PERSISTED"
    assert changed["decision_writes_suppressed"] == 0
    assert len(connection.runs) == 2


def test_suppression_artifact_and_source_edges_rollback_atomically() -> None:
    connection = _LedgerConnection()
    persist_statistical_run(connection, _result())
    baseline_artifacts = copy.deepcopy(connection.artifacts)
    baseline_edges = copy.deepcopy(connection.edges)
    connection.fail_on_suppression_edge_number = 2

    with pytest.raises(RuntimeError, match="injected_suppression_edge_failure"):
        persist_statistical_run(connection, _result(source_offset=10))

    assert connection.artifacts == baseline_artifacts
    assert connection.edges == baseline_edges
    assert len(connection.runs) == 1
    assert connection.rollbacks == 1


def test_rejects_same_source_set_with_a_different_run() -> None:
    connection = _LedgerConnection()
    result = _result()
    persist_statistical_run(connection, result)
    conflicting = _result(source_head="b" * 40)

    with pytest.raises(AlrOperationalConflict, match="source_set_run_conflict"):
        persist_statistical_run(connection, conflicting)

    assert connection.rollbacks == 1


def test_reads_only_bounded_untrained_alr_scanner_cycles() -> None:
    connection = _LedgerConnection()
    connection.untrained_rows = [
        {
            "source_hash": "1" * 64,
            "source_key": "scan-1|2026-07-09T12:00:00Z",
            "source_ts": "2026-07-09T12:00:00Z",
            "canonical_payload": {"scan_id": "scan-1"},
        }
    ]

    rows = fetch_untrained_scanner_cycles(connection, limit=4)

    assert rows == connection.untrained_rows
    query, params = connection.calls[-1]
    assert "training_input" in query
    assert params == ("trading.scanner_snapshots", 4)
    assert "UPDATE" not in query.upper()
    assert "DELETE" not in query.upper()


def test_normalizes_postgresql_timestamptz_to_canonical_utc_z() -> None:
    connection = _LedgerConnection()
    connection.untrained_rows = [
        {
            "source_hash": "1" * 64,
            "source_key": "scan-1|2026-07-09T12:00:00Z",
            "source_ts": datetime(2026, 7, 9, 14, 0, tzinfo=timezone.utc),
            "canonical_payload": {"scan_id": "scan-1"},
        }
    ]

    rows = fetch_untrained_scanner_cycles(connection, limit=4)

    assert rows[0]["source_ts"] == "2026-07-09T14:00:00Z"


def test_v152_expands_only_alr_owned_artifacts_and_run_ledger() -> None:
    migration = (
        Path(__file__).parents[3]
        / "sql/migrations/V152__alr_operational_artifacts.sql"
    )
    source = migration.read_text(encoding="utf-8")

    assert "learning.alr_training_runs" in source
    assert "alr_artifact_nodes_kind_check" in source
    assert "statistical_experiment" in source
    assert "DEFER_EVIDENCE" in source
    assert "DROP TABLE" not in source
    assert "ALTER TABLE trading." not in source

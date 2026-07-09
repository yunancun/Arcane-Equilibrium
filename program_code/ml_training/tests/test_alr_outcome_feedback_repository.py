from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ml_training.alr_outcome_feedback import build_outcome_feedback
from ml_training.alr_outcome_feedback_repository import (
    AlrOutcomeFeedbackConflict,
    build_feedback_persistence_plan,
    fetch_unreviewed_outcome_runs,
    persist_outcome_feedback,
)
from ml_training.alr_scanner_statistical_experiment import (
    build_scanner_statistical_experiment,
)


def _feedback(*, proof_packet: dict[str, Any] | None = None) -> dict[str, Any]:
    cycles = []
    for ordinal in range(1, 5):
        cycles.append(
            {
                "source_hash": f"{ordinal:064x}",
                "source_key": f"scan-{ordinal}|2026-07-09T12:0{ordinal}:00Z",
                "source_ts": f"2026-07-09T12:0{ordinal}:00Z",
                "canonical_payload": {
                    "candidates": [
                        {"symbol": symbol, "final_score": ordinal}
                        for symbol in ("ALPHAUSDT", "BETAUSDT", "GAMMAUSDT")
                    ],
                    "added": ["ALPHAUSDT"] if ordinal == 1 else [],
                },
            }
        )
    experiment = build_scanner_statistical_experiment(source_head="a" * 40, cycles=cycles)
    return build_outcome_feedback(
        run=experiment["run"],
        candidate_artifact=experiment["candidate_artifact"],
        proof_packet=proof_packet,
    )


def test_builds_deferred_feedback_persistence_plan() -> None:
    plan = build_feedback_persistence_plan(_feedback())

    assert plan["feedback_status"] == "DEFER_EVIDENCE"
    assert plan["bridge_outcome"] == "DEFER_EVIDENCE"
    assert plan["proof_packet_present"] is False
    assert plan["reward_record_count"] == 0
    assert plan["rotate_next_target"] is True
    assert len(plan["artifacts"]) == 3
    assert len(plan["edges"]) == 3


class _Connection:
    def __init__(self) -> None:
        self.feedback_by_run: dict[str, str] = {}
        self.artifacts: dict[str, str] = {}
        self.edges: set[str] = set()
        self.unreviewed_rows: list[dict[str, Any]] = []
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
        self.row: Any = None

    def __enter__(self) -> "_Cursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        if "SELECT feedback_artifact_hash FROM learning.alr_outcome_feedback_events" in sql:
            value = self.connection.feedback_by_run.get(str(params[0]))
            self.row = None if value is None else (value,)
        elif "FROM learning.alr_training_runs AS run" in sql:
            self.row = self.connection.unreviewed_rows
        elif "INSERT INTO learning.alr_artifact_nodes" in sql:
            self.connection.artifacts[str(params[0])] = str(params[1])
            self.row = None
        elif "INSERT INTO learning.alr_provenance_edges" in sql:
            self.connection.edges.add(str(params[0]))
            self.row = None
        elif "INSERT INTO learning.alr_outcome_feedback_events" in sql:
            feedback_hash = str(params[0])
            run_hash = str(params[1])
            existing = self.connection.feedback_by_run.setdefault(run_hash, feedback_hash)
            self.row = (feedback_hash,) if existing == feedback_hash else None

    def fetchone(self) -> Any:
        return self.row

    def fetchall(self) -> Any:
        return self.row


def test_persists_feedback_once_and_replay_is_duplicate() -> None:
    connection = _Connection()
    feedback = _feedback()

    first = persist_outcome_feedback(connection, feedback)
    second = persist_outcome_feedback(connection, feedback)

    assert first["status"] == "PERSISTED"
    assert second["status"] == "DUPLICATE"
    assert len(connection.feedback_by_run) == 1
    assert len(connection.artifacts) == 3
    assert len(connection.edges) == 3
    assert not any(
        token in sql.upper()
        for sql, _ in connection.calls
        for token in ("UPDATE ", "DELETE ")
    )


def test_rejects_second_feedback_with_a_different_hash_for_same_run() -> None:
    connection = _Connection()
    first = _feedback()
    persist_outcome_feedback(connection, first)
    conflicting = _feedback(proof_packet={"schema_version": "unknown"})

    with pytest.raises(AlrOutcomeFeedbackConflict, match="run_feedback_conflict"):
        persist_outcome_feedback(connection, conflicting)

    assert connection.rollbacks == 1


def test_reads_only_bounded_runs_without_feedback() -> None:
    connection = _Connection()
    connection.unreviewed_rows = [
        {
            "run_hash": "a" * 64,
            "candidate_artifact_hash": "b" * 64,
            "candidate_artifact": {"candidate_scope": {}},
        }
    ]

    rows = fetch_unreviewed_outcome_runs(connection, limit=4)

    assert rows == connection.unreviewed_rows
    query, params = connection.calls[-1]
    assert "learning.alr_outcome_feedback_events" in query
    assert params == (4,)
    assert "UPDATE" not in query.upper()
    assert "DELETE" not in query.upper()


def test_v153_is_append_only_and_rejects_non_alr_schema_changes() -> None:
    migration = (
        Path(__file__).parents[3]
        / "sql/migrations/V153__alr_outcome_feedback.sql"
    )
    source = migration.read_text(encoding="utf-8")

    assert "learning.alr_outcome_feedback_events" in source
    assert "outcome_feedback" in source
    assert "target_rotation" in source
    assert "DROP TABLE" not in source
    assert "ALTER TABLE trading." not in source

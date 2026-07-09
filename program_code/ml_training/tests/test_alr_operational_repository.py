from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ml_training.alr_operational_repository import (
    AlrOperationalConflict,
    build_statistical_run_plan,
    fetch_untrained_scanner_cycles,
    persist_statistical_run,
)
from ml_training.alr_scanner_statistical_experiment import (
    build_scanner_statistical_experiment,
)


def _result(*, source_head: str = "a" * 40) -> dict[str, Any]:
    cycles = []
    for ordinal in range(1, 5):
        cycles.append(
            {
                "source_hash": f"{ordinal:064x}",
                "source_key": f"scan-{ordinal}|2026-07-09T12:0{ordinal}:00Z",
                "source_ts": f"2026-07-09T12:0{ordinal}:00Z",
                "canonical_payload": {
                    "ts": f"2026-07-09T12:0{ordinal}:00Z",
                    "scan_id": f"scan-{ordinal}",
                    "active_symbols": ["ALPHAUSDT", "BETAUSDT", "GAMMAUSDT"],
                    "added": ["ALPHAUSDT"] if ordinal == 1 else [],
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
        self.edges: set[str] = set()
        self.untrained_rows: list[dict[str, Any]] = []
        self.calls: list[tuple[str, tuple[Any, ...] | None]] = []
        self.commits = 0
        self.rollbacks = 0

    def cursor(self) -> "_LedgerCursor":
        return _LedgerCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


class _LedgerCursor:
    def __init__(self, connection: _LedgerConnection) -> None:
        self.connection = connection
        self.row: Any = None

    def __enter__(self) -> "_LedgerCursor":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        self.connection.calls.append((sql, params))
        if "SELECT run_hash FROM learning.alr_training_runs" in sql:
            self.row = self.connection.runs.get(str(params[0]))
            if self.row is not None:
                self.row = (self.row,)
        elif "FROM learning.alr_source_events AS source" in sql:
            self.row = self.connection.untrained_rows
        elif "INSERT INTO learning.alr_artifact_nodes" in sql:
            self.connection.artifacts[str(params[0])] = str(params[1])
            self.row = None
        elif "INSERT INTO learning.alr_provenance_edges" in sql:
            self.connection.edges.add(str(params[0]))
            self.row = None
        elif "INSERT INTO learning.alr_training_runs" in sql:
            source_set_hash = str(params[1])
            run_hash = str(params[0])
            existing = self.connection.runs.setdefault(source_set_hash, run_hash)
            self.row = (run_hash,) if existing == run_hash else None

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

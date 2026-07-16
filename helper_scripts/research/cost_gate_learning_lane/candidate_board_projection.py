"""Disk-backed full-universe projection for candidate-board construction.

This storage adapter owns the one-scan SQLite reduction and projected-board
builder.  It deliberately does not import ``outcome_review``; statistical
methodology enters through the same injected cohort-evaluator Interface used by
the list-backed candidate-board builder.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import datetime as dt
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sqlite3
from typing import Any

from cost_gate_learning_lane import candidate_board as candidate_board_module
from cost_gate_learning_lane.candidate_board import (
    LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION,
)
from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
from cost_gate_learning_lane.ledger_streaming import scan_retained_jsonl
from cost_gate_learning_lane.runtime_adapter import project_candidate_evidence_rows


class CandidateBoardQualifiedCohortMaterializationError(ValueError):
    """One exact qualified cohort cannot be materialized inside its hard cap."""


def _duplicate_outcome_semantic_projection(
    item: dict[str, Any],
) -> dict[str, Any]:
    row = item["row"]
    fields = (
        *candidate_board_module._DUPLICATE_EXACT_FIELDS,
        *candidate_board_module._DUPLICATE_BPS_FIELDS,
    )
    return {
        "fields": {
            key: (
                {"present": True, "value": row[key]}
                if key in row
                else {"present": False}
            )
            for key in fields
        }
    }


class CandidateBoardSqliteProjection:
    """Temporary SQLite-backed exact candidate-board universe."""

    def __init__(
        self,
        *,
        max_qualified_cohort_rows: int,
        max_qualified_cohort_bytes: int,
    ) -> None:
        if max_qualified_cohort_rows < 0 or max_qualified_cohort_bytes < 0:
            raise ValueError("candidate-board projection limits must be non-negative")
        self.max_qualified_cohort_rows = max_qualified_cohort_rows
        self.max_qualified_cohort_bytes = max_qualified_cohort_bytes
        self._db = sqlite3.connect("")
        self._db.execute("PRAGMA temp_store=FILE")
        self._db.execute("PRAGMA journal_mode=OFF")
        self._db.execute("PRAGMA synchronous=OFF")
        self._db.execute(
            """
            CREATE TABLE lineage_rows (
                row_id INTEGER PRIMARY KEY,
                partition_name TEXT NOT NULL,
                reason TEXT NOT NULL,
                event_hash TEXT,
                stable_cohort_hash TEXT,
                candidate_family_key TEXT,
                raw_event_date TEXT,
                current_exact_seed INTEGER NOT NULL,
                row_json TEXT,
                evaluation_json TEXT,
                stable_projection_json TEXT,
                outcome_semantics_json TEXT,
                evaluation_semantics_json TEXT,
                representative_sha256 TEXT,
                source_sort_key TEXT
            )
            """
        )
        self.raw_blocked_outcome_row_count = 0
        self.qualified_lineage_outcome_row_count = 0
        self.unqualified_lineage_outcome_row_count = 0
        self.invalid_lineage_outcome_row_count = 0
        self.invalid_exact_cohort_row_count = 0
        self.invalid_identity_family_row_count = 0
        self.unassigned_invalid_lineage_outcome_row_count = 0
        self.lineage_exclusion_reason_counts: dict[str, int] = {}
        self._cohort_sources: dict[str, dict[str, Any]] = {}
        self._finalized = False
        self._closed = False

    def __len__(self) -> int:
        return self.raw_blocked_outcome_row_count

    @property
    def closed(self) -> bool:
        return self._closed

    def __enter__(self) -> CandidateBoardSqliteProjection:
        if self._closed:
            raise RuntimeError("candidate-board projection is closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if not self._closed:
            self._db.close()
            self._closed = True

    def add_blocked_row(self, row: dict[str, Any]) -> None:
        if self._finalized or self._closed:
            raise RuntimeError("candidate-board projection is not writable")
        item = candidate_board_module._classify_lineage(row)
        if (
            item["partition"] == "QUALIFIED"
            and not candidate_board_module._candidate_source_contract_valid(item)
        ):
            item = {
                **item,
                "partition": "INVALID",
                "reason": "INVALID_LINEAGE_EXACT_COHORT",
            }
        partition = item["partition"]
        reason = item["reason"]
        self.raw_blocked_outcome_row_count += 1
        if partition == "QUALIFIED":
            self.qualified_lineage_outcome_row_count += 1
        elif partition == "UNQUALIFIED":
            self.unqualified_lineage_outcome_row_count += 1
        else:
            self.invalid_lineage_outcome_row_count += 1
            if reason == "INVALID_LINEAGE_EXACT_COHORT":
                self.invalid_exact_cohort_row_count += 1
            elif reason == "INVALID_LINEAGE_IDENTITY_FAMILY":
                self.invalid_identity_family_row_count += 1
            else:
                self.unassigned_invalid_lineage_outcome_row_count += 1
        if partition != "QUALIFIED":
            self.lineage_exclusion_reason_counts[reason] = (
                self.lineage_exclusion_reason_counts.get(reason, 0) + 1
            )

        current_exact_seed = bool(
            partition == "INVALID"
            and reason == "INVALID_LINEAGE_EXACT_COHORT"
            and candidate_board_module._candidate_source_contract_valid(item)
        )
        full_seed = partition == "QUALIFIED" or current_exact_seed
        event_hash = item.get("event_hash")
        family_key = item.get("candidate_family_key")
        raw_event_date = item.get("raw_event_date")
        raw_event_date_text = (
            raw_event_date.isoformat()
            if isinstance(raw_event_date, dt.date)
            else None
        )
        compact_addressable = bool(
            family_key
            and raw_event_date_text
            and (
                reason == "INVALID_LINEAGE_IDENTITY_FAMILY"
                or (
                    event_hash
                    and (
                        partition == "UNQUALIFIED"
                        or (
                            reason == "INVALID_LINEAGE_EXACT_COHORT"
                            and not current_exact_seed
                        )
                    )
                )
            )
        )
        if not full_seed and not compact_addressable:
            return

        evaluation = item.get("evaluation")
        stable_projection = item.get("stable_projection")
        outcome_semantics = (
            _duplicate_outcome_semantic_projection(item)
            if event_hash
            else None
        )
        evaluation_semantics = (
            {
                key: value
                for key, value in evaluation.items()
                if key != "candidate_evaluation_context_hash"
            }
            if partition == "QUALIFIED" and isinstance(evaluation, dict)
            else None
        )
        source_sort_key = (
            candidate_board_module._canonical_sha256(
                {
                    "evaluation": evaluation,
                    "stable_projection": stable_projection,
                }
            )
            if full_seed
            else None
        )
        representative_sha256 = (
            candidate_board_module._canonical_sha256(
                candidate_board_module._duplicate_semantic_projection(item)
            )
            if partition == "QUALIFIED"
            else None
        )
        canonical_json = candidate_board_module._canonical_json
        self._db.execute(
            """
            INSERT INTO lineage_rows (
                partition_name, reason, event_hash, stable_cohort_hash,
                candidate_family_key, raw_event_date, current_exact_seed,
                row_json, evaluation_json, stable_projection_json,
                outcome_semantics_json, evaluation_semantics_json,
                representative_sha256, source_sort_key
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                partition,
                reason,
                event_hash,
                item.get("stable_cohort_hash"),
                family_key,
                raw_event_date_text,
                int(current_exact_seed),
                canonical_json(dict(item["row"])) if full_seed else None,
                canonical_json(dict(evaluation))
                if full_seed and isinstance(evaluation, dict)
                else None,
                canonical_json(dict(stable_projection))
                if full_seed and isinstance(stable_projection, dict)
                else None,
                canonical_json(outcome_semantics)
                if outcome_semantics is not None
                else None,
                canonical_json(evaluation_semantics)
                if evaluation_semantics is not None
                else None,
                representative_sha256,
                source_sort_key,
            ),
        )

    def finalize_scan(self) -> None:
        if self._closed:
            raise RuntimeError("candidate-board projection is closed")
        if self._finalized:
            return
        self._db.executescript(
            """
            CREATE INDEX lineage_rows_event_idx
                ON lineage_rows(event_hash, partition_name, row_id);
            CREATE INDEX lineage_rows_cohort_idx
                ON lineage_rows(stable_cohort_hash, partition_name, reason);
            CREATE INDEX lineage_rows_family_date_idx
                ON lineage_rows(candidate_family_key, raw_event_date, reason);
            """
        )
        self._db.commit()
        self._finalized = True


@dataclass
class CandidateBoardLedgerProjection:
    """Exact projection plus full-universe counters from one retained scan."""

    rows: CandidateBoardSqliteProjection
    source_ledger_row_count: int
    blocked_outcome_row_count: int
    additional_blocked_outcome_row_count: int
    lineage_exclusion_reason_counts: dict[str, int]

    @property
    def closed(self) -> bool:
        return self.rows.closed

    def __enter__(self) -> CandidateBoardLedgerProjection:
        if self.closed:
            raise RuntimeError("candidate-board ledger projection is closed")
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        self.rows.close()


def read_candidate_board_ledger_projection(
    ledger_path: Path,
    *,
    max_qualified_cohort_rows: int,
    max_qualified_cohort_bytes: int,
    additional_rows: Iterable[Mapping[str, Any]] = (),
) -> CandidateBoardLedgerProjection:
    """Scan one retained generation plus nonpersistent rows into one universe."""
    source_row_count = 0
    additional_blocked_outcome_row_count = 0
    rows = CandidateBoardSqliteProjection(
        max_qualified_cohort_rows=max_qualified_cohort_rows,
        max_qualified_cohort_bytes=max_qualified_cohort_bytes,
    )
    try:

        def consume(raw_row: dict[str, Any]) -> None:
            nonlocal source_row_count
            source_row_count += 1
            row = project_candidate_evidence_rows((raw_row,))[0]
            if row.get("record_type") == BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
                rows.add_blocked_row(row)

        scan_retained_jsonl(ledger_path, consume)
        for additional_row in additional_rows:
            row = project_candidate_evidence_rows((dict(additional_row),))[0]
            if row.get("record_type") != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
                continue
            rows.add_blocked_row(row)
            additional_blocked_outcome_row_count += 1
        rows.finalize_scan()
        return CandidateBoardLedgerProjection(
            rows=rows,
            source_ledger_row_count=source_row_count,
            blocked_outcome_row_count=rows.raw_blocked_outcome_row_count,
            additional_blocked_outcome_row_count=(
                additional_blocked_outcome_row_count
            ),
            lineage_exclusion_reason_counts={
                key: rows.lineage_exclusion_reason_counts[key]
                for key in sorted(rows.lineage_exclusion_reason_counts)
            },
        )
    except Exception:
        rows.close()
        raise


def _compact_duplicate_item(
    outcome_semantics_json: str,
    evaluation_semantics_json: str | None,
) -> dict[str, Any]:
    payload = json.loads(outcome_semantics_json)
    row = {
        key: field["value"]
        for key, field in payload["fields"].items()
        if field["present"]
    }
    item: dict[str, Any] = {"row": row}
    if evaluation_semantics_json is not None:
        item["evaluation"] = json.loads(evaluation_semantics_json)
    return item


class _ProjectionEventAccumulator:
    """O(frozen fields + addressed cohorts) reducer for one event hash."""

    def __init__(self) -> None:
        self.member_count = 0
        self.qualified_count = 0
        self.invalid_count = 0
        self.claimed_cohorts: set[str] = set()
        self.scoped_counts: dict[str, int] = {}
        self.semantic_equal = True
        self.baseline: dict[str, Any] | None = None
        self.numeric_bounds: dict[str, tuple[float | int, float | int]] = {}
        self.representative_row_id: int | None = None
        self.representative_sha256: str | None = None

    def add_member(
        self,
        *,
        row_id: int,
        partition: str,
        outcome_semantics_json: str | None,
        evaluation_semantics_json: str | None,
        representative_sha256: str | None,
        target_cohorts: set[str],
        claimed_cohorts: set[str],
    ) -> None:
        self.member_count += 1
        self.claimed_cohorts.update(claimed_cohorts)
        for cohort_hash in target_cohorts:
            self.scoped_counts[cohort_hash] = (
                self.scoped_counts.get(cohort_hash, 0) + 1
            )
        if partition == "INVALID":
            self.invalid_count += 1
            return
        if outcome_semantics_json is None:
            self.semantic_equal = False
            return
        item = _compact_duplicate_item(
            outcome_semantics_json,
            evaluation_semantics_json,
        )
        if partition == "QUALIFIED":
            self.qualified_count += 1
            if self.baseline is None:
                self.baseline = item
                for field in candidate_board_module._DUPLICATE_BPS_FIELDS:
                    if field not in item["row"]:
                        continue
                    value = item["row"][field]
                    if isinstance(value, (int, float)) and not isinstance(
                        value,
                        bool,
                    ):
                        if not math.isfinite(value):
                            self.semantic_equal = False
                        else:
                            self.numeric_bounds[field] = (value, value)
            elif not candidate_board_module._duplicate_semantics_equal(
                item,
                self.baseline,
            ):
                self.semantic_equal = False
            if (
                representative_sha256 is not None
                and (
                    self.representative_sha256 is None
                    or representative_sha256 < self.representative_sha256
                )
            ):
                self.representative_sha256 = representative_sha256
                self.representative_row_id = row_id
        elif (
            self.baseline is None
            or not candidate_board_module._duplicate_outcome_semantics_equal(
                item,
                self.baseline,
            )
        ):
            self.semantic_equal = False

        if self.baseline is not None:
            row = item["row"]
            for field, (minimum, maximum) in tuple(self.numeric_bounds.items()):
                value = row.get(field)
                if (
                    type(value) not in {int, float}
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                ):
                    self.semantic_equal = False
                    continue
                self.numeric_bounds[field] = (
                    min(minimum, value),
                    max(maximum, value),
                )

    def semantics_are_exact(self) -> bool:
        return bool(
            self.semantic_equal
            and self.qualified_count > 0
            and self.representative_row_id is not None
            and not any(
                maximum - minimum > 1e-9
                for minimum, maximum in self.numeric_bounds.values()
            )
        )


def _projection_duplicate_gate(
    projection: CandidateBoardSqliteProjection,
) -> tuple[dict[str, dict[str, int]], int, int]:
    db = projection._db
    db.executescript(
        """
        DROP TABLE IF EXISTS cohort_windows;
        DROP TABLE IF EXISTS row_cohorts;
        DROP TABLE IF EXISTS evaluator_rows;
        CREATE TEMP TABLE cohort_windows (
            cohort_hash TEXT NOT NULL,
            candidate_family_key TEXT NOT NULL,
            raw_event_date TEXT NOT NULL,
            PRIMARY KEY (cohort_hash, raw_event_date)
        );
        CREATE TEMP TABLE row_cohorts (
            row_id INTEGER NOT NULL,
            cohort_hash TEXT NOT NULL,
            claimed INTEGER NOT NULL,
            PRIMARY KEY (row_id, cohort_hash)
        );
        CREATE TEMP TABLE evaluator_rows (
            cohort_hash TEXT NOT NULL,
            event_hash TEXT NOT NULL,
            row_id INTEGER NOT NULL,
            PRIMARY KEY (cohort_hash, event_hash)
        );
        """
    )
    cohort_sources: dict[str, dict[str, Any]] = {}
    for (
        cohort_hash,
        family_key,
        evaluation_json,
        stable_projection_json,
        source_sort_key,
    ) in db.execute(
        """
        SELECT stable_cohort_hash, candidate_family_key, evaluation_json,
               stable_projection_json, source_sort_key
          FROM lineage_rows
         WHERE row_json IS NOT NULL
           AND stable_cohort_hash IS NOT NULL
         ORDER BY stable_cohort_hash, source_sort_key, row_id
        """
    ):
        if cohort_hash in cohort_sources:
            continue
        evaluation = json.loads(evaluation_json)
        cohort_sources[cohort_hash] = {
            "candidate_family_key": family_key,
            "evaluation": evaluation,
            "stable_projection": json.loads(stable_projection_json),
            "source_sort_key": source_sort_key,
        }
        db.executemany(
            """
            INSERT INTO cohort_windows (
                cohort_hash, candidate_family_key, raw_event_date
            ) VALUES (?, ?, ?)
            """,
            (
                (cohort_hash, family_key, date_value.isoformat())
                for date_value in sorted(
                    candidate_board_module._evaluation_window_dates(evaluation)
                )
            ),
        )
    projection._cohort_sources = cohort_sources
    db.executescript(
        """
        INSERT OR IGNORE INTO row_cohorts (row_id, cohort_hash, claimed)
        SELECT row_id, stable_cohort_hash, 1
          FROM lineage_rows
         WHERE event_hash IS NOT NULL
           AND stable_cohort_hash IS NOT NULL
           AND (
                partition_name = 'QUALIFIED'
                OR current_exact_seed = 1
           );

        INSERT OR IGNORE INTO row_cohorts (row_id, cohort_hash, claimed)
        SELECT rows.row_id, windows.cohort_hash, 0
          FROM lineage_rows AS rows
          JOIN cohort_windows AS windows
            ON windows.candidate_family_key = rows.candidate_family_key
           AND windows.raw_event_date = rows.raw_event_date
         WHERE rows.event_hash IS NOT NULL
           AND (
                rows.partition_name = 'UNQUALIFIED'
                OR (
                    rows.partition_name = 'INVALID'
                    AND rows.current_exact_seed = 0
                    AND rows.reason IN (
                        'INVALID_LINEAGE_EXACT_COHORT',
                        'INVALID_LINEAGE_IDENTITY_FAMILY'
                    )
                )
           );
        CREATE INDEX row_cohorts_event_idx
            ON row_cohorts(row_id, cohort_hash, claimed);
        """
    )

    audits: dict[str, dict[str, int]] = {}
    consistent_extra_total = 0
    conflict_total = 0

    def audit(cohort_hash: str) -> dict[str, int]:
        return audits.setdefault(
            cohort_hash,
            {
                "consistent_extra": 0,
                "conflicting": 0,
                "outcome_conflict": 0,
                "cohort_conflict": 0,
            },
        )

    def finish_event(accumulator: _ProjectionEventAccumulator) -> None:
        nonlocal consistent_extra_total, conflict_total
        if accumulator.member_count == 1 and accumulator.invalid_count:
            return
        if not accumulator.claimed_cohorts:
            return
        if len(accumulator.claimed_cohorts) > 1:
            conflict_total += accumulator.member_count
            for cohort_hash in accumulator.claimed_cohorts:
                scoped_count = accumulator.scoped_counts.get(cohort_hash, 0)
                scoped = audit(cohort_hash)
                scoped["conflicting"] += scoped_count
                scoped["cohort_conflict"] += scoped_count
            return
        cohort_hash = next(iter(accumulator.claimed_cohorts))
        if accumulator.invalid_count or not accumulator.semantics_are_exact():
            conflict_total += accumulator.member_count
            scoped = audit(cohort_hash)
            scoped["conflicting"] += accumulator.member_count
            scoped["outcome_conflict"] += accumulator.member_count
            return
        db.execute(
            """
            INSERT INTO evaluator_rows (cohort_hash, event_hash, row_id)
            SELECT ?, event_hash, ?
              FROM lineage_rows
             WHERE row_id = ?
            """,
            (
                cohort_hash,
                accumulator.representative_row_id,
                accumulator.representative_row_id,
            ),
        )
        extras = accumulator.qualified_count - 1
        if extras:
            consistent_extra_total += extras
            audit(cohort_hash)["consistent_extra"] += extras

    cursor = db.execute(
        """
        SELECT rows.event_hash, rows.row_id, rows.partition_name,
               rows.outcome_semantics_json, rows.evaluation_semantics_json,
               rows.representative_sha256, links.cohort_hash, links.claimed
          FROM lineage_rows AS rows
          JOIN row_cohorts AS links ON links.row_id = rows.row_id
         ORDER BY rows.event_hash,
                  CASE rows.partition_name WHEN 'QUALIFIED' THEN 0 ELSE 1 END,
                  rows.row_id,
                  links.cohort_hash
        """
    )
    current_event_hash: str | None = None
    current_row_id: int | None = None
    current_row: tuple[str, str | None, str | None, str | None] | None = None
    current_targets: set[str] = set()
    current_claims: set[str] = set()
    accumulator: _ProjectionEventAccumulator | None = None

    def finish_member() -> None:
        nonlocal current_row_id, current_row, current_targets, current_claims
        if accumulator is None or current_row_id is None or current_row is None:
            return
        partition, outcome_json, evaluation_json, representative_sha = current_row
        accumulator.add_member(
            row_id=current_row_id,
            partition=partition,
            outcome_semantics_json=outcome_json,
            evaluation_semantics_json=evaluation_json,
            representative_sha256=representative_sha,
            target_cohorts=current_targets,
            claimed_cohorts=current_claims,
        )
        current_row_id = None
        current_row = None
        current_targets = set()
        current_claims = set()

    for (
        event_hash,
        row_id,
        partition,
        outcome_json,
        evaluation_json,
        representative_sha,
        cohort_hash,
        claimed,
    ) in cursor:
        if event_hash != current_event_hash:
            finish_member()
            if accumulator is not None:
                finish_event(accumulator)
            current_event_hash = event_hash
            accumulator = _ProjectionEventAccumulator()
        if row_id != current_row_id:
            finish_member()
            current_row_id = row_id
            current_row = (
                partition,
                outcome_json,
                evaluation_json,
                representative_sha,
            )
        current_targets.add(cohort_hash)
        if claimed:
            current_claims.add(cohort_hash)
    finish_member()
    if accumulator is not None:
        finish_event(accumulator)
    db.commit()
    return audits, consistent_extra_total, conflict_total


def _load_projection_evaluator_rows(
    projection: CandidateBoardSqliteProjection,
    cohort_hash: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    projected_bytes = 0
    for (row_json,) in projection._db.execute(
        """
        SELECT rows.row_json
          FROM evaluator_rows AS selected
          JOIN lineage_rows AS rows ON rows.row_id = selected.row_id
         WHERE selected.cohort_hash = ?
         ORDER BY selected.event_hash
        """,
        (cohort_hash,),
    ):
        next_count = len(rows) + 1
        projected_bytes += len(row_json.encode("utf-8")) + 1
        if (
            next_count > projection.max_qualified_cohort_rows
            or projected_bytes > projection.max_qualified_cohort_bytes
        ):
            raise CandidateBoardQualifiedCohortMaterializationError(
                "CANDIDATE_BOARD_QUALIFIED_COHORT_MATERIALIZATION_LIMIT_REACHED:"
                f"{cohort_hash}"
            )
        rows.append(json.loads(row_json))
    return rows


def _finalize_candidate_board(
    *,
    projection: CandidateBoardSqliteProjection,
    candidate_rows: list[dict[str, Any]],
    as_of_date: dt.date,
    consistent_extras: int,
    duplicate_conflicts: int,
    eligible_rows_sink: dict[str, list[dict[str, Any]]] | None,
) -> dict[str, Any]:
    eligible_by_side_cell: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_rows:
        if row["selection_eligible"]:
            eligible_by_side_cell.setdefault(row["side_cell_key"], []).append(row)
    for rows in eligible_by_side_cell.values():
        if len(rows) > 1:
            for row in rows:
                row["blockers"] = sorted({
                    *row["blockers"],
                    "SIDE_CELL_STABLE_COHORT_AMBIGUITY",
                })
                row["selection_eligible"] = False
    candidate_rows.sort(
        key=lambda row: (
            row["candidate_identity"]["strategy_name"],
            row["candidate_identity"]["strategy_version"],
            row["candidate_identity"]["strategy_config_hash"],
            row["candidate_identity"]["symbol"],
            row["candidate_identity"]["side"],
            row["candidate_identity"]["horizon_minutes"],
            row["candidate_identity"]["target_regime_hash"],
            row["candidate_identity"]["venue"],
            row["candidate_identity"]["product"],
            row["candidate_identity"]["engine_mode"],
            row["candidate_id"],
            row["stable_cohort_hash"],
        )
    )
    if len({row["candidate_id"] for row in candidate_rows}) != len(candidate_rows):
        raise ValueError("CANDIDATE_ID_COLLISION")
    if eligible_rows_sink is not None:
        for row in candidate_rows:
            if row["selection_eligible"]:
                cohort_hash = row["stable_cohort_hash"]
                eligible_rows_sink[cohort_hash] = _load_projection_evaluator_rows(
                    projection,
                    cohort_hash,
                )
    semantic_rows = [
        {
            field: row[field]
            for field in candidate_board_module._SELECTION_FIELDS
        }
        for row in candidate_rows
    ]
    semantic_rows.sort(
        key=lambda row: (
            row["candidate_id"],
            candidate_board_module._canonical_sha256(row),
        )
    )
    selection_hash = candidate_board_module._canonical_sha256(
        {
            "schema_version": candidate_board_module._SELECTION_SCHEMA_VERSION,
            "candidate_rows": semantic_rows,
        }
    )
    lineage_partition_complete = (
        projection.raw_blocked_outcome_row_count
        == projection.qualified_lineage_outcome_row_count
        + projection.unqualified_lineage_outcome_row_count
        + projection.invalid_lineage_outcome_row_count
        and projection.invalid_lineage_outcome_row_count
        == projection.invalid_exact_cohort_row_count
        + projection.invalid_identity_family_row_count
        + projection.unassigned_invalid_lineage_outcome_row_count
    )
    if not lineage_partition_complete:
        raise ValueError("CANDIDATE_BOARD_COUNT_INVARIANT_VIOLATION")
    reasons = {
        key: projection.lineage_exclusion_reason_counts[key]
        for key in sorted(projection.lineage_exclusion_reason_counts)
    }
    top_audit = {
        "lineage_partition_complete": True,
        "raw_blocked_outcome_row_count": (
            projection.raw_blocked_outcome_row_count
        ),
        "qualified_lineage_outcome_row_count": (
            projection.qualified_lineage_outcome_row_count
        ),
        "unqualified_lineage_outcome_row_count": (
            projection.unqualified_lineage_outcome_row_count
        ),
        "invalid_lineage_outcome_row_count": (
            projection.invalid_lineage_outcome_row_count
        ),
        "invalid_exact_cohort_row_count": (
            projection.invalid_exact_cohort_row_count
        ),
        "invalid_identity_family_row_count": (
            projection.invalid_identity_family_row_count
        ),
        "unassigned_invalid_lineage_outcome_row_count": (
            projection.unassigned_invalid_lineage_outcome_row_count
        ),
        "unqualified_raw_valid_evaluation_missing_row_count": reasons.get(
            "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING",
            0,
        ),
        "unqualified_event_outside_evaluation_window_row_count": reasons.get(
            "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW",
            0,
        ),
        "consistent_duplicate_event_hash_extra_row_count": consistent_extras,
        "conflicting_duplicate_event_hash_row_count": duplicate_conflicts,
        "conflicting_duplicate_event_hash_attribution_row_count": sum(
            row["conflicting_event_hash_row_count"] for row in candidate_rows
        ),
        "lineage_exclusion_reason_counts": reasons,
    }
    selection_fields = set(candidate_board_module._SELECTION_FIELDS)
    candidate_audit_rows = [
        {
            "candidate_id": row["candidate_id"],
            **{
                key: value
                for key, value in row.items()
                if key not in selection_fields and key != "candidate_id"
            },
        }
        for row in candidate_rows
    ]
    candidate_audit_rows.sort(key=lambda row: row["candidate_id"])
    audit_hash = candidate_board_module._canonical_sha256(
        {
            "schema_version": candidate_board_module._AUDIT_SCHEMA_VERSION,
            **top_audit,
            "candidate_audit_rows": candidate_audit_rows,
        }
    )
    board = {
        "schema_version": LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION,
        "as_of_utc_date": as_of_date.isoformat(),
        "candidate_universe_complete": True,
        **top_audit,
        "candidate_rows": candidate_rows,
        "selection_hash": selection_hash,
        "audit_hash": audit_hash,
    }
    board["board_hash"] = candidate_board_module._canonical_sha256(board)
    return board


def build_learning_candidate_board_from_projection(
    projection: CandidateBoardSqliteProjection,
    *,
    cfg: candidate_board_module.CandidateBoardConfig,
    overlay: dict[str, dict[str, Any]],
    edge_estimates: dict[str, dict[str, Any]],
    expected_slippage: dict[str, Any] | None,
    as_of_date: dt.date,
    cohort_evaluator: candidate_board_module.CandidateCohortEvaluator,
    eligible_evaluator_rows_by_cohort_sink: (
        dict[str, list[dict[str, Any]]] | None
    ) = None,
) -> dict[str, Any]:
    """Mirror the list builder over one exact SQLite projection."""
    projection.finalize_scan()
    duplicate_audits, consistent_extras, duplicate_conflicts = (
        _projection_duplicate_gate(projection)
    )
    candidate_rows: list[dict[str, Any]] = []
    for cohort_hash in sorted(projection._cohort_sources):
        source = projection._cohort_sources[cohort_hash]
        evaluation_context = source["evaluation"]
        candidate_projection = (
            candidate_board_module.candidate_learning_context_projection(
                evaluation_context
            )
        )
        identity = candidate_board_module._candidate_identity(evaluation_context)
        family_key = source["candidate_family_key"]
        side_cell_key = (
            f"{identity['strategy_name']}|{identity['symbol']}|{identity['side']}"
        )
        qualified_raw_count = int(
            projection._db.execute(
                """
                SELECT COUNT(*)
                  FROM lineage_rows
                 WHERE partition_name = 'QUALIFIED'
                   AND stable_cohort_hash = ?
                """,
                (cohort_hash,),
            ).fetchone()[0]
        )
        exact_count = int(
            projection._db.execute(
                """
                SELECT COUNT(*)
                  FROM lineage_rows
                 WHERE partition_name = 'INVALID'
                   AND reason = 'INVALID_LINEAGE_EXACT_COHORT'
                   AND current_exact_seed = 1
                   AND stable_cohort_hash = ?
                """,
                (cohort_hash,),
            ).fetchone()[0]
        )
        family_count = int(
            projection._db.execute(
                """
                SELECT COUNT(*)
                  FROM lineage_rows AS rows
                  JOIN cohort_windows AS windows
                    ON windows.candidate_family_key = rows.candidate_family_key
                   AND windows.raw_event_date = rows.raw_event_date
                 WHERE windows.cohort_hash = ?
                   AND rows.partition_name = 'INVALID'
                   AND rows.reason = 'INVALID_LINEAGE_IDENTITY_FAMILY'
                """,
                (cohort_hash,),
            ).fetchone()[0]
        )
        duplicate = duplicate_audits.get(
            cohort_hash,
            {
                "consistent_extra": 0,
                "conflicting": 0,
                "outcome_conflict": 0,
                "cohort_conflict": 0,
            },
        )
        rows_for_evaluator = _load_projection_evaluator_rows(
            projection,
            cohort_hash,
        )
        cohort_expected_slippage = (
            candidate_board_module.candidate_cost_projection_for_recorded_date(
                expected_slippage,
                as_of_date=(
                    candidate_board_module._validated_evaluation_as_of_date(
                        evaluation_context
                    )
                ),
            )
        )
        evaluation = cohort_evaluator(
            side_cell_key,
            rows_for_evaluator,
            cfg=cfg,
            overlay=overlay,
            edge_estimates=edge_estimates,
            expected_slippage=cohort_expected_slippage,
        )
        candidate_rows.append(
            candidate_board_module._build_candidate_row(
                evaluation_context=evaluation_context,
                projection=candidate_projection,
                stable_cohort_hash=cohort_hash,
                candidate_family_key=family_key,
                qualified_raw_count=qualified_raw_count,
                evaluator_input_count=len(rows_for_evaluator),
                exact_invalid_count=exact_count,
                family_invalid_count=family_count,
                duplicate_audit=duplicate,
                cohort_evaluation=evaluation,
                expected_slippage=cohort_expected_slippage,
            )
        )
    return _finalize_candidate_board(
        projection=projection,
        candidate_rows=candidate_rows,
        as_of_date=as_of_date,
        consistent_extras=consistent_extras,
        duplicate_conflicts=duplicate_conflicts,
        eligible_rows_sink=eligible_evaluator_rows_by_cohort_sink,
    )

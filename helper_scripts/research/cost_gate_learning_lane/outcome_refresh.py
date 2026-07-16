#!/usr/bin/env python3
"""One-command outcome refresh for the cost-gate demo learning lane.

This module keeps the learning lane artifact-only. It reads the append-only
ledger, loads local price rows or read-only ``market.klines`` rows, builds
missing outcome rows, and optionally appends them back to the same JSONL ledger.
It never writes PG, calls Bybit, submits orders, or mutates runtime config.
"""

from __future__ import annotations

import argparse
from collections.abc import Collection
import copy
import datetime as dt
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import (
    ADMIT_DECISION,
    OUTCOME_ADAPTER_SCHEMA_VERSION,
)
from cost_gate_learning_lane.candidate_evaluation_producer import (
    CandidateEvaluationSourceProvider,
    outcome_subtype_semantics_valid,
    partition_candidate_evaluation_outcomes,
)
from cost_gate_learning_lane.candidate_evaluation_cold_source import (
    DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY,
    build_reviewed_legacy_build_source_provider,
)
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
    validate_outcome_config,
)
from cost_gate_learning_lane import outcome_writer as outcome_writer_module
from cost_gate_learning_lane.price_observations import (
    PriceObservationBuildConfig,
    build_price_observations_from_rows,
    connect_readonly_price_observation_pg,
    fetch_market_kline_price_rows,
    read_source_price_rows,
    required_price_observation_windows,
    validate_pg_timeframe,
    validate_price_observation_config,
)
from cost_gate_learning_lane.runtime_adapter import (
    append_jsonl_ledger,
    project_learning_ledger_row,
)
from cost_gate_learning_lane.ledger_streaming import (
    LedgerProjectionLimitError,
    LedgerScanError,
    scan_retained_jsonl,
)


OUTCOME_REFRESH_RECORD_TYPE = "cost_gate_outcome_refresh_batch"
OUTCOME_REFRESH_SCHEMA_VERSION = "cost_gate_demo_learning_lane_outcome_refresh_v1"
RETAINED_LEDGER_SCAN_DEFERRED_EXIT_CODE = 75
MAX_OUTCOME_REFRESH_PROJECTED_ROWS = 250_000
MAX_OUTCOME_REFRESH_PROJECTED_BYTES = 512 * 1024 * 1024
DEFAULT_OUTCOME_REFRESH_BATCH_LIMIT = 10_000
MAX_OUTCOME_REFRESH_BATCH_LIMIT = 250_000
_CANDIDATE_EVALUATION_PREFLIGHT_FIELDS = {
    "generated_outcome_count",
    "candidate_evaluation_eligible_count",
    "candidate_evaluation_preflight_attached_count",
    "candidate_evaluation_deferred_count",
    "candidate_evaluation_not_applicable_count",
    "candidate_evaluation_defer_reason_counts",
    "candidate_evaluation_batch_deferred",
    "deferred_outcome_count",
}


@dataclass(frozen=True)
class OutcomeRefreshSelection:
    """Which outcome rows this refresh should build."""

    record_blocked_outcomes: bool = False
    record_probe_outcomes: bool = False


@dataclass(frozen=True)
class OutcomeRefreshLedgerProjection:
    """Bounded outcome-refresh working set plus full-scan backlog accounting."""

    rows: list[dict[str, Any]]
    pending_attempt_count: int
    mature_pending_attempt_count: int
    selected_attempt_count: int
    selected_attempt_keys: tuple[tuple[str, str], ...]
    mature_backlog_remaining_count: int
    pending_backlog_remaining_count: int
    completed_attempt_count: int
    duplicate_admission_row_count: int
    conflict_attempt_count: int
    invalid_time_attempt_count: int
    immature_attempt_count: int
    relevant_fill_count: int
    projected_row_count: int
    projected_bytes: int
    batch_limit: int
    requested_side_cell_keys: tuple[str, ...]
    retained_ledger_source_row_count: int
    retained_ledger_source_bytes: int
    retained_ledger_scan_complete: bool = True
    pending_universe_fully_processed: bool = False

    def __iter__(self):
        return iter(self.rows)

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index):
        return self.rows[index]


def _canonical_row_bytes(row: dict[str, Any]) -> bytes:
    return json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


_OUTCOME_SEMANTIC_VOLATILE_KEYS = {
    "generated_at",
    "generated_at_ms",
    "generated_at_utc",
    "materialized_at",
    "materialized_at_ms",
    "materialized_at_utc",
    "source",
}


def _outcome_semantic_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _outcome_semantic_value(item)
            for key, item in value.items()
            if key not in _OUTCOME_SEMANTIC_VOLATILE_KEYS
        }
    if isinstance(value, list):
        return [_outcome_semantic_value(item) for item in value]
    return value


def _outcome_semantic_bytes(row: dict[str, Any]) -> bytes:
    return _canonical_row_bytes(
        {
            "effective_timestamp_ms": outcome_writer_module._row_ts_ms(row),
            "row": _outcome_semantic_value(row),
        }
    )


def _compact_fill_evidence_row(row: dict[str, Any]) -> dict[str, Any]:
    """Keep only fields consumed by outcome_writer fill reconciliation."""
    keys = {
        "fill_id",
        "exec_id",
        "execution_id",
        "attempt_id",
        "context_id",
        "signal_id",
        "order_link_id",
        "orderLinkId",
        "openclaw_order_link_id",
        "client_order_id",
        "order_id",
        "bounded_probe_attempt_id",
    }
    compact = {key: row[key] for key in keys if key in row}
    for section_name in ("event", "lineage"):
        section = row.get(section_name)
        if isinstance(section, dict):
            projected = {key: section[key] for key in keys if key in section}
            if projected:
                compact[section_name] = projected
    return compact


def _projection_horizon_minutes(
    row: dict[str, Any],
    *,
    default_horizon_minutes: int,
) -> int | None:
    return outcome_writer_module._row_outcome_horizon_minutes(
        row,
        default_horizon_minutes,
    )


def _fill_link_ids(row: dict[str, Any]) -> set[str]:
    keys = (
        "attempt_id",
        "context_id",
        "signal_id",
        "order_link_id",
        "orderLinkId",
        "openclaw_order_link_id",
        "bounded_probe_attempt_id",
    )
    sections = (row, row.get("event"), row.get("lineage"))
    return {
        str(section.get(key) or "").strip()
        for section in sections
        if isinstance(section, dict)
        for key in keys
        if str(section.get(key) or "").strip()
    }


def _validate_batch_limit(batch_limit: int) -> None:
    if (
        isinstance(batch_limit, bool)
        or not isinstance(batch_limit, int)
        or not 1 <= batch_limit <= MAX_OUTCOME_REFRESH_BATCH_LIMIT
    ):
        raise ValueError(
            "--outcome-refresh-batch-limit must be in [1, 250000]"
        )


def _normalize_side_cell_keys(
    side_cell_keys: Collection[str] | None,
) -> tuple[str, ...]:
    if side_cell_keys is None:
        return ()
    if isinstance(side_cell_keys, (str, bytes)):
        raise ValueError("side_cell_keys must be a collection of non-empty strings")
    normalized: set[str] = set()
    for value in side_cell_keys:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "side_cell_keys must be a collection of non-empty strings"
            )
        normalized.add(value.strip())
    if not normalized:
        raise ValueError("side_cell_keys must not be empty when provided")
    return tuple(sorted(normalized))


def read_outcome_refresh_ledger_projection(
    ledger_path: Path,
    *,
    selection: OutcomeRefreshSelection,
    now_utc: dt.datetime | None = None,
    outcome_cfg: ProbeOutcomeConfig | None = None,
    batch_limit: int = DEFAULT_OUTCOME_REFRESH_BATCH_LIMIT,
    side_cell_keys: Collection[str] | None = None,
) -> OutcomeRefreshLedgerProjection:
    """Scan the retained generation fully and return one bounded mature batch.

    When ``side_cell_keys`` is provided, only counting and oldest-first
    selection are scoped.  Admission variants, completed attempt keys,
    cross-target identities, and fills remain global in the disk-backed
    projection so a conflicting row outside the requested cell cannot be
    hidden by the scope.
    """
    _validate_selection(selection)
    outcome_cfg = outcome_cfg or ProbeOutcomeConfig()
    validate_outcome_config(outcome_cfg)
    _validate_batch_limit(batch_limit)
    requested_side_cell_keys = _normalize_side_cell_keys(side_cell_keys)
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    selected_record_types = set()
    if selection.record_blocked_outcomes:
        selected_record_types.add("blocked_signal_outcome")
    if selection.record_probe_outcomes:
        selected_record_types.add("probe_outcome")

    with tempfile.TemporaryDirectory(prefix="cost-gate-outcome-refresh-") as temp_dir:
        db_path = Path(temp_dir) / "projection.sqlite3"
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA journal_mode=OFF")
            conn.execute("PRAGMA synchronous=OFF")
            conn.executescript(
                """
                CREATE TABLE admissions (
                    target_record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    first_seq INTEGER NOT NULL,
                    event_ts_ms INTEGER NOT NULL,
                    horizon_minutes INTEGER,
                    payload BLOB NOT NULL,
                    duplicate_count INTEGER NOT NULL DEFAULT 0,
                    conflicted INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (target_record_type, attempt_id)
                ) WITHOUT ROWID;
                CREATE TABLE admission_variants (
                    target_record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    semantic_payload BLOB NOT NULL,
                    PRIMARY KEY (
                        target_record_type,
                        attempt_id,
                        semantic_payload
                    )
                ) WITHOUT ROWID;
                CREATE TABLE attempt_targets (
                    attempt_id TEXT NOT NULL,
                    target_record_type TEXT NOT NULL,
                    PRIMARY KEY (attempt_id, target_record_type)
                ) WITHOUT ROWID;
                CREATE TABLE admission_side_cells (
                    target_record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    side_cell_key TEXT NOT NULL,
                    PRIMARY KEY (
                        target_record_type,
                        attempt_id,
                        side_cell_key
                    )
                ) WITHOUT ROWID;
                CREATE TABLE completed (
                    record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    PRIMARY KEY (record_type, attempt_id)
                ) WITHOUT ROWID;
                CREATE TABLE fills (
                    payload BLOB PRIMARY KEY,
                    first_seq INTEGER NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE fill_links (
                    payload BLOB NOT NULL,
                    link_id TEXT NOT NULL,
                    PRIMARY KEY (payload, link_id)
                ) WITHOUT ROWID;
                """
            )
            seq = 0

            def consume(raw_row: dict[str, Any]) -> None:
                nonlocal seq
                seq += 1
                outcome_row, _dedup_row, quarantined = (
                    project_learning_ledger_row(raw_row)
                )
                if quarantined or outcome_row is None:
                    return
                record_type = str(outcome_row.get("record_type") or "").strip()
                if record_type in selected_record_types:
                    attempt_id = (
                        str(outcome_row.get("attempt_id") or "").strip()
                        or outcome_writer_module._attempt_id(outcome_row)
                    )
                    if attempt_id:
                        conn.execute(
                            "INSERT OR IGNORE INTO completed VALUES (?, ?)",
                            (record_type, attempt_id),
                        )
                if record_type == "probe_admission_decision":
                    decision = outcome_writer_module._row_decision(outcome_row)
                    target_record_type = None
                    if (
                        decision != ADMIT_DECISION
                        and outcome_row.get("allowed_to_submit_order") is False
                    ):
                        target_record_type = "blocked_signal_outcome"
                    elif decision == ADMIT_DECISION:
                        target_record_type = "probe_outcome"
                    if target_record_type is not None:
                        attempt_id = (
                            str(outcome_row.get("attempt_id") or "").strip()
                            or outcome_writer_module._attempt_id(outcome_row)
                        )
                        if attempt_id:
                            conn.execute(
                                "INSERT OR IGNORE INTO attempt_targets VALUES (?, ?)",
                                (attempt_id, target_record_type),
                            )
                            row_side_cell_key = (
                                outcome_writer_module._ledger_side_cell(
                                    outcome_row
                                )
                            )
                            if row_side_cell_key:
                                conn.execute(
                                    """
                                    INSERT OR IGNORE INTO admission_side_cells
                                    VALUES (?, ?, ?)
                                    """,
                                    (
                                        target_record_type,
                                        attempt_id,
                                        row_side_cell_key,
                                    ),
                                )
                        if (
                            attempt_id
                            and target_record_type in selected_record_types
                        ):
                            payload = _canonical_row_bytes(outcome_row)
                            semantic_payload = _outcome_semantic_bytes(
                                outcome_row
                            )
                            existing = conn.execute(
                                """
                                SELECT 1
                                FROM admissions
                                WHERE target_record_type = ? AND attempt_id = ?
                                """,
                                (target_record_type, attempt_id),
                            ).fetchone()
                            if existing is None:
                                conn.execute(
                                    """
                                    INSERT INTO admissions (
                                        target_record_type,
                                        attempt_id,
                                        first_seq,
                                        event_ts_ms,
                                        horizon_minutes,
                                        payload
                                    ) VALUES (?, ?, ?, ?, ?, ?)
                                    """,
                                    (
                                        target_record_type,
                                        attempt_id,
                                        seq,
                                        outcome_writer_module._row_ts_ms(
                                            outcome_row
                                        ),
                                        _projection_horizon_minutes(
                                            outcome_row,
                                            default_horizon_minutes=(
                                                outcome_cfg.horizon_minutes
                                            ),
                                        ),
                                        payload,
                                    ),
                                )
                                conn.execute(
                                    """
                                    INSERT INTO admission_variants
                                    VALUES (?, ?, ?)
                                    """,
                                    (
                                        target_record_type,
                                        attempt_id,
                                        semantic_payload,
                                    ),
                                )
                            else:
                                variant_insert = conn.execute(
                                    """
                                    INSERT OR IGNORE INTO admission_variants
                                    VALUES (?, ?, ?)
                                    """,
                                    (
                                        target_record_type,
                                        attempt_id,
                                        semantic_payload,
                                    ),
                                )
                                if variant_insert.rowcount == 0:
                                    conn.execute(
                                        """
                                        UPDATE admissions
                                        SET duplicate_count = duplicate_count + 1
                                        WHERE target_record_type = ?
                                          AND attempt_id = ?
                                        """,
                                        (target_record_type, attempt_id),
                                    )
                                else:
                                    conn.execute(
                                        """
                                        UPDATE admissions
                                        SET conflicted = 1
                                        WHERE target_record_type = ?
                                          AND attempt_id = ?
                                        """,
                                        (target_record_type, attempt_id),
                                    )
                if (
                    selection.record_probe_outcomes
                    and outcome_writer_module._row_has_fill_execution_evidence(
                        outcome_row
                    )
                ):
                    compact = _compact_fill_evidence_row(outcome_row)
                    payload = _canonical_row_bytes(compact)
                    conn.execute(
                        "INSERT OR IGNORE INTO fills VALUES (?, ?)",
                        (payload, seq),
                    )
                    conn.executemany(
                        "INSERT OR IGNORE INTO fill_links VALUES (?, ?)",
                        [(payload, link_id) for link_id in _fill_link_ids(compact)],
                    )

            scan = scan_retained_jsonl(ledger_path, consume)
            conn.commit()
            if requested_side_cell_keys:
                conn.execute(
                    """
                    CREATE TEMP TABLE requested_side_cells (
                        side_cell_key TEXT PRIMARY KEY
                    )
                    """
                )
                conn.executemany(
                    "INSERT INTO requested_side_cells VALUES (?)",
                    [(key,) for key in requested_side_cell_keys],
                )
            scope_clause = (
                """
                  AND EXISTS (
                      SELECT 1
                      FROM admission_side_cells scoped
                      JOIN requested_side_cells requested
                        ON requested.side_cell_key = scoped.side_cell_key
                      WHERE scoped.target_record_type = a.target_record_type
                        AND scoped.attempt_id = a.attempt_id
                  )
                """
                if requested_side_cell_keys
                else ""
            )
            conn.execute(
                """
                UPDATE admissions
                SET conflicted = 1
                WHERE attempt_id IN (
                    SELECT attempt_id
                    FROM attempt_targets
                    GROUP BY attempt_id
                    HAVING COUNT(DISTINCT target_record_type) > 1
                )
                """
            )
            conn.commit()
            processable = """
                FROM admissions a
                WHERE a.conflicted = 0
                  AND NOT EXISTS (
                      SELECT 1
                      FROM completed c
                      WHERE c.record_type = a.target_record_type
                        AND c.attempt_id = a.attempt_id
                  )
            """ + scope_clause
            pending_attempt_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM admissions a
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM completed c
                        WHERE c.record_type = a.target_record_type
                          AND c.attempt_id = a.attempt_id
                    )
                    {scope_clause}
                    """
                ).fetchone()[0]
            )
            completed_attempt_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM admissions a
                    WHERE a.conflicted = 0
                      AND EXISTS (
                          SELECT 1
                          FROM completed c
                          WHERE c.record_type = a.target_record_type
                          AND c.attempt_id = a.attempt_id
                      )
                    {scope_clause}
                    """
                ).fetchone()[0]
            )
            conflict_attempt_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM admissions a
                    WHERE a.conflicted = 1
                    {scope_clause}
                    """
                ).fetchone()[0]
            )
            duplicate_admission_row_count = int(
                conn.execute(
                    f"""
                    SELECT COALESCE(SUM(a.duplicate_count), 0)
                    FROM admissions a
                    WHERE 1 = 1
                    {scope_clause}
                    """
                ).fetchone()[0]
            )
            invalid_time_attempt_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) {processable}
                      AND (a.event_ts_ms <= 0 OR a.horizon_minutes IS NULL)
                    """
                ).fetchone()[0]
            )
            immature_attempt_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) {processable}
                      AND a.event_ts_ms > 0
                      AND a.horizon_minutes IS NOT NULL
                      AND a.event_ts_ms + a.horizon_minutes * 60000 > ?
                    """,
                    (now_ms,),
                ).fetchone()[0]
            )
            mature_pending_attempt_count = int(
                conn.execute(
                    f"""
                    SELECT COUNT(*) {processable}
                      AND a.event_ts_ms > 0
                      AND a.horizon_minutes IS NOT NULL
                      AND a.event_ts_ms + a.horizon_minutes * 60000 <= ?
                    """,
                    (now_ms,),
                ).fetchone()[0]
            )
            conn.execute(
                """
                CREATE TEMP TABLE selected_admissions (
                    target_record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    event_ts_ms INTEGER NOT NULL,
                    first_seq INTEGER NOT NULL,
                    payload BLOB NOT NULL,
                    PRIMARY KEY (target_record_type, attempt_id)
                ) WITHOUT ROWID
                """
            )
            conn.execute(
                f"""
                INSERT INTO selected_admissions
                SELECT
                    a.target_record_type,
                    a.attempt_id,
                    a.event_ts_ms,
                    a.first_seq,
                    a.payload
                {processable}
                  AND a.event_ts_ms > 0
                  AND a.horizon_minutes IS NOT NULL
                  AND a.event_ts_ms + a.horizon_minutes * 60000 <= ?
                ORDER BY
                    a.event_ts_ms,
                    a.first_seq,
                    a.target_record_type,
                    a.attempt_id
                LIMIT ?
                """,
                (now_ms, batch_limit),
            )
            selected_attempt_count = int(
                conn.execute(
                    "SELECT COUNT(*) FROM selected_admissions"
                ).fetchone()[0]
            )
            selected_attempt_keys: list[tuple[str, str]] = []
            projected_rows: list[dict[str, Any]] = []
            projected_bytes = 0

            def append_payload(payload: bytes) -> None:
                nonlocal projected_bytes
                projected_bytes += len(payload)
                if (
                    len(projected_rows) >= MAX_OUTCOME_REFRESH_PROJECTED_ROWS
                    or projected_bytes > MAX_OUTCOME_REFRESH_PROJECTED_BYTES
                ):
                    raise LedgerProjectionLimitError(
                        "OUTCOME_REFRESH_PROJECTION_LIMIT_REACHED",
                        path=ledger_path,
                    )
                projected_rows.append(
                    json.loads(bytes(payload).decode("utf-8"))
                )

            conn.execute(
                "CREATE TEMP TABLE selected_fill_links (link_id TEXT PRIMARY KEY)"
            )
            for target_record_type, attempt_id, raw_payload in conn.execute(
                """
                SELECT target_record_type, attempt_id, payload
                FROM selected_admissions
                ORDER BY
                    event_ts_ms,
                    first_seq,
                    target_record_type,
                    attempt_id
                """
            ):
                selected_attempt_keys.append(
                    (str(target_record_type), str(attempt_id))
                )
                payload = bytes(raw_payload)
                row = json.loads(payload.decode("utf-8"))
                append_payload(payload)
                if target_record_type == "probe_outcome":
                    conn.executemany(
                        "INSERT OR IGNORE INTO selected_fill_links VALUES (?)",
                        [(link_id,) for link_id in _fill_link_ids(row)],
                    )
            relevant_fill_count = 0
            for (payload,) in conn.execute(
                """
                SELECT f.payload
                FROM fills f
                WHERE EXISTS (
                    SELECT 1
                    FROM fill_links l
                    JOIN selected_fill_links s ON s.link_id = l.link_id
                    WHERE l.payload = f.payload
                )
                ORDER BY f.first_seq, f.payload
                """
            ):
                append_payload(bytes(payload))
                relevant_fill_count += 1

            mature_backlog_remaining_count = mature_pending_attempt_count
            pending_backlog_remaining_count = pending_attempt_count
            return OutcomeRefreshLedgerProjection(
                rows=projected_rows,
                pending_attempt_count=pending_attempt_count,
                mature_pending_attempt_count=mature_pending_attempt_count,
                selected_attempt_count=selected_attempt_count,
                selected_attempt_keys=tuple(selected_attempt_keys),
                mature_backlog_remaining_count=mature_backlog_remaining_count,
                pending_backlog_remaining_count=pending_backlog_remaining_count,
                completed_attempt_count=completed_attempt_count,
                duplicate_admission_row_count=duplicate_admission_row_count,
                conflict_attempt_count=conflict_attempt_count,
                invalid_time_attempt_count=invalid_time_attempt_count,
                immature_attempt_count=immature_attempt_count,
                relevant_fill_count=relevant_fill_count,
                projected_row_count=len(projected_rows),
                projected_bytes=projected_bytes,
                batch_limit=batch_limit,
                requested_side_cell_keys=requested_side_cell_keys,
                retained_ledger_source_row_count=scan.row_count,
                retained_ledger_source_bytes=scan.source_bytes,
                retained_ledger_scan_complete=True,
                pending_universe_fully_processed=(
                    pending_backlog_remaining_count == 0
                    and conflict_attempt_count == 0
                ),
            )
        finally:
            conn.close()


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _validate_selection(selection: OutcomeRefreshSelection) -> None:
    if not selection.record_blocked_outcomes and not selection.record_probe_outcomes:
        raise ValueError(
            "select at least one of --record-blocked-outcomes or --record-probe-outcomes"
        )


def price_observation_config_for_refresh(
    *,
    selection: OutcomeRefreshSelection,
    outcome_cfg: ProbeOutcomeConfig,
) -> PriceObservationBuildConfig:
    """Map the requested outcome refresh into required price windows."""
    _validate_selection(selection)
    validate_outcome_config(outcome_cfg)
    cfg = PriceObservationBuildConfig(
        horizon_minutes=outcome_cfg.horizon_minutes,
        max_entry_delay_ms=outcome_cfg.max_entry_delay_ms,
        include_blocked_signals=selection.record_blocked_outcomes,
        include_admitted_probes=selection.record_probe_outcomes,
    )
    validate_price_observation_config(cfg)
    return cfg


def build_cost_gate_outcome_refresh_batch(
    ledger_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    selection: OutcomeRefreshSelection | None = None,
    outcome_cfg: ProbeOutcomeConfig | None = None,
    price_source: str,
    candidate_evaluation_source_provider: (
        CandidateEvaluationSourceProvider | None
    ) = None,
) -> dict[str, Any]:
    """Build missing outcome rows from a ledger plus price rows."""
    selection = selection or OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = outcome_cfg or ProbeOutcomeConfig()
    price_cfg = price_observation_config_for_refresh(
        selection=selection,
        outcome_cfg=outcome_cfg,
    )
    windows = required_price_observation_windows(ledger_rows, cfg=price_cfg)
    observations = build_price_observations_from_rows(price_rows, windows)
    generated_at = (now_utc or _utc_now()).astimezone(dt.timezone.utc)

    probe_outcomes = (
        build_probe_outcome_records(
            ledger_rows,
            observations,
            now_utc=generated_at,
            cfg=outcome_cfg,
        )
        if selection.record_probe_outcomes
        else []
    )
    blocked_outcomes = (
        build_blocked_signal_outcome_records(
            ledger_rows,
            observations,
            now_utc=generated_at,
            cfg=outcome_cfg,
        )
        if selection.record_blocked_outcomes
        else []
    )
    preflight = partition_candidate_evaluation_outcomes(
        probe_outcomes + blocked_outcomes,
        source_provider=candidate_evaluation_source_provider,
        now_utc=generated_at,
    )
    outcome_rows = preflight["outcomes"]
    probe_outcomes = preflight["probe_outcomes"]
    blocked_outcomes = preflight["blocked_signal_outcomes"]

    return {
        "schema_version": OUTCOME_REFRESH_SCHEMA_VERSION,
        # C4 對稱性:此 batch 只包 outcome 面 record(probe_outcomes + blocked_outcomes),
        # 故攜 outcome 面版本(v2),與 runtime_adapter.main() 的 probe_outcome_batch 一致。
        "adapter_schema_version": OUTCOME_ADAPTER_SCHEMA_VERSION,
        "record_type": OUTCOME_REFRESH_RECORD_TYPE,
        "generated_at_utc": generated_at.isoformat(),
        "price_source": price_source,
        "record_blocked_outcomes": selection.record_blocked_outcomes,
        "record_probe_outcomes": selection.record_probe_outcomes,
        "horizon_minutes": outcome_cfg.horizon_minutes,
        "outcome_cost_bps": outcome_cfg.cost_bps,
        "max_entry_delay_ms": outcome_cfg.max_entry_delay_ms,
        "window_count": len(windows),
        "price_observation_count": len(observations),
        "probe_outcome_count": len(probe_outcomes),
        "blocked_signal_outcome_count": len(blocked_outcomes),
        "outcome_count": len(outcome_rows),
        "windows": windows,
        "observations": observations,
        "outcomes": outcome_rows,
        "probe_outcomes": probe_outcomes,
        "blocked_signal_outcomes": blocked_outcomes,
        "append_requested": False,
        "appended_to_ledger": False,
        "appended_outcome_count": 0,
        **{
            key: value
            for key, value in preflight.items()
            if key
            not in {"outcomes", "probe_outcomes", "blocked_signal_outcomes"}
        },
        "boundary": (
            "outcome refresh artifact only; PG source is read-only SELECT-only; "
            "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
        ),
    }


def append_refresh_outcomes_to_ledger(
    ledger_path: Path,
    batch: dict[str, Any],
    *,
    projection: OutcomeRefreshLedgerProjection | None = None,
) -> int:
    """Append built outcome rows from a refresh batch to the JSONL ledger."""
    rows = batch.get("outcomes")
    if (
        not isinstance(rows, list)
        or not _candidate_evaluation_preflight_valid(batch, rows)
    ):
        _refuse_refresh_append(batch)
        if projection is not None:
            _attach_projection_accounting(batch, projection)
        return 0
    try:
        rows_to_append = copy.deepcopy(rows)
        for row in rows_to_append:
            json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                allow_nan=False,
            )
    except Exception:
        _refuse_refresh_append(batch)
        if projection is not None:
            _attach_projection_accounting(batch, projection)
        return 0
    if projection is None:
        outcome_attempt_keys = [
            _outcome_attempt_key(row) for row in rows_to_append
        ]
    else:
        projection_bound_keys = _projection_bound_outcome_attempt_keys(
            rows_to_append,
            projection,
        )
        if projection_bound_keys is None:
            _refuse_refresh_append(batch)
            _attach_projection_accounting(batch, projection)
            return 0
        outcome_attempt_keys = projection_bound_keys
    appended = 0
    appended_attempt_keys: set[tuple[str, str]] = set()
    try:
        for row, attempt_key in zip(rows_to_append, outcome_attempt_keys):
            append_jsonl_ledger(ledger_path, row)
            appended += 1
            if attempt_key is not None:
                appended_attempt_keys.add(attempt_key)
    finally:
        batch["append_requested"] = True
        batch["appended_to_ledger"] = appended > 0
        batch["appended_outcome_count"] = appended
        if projection is not None:
            _attach_projection_accounting(
                batch,
                projection,
                appended_attempt_keys=appended_attempt_keys,
            )
    return appended


def _outcome_attempt_key(row: dict[str, Any]) -> tuple[str, str] | None:
    raw_record_type = row.get("record_type")
    raw_attempt_id = row.get("attempt_id")
    if not isinstance(raw_record_type, str) or not isinstance(raw_attempt_id, str):
        return None
    record_type = raw_record_type.strip()
    attempt_id = raw_attempt_id.strip()
    if (
        record_type not in {"blocked_signal_outcome", "probe_outcome"}
        or not attempt_id
    ):
        return None
    return record_type, attempt_id


def _projection_bound_outcome_attempt_keys(
    rows: list[dict[str, Any]],
    projection: OutcomeRefreshLedgerProjection,
) -> list[tuple[str, str]] | None:
    selected_attempt_keys = set(projection.selected_attempt_keys)
    if (
        len(selected_attempt_keys) != len(projection.selected_attempt_keys)
        or len(selected_attempt_keys) != projection.selected_attempt_count
    ):
        return None
    outcome_attempt_keys: list[tuple[str, str]] = []
    seen_attempt_keys: set[tuple[str, str]] = set()
    for row in rows:
        attempt_key = _outcome_attempt_key(row)
        if (
            attempt_key is None
            or attempt_key not in selected_attempt_keys
            or attempt_key in seen_attempt_keys
        ):
            return None
        seen_attempt_keys.add(attempt_key)
        outcome_attempt_keys.append(attempt_key)
    return outcome_attempt_keys


def _attach_projection_accounting(
    batch: dict[str, Any],
    projection: OutcomeRefreshLedgerProjection,
    *,
    appended_attempt_keys: set[tuple[str, str]] | None = None,
) -> None:
    selected_attempt_keys = set(projection.selected_attempt_keys)
    terminalized_attempt_keys = selected_attempt_keys.intersection(
        appended_attempt_keys or set()
    )
    selected_terminalized_attempt_count = len(terminalized_attempt_keys)
    selected_unterminalized_attempt_count = (
        len(selected_attempt_keys) - selected_terminalized_attempt_count
    )
    mature_backlog_remaining_count = (
        projection.mature_pending_attempt_count
        - selected_terminalized_attempt_count
    )
    pending_backlog_remaining_count = (
        projection.pending_attempt_count - selected_terminalized_attempt_count
    )
    batch.update(
        {
            "pending_attempt_count": projection.pending_attempt_count,
            "mature_pending_attempt_count": (
                projection.mature_pending_attempt_count
            ),
            "selected_attempt_count": len(selected_attempt_keys),
            "selected_terminalized_attempt_count": (
                selected_terminalized_attempt_count
            ),
            "selected_unterminalized_attempt_count": (
                selected_unterminalized_attempt_count
            ),
            "mature_backlog_remaining_count": mature_backlog_remaining_count,
            "pending_backlog_remaining_count": pending_backlog_remaining_count,
            "completed_attempt_count": projection.completed_attempt_count,
            "duplicate_admission_row_count": (
                projection.duplicate_admission_row_count
            ),
            "conflict_attempt_count": projection.conflict_attempt_count,
            "invalid_time_attempt_count": (
                projection.invalid_time_attempt_count
            ),
            "immature_attempt_count": projection.immature_attempt_count,
            "relevant_fill_count": projection.relevant_fill_count,
            "projected_row_count": projection.projected_row_count,
            "projected_bytes": projection.projected_bytes,
            "batch_limit": projection.batch_limit,
            "retained_ledger_source_row_count": (
                projection.retained_ledger_source_row_count
            ),
            "retained_ledger_source_bytes": (
                projection.retained_ledger_source_bytes
            ),
            "retained_ledger_scan_complete": (
                projection.retained_ledger_scan_complete
            ),
            "pending_universe_fully_processed": (
                pending_backlog_remaining_count == 0
                and projection.conflict_attempt_count == 0
            ),
        }
    )


def _candidate_evaluation_preflight_valid(
    batch: dict[str, Any],
    rows: list[Any],
) -> bool:
    required_shape_fields = {
        "generated_at_utc",
        "outcome_count",
        "probe_outcome_count",
        "blocked_signal_outcome_count",
        "probe_outcomes",
        "blocked_signal_outcomes",
    }
    if (
        not _CANDIDATE_EVALUATION_PREFLIGHT_FIELDS <= set(batch)
        or not required_shape_fields <= set(batch)
        or not all(isinstance(row, dict) for row in rows)
        or not all(outcome_subtype_semantics_valid(row) for row in rows)
        or not isinstance(batch["probe_outcomes"], list)
        or not isinstance(batch["blocked_signal_outcomes"], list)
    ):
        return False
    count_fields = (
        "generated_outcome_count",
        "candidate_evaluation_eligible_count",
        "candidate_evaluation_preflight_attached_count",
        "candidate_evaluation_deferred_count",
        "candidate_evaluation_not_applicable_count",
        "deferred_outcome_count",
    )
    if any(
        isinstance(batch.get(field), bool)
        or not isinstance(batch.get(field), int)
        or batch[field] < 0
        for field in count_fields
    ):
        return False
    generated = batch["generated_outcome_count"]
    eligible = batch["candidate_evaluation_eligible_count"]
    attached = batch["candidate_evaluation_preflight_attached_count"]
    deferred = batch["candidate_evaluation_deferred_count"]
    not_applicable = batch["candidate_evaluation_not_applicable_count"]
    reason_counts = batch["candidate_evaluation_defer_reason_counts"]
    batch_deferred = batch["candidate_evaluation_batch_deferred"]
    if (
        not isinstance(reason_counts, dict)
        or not all(
            isinstance(reason, str)
            and reason
            and isinstance(count, int)
            and not isinstance(count, bool)
            and count > 0
            for reason, count in reason_counts.items()
        )
        or not isinstance(batch_deferred, bool)
    ):
        return False
    arithmetic_valid = bool(
        generated == eligible + not_applicable
        and eligible == attached + deferred
        and sum(reason_counts.values()) == deferred
        and batch["deferred_outcome_count"] == deferred
        and batch_deferred is (deferred > 0)
        and (not batch_deferred or not rows)
        and (batch_deferred or len(rows) == generated)
    )
    if not arithmetic_valid or batch_deferred:
        return False

    subtype_lists = (
        batch["probe_outcomes"],
        batch["blocked_signal_outcomes"],
    )
    shape_counts = (
        ("outcome_count", rows),
        ("probe_outcome_count", subtype_lists[0]),
        ("blocked_signal_outcome_count", subtype_lists[1]),
    )
    if any(
        isinstance(batch.get(field), bool)
        or not isinstance(batch.get(field), int)
        or batch[field] != len(values)
        for field, values in shape_counts
    ):
        return False

    generated_at = _parse_aware_utc(batch["generated_at_utc"])
    if generated_at is None:
        return False
    semantic_now = min(_utc_now(), generated_at)
    try:
        semantic = partition_candidate_evaluation_outcomes(
            rows,
            source_provider=None,
            now_utc=semantic_now,
        )
    except Exception:
        return False
    if any(
        not _exact_value_equal(semantic[field], batch[field])
        for field in _CANDIDATE_EVALUATION_PREFLIGHT_FIELDS
    ):
        return False
    return bool(
        _exact_value_equal(semantic["outcomes"], rows)
        and _exact_value_equal(
            semantic["probe_outcomes"],
            batch["probe_outcomes"],
        )
        and _exact_value_equal(
            semantic["blocked_signal_outcomes"],
            batch["blocked_signal_outcomes"],
        )
        and _exact_value_equal(
            rows,
            batch["probe_outcomes"] + batch["blocked_signal_outcomes"],
        )
    )


def _parse_aware_utc(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(dt.timezone.utc)


def _exact_value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, dict) and isinstance(right, dict):
        return set(left) == set(right) and all(
            _exact_value_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _exact_value_equal(left_item, right_item)
            for left_item, right_item in zip(left, right)
        )
    return type(left) is type(right) and left == right


def _refuse_refresh_append(batch: dict[str, Any]) -> None:
    batch["append_requested"] = True
    batch["appended_to_ledger"] = False
    batch["appended_outcome_count"] = 0
    for field in ("outcomes", "probe_outcomes", "blocked_signal_outcomes"):
        if field in batch:
            batch[field] = []
    for field in ("outcome_count", "probe_outcome_count", "blocked_signal_outcome_count"):
        if field in batch:
            batch[field] = 0


def build_price_rows_from_pg_for_refresh(
    ledger_rows: list[dict[str, Any]],
    *,
    selection: OutcomeRefreshSelection,
    outcome_cfg: ProbeOutcomeConfig,
    timeframe: str = "1m",
    statement_timeout_ms: int = 180_000,
    conn: Any | None = None,
) -> list[dict[str, Any]]:
    """Load local PG kline rows needed by this refresh selection."""
    timeframe = validate_pg_timeframe(timeframe)
    price_cfg = price_observation_config_for_refresh(
        selection=selection,
        outcome_cfg=outcome_cfg,
    )
    windows = required_price_observation_windows(ledger_rows, cfg=price_cfg)
    if not windows:
        return []
    owned_conn = conn is None
    pg_conn = conn or connect_readonly_price_observation_pg(
        statement_timeout_ms_default=statement_timeout_ms,
    )
    try:
        return fetch_market_kline_price_rows(pg_conn, windows, timeframe=timeframe)
    finally:
        if owned_conn:
            close = getattr(pg_conn, "close", None)
            if callable(close):
                close()


def refresh_cost_gate_outcomes_from_price_rows(
    ledger_path: Path,
    price_rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    selection: OutcomeRefreshSelection | None = None,
    outcome_cfg: ProbeOutcomeConfig | None = None,
    price_source: str = "local_price_file",
    append_ledger: bool = False,
    batch_limit: int = DEFAULT_OUTCOME_REFRESH_BATCH_LIMIT,
    side_cell_keys: Collection[str] | None = None,
    candidate_evaluation_source_provider: (
        CandidateEvaluationSourceProvider | None
    ) = None,
) -> dict[str, Any]:
    """Build a refresh batch from in-memory price rows and optionally append it."""
    selection = selection or OutcomeRefreshSelection(record_blocked_outcomes=True)
    outcome_cfg = outcome_cfg or ProbeOutcomeConfig()
    fixed_now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    projection = read_outcome_refresh_ledger_projection(
        ledger_path,
        selection=selection,
        now_utc=fixed_now,
        outcome_cfg=outcome_cfg,
        batch_limit=batch_limit,
        side_cell_keys=side_cell_keys,
    )
    batch = build_cost_gate_outcome_refresh_batch(
        projection.rows,
        price_rows,
        now_utc=fixed_now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source=price_source,
        candidate_evaluation_source_provider=candidate_evaluation_source_provider,
    )
    _attach_projection_accounting(batch, projection)
    if append_ledger:
        append_refresh_outcomes_to_ledger(
            ledger_path,
            batch,
            projection=projection,
        )
    return batch


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-prices", type=Path)
    source.add_argument("--source-pg", action="store_true")
    parser.add_argument("--record-blocked-outcomes", action="store_true")
    parser.add_argument("--record-probe-outcomes", action="store_true")
    parser.add_argument("--append-ledger", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--outcome-cost-bps", type=float, default=4.0)
    # P1-2a:每日分位 artifact 路徑。給定則保守成本走 per-symbol/global q75,
    # 否則 fallback 到 toml_tier(離線可跑,仍保守)。--outcome-cost-bps 只保留為
    # net_bps_optimistic 連續性對照列的常數,不再是權威淨值。
    parser.add_argument("--slippage-artifact", type=Path, default=None)
    parser.add_argument("--max-entry-delay-ms", type=int, default=5 * 60_000)
    parser.add_argument("--pg-timeframe", default="1m")
    parser.add_argument("--pg-statement-timeout-ms", type=int, default=180_000)
    parser.add_argument(
        "--outcome-refresh-batch-limit",
        type=int,
        default=DEFAULT_OUTCOME_REFRESH_BATCH_LIMIT,
    )
    parser.add_argument(
        "--enable-pre-capability-candidate-evaluation-source",
        action="store_true",
    )
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    selection = OutcomeRefreshSelection(
        record_blocked_outcomes=args.record_blocked_outcomes,
        record_probe_outcomes=args.record_probe_outcomes,
    )
    _validate_selection(selection)
    fixed_now = _utc_now()
    slippage_table = None
    if args.slippage_artifact and args.slippage_artifact.exists():
        from cost_gate_learning_lane.cost_model import load_slippage_quantiles

        payload = json.loads(args.slippage_artifact.read_text(encoding="utf-8"))
        slippage_table = load_slippage_quantiles(payload)
    outcome_cfg = ProbeOutcomeConfig(
        horizon_minutes=args.horizon_minutes,
        cost_bps=args.outcome_cost_bps,
        max_entry_delay_ms=args.max_entry_delay_ms,
        slippage_table=slippage_table,
    )
    validate_outcome_config(outcome_cfg)
    try:
        projection = read_outcome_refresh_ledger_projection(
            args.ledger,
            selection=selection,
            now_utc=fixed_now,
            outcome_cfg=outcome_cfg,
            batch_limit=args.outcome_refresh_batch_limit,
        )
    except (LedgerScanError, LedgerProjectionLimitError) as exc:
        print(
            json.dumps(
                {
                    "status": "RETAINED_LEDGER_SCAN_DEFERRED",
                    "ledger_path": str(args.ledger),
                    "reason": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return RETAINED_LEDGER_SCAN_DEFERRED_EXIT_CODE
    ledger_rows = projection.rows

    if args.source_pg:
        price_rows = build_price_rows_from_pg_for_refresh(
            ledger_rows,
            selection=selection,
            outcome_cfg=outcome_cfg,
            timeframe=args.pg_timeframe,
            statement_timeout_ms=args.pg_statement_timeout_ms,
        )
        price_source = "pg_market_klines"
    else:
        if args.source_prices is None:
            raise ValueError("--source-prices is required unless --source-pg is used")
        price_rows = read_source_price_rows(args.source_prices)
        price_source = "local_price_file"

    candidate_evaluation_source_provider = (
        build_reviewed_legacy_build_source_provider(
            DEFAULT_REVIEWED_LEGACY_BUILD_REGISTRY
        )
        if args.enable_pre_capability_candidate_evaluation_source
        else None
    )
    batch = build_cost_gate_outcome_refresh_batch(
        ledger_rows,
        price_rows,
        now_utc=fixed_now,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source=price_source,
        candidate_evaluation_source_provider=(
            candidate_evaluation_source_provider
        ),
    )
    _attach_projection_accounting(batch, projection)
    if args.source_pg:
        batch["pg_timeframe"] = args.pg_timeframe
    if args.append_ledger:
        append_refresh_outcomes_to_ledger(
            args.ledger,
            batch,
            projection=projection,
        )
    if args.output:
        _write_json(args.output, batch)
    if args.print_json or not args.output:
        print(json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

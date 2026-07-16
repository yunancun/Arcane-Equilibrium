#!/usr/bin/env python3
"""One-command outcome refresh for the cost-gate demo learning lane.

This module keeps the learning lane artifact-only. It reads the append-only
ledger, loads local price rows or read-only ``market.klines`` rows, builds
missing outcome rows, and optionally appends them back to the same JSONL ledger.
It never writes PG, calls Bybit, submits orders, or mutates runtime config.
"""

from __future__ import annotations

import argparse
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


def _canonical_row_bytes(row: dict[str, Any]) -> bytes:
    return json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


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


def read_outcome_refresh_ledger_projection(
    ledger_path: Path,
    *,
    selection: OutcomeRefreshSelection,
) -> list[dict[str, Any]]:
    """Project only pending admissions and exact fill links through one scan."""
    _validate_selection(selection)
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
                    seq INTEGER PRIMARY KEY,
                    target_record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    payload BLOB NOT NULL
                );
                CREATE TABLE completed (
                    record_type TEXT NOT NULL,
                    attempt_id TEXT NOT NULL,
                    PRIMARY KEY (record_type, attempt_id)
                ) WITHOUT ROWID;
                CREATE TABLE fills (
                    seq INTEGER PRIMARY KEY,
                    payload BLOB NOT NULL
                );
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
                        selection.record_blocked_outcomes
                        and decision != ADMIT_DECISION
                        and outcome_row.get("allowed_to_submit_order") is False
                    ):
                        target_record_type = "blocked_signal_outcome"
                    elif (
                        selection.record_probe_outcomes
                        and decision == ADMIT_DECISION
                    ):
                        target_record_type = "probe_outcome"
                    if target_record_type is not None:
                        attempt_id = (
                            str(outcome_row.get("attempt_id") or "").strip()
                            or outcome_writer_module._attempt_id(outcome_row)
                        )
                        if attempt_id:
                            conn.execute(
                                "INSERT INTO admissions VALUES (?, ?, ?, ?)",
                                (
                                    seq,
                                    target_record_type,
                                    attempt_id,
                                    _canonical_row_bytes(outcome_row),
                                ),
                            )
                if (
                    selection.record_probe_outcomes
                    and outcome_writer_module._row_has_fill_execution_evidence(
                        outcome_row
                    )
                ):
                    conn.execute(
                        "INSERT INTO fills VALUES (?, ?)",
                        (
                            seq,
                            _canonical_row_bytes(
                                _compact_fill_evidence_row(outcome_row)
                            ),
                        ),
                    )

            scan_retained_jsonl(ledger_path, consume)
            conn.commit()
            projected_rows: list[dict[str, Any]] = []
            projected_bytes = 0
            for _seq, payload in conn.execute(
                """
                SELECT a.seq, a.payload
                FROM admissions a
                WHERE NOT EXISTS (
                    SELECT 1
                    FROM completed c
                    WHERE c.record_type = a.target_record_type
                      AND c.attempt_id = a.attempt_id
                )
                UNION ALL
                SELECT f.seq, f.payload FROM fills f
                ORDER BY seq
                """
            ):
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
            return projected_rows
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


def append_refresh_outcomes_to_ledger(ledger_path: Path, batch: dict[str, Any]) -> int:
    """Append built outcome rows from a refresh batch to the JSONL ledger."""
    rows = batch.get("outcomes")
    if (
        not isinstance(rows, list)
        or not _candidate_evaluation_preflight_valid(batch, rows)
    ):
        _refuse_refresh_append(batch)
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
        return 0
    appended = 0
    for row in rows_to_append:
        append_jsonl_ledger(ledger_path, row)
        appended += 1
    batch["append_requested"] = True
    batch["appended_to_ledger"] = appended > 0
    batch["appended_outcome_count"] = appended
    return appended


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
    candidate_evaluation_source_provider: (
        CandidateEvaluationSourceProvider | None
    ) = None,
) -> dict[str, Any]:
    """Build a refresh batch from in-memory price rows and optionally append it."""
    selection = selection or OutcomeRefreshSelection(record_blocked_outcomes=True)
    ledger_rows = read_outcome_refresh_ledger_projection(
        ledger_path,
        selection=selection,
    )
    batch = build_cost_gate_outcome_refresh_batch(
        ledger_rows,
        price_rows,
        now_utc=now_utc,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source=price_source,
        candidate_evaluation_source_provider=candidate_evaluation_source_provider,
    )
    if append_ledger:
        append_refresh_outcomes_to_ledger(ledger_path, batch)
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
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    selection = OutcomeRefreshSelection(
        record_blocked_outcomes=args.record_blocked_outcomes,
        record_probe_outcomes=args.record_probe_outcomes,
    )
    _validate_selection(selection)
    try:
        ledger_rows = read_outcome_refresh_ledger_projection(
            args.ledger,
            selection=selection,
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

    batch = build_cost_gate_outcome_refresh_batch(
        ledger_rows,
        price_rows,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source=price_source,
    )
    if args.source_pg:
        batch["pg_timeframe"] = args.pg_timeframe
    if args.append_ledger:
        append_refresh_outcomes_to_ledger(args.ledger, batch)
    if args.output:
        _write_json(args.output, batch)
    if args.print_json or not args.output:
        print(json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

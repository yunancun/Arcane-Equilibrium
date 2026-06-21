#!/usr/bin/env python3
"""Materialize recorded cost-gate rejects into the demo-learning ledger.

The Rust hot-path writer is the live capture path, but it is operator-gated.
This module recovers already-recorded PG ``learning.decision_features`` rejects
into the same append-only JSONL contract used by the runtime adapter. It only
builds or appends artifact rows; it never writes PG, calls Bybit, submits
orders, lowers the main Cost Gate, or mutates runtime config.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import datetime as dt
from dataclasses import dataclass
import json
import math
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import (  # noqa: E402
    ADAPTER_SCHEMA_VERSION,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
)
from cost_gate_learning_lane.runtime_adapter import (  # noqa: E402
    RuntimeAdmissionConfig,
    append_jsonl_ledger,
    build_ledger_record,
    evaluate_probe_admission,
    read_jsonl_ledger,
)


REJECT_MATERIALIZER_SCHEMA_VERSION = "cost_gate_reject_materializer_v1"
VALID_ENGINE_MODES = {"paper", "demo", "live_demo", "live"}


@dataclass(frozen=True)
class RejectMaterializerConfig:
    """Controls which recorded rejects are materialized from PG."""

    engine_modes: tuple[str, ...] = ("demo", "live_demo")
    lookback_hours: int = 24
    limit: int = 10_000
    eligible_negative_edge_only: bool = True
    statement_timeout_ms: int = 180_000


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if value is None:
        return None
    if isinstance(value, dt.datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = dt.datetime.fromisoformat(text)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _dt_to_ms(value: Any) -> int:
    parsed = _parse_dt(value)
    return int(parsed.timestamp() * 1000) if parsed else 0


def _side_label(value: Any) -> str:
    text = _str(value)
    lowered = text.lower()
    if lowered in {"1", "1.0", "buy", "long"}:
        return "Buy"
    if lowered in {"-1", "-1.0", "sell", "short"}:
        return "Sell"
    return text


def validate_materializer_config(cfg: RejectMaterializerConfig) -> None:
    if not cfg.engine_modes:
        raise ValueError("at least one engine mode is required")
    bad_modes = [mode for mode in cfg.engine_modes if mode not in VALID_ENGINE_MODES]
    if bad_modes:
        raise ValueError(f"invalid engine mode(s): {bad_modes}")
    if cfg.lookback_hours < 1 or cfg.lookback_hours > 24 * 30:
        raise ValueError("--lookback-hours must be in [1, 720]")
    if cfg.limit < 1 or cfg.limit > 500_000:
        raise ValueError("--limit must be in [1, 500000]")
    if cfg.statement_timeout_ms < 1_000 or cfg.statement_timeout_ms > 900_000:
        raise ValueError("--pg-statement-timeout-ms must be in [1000, 900000]")


def build_cost_gate_reject_feature_sql(cfg: RejectMaterializerConfig) -> tuple[str, list[Any]]:
    """Return the read-only SQL that extracts recorded cost-gate reject rows."""
    validate_materializer_config(cfg)
    where = [
        "f.engine_mode = ANY(%s)",
        "f.ts >= now() - (%s::int * interval '1 hour')",
        "f.reject_reason_code LIKE 'cost_gate%%'",
    ]
    params: list[Any] = [list(cfg.engine_modes), cfg.lookback_hours]
    if cfg.eligible_negative_edge_only:
        where.append("f.reject_reason_code LIKE '%%negative_edge%%'")
    params.append(cfg.limit)
    sql = f"""
SELECT
    f.ts,
    (EXTRACT(EPOCH FROM f.ts) * 1000)::bigint AS ts_ms,
    f.context_id,
    f.engine_mode,
    f.strategy_name,
    f.symbol,
    CASE WHEN f.side = 1 THEN 'Buy' ELSE 'Sell' END AS side,
    f.reject_reason_code,
    d.last_price::float8 AS last_price
FROM learning.decision_features f
LEFT JOIN trading.decision_context_snapshots d
  ON d.context_id = f.context_id
WHERE {' AND '.join(where)}
ORDER BY f.ts DESC
LIMIT %s
"""
    return sql, params


def _cursor_rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in rows]


def connect_readonly_reject_materializer_pg(
    *,
    statement_timeout_ms_default: int = 180_000,
) -> Any:
    """Connect to PG for read-only reject materialization."""
    from helper_scripts.lib.pg_connect import connect_report_pg

    conn = connect_report_pg(
        "cost_gate_reject_materializer",
        statement_timeout_ms_default=statement_timeout_ms_default,
    )
    conn.rollback()
    conn.set_session(readonly=True, autocommit=True)
    return conn


def fetch_cost_gate_reject_feature_rows(
    conn: Any,
    cfg: RejectMaterializerConfig,
) -> list[dict[str, Any]]:
    """Fetch recorded cost-gate reject rows from local PG."""
    sql, params = build_cost_gate_reject_feature_sql(cfg)
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return _cursor_rows_to_dicts(cur)


def reject_feature_row_to_event(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize a PG feature row into the runtime adapter reject event shape."""
    ts_ms = _int(row.get("ts_ms")) or _dt_to_ms(row.get("ts"))
    event = {
        "strategy_name": row.get("strategy_name"),
        "symbol": _str(row.get("symbol")).upper(),
        "side": _side_label(row.get("side")),
        "reject_reason_code": row.get("reject_reason_code"),
        "engine_mode": _str(row.get("engine_mode")).lower(),
        "ts_ms": ts_ms,
        "context_id": row.get("context_id"),
    }
    last_price = _float(row.get("last_price"))
    if last_price is not None and last_price > 0.0:
        event["last_price"] = last_price
    return event


def _ledger_attempt_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _str(row.get("attempt_id"))
        for row in rows
        if _str(row.get("attempt_id"))
    }


def _decision_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        decision = _str(record.get("decision")) or "UNKNOWN"
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def build_materialized_reject_ledger_batch(
    plan: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    *,
    existing_ledger_rows: list[dict[str, Any]] | None = None,
    now_utc: dt.datetime | None = None,
    admission_cfg: RuntimeAdmissionConfig | None = None,
    risk_state: str = "NORMAL",
) -> dict[str, Any]:
    """Build idempotent admission-ledger rows from recorded reject features."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    existing = existing_ledger_rows or []
    seen_attempt_ids = _ledger_attempt_ids(existing)
    materialized: list[dict[str, Any]] = []
    skipped_existing = 0
    malformed_rows = 0

    for feature_row in feature_rows:
        event = reject_feature_row_to_event(feature_row)
        if not event.get("symbol") or _int(event.get("ts_ms")) <= 0:
            malformed_rows += 1
            continue
        decision = evaluate_probe_admission(
            plan,
            event,
            ledger_rows=existing + materialized,
            now_utc=now,
            cfg=admission_cfg,
            adapter_enabled=False,
            risk_state=risk_state,
        )
        record = build_ledger_record(decision)
        attempt_id = _str(record.get("attempt_id"))
        if attempt_id in seen_attempt_ids:
            skipped_existing += 1
            continue
        record["source"] = "materialized_from_pg_decision_features"
        record["source_schema"] = "learning.decision_features"
        record["source_context_id"] = event.get("context_id")
        record["materialized_at_utc"] = now.isoformat()
        record["boundary"] = (
            "reject materialization artifact only; PG source is read-only SELECT-only; "
            "no PG write, Bybit call, order, config, risk, auth, runtime mutation, "
            "or main Cost Gate lowering"
        )
        materialized.append(record)
        seen_attempt_ids.add(attempt_id)

    status = "MATERIALIZED_REJECT_ROWS_PRESENT" if materialized else "NO_NEW_REJECT_ROWS"
    return {
        "schema_version": REJECT_MATERIALIZER_SCHEMA_VERSION,
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "record_type": "cost_gate_reject_materialization_batch",
        "generated_at_utc": now.isoformat(),
        "status": status,
        "input_feature_row_count": len(feature_rows),
        "materialized_record_count": len(materialized),
        "skipped_existing_attempt_count": skipped_existing,
        "malformed_feature_row_count": malformed_rows,
        "decision_counts": _decision_counts(materialized),
        "records": materialized,
        "append_requested": False,
        "appended_to_ledger": False,
        "appended_record_count": 0,
        "boundary": (
            "artifact-only reject materialization; read-only PG SELECT when sourced "
            "from PG; no PG write, Bybit call, order, config, risk, auth, runtime "
            "mutation, order authority, promotion evidence, or main Cost Gate lowering"
        ),
    }


def append_materialized_records_to_ledger(ledger_path: Path, batch: dict[str, Any]) -> int:
    """Append materialized admission records to the JSONL ledger."""
    records = batch.get("records")
    if not isinstance(records, list):
        return 0
    appended = 0
    for record in records:
        if (
            isinstance(record, dict)
            and record.get("record_type") == PROBE_ADMISSION_DECISION_RECORD_TYPE
        ):
            append_jsonl_ledger(ledger_path, record)
            appended += 1
    batch["append_requested"] = True
    batch["appended_to_ledger"] = appended > 0
    batch["appended_record_count"] = appended
    return appended


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _read_json_or_jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".jsonl":
        rows = []
        for line_no, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed JSONL row at {path}:{line_no}") from exc
            if isinstance(payload, dict):
                rows.append(payload)
        return rows
    payload = json.loads(text)
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        rows = payload.get("rows") or payload.get("features") or payload.get("data")
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    raise ValueError(f"{path} did not contain rows")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-pg", action="store_true")
    source.add_argument("--source-rows", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--append-ledger", action="store_true")
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--include-non-negative-edge", action="store_true")
    parser.add_argument("--risk-state", default="NORMAL")
    parser.add_argument("--max-plan-age-hours", type=int, default=24)
    parser.add_argument("--min-failed-outcomes-to-disable", type=int, default=2)
    parser.add_argument("--min-outcome-net-positive-pct", type=float, default=50.0)
    parser.add_argument("--min-avg-net-bps", type=float, default=0.0)
    parser.add_argument("--pg-statement-timeout-ms", type=int, default=180_000)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = RejectMaterializerConfig(
        engine_modes=tuple(args.engine_modes or ("demo", "live_demo")),
        lookback_hours=args.lookback_hours,
        limit=args.limit,
        eligible_negative_edge_only=not args.include_non_negative_edge,
        statement_timeout_ms=args.pg_statement_timeout_ms,
    )
    validate_materializer_config(cfg)
    admission_cfg = RuntimeAdmissionConfig(
        max_plan_age_hours=args.max_plan_age_hours,
        min_failed_outcomes_to_disable=args.min_failed_outcomes_to_disable,
        min_outcome_net_positive_pct=args.min_outcome_net_positive_pct,
        min_avg_net_bps=args.min_avg_net_bps,
    )
    plan = _read_json(args.plan)
    existing = read_jsonl_ledger(args.ledger)

    if args.source_rows:
        feature_rows = _read_json_or_jsonl_rows(args.source_rows)
    else:
        conn = connect_readonly_reject_materializer_pg(
            statement_timeout_ms_default=cfg.statement_timeout_ms,
        )
        try:
            feature_rows = fetch_cost_gate_reject_feature_rows(conn, cfg)
        finally:
            close = getattr(conn, "close", None)
            if callable(close):
                close()

    batch = build_materialized_reject_ledger_batch(
        plan,
        feature_rows,
        existing_ledger_rows=existing,
        admission_cfg=admission_cfg,
        risk_state=args.risk_state,
    )
    if args.append_ledger:
        append_materialized_records_to_ledger(args.ledger, batch)
    if args.output:
        _write_json(args.output, batch)
    if args.print_json or not args.output:
        print(json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

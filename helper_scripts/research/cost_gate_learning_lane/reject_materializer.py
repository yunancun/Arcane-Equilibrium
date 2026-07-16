#!/usr/bin/env python3
"""Materialize recorded cost-gate rejects into the demo-learning ledger.

The Rust hot-path writer is the live capture path, but it is operator-gated.
This module recovers already-recorded PG ``learning.decision_features`` rejects
and recent pipeline-snapshot rejects into the same append-only JSONL contract
used by the runtime adapter. It only builds or appends artifact rows; it never
writes PG, calls Bybit, submits orders, lowers the main Cost Gate, or mutates
runtime config.
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
    ELIGIBLE_REJECT_REASON_CODE,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
)
from cost_gate_learning_lane.runtime_adapter import (  # noqa: E402
    ADMIT_DECISION,
    CANDIDATE_EVENT_CONTEXT_UNQUALIFIED_STATUS,
    RuntimeAdmissionConfig,
    append_jsonl_ledger,
    build_ledger_record,
    evaluate_probe_admission,
    normalize_reject_reason_code,
    project_learning_ledger_row,
    side_cell_key,
    validate_ledger_event_candidate_context,
)
from cost_gate_learning_lane.ledger_streaming import (  # noqa: E402
    LedgerProjectionLimitError,
    LedgerScanError,
    scan_retained_jsonl,
)


REJECT_MATERIALIZER_SCHEMA_VERSION = "cost_gate_reject_materializer_v1"
RETAINED_LEDGER_SCAN_DEFERRED_EXIT_CODE = 75
MAX_REJECT_RUNTIME_PROJECTED_ROWS = 250_000
MAX_REJECT_RUNTIME_PROJECTED_BYTES = 512 * 1024 * 1024
VALID_ENGINE_MODES = {"paper", "demo", "live_demo", "live"}


@dataclass(frozen=True)
class RejectMaterializerConfig:
    """Controls which recorded rejects are materialized from PG."""

    engine_modes: tuple[str, ...] = ("demo", "live_demo")
    lookback_hours: int = 24
    limit: int = 10_000
    eligible_negative_edge_only: bool = True
    statement_timeout_ms: int = 180_000


@dataclass(frozen=True)
class RejectLedgerProjection:
    """Exact dedup targets plus bounded runtime rows for selected plan cells."""

    runtime_rows: list[dict[str, Any]]
    existing_attempt_ids: set[str]
    existing_event_keys: set[str]
    quarantined_dedup_match_count: int


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _str(value: Any) -> str:
    return str(value or "").strip()


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        return [
            {**row, "_materializer_source": "pg_decision_features"}
            for row in _cursor_rows_to_dicts(cur)
        ]


def reject_feature_row_to_event(row: dict[str, Any]) -> dict[str, Any]:
    """把 feature row 轉成 reject event；prospective context 必 raw-first 驗證。"""
    has_candidate_context = "candidate_event_context" in row
    if (
        has_candidate_context
        and row.get("_materializer_source") != "explicit_source_rows"
    ):
        # 為什麼 fail-closed：PG/snapshot/unmarked 都是 historical recovery，
        # 即使 context 本身 hash 合法也可能是外來 graft，禁止升格為 prospective。
        raise ValueError("CANDIDATE_EVENT_CONTEXT_SOURCE_NOT_EXPLICIT")
    if has_candidate_context:
        # 為什麼先驗 raw outer：若先 upper/lower/int/side normalization，錯誤 graft
        # 會被修成看似一致；prospective lineage 禁止任何 trim/coerce/backfill。
        event = validate_ledger_event_candidate_context(
            {
                "strategy_name": row.get("strategy_name"),
                "symbol": row.get("symbol"),
                "side": row.get("side"),
                "context_id": row.get("context_id"),
                "signal_id": row.get("signal_id"),
                "engine_mode": row.get("engine_mode"),
                "ts_ms": row.get("ts_ms"),
                "candidate_event_context": row.get("candidate_event_context"),
            }
        )
        event["reject_reason_code"] = row.get("reject_reason_code")
        last_price = _float(row.get("last_price"))
        if last_price is not None and last_price > 0.0:
            event["last_price"] = last_price
        return event

    ts_ms = _int(row.get("ts_ms"))
    if ts_ms <= 0:
        ts_ms = _dt_to_ms(row.get("ts"))
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


def _snapshot_side(intent: dict[str, Any]) -> str:
    for key in ("side", "order_side"):
        if _str(intent.get(key)):
            return _side_label(intent.get(key))
    if isinstance(intent.get("is_long"), bool):
        return "Buy" if intent.get("is_long") is True else "Sell"
    intent_type = _str(intent.get("intent_type")).lower()
    if "long" in intent_type or "buy" in intent_type:
        return "Buy"
    if "short" in intent_type or "sell" in intent_type:
        return "Sell"
    return ""


def pipeline_snapshot_recent_intents_to_feature_rows(
    snapshot: dict[str, Any],
    *,
    engine_modes: tuple[str, ...] = ("demo", "live_demo"),
    limit: int = 10_000,
    snapshot_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Convert pipeline_snapshot recent cost-gate rejects to feature rows.

    This fallback closes the gap where the engine snapshot clearly shows
    cost-gate rejections, but PG decision-feature persistence is stale. Rows
    still pass through the same admission policy and append-only ledger
    de-duplication as PG materialized rows.
    """
    mode = _str(snapshot.get("trading_mode") or snapshot.get("engine_mode")).lower()
    if mode and mode not in engine_modes:
        return []
    recent = snapshot.get("recent_intents")
    if not isinstance(recent, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in recent:
        if not isinstance(item, dict):
            continue
        intent = item.get("intent")
        if not isinstance(intent, dict):
            continue
        result = _str(item.get("result"))
        normalized_reason = normalize_reject_reason_code(result)
        if normalized_reason != ELIGIBLE_REJECT_REASON_CODE:
            continue
        ts_ms = _int(item.get("timestamp_ms"))
        symbol = _str(intent.get("symbol")).upper()
        strategy = _str(intent.get("strategy") or intent.get("strategy_name"))
        side = _snapshot_side(intent)
        if not symbol or not strategy or not side or ts_ms <= 0:
            continue
        limit_price = _float(intent.get("limit_price") or intent.get("price"))
        context_parts = [
            "snapshot",
            str(ts_ms),
            strategy,
            symbol,
            side,
        ]
        if limit_price is not None:
            context_parts.append(f"{limit_price:.12g}")
        row: dict[str, Any] = {
            "ts_ms": ts_ms,
            "context_id": "|".join(context_parts),
            "engine_mode": mode or "demo",
            "strategy_name": strategy,
            "symbol": symbol,
            "side": side,
            "reject_reason_code": normalized_reason,
            "raw_reject_result": result,
            "_materializer_source": "pipeline_snapshot_recent_intents",
        }
        if snapshot_path is not None:
            row["_source_snapshot_path"] = str(snapshot_path)
        if limit_price is not None and limit_price > 0.0:
            row["last_price"] = limit_price
        rows.append(row)
    return rows[-limit:]


def _ledger_attempt_ids(rows: list[dict[str, Any]]) -> set[str]:
    return {
        _str(row.get("attempt_id"))
        for row in rows
        if _str(row.get("attempt_id"))
    }


def _event_equivalence_key(row: dict[str, Any]) -> str:
    event = _dict(row.get("event")) or row
    side_cell = _str(row.get("side_cell_key")) or side_cell_key(
        event.get("strategy_name") or event.get("strategy"),
        event.get("symbol"),
        event.get("side"),
    )
    ts_ms = 0
    for key in ("ts_ms", "attempt_ts_ms", "generated_at_ms"):
        ts_ms = _int(row.get(key) if row.get(key) is not None else event.get(key))
        if ts_ms > 0:
            break
    if not side_cell or ts_ms <= 0:
        return ""
    return f"{side_cell}|{ts_ms // 1000}"


def _ledger_event_equivalence_keys(rows: list[dict[str, Any]]) -> set[str]:
    return {
        key
        for key in (_event_equivalence_key(row) for row in rows)
        if key
    }


def _decision_counts(records: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        decision = _str(record.get("decision")) or "UNKNOWN"
        counts[decision] = counts.get(decision, 0) + 1
    return counts


def _feature_attempt_id(event: dict[str, Any]) -> str:
    for key in ("context_id", "signal_id"):
        value = _str(event.get(key))
        if value:
            return value
    return f"{side_cell_key(event.get('strategy_name'), event.get('symbol'), event.get('side'))}|{_int(event.get('ts_ms'))}"


def read_reject_materializer_ledger_projection(
    ledger_path: Path,
    *,
    plan: dict[str, Any],
    feature_rows: list[dict[str, Any]],
) -> RejectLedgerProjection:
    """Scan once and retain only exact materializer state."""
    target_attempt_ids: set[str] = set()
    target_event_keys: set[str] = set()
    for feature_row in feature_rows:
        event = reject_feature_row_to_event(feature_row)
        target_attempt_ids.add(_feature_attempt_id(event))
        event_key = _event_equivalence_key(event)
        if event_key:
            target_event_keys.add(event_key)
    target_side_cells = {
        _str(candidate.get("side_cell_key"))
        for candidate in plan.get("probe_candidates") or []
        if isinstance(candidate, dict) and _str(candidate.get("side_cell_key"))
    }
    runtime_rows: list[dict[str, Any]] = []
    runtime_bytes = 0
    existing_attempt_ids: set[str] = set()
    existing_event_keys: set[str] = set()
    quarantined_matches = 0

    def consume(raw_row: dict[str, Any]) -> None:
        nonlocal runtime_bytes, quarantined_matches
        outcome_row, dedup_row, quarantined = project_learning_ledger_row(raw_row)
        dedup_matched = False
        attempt_id = _str(dedup_row.get("attempt_id"))
        if attempt_id and attempt_id in target_attempt_ids:
            existing_attempt_ids.add(attempt_id)
            dedup_matched = True
        event_key = _event_equivalence_key(dedup_row)
        if event_key and event_key in target_event_keys:
            existing_event_keys.add(event_key)
            dedup_matched = True
        if quarantined and dedup_matched:
            quarantined_matches += 1
        if quarantined or outcome_row is None:
            return
        key = _str(outcome_row.get("side_cell_key")) or side_cell_key(
            _dict(outcome_row.get("event")).get("strategy_name")
            or _dict(outcome_row.get("event")).get("strategy"),
            _dict(outcome_row.get("event")).get("symbol"),
            _dict(outcome_row.get("event")).get("side"),
        )
        if key not in target_side_cells:
            return
        record_type = _str(outcome_row.get("record_type"))
        row_decision = _str(outcome_row.get("decision")) or _str(
            _dict(outcome_row.get("admission_decision")).get("decision")
        )
        if not (
            row_decision == ADMIT_DECISION
            or record_type in {"probe_outcome", "side_cell_disabled"}
        ):
            return
        encoded = json.dumps(
            outcome_row,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        runtime_bytes += len(encoded)
        if (
            len(runtime_rows) >= MAX_REJECT_RUNTIME_PROJECTED_ROWS
            or runtime_bytes > MAX_REJECT_RUNTIME_PROJECTED_BYTES
        ):
            raise LedgerProjectionLimitError(
                "REJECT_RUNTIME_PROJECTION_LIMIT_REACHED",
                path=ledger_path,
            )
        runtime_rows.append(outcome_row)

    scan_retained_jsonl(ledger_path, consume)
    return RejectLedgerProjection(
        runtime_rows=runtime_rows,
        existing_attempt_ids=existing_attempt_ids,
        existing_event_keys=existing_event_keys,
        quarantined_dedup_match_count=quarantined_matches,
    )


def build_materialized_reject_ledger_batch(
    plan: dict[str, Any],
    feature_rows: list[dict[str, Any]],
    *,
    existing_ledger_rows: list[dict[str, Any]] | None = None,
    dedup_ledger_rows: list[dict[str, Any]] | None = None,
    existing_attempt_ids: set[str] | None = None,
    existing_event_keys: set[str] | None = None,
    now_utc: dt.datetime | None = None,
    admission_cfg: RuntimeAdmissionConfig | None = None,
    risk_state: str = "NORMAL",
) -> dict[str, Any]:
    """Build idempotent admission-ledger rows from recorded reject features."""
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    existing = existing_ledger_rows or []
    dedup_existing = (
        dedup_ledger_rows if dedup_ledger_rows is not None else existing
    )
    seen_attempt_ids = (
        set(existing_attempt_ids)
        if existing_attempt_ids is not None
        else _ledger_attempt_ids(dedup_existing)
    )
    seen_event_keys = (
        set(existing_event_keys)
        if existing_event_keys is not None
        else _ledger_event_equivalence_keys(dedup_existing)
    )
    materialized: list[dict[str, Any]] = []
    skipped_existing = 0
    skipped_existing_event_key = 0
    malformed_rows = 0

    for feature_row in feature_rows:
        event = reject_feature_row_to_event(feature_row)
        if not event.get("symbol") or _int(event.get("ts_ms")) <= 0:
            malformed_rows += 1
            continue
        event_key = _event_equivalence_key(event)
        if event_key and event_key in seen_event_keys:
            skipped_existing += 1
            skipped_existing_event_key += 1
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
        if "candidate_event_context" not in event:
            # 為什麼顯式 unqualified：PG/snapshot 歷史資料沒有 prospective lineage，
            # 可保留作 counterfactual，但不得被後續 cold consumer 誤當合格 context。
            summary = _dict(record.get("candidate_summary"))
            summary["candidate_event_context_status"] = (
                CANDIDATE_EVENT_CONTEXT_UNQUALIFIED_STATUS
            )
            record["candidate_summary"] = summary
        attempt_id = _str(record.get("attempt_id"))
        if attempt_id in seen_attempt_ids:
            skipped_existing += 1
            continue
        materializer_source = _str(feature_row.get("_materializer_source"))
        if materializer_source == "pipeline_snapshot_recent_intents":
            record["source"] = "materialized_from_pipeline_snapshot_recent_intents"
            record["source_schema"] = "pipeline_snapshot.recent_intents"
            record["source_snapshot_path"] = feature_row.get("_source_snapshot_path")
        elif materializer_source == "explicit_source_rows":
            record["source"] = "materialized_from_explicit_source_rows"
            record["source_schema"] = "explicit_source_rows"
        elif materializer_source == "pg_decision_features":
            record["source"] = "materialized_from_pg_decision_features"
            record["source_schema"] = "learning.decision_features"
        else:
            # 保留既有 in-memory API 相容性；CLI PG 路徑在入口已顯式標記來源。
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
        if event_key:
            seen_event_keys.add(event_key)

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
        "skipped_existing_event_key_count": skipped_existing_event_key,
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


def _read_pipeline_snapshot_rows(
    path: Path,
    cfg: RejectMaterializerConfig,
) -> tuple[list[dict[str, Any]], str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], "missing"
    except json.JSONDecodeError as exc:
        return [], f"json_decode_error:{exc}"
    except OSError as exc:
        return [], f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return [], "json_not_object"
    return (
        pipeline_snapshot_recent_intents_to_feature_rows(
            payload,
            engine_modes=cfg.engine_modes,
            limit=cfg.limit,
            snapshot_path=path,
        ),
        None,
    )


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
    parser.add_argument(
        "--snapshot-json",
        type=Path,
        default=None,
        help=(
            "optional pipeline_snapshot.json fallback; recent cost-gate rejected "
            "intents are materialized in addition to the primary source"
        ),
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument("--append-ledger", action="store_true")
    parser.add_argument("--engine-mode", action="append", dest="engine_modes")
    parser.add_argument("--lookback-hours", type=int, default=24)
    parser.add_argument("--limit", type=int, default=10_000)
    parser.add_argument("--include-non-negative-edge", action="store_true")
    parser.add_argument("--risk-state", default="NORMAL")
    parser.add_argument("--max-plan-age-hours", type=int, default=24)
    # P2-7:CLI 默認與 RuntimeAdmissionConfig dataclass 同步(n≥8 才觸發 UCB-futility 禁用)。
    parser.add_argument("--min-failed-outcomes-to-disable", type=int, default=8)
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

    source_rows_count = 0
    pg_rows_count: int | None = None
    snapshot_rows: list[dict[str, Any]] = []
    snapshot_error: str | None = None

    if args.source_rows:
        feature_rows = [
            {**row, "_materializer_source": "explicit_source_rows"}
            for row in _read_json_or_jsonl_rows(args.source_rows)
        ]
        source_rows_count = len(feature_rows)
    else:
        conn = connect_readonly_reject_materializer_pg(
            statement_timeout_ms_default=cfg.statement_timeout_ms,
        )
        try:
            feature_rows = fetch_cost_gate_reject_feature_rows(conn, cfg)
            pg_rows_count = len(feature_rows)
        finally:
            close = getattr(conn, "close", None)
            if callable(close):
                close()

    if args.snapshot_json is not None:
        snapshot_rows, snapshot_error = _read_pipeline_snapshot_rows(
            args.snapshot_json,
            cfg,
        )
        feature_rows = feature_rows + snapshot_rows

    try:
        projection = read_reject_materializer_ledger_projection(
            args.ledger,
            plan=plan,
            feature_rows=feature_rows,
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

    batch = build_materialized_reject_ledger_batch(
        plan,
        feature_rows,
        existing_ledger_rows=projection.runtime_rows,
        existing_attempt_ids=projection.existing_attempt_ids,
        existing_event_keys=projection.existing_event_keys,
        admission_cfg=admission_cfg,
        risk_state=args.risk_state,
    )
    batch["source_counts"] = {
        "pg_input_feature_row_count": pg_rows_count,
        "source_rows_input_row_count": source_rows_count if args.source_rows else None,
        "snapshot_input_row_count": len(snapshot_rows),
    }
    batch["snapshot_json_path"] = str(args.snapshot_json) if args.snapshot_json else None
    batch["snapshot_json_error"] = snapshot_error
    if args.append_ledger:
        append_materialized_records_to_ledger(args.ledger, batch)
    if args.output:
        _write_json(args.output, batch)
    if args.print_json or not args.output:
        print(json.dumps(batch, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

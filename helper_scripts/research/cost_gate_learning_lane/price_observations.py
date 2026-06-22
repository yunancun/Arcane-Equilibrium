#!/usr/bin/env python3
"""Build local price observations for the cost-gate demo learning lane.

This module is artifact-only. It reads an append-only learning-lane ledger and
either a local price/kline export or read-only ``market.klines`` rows, then emits
normalized observations that can be passed to
``runtime_adapter.py --price-observations``. It does not write PG, call Bybit,
submit orders, or mutate runtime config.
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

from cost_gate_learning_lane.contract import (
    ADAPTER_SCHEMA_VERSION,
    ADMIT_DECISION,
    BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    PROBE_ADMISSION_DECISION_RECORD_TYPE,
    PROBE_OUTCOME_RECORD_TYPE,
)


ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PRICE_OBSERVATION_SCHEMA_VERSION = "cost_gate_demo_learning_lane_price_observations_v1"


@dataclass(frozen=True)
class PriceObservationBuildConfig:
    """Controls which ledger rows need price observations."""

    horizon_minutes: int = 60
    max_entry_delay_ms: int = 5 * 60_000
    include_blocked_signals: bool = True
    include_admitted_probes: bool = False


def validate_price_observation_config(cfg: PriceObservationBuildConfig) -> None:
    if cfg.horizon_minutes < 1 or cfg.horizon_minutes > 24 * 60:
        raise ValueError("--horizon-minutes must be in [1, 1440]")
    if cfg.max_entry_delay_ms < 0 or cfg.max_entry_delay_ms > 24 * 3_600_000:
        raise ValueError("--max-entry-delay-ms must be in [0, 86400000]")
    if not cfg.include_blocked_signals and not cfg.include_admitted_probes:
        raise ValueError("at least one of blocked signals or admitted probes must be included")


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


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
        for key in ("rows", "klines", "observations", "prices", "data"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    raise ValueError(f"{path} did not contain a JSON array or row container")


def read_ledger_rows(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL or JSON container ledger artifact."""
    if not path.exists():
        return []
    return _read_json_or_jsonl_rows(path)


def read_source_price_rows(path: Path) -> list[dict[str, Any]]:
    """Read local price rows from JSONL, JSON array, or row-container JSON."""
    return _read_json_or_jsonl_rows(path)


def validate_pg_timeframe(value: Any) -> str:
    text = _str(value)
    if not text or len(text) > 16 or not all(ch.isalnum() for ch in text):
        raise ValueError("--pg-timeframe must be a short alphanumeric kline timeframe")
    return text


def build_market_klines_observation_sql() -> str:
    """SQL used by the read-only PG Adapter to load local kline closes."""
    return """
SELECT
    k.symbol,
    (EXTRACT(EPOCH FROM k.ts) * 1000)::bigint AS ts_ms,
    k.close::float8 AS close
FROM market.klines k
WHERE k.symbol = %s
  AND k.timeframe = %s
  AND k.ts >= %s
  AND k.ts <= %s
ORDER BY k.ts ASC
"""


def _ms_to_utc_dt(value: int) -> dt.datetime:
    return dt.datetime.fromtimestamp(value / 1000.0, tz=dt.timezone.utc)


def _cursor_rows_to_dicts(cur: Any) -> list[dict[str, Any]]:
    rows = cur.fetchall()
    if not rows:
        return []
    if isinstance(rows[0], Mapping):
        return [dict(row) for row in rows]
    columns = [desc[0] for desc in cur.description]
    return [dict(zip(columns, row)) for row in rows]


def fetch_market_kline_price_rows(
    conn: Any,
    windows: list[dict[str, Any]],
    *,
    timeframe: str = "1m",
) -> list[dict[str, Any]]:
    """Fetch local PG ``market.klines`` rows for ledger-derived windows."""
    timeframe = validate_pg_timeframe(timeframe)
    windows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for window in windows:
        symbol = _str(window.get("symbol")).upper()
        start_ts_ms = _int(window.get("start_ts_ms"))
        end_ts_ms = _int(window.get("end_ts_ms"))
        if symbol and start_ts_ms > 0 and end_ts_ms >= start_ts_ms:
            windows_by_symbol.setdefault(symbol, []).append(window)
    if not windows_by_symbol:
        return []

    sql = build_market_klines_observation_sql()
    rows: list[dict[str, Any]] = []
    for symbol, symbol_windows in sorted(windows_by_symbol.items()):
        start_ts_ms = min(_int(window.get("start_ts_ms")) for window in symbol_windows)
        end_ts_ms = max(_int(window.get("end_ts_ms")) for window in symbol_windows)
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    symbol,
                    timeframe,
                    _ms_to_utc_dt(start_ts_ms),
                    _ms_to_utc_dt(end_ts_ms),
                ),
            )
            for row in _cursor_rows_to_dicts(cur):
                ts_ms = _int(row.get("ts_ms"))
                close = _float(row.get("close"))
                if ts_ms <= 0 or close is None or close <= 0.0:
                    continue
                rows.append(
                    {
                        "symbol": _str(row.get("symbol")).upper() or symbol,
                        "ts_ms": ts_ms,
                        "close": close,
                        "timeframe": timeframe,
                        "source": "pg_market_klines",
                    }
                )
    return rows


def connect_readonly_price_observation_pg(
    *,
    statement_timeout_ms_default: int = 180_000,
) -> Any:
    """Connect to PG for read-only price observation extraction."""
    from helper_scripts.lib.pg_connect import connect_report_pg

    conn = connect_report_pg(
        "cost_gate_price_observations",
        statement_timeout_ms_default=statement_timeout_ms_default,
    )
    conn.rollback()
    conn.set_session(readonly=True, autocommit=True)
    return conn


def _row_decision(row: dict[str, Any]) -> str:
    if row.get("decision"):
        return _str(row.get("decision"))
    decision = _dict(row.get("admission_decision"))
    return _str(decision.get("decision"))


def _ledger_side_cell(row: dict[str, Any]) -> str:
    if row.get("side_cell_key"):
        return _str(row.get("side_cell_key"))
    event = _dict(row.get("event"))
    return "|".join(
        [
            _str(event.get("strategy_name") or event.get("strategy")),
            _str(event.get("symbol")).upper(),
            _str(event.get("side")),
        ]
    )


def _ledger_ts_ms(row: dict[str, Any]) -> int:
    for key in ("ts_ms", "attempt_ts_ms", "generated_at_ms"):
        value = _int(row.get(key), default=0)
        if value > 0:
            return value
    event = _dict(row.get("event"))
    value = _int(event.get("ts_ms"), default=0)
    if value > 0:
        return value
    parsed = _parse_dt(row.get("generated_at_utc"))
    return int(parsed.timestamp() * 1000) if parsed else 0


def _attempt_id(row: dict[str, Any]) -> str:
    if row.get("attempt_id"):
        return _str(row.get("attempt_id"))
    event = _dict(row.get("event"))
    for key in ("context_id", "signal_id"):
        value = _str(event.get(key))
        if value:
            return value
    return "|".join([_ledger_side_cell(row), str(_ledger_ts_ms(row))])


def _existing_outcome_attempt_ids(
    ledger_rows: list[dict[str, Any]],
    *,
    record_type: str,
) -> set[str]:
    return {
        _attempt_id(row)
        for row in ledger_rows
        if _str(row.get("record_type")) == record_type and _attempt_id(row)
    }


def _is_blocked_admission(row: dict[str, Any], decision: str) -> bool:
    allowed = row.get("allowed_to_submit_order")
    return decision != ADMIT_DECISION and allowed is False


def _row_outcome_horizon_minutes(row: dict[str, Any], default_horizon_minutes: int) -> int:
    candidate = _dict(row.get("candidate_summary"))
    for value in (
        row.get("outcome_horizon_minutes"),
        row.get("learning_outcome_horizon_minutes"),
        candidate.get("outcome_horizon_minutes"),
        candidate.get("learning_outcome_horizon_minutes"),
    ):
        parsed = _int(value)
        if 1 <= parsed <= 24 * 60:
            return parsed
    return default_horizon_minutes


def required_price_observation_windows(
    ledger_rows: list[dict[str, Any]],
    *,
    cfg: PriceObservationBuildConfig | None = None,
) -> list[dict[str, Any]]:
    """Return ledger-derived symbol/time windows that still need price rows."""
    cfg = cfg or PriceObservationBuildConfig()
    validate_price_observation_config(cfg)
    blocked_done = _existing_outcome_attempt_ids(
        ledger_rows,
        record_type=BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE,
    )
    probe_done = _existing_outcome_attempt_ids(
        ledger_rows,
        record_type=PROBE_OUTCOME_RECORD_TYPE,
    )
    windows: list[dict[str, Any]] = []

    for row in ledger_rows:
        if _str(row.get("record_type")) != PROBE_ADMISSION_DECISION_RECORD_TYPE:
            continue
        event = _dict(row.get("event"))
        symbol = _str(event.get("symbol")).upper()
        side = _str(event.get("side"))
        event_ts_ms = _ledger_ts_ms(row)
        if not symbol or event_ts_ms <= 0:
            continue
        decision = _row_decision(row)
        attempt_id = _attempt_id(row)
        target_record_type: str | None = None
        if (
            cfg.include_blocked_signals
            and _is_blocked_admission(row, decision)
            and attempt_id not in blocked_done
        ):
            target_record_type = BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
        elif (
            cfg.include_admitted_probes
            and decision == ADMIT_DECISION
            and attempt_id not in probe_done
        ):
            target_record_type = PROBE_OUTCOME_RECORD_TYPE
        if target_record_type is None:
            continue
        horizon_minutes = _row_outcome_horizon_minutes(row, cfg.horizon_minutes)
        horizon_ms = horizon_minutes * 60_000
        exit_target_ts_ms = event_ts_ms + horizon_ms
        windows.append(
            {
                "schema_version": PRICE_OBSERVATION_SCHEMA_VERSION,
                "record_type": "price_observation_window",
                "attempt_id": attempt_id,
                "target_outcome_record_type": target_record_type,
                "source_admission_decision": decision,
                "allowed_to_submit_order": row.get("allowed_to_submit_order"),
                "side_cell_key": row.get("side_cell_key") or _ledger_side_cell(row),
                "symbol": symbol,
                "side": side,
                "event_ts_ms": event_ts_ms,
                "start_ts_ms": event_ts_ms,
                "exit_target_ts_ms": exit_target_ts_ms,
                "end_ts_ms": exit_target_ts_ms + cfg.max_entry_delay_ms,
                "horizon_minutes": horizon_minutes,
                "default_horizon_minutes": cfg.horizon_minutes,
                "max_entry_delay_ms": cfg.max_entry_delay_ms,
                "candidate_summary": row.get("candidate_summary") or {},
            }
        )

    return sorted(
        windows,
        key=lambda row: (
            _str(row.get("symbol")),
            _int(row.get("start_ts_ms")),
            _str(row.get("attempt_id")),
            _str(row.get("target_outcome_record_type")),
        ),
    )


def _price_row_ts_ms(row: dict[str, Any]) -> int:
    for key in (
        "ts_ms",
        "close_ts_ms",
        "close_time_ms",
        "end_ts_ms",
        "timestamp_ms",
        "start_ts_ms",
        "open_time_ms",
        "open_ts_ms",
    ):
        value = _int(row.get(key), default=0)
        if value > 0:
            return value
    parsed = _parse_dt(
        row.get("ts_utc")
        or row.get("timestamp")
        or row.get("time")
        or row.get("open_time")
        or row.get("close_time")
    )
    return int(parsed.timestamp() * 1000) if parsed else 0


def _price_row_price(row: dict[str, Any]) -> float | None:
    for key in ("close", "price", "close_price", "last_price", "mark_price"):
        value = _float(row.get(key))
        if value is not None and value > 0.0:
            return value
    return None


def build_price_observations_from_rows(
    price_rows: list[dict[str, Any]],
    windows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Filter and normalize local price rows for the requested windows."""
    if not windows:
        return []
    windows_by_symbol: dict[str, list[dict[str, Any]]] = {}
    for window in windows:
        symbol = _str(window.get("symbol")).upper()
        if symbol:
            windows_by_symbol.setdefault(symbol, []).append(window)

    out: list[dict[str, Any]] = []
    seen: set[tuple[str, int, float]] = set()
    for row in price_rows:
        symbol = _str(row.get("symbol")).upper()
        if not symbol or symbol not in windows_by_symbol:
            continue
        ts_ms = _price_row_ts_ms(row)
        price = _price_row_price(row)
        if ts_ms <= 0 or price is None:
            continue
        if not any(
            _int(window.get("start_ts_ms")) <= ts_ms <= _int(window.get("end_ts_ms"))
            for window in windows_by_symbol[symbol]
        ):
            continue
        key = (symbol, ts_ms, price)
        if key in seen:
            continue
        seen.add(key)
        observation = {
            "schema_version": PRICE_OBSERVATION_SCHEMA_VERSION,
            "record_type": "price_observation",
            "symbol": symbol,
            "ts_ms": ts_ms,
            "close": price,
            "source": _str(row.get("source")) or "local_price_row",
        }
        timeframe = _str(row.get("timeframe"))
        if timeframe:
            observation["timeframe"] = timeframe
        out.append(observation)

    return sorted(out, key=lambda row: (_str(row.get("symbol")), _int(row.get("ts_ms"))))


def build_price_observation_artifact(
    ledger_rows: list[dict[str, Any]],
    price_rows: list[dict[str, Any]],
    *,
    now_utc: dt.datetime | None = None,
    cfg: PriceObservationBuildConfig | None = None,
) -> dict[str, Any]:
    """Build a JSON artifact containing windows and normalized observations."""
    cfg = cfg or PriceObservationBuildConfig()
    windows = required_price_observation_windows(ledger_rows, cfg=cfg)
    observations = build_price_observations_from_rows(price_rows, windows)
    generated_at = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    return {
        "schema_version": PRICE_OBSERVATION_SCHEMA_VERSION,
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
        "generated_at_utc": generated_at.isoformat(),
        "record_type": "price_observation_batch",
        "window_count": len(windows),
        "observation_count": len(observations),
        "windows": windows,
        "observations": observations,
        "boundary": (
            "price observation artifact only; no PG, Bybit, order, config, "
            "risk, auth, or runtime mutation"
        ),
    }


def write_price_observation_artifact(path: Path, artifact: dict[str, Any]) -> None:
    """Write either a JSON artifact or JSONL observations for runtime_adapter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    observations = artifact.get("observations")
    if path.suffix == ".jsonl":
        rows = observations if isinstance(observations, list) else []
        path.write_text(
            "".join(
                json.dumps(row, ensure_ascii=False, sort_keys=True, default=str) + "\n"
                for row in rows
                if isinstance(row, dict)
            ),
            encoding="utf-8",
        )
        return
    path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--source-prices", type=Path)
    source.add_argument("--source-pg", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--horizon-minutes", type=int, default=60)
    parser.add_argument("--max-entry-delay-ms", type=int, default=5 * 60_000)
    parser.add_argument("--pg-timeframe", default="1m")
    parser.add_argument("--pg-statement-timeout-ms", type=int, default=180_000)
    parser.add_argument("--include-admitted", action="store_true")
    parser.add_argument("--no-blocked", action="store_true")
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    cfg = PriceObservationBuildConfig(
        horizon_minutes=args.horizon_minutes,
        max_entry_delay_ms=args.max_entry_delay_ms,
        include_blocked_signals=not args.no_blocked,
        include_admitted_probes=args.include_admitted,
    )
    validate_price_observation_config(cfg)
    ledger_rows = read_ledger_rows(args.ledger)
    price_source = "local_price_file"
    if args.source_pg:
        validate_pg_timeframe(args.pg_timeframe)
        windows = required_price_observation_windows(ledger_rows, cfg=cfg)
        if windows:
            conn = connect_readonly_price_observation_pg(
                statement_timeout_ms_default=args.pg_statement_timeout_ms,
            )
            try:
                price_rows = fetch_market_kline_price_rows(
                    conn,
                    windows,
                    timeframe=args.pg_timeframe,
                )
            finally:
                conn.close()
        else:
            price_rows = []
        price_source = "pg_market_klines"
    else:
        if args.source_prices is None:
            raise ValueError("--source-prices is required unless --source-pg is used")
        price_rows = read_source_price_rows(args.source_prices)
    artifact = build_price_observation_artifact(
        ledger_rows,
        price_rows,
        cfg=cfg,
    )
    artifact["price_source"] = price_source
    if args.source_pg:
        artifact["pg_timeframe"] = args.pg_timeframe
    if args.output:
        write_price_observation_artifact(args.output, artifact)
    if args.print_json or not args.output:
        print(json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

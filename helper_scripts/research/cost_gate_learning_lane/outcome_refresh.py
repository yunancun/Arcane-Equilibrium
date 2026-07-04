#!/usr/bin/env python3
"""One-command outcome refresh for the cost-gate demo learning lane.

This module keeps the learning lane artifact-only. It reads the append-only
ledger, loads local price rows or read-only ``market.klines`` rows, builds
missing outcome rows, and optionally appends them back to the same JSONL ledger.
It never writes PG, calls Bybit, submits orders, or mutates runtime config.
"""

from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any


RESEARCH_ROOT = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[3]
for _path in (str(RESEARCH_ROOT), str(ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from cost_gate_learning_lane.contract import ADAPTER_SCHEMA_VERSION
from cost_gate_learning_lane.outcome_writer import (
    ProbeOutcomeConfig,
    build_blocked_signal_outcome_records,
    build_probe_outcome_records,
    validate_outcome_config,
)
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
from cost_gate_learning_lane.runtime_adapter import append_jsonl_ledger, read_jsonl_ledger


OUTCOME_REFRESH_RECORD_TYPE = "cost_gate_outcome_refresh_batch"
OUTCOME_REFRESH_SCHEMA_VERSION = "cost_gate_demo_learning_lane_outcome_refresh_v1"


@dataclass(frozen=True)
class OutcomeRefreshSelection:
    """Which outcome rows this refresh should build."""

    record_blocked_outcomes: bool = False
    record_probe_outcomes: bool = False


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
    outcome_rows = probe_outcomes + blocked_outcomes

    return {
        "schema_version": OUTCOME_REFRESH_SCHEMA_VERSION,
        "adapter_schema_version": ADAPTER_SCHEMA_VERSION,
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
        "boundary": (
            "outcome refresh artifact only; PG source is read-only SELECT-only; "
            "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
        ),
    }


def append_refresh_outcomes_to_ledger(ledger_path: Path, batch: dict[str, Any]) -> int:
    """Append built outcome rows from a refresh batch to the JSONL ledger."""
    rows = batch.get("outcomes")
    if not isinstance(rows, list):
        return 0
    appended = 0
    for row in rows:
        if isinstance(row, dict):
            append_jsonl_ledger(ledger_path, row)
            appended += 1
    batch["append_requested"] = True
    batch["appended_to_ledger"] = appended > 0
    batch["appended_outcome_count"] = appended
    return appended


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
) -> dict[str, Any]:
    """Build a refresh batch from in-memory price rows and optionally append it."""
    ledger_rows = read_jsonl_ledger(ledger_path)
    batch = build_cost_gate_outcome_refresh_batch(
        ledger_rows,
        price_rows,
        now_utc=now_utc,
        selection=selection,
        outcome_cfg=outcome_cfg,
        price_source=price_source,
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

    ledger_rows = read_jsonl_ledger(args.ledger)
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

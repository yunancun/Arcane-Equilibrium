"""REF-21 full-chain replay run orchestration routes.

This module owns the one-click full-chain run entrypoint. It prepares one
multi-symbol S2 public-data fixture, registers one manifest per requested
strategy, and starts the existing dedicated Rust ``replay_runner`` subprocess
for each manifest. It does not run scanner, strategy, risk, or execution logic
inside the Control API worker process.
"""

import asyncio
import bisect
import hashlib
import json
import logging
import os
import time
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, validator

from . import main_legacy as base
from . import replay_execution_calibration as _ec
from .auth import require_scope_and_operator
from .db_pool import get_pg_conn
from .replay_quick_routes import (
    _DEFAULT_FULL_CHAIN_STRATEGIES,
    _STRATEGY_RE,
    ReplayFullChainPrepareRequest,
    _estimate_bar_count,
    _fetch_current_risk_config,
    _fetch_current_scanner_snapshot,
    _fetch_full_chain_events,
    _fetch_full_chain_strategy_params,
    _max_full_chain_bars_per_symbol,
    _max_full_chain_events,
    _require_full_chain_bulk_prod_ip_allowed,
    _resolve_full_chain_symbols,
    _rh,
    _to_utc_ms,
    _write_full_chain_s2_fixture,
)

try:
    from ..replay import canary_writer as _cw  # type: ignore[no-redef]
    from ..replay import experiment_registry as _er  # type: ignore[no-redef]
    from ..replay import manifest_signer as _ms  # type: ignore[no-redef]
    from ..replay import run_finalize_route as _fr  # type: ignore[no-redef]
    from ..replay import run_route as _rrun  # type: ignore[no-redef]
    from ..replay import simulated_fills_writer as _sfw  # type: ignore[no-redef]
    from ..replay.replay_models import ReplayRunRequest
except ImportError:
    from replay import canary_writer as _cw  # type: ignore[no-redef]
    from replay import experiment_registry as _er  # type: ignore[no-redef]
    try:
        from replay import manifest_signer as _ms  # type: ignore[no-redef]
    except ImportError:
        _ms = None  # type: ignore[assignment]
    from replay import run_finalize_route as _fr  # type: ignore[no-redef]
    from replay import run_route as _rrun  # type: ignore[no-redef]
    from replay import simulated_fills_writer as _sfw  # type: ignore[no-redef]
    from replay.replay_models import ReplayRunRequest


logger = logging.getLogger(__name__)

full_chain_replay_router = APIRouter(
    prefix="/api/v1/replay",
    tags=["Replay Full Chain / 全鏈條回測"],
)

_STATEMENT_TIMEOUT_MS = _rh.DEFAULT_PG_STATEMENT_TIMEOUT_MS
_FULL_CHAIN_SYMBOL_SENTINEL = "FULL_CHAIN"
_REPLAY_LIMITER = base.limiter
_FULL_CHAIN_HALF_LIFE_DAYS = 7.0
_FULL_CHAIN_EMBARGO_DAYS = 14.0
_BBO_ANCHOR_S1_COVERAGE_RATIO = 0.80


class ReplayFullChainRunRequest(ReplayFullChainPrepareRequest):
    """POST /api/v1/replay/full-chain/run body."""

    strategies: Optional[list[str]] = Field(
        default=None,
        description="Strategy list. Defaults to all REF-21 registered strategies.",
    )
    auto_finalize_completed: bool = Field(
        default=True,
        description=(
            "If replay_runner exits within the spawn poll grace, finalize "
            "the report in the same request."
        ),
    )

    @validator("strategies")
    def _strategies_allowlist(
        cls,
        value: Optional[list[str]],
    ) -> Optional[list[str]]:
        if value is None:
            return None
        normalised: list[str] = []
        seen: set[str] = set()
        allowed = set(_DEFAULT_FULL_CHAIN_STRATEGIES)
        for item in value:
            strategy = str(item).strip()
            if not _STRATEGY_RE.match(strategy):
                raise ValueError(
                    "strategies must be 1-64 chars: A-Z a-z 0-9 _ ."
                )
            if strategy not in allowed:
                raise ValueError(
                    "unsupported REF-21 full-chain strategy: " + strategy
                )
            if strategy not in seen:
                normalised.append(strategy)
                seen.add(strategy)
        if not normalised:
            raise ValueError("strategies cannot be empty")
        return normalised


def _require_replay_write(actor: base.AuthenticatedActor) -> None:
    require_scope_and_operator(actor, "replay:write")


def _replay_rate_limit_key(request: Request) -> str:
    state_actor = getattr(getattr(request, "state", None), "actor", None)
    if state_actor is not None:
        actor_id = getattr(state_actor, "actor_id", None)
        if actor_id:
            return f"actor:{actor_id}"
    client = getattr(request, "client", None)
    return f"ip:{client.host}" if client is not None else "ip:unknown"


def _max_full_chain_run_strategies() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_FULL_CHAIN_MAX_STRATEGIES", "5")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 5
    return max(1, min(parsed, len(_DEFAULT_FULL_CHAIN_STRATEGIES)))


def _canonical_sha256(payload: Any) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _iso_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _cursor_fetchall(cur: Any) -> list[Any]:
    rows = cur.fetchall()
    return list(rows or [])


def _microstructure_overlay_enabled() -> bool:
    raw = os.environ.get("OPENCLAW_REPLAY_MICROSTRUCTURE_OVERLAY_ENABLED", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def _microstructure_max_staleness_ms() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_MICROSTRUCTURE_MAX_STALENESS_MS", "120000")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 120_000
    return max(0, min(parsed, 3_600_000))


def _fetch_microstructure_overlays_sync(
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    """Fetch locally recorded ticker BBO rows for fixture enrichment.

    Bybit's public ticker/orderbook REST endpoints are current snapshots, not
    historical endpoints. REF-21 only enriches historical fixtures from locally
    recorded `market.market_tickers` rows and labels the coverage explicitly.
    """
    if not _microstructure_overlay_enabled():
        return {
            "status": "disabled",
            "source": "market.market_tickers",
            "records": {},
            "reason": "env_disabled",
        }
    if not symbols:
        return {
            "status": "empty",
            "source": "market.market_tickers",
            "records": {},
            "reason": "empty_symbols",
        }
    try:
        with get_pg_conn() as conn:
            if conn is None:
                return {
                    "status": "unavailable",
                    "source": "market.market_tickers",
                    "records": {},
                    "reason": "pg_unavailable",
                }
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s;", (_STATEMENT_TIMEOUT_MS,))
            cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1 FROM information_schema.tables
                    WHERE table_schema = 'market'
                      AND table_name = 'market_tickers'
                );
                """
            )
            if not bool(cur.fetchone()[0]):
                return {
                    "status": "unavailable",
                    "source": "market.market_tickers",
                    "records": {},
                    "reason": "table_absent",
                }
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'market'
                  AND table_name = 'market_tickers';
                """
            )
            ticker_columns = {str(row[0]) for row in _cursor_fetchall(cur)}
            funding_expr = (
                "funding_rate"
                if "funding_rate" in ticker_columns
                else "NULL::real AS funding_rate"
            )
            cur.execute(
                f"""
                SELECT
                    symbol,
                    floor(extract(epoch from ts) * 1000)::bigint AS ts_ms,
                    best_bid,
                    best_ask,
                    bid_size,
                    ask_size,
                    spread_bps,
                    volume_24h,
                    turnover_24h,
                    index_price,
                    open_interest,
                    {funding_expr}
                FROM market.market_tickers
                WHERE symbol = ANY(%s)
                  AND ts >= to_timestamp(%s / 1000.0)
                  AND ts <= to_timestamp(%s / 1000.0)
                  AND best_bid IS NOT NULL
                  AND best_ask IS NOT NULL
                ORDER BY symbol, ts ASC;
                """,
                (symbols, start_ms - _microstructure_max_staleness_ms(), end_ms),
            )
            rows = _cursor_fetchall(cur)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "source": "market.market_tickers",
            "records": {},
            "reason": type(exc).__name__,
            "message": str(exc),
        }

    records: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        symbol = str(row[0]).strip().upper()
        best_bid = float(row[2]) if row[2] is not None else None
        best_ask = float(row[3]) if row[3] is not None else None
        if (
            not symbol
            or best_bid is None
            or best_ask is None
            or best_bid <= 0
            or best_ask <= 0
            or best_bid > best_ask
        ):
            continue
        records.setdefault(symbol, []).append({
            "ts_ms": int(row[1]),
            "best_bid": best_bid,
            "best_ask": best_ask,
            "bid_size": float(row[4]) if row[4] is not None else None,
            "ask_size": float(row[5]) if row[5] is not None else None,
            "spread_bps": float(row[6]) if row[6] is not None else None,
            "volume_24h": float(row[7]) if row[7] is not None else None,
            "turnover_24h": float(row[8]) if row[8] is not None else None,
            "index_price": float(row[9]) if row[9] is not None else None,
            "open_interest": float(row[10]) if row[10] is not None else None,
            "funding_rate": float(row[11]) if row[11] is not None else None,
        })
    record_count = sum(len(items) for items in records.values())
    return {
        "status": "ok" if record_count else "empty",
        "source": "market.market_tickers",
        "records": records,
        "record_count": record_count,
        "symbol_count": len(records),
        "reason": None if record_count else "no_bbo_rows_for_window",
    }


def _apply_microstructure_overlays(
    events: list[dict[str, Any]],
    overlay: dict[str, Any],
    *,
    max_staleness_ms: int,
) -> dict[str, Any]:
    records_by_symbol = overlay.get("records") if isinstance(overlay, dict) else None
    if not isinstance(records_by_symbol, dict):
        return {
            "status": "unavailable",
            "source": "market.market_tickers",
            "event_count": len(events),
            "enriched_event_count": 0,
            "reason": "records_missing",
        }

    timestamps: dict[str, list[int]] = {}
    for symbol, rows in records_by_symbol.items():
        if not isinstance(rows, list):
            continue
        rows.sort(key=lambda item: int(item.get("ts_ms", 0)))
        timestamps[str(symbol)] = [int(item.get("ts_ms", 0)) for item in rows]

    enriched = 0
    field_counts: dict[str, int] = {
        "best_bid": 0,
        "best_ask": 0,
        "turnover_24h": 0,
        "volume_24h": 0,
        "index_price": 0,
        "open_interest": 0,
        "funding_rate": 0,
    }
    for event in events:
        symbol = str(event.get("symbol") or "").upper()
        event_ts = int(event.get("ts_ms") or 0)
        rows = records_by_symbol.get(symbol)
        ts_values = timestamps.get(symbol)
        if not rows or not ts_values:
            continue
        idx = bisect.bisect_right(ts_values, event_ts) - 1
        if idx < 0:
            continue
        record = rows[idx]
        age_ms = event_ts - int(record["ts_ms"])
        if age_ms < 0 or age_ms > max_staleness_ms:
            continue
        event["best_bid"] = record["best_bid"]
        event["best_ask"] = record["best_ask"]
        field_counts["best_bid"] += 1
        field_counts["best_ask"] += 1
        if record.get("bid_size") is not None:
            event["bid_size"] = record["bid_size"]
        if record.get("ask_size") is not None:
            event["ask_size"] = record["ask_size"]
        if record.get("spread_bps") is not None:
            event["spread_bps"] = record["spread_bps"]
        for field in (
            "turnover_24h",
            "volume_24h",
            "index_price",
            "open_interest",
            "funding_rate",
        ):
            value = record.get(field)
            if value is None:
                continue
            try:
                parsed = float(value)
            except (TypeError, ValueError):
                continue
            if parsed == parsed:
                event[field] = parsed
                field_counts[field] += 1
        event["microstructure_source"] = "market.market_tickers"
        enriched += 1

    field_coverage = {
        field: (count / len(events)) if events else 0.0
        for field, count in field_counts.items()
    }
    bbo_anchor_event_count = min(
        field_counts.get("best_bid", 0),
        field_counts.get("best_ask", 0),
    )
    bbo_anchor_coverage_ratio = (
        bbo_anchor_event_count / len(events)
        if events
        else 0.0
    )
    return {
        "status": "ok" if enriched else "empty",
        "source": "market.market_tickers",
        "event_count": len(events),
        "enriched_event_count": enriched,
        "coverage_ratio": (enriched / len(events)) if events else 0.0,
        "bbo_anchor_status": (
            "available" if bbo_anchor_event_count else "unavailable"
        ),
        "bbo_anchor_event_count": bbo_anchor_event_count,
        "bbo_anchor_coverage_ratio": bbo_anchor_coverage_ratio,
        "field_counts": field_counts,
        "field_coverage": field_coverage,
        "max_staleness_ms": max_staleness_ms,
        "reason": None if enriched else "no_matching_bbo_rows",
    }


def _instrument_specs_from_universe(
    historical_universe: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    entries = historical_universe.get("entries")
    if not isinstance(entries, list):
        return specs
    for item in entries:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        specs[symbol] = {
            "tick_size": item.get("tick_size"),
            "qty_step": item.get("qty_step"),
            "min_notional": item.get("min_notional"),
            "source": "market.symbol_universe_snapshots",
        }
    return specs


def _apply_instrument_specs(
    events: list[dict[str, Any]],
    specs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not specs:
        return {
            "status": "empty",
            "source": "market.symbol_universe_snapshots",
            "event_count": len(events),
            "tick_size_event_count": 0,
            "coverage_ratio": 0.0,
            "reason": "no_specs",
        }
    tick_size_count = 0
    for event in events:
        symbol = str(event.get("symbol") or "").strip().upper()
        spec = specs.get(symbol)
        if not spec:
            continue
        value = spec.get("tick_size")
        if value is None:
            continue
        try:
            tick_size = float(value)
        except (TypeError, ValueError):
            continue
        if tick_size > 0 and tick_size == tick_size:
            event["tick_size"] = tick_size
            tick_size_count += 1
    return {
        "status": "ok" if tick_size_count else "empty",
        "source": "market.symbol_universe_snapshots",
        "event_count": len(events),
        "tick_size_event_count": tick_size_count,
        "coverage_ratio": (tick_size_count / len(events)) if events else 0.0,
        "reason": None if tick_size_count else "no_tick_size_for_events",
    }


def _build_input_fidelity_summary(
    *,
    microstructure_stats: dict[str, Any],
    instrument_stats: dict[str, Any],
    edge_snapshot: dict[str, Any],
    execution_calibration: dict[str, Any],
) -> dict[str, Any]:
    field_coverage = microstructure_stats.get("field_coverage")
    if not isinstance(field_coverage, dict):
        field_coverage = {}
    return {
        "indicators": {
            "status": "runner_derived",
            "source": "fixture_ohlcv",
            "warmup_bars": 30,
        },
        "signals": {
            "status": "runner_derived",
            "source": "fixture_ohlcv_indicator_snapshot",
        },
        "microstructure": {
            "status": microstructure_stats.get("status"),
            "source": microstructure_stats.get("source"),
            "coverage_ratio": microstructure_stats.get("coverage_ratio", 0.0),
            "bbo_anchor_status": microstructure_stats.get("bbo_anchor_status"),
            "bbo_anchor_event_count": microstructure_stats.get(
                "bbo_anchor_event_count",
                0,
            ),
            "bbo_anchor_coverage_ratio": microstructure_stats.get(
                "bbo_anchor_coverage_ratio",
                0.0,
            ),
            "field_coverage": field_coverage,
        },
        "instrument_specs": {
            "status": instrument_stats.get("status"),
            "source": instrument_stats.get("source"),
            "tick_size_coverage_ratio": instrument_stats.get("coverage_ratio", 0.0),
        },
        "edge_snapshot": {
            "status": edge_snapshot.get("status"),
            "source": edge_snapshot.get("source"),
            "cell_count": edge_snapshot.get("cell_count", 0),
            "cutoff_iso": edge_snapshot.get("cutoff_iso"),
        },
        "execution_calibration": {
            "status": execution_calibration.get("status"),
            "source": execution_calibration.get("source"),
            "confidence": execution_calibration.get("execution_confidence"),
            "slippage_sample_count": execution_calibration.get(
                "slippage_sample_count",
                0,
            ),
            "recommended_taker_slippage_bps": execution_calibration.get(
                "recommended_taker_slippage_bps"
            ),
            "risk_overlay_applied": (
                execution_calibration.get("risk_overlay") or {}
            ).get("applied", False),
            "maker_fill_probability_status": execution_calibration.get(
                "maker_fill_probability_status"
            ),
            "maker_fill_confidence": execution_calibration.get(
                "maker_fill_confidence"
            ),
            "maker_order_sample_count": execution_calibration.get(
                "maker_order_sample_count",
                0,
            ),
            "maker_any_fill_probability": execution_calibration.get(
                "maker_any_fill_probability",
                0.0,
            ),
            "recommended_maker_fill_probability_cap": execution_calibration.get(
                "recommended_maker_fill_probability_cap",
            ),
        },
    }


def _fetch_historical_universe_snapshot_sync(
    *,
    category: str,
    start_ms: int,
    end_ms: int,
    max_symbols: int,
) -> dict[str, Any]:
    """Read V058 as the default universe source for current-scanner replay."""
    try:
        with get_pg_conn() as conn:
            if conn is None:
                return {
                    "status": "unavailable",
                    "source": "v058_symbol_universe_snapshots",
                    "reason": "pg_unavailable",
                    "symbols": [],
                }
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s;", (_STATEMENT_TIMEOUT_MS,))
            cur.execute("SELECT to_regclass('market.market_tickers') IS NOT NULL;")
            has_market_tickers = bool(cur.fetchone()[0])
            latest_ticker_cte = (
                """
                latest_ticker AS (
                    SELECT DISTINCT ON (mt.symbol)
                        mt.symbol,
                        mt.turnover_24h
                    FROM market.market_tickers mt
                    JOIN candidate_symbols c ON c.symbol = mt.symbol
                    WHERE mt.ts <= to_timestamp(%s / 1000.0)
                    ORDER BY mt.symbol, mt.ts DESC
                )
                """
                if has_market_tickers
                else """
                latest_ticker AS (
                    SELECT NULL::text AS symbol, NULL::real AS turnover_24h
                    WHERE false
                )
                """
            )
            cur.execute(
                f"""
                WITH candidate_symbols AS (
                    SELECT DISTINCT symbol
                    FROM market.symbol_universe_snapshots
                    WHERE exchange = 'bybit'
                      AND category = %s
                      AND ts <= to_timestamp(%s / 1000.0)
                      AND (listed_at IS NULL OR listed_at <= to_timestamp(%s / 1000.0))
                      AND (delisted_at IS NULL OR delisted_at >= to_timestamp(%s / 1000.0))
                ),
                latest AS (
                    SELECT DISTINCT ON (s.symbol)
                        s.symbol,
                        s.ts,
                        s.status,
                        s.base_coin,
                        s.quote_coin,
                        s.contract_type,
                        s.tick_size,
                        s.qty_step,
                        s.min_notional,
                        s.listed_at,
                        s.delisted_at,
                        s.is_delisted_at_asof,
                        s.source_uri
                    FROM market.symbol_universe_snapshots s
                    JOIN candidate_symbols c ON c.symbol = s.symbol
                    WHERE s.exchange = 'bybit'
                      AND s.category = %s
                      AND s.ts <= to_timestamp(%s / 1000.0)
                    ORDER BY s.symbol, s.ts DESC
                ),
                {latest_ticker_cte}
                SELECT
                    latest.symbol,
                    latest.ts,
                    latest.status,
                    latest.base_coin,
                    latest.quote_coin,
                    latest.contract_type,
                    latest.tick_size,
                    latest.qty_step,
                    latest.min_notional,
                    latest.listed_at,
                    latest.delisted_at,
                    latest.is_delisted_at_asof,
                    latest.source_uri,
                    latest_ticker.turnover_24h
                FROM latest
                LEFT JOIN latest_ticker ON latest_ticker.symbol = latest.symbol
                WHERE NOT (
                    latest.is_delisted_at_asof
                    AND COALESCE(latest.delisted_at, latest.ts) < to_timestamp(%s / 1000.0)
                )
                ORDER BY
                    CASE WHEN latest_ticker.turnover_24h IS NULL THEN 1 ELSE 0 END,
                    latest_ticker.turnover_24h DESC NULLS LAST,
                    CASE latest.symbol WHEN 'BTCUSDT' THEN 0 WHEN 'ETHUSDT' THEN 1 ELSE 2 END,
                    latest.is_delisted_at_asof ASC,
                    latest.symbol ASC
                LIMIT %s;
                """,
                (
                    category,
                    end_ms,
                    end_ms,
                    start_ms,
                    category,
                    end_ms,
                    *([end_ms] if has_market_tickers else []),
                    start_ms,
                    max_symbols,
                ),
            )
            rows = _cursor_fetchall(cur)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "source": "v058_symbol_universe_snapshots",
            "reason": type(exc).__name__,
            "message": str(exc),
            "symbols": [],
        }

    symbols: list[str] = []
    entries: list[dict[str, Any]] = []
    for row in rows:
        symbol = str(row[0]).strip().upper()
        if not symbol:
            continue
        symbols.append(symbol)
        entries.append({
            "symbol": symbol,
            "asof_ts": row[1].isoformat() if hasattr(row[1], "isoformat") else str(row[1]),
            "status": row[2],
            "base_coin": row[3],
            "quote_coin": row[4],
            "contract_type": row[5],
            "tick_size": float(row[6]) if row[6] is not None else None,
            "qty_step": float(row[7]) if row[7] is not None else None,
            "min_notional": float(row[8]) if row[8] is not None else None,
            "listed_at": row[9].isoformat() if hasattr(row[9], "isoformat") else row[9],
            "delisted_at": row[10].isoformat() if hasattr(row[10], "isoformat") else row[10],
            "is_delisted_at_asof": bool(row[11]),
            "source_uri": row[12],
            "turnover_24h": float(row[13]) if row[13] is not None else None,
        })
    if not symbols:
        return {
            "status": "empty",
            "source": "v058_symbol_universe_snapshots",
            "reason": "no_rows_for_window",
            "symbols": [],
            "window": {"start_ms": start_ms, "end_ms": end_ms},
        }
    warnings: list[str] = []
    if len(rows) >= max_symbols:
        warnings.append(f"historical_universe_truncated_to_{max_symbols}")
    return {
        "status": "ok",
        "source": "v058_symbol_universe_snapshots",
        "symbols": symbols,
        "symbol_count": len(symbols),
        "entries": entries,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "data_window_start": _iso_from_ms(start_ms),
        "data_window_end": _iso_from_ms(end_ms),
        "warnings": warnings,
    }


def _normalise_edge_payload(payload: Any) -> Optional[dict[str, Any]]:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    cell = dict(payload)
    if "runtime_bps" not in cell and "shrunk_bps" not in cell:
        for key in (
            "runtime_edge_bps",
            "shrunk_edge_bps",
            "mean_net_bps",
            "edge_bps",
            "net_bps",
        ):
            if key in cell:
                cell["shrunk_bps"] = cell[key]
                break
    if "runtime_bps" not in cell and "shrunk_bps" not in cell:
        return None
    for key in ("runtime_bps", "shrunk_bps", "win_rate", "win_rate_shrunk", "std_bps"):
        if key in cell and cell[key] is not None:
            try:
                cell[key] = float(cell[key])
            except (TypeError, ValueError):
                return None
    if "n" not in cell:
        for key in ("n_trades", "sample_size", "count"):
            if key in cell:
                cell["n"] = cell[key]
                break
    if "n" in cell and cell["n"] is not None:
        try:
            cell["n"] = int(cell["n"])
        except (TypeError, ValueError):
            cell["n"] = 0
    return _json_safe_payload(cell)


def _json_safe_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe_payload(v) for v in value]
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _fetch_edge_estimate_snapshot_sync(
    *,
    symbols: list[str],
    strategies: list[str],
    cutoff_ms: int,
) -> dict[str, Any]:
    """Read V059 historical edge snapshots as replay runner JSON cells."""
    if not symbols or not strategies:
        return {
            "status": "empty",
            "source": "v059_edge_estimate_snapshots",
            "reason": "empty_symbols_or_strategies",
            "edge_estimates": {},
        }
    try:
        with get_pg_conn() as conn:
            if conn is None:
                return {
                    "status": "unavailable",
                    "source": "v059_edge_estimate_snapshots",
                    "reason": "pg_unavailable",
                    "edge_estimates": {},
                }
            cur = conn.cursor()
            cur.execute("SET LOCAL statement_timeout = %s;", (_STATEMENT_TIMEOUT_MS,))
            cur.execute(
                """
                SELECT DISTINCT ON (strategy, symbol)
                    strategy,
                    symbol,
                    asof_ts,
                    source_tier,
                    estimate_payload_jsonb,
                    regime_key,
                    cell_key
                FROM learning.edge_estimate_snapshots
                WHERE symbol = ANY(%s)
                  AND strategy = ANY(%s)
                  AND asof_ts <= to_timestamp(%s / 1000.0)
                  AND is_deprecated_at_asof = false
                ORDER BY
                    strategy,
                    symbol,
                    asof_ts DESC,
                    (regime_key = 'global') DESC,
                    (cell_key = 'default') DESC;
                """,
                (symbols, strategies, cutoff_ms),
            )
            rows = _cursor_fetchall(cur)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "unavailable",
            "source": "v059_edge_estimate_snapshots",
            "reason": type(exc).__name__,
            "message": str(exc),
            "edge_estimates": {},
        }

    edge_estimates: dict[str, Any] = {}
    cells: list[dict[str, Any]] = []
    for row in rows:
        strategy = str(row[0])
        symbol = str(row[1]).upper()
        cell = _normalise_edge_payload(row[4])
        if cell is None:
            continue
        key = f"{strategy}::{symbol}"
        edge_estimates[key] = cell
        cells.append({
            "key": key,
            "asof_ts": row[2].isoformat() if hasattr(row[2], "isoformat") else str(row[2]),
            "source_tier": row[3],
            "regime_key": row[5],
            "cell_key": row[6],
        })
    return {
        "status": "ok" if edge_estimates else "empty",
        "source": "v059_edge_estimate_snapshots",
        "cutoff_ms": cutoff_ms,
        "cutoff_iso": _iso_from_ms(cutoff_ms),
        "cell_count": len(edge_estimates),
        "cells": cells,
        "edge_estimates": edge_estimates,
        "reason": None if edge_estimates else "no_cells_for_symbols_strategies_cutoff",
    }


async def _prepare_full_chain_run_fixture(
    body: ReplayFullChainRunRequest,
    strategies: list[str],
) -> dict[str, Any]:
    _require_full_chain_bulk_prod_ip_allowed()
    start_ms = _to_utc_ms(body.data_window_start)
    end_ms = _to_utc_ms(body.data_window_end)
    estimated_bars_per_symbol = _estimate_bar_count(
        start_ms,
        end_ms,
        body.timeframe,
    )
    max_bars_per_symbol = _max_full_chain_bars_per_symbol()
    if estimated_bars_per_symbol > max_bars_per_symbol:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_full_chain_window_too_large_per_symbol"],
                "message": (
                    f"requested window estimates {estimated_bars_per_symbol} "
                    f"bars per symbol; full-chain per-symbol limit is "
                    f"{max_bars_per_symbol}"
                ),
            },
        )

    scanner_snapshot: dict[str, Any] = {}
    scanner_warning: Optional[str] = None
    historical_universe: dict[str, Any] = {}
    universe_source = body.universe_preset
    if body.universe_preset == "current_scanner":
        historical_universe = await asyncio.to_thread(
            _fetch_historical_universe_snapshot_sync,
            category=body.category,
            start_ms=start_ms,
            end_ms=end_ms,
            max_symbols=body.max_symbols,
        )
        if historical_universe.get("status") == "ok" and historical_universe.get("symbols"):
            symbols = list(historical_universe["symbols"])
            warnings = list(historical_universe.get("warnings") or [])
            universe_source = "v058_symbol_universe_snapshots"
            scanner_snapshot = {"historical_universe": historical_universe}
        else:
            reason = str(historical_universe.get("reason") or "empty")
            try:
                scanner_snapshot = await _fetch_current_scanner_snapshot()
            except Exception as exc:  # noqa: BLE001
                scanner_warning = f"scanner_snapshot_unavailable:{exc}"
                scanner_snapshot = {"status": "unavailable", "reason": str(exc)}
            symbols, warnings = _resolve_full_chain_symbols(
                body=body,
                scanner_snapshot=scanner_snapshot,
            )
            warnings.append(
                "historical_universe_unavailable_fell_back_to_current_scanner:"
                + reason
            )
            universe_source = "current_scanner_fallback"
    else:
        symbols, warnings = _resolve_full_chain_symbols(
            body=body,
            scanner_snapshot=scanner_snapshot,
        )
    if scanner_warning:
        warnings.append(scanner_warning)

    estimated_events = estimated_bars_per_symbol * len(symbols)
    max_events = _max_full_chain_events()
    if estimated_events > max_events:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_full_chain_window_too_large"],
                "message": (
                    f"requested window estimates {estimated_events} events across "
                    f"{len(symbols)} symbols; full-chain limit is {max_events}"
                ),
            },
        )

    try:
        market_task = _fetch_full_chain_events(
            symbols=symbols,
            category=body.category,
            timeframe=body.timeframe,
            start_ms=start_ms,
            end_ms=end_ms,
            max_bars_per_symbol=max_bars_per_symbol,
        )
        edge_task = asyncio.to_thread(
            _fetch_edge_estimate_snapshot_sync,
            symbols=symbols,
            strategies=strategies,
            cutoff_ms=start_ms,
        )
        if body.use_current_config:
            strategy_task = _fetch_full_chain_strategy_params(engine=body.engine)
            risk_task = _fetch_current_risk_config(engine=body.engine)
            (
                (events, per_symbol_counts),
                strategy_params,
                risk_overrides,
                edge_snapshot,
            ) = await asyncio.gather(
                market_task,
                strategy_task,
                risk_task,
                edge_task,
            )
        else:
            (events, per_symbol_counts), edge_snapshot = await asyncio.gather(
                market_task,
                edge_task,
            )
            strategy_params = None
            risk_overrides = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("full-chain replay run prepare failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_full_chain_run_prepare_failed"],
                "message": str(exc),
            },
        ) from exc

    if not events:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_codes": ["replay_full_chain_no_market_data"],
                "message": "Bybit public kline returned no bars for this universe/window",
                "symbols": symbols,
            },
        )
    events.sort(
        key=lambda item: (int(item.get("ts_ms", 0)), str(item.get("symbol", "")))
    )
    microstructure_overlay = await asyncio.to_thread(
        _fetch_microstructure_overlays_sync,
        symbols=symbols,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    microstructure_stats = _apply_microstructure_overlays(
        events,
        microstructure_overlay,
        max_staleness_ms=_microstructure_max_staleness_ms(),
    )
    instrument_stats = _apply_instrument_specs(
        events,
        _instrument_specs_from_universe(historical_universe),
    )
    if microstructure_stats.get("status") != "ok":
        warnings.append(
            "microstructure_overlay_unavailable:"
            + str(
                microstructure_stats.get("reason")
                or microstructure_overlay.get("reason")
                or microstructure_stats.get("status")
                or "unknown"
            )
        )
    else:
        bbo_anchor_coverage = float(
            microstructure_stats.get("bbo_anchor_coverage_ratio") or 0.0
        )
        if bbo_anchor_coverage < _BBO_ANCHOR_S1_COVERAGE_RATIO:
            warnings.append(f"bbo_anchor_coverage_low:{bbo_anchor_coverage:.2f}")
    if instrument_stats.get("status") != "ok":
        warnings.append(
            "instrument_specs_unavailable:"
            + str(instrument_stats.get("reason") or instrument_stats.get("status") or "unknown")
        )
    missing_symbols = [symbol for symbol, count in per_symbol_counts.items() if count <= 0]
    if missing_symbols:
        warnings.append("market_data_missing_for:" + ",".join(missing_symbols))
    if edge_snapshot.get("status") != "ok":
        warnings.append(
            "edge_snapshot_unavailable:"
            + str(edge_snapshot.get("reason") or edge_snapshot.get("status") or "unknown")
        )
    execution_calibration = await asyncio.to_thread(
        _ec.fetch_execution_calibration_sync,
        get_pg_conn_fn=get_pg_conn,
        symbols=symbols,
        strategies=strategies,
        asof_ms=start_ms,
    )
    risk_overrides = _ec.apply_execution_calibration_to_risk_overrides(
        risk_overrides,
        execution_calibration,
    )
    if execution_calibration.get("status") not in {"calibrated", "limited"}:
        warnings.append(
            "execution_calibration_conservative_bound:"
            + str(
                execution_calibration.get("reason")
                or execution_calibration.get("status")
                or "unknown"
            )
        )
    if execution_calibration.get("maker_fill_probability_status") not in {
        "calibrated",
        "limited",
    }:
        warnings.append(
            "maker_fill_probability_conservative_bound:"
            + str(
                execution_calibration.get("maker_fill_probability_reason")
                or execution_calibration.get("maker_fill_probability_status")
                or "unknown"
            )
        )

    fixture_path = await asyncio.to_thread(
        _write_full_chain_s2_fixture,
        symbols=symbols,
        timeframe=body.timeframe,
        category=body.category,
        engine=body.engine,
        start_ms=start_ms,
        end_ms=end_ms,
        events=events,
        scanner_snapshot=scanner_snapshot,
        universe_preset=body.universe_preset,
        microstructure_overlay=microstructure_stats,
    )
    input_fidelity = _build_input_fidelity_summary(
        microstructure_stats=microstructure_stats,
        instrument_stats=instrument_stats,
        edge_snapshot=edge_snapshot,
        execution_calibration=execution_calibration,
    )

    return {
        "fixture_path": fixture_path,
        "events": events,
        "event_count": len(events),
        "estimated_event_count": estimated_events,
        "estimated_bars_per_symbol": estimated_bars_per_symbol,
        "per_symbol_event_counts": per_symbol_counts,
        "symbols": symbols,
        "warnings": warnings,
        "scanner_snapshot": scanner_snapshot,
        "historical_universe": historical_universe,
        "universe_source": universe_source,
        "edge_snapshot": edge_snapshot,
        "microstructure_overlay": microstructure_stats,
        "instrument_specs": instrument_stats,
        "input_fidelity": input_fidelity,
        "execution_calibration": execution_calibration,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "strategy_params": strategy_params,
        "risk_overrides": risk_overrides,
    }


def _build_manifest_jsonb(
    *,
    body: ReplayFullChainRunRequest,
    strategy: str,
    fixture_path: Any,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
    scanner_snapshot: dict[str, Any],
    universe_source: str,
    historical_universe: dict[str, Any],
    edge_snapshot: dict[str, Any],
    microstructure_overlay: dict[str, Any],
    input_fidelity: dict[str, Any],
    execution_calibration: dict[str, Any],
) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "mode": "full_chain",
        "execution_scope": "historical_scanner_timeline_to_strategy_risk_exit",
        "source": "s2_bybit_public_full_chain",
        "fixture_uri": str(fixture_path),
        "symbol": _FULL_CHAIN_SYMBOL_SENTINEL,
        "symbols": symbols,
        "strategy": strategy,
        "timeframe": body.timeframe,
        "data_tier": "S2",
        "engine": body.engine,
        "category": body.category,
        "starting_balance": body.starting_balance,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "universe_preset": body.universe_preset,
        "universe_source": universe_source,
        "historical_universe": historical_universe,
        "scanner_snapshot_hash": _canonical_sha256(scanner_snapshot),
        "edge_snapshot_meta": {
            key: value
            for key, value in edge_snapshot.items()
            if key != "edge_estimates"
        },
        "edge_estimates": edge_snapshot.get("edge_estimates") or {},
        "microstructure_overlay": microstructure_overlay,
        "input_fidelity": input_fidelity,
        "execution_calibration": execution_calibration,
        "replay_tier": "s2_public_replay",
        "promotion_allowed": False,
        "promotion_block_reason": "current_config_in_sample_sandbox",
    }


async def _register_full_chain_experiment(
    *,
    actor: base.AuthenticatedActor,
    body: ReplayFullChainRunRequest,
    strategy: str,
    manifest_jsonb: dict[str, Any],
    strategy_params: Optional[dict[str, Any]],
    risk_overrides: Optional[dict[str, Any]],
) -> dict[str, Any]:
    register_body = _er.ReplayExperimentRegisterRequest(
        idempotency_key=(
            "ref21-full-chain-register:"
            + _canonical_sha256({
                "actor": str(actor.actor_id),
                "strategy": strategy,
                "manifest": manifest_jsonb,
            })[:96]
        ),
        symbol=_FULL_CHAIN_SYMBOL_SENTINEL,
        strategy=strategy,
        timeframe=body.timeframe,
        data_tier="S2",
        data_window_start=body.data_window_start,
        data_window_end=body.data_window_end,
        strategy_config_sha256="0" * 64,
        risk_config_sha256="0" * 64,
        half_life_days=_FULL_CHAIN_HALF_LIFE_DAYS,
        embargo_days=_FULL_CHAIN_EMBARGO_DAYS,
        manifest_jsonb=manifest_jsonb,
        strategy_params=strategy_params,
        risk_overrides=risk_overrides,
    )
    result, err = await asyncio.to_thread(
        _er.run_register_in_pg_xact,
        get_pg_conn,
        actor,
        register_body,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
        manifest_signer_module=_ms,
    )
    http_err = _er.map_register_error_to_http(err)
    if http_err is not None:
        status, detail = http_err
        detail = dict(detail)
        detail["strategy"] = strategy
        raise HTTPException(status_code=status, detail=detail)
    if not result or not result.get("experiment_id"):
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_full_chain_register_empty_result"],
                "message": "full-chain replay experiment registration returned no id",
                "strategy": strategy,
            },
        )
    return result


async def _start_full_chain_run(
    *,
    actor: base.AuthenticatedActor,
    experiment_id: str,
    strategy: str,
    active_cap: int,
) -> dict[str, Any]:
    run_body = ReplayRunRequest(
        experiment_id=experiment_id,
        idempotency_key=(
            "ref21-full-chain-run:"
            + _canonical_sha256({
                "actor": str(actor.actor_id),
                "experiment_id": experiment_id,
                "strategy": strategy,
            })[:100]
        ),
    )
    run_id, subprocess_pid, pg_err, output_dir = await asyncio.to_thread(
        _rrun._do_pg_path_for_run_sync,
        body=run_body,
        actor_id=str(actor.actor_id),
        get_pg_conn_fn=get_pg_conn,
        route_helpers=_rh,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
        per_actor_cap=active_cap,
        global_cap=active_cap,
    )
    if run_id is not None and pg_err is None:
        return {
            "strategy": strategy,
            "experiment_id": experiment_id,
            "run_id": run_id,
            "status": "running",
            "subprocess_pid": subprocess_pid,
            "subprocess_completed_in_poll": subprocess_pid is None,
            "output_dir": str(output_dir) if output_dir else None,
        }

    http_err = _rrun.map_run_pg_error_to_http(pg_err, experiment_id=experiment_id)
    if http_err is not None:
        status, detail = http_err
        detail = dict(detail)
        detail["strategy"] = strategy
        detail["experiment_id"] = experiment_id
        raise HTTPException(status_code=status, detail=detail)

    raise HTTPException(
        status_code=503,
        detail={
            "reason_codes": ["replay_full_chain_run_pg_unavailable"],
            "message": "full-chain replay run requires PG-backed run_state",
            "strategy": strategy,
            "experiment_id": experiment_id,
            "pg_reason": pg_err or "unknown",
        },
    )


async def _finalize_if_completed_in_poll(
    *,
    actor: base.AuthenticatedActor,
    run: dict[str, Any],
) -> None:
    if not run.get("subprocess_completed_in_poll"):
        return
    response, http_err = await _fr.run_finalize_in_pg_xact(
        actor=actor,
        run_id=str(run["run_id"]),
        get_pg_conn_fn=get_pg_conn,
        resolve_artifact_output_dir_fn=_rh.resolve_artifact_output_dir,
        artifact_path_within_allowlist_fn=_rh.artifact_path_within_allowlist,
        verify_replay_runner_pid_fn=_rh.verify_replay_runner_pid,
        canary_writer=_cw,
        simulated_fills_writer=_sfw,
        audit_emit_fn=_rh.emit_replay_audit_stub,
        statement_timeout_ms=_fr._FINALIZE_STATEMENT_TIMEOUT_MS,
    )
    if http_err is not None:
        status, detail = http_err
        run["finalize_status"] = "failed"
        run["finalize_http_status"] = status
        run["finalize_detail"] = detail
        return
    run["status"] = "completed"
    run["finalize_status"] = "completed"
    run["finalize"] = response


@full_chain_replay_router.post("/full-chain/run")
@_REPLAY_LIMITER.limit("10/minute", key_func=_replay_rate_limit_key)
async def post_replay_full_chain_run(
    request: Request,
    body: ReplayFullChainRunRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Prepare a full-chain fixture and spawn dedicated replay_runner runs."""
    _require_replay_write(actor)
    started_at_ms = int(time.time() * 1000)
    strategies = body.strategies or list(_DEFAULT_FULL_CHAIN_STRATEGIES)
    max_strategies = _max_full_chain_run_strategies()
    if len(strategies) > max_strategies:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_full_chain_strategy_cap_exceeded"],
                "message": (
                    f"requested {len(strategies)} strategies; full-chain "
                    f"run limit is {max_strategies}"
                ),
            },
        )

    prepared = await _prepare_full_chain_run_fixture(body, strategies)
    registered: list[dict[str, Any]] = []
    for strategy in strategies:
        manifest_jsonb = _build_manifest_jsonb(
            body=body,
            strategy=strategy,
            fixture_path=prepared["fixture_path"],
            symbols=prepared["symbols"],
            start_ms=prepared["start_ms"],
            end_ms=prepared["end_ms"],
            scanner_snapshot=prepared["scanner_snapshot"],
            universe_source=prepared["universe_source"],
            historical_universe=prepared["historical_universe"],
            edge_snapshot=prepared["edge_snapshot"],
            microstructure_overlay=prepared["microstructure_overlay"],
            input_fidelity=prepared["input_fidelity"],
            execution_calibration=prepared["execution_calibration"],
        )
        registered.append(
            await _register_full_chain_experiment(
                actor=actor,
                body=body,
                strategy=strategy,
                manifest_jsonb=manifest_jsonb,
                strategy_params=prepared["strategy_params"],
                risk_overrides=prepared["risk_overrides"],
            )
        )

    active_cap = max(1, len(registered))
    runs: list[dict[str, Any]] = []
    for strategy, experiment in zip(strategies, registered):
        run = await _start_full_chain_run(
            actor=actor,
            experiment_id=str(experiment["experiment_id"]),
            strategy=strategy,
            active_cap=active_cap,
        )
        if body.auto_finalize_completed:
            await _finalize_if_completed_in_poll(actor=actor, run=run)
        runs.append(run)

    completed_in_poll = sum(1 for item in runs if item.get("status") == "completed")
    return _rh.replay_response_envelope({
        "mode": "full_chain_run",
        "execution_mode": "subprocess_strategy_risk_per_strategy",
        "scanner_scope": "historical_scanner_timeline_from_fixture",
        "started_at_ms": started_at_ms,
        "fixture_uri": str(prepared["fixture_path"]),
        "data_tier": "S2",
        "source": "s2_bybit_public_full_chain",
        "event_count": prepared["event_count"],
        "estimated_event_count": prepared["estimated_event_count"],
        "estimated_bars_per_symbol": prepared["estimated_bars_per_symbol"],
        "per_symbol_event_counts": prepared["per_symbol_event_counts"],
        "symbols": prepared["symbols"],
        "universe_source": prepared["universe_source"],
        "historical_universe": prepared["historical_universe"],
        "edge_snapshot": {
            key: value
            for key, value in prepared["edge_snapshot"].items()
            if key != "edge_estimates"
        },
        "microstructure_overlay": prepared["microstructure_overlay"],
        "instrument_specs": prepared["instrument_specs"],
        "input_fidelity": prepared["input_fidelity"],
        "execution_calibration": prepared["execution_calibration"],
        "strategies": strategies,
        "strategy_count": len(strategies),
        "runs": runs,
        "completed_in_poll": completed_in_poll,
        "warnings": prepared["warnings"],
        "timeframe": body.timeframe,
        "engine": body.engine,
        "category": body.category,
        "data_window_start": datetime.fromtimestamp(
            prepared["start_ms"] / 1000,
            tz=timezone.utc,
        ).isoformat(),
        "data_window_end": datetime.fromtimestamp(
            prepared["end_ms"] / 1000,
            tz=timezone.utc,
        ).isoformat(),
        "starting_balance": body.starting_balance,
        "promotion_allowed": False,
        "promotion_block_reason": "current_config_in_sample_sandbox",
    })


__all__ = [
    "ReplayFullChainRunRequest",
    "full_chain_replay_router",
]

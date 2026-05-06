"""REF-21 full-chain replay run orchestration routes.

This module owns the one-click full-chain run entrypoint. It prepares one
multi-symbol S2 public-data fixture, registers one manifest per requested
strategy, and starts the existing dedicated Rust ``replay_runner`` subprocess
for each manifest. It does not run scanner, strategy, risk, or execution logic
inside the Control API worker process.
"""

import asyncio
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
            cur.execute(
                """
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
                )
                SELECT
                    symbol,
                    ts,
                    status,
                    base_coin,
                    quote_coin,
                    contract_type,
                    listed_at,
                    delisted_at,
                    is_delisted_at_asof,
                    source_uri
                FROM latest
                WHERE NOT (
                    is_delisted_at_asof
                    AND COALESCE(delisted_at, ts) < to_timestamp(%s / 1000.0)
                )
                ORDER BY
                    CASE symbol WHEN 'BTCUSDT' THEN 0 WHEN 'ETHUSDT' THEN 1 ELSE 2 END,
                    is_delisted_at_asof ASC,
                    symbol ASC
                LIMIT %s;
                """,
                (
                    category,
                    end_ms,
                    end_ms,
                    start_ms,
                    category,
                    end_ms,
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
            "listed_at": row[6].isoformat() if hasattr(row[6], "isoformat") else row[6],
            "delisted_at": row[7].isoformat() if hasattr(row[7], "isoformat") else row[7],
            "is_delisted_at_asof": bool(row[8]),
            "source_uri": row[9],
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
    missing_symbols = [symbol for symbol, count in per_symbol_counts.items() if count <= 0]
    if missing_symbols:
        warnings.append("market_data_missing_for:" + ",".join(missing_symbols))
    if edge_snapshot.get("status") != "ok":
        warnings.append(
            "edge_snapshot_unavailable:"
            + str(edge_snapshot.get("reason") or edge_snapshot.get("status") or "unknown")
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

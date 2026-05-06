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


async def _prepare_full_chain_run_fixture(
    body: ReplayFullChainRunRequest,
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
    if body.universe_preset == "current_scanner":
        try:
            scanner_snapshot = await _fetch_current_scanner_snapshot()
        except Exception as exc:  # noqa: BLE001
            scanner_warning = f"scanner_snapshot_unavailable:{exc}"
            scanner_snapshot = {"status": "unavailable", "reason": str(exc)}

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
        if body.use_current_config:
            strategy_task = _fetch_full_chain_strategy_params(engine=body.engine)
            risk_task = _fetch_current_risk_config(engine=body.engine)
            (
                (events, per_symbol_counts),
                strategy_params,
                risk_overrides,
            ) = await asyncio.gather(market_task, strategy_task, risk_task)
        else:
            events, per_symbol_counts = await market_task
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
) -> dict[str, Any]:
    return {
        "manifest_version": 1,
        "mode": "full_chain",
        "execution_scope": "scanner_universe_snapshot_to_strategy_risk_exit",
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
        "scanner_snapshot_hash": _canonical_sha256(scanner_snapshot),
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
        half_life_days=7.0,
        embargo_days=7.0,
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

    prepared = await _prepare_full_chain_run_fixture(body)
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
        "scanner_scope": "scanner_universe_snapshot",
        "started_at_ms": started_at_ms,
        "fixture_uri": str(prepared["fixture_path"]),
        "data_tier": "S2",
        "source": "s2_bybit_public_full_chain",
        "event_count": prepared["event_count"],
        "estimated_event_count": prepared["estimated_event_count"],
        "estimated_bars_per_symbol": prepared["estimated_bars_per_symbol"],
        "per_symbol_event_counts": prepared["per_symbol_event_counts"],
        "symbols": prepared["symbols"],
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

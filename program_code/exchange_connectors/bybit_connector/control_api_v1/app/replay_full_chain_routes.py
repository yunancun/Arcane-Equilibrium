"""REF-21 full-chain replay run orchestration routes.

This module owns the one-click full-chain run entrypoint. It prepares one
multi-symbol S2 public-data fixture, registers one manifest per requested
strategy, and starts the existing dedicated Rust ``replay_runner`` subprocess
for each manifest. It does not run scanner, strategy, risk, or execution logic
inside the Control API worker process.

MODULE_NOTE（2026-06-02 行為保留拆分）：
    自足資料層（production TOML echo / microstructure overlay / instrument spec
    / edge snapshot / historical universe 讀取 / input fidelity / manifest 組裝）
    已下推至 ``replay/full_chain_fixture.py``（CLAUDE §七 route rule + §九 LOC
    guardrail）。本檔保留：2 個 route handler（``/full-chain/coverage`` +
    ``/full-chain/run``）、pydantic 請求模型、orchestrator（prepare/coverage scope
    /register/start/finalize 的 await-gather 序列與 warning 組裝），以及與
    ``app/`` 緊耦合的 IPC fetch 縫。

    Monkeypatch 縫不變式（測試 ``test_replay_full_chain_run_routes.py`` 對
    ``app.replay_full_chain_routes`` 命名空間 patch）：
    - 6 個直接縫（``_fetch_full_chain_events`` / ``_fetch_full_chain_strategy_params``
      / ``_fetch_current_risk_config`` / ``_fetch_current_scanner_snapshot`` /
      ``_fetch_historical_universe_snapshot_sync`` / ``_fetch_edge_estimate_snapshot_sync``）
      必須在本模塊命名空間於呼叫時解析才生效。orchestrator 以裸名呼叫，patch 流通。
      2 個本地 SQL 縫（universe / edge）保留為本模塊薄 wrapper，綁 ``get_pg_conn``
      後委派 ``full_chain_fixture``，被 patch 時整塊替換 → fake 收到原 kwargs。
    - 4 個 alias 縫（``_dc`` / ``_er`` / ``_rrun`` / ``_fr``）patch 的是 package
      模塊屬性，保留 alias 即可。
    - 測試亦以 read 方式存取 ``mod._apply_microstructure_overlays`` /
      ``mod._canonical_sha256`` / ``mod._load_production_*``，故 re-export 自
      ``full_chain_fixture`` 保 attr surface。
"""

import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, validator

from . import main_legacy as base
from . import replay_data_coverage as _dc
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
    _raise_prepare_rejection,
    _require_full_chain_bulk_prod_ip_allowed,
    _replay_prepare_policy,
    _resolve_full_chain_symbols,
    _rh,
    _to_utc_ms,
    _write_full_chain_s2_fixture,
)

try:
    from ..replay import canary_writer as _cw  # type: ignore[no-redef]
    from ..replay import experiment_registry as _er  # type: ignore[no-redef]
    from ..replay import full_chain_fixture as _fcf  # type: ignore[no-redef]
    from ..replay import manifest_signer as _ms  # type: ignore[no-redef]
    from ..replay import run_finalize_route as _fr  # type: ignore[no-redef]
    from ..replay import run_route as _rrun  # type: ignore[no-redef]
    from ..replay import simulated_fills_writer as _sfw  # type: ignore[no-redef]
    from ..replay.replay_models import ReplayRunRequest
except ImportError:
    from replay import canary_writer as _cw  # type: ignore[no-redef]
    from replay import experiment_registry as _er  # type: ignore[no-redef]
    from replay import full_chain_fixture as _fcf  # type: ignore[no-redef]
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
# full-chain manifest 內代表「整個 universe」的 symbol sentinel。
# 單一來源在 full_chain_fixture，re-import 避免重複字面值漂移。
_FULL_CHAIN_SYMBOL_SENTINEL = _fcf._FULL_CHAIN_SYMBOL_SENTINEL
_REPLAY_LIMITER = base.limiter
_FULL_CHAIN_HALF_LIFE_DAYS = 7.0
_FULL_CHAIN_EMBARGO_DAYS = 14.0
_BBO_ANCHOR_S1_COVERAGE_RATIO = 0.80


# ─────────────────────────────────────────────────────────────────────────────
# 自足資料 helper re-export — 抽出至 replay/full_chain_fixture.py（2026-06-02）
#
# 為何 re-export：測試以 ``mod._apply_microstructure_overlays`` /
# ``mod._canonical_sha256`` / ``mod._load_production_*`` 讀取存取（非 patch），
# orchestrator 也以裸名呼叫 ``_canonical_sha256`` / ``_build_manifest_jsonb``。
# ``from X import name`` 把本模塊屬性綁到 package 函式，attr surface 與裸名解析
# 兩者透明，行為與抽出前 byte-identical。
# ─────────────────────────────────────────────────────────────────────────────
_canonical_sha256 = _fcf.canonical_sha256
_resolve_settings_root = _fcf.resolve_settings_root
_load_production_scanner_config = _fcf.load_production_scanner_config
_load_production_strategy_params_toml = _fcf.load_production_strategy_params_toml
_load_production_risk_overrides_toml = _fcf.load_production_risk_overrides_toml
_iso_from_ms = _fcf.iso_from_ms
_cursor_fetchall = _fcf.cursor_fetchall
_microstructure_overlay_enabled = _fcf.microstructure_overlay_enabled
_microstructure_max_staleness_ms = _fcf.microstructure_max_staleness_ms
_apply_microstructure_overlays = _fcf.apply_microstructure_overlays
_instrument_specs_from_universe = _fcf.instrument_specs_from_universe
_apply_instrument_specs = _fcf.apply_instrument_specs
_build_input_fidelity_summary = _fcf.build_input_fidelity_summary
_normalise_edge_payload = _fcf.normalise_edge_payload
_json_safe_payload = _fcf.json_safe_payload
_finite_float = _fcf.finite_float
_build_manifest_jsonb = _fcf.build_manifest_jsonb


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


# ─────────────────────────────────────────────────────────────────────────────
# 本地 SQL 縫 wrapper — 綁 get_pg_conn 後委派 full_chain_fixture
#
# 為何保留 wrapper（不直接 re-export）：測試 patch
# ``mod._fetch_historical_universe_snapshot_sync`` /
# ``mod._fetch_edge_estimate_snapshot_sync``，且 orchestrator 以裸名呼叫且
# 不傳 get_pg_conn_fn（fake 只 assert category/symbols/cutoff_ms 等業務 kwargs）。
# wrapper 在本模塊命名空間綁 get_pg_conn + _STATEMENT_TIMEOUT_MS 後委派；被 patch
# 時整塊替換，fake 收到與抽出前完全一致的 kwargs。SQL/結構 byte-identical。
# ─────────────────────────────────────────────────────────────────────────────


def _fetch_historical_universe_snapshot_sync(
    *,
    category: str,
    start_ms: int,
    end_ms: int,
    max_symbols: int,
) -> dict[str, Any]:
    return _fcf.fetch_historical_universe_snapshot_sync(
        get_pg_conn_fn=get_pg_conn,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
        category=category,
        start_ms=start_ms,
        end_ms=end_ms,
        max_symbols=max_symbols,
    )


def _fetch_edge_estimate_snapshot_sync(
    *,
    symbols: list[str],
    strategies: list[str],
    cutoff_ms: int,
) -> dict[str, Any]:
    return _fcf.fetch_edge_estimate_snapshot_sync(
        get_pg_conn_fn=get_pg_conn,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
        symbols=symbols,
        strategies=strategies,
        cutoff_ms=cutoff_ms,
    )


def _fetch_microstructure_overlays_sync(
    *,
    symbols: list[str],
    start_ms: int,
    end_ms: int,
) -> dict[str, Any]:
    return _fcf.fetch_microstructure_overlays_sync(
        get_pg_conn_fn=get_pg_conn,
        statement_timeout_ms=_STATEMENT_TIMEOUT_MS,
        symbols=symbols,
        start_ms=start_ms,
        end_ms=end_ms,
    )


async def _prepare_full_chain_run_fixture(
    body: ReplayFullChainRunRequest,
    strategies: list[str],
) -> dict[str, Any]:
    _require_full_chain_bulk_prod_ip_allowed()
    policy = _replay_prepare_policy()
    start_ms = _to_utc_ms(body.data_window_start)
    end_ms = _to_utc_ms(body.data_window_end)
    estimated_bars_per_symbol = _estimate_bar_count(
        start_ms,
        end_ms,
        body.timeframe,
    )
    max_bars_per_symbol = policy.full_chain_max_bars_per_symbol
    rejection = policy.validate_full_chain_bars_per_symbol(
        estimated_bars_per_symbol=estimated_bars_per_symbol,
    )
    if rejection is not None:
        _raise_prepare_rejection(rejection)

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
    rejection = policy.validate_full_chain_event_window(
        estimated_events=estimated_events,
        symbol_count=len(symbols),
    )
    if rejection is not None:
        _raise_prepare_rejection(rejection)

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
        orderbook_coverage = float(
            microstructure_stats.get("orderbook_depth_coverage_ratio") or 0.0
        )
        if orderbook_coverage < _BBO_ANCHOR_S1_COVERAGE_RATIO:
            warnings.append(f"orderbook_depth_coverage_low:{orderbook_coverage:.2f}")
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
    if execution_calibration.get("latency_status") not in {"calibrated", "limited"}:
        warnings.append(
            "latency_calibration_conservative_bound:"
            + str(
                execution_calibration.get("latency_reason")
                or execution_calibration.get("latency_status")
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


async def _resolve_full_chain_coverage_scope(
    body: ReplayFullChainRunRequest,
) -> dict[str, Any]:
    policy = _replay_prepare_policy()
    start_ms = _to_utc_ms(body.data_window_start)
    end_ms = _to_utc_ms(body.data_window_end)
    estimated_bars_per_symbol = _estimate_bar_count(
        start_ms,
        end_ms,
        body.timeframe,
    )
    rejection = policy.validate_full_chain_bars_per_symbol(
        estimated_bars_per_symbol=estimated_bars_per_symbol,
    )
    if rejection is not None:
        _raise_prepare_rejection(rejection)

    scanner_snapshot: dict[str, Any] = {}
    historical_universe: dict[str, Any] = {}
    universe_source = body.universe_preset
    warnings: list[str] = []
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
            warnings.extend(list(historical_universe.get("warnings") or []))
            scanner_snapshot = {"historical_universe": historical_universe}
            universe_source = "v058_symbol_universe_snapshots"
        else:
            reason = str(historical_universe.get("reason") or "empty")
            try:
                scanner_snapshot = await _fetch_current_scanner_snapshot()
            except Exception as exc:  # noqa: BLE001
                scanner_snapshot = {"status": "unavailable", "reason": str(exc)}
                warnings.append(f"scanner_snapshot_unavailable:{exc}")
            symbols, resolved_warnings = _resolve_full_chain_symbols(
                body=body,
                scanner_snapshot=scanner_snapshot,
            )
            warnings.extend(resolved_warnings)
            warnings.append(
                "historical_universe_unavailable_fell_back_to_current_scanner:"
                + reason
            )
            universe_source = "current_scanner_fallback"
    else:
        symbols, resolved_warnings = _resolve_full_chain_symbols(
            body=body,
            scanner_snapshot=scanner_snapshot,
        )
        warnings.extend(resolved_warnings)

    estimated_events = estimated_bars_per_symbol * len(symbols)
    rejection = policy.validate_full_chain_event_window(
        estimated_events=estimated_events,
        symbol_count=len(symbols),
    )
    if rejection is not None:
        _raise_prepare_rejection(rejection)
    return {
        "start_ms": start_ms,
        "end_ms": end_ms,
        "symbols": symbols,
        "warnings": warnings,
        "scanner_snapshot": scanner_snapshot,
        "historical_universe": historical_universe,
        "universe_source": universe_source,
        "estimated_bars_per_symbol": estimated_bars_per_symbol,
        "estimated_event_count": estimated_events,
    }


@full_chain_replay_router.post("/full-chain/coverage")
@_REPLAY_LIMITER.limit("10/minute", key_func=_replay_rate_limit_key)
async def post_replay_full_chain_coverage(
    request: Request,
    body: ReplayFullChainRunRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Read-only recorder coverage preflight for one-click full-chain replay."""
    _require_replay_write(actor)
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

    scope = await _resolve_full_chain_coverage_scope(body)
    recorder_coverage, edge_snapshot, execution_calibration = await asyncio.gather(
        asyncio.to_thread(
            _dc.estimate_replay_window_coverage_sync,
            get_pg_conn_fn=get_pg_conn,
            symbols=scope["symbols"],
            start_ms=scope["start_ms"],
            end_ms=scope["end_ms"],
            timeframe=body.timeframe,
        ),
        asyncio.to_thread(
            _fetch_edge_estimate_snapshot_sync,
            symbols=scope["symbols"],
            strategies=strategies,
            cutoff_ms=scope["start_ms"],
        ),
        asyncio.to_thread(
            _ec.fetch_execution_calibration_sync,
            get_pg_conn_fn=get_pg_conn,
            symbols=scope["symbols"],
            strategies=strategies,
            asof_ms=scope["start_ms"],
        ),
    )
    coverage_verdict = _dc.build_replay_coverage_verdict(
        recorder_coverage=recorder_coverage,
        execution_calibration=execution_calibration,
    )
    warnings = list(scope["warnings"])
    warnings.extend(coverage_verdict.get("reason_codes") or [])
    if edge_snapshot.get("status") != "ok":
        warnings.append(
            "edge_snapshot_unavailable:"
            + str(edge_snapshot.get("reason") or edge_snapshot.get("status") or "unknown")
        )
    return _rh.replay_response_envelope({
        "mode": "full_chain_coverage_preflight",
        "execution_mode": "read_only_preflight_no_subprocess",
        "promotion_allowed": False,
        "universe_preset": body.universe_preset,
        "universe_source": scope["universe_source"],
        "symbols": scope["symbols"],
        "symbol_count": len(scope["symbols"]),
        "strategies": strategies,
        "strategy_count": len(strategies),
        "timeframe": body.timeframe,
        "category": body.category,
        "engine": body.engine,
        "data_window_start": _iso_from_ms(scope["start_ms"]),
        "data_window_end": _iso_from_ms(scope["end_ms"]),
        "estimated_bars_per_symbol": scope["estimated_bars_per_symbol"],
        "estimated_event_count": scope["estimated_event_count"],
        "historical_universe": scope["historical_universe"],
        "recorder_coverage": recorder_coverage,
        "coverage_verdict": coverage_verdict,
        "edge_snapshot": edge_snapshot,
        "execution_calibration": execution_calibration,
        "warnings": warnings,
    })


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
            # P0 Replay Tier A T4（2026-05-11）：把 prepared 階段 IPC fetched 的
            # production strategy_params / risk_overrides 直接 echo 進 manifest
            # top-level，讓 replay engine 能讀生產配置；register handler 仍會走
            # _replay_strategy_params / _replay_risk_overrides reserved blob path
            # 作 backward compat 雙保險。
            strategy_params=prepared["strategy_params"],
            risk_overrides=prepared["risk_overrides"],
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

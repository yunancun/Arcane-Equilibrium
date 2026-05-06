"""Replay Quick Routes — one-click operator fixture preparation.

MODULE_NOTE (EN):
  Provides the simple Replay UI with a narrow backend action:
  turn (symbol, timeframe, start, end, demo/live engine) into an S2 Bybit
  public-data fixture and attach current engine strategy/risk snapshots.
  It deliberately does not spawn replay_runner; the existing REF-20
  register/run/finalize routes remain the canonical execution path.
  REF-21 adds full-chain dataset preparation: scanner/custom multi-symbol
  universe -> time-ordered S2 fixture + engine config snapshots. Execution
  stays out of this module until the full scanner/strategy/risk replay runner
  is wired.

MODULE_NOTE (中):
  提供 Replay 傻瓜式 UI 所需的窄後端動作：把 symbol/timeframe/start/end
  與 demo/live engine 轉成 S2 Bybit public-data fixture，並附上當前引擎的
  strategy/risk snapshot。此路由不直接 spawn replay_runner；既有 REF-20
  register/run/finalize 仍是唯一執行主路徑。
  REF-21 在這裡新增全鏈條資料準備：scanner/custom 多幣種 universe -> 時間
  排序 S2 fixture + engine config snapshots。完整 scanner/strategy/risk runner
  接上前，本模組不偽裝成已完成執行。
"""

import asyncio
import json
import logging
import math
import os
import re
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, validator

from . import main_legacy as base
from .auth import require_scope_and_operator
from .ipc_dispatch import one_shot_ipc_call

try:
    from ..replay import route_helpers as _rh  # type: ignore[no-redef]
    from ..replay.bybit_public_client import ReplayBybitPublicClient
except ImportError:
    from replay import route_helpers as _rh  # type: ignore[no-redef]
    from replay.bybit_public_client import ReplayBybitPublicClient


logger = logging.getLogger(__name__)

quick_replay_router = APIRouter(
    prefix="/api/v1/replay",
    tags=["Replay Quick / 快速回測"],
)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9_.]{1,32}$")
_STRATEGY_RE = re.compile(r"^[A-Za-z0-9_.]{1,64}$")
_ALLOWED_ENGINES = {"demo", "live"}
_ALLOWED_CATEGORIES = {"linear", "spot", "inverse"}
_ALLOWED_UNIVERSE_PRESETS = {"current_scanner", "pinned_only", "custom"}
_DEFAULT_FULL_CHAIN_SYMBOLS = ("BTCUSDT", "ETHUSDT")
_DEFAULT_FULL_CHAIN_STRATEGIES = (
    "grid_trading",
    "ma_crossover",
    "bb_breakout",
    "bb_reversion",
    "funding_arb",
)
_TIMEFRAMES: dict[str, tuple[str, int]] = {
    "1m": ("1", 60_000),
    "3m": ("3", 180_000),
    "5m": ("5", 300_000),
    "15m": ("15", 900_000),
    "1h": ("60", 3_600_000),
    "4h": ("240", 14_400_000),
    "1d": ("D", 86_400_000),
}
_REPLAY_BYBIT_PUBLIC_CLIENT = ReplayBybitPublicClient()


class ReplayQuickPrepareRequest(BaseModel):
    """POST /api/v1/replay/quick/prepare body."""

    symbol: str = Field(default="BTCUSDT", min_length=1, max_length=32)
    strategy: str = Field(default="grid_trading", min_length=1, max_length=64)
    timeframe: str = Field(default="1m", min_length=1, max_length=8)
    engine: str = Field(default="demo", min_length=1, max_length=16)
    category: str = Field(default="linear", min_length=1, max_length=16)
    data_window_start: datetime
    data_window_end: datetime
    starting_balance: Optional[float] = Field(default=10_000.0, gt=0)
    use_current_config: bool = True

    @validator("symbol")
    def _symbol_allowlist(cls, value: str) -> str:
        v = value.strip().upper()
        if not _SYMBOL_RE.match(v):
            raise ValueError("symbol must be 1-32 chars: A-Z 0-9 _ .")
        return v

    @validator("strategy")
    def _strategy_allowlist(cls, value: str) -> str:
        v = value.strip()
        if not _STRATEGY_RE.match(v):
            raise ValueError("strategy must be 1-64 chars: A-Z a-z 0-9 _ .")
        return v

    @validator("timeframe")
    def _timeframe_allowlist(cls, value: str) -> str:
        v = value.strip()
        if v not in _TIMEFRAMES:
            raise ValueError("quick replay supports 1m/3m/5m/15m/1h/4h/1d")
        return v

    @validator("engine")
    def _engine_allowlist(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in _ALLOWED_ENGINES:
            raise ValueError("engine must be demo or live")
        return v

    @validator("category")
    def _category_allowlist(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in _ALLOWED_CATEGORIES:
            raise ValueError("category must be linear, spot, or inverse")
        return v

    @validator("data_window_end")
    def _window_order(cls, value: datetime, values: dict[str, Any]) -> datetime:
        start = values.get("data_window_start")
        if start is not None and _to_utc_ms(value) <= _to_utc_ms(start):
            raise ValueError("data_window_end must be greater than data_window_start")
        return value


class ReplayFullChainPrepareRequest(BaseModel):
    """POST /api/v1/replay/full-chain/prepare body."""

    universe_preset: str = Field(
        default="current_scanner",
        min_length=1,
        max_length=32,
        description="current_scanner, pinned_only, or custom",
    )
    symbols: Optional[list[str]] = Field(default=None)
    timeframe: str = Field(default="1m", min_length=1, max_length=8)
    engine: str = Field(default="demo", min_length=1, max_length=16)
    category: str = Field(default="linear", min_length=1, max_length=16)
    data_window_start: datetime
    data_window_end: datetime
    starting_balance: Optional[float] = Field(default=10_000.0, gt=0)
    max_symbols: int = Field(default=8, ge=1, le=25)
    use_current_config: bool = True

    @validator("universe_preset")
    def _universe_allowlist(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in _ALLOWED_UNIVERSE_PRESETS:
            raise ValueError(
                "universe_preset must be current_scanner, pinned_only, or custom"
            )
        return v

    @validator("symbols")
    def _symbols_allowlist(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        normalised: list[str] = []
        seen: set[str] = set()
        for item in value:
            symbol = str(item).strip().upper()
            if not _SYMBOL_RE.match(symbol):
                raise ValueError(
                    "symbols must contain 1-32 char symbols: A-Z 0-9 _ ."
                )
            if symbol not in seen:
                normalised.append(symbol)
                seen.add(symbol)
        return normalised

    @validator("timeframe")
    def _full_chain_timeframe_allowlist(cls, value: str) -> str:
        v = value.strip()
        if v not in _TIMEFRAMES:
            raise ValueError("full-chain replay supports 1m/3m/5m/15m/1h/4h/1d")
        return v

    @validator("engine")
    def _full_chain_engine_allowlist(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in _ALLOWED_ENGINES:
            raise ValueError("engine must be demo or live")
        return v

    @validator("category")
    def _full_chain_category_allowlist(cls, value: str) -> str:
        v = value.strip().lower()
        if v not in _ALLOWED_CATEGORIES:
            raise ValueError("category must be linear, spot, or inverse")
        return v

    @validator("data_window_end")
    def _full_chain_window_order(
        cls,
        value: datetime,
        values: dict[str, Any],
    ) -> datetime:
        start = values.get("data_window_start")
        if start is not None and _to_utc_ms(value) <= _to_utc_ms(start):
            raise ValueError("data_window_end must be greater than data_window_start")
        return value


def _require_replay_write(actor: base.AuthenticatedActor) -> None:
    """Mutating-route gate: Operator role + replay:write scope."""
    require_scope_and_operator(actor, "replay:write")


def _to_utc_ms(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def _estimate_bar_count(start_ms: int, end_ms: int, timeframe: str) -> int:
    interval_ms = _TIMEFRAMES[timeframe][1]
    return int(math.ceil((end_ms - start_ms) / interval_ms))


def _max_quick_bars() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_QUICK_MAX_BARS", "5000")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 5000
    return max(200, min(parsed, 20_000))


def _max_full_chain_events() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_FULL_CHAIN_MAX_EVENTS", "100000")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 100_000
    return max(1_000, min(parsed, 300_000))


def _full_chain_prepare_enabled() -> bool:
    raw = os.environ.get("OPENCLAW_REPLAY_PREPARE_ENABLED", "0")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _bulk_prod_ip_allowed() -> bool:
    raw = os.environ.get("OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP", "0")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _require_full_chain_bulk_prod_ip_allowed() -> None:
    """Block bulk Bybit fetches from the live release host unless explicitly enabled."""
    if not _rh.is_live_release_profile() or _bulk_prod_ip_allowed():
        return
    raise HTTPException(
        status_code=403,
        detail={
            "reason_codes": ["replay_full_chain_prod_ip_blocked"],
            "message": (
                "full-chain replay prepare is enabled, but bulk Bybit fetches "
                "from the live release host are blocked unless "
                "OPENCLAW_REPLAY_BULK_ALLOW_PROD_IP=1 is set for a governed run"
            ),
        },
    )


def _max_full_chain_bars_per_symbol() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_FULL_CHAIN_MAX_BARS_PER_SYMBOL", "12000")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 12_000
    return max(200, min(parsed, 50_000))


def _full_chain_fetch_concurrency() -> int:
    raw = os.environ.get("OPENCLAW_REPLAY_FULL_CHAIN_FETCH_CONCURRENCY", "3")
    try:
        parsed = int(raw)
    except ValueError:
        parsed = 3
    return max(1, min(parsed, 5))


def _fixture_root() -> Path:
    base_dir = (
        os.environ.get("OPENCLAW_REPLAY_QUICK_FIXTURE_DIR", "").strip()
        or os.environ.get("OPENCLAW_DATA_DIR", "").strip()
    )
    if base_dir:
        root = Path(base_dir)
    else:
        root = Path(tempfile.gettempdir()) / "openclaw"
    return root / "replay_quick_fixtures"


def _full_chain_fixture_root() -> Path:
    base_dir = os.environ.get("OPENCLAW_REPLAY_FULL_CHAIN_FIXTURE_DIR", "").strip()
    if base_dir:
        return Path(base_dir)
    return _fixture_root() / "full_chain"


def _fetch_bybit_klines_sync(
    *,
    symbol: str,
    category: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    max_bars: Optional[int] = None,
) -> list[dict[str, Any]]:
    """Fetch Bybit public klines and return replay MarketEvent dictionaries."""
    request_bar_budget = max_bars if max_bars is not None else _max_quick_bars()
    return _REPLAY_BYBIT_PUBLIC_CLIENT.fetch_klines_sync(
        symbol=symbol,
        category=category,
        timeframe=timeframe,
        start_ms=start_ms,
        end_ms=end_ms,
        max_bars=request_bar_budget,
    )


def _write_s2_fixture(
    *,
    symbol: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    events: list[dict[str, Any]],
) -> Path:
    root = _fixture_root()
    root.mkdir(parents=True, exist_ok=True)
    safe_name = (
        f"{symbol}_{timeframe}_{start_ms}_{end_ms}_{uuid.uuid4().hex[:12]}.json"
    )
    path = root / safe_name
    payload = {
        "schema_version": 1,
        "source": "s2_bybit_public",
        "events": events,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        logger.warning("quick replay fixture chmod failed path=%s", path)
    return path


def _write_full_chain_s2_fixture(
    *,
    symbols: list[str],
    timeframe: str,
    category: str,
    engine: str,
    start_ms: int,
    end_ms: int,
    events: list[dict[str, Any]],
    scanner_snapshot: dict[str, Any],
    universe_preset: str,
    microstructure_overlay: Optional[dict[str, Any]] = None,
) -> Path:
    root = _full_chain_fixture_root()
    root.mkdir(parents=True, exist_ok=True)
    symbol_hash = uuid.uuid5(uuid.NAMESPACE_DNS, ",".join(symbols)).hex[:8]
    safe_name = (
        f"full_chain_{universe_preset}_{timeframe}_{symbol_hash}_"
        f"{start_ms}_{end_ms}_{uuid.uuid4().hex[:12]}.json"
    )
    path = root / safe_name
    payload = {
        "schema_version": 1,
        "mode": "full_chain",
        "source": "s2_bybit_public_full_chain",
        "category": category,
        "engine": engine,
        "timeframe": timeframe,
        "symbols": symbols,
        "window": {"start_ms": start_ms, "end_ms": end_ms},
        "scanner_snapshot": scanner_snapshot,
        "microstructure_overlay": microstructure_overlay or {
            "status": "not_requested",
            "source": "market.market_tickers",
        },
        "events": events,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    try:
        path.chmod(0o600)
    except OSError:
        logger.warning("full-chain replay fixture chmod failed path=%s", path)
    return path


def _unwrap_ipc_payload(resp: Any) -> Any:
    if isinstance(resp, dict) and "result" in resp:
        return resp["result"]
    return resp


def _parse_maybe_json_dict(payload: Any) -> dict[str, Any]:
    payload = _unwrap_ipc_payload(payload)
    if isinstance(payload, str):
        parsed = json.loads(payload)
        if isinstance(parsed, dict):
            return parsed
    if isinstance(payload, dict):
        return payload
    raise ValueError("ipc_payload_not_dict")


def _symbol_list_from_value(value: Any) -> list[str]:
    if isinstance(value, str):
        raw_items = [part.strip() for part in value.split(",")]
    elif isinstance(value, list):
        raw_items = value
    else:
        return []

    symbols: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        symbol = str(item).strip().upper()
        if not _SYMBOL_RE.match(symbol):
            continue
        if symbol not in seen:
            symbols.append(symbol)
            seen.add(symbol)
    return symbols


def _extract_scanner_symbols(snapshot: dict[str, Any]) -> list[str]:
    candidates: list[Any] = [
        snapshot.get("active_symbols"),
        snapshot.get("symbols"),
        snapshot.get("candidate_symbols"),
    ]
    nested_keys = ("data", "status", "last_scan", "scanner", "snapshot")
    for key in nested_keys:
        nested = snapshot.get(key)
        if isinstance(nested, dict):
            candidates.extend([
                nested.get("active_symbols"),
                nested.get("symbols"),
                nested.get("candidate_symbols"),
            ])
            top = nested.get("top_candidates") or nested.get("candidates")
            if isinstance(top, list):
                candidates.append([
                    item.get("symbol")
                    for item in top
                    if isinstance(item, dict) and item.get("symbol")
                ])

    for candidate in candidates:
        symbols = _symbol_list_from_value(candidate)
        if symbols:
            return symbols
    return []


async def _fetch_current_scanner_snapshot() -> dict[str, Any]:
    resp = await one_shot_ipc_call(
        "get_scanner_status",
        params={},
        timeout=5.0,
        wrap_errors_as_http=False,
        error_context="replay_full_chain_scanner_status",
    )
    try:
        return _parse_maybe_json_dict(resp)
    except Exception:  # noqa: BLE001
        return {"raw": _unwrap_ipc_payload(resp)}


def _resolve_full_chain_symbols(
    *,
    body: ReplayFullChainPrepareRequest,
    scanner_snapshot: dict[str, Any],
) -> tuple[list[str], list[str]]:
    warnings: list[str] = []

    if body.universe_preset == "custom":
        symbols = body.symbols or []
        if not symbols:
            raise HTTPException(
                status_code=400,
                detail={
                    "reason_codes": ["replay_full_chain_custom_symbols_required"],
                    "message": "custom full-chain replay requires at least one symbol",
                },
            )
    elif body.universe_preset == "pinned_only":
        symbols = list(body.symbols or _DEFAULT_FULL_CHAIN_SYMBOLS)
    else:
        symbols = _extract_scanner_symbols(scanner_snapshot)
        if not symbols:
            warnings.append("scanner_universe_empty_fell_back_to_pinned_symbols")
            symbols = list(_DEFAULT_FULL_CHAIN_SYMBOLS)

    if len(symbols) > body.max_symbols:
        warnings.append(f"symbol_universe_truncated_to_{body.max_symbols}")
        symbols = symbols[: body.max_symbols]

    if not symbols:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_full_chain_empty_universe"],
                "message": "full-chain replay resolved an empty universe",
            },
        )
    return symbols, warnings


async def _fetch_current_strategy_params(
    *,
    engine: str,
    strategy: str,
) -> dict[str, Any]:
    resp = await one_shot_ipc_call(
        "get_strategy_params",
        params={"engine": engine, "strategy_name": strategy},
        timeout=5.0,
        wrap_errors_as_http=False,
        error_context="replay_quick_strategy_params",
    )
    params = _parse_maybe_json_dict(resp)
    if isinstance(params.get(strategy), dict):
        return params
    return {strategy: params}


async def _fetch_full_chain_strategy_params(*, engine: str) -> dict[str, Any]:
    tasks = [
        _fetch_current_strategy_params(engine=engine, strategy=strategy)
        for strategy in _DEFAULT_FULL_CHAIN_STRATEGIES
    ]
    merged: dict[str, Any] = {}
    for params in await asyncio.gather(*tasks):
        merged.update(params)
    return merged


async def _fetch_current_risk_config(*, engine: str) -> dict[str, Any]:
    resp = await one_shot_ipc_call(
        "get_risk_config",
        params={"engine": engine},
        timeout=5.0,
        wrap_errors_as_http=False,
        error_context="replay_quick_risk_config",
    )
    config = _parse_maybe_json_dict(resp)
    inner = config.get("config")
    if isinstance(inner, dict):
        return inner
    return config


async def _fetch_full_chain_events(
    *,
    symbols: list[str],
    category: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
    max_bars_per_symbol: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    semaphore = asyncio.Semaphore(_full_chain_fetch_concurrency())

    async def _fetch_one(symbol: str) -> tuple[str, list[dict[str, Any]]]:
        async with semaphore:
            rows = await asyncio.to_thread(
                _fetch_bybit_klines_sync,
                symbol=symbol,
                category=category,
                timeframe=timeframe,
                start_ms=start_ms,
                end_ms=end_ms,
                max_bars=max_bars_per_symbol,
            )
            return symbol, rows

    results = await asyncio.gather(*[_fetch_one(symbol) for symbol in symbols])
    per_symbol_counts: dict[str, int] = {}
    events: list[dict[str, Any]] = []
    for symbol, rows in results:
        per_symbol_counts[symbol] = len(rows)
        events.extend(rows)
    events.sort(
        key=lambda item: (int(item.get("ts_ms", 0)), str(item.get("symbol", "")))
    )
    return events, per_symbol_counts


@quick_replay_router.post("/quick/prepare")
async def post_replay_quick_prepare(
    body: ReplayQuickPrepareRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Prepare a one-click S2 replay fixture + current config snapshots."""
    _require_replay_write(actor)
    start_ms = _to_utc_ms(body.data_window_start)
    end_ms = _to_utc_ms(body.data_window_end)
    estimated_bars = _estimate_bar_count(start_ms, end_ms, body.timeframe)
    max_bars = _max_quick_bars()
    if estimated_bars > max_bars:
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["replay_quick_window_too_large"],
                "message": (
                    f"requested window estimates {estimated_bars} bars; "
                    f"quick replay limit is {max_bars}"
                ),
            },
        )

    try:
        market_task = asyncio.to_thread(
            _fetch_bybit_klines_sync,
            symbol=body.symbol,
            category=body.category,
            timeframe=body.timeframe,
            start_ms=start_ms,
            end_ms=end_ms,
        )
        if body.use_current_config:
            strategy_task = _fetch_current_strategy_params(
                engine=body.engine,
                strategy=body.strategy,
            )
            risk_task = _fetch_current_risk_config(engine=body.engine)
            events, strategy_params, risk_overrides = await asyncio.gather(
                market_task,
                strategy_task,
                risk_task,
            )
        else:
            events = await market_task
            strategy_params = None
            risk_overrides = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("quick replay prepare failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_quick_prepare_failed"],
                "message": str(exc),
            },
        ) from exc

    if not events:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_codes": ["replay_quick_no_market_data"],
                "message": "Bybit public kline returned no bars for this window",
            },
        )

    fixture_path = await asyncio.to_thread(
        _write_s2_fixture,
        symbol=body.symbol,
        timeframe=body.timeframe,
        start_ms=start_ms,
        end_ms=end_ms,
        events=events,
    )

    return _rh.replay_response_envelope({
        "fixture_uri": str(fixture_path),
        "data_tier": "S2",
        "source": "s2_bybit_public",
        "event_count": len(events),
        "estimated_bar_count": estimated_bars,
        "symbol": body.symbol,
        "strategy": body.strategy,
        "timeframe": body.timeframe,
        "engine": body.engine,
        "category": body.category,
        "data_window_start": datetime.fromtimestamp(
            start_ms / 1000, tz=timezone.utc,
        ).isoformat(),
        "data_window_end": datetime.fromtimestamp(
            end_ms / 1000, tz=timezone.utc,
        ).isoformat(),
        "starting_balance": body.starting_balance,
        "strategy_params": strategy_params,
        "risk_overrides": risk_overrides,
    })


@quick_replay_router.post("/full-chain/prepare")
async def post_replay_full_chain_prepare(
    body: ReplayFullChainPrepareRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> dict[str, Any]:
    """Prepare a REF-21 full-chain multi-symbol S2 fixture + config snapshots."""
    _require_replay_write(actor)
    if not _full_chain_prepare_enabled():
        raise HTTPException(
            status_code=403,
            detail={
                "reason_codes": ["replay_full_chain_prepare_disabled"],
                "message": (
                    "full-chain replay prepare is disabled; set "
                    "OPENCLAW_REPLAY_PREPARE_ENABLED=1 only for governed R1 hardening"
                ),
            },
        )
    _require_full_chain_bulk_prod_ip_allowed()
    start_ms = _to_utc_ms(body.data_window_start)
    end_ms = _to_utc_ms(body.data_window_end)
    estimated_bars_per_symbol = _estimate_bar_count(start_ms, end_ms, body.timeframe)
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
        logger.warning("full-chain replay prepare failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={
                "reason_codes": ["replay_full_chain_prepare_failed"],
                "message": str(exc),
            },
        ) from exc

    missing_symbols = [symbol for symbol, count in per_symbol_counts.items() if count <= 0]
    if not events:
        raise HTTPException(
            status_code=404,
            detail={
                "reason_codes": ["replay_full_chain_no_market_data"],
                "message": "Bybit public kline returned no bars for this universe/window",
                "symbols": symbols,
            },
        )
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

    return _rh.replay_response_envelope({
        "fixture_uri": str(fixture_path),
        "data_tier": "S2",
        "source": "s2_bybit_public_full_chain",
        "mode": "full_chain",
        "execution_mode": "dataset_only_until_ref21_runner",
        "event_count": len(events),
        "estimated_event_count": estimated_events,
        "estimated_bars_per_symbol": estimated_bars_per_symbol,
        "per_symbol_event_counts": per_symbol_counts,
        "symbols": symbols,
        "universe_preset": body.universe_preset,
        "scanner_snapshot": scanner_snapshot,
        "warnings": warnings,
        "timeframe": body.timeframe,
        "engine": body.engine,
        "category": body.category,
        "data_window_start": datetime.fromtimestamp(
            start_ms / 1000, tz=timezone.utc,
        ).isoformat(),
        "data_window_end": datetime.fromtimestamp(
            end_ms / 1000, tz=timezone.utc,
        ).isoformat(),
        "starting_balance": body.starting_balance,
        "strategy_params": strategy_params,
        "risk_overrides": risk_overrides,
    })


__all__ = [
    "ReplayFullChainPrepareRequest",
    "ReplayQuickPrepareRequest",
    "quick_replay_router",
    "_fetch_bybit_klines_sync",
    "_write_full_chain_s2_fixture",
    "_write_s2_fixture",
]

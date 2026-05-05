"""Replay Quick Routes — one-click operator fixture preparation.

MODULE_NOTE (EN):
  Provides the simple Replay UI with a narrow backend action:
  turn (symbol, timeframe, start, end, demo/live engine) into an S2 Bybit
  public-data fixture and attach current engine strategy/risk snapshots.
  It deliberately does not spawn replay_runner; the existing REF-20
  register/run/finalize routes remain the canonical execution path.

MODULE_NOTE (中):
  提供 Replay 傻瓜式 UI 所需的窄後端動作：把 symbol/timeframe/start/end
  與 demo/live engine 轉成 S2 Bybit public-data fixture，並附上當前引擎的
  strategy/risk snapshot。此路由不直接 spawn replay_runner；既有 REF-20
  register/run/finalize 仍是唯一執行主路徑。
"""

import asyncio
import json
import logging
import math
import os
import re
import tempfile
import urllib.parse
import urllib.request
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
except ImportError:
    from replay import route_helpers as _rh  # type: ignore[no-redef]


logger = logging.getLogger(__name__)

quick_replay_router = APIRouter(
    prefix="/api/v1/replay",
    tags=["Replay Quick / 快速回測"],
)

_SYMBOL_RE = re.compile(r"^[A-Za-z0-9_.]{1,32}$")
_STRATEGY_RE = re.compile(r"^[A-Za-z0-9_.]{1,64}$")
_ALLOWED_ENGINES = {"demo", "live"}
_ALLOWED_CATEGORIES = {"linear", "spot", "inverse"}
_BYBIT_BASE_URL = "https://api.bybit.com"
_BYBIT_LIMIT = 200
_TIMEFRAMES: dict[str, tuple[str, int]] = {
    "1m": ("1", 60_000),
    "3m": ("3", 180_000),
    "5m": ("5", 300_000),
    "15m": ("15", 900_000),
    "1h": ("60", 3_600_000),
    "4h": ("240", 14_400_000),
    "1d": ("D", 86_400_000),
}


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


def _fetch_bybit_klines_sync(
    *,
    symbol: str,
    category: str,
    timeframe: str,
    start_ms: int,
    end_ms: int,
) -> list[dict[str, Any]]:
    """Fetch Bybit public klines and return replay MarketEvent dictionaries."""
    interval = _TIMEFRAMES[timeframe][0]
    events_by_ts: dict[int, dict[str, Any]] = {}
    end_cursor = end_ms
    max_requests = int(math.ceil(_max_quick_bars() / _BYBIT_LIMIT)) + 2

    for _ in range(max_requests):
        query = urllib.parse.urlencode({
            "category": category,
            "symbol": symbol,
            "interval": interval,
            "start": str(start_ms),
            "end": str(end_cursor),
            "limit": str(_BYBIT_LIMIT),
        })
        req = urllib.request.Request(
            f"{_BYBIT_BASE_URL}/v5/market/kline?{query}",
            headers={"User-Agent": "OpenClawReplayQuick/1.0"},
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("retCode") != 0:
            raise RuntimeError(
                "bybit_kline_error:"
                + str(data.get("retMsg") or data.get("retCode") or "unknown")
            )
        rows = data.get("result", {}).get("list", [])
        if not rows:
            break

        parsed_ts: list[int] = []
        for row in rows:
            ts = int(row[0])
            parsed_ts.append(ts)
            if ts < start_ms or ts > end_ms:
                continue
            events_by_ts[ts] = {
                "ts_ms": ts,
                "symbol": symbol,
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
                "volume": float(row[5]),
            }

        oldest = min(parsed_ts)
        if oldest <= start_ms or len(rows) < _BYBIT_LIMIT:
            break
        next_cursor = oldest - 1
        if next_cursor >= end_cursor:
            break
        end_cursor = next_cursor

    return [events_by_ts[k] for k in sorted(events_by_ts)]


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


__all__ = [
    "ReplayQuickPrepareRequest",
    "quick_replay_router",
    "_fetch_bybit_klines_sync",
    "_write_s2_fixture",
]

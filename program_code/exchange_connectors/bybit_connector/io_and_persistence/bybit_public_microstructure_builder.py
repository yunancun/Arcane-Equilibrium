#!/usr/bin/env python3
"""
MODULE_NOTE:
- role: H0 public microstructure input builder.
- purpose:
  Pull Bybit public market data and normalize it into an auditable local
  microstructure snapshot for H0-A market friction.
- upstream:
  1) runtime/bybit/bybit_runtime_state_latest.json
- output:
  runtime/bybit/local_judgment/bybit_public_microstructure_latest.json
- notes:
  1) v1 uses Bybit public REST only, no auth required.
  2) This module does NOT authorize trading.
  3) It exists only to supply public market structure facts to H0.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


RUNTIME_STATE_PATH = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/"
    "bybit_runtime_state_latest.json"
)

OUTPUT_DIR = Path(
    os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment"
)
LATEST_OUTPUT_PATH = OUTPUT_DIR / "bybit_public_microstructure_latest.json"

BYBIT_PUBLIC_BASE_URL_ENV = "BYBIT_PUBLIC_BASE_URL"
BYBIT_PUBLIC_CATEGORY_ENV = "BYBIT_PUBLIC_CATEGORY"
BYBIT_PUBLIC_SYMBOL_ENV = "BYBIT_PUBLIC_SYMBOL"
BYBIT_PUBLIC_ORDERBOOK_LIMIT_ENV = "BYBIT_PUBLIC_ORDERBOOK_LIMIT"
BYBIT_PUBLIC_RECENT_TRADE_LIMIT_ENV = "BYBIT_PUBLIC_RECENT_TRADE_LIMIT"
BYBIT_PUBLIC_KLINE_INTERVAL_ENV = "BYBIT_PUBLIC_KLINE_INTERVAL"
BYBIT_PUBLIC_KLINE_LIMIT_ENV = "BYBIT_PUBLIC_KLINE_LIMIT"
BYBIT_LOCAL_SLIPPAGE_TEST_NOTIONAL_USDT_ENV = "BYBIT_LOCAL_SLIPPAGE_TEST_NOTIONAL_USDT"

DEFAULT_BASE_URL = "https://api.bybit.com"
DEFAULT_CATEGORY = "linear"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_ORDERBOOK_LIMIT = 50
DEFAULT_RECENT_TRADE_LIMIT = 50
DEFAULT_KLINE_INTERVAL = "1"
DEFAULT_KLINE_LIMIT = 20
DEFAULT_TEST_NOTIONAL_USDT = 100.0


def load_json(path: Path) -> tuple[dict[str, Any], bool, str | None]:
    """Load JSON from disk."""
    if not path.exists():
        return {}, False, f"missing_file:{path}"
    try:
        return json.loads(path.read_text(encoding="utf-8")), True, None
    except Exception as exc:  # pragma: no cover
        return {}, False, f"json_load_error:{path}:{exc}"


def parse_int_env(name: str, default: int) -> int:
    """Parse integer env with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


def parse_float_env(name: str, default: float) -> float:
    """Parse float env with fallback."""
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(str(raw).strip())
    except ValueError:
        return default


def fetch_json(base_url: str, path: str, params: dict[str, Any], timeout: int = 10) -> dict[str, Any]:
    """Fetch JSON via urllib GET."""
    query = urllib.parse.urlencode(params)
    url = f"{base_url}{path}?{query}"
    request = urllib.request.Request(
        url=url,
        headers={
            "User-Agent": "OpenClaw-H0-F/1.0",
            "Accept": "application/json",
        },
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def save_report(report: dict[str, Any]) -> tuple[Path, Path]:
    """Write latest and dated JSON outputs."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    latest_path = LATEST_OUTPUT_PATH
    dated_path = OUTPUT_DIR / f"bybit_public_microstructure_{report['ts_ms']}.json"
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    latest_path.write_text(serialized, encoding="utf-8")
    dated_path.write_text(serialized, encoding="utf-8")
    return latest_path, dated_path


def safe_float(value: Any) -> float | None:
    """Best-effort float parsing."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

def compute_book_side_notional(levels: list[list[str]], top_n: int) -> float:
    """Compute quote notional across first top_n levels."""
    total = 0.0
    for level in levels[:top_n]:
        if len(level) < 2:
            continue
        price = safe_float(level[0])
        qty = safe_float(level[1])
        if price is None or qty is None:
            continue
        total += price * qty
    return round(total, 6)


def compute_market_slippage_bps(levels: list[list[str]], test_notional: float, is_buy: bool) -> float | None:
    """
    Estimate slippage in bps by walking book levels for a target quote notional.
    For buy, compare avg fill vs best ask.
    For sell, compare avg fill vs best bid.
    """
    if not levels or test_notional <= 0:
        return None

    best_price = safe_float(levels[0][0]) if len(levels[0]) >= 1 else None
    if best_price is None or best_price <= 0:
        return None

    remaining = test_notional
    total_qty = 0.0
    total_quote = 0.0

    for level in levels:
        if len(level) < 2:
            continue
        price = safe_float(level[0])
        qty = safe_float(level[1])
        if price is None or qty is None or price <= 0 or qty <= 0:
            continue

        level_quote = price * qty
        take_quote = min(level_quote, remaining)
        take_qty = take_quote / price

        total_quote += take_quote
        total_qty += take_qty
        remaining -= take_quote

        if remaining <= 1e-9:
            break

    if total_qty <= 0:
        return None

    avg_price = total_quote / total_qty
    if is_buy:
        slippage = ((avg_price / best_price) - 1.0) * 10000.0
    else:
        slippage = (1.0 - (avg_price / best_price)) * 10000.0

    return round(max(slippage, 0.0), 6)


def compute_volatility_band_from_klines(kline_rows: list[list[str]]) -> tuple[float | None, str]:
    """Compute a simple realized-vol proxy from close-to-close returns."""
    closes: list[float] = []
    for row in reversed(kline_rows):
        if len(row) < 5:
            continue
        close_price = safe_float(row[4])
        if close_price is not None and close_price > 0:
            closes.append(close_price)

    if len(closes) < 3:
        return None, "unavailable"

    returns: list[float] = []
    for idx in range(1, len(closes)):
        prev_close = closes[idx - 1]
        curr_close = closes[idx]
        returns.append((curr_close / prev_close) - 1.0)

    if len(returns) < 2:
        return None, "unavailable"

    mean_return = sum(returns) / len(returns)
    variance = sum((item - mean_return) ** 2 for item in returns) / len(returns)
    stdev = math.sqrt(variance)
    vol_bps = round(stdev * 10000.0, 6)

    if vol_bps < 5:
        band = "low"
    elif vol_bps < 15:
        band = "moderate"
    else:
        band = "high"

    return vol_bps, band

def build_report() -> dict[str, Any]:
    """Build a public microstructure snapshot for H0."""
    ts_ms = int(time.time() * 1000)

    runtime, runtime_present, runtime_error = load_json(RUNTIME_STATE_PATH)
    source_errors = [error for error in [runtime_error] if error]

    base_url = os.getenv(BYBIT_PUBLIC_BASE_URL_ENV, DEFAULT_BASE_URL).strip()
    category = os.getenv(BYBIT_PUBLIC_CATEGORY_ENV, DEFAULT_CATEGORY).strip()
    symbol = os.getenv(BYBIT_PUBLIC_SYMBOL_ENV, DEFAULT_SYMBOL).strip().upper()
    orderbook_limit = parse_int_env(BYBIT_PUBLIC_ORDERBOOK_LIMIT_ENV, DEFAULT_ORDERBOOK_LIMIT)
    recent_trade_limit = parse_int_env(BYBIT_PUBLIC_RECENT_TRADE_LIMIT_ENV, DEFAULT_RECENT_TRADE_LIMIT)
    kline_interval = os.getenv(BYBIT_PUBLIC_KLINE_INTERVAL_ENV, DEFAULT_KLINE_INTERVAL).strip()
    kline_limit = parse_int_env(BYBIT_PUBLIC_KLINE_LIMIT_ENV, DEFAULT_KLINE_LIMIT)
    test_notional = parse_float_env(
        BYBIT_LOCAL_SLIPPAGE_TEST_NOTIONAL_USDT_ENV,
        DEFAULT_TEST_NOTIONAL_USDT,
    )

    runtime_state = runtime.get("overall_runtime_state", "unknown")
    system_mode = runtime.get("system_mode", "unknown")
    execution_state = runtime.get("execution_state", "unknown")

    orderbook_payload: dict[str, Any] | None = None
    trades_payload: dict[str, Any] | None = None
    kline_payload: dict[str, Any] | None = None
    fetch_errors: list[str] = []

    try:
        orderbook_payload = fetch_json(
            base_url,
            "/v5/market/orderbook",
            {
                "category": category,
                "symbol": symbol,
                "limit": orderbook_limit,
            },
        )
    except Exception as exc:
        fetch_errors.append(f"orderbook_fetch_failed:{exc}")

    try:
        trades_payload = fetch_json(
            base_url,
            "/v5/market/recent-trade",
            {
                "category": category,
                "symbol": symbol,
                "limit": recent_trade_limit,
            },
        )
    except Exception as exc:
        fetch_errors.append(f"recent_trade_fetch_failed:{exc}")

    try:
        kline_payload = fetch_json(
            base_url,
            "/v5/market/kline",
            {
                "category": category,
                "symbol": symbol,
                "interval": kline_interval,
                "limit": kline_limit,
            },
        )
    except Exception as exc:
        fetch_errors.append(f"kline_fetch_failed:{exc}")

    orderbook_result = (orderbook_payload or {}).get("result", {})
    bids = orderbook_result.get("b", []) or []
    asks = orderbook_result.get("a", []) or []

    best_bid = safe_float(bids[0][0]) if bids and len(bids[0]) >= 1 else None
    best_ask = safe_float(asks[0][0]) if asks and len(asks[0]) >= 1 else None

    spread_abs = None
    spread_bps = None
    if best_bid is not None and best_ask is not None and best_bid > 0 and best_ask >= best_bid:
        spread_abs = round(best_ask - best_bid, 8)
        mid_price = (best_bid + best_ask) / 2.0
        if mid_price > 0:
            spread_bps = round((spread_abs / mid_price) * 10000.0, 6)

    recent_trade_rows = ((trades_payload or {}).get("result", {}) or {}).get("list", []) or []
    last_trade_price = None
    last_trade_ts_ms = None
    if recent_trade_rows:
        row0 = recent_trade_rows[0] or {}
        last_trade_price = safe_float(row0.get("price", row0.get("p")))
        try:
            last_trade_ts_ms = int(row0.get("time", row0.get("T")))
        except (TypeError, ValueError):
            last_trade_ts_ms = None

    kline_rows = ((kline_payload or {}).get("result", {}) or {}).get("list", []) or []
    volatility_bps, volatility_band = compute_volatility_band_from_klines(kline_rows)

    bid_depth_notional_top10 = compute_book_side_notional(bids, top_n=10)
    ask_depth_notional_top10 = compute_book_side_notional(asks, top_n=10)
    slippage_buy_bps = compute_market_slippage_bps(asks, test_notional=test_notional, is_buy=True)
    slippage_sell_bps = compute_market_slippage_bps(bids, test_notional=test_notional, is_buy=False)

    coverage = {
        "best_bid_ask_present": best_bid is not None and best_ask is not None,
        "orderbook_depth_present": len(bids) > 0 and len(asks) > 0,
        "recent_trade_tape_present": len(recent_trade_rows) > 0,
        "volatility_band_present": volatility_bps is not None,
        "slippage_proxy_present": slippage_buy_bps is not None and slippage_sell_bps is not None,
    }

    if fetch_errors:
        microstructure_state = "blocked_public_fetch_failed"
        allow_use_by_h0 = False
    elif all(coverage.values()):
        microstructure_state = "healthy_basic_public_microstructure"
        allow_use_by_h0 = True
    else:
        microstructure_state = "partial_public_microstructure"
        allow_use_by_h0 = False

    return {
        "public_type": "bybit_public_microstructure",
        "public_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "H0-F",
        "report_ok": True,
        "runtime_context": {
            "runtime_present": runtime_present,
            "overall_runtime_state": runtime_state,
            "system_mode": system_mode,
            "execution_state": execution_state,
            "source_errors": source_errors,
        },
        "config": {
            "base_url": base_url,
            "category": category,
            "symbol": symbol,
            "orderbook_limit": orderbook_limit,
            "recent_trade_limit": recent_trade_limit,
            "kline_interval": kline_interval,
            "kline_limit": kline_limit,
            "slippage_test_notional_usdt": test_notional,
        },
        "fetch_status": {
            "fetch_errors": fetch_errors,
            "orderbook_ret_code": orderbook_payload.get("retCode") if orderbook_payload else None,
            "trades_ret_code": trades_payload.get("retCode") if trades_payload else None,
            "kline_ret_code": kline_payload.get("retCode") if kline_payload else None,
        },
        "derived": {
            "best_bid": best_bid,
            "best_ask": best_ask,
            "spread_abs": spread_abs,
            "spread_bps": spread_bps,
            "bid_depth_notional_top10": bid_depth_notional_top10,
            "ask_depth_notional_top10": ask_depth_notional_top10,
            "recent_trade_count": len(recent_trade_rows),
            "last_trade_price": last_trade_price,
            "last_trade_ts_ms": last_trade_ts_ms,
            "volatility_bps": volatility_bps,
            "volatility_band": volatility_band,
            "slippage_buy_bps_for_test_notional": slippage_buy_bps,
            "slippage_sell_bps_for_test_notional": slippage_sell_bps,
        },
        "coverage": coverage,
        "microstructure_state": microstructure_state,
        "allow_use_by_h0": allow_use_by_h0,
        "operator_message": (
            "H0-F public microstructure snapshot built from Bybit public REST market data."
        ),
    }


def main() -> None:
    """Entry point."""
    report = build_report()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    latest_path, dated_path = save_report(report)
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")


if __name__ == "__main__":
    main()

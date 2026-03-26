from __future__ import annotations

"""
Bybit Public WebSocket Listener / Bybit 公共 WebSocket 监听器
实时接收 Bybit 永续合约公共行情数据（ticker / orderbook / trade）

MODULE_NOTE (中文):
  本模块订阅 Bybit V5 公共 WebSocket，接收 linear 永续合约的实时行情推送。
  公共 WebSocket 不需要 API Key 认证，不消耗 REST API 速率限制。
  数据更新频率约 100ms（ticker），远优于 REST 轮询。

  关键设计：
  - 复用 bybit_private_ws_listener.py 的连接管理模式（自动重连、状态追踪、JSONL 日志）
  - 支持动态订阅/取消订阅交易对
  - 通过回调函数将价格事件推送给 market_data_dispatcher（注意力过滤器）
  - 线程安全：所有状态变更通过 threading.Lock 保护

MODULE_NOTE (English):
  This module subscribes to Bybit V5 public WebSocket for real-time linear perpetual
  contract market data pushes. Public WebSocket requires no API key authentication
  and does not consume REST API rate limits.
  Data update frequency is ~100ms (ticker), far superior to REST polling.

  Key design:
  - Reuses connection management pattern from bybit_private_ws_listener.py
    (auto-reconnect, status tracking, JSONL logging)
  - Supports dynamic subscribe/unsubscribe of trading pairs
  - Pushes price events to market_data_dispatcher (attention filter) via callbacks
  - Thread-safe: all state mutations protected by threading.Lock

安全不变量 / Safety invariant:
  - 仅订阅公共数据，绝不发送任何交易指令 / Only subscribes to public data, never sends trading commands
  - system_mode / execution_state / execution_authority 全程不变 / Unchanged throughout
"""

import json
import logging
import threading
import time
from typing import Any, Callable

import websocket

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Constants / 常量
# ═══════════════════════════════════════════════════════════════════════════════

# Bybit V5 public WebSocket for linear perpetual contracts
# Bybit V5 线性永续合约公共 WebSocket 地址
PUBLIC_WS_URL = "wss://stream.bybit.com/v5/public/linear"

# Connection parameters / 连接参数
PING_INTERVAL = 20       # WebSocket ping interval (seconds) / 心跳间隔
PING_TIMEOUT = 10        # Ping timeout (seconds) / 心跳超时
RECONNECT_DELAY_SEC = 3  # Delay before reconnection attempt / 重连等待时间

# Default symbols to subscribe / 默认订阅的交易对
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]


# ═══════════════════════════════════════════════════════════════════════════════
# Price Event Type / 价格事件类型
# ═══════════════════════════════════════════════════════════════════════════════

class PriceEvent:
    """
    Normalized price event from WebSocket / 从 WebSocket 归一化的价格事件

    Contains the essential fields needed by the attention filter and paper engine.
    包含注意力过滤器和纸上交易引擎所需的关键字段。
    """
    __slots__ = (
        "symbol", "last_price", "mark_price", "index_price",
        "best_bid", "best_ask", "volume_24h", "turnover_24h",
        "price_change_pct_24h", "high_24h", "low_24h",
        "ts_ms", "receive_ts_ms",
    )

    def __init__(
        self,
        symbol: str,
        last_price: float,
        mark_price: float | None = None,
        index_price: float | None = None,
        best_bid: float | None = None,
        best_ask: float | None = None,
        volume_24h: float | None = None,
        turnover_24h: float | None = None,
        price_change_pct_24h: float | None = None,
        high_24h: float | None = None,
        low_24h: float | None = None,
        ts_ms: int = 0,
        receive_ts_ms: int = 0,
    ):
        self.symbol = symbol
        self.last_price = last_price
        self.mark_price = mark_price
        self.index_price = index_price
        self.best_bid = best_bid
        self.best_ask = best_ask
        self.volume_24h = volume_24h
        self.turnover_24h = turnover_24h
        self.price_change_pct_24h = price_change_pct_24h
        self.high_24h = high_24h
        self.low_24h = low_24h
        self.ts_ms = ts_ms
        self.receive_ts_ms = receive_ts_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "last_price": self.last_price,
            "mark_price": self.mark_price,
            "index_price": self.index_price,
            "best_bid": self.best_bid,
            "best_ask": self.best_ask,
            "volume_24h": self.volume_24h,
            "turnover_24h": self.turnover_24h,
            "price_change_pct_24h": self.price_change_pct_24h,
            "high_24h": self.high_24h,
            "low_24h": self.low_24h,
            "ts_ms": self.ts_ms,
            "receive_ts_ms": self.receive_ts_ms,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Public WebSocket Listener / 公共 WebSocket 监听器
# ═══════════════════════════════════════════════════════════════════════════════

# Type alias for price event callback
# 价格事件回调类型别名
PriceCallback = Callable[[PriceEvent], None]


class BybitPublicWsListener:
    """
    Bybit public WebSocket listener for real-time market data.
    Bybit 公共 WebSocket 监听器，用于接收实时行情数据。

    Usage:
        listener = BybitPublicWsListener(
            symbols=["BTCUSDT", "ETHUSDT"],
            on_price=my_callback,
        )
        listener.start()   # starts background thread
        ...
        listener.stop()    # graceful shutdown
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        on_price: PriceCallback | None = None,
        ws_url: str = PUBLIC_WS_URL,
    ) -> None:
        self._symbols = list(symbols or DEFAULT_SYMBOLS)
        self._on_price = on_price
        self._ws_url = ws_url

        # Internal state / 内部状态
        self._ws: websocket.WebSocketApp | None = None
        self._thread: threading.Thread | None = None
        self._stop_flag = threading.Event()
        self._lock = threading.Lock()

        # Latest prices cache (symbol → PriceEvent)
        # 最新价格缓存
        self._latest_prices: dict[str, PriceEvent] = {}

        # Status tracking / 状态追踪
        self._status: dict[str, Any] = {
            "listener_type": "bybit_public_ws_listener",
            "listener_version": "v1",
            "running": False,
            "connected": False,
            "subscribed_symbols": list(self._symbols),
            "connection_attempts": 0,
            "connection_open_count": 0,
            "subscribe_ok_count": 0,
            "message_count": 0,
            "ticker_update_count": 0,
            "last_error": None,
            "last_ticker_ts_ms": None,
            "started_ts_ms": None,
            "ws_url": ws_url,
        }

    # ── Public Interface / 公开接口 ──

    def start(self) -> None:
        """Start the WebSocket listener in a background thread / 后台线程启动 WS 监听"""
        if self._thread and self._thread.is_alive():
            logger.warning("Public WS listener already running / 公共 WS 监听器已在运行")
            return

        self._stop_flag.clear()
        with self._lock:
            self._status["running"] = True
            self._status["started_ts_ms"] = int(time.time() * 1000)

        self._thread = threading.Thread(
            target=self._run_loop,
            name="bybit-public-ws",
            daemon=True,
        )
        self._thread.start()
        logger.info("Public WS listener started / 公共 WS 监听器已启动, symbols=%s", self._symbols)

    def stop(self) -> None:
        """Gracefully stop the listener / 优雅停止监听器"""
        self._stop_flag.set()
        with self._lock:
            self._status["running"] = False
        ws = self._ws
        if ws:
            try:
                ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=10)
        logger.info("Public WS listener stopped / 公共 WS 监听器已停止")

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def get_status(self) -> dict[str, Any]:
        """Get listener status snapshot / 获取监听器状态快照"""
        with self._lock:
            return dict(self._status)

    def get_latest_price(self, symbol: str) -> PriceEvent | None:
        """Get the latest cached price for a symbol / 获取某交易对的最新缓存价格"""
        return self._latest_prices.get(symbol)

    def get_all_latest_prices(self) -> dict[str, float]:
        """Get all latest prices as {symbol: last_price} / 获取所有最新价格"""
        return {
            sym: evt.last_price
            for sym, evt in self._latest_prices.items()
        }

    def add_symbol(self, symbol: str) -> None:
        """Dynamically subscribe to a new symbol / 动态订阅新交易对"""
        if symbol in self._symbols:
            return
        self._symbols.append(symbol)
        with self._lock:
            self._status["subscribed_symbols"] = list(self._symbols)
        ws = self._ws
        if ws:
            try:
                sub_msg = {"op": "subscribe", "args": [f"tickers.{symbol}"]}
                ws.send(json.dumps(sub_msg))
                logger.info("Subscribed to %s / 已订阅 %s", symbol, symbol)
            except Exception as e:
                logger.warning("Failed to subscribe %s: %s", symbol, e)

    def remove_symbol(self, symbol: str) -> None:
        """Dynamically unsubscribe from a symbol / 动态取消订阅交易对"""
        if symbol not in self._symbols:
            return
        self._symbols.remove(symbol)
        with self._lock:
            self._status["subscribed_symbols"] = list(self._symbols)
        ws = self._ws
        if ws:
            try:
                unsub_msg = {"op": "unsubscribe", "args": [f"tickers.{symbol}"]}
                ws.send(json.dumps(unsub_msg))
                logger.info("Unsubscribed from %s / 已取消订阅 %s", symbol, symbol)
            except Exception as e:
                logger.warning("Failed to unsubscribe %s: %s", symbol, e)

    # ── Internal: Connection Loop / 内部：连接循环 ──

    def _run_loop(self) -> None:
        """Main connection loop with auto-reconnect / 主连接循环（含自动重连）"""
        while not self._stop_flag.is_set():
            with self._lock:
                self._status["connection_attempts"] += 1

            def on_open(ws):
                with self._lock:
                    self._status["connection_open_count"] += 1
                    self._status["connected"] = True
                # Subscribe to ticker topics for all symbols
                # 订阅所有交易对的 ticker 主题
                topics = [f"tickers.{s}" for s in self._symbols]
                sub_msg = {"op": "subscribe", "args": topics}
                ws.send(json.dumps(sub_msg))
                logger.info(
                    "Public WS connected, subscribing to %d symbols / 公共 WS 已连接，正在订阅 %d 个交易对",
                    len(topics), len(topics),
                )

            def on_message(ws, message):
                self._handle_message(message)

            def on_error(ws, error):
                with self._lock:
                    self._status["last_error"] = str(error)
                logger.warning("Public WS error: %s", error)

            def on_close(ws, code, msg):
                with self._lock:
                    self._status["connected"] = False
                logger.info("Public WS closed: code=%s msg=%s", code, msg)

            ws = websocket.WebSocketApp(
                self._ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close,
            )
            self._ws = ws

            try:
                ws.run_forever(
                    ping_interval=PING_INTERVAL,
                    ping_timeout=PING_TIMEOUT,
                )
            except Exception as e:
                with self._lock:
                    self._status["last_error"] = f"run_forever_exception: {e}"
                logger.error("Public WS run_forever exception: %s", e)

            self._ws = None

            if self._stop_flag.is_set():
                break

            logger.info(
                "Reconnecting in %ds / %d 秒后重连...",
                RECONNECT_DELAY_SEC, RECONNECT_DELAY_SEC,
            )
            self._stop_flag.wait(timeout=RECONNECT_DELAY_SEC)

        with self._lock:
            self._status["running"] = False
            self._status["connected"] = False

    # ── Internal: Message Handling / 内部：消息处理 ──

    def _handle_message(self, raw: str) -> None:
        """
        Parse and route incoming WebSocket messages / 解析并路由 WebSocket 消息

        Bybit V5 ticker message format:
        {
            "topic": "tickers.BTCUSDT",
            "type": "snapshot" | "delta",
            "ts": 1234567890123,
            "cs": ...,
            "data": {
                "symbol": "BTCUSDT",
                "lastPrice": "87654.30",
                "markPrice": "87650.12",
                "indexPrice": "87652.00",
                "bid1Price": "87654.00",
                "ask1Price": "87654.50",
                "volume24h": "12345.678",
                "turnover24h": "1082345678.90",
                "price24hPcnt": "0.0123",
                "highPrice24h": "88000.00",
                "lowPrice24h": "86000.00",
                ...
            }
        }
        """
        now_ms = int(time.time() * 1000)

        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        with self._lock:
            self._status["message_count"] += 1

        # Handle subscribe confirmation / 处理订阅确认
        if isinstance(msg, dict) and msg.get("op") == "subscribe":
            if msg.get("success"):
                with self._lock:
                    self._status["subscribe_ok_count"] += 1
                logger.info("Subscribe confirmed: %s", msg.get("req_id", ""))
            return

        # Handle ticker data / 处理 ticker 数据
        topic = msg.get("topic", "")
        if not topic.startswith("tickers."):
            return

        data = msg.get("data")
        if not data:
            return

        symbol = data.get("symbol", "")
        if not symbol:
            return

        # Parse ticker fields — Bybit sends string values
        # 解析 ticker 字段 — Bybit 以字符串形式发送数值
        try:
            last_price = float(data.get("lastPrice", 0))
        except (ValueError, TypeError):
            return

        if last_price <= 0:
            return

        event = PriceEvent(
            symbol=symbol,
            last_price=last_price,
            mark_price=_safe_float(data.get("markPrice")),
            index_price=_safe_float(data.get("indexPrice")),
            best_bid=_safe_float(data.get("bid1Price")),
            best_ask=_safe_float(data.get("ask1Price")),
            volume_24h=_safe_float(data.get("volume24h")),
            turnover_24h=_safe_float(data.get("turnover24h")),
            price_change_pct_24h=_safe_float(data.get("price24hPcnt")),
            high_24h=_safe_float(data.get("highPrice24h")),
            low_24h=_safe_float(data.get("lowPrice24h")),
            ts_ms=msg.get("ts", 0),
            receive_ts_ms=now_ms,
        )

        # Update cache / 更新缓存
        self._latest_prices[symbol] = event

        with self._lock:
            self._status["ticker_update_count"] += 1
            self._status["last_ticker_ts_ms"] = now_ms

        # Dispatch to callback / 分发给回调
        if self._on_price:
            try:
                self._on_price(event)
            except Exception as e:
                logger.error("Price callback error for %s: %s", symbol, e)


# ═══════════════════════════════════════════════════════════════════════════════
# Utility / 工具函数
# ═══════════════════════════════════════════════════════════════════════════════

def _safe_float(val: Any) -> float | None:
    """Safely convert a value to float, return None on failure / 安全转换为浮点数"""
    if val is None:
        return None
    try:
        f = float(val)
        return f if f > 0 else None
    except (ValueError, TypeError):
        return None

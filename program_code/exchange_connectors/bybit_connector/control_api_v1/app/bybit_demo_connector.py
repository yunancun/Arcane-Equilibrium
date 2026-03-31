"""
Bybit Demo Trading Connector — Execute orders on Bybit's sandbox API
Bybit Demo 交易连接器 — 在 Bybit 沙盒 API 上执行订单

MODULE_NOTE (中文):
  连接 Bybit Demo Trading API (api-demo.bybit.com)，允许策略信号在
  Bybit 的沙盒环境中执行真实模拟订单。

  与 Paper Trading Engine 的区别：
  - Paper Trading: 本地模拟，成交价/滑点/手续费全部估算
  - Demo Trading: Bybit 服务端模拟，使用真实订单簿深度，更真实

  两者并行运行，可互相验证。

MODULE_NOTE (English):
  Connects to Bybit Demo Trading API for sandbox order execution.
  Runs in parallel with local Paper Trading Engine for cross-validation.

Safety invariant:
  - 只连 Demo API (api-demo.bybit.com)，永远不连 Production
  - API key 从 secrets 文件读取，不硬编码
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
import urllib.request
import urllib.error
from typing import Any

logger = logging.getLogger(__name__)

DEMO_BASE_URL = "https://api-demo.bybit.com"
RECV_WINDOW = "5000"


def round_qty_for_exchange(qty: float) -> float:
    """
    Round qty to Bybit exchange step precision.
    四舍五入到 Bybit 交易所步長精度。

    Bybit linear perps: BTC=0.001 step (3dp), ETH=0.01 step (2dp),
    cheap tokens (price < $1) typically use integer step (1 unit).
    Heuristic: qty >= 1 → round to nearest integer; qty < 1 → round to 3dp.

    This function is shared between the demo connector and pipeline bridge
    to ensure Paper and Demo use identical qty values.
    此函數由 demo connector 和 pipeline bridge 共用，
    確保 Paper 和 Demo 使用完全相同的 qty 值。
    """
    if qty >= 1.0:
        return float(round(qty))
    return round(qty, 3)


class BybitDemoConnector:
    """
    Executes orders on Bybit Demo Trading API.
    """

    def __init__(self, api_key: str = "", api_secret: str = "") -> None:
        # Read from secrets if not provided
        if not api_key:
            key_path = os.path.expanduser("~/BybitOpenClaw/secrets/secret_files/bybit/demo/api_key")
            try:
                with open(key_path) as f:
                    api_key = f.read().strip()
            except FileNotFoundError:
                logger.warning("Bybit Demo API key not found at %s", key_path)
        if not api_secret:
            secret_path = os.path.expanduser("~/BybitOpenClaw/secrets/secret_files/bybit/demo/api_secret")
            try:
                with open(secret_path) as f:
                    api_secret = f.read().strip()
            except FileNotFoundError:
                logger.warning("Bybit Demo API secret not found at %s", secret_path)

        self._api_key = api_key
        self._api_secret = api_secret
        self._enabled = bool(api_key and api_secret)
        self._lock = threading.Lock()
        self._stats = {
            "orders_submitted": 0,
            "orders_filled": 0,
            "orders_rejected": 0,
            "errors": 0,
        }

        if self._enabled:
            logger.info("BybitDemoConnector enabled / Bybit Demo 连接器已启用")
        else:
            logger.info("BybitDemoConnector disabled (no API keys) / Bybit Demo 连接器未启用")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _sign(self, timestamp: str, params: str) -> str:
        sign_str = f"{timestamp}{self._api_key}{RECV_WINDOW}{params}"
        return hmac.new(
            self._api_secret.encode(), sign_str.encode(), hashlib.sha256
        ).hexdigest()

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a signed API request to Bybit Demo."""
        timestamp = str(int(time.time() * 1000))
        url = f"{DEMO_BASE_URL}{path}"

        if method == "GET":
            query = "&".join(f"{k}={v}" for k, v in (params or {}).items())
            signature = self._sign(timestamp, query)
            if query:
                url += f"?{query}"
            data = None
        else:
            body = json.dumps(params or {})
            signature = self._sign(timestamp, body)
            data = body.encode()

        headers = {
            "X-BAPI-API-KEY": self._api_key,
            "X-BAPI-SIGN": signature,
            "X-BAPI-TIMESTAMP": timestamp,
            "X-BAPI-RECV-WINDOW": RECV_WINDOW,
            "Content-Type": "application/json",
        }

        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            logger.error("Bybit API HTTP %d: %s", e.code, body[:200])
            return {"retCode": e.code, "retMsg": body[:200]}
        except Exception as e:
            logger.error("Bybit API request failed: %s", e)
            return {"retCode": -1, "retMsg": str(e)}

    # ── Public Methods ──

    def get_executions(self, category: str = "linear", limit: int = 50) -> dict[str, Any]:
        """Get recent executions. 获取最近成交记录。"""
        return self._request("GET", "/v5/execution/list", {"category": category, "limit": str(limit)})

    def get_wallet_balance(self) -> dict[str, Any]:
        """Get account balance."""
        return self._request("GET", "/v5/account/wallet-balance", {"accountType": "UNIFIED"})

    def get_positions(self, category: str = "linear", symbol: str = "") -> dict[str, Any]:
        """Get open positions."""
        params: dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/v5/position/list", params)

    def get_open_orders(self, category: str = "linear", symbol: str = "") -> dict[str, Any]:
        """Get open orders."""
        params: dict[str, Any] = {"category": category}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/v5/order/realtime", params)

    def submit_order(
        self,
        symbol: str,
        side: str,
        order_type: str = "Market",
        qty: float = 0.001,
        price: float | None = None,
        category: str = "linear",
        reduce_only: bool = False,
        time_in_force: str = "GTC",
    ) -> dict[str, Any]:
        """
        Submit an order to Bybit Demo.
        提交订单到 Bybit Demo。
        """
        if not self._enabled:
            return {"retCode": -1, "retMsg": "Demo connector not enabled"}

        # Round qty to exchange step precision to avoid "Qty invalid" rejections.
        # Uses shared round_qty_for_exchange() for consistency with Paper engine.
        # 四舍五入到交易所步长精度，使用共用函數確保與 Paper 一致
        qty = round_qty_for_exchange(qty)
        if qty <= 0:
            return {"retCode": -1, "retMsg": "qty rounds to zero, order skipped"}

        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type.capitalize() if order_type.lower() in ("market", "limit") else order_type,
            "qty": str(qty),
            "timeInForce": time_in_force,
        }
        if price is not None and order_type.lower() == "limit":
            params["price"] = str(price)
        if reduce_only:
            params["reduceOnly"] = True

        result = self._request("POST", "/v5/order/create", params)

        with self._lock:
            if result.get("retCode") == 0:
                self._stats["orders_submitted"] += 1
                order_id = result.get("result", {}).get("orderId", "")
                logger.info(
                    "Demo order submitted: %s %s %s qty=%s orderId=%s / Demo 订单已提交",
                    symbol, side, order_type, qty, order_id,
                )
            else:
                self._stats["orders_rejected"] += 1
                logger.warning(
                    "Demo order rejected: %s %s %s qty=%s reason=%s / Demo 订单被拒",
                    symbol, side, order_type, qty, result.get("retMsg"),
                )

        return result

    def cancel_order(self, symbol: str, order_id: str, category: str = "linear") -> dict[str, Any]:
        """Cancel an order."""
        return self._request("POST", "/v5/order/cancel", {
            "category": category, "symbol": symbol, "orderId": order_id,
        })

    # ── Batch 11: Exchange Conditional Orders (stop-loss) ──
    # Batch 11：交易所条件单（止损）— DOC-01 §5.9 双重防线

    def place_conditional_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        trigger_price: float,
        *,
        category: str = "linear",
        order_type: str = "Market",
        trigger_direction: int | None = None,
        reduce_only: bool = True,
    ) -> dict[str, Any]:
        """
        Place a conditional stop-loss order on Bybit Demo sandbox.
        在 Bybit Demo sandbox 上创建条件止损单。

        DOC-01 §5.9: Exchange conditional order = second defense line.
        Even if the local program crashes, the exchange order persists.
        即使本地程序崩溃，交易所条件单依然存在。

        Args:
            symbol: e.g. "BTCUSDT"
            side: "Buy" or "Sell" — the close side (opposite of position)
            qty: position size to close
            trigger_price: price at which the stop triggers
            category: "linear" for USDT perps
            order_type: "Market" (recommended for stops) or "Limit"
            trigger_direction: 1 = rise above trigger, 2 = fall below trigger.
                Auto-detected from side if None.
            reduce_only: True — stops should only close, never open new positions
        """
        if not self._enabled:
            return {"retCode": -1, "retMsg": "Demo connector not enabled"}

        # Auto-detect trigger direction from close side:
        #   Sell stop (close long) → triggers when price falls below → direction=2
        #   Buy stop (close short) → triggers when price rises above → direction=1
        # 自动推断触发方向
        if trigger_direction is None:
            trigger_direction = 2 if side.capitalize() == "Sell" else 1

        # Round qty same as submit_order / 四舍五入到交易所步长精度
        if qty >= 1.0:
            qty = round(qty)
        else:
            qty = round(qty, 3)
        if qty <= 0:
            return {"retCode": -1, "retMsg": "qty rounds to zero, conditional order skipped"}

        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type.capitalize() if order_type.lower() in ("market", "limit") else order_type,
            "qty": str(qty),
            "triggerPrice": str(trigger_price),
            "triggerDirection": trigger_direction,
            "reduceOnly": True,
            "timeInForce": "GTC",
            "orderFilter": "StopOrder",
        }

        result = self._request("POST", "/v5/order/create", params)

        with self._lock:
            if result.get("retCode") == 0:
                self._stats["conditional_orders_created"] = self._stats.get("conditional_orders_created", 0) + 1
                order_id = result.get("result", {}).get("orderId", "")
                logger.info(
                    "Demo CONDITIONAL stop-loss created: %s %s trigger=%.2f qty=%s orderId=%s / "
                    "Demo 条件止损单已创建",
                    symbol, side, trigger_price, qty, order_id,
                )
            else:
                self._stats["conditional_orders_failed"] = self._stats.get("conditional_orders_failed", 0) + 1
                logger.warning(
                    "Demo conditional order failed: %s %s trigger=%.2f reason=%s / "
                    "Demo 条件单创建失败",
                    symbol, side, trigger_price, result.get("retMsg"),
                )

        return result

    def cancel_all_orders(self, category: str = "linear") -> dict[str, int]:
        """
        Cancel ALL open orders on Demo (regular + conditional).
        取消 Demo 所有掛單（普通單 + 條件止損單）。

        Returns summary dict with regular_canceled and conditional_canceled counts.
        回傳取消數量摘要。
        """
        summary = {"regular_canceled": 0, "conditional_canceled": 0}
        if not self._enabled:
            return summary

        # Pass 1: Cancel all regular (limit) orders
        # 第一遍：取消所有普通掛單
        try:
            result = self._request("POST", "/v5/order/cancel-all", {
                "category": category,
            })
            if result.get("retCode") == 0:
                cancelled = result.get("result", {}).get("list", [])
                summary["regular_canceled"] = len(cancelled)
                logger.info("Demo cancel-all regular orders: %d canceled", len(cancelled))
            else:
                logger.warning("Demo cancel-all regular failed: %s", result.get("retMsg"))
        except Exception as e:
            logger.warning("Demo cancel-all regular error: %s (non-fatal)", e)

        # Pass 2: Cancel all conditional (stop) orders
        # 第二遍：取消所有條件止損單
        try:
            result = self._request("POST", "/v5/order/cancel-all", {
                "category": category,
                "orderFilter": "StopOrder",
            })
            if result.get("retCode") == 0:
                cancelled = result.get("result", {}).get("list", [])
                summary["conditional_canceled"] = len(cancelled)
                logger.info("Demo cancel-all conditional orders: %d canceled", len(cancelled))
            else:
                logger.warning("Demo cancel-all conditional failed: %s", result.get("retMsg"))
        except Exception as e:
            logger.warning("Demo cancel-all conditional error: %s (non-fatal)", e)

        return summary

    def cancel_all_conditional_orders(self, symbol: str, category: str = "linear") -> dict[str, Any]:
        """
        Cancel all conditional (stop) orders for a symbol on Demo.
        取消某个交易对的所有条件单（Demo 环境）。
        """
        if not self._enabled:
            return {"retCode": -1, "retMsg": "Demo connector not enabled"}
        return self._request("POST", "/v5/order/cancel-all", {
            "category": category,
            "symbol": symbol,
            "orderFilter": "StopOrder",
        })

    def get_conditional_orders(self, category: str = "linear", symbol: str = "") -> dict[str, Any]:
        """
        Get open conditional orders from Demo.
        获取 Demo 环境的挂起条件单。
        """
        params: dict[str, Any] = {"category": category, "orderFilter": "StopOrder"}
        if symbol:
            params["symbol"] = symbol
        return self._request("GET", "/v5/order/realtime", params)

    def get_status(self) -> dict[str, Any]:
        """Get connector status."""
        with self._lock:
            return {
                "component": "bybit_demo_connector",
                "enabled": self._enabled,
                "base_url": DEMO_BASE_URL,
                **dict(self._stats),
            }

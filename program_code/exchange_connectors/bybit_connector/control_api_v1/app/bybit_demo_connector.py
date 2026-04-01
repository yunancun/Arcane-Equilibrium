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


def round_qty_for_exchange(qty: float, category: str = "linear") -> float:
    """
    Round qty to Bybit exchange step precision.
    四捨五入到 Bybit 交易所步長精度。

    Linear perps: BTC=0.001 step, cheap tokens often use integer step.
    Inverse perps: BTCUSD step=1 (integer contracts, e.g. 100 BTCUSD).
    Spot: same heuristic as linear (base asset qty).

    Linear perp：BTC=0.001 步長，便宜幣種通常整數步長。
    Inverse perp：BTCUSD step=1（整數張數，如 100 BTCUSD）。
    Spot：同 linear 啟發式（基礎資產數量）。

    Heuristic: inverse or qty >= 1 → nearest integer; qty < 1 → 3dp.
    Inverse 或 qty >= 1 → 取整；qty < 1 → 保留 3 位小數。

    The ``category`` parameter defaults to "linear" for backwards compatibility.
    All existing callers that omit it continue to work as before.
    ``category`` 參數默認為 "linear"，確保向後兼容，現有調用者無需修改。

    This function is shared between the demo connector and pipeline bridge
    to ensure Paper and Demo use identical qty values.
    此函數由 demo connector 和 pipeline bridge 共用，
    確保 Paper 和 Demo 使用完全相同的 qty 值。
    """
    # INV-3: Inverse contracts use integer contract size (e.g. BTCUSD = 1 contract unit).
    # INV-3：Inverse 合約使用整數張數（如 BTCUSD 最小 1 張），強制取整。
    if category == "inverse" or qty >= 1.0:
        return float(round(qty))
    return round(qty, 3)


def round_price_for_exchange(price: float, tick_size: float | None = None) -> float:
    """
    Round price to exchange tick size precision.
    按交易所 tickSize 精度取整價格。

    If tick_size is provided (from SymbolCategoryRegistry), round to tick_size grid.
    Otherwise fall back to 8 decimal places (safe for all Bybit symbols).
    如果提供了 tick_size（來自 SymbolCategoryRegistry），對齊到 tick_size 網格。
    否則回退到 8 位小數（對所有 Bybit 品種安全）。

    CRITICAL: 之前硬編碼 round(..., 2) 導致低價幣（如 PIPPINUSDT $0.06）
    止損觸發價被錯誤進位到市價附近，19 秒內觸發假止損。
    CRITICAL: Previously hardcoded round(..., 2) caused low-price coins
    (e.g. PIPPINUSDT $0.06) stop trigger price to round UP to near market price,
    triggering false stop loss within 19 seconds.
    """
    if tick_size and tick_size > 0:
        # Round DOWN for long stop-loss, round UP for short stop-loss
        # This function rounds to nearest tick — caller handles direction
        # 取整到最近的 tick — 方向由調用者處理
        import math
        return round(math.floor(price / tick_size) * tick_size, 10)
    # Fallback: 8 decimal places covers all Bybit price precisions
    # 回退：8 位小數覆蓋所有 Bybit 品種的價格精度
    return round(price, 8)


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

    def set_leverage(
        self,
        symbol: str,
        buy_leverage: float,
        sell_leverage: float | None = None,
        category: str = "linear",
    ) -> dict[str, Any]:
        """
        Set leverage for a symbol on Bybit Demo before placing an order.
        在下单前为 Bybit Demo 设置每个品种的杠杆倍数。

        Bybit requires buy_leverage and sell_leverage to be set via
        POST /v5/position/set-leverage before placing leveraged orders.
        For one-way mode both values must match.
        Spot category is not supported — skipped silently.

        Bybit 的线性/反向合约需要在下单前明确设置多空两侧杠杆。
        现货品类不支持杠杆设置，静默跳过。

        retCode 110043 means "leverage not modified" (already at the target
        value) — treated as success, not an error.
        retCode 110043 表示"杠杆未变更"（已是目标值）— 视为成功。
        """
        if not self._enabled:
            return {"retCode": -1, "retMsg": "Demo connector not enabled"}

        # Spot has no leverage on Bybit — skip silently
        # 现货品类无杠杆概念，静默跳过
        if category == "spot":
            return {"retCode": 0, "retMsg": "spot: leverage not applicable"}

        if sell_leverage is None:
            sell_leverage = buy_leverage  # one-way mode: both sides must match

        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "buyLeverage": str(float(buy_leverage)),
            "sellLeverage": str(float(sell_leverage)),
        }
        result = self._request("POST", "/v5/position/set-leverage", params)

        ret_code = result.get("retCode")
        if ret_code == 0:
            logger.info(
                "Demo leverage set: %s category=%s leverage=%.1fx / Demo 杠杆已设置",
                symbol, category, buy_leverage,
            )
        elif ret_code == 110043:
            # "leverage not modified" — already at target value, not an error
            # 杠杆未变更（已是目标值），非错误
            logger.debug(
                "Demo leverage unchanged (already at %.1fx): %s",
                buy_leverage, symbol,
            )
        else:
            logger.warning(
                "Demo set-leverage failed: %s category=%s leverage=%.1fx reason=%s / "
                "Demo 设置杠杆失败",
                symbol, category, buy_leverage, result.get("retMsg"),
            )
        return result

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
        # Pass category so inverse contracts are correctly rounded to integers.
        # 四捨五入到交易所步長精度，使用共用函數確保與 Paper 一致。
        # 傳入 category 確保 inverse 合約正確取整（整數張數）。
        qty = round_qty_for_exchange(qty, category=category)
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

    def cancel_all_orders(self, category: str = "all") -> dict[str, int]:
        """
        Cancel ALL open orders on Demo across all active categories (regular + conditional).
        取消 Demo 所有品類的掛單（普通單 + 條件止損單）。

        When category="all" (default), iterates linear/spot/inverse to ensure complete cleanup.
        category="all" 時遍歷 linear/spot/inverse，確保不遺漏任何品類。

        Returns summary dict with regular_canceled and conditional_canceled counts.
        回傳各品類取消數量匯總。
        """
        summary = {"regular_canceled": 0, "conditional_canceled": 0}
        if not self._enabled:
            return summary

        categories = ["linear", "spot", "inverse"] if category == "all" else [category]

        # settle coin required for /v5/order/cancel-all StopOrder on linear/inverse
        # Bybit cancel-all for stop orders needs settleCoin for linear, baseCoin for inverse
        # 條件止損取消時 linear 需要 settleCoin，inverse 需要 baseCoin
        _settle: dict[str, str] = {"linear": "USDT", "inverse": "BTC"}

        for cat in categories:
            # Pass 1: Cancel all regular (limit/market) orders
            # 第一遍：取消所有普通掛單
            try:
                result = self._request("POST", "/v5/order/cancel-all", {"category": cat})
                if result.get("retCode") == 0:
                    n = len(result.get("result", {}).get("list", []))
                    summary["regular_canceled"] += n
                    if n:
                        logger.info("Demo cancel-all regular [%s]: %d canceled", cat, n)
                else:
                    logger.warning("Demo cancel-all regular [%s] failed: %s", cat, result.get("retMsg"))
            except Exception as e:
                logger.warning("Demo cancel-all regular [%s] error: %s (non-fatal)", cat, e)

            # Pass 2: Cancel all conditional (stop) orders
            # 第二遍：取消所有條件止損單
            try:
                params: dict[str, Any] = {"category": cat, "orderFilter": "StopOrder"}
                if cat in _settle:
                    params[_settle_key := "settleCoin" if cat == "linear" else "baseCoin"] = _settle[cat]
                result = self._request("POST", "/v5/order/cancel-all", params)
                if result.get("retCode") == 0:
                    n = len(result.get("result", {}).get("list", []))
                    summary["conditional_canceled"] += n
                    if n:
                        logger.info("Demo cancel-all conditional [%s]: %d canceled", cat, n)
                else:
                    logger.warning("Demo cancel-all conditional [%s] failed: %s", cat, result.get("retMsg"))
            except Exception as e:
                logger.warning("Demo cancel-all conditional [%s] error: %s (non-fatal)", cat, e)

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

        Bybit V5 /v5/order/realtime requires at least one of symbol/settleCoin/baseCoin
        for linear category. We add settleCoin=USDT as default for linear so the query
        succeeds without a specific symbol. Without this the API returns retCode=10001.
        Bybit V5 linear 分类需要至少传 symbol/settleCoin/baseCoin 之一，
        否则返回 retCode=10001。此处默认加 settleCoin=USDT 确保查询成功。
        """
        params: dict[str, Any] = {"category": category, "orderFilter": "StopOrder", "limit": 50}
        if symbol:
            params["symbol"] = symbol
        elif category == "linear":
            params["settleCoin"] = "USDT"  # Required for linear without symbol
        elif category == "inverse":
            params["settleCoin"] = "BTC"   # Default settle coin for inverse
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

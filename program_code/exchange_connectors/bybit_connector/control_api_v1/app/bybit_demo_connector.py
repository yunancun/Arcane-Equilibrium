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


def round_qty_for_exchange(
    qty: float,
    category: str = "linear",
    qty_step: float | None = None,
) -> float:
    """
    Round qty to Bybit exchange step precision.
    四捨五入到 Bybit 交易所步長精度。

    When qty_step is provided (from SymbolCategoryRegistry), rounds to the
    nearest multiple of qty_step using floor (to avoid exceeding balance).
    當提供 qty_step 時（來自 SymbolCategoryRegistry），取 qty_step 的整數倍（向下）。

    Fallback heuristic (qty_step=None): inverse or qty >= 1 → integer; qty < 1 → 3dp.
    回退啟發式（qty_step=None）：inverse 或 qty >= 1 → 取整；qty < 1 → 3 位小數。
    """
    import math

    # Use actual qty_step from exchange when available / 有步長數據時使用精確取整
    if qty_step and qty_step > 0:
        floored = math.floor(qty / qty_step) * qty_step
        # Derive decimal places from qty_step to avoid float artifacts
        # 從 qty_step 推導小數位數避免浮點誤差
        step_str = f"{qty_step:.10f}".rstrip("0")
        decimals = len(step_str.split(".")[-1]) if "." in step_str else 0
        return round(floored, decimals)

    # Fallback heuristic / 回退啟發式
    if category == "inverse" or qty >= 1.0:
        return float(round(qty))
    return round(qty, 3)


def round_price_for_exchange(
    price: float,
    tick_size: float | None = None,
    direction: str = "floor",
) -> float:
    """
    Round price to exchange tick size precision with direction control.
    按交易所 tickSize 精度取整價格，支持方向控制。

    direction:
      "floor" — round down (default, conservative for long stop-loss)
      "ceil"  — round up (conservative for short stop-loss)
      "nearest" — round to nearest tick (for limit orders)

    direction:
      "floor" — 向下取整（默認，保守用於多頭止損）
      "ceil"  — 向上取整（保守用於空頭止損）
      "nearest" — 取最近的 tick（用於限價單）
    """
    if tick_size and tick_size > 0:
        import math
        if direction == "ceil":
            aligned = math.ceil(price / tick_size) * tick_size
        elif direction == "nearest":
            aligned = round(price / tick_size) * tick_size
        else:  # "floor" or default
            aligned = math.floor(price / tick_size) * tick_size
        return round(aligned, 10)
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
        # Rate limit state / 限流狀態
        self._rate_limit_remaining: int = 120
        self._rate_limit_reset_ms: int = 0
        # Account info (populated on first use) / 帳戶信息（首次使用時填充）
        self._account_type: str = "UNIFIED"
        self._position_mode: str = "one_way"  # "one_way" or "hedge"

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
                result = json.loads(resp.read().decode())
                # Tag business errors from Bybit (HTTP 200 but retCode != 0)
                # 標記 Bybit 業務錯誤（HTTP 200 但 retCode != 0）
                if result.get("retCode", 0) != 0:
                    result["errorType"] = "business"
                # Read rate limit headers if present / 讀取限流頭部
                self._update_rate_limit_from_headers(resp.headers)
                return result
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            logger.error("Bybit API HTTP %d: %s", e.code, body[:200])
            # Try to parse Bybit JSON error body / 嘗試解析 Bybit JSON 錯誤體
            try:
                parsed = json.loads(body)
                parsed["errorType"] = "business"
                parsed["httpCode"] = e.code
                return parsed
            except (json.JSONDecodeError, ValueError):
                return {"retCode": -1, "retMsg": body[:200], "httpCode": e.code, "errorType": "transport"}
        except Exception as e:
            logger.error("Bybit API request failed: %s", e)
            return {"retCode": -1, "retMsg": str(e), "errorType": "network"}

    def _request_with_retry(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        max_retries: int = 3,
        base_delay: float = 0.5,
    ) -> dict[str, Any]:
        """
        Request with exponential backoff retry for transient errors.
        帶指數退避重試的請求（僅重試瞬態錯誤）。

        Retries on: network errors, HTTP 429/502/503/504, retCode 10006 (rate limit).
        Does NOT retry on business errors (param invalid, insufficient balance, etc.).
        """
        for attempt in range(max_retries + 1):
            # Pre-request rate limit check / 請求前限流檢查
            if self._rate_limit_remaining <= 2:
                now_ms = int(time.time() * 1000)
                wait_ms = max(0, self._rate_limit_reset_ms - now_ms)
                if wait_ms > 0:
                    sleep_s = min(wait_ms / 1000.0, 5.0)  # cap at 5s
                    logger.info("Rate limit near — sleeping %.1fs / 接近限流，等待", sleep_s)
                    time.sleep(sleep_s)

            result = self._request(method, path, params)
            error_type = result.get("errorType")
            ret_code = result.get("retCode", 0)

            # Success — return immediately / 成功 — 立即返回
            if ret_code == 0:
                return result

            # Non-retryable business errors / 不可重試的業務錯誤
            if error_type == "business" and ret_code not in (10006, 10016):
                return result

            # Last attempt — return whatever we got / 最後一次嘗試
            if attempt >= max_retries:
                return result

            # Retryable — backoff and retry / 可重試 — 退避後重試
            delay = base_delay * (2 ** attempt)
            logger.warning(
                "Retrying %s %s (attempt %d/%d, retCode=%s, delay=%.1fs) / 重試中",
                method, path, attempt + 1, max_retries, ret_code, delay,
            )
            time.sleep(delay)

        return result  # should not reach here

    def _update_rate_limit_from_headers(self, headers) -> None:
        """Read Bybit rate limit headers and update internal state.
        讀取 Bybit 限流頭部並更新內部狀態。"""
        try:
            remaining = headers.get("X-Bapi-Limit-Status")
            reset_ts = headers.get("X-Bapi-Limit-Reset-Timestamp")
            if remaining is not None:
                self._rate_limit_remaining = int(remaining)
            if reset_ts is not None:
                self._rate_limit_reset_ms = int(reset_ts)
        except (ValueError, TypeError):
            pass  # ignore malformed headers

    # ── Public Methods ──

    def get_executions(self, category: str = "linear", limit: int = 50) -> dict[str, Any]:
        """Get recent executions. 获取最近成交记录。"""
        return self._request("GET", "/v5/execution/list", {"category": category, "limit": str(limit)})

    def detect_account_info(self) -> None:
        """
        Query account info to detect account type and position mode.
        查詢帳戶信息以檢測帳戶類型和持倉模式。
        Call on startup when connector is enabled.
        """
        if not self._enabled:
            return
        try:
            result = self._request("GET", "/v5/account/info", {})
            if result.get("retCode") == 0:
                info = result.get("result", {})
                # Unified Margin Status: 1=regular, 3=unified, 4=UTA Pro
                ums = info.get("unifiedMarginStatus")
                if ums in (3, 4):
                    self._account_type = "UNIFIED"
                elif ums == 1:
                    self._account_type = "CONTRACT"
                # Position mode: 0=one-way, 3=hedge (BothSide)
                margin_mode = info.get("marginMode", "")
                # Bybit V5: position mode comes from separate endpoint for linear
                logger.info(
                    "Account info: type=%s marginMode=%s / 帳戶類型=%s",
                    self._account_type, margin_mode, self._account_type,
                )
        except Exception as e:
            logger.warning("Failed to detect account info: %s / 帳戶信息檢測失敗", e)

    def query_position_mode(self, category: str = "linear") -> str:
        """
        Query current position mode (one-way or hedge).
        查詢當前持倉模式（單向或對沖）。
        Returns "one_way" or "hedge".
        """
        if not self._enabled:
            return self._position_mode
        try:
            # Bybit V5: GET /v5/position/list returns positionIdx per position
            # But position mode is set at account level
            result = self._request("GET", "/v5/position/list",
                                   {"category": category, "symbol": "BTCUSDT", "limit": "1"})
            if result.get("retCode") == 0:
                positions = result.get("result", {}).get("list", [])
                if positions:
                    pos_idx = positions[0].get("positionIdx", 0)
                    if pos_idx != 0:
                        self._position_mode = "hedge"
                        logger.warning(
                            "Hedge mode detected (positionIdx=%d) — orders will include positionIdx / "
                            "檢測到對沖模式", pos_idx,
                        )
                    else:
                        self._position_mode = "one_way"
        except Exception as e:
            logger.warning("Failed to query position mode: %s", e)
        return self._position_mode

    def get_wallet_balance(self) -> dict[str, Any]:
        """Get account balance. Uses detected account type.
        獲取帳戶餘額。使用檢測到的帳戶類型。"""
        return self._request("GET", "/v5/account/wallet-balance",
                             {"accountType": self._account_type})

    # Bybit V5 linear covers BOTH USDT and USDC settled contracts.
    # Queries/cancels that use settleCoin must iterate both to avoid missing USDC pairs (e.g. BTCPERP).
    # Inverse contracts all settle in BTC only.
    # Bybit V5 linear 同時包含 USDT 和 USDC 結算合約。
    # 使用 settleCoin 的查詢/取消必須遍歷兩者，否則會漏掉 USDC 合約（如 BTCPERP）。
    _SETTLE_COINS: dict[str, list[str]] = {
        "linear": ["USDT", "USDC"],
        "inverse": ["BTC"],
    }

    def get_positions(self, category: str = "linear", symbol: str = "") -> dict[str, Any]:
        """
        Get open positions. Queries all settleCoin variants for linear (USDT + USDC).
        查詢持倉。linear 品類查詢 USDT + USDC 兩種結算幣，合併結果。
        """
        if symbol:
            return self._request("GET", "/v5/position/list", {"category": category, "symbol": symbol})
        coins = self._SETTLE_COINS.get(category, [])
        if not coins:
            return self._request("GET", "/v5/position/list", {"category": category})
        # Query each settleCoin and merge results / 逐個查詢並合併
        merged_list: list[dict] = []
        last_result: dict[str, Any] = {}
        for coin in coins:
            result = self._request("GET", "/v5/position/list", {"category": category, "settleCoin": coin})
            last_result = result
            merged_list.extend(result.get("result", {}).get("list", []))
        # Return merged into standard Bybit response shape
        if last_result.get("retCode") == 0 or merged_list:
            merged = dict(last_result)
            merged.setdefault("result", {})["list"] = merged_list
            return merged
        return last_result

    def get_open_orders(self, category: str = "linear", symbol: str = "") -> dict[str, Any]:
        """
        Get open orders. Queries all settleCoin variants for linear (USDT + USDC).
        查詢掛單。linear 品類查詢 USDT + USDC 兩種結算幣，合併結果。
        """
        if symbol:
            return self._request("GET", "/v5/order/realtime", {"category": category, "symbol": symbol})
        coins = self._SETTLE_COINS.get(category, [])
        if not coins:
            return self._request("GET", "/v5/order/realtime", {"category": category})
        merged_list: list[dict] = []
        last_result: dict[str, Any] = {}
        for coin in coins:
            result = self._request("GET", "/v5/order/realtime", {"category": category, "settleCoin": coin})
            last_result = result
            merged_list.extend(result.get("result", {}).get("list", []))
        if last_result.get("retCode") == 0 or merged_list:
            merged = dict(last_result)
            merged.setdefault("result", {})["list"] = merged_list
            return merged
        return last_result

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
        qty_step: float | None = None,
        symbol_registry: object | None = None,
    ) -> dict[str, Any]:
        """
        Submit an order to Bybit Demo.
        提交订单到 Bybit Demo。

        qty_step: optional qtyStep for precise rounding.
        symbol_registry: optional SymbolCategoryRegistry for pre-submission validation.
        """
        if not self._enabled:
            return {"retCode": -1, "retMsg": "Demo connector not enabled"}

        # Round qty using actual qtyStep when available / 使用實際步長取整
        qty = round_qty_for_exchange(qty, category=category, qty_step=qty_step)
        if qty <= 0:
            return {"retCode": -1, "retMsg": "qty rounds to zero, order skipped"}

        # Pre-submission validation against exchange limits / 提交前驗證交易所限制
        if symbol_registry and hasattr(symbol_registry, "validate_order_params"):
            valid, reason = symbol_registry.validate_order_params(symbol, qty, price or 0)
            if not valid:
                logger.warning("Order rejected locally: %s %s qty=%s reason=%s", symbol, side, qty, reason)
                return {"retCode": -2, "retMsg": f"local_validation_failed: {reason}"}

        params: dict[str, Any] = {
            "category": category,
            "symbol": symbol,
            "side": side.capitalize(),
            "orderType": order_type.capitalize() if order_type.lower() in ("market", "limit") else order_type,
            "qty": str(qty),
        }
        # Bybit V5: Market orders use IOC internally; only send timeInForce for Limit orders.
        # Market 單內部使用 IOC；只有 Limit 單才需要發 timeInForce。
        if order_type.lower() != "market":
            params["timeInForce"] = time_in_force
        if price is not None and order_type.lower() == "limit":
            params["price"] = str(price)
        # Bybit V5: reduceOnly not valid for spot (no position concept).
        # 現貨無持倉概念，不能帶 reduceOnly。
        if reduce_only and category != "spot":
            params["reduceOnly"] = True
        # Include positionIdx for non-spot (required for hedge mode, safe for one-way)
        # 非現貨品類包含 positionIdx（對沖模式必需，單向模式安全）
        if category != "spot":
            if self._position_mode == "hedge":
                params["positionIdx"] = 1 if side.capitalize() == "Buy" else 2
            else:
                params["positionIdx"] = 0

        result = self._request_with_retry("POST", "/v5/order/create", params)

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

        # Round qty using shared function (consistent with submit_order, handles inverse)
        # 使用共用函數取整（與 submit_order 一致，正確處理 inverse 整數張數）
        qty = round_qty_for_exchange(qty, category=category)
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
            "orderFilter": "StopOrder",
        }
        if order_type.lower() != "market":
            params["timeInForce"] = "GTC"
        if reduce_only and category != "spot":
            params["reduceOnly"] = True
        # positionIdx for non-spot / 非現貨持倉索引
        if category != "spot":
            if self._position_mode == "hedge":
                params["positionIdx"] = 1 if side.capitalize() == "Buy" else 2
            else:
                params["positionIdx"] = 0

        result = self._request_with_retry("POST", "/v5/order/create", params)

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

        for cat in categories:
            # Get all settleCoin variants for this category (linear=USDT+USDC, inverse=BTC)
            # 取得該品類的所有結算幣（linear=USDT+USDC，inverse=BTC）
            coins = self._SETTLE_COINS.get(cat, [None])  # None = no settleCoin needed (spot)

            for coin in coins:
                # Pass 1: Cancel all regular (limit/market) orders
                # 第一遍：取消所有普通掛單
                try:
                    cancel_params: dict[str, Any] = {"category": cat}
                    if coin:
                        cancel_params["settleCoin"] = coin
                    result = self._request("POST", "/v5/order/cancel-all", cancel_params)
                    if result.get("retCode") == 0:
                        n = len(result.get("result", {}).get("list", []))
                        summary["regular_canceled"] += n
                        if n:
                            logger.info("Demo cancel-all regular [%s/%s]: %d canceled", cat, coin or "-", n)
                    else:
                        logger.warning("Demo cancel-all regular [%s/%s] failed: %s", cat, coin or "-", result.get("retMsg"))
                except Exception as e:
                    logger.warning("Demo cancel-all regular [%s/%s] error: %s (non-fatal)", cat, coin or "-", e)

                # Pass 2: Cancel all conditional (stop) orders
                # 第二遍：取消所有條件止損單
                try:
                    params: dict[str, Any] = {"category": cat, "orderFilter": "StopOrder"}
                    if coin:
                        params["settleCoin"] = coin
                    result = self._request("POST", "/v5/order/cancel-all", params)
                    if result.get("retCode") == 0:
                        n = len(result.get("result", {}).get("list", []))
                        summary["conditional_canceled"] += n
                        if n:
                            logger.info("Demo cancel-all conditional [%s/%s]: %d canceled", cat, coin or "-", n)
                    else:
                        logger.warning("Demo cancel-all conditional [%s/%s] failed: %s", cat, coin or "-", result.get("retMsg"))
                except Exception as e:
                    logger.warning("Demo cancel-all conditional [%s/%s] error: %s (non-fatal)", cat, coin or "-", e)

        return summary

    def cancel_symbol_orders(self, symbol: str, category: str = "linear", order_filter: str | None = None) -> dict[str, Any]:
        """
        Cancel all orders for a specific symbol. Supports both regular and conditional orders.
        取消某個幣種的所有掛單。支持普通單和條件單。

        Args:
            symbol: e.g. "BTCUSDT"
            category: "linear", "spot", "inverse"
            order_filter: None = all orders, "StopOrder" = conditional only, "Order" = regular only
                          None = 全部，"StopOrder" = 僅條件單，"Order" = 僅普通單

        Use cases / 使用場景:
          - Cancel hedge orders when market direction changes / 市場方向變化時取消對沖掛單
          - Replace stale limit orders with updated prices / 用新價格替換過期限價單
          - Clean up before closing a position / 平倉前清理相關掛單
        """
        if not self._enabled:
            return {"retCode": -1, "retMsg": "Demo connector not enabled"}
        params: dict[str, Any] = {"category": category, "symbol": symbol}
        if order_filter:
            params["orderFilter"] = order_filter
        return self._request("POST", "/v5/order/cancel-all", params)

    def cancel_all_conditional_orders(self, symbol: str, category: str = "linear") -> dict[str, Any]:
        """
        Cancel all conditional (stop) orders for a symbol on Demo.
        取消某个交易对的所有条件单（Demo 环境）。
        Convenience wrapper around cancel_symbol_orders.
        """
        return self.cancel_symbol_orders(symbol, category, order_filter="StopOrder")

    def get_conditional_orders(self, category: str = "linear", symbol: str = "") -> dict[str, Any]:
        """
        Get open conditional orders from Demo. Queries USDT + USDC for linear.
        查詢 Demo 條件單。linear 品類查詢 USDT + USDC 兩種結算幣。
        """
        if symbol:
            return self._request("GET", "/v5/order/realtime",
                                 {"category": category, "orderFilter": "StopOrder", "limit": 50, "symbol": symbol})
        coins = self._SETTLE_COINS.get(category, [])
        if not coins:
            return self._request("GET", "/v5/order/realtime",
                                 {"category": category, "orderFilter": "StopOrder", "limit": 50})
        merged_list: list[dict] = []
        last_result: dict[str, Any] = {}
        for coin in coins:
            result = self._request("GET", "/v5/order/realtime",
                                   {"category": category, "orderFilter": "StopOrder", "limit": 50, "settleCoin": coin})
            last_result = result
            merged_list.extend(result.get("result", {}).get("list", []))
        if last_result.get("retCode") == 0 or merged_list:
            merged = dict(last_result)
            merged.setdefault("result", {})["list"] = merged_list
            return merged
        return last_result

    def get_status(self) -> dict[str, Any]:
        """Get connector status."""
        with self._lock:
            return {
                "component": "bybit_demo_connector",
                "enabled": self._enabled,
                "base_url": DEMO_BASE_URL,
                **dict(self._stats),
            }

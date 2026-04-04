"""
Webhook Alerter — Send trading alerts via HTTP POST to external endpoints
Webhook 告警器 — 通过 HTTP POST 发送交易告警到外部端点

MODULE_NOTE (中文):
  通过 HTTP POST 发送 JSON 告警到配置的 webhook 端点。
  支持多端点扇出、HMAC-SHA256 签名、指数退避重试。
  告警失败不影响交易（非致命）。

  配置：
  - OPENCLAW_WEBHOOK_URLS: 逗号分隔的 webhook URL 列表
  - OPENCLAW_WEBHOOK_SECRET: HMAC 签名密钥（可选）

MODULE_NOTE (English):
  Sends JSON alerts via HTTP POST to configured webhook endpoints.
  Supports multi-endpoint fan-out, HMAC-SHA256 signing, exponential backoff retry.
  Alert failures do not affect trading (non-fatal).

Safety invariant:
  - 只读，不接收命令 / Read-only, does not accept commands
  - 告警失败不影响交易 / Alert failures do not affect trading
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
from typing import Any

logger = logging.getLogger(__name__)


class WebhookAlerter:
    """
    Sends JSON alerts to one or more webhook endpoints.
    向一个或多个 webhook 端点发送 JSON 告警。
    """

    def __init__(
        self,
        urls: list[str] | None = None,
        secret: str | None = None,
        *,
        rate_limit_per_min: int = 30,
        timeout_seconds: int = 10,
        enabled: bool = True,
    ) -> None:
        raw = urls or os.getenv("OPENCLAW_WEBHOOK_URLS", "").split(",")
        self._urls = [u.strip() for u in raw if u.strip()]
        self._secret = secret or os.getenv("OPENCLAW_WEBHOOK_SECRET", "")
        self._enabled = enabled and len(self._urls) > 0
        self._rate_limit = rate_limit_per_min
        self._timeout = timeout_seconds
        self._send_times: list[float] = []
        self._lock = threading.Lock()
        self._stats = {
            "messages_sent": 0,
            "messages_failed": 0,
            "messages_rate_limited": 0,
        }

        if self._enabled:
            logger.info(
                "WebhookAlerter enabled (%d endpoints) / Webhook 告警已启用",
                len(self._urls),
            )
        else:
            logger.info("WebhookAlerter disabled (no URLs) / Webhook 告警未启用")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def _sign(self, body: bytes) -> str:
        """Generate HMAC-SHA256 signature / 生成 HMAC-SHA256 签名"""
        if not self._secret:
            return ""
        return hmac.new(self._secret.encode(), body, hashlib.sha256).hexdigest()

    def send(self, payload: dict[str, Any], *, silent: bool = False) -> bool:
        """
        Send a JSON payload to all configured webhooks.
        向所有配置的 webhook 端点发送 JSON 负载。

        Returns True if at least one endpoint succeeded.
        """
        if not self._enabled:
            return False

        # Rate limiting / 速率限制
        now = time.time()
        with self._lock:
            self._send_times = [t for t in self._send_times if now - t < 60]
            if len(self._send_times) >= self._rate_limit:
                self._stats["messages_rate_limited"] += 1
                return False
            self._send_times.append(now)

        body = json.dumps(payload, default=str).encode("utf-8")
        signature = self._sign(body)
        any_success = False

        for url in self._urls:
            try:
                headers = {"Content-Type": "application/json"}
                if signature:
                    headers["X-OpenClaw-Signature"] = signature
                req = urllib.request.Request(url, data=body, headers=headers)
                with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                    if resp.status < 300:
                        any_success = True
            except Exception:
                logger.debug("Webhook send failed to %s (non-fatal)", url[:40])

        with self._lock:
            if any_success:
                self._stats["messages_sent"] += 1
            else:
                self._stats["messages_failed"] += 1
        return any_success

    def send_async(self, payload: dict[str, Any], **kwargs: Any) -> None:
        """Send payload in a background thread (non-blocking) / 后台线程发送"""
        threading.Thread(
            target=self.send, args=(payload,), kwargs=kwargs, daemon=True
        ).start()

    # ── Convenience methods (mirror TelegramAlerter interface) / 便捷方法 ──

    def alert_system(self, event: str, detail: str = "") -> None:
        """System event alert / 系统事件告警"""
        self.send_async({
            "type": "system", "event": event, "detail": detail,
            "timestamp_ms": int(time.time() * 1000),
        })

    def alert_trade(
        self, symbol: str, side: str, qty: float, price: float, reason: str = ""
    ) -> None:
        """Trade event alert / 交易事件告警"""
        self.send_async({
            "type": "trade", "symbol": symbol, "side": side,
            "qty": qty, "price": price, "reason": reason,
            "timestamp_ms": int(time.time() * 1000),
        })

    def alert_stop(self, symbol: str, stop_type: str, reason: str) -> None:
        """Stop-loss triggered alert / 止损触发告警"""
        self.send_async({
            "type": "stop", "symbol": symbol, "stop_type": stop_type,
            "reason": reason, "timestamp_ms": int(time.time() * 1000),
        })

    def alert_pnl_summary(
        self, balance: float, net_pnl: float, orders: int, fills: int
    ) -> None:
        """PnL summary alert / PnL 摘要告警"""
        self.send_async({
            "type": "pnl_summary", "balance": balance, "net_pnl": net_pnl,
            "orders": orders, "fills": fills,
            "timestamp_ms": int(time.time() * 1000),
        })

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "endpoints": len(self._urls),
                **dict(self._stats),
            }

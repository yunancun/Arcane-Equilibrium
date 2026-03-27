"""
Telegram Alerter — Send trading alerts via Telegram Bot API
Telegram 告警器 — 通过 Telegram Bot API 发送交易告警

MODULE_NOTE (中文):
  通过 Telegram Bot API 发送系统告警。告警类型：
  1. 系统状态：WebSocket 断连 / 重连 / 服务启动停止
  2. 交易事件：订单成交 / 订单拒绝 / 止损触发
  3. PnL 报告：每小时 PnL 摘要 / 日度报告
  4. 策略事件：策略激活/停止 / 信号共识变化

  配置：
  - OPENCLAW_TELEGRAM_BOT_TOKEN: Bot API Token
  - OPENCLAW_TELEGRAM_CHAT_ID: 目标 Chat ID

MODULE_NOTE (English):
  Sends system alerts via Telegram Bot API. Alert types:
  1. System: WebSocket disconnect/reconnect, service start/stop
  2. Trading: order fills, rejections, stop triggers
  3. PnL: hourly summary, daily report
  4. Strategy: activation/stop, signal consensus changes

Safety invariant:
  - 只读，不接收命令 / Read-only, does not accept commands
  - 告警失败不影响交易 / Alert failures do not affect trading
"""

from __future__ import annotations

import logging
import os
import threading
import time
import urllib.request
import urllib.parse
import json
from typing import Any

logger = logging.getLogger(__name__)


class TelegramAlerter:
    """
    Sends alerts to Telegram via Bot API.
    通过 Bot API 发送 Telegram 告警。
    """

    def __init__(
        self,
        bot_token: str | None = None,
        chat_id: str | None = None,
        *,
        rate_limit_per_min: int = 20,
        enabled: bool = True,
    ) -> None:
        self._token = bot_token or os.getenv("OPENCLAW_TELEGRAM_BOT_TOKEN", "")
        self._chat_id = chat_id or os.getenv("OPENCLAW_TELEGRAM_CHAT_ID", "")
        self._enabled = enabled and bool(self._token) and bool(self._chat_id)
        self._rate_limit = rate_limit_per_min
        self._send_times: list[float] = []
        self._lock = threading.Lock()
        self._stats = {
            "messages_sent": 0,
            "messages_failed": 0,
            "messages_rate_limited": 0,
        }

        if self._enabled:
            logger.info("TelegramAlerter enabled (chat_id=%s) / Telegram 告警已启用", self._chat_id)
        else:
            logger.info("TelegramAlerter disabled (no token or chat_id) / Telegram 告警未启用")

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def send(self, message: str, *, parse_mode: str = "HTML", silent: bool = False) -> bool:
        """
        Send a message to the configured Telegram chat.
        发送消息到配置的 Telegram 聊天。

        Returns True if sent successfully, False otherwise.
        """
        if not self._enabled:
            return False

        # Rate limiting
        now = time.time()
        with self._lock:
            self._send_times = [t for t in self._send_times if now - t < 60]
            if len(self._send_times) >= self._rate_limit:
                self._stats["messages_rate_limited"] += 1
                return False
            self._send_times.append(now)

        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            payload = json.dumps({
                "chat_id": self._chat_id,
                "text": message,
                "parse_mode": parse_mode,
                "disable_notification": silent,
            }).encode("utf-8")

            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())

            if result.get("ok"):
                with self._lock:
                    self._stats["messages_sent"] += 1
                return True
            else:
                logger.warning("Telegram API error: %s", result.get("description"))
                with self._lock:
                    self._stats["messages_failed"] += 1
                return False

        except Exception:
            logger.debug("Telegram send failed (non-fatal)")
            with self._lock:
                self._stats["messages_failed"] += 1
            return False

    def send_async(self, message: str, **kwargs: Any) -> None:
        """Send message in a background thread (non-blocking) / 后台线程发送"""
        threading.Thread(target=self.send, args=(message,), kwargs=kwargs, daemon=True).start()

    # ── Convenience methods / 便捷方法 ──

    def alert_system(self, event: str, detail: str = "") -> None:
        """System event alert / 系统事件告警"""
        msg = f"🔧 <b>System</b>\n{event}"
        if detail:
            msg += f"\n<i>{detail}</i>"
        self.send_async(msg)

    def alert_trade(self, symbol: str, side: str, qty: float, price: float, reason: str = "") -> None:
        """Trade event alert / 交易事件告警"""
        emoji = "📈" if side == "Buy" else "📉"
        msg = f"{emoji} <b>{side} {symbol}</b>\nQty: {qty}\nPrice: ${price:,.2f}"
        if reason:
            msg += f"\n{reason}"
        self.send_async(msg)

    def alert_stop(self, symbol: str, stop_type: str, reason: str) -> None:
        """Stop-loss triggered alert / 止损触发告警"""
        msg = f"🛑 <b>STOP: {stop_type}</b>\n{symbol}\n{reason}"
        self.send_async(msg)

    def alert_pnl_summary(self, balance: float, net_pnl: float, orders: int, fills: int) -> None:
        """PnL summary alert / PnL 摘要告警"""
        emoji = "✅" if net_pnl >= 0 else "⚠️"
        msg = (
            f"{emoji} <b>PnL Summary</b>\n"
            f"Balance: ${balance:,.2f}\n"
            f"Net PnL: ${net_pnl:,.4f}\n"
            f"Orders: {orders} | Fills: {fills}"
        )
        self.send_async(msg, silent=True)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "enabled": self._enabled,
                "chat_id": self._chat_id[:4] + "..." if self._chat_id else "",
                **dict(self._stats),
            }

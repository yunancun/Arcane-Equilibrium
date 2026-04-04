"""
Alert Router — Multi-channel alert fan-out (Telegram + Webhook)
告警路由器 — 多通道告警扇出（Telegram + Webhook）

MODULE_NOTE (中文):
  统一告警分发：将系统/交易/PnL/止损告警同时发送到 Telegram 和 Webhook。
  每个通道独立失败不影响另一通道。支持按严重级别过滤。

MODULE_NOTE (English):
  Unified alert dispatch: fans out system/trade/PnL/stop alerts to both
  Telegram and Webhook channels. Each channel fails independently.
  Supports severity-based filtering.

Safety invariant:
  - 告警失败不影响交易 / Alert failures do not affect trading
  - 每个通道独立 / Each channel independent
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .telegram_alerter import TelegramAlerter
from .webhook_alerter import WebhookAlerter

logger = logging.getLogger(__name__)


class AlertRouter:
    """
    Fans out alerts to multiple channels (Telegram + Webhook).
    将告警扇出到多个通道。
    """

    def __init__(
        self,
        telegram: Optional[TelegramAlerter] = None,
        webhook: Optional[WebhookAlerter] = None,
    ) -> None:
        self._telegram = telegram
        self._webhook = webhook
        active = []
        if telegram and telegram.is_enabled:
            active.append("telegram")
        if webhook and webhook.is_enabled:
            active.append("webhook")
        logger.info("AlertRouter initialized: %s / 告警路由器已初始化", active or ["none"])

    def alert_system(self, event: str, detail: str = "") -> None:
        """System event → all channels / 系统事件 → 全通道"""
        if self._telegram:
            self._telegram.alert_system(event, detail)
        if self._webhook:
            self._webhook.alert_system(event, detail)

    def alert_trade(
        self, symbol: str, side: str, qty: float, price: float, reason: str = ""
    ) -> None:
        """Trade event → all channels / 交易事件 → 全通道"""
        if self._telegram:
            self._telegram.alert_trade(symbol, side, qty, price, reason)
        if self._webhook:
            self._webhook.alert_trade(symbol, side, qty, price, reason)

    def alert_stop(self, symbol: str, stop_type: str, reason: str) -> None:
        """Stop trigger → all channels / 止损触发 → 全通道"""
        if self._telegram:
            self._telegram.alert_stop(symbol, stop_type, reason)
        if self._webhook:
            self._webhook.alert_stop(symbol, stop_type, reason)

    def alert_pnl_summary(
        self, balance: float, net_pnl: float, orders: int, fills: int
    ) -> None:
        """PnL summary → all channels / PnL 摘要 → 全通道"""
        if self._telegram:
            self._telegram.alert_pnl_summary(balance, net_pnl, orders, fills)
        if self._webhook:
            self._webhook.alert_pnl_summary(balance, net_pnl, orders, fills)

    def get_stats(self) -> dict[str, Any]:
        """Combined stats from all channels / 所有通道的合併統計"""
        return {
            "telegram": self._telegram.get_stats() if self._telegram else None,
            "webhook": self._webhook.get_stats() if self._webhook else None,
        }

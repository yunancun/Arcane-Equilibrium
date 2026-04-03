"""
Batch 7 — Strategist Fast Channel: emergency intent builder
=============================================================

MODULE_NOTE (中文):
  Strategist 快速通道 — 從 strategist_agent.py 提取。
  處理緊急風控觸發的確定性行動（<10ms）。
  構建 close_all / flash_crash / reduce_all 觸發的 TradeIntent 列表。

MODULE_NOTE (English):
  Strategist fast channel — extracted from strategist_agent.py.
  Handles deterministic risk-driven actions on emergency triggers (<10ms).
  Builds TradeIntent lists for close_all / flash_crash / reduce_all triggers.

Safety invariants / 安全不變量:
  - Pure function: no side effects, no state mutation
    純函數：無副作用、不修改狀態
  - Caller (StrategistAgent) manages _emergency_mode flag and queue
    調用者 (StrategistAgent) 管理 _emergency_mode 標誌和隊列
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, List

logger = logging.getLogger(__name__)


def build_emergency_intents(
    trigger: str,
    symbols: list[str],
    TradeIntent: type,
) -> list:
    """
    Build emergency TradeIntents for fast channel triggers.
    構建快速通道觸發的緊急 TradeIntent。

    Args:
        trigger: "close_all" / "flash_crash" / "reduce_all"
                 觸發類型
        symbols: Target symbols to act on
                 目標交易對列表
        TradeIntent: The TradeIntent class (passed to avoid circular import)
                     TradeIntent 類（透過參數傳入避免循環導入）

    Returns:
        List of emergency TradeIntents / 緊急 TradeIntent 列表
    """
    intents: list = []

    for symbol in symbols:
        if trigger in ("close_all", "flash_crash"):
            # Close all positions — maximum urgency
            # 全平持倉 — 最高緊急度
            direction = "close"
            confidence = 1.0
            thesis = f"Emergency {trigger} triggered / 緊急 {trigger} 觸發"
        elif trigger == "reduce_all":
            # Reduce positions — high urgency but not full close
            # 減倉 — 高緊急度但非全平
            direction = "reduce"
            confidence = 0.9
            thesis = f"Emergency reduce_all triggered / 緊急減倉觸發"
        else:
            # Unknown trigger — skip (fail-closed: don't fabricate intents)
            # 未知觸發 — 跳過（fail-closed：不捏造 intent）
            logger.warning(
                "Unknown fast channel trigger: %s, skipping symbol %s / "
                "未知快速通道觸發：%s，跳過 %s",
                trigger, symbol, trigger, symbol,
            )
            continue

        intent = TradeIntent(
            symbol=symbol,
            strategy="fast_channel",
            direction=direction,
            size=0.0,  # size determined by Executor based on current position
            confidence=confidence,
            thesis=thesis,
            invalidation_condition="N/A — emergency override",
            metadata={
                "intent_id": f"fast:{uuid.uuid4().hex[:8]}",
                "source": "fast_channel",
                "trigger": trigger,
                "priority": 1,
            },
        )
        intents.append(intent)

    return intents

"""Guardian handler implementation for AIService.
AIService Guardian handler 實作。

Extracted from ``ai_service_dispatch.py`` by TIER4-AI-SERVICE-DISPATCH-SPLIT.
由 TIER4-AI-SERVICE-DISPATCH-SPLIT 自 ``ai_service_dispatch.py`` 抽出。
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from . import ai_service as core

logger = logging.getLogger(__name__)


async def handle_guardian(service: Any, params: dict[str, Any]) -> dict[str, Any]:
    """
    Guardian L1 information layer: classify market events via Ollama.
    守衛 L1 信息層：通過 Ollama 分類市場事件。

    IMPORTANT: This is INFORMATIONAL ONLY — does NOT block trades.
    重要：這僅是信息層 — 不阻擋交易。
    Trade blocking authority stays entirely in Rust Guardian (4-check deterministic).
    交易阻擋權完全在 Rust Guardian（4 項確定性檢查）。

    Input from Rust:
      params.event = {event_type, severity, description, affected_symbols}
      params.check_type = "event_classification" (B4: informational)

    Returns: classification result with risk_level and assessment.
    返回：包含 risk_level 和 assessment 的分類結果。

    Fail-closed: Ollama unavailable → classify as severity from input (conservative).
    失敗關閉：Ollama 不可用 → 使用輸入的 severity 分類（保守）。
    """
    service._stats["guardian_calls"] += 1

    event = params.get("event", params.get("intent", {}))
    check_type = params.get("check_type", "event_classification")
    event_type = event.get("event_type", "unknown")
    severity = event.get("severity", "medium")
    description = event.get("description", "")
    affected_symbols = event.get("affected_symbols", [])
    symbol = event.get("symbol", affected_symbols[0] if affected_symbols else "unknown")

    ollama = await asyncio.to_thread(core._get_ollama_client)

    # Default: use input severity as risk_level (fail-closed conservative)
    # 默認：使用輸入 severity 作為 risk_level（失敗關閉保守）
    risk_level = severity
    assessment = f"Fallback classification from input severity: {severity}"
    source = "heuristic"

    if ollama is not None and await ollama.is_available_async():
        try:
            classify_text = (
                f"Event type: {event_type}\n"
                f"Severity reported: {severity}\n"
                f"Description: {description}\n"
                f"Affected symbols: {', '.join(affected_symbols) if affected_symbols else 'unknown'}"
            )
            response = await asyncio.to_thread(
                ollama.generate,
                classify_text,
                system=core._GUARDIAN_SYSTEM_PROMPT,
                temperature=0.1,
                max_tokens=128,
                timeout=4,
                think=False,
            )
            if response.success:
                parsed = service._parse_guardian_response(response.text, severity)
                risk_level = parsed["risk_level"]
                assessment = parsed["assessment"]
                source = "ollama_l1"
            else:
                logger.debug(
                    "Guardian Ollama call unsuccessful, using fallback / "
                    "守衛 Ollama 調用未成功，使用回退"
                )
        except Exception as exc:
            logger.warning(
                "Guardian classification error (fallback to severity): %s / "
                "守衛分類錯誤（回退到 severity）: %s",
                str(exc)[:100], str(exc)[:100],
            )

    logger.info(
        "Guardian L1: event=%s risk=%s source=%s / 守衛 L1：event=%s risk=%s",
        event_type, risk_level, source, event_type, risk_level,
    )

    # B4: Relay high/critical events to agents via MessageBus (informational)
    # B4：通過 MessageBus 將高/嚴重事件中繼給其他 Agent（信息用途）
    if risk_level in ("high", "critical") and service._message_bus is not None:
        try:
            from .multi_agent_framework import (
                AgentMessage,
                AgentRole,
                MessageType,
            )
            alert_msg = AgentMessage(
                sender=AgentRole.GUARDIAN,
                receiver=AgentRole.STRATEGIST,
                message_type=MessageType.EVENT_ALERT,
                priority=1,
                payload={
                    "event_type": event_type,
                    "severity": severity,
                    "risk_level": risk_level,
                    "assessment": assessment,
                    "affected_symbols": affected_symbols,
                    "source": "guardian_l1_ipc",
                },
            )
            service._message_bus.send(alert_msg)
            logger.info(
                "Guardian L1: relayed %s event to Strategist via MessageBus / "
                "守衛 L1：已通過 MessageBus 將 %s 事件中繼給策略師",
                risk_level, risk_level,
            )
        except Exception as relay_exc:
            # Fail-open: relay failure does not block classification response
            # 失敗開放：中繼失敗不阻擋分類回應
            logger.warning("Guardian MessageBus relay failed (fail-open): %s", relay_exc)

    return {
        "status": "checked",
        "agent": "guardian",
        "symbol": symbol,
        "check_type": check_type,
        "risk_level": risk_level,
        "assessment": assessment,
        "event_type": event_type,
        "affected_symbols": affected_symbols,
        "source": source,
        # NOT a trade verdict — informational only
        # 非交易裁決 — 僅信息用途
        "is_informational": True,
    }


def parse_guardian_response(text: str, fallback_severity: str) -> dict[str, str]:
    """Parse Ollama guardian classification response. / 解析 Ollama 守衛分類回應。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    valid_levels = ("low", "medium", "high", "critical")
    try:
        result = json.loads(text)
        level = str(result.get("risk_level", fallback_severity)).lower()
        if level not in valid_levels:
            level = fallback_severity
        return {
            "risk_level": level,
            "assessment": str(result.get("assessment", "AI classification"))[:200],
        }
    except (json.JSONDecodeError, AttributeError):
        # Try single-word response (like classify() output)
        # 嘗試單詞回應（類似 classify() 輸出）
        word = text.strip().lower()
        if word in valid_levels:
            return {"risk_level": word, "assessment": f"Classified as {word}"}
        return {"risk_level": fallback_severity, "assessment": f"Parse failed, fallback: {fallback_severity}"}

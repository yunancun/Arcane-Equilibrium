"""
Batch 7 — StrategistAgent Cognitive / Fast Channel Sibling
============================================================
Governance refs: EX-06 §4 / CLAUDE.md §九 file-size discipline / G3-08 Phase 4

MODULE_NOTE (中文):
  本模組是 StrategistAgent 的 sibling，承載「V2 雙軌快速通道」與「認知調製器整合」
  相關的 4 個方法，從 strategist_agent.py 拆出以維持主檔在 §九 800 行警告線之下。
  函數一律接受 ``agent: StrategistAgent`` 作為第一個參數。

  涵蓋方法：
  1. handle_fast_channel — V2 緊急通道（reduce_all/close_all/flash_crash），
                           設置 _emergency_mode 阻斷正常通道
  2. clear_emergency_mode — 緊急模式清除，正常通道恢復
  3. set_cognitive_modulator — CognitiveModulator 注入（決策門檻調整來源）
  4. _apply_cognitive_modulation — 將 (confidence_floor, qty_ceiling) 套用到 confidence

MODULE_NOTE (English):
  StrategistAgent sibling carrying 4 methods around "V2 dual-track fast channel"
  and "CognitiveModulator integration". Extracted from strategist_agent.py so
  the main file stays under the §九 800-line warning threshold.
  Functions take ``agent: StrategistAgent`` as the first parameter.

  Covered methods:
  1. handle_fast_channel — V2 emergency channel (reduce_all/close_all/flash_crash),
                           sets _emergency_mode to block normal channel
  2. clear_emergency_mode — clear emergency mode, normal channel resumes
  3. set_cognitive_modulator — inject CognitiveModulator (decision-threshold source)
  4. _apply_cognitive_modulation — apply (confidence_floor, qty_ceiling) to confidence

Hard boundaries (CLAUDE.md §四):
  - 緊急模式為 fail-closed 邊界（emergency mode is a fail-closed boundary）— 觸發後
    必須由 clear_emergency_mode 顯式關閉，避免 stale intent 在緊急時段流入。
  - 認知調製 ≠ 能力限制（cognitive modulation != capability restriction），詳 §二
    根原則 #11 衍生準則。Modulator 缺失時返回 (config.min_confidence, 1.0) 透傳。
  - 不變動業務邏輯，只搬位置 (no business-logic change, location-only refactor).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, List

from .multi_agent_framework import TradeIntent
from .strategist_fast_channel import build_emergency_intents

if TYPE_CHECKING:  # pragma: no cover — type-checker only / 僅型別檢查
    from .strategist_agent import StrategistAgent

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# V2 Dual-track Fast Channel / 雙軌快速通道
# ─────────────────────────────────────────────────────────────────────────────

def handle_fast_channel(
    agent: "StrategistAgent",
    trigger: str,
    symbols: list[str] | None = None,
) -> List[TradeIntent]:
    """
    V2 Fast channel: deterministic risk-driven actions (<10ms).
    V2 快速通道：確定性風控驅動的行動（<10ms）。

    Triggers: risk_governor >= DEFENSIVE -> reduce_all / close_all / flash_crash
    觸發條件：risk_governor >= DEFENSIVE -> 減倉/全平/閃崩保護

    Sets _emergency_mode flag to block normal channel, then generates pre-defined
    intents. Normal channel checks this flag before emitting.
    設置 _emergency_mode 標誌阻斷正常通道，然後生成預定義 intent。
    正常通道在發射前檢查此標誌。

    Args:
        trigger: Action type — "reduce_all" / "close_all" / "flash_crash"
        symbols: Specific symbols to act on (None = all)

    Returns:
        List of emergency TradeIntents
    """
    # Set emergency mode — blocks normal channel
    # 設置緊急模式 — 阻斷正常通道
    agent._emergency_mode.set()

    with agent._lock:
        # Clear normal channel queue (stale intents are dangerous during emergency)
        # 清空正常通道隊列（緊急時期過期 intent 是危險的）
        agent._normal_queue.clear()

        # Delegate intent construction to extracted module
        # 委託提取的模組構建 intent
        target_symbols = symbols or []
        emergency_intents = build_emergency_intents(
            trigger=trigger,
            symbols=target_symbols,
            TradeIntent=TradeIntent,
        )

        agent._pending_intents.extend(emergency_intents)
        agent._stats["intents_produced"] += len(emergency_intents)

        logger.warning(
            "Fast channel triggered: %s, %d intents generated / "
            "快速通道觸發：%s，生成 %d 個 intent",
            trigger, len(emergency_intents), trigger, len(emergency_intents),
        )

        return emergency_intents


def clear_emergency_mode(agent: "StrategistAgent") -> None:
    """
    V2: Clear emergency mode after fast channel actions are processed.
    V2：快速通道行動處理完畢後清除緊急模式。

    Normal channel resumes accepting signals after this call.
    此調用後正常通道恢復接收信號。
    """
    agent._emergency_mode.clear()
    logger.info("Emergency mode cleared, normal channel resumed / 緊急模式清除，正常通道恢復")


# ─────────────────────────────────────────────────────────────────────────────
# CognitiveModulator integration / 認知調製器整合
# ─────────────────────────────────────────────────────────────────────────────

def set_cognitive_modulator(agent: "StrategistAgent", modulator: Any) -> None:
    """
    V2: Inject CognitiveModulator for decision threshold adjustment.
    V2：注入 CognitiveModulator 用於決策門檻調整。

    Principle: cognitive modulation != capability restriction (see root principle derivative).
    原則：認知調製 != 能力限制（見根原則衍生準則）。
    """
    agent._cognitive_modulator = modulator
    logger.info(
        "CognitiveModulator injected into StrategistAgent / "
        "認知調製器已注入 StrategistAgent"
    )


def _apply_cognitive_modulation(
    agent: "StrategistAgent",
    confidence: float,
) -> tuple[float, float]:
    """
    V2: Apply CognitiveModulator thresholds to confidence and qty.
    V2：應用認知門檻調製到信心和倉位。

    Returns (adjusted_min_confidence, qty_ceiling_multiplier).
    返回 (調整後最低信心門檻, 倉位上限乘數)。

    If no modulator is injected, returns default config values (bypass).
    若未注入調製器，返回默認配置值（跳過）。
    """
    if agent._cognitive_modulator is None:
        return (agent.config.min_confidence, 1.0)

    try:
        params = agent._cognitive_modulator.get_current_params()
        conf_floor = params.get("confidence_floor", agent.config.min_confidence)
        qty_ceil = params.get("qty_ceiling", 1.0)
        return (conf_floor, qty_ceil)
    except Exception as e:
        logger.warning(
            "CognitiveModulator error, using defaults: %s / "
            "認知調製器錯誤，使用默認值: %s", e, e,
        )
        return (agent.config.min_confidence, 1.0)

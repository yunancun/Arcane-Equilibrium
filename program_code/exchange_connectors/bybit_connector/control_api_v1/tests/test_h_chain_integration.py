"""
Principle 14 Integration Tests — Zero-Cost Fallback (Ollama Unavailable)
=========================================================================
根原則 14 集成測試：Ollama 不可用時系統退化到 L0/啟發式模式，交易鏈路不中斷。

MODULE_NOTE (中文):
  本測試文件驗證根原則 14「零外部成本可運行」的核心承諾：
  - Ollama（L1 本地推理）崩潰或不可用時，系統必須自動退化到 L0 確定性模式
  - 退化後交易鏈路（H0 Gate → GovernanceHub → PipelineBridge → ExecutorAgent）
    不得中斷，各守門組件仍可正常工作
  - 退化路徑必須是保守的（fail-closed），不允許 allow-all 或直接放行未評估信號

MODULE_NOTE (English):
  This test file validates the core promise of Principle 14 (zero external cost):
  - When Ollama (L1 local inference) crashes or is unavailable, the system must
    automatically degrade to L0 deterministic mode.
  - After degradation, the trading pipeline (H0 Gate → GovernanceHub →
    PipelineBridge → ExecutorAgent) must NOT be interrupted.
  - The degradation path must be conservative (fail-closed): no allow-all,
    no passing unevaluated signals through.

Governance refs:
  DOC-01 §5.14 (Principle 14): zero external cost operation
  DOC-02 §3:   H0 Gate deterministic gating, <1ms SLA
  EX-06 §4:    StrategistAgent fallback to heuristic when Ollama unavailable
"""

from __future__ import annotations

import sys
import os
import time
import unittest
from unittest.mock import MagicMock, patch

# Ensure app is importable / 確保 app 可導入
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.strategist_agent import StrategistAgent, StrategistConfig, _heuristic_evaluate
from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    IntelObject,
    MessageBus,
    MessageType,
    DataQualityLevel,
    SentimentScore,
)
from app.h0_gate import H0Gate, H0GateConfig, H0GateRiskSnapshot, H0GateHealthSnapshot


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════

def _make_intel_message(
    *,
    relevance_score: float = 0.8,
    freshness_seconds: int = 30,
    symbols: list | None = None,
    sentiment: SentimentScore = SentimentScore.POSITIVE,
    data_quality: DataQualityLevel = DataQualityLevel.FACT,
) -> AgentMessage:
    """
    Build a valid INTEL_OBJECT AgentMessage for test injection.
    構造用於測試注入的合法 INTEL_OBJECT 消息。
    """
    if symbols is None:
        symbols = ["BTCUSDT"]
    return AgentMessage(
        sender=AgentRole.SCOUT,
        receiver=AgentRole.STRATEGIST,
        message_type=MessageType.INTEL_OBJECT,
        priority=3,
        payload={
            "intel_id": "test_intel_001",
            "source": "test_source",
            "timestamp_ms": int(time.time() * 1000),
            "freshness_seconds": freshness_seconds,
            "data_quality": data_quality.value,
            "sentiment": sentiment.value,
            "relevance_score": relevance_score,
            "content": "BTC breakout signal detected.",
            "symbols": symbols,
            "metadata": {},
        },
    )


def _make_strategist(
    *,
    ollama_available: bool = True,
    shadow: bool = False,
    cost_tracker=None,
) -> tuple[StrategistAgent, MagicMock]:
    """
    Build a StrategistAgent with a controlled mock OllamaClient.
    構造帶有受控 Mock OllamaClient 的 StrategistAgent。

    Returns (agent, mock_ollama_client).
    """
    mock_ollama = MagicMock()
    mock_ollama.is_available.return_value = ollama_available
    # Ensure judge_edge is not called when Ollama is unavailable
    # 確保 Ollama 不可用時 judge_edge 不被調用
    mock_ollama.judge_edge.return_value = MagicMock(success=False, error="unavailable")

    config = StrategistConfig(shadow=shadow, min_confidence=0.3)
    agent = StrategistAgent(
        config=config,
        ollama_client=mock_ollama,
        cost_tracker=cost_tracker,
    )
    agent.start()
    return agent, mock_ollama


# ═══════════════════════════════════════════════════════════════════════════════
# TestPrinciple14OllamaFallback
# ═══════════════════════════════════════════════════════════════════════════════

class TestPrinciple14OllamaFallback(unittest.TestCase):
    """
    Integration tests for Principle 14: zero-cost fallback when Ollama is unavailable.
    根原則 14 集成測試：Ollama 不可用時系統退化到 L0/啟發式模式，交易鏈路不中斷。

    All tests use MagicMock — no real Ollama connection is required.
    所有測試均使用 MagicMock，不需要真實 Ollama 連接。
    """

    # ── Test 1: Strategist uses heuristic when Ollama is unavailable ──────────

    def test_ollama_unavailable_strategist_uses_heuristic(self):
        """
        When OllamaClient.is_available()=False, StrategistAgent must:
        1. Not call judge_edge() (no AI call attempted)
        2. Fall back to _heuristic_evaluate() (heuristic_evaluations counter increments)
        3. System does not crash

        Ollama 不可用時，StrategistAgent 必須：
        1. 不調用 judge_edge()（不嘗試 AI 調用）
        2. 回退到 _heuristic_evaluate()（heuristic_evaluations 計數器遞增）
        3. 系統不崩潰
        """
        agent, mock_ollama = _make_strategist(ollama_available=False)

        # Deliver a high-quality intel message / 投遞高質量情報消息
        msg = _make_intel_message(relevance_score=0.9, freshness_seconds=10)
        agent.on_message(msg)

        # Verify: judge_edge must NOT have been called / 確認 judge_edge 絕對不被調用
        mock_ollama.judge_edge.assert_not_called()

        # Verify: heuristic path was used / 確認走了啟發式評估路徑
        with agent._lock:
            heuristic_count = agent._stats["heuristic_evaluations"]
        self.assertGreaterEqual(heuristic_count, 1,
            "heuristic_evaluations should be >= 1 when Ollama is unavailable")

    # ── Test 2: H1 budget check passes (fail-open) when cost_tracker is None ─

    def test_ollama_unavailable_h1_budget_check_passes(self):
        """
        When cost_tracker is None (Ollama unavailable / not configured), the H1 budget
        check must return True (fail-open), allowing the rest of the pipeline to run.

        This prevents budget tracking failures from blocking all trade evaluation.

        cost_tracker=None 時 H1 budget check 必須返回 True（fail-open），
        確保成本追蹤組件不存在時不會阻塞整條評估鏈路。
        """
        agent, _ = _make_strategist(ollama_available=False, cost_tracker=None)

        # Direct unit-level assertion on _h1_check_budget()
        # 直接測試 _h1_check_budget() 的行為
        result = agent._h1_check_budget()
        self.assertTrue(result,
            "_h1_check_budget() must return True (fail-open) when cost_tracker is None")

    # Test 3 (PipelineBridge) deleted (DEAD-PY-2)


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)

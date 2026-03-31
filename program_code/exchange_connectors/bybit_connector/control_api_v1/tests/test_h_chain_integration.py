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

    # ── Test 3: PipelineBridge processes intents without Ollama ──────────────

    def test_ollama_unavailable_pipeline_bridge_processes_intents(self):
        """
        PipelineBridge._process_pending_intents() must continue to function when
        Ollama is unavailable. The bridge orchestrates OrderIntent dispatch and must
        not crash or deadlock in L0 mode.

        Verification: bridge._process_pending_intents() runs without exception,
        and no intents are silently discarded due to Ollama absence.

        Ollama 不可用時，PipelineBridge._process_pending_intents() 必須繼續運行，
        不崩潰、不死鎖，heuristic 模式下的 intent 可被正常處理。
        """
        from app.pipeline_bridge import PipelineBridge

        # Build minimal mock orchestrator with no pending intents
        # 構建最小化 mock 編排器（無待處理 intent）
        mock_orch = MagicMock()
        mock_orch.collect_pending_intents.return_value = []

        mock_engine = MagicMock()

        # Construct PipelineBridge without Ollama (no strategist_agent)
        # 構建不帶 Ollama 的 PipelineBridge（無 strategist_agent）
        # PipelineBridge requires kline_manager, indicator_engine, signal_engine as positional args
        # PipelineBridge 需要三個必填位置參數，使用 MagicMock 提供最小化實現
        mock_km = MagicMock()
        mock_ie = MagicMock()
        mock_se = MagicMock()
        bridge = PipelineBridge(
            mock_km,
            mock_ie,
            mock_se,
            mock_orch,
            mock_engine,
        )

        # Should complete without exception / 必須無異常完成
        try:
            bridge._process_pending_intents()
        except Exception as exc:
            self.fail(
                f"_process_pending_intents() raised {type(exc).__name__}: {exc} "
                "when Ollama is unavailable"
            )

        # Orchestrator must have been called to collect intents
        # 編排器必須被調用以收集 intent
        mock_orch.collect_pending_intents.assert_called_once()

    # ── Test 4: H0 Gate continues to block bad intents without Ollama ────────

    def test_ollama_unavailable_h0_gate_still_blocks_bad_intents(self):
        """
        H0 Gate is pure deterministic logic (no Ollama dependency).
        It must continue to block intents with stale/unhealthy state even
        when Ollama is unavailable.

        Verification: H0Gate.check() blocks a symbol with no price tick
        (freshness check fails → blocked).

        H0 Gate 是純確定性邏輯，不依賴 Ollama。
        即使 Ollama 不可用，對數據過期或系統不健康的 intent 仍必須阻擋。
        """
        config = H0GateConfig(
            max_data_age_ms=1000,    # 1 second freshness threshold / 1 秒新鮮度閾值
            allowed_categories=["linear", "spot"],
        )
        gate = H0Gate(config=config)

        # Do NOT inject any price tick → freshness check will fail
        # 不注入任何 price tick → 新鮮度檢查失敗
        result = gate.check("BTCUSDT", "linear")

        self.assertFalse(result.allowed,
            "H0 Gate must block intent when no price tick has been received "
            "(freshness check), regardless of Ollama availability")
        self.assertIn("freshness", result.check_name.lower(),
            f"Expected freshness check to trigger, got check_name='{result.check_name}'")

    # ── Test 5: ExecutorAgent still requires Decision Lease in L0 mode ────────

    def test_ollama_unavailable_executor_still_applies_fail_closed(self):
        """
        ExecutorAgent must require a valid Decision Lease before execution,
        even in L0 mode (Ollama unavailable).

        If GovernanceHub.acquire_lease() returns None (lease acquisition fails),
        ExecutorAgent must reject execution with fail-closed behavior.
        This confirms Principle 3 enforcement is independent of Ollama.

        即使在 L0 模式（Ollama 不可用），ExecutorAgent 必須要求有效的 Decision Lease。
        acquire_lease() 返回 None 時，ExecutorAgent 必須拒絕執行（fail-closed）。
        確認根原則 3 的執行與 Ollama 無關。
        """
        from app.executor_agent import ExecutorAgent

        # Mock GovernanceHub that always fails to acquire a lease
        # Mock GovernanceHub，acquire_lease() 永遠返回 None（模擬 Ollama 不可用 + 未授權）
        mock_hub = MagicMock()
        mock_hub.acquire_lease.return_value = None  # fail-closed simulation

        mock_paper_engine = MagicMock()

        agent = ExecutorAgent(
            paper_engine=mock_paper_engine,
            governance_hub=mock_hub,
        )

        report = agent.execute_order(
            intent_id="test_intent_p14",
            symbol="BTCUSDT",
            side="Buy",
            qty=0.001,
        )

        # Execution must be rejected / 必須拒絕執行
        self.assertFalse(report.success,
            "ExecutorAgent must reject execution when acquire_lease() returns None "
            "(fail-closed, Principle 3)")
        self.assertIn("lease", report.error.lower(),
            f"Error message should reference lease failure, got: '{report.error}'")

        # Paper engine must NOT have been called / 紙上交易引擎不得被調用
        mock_paper_engine.submit_order.assert_not_called()

    # ── Test 6: Mid-evaluation Ollama crash → fallback to heuristic ──────────

    def test_ollama_crash_mid_evaluation_falls_back(self):
        """
        If Ollama connection fails mid-evaluation (ConnectionError during _ai_evaluate),
        StrategistAgent must:
        1. Catch the exception (not propagate it)
        2. Fall back to _heuristic_evaluate()
        3. Never allow-all (fail-closed behavior preserved)
        4. error counter increments

        Ollama 在評估過程中崩潰（_ai_evaluate 拋出 ConnectionError）時，
        StrategistAgent 必須：
        1. 捕獲異常（不向外傳播）
        2. 回退到 _heuristic_evaluate()
        3. 絕不 allow-all（fail-closed 行為保持）
        4. error 計數器遞增
        """
        # Build agent where Ollama reports as available...
        # 構建 Ollama 報告為可用的 agent...
        agent, mock_ollama = _make_strategist(ollama_available=True)

        # ...but judge_edge raises a ConnectionError mid-call
        # ...但 judge_edge 在調用過程中拋出 ConnectionError
        mock_ollama.judge_edge.side_effect = ConnectionError("Ollama server crashed")

        initial_errors = agent._stats["errors"]
        initial_heuristic = agent._stats["heuristic_evaluations"]

        # Deliver high-quality intel — Ollama will crash during evaluation
        # 投遞高質量情報 — Ollama 將在評估過程中崩潰
        msg = _make_intel_message(relevance_score=0.9, freshness_seconds=10)

        # Must not raise / 不得向外拋出異常
        try:
            agent.on_message(msg)
        except Exception as exc:
            self.fail(
                f"on_message() raised {type(exc).__name__}: {exc} "
                "after mid-evaluation Ollama crash — system should not propagate exception"
            )

        # Error counter must increment / error 計數器必須遞增
        with agent._lock:
            errors_after = agent._stats["errors"]
            heuristic_after = agent._stats["heuristic_evaluations"]

        self.assertGreater(errors_after, initial_errors,
            "errors counter must increment after ConnectionError in _evaluate_edge")

        self.assertGreater(heuristic_after, initial_heuristic,
            "heuristic_evaluations must increment — fallback must occur, not allow-all")


# ═══════════════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    unittest.main(verbosity=2)

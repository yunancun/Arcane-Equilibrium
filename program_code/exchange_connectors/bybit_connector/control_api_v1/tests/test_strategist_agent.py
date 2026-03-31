"""
Sprint 5a — TestScoutStrategistChain: Scout → Strategist chain end-to-end verification
========================================================================================
Sprint 5a：Scout→Strategist 情報鏈路端到端驗證測試

Tests verify:
- Mock MessageBus sends INTEL_OBJECT → _handle_intel() is called
- _stats["intel_received"] increments after message receipt
測試確認：
- Mock MessageBus 發送 INTEL_OBJECT → _handle_intel() 被調用
- 收到消息後 _stats["intel_received"] 遞增
"""

import sys
import os
import unittest
from unittest.mock import MagicMock, patch

# Ensure app is importable / 確保 app 可導入
_test_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_test_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)

from app.multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    IntelObject,
    MessageBus,
    MessageType,
    ScoutAgent,
    ScoutConfig,
    SentimentScore,
    DataQualityLevel,
)
from app.strategist_agent import StrategistAgent, StrategistConfig


# ═══════════════════════════════════════════════════════════════════════════════
# TestScoutStrategistChain
# Scout → Strategist 情報鏈路端到端驗證
# ═══════════════════════════════════════════════════════════════════════════════

class TestScoutStrategistChain(unittest.TestCase):
    """
    End-to-end verification of the Scout → MessageBus → Strategist chain.
    Scout → MessageBus → Strategist 鏈路端到端驗證。

    Uses Mock MessageBus to isolate transport, verifying that:
    1. INTEL_OBJECT message delivery triggers _handle_intel()
    2. _stats["intel_received"] counter increments on receipt
    使用 Mock MessageBus 隔離傳輸層，確認：
    1. INTEL_OBJECT 消息到達後 _handle_intel() 被調用
    2. 收到消息後 _stats["intel_received"] 計數器遞增
    """

    def _make_intel_message(self, relevance_score: float = 0.7) -> AgentMessage:
        """
        Build a valid INTEL_OBJECT AgentMessage for test injection.
        構建用於測試注入的有效 INTEL_OBJECT AgentMessage。
        """
        intel = IntelObject(
            source="test_scout",
            content="BTC strong uptrend detected",
            symbols=["BTCUSDT"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.POSITIVE,
            relevance_score=relevance_score,
            freshness_seconds=2,
            metadata={"price": 65000.0},
        )
        return AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            priority=3,
            payload=intel.to_dict(),
        )

    def test_intel_object_triggers_handle_intel(self):
        """
        Mock MessageBus delivers INTEL_OBJECT → _handle_intel() is invoked.
        Mock MessageBus 遞送 INTEL_OBJECT → _handle_intel() 必須被調用。

        Verifies Node 4 of the chain: on_message() routes INTEL_OBJECT to _handle_intel().
        驗證鏈路節點 4：on_message() 將 INTEL_OBJECT 路由至 _handle_intel()。
        """
        # Create Strategist in running state with a real MessageBus
        # 使用真實 MessageBus 建立運行中的 Strategist
        bus = MessageBus()
        strategist = StrategistAgent(
            config=StrategistConfig(shadow=True, min_relevance=0.3),
            message_bus=bus,
        )
        strategist.start()  # sets state = RUNNING
        bus.subscribe(AgentRole.STRATEGIST, strategist.on_message)

        # Spy on _handle_intel by wrapping it
        # 通過包裝監視 _handle_intel 是否被調用
        original_handle_intel = strategist._handle_intel
        call_record = []

        def spy_handle_intel(msg):
            call_record.append(msg)
            return original_handle_intel(msg)

        strategist._handle_intel = spy_handle_intel

        # Deliver an INTEL_OBJECT message via the bus
        # 通過消息總線遞送 INTEL_OBJECT
        msg = self._make_intel_message(relevance_score=0.7)
        bus.send(msg)

        # _handle_intel must have been called once
        # _handle_intel 必須被調用一次
        self.assertEqual(
            len(call_record), 1,
            "_handle_intel was not called after INTEL_OBJECT was sent via MessageBus"
        )
        self.assertEqual(
            call_record[0].message_type, MessageType.INTEL_OBJECT,
            "Message type passed to _handle_intel should be INTEL_OBJECT"
        )

    def test_intel_received_counter_increments(self):
        """
        _stats["intel_received"] increments when Strategist receives an INTEL_OBJECT.
        Strategist 收到 INTEL_OBJECT 後 _stats["intel_received"] 必須遞增。

        Verifies Node 5 of the chain: the counter is observable evidence that
        intel data flowed through the pipeline successfully.
        驗證鏈路節點 5：計數器遞增是情報成功流經管線的可觀察憑據。
        """
        bus = MessageBus()
        strategist = StrategistAgent(
            config=StrategistConfig(shadow=True, min_relevance=0.3),
            message_bus=bus,
        )
        strategist.start()
        bus.subscribe(AgentRole.STRATEGIST, strategist.on_message)

        # Capture baseline counter before sending any message
        # 在發送消息前記錄基準計數器值
        stats_before = strategist.get_stats()
        baseline = stats_before.get("intel_received", 0)

        # Send one INTEL_OBJECT with relevance above threshold
        # 發送一條高於 threshold 的 INTEL_OBJECT
        msg = self._make_intel_message(relevance_score=0.8)
        bus.send(msg)

        # Counter must have incremented by exactly 1
        # 計數器必須恰好遞增 1
        stats_after = strategist.get_stats()
        after_count = stats_after.get("intel_received", 0)
        self.assertEqual(
            after_count, baseline + 1,
            f"Expected intel_received to increment from {baseline} to {baseline + 1}, "
            f"got {after_count}"
        )



# ═══════════════════════════════════════════════════════════════════════════════
# TestH1ThoughtGate
# H1 ThoughtGate 三路門控（預算 / 複雜度 / 冷卻期）測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestH1ThoughtGate(unittest.TestCase):
    """
    Tests for H1 ThoughtGate: budget, complexity, and cooldown checks.
    H1 思考閘門測試：預算門控、複雜度評分、冷卻期檢查。

    Verifies:
    1. Budget exceeded → h1_budget_skip increments, heuristic path used (not allow-all)
    2. Low complexity intel → h1_complexity_skip increments
    3. Same symbol within 30s → h1_cooldown_skip increments
    4. All H1 checks pass → _evaluate_edge() called
    5. _evaluate_edge() raises TimeoutError → heuristic fallback (existing except coverage)
    6. H2: cost_tracker budget OK → evaluate_edge called
    7. H2: cost_tracker budget exceeded → heuristic walked
    8. H2: cost_tracker=None → normal execution (fail-open)
    9. H3: low complexity → l1_9b route
    10. H3: medium complexity → l1_27b route
    11. H3: high complexity → l2 thread spawned, heuristic used as immediate result
    """

    def _make_strategist(self, cost_tracker=None) -> StrategistAgent:
        """
        Create a running StrategistAgent for testing.
        建立用於測試的運行中 StrategistAgent。
        """
        agent = StrategistAgent(
            config=StrategistConfig(
                shadow=True,
                min_relevance=0.3,
                heuristic_min_relevance=0.0,  # ensure heuristic can pass in these tests
                heuristic_min_freshness=9999,
            ),
            cost_tracker=cost_tracker,
        )
        agent.start()
        return agent

    def _make_intel(self, relevance_score: float = 0.7, symbols=None) -> IntelObject:
        """
        Build a valid IntelObject for test injection.
        構建用於測試注入的有效 IntelObject。
        """
        return IntelObject(
            source="test",
            content="test signal",
            symbols=symbols or ["BTCUSDT"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.POSITIVE,
            relevance_score=relevance_score,
            freshness_seconds=1,
            metadata={},
        )

    def _make_intel_message(self, intel: IntelObject) -> "AgentMessage":
        """
        Wrap IntelObject as AgentMessage.
        將 IntelObject 包裝為 AgentMessage。
        """
        return AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            priority=3,
            payload=intel.to_dict(),
        )

    # ── 5a-3 H1 Tests ────────────────────────────────────────────────────────

    def test_h1_budget_skip(self):
        """
        Budget exceeded → h1_budget_skip increments; heuristic evaluation used (not allow-all).
        預算超限 → h1_budget_skip 遞增；走啟發式評估而非 allow-all。
        """
        mock_tracker = MagicMock()
        mock_tracker.check_daily_budget.return_value = (False, 0.0)

        agent = self._make_strategist(cost_tracker=mock_tracker)
        intel = self._make_intel(relevance_score=0.8)

        # Spy on _evaluate_edge to confirm it is NOT called
        # 監視 _evaluate_edge 確認其不被調用
        agent._evaluate_edge = MagicMock(wraps=agent._evaluate_edge)

        agent._handle_intel(self._make_intel_message(intel))

        stats = agent.get_stats()
        self.assertEqual(stats["h1_budget_skip"], 1, "h1_budget_skip should be 1")
        # _evaluate_edge must not be called; heuristic path is used instead
        # _evaluate_edge 不應被調用；應走啟發式路徑
        agent._evaluate_edge.assert_not_called()

    def test_h1_complexity_skip(self):
        """
        Low relevance_score → complexity < 0.3 → h1_complexity_skip increments.
        低 relevance_score → 複雜度 < 0.3 → h1_complexity_skip 遞增。
        Note: min_relevance must be <= relevance_score so the early-return filter doesn't
        trigger before the H1 gate.  We use min_relevance=0.1 here.
        注意：min_relevance 須 <= relevance_score，以確保情報通過最低相關性過濾，到達 H1 閘門。
        """
        agent = StrategistAgent(
            config=StrategistConfig(
                shadow=True,
                min_relevance=0.1,  # allow 0.2 relevance to pass the pre-filter
                heuristic_min_relevance=0.0,
                heuristic_min_freshness=9999,
            ),
        )
        agent.start()
        intel = self._make_intel(relevance_score=0.2)  # complexity = 0.2 < 0.3
        agent._evaluate_edge = MagicMock(wraps=agent._evaluate_edge)

        agent._handle_intel(self._make_intel_message(intel))

        stats = agent.get_stats()
        self.assertEqual(stats["h1_complexity_skip"], 1, "h1_complexity_skip should be 1")
        agent._evaluate_edge.assert_not_called()

    def test_h1_cooldown_hit(self):
        """
        Same symbol twice within 30s → second call hits cooldown → h1_cooldown_skip increments.
        同一符號 30 秒內第二次 → 觸發冷卻期 → h1_cooldown_skip 遞增。
        """
        agent = self._make_strategist()
        intel = self._make_intel(relevance_score=0.7)

        # Force cooldown timestamp to be recent (now - 5s)
        # 強制設置冷卻時間戳為近期（now - 5秒）
        import time
        agent._h1_cooldown["BTCUSDT"] = time.time() - 5.0  # within 30s window

        agent._evaluate_edge = MagicMock(wraps=agent._evaluate_edge)
        agent._handle_intel(self._make_intel_message(intel))

        stats = agent.get_stats()
        self.assertEqual(stats["h1_cooldown_skip"], 1, "h1_cooldown_skip should be 1")
        agent._evaluate_edge.assert_not_called()

    def test_h1_all_pass(self):
        """
        All H1 checks pass → _evaluate_edge() is called (not heuristic).
        所有 H1 檢查通過 → _evaluate_edge() 被調用（非啟發式）。
        """
        mock_tracker = MagicMock()
        mock_tracker.check_daily_budget.return_value = (True, 1.5)

        agent = self._make_strategist(cost_tracker=mock_tracker)
        # Use relevance_score=0.7 (complexity=0.7, passes budget+complexity+cooldown)
        intel = self._make_intel(relevance_score=0.7)

        # Mock _evaluate_edge to avoid Ollama dependency
        # Mock _evaluate_edge 避免 Ollama 依賴
        from app.strategist_agent import EdgeEvaluation
        mock_eval = MagicMock(return_value=EdgeEvaluation(has_edge=False, confidence=0.0, reason="mock", source="ai"))
        agent._evaluate_edge = mock_eval

        agent._handle_intel(self._make_intel_message(intel))

        stats = agent.get_stats()
        self.assertEqual(stats["h1_budget_skip"], 0)
        self.assertEqual(stats["h1_complexity_skip"], 0)
        self.assertEqual(stats["h1_cooldown_skip"], 0)
        mock_eval.assert_called_once()

    def test_h1_timeout_fallback(self):
        """
        _evaluate_edge() raises TimeoutError → heuristic fallback is used (existing except handling).
        _evaluate_edge() 拋出 TimeoutError → 走啟發式回退（現有 except 覆蓋此場景）。
        """
        agent = self._make_strategist()
        intel = self._make_intel(relevance_score=0.7)

        # Patch _evaluate_edge to raise TimeoutError
        # 模擬 _evaluate_edge 拋出 TimeoutError
        def raise_timeout(i):
            raise TimeoutError("Ollama timeout")

        agent._evaluate_edge = raise_timeout

        # Should not raise; heuristic fallback handles TimeoutError
        # 不應拋出異常；啟發式回退處理 TimeoutError
        try:
            agent._handle_intel(self._make_intel_message(intel))
        except Exception as e:
            self.fail(f"_handle_intel raised unexpectedly: {e}")

        stats = agent.get_stats()
        # errors counter should increment due to the exception being caught
        # 因異常被捕獲，errors 計數器應遞增
        self.assertGreaterEqual(stats["heuristic_evaluations"], 1)

    # ── 5a-5 H2 Budget Tests ──────────────────────────────────────────────────

    def test_h2_budget_ok(self):
        """
        H2: budget OK → evaluate_edge called, no h1_budget_skip.
        H2：預算充足 → evaluate_edge 被調用，無 h1_budget_skip。
        """
        mock_tracker = MagicMock()
        mock_tracker.check_daily_budget.return_value = (True, 1.0)

        agent = self._make_strategist(cost_tracker=mock_tracker)
        intel = self._make_intel(relevance_score=0.7)

        from app.strategist_agent import EdgeEvaluation
        mock_eval = MagicMock(return_value=EdgeEvaluation(has_edge=False, confidence=0.0, reason="mock", source="ai"))
        agent._evaluate_edge = mock_eval

        agent._handle_intel(self._make_intel_message(intel))

        stats = agent.get_stats()
        self.assertEqual(stats["h1_budget_skip"], 0)
        mock_eval.assert_called_once()

    def test_h2_budget_exceeded(self):
        """
        H2: budget exceeded → heuristic walked, evaluate_edge NOT called.
        H2：預算超限 → 走啟發式，evaluate_edge 不被調用。
        """
        mock_tracker = MagicMock()
        mock_tracker.check_daily_budget.return_value = (False, 0.0)

        agent = self._make_strategist(cost_tracker=mock_tracker)
        intel = self._make_intel(relevance_score=0.8)
        agent._evaluate_edge = MagicMock()

        agent._handle_intel(self._make_intel_message(intel))

        agent._evaluate_edge.assert_not_called()
        stats = agent.get_stats()
        self.assertGreaterEqual(stats["heuristic_evaluations"], 1)

    def test_h2_no_cost_tracker(self):
        """
        H2: cost_tracker=None → normal execution, fail-open, no crash.
        H2：cost_tracker=None → 正常執行，fail-open，不崩潰。
        """
        agent = self._make_strategist(cost_tracker=None)
        self.assertIsNone(agent.cost_tracker)

        intel = self._make_intel(relevance_score=0.7)
        from app.strategist_agent import EdgeEvaluation
        mock_eval = MagicMock(return_value=EdgeEvaluation(has_edge=False, confidence=0.0, reason="mock", source="ai"))
        agent._evaluate_edge = mock_eval

        # Should not raise; budget is unconstrained when tracker is None
        # 不應拋出異常；無追蹤器時預算不受限
        try:
            agent._handle_intel(self._make_intel_message(intel))
        except Exception as e:
            self.fail(f"Should not raise with cost_tracker=None: {e}")

        mock_eval.assert_called_once()

    # ── 5a-6 H3 ModelRouter Tests ─────────────────────────────────────────────

    def test_h3_routes_l1_9b(self):
        """
        Low complexity (relevance=0.2) → _h3_route_model returns 'l1_9b'.
        低複雜度 → _h3_route_model 返回 'l1_9b'。
        """
        agent = self._make_strategist()
        intel = self._make_intel(relevance_score=0.2)
        result = agent._h3_route_model(intel)
        self.assertEqual(result, "l1_9b")

    def test_h3_routes_l1_27b(self):
        """
        Medium complexity (relevance=0.6, no multi-symbol boost) → route 'l1_27b'.
        中等複雜度 → 路由到 'l1_27b'。
        """
        agent = self._make_strategist()
        intel = self._make_intel(relevance_score=0.6)
        result = agent._h3_route_model(intel)
        self.assertEqual(result, "l1_27b")

    def test_h3_routes_l2_thread(self):
        """
        High complexity (relevance=0.9) → threading.Thread spawned, evaluate_edge NOT called
        synchronously; heuristic used as immediate result.
        高複雜度 → threading.Thread 被創建，evaluate_edge 不被同步調用，立即走啟發式。
        """
        agent = self._make_strategist()
        # High relevance_score → complexity >= 0.8 → l2 route
        intel = self._make_intel(relevance_score=0.9)

        # Track if _evaluate_edge is called synchronously
        # 追蹤 _evaluate_edge 是否被同步調用
        sync_eval_calls = []
        from app.strategist_agent import EdgeEvaluation

        def mock_eval_sync(i):
            sync_eval_calls.append(i)
            return EdgeEvaluation(has_edge=False, confidence=0.0, reason="sync", source="ai")

        agent._evaluate_edge = mock_eval_sync

        # Patch threading.Thread to capture if it's created
        # 攔截 threading.Thread 確認其被創建
        thread_calls = []
        original_thread_init = __import__("threading").Thread.__init__

        import threading as _threading
        created_threads = []

        class SpyThread(_threading.Thread):
            def __init__(self, **kwargs):
                created_threads.append(kwargs.get("target"))
                super().__init__(**kwargs)
            def start(self):
                pass  # don't actually start — we just check it was created

        with patch("app.strategist_agent.threading.Thread", SpyThread):
            agent._handle_intel(self._make_intel_message(intel))

        # Thread must have been created for L2 evaluation
        # 必須為 L2 評估創建 Thread
        self.assertGreater(len(created_threads), 0, "Expected threading.Thread to be created for L2 path")
        # _evaluate_edge must NOT have been called synchronously
        # _evaluate_edge 不應被同步調用
        self.assertEqual(len(sync_eval_calls), 0, "evaluate_edge must not be called synchronously for L2 path")
        # heuristic_evaluations should be >= 1 (immediate fallback result)
        # heuristic_evaluations 應 >= 1（立即回退結果）
        stats = agent.get_stats()
        self.assertGreaterEqual(stats["heuristic_evaluations"], 1)


# ═══════════════════════════════════════════════════════════════════════════════
# TestStrategistShadowFalse
# Sprint 5a：shadow=False 模式驗證 — intent 進入 _pending_intents，超出時被截斷
# ═══════════════════════════════════════════════════════════════════════════════

class TestStrategistShadowFalse(unittest.TestCase):
    """
    Sprint 5a: Verify shadow=False mode correctly buffers TradeIntents.
    Sprint 5a：驗證 shadow=False 模式正確緩衝 TradeIntent。

    Tests:
    1. shadow=False → _handle_intel() adds intent to _pending_intents
    2. _pending_intents respects max_pending_intents cap (older intents dropped when full)
    測試：
    1. shadow=False → _handle_intel() 將 intent 加入 _pending_intents
    2. _pending_intents 遵守 max_pending_intents 上限（滿時不加入新 intent）
    """

    def _make_intel_message_live(self, symbol: str = "BTCUSDT",
                                  relevance: float = 0.9) -> "AgentMessage":
        """
        Build an INTEL_OBJECT message that will reliably produce a TradeIntent.
        構建一條能可靠產出 TradeIntent 的 INTEL_OBJECT 消息。

        Uses high relevance_score (0.9) to pass all H1 checks (budget/complexity/cooldown),
        and patches _evaluate_edge to return a guaranteed positive EdgeEvaluation.
        使用高 relevance_score (0.9) 通過所有 H1 閘門，並 mock _evaluate_edge 返回正向結果。
        """
        return AgentMessage(
            sender=AgentRole.SCOUT,
            receiver=AgentRole.STRATEGIST,
            message_type=MessageType.INTEL_OBJECT,
            priority=3,
            payload={
                "intel_id": f"test_live_{id(symbol)}",
                "source": "test_scout",
                "timestamp_ms": int(__import__("time").time() * 1000),
                "freshness_seconds": 2,
                "data_quality": "fact",
                "sentiment": "positive",
                "relevance_score": relevance,
                "content": f"Bullish breakout for {symbol}",
                "symbols": [symbol],
                "metadata": {"strategy_name": "test"},
            },
        )

    def _make_strategist_live(self, max_pending: int = 50) -> "StrategistAgent":
        """
        Create a shadow=False StrategistAgent for testing intent buffering.
        建立 shadow=False 的 StrategistAgent 用於測試 intent 緩衝。
        """
        from app.strategist_agent import StrategistAgent, StrategistConfig
        agent = StrategistAgent(
            config=StrategistConfig(
                shadow=False,
                min_relevance=0.3,
                min_confidence=0.1,  # low bar so heuristic evaluations pass
                heuristic_min_relevance=0.0,
                heuristic_min_freshness=9999,
                max_pending_intents=max_pending,
            )
        )
        agent.start()
        return agent

    def _make_positive_evaluation(self) -> "EdgeEvaluation":
        """Return an EdgeEvaluation that will produce a TradeIntent."""
        from app.strategist_agent import EdgeEvaluation
        return EdgeEvaluation(
            has_edge=True,
            confidence=0.8,
            source="heuristic",
            reason="test_edge",
        )

    def test_shadow_false_intent_added_to_pending(self):
        """
        shadow=False: when _handle_intel() evaluates an edge, intent is added to _pending_intents.
        shadow=False：_handle_intel() 評估出 edge 時，intent 應被加入 _pending_intents。

        Verifies that the Strategist is in live (non-shadow) mode after Sprint 5a switch,
        and that valid intel produces buffered TradeIntents for downstream consumption.
        驗證 Sprint 5a 切換後 Strategist 處於真實模式，有效情報產出可被下游消費的 TradeIntent。
        """
        from app.strategist_agent import StrategistAgent, StrategistConfig, EdgeEvaluation
        agent = self._make_strategist_live()

        # Patch _evaluate_edge to return a guaranteed positive result
        # 修補 _evaluate_edge 返回正向結果，排除 Ollama 不可用的不確定性
        positive_eval = EdgeEvaluation(has_edge=True, confidence=0.8,
                                       source="heuristic", reason="test")
        agent._evaluate_edge = lambda _intel: positive_eval

        msg = self._make_intel_message_live(symbol="BTCUSDT", relevance=0.9)
        agent.on_message(msg)

        # In shadow=False mode, _pending_intents should have at least 1 item
        # shadow=False 模式下，_pending_intents 應至少有 1 個 item
        with agent._lock:
            pending_count = len(agent._pending_intents)

        self.assertGreater(
            pending_count, 0,
            "shadow=False: expected at least one intent in _pending_intents after positive intel"
        )

    def test_shadow_false_pending_intents_capped(self):
        """
        When _pending_intents reaches max_pending_intents, new intents are NOT added.
        當 _pending_intents 達到 max_pending_intents 上限時，新 intent 不被加入。

        The production code at line 405 checks `len < max` before appending.
        This protects against memory overflow under 650-symbol load.
        生產代碼第 405 行：加入前檢查 len < max，防止 650 符號負載下記憶體溢出。
        """
        from app.strategist_agent import StrategistAgent, StrategistConfig, EdgeEvaluation
        max_pending = 2
        agent = self._make_strategist_live(max_pending=max_pending)

        positive_eval = EdgeEvaluation(has_edge=True, confidence=0.8,
                                       source="heuristic", reason="test")
        agent._evaluate_edge = lambda _intel: positive_eval

        # Send more intents than the cap allows (3 messages, cap=2)
        # 發送超過上限的 intent（3 條消息，上限=2）
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        for sym in symbols:
            msg = self._make_intel_message_live(symbol=sym, relevance=0.9)
            agent.on_message(msg)
            __import__("time").sleep(0.01)  # ensure cooldown doesn't block all

        # Should have at most max_pending intents buffered
        # 緩衝區最多應有 max_pending 個 intent
        with agent._lock:
            pending_count = len(agent._pending_intents)

        self.assertLessEqual(
            pending_count, max_pending,
            f"Expected _pending_intents count <= {max_pending}, got {pending_count}"
        )


# ═══════════════════════════════════════════════════════════════════════════════
# TestH4OutputValidation
# Sprint 5b-1: H4 AI 輸出驗證 — _validate_ai_output() 行為測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestH4OutputValidation(unittest.TestCase):
    """
    Sprint 5b-1: Verify H4 AI output validation method and its integration in _ai_evaluate().
    Sprint 5b-1：驗證 H4 AI 輸出驗證方法及其在 _ai_evaluate() 中的集成行為。

    Tests:
    1. Valid parsed dict → _validate_ai_output returns True
    2. Missing 'confidence' → returns False → _ai_evaluate falls back to heuristic
    3. Non-numeric confidence → returns False
    4. Out-of-range confidence → returns False
    測試：
    1. 合法 dict → _validate_ai_output 返回 True
    2. 缺少 confidence → 返回 False → _ai_evaluate 降級啟發式
    3. confidence 非數值 → 返回 False
    4. confidence 超出範圍 → 返回 False
    """

    def _make_agent(self) -> "StrategistAgent":
        """Create a minimal StrategistAgent for unit testing _validate_ai_output.
        構建用於單元測試 _validate_ai_output 的最小 StrategistAgent。"""
        from app.strategist_agent import StrategistAgent, StrategistConfig
        config = StrategistConfig(shadow=True, min_relevance=0.1)
        return StrategistAgent(config=config)

    def _make_intel(self, symbol: str = "BTCUSDT") -> "IntelObject":
        """Build a minimal IntelObject for _ai_evaluate tests.
        構建 _ai_evaluate 測試用的最小 IntelObject。"""
        return IntelObject(
            source="test",
            content="test signal",
            symbols=[symbol],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.POSITIVE,
            relevance_score=0.8,
            freshness_seconds=5,
            metadata={},
        )

    # ── _validate_ai_output unit tests / 單元測試 ──

    def test_h4_valid_output_returns_true(self):
        """Valid parsed dict with confidence in [0, 1] should return True.
        合法 dict 且 confidence 在 [0, 1] 範圍應返回 True。"""
        agent = self._make_agent()
        parsed = {"has_edge": True, "confidence": 0.75, "reason": "looks good"}
        self.assertTrue(agent._validate_ai_output(parsed))

    def test_h4_valid_output_confidence_zero(self):
        """Confidence exactly 0.0 is valid (boundary).
        confidence 精確為 0.0 是合法值（邊界測試）。"""
        agent = self._make_agent()
        parsed = {"confidence": 0.0}
        self.assertTrue(agent._validate_ai_output(parsed))

    def test_h4_valid_output_confidence_one(self):
        """Confidence exactly 1.0 is valid (boundary).
        confidence 精確為 1.0 是合法值（邊界測試）。"""
        agent = self._make_agent()
        parsed = {"confidence": 1.0}
        self.assertTrue(agent._validate_ai_output(parsed))

    def test_h4_missing_confidence_returns_false(self):
        """Missing 'confidence' key → should return False.
        缺少 'confidence' 鍵 → 應返回 False。"""
        agent = self._make_agent()
        parsed = {"has_edge": True, "reason": "no confidence here"}
        self.assertFalse(agent._validate_ai_output(parsed))

    def test_h4_non_dict_returns_false(self):
        """Non-dict input (list, string, None) → should return False.
        非 dict 輸入（列表、字符串、None）→ 應返回 False。"""
        agent = self._make_agent()
        self.assertFalse(agent._validate_ai_output([{"confidence": 0.5}]))
        self.assertFalse(agent._validate_ai_output("confidence: 0.5"))
        self.assertFalse(agent._validate_ai_output(None))

    def test_h4_confidence_out_of_range_high(self):
        """confidence=1.5 (above 1.0) → should return False.
        confidence=1.5（超出上限）→ 應返回 False。"""
        agent = self._make_agent()
        parsed = {"has_edge": True, "confidence": 1.5}
        self.assertFalse(agent._validate_ai_output(parsed))

    def test_h4_confidence_out_of_range_low(self):
        """confidence=-0.1 (below 0.0) → should return False.
        confidence=-0.1（低於下限）→ 應返回 False。"""
        agent = self._make_agent()
        parsed = {"has_edge": True, "confidence": -0.1}
        self.assertFalse(agent._validate_ai_output(parsed))

    def test_h4_non_numeric_confidence_returns_false(self):
        """Non-numeric confidence (string) → should return False.
        非數值型 confidence（字符串）→ 應返回 False。"""
        agent = self._make_agent()
        parsed = {"has_edge": True, "confidence": "high"}
        self.assertFalse(agent._validate_ai_output(parsed))

    def test_h4_integer_confidence_valid(self):
        """Integer confidence (0 or 1) should be accepted (isinstance int/float).
        整數型 confidence (0 或 1) 應被接受（isinstance int/float 均可）。"""
        agent = self._make_agent()
        self.assertTrue(agent._validate_ai_output({"confidence": 1}))
        self.assertTrue(agent._validate_ai_output({"confidence": 0}))

    # ── Integration: _ai_evaluate falls back to heuristic on H4 fail ──
    # 集成測試：H4 驗證失敗時 _ai_evaluate 降級到啟發式

    def test_h4_fallback_to_heuristic_on_invalid_output(self):
        """When judge_edge returns invalid output, _ai_evaluate falls back to heuristic
        and increments h4_validation_fail counter (not allow-all).
        當 judge_edge 返回無效輸出時，_ai_evaluate 降級到啟發式，
        並遞增 h4_validation_fail 計數器（不可 allow-all）。"""
        from app.strategist_agent import StrategistAgent, StrategistConfig
        config = StrategistConfig(shadow=True, min_relevance=0.1,
                                  heuristic_min_relevance=0.1,
                                  heuristic_min_freshness=300)
        agent = StrategistAgent(config=config)

        mock_response = MagicMock()
        mock_response.success = True
        # Return JSON without 'confidence' key → H4 validation fails
        # 返回缺少 'confidence' 的 JSON → H4 驗證失敗
        mock_response.text = '{"has_edge": true, "reason": "missing confidence"}'

        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = mock_response
        agent._ollama = mock_ollama

        intel = self._make_intel()
        result = agent._ai_evaluate(intel)

        # Should have fallen back to heuristic (source = "heuristic")
        # 應降級到啟發式（source = "heuristic"）
        self.assertEqual(result.source, "heuristic",
                         "H4 validation failure must produce heuristic result, not allow-all")

        # h4_validation_fail counter should be incremented
        # h4_validation_fail 計數器應已遞增
        with agent._lock:
            fail_count = agent._stats.get("h4_validation_fail", 0)
        self.assertGreater(fail_count, 0,
                           "h4_validation_fail counter must increment on H4 rejection")


# ═══════════════════════════════════════════════════════════════════════════════
# TestCostTrackerOllama
# Sprint 5b-2/6: H5 CostLogger — record_ollama_call / get_cost_edge_ratio 測試
# ═══════════════════════════════════════════════════════════════════════════════

class TestCostTrackerOllama(unittest.TestCase):
    """
    Sprint 5b-2/6: Verify Ollama call tracking and cost-edge ratio in Layer2CostTracker.
    Sprint 5b-2/6：驗證 Layer2CostTracker 中的 Ollama 調用追蹤和成本效益比。

    Tests:
    1. record_ollama_call increments in-memory counter
    2. get_cost_edge_ratio returns dict with roi_basis = "paper_simulation_only"
    3. get_cost_summary returns dict with roi_basis = "paper_simulation_only"
    4. StrategistAgent with cost_tracker=None does not crash
    測試：
    1. record_ollama_call 遞增記憶體計數器
    2. get_cost_edge_ratio 返回含 roi_basis = "paper_simulation_only" 的 dict
    3. get_cost_summary 返回含 roi_basis = "paper_simulation_only" 的 dict
    4. cost_tracker=None 時 StrategistAgent 不崩潰
    """

    def _make_tracker(self) -> "Layer2CostTracker":
        """Create a Layer2CostTracker with a temp state file.
        使用臨時狀態文件創建 Layer2CostTracker。"""
        import tempfile
        from app.layer2_cost_tracker import Layer2CostTracker
        tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        tmp.close()
        return Layer2CostTracker(state_file=tmp.name)

    def test_record_ollama_call_increments_counter(self):
        """record_ollama_call should increment per-model in-memory counter.
        record_ollama_call 應遞增記憶體中對應模型的計數器。"""
        tracker = self._make_tracker()
        tracker.record_ollama_call(model="l1_9b", duration_ms=150.0)
        tracker.record_ollama_call(model="l1_9b", duration_ms=200.0)
        tracker.record_ollama_call(model="l1_27b", duration_ms=500.0)

        stats = tracker.get_ollama_stats()
        self.assertIn("l1_9b", stats)
        self.assertEqual(stats["l1_9b"]["call_count"], 2)
        self.assertIn("l1_27b", stats)
        self.assertEqual(stats["l1_27b"]["call_count"], 1)

    def test_record_ollama_call_duration_accumulated(self):
        """record_ollama_call should accumulate total_duration_ms correctly.
        record_ollama_call 應正確累積 total_duration_ms。"""
        tracker = self._make_tracker()
        tracker.record_ollama_call(model="l1_9b", duration_ms=100.0)
        tracker.record_ollama_call(model="l1_9b", duration_ms=200.5)

        stats = tracker.get_ollama_stats()
        self.assertAlmostEqual(stats["l1_9b"]["total_duration_ms"], 300.5, places=1)

    def test_get_cost_edge_ratio_has_roi_basis(self):
        """get_cost_edge_ratio must return dict with roi_basis = 'paper_simulation_only'.
        get_cost_edge_ratio 必須返回含 roi_basis = 'paper_simulation_only' 的 dict。"""
        tracker = self._make_tracker()
        result = tracker.get_cost_edge_ratio()
        self.assertIn("roi_basis", result)
        self.assertEqual(result["roi_basis"], "paper_simulation_only")
        self.assertIn("roi_disclaimer", result)
        self.assertIn("cost_edge_ratio", result)

    def test_get_cost_edge_ratio_none_when_insufficient_data(self):
        """cost_edge_ratio should be None when data_days < ADAPTIVE_MIN_DAYS.
        data_days 不足時 cost_edge_ratio 應為 None。"""
        tracker = self._make_tracker()
        result = tracker.get_cost_edge_ratio()
        # Fresh tracker has no data, so ratio should be None
        # 全新追蹤器無數據，比率應為 None
        self.assertIsNone(result["cost_edge_ratio"])

    def test_get_cost_summary_has_roi_basis(self):
        """get_cost_summary must include roi_basis = 'paper_simulation_only'.
        get_cost_summary 必須包含 roi_basis = 'paper_simulation_only'。"""
        tracker = self._make_tracker()
        summary = tracker.get_cost_summary()
        self.assertIn("roi_basis", summary)
        self.assertEqual(summary["roi_basis"], "paper_simulation_only")
        self.assertIn("roi_disclaimer", summary)

    def test_record_ollama_call_none_tracker_strategist_no_crash(self):
        """StrategistAgent with cost_tracker=None should not crash when processing intel.
        cost_tracker=None 時 StrategistAgent 處理 intel 不得崩潰。"""
        from app.strategist_agent import StrategistAgent, StrategistConfig
        config = StrategistConfig(shadow=True, min_relevance=0.1)
        agent = StrategistAgent(config=config, cost_tracker=None)

        mock_response = MagicMock()
        mock_response.success = True
        mock_response.text = '{"has_edge": false, "confidence": 0.3, "reason": "no signal"}'
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = mock_response
        agent._ollama = mock_ollama

        intel = IntelObject(
            source="test",
            content="no signal",
            symbols=["BTCUSDT"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.NEUTRAL,
            relevance_score=0.5,
            freshness_seconds=10,
            metadata={},
        )
        # Should not raise even with cost_tracker=None
        # cost_tracker=None 時不應拋出異常
        try:
            result = agent._ai_evaluate(intel)
            self.assertIsNotNone(result)
        except Exception as e:
            self.fail(f"_ai_evaluate raised exception with cost_tracker=None: {e}")

    def test_record_ollama_call_via_strategist_increments_stat(self):
        """When cost_tracker has record_ollama_call, strategist increments ollama_calls_tracked.
        cost_tracker 有 record_ollama_call 時，strategist 應遞增 ollama_calls_tracked 統計。"""
        from app.strategist_agent import StrategistAgent, StrategistConfig
        tracker = self._make_tracker()
        config = StrategistConfig(shadow=True, min_relevance=0.1,
                                  heuristic_min_relevance=0.1,
                                  heuristic_min_freshness=300)
        agent = StrategistAgent(config=config, cost_tracker=tracker)

        mock_response = MagicMock()
        mock_response.success = True
        # Valid output with confidence
        # 有效輸出含 confidence
        mock_response.text = '{"has_edge": true, "confidence": 0.8, "reason": "strong signal"}'
        mock_ollama = MagicMock()
        mock_ollama.is_available.return_value = True
        mock_ollama.judge_edge.return_value = mock_response
        agent._ollama = mock_ollama

        intel = IntelObject(
            source="test",
            content="strong signal",
            symbols=["BTCUSDT"],
            data_quality=DataQualityLevel.FACT,
            sentiment=SentimentScore.POSITIVE,
            relevance_score=0.8,
            freshness_seconds=5,
            metadata={},
        )
        agent._ai_evaluate(intel)

        with agent._lock:
            tracked = agent._stats.get("ollama_calls_tracked", 0)
        self.assertGreater(tracked, 0,
                           "ollama_calls_tracked must increment after successful AI evaluation")


if __name__ == "__main__":
    unittest.main()

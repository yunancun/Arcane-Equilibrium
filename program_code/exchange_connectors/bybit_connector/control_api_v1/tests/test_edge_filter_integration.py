"""
Integration Tests for Pre-Trade Edge Filter in PipelineBridge
PipelineBridge 中交易前 edge 过滤器的集成测试

Covers:
  - Edge filter decision logic (pass/reject/fail-open)
  - OllamaClient integration with judge_edge()
  - JSON and freetext response parsing
  - Fail-open design: graceful degradation on Ollama unavailability
  - Statistics tracking (checked, passed, rejected, errors)
  - Context building (symbol, side, strategy, confidence, indicators)
  - Timeout handling
  - Disable/enable toggle
  - No ollama_client set (pass-through)
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.pipeline_bridge import PipelineBridge
from app.ollama_client import OllamaResponse


# ═══════════════════════════════════════════════════════════════════════════════
# Test Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════


class MockIntent:
    """Mock OrderIntent object for testing / 用于测试的 Mock OrderIntent 对象"""

    def __init__(
        self,
        symbol: str = "BTCUSDT",
        side: str = "Buy",
        order_type: str = "market",
        qty: float = 0.1,
        price: float = 45000.0,
        confidence: float = 0.75,
        strategy_name: str = "TestStrategy",
        metadata: dict | None = None,
    ):
        self.symbol = symbol
        self.side = side
        self.order_type = order_type
        self.qty = qty
        self.price = price
        self.confidence = confidence
        self.strategy_name = strategy_name
        self.metadata = metadata or {
            "strategy_name": strategy_name,
            "confidence": confidence,
            "category": "linear",
        }


@pytest.fixture
def mock_kline_manager():
    """Mock KlineManager with minimal interface / 最小接口的 Mock KlineManager"""
    mgr = MagicMock()
    mgr.bootstrap_from_rest.return_value = {}
    mgr.on_price_event = MagicMock()
    mgr.get_regime = MagicMock(return_value="normal")
    mgr.get_latest_indicators = MagicMock(
        return_value={
            "rsi_14": 55.0,
            "atr_14": 500.0,
            "bb_width": 0.02,
            "macd_histogram": 0.001,
            "volume_ratio": 1.2,
        }
    )
    return mgr


@pytest.fixture
def mock_indicator_engine():
    """Mock IndicatorEngine / Mock IndicatorEngine"""
    return MagicMock()


@pytest.fixture
def mock_signal_engine():
    """Mock SignalEngine / Mock SignalEngine"""
    return MagicMock()


@pytest.fixture
def mock_orchestrator():
    """Mock StrategyOrchestrator / Mock StrategyOrchestrator"""
    orch = MagicMock()
    orch.dispatch_tick = MagicMock()
    orch.collect_pending_intents = MagicMock(return_value=[])
    orch.restore_all_strategy_state = MagicMock()
    orch.save_all_strategy_state = MagicMock(return_value={})
    return orch


@pytest.fixture
def mock_paper_engine():
    """Mock PaperTradingEngine / Mock PaperTradingEngine"""
    engine = MagicMock()
    engine.submit_order = MagicMock(
        return_value={
            "order": {"order_id": "test-order-1"},
            "fills": [{"price": 45000.0}],
        }
    )
    engine.get_state = MagicMock(return_value={"positions": {}})
    return engine


@pytest.fixture
def mock_ollama_client():
    """Mock OllamaClient / Mock OllamaClient"""
    client = MagicMock()
    client.is_available = MagicMock(return_value=True)
    client.judge_edge = MagicMock(
        return_value=OllamaResponse(
            text='{"has_edge": true, "confidence": 0.8, "reason": "strong trend"}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )
    )
    return client


@pytest.fixture
def pipeline_bridge(
    mock_kline_manager,
    mock_indicator_engine,
    mock_signal_engine,
    mock_orchestrator,
    mock_paper_engine,
):
    """Fresh PipelineBridge instance with mocked dependencies / 带有 Mock 依赖的全新 PipelineBridge"""
    bridge = PipelineBridge(
        kline_manager=mock_kline_manager,
        indicator_engine=mock_indicator_engine,
        signal_engine=mock_signal_engine,
        orchestrator=mock_orchestrator,
        paper_engine=mock_paper_engine,
        auto_submit_intents=True,
        max_intents_per_tick=20,
    )
    return bridge


# ═══════════════════════════════════════════════════════════════════════════════
# TestEdgeFilterIntegration / 边界过滤集成测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeFilterIntegration:
    """Integration tests for pre-trade edge filter in PipelineBridge.
    PipelineBridge 中交易前 edge 过滤器的集成测试。
    """

    def test_edge_filter_passes_good_signal(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: judge_edge returns has_edge=true, intent is submitted.
        测试：judge_edge 返回 has_edge=true，意图被提交。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text='{"has_edge": true, "confidence": 0.8, "reason": "strong trend"}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent was submitted
        assert mock_orchestrator.collect_pending_intents.called
        assert pipeline_bridge._stats["intents_submitted"] > 0 or pipeline_bridge._stats["intents_rejected"] == 0

        # Verify edge filter was called and passed
        assert mock_ollama_client.judge_edge.called
        assert pipeline_bridge._edge_filter_stats["passed"] == 1

    def test_edge_filter_rejects_no_edge(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: judge_edge returns has_edge=false, intent is rejected.
        测试：judge_edge 返回 has_edge=false，意图被拒绝。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text='{"has_edge": false, "confidence": 0.2, "reason": "no trend"}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent was rejected by edge filter
        assert mock_ollama_client.judge_edge.called
        assert pipeline_bridge._edge_filter_stats["rejected"] == 1
        assert pipeline_bridge._stats["intents_rejected"] == 1

    def test_edge_filter_fail_open_on_ollama_unavailable(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: is_available()=False, intent passes through (fail-open).
        测试：is_available()=False，意图通过（失败放行）。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.is_available.return_value = False

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent passed through despite Ollama being unavailable
        assert mock_ollama_client.judge_edge.call_count == 0  # Never called
        assert pipeline_bridge._edge_filter_stats["errors"] == 1
        assert pipeline_bridge._stats["intents_submitted"] > 0

    def test_edge_filter_fail_open_on_error(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: judge_edge returns success=False, intent passes through (fail-open).
        测试：judge_edge 返回 success=False，意图通过（失败放行）。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text="",
            model="qwen3.5:27b-q4_K_M",
            success=False,
            latency_ms=150.0,
            error="Connection timeout",
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent passed through despite error
        assert mock_ollama_client.judge_edge.called
        assert pipeline_bridge._edge_filter_stats["errors"] == 1
        assert pipeline_bridge._stats["intents_submitted"] > 0

    def test_edge_filter_fail_open_on_exception(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: judge_edge raises Exception, intent passes through (fail-open).
        测试：judge_edge 抛出异常，意图通过（失败放行）。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.side_effect = RuntimeError("Network error")

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent passed through despite exception
        assert mock_ollama_client.judge_edge.called
        assert pipeline_bridge._edge_filter_stats["errors"] == 1
        assert pipeline_bridge._stats["intents_submitted"] > 0

    def test_edge_filter_disabled_passes_all(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: _edge_filter_enabled=False, intents pass without calling judge_edge.
        测试：_edge_filter_enabled=False，意图不调用 judge_edge 直接通过。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        pipeline_bridge._edge_filter_enabled = False

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify judge_edge was never called
        assert mock_ollama_client.judge_edge.call_count == 0
        assert pipeline_bridge._stats["intents_submitted"] > 0

    def test_edge_filter_no_client_passes_all(self, pipeline_bridge, mock_orchestrator):
        """Test: no ollama_client set, intents pass through normally.
        测试：未设置 ollama_client，意图正常通过。
        """
        # Don't set ollama_client
        assert pipeline_bridge._ollama_client is None

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intents were submitted
        assert pipeline_bridge._stats["intents_submitted"] > 0

    def test_edge_filter_stats_tracking(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: multiple intents (pass/reject) are tracked correctly.
        测试：多个意图（通过/拒绝）被正确追踪。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        # First intent: passes
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text='{"has_edge": true, "confidence": 0.8, "reason": "strong"}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )
        intent1 = MockIntent(symbol="BTCUSDT", side="Buy")

        # Second intent: rejected
        intent2 = MockIntent(symbol="ETHUSDT", side="Sell")

        mock_orchestrator.collect_pending_intents.side_effect = [
            [intent1],
            [intent2],
        ]

        # Update mock for second call to reject
        responses = [
            OllamaResponse(
                text='{"has_edge": true, "confidence": 0.8, "reason": "strong"}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": false, "confidence": 0.3, "reason": "weak"}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
        ]
        mock_ollama_client.judge_edge.side_effect = responses

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})
        pipeline_bridge.on_tick({"symbol": "ETHUSDT", "last_price": 2500.0})

        # Verify stats
        assert pipeline_bridge._edge_filter_stats["checked"] == 2
        assert pipeline_bridge._edge_filter_stats["passed"] == 1
        assert pipeline_bridge._edge_filter_stats["rejected"] == 1

    def test_edge_filter_freetext_parsing(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: non-JSON text response with 'yes/true' is parsed as has_edge=true.
        测试：非 JSON 文本响应包含 'yes/true' 被解析为 has_edge=true。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text="yes has edge strong trend confirmed",
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent passed (heuristic parsing allowed it)
        assert pipeline_bridge._edge_filter_stats["passed"] == 1
        assert pipeline_bridge._stats["intents_submitted"] > 0

    def test_edge_filter_freetext_rejection(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: non-JSON text response with 'no/false' is parsed as has_edge=false.
        测试：非 JSON 文本响应包含 'no/false' 被解析为 has_edge=false。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text="no edge detected false signal weak",
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent was rejected (heuristic parsing rejected it)
        assert pipeline_bridge._edge_filter_stats["rejected"] == 1
        assert pipeline_bridge._stats["intents_rejected"] == 1

    def test_edge_filter_context_includes_symbol(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: context passed to judge_edge includes symbol and side.
        测试：传递给 judge_edge 的上下文包含 symbol 和 side。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        intent = MockIntent(symbol="ETHUSDT", side="Sell", confidence=0.85)
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "ETHUSDT", "last_price": 2500.0})

        # Verify judge_edge was called with context containing symbol and side
        assert mock_ollama_client.judge_edge.called
        call_args = mock_ollama_client.judge_edge.call_args
        context = call_args[0][0] if call_args[0] else call_args.kwargs.get("market_context", "")

        assert "ETHUSDT" in context
        assert "Sell" in context

    def test_edge_filter_respects_timeout(self, pipeline_bridge, mock_ollama_client, mock_orchestrator):
        """Test: judge_edge is called with timeout=10 parameter.
        测试：judge_edge 被调用时包含 timeout=10 参数。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify timeout parameter was passed
        assert mock_ollama_client.judge_edge.called
        call_kwargs = mock_ollama_client.judge_edge.call_args.kwargs
        assert call_kwargs.get("timeout") == 10

    def test_edge_filter_json_parsing_with_extra_fields(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: JSON response with extra fields is parsed correctly.
        测试：包含额外字段的 JSON 响应被正确解析。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text='{"has_edge": true, "confidence": 0.95, "reason": "very strong", "extra_field": "ignored"}',
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent passed
        assert pipeline_bridge._edge_filter_stats["passed"] == 1

    def test_edge_filter_default_allow_on_missing_has_edge(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: JSON response missing has_edge defaults to true (fail-open).
        测试：JSON 响应缺少 has_edge 字段时默认为 true（失败放行）。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text='{"confidence": 0.7, "reason": "uncertain"}',  # has_edge missing
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify intent passed (default allow)
        assert pipeline_bridge._edge_filter_stats["passed"] == 1

    def test_edge_filter_multiple_intents_per_tick(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: multiple intents in one tick are all filtered.
        测试：一个 tick 中的多个意图都被过滤。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        # Three intents, set up alternating passes/rejects
        responses = [
            OllamaResponse(
                text='{"has_edge": true, "confidence": 0.8}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": false, "confidence": 0.3}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": true, "confidence": 0.7}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
        ]
        mock_ollama_client.judge_edge.side_effect = responses

        intent1 = MockIntent(symbol="BTCUSDT", side="Buy")
        intent2 = MockIntent(symbol="ETHUSDT", side="Sell")
        intent3 = MockIntent(symbol="BNBUSDT", side="Buy")

        # All three intents come from a single orchestrator call
        mock_orchestrator.collect_pending_intents.return_value = [intent1, intent2, intent3]

        pipeline_bridge.activate()
        # Activate with one tick to set latest prices
        pipeline_bridge._latest_prices["BTCUSDT"] = 45000.0
        pipeline_bridge._latest_prices["ETHUSDT"] = 2500.0
        pipeline_bridge._latest_prices["BNBUSDT"] = 650.0

        # Now process intents with all symbols priced
        pipeline_bridge._process_pending_intents()

        # Verify stats: 3 checks (one per intent), 2 passed, 1 rejected
        assert pipeline_bridge._edge_filter_stats["checked"] == 3
        assert pipeline_bridge._edge_filter_stats["passed"] == 2
        assert pipeline_bridge._edge_filter_stats["rejected"] == 1

    def test_edge_filter_with_metadata_strategy_name(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: strategy name from metadata is included in context.
        测试：元数据中的策略名称被包含在上下文中。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        metadata = {
            "strategy_name": "MomentumGrid",
            "confidence": 0.82,
            "category": "linear",
        }
        intent = MockIntent(symbol="BTCUSDT", side="Buy", metadata=metadata)
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify context included strategy name
        call_args = mock_ollama_client.judge_edge.call_args
        context = call_args[0][0] if call_args[0] else ""
        assert "MomentumGrid" in context

    def test_edge_filter_context_with_indicators(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator, mock_kline_manager
    ):
        """Test: indicators from KlineManager are included in context if available.
        测试：如果可用，KlineManager 中的指标被包含在上下文中。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_kline_manager.get_latest_indicators.return_value = {
            "rsi_14": 62.5,
            "atr_14": 450.0,
            "bb_width": 0.018,
            "macd_histogram": 0.0015,
            "volume_ratio": 1.5,
        }

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify context included indicator info
        call_args = mock_ollama_client.judge_edge.call_args
        context = call_args[0][0] if call_args[0] else ""
        assert "Indicators:" in context or "rsi_14" in context or "atr_14" in context

    def test_edge_filter_maintains_stats_across_ticks(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: edge filter stats are maintained across multiple ticks.
        测试：edge 过滤器统计在多个 tick 中被维护。
        """
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        # Simulate 3 ticks with 2 intents each
        responses = [
            OllamaResponse(
                text='{"has_edge": true}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": false}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": true}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": true}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": false}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
            OllamaResponse(
                text='{"has_edge": true}',
                model="qwen3.5:27b-q4_K_M",
                success=True,
                latency_ms=150.0,
            ),
        ]
        mock_ollama_client.judge_edge.side_effect = responses

        intent1 = MockIntent(symbol="BTC")
        intent2 = MockIntent(symbol="ETH")

        pipeline_bridge.activate()

        for i in range(3):
            mock_orchestrator.collect_pending_intents.return_value = [intent1, intent2]
            pipeline_bridge.on_tick({"symbol": "BTC", "last_price": 45000.0 + (i * 100)})

        # Verify cumulative stats
        assert pipeline_bridge._edge_filter_stats["checked"] == 6
        assert pipeline_bridge._edge_filter_stats["passed"] == 4
        assert pipeline_bridge._edge_filter_stats["rejected"] == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Additional Scenario Tests / 额外场景测试
# ═══════════════════════════════════════════════════════════════════════════════


class TestEdgeFilterErrorHandling:
    """Test edge filter error handling and edge cases.
    测试 edge 过滤器错误处理和边界情况。
    """

    def test_edge_filter_handles_none_intent_metadata(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: intent with None metadata doesn't crash / 意图的 None 元数据不会导致崩溃"""
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        intent.metadata = None  # Explicitly set to None
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify it didn't crash
        assert mock_ollama_client.judge_edge.called
        assert pipeline_bridge._edge_filter_stats["passed"] == 1

    def test_edge_filter_handles_missing_price_in_market_prices(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: missing symbol price in market_prices defaults to 0.0 / 缺少的 symbol 价格默认为 0.0"""
        pipeline_bridge.set_ollama_client(mock_ollama_client)

        intent = MockIntent(symbol="UNKNOWN")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify it didn't crash and context was built
        assert mock_ollama_client.judge_edge.called
        call_args = mock_ollama_client.judge_edge.call_args
        context = call_args[0][0] if call_args[0] else ""
        assert "Current price: 0" in context

    def test_edge_filter_with_invalid_json_defaults_to_heuristic(
        self, pipeline_bridge, mock_ollama_client, mock_orchestrator
    ):
        """Test: invalid JSON triggers fallback heuristic parsing / 无效 JSON 触发回退启发式解析"""
        pipeline_bridge.set_ollama_client(mock_ollama_client)
        mock_ollama_client.judge_edge.return_value = OllamaResponse(
            text='{"has_edge": true, malformed}',  # Invalid JSON
            model="qwen3.5:27b-q4_K_M",
            success=True,
            latency_ms=150.0,
        )

        intent = MockIntent(symbol="BTCUSDT", side="Buy")
        mock_orchestrator.collect_pending_intents.return_value = [intent]

        pipeline_bridge.activate()
        pipeline_bridge.on_tick({"symbol": "BTCUSDT", "last_price": 45000.0})

        # Verify heuristic parsing kicked in (contains "true" so passes)
        assert pipeline_bridge._edge_filter_stats["passed"] == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

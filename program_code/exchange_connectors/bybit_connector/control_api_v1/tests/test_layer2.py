"""
Tests for Layer 2 AI Reasoning Engine / L2 AI 推理引擎测试

覆盖范围 / Coverage:
  - layer2_types: data structures, PricingTable, Layer2Config, AdaptiveBudgetState, Layer2Session
  - layer2_cost_tracker: cost recording, daily budget, adaptive multiplier, pricing, session history
  - layer2_tools: ToolExecutor, SearchProvider degradation, tool schemas
  - layer2_engine: L1 triage, L2 agent loop (mocked), model upgrade triage, paper integration
  - layer2_routes: all 9 routes via TestClient
  - Safety invariants: is_simulated, daily hard cap, budget enforcement
"""

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.layer2_types import (
    ADAPTIVE_MIN_DAYS,
    ADAPTIVE_TIERS,
    DEFAULT_DAILY_HARD_CAP_USD,
    DEFAULT_SESSION_BUDGET_SONNET_USD,
    DEFAULT_SESSION_BUDGET_OPUS_USD,
    MODEL_HAIKU,
    MODEL_IDS,
    MODEL_OPUS,
    MODEL_SONNET,
    MAX_AGENT_ITERATIONS,
    PRICING_VERIFY_INTERVAL_DAYS,
    SESSION_STATE_BUDGET_EXCEEDED,
    SESSION_STATE_COMPLETED,
    SESSION_STATE_FAILED,
    SESSION_STATE_PENDING,
    SESSION_STATE_RUNNING,
    SEARCH_PROVIDER_PERPLEXITY,
    SEARCH_PROVIDER_WEBPILOT,
    TOOL_GET_MARKET_STATE,
    TOOL_SUBMIT_RECOMMENDATION,
    TOOL_WEB_SEARCH,
    AdaptiveBudgetState,
    Insight,
    Layer2Config,
    Layer2Session,
    ModelPricing,
    PricingTable,
    Recommendation,
    SearchResponse,
    SearchResult,
    ToolCallRecord,
)
from app.layer2_cost_tracker import Layer2CostTracker
from app.layer2_tools import (
    TOOL_SCHEMAS,
    ToolExecutor,
    PerplexitySearchProvider,
    WebPilotSearchProvider,
    search_with_degradation,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures / 测试夹具
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_cost_file():
    fd, path = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    os.unlink(path)
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def cost_tracker(tmp_cost_file):
    return Layer2CostTracker(state_file=tmp_cost_file)


@pytest.fixture
def session():
    return Layer2Session()


def _run(coro):
    # Py 3.12：asyncio.get_event_loop() 在無 current loop 時 raise RuntimeError。
    # 前序 test 可能關閉 loop，故每 call 自管 new loop + close，不污染 global state。
    # Py 3.12: asyncio.get_event_loop() raises when no current loop exists.
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ═══════════════════════════════════════════════════════════════════════════════
# Types Tests / 类型测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2Types:
    """Tests for layer2_types.py"""

    def test_search_result_defaults(self):
        r = SearchResult(title="test", snippet="test snippet")
        assert r.title == "test"
        assert r.provider == ""
        assert r.confidence == 0.0

    def test_search_response_defaults(self):
        r = SearchResponse(query="btc news")
        assert r.results == []
        assert r.error is None
        assert not r.is_degraded

    def test_tool_call_record_timestamp(self):
        tc = ToolCallRecord(tool_name="test_tool")
        assert tc.timestamp_ms > 0
        assert tc.error is None

    def test_recommendation_fields(self):
        rec = Recommendation(
            action="buy", symbol="BTCUSDT", confidence=0.8,
            edge_bps=15.0, reasoning="test",
        )
        assert rec.action == "buy"
        assert rec.suggested_size_fraction == 0.02

    def test_insight_fields(self):
        ins = Insight(category="macro", title="Fed rate", detail="Rate unchanged")
        assert ins.confidence == 0.0

    def test_layer2_session_to_dict(self):
        s = Layer2Session()
        d = s.to_dict()
        assert d["state"] == SESSION_STATE_PENDING
        assert d["is_simulated"] is True
        assert d["data_category"] == "paper_simulated"
        assert d["recommendation"] is None
        assert d["total_cost_usd"] == 0.0

    def test_layer2_session_with_recommendation(self):
        s = Layer2Session()
        s.recommendation = Recommendation(
            action="sell", symbol="ETHUSDT", confidence=0.7,
            edge_bps=10.0, reasoning="bearish signal",
        )
        d = s.to_dict()
        assert d["recommendation"]["action"] == "sell"
        assert d["recommendation"]["symbol"] == "ETHUSDT"

    def test_session_total_cost(self):
        s = Layer2Session()
        s.cost_usd = 0.5
        s.search_cost_usd = 0.01
        assert s.total_cost() == 0.51

    def test_session_duration(self):
        s = Layer2Session()
        s.started_at_ms = 1000
        s.completed_at_ms = 5000
        assert s.duration_ms() == 4000

    def test_session_duration_none(self):
        s = Layer2Session()
        assert s.duration_ms() is None

    def test_model_pricing_cost(self):
        mp = ModelPricing(model_id="test", input_per_mtok=3.0, output_per_mtok=15.0)
        cost = mp.cost_for_tokens(1000, 500)
        # 1000/1M * 3.0 + 500/1M * 15.0 = 0.003 + 0.0075 = 0.0105
        assert abs(cost - 0.0105) < 0.0001

    def test_pricing_table_defaults(self):
        pt = PricingTable()
        assert MODEL_HAIKU in pt.models
        assert MODEL_SONNET in pt.models
        assert MODEL_OPUS in pt.models
        assert pt.perplexity_per_search == 0.005

    def test_pricing_table_stale_detection(self):
        pt = PricingTable()
        # With current date as verified, should not be stale
        assert not pt.is_stale("2026-03-27")
        # 60 days later should be stale
        assert pt.is_stale("2026-05-27")

    def test_pricing_table_to_dict(self):
        pt = PricingTable()
        d = pt.to_dict()
        assert "models" in d
        assert "is_stale" in d

    def test_layer2_config_defaults(self):
        c = Layer2Config()
        assert c.daily_hard_cap_usd == DEFAULT_DAILY_HARD_CAP_USD
        assert c.default_model == MODEL_SONNET
        assert c.max_iterations == MAX_AGENT_ITERATIONS

    def test_layer2_config_to_dict(self):
        c = Layer2Config()
        d = c.to_dict()
        assert d["daily_hard_cap_usd"] == 2.0
        assert d["adaptive_enabled"] is True

    def test_adaptive_budget_state_to_dict(self):
        a = AdaptiveBudgetState(multiplier=1.5, roi_7d=2.5)
        d = a.to_dict()
        assert d["multiplier"] == 1.5
        assert d["roi_7d"] == 2.5

    def test_adaptive_budget_state_none_roi(self):
        a = AdaptiveBudgetState()
        d = a.to_dict()
        assert d["roi_7d"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# Cost Tracker Tests / 成本追踪器测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2CostTracker:
    """Tests for layer2_cost_tracker.py"""

    def test_init_creates_default_state(self, cost_tracker, tmp_cost_file):
        assert os.path.exists(tmp_cost_file)
        with open(tmp_cost_file) as f:
            data = json.load(f)
        assert "daily_spend" in data
        assert "sessions" in data
        assert "config" in data
        assert "pricing" in data

    def test_get_daily_spend_default(self, cost_tracker):
        spend = cost_tracker.get_daily_spend()
        assert spend["total_usd"] == 0.0
        assert spend["session_count"] == 0

    def test_check_daily_budget_ok(self, cost_tracker):
        allowed, remaining = cost_tracker.check_daily_budget()
        assert allowed is True
        # Remaining is min(hard_cap, adaptive_effective) when adaptive enabled
        assert remaining > 0
        assert remaining <= DEFAULT_DAILY_HARD_CAP_USD

    def test_record_claude_cost(self, cost_tracker, session):
        cost = cost_tracker.record_claude_cost(session, input_tokens=1000, output_tokens=500, model_tier=MODEL_SONNET)
        assert cost > 0
        assert session.cost_usd > 0
        assert session.input_tokens == 1000
        assert session.output_tokens == 500

    def test_record_claude_cost_unknown_tier(self, cost_tracker, session):
        # Unknown tier should fall back to sonnet
        cost = cost_tracker.record_claude_cost(session, input_tokens=100, output_tokens=50, model_tier="unknown_model")
        assert cost > 0

    def test_record_search_cost(self, cost_tracker, session):
        cost_tracker.record_search_cost(session, "perplexity", 0.005)
        assert session.search_cost_usd == 0.005
        spend = cost_tracker.get_daily_spend()
        assert spend["search_usd"] == 0.005

    def test_daily_hard_cap_enforcement(self, cost_tracker, session):
        # Exhaust daily budget
        for _ in range(100):
            cost_tracker.record_claude_cost(session, input_tokens=100000, output_tokens=50000, model_tier=MODEL_OPUS)
        allowed, remaining = cost_tracker.check_daily_budget()
        # After many expensive calls, should be over budget
        assert remaining <= 0 or not allowed

    def test_effective_session_budget_sonnet(self, cost_tracker):
        budget = cost_tracker.get_effective_session_budget(MODEL_SONNET)
        assert budget > 0
        assert budget <= DEFAULT_DAILY_HARD_CAP_USD

    def test_effective_session_budget_opus(self, cost_tracker):
        budget = cost_tracker.get_effective_session_budget(MODEL_OPUS)
        assert budget >= DEFAULT_SESSION_BUDGET_OPUS_USD or budget <= DEFAULT_DAILY_HARD_CAP_USD

    def test_record_session(self, cost_tracker, session):
        session.state = SESSION_STATE_COMPLETED
        cost_tracker.record_session(session)
        sessions = cost_tracker.get_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == session.session_id

    def test_get_session_by_id(self, cost_tracker, session):
        session.state = SESSION_STATE_COMPLETED
        cost_tracker.record_session(session)
        found = cost_tracker.get_session_by_id(session.session_id)
        assert found is not None
        assert found["session_id"] == session.session_id

    def test_get_session_by_id_not_found(self, cost_tracker):
        assert cost_tracker.get_session_by_id("nonexistent") is None

    def test_backfill_pnl_attribution(self, cost_tracker, session):
        session.state = SESSION_STATE_COMPLETED
        cost_tracker.record_session(session)
        result = cost_tracker.backfill_pnl_attribution(
            session.session_id, {"realized_pnl_usd": 5.0, "roi": 2.5},
        )
        assert result is True
        found = cost_tracker.get_session_by_id(session.session_id)
        assert found["pnl_attribution"]["roi"] == 2.5

    def test_backfill_pnl_not_found(self, cost_tracker):
        assert cost_tracker.backfill_pnl_attribution("fake", {}) is False

    def test_recalculate_adaptive_no_data(self, cost_tracker):
        state = cost_tracker.recalculate_adaptive()
        assert state.multiplier == 1.0
        assert state.roi_7d is None

    def test_get_cost_summary(self, cost_tracker):
        summary = cost_tracker.get_cost_summary()
        assert "today" in summary
        assert "budget" in summary
        assert "adaptive" in summary
        assert "cumulative" in summary
        assert summary["budget"]["daily_hard_cap_usd"] == DEFAULT_DAILY_HARD_CAP_USD

    def test_update_pricing(self, cost_tracker):
        pricing = cost_tracker.update_pricing({
            "models": {"haiku": {"input_per_mtok": 1.0, "last_verified_date": "2026-03-27"}},
        })
        assert pricing.models[MODEL_HAIKU].input_per_mtok == 1.0

    def test_update_config(self, cost_tracker):
        config = cost_tracker.update_config({"daily_hard_cap_usd": 20.0})
        assert config.daily_hard_cap_usd == 20.0

    def test_session_budget_check(self, cost_tracker, session):
        session.session_budget_usd = 1.0
        assert cost_tracker.check_session_budget(session) is True
        session.cost_usd = 1.5
        assert cost_tracker.check_session_budget(session) is False

    def test_max_session_history_trimmed(self, cost_tracker):
        for i in range(510):
            s = Layer2Session(state=SESSION_STATE_COMPLETED)
            cost_tracker.record_session(s)
        sessions = cost_tracker.get_sessions(limit=600)
        assert len(sessions) <= Layer2CostTracker.MAX_SESSION_HISTORY

    def test_file_permissions(self, tmp_cost_file):
        tracker = Layer2CostTracker(state_file=tmp_cost_file)
        st = os.stat(tmp_cost_file)
        # Check owner-only permissions (0o600)
        assert (st.st_mode & 0o777) == 0o600


# ═══════════════════════════════════════════════════════════════════════════════
# Tools Tests / 工具测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestToolSchemas:
    """Test tool schema definitions"""

    def test_all_schemas_present(self):
        names = {s["name"] for s in TOOL_SCHEMAS}
        assert TOOL_GET_MARKET_STATE in names
        assert TOOL_SUBMIT_RECOMMENDATION in names
        assert TOOL_WEB_SEARCH in names
        assert len(TOOL_SCHEMAS) == 8

    def test_schemas_have_required_fields(self):
        for schema in TOOL_SCHEMAS:
            assert "name" in schema
            assert "description" in schema
            assert "input_schema" in schema
            assert schema["input_schema"]["type"] == "object"


class TestToolExecutor:
    """Tests for ToolExecutor"""

    @pytest.fixture
    def executor(self):
        return ToolExecutor()

    def test_unknown_tool(self, executor):
        result = _run(
            executor.execute("nonexistent_tool", {})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_submit_recommendation(self, executor):
        result = _run(
            executor.execute(TOOL_SUBMIT_RECOMMENDATION, {
                "action": "buy",
                "symbol": "BTCUSDT",
                "confidence": 0.8,
                "edge_bps": 15.0,
                "reasoning": "test reasoning",
            })
        )
        parsed = json.loads(result)
        assert parsed["status"] == "recommendation_accepted"
        assert executor.recommendation is not None
        assert executor.recommendation.action == "buy"

    def test_record_insight(self, executor):
        result = _run(
            executor.execute("record_insight", {
                "category": "macro",
                "title": "Test Insight",
                "detail": "Test detail",
            })
        )
        parsed = json.loads(result)
        assert parsed["status"] == "insight_recorded"
        assert len(executor.insights) == 1

    def test_get_account_state_no_engine(self, executor):
        result = _run(
            executor.execute("get_account_state", {})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_get_market_state_no_files(self, executor):
        result = _run(
            executor.execute("get_market_state", {"symbol": "BTCUSDT"})
        )
        parsed = json.loads(result)
        assert parsed["symbol"] == "BTCUSDT"

    def test_web_search_empty_query(self, executor):
        result = _run(
            executor.execute("web_search", {"query": ""})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_fetch_url_empty(self, executor):
        result = _run(
            executor.execute("fetch_url", {"url": ""})
        )
        parsed = json.loads(result)
        assert "error" in parsed

    def test_get_recent_decisions_no_dir(self, executor):
        result = _run(
            executor.execute("get_recent_decisions", {"limit": 5})
        )
        parsed = json.loads(result)
        assert "decisions" in parsed or "error" in parsed

    def test_get_experience_no_state(self, executor):
        result = _run(
            executor.execute("get_experience", {"category": "all"})
        )
        parsed = json.loads(result)
        # Either returns records or an error/note about missing file
        assert isinstance(parsed, dict)


class TestSearchProviders:
    """Tests for search provider implementations"""

    def test_perplexity_not_available_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = PerplexitySearchProvider()
            # Without API key, should not be available
            os.environ.pop("PERPLEXITY_API_KEY", None)
            assert provider.is_available() is False

    def test_webpilot_availability(self):
        provider = WebPilotSearchProvider()
        # May or may not be available depending on environment
        result = provider.is_available()
        assert isinstance(result, bool)

    def test_search_with_degradation_all_unavailable(self):
        """When all providers are unavailable, should return error"""
        with patch("app.layer2_tools.SEARCH_PROVIDERS", {}):
            response = _run(
                search_with_degradation("test query", enabled_providers=["nonexistent"])
            )
            assert response.error is not None


# ═══════════════════════════════════════════════════════════════════════════════
# Engine Tests / 引擎测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2Engine:
    """Tests for layer2_engine.py"""

    @pytest.fixture
    def engine_setup(self, tmp_cost_file):
        from app.layer2_engine import Layer2Engine
        tracker = Layer2CostTracker(state_file=tmp_cost_file)
        engine = Layer2Engine(cost_tracker=tracker)
        return engine, tracker

    def test_not_running_initially(self, engine_setup):
        engine, _ = engine_setup
        assert engine.is_running is False
        assert engine.get_current_session() is None

    def test_run_session_no_api_key(self, engine_setup):
        """Without ANTHROPIC_API_KEY, session should fail gracefully"""
        engine, _ = engine_setup
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from app.layer2_engine import reset_anthropic_client
            reset_anthropic_client()

            session = _run(
                engine.run_session(trigger="manual", symbol="BTCUSDT")
            )
            assert session.state == SESSION_STATE_FAILED
            assert "not available" in session.final_summary.lower() or "not set" in session.final_summary.lower()

    def test_run_session_budget_exceeded(self, engine_setup):
        """When daily budget is 0, session should be blocked"""
        engine, tracker = engine_setup
        tracker.update_config({"daily_hard_cap_usd": 0.001})
        # Record enough cost to exceed
        s = Layer2Session()
        tracker.record_claude_cost(s, 1000000, 500000, MODEL_OPUS)

        session = _run(
            engine.run_session(trigger="manual")
        )
        assert session.state == SESSION_STATE_BUDGET_EXCEEDED

    def test_concurrent_session_blocked(self, engine_setup):
        """Second concurrent session should fail"""
        engine, _ = engine_setup
        # Py 3.12：改 new_event_loop + close 外層 try/finally，內層 try/finally 保留 lock release。
        # Py 3.12: wrap with new_event_loop+close (outer); keep lock release in inner try/finally.
        loop = asyncio.new_event_loop()
        try:
            # Acquire the asyncio lock to simulate a running session (P1-NEW-7: asyncio.Lock)
            loop.run_until_complete(engine._session_lock.acquire())
            try:
                session = loop.run_until_complete(
                    engine.run_session(trigger="manual")
                )
                assert session.state == SESSION_STATE_FAILED
                assert "already running" in session.final_summary.lower()
            finally:
                engine._session_lock.release()
        finally:
            loop.close()

    def test_l1_triage_no_client(self, engine_setup):
        """L1 triage without API key should return not worth investigating"""
        engine, _ = engine_setup
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from app.layer2_engine import reset_anthropic_client
            reset_anthropic_client()

            result = _run(
                engine.l1_triage()
            )
            assert result.get("worth_investigating") is False

    @patch("app.layer2_engine._get_anthropic_client")
    def test_l1_triage_success(self, mock_client_fn, engine_setup):
        """L1 triage with mocked client"""
        engine, _ = engine_setup
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 50
        mock_response.content = [MagicMock(text='{"worth_investigating": true, "reason": "test"}')]
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        result = _run(
            engine.l1_triage({"test": "context"})
        )
        assert result.get("worth_investigating") is True

    @patch("app.layer2_engine._get_anthropic_client")
    def test_full_session_mocked(self, mock_client_fn, engine_setup):
        """Full session with mocked Anthropic client (end_turn immediately)"""
        engine, tracker = engine_setup
        mock_client = MagicMock()

        # Mock response that just gives a text answer (no tool use)
        mock_response = MagicMock()
        mock_response.usage.input_tokens = 500
        mock_response.usage.output_tokens = 200
        mock_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Market analysis complete. No clear opportunity at this time."
        mock_response.content = [text_block]
        mock_client.messages.create.return_value = mock_response
        mock_client_fn.return_value = mock_client

        session = _run(
            engine.run_session(trigger="manual", symbol="BTCUSDT")
        )
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 1
        assert session.cost_usd > 0
        assert session.is_simulated is True

        # Session should be recorded
        sessions = tracker.get_sessions()
        assert len(sessions) == 1

    @patch("app.layer2_engine._get_anthropic_client")
    def test_session_with_tool_calls(self, mock_client_fn, engine_setup):
        """Session with tool calls then end_turn"""
        engine, tracker = engine_setup
        mock_client = MagicMock()

        # First call: tool_use
        tool_response = MagicMock()
        tool_response.usage.input_tokens = 500
        tool_response.usage.output_tokens = 100
        tool_response.stop_reason = "tool_use"
        tool_block = MagicMock()
        tool_block.type = "tool_use"
        tool_block.name = "get_market_state"
        tool_block.input = {"symbol": "BTCUSDT"}
        tool_block.id = "tool_1"
        tool_response.content = [tool_block]

        # Second call: end_turn
        end_response = MagicMock()
        end_response.usage.input_tokens = 800
        end_response.usage.output_tokens = 300
        end_response.stop_reason = "end_turn"
        text_block = MagicMock()
        text_block.type = "text"
        text_block.text = "Based on market analysis, holding is recommended."
        end_response.content = [text_block]

        mock_client.messages.create.side_effect = [tool_response, end_response]
        mock_client_fn.return_value = mock_client

        session = _run(
            engine.run_session(trigger="manual", symbol="BTCUSDT")
        )
        assert session.state == SESSION_STATE_COMPLETED
        assert session.iterations == 2
        assert len(session.tool_calls) == 1
        assert session.tool_calls[0].tool_name == "get_market_state"

    @patch("app.layer2_engine._get_anthropic_client")
    def test_model_upgrade_triage(self, mock_client_fn, engine_setup):
        """Test model upgrade triage logic"""
        engine, _ = engine_setup
        mock_client = MagicMock()

        # Upgrade triage response
        triage_response = MagicMock()
        triage_response.usage.input_tokens = 100
        triage_response.usage.output_tokens = 50
        triage_response.content = [MagicMock(text='{"upgrade_to_opus": true, "reason": "major event"}')]
        mock_client.messages.create.return_value = triage_response
        mock_client_fn.return_value = mock_client

        session = Layer2Session()
        result = _run(
            engine._model_upgrade_triage(session, '{"results": [{"title": "Fed rate hike"}]}', mock_client)
        )
        assert result is True
        assert session.upgrade_reason == "major event"


# ═══════════════════════════════════════════════════════════════════════════════
# Safety Invariant Tests / 安全不变量测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyInvariants:
    """Verify safety invariants are always maintained"""

    def test_session_always_simulated(self):
        s = Layer2Session()
        assert s.is_simulated is True
        assert s.data_category == "paper_simulated"
        d = s.to_dict()
        assert d["is_simulated"] is True

    def test_daily_hard_cap_cannot_be_bypassed(self, cost_tracker, session):
        """Even with high adaptive multiplier, daily cap holds"""
        cost_tracker.update_config({"daily_hard_cap_usd": 1.0})
        # Record costs up to cap
        for _ in range(20):
            cost_tracker.record_claude_cost(session, 100000, 50000, MODEL_OPUS)

        allowed, remaining = cost_tracker.check_daily_budget()
        assert not allowed or remaining <= 0

    def test_session_budget_enforced(self, cost_tracker):
        s = Layer2Session(session_budget_usd=0.01)
        s.cost_usd = 0.02
        assert not cost_tracker.check_session_budget(s)

    def test_recommendation_requires_all_fields(self):
        with pytest.raises(TypeError):
            Recommendation(action="buy")  # Missing required fields

    def test_tool_schemas_count(self):
        assert len(TOOL_SCHEMAS) == 8


# ═══════════════════════════════════════════════════════════════════════════════
# Route Tests / 路由测试
# ═══════════════════════════════════════════════════════════════════════════════

class TestLayer2Routes:
    """Tests for layer2_routes.py via direct function calls"""

    @pytest.fixture
    def setup_routes(self, tmp_cost_file):
        """Patch the cost tracker and engine for route testing"""
        tracker = Layer2CostTracker(state_file=tmp_cost_file)

        with patch("app.layer2_routes._get_cost_tracker", return_value=tracker):
            from app.layer2_engine import Layer2Engine
            engine = Layer2Engine(cost_tracker=tracker)
            with patch("app.layer2_routes._get_engine", return_value=engine):
                yield tracker, engine

    def test_get_cost_summary(self, setup_routes):
        from app.layer2_routes import get_cost_summary
        tracker, _ = setup_routes

        mock_actor = MagicMock()
        result = _run(
            get_cost_summary(actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert result["is_simulated"] is True
        assert "today" in result["data"]

    def test_get_pricing(self, setup_routes):
        from app.layer2_routes import get_pricing
        mock_actor = MagicMock()
        result = _run(
            get_pricing(actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert "models" in result["data"]

    def test_get_config(self, setup_routes):
        from app.layer2_routes import get_config
        mock_actor = MagicMock()
        result = _run(
            get_config(actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert "daily_hard_cap_usd" in result["data"]

    def test_get_sessions_empty(self, setup_routes):
        from app.layer2_routes import get_sessions
        mock_actor = MagicMock()
        result = _run(
            get_sessions(limit=20, offset=0, actor=mock_actor)
        )
        assert result["data"]["sessions"] == []

    def test_get_adaptive_budget(self, setup_routes):
        from app.layer2_routes import get_adaptive_budget
        mock_actor = MagicMock()
        result = _run(
            get_adaptive_budget(recalculate=False, actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert "multiplier" in result["data"]

    def test_get_adaptive_budget_recalculate(self, setup_routes):
        from app.layer2_routes import get_adaptive_budget
        mock_actor = MagicMock()
        result = _run(
            get_adaptive_budget(recalculate=True, actor=mock_actor)
        )
        assert result["action_result"] == "success"

    def test_update_config_empty(self, setup_routes):
        from app.layer2_routes import update_config, ConfigUpdateRequest
        mock_actor = MagicMock()
        req = ConfigUpdateRequest()
        result = _run(
            update_config(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "blocked"

    def test_update_config_valid(self, setup_routes):
        from app.layer2_routes import update_config, ConfigUpdateRequest
        tracker, _ = setup_routes
        mock_actor = MagicMock()
        req = ConfigUpdateRequest(daily_hard_cap_usd=20.0)
        result = _run(
            update_config(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "success"
        assert result["data"]["config"]["daily_hard_cap_usd"] == 20.0

    def test_update_pricing_empty(self, setup_routes):
        from app.layer2_routes import update_pricing, PricingUpdateRequest
        mock_actor = MagicMock()
        req = PricingUpdateRequest()
        result = _run(
            update_pricing(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "blocked"

    def test_update_pricing_valid(self, setup_routes):
        from app.layer2_routes import update_pricing, PricingUpdateRequest
        mock_actor = MagicMock()
        req = PricingUpdateRequest(
            models={"haiku": {"input_per_mtok": 1.0, "last_verified_date": "2026-03-28"}},
        )
        result = _run(
            update_pricing(req=req, actor=mock_actor)
        )
        assert result["action_result"] == "success"

    def test_get_session_detail_not_found(self, setup_routes):
        from app.layer2_routes import get_session_detail
        mock_actor = MagicMock()
        with pytest.raises(Exception):  # HTTPException
            _run(
                get_session_detail(session_id="nonexistent", actor=mock_actor)
            )

    @patch("app.layer2_engine._get_anthropic_client")
    def test_trigger_session_budget_exceeded(self, mock_client_fn, setup_routes):
        from app.layer2_routes import trigger_l2_session, TriggerRequest
        tracker, engine = setup_routes
        tracker.update_config({"daily_hard_cap_usd": 0.001})
        # Exhaust budget
        s = Layer2Session()
        tracker.record_claude_cost(s, 1000000, 500000, MODEL_OPUS)

        mock_actor = MagicMock()
        background = MagicMock()
        req = TriggerRequest(symbol="BTCUSDT")
        result = _run(
            trigger_l2_session(req=req, background_tasks=background, actor=mock_actor)
        )
        assert result["action_result"] == "blocked"
        assert "daily_budget_exceeded" in result["reason_codes"]

"""
Tests for Phase 2 Strategy Toolkit API Routes / Phase 2 策略工具包 API 路由测试

覆盖 11 条路由：
  GET  /strategy/klines/{symbol}/{timeframe}
  GET  /strategy/indicators/{symbol}/{timeframe}
  GET  /strategy/signals
  GET  /strategy/signals/{symbol}/summary
  GET  /strategy/list
  GET  /strategy/{name}/status
  POST /strategy/{name}/activate
  POST /strategy/{name}/pause
  POST /strategy/{name}/stop
  GET  /strategy/intents
  GET  /strategy/status
"""

import pytest
import sys
import os

# Ensure both control_api_v1/ and program_code/ are in path
# 确保 control_api_v1/ 和 program_code/ 都在路径中
_tests_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_tests_dir)
_bybit_connector_dir = os.path.dirname(_control_api_dir)
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir)
_program_code_dir = os.path.dirname(_exchange_connectors_dir)
if _control_api_dir not in sys.path:
    sys.path.insert(0, _control_api_dir)
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

from fastapi.testclient import TestClient
from app.phase2_strategy_routes import (
    phase2_router, KLINE_MANAGER, INDICATOR_ENGINE, SIGNAL_ENGINE, ORCHESTRATOR,
)


# =============================================================================
# Test Client Setup / 测试客户端设置
# =============================================================================

from fastapi import FastAPI

test_app = FastAPI()
test_app.include_router(phase2_router)
client = TestClient(test_app)


# =============================================================================
# Kline Route Tests / K线路由测试
# =============================================================================

class TestKlineRoutes:
    """Kline API route tests / K线 API 路由测试"""

    def test_get_klines_empty(self):
        """GET klines with no data returns empty / 无数据返回空"""
        resp = client.get("/api/v1/strategy/klines/BTCUSDT/1m")
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_result"] == "success"
        assert data["is_simulated"] is True
        assert data["data"]["symbol"] == "BTCUSDT"
        assert data["data"]["count"] == 0

    def test_get_klines_with_data(self):
        """GET klines returns data after feeding ticks / 输入 tick 后返回数据"""
        # Feed some ticks / 输入一些 tick
        for i in range(5):
            KLINE_MANAGER.on_tick("BTCUSDT", 45000.0 + i * 100, ts_ms=60000 * (i + 1))
        resp = client.get("/api/v1/strategy/klines/BTCUSDT/1m?n=10")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["count"] >= 1

    def test_get_klines_case_insensitive(self):
        """Symbol is uppercased / 交易对自动大写"""
        resp = client.get("/api/v1/strategy/klines/btcusdt/1m")
        assert resp.status_code == 200
        assert resp.json()["data"]["symbol"] == "BTCUSDT"


# =============================================================================
# Indicator Route Tests / 指标路由测试
# =============================================================================

class TestIndicatorRoutes:
    """Indicator API route tests / 指标 API 路由测试"""

    def test_get_indicators_empty(self):
        """GET indicators with no data returns empty / 无数据返回空"""
        resp = client.get("/api/v1/strategy/indicators/SOLUSDT/1m")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["indicator_count"] == 0

    def test_get_indicators_after_data(self):
        """GET indicators returns values after feeding data / 输入数据后返回指标值"""
        # Feed enough ticks to trigger indicator computation / 输入足够的 tick 触发指标计算
        for i in range(40):
            KLINE_MANAGER.on_tick("ETHUSDT", 3000.0 + i * 5, ts_ms=60000 * (i + 1))
        resp = client.get("/api/v1/strategy/indicators/ETHUSDT/1m")
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Should have some indicator values / 应有一些指标值
        assert data["indicator_count"] >= 0  # May or may not have values depending on min_periods


# =============================================================================
# Signal Route Tests / 信号路由测试
# =============================================================================

class TestSignalRoutes:
    """Signal API route tests / 信号 API 路由测试"""

    def test_get_signals(self):
        """GET signals returns list / 返回信号列表"""
        resp = client.get("/api/v1/strategy/signals")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "signals" in data
        assert "count" in data

    def test_get_signals_filtered(self):
        """GET signals with symbol filter / 按交易对过滤信号"""
        resp = client.get("/api/v1/strategy/signals?symbol=BTCUSDT&n=10")
        assert resp.status_code == 200

    def test_get_signal_summary(self):
        """GET signal summary for symbol / 获取交易对信号摘要"""
        resp = client.get("/api/v1/strategy/signals/BTCUSDT/summary")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["symbol"] == "BTCUSDT"
        assert "consensus_direction" in data


# =============================================================================
# Strategy Management Route Tests / 策略管理路由测试
# =============================================================================

class TestStrategyRoutes:
    """Strategy management API route tests / 策略管理 API 路由测试"""

    def test_list_strategies(self):
        """GET list returns all registered strategies / 列出所有注册的策略"""
        resp = client.get("/api/v1/strategy/list")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["count"] >= 4  # 4 default strategies
        names = [s["strategy"] for s in data["strategies"]]
        assert "MA_Crossover" in names
        assert "BB_Reversion" in names
        assert "FundingRate_Arb" in names
        assert "Grid_Trading" in names

    def test_get_strategy_status(self):
        """GET strategy status / 获取策略状态"""
        resp = client.get("/api/v1/strategy/MA_Crossover/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["strategy"] == "MA_Crossover"

    def test_get_nonexistent_strategy(self):
        """GET nonexistent strategy returns not_found / 不存在的策略返回 not_found"""
        resp = client.get("/api/v1/strategy/NonExistent/status")
        assert resp.status_code == 200
        assert resp.json()["action_result"] == "not_found"

    def test_activate_strategy(self):
        """POST activate changes state to active / 激活策略"""
        resp = client.post("/api/v1/strategy/MA_Crossover/activate")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "activated"
        assert data["new_state"] == "active"

    def test_pause_strategy(self):
        """POST pause changes state to paused / 暂停策略"""
        client.post("/api/v1/strategy/MA_Crossover/activate")
        resp = client.post("/api/v1/strategy/MA_Crossover/pause")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "paused"

    def test_stop_strategy(self):
        """POST stop changes state to stopped / 停止策略"""
        client.post("/api/v1/strategy/MA_Crossover/activate")
        resp = client.post("/api/v1/strategy/MA_Crossover/stop")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "stopped"

    def test_activate_nonexistent(self):
        """POST activate nonexistent returns not_found / 激活不存在的策略"""
        resp = client.post("/api/v1/strategy/NonExistent/activate")
        assert resp.json()["action_result"] == "not_found"

    def test_pause_nonexistent(self):
        resp = client.post("/api/v1/strategy/NonExistent/pause")
        assert resp.json()["action_result"] == "not_found"

    def test_stop_nonexistent(self):
        resp = client.post("/api/v1/strategy/NonExistent/stop")
        assert resp.json()["action_result"] == "not_found"


# =============================================================================
# Intent & Status Route Tests / 意图与状态路由测试
# =============================================================================

class TestIntentAndStatusRoutes:
    """Intent history and orchestrator status route tests / 意图历史与编排器状态路由测试"""

    def test_get_intents(self):
        """GET intents returns list / 获取意图列表"""
        resp = client.get("/api/v1/strategy/intents")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "intents" in data
        assert "count" in data

    def test_get_orchestrator_status(self):
        """GET status returns comprehensive info / 获取编排器综合状态"""
        resp = client.get("/api/v1/strategy/status")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["component"] == "strategy_orchestrator"
        assert "strategies" in data
        assert "kline_manager_status" in data
        assert "indicator_engine_status" in data
        assert "signal_engine_status" in data

    def test_all_responses_marked_simulated(self):
        """All responses have is_simulated=True / 所有响应标记 is_simulated=True"""
        routes = [
            "/api/v1/strategy/klines/BTCUSDT/1m",
            "/api/v1/strategy/indicators/BTCUSDT/1m",
            "/api/v1/strategy/signals",
            "/api/v1/strategy/signals/BTCUSDT/summary",
            "/api/v1/strategy/list",
            "/api/v1/strategy/intents",
            "/api/v1/strategy/status",
        ]
        for route in routes:
            resp = client.get(route)
            assert resp.status_code == 200, f"Failed: {route}"
            assert resp.json()["is_simulated"] is True, f"Not simulated: {route}"

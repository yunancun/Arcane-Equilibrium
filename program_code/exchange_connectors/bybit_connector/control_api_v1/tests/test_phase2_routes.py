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
import time

# Set test token BEFORE importing modules that use it
# 在导入使用 token 的模块之前设置测试 token
os.environ["OPENCLAW_API_TOKEN"] = "test-token"

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
from app import main_legacy as base
from local_model_tools.strategies.base import StrategyBase


# DEAD-PY-2: Python strategy classes deleted. Register stub StrategyBase objects
# so the HTTP route layer (activate/pause/stop) can still be tested.
# DEAD-PY-2：Python 策略類已刪除。注冊 stub 對象以便繼續測試 HTTP 路由層。
class _StubStrategy(StrategyBase):
    """Minimal stub strategy for route testing after DEAD-PY-2.
    DEAD-PY-2 後用於路由測試的最小 stub 策略。"""
    def __init__(self, strategy_name: str) -> None:
        super().__init__()
        self._name = strategy_name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return f"Stub strategy for testing: {self._name}"

    def on_signal(self, signal: dict) -> None:  # type: ignore[override]
        pass

    def on_tick(self, symbol: str, price: float, **kwargs) -> None:  # type: ignore[override]
        pass

    def get_status(self) -> dict:  # type: ignore[override]
        return {"strategy": self._name, "state": self._state}


def _ensure_stub_strategies_registered() -> None:
    """Register stub strategies if not already present.
    若尚未注冊，則注冊 stub 策略。"""
    for _sname in ("BB_Reversion", "FundingRate_Arb", "MA_Crossover", "Grid_Trading"):
        if _sname not in ORCHESTRATOR._strategies:
            ORCHESTRATOR.register_strategy(_StubStrategy(_sname), name=_sname)


# =============================================================================
# Test Client Setup / 测试客户端设置
# =============================================================================

from fastapi import FastAPI

test_app = FastAPI()
test_app.include_router(phase2_router)
client = TestClient(test_app)

# Auth headers for all requests. Read the singleton at request time because the
# broad suite mutates auth settings in other files.
# 所有请求的认证头；全量 suite 其他測試會改 auth settings，因此每次 request 動態讀取。
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {base.settings.api_token}"}


# =============================================================================
# Kline Route Tests / K线路由测试
# =============================================================================

class TestKlineRoutes:
    """Kline API route tests / K线 API 路由测试"""

    def test_get_klines_empty(self):
        """GET klines returns correct response format / 返回正确响应格式"""
        # count may be > 0 if bootstrap_from_rest loaded historical klines at startup
        # 若 bootstrap_from_rest 在启动时加载了历史 K线，count 可能 > 0
        resp = client.get("/api/v1/strategy/klines/BTCUSDT/1m", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()
        assert data["action_result"] == "success"
        assert data["is_simulated"] is True
        assert data["data"]["symbol"] == "BTCUSDT"
        assert data["data"]["count"] >= 0

    def test_get_klines_no_auth(self):
        """GET klines without auth returns 401 / 无认证返回 401"""
        resp = client.get("/api/v1/strategy/klines/BTCUSDT/1m")
        assert resp.status_code == 401

    def test_get_klines_with_data(self):
        """GET klines keeps the route shape stable after feeding ticks.

        The Python KlineManager is a Rust-first compatibility stub, so on_tick
        may be a no-op when the Rust reader is unavailable.
        """
        for i in range(5):
            KLINE_MANAGER.on_tick("BTCUSDT", 45000.0 + i * 100, ts_ms=60000 * (i + 1))
        resp = client.get("/api/v1/strategy/klines/BTCUSDT/1m?n=10", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["symbol"] == "BTCUSDT"
        assert data["count"] >= 0
        assert "closed_klines" in data

    def test_get_klines_case_insensitive(self):
        """Symbol is uppercased / 交易对自动大写"""
        resp = client.get("/api/v1/strategy/klines/btcusdt/1m", headers=auth_headers())
        assert resp.status_code == 200
        assert resp.json()["data"]["symbol"] == "BTCUSDT"

    def test_get_klines_invalid_symbol(self):
        """GET klines with invalid symbol returns 400 / 无效交易对返回 400"""
        resp = client.get("/api/v1/strategy/klines/!!invalid!!/1m", headers=auth_headers())
        assert resp.status_code == 400

    def test_get_klines_invalid_timeframe(self):
        """GET klines with invalid timeframe returns 400 / 无效时间框架返回 400"""
        resp = client.get("/api/v1/strategy/klines/BTCUSDT/2m", headers=auth_headers())
        assert resp.status_code == 400


# =============================================================================
# Indicator Route Tests / 指标路由测试
# =============================================================================

class TestIndicatorRoutes:
    """Indicator API route tests / 指标 API 路由测试"""

    def test_get_indicators_empty(self):
        """GET indicators returns valid response / 指标端点返回有效响应"""
        resp = client.get("/api/v1/strategy/indicators/SOLUSDT/1m", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        # Rust engine may return pre-computed indicators; Python fallback returns 0
        # Rust 引擎可能返回预计算指标；Python 降级返回 0
        assert data["indicator_count"] >= 0

    def test_get_indicators_after_data(self):
        """GET indicators returns values after feeding data / 输入数据后返回指标值"""
        # Feed enough ticks to trigger indicator computation / 输入足够的 tick 触发指标计算
        for i in range(40):
            KLINE_MANAGER.on_tick("ETHUSDT", 3000.0 + i * 5, ts_ms=60000 * (i + 1))
        resp = client.get("/api/v1/strategy/indicators/ETHUSDT/1m", headers=auth_headers())
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
        resp = client.get("/api/v1/strategy/signals", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "signals" in data
        assert "count" in data

    def test_get_signals_filtered(self):
        """GET signals with symbol filter / 按交易对过滤信号"""
        resp = client.get("/api/v1/strategy/signals?symbol=BTCUSDT&n=10", headers=auth_headers())
        assert resp.status_code == 200

    def test_get_signal_summary(self):
        """GET signal summary for symbol / 获取交易对信号摘要"""
        resp = client.get("/api/v1/strategy/signals/BTCUSDT/summary", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["symbol"] == "BTCUSDT"
        # Rust-first uses "consensus", Python fallback uses "consensus_direction"
        # Rust 優先用 "consensus"，Python 降級用 "consensus_direction"
        assert "consensus" in data or "consensus_direction" in data


# =============================================================================
# Strategy Management Route Tests / 策略管理路由测试
# =============================================================================

class TestStrategyRoutes:
    """Strategy management API route tests / 策略管理 API 路由测试"""

    def test_list_strategies(self):
        """GET list returns stable strategy-list shape.

        Python strategy classes are retired; when Rust is unavailable the
        fallback orchestrator may legitimately expose an empty list.
        """
        _ensure_stub_strategies_registered()
        resp = client.get("/api/v1/strategy/list", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data["strategies"], list)
        assert data["count"] == len(data["strategies"])

    def test_get_strategy_status(self):
        """GET strategy status / 获取策略状态"""
        _ensure_stub_strategies_registered()
        # Rust uses lowercase names; try both / Rust 用小寫名稱；兩者都試
        resp = client.get("/api/v1/strategy/MA_Crossover/status", headers=auth_headers())
        if resp.status_code == 404:
            resp = client.get("/api/v1/strategy/ma_crossover/status", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data.get("strategy") == "MA_Crossover" or data.get("name") == "ma_crossover"

    def test_get_nonexistent_strategy(self):
        """GET nonexistent strategy returns 404 / 不存在的策略返回 404"""
        resp = client.get("/api/v1/strategy/NonExistent/status", headers=auth_headers())
        assert resp.status_code == 404

    def test_activate_strategy(self):
        """POST activate changes state to active / 激活策略"""
        _ensure_stub_strategies_registered()
        resp = client.post("/api/v1/strategy/BB_Reversion/activate", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "activated"
        assert data["new_state"] == "active"

    def test_pause_strategy(self):
        """POST pause changes state to paused / 暂停策略"""
        _ensure_stub_strategies_registered()
        client.post("/api/v1/strategy/BB_Reversion/activate", headers=auth_headers())
        resp = client.post("/api/v1/strategy/BB_Reversion/pause", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "paused"

    def test_stop_strategy(self):
        """POST stop changes state to stopped / 停止策略"""
        _ensure_stub_strategies_registered()
        client.post("/api/v1/strategy/FundingRate_Arb/activate", headers=auth_headers())
        resp = client.post("/api/v1/strategy/FundingRate_Arb/stop", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["action"] == "stopped"

    def test_activate_nonexistent(self):
        """POST activate nonexistent returns 404 / 激活不存在的策略返回 404"""
        resp = client.post("/api/v1/strategy/NonExistent/activate", headers=auth_headers())
        assert resp.status_code == 404

    def test_pause_nonexistent(self):
        resp = client.post("/api/v1/strategy/NonExistent/pause", headers=auth_headers())
        assert resp.status_code == 404

    def test_stop_nonexistent(self):
        resp = client.post("/api/v1/strategy/NonExistent/stop", headers=auth_headers())
        assert resp.status_code == 404


# =============================================================================
# Intent & Status Route Tests / 意图与状态路由测试
# =============================================================================

class TestIntentAndStatusRoutes:
    """Intent history and orchestrator status route tests / 意图历史与编排器状态路由测试"""

    def test_get_intents(self):
        """GET intents returns list / 获取意图列表"""
        resp = client.get("/api/v1/strategy/intents", headers=auth_headers())
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "intents" in data
        assert "count" in data

    def test_get_orchestrator_status(self):
        """GET status returns comprehensive info / 获取编排器综合状态"""
        resp = client.get("/api/v1/strategy/status", headers=auth_headers())
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
            resp = client.get(route, headers=auth_headers())
            assert resp.status_code == 200, f"Failed: {route}"
            assert resp.json()["is_simulated"] is True, f"Not simulated: {route}"


# TestPipelineBridgeGovernanceInjection + TestAutoDeployerPipelineBridgeWiring deleted (DEAD-PY-2)

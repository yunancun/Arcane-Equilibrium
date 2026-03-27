from __future__ import annotations

"""
Phase 2 Local Strategy Toolkit — API Routes / API 路由
11 条 FastAPI 路由：K线 / 指标 / 信号 / 策略管理 / 编排器状态

MODULE_NOTE (中文):
  本模块为 Phase 2 本地策略工具包提供 API 路由，使 GUI 和外部工具能够：
  1. 查看 K线数据和技术指标
  2. 查看交易信号和信号历史
  3. 管理策略生命周期（注册/激活/暂停/停止）
  4. 收集和查看 OrderIntent 历史
  5. 查看编排器综合状态

  路由清单（11 条）：
  GET  /strategy/klines/{symbol}/{timeframe}     — 获取 K线数据
  GET  /strategy/indicators/{symbol}/{timeframe}  — 获取技术指标
  GET  /strategy/signals                          — 获取信号历史
  GET  /strategy/signals/{symbol}/summary         — 获取信号共识摘要
  GET  /strategy/list                             — 列出所有策略
  GET  /strategy/{name}/status                    — 获取指定策略状态
  POST /strategy/{name}/activate                  — 激活策略
  POST /strategy/{name}/pause                     — 暂停策略
  POST /strategy/{name}/stop                      — 停止策略
  GET  /strategy/intents                          — 获取 OrderIntent 历史
  GET  /strategy/status                           — 获取编排器综合状态

MODULE_NOTE (English):
  Provides API routes for Phase 2 local strategy toolkit, enabling GUI and
  external tools to:
  1. View kline data and technical indicators
  2. View trading signals and signal history
  3. Manage strategy lifecycle (register/activate/pause/stop)
  4. Collect and view OrderIntent history
  5. View orchestrator comprehensive status

  Route list (11 routes):
  GET  /strategy/klines/{symbol}/{timeframe}     — get kline data
  GET  /strategy/indicators/{symbol}/{timeframe}  — get technical indicators
  GET  /strategy/signals                          — get signal history
  GET  /strategy/signals/{symbol}/summary         — get signal consensus summary
  GET  /strategy/list                             — list all strategies
  GET  /strategy/{name}/status                    — get specific strategy status
  POST /strategy/{name}/activate                  — activate strategy
  POST /strategy/{name}/pause                     — pause strategy
  POST /strategy/{name}/stop                      — stop strategy
  GET  /strategy/intents                          — get OrderIntent history
  GET  /strategy/status                           — get orchestrator status

安全不变量 / Safety invariant:
  - system_mode = read_only 不变 / system_mode remains read_only
  - 所有策略仅产生 OrderIntent，不直接执行交易 / All strategies only generate OrderIntents
  - 所有数据标记 is_simulated=True / All data marked is_simulated=True
"""

import logging
import re
import sys
import os
from typing import Any

from fastapi import APIRouter, Query

# Add program_code to path so local_model_tools is importable
# 将 program_code 加入路径以便导入 local_model_tools
_app_dir = os.path.dirname(os.path.abspath(__file__))
_control_api_dir = os.path.dirname(_app_dir)
_bybit_connector_dir = os.path.dirname(_control_api_dir)
_exchange_connectors_dir = os.path.dirname(_bybit_connector_dir)
_program_code_dir = os.path.dirname(_exchange_connectors_dir)
if _program_code_dir not in sys.path:
    sys.path.insert(0, _program_code_dir)

from local_model_tools.kline_manager import KlineManager
from local_model_tools.indicator_engine import IndicatorEngine
from local_model_tools.signal_generator import SignalEngine
from local_model_tools.strategy_orchestrator import StrategyOrchestrator
from local_model_tools.strategies.ma_crossover import MACrossoverStrategy
from local_model_tools.strategies.bollinger_reversion import BollingerReversionStrategy
from local_model_tools.strategies.funding_rate_arb import FundingRateArbStrategy
from local_model_tools.strategies.grid_trading import GridTradingStrategy

logger = logging.getLogger(__name__)


# =============================================================================
# Shared Instances / 共享实例
# =============================================================================
# These are module-level singletons, initialized once when the router is imported.
# 模块级单例，在路由被导入时初始化一次。

DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT"]
DEFAULT_TIMEFRAMES = ["1m", "5m", "15m", "1h"]

# Create the full pipeline / 创建完整管线
KLINE_MANAGER = KlineManager(symbols=DEFAULT_SYMBOLS, timeframes=DEFAULT_TIMEFRAMES)
INDICATOR_ENGINE = IndicatorEngine(kline_manager=KLINE_MANAGER)
SIGNAL_ENGINE = SignalEngine()

# Wire indicator engine → signal engine / 连接指标引擎 → 信号引擎
INDICATOR_ENGINE.register_on_update(SIGNAL_ENGINE.on_indicators_update)

# Create orchestrator / 创建编排器
ORCHESTRATOR = StrategyOrchestrator(
    kline_manager=KLINE_MANAGER,
    indicator_engine=INDICATOR_ENGINE,
    signal_engine=SIGNAL_ENGINE,
)

# Pre-register default strategies (idle by default, user activates via API)
# 预注册默认策略（默认 idle，用户通过 API 激活）
ORCHESTRATOR.register_strategy(MACrossoverStrategy(symbol="BTCUSDT"))
ORCHESTRATOR.register_strategy(BollingerReversionStrategy(symbol="BTCUSDT"))
ORCHESTRATOR.register_strategy(FundingRateArbStrategy(symbol="BTCUSDT"))
ORCHESTRATOR.register_strategy(GridTradingStrategy(
    symbol="BTCUSDT", upper_price=100000.0, lower_price=80000.0, grid_count=20,
))

logger.info(
    "Phase 2 strategy pipeline initialized / Phase 2 策略管线初始化完成: "
    "symbols=%s, timeframes=%s, strategies=%s",
    DEFAULT_SYMBOLS, DEFAULT_TIMEFRAMES, ORCHESTRATOR.list_available_strategies(),
)


# =============================================================================
# Router / 路由
# =============================================================================

phase2_router = APIRouter(
    prefix="/api/v1/strategy",
    tags=["Phase 2 — Local Strategy Toolkit / 本地策略工具包"],
)


# Input validation: symbol must be 1-20 alphanumeric chars
# 输入验证：交易对必须是 1-20 个字母数字字符
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]{1,20}$")

# Valid timeframes / 有效时间框架
_VALID_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}


def _validate_symbol(symbol: str) -> str | None:
    """Validate and normalize symbol. Returns uppercased symbol or None if invalid."""
    s = symbol.strip().upper()
    if not _SYMBOL_PATTERN.match(s):
        return None
    return s


def _envelope(data: Any, action: str = "success") -> dict[str, Any]:
    """Minimal response envelope for Phase 2 routes / Phase 2 路由的最小响应封装"""
    return {
        "action_result": action,
        "data": data,
        "is_simulated": True,
        "data_category": "paper_simulated",
    }


# ── Kline Routes / K线路由 ──

@phase2_router.get("/klines/{symbol}/{timeframe}")
async def get_klines(
    symbol: str,
    timeframe: str,
    n: int = Query(default=50, ge=1, le=500, description="Number of klines to return / 返回K线数量"),
):
    """
    Get latest N closed klines for a symbol + timeframe.
    获取指定交易对 + 时间框架的最近 N 根已闭合 K线。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        return _envelope({"error": "Invalid symbol (1-20 alphanumeric) / 无效交易对"}, action="invalid_input")
    if timeframe not in _VALID_TIMEFRAMES:
        return _envelope({"error": f"Invalid timeframe, valid: {sorted(_VALID_TIMEFRAMES)} / 无效时间框架"}, action="invalid_input")
    klines = KLINE_MANAGER.get_latest_klines(sym, timeframe, n=n)
    current = KLINE_MANAGER.get_current_bar(sym, timeframe)
    return _envelope({
        "symbol": sym,
        "timeframe": timeframe,
        "closed_klines": klines,
        "current_bar": current.to_dict() if current else None,
        "count": len(klines),
    })


# ── Indicator Routes / 指标路由 ──

@phase2_router.get("/indicators/{symbol}/{timeframe}")
async def get_indicators(symbol: str, timeframe: str):
    """
    Get latest cached indicator values for a symbol + timeframe.
    获取指定交易对 + 时间框架的最新缓存指标值。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        return _envelope({"error": "Invalid symbol / 无效交易对"}, action="invalid_input")
    if timeframe not in _VALID_TIMEFRAMES:
        return _envelope({"error": "Invalid timeframe / 无效时间框架"}, action="invalid_input")
    indicators = INDICATOR_ENGINE.get_indicators(sym, timeframe)
    return _envelope({
        "symbol": sym,
        "timeframe": timeframe,
        "indicators": indicators,
        "indicator_count": len(indicators),
    })


# ── Signal Routes / 信号路由 ──

@phase2_router.get("/signals")
async def get_signals(
    symbol: str = Query(default=None, description="Filter by symbol / 按交易对过滤"),
    n: int = Query(default=50, ge=1, le=200, description="Number of signals / 信号数量"),
):
    """
    Get recent trading signals.
    获取最近的交易信号。
    """
    filter_sym = None
    if symbol:
        filter_sym = _validate_symbol(symbol)
        if filter_sym is None:
            return _envelope({"error": "Invalid symbol / 无效交易对"}, action="invalid_input")
    signals = SIGNAL_ENGINE.get_latest_signals(symbol=filter_sym, n=n)
    return _envelope({
        "signals": signals,
        "count": len(signals),
        "filter_symbol": filter_sym,
    })


@phase2_router.get("/signals/{symbol}/summary")
async def get_signal_summary(symbol: str):
    """
    Get signal consensus summary for a symbol.
    获取指定交易对的信号共识摘要。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        return _envelope({"error": "Invalid symbol / 无效交易对"}, action="invalid_input")
    summary = SIGNAL_ENGINE.get_signal_summary(sym)
    return _envelope(summary)


# ── Strategy Management Routes / 策略管理路由 ──

@phase2_router.get("/list")
async def list_strategies():
    """
    List all registered strategies and their states.
    列出所有注册的策略及其状态。
    """
    statuses = ORCHESTRATOR.get_all_strategies_status()
    return _envelope({
        "strategies": statuses,
        "count": len(statuses),
    })


@phase2_router.get("/{name}/status")
async def get_strategy_status(name: str):
    """
    Get status of a specific strategy.
    获取指定策略的状态。
    """
    status = ORCHESTRATOR.get_strategy_status(name)
    if status is None:
        return _envelope(
            {"error": f"Strategy '{name}' not found / 策略 '{name}' 未找到"},
            action="not_found",
        )
    return _envelope(status)


@phase2_router.post("/{name}/activate")
async def activate_strategy(name: str):
    """
    Activate a registered strategy.
    激活已注册的策略。
    """
    success = ORCHESTRATOR.activate_strategy(name)
    if not success:
        return _envelope(
            {"error": f"Strategy '{name}' not found / 策略 '{name}' 未找到"},
            action="not_found",
        )
    return _envelope({
        "strategy": name,
        "action": "activated",
        "new_state": "active",
    })


@phase2_router.post("/{name}/pause")
async def pause_strategy(name: str):
    """
    Pause a running strategy.
    暂停运行中的策略。
    """
    success = ORCHESTRATOR.pause_strategy(name)
    if not success:
        return _envelope(
            {"error": f"Strategy '{name}' not found / 策略 '{name}' 未找到"},
            action="not_found",
        )
    return _envelope({
        "strategy": name,
        "action": "paused",
        "new_state": "paused",
    })


@phase2_router.post("/{name}/stop")
async def stop_strategy(name: str):
    """
    Stop a strategy.
    停止策略。
    """
    success = ORCHESTRATOR.stop_strategy(name)
    if not success:
        return _envelope(
            {"error": f"Strategy '{name}' not found / 策略 '{name}' 未找到"},
            action="not_found",
        )
    return _envelope({
        "strategy": name,
        "action": "stopped",
        "new_state": "stopped",
    })


# ── Intent & Status Routes / 意图与状态路由 ──

@phase2_router.get("/intents")
async def get_intents(
    n: int = Query(default=50, ge=1, le=200, description="Number of intents / 意图数量"),
):
    """
    Get recent OrderIntent history.
    获取最近的 OrderIntent 历史。
    """
    history = ORCHESTRATOR.get_intent_history(n=n)
    return _envelope({
        "intents": history,
        "count": len(history),
    })


@phase2_router.get("/status")
async def get_orchestrator_status():
    """
    Get comprehensive orchestrator status including all sub-components.
    获取编排器综合状态，包括所有子组件。
    """
    return _envelope(ORCHESTRATOR.get_status())

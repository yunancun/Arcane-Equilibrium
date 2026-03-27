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

from fastapi import APIRouter, Depends, HTTPException, Query

from . import main_legacy as base  # Auth helpers (current_actor, AuthenticatedActor)

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
from local_model_tools.strategies.bb_breakout import BBBreakoutStrategy

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
_grid_upper = float(os.getenv("OPENCLAW_GRID_UPPER", "68000"))
_grid_lower = float(os.getenv("OPENCLAW_GRID_LOWER", "63000"))
_grid_count = int(os.getenv("OPENCLAW_GRID_COUNT", "25"))

ORCHESTRATOR.register_strategy(GridTradingStrategy(
    symbol="BTCUSDT", upper_price=_grid_upper, lower_price=_grid_lower, grid_count=_grid_count,
))
ORCHESTRATOR.register_strategy(BBBreakoutStrategy(symbol="BTCUSDT"))

logger.info(
    "Phase 2 strategy pipeline initialized / Phase 2 策略管线初始化完成: "
    "symbols=%s, timeframes=%s, strategies=%s",
    DEFAULT_SYMBOLS, DEFAULT_TIMEFRAMES, ORCHESTRATOR.list_available_strategies(),
)

# ── Pipeline Bridge (connects strategy pipeline to paper trading engine) ──
# 管线桥接器（连接策略管线与纸上交易引擎）
# Lazy initialization: bridge is created here but activated when paper session starts
# 延迟激活：桥接器在此创建，但在纸上交易 session 启动时激活

from .pipeline_bridge import PipelineBridge

# Import paper trading singletons (these are created in paper_trading_routes.py)
# 导入纸上交易单例（在 paper_trading_routes.py 中创建）
# Note: circular import is avoided because both files are imported at module level by main.py
# 注意：避免循环导入，因为两个文件都由 main.py 在模块级导入
try:
    from .paper_trading_routes import ENGINE as PAPER_ENGINE
    # StopManager with default 5% hard stop + 3% trailing + 48h time stop
    # 止损管理器：5% 硬止损 + 3% 追踪止损 + 48h 时间止损
    import sys as _sys
    _lmt_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    if _lmt_dir not in _sys.path:
        _sys.path.insert(0, _lmt_dir)
    from local_model_tools.stop_manager import StopManager, StopConfig
    STOP_MANAGER = StopManager(StopConfig(hard_stop_pct=5.0, trailing_stop_pct=3.0, time_stop_hours=48.0))

    PIPELINE_BRIDGE = PipelineBridge(
        kline_manager=KLINE_MANAGER,
        indicator_engine=INDICATOR_ENGINE,
        signal_engine=SIGNAL_ENGINE,
        orchestrator=ORCHESTRATOR,
        paper_engine=PAPER_ENGINE,
        stop_manager=STOP_MANAGER,
    )
    logger.info("Pipeline bridge created with StopManager (inactive until paper session starts) / 管线桥接器+止损管理器已创建")
except ImportError:
    PIPELINE_BRIDGE = None
    logger.warning("Could not import paper trading engine — pipeline bridge disabled / 无法导入纸上交易引擎 — 管线桥接器已禁用")


# ── AI Consultation (connects Layer 2 engine to strategy orchestrator) ──
# AI 咨询连接（将 Layer 2 引擎连接到策略编排器）
try:
    from .layer2_routes import _get_engine as _get_l2_engine
    ORCHESTRATOR.set_ai_engine(_get_l2_engine())
    logger.info("AI consultation connected to orchestrator / AI 咨询已连接编排器")
except (ImportError, Exception) as e:
    logger.info("AI consultation not available: %s / AI 咨询不可用: %s", e, e)

# ── Telegram Alerter (optional, enabled by env vars) ──
try:
    from .telegram_alerter import TelegramAlerter
    TELEGRAM = TelegramAlerter()
    if TELEGRAM.is_enabled and PIPELINE_BRIDGE is not None:
        PIPELINE_BRIDGE.set_telegram(TELEGRAM)
        logger.info("Telegram alerts wired to pipeline bridge / Telegram 告警已接入管线")
except ImportError:
    TELEGRAM = None

# ── Grafana Data Writer (writes trading data to PostgreSQL for dashboards) ──
# Grafana 数据写入器（将交易数据写入 PostgreSQL 供仪表盘使用）
try:
    from .grafana_data_writer import GrafanaDataWriter
    GRAFANA_WRITER = GrafanaDataWriter(
        paper_engine=PAPER_ENGINE,
        kline_manager=KLINE_MANAGER,
        signal_engine=SIGNAL_ENGINE,
        orchestrator=ORCHESTRATOR,
        pipeline_bridge=PIPELINE_BRIDGE,
    )
    GRAFANA_WRITER.start()
    logger.info("Grafana data writer started / Grafana 数据写入器已启动")
except Exception as e:
    GRAFANA_WRITER = None
    logger.info("Grafana data writer not available: %s / Grafana 写入器不可用: %s", e, e)

# ── Bybit Demo Connector (optional, for sandbox execution) ──
# Bybit Demo 连接器（可选，用于沙盒执行）
try:
    from .bybit_demo_connector import BybitDemoConnector
    DEMO_CONNECTOR = BybitDemoConnector()
    if DEMO_CONNECTOR.is_enabled and PIPELINE_BRIDGE is not None:
        PIPELINE_BRIDGE.set_demo_connector(DEMO_CONNECTOR)
        logger.info("Bybit Demo connector wired to pipeline bridge / Bybit Demo 已接入管线")
except Exception as e:
    DEMO_CONNECTOR = None
    logger.info("Bybit Demo connector not available: %s", e)

# ── Bybit Demo Data Sync (pulls Demo data into PostgreSQL) ──
# Bybit Demo 数据同步器（从 Demo API 拉取数据写入 PostgreSQL）
try:
    from .bybit_demo_sync import BybitDemoSync
    DEMO_SYNC = BybitDemoSync(demo_connector=DEMO_CONNECTOR)
    DEMO_SYNC.start()
    logger.info("Bybit Demo sync started / Demo 数据同步器已启动")
except Exception as e:
    DEMO_SYNC = None
    logger.info("Demo sync not available: %s", e)

# ── Market Scanner + Strategy Auto-Deployer (autonomous opportunity discovery) ──
# 市场扫描器 + 策略自动部署器（自主发现交易机会）
try:
    from local_model_tools.market_scanner import MarketScanner
    from local_model_tools.strategy_auto_deployer import StrategyAutoDeployer

    MARKET_SCANNER = MarketScanner(max_symbols=10)
    AUTO_DEPLOYER = StrategyAutoDeployer(
        orchestrator=ORCHESTRATOR,
        kline_manager=KLINE_MANAGER,
        paper_engine=PAPER_ENGINE,
        max_symbols=10,            # Agent can trade up to 10 symbols simultaneously
        risk_per_trade_pct=2.0,    # Risk 2% of balance per trade (more aggressive)
        min_qty_usdt=20.0,         # Minimum $20 per trade
        max_qty_pct=15.0,          # Max 15% of balance per single trade
    )
    MARKET_SCANNER.register_on_scan(AUTO_DEPLOYER.on_scan_results)
    MARKET_SCANNER.start()
    logger.info("Market scanner + auto-deployer started / 市场扫描器+自动部署器已启动")
except Exception as e:
    MARKET_SCANNER = None
    AUTO_DEPLOYER = None
    logger.warning("Market scanner not available: %s", e)


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


_STRATEGY_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_\-]{1,50}$")


def _validate_strategy_name(name: str) -> str | None:
    """Validate strategy name (1-50 alphanum/underscore/dash). Returns cleaned name or None."""
    if not _STRATEGY_NAME_PATTERN.match(name):
        return None
    return name


def _envelope(data: Any, action: str = "success") -> dict[str, Any]:
    """Response envelope for Phase 2 routes / Phase 2 路由的响应封装"""
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
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get latest N closed klines for a symbol + timeframe.
    获取指定交易对 + 时间框架的最近 N 根已闭合 K线。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="Invalid symbol (1-20 alphanumeric) / 无效交易对")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail=f"Invalid timeframe, valid: {sorted(_VALID_TIMEFRAMES)} / 无效时间框架")
    try:
        klines = KLINE_MANAGER.get_latest_klines(sym, timeframe, n=n)
        current = KLINE_MANAGER.get_current_bar(sym, timeframe)
        return _envelope({
            "symbol": sym,
            "timeframe": timeframe,
            "closed_klines": klines,
            "current_bar": current.to_dict() if current else None,
            "count": len(klines),
        })
    except Exception:
        logger.exception("Error in get_klines / get_klines 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Indicator Routes / 指标路由 ──

@phase2_router.get("/indicators/{symbol}/{timeframe}")
async def get_indicators(
    symbol: str,
    timeframe: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get latest cached indicator values for a symbol + timeframe.
    获取指定交易对 + 时间框架的最新缓存指标值。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="Invalid symbol / 无效交易对")
    if timeframe not in _VALID_TIMEFRAMES:
        raise HTTPException(status_code=400, detail="Invalid timeframe / 无效时间框架")
    try:
        indicators = INDICATOR_ENGINE.get_indicators(sym, timeframe)
        return _envelope({
            "symbol": sym,
            "timeframe": timeframe,
            "indicators": indicators,
            "indicator_count": len(indicators),
        })
    except Exception:
        logger.exception("Error in get_indicators / get_indicators 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Signal Routes / 信号路由 ──

@phase2_router.get("/signals")
async def get_signals(
    symbol: str = Query(default=None, description="Filter by symbol / 按交易对过滤"),
    n: int = Query(default=50, ge=1, le=200, description="Number of signals / 信号数量"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get recent trading signals.
    获取最近的交易信号。
    """
    filter_sym = None
    if symbol:
        filter_sym = _validate_symbol(symbol)
        if filter_sym is None:
            raise HTTPException(status_code=400, detail="Invalid symbol / 无效交易对")
    try:
        signals = SIGNAL_ENGINE.get_latest_signals(symbol=filter_sym, n=n)
        return _envelope({
            "signals": signals,
            "count": len(signals),
            "filter_symbol": filter_sym,
        })
    except Exception:
        logger.exception("Error in get_signals / get_signals 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.get("/signals/{symbol}/summary")
async def get_signal_summary(
    symbol: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get signal consensus summary for a symbol.
    获取指定交易对的信号共识摘要。
    """
    sym = _validate_symbol(symbol)
    if sym is None:
        raise HTTPException(status_code=400, detail="Invalid symbol / 无效交易对")
    try:
        summary = SIGNAL_ENGINE.get_signal_summary(sym)
        return _envelope(summary)
    except Exception:
        logger.exception("Error in get_signal_summary / get_signal_summary 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Strategy Management Routes / 策略管理路由 ──

@phase2_router.get("/list")
async def list_strategies(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    List all registered strategies and their states.
    列出所有注册的策略及其状态。
    """
    try:
        statuses = ORCHESTRATOR.get_all_strategies_status()
        return _envelope({
            "strategies": statuses,
            "count": len(statuses),
        })
    except Exception:
        logger.exception("Error in list_strategies / list_strategies 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.get("/{name}/status")
async def get_strategy_status(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get status of a specific strategy.
    获取指定策略的状态。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        status = ORCHESTRATOR.get_strategy_status(name)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope(status)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in get_strategy_status / get_strategy_status 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.post("/{name}/activate")
async def activate_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Activate a registered strategy.
    激活已注册的策略。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.activate_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope({
            "strategy": name,
            "action": "activated",
            "new_state": "active",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in activate_strategy / activate_strategy 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.post("/{name}/pause")
async def pause_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Pause a running strategy.
    暂停运行中的策略。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.pause_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope({
            "strategy": name,
            "action": "paused",
            "new_state": "paused",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in pause_strategy / pause_strategy 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.post("/{name}/stop")
async def stop_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Stop a strategy.
    停止策略。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.stop_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope({
            "strategy": name,
            "action": "stopped",
            "new_state": "stopped",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error in stop_strategy / stop_strategy 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Intent & Status Routes / 意图与状态路由 ──

@phase2_router.get("/intents")
async def get_intents(
    n: int = Query(default=50, ge=1, le=200, description="Number of intents / 意图数量"),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get recent OrderIntent history.
    获取最近的 OrderIntent 历史。
    """
    try:
        history = ORCHESTRATOR.get_intent_history(n=n)
        return _envelope({
            "intents": history,
            "count": len(history),
        })
    except Exception:
        logger.exception("Error in get_intents / get_intents 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.get("/status")
async def get_orchestrator_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get comprehensive orchestrator status including all sub-components.
    获取编排器综合状态，包括所有子组件。
    """
    try:
        return _envelope(ORCHESTRATOR.get_status())
    except Exception:
        logger.exception("Error in get_orchestrator_status / get_orchestrator_status 异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Telegram Status Route / Telegram 状态路由 ──

@phase2_router.get("/telegram/status")
async def get_telegram_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Telegram alerter status / 获取 Telegram 告警器状态"""
    if TELEGRAM is None:
        return _envelope({"enabled": False, "reason": "module not loaded"})
    return _envelope(TELEGRAM.get_stats())


# ── AI Consultation Route / AI 咨询路由 ──

@phase2_router.get("/ai/status")
async def get_ai_consultation_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get AI consultation availability status.
    获取 AI 咨询可用状态。
    """
    try:
        result = ORCHESTRATOR.request_ai_analysis("status_check")
        return _envelope({
            "ai_consultation_enabled": ORCHESTRATOR._ai_consultation_enabled,
            "analysis_result": result,
        })
    except Exception:
        logger.exception("AI status check error / AI 状态检查异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


# ── Bybit Demo Routes / Bybit Demo 路由 ──

@phase2_router.get("/demo/status")
async def get_demo_status(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo connector status / 获取 Bybit Demo 连接器状态"""
    if DEMO_CONNECTOR is None:
        return _envelope({"enabled": False})
    try:
        status = DEMO_CONNECTOR.get_status()
        return _envelope(status)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/demo/balance")
async def get_demo_balance(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo account balance / 获取 Bybit Demo 账户余额"""
    if DEMO_CONNECTOR is None or not DEMO_CONNECTOR.is_enabled:
        return _envelope({"enabled": False})
    try:
        result = DEMO_CONNECTOR.get_wallet_balance()
        return _envelope(result)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/demo/positions")
async def get_demo_positions(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get Bybit Demo open positions / 获取 Bybit Demo 持仓"""
    if DEMO_CONNECTOR is None or not DEMO_CONNECTOR.is_enabled:
        return _envelope({"enabled": False})
    try:
        result = DEMO_CONNECTOR.get_positions()
        return _envelope(result)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


# ── Market Scanner Routes / 市场扫描路由 ──

@phase2_router.get("/scanner/opportunities")
async def get_scanner_opportunities(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get latest market scan opportunities / 获取最新市场扫描机会"""
    if MARKET_SCANNER is None:
        return _envelope({"available": False})
    try:
        return _envelope({
            "opportunities": MARKET_SCANNER.get_latest_opportunities(),
            "stats": MARKET_SCANNER.get_stats(),
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")


@phase2_router.get("/scanner/deployed")
async def get_auto_deployed(actor: base.AuthenticatedActor = Depends(base.current_actor)):
    """Get auto-deployed strategies / 获取自动部署的策略"""
    if AUTO_DEPLOYER is None:
        return _envelope({"available": False})
    try:
        return _envelope({
            "deployed": AUTO_DEPLOYER.get_deployed(),
            "stats": AUTO_DEPLOYER.get_stats(),
        })
    except Exception:
        raise HTTPException(status_code=500, detail="Internal error")

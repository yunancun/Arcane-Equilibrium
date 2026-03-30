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

from fastapi import APIRouter, Body, Depends, HTTPException, Query

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

# Trade Attribution Engine / 交易归因引擎
from .trade_attribution import TradeAttributionEngine

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

# Initialize Trade Attribution Engine / 初始化交易归因引擎
# This engine decomposes completed trades into skill vs luck attribution factors
# 本引擎将完成的交易分解为技能vs运气的归因因子
TRADE_ATTRIBUTION = TradeAttributionEngine()
logger.info("TradeAttributionEngine initialized / 交易归因引擎已初始化")

# ── Scout Agent + Message Bus (T2.07: Plan A2 — ScoutAgent as OpenClaw local proxy) ──
# Scout 代理 + 消息总线（T2.07：方案 A2 — ScoutAgent 作为 OpenClaw 本地代理）
from .multi_agent_framework import ScoutAgent, MessageBus, ScoutConfig
MESSAGE_BUS = MessageBus()
SCOUT_AGENT = ScoutAgent(config=ScoutConfig(), message_bus=MESSAGE_BUS)
SCOUT_AGENT.start()
logger.info("ScoutAgent + MessageBus initialized (Plan A2) / Scout 代理 + 消息总线已初始化（方案 A2）")

# ── Batch 7: Conductor + StrategistAgent (5-Agent event loop) ──
# Batch 7：Conductor + StrategistAgent（5-Agent 事件循环）
from .multi_agent_framework import AgentRole, Conductor, AgentState as _AgentState
from .strategist_agent import StrategistAgent, StrategistConfig
from .ollama_client import OllamaClient

# Create Conductor with shared MessageBus / 创建 Conductor 并使用共享消息总线
CONDUCTOR = Conductor(message_bus=MESSAGE_BUS)

# Register Scout with Conductor / 向 Conductor 注册 Scout
CONDUCTOR.register_agent(AgentRole.SCOUT, resource_mode="local")
CONDUCTOR.set_agent_state(AgentRole.SCOUT, _AgentState.RUNNING)

# Create OllamaClient for Strategist AI evaluation / 为 Strategist 创建 OllamaClient
OLLAMA_CLIENT: Any = None
try:
    OLLAMA_CLIENT = OllamaClient()
    _ollama_ok = OLLAMA_CLIENT.is_available(force_check=True)
    logger.info("OllamaClient for Strategist: available=%s / Strategist 用 OllamaClient: 可用=%s", _ollama_ok, _ollama_ok)
except Exception as _oc_e:
    logger.warning("OllamaClient init failed: %s / OllamaClient 初始化失败: %s", _oc_e, _oc_e)

# Create StrategistAgent (shadow=True by default — log only, no live intents)
# 创建 StrategistAgent（默认 shadow=True — 仅记录，不产生实际 intent）
STRATEGIST_AGENT = StrategistAgent(
    config=StrategistConfig(shadow=True),
    message_bus=MESSAGE_BUS,
    ollama_client=OLLAMA_CLIENT,
)
STRATEGIST_AGENT.start()

# Register Strategist with Conductor / 向 Conductor 注册 Strategist
CONDUCTOR.register_agent(AgentRole.STRATEGIST, resource_mode="local")
CONDUCTOR.set_agent_state(AgentRole.STRATEGIST, _AgentState.RUNNING)

# Subscribe Strategist to MessageBus (receives messages sent to STRATEGIST role)
# 订阅 Strategist 到消息总线（接收发送给 STRATEGIST 角色的消息）
MESSAGE_BUS.subscribe(AgentRole.STRATEGIST, STRATEGIST_AGENT.on_message)

logger.info(
    "Batch 7: Conductor + StrategistAgent initialized (shadow=%s) / "
    "Batch 7：Conductor + StrategistAgent 已初始化 (shadow=%s)",
    STRATEGIST_AGENT.config.shadow, STRATEGIST_AGENT.config.shadow,
)

# ── Batch 8: GuardianAgent — risk review for every TradeIntent (fail-closed) ──
# Batch 8：GuardianAgent — 审查每个 TradeIntent 的风控守卫（失败时拒绝）
from .guardian_agent import GuardianAgent, GuardianConfig

# GovernanceHub reference for SM-04 risk escalation (may be None at this point, injected later)
# GovernanceHub 引用用于 SM-04 风控升级（此时可能为 None，后续注入）
_GOV_HUB_FOR_GUARDIAN: Any = None
try:
    from .paper_trading_routes import GOV_HUB as _GOV_HUB_FOR_GUARDIAN
except ImportError:
    pass

# RiskManager reference for drawdown checks / RiskManager 引用用于回撤检查
_RISK_MGR_FOR_GUARDIAN: Any = None
try:
    from .paper_trading_routes import ENGINE as _PE_REF
    if _PE_REF and hasattr(_PE_REF, '_risk_manager'):
        _RISK_MGR_FOR_GUARDIAN = _PE_REF._risk_manager
except (ImportError, AttributeError):
    pass

GUARDIAN_AGENT = GuardianAgent(
    config=GuardianConfig(),
    message_bus=MESSAGE_BUS,
    risk_manager=_RISK_MGR_FOR_GUARDIAN,
    ollama_client=OLLAMA_CLIENT,
    governance_hub=_GOV_HUB_FOR_GUARDIAN,
)
GUARDIAN_AGENT.start()

# Register Guardian with Conductor / 向 Conductor 注册 Guardian
CONDUCTOR.register_agent(AgentRole.GUARDIAN, resource_mode="local")
CONDUCTOR.set_agent_state(AgentRole.GUARDIAN, _AgentState.RUNNING)

# Subscribe Guardian to MessageBus — receives TRADE_INTENT and EVENT_ALERT
# 订阅 Guardian 到消息总线 — 接收 TRADE_INTENT 和 EVENT_ALERT
MESSAGE_BUS.subscribe(AgentRole.GUARDIAN, GUARDIAN_AGENT.on_message)

logger.info(
    "Batch 8: GuardianAgent initialized (fail-closed, SM-04 linked=%s) / "
    "Batch 8：GuardianAgent 已初始化 (fail-closed, SM-04 关联=%s)",
    _GOV_HUB_FOR_GUARDIAN is not None, _GOV_HUB_FOR_GUARDIAN is not None,
)

# ── Batch 9: AnalystAgent — trade result analysis + LearningTierGate metrics ──
# Batch 9：AnalystAgent — 交易结果分析 + 学习等级门控指标更新
from .analyst_agent import AnalystAgent, AnalystConfig

# LearningTierGate reference for metrics update / LearningTierGate 引用用于指标更新
_LTG_FOR_ANALYST: Any = None
try:
    from .paper_trading_routes import LEARNING_TIER_GATE as _LTG_FOR_ANALYST
except ImportError:
    pass

ANALYST_AGENT = AnalystAgent(
    config=AnalystConfig(),
    message_bus=MESSAGE_BUS,
    ollama_client=OLLAMA_CLIENT,
    learning_tier_gate=_LTG_FOR_ANALYST,
)
ANALYST_AGENT.start()

# Register Analyst with Conductor / 向 Conductor 注册 Analyst
CONDUCTOR.register_agent(AgentRole.ANALYST, resource_mode="local")
CONDUCTOR.set_agent_state(AgentRole.ANALYST, _AgentState.RUNNING)

# Subscribe Analyst to MessageBus — receives ROUND_TRIP_COMPLETE
# 订阅 Analyst 到消息总线 — 接收 ROUND_TRIP_COMPLETE
MESSAGE_BUS.subscribe(AgentRole.ANALYST, ANALYST_AGENT.on_message)

logger.info(
    "Batch 9: AnalystAgent initialized (LearningTierGate linked=%s) / "
    "Batch 9：AnalystAgent 已初始化 (LearningTierGate 关联=%s)",
    _LTG_FOR_ANALYST is not None, _LTG_FOR_ANALYST is not None,
)

# ── Bybit Demo Connector (created early to read balance for position sizing) ──
# 提前创建 Demo 连接器，用于读取账户余额计算仓位大小
try:
    from .bybit_demo_connector import BybitDemoConnector
    DEMO_CONNECTOR: Any = BybitDemoConnector()
    if DEMO_CONNECTOR.is_enabled:
        _bal_result = DEMO_CONNECTOR.get_wallet_balance()
        _equity_str = (
            _bal_result.get("result", {}).get("list", [{}])[0].get("totalEquity", "")
        )
        _ACCOUNT_BALANCE_USDT = float(_equity_str) if _equity_str else 10000.0
        logger.info(
            "Demo balance read for sizing: $%.0f / 已读取 Demo 余额用于仓位计算",
            _ACCOUNT_BALANCE_USDT,
        )
    else:
        _ACCOUNT_BALANCE_USDT = 10000.0
        logger.info("Demo connector disabled, using paper balance $%.0f for sizing", _ACCOUNT_BALANCE_USDT)
except Exception as _e:
    DEMO_CONNECTOR = None
    _ACCOUNT_BALANCE_USDT = 10000.0
    logger.info("Demo connector unavailable (%s), using default balance for sizing", _e)

# ── Compute initial qty for pre-registered strategies based on account balance ──
# 根据账户余额计算预注册策略的初始仓位大小
# Logic: 2% risk / 5 strategies, min $20, max 15% of balance
# 逻辑：2% 风险 / 5 个策略，最小 $20，最大 15%
_N_DEFAULT_STRATEGIES = 5
_per_strategy_usdt = (_ACCOUNT_BALANCE_USDT * 2.0 / 100.0) / _N_DEFAULT_STRATEGIES
_per_strategy_usdt = max(20.0, min(_per_strategy_usdt, _ACCOUNT_BALANCE_USDT * 0.15))
_BTC_PRICE_HINT = float(os.getenv("OPENCLAW_BTC_PRICE_HINT", "67000"))
_DEFAULT_BTC_QTY = round(_per_strategy_usdt / _BTC_PRICE_HINT, 3)  # 3dp = Bybit BTCUSDT step precision
logger.info(
    "Default strategy qty: $%.0f/trade → %.6f BTC (balance=$%.0f) / 默认策略仓位",
    _per_strategy_usdt, _DEFAULT_BTC_QTY, _ACCOUNT_BALANCE_USDT,
)

# Pre-register default strategies (idle by default, user activates via API)
# 预注册默认策略（默认 idle，用户通过 API 激活）
ORCHESTRATOR.register_strategy(MACrossoverStrategy(symbol="BTCUSDT", qty_per_trade=_DEFAULT_BTC_QTY, min_confidence=0.5))
ORCHESTRATOR.register_strategy(BollingerReversionStrategy(symbol="BTCUSDT", qty_per_trade=_DEFAULT_BTC_QTY))
ORCHESTRATOR.register_strategy(FundingRateArbStrategy(symbol="BTCUSDT", qty_per_trade=_DEFAULT_BTC_QTY))
_grid_upper = float(os.getenv("OPENCLAW_GRID_UPPER", "68000"))
_grid_lower = float(os.getenv("OPENCLAW_GRID_LOWER", "63000"))
_grid_count = int(os.getenv("OPENCLAW_GRID_COUNT", "25"))

ORCHESTRATOR.register_strategy(GridTradingStrategy(
    symbol="BTCUSDT", upper_price=_grid_upper, lower_price=_grid_lower,
    grid_count=_grid_count, qty_per_grid=_DEFAULT_BTC_QTY,
))
ORCHESTRATOR.register_strategy(BBBreakoutStrategy(symbol="BTCUSDT", qty_per_trade=_DEFAULT_BTC_QTY))

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
    # StopManager with default 5% hard stop + 5% trailing + 48h time stop
    # 止损管理器：5% 硬止损 + 5% 追踪止损 + 48h 时间止损
    # B6: trailing_stop_pct widened from 3.0→5.0 to avoid noise-triggered stops in crypto
    # B6：追踪止损从 3.0% 加宽至 5.0%，避免加密货币正常波动触发止损
    import sys as _sys
    _lmt_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
    if _lmt_dir not in _sys.path:
        _sys.path.insert(0, _lmt_dir)
    from local_model_tools.stop_manager import StopManager, StopConfig
    STOP_MANAGER = StopManager(StopConfig(hard_stop_pct=5.0, trailing_stop_pct=5.0, time_stop_hours=48.0))

    PIPELINE_BRIDGE = PipelineBridge(
        kline_manager=KLINE_MANAGER,
        indicator_engine=INDICATOR_ENGINE,
        signal_engine=SIGNAL_ENGINE,
        orchestrator=ORCHESTRATOR,
        paper_engine=PAPER_ENGINE,
        stop_manager=STOP_MANAGER,
    )
    logger.info("Pipeline bridge created with StopManager (inactive until paper session starts) / 管线桥接器+止损管理器已创建")

    # --- Governance Hub injection (T1.01) ---
    # 治理集线器注入到管线桥接器 (T1.01)
    try:
        from .paper_trading_routes import GOV_HUB as _GOV_HUB_REF
        if _GOV_HUB_REF is not None:
            PIPELINE_BRIDGE.set_governance_hub(_GOV_HUB_REF)
            logger.info("GovernanceHub injected into PipelineBridge / 治理集线器已注入管线桥接器")
        else:
            logger.warning("GOV_HUB is None — PipelineBridge running without governance / GOV_HUB 为 None — 管线桥接器运行不包含治理")
    except ImportError as e:
        logger.warning("Could not import GOV_HUB for PipelineBridge: %s / 无法为管线桥接器导入 GOV_HUB: %s", e, e)

    # --- T2.02: PerceptionPlane injection (Cognitive Honesty) ---
    # T2.02：感知平面注入（认知诚实检查）
    try:
        from .paper_trading_routes import PERCEPTION_PLANE as _PERCEPTION_PLANE_REF
        if _PERCEPTION_PLANE_REF is not None:
            PIPELINE_BRIDGE.set_perception_plane(_PERCEPTION_PLANE_REF)
            logger.info("PerceptionPlane injected into PipelineBridge / 感知平面已注入管线桥接器")
        else:
            logger.warning("PERCEPTION_PLANE is None — skipping cognitive honesty checks / 感知平面为 None — 跳过认知诚实检查")
    except ImportError as e:
        logger.warning("Could not import PERCEPTION_PLANE for PipelineBridge: %s", e)

    # --- T3.05: ScannerRateLimiter injection ---
    try:
        from .paper_trading_routes import SCANNER_RATE_LIMITER as _SCANNER_RATE_LIMITER_REF
        if PIPELINE_BRIDGE is not None and _SCANNER_RATE_LIMITER_REF is not None:
            PIPELINE_BRIDGE.set_scanner_rate_limiter(_SCANNER_RATE_LIMITER_REF)
            logger.info("ScannerRateLimiter injected into PipelineBridge / 掃描限速器已注入管線橋接器")
    except ImportError as e:
        logger.warning("Could not import SCANNER_RATE_LIMITER: %s", e)

    # --- L1.01: TradeAttributionEngine injection ---
    # L1.01：交易归因引擎注入到管线桥接器
    # This enables attribution of completed trades into skill vs luck factors (ALPHA/TIMING/SIZING/EXECUTION/COST/LUCK)
    # 使已完成的交易能够分解为技能vs运气因子
    try:
        if PIPELINE_BRIDGE is not None and TRADE_ATTRIBUTION is not None:
            PIPELINE_BRIDGE.set_trade_attribution(TRADE_ATTRIBUTION)
            logger.info("TradeAttributionEngine injected into PipelineBridge / 交易归因引擎已注入管线桥接器")
        else:
            logger.warning("TRADE_ATTRIBUTION or PIPELINE_BRIDGE is None — skipping attribution / 归因引擎或管线桥接器为 None — 跳过交易归因")
    except Exception as e:
        logger.warning("Could not inject TradeAttributionEngine: %s", e)

    # --- T2.07: ScoutAgent + MessageBus injection (Plan A2) ---
    # T2.07：Scout 代理 + 消息总线注入管線桥接器（方案 A2）
    try:
        if PIPELINE_BRIDGE is not None:
            PIPELINE_BRIDGE.set_scout_agent(SCOUT_AGENT)
            PIPELINE_BRIDGE.set_message_bus(MESSAGE_BUS)
            logger.info("ScoutAgent + MessageBus injected into PipelineBridge / Scout 代理 + 消息总线已注入管线桥接器")
    except Exception as e:
        logger.warning("Could not inject ScoutAgent/MessageBus: %s", e)

    # --- Batch 7: StrategistAgent + OllamaClient injection into PipelineBridge ---
    # Batch 7：StrategistAgent + OllamaClient 注入管线桥接器
    try:
        if PIPELINE_BRIDGE is not None:
            PIPELINE_BRIDGE.set_strategist_agent(STRATEGIST_AGENT)
            logger.info("StrategistAgent injected into PipelineBridge / StrategistAgent 已注入管线桥接器")
    except Exception as e:
        logger.warning("Could not inject StrategistAgent: %s", e)

    # --- Batch 8: GuardianAgent injection into PipelineBridge ---
    # Batch 8：GuardianAgent 注入管线桥接器（主门控 fail-closed）
    try:
        if PIPELINE_BRIDGE is not None:
            PIPELINE_BRIDGE.set_guardian_agent(GUARDIAN_AGENT)
            logger.info("GuardianAgent injected into PipelineBridge (primary gate) / GuardianAgent 已注入管线桥接器（主门控）")
    except Exception as e:
        logger.warning("Could not inject GuardianAgent: %s", e)

    # --- Batch 9: AnalystAgent injection into PipelineBridge ---
    # Batch 9：AnalystAgent 注入管线桥接器（交易结果分析 + 指标更新）
    try:
        if PIPELINE_BRIDGE is not None:
            PIPELINE_BRIDGE.set_analyst_agent(ANALYST_AGENT)
            logger.info("AnalystAgent injected into PipelineBridge / AnalystAgent 已注入管线桥接器")
    except Exception as e:
        logger.warning("Could not inject AnalystAgent: %s", e)

    # --- EX-05: LearningTierGate injection into PipelineBridge ---
    # EX-05：学习等级门控注入管线桥接器，以支持 L1→L2→L3... 自动晋升
    try:
        from .paper_trading_routes import LEARNING_TIER_GATE as _LTG_REF
        if PIPELINE_BRIDGE is not None and _LTG_REF is not None:
            PIPELINE_BRIDGE.set_learning_tier_gate(_LTG_REF)
            logger.info("LearningTierGate injected into PipelineBridge / 学习等级门控已注入管線桥接器")
        else:
            if _LTG_REF is None:
                logger.warning("LEARNING_TIER_GATE is None — auto-promotion disabled / 学习等级门控为 None — 自动晋升已禁用")
    except (ImportError, Exception) as e:
        logger.warning("Could not inject LearningTierGate into PipelineBridge: %s", e)

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

# ── Wire Demo Connector to Pipeline Bridge (DEMO_CONNECTOR created earlier) ──
# 将已提前创建的 Demo 连接器接入管线桥接器
if DEMO_CONNECTOR is not None and DEMO_CONNECTOR.is_enabled and PIPELINE_BRIDGE is not None:
    PIPELINE_BRIDGE.set_demo_connector(DEMO_CONNECTOR)
    logger.info("Bybit Demo connector wired to pipeline bridge / Bybit Demo 已接入管线")

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

    # Lazy dispatcher reference: resolves at call time so it works even if
    # market feed starts after the auto-deployer is created.
    # 惰性 dispatcher 引用：调用时才解析，无论行情流何时启动均有效。
    from . import paper_trading_routes as _ptr

    MARKET_SCANNER = MarketScanner(max_symbols=10)
    AUTO_DEPLOYER = StrategyAutoDeployer(
        orchestrator=ORCHESTRATOR,
        kline_manager=KLINE_MANAGER,
        paper_engine=PAPER_ENGINE,
        max_symbols=10,            # Agent can trade up to 10 symbols simultaneously
        risk_per_trade_pct=2.0,    # Risk 2% of balance per trade (more aggressive)
        min_qty_usdt=20.0,         # Minimum $20 per trade
        max_qty_pct=15.0,          # Max 15% of balance per single trade
        market_feed_add_fn=lambda sym: _ptr.DISPATCHER.add_symbol(sym) if _ptr.DISPATCHER else None,
    )
    MARKET_SCANNER.register_on_scan(AUTO_DEPLOYER.on_scan_results)
    MARKET_SCANNER.start()

    # G1: wire auto-deployer into pipeline bridge for consecutive-loss auto-exit
    # G1：将自动部署器接入管线桥接器，实现连续亏损自动退出
    if PIPELINE_BRIDGE is not None:
        PIPELINE_BRIDGE.set_auto_deployer(AUTO_DEPLOYER)
        logger.info("Auto-deployer wired to pipeline bridge for loss tracking / 自动部署器已接入管线桥接器")

    logger.info("Market scanner + auto-deployer started / 市场扫描器+自动部署器已启动")
except Exception as e:
    MARKET_SCANNER = None
    AUTO_DEPLOYER = None
    logger.warning("Market scanner not available: %s", e)

# --- Wire ScoutAgent + MessageBus into scout_routes ---
try:
    from . import scout_routes
    scout_routes.set_scout_agent(SCOUT_AGENT)
    scout_routes.set_message_bus(MESSAGE_BUS)
    # Batch 9: Wire PerceptionPlane into scout_routes for cognitive level marking
    # Batch 9：将感知平面接入 scout 路由用于认知级别标记
    try:
        from .paper_trading_routes import PERCEPTION_PLANE as _PP_FOR_SCOUT
        if _PP_FOR_SCOUT is not None:
            scout_routes.set_perception_plane(_PP_FOR_SCOUT)
    except ImportError:
        pass
    logger.info("ScoutAgent + MessageBus (+ PerceptionPlane) wired to scout_routes / Scout 代理 + 消息总线（+ 感知平面）已接入 scout 路由")
except Exception as e:
    logger.warning("Could not wire scout_routes: %s", e)


# ── E1: Auto-Observation Writer (writes observations after each round-trip trade) ──
# E1：自动观察写入器（每轮交易结束后写入观察）
try:
    import time as _time_mod
    from . import main_legacy as _ml

    def _write_auto_observation(
        symbol: str,
        strategy_name: str,
        close_pnl: float,
        hold_ms: int,
        regime: str,
    ) -> None:
        """Write a trading observation to the learning state after each round-trip."""
        try:
            outcome = "win" if close_pnl > 0 else ("loss" if close_pnl < 0 else "breakeven")
            hold_h = hold_ms / 3_600_000
            obs_text = (
                f"[Auto] {strategy_name} on {symbol}: {outcome} "
                f"PnL={close_pnl:+.4f} USDT, hold={hold_h:.2f}h, regime={regime}"
            )

            def mutator(state):
                import uuid
                ts = int(_time_mod.time() * 1000)
                record = {
                    "observation_id": f"auto:{uuid.uuid4().hex[:12]}",
                    "observation_ts_ms": ts,
                    "observation_type": "trade_outcome",
                    "confidence_level": "fact",
                    "title": f"Trade: {strategy_name}/{symbol} → {outcome}",
                    "detail": obs_text,
                    "related_hypothesis_id": None,
                    "tags": ["auto", "trade", strategy_name, symbol, outcome, regime],
                }
                ls = state.setdefault("learning_state", {})
                ls.setdefault("observation_summary", {}).setdefault("last_observation_ts_ms", None)
                ls["observation_summary"]["last_observation_ts_ms"] = ts
                ls.setdefault("records", {}).setdefault("observations", []).append(record)
                return state

            _ml.STORE.mutate(mutator)
        except Exception:
            pass  # non-fatal, best-effort

    if PIPELINE_BRIDGE is not None:
        PIPELINE_BRIDGE.set_observation_writer(_write_auto_observation)
        logger.info("Auto-observation writer wired to pipeline bridge / 自动观察写入器已接入管线桥接器")
except Exception as _e1_e:
    logger.info("Auto-observation writer not wired: %s", _e1_e)


# ── Auto-start market feed if a paper session is already active ──
# 若纸上交易 session 已存在（服务重启场景），自动重启行情数据流
# This prevents the "frozen system" state after systemctl restart.
# 防止 systemctl restart 后系统进入"活死人"状态（策略激活但无数据）。
try:
    from . import paper_trading_routes as _paper_ptr
    from .paper_trading_routes import MarketDataDispatcher

    if (
        _paper_ptr.DISPATCHER is None          # feed not yet running
        and PIPELINE_BRIDGE is not None        # pipeline ready
        and _paper_ptr.PAPER_STORE is not None  # store available
    ):
        _sess_state = _paper_ptr.PAPER_STORE.read().get("session", {}).get("session_state", "")
        if _sess_state in ("active", "paused"):
            _auto_symbols = ["BTCUSDT", "ETHUSDT"]
            _paper_ptr.DISPATCHER = MarketDataDispatcher(
                engine=_paper_ptr.ENGINE,
                symbols=_auto_symbols,
            )
            _paper_ptr.DISPATCHER.start()
            _paper_ptr.DISPATCHER.register_tick_consumer(PIPELINE_BRIDGE)
            PIPELINE_BRIDGE.activate()
            logger.info(
                "Auto-started market feed (session_state=%s) / 自动启动行情流（session_state=%s）",
                _sess_state, _sess_state,
            )
        else:
            logger.info(
                "No active paper session at startup (state=%r), skipping auto market feed / "
                "启动时无活跃 session，跳过自动启动行情流",
                _sess_state,
            )
except Exception as _auto_e:
    logger.info("Auto market feed start skipped: %s / 自动启动行情流已跳过: %s", _auto_e, _auto_e)


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


# ── Strategy Create & Delete Routes / 策略创建与删除路由 ──

@phase2_router.post("/create")
async def create_strategy(
    request: dict[str, Any] = Body(...),
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Create and register a new strategy instance.
    创建并注册新策略实例。AI Agent 或用户均可调用。

    Body JSON:
      strategy_type: str — one of: ma_crossover, bb_reversion, funding_arb, grid, bb_breakout
      symbol: str — trading pair (e.g. BTCUSDT)
      qty_per_trade: float — quantity per trade (optional, default 0.001)
      params: dict — additional strategy-specific params (optional)
    """
    from program_code.local_model_tools.strategies.ma_crossover import MACrossoverStrategy
    from program_code.local_model_tools.strategies.bollinger_reversion import BollingerReversionStrategy
    from program_code.local_model_tools.strategies.funding_rate_arb import FundingRateArbStrategy
    from program_code.local_model_tools.strategies.grid_trading import GridTradingStrategy
    from program_code.local_model_tools.strategies.bb_breakout import BBBreakoutStrategy

    stype = request.get("strategy_type", "").lower()
    symbol = request.get("symbol", "").upper()
    qty = request.get("qty_per_trade", 0.001)
    params = request.get("params", {})

    if not stype or not symbol:
        raise HTTPException(status_code=400, detail="strategy_type and symbol required / 需要 strategy_type 和 symbol")

    strategy = None
    try:
        if stype in ("ma_crossover", "trend"):
            strategy = MACrossoverStrategy(symbol=symbol, qty_per_trade=qty)
        elif stype in ("bb_reversion", "reversion"):
            strategy = BollingerReversionStrategy(symbol=symbol, qty_per_trade=qty)
        elif stype in ("funding_arb", "funding_rate_arb"):
            strategy = FundingRateArbStrategy(symbol=symbol, qty_per_trade=qty)
        elif stype in ("grid", "grid_trading"):
            upper = params.get("upper_price", 0)
            lower = params.get("lower_price", 0)
            grid_count = params.get("grid_count", 20)
            if not upper or not lower:
                raise HTTPException(status_code=400, detail="Grid strategy requires upper_price and lower_price in params / 网格策略需要 upper_price 和 lower_price")
            strategy = GridTradingStrategy(symbol=symbol, upper_price=upper, lower_price=lower,
                                          grid_count=grid_count, qty_per_grid=qty)
        elif stype in ("bb_breakout", "breakout"):
            strategy = BBBreakoutStrategy(symbol=symbol, qty_per_trade=qty)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown strategy_type: {stype} / 未知策略类型: {stype}")

        unique_name = f"{strategy.name}_{symbol}"
        ORCHESTRATOR.register_strategy(strategy, name=unique_name)

        # Add symbol to kline manager if new
        if KLINE_MANAGER and symbol not in KLINE_MANAGER.get_tracked_symbols():
            KLINE_MANAGER.add_symbol(symbol)

        return _envelope({
            "strategy": unique_name,
            "action": "created",
            "state": "idle",
            "symbol": symbol,
            "strategy_type": stype,
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating strategy / 创建策略异常")
        raise HTTPException(status_code=500, detail="Internal error / 内部错误")


@phase2_router.delete("/{name}")
async def delete_strategy(
    name: str,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Delete (remove) a strategy completely. Cannot be reactivated.
    完全删除策略（不可恢复）。与 stop 不同，delete 从注册表中移除。
    """
    if _validate_strategy_name(name) is None:
        raise HTTPException(status_code=400, detail="Invalid strategy name / 无效策略名称")
    try:
        success = ORCHESTRATOR.remove_strategy(name)
        if not success:
            raise HTTPException(status_code=404, detail=f"Strategy '{name}' not found / 策略 '{name}' 未找到")
        return _envelope({
            "strategy": name,
            "action": "deleted",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting strategy / 删除策略异常")
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
        # Bybit V5 requires symbol or settleCoin — use settleCoin=USDT for all linear positions
        params: dict[str, Any] = {"category": "linear", "settleCoin": "USDT"}
        result = DEMO_CONNECTOR._request("GET", "/v5/position/list", params)
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

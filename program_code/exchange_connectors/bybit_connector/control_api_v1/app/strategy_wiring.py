from __future__ import annotations

"""
Strategy Wiring -- module-level singletons and dependency injection
(Split from phase2_strategy_routes.py, TD-02)

MODULE_NOTE (中文):
  本模块包含 Phase 2 本地策略工具包的模块级单例创建与依赖注入接线。
  从 phase2_strategy_routes.py 拆分而来，使路由文件保持精简。

  内容清单：
  - 共享实例（KlineManager / IndicatorEngine / SignalEngine / Orchestrator）
  - 交易归因引擎（TradeAttributionEngine）
  - ScoutAgent + MessageBus + Conductor
  - OllamaClient + StrategistAgent + GuardianAgent + AnalystAgent + ExecutorAgent
  - Demo Connector + 仓位计算
  - 策略预注册
  - PipelineBridge 创建 + 所有 DI 接线
  - PaperLiveGate
  - AI Consultation / Telegram / Grafana / DemoSync
  - MarketScanner + AutoDeployer + ScoutWorker
  - Scout routes 接线 / E1 自动观察写入器
  - 后台行情流自动启动
  - H0Gate / TruthSourceRegistry 注入
  - Router 创建
  - 输入验证辅助函数

MODULE_NOTE (English):
  Contains module-level singleton creation and dependency injection wiring
  for the Phase 2 local strategy toolkit. Split from phase2_strategy_routes.py
  to keep the route file concise.

  Contents:
  - Shared instances (KlineManager / IndicatorEngine / SignalEngine / Orchestrator)
  - Trade Attribution Engine
  - ScoutAgent + MessageBus + Conductor
  - OllamaClient + StrategistAgent + GuardianAgent + AnalystAgent + ExecutorAgent
  - Demo Connector + position sizing
  - Strategy pre-registration
  - PipelineBridge creation + all DI wiring
  - PaperLiveGate
  - AI Consultation / Telegram / Grafana / DemoSync
  - MarketScanner + AutoDeployer + ScoutWorker
  - Scout routes wiring / E1 Auto-Observation Writer
  - Auto-start market feed
  - H0Gate / TruthSourceRegistry injection
  - Router creation
  - Input validation helpers

安全不变量 / Safety invariant:
  - system_mode = read_only 不变 / system_mode remains read_only
  - 所有策略仅产生 OrderIntent，不直接执行交易 / All strategies only generate OrderIntents
  - 所有数据标记 is_simulated=True / All data marked is_simulated=True
"""

import logging
import re
import os
from typing import Any

from fastapi import APIRouter

# ── sys.path 注入（統一由 _path_setup 模塊處理）──────────────────────────────────
# sys.path injection — centralized in _path_setup.py (APR01-MEDIUM-11 dedup)
from . import _path_setup  # noqa: F401  — ensures program_code/ is on sys.path

from local_model_tools.kline_manager import KlineManager
from local_model_tools.indicator_engine import IndicatorEngine
from local_model_tools.signal_generator import SignalEngine
from local_model_tools.strategy_orchestrator import StrategyOrchestrator
# DEAD-PY-2: Python strategy classes deleted — Rust openclaw_engine is sole strategy executor.
# Python 策略類已刪除 — Rust openclaw_engine 為唯一策略執行器。

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

# ── E5-FN-3-FUP-d: Scout audit_callback wiring ──
# Wires ScoutAgent._audit(...) calls into GOV_HUB._change_audit_log via
# agent_audit_bridge. Satisfies Root Principle #8 "Trade Explainability" by
# ensuring every Scout intel_produced / event_alert_produced call-site produces
# an append-only audit record (Scout is the 5-Agent framework's eyes-and-ears,
# its outputs feed Strategist/Guardian decisions — auditing them completes the
# decision-trail chain).
# Fail-open: GOV_HUB unavailable → bridge silently drops events; Scout's main
# intel/alert path is never disrupted.
# Local import of make_agent_audit_callback: the canonical import lives later
# in the AnalystAgent block (line ~258) — duplicated here to keep Scout's
# wiring self-contained without reordering the Batch 7/8/9 existing imports.
# 將 ScoutAgent._audit(...) 透過 agent_audit_bridge 接到 GOV_HUB._change_audit_log；
# 落實根原則 #8「交易可解釋」。Scout 是 5-Agent 體系的「眼耳」，其 intel/alert
# 輸出會餵給 Strategist/Guardian 決策，審計 Scout 才能完整還原決策鏈。
# fail-open：GOV_HUB 不可用時 bridge 靜默丟棄，不阻塞 Scout。
# 此處本地重複 import make_agent_audit_callback 以保持 Scout 接線自包含，
# 不重排位於 AnalystAgent 區塊的既有 import（約第 258 行）。
from .agent_audit_bridge import make_agent_audit_callback as _make_scout_audit_cb

_GOV_HUB_FOR_SCOUT: Any = None
try:
    from .paper_trading_routes import GOV_HUB as _GOV_HUB_FOR_SCOUT
except ImportError:
    pass

_SCOUT_AUDIT_CB = _make_scout_audit_cb(_GOV_HUB_FOR_SCOUT, "ScoutAgent")

SCOUT_AGENT = ScoutAgent(
    config=ScoutConfig(),
    message_bus=MESSAGE_BUS,
    audit_callback=_SCOUT_AUDIT_CB,
)
SCOUT_AGENT.start()
logger.info("ScoutAgent + MessageBus initialized (Plan A2) / Scout 代理 + 消息总线已初始化（方案 A2）")

# ── Batch 7: Conductor + StrategistAgent (5-Agent event loop) ──
# Batch 7：Conductor + StrategistAgent（5-Agent 事件循环）
from .multi_agent_framework import AgentRole, Conductor, AgentState as _AgentState
from .strategist_agent import StrategistAgent, StrategistConfig
from .local_llm_factory import get_local_llm_client

# Layer2CostTracker for H1/H5 budget gate injection into StrategistAgent
# Layer2CostTracker 用於 H1/H5 預算門控注入到 StrategistAgent
_COST_TRACKER_FOR_STRATEGIST: Any = None
try:
    from .layer2_cost_tracker import Layer2CostTracker
    _COST_TRACKER_FOR_STRATEGIST = Layer2CostTracker()
    logger.info(
        "Layer2CostTracker for StrategistAgent initialized / "
        "StrategistAgent 用 Layer2CostTracker 已初始化"
    )
except Exception as _ct_e:
    logger.warning(
        "Layer2CostTracker init failed, StrategistAgent will run without budget gate: %s / "
        "Layer2CostTracker 初始化失敗，StrategistAgent 將無預算門控運行: %s",
        _ct_e, _ct_e,
    )

# Create Conductor with shared MessageBus / 创建 Conductor 并使用共享消息总线
CONDUCTOR = Conductor(message_bus=MESSAGE_BUS)

# Register Scout with Conductor / 向 Conductor 注册 Scout
CONDUCTOR.register_agent(AgentRole.SCOUT, resource_mode="local")
CONDUCTOR.set_agent_state(AgentRole.SCOUT, _AgentState.RUNNING)

# Create local LLM client for Strategist AI evaluation / 为 Strategist 创建本地 LLM 客戶端
# LLM-ABC-MIGRATION-1: routed via local_llm_factory (LOCAL_LLM_PROVIDER env switches
# between Ollama / LM Studio). Variable name `OLLAMA_CLIENT` kept for §九 grep-stability.
# LLM-ABC-MIGRATION-1：經 local_llm_factory（LOCAL_LLM_PROVIDER 切 Ollama/LM Studio）；
# 變數名 OLLAMA_CLIENT 保留以維持 §九 單例表 grep 穩定。
OLLAMA_CLIENT: Any = None
try:
    OLLAMA_CLIENT = get_local_llm_client()
    _ollama_ok = OLLAMA_CLIENT.is_available(force_check=True)
    logger.info(
        "Local LLM client for Strategist: available=%s / Strategist 用本地 LLM 客戶端: 可用=%s",
        _ollama_ok, _ollama_ok,
    )
except Exception as _oc_e:
    logger.warning(
        "Local LLM client init failed: %s / 本地 LLM 客戶端初始化失敗: %s", _oc_e, _oc_e,
    )

# Sprint 5a: Switch Strategist from shadow mode to live mode.
# After G-05 (acquire_lease) and H0 Gate blocking are confirmed, the full
# Scout→Strategist→Guardian→ExecutorAgent pipeline is safe to activate.
# Sprint 5a：策略師從影子模式切換到真實模式。
# G-05（acquire_lease）和 H0 Gate blocking 確認後，完整鏈路已具備安全條件。
# Pre-conditions confirmed (2026-03-31):
#   - G-05: ExecutorAgent.execute_order() calls governance_hub.acquire_lease() (fail-closed)
#   - H0 Gate blocking: _process_pending_intents() now rejects intents when allowed=False
#   - Guardian gate: pipeline_bridge.py routes intents through GuardianAgent review
# 前置條件確認（2026-03-31）：
#   - G-05：ExecutorAgent 已插入 acquire_lease()（fail-closed）
#   - H0 Gate 阻擋：_process_pending_intents() 在 allowed=False 時拒絕 intent
#   - Guardian 門控：pipeline_bridge.py 將 intent 路由至 GuardianAgent 審查
# cost_tracker injected for H1/H5 budget gate; None = no budget constraint (fail-open)
# cost_tracker 注入以啟用 H1/H5 預算門控；None 表示無預算限制（fail-open）

# ── E5-FN-3-FUP-a: Strategist audit_callback wiring ──
# Wires StrategistAgent._audit(...) calls into GOV_HUB._change_audit_log via
# agent_audit_bridge. Satisfies Root Principle #8 "Trade Explainability" by
# ensuring every Strategist decision (edge_evaluation / intent_produced /
# shadow_intent / directive_received / risk_verdict_received / ...) produces
# an append-only audit record.
# Fail-open: GOV_HUB unavailable → bridge silently drops events; Strategist's
# main path is never disrupted.
# Local import of make_agent_audit_callback: the canonical import lives later
# in the AnalystAgent block (line ~258) — duplicated here to keep Strategist's
# wiring self-contained without reordering the existing Analyst import.
# 將 StrategistAgent._audit(...) 透過 agent_audit_bridge 接到 GOV_HUB._change_audit_log；
# 落實根原則 #8「交易可解釋」。fail-open：GOV_HUB 不可用時靜默丟棄，不阻塞 agent。
# 此處本地重複 import make_agent_audit_callback 以保持 Strategist 接線自包含，
# 不重排位於 AnalystAgent 區塊的既有 import（約第 258 行）。
from .agent_audit_bridge import make_agent_audit_callback as _make_agent_audit_callback_strategist

_GOV_HUB_FOR_STRATEGIST: Any = None
try:
    from .paper_trading_routes import GOV_HUB as _GOV_HUB_FOR_STRATEGIST
except ImportError:
    pass

_STRATEGIST_AUDIT_CB = _make_agent_audit_callback_strategist(
    _GOV_HUB_FOR_STRATEGIST, "StrategistAgent"
)

STRATEGIST_AGENT = StrategistAgent(
    config=StrategistConfig(shadow=False),
    message_bus=MESSAGE_BUS,
    ollama_client=OLLAMA_CLIENT,
    cost_tracker=_COST_TRACKER_FOR_STRATEGIST,
    audit_callback=_STRATEGIST_AUDIT_CB,
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

# ── E5-FN-3-FUP-b: Guardian audit_callback wiring ──
# Wires GuardianAgent._audit(...) calls into GOV_HUB._change_audit_log via
# agent_audit_bridge. Satisfies Root Principle #8 "Trade Explainability" by
# ensuring every verdict / event_assessed / risk_pattern_received /
# directive_received call-site appends an audit row.
# Fail-open: if GOV_HUB is unavailable the bridge silently drops events so
# Guardian's main risk-review path is never disrupted.
# 將 GuardianAgent._audit(...) 透過 agent_audit_bridge 接到 GOV_HUB._change_audit_log；
# 落實根原則 #8「交易可解釋」。fail-open：GOV_HUB 不可用時靜默丟棄，不阻塞 Guardian。
# Local import: AnalystAgent pilot (Batch 9) imports make_agent_audit_callback
# later in the module; we do an isolated import here so re-ordering Batch 8/9
# stays safe (leaves pilot import intact).
# 本處使用局部 import，避免影響 Batch 9 AnalystAgent pilot 原有 import 位置。
from .agent_audit_bridge import make_agent_audit_callback as _make_guardian_audit_cb
_GUARDIAN_AUDIT_CB = _make_guardian_audit_cb(_GOV_HUB_FOR_GUARDIAN, "GuardianAgent")

GUARDIAN_AGENT = GuardianAgent(
    config=GuardianConfig(),
    message_bus=MESSAGE_BUS,
    risk_manager=_RISK_MGR_FOR_GUARDIAN,
    ollama_client=OLLAMA_CLIENT,
    governance_hub=_GOV_HUB_FOR_GUARDIAN,
    audit_callback=_GUARDIAN_AUDIT_CB,
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

# E5-FN-3 / 5-Agent Decision Audit Trail (pilot = Analyst).
# E5-FN-3：5-Agent 決策審計跟踪（pilot = Analyst）。
# Wires AnalystAgent._audit(...) calls into GOV_HUB._change_audit_log via the
# agent_audit_bridge module. Satisfies Root Principle #8 "Trade Explainability"
# by ensuring every agent decision produces an append-only audit record.
# Fail-open: if GOV_HUB is unavailable, the bridge silently drops events so
# the agent's main path is never disrupted.
# 將 AnalystAgent._audit(...) 透過 agent_audit_bridge 接到 GOV_HUB._change_audit_log；
# 落實根原則 #8「交易可解釋」。fail-open：GOV_HUB 不可用時靜默丟棄，不阻塞 agent。
from .agent_audit_bridge import make_agent_audit_callback

_GOV_HUB_FOR_ANALYST: Any = None
try:
    from .paper_trading_routes import GOV_HUB as _GOV_HUB_FOR_ANALYST
except ImportError:
    pass

_ANALYST_AUDIT_CB = make_agent_audit_callback(_GOV_HUB_FOR_ANALYST, "AnalystAgent")

ANALYST_AGENT = AnalystAgent(
    config=AnalystConfig(),
    message_bus=MESSAGE_BUS,
    ollama_client=OLLAMA_CLIENT,
    learning_tier_gate=_LTG_FOR_ANALYST,
    audit_callback=_ANALYST_AUDIT_CB,
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

# DEAD-PY-2: DEMO_CONNECTOR removed — BybitDemoConnector trading methods deleted.
# Demo account data is read via the httpx BybitClient (read-only).
# DEMO_CONNECTOR 已移除 — BybitDemoConnector 交易方法已刪除。Demo 帳戶數據改用 httpx BybitClient 讀取（只讀）。
DEMO_CONNECTOR = None

logger.info(
    "Phase 2 strategy pipeline initialized (Rust strategies only) / Phase 2 策略管線初始化完成（僅 Rust 策略）: "
    "symbols=%s, timeframes=%s",
    DEFAULT_SYMBOLS, DEFAULT_TIMEFRAMES,
)

# ── Pipeline Bridge retired (DEAD-PY-2, RC-10) ──────────────────────────────
# PipelineBridge 已退場（DEAD-PY-2，RC-10）— Rust openclaw_engine 為唯一引擎。
# PIPELINE_BRIDGE = None signals soft-degraded mode to startup integrity check.
PIPELINE_BRIDGE = None

# PAPER_ENGINE is always None since ARCH-RC1 1C-3-F (retired).
# Kept as None for compatibility with components that accept paper_engine= kwarg.
# PAPER_ENGINE 自 ARCH-RC1 1C-3-F 後始終為 None（已退場）。
PAPER_ENGINE = None
try:
    from .paper_trading_routes import ENGINE as PAPER_ENGINE  # type: ignore[assignment]
except ImportError:
    pass  # PAPER_ENGINE stays None

# --- B4: CognitiveModulator instantiation + injection into StrategistAgent ---
# B4：实例化 CognitiveModulator 并注入 StrategistAgent（L0 决策门槛调制）
try:
    from program_code.local_model_tools.cognitive_modulator import CognitiveModulator
    _cognitive_modulator = CognitiveModulator()
    STRATEGIST_AGENT.set_cognitive_modulator(_cognitive_modulator)
    logger.info(
        "CognitiveModulator instantiated and injected into StrategistAgent / "
        "认知调制器已实例化并注入 StrategistAgent"
    )
except Exception as e:
    logger.warning("Could not inject CognitiveModulator: %s / 注入认知调制器失败: %s", e, e)

# Batch 10: OMS SM-03 removed — Python OMS deprecated 2026-04-10.
# Order lifecycle now tracked in Rust event_consumer → trading.orders + order_state_changes.
# Batch 10：OMS SM-03 已移除 — Python OMS 於 2026-04-10 廢棄。
# 訂單生命週期現由 Rust event_consumer 寫入 trading.orders + order_state_changes。

# --- Batch 10: AnalystAgent initialization ---
# Batch 10：AnalystAgent 初始化（交易結果分析 + L2 Cron 觸發）
# E5-FN-3: reuse the same audit bridge as Batch 9 so the re-initialized
# AnalystAgent keeps emitting 5-Agent audit trail events.
# E5-FN-3：重用 Batch 9 的審計橋接，確保重建後的 AnalystAgent 仍寫 audit trail。
try:
    from .analyst_agent import AnalystAgent, AnalystConfig
    # LLM-ABC-MIGRATION-1: heavy variant via factory (Ollama 27B | LM Studio heavy).
    # LLM-ABC-MIGRATION-1：heavy 變體經 factory（Ollama 27B | LM Studio 重型）。
    from .local_llm_factory import get_local_llm_client
    ANALYST_AGENT = AnalystAgent(
        config=AnalystConfig(),
        message_bus=MESSAGE_BUS if 'MESSAGE_BUS' in dir() else None,
        ollama_client=get_local_llm_client(heavy=True),  # heavy: complex weekly pattern analysis
        audit_callback=_ANALYST_AUDIT_CB,
    )
    ANALYST_AGENT.start()
    if MESSAGE_BUS is not None:
        from .multi_agent_framework import AgentRole as _AR
        MESSAGE_BUS.subscribe(_AR.ANALYST, ANALYST_AGENT.on_message)
        logger.info("AnalystAgent subscribed to MessageBus / 分析师代理已订阅消息总线")
except (ImportError, Exception) as e:
    ANALYST_AGENT = None
    logger.warning("Could not initialize AnalystAgent: %s", e)

# ── Batch 11: ExecutorAgent — order execution wrapper + quality feedback ──
# Batch 11：ExecutorAgent — 订单执行包装 + 执行质量反馈
try:
    from .executor_agent import ExecutorAgent, ExecutorConfig
    from .multi_agent_framework import AgentRole as _AR11

    _GOV_HUB_FOR_EXECUTOR: Any = None
    try:
        from .paper_trading_routes import GOV_HUB as _GOV_HUB_FOR_EXECUTOR
    except ImportError:
        pass

    # ── E5-FN-3-FUP-c: Executor audit_callback wiring ──
    # Wires ExecutorAgent._audit(...) calls into GOV_HUB._change_audit_log via
    # agent_audit_bridge. Satisfies Root Principle #8 "Trade Explainability".
    # Fail-open: GOV_HUB unavailable → bridge silently drops events.
    # 將 ExecutorAgent._audit(...) 透過 agent_audit_bridge 接到 GOV_HUB._change_audit_log；
    # 落實根原則 #8「交易可解釋」。fail-open：GOV_HUB 不可用時靜默丟棄，不阻塞 agent。
    _EXECUTOR_AUDIT_CB = make_agent_audit_callback(_GOV_HUB_FOR_EXECUTOR, "ExecutorAgent")

    EXECUTOR_AGENT = ExecutorAgent(
        config=ExecutorConfig(),
        message_bus=MESSAGE_BUS,
        paper_engine=PAPER_ENGINE,
        governance_hub=_GOV_HUB_FOR_EXECUTOR,
        audit_callback=_EXECUTOR_AUDIT_CB,
    )
    EXECUTOR_AGENT.start()
    CONDUCTOR.register_agent(_AR11.EXECUTOR, resource_mode="local")
    CONDUCTOR.set_agent_state(_AR11.EXECUTOR, _AgentState.RUNNING)
    MESSAGE_BUS.subscribe(_AR11.EXECUTOR, EXECUTOR_AGENT.on_message)

    logger.info(
        "Batch 11: ExecutorAgent initialized (bus=%s, engine=%s) / Batch 11：ExecutorAgent 已初始化",
        MESSAGE_BUS is not None, PAPER_ENGINE is not None,
    )
except (ImportError, Exception) as e:
    EXECUTOR_AGENT = None
    logger.warning("Could not initialize ExecutorAgent: %s / 无法初始化 ExecutorAgent: %s", e, e)

# ── Batch 12: PaperLiveGate instantiation (Paper→Live gate conditions) ──
# Batch 12：PaperLiveGate 实例化（纸盘→实盘闸门条件）
try:
    from .paper_live_gate import PaperLiveGate, PaperLiveGateConfig

    def _paper_live_gate_audit_cb(event_type: str, event_data: dict) -> None:
        """Audit callback for PaperLiveGate → ChangeAuditLog"""
        try:
            from .paper_trading_routes import GOV_HUB as _hub
            if _hub is not None and _hub._change_audit_log is not None:
                from .change_audit_log import ChangeType
                _hub._change_audit_log.record_change(
                    change_type=ChangeType.STATE_CHANGE,
                    who="PaperLiveGate",
                    what=f"Gate event: {event_type}",
                    reason=str(event_data.get('reason', 'gate_evaluation')),
                    old_value=event_data.get('old_value'),
                    new_value=event_data.get('new_value'),
                )
        except Exception as e:
            logger.warning("PaperLiveGate audit callback failed (non-fatal): %s", e)

    PAPER_LIVE_GATE = PaperLiveGate(
        config=PaperLiveGateConfig(),
        audit_callback=_paper_live_gate_audit_cb,
    )
    logger.info("Batch 12: PaperLiveGate instantiated / PaperLiveGate 已实例化")
except (ImportError, Exception) as e:
    PAPER_LIVE_GATE = None
    logger.warning("Could not instantiate PaperLiveGate: %s", e)


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
    if TELEGRAM.is_enabled:
        logger.info("Telegram alerter enabled / Telegram 告警已啟用")
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
        pipeline_bridge=None,
    )
    GRAFANA_WRITER.start()
    logger.info("Grafana data writer started / Grafana 数据写入器已启动")
except Exception as e:
    GRAFANA_WRITER = None
    logger.info("Grafana data writer not available: %s / Grafana 写入器不可用: %s", e, e)

# DEAD-PY-2: Demo connector wiring removed. DEMO_CONNECTOR = None.
# Demo 連接器接線已移除。Demo 帳戶數據讀取改用 httpx BybitClient。
DEMO_SYNC = None

# ── Market Scanner + Strategy Auto-Deployer (autonomous opportunity discovery) ──
# 市场扫描器 + 策略自动部署器（自主发现交易机会）
try:
    from local_model_tools.market_scanner import MarketScanner
    from local_model_tools.strategy_auto_deployer import StrategyAutoDeployer

    # Lazy dispatcher reference: resolves at call time so it works even if
    # market feed starts after the auto-deployer is created.
    # 惰性 dispatcher 引用：调用时才解析，无论行情流何时启动均有效。
    from . import paper_trading_routes as _ptr

    MARKET_SCANNER = MarketScanner(max_symbols=25, categories=["linear", "spot"])
    AUTO_DEPLOYER = StrategyAutoDeployer(
        orchestrator=ORCHESTRATOR,
        kline_manager=KLINE_MANAGER,
        paper_engine=PAPER_ENGINE,
        max_symbols=30,            # 25 linear + 5 spot reserved
        risk_per_trade_pct=3.0,    # Risk 3% of balance per trade (max loss per trade)
        min_qty_usdt=20.0,         # Minimum $20 per trade
        max_qty_pct=18.0,          # Max 18% of balance per single trade (90% of 20% risk limit, 10% headroom)

        pinned_symbols=["BTCUSDT", "ETHUSDT"],  # Always monitor + attempt to trade (learning/evolution)
        reserved_slots={"spot": 5},  # 5 slots reserved for spot — linear can't squeeze them out
    )
    MARKET_SCANNER.register_on_scan(AUTO_DEPLOYER.on_scan_results)
    MARKET_SCANNER.start()

    # DEAD-PY-2: PipelineBridge removed — auto-deployer runs without bridge reference.
    # DEAD-PY-2：PipelineBridge 已移除 — 自動部署器不再持有橋接器引用。

    # 0A-5: Inject BacktestEngine into auto-deployer for pre-deployment validation.
    # 0A-5：注入 BacktestEngine 到自動部署器，供部署前回測驗證使用。
    try:
        from .backtest_routes import get_backtest_engine as _get_bt_engine
        _bt_engine = _get_bt_engine()
        AUTO_DEPLOYER.set_backtest_engine(_bt_engine, min_sharpe=0.0)
        logger.info(
            "0A-5: BacktestEngine injected into auto-deployer / "
            "BacktestEngine 已注入自動部署器供部署前驗證"
        )
    except Exception as _bt_wire_err:
        logger.warning(
            "0A-5: Could not wire BacktestEngine to auto-deployer (fail-open): %s",
            _bt_wire_err,
        )

    # 0A-2: Inject auto-deployer into evolution_routes for B13 auto-apply on evolution completion.
    # 0A-2：注入自動部署器到 evolution_routes，使進化完成後自動應用最優參數（B13 閉環）。
    # Paper/demo mode: no confirmation needed (per Operator decision in Batch 9).
    # Paper/demo 模式：免確認（依 Batch 9 Operator 決策）。
    try:
        from . import evolution_routes as _evolution_routes
        _evolution_routes.set_auto_deployer(AUTO_DEPLOYER)
        logger.info(
            "0A-2: Auto-deployer injected into evolution_routes for B13 auto-apply / "
            "自動部署器已注入 evolution_routes 供 B13 進化結果自動應用"
        )
    except Exception as _evo_wire_err:
        logger.warning(
            "0A-2: Could not wire auto-deployer to evolution_routes (fail-open): %s",
            _evo_wire_err,
        )

    logger.info("Market scanner + auto-deployer started / 市场扫描器+自动部署器已启动")
except Exception as e:
    MARKET_SCANNER = None
    AUTO_DEPLOYER = None
    logger.warning("Market scanner not available: %s", e)

# ── ScoutWorker: 30-minute periodic intel injection into Strategist chain ──
# ScoutWorker：每 30 分鐘定時掃描並通過 ScoutAgent → MessageBus 向策略師注入情報
# This complements MarketScanner's own 5-minute loop (which feeds AUTO_DEPLOYER).
# ScoutWorker 補充 MarketScanner 自身的 5 分鐘循環（後者只饋送 AUTO_DEPLOYER）。
# ScoutWorker covers the Scout→Strategist intel pipeline for AI-driven analysis.
# ScoutWorker 覆蓋 Scout→策略師情報管線，供 AI 驅動的策略分析使用。
_SCOUT_WORKER = None
try:
    from .scout_worker import ScoutWorker as _ScoutWorkerClass

    def _make_scout_scan_fn():
        """
        Build a scan function that runs one full scan and injects intel via ScoutAgent.
        構建掃描函數：執行一次完整掃描，並通過 ScoutAgent.produce_intel() 注入情報。

        Uses module-level MARKET_SCANNER and SCOUT_AGENT captured at init time.
        捕獲模塊級別的 MARKET_SCANNER 和 SCOUT_AGENT，在初始化時綁定。

        Returns None if either dependency is unavailable (fail-open for scout intel).
        若任一依賴不可用，返回 None（情報注入 fail-open，不影響主程序）。
        """
        _ms = MARKET_SCANNER
        _sa = SCOUT_AGENT
        if _ms is None or _sa is None:
            return None

        def _scan_and_produce_intel() -> None:
            """
            Execute one scan cycle and push top opportunities as Scout intel.
            執行一次掃描週期，將頂部機會推送為 Scout 情報供策略師分析。

            Fail-open: exceptions are caught in ScoutWorker._run_loop(), so
            this function only needs to raise on genuine failures.
            Fail-open：ScoutWorker._run_loop() 已捕獲異常，此函數只需在真正失敗時拋出。
            """
            opportunities = _ms.scan()
            if not opportunities:
                logger.debug(
                    "ScoutWorker: scan returned no opportunities / 掃描未返回機會，跳過情報注入"
                )
                return
            # Take top-5 opportunities by score to avoid intel flooding.
            # 取評分最高的前 5 個機會，避免情報洪泛策略師消息隊列。
            top = sorted(opportunities, key=lambda o: getattr(o, "score", 0.0), reverse=True)[:5]
            symbols = [getattr(o, "symbol", str(o)) for o in top]
            summary = ", ".join(
                f"{getattr(o, 'symbol', '?')}({getattr(o, 'score', 0.0):.2f})"
                for o in top
            )
            _sa.produce_intel(
                source="ScoutWorker",
                content=f"30-min periodic scan top opportunities: {summary}",
                symbols=symbols,
                relevance_score=0.6,
                freshness_seconds=0,
                metadata={"trigger": "scout_worker_30min", "total_opportunities": len(opportunities)},
            )
            logger.info(
                "ScoutWorker: intel produced for %d symbols (top 5 of %d opportunities) "
                "/ ScoutWorker：已為 %d 個幣種生成情報（%d 個機會中的前 5）",
                len(symbols), len(opportunities), len(symbols), len(opportunities),
            )

        return _scan_and_produce_intel

    _scout_scan_fn = _make_scout_scan_fn()
    if _scout_scan_fn is not None:
        _SCOUT_WORKER = _ScoutWorkerClass(scan_fn=_scout_scan_fn)
        _SCOUT_WORKER.start()
        logger.info(
            "ScoutWorker initialized and started (30-min intel injection) "
            "/ ScoutWorker 已初始化並啟動（30 分鐘情報注入）"
        )
    else:
        logger.warning(
            "ScoutWorker not started: MARKET_SCANNER or SCOUT_AGENT unavailable "
            "/ ScoutWorker 未啟動：MARKET_SCANNER 或 SCOUT_AGENT 不可用"
        )
except Exception as _scout_worker_exc:
    # Scout intel injection failure is non-fatal; main pipeline continues.
    # Scout 情報注入失敗不影響主程序；繼續運行。
    logger.warning(
        "ScoutWorker initialization failed (non-fatal): %s "
        "/ ScoutWorker 初始化失敗（非致命）：%s",
        type(_scout_worker_exc).__name__,
        _scout_worker_exc,
    )
    _SCOUT_WORKER = None

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

    # DEAD-PY-2: observation writer no longer injected into PipelineBridge (PIPELINE_BRIDGE = None).
    pass
except Exception as _e1_e:
    logger.info("Auto-observation writer not wired: %s", _e1_e)


# ── Auto-start market feed based on global mode ──
# 根据全局模式决定是否自动启动行情数据流（服务重启场景下的自动恢复）
_FEED_AUTO_MODES = {"observe_only", "shadow_only", "demo_reserved", "live_reserved"}

# ─────────────────────────────────────────────────────────────────────
# APR01-P0-1: Inject TruthSourceRegistry into StrategistAgent + AnalystAgent
# APR01-P0-1：注入 TruthSourceRegistry 到 StrategistAgent + AnalystAgent
#
# Without this injection, set_truth_registry() was defined but never called,
# making the entire Phase 2 learning loop (pattern claims → strategy weights)
# dead code. The singleton also loads persisted claims from disk on first
# access (APR01-P1-1), so knowledge survives restarts.
# 若缺少此注入，set_truth_registry() 虽已定义却从未被调用，
# 导致整个 Phase 2 学习循环（模式声明 → 策略权重）成为死代码。
# 单例在首次访问时从磁盘加载已持久化的声明，使知识在重启后可恢复。
# ─────────────────────────────────────────────────────────────────────
try:
    from .truth_source_registry import get_truth_registry
    _TRUTH_REGISTRY = get_truth_registry()

    if STRATEGIST_AGENT is not None:
        STRATEGIST_AGENT.set_truth_registry(_TRUTH_REGISTRY)
        logger.info(
            "TruthSourceRegistry injected into StrategistAgent "
            "/ TruthSourceRegistry 已注入 StrategistAgent"
        )
    if ANALYST_AGENT is not None:
        ANALYST_AGENT.set_truth_registry(_TRUTH_REGISTRY)
        logger.info(
            "TruthSourceRegistry injected into AnalystAgent "
            "/ TruthSourceRegistry 已注入 AnalystAgent"
        )
except (ImportError, Exception) as _tsr_err:
    # fail-open: agents continue without registry — pattern learning disabled
    # fail-open：agents 继续运行但无 registry — 模式学习已禁用
    _TRUTH_REGISTRY = None
    logger.warning(
        "Could not inject TruthSourceRegistry into agents (fail-open): %s "
        "/ 無法注入 TruthSourceRegistry 到 agents（fail-open）：%s",
        _tsr_err, _tsr_err,
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


# =============================================================================
# Public Exports / 公共导出
# =============================================================================

__all__ = [
    # Shared instances / 共享实例
    "DEFAULT_SYMBOLS",
    "DEFAULT_TIMEFRAMES",
    "KLINE_MANAGER",
    "INDICATOR_ENGINE",
    "SIGNAL_ENGINE",
    "ORCHESTRATOR",
    "TRADE_ATTRIBUTION",
    # Agents / 代理
    "SCOUT_AGENT",
    "MESSAGE_BUS",
    "CONDUCTOR",
    "OLLAMA_CLIENT",
    "STRATEGIST_AGENT",
    "GUARDIAN_AGENT",
    "ANALYST_AGENT",
    # Pipeline / 管线 (DEMO_CONNECTOR/PIPELINE_BRIDGE removed in DEAD-PY-2)
    "PAPER_ENGINE",
    "PAPER_LIVE_GATE",
    # Alerting / 告警
    "TELEGRAM",
    # Scanner + Deployer / 扫描器 + 部署器
    "MARKET_SCANNER",
    "AUTO_DEPLOYER",
    # Router / 路由
    "phase2_router",
    # Helpers / 辅助
    "_SYMBOL_PATTERN",
    "_STRATEGY_NAME_PATTERN",
    "_VALID_TIMEFRAMES",
    "_validate_symbol",
    "_validate_strategy_name",
    "_envelope",
]

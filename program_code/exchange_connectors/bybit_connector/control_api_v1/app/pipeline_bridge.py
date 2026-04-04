"""
Pipeline Bridge -- Connects Strategy Pipeline to Paper Trading Engine
管线桥接器 -- 连接策略管线与纸上交易引擎

TD-01 Split: This file is now a thin facade that combines three mixins:
  - bridge_core.py    — lifecycle, tick processing, intent submission (~845 lines)
  - bridge_agents.py  — agent gates, hooks, scout scans, cron (~919 lines)
  - bridge_stats.py   — positions, round-trips, market data, stats (~825 lines)

All existing imports (`from .pipeline_bridge import PipelineBridge`) remain valid.
所有既有的 import 路徑不變。

MODULE_NOTE (中文):
  本模块是 Phase 3a 的核心组件，解决策略管线与纸上交易引擎之间的断裂问题。

  职责：
  1. Tick Fan-Out：将 WebSocket tick 同时分发给 KlineManager 和 StrategyOrchestrator
  2. Intent→Order Bridge：将策略产生的 OrderIntent 提交到 PaperTradingEngine
  3. 执行回调：将成交结果反馈给策略，让策略知道其意图是否被执行

MODULE_NOTE (English):
  Core Phase 3a component that bridges the strategy pipeline and paper trading pipeline.

Safety invariant:
  - system_mode = read_only (unchanged)
  - All orders go through RiskManager via PaperTradingEngine.submit_order()
  - All data marked is_simulated=True
"""

from .bridge_core import _BridgeCoreMixin
from .bridge_agents import _BridgeAgentsMixin
from .bridge_stats import _BridgeStatsMixin


class PipelineBridge(_BridgeCoreMixin, _BridgeAgentsMixin, _BridgeStatsMixin):
    """
    IPC relay + Agent callback container (RC-10/IPC-04 downgraded).
    IPC 中繼 + Agent 回調容器（RC-10/IPC-04 降級）。

    Previously: full tick processing bridge (KlineManager→Indicators→Signals→Strategies→Intents).
    Now: Rust engine handles ALL tick processing. This class is retained only for:
      1. Agent dependency injection (set_*() methods) — Scout/Strategist/Guardian etc.
      2. API state queries (get_stats(), _latest_prices fallback)
      3. Future Agent callback relay (on_tick_result from Rust IPC)
    Tick processing (on_tick) is DISABLED — self._active is never set to True (RC-10).

    之前：完整 tick 處理橋接。現在：Rust 引擎處理所有 tick。此類僅保留用於：
      1. Agent 依賴注入 2. API 狀態查詢 3. 未來 Agent 回調中繼

    Composed from:
      _BridgeCoreMixin   — __init__, set_*, lifecycle, on_tick, intent pipeline
      _BridgeAgentsMixin  — gate checks, execution hooks, scout, cron, edge filter
      _BridgeStatsMixin   — position open/close, round-trips, funding, volume, stats
    """
    pass

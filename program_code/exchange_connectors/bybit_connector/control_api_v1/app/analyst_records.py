"""
Analyst Records — Pure dataclasses for AnalystAgent
====================================================
Sibling extracted from ``analyst_agent.py`` (G3-08-FUP-ANALYST-SPLIT P2,
2026-04-28) to keep ``analyst_agent.py`` under §九 800 LOC warning line.

MODULE_NOTE (中文):
  本模組存放 AnalystAgent 使用的純數據結構（dataclasses）：
  - ``TradeRecord``：已完成的單筆 round-trip 交易記錄（含 fees + param_snapshot）
  - ``PatternInsight``：L2 模式發現結果（winning/losing patterns + regime matrix）
  - ``AnalystConfig``：AnalystAgent 配置（L2 觸發門檻、滾動窗口大小等）

  零行為變更：所有 dataclass 欄位、預設值、property、to_dict 序列化保持
  與原始 ``analyst_agent.py`` 完全一致。``analyst_agent.py`` 透過
  ``from .analyst_records import TradeRecord, PatternInsight, AnalystConfig``
  re-export，確保 ``from app.analyst_agent import TradeRecord`` 等既有
  test / strategy_wiring import 路徑不破。

MODULE_NOTE (English):
  Pure dataclasses for AnalystAgent extracted from ``analyst_agent.py``
  (G3-08-FUP-ANALYST-SPLIT P2, 2026-04-28) to keep parent under §九 800 LOC
  warning line.

  Zero behavior change: every dataclass field, default, property and
  ``to_dict`` serialisation matches the original ``analyst_agent.py`` byte
  for byte. ``analyst_agent.py`` re-exports these symbols so existing
  ``from app.analyst_agent import TradeRecord`` imports remain valid.
"""

from __future__ import annotations

import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List


# ═══════════════════════════════════════════════════════════════════════════════
# TradeRecord / 已完成交易記錄
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TradeRecord:
    """
    A completed round-trip trade record / 已完成的交易回合记录

    U-05: Added fees_paid and param_snapshot for accurate cost attribution
    and parameter auditing (Principle 8 auditability).
    U-05：新增 fees_paid 和 param_snapshot 用于精确成本归因和参数审计（原则 8）。
    """
    trade_id: str = ""
    symbol: str = ""
    strategy: str = ""
    direction: str = ""
    entry_price: float = 0.0
    exit_price: float = 0.0
    pnl: float = 0.0
    hold_ms: int = 0
    regime: str = "unknown"
    timestamp_ms: int = 0
    # U-05: Real round-trip fees (entry_fee + close_fee) / 真实 round-trip 费用
    fees_paid: float = 0.0
    # U-05: Dynamic parameters snapshot at entry time / 开仓时动态参数快照
    param_snapshot: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

    @property
    def net_pnl(self) -> float:
        """PnL after fees / 扣除费用后的净盈亏"""
        return self.pnl - self.fees_paid

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trade_id": self.trade_id,
            "symbol": self.symbol,
            "strategy": self.strategy,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "exit_price": self.exit_price,
            "pnl": self.pnl,
            "hold_ms": self.hold_ms,
            "regime": self.regime,
            "timestamp_ms": self.timestamp_ms,
            "is_win": self.is_win,
            # U-05: Include fees and param_snapshot in serialized output.
            # U-05：在序列化输出中包含费用和参数快照。
            "fees_paid": self.fees_paid,
            "net_pnl": self.net_pnl,
            "param_snapshot": self.param_snapshot,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PatternInsight / L2 模式發現結果
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PatternInsight:
    """L2 pattern discovery result / L2 模式发现结果"""
    insight_id: str = field(default_factory=lambda: f"insight_{uuid.uuid4().hex[:12]}")
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    observations_count: int = 0
    winning_patterns: List[str] = field(default_factory=list)
    losing_patterns: List[str] = field(default_factory=list)
    regime_strategy_matrix: Dict[str, Dict[str, float]] = field(default_factory=dict)
    source: str = "unknown"  # "ai" or "statistical"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "insight_id": self.insight_id,
            "timestamp_ms": self.timestamp_ms,
            "observations_count": self.observations_count,
            "winning_patterns": self.winning_patterns,
            "losing_patterns": self.losing_patterns,
            "regime_strategy_matrix": self.regime_strategy_matrix,
            "source": self.source,
            "metadata": self.metadata,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# AnalystConfig / AnalystAgent 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AnalystConfig:
    """Configuration for AnalystAgent / AnalystAgent 配置"""
    # L2 trigger: minimum observations before pattern analysis / L2 触发：最小观察数
    # 0A-6: lowered from 50 to 20 for faster L2 pattern discovery feedback loop
    # 0A-6：从 50 降至 20，加速 L2 模式发现反馈闭环（可通过 ANALYST_L2_MIN_OBS 覆盖）
    l2_min_observations: int = int(os.environ.get("ANALYST_L2_MIN_OBS", "20"))
    # Rolling window for metrics / 滚动窗口大小
    rolling_window: int = 50
    # Strategy ranking minimum trades / 策略排名最小交易数
    min_trades_for_ranking: int = 10
    # Maximum trade records to keep in memory / 内存中保留的最大交易记录数
    max_records: int = 5000

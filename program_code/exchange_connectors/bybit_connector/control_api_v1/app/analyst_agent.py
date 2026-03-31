"""
Batch 9 (Pre-write) — AnalystAgent: Trade result analysis + learning metrics + pattern discovery
=================================================================================================
Governance refs: EX-06 §7, DOC-04 §G Multi-Agent, EX-05 §3

MODULE_NOTE (中文):
  AnalystAgent 是 5-Agent 体系中的"分析师"。
  职责：
  1. 消费 ROUND_TRIP_COMPLETE 消息，分析每笔交易结果
  2. L1 层：计算滚动胜率、策略排名、regime 适配度，更新 LearningTierGate 指标
  3. L2 层：observations ≥ 200 后，调用 Qwen analyze_patterns() 产出 PatternInsight
  4. PatternInsight 包含：winning_patterns, losing_patterns, regime_strategy_matrix
  5. 所有分析结果写入审计日志

  安全不变量：
  - 只读分析，不产生任何交易指令
  - fail-closed：错误时停止分析但不影响交易
  - 所有结果写入审计

MODULE_NOTE (English):
  AnalystAgent is the "analyst" in the 5-Agent system.
  Responsibilities:
  1. Consume ROUND_TRIP_COMPLETE messages, analyze each trade result
  2. L1: Calculate rolling win rate, strategy ranking, regime fit, update LearningTierGate metrics
  3. L2: After observations >= 200, call Qwen analyze_patterns() to produce PatternInsight
  4. PatternInsight contains: winning_patterns, losing_patterns, regime_strategy_matrix
  5. All analysis results written to audit log

  Safety invariants:
  - Read-only analysis, never produces trade instructions
  - fail-closed: errors stop analysis but don't affect trading
  - All results audited
"""

from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    MessageBus,
    MessageType,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures / 数据结构
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class TradeRecord:
    """A completed round-trip trade record / 已完成的交易回合记录"""
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

    @property
    def is_win(self) -> bool:
        return self.pnl > 0

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
        }


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


@dataclass
class AnalystConfig:
    """Configuration for AnalystAgent / AnalystAgent 配置"""
    # L2 trigger: minimum observations before pattern analysis / L2 触发：最小观察数
    l2_min_observations: int = 200
    # Rolling window for metrics / 滚动窗口大小
    rolling_window: int = 50
    # Strategy ranking minimum trades / 策略排名最小交易数
    min_trades_for_ranking: int = 10
    # Maximum trade records to keep in memory / 内存中保留的最大交易记录数
    max_records: int = 5000


# ═══════════════════════════════════════════════════════════════════════════════
# AnalystAgent / 分析师代理
# ═══════════════════════════════════════════════════════════════════════════════

class AnalystAgent:
    """EX-06 §7 — Trade analysis, learning metrics, and pattern discovery agent.

    L1: Statistical analysis (always running)
    L2: AI pattern discovery (triggered after sufficient observations)

    L1：统计分析（始终运行）
    L2：AI 模式发现（在足够观察后触发）
    """

    def __init__(
        self,
        *,
        config: Optional[AnalystConfig] = None,
        message_bus: Optional[MessageBus] = None,
        ollama_client: Optional[Any] = None,
        learning_tier_gate: Optional[Any] = None,
        audit_callback: Optional[Callable] = None,
    ):
        self.config = config or AnalystConfig()
        self.bus = message_bus
        self._ollama = ollama_client
        self._learning_tier_gate = learning_tier_gate
        self._audit_callback = audit_callback
        self.state = AgentState.INITIALIZING
        self._lock = threading.Lock()

        # Trade records / 交易记录
        self._records: List[TradeRecord] = []

        # Per-strategy metrics / 策略级指标
        self._strategy_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0, "trades": 0, "pnl_list": []}
        )

        # Per-regime metrics / Regime 级指标
        self._regime_stats: Dict[str, Dict[str, Any]] = defaultdict(
            lambda: {"wins": 0, "losses": 0, "total_pnl": 0.0, "trades": 0}
        )

        # L2 pattern insights / L2 模式洞察
        self._pattern_insights: List[PatternInsight] = []
        self._last_l2_analysis_count: int = 0

        # Truth Source Registry: injected externally for claim registration
        # 知識登記表：外部注入，用於登記模式聲明（Principle 7 隔離）
        self._truth_registry: Optional[Any] = None

        # Stats / 统计
        self._stats = {
            "trades_analyzed": 0,
            "l1_updates": 0,
            "l2_analyses": 0,
            "errors": 0,
        }

    # ── Lifecycle / 生命周期 ──

    def start(self) -> None:
        self.state = AgentState.RUNNING
        logger.info("AnalystAgent started / 分析师代理已启动")

    def pause(self) -> None:
        self.state = AgentState.PAUSED

    def stop(self) -> None:
        self.state = AgentState.STOPPED
        logger.info("AnalystAgent stopped / 分析师代理已停止")

    # ── Message Handler / 消息处理 ──

    def on_message(self, message: AgentMessage) -> None:
        """Handle incoming messages / 处理入站消息"""
        if self.state != AgentState.RUNNING:
            return

        if message.message_type == MessageType.ROUND_TRIP_COMPLETE:
            self._handle_round_trip(message)
        elif message.message_type == MessageType.EXECUTION_REPORT:
            self._handle_execution_report(message)
        elif message.message_type == MessageType.SYSTEM_DIRECTIVE:
            self._handle_directive(message)

    def _handle_round_trip(self, message: AgentMessage) -> None:
        """Process a completed round-trip trade / 处理已完成的交易回合"""
        payload = message.payload
        if not payload:
            return

        try:
            record = TradeRecord(
                trade_id=payload.get("trade_id", f"trade_{uuid.uuid4().hex[:12]}"),
                symbol=payload.get("symbol", ""),
                strategy=payload.get("strategy", "unknown"),
                direction=payload.get("direction", ""),
                entry_price=float(payload.get("entry_price", 0.0)),
                exit_price=float(payload.get("exit_price", 0.0)),
                pnl=float(payload.get("pnl", 0.0)),
                hold_ms=int(payload.get("hold_ms", 0)),
                regime=payload.get("regime", "unknown"),
                timestamp_ms=int(payload.get("timestamp_ms", int(time.time() * 1000))),
            )
            self.analyze_trade(record)
        except Exception as e:
            logger.error("Failed to handle round trip: %s / 处理交易回合失败: %s", e, e)
            with self._lock:
                self._stats["errors"] += 1

    def _handle_execution_report(self, message: AgentMessage) -> None:
        """Process execution report (for quality metrics) / 处理执行报告"""
        self._audit("execution_report_received", message.payload)

    def _handle_directive(self, message: AgentMessage) -> None:
        """Handle Conductor directives / 处理 Conductor 指令"""
        directive = message.payload.get("directive_type", "")
        if directive == "trigger_l2_analysis":
            self._run_l2_analysis()
        self._audit("directive_received", message.payload)

    # ── L1: Statistical Analysis / L1：统计分析 ──

    def analyze_trade(self, record: TradeRecord) -> Dict[str, Any]:
        """
        L1 analysis: update rolling metrics for the trade.
        L1 分析：更新交易的滚动指标。
        """
        with self._lock:
            self._records.append(record)
            if len(self._records) > self.config.max_records:
                self._records = self._records[-self.config.max_records:]
            self._stats["trades_analyzed"] += 1
            self._stats["l1_updates"] += 1

        # Update per-strategy stats / 更新策略级统计
        with self._lock:
            ss = self._strategy_stats[record.strategy]
            ss["trades"] += 1
            ss["total_pnl"] += record.pnl
            ss["pnl_list"].append(record.pnl)
            if len(ss["pnl_list"]) > self.config.rolling_window:
                ss["pnl_list"] = ss["pnl_list"][-self.config.rolling_window:]
            if record.is_win:
                ss["wins"] += 1
            else:
                ss["losses"] += 1

            # Update per-regime stats / 更新 regime 级统计
            rs = self._regime_stats[record.regime]
            rs["trades"] += 1
            rs["total_pnl"] += record.pnl
            if record.is_win:
                rs["wins"] += 1
            else:
                rs["losses"] += 1

        # Compute metrics / 计算指标
        metrics = self.compute_strategy_metrics(record.strategy)

        # Update LearningTierGate if available / 更新 LearningTierGate
        if self._learning_tier_gate:
            try:
                total = metrics.get("total_trades", 0)
                win_rate = metrics.get("win_rate", 0.0)
                if hasattr(self._learning_tier_gate, "update_metrics"):
                    self._learning_tier_gate.update_metrics(
                        observation_count=total,
                        win_rate=win_rate,
                    )
            except Exception as e:
                logger.debug("LearningTierGate update failed: %s", e)

        # Audit / 审计
        self._audit("trade_analyzed", {
            "record": record.to_dict(),
            "metrics": metrics,
        })

        # Check if L2 should be triggered / 检查是否应触发 L2
        total_records = len(self._records)
        if (
            total_records >= self.config.l2_min_observations
            and total_records - self._last_l2_analysis_count >= self.config.l2_min_observations
        ):
            self._run_l2_analysis()

        return metrics

    def compute_strategy_metrics(self, strategy: str) -> Dict[str, Any]:
        """Compute metrics for a specific strategy / 计算指定策略的指标"""
        with self._lock:
            ss = self._strategy_stats.get(strategy, {})
            trades = ss.get("trades", 0)
            wins = ss.get("wins", 0)
            total_pnl = ss.get("total_pnl", 0.0)
            pnl_list = ss.get("pnl_list", [])

        if trades == 0:
            return {"strategy": strategy, "total_trades": 0, "win_rate": 0.0, "total_pnl": 0.0, "sharpe_ratio": 0.0}

        win_rate = wins / trades if trades > 0 else 0.0

        # Rolling Sharpe (simplified: mean/std of PnL)
        sharpe = 0.0
        if pnl_list and len(pnl_list) >= 2:
            mean_pnl = sum(pnl_list) / len(pnl_list)
            variance = sum((p - mean_pnl) ** 2 for p in pnl_list) / (len(pnl_list) - 1)
            std_pnl = variance ** 0.5
            if std_pnl > 0:
                sharpe = mean_pnl / std_pnl

        return {
            "strategy": strategy,
            "total_trades": trades,
            "win_rate": round(win_rate, 4),
            "total_pnl": round(total_pnl, 6),
            "sharpe_ratio": round(sharpe, 4),
            "rolling_window": len(pnl_list),
        }

    def get_strategy_rankings(self) -> List[Dict[str, Any]]:
        """Rank strategies by Sharpe ratio / 按 Sharpe 比率排名策略"""
        with self._lock:
            strategies = list(self._strategy_stats.keys())

        rankings = []
        for s in strategies:
            m = self.compute_strategy_metrics(s)
            if m.get("total_trades", 0) >= self.config.min_trades_for_ranking:
                rankings.append(m)

        rankings.sort(key=lambda x: x.get("sharpe_ratio", 0.0), reverse=True)
        return rankings

    def get_regime_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Get per-regime performance / 获取 regime 级性能"""
        with self._lock:
            result = {}
            for regime, stats in self._regime_stats.items():
                trades = stats["trades"]
                wins = stats["wins"]
                result[regime] = {
                    "trades": trades,
                    "win_rate": round(wins / trades, 4) if trades > 0 else 0.0,
                    "total_pnl": round(stats["total_pnl"], 6),
                }
            return result

    def set_truth_registry(self, registry: Any) -> None:
        """
        Inject TruthSourceRegistry for pattern claim registration.
        注入知識登記表，供模式洞察登記聲明使用。

        Fail-open: if registry is None, analyze_patterns() continues without registration.
        失敗開放：registry 為 None 時，分析繼續正常運行，不登記聲明。
        """
        self._truth_registry = registry

    def _register_pattern_claims(self, insight: Any) -> None:
        """
        Register winning/losing patterns from insight into TruthSourceRegistry.
        將洞察中的贏/輸模式登記到知識登記表。

        Fail-open: any error → log warning, never raises.
        失敗開放：任何異常 → 記錄警告，不向上拋出。
        """
        if self._truth_registry is None:
            return
        try:
            n_obs = len(self._records)
            confidence = min(0.85, 0.5 + n_obs * 0.001)
            for pattern_text in (getattr(insight, "winning_patterns", None) or []):
                self._truth_registry.register_claim(
                    pattern_text=str(pattern_text),
                    evidence_source="ai",
                    observation_count=n_obs,
                    confidence=confidence,
                    applies_to_regime="all",
                    applies_to_strategy="all",
                )
        except Exception as e:
            logger.warning("_register_pattern_claims failed (fail-open): %s", e)

    # ── L2: AI Pattern Discovery / L2：AI 模式发现 ──

    def analyze_patterns(self, *, force: bool = False) -> Optional[PatternInsight]:
        """
        Batch 10: Public API for L2 pattern analysis.
        公开的 L2 模式分析入口，供 Cron 触发器和外部调用使用。

        Args:
            force: If True, skip the min_observations check (e.g., for scheduled analysis).

        Returns:
            PatternInsight if analysis ran, None if skipped.
        """
        total = len(self._records)
        if not force and total < self.config.l2_min_observations:
            logger.info(
                "analyze_patterns skipped: %d/%d observations / 分析跳过：观察不足",
                total, self.config.l2_min_observations,
            )
            return None
        if total == 0:
            logger.info("analyze_patterns skipped: no observations / 分析跳过：无观察数据")
            return None
        self._audit("l2_analysis_triggered", {
            "total_observations": total,
            "trigger": "scheduled" if force else "threshold",
        })
        return self._run_l2_analysis(force=force)

    def _run_l2_analysis(self, *, force: bool = False) -> Optional[PatternInsight]:
        """
        Run L2 pattern analysis (requires sufficient observations).
        运行 L2 模式分析（需要足够的观察数据）。

        Args:
            force: If True, skip the min_observations check.
        """
        total = len(self._records)
        if not force and total < self.config.l2_min_observations:
            logger.info("L2 analysis skipped: only %d/%d observations / L2 分析跳过：观察不足",
                        total, self.config.l2_min_observations)
            return None

        self._last_l2_analysis_count = total

        with self._lock:
            self._stats["l2_analyses"] += 1

        # Try AI analysis first / 先尝试 AI 分析
        if self._ollama and self._ollama.is_available():
            try:
                insight = self._ai_pattern_analysis()
                if insight:
                    return insight
            except Exception as e:
                logger.warning("AI L2 analysis failed, using statistical fallback: %s", e)

        # Statistical fallback / 统计回退
        return self._statistical_pattern_analysis()

    def _ai_pattern_analysis(self) -> Optional[PatternInsight]:
        """Use Qwen to discover patterns / 使用 Qwen 发现模式"""
        # Build summary for AI / 构建 AI 摘要
        rankings = self.get_strategy_rankings()
        regime_metrics = self.get_regime_metrics()

        summary = (
            f"Trade history: {len(self._records)} observations\n"
            f"Strategy rankings (by Sharpe):\n"
        )
        for r in rankings[:10]:
            summary += f"  {r['strategy']}: Sharpe={r['sharpe_ratio']}, WR={r['win_rate']}, trades={r['total_trades']}\n"
        summary += f"\nRegime performance:\n"
        for regime, m in regime_metrics.items():
            summary += f"  {regime}: WR={m['win_rate']}, PnL={m['total_pnl']}, trades={m['trades']}\n"

        system = (
            "You are a quantitative trading analyst. Analyze the following trade data "
            "and identify patterns. Respond with JSON: "
            '{"winning_patterns": ["..."], "losing_patterns": ["..."], '
            '"regime_strategy_matrix": {"regime": {"strategy": win_rate}}}'
        )

        response = self._ollama.generate(summary, system=system, temperature=0.3, max_tokens=1024, think=True)

        if not response.success:
            return None

        try:
            text = response.text.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            result = json.loads(text)
            insight = PatternInsight(
                observations_count=len(self._records),
                winning_patterns=result.get("winning_patterns", []),
                losing_patterns=result.get("losing_patterns", []),
                regime_strategy_matrix=result.get("regime_strategy_matrix", {}),
                source="ai",
            )
        except (json.JSONDecodeError, KeyError):
            return None

        with self._lock:
            self._pattern_insights.append(insight)

        # Send to Strategist / 发送给 Strategist
        if self.bus:
            msg = AgentMessage(
                sender=AgentRole.ANALYST,
                receiver=AgentRole.STRATEGIST,
                message_type=MessageType.PATTERN_INSIGHT,
                priority=5,
                payload=insight.to_dict(),
            )
            self.bus.send(msg)

        self._audit("l2_pattern_insight", insight.to_dict())
        logger.info("L2 AI pattern analysis complete: %d patterns found / L2 AI 模式分析完成",
                     len(insight.winning_patterns) + len(insight.losing_patterns))
        return insight

    def _statistical_pattern_analysis(self) -> PatternInsight:
        """Statistical fallback for pattern analysis / 统计回退模式分析"""
        rankings = self.get_strategy_rankings()
        regime_metrics = self.get_regime_metrics()

        winning_patterns = []
        losing_patterns = []

        for r in rankings:
            wr = r.get("win_rate", 0.0)
            strategy = r.get("strategy", "")
            if wr >= 0.55:
                winning_patterns.append(f"{strategy}: win_rate={wr:.1%}")
            elif wr < 0.35 and r.get("total_trades", 0) >= self.config.min_trades_for_ranking:
                losing_patterns.append(f"{strategy}: win_rate={wr:.1%}")

        # Build regime-strategy matrix / 构建 regime-策略矩阵
        rsm: Dict[str, Dict[str, float]] = {}
        for record in self._records:
            regime = record.regime
            strategy = record.strategy
            if regime not in rsm:
                rsm[regime] = {}
            if strategy not in rsm[regime]:
                rsm[regime][strategy] = 0.0
            if record.is_win:
                rsm[regime][strategy] += 1.0

        # Normalize to win rates / 归一化为胜率
        regime_trade_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for record in self._records:
            regime_trade_counts[record.regime][record.strategy] += 1
        for regime in rsm:
            for strategy in rsm[regime]:
                count = regime_trade_counts[regime][strategy]
                if count > 0:
                    rsm[regime][strategy] = round(rsm[regime][strategy] / count, 4)

        insight = PatternInsight(
            observations_count=len(self._records),
            winning_patterns=winning_patterns,
            losing_patterns=losing_patterns,
            regime_strategy_matrix=rsm,
            source="statistical",
        )

        with self._lock:
            self._pattern_insights.append(insight)

        # Send to Strategist / 发送给 Strategist
        if self.bus:
            msg = AgentMessage(
                sender=AgentRole.ANALYST,
                receiver=AgentRole.STRATEGIST,
                message_type=MessageType.PATTERN_INSIGHT,
                priority=5,
                payload=insight.to_dict(),
            )
            self.bus.send(msg)

        self._audit("l2_pattern_insight", insight.to_dict())
        logger.info("L2 statistical pattern analysis complete / L2 统计模式分析完成")
        return insight

    # ── Audit / 审计 ──

    def _audit(self, event_type: str, data: Any) -> None:
        if self._audit_callback:
            try:
                self._audit_callback(f"analyst_{event_type}", data)
            except Exception as e:
                logger.debug("Audit callback error: %s", e)

    # ── Status / 状态 ──

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "role": AgentRole.ANALYST.value,
                "state": self.state.value,
                "total_records": len(self._records),
                "strategies_tracked": len(self._strategy_stats),
                "regimes_tracked": len(self._regime_stats),
                "pattern_insights": len(self._pattern_insights),
                **dict(self._stats),
            }

    def get_latest_insight(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._pattern_insights:
                return self._pattern_insights[-1].to_dict()
            return None

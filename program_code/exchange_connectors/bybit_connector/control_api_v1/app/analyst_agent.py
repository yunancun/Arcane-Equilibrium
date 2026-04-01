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
import os
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
    # C7 fix: lowered from 200 to 50, overridable via ANALYST_L2_MIN_OBS env var
    # C7 修复：从 200 降至 50，可通过环境变量 ANALYST_L2_MIN_OBS 覆盖
    l2_min_observations: int = int(os.environ.get("ANALYST_L2_MIN_OBS", "50"))
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
        min_observations_for_ai: Optional[int] = None,
    ):
        self.config = config or AnalystConfig()
        # Configurable observation threshold for L2 AI analysis trigger.
        # Only overrides config.l2_min_observations when explicitly provided.
        # 可配置的 L2 AI 分析觸發觀察數閾值。僅在顯式提供時覆蓋 config 值。
        if min_observations_for_ai is not None:
            self.config.l2_min_observations = min_observations_for_ai
        self._min_observations_for_ai: int = self.config.l2_min_observations
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

        # ExperimentLedger: injected externally for hypothesis observation recording
        # 實驗帳本：外部注入，用於記錄模式假設觀測（原則 7：學習平面隔離）
        self._experiment_ledger: Optional[Any] = None

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

    def set_experiment_ledger(self, ledger: Any) -> None:
        """
        注入 ExperimentLedger 實例，供假設觀測記錄使用。
        Inject ExperimentLedger instance for hypothesis observation recording.

        原則 7：ExperimentLedger 屬於學習平面，不影響 live 交易決策。
        Principle 7: ExperimentLedger belongs to learning plane, does not affect live decisions.

        fail-open：ledger 為 None 時，分析繼續正常運行，不記錄觀測。
        fail-open: if ledger is None, analysis continues without recording observations.
        """
        self._experiment_ledger = ledger

    # 已知策略名稱清單，供從 pattern_text 中提取策略名使用
    # Known strategy names used to extract applies_to_strategy from pattern_text
    _KNOWN_STRATEGIES = frozenset([
        "ma_crossover", "grid", "bb_reversion", "bb_breakout", "funding_arb",
    ])

    @staticmethod
    def _extract_strategy_from_pattern(pattern_text: str) -> str:
        """
        Extract a strategy key from pattern text for use as applies_to_strategy.
        從 pattern 文字中提取策略 key，作為 applies_to_strategy 使用。

        Priority:
          1. If a known strategy name appears in the text, return it directly.
          2. Otherwise, derive a stable slug from the first 40 chars of pattern_text.
             This ensures registration still happens (total_registered > 0) while
             never injecting "all" which is silently skipped by StrategistAgent.

        優先順序：
          1. 如果文字包含已知策略名，直接返回。
          2. 否則，從 pattern_text 前 40 字元衍生穩定 slug，確保聲明能被登記。
             絕不回退到 "all"，因為 StrategistAgent._apply_pattern_insight() 明確跳過
             applies_to_strategy=="all" 的聲明，會導致所有聲明靜默丟失。

        StrategistAgent._strategy_preference_weights 使用 .get(strategy, 1.0) 回退，
        因此未知的 slug key 完全安全，不會崩潰。
        StrategistAgent uses .get(strategy, 1.0) fallback, so an unknown slug key
        is completely safe and won't cause any errors.
        """
        lower = pattern_text.lower()
        # 優先：從已知策略名中匹配 / Priority: match against known strategy names
        for strategy in AnalystAgent._KNOWN_STRATEGIES:
            if strategy in lower:
                return strategy
        # 回退：從前 40 字元衍生穩定 slug（去掉空格/特殊字元，轉小寫）
        # Fallback: derive a stable slug from first 40 chars (strip spaces/special chars, lowercase)
        import re as _re
        slug = _re.sub(r"[^a-z0-9_]", "_", lower[:40]).strip("_")
        # 確保 slug 非空且不等於 "all" / Ensure slug is non-empty and not "all"
        return slug if slug and slug != "all" else "generic_pattern"

    def _register_pattern_claims(self, insight: Any) -> None:
        """
        Register winning/losing patterns from insight into TruthSourceRegistry.
        將洞察中的贏/輸模式登記到知識登記表。

        - winning_patterns: registered with confidence derived from observation count.
          贏模式：置信度由觀察數推算。
        - losing_patterns: registered with inverted confidence (fixed 0.4) and
          "losing: " prefix so StrategistAgent can identify them as negative signals.
          輸模式：反轉置信度（固定 0.4），加 "losing: " 前綴，讓 StrategistAgent 識別為負向信號。
        - applies_to_strategy is extracted via _extract_strategy_from_pattern(); this method
          never returns "all" to avoid silent skip in StrategistAgent._apply_pattern_insight().
          applies_to_strategy 通過 _extract_strategy_from_pattern() 提取，
          該方法永不返回 "all"，避免 StrategistAgent 靜默跳過所有聲明。

        Fail-open: any error → log warning, never raises.
        失敗開放：任何異常 → 記錄警告，不向上拋出。
        """
        try:
            n_obs = len(self._records)
            # 置信度上限 0.85（原則 7：AI 輸出永遠不是 FACT）
            # Confidence capped at 0.85 (Principle 7: AI output is never FACT)
            win_confidence = min(0.85, 0.5 + n_obs * 0.001)

            # ── 贏模式登記到 TruthSourceRegistry / Register winning patterns to TruthSourceRegistry ──
            # registry 未注入時跳過此區塊，但後面的 ExperimentLedger 記錄仍會執行
            # Skip this block when registry is not injected; ExperimentLedger recording still runs
            if self._truth_registry is not None:
                for pattern_text in (getattr(insight, "winning_patterns", None) or []):
                    pt_str = str(pattern_text)
                    # 提取策略 key；_extract_strategy_from_pattern 永不返回 "all"
                    # Extract strategy key; _extract_strategy_from_pattern never returns "all"
                    strategy = self._extract_strategy_from_pattern(pt_str)
                    self._truth_registry.register_claim(
                        pattern_text=pt_str,
                        evidence_source="ai",
                        observation_count=n_obs,
                        confidence=win_confidence,
                        applies_to_regime="all",
                        applies_to_strategy=strategy,
                    )

            # 向 ExperimentLedger 記錄贏模式觀測（fail-open，獨立於 truth_registry）
            # Record winning pattern observations to ExperimentLedger (fail-open, independent of truth_registry)
            if self._experiment_ledger is not None:
                self._record_pattern_observations(insight, is_winning=True)

            # ── 輸模式登記到 TruthSourceRegistry / Register losing patterns to TruthSourceRegistry ──
            # 置信度反轉：輸模式固定使用低置信度 0.4，讓 StrategistAgent 降低對應策略偏好
            # Confidence inverted: losing patterns use fixed low confidence 0.4
            # so StrategistAgent reduces preference for those strategies
            losing_confidence = 0.4
            if self._truth_registry is not None:
                for pattern_text in (getattr(insight, "losing_patterns", None) or []):
                    pt_str = str(pattern_text)
                    # 提取策略 key，不使用 "all"
                    # Extract strategy key, never "all"
                    strategy = self._extract_strategy_from_pattern(pt_str)
                    # 加 "losing: " 前綴，讓 StrategistAgent._apply_pattern_insight() 識別為負向信號
                    # Prefix with "losing: " so StrategistAgent identifies it as a negative signal
                    self._truth_registry.register_claim(
                        pattern_text=f"losing: {pt_str}",
                        evidence_source="ai",
                        observation_count=n_obs,
                        confidence=losing_confidence,
                        applies_to_regime="all",
                        applies_to_strategy=strategy,
                    )

            # 向 ExperimentLedger 記錄輸模式觀測（fail-open，獨立於 truth_registry）
            # Record losing pattern observations to ExperimentLedger (fail-open, independent of truth_registry)
            if self._experiment_ledger is not None:
                self._record_pattern_observations(insight, is_winning=False)

        except Exception as e:
            logger.warning("_register_pattern_claims failed (fail-open): %s", e)

    def _record_pattern_observations(self, insight: Any, is_winning: bool) -> None:
        """
        根據分析結果向 ExperimentLedger 記錄觀測。
        Record pattern analysis observations to ExperimentLedger.

        winning patterns → outcome="supporting"
        losing patterns  → outcome="refuting"

        fail-open：單條失敗不傳播，繼續記錄其餘假設。
        fail-open: single failure does not propagate; continue recording other hypotheses.

        原則 7：本方法僅操作學習平面（ExperimentLedger），不影響交易決策。
        Principle 7: This method only operates on the learning plane (ExperimentLedger),
        and does not affect trading decisions.

        Args:
            insight: PatternInsight object from L2 analysis / L2 分析產生的模式洞察對象
            is_winning: True for winning patterns (supporting), False for losing (refuting)
                        True 表示贏模式（支持），False 表示輸模式（反駁）
        """
        # 根據贏/輸確定 outcome 字串 / Determine outcome string based on win/loss
        outcome = "supporting" if is_winning else "refuting"
        try:
            # 取所有活躍假設（PENDING / RUNNING 狀態）/ Get all active (non-concluded) hypotheses
            all_hyps = self._experiment_ledger.get_all_hypotheses()
            for hyp in all_hyps:
                # 只對尚未結案的假設記錄觀測 / Only record for non-concluded hypotheses
                if hyp.status.value in ("PENDING", "RUNNING"):
                    try:
                        self._experiment_ledger.record_observation(hyp.hypothesis_id, outcome)
                    except Exception as e:
                        # fail-open：跳過此假設，繼續處理其餘 / fail-open: skip this hypothesis
                        logger.debug(
                            "ExperimentLedger record_observation skipped hyp=%s: %s",
                            hyp.hypothesis_id, e,
                        )
        except Exception as e:
            # fail-open：不阻塞分析路徑 / fail-open: do not block the analysis path
            logger.warning("_record_pattern_observations failed (fail-open): %s", e)

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

        # 在發送給 Strategist 前，先登記模式聲明到 TruthSourceRegistry（若已注入）
        # Register pattern claims into TruthSourceRegistry before sending to Strategist
        self._register_pattern_claims(insight)

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

        # 在發送給 Strategist 前，先登記模式聲明到 TruthSourceRegistry（若已注入）
        # Register pattern claims into TruthSourceRegistry before sending to Strategist
        self._register_pattern_claims(insight)

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

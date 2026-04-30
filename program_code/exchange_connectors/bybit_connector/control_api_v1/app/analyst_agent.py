"""AnalystAgent: trade-result analysis, learning metrics, and pattern discovery.

Consumes ROUND_TRIP_COMPLETE messages, updates L1 metrics, optionally runs L2
pattern discovery after enough observations, and writes audited analysis output.
Safety invariant: read-only analysis only; it never emits trade instructions.

G3-08-FUP-ANALYST-SPLIT keeps dataclasses in analyst_records.py and pattern
claim helpers in analyst_pattern_claims.py; this module retains AnalystAgent and
re-exports TradeRecord / PatternInsight / AnalystConfig for BWD compatibility.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from typing import Any, Callable, Dict, List, Optional

from .analyst_pattern_claims import (
    KNOWN_STRATEGIES,
    extract_strategy_from_pattern,
    record_pattern_observations,
    register_pattern_claims,
)
# G3-08-FUP-ANALYST-SPLIT P2: dataclasses moved to analyst_records sibling.
# Re-exported below for BWD-compat (tests + strategy_wiring.py rely on
# ``from app.analyst_agent import TradeRecord/PatternInsight/AnalystConfig``).
# G3-08-FUP-ANALYST-SPLIT P2：dataclass 已搬到 analyst_records sibling，
# 此處 re-export 保 BWD-compat（test + strategy_wiring.py 使用
# ``from app.analyst_agent import TradeRecord/PatternInsight/AnalystConfig``）。
from .analyst_records import AnalystConfig, PatternInsight, TradeRecord
from .base_agent import BaseAgent
# G3-08 Phase 4 Sub-task 4-3 — Analyst agent_state invalidation hint
# (env-gated no-op when OPENCLAW_H_STATE_GATEWAY != "1").
# G3-08 Phase 4 Sub-task 4-3 — Analyst agent_state 失效提示
# （env=非 "1" 時為 no-op）。
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
from .llm_call_wrapper import call_ollama_generate, ollama_is_available
from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    MessageBus,
    MessageType,
)

logger = logging.getLogger(__name__)

# Public re-exports for BWD-compat / 公開符號 re-export 保 BWD-compat
__all__ = [
    "AnalystAgent",
    "AnalystConfig",
    "PatternInsight",
    "TradeRecord",
]


# ═══════════════════════════════════════════════════════════════════════════════
# AnalystAgent / 分析师代理
# ═══════════════════════════════════════════════════════════════════════════════

class AnalystAgent(BaseAgent):
    """EX-06 §7 — Trade analysis, learning metrics, and pattern discovery agent.

    L1: Statistical analysis (always running)
    L2: AI pattern discovery (triggered after sufficient observations)

    L1：统计分析（始终运行）
    L2：AI 模式发现（在足够观察后触发）

    Inherits BaseAgent for shared lifecycle + audit skeleton (E5-P1-4).
    繼承 BaseAgent 共享生命週期 + 審計骨架（E5-P1-4）。
    """

    role = AgentRole.ANALYST

    # G3-08-FUP-ANALYST-SPLIT P2: keep class-level attribute alias for
    # callers that read ``AnalystAgent._KNOWN_STRATEGIES`` directly. Source of
    # truth lives in ``analyst_pattern_claims.KNOWN_STRATEGIES``.
    # G3-08-FUP-ANALYST-SPLIT P2：保留 class-level 屬性別名供讀取
    # ``AnalystAgent._KNOWN_STRATEGIES`` 的呼叫者；真值在
    # ``analyst_pattern_claims.KNOWN_STRATEGIES``。
    _KNOWN_STRATEGIES = KNOWN_STRATEGIES

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
        super().__init__(
            role=AgentRole.ANALYST,
            message_bus=message_bus,
            audit_callback=audit_callback,
            cost_tracker=None,  # Analyst's Ollama usage is untracked (legacy behavior).
        )
        self.config = config or AnalystConfig()
        # Configurable observation threshold for L2 AI analysis trigger.
        # Only overrides config.l2_min_observations when explicitly provided.
        # 可配置的 L2 AI 分析觸發觀察數閾值。僅在顯式提供時覆蓋 config 值。
        if min_observations_for_ai is not None:
            self.config.l2_min_observations = min_observations_for_ai
        self._min_observations_for_ai: int = self.config.l2_min_observations
        self._ollama = ollama_client
        self._learning_tier_gate = learning_tier_gate

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

        # GUI heartbeat contract: ms-epoch of most recent observable activity
        # (start / on_message / analyze_trade). 0 means never active — read by
        # ``agents_routes_helpers._build_analyst_card``.
        # GUI 心跳契約：最近一次可觀察活動（start / on_message / analyze_trade）的
        # ms-epoch。0 表示從未活動 — 由 ``_build_analyst_card`` 讀取。
        self._last_heartbeat_ms: int = 0

        # G8-01-FUP-LOSSES-WIRING: optional callback fired on every analyzed
        # trade so downstream consumers (StrategistAgent) can update local
        # ``_stats["consecutive_losses"]`` for CognitiveModulator input.
        # Signature: ``Callable[[float], None]`` — receives ``record.net_pnl``
        # (PnL minus fees) per analyzed round-trip; positive resets, non-positive
        # increments. Strict fail-open: any exception is logged-and-swallowed
        # so analyst hot path is never poisoned (Principle #6 fail-closed,
        # but fail-open here means: bypass downstream wiring, never crash).
        # G8-01-FUP-LOSSES-WIRING：每筆已分析交易觸發的可選 callback，供下游消費者
        # （StrategistAgent）更新自身 ``_stats["consecutive_losses"]`` 作為
        # CognitiveModulator 的輸入。簽名 ``Callable[[float], None]`` —— 接收
        # ``record.net_pnl``（PnL 扣費後）；正值 reset、非正值遞增。嚴格 fail-open：
        # 任何例外 log+吞下，永不污染 analyst hot path（原則 #6 fail-closed，
        # 此處 fail-open 指：略過下游接線、絕不崩潰）。
        self._strategist_loss_callback: Optional[Callable[[float], None]] = None

    # ── Lifecycle / 生命周期 ──
    # pause() inherited from BaseAgent. start/stop override to preserve info log.
    # pause() 繼承自 BaseAgent；start/stop 覆蓋以保留 info log。

    def start(self) -> None:
        super().start()
        # GUI heartbeat contract: stamp on lifecycle start so the roster card
        # leaves "never active" the moment the agent enters RUNNING.
        # GUI 心跳契約：start() 即蓋章，使卡片於 RUNNING 一刻離「從未活動」。
        self._last_heartbeat_ms = int(time.time() * 1000)
        logger.info("AnalystAgent started / 分析师代理已启动")

    def stop(self) -> None:
        super().stop()
        logger.info("AnalystAgent stopped / 分析师代理已停止")

    # ── Message Handler / 消息处理 ──

    def on_message(self, message: AgentMessage) -> None:
        """Handle incoming messages / 处理入站消息"""
        # GUI heartbeat contract (M-1 strict): only RUNNING agents stamp.
        # CLAUDE.md 原則 #10 認知誠實：stopped agent 蓋章 = GUI 矛盾訊號。
        # GUI 心跳契約（M-1 嚴格化）：僅 RUNNING agent 蓋章；非 RUNNING 不蓋章。
        if self.state != AgentState.RUNNING:
            return
        self._last_heartbeat_ms = int(time.time() * 1000)

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
                # U-05: Read fees and param_snapshot with .get() for backward compat.
                # Old round-trip messages without these fields default to 0/empty.
                # U-05：用 .get() 读取费用和参数快照，确保向后兼容。
                fees_paid=float(payload.get("fees_paid", 0.0)),
                param_snapshot=payload.get("param_snapshot", {}),
            )
            self.analyze_trade(record)
        except Exception as e:
            logger.error("Failed to handle round trip: %s / 处理交易回合失败: %s", e, e)
            with self._lock:
                self._stats["errors"] += 1
        # G3-08 Phase 4 Sub-task 4-3: emit invalidation hint outside the lock;
        # env=0 → no-op (zero overhead). Always fired (success or error path)
        # because both bump observable counters (trades_analyzed/l1_updates on
        # success; errors on exception) which Rust h_state_cache should refresh.
        # G3-08 Phase 4 Sub-task 4-3：於鎖外送出失效提示；env=0 為 no-op（零負擔）。
        # 成功與錯誤兩條路徑都送（成功遞增 trades_analyzed/l1_updates；錯誤遞增
        # errors），均為 Rust h_state_cache 應刷新的觀測量。
        _invalidate_h_state_async("agent.analyst.round_trip_analyzed")

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
        # GUI heartbeat contract: analyze_trade is the canonical observable
        # activity for Analyst (direct callers like _handle_round_trip already
        # stamp via on_message; this catches programmatic callers too).
        # GUI 心跳契約：analyze_trade 是 Analyst 的標準觀察活動；on_message
        # 路徑已蓋章，此處覆蓋直接呼叫者（程式化呼叫）。
        self._last_heartbeat_ms = int(time.time() * 1000)
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

        # G8-01-FUP-LOSSES-WIRING: notify Strategist of trade outcome so it can
        # advance ``_stats["consecutive_losses"]`` for next CognitiveModulator
        # tick. Fail-open: any exception is logged-then-swallowed; analyst hot
        # path must not be disrupted by downstream consumer failures.
        # Use ``record.net_pnl`` (PnL minus fees) — pure profitability after
        # transaction costs — to mirror what a human trader would call a "win".
        # G8-01-FUP-LOSSES-WIRING：通知 Strategist 該筆交易結果，使其能更新
        # ``_stats["consecutive_losses"]`` 供下次 CognitiveModulator tick 使用。
        # Fail-open：任何例外被 log 吞下，下游消費者失敗不阻塞 analyst hot path。
        # 用 ``record.net_pnl``（扣費後 PnL）—— 對齊人類交易者「真正獲利」的語意。
        if self._strategist_loss_callback is not None:
            try:
                self._strategist_loss_callback(record.net_pnl)
            except Exception as cb_exc:
                logger.warning(
                    "strategist_loss_callback raised (non-fatal, fail-open): %s / "
                    "strategist_loss_callback 拋出例外（非致命，fail-open）：%s",
                    cb_exc, cb_exc,
                )

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

    def set_strategist_loss_callback(
        self,
        callback: Optional[Callable[[float], None]],
    ) -> None:
        """
        G8-01-FUP-LOSSES-WIRING: inject Strategist consecutive-loss-tracking hook.
        G8-01-FUP-LOSSES-WIRING：注入 Strategist 連續虧損追蹤鉤子。

        After every ``analyze_trade(record)`` invocation Analyst calls this
        callback with ``record.net_pnl`` (post-fee PnL). The downstream consumer
        is expected to update ``StrategistAgent._stats["consecutive_losses"]``
        — incrementing on net_pnl <= 0, resetting to 0 on net_pnl > 0 — so the
        next ``tick_cognitive_modulator`` cycle observes a non-zero input
        (closes G8-01 RFC §3.1 acknowledged limitation).

        每次 ``analyze_trade(record)`` 之後，Analyst 以 ``record.net_pnl``（扣費
        後 PnL）呼叫此 callback。下游消費者（StrategistAgent）負責更新自身
        ``_stats["consecutive_losses"]`` —— net_pnl <= 0 時遞增、net_pnl > 0 時
        歸零，使下次 ``tick_cognitive_modulator`` cycle 取得非零輸入（解 G8-01
        RFC §3.1 acknowledged limitation）。

        Args:
            callback: ``Callable[[float], None]`` taking the trade's net_pnl,
                or ``None`` to clear a previously installed callback.
                ``Callable[[float], None]`` 接受該筆交易 net_pnl，或 ``None``
                以清除先前安裝的 callback。

        Fail-open: callback exceptions are caught at the call site (analyze_trade)
        and logged-then-swallowed; analyst hot path is never disrupted.
        Fail-open：callback 例外於呼叫點（analyze_trade）捕獲後 log 吞下，
        analyst hot path 永不中斷。
        """
        self._strategist_loss_callback = callback

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

    @staticmethod
    def _extract_strategy_from_pattern(pattern_text: str) -> str:
        """
        BWD-compat staticmethod delegator to ``analyst_pattern_claims.extract_strategy_from_pattern``.
        See sibling module for full docstring (G3-08-FUP-ANALYST-SPLIT P2 split).
        BWD-compat 靜態方法委派至 ``analyst_pattern_claims.extract_strategy_from_pattern``，
        詳細文檔見 sibling 模組（G3-08-FUP-ANALYST-SPLIT P2 拆分）。
        """
        return extract_strategy_from_pattern(pattern_text)

    def _register_pattern_claims(self, insight: Any) -> None:
        """
        Delegate to ``analyst_pattern_claims.register_pattern_claims``.
        委派至 ``analyst_pattern_claims.register_pattern_claims``。

        Wraps with current ``len(self._records)`` snapshot + injected
        ``_truth_registry`` / ``_experiment_ledger``; identical fail-open
        semantics to original implementation (G3-08-FUP-ANALYST-SPLIT P2).
        以當前 ``len(self._records)`` snapshot + 注入的
        ``_truth_registry`` / ``_experiment_ledger`` 包裝呼叫；fail-open 語意
        與原始實作完全一致（G3-08-FUP-ANALYST-SPLIT P2）。
        """
        register_pattern_claims(
            insight=insight,
            n_obs=len(self._records),
            truth_registry=self._truth_registry,
            experiment_ledger=self._experiment_ledger,
            logger=logger,
        )

    def _record_pattern_observations(self, insight: Any, is_winning: bool) -> None:
        """
        BWD-compat instance delegator to ``analyst_pattern_claims.record_pattern_observations``.
        Caller chain: ``register_pattern_claims`` already invokes the helper
        directly, so this thin wrapper exists only for any external test that
        may patch / call the original instance method.
        BWD-compat 實例委派至 ``analyst_pattern_claims.record_pattern_observations``。
        呼叫鏈：``register_pattern_claims`` 已直接呼叫 helper，此薄 wrapper
        僅供可能 patch / 呼叫原始 instance method 的外部測試使用。
        """
        if self._experiment_ledger is None:
            return
        record_pattern_observations(
            experiment_ledger=self._experiment_ledger,
            insight=insight,
            is_winning=is_winning,
            logger=logger,
        )

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
        # E5-P1-4: Ollama availability check routed via llm_call_wrapper.
        # E5-P1-4：Ollama 可用性檢查統一走 llm_call_wrapper。
        if ollama_is_available(self._ollama):
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

        # E5-P1-4: routed via llm_call_wrapper.call_ollama_generate (identical defaults).
        # E5-P1-4：通過 llm_call_wrapper.call_ollama_generate（默認參數完全一致）。
        response = call_ollama_generate(
            self._ollama, summary, system=system, temperature=0.3, max_tokens=1024, think=True,
        )

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
    # _audit() inherited from BaseAgent (prefixes event with role.value = "analyst").
    # _audit() 繼承自 BaseAgent（前綴為 role.value = "analyst"）。

    # ── Status / 状态 ──

    # G3-08 Phase 4 Sub-task 4-3: Analyst agent_state snapshot accessor.
    # G3-08 Phase 4 Sub-task 4-3：Analyst agent 狀態 snapshot 存取器。
    def get_analyst_snapshot(self) -> Dict[str, Any]:
        """Thread-safe agent-state snapshot for h_state_cache (PA RFC §2.3, 5 fields).
        Schema parity with Rust ``AgentState.stats: HashMap<String, i64>``: all
        values are int or bool→int (no float / string). Pure-read, takes only
        self._lock; safe from any thread.

        H state cache 用 Analyst 狀態 snapshot（PA RFC §2.3，5 欄位）。
        對齊 Rust ``AgentState.stats: HashMap<String, i64>``，皆 int 或 bool→int。
        純讀、只取 self._lock，任何線程安全。

        Phase 4 invariant: ``experiment_ledger_connected`` reports whether a
        ledger has been injected (``set_experiment_ledger``), not whether the
        ledger is healthy — health belongs to a separate snapshot.
        Phase 4 不變量：``experiment_ledger_connected`` 僅表示是否有注入 ledger
        （``set_experiment_ledger``），不代表 ledger 是否健康；健康狀態另循 snapshot。
        """
        with self._lock:
            return {
                "trades_analyzed": int(self._stats.get("trades_analyzed", 0)),
                "l1_updates": int(self._stats.get("l1_updates", 0)),
                "l2_analyses": int(self._stats.get("l2_analyses", 0)),
                "errors": int(self._stats.get("errors", 0)),
                "experiment_ledger_connected": int(self._experiment_ledger is not None),
            }

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "role": AgentRole.ANALYST.value,
                "state": self.state.value,
                "total_records": len(self._records),
                "strategies_tracked": len(self._strategy_stats),
                "regimes_tracked": len(self._regime_stats),
                "pattern_insights": len(self._pattern_insights),
                # GUI heartbeat contract: ms-epoch surfaced for roster card.
                # GUI 心跳契約：給 roster card 用的 ms-epoch。
                "last_heartbeat_ms": int(self._last_heartbeat_ms),
                **dict(self._stats),
            }

    def get_latest_insight(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            if self._pattern_insights:
                return self._pattern_insights[-1].to_dict()
            return None

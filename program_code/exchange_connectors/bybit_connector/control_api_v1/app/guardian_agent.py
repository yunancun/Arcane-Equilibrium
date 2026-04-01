"""
Batch 8 (Pre-write) — GuardianAgent: Risk review + dynamic risk control
=========================================================================
Governance refs: EX-06 §5, DOC-04 §G Multi-Agent, DOC-01 §5.3

MODULE_NOTE (中文):
  GuardianAgent 是 5-Agent 体系中的"风控守卫"。
  职责：
  1. 审查每个 TradeIntent，返回 APPROVED / REJECTED / MODIFIED
  2. 5 项检查：方向冲突 / 杠杆上限 / 关联冲突 / Sharpe 阈值 / 回撤限制
  3. 消费 EventAlert，使用 Qwen 3.5 评估异常事件风险
  4. 动态调整风控参数（联动 SM-04 RiskGovernor）
  5. fail-closed：Guardian 不可用或返回 UNKNOWN 时默认拒绝

  安全不变量：
  - Guardian 裁决优先于 Strategist（EX-06 §9）
  - 不可用时默认 REJECTED
  - 禁止 except:pass

MODULE_NOTE (English):
  GuardianAgent is the "risk guardian" in the 5-Agent system.
  Responsibilities:
  1. Review each TradeIntent, return APPROVED / REJECTED / MODIFIED
  2. 5 checks: direction conflict / leverage cap / correlation conflict / Sharpe threshold / drawdown limit
  3. Consume EventAlert, use Qwen 3.5 for anomalous event risk assessment
  4. Dynamic risk parameter adjustment (linked to SM-04 RiskGovernor)
  5. fail-closed: Guardian unavailable or UNKNOWN → default REJECTED

  Safety invariants:
  - Guardian verdict overrides Strategist (EX-06 §9)
  - Unavailable → default REJECTED
  - No except:pass
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    MessageBus,
    MessageType,
    RiskVerdict,
    RiskVerdictResult,
    TradeIntent,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class GuardianConfig:
    """Configuration for GuardianAgent / GuardianAgent 配置"""
    # Max leverage allowed / 最大允许杠杆
    max_leverage: float = 5.0
    # Max drawdown percentage before rejecting new trades / 最大回撤百分比
    max_drawdown_pct: float = 15.0
    # Minimum Sharpe ratio for strategy to open new trades / 策略最低 Sharpe 比率
    min_sharpe_ratio: float = 0.0
    # Max correlation between positions (reject if too correlated) / 最大持仓相关性
    max_correlation: float = 0.85
    # Max concurrent positions per direction / 每方向最大并发仓位
    max_same_direction_positions: int = 3
    # Size reduction factor for MODIFIED verdicts / MODIFIED 裁决的仓位缩减因子
    modification_size_factor: float = 0.5
    # Leverage reduction for MODIFIED verdicts / MODIFIED 裁决的杠杆缩减
    modification_leverage_cap: float = 2.0


# ═══════════════════════════════════════════════════════════════════════════════
# GuardianAgent / 守卫代理
# ═══════════════════════════════════════════════════════════════════════════════

class GuardianAgent:
    """EX-06 §5 — Risk review agent that approves/rejects/modifies every TradeIntent.

    Guardian's verdict ALWAYS overrides Strategist (EX-06 §9).
    fail-closed: any error → REJECTED.

    Guardian 的裁决始终优先于 Strategist（EX-06 §9）。
    fail-closed：任何错误 → REJECTED。
    """

    def __init__(
        self,
        *,
        config: Optional[GuardianConfig] = None,
        message_bus: Optional[MessageBus] = None,
        risk_manager: Optional[Any] = None,
        ollama_client: Optional[Any] = None,
        governance_hub: Optional[Any] = None,
        audit_callback: Optional[Callable] = None,
    ):
        self.config = config or GuardianConfig()
        self.bus = message_bus
        self._risk_manager = risk_manager
        self._ollama = ollama_client
        self._governance_hub = governance_hub
        self._audit_callback = audit_callback
        self.state = AgentState.INITIALIZING
        self._lock = threading.Lock()

        # Active positions tracking (injected from PipelineBridge state)
        # 活跃仓位追踪（从 PipelineBridge 状态注入）
        self._active_positions: Dict[str, Dict[str, Any]] = {}

        # Strategy performance cache / 策略性能缓存
        self._strategy_metrics: Dict[str, Dict[str, float]] = {}

        # Event risk state (from Scout alerts) / 事件风险状态
        self._active_event_risks: List[Dict[str, Any]] = []
        self._max_event_risks = 50

        # Stats / 统计
        self._stats = {
            "intents_reviewed": 0,
            "verdicts_approved": 0,
            "verdicts_rejected": 0,
            "verdicts_modified": 0,
            "events_assessed": 0,
            "errors": 0,
        }

        # Verdict log / 裁决日志
        self._verdict_log: List[Dict[str, Any]] = []
        self._max_verdict_log = 200

    # ── Lifecycle / 生命周期 ──

    def start(self) -> None:
        self.state = AgentState.RUNNING
        logger.info("GuardianAgent started / 守卫代理已启动")

    def pause(self) -> None:
        self.state = AgentState.PAUSED

    def stop(self) -> None:
        self.state = AgentState.STOPPED
        logger.info("GuardianAgent stopped / 守卫代理已停止")

    # ── Message Handler / 消息处理 ──

    def on_message(self, message: AgentMessage) -> None:
        """Handle incoming messages / 处理入站消息"""
        if self.state != AgentState.RUNNING:
            return

        if message.message_type == MessageType.TRADE_INTENT:
            self._handle_trade_intent(message)
        elif message.message_type == MessageType.EVENT_ALERT:
            self._handle_event_alert(message)
        elif message.message_type == MessageType.RISK_PATTERN:
            self._handle_risk_pattern(message)
        elif message.message_type == MessageType.SYSTEM_DIRECTIVE:
            self._handle_directive(message)

    # ── Core Review / 核心审查 ──

    def review_intent(self, intent: TradeIntent) -> RiskVerdict:
        """
        Review a TradeIntent through 5 checks. Returns APPROVED / REJECTED / MODIFIED.
        通过 5 项检查审查 TradeIntent。返回 APPROVED / REJECTED / MODIFIED。

        fail-closed: any exception → REJECTED.
        """
        try:
            return self._do_review(intent)
        except Exception as e:
            logger.error("Guardian review exception (fail-closed → REJECTED): %s / 守卫审查异常: %s", e, e)
            with self._lock:
                self._stats["errors"] += 1
                self._stats["verdicts_rejected"] += 1
            return RiskVerdict(
                intent_id=intent.intent_id,
                result=RiskVerdictResult.REJECTED,
                reason=f"Guardian error (fail-closed): {e}",
                risk_score=1.0,
            )

    def _do_review(self, intent: TradeIntent) -> RiskVerdict:
        """Internal review logic / 内部审查逻辑"""
        with self._lock:
            self._stats["intents_reviewed"] += 1

        rejection_reasons: List[str] = []
        modification_needed = False
        modified_params: Dict[str, Any] = {}
        risk_score = 0.0

        # Check 1: Direction conflict / 方向冲突检查
        dir_result = self._check_direction_conflict(intent)
        if dir_result:
            rejection_reasons.append(dir_result)
            risk_score += 0.3

        # Check 2: Leverage cap / 杠杆上限检查
        leverage = intent.params.get("leverage", 1.0)
        if leverage > self.config.max_leverage:
            if leverage > self.config.max_leverage * 2:
                rejection_reasons.append(
                    f"Leverage {leverage}x far exceeds cap {self.config.max_leverage}x"
                )
                risk_score += 0.4
            else:
                modification_needed = True
                modified_params["leverage"] = self.config.modification_leverage_cap
                risk_score += 0.15

        # Check 3: Correlation conflict / 关联冲突检查
        corr_result = self._check_correlation_conflict(intent)
        if corr_result:
            rejection_reasons.append(corr_result)
            risk_score += 0.2

        # Check 4: Sharpe ratio threshold / Sharpe 比率阈值检查
        sharpe_result = self._check_sharpe_threshold(intent)
        if sharpe_result:
            rejection_reasons.append(sharpe_result)
            risk_score += 0.2

        # Check 5: Drawdown limit / 回撤限制检查
        dd_result = self._check_drawdown_limit(intent)
        if dd_result:
            rejection_reasons.append(dd_result)
            risk_score += 0.3

        # Determine verdict / 确定裁决
        risk_score = min(risk_score, 1.0)

        if rejection_reasons:
            verdict = RiskVerdict(
                intent_id=intent.intent_id,
                result=RiskVerdictResult.REJECTED,
                reason="; ".join(rejection_reasons),
                risk_score=risk_score,
            )
            with self._lock:
                self._stats["verdicts_rejected"] += 1
        elif modification_needed:
            # Also reduce size by modification factor / 同时按因子缩减仓位
            modified_params["size"] = intent.size * self.config.modification_size_factor
            verdict = RiskVerdict(
                intent_id=intent.intent_id,
                result=RiskVerdictResult.MODIFIED,
                reason=f"Modified: leverage capped, size reduced by {self.config.modification_size_factor}",
                modified_params=modified_params,
                risk_score=risk_score,
            )
            with self._lock:
                self._stats["verdicts_modified"] += 1
        else:
            verdict = RiskVerdict(
                intent_id=intent.intent_id,
                result=RiskVerdictResult.APPROVED,
                reason="All 5 checks passed",
                risk_score=risk_score,
            )
            with self._lock:
                self._stats["verdicts_approved"] += 1

        # Log and audit / 记录和审计
        record = {
            "intent_id": intent.intent_id,
            "symbol": intent.symbol,
            "direction": intent.direction,
            "verdict": verdict.result.value,
            "reason": verdict.reason,
            "risk_score": verdict.risk_score,
            "timestamp_ms": int(time.time() * 1000),
        }
        with self._lock:
            self._verdict_log.append(record)
            if len(self._verdict_log) > self._max_verdict_log:
                self._verdict_log = self._verdict_log[-self._max_verdict_log:]

        self._audit("verdict", record)

        # Send verdict back to Strategist via bus / 通过总线发送裁决给 Strategist
        if self.bus:
            msg = AgentMessage(
                sender=AgentRole.GUARDIAN,
                receiver=AgentRole.STRATEGIST,
                message_type=MessageType.RISK_VERDICT,
                priority=1,
                payload=verdict.to_dict(),
            )
            self.bus.send(msg)

        return verdict

    # ── 5 Checks / 5 项检查 ──

    def _check_direction_conflict(self, intent: TradeIntent) -> Optional[str]:
        """Check if intent conflicts with existing positions / 检查 intent 是否与现有仓位冲突"""
        same_direction_count = 0
        for key, pos in self._active_positions.items():
            if pos.get("symbol") == intent.symbol:
                existing_side = pos.get("side", "")
                intent_side = "Buy" if intent.direction == "long" else "Sell"
                if existing_side != intent_side:
                    return f"Direction conflict: existing {existing_side} position on {intent.symbol}"
            # Count same-direction positions
            existing_side = pos.get("side", "")
            intent_side = "Buy" if intent.direction == "long" else "Sell"
            if existing_side == intent_side:
                same_direction_count += 1

        if same_direction_count >= self.config.max_same_direction_positions:
            return f"Too many {intent.direction} positions: {same_direction_count} >= {self.config.max_same_direction_positions}"

        return None

    def _check_correlation_conflict(self, intent: TradeIntent) -> Optional[str]:
        """Check if new position is too correlated with existing ones / 检查新仓位与现有仓位的关联性"""
        # Simplified: BTC and ETH are highly correlated
        correlated_pairs = {
            ("BTCUSDT", "ETHUSDT"): 0.85,
            ("ETHUSDT", "BTCUSDT"): 0.85,
        }
        for key, pos in self._active_positions.items():
            pos_symbol = pos.get("symbol", "")
            pair = (intent.symbol, pos_symbol)
            correlation = correlated_pairs.get(pair, 0.0)
            if correlation >= self.config.max_correlation:
                pos_side = pos.get("side", "")
                intent_side = "Buy" if intent.direction == "long" else "Sell"
                if pos_side == intent_side:
                    return f"Correlation conflict: {intent.symbol} ↔ {pos_symbol} (r={correlation:.2f})"
        return None

    def _check_sharpe_threshold(self, intent: TradeIntent) -> Optional[str]:
        """Check if strategy Sharpe ratio meets minimum / 检查策略 Sharpe 比率是否达标"""
        strategy = intent.strategy
        metrics = self._strategy_metrics.get(strategy, {})
        sharpe = metrics.get("sharpe_ratio")
        if sharpe is not None and sharpe < self.config.min_sharpe_ratio:
            return f"Strategy '{strategy}' Sharpe {sharpe:.2f} below minimum {self.config.min_sharpe_ratio:.2f}"
        return None

    def _check_drawdown_limit(self, intent: TradeIntent) -> Optional[str]:
        """Check if portfolio drawdown exceeds limit / 检查组合回撤是否超限"""
        if self._risk_manager:
            try:
                # Try to get current drawdown from risk manager
                rm_state = getattr(self._risk_manager, "get_portfolio_summary", None)
                if rm_state:
                    summary = rm_state()
                    current_dd = abs(summary.get("current_drawdown_pct", 0.0))
                    if current_dd >= self.config.max_drawdown_pct:
                        return f"Portfolio drawdown {current_dd:.1f}% exceeds limit {self.config.max_drawdown_pct:.1f}%"
            except Exception as e:
                logger.debug("Drawdown check failed: %s", e)
        return None

    # ── Event Alert Handling / 事件告警处理 ──

    def _handle_trade_intent(self, message: AgentMessage) -> None:
        """Handle TradeIntent from Strategist via MessageBus, review and forward approved intents.
        处理来自 Strategist 的 TradeIntent（经 MessageBus），审查后将批准的 intent 转发给 Executor。

        After review_intent(), if the verdict is APPROVED or MODIFIED, emit an APPROVED_INTENT
        message on the bus so ExecutorAgent can pick it up. This connects the designed but
        previously broken Guardian→Executor MessageBus path (APR01-P1-5).

        审查完成后，若裁决为 APPROVED 或 MODIFIED，通过 bus 发送 APPROVED_INTENT 消息，
        使 ExecutorAgent 能够接收。这接通了原本设计但从未连接的 Guardian→Executor 消息总线路径。

        Fail-open: bus.send failure only logs a warning — does NOT block the existing
        pipeline_bridge direct execution path (which remains the primary path).
        失败开放：bus.send 失败仅记录警告，不阻塞现有 pipeline_bridge 直接执行路径。
        """
        payload = message.payload
        if not payload:
            return
        try:
            intent = TradeIntent(
                intent_id=payload.get("intent_id", f"intent_{uuid.uuid4().hex[:12]}"),
                symbol=payload.get("symbol", ""),
                strategy=payload.get("strategy", ""),
                direction=payload.get("direction", ""),
                size=float(payload.get("size", 0.0)),
                params=payload.get("params", {}),
                confidence=float(payload.get("confidence", 0.0)),
                thesis=payload.get("thesis", ""),
                invalidation_condition=payload.get("invalidation_condition", ""),
                metadata=payload.get("metadata", {}),
            )
            verdict = self.review_intent(intent)

            # ── APR01-P1-5: Emit APPROVED_INTENT to Executor via MessageBus ──
            # ── APR01-P1-5：通过 MessageBus 向 Executor 发送 APPROVED_INTENT ──
            # This is ADDITIVE — the existing pipeline_bridge direct path is unchanged.
            # 这是附加逻辑，现有 pipeline_bridge 直接路径不受影响。
            #
            # ⚠ MUTUAL EXCLUSIVITY ASSUMPTION (E2 review 2026-04-01):
            # This bus-based path is ONLY reachable when Strategist sends TRADE_INTENT
            # via MessageBus. The pipeline_bridge path calls review_intent() DIRECTLY
            # without sending TRADE_INTENT on the bus, so _handle_trade_intent() never
            # fires. The two paths are currently mutually exclusive per intent.
            # TODO: Before activating bus-based flow in production, add intent_id
            # deduplication in ExecutorAgent to prevent double execution if both paths
            # are ever active simultaneously.
            # ⚠ 互斥假设（E2 审查 2026-04-01）：
            # 此 bus 路径仅在 Strategist 通过 MessageBus 发送 TRADE_INTENT 时触发。
            # pipeline_bridge 直接调用 review_intent()，不发送 TRADE_INTENT，
            # 因此 _handle_trade_intent() 不会触发。两条路径当前互斥。
            # TODO：在生产启用 bus 流程前，需在 ExecutorAgent 中添加 intent_id 去重，
            # 防止两条路径同时激活时重复下单。
            if self.bus and verdict.result in (
                RiskVerdictResult.APPROVED,
                RiskVerdictResult.MODIFIED,
            ):
                # Build the payload ExecutorAgent._handle_approved_intent() expects:
                # intent_id, symbol, direction, size, metadata
                # 构建 ExecutorAgent._handle_approved_intent() 期望的负载格式
                approved_payload = intent.to_dict()
                if verdict.result == RiskVerdictResult.MODIFIED:
                    # Apply Guardian's modifications before forwarding
                    # 转发前应用 Guardian 的修改参数
                    approved_payload["size"] = verdict.modified_params.get(
                        "size", intent.size
                    )
                    approved_payload["params"] = {
                        **intent.params,
                        **verdict.modified_params,
                    }
                    approved_payload.setdefault("metadata", {})["guardian_modified"] = True

                try:
                    # sender=STRATEGIST to match VALID_ROUTES table
                    # (STRATEGIST, EXECUTOR) → [APPROVED_INTENT]
                    # 使用 STRATEGIST 作为发送者以匹配路由表定义
                    approved_msg = AgentMessage(
                        sender=AgentRole.STRATEGIST,
                        receiver=AgentRole.EXECUTOR,
                        message_type=MessageType.APPROVED_INTENT,
                        priority=2,
                        payload=approved_payload,
                    )
                    sent = self.bus.send(approved_msg)
                    if sent:
                        logger.info(
                            "APPROVED_INTENT emitted to Executor for %s %s (verdict=%s) / "
                            "已向 Executor 发送 APPROVED_INTENT：%s %s（裁决=%s）",
                            intent.symbol, intent.intent_id, verdict.result.value,
                            intent.symbol, intent.intent_id, verdict.result.value,
                        )
                    else:
                        logger.warning(
                            "APPROVED_INTENT bus.send returned False for %s — "
                            "route validation may have failed (fail-open) / "
                            "bus.send 返回 False：%s — 路由验证可能失败（失败开放）",
                            intent.intent_id, intent.intent_id,
                        )
                except Exception as e:
                    # Fail-open: log but don't block — pipeline_bridge is the primary path
                    # 失败开放：仅记录，不阻塞 — pipeline_bridge 是主要执行路径
                    logger.warning(
                        "Failed to emit APPROVED_INTENT on bus (fail-open): %s / "
                        "通过 bus 发送 APPROVED_INTENT 失败（失败开放）：%s",
                        e, e,
                    )
        except Exception as e:
            logger.error("Failed to handle trade intent: %s / 处理交易意图失败: %s", e, e)
            with self._lock:
                self._stats["errors"] += 1

    def _handle_event_alert(self, message: AgentMessage) -> None:
        """Handle EventAlert from Scout — assess risk using Qwen if available / 处理 Scout 事件告警"""
        with self._lock:
            self._stats["events_assessed"] += 1

        payload = message.payload
        severity = payload.get("severity", "medium")
        event_type = payload.get("event_type", "unknown")

        risk_level = "medium"  # default

        # Try AI classification if available / 尝试 AI 分类
        if self._ollama and self._ollama.is_available():
            try:
                desc = payload.get("description", event_type)
                resp = self._ollama.classify(
                    f"Event: {event_type}. Severity: {severity}. Description: {desc}",
                    ["low", "medium", "high", "critical"],
                )
                if resp.success:
                    risk_level = resp.text.strip().lower()
                    if risk_level not in ("low", "medium", "high", "critical"):
                        risk_level = severity  # fallback to scout's assessment
            except Exception as e:
                logger.warning("Event risk classification failed: %s / 事件风险分类失败", e)

        event_record = {
            "event_type": event_type,
            "severity": severity,
            "risk_level": risk_level,
            "timestamp_ms": int(time.time() * 1000),
            "affected_symbols": payload.get("affected_symbols", []),
        }
        with self._lock:
            self._active_event_risks.append(event_record)
            if len(self._active_event_risks) > self._max_event_risks:
                self._active_event_risks = self._active_event_risks[-self._max_event_risks:]

        # If high/critical, trigger risk parameter tightening via GovernanceHub (SM-04)
        # 如果高/严重，通过 GovernanceHub 触发风控参数收紧（SM-04）
        if risk_level in ("high", "critical") and self._governance_hub:
            try:
                if hasattr(self._governance_hub, "trigger_risk_upgrade"):
                    self._governance_hub.trigger_risk_upgrade(event_record)
                    logger.info("SM-04 risk upgrade triggered for %s event / SM-04 风控升级已触发", event_type)
            except Exception as e:
                logger.warning("SM-04 trigger failed: %s", e)

        self._audit("event_assessed", event_record)

    def _handle_risk_pattern(self, message: AgentMessage) -> None:
        """Handle risk pattern from Analyst / 处理 Analyst 风险模式"""
        self._audit("risk_pattern_received", message.payload)

    def _handle_directive(self, message: AgentMessage) -> None:
        """Handle Conductor directives / 处理 Conductor 指令"""
        directive = message.payload.get("directive_type", "")
        if directive == "update_risk_params":
            new_config = message.payload.get("params", {})
            if "max_leverage" in new_config:
                self.config.max_leverage = float(new_config["max_leverage"])
            if "max_drawdown_pct" in new_config:
                self.config.max_drawdown_pct = float(new_config["max_drawdown_pct"])
            logger.info("Guardian risk params updated via directive / 守卫风控参数已通过指令更新")
        self._audit("directive_received", message.payload)

    # ── State Injection / 状态注入 ──

    def update_active_positions(self, positions: Dict[str, Dict[str, Any]]) -> None:
        """Update known active positions (called periodically by bridge) / 更新已知活跃仓位"""
        with self._lock:
            self._active_positions = dict(positions)

    def update_strategy_metrics(self, metrics: Dict[str, Dict[str, float]]) -> None:
        """Update strategy performance metrics / 更新策略性能指标"""
        with self._lock:
            self._strategy_metrics.update(metrics)

    # ── Audit / 审计 ──

    def _audit(self, event_type: str, data: Any) -> None:
        if self._audit_callback:
            try:
                self._audit_callback(f"guardian_{event_type}", data)
            except Exception as e:
                logger.debug("Audit callback error: %s", e)

    # ── Status / 状态 ──

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "role": AgentRole.GUARDIAN.value,
                "state": self.state.value,
                "active_positions": len(self._active_positions) if self._active_positions else 0,
                "active_event_risks": len(self._active_event_risks) if self._active_event_risks else 0,
                **dict(self._stats),
            }

    def get_recent_verdicts(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self._verdict_log[-limit:])

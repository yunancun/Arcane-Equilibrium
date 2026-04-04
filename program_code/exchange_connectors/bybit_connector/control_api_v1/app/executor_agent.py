"""
Batch 11 (Pre-write) — ExecutorAgent: Order execution wrapper + quality feedback
==================================================================================
Governance refs: EX-06 §6, DOC-04 §G Multi-Agent

MODULE_NOTE (中文):
  ExecutorAgent 是 5-Agent 体系中的"执行者"。
  职责：
  1. 消费 APPROVED_INTENT（经 Guardian 批准的 intent）
  2. 调用 PaperTradingEngine.submit_order() 执行
  3. 产出 EXECUTION_REPORT（含滑点、填充时间、实际价格 vs 预期价格）
  4. 开仓后触发创建交易所条件单的回调接口（具体实现留给 Batch 11）

  安全不变量：
  - system_mode = read_only 不变
  - fail-closed：执行异常时记录错误但不崩溃
  - 所有执行结果写入审计日志
  - 仅执行经 Guardian 批准的 intent

MODULE_NOTE (English):
  ExecutorAgent is the "executor" in the 5-Agent system.
  Responsibilities:
  1. Consume APPROVED_INTENT (Guardian-approved intents)
  2. Call PaperTradingEngine.submit_order() for execution
  3. Produce EXECUTION_REPORT (slippage, fill time, actual vs expected price)
  4. Trigger exchange conditional order creation callback after opening (Batch 11)

  Safety invariants:
  - system_mode = read_only (unchanged)
  - fail-closed: execution errors logged but don't crash
  - All execution results audited
  - Only execute Guardian-approved intents
"""

from __future__ import annotations

import collections
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
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Data Structures / 数据结构
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ExecutionReport:
    """Execution quality report / 执行质量报告"""
    report_id: str = field(default_factory=lambda: f"exec_{uuid.uuid4().hex[:12]}")
    intent_id: str = ""
    symbol: str = ""
    side: str = ""
    requested_qty: float = 0.0
    filled_qty: float = 0.0
    expected_price: float = 0.0
    actual_price: float = 0.0
    slippage_bps: float = 0.0  # basis points
    fill_time_ms: float = 0.0
    success: bool = False
    error: str = ""
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "intent_id": self.intent_id,
            "symbol": self.symbol,
            "side": self.side,
            "requested_qty": self.requested_qty,
            "filled_qty": self.filled_qty,
            "expected_price": self.expected_price,
            "actual_price": self.actual_price,
            "slippage_bps": self.slippage_bps,
            "fill_time_ms": self.fill_time_ms,
            "success": self.success,
            "error": self.error,
            "timestamp_ms": self.timestamp_ms,
            "metadata": self.metadata,
        }


@dataclass
class ExecutorConfig:
    """Configuration for ExecutorAgent / ExecutorAgent 配置"""
    # Maximum slippage tolerance (bps) before flagging / 最大滑点容忍度
    max_slippage_bps: float = 50.0
    # Maximum fill time before flagging (ms) / 最大填充时间
    max_fill_time_ms: float = 5000.0
    # Maximum execution reports to keep / 最大保留的执行报告数
    max_reports: int = 1000
    # ARCH-1: Intent dedup window (seconds) — reject duplicate intent_ids within this window
    # ARCH-1：intent 去重窗口（秒）— 在此窗口內拒絕重複的 intent_id
    dedup_window_seconds: float = 10.0
    # Callback for exchange conditional order creation (set externally)
    # 交易所条件单创建回调（外部设置）


# ═══════════════════════════════════════════════════════════════════════════════
# ExecutorAgent / 执行者代理
# ═══════════════════════════════════════════════════════════════════════════════

class ExecutorAgent:
    """EX-06 §6 — Order execution wrapper with quality feedback.

    Only executes Guardian-approved intents. Provides execution quality metrics
    (slippage, fill time) back to the system.

    仅执行 Guardian 批准的 intent。提供执行质量指标反馈。
    """

    def __init__(
        self,
        *,
        config: Optional[ExecutorConfig] = None,
        message_bus: Optional[MessageBus] = None,
        paper_engine: Optional[Any] = None,
        audit_callback: Optional[Callable] = None,
        governance_hub: Optional[Any] = None,
    ):
        """
        Initialize ExecutorAgent with optional GovernanceHub for Decision Lease acquisition.
        初始化 ExecutorAgent，支持可選的 GovernanceHub 用於 Decision Lease 申請。

        governance_hub: If provided, acquire_lease() will be called before any submit_order().
                        This enforces principle 3: AI output ≠ immediate command.
        governance_hub：若提供，執行訂單前會先調用 acquire_lease()。
                        這強制落實根原則 3：AI 輸出不等於即時命令。
        """
        self.config = config or ExecutorConfig()
        self.bus = message_bus
        self._paper_engine = paper_engine
        self._audit_callback = audit_callback
        # GovernanceHub for Decision Lease — principle 3 enforcement
        # GovernanceHub 用於 Decision Lease 申請，落實根原則 3
        self._governance_hub = governance_hub
        self.state = AgentState.INITIALIZING
        self._lock = threading.Lock()

        # Conditional order callback (Batch 11: exchange stop-loss orders)
        # 条件单回调（Batch 11：交易所止损单）
        self._conditional_order_callback: Optional[Callable] = None

        # Execution reports / 执行报告
        self._reports: List[ExecutionReport] = []

        # Market prices (injected periodically) / 市场价格
        self._market_prices: Dict[str, float] = {}

        # ARCH-1: Intent dedup — prevent double execution if both bus + direct paths fire
        # ARCH-1：intent 去重 — 防止 bus 路徑和直接路徑同時觸發時雙重執行
        self._recent_intent_ids: collections.OrderedDict = collections.OrderedDict()

        # Stats / 统计
        self._stats = {
            "intents_received": 0,
            "intents_deduped": 0,
            "executions_attempted": 0,
            "executions_success": 0,
            "executions_failed": 0,
            "total_slippage_bps": 0.0,
            "errors": 0,
        }

    # ── Lifecycle / 生命周期 ──

    def start(self) -> None:
        self.state = AgentState.RUNNING
        logger.info("ExecutorAgent started / 执行者代理已启动")

    def pause(self) -> None:
        self.state = AgentState.PAUSED

    def stop(self) -> None:
        self.state = AgentState.STOPPED
        logger.info("ExecutorAgent stopped / 执行者代理已停止")

    # ── Injection / 注入 ──

    def set_conditional_order_callback(self, callback: Callable) -> None:
        """Set callback for exchange conditional orders (Batch 11) / 设置条件单回调"""
        self._conditional_order_callback = callback

    def update_market_prices(self, prices: Dict[str, float]) -> None:
        """Update current market prices / 更新当前市场价格"""
        with self._lock:
            self._market_prices.update(prices)

    def _check_and_record_intent(self, intent_id: str) -> bool:
        """Check if intent_id is new (returns True) or duplicate (returns False).
        Also prunes stale entries beyond dedup window (ARCH-1).
        检查 intent_id 是否为新（返回 True）或重复（返回 False），并清理过期条目。"""
        now = time.time()
        cutoff = now - self.config.dedup_window_seconds
        with self._lock:
            # Prune expired entries / 清理过期条目
            while self._recent_intent_ids:
                oldest_key, oldest_ts = next(iter(self._recent_intent_ids.items()))
                if oldest_ts < cutoff:
                    self._recent_intent_ids.pop(oldest_key)
                else:
                    break
            # Check duplicate / 检查重复
            if intent_id in self._recent_intent_ids:
                return False
            # Record new intent / 记录新 intent
            self._recent_intent_ids[intent_id] = now
            return True

    # ── Message Handler / 消息处理 ──

    def on_message(self, message: AgentMessage) -> None:
        """Handle incoming messages / 处理入站消息"""
        if self.state != AgentState.RUNNING:
            return

        if message.message_type == MessageType.APPROVED_INTENT:
            self._handle_approved_intent(message)
        elif message.message_type == MessageType.SYSTEM_DIRECTIVE:
            self._handle_directive(message)

    def _handle_approved_intent(self, message: AgentMessage) -> None:
        """Execute a Guardian-approved intent with dedup safety (ARCH-1).
        执行 Guardian 批准的 intent，含去重安全檢查。"""
        with self._lock:
            self._stats["intents_received"] += 1

        payload = message.payload
        if not payload:
            logger.warning("Empty approved intent payload / 空的批准 intent 负载")
            return

        intent_id = payload.get("intent_id", "unknown")
        symbol = payload.get("symbol", "")
        direction = payload.get("direction", "")
        size = float(payload.get("size", 0.0))

        # ARCH-1: Dedup check — reject if intent_id was already executed within window
        # ARCH-1：去重檢查 — 若 intent_id 在窗口內已執行則拒絕
        if intent_id != "unknown" and not self._check_and_record_intent(intent_id):
            with self._lock:
                self._stats["intents_deduped"] += 1
            logger.warning(
                "DEDUP: intent_id=%s already executed within window, skipping "
                "/ 去重：intent_id=%s 在窗口內已執行，跳過",
                intent_id, intent_id,
            )
            return

        if not symbol or not direction or size <= 0:
            logger.warning("Invalid approved intent: symbol=%s dir=%s size=%s", symbol, direction, size)
            with self._lock:
                self._stats["errors"] += 1
            return

        side = "Buy" if direction == "long" else "Sell"

        report = self.execute_order(
            intent_id=intent_id,
            symbol=symbol,
            side=side,
            qty=size,
            metadata=payload.get("metadata", {}),
        )

        # Send EXECUTION_REPORT to Analyst / 发送执行报告给 Analyst
        if self.bus and report:
            msg = AgentMessage(
                sender=AgentRole.EXECUTOR,
                receiver=AgentRole.ANALYST,
                message_type=MessageType.EXECUTION_REPORT,
                priority=4,
                payload=report.to_dict(),
            )
            self.bus.send(msg)

    def _handle_directive(self, message: AgentMessage) -> None:
        """Handle Conductor directives / 处理 Conductor 指令"""
        self._audit("directive_received", message.payload)

    # ── Core Execution / 核心执行 ──

    def execute_order(
        self,
        *,
        intent_id: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str = "market",
        price: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionReport:
        """
        Execute an order through PaperTradingEngine, after acquiring a Decision Lease.
        通過 PaperTradingEngine 執行訂單，執行前必須先取得 Decision Lease。

        Principle 3 enforcement: Guardian approval (quality gate) ≠ Decision Lease (temporal
        authorization). Both control layers must be satisfied before execution proceeds.
        根原則 3 落實：Guardian 批准（質量門）≠ Decision Lease（時效授權）。
        兩個控制層都必須通過，才允許執行訂單。

        fail-closed: If governance_hub is present but acquire_lease() returns None,
        execution is rejected. Missing governance_hub is fail-open (backward compat).
        失敗默認收縮：若 governance_hub 存在但 acquire_lease() 返回 None，
        則拒絕執行。無 governance_hub 時允許通過（向後兼容）。
        """
        start_time = time.time()

        with self._lock:
            self._stats["executions_attempted"] += 1
            expected_price = self._market_prices.get(symbol, 0.0)

        # ── Decision Lease acquisition — principle 3: AI output ≠ immediate command ──
        # ── Decision Lease 申請 — 根原則 3：AI 輸出不等於即時命令 ──
        # Guardian approval is a quality gate; the lease provides temporal authorization.
        # Both layers are independent and must both pass before execution.
        # Guardian 批准是質量門；Lease 提供時效授權。兩層獨立，必須同時通過。
        lease_id: Optional[str] = None
        if self._governance_hub is not None:
            lease_id = self._governance_hub.acquire_lease(
                intent_id=intent_id,
                scope="TRADE_ENTRY",
                ttl_seconds=30.0,
            )
            if lease_id is None:
                # fail-closed: lease acquisition failed → reject execution
                # Reasons: hub disabled, not authorized, auth doesn't permit TRADE_ENTRY,
                # or hub is in FROZEN mode. Never proceed without temporal authorization.
                # 失敗默認收縮：lease 申請失敗 → 拒絕執行。
                # 原因可能是：hub 禁用、未授權、auth 不允許 TRADE_ENTRY、或 FROZEN 模式。
                # 無時效授權絕不允許下單。
                logger.warning(
                    "Decision Lease acquisition failed for intent %s symbol %s — "
                    "rejecting execution (fail-closed, principle 3) / "
                    "Decision Lease 申請失敗，intent=%s symbol=%s — "
                    "拒絕執行（失敗默認收縮，根原則 3）",
                    intent_id, symbol, intent_id, symbol,
                )
                report = ExecutionReport(
                    intent_id=intent_id,
                    symbol=symbol,
                    side=side,
                    requested_qty=qty,
                    expected_price=expected_price,
                    success=False,
                    error="governance_lease_acquisition_failed",
                    metadata=metadata or {},
                )
                with self._lock:
                    self._stats["executions_failed"] += 1
                    self._stats["errors"] += 1
                self._store_report(report)
                return report

        if not self._paper_engine:
            report = ExecutionReport(
                intent_id=intent_id,
                symbol=symbol,
                side=side,
                requested_qty=qty,
                expected_price=expected_price,
                success=False,
                error="No paper engine available",
            )
            with self._lock:
                self._stats["executions_failed"] += 1
                self._stats["errors"] += 1
            self._store_report(report)
            return report

        try:
            result = self._paper_engine.submit_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                qty=qty,
                price=price,
                market_prices=dict(self._market_prices),
            )

            fill_time_ms = (time.time() - start_time) * 1000
            rejected_reason = result.get("rejected_reason") if isinstance(result, dict) else None
            order = result.get("order", {}) if isinstance(result, dict) else {}

            if rejected_reason:
                report = ExecutionReport(
                    intent_id=intent_id,
                    symbol=symbol,
                    side=side,
                    requested_qty=qty,
                    expected_price=expected_price,
                    fill_time_ms=fill_time_ms,
                    success=False,
                    error=f"Order rejected: {rejected_reason}",
                    metadata=metadata or {},
                )
                with self._lock:
                    self._stats["executions_failed"] += 1
            else:
                actual_price = float(order.get("avg_fill_price", expected_price) or expected_price)
                filled_qty = float(order.get("filled_qty", qty) or qty)

                # Calculate slippage in basis points / 计算滑点（基点）
                slippage_bps = 0.0
                if expected_price > 0 and actual_price > 0:
                    slippage_bps = abs(actual_price - expected_price) / expected_price * 10000

                report = ExecutionReport(
                    intent_id=intent_id,
                    symbol=symbol,
                    side=side,
                    requested_qty=qty,
                    filled_qty=filled_qty,
                    expected_price=expected_price,
                    actual_price=actual_price,
                    slippage_bps=round(slippage_bps, 2),
                    fill_time_ms=round(fill_time_ms, 2),
                    success=True,
                    metadata=metadata or {},
                )
                with self._lock:
                    self._stats["executions_success"] += 1
                    self._stats["total_slippage_bps"] += slippage_bps

                # Trigger conditional order callback if available (Batch 11)
                # 触发条件单回调（Batch 11）
                if self._conditional_order_callback and report.success:
                    try:
                        self._conditional_order_callback(symbol, side, actual_price, filled_qty)
                    except Exception as e:
                        logger.warning("Conditional order callback failed: %s / 条件单回调失败", e)

        except Exception as e:
            fill_time_ms = (time.time() - start_time) * 1000
            # Log full exception details server-side; expose only a generic message
            # to the caller to prevent dynamic exception string leaks (A5 fix).
            # 服务端记录完整异常；对调用方仅返回通用消息，防止动态异常字符串泄漏。
            logger.error("ExecutorAgent execution error: %s", e, exc_info=True)
            report = ExecutionReport(
                intent_id=intent_id,
                symbol=symbol,
                side=side,
                requested_qty=qty,
                expected_price=expected_price,
                fill_time_ms=round(fill_time_ms, 2),
                success=False,
                error="Execution failed — see server logs",
                metadata=metadata or {},
            )
            with self._lock:
                self._stats["executions_failed"] += 1
                self._stats["errors"] += 1

        self._store_report(report)
        return report

    # ── Report Storage / 报告存储 ──

    def _store_report(self, report: ExecutionReport) -> None:
        """Store and audit an execution report / 存储并审计执行报告"""
        with self._lock:
            self._reports.append(report)
            if len(self._reports) > self.config.max_reports:
                self._reports = self._reports[-self.config.max_reports:]
        self._audit("execution_report", report.to_dict())

    # ── Audit / 审计 ──

    def _audit(self, event_type: str, data: Any) -> None:
        if self._audit_callback:
            try:
                self._audit_callback(f"executor_{event_type}", data)
            except Exception as e:
                logger.debug("Audit callback error: %s", e)

    # ── Status / 状态 ──

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            avg_slippage = 0.0
            if self._stats["executions_success"] > 0:
                avg_slippage = self._stats["total_slippage_bps"] / self._stats["executions_success"]
            return {
                "role": AgentRole.EXECUTOR.value,
                "state": self.state.value,
                "total_reports": len(self._reports),
                "avg_slippage_bps": round(avg_slippage, 2),
                **dict(self._stats),
            }

    def get_recent_reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._reports[-limit:]]

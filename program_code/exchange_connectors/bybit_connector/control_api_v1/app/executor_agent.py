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
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .base_agent import BaseAgent
# W-AUDIT-9 T3 — graduated canary 5-stage enum（mirror Rust）。
# 用於 stage-aware ``canary_stage_provider``；舊 ``shadow_mode_provider``
# 仍保留為 backward-compat lambda（Stage 0 → True；Stage ≥ 1 → False）。
from .executor_config_cache import CanaryStage
# G3-08 Phase 4 Sub-task 4-4 — Executor agent_state invalidation hint.
# env-gated no-op when OPENCLAW_H_STATE_GATEWAY != "1" (zero overhead).
# G3-08 Phase 4 Sub-task 4-4 — Executor agent_state 失效提示。
# OPENCLAW_H_STATE_GATEWAY != "1" 時 no-op，零負擔。
from .h_state_invalidator import invalidate_async as _invalidate_h_state_async
from .multi_agent_framework import (
    AgentMessage,
    AgentRole,
    AgentState,
    MessageBus,
    MessageType,
)

logger = logging.getLogger(__name__)


def _resolve_execution_engine(metadata: Optional[Dict[str, Any]]) -> str:
    candidates: list[Any] = []
    if isinstance(metadata, dict):
        candidates.extend(
            [
                metadata.get("engine"),
                metadata.get("engine_mode"),
                metadata.get("runtime_engine"),
                metadata.get("pipeline_engine"),
            ]
        )
    candidates.extend(
        [
            os.environ.get("OPENCLAW_EXECUTOR_DEFAULT_ENGINE"),
            os.environ.get("OPENCLAW_EXECUTOR_CACHE_ENGINE"),
        ]
    )
    for candidate in candidates:
        engine = _normalize_execution_engine(candidate)
        if engine is not None:
            return engine
    return "paper"


def _normalize_execution_engine(value: Any) -> Optional[str]:
    if value is None:
        return None
    engine = str(value).strip().lower()
    if engine == "live_demo":
        return "live"
    if engine in {"paper", "demo", "live"}:
        return engine
    return None


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

class ExecutorAgent(BaseAgent):
    """EX-06 §6 — Order execution wrapper with quality feedback.

    Only executes Guardian-approved intents. Provides execution quality metrics
    (slippage, fill time) back to the system.

    仅执行 Guardian 批准的 intent。提供执行质量指标反馈。

    Inherits BaseAgent for shared lifecycle + audit skeleton (E5-P1-4).
    繼承 BaseAgent 共享生命週期 + 審計骨架（E5-P1-4）。
    """

    role = AgentRole.EXECUTOR

    def __init__(
        self,
        *,
        config: Optional[ExecutorConfig] = None,
        message_bus: Optional[MessageBus] = None,
        paper_engine: Optional[Any] = None,
        audit_callback: Optional[Callable] = None,
        governance_hub: Optional[Any] = None,
        shadow_mode_provider: Optional[Callable[..., bool]] = None,
        canary_stage_provider: Optional[Callable[..., "CanaryStage"]] = None,
        event_store: Optional[Any] = None,
    ):
        """
        Initialize ExecutorAgent with optional GovernanceHub for Decision Lease acquisition.
        初始化 ExecutorAgent，支援可選的 GovernanceHub 用於 Decision Lease 申請。

        governance_hub: 若提供，執行訂單前會先調用 acquire_lease()。
                        這強制落實根原則 3：AI 輸出不等於即時命令。

        shadow_mode_provider（legacy backward-compat）：callable，每次呼叫回傳
            當前 ``shadow_mode`` 旗標。當 ``canary_stage_provider`` 同時提供
            時，後者優先；否則 fall back 此 provider（投影為 stage：True →
            Stage 0，False → Stage 1）。``None``（測試/獨立使用）時不使用匿名
            fallback；讀取時視為 provider unavailable 並 fail-close 到
            Stage 0（``shadow_mode=True`` legacy projection）。

        canary_stage_provider（W-AUDIT-9 T3 SoT）：callable，每次呼叫回傳當前
            ``CanaryStage`` enum（per AMD-2026-05-09-03 §2.1）。優先於
            ``shadow_mode_provider``。``None``（測試/獨立使用）時 fall back
            到 ``shadow_mode_provider``（如有）；雙 None → fail-closed Stage 0。

        invariant 9（**critical**, TODO v19 §5）：
            cache miss / IPC failure / schema fail / provider exception
            → Stage 0（**不是** Stage 1）。break 即雞蛋死循環復活。
        """
        super().__init__(
            role=AgentRole.EXECUTOR,
            message_bus=message_bus,
            audit_callback=audit_callback,
            cost_tracker=None,  # Executor does not invoke LLMs.
            event_store=event_store,
        )
        self.config = config or ExecutorConfig()
        self._paper_engine = paper_engine
        # GovernanceHub for Decision Lease — principle 3 enforcement
        # GovernanceHub 用於 Decision Lease 申請，落實根原則 3
        self._governance_hub = governance_hub
        # G3-03 Phase B + W-AUDIT-9 T3：shadow_mode 改為 runtime provider 提供。
        # `_canary_stage_provider` 為 W-AUDIT-9 T3 stage-aware SoT 路徑；
        # `_shadow_mode_provider` 保留為 backward-compat（legacy bool projection）。
        # 無 provider 時 _read_canary_stage() / _read_shadow_mode() 顯式
        # fail-closed Stage 0，不放入隱性 callable fallback。
        self._shadow_mode_provider: Optional[Callable[..., bool]] = shadow_mode_provider
        self._canary_stage_provider: Optional[Callable[..., "CanaryStage"]] = canary_stage_provider
        self._shadow_mode_provider_missing_warned: bool = False
        self._canary_stage_provider_missing_warned: bool = False

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

        # GUI heartbeat contract: ms-epoch of most recent observable activity
        # (start / on_message). 0 means never active — read by
        # ``agents_routes_helpers._build_executor_card``.
        # GUI 心跳契約：最近一次可觀察活動（start / on_message）的 ms-epoch。
        # 0 表示從未活動 — 由 ``_build_executor_card`` 讀取。
        self._last_heartbeat_ms: int = 0

    # ── G3-08 Phase 4 Sub-task 4-4: agent_state snapshot accessor ──

    def get_executor_snapshot(self) -> Dict[str, Any]:
        """Executor agent-state snapshot for h_state_cache (PA RFC §2.4, 9 fields).

        Schema parity with Rust ``AgentState.stats: HashMap<String, i64>``:
        all values are int (or bool→int). Pure-read, takes only ``self._lock``
        for the stats / dedup buffer; safe from any thread.

        Schema (PA RFC §2.4):
          intents_received / intents_deduped / executions_attempted /
          executions_success / executions_failed / total_slippage_bps (cast int) /
          errors / recent_intent_id_size / shadow_mode (bool→int via
          ``_read_shadow_mode``).

        NOTE — snapshot vs ConfigStore SSOT:
          ``shadow_mode`` is pulled via ``self._read_shadow_mode()`` (G3-03
          ConfigStore provider backed by Rust ``RiskConfig.executor.shadow_mode``).
          That cache remains the single source of truth for the live flag —
          this snapshot is a *read-through observation* for h_state_cache, not
          a writable copy. Provider call is performed *outside* ``self._lock``
          to avoid a possible deadlock with ``ExecutorConfigCache`` internal
          lock; provider exception → fail-closed to ``shadow_mode=1`` per
          CLAUDE.md §二 原則 #6.

        snapshot 與 ConfigStore SSOT 區分：
          ``shadow_mode`` 透過 ``self._read_shadow_mode()``（G3-03 ConfigStore
          provider，背後是 Rust ``RiskConfig.executor.shadow_mode``）取；該 cache
          仍為 live flag 的唯一真實來源 —— 本 snapshot 僅為 h_state_cache 的
          *讀通觀察*，非可寫副本。provider 呼叫於 ``self._lock`` 外執行，
          避免與 ``ExecutorConfigCache`` 內部 lock 死鎖；provider 例外
          → fail-closed 為 ``shadow_mode=1``（CLAUDE.md §二 原則 #6）。
        """
        with self._lock:
            snapshot: Dict[str, Any] = {
                "intents_received": int(self._stats.get("intents_received", 0)),
                "intents_deduped": int(self._stats.get("intents_deduped", 0)),
                "executions_attempted": int(self._stats.get("executions_attempted", 0)),
                "executions_success": int(self._stats.get("executions_success", 0)),
                "executions_failed": int(self._stats.get("executions_failed", 0)),
                # ``total_slippage_bps`` is float in self._stats; cast int for
                # Rust HashMap<String, i64> parity (Phase 4 invariant).
                # ``total_slippage_bps`` 在 _stats 為 float；轉 int 對齊 Rust。
                "total_slippage_bps": int(self._stats.get("total_slippage_bps", 0.0)),
                "errors": int(self._stats.get("errors", 0)),
                "recent_intent_id_size": int(len(self._recent_intent_ids)),
            }
        # provider call OUTSIDE self._lock to avoid possible deadlock with
        # ExecutorConfigCache internal lock (G3-03 Phase B).
        # provider 呼叫於 self._lock 外，避與 ExecutorConfigCache 內部 lock 死鎖。
        snapshot["shadow_mode"] = int(self._read_shadow_mode())
        return snapshot

    # ── Lifecycle / 生命周期 ──
    # pause() inherited from BaseAgent. start/stop override to preserve info log.
    # pause() 繼承自 BaseAgent；start/stop 覆蓋以保留 info log。

    def start(self) -> None:
        super().start()
        # GUI heartbeat contract: stamp on lifecycle start so the roster card
        # leaves "never active" the moment the agent enters RUNNING.
        # GUI 心跳契約：start() 即蓋章，使卡片於 RUNNING 一刻離「從未活動」。
        self._last_heartbeat_ms = int(time.time() * 1000)
        logger.info("ExecutorAgent started / 执行者代理已启动")

    def stop(self) -> None:
        super().stop()
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
        # GUI heartbeat contract (M-1 strict): only RUNNING agents stamp.
        # CLAUDE.md 原則 #10 認知誠實：stopped agent 蓋章 = GUI 矛盾訊號。
        # GUI 心跳契約（M-1 嚴格化）：僅 RUNNING agent 蓋章；非 RUNNING 不蓋章。
        if self.state != AgentState.RUNNING:
            return
        self._last_heartbeat_ms = int(time.time() * 1000)

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
            _invalidate_h_state_async("agent.executor.intent_empty")
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
            _invalidate_h_state_async("agent.executor.intent_deduped")
            return

        if not symbol or not direction or size <= 0:
            logger.warning("Invalid approved intent: symbol=%s dir=%s size=%s", symbol, direction, size)
            with self._lock:
                self._stats["errors"] += 1
            _invalidate_h_state_async("agent.executor.intent_invalid")
            return

        side = "Buy" if direction == "long" else "Sell"

        report = self.execute_order(
            intent_id=intent_id,
            symbol=symbol,
            side=side,
            qty=size,
            metadata=payload.get("metadata", {}),
        )

        # G3-08 Phase 4 Sub-task 4-4: invalidate h_state_cache hint after the
        # execution settles (success or failure). env=0 → fire-and-forget no-op.
        # G3-08 Phase 4 Sub-task 4-4：執行落地後（成功 / 失敗）發出
        # h_state_cache 失效提示；env=0 為 no-op。
        if report is not None and report.success:
            _invalidate_h_state_async("agent.executor.execution_complete")
        else:
            _invalidate_h_state_async("agent.executor.execution_failed")

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
            # R-06-v2: IPC bridge — fallback to Rust engine SubmitOrder (shadow-only).
            # R-06-v2：IPC 橋接 — 回退到 Rust 引擎 SubmitOrder（影子模式）。
            # _paper_engine is None since DEAD-PY-2 deleted PaperTradingEngine.
            # Path A (Agent pipeline) submits to Rust paper_state via IPC instead.
            # Default shadow=True: log intent but don't submit, to avoid Path A/B conflicts.
            # shadow=True 默認：僅記錄 intent 不提交，避免 Path A/B 倉位衝突。
            return self._execute_via_ipc(
                intent_id=intent_id, symbol=symbol, side=side, qty=qty,
                order_type=order_type, price=price, expected_price=expected_price,
                start_time=start_time, metadata=metadata,
            )

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

    # ── R-06-v2: IPC Execution Bridge / IPC 執行橋接 ──

    # G3-03 Phase B (2026-04-25): the historical class attribute
    # ``_shadow_mode: bool = True`` has been removed. Shadow mode is now read
    # at execution time via ``self._read_shadow_mode()`` (provider set in __init__),
    # which routes through the Rust-IPC-backed ``ExecutorConfigCache``
    # (``executor_config_cache.py``). This closes CLAUDE.md §二 principle #3
    # ("AI 輸出 ≠ 即時命令") — operator IPC flip + cache poll cycle yield
    # < 60s shadow→live turnaround instead of restart-to-apply.
    # G3-03 Phase B：``_shadow_mode = True`` 類屬性硬編碼已移除，改於執行時
    # 透過 ``_read_shadow_mode()`` 即時讀取（背後是 Rust IPC 快取）。
    # 落實根原則 #3，operator IPC 切換 < 60s 生效，取代重啟才生效。

    def _execute_via_ipc(
        self,
        *,
        intent_id: str,
        symbol: str,
        side: str,
        qty: float,
        order_type: str,
        price: Optional[float],
        expected_price: float,
        start_time: float,
        metadata: Optional[Dict[str, Any]],
    ) -> ExecutionReport:
        """
        Execute via Rust engine IPC SubmitOrder (R-06-v2 bridge).
        通過 Rust 引擎 IPC SubmitOrder 執行（R-06-v2 橋接）。

        When shadow_mode=True (default): logs the intent and returns a shadow report
        without actually placing an order. This avoids Path A/B position conflicts.
        shadow_mode=True（默認）時：記錄 intent 並返回影子報告，不實際下單。

        When shadow_mode=False: sends SubmitOrder IPC to Rust engine, which routes
        to paper_state. The order goes through the same governance + risk pipeline.
        shadow_mode=False 時：發送 SubmitOrder IPC 到 Rust 引擎。

        Fail-closed: IPC error → return failure report, never raises.
        失敗關閉：IPC 錯誤 → 返回失敗報告，不向上拋出。
        """
        execution_engine = _resolve_execution_engine(metadata)
        shadow_now = self._read_shadow_mode(execution_engine)
        if shadow_now:
            # Shadow mode: log only, don't submit / 影子模式：僅記錄不提交
            logger.info(
                "Executor IPC shadow: intent=%s engine=%s %s %s qty=%.6f / "
                "執行器 IPC 影子：intent=%s engine=%s %s %s qty=%.6f",
                intent_id, execution_engine, side, symbol, qty,
                intent_id, execution_engine, side, symbol, qty,
            )
            report = ExecutionReport(
                intent_id=intent_id, symbol=symbol, side=side,
                requested_qty=qty, expected_price=expected_price,
                success=True,  # shadow "success" — intent was captured
                error="shadow_mode",
                metadata={
                    **(metadata or {}),
                    "execution_path": "ipc_shadow",
                    "execution_engine": execution_engine,
                },
            )
            self._store_report(report)
            return report

        # Real IPC submission / 真實 IPC 提交
        import asyncio
        try:
            from .paper_trading_routes import _ipc_command

            ipc_params = {
                "engine": execution_engine,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "order_type": order_type,
                "strategy": f"agent_executor:{intent_id[:12]}",
            }
            if price is not None:
                ipc_params["limit_price"] = price

            # Bridge sync→async: run IPC in a new event loop if needed
            # 同步→異步橋接：必要時在新事件循環中運行 IPC
            try:
                loop = asyncio.get_running_loop()
                # Already in async context — schedule coroutine
                future = asyncio.run_coroutine_threadsafe(
                    _ipc_command("submit_paper_order", ipc_params), loop,
                )
                result = future.result(timeout=5.0)
            except RuntimeError:
                # No running loop — create one
                result = asyncio.run(_ipc_command("submit_paper_order", ipc_params))

            fill_time_ms = (time.time() - start_time) * 1000
            if isinstance(result, dict) and result.get("error"):
                report = ExecutionReport(
                    intent_id=intent_id, symbol=symbol, side=side,
                    requested_qty=qty, expected_price=expected_price,
                    fill_time_ms=round(fill_time_ms, 2), success=False,
                    error=f"IPC rejected: {str(result.get('error', ''))[:100]}",
                    metadata={
                        **(metadata or {}),
                        "execution_path": "ipc_real",
                        "execution_engine": execution_engine,
                    },
                )
            else:
                actual_price = float(result.get("price", expected_price)) if isinstance(result, dict) else expected_price
                filled_qty = float(result.get("qty", qty)) if isinstance(result, dict) else qty
                slippage_bps = abs(actual_price - expected_price) / max(expected_price, 1e-8) * 10_000 if expected_price > 0 else 0.0
                report = ExecutionReport(
                    intent_id=intent_id, symbol=symbol, side=side,
                    requested_qty=qty, filled_qty=filled_qty,
                    expected_price=expected_price, actual_price=actual_price,
                    slippage_bps=round(slippage_bps, 2),
                    fill_time_ms=round(fill_time_ms, 2), success=True,
                    metadata={
                        **(metadata or {}),
                        "execution_path": "ipc_real",
                        "execution_engine": execution_engine,
                    },
                )
                with self._lock:
                    self._stats["executions_success"] += 1
            self._store_report(report)
            return report

        except Exception as e:
            fill_time_ms = (time.time() - start_time) * 1000
            logger.error("Executor IPC bridge failed: %s / 執行器 IPC 橋接失敗", e)
            report = ExecutionReport(
                intent_id=intent_id, symbol=symbol, side=side,
                requested_qty=qty, expected_price=expected_price,
                fill_time_ms=round(fill_time_ms, 2), success=False,
                error="IPC bridge failed — see server logs",
                metadata={
                    **(metadata or {}),
                    "execution_path": "ipc_error",
                    "execution_engine": execution_engine,
                },
            )
            with self._lock:
                self._stats["executions_failed"] += 1
                self._stats["errors"] += 1
            self._store_report(report)
            return report

    def _read_canary_stage(self, engine: Optional[str] = None) -> "CanaryStage":
        """W-AUDIT-9 T3 — 讀取當前 ``CanaryStage`` for given engine。

        provider 優先序：
          1. ``self._canary_stage_provider``（W-AUDIT-9 SoT）
          2. fallback 到 ``self._shadow_mode_provider``（legacy projection；
             True → SHADOW，False → PAPER_SINGLE_COHORT）
          3. 雙 None → fail-closed SHADOW

        invariant 9（**critical**）：任何錯誤路徑均 fail-closed Stage 0
        （**不是** Stage 1）。
        """
        # ── 1. 優先 stage-aware provider ──
        stage_provider = self._canary_stage_provider
        if stage_provider is not None:
            try:
                if engine is None:
                    raw = stage_provider()
                else:
                    try:
                        raw = stage_provider(engine)
                    except TypeError:
                        # provider 不接受 engine arg → 退化為 zero-arg call
                        raw = stage_provider()
                # 防禦：provider 應回 CanaryStage，但任何異常值 fall back SHADOW
                if isinstance(raw, CanaryStage):
                    return raw
                return CanaryStage.from_raw(raw)
            except Exception as exc:  # noqa: BLE001 — 任何錯誤一律 fail-closed Stage 0
                logger.warning(
                    "ExecutorAgent canary_stage_provider raised %s engine=%s — "
                    "fail-closed Stage 0（**不是** Stage 1）",
                    exc, engine or "default",
                )
                return CanaryStage.SHADOW

        # ── 2. fallback legacy shadow_mode_provider（投影為 stage）──
        legacy_provider = self._shadow_mode_provider
        if legacy_provider is not None:
            try:
                if engine is None:
                    is_shadow = bool(legacy_provider())
                else:
                    try:
                        is_shadow = bool(legacy_provider(engine))
                    except TypeError:
                        is_shadow = bool(legacy_provider())
                # legacy 投影：True → SHADOW；False → PAPER_SINGLE_COHORT
                # （注意：這只是 backward-compat 投影；新代碼應直接注入
                #  canary_stage_provider 以區分 Stage 1/2/3/4）
                return CanaryStage.SHADOW if is_shadow else CanaryStage.PAPER_SINGLE_COHORT
            except Exception as exc:  # noqa: BLE001 — invariant 9 fail-closed
                logger.warning(
                    "ExecutorAgent shadow_mode_provider raised %s engine=%s — "
                    "fail-closed Stage 0（**不是** Stage 1）",
                    exc, engine or "default",
                )
                return CanaryStage.SHADOW

        # ── 3. 雙 provider 缺失：fail-closed Stage 0 ──
        if not self._canary_stage_provider_missing_warned:
            logger.warning(
                "ExecutorAgent provider unavailable for engine=%s — "
                "fail-closed Stage 0（**不是** Stage 1）",
                engine or "default",
            )
            self._canary_stage_provider_missing_warned = True
        return CanaryStage.SHADOW

    def _read_shadow_mode(self, engine: Optional[str] = None) -> bool:
        """W-AUDIT-9 backward-compat — 投影 ``CanaryStage`` 至 legacy bool。

        Stage 0 → True（shadow）；Stage ≥ 1 → False（live submit per cohort scope）。

        本方法保留供既有 callsite（snapshot / get_stats / route layer）使用；
        新代碼建議直接呼叫 ``_read_canary_stage()`` 以取得 stage 資訊。

        provider 缺失或 exception 時 fail-closed True（=Stage 0），對齊
        TODO v19 §5 invariant 9。
        """
        # 為保留 legacy `shadow_mode_provider unavailable` warning（既有測試
        # `test_executor_agent_has_no_unconditional_lambda_true_fallback`
        # grep source 字串 `shadow_mode_provider unavailable`），只在「兩個
        # provider 都 None」時印該訊息。
        if (
            self._canary_stage_provider is None
            and self._shadow_mode_provider is None
            and not self._shadow_mode_provider_missing_warned
        ):
            logger.warning(
                "ExecutorAgent shadow_mode_provider unavailable for engine=%s — "
                "fail-closed to shadow=True / shadow_mode_provider 未配置，"
                "fail-closed",
                engine or "default",
            )
            self._shadow_mode_provider_missing_warned = True

        stage = self._read_canary_stage(engine)
        return stage == CanaryStage.SHADOW

    # ── Report Storage / 报告存储 ──

    def _store_report(self, report: ExecutionReport) -> None:
        """Store and audit an execution report / 存储并审计执行报告"""
        with self._lock:
            self._reports.append(report)
            if len(self._reports) > self.config.max_reports:
                self._reports = self._reports[-self.config.max_reports:]
        self._audit("execution_report", report.to_dict())

    # ── Audit / 审计 ──
    # _audit() inherited from BaseAgent (prefixes event with role.value = "executor").
    # _audit() 繼承自 BaseAgent（前綴為 role.value = "executor"）。

    # ── Status / 状态 ──

    def get_stats(self) -> Dict[str, Any]:
        """Return the live ExecutorAgent stats snapshot / 回傳即時統計快照。

        Plan ``aa-nifty-walrus.md`` UX A-grade contract requires the route
        layer to render shadow vs live with three-layer visual isolation
        (card bg + banner + number unit). To satisfy that contract this
        snapshot must expose two non-``_stats`` fields the route layer
        relies on:

        * ``shadow_mode`` — bool, derived live from
          ``self._read_shadow_mode()`` (G3-03 Phase B Rust IPC cache
          backed by ``ExecutorConfigCache``). Provider exception →
          fail-closed ``True`` (mirrors ``get_executor_snapshot`` policy
          and CLAUDE.md §二 原則 #6 "失敗默認收縮").
        * ``orders_submitted`` — int, an alias for ``executions_success``
          (the count of intents that *actually traded*, not merely
          attempted; plan §A copy "今日成单数" maps to fills, not
          attempts). Aliased rather than added to ``_stats`` to avoid
          double-counting on dashboards that also read
          ``executions_success`` directly.

        Both fields land *after* the ``**self._stats`` spread so the
        original keys remain stable. Provider call is performed *outside*
        ``self._lock`` to avoid deadlock with ``ExecutorConfigCache``
        internal lock (same rule as ``get_executor_snapshot`` since G3-03
        Phase B).

        plan ``aa-nifty-walrus.md`` UX A 級合約要求路由層以三層視覺隔離
        渲染 shadow / live（卡片底色 + banner + 數字單位）。為履行合約，
        本快照必須額外曝露兩個非 ``_stats`` 欄位：

        * ``shadow_mode`` — bool；透過 ``self._read_shadow_mode()``
          即時讀取（G3-03 Phase B 的 Rust IPC 快取，背後是
          ``ExecutorConfigCache``）。provider 例外 → fail-closed 為
          ``True``（對齊 ``get_executor_snapshot`` 策略與 CLAUDE.md §二
          原則 #6「失敗默認收縮」）。
        * ``orders_submitted`` — int；``executions_success`` 的別名（plan
          §A「今日成单数」應指實際成交，非嘗試；故對應到
          ``executions_success``）。以別名方式輸出，不另寫進 ``_stats``，
          避免 dashboard 雙重讀取造成計數翻倍。

        兩欄位皆置於 ``**self._stats`` 展開之後，原 key 順序保持穩定。
        provider 呼叫於 ``self._lock`` 外執行，以避免與
        ``ExecutorConfigCache`` 內部 lock 死鎖（G3-03 Phase B 原則）。
        """
        with self._lock:
            avg_slippage = 0.0
            if self._stats["executions_success"] > 0:
                avg_slippage = self._stats["total_slippage_bps"] / self._stats["executions_success"]
            executions_success = int(self._stats.get("executions_success", 0))
            # GUI heartbeat contract: ms-epoch read inside the lock for
            # consistency with other stats fields.
            # GUI 心跳契約：在 lock 內讀 ms-epoch，與其他 stats 欄位一致。
            last_heartbeat_ms = int(self._last_heartbeat_ms)
            base = {
                "role": AgentRole.EXECUTOR.value,
                "state": self.state.value,
                "total_reports": len(self._reports),
                "avg_slippage_bps": round(avg_slippage, 2),
                # GUI heartbeat contract: surfaced for roster card.
                # GUI 心跳契約：給 roster card 用。
                "last_heartbeat_ms": last_heartbeat_ms,
                **dict(self._stats),
            }
        # Provider call OUTSIDE self._lock to avoid deadlock with
        # ExecutorConfigCache internal lock (G3-03 Phase B contract; mirrors
        # get_executor_snapshot()).
        # provider 呼叫於 self._lock 外，避與 ExecutorConfigCache 內部 lock 死鎖
        # （G3-03 Phase B 契約；對齊 get_executor_snapshot()）。
        shadow_mode_bool = self._read_shadow_mode()
        base["shadow_mode"] = shadow_mode_bool
        # ``orders_submitted`` is the count of *fills produced*, not attempts —
        # plan §A copy「今日成单数」maps to executions_success (real trades).
        # ``orders_submitted`` 是真實成交數，對應 executions_success，非 attempt。
        base["orders_submitted"] = executions_success
        return base

    def get_recent_reports(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock:
            return [r.to_dict() for r in self._reports[-limit:]]

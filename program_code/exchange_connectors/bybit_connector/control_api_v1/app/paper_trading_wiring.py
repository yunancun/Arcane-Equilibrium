"""
Paper Trading Wiring — module-level singletons and dependency injection (TD-03 split).
紙上交易接線 — 模組級單例和依賴注入（TD-03 拆分）。

Split from paper_trading_routes.py to keep routes file under 800-line warning limit.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .ipc_state_reader import get_rust_reader
# ARCH-RC1 1C-3-F: paper_trading_engine.py retired. Rust engine is now the
# sole paper-side engine; PAPER_STORE/ENGINE remain as None stubs purely so
# legacy import sites (main.py / governance_routes.py / strategy_wiring.py)
# don't crash — every consumer already gates on `if ENGINE is not None`.
# ARCH-RC1 1C-3-F：paper_trading_engine.py 退場，PAPER_STORE/ENGINE 留 None stub。
from .shadow_decision_builder import ShadowDecisionConsumer
from .paper_trading_metrics import compute_full_metrics

# ═══════════════════════════════════════════════════════════════════════════════
# Paper State Store Initialization / 纸上状态存储初始化
# ═══════════════════════════════════════════════════════════════════════════════

_paper_state_path = os.getenv(
    "OPENCLAW_PAPER_STATE_FILE",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "runtime", "paper_trading_state.json")
    ),
)
# ARCH-RC1 1C-3-F: PAPER_STORE removed — PaperStateStore retired; Rust owns paper state. / PAPER_STORE 已移除，紙盤狀態權威移至 Rust。

# Risk manager (3-tier priority: P0 category > P1 global > P2 agent)
# 风控管理器（三层优先级：P0 品类专属 > P1 全局 > P2 Agent 自适应）
from .risk_manager import RiskManager  # noqa: E402
from .portfolio_risk_control import PortfolioRiskControl, PortfolioRiskConfig  # noqa: E402
from .perception_data_plane import PerceptionPlane  # noqa: E402
# ARCH-RC1 1C-3-D: RiskManager is now a thin RiskViewClient subclass; the
# real risk authority lives in Rust ConfigStore + intent_processor. The old
# set_portfolio_risk_control / set_governance_hub / set_change_audit_log
# injection points are removed — those dependencies are owned by Rust now.
RISK_MANAGER = RiskManager()
PORTFOLIO_RISK_CONTROL = PortfolioRiskControl(config=PortfolioRiskConfig())
# T5.04: Symbol whitelist removed — Scanner + Guardian + H0 Gate provide sufficient filtering.
# 符号白名单已移除 — 掃描器 + Guardian + H0 Gate 提供了足夠的篩選機制。
# T2.02: Initialize and inject PerceptionPlane / 初始化并注入感知平面
PERCEPTION_PLANE = PerceptionPlane()
# ═══════════════════════════════════════════════════════════════════════════════
# ARCH-RC1 1C-3-F: PaperTradingEngine retired (deleted in de1ec69).
# ARCH-RC1 1C-3-F：PaperTradingEngine 已退場（de1ec69 物理刪除）。
#
# Rust openclaw_engine is the sole paper trading engine.
# Rust openclaw_engine 是唯一的紙上交易引擎。
# All paper state reads go through ipc_state_reader (Rust snapshot).
# 所有 paper 狀態讀取通過 ipc_state_reader（Rust 快照）。
# ENGINE remains as a None stub purely so legacy import sites
# (main.py / governance_routes.py / strategy_wiring.py) don't crash —
# every consumer already gates on `if ENGINE is not None`.
# ENGINE 保留為 None stub 僅為避免 legacy import site 崩潰，所有消費者均已 None 短路。
# ═══════════════════════════════════════════════════════════════════════════════
ENGINE = None  # type: ignore[assignment]
logger.info(
    "PaperTradingEngine retired (ARCH-RC1 1C-3-F) — openclaw_engine is sole paper engine / "
    "PaperTradingEngine 已退場（ARCH-RC1 1C-3-F）— openclaw_engine 現為唯一紙盤引擎"
)

# T7.01: Initialize BybitDemoConnector / 初始化 Bybit Demo 连接器
from .bybit_demo_connector import BybitDemoConnector  # noqa: E402
from .bybit_demo_sync import BybitDemoSync  # noqa: E402

DEMO_CONNECTOR = None
try:
    DEMO_CONNECTOR = BybitDemoConnector()
except Exception as e:
    logger.warning("Failed to initialize BybitDemoConnector: %s", e)

# T7.04: Initialize BybitDemoSync for demo state snapshots / 初始化 Demo 同步器
DEMO_SYNC = None
if DEMO_CONNECTOR is not None and DEMO_CONNECTOR.is_enabled:
    try:
        DEMO_SYNC = BybitDemoSync(DEMO_CONNECTOR)
    except Exception as e:
        logger.warning("Failed to initialize BybitDemoSync: %s", e)

# T2.03: Initialize and inject ProtectiveOrderManager / 初始化并注入保护性订单管理器
from .protective_order_manager import ProtectiveOrderManager, ProtectiveOrderSide, ProtectiveOrderType  # noqa: E402

# T7.02: Enhanced ProtectiveOrderManager execute callback → Demo API
def _protective_order_execute_callback(order, market_state):
    """Execute protective order via Demo API if available / 通过 Demo API 执行保护性订单"""
    logger.info("Protective order triggered: %s %s %s", order.order_id, order.symbol, order.order_type.value)

    if DEMO_CONNECTOR is None:
        logger.warning("Demo connector unavailable, protective order not submitted to exchange")
        return

    try:
        # Map side: LONG_POSITION closing = Sell, SHORT_POSITION closing = Buy
        if order.side == ProtectiveOrderSide.LONG_POSITION:
            bybit_side = "Sell"
        elif order.side == ProtectiveOrderSide.SHORT_POSITION:
            bybit_side = "Buy"
        else:
            logger.warning("Unsupported protective order side: %s", order.side.value)
            return

        # Map order type
        if order.order_type in (ProtectiveOrderType.HARD_STOP_LOSS, ProtectiveOrderType.SOFT_STOP_LOSS,
                                ProtectiveOrderType.EMERGENCY_CLOSE_ALL):
            bybit_order_type = "Market"
            bybit_price = None
        elif order.order_type == ProtectiveOrderType.TAKE_PROFIT:
            bybit_order_type = "Limit"
            bybit_price = order.trigger_price
        else:
            bybit_order_type = "Market"
            bybit_price = None

        result = DEMO_CONNECTOR.submit_order(
            symbol=order.symbol,
            side=bybit_side,
            order_type=bybit_order_type,
            qty=order.quantity,
            price=bybit_price,
            reduce_only=True,
            category="linear",
        )
        logger.info("Protective order %s submitted to Demo API: %s", order.order_id, result)
    except Exception as e:
        logger.error("Failed to submit protective order %s to Demo API: %s", order.order_id, e)

PROTECTIVE_ORDER_MANAGER = ProtectiveOrderManager(on_execute_callback=_protective_order_execute_callback)
# RC-10: ENGINE is None — skip all injections / ENGINE 為 None — 跳過所有注入

# Governance Hub (SM-01 + SM-04 + SM-02 + EX-04 integration)
# 治理集線器（授權 + 風控 + 租約 + 對賬 集成）
from .governance_hub import GovernanceHub  # noqa: E402
from .audit_persistence import AuditPipeline, AuditPersistenceConfig  # noqa: E402
from .incident_event_model import IncidentPolicy  # noqa: E402
from .ttl_enforcer import TTLEnforcer  # noqa: E402
import os as _gov_os
import atexit as _atexit
_gov_audit_dir = _gov_os.getenv(
    "OPENCLAW_GOVERNANCE_AUDIT_DIR",
    _gov_os.path.abspath(_gov_os.path.join(_gov_os.path.dirname(__file__), "..", "runtime", "governance_audit"))
)

# T1.04: Create AuditPipeline for SM persistence
AUDIT_PIPELINE = AuditPipeline(
    config=AuditPersistenceConfig(base_dir=_gov_audit_dir)
)

GOV_HUB = GovernanceHub(audit_dir=_gov_audit_dir)

# T1.04: Connect AuditPipeline to GovernanceHub for SM callbacks
GOV_HUB.set_audit_pipeline(AUDIT_PIPELINE)

# T1.05: Create IncidentPolicy and connect to GovernanceHub
INCIDENT_POLICY = IncidentPolicy(
    audit_callback=AUDIT_PIPELINE.make_callback("incident_policy"),
    on_auth_action=GOV_HUB.handle_incident_auth_action,
    on_risk_action=GOV_HUB.handle_incident_risk_action,
    on_operator_alert=GOV_HUB.handle_incident_operator_alert,
)

# T1.06: Create and start TTL Enforcer daemon
# FIX-04: Counter for tracking TTL enforcement failures
_ttl_enforcement_failures = 0

def _make_ttl_expiry_callback():
    """Create expiry callback for TTL Enforcer to trigger SM transitions"""
    def callback(entry, action):
        global _ttl_enforcement_failures
        try:
            # Access module-level globals for late binding to SM singletons
            # This allows the SMs to be initialized after the callback is created
            gov_hub = globals().get("GOV_HUB")
            if gov_hub is None:
                logger.warning("GovernanceHub not available in TTL callback")
                return

            # Handle different SM types based on entry.state_machine_name
            if entry.state_machine_name == "Authorization":
                if action == "auto_reject":
                    try:
                        # Ensure SMs are initialized
                        if not gov_hub._initialized:
                            gov_hub._ensure_initialized()

                        # Call reject on the authorization SM
                        if gov_hub._authorization_sm is not None:
                            result = gov_hub._authorization_sm.reject(
                                entry.object_id,
                                reason=f"TTL expired: {action}"
                            )
                            logger.info("TTL expired Authorization %s: auto-rejected to %s", entry.object_id, result.state.value)
                        else:
                            logger.warning("Authorization SM not available for TTL callback")
                    except Exception as e:
                        _ttl_enforcement_failures += 1
                        logger.critical("Failed to reject authorization %s on TTL: %s", entry.object_id, e)
                        # FIX-04: Send alert via TELEGRAM_ALERTER if available
                        if TELEGRAM_ALERTER and TELEGRAM_ALERTER.is_enabled:
                            try:
                                TELEGRAM_ALERTER.alert(f"TTL enforcement failure: Authorization {entry.object_id} rejection failed: {e}")
                            except Exception:
                                pass  # Don't fail the callback if alerting fails

            elif entry.state_machine_name == "DecisionLease":
                if action == "auto_expire":
                    try:
                        # Ensure SMs are initialized
                        if not gov_hub._initialized:
                            gov_hub._ensure_initialized()

                        # Call reject on the lease SM (to expire it)
                        if gov_hub._lease_sm is not None:
                            result = gov_hub._lease_sm.reject(
                                entry.object_id,
                                reason=f"TTL expired: {action}"
                            )
                            logger.info("TTL expired Lease %s: auto-expired to %s", entry.object_id, result.state.value)
                        else:
                            logger.warning("DecisionLease SM not available for TTL callback")
                    except Exception as e:
                        _ttl_enforcement_failures += 1
                        logger.critical("Failed to expire lease %s on TTL: %s", entry.object_id, e)
                        # FIX-04: Send alert via TELEGRAM_ALERTER if available
                        if TELEGRAM_ALERTER and TELEGRAM_ALERTER.is_enabled:
                            try:
                                TELEGRAM_ALERTER.alert(f"TTL enforcement failure: Lease {entry.object_id} expiry failed: {e}")
                            except Exception:
                                pass  # Don't fail the callback if alerting fails

            elif entry.state_machine_name == "OMS":
                # Batch 10: Handle OMS TTL expiry (e.g., SUBMITTED timeout → auto-CANCEL)
                if action == "auto_cancel":
                    try:
                        if not gov_hub._initialized:
                            gov_hub._ensure_initialized()
                        if gov_hub._oms_sm is not None:
                            from .oms_state_machine import OrderState, OrderInitiator
                            gov_hub._oms_sm.cancel(
                                entry.object_id,
                                initiator=OrderInitiator.SYSTEM,
                                reason=f"TTL expired: {action}",
                            )
                            logger.info("TTL expired OMS %s: auto-canceled", entry.object_id)
                        else:
                            logger.warning("OMS SM not available for TTL callback")
                    except Exception as e:
                        _ttl_enforcement_failures += 1
                        logger.critical("Failed to cancel OMS order %s on TTL: %s", entry.object_id, e)
                        if TELEGRAM_ALERTER and TELEGRAM_ALERTER.is_enabled:
                            try:
                                TELEGRAM_ALERTER.alert(f"TTL enforcement failure: OMS {entry.object_id} cancel failed: {e}")
                            except Exception:
                                pass

            elif entry.state_machine_name == "RiskGovernor":
                if action == "manual_review_required":
                    try:
                        # Ensure SMs are initialized
                        if not gov_hub._initialized:
                            gov_hub._ensure_initialized()

                        # Request manual review
                        if gov_hub._risk_governor_sm is not None:
                            result = gov_hub._risk_governor_sm.request_manual_review(
                                reason=f"TTL expired: Circuit breaker requires manual review"
                            )
                            logger.info("TTL expired Risk state: escalated to MANUAL_REVIEW (level=%s)", result.level)
                        else:
                            logger.warning("RiskGovernor SM not available for TTL callback")
                    except Exception as e:
                        _ttl_enforcement_failures += 1
                        logger.critical("Failed to request manual review on TTL: %s", e)
                        # FIX-04: Send alert via TELEGRAM_ALERTER if available
                        if TELEGRAM_ALERTER and TELEGRAM_ALERTER.is_enabled:
                            try:
                                TELEGRAM_ALERTER.alert(f"TTL enforcement failure: Risk manual review request failed: {e}")
                            except Exception:
                                pass  # Don't fail the callback if alerting fails

                elif action == "escalate":
                    try:
                        # Ensure SMs are initialized
                        if not gov_hub._initialized:
                            gov_hub._ensure_initialized()

                        # Escalate from MANUAL_REVIEW
                        if gov_hub._risk_governor_sm is not None:
                            result = gov_hub._risk_governor_sm.request_manual_review(
                                reason=f"TTL expired: Manual review timeout, escalating"
                            )
                            logger.info("TTL expired Risk MANUAL_REVIEW: escalated (level=%s)", result.level)
                        else:
                            logger.warning("RiskGovernor SM not available for TTL callback")
                    except Exception as e:
                        _ttl_enforcement_failures += 1
                        logger.critical("Failed to escalate risk on TTL: %s", e)
                        # FIX-04: Send alert via TELEGRAM_ALERTER if available
                        if TELEGRAM_ALERTER and TELEGRAM_ALERTER.is_enabled:
                            try:
                                TELEGRAM_ALERTER.alert(f"TTL enforcement failure: Risk escalation failed: {e}")
                            except Exception:
                                pass  # Don't fail the callback if alerting fails

        except Exception as e:
            _ttl_enforcement_failures += 1
            logger.critical("Error in TTL expiry callback: %s", e)
            # FIX-04: Send alert via TELEGRAM_ALERTER if available
            if TELEGRAM_ALERTER and TELEGRAM_ALERTER.is_enabled:
                try:
                    TELEGRAM_ALERTER.alert(f"TTL enforcement failure: Callback error: {e}")
                except Exception:
                    pass  # Don't fail the callback if alerting fails

    return callback

TTL_ENFORCER = TTLEnforcer(
    audit_callback=AUDIT_PIPELINE.make_callback("ttl_enforcer"),
    expiry_callback=_make_ttl_expiry_callback(),
)

# Start TTL daemon sweep (every 5 seconds)
TTL_ENFORCER.start_daemon_sweep(interval_seconds=5)

# Register shutdown hook to stop TTL daemon gracefully
def _shutdown_ttl_enforcer():
    try:
        TTL_ENFORCER.stop_daemon_sweep(timeout_seconds=10)
        logger.info("TTL Enforcer daemon stopped")
    except Exception as e:
        logger.error("Error stopping TTL Enforcer: %s", e)

_atexit.register(_shutdown_ttl_enforcer)

# ─────────────────────────────────────────────────────────────────────
# P1-16: H0Gate singleton + H0HealthWorker background daemon
# P1-16：H0 確定性門控單例 + 健康監控背景線程
# ─────────────────────────────────────────────────────────────────────
try:
    from .h0_gate import H0Gate, H0HealthWorker, H0GateConfig

    def _h0_db_probe() -> None:
        """Lightweight I/O probe via paper-state file stat().

        ARCH-RC1 1C-3-E F-mini: switched from PAPER_STORE.read() (which loads
        and JSON-decodes the full snapshot) to a cheap os.stat() — same purpose
        (detect disk hang) at a fraction of the cost, and decoupled from the
        soon-to-be-retired Python PaperStateStore.
        透過 paper state 文件 stat() 測量輕量 I/O 延遲（偵測磁盤 hang）。
        """
        try:
            os.stat(_paper_state_path)
        except FileNotFoundError:
            pass

    H0_GATE = H0Gate(config=H0GateConfig())
    _h0_health_worker = H0HealthWorker(
        gate=H0_GATE,
        sample_interval_s=5.0,
        db_probe_fn=_h0_db_probe,
    )
    _h0_health_worker.start()
    logger.info(
        "H0Gate + H0HealthWorker started (P1-16) / H0 門控 + 健康監控線程已啟動"
    )

    def _shutdown_h0_health_worker() -> None:
        try:
            _h0_health_worker.stop()
            logger.info("H0HealthWorker stopped / H0 健康監控線程已停止")
        except Exception as _h0_stop_err:
            logger.error("Error stopping H0HealthWorker: %s", _h0_stop_err)

    _atexit.register(_shutdown_h0_health_worker)

except ImportError as _h0_import_err:
    H0_GATE = None
    logger.warning(
        "H0Gate not available (import error) — running without H0 gate: %s "
        "/ H0 門控不可用（導入錯誤）：%s",
        _h0_import_err, _h0_import_err,
    )

# ARCH-RC1 1C-3-D: governance_hub injection no longer flows through RISK_MANAGER.
# RC-10: ENGINE is always None (PaperTradingEngine retired) — governance_hub set via Rust IPC only.

# T2.04: Initialize and inject ChangeAuditLog / 初始化并注入變更審計日誌
from .change_audit_log import ChangeAuditLog  # noqa: E402
CHANGE_AUDIT_LOG = ChangeAuditLog()
GOV_HUB.set_change_audit_log(CHANGE_AUDIT_LOG)

# ARCH-RC1 1C-3-D: ChangeAuditLog injection into RISK_MANAGER removed —
# audit now flows via V014 engine_events written by the Rust IPC layer.

# T2.05: Initialize and inject RecoveryApprovalGate / 初始化并注入恢復審批門禁
from .recovery_approval_gate import RecoveryApprovalGate  # noqa: E402
RECOVERY_GATE = RecoveryApprovalGate()
GOV_HUB.set_recovery_gate(RECOVERY_GATE)

# T2.07: Initialize and inject ScannerRateLimiter / 初始化并注入扫描速率限制器
from .scanner_rate_limiter import ScannerRateLimiter  # noqa: E402
SCANNER_RATE_LIMITER = ScannerRateLimiter()

# T8.06: Initialize and inject TelegramAlerter into GovernanceHub
from .telegram_alerter import TelegramAlerter  # noqa: E402
TELEGRAM_ALERTER = TelegramAlerter()
if TELEGRAM_ALERTER.is_enabled:
    GOV_HUB.set_alerter(TELEGRAM_ALERTER)
    logger.info("TelegramAlerter injected into GovernanceHub")
else:
    logger.info("TelegramAlerter disabled (no token/chat_id configured)")

# OC-1/OC-2: WebhookAlerter + AlertRouter (multi-channel alert fan-out)
# OC-1/OC-2：WebhookAlerter + AlertRouter（多通道告警扇出）
from .webhook_alerter import WebhookAlerter  # noqa: E402
from .alert_router import AlertRouter  # noqa: E402
WEBHOOK_ALERTER = WebhookAlerter()
ALERT_ROUTER = AlertRouter(telegram=TELEGRAM_ALERTER, webhook=WEBHOOK_ALERTER)

# T9A.01: Initialize and inject LearningTierGate for analyst agent evolution
from .learning_tier_gate import LearningTierGate  # noqa: E402
try:
    def _make_learning_tier_audit_callback():
        """Create audit callback for LearningTierGate promotion events"""
        def callback(promotion_record: dict):
            try:
                # Emit learning_tier_promotion audit via AUDIT_PIPELINE if available
                if AUDIT_PIPELINE:
                    AUDIT_PIPELINE.record_event({
                        "event_type": "learning_tier_promotion",
                        "data": promotion_record,
                        "timestamp_ms": int(promotion_record.get("effective_at_ms", 0)),
                    })
                logger.info("Learning tier promotion recorded: %s", promotion_record.get('promotion_id'))
            except Exception as e:
                logger.error("Error in learning tier audit callback: %s", e)
        return callback

    LEARNING_TIER_GATE = LearningTierGate(audit_callback=_make_learning_tier_audit_callback())
    # RC-10: ENGINE is None — skip ENGINE injection
    GOV_HUB.set_learning_tier_gate(LEARNING_TIER_GATE)
    logger.info("LearningTierGate injected into GovernanceHub (ENGINE disabled RC-10)")
except Exception as e:
    logger.error("Failed to initialize LearningTierGate: %s", e)
    LEARNING_TIER_GATE = None

# Export GOV_HUB as _GOVERNANCE_HUB for governance_routes.py to import
# This creates a singleton reference for the governance API routes
# 将 GOV_HUB 导出为 _GOVERNANCE_HUB，供 governance_routes.py 导入
import sys as _sys_ref
_current_module = _sys_ref.modules[__name__]
_current_module._GOVERNANCE_HUB = GOV_HUB

# Shadow decision consumer (lazy-initialized with engine)
# 影子决策消费器（与引擎延迟初始化）
SHADOW_CONSUMER: ShadowDecisionConsumer | None = None

__all__ = [
    "RISK_MANAGER",
    "PORTFOLIO_RISK_CONTROL",
    "PERCEPTION_PLANE",
    "ENGINE",
    "DEMO_CONNECTOR",
    "DEMO_SYNC",
    "PROTECTIVE_ORDER_MANAGER",
    "GOV_HUB",
    "AUDIT_PIPELINE",
    "INCIDENT_POLICY",
    "TTL_ENFORCER",
    "H0_GATE",
    "CHANGE_AUDIT_LOG",
    "RECOVERY_GATE",
    "SCANNER_RATE_LIMITER",
    "TELEGRAM_ALERTER",
    "WEBHOOK_ALERTER",
    "ALERT_ROUTER",
    "LEARNING_TIER_GATE",
    "SHADOW_CONSUMER",
    "_ttl_enforcement_failures",
]

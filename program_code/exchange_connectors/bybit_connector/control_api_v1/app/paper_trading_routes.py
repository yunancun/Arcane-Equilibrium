from __future__ import annotations

"""
OpenClaw Paper Trading API Routes / 纸上交易 API 路由
OpenClaw 模拟交易系统的所有 REST API 端点

MODULE_NOTE (中文):
  本模块定义纸上交易系统的所有 API 路由，使用 FastAPI APIRouter 模式。
  所有路由复用主系统的认证机制，要求 paper:read 或 paper:trade scope。
  所有响应携带 is_simulated=True 和 data_category=paper_simulated 标记。

MODULE_NOTE (English):
  This module defines all API routes for the paper trading system using FastAPI APIRouter.
  All routes reuse the main system's auth mechanism, requiring paper:read or paper:trade scopes.
  All responses carry is_simulated=True and data_category=paper_simulated markers.
"""

import json
import logging
import os
import subprocess
from typing import Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from . import main_legacy as base
from .paper_trading_engine import (
    DEFAULT_INITIAL_BALANCE_USDT,
    PaperStateStore,
    PaperTradingEngine,
)
from .market_data_dispatcher import MarketDataDispatcher
from .shadow_decision_builder import (
    ShadowDecisionConsumer,
    ShadowDecisionFileFeeder,
    build_shadow_decision,
)
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
PAPER_STORE = PaperStateStore(_paper_state_path)

# Risk manager (3-tier priority: P0 category > P1 global > P2 agent)
# 风控管理器（三层优先级：P0 品类专属 > P1 全局 > P2 Agent 自适应）
from .risk_manager import RiskManager  # noqa: E402
from .portfolio_risk_control import PortfolioRiskControl, PortfolioRiskConfig  # noqa: E402
from .perception_data_plane import PerceptionPlane  # noqa: E402
RISK_MANAGER = RiskManager()  # Loads operator config from file automatically
# T2.01: Initialize and inject PortfolioRiskControl / 初始化并注入组合风控
PORTFOLIO_RISK_CONTROL = PortfolioRiskControl(config=PortfolioRiskConfig())
RISK_MANAGER.set_portfolio_risk_control(PORTFOLIO_RISK_CONTROL)
# T5.04: Symbol whitelist removed — Scanner + Guardian + H0 Gate provide sufficient filtering.
# 符号白名单已移除 — 掃描器 + Guardian + H0 Gate 提供了足夠的篩選機制。
# T2.02: Initialize and inject PerceptionPlane / 初始化并注入感知平面
PERCEPTION_PLANE = PerceptionPlane()
ENGINE = PaperTradingEngine(PAPER_STORE, risk_manager=RISK_MANAGER)

# Restore agent P2 risk params from paper state (session-scoped, e.g. trailing stops, cooldowns)
# 從 paper state 恢復 Agent P2 風控參數（Session 範圍：trailing stops、cooldown 等運行狀態）
try:
    _paper_state = PAPER_STORE.read()
    _risk_state = _paper_state.get("risk")
    if _risk_state:
        RISK_MANAGER.load_risk_state(_risk_state)
        logger.info("Agent risk state restored from paper state / Agent 風控狀態已從 paper state 恢復")
except Exception as _e:
    logger.warning("Failed to restore agent risk state: %s (non-fatal)", _e)

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
ENGINE.set_protective_order_manager(PROTECTIVE_ORDER_MANAGER)

# T7.01: Inject BybitDemoConnector into ENGINE / 向 ENGINE 注入 Demo 连接器
if DEMO_CONNECTOR is not None:
    ENGINE.set_demo_connector(DEMO_CONNECTOR)

# T7.04: Inject BybitDemoSync into ENGINE / 向 ENGINE 注入 Demo 同步器
if DEMO_SYNC is not None:
    ENGINE.set_demo_sync(DEMO_SYNC)

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
        """Lightweight I/O probe via PAPER_STORE read.
        透過 paper state 文件讀取測量輕量 I/O 延遲（偵測磁盤 hang）。
        """
        PAPER_STORE.read()

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

ENGINE.set_governance_hub(GOV_HUB)
RISK_MANAGER.set_governance_hub(GOV_HUB)

# T2.04: Initialize and inject ChangeAuditLog / 初始化并注入變更審計日誌
from .change_audit_log import ChangeAuditLog  # noqa: E402
CHANGE_AUDIT_LOG = ChangeAuditLog()
GOV_HUB.set_change_audit_log(CHANGE_AUDIT_LOG)

# T3.06: Inject ChangeAuditLog into RiskManager and PaperTradingEngine
RISK_MANAGER.set_change_audit_log(CHANGE_AUDIT_LOG)
ENGINE.set_change_audit_log(CHANGE_AUDIT_LOG)

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
    ENGINE.set_learning_tier_gate(LEARNING_TIER_GATE)
    GOV_HUB.set_learning_tier_gate(LEARNING_TIER_GATE)
    logger.info("LearningTierGate injected into ENGINE and GovernanceHub")
except Exception as e:
    logger.error("Failed to initialize LearningTierGate: %s", e)
    LEARNING_TIER_GATE = None

# Export GOV_HUB as _GOVERNANCE_HUB for governance_routes.py to import
# This creates a singleton reference for the governance API routes
# 将 GOV_HUB 导出为 _GOVERNANCE_HUB，供 governance_routes.py 导入
import sys as _sys_ref
_current_module = _sys_ref.modules[__name__]
_current_module._GOVERNANCE_HUB = GOV_HUB

# Market data dispatcher (lazy-initialized on first start)
# 行情分发器（首次启动时延迟初始化）
DISPATCHER: MarketDataDispatcher | None = None

# Shadow decision consumer (lazy-initialized with engine)
# 影子决策消费器（与引擎延迟初始化）
SHADOW_CONSUMER: ShadowDecisionConsumer | None = None

# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

paper_router = APIRouter(prefix="/api/v1/paper", tags=["Paper Trading / 纸上交易"])


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response Models / 请求响应模型
# ═══════════════════════════════════════════════════════════════════════════════

class SessionStartRequest(BaseModel):
    initial_balance: float = Field(default=DEFAULT_INITIAL_BALANCE_USDT, gt=0, le=1_000_000)


class OrderSubmitRequest(BaseModel):
    symbol: str = Field(max_length=30)
    side: str = Field(max_length=4)      # "Buy" or "Sell"
    order_type: str = Field(max_length=10)  # "market" or "limit"
    qty: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    leverage: float = Field(default=1.0, gt=0, le=125)


class OrderCancelRequest(BaseModel):
    order_id: str = Field(max_length=50)


class TickRequest(BaseModel):
    market_prices: dict[str, float]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: Build paper response envelope / 构建纸上交易响应信封
# ═══════════════════════════════════════════════════════════════════════════════

def _paper_response(
    data: Any,
    action_result: str = "success",
    reason_codes: list[str] | None = None,
) -> dict[str, Any]:
    """Build a simplified response envelope for paper trading routes."""
    return {
        "api_version": "v1",
        "action_result": action_result,
        "reason_codes": reason_codes or [],
        "data_category": "paper_simulated",
        "is_simulated": True,
        "data": data,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Session Routes / Session 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/session/start")
def post_session_start(
    req: SessionStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Start a new paper trading session / 开始新的纸上交易 session"""
    try:
        state = ENGINE.start_session(initial_balance=req.initial_balance)

        # Auto-grant paper authorization on session start (zero real risk).
        # 会话启动时自动授予纸盘授权（无真实资金风险）。
        # This unblocks is_authorized() so orders can flow through the governance gate.
        # 这将解除 is_authorized() 的阻塞，让订单能通过治理门检。
        try:
            if GOV_HUB is not None:
                granted = GOV_HUB.grant_paper_authorization()
                if granted:
                    logger.info("Paper trading authorization auto-granted on session start")
                else:
                    logger.warning(
                        "grant_paper_authorization() returned False on session start "
                        "— governance gate will remain closed / 纸盘授权返回 False — 治理门检仍关闭"
                    )
        except Exception as _auth_err:
            # Non-fatal: session itself is started; warn and continue.
            # 非致命错误：会话本身已启动；记录警告并继续。
            logger.warning("Failed to auto-grant paper authorization: %s", _auth_err)

        return _paper_response({"session": state["session"], "message": "Paper trading session started"})
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session start conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.post("/session/reauth")
def post_session_reauth(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Re-grant paper trading authorization without resetting the session.
    重新授予纸盘交易授权，无需重置当前 session。

    Use case: server was restarted with an existing active session; the authorization
    was not re-granted on startup (because grant_paper_authorization() is normally
    called on session start, not on state-file load).
    使用场景：服务器重启后加载了已有 active session；由于 grant_paper_authorization()
    只在 session start 时调用，重启后授权丢失。此端点补授权，不影响现有 session 状态。

    Returns: {granted: bool, is_authorized: bool, auth_state: str}
    """
    try:
        if GOV_HUB is None:
            raise HTTPException(status_code=503, detail="Governance hub not available")

        already_authorized = GOV_HUB.is_authorized()
        if already_authorized:
            return _paper_response({
                "granted": False,
                "is_authorized": True,
                "message": "Authorization already active — no-op / 授权已有效，跳过",
            })

        granted = GOV_HUB.grant_paper_authorization()
        is_authorized_after = GOV_HUB.is_authorized()
        logger.info(
            "Paper session reauth: granted=%s, is_authorized_after=%s / "
            "纸盘 session 补授权：granted=%s，授权后状态=%s",
            granted, is_authorized_after, granted, is_authorized_after,
        )
        return _paper_response({
            "granted": granted,
            "is_authorized": is_authorized_after,
            "message": "Paper authorization re-granted / 纸盘授权已补授" if granted
                       else "grant_paper_authorization() returned False / 补授权返回 False",
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error in session reauth: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@paper_router.post("/session/pause")
def post_session_pause(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Pause the current session / 暂停当前 session"""
    try:
        state = ENGINE.pause_session()
        return _paper_response({"session": state["session"]})
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session pause conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.post("/session/resume")
def post_session_resume(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Resume a paused session / 恢复已暂停的 session"""
    try:
        state = ENGINE.resume_session()
        return _paper_response({"session": state["session"]})
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session resume conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.post("/session/stop")
def post_session_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop the session and finalize PnL / 停止 session 并结算 PnL"""
    try:
        state = ENGINE.stop_session()
        return _paper_response({
            "session": state["session"],
            "pnl": state["pnl"],
            "message": "Paper trading session stopped and PnL finalized",
        })
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Session stop conflict: %s", e)
        raise HTTPException(status_code=409, detail="Session state conflict")


@paper_router.get("/session/status")
def get_session_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current session status / 获取 session 状态"""
    return _paper_response(ENGINE.get_session_status())


# ═══════════════════════════════════════════════════════════════════════════════
# Order Routes / 订单路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/order/submit")
def post_order_submit(
    req: OrderSubmitRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Submit a paper order / 提交纸上订单"""
    try:
        # Use live market prices from dispatcher if available, fall back to order price
        # 优先使用来自行情分发器的实时价格，否则回退到订单价格
        live_prices = None
        if DISPATCHER and DISPATCHER.is_running():
            live_prices = DISPATCHER.get_status().get("latest_prices", {})
        if not live_prices:
            live_prices = {req.symbol: req.price} if req.price else None

        result = ENGINE.submit_order(
            symbol=req.symbol,
            side=req.side,
            order_type=req.order_type,
            qty=req.qty,
            price=req.price,
            leverage=req.leverage,
            market_prices=live_prices,
        )
        if result["rejected_reason"]:
            return _paper_response(
                result,
                action_result="blocked",
                reason_codes=[result["rejected_reason"]],
            )
        return _paper_response(result)
    except ValueError as e:
        # 不暴露內部異常細節到 HTTP 響應 / Do not leak internal exception details to HTTP response
        logger.warning("Order submission validation error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid order parameters")


@paper_router.post("/order/cancel")
def post_order_cancel(
    req: OrderCancelRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Cancel a working paper order / 取消纸上订单"""
    result = ENGINE.cancel_order(req.order_id)
    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["reason"])
    return _paper_response({"order_id": req.order_id, "canceled": True})


@paper_router.get("/orders")
def get_orders(
    state_filter: str | None = None,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """List paper orders / 获取纸上订单列表"""
    orders = ENGINE.get_orders(state_filter=state_filter)
    return _paper_response({"orders": orders, "count": len(orders)})


# ═══════════════════════════════════════════════════════════════════════════════
# Position / Fill / PnL Routes / 持仓 / 成交 / PnL 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/positions")
def get_positions(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get current paper positions / 获取纸上持仓"""
    positions = ENGINE.get_positions()
    return _paper_response({"positions": positions, "count": len(positions)})


@paper_router.get("/fills")
def get_fills(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get fill history / 获取成交历史"""
    fills = ENGINE.get_fills(limit=min(limit, 200))
    return _paper_response({"fills": fills, "count": len(fills)})


@paper_router.get("/pnl")
def get_pnl(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get paper PnL summary / 获取纸上 PnL 汇总"""
    return _paper_response(ENGINE.get_pnl())


@paper_router.get("/audit-trail")
def get_audit_trail(
    limit: int = 100,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get audit trail / 获取审计记录"""
    trail = ENGINE.get_audit_trail(limit=min(limit, 500))
    return _paper_response({"audit_trail": trail, "count": len(trail)})


# ═══════════════════════════════════════════════════════════════════════════════
# Tick Route / 成交模拟 Tick 路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.post("/tick")
def post_tick(
    req: TickRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Manually trigger a fill simulation tick / 手动触发成交模拟 tick

    Provide current market prices to check if any limit orders should fill.
    """
    result = ENGINE.tick(market_prices=req.market_prices)
    return _paper_response(result)


# ═══════════════════════════════════════════════════════════════════════════════
# Export Route / 导出路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/export")
def get_export(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Export complete session data for analysis / 导出完整 session 数据"""
    return _paper_response(ENGINE.export_session())


# ═══════════════════════════════════════════════════════════════════════════════
# Market Feed Routes / 实时行情流路由
# ═══════════════════════════════════════════════════════════════════════════════

class MarketFeedStartRequest(BaseModel):
    symbols: list[str] = Field(default=["BTCUSDT", "ETHUSDT"], max_length=20)


class MarketFeedSymbolRequest(BaseModel):
    symbol: str = Field(max_length=30)


@paper_router.post("/market-feed/start")
def post_market_feed_start(
    req: MarketFeedStartRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Start real-time market data feed (Bybit public WebSocket).
    启动实时行情数据流（Bybit 公共 WebSocket）。

    Connects to wss://stream.bybit.com/v5/public/linear and subscribes to ticker data.
    The attention filter automatically triggers paper engine ticks based on trading context.
    """
    global DISPATCHER
    if DISPATCHER and DISPATCHER.is_running():
        return _paper_response(
            {"message": "Market feed already running / 行情流已在运行", "status": DISPATCHER.get_status()},
            action_result="no_change",
        )

    DISPATCHER = MarketDataDispatcher(
        engine=ENGINE,
        symbols=req.symbols,
    )
    DISPATCHER.start()

    # Register pipeline bridge as tick consumer / 注册管线桥接器为 tick 消费者
    try:
        from .phase2_strategy_routes import PIPELINE_BRIDGE
        if PIPELINE_BRIDGE is not None:
            DISPATCHER.register_tick_consumer(PIPELINE_BRIDGE)
            PIPELINE_BRIDGE.activate()
            logger.info("Pipeline bridge registered and activated / 管线桥接器已注册并激活")
    except ImportError:
        logger.warning("Pipeline bridge not available / 管线桥接器不可用")

    return _paper_response({
        "message": "Market feed started / 行情流已启动",
        "symbols": req.symbols,
        "status": DISPATCHER.get_status(),
    })


@paper_router.post("/market-feed/stop")
def post_market_feed_stop(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Stop the real-time market data feed / 停止实时行情数据流"""
    global DISPATCHER
    if not DISPATCHER or not DISPATCHER.is_running():
        return _paper_response(
            {"message": "Market feed not running / 行情流未运行"},
            action_result="no_change",
        )

    # Deactivate pipeline bridge / 停用管线桥接器
    try:
        from .phase2_strategy_routes import PIPELINE_BRIDGE
        if PIPELINE_BRIDGE is not None:
            PIPELINE_BRIDGE.deactivate()
    except ImportError:
        pass

    DISPATCHER.stop()
    return _paper_response({"message": "Market feed stopped / 行情流已停止"})


@paper_router.get("/market-feed/status")
def get_market_feed_status(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get market data feed status / 获取行情数据流状态"""
    if not DISPATCHER:
        return _paper_response({
            "running": False,
            "attention_level": "dormant",
            "message": "Market feed not initialized / 行情流未初始化",
        })
    return _paper_response(DISPATCHER.get_status())


@paper_router.post("/market-feed/add-symbol")
def post_market_feed_add_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Dynamically add a symbol to the market feed / 动态添加交易对到行情流"""
    if not DISPATCHER or not DISPATCHER.is_running():
        raise HTTPException(status_code=409, detail="Market feed not running / 行情流未运行")

    DISPATCHER.add_symbol(req.symbol)
    return _paper_response({
        "message": f"Symbol {req.symbol} added / 已添加交易对 {req.symbol}",
        "symbol": req.symbol,
    })


@paper_router.post("/market-feed/remove-symbol")
def post_market_feed_remove_symbol(
    req: MarketFeedSymbolRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Dynamically remove a symbol from the market feed / 动态移除交易对"""
    if not DISPATCHER or not DISPATCHER.is_running():
        raise HTTPException(status_code=409, detail="Market feed not running / 行情流未运行")

    DISPATCHER.remove_symbol(req.symbol)
    return _paper_response({
        "message": f"Symbol {req.symbol} removed / 已移除交易对 {req.symbol}",
        "symbol": req.symbol,
    })


# ═══════════════════════════════════════════════════════════════════════════════
# Shadow Decision Routes / 影子决策路由
# ═══════════════════════════════════════════════════════════════════════════════

class ShadowFeedRequest(BaseModel):
    market_prices: dict[str, float]
    symbol: str = Field(default="BTCUSDT", max_length=30)


@paper_router.post("/shadow/feed")
def post_shadow_feed(
    req: ShadowFeedRequest,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Manually feed a shadow decision tick.
    手动触发一次影子决策馈送（用于测试或手动模式）。

    Builds a shadow decision from current verdict/observation files and consumes it.
    """
    global SHADOW_CONSUMER
    if SHADOW_CONSUMER is None:
        SHADOW_CONSUMER = ShadowDecisionConsumer(ENGINE)

    # Build a minimal decision (no H-chain files — manual mode)
    decision = build_shadow_decision(symbol=req.symbol, market_prices=req.market_prices)
    result = SHADOW_CONSUMER.consume(decision, req.market_prices)
    return _paper_response(result)


@paper_router.get("/shadow/history")
def get_shadow_history(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get shadow decision consumption history / 获取影子决策消费历史"""
    if SHADOW_CONSUMER is None:
        return _paper_response({"history": [], "count": 0})
    history = SHADOW_CONSUMER.get_history(limit=min(limit, 200))
    return _paper_response({"history": history, "count": len(history)})


@paper_router.get("/shadow/decisions")
def get_shadow_decisions(
    limit: int = 50,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """Get shadow decisions stored in paper state / 获取存储在纸上状态中的影子决策"""
    state = ENGINE.get_state()
    decisions = state.get("shadow_decisions", [])[-min(limit, 200):]
    return _paper_response({"shadow_decisions": decisions, "count": len(decisions)})


# ═══════════════════════════════════════════════════════════════════════════════
# Metrics Route / 性能指标路由
# ═══════════════════════════════════════════════════════════════════════════════

@paper_router.get("/metrics")
def get_metrics(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get comprehensive performance metrics for the paper trading session.
    获取纸上交易 session 的综合性能指标。

    Includes: win rate, drawdown, holding period, Sharpe ratio, shadow decision stats.
    """
    state = ENGINE.get_state()
    metrics = compute_full_metrics(state)
    return _paper_response(metrics)


# ═══════════════════════════════════════════════════════════════════════════════
# AI Cost Tracking Route (via OpenClaw gateway) / AI 成本追踪路由
# ═══════════════════════════════════════════════════════════════════════════════

def _fetch_openclaw_usage_cost() -> dict[str, Any] | None:
    """
    Fetch AI usage cost from OpenClaw gateway CLI.
    从 OpenClaw 网关 CLI 获取 AI 使用成本。

    Returns parsed cost data or None if OpenClaw is not available.
    """
    try:
        result = subprocess.run(
            ["openclaw", "gateway", "usage-cost", "--json", "--days", "30"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, json.JSONDecodeError):
        return None


@paper_router.get("/ai-cost")
def get_ai_cost(
    actor: base.AuthenticatedActor = Depends(base.current_actor),
):
    """
    Get AI usage cost from OpenClaw gateway.
    从 OpenClaw 网关获取 AI 使用成本。

    Integrates OpenClaw's built-in token/cost tracking with our Net PnL system.
    """
    raw = _fetch_openclaw_usage_cost()
    if raw is None:
        return _paper_response({
            "available": False,
            "message": "OpenClaw gateway not reachable / OpenClaw 网关不可达",
            "today_cost": 0.0,
            "today_tokens": 0,
            "total_cost_30d": 0.0,
            "total_tokens_30d": 0,
            "daily": [],
        })

    # Extract today's cost
    daily = raw.get("daily", [])
    totals = raw.get("totals", {})

    today_entry = daily[-1] if daily else {}
    today_cost = today_entry.get("totalCost", 0.0)
    today_tokens = today_entry.get("totalTokens", 0)

    return _paper_response({
        "available": True,
        "source": "openclaw_gateway_usage_cost",
        "today_cost": round(today_cost, 6),
        "today_tokens": today_tokens,
        "total_cost_30d": round(totals.get("totalCost", 0.0), 6),
        "total_tokens_30d": totals.get("totalTokens", 0),
        "cost_breakdown": {
            "input_cost": round(totals.get("inputCost", 0.0), 6),
            "output_cost": round(totals.get("outputCost", 0.0), 6),
            "cache_read_cost": round(totals.get("cacheReadCost", 0.0), 6),
            "cache_write_cost": round(totals.get("cacheWriteCost", 0.0), 6),
        },
        "daily": daily[-7:],  # Last 7 days
    })

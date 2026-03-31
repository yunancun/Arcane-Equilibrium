"""
Governance Routes — REST API endpoints for unified governance control
治理路由 — 统一治理控制的 REST API 端点

MODULE_NOTE (中文):
  本模块提供治理集线器的 REST API 接口：
  - GET /api/v1/governance/status — 联合治理仪表板
  - GET /api/v1/governance/auth/status — 授权 SM 详细状态
  - POST /api/v1/governance/auth/request — 创建新授权请求（DRAFT → PENDING_APPROVAL，等待操作员批准）
  - POST /api/v1/governance/auth/approve — 操作员批准待审核授权
  - GET /api/v1/governance/risk/level — 风控等级 + 历史
  - POST /api/v1/governance/risk/override — 操作员降级（带原因）
  - POST /api/v1/governance/reconcile — 触发手动对账
  - GET /api/v1/governance/leases — 列出活跃租约

  所有路由遵循统一的响应模式，采用 APIRouter 前缀避免循环依赖。

MODULE_NOTE (English):
  REST API routes for the GovernanceHub:
  - GET /api/v1/governance/status — Combined governance dashboard
  - GET /api/v1/governance/auth/status — Authorization SM detailed state
  - POST /api/v1/governance/auth/request — Create new authorization request (DRAFT → PENDING_APPROVAL, awaiting Operator)
  - POST /api/v1/governance/auth/approve — Operator approves pending auth
  - GET /api/v1/governance/risk/level — Risk governor level + history
  - POST /api/v1/governance/risk/override — Operator de-escalates
  - POST /api/v1/governance/reconcile — Trigger manual reconciliation
  - GET /api/v1/governance/leases — List active leases

  All routes follow unified response pattern with APIRouter prefix to avoid circular deps.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
import hmac
import html

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Router / 路由器
# ═══════════════════════════════════════════════════════════════════════════════

governance_router = APIRouter(
    prefix="/api/v1/governance",
    tags=["Governance / 治理"],
)


# ═══════════════════════════════════════════════════════════════════════════════
# Lazy Imports / 延迟导入
# ═══════════════════════════════════════════════════════════════════════════════

def _get_governance_hub() -> Any:
    """
    Lazy import to avoid circular dependency / 延迟导入避免循环依赖

    Tries to get GOV_HUB from paper_trading_routes module (the primary source).
    Falls back gracefully if unavailable.

    Returns:
        GovernanceHub instance or None if unavailable
    """
    try:
        # Primary source: paper_trading_routes.GOV_HUB
        from .paper_trading_routes import GOV_HUB
        return GOV_HUB
    except ImportError:
        try:
            # Fallback: try module-level singleton (if explicitly exported)
            from . import _GOVERNANCE_HUB
            return _GOVERNANCE_HUB
        except ImportError:
            return None


def _get_paper_live_gate() -> Any:
    """
    Lazy import PaperLiveGate from phase2_strategy_routes / 延迟导入

    Returns:
        PaperLiveGate instance or None if unavailable
    """
    try:
        from .phase2_strategy_routes import PAPER_LIVE_GATE
        return PAPER_LIVE_GATE
    except ImportError:
        return None


def _get_h0_gate() -> Any:
    """
    Lazy import H0Gate singleton from paper_trading_routes (P1-16).
    延遲導入 H0Gate singleton（來自 paper_trading_routes，P1-16）。

    Returns:
        H0Gate instance or None if unavailable / H0Gate 實例，不可用時為 None
    """
    try:
        from .paper_trading_routes import H0_GATE  # noqa: PLC0415
        return H0_GATE
    except (ImportError, AttributeError):
        return None


def _require_operator_auth(authorization: str | None = Header(default=None)) -> Any:
    """FastAPI Depends: 驗證認證 + Operator 角色，返回已驗證的 actor。
    Validates authentication and Operator role; returns the authenticated actor.

    用於所有需要 Operator 角色的端點簽名，替代手動調用 _require_operator_role()。
    Intended as the standard Depends() target for all write/state-change endpoints,
    replacing the current pattern of manually calling _require_operator_role(actor)
    inside the function body. (P2-NEW-3)

    Usage in new endpoints:
        actor: Any = Depends(_require_operator_auth)

    Raises:
        HTTPException(401) if not authenticated.
        HTTPException(403) if authenticated but not Operator.
        HTTPException(503) if authentication system unavailable.
    """
    actor = _get_auth_actor(authorization)
    _require_operator_role(actor)
    return actor


def _get_auth_actor(authorization: str | None = Header(default=None)) -> Any:
    """
    FastAPI dependency — validates bearer token and returns authenticated actor.
    FastAPI 依赖 — 验证 bearer token 并返回已认证的 actor。

    Called by FastAPI at request time (use as Depends(_get_auth_actor) WITHOUT parentheses).
    由 FastAPI 在请求时调用（使用 Depends(_get_auth_actor)，不加括号）。
    """
    try:
        from . import main_legacy as base
    except ImportError:
        raise HTTPException(status_code=503, detail="Authentication system unavailable")

    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.replace("Bearer ", "", 1).strip()
    if not hmac.compare_digest(token.encode("utf-8"), base.settings.api_token.encode("utf-8")):
        raise HTTPException(status_code=401, detail="Authentication required")
    return base.build_authenticated_actor()


def _get_authenticated_actor_class() -> type:
    """
    Lazily import AuthenticatedActor to avoid circular imports.
    延迟导入 AuthenticatedActor 以避免循环依赖。

    Returns:
        AuthenticatedActor class, or type(None) as fail-closed sentinel.
    """
    try:
        from .main_legacy import AuthenticatedActor
        return AuthenticatedActor
    except (ImportError, AttributeError):
        return type(None)  # fail-closed: no actor will match type(None)


def _sanitize_log(value: Any, max_len: int = 200) -> str:
    """
    Sanitize a value for safe log output (strip newlines, truncate).
    清理日志输出值（去除换行符，截断长度）。
    """
    return str(value).replace("\n", "\\n").replace("\r", "\\r")[:max_len]


def _require_operator_role(actor: Any) -> None:
    """
    Validate that actor has Operator role / 验证 actor 具有 Operator 角色

    Uses duck-typing (hasattr check) instead of isinstance to avoid false negatives
    from Python module reimport causing different class objects in memory.
    The actor is guaranteed to come from the FastAPI dependency chain (current_actor),
    so duck-typing is safe here.
    """
    if not actor or not hasattr(actor, 'roles') or not hasattr(actor, 'actor_id'):
        raise HTTPException(status_code=401, detail="Authentication required")
    if "operator" not in actor.roles:
        logger.warning(
            "Non-operator attempted governance action: %s",
            _sanitize_log(actor.actor_id),
        )
        raise HTTPException(status_code=403, detail="Operator role required")


def _sanitize_string(s: str, max_len: int = 500) -> str:
    """SECURITY FIX #4: Sanitize user input to prevent injection / 清理用户输入防止注入"""
    if not isinstance(s, str):
        raise ValueError("Input must be string")
    # Limit length
    s = s[:max_len]
    # HTML-escape for safe logging/display
    return html.escape(s, quote=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Request/Response Models / 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════════

class AuthApprovalRequest(BaseModel):
    """Request to approve pending authorization / 批准待审核授权的请求"""
    approval_note: str = Field(..., min_length=1, max_length=500, description="Operator's approval note")


class RiskOverrideRequest(BaseModel):
    """Request to de-escalate risk level / 降级风险等级的请求"""
    target_level: str = Field(
        ...,
        description="Target risk level: NORMAL, CAUTIOUS, REDUCED, DEFENSIVE, CIRCUIT_BREAKER, MANUAL_REVIEW"
    )
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for de-escalation")


class ManualReconciliationRequest(BaseModel):
    """Request to trigger manual reconciliation / 触发手动对账的请求"""
    paper_state: dict[str, Any] = Field(..., description="Local paper trading state")
    demo_state: dict[str, Any] | None = Field(default=None, description="Demo/exchange state (optional)")
    reason: str = Field(default="manual_trigger", description="Reason for reconciliation")


class DeEscalationRequest(BaseModel):
    """Request to de-escalate risk level / 降级风险等级的请求"""
    target_level: int = Field(..., ge=0, le=5, description="Target risk level (0=NORMAL to 5=MANUAL_REVIEW)")
    requested_by: str = Field(..., min_length=1, max_length=100, description="Requester name/ID")
    reason: str = Field(..., min_length=1, max_length=500, description="Reason for de-escalation")


class ApproveDeEscalationRequest(BaseModel):
    """Request to approve de-escalation / 批准降级的请求"""
    approved_by: str = Field(..., min_length=1, max_length=100, description="Approver name/ID")


class SymbolWhitelistAddRequest(BaseModel):
    """Request to add symbol to whitelist / 将符号添加到白名单的请求"""
    symbol: str = Field(..., min_length=1, max_length=50, description="Symbol to add (e.g., BTCUSDT)")
    category: str = Field(..., description="Category (spot, linear, inverse, option)")


class PaperLiveGateEvaluateRequest(BaseModel):
    """Request to evaluate PaperLiveGate conditions / 评估 PaperLiveGate 条件的请求"""
    paper_start_time_ms: int = Field(..., description="Paper trading start timestamp (ms)")
    total_trades: int = Field(..., ge=0, description="Total completed round-trip trades")
    win_rate_percent: float = Field(..., ge=0, le=100)
    net_pnl: float = Field(...)
    sharpe_ratio: float = Field(...)
    max_drawdown_percent: float = Field(..., ge=0)
    profit_factor: float = Field(..., ge=0)
    audit_trail_completeness_percent: float = Field(default=99.0, ge=0, le=100)
    reconciliation_mismatch_percent: float = Field(default=0.0, ge=0)
    consecutive_losses: int = Field(default=0, ge=0)
    has_major_incidents: bool = Field(default=False)


class AuthRequestBody(BaseModel):
    """
    Request body for POST /auth/request — create a new authorization request.
    POST /auth/request 的请求体 — 创建新的授权请求。

    Used for Live Trading authorization requests that require Operator approval.
    用于需要操作员批准的实盘交易授权请求。
    """
    scope: dict = Field(default_factory=dict, description="Authorization scope dict (e.g., mode, execution, limits)")
    ttl_hours: int = Field(default=24, ge=1, le=168, description="TTL in hours (1–168)")
    reason: str = Field(default="operator_request", min_length=1, max_length=500, description="Reason for authorization request")


class GovernanceResponse:
    """Unified response wrapper for governance API / 治理 API 的统一响应包装"""

    @staticmethod
    def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
        return {
            "ok": True,
            "message": message,
            "data": data,
            "data_category": "governance",
        }

    @staticmethod
    def error(message: str, code: str = "error", status_code: int = 400) -> dict[str, Any]:
        return {
            "ok": False,
            "message": message,
            "code": code,
            "data_category": "governance",
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════

@governance_router.get("/status")
def get_governance_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get combined governance dashboard.
    获取联合治理仪表板。

    Returns governance hub status: authorization, risk, leases, reconciliation.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        status = hub.get_status()
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        return GovernanceResponse.success(data=status.to_dict(), message="governance_status")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting governance status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/status/detailed")
def get_detailed_governance_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get detailed aggregated governance status.
    获取详细的聚合治理状态。

    Returns comprehensive status including risk SM, authorizations, leases, OMS orders,
    recovery gate, change audit log, and demo connector.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        base_status = hub.get_status()
        # FIX-06: Null safety check
        if base_status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        detailed = base_status.to_dict()

        # Risk Governor State
        detailed["risk_governor"] = {
            "level": base_status.risk_level,
            "level_name": base_status.risk_level_name,
            "escalation_reason": base_status.risk_escalation_reason,
        }

        # Authorization counts
        detailed["authorization"] = {
            "state": base_status.auth_state,
            "expires_at_ms": base_status.auth_expires_at_ms,
            "pending_approval": base_status.auth_pending_approval,
        }

        # Leases
        detailed["decision_leases"] = {
            "active_count": base_status.active_leases_count,
            "total_tracked": base_status.total_leases_tracked,
        }

        # Reconciliation
        detailed["reconciliation"] = {
            "last_check_ms": base_status.last_reconciliation_ms,
            "last_result": base_status.last_reconciliation_result,
            "is_consistent": base_status.is_consistent,
        }

        # Recovery Gate pending count
        try:
            if hub._recovery_gate is not None:
                pending_reqs = hub._recovery_gate.get_pending_requests()
                detailed["recovery_gate"] = {
                    "pending_count": len(pending_reqs),
                    "stats": hub._recovery_gate.get_stats(),
                }
            else:
                detailed["recovery_gate"] = None
        except Exception as e:
            logger.debug(f"Error getting recovery gate status: {e}")
            detailed["recovery_gate"] = None

        # Change Audit Log pending count
        try:
            if hub._change_audit_log is not None:
                pending_changes = hub._change_audit_log.get_pending_approvals()
                detailed["change_audit_log"] = {
                    "pending_count": len(pending_changes),
                    "total_changes": len(hub._change_audit_log.get_all_changes()),
                }
            else:
                detailed["change_audit_log"] = None
        except Exception as e:
            logger.debug(f"Error getting change audit log status: {e}")
            detailed["change_audit_log"] = None

        # OMS State Machine status if available
        try:
            if hub._oms_sm is not None:
                # Try to get OMS status if the method exists
                if hasattr(hub._oms_sm, "get_status"):
                    oms_status = hub._oms_sm.get_status()
                    detailed["oms"] = oms_status if isinstance(oms_status, dict) else str(oms_status)
                else:
                    detailed["oms"] = {"status": "available", "method_unavailable": True}
            else:
                detailed["oms"] = None
        except Exception as e:
            logger.debug(f"Error getting OMS status: {e}")
            detailed["oms"] = None

        # Demo connector status if available
        try:
            from .paper_trading_routes import ENGINE
            if ENGINE is not None and hasattr(ENGINE, "_demo_connector"):
                demo_enabled = ENGINE._demo_connector is not None
                detailed["demo_connector"] = {
                    "enabled": demo_enabled,
                    "connector_type": type(ENGINE._demo_connector).__name__ if demo_enabled else None,
                }
            else:
                detailed["demo_connector"] = None
        except Exception as e:
            logger.debug(f"Error getting demo connector status: {e}")
            detailed["demo_connector"] = None

        # Overall health
        detailed["health"] = {
            "enabled": base_status.enabled,
            "mode": base_status.mode,
            "incident_count": base_status.incident_count,
            "callback_errors": base_status.callback_errors,
        }

        return GovernanceResponse.success(data=detailed, message="governance_status_detailed")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting detailed governance status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/auth/status")
def get_authorization_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get detailed Authorization SM state.
    获取详细的授权 SM 状态。

    Returns current state, scope, expiration, pending approvals.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        status = hub.get_status()
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        auth_detail = {
            "state": status.auth_state,
            "expires_at_ms": status.auth_expires_at_ms,
            "scope": status.auth_scope,
            "pending_approval": status.auth_pending_approval,
            "is_effective": status.auth_state in ["ACTIVE", "RESTRICTED"],
        }
        return GovernanceResponse.success(data=auth_detail, message="authorization_status")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting authorization status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/auth/request")
def request_authorization(
    body: AuthRequestBody,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Request a new authorization (DRAFT → PENDING_APPROVAL).
    请求新授权（DRAFT → PENDING_APPROVAL），等待操作员批准。

    Used for Live Trading authorization requests that require Operator approval.
    Paper Trading should use the auto-grant path (triggered on session start).
    用于需要操作员批准的实盘交易授权请求。
    纸盘交易应使用自动授权路径（在会话启动时触发）。

    Body: {scope: dict (optional), ttl_hours: int (default 24), reason: str}
    Returns: {authorization_id, state: "pending_approval"}
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        _require_operator_role(actor)

        # Sanitize reason before use / 清理 reason 防注入
        sanitized_reason = _sanitize_string(body.reason, max_len=500)

        if hub._authorization_sm is None:
            raise HTTPException(status_code=503, detail="Authorization state machine not initialized")

        # Step 1: Create DRAFT authorization / 步骤 1：创建 DRAFT 授权
        import time as _time
        expires_at_ms = int((_time.time() + body.ttl_hours * 3600) * 1000)
        requester = actor.actor_id
        auth_obj = hub._authorization_sm.create_draft(
            title=f"Operator Authorization Request / 操作员授权请求 ({requester})",
            scope=body.scope,
            created_by=requester,
            description=sanitized_reason,
            expires_at_ms=expires_at_ms,
        )
        auth_id = auth_obj.authorization_id

        # Step 2: Submit (DRAFT → PENDING_APPROVAL) / 步骤 2：提交（DRAFT → PENDING_APPROVAL）
        hub._authorization_sm.submit_for_approval(auth_id)

        logger.info(
            "Authorization request submitted by %s (id=%s, reason=%s) / "
            "授权请求已提交（id=%s，操作者=%s，原因=%s）",
            _sanitize_log(actor.actor_id), auth_id, sanitized_reason,
            auth_id, _sanitize_log(actor.actor_id), sanitized_reason,
        )

        return GovernanceResponse.success(
            data={
                "authorization_id": auth_id,
                "state": "pending_approval",
                "ttl_hours": body.ttl_hours,
                "scope": body.scope,
                "reason": sanitized_reason,
                "requested_by": actor.actor_id,
                "message": "Authorization request submitted. Awaiting Operator approval.",
            },
            message="authorization_requested",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error requesting authorization: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/auth/approve")
def approve_authorization(
    body: AuthApprovalRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator approves pending authorization.
    操作员批准待审核授权。

    Transitions authorization from PENDING_APPROVAL to ACTIVE.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # SECURITY FIX #4: Sanitize approval note
        sanitized_note = _sanitize_string(body.approval_note, max_len=500)

        # Get current auth state and approve pending
        status = hub.get_status()
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        if not status.auth_pending_approval:
            return GovernanceResponse.error(
                "No pending authorization approval",
                code="no_pending_approval",
                status_code=400
            )

        # SECURITY FIX #8: Actually call hub._authorization_sm.approve() to approve pending
        if hub._authorization_sm:
            try:
                all_auths = hub._authorization_sm.list_all()
                pending_auth = next(
                    (a for a in all_auths if a.state.value == "PENDING_APPROVAL"),
                    None
                )
                if pending_auth:
                    hub._authorization_sm.approve(pending_auth.authorization_id, approved_by=actor.actor_id)
                    logger.info("Authorization approved by %s: %s", _sanitize_log(actor.actor_id), sanitized_note)
                else:
                    return GovernanceResponse.error("No pending authorization found", code="not_found", status_code=404)
            except Exception as e:
                logger.error(f"Error calling approval method: {e}")
                # SECURITY FIX #6: Generic error to client, full details logged server-side
                raise HTTPException(status_code=500, detail="Failed to process approval")

        return GovernanceResponse.success(
            data={
                "status": "approval_recorded",
                "note": sanitized_note,
                "next_state": "ACTIVE",
            },
            message="authorization_approved"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving authorization: {e}", exc_info=True)
        # SECURITY FIX #6: Return generic error message
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/risk/level")
def get_risk_level(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get current risk governor level and history.
    获取当前风控等级和历史。

    Returns level, level_name, escalation reason, constraints.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        status = hub.get_status()
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        level_detail = {
            "level": status.risk_level,
            "level_name": status.risk_level_name,
            "escalation_reason": status.risk_escalation_reason,
            "mode": status.mode,
        }

        # Risk level mappings
        level_names = {
            0: "NORMAL",
            1: "CAUTIOUS",
            2: "REDUCED",
            3: "DEFENSIVE",
            4: "CIRCUIT_BREAKER",
            5: "MANUAL_REVIEW",
        }

        if status.risk_level is not None and status.risk_level in level_names:
            level_detail["level_name"] = level_names[status.risk_level]

        return GovernanceResponse.success(data=level_detail, message="risk_level_status")
    except Exception as e:
        logger.error(f"Error getting risk level: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/risk/override")
def override_risk_level(
    body: RiskOverrideRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator de-escalates risk level manually.
    操作员手动降级风险等级。

    Only LOWER risk (towards NORMAL) permitted; requires approval.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # SECURITY FIX #4: Sanitize reason
        sanitized_reason = _sanitize_string(body.reason, max_len=500)

        status = hub.get_status()
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        current_level = status.risk_level or 0

        # Map level name to int
        level_map = {
            "NORMAL": 0,
            "CAUTIOUS": 1,
            "REDUCED": 2,
            "DEFENSIVE": 3,
            "CIRCUIT_BREAKER": 4,
            "MANUAL_REVIEW": 5,
        }

        target_level = level_map.get(body.target_level.upper())
        if target_level is None:
            return GovernanceResponse.error(
                "Invalid target risk level",
                code="invalid_level",
                status_code=400
            )

        if target_level >= current_level:
            return GovernanceResponse.error(
                "Cannot escalate via override; only de-escalation allowed",
                code="escalation_not_allowed",
                status_code=403
            )

        # FIX-01: Check de-escalation gate for downward level changes
        # Map int back to string for gate check
        int_to_level_name = {
            0: "NORMAL",
            1: "CAUTIOUS",
            2: "REDUCED",
            3: "DEFENSIVE",
            4: "CIRCUIT_BREAKER",
            5: "MANUAL_REVIEW",
        }
        current_level_str = int_to_level_name.get(current_level, "UNKNOWN")
        target_level_str = int_to_level_name.get(target_level, "UNKNOWN")

        if target_level < current_level:
            # This is a de-escalation, check the gate
            if not hub._check_de_escalation_gate(current_level_str, target_level_str, sanitized_reason):
                return GovernanceResponse.success(
                    data={
                        "status": "de_escalation_pending_approval",
                        "current_level": current_level,
                        "target_level": target_level,
                        "reason": sanitized_reason,
                    },
                    message="de_escalation_pending_approval"
                )

        # SECURITY FIX #9: Actually apply the de-escalation if risk governor supports it
        if hub._risk_governor_sm:
            try:
                from .risk_governor_state_machine import RiskLevel, RiskInitiator
                hub._risk_governor_sm.escalate_to(
                    RiskLevel(target_level),
                    reason=sanitized_reason,
                    initiator=RiskInitiator.OPERATOR,
                )
                logger.warning(
                    "Risk override applied by %s: %s → %s, reason: %s",
                    _sanitize_log(actor.actor_id), current_level, target_level, sanitized_reason,
                )
            except Exception as e:
                logger.error(f"Error applying risk de-escalation: {e}")
                # SECURITY FIX #6: Return generic error to client
                raise HTTPException(status_code=500, detail="Failed to apply risk override")

        return GovernanceResponse.success(
            data={
                "status": "override_applied",
                "current_level": current_level,
                "target_level": target_level,
                "reason": sanitized_reason,
            },
            message="risk_override_applied"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in risk override: {e}", exc_info=True)
        # SECURITY FIX #6: Return generic error message
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/risk/de-escalation/request")
def request_de_escalation(
    body: DeEscalationRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Submit a de-escalation request for risk level.
    提交风险等级降级请求。

    Request will be queued for Operator approval before execution.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        _require_operator_role(actor)

        # Sanitize inputs
        sanitized_reason = _sanitize_string(body.reason, max_len=500)
        sanitized_requester = _sanitize_string(body.requested_by, max_len=100)

        # Submit de-escalation request
        request_id = hub.request_de_escalation(
            target_level=body.target_level,
            requested_by=sanitized_requester,
            reason=sanitized_reason,
        )

        if request_id is None:
            return GovernanceResponse.error(
                "Failed to submit de-escalation request",
                code="submission_failed",
                status_code=500
            )

        logger.info("De-escalation request submitted: %s by %s", request_id, sanitized_requester)

        return GovernanceResponse.success(
            data={
                "request_id": request_id,
                "target_level": body.target_level,
                "status": "pending_approval",
                "requested_by": sanitized_requester,
            },
            message="deescalation_requested"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error submitting de-escalation request: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/risk/de-escalation/{request_id}/approve")
def approve_de_escalation_request(
    request_id: str,
    body: ApproveDeEscalationRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator approves and executes a de-escalation request.
    操作员批准并执行降级请求。

    This will execute the risk level reduction if approved.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # Sanitize approver name
        sanitized_approver = _sanitize_string(body.approved_by, max_len=100)

        # Approve and execute de-escalation
        success = hub.approve_de_escalation(
            request_id=request_id,
            approved_by=sanitized_approver,
        )

        if not success:
            return GovernanceResponse.error(
                f"Failed to approve de-escalation request {request_id}",
                code="approval_failed",
                status_code=500
            )

        logger.info(f"De-escalation request approved: {request_id} by {sanitized_approver}")

        return GovernanceResponse.success(
            data={
                "request_id": request_id,
                "status": "approved_and_executed",
                "approved_by": sanitized_approver,
            },
            message="deescalation_approved"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving de-escalation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/reconcile")
def trigger_manual_reconciliation(
    body: ManualReconciliationRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Trigger manual reconciliation between paper and demo/exchange.
    触发纸上交易与 demo/交易所之间的手动对账。

    Returns reconciliation report.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        _require_operator_role(actor)

        logger.info(
            "Manual reconciliation triggered by %s: %s",
            _sanitize_log(actor.actor_id), _sanitize_log(body.reason),
        )

        report = hub.reconcile(
            paper_state=body.paper_state,
            demo_state=body.demo_state,
        )

        if not report.get("ok", True):
            return GovernanceResponse.error(
                report.get("reason", "Reconciliation failed"),
                code="reconciliation_error",
                status_code=500
            )

        return GovernanceResponse.success(
            data={
                "result": report.get("result"),
                "is_consistent": report.get("is_consistent"),
                "severity": report.get("severity"),
                "discrepancies": report.get("discrepancies", []),
                "timestamp_ms": int(__import__("time").time() * 1000),
            },
            message="reconciliation_complete"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in manual reconciliation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/recovery/pending")
def get_pending_recovery_requests(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get all pending recovery approval requests.
    获取所有待审批恢复请求。

    Returns list of pending recovery requests awaiting Operator approval.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        if hub._recovery_gate is None:
            return GovernanceResponse.success(data=[], message="recovery_pending_empty")

        pending = hub._recovery_gate.get_pending_requests()
        return GovernanceResponse.success(data=pending, message="recovery_pending_list")
    except Exception as e:
        logger.error(f"Error getting pending recovery requests: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/recovery/{request_id}/approve")
def approve_recovery_request(
    request_id: str,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator approves a pending recovery request.
    操作员批准待处理的恢复请求。

    Transitions recovery from PENDING to APPROVED and executes the recovery.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_globally_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        if hub._recovery_gate is None:
            return GovernanceResponse.error(
                "Recovery approval gate not available",
                code="gate_unavailable",
                status_code=503
            )

        # Verify request exists
        req = hub._recovery_gate.get_request(request_id)
        if req is None:
            return GovernanceResponse.error(
                f"Recovery request {request_id} not found",
                code="not_found",
                status_code=404
            )

        # Approve the recovery
        approval = hub._recovery_gate.approve_recovery(
            request_id=request_id,
            approved_by=actor.actor_id,
        )

        if approval is None:
            return GovernanceResponse.error(
                "Failed to approve recovery request",
                code="approval_failed",
                status_code=500
            )

        logger.info("Recovery request approved by %s: %s", _sanitize_log(actor.actor_id), request_id)

        return GovernanceResponse.success(
            data={
                "request_id": request_id,
                "approval_id": approval.approval_id,
                "status": "approved",
                "has_observation_period": approval.has_observation_period,
                "observation_end_ms": approval.observation_end_ms,
            },
            message="recovery_approved"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving recovery request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/audit/changes")
def get_change_history(
    limit: int = 50,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get change audit log history.
    获取变更审计日志历史。

    Returns list of recorded changes with audit trail.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        if hub._change_audit_log is None:
            return GovernanceResponse.success(data=[], message="audit_changes_empty")

        # Get all changes (limit applied on response)
        all_changes = hub._change_audit_log.get_all_changes()
        # Return most recent first (reverse order), limited by limit param
        changes_data = [change.to_dict() for change in reversed(all_changes[-limit:])]

        return GovernanceResponse.success(
            data=changes_data,
            message="audit_changes_list"
        )
    except Exception as e:
        logger.error(f"Error getting change history: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/audit/pending")
def get_pending_approvals(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get all changes awaiting approval.
    获取所有待批准的变更。

    Returns list of PENDING and EMERGENCY_BYPASSED changes.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        if hub._change_audit_log is None:
            return GovernanceResponse.success(data=[], message="audit_pending_empty")

        pending = hub._change_audit_log.get_pending_approvals()
        pending_data = [change.to_dict() for change in pending]

        return GovernanceResponse.success(data=pending_data, message="audit_pending_list")
    except Exception as e:
        logger.error(f"Error getting pending approvals: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


class AuditApprovalBody(BaseModel):
    """Request body for audit change approve/reject / 审计变更批准/拒绝请求体"""
    reason: str = Field("", max_length=500, description="Approval or rejection reason / 批准或拒绝原因")


@governance_router.post("/audit/approve/{change_id}")
def approve_audit_change(
    change_id: str,
    body: AuditApprovalBody,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator approves a pending audit change record.
    操作员批准待处理的审计变更记录。
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        _require_operator_role(actor)
        if hub._change_audit_log is None:
            return GovernanceResponse.error("Change audit log not available", code="log_unavailable", status_code=503)

        approver = actor.actor_id
        result = hub._change_audit_log.approve_change(
            change_id=change_id,
            approved_by=approver,
            approval_reason=body.reason or "Operator approved via GUI",
        )
        if result is None:
            return GovernanceResponse.error(f"Change {change_id} not found", code="not_found", status_code=404)

        logger.info(f"Audit change {change_id} approved by {approver}")
        return GovernanceResponse.success(data=result.to_dict(), message="audit_change_approved")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving audit change {change_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/audit/reject/{change_id}")
def reject_audit_change(
    change_id: str,
    body: AuditApprovalBody,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator rejects a pending audit change record.
    操作员拒绝待处理的审计变更记录。
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        _require_operator_role(actor)
        if hub._change_audit_log is None:
            return GovernanceResponse.error("Change audit log not available", code="log_unavailable", status_code=503)

        rejector = actor.actor_id
        rejection_reason = body.reason.strip() if body.reason.strip() else "Operator rejected via GUI"
        result = hub._change_audit_log.reject_change(
            change_id=change_id,
            rejected_by=rejector,
            rejection_reason=rejection_reason,
        )
        if result is None:
            return GovernanceResponse.error(f"Change {change_id} not found", code="not_found", status_code=404)

        logger.info(f"Audit change {change_id} rejected by {rejector}")
        return GovernanceResponse.success(data=result.to_dict(), message="audit_change_rejected")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting audit change {change_id}: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/audit/dismiss-all")
def dismiss_all_pending(
    body: AuditApprovalBody,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Operator dismisses (approves) ALL pending audit changes in one action.
    操作员一键清除所有待审核的审计变更。
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        _require_operator_role(actor)
        if hub._change_audit_log is None:
            return GovernanceResponse.success(data={"dismissed": 0}, message="audit_log_empty")

        pending = hub._change_audit_log.get_pending_approvals()
        approver = actor.actor_id
        reason = body.reason.strip() if body.reason.strip() else "Operator bulk dismissed via GUI"
        dismissed = 0
        for record in pending:
            try:
                hub._change_audit_log.approve_change(
                    change_id=record.change_id,
                    approved_by=approver,
                    approval_reason=reason,
                )
                dismissed += 1
            except Exception:
                pass

        logger.info("Audit: %d pending changes dismissed by %s", dismissed, approver)
        return GovernanceResponse.success(
            data={"dismissed": dismissed},
            message="audit_all_dismissed",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error dismissing all pending: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/symbols/whitelist")
def get_symbol_whitelist(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get current symbol whitelist across all categories.
    获取所有品类的当前符号白名单。

    Returns symbol whitelist grouped by category.
    """
    try:
        # Lazy import to avoid circular dependencies
        from .paper_trading_routes import RISK_MANAGER

        if RISK_MANAGER is None:
            return GovernanceResponse.error(
                "Risk manager not available",
                code="manager_unavailable",
                status_code=503
            )

        whitelist_data = {}
        categories = ["spot", "linear", "inverse", "option"]

        for category in categories:
            try:
                cfg = RISK_MANAGER.get_category_config(category)
                if cfg is not None and hasattr(cfg, "allowed_symbols"):
                    whitelist_data[category] = cfg.allowed_symbols or []
                else:
                    whitelist_data[category] = []
            except Exception as e:
                logger.debug(f"Error getting whitelist for {category}: {e}")
                whitelist_data[category] = []

        return GovernanceResponse.success(data=whitelist_data, message="symbol_whitelist")
    except Exception as e:
        logger.error(f"Error getting symbol whitelist: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/symbols/whitelist")
def add_symbol_to_whitelist(
    body: SymbolWhitelistAddRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Add a symbol to the whitelist for a specific category.
    将符号添加到特定品类的白名单。

    Records change to ChangeAuditLog if available.
    """
    hub = _get_governance_hub()

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # Lazy import to avoid circular dependencies
        from .paper_trading_routes import RISK_MANAGER

        if RISK_MANAGER is None:
            return GovernanceResponse.error(
                "Risk manager not available",
                code="manager_unavailable",
                status_code=503
            )

        # Sanitize inputs
        sanitized_symbol = _sanitize_string(body.symbol.upper(), max_len=50)
        sanitized_category = _sanitize_string(body.category.lower(), max_len=50)

        # Get current config
        cfg = RISK_MANAGER.get_category_config(sanitized_category)
        old_whitelist = cfg.allowed_symbols if cfg and hasattr(cfg, "allowed_symbols") else []

        # Add symbol if not already present
        if sanitized_symbol not in old_whitelist:
            new_whitelist = old_whitelist + [sanitized_symbol]
            RISK_MANAGER.update_category_config(
                sanitized_category,
                {"allowed_symbols": new_whitelist}
            )

            # Record to change audit log if available
            if hub and hub._change_audit_log:
                try:
                    from .change_audit_log import ChangeType
                    hub._change_audit_log.record_change(
                        change_type=ChangeType.CONFIG_CHANGE,
                        who=actor.actor_id,
                        what=f"Symbol added to {sanitized_category} whitelist: {sanitized_symbol}",
                        reason="Operator whitelist management",
                        old_value=old_whitelist,
                        new_value=new_whitelist,
                        affected_components=["risk_manager", sanitized_category],
                    )
                except Exception as e:
                    logger.warning(f"Failed to record whitelist change: {e}")

            logger.info(
                "Symbol %s added to %s whitelist by %s",
                sanitized_symbol, sanitized_category, _sanitize_log(actor.actor_id),
            )

            return GovernanceResponse.success(
                data={
                    "symbol": sanitized_symbol,
                    "category": sanitized_category,
                    "status": "added",
                    "new_whitelist": new_whitelist,
                },
                message="symbol_added"
            )
        else:
            return GovernanceResponse.success(
                data={
                    "symbol": sanitized_symbol,
                    "category": sanitized_category,
                    "status": "already_exists",
                    "whitelist": old_whitelist,
                },
                message="symbol_already_in_whitelist"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding symbol to whitelist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.delete("/symbols/whitelist/{symbol}")
def remove_symbol_from_whitelist(
    symbol: str,
    category: str | None = None,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Remove a symbol from the whitelist.
    从白名单中删除符号。

    If category not specified, removes from all categories.
    """
    hub = _get_governance_hub()

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # Lazy import to avoid circular dependencies
        from .paper_trading_routes import RISK_MANAGER

        if RISK_MANAGER is None:
            return GovernanceResponse.error(
                "Risk manager not available",
                code="manager_unavailable",
                status_code=503
            )

        # Sanitize inputs
        sanitized_symbol = _sanitize_string(symbol.upper(), max_len=50)
        categories_to_update = []

        if category:
            sanitized_category = _sanitize_string(category.lower(), max_len=50)
            categories_to_update = [sanitized_category]
        else:
            categories_to_update = ["spot", "linear", "inverse", "option"]

        changes_made = []

        for cat in categories_to_update:
            try:
                cfg = RISK_MANAGER.get_category_config(cat)
                old_whitelist = cfg.allowed_symbols if cfg and hasattr(cfg, "allowed_symbols") else []

                if sanitized_symbol in old_whitelist:
                    new_whitelist = [s for s in old_whitelist if s != sanitized_symbol]
                    RISK_MANAGER.update_category_config(
                        cat,
                        {"allowed_symbols": new_whitelist}
                    )

                    changes_made.append(cat)

                    # Record to change audit log if available
                    if hub and hub._change_audit_log:
                        try:
                            from .change_audit_log import ChangeType
                            hub._change_audit_log.record_change(
                                change_type=ChangeType.CONFIG_CHANGE,
                                who=actor.actor_id,
                                what=f"Symbol removed from {cat} whitelist: {sanitized_symbol}",
                                reason="Operator whitelist management",
                                old_value=old_whitelist,
                                new_value=new_whitelist,
                                affected_components=["risk_manager", cat],
                            )
                        except Exception as e:
                            logger.warning(f"Failed to record whitelist change: {e}")
            except Exception as e:
                logger.warning(f"Error updating whitelist for {cat}: {e}")

        if changes_made:
            logger.info(
                "Symbol %s removed from %s by %s",
                sanitized_symbol, ','.join(changes_made), _sanitize_log(actor.actor_id),
            )
            return GovernanceResponse.success(
                data={
                    "symbol": sanitized_symbol,
                    "categories_updated": changes_made,
                    "status": "removed",
                },
                message="symbol_removed"
            )
        else:
            return GovernanceResponse.success(
                data={
                    "symbol": sanitized_symbol,
                    "status": "not_found",
                },
                message="symbol_not_in_whitelist"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing symbol from whitelist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/leases")
def get_active_leases(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    List all active decision leases.
    列出所有活跃决策租约。

    Returns list of ACTIVE and BRIDGED leases.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        status = hub.get_status()
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")

        # 从 DecisionLeaseStateMachine 读取真实租约列表
        # Fetch real lease list from DecisionLeaseStateMachine
        all_leases: list[dict] = []
        live_leases: list[dict] = []
        if hub._lease_sm is not None:
            # get_all() 返回所有状态的租约（含终态）
            # get_all() returns leases in all states (including terminal)
            try:
                all_leases = [lease.to_dict() for lease in hub._lease_sm.get_all()]
            except Exception as _e:
                logger.warning(f"Failed to fetch all leases: {_e}")
            # get_live() 仅返回 ACTIVE + BRIDGED 的活跃租约
            # get_live() returns only ACTIVE and BRIDGED leases
            try:
                live_leases = [lease.to_dict() for lease in hub._lease_sm.get_live()]
            except Exception as _e:
                logger.warning(f"Failed to fetch live leases: {_e}")

        lease_detail = {
            "active_count": status.active_leases_count,
            "total_tracked": status.total_leases_tracked,
            # 活跃租约（ACTIVE + BRIDGED）/ Live leases (ACTIVE + BRIDGED only)
            "leases": live_leases,
            # 全量快照（所有状态）/ Full snapshot (all states including terminal)
            "all_leases": all_leases,
        }

        return GovernanceResponse.success(data=lease_detail, message="leases_list")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leases: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/events")
def get_governance_events(
    limit: int = 50,
    event_type: str | None = None,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    T9A.02: Retrieve governance events from the event stream.
    检索治理事件流中的治理事件。

    Query Parameters:
      - limit: Maximum number of events to return (default 50, max 1000)
      - event_type: Optional filter by event type/category (e.g., "risk_governor", "authorization", "reconciliation")

    Returns list of governance events in reverse chronological order (most recent first).
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        # Validate limit parameter
        if limit < 1 or limit > 1000:
            limit = min(max(limit, 1), 1000)

        # Retrieve events from governance hub
        events = hub.get_governance_events(limit=limit, event_type=event_type)

        return GovernanceResponse.success(
            data={
                "events": events,
                "count": len(events),
                "limit": limit,
                "event_type_filter": event_type,
            },
            message="governance_events_retrieved"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving governance events: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/learning-tier/status")
def get_learning_tier_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    T10.04: Retrieve current learning tier gate status and capabilities.
    检索当前学习层级门控状态和能力。

    Returns tier level, available capabilities, and promotion history.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        tier_status = hub.get_learning_tier_status()
        return GovernanceResponse.success(
            data=tier_status,
            message="learning_tier_status_retrieved"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving learning tier status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/learning-tier/promote")
def promote_learning_tier(
    request: dict[str, Any],
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    T10.04: Manually promote learning tier (operator only).
    手动晋升学习层级（仅限操作员）。

    Body: {target_tier: int, reason: str, approved_by: str}
    """
    _require_operator_role(actor)

    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        gate = hub._learning_tier_gate
        if gate is None:
            raise HTTPException(status_code=503, detail="LearningTierGate not configured")

        target_tier = request.get("target_tier")
        reason = html.escape(str(request.get("reason", "Manual promotion")))
        approved_by = html.escape(str(request.get("approved_by", "operator")))

        if target_tier is None or not isinstance(target_tier, int):
            raise HTTPException(status_code=400, detail="target_tier (int) is required")

        result = gate.promote_tier(
            target_tier=target_tier,
            reason=reason,
            initiator_name=approved_by,
        )

        return GovernanceResponse.success(
            data={"promoted": result is not None, "target_tier": target_tier},
            message="learning_tier_promotion_processed"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error promoting learning tier: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/oms/orders")
def get_oms_orders(
    state: str | None = None,
    limit: int = 50,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    T10.05: Retrieve OMS order states for governance visibility.
    检索 OMS 订单状态以提供治理可见性。

    Query Parameters:
      - state: Optional filter by OrderState name (e.g., "PENDING", "RECONCILING")
      - limit: Maximum number of orders to return (default 50)
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        if limit < 1 or limit > 500:
            limit = min(max(limit, 1), 500)

        orders = hub.get_oms_orders(state=state, limit=limit)

        return GovernanceResponse.success(
            data={
                "orders": orders,
                "count": len(orders),
                "state_filter": state,
                "limit": limit,
            },
            message="oms_orders_retrieved"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving OMS orders: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/health-check")
def governance_health_check(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Health check for governance hub and all SMs.
    治理集线器和所有 SM 的健康检查。

    Returns status of each SM and overall governance health.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    try:
        status = hub.get_status()
        health = {
            "overall_health": "ok" if status.enabled else "disabled",
            "enabled": status.enabled,
            "mode": status.mode,
            "is_authorized": hub.is_authorized(),
            "components": {
                "authorization": {"status": status.auth_state or "unavailable"},
                "risk_governor": {"status": status.risk_level_name or "unavailable"},
                "decision_lease": {"active": status.active_leases_count},
                "reconciliation": {"last_result": status.last_reconciliation_result or "never_run"},
            },
            "error_count": status.callback_errors,
            "incident_count": status.incident_count,
        }

        return GovernanceResponse.success(data=health, message="health_check")
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


# ── Batch 12: Paper→Live Gate Endpoints ──
# Batch 12：纸盘→实盘闸门端点

@governance_router.get("/paper-live-gate/status")
def get_paper_live_gate_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get PaperLiveGate status (last evaluation result or "not_evaluated").
    获取 PaperLiveGate 状态（最后评估结果或"未评估"）。

    Returns:
        Current gate status: "not_evaluated", "closed" (conditions not met), or "open" (ready for transition)
    """
    gate = _get_paper_live_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="PaperLiveGate not available")

    try:
        raw_status = gate.get_gate_status() if hasattr(gate, 'get_gate_status') else None
        status_info = raw_status.to_dict() if raw_status is not None and hasattr(raw_status, 'to_dict') else {"status": "not_evaluated"}
        return GovernanceResponse.success(data=status_info, message="paper_live_gate_status")
    except Exception as e:
        logger.error(f"Error getting PaperLiveGate status: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/paper-live-gate/evaluate")
def evaluate_paper_live_gate(
    request: PaperLiveGateEvaluateRequest,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Trigger PaperLiveGate evaluation with provided metrics.
    使用提供的指标触发 PaperLiveGate 评估。

    Parameters (from request body):
      - paper_start_time_ms: Paper trading start timestamp (ms)
      - total_trades: Total completed round-trip trades
      - win_rate_percent: Win rate as percentage (0-100)
      - net_pnl: Net profit/loss (can be negative)
      - sharpe_ratio: Sharpe ratio (can be negative)
      - max_drawdown_percent: Maximum drawdown as percentage
      - profit_factor: Profit factor (gross profit / gross loss, >= 0)
      - audit_trail_completeness_percent: Audit trail completeness (default: 99.0)
      - reconciliation_mismatch_percent: Reconciliation mismatch percentage (default: 0.0)
      - consecutive_losses: Consecutive losses count (default: 0)
      - has_major_incidents: Whether there are major incidents (default: False)

    Returns:
        Evaluation result: gate_status, passed_conditions, failed_conditions
    """
    gate = _get_paper_live_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="PaperLiveGate not available")

    hub = _get_governance_hub()

    try:
        # SECURITY FIX: Require Operator role
        _require_operator_role(actor)

        # Prepare evaluation metrics dict from request
        metrics = {
            "paper_start_time_ms": request.paper_start_time_ms,
            "total_trades": request.total_trades,
            "win_rate_percent": request.win_rate_percent,
            "net_pnl": request.net_pnl,
            "sharpe_ratio": request.sharpe_ratio,
            "max_drawdown_percent": request.max_drawdown_percent,
            "profit_factor": request.profit_factor,
            "audit_trail_completeness_percent": request.audit_trail_completeness_percent,
            "reconciliation_mismatch_percent": request.reconciliation_mismatch_percent,
            "consecutive_losses": request.consecutive_losses,
            "has_major_incidents": request.has_major_incidents,
        }

        # Evaluate the gate
        result = gate.evaluate_gate(**metrics) if hasattr(gate, 'evaluate_gate') else {"status": "error", "reason": "evaluate_gate method not found"}

        # Convert GateCheckResult to dict for JSON response / 转换为 dict 以便 JSON 响应
        result_dict = result.to_dict() if hasattr(result, 'to_dict') else result
        gate_status_str = result.gate_status.value if hasattr(result, 'gate_status') else str(result)

        # Record to ChangeAuditLog if available
        if hub is not None and hub._change_audit_log is not None:
            try:
                from .change_audit_log import ChangeType
                hub._change_audit_log.record_change(
                    change_type=ChangeType.STATE_CHANGE,
                    who=actor.actor_id if hasattr(actor, "actor_id") else "unknown",
                    what=f"PaperLiveGate evaluation: {gate_status_str}",
                    reason="API evaluation request",
                    old_value=None,
                    new_value=gate_status_str,
                )
            except Exception as e:
                logger.warning("Failed to record PaperLiveGate evaluation to ChangeAuditLog: %s", e)

        return GovernanceResponse.success(
            data=result_dict,
            message="paper_live_gate_evaluated"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error evaluating PaperLiveGate: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/h0-gate/status")
def get_h0_gate_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Get H0 Gate current state and statistics (P1-16).
    獲取 H0 確定性門控當前狀態與統計數據（P1-16）。

    Returns current config, health snapshot, risk snapshot, tracked symbols,
    and accumulated check statistics for monitoring and observability.
    返回當前配置、健康快照、風控快照、追蹤符號數及累積檢查統計。

    Read-only endpoint — no state mutation. Authenticated users only (no Operator role required).
    只讀端點，不修改任何狀態。僅需認證用戶（無需 Operator 角色）。
    """
    gate = _get_h0_gate()
    if gate is None:
        raise HTTPException(status_code=503, detail="H0Gate not available")

    try:
        state = gate.get_current_state()
        if state is None:
            raise HTTPException(status_code=500, detail="H0Gate state unavailable")

        # 1B-2: Compute freshness diagnostic fields from gate internals.
        # H0Gate._price_ts is a symbol→timestamp_ms dict updated on every tick.
        # We expose the most-recent entry's age so the GUI / monitoring can show
        # how stale the freshest data is, without modifying the hot path.
        # getattr with {} default ensures graceful handling of mocks / missing attr.
        #
        # 1B-2: 從 H0Gate 內部計算新鮮度診斷字段。
        # H0Gate._price_ts 是幣種→時間戳（ms）的字典，每個 tick 更新。
        # 這裡暴露最新一筆的數據年齡，讓 GUI/監控顯示數據新鮮程度，不影響熱路徑。
        # 使用 isinstance(dict) 確保 getattr 拿到的是真實字典而非 mock 物件。
        now_ms = int(time.time() * 1000)
        raw_price_ts = getattr(gate, "_price_ts", None)
        # Only use the attribute if it is a real dict; mocks/None → treat as empty.
        # 只有在屬性確實為 dict 時才使用；mock/None 視為空字典。
        price_ts_dict: dict = raw_price_ts if isinstance(raw_price_ts, dict) else {}
        if price_ts_dict:
            # Use the most recent timestamp across all tracked symbols as the
            # "best case" freshness indicator.
            # 使用所有追蹤幣種中最新的時間戳作為「最佳情況」新鮮度指標。
            latest_ts = max(price_ts_dict.values())
            freshness_age_ms: int | None = now_ms - latest_ts
        else:
            # No price data at all — no freshness information available.
            # 尚無任何 tick 數據，新鮮度信息不可用。
            freshness_age_ms = None

        # freshness_score: 1.0 = perfectly fresh, 0.0 = stale/no data.
        # Linear decay: score = max(0, 1 - age_ms / max_data_age_ms).
        # freshness_score：1.0 = 完全新鮮，0.0 = 過期/無數據。
        # 線性衰減：score = max(0, 1 - age_ms / max_data_age_ms)。
        if freshness_age_ms is not None:
            # Safely read max_data_age_ms from config; default 1000ms if not a real int.
            # 安全讀取 max_data_age_ms；若不是整數（如 mock）則用 1000ms 默認值。
            raw_max_age = getattr(getattr(gate, "_config", None), "max_data_age_ms", 1000)
            max_age_ms: int = raw_max_age if isinstance(raw_max_age, int) and raw_max_age > 0 else 1000
            freshness_score: float | None = max(0.0, 1.0 - freshness_age_ms / max_age_ms)
        else:
            freshness_score = None

        return {
            "ok": True,
            "message": "h0_gate_status",
            "data": state,
            # Freshness diagnostic fields (1B-2 / H0Gate API extension):
            # NOTE: freshness is BLOCKING in the pipeline (fail-closed since Sprint 5a).
            # H0Gate.check() returning allowed=False causes intent to be skipped via `continue`.
            # This field is retained for API backward compatibility but the value reflects
            # the current enforced state: False = fail-closed, NOT advisory.
            # 新鮮度診斷字段（1B-2 / H0Gate API 擴充）：
            # 注意：freshness 在管線中為 fail-closed（Sprint 5a 起正式阻擋）。
            # H0Gate.check() 返回 allowed=False 時 intent 被跳過（continue）。
            # 此字段保留以維持 API 向後兼容，值已更新為 False 反映實際強制狀態。
            "freshness_age_ms": freshness_age_ms,
            "freshness_score": freshness_score,
            "data_quality_warn_only": False,  # fail-closed since Sprint 5a — NOT advisory / Sprint 5a 起為強制 fail-closed
        }
    except HTTPException:
        raise
    except Exception:
        logger.error("Error getting H0Gate status", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


__all__ = ["governance_router"]

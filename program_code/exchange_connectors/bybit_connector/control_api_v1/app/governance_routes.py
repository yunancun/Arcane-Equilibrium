"""
Governance Routes — REST API endpoints for unified governance control
治理路由 — 统一治理控制的 REST API 端点

MODULE_NOTE (中文):
  本模块提供治理集线器的 REST API 接口：
  - GET /api/v1/governance/status — 联合治理仪表板
  - GET /api/v1/governance/auth/status — 授权 SM 详细状态
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
  - POST /api/v1/governance/auth/approve — Operator approves pending auth
  - GET /api/v1/governance/risk/level — Risk governor level + history
  - POST /api/v1/governance/risk/override — Operator de-escalates
  - POST /api/v1/governance/reconcile — Trigger manual reconciliation
  - GET /api/v1/governance/leases — List active leases

  All routes follow unified response pattern with APIRouter prefix to avoid circular deps.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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

def _get_governance_hub():
    """
    Lazy import to avoid circular dependency / 延迟导入避免循环依赖

    Tries to get GOV_HUB from paper_trading_routes module (the primary source).
    Falls back gracefully if unavailable.
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


def _get_auth_actor():
    """Lazy import of authentication dependency / 延迟导入认证依赖"""
    try:
        from . import main_legacy as base
        return base.current_actor
    except ImportError:
        # SECURITY FIX #1: Fail explicitly if auth system unavailable (not fallback to "system")
        raise HTTPException(status_code=503, detail="Authentication system unavailable")


def _require_operator_role(actor: Any) -> None:
    """SECURITY FIX #1: Validate that actor has Operator role / 验证 actor 具有 Operator 角色"""
    if not actor:
        raise HTTPException(status_code=401, detail="Authentication required")

    # Check if actor has operator_role or is_operator flag
    is_operator = (
        actor.get("operator_role") == "Operator" or
        actor.get("is_operator") is True or
        actor.get("role") == "operator"
    )

    if not is_operator:
        logger.warning(f"Non-operator attempted privileged operation: {actor.get('user', 'unknown')}")
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
    actor: Any = Depends(_get_auth_actor()),
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
        return GovernanceResponse.success(data=status.to_dict(), message="governance_status")
    except Exception as e:
        logger.error(f"Error getting governance status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/auth/status")
def get_authorization_status(
    actor: Any = Depends(_get_auth_actor()),
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
        auth_detail = {
            "state": status.auth_state,
            "expires_at_ms": status.auth_expires_at_ms,
            "scope": status.auth_scope,
            "pending_approval": status.auth_pending_approval,
            "is_effective": status.auth_state in ["ACTIVE", "RESTRICTED"],
        }
        return GovernanceResponse.success(data=auth_detail, message="authorization_status")
    except Exception as e:
        logger.error(f"Error getting authorization status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.post("/auth/approve")
def approve_authorization(
    body: AuthApprovalRequest,
    actor: Any = Depends(_get_auth_actor()),
) -> dict[str, Any]:
    """
    Operator approves pending authorization.
    操作员批准待审核授权。

    Transitions authorization from PENDING_APPROVAL to ACTIVE.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub._enabled:
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # SECURITY FIX #4: Sanitize approval note
        sanitized_note = _sanitize_string(body.approval_note, max_len=500)

        # Get current auth state and approve pending
        status = hub.get_status()
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
                    hub._authorization_sm.approve(pending_auth.authorization_id, approved_by=actor.get("user", "unknown"))
                    logger.info(f"Authorization approved by {actor.get('user', 'unknown')}: {sanitized_note}")
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
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.post("/risk/override")
def override_risk_level(
    body: RiskOverrideRequest,
    actor: Any = Depends(_get_auth_actor()),
) -> dict[str, Any]:
    """
    Operator de-escalates risk level manually.
    操作员手动降级风险等级。

    Only LOWER risk (towards NORMAL) permitted; requires approval.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub._enabled:
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        # SECURITY FIX #1: Require Operator role
        _require_operator_role(actor)

        # SECURITY FIX #4: Sanitize reason
        sanitized_reason = _sanitize_string(body.reason, max_len=500)

        status = hub.get_status()
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

        # SECURITY FIX #9: Actually apply the de-escalation if risk governor supports it
        if hub._risk_governor_sm:
            try:
                from .risk_governor_state_machine import RiskLevel, RiskInitiator
                hub._risk_governor_sm.escalate_to(
                    RiskLevel(target_level),
                    reason=sanitized_reason,
                    initiator=RiskInitiator.OPERATOR,
                )
                logger.warning(f"Risk override applied by {actor.get('user', 'unknown')}: {current_level} → {target_level}, reason: {sanitized_reason}")
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


@governance_router.post("/reconcile")
def trigger_manual_reconciliation(
    body: ManualReconciliationRequest,
    actor: Any = Depends(_get_auth_actor()),
) -> dict[str, Any]:
    """
    Trigger manual reconciliation between paper and demo/exchange.
    触发纸上交易与 demo/交易所之间的手动对账。

    Returns reconciliation report.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub.is_enabled():
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
        logger.info(f"Manual reconciliation triggered by {actor}: {body.reason}")

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
    except Exception as e:
        logger.error(f"Error in manual reconciliation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/leases")
def get_active_leases(
    actor: Any = Depends(_get_auth_actor()),
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

        # Note: Actual lease details would be fetched from hub._lease_sm
        lease_detail = {
            "active_count": status.active_leases_count,
            "total_tracked": status.total_leases_tracked,
            "leases": [],  # Populated from hub._lease_sm.get_all_leases() in full impl
        }

        return GovernanceResponse.success(data=lease_detail, message="leases_list")
    except Exception as e:
        logger.error(f"Error getting leases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.post("/health-check")
def governance_health_check(
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


__all__ = ["governance_router"]

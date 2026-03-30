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
        actor = base.current_actor
        # FIX-02: Ensure we never return None silently
        if actor is None:
            raise HTTPException(status_code=401, detail="Authentication required")
        return actor
    except HTTPException:
        raise
    except ImportError:
        # SECURITY FIX #1: Fail explicitly if auth system unavailable (not fallback to "system")
        raise HTTPException(status_code=503, detail="Authentication system unavailable")


def _require_operator_role(actor: Any) -> None:
    """SECURITY FIX #1: Validate that actor has Operator role / 验证 actor 具有 Operator 角色"""
    if not actor or not isinstance(actor, dict):
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
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")
        return GovernanceResponse.success(data=status.to_dict(), message="governance_status")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting governance status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/status/detailed")
def get_detailed_governance_status(
    actor: Any = Depends(_get_auth_actor()),
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


@governance_router.post("/risk/de-escalation/request")
def request_de_escalation(
    body: DeEscalationRequest,
    actor: Any = Depends(_get_auth_actor()),
) -> dict[str, Any]:
    """
    Submit a de-escalation request for risk level.
    提交风险等级降级请求。

    Request will be queued for Operator approval before execution.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub._enabled:
        raise HTTPException(status_code=403, detail="Governance hub disabled")

    try:
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

        logger.info(f"De-escalation request submitted: {request_id} by {sanitized_requester}")

        return GovernanceResponse.success(
            data={
                "request_id": request_id,
                "target_level": body.target_level,
                "status": "pending_approval",
                "requested_by": sanitized_requester,
            },
            message="deescalation_requested"
        )
    except Exception as e:
        logger.error(f"Error submitting de-escalation request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/risk/de-escalation/{request_id}/approve")
def approve_de_escalation_request(
    request_id: str,
    body: ApproveDeEscalationRequest,
    actor: Any = Depends(_get_auth_actor()),
) -> dict[str, Any]:
    """
    Operator approves and executes a de-escalation request.
    操作员批准并执行降级请求。

    This will execute the risk level reduction if approved.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub._enabled:
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


@governance_router.get("/recovery/pending")
def get_pending_recovery_requests(
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.post("/recovery/{request_id}/approve")
def approve_recovery_request(
    request_id: str,
    actor: Any = Depends(_get_auth_actor()),
) -> dict[str, Any]:
    """
    Operator approves a pending recovery request.
    操作员批准待处理的恢复请求。

    Transitions recovery from PENDING to APPROVED and executes the recovery.
    """
    hub = _get_governance_hub()
    if hub is None:
        raise HTTPException(status_code=503, detail="Governance hub not available")

    if not hub._enabled:
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
            approved_by=actor.get("user", "unknown"),
        )

        if approval is None:
            return GovernanceResponse.error(
                "Failed to approve recovery request",
                code="approval_failed",
                status_code=500
            )

        logger.info(f"Recovery request approved by {actor.get('user', 'unknown')}: {request_id}")

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
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/audit/pending")
def get_pending_approvals(
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/symbols/whitelist")
def get_symbol_whitelist(
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.post("/symbols/whitelist")
def add_symbol_to_whitelist(
    body: SymbolWhitelistAddRequest,
    actor: Any = Depends(_get_auth_actor()),
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
                        who=actor.get("user", "unknown"),
                        what=f"Symbol added to {sanitized_category} whitelist: {sanitized_symbol}",
                        reason="Operator whitelist management",
                        old_value=old_whitelist,
                        new_value=new_whitelist,
                        affected_components=["risk_manager", sanitized_category],
                    )
                except Exception as e:
                    logger.warning(f"Failed to record whitelist change: {e}")

            logger.info(f"Symbol {sanitized_symbol} added to {sanitized_category} whitelist by {actor.get('user', 'unknown')}")

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
    actor: Any = Depends(_get_auth_actor()),
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
                                who=actor.get("user", "unknown"),
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
            logger.info(f"Symbol {sanitized_symbol} removed from {','.join(changes_made)} by {actor.get('user', 'unknown')}")
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
        # FIX-06: Null safety check
        if status is None:
            raise HTTPException(status_code=500, detail="Governance status unavailable")

        # Note: Actual lease details would be fetched from hub._lease_sm
        lease_detail = {
            "active_count": status.active_leases_count,
            "total_tracked": status.total_leases_tracked,
            "leases": [],  # Populated from hub._lease_sm.get_all_leases() in full impl
        }

        return GovernanceResponse.success(data=lease_detail, message="leases_list")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting leases: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/events")
def get_governance_events(
    limit: int = 50,
    event_type: str | None = None,
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/learning-tier/status")
def get_learning_tier_status(
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.post("/learning-tier/promote")
def promote_learning_tier(
    request: dict[str, Any],
    actor: Any = Depends(_get_auth_actor()),
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
        raise HTTPException(status_code=500, detail=str(e))


@governance_router.get("/oms/orders")
def get_oms_orders(
    state: str | None = None,
    limit: int = 50,
    actor: Any = Depends(_get_auth_actor()),
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

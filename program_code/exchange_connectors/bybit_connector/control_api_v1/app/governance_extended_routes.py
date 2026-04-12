"""
Governance Extended Routes — Audit, leases, events, learning tier, health, gate endpoints.
治理擴展路由 — 審計、租約、事件、學習層級、健康檢查、門控端點。

MODULE_NOTE (EN): Extracted from governance_routes.py (FIX-08 file size).
  Contains audit approval, lease, event, learning tier, OMS, health check,
  PaperLiveGate, and H0Gate endpoints. All routes registered on the shared
  governance_router imported from governance_routes.
MODULE_NOTE (中): 從 governance_routes.py 提取（FIX-08 文件大小）。
  包含審計批准、租約、事件、學習層級、OMS、健康檢查、
  PaperLiveGate 和 H0Gate 端點。所有路由註冊在共享 governance_router 上。
"""

from __future__ import annotations

import html
import logging
import time
from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from . import governance_routes as _gov
from .governance_routes import (
    GovernanceResponse,
    PaperLiveGateEvaluateRequest,
    _get_auth_actor,
    _require_operator_role,
    governance_router,
)

# Use module-level access for patchability in tests (tests patch governance_routes._get_*)
# 使用模組級別存取以便測試中可 patch（測試 patch governance_routes._get_*）
def _get_governance_hub():
    return _gov._get_governance_hub()

def _get_h0_gate():
    return _gov._get_h0_gate()

def _get_paper_live_gate():
    return _gov._get_paper_live_gate()

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# Audit Approval Endpoints / 審計批准端點
# ═══════════════════════════════════════════════════════════════════════════════

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

        logger.info("Audit change %s approved by %s", change_id, approver)
        return GovernanceResponse.success(data=result.to_dict(), message="audit_change_approved")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error approving audit change %s: %s", change_id, e)
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

        logger.info("Audit change %s rejected by %s", change_id, rejector)
        return GovernanceResponse.success(data=result.to_dict(), message="audit_change_rejected")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error rejecting audit change %s: %s", change_id, e)
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


# DEAD-PY-1: Symbol Whitelist endpoints removed (T5.04, ARCH-RC1 1C-3-F, 2026-04-08).
# Scanner + Guardian + H0 Gate provide sufficient filtering — whitelist was redundant.
# GUI cleanup tracked in WP-CLEANUP-WHITELIST-UI (tab-governance.html + governance.js).
# Symbol 白名單端點已移除（T5.04）；GUI 清理見 WP-CLEANUP-WHITELIST-UI。


# ═══════════════════════════════════════════════════════════════════════════════
# Lease & Event Endpoints / 租約和事件端點
# ═══════════════════════════════════════════════════════════════════════════════

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
                logger.warning("Failed to fetch all leases: %s", _e)
            # get_live() 仅返回 ACTIVE + BRIDGED 的活跃租约
            # get_live() returns only ACTIVE and BRIDGED leases
            try:
                live_leases = [lease.to_dict() for lease in hub._lease_sm.get_live()]
            except Exception as _e:
                logger.warning("Failed to fetch live leases: %s", _e)

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
        logger.error("Error getting leases: %s", e)
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
      - event_type: Optional filter by event type/category

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
        logger.error("Error retrieving governance events: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ═══════════════════════════════════════════════════════════════════════════════
# Learning Tier & OMS Endpoints / 學習層級和 OMS 端點
# ═══════════════════════════════════════════════════════════════════════════════

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
        logger.error("Error retrieving learning tier status: %s", e)
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
        logger.error("Error promoting learning tier: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.get("/oms/orders")
def get_oms_orders(
    state: str | None = None,
    limit: int = 50,
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Order history endpoint — Python OMS removed 2026-04-10.
    Order lifecycle now tracked in Rust: trading.orders + trading.order_state_changes.
    訂單歷史端點 — Python OMS 已移除，訂單生命週期由 Rust 寫入 trading.orders。

    Returns empty list; order data is in DB table trading.orders (engine_mode column discriminates paper/demo/live).
    """
    return GovernanceResponse.success(
        data={
            "orders": [],
            "count": 0,
            "state_filter": state,
            "limit": limit,
            "note": "Order tracking migrated to Rust DB (trading.orders). Query DB directly.",
        },
        message="oms_orders_retrieved"
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Health Check & Gate Endpoints / 健康檢查和門控端點
# ═══════════════════════════════════════════════════════════════════════════════

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
        logger.error("Error in health check: %s", e)
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
        logger.error("Error getting PaperLiveGate status: %s", e)
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
      - paper_start_time_ms, total_trades, win_rate_percent, net_pnl, sharpe_ratio,
        max_drawdown_percent, profit_factor, audit_trail_completeness_percent,
        reconciliation_mismatch_percent, consecutive_losses, has_major_incidents

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
                    auto_approve=True,
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
        now_ms = int(time.time() * 1000)
        raw_price_ts = getattr(gate, "_price_ts", None)
        price_ts_dict: dict = raw_price_ts if isinstance(raw_price_ts, dict) else {}
        if price_ts_dict:
            latest_ts = max(price_ts_dict.values())
            freshness_age_ms: int | None = now_ms - latest_ts
        else:
            freshness_age_ms = None

        # freshness_score: 1.0 = perfectly fresh, 0.0 = stale/no data.
        if freshness_age_ms is not None:
            raw_max_age = getattr(getattr(gate, "_config", None), "max_data_age_ms", 1000)
            max_age_ms: int = raw_max_age if isinstance(raw_max_age, int) and raw_max_age > 0 else 1000
            freshness_score: float | None = max(0.0, 1.0 - freshness_age_ms / max_age_ms)
        else:
            freshness_score = None

        return {
            "ok": True,
            "message": "h0_gate_status",
            "data": state,
            # Freshness diagnostic fields (1B-2 / H0Gate API extension)
            "freshness_age_ms": freshness_age_ms,
            "freshness_score": freshness_score,
            "data_quality_warn_only": False,  # fail-closed since Sprint 5a
        }
    except HTTPException:
        raise
    except Exception:
        logger.error("Error getting H0Gate status", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")

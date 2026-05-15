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

  - GET /api/v1/governance/promotion-pipeline/status — 策略漸進放權管線狀態（6-01）
  - POST /api/v1/governance/promotion-pipeline/promote — 晉升策略階段（6-02）
  - POST /api/v1/governance/promotion-pipeline/operator-decision — Operator Live 審批（6-03）

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

  - GET /api/v1/governance/promotion-pipeline/status — Strategy promotion pipeline status (6-01)
  - POST /api/v1/governance/promotion-pipeline/promote — Promote strategy stage (6-02)
  - POST /api/v1/governance/promotion-pipeline/operator-decision — Operator live approval (6-03)

  All routes follow unified response pattern with APIRouter prefix to avoid circular deps.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, Field
import hmac
import html

from .live_halt_recovery import (
    LIVE_HALT_REQUEST_ID,
    approve_live_halt_recovery,
    build_live_halt_recovery_request,
    is_live_halt_recovery_request,
)

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


def _require_operator_auth(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
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
    actor = _get_auth_actor(request, authorization)
    _require_operator_role(actor)
    return actor


def _get_auth_actor(
    request: Request,
    authorization: str | None = Header(default=None),
) -> Any:
    """
    FastAPI dependency — validates auth via HttpOnly cookie (GUI) or Bearer token (API clients).
    FastAPI 依赖 — 通过 HttpOnly cookie（GUI）或 Bearer token（API 客户端）验证认证。

    Cookie takes priority; Authorization header is fallback for programmatic access.
    Cookie 優先；Authorization header 作為編程接口的後備。

    Called by FastAPI at request time (use as Depends(_get_auth_actor) WITHOUT parentheses).
    由 FastAPI 在請求時調用（使用 Depends(_get_auth_actor)，不加括號）。
    """
    try:
        from . import main_legacy as base
    except ImportError:
        raise HTTPException(status_code=503, detail="Authentication system unavailable")

    token: str | None = None

    # Priority 1: HttpOnly cookie (XSS-safe, set by /api/v1/auth/login)
    # 優先級 1：HttpOnly cookie（防 XSS，由登入端點設置）
    cookie_token = request.cookies.get("oc_auth_token")
    if cookie_token:
        token = cookie_token

    # Priority 2: Authorization header (for programmatic API clients)
    # 優先級 2：Authorization header（供編程 API 客戶端使用）
    if token is None and authorization is not None and authorization.startswith("Bearer "):
        token = authorization.replace("Bearer ", "", 1).strip()

    if token is None:
        raise HTTPException(status_code=401, detail="Authentication required")
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


def _record_live_halt_recovery_audit(hub: Any, who: str, result: dict[str, Any]) -> None:
    """Fail-soft audit for operator-approved Live halt recovery."""
    if hub is None or getattr(hub, "_change_audit_log", None) is None:
        logger.warning(
            "live_halt_recovery: change_audit_log unavailable — operator=%s",
            _sanitize_log(who),
        )
        return

    try:
        from .change_audit_log import ChangeType

        hub._change_audit_log.record_change(
            change_type=ChangeType.STATE_CHANGE,
            who=who,
            what="Live halt recovery approved (engine=live)",
            reason="operator approved live risk reset before signed auth renewal",
            old_value={
                "request_id": result.get("request_id"),
                "status": "live_halted",
                "snapshot": (result.get("request") or {}).get("evidence", {}),
            },
            new_value={
                "status": result.get("status"),
                "reset": result.get("reset"),
                "offline_reset": result.get("offline_reset"),
                "unhalt": result.get("unhalt"),
                "next_step": result.get("next_step"),
            },
            affected_components=[
                "live_halt",
                "paper_state:live",
                "paper_state:live_demo",
                "trading.paper_state_checkpoint",
                "live_authorization",
            ],
            auto_approve=True,
        )
    except Exception as exc:
        logger.warning("live_halt_recovery: change_audit_log write failed: %s", exc)


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


_LEASE_ROUTER_TRUE_VALUES = {"1", "true", "yes", "on"}


def _lease_router_env_snapshot() -> tuple[bool | None, str | None]:
    """
    Return API-process env fallback for the Rust lease-router flag.
    返回 API 进程环境中的 Rust lease-router 旗标后备快照。
    """
    raw = os.environ.get("OPENCLAW_LEASE_ROUTER_GATE_ENABLED")
    if raw is None:
        return None, None
    return raw.strip().lower() in _LEASE_ROUTER_TRUE_VALUES, raw


async def _build_lease_router_status_payload(
    dispatcher: Any | None = None,
) -> dict[str, Any]:
    """
    Build a read-only Decision Lease router status payload for GUI display.
    为 GUI 构造只读 Decision Lease router 状态。

    Rust runtime state is authoritative when IPC is available. The API env var
    is only a degraded fallback so the GUI never hardcodes a false value.
    Rust runtime IPC 可用时是权威来源；API env 仅作降级后备，避免 GUI 硬编码 false。
    """
    env_enabled, env_raw = _lease_router_env_snapshot()
    fallback_status = (
        "unknown" if env_enabled is None else ("enabled" if env_enabled else "disabled")
    )
    payload: dict[str, Any] = {
        "enabled": env_enabled,
        "router_gate_enabled": env_enabled,
        "status": fallback_status,
        "source": "api_env_fallback" if env_enabled is not None else "unavailable",
        "ipc_available": False,
        "env_raw": env_raw,
        "audit_writer_configured": None,
        "risk_governor_tier": None,
        "paper_paused": None,
        "session_halted": None,
        "warning": "rust_ipc_unavailable",
    }

    try:
        if dispatcher is None:
            from .ipc_dispatch import one_shot_ipc_call  # noqa: PLC0415

            dispatcher = one_shot_ipc_call
        runtime = await dispatcher(
            "get_risk_runtime_status",
            params={},
            timeout=2.0,
            wrap_errors_as_http=False,
            error_context="lease_router_status",
        )
        if not isinstance(runtime, dict):
            raise ValueError("get_risk_runtime_status returned a non-object payload")
        lease_router = runtime.get("lease_router")
        if not isinstance(lease_router, dict):
            raise ValueError("get_risk_runtime_status missing lease_router")
        enabled = bool(lease_router.get("enabled"))
        payload.update(
            {
                "enabled": enabled,
                "router_gate_enabled": enabled,
                "status": "enabled" if enabled else "disabled",
                "source": "rust_ipc:get_risk_runtime_status",
                "ipc_available": True,
                "audit_writer_configured": bool(
                    lease_router.get("audit_writer_configured")
                ),
                "runtime_source": lease_router.get("source"),
                "scope": lease_router.get("scope"),
                "risk_governor_tier": runtime.get("governor_tier"),
                "paper_paused": runtime.get("paper_paused"),
                "session_halted": runtime.get("session_halted"),
                "warning": None,
            }
        )
    except Exception as exc:  # noqa: BLE001 - status endpoint must degrade visibly
        payload["error"] = _sanitize_log(exc, max_len=200)
    return payload


# ═══════════════════════════════════════════════════════════════════════════════
# Routes / 路由
# ═══════════════════════════════════════════════════════════════════════════════

@governance_router.get("/lease-router/status")
async def get_lease_router_status(
    actor: Any = Depends(_get_auth_actor),
) -> dict[str, Any]:
    """
    Return read-only Decision Lease router status for the Settings tab.
    返回 Settings 页只读 Decision Lease router 状态。
    """
    payload = await _build_lease_router_status_payload()
    return GovernanceResponse.success(data=payload, message="lease_router_status")


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
        logger.error("Error getting governance status: %s", e)
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
            logger.debug("Error getting recovery gate status: %s", e)
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
            logger.debug("Error getting change audit log status: %s", e)
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
            logger.debug("Error getting OMS status: %s", e)
            detailed["oms"] = None

        # DEAD-PY-2: BybitDemoConnector removed. Demo orders go through Rust IPC.
        # Demo 連接器已移除（DEAD-PY-2）。Demo 訂單通過 Rust IPC 執行。
        detailed["demo_connector"] = {"enabled": False, "connector_type": None}

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
        logger.error("Error getting detailed governance status: %s", e, exc_info=True)
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
        logger.error("Error getting authorization status: %s", e)
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
                logger.error("Error calling approval method: %s", e)
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
        logger.error("Error approving authorization: %s", e, exc_info=True)
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
        logger.error("Error getting risk level: %s", e)
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
                logger.error("Error applying risk de-escalation: %s", e)
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
        logger.error("Error in risk override: %s", e, exc_info=True)
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

        logger.info("De-escalation request approved: %s by %s", request_id, sanitized_approver)

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
        logger.error("Error approving de-escalation: %s", e, exc_info=True)
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
        logger.error("Error in manual reconciliation: %s", e, exc_info=True)
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
        pending = []
        if hub._recovery_gate is not None:
            pending = hub._recovery_gate.get_pending_requests()

        live_halt_request = build_live_halt_recovery_request()
        if live_halt_request is not None:
            existing_ids = {req.get("request_id") or req.get("id") for req in pending}
            if LIVE_HALT_REQUEST_ID not in existing_ids:
                pending = [live_halt_request, *pending]

        return GovernanceResponse.success(data=pending, message="recovery_pending_list")
    except Exception as e:
        logger.error("Error getting pending recovery requests: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


@governance_router.post("/recovery/{request_id}/approve")
async def approve_recovery_request(
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

        if is_live_halt_recovery_request(request_id):
            result = await approve_live_halt_recovery(str(actor.actor_id))
            _record_live_halt_recovery_audit(hub, str(actor.actor_id), result)
            logger.info(
                "Live halt recovery approved by %s: %s",
                _sanitize_log(actor.actor_id),
                request_id,
            )
            return GovernanceResponse.success(
                data=result,
                message="live_halt_recovery_approved",
            )

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
        logger.error("Error approving recovery request: %s", e, exc_info=True)
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
        logger.error("Error getting change history: %s", e)
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
        logger.error("Error getting pending approvals: %s", e)
        raise HTTPException(status_code=500, detail="Internal server error")


# ═══════════════════════════════════════════════════════════════════════════════
# Extended routes registered via side-effect imports (FIX-08 file size split).
# Routes are defined in governance_extended_routes.py and governance_promotion_routes.py
# but registered on governance_router via @governance_router.xxx decorators at import time.
# 擴展路由通過副作用導入註冊（FIX-08 文件大小拆分）。
# ═══════════════════════════════════════════════════════════════════════════════
from . import governance_extended_routes as _ext_routes  # noqa: F401 — registers routes on governance_router
from . import governance_promotion_routes as _promo_routes  # noqa: F401 — registers routes on governance_router

# Re-export extracted names for backward compatibility (tests import from governance_routes)
# 為向後兼容重導出提取的名稱（測試從 governance_routes 導入）
from .governance_extended_routes import (  # noqa: F401
    AuditApprovalBody,
    approve_audit_change,
    dismiss_all_pending,
    evaluate_paper_live_gate,
    get_active_leases,
    get_governance_events,
    get_h0_gate_status,
    get_learning_tier_status,
    get_oms_orders,
    get_paper_live_gate_status,
    governance_health_check,
    promote_learning_tier,
    reject_audit_change,
)
from .governance_promotion_routes import (  # noqa: F401
    get_promotion_pipeline_status,
    promote_strategy,
    set_promotion_operator_decision,
)


__all__ = ["governance_router"]

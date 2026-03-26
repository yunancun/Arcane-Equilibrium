"""
OpenClaw / Bybit Control API V1 RC2 - FastAPI skeleton
OpenClaw / Bybit 控制 API V1 RC2 - FastAPI 骨架

说明 / Notes:
- 本文件是“可落地的路由骨架”，不是完整业务实现。
- This file is an implementation-oriented routing skeleton, not the full business logic.
- 目标是让后续工程可以直接按统一模型、统一依赖、统一错误处理继续拆分模块。
- The goal is to let the engineering work continue with unified models, dependencies, and error handling.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, Protocol, TypeVar

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field


# -----------------------------------------------------------------------------
# Enums / 枚举
# -----------------------------------------------------------------------------

ActionResult = Literal["success", "failed", "blocked", "replayed"]
ConnectionState = Literal["ready", "degraded", "down", "unknown"]
RuntimeConnectionState = Literal["healthy", "degraded", "down", "unknown"]
CompletenessState = Literal["complete", "partial", "missing", "unknown"]
DemoState = Literal["closed", "armed_but_closed", "demo_enabled", "relocked"]
GateState = Literal["not_evaluated", "passed", "failed", "blocked"]


# -----------------------------------------------------------------------------
# Common models / 公共模型
# -----------------------------------------------------------------------------

T = TypeVar("T")


class RequestEnvelope(BaseModel):
    """统一 POST 请求 envelope / Unified POST request envelope."""

    request_id: str
    idempotency_key: str
    operator_id: str
    reason: str
    client_ts_ms: int
    expected_state_revision: int
    expected_previous_state: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SourceContext(BaseModel):
    """来源上下文 / Source and connector context."""

    readonly_connector_name: str | None = "bybit_prod_readonly_main"
    readonly_connector_role: str = "fact_source"
    readonly_connector_scope: str = "private_readonly"
    execution_connector_name: str | None = None
    execution_connector_role: str = "execution_source_reserved"
    execution_connector_scope: str = "not_attached"
    connector_role_separation_ok: bool = True
    rest_private_connection_state: ConnectionState = "unknown"
    ws_private_connection_state: ConnectionState = "unknown"
    runtime_connection_state: RuntimeConnectionState = "unknown"
    account_fact_completeness_state: CompletenessState = "unknown"
    source_snapshot_completeness_state: CompletenessState = "unknown"
    pinned_runtime_snapshot_id: str = ""
    pinned_runtime_snapshot_ts_ms: int = 0


class ResponseEnvelope(BaseModel, Generic[T]):
    """统一响应 envelope / Unified response envelope."""

    api_version: Literal["v1"] = "v1"
    schema_version: Literal["v1"] = "v1"
    request_id: str | None = None
    snapshot_ts_ms: int = 0
    snapshot_id: str = ""
    state_revision: int = 0
    action_result: ActionResult = "success"
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_ref: str | None = None
    source_context: SourceContext = Field(default_factory=SourceContext)
    data: T | dict[str, Any]


# -----------------------------------------------------------------------------
# Domain response models / 业务响应模型
# -----------------------------------------------------------------------------


class OverviewData(BaseModel):
    global_stage_label: str
    global_mode_state: str
    global_capability_state: str
    global_execution_authority_state: str


class RecheckResultData(BaseModel):
    chapter_key: str
    recheck_type: str
    recheck_state: str
    current_phase_ready: bool
    readiness_scope: str


class DemoValidateData(BaseModel):
    demo_state_switch: DemoState
    demo_prerequisites_gate_state: GateState
    demo_arm_gate_state: GateState
    demo_enable_gate_state: GateState
    demo_enable_reason_codes: list[str] = Field(default_factory=list)


class DemoTransitionData(BaseModel):
    demo_state_switch: DemoState
    previous_demo_state_switch: DemoState


class SafeBundleStepResult(BaseModel):
    step_key: str
    step_action_result: ActionResult
    step_reason_codes: list[str] = Field(default_factory=list)


class SafeBundleData(BaseModel):
    bundle_key: str
    bundle_steps: list[SafeBundleStepResult]
    final_demo_state_switch: DemoState


class InputAcceptedData(BaseModel):
    accepted: bool = True


class ConfigChangeAcceptedData(BaseModel):
    accepted_paths: list[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# Auth / 认证授权依赖
# -----------------------------------------------------------------------------


@dataclass
class AuthenticatedActor:
    """认证主体 / Authenticated actor."""

    actor_id: str
    actor_type: Literal["human", "service"]
    roles: set[str]
    scopes: set[str]


bearer_scheme = HTTPBearer(auto_error=False)


async def get_authenticated_actor(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> AuthenticatedActor:
    """
    认证入口 / Authentication entry.

    当前仅保留骨架；正式实现需在此校验 token、加载角色和 scope。
    This is only a skeleton. The real implementation must validate the token and
    load roles/scopes here.
    """

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"reason_codes": ["authentication_required"]},
        )

    # TODO: Replace with real token validation / 替换为真实令牌校验
    return AuthenticatedActor(
        actor_id="demo-operator",
        actor_type="human",
        roles={"operator_guarded", "viewer", "config_admin", "finance_input"},
        scopes={
            "state:read",
            "learning:read",
            "control:recheck",
            "control:validate",
            "control:arm",
            "control:enable",
            "control:relock",
            "control:bundle",
            "input:cost",
            "input:event",
            "input:note",
            "input:config",
        },
    )


def require_scope(required_scope: str):
    """Scope 依赖生成器 / Scope dependency factory."""

    async def _inner(actor: AuthenticatedActor = Depends(get_authenticated_actor)) -> AuthenticatedActor:
        if required_scope not in actor.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"reason_codes": ["scope_not_allowed"]},
            )
        return actor

    return _inner


def verify_operator_identity(envelope: RequestEnvelope, actor: AuthenticatedActor) -> None:
    """检查 operator_id 与认证主体一致 / Verify operator identity."""

    if envelope.operator_id != actor.actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_codes": ["operator_identity_mismatch"]},
        )


# -----------------------------------------------------------------------------
# Service protocols / 服务协议接口
# -----------------------------------------------------------------------------


class StateStore(Protocol):
    async def get_latest_snapshot(self) -> dict[str, Any]: ...
    async def commit_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]: ...


class SourceContextService(Protocol):
    async def build(self, snapshot: dict[str, Any]) -> SourceContext: ...


class IdempotencyService(Protocol):
    async def lookup(self, request_id: str, idempotency_key: str) -> dict[str, Any] | None: ...
    async def record(self, request_id: str, idempotency_key: str, result: dict[str, Any]) -> None: ...


class AuditService(Protocol):
    async def create_audit_ref(self, action_type: str) -> str: ...


# -----------------------------------------------------------------------------
# Dummy service implementations / 占位服务实现
# -----------------------------------------------------------------------------


class DummyStateStore:
    async def get_latest_snapshot(self) -> dict[str, Any]:
        return {
            "meta": {
                "snapshot_ts_ms": 0,
                "state_revision": 1,
            },
            "control_plane": {
                "demo_control": {
                    "demo_state_switch": "closed",
                    "demo_prerequisites_gate_state": "not_evaluated",
                    "demo_arm_gate_state": "not_evaluated",
                    "demo_enable_gate_state": "blocked",
                }
            },
        }

    async def commit_snapshot(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return snapshot


class DummySourceContextService:
    async def build(self, snapshot: dict[str, Any]) -> SourceContext:
        return SourceContext(
            rest_private_connection_state="ready",
            ws_private_connection_state="ready",
            runtime_connection_state="healthy",
            account_fact_completeness_state="complete",
            source_snapshot_completeness_state="complete",
            pinned_runtime_snapshot_id="runtime-snapshot-001",
            pinned_runtime_snapshot_ts_ms=0,
        )


class DummyIdempotencyService:
    async def lookup(self, request_id: str, idempotency_key: str) -> dict[str, Any] | None:
        return None

    async def record(self, request_id: str, idempotency_key: str, result: dict[str, Any]) -> None:
        return None


class DummyAuditService:
    async def create_audit_ref(self, action_type: str) -> str:
        return f"audit:{action_type}:demo"


state_store = DummyStateStore()
source_context_service = DummySourceContextService()
idempotency_service = DummyIdempotencyService()
audit_service = DummyAuditService()


# -----------------------------------------------------------------------------
# Router helpers / 路由辅助函数
# -----------------------------------------------------------------------------


def build_response(
    *,
    request_id: str | None,
    snapshot: dict[str, Any],
    source_context: SourceContext,
    data: BaseModel | dict[str, Any],
    action_result: ActionResult = "success",
    reason_codes: list[str] | None = None,
    warnings: list[str] | None = None,
    audit_ref: str | None = None,
) -> ResponseEnvelope[Any]:
    """统一响应组装器 / Unified response builder."""

    meta = snapshot.get("meta", {})
    return ResponseEnvelope[Any](
        request_id=request_id,
        snapshot_ts_ms=meta.get("snapshot_ts_ms", 0),
        snapshot_id=f"snapshot:{meta.get('state_revision', 0)}",
        state_revision=meta.get("state_revision", 0),
        action_result=action_result,
        reason_codes=reason_codes or [],
        warnings=warnings or [],
        audit_ref=audit_ref,
        source_context=source_context,
        data=data,
    )


async def get_current_snapshot_and_source() -> tuple[dict[str, Any], SourceContext]:
    snapshot = await state_store.get_latest_snapshot()
    source_context = await source_context_service.build(snapshot)
    return snapshot, source_context


# -----------------------------------------------------------------------------
# Routers / 路由
# -----------------------------------------------------------------------------

system_router = APIRouter(prefix="/api/v1/system", tags=["system"])
learning_router = APIRouter(prefix="/api/v1/learning", tags=["learning"])
control_router = APIRouter(prefix="/api/v1/control", tags=["control"])
input_router = APIRouter(prefix="/api/v1/input", tags=["input"])


@system_router.get("/overview", response_model=ResponseEnvelope[OverviewData])
async def get_system_overview(
    actor: AuthenticatedActor = Depends(require_scope("state:read")),
) -> ResponseEnvelope[OverviewData]:
    snapshot, source_context = await get_current_snapshot_and_source()
    data = OverviewData(
        global_stage_label="shadow_closeout_ready",
        global_mode_state="shadow_only",
        global_capability_state="shadow_control_ready",
        global_execution_authority_state="disabled",
    )
    return build_response(
        request_id=None,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
    )


@control_router.post("/demo/validate", response_model=ResponseEnvelope[DemoValidateData])
async def post_demo_validate(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor = Depends(require_scope("control:validate")),
) -> ResponseEnvelope[DemoValidateData]:
    verify_operator_identity(envelope, actor)

    # TODO: idempotency lookup / 幂等查重
    # TODO: revision check / revision 检查
    # TODO: source context availability checks / 来源可用性检查
    # TODO: execute validate handler / 执行 validate 处理器

    snapshot, source_context = await get_current_snapshot_and_source()
    audit_ref = await audit_service.create_audit_ref("demo_validate")

    data = DemoValidateData(
        demo_state_switch="closed",
        demo_prerequisites_gate_state="passed",
        demo_arm_gate_state="passed",
        demo_enable_gate_state="blocked",
        demo_enable_reason_codes=["not_armed"],
    )
    return build_response(
        request_id=envelope.request_id,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
        action_result="success",
        audit_ref=audit_ref,
    )


@control_router.post("/demo/arm", response_model=ResponseEnvelope[DemoTransitionData])
async def post_demo_arm(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor = Depends(require_scope("control:arm")),
) -> ResponseEnvelope[DemoTransitionData]:
    verify_operator_identity(envelope, actor)

    snapshot, source_context = await get_current_snapshot_and_source()
    audit_ref = await audit_service.create_audit_ref("demo_arm")

    data = DemoTransitionData(
        demo_state_switch="armed_but_closed",
        previous_demo_state_switch="closed",
    )
    return build_response(
        request_id=envelope.request_id,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
        action_result="success",
        audit_ref=audit_ref,
    )


@control_router.post("/demo/enable", response_model=ResponseEnvelope[DemoTransitionData])
async def post_demo_enable(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor = Depends(require_scope("control:enable")),
) -> ResponseEnvelope[DemoTransitionData]:
    verify_operator_identity(envelope, actor)

    snapshot, source_context = await get_current_snapshot_and_source()
    audit_ref = await audit_service.create_audit_ref("demo_enable")

    data = DemoTransitionData(
        demo_state_switch="demo_enabled",
        previous_demo_state_switch="armed_but_closed",
    )
    return build_response(
        request_id=envelope.request_id,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
        action_result="blocked",
        reason_codes=["live_mode_reserved_only"],
        audit_ref=audit_ref,
    )


@control_router.post("/demo/relock", response_model=ResponseEnvelope[DemoTransitionData])
async def post_demo_relock(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor = Depends(require_scope("control:relock")),
) -> ResponseEnvelope[DemoTransitionData]:
    verify_operator_identity(envelope, actor)

    snapshot, source_context = await get_current_snapshot_and_source()
    audit_ref = await audit_service.create_audit_ref("demo_relock")

    data = DemoTransitionData(
        demo_state_switch="relocked",
        previous_demo_state_switch="demo_enabled",
    )
    return build_response(
        request_id=envelope.request_id,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
        action_result="success",
        audit_ref=audit_ref,
    )


@control_router.post("/safe-recheck-bundle", response_model=ResponseEnvelope[SafeBundleData])
async def post_safe_recheck_bundle(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor = Depends(require_scope("control:bundle")),
) -> ResponseEnvelope[SafeBundleData]:
    verify_operator_identity(envelope, actor)

    snapshot, source_context = await get_current_snapshot_and_source()
    audit_ref = await audit_service.create_audit_ref("safe_recheck_bundle")

    data = SafeBundleData(
        bundle_key="default_safe_bundle",
        bundle_steps=[
            SafeBundleStepResult(step_key="j-canonical", step_action_result="success"),
            SafeBundleStepResult(step_key="k-canonical", step_action_result="success"),
            SafeBundleStepResult(step_key="demo-validate", step_action_result="success"),
        ],
        final_demo_state_switch="closed",
    )
    return build_response(
        request_id=envelope.request_id,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
        action_result="success",
        audit_ref=audit_ref,
    )


@input_router.post("/config-change", response_model=ResponseEnvelope[ConfigChangeAcceptedData])
async def post_config_change(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor = Depends(require_scope("input:config")),
) -> ResponseEnvelope[ConfigChangeAcceptedData]:
    verify_operator_identity(envelope, actor)

    # TODO: validate whitelist paths / 校验白名单路径
    # TODO: reject ACT / DRV / AUD writes / 拒绝 ACT / DRV / AUD 直写

    snapshot, source_context = await get_current_snapshot_and_source()
    audit_ref = await audit_service.create_audit_ref("config_change")

    data = ConfigChangeAcceptedData(
        accepted_paths=["global_runtime.controls.global_operator_mode_switch"],
    )
    return build_response(
        request_id=envelope.request_id,
        snapshot=snapshot,
        source_context=source_context,
        data=data,
        action_result="success",
        audit_ref=audit_ref,
    )


# -----------------------------------------------------------------------------
# Application factory / 应用工厂
# -----------------------------------------------------------------------------


def create_app() -> FastAPI:
    """创建 FastAPI 应用 / Create FastAPI application."""

    app = FastAPI(
        title="OpenClaw / Bybit Control API",
        version="v1-rc2",
        description="OpenClaw / Bybit Control API V1 RC2 skeleton",
    )
    app.include_router(system_router)
    app.include_router(learning_router)
    app.include_router(control_router)
    app.include_router(input_router)
    return app


app = create_app()

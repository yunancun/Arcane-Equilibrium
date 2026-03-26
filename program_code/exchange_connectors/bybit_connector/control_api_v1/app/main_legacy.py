from __future__ import annotations

"""
OpenClaw / Bybit Control API + GUI MVP
OpenClaw / Bybit 控制 API 与 GUI 的可运行 MVP

说明 / Notes:
- 这是一个面向当前 RC2 合同的可运行实现。
- This is a runnable implementation aligned with the current RC2 contract.
- 它默认保持 execution disabled / protected。
- It keeps execution disabled / protected by default.
- 后续若要接 OpenClaw runtime，只需要替换 source-context 与事实获取逻辑。
- To connect a real OpenClaw runtime later, replace the source-context and fact-loading logic.
"""

import copy
import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field


def _split_csv(value: str) -> set[str]:
    return {item.strip() for item in value.split(",") if item.strip()}


@dataclass(slots=True)
class Settings:
    api_prefix: str = "/api/v1"
    api_version: str = "v1"
    schema_version: str = "v1"
    service_name: str = "OpenClaw / Bybit Control API"
    gui_title: str = "OpenClaw / Bybit Control Center"

    api_token: str = field(default_factory=lambda: os.getenv("OPENCLAW_API_TOKEN", "change-me"))
    auth_actor_id: str = field(default_factory=lambda: os.getenv("OPENCLAW_AUTH_ACTOR_ID", "demo-operator"))
    auth_actor_type: str = field(default_factory=lambda: os.getenv("OPENCLAW_AUTH_ACTOR_TYPE", "human"))
    auth_roles: set[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv(
                "OPENCLAW_AUTH_ROLES",
                "viewer,operator,operator_guarded,config_admin,finance_input",
            )
        )
    )
    auth_scopes: set[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv(
                "OPENCLAW_AUTH_SCOPES",
                ",".join(
                    [
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
                    ]
                ),
            )
        )
    )
    state_file_path: str = field(
        default_factory=lambda: os.getenv(
            "OPENCLAW_STATE_FILE",
            os.path.abspath(
                os.path.join(
                    os.path.dirname(__file__),
                    "..",
                    "runtime",
                    "openclaw_bybit_control_state.json",
                )
            ),
        )
    )
    readonly_connector_name: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_READONLY_CONNECTOR_NAME", "bybit_prod_readonly_main")
    )
    execution_connector_name: str | None = field(
        default_factory=lambda: os.getenv("OPENCLAW_EXECUTION_CONNECTOR_NAME") or None
    )
    rest_private_connection_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_REST_PRIVATE_CONNECTION_STATE", "ready")
    )
    ws_private_connection_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_WS_PRIVATE_CONNECTION_STATE", "ready")
    )
    runtime_connection_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_RUNTIME_CONNECTION_STATE", "healthy")
    )
    account_fact_completeness_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_ACCOUNT_FACT_COMPLETENESS_STATE", "complete")
    )
    source_snapshot_completeness_state: str = field(
        default_factory=lambda: os.getenv("OPENCLAW_SOURCE_SNAPSHOT_COMPLETENESS_STATE", "complete")
    )


settings = Settings()

ActionResult = Literal["success", "failed", "blocked", "replayed"]
ConnectionState = Literal["ready", "degraded", "down", "unknown"]
RuntimeConnectionState = Literal["healthy", "degraded", "down", "unknown"]
CompletenessState = Literal["complete", "partial", "missing", "unknown"]
DemoState = Literal["closed", "armed_but_closed", "demo_enabled", "relocked"]
GateState = Literal["not_evaluated", "passed", "failed", "blocked"]
EffectiveRiskEnvelopeState = Literal["reserved", "configured", "blocking"]

T = TypeVar("T")


class RequestEnvelope(BaseModel):
    request_id: str
    idempotency_key: str
    operator_id: str
    reason: str
    client_ts_ms: int
    expected_state_revision: int
    expected_previous_state: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SourceContext(BaseModel):
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
    api_version: Literal["v1"] = "v1"
    schema_version: Literal["v1"] = "v1"
    request_id: str | None = None
    snapshot_ts_ms: int
    snapshot_id: str
    state_revision: int
    action_result: ActionResult
    reason_codes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    audit_ref: str | None = None
    source_context: SourceContext
    data: T


class OverviewData(BaseModel):
    global_runtime: dict[str, Any]
    chapter_status_summary: dict[str, Any]
    daily_business_summary: dict[str, Any]
    health_summary: dict[str, Any]
    demo_control_summary: dict[str, Any]
    latest_control_action_summary: dict[str, Any]
    latest_write_action_summary: dict[str, Any]


class RecheckResultData(BaseModel):
    chapter: str
    recheck_kind: str
    recheck_state: str
    last_verified_ts_ms: int
    chapter_snapshot: dict[str, Any]
    pinned_runtime_snapshot_id: str


class DemoValidateData(BaseModel):
    demo_state_switch: DemoState
    demo_prerequisites_gate_state: GateState
    demo_prerequisites_reason_codes: list[str] = Field(default_factory=list)
    demo_arm_gate_state: GateState
    demo_arm_reason_codes: list[str] = Field(default_factory=list)
    demo_enable_gate_state: GateState
    demo_enable_reason_codes: list[str] = Field(default_factory=list)
    demo_relock_gate_state: GateState
    demo_relock_reason_codes: list[str] = Field(default_factory=list)
    pinned_runtime_snapshot_id: str


class DemoTransitionData(BaseModel):
    demo_state_switch: DemoState
    previous_demo_state_switch: DemoState
    gate_state: GateState
    reason_codes: list[str] = Field(default_factory=list)
    pinned_runtime_snapshot_id: str


class SafeBundleStepResult(BaseModel):
    step_name: str
    action_result: ActionResult
    reason_codes: list[str] = Field(default_factory=list)
    audit_ref: str | None = None


class SafeBundleData(BaseModel):
    bundle_base_snapshot_id: str
    bundle_final_snapshot_id: str
    bundle_committed: bool
    steps: list[SafeBundleStepResult]


class InputAcceptedData(BaseModel):
    accepted: bool = True
    record_count_delta: int = 0


class ConfigChangeAcceptedData(BaseModel):
    accepted_paths: list[str] = Field(default_factory=list)
    rejected_paths: list[str] = Field(default_factory=list)


class LearningOverviewData(BaseModel):
    summary: dict[str, Any]
    experiments: dict[str, Any]
    approval_requirements: dict[str, Any]


class LearningHypothesesData(BaseModel):
    hypotheses: list[dict[str, Any]]
    experiments: list[dict[str, Any]]
    approval_requirements: dict[str, Any]


class ProductFamilyConfigData(BaseModel):
    """
    产品族配置写操作结果 / Result of a product family configuration write operation.

    包含已应用的变更、被拒绝的字段及当前状态快照。
    Contains applied changes, rejected fields, and the current state snapshot.
    """

    family: str
    applied_changes: dict[str, Any]
    rejected_fields: list[str] = Field(default_factory=list)
    current_controls: dict[str, Any]
    current_derived: dict[str, Any]
    current_action_permissions: dict[str, Any]


class PnLEntryData(BaseModel):
    """
    PnL 条目录入结果 / Result of a PnL entry record operation.

    记录一次已实现 / 未实现盈亏更新的确认信息。
    Records confirmation of a realized / unrealized PnL update.
    """

    accepted: bool = True
    entry_type: str
    delta_realized_pnl: float = 0.0
    delta_unrealized_pnl: float = 0.0
    record_count_delta: int = 1


class BusinessSummaryData(BaseModel):
    """
    经营与收益完整汇总 / Complete business and income summary.

    比 /system/business/daily 更丰富：包含历史条目列表和成本分解。
    Richer than /system/business/daily: includes historical entry lists and cost breakdown.
    """

    daily: dict[str, Any]
    cost_entries_recent: list[dict[str, Any]] = Field(default_factory=list)
    event_entries_recent: list[dict[str, Any]] = Field(default_factory=list)
    pnl_entries_recent: list[dict[str, Any]] = Field(default_factory=list)
    cost_breakdown: dict[str, Any] = Field(default_factory=dict)
    entry_totals: dict[str, Any] = Field(default_factory=dict)


def now_ms() -> int:
    return int(time.time() * 1000)


ACTION_NAMES = [
    "new_order",
    "cancel",
    "amend",
    "reduce_only",
    "increase_position",
    "close_position",
]

PRODUCT_FAMILIES = [
    "spot",
    "margin",
    "perp_linear",
    "perp_inverse",
    "options",
    "other_derivatives_reserved",
]

CONFIG_CHANGE_WHITELIST = {
    "meta.environment",
    "global_runtime.controls.global_execution_mode_switch",
    "global_runtime.controls.global_operator_mode_switch",
    "control_plane.demo_control.demo_operator_ack_required",
    "control_plane.risk_envelope.risk_policy_switch",
    "control_plane.risk_envelope.risk_policy_profile",
    "learning_state.experiments.approval_required",
}
for pf in PRODUCT_FAMILIES:
    CONFIG_CHANGE_WHITELIST.add(f"product_family_status.{pf}.controls.enabled_switch")
    CONFIG_CHANGE_WHITELIST.add(f"product_family_status.{pf}.controls.visibility_switch")
    CONFIG_CHANGE_WHITELIST.add(f"product_family_status.{pf}.controls.mode_switch")
    for action_name in ACTION_NAMES:
        CONFIG_CHANGE_WHITELIST.add(
            f"control_plane.action_permissions.global.configured_{action_name}_allowed_switch"
        )
        CONFIG_CHANGE_WHITELIST.add(
            f"control_plane.action_permissions.by_product_family.{pf}.configured_{action_name}_allowed_switch"
        )


def _permission_block(configured: bool = False) -> dict[str, Any]:
    block: dict[str, Any] = {}
    for action_name in ACTION_NAMES:
        block[f"configured_{action_name}_allowed_switch"] = configured
        block[f"effective_{action_name}_allowed_state"] = "disabled"
        block[f"effective_{action_name}_reason_codes"] = []
    return block


def deep_set(container: dict[str, Any], path: str, value: Any) -> None:
    pieces = path.split(".")
    current = container
    for piece in pieces[:-1]:
        current = current[piece]
    current[pieces[-1]] = value


def build_snapshot_id(state: dict[str, Any]) -> str:
    revision = state["meta"]["state_revision"]
    meta = {
        "revision": revision,
        "global_execution_mode_switch": state["global_runtime"]["controls"]["global_execution_mode_switch"],
        "demo_state_switch": state["control_plane"]["demo_control"]["demo_state_switch"],
        "risk_state": state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"],
        "updated_ts": state["meta"]["snapshot_ts_ms"],
    }
    payload = json.dumps(meta, ensure_ascii=False, sort_keys=True).encode("utf-8")
    digest = hashlib.sha1(payload).hexdigest()[:12]
    return f"snapshot:{revision}:{digest}"


def _compile_global_stage_label(state: dict[str, Any]) -> str:
    controls = state["global_runtime"]["controls"]
    chapter_status = state["chapter_status"]

    if controls["global_execution_mode_switch"] == "live_reserved":
        return "future_live_reserved"
    if (
        chapter_status["K"]["current_phase_ready"] is True
        and chapter_status["K"]["readiness_scope"] == "design_only_gate_closed"
    ):
        return "design_only_gate_closed"
    if (
        chapter_status["J"]["current_phase_ready"] is True
        and chapter_status["J"]["readiness_scope"] == "shadow_closeout"
    ):
        return "shadow_closeout_ready"
    if chapter_status["J"]["chapter_state"] in {"partial", "implemented", "canonical_open"}:
        return "shadow_closeout_partial"
    return "observer_baseline"


def _compile_global_mode_state(state: dict[str, Any]) -> str:
    mapping = {
        "observe_only": "observe_only",
        "shadow_only": "shadow_only",
        "design_only": "design_only",
        "demo_reserved": "demo_reserved",
        "live_reserved": "live_reserved",
    }
    return mapping.get(state["global_runtime"]["facts"]["system_mode_fact"], "design_only")


def _compile_effective_risk_envelope_state(state: dict[str, Any]) -> EffectiveRiskEnvelopeState:
    policy_switch = state["control_plane"]["risk_envelope"]["risk_policy_switch"]
    health_overall = state["health_telemetry"]["gates"]["health_gates_overall_state"]
    cooldown_state = state["control_plane"]["demo_control"]["demo_cooldown_state"]

    if policy_switch == "manual_blocked":
        return "blocking"
    if health_overall == "failed":
        return "blocking"
    if cooldown_state == "active" and state["control_plane"]["demo_control"]["demo_state_switch"] == "demo_enabled":
        return "blocking"
    if policy_switch == "default_guarded":
        return "configured"
    return "reserved"


def _compile_demo_gate_states(state: dict[str, Any]) -> None:
    demo = state["control_plane"]["demo_control"]
    execution_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    health_overall = state["health_telemetry"]["gates"]["health_gates_overall_state"]
    risk_state = state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"]

    prerequisite_reasons: list[str] = []
    if execution_mode == "live_reserved":
        prereq_state = "blocked"
        prerequisite_reasons.append("live_mode_reserved_only")
    else:
        prereq_state = "passed"

    demo["demo_prerequisites_gate_state"] = prereq_state
    demo["demo_prerequisites_reason_codes"] = prerequisite_reasons

    arm_reasons: list[str] = []
    if prereq_state != "passed":
        arm_state = "blocked"
        arm_reasons.append("prerequisites_not_passed")
    elif execution_mode != "demo_reserved":
        arm_state = "blocked"
        arm_reasons.append("execution_mode_disabled")
    else:
        arm_state = "passed"

    demo["demo_arm_gate_state"] = arm_state
    demo["demo_arm_reason_codes"] = arm_reasons

    enable_reasons: list[str] = []
    if demo["demo_state_switch"] != "armed_but_closed":
        enable_state = "blocked"
        enable_reasons.append("not_armed")
    elif health_overall == "failed":
        enable_state = "blocked"
        enable_reasons.append("health_gate_blocked")
    elif risk_state == "blocking":
        enable_state = "blocked"
        enable_reasons.append("risk_envelope_blocked")
    elif demo["demo_cooldown_state"] == "active" and (demo["demo_cooldown_until_ts_ms"] or 0) > now_ms():
        enable_state = "blocked"
        enable_reasons.append("cooldown_active")
    else:
        enable_state = "passed"

    demo["demo_enable_gate_state"] = enable_state
    demo["demo_enable_reason_codes"] = enable_reasons
    demo["demo_relock_gate_state"] = "passed"
    demo["demo_relock_reason_codes"] = []


def _compile_global_execution_authority_state(state: dict[str, Any]) -> str:
    execution_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    demo_state = state["control_plane"]["demo_control"]["demo_state_switch"]
    health_overall = state["health_telemetry"]["gates"]["health_gates_overall_state"]
    risk_state = state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"]

    if execution_mode == "disabled":
        return "disabled"
    if execution_mode == "live_reserved":
        return "live_blocked"
    if execution_mode == "demo_reserved" and demo_state != "demo_enabled":
        return "demo_blocked"
    if (
        execution_mode == "demo_reserved"
        and demo_state == "demo_enabled"
        and health_overall != "failed"
        and risk_state != "blocking"
    ):
        return "demo_enabled"
    return "demo_blocked"


def _compile_global_capability_state(state: dict[str, Any]) -> str:
    stage = state["global_runtime"]["derived"]["global_stage_label"]
    if stage == "design_only_gate_closed":
        return "shadow_control_ready"
    if stage == "shadow_closeout_ready":
        return "shadow_operational_visibility"
    if stage == "future_live_reserved":
        return "live_candidate_reserved"
    return "minimal_visibility"


def _compile_effective_action_permissions(state: dict[str, Any]) -> None:
    execution_mode = state["global_runtime"]["controls"]["global_execution_mode_switch"]
    demo_state = state["control_plane"]["demo_control"]["demo_state_switch"]
    risk_state = state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"]

    global_block = state["control_plane"]["action_permissions"]["global"]
    for action_name in ACTION_NAMES:
        configured_key = f"configured_{action_name}_allowed_switch"
        effective_key = f"effective_{action_name}_allowed_state"
        reason_key = f"effective_{action_name}_reason_codes"
        reasons: list[str] = []

        if not global_block[configured_key]:
            state_value = "disabled"
            reasons.append("configured_switch_disabled")
        elif execution_mode == "disabled":
            state_value = "blocked"
            reasons.append("global_execution_blocked")
        elif demo_state != "demo_enabled":
            state_value = "blocked"
            reasons.append("demo_not_enabled")
        elif risk_state == "blocking":
            state_value = "blocked"
            reasons.append("risk_scope_blocked")
        else:
            state_value = "allowed"

        global_block[effective_key] = state_value
        global_block[reason_key] = reasons

    for pf in PRODUCT_FAMILIES:
        pf_control = state["product_family_status"][pf]["controls"]
        pf_permission = state["control_plane"]["action_permissions"]["by_product_family"][pf]
        for action_name in ACTION_NAMES:
            configured_key = f"configured_{action_name}_allowed_switch"
            effective_key = f"effective_{action_name}_allowed_state"
            reason_key = f"effective_{action_name}_reason_codes"
            reasons = []

            if not pf_permission[configured_key]:
                state_value = "disabled"
                reasons.append("configured_switch_disabled")
            elif not pf_control["enabled_switch"]:
                state_value = "blocked"
                reasons.append("product_family_disabled")
            elif not pf_control["visibility_switch"]:
                state_value = "blocked"
                reasons.append("product_family_not_visible")
            elif pf_control["mode_switch"] != "shadow_only":
                state_value = "blocked"
                reasons.append("product_family_mode_blocked")
            elif execution_mode == "disabled":
                state_value = "blocked"
                reasons.append("global_execution_blocked")
            elif demo_state != "demo_enabled":
                state_value = "blocked"
                reasons.append("demo_not_enabled")
            elif risk_state == "blocking":
                state_value = "blocked"
                reasons.append("risk_scope_blocked")
            else:
                state_value = "allowed"

            pf_permission[effective_key] = state_value
            pf_permission[reason_key] = reasons


def _compile_product_family_derived(state: dict[str, Any], pf: str) -> None:
    pf_state = state["product_family_status"][pf]
    controls = pf_state["controls"]
    facts = pf_state["facts"]
    global_exec_authority = state["global_runtime"]["derived"]["global_execution_authority_state"]
    effective_any_allowed = False

    if not controls["visibility_switch"]:
        capability_state = "unavailable"
    elif facts["exchange_permission_fact"] == "unavailable" or facts["account_permission_fact"] == "unavailable":
        capability_state = "unavailable"
    elif not controls["enabled_switch"]:
        capability_state = "visible_only"
    elif controls["mode_switch"] == "observe_only":
        capability_state = "visible_only"
    elif (
        controls["mode_switch"] == "shadow_only"
        and state["capability_matrix"]["product_families"][pf]["control_plane_capability_state"] == "implemented"
    ):
        capability_state = "shadow_control_ready"
    elif controls["mode_switch"] == "shadow_only":
        capability_state = "shadow_visible"
    else:
        capability_state = "reserved"

    for action_name in ACTION_NAMES:
        if (
            state["control_plane"]["action_permissions"]["by_product_family"][pf][
                f"effective_{action_name}_allowed_state"
            ]
            == "allowed"
        ):
            effective_any_allowed = True
            break

    if not controls["enabled_switch"]:
        execution_authority_state = "disabled"
    elif global_exec_authority == "disabled":
        execution_authority_state = "disabled"
    elif global_exec_authority != "demo_enabled":
        execution_authority_state = "blocked"
    elif controls["mode_switch"] != "shadow_only":
        execution_authority_state = "blocked"
    elif effective_any_allowed:
        execution_authority_state = "guarded"
    else:
        execution_authority_state = "blocked"

    if not controls["visibility_switch"]:
        summary = "hidden"
    elif not controls["enabled_switch"]:
        summary = "visible_but_disabled"
    elif controls["mode_switch"] == "disabled":
        summary = "visible_but_not_enabled"
    elif capability_state == "shadow_control_ready":
        summary = "shadow_control_ready"
    elif controls["mode_switch"] in {"observe_only", "shadow_only"}:
        summary = "shadow_visible_only"
    else:
        summary = "reserved"

    pf_state["derived"]["capability_state"] = capability_state
    pf_state["derived"]["execution_authority_state"] = execution_authority_state
    pf_state["derived"]["product_family_summary"] = summary


def compile_state(state: dict[str, Any]) -> dict[str, Any]:
    state = copy.deepcopy(state)
    state["meta"]["snapshot_ts_ms"] = now_ms()
    state["global_runtime"]["derived"]["global_mode_state"] = _compile_global_mode_state(state)
    state["global_runtime"]["derived"]["global_stage_label"] = _compile_global_stage_label(state)
    state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"] = _compile_effective_risk_envelope_state(state)
    _compile_demo_gate_states(state)
    state["global_runtime"]["derived"]["global_execution_authority_state"] = _compile_global_execution_authority_state(state)
    state["global_runtime"]["derived"]["global_capability_state"] = _compile_global_capability_state(state)
    _compile_effective_action_permissions(state)

    for pf in PRODUCT_FAMILIES:
        _compile_product_family_derived(state, pf)

    state["global_runtime"]["derived"]["runtime_still_protected"] = (
        state["global_runtime"]["derived"]["global_execution_authority_state"] != "demo_enabled"
        and state["global_runtime"]["controls"]["global_execution_mode_switch"] != "live_reserved"
    )

    blockers: list[str] = []
    if state["global_runtime"]["controls"]["global_execution_mode_switch"] == "disabled":
        blockers.append("global_execution_blocked")
    if state["control_plane"]["demo_control"]["demo_state_switch"] != "demo_enabled":
        blockers.append("demo_not_enabled")
    if state["control_plane"]["risk_envelope"]["effective_risk_envelope_state"] == "blocking":
        blockers.append("risk_scope_blocked")
    state["global_runtime"]["derived"]["overview_blocker_summary"] = blockers

    state["control_plane"]["execution_control_summary"] = {
        "global_execution_mode_switch_summary": state["global_runtime"]["controls"]["global_execution_mode_switch"],
        "global_operator_mode_switch_summary": state["global_runtime"]["controls"]["global_operator_mode_switch"],
    }
    state["control_plane"]["health_gate_summary"] = {
        "health_gates_overall_state_summary": state["health_telemetry"]["gates"]["health_gates_overall_state"],
        "exchange_timeout_gate_state_summary": state["health_telemetry"]["gates"]["exchange_timeout_gate_state"],
        "ws_disconnect_gate_state_summary": state["health_telemetry"]["gates"]["ws_disconnect_gate_state"],
        "latency_gate_state_summary": state["health_telemetry"]["gates"]["latency_gate_state"],
        "freshness_gate_state_summary": state["health_telemetry"]["gates"]["freshness_gate_state"],
    }
    state["meta"]["snapshot_id"] = build_snapshot_id(state)
    return state


def build_default_state() -> dict[str, Any]:
    ts = now_ms()
    product_families: dict[str, Any] = {}
    capability_product_families: dict[str, Any] = {}
    permission_by_pf: dict[str, Any] = {}

    for pf in PRODUCT_FAMILIES:
        visible = pf == "spot"
        product_families[pf] = {
            "facts": {
                "exchange_permission_fact": "readonly_visible",
                "account_permission_fact": "readonly_visible",
            },
            "controls": {
                "enabled_switch": False,
                "visibility_switch": visible,
                "mode_switch": "disabled",
            },
            "derived": {
                "capability_state": "visible_only" if visible else "unavailable",
                "execution_authority_state": "disabled",
                "product_family_summary": "visible_but_disabled" if visible else "hidden",
            },
            "audit": {"last_change_ts_ms": None, "last_change_by": None},
        }
        capability_product_families[pf] = {
            "visibility_capability_state": "implemented",
            "control_plane_capability_state": "implemented" if pf == "spot" else "reserved",
            "execution_capability_state": "reserved",
        }
        permission_by_pf[pf] = _permission_block(False)

    state = {
        "meta": {
            "schema_name": "openclaw_bybit_state_dictionary",
            "document_version": "v1",
            "schema_version": "v1",
            "api_version": "v1",
            "snapshot_ts_ms": ts,
            "state_revision": 1,
            "environment": "local_dev",
            "repo_branch": "feature/openclaw-bybit-control-api-gui-v1-rc2",
            "repo_commit_short": "",
            "state_compiler_version": "control_api_v1_mvp",
            "snapshot_source_summary": {
                "runtime_latest_used": False,
                "canonical_recheck_used": True,
                "functional_closeout_used": True,
                "telemetry_used": True,
                "manual_inputs_used": True,
            },
        },
        "global_runtime": {
            "facts": {
                "system_mode_fact": "design_only",
                "execution_state_fact": "execution_disabled",
                "runtime_last_refresh_ts_ms": ts,
                "runtime_data_freshness_state": "fresh",
            },
            "controls": {
                "global_execution_mode_switch": "disabled",
                "global_operator_mode_switch": "manual_only",
            },
            "derived": {
                "global_stage_label": "design_only_gate_closed",
                "global_mode_state": "design_only",
                "global_capability_state": "shadow_control_ready",
                "global_execution_authority_state": "disabled",
                "runtime_still_protected": True,
                "overview_blocker_summary": ["global_execution_blocked"],
            },
            "audit": {
                "last_runtime_state_change_ts_ms": None,
                "last_runtime_state_change_by": None,
            },
        },
        "chapter_status": {
            "I": {
                "chapter_display_name": "I (Decision Lease Control Plane)",
                "chapter_state": "canonical_closed",
                "chapter_interpretation": "shadow_only_decision_lease_control_plane_closed",
                "current_phase_ready": True,
                "readiness_scope": "shadow_closeout",
                "execution_meaning": "does_not_grant_live_execution",
                "last_verified_ts_ms": ts,
                "source_of_truth": "canonical_recheck",
            },
            "J": {
                "chapter_display_name": "J (Functional Closeout / Shadow)",
                "chapter_state": "canonical_closed",
                "chapter_interpretation": "functional_closeout_ready_shadow_only",
                "current_phase_ready": True,
                "readiness_scope": "shadow_closeout",
                "execution_meaning": "does_not_grant_live_execution",
                "last_verified_ts_ms": ts,
                "source_of_truth": "closeout",
            },
            "K": {
                "chapter_display_name": "K (Functional Closeout / Design Gate)",
                "chapter_state": "canonical_closed",
                "chapter_interpretation": "functional_closeout_ready_design_only_gate_closed",
                "current_phase_ready": True,
                "readiness_scope": "design_only_gate_closed",
                "execution_meaning": "design_only_gate_closed_not_enabled",
                "last_verified_ts_ms": ts,
                "source_of_truth": "closeout",
            },
        },
        "product_family_status": product_families,
        "control_plane": {
            "execution_control_summary": {
                "global_execution_mode_switch_summary": "disabled",
                "global_operator_mode_switch_summary": "manual_only",
            },
            "demo_control": {
                "demo_state_switch": "closed",
                "demo_validate_requested": False,
                "demo_operator_ack_required": True,
                "demo_operator_ack_completed": False,
                "demo_prerequisites_gate_state": "not_evaluated",
                "demo_prerequisites_reason_codes": [],
                "demo_prerequisites_last_evaluated_ts_ms": None,
                "demo_arm_gate_state": "blocked",
                "demo_arm_reason_codes": ["prerequisites_not_passed"],
                "demo_arm_last_evaluated_ts_ms": None,
                "demo_enable_gate_state": "blocked",
                "demo_enable_reason_codes": ["not_armed"],
                "demo_enable_last_evaluated_ts_ms": None,
                "demo_relock_gate_state": "passed",
                "demo_relock_reason_codes": [],
                "demo_relock_last_evaluated_ts_ms": None,
                "demo_last_action_type": None,
                "demo_last_action_result": None,
                "demo_last_action_reason_codes": [],
                "demo_last_action_ts_ms": None,
                "demo_cooldown_state": "inactive",
                "demo_cooldown_until_ts_ms": None,
            },
            "action_permissions": {
                "global": _permission_block(False),
                "by_product_family": permission_by_pf,
            },
            "health_gate_summary": {
                "health_gates_overall_state_summary": "not_evaluated",
                "exchange_timeout_gate_state_summary": "not_evaluated",
                "ws_disconnect_gate_state_summary": "not_evaluated",
                "latency_gate_state_summary": "not_evaluated",
                "freshness_gate_state_summary": "not_evaluated",
            },
            "risk_envelope": {
                "risk_policy_switch": "default_guarded",
                "risk_policy_profile": "default",
                "effective_risk_envelope_state": "configured",
            },
        },
        "capability_matrix": {
            "J": {
                "canonical_recheck_state": "passed",
                "closeout_state": "passed",
                "canonical_recheck_last_verified_ts_ms": ts,
                "closeout_last_verified_ts_ms": ts,
            },
            "K": {
                "canonical_recheck_state": "passed",
                "closeout_state": "passed",
                "canonical_recheck_last_verified_ts_ms": ts,
                "closeout_last_verified_ts_ms": ts,
            },
            "product_families": capability_product_families,
        },
        "business_metrics": {
            "daily": {
                "window_start_ts_ms": ts,
                "window_end_ts_ms": ts,
                "window_timezone": "Europe/Madrid",
                "reporting_currency": "USDT",
                "fx_rate_source": "bybit_mark_or_manual_config",
                "valuation_basis": "mark",
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "gross_pnl": 0,
                "total_cost": 0,
                "net_operating_pnl": 0,
                "manual_cost_included": True,
                "manual_cost_source_count": 0,
                "business_event_count": 0,
            }
        },
        "health_telemetry": {
            "scores": {
                "overall_health_score": 100,
                "ai_health_score": 100,
                "exchange_health_score": 100,
                "infra_health_score": 100,
                "data_freshness_score": 100,
            },
            "metrics": {
                "avg_ai_latency_ms": 0,
                "exchange_timeout_count": 0,
                "ws_disconnect_count": 0,
                "runtime_stale_count": 0,
            },
            "evaluation_context": {
                "evaluation_window_sec": 300,
                "sample_count": 0,
                "last_evaluated_ts_ms": ts,
                "threshold_basis": "rolling_window",
            },
            "gates": {
                "health_gates_overall_state": "passed",
                "exchange_timeout_gate_state": "passed",
                "ws_disconnect_gate_state": "passed",
                "latency_gate_state": "passed",
                "freshness_gate_state": "passed",
            },
        },
        "learning_state": {
            "observation_summary": {
                "last_observation_ts_ms": None,
                "recent_lessons_count": 0,
                "recent_hypothesis_count": 0,
                "recent_experiment_proposal_count": 0,
            },
            "memory": {"lessons_memory_state": "active", "last_memory_update_ts_ms": None},
            "hypotheses": {"active_hypothesis_count": 0, "last_hypothesis_ts_ms": None},
            "experiments": {
                "approval_required": True,
                "active_experiment_count": 0,
                "last_experiment_proposal_ts_ms": None,
            },
            "derived": {"learning_progression_state": "observe_and_record_only"},
            "records": {"hypotheses": [], "experiments": [], "manual_notes": []},
        },
        "audit_context": {
            "last_operator_action_type": None,
            "last_operator_action_ts_ms": None,
            "last_operator_action_result": None,
            "last_operator_action_operator": None,
            "last_operator_action_target": None,
            "last_operator_action_request_id": None,
            "last_operator_action_reason_codes": [],
            "last_operator_action_audit_ref": None,
            "last_state_revision_before": None,
            "last_state_revision_after": None,
            "last_control_action_type": None,
            "last_control_action_request_id": None,
            "last_control_action_ts_ms": None,
            "last_control_action_by": None,
            "last_control_action_result": None,
            "last_control_action_reason_codes": [],
            "last_control_action_audit_ref": None,
            "last_write_action_type": None,
            "last_write_action_request_id": None,
            "last_write_action_ts_ms": None,
            "last_write_action_by": None,
            "last_write_action_result": None,
            "last_write_action_reason_codes": [],
            "last_write_action_audit_ref": None,
        },
        "records": {
            "idempotency": {},
            "cost_entries": [],
            "event_entries": [],
        },
    }
    return compile_state(state)


class JsonStateStore:
    def __init__(self, file_path: str) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if not self.file_path.exists():
            self.write(build_default_state())

    def read(self) -> dict[str, Any]:
        with self._lock:
            with self.file_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            compiled = compile_state(payload)
            if compiled != payload:
                self.write(compiled)
            return compiled

    def write(self, state: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            compiled = compile_state(state)
            with self.file_path.open("w", encoding="utf-8") as handle:
                json.dump(compiled, handle, ensure_ascii=False, indent=2)
            return compiled

    def mutate(self, mutator) -> dict[str, Any]:
        with self._lock:
            current = self.read()
            mutated = mutator(copy.deepcopy(current))
            return self.write(mutated)


STORE = JsonStateStore(settings.state_file_path)


@dataclass(slots=True)
class AuthenticatedActor:
    actor_id: str
    actor_type: str
    roles: set[str]
    scopes: set[str]


def build_authenticated_actor() -> AuthenticatedActor:
    return AuthenticatedActor(
        actor_id=settings.auth_actor_id,
        actor_type=settings.auth_actor_type,
        roles=set(settings.auth_roles),
        scopes=set(settings.auth_scopes),
    )


def require_scope(actor: AuthenticatedActor, scope: str) -> None:
    if scope not in actor.scopes:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_codes": ["forbidden_scope"]},
        )


def verify_operator_identity(envelope: RequestEnvelope, actor: AuthenticatedActor) -> None:
    if envelope.operator_id != actor.actor_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"reason_codes": ["operator_identity_mismatch"]},
        )


def request_fingerprint(envelope: RequestEnvelope) -> str:
    payload = envelope.model_dump(mode="json")
    return hashlib.sha1(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def build_source_context(snapshot: dict[str, Any]) -> SourceContext:
    execution_name = settings.execution_connector_name
    return SourceContext(
        readonly_connector_name=settings.readonly_connector_name,
        readonly_connector_role="fact_source",
        readonly_connector_scope="private_readonly",
        execution_connector_name=execution_name,
        execution_connector_role="execution_source_reserved",
        execution_connector_scope="private_execution" if execution_name else "not_attached",
        connector_role_separation_ok=(execution_name is None or execution_name != settings.readonly_connector_name),
        rest_private_connection_state=settings.rest_private_connection_state,
        ws_private_connection_state=settings.ws_private_connection_state,
        runtime_connection_state=settings.runtime_connection_state,
        account_fact_completeness_state=settings.account_fact_completeness_state,
        source_snapshot_completeness_state=settings.source_snapshot_completeness_state,
        pinned_runtime_snapshot_id=f"runtime:{snapshot['meta']['snapshot_id']}",
        pinned_runtime_snapshot_ts_ms=snapshot["meta"]["snapshot_ts_ms"],
    )


def ensure_source_is_usable(source_context: SourceContext) -> None:
    if source_context.runtime_connection_state in {"down", "unknown"}:
        raise HTTPException(status_code=503, detail={"reason_codes": ["runtime_fact_unavailable"]})
    if source_context.rest_private_connection_state in {"down", "unknown"}:
        raise HTTPException(status_code=503, detail={"reason_codes": ["connector_unavailable"]})
    if source_context.source_snapshot_completeness_state == "missing":
        raise HTTPException(status_code=503, detail={"reason_codes": ["source_snapshot_incomplete"]})


def _assert_revision(snapshot: dict[str, Any], envelope: RequestEnvelope) -> None:
    if envelope.expected_state_revision != snapshot["meta"]["state_revision"]:
        raise HTTPException(status_code=409, detail={"reason_codes": ["state_revision_mismatch"]})


def _assert_previous_state(snapshot: dict[str, Any], envelope: RequestEnvelope, allowed: set[str] | None = None) -> None:
    current = snapshot["control_plane"]["demo_control"]["demo_state_switch"]
    expected = envelope.expected_previous_state
    if expected is None or expected != current or (allowed is not None and current not in allowed):
        raise HTTPException(status_code=409, detail={"reason_codes": ["previous_state_mismatch"]})


def _check_idempotency(snapshot: dict[str, Any], envelope: RequestEnvelope) -> dict[str, Any] | None:
    record = snapshot["records"]["idempotency"].get(envelope.idempotency_key)
    if record is None:
        return None
    if record["fingerprint"] != request_fingerprint(envelope):
        raise HTTPException(status_code=409, detail={"reason_codes": ["idempotency_conflict"]})
    return record["response"]


def _store_idempotent_response(state: dict[str, Any], envelope: RequestEnvelope, response: dict[str, Any]) -> None:
    stored_response = dict(response)
    stored_response.pop("snapshot", None)
    state["records"]["idempotency"][envelope.idempotency_key] = {
        "request_id": envelope.request_id,
        "fingerprint": request_fingerprint(envelope),
        "response": stored_response,
    }


def _write_audit_fields(
    state: dict[str, Any],
    *,
    action_type: str,
    operator_id: str,
    request_id: str,
    result: str,
    reason_codes: list[str],
    is_control_action: bool,
) -> str:
    ts = now_ms()
    audit_ref = f"audit:{action_type}:{ts}"
    audit = state["audit_context"]
    audit["last_state_revision_before"] = state["meta"]["state_revision"]
    audit["last_state_revision_after"] = state["meta"]["state_revision"] + 1

    audit["last_write_action_type"] = action_type
    audit["last_write_action_request_id"] = request_id
    audit["last_write_action_ts_ms"] = ts
    audit["last_write_action_by"] = operator_id
    audit["last_write_action_result"] = result
    audit["last_write_action_reason_codes"] = list(reason_codes)
    audit["last_write_action_audit_ref"] = audit_ref

    if is_control_action:
        audit["last_control_action_type"] = action_type
        audit["last_control_action_request_id"] = request_id
        audit["last_control_action_ts_ms"] = ts
        audit["last_control_action_by"] = operator_id
        audit["last_control_action_result"] = result
        audit["last_control_action_reason_codes"] = list(reason_codes)
        audit["last_control_action_audit_ref"] = audit_ref

        audit["last_operator_action_type"] = action_type
        audit["last_operator_action_ts_ms"] = ts
        audit["last_operator_action_result"] = result
        audit["last_operator_action_operator"] = operator_id
        audit["last_operator_action_target"] = "control_plane"
        audit["last_operator_action_request_id"] = request_id
        audit["last_operator_action_reason_codes"] = list(reason_codes)
        audit["last_operator_action_audit_ref"] = audit_ref

    return audit_ref


def _bump_revision(state: dict[str, Any]) -> None:
    state["meta"]["state_revision"] += 1


def get_latest_snapshot() -> tuple[dict[str, Any], SourceContext]:
    snapshot = STORE.read()
    return snapshot, build_source_context(snapshot)


def build_overview(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        "global_runtime": {
            "global_stage_label": snapshot["global_runtime"]["derived"]["global_stage_label"],
            "global_mode_state": snapshot["global_runtime"]["derived"]["global_mode_state"],
            "global_capability_state": snapshot["global_runtime"]["derived"]["global_capability_state"],
            "global_execution_authority_state": snapshot["global_runtime"]["derived"]["global_execution_authority_state"],
            "runtime_still_protected": snapshot["global_runtime"]["derived"]["runtime_still_protected"],
        },
        "chapter_status_summary": snapshot["chapter_status"],
        "daily_business_summary": snapshot["business_metrics"]["daily"],
        "health_summary": snapshot["health_telemetry"],
        "demo_control_summary": {
            "demo_state_switch": snapshot["control_plane"]["demo_control"]["demo_state_switch"],
            "demo_prerequisites_gate_state": snapshot["control_plane"]["demo_control"]["demo_prerequisites_gate_state"],
            "demo_arm_gate_state": snapshot["control_plane"]["demo_control"]["demo_arm_gate_state"],
            "demo_enable_gate_state": snapshot["control_plane"]["demo_control"]["demo_enable_gate_state"],
            "demo_relock_gate_state": snapshot["control_plane"]["demo_control"]["demo_relock_gate_state"],
        },
        "latest_control_action_summary": {
            "last_control_action_type": snapshot["audit_context"]["last_control_action_type"],
            "last_control_action_ts_ms": snapshot["audit_context"]["last_control_action_ts_ms"],
            "last_control_action_result": snapshot["audit_context"]["last_control_action_result"],
            "last_control_action_reason_codes": snapshot["audit_context"]["last_control_action_reason_codes"],
            "last_control_action_audit_ref": snapshot["audit_context"]["last_control_action_audit_ref"],
        },
        "latest_write_action_summary": {
            "last_write_action_type": snapshot["audit_context"]["last_write_action_type"],
            "last_write_action_ts_ms": snapshot["audit_context"]["last_write_action_ts_ms"],
            "last_write_action_result": snapshot["audit_context"]["last_write_action_result"],
            "last_write_action_reason_codes": snapshot["audit_context"]["last_write_action_reason_codes"],
            "last_write_action_audit_ref": snapshot["audit_context"]["last_write_action_audit_ref"],
        },
    }


def perform_recheck(envelope: RequestEnvelope, actor: AuthenticatedActor, chapter: str, kind: str) -> tuple[dict[str, Any], str]:
    snapshot, source_context = get_latest_snapshot()
    require_scope(actor, "control:recheck")
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        ts = now_ms()
        target = state["capability_matrix"][chapter]
        if kind == "canonical":
            target["canonical_recheck_state"] = "passed"
            target["canonical_recheck_last_verified_ts_ms"] = ts
        else:
            target["closeout_state"] = "passed"
            target["closeout_last_verified_ts_ms"] = ts

        state["chapter_status"][chapter]["last_verified_ts_ms"] = ts
        audit_ref = _write_audit_fields(
            state,
            action_type=f"{chapter.lower()}_{kind}_recheck",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "chapter": chapter,
                "recheck_kind": kind,
                "recheck_state": "passed",
                "last_verified_ts_ms": ts,
                "chapter_snapshot": copy.deepcopy(compiled["chapter_status"][chapter]),
                "pinned_runtime_snapshot_id": build_source_context(compiled).pinned_runtime_snapshot_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    source = build_source_context(final_state)
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "chapter": chapter,
            "recheck_kind": kind,
            "recheck_state": "passed",
            "last_verified_ts_ms": final_state["chapter_status"][chapter]["last_verified_ts_ms"],
            "chapter_snapshot": final_state["chapter_status"][chapter],
            "pinned_runtime_snapshot_id": source.pinned_runtime_snapshot_id,
        },
        "snapshot": final_state,
    }, "success"


def perform_validate(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    snapshot, source_context = get_latest_snapshot()
    require_scope(actor, "control:validate")
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        ts = now_ms()
        demo = state["control_plane"]["demo_control"]
        demo["demo_validate_requested"] = True
        demo["demo_prerequisites_last_evaluated_ts_ms"] = ts
        demo["demo_arm_last_evaluated_ts_ms"] = ts
        demo["demo_enable_last_evaluated_ts_ms"] = ts
        demo["demo_relock_last_evaluated_ts_ms"] = ts
        demo["demo_last_action_type"] = "validate"
        demo["demo_last_action_result"] = "success"
        demo["demo_last_action_reason_codes"] = []
        demo["demo_last_action_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state,
            action_type="demo_validate",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "demo_state_switch": compiled["control_plane"]["demo_control"]["demo_state_switch"],
                "demo_prerequisites_gate_state": compiled["control_plane"]["demo_control"]["demo_prerequisites_gate_state"],
                "demo_prerequisites_reason_codes": compiled["control_plane"]["demo_control"]["demo_prerequisites_reason_codes"],
                "demo_arm_gate_state": compiled["control_plane"]["demo_control"]["demo_arm_gate_state"],
                "demo_arm_reason_codes": compiled["control_plane"]["demo_control"]["demo_arm_reason_codes"],
                "demo_enable_gate_state": compiled["control_plane"]["demo_control"]["demo_enable_gate_state"],
                "demo_enable_reason_codes": compiled["control_plane"]["demo_control"]["demo_enable_reason_codes"],
                "demo_relock_gate_state": compiled["control_plane"]["demo_control"]["demo_relock_gate_state"],
                "demo_relock_reason_codes": compiled["control_plane"]["demo_control"]["demo_relock_reason_codes"],
                "pinned_runtime_snapshot_id": build_source_context(compiled).pinned_runtime_snapshot_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    source = build_source_context(final_state)
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "demo_state_switch": final_state["control_plane"]["demo_control"]["demo_state_switch"],
            "demo_prerequisites_gate_state": final_state["control_plane"]["demo_control"]["demo_prerequisites_gate_state"],
            "demo_prerequisites_reason_codes": final_state["control_plane"]["demo_control"]["demo_prerequisites_reason_codes"],
            "demo_arm_gate_state": final_state["control_plane"]["demo_control"]["demo_arm_gate_state"],
            "demo_arm_reason_codes": final_state["control_plane"]["demo_control"]["demo_arm_reason_codes"],
            "demo_enable_gate_state": final_state["control_plane"]["demo_control"]["demo_enable_gate_state"],
            "demo_enable_reason_codes": final_state["control_plane"]["demo_control"]["demo_enable_reason_codes"],
            "demo_relock_gate_state": final_state["control_plane"]["demo_control"]["demo_relock_gate_state"],
            "demo_relock_reason_codes": final_state["control_plane"]["demo_control"]["demo_relock_reason_codes"],
            "pinned_runtime_snapshot_id": source.pinned_runtime_snapshot_id,
        },
        "snapshot": final_state,
    }, "success"


def _blocked(reason_codes: list[str]) -> None:
    raise HTTPException(status_code=422, detail={"reason_codes": reason_codes})


def perform_demo_transition(envelope: RequestEnvelope, actor: AuthenticatedActor, action: str) -> tuple[dict[str, Any], str]:
    scope_map = {"arm": "control:arm", "enable": "control:enable", "relock": "control:relock"}
    require_scope(actor, scope_map[action])

    snapshot, source_context = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    if action == "arm":
        _assert_previous_state(snapshot, envelope, {"closed", "relocked"})
        if snapshot["control_plane"]["demo_control"]["demo_prerequisites_gate_state"] != "passed":
            _blocked(["prerequisites_not_passed"])
        if snapshot["global_runtime"]["controls"]["global_execution_mode_switch"] != "demo_reserved":
            _blocked(["execution_mode_disabled"])
        if snapshot["control_plane"]["demo_control"]["demo_operator_ack_required"] and not envelope.payload.get("acknowledged", False):
            _blocked(["operator_ack_required"])

    if action == "enable":
        _assert_previous_state(snapshot, envelope, {"armed_but_closed"})
        if snapshot["control_plane"]["demo_control"]["demo_enable_gate_state"] != "passed":
            _blocked(snapshot["control_plane"]["demo_control"]["demo_enable_reason_codes"])
        if snapshot["control_plane"]["demo_control"]["demo_operator_ack_required"] and not envelope.payload.get("acknowledged", False):
            _blocked(["operator_ack_required"])

    if action == "relock":
        _assert_previous_state(snapshot, envelope, {"armed_but_closed", "demo_enabled", "relocked"})

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        demo = state["control_plane"]["demo_control"]
        previous = demo["demo_state_switch"]
        ts = now_ms()
        reason_codes: list[str] = []

        if action == "arm":
            demo["demo_state_switch"] = "armed_but_closed"
        elif action == "enable":
            demo["demo_state_switch"] = "demo_enabled"
            demo["demo_operator_ack_completed"] = True
        elif action == "relock":
            demo["demo_state_switch"] = "relocked"
            demo["demo_cooldown_state"] = "active"
            demo["demo_cooldown_until_ts_ms"] = envelope.client_ts_ms + 300000

        demo["demo_last_action_type"] = action
        demo["demo_last_action_result"] = "success"
        demo["demo_last_action_reason_codes"] = reason_codes
        demo["demo_last_action_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state,
            action_type=f"demo_{action}",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=reason_codes,
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "demo_state_switch": compiled["control_plane"]["demo_control"]["demo_state_switch"],
                "previous_demo_state_switch": previous,
                "gate_state": "passed",
                "reason_codes": [],
                "pinned_runtime_snapshot_id": build_source_context(compiled).pinned_runtime_snapshot_id,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    source = build_source_context(final_state)
    previous_state = snapshot["control_plane"]["demo_control"]["demo_state_switch"]
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "demo_state_switch": final_state["control_plane"]["demo_control"]["demo_state_switch"],
            "previous_demo_state_switch": previous_state,
            "gate_state": "passed",
            "reason_codes": [],
            "pinned_runtime_snapshot_id": source.pinned_runtime_snapshot_id,
        },
        "snapshot": final_state,
    }, "success"


def perform_safe_bundle(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    require_scope(actor, "control:bundle")
    snapshot, source_context = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)
    ensure_source_is_usable(source_context)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        ts = now_ms()
        for chapter in ("J", "K"):
            state["capability_matrix"][chapter]["canonical_recheck_state"] = "passed"
            state["capability_matrix"][chapter]["canonical_recheck_last_verified_ts_ms"] = ts
            state["capability_matrix"][chapter]["closeout_state"] = "passed"
            state["capability_matrix"][chapter]["closeout_last_verified_ts_ms"] = ts
            state["chapter_status"][chapter]["last_verified_ts_ms"] = ts

        demo = state["control_plane"]["demo_control"]
        demo["demo_validate_requested"] = True
        demo["demo_prerequisites_last_evaluated_ts_ms"] = ts
        demo["demo_arm_last_evaluated_ts_ms"] = ts
        demo["demo_enable_last_evaluated_ts_ms"] = ts
        demo["demo_relock_last_evaluated_ts_ms"] = ts
        demo["demo_last_action_type"] = "safe_recheck_bundle"
        demo["demo_last_action_result"] = "success"
        demo["demo_last_action_reason_codes"] = []
        demo["demo_last_action_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state,
            action_type="safe_recheck_bundle",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=True,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        steps = [
            {"step_name": "j-canonical", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "k-canonical", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "j-closeout", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "k-closeout", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
            {"step_name": "demo-validate", "action_result": "success", "reason_codes": [], "audit_ref": audit_ref},
        ]
        response = {
            "audit_ref": audit_ref,
            "data": {
                "bundle_base_snapshot_id": snapshot["meta"]["snapshot_id"],
                "bundle_final_snapshot_id": compiled["meta"]["snapshot_id"],
                "bundle_committed": True,
                "steps": steps,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"],
        "data": {
            "bundle_base_snapshot_id": snapshot["meta"]["snapshot_id"],
            "bundle_final_snapshot_id": final_state["meta"]["snapshot_id"],
            "bundle_committed": True,
            "steps": [
                {"step_name": "j-canonical", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "k-canonical", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "j-closeout", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "k-closeout", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
                {"step_name": "demo-validate", "action_result": "success", "reason_codes": [], "audit_ref": final_state["audit_context"]["last_control_action_audit_ref"]},
            ],
        },
        "snapshot": final_state,
    }, "success"


def apply_input_action(envelope: RequestEnvelope, actor: AuthenticatedActor, action: str) -> tuple[dict[str, Any], str]:
    scope_map = {"cost": "input:cost", "event": "input:event", "manual-note": "input:note"}
    require_scope(actor, scope_map[action])

    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        delta = 0
        payload = dict(envelope.payload)
        payload["recorded_ts_ms"] = now_ms()

        if action == "cost":
            amount = float(payload.get("amount", 0))
            state["records"]["cost_entries"].append(payload)
            state["business_metrics"]["daily"]["total_cost"] += amount
            state["business_metrics"]["daily"]["manual_cost_source_count"] += 1
            state["business_metrics"]["daily"]["net_operating_pnl"] -= amount
            delta = 1
        elif action == "event":
            state["records"]["event_entries"].append(payload)
            state["business_metrics"]["daily"]["business_event_count"] += 1
            delta = 1
        else:
            state["learning_state"]["records"]["manual_notes"].append(payload)
            delta = 1

        audit_ref = _write_audit_fields(
            state,
            action_type=action.replace("-", "_"),
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {"audit_ref": audit_ref, "data": {"accepted": True, "record_count_delta": delta}, "snapshot": compiled}
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_config_change(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    require_scope(actor, "input:config")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    changes = envelope.payload.get("changes")
    if not isinstance(changes, list) or not changes:
        raise HTTPException(status_code=400, detail={"reason_codes": ["cfg_field_required"]})

    accepted_paths: list[str] = []
    rejected_paths: list[str] = []

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        for item in changes:
            if not isinstance(item, dict) or "path" not in item:
                raise HTTPException(status_code=400, detail={"reason_codes": ["cfg_field_required"]})
            path = item["path"]
            value = item.get("value")
            if path not in CONFIG_CHANGE_WHITELIST:
                rejected_paths.append(path)
                continue
            deep_set(state, path, value)
            accepted_paths.append(path)

        if not accepted_paths:
            raise HTTPException(status_code=400, detail={"reason_codes": ["path_not_whitelisted"]})

        audit_ref = _write_audit_fields(
            state,
            action_type="config_change",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted_paths": accepted_paths, "rejected_paths": rejected_paths},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted_paths": accepted_paths, "rejected_paths": rejected_paths},
        "snapshot": final_state,
    }, "success"


# ── 产品族配置写接口 / Product Family Config Write ───────────────────────────

# 当前阶段允许的 mode_switch 值（live 相关值不在此阶段开放）
# Allowed mode_switch values at this stage (live-related values are NOT opened yet)
ALLOWED_MODE_SWITCHES: frozenset[str] = frozenset({"disabled", "observe_only", "shadow_only"})


def apply_product_family_config(
    envelope: RequestEnvelope,
    actor: AuthenticatedActor,
    family: str,
) -> tuple[dict[str, Any], str]:
    """
    应用产品族控制配置变更 / Apply product family control configuration changes.

    支持修改：enabled_switch / visibility_switch / mode_switch / action_permissions
    Supports modifying: enabled_switch / visibility_switch / mode_switch / action_permissions

    安全规则 / Safety rules:
    - mode_switch 只允许: disabled / observe_only / shadow_only
      mode_switch only allows: disabled / observe_only / shadow_only
    - 不能直接把产品族升到 live 相关模式
      Cannot directly set a product family to live-related modes
    - 需要 input:config scope
      Requires input:config scope
    """
    if family not in PRODUCT_FAMILIES:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["invalid_product_family"]},
        )

    require_scope(actor, "input:config")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    applied_changes: dict[str, Any] = {}
    rejected_fields: list[str] = []
    payload = dict(envelope.payload)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        pf_controls = state["product_family_status"][family]["controls"]

        # 处理 enabled_switch（布尔值）/ Handle enabled_switch (boolean)
        if "enabled_switch" in payload:
            val = payload["enabled_switch"]
            if isinstance(val, bool):
                pf_controls["enabled_switch"] = val
                applied_changes["enabled_switch"] = val
            else:
                rejected_fields.append("enabled_switch:invalid_type")

        # 处理 visibility_switch（布尔值）/ Handle visibility_switch (boolean)
        if "visibility_switch" in payload:
            val = payload["visibility_switch"]
            if isinstance(val, bool):
                pf_controls["visibility_switch"] = val
                applied_changes["visibility_switch"] = val
            else:
                rejected_fields.append("visibility_switch:invalid_type")

        # 处理 mode_switch（只允许受限值）/ Handle mode_switch (only allowed values)
        if "mode_switch" in payload:
            val = payload["mode_switch"]
            if val in ALLOWED_MODE_SWITCHES:
                pf_controls["mode_switch"] = val
                applied_changes["mode_switch"] = val
            else:
                rejected_fields.append(f"mode_switch:{val}:not_allowed_at_this_stage")

        # 处理每个动作的开关权限 / Handle per-action permission switches
        action_perms_payload = payload.get("action_permissions", {})
        if isinstance(action_perms_payload, dict):
            pf_perms = state["control_plane"]["action_permissions"]["by_product_family"][family]
            for action_name, val in action_perms_payload.items():
                key = f"configured_{action_name}_allowed_switch"
                if action_name in ACTION_NAMES and isinstance(val, bool):
                    pf_perms[key] = val
                    applied_changes[f"action_permissions.{action_name}"] = val
                else:
                    rejected_fields.append(f"action_permissions.{action_name}:invalid")

        # 更新审计字段 / Update audit fields
        state["product_family_status"][family]["audit"] = {
            "last_change_ts_ms": now_ms(),
            "last_change_by": actor.actor_id,
        }

        result_str = "success" if applied_changes else "blocked"
        audit_ref = _write_audit_fields(
            state,
            action_type=f"product_family_config_{family}",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result=result_str,
            reason_codes=rejected_fields,
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "family": family,
                "applied_changes": dict(applied_changes),
                "rejected_fields": list(rejected_fields),
                "current_controls": copy.deepcopy(compiled["product_family_status"][family]["controls"]),
                "current_derived": copy.deepcopy(compiled["product_family_status"][family]["derived"]),
                "current_action_permissions": copy.deepcopy(
                    compiled["control_plane"]["action_permissions"]["by_product_family"][family]
                ),
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "family": family,
            "applied_changes": applied_changes,
            "rejected_fields": rejected_fields,
            "current_controls": final_state["product_family_status"][family]["controls"],
            "current_derived": final_state["product_family_status"][family]["derived"],
            "current_action_permissions": final_state["control_plane"]["action_permissions"]["by_product_family"][family],
        },
        "snapshot": final_state,
    }, "success" if applied_changes else "blocked"


# ── PnL 条目录入 / PnL Entry Input ──────────────────────────────────────────


def apply_pnl_entry(envelope: RequestEnvelope, actor: AuthenticatedActor) -> tuple[dict[str, Any], str]:
    """
    录入一条 PnL 更新记录 / Record a PnL update entry.

    payload 字段（均可选）/ payload fields (all optional):
    - entry_type: str  例如 "realized" | "unrealized" | "manual_adjustment"
    - realized_pnl: float  当次已实现盈亏增量 / realized PnL delta for this entry
    - unrealized_pnl: float  当前未实现盈亏（取最新值）/ current unrealized PnL (snapshot, not delta)
    - symbol: str  涉及标的 / symbol involved
    - note: str  备注 / note
    - category: str  成本/盈亏类型分类，用于 cost_breakdown

    注意：unrealized_pnl 取最新值覆盖（snapshot），realized_pnl 是累计增量。
    Note: unrealized_pnl is a snapshot (overwrite); realized_pnl is an accumulative delta.
    """
    require_scope(actor, "input:cost")  # 复用 cost scope / reuse cost scope for PnL writes
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        payload = dict(envelope.payload)
        payload["recorded_ts_ms"] = now_ms()
        payload["recorded_by"] = actor.actor_id

        entry_type = str(payload.get("entry_type", "manual_adjustment"))
        delta_realized = float(payload.get("realized_pnl", 0.0))
        delta_unrealized = float(payload.get("unrealized_pnl", 0.0))
        has_unrealized = "unrealized_pnl" in envelope.payload

        # 确保 pnl_entries 列表存在（兼容旧快照文件）
        # Ensure pnl_entries list exists (backward-compatible with old state files)
        if "pnl_entries" not in state["records"]:
            state["records"]["pnl_entries"] = []
        state["records"]["pnl_entries"].append(payload)

        # 更新每日 PnL / Update daily PnL metrics
        daily = state["business_metrics"]["daily"]
        daily["realized_pnl"] = daily.get("realized_pnl", 0.0) + delta_realized
        if has_unrealized:
            # unrealized 取最新快照值，不累加 / unrealized is a snapshot value, not accumulated
            daily["unrealized_pnl"] = delta_unrealized
        daily["gross_pnl"] = daily["realized_pnl"] + daily.get("unrealized_pnl", 0.0)
        daily["net_operating_pnl"] = daily["gross_pnl"] - daily.get("total_cost", 0.0)

        audit_ref = _write_audit_fields(
            state,
            action_type="pnl_entry",
            operator_id=actor.actor_id,
            request_id=envelope.request_id,
            result="success",
            reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "accepted": True,
                "entry_type": entry_type,
                "delta_realized_pnl": delta_realized,
                "delta_unrealized_pnl": delta_unrealized,
                "record_count_delta": 1,
            },
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    payload = envelope.payload
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {
            "accepted": True,
            "entry_type": str(payload.get("entry_type", "manual_adjustment")),
            "delta_realized_pnl": float(payload.get("realized_pnl", 0.0)),
            "delta_unrealized_pnl": float(payload.get("unrealized_pnl", 0.0)),
            "record_count_delta": 1,
        },
        "snapshot": final_state,
    }, "success"


# ── 经营摘要构建器 / Business Summary Builder ────────────────────────────────

_MAX_RECENT_ENTRIES: int = 20  # 每次最多返回多少条历史记录 / Max entries returned per call


def build_business_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建完整的经营与收益汇总 / Build a complete business and income summary.

    包含：每日 PnL 指标 + 最近费用条目 + 最近事件条目 + 最近 PnL 条目 + 成本分类合计
    Includes: daily PnL metrics + recent cost entries + recent event entries
              + recent PnL entries + cost breakdown by category
    """
    daily = copy.deepcopy(snapshot["business_metrics"]["daily"])
    records = snapshot.get("records", {})

    cost_entries: list[dict[str, Any]] = records.get("cost_entries", [])
    event_entries: list[dict[str, Any]] = records.get("event_entries", [])
    pnl_entries: list[dict[str, Any]] = records.get("pnl_entries", [])

    # 取最近 N 条，按最新在前排列 / Take last N, newest first
    cost_recent = list(reversed(cost_entries[-_MAX_RECENT_ENTRIES:]))
    event_recent = list(reversed(event_entries[-_MAX_RECENT_ENTRIES:]))
    pnl_recent = list(reversed(pnl_entries[-_MAX_RECENT_ENTRIES:]))

    # 按 category 做成本分解 / Compute cost breakdown by category
    cost_breakdown: dict[str, float] = {}
    for entry in cost_entries:
        category = str(entry.get("category", "manual"))
        cost_breakdown[category] = round(
            cost_breakdown.get(category, 0.0) + float(entry.get("amount", 0.0)),
            8,
        )

    return {
        "daily": daily,
        "cost_entries_recent": cost_recent,
        "event_entries_recent": event_recent,
        "pnl_entries_recent": pnl_recent,
        "cost_breakdown": cost_breakdown,
        "entry_totals": {
            "total_cost_entries": len(cost_entries),
            "total_event_entries": len(event_entries),
            "total_pnl_entries": len(pnl_entries),
        },
    }


app = FastAPI(
    title=settings.service_name,
    version=settings.api_version,
    description="OpenClaw / Bybit Control API + GUI MVP",
)

static_dir = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def current_actor(authorization: str | None = Header(default=None)) -> Any:
    if authorization is None or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"reason_codes": ["unauthenticated"]})
    token = authorization.replace("Bearer ", "", 1).strip()
    if token != settings.api_token:
        raise HTTPException(status_code=401, detail={"reason_codes": ["unauthenticated"]})
    return build_authenticated_actor()


def envelope_response(
    *,
    snapshot: dict[str, Any],
    request_id: str | None,
    action_result: str,
    data: Any,
    audit_ref: str | None = None,
    reason_codes: list[str] | None = None,
) -> ResponseEnvelope[Any]:
    return ResponseEnvelope[Any](
        api_version=settings.api_version,
        schema_version=settings.schema_version,
        request_id=request_id,
        snapshot_ts_ms=snapshot["meta"]["snapshot_ts_ms"],
        snapshot_id=snapshot["meta"]["snapshot_id"],
        state_revision=snapshot["meta"]["state_revision"],
        action_result=action_result,
        reason_codes=reason_codes or [],
        warnings=[],
        audit_ref=audit_ref,
        source_context=build_source_context(snapshot),
        data=data,
    )


@app.get("/", include_in_schema=False)
def root_redirect() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/gui", include_in_schema=False)
def gui_index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get(f"{settings.api_prefix}/system/overview", response_model=ResponseEnvelope[OverviewData])
def get_system_overview(actor=Depends(current_actor)) -> ResponseEnvelope[OverviewData]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=OverviewData(**build_overview(snapshot)))


@app.get(f"{settings.api_prefix}/system/chapter-status", response_model=ResponseEnvelope[dict[str, Any]])
def get_chapter_status(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["chapter_status"])


@app.get(f"{settings.api_prefix}/system/control-plane", response_model=ResponseEnvelope[dict[str, Any]])
def get_control_plane(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["control_plane"])


@app.get(f"{settings.api_prefix}/system/capability-matrix", response_model=ResponseEnvelope[dict[str, Any]])
def get_capability_matrix(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["capability_matrix"])


@app.get(f"{settings.api_prefix}/system/product-families", response_model=ResponseEnvelope[dict[str, Any]])
def get_product_families(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["product_family_status"])


@app.get(f"{settings.api_prefix}/system/business/daily", response_model=ResponseEnvelope[dict[str, Any]])
def get_business_daily(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["business_metrics"]["daily"])


@app.get(f"{settings.api_prefix}/system/health", response_model=ResponseEnvelope[dict[str, Any]])
def get_health(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=snapshot["health_telemetry"])


@app.get(f"{settings.api_prefix}/system/audit-summary", response_model=ResponseEnvelope[dict[str, Any]])
def get_audit_summary(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, _ = get_latest_snapshot()
    data = {
        "latest_control_action_summary": {
            "type": snapshot["audit_context"]["last_control_action_type"],
            "request_id": snapshot["audit_context"]["last_control_action_request_id"],
            "ts_ms": snapshot["audit_context"]["last_control_action_ts_ms"],
            "by": snapshot["audit_context"]["last_control_action_by"],
            "result": snapshot["audit_context"]["last_control_action_result"],
            "reason_codes": snapshot["audit_context"]["last_control_action_reason_codes"],
            "audit_ref": snapshot["audit_context"]["last_control_action_audit_ref"],
        },
        "latest_write_action_summary": {
            "type": snapshot["audit_context"]["last_write_action_type"],
            "request_id": snapshot["audit_context"]["last_write_action_request_id"],
            "ts_ms": snapshot["audit_context"]["last_write_action_ts_ms"],
            "by": snapshot["audit_context"]["last_write_action_by"],
            "result": snapshot["audit_context"]["last_write_action_result"],
            "reason_codes": snapshot["audit_context"]["last_write_action_reason_codes"],
            "audit_ref": snapshot["audit_context"]["last_write_action_audit_ref"],
        },
        "last_state_revision_before": snapshot["audit_context"]["last_state_revision_before"],
        "last_state_revision_after": snapshot["audit_context"]["last_state_revision_after"],
    }
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=data)


@app.get(f"{settings.api_prefix}/system/source-context", response_model=ResponseEnvelope[dict[str, Any]])
def get_source_context(actor=Depends(current_actor)) -> ResponseEnvelope[dict[str, Any]]:
    snapshot, source = get_latest_snapshot()
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=source.model_dump(mode="json"))


@app.get(f"{settings.api_prefix}/learning/overview", response_model=ResponseEnvelope[LearningOverviewData])
def get_learning_overview(actor=Depends(current_actor)) -> ResponseEnvelope[LearningOverviewData]:
    snapshot, _ = get_latest_snapshot()
    data = LearningOverviewData(
        summary=snapshot["learning_state"]["observation_summary"],
        experiments=snapshot["learning_state"]["experiments"],
        approval_requirements={"approval_required": snapshot["learning_state"]["experiments"]["approval_required"]},
    )
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=data)


@app.get(f"{settings.api_prefix}/learning/hypotheses", response_model=ResponseEnvelope[LearningHypothesesData])
def get_learning_hypotheses(actor=Depends(current_actor)) -> ResponseEnvelope[LearningHypothesesData]:
    snapshot, _ = get_latest_snapshot()
    data = LearningHypothesesData(
        hypotheses=snapshot["learning_state"]["records"]["hypotheses"],
        experiments=snapshot["learning_state"]["records"]["experiments"],
        approval_requirements={"approval_required": snapshot["learning_state"]["experiments"]["approval_required"]},
    )
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=data)


@app.post(f"{settings.api_prefix}/control/recheck/j-canonical", response_model=ResponseEnvelope[RecheckResultData])
def post_j_canonical(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[RecheckResultData]:
    result, action_result = perform_recheck(envelope, actor, "J", "canonical")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/recheck/k-canonical", response_model=ResponseEnvelope[RecheckResultData])
def post_k_canonical(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[RecheckResultData]:
    result, action_result = perform_recheck(envelope, actor, "K", "canonical")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/recheck/j-closeout", response_model=ResponseEnvelope[RecheckResultData])
def post_j_closeout(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[RecheckResultData]:
    result, action_result = perform_recheck(envelope, actor, "J", "closeout")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/recheck/k-closeout", response_model=ResponseEnvelope[RecheckResultData])
def post_k_closeout(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[RecheckResultData]:
    result, action_result = perform_recheck(envelope, actor, "K", "closeout")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=RecheckResultData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/demo/validate", response_model=ResponseEnvelope[DemoValidateData])
def post_demo_validate(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[DemoValidateData]:
    result, action_result = perform_validate(envelope, actor)
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoValidateData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/demo/arm", response_model=ResponseEnvelope[DemoTransitionData])
def post_demo_arm(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[DemoTransitionData]:
    result, action_result = perform_demo_transition(envelope, actor, "arm")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoTransitionData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/demo/enable", response_model=ResponseEnvelope[DemoTransitionData])
def post_demo_enable(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[DemoTransitionData]:
    result, action_result = perform_demo_transition(envelope, actor, "enable")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoTransitionData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/demo/relock", response_model=ResponseEnvelope[DemoTransitionData])
def post_demo_relock(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[DemoTransitionData]:
    result, action_result = perform_demo_transition(envelope, actor, "relock")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=DemoTransitionData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/control/safe-recheck-bundle", response_model=ResponseEnvelope[SafeBundleData])
def post_safe_bundle(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[SafeBundleData]:
    result, action_result = perform_safe_bundle(envelope, actor)
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=SafeBundleData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/input/cost", response_model=ResponseEnvelope[InputAcceptedData])
def post_input_cost(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[InputAcceptedData]:
    result, action_result = apply_input_action(envelope, actor, "cost")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/input/event", response_model=ResponseEnvelope[InputAcceptedData])
def post_input_event(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[InputAcceptedData]:
    result, action_result = apply_input_action(envelope, actor, "event")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/input/manual-note", response_model=ResponseEnvelope[InputAcceptedData])
def post_input_note(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[InputAcceptedData]:
    result, action_result = apply_input_action(envelope, actor, "manual-note")
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


@app.post(f"{settings.api_prefix}/input/config-change", response_model=ResponseEnvelope[ConfigChangeAcceptedData])
def post_config_change(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[ConfigChangeAcceptedData]:
    result, action_result = apply_config_change(envelope, actor)
    return envelope_response(snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result, data=ConfigChangeAcceptedData(**result["data"]), audit_ref=result["audit_ref"], reason_codes=["replayed_request"] if action_result == "replayed" else [])


# ── 产品族配置写接口路由 / Product Family Config Write Routes ─────────────────


@app.post(
    f"{settings.api_prefix}/control/product-family/{{family}}/config",
    response_model=ResponseEnvelope[ProductFamilyConfigData],
)
def post_product_family_config(
    family: str,
    envelope: RequestEnvelope,
    actor=Depends(current_actor),
) -> ResponseEnvelope[ProductFamilyConfigData]:
    """
    修改指定产品族的控制配置 / Modify control configuration for a specific product family.

    payload 支持字段 / Supported payload fields:
    - enabled_switch: bool      是否启用该产品族 / Enable this product family
    - visibility_switch: bool   是否在 GUI 可见 / Make visible in GUI
    - mode_switch: str          模式切换（只允许 disabled/observe_only/shadow_only）
                                Mode switch (only allows disabled/observe_only/shadow_only)
    - action_permissions: dict  每个动作的开关，例如 {"new_order": false, "cancel": false}
                                Per-action switches, e.g. {"new_order": false, "cancel": false}

    安全 / Safety: 不能设置为 live 相关模式。需要 input:config scope。
    Cannot set to live-related modes. Requires input:config scope.
    """
    result, action_result = apply_product_family_config(envelope, actor, family)
    return envelope_response(
        snapshot=result["snapshot"],
        request_id=envelope.request_id,
        action_result=action_result,
        data=ProductFamilyConfigData(**result["data"]),
        audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


# ── 经营摘要路由 / Business Summary Route ────────────────────────────────────


@app.get(
    f"{settings.api_prefix}/system/business/summary",
    response_model=ResponseEnvelope[BusinessSummaryData],
)
def get_business_summary(actor=Depends(current_actor)) -> ResponseEnvelope[BusinessSummaryData]:
    """
    经营与收益完整摘要 / Complete business and income summary.

    比 /system/business/daily 更完整：包含历史条目列表和按类别成本分解。
    Richer than /system/business/daily: includes entry history and category-level cost breakdown.
    """
    snapshot, _ = get_latest_snapshot()
    summary = build_business_summary(snapshot)
    return envelope_response(
        snapshot=snapshot,
        request_id=None,
        action_result="success",
        data=BusinessSummaryData(**summary),
    )


# ── PnL 条目录入路由 / PnL Entry Input Route ─────────────────────────────────


@app.post(f"{settings.api_prefix}/input/pnl-entry", response_model=ResponseEnvelope[PnLEntryData])
def post_pnl_entry(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[PnLEntryData]:
    """
    录入 PnL 更新条目 / Record a PnL update entry.

    用于手动录入已实现盈亏 / 未实现盈亏更新，自动刷新每日经营摘要中的 PnL 指标。
    Used to manually record realized/unrealized PnL updates.
    Automatically refreshes PnL metrics in the daily business summary.

    payload 字段 / payload fields:
    - entry_type: str          条目类型 / Entry type
    - realized_pnl: float      累计增量（已实现）/ Cumulative delta (realized)
    - unrealized_pnl: float    当前快照值（未实现）/ Current snapshot value (unrealized)
    - symbol: str              涉及标的 / Symbol involved (optional)
    - note: str                备注 / Note (optional)
    - category: str            分类（用于 cost_breakdown）/ Category for cost_breakdown (optional)
    """
    result, action_result = apply_pnl_entry(envelope, actor)
    return envelope_response(
        snapshot=result["snapshot"],
        request_id=envelope.request_id,
        action_result=action_result,
        data=PnLEntryData(**result["data"]),
        audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )

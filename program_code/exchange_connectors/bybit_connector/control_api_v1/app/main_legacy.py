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
                        # ── L 章学习系统权限 / L-chapter learning system scopes ──
                        "learning:write",   # 录入观察/经验/假设/实验 / Record observations/lessons/hypotheses/experiments
                        "learning:manage",  # 审批假设/实验、完成实验 / Approve hypotheses/experiments, complete experiments
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


# ═══════════════════════════════════════════════════════════════════════════════
# L 章 Pydantic 响应模型 / L-Chapter Pydantic Response Models
#
# 以下模型覆盖学习系统五大模块的 API 响应：
# 观察流 / 经验记忆 / 假设队列 / 实验队列 / 净 PnL 仪表盘。
#
# The following models cover API responses for the five L-chapter modules:
# Observation Feed / Lessons Memory / Hypothesis Queue / Experiment Queue / Net PnL Dashboard.
# ═══════════════════════════════════════════════════════════════════════════════


class ObservationAcceptedData(BaseModel):
    """
    观察记录录入结果 / Result of recording an observation.

    当一条观察被成功写入观察流时返回此结构。
    Returned when an observation is successfully written to the observation feed.
    """

    accepted: bool = True
    observation_id: str
    record_count_delta: int = 1


class LessonAcceptedData(BaseModel):
    """
    经验教训录入结果 / Result of recording a lesson learned.

    当一条经验教训被成功写入经验记忆库时返回此结构。
    Returned when a lesson is successfully written to the lessons memory.
    """

    accepted: bool = True
    lesson_id: str
    record_count_delta: int = 1


class HypothesisAcceptedData(BaseModel):
    """
    假设录入结果 / Result of recording a hypothesis.

    假设的 confidence_level 始终为 "hypothesis"（原则 8：区分事实/推断/假设）。
    Hypothesis confidence_level is always "hypothesis" (Principle 8: distinguish fact/inference/hypothesis).
    """

    accepted: bool = True
    hypothesis_id: str
    status: str = "proposed"
    record_count_delta: int = 1


class ExperimentAcceptedData(BaseModel):
    """
    实验提案录入结果 / Result of recording an experiment proposal.

    如果 approval_required=True，实验状态为 pending_approval，需要 Operator 审批。
    If approval_required=True, experiment status is pending_approval, requiring Operator approval.
    """

    accepted: bool = True
    experiment_id: str
    status: str
    approval_required: bool
    record_count_delta: int = 1


class HypothesisVerdictData(BaseModel):
    """
    假设审批结果 / Result of hypothesis verdict by Operator.

    Operator 可以批准（approved）、拒绝（rejected）或归档（archived）假设。
    Operator can approve, reject, or archive a hypothesis.
    """

    hypothesis_id: str
    new_status: str
    operator_verdict: str


class ExperimentApprovalData(BaseModel):
    """
    实验审批结果 / Result of experiment approval/rejection by Operator.

    仅对 pending_approval 状态的实验有效。
    Only valid for experiments in pending_approval status.
    """

    experiment_id: str
    new_status: str
    operator_approval: str


class ExperimentCompletionData(BaseModel):
    """
    实验完成结果 / Result of experiment completion.

    记录实验结论和置信度级别，状态变为 completed。
    Records experiment conclusion and confidence level, status becomes completed.
    """

    experiment_id: str
    new_status: str
    result_summary: str
    result_confidence_level: str


class LearningFeedData(BaseModel):
    """
    完整学习观察流 / Complete learning observation feed.

    包含：最近观察 + 最近经验教训 + 摘要统计 + 记忆状态。
    Includes: recent observations + recent lessons + summary statistics + memory state.
    """

    observations_recent: list[dict[str, Any]] = Field(default_factory=list)
    lessons_recent: list[dict[str, Any]] = Field(default_factory=list)
    observation_summary: dict[str, Any] = Field(default_factory=dict)
    memory_state: dict[str, Any] = Field(default_factory=dict)
    totals: dict[str, Any] = Field(default_factory=dict)


class LearningExperimentsData(BaseModel):
    """
    实验队列完整视图 / Complete experiment queue view.

    包含：实验列表 + 待审批数量 + 审批开关状态。
    Includes: experiments list + pending approval count + approval switch status.
    """

    experiments: list[dict[str, Any]] = Field(default_factory=list)
    hypotheses: list[dict[str, Any]] = Field(default_factory=list)
    pending_approval_count: int = 0
    approval_required: bool = True


class NetPnLDashboardData(BaseModel):
    """
    含所有成本分解的净 PnL 仪表盘 / Net PnL dashboard with full cost breakdown.

    整合每日经营指标、成本分类、周期快照趋势和最近录入条目。
    Integrates daily business metrics, cost categories, period snapshot trends, and recent entries.
    """

    daily: dict[str, Any]
    cost_breakdown: dict[str, Any] = Field(default_factory=dict)
    period_snapshots: list[dict[str, Any]] = Field(default_factory=list)
    pnl_entries_recent: list[dict[str, Any]] = Field(default_factory=list)
    cost_entries_recent: list[dict[str, Any]] = Field(default_factory=list)
    net_pnl_trend: list[dict[str, Any]] = Field(default_factory=list)
    entry_totals: dict[str, Any] = Field(default_factory=dict)


class ReviewQueueData(BaseModel):
    """审核队列 / Review queue with pending and recently decided packets.
    待审核 + 最近已决定的审核包列表。"""
    pending_packets: list[dict[str, Any]] = Field(default_factory=list)
    recent_decided: list[dict[str, Any]] = Field(default_factory=list)
    pending_count: int = 0
    total_count: int = 0
    auto_pipeline_summary: dict[str, Any] = Field(default_factory=dict)


class ReviewDecisionData(BaseModel):
    """审核决定结果 / Result of a review decision on a packet.
    Operator 对审核包做出决定后的返回数据。"""
    packet_id: str
    decision: str
    new_status: str
    record_created: bool = False
    created_record_id: str | None = None


class AutoGenerationResultData(BaseModel):
    """自动生成结果 / Result of an auto-generation scan.
    自动扫描后生成的审核包统计。"""
    packets_generated: int = 0
    packet_ids: list[str] = Field(default_factory=list)
    scan_type: str = ""
    skipped_duplicates: int = 0


class AIConsultationResultData(BaseModel):
    """AI 咨询结果 / Result of AI consultation (stub for future H-chain integration).
    AI 咨询返回的数据（当前为 stub，未来接入 H 链）。"""
    packet_id: str
    ai_tier: str
    question_sent: str
    ai_response: str | None = None
    cost_usd: float = 0.0
    consultation_status: str = "stub_pending_h_chain_integration"


# ── L 章学习系统常量 / L-chapter Learning System Constants ────────────────────

# 观察类别白名单 / Allowed observation categories
# 用于验证观察记录的 category 字段
# Used to validate the category field of observation records
OBSERVATION_CATEGORIES = frozenset({"market", "execution", "cost", "system", "strategy", "other"})

# 经验教训类别白名单 / Allowed lesson categories
# 用于验证经验教训的 category 字段
# Used to validate the category field of lesson records
LESSON_CATEGORIES = frozenset({"market_pattern", "cost_insight", "execution_quality", "strategy", "system", "other"})

# 置信度级别白名单 / Allowed confidence levels
# 原则 8：所有结论区分事实 / 推断 / 假设
# Principle 8: all conclusions must distinguish fact / inference / hypothesis
CONFIDENCE_LEVELS = frozenset({"fact", "inference", "hypothesis"})

# 假设审批动作白名单 / Allowed hypothesis verdict actions
HYPOTHESIS_VERDICT_ACTIONS = frozenset({"approved", "rejected", "archived"})

# 实验审批动作白名单 / Allowed experiment approval actions
EXPERIMENT_APPROVAL_ACTIONS = frozenset({"approved", "rejected"})

# ── L 章自动学习管线常量 / L-chapter Auto Learning Pipeline Constants ────────
# 审核包状态白名单 / Review packet status whitelist
REVIEW_PACKET_STATUSES = frozenset({
    "pending_review",    # 待审核
    "approved",          # 已批准
    "rejected",          # 已拒绝
    "deferred",          # 已搁置
    "ai_consulted",      # AI 已咨询（等待最终决定）
})

# 审核包类型白名单 / Review packet type whitelist
REVIEW_PACKET_TYPES = frozenset({
    "auto_observation",   # 自动观察
    "auto_lesson",        # 自动经验
    "auto_hypothesis",    # 自动假设
})

# 审核包决策动作白名单 / Review packet decision action whitelist
REVIEW_DECISION_ACTIONS = frozenset({
    "approve",   # 批准
    "reject",    # 拒绝
    "defer",     # 搁置
    "ask_ai",    # 询问 AI
})

# 自动观察扫描类型白名单 / Auto scan type whitelist
AUTO_SCAN_TYPES = frozenset({"observations", "lessons", "hypotheses"})


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

    # ── L 章学习状态派生字段 / L-chapter learning derived fields ──────────────
    # 从 records 列表动态计算摘要统计，确保派生字段始终与底层数据一致。
    # Dynamically compute summary statistics from records lists, ensuring
    # derived fields always stay consistent with underlying data.
    ls = state.get("learning_state", {})
    ls_records = ls.get("records", {})

    # 统计活跃假设数（状态为 proposed / under_review / testing）
    # Count active hypotheses (status in proposed / under_review / testing)
    active_hyp = [h for h in ls_records.get("hypotheses", [])
                  if h.get("status") in {"proposed", "under_review", "testing"}]
    ls.setdefault("hypotheses", {})["active_hypothesis_count"] = len(active_hyp)

    # 统计活跃实验数（状态为 proposed / pending_approval / approved / in_progress）
    # Count active experiments (status in proposed / pending_approval / approved / in_progress)
    active_exp = [e for e in ls_records.get("experiments", [])
                  if e.get("status") in {"proposed", "pending_approval", "approved", "in_progress"}]
    ls.setdefault("experiments", {})["active_experiment_count"] = len(active_exp)

    # 更新观察摘要计数 / Update observation summary counts
    obs_summary = ls.setdefault("observation_summary", {})
    obs_summary["recent_lessons_count"] = len(ls_records.get("lessons", []))
    obs_summary["recent_hypothesis_count"] = len(ls_records.get("hypotheses", []))
    obs_summary["recent_experiment_proposal_count"] = len(ls_records.get("experiments", []))

    # 学习进展状态始终为 observe_and_record_only（当前系统 read_only / disabled）
    # Learning progression state always observe_and_record_only while system is read_only
    ls.setdefault("derived", {})["learning_progression_state"] = "observe_and_record_only"

    # 自动学习管线审核包计数 / Auto learning pipeline review queue count
    review_queue = ls_records.get("review_queue", [])
    auto_pipeline = ls.setdefault("auto_pipeline", {})
    auto_pipeline["pending_review_count"] = len(
        [p for p in review_queue if p.get("status") == "pending_review"]
    )

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
            # ── L 章：学习 / 自我感知 / Net PnL ──
            # L Chapter: Learning / Self-Observability / Net PnL
            "L": {
                "chapter_display_name": "L (Learning / Self-Observability / Net PnL)",
                "chapter_state": "implemented",
                "chapter_interpretation": "learning_observe_and_record_active",
                "current_phase_ready": True,
                "readiness_scope": "observe_and_record_only",
                "execution_meaning": "does_not_grant_live_execution",
                "last_verified_ts_ms": ts,
                "source_of_truth": "learning_state",
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
            },
            # ── L 章周期快照 / L-chapter period snapshots ──
            # 用于 Net PnL 趋势追踪：Operator 手动保存当前经营指标快照。
            # For Net PnL trend tracking: Operator manually saves current business metrics snapshot.
            "period_snapshots": [],
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
            # ── L 章学习记录存储 / L-chapter learning record storage ──
            # observations: 观察流记录 / Observation feed records
            # lessons: 经验教训记录 / Lessons memory records
            # hypotheses: 假设队列 / Hypothesis queue
            # experiments: 实验队列 / Experiment queue
            # manual_notes: 手动备注（已有）/ Manual notes (existing)
            "records": {
                "observations": [],
                "lessons": [],
                "hypotheses": [],
                "experiments": [],
                "manual_notes": [],
                "review_queue": [],
            },
            # ── 自动学习管线摘要 / Auto learning pipeline summary ──
            "auto_pipeline": {
                "last_observation_scan_ts_ms": None,
                "last_lesson_scan_ts_ms": None,
                "last_hypothesis_scan_ts_ms": None,
                "total_packets_generated": 0,
                "total_packets_approved": 0,
                "total_packets_rejected": 0,
            },
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


# ═══════════════════════════════════════════════════════════════════════════════
# L 章：学习系统逻辑函数 / L-Chapter: Learning System Logic Functions
#
# 五大模块的写入 / 审批 / 查询逻辑。
# 所有写操作遵循标准流程：scope → snapshot → identity → idempotency → revision → mutate。
#
# Write / approve / query logic for the five learning modules.
# All write operations follow the standard flow:
# scope → snapshot → identity → idempotency → revision → mutate.
# ═══════════════════════════════════════════════════════════════════════════════


def apply_learning_observation(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    录入一条观察记录到观察流 / Record an observation to the observation feed.

    payload 必填字段 / Required payload fields:
    - title: str        观察标题 / Observation title
    - detail: str       观察详情 / Observation detail
    - category: str     类别（market/execution/cost/system/strategy/other）
    - confidence_level: str  置信度（fact/inference/hypothesis）

    payload 可选字段 / Optional payload fields:
    - related_hypothesis_id: str  关联假设 ID / Related hypothesis ID
    - tags: list[str]            标签 / Tags
    """
    require_scope(actor, "learning:write")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    # 验证必填字段 / Validate required fields
    p = envelope.payload
    title = str(p.get("title", "")).strip()
    detail = str(p.get("detail", "")).strip()
    category = str(p.get("category", "")).strip()
    confidence = str(p.get("confidence_level", "")).strip()
    if not title or not detail:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_title_or_detail"]})
    if category not in OBSERVATION_CATEGORIES:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_observation_category"]})
    if confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_confidence_level"]})

    ts = now_ms()
    observation_id = f"obs:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        # 构建观察记录 / Build observation record
        record = {
            "observation_id": observation_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            "source": "operator_input",
            "category": category,
            "confidence_level": confidence,
            "title": title,
            "detail": detail,
            "related_hypothesis_id": p.get("related_hypothesis_id"),
            "tags": list(p.get("tags", [])),
        }
        # 确保 observations 列表存在（兼容旧快照）
        # Ensure observations list exists (backward-compatible with old state files)
        ls_records = state["learning_state"].setdefault("records", {})
        ls_records.setdefault("observations", []).append(record)

        # 更新最后观察时间 / Update last observation timestamp
        state["learning_state"]["observation_summary"]["last_observation_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_observation", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "observation_id": observation_id, "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "observation_id": observation_id, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_learning_lesson(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    录入一条经验教训到经验记忆库 / Record a lesson to the lessons memory.

    payload 必填字段 / Required payload fields:
    - title: str        经验标题 / Lesson title
    - detail: str       经验详情 / Lesson detail
    - category: str     类别（market_pattern/cost_insight/execution_quality/strategy/system/other）
    - confidence_level: str  置信度（fact/inference/hypothesis）

    payload 可选字段 / Optional payload fields:
    - source_observation_ids: list[str]  来源观察 ID 列表 / Source observation IDs
    - actionable: bool                   是否可操作 / Whether actionable
    - related_hypothesis_ids: list[str]  关联假设 ID 列表 / Related hypothesis IDs
    - tags: list[str]                    标签 / Tags
    """
    require_scope(actor, "learning:write")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    title = str(p.get("title", "")).strip()
    detail = str(p.get("detail", "")).strip()
    category = str(p.get("category", "")).strip()
    confidence = str(p.get("confidence_level", "")).strip()
    if not title or not detail:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_title_or_detail"]})
    if category not in LESSON_CATEGORIES:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_lesson_category"]})
    if confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_confidence_level"]})

    ts = now_ms()
    lesson_id = f"lesson:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        record = {
            "lesson_id": lesson_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            "source_observation_ids": list(p.get("source_observation_ids", [])),
            "confidence_level": confidence,
            "category": category,
            "title": title,
            "detail": detail,
            "actionable": bool(p.get("actionable", False)),
            "related_hypothesis_ids": list(p.get("related_hypothesis_ids", [])),
            "tags": list(p.get("tags", [])),
        }
        ls_records = state["learning_state"].setdefault("records", {})
        ls_records.setdefault("lessons", []).append(record)

        # 更新记忆最后更新时间 / Update memory last update timestamp
        state["learning_state"]["memory"]["last_memory_update_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_lesson", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "lesson_id": lesson_id, "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "lesson_id": lesson_id, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_learning_hypothesis(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    提出一条假设到假设队列 / Propose a hypothesis to the hypothesis queue.

    原则 8：假设的 confidence_level 始终强制为 "hypothesis"，不由调用方指定。
    Principle 8: hypothesis confidence_level is always forced to "hypothesis", not caller-specified.

    payload 必填字段 / Required payload fields:
    - title: str                假设标题 / Hypothesis title
    - description: str          假设描述 / Hypothesis description
    - testable_prediction: str  可检验的预测 / Testable prediction

    payload 可选字段 / Optional payload fields:
    - supporting_observation_ids: list[str]  支持该假设的观察 ID / Supporting observation IDs
    - supporting_lesson_ids: list[str]       支持该假设的经验 ID / Supporting lesson IDs
    - tags: list[str]                        标签 / Tags
    """
    require_scope(actor, "learning:write")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    title = str(p.get("title", "")).strip()
    description = str(p.get("description", "")).strip()
    testable_prediction = str(p.get("testable_prediction", "")).strip()
    if not title or not description or not testable_prediction:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_required_hypothesis_fields"]})

    ts = now_ms()
    hypothesis_id = f"hyp:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        record = {
            "hypothesis_id": hypothesis_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            # 原则 8：强制为 hypothesis / Principle 8: forced to hypothesis
            "status": "proposed",
            "confidence_level": "hypothesis",
            "title": title,
            "description": description,
            "testable_prediction": testable_prediction,
            "supporting_observation_ids": list(p.get("supporting_observation_ids", [])),
            "supporting_lesson_ids": list(p.get("supporting_lesson_ids", [])),
            "related_experiment_id": None,
            "operator_verdict": None,
            "operator_verdict_ts_ms": None,
            "operator_verdict_reason": None,
            "tags": list(p.get("tags", [])),
        }
        state["learning_state"]["records"]["hypotheses"].append(record)
        state["learning_state"]["hypotheses"]["last_hypothesis_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_hypothesis", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "hypothesis_id": hypothesis_id, "status": "proposed", "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "hypothesis_id": hypothesis_id, "status": "proposed", "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


def apply_learning_experiment(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    提出一项实验到实验队列 / Propose an experiment to the experiment queue.

    如果当前 learning_state.experiments.approval_required=True，
    实验状态初始化为 pending_approval；否则直接 approved。
    If approval_required=True, experiment status starts as pending_approval; otherwise approved.

    payload 必填字段 / Required payload fields:
    - hypothesis_id: str    关联假设 ID / Linked hypothesis ID (must exist)
    - title: str            实验标题 / Experiment title
    - description: str      实验描述 / Experiment description
    - method: str           实验方法 / Experiment method
    - success_criteria: str 成功标准 / Success criteria

    payload 可选字段 / Optional payload fields:
    - risk_assessment: str  风险评估 / Risk assessment
    - tags: list[str]       标签 / Tags
    """
    require_scope(actor, "learning:write")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    hypothesis_id = str(p.get("hypothesis_id", "")).strip()
    title = str(p.get("title", "")).strip()
    description = str(p.get("description", "")).strip()
    method = str(p.get("method", "")).strip()
    success_criteria = str(p.get("success_criteria", "")).strip()
    if not hypothesis_id or not title or not description or not method or not success_criteria:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_required_experiment_fields"]})

    # 验证关联假设存在 / Verify linked hypothesis exists
    hyp_list = snapshot["learning_state"]["records"]["hypotheses"]
    if not any(h.get("hypothesis_id") == hypothesis_id for h in hyp_list):
        raise HTTPException(status_code=400, detail={"reason_codes": ["hypothesis_not_found"]})

    # 快照当前审批要求 / Snapshot current approval requirement
    approval_required = snapshot["learning_state"]["experiments"]["approval_required"]
    initial_status = "pending_approval" if approval_required else "approved"

    ts = now_ms()
    experiment_id = f"exp:{ts}"

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        record = {
            "experiment_id": experiment_id,
            "recorded_ts_ms": ts,
            "recorded_by": actor.actor_id,
            "status": initial_status,
            "hypothesis_id": hypothesis_id,
            "title": title,
            "description": description,
            "method": method,
            "success_criteria": success_criteria,
            "risk_assessment": str(p.get("risk_assessment", "")),
            "approval_required": approval_required,
            "operator_approval": None,
            "operator_approval_ts_ms": None,
            "operator_approval_reason": None,
            "result_summary": None,
            "result_confidence_level": None,
            "completed_ts_ms": None,
            "tags": list(p.get("tags", [])),
        }
        state["learning_state"]["records"]["experiments"].append(record)
        state["learning_state"]["experiments"]["last_experiment_proposal_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="learning_experiment", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "accepted": True, "experiment_id": experiment_id,
                "status": initial_status, "approval_required": approval_required,
                "record_count_delta": 1,
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
            "accepted": True, "experiment_id": experiment_id,
            "status": initial_status, "approval_required": approval_required,
            "record_count_delta": 1,
        },
        "snapshot": final_state,
    }, "success"


def apply_hypothesis_verdict(
    envelope: RequestEnvelope, actor: AuthenticatedActor, hypothesis_id: str
) -> tuple[dict[str, Any], str]:
    """
    Operator 对假设做出审批判定 / Operator renders verdict on a hypothesis.

    payload 必填字段 / Required payload fields:
    - verdict: str  判定结果（approved / rejected / archived）
    - reason: str   判定理由 / Verdict reason (optional but recommended)

    状态转换 / Status transitions:
    - proposed → approved / rejected / archived
    - under_review → approved / rejected / archived
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    verdict = str(p.get("verdict", "")).strip()
    if verdict not in HYPOTHESIS_VERDICT_ACTIONS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_hypothesis_verdict"]})

    # 查找假设 / Find the hypothesis
    hyp_list = snapshot["learning_state"]["records"]["hypotheses"]
    target = None
    target_idx = -1
    for idx, h in enumerate(hyp_list):
        if h.get("hypothesis_id") == hypothesis_id:
            target = h
            target_idx = idx
            break
    if target is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["hypothesis_not_found"]})

    ts = now_ms()
    # 映射 verdict → 新状态 / Map verdict → new status
    status_map = {"approved": "validated", "rejected": "invalidated", "archived": "archived"}
    new_status = status_map[verdict]

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        hyp = state["learning_state"]["records"]["hypotheses"][target_idx]
        hyp["status"] = new_status
        hyp["operator_verdict"] = verdict
        hyp["operator_verdict_ts_ms"] = ts
        hyp["operator_verdict_reason"] = str(p.get("reason", ""))

        audit_ref = _write_audit_fields(
            state, action_type="hypothesis_verdict", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"hypothesis_id": hypothesis_id, "new_status": new_status, "operator_verdict": verdict},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"hypothesis_id": hypothesis_id, "new_status": new_status, "operator_verdict": verdict},
        "snapshot": final_state,
    }, "success"


def apply_experiment_approval(
    envelope: RequestEnvelope, actor: AuthenticatedActor, experiment_id: str
) -> tuple[dict[str, Any], str]:
    """
    Operator 审批或拒绝实验 / Operator approves or rejects an experiment.

    仅对 pending_approval 状态的实验有效。
    Only valid for experiments in pending_approval status.

    payload 必填字段 / Required payload fields:
    - action: str   审批动作（approved / rejected）
    - reason: str   理由 / Reason (optional but recommended)
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    action = str(p.get("action", "")).strip()
    if action not in EXPERIMENT_APPROVAL_ACTIONS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_experiment_approval_action"]})

    # 查找实验 / Find the experiment
    exp_list = snapshot["learning_state"]["records"]["experiments"]
    target_idx = -1
    for idx, e in enumerate(exp_list):
        if e.get("experiment_id") == experiment_id:
            if e.get("status") != "pending_approval":
                raise HTTPException(status_code=400, detail={"reason_codes": ["experiment_not_pending_approval"]})
            target_idx = idx
            break
    if target_idx == -1:
        raise HTTPException(status_code=404, detail={"reason_codes": ["experiment_not_found"]})

    ts = now_ms()

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        exp = state["learning_state"]["records"]["experiments"][target_idx]
        exp["status"] = action  # "approved" or "rejected"
        exp["operator_approval"] = action
        exp["operator_approval_ts_ms"] = ts
        exp["operator_approval_reason"] = str(p.get("reason", ""))

        audit_ref = _write_audit_fields(
            state, action_type="experiment_approval", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"experiment_id": experiment_id, "new_status": action, "operator_approval": action},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"experiment_id": experiment_id, "new_status": action, "operator_approval": action},
        "snapshot": final_state,
    }, "success"


def apply_experiment_completion(
    envelope: RequestEnvelope, actor: AuthenticatedActor, experiment_id: str
) -> tuple[dict[str, Any], str]:
    """
    标记实验完成并录入结论 / Mark an experiment as completed and record conclusion.

    仅对 approved 或 in_progress 状态的实验有效。
    Only valid for experiments in approved or in_progress status.

    payload 必填字段 / Required payload fields:
    - result_summary: str           实验结论摘要 / Experiment conclusion summary
    - result_confidence_level: str  结论置信度（fact/inference/hypothesis）
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    result_summary = str(p.get("result_summary", "")).strip()
    result_confidence = str(p.get("result_confidence_level", "")).strip()
    if not result_summary:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_result_summary"]})
    if result_confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_confidence_level"]})

    # 查找实验 / Find the experiment
    exp_list = snapshot["learning_state"]["records"]["experiments"]
    target_idx = -1
    for idx, e in enumerate(exp_list):
        if e.get("experiment_id") == experiment_id:
            if e.get("status") not in {"approved", "in_progress"}:
                raise HTTPException(status_code=400, detail={"reason_codes": ["experiment_not_completable"]})
            target_idx = idx
            break
    if target_idx == -1:
        raise HTTPException(status_code=404, detail={"reason_codes": ["experiment_not_found"]})

    ts = now_ms()

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        exp = state["learning_state"]["records"]["experiments"][target_idx]
        exp["status"] = "completed"
        exp["result_summary"] = result_summary
        exp["result_confidence_level"] = result_confidence
        exp["completed_ts_ms"] = ts

        audit_ref = _write_audit_fields(
            state, action_type="experiment_completion", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "experiment_id": experiment_id, "new_status": "completed",
                "result_summary": result_summary, "result_confidence_level": result_confidence,
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
            "experiment_id": experiment_id, "new_status": "completed",
            "result_summary": result_summary, "result_confidence_level": result_confidence,
        },
        "snapshot": final_state,
    }, "success"


def apply_pnl_period_snapshot(
    envelope: RequestEnvelope, actor: AuthenticatedActor
) -> tuple[dict[str, Any], str]:
    """
    保存当前经营指标为周期快照 / Save current business metrics as a period snapshot.

    用于 Net PnL 趋势追踪：Operator 手动冻结当前时刻的经营指标。
    For Net PnL trend tracking: Operator manually freezes current-moment business metrics.

    payload 必填字段 / Required payload fields:
    - period_label: str  周期标签，例如 "2026-03-26" / Period label, e.g. "2026-03-26"
    """
    require_scope(actor, "input:cost")  # 复用 cost scope / Reuse cost scope
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    period_label = str(p.get("period_label", "")).strip()
    if not period_label:
        raise HTTPException(status_code=400, detail={"reason_codes": ["missing_period_label"]})

    ts = now_ms()

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        daily = state["business_metrics"]["daily"]

        # 构建成本分解快照 / Build cost breakdown snapshot
        cost_breakdown: dict[str, float] = {}
        for entry in state.get("records", {}).get("cost_entries", []):
            cat = str(entry.get("category", "manual"))
            cost_breakdown[cat] = round(cost_breakdown.get(cat, 0.0) + float(entry.get("amount", 0.0)), 8)

        period_record = {
            "snapshot_ts_ms": ts,
            "period_label": period_label,
            "realized_pnl": daily.get("realized_pnl", 0.0),
            "unrealized_pnl": daily.get("unrealized_pnl", 0.0),
            "gross_pnl": daily.get("gross_pnl", 0.0),
            "total_cost": daily.get("total_cost", 0.0),
            "net_operating_pnl": daily.get("net_operating_pnl", 0.0),
            "cost_breakdown": cost_breakdown,
            "recorded_by": actor.actor_id,
        }

        # 确保 period_snapshots 列表存在（兼容旧快照文件）
        # Ensure period_snapshots list exists (backward-compatible)
        state["business_metrics"].setdefault("period_snapshots", []).append(period_record)

        audit_ref = _write_audit_fields(
            state, action_type="pnl_period_snapshot", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {"accepted": True, "record_count_delta": 1},
            "snapshot": compiled,
        }
        _store_idempotent_response(compiled, envelope, response)
        STORE.write(compiled)
        return compiled

    final_state = STORE.mutate(mutator)
    return {
        "audit_ref": final_state["audit_context"]["last_write_action_audit_ref"],
        "data": {"accepted": True, "record_count_delta": 1},
        "snapshot": final_state,
    }, "success"


# ═══════════════════════════════════════════════════════════════════════════════
# L 章自动学习管线 / L-Chapter Auto Learning Pipeline
#
# 核心概念：审核包 (Review Packet)
# 系统自动扫描运行状态生成发现 → 打包成简单易懂的审核包 → Operator 审批
# 灵感来源：I8 Manual Approval Packet，但面向非金融专业 Operator 大幅简化。
#
# Core concept: Review Packet
# System auto-scans runtime state → packages findings into simple review packets → Operator decides
# Inspired by I8 Manual Approval Packet, radically simplified for non-financial-expert Operator.
#
# 原则 7 保证：自动生成只创建审核包，不自动创建正式记录。
# Principle 7 guarantee: auto-generation only creates review packets, never creates actual records.
# ═══════════════════════════════════════════════════════════════════════════════


def _content_hash(text: str) -> str:
    """生成内容指纹，用于审核包去重 / Generate content fingerprint for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_review_packet(
    *,
    packet_type: str,
    what_happened: str,
    why_it_matters: str,
    confidence_level: str,
    target_collection: str,
    record_data: dict[str, Any],
    ai_recommended: bool = True,
    ai_tier: str = "light",
    ai_question: str = "",
    ai_context: dict[str, Any] | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """
    构建标准审核包 / Build a standard review packet.

    每个审核包包含：
    1. 简要说明 (what_happened) — 大白话，无金融术语
    2. 为什么重要 (why_it_matters) — 后果分析，通俗易懂
    3. 你的选择 (options) — 每个选项附带后果说明
    4. 置信度标签 (confidence_level) — 事实/推断/假设
    5. AI 咨询建议 — 推荐层级 + 预估成本 + 预生成问题

    Each packet contains:
    1. what_happened — plain language, no jargon
    2. why_it_matters — consequence analysis in simple terms
    3. options — each option with consequence description
    4. confidence_level — fact / inference / hypothesis
    5. AI consultation — recommended tier + estimated cost + pre-built question
    """
    ts = now_ms()
    packet_id = f"rpkt:{ts}"

    # 按类型设定固定后果说明 / Fixed consequence text per packet type
    # 用大白话让非金融专业的 Operator 一眼就能理解每个选择的结果
    consequence_map = {
        "auto_observation": {
            "approve": "记录为正式观察，系统会记住这个发现并用于后续学习 / Record as observation, system will remember this for future learning",
            "reject": "丢弃这个发现，系统不会记住它 / Discard, system will not remember this",
            "defer": "暂不处理，下次审核时再看 / Skip for now, review later",
        },
        "auto_lesson": {
            "approve": "记录为正式经验，系统会参考这条经验来改进判断 / Record as lesson, system will use this to improve judgment",
            "reject": "丢弃这条经验总结，不纳入系统记忆 / Discard, not added to system memory",
            "defer": "暂不处理，下次审核时再看 / Skip for now, review later",
        },
        "auto_hypothesis": {
            "approve": "正式提出假设，系统会追踪并寻找验证机会 / Formally propose hypothesis, system will track and seek validation",
            "reject": "丢弃这个假设，系统不会追踪它 / Discard, system will not track this",
            "defer": "暂不处理，下次审核时再看 / Skip for now, review later",
        },
    }
    consequences = consequence_map.get(packet_type, consequence_map["auto_observation"])

    # AI 咨询成本估算（参考 H2 query_budget 定义）
    # AI consultation cost estimate (referencing H2 query_budget definitions)
    cost_map = {"light": 0.02, "standard": 0.05, "none": 0.0}
    estimated_cost = cost_map.get(ai_tier, 0.02)

    content_text = f"{packet_type}:{record_data.get('title', '')}:{record_data.get('category', '')}"

    return {
        "packet_id": packet_id,
        "packet_type": packet_type,
        "created_ts_ms": ts,
        "status": "pending_review",
        "source": "system_auto",
        "_content_hash": _content_hash(content_text),
        # ── 简要说明 / What Happened ──
        "what_happened": what_happened,
        # ── 为什么重要 / Why It Matters ──
        "why_it_matters": why_it_matters,
        # ── 你的选择 / Your Options ──
        "options": {
            "approve": {"label": "批准 / Approve", "consequence": consequences["approve"]},
            "reject": {"label": "拒绝 / Reject", "consequence": consequences["reject"]},
            "defer": {"label": "搁置 / Defer", "consequence": consequences["defer"]},
        },
        # ── 置信度标签 / Confidence Tag (原则 8 / Principle 8) ──
        "confidence_level": confidence_level,
        # ── AI 咨询建议 / AI Consultation Suggestion ──
        "ai_consultation": {
            "recommended": ai_recommended,
            "recommended_tier": ai_tier,
            "estimated_cost_usd": estimated_cost,
            "pre_built_question": ai_question,
            "question_context": ai_context or {},
        },
        # ── 候选记录 / Candidate record (批准后创建) ──
        "candidate_record": {
            "target_collection": target_collection,
            "record_data": record_data,
        },
        # ── 审核追踪 / Review audit trail ──
        "decided_by": None,
        "decided_ts_ms": None,
        "decision": None,
        "decision_reason": None,
        "ai_consultation_result": None,
        "ai_consultation_cost_usd": None,
        "tags": tags or [],
    }


def _build_ai_question_for_observation(title: str, detail: str, category: str) -> str:
    """
    为自动观察构建 AI 咨询问题 / Build AI question for auto-observation.

    参考 I 章紧凑 JSON 模式，生成简洁有效的问题。
    Inspired by I-chapter compact JSON pattern, generates concise effective questions.
    """
    return (
        f"系统自动观察到以下情况：{title}。"
        f"详情：{detail}。类别：{category}。"
        f"请用简单的语言评估："
        f"1）这个观察是否值得记录？"
        f"2）置信度应该是「事实」还是「推断」？"
        f"3）是否有需要注意的关联因素？"
    )


def _build_ai_question_for_lesson(title: str, detail: str, obs_count: int) -> str:
    """为自动经验构建 AI 咨询问题 / Build AI question for auto-lesson."""
    return (
        f"系统从 {obs_count} 条相关观察中总结出一条可能的经验：{title}。"
        f"详情：{detail}。"
        f"请用简单的语言评估："
        f"1）这个经验总结是否准确合理？"
        f"2）对未来的系统运行有什么指导意义？"
        f"3）是否需要更多观察来确认？"
    )


def _build_ai_question_for_hypothesis(title: str, prediction: str) -> str:
    """为自动假设构建 AI 咨询问题 / Build AI question for auto-hypothesis."""
    return (
        f"系统基于已有经验提出一个假设：{title}。"
        f"可检验预测：{prediction}。"
        f"请用简单的语言评估："
        f"1）这个假设是否有道理？"
        f"2）如果假设成立，会有什么实际影响？"
        f"3）建议用什么方法来验证这个假设？"
    )


# ── 自动观察扫描 / Auto Observation Scanner ──────────────────────────────────


def generate_auto_observations(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    扫描系统运行状态，自动生成观察审核包 / Scan system runtime state, generate observation review packets.

    扫描来源 / Scan sources:
    - health_telemetry: 健康门控、延迟、超时 / Health gates, latency, timeout
    - business_metrics: 成本趋势、PnL 变化 / Cost trends, PnL changes
    - learning_state: 观察模式、空闲检测 / Observation patterns, idle detection

    每条规则输出一个审核包，用大白话描述发现和后果。
    Each rule outputs a review packet in plain language describing finding and consequences.
    """
    packets: list[dict[str, Any]] = []
    health = snapshot.get("health_telemetry", {})
    gates = health.get("gates", {})
    daily = snapshot.get("business_metrics", {}).get("daily", {})
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})
    global_rt = snapshot.get("global_runtime", {})

    # ── 规则 1：健康门控失败 / Rule 1: Health gate failure ──
    overall_health = gates.get("health_gates_overall_state", "passed")
    if overall_health != "passed":
        failed_gates = [
            k.replace("_gate_state", "").replace("_", " ")
            for k, v in gates.items()
            if k.endswith("_gate_state") and v != "passed" and k != "health_gates_overall_state"
        ]
        failed_str = "、".join(failed_gates) if failed_gates else "未知项"
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"系统健康检查未通过：{failed_str} 未达标 / Health check failed: {failed_str}",
            why_it_matters=(
                "系统不健康时，AI 的观察和判断质量可能下降。"
                "按照原则 5，应先保证系统健康再做其他判断。"
                " / When system is unhealthy, AI quality may degrade. Principle 5: system health first."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"系统健康检查未通过：{failed_str}",
                "detail": f"健康门控整体状态 {overall_health}，未通过项：{failed_str}",
                "category": "system",
                "confidence_level": "fact",
                "tags": ["auto_generated", "health"],
            },
            ai_recommended=False,
            ai_tier="none",
            ai_question="",
            tags=["health", "auto_generated"],
        ))

    # ── 规则 2：AI 成本偏高 / Rule 2: AI cost elevated ──
    ai_cost = float(daily.get("ai_api_cost", 0.0))
    if ai_cost > 0.5:
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"今日 AI 调用成本已达 ${ai_cost:.2f} / Today's AI cost reached ${ai_cost:.2f}",
            why_it_matters=(
                "AI 成本是净利润的直接扣除项。成本过高会侵蚀收益。"
                "应关注是否有不必要的 AI 调用。"
                " / AI cost directly reduces net profit. Monitor for unnecessary calls."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"AI 调用成本偏高：${ai_cost:.2f}",
                "detail": f"今日 AI API 调用累计成本 ${ai_cost:.2f}，超过 $0.50 阈值",
                "category": "cost",
                "confidence_level": "fact",
                "tags": ["auto_generated", "cost", "ai_cost"],
            },
            ai_recommended=True,
            ai_tier="light",
            ai_question=_build_ai_question_for_observation(
                f"AI 调用成本偏高：${ai_cost:.2f}",
                f"今日 AI API 调用累计成本 ${ai_cost:.2f}，超过 $0.50 阈值",
                "cost",
            ),
            ai_context={"metric": "ai_api_cost", "value": ai_cost, "threshold": 0.5},
            tags=["cost", "auto_generated"],
        ))

    # ── 规则 3：数据新鲜度下降 / Rule 3: Data freshness degraded ──
    freshness = global_rt.get("facts", {}).get("runtime_data_freshness_state", "fresh")
    if freshness != "fresh":
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"数据新鲜度状态异常：{freshness} / Data freshness degraded: {freshness}",
            why_it_matters=(
                "数据不新鲜意味着系统看到的市场信息可能是过时的。"
                "在此状态下做出的任何判断都不够可靠。"
                " / Stale data means market info may be outdated. Judgments become unreliable."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"数据新鲜度异常：{freshness}",
                "detail": f"runtime_data_freshness_state = {freshness}，非 fresh 状态",
                "category": "system",
                "confidence_level": "fact",
                "tags": ["auto_generated", "freshness"],
            },
            ai_recommended=False,
            ai_tier="none",
            ai_question="",
            tags=["freshness", "auto_generated"],
        ))

    # ── 规则 4：PnL 显著变化 / Rule 4: Significant PnL change ──
    net_pnl = float(daily.get("net_operating_pnl", 0.0))
    if abs(net_pnl) > 100.0:
        direction = "盈利" if net_pnl > 0 else "亏损"
        direction_en = "profit" if net_pnl > 0 else "loss"
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened=f"今日净经营 PnL 显著变化：{direction} ${abs(net_pnl):.2f} / Net PnL significant: {direction_en} ${abs(net_pnl):.2f}",
            why_it_matters=(
                f"净 PnL {direction} ${abs(net_pnl):.2f} 超过 $100 的关注阈值。"
                "建议记录并分析原因，以便优化策略。"
                f" / Net PnL {direction_en} ${abs(net_pnl):.2f} exceeds $100 attention threshold."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": f"净 PnL 显著{direction}：${abs(net_pnl):.2f}",
                "detail": f"今日净经营 PnL = ${net_pnl:.2f}（{direction} ${abs(net_pnl):.2f}）",
                "category": "cost",
                "confidence_level": "fact",
                "tags": ["auto_generated", "pnl"],
            },
            ai_recommended=True,
            ai_tier="light",
            ai_question=_build_ai_question_for_observation(
                f"净 PnL 显著{direction}：${abs(net_pnl):.2f}",
                f"今日净经营 PnL = ${net_pnl:.2f}",
                "cost",
            ),
            ai_context={"metric": "net_operating_pnl", "value": net_pnl, "threshold": 100.0},
            tags=["pnl", "auto_generated"],
        ))

    # ── 规则 5：长时间无观察 / Rule 5: No observations for extended period ──
    last_obs_ts = ls.get("observation_summary", {}).get("last_observation_ts_ms")
    observations = ls_records.get("observations", [])
    if len(observations) == 0 and last_obs_ts is None:
        packets.append(_build_review_packet(
            packet_type="auto_observation",
            what_happened="系统从未记录过观察 / No observations have been recorded yet",
            why_it_matters=(
                "学习系统需要观察数据作为基础。没有观察就无法总结经验、提出假设。"
                "建议开始记录系统运行中的发现。"
                " / Learning system needs observations as foundation. No observations means no learning."
            ),
            confidence_level="fact",
            target_collection="observations",
            record_data={
                "title": "学习系统初始化：首次观察扫描",
                "detail": "系统自动扫描已启动，但尚未有任何观察记录。这是首次扫描。",
                "category": "system",
                "confidence_level": "fact",
                "tags": ["auto_generated", "initialization"],
            },
            ai_recommended=False,
            ai_tier="none",
            ai_question="",
            tags=["initialization", "auto_generated"],
        ))

    return packets


# ── 自动经验提取 / Auto Lesson Extractor ─────────────────────────────────────


def generate_auto_lessons(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从累积观察中检测模式并提取经验 / Detect patterns in observations and extract lessons.

    策略 / Strategy:
    - 统计每个 category 的观察次数，如果同一类别出现 3+ 次 → 提议生成经验
    - Count observations per category; if same category appears 3+ times → propose a lesson

    经验是推断，不是事实（原则 8）。
    Lessons are inferences, not facts (Principle 8).
    """
    packets: list[dict[str, Any]] = []
    ls_records = snapshot.get("learning_state", {}).get("records", {})
    observations = ls_records.get("observations", [])
    existing_lessons = ls_records.get("lessons", [])

    if len(observations) < 3:
        return packets

    # 按 category 分组计数 / Group by category
    cat_counts: dict[str, int] = {}
    cat_examples: dict[str, list[str]] = {}
    for obs in observations:
        cat = obs.get("category", "other")
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        titles = cat_examples.setdefault(cat, [])
        if len(titles) < 3:
            titles.append(obs.get("title", "无标题"))

    # 已有经验的类别（避免重复提议）/ Categories with existing lessons (avoid duplicates)
    existing_lesson_cats = {l.get("category", "") for l in existing_lessons}

    # 类别名称映射（中文显示）/ Category name map for Chinese display
    cat_names = {
        "market": "市场", "execution": "执行", "cost": "成本",
        "system": "系统", "strategy": "策略", "other": "其他",
    }
    lesson_cat_map = {
        "market": "market_pattern", "execution": "execution_quality",
        "cost": "cost_insight", "system": "system", "strategy": "strategy",
        "other": "other",
    }

    for cat, count in cat_counts.items():
        if count < 3:
            continue
        lesson_cat = lesson_cat_map.get(cat, "other")
        if lesson_cat in existing_lesson_cats:
            continue

        cat_cn = cat_names.get(cat, cat)
        examples_str = "；".join(cat_examples.get(cat, []))
        title = f"「{cat_cn}」类别已有 {count} 条观察，建议总结经验"
        detail = f"在「{cat_cn}」类别下已积累 {count} 条观察记录。代表性观察：{examples_str}。建议归纳为一条可复用的经验。"

        packets.append(_build_review_packet(
            packet_type="auto_lesson",
            what_happened=f"「{cat_cn}」类别已有 {count} 条观察，可能存在规律 / {count} observations in '{cat}' category suggest a pattern",
            why_it_matters=(
                f"在同一个类别下反复出现的观察，通常意味着存在规律。"
                f"如果把这些发现总结为经验，系统未来可以更快识别类似情况。"
                f" / Repeated observations in same category often indicate a pattern worth remembering."
            ),
            confidence_level="inference",
            target_collection="lessons",
            record_data={
                "title": title,
                "detail": detail,
                "category": lesson_cat,
                "confidence_level": "inference",
                "actionable": True,
                "tags": ["auto_generated", f"from_{cat}_observations"],
            },
            ai_recommended=True,
            ai_tier="light",
            ai_question=_build_ai_question_for_lesson(title, detail, count),
            ai_context={"category": cat, "observation_count": count},
            tags=["pattern_detection", "auto_generated"],
        ))

    return packets


# ── 自动假设提议 / Auto Hypothesis Proposer ──────────────────────────────────


def generate_auto_hypotheses(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    """
    从累积经验中提议假设 / Propose hypotheses from accumulated lessons.

    策略 / Strategy:
    - 有 actionable=True 的 lesson 但无关联的 hypothesis → 建议提出假设
    - If a lesson is actionable but has no linked hypothesis → propose one

    假设的置信度永远是 "hypothesis"（原则 8）。
    Hypothesis confidence is always "hypothesis" (Principle 8).
    """
    packets: list[dict[str, Any]] = []
    ls_records = snapshot.get("learning_state", {}).get("records", {})
    lessons = ls_records.get("lessons", [])
    hypotheses = ls_records.get("hypotheses", [])

    if not lessons:
        return packets

    # 已被假设引用的 lesson ID / Lesson IDs already referenced by hypotheses
    referenced_lesson_ids: set[str] = set()
    for hyp in hypotheses:
        for lid in hyp.get("supporting_lesson_ids", []):
            referenced_lesson_ids.add(lid)

    for lesson in lessons:
        lesson_id = lesson.get("lesson_id", "")
        if not lesson.get("actionable", False):
            continue
        if lesson_id in referenced_lesson_ids:
            continue

        title = lesson.get("title", "无标题")
        detail = lesson.get("detail", "")
        cat = lesson.get("category", "other")

        hyp_title = f"基于经验「{title}」的可检验假设"
        prediction = f"如果经验「{title}」成立，则在类似条件下应该能观察到相同规律"

        packets.append(_build_review_packet(
            packet_type="auto_hypothesis",
            what_happened=f"有一条可操作的经验尚未形成假设：{title} / Actionable lesson without hypothesis: {title}",
            why_it_matters=(
                "可操作的经验如果不转化为假设，就无法被系统性地验证。"
                "提出假设后可以设计实验来确认经验是否可靠。"
                " / Actionable lessons need hypotheses to be systematically validated."
            ),
            confidence_level="hypothesis",
            target_collection="hypotheses",
            record_data={
                "title": hyp_title,
                "description": f"基于经验记录：{detail}",
                "testable_prediction": prediction,
                "confidence_level": "hypothesis",
                "supporting_lesson_ids": [lesson_id],
                "tags": ["auto_generated", f"from_lesson_{lesson_id}"],
            },
            ai_recommended=True,
            ai_tier="standard",
            ai_question=_build_ai_question_for_hypothesis(hyp_title, prediction),
            ai_context={"source_lesson_id": lesson_id, "lesson_category": cat},
            tags=["hypothesis_proposal", "auto_generated"],
        ))

    return packets


# ── 自动学习管线写逻辑 / Auto Learning Pipeline Write Logic ──────────────────


def apply_auto_generate(
    envelope: RequestEnvelope, actor: AuthenticatedActor, scan_type: str
) -> tuple[dict[str, Any], str]:
    """
    触发自动扫描并生成审核包 / Trigger auto-scan and generate review packets.

    scan_type: "observations" | "lessons" | "hypotheses"

    生成的审核包追加到 learning_state.records.review_queue，
    通过 _content_hash 去重（跳过已存在的相同内容）。
    Generated packets are appended to review_queue with deduplication via _content_hash.

    安全保证 / Safety: 只生成审核包，不创建正式记录（原则 7）。
    Only generates review packets, never creates actual records (Principle 7).
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    if scan_type not in AUTO_SCAN_TYPES:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_scan_type"]})

    # 根据扫描类型调用对应的生成器 / Call corresponding generator by scan type
    if scan_type == "observations":
        new_packets = generate_auto_observations(snapshot)
    elif scan_type == "lessons":
        new_packets = generate_auto_lessons(snapshot)
    else:
        new_packets = generate_auto_hypotheses(snapshot)

    ts = now_ms()
    generated_ids: list[str] = []
    skipped = 0

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal generated_ids, skipped
        ls = state["learning_state"]
        queue = ls.setdefault("records", {}).setdefault("review_queue", [])
        pipeline = ls.setdefault("auto_pipeline", {})

        # 去重：检查已有审核包的 _content_hash / Dedup: check existing _content_hash
        existing_hashes = {
            p.get("_content_hash") for p in queue
            if p.get("status") in {"pending_review", "ai_consulted"}
        }

        for pkt in new_packets:
            if pkt.get("_content_hash") in existing_hashes:
                skipped += 1
                continue
            queue.append(pkt)
            generated_ids.append(pkt["packet_id"])
            existing_hashes.add(pkt.get("_content_hash"))

        # 更新管线摘要 / Update pipeline summary
        ts_key = f"last_{scan_type[:-1] if scan_type.endswith('s') else scan_type}_scan_ts_ms"
        if scan_type == "observations":
            ts_key = "last_observation_scan_ts_ms"
        elif scan_type == "lessons":
            ts_key = "last_lesson_scan_ts_ms"
        else:
            ts_key = "last_hypothesis_scan_ts_ms"
        pipeline[ts_key] = ts
        pipeline["total_packets_generated"] = pipeline.get("total_packets_generated", 0) + len(generated_ids)

        audit_ref = _write_audit_fields(
            state, action_type=f"auto_scan_{scan_type}", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "packets_generated": len(generated_ids),
                "packet_ids": generated_ids,
                "scan_type": scan_type,
                "skipped_duplicates": skipped,
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
            "packets_generated": len(generated_ids),
            "packet_ids": generated_ids,
            "scan_type": scan_type,
            "skipped_duplicates": skipped,
        },
        "snapshot": final_state,
    }, "success"


def apply_review_decision(
    envelope: RequestEnvelope, actor: AuthenticatedActor, packet_id: str
) -> tuple[dict[str, Any], str]:
    """
    Operator 对审核包做出决定 / Operator decides on a review packet.

    payload:
    - decision: str   "approve" | "reject" | "defer" | "ask_ai"
    - reason: str     决定理由（可选）/ Decision reason (optional)

    批准 (approve): 从 candidate_record 提取数据，在对应 collection 创建真实记录
    拒绝 (reject): 标记为已拒绝，不创建记录
    搁置 (defer): 标记为已搁置，保留在队列中
    询问 AI (ask_ai): 标记为 AI 已咨询，返回预生成问题（实际 AI 调用为 stub）

    Approve: creates real record from candidate_record
    Reject: marks as rejected, no record created
    Defer: marks as deferred, stays in queue
    Ask AI: marks as ai_consulted, returns pre-built question (actual AI call is stub)
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)
    replay = _check_idempotency(snapshot, envelope)
    if replay is not None:
        replay["snapshot"] = snapshot
        return replay, "replayed"
    _assert_revision(snapshot, envelope)

    p = envelope.payload
    decision = str(p.get("decision", "")).strip()
    reason = str(p.get("reason", "")).strip()
    if decision not in REVIEW_DECISION_ACTIONS:
        raise HTTPException(status_code=400, detail={"reason_codes": ["invalid_review_decision"]})

    # 查找审核包 / Find the review packet
    queue = snapshot.get("learning_state", {}).get("records", {}).get("review_queue", [])
    target_idx = None
    for i, pkt in enumerate(queue):
        if pkt.get("packet_id") == packet_id:
            target_idx = i
            break
    if target_idx is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["review_packet_not_found"]})

    pkt = queue[target_idx]
    if pkt["status"] not in {"pending_review", "ai_consulted", "deferred"}:
        raise HTTPException(status_code=400, detail={"reason_codes": ["review_packet_already_decided"]})

    ts = now_ms()
    created_record_id: str | None = None

    def mutator(state: dict[str, Any]) -> dict[str, Any]:
        nonlocal created_record_id
        rq = state["learning_state"]["records"]["review_queue"]
        packet = rq[target_idx]

        # 记录决定 / Record decision
        packet["decided_by"] = actor.actor_id
        packet["decided_ts_ms"] = ts
        packet["decision"] = decision
        packet["decision_reason"] = reason or None

        pipeline = state["learning_state"].setdefault("auto_pipeline", {})

        if decision == "approve":
            packet["status"] = "approved"
            pipeline["total_packets_approved"] = pipeline.get("total_packets_approved", 0) + 1

            # 从 candidate_record 创建真实记录 / Create real record from candidate_record
            candidate = packet.get("candidate_record", {})
            target_col = candidate.get("target_collection", "observations")
            rec_data = candidate.get("record_data", {})

            if target_col == "observations":
                record_id = f"obs:{ts}"
                record = {
                    "observation_id": record_id,
                    "recorded_ts_ms": ts,
                    "recorded_by": actor.actor_id,
                    "source": "system_auto_approved",
                    "category": rec_data.get("category", "other"),
                    "confidence_level": rec_data.get("confidence_level", "inference"),
                    "title": rec_data.get("title", ""),
                    "detail": rec_data.get("detail", ""),
                    "related_hypothesis_id": rec_data.get("related_hypothesis_id"),
                    "tags": rec_data.get("tags", []),
                }
                state["learning_state"]["records"].setdefault("observations", []).append(record)
                state["learning_state"]["observation_summary"]["last_observation_ts_ms"] = ts

            elif target_col == "lessons":
                record_id = f"lesson:{ts}"
                record = {
                    "lesson_id": record_id,
                    "recorded_ts_ms": ts,
                    "recorded_by": actor.actor_id,
                    "source_observation_ids": rec_data.get("source_observation_ids", []),
                    "confidence_level": rec_data.get("confidence_level", "inference"),
                    "category": rec_data.get("category", "other"),
                    "title": rec_data.get("title", ""),
                    "detail": rec_data.get("detail", ""),
                    "actionable": rec_data.get("actionable", False),
                    "related_hypothesis_ids": rec_data.get("related_hypothesis_ids", []),
                    "tags": rec_data.get("tags", []),
                }
                state["learning_state"]["records"].setdefault("lessons", []).append(record)
                state["learning_state"]["memory"]["last_memory_update_ts_ms"] = ts

            elif target_col == "hypotheses":
                record_id = f"hyp:{ts}"
                record = {
                    "hypothesis_id": record_id,
                    "recorded_ts_ms": ts,
                    "recorded_by": actor.actor_id,
                    "status": "proposed",
                    "confidence_level": "hypothesis",  # 原则 8 强制 / Principle 8 enforced
                    "title": rec_data.get("title", ""),
                    "description": rec_data.get("description", ""),
                    "testable_prediction": rec_data.get("testable_prediction", ""),
                    "supporting_observation_ids": rec_data.get("supporting_observation_ids", []),
                    "supporting_lesson_ids": rec_data.get("supporting_lesson_ids", []),
                    "related_experiment_id": None,
                    "operator_verdict": None,
                    "operator_verdict_ts_ms": None,
                    "operator_verdict_reason": None,
                    "tags": rec_data.get("tags", []),
                }
                state["learning_state"]["records"].setdefault("hypotheses", []).append(record)
                state["learning_state"]["hypotheses"]["last_hypothesis_ts_ms"] = ts

            else:
                record_id = f"rec:{ts}"

            created_record_id = record_id

        elif decision == "reject":
            packet["status"] = "rejected"
            pipeline["total_packets_rejected"] = pipeline.get("total_packets_rejected", 0) + 1

        elif decision == "defer":
            packet["status"] = "deferred"

        elif decision == "ask_ai":
            packet["status"] = "ai_consulted"
            # AI 调用为 stub / AI call is a stub
            packet["ai_consultation_result"] = (
                "[AI 咨询功能待接入 H 链 / AI consultation pending H-chain integration] "
                "当前为占位回复。实际接入后，系统将通过 H1-H5 治理链调用 AI 并在此显示回复。"
            )
            packet["ai_consultation_cost_usd"] = 0.0

        audit_ref = _write_audit_fields(
            state, action_type=f"review_decision_{decision}", operator_id=actor.actor_id,
            request_id=envelope.request_id, result="success", reason_codes=[],
            is_control_action=False,
        )
        _bump_revision(state)
        compiled = STORE.write(state)
        response = {
            "audit_ref": audit_ref,
            "data": {
                "packet_id": packet_id,
                "decision": decision,
                "new_status": packet["status"],
                "record_created": decision == "approve",
                "created_record_id": created_record_id,
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
            "packet_id": packet_id,
            "decision": decision,
            "new_status": "approved" if decision == "approve" else (
                "rejected" if decision == "reject" else (
                    "deferred" if decision == "defer" else "ai_consulted"
                )
            ),
            "record_created": decision == "approve",
            "created_record_id": created_record_id,
        },
        "snapshot": final_state,
    }, "success"


def apply_ai_consultation(
    envelope: RequestEnvelope, actor: AuthenticatedActor, packet_id: str
) -> tuple[dict[str, Any], str]:
    """
    执行 AI 咨询（当前为 stub）/ Execute AI consultation (currently a stub).

    未来接入 H1-H5 治理链后，此函数将：
    1. 调用 H1 thought_gate 判断是否需要 AI
    2. 通过 H2 query_budget 验证预算
    3. 通过 H3 model_router 选择模型
    4. 通过 H4 compute_governor 执行约束
    5. 记录成本到 H5

    当前返回 stub 响应，包含预生成的问题和占位回复。
    Currently returns stub response with pre-built question and placeholder reply.
    """
    require_scope(actor, "learning:manage")
    snapshot, _ = get_latest_snapshot()
    verify_operator_identity(envelope, actor)

    queue = snapshot.get("learning_state", {}).get("records", {}).get("review_queue", [])
    target_pkt = None
    for pkt in queue:
        if pkt.get("packet_id") == packet_id:
            target_pkt = pkt
            break
    if target_pkt is None:
        raise HTTPException(status_code=404, detail={"reason_codes": ["review_packet_not_found"]})

    ai_info = target_pkt.get("ai_consultation", {})
    question = ai_info.get("pre_built_question", "无预生成问题")
    tier = ai_info.get("recommended_tier", "light")

    return {
        "audit_ref": None,
        "data": {
            "packet_id": packet_id,
            "ai_tier": tier,
            "question_sent": question,
            "ai_response": (
                "[AI 咨询功能待接入 H 链 / AI consultation pending H-chain integration] "
                "当前为占位回复。系统已准备好通过 H1(thought_gate) → H2(query_budget) → "
                "H3(model_router) → H4(compute_governor) → H5(cost_log) 的完整治理链调用 AI。"
                "接入后将在此显示 AI 的真实回复。"
            ),
            "cost_usd": 0.0,
            "consultation_status": "stub_pending_h_chain_integration",
        },
        "snapshot": snapshot,
    }, "success"


# ── 审核队列只读构建器 / Review Queue Read-Only Builder ──────────────────────


def build_review_queue(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建审核队列视图 / Build review queue view.

    返回待审核的审核包（pending_review + ai_consulted + deferred）
    和最近已决定的审核包（approved + rejected）。
    Returns pending packets and recently decided packets.
    """
    ls = snapshot.get("learning_state", {})
    queue = ls.get("records", {}).get("review_queue", [])
    pipeline = ls.get("auto_pipeline", {})

    pending = [p for p in queue if p.get("status") in {"pending_review", "ai_consulted", "deferred"}]
    decided = [p for p in queue if p.get("status") in {"approved", "rejected"}]

    # 最新在前 / Newest first
    pending.sort(key=lambda x: x.get("created_ts_ms", 0), reverse=True)
    decided.sort(key=lambda x: x.get("decided_ts_ms", 0), reverse=True)

    return {
        "pending_packets": pending,
        "recent_decided": decided[-_MAX_RECENT_ENTRIES:],
        "pending_count": len(pending),
        "total_count": len(queue),
        "auto_pipeline_summary": copy.deepcopy(pipeline),
    }


# ── L 章只读查询构建器 / L-Chapter Read-Only Query Builders ────────────────────


def build_learning_feed(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建完整学习观察流 / Build complete learning observation feed.

    返回最近 N 条观察和经验教训，以及摘要统计。
    Returns the last N observations and lessons, plus summary statistics.
    """
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})

    observations = ls_records.get("observations", [])
    lessons = ls_records.get("lessons", [])

    # 取最近 N 条，按最新在前排列 / Take last N, newest first
    obs_recent = list(reversed(observations[-_MAX_RECENT_ENTRIES:]))
    les_recent = list(reversed(lessons[-_MAX_RECENT_ENTRIES:]))

    return {
        "observations_recent": obs_recent,
        "lessons_recent": les_recent,
        "observation_summary": copy.deepcopy(ls.get("observation_summary", {})),
        "memory_state": copy.deepcopy(ls.get("memory", {})),
        "totals": {
            "total_observations": len(observations),
            "total_lessons": len(lessons),
            "total_hypotheses": len(ls_records.get("hypotheses", [])),
            "total_experiments": len(ls_records.get("experiments", [])),
            "total_manual_notes": len(ls_records.get("manual_notes", [])),
        },
    }


def build_learning_experiments(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建实验队列完整视图 / Build complete experiment queue view.

    包含所有实验、关联假设和待审批统计。
    Includes all experiments, linked hypotheses, and pending approval statistics.
    """
    ls = snapshot.get("learning_state", {})
    ls_records = ls.get("records", {})

    experiments = ls_records.get("experiments", [])
    hypotheses = ls_records.get("hypotheses", [])

    # 统计待审批数 / Count pending approvals
    pending = sum(1 for e in experiments if e.get("status") == "pending_approval")

    return {
        "experiments": list(reversed(experiments[-_MAX_RECENT_ENTRIES:])),
        "hypotheses": list(reversed(hypotheses[-_MAX_RECENT_ENTRIES:])),
        "pending_approval_count": pending,
        "approval_required": ls.get("experiments", {}).get("approval_required", True),
    }


def build_net_pnl_dashboard(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    构建含所有成本分解的净 PnL 仪表盘 / Build Net PnL dashboard with full cost breakdown.

    整合：每日经营指标 + 成本分类 + 周期快照趋势 + 最近录入条目。
    Integrates: daily business metrics + cost categories + period snapshot trends + recent entries.
    """
    daily = copy.deepcopy(snapshot["business_metrics"]["daily"])
    records = snapshot.get("records", {})
    bm = snapshot.get("business_metrics", {})

    cost_entries = records.get("cost_entries", [])
    pnl_entries = records.get("pnl_entries", [])
    period_snapshots = bm.get("period_snapshots", [])

    # 成本分解 / Cost breakdown
    cost_breakdown: dict[str, float] = {}
    for entry in cost_entries:
        cat = str(entry.get("category", "manual"))
        cost_breakdown[cat] = round(cost_breakdown.get(cat, 0.0) + float(entry.get("amount", 0.0)), 8)

    # 趋势数据：从周期快照提取 net_operating_pnl 序列
    # Trend data: extract net_operating_pnl series from period snapshots
    net_pnl_trend = [
        {
            "period_label": ps.get("period_label", ""),
            "net_operating_pnl": ps.get("net_operating_pnl", 0.0),
            "gross_pnl": ps.get("gross_pnl", 0.0),
            "total_cost": ps.get("total_cost", 0.0),
            "snapshot_ts_ms": ps.get("snapshot_ts_ms", 0),
        }
        for ps in period_snapshots
    ]

    return {
        "daily": daily,
        "cost_breakdown": cost_breakdown,
        "period_snapshots": list(reversed(period_snapshots[-_MAX_RECENT_ENTRIES:])),
        "pnl_entries_recent": list(reversed(pnl_entries[-_MAX_RECENT_ENTRIES:])),
        "cost_entries_recent": list(reversed(cost_entries[-_MAX_RECENT_ENTRIES:])),
        "net_pnl_trend": net_pnl_trend,
        "entry_totals": {
            "total_cost_entries": len(cost_entries),
            "total_pnl_entries": len(pnl_entries),
            "total_period_snapshots": len(period_snapshots),
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


# ═══════════════════════════════════════════════════════════════════════════════
# L 章路由 / L-Chapter Routes
#
# 三类端点：
# 1. GET 查询端点：观察流 / 实验队列 / 净 PnL 仪表盘
# 2. POST 录入端点：观察 / 经验 / 假设 / 实验 / 周期快照
# 3. POST 管理端点：假设审批 / 实验审批 / 实验完成
#
# Three categories of endpoints:
# 1. GET queries: observation feed / experiment queue / net PnL dashboard
# 2. POST inputs: observation / lesson / hypothesis / experiment / period snapshot
# 3. POST management: hypothesis verdict / experiment approval / experiment completion
# ═══════════════════════════════════════════════════════════════════════════════


@app.get(f"{settings.api_prefix}/learning/feed", response_model=ResponseEnvelope[LearningFeedData])
def get_learning_feed(actor=Depends(current_actor)) -> ResponseEnvelope[LearningFeedData]:
    """
    学习观察流 / Learning observation feed.

    返回最近的观察和经验教训列表，以及摘要统计。
    Returns recent observations and lessons, plus summary statistics.
    """
    snapshot, _ = get_latest_snapshot()
    feed = build_learning_feed(snapshot)
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=LearningFeedData(**feed))


@app.get(f"{settings.api_prefix}/learning/experiments", response_model=ResponseEnvelope[LearningExperimentsData])
def get_learning_experiments_list(actor=Depends(current_actor)) -> ResponseEnvelope[LearningExperimentsData]:
    """
    实验队列完整视图 / Complete experiment queue view.

    包含所有实验和关联假设，以及待审批数量。
    Includes all experiments and linked hypotheses, plus pending approval count.
    """
    snapshot, _ = get_latest_snapshot()
    data = build_learning_experiments(snapshot)
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=LearningExperimentsData(**data))


@app.get(f"{settings.api_prefix}/learning/net-pnl", response_model=ResponseEnvelope[NetPnLDashboardData])
def get_net_pnl_dashboard(actor=Depends(current_actor)) -> ResponseEnvelope[NetPnLDashboardData]:
    """
    含所有成本分解的净 PnL 仪表盘 / Net PnL dashboard with full cost breakdown.

    整合每日 PnL、成本分类分解、趋势和最近录入条目。
    Integrates daily PnL, cost category breakdown, trends, and recent entries.
    """
    snapshot, _ = get_latest_snapshot()
    dashboard = build_net_pnl_dashboard(snapshot)
    return envelope_response(snapshot=snapshot, request_id=None, action_result="success", data=NetPnLDashboardData(**dashboard))


# ── L 章录入路由 / L-Chapter Input Routes ─────────────────────────────────────


@app.post(f"{settings.api_prefix}/input/observation", response_model=ResponseEnvelope[ObservationAcceptedData])
def post_input_observation(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[ObservationAcceptedData]:
    """
    录入观察记录 / Record an observation to the observation feed.

    payload 字段 / payload fields:
    - title: str            观察标题（必填）/ Observation title (required)
    - detail: str           观察详情（必填）/ Observation detail (required)
    - category: str         类别（必填）/ Category (required): market/execution/cost/system/strategy/other
    - confidence_level: str 置信度（必填）/ Confidence (required): fact/inference/hypothesis
    - related_hypothesis_id: str  关联假设 ID（可选）/ Related hypothesis ID (optional)
    - tags: list[str]       标签（可选）/ Tags (optional)
    """
    result, action_result = apply_learning_observation(envelope, actor)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=ObservationAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(f"{settings.api_prefix}/input/lesson", response_model=ResponseEnvelope[LessonAcceptedData])
def post_input_lesson(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[LessonAcceptedData]:
    """
    录入经验教训 / Record a lesson to the lessons memory.

    payload 字段 / payload fields:
    - title: str            经验标题（必填）/ Lesson title (required)
    - detail: str           经验详情（必填）/ Lesson detail (required)
    - category: str         类别（必填）/ Category (required): market_pattern/cost_insight/execution_quality/strategy/system/other
    - confidence_level: str 置信度（必填）/ Confidence (required): fact/inference/hypothesis
    """
    result, action_result = apply_learning_lesson(envelope, actor)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=LessonAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(f"{settings.api_prefix}/input/hypothesis", response_model=ResponseEnvelope[HypothesisAcceptedData])
def post_input_hypothesis(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[HypothesisAcceptedData]:
    """
    提出假设 / Propose a hypothesis.

    原则 8：confidence_level 自动设为 "hypothesis"。
    Principle 8: confidence_level is automatically set to "hypothesis".

    payload 字段 / payload fields:
    - title: str                假设标题（必填）/ Title (required)
    - description: str          假设描述（必填）/ Description (required)
    - testable_prediction: str  可检验预测（必填）/ Testable prediction (required)
    """
    result, action_result = apply_learning_hypothesis(envelope, actor)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=HypothesisAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(f"{settings.api_prefix}/input/experiment", response_model=ResponseEnvelope[ExperimentAcceptedData])
def post_input_experiment(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[ExperimentAcceptedData]:
    """
    提出实验 / Propose an experiment to validate a hypothesis.

    payload 字段 / payload fields:
    - hypothesis_id: str    关联假设 ID（必填）/ Linked hypothesis ID (required)
    - title: str            实验标题（必填）/ Title (required)
    - description: str      实验描述（必填）/ Description (required)
    - method: str           实验方法（必填）/ Method (required)
    - success_criteria: str 成功标准（必填）/ Success criteria (required)
    """
    result, action_result = apply_learning_experiment(envelope, actor)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=ExperimentAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


# ── L 章管理路由 / L-Chapter Management Routes ───────────────────────────────


@app.post(
    f"{settings.api_prefix}/learning/hypothesis/{{hypothesis_id}}/verdict",
    response_model=ResponseEnvelope[HypothesisVerdictData],
)
def post_hypothesis_verdict(
    hypothesis_id: str, envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[HypothesisVerdictData]:
    """
    Operator 审批假设 / Operator renders verdict on a hypothesis.

    payload 字段 / payload fields:
    - verdict: str  判定（必填）/ Verdict (required): approved / rejected / archived
    - reason: str   理由（可选）/ Reason (optional)
    """
    result, action_result = apply_hypothesis_verdict(envelope, actor, hypothesis_id)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=HypothesisVerdictData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(
    f"{settings.api_prefix}/learning/experiment/{{experiment_id}}/approve",
    response_model=ResponseEnvelope[ExperimentApprovalData],
)
def post_experiment_approval(
    experiment_id: str, envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[ExperimentApprovalData]:
    """
    Operator 审批实验 / Operator approves or rejects an experiment.

    payload 字段 / payload fields:
    - action: str   审批动作（必填）/ Action (required): approved / rejected
    - reason: str   理由（可选）/ Reason (optional)
    """
    result, action_result = apply_experiment_approval(envelope, actor, experiment_id)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=ExperimentApprovalData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(
    f"{settings.api_prefix}/learning/experiment/{{experiment_id}}/complete",
    response_model=ResponseEnvelope[ExperimentCompletionData],
)
def post_experiment_completion(
    experiment_id: str, envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[ExperimentCompletionData]:
    """
    标记实验完成 / Mark an experiment as completed.

    payload 字段 / payload fields:
    - result_summary: str           实验结论（必填）/ Conclusion (required)
    - result_confidence_level: str  结论置信度（必填）/ Confidence (required): fact/inference/hypothesis
    """
    result, action_result = apply_experiment_completion(envelope, actor, experiment_id)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=ExperimentCompletionData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(f"{settings.api_prefix}/input/pnl-period-snapshot", response_model=ResponseEnvelope[InputAcceptedData])
def post_pnl_period_snapshot(envelope: RequestEnvelope, actor=Depends(current_actor)) -> ResponseEnvelope[InputAcceptedData]:
    """
    保存当前经营指标为周期快照 / Save current business metrics as a period snapshot.

    payload 字段 / payload fields:
    - period_label: str  周期标签（必填）/ Period label (required), e.g. "2026-03-26"
    """
    result, action_result = apply_pnl_period_snapshot(envelope, actor)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=InputAcceptedData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


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


# ═══════════════════════════════════════════════════════════════════════════════
# L 章自动学习管线路由 / L-Chapter Auto Learning Pipeline Routes
#
# 三类端点：
# 1. POST 扫描端点：触发自动观察/经验/假设生成
# 2. GET 审核队列：获取待审核和已审核的审核包
# 3. POST 审核决策：对审核包做出批准/拒绝/搁置/询问AI 决定
#
# Three categories:
# 1. POST scan: trigger auto observation/lesson/hypothesis generation
# 2. GET review queue: pending and decided review packets
# 3. POST review decision: approve/reject/defer/ask-ai on review packets
# ═══════════════════════════════════════════════════════════════════════════════


@app.post(
    f"{settings.api_prefix}/learning/auto/scan-observations",
    response_model=ResponseEnvelope[AutoGenerationResultData],
)
def post_auto_scan_observations(
    envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[AutoGenerationResultData]:
    """
    扫描系统状态并自动生成观察审核包 / Scan system state and auto-generate observation review packets.

    检查健康门控、AI 成本、数据新鲜度、PnL 变化等，
    将发现打包为简单易懂的审核包供 Operator 审批。
    """
    result, action_result = apply_auto_generate(envelope, actor, "observations")
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=AutoGenerationResultData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(
    f"{settings.api_prefix}/learning/auto/scan-lessons",
    response_model=ResponseEnvelope[AutoGenerationResultData],
)
def post_auto_scan_lessons(
    envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[AutoGenerationResultData]:
    """
    从累积观察中自动提取经验审核包 / Auto-extract lesson review packets from accumulated observations.

    检测同一类别是否出现多次观察，如果有规律性，
    建议总结为经验（需要 Operator 审批确认）。
    """
    result, action_result = apply_auto_generate(envelope, actor, "lessons")
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=AutoGenerationResultData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(
    f"{settings.api_prefix}/learning/auto/scan-hypotheses",
    response_model=ResponseEnvelope[AutoGenerationResultData],
)
def post_auto_scan_hypotheses(
    envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[AutoGenerationResultData]:
    """
    从累积经验中自动提议假设审核包 / Auto-propose hypothesis review packets from accumulated lessons.

    对于可操作但尚未关联假设的经验，自动生成假设提议。
    """
    result, action_result = apply_auto_generate(envelope, actor, "hypotheses")
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=AutoGenerationResultData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.get(
    f"{settings.api_prefix}/learning/review-queue",
    response_model=ResponseEnvelope[ReviewQueueData],
)
def get_review_queue_view(actor=Depends(current_actor)) -> ResponseEnvelope[ReviewQueueData]:
    """
    获取审核队列 / Get review queue.

    返回待审核的审核包和最近已决定的审核包，以及管线摘要。
    Returns pending and recently decided review packets, plus pipeline summary.
    """
    snapshot, _ = get_latest_snapshot()
    data = build_review_queue(snapshot)
    return envelope_response(
        snapshot=snapshot, request_id=None, action_result="success",
        data=ReviewQueueData(**data),
    )


@app.post(
    f"{settings.api_prefix}/learning/review/{{packet_id}}/decide",
    response_model=ResponseEnvelope[ReviewDecisionData],
)
def post_review_decide(
    packet_id: str, envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[ReviewDecisionData]:
    """
    对审核包做出决定 / Decide on a review packet.

    payload 字段 / payload fields:
    - decision: str   "approve" | "reject" | "defer" | "ask_ai"
    - reason: str     决定理由（可选）/ Decision reason (optional)

    批准后系统自动创建对应的正式记录。
    Upon approval, system auto-creates the corresponding record.
    """
    result, action_result = apply_review_decision(envelope, actor, packet_id)
    return envelope_response(
        snapshot=result["snapshot"], request_id=envelope.request_id, action_result=action_result,
        data=ReviewDecisionData(**result["data"]), audit_ref=result["audit_ref"],
        reason_codes=["replayed_request"] if action_result == "replayed" else [],
    )


@app.post(
    f"{settings.api_prefix}/learning/review/{{packet_id}}/ai-consult",
    response_model=ResponseEnvelope[AIConsultationResultData],
)
def post_review_ai_consult(
    packet_id: str, envelope: RequestEnvelope, actor=Depends(current_actor)
) -> ResponseEnvelope[AIConsultationResultData]:
    """
    对审核包执行 AI 咨询（当前 stub）/ AI consultation on review packet (currently stub).

    当前返回预生成的问题和占位回复。
    未来接入 H1-H5 治理链后将执行真实 AI 调用。
    """
    result, action_result = apply_ai_consultation(envelope, actor, packet_id)
    return envelope_response(
        snapshot=result["snapshot"], request_id=None, action_result=action_result,
        data=AIConsultationResultData(**result["data"]),
    )

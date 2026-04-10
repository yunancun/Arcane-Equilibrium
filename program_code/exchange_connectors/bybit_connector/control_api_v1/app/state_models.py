"""
MODULE_NOTE (中文):
  狀態模型定義模塊。包含 Control API 所有 Pydantic 請求/響應模型和類型別名。
  從 main_legacy.py 拆分而來，純數據定義，零業務邏輯。

MODULE_NOTE (English):
  State model definitions. Contains all Pydantic request/response models and type aliases
  for the Control API. Extracted from main_legacy.py.
  Pure data definitions, zero business logic.
"""

from __future__ import annotations

from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════════════════════
# Type Aliases / 類型別名
# ═══════════════════════════════════════════════════════════════════════════════

ActionResult = Literal["success", "failed", "blocked", "replayed"]
ConnectionState = Literal["ready", "degraded", "down", "unknown"]
RuntimeConnectionState = Literal["healthy", "degraded", "down", "unknown"]
CompletenessState = Literal["complete", "partial", "missing", "unknown"]
DemoState = Literal["closed", "armed_but_closed", "demo_enabled", "relocked"]
GateState = Literal["not_evaluated", "passed", "failed", "blocked"]
EffectiveRiskEnvelopeState = Literal["reserved", "configured", "blocking"]

T = TypeVar("T")


class RequestEnvelope(BaseModel):
    request_id: str = Field(max_length=200)
    idempotency_key: str = Field(max_length=200)
    operator_id: str = Field(max_length=100)
    reason: str = Field(max_length=500)
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
    # DEPRECATED notice field — callers should migrate to the active AI pipeline endpoint.
    # 廢棄通知字段 — 調用方應遷移至現有 AI 管線端點。
    deprecation_notice: str | None = None

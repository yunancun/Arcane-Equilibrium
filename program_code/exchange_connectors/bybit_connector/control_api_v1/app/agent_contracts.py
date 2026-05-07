"""Typed Agent Decision Spine contracts for Python agents.

MAG-033 mirrors the Rust `agent_spine::contracts` payloads so Strategist,
Guardian, Executor, and Analyst can exchange typed objects through the durable
spine store without free-text routing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


AgentSpineMode = Literal["disabled", "shadow", "canary", "primary"]

DecisionObjectType = Literal[
    "strategy_signal",
    "strategist_decision",
    "guardian_verdict",
    "execution_plan",
    "execution_report",
    "analyst_insight",
]

DecisionEdgeType = Literal[
    "evidence_for",
    "signal_for",
    "reviewed_by",
    "modified_by",
    "planned_by",
    "leased_by",
    "executed_by",
    "analyzed_by",
    "protective_bypass_for",
]

StrategySignalDirection = Literal[
    "long",
    "short",
    "close_long",
    "close_short",
    "neutral",
]

DecisionAction = Literal["open", "hold", "reduce", "close", "no_action"]

CanonicalStrategy = Literal[
    "ma_crossover",
    "grid_trading",
    "bb_reversion",
    "bb_breakout",
    "funding_arb",
]


class _SpineModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StrategySignal(_SpineModel):
    schema_version: str = "agent_spine.strategy_signal.v1"
    signal_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str
    direction: StrategySignalDirection
    raw_signal_strength: float
    expected_edge_bps: float | None = None
    expected_cost_bps: float | None = None
    confidence: float
    regime: str | None = None
    scanner_candidate_id: str | None = None
    scanner_decay_id: str | None = None
    context_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    invalidation: str | None = None
    order_type: str | None = None
    limit_price: float | None = None
    time_in_force: str | None = None
    maker_timeout_ms: int | None = None


class StrategistDecision(_SpineModel):
    schema_version: str = "agent_spine.strategist_decision.v1"
    decision_id: str
    signal_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str
    direction: StrategySignalDirection
    confidence: float
    decision_action: DecisionAction = "open"
    selected_strategy: CanonicalStrategy | None = None
    selected_candidate_id: str | None = None
    candidate_scores: list[dict[str, Any]] = Field(default_factory=list)
    expected_net_edge_bps: float | None = None
    portfolio_impact: dict[str, Any] = Field(default_factory=dict)
    thesis: str | None = None
    invalidation: str | None = None
    fact_refs: list[str] = Field(default_factory=list)
    inference_refs: list[str] = Field(default_factory=list)
    hypothesis_refs: list[str] = Field(default_factory=list)
    proposed_qty: float | None = None
    proposed_price: float | None = None
    rationale: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardianVerdict(_SpineModel):
    schema_version: str = "agent_spine.guardian_verdict.v1"
    verdict_id: str
    decision_id: str
    verdict_version: int
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str
    allow: bool
    risk_level: str
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(_SpineModel):
    schema_version: str = "agent_spine.execution_plan.v1"
    order_plan_id: str
    decision_id: str
    verdict_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str
    direction: StrategySignalDirection
    qty: float
    order_type: str
    limit_price: float | None = None
    time_in_force: str | None = None
    lease_id: str | None = None
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionReport(_SpineModel):
    schema_version: str = "agent_spine.execution_report.v1"
    execution_report_id: str
    order_plan_id: str
    decision_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    status: str
    exchange_order_id: str | None = None
    fill_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalystInsight(_SpineModel):
    schema_version: str = "agent_spine.analyst_insight.v1"
    insight_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str | None = None
    decision_id: str | None = None
    order_plan_id: str | None = None
    execution_report_id: str | None = None
    insight_level: Literal["fact", "inference", "hypothesis"] = "inference"
    summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    claims: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


SpinePayload = (
    StrategySignal
    | StrategistDecision
    | GuardianVerdict
    | ExecutionPlan
    | ExecutionReport
    | AnalystInsight
)


def payload_dict(model: SpinePayload) -> dict[str, Any]:
    return model.model_dump(mode="json")

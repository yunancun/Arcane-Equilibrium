"""Typed Agent Decision Spine contracts for Python agents.

MAG-033 mirrors the Rust `agent_spine::contracts` payloads so Strategist,
Guardian, Executor, and Analyst can exchange typed objects through the durable
spine store without free-text routing.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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

GuardianP2Field = Literal["size", "leverage", "stop", "cooldown"]
GuardianP2Action = Literal["cap", "reduce", "tighten", "extend", "set"]

ExecutionOrderStyle = Literal["market", "limit", "post_only", "twap", "split"]
ExecutionUrgency = Literal["low", "normal", "high", "urgent"]
ExecutionMakerPreference = Literal["none", "prefer_maker", "maker_only", "allow_taker"]
ExecutionAuthoritySource = Literal["strategist_decision"]

PositionReviewRecommendation = Literal[
    "hold",
    "reduce",
    "tighten_exit",
    "stop_adding",
    "close_when_net_positive",
    "close_now_if_risk_requires",
    "no_action",
]

PositionReviewTrigger = Literal[
    "scanner_decay",
    "analyst_risk_pattern",
    "guardian_risk_pattern",
    "adverse_pnl_drift",
    "cost_edge_ratio_deterioration",
    "regime_shift",
    "time_stop_nearing",
]

PositionReviewUrgency = Literal["low", "medium", "high", "critical"]

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


class PositionReview(_SpineModel):
    schema_version: str = "agent_spine.position_review.v1"
    position_review_id: str
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str | None = None
    position_id: str | None = None
    scanner_decay_id: str | None = None
    trigger: PositionReviewTrigger
    recommendation: PositionReviewRecommendation
    decision_action: DecisionAction = "hold"
    direction: StrategySignalDirection = "neutral"
    urgency: PositionReviewUrgency = "low"
    confidence: float = 0.0
    remaining_edge_lcb_bps: float | None = None
    exit_cost_bps: float | None = None
    current_pnl_bps: float | None = None
    net_exit_bps: float | None = None
    market_regime_before: str | None = None
    market_regime_after: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    position_directives: dict[str, Any] = Field(default_factory=dict)
    thesis: str | None = None
    invalidation: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    fact_refs: list[str] = Field(default_factory=list)
    inference_refs: list[str] = Field(default_factory=list)
    hypothesis_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GuardianP2Modification(_SpineModel):
    field: GuardianP2Field
    action: GuardianP2Action
    original_value: float | int | str | None = None
    modified_value: float | int | str
    unit: str | None = None
    reason_code: str
    reason: str
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
    p2_modifications: list[GuardianP2Modification] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionPlan(_SpineModel):
    schema_version: str = "agent_spine.execution_plan.v1"
    order_plan_id: str
    decision_id: str
    verdict_id: str = Field(min_length=1)
    verdict_version: int = Field(ge=0)
    ts_ms: int
    engine_mode: str
    symbol: str
    strategy: str
    direction: StrategySignalDirection
    symbol_source: ExecutionAuthoritySource
    direction_source: ExecutionAuthoritySource
    qty: float = Field(gt=0)
    reduce_only: bool = False
    order_style: ExecutionOrderStyle
    urgency: ExecutionUrgency = "normal"
    max_slippage_bps: float | None = Field(default=None, ge=0, le=10_000)
    maker_preference: ExecutionMakerPreference = "none"
    order_type: str
    limit_price: float | None = Field(default=None, gt=0)
    time_in_force: str | None = None
    order_style_params: dict[str, Any] = Field(default_factory=dict)
    local_stop_policy: dict[str, Any] = Field(default_factory=dict)
    anti_hunt_stop_policy: dict[str, Any] = Field(default_factory=dict)
    lease_scope: str | None = None
    lease_ttl_ms: int | None = Field(default=None, ge=1)
    lease_id: str | None = None
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_execution_plan_contract(self) -> "ExecutionPlan":
        order_type = self.order_type.strip().lower()
        time_in_force = (self.time_in_force or "").strip().lower()

        if self.order_style == "market":
            if order_type != "market":
                raise ValueError("market_style_requires_market_order_type")
            if self.limit_price is not None:
                raise ValueError("market_style_forbids_limit_price")
            if self.time_in_force is not None:
                raise ValueError("market_style_forbids_time_in_force")
        elif self.order_style == "limit":
            if order_type != "limit":
                raise ValueError("limit_style_requires_limit_order_type")
            if self.limit_price is None:
                raise ValueError("limit_style_requires_limit_price")
            if time_in_force == "postonly":
                raise ValueError("post_only_tif_requires_post_only_style")
        elif self.order_style == "post_only":
            if order_type != "limit":
                raise ValueError("post_only_style_requires_limit_order_type")
            if self.limit_price is None:
                raise ValueError("post_only_style_requires_limit_price")
            if time_in_force != "postonly":
                raise ValueError("post_only_style_requires_postonly_tif")
        elif self.order_style in ("twap", "split"):
            if order_type not in {"market", "limit"}:
                raise ValueError("scheduled_style_requires_market_or_limit_order_type")
            if order_type == "limit" and self.limit_price is None:
                raise ValueError("scheduled_limit_style_requires_limit_price")

        if self.maker_preference == "maker_only" and self.order_style != "post_only":
            raise ValueError("maker_only_requires_post_only_style")
        if self.maker_preference == "allow_taker" and self.order_style == "post_only":
            raise ValueError("post_only_style_forbids_allow_taker_preference")

        close_direction = self.direction in ("close_long", "close_short")
        if self.reduce_only and not close_direction:
            raise ValueError("reduce_only_requires_close_direction")
        if close_direction and not self.reduce_only:
            raise ValueError("close_direction_requires_reduce_only")

        return self


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

from __future__ import annotations

"""
Scanner advisory contracts for Agent Decision Spine conversion.

MODULE_NOTE (中文):
  MAG-021 的 Python-side 序列化契約。這些模型只表示 scanner evidence，
  不表示訂單、approval、risk verdict 或 live config mutation。
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SCANNER_ADVISORY_BOUNDARY: dict[str, Any] = {
    "module": "scanner",
    "output_class": "advisory_evidence",
    "can_directly_approve_orders": False,
    "can_directly_dispatch_orders": False,
    "can_directly_close_positions": False,
    "position_decay_requires_review": True,
    "execution_path": [
        "OpportunityCandidate",
        "StrategistDecision",
        "GuardianVerdict",
        "ExecutionPlan",
        "DecisionLease",
    ],
}

ScannerAuthorityMode = Literal[
    "legacy_gate",
    "advisory_shadow",
    "advisory_enforced",
]

OpportunityDecayReason = Literal[
    "score_weakened",
    "displaced",
    "exited_top_set",
    "data_stale",
    "hard_fact_invalid",
]


class OpportunityCandidate(BaseModel):
    """Scanner candidate evidence; advisory only / scanner candidate evidence；僅 advisory。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    candidate_id: str
    scan_id: str
    scan_ts_ms: int
    symbol: str
    strategy: str
    authority_mode: ScannerAuthorityMode = "legacy_gate"
    final_score: float
    raw_score: float
    opportunity_score: float | None = None
    opportunity_lcb_bps: float | None = None
    admission_hint: str | None = None
    route_mode: str
    market_status: str
    route_reason: str
    data_quality_score: float | None = None
    edge_bps: float | None = None
    edge_n: int = 0
    evidence: dict[str, Any] = Field(default_factory=dict)


class OpportunityDecay(BaseModel):
    """Scanner decay evidence; never a direct close / scanner decay evidence；絕非直接平倉。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1.0"
    decay_id: str
    candidate_id: str | None = None
    scan_id: str
    decay_ts_ms: int
    symbol: str
    strategy: str | None = None
    authority_mode: ScannerAuthorityMode = "legacy_gate"
    reason: OpportunityDecayReason
    previous_score: float | None = None
    current_score: float | None = None
    previous_rank: int | None = None
    current_rank: int | None = None
    has_open_position: bool = False
    position_review_required: bool = False
    auto_close_allowed: bool = False
    evidence: dict[str, Any] = Field(default_factory=dict)

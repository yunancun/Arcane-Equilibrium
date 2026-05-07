from __future__ import annotations

"""
OpenClaw read-only API models.

MODULE_NOTE (中文):
  MAG-015+ 的 backend-authored view-model 契約。這些模型描述
  /api/v1/openclaw/* envelope、proposal ledger、approval relay request；approval
  model 只表示 operator decision record，不代表 order / config / live-auth 執行。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


OpenClawStatus = Literal["pass", "warn", "fail", "degraded", "disabled"]
OpenClawProposalType = Literal[
    "read_only_report",
    "diagnosis_followup",
    "offline_replay",
    "config_change",
    "risk_change",
    "live_authorization",
    "deploy",
    "trade_affecting",
]
OpenClawRiskClass = Literal[
    "read_only",
    "offline",
    "demo_only",
    "live_affecting",
    "mainnet_affecting",
]
OpenClawRequiredApprovalClass = Literal[
    "none",
    "operator",
    "governance",
    "live_reserved",
    "deploy_operator",
]
OpenClawProposalStatus = Literal[
    "drafted",
    "persisted",
    "visible",
    "pending_approval",
    "completed_read_only",
    "approved",
    "rejected",
    "expired",
    "cancelled",
    "failed",
]
OpenClawApprovalDecision = Literal[
    "approved",
    "rejected",
    "expired",
    "denied",
    "cancelled",
]


class OpenClawEvidenceRef(BaseModel):
    ref_type: Literal[
        "db_row",
        "healthcheck",
        "report",
        "api_route",
        "log_excerpt",
        "config_key",
        "commit",
        "runtime_probe",
    ]
    ref_id: str
    label: str
    freshness_ts_ms: int | None = None
    engine_mode: str | None = None
    safe_url: str | None = None


class OpenClawEnvelope(BaseModel):
    ok: bool
    status: OpenClawStatus
    generated_at_ms: int
    freshness_ms: int | None = None
    degraded: bool
    degraded_reasons: list[str] = Field(default_factory=list)
    evidence_refs: list[OpenClawEvidenceRef] = Field(default_factory=list)
    data: dict[str, Any]
    is_simulated: bool = False
    data_category: str


class OpenClawProposalCreateRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    proposal_type: OpenClawProposalType = "read_only_report"
    risk_class: OpenClawRiskClass = "read_only"
    summary: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[OpenClawEvidenceRef] = Field(default_factory=list)
    required_approval_class: OpenClawRequiredApprovalClass = "none"
    expires_at_ms: int | None = None
    linked_diagnosis_id: str | None = Field(default=None, max_length=200)
    linked_escalation_id: str | None = Field(default=None, max_length=200)
    side_effect_route: str | None = Field(default=None, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)


class OpenClawProposalDecisionRequest(BaseModel):
    request_id: str | None = Field(default=None, min_length=1, max_length=200)
    reason: str | None = Field(default=None, max_length=1000)

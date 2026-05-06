from __future__ import annotations

"""
OpenClaw read-only API models.

MODULE_NOTE (中文):
  MAG-015/MAG-017 的 backend-authored view-model 契約。這些模型只描述
  /api/v1/openclaw/* 讀取回應，不承載 proposal / approval / order 寫入能力。
"""

from typing import Any, Literal

from pydantic import BaseModel, Field


OpenClawStatus = Literal["pass", "warn", "fail", "degraded", "disabled"]


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

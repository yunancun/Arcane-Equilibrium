from __future__ import annotations

"""
OpenClaw supervisor cloud escalation policy.

MODULE_NOTE (中文):
  MAG-019 的 supervisor cloud ledger foundation。此模組只負責 packet、
  budget decision、以及 cloud call 前的 `agent.ai_invocations` ledger row
  預留；它本身不呼叫任何 cloud/network provider。
"""

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from typing import Any


_TRIGGER_TYPES = {
    "healthcheck_fail",
    "edge_regression",
    "execution_quality_shock",
    "strategy_anomaly",
    "governance_contradiction",
    "operator_requested",
    "daily_brief_low_confidence",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def _json_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _bounded_summary(value: str, *, max_bytes: int) -> tuple[str, bool]:
    encoded = value.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return value, False
    trimmed = encoded[: max(0, max_bytes - 32)].decode("utf-8", errors="ignore")
    return trimmed + " [truncated]", True


@dataclass(frozen=True)
class SupervisorCloudConfig:
    enabled: bool
    require_budget: bool
    daily_cap_usd: float | None
    monthly_cap_usd: float | None
    max_packet_bytes: int
    provider: str | None
    model: str | None
    tier: str = "L2"

    @classmethod
    def from_env(cls) -> "SupervisorCloudConfig":
        return cls(
            enabled=_env_enabled("OPENCLAW_SUPERVISOR_CLOUD_ENABLED"),
            require_budget=_env_enabled("OPENCLAW_SUPERVISOR_CLOUD_REQUIRE_BUDGET", "1"),
            daily_cap_usd=_env_float("OPENCLAW_SUPERVISOR_CLOUD_DAILY_USD_CAP"),
            monthly_cap_usd=_env_float("OPENCLAW_SUPERVISOR_CLOUD_MONTHLY_USD_CAP"),
            max_packet_bytes=_env_int("OPENCLAW_SUPERVISOR_CLOUD_MAX_PACKET_BYTES", 32_768),
            provider=os.getenv("OPENCLAW_SUPERVISOR_CLOUD_PROVIDER") or None,
            model=os.getenv("OPENCLAW_SUPERVISOR_CLOUD_MODEL") or None,
            tier=os.getenv("OPENCLAW_SUPERVISOR_CLOUD_TIER", "L2"),
        )

    @property
    def budget_configured(self) -> bool:
        return self.daily_cap_usd is not None and self.monthly_cap_usd is not None

    @property
    def model_configured(self) -> bool:
        return bool(self.provider and self.model)

    def evaluate_budget(self, *, estimated_cost_usd: float = 0.0) -> dict[str, Any]:
        estimated = max(0.0, float(estimated_cost_usd or 0.0))
        reason = "allowed"
        allowed = True
        if not self.enabled:
            allowed = False
            reason = "cloud_disabled_by_env"
        elif self.require_budget and not self.budget_configured:
            allowed = False
            reason = "cloud_budget_missing"
        elif self.daily_cap_usd is not None and estimated > self.daily_cap_usd:
            allowed = False
            reason = "daily_budget_exceeded"
        elif self.monthly_cap_usd is not None and estimated > self.monthly_cap_usd:
            allowed = False
            reason = "monthly_budget_exceeded"
        elif not self.model_configured:
            allowed = False
            reason = "cloud_model_missing"

        return {
            "allowed": allowed,
            "status": "allowed" if allowed else "denied",
            "reason": reason,
            "cloud_enabled": self.enabled,
            "require_budget": self.require_budget,
            "budget_configured": self.budget_configured,
            "daily_cap_configured": self.daily_cap_usd is not None,
            "monthly_cap_configured": self.monthly_cap_usd is not None,
            "daily_cap_usd": self.daily_cap_usd,
            "monthly_cap_usd": self.monthly_cap_usd,
            "estimated_cost_usd": round(estimated, 6),
            "provider_configured": bool(self.provider),
            "model_configured": bool(self.model),
        }

    def model_request(self) -> dict[str, str] | None:
        if not self.model_configured:
            return None
        return {
            "provider": str(self.provider),
            "model": str(self.model),
            "tier": self.tier,
        }


def build_supervisor_cloud_policy_snapshot(
    *,
    estimated_cost_usd: float = 0.0,
    config: SupervisorCloudConfig | None = None,
) -> dict[str, Any]:
    cfg = config or SupervisorCloudConfig.from_env()
    decision = cfg.evaluate_budget(estimated_cost_usd=estimated_cost_usd)
    return {
        "cloud_enabled": cfg.enabled,
        "require_budget": cfg.require_budget,
        "budget_configured": cfg.budget_configured,
        "daily_cap_configured": cfg.daily_cap_usd is not None,
        "monthly_cap_configured": cfg.monthly_cap_usd is not None,
        "provider_configured": bool(cfg.provider),
        "model_configured": bool(cfg.model),
        "disabled_reason": None if decision["allowed"] else decision["reason"],
        "per_agent_cloud_calls_allowed": False,
        "supervisor_packet_required": True,
        "ai_invocation_link_required": True,
        "default_cloud_call_allowed": decision["allowed"],
        "budget_decision": decision,
    }


def build_escalation_packet(
    *,
    trigger_type: str,
    source_observation_ids: list[str],
    input_summary: str,
    estimated_cost_usd: float = 0.0,
    config: SupervisorCloudConfig | None = None,
    created_at_ms: int | None = None,
) -> dict[str, Any]:
    if trigger_type not in _TRIGGER_TYPES:
        raise ValueError(f"invalid_trigger_type:{trigger_type}")
    cfg = config or SupervisorCloudConfig.from_env()
    created = created_at_ms or _now_ms()
    safe_summary, truncated = _bounded_summary(
        input_summary,
        max_bytes=max(256, cfg.max_packet_bytes),
    )
    budget_decision = cfg.evaluate_budget(estimated_cost_usd=estimated_cost_usd)
    diagnosis_id = None
    diagnoses: list[dict[str, Any]] = []
    if not budget_decision["allowed"]:
        diagnosis_id = "diag_cloud_budget_" + _json_hash(
            {
                "trigger_type": trigger_type,
                "source_observation_ids": source_observation_ids,
                "reason": budget_decision["reason"],
                "created_at_ms": created,
            }
        )
        diagnoses.append(
            {
                "diagnosis_id": diagnosis_id,
                "ts_ms": created,
                "severity": "warn",
                "domain": "ai_cost",
                "status": "open",
                "facts": [budget_decision["reason"]],
                "inferences": [],
                "hypotheses": [],
                "recommended_action": "keep_supervisor_cloud_disabled",
                "evidence_refs": [],
                "linked_escalation_id": None,
                "linked_proposal_id": None,
            }
        )
    escalation_id = "esc_" + _json_hash(
        {
            "trigger_type": trigger_type,
            "source_observation_ids": source_observation_ids,
            "input_summary_hash": _sha256_text(safe_summary),
            "created_at_ms": created,
        }
    )
    for diagnosis in diagnoses:
        diagnosis["linked_escalation_id"] = escalation_id
    return {
        "escalation_id": escalation_id,
        "created_at_ms": created,
        "trigger_type": trigger_type,
        "source_observation_ids": list(source_observation_ids),
        "budget_decision": budget_decision,
        "prompt_hash": _sha256_text(safe_summary),
        "input_summary": safe_summary,
        "payload_truncated": truncated,
        "model_request": cfg.model_request() if budget_decision["allowed"] else None,
        "ai_invocation_id": None,
        "response_summary": None,
        "result_diagnosis_ids": [diagnosis_id] if diagnosis_id else [],
        "result_proposal_ids": [],
        "diagnoses": diagnoses,
        "status": "budget_checked" if budget_decision["allowed"] else "denied",
    }


def record_invocation_before_cloud_call(
    *,
    packet: dict[str, Any],
    event_store: Any,
    estimated_input_tokens: int = 0,
) -> dict[str, Any]:
    budget = packet.get("budget_decision") or {}
    if not budget.get("allowed"):
        return dict(packet)
    model_request = packet.get("model_request") or {}
    if event_store is None:
        out = dict(packet)
        out["status"] = "failed"
        out["degraded_reason"] = "agent_event_store_unavailable"
        return out
    invocation_id = "ai_supervisor_" + uuid.uuid4().hex[:16]
    record_fn = getattr(event_store, "record_ai_invocation", None)
    if record_fn is None:
        out = dict(packet)
        out["status"] = "failed"
        out["degraded_reason"] = "agent_event_store_missing_method"
        return out
    ok = bool(
        record_fn(
            invocation_id=invocation_id,
            provider=model_request.get("provider") or "unknown",
            model=model_request.get("model") or "unknown",
            tier=model_request.get("tier") or "L2",
            purpose="openclaw_supervisor_escalation",
            prompt_hash=packet.get("prompt_hash"),
            input_tokens=int(estimated_input_tokens or 0),
            output_tokens=0,
            cost_usd=float(budget.get("estimated_cost_usd") or 0.0),
            latency_ms=0,
            success=False,
            response_summary="supervisor cloud invocation reserved before request",
            context_id=packet.get("escalation_id"),
            details={
                "control_plane": True,
                "escalation_id": packet.get("escalation_id"),
                "trigger_type": packet.get("trigger_type"),
                "source_observation_ids": packet.get("source_observation_ids") or [],
                "budget_decision": budget,
                "input_summary_hash": packet.get("prompt_hash"),
                "ledger_phase": "before_cloud_call",
            },
            engine_mode=None,
        )
    )
    out = dict(packet)
    if not ok:
        out["status"] = "failed"
        out["degraded_reason"] = "ai_invocation_record_failed"
        return out
    out["ai_invocation_id"] = invocation_id
    out["status"] = "invocation_recorded"
    return out

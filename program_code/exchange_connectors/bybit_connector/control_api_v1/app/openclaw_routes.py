from __future__ import annotations

"""
OpenClaw read-only control-plane routes.

MODULE_NOTE (中文):
  MAG-016/MAG-017 只讀基礎層。此模組只暴露 Sprint A allowlist：
  GET /api/v1/openclaw/status 與 GET /api/v1/openclaw/self-state。
  它聚合 backend-authored view models，所有 backing source 缺失都回
  degraded envelope，不新增 proposal / approval / trading side effect。
"""

import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Request

from . import agents_routes_helpers as _agent_h
from . import main_legacy as base
from .db_pool import get_pg_conn
from .openclaw_models import OpenClawEnvelope, OpenClawEvidenceRef, OpenClawStatus
from .openclaw_supervisor_policy import build_supervisor_cloud_policy_snapshot

logger = logging.getLogger(__name__)


openclaw_router = APIRouter(
    prefix="/api/v1/openclaw",
    tags=["OpenClaw Read-Only / OpenClaw 只讀"],
)

_STATEMENT_TIMEOUT_MS = 2_000
_RECENT_WINDOW_MINUTES = 30
_AGENT_EVENT_TABLES = (
    "agent.messages",
    "agent.state_changes",
    "agent.ai_invocations",
)
_LOCAL_AGENT_ROLES = ("scout", "strategist", "guardian", "executor", "analyst")
_OPENCLAW_CONTEXT_HEADERS = {
    "source": "x-openclaw-source",
    "channel": "x-openclaw-channel",
    "sender": "x-openclaw-sender",
    "auth_profile": "x-openclaw-auth-profile",
    "request_id": "x-openclaw-request-id",
}


def _now_ms() -> int:
    return int(time.time() * 1000)


def _iso_from_ms(ts_ms: int | None) -> str | None:
    if ts_ms is None:
        return None
    try:
        return datetime.fromtimestamp(ts_ms / 1000.0, tz=timezone.utc).isoformat()
    except Exception:
        return None


def _env_enabled(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).strip() == "1"


def _safe_status_reason(prefix: str, exc: Exception) -> str:
    return f"{prefix}:{type(exc).__name__}"


def _hash_snapshot(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _set_statement_timeout(cur: Any) -> None:
    cur.execute("SET LOCAL statement_timeout = %s", (_STATEMENT_TIMEOUT_MS,))


def _read_agent_event_store_summary() -> tuple[dict[str, Any], str | None]:
    enabled = _env_enabled("OPENCLAW_AGENT_EVENT_STORE_ENABLED")
    required = _env_enabled("OPENCLAW_AGENT_EVENT_STORE_HEALTH_REQUIRED")
    window_minutes = int(
        os.getenv(
            "OPENCLAW_AGENT_EVENT_STORE_HEALTH_WINDOW_MINUTES",
            str(_RECENT_WINDOW_MINUTES),
        )
    )
    summary: dict[str, Any] = {
        "enabled": enabled,
        "required": required,
        "window_minutes": window_minutes,
        "tables_present": False,
        "missing_tables": [],
        "recent_rows": {
            "messages": 0,
            "state_changes": 0,
            "ai_invocations": 0,
        },
        "row_proof": False,
        "zero_row_blocker": False,
        "status": "disabled" if not enabled else "degraded",
    }

    with get_pg_conn() as conn:
        if conn is None:
            return summary, "pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            missing: list[str] = []
            for table_name in _AGENT_EVENT_TABLES:
                cur.execute("SELECT to_regclass(%s) IS NOT NULL", (table_name,))
                row = cur.fetchone()
                if not row or not row[0]:
                    missing.append(table_name)
            if missing:
                summary["missing_tables"] = missing
                summary["status"] = "fail" if enabled or required else "disabled"
                summary["zero_row_blocker"] = enabled or required
                return summary, None

            summary["tables_present"] = True
            counts: dict[str, int] = {}
            for table_name in _AGENT_EVENT_TABLES:
                cur.execute(
                    f"""
                    SELECT count(*)::int
                      FROM {table_name}
                     WHERE ts > now() - (%s::text || ' minutes')::interval
                    """,
                    (window_minutes,),
                )
                row = cur.fetchone()
                counts[table_name] = int(row[0] if row else 0)

            recent_rows = {
                "messages": counts["agent.messages"],
                "state_changes": counts["agent.state_changes"],
                "ai_invocations": counts["agent.ai_invocations"],
            }
            zero_rows = [name for name, count in recent_rows.items() if count <= 0]
            summary["recent_rows"] = recent_rows
            summary["row_proof"] = not zero_rows
            summary["zero_row_blocker"] = bool(zero_rows and (enabled or required))
            if not enabled:
                summary["status"] = "disabled"
            elif zero_rows:
                summary["status"] = "fail" if required else "warn"
                summary["zero_rows"] = zero_rows
            else:
                summary["status"] = "pass"
            return summary, None
        except Exception as exc:  # noqa: BLE001 - read route degrades, never 5xx
            logger.warning("openclaw agent event-store read failed: %s", exc)
            return summary, _safe_status_reason("pg_error", exc)


def _read_runtime_summary() -> tuple[dict[str, Any], str | None]:
    try:
        snapshot, source_context = base.get_latest_snapshot()
        meta = snapshot.get("meta", {}) if isinstance(snapshot, dict) else {}
        global_runtime = (
            snapshot.get("global_runtime", {}) if isinstance(snapshot, dict) else {}
        )
        facts = global_runtime.get("facts", {}) if isinstance(global_runtime, dict) else {}
        derived = (
            global_runtime.get("derived", {}) if isinstance(global_runtime, dict) else {}
        )
        snapshot_ts_ms = int(meta.get("snapshot_ts_ms") or 0)
        generated_at_ms = _now_ms()
        return (
            {
                "snapshot_id": str(meta.get("snapshot_id") or ""),
                "snapshot_ts_ms": snapshot_ts_ms,
                "snapshot_ts": _iso_from_ms(snapshot_ts_ms),
                "snapshot_age_ms": (
                    max(0, generated_at_ms - snapshot_ts_ms) if snapshot_ts_ms else None
                ),
                "state_revision": int(meta.get("state_revision") or 0),
                "runtime_connection_state": getattr(
                    source_context, "runtime_connection_state", "unknown"
                ),
                "pinned_runtime_snapshot_id": getattr(
                    source_context, "pinned_runtime_snapshot_id", ""
                ),
                "pinned_runtime_snapshot_ts_ms": getattr(
                    source_context, "pinned_runtime_snapshot_ts_ms", 0
                ),
                "engine_alive": facts.get("engine_alive"),
                "global_mode_state": derived.get("global_mode_state"),
                "paper_posture": facts.get("paper_state") or facts.get("paper"),
                "demo_posture": facts.get("demo_state") or facts.get("demo"),
                "live_posture": facts.get("live_state") or facts.get("live"),
            },
            None,
        )
    except Exception as exc:  # noqa: BLE001 - safe read envelope
        logger.warning("openclaw runtime snapshot read failed: %s", exc)
        return (
            {
                "snapshot_id": "",
                "snapshot_ts_ms": 0,
                "snapshot_ts": None,
                "snapshot_age_ms": None,
                "state_revision": 0,
                "runtime_connection_state": "unknown",
                "pinned_runtime_snapshot_id": "",
                "pinned_runtime_snapshot_ts_ms": 0,
                "engine_alive": None,
                "global_mode_state": None,
                "paper_posture": None,
                "demo_posture": None,
                "live_posture": None,
            },
            _safe_status_reason("runtime_snapshot_unavailable", exc),
        )


def _agent_stats(agent: Any) -> dict[str, Any]:
    stats = _agent_h._safe_call(_agent_h._safe_get(agent, "get_stats"))
    return dict(stats) if isinstance(stats, dict) else {}


def _build_agent_states() -> list[dict[str, Any]]:
    sw = sys.modules.get("app.strategy_wiring") or sys.modules.get(
        "program_code.exchange_connectors.bybit_connector.control_api_v1.app.strategy_wiring"
    )
    role_to_attr = {
        "scout": "SCOUT_AGENT",
        "strategist": "STRATEGIST_AGENT",
        "guardian": "GUARDIAN_AGENT",
        "executor": "EXECUTOR_AGENT",
        "analyst": "ANALYST_AGENT",
    }
    out: list[dict[str, Any]] = []
    for role in _LOCAL_AGENT_ROLES:
        stats = _agent_stats(_agent_h._safe_get(sw, role_to_attr[role]))
        out.append(
            {
                "role": role,
                "runtime_state": stats.get("state") or "unknown",
                "last_heartbeat_ms": stats.get("last_heartbeat_ms"),
                "shadow_mode": stats.get("shadow_mode") if role == "executor" else None,
                "source": "strategy_wiring" if stats else "not_loaded",
            }
        )

    conductor = _agent_h._safe_get(sw, "CONDUCTOR")
    conductor_stats = _agent_stats(conductor)
    out.append(
        {
            "role": "conductor",
            "runtime_state": conductor_stats.get("state") or (
                "available" if conductor is not None else "unknown"
            ),
            "last_heartbeat_ms": conductor_stats.get("last_heartbeat_ms"),
            "source": "strategy_wiring" if conductor is not None else "not_loaded",
        }
    )
    out.append(
        {
            "role": "supervisor",
            "runtime_state": "disabled",
            "last_heartbeat_ms": None,
            "source": "mag019_pending",
        }
    )
    return out


def _build_authority_posture() -> dict[str, Any]:
    return {
        "trading_authority": "rust_openclaw_engine",
        "gateway_role": "read_only_supervisor_relay",
        "active_allowlist": [
            {"method": "GET", "path": "/api/v1/openclaw/status"},
            {"method": "GET", "path": "/api/v1/openclaw/self-state"},
        ],
        "deferred_workflows_enabled": False,
        "can_submit_orders": False,
        "can_cancel_orders": False,
        "can_close_positions": False,
        "can_mutate_live_config": False,
        "can_mutate_risk_config": False,
        "can_read_secrets": False,
        "can_restart_or_deploy": False,
        "requires_governance_hub_for_side_effects": True,
        "requires_decision_lease_for_execution": True,
        "request_context_required": list(_OPENCLAW_CONTEXT_HEADERS.keys()),
    }


def _build_gateway_posture() -> dict[str, Any]:
    configured = bool(os.getenv("OPENCLAW_GATEWAY_BASE_URL", "").strip())
    return {
        "configured": configured,
        "status": "not_configured" if not configured else "configured_read_only",
        "channels": {
            "console": "available",
            "telegram": "disabled",
            "webchat": "disabled",
            "mobile": "disabled",
            "gateway_internal": "disabled",
        },
        "outage_non_fatal_to_trading_runtime": True,
    }


def _build_request_context(
    request: Request,
    actor: base.AuthenticatedActor,
) -> tuple[dict[str, Any], str | None]:
    values: dict[str, str | None] = {}
    missing: list[str] = []
    for field, header in _OPENCLAW_CONTEXT_HEADERS.items():
        value = request.headers.get(header)
        if not value:
            missing.append(field)
        values[field] = value

    effective_auth_profile = values["auth_profile"] or (
        "operator" if "operator" in actor.roles else "read_only"
    )
    context = {
        "source": values["source"] or "console",
        "channel": values["channel"] or "console",
        "sender": values["sender"] or actor.actor_id,
        "auth_profile": effective_auth_profile,
        "request_id": values["request_id"] or request.headers.get("x-request-id"),
        "complete": not missing,
        "missing": missing,
    }
    if missing:
        return context, "request_context_inferred"
    return context, None


def _build_governance_posture() -> dict[str, Any]:
    return {
        "governance_hub_required": True,
        "decision_lease_required": True,
        "live_auth_mutation_allowed": False,
        "direct_trade_side_effect_allowed": False,
        "known_live_blockers": [],
    }


def _build_edge_summary() -> dict[str, Any]:
    return {
        "status": "not_queried",
        "read_only_sources": ["[33]", "[38]", "[40]", "[51]"],
        "raw_table_join_in_frontend_allowed": False,
    }


def _build_model_budget(event_store: dict[str, Any]) -> dict[str, Any]:
    policy = build_supervisor_cloud_policy_snapshot()
    return {
        "local_event_store_ai_rows_30m": event_store["recent_rows"]["ai_invocations"],
        **policy,
    }


def _build_blockers(
    *,
    event_store: dict[str, Any],
    event_store_error: str | None,
    runtime_error: str | None,
    request_context_error: str | None,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if event_store_error:
        blockers.append(
            {
                "code": "agent_event_store_unavailable",
                "severity": "warn",
                "summary": "Agent event-store backing source is unavailable.",
            }
        )
    if event_store.get("zero_row_blocker"):
        blockers.append(
            {
                "code": "agent_event_store_zero_rows",
                "severity": "fail",
                "summary": "Required recent agent event-store row proof is incomplete.",
            }
        )
    if runtime_error:
        blockers.append(
            {
                "code": "runtime_snapshot_unavailable",
                "severity": "warn",
                "summary": "Runtime snapshot could not be read for this envelope.",
            }
        )
    if request_context_error:
        blockers.append(
            {
                "code": "request_context_inferred",
                "severity": "warn",
                "summary": "OpenClaw request context headers were missing and inferred.",
            }
        )
    return blockers


def _derive_envelope_status(
    *,
    event_store: dict[str, Any],
    source_errors: list[str],
    blockers: list[dict[str, Any]],
) -> tuple[OpenClawStatus, bool, list[str]]:
    degraded_reasons = [reason for reason in source_errors if reason]
    if any(blocker["severity"] == "fail" for blocker in blockers):
        return "fail", bool(degraded_reasons), degraded_reasons
    if degraded_reasons:
        return "degraded", True, degraded_reasons
    if event_store["status"] == "disabled":
        return "warn", False, []
    if any(blocker["severity"] == "warn" for blocker in blockers):
        return "warn", False, []
    return "pass", False, []


def _evidence_refs(generated_at_ms: int) -> list[OpenClawEvidenceRef]:
    return [
        OpenClawEvidenceRef(
            ref_type="api_route",
            ref_id="GET /api/v1/openclaw/status",
            label="Sprint A active OpenClaw status allowlist route",
            freshness_ts_ms=generated_at_ms,
            safe_url="/api/v1/openclaw/status",
        ),
        OpenClawEvidenceRef(
            ref_type="api_route",
            ref_id="GET /api/v1/openclaw/self-state",
            label="Sprint A active OpenClaw self-state allowlist route",
            freshness_ts_ms=generated_at_ms,
            safe_url="/api/v1/openclaw/self-state",
        ),
        OpenClawEvidenceRef(
            ref_type="healthcheck",
            ref_id="[52] agent_event_store_rows",
            label="Agent event-store recent row proof",
            freshness_ts_ms=generated_at_ms,
        ),
    ]


def _compose_common_payload(
    *,
    request: Request,
    actor: base.AuthenticatedActor,
    event_store: dict[str, Any],
    event_store_error: str | None,
    runtime: dict[str, Any],
    runtime_error: str | None,
    generated_at_ms: int,
) -> tuple[dict[str, Any], OpenClawStatus, bool, list[str]]:
    request_context, request_context_error = _build_request_context(request, actor)
    source_errors = [
        reason
        for reason in (event_store_error, runtime_error, request_context_error)
        if reason
    ]
    blockers = _build_blockers(
        event_store=event_store,
        event_store_error=event_store_error,
        runtime_error=runtime_error,
        request_context_error=request_context_error,
    )
    status, degraded, degraded_reasons = _derive_envelope_status(
        event_store=event_store,
        source_errors=source_errors,
        blockers=blockers,
    )
    common = {
        "generated_at": _iso_from_ms(generated_at_ms),
        "request_context": request_context,
        "authority": _build_authority_posture(),
        "gateway": _build_gateway_posture(),
        "runtime": runtime,
        "agent_event_store": event_store,
        "governance": _build_governance_posture(),
        "model_budget": _build_model_budget(event_store),
        "open_blockers": blockers,
    }
    return common, status, degraded, degraded_reasons


async def _read_backing_sources() -> tuple[dict[str, Any], str | None, dict[str, Any], str | None]:
    (event_store, event_store_error), (runtime, runtime_error) = await asyncio.gather(
        asyncio.to_thread(_read_agent_event_store_summary),
        asyncio.to_thread(_read_runtime_summary),
    )
    return event_store, event_store_error, runtime, runtime_error


@openclaw_router.get("/status", response_model=OpenClawEnvelope)
async def get_openclaw_status(
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    generated_at_ms = _now_ms()
    event_store, event_store_error, runtime, runtime_error = await _read_backing_sources()
    common, status, degraded, degraded_reasons = _compose_common_payload(
        request=request,
        actor=actor,
        event_store=event_store,
        event_store_error=event_store_error,
        runtime=runtime,
        runtime_error=runtime_error,
        generated_at_ms=generated_at_ms,
    )
    data = {
        "overall_state": status,
        "authority": common["authority"],
        "gateway": common["gateway"],
        "runtime": common["runtime"],
        "agent_event_store": common["agent_event_store"],
        "model_budget": common["model_budget"],
        "request_context": common["request_context"],
        "open_blockers": common["open_blockers"],
    }
    return OpenClawEnvelope(
        ok=(not degraded and status not in {"fail", "degraded"}),
        status=status,
        generated_at_ms=generated_at_ms,
        freshness_ms=runtime.get("snapshot_age_ms"),
        degraded=degraded or status == "degraded",
        degraded_reasons=degraded_reasons,
        evidence_refs=_evidence_refs(generated_at_ms),
        data=data,
        data_category="openclaw_status",
    )


@openclaw_router.get("/self-state", response_model=OpenClawEnvelope)
async def get_openclaw_self_state(
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    generated_at_ms = _now_ms()
    event_store, event_store_error, runtime, runtime_error = await _read_backing_sources()
    common, status, degraded, degraded_reasons = _compose_common_payload(
        request=request,
        actor=actor,
        event_store=event_store,
        event_store_error=event_store_error,
        runtime=runtime,
        runtime_error=runtime_error,
        generated_at_ms=generated_at_ms,
    )
    snapshot_payload = {
        "generated_at_ms": generated_at_ms,
        "runtime_snapshot_id": runtime.get("snapshot_id"),
        "event_rows": event_store.get("recent_rows"),
        "status": status,
    }
    data = {
        "snapshot_id": f"openclaw_self_state_{_hash_snapshot(snapshot_payload)}",
        "runtime": common["runtime"],
        "agents": _build_agent_states(),
        "agent_event_store": common["agent_event_store"],
        "governance": common["governance"],
        "edge": _build_edge_summary(),
        "model_budget": common["model_budget"],
        "open_blockers": common["open_blockers"],
        "latest_diagnoses": [],
        "authority": common["authority"],
        "gateway": common["gateway"],
        "request_context": common["request_context"],
    }
    return OpenClawEnvelope(
        ok=(not degraded and status not in {"fail", "degraded"}),
        status=status,
        generated_at_ms=generated_at_ms,
        freshness_ms=runtime.get("snapshot_age_ms"),
        degraded=degraded or status == "degraded",
        degraded_reasons=degraded_reasons,
        evidence_refs=_evidence_refs(generated_at_ms),
        data=data,
        data_category="openclaw_self_state",
    )

from __future__ import annotations

"""
OpenClaw read-only control-plane routes.

MODULE_NOTE (中文):
  MAG-016/MAG-017 只讀基礎層。P1-OPENCLAW-3 擴展 backend-authored
  observability allowlist：status、self-state、brief/latest、diagnostics、
  escalations 五個 GET route。
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

from fastapi import APIRouter, Depends, HTTPException, Request

from . import agents_routes_helpers as _agent_h
from . import main_legacy as base
from .db_pool import get_pg_conn
from .openclaw_authority_contracts import (
    OPENCLAW_CONTEXT_HEADERS as _OPENCLAW_CONTEXT_HEADERS,
    OPENCLAW_PROPOSAL_LEDGER_ROUTES as _OPENCLAW_PROPOSAL_LEDGER_ROUTES,
    OPENCLAW_READ_ONLY_ROUTES as _OPENCLAW_READ_ONLY_ROUTES,
    build_openclaw_authority_posture,
)
from .openclaw_models import (
    OpenClawEnvelope,
    OpenClawEvidenceRef,
    OpenClawProposalCreateRequest,
    OpenClawProposalDecisionRequest,
    OpenClawStatus,
)
from .openclaw_proposal_store import (
    OpenClawProposalStore,
    OpenClawProposalStoreUnavailable,
    OpenClawProposalValidationError,
)
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
_SUPERVISOR_ESCALATION_PURPOSE = "openclaw_supervisor_escalation"


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


def _details_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _safe_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _model_to_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return dict(value.model_dump())
    return dict(value.dict())


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
    return dict(build_openclaw_authority_posture())


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
    extra_source_errors: list[str] | None = None,
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
    for reason in extra_source_errors or []:
        blockers.append(
            {
                "code": reason.split(":", 1)[0],
                "severity": "warn",
                "summary": "Optional OpenClaw read backing source is unavailable.",
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
    route_refs = [
        OpenClawEvidenceRef(
            ref_type="api_route",
            ref_id=f"{method} {path}",
            label=label,
            freshness_ts_ms=generated_at_ms,
            safe_url=path,
        )
        for method, path, label in _OPENCLAW_READ_ONLY_ROUTES
        + _OPENCLAW_PROPOSAL_LEDGER_ROUTES
    ]
    return [
        *route_refs,
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
    extra_source_errors: list[str] | None = None,
) -> tuple[dict[str, Any], OpenClawStatus, bool, list[str]]:
    request_context, request_context_error = _build_request_context(request, actor)
    source_errors = [
        reason
        for reason in (event_store_error, runtime_error, request_context_error)
        if reason
    ]
    source_errors.extend(extra_source_errors or [])
    blockers = _build_blockers(
        event_store=event_store,
        event_store_error=event_store_error,
        runtime_error=runtime_error,
        request_context_error=request_context_error,
        extra_source_errors=extra_source_errors,
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


def _evidence_ref_dict(
    *,
    ref_type: str,
    ref_id: str,
    label: str,
    generated_at_ms: int,
    safe_url: str | None = None,
) -> dict[str, Any]:
    return {
        "ref_type": ref_type,
        "ref_id": ref_id,
        "label": label,
        "freshness_ts_ms": generated_at_ms,
        "safe_url": safe_url,
    }


def _build_latest_brief(
    *,
    common: dict[str, Any],
    status: OpenClawStatus,
    generated_at_ms: int,
) -> dict[str, Any]:
    event_rows = common["agent_event_store"].get("recent_rows", {})
    blockers = common["open_blockers"]
    warnings = [
        {
            "code": blocker["code"],
            "severity": blocker["severity"],
            "summary": blocker["summary"],
        }
        for blocker in blockers
    ]
    if common["agent_event_store"].get("status") == "disabled":
        warnings.append(
            {
                "code": "agent_event_store_disabled",
                "severity": "warn",
                "summary": "Agent event-store health surface is disabled by env.",
            }
        )

    next_actions = [
        {
            "action": "keep_openclaw_read_only",
            "reason": "Proposal, approval, order, config, secret, and deploy lanes are disabled.",
        }
    ]
    if warnings:
        next_actions.append(
            {
                "action": "inspect_degraded_sources",
                "reason": "One or more backing sources are missing, stale, or inferred.",
            }
        )
    if common["model_budget"].get("default_cloud_call_allowed") is False:
        next_actions.append(
            {
                "action": "keep_supervisor_cloud_disabled",
                "reason": common["model_budget"].get("disabled_reason"),
            }
        )

    payload = {
        "status": status,
        "runtime_snapshot_id": common["runtime"].get("snapshot_id"),
        "event_rows": event_rows,
        "warnings": warnings,
    }
    return {
        "brief_id": f"brief_{_hash_snapshot(payload)}",
        "title": "OpenClaw control-plane latest brief",
        "ts_ms": generated_at_ms,
        "status": status,
        "facts": [
            {
                "claim": "OpenClaw has no direct trading, risk-config, live-auth, secret, restart, or deploy authority.",
                "source": "authority_posture",
            },
            {
                "claim": "OpenClaw brief data is backend-authored by the FastAPI control plane.",
                "source": "openclaw_routes",
            },
            {
                "claim": "Recent agent event-store rows are counted from durable agent tables.",
                "source": "agent_event_store",
                "window_minutes": common["agent_event_store"].get("window_minutes"),
                "rows": event_rows,
            },
        ],
        "warnings": warnings,
        "next_actions": next_actions,
        "source_tables": [
            "agent.messages",
            "agent.state_changes",
            "agent.ai_invocations",
        ],
        "route_allowlist": common["authority"]["active_allowlist"],
        "proposal_lane": {
            "creation_endpoint_enabled": False,
            "approval_relay_enabled": False,
            "reason": "deferred_until_explicit_operator_approval",
        },
    }


def _build_diagnostics(
    *,
    common: dict[str, Any],
    status: OpenClawStatus,
    generated_at_ms: int,
) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    route_evidence = _evidence_ref_dict(
        ref_type="api_route",
        ref_id="GET /api/v1/openclaw/diagnostics",
        label="OpenClaw diagnostics view",
        generated_at_ms=generated_at_ms,
        safe_url="/api/v1/openclaw/diagnostics",
    )
    event_evidence = _evidence_ref_dict(
        ref_type="healthcheck",
        ref_id="[52] agent_event_store_rows",
        label="Agent event-store recent row proof",
        generated_at_ms=generated_at_ms,
    )

    domain_by_code = {
        "agent_event_store_unavailable": "data",
        "agent_event_store_zero_rows": "data",
        "agent_event_store_disabled": "data",
        "runtime_snapshot_unavailable": "runtime",
        "request_context_inferred": "gateway",
        "supervisor_escalation_ledger_unavailable": "ai_cost",
    }
    for blocker in common["open_blockers"]:
        code = blocker["code"]
        diagnostics.append(
            {
                "diagnosis_id": f"diag_{_hash_snapshot({'code': code, 'status': status})}",
                "ts_ms": generated_at_ms,
                "severity": blocker["severity"],
                "domain": domain_by_code.get(code, "operator"),
                "status": "open",
                "facts": [blocker["summary"]],
                "inferences": [
                    "OpenClaw read models should be treated as incomplete until this source recovers."
                ],
                "hypotheses": [
                    "The backing source may be unavailable, disabled, idle, or missing required request context."
                ],
                "recommended_action": "verify_backing_source_and_keep_read_only",
                "evidence_refs": [route_evidence, event_evidence],
                "linked_escalation_id": None,
                "linked_proposal_id": None,
            }
        )

    if common["agent_event_store"].get("status") == "disabled":
        diagnostics.append(
            {
                "diagnosis_id": "diag_agent_event_store_disabled",
                "ts_ms": generated_at_ms,
                "severity": "warn",
                "domain": "data",
                "status": "open",
                "facts": ["Agent event-store health check is disabled by env."],
                "inferences": [
                    "OpenClaw cannot use the recent row proof as a hard readiness gate."
                ],
                "hypotheses": ["The deployment may be intentionally running in advisory-only mode."],
                "recommended_action": "enable_event_store_health_when_runtime_row_proof_is_required",
                "evidence_refs": [event_evidence],
                "linked_escalation_id": None,
                "linked_proposal_id": None,
            }
        )

    if not diagnostics:
        diagnostics.append(
            {
                "diagnosis_id": f"diag_openclaw_read_only_{_hash_snapshot({'status': status})}",
                "ts_ms": generated_at_ms,
                "severity": "info",
                "domain": "governance",
                "status": "open",
                "facts": [
                    "The active OpenClaw route allowlist is read-only.",
                    "Proposal creation and approval relay are disabled.",
                ],
                "inferences": [
                    "This surface can observe runtime posture without changing trading authority."
                ],
                "hypotheses": [],
                "recommended_action": "continue_read_only_observation",
                "evidence_refs": [route_evidence],
                "linked_escalation_id": None,
                "linked_proposal_id": None,
            }
        )
    return diagnostics


def _row_to_escalation(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        invocation_id,
        created_at_ms,
        provider,
        model,
        tier,
        prompt_hash,
        success,
        response_summary,
        context_id,
        details,
    ) = row
    detail_payload = _details_dict(details)
    escalation_id = str(
        detail_payload.get("escalation_id")
        or context_id
        or f"esc_ai_{_hash_snapshot({'invocation_id': invocation_id})}"
    )
    source_ids = _safe_list(detail_payload.get("source_observation_ids"))
    budget_decision = detail_payload.get("budget_decision")
    ledger_phase = str(detail_payload.get("ledger_phase") or "")
    status = "invocation_recorded" if ledger_phase == "before_cloud_call" else "responded"
    if success is False and ledger_phase != "before_cloud_call":
        status = "failed"
    return {
        "escalation_id": escalation_id,
        "created_at_ms": int(created_at_ms or 0),
        "trigger_type": str(detail_payload.get("trigger_type") or "operator_requested"),
        "source_observation_ids": source_ids,
        "budget_decision": budget_decision if isinstance(budget_decision, dict) else {},
        "prompt_hash": prompt_hash,
        "input_summary": "Supervisor escalation ledger row from agent.ai_invocations.",
        "model_request": {
            "provider": provider,
            "model": model,
            "tier": tier,
        },
        "ai_invocation_id": invocation_id,
        "response_summary": response_summary,
        "result_diagnosis_ids": _safe_list(detail_payload.get("result_diagnosis_ids")),
        "result_proposal_ids": _safe_list(detail_payload.get("result_proposal_ids")),
        "status": status,
    }


def _read_supervisor_escalation_ledger(
    *,
    limit: int = 20,
) -> tuple[dict[str, Any], str | None]:
    ledger: dict[str, Any] = {
        "source_table": "agent.ai_invocations",
        "purpose": _SUPERVISOR_ESCALATION_PURPOSE,
        "available": False,
        "items": [],
        "recent_count": 0,
    }
    with get_pg_conn() as conn:
        if conn is None:
            return ledger, "supervisor_escalation_ledger_unavailable:pg_unavailable"
        try:
            cur = conn.cursor()
            _set_statement_timeout(cur)
            cur.execute("SELECT to_regclass(%s) IS NOT NULL", ("agent.ai_invocations",))
            row = cur.fetchone()
            if not row or not row[0]:
                ledger["missing_table"] = "agent.ai_invocations"
                return ledger, "supervisor_escalation_ledger_unavailable:missing_table"
            cur.execute(
                """
                SELECT
                    invocation_id,
                    (EXTRACT(EPOCH FROM ts) * 1000)::bigint AS ts_ms,
                    provider,
                    model,
                    tier,
                    prompt_hash,
                    success,
                    response_summary,
                    context_id,
                    details
                  FROM agent.ai_invocations
                 WHERE purpose = %s
                 ORDER BY ts DESC
                 LIMIT %s
                """,
                (_SUPERVISOR_ESCALATION_PURPOSE, int(limit)),
            )
            rows = list(cur.fetchall() or [])
            items = [_row_to_escalation(tuple(item)) for item in rows]
            ledger.update(
                {
                    "available": True,
                    "items": items,
                    "recent_count": len(items),
                }
            )
            return ledger, None
        except Exception as exc:  # noqa: BLE001 - read route degrades, never 5xx
            logger.warning("openclaw supervisor escalation ledger read failed: %s", exc)
            return ledger, _safe_status_reason(
                "supervisor_escalation_ledger_unavailable",
                exc,
            )


def _build_escalations_view(
    *,
    common: dict[str, Any],
    ledger: dict[str, Any],
) -> dict[str, Any]:
    return {
        "creation_endpoint_enabled": False,
        "external_creation_deferred": True,
        "approval_relay_enabled": False,
        "cloud_policy": common["model_budget"],
        "ledger": {
            "source_table": ledger["source_table"],
            "purpose": ledger["purpose"],
            "available": ledger["available"],
            "recent_count": ledger["recent_count"],
        },
        "items": ledger["items"],
        "proposal_side_effect_allowed": False,
        "direct_cloud_call_allowed_from_route": False,
    }


def _get_proposal_store() -> OpenClawProposalStore:
    return OpenClawProposalStore()


def _actor_dict(actor: base.AuthenticatedActor) -> dict[str, Any]:
    return {
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type,
        "roles": sorted(actor.roles),
        "scopes": sorted(actor.scopes),
    }


def _require_complete_write_context(
    request: Request,
    actor: base.AuthenticatedActor,
) -> dict[str, Any]:
    context, context_error = _build_request_context(request, actor)
    if context_error or not context.get("request_id"):
        raise HTTPException(
            status_code=400,
            detail={
                "reason_codes": ["openclaw_request_context_required"],
                "missing": context.get("missing", []),
            },
        )
    return context


def _require_proposal_creator(actor: base.AuthenticatedActor) -> None:
    if not ({"operator", "operator_guarded", "service"} & set(actor.roles)):
        raise HTTPException(
            status_code=403,
            detail={"reason_codes": ["openclaw_proposal_creator_required"]},
        )


def _require_approval_actor(actor: base.AuthenticatedActor) -> None:
    if not ({"operator", "operator_guarded"} & set(actor.roles)):
        raise HTTPException(
            status_code=403,
            detail={"reason_codes": ["openclaw_operator_approval_required"]},
        )


def _resolve_body_request_id(
    *,
    body_request_id: str | None,
    context: dict[str, Any],
) -> str:
    context_request_id = str(context.get("request_id") or "")
    if body_request_id and body_request_id != context_request_id:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": ["openclaw_request_id_mismatch"]},
        )
    return context_request_id


def _write_envelope(
    *,
    data_category: str,
    data: dict[str, Any],
    generated_at_ms: int,
    status: OpenClawStatus = "pass",
    ok: bool = True,
    degraded_reasons: list[str] | None = None,
) -> OpenClawEnvelope:
    degraded = bool(degraded_reasons) or status == "degraded"
    return OpenClawEnvelope(
        ok=ok and status not in {"fail", "degraded"},
        status=status,
        generated_at_ms=generated_at_ms,
        freshness_ms=None,
        degraded=degraded,
        degraded_reasons=degraded_reasons or [],
        evidence_refs=_evidence_refs(generated_at_ms),
        data=data,
        data_category=data_category,
    )


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


@openclaw_router.get("/brief/latest", response_model=OpenClawEnvelope)
async def get_openclaw_brief_latest(
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
        "brief": _build_latest_brief(
            common=common,
            status=status,
            generated_at_ms=generated_at_ms,
        ),
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
        data_category="openclaw_brief_latest",
    )


@openclaw_router.get("/diagnostics", response_model=OpenClawEnvelope)
async def get_openclaw_diagnostics(
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
    diagnostics = _build_diagnostics(
        common=common,
        status=status,
        generated_at_ms=generated_at_ms,
    )
    data = {
        "diagnostics": diagnostics,
        "diagnostic_count": len(diagnostics),
        "authority": common["authority"],
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
        data_category="openclaw_diagnostics",
    )


@openclaw_router.get("/escalations", response_model=OpenClawEnvelope)
async def get_openclaw_escalations(
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    generated_at_ms = _now_ms()
    (
        event_store,
        event_store_error,
        runtime,
        runtime_error,
    ), (ledger, ledger_error) = await asyncio.gather(
        _read_backing_sources(),
        asyncio.to_thread(_read_supervisor_escalation_ledger),
    )
    common, status, degraded, degraded_reasons = _compose_common_payload(
        request=request,
        actor=actor,
        event_store=event_store,
        event_store_error=event_store_error,
        runtime=runtime,
        runtime_error=runtime_error,
        generated_at_ms=generated_at_ms,
        extra_source_errors=[ledger_error] if ledger_error else None,
    )
    data = {
        "escalations": _build_escalations_view(common=common, ledger=ledger),
        "authority": common["authority"],
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
        data_category="openclaw_escalations",
    )


@openclaw_router.get("/proposals", response_model=OpenClawEnvelope)
async def get_openclaw_proposals(
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    generated_at_ms = _now_ms()
    request_context, request_context_error = _build_request_context(request, actor)
    ledger, ledger_error = _get_proposal_store().list_proposals()
    degraded_reasons = [
        reason
        for reason in (request_context_error, ledger_error)
        if reason
    ]
    status: OpenClawStatus = "degraded" if degraded_reasons else "pass"
    data = {
        "proposals": ledger,
        "authority": _build_authority_posture(),
        "request_context": request_context,
        "side_effect_delegation_enabled": False,
    }
    return _write_envelope(
        data_category="openclaw_proposals",
        data=data,
        generated_at_ms=generated_at_ms,
        status=status,
        ok=not degraded_reasons,
        degraded_reasons=degraded_reasons,
    )


@openclaw_router.post("/proposals", response_model=OpenClawEnvelope)
async def create_openclaw_proposal(
    body: OpenClawProposalCreateRequest,
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    _require_proposal_creator(actor)
    context = _require_complete_write_context(request, actor)
    _resolve_body_request_id(body_request_id=body.request_id, context=context)
    generated_at_ms = _now_ms()
    payload = _model_to_dict(body)
    evidence_refs = [
        _model_to_dict(item)
        for item in body.evidence_refs
    ]
    try:
        proposal = _get_proposal_store().create_proposal(
            request_context=context,
            actor=_actor_dict(actor),
            proposal_type=body.proposal_type,
            risk_class=body.risk_class,
            summary=body.summary,
            evidence_refs=evidence_refs,
            required_approval_class=body.required_approval_class,
            expires_at_ms=body.expires_at_ms,
            linked_diagnosis_id=body.linked_diagnosis_id,
            linked_escalation_id=body.linked_escalation_id,
            side_effect_route=body.side_effect_route,
            payload=payload.get("payload") or {},
        )
    except OpenClawProposalValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": [str(exc)]},
        ) from exc
    except OpenClawProposalStoreUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason_codes": ["openclaw_proposal_store_unavailable"], "detail": str(exc)},
        ) from exc

    return _write_envelope(
        data_category="openclaw_proposal_created",
        data={
            "proposal": proposal,
            "request_context": context,
            "side_effect_executed": False,
        },
        generated_at_ms=generated_at_ms,
    )


@openclaw_router.post("/proposals/{proposal_id}/approve", response_model=OpenClawEnvelope)
async def approve_openclaw_proposal(
    proposal_id: str,
    body: OpenClawProposalDecisionRequest,
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    return await _decide_openclaw_proposal(
        proposal_id=proposal_id,
        action="approve",
        body=body,
        request=request,
        actor=actor,
    )


@openclaw_router.post("/proposals/{proposal_id}/reject", response_model=OpenClawEnvelope)
async def reject_openclaw_proposal(
    proposal_id: str,
    body: OpenClawProposalDecisionRequest,
    request: Request,
    actor: base.AuthenticatedActor = Depends(base.current_actor),
) -> OpenClawEnvelope:
    return await _decide_openclaw_proposal(
        proposal_id=proposal_id,
        action="reject",
        body=body,
        request=request,
        actor=actor,
    )


async def _decide_openclaw_proposal(
    *,
    proposal_id: str,
    action: str,
    body: OpenClawProposalDecisionRequest,
    request: Request,
    actor: base.AuthenticatedActor,
) -> OpenClawEnvelope:
    _require_approval_actor(actor)
    context = _require_complete_write_context(request, actor)
    _resolve_body_request_id(body_request_id=body.request_id, context=context)
    generated_at_ms = _now_ms()
    try:
        approval = _get_proposal_store().decide_proposal(
            proposal_id=proposal_id,
            request_context=context,
            actor=_actor_dict(actor),
            action=action,
            reason=body.reason,
        )
    except OpenClawProposalValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail={"reason_codes": [str(exc)]},
        ) from exc
    except OpenClawProposalStoreUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={"reason_codes": ["openclaw_proposal_store_unavailable"], "detail": str(exc)},
        ) from exc
    if approval is None:
        raise HTTPException(
            status_code=404,
            detail={"reason_codes": ["openclaw_proposal_not_found"]},
        )
    decision = approval.get("decision")
    status: OpenClawStatus = "warn" if decision in {"denied", "expired"} else "pass"
    return _write_envelope(
        data_category="openclaw_proposal_decision",
        data={
            "approval": approval,
            "request_context": context,
            "side_effect_executed": False,
            "side_effect_delegation_enabled": False,
        },
        generated_at_ms=generated_at_ms,
        status=status,
        ok=decision not in {"denied", "expired"},
    )

#!/usr/bin/env python3
"""Open a bounded active Decision Lease window and evaluate no-order gates.

This helper is intentionally narrower than admission/execution. With explicit
CLI plus env opt-in it acquires a short-lived Demo TRADE_ENTRY lease for the
current candidate, captures read-only governance state while that lease is
active, evaluates the existing Decision Lease / Guardian gate evidence, and
then releases the lease in a finally block. The resulting artifact proves an
active-window gate check; it does not leave runtime admission or order authority
after the lease is released.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
from pathlib import Path
from typing import Any, Awaitable, Callable, Mapping


_SRV_ROOT = Path(__file__).resolve().parents[3]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))


from cost_gate_learning_lane import (  # noqa: E402
    current_candidate_decision_lease_guardian_gate_evidence as gate_evidence,
)
from cost_gate_learning_lane import (  # noqa: E402
    current_candidate_decision_lease_no_order_validation as lease_validation,
)


SCHEMA_VERSION = "current_candidate_active_decision_lease_gate_window_v1"
ACTIVE_WINDOW_SNAPSHOT_SCHEMA_VERSION = (
    "runtime_governance_ipc_readonly_snapshot_v1"
)

DRY_RUN_READY_STATUS = (
    "CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_DRY_RUN_READY"
)
DONE_STATUS = "CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_DONE_NO_ORDER"
SOURCE_NOT_READY_STATUS = (
    "CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_SOURCE_NOT_READY"
)
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_BLOCKED_BY_LOSS_CONTROL"
)
BLOCKED_BY_RUNTIME_STATUS = (
    "CURRENT_CANDIDATE_ACTIVE_DECISION_LEASE_GATE_WINDOW_BLOCKED_BY_RUNTIME"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

RUN_ENV = "OPENCLAW_CURRENT_CANDIDATE_ACTIVE_LEASE_GATE_WINDOW"
LEASE_SCOPE = lease_validation.LEASE_SCOPE
LEASE_PROFILE = lease_validation.LEASE_PROFILE
LEASE_TTL_SECONDS = lease_validation.LEASE_TTL_SECONDS
LEASE_SOURCE_STAGE = "current_candidate_active_decision_lease_gate_window"

DEFAULT_MAX_GATE_PACKET_AGE_SECONDS = (
    lease_validation.DEFAULT_MAX_GATE_PACKET_AGE_SECONDS
)
DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS = (
    gate_evidence.DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS
)
DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS = (
    gate_evidence.DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS
)
DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS = 30

BOUNDARY = (
    "bounded current-candidate active Decision Lease gate window; one short "
    "Demo governance lease acquire/release, read-only governance snapshot, "
    "no Bybit/private/order/cancel/modify call, no PG read/write, no runtime "
    "config/env/service/crontab mutation, no Cost Gate lowering, no live or "
    "mainnet authority, no order/probe authority after release, and no profit "
    "proof"
)

IPCDispatcher = Callable[..., Awaitable[Mapping[str, Any]]]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"json object required: {path}")
    return payload


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _make_intent_id(candidate: dict[str, Any], now: dt.datetime) -> str:
    raw = (
        f"current_candidate_active_gate_window:"
        f"{candidate.get('strategy_name')}:{candidate.get('symbol')}:"
        f"{candidate.get('side')}:{now.strftime('%Y%m%dT%H%M%SZ')}"
    )
    return re.sub(r"[^A-Za-z0-9:_.-]+", "_", raw)[:180]


def _normalize_method_entry(raw: Any) -> dict[str, Any]:
    if isinstance(raw, Mapping):
        payload = dict(raw)
        if payload.get("ok") is False:
            return payload
        if "result" in payload or "payload" in payload:
            return {"ok": payload.get("ok", True), **payload}
        return {"ok": True, "result": payload}
    if isinstance(raw, list):
        return {"ok": True, "result": list(raw)}
    return {"ok": False, "error": "ipc_result_not_object_or_list"}


def _dispatch_ipc_method(
    *,
    method: str,
    params: Mapping[str, Any] | None = None,
    dispatcher: IPCDispatcher | None = None,
    timeout_seconds: float = 5.0,
) -> dict[str, Any]:
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
        governance_lease_bridge as bridge,
    )
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
        ipc_dispatch,
    )

    dispatch = dispatcher or ipc_dispatch.one_shot_ipc_call
    try:
        raw = bridge._run_async_blocking(  # type: ignore[attr-defined]  # noqa: SLF001
            dispatch(method, dict(params or {}), timeout_seconds),
            timeout=timeout_seconds + 1.0,
        )
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"ipc_dispatch_exception:{type(exc).__name__}"}
    return _normalize_method_entry(raw)


def _method_result(entry: Mapping[str, Any]) -> Any:
    if entry.get("ok") is False:
        return None
    if "result" in entry:
        return entry.get("result")
    if "payload" in entry:
        return entry.get("payload")
    return dict(entry)


def _lease_id_from_payload(payload: Mapping[str, Any]) -> str | None:
    return _str(
        payload.get("lease_id")
        or payload.get("decision_lease_id")
        or _dict(payload.get("metadata")).get("lease_id")
    ) or None


def _expires_at_from_lease(
    *,
    lease: Mapping[str, Any],
    now: dt.datetime,
    ttl_seconds: float,
) -> str:
    for key in ("expires_at_utc", "lease_expires_at_utc", "expires_at"):
        value = _str(lease.get(key))
        if value:
            return value
    for key in ("expires_at_ms", "lease_expires_at_ms", "expiry_ms"):
        number = _float(lease.get(key))
        if number and number > 0:
            seconds = number / 1000.0 if number > 10_000_000_000 else number
            try:
                return dt.datetime.fromtimestamp(
                    seconds,
                    tz=dt.timezone.utc,
                ).isoformat()
            except (OverflowError, OSError, ValueError):
                pass
    return (now + dt.timedelta(seconds=ttl_seconds)).isoformat()


def _lease_list_from_entry(entry: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = _method_result(entry)
    if isinstance(raw, Mapping):
        raw = raw.get("leases") or raw.get("items") or raw.get("result")
    if raw is None:
        return []
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, Mapping)]


def _enrich_active_lease(
    *,
    lease: Mapping[str, Any],
    lease_id: str,
    candidate: dict[str, Any],
    now: dt.datetime,
    ttl_seconds: float,
) -> dict[str, Any]:
    enriched = dict(lease)
    metadata = dict(_dict(enriched.get("metadata")))
    metadata.update(
        {
            "candidate": candidate,
            "environment": metadata.get("environment") or "demo",
            "demo_only": metadata.get("demo_only", True),
            "source_stage": LEASE_SOURCE_STAGE,
            "metadata_enriched_by_helper": True,
        }
    )
    enriched.update(
        {
            "lease_id": lease_id,
            "decision_lease_id": lease_id,
            "state": enriched.get("state") or enriched.get("status") or "ACTIVE",
            "status": enriched.get("status") or enriched.get("state") or "ACTIVE",
            "scope": enriched.get("scope") or LEASE_SCOPE,
            "environment": enriched.get("environment") or "demo",
            "demo_only": enriched.get("demo_only", True),
            "candidate": candidate,
            "expires_at_utc": _expires_at_from_lease(
                lease=enriched,
                now=now,
                ttl_seconds=ttl_seconds,
            ),
            "metadata": metadata,
        }
    )
    return enriched


def _build_active_runtime_snapshot(
    *,
    lease_id: str,
    candidate: dict[str, Any],
    now: dt.datetime,
    ttl_seconds: float,
    dispatcher: IPCDispatcher | None,
    timeout_seconds: float,
) -> tuple[dict[str, Any], list[str]]:
    reasons: list[str] = []
    get_status = _dispatch_ipc_method(
        method="governance.get_status",
        dispatcher=dispatcher,
        timeout_seconds=timeout_seconds,
    )
    list_leases = _dispatch_ipc_method(
        method="governance.list_leases",
        dispatcher=dispatcher,
        timeout_seconds=timeout_seconds,
    )
    get_risk_state = _dispatch_ipc_method(
        method="governance.get_risk_state",
        dispatcher=dispatcher,
        timeout_seconds=timeout_seconds,
    )

    for method, entry in (
        ("governance.get_status", get_status),
        ("governance.list_leases", list_leases),
        ("governance.get_risk_state", get_risk_state),
    ):
        if entry.get("ok") is False:
            reasons.append(f"{method}_not_ok")

    leases = _lease_list_from_entry(list_leases)
    selected = next(
        (lease for lease in leases if _lease_id_from_payload(lease) == lease_id),
        None,
    )
    get_lease = None
    if selected is None:
        get_lease = _dispatch_ipc_method(
            method="governance.get_lease",
            params={"lease_id": lease_id},
            dispatcher=dispatcher,
            timeout_seconds=timeout_seconds,
        )
        if get_lease.get("ok") is False:
            reasons.append("governance.get_lease_not_ok")
        raw_get_lease = _method_result(get_lease)
        if isinstance(raw_get_lease, Mapping) and _lease_id_from_payload(raw_get_lease) == lease_id:
            selected = dict(raw_get_lease)

    if selected is None:
        reasons.append("active_lease_not_visible_in_runtime_snapshot")
    else:
        enriched = _enrich_active_lease(
            lease=selected,
            lease_id=lease_id,
            candidate=candidate,
            now=now,
            ttl_seconds=ttl_seconds,
        )
        replaced = False
        next_leases: list[dict[str, Any]] = []
        for lease in leases:
            if _lease_id_from_payload(lease) == lease_id:
                next_leases.append(enriched)
                replaced = True
            else:
                next_leases.append(lease)
        if not replaced:
            next_leases.append(enriched)
        leases = next_leases
        list_leases = {"ok": True, "result": leases}

    status_result = _method_result(get_status)
    if isinstance(status_result, Mapping):
        status_payload = dict(status_result)
        status_payload["lease_live_count"] = max(
            int(_float(status_payload.get("lease_live_count")) or 0),
            len(leases),
        )
        get_status = {"ok": True, "result": status_payload}

    snapshot = {
        "schema_version": ACTIVE_WINDOW_SNAPSHOT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": "RUNTIME_GOVERNANCE_IPC_READONLY_SNAPSHOT_READY",
        "source": "active_decision_lease_gate_window_runtime_reads",
        "active_window": {
            "lease_id": lease_id,
            "candidate": candidate,
            "lease_scope": LEASE_SCOPE,
            "lease_profile": LEASE_PROFILE,
            "lease_ttl_seconds": ttl_seconds,
            "metadata_enriched_by_helper": selected is not None,
            "lease_acquired_before_snapshot": True,
            "lease_release_pending_at_snapshot": True,
        },
        "methods": {
            "governance.get_status": get_status,
            "governance.list_leases": list_leases,
            "governance.get_risk_state": get_risk_state,
        },
        "answers": {
            "runtime_readonly_ipc_call_performed": True,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "live_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
        },
        "boundary": (
            "snapshot uses read-only governance IPC calls captured inside a "
            "separately audited bounded active lease window"
        ),
    }
    return snapshot, sorted(set(reasons))


def _acquire_active_lease(
    *,
    intent_id: str,
    ttl_seconds: float,
    dispatcher: IPCDispatcher | None,
    timeout_seconds: float,
) -> str | None:
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
        governance_lease_bridge as bridge,
    )

    lease_id = bridge.acquire_lease_via_ipc(
        intent_id=intent_id,
        scope=LEASE_SCOPE,
        ttl_seconds=ttl_seconds,
        profile=LEASE_PROFILE,
        source_stage=LEASE_SOURCE_STAGE,
        timeout_seconds=timeout_seconds,
        dispatcher=dispatcher,
    )
    if lease_id == "bypass":
        return None
    return lease_id


def _release_active_lease(
    *,
    lease_id: str,
    dispatcher: IPCDispatcher | None,
    timeout_seconds: float,
) -> bool:
    from program_code.exchange_connectors.bybit_connector.control_api_v1.app import (  # noqa: PLC0415
        governance_lease_bridge as bridge,
    )

    return bridge.release_lease_via_ipc(
        lease_id=lease_id,
        consumed=False,
        timeout_seconds=timeout_seconds,
        dispatcher=dispatcher,
    )


def _source_preflight(
    *,
    gate_packet: dict[str, Any],
    sizing_proposal: dict[str, Any],
    now_utc: dt.datetime,
    max_gate_packet_age_seconds: int,
    max_sizing_proposal_age_seconds: int,
    source_head: str | None,
    runtime_head: str | None,
) -> dict[str, Any]:
    return lease_validation.build_current_candidate_decision_lease_no_order_validation(
        gate_packet=gate_packet,
        sizing_proposal=sizing_proposal,
        run=False,
        require_env=False,
        now_utc=now_utc,
        max_gate_packet_age_seconds=max_gate_packet_age_seconds,
        max_sizing_proposal_age_seconds=max_sizing_proposal_age_seconds,
        source_head=source_head,
        runtime_head=runtime_head,
    )


def _artifact_summary(path: Path | None, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "generated_at_utc": payload.get("generated_at_utc"),
    }


def build_current_candidate_active_decision_lease_gate_window(
    *,
    admission_review: dict[str, Any] | None,
    gate_packet: dict[str, Any] | None,
    sizing_proposal: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    run: bool = False,
    require_env: bool = True,
    now_utc: dt.datetime | None = None,
    lease_ttl_seconds: float = LEASE_TTL_SECONDS,
    timeout_seconds: float = 5.0,
    max_admission_review_age_seconds: int = DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS,
    max_gate_packet_age_seconds: int = DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    max_runtime_snapshot_age_seconds: int = DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS,
    max_sizing_proposal_age_seconds: int = DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS,
    source_head: str | None = None,
    runtime_head: str | None = None,
    dispatcher: IPCDispatcher | None = None,
) -> dict[str, Any]:
    if lease_ttl_seconds <= 0 or lease_ttl_seconds > 10:
        raise ValueError("lease_ttl_seconds must be in (0, 10]")
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("timeout_seconds must be in (0, 30]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    paths = paths or {}
    admission = _dict(admission_review)
    gate = _dict(gate_packet)
    proposal = _dict(sizing_proposal)
    preflight = _source_preflight(
        gate_packet=gate,
        sizing_proposal=proposal,
        now_utc=now,
        max_gate_packet_age_seconds=max_gate_packet_age_seconds,
        max_sizing_proposal_age_seconds=max_sizing_proposal_age_seconds,
        source_head=source_head,
        runtime_head=runtime_head,
    )
    candidate = _candidate_identity(_dict(preflight.get("candidate")) or _dict(gate.get("candidate")))
    intent_id = _make_intent_id(candidate, now)

    source_reasons: list[str] = []
    runtime_reasons: list[str] = []
    if preflight.get("status") != lease_validation.DRY_RUN_READY_STATUS:
        source_reasons.extend(_list(preflight.get("source_blockers")))
        if preflight.get("status") == lease_validation.AUTHORITY_BOUNDARY_VIOLATION_STATUS:
            source_reasons.append("source_preflight_authority_boundary_violation")
        if not source_reasons:
            source_reasons.append("source_preflight_not_ready")
    if not candidate.get("side_cell_key"):
        source_reasons.append("candidate_missing")

    lease_id: str | None = None
    release_ok = False
    active_snapshot: dict[str, Any] | None = None
    active_gate_packet: dict[str, Any] | None = None
    mutation_performed = False

    if not run:
        status = DRY_RUN_READY_STATUS if not source_reasons else SOURCE_NOT_READY_STATUS
        reason = (
            "dry_run_ready_for_explicit_active_lease_gate_window"
            if not source_reasons
            else "source_preflight_not_ready"
        )
    elif source_reasons:
        status = SOURCE_NOT_READY_STATUS
        reason = "source_preflight_not_ready"
    elif require_env and os.environ.get(RUN_ENV) != "1":
        status = SOURCE_NOT_READY_STATUS
        reason = f"{RUN_ENV}_not_set"
        source_reasons.append(f"{RUN_ENV}_not_set")
    else:
        try:
            lease_id = _acquire_active_lease(
                intent_id=intent_id,
                ttl_seconds=lease_ttl_seconds,
                dispatcher=dispatcher,
                timeout_seconds=timeout_seconds,
            )
            mutation_performed = lease_id is not None
            if lease_id is None:
                runtime_reasons.append("lease_acquire_failed")
            else:
                active_snapshot, snapshot_reasons = _build_active_runtime_snapshot(
                    lease_id=lease_id,
                    candidate=candidate,
                    now=now,
                    ttl_seconds=lease_ttl_seconds,
                    dispatcher=dispatcher,
                    timeout_seconds=timeout_seconds,
                )
                runtime_reasons.extend(snapshot_reasons)
                active_gate_packet = gate_evidence.build_current_candidate_decision_lease_guardian_gate_evidence(
                    admission_review=admission,
                    runtime_governance_snapshot=active_snapshot,
                    sizing_proposal=proposal,
                    paths={
                        "admission_review": paths.get("admission_review"),
                        "runtime_governance_snapshot": None,
                        "sizing_proposal": paths.get("sizing_proposal"),
                    },
                    now_utc=now,
                    max_admission_review_age_seconds=max_admission_review_age_seconds,
                    max_runtime_snapshot_age_seconds=max_runtime_snapshot_age_seconds,
                    max_sizing_proposal_age_seconds=max_sizing_proposal_age_seconds,
                    source_head=source_head,
                    runtime_head=runtime_head,
                )
        finally:
            if lease_id:
                release_ok = _release_active_lease(
                    lease_id=lease_id,
                    dispatcher=dispatcher,
                    timeout_seconds=timeout_seconds,
                )
                if not release_ok:
                    runtime_reasons.append("lease_release_failed")

        if runtime_reasons:
            status = BLOCKED_BY_RUNTIME_STATUS
            reason = "active_lease_window_runtime_check_failed"
        elif not active_gate_packet:
            status = BLOCKED_BY_RUNTIME_STATUS
            reason = "active_gate_packet_missing"
            runtime_reasons.append("active_gate_packet_missing")
        elif active_gate_packet.get("status") == gate_evidence.READY_NO_ORDER_STATUS:
            status = DONE_STATUS
            reason = "active_decision_lease_and_guardian_gate_validated_no_order"
        elif active_gate_packet.get("status") == gate_evidence.AUTHORITY_BOUNDARY_VIOLATION_STATUS:
            status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
            reason = "active_gate_packet_authority_boundary_violation"
        else:
            status = BLOCKED_BY_LOSS_CONTROL_STATUS
            reason = "active_window_gate_not_ready"

    active_gate_status = active_gate_packet.get("status") if active_gate_packet else None
    lease_released = mutation_performed and release_ok
    risk_context = dict(_dict(preflight.get("risk_context")))
    if (
        risk_context.get("resolved_cap_usdt") is None
        and risk_context.get("gui_resolved_cap_usdt") is not None
    ):
        risk_context["resolved_cap_usdt"] = risk_context.get("gui_resolved_cap_usdt")
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": candidate,
        "source_head": source_head,
        "runtime_head": runtime_head,
        "artifacts": {
            "admission_review": _artifact_summary(
                paths.get("admission_review"),
                admission,
            ),
            "gate_packet": _artifact_summary(paths.get("gate_packet"), gate),
            "sizing_proposal": _artifact_summary(
                paths.get("sizing_proposal"),
                proposal,
            ),
        },
        "source_preflight": preflight,
        "source_blockers": sorted(set(source_reasons)),
        "runtime_blockers": sorted(set(runtime_reasons)),
        "blocking_gates": sorted(set(source_reasons + runtime_reasons)),
        "active_window": {
            "intent_id": intent_id,
            "lease_id": lease_id,
            "lease_scope": LEASE_SCOPE,
            "lease_profile": LEASE_PROFILE,
            "lease_ttl_seconds": lease_ttl_seconds,
            "source_stage": LEASE_SOURCE_STAGE,
            "acquire_ok": mutation_performed,
            "release_ok": release_ok if mutation_performed else False,
            "released_outcome": "Failed",
            "gate_evidence_status_during_active_window": active_gate_status,
            "lease_released_before_artifact": lease_released,
        },
        "risk_context": risk_context,
        "active_runtime_governance_snapshot": active_snapshot,
        "active_window_gate_evidence": active_gate_packet,
        "answers": {
            "review_contract_ready": not source_reasons and not runtime_reasons,
            "gate_evidence_ready_during_active_window": active_gate_status
            == gate_evidence.READY_NO_ORDER_STATUS,
            "runtime_admission_ready": False,
            "runtime_admission_ready_after_release": False,
            "order_admission_ready": False,
            "governance_lease_mutation_performed": mutation_performed,
            "decision_lease_acquire_performed": mutation_performed,
            "decision_lease_release_performed": lease_released,
            "decision_lease_emitted": False,
            "lease_released_before_artifact": lease_released,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "order_submission_performed": False,
            "order_cancel_performed": False,
            "order_modify_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "service_restart_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "cost_gate_lowering_performed": False,
            "live_authority_granted": False,
            "mainnet_authority_granted": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    active = _dict(packet.get("active_window"))
    answers = _dict(packet.get("answers"))
    risk = _dict(packet.get("risk_context"))
    lines = [
        "# Current Candidate Active Decision Lease Gate Window",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{packet.get('candidate', {}).get('side_cell_key')}`",
        f"- Lease id: `{active.get('lease_id')}`",
        f"- Acquire/release ok: `{active.get('acquire_ok')}` / `{active.get('release_ok')}`",
        f"- Gate status during active window: `{active.get('gate_evidence_status_during_active_window')}`",
        f"- Runtime admission ready after release: `{answers.get('runtime_admission_ready_after_release')}`",
        f"- GUI resolved cap USDT: `{risk.get('resolved_cap_usdt')}`",
        f"- Single-position budget USDT: `{risk.get('single_position_budget_usdt')}`",
        f"- Effective single-order cap USDT: `{risk.get('effective_single_order_cap_usdt')}`",
        "",
        "## Blockers",
    ]
    blockers = _list(packet.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", packet.get("boundary", "")])
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-review-json", type=Path, required=True)
    parser.add_argument("--gate-packet-json", type=Path, required=True)
    parser.add_argument("--sizing-proposal-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--active-runtime-snapshot-json-output", type=Path)
    parser.add_argument("--active-gate-evidence-json-output", type=Path)
    parser.add_argument("--source-head")
    parser.add_argument("--runtime-head")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--lease-ttl-seconds", type=float, default=LEASE_TTL_SECONDS)
    parser.add_argument("--timeout-seconds", type=float, default=5.0)
    parser.add_argument(
        "--max-admission-review-age-seconds",
        type=int,
        default=DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-gate-packet-age-seconds",
        type=int,
        default=DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-runtime-snapshot-age-seconds",
        type=int,
        default=DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-sizing-proposal-age-seconds",
        type=int,
        default=DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS,
    )
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.run and not args.yes:
        raise SystemExit("--run requires --yes")
    if args.run and os.environ.get(RUN_ENV) != "1":
        raise SystemExit(f"--run requires {RUN_ENV}=1")

    packet = build_current_candidate_active_decision_lease_gate_window(
        admission_review=_read_json(args.admission_review_json),
        gate_packet=_read_json(args.gate_packet_json),
        sizing_proposal=_read_json(args.sizing_proposal_json),
        paths={
            "admission_review": args.admission_review_json,
            "gate_packet": args.gate_packet_json,
            "sizing_proposal": args.sizing_proposal_json,
        },
        run=args.run,
        require_env=True,
        lease_ttl_seconds=args.lease_ttl_seconds,
        timeout_seconds=args.timeout_seconds,
        max_admission_review_age_seconds=args.max_admission_review_age_seconds,
        max_gate_packet_age_seconds=args.max_gate_packet_age_seconds,
        max_runtime_snapshot_age_seconds=args.max_runtime_snapshot_age_seconds,
        max_sizing_proposal_age_seconds=args.max_sizing_proposal_age_seconds,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.active_runtime_snapshot_json_output and packet.get(
        "active_runtime_governance_snapshot"
    ):
        _write_json(
            args.active_runtime_snapshot_json_output,
            packet["active_runtime_governance_snapshot"],
        )
    if args.active_gate_evidence_json_output and packet.get("active_window_gate_evidence"):
        _write_json(
            args.active_gate_evidence_json_output,
            packet["active_window_gate_evidence"],
        )
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if packet["status"] in {DRY_RUN_READY_STATUS, DONE_STATUS} else 1


if __name__ == "__main__":
    raise SystemExit(main())

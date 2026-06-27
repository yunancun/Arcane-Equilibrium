#!/usr/bin/env python3
"""Refresh actual-admission BBO inside a bounded active Decision Lease window.

This helper is a no-order bridge between the public quote construction refresh
and the active Decision Lease / Guardian gate check. With explicit CLI plus env
opt-in it acquires one short Demo TRADE_ENTRY lease, captures public BBO and
instrument data while the lease is live, evaluates the read-only gate evidence
in that same live window, and releases the lease in a finally block.
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
from typing import Any, Callable


_SRV_ROOT = Path(__file__).resolve().parents[3]
if str(_SRV_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRV_ROOT))


from cost_gate_learning_lane import (  # noqa: E402
    current_candidate_active_decision_lease_gate_window as active_lease_window,
)
from cost_gate_learning_lane import (  # noqa: E402
    current_candidate_decision_lease_guardian_gate_evidence as gate_evidence,
)
from cost_gate_learning_lane import (  # noqa: E402
    current_candidate_decision_lease_no_order_validation as lease_validation,
)
from cost_gate_learning_lane import (  # noqa: E402
    current_candidate_public_quote_construction_refresh as quote_refresh,
)


SCHEMA_VERSION = "current_candidate_actual_admission_bbo_lease_window_v1"

DRY_RUN_READY_STATUS = (
    "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DRY_RUN_READY"
)
DONE_STATUS = (
    "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_DONE_NO_ORDER"
)
SOURCE_NOT_READY_STATUS = (
    "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_SOURCE_NOT_READY"
)
BLOCKED_BY_LOSS_CONTROL_STATUS = (
    "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_BLOCKED_BY_LOSS_CONTROL"
)
BLOCKED_BY_RUNTIME_STATUS = (
    "CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW_BLOCKED_BY_RUNTIME"
)
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

RUN_ENV = "OPENCLAW_CURRENT_CANDIDATE_ACTUAL_ADMISSION_BBO_LEASE_WINDOW"
LEASE_SCOPE = lease_validation.LEASE_SCOPE
LEASE_PROFILE = lease_validation.LEASE_PROFILE
LEASE_TTL_SECONDS = lease_validation.LEASE_TTL_SECONDS
LEASE_SOURCE_STAGE = "current_candidate_actual_admission_bbo_lease_window"

DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS = (
    gate_evidence.DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS
)
DEFAULT_MAX_GATE_PACKET_AGE_SECONDS = (
    lease_validation.DEFAULT_MAX_GATE_PACKET_AGE_SECONDS
)
DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS = 30
DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS = (
    lease_validation.DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS
)
DEFAULT_MAX_ENVELOPE_AGE_SECONDS = quote_refresh.DEFAULT_MAX_ENVELOPE_AGE_SECONDS
DEFAULT_MAX_FRESH_BBO_AGE_MS = quote_refresh.DEFAULT_MAX_FRESH_BBO_AGE_MS

BOUNDARY = (
    "bounded current-candidate actual-admission BBO lease window; one short "
    "Demo governance lease acquire/release plus public Bybit market-data GETs "
    "only, no Bybit/private/order/cancel/modify call, no PG read/write, no "
    "runtime config/env/service/crontab mutation, no Cost Gate lowering, no "
    "live or mainnet authority, no order/probe authority after release, and no "
    "profit proof"
)

NowFn = Callable[[], dt.datetime]
MonotonicFn = Callable[[], float]
Opener = Callable[..., Any]


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


def _same_float(left: Any, right: Any, tolerance: float = 1e-8) -> bool:
    left_num = _float(left)
    right_num = _float(right)
    return (
        left_num is not None
        and right_num is not None
        and abs(left_num - right_num) <= tolerance
    )


def _stale_local_10_cap_mismatch(candidate_cap: Any, envelope_cap: Any) -> bool:
    return (
        _same_float(candidate_cap, 10.0, tolerance=1e-9)
        and _float(envelope_cap) is not None
        and not _same_float(candidate_cap, envelope_cap, tolerance=1e-6)
    )


def _candidate_identity(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "side_cell_key": candidate.get("side_cell_key"),
        "strategy_name": candidate.get("strategy_name"),
        "symbol": candidate.get("symbol"),
        "side": candidate.get("side"),
        "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
    }


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, Any, Any, Any, Any]:
    return (
        candidate.get("side_cell_key"),
        candidate.get("strategy_name"),
        candidate.get("symbol"),
        candidate.get("side"),
        candidate.get("outcome_horizon_minutes"),
    )


def _candidate_aligned(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return bool(left.get("side_cell_key")) and _candidate_key(left) == _candidate_key(right)


def _make_intent_id(candidate: dict[str, Any], now: dt.datetime) -> str:
    raw = (
        f"current_candidate_actual_admission_bbo_window:"
        f"{candidate.get('strategy_name')}:{candidate.get('symbol')}:"
        f"{candidate.get('side')}:{now.strftime('%Y%m%dT%H%M%SZ')}"
    )
    return re.sub(r"[^A-Za-z0-9:_.-]+", "_", raw)[:180]


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


def _artifact_summary(path: Path | None, payload: dict[str, Any] | None) -> dict[str, Any]:
    data = _dict(payload)
    return {
        "path": str(path) if path else None,
        "sha256": _sha256(path),
        "schema_version": data.get("schema_version"),
        "status": data.get("status"),
        "generated_at_utc": data.get("generated_at_utc"),
    }


def _source_preflight(
    *,
    admission_review: dict[str, Any],
    gate_packet: dict[str, Any],
    sizing_proposal: dict[str, Any],
    current_candidate_envelope: dict[str, Any],
    now_utc: dt.datetime,
    max_gate_packet_age_seconds: int,
    max_sizing_proposal_age_seconds: int,
    max_envelope_age_seconds: int,
    source_head: str | None,
    runtime_head: str | None,
) -> dict[str, Any]:
    lease_preflight = (
        lease_validation.build_current_candidate_decision_lease_no_order_validation(
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
    )
    envelope_candidate, envelope_reasons = (
        quote_refresh._validate_current_candidate_envelope(  # noqa: SLF001
            current_candidate_envelope,
            now_utc=now_utc,
            max_envelope_age_seconds=max_envelope_age_seconds,
        )
    )
    lease_candidate = _candidate_identity(_dict(lease_preflight.get("candidate")))
    if not lease_candidate.get("side_cell_key"):
        lease_candidate = _candidate_identity(_dict(gate_packet.get("candidate")))
    candidate = lease_candidate if lease_candidate.get("side_cell_key") else envelope_candidate

    reasons: list[str] = []
    authority_reasons: list[str] = []
    if lease_preflight.get("status") != lease_validation.DRY_RUN_READY_STATUS:
        reasons.extend(_list(lease_preflight.get("source_blockers")))
        if lease_preflight.get("status") == lease_validation.AUTHORITY_BOUNDARY_VIOLATION_STATUS:
            authority_reasons.append("lease_preflight_authority_boundary_violation")
        if not reasons:
            reasons.append("lease_preflight_not_ready")
    reasons.extend(envelope_reasons)
    authority_reasons.extend(
        reason
        for reason in envelope_reasons
        if "authority" in reason or "mutation" in reason
    )
    if not _candidate_aligned(candidate, envelope_candidate):
        reasons.append("current_candidate_envelope_candidate_mismatch")

    risk_context = dict(_dict(lease_preflight.get("risk_context")))
    admission_reasons = (
        gate_evidence._admission_source_reasons(admission_review)  # noqa: SLF001
        if admission_review
        else ["admission_review_missing"]
    )
    reasons.extend(admission_reasons)
    authority_reasons.extend(
        reason
        for reason in admission_reasons
        if "authority" in reason or "mutation" in reason
    )
    admission_context = (
        gate_evidence._extract_admission_context(admission_review)  # noqa: SLF001
        if admission_review
        else {}
    )
    admission_candidate = _dict(admission_context.get("candidate"))
    if not _candidate_aligned(candidate, admission_candidate):
        reasons.append("admission_review_candidate_mismatch")

    cap_resolution = _dict(current_candidate_envelope.get("cap_resolution"))
    envelope_cap = _float(cap_resolution.get("resolved_cap_usdt"))
    gate_cap = _float(
        risk_context.get("resolved_cap_usdt")
        or risk_context.get("gui_resolved_cap_usdt")
    )
    admission_cap = _float(admission_context.get("resolved_cap_usdt"))
    if not _same_float(envelope_cap, gate_cap, tolerance=1e-6):
        reasons.append("current_candidate_envelope_cap_mismatch_gate_packet")
    if _stale_local_10_cap_mismatch(gate_cap, envelope_cap):
        reasons.append("gate_packet_stale_local_10_usdt_cap_mismatch_gui_envelope")
    if not _same_float(envelope_cap, admission_cap, tolerance=1e-6):
        reasons.append("admission_review_cap_mismatch_current_candidate_envelope")
    if _stale_local_10_cap_mismatch(admission_cap, envelope_cap):
        reasons.append("admission_review_stale_local_10_usdt_cap_mismatch_gui_envelope")
    if not _same_float(
        cap_resolution.get("account_equity_usdt"),
        risk_context.get("account_equity_usdt"),
        tolerance=1e-6,
    ):
        reasons.append("account_equity_usdt_mismatch_gate_packet")
    if not _same_float(
        cap_resolution.get("account_equity_usdt"),
        admission_context.get("account_equity_usdt"),
        tolerance=1e-6,
    ):
        reasons.append("admission_review_account_equity_usdt_mismatch")
    if not _same_float(
        cap_resolution.get("per_trade_budget_usdt"),
        risk_context.get("per_trade_budget_usdt"),
        tolerance=1e-6,
    ):
        reasons.append("per_trade_budget_usdt_mismatch_gate_packet")
    if not _same_float(
        cap_resolution.get("per_trade_budget_usdt"),
        admission_context.get("per_trade_budget_usdt"),
        tolerance=1e-6,
    ):
        reasons.append("admission_review_per_trade_budget_usdt_mismatch")
    if not _same_float(
        cap_resolution.get("single_position_budget_usdt"),
        risk_context.get("single_position_budget_usdt"),
        tolerance=1e-6,
    ):
        reasons.append("single_position_budget_usdt_mismatch_gate_packet")
    if not _same_float(
        cap_resolution.get("single_position_budget_usdt"),
        admission_context.get("single_position_budget_usdt"),
        tolerance=1e-6,
    ):
        reasons.append("admission_review_single_position_budget_usdt_mismatch")
    if not _same_float(
        cap_resolution.get("per_trade_risk_pct_fraction"),
        risk_context.get("per_trade_risk_pct_fraction"),
        tolerance=1e-8,
    ):
        reasons.append("per_trade_risk_pct_fraction_mismatch_gate_packet")
    if not _same_float(
        cap_resolution.get("per_trade_risk_pct_fraction"),
        admission_context.get("per_trade_risk_pct_fraction"),
        tolerance=1e-8,
    ):
        reasons.append("admission_review_per_trade_risk_pct_fraction_mismatch")
    if not _same_float(
        cap_resolution.get("per_trade_risk_pct_display"),
        admission_context.get("per_trade_risk_pct_display"),
        tolerance=1e-8,
    ):
        reasons.append("admission_review_per_trade_risk_pct_display_mismatch")
    if not _same_float(
        cap_resolution.get("position_size_max_pct"),
        risk_context.get("position_size_max_pct"),
        tolerance=1e-8,
    ):
        reasons.append("position_size_max_pct_mismatch_gate_packet")
    if not _same_float(
        cap_resolution.get("position_size_max_pct"),
        admission_context.get("position_size_max_pct"),
        tolerance=1e-8,
    ):
        reasons.append("admission_review_position_size_max_pct_mismatch")

    status = (
        AUTHORITY_BOUNDARY_VIOLATION_STATUS
        if authority_reasons
        else DRY_RUN_READY_STATUS
        if not reasons
        else SOURCE_NOT_READY_STATUS
    )
    return {
        "schema_version": "current_candidate_actual_admission_bbo_source_preflight_v1",
        "generated_at_utc": now_utc.isoformat(),
        "status": status,
        "candidate": candidate,
        "lease_preflight_status": lease_preflight.get("status"),
        "lease_preflight": lease_preflight,
        "admission_review_status": admission_review.get("status"),
        "admission_context": admission_context,
        "current_candidate_envelope_status": current_candidate_envelope.get("status"),
        "current_candidate_envelope_candidate": envelope_candidate,
        "cap_resolution": cap_resolution,
        "risk_context": risk_context,
        "source_blockers": sorted(set(reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
    }


def _min_positive(*values: Any) -> float | None:
    parsed = [
        value
        for value in (_float(item) for item in values)
        if value is not None and value > 0
    ]
    return min(parsed) if parsed else None


def _actual_bbo_sizing_proposal(
    *,
    quote_packet: dict[str, Any],
    base_sizing_proposal: dict[str, Any],
    candidate: dict[str, Any],
    generated_at_utc: dt.datetime,
) -> dict[str, Any]:
    """Build a no-authority sizing proposal from the actual admission BBO shape."""
    summary = _dict(quote_packet.get("summary"))
    construction = _dict(
        _dict(_dict(quote_packet).get("construction_preview")).get("construction")
    )
    base_risk = _dict(base_sizing_proposal.get("risk_context"))
    base_sizing = _dict(base_sizing_proposal.get("sizing_proposal"))

    resolved_cap = _float(summary.get("resolved_cap_usdt")) or _float(
        base_risk.get("gui_resolved_cap_usdt")
    )
    single_position_budget = _float(
        summary.get("single_position_budget_usdt")
    ) or _float(base_risk.get("single_position_budget_usdt"))
    max_order_notional = _float(summary.get("max_order_notional_usdt"))
    if max_order_notional is None:
        max_order_notional = _float(base_risk.get("max_order_notional_usdt"))
    guardian_adjusted_cap = _float(base_risk.get("guardian_adjusted_cap_usdt"))
    if guardian_adjusted_cap is None:
        guardian_adjusted_cap = _float(
            summary.get("effective_single_order_cap_usdt")
        ) or resolved_cap
    effective_cap = _min_positive(
        resolved_cap,
        single_position_budget,
        guardian_adjusted_cap,
        max_order_notional if max_order_notional and max_order_notional > 0 else None,
    )

    rounded_qty = _float(construction.get("rounded_qty"))
    rounded_notional = _float(construction.get("rounded_notional_usdt"))
    min_notional = _float(construction.get("min_notional"))

    return {
        "schema_version": gate_evidence.SIZING_PROPOSAL_SCHEMA_VERSION,
        "generated_at_utc": generated_at_utc.isoformat(),
        "status": gate_evidence.SIZING_PROPOSAL_READY_STATUS,
        "candidate": candidate,
        "source_blockers": [],
        "authority_contamination_reasons": [],
        "risk_context": {
            **base_risk,
            "sizing_source": "actual_admission_bbo_construction",
            "gui_risk_config_is_source_of_truth": True,
            "risk_source_of_truth": summary.get("risk_source_of_truth")
            or base_risk.get("risk_source_of_truth"),
            "cap_source": summary.get("cap_source") or base_risk.get("cap_source"),
            "account_equity_usdt": summary.get("account_equity_usdt")
            or base_risk.get("account_equity_usdt"),
            "gui_resolved_cap_usdt": resolved_cap,
            "per_trade_risk_pct_fraction": summary.get(
                "per_trade_risk_pct_fraction"
            )
            or base_risk.get("per_trade_risk_pct_fraction"),
            "per_trade_risk_pct_display": summary.get("per_trade_risk_pct_display")
            or base_risk.get("per_trade_risk_pct_display"),
            "position_size_max_pct": summary.get("position_size_max_pct")
            or base_risk.get("position_size_max_pct"),
            "per_trade_budget_usdt": summary.get("per_trade_budget_usdt")
            or base_risk.get("per_trade_budget_usdt"),
            "single_position_budget_usdt": single_position_budget,
            "max_order_notional_usdt": max_order_notional,
            "guardian_adjusted_cap_usdt": guardian_adjusted_cap,
            "original_rounded_qty": base_sizing.get("proposed_rounded_qty")
            or base_sizing.get("original_rounded_qty"),
            "original_rounded_notional_usdt": base_sizing.get(
                "proposed_rounded_notional_usdt"
            )
            or base_sizing.get("original_rounded_notional_usdt"),
            "local_10_usdt_cap_is_global_risk_authority": False,
        },
        "sizing_proposal": {
            "limit_price": construction.get("limit_price"),
            "qty_step": construction.get("qty_step"),
            "min_notional": min_notional,
            "single_position_budget_usdt": single_position_budget,
            "effective_single_order_cap_usdt": effective_cap,
            "proposed_rounded_qty": rounded_qty,
            "proposed_rounded_notional_usdt": rounded_notional,
            "original_rounded_qty": base_sizing.get("proposed_rounded_qty")
            or base_sizing.get("original_rounded_qty"),
            "original_rounded_notional_usdt": base_sizing.get(
                "proposed_rounded_notional_usdt"
            )
            or base_sizing.get("original_rounded_notional_usdt"),
            "notional_lte_guardian_adjusted_cap": (
                rounded_notional is not None
                and guardian_adjusted_cap is not None
                and rounded_notional <= guardian_adjusted_cap + 1e-8
            ),
            "notional_lte_gui_resolved_cap": (
                rounded_notional is not None
                and resolved_cap is not None
                and rounded_notional <= resolved_cap + 1e-8
            ),
            "notional_lte_single_position_budget": (
                rounded_notional is not None
                and single_position_budget is not None
                and rounded_notional <= single_position_budget + 1e-8
            ),
            "notional_lte_effective_single_order_cap": (
                rounded_notional is not None
                and effective_cap is not None
                and rounded_notional <= effective_cap + 1e-8
            ),
            "notional_gte_min_notional": (
                rounded_notional is not None
                and min_notional is not None
                and rounded_notional >= min_notional
            ),
            "runtime_admission_ready": False,
            "order_admission_ready": False,
        },
        "answers": {
            "review_contract_ready": True,
            "runtime_admission_ready": False,
            "order_admission_ready": False,
            "decision_lease_acquire_performed": False,
            "decision_lease_release_performed": False,
            "order_submission_performed": False,
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "live_authority_granted": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
    }


def build_current_candidate_actual_admission_bbo_lease_window(
    *,
    admission_review: dict[str, Any] | None,
    gate_packet: dict[str, Any] | None,
    sizing_proposal: dict[str, Any] | None,
    current_candidate_envelope: dict[str, Any] | None,
    paths: dict[str, Path | None] | None = None,
    run: bool = False,
    require_env: bool = True,
    now_fn: NowFn | None = None,
    monotonic_fn: MonotonicFn | None = None,
    lease_ttl_seconds: float = LEASE_TTL_SECONDS,
    timeout_seconds: float = 5.0,
    base_url: str = quote_refresh.quote_capture.DEFAULT_BASE_URL,
    max_admission_review_age_seconds: int = DEFAULT_MAX_ADMISSION_REVIEW_AGE_SECONDS,
    max_gate_packet_age_seconds: int = DEFAULT_MAX_GATE_PACKET_AGE_SECONDS,
    max_runtime_snapshot_age_seconds: int = DEFAULT_MAX_RUNTIME_SNAPSHOT_AGE_SECONDS,
    max_sizing_proposal_age_seconds: int = DEFAULT_MAX_SIZING_PROPOSAL_AGE_SECONDS,
    max_envelope_age_seconds: int = DEFAULT_MAX_ENVELOPE_AGE_SECONDS,
    max_fresh_bbo_age_ms: int = DEFAULT_MAX_FRESH_BBO_AGE_MS,
    source_head: str | None = None,
    runtime_head: str | None = None,
    dispatcher: active_lease_window.IPCDispatcher | None = None,
    opener: Opener | None = None,
) -> dict[str, Any]:
    if lease_ttl_seconds <= 0 or lease_ttl_seconds > 10:
        raise ValueError("lease_ttl_seconds must be in (0, 10]")
    if timeout_seconds <= 0 or timeout_seconds > 30:
        raise ValueError("timeout_seconds must be in (0, 30]")
    if max_fresh_bbo_age_ms <= 0 or max_fresh_bbo_age_ms > 5000:
        raise ValueError("max_fresh_bbo_age_ms must be in (0, 5000]")

    now_fn = now_fn or _utc_now
    now = now_fn().astimezone(dt.timezone.utc)
    paths = paths or {}
    admission = _dict(admission_review)
    gate = _dict(gate_packet)
    proposal = _dict(sizing_proposal)
    envelope = _dict(current_candidate_envelope)
    preflight = _source_preflight(
        admission_review=admission,
        gate_packet=gate,
        sizing_proposal=proposal,
        current_candidate_envelope=envelope,
        now_utc=now,
        max_gate_packet_age_seconds=max_gate_packet_age_seconds,
        max_sizing_proposal_age_seconds=max_sizing_proposal_age_seconds,
        max_envelope_age_seconds=max_envelope_age_seconds,
        source_head=source_head,
        runtime_head=runtime_head,
    )
    candidate = _candidate_identity(_dict(preflight.get("candidate")))
    source_reasons = list(_list(preflight.get("source_blockers")))
    authority_reasons = list(_list(preflight.get("authority_contamination_reasons")))
    runtime_reasons: list[str] = []
    loss_control_reasons: list[str] = []
    if not candidate.get("side_cell_key"):
        source_reasons.append("candidate_missing")

    lease_id: str | None = None
    release_ok = False
    mutation_performed = False
    quote_packet: dict[str, Any] | None = None
    active_snapshot: dict[str, Any] | None = None
    active_gate_packet: dict[str, Any] | None = None
    active_gate_sizing_proposal: dict[str, Any] | None = None
    quote_started_after_acquire = False

    if not run:
        status = (
            DRY_RUN_READY_STATUS
            if not source_reasons and not authority_reasons
            else SOURCE_NOT_READY_STATUS
        )
        reason = (
            "dry_run_ready_for_explicit_actual_admission_bbo_lease_window"
            if status == DRY_RUN_READY_STATUS
            else "source_preflight_not_ready"
        )
    elif authority_reasons:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "source_preflight_authority_boundary_violation"
    elif source_reasons:
        status = SOURCE_NOT_READY_STATUS
        reason = "source_preflight_not_ready"
    elif require_env and os.environ.get(RUN_ENV) != "1":
        status = SOURCE_NOT_READY_STATUS
        reason = f"{RUN_ENV}_not_set"
        source_reasons.append(f"{RUN_ENV}_not_set")
    else:
        intent_id = _make_intent_id(candidate, now)
        try:
            lease_id = active_lease_window._acquire_active_lease(  # noqa: SLF001
                intent_id=intent_id,
                ttl_seconds=lease_ttl_seconds,
                dispatcher=dispatcher,
                timeout_seconds=timeout_seconds,
            )
            mutation_performed = lease_id is not None
            if lease_id is None:
                runtime_reasons.append("lease_acquire_failed")
            else:
                quote_started_after_acquire = True
                quote_packet = (
                    quote_refresh.build_current_candidate_public_quote_construction_refresh(
                        current_candidate_envelope=envelope,
                        current_candidate_envelope_path=paths.get(
                            "current_candidate_envelope"
                        ),
                        base_url=base_url,
                        timeout_seconds=min(
                            timeout_seconds,
                            quote_refresh.DEFAULT_TIMEOUT_SECONDS,
                        ),
                        max_fresh_bbo_age_ms=max_fresh_bbo_age_ms,
                        max_envelope_age_seconds=max_envelope_age_seconds,
                        opener=opener,
                        now_fn=now_fn,
                        monotonic_fn=monotonic_fn,
                        source_head=source_head,
                        runtime_head=runtime_head,
                    )
                )
                snapshot_now = now_fn().astimezone(dt.timezone.utc)
                active_gate_sizing_proposal = proposal
                if quote_packet.get("status") == quote_refresh.READY_STATUS:
                    active_gate_sizing_proposal = _actual_bbo_sizing_proposal(
                        quote_packet=quote_packet,
                        base_sizing_proposal=proposal,
                        candidate=candidate,
                        generated_at_utc=snapshot_now,
                    )
                active_snapshot, snapshot_reasons = (
                    active_lease_window._build_active_runtime_snapshot(  # noqa: SLF001
                        lease_id=lease_id,
                        candidate=candidate,
                        now=snapshot_now,
                        ttl_seconds=lease_ttl_seconds,
                        dispatcher=dispatcher,
                        timeout_seconds=timeout_seconds,
                    )
                )
                runtime_reasons.extend(snapshot_reasons)
                active_gate_packet = (
                    gate_evidence.build_current_candidate_decision_lease_guardian_gate_evidence(
                        admission_review=admission,
                        runtime_governance_snapshot=active_snapshot,
                        sizing_proposal=active_gate_sizing_proposal,
                        paths={
                            "admission_review": paths.get("admission_review"),
                            "runtime_governance_snapshot": None,
                            "sizing_proposal": None,
                        },
                        now_utc=snapshot_now,
                        max_admission_review_age_seconds=(
                            max_admission_review_age_seconds
                        ),
                        max_runtime_snapshot_age_seconds=(
                            max_runtime_snapshot_age_seconds
                        ),
                        max_sizing_proposal_age_seconds=(
                            max_sizing_proposal_age_seconds
                        ),
                        source_head=source_head,
                        runtime_head=runtime_head,
                    )
                )
        finally:
            if lease_id:
                release_ok = active_lease_window._release_active_lease(  # noqa: SLF001
                    lease_id=lease_id,
                    dispatcher=dispatcher,
                    timeout_seconds=timeout_seconds,
                )
                if not release_ok:
                    runtime_reasons.append("lease_release_failed")

        if (
            quote_packet
            and quote_packet.get("status")
            == quote_refresh.AUTHORITY_BOUNDARY_VIOLATION_STATUS
        ):
            authority_reasons.extend(_list(quote_packet.get("blocking_gates")))
            status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
            reason = "actual_admission_quote_authority_boundary_violation"
        elif runtime_reasons:
            status = BLOCKED_BY_RUNTIME_STATUS
            reason = "actual_admission_bbo_lease_window_runtime_check_failed"
        elif not quote_packet:
            status = BLOCKED_BY_RUNTIME_STATUS
            reason = "actual_admission_quote_packet_missing"
            runtime_reasons.append("actual_admission_quote_packet_missing")
        elif quote_packet.get("status") != quote_refresh.READY_STATUS:
            status = BLOCKED_BY_LOSS_CONTROL_STATUS
            reason = "actual_admission_bbo_refresh_not_ready"
            loss_control_reasons.extend(_list(quote_packet.get("blocking_gates")))
            loss_control_reasons.append("actual_admission_bbo_refresh_not_ready")
        elif not active_gate_packet:
            status = BLOCKED_BY_RUNTIME_STATUS
            reason = "active_window_gate_packet_missing"
            runtime_reasons.append("active_window_gate_packet_missing")
        elif active_gate_packet.get("status") != gate_evidence.READY_NO_ORDER_STATUS:
            status = BLOCKED_BY_LOSS_CONTROL_STATUS
            reason = "active_window_gate_not_ready"
            loss_control_reasons.extend(_list(active_gate_packet.get("blocking_gates")))
            loss_control_reasons.append("active_window_gate_not_ready")
        else:
            status = DONE_STATUS
            reason = "actual_admission_bbo_and_gate_validated_during_active_window_no_order"

    quote_summary = _dict(_dict(quote_packet).get("summary"))
    quote_public = _dict(_dict(quote_packet).get("public_quote"))
    quote_derived = _dict(quote_public.get("derived"))
    construction = _dict(_dict(_dict(quote_packet).get("construction_preview")).get("construction"))
    active_gate_status = _dict(active_gate_packet).get("status") if active_gate_packet else None
    lease_released = mutation_performed and release_ok
    actual_bbo_ready = (
        quote_packet is not None
        and quote_packet.get("status") == quote_refresh.READY_STATUS
        and quote_started_after_acquire
        and mutation_performed
    )
    gate_ready = active_gate_status == gate_evidence.READY_NO_ORDER_STATUS
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
            "current_candidate_envelope": _artifact_summary(
                paths.get("current_candidate_envelope"),
                envelope,
            ),
        },
        "source_preflight": preflight,
        "source_blockers": sorted(set(source_reasons)),
        "runtime_blockers": sorted(set(runtime_reasons)),
        "loss_control_blockers": sorted(set(loss_control_reasons)),
        "authority_contamination_reasons": sorted(set(authority_reasons)),
        "blocking_gates": sorted(
            set(source_reasons + runtime_reasons + loss_control_reasons + authority_reasons)
        ),
        "active_window": {
            "lease_id": lease_id,
            "lease_scope": LEASE_SCOPE,
            "lease_profile": LEASE_PROFILE,
            "lease_ttl_seconds": lease_ttl_seconds,
            "source_stage": LEASE_SOURCE_STAGE,
            "acquire_ok": mutation_performed,
            "release_ok": release_ok if mutation_performed else False,
            "lease_released_before_artifact": lease_released,
            "quote_started_after_lease_acquire": quote_started_after_acquire,
            "actual_admission_bbo_status_during_active_window": _dict(quote_packet).get(
                "status"
            ),
            "gate_evidence_status_during_active_window": active_gate_status,
        },
        "risk_context": risk_context,
        "actual_admission_bbo": {
            "status": _dict(quote_packet).get("status"),
            "request_count": quote_summary.get("request_count"),
            "bbo_age_ms": quote_derived.get("effective_bbo_age_ms"),
            "max_fresh_bbo_age_ms": quote_summary.get("max_fresh_bbo_age_ms"),
            "resolved_cap_usdt": quote_summary.get("resolved_cap_usdt"),
            "cap_source": quote_summary.get("cap_source"),
            "effective_single_order_cap_usdt": quote_summary.get(
                "effective_single_order_cap_usdt"
            ),
            "account_equity_usdt": quote_summary.get("account_equity_usdt"),
            "per_trade_budget_usdt": quote_summary.get("per_trade_budget_usdt"),
            "single_position_budget_usdt": quote_summary.get(
                "single_position_budget_usdt"
            ),
            "max_order_notional_usdt": quote_summary.get("max_order_notional_usdt"),
            "position_size_max_pct": quote_summary.get("position_size_max_pct"),
            "gui_risk_config_is_source_of_truth": quote_summary.get(
                "gui_risk_config_is_source_of_truth"
            ),
            "local_10_usdt_cap_is_global_risk_authority": quote_summary.get(
                "local_10_usdt_cap_is_global_risk_authority"
            ),
            "construction_constructible": quote_summary.get(
                "construction_constructible"
            ),
            "limit_price": construction.get("limit_price"),
            "rounded_qty": construction.get("rounded_qty"),
            "rounded_notional_usdt": construction.get("rounded_notional_usdt"),
        },
        "actual_admission_quote_construction_refresh": quote_packet,
        "active_runtime_governance_snapshot": active_snapshot,
        "active_window_gate_sizing_proposal": active_gate_sizing_proposal,
        "active_window_gate_evidence": active_gate_packet,
        "answers": {
            "review_contract_ready": (
                not source_reasons
                and not runtime_reasons
                and not loss_control_reasons
                and not authority_reasons
            ),
            "actual_admission_bbo_refreshed_during_active_lease": actual_bbo_ready,
            "fresh_actual_admission_bbo_and_gate_ready_during_window": (
                actual_bbo_ready and gate_ready
            ),
            "gate_evidence_ready_during_active_window": gate_ready,
            "runtime_admission_ready": False,
            "runtime_admission_ready_after_release": False,
            "order_admission_ready": False,
            "governance_lease_mutation_performed": mutation_performed,
            "decision_lease_acquire_performed": mutation_performed,
            "decision_lease_release_performed": lease_released,
            "decision_lease_emitted": False,
            "lease_released_before_artifact": lease_released,
            "public_quote_capture_performed": bool(
                quote_summary.get("public_quote_capture_performed")
            ),
            "bybit_call_performed": bool(quote_summary.get("network_call_performed")),
            "bybit_public_market_data_call_performed": bool(
                quote_summary.get("bybit_public_market_data_call_performed")
            ),
            "bybit_private_call_performed": False,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
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
    bbo = _dict(packet.get("actual_admission_bbo"))
    lines = [
        "# Current Candidate Actual-Admission BBO Lease Window",
        "",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Lease id: `{active.get('lease_id')}`",
        f"- Acquire/release ok: `{active.get('acquire_ok')}` / `{active.get('release_ok')}`",
        "- Actual BBO status during active window: "
        f"`{active.get('actual_admission_bbo_status_during_active_window')}`",
        "- Gate status during active window: "
        f"`{active.get('gate_evidence_status_during_active_window')}`",
        "- Runtime admission ready after release: "
        f"`{answers.get('runtime_admission_ready_after_release')}`",
        f"- GUI resolved cap USDT: `{risk.get('resolved_cap_usdt')}`",
        "- Per-trade risk pct fraction/display: "
        f"`{risk.get('per_trade_risk_pct_fraction')}` / "
        f"`{risk.get('per_trade_risk_pct_display')}`",
        f"- Max single position pct: `{risk.get('position_size_max_pct')}`",
        f"- BBO age ms: `{bbo.get('bbo_age_ms')}`",
        f"- Rounded notional USDT: `{bbo.get('rounded_notional_usdt')}`",
        "",
        "## Blockers",
    ]
    blockers = _list(packet.get("blocking_gates"))
    lines.extend(f"- `{blocker}`" for blocker in blockers) if blockers else lines.append("- none")
    lines.extend(["", "## Boundary", BOUNDARY])
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--admission-review-json", type=Path, required=True)
    parser.add_argument("--gate-packet-json", type=Path, required=True)
    parser.add_argument("--sizing-proposal-json", type=Path, required=True)
    parser.add_argument("--current-candidate-envelope-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--actual-quote-construction-json-output", type=Path)
    parser.add_argument("--actual-construction-preview-json-output", type=Path)
    parser.add_argument("--active-runtime-snapshot-json-output", type=Path)
    parser.add_argument("--active-gate-evidence-json-output", type=Path)
    parser.add_argument(
        "--base-url",
        default=quote_refresh.quote_capture.DEFAULT_BASE_URL,
        choices=sorted(quote_refresh.quote_capture.ALLOWED_BASE_URLS),
    )
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
    parser.add_argument(
        "--max-envelope-age-seconds",
        type=int,
        default=DEFAULT_MAX_ENVELOPE_AGE_SECONDS,
    )
    parser.add_argument(
        "--max-fresh-bbo-age-ms",
        type=int,
        default=DEFAULT_MAX_FRESH_BBO_AGE_MS,
    )
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.run and not args.yes:
        raise SystemExit("--run requires --yes")
    if args.run and os.environ.get(RUN_ENV) != "1":
        raise SystemExit(f"--run requires {RUN_ENV}=1")

    packet = build_current_candidate_actual_admission_bbo_lease_window(
        admission_review=_read_json(args.admission_review_json),
        gate_packet=_read_json(args.gate_packet_json),
        sizing_proposal=_read_json(args.sizing_proposal_json),
        current_candidate_envelope=_read_json(args.current_candidate_envelope_json),
        paths={
            "admission_review": args.admission_review_json,
            "gate_packet": args.gate_packet_json,
            "sizing_proposal": args.sizing_proposal_json,
            "current_candidate_envelope": args.current_candidate_envelope_json,
        },
        run=args.run,
        require_env=True,
        base_url=args.base_url,
        lease_ttl_seconds=args.lease_ttl_seconds,
        timeout_seconds=args.timeout_seconds,
        max_admission_review_age_seconds=args.max_admission_review_age_seconds,
        max_gate_packet_age_seconds=args.max_gate_packet_age_seconds,
        max_runtime_snapshot_age_seconds=args.max_runtime_snapshot_age_seconds,
        max_sizing_proposal_age_seconds=args.max_sizing_proposal_age_seconds,
        max_envelope_age_seconds=args.max_envelope_age_seconds,
        max_fresh_bbo_age_ms=args.max_fresh_bbo_age_ms,
        source_head=args.source_head,
        runtime_head=args.runtime_head,
    )
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, render_markdown(packet))
    quote_packet = _dict(packet.get("actual_admission_quote_construction_refresh"))
    if args.actual_quote_construction_json_output and quote_packet:
        _write_json(args.actual_quote_construction_json_output, quote_packet)
    construction_preview = _dict(quote_packet.get("construction_preview"))
    if args.actual_construction_preview_json_output and construction_preview:
        _write_json(args.actual_construction_preview_json_output, construction_preview)
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

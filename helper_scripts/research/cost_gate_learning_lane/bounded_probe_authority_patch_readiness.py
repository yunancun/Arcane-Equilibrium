#!/usr/bin/env python3
"""Build a no-authority Rust patch-readiness packet for bounded Demo probes.

This artifact consumes the no-authority placement repair plan and statically
scans the source tree for the seams needed to turn a Cost Gate-blocked signal
into a bounded, near-touch Demo learning attempt.

It does not query PG, call Bybit, submit orders, lower the Cost Gate, grant
probe/order authority, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PATCH_READINESS_SCHEMA_VERSION = "bounded_demo_probe_authority_patch_readiness_v1"
PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION = (
    "bounded_demo_probe_placement_repair_plan_v1"
)
READY_REPAIR_STATUS = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
BOUNDARY = (
    "artifact-only bounded Demo probe source-readiness scan; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)


@dataclass(frozen=True)
class SourceCheck:
    check_id: str
    category: str
    description: str
    required_patterns: tuple[str, ...]
    paths: tuple[str, ...]
    missing_reason: str


EXISTING_SEAM_CHECKS: tuple[SourceCheck, ...] = (
    SourceCheck(
        check_id="demo_learning_lane_admission_policy",
        category="existing_authority_seam",
        description=(
            "Rust has a pure Cost Gate demo-learning admission Module that "
            "keeps main Cost Gate lowering disallowed."
        ),
        required_patterns=(
            "evaluate_probe_admission",
            "ORDER_AUTHORITY_GRANTED",
            "demo_learning_lane_must_not_lower_main_cost_gate",
        ),
        paths=("rust/openclaw_engine/src/demo_learning_lane.rs",),
        missing_reason="demo_learning_lane_admission_policy_missing",
    ),
    SourceCheck(
        check_id="eligible_reject_hot_path_capture",
        category="existing_authority_seam",
        description=(
            "Eligible Demo/LiveDemo Cost Gate rejects can be normalized into "
            "learning-lane RejectEvent rows."
        ),
        required_patterns=("exchange_gate_reject_event", "ELIGIBLE_REJECT_REASON_CODE"),
        paths=("rust/openclaw_engine/src/demo_learning_lane_hot_path.rs",),
        missing_reason="eligible_cost_gate_reject_hot_path_capture_missing",
    ),
    SourceCheck(
        check_id="admission_ledger_writer",
        category="existing_authority_seam",
        description=(
            "The writer can persist admission and capture-error JSONL rows "
            "without submitting orders."
        ),
        required_patterns=(
            "probe_admission_decision",
            "probe_capture_error",
            "does not submit orders",
        ),
        paths=(
            "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
            "rust/openclaw_engine/src/demo_learning_lane_ledger.rs",
        ),
        missing_reason="admission_ledger_writer_missing",
    ),
    SourceCheck(
        check_id="order_intent_limit_tif_surface",
        category="existing_authority_seam",
        description=(
            "OrderIntent already carries limit_price and TimeInForce, so a "
            "bounded Adapter can alter placement shape without inventing a new "
            "order object."
        ),
        required_patterns=("limit_price", "time_in_force", "TimeInForce::PostOnly"),
        paths=(
            "rust/openclaw_engine/src/intent_processor/mod.rs",
            "rust/openclaw_engine/src/order_manager.rs",
        ),
        missing_reason="order_intent_limit_tif_surface_missing",
    ),
    SourceCheck(
        check_id="dispatch_bbo_reference_surface",
        category="existing_authority_seam",
        description=(
            "Tick dispatch exposes best_bid/best_ask and reference price data "
            "near the exchange dispatch point."
        ),
        required_patterns=("best_bid", "best_ask", "execution_reference"),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        missing_reason="dispatch_bbo_reference_surface_missing",
    ),
    SourceCheck(
        check_id="exchange_dispatch_limit_tif_forwarding",
        category="existing_authority_seam",
        description=(
            "Exchange dispatch already forwards order_type, limit_price, and "
            "TimeInForce to the downstream order request."
        ),
        required_patterns=("OrderDispatchRequest", "limit_price: intent.limit_price", "time_in_force: intent.time_in_force"),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        missing_reason="exchange_dispatch_limit_tif_forwarding_missing",
    ),
)

PATCH_REQUIREMENT_CHECKS: tuple[SourceCheck, ...] = (
    SourceCheck(
        check_id="bounded_probe_near_touch_adapter",
        category="adapter_module_seam",
        description=(
            "A pure Rust Adapter Module should apply the placement repair plan's "
            "post_only_near_touch_or_skip rule to the selected side-cell."
        ),
        required_patterns=(
            "post_only_near_touch_or_skip",
            "BoundedProbePlacementDecision",
        ),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="near_touch_or_skip_adapter_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="fresh_bbo_age_guard",
        category="adapter_module_seam",
        description=(
            "The Adapter should fail closed when the BBO snapshot is older than "
            "max_fresh_bbo_age_ms."
        ),
        required_patterns=("max_fresh_bbo_age_ms",),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="fresh_bbo_age_guard_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="max_initial_gap_guard",
        category="adapter_module_seam",
        description=(
            "The Adapter should compute initial touch gap bps and skip when it "
            "exceeds max_initial_passive_gap_bps."
        ),
        required_patterns=("max_initial_passive_gap_bps", "touch_gap_bps"),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="initial_touch_gap_guard_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="touchability_skip_record",
        category="adapter_module_seam",
        description=(
            "Skipped near-touch attempts should be recorded as "
            "bounded_probe_touchability_block rather than silently lost."
        ),
        required_patterns=("bounded_probe_touchability_block",),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="touchability_skip_record_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="candidate_matched_attempt_lineage",
        category="adapter_module_seam",
        description=(
            "The Adapter output should name bounded_probe_attempt rows and carry "
            "side_cell_key lineage for later fill/fee/slippage review."
        ),
        required_patterns=("bounded_probe_attempt", "side_cell_key"),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="candidate_matched_attempt_lineage_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="authority_path_wiring",
        category="authority_path_wiring_seam",
        description=(
            "The tick/exchange authority path should call the Adapter before any "
            "future bounded probe order is submitted."
        ),
        required_patterns=(
            "post_only_near_touch_from_optional_bbo_or_skip",
            "BoundedProbeOptionalBboPlacementRequest",
            "bounded_probe_attempt",
        ),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        missing_reason="authority_path_wiring_missing_from_tick_dispatch",
    ),
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _artifact_status(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = (
        (payload or {}).get("generated_at_utc")
        or (payload or {}).get("generated")
        or (payload or {}).get("ts_utc")
    )
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _authority_preserved(placement_repair_plan: dict[str, Any] | None) -> bool:
    payload = _dict(placement_repair_plan)
    answers = _dict(payload.get("answers"))
    plan = _dict(payload.get("placement_repair_plan"))
    boundary = _dict(plan.get("authority_boundary"))
    for source in (payload, answers, plan, boundary):
        if source.get("global_cost_gate_lowering_recommended") is True:
            return False
        if source.get("probe_authority_granted") is True:
            return False
        if source.get("order_authority_granted") is True:
            return False
        if source.get("promotion_evidence") is True:
            return False
        if source.get("promotion_proof") is True:
            return False
        if source.get("main_cost_gate_adjustment") not in (None, "", "NONE"):
            return False
    return True


def _placement_plan_summary(
    placement_repair_plan: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    payload = _dict(placement_repair_plan)
    plan = _dict(payload.get("placement_repair_plan"))
    candidate = _dict(plan.get("candidate")) or _dict(payload.get("candidate"))
    artifact = _artifact_status(
        payload or None,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    authority_preserved = _authority_preserved(payload)
    ready = (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
        and payload.get("status") == READY_REPAIR_STATUS
        and plan.get("order_mode") == "post_only_near_touch_or_skip"
        and authority_preserved
    )
    return {
        "artifact": artifact,
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "ready_for_source_patch_review": ready,
        "authority_preserved": authority_preserved,
        "candidate": {
            "side_cell_key": candidate.get("side_cell_key"),
            "strategy_name": candidate.get("strategy_name"),
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
        },
        "order_mode": plan.get("order_mode"),
        "max_fresh_bbo_age_ms": plan.get("max_fresh_bbo_age_ms"),
        "max_initial_passive_gap_bps": _float(
            plan.get("max_initial_passive_gap_bps")
        ),
        "max_demo_notional_usdt_per_order": _dict(plan.get("probe_limits")).get(
            "max_demo_notional_usdt_per_order"
        ),
        "max_probe_intents_before_review": _dict(plan.get("probe_limits")).get(
            "max_probe_intents_before_review"
        ),
        "skip_record_type": _dict(plan.get("skip_record")).get("record_type"),
        "post_order_evidence": _list(plan.get("post_order_evidence")),
    }


def _iter_files(repo_root: Path, path_text: str) -> list[Path]:
    path = repo_root / path_text
    if path.is_file():
        return [path]
    if path.is_dir():
        return [
            item
            for item in sorted(path.rglob("*.rs"))
            if ".git" not in item.parts and item.is_file()
        ]
    return []


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_repo_text(repo_root: Path, rel_path: str) -> str:
    path = repo_root / rel_path
    return _read_file(path) or ""


def _repo_file_present(repo_root: Path, rel_path: str) -> bool:
    return (repo_root / rel_path).is_file()


def _find_pattern_evidence(
    files: list[tuple[str, str]], patterns: tuple[str, ...]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for pattern in patterns:
        matched = False
        for rel_path, text in files:
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    evidence.append(
                        {
                            "pattern": pattern,
                            "path": rel_path,
                            "line": idx,
                            "snippet": line.strip()[:220],
                        }
                    )
                    matched = True
                    break
            if matched:
                break
    return evidence


def _evaluate_source_check(repo_root: Path, check: SourceCheck) -> dict[str, Any]:
    loaded_files: list[tuple[str, str]] = []
    missing_paths: list[str] = []
    for rel in check.paths:
        files = _iter_files(repo_root, rel)
        if not files:
            missing_paths.append(rel)
            continue
        for path in files:
            text = _read_file(path)
            if text is not None:
                loaded_files.append((path.relative_to(repo_root).as_posix(), text))
    text_by_pattern = {
        pattern: any(pattern in text for _, text in loaded_files)
        for pattern in check.required_patterns
    }
    present = bool(loaded_files) and all(text_by_pattern.values())
    return {
        "check_id": check.check_id,
        "category": check.category,
        "description": check.description,
        "present": present,
        "missing_reason": None if present else check.missing_reason,
        "paths": list(check.paths),
        "loaded_file_count": len(loaded_files),
        "missing_paths": missing_paths,
        "required_patterns": list(check.required_patterns),
        "missing_patterns": [
            pattern for pattern, found in text_by_pattern.items() if not found
        ],
        "evidence": _find_pattern_evidence(loaded_files, check.required_patterns),
    }


def _check_present(rows: list[dict[str, Any]], check_id: str) -> bool:
    return any(
        row.get("check_id") == check_id and row.get("present") is True
        for row in rows
    )


def _source_readiness(repo_root: Path) -> dict[str, Any]:
    existing = [
        _evaluate_source_check(repo_root, check) for check in EXISTING_SEAM_CHECKS
    ]
    required = [
        _evaluate_source_check(repo_root, check) for check in PATCH_REQUIREMENT_CHECKS
    ]
    missing_existing = [
        row["missing_reason"] for row in existing if row.get("present") is not True
    ]
    missing_required = [
        row["missing_reason"] for row in required if row.get("present") is not True
    ]
    return {
        "repo_root": str(repo_root),
        "existing_authority_seams": existing,
        "required_patch_seams": required,
        "existing_authority_seams_present": not missing_existing,
        "required_patch_seams_present": not missing_required,
        "adapter_module_present": _check_present(
            required,
            "bounded_probe_near_touch_adapter",
        ),
        "authority_path_wiring_present": _check_present(
            required,
            "authority_path_wiring",
        ),
        "missing_existing_seams": missing_existing,
        "missing_required_patch_seams": missing_required,
    }


def _active_order_submission_readiness(repo_root: Path) -> dict[str, Any]:
    writer_rel = "rust/openclaw_engine/src/demo_learning_lane_writer.rs"
    dispatch_rel = "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs"
    near_touch_rel = "rust/openclaw_engine/src/bounded_probe_near_touch.rs"
    writer_text = _read_repo_text(
        repo_root,
        writer_rel,
    )
    dispatch_text = _read_repo_text(
        repo_root,
        dispatch_rel,
    )
    near_touch_text = _read_repo_text(
        repo_root,
        near_touch_rel,
    )
    file_presence = {
        writer_rel: _repo_file_present(repo_root, writer_rel),
        dispatch_rel: _repo_file_present(repo_root, dispatch_rel),
        near_touch_rel: _repo_file_present(repo_root, near_touch_rel),
    }
    writer_no_order_contract = "does not submit orders" in writer_text
    dispatch_no_order_contract = "no order submitted" in dispatch_text
    near_touch_pure_no_order_contract = "submit\n//! orders" in near_touch_text or (
        "does not read plans, write ledgers, call Bybit, submit" in near_touch_text
    )
    adapter_enabled_hardcoded_false = re.search(
        r"evaluate_probe_admission\([\s\S]*?,\s*false\s*,\s*risk_state\s*,?\s*\)",
        writer_text,
    ) is not None
    positive_active_evidence = {
        "writer_submits_candidate_matched_probe_order": (
            "submit_candidate_matched_bounded_probe_order" in writer_text
            or "active_bounded_probe_order_submission" in writer_text
        ),
        "dispatch_forwards_admitted_bounded_probe_to_exchange": (
            "dispatch_admitted_bounded_probe_order" in dispatch_text
            or "active_bounded_probe_order_submission" in dispatch_text
        ),
        "adapter_enabled_by_runtime_bounded_probe_gate": (
            "bounded_probe_adapter_enabled" in writer_text
            or "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED" in writer_text
        ),
    }
    blockers: list[str] = []
    for rel_path, present in file_presence.items():
        if not present:
            blockers.append(f"source_file_missing:{rel_path}")
    if writer_no_order_contract:
        blockers.append("demo_learning_lane_writer_contract_no_order_submission")
    if adapter_enabled_hardcoded_false:
        blockers.append("demo_learning_lane_writer_adapter_enabled_false")
    if dispatch_no_order_contract:
        blockers.append("tick_dispatch_records_preview_no_order_submitted")
    if near_touch_pure_no_order_contract:
        blockers.append("near_touch_adapter_contract_pure_no_order_math")
    missing_positive_evidence = [
        key for key, present in positive_active_evidence.items() if present is not True
    ]
    if missing_positive_evidence:
        blockers.append("positive_active_order_submission_evidence_missing")
    active_ready = (
        all(file_presence.values())
        and not missing_positive_evidence
        and not blockers
    )
    return {
        "status": (
            "ACTIVE_ORDER_SUBMISSION_WIRING_PRESENT"
            if active_ready
            else "ACTIVE_ORDER_SUBMISSION_WIRING_MISSING"
        ),
        "active_order_submission_ready": active_ready,
        "blockers": blockers,
        "evidence": {
            "file_presence": file_presence,
            "writer_no_order_contract": writer_no_order_contract,
            "adapter_enabled_hardcoded_false": adapter_enabled_hardcoded_false,
            "dispatch_no_order_contract": dispatch_no_order_contract,
            "near_touch_pure_no_order_contract": near_touch_pure_no_order_contract,
            "positive_active_evidence": positive_active_evidence,
            "missing_positive_active_evidence": missing_positive_evidence,
        },
        "required_before_order": [
            "separate_source_patch_to_enable_active_bounded_demo_order_submission",
            "candidate_matched_attempt_fill_fee_slippage_lineage",
            "fresh_e3_bb_exchange_facing_order_envelope_review",
            "guardian_decision_lease_rust_authority_path_preserved",
        ],
        "boundary": "source scan only; this packet never grants active order authority",
    }


def _profitability_improvement_lanes(
    placement_summary: dict[str, Any], source_summary: dict[str, Any]
) -> list[dict[str, Any]]:
    candidate = _dict(placement_summary.get("candidate"))
    return [
        {
            "lane": "execution_realism_first",
            "objective": (
                "convert selected Cost Gate-blocked side-cell signals into "
                "touchable maker Demo attempts before changing Cost Gate thresholds"
            ),
            "why_it_can_improve_profitability": (
                "Current evidence shows orders but no fills; without touchable "
                "attempts the system cannot learn fee, slippage, queue, or edge capture."
            ),
            "next_engineering_module": "bounded_demo_probe_near_touch_authority_adapter",
            "current_candidate": candidate.get("side_cell_key"),
            "machine_gate": "candidate_matched_fill_fee_slippage_lineage_recorded",
        },
        {
            "lane": "edge_amplification_by_side_cell_horizon",
            "objective": (
                "specialize probes to ranked strategy/symbol/side/horizon cells "
                "instead of lowering the global Cost Gate"
            ),
            "why_it_can_improve_profitability": (
                "It concentrates risk budget on blocked cells with observed net-cost "
                "cushion and avoids spending Demo budget on robust negative cells."
            ),
            "next_engineering_module": "multi_horizon_blocked_signal_control_loop",
            "current_candidate": candidate.get("side_cell_key"),
            "machine_gate": "matched_blocked_controls_positive_and_independent",
        },
        {
            "lane": "autonomous_learning_feedback",
            "objective": (
                "feed bounded probe results back into result-review and "
                "execution-realism review before any parameter or Cost Gate change"
            ),
            "why_it_can_improve_profitability": (
                "It separates alpha existence from realized edge capture, preventing "
                "positive-looking signals from being promoted when execution loses the edge."
            ),
            "next_engineering_module": "bounded_probe_result_and_execution_realism_review",
            "current_gap": source_summary.get("missing_required_patch_seams"),
            "machine_gate": "probe_edge_capture_ratio_and_matched_control_pass",
        },
    ]


def _status(
    *,
    placement_summary: dict[str, Any],
    source_summary: dict[str, Any],
) -> tuple[str, str, list[str]]:
    artifact_status = _dict(placement_summary.get("artifact")).get("status")
    if placement_summary.get("authority_preserved") is not True:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "placement_repair_plan_contains_authority_granting_fields",
            ["remove_authority_granting_input_before_source_patch_review"],
        )
    if artifact_status != "FRESH":
        return (
            "PLACEMENT_REPAIR_PLAN_REQUIRED",
            "fresh_bounded_demo_probe_placement_repair_plan_v1_required",
            ["refresh_bounded_probe_placement_repair_plan_before_source_readiness"],
        )
    if (
        _dict(placement_summary.get("artifact")).get("schema_version")
        != PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
        or placement_summary.get("status") != READY_REPAIR_STATUS
        or placement_summary.get("ready_for_source_patch_review") is not True
    ):
        return (
            "PLACEMENT_REPAIR_PLAN_NOT_READY",
            "placement_repair_plan_is_not_ready_for_operator_source_patch_review",
            ["resolve_placement_repair_plan_status_before_rust_patch"],
        )
    if source_summary.get("existing_authority_seams_present") is not True:
        return (
            "SOURCE_SCAN_INCOMPLETE",
            "required_existing_authority_seams_missing_or_unreadable",
            ["repair_source_scan_or_existing_seam_before_rust_patch"],
        )
    if source_summary.get("adapter_module_present") is not True:
        return (
            "RUST_PATCH_REQUIRED_NEAR_TOUCH_PLACEMENT_ADAPTER_MISSING",
            "existing_source_lacks_required_near_touch_or_skip_authority_adapter",
            [
                "operator_review_existing_rust_authority_path_patch",
                "implement_bounded_demo_probe_near_touch_or_skip_adapter",
                "record_skip_and_candidate_matched_attempt_lineage_before_any_order",
            ],
        )
    if source_summary.get("authority_path_wiring_present") is not True:
        return (
            "RUST_PATCH_REQUIRED_AUTHORITY_PATH_WIRING_MISSING",
            "near_touch_adapter_exists_but_tick_dispatch_authority_path_is_not_wired",
            [
                "operator_review_tick_dispatch_authority_path_patch",
                "wire_bounded_demo_probe_adapter_before_any_probe_order_submission",
                "record_skip_and_candidate_matched_attempt_lineage_before_any_order",
            ],
        )
    return (
        "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
        "source_contains_required_near_touch_authority_adapter_and_evidence_hooks",
        [
            "operator_review_static_patch_readiness_before_demo_authorization",
            "run_bounded_demo_probe_only_after_separate_authorization",
            "refresh_order_to_fill_and_execution_realism_artifacts_after_probe",
        ],
    )


def build_bounded_demo_probe_authority_patch_readiness(
    *,
    placement_repair_plan: dict[str, Any] | None,
    repo_root: Path,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    repo_root = repo_root.resolve()
    placement_summary = _placement_plan_summary(
        placement_repair_plan,
        now_utc=now,
        max_age_seconds=max_artifact_age_hours * 3600,
    )
    source_summary = _source_readiness(repo_root)
    active_order_summary = _active_order_submission_readiness(repo_root)
    status, reason, next_actions = _status(
        placement_summary=placement_summary,
        source_summary=source_summary,
    )
    lanes = _profitability_improvement_lanes(placement_summary, source_summary)
    return {
        "schema_version": PATCH_READINESS_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "placement_repair_plan": placement_summary,
        "source_readiness": source_summary,
        "active_order_submission_readiness": active_order_summary,
        "profitability_improvement_lanes": lanes,
        "answers": {
            "placement_repair_plan_ready": placement_summary.get(
                "ready_for_source_patch_review"
            )
            is True,
            "source_scan_complete": source_summary.get(
                "existing_authority_seams_present"
            )
            is True,
            "existing_authority_seams_present": source_summary.get(
                "existing_authority_seams_present"
            )
            is True,
            "rust_near_touch_authority_adapter_present": source_summary.get(
                "adapter_module_present"
            )
            is True,
            "rust_authority_path_wiring_present": source_summary.get(
                "authority_path_wiring_present"
            )
            is True,
            "rust_active_order_submission_wiring_present": active_order_summary.get(
                "active_order_submission_ready"
            )
            is True,
            "active_order_submission_ready": active_order_summary.get(
                "active_order_submission_ready"
            )
            is True,
            "active_order_submission_authority_granted": False,
            "rust_patch_required": status.startswith("RUST_PATCH_REQUIRED_"),
            "runtime_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    placement = _dict(packet.get("placement_repair_plan"))
    source = _dict(packet.get("source_readiness"))
    active_order = _dict(packet.get("active_order_submission_readiness"))
    lines = [
        "# Bounded Demo Probe Authority Patch Readiness",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(placement.get('candidate')).get('side_cell_key')}`",
        f"- Order mode: `{placement.get('order_mode')}`",
        f"- Existing authority seams present: `{source.get('existing_authority_seams_present')}`",
        f"- Required patch seams present: `{source.get('required_patch_seams_present')}`",
        f"- Near-touch Adapter present: `{source.get('adapter_module_present')}`",
        f"- Authority path wiring present: `{source.get('authority_path_wiring_present')}`",
        f"- Active order submission ready: `{active_order.get('active_order_submission_ready')}`",
        f"- Active order submission blockers: `{active_order.get('blockers')}`",
        f"- Missing patch seams: `{source.get('missing_required_patch_seams')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Profitability Lanes",
        "",
    ]
    for lane in _list(packet.get("profitability_improvement_lanes")):
        lines.append(f"- `{lane.get('lane')}`: {lane.get('objective')}")
    lines.extend(["", "## Next Actions", ""])
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--placement-repair-plan-json", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_read_json(args.placement_repair_plan_json),
        repo_root=args.repo_root,
        max_artifact_age_hours=args.max_artifact_age_hours,
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not args.output and not args.json_output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

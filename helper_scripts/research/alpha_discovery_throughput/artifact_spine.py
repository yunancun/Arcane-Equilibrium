"""Cost Gate artifact spine classification.

MODULE_NOTE:
  用途：把 Cost Gate learning lane 的物理 artifacts 收斂成少數 active-loop
  Interface，避免 caller 把治理包裝、dashboard、smoke 與 alpha evidence 混用。
  邊界：artifact-only filesystem inspection；不連 DB、不連 Bybit、不改 runtime。
"""

from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


COST_GATE_ARTIFACT_SPINE_SCHEMA_VERSION = "cost_gate_artifact_spine_v1"
ACTIVE_STATE_SCHEMA_VERSION = "cost_gate_artifact_spine_active_state_v1"
DEFAULT_ARTIFACT_SPINE_MAX_AGE_SECONDS = 36 * 60 * 60
BLOCKED_OUTCOME_REVIEW_CANDIDATES_STATUS = (
    "DEMO_PROBE_AUTHORITY_REVIEW_CANDIDATES_PRESENT"
)
FALSE_NEGATIVE_CANDIDATES_READY_STATUS = (
    "COST_GATE_FALSE_NEGATIVE_CANDIDATES_READY_FOR_OPERATOR_REVIEW"
)
DOWNSTREAM_PROBE_ARTIFACT_IDS = (
    "sealed_horizon_probe_preflight",
    "bounded_probe_operator_authorization",
    "bounded_probe_shadow_placement_impact",
    "bounded_probe_result_review",
    "bounded_probe_execution_realism_review",
)
_BAD_STATUS_VALUES = {
    "MISSING",
    "EMPTY",
    "MALFORMED",
    "READ_ERROR",
    "STALE_ARTIFACT",
    "SOURCE_SCORECARD_UNAVAILABLE",
    "WAIT_FOR_HISTORICAL_SCORECARD_REFRESH",
}


@dataclass(frozen=True)
class PhysicalArtifactSpec:
    artifact_id: str
    rel_path: str
    artifact_class: str
    role: str
    present_key: str | None = None
    source_ok_key: str | None = None
    status_key: str | None = None
    source_error_key: str | None = None
    counts_as_alpha_evidence: bool = False
    authority_boundary: str = "no_authority"


@dataclass(frozen=True)
class SpineNodeSpec:
    node_id: str
    interface_role: str
    member_artifact_ids: tuple[str, ...]
    counts_as_alpha_evidence: bool
    required_artifact_ids: tuple[str, ...] = ()


PHYSICAL_ARTIFACT_SPECS: tuple[PhysicalArtifactSpec, ...] = (
    PhysicalArtifactSpec(
        artifact_id="cost_gate_reject_counterfactual",
        rel_path="cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json",
        artifact_class="evidence",
        role="blocked_signal_counterfactual_raw",
        counts_as_alpha_evidence=True,
    ),
    PhysicalArtifactSpec(
        artifact_id="probe_ledger",
        rel_path="cost_gate_learning_lane/probe_ledger.jsonl",
        artifact_class="ledger",
        role="append_only_learning_rows",
        status_key="ledger_status",
        source_error_key="ledger_source_error",
        counts_as_alpha_evidence=True,
    ),
    PhysicalArtifactSpec(
        artifact_id="activation_preflight",
        rel_path="cost_gate_learning_lane/activation_preflight_latest.json",
        artifact_class="readiness",
        role="source_writer_loop_readiness",
        status_key="profit_learning_activation_status",
    ),
    PhysicalArtifactSpec(
        artifact_id="blocked_outcome_review",
        rel_path="cost_gate_learning_lane/blocked_outcome_review_latest.json",
        artifact_class="evidence",
        role="false_negative_edge_amplification_keep_blocked_classifier",
        status_key="blocked_signal_outcome_review_status",
        counts_as_alpha_evidence=True,
    ),
    PhysicalArtifactSpec(
        artifact_id="false_negative_candidate_packet",
        rel_path="cost_gate_learning_lane/false_negative_candidate_packet_latest.json",
        artifact_class="candidate_queue",
        role="ranked_false_negative_and_edge_amplification_queue",
        present_key="false_negative_candidate_packet_present",
        source_ok_key="false_negative_candidate_packet_source_ok",
        status_key="false_negative_candidate_packet_status",
        source_error_key="false_negative_candidate_packet_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="sealed_horizon_probe_preflight",
        rel_path="cost_gate_learning_lane/sealed_horizon_probe_preflight_latest.json",
        artifact_class="probe_governance",
        role="candidate_horizon_preflight",
        present_key="sealed_horizon_probe_preflight_present",
        source_ok_key="sealed_horizon_probe_preflight_source_ok",
        status_key="sealed_horizon_probe_preflight_status",
        source_error_key="sealed_horizon_probe_preflight_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="bounded_probe_operator_authorization",
        rel_path="cost_gate_learning_lane/bounded_probe_operator_authorization_latest.json",
        artifact_class="probe_governance",
        role="operator_authorization_object_review",
        present_key="bounded_probe_operator_authorization_present",
        source_ok_key="bounded_probe_operator_authorization_source_ok",
        status_key="bounded_probe_operator_authorization_status",
        source_error_key="bounded_probe_operator_authorization_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="bounded_probe_shadow_placement_impact",
        rel_path="cost_gate_learning_lane/bounded_probe_shadow_placement_impact_latest.json",
        artifact_class="execution_touchability",
        role="mechanical_touchability_repair_shadow",
        present_key="bounded_probe_shadow_placement_impact_present",
        source_ok_key="bounded_probe_shadow_placement_impact_source_ok",
        status_key="bounded_probe_shadow_placement_impact_status",
        source_error_key="bounded_probe_shadow_placement_impact_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="bounded_probe_result_review",
        rel_path="cost_gate_learning_lane/bounded_probe_result_review_latest.json",
        artifact_class="probe_result",
        role="candidate_matched_probe_vs_control_result",
        present_key="bounded_probe_result_review_present",
        source_ok_key="bounded_probe_result_review_source_ok",
        status_key="bounded_probe_result_review_status",
        source_error_key="bounded_probe_result_review_source_error",
        counts_as_alpha_evidence=True,
    ),
    PhysicalArtifactSpec(
        artifact_id="bounded_probe_execution_realism_review",
        rel_path="cost_gate_learning_lane/bounded_probe_execution_realism_review_latest.json",
        artifact_class="probe_result",
        role="fill_fee_slippage_timing_gap_review",
        present_key="bounded_probe_execution_realism_review_present",
        source_ok_key="bounded_probe_execution_realism_review_source_ok",
        status_key="bounded_probe_execution_realism_review_status",
        source_error_key="bounded_probe_execution_realism_review_source_error",
        counts_as_alpha_evidence=True,
    ),
    PhysicalArtifactSpec(
        artifact_id="false_negative_operator_review",
        rel_path="cost_gate_learning_lane/false_negative_operator_review_latest.json",
        artifact_class="governance",
        role="operator_typed_confirm_review_state",
        present_key="false_negative_operator_review_present",
        source_ok_key="false_negative_operator_review_source_ok",
        status_key="false_negative_operator_review_status",
        source_error_key="false_negative_operator_review_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="sealed_horizon_operator_review",
        rel_path="cost_gate_learning_lane/sealed_horizon_operator_review_latest.json",
        artifact_class="governance",
        role="sealed_horizon_operator_review_state",
        present_key="sealed_horizon_operator_review_present",
        source_ok_key="sealed_horizon_operator_review_source_ok",
        status_key="sealed_horizon_operator_review_status",
        source_error_key="sealed_horizon_operator_review_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="profit_learning_decision_packet",
        rel_path="cost_gate_learning_lane/profit_learning_decision_packet_latest.json",
        artifact_class="dashboard_view",
        role="cost_gate_profit_learning_summary_view",
        present_key="profit_learning_decision_packet_present",
        source_ok_key="profit_learning_decision_packet_source_ok",
        status_key="profit_learning_decision_packet_status",
        source_error_key="profit_learning_decision_packet_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="historical_scorecard_review",
        rel_path="cost_gate_learning_lane/historical_scorecard_review_latest.json",
        artifact_class="diagnostic_view",
        role="historical_counterfactual_diagnostic_only",
        status_key="historical_scorecard_review_status",
        source_error_key="historical_scorecard_review_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="profitability_path_scorecard",
        rel_path="alpha_discovery_throughput/profitability_path_scorecard_latest.json",
        artifact_class="dashboard_view",
        role="cross_path_economics_closure",
        present_key="profitability_path_scorecard_present",
        source_ok_key="profitability_path_scorecard_source_ok",
        status_key="profitability_path_scorecard_status",
        source_error_key="profitability_path_scorecard_source_error",
    ),
    PhysicalArtifactSpec(
        artifact_id="alpha_discovery_killboard",
        rel_path="alpha_discovery_throughput/alpha_discovery_latest.json",
        artifact_class="dashboard_view",
        role="killboard_worklist_current_next_actions",
    ),
)


SPINE_NODE_SPECS: tuple[SpineNodeSpec, ...] = (
    SpineNodeSpec(
        node_id="blocked_signal_counterfactual_evidence",
        interface_role="raw blocked-signal after-cost markout evidence",
        member_artifact_ids=("cost_gate_reject_counterfactual",),
        counts_as_alpha_evidence=True,
        required_artifact_ids=("cost_gate_reject_counterfactual",),
    ),
    SpineNodeSpec(
        node_id="probe_ledger",
        interface_role="append-only learning lineage and outcomes",
        member_artifact_ids=("probe_ledger",),
        counts_as_alpha_evidence=True,
        required_artifact_ids=("probe_ledger",),
    ),
    SpineNodeSpec(
        node_id="learning_stack_readiness",
        interface_role="source writer loop readiness, not alpha evidence",
        member_artifact_ids=("activation_preflight",),
        counts_as_alpha_evidence=False,
        required_artifact_ids=("activation_preflight",),
    ),
    SpineNodeSpec(
        node_id="blocked_outcome_review",
        interface_role="false-negative, edge-amplification, keep-blocked classifier",
        member_artifact_ids=(
            "blocked_outcome_review",
            "false_negative_candidate_packet",
        ),
        counts_as_alpha_evidence=True,
        required_artifact_ids=("blocked_outcome_review",),
    ),
    SpineNodeSpec(
        node_id="bounded_demo_probe_readiness",
        interface_role=(
            "candidate-matched preflight, touchability, authorization lineage, "
            "probe result, and execution-realism review"
        ),
        member_artifact_ids=(
            "sealed_horizon_probe_preflight",
            "bounded_probe_operator_authorization",
            "bounded_probe_shadow_placement_impact",
            "bounded_probe_result_review",
            "bounded_probe_execution_realism_review",
        ),
        counts_as_alpha_evidence=True,
        required_artifact_ids=(
            "sealed_horizon_probe_preflight",
            "bounded_probe_operator_authorization",
            "bounded_probe_shadow_placement_impact",
            "bounded_probe_result_review",
            "bounded_probe_execution_realism_review",
        ),
    ),
    SpineNodeSpec(
        node_id="profitability_path_scorecard",
        interface_role="cross-path economics closure and prioritization",
        member_artifact_ids=("profitability_path_scorecard",),
        counts_as_alpha_evidence=False,
        required_artifact_ids=("profitability_path_scorecard",),
    ),
    SpineNodeSpec(
        node_id="alpha_discovery_worklist",
        interface_role="current killboard and next action view",
        member_artifact_ids=("alpha_discovery_killboard",),
        counts_as_alpha_evidence=False,
        required_artifact_ids=("alpha_discovery_killboard",),
    ),
)


def _bool_from_detail(detail: dict[str, Any], key: str | None) -> bool | None:
    if not key or key not in detail:
        return None
    value = detail.get(key)
    return value if isinstance(value, bool) else None


def _read_json_head(path: Path) -> tuple[dict[str, Any], str | None]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return {}, f"malformed:{type(exc).__name__}"
    if not isinstance(payload, dict):
        return {}, "not_object"
    return {
        "schema_version": payload.get("schema_version"),
        "status": payload.get("status"),
        "generated_at_utc": payload.get("generated_at_utc"),
    }, None


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


def _artifact_age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    return max(0.0, (now_utc - parsed).total_seconds())


def _status_is_bad(value: Any) -> bool:
    return str(value or "").strip().upper() in _BAD_STATUS_VALUES


def _status_upper(value: Any) -> str:
    return str(value or "").strip().upper()


def _file_present(path: Path) -> bool:
    try:
        return path.exists()
    except OSError:
        return False


def _non_json_file_error(path: Path) -> str | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        return "missing"
    except OSError as exc:
        return f"read_error:{type(exc).__name__}"
    return "empty" if stat.st_size <= 0 else None


def _artifact_entry(
    spec: PhysicalArtifactSpec,
    *,
    data_dir: Path,
    detail: dict[str, Any],
    now_utc: dt.datetime | None,
    max_age_seconds: int,
) -> dict[str, Any]:
    path = data_dir / spec.rel_path
    json_head: dict[str, Any] = {}
    file_error: str | None = None
    if path.suffix == ".json":
        json_head, file_error = _read_json_head(path)
    else:
        file_error = _non_json_file_error(path)

    detail_present = _bool_from_detail(detail, spec.present_key)
    present = detail_present if detail_present is not None else file_error != "missing"
    detail_status = detail.get(spec.status_key) if spec.status_key else None
    status = detail_status if detail_status is not None else json_head.get("status")
    detail_error = detail.get(spec.source_error_key) if spec.source_error_key else None
    source_error = detail_error if detail_error is not None else file_error
    generated_at = json_head.get("generated_at_utc")
    age_seconds = (
        _artifact_age_seconds(generated_at, now_utc=now_utc)
        if now_utc is not None
        else None
    )
    freshness_error = (
        "stale_artifact"
        if age_seconds is not None and age_seconds > max_age_seconds
        else None
    )
    if source_error is None and freshness_error is not None:
        source_error = freshness_error

    detail_source_ok = _bool_from_detail(detail, spec.source_ok_key)
    if detail_source_ok is not None:
        source_ok = (
            detail_source_ok
            and present
            and source_error is None
            and not _status_is_bad(status)
        )
    else:
        source_ok = (
            present
            and source_error is None
            and not _status_is_bad(status)
        )

    return {
        "artifact_id": spec.artifact_id,
        "artifact_class": spec.artifact_class,
        "role": spec.role,
        "path": str(path),
        "present": bool(present),
        "source_ok": bool(source_ok),
        "status": status,
        "source_error": source_error,
        "schema_version": json_head.get("schema_version"),
        "generated_at_utc": generated_at,
        "age_seconds": age_seconds,
        "counts_as_alpha_evidence": spec.counts_as_alpha_evidence,
        "authority_boundary": spec.authority_boundary,
    }


def _spine_node(
    spec: SpineNodeSpec,
    *,
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    members = [
        by_id[artifact_id]
        for artifact_id in spec.member_artifact_ids
        if artifact_id in by_id
    ]
    required_artifact_ids = spec.required_artifact_ids or spec.member_artifact_ids
    required_members = [
        by_id[artifact_id]
        for artifact_id in required_artifact_ids
        if artifact_id in by_id
    ]
    present = [entry for entry in members if entry.get("present") is True]
    required_present = [
        entry for entry in required_members if entry.get("present") is True
    ]
    stale = [
        entry
        for entry in present
        if entry.get("source_ok") is not True
    ]
    stale_required = [
        entry
        for entry in required_present
        if entry.get("source_ok") is not True
    ]
    missing_required = [
        entry["artifact_id"]
        for entry in required_members
        if entry.get("present") is not True
    ]
    return {
        "node_id": spec.node_id,
        "interface_role": spec.interface_role,
        "member_artifact_ids": list(spec.member_artifact_ids),
        "required_artifact_ids": list(required_artifact_ids),
        "present_member_count": len(present),
        "required_present_member_count": len(required_present),
        "stale_or_unreadable_member_count": len(stale),
        "missing_required_artifact_ids": missing_required,
        "counts_as_alpha_evidence": spec.counts_as_alpha_evidence,
        "node_ready": (
            len(required_present) == len(required_members)
            and not stale_required
        ),
    }


def _int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _active_state(
    *,
    detail: dict[str, Any],
    by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    false_negative_packet = by_id.get("false_negative_candidate_packet", {})
    blocked_review = by_id.get("blocked_outcome_review", {})
    false_negative_packet_status = _status_upper(false_negative_packet.get("status"))
    false_negative_packet_present = (
        false_negative_packet.get("present") is True
    )
    false_negative_packet_source_ok = (
        false_negative_packet.get("source_ok") is True
    )
    false_negative_operator_ready = (
        detail.get("false_negative_candidate_packet_operator_review_ready") is True
    )
    false_negative_queue_ready = (
        false_negative_packet_status == FALSE_NEGATIVE_CANDIDATES_READY_STATUS
        and false_negative_packet_source_ok
        and false_negative_operator_ready
    )

    blocked_review_status = _status_upper(blocked_review.get("status"))
    blocked_review_source_ok = blocked_review.get("source_ok") is True
    blocked_outcome_review_candidate_ready = (
        blocked_review_status == BLOCKED_OUTCOME_REVIEW_CANDIDATES_STATUS
        and blocked_review_source_ok
    )

    stale_downstream_probe_artifact_ids = [
        artifact_id
        for artifact_id in DOWNSTREAM_PROBE_ARTIFACT_IDS
        if by_id.get(artifact_id, {}).get("present") is True
        and by_id.get(artifact_id, {}).get("source_ok") is not True
    ]

    return {
        "schema_version": ACTIVE_STATE_SCHEMA_VERSION,
        "interface_role": (
            "artifact-spine active-loop state consumed by discovery_loop"
        ),
        "blocked_outcome_review_candidate_ready": (
            blocked_outcome_review_candidate_ready
        ),
        "blocked_outcome_review_status": blocked_review_status or None,
        "blocked_outcome_review_source_ok": blocked_review_source_ok,
        "false_negative_candidate_packet_present": (
            false_negative_packet_present
        ),
        "false_negative_candidate_packet_source_ok": (
            false_negative_packet_source_ok
        ),
        "false_negative_candidate_packet_status": (
            false_negative_packet_status or None
        ),
        "false_negative_candidate_packet_operator_review_ready": (
            false_negative_operator_ready
        ),
        "false_negative_queue_ready": false_negative_queue_ready,
        "false_negative_candidate_packet_refresh_required": (
            false_negative_packet_present
            and not false_negative_packet_source_ok
        ),
        "stale_downstream_probe_artifact_ids": (
            stale_downstream_probe_artifact_ids
        ),
        "global_cost_gate_lowering_recommended": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "promotion_evidence": False,
    }


def build_cost_gate_artifact_spine(
    *,
    data_dir: Path,
    detail: dict[str, Any],
    now_utc: dt.datetime | None = None,
    max_age_seconds: int = DEFAULT_ARTIFACT_SPINE_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    """Build the logical active artifact spine for Cost Gate learning."""
    physical_entries = [
        _artifact_entry(
            spec,
            data_dir=data_dir,
            detail=detail,
            now_utc=now_utc,
            max_age_seconds=max_age_seconds,
        )
        for spec in PHYSICAL_ARTIFACT_SPECS
    ]
    by_id = {entry["artifact_id"]: entry for entry in physical_entries}
    nodes = [_spine_node(spec, by_id=by_id) for spec in SPINE_NODE_SPECS]
    active_state = _active_state(detail=detail, by_id=by_id)

    governance_stale = [
        entry["artifact_id"]
        for entry in physical_entries
        if entry["artifact_class"]
        in {"governance", "probe_governance", "dashboard_view"}
        and entry["present"]
        and entry["source_ok"] is not True
    ]
    evidence_stale = [
        entry["artifact_id"]
        for entry in physical_entries
        if entry["counts_as_alpha_evidence"]
        and entry["present"]
        and entry["source_ok"] is not True
    ]
    fill_backed_available = (
        detail.get(
            "bounded_probe_execution_realism_review_fill_backed_probe_execution_available"
        )
        is True
    )
    matched_control_present = (
        detail.get("bounded_probe_result_review_matched_control_present") is True
    )
    completed_probe_outcomes = _int(
        detail.get("bounded_probe_result_review_completed_probe_outcome_count")
    )
    probe_result_learning_valid = (
        fill_backed_available
        and matched_control_present
        and completed_probe_outcomes > 0
    )
    proof_gap = None if probe_result_learning_valid else (
        "candidate_matched_fill_backed_matched_control_probe_result_missing"
    )

    node_counts: dict[str, int] = {}
    artifact_class_counts: dict[str, int] = {}
    for node in nodes:
        key = "ready" if node["node_ready"] else "not_ready"
        node_counts[key] = node_counts.get(key, 0) + 1
    for entry in physical_entries:
        artifact_class = str(entry["artifact_class"])
        artifact_class_counts[artifact_class] = (
            artifact_class_counts.get(artifact_class, 0) + 1
        )

    active_alpha_nodes = [
        node["node_id"]
        for node in nodes
        if node["counts_as_alpha_evidence"] is True
    ]
    ready_alpha_nodes = [
        node["node_id"]
        for node in nodes
        if node["counts_as_alpha_evidence"] is True and node["node_ready"] is True
    ]

    return {
        "schema_version": COST_GATE_ARTIFACT_SPINE_SCHEMA_VERSION,
        "policy": (
            "active_loop_uses_logical_spine; governance_dashboard_smoke_artifacts_"
            "are_not_alpha_evidence"
        ),
        "summary": {
            "spine_node_count": len(nodes),
            "ready_spine_node_count": node_counts.get("ready", 0),
            "alpha_evidence_node_count": len(active_alpha_nodes),
            "ready_alpha_evidence_node_count": len(ready_alpha_nodes),
            "physical_artifact_count": len(physical_entries),
            "artifact_class_counts": artifact_class_counts,
            "governance_stale_or_unreadable_artifact_ids": governance_stale,
            "alpha_evidence_stale_or_unreadable_artifact_ids": evidence_stale,
            "probe_result_learning_valid": probe_result_learning_valid,
            "proof_gap": proof_gap,
            "active_state": active_state,
            "global_cost_gate_lowering_recommended": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "spine_nodes": nodes,
        "physical_artifacts": physical_entries,
        "archive_policy": {
            "timestamped_runs": "lineage_only_not_active_interface",
            "markdown_mirrors": "operator_readable_view_not_decision_artifact",
            "codex_smoke": "smoke_history_not_canonical_latest",
            "old_nested_latest": "archive_or_replay_input_not_active_loop",
        },
    }


def summarize_cost_gate_artifact_spine(spine: dict[str, Any] | None) -> dict[str, Any]:
    """Return a compact killboard-safe summary of the spine."""
    if not isinstance(spine, dict):
        return {}
    summary = spine.get("summary")
    return summary if isinstance(summary, dict) else {}


__all__ = [
    "ACTIVE_STATE_SCHEMA_VERSION",
    "COST_GATE_ARTIFACT_SPINE_SCHEMA_VERSION",
    "build_cost_gate_artifact_spine",
    "summarize_cost_gate_artifact_spine",
]

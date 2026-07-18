#!/usr/bin/python3
"""Exact-input observer for the current-head ALR reconciliation and two cycles.

This program is read-only.  It delegates the established service, source, Git,
singleton, PostgreSQL and durable-decision checks to the hash-pinned v1 observer,
while replacing its retired generation constants with one O_EXCL-created,
exact-hash-bound observer input.
"""

from __future__ import annotations

import ast
import copy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import types
from typing import Any, Callable, Mapping, Sequence


SCHEMA = "p0b_alr_current_head_two_cycle_observer_v2"
INPUT_SCHEMA = "p0b_alr_current_head_observer_input_v2"
CONSUMER_SOURCE_PATH = Path(
    "/home/ncyu/BybitOpenClaw/srv/program_code/ml_training/alr_event_consumer.py"
)
UNIT_NAME = "openclaw-alr-shadow.service"
UNIT_PATH = Path("/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service")
COST_OWNER = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/locks/"
    "cost_gate_learning_lane_cron.owner.owner.json"
)
SYSTEMD = "/usr/bin/systemctl"
MAX_INPUT_BYTES = 256 * 1024
BASE_OBSERVER_SHA256 = (
    "30a944020767bad5c5dd35d2df4d7a6f7f8b2a87fefea086e276b32fa0b002ed"
)
BASE_OBSERVER_NAME = "p0b_alr_two_natural_cycle_observer_v1.py"
MAX_ARTIFACT_BYTES = 2 * 1024 * 1024

STARTUP_RECONCILIATION_SQL = (
    "WITH first_notification AS ("
    "SELECT event_id,recorded_at FROM learning.alr_consumer_events "
    "WHERE session_id=%s::uuid AND event_kind='NOTIFICATION_RECEIVED' "
    "ORDER BY recorded_at,event_id LIMIT 1) "
    "SELECT artifact.artifact_hash,artifact.created_at,artifact.canonical_payload,"
    "notification.event_id AS first_notification_event_id,"
    "notification.recorded_at AS first_notification_recorded_at "
    "FROM learning.alr_artifact_nodes AS artifact CROSS JOIN first_notification AS notification "
    "WHERE artifact.artifact_kind IN ('target_rotation','learning_target') "
    "AND artifact.created_at >= %s AND artifact.created_at < notification.recorded_at "
    "AND artifact.canonical_payload->>'schema_version'="
    "'alr_candidate_learning_projection_artifact_v2' "
    "AND artifact.canonical_payload#>>'{decision,source_head}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,source_content_sha256}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,board_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,audit_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,selection_hash}'=%s "
    "AND artifact.canonical_payload#>>'{source_refs,handoff,evidence,candidate_set_hash}'=%s "
    "ORDER BY artifact.created_at,artifact.artifact_hash LIMIT 2"
)
HEX64_RE = re.compile(r"[0-9a-f]{64}")
HEX40_RE = re.compile(r"[0-9a-f]{40}")
HEX32_RE = re.compile(r"[0-9a-f]{32}")
CANONICAL_Q18_RE = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{18}")

CANDIDATE_SELECTION_FIELDS = (
    "schema_version",
    "candidate_id",
    "candidate_family_key",
    "stable_cohort_hash",
    "candidate_identity",
    "identity_complete",
    "arbiter_input",
    "arbiter_input_complete",
    "selection_eligible",
    "blockers",
)
CANDIDATE_BOARD_AUDIT_FIELDS = (
    "lineage_partition_complete",
    "raw_blocked_outcome_row_count",
    "qualified_lineage_outcome_row_count",
    "unqualified_lineage_outcome_row_count",
    "invalid_lineage_outcome_row_count",
    "invalid_exact_cohort_row_count",
    "invalid_identity_family_row_count",
    "unassigned_invalid_lineage_outcome_row_count",
    "unqualified_raw_valid_evaluation_missing_row_count",
    "unqualified_event_outside_evaluation_window_row_count",
    "consistent_duplicate_event_hash_extra_row_count",
    "conflicting_duplicate_event_hash_row_count",
    "conflicting_duplicate_event_hash_attribution_row_count",
    "lineage_exclusion_reason_counts",
)
CANDIDATE_BOARD_FIELDS = {
    "schema_version",
    "as_of_utc_date",
    "candidate_universe_complete",
    *CANDIDATE_BOARD_AUDIT_FIELDS,
    "candidate_rows",
    "selection_hash",
    "audit_hash",
    "board_hash",
}
CANDIDATE_ROW_FIELDS = set(
    """
schema_version candidate_id candidate_family_key stable_cohort_hash candidate_identity
identity_complete arbiter_input arbiter_input_complete selection_eligible
qualified_metrics_actionable metrics_scope blockers side_cell_key horizon_minutes
qualified_raw_outcome_count qualified_evaluator_input_count qualified_uncensored_outcome_count
qualified_valid_uncensored_outcome_count qualified_invalid_outcome_row_count
qualified_censored_outcome_count consistent_duplicate_event_hash_extra_row_count
conflicting_event_hash_row_count duplicate_event_hash_outcome_conflict_row_count
duplicate_event_hash_cohort_conflict_row_count invalid_lineage_exact_cohort_row_count
invalid_lineage_identity_family_row_count lineage_blocker_reason_counts
qualified_distinct_entry_observation_count qualified_duplicate_outcome_row_count
qualified_window_overlap_excluded_entry_count qualified_entry_ts_missing_row_count n_eff
distinct_entry_utc_days entry_day_counts top_entry_utc_day top_entry_day_share
top_entry_day_share_pct censored_share censored_pct replica_inconsistent_group_count
zero_variance_suspect data_integrity_suspect cluster_variance_clean day_cluster_variance
cluster_se cluster_count legacy_optimistic_cost_present avg_net_bps mean_net_e cost_basis_main
expected_cost_recomputable_count expected_cost_recomputable_share cost_recomputable_share
tail_cost_recomputable_count tail_cost_recomputable_share avg_expected_cost_bps
avg_tail_cost_bps tail_metric regime_entry_counts regime_coverage_inputs
hidden_oos_consumed
""".split()
)
CANDIDATE_LINEAGE_REASONS = {
    "UNQUALIFIED_CONTEXT_MISSING",
    "UNQUALIFIED_LEGACY_PROJECTION_ONLY",
    "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING",
    "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW",
    "INVALID_LINEAGE_RAW_CONTEXT_INVALID",
    "INVALID_LINEAGE_IDENTITY_FAMILY",
    "INVALID_LINEAGE_EXACT_COHORT",
}
CANDIDATE_IDENTITY_ORDER_FIELDS = (
    "strategy_name",
    "strategy_version",
    "strategy_config_hash",
    "symbol",
    "side",
    "horizon_minutes",
    "target_regime_hash",
    "venue",
    "product",
    "engine_mode",
)
CANDIDATE_METRIC_FIELDS = {
    "n_eff",
    "median_distinct_entries_7d",
    "expected_new_entries",
    "information_gain",
    "gate_progress",
    "ambiguity",
    "quality",
    "compute",
    "storage",
    "resource",
    "portfolio_redundancy",
    "day_coverage",
    "day_deficit",
    "regime_coverage",
    "regime_deficit",
    "bull_share",
    "evi",
}
CANDIDATE_SCANNER_CONTEXT_FIELDS = {"novelty", "recurrence"}
CANDIDATE_METRICS_ASSESSMENT_FIELDS = {
    "family_key",
    "evaluation_id",
    "material_fingerprint",
    "identity",
    "context_hashes",
    "proof_stage",
    "next_gap",
    "learning_only",
    "state",
    "eligible",
    "blocker_codes",
    "portfolio_assumption",
    "scanner_context",
    "metrics",
    "rank",
}
CANDIDATE_INELIGIBLE_ASSESSMENT_FIELDS = {
    "family_key",
    "evaluation_id",
    "material_fingerprint",
    "identity",
    "state",
    "eligible",
    "blocker_codes",
    "portfolio_assumption",
    "scanner_context",
    "metrics",
    "rank",
}
CANDIDATE_SELECTION_VIEW_FIELDS = {
    "family_key",
    "candidate_family_key",
    "evaluation_id",
    "candidate_eval_id",
    "material_fingerprint",
    "state",
    "identity",
    "context_hashes",
    "proof_stage",
    "next_gap",
    "blocker_codes",
    "metrics",
    "portfolio_assumption",
    "learning_only",
    "evi",
}

INPUT_FIELDS = {
    "schema_version",
    "target_head",
    "observer_not_before_utc",
    "active_identity",
    "phase1_receipt",
    "cutover_authorization",
    "provisional_cutover",
    "admitted_board",
    "runtime_files",
    "consumer_source",
    "git_seals",
    "private_deps",
    "no_authority",
}

GOVERNANCE_BINDING_FIELDS = {
    "compiled_route_schema",
    "context_artifact_schema",
    "compiled_route_digest",
    "route_dag_digest",
    "pm_context_artifact_digest",
    "pa_context_artifact_digest",
    "e3_context_artifact_digest",
    "ops_preflight_context_artifact_digest",
    "pa_role_fragment_digest",
    "pa_command_capture_digest",
    "e3_role_fragment_digest",
    "e3_command_capture_digest",
    "ops_preflight_role_fragment_digest",
    "ops_preflight_command_capture_digest",
    "ops_preflight_attestation_digest",
    "ops_preflight_observed_at",
    "ops_preflight_expires_at",
    "pm_approval_artifact_digest",
    "authorized_argv_digest",
    "protected_baseline_digest",
    "phase_runtime_bindings_artifact_digest",
    "phase_runtime_bindings_path",
}
CUTOVER_CLAIM_FIELDS = {
    "p0b_effect_adapter_selection",
    "p0b_adapter_source",
    "p0b_adapter_tests",
    "p0b_base_adapter_source",
    "p0b_generation_apply_source",
    "p0b_observer_source",
    "p0b_observer_tests",
    "p0b_observer_dependency_source",
    "p0b_phase1_task_contract",
    "p0b_phase1_route",
    "p0b_phase1_context_artifact",
    "p0b_phase1_intent",
    "p0b_phase1_receipt",
    "p0b_phase1_closure",
    "p0b_sealed_lineage_bundle",
    "p0b_private_bundle_receipt",
    "p0b_private_bundle_destination",
    "p0b_target_source_attestation",
    "p0b_completion_inventory",
    "p0b_producer_inventory",
    "p0b_live_inventory",
    "p0b_protected_runtime_baseline",
    "p0b_staged_candidate_board",
    "p0b_phase_runtime_bindings",
    "p0b_runtime_source_binding",
    "p0b_runtime_protected_binding",
    "p0b_runtime_paths_binding",
    "p0b_runtime_inventories_binding",
    "p0b_runtime_lineage_binding",
}
STAGE_CLAIM_FIELDS = {
    "p0b_effect_adapter_selection",
    "p0b_adapter_source",
    "p0b_adapter_tests",
    "p0b_base_adapter_source",
    "p0b_generation_apply_source",
    "p0b_private_bundle_stager_source",
    "p0b_private_bundle_stager_tests",
    "p0b_private_bundle_source_manifest",
    "p0b_private_bundle_destination_absent_attestation",
    "p0b_target_source_attestation",
    "p0b_completion_inventory",
    "p0b_producer_inventory",
    "p0b_live_inventory",
    "p0b_protected_runtime_baseline",
    "p0b_p0a_completed_board_input",
    "p0b_phase_runtime_bindings",
    "p0b_runtime_source_binding",
    "p0b_runtime_protected_binding",
    "p0b_runtime_paths_binding",
    "p0b_runtime_inventories_binding",
    "p0b_runtime_lineage_binding",
}
RUNTIME_BINDING_FIELDS = {
    "schema_version", "phase", "intent_id", "target_head",
    "source_attestation", "protected_runtime_baseline", "phase_paths",
    "inventories", "lineage", "section_claims", "observed_at", "expires_at",
    "artifact_digest",
}
RUNTIME_BINDING_SECTIONS = {
    "source_attestation": "p0b_runtime_source_binding",
    "protected_runtime_baseline": "p0b_runtime_protected_binding",
    "phase_paths": "p0b_runtime_paths_binding",
    "inventories": "p0b_runtime_inventories_binding",
    "lineage": "p0b_runtime_lineage_binding",
}
PHASE1_CLOSURE_FIELDS = {
    "schema_version",
    "status",
    "phase",
    "intent_id",
    "intent_digest",
    "task_contract_digest",
    "compiled_route_digest",
    "context_artifact_digest",
    "stage_authorization_digest",
    "stage_runtime_bindings_artifact_digest",
    "phase1_effect_receipt_digest",
    "phase_result_digest",
    "ops_postcheck",
    "ops_postcheck_digest",
    "closed_at_utc",
    "closure_digest",
}
OPS_POSTCHECK_FIELDS = {
    "schema_version",
    "adapter_id",
    "phase",
    "intent_id",
    "intent_digest",
    "task_contract_digest",
    "context_artifact_digest",
    "compiled_route_digest",
    "source_head",
    "target_host",
    "target_user_unit",
    "effect_receipt_digest",
    "phase_result_digest",
    "observer_receipt_digest",
    "observed_at",
    "expires_at",
    "verified",
    "operation_digest",
}
PHASE1_LINEAGE_BUNDLE_FIELDS = {
    "schema_version",
    "target_head",
    "intent_id",
    "intent_digest",
    "task_contract_digest",
    "compiled_route_digest",
    "context_artifact_digest",
    "stage_authorization",
    "stage_authorization_digest",
    "stage_runtime_bindings",
    "stage_runtime_bindings_artifact_digest",
    "phase1_effect_receipt",
    "phase1_effect_receipt_digest",
    "phase1_closure",
    "phase1_closure_digest",
    "private_deps_receipt",
    "private_deps_destination",
    "private_deps_manifest_sha256",
    "staged_board",
    "bundle_digest",
}
SOURCE_ATTESTATION_FIELDS = {"source", "execution_tree", "source_tree_digest"}
PROTECTED_BASELINE_FIELDS = {
    "service_baseline", "protected", "protected_digest",
    "pin_consumer_inventory", "pin_consumer_inventory_digest",
    "runtime_identity", "runtime_identity_digest",
}
INVENTORY_FIELDS = {
    "live_inventory", "live_inventory_digest", "completion_inventory",
    "completion_inventory_digest", "producer_inventory",
    "producer_inventory_digest", "ledger_inventory", "ledger_inventory_digest",
    "lane_effective_config", "lane_effective_config_digest",
}
RUNTIME_RECOVERY_ROOT = Path(
    "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_recovery/"
    "alr-current-head-rollforward"
)
STAGING_ROOT = RUNTIME_RECOVERY_ROOT / "staging"
AUTHORIZATION_FIELDS = {
    "schema_version", "adapter_id", "phase", "intent_id", "intent_digest",
    "task_contract_digest", "context_artifact_digest", "governance_bindings",
    "claim_bindings", "expected_source_head", "expected_origin_main_head",
    "expected_old_runtime_source_head", "expected_old_pin_digest",
    "expected_source_tree_digest", "expected_pin_consumer_inventory_digest",
    "expected_runtime_identity_digest", "target_host", "target_environment",
    "target_user_unit", "require_clean_tree", "require_fresh_origin_main",
    "phase1_effect_receipt_digest", "phase1_closure_digest",
    "sealed_lineage_bundle_digest", "private_bundle_destination",
    "observer_requirement", "approved_by", "approved_at", "expires_at",
    "typed_confirm", "hard_stops", "authorization_digest",
}
CUTOVER_HARD_STOPS = [
    "phase-scoped P0-B ALR effect only",
    "no live/mainnet authority expansion",
    "no order/broker/decision-lease effect",
    "no unrelated service or user-manager mutation",
    "no ambient environment or secret inheritance",
    (
        "only fresh public Git origin read, normal-lane readonly PG, and existing "
        "fixed-path credential load are allowed"
    ),
    (
        "no broker/private external contact, package installation, or adapter "
        "credential-content read"
    ),
    "fail closed; never restore the old generation after cutover begins",
    "cutover finalizes only after OBSERVER_V2_EXACT_POSTCHECK_PASS",
]


class ObserverInputError(RuntimeError):
    """An exact observer-input admission check failed."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ObserverInputError("input_not_canonicalizable") from exc


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def candidate_audit_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    selection_fields = set(CANDIDATE_SELECTION_FIELDS)
    projected = [
        {
            "candidate_id": row["candidate_id"],
            **{
                key: copy.deepcopy(value)
                for key, value in row.items()
                if key not in selection_fields and key != "candidate_id"
            },
        }
        for row in rows
    ]
    return sorted(projected, key=lambda row: row["candidate_id"])


def _candidate_row_order_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    identity = row.get("candidate_identity")
    if not isinstance(identity, Mapping) or set(identity) != set(
        CANDIDATE_IDENTITY_ORDER_FIELDS
    ):
        raise ObserverInputError("candidate_identity_fields_invalid")
    return (
        *(identity[field] for field in CANDIDATE_IDENTITY_ORDER_FIELDS),
        row["candidate_id"],
        row["stable_cohort_hash"],
    )


def validate_dynamic_candidate_board(
    config: Mapping[str, Any], board_outer: Mapping[str, Any]
) -> dict[str, Any]:
    """Validate the current board without inheriting v1's empty-board constant."""

    checked = validate_observer_input_payload(config)
    admitted = checked["admitted_board"]
    if (
        not isinstance(board_outer, Mapping)
        or board_outer.get("schema_version")
        != "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
        or board_outer.get("candidate_board_generation_state") != "COMPLETE"
        or board_outer.get("ledger_scan_status") != "COMPLETE"
        or board_outer.get("latest_alias_used", False) is not False
        or board_outer.get("generated_at_utc") != admitted["generated_at_utc"]
    ):
        raise ObserverInputError("board_outer_semantics_invalid")
    board = _exact_fields(
        board_outer.get("learning_candidate_board"),
        CANDIDATE_BOARD_FIELDS,
        "board_fields_invalid",
    )
    if (
        board.get("schema_version") != "cost_gate_learning_candidate_board_v2"
        or board.get("candidate_universe_complete") is not True
        or board.get("lineage_partition_complete") is not True
    ):
        raise ObserverInputError("board_semantics_invalid")
    as_of = board.get("as_of_utc_date")
    try:
        parsed_as_of = datetime.strptime(str(as_of), "%Y-%m-%d")
    except ValueError as exc:
        raise ObserverInputError("board_as_of_utc_date_invalid") from exc
    if parsed_as_of.strftime("%Y-%m-%d") != as_of:
        raise ObserverInputError("board_as_of_utc_date_invalid")

    count_fields = CANDIDATE_BOARD_AUDIT_FIELDS[1:-1]
    if any(
        isinstance(board.get(field), bool)
        or not isinstance(board.get(field), int)
        or board[field] < 0
        for field in count_fields
    ):
        raise ObserverInputError("board_count_contract_invalid")
    raw = board["raw_blocked_outcome_row_count"]
    qualified = board["qualified_lineage_outcome_row_count"]
    unqualified = board["unqualified_lineage_outcome_row_count"]
    invalid = board["invalid_lineage_outcome_row_count"]
    if (
        raw != qualified + unqualified + invalid
        or invalid
        != board["invalid_exact_cohort_row_count"]
        + board["invalid_identity_family_row_count"]
        + board["unassigned_invalid_lineage_outcome_row_count"]
    ):
        raise ObserverInputError("board_count_invariants_invalid")
    reasons = board.get("lineage_exclusion_reason_counts")
    if (
        not isinstance(reasons, Mapping)
        or not set(reasons).issubset(CANDIDATE_LINEAGE_REASONS)
        or any(
            not isinstance(key, str)
            or not key
            or isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            for key, value in reasons.items()
        )
        or sum(reasons.values()) != unqualified + invalid
        or reasons.get("INVALID_LINEAGE_EXACT_COHORT", 0)
        != board["invalid_exact_cohort_row_count"]
        or reasons.get("INVALID_LINEAGE_IDENTITY_FAMILY", 0)
        != board["invalid_identity_family_row_count"]
        or reasons.get("INVALID_LINEAGE_RAW_CONTEXT_INVALID", 0)
        != board["unassigned_invalid_lineage_outcome_row_count"]
        or reasons.get("UNQUALIFIED_RAW_VALID_EVALUATION_MISSING", 0)
        != board["unqualified_raw_valid_evaluation_missing_row_count"]
        or reasons.get("UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW", 0)
        != board["unqualified_event_outside_evaluation_window_row_count"]
    ):
        raise ObserverInputError("board_reason_counts_invalid")

    rows = board.get("candidate_rows")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ObserverInputError("candidate_rows_invalid")
    normalized_rows = [dict(row) for row in rows]
    if any(set(row) != CANDIDATE_ROW_FIELDS for row in normalized_rows):
        raise ObserverInputError("candidate_row_fields_invalid")
    if any(
        row.get("schema_version") != "cost_gate_learning_candidate_v2"
        or not isinstance(row.get("candidate_id"), str)
        or not row["candidate_id"]
        or HEX64_RE.fullmatch(str(row.get("candidate_family_key", ""))) is None
        or HEX64_RE.fullmatch(str(row.get("stable_cohort_hash", ""))) is None
        or type(row.get("identity_complete")) is not bool
        or type(row.get("arbiter_input_complete")) is not bool
        or type(row.get("selection_eligible")) is not bool
        or not isinstance(row.get("arbiter_input"), Mapping)
        or not isinstance(row.get("blockers"), list)
        or not all(isinstance(code, str) and code for code in row["blockers"])
        or row["selection_eligible"] is not (not row["blockers"])
        for row in normalized_rows
    ):
        raise ObserverInputError("candidate_row_semantics_invalid")
    integer_row_fields = {
        "qualified_raw_outcome_count",
        "consistent_duplicate_event_hash_extra_row_count",
        "conflicting_event_hash_row_count",
        "invalid_lineage_exact_cohort_row_count",
        "invalid_lineage_identity_family_row_count",
    }
    if any(
        isinstance(row.get(field), bool)
        or not isinstance(row.get(field), int)
        or row[field] < 0
        for row in normalized_rows
        for field in integer_row_fields
    ):
        raise ObserverInputError("candidate_row_count_invalid")
    candidate_ids = [row["candidate_id"] for row in normalized_rows]
    if len(candidate_ids) != len(set(candidate_ids)):
        raise ObserverInputError("candidate_id_collision")
    try:
        sorted_rows = sorted(normalized_rows, key=_candidate_row_order_key)
    except (KeyError, TypeError, ValueError) as exc:
        raise ObserverInputError("candidate_rows_order_invalid") from exc
    if normalized_rows != sorted_rows:
        raise ObserverInputError("candidate_rows_order_invalid")
    if (
        sum(row["qualified_raw_outcome_count"] for row in normalized_rows)
        != qualified
        or sum(
            row["invalid_lineage_exact_cohort_row_count"]
            for row in normalized_rows
        )
        > board["invalid_exact_cohort_row_count"]
        or max(
            (
                row["invalid_lineage_identity_family_row_count"]
                for row in normalized_rows
            ),
            default=0,
        )
        > board["invalid_identity_family_row_count"]
    ):
        raise ObserverInputError("board_candidate_totals_invalid")
    duplicate_total = sum(
        row["consistent_duplicate_event_hash_extra_row_count"]
        for row in normalized_rows
    )
    conflict_total = sum(
        row["conflicting_event_hash_row_count"] for row in normalized_rows
    )
    unique_conflict = board["conflicting_duplicate_event_hash_row_count"]
    if (
        duplicate_total != board["consistent_duplicate_event_hash_extra_row_count"]
        or conflict_total
        != board["conflicting_duplicate_event_hash_attribution_row_count"]
        or unique_conflict
        < max(
            (row["conflicting_event_hash_row_count"] for row in normalized_rows),
            default=0,
        )
        or unique_conflict > conflict_total
        or unique_conflict > raw
        or (unique_conflict == 0) != (conflict_total == 0)
    ):
        raise ObserverInputError("board_duplicate_totals_invalid")

    semantic_rows = [
        {field: copy.deepcopy(row[field]) for field in CANDIDATE_SELECTION_FIELDS}
        for row in normalized_rows
    ]
    semantic_rows.sort(key=lambda row: (row["candidate_id"], canonical_sha256(row)))
    selection_hash = canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_selection_v2",
            "candidate_rows": semantic_rows,
        }
    )
    if board.get("selection_hash") != selection_hash:
        raise ObserverInputError("board_selection_hash_mismatch")
    audit_hash = canonical_sha256(
        {
            "schema_version": "cost_gate_learning_candidate_audit_v2",
            **{field: board[field] for field in CANDIDATE_BOARD_AUDIT_FIELDS},
            "candidate_audit_rows": candidate_audit_rows(normalized_rows),
        }
    )
    if board.get("audit_hash") != audit_hash:
        raise ObserverInputError("board_audit_hash_mismatch")
    board_hash = canonical_sha256(
        {key: value for key, value in board.items() if key != "board_hash"}
    )
    if board.get("board_hash") != board_hash:
        raise ObserverInputError("board_hash_mismatch")
    candidate_set_hash = canonical_sha256(semantic_rows)
    expected_bindings = {
        "board_hash": board_hash,
        "audit_hash": audit_hash,
        "selection_hash": selection_hash,
        "candidate_set_hash": candidate_set_hash,
    }
    if any(admitted[key] != value for key, value in expected_bindings.items()):
        mismatched = next(
            key for key, value in expected_bindings.items() if admitted[key] != value
        )
        raise ObserverInputError(f"board_{mismatched}_mismatch")
    authority_values: list[Any] = []

    def visit_authority(value: Any) -> None:
        if isinstance(value, Mapping):
            for key, nested in value.items():
                lowered = str(key).lower()
                if "authority" in lowered and any(
                    token in lowered
                    for token in ("order", "probe", "promotion", "runtime")
                ):
                    authority_values.append(nested)
                visit_authority(nested)
        elif isinstance(value, list):
            for nested in value:
                visit_authority(nested)

    visit_authority(board_outer)
    if any(
        value not in (False, "NOT_GRANTED", 0, None, [])
        for value in authority_values
    ):
        raise ObserverInputError("board_authority_grant_present")
    return {
        "candidate_count": len(normalized_rows),
        "qualified_lineage_outcome_row_count": qualified,
        "candidate_universe_complete": True,
        "candidate_rows": copy.deepcopy(normalized_rows),
        **expected_bindings,
    }


def _canonical_q18(value: Any) -> bool:
    if not isinstance(value, str) or CANONICAL_Q18_RE.fullmatch(value) is None:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and format(parsed, "f") == value


def _candidate_assessment_rank_key(item: Mapping[str, Any]) -> tuple[Any, ...]:
    priority = {
        "DECISION_READY": 0,
        "COLLECT_DISTINCT_ENTRIES": 1,
        "REPAIR_DATA_QUALITY": 2,
        "WAIT_COOLDOWN": 3,
        "EXTERNAL_GAP": 4,
        "INELIGIBLE": 5,
    }.get(item.get("state"), 6)
    metrics = item.get("metrics")
    family_key = str(item.get("family_key", "~"))
    evaluation_id = str(item.get("evaluation_id", "~"))
    canonical_tie = canonical_sha256(
        {key: value for key, value in item.items() if key != "rank"}
    )
    slots: list[Any] = [Decimal(0)] * 10
    if not isinstance(metrics, Mapping):
        return (
            priority,
            Decimal(1),
            *slots,
            family_key,
            evaluation_id,
            canonical_tie,
        )
    if item.get("state") == "DECISION_READY":
        slots = [
            -int(item["proof_stage"]),
            -Decimal(metrics["quality"]),
            -Decimal(metrics["day_coverage"]),
            -Decimal(metrics["regime_coverage"]),
            -Decimal(metrics["evi"]),
            -Decimal(metrics["n_eff"]),
            -Decimal(metrics["ambiguity"]),
            Decimal(metrics["resource"]),
            Decimal(metrics["portfolio_redundancy"]),
            int(bool(item["learning_only"])),
        ]
    elif item.get("state") == "COLLECT_DISTINCT_ENTRIES":
        scanner = item["scanner_context"]
        slots[:7] = [
            -Decimal(metrics["evi"]),
            -Decimal(metrics["day_deficit"]),
            -Decimal(metrics["regime_deficit"]),
            Decimal(metrics["resource"]),
            Decimal(metrics["portfolio_redundancy"]),
            -Decimal(scanner["recurrence"]),
            -Decimal(scanner["novelty"]),
        ]
    else:
        scanner = item["scanner_context"]
        slots[:2] = [-Decimal(metrics["evi"]), -Decimal(scanner["novelty"])]
    return (
        priority,
        Decimal(0),
        *slots,
        family_key,
        evaluation_id,
        canonical_tie,
    )


def candidate_selection_view(assessment: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "family_key",
        "evaluation_id",
        "material_fingerprint",
        "identity",
        "context_hashes",
        "proof_stage",
        "next_gap",
        "blocker_codes",
        "metrics",
        "portfolio_assumption",
        "learning_only",
        "state",
    }
    if not required.issubset(assessment):
        raise ObserverInputError("dynamic_decision_semantics_invalid")
    metrics = assessment.get("metrics")
    if (
        HEX64_RE.fullmatch(str(assessment.get("family_key", ""))) is None
        or HEX64_RE.fullmatch(str(assessment.get("evaluation_id", ""))) is None
        or HEX64_RE.fullmatch(str(assessment.get("material_fingerprint", "")))
        is None
        or not isinstance(assessment.get("identity"), Mapping)
        or not isinstance(assessment.get("context_hashes"), Mapping)
        or type(assessment.get("proof_stage")) is not int
        or assessment["proof_stage"] < 0
        or not isinstance(assessment.get("next_gap"), Mapping)
        or not isinstance(assessment.get("blocker_codes"), list)
        or not all(
            isinstance(code, str) and code for code in assessment["blocker_codes"]
        )
        or not isinstance(metrics, Mapping)
        or "evi" not in metrics
        or not isinstance(assessment.get("portfolio_assumption"), str)
        or type(assessment.get("learning_only")) is not bool
    ):
        raise ObserverInputError("dynamic_decision_semantics_invalid")
    return {
        "family_key": assessment["family_key"],
        "candidate_family_key": assessment["family_key"],
        "evaluation_id": assessment["evaluation_id"],
        "candidate_eval_id": assessment["evaluation_id"],
        "material_fingerprint": assessment["material_fingerprint"],
        "state": assessment["state"],
        "identity": copy.deepcopy(dict(assessment["identity"])),
        "context_hashes": copy.deepcopy(dict(assessment["context_hashes"])),
        "proof_stage": assessment["proof_stage"],
        "next_gap": copy.deepcopy(dict(assessment["next_gap"])),
        "blocker_codes": list(assessment["blocker_codes"]),
        "metrics": copy.deepcopy(dict(metrics)),
        "portfolio_assumption": assessment["portfolio_assumption"],
        "learning_only": assessment["learning_only"],
        "evi": metrics["evi"],
    }


def validate_dynamic_decision_semantics(
    decision: Mapping[str, Any], board: Mapping[str, Any]
) -> dict[str, Any]:
    """Rebuild durable arbiter selection semantics for empty and non-empty boards."""

    assessments = decision.get("evaluated_candidates")
    candidate_count = decision.get("candidate_count")
    eligible_count = decision.get("eligible_candidate_count")
    if (
        decision.get("evidence_source_status") != "READY"
        or decision.get("evidence_selection_hash") != board.get("selection_hash")
        or decision.get("candidate_set_hash") != board.get("candidate_set_hash")
        or not isinstance(assessments, list)
        or not all(isinstance(item, Mapping) for item in assessments)
        or type(candidate_count) is not int
        or candidate_count != len(assessments)
        or candidate_count != board.get("candidate_count")
        or type(eligible_count) is not int
        or HEX64_RE.fullmatch(str(decision.get("policy_hash", ""))) is None
    ):
        raise ObserverInputError("dynamic_decision_semantics_invalid")
    states = {
        "DECISION_READY",
        "COLLECT_DISTINCT_ENTRIES",
        "REPAIR_DATA_QUALITY",
        "WAIT_COOLDOWN",
        "EXTERNAL_GAP",
        "INELIGIBLE",
    }
    for index, assessment in enumerate(assessments, start=1):
        metrics = assessment.get("metrics")
        expected_fields = (
            CANDIDATE_INELIGIBLE_ASSESSMENT_FIELDS
            if metrics is None
            else CANDIDATE_METRICS_ASSESSMENT_FIELDS
        )
        if assessment.get("state") == "WAIT_COOLDOWN" and metrics is not None:
            expected_fields = {*expected_fields, "cooldown_remaining_seconds"}
        scanner = assessment.get("scanner_context")
        if (
            set(assessment) != expected_fields
            or not isinstance(scanner, Mapping)
            or set(scanner) != CANDIDATE_SCANNER_CONTEXT_FIELDS
            or not all(_canonical_q18(value) for value in scanner.values())
            or (
                metrics is not None
                and (
                    not isinstance(metrics, Mapping)
                    or set(metrics) != CANDIDATE_METRIC_FIELDS
                    or not all(_canonical_q18(value) for value in metrics.values())
                    or type(assessment.get("proof_stage")) is not int
                    or not 0 <= assessment["proof_stage"] <= 6
                )
            )
            or type(assessment.get("rank")) is not int
            or assessment["rank"] != index
            or assessment.get("state") not in states
            or type(assessment.get("eligible")) is not bool
            or assessment["eligible"]
            is not (assessment.get("state") == "DECISION_READY")
            or (metrics is None and assessment.get("state") != "INELIGIBLE")
            or (
                "cooldown_remaining_seconds" in expected_fields
                and (
                    type(assessment.get("cooldown_remaining_seconds")) is not int
                    or assessment["cooldown_remaining_seconds"] < 0
                )
            )
        ):
            raise ObserverInputError("dynamic_decision_semantics_invalid")
    try:
        canonical_order = sorted(assessments, key=_candidate_assessment_rank_key)
    except (KeyError, TypeError, ValueError, ArithmeticError, InvalidOperation) as exc:
        raise ObserverInputError("dynamic_decision_semantics_invalid") from exc
    if assessments != canonical_order or eligible_count != sum(
        item["eligible"] is True for item in assessments
    ):
        raise ObserverInputError("dynamic_decision_semantics_invalid")

    ready = [item for item in assessments if item["state"] == "DECISION_READY"]
    collection = [
        item for item in assessments if item["state"] == "COLLECT_DISTINCT_ENTRIES"
    ]
    repair = [item for item in assessments if item["state"] == "REPAIR_DATA_QUALITY"]
    waiting = [item for item in assessments if item["state"] == "WAIT_COOLDOWN"]
    external = [item for item in assessments if item["state"] == "EXTERNAL_GAP"]
    if ready:
        expected_code = "QUALIFIED_CANDIDATE_SELECTED"
    elif collection:
        expected_code = "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES"
    elif repair or any(item.get("metrics") is None for item in assessments):
        expected_code = "NO_QUALIFIED_CANDIDATE_REPAIR_DATA"
    elif waiting:
        expected_code = "NO_QUALIFIED_CANDIDATE_WAIT_COOLDOWN"
    elif external:
        expected_code = "NO_QUALIFIED_CANDIDATE_EXTERNAL_GAP"
    else:
        expected_code = "NO_QUALIFIED_CANDIDATE_ROTATE_RESEARCH_DIRECTION"
    selected = decision.get("selected_candidate")
    collection_target = decision.get("selected_collection_target")
    if decision.get("decision_code") != expected_code:
        raise ObserverInputError("dynamic_decision_semantics_invalid")
    if expected_code == "QUALIFIED_CANDIDATE_SELECTED":
        if (
            collection_target is not None
            or not isinstance(selected, Mapping)
            or set(selected) != CANDIDATE_SELECTION_VIEW_FIELDS
            or dict(selected) != candidate_selection_view(ready[0])
        ):
            raise ObserverInputError("dynamic_decision_semantics_invalid")
    elif expected_code == "NO_QUALIFIED_CANDIDATE_COLLECT_DISTINCT_ENTRIES":
        if (
            selected is not None
            or not isinstance(collection_target, Mapping)
            or set(collection_target) != CANDIDATE_SELECTION_VIEW_FIELDS
            or dict(collection_target) != candidate_selection_view(collection[0])
        ):
            raise ObserverInputError("dynamic_decision_semantics_invalid")
    elif selected is not None or collection_target is not None:
        raise ObserverInputError("dynamic_decision_semantics_invalid")
    return {
        "decision_code": expected_code,
        "candidate_count": candidate_count,
        "eligible_candidate_count": eligible_count,
    }


def _strict_json(raw: bytes, reason: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ObserverInputError(reason)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObserverInputError(reason) from exc
    if not isinstance(value, dict) or canonical_bytes(value) != raw:
        raise ObserverInputError(reason)
    return value


def _decode_json_artifact(raw: bytes, reason: str) -> dict[str, Any]:
    def unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ObserverInputError(reason)
            result[key] = value
        return result

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ObserverInputError(reason) from exc
    if not isinstance(value, dict):
        raise ObserverInputError(reason)
    return value


def read_bound_regular(
    path: Path,
    expected_sha256: str,
    *,
    max_bytes: int = MAX_ARTIFACT_BYTES,
    mode: int | None = None,
    expected_uid: int = 1000,
    expected_gid: int = 1000,
) -> tuple[bytes, dict[str, Any]]:
    digest = _hash(expected_sha256, "bound_artifact_expected_hash_invalid")
    try:
        before = path.lstat()
    except OSError as exc:
        raise ObserverInputError("bound_artifact_unavailable") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or (mode is not None and stat.S_IMODE(before.st_mode) != mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= max_bytes
    ):
        raise ObserverInputError("bound_artifact_identity_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ObserverInputError("bound_artifact_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        raw = b""
        while len(raw) < opened.st_size:
            chunk = os.read(descriptor, min(64 * 1024, opened.st_size - len(raw)))
            if not chunk:
                break
            raw += chunk
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        any(getattr(before, key) != getattr(opened, key) for key in stable)
        or any(getattr(opened, key) != getattr(final, key) for key in stable)
        or len(raw) != opened.st_size
        or hashlib.sha256(raw).hexdigest() != digest
    ):
        raise ObserverInputError("bound_artifact_identity_or_hash_drift")
    return raw, {
        "path": str(path),
        "sha256": digest,
        "dev": opened.st_dev,
        "ino": opened.st_ino,
        "uid": opened.st_uid,
        "gid": opened.st_gid,
        "mode": f"{stat.S_IMODE(opened.st_mode):04o}",
        "nlink": opened.st_nlink,
        "size": opened.st_size,
    }


def observe_stable_regular(path: Path, *, max_bytes: int) -> tuple[bytes, dict[str, Any]]:
    """Observe stable bytes without claiming a pre-existing digest trust root."""
    try:
        before = path.lstat()
    except OSError as exc:
        raise ObserverInputError("observed_regular_unavailable") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
        or not 0 < before.st_size <= max_bytes
    ):
        raise ObserverInputError("observed_regular_identity_invalid")
    descriptor = os.open(
        path,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    stable = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    if any(getattr(before, key) != getattr(opened, key) for key in stable) or any(
        getattr(opened, key) != getattr(final, key) for key in stable
    ):
        raise ObserverInputError("observed_regular_changed")
    raw = b"".join(chunks)
    if len(raw) != opened.st_size:
        raise ObserverInputError("observed_regular_short_read")
    return raw, {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size": opened.st_size,
        "uid": opened.st_uid,
        "gid": opened.st_gid,
        "mode": stat.S_IMODE(opened.st_mode),
        "nlink": opened.st_nlink,
    }


def load_exact_base_observer(
    path: Path | None = None,
    *,
    reader: Callable[..., tuple[bytes, dict[str, Any]]] = read_bound_regular,
) -> Any:
    source_path = path or Path(__file__).with_name(BASE_OBSERVER_NAME)
    raw, _identity = reader(
        source_path,
        BASE_OBSERVER_SHA256,
        mode=None,
        expected_uid=os.getuid(),
        expected_gid=os.getgid(),
    )
    module = types.ModuleType("p0b_current_head_sealed_base_observer_v1")
    module.__file__ = str(source_path)
    try:
        exec(compile(raw, str(source_path), "exec", dont_inherit=True), module.__dict__)
    except Exception as exc:
        raise ObserverInputError("base_observer_load_failed") from exc
    if not callable(getattr(module, "run_observation", None)):
        raise ObserverInputError("base_observer_interface_missing")
    return module


def build_readonly_runtime_module(base_observer: Any, target_head: str) -> Any:
    """Provide only the v1 observer's read-only runtime compatibility surface."""

    base_namespace = types.SimpleNamespace()
    base_namespace.SYSTEM_ENV = dict(base_observer.RECOVERY_BASE_SYSTEM_ENV)
    base_namespace.REPO = base_observer.RECOVERY_REPO_PATH

    class ReadonlyRuntimeBase:
        @staticmethod
        def run(
            argv: Sequence[str],
            *,
            cwd: Path | None = None,
            env: Mapping[str, str] | None = None,
            timeout: int = 60,
        ) -> subprocess.CompletedProcess[str]:
            command = list(argv)
            git_prefix = list(base_observer.RECOVERY_GIT_COMMAND_PREFIX)
            allowed_git = (
                command[: len(git_prefix)] == git_prefix
                and command[len(git_prefix) :]
                in (
                    list(base_observer.RECOVERY_GIT_CONFIG_INVENTORY_ARGS),
                    ["rev-parse", "--shared-index-path"],
                    ["ls-files", "-v", "-z"],
                    ["ls-files", "--stage", "-z"],
                    ["symbolic-ref", "--short", "HEAD"],
                    ["rev-parse", "HEAD"],
                    ["rev-parse", "origin/main"],
                    ["status", "--porcelain=v1", "--untracked-files=all"],
                    ["status", "--porcelain=v1", "--untracked-files=all", "--ignore-submodules=all"],
                )
            )
            show_prefix = [SYSTEMD, "--user", "show", UNIT_NAME]
            allowed_show = (
                command[: len(show_prefix)] == show_prefix
                and len(command[len(show_prefix) :]) % 2 == 0
                and all(
                    command[index] == "-p"
                    and command[index + 1]
                    in {
                        "LoadState",
                        "ActiveState",
                        "SubState",
                        "MainPID",
                        "ExecMainStartTimestampMonotonic",
                        "NRestarts",
                        "InvocationID",
                        "FragmentPath",
                        "DropInPaths",
                        "ControlGroup",
                        "Environment",
                        "NeedDaemonReload",
                    }
                    for index in range(len(show_prefix), len(command), 2)
                )
            )
            allowed = allowed_git or allowed_show or command in (
                [SYSTEMD, "--user", "list-jobs", "--no-legend", "--no-pager"],
                [
                    SYSTEMD,
                    "--user",
                    "list-units",
                    "--type=scope",
                    "--state=active",
                    "--no-legend",
                    "--no-pager",
                ],
            )
            if not allowed:
                raise base_observer.ObserverUnverified(
                    "readonly_runtime_command_not_allowlisted"
                )
            try:
                completed = subprocess.run(
                    command,
                    cwd=cwd,
                    env=dict(env or base_namespace.SYSTEM_ENV),
                    text=True,
                    capture_output=True,
                    timeout=min(timeout, 60),
                    check=False,
                )
            except Exception as exc:
                raise base_observer.ObserverUnverified(
                    "readonly_runtime_command_failed"
                ) from exc
            if completed.returncode != 0:
                raise base_observer.ObserverUnverified(
                    "readonly_runtime_command_nonzero"
                )
            return completed

        def git(self, *args: str) -> str:
            return self.run(
                [*base_observer.RECOVERY_GIT_COMMAND_PREFIX, *args],
                env=dict(base_observer.RECOVERY_HARDENED_GIT_ENV),
            ).stdout.strip()

    base_namespace.RecoveryRuntime = ReadonlyRuntimeBase

    class Runtime(ReadonlyRuntimeBase):
        @staticmethod
        def _service_properties() -> dict[str, str]:
            properties = (
                "LoadState",
                "ActiveState",
                "SubState",
                "MainPID",
                "ExecMainStartTimestampMonotonic",
                "NRestarts",
                "InvocationID",
                "FragmentPath",
                "DropInPaths",
                "ControlGroup",
                "Environment",
                "NeedDaemonReload",
            )
            command = [SYSTEMD, "--user", "show", UNIT_NAME]
            for prop in properties:
                command.extend(("-p", prop))
            raw = ReadonlyRuntimeBase.run(command).stdout
            result: dict[str, str] = {}
            for line in raw.splitlines():
                key, separator, value = line.partition("=")
                if separator != "=" or key not in properties or key in result:
                    raise base_observer.ObserverUnverified(
                        "readonly_service_properties_invalid"
                    )
                result[key] = value
            if set(result) != set(properties):
                raise base_observer.ObserverUnverified(
                    "readonly_service_properties_missing"
                )
            return result

        @staticmethod
        def _process_start_ticks(pid: int) -> str:
            try:
                raw = (Path("/proc") / str(pid) / "stat").read_text()
            except OSError as exc:
                raise base_observer.ObserverUnverified(
                    "readonly_process_stat_unavailable"
                ) from exc
            close = raw.rfind(")")
            fields = raw[close + 2 :].split() if close >= 0 else []
            if len(fields) < 20 or not fields[19].isdigit():
                raise base_observer.ObserverUnverified(
                    "readonly_process_start_ticks_invalid"
                )
            return fields[19]

        def source_snapshot(self) -> dict[str, Any]:
            try:
                boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            except OSError as exc:
                raise base_observer.ObserverUnverified(
                    "readonly_boot_id_unavailable"
                ) from exc
            branch = self.git("symbolic-ref", "--short", "HEAD")
            head = self.git("rev-parse", "HEAD")
            origin_main = ReadonlyRuntimeBase.run(
                [
                    *base_observer.RECOVERY_GIT_COMMAND_PREFIX,
                    "rev-parse",
                    "origin/main",
                ],
                env=dict(base_observer.RECOVERY_HARDENED_GIT_ENV),
            ).stdout.strip()
            status = self.git("status", "--porcelain=v1", "--untracked-files=all")
            if (
                not boot_id
                or os.getuid() != 1000
                or os.getgid() != 1000
                or branch != "main"
                or head != target_head
                or origin_main != target_head
                or status
            ):
                raise base_observer.ObserverFail("runtime_source_generation_drift")
            return {
                "boot_id": boot_id,
                "uid": 1000,
                "gid": 1000,
                "branch": "main",
                "head": target_head,
                "clean": True,
            }

        def alr_active_snapshot(self) -> dict[str, str]:
            observed = self._service_properties()
            pid = observed.get("MainPID", "")
            if not pid.isdigit() or int(pid) <= 0:
                raise base_observer.ObserverFail("readonly_service_pid_invalid")
            observed["ProcessStartTicks"] = self._process_start_ticks(int(pid))
            return observed

        def manager_loaded_alr_head(
            self, *, expected_head: str, require_active: bool
        ) -> dict[str, Any]:
            observed = self._service_properties()
            environment = observed.get("Environment", "").split()
            heads = [
                value.split("=", 1)[1]
                for value in environment
                if value.startswith("ALR_SOURCE_HEAD=")
            ]
            pid = observed.get("MainPID", "")
            if (
                expected_head != target_head
                or require_active is not True
                or heads != [target_head]
                or observed.get("LoadState") != "loaded"
                or observed.get("ActiveState") != "active"
                or observed.get("SubState") != "running"
                or observed.get("NRestarts") != "0"
                or observed.get("FragmentPath") != str(UNIT_PATH)
                or observed.get("DropInPaths") != ""
                or observed.get("NeedDaemonReload") != "no"
                or not pid.isdigit()
                or int(pid) <= 0
            ):
                raise base_observer.ObserverFail("readonly_manager_identity_invalid")
            return {
                "head": target_head,
                "conflicting_generation_environment": [],
                "fragment_path": str(UNIT_PATH),
                "drop_in_paths": "",
                "need_daemon_reload": "no",
                "active_required": True,
                "main_pid": pid,
                "process_start_ticks": self._process_start_ticks(int(pid)),
                "invocation_id": observed.get("InvocationID", ""),
            }

        @staticmethod
        def assert_no_queued_systemd_job() -> dict[str, str]:
            raw = ReadonlyRuntimeBase.run(
                [SYSTEMD, "--user", "list-jobs", "--no-legend", "--no-pager"]
            ).stdout
            if raw.strip():
                raise base_observer.ObserverFail("runtime_systemd_job_not_quiescent")
            return {"status": "NO_QUEUED_JOB", "unit": UNIT_NAME}

        @staticmethod
        def assert_lane_quiescent() -> dict[str, Any]:
            processes: list[int] = []
            for proc in Path("/proc").iterdir():
                if not proc.name.isdigit() or int(proc.name) == os.getpid():
                    continue
                try:
                    command = (proc / "cmdline").read_bytes()
                except OSError:
                    continue
                if b"cost_gate_learning_lane_cron.sh" in command:
                    processes.append(int(proc.name))
            scopes_raw = ReadonlyRuntimeBase.run(
                [
                    SYSTEMD,
                    "--user",
                    "list-units",
                    "--type=scope",
                    "--state=active",
                    "--no-legend",
                    "--no-pager",
                ]
            ).stdout
            scopes = [
                line.split()[0]
                for line in scopes_raw.splitlines()
                if line.strip()
                and line.split()[0].startswith("openclaw-research-cost-")
            ]
            if COST_OWNER.exists() or processes or scopes:
                raise base_observer.ObserverFail("runtime_lane_not_quiescent")
            return {"owner": False, "processes": [], "scopes": []}

    return types.SimpleNamespace(Runtime=Runtime, base=base_namespace)


def load_observer_input(
    path: Path,
    expected_sha256: str,
    *,
    expected_uid: int = 1000,
    expected_gid: int = 1000,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one parent-created O_EXCL input through a stable private file identity.

    O_EXCL is a creation-time fact and cannot be reconstructed from a later
    inode.  The parent integration contract owns that creation receipt; this
    observer independently enforces every property still observable here:
    private mode, owner, one link, no symlink, stable inode and exact bytes.
    """

    digest = _hash(expected_sha256, "observer_input_expected_hash_invalid")
    try:
        before = path.lstat()
    except OSError as exc:
        raise ObserverInputError("observer_input_unavailable") from exc
    if (
        not path.is_absolute()
        or stat.S_ISLNK(before.st_mode)
        or not stat.S_ISREG(before.st_mode)
        or before.st_uid != expected_uid
        or before.st_gid != expected_gid
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_nlink != 1
        or not 0 < before.st_size <= MAX_INPUT_BYTES
    ):
        raise ObserverInputError("observer_input_identity_invalid")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ObserverInputError("observer_input_open_failed") from exc
    try:
        opened = os.fstat(descriptor)
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 64 * 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        final = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    stable_fields = ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
    if (
        any(getattr(before, key) != getattr(opened, key) for key in stable_fields)
        or any(getattr(opened, key) != getattr(final, key) for key in stable_fields)
        or len(raw) != opened.st_size
        or hashlib.sha256(raw).hexdigest() != digest
    ):
        raise ObserverInputError("observer_input_identity_or_hash_drift")
    payload = validate_observer_input_payload(
        _strict_json(raw, "observer_input_json_or_canonical_invalid")
    )
    return payload, {
        "path": str(path),
        "sha256": digest,
        "dev": opened.st_dev,
        "ino": opened.st_ino,
        "uid": opened.st_uid,
        "gid": opened.st_gid,
        "mode": "0600",
        "nlink": opened.st_nlink,
        "size": opened.st_size,
        "parent_o_excl_creation_required": True,
        "parent_o_excl_creation_observed_by_this_process": False,
    }


def _exact_fields(value: Any, fields: set[str], reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise ObserverInputError(reason)
    return value


def _hash(value: Any, reason: str, *, length: int = 64) -> str:
    expression = {64: HEX64_RE, 40: HEX40_RE, 32: HEX32_RE}.get(length)
    if not isinstance(value, str) or expression is None or expression.fullmatch(value) is None:
        raise ObserverInputError(reason)
    return value


def _utc(value: Any, reason: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ObserverInputError(reason)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ObserverInputError(reason) from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ObserverInputError(reason)
    return parsed.astimezone(timezone.utc)


def _binding(value: Any, reason: str) -> dict[str, str]:
    bound = _exact_fields(value, {"path", "sha256"}, reason)
    path = bound.get("path")
    if not isinstance(path, str) or not Path(path).is_absolute() or "\x00" in path:
        raise ObserverInputError(reason)
    return {"path": path, "sha256": _hash(bound.get("sha256"), reason)}


def validate_observer_input_payload(payload: Any) -> dict[str, Any]:
    """Validate and normalize the sole parent-integration input contract."""

    root = _exact_fields(payload, INPUT_FIELDS, "observer_input_fields_invalid")
    if root.get("schema_version") != INPUT_SCHEMA:
        raise ObserverInputError("observer_input_schema_invalid")
    target_head = _hash(root.get("target_head"), "observer_target_head_invalid", length=40)
    not_before = _utc(root.get("observer_not_before_utc"), "observer_not_before_invalid")

    active = _exact_fields(
        root.get("active_identity"),
        {
            "MainPID",
            "ProcessStartTicks",
            "InvocationID",
            "ExecMainStartTimestampMonotonic",
            "NRestarts",
            "ALRSourceHead",
        },
        "observer_active_identity_fields_invalid",
    )
    if (
        not isinstance(active.get("MainPID"), str)
        or not active["MainPID"].isdigit()
        or int(active["MainPID"]) <= 0
        or not isinstance(active.get("ProcessStartTicks"), str)
        or not active["ProcessStartTicks"].isdigit()
        or not isinstance(active.get("ExecMainStartTimestampMonotonic"), str)
        or not active["ExecMainStartTimestampMonotonic"].isdigit()
        or _hash(active.get("InvocationID"), "observer_invocation_id_invalid", length=32)
        != active.get("InvocationID")
        or active.get("NRestarts") != "0"
        or active.get("ALRSourceHead") != target_head
    ):
        raise ObserverInputError("observer_active_identity_invalid")

    board = _exact_fields(
        root.get("admitted_board"),
        {
            "staged_path",
            "live_path",
            "source_content_sha256",
            "generated_at_utc",
            "board_hash",
            "audit_hash",
            "selection_hash",
            "candidate_set_hash",
        },
        "observer_board_fields_invalid",
    )
    staged = board.get("staged_path")
    live = board.get("live_path")
    if (
        not isinstance(staged, str)
        or not Path(staged).is_absolute()
        or not isinstance(live, str)
        or not Path(live).is_absolute()
        or Path(staged).name != Path(live).name
        or Path(live).parent
        != Path("/home/ncyu/.local/share/openclaw/alr-candidate-evidence")
    ):
        raise ObserverInputError("observer_board_path_invalid")
    generated = _utc(board.get("generated_at_utc"), "observer_board_generated_invalid")
    if generated > not_before:
        raise ObserverInputError("observer_board_after_not_before")
    normalized_board = {
        "staged_path": staged,
        "live_path": live,
        "source_content_sha256": _hash(
            board.get("source_content_sha256"), "observer_board_content_hash_invalid"
        ),
        "generated_at_utc": board["generated_at_utc"],
        "board_hash": _hash(board.get("board_hash"), "observer_board_hash_invalid"),
        "audit_hash": _hash(board.get("audit_hash"), "observer_board_audit_hash_invalid"),
        "selection_hash": _hash(
            board.get("selection_hash"), "observer_board_selection_hash_invalid"
        ),
        "candidate_set_hash": _hash(
            board.get("candidate_set_hash"), "observer_candidate_set_hash_invalid"
        ),
    }

    runtime_files = _exact_fields(
        root.get("runtime_files"),
        {"unit", "pin", "pin_derived_at_utc"},
        "observer_runtime_files_fields_invalid",
    )
    unit = _binding(runtime_files.get("unit"), "observer_unit_binding_invalid")
    pin = _binding(runtime_files.get("pin"), "observer_pin_binding_invalid")
    if unit["path"] != "/home/ncyu/.config/systemd/user/openclaw-alr-shadow.service":
        raise ObserverInputError("observer_unit_path_invalid")
    if pin["path"] != (
        "/home/ncyu/BybitOpenClaw/var/openclaw/runtime_generation/"
        "expected_source_head.json"
    ):
        raise ObserverInputError("observer_pin_path_invalid")
    _utc(runtime_files.get("pin_derived_at_utc"), "observer_pin_derived_at_invalid")

    consumer = _exact_fields(
        root.get("consumer_source"),
        {"path", "sha256", "blob_sha1", "ml_training_tree_sha1"},
        "observer_consumer_source_fields_invalid",
    )
    if (
        consumer.get("path") != str(CONSUMER_SOURCE_PATH)
        or HEX64_RE.fullmatch(str(consumer.get("sha256", ""))) is None
        or HEX40_RE.fullmatch(str(consumer.get("blob_sha1", ""))) is None
        or HEX40_RE.fullmatch(str(consumer.get("ml_training_tree_sha1", ""))) is None
    ):
        raise ObserverInputError("observer_consumer_source_binding_invalid")

    git_seals = _exact_fields(
        root.get("git_seals"),
        {
            "origin_main_head",
            "tracked_file_count",
            "git_index_sha256",
            "git_index_size",
            "git_stage_inventory_sha256",
            "git_stage_inventory_size",
        },
        "observer_git_seals_fields_invalid",
    )
    if (
        git_seals.get("origin_main_head") != target_head
        or isinstance(git_seals.get("tracked_file_count"), bool)
        or not isinstance(git_seals.get("tracked_file_count"), int)
        or not 1 <= git_seals["tracked_file_count"] <= 1_000_000
        or HEX64_RE.fullmatch(str(git_seals.get("git_index_sha256", ""))) is None
        or isinstance(git_seals.get("git_index_size"), bool)
        or not isinstance(git_seals.get("git_index_size"), int)
        or not 1 <= git_seals["git_index_size"] <= 64 * 1024 * 1024
        or HEX64_RE.fullmatch(
            str(git_seals.get("git_stage_inventory_sha256", ""))
        )
        is None
        or isinstance(git_seals.get("git_stage_inventory_size"), bool)
        or not isinstance(git_seals.get("git_stage_inventory_size"), int)
        or not 1 <= git_seals["git_stage_inventory_size"] <= 64 * 1024 * 1024
    ):
        raise ObserverInputError("observer_git_seals_invalid")

    private = _exact_fields(
        root.get("private_deps"),
        {"receipt", "destination", "manifest_sha256"},
        "observer_private_deps_fields_invalid",
    )
    destination = private.get("destination")
    if destination != "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps":
        raise ObserverInputError("observer_private_deps_destination_invalid")

    authority = _exact_fields(
        root.get("no_authority"),
        {"order", "probe", "promotion", "runtime"},
        "observer_authority_fields_invalid",
    )
    if authority != {"order": False, "probe": False, "promotion": False, "runtime": False}:
        raise ObserverInputError("observer_authority_grant_present")

    return {
        "schema_version": INPUT_SCHEMA,
        "target_head": target_head,
        "observer_not_before_utc": root["observer_not_before_utc"],
        "active_identity": dict(active),
        "phase1_receipt": _binding(root.get("phase1_receipt"), "phase1_receipt_binding_invalid"),
        "cutover_authorization": _binding(
            root.get("cutover_authorization"),
            "cutover_authorization_binding_invalid",
        ),
        "provisional_cutover": _binding(
            root.get("provisional_cutover"),
            "provisional_cutover_binding_invalid",
        ),
        "admitted_board": normalized_board,
        "runtime_files": {
            "unit": unit,
            "pin": pin,
            "pin_derived_at_utc": runtime_files["pin_derived_at_utc"],
        },
        "consumer_source": dict(consumer),
        "git_seals": dict(git_seals),
        "private_deps": {
            "receipt": _binding(private.get("receipt"), "private_deps_receipt_binding_invalid"),
            "destination": destination,
            "manifest_sha256": _hash(
                private.get("manifest_sha256"), "private_deps_manifest_hash_invalid"
            ),
        },
        "no_authority": dict(authority),
    }


def _consumer_source_order_invariants(
    source_raw: bytes, expected_sha256: str
) -> dict[str, bool]:
    if hashlib.sha256(source_raw).hexdigest() != expected_sha256:
        raise ObserverInputError("consumer_source_hash_mismatch")
    try:
        source = source_raw.decode("utf-8")
        tree = ast.parse(source)
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise ObserverInputError("consumer_source_parse_invalid") from exc
    functions = {
        node.name: ast.get_source_segment(source, node)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    runner = functions.get("run_event_consumer")
    loop = functions.get("event_consumer_loop")
    if not isinstance(runner, str) or not isinstance(loop, str):
        raise ObserverInputError("consumer_source_invariant_function_missing")
    open_index = runner.find("open_candidate_board_event_source(")
    session_index = runner.find("start_consumer_session(")
    loop_call_index = runner.find("result = event_consumer_loop(")
    pass_source_index = runner.find("candidate_board_source=board_source")
    startup_consume_index = loop.find(
        "candidate_board_source.consume_reconciliation_request()"
    )
    first_operational_index = loop.find("_process_operational_cycle(")
    notification_loop_index = loop.find("while not should_stop():")
    notification_wait_index = loop.find("wait_for_notifications(")
    if not (
        0 <= open_index < session_index < loop_call_index < pass_source_index
        and 0
        <= startup_consume_index
        < first_operational_index
        < notification_loop_index
        < notification_wait_index
    ):
        raise ObserverInputError("consumer_source_order_invariant_failed")
    return {
        "watch_opened_before_session_and_loop": True,
        "startup_reconciliation_consumed_before_first_operational_cycle": True,
        "first_operational_cycle_before_notification_loop": True,
        "notification_wait_only_after_startup_operational_cycle": True,
    }


def validate_startup_reconciliation_proof(
    config: Mapping[str, Any],
    consumer_source_raw: bytes,
    proof: Mapping[str, Any],
) -> dict[str, Any]:
    """Combine sealed source ordering with same-session temporal PG evidence.

    The database does not persist an explicit reconciliation trigger.  This is
    deliberately a two-surface proof and never a PG-explicit-trigger claim.
    """

    checked = validate_observer_input_payload(config)
    invariants = _consumer_source_order_invariants(
        consumer_source_raw, checked["consumer_source"]["sha256"]
    )
    root = _exact_fields(
        proof,
        {
            "schema_version",
            "session_id",
            "session_started_at_utc",
            "decision_row_count",
            "decision",
            "first_notification_received_row_count",
            "first_notification_received",
            "same_session",
            "pg_explicit_trigger_claimed",
        },
        "startup_proof_fields_invalid",
    )
    decision = _exact_fields(
        root.get("decision"),
        {
            "artifact_hash",
            "created_at_utc",
            "board_generated_at_utc",
            "source_head",
            "source_content_sha256",
            "board_hash",
            "audit_hash",
            "selection_hash",
            "candidate_set_hash",
            "no_authority",
        },
        "startup_decision_fields_invalid",
    )
    notification = _exact_fields(
        root.get("first_notification_received"),
        {"event_id", "recorded_at_utc"},
        "startup_notification_fields_invalid",
    )
    board = checked["admitted_board"]
    if (
        root.get("schema_version")
        != "p0b_alr_startup_reconciliation_temporal_v1"
        or root.get("decision_row_count") != 1
        or root.get("first_notification_received_row_count") != 1
        or root.get("same_session") is not True
        or root.get("pg_explicit_trigger_claimed") is not False
        or not isinstance(root.get("session_id"), str)
        or not root["session_id"]
        or not isinstance(notification.get("event_id"), str)
        or not notification["event_id"]
        or decision.get("source_head") != checked["target_head"]
        or decision.get("board_generated_at_utc") != board["generated_at_utc"]
        or decision.get("source_content_sha256") != board["source_content_sha256"]
        or decision.get("board_hash") != board["board_hash"]
        or decision.get("audit_hash") != board["audit_hash"]
        or decision.get("selection_hash") != board["selection_hash"]
        or decision.get("candidate_set_hash") != board["candidate_set_hash"]
        or decision.get("no_authority") is not True
    ):
        raise ObserverInputError("startup_proof_binding_invalid")
    artifact_hash = _hash(
        decision.get("artifact_hash"), "startup_decision_artifact_hash_invalid"
    )
    session_started = _utc(
        root.get("session_started_at_utc"), "startup_session_time_invalid"
    )
    decision_at = _utc(decision.get("created_at_utc"), "startup_decision_time_invalid")
    notification_at = _utc(
        notification.get("recorded_at_utc"), "startup_notification_time_invalid"
    )
    not_before = _utc(
        checked["observer_not_before_utc"], "observer_not_before_invalid"
    )
    if not not_before <= session_started <= decision_at < notification_at:
        raise ObserverInputError("startup_temporal_order_invalid")
    return {
        "startup_reconciliation_proof_basis": (
            "SOURCE_ORDER_PLUS_SESSION_TEMPORAL_ATTESTATION"
        ),
        "pg_explicit_trigger_claimed": False,
        "consumer_source": dict(checked["consumer_source"]),
        "source_ordering_invariants": invariants,
        "session_id": root["session_id"],
        "session_started_at_utc": root["session_started_at_utc"],
        "decision_artifact_hash": artifact_hash,
        "decision_created_at_utc": decision["created_at_utc"],
        "first_notification_received_event_id": notification["event_id"],
        "first_notification_received_at_utc": notification["recorded_at_utc"],
        "decision_strictly_before_first_notification_received": True,
        "same_session": True,
        "admitted_board": {
            key: board[key]
            for key in (
                "source_content_sha256",
                "board_hash",
                "audit_hash",
                "selection_hash",
                "candidate_set_hash",
            )
        },
        "authority": dict(checked["no_authority"]),
    }


def _required_mapping(value: Any, reason: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ObserverInputError(reason)
    return value


def observer_input_contract_sha256(config: Mapping[str, Any]) -> str:
    checked = validate_observer_input_payload(config)
    projection = {
        key: value for key, value in checked.items() if key != "provisional_cutover"
    }
    return canonical_sha256(projection)


def _sha256_prefixed(value: Any) -> str:
    return "sha256:" + canonical_sha256(value)


def validate_cutover_authorization(
    config: Mapping[str, Any],
    authorization: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    checked = validate_observer_input_payload(config)
    if (
        not isinstance(now, datetime)
        or now.tzinfo is None
        or now.utcoffset() != timezone.utc.utcoffset(now)
    ):
        raise ObserverInputError("cutover_observation_time_invalid")
    now = now.astimezone(timezone.utc)
    auth = _exact_fields(
        authorization,
        AUTHORIZATION_FIELDS,
        "cutover_authorization_fields_invalid",
    )
    governance = _exact_fields(
        auth.get("governance_bindings"),
        GOVERNANCE_BINDING_FIELDS,
        "cutover_governance_bindings_invalid",
    )
    claims = _exact_fields(
        auth.get("claim_bindings"),
        CUTOVER_CLAIM_FIELDS,
        "cutover_claim_bindings_invalid",
    )
    digest_fields = (
        "intent_digest", "task_contract_digest", "context_artifact_digest",
        "expected_old_pin_digest", "expected_source_tree_digest",
        "expected_pin_consumer_inventory_digest",
        "expected_runtime_identity_digest", "phase1_effect_receipt_digest",
        "phase1_closure_digest", "sealed_lineage_bundle_digest",
        "authorization_digest",
    )
    governance_digest_fields = GOVERNANCE_BINDING_FIELDS - {
        "compiled_route_schema", "context_artifact_schema",
        "ops_preflight_observed_at", "ops_preflight_expires_at",
        "phase_runtime_bindings_path",
    }
    if any(
        re.fullmatch(r"sha256:[0-9a-f]{64}", str(auth.get(key, ""))) is None
        for key in digest_fields
    ) or any(
        re.fullmatch(r"sha256:[0-9a-f]{64}", str(governance.get(key, ""))) is None
        for key in governance_digest_fields
    ) or any(
        re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)) is None
        for value in claims.values()
    ):
        raise ObserverInputError("cutover_authorization_digest_field_invalid")
    expected_digest = _sha256_prefixed(
        {key: value for key, value in auth.items() if key != "authorization_digest"}
    )
    approved = _utc(auth.get("approved_at"), "cutover_approved_at_invalid")
    expires = _utc(auth.get("expires_at"), "cutover_expires_at_invalid")
    ops_observed = _utc(
        governance.get("ops_preflight_observed_at"),
        "cutover_ops_observed_at_invalid",
    )
    ops_expires = _utc(
        governance.get("ops_preflight_expires_at"),
        "cutover_ops_expires_at_invalid",
    )
    target = checked["target_head"]
    expected_typed = (
        f"p0b-alr-rollforward:cutover:trade-core:{target}:{auth.get('intent_id')}"
    )
    if (
        auth.get("schema_version") != "p0b_alr_runtime_authorization_v1"
        or auth.get("adapter_id") != "p0b_alr_rollforward_adapter_v1"
        or auth.get("phase") != "cutover"
        or governance.get("compiled_route_schema")
        != "hybrid_execution_dag_v1"
        or governance.get("context_artifact_schema") != "context_artifact_v1"
        or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{7,127}", str(auth.get("intent_id", ""))
        )
        is None
        or auth.get("expected_source_head") != target
        or auth.get("expected_origin_main_head") != target
        or HEX40_RE.fullmatch(
            str(auth.get("expected_old_runtime_source_head", ""))
        )
        is None
        or auth.get("expected_old_runtime_source_head") == target
        or auth.get("target_host") != "trade-core"
        or auth.get("target_environment") != "trade_core_alr"
        or auth.get("target_user_unit") != UNIT_NAME
        or auth.get("require_clean_tree") is not True
        or auth.get("require_fresh_origin_main") is not True
        or auth.get("phase1_effect_receipt_digest")
        != "sha256:" + checked["phase1_receipt"]["sha256"]
        or auth.get("private_bundle_destination")
        != checked["private_deps"]["destination"]
        or auth.get("observer_requirement") != "REQUIRED_PASS"
        or not Path(
            str(governance.get("phase_runtime_bindings_path", ""))
        ).is_absolute()
        or "latest" in Path(
            str(governance.get("phase_runtime_bindings_path", ""))
        ).name.lower()
        or not isinstance(auth.get("approved_by"), str)
        or not auth["approved_by"]
        or auth.get("typed_confirm") != expected_typed
        or auth.get("hard_stops") != CUTOVER_HARD_STOPS
        or auth.get("authorization_digest") != expected_digest
        or not approved <= now < expires
        or not ops_observed <= now < ops_expires
        or not 0 < (ops_expires - ops_observed).total_seconds() <= 900
    ):
        raise ObserverInputError("cutover_authorization_binding_invalid")
    if any("context_plan" in str(key).lower() for key in auth):
        raise ObserverInputError("obsolete_generic_approval_forbidden")
    return {
        "authorization_digest": auth["authorization_digest"],
        "intent_digest": auth["intent_digest"],
        "sealed_lineage_bundle_digest": auth["sealed_lineage_bundle_digest"],
        "protected_baseline_digest": governance["protected_baseline_digest"],
        "expected_runtime_identity_digest": auth["expected_runtime_identity_digest"],
        "claim_bindings": dict(claims),
        "approved_at": auth["approved_at"],
        "expires_at": auth["expires_at"],
    }


def validate_stage_authorization(
    phase1: Mapping[str, Any],
    authorization: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the expired-safe Stage authority at its recorded effect time."""

    auth = _exact_fields(
        authorization,
        AUTHORIZATION_FIELDS,
        "stage_authorization_fields_invalid",
    )
    governance = _exact_fields(
        auth.get("governance_bindings"),
        GOVERNANCE_BINDING_FIELDS,
        "stage_governance_bindings_invalid",
    )
    claims = _exact_fields(
        auth.get("claim_bindings"),
        STAGE_CLAIM_FIELDS,
        "stage_claim_bindings_invalid",
    )
    governance_digest_fields = GOVERNANCE_BINDING_FIELDS - {
        "compiled_route_schema",
        "context_artifact_schema",
        "ops_preflight_observed_at",
        "ops_preflight_expires_at",
        "phase_runtime_bindings_path",
    }
    digest_fields = (
        "intent_digest",
        "task_contract_digest",
        "context_artifact_digest",
        "expected_old_pin_digest",
        "expected_source_tree_digest",
        "expected_pin_consumer_inventory_digest",
        "expected_runtime_identity_digest",
        "authorization_digest",
    )
    if (
        any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", str(auth.get(key, "")))
            is None
            for key in digest_fields
        )
        or any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", str(governance.get(key, "")))
            is None
            for key in governance_digest_fields
        )
        or any(
            re.fullmatch(r"sha256:[0-9a-f]{64}", str(value)) is None
            for value in claims.values()
        )
    ):
        raise ObserverInputError("stage_authorization_digest_field_invalid")
    target = phase1.get("target_head")
    old_head = phase1.get("old_head")
    expected_digest = _sha256_prefixed(
        {key: value for key, value in auth.items() if key != "authorization_digest"}
    )
    approved = _utc(auth.get("approved_at"), "stage_approved_at_invalid")
    expires = _utc(auth.get("expires_at"), "stage_expires_at_invalid")
    completed = _utc(phase1.get("completed_at_utc"), "phase1_completed_at_invalid")
    ops_observed = _utc(
        governance.get("ops_preflight_observed_at"),
        "stage_ops_observed_at_invalid",
    )
    ops_expires = _utc(
        governance.get("ops_preflight_expires_at"),
        "stage_ops_expires_at_invalid",
    )
    expected_typed = (
        f"p0b-alr-rollforward:stage:trade-core:{target}:{auth.get('intent_id')}"
    )
    hard_stops = auth.get("hard_stops")
    if (
        auth.get("schema_version") != "p0b_alr_runtime_authorization_v1"
        or auth.get("adapter_id") != "p0b_alr_rollforward_adapter_v1"
        or auth.get("phase") != "stage"
        or governance.get("compiled_route_schema") != "hybrid_execution_dag_v1"
        or governance.get("context_artifact_schema") != "context_artifact_v1"
        or re.fullmatch(
            r"[a-z0-9][a-z0-9._-]{7,127}", str(auth.get("intent_id", ""))
        )
        is None
        or HEX40_RE.fullmatch(str(target or "")) is None
        or HEX40_RE.fullmatch(str(old_head or "")) is None
        or auth.get("expected_source_head") != target
        or auth.get("expected_origin_main_head") != target
        or auth.get("expected_old_runtime_source_head") != old_head
        or auth.get("target_host") != "trade-core"
        or auth.get("target_environment") != "trade_core_alr"
        or auth.get("target_user_unit") != UNIT_NAME
        or auth.get("require_clean_tree") is not True
        or auth.get("require_fresh_origin_main") is not True
        or auth.get("phase1_effect_receipt_digest") is not None
        or auth.get("phase1_closure_digest") is not None
        or auth.get("sealed_lineage_bundle_digest") is not None
        or auth.get("private_bundle_destination")
        != "/home/ncyu/BybitOpenClaw/var/openclaw/p0b-observer-deps"
        or auth.get("observer_requirement") != "NOT_APPLICABLE"
        or not Path(
            str(governance.get("phase_runtime_bindings_path", ""))
        ).is_absolute()
        or "latest" in Path(
            str(governance.get("phase_runtime_bindings_path", ""))
        ).name.lower()
        or not isinstance(auth.get("approved_by"), str)
        or not auth["approved_by"]
        or auth.get("typed_confirm") != expected_typed
        or not isinstance(hard_stops, list)
        or len(hard_stops) < 7
        or len(set(hard_stops)) != len(hard_stops)
        or auth.get("authorization_digest") != expected_digest
        or not approved <= completed <= expires
        or not ops_observed <= completed <= ops_expires
        or claims["p0b_protected_runtime_baseline"]
        != governance["protected_baseline_digest"]
    ):
        raise ObserverInputError("stage_authorization_binding_invalid")
    return {
        "authorization_digest": auth["authorization_digest"],
        "expected_old_runtime_source_head": auth[
            "expected_old_runtime_source_head"
        ],
        "expected_old_pin_digest": auth["expected_old_pin_digest"],
        "expected_source_tree_digest": auth["expected_source_tree_digest"],
        "expected_pin_consumer_inventory_digest": auth[
            "expected_pin_consumer_inventory_digest"
        ],
        "expected_runtime_identity_digest": auth[
            "expected_runtime_identity_digest"
        ],
        "target_source_attestation_digest": claims[
            "p0b_target_source_attestation"
        ],
        "protected_baseline_digest": claims[
            "p0b_protected_runtime_baseline"
        ],
    }


def validate_phase_runtime_bindings(
    bindings: Mapping[str, Any],
    authorization: Mapping[str, Any],
    *,
    phase: str,
    observed_at: datetime,
    artifact_path: str,
    config: Mapping[str, Any],
) -> dict[str, Any]:
    """Independently validate the formal read-only data-plane artifact."""

    root = _exact_fields(
        bindings, RUNTIME_BINDING_FIELDS, "runtime_bindings_fields_invalid"
    )
    governance = _required_mapping(
        authorization.get("governance_bindings"),
        "runtime_bindings_governance_invalid",
    )
    claims = _required_mapping(
        authorization.get("claim_bindings"), "runtime_bindings_claims_invalid"
    )
    if (
        root.get("schema_version") != "phase_runtime_bindings_v1"
        or root.get("phase") != phase
        or root.get("intent_id") != authorization.get("intent_id")
        or root.get("target_head") != authorization.get("expected_source_head")
        or governance.get("phase_runtime_bindings_path") != artifact_path
    ):
        raise ObserverInputError("runtime_bindings_authority_mismatch")
    start = _utc(root.get("observed_at"), "runtime_bindings_observed_at_invalid")
    expires = _utc(root.get("expires_at"), "runtime_bindings_expires_at_invalid")
    if not start <= observed_at <= expires or expires <= start:
        raise ObserverInputError("runtime_bindings_time_invalid")
    expected_digest = _sha256_prefixed(
        {key: value for key, value in root.items() if key != "artifact_digest"}
    )
    if (
        root.get("artifact_digest") != expected_digest
        or governance.get("phase_runtime_bindings_artifact_digest")
        != expected_digest
        or claims.get("p0b_phase_runtime_bindings") != expected_digest
    ):
        raise ObserverInputError("runtime_bindings_artifact_digest_invalid")

    section_claims = _exact_fields(
        root.get("section_claims"),
        set(RUNTIME_BINDING_SECTIONS),
        "runtime_bindings_section_claims_invalid",
    )
    for section, claim_name in RUNTIME_BINDING_SECTIONS.items():
        claim = _exact_fields(
            section_claims.get(section),
            {"claim", "digest"},
            "runtime_bindings_section_claim_invalid",
        )
        section_digest = _sha256_prefixed(root[section])
        if (
            claim.get("claim") != claim_name
            or claim.get("digest") != section_digest
            or claims.get(claim_name) != section_digest
        ):
            raise ObserverInputError("runtime_bindings_section_claim_invalid")

    source = _exact_fields(
        root.get("source_attestation"),
        SOURCE_ATTESTATION_FIELDS,
        "runtime_bindings_source_fields_invalid",
    )
    snapshot = _required_mapping(
        source.get("source"), "runtime_bindings_source_snapshot_invalid"
    )
    if (
        snapshot.get("head") != authorization.get("expected_source_head")
        or snapshot.get("origin_main")
        != authorization.get("expected_origin_main_head")
        or snapshot.get("remote_origin_main")
        != authorization.get("expected_origin_main_head")
        or source.get("source_tree_digest")
        != _sha256_prefixed(source.get("execution_tree"))
        or source.get("source_tree_digest")
        != authorization.get("expected_source_tree_digest")
        or claims.get("p0b_target_source_attestation")
        != _sha256_prefixed(source)
    ):
        raise ObserverInputError("runtime_bindings_source_invalid")

    protected = _exact_fields(
        root.get("protected_runtime_baseline"),
        PROTECTED_BASELINE_FIELDS,
        "runtime_bindings_protected_fields_invalid",
    )
    service = _exact_fields(
        protected.get("service_baseline"),
        {
            "unit_sha256", "pin_sha256", "unit_head", "pin_head",
            "active_identity", "unit_identity", "pin_identity",
            "unit_lock_identity", "cost_lock_identity", "alpha_lock_identity",
        },
        "runtime_bindings_service_fields_invalid",
    )
    runtime_identity = _exact_fields(
        protected.get("runtime_identity"),
        {
            "schema_version", "target_host", "target_user_unit", "source_head",
            "invocation_id", "main_pid", "main_pid_start_ticks", "control_group",
            "unit_fragment_path", "unit_file_sha256", "pin_path", "pin_sha256",
            "cost_pin_lock_path", "alpha_pin_lock_path", "nrestarts",
            "active_state", "sub_state", "observed_at",
        },
        "runtime_bindings_runtime_identity_fields_invalid",
    )
    if (
        protected.get("protected_digest")
        != _sha256_prefixed(protected.get("protected"))
        or protected.get("pin_consumer_inventory_digest")
        != _sha256_prefixed(protected.get("pin_consumer_inventory"))
        or protected.get("runtime_identity_digest")
        != _sha256_prefixed(runtime_identity)
        or protected.get("pin_consumer_inventory_digest")
        != authorization.get("expected_pin_consumer_inventory_digest")
        or protected.get("runtime_identity_digest")
        != authorization.get("expected_runtime_identity_digest")
        or claims.get("p0b_protected_runtime_baseline")
        != protected.get("protected_digest")
        or service.get("unit_head")
        != authorization.get("expected_old_runtime_source_head")
        or service.get("pin_head")
        != authorization.get("expected_old_runtime_source_head")
        or "sha256:" + str(service.get("pin_sha256"))
        != authorization.get("expected_old_pin_digest")
    ):
        raise ObserverInputError("runtime_bindings_protected_invalid")

    intent_id = str(authorization.get("intent_id"))
    path_fields = (
        {
            "staging_root", "cron_destination", "sealed_destination",
            "publisher_receipt_path", "private_deps_receipt_path",
            "private_deps_destination", "phase1_receipt_path",
            "phase1_closure_path",
        }
        if phase == "stage"
        else {
            "phase1_receipt_path", "phase1_closure_path", "live_destination",
            "provisional_cutover_path", "observer_input_path",
        }
    )
    paths = _exact_fields(
        root.get("phase_paths"), path_fields, "runtime_bindings_paths_fields_invalid"
    )
    if phase == "stage":
        staging = STAGING_ROOT / intent_id
        expected_paths = {
            "staging_root": str(staging),
            "cron_destination": str(staging / "cron-scratch"),
            "sealed_destination": str(staging / "sealed"),
            "publisher_receipt_path": str(staging / "staging-publisher-result.json"),
            "private_deps_receipt_path": str(staging / "private-deps-receipt.json"),
            "private_deps_destination": config["private_deps"]["destination"],
            "phase1_receipt_path": str(RUNTIME_RECOVERY_ROOT / f"{intent_id}.phase1.json"),
            "phase1_closure_path": str(RUNTIME_RECOVERY_ROOT / f"{intent_id}.phase1.closure.json"),
        }
    else:
        expected_paths = {
            "phase1_receipt_path": paths.get("phase1_receipt_path"),
            "phase1_closure_path": paths.get("phase1_closure_path"),
            "live_destination": "/home/ncyu/.local/share/openclaw/alr-candidate-evidence",
            "provisional_cutover_path": str(
                RUNTIME_RECOVERY_ROOT / f"{intent_id}.phase2.provisional.json"
            ),
            "observer_input_path": str(
                RUNTIME_RECOVERY_ROOT / f"{intent_id}.phase2.observer-input.json"
            ),
        }
        if any(
            not Path(str(paths.get(key, ""))).is_absolute()
            or "latest" in Path(str(paths.get(key, ""))).name.lower()
            for key in ("phase1_receipt_path", "phase1_closure_path")
        ):
            raise ObserverInputError("runtime_bindings_paths_invalid")
    if dict(paths) != expected_paths:
        raise ObserverInputError("runtime_bindings_paths_invalid")

    inventories = _exact_fields(
        root.get("inventories"), INVENTORY_FIELDS,
        "runtime_bindings_inventory_fields_invalid",
    )
    pairs = (
        ("live_inventory", "live_inventory_digest"),
        ("completion_inventory", "completion_inventory_digest"),
        ("producer_inventory", "producer_inventory_digest"),
        ("ledger_inventory", "ledger_inventory_digest"),
        ("lane_effective_config", "lane_effective_config_digest"),
    )
    if any(
        inventories[digest] != _sha256_prefixed(inventories[value])
        for value, digest in pairs
    ) or (
        claims.get("p0b_live_inventory") != inventories["live_inventory_digest"]
        or claims.get("p0b_completion_inventory")
        != inventories["completion_inventory_digest"]
        or claims.get("p0b_producer_inventory")
        != inventories["producer_inventory_digest"]
    ):
        raise ObserverInputError("runtime_bindings_inventory_invalid")

    lineage_fields = (
        {"p0a_completed_board_input", "private_bundle_destination_absent"}
        if phase == "stage"
        else {
            "phase1_receipt", "phase1_closure", "sealed_lineage_bundle",
            "completion", "producer_board", "staged_board",
            "staging_publisher_receipt", "private_deps_receipt", "token",
            "max_age_seconds", "proposed_unit_sha256", "private_deps_destination",
            "private_deps_manifest_sha256", "completion_inventory_digest",
            "producer_inventory_digest", "ledger_pre_inventory_digest",
            "ledger_post_inventory_digest", "lane_effective_config_digest",
        }
    )
    lineage = _exact_fields(
        root.get("lineage"), lineage_fields, "runtime_bindings_lineage_fields_invalid"
    )
    if phase == "stage":
        p0a = _binding(
            lineage.get("p0a_completed_board_input"),
            "runtime_bindings_p0a_binding_invalid",
        )
        absent = _exact_fields(
            lineage.get("private_bundle_destination_absent"),
            {"destination", "absent"},
            "runtime_bindings_private_absence_invalid",
        )
        if (
            claims.get("p0b_p0a_completed_board_input")
            != "sha256:" + p0a["sha256"]
            or absent
            != {"destination": config["private_deps"]["destination"], "absent": True}
            or claims.get("p0b_private_bundle_destination_absent_attestation")
            != _sha256_prefixed(absent)
        ):
            raise ObserverInputError("runtime_bindings_stage_lineage_invalid")
    else:
        bound = {
            key: _binding(
                lineage.get(key), f"runtime_bindings_{key}_binding_invalid"
            )
            for key in (
                "phase1_receipt", "phase1_closure", "sealed_lineage_bundle",
                "completion", "producer_board", "staged_board",
                "staging_publisher_receipt", "private_deps_receipt",
            )
        }
        if (
            bound["phase1_receipt"] != config["phase1_receipt"]
            or bound["staged_board"]
            != {
                "path": config["admitted_board"]["staged_path"],
                "sha256": config["admitted_board"]["source_content_sha256"],
            }
            or bound["private_deps_receipt"]
            != config["private_deps"]["receipt"]
            or authorization.get("phase1_closure_digest")
            != "sha256:" + bound["phase1_closure"]["sha256"]
            or authorization.get("sealed_lineage_bundle_digest")
            != "sha256:" + bound["sealed_lineage_bundle"]["sha256"]
            or lineage.get("private_deps_destination")
            != config["private_deps"]["destination"]
            or lineage.get("private_deps_manifest_sha256")
            != config["private_deps"]["manifest_sha256"]
            or lineage.get("completion_inventory_digest")
            != inventories["completion_inventory_digest"]
            or lineage.get("producer_inventory_digest")
            != inventories["producer_inventory_digest"]
            or lineage.get("ledger_post_inventory_digest")
            != inventories["ledger_inventory_digest"]
            or lineage.get("lane_effective_config_digest")
            != inventories["lane_effective_config_digest"]
        ):
            raise ObserverInputError("runtime_bindings_cutover_lineage_invalid")
    return {
        "artifact_digest": expected_digest,
        "source_attestation_digest": _sha256_prefixed(source),
        "protected_baseline_digest": protected["protected_digest"],
        "phase1_closure": lineage.get("phase1_closure"),
        "sealed_lineage_bundle": lineage.get("sealed_lineage_bundle"),
    }


def validate_phase1_closure_and_bundle(
    config: Mapping[str, Any],
    *,
    phase1: Mapping[str, Any],
    stage_authorization: Mapping[str, Any],
    stage_runtime_bindings: Mapping[str, Any],
    phase1_closure: Mapping[str, Any],
    sealed_lineage_bundle: Mapping[str, Any],
    phase1_closure_binding: Mapping[str, Any],
    sealed_lineage_bundle_binding: Mapping[str, Any],
) -> dict[str, str]:
    """Validate separate Phase1 governance artifacts and their raw bindings."""

    checked = validate_observer_input_payload(config)
    closure_binding = _binding(
        phase1_closure_binding, "phase1_closure_binding_invalid"
    )
    bundle_binding = _binding(
        sealed_lineage_bundle_binding, "sealed_lineage_bundle_binding_invalid"
    )
    closure = _exact_fields(
        phase1_closure, PHASE1_CLOSURE_FIELDS, "phase1_closure_fields_invalid"
    )
    ops = _exact_fields(
        closure.get("ops_postcheck"),
        OPS_POSTCHECK_FIELDS,
        "phase1_ops_postcheck_fields_invalid",
    )
    stage_governance = _required_mapping(
        stage_authorization.get("governance_bindings"),
        "stage_governance_bindings_invalid",
    )
    common = {
        "intent_id": stage_authorization.get("intent_id"),
        "intent_digest": stage_authorization.get("intent_digest"),
        "task_contract_digest": stage_authorization.get("task_contract_digest"),
        "compiled_route_digest": stage_governance.get("compiled_route_digest"),
        "context_artifact_digest": stage_authorization.get(
            "context_artifact_digest"
        ),
    }
    receipt_raw_digest = "sha256:" + checked["phase1_receipt"]["sha256"]
    phase_result_digest = _sha256_prefixed(phase1)
    try:
        completed = _utc(phase1.get("completed_at_utc"), "phase1_completed_at_invalid")
        observed = _utc(ops.get("observed_at"), "phase1_ops_observed_at_invalid")
        expires = _utc(ops.get("expires_at"), "phase1_ops_expires_at_invalid")
        closed = _utc(closure.get("closed_at_utc"), "phase1_closed_at_invalid")
    except ObserverInputError as exc:
        raise ObserverInputError("phase1_closure_semantics_invalid") from exc
    if (
        closure.get("schema_version")
        != "p0b_alr_phase1_governance_closure_v1"
        or closure.get("status") != "PHASE1_GOVERNANCE_CLOSURE_PASS"
        or closure.get("phase") != "stage"
        or any(closure.get(key) != value for key, value in common.items())
        or closure.get("stage_authorization_digest")
        != stage_authorization.get("authorization_digest")
        or closure.get("stage_runtime_bindings_artifact_digest")
        != stage_runtime_bindings.get("artifact_digest")
        or closure.get("phase1_effect_receipt_digest") != receipt_raw_digest
        or closure.get("phase_result_digest") != phase_result_digest
        or closure.get("ops_postcheck_digest") != ops.get("operation_digest")
        or closure.get("closure_digest")
        != _sha256_prefixed(
            {
                key: value
                for key, value in closure.items()
                if key != "closure_digest"
            }
        )
        or ops.get("schema_version") != "ops_p0b_alr_postcheck_v1"
        or ops.get("adapter_id") != "p0b_alr_rollforward_adapter_v1"
        or ops.get("phase") != "stage"
        or any(ops.get(key) != value for key, value in common.items())
        or ops.get("source_head") != checked["target_head"]
        or ops.get("target_host") != "trade-core"
        or ops.get("target_user_unit") != UNIT_NAME
        or ops.get("effect_receipt_digest") != receipt_raw_digest
        or ops.get("phase_result_digest") != phase_result_digest
        or ops.get("observer_receipt_digest") is not None
        or ops.get("verified") is not True
        or ops.get("operation_digest")
        != _sha256_prefixed(
            {
                key: value
                for key, value in ops.items()
                if key != "operation_digest"
            }
        )
        or not completed <= observed <= closed < expires
        or expires <= observed
        or (expires - observed).total_seconds() > 15 * 60
    ):
        raise ObserverInputError("phase1_closure_semantics_invalid")

    bundle = _exact_fields(
        sealed_lineage_bundle,
        PHASE1_LINEAGE_BUNDLE_FIELDS,
        "sealed_lineage_bundle_fields_invalid",
    )
    bound = {
        key: _binding(bundle.get(key), f"sealed_lineage_bundle_{key}_invalid")
        for key in (
            "stage_authorization",
            "stage_runtime_bindings",
            "phase1_effect_receipt",
            "phase1_closure",
            "private_deps_receipt",
            "staged_board",
        )
    }
    sealed = _required_mapping(
        phase1.get("sealed_lineage"), "phase1_sealed_lineage_invalid"
    )
    if (
        bundle.get("schema_version")
        != "p0b_alr_phase1_sealed_lineage_bundle_v1"
        or bundle.get("target_head") != checked["target_head"]
        or any(bundle.get(key) != value for key, value in common.items())
        or bound["stage_authorization"] != phase1.get("stage_authorization")
        or bundle.get("stage_authorization_digest")
        != phase1.get("stage_authorization_digest")
        or bound["stage_runtime_bindings"] != phase1.get("stage_runtime_bindings")
        or bundle.get("stage_runtime_bindings_artifact_digest")
        != phase1.get("stage_runtime_bindings_artifact_digest")
        or bound["phase1_effect_receipt"] != checked["phase1_receipt"]
        or bundle.get("phase1_effect_receipt_digest") != receipt_raw_digest
        or bound["phase1_closure"] != closure_binding
        or bundle.get("phase1_closure_digest")
        != "sha256:" + closure_binding["sha256"]
        or bound["private_deps_receipt"] != checked["private_deps"]["receipt"]
        or bound["private_deps_receipt"] != sealed.get("private_deps_receipt")
        or bundle.get("private_deps_destination")
        != checked["private_deps"]["destination"]
        or bundle.get("private_deps_destination")
        != sealed.get("private_deps_destination")
        or bundle.get("private_deps_manifest_sha256")
        != checked["private_deps"]["manifest_sha256"]
        or bundle.get("private_deps_manifest_sha256")
        != sealed.get("private_deps_manifest_sha256")
        or bound["staged_board"]
        != {
            "path": checked["admitted_board"]["staged_path"],
            "sha256": checked["admitted_board"]["source_content_sha256"],
        }
        or bound["staged_board"] != sealed.get("staged_board")
        or bundle.get("bundle_digest")
        != _sha256_prefixed(
            {
                key: value
                for key, value in bundle.items()
                if key != "bundle_digest"
            }
        )
    ):
        raise ObserverInputError("sealed_lineage_bundle_semantics_invalid")
    return {
        "phase1_closure_raw_digest": "sha256:" + closure_binding["sha256"],
        "sealed_lineage_bundle_raw_digest": "sha256:" + bundle_binding["sha256"],
        "phase1_closure_digest": str(closure["closure_digest"]),
        "sealed_lineage_bundle_digest": str(bundle["bundle_digest"]),
    }


def validate_lineage_payloads(
    config: Mapping[str, Any],
    payloads: Mapping[str, Any],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cross-bind the staged lane, cutover and private-dependency receipts."""

    checked = validate_observer_input_payload(config)
    roots = _exact_fields(
        payloads,
        {
            "phase1_receipt",
            "phase1_closure",
            "sealed_lineage_bundle",
            "stage_authorization",
            "stage_runtime_bindings",
            "cutover_authorization",
            "cutover_runtime_bindings",
            "provisional_cutover",
            "private_deps_receipt",
        },
        "lineage_payload_set_invalid",
    )
    board = checked["admitted_board"]
    runtime = checked["runtime_files"]

    phase1 = _required_mapping(roots.get("phase1_receipt"), "phase1_receipt_invalid")
    stage_binding = _binding(
        phase1.get("stage_authorization"),
        "phase1_stage_authorization_binding_invalid",
    )
    stage_runtime = _exact_fields(
        phase1.get("stage_authorized_runtime"),
        {
            "expected_old_runtime_source_head",
            "expected_old_pin_digest",
            "expected_source_tree_digest",
            "expected_pin_consumer_inventory_digest",
            "expected_runtime_identity_digest",
        },
        "phase1_stage_authorized_runtime_fields_invalid",
    )
    stage_authorization = _required_mapping(
        roots.get("stage_authorization"), "stage_authorization_invalid"
    )
    stage_result = validate_stage_authorization(phase1, stage_authorization)
    stage_runtime_binding = _binding(
        phase1.get("stage_runtime_bindings"),
        "phase1_stage_runtime_bindings_invalid",
    )
    stage_runtime_payload = _required_mapping(
        roots.get("stage_runtime_bindings"), "stage_runtime_bindings_invalid"
    )
    stage_observed_at = _utc(
        phase1.get("completed_at_utc"), "phase1_completed_at_invalid"
    )
    stage_runtime_result = validate_phase_runtime_bindings(
        stage_runtime_payload,
        stage_authorization,
        phase="stage",
        observed_at=stage_observed_at,
        artifact_path=stage_runtime_binding["path"],
        config=checked,
    )
    sealed = _required_mapping(phase1.get("sealed_lineage"), "phase1_sealed_lineage_invalid")
    staged = _required_mapping(sealed.get("staged_board"), "phase1_staged_board_invalid")
    fence_fields = {
        "completion_inventory_sha256",
        "producer_inventory_sha256",
        "ledger_post_inventory_sha256",
        "lane_effective_config_sha256",
    }
    phase1_fence = {key: sealed.get(key) for key in fence_fields}
    if (
        phase1.get("schema_version") != "p0b_alr_current_head_rollforward_v1"
        or phase1.get("phase") != 1
        or phase1.get("status") != "PHASE1_STAGING_APPLIED_PASS"
        or phase1.get("target_head") != checked["target_head"]
        or phase1.get("old_head") != stage_result["expected_old_runtime_source_head"]
        or phase1.get("authorization_digest")
        != stage_result["authorization_digest"]
        or phase1.get("stage_authorization_digest")
        != stage_result["authorization_digest"]
        or phase1.get("stage_runtime_bindings_artifact_digest")
        != stage_runtime_result["artifact_digest"]
        or stage_binding.get("sha256")
        != hashlib.sha256(canonical_bytes(stage_authorization)).hexdigest()
        or stage_runtime_binding.get("sha256")
        != hashlib.sha256(canonical_bytes(stage_runtime_payload)).hexdigest()
        or dict(stage_runtime)
        != {
            key: stage_result[key]
            for key in (
                "expected_old_runtime_source_head",
                "expected_old_pin_digest",
                "expected_source_tree_digest",
                "expected_pin_consumer_inventory_digest",
                "expected_runtime_identity_digest",
            )
        }
        or phase1.get("old_alr_retained_running") is not True
        or staged
        != {"path": board["staged_path"], "sha256": board["source_content_sha256"]}
        or any(
            not isinstance(value, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
            for value in phase1_fence.values()
        )
    ):
        raise ObserverInputError("phase1_receipt_lineage_mismatch")

    authorization = _required_mapping(
        roots.get("cutover_authorization"), "cutover_authorization_invalid"
    )
    authorization_result = validate_cutover_authorization(
        checked,
        authorization,
        now=datetime.now(timezone.utc) if now is None else now,
    )
    cutover_runtime_payload = _required_mapping(
        roots.get("cutover_runtime_bindings"), "cutover_runtime_bindings_invalid"
    )
    cutover_runtime_result = validate_phase_runtime_bindings(
        cutover_runtime_payload,
        authorization,
        phase="cutover",
        observed_at=datetime.now(timezone.utc) if now is None else now,
        artifact_path=authorization["governance_bindings"][
            "phase_runtime_bindings_path"
        ],
        config=checked,
    )
    if any(
        authorization.get(key) != stage_result[key]
        for key in (
            "expected_old_runtime_source_head",
            "expected_old_pin_digest",
            "expected_source_tree_digest",
            "expected_pin_consumer_inventory_digest",
            "expected_runtime_identity_digest",
        )
    ) or (
        authorization_result["claim_bindings"]["p0b_target_source_attestation"]
        != stage_result["target_source_attestation_digest"]
        or authorization_result["protected_baseline_digest"]
        != stage_result["protected_baseline_digest"]
        or cutover_runtime_result["source_attestation_digest"]
        != stage_runtime_result["source_attestation_digest"]
        or cutover_runtime_result["protected_baseline_digest"]
        != stage_runtime_result["protected_baseline_digest"]
    ):
        raise ObserverInputError("stage_to_cutover_authorization_mismatch")
    closure_bundle_result = validate_phase1_closure_and_bundle(
        checked,
        phase1=phase1,
        stage_authorization=stage_authorization,
        stage_runtime_bindings=stage_runtime_payload,
        phase1_closure=_required_mapping(
            roots.get("phase1_closure"), "phase1_closure_invalid"
        ),
        sealed_lineage_bundle=_required_mapping(
            roots.get("sealed_lineage_bundle"),
            "sealed_lineage_bundle_invalid",
        ),
        phase1_closure_binding=_required_mapping(
            cutover_runtime_result.get("phase1_closure"),
            "cutover_phase1_closure_binding_invalid",
        ),
        sealed_lineage_bundle_binding=_required_mapping(
            cutover_runtime_result.get("sealed_lineage_bundle"),
            "cutover_sealed_lineage_bundle_binding_invalid",
        ),
    )
    claims = authorization_result["claim_bindings"]
    sealed_lineage_digest = closure_bundle_result[
        "sealed_lineage_bundle_raw_digest"
    ]
    private_destination_digest = "sha256:" + hashlib.sha256(
        checked["private_deps"]["destination"].encode("utf-8")
    ).hexdigest()
    if (
        claims["p0b_phase1_receipt"]
        != "sha256:" + checked["phase1_receipt"]["sha256"]
        or claims["p0b_staged_candidate_board"]
        != "sha256:" + board["source_content_sha256"]
        or claims["p0b_private_bundle_receipt"]
        != "sha256:" + checked["private_deps"]["receipt"]["sha256"]
        or claims["p0b_sealed_lineage_bundle"]
        != sealed_lineage_digest
        or authorization_result["sealed_lineage_bundle_digest"]
        != sealed_lineage_digest
        or claims["p0b_phase1_closure"]
        != authorization["phase1_closure_digest"]
        or claims["p0b_private_bundle_destination"]
        != private_destination_digest
        or claims["p0b_protected_runtime_baseline"]
        != authorization_result["protected_baseline_digest"]
        or claims["p0b_completion_inventory"]
        != phase1_fence["completion_inventory_sha256"]
        or claims["p0b_producer_inventory"]
        != phase1_fence["producer_inventory_sha256"]
    ):
        raise ObserverInputError("cutover_authorization_claim_binding_mismatch")

    provisional = _exact_fields(
        roots.get("provisional_cutover"),
        {
            "schema_version",
            "status",
            "target_head",
            "phase1_receipt",
            "cutover_authorization",
            "cutover_authorization_digest",
            "live_board",
            "unit",
            "pin",
            "private_deps_receipt",
            "private_deps_destination",
            "private_deps_manifest_sha256",
            "active_identity",
            "generation_fence",
            "observer_input_contract_sha256",
        },
        "provisional_cutover_fields_invalid",
    )
    provisional_fence = _exact_fields(
        provisional.get("generation_fence"),
        fence_fields,
        "provisional_generation_fence_fields_invalid",
    )
    if (
        provisional.get("schema_version")
        != "p0b_alr_current_head_rollforward_provisional_cutover_v1"
        or provisional.get("status") != "PHASE2_PROVISIONAL_CUTOVER_READY"
        or provisional.get("target_head") != checked["target_head"]
        or provisional.get("phase1_receipt") != checked["phase1_receipt"]
        or provisional.get("cutover_authorization")
        != checked["cutover_authorization"]
        or provisional.get("cutover_authorization_digest")
        != authorization_result["authorization_digest"]
        or provisional.get("live_board")
        != {"path": board["live_path"], "sha256": board["source_content_sha256"]}
        or provisional.get("unit") != runtime["unit"]
        or provisional.get("pin") != runtime["pin"]
        or provisional.get("private_deps_receipt")
        != checked["private_deps"]["receipt"]
        or provisional.get("private_deps_destination")
        != checked["private_deps"]["destination"]
        or provisional.get("private_deps_manifest_sha256")
        != checked["private_deps"]["manifest_sha256"]
        or provisional.get("active_identity") != checked["active_identity"]
        or dict(provisional_fence) != phase1_fence
        or provisional.get("observer_input_contract_sha256")
        != observer_input_contract_sha256(checked)
    ):
        raise ObserverInputError("provisional_cutover_lineage_mismatch")

    private = _required_mapping(
        roots.get("private_deps_receipt"), "private_deps_receipt_invalid"
    )
    expected_private_boundaries = {
        "service_mutation": False,
        "database_access": False,
        "broker_contact": False,
        "credential_access": False,
        "subprocess_spawned": False,
        "source_repository_mutation": False,
    }
    if (
        private.get("schema_version") != "p0b_psycopg_private_bundle_stage_v1"
        or private.get("status") != "APPLIED_POSTCHECK_PASS"
        or private.get("destination") != checked["private_deps"]["destination"]
        or private.get("source_manifest_sha256")
        != checked["private_deps"]["manifest_sha256"]
        or private.get("destination_manifest_sha256")
        != checked["private_deps"]["manifest_sha256"]
        or private.get("mutation_performed") is not True
        or private.get("boundaries") != expected_private_boundaries
    ):
        raise ObserverInputError("private_deps_receipt_lineage_mismatch")

    return {
        "phase1_receipt_sha256": checked["phase1_receipt"]["sha256"],
        "stage_authorization_sha256": stage_binding["sha256"],
        "stage_authorization_digest": stage_result["authorization_digest"],
        "stage_runtime_bindings_sha256": stage_runtime_binding["sha256"],
        "stage_runtime_bindings_artifact_digest": stage_runtime_result[
            "artifact_digest"
        ],
        "cutover_authorization_sha256": checked["cutover_authorization"]["sha256"],
        "cutover_authorization_digest": authorization_result[
            "authorization_digest"
        ],
        "cutover_runtime_bindings_artifact_digest": cutover_runtime_result[
            "artifact_digest"
        ],
        "observer_source_sha256": claims["p0b_observer_source"].removeprefix(
            "sha256:"
        ),
        "phase1_closure_digest": authorization["phase1_closure_digest"],
        "phase1_closure_canonical_digest": closure_bundle_result[
            "phase1_closure_digest"
        ],
        "sealed_lineage_bundle_digest": sealed_lineage_digest,
        "sealed_lineage_bundle_canonical_digest": closure_bundle_result[
            "sealed_lineage_bundle_digest"
        ],
        "target_source_attestation_digest": stage_result[
            "target_source_attestation_digest"
        ],
        "protected_baseline_digest": stage_result[
            "protected_baseline_digest"
        ],
        "provisional_cutover_sha256": checked["provisional_cutover"]["sha256"],
        "phase2_identity": dict(checked["active_identity"]),
        "live_board_sha256": board["source_content_sha256"],
        "private_deps_receipt_sha256": checked["private_deps"]["receipt"]["sha256"],
        "private_deps_manifest_sha256": checked["private_deps"]["manifest_sha256"],
        "authority": dict(checked["no_authority"]),
    }


def validate_base_pass_result(
    config: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    """Project only a v1 PASS that remains exact under the new generation input."""

    checked = validate_observer_input_payload(config)
    if (
        not isinstance(result, Mapping)
        or result.get("status") != "PASS"
        or result.get("reason_codes") != []
        or result.get("target_head") != checked["target_head"]
    ):
        raise ObserverInputError("base_observation_not_pass")
    trust = _required_mapping(result.get("trust_root"), "base_trust_root_invalid")
    board = checked["admitted_board"]
    if {
        "board_source_content_sha256": trust.get("board_source_content_sha256"),
        "board_hash": trust.get("board_hash"),
        "board_audit_hash": trust.get("board_audit_hash"),
        "selection_hash": trust.get("selection_hash"),
        "candidate_set_hash": trust.get("candidate_set_hash"),
    } != {
        "board_source_content_sha256": board["source_content_sha256"],
        "board_hash": board["board_hash"],
        "board_audit_hash": board["audit_hash"],
        "selection_hash": board["selection_hash"],
        "candidate_set_hash": board["candidate_set_hash"],
    }:
        raise ObserverInputError("base_board_trust_root_mismatch")
    runtime = _required_mapping(result.get("runtime"), "base_runtime_invalid")
    expected_runtime_identity = {
        key: checked["active_identity"][key]
        for key in (
            "MainPID",
            "ProcessStartTicks",
            "InvocationID",
            "ExecMainStartTimestampMonotonic",
        )
    }
    observed_runtime_identity = _required_mapping(
        runtime.get("identity"), "base_runtime_identity_invalid"
    )
    if (
        runtime.get("source_head") != checked["target_head"]
        or any(
            observed_runtime_identity.get(key) != value
            for key, value in expected_runtime_identity.items()
        )
        or runtime.get("nrestarts") != 0
    ):
        raise ObserverInputError("base_runtime_identity_drift")
    session = _required_mapping(result.get("session"), "base_session_invalid")
    not_before = _utc(
        checked["observer_not_before_utc"], "observer_not_before_invalid"
    )
    session_started = _utc(session.get("started_at_utc"), "base_session_time_invalid")
    if (
        session_started < not_before
        or session.get("post_pin_unique_open_session") is not True
    ):
        raise ObserverInputError("base_session_before_observer_bound")

    transaction = _required_mapping(result.get("transaction"), "base_transaction_invalid")
    start = _required_mapping(transaction.get("start"), "base_transaction_start_invalid")
    final = _required_mapping(transaction.get("final"), "base_transaction_final_invalid")
    if (
        start.get("transaction_read_only") != "on"
        or start.get("transaction_isolation") != "repeatable read"
        or start.get("xid_assigned") is not False
        or final.get("tuples_inserted") != 0
        or final.get("tuples_updated") != 0
        or final.get("tuples_deleted") != 0
        or final.get("xid_assigned") is not False
        or transaction.get("rolled_back") is not True
    ):
        raise ObserverInputError("base_transaction_not_readonly")

    cycles = result.get("cycles")
    if result.get("cycle_count") != 2 or not isinstance(cycles, list) or len(cycles) != 2:
        raise ObserverInputError("base_exact_two_cycles_required")
    lane_ids: set[str] = set()
    notification_ids: set[str] = set()
    cursors: set[tuple[str, str, str, str]] = set()
    decision_ids: set[str] = set()
    health_ids: set[str] = set()
    for cycle in cycles:
        value = _required_mapping(cycle, "base_cycle_invalid")
        notification = _required_mapping(
            value.get("notification"), "base_cycle_notification_required"
        )
        cursor = _required_mapping(value.get("cursor"), "base_cycle_cursor_invalid")
        decision = _required_mapping(value.get("decision"), "base_cycle_decision_invalid")
        health = _required_mapping(value.get("health"), "base_cycle_health_invalid")
        lane_id = str(value.get("lane_success_event_id") or "")
        notification_id = str(notification.get("event_id") or "")
        cursor_id = (
            str(cursor.get("source_ts") or ""),
            str(cursor.get("source_scan_id") or ""),
            str(cursor.get("source_hash") or ""),
            str(cursor.get("source_key") or ""),
        )
        decision_id = _hash(
            decision.get("artifact_hash"), "base_cycle_decision_hash_invalid"
        )
        health_id = _hash(health.get("snapshot_hash"), "base_cycle_health_hash_invalid")
        if (
            not lane_id
            or not notification_id
            or any(not item for item in cursor_id)
            or _utc(value.get("lane_success_recorded_at"), "base_cycle_lane_time_invalid")
            < not_before
            or _utc(notification.get("recorded_at"), "base_cycle_notification_time_invalid")
            < not_before
            or _utc(cursor.get("source_ts"), "base_cycle_source_time_invalid")
            < not_before
        ):
            raise ObserverInputError("base_cycle_before_observer_bound")
        lane_ids.add(lane_id)
        notification_ids.add(notification_id)
        cursors.add(cursor_id)
        decision_ids.add(decision_id)
        health_ids.add(health_id)
    if any(len(values) != 2 for values in (lane_ids, notification_ids, cursors, decision_ids, health_ids)):
        raise ObserverInputError("base_cycles_not_distinct")

    claims = _required_mapping(result.get("claims"), "base_claims_invalid")
    boundaries = _required_mapping(result.get("boundaries"), "base_boundaries_invalid")
    if (
        claims.get("two_natural_cycles_observed") is not True
        or claims.get("trading_or_order_authority_claimed") is not False
        or claims.get("serving_or_promotion_claimed") is not False
        or boundaries.get("pg_readonly_effect_guard_passed") is not True
        or boundaries.get("pg_tuple_write_observed") is not False
        or boundaries.get("credential_content_output") is not False
    ):
        raise ObserverInputError("base_claim_or_boundary_invalid")
    return {
        "runtime_identity": dict(checked["active_identity"]),
        "session_id": session.get("session_id"),
        "session_started_at_utc": session.get("started_at_utc"),
        "cycle_count": 2,
        "cycles_distinct": True,
        "all_cycles_post_observer_not_before": True,
        "lane_success_event_ids": sorted(lane_ids),
        "notification_consumed_event_ids": sorted(notification_ids),
        "decision_artifact_hashes": sorted(decision_ids),
        "health_snapshot_hashes": sorted(health_ids),
        "pg_readonly_single_transaction_rolled_back": True,
        "credential_content_output": False,
        "authority": dict(checked["no_authority"]),
    }


def configure_base_observer(base: Any, config: Mapping[str, Any]) -> None:
    checked = validate_observer_input_payload(config)
    board = checked["admitted_board"]
    runtime = checked["runtime_files"]
    base.TARGET_HEAD = checked["target_head"]
    base.BOARD_PATH = Path(board["live_path"])
    base.BOARD_SOURCE_CONTENT_SHA256 = board["source_content_sha256"]
    base.BOARD_HASH = board["board_hash"]
    base.BOARD_AUDIT_HASH = board["audit_hash"]
    base.SELECTION_HASH = board["selection_hash"]
    base.CANDIDATE_SET_HASH = board["candidate_set_hash"]
    base.UNIT_PATH = Path(runtime["unit"]["path"])
    base.UNIT_SHA256 = runtime["unit"]["sha256"]
    base.PIN_PATH = Path(runtime["pin"]["path"])
    base.PIN_SHA256 = runtime["pin"]["sha256"]
    base.PIN_DERIVED_AT_UTC = runtime["pin_derived_at_utc"]
    base.PG_APPLICATION_NAME = "p0b-alr-current-head-two-cycle-observer-v2"
    base.DECISION_SQL = base.DECISION_SQL.replace(
        "artifact.artifact_kind='target_rotation'",
        "artifact.artifact_kind IN ('target_rotation','learning_target')",
    ).replace(
        "artifact.canonical_payload#>>'{decision,decision_code}'=%s",
        "%s IS NOT NULL",
    )

    original_validate_cycle = base._validate_cycle
    original_validate_decision = base._validate_decision
    original_postcheck_sample = base._postcheck_sample
    dynamic_board: dict[str, Any] = {}
    not_before = _utc(
        checked["observer_not_before_utc"], "observer_not_before_invalid"
    )

    def validate_bound_board(board_outer: Mapping[str, Any]) -> dict[str, Any]:
        result = validate_dynamic_candidate_board(checked, board_outer)
        dynamic_board.clear()
        dynamic_board.update(copy.deepcopy(result))
        return result

    base._validate_board = validate_bound_board

    def postcheck_bound_board(
        sample: Mapping[str, Any], expected_identity: Mapping[str, str]
    ) -> None:
        current = _required_mapping(
            sample.get("current_board"), "postcheck_board_missing"
        )
        if (
            not dynamic_board
            or current.get("candidate_count") != dynamic_board["candidate_count"]
        ):
            raise base.ObserverUnverified("postcheck_board_candidate_count_invalid")
        shadow = copy.deepcopy(dict(sample))
        shadow["current_board"]["candidate_count"] = 0
        original_postcheck_sample(shadow, expected_identity)

    base._postcheck_sample = postcheck_bound_board

    def post_bound_cycle(row: Mapping[str, Any], session: Mapping[str, Any]) -> Any:
        cycle = original_validate_cycle(row, session)
        if cycle is None:
            return None
        if any(
            value < not_before
            for value in (
                cycle["source_ts"],
                cycle["recorded_at"],
                cycle["notification"]["recorded_at"],
            )
        ):
            raise base.ObserverFail("cycle_before_observer_not_before")
        return cycle

    base._validate_cycle = post_bound_cycle

    def generated_bound_decision(
        row: Mapping[str, Any],
        edges: list[Mapping[str, Any]],
        cycle: Mapping[str, Any],
    ) -> Any:
        payload = _required_mapping(
            row.get("canonical_payload"), "decision_payload_invalid"
        )
        refs = _required_mapping(payload.get("source_refs"), "decision_refs_invalid")
        handoff = _required_mapping(refs.get("handoff"), "decision_handoff_invalid")
        evidence = _required_mapping(
            handoff.get("evidence"), "decision_evidence_invalid"
        )
        if evidence.get("generated_at") != board["generated_at_utc"]:
            raise base.ObserverFail("decision_board_generated_at_mismatch")
        decision = _required_mapping(
            payload.get("decision"), "decision_nested_missing"
        )
        dynamic = validate_dynamic_decision_semantics(decision, dynamic_board)
        artifact_hash = _hash(
            row.get("artifact_hash"), "decision_artifact_hash_invalid"
        )
        decision_hash = _hash(
            decision.get("decision_hash"), "decision_hash_invalid"
        )
        expected_kind = (
            "learning_target"
            if dynamic["decision_code"] == "QUALIFIED_CANDIDATE_SELECTED"
            else "target_rotation"
        )
        if (
            canonical_sha256(payload) != artifact_hash
            or canonical_sha256(
                {
                    key: value
                    for key, value in decision.items()
                    if key != "decision_hash"
                }
            )
            != decision_hash
            or row.get("artifact_kind") != expected_kind
            or payload.get("decision_code") != dynamic["decision_code"]
            or payload.get("decision_hash") != decision_hash
            or payload.get("selected_candidate")
            != decision.get("selected_candidate")
            or payload.get("selected_collection_target")
            != decision.get("selected_collection_target")
        ):
            raise base.ObserverFail("decision_dynamic_artifact_binding_invalid")

        shadow_row = copy.deepcopy(dict(row))
        shadow_payload = copy.deepcopy(dict(payload))
        shadow_decision = copy.deepcopy(dict(decision))
        shadow_decision.update(
            {
                "selected_candidate": None,
                "selected_collection_target": None,
                "candidate_count": 0,
                "eligible_candidate_count": 0,
                "evaluated_candidates": [],
            }
        )
        shadow_decision["decision_hash"] = canonical_sha256(
            {
                key: value
                for key, value in shadow_decision.items()
                if key != "decision_hash"
            }
        )
        shadow_payload.update(
            {
                "decision_hash": shadow_decision["decision_hash"],
                "selected_candidate": None,
                "selected_collection_target": None,
                "decision": shadow_decision,
            }
        )
        shadow_artifact_hash = canonical_sha256(shadow_payload)
        shadow_row.update(
            {
                "artifact_kind": "target_rotation",
                "artifact_hash": shadow_artifact_hash,
                "canonical_payload": shadow_payload,
            }
        )
        shadow_edges = []
        for edge in edges:
            shadow_edge = copy.deepcopy(dict(edge))
            shadow_edge["to_artifact_hash"] = shadow_artifact_hash
            shadow_edge["edge_hash"] = canonical_sha256(
                {
                    "from_artifact_hash": shadow_edge.get("from_artifact_hash"),
                    "to_artifact_hash": shadow_artifact_hash,
                    "edge_role": shadow_edge.get("edge_role"),
                }
            )
            shadow_edges.append(shadow_edge)
        previous_code = base.DECISION_CODE
        base.DECISION_CODE = dynamic["decision_code"]
        try:
            common = original_validate_decision(shadow_row, shadow_edges, cycle)
        finally:
            base.DECISION_CODE = previous_code
        return {
            **common,
            "artifact_hash": artifact_hash,
            "decision_hash": decision_hash,
            "decision_code": dynamic["decision_code"],
        }

    base._validate_decision = generated_bound_decision


def prepare_current_git_seals(
    base: Any, recovery: Any, config: Mapping[str, Any]
) -> dict[str, Any]:
    """Seal the mutable index representation under exact HEAD+clean validation.

    The index digest is checkout-local, so it is observed twice by the inherited
    hardener rather than confused with the immutable target tree.  The target
    commit and clean stage-0 inventory remain the source authority.
    """

    index_raw, index_identity = observe_stable_regular(
        base.RECOVERY_GIT_INDEX_PATH,
        max_bytes=base.MAX_GIT_INDEX_INVENTORY_BYTES,
    )
    checked = validate_observer_input_payload(config)
    seals = checked["git_seals"]
    if (
        index_identity["sha256"] != seals["git_index_sha256"]
        or index_identity["size"] != seals["git_index_size"]
    ):
        raise ObserverInputError("target_git_index_seal_mismatch")
    base.RECOVERY_GIT_INDEX_SHA256 = seals["git_index_sha256"]
    base.RECOVERY_GIT_INDEX_SIZE = seals["git_index_size"]
    base.RECOVERY_GIT_INDEX_RECORD_COUNT = seals["tracked_file_count"]
    runtime_class = recovery.base.RecoveryRuntime
    try:
        stage = runtime_class.run(
            [*base.RECOVERY_GIT_COMMAND_PREFIX, "ls-files", "--stage", "-z"],
            env=dict(base.RECOVERY_HARDENED_GIT_ENV),
        ).stdout
    except Exception as exc:
        raise ObserverInputError("target_git_stage_inventory_failed") from exc
    if not isinstance(stage, str) or not stage.endswith("\x00"):
        raise ObserverInputError("target_git_stage_inventory_invalid")
    records = stage[:-1].split("\x00")
    if len(records) != seals["tracked_file_count"]:
        raise ObserverInputError("target_git_tracked_count_mismatch")
    for record in records:
        metadata, separator, path = record.partition("\t")
        fields = metadata.split(" ")
        if (
            separator != "\t"
            or len(fields) != 3
            or re.fullmatch(r"[0-7]{6}", fields[0]) is None
            or re.fullmatch(r"[0-9a-f]{40}", fields[1]) is None
            or fields[2] != "0"
            or fields[0] == "160000"
            or not path
            or path == ".gitmodules"
        ):
            raise ObserverInputError("target_git_stage_or_submodule_invalid")
    stage_raw = stage.encode("utf-8")
    if (
        hashlib.sha256(stage_raw).hexdigest()
        != seals["git_stage_inventory_sha256"]
        or len(stage_raw) != seals["git_stage_inventory_size"]
    ):
        raise ObserverInputError("target_git_stage_inventory_seal_mismatch")
    base.RECOVERY_GIT_STAGE_INVENTORY_SIZE = seals["git_stage_inventory_size"]
    return {
        "index_sha256": hashlib.sha256(index_raw).hexdigest(),
        "index_size": len(index_raw),
        "tracked_record_count": len(records),
        "stage_inventory_sha256": hashlib.sha256(stage.encode("utf-8")).hexdigest(),
        "stage_inventory_size": len(stage.encode("utf-8")),
        "stage0_only": True,
        "gitlink_count": 0,
    }


def load_bound_trust(
    base: Any,
    config: Mapping[str, Any],
    *,
    reader: Callable[..., tuple[bytes, dict[str, Any]]] = read_bound_regular,
    authorization_now: datetime | None = None,
) -> dict[str, Any]:
    checked = validate_observer_input_payload(config)
    configure_base_observer(base, checked)

    decoded: dict[str, dict[str, Any]] = {}
    identities: dict[str, dict[str, Any]] = {}
    phase1_raw, phase1_identity = reader(
        Path(checked["phase1_receipt"]["path"]),
        checked["phase1_receipt"]["sha256"],
        mode=0o600,
    )
    decoded["phase1_receipt"] = _decode_json_artifact(
        phase1_raw, "phase1_receipt_json_invalid"
    )
    identities["phase1_receipt"] = phase1_identity
    stage_binding = _binding(
        decoded["phase1_receipt"].get("stage_authorization"),
        "phase1_stage_authorization_binding_invalid",
    )
    stage_runtime_binding = _binding(
        decoded["phase1_receipt"].get("stage_runtime_bindings"),
        "phase1_stage_runtime_bindings_invalid",
    )
    bindings = {
        "stage_authorization": stage_binding,
        "stage_runtime_bindings": stage_runtime_binding,
        "cutover_authorization": checked["cutover_authorization"],
        "provisional_cutover": checked["provisional_cutover"],
        "private_deps_receipt": checked["private_deps"]["receipt"],
    }
    for label, binding in bindings.items():
        raw, identity = reader(
            Path(binding["path"]),
            binding["sha256"],
            mode=0o600,
        )
        decoded[label] = _decode_json_artifact(raw, f"{label}_json_invalid")
        identities[label] = identity
    cutover_governance = _required_mapping(
        decoded["cutover_authorization"].get("governance_bindings"),
        "cutover_governance_bindings_invalid",
    )
    cutover_runtime_path = Path(
        str(cutover_governance.get("phase_runtime_bindings_path", ""))
    )
    cutover_runtime_raw, cutover_runtime_identity = observe_stable_regular(
        cutover_runtime_path, max_bytes=MAX_ARTIFACT_BYTES
    )
    if (
        cutover_runtime_identity["uid"] != 1000
        or cutover_runtime_identity["gid"] != 1000
        or cutover_runtime_identity["mode"] != 0o600
    ):
        raise ObserverInputError("cutover_runtime_bindings_identity_invalid")
    decoded["cutover_runtime_bindings"] = _decode_json_artifact(
        cutover_runtime_raw, "cutover_runtime_bindings_json_invalid"
    )
    identities["cutover_runtime_bindings"] = cutover_runtime_identity
    cutover_lineage = _required_mapping(
        decoded["cutover_runtime_bindings"].get("lineage"),
        "cutover_runtime_lineage_invalid",
    )
    for label in ("phase1_closure", "sealed_lineage_bundle"):
        binding = _binding(
            cutover_lineage.get(label), f"cutover_{label}_binding_invalid"
        )
        raw, identity = reader(
            Path(binding["path"]), binding["sha256"], mode=0o600
        )
        decoded[label] = _decode_json_artifact(raw, f"{label}_json_invalid")
        identities[label] = identity
    lineage = validate_lineage_payloads(
        checked, decoded, now=authorization_now
    )
    lineage["cutover_runtime_bindings_sha256"] = cutover_runtime_identity[
        "sha256"
    ]
    _observer_source_raw, observer_source_identity = reader(
        Path(__file__), lineage["observer_source_sha256"], mode=None
    )

    board = checked["admitted_board"]
    staged_raw, staged_identity = reader(
        Path(board["staged_path"]), board["source_content_sha256"], mode=None
    )
    live_raw, live_identity = reader(
        Path(board["live_path"]), board["source_content_sha256"], mode=None
    )
    if staged_raw != live_raw:
        raise ObserverInputError("staged_live_board_bytes_mismatch")
    validated_board = base._validate_board(
        base._strict_json(live_raw, label="current_head_live_board")
    )

    source_binding = checked["consumer_source"]
    source_raw, source_identity = reader(
        Path(source_binding["path"]),
        source_binding["sha256"],
        mode=None,
    )
    source_invariants = _consumer_source_order_invariants(
        source_raw, source_binding["sha256"]
    )

    runtime = checked["runtime_files"]
    unit_raw, unit_identity = reader(
        Path(runtime["unit"]["path"]), runtime["unit"]["sha256"], mode=0o600
    )
    try:
        unit_text = unit_raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ObserverInputError("unit_not_utf8") from exc
    if unit_text.count(checked["target_head"]) != 1:
        raise ObserverInputError("unit_target_head_binding_invalid")
    pin_raw, pin_identity = reader(
        Path(runtime["pin"]["path"]), runtime["pin"]["sha256"], mode=0o600
    )
    pin = _decode_json_artifact(pin_raw, "pin_json_invalid")
    if (
        pin.get("head") != checked["target_head"]
        or pin.get("derived_at_utc") != runtime["pin_derived_at_utc"]
        or pin.get("base_dir") != "/home/ncyu/BybitOpenClaw/srv"
    ):
        raise ObserverInputError("pin_payload_invalid")
    lower_bound = _utc(
        checked["observer_not_before_utc"], "observer_not_before_invalid"
    )
    service_identity = {
        key: checked["active_identity"][key]
        for key in (
            "MainPID",
            "ProcessStartTicks",
            "InvocationID",
            "ExecMainStartTimestampMonotonic",
        )
    }
    return {
        "lower_bound": lower_bound,
        "lower_bound_text": checked["observer_not_before_utc"],
        "service_identity": service_identity,
        "board": validated_board,
        "lineage": lineage,
        "source_raw": source_raw,
        "source_ordering_invariants": source_invariants,
        "identities": {
            **identities,
            "observer_source": observer_source_identity,
            "staged_board": staged_identity,
            "live_board": live_identity,
            "consumer_source": source_identity,
            "unit": unit_identity,
            "pin": pin_identity,
        },
    }


def install_startup_query_capture(
    base: Any,
    config: Mapping[str, Any],
    capture: dict[str, Any],
) -> None:
    checked = validate_observer_input_payload(config)
    original_fetch_all = base._fetch_all
    board = checked["admitted_board"]

    def fetch_all(
        cursor: Any,
        sql: str,
        params: Sequence[Any] = (),
        *,
        maximum: int,
        overflow_reason: str,
    ) -> list[Mapping[str, Any]]:
        if sql == base.CYCLES_SQL:
            if capture:
                raise base.ObserverFail("startup_query_capture_repeated")
            session_id, session_started = params
            rows = original_fetch_all(
                cursor,
                STARTUP_RECONCILIATION_SQL,
                (
                    session_id,
                    session_started,
                    checked["target_head"],
                    board["source_content_sha256"],
                    board["board_hash"],
                    board["audit_hash"],
                    board["selection_hash"],
                    board["candidate_set_hash"],
                ),
                maximum=2,
                overflow_reason="startup_reconciliation_row_limit_exceeded",
            )
            capture.update(
                {
                    "session_id": str(session_id),
                    "session_started": session_started,
                    "rows": rows,
                }
            )
        return original_fetch_all(
            cursor,
            sql,
            params,
            maximum=maximum,
            overflow_reason=overflow_reason,
        )

    base._fetch_all = fetch_all


def startup_proof_from_capture(
    base: Any,
    config: Mapping[str, Any],
    capture: Mapping[str, Any],
) -> dict[str, Any]:
    checked = validate_observer_input_payload(config)
    rows = capture.get("rows")
    if not isinstance(rows, list) or len(rows) != 1:
        raise ObserverInputError("startup_reconciliation_row_ambiguous_or_missing")
    row = _required_mapping(rows[0], "startup_reconciliation_row_invalid")
    payload = _required_mapping(
        row.get("canonical_payload"), "startup_reconciliation_payload_invalid"
    )
    artifact_hash = _hash(
        row.get("artifact_hash"), "startup_reconciliation_artifact_hash_invalid"
    )
    if canonical_sha256(payload) != artifact_hash:
        raise ObserverInputError("startup_reconciliation_artifact_hash_mismatch")
    decision = _required_mapping(
        payload.get("decision"), "startup_reconciliation_decision_invalid"
    )
    refs = _required_mapping(
        payload.get("source_refs"), "startup_reconciliation_source_refs_invalid"
    )
    handoff = _required_mapping(
        refs.get("handoff"), "startup_reconciliation_handoff_invalid"
    )
    evidence = _required_mapping(
        handoff.get("evidence"), "startup_reconciliation_evidence_invalid"
    )
    try:
        base._require_no_authority(
            payload.get("no_authority"), "startup_outer_authority_invalid"
        )
        base._require_no_authority(
            decision.get("no_authority"), "startup_decision_authority_invalid"
        )
        base._require_no_authority(
            handoff.get("no_authority", decision.get("no_authority")),
            "startup_handoff_authority_invalid",
        )
    except Exception as exc:
        raise ObserverInputError("startup_reconciliation_authority_invalid") from exc
    for field in getattr(base, "FALSE_CLAIMS", ()):
        if payload.get(field) is not False or decision.get(field) is not False:
            raise ObserverInputError("startup_reconciliation_false_claim_invalid")
    board = checked["admitted_board"]
    proof = {
        "schema_version": "p0b_alr_startup_reconciliation_temporal_v1",
        "session_id": capture.get("session_id"),
        "session_started_at_utc": base._utc_z(
            capture.get("session_started"), "startup_session_time_invalid"
        ),
        "decision_row_count": 1,
        "decision": {
            "artifact_hash": artifact_hash,
            "created_at_utc": base._utc_z(
                row.get("created_at"), "startup_decision_time_invalid"
            ),
            "board_generated_at_utc": evidence.get("generated_at"),
            "source_head": decision.get("source_head"),
            "source_content_sha256": evidence.get("source_content_sha256"),
            "board_hash": evidence.get("board_hash"),
            "audit_hash": evidence.get("audit_hash"),
            "selection_hash": evidence.get("selection_hash"),
            "candidate_set_hash": evidence.get("candidate_set_hash"),
            "no_authority": True,
        },
        "first_notification_received_row_count": 1,
        "first_notification_received": {
            "event_id": row.get("first_notification_event_id"),
            "recorded_at_utc": base._utc_z(
                row.get("first_notification_recorded_at"),
                "startup_notification_time_invalid",
            ),
        },
        "same_session": True,
        "pg_explicit_trigger_claimed": False,
    }
    return validate_startup_reconciliation_proof(
        checked,
        read_bound_regular(
            Path(checked["consumer_source"]["path"]),
            checked["consumer_source"]["sha256"],
            mode=None,
        )[0],
        proof,
    )


def run_current_observation(
    config: Mapping[str, Any],
    *,
    base_loader: Callable[[], Any] = load_exact_base_observer,
    artifact_reader: Callable[..., tuple[bytes, dict[str, Any]]] = read_bound_regular,
    environment: Mapping[str, str] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Run the sealed v1 observer once and add current-head/startup bindings."""

    checked = validate_observer_input_payload(config)
    base = base_loader()
    observation_started_at = now()
    trust = load_bound_trust(
        base,
        checked,
        reader=artifact_reader,
        authorization_now=observation_started_at,
    )
    capture: dict[str, Any] = {}
    install_startup_query_capture(base, checked, capture)

    def recovery_loader() -> Any:
        recovery = build_readonly_runtime_module(base, checked["target_head"])
        prepare_current_git_seals(base, recovery, checked)
        return recovery

    connect_calls = 0

    def connect_once(parameters: Mapping[str, str]) -> Any:
        nonlocal connect_calls
        connect_calls += 1
        if connect_calls != 1:
            raise base.ObserverUnverified("pg_reconnect_attempt_forbidden")
        return base.connect_readonly(parameters)

    base_result = base.run_observation(
        trust_loader=lambda _reader: trust,
        file_reader=base._read_bound_file,
        recovery_module_loader=recovery_loader,
        dsn_loader=base.read_exact_dsn,
        connect=connect_once,
        lock_observer=base.observe_singleton_lock,
        environment=os.environ if environment is None else environment,
        now=now,
    )
    if connect_calls != 1:
        raise ObserverInputError("pg_connection_count_invalid")
    cycles = validate_base_pass_result(checked, base_result)
    startup = startup_proof_from_capture(base, checked, capture)
    if (
        startup["session_id"] != cycles["session_id"]
        or startup["session_started_at_utc"] != cycles["session_started_at_utc"]
    ):
        raise ObserverInputError("startup_cycle_session_binding_mismatch")
    return {
        "schema_version": SCHEMA,
        "status": "OBSERVER_V2_EXACT_POSTCHECK_PASS",
        "reason_codes": [],
        "observed_at_utc": now().astimezone(timezone.utc).isoformat().replace(
            "+00:00", "Z"
        ),
        "target_head": checked["target_head"],
        "observer_not_before_utc": checked["observer_not_before_utc"],
        "input": {
            "schema_version": INPUT_SCHEMA,
            "canonical_sha256": canonical_sha256(checked),
            "parent_o_excl_creation_required": True,
            "parent_o_excl_creation_claimed_by_observer": False,
        },
        "lineage": trust["lineage"],
        "runtime_and_cycles": cycles,
        "startup_reconciliation": startup,
        "private_dependencies": {
            "receipt_sha256": checked["private_deps"]["receipt"]["sha256"],
            "manifest_sha256": checked["private_deps"]["manifest_sha256"],
            "exact_bundle_verified_by_base_before_pg_connect": True,
        },
        "database": {
            "connection_count": 1,
            "reconnect_performed": False,
            "transaction_readonly_repeatable_read": True,
            "rolled_back": True,
            "tuple_mutation_observed": False,
        },
        "claims": {
            "startup_reconciliation_observed_by_combined_surfaces": True,
            "pg_explicit_trigger_claimed": False,
            "two_notification_backed_natural_cycles_observed": True,
            "current_fit_claimed": False,
            "training_or_model_fit_claimed": False,
            "serving_or_promotion_claimed": False,
            "trading_or_order_authority_claimed": False,
        },
        "boundaries": {
            "service_mutation_performed": False,
            "source_mutation_performed": False,
            "database_mutation_performed": False,
            "broker_contact_performed": False,
            "credential_content_output": False,
        },
    }


def _failure(reason: str, target_head: str | None = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA,
        "status": "UNVERIFIED",
        "reason_codes": [reason],
        "target_head": target_head,
        "claims": {
            "startup_reconciliation_observed_by_combined_surfaces": False,
            "pg_explicit_trigger_claimed": False,
            "two_notification_backed_natural_cycles_observed": False,
        },
        "boundaries": {
            "service_mutation_performed": False,
            "source_mutation_performed": False,
            "database_mutation_performed": False,
            "broker_contact_performed": False,
            "credential_content_output": False,
        },
    }


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    result: dict[str, Any]
    try:
        if sys.flags.isolated != 1 or sys.dont_write_bytecode is not True:
            raise ObserverInputError("isolated_no_bytecode_runtime_required")
        if len(arguments) != 4 or arguments[0] != "--observer-input" or arguments[2] != "--observer-input-sha256":
            raise ObserverInputError("cli_contract_invalid")
        input_path = Path(arguments[1])
        if not input_path.is_absolute():
            raise ObserverInputError("observer_input_path_not_absolute")
        config, identity = load_observer_input(input_path, arguments[3])
        result = run_current_observation(config)
        result["input"]["identity"] = identity
    except ObserverInputError as exc:
        result = _failure(exc.reason)
    except Exception as exc:
        result = _failure("observer_internal_unverified:" + type(exc).__name__)
    print(canonical_bytes(result).decode("utf-8"), flush=True)
    return 0 if result["status"] == "OBSERVER_V2_EXACT_POSTCHECK_PASS" else 5


if __name__ == "__main__":
    raise SystemExit(main())

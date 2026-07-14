"""Canonical validation contract for cost-gate learning candidate boards.

This module owns the frozen v2 field sets and the fail-closed validator.  It has
no dependency on the board producer so candidate_board can expose the validator
as a compatible facade without an import cycle.
"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any

from cost_gate_learning_lane.cost_model import (
    FEE_FLOOR_BPS,
    MIN_SYMBOL_FILLS_FOR_QUANTILE,
    QUANTILE_ARTIFACT_MAX_AGE_HOURS,
)

LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION = "cost_gate_learning_candidate_board_v2"
LEARNING_CANDIDATE_SCHEMA_VERSION = "cost_gate_learning_candidate_v2"
ARBITER_INPUT_SCHEMA_VERSION = "alr_candidate_arbiter_input_v2"
COST_EVIDENCE_SCHEMA_VERSION = "alr_candidate_cost_evidence_v2"
_CANDIDATE_FAMILY_SCHEMA_VERSION = "candidate_learning_family_v2"
_SELECTION_SCHEMA_VERSION = "cost_gate_learning_candidate_selection_v2"
_AUDIT_SCHEMA_VERSION = "cost_gate_learning_candidate_audit_v2"
_SELECTION_N_EFF_MIN = 30
_SELECTION_UTC_DAYS_MIN = 5
_SELECTION_TOP_DAY_SHARE_MAX_PCT = 50.0
_SIDE_CELL_AMBIGUITY_BLOCKER = "SIDE_CELL_STABLE_COHORT_AMBIGUITY"
_UNQUALIFIED_EXCLUSION_REASONS = {
    "UNQUALIFIED_CONTEXT_MISSING",
    "UNQUALIFIED_LEGACY_PROJECTION_ONLY",
    "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING",
    "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW",
}
_INVALID_EXCLUSION_REASONS = {
    "INVALID_LINEAGE_RAW_CONTEXT_INVALID",
    "INVALID_LINEAGE_IDENTITY_FAMILY",
    "INVALID_LINEAGE_EXACT_COHORT",
}
_LINEAGE_EXCLUSION_REASONS = (
    _UNQUALIFIED_EXCLUSION_REASONS | _INVALID_EXCLUSION_REASONS
)
_ARBITER_IDENTITY_FIELDS = {
    "strategy_name",
    "strategy_version",
    "config_hash",
    "symbol",
    "side",
    "horizon_minutes",
    "target_regime",
    "engine_mode",
    "evidence_engine_mode",
    "venue",
    "product",
}
_TARGET_REGIME_FIELDS = {
    "label",
    "utc_date",
    "hash",
    "point_in_time",
    "source_complete",
    "source_hash",
    "classifier_hash",
}
_CONTEXT_HASH_FIELDS = {"data", "evidence", "cost", "portfolio"}
_QUALITY_FIELDS = {
    "hash_ok",
    "integrity_ok",
    "freshness_ok",
    "censored_share",
    "cost_recomputable_share",
    "unknown_regime_share",
    "replica_inconsistency_count",
    "cluster_variance_clean",
    "legacy_optimistic_cost_present",
    "hidden_oos_consumed",
    "top_day_share",
}
_EVIDENCE_FIELDS = {
    "n_eff",
    "utc_day_count",
    "mean_net_e",
    "day_cluster_variance",
    "cluster_se",
    "cluster_count",
    "proof_stage",
    "completed_proof_stages",
    "next_gap",
    "raw_attempt_count",
    "regime_entry_counts",
}
_NEXT_GAP_FIELDS = {"kind", "code"}
_RESOURCE_FIELDS = {
    "daily_buckets",
    "estimated_rows_scanned",
    "predicted_canonical_bytes",
    "zero_resource_attested",
    "resource_estimator_hash",
}
_RESOURCE_BUCKET_FIELDS = {"utc_date", "scan_complete", "distinct_entries"}
_PORTFOLIO_FIELDS = {
    "sector_exposure_share",
    "strategy_active_target_share",
    "beta_to_portfolio",
}
_COST_EVIDENCE_FIELDS = {
    "schema_version",
    "basis",
    "source_asof_utc",
    "source_payload_sha256",
    "normalized_projection_sha256",
    "max_age_hours",
    "fee_floor_bps",
    "mean_abs_source",
    "tail_source",
}
_MEAN_ABS_SOURCE_FIELDS = {"scope", "symbol", "sample_count", "mean_abs_bps"}
_TAIL_SOURCE_FIELDS = {
    "scope", "symbol", "sample_count", "tail_bps", "tail_metric"
}
_CANDIDATE_COUNT_FIELDS = {
    "qualified_raw_outcome_count",
    "qualified_evaluator_input_count",
    "qualified_uncensored_outcome_count",
    "qualified_valid_uncensored_outcome_count",
    "qualified_invalid_outcome_row_count",
    "qualified_censored_outcome_count",
    "consistent_duplicate_event_hash_extra_row_count",
    "conflicting_event_hash_row_count",
    "duplicate_event_hash_outcome_conflict_row_count",
    "duplicate_event_hash_cohort_conflict_row_count",
    "invalid_lineage_exact_cohort_row_count",
    "invalid_lineage_identity_family_row_count",
    "qualified_distinct_entry_observation_count",
    "qualified_duplicate_outcome_row_count",
    "qualified_window_overlap_excluded_entry_count",
    "qualified_entry_ts_missing_row_count",
    "n_eff",
    "distinct_entry_utc_days",
    "replica_inconsistent_group_count",
    "cluster_count",
    "expected_cost_recomputable_count",
    "tail_cost_recomputable_count",
}
_BOARD_FIELDS = set(
    """
schema_version as_of_utc_date candidate_universe_complete lineage_partition_complete
raw_blocked_outcome_row_count qualified_lineage_outcome_row_count
unqualified_lineage_outcome_row_count invalid_lineage_outcome_row_count
invalid_exact_cohort_row_count invalid_identity_family_row_count
unassigned_invalid_lineage_outcome_row_count
unqualified_raw_valid_evaluation_missing_row_count
unqualified_event_outside_evaluation_window_row_count
consistent_duplicate_event_hash_extra_row_count
conflicting_duplicate_event_hash_row_count
conflicting_duplicate_event_hash_attribution_row_count
lineage_exclusion_reason_counts candidate_rows
selection_hash audit_hash board_hash
""".split()
)
_SELECTION_FIELDS = tuple(
    """
schema_version candidate_id candidate_family_key stable_cohort_hash candidate_identity
identity_complete arbiter_input arbiter_input_complete selection_eligible blockers
""".split()
)
_TOP_AUDIT_FIELDS = tuple(
    """
lineage_partition_complete raw_blocked_outcome_row_count
qualified_lineage_outcome_row_count unqualified_lineage_outcome_row_count
invalid_lineage_outcome_row_count invalid_exact_cohort_row_count
invalid_identity_family_row_count unassigned_invalid_lineage_outcome_row_count
unqualified_raw_valid_evaluation_missing_row_count
unqualified_event_outside_evaluation_window_row_count
consistent_duplicate_event_hash_extra_row_count conflicting_duplicate_event_hash_row_count
conflicting_duplicate_event_hash_attribution_row_count
lineage_exclusion_reason_counts
""".split()
)
_CANDIDATE_ROW_FIELDS = set(
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
_REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)


def _exact_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _sha256_text(value: Any) -> bool:
    return bool(
        _exact_text(value)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def _git_sha_text(value: Any) -> bool:
    return bool(
        _exact_text(value)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
    )


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _exact_value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        return set(left) == set(right) and all(
            _exact_value_equal(left[key], right[key]) for key in left
        )
    if isinstance(left, list) and isinstance(right, list):
        return len(left) == len(right) and all(
            _exact_value_equal(a, b) for a, b in zip(left, right)
        )
    if type(left) is not type(right):
        return False
    if type(left) is float and left == right == 0.0:
        return math.copysign(1.0, left) == math.copysign(1.0, right)
    return left == right


def _candidate_family_key(identity: dict[str, Any]) -> str:
    return _canonical_sha256(
        {
            "schema_version": _CANDIDATE_FAMILY_SCHEMA_VERSION,
            "identity": identity,
        }
    )


def _candidate_row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
    identity = row["candidate_identity"]
    return (
        identity["strategy_name"],
        identity["strategy_version"],
        identity["strategy_config_hash"],
        identity["symbol"],
        identity["side"],
        identity["horizon_minutes"],
        identity["target_regime_hash"],
        identity["venue"],
        identity["product"],
        identity["engine_mode"],
        row["candidate_id"],
        row["stable_cohort_hash"],
    )


def validate_learning_candidate_board_v2(value: Mapping[str, Any]) -> dict[str, Any]:
    """驗證 board-v2 全部 canonical hashes 與可重建 identity，不接受 rehashed poison。"""
    if not isinstance(value, Mapping) or set(value) != _BOARD_FIELDS:
        raise ValueError("candidate_board_fields_invalid")
    board = dict(value)
    if board.get("schema_version") != LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION:
        raise ValueError("board_schema_invalid")
    if board.get("candidate_universe_complete") is not True:
        raise ValueError("candidate_universe_incomplete")
    as_of_raw = board.get("as_of_utc_date")
    if not isinstance(as_of_raw, str) or not _canonical_utc_date(as_of_raw):
        raise ValueError("board_as_of_utc_date_invalid")
    as_of_date = dt.date.fromisoformat(as_of_raw)
    if board.get("lineage_partition_complete") is not True:
        raise ValueError("candidate_board_count_invariant_violation")

    count_fields = set(_TOP_AUDIT_FIELDS) - {
        "lineage_partition_complete",
        "lineage_exclusion_reason_counts",
    }
    if any(
        isinstance(board.get(field), bool)
        or not isinstance(board.get(field), int)
        or board[field] < 0
        for field in count_fields
    ):
        raise ValueError("candidate_board_count_invalid")
    if board["raw_blocked_outcome_row_count"] != (
        board["qualified_lineage_outcome_row_count"]
        + board["unqualified_lineage_outcome_row_count"]
        + board["invalid_lineage_outcome_row_count"]
    ):
        raise ValueError("candidate_board_count_invariant_violation")
    if board["invalid_lineage_outcome_row_count"] != (
        board["invalid_exact_cohort_row_count"]
        + board["invalid_identity_family_row_count"]
        + board["unassigned_invalid_lineage_outcome_row_count"]
    ):
        raise ValueError("candidate_board_count_invariant_violation")
    reason_counts = board.get("lineage_exclusion_reason_counts")
    if not _valid_count_mapping(reason_counts) or sum(reason_counts.values()) != (
        board["unqualified_lineage_outcome_row_count"]
        + board["invalid_lineage_outcome_row_count"]
    ):
        raise ValueError("candidate_board_reason_counts_invalid")
    if (
        not set(reason_counts).issubset(_LINEAGE_EXCLUSION_REASONS)
        or sum(reason_counts.get(code, 0) for code in _UNQUALIFIED_EXCLUSION_REASONS)
        != board["unqualified_lineage_outcome_row_count"]
        or sum(reason_counts.get(code, 0) for code in _INVALID_EXCLUSION_REASONS)
        != board["invalid_lineage_outcome_row_count"]
        or reason_counts.get("INVALID_LINEAGE_EXACT_COHORT", 0)
        != board["invalid_exact_cohort_row_count"]
        or reason_counts.get("INVALID_LINEAGE_IDENTITY_FAMILY", 0)
        != board["invalid_identity_family_row_count"]
        or reason_counts.get("INVALID_LINEAGE_RAW_CONTEXT_INVALID", 0)
        != board["unassigned_invalid_lineage_outcome_row_count"]
        or reason_counts.get("UNQUALIFIED_RAW_VALID_EVALUATION_MISSING", 0)
        != board["unqualified_raw_valid_evaluation_missing_row_count"]
        or reason_counts.get("UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW", 0)
        != board["unqualified_event_outside_evaluation_window_row_count"]
    ):
        raise ValueError("candidate_board_reason_counts_invalid")

    rows = board.get("candidate_rows")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("candidate_rows_invalid")
    normalized_rows = [dict(row) for row in rows]
    row_validations = [
        _validate_candidate_row_v2(row) for row in normalized_rows
    ]
    if any(recorded_date > as_of_date for recorded_date, _ in row_validations):
        raise ValueError("board_generation_precedes_evaluation")
    otherwise_eligible_cohorts: dict[str, set[str]] = {}
    for row, (_, base_blockers) in zip(normalized_rows, row_validations):
        if not base_blockers:
            otherwise_eligible_cohorts.setdefault(
                row["side_cell_key"], set()
            ).add(row["stable_cohort_hash"])
    for row, (_, base_blockers) in zip(normalized_rows, row_validations):
        expected_ambiguity = bool(
            not base_blockers
            and len(otherwise_eligible_cohorts.get(row["side_cell_key"], ())) > 1
        )
        actual_ambiguity = _SIDE_CELL_AMBIGUITY_BLOCKER in row["blockers"]
        if actual_ambiguity is not expected_ambiguity:
            raise ValueError("candidate_ambiguity_blockers_invalid")
        if row.get("selection_eligible") is not (not row["blockers"]):
            raise ValueError("candidate_selection_eligibility_invalid")
    if (
        sum(row["qualified_raw_outcome_count"] for row in normalized_rows)
        != board["qualified_lineage_outcome_row_count"]
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
        raise ValueError("candidate_board_count_invariant_violation")
    consistent_duplicate_total = sum(
        row["consistent_duplicate_event_hash_extra_row_count"]
        for row in normalized_rows
    )
    conflict_attribution_total = sum(
        row["conflicting_event_hash_row_count"] for row in normalized_rows
    )
    max_candidate_conflict_attribution = max(
        (row["conflicting_event_hash_row_count"] for row in normalized_rows),
        default=0,
    )
    unique_conflict_total = board["conflicting_duplicate_event_hash_row_count"]
    if (
        board["consistent_duplicate_event_hash_extra_row_count"]
        != consistent_duplicate_total
        or board["conflicting_duplicate_event_hash_attribution_row_count"]
        != conflict_attribution_total
        or unique_conflict_total < max_candidate_conflict_attribution
        or unique_conflict_total > conflict_attribution_total
        or unique_conflict_total > board["raw_blocked_outcome_row_count"]
        or (unique_conflict_total == 0) != (conflict_attribution_total == 0)
    ):
        raise ValueError("candidate_board_duplicate_totals_invalid")
    if len({row["candidate_id"] for row in normalized_rows}) != len(normalized_rows):
        raise ValueError("candidate_id_collision")
    if not _exact_value_equal(
        normalized_rows,
        sorted(normalized_rows, key=_candidate_row_sort_key),
    ):
        raise ValueError("candidate_rows_order_invalid")

    semantic_rows = [
        {field: row[field] for field in _SELECTION_FIELDS}
        for row in normalized_rows
    ]
    semantic_rows.sort(
        key=lambda row: (row["candidate_id"], _canonical_sha256(row))
    )
    expected_selection_hash = _canonical_sha256(
        {
            "schema_version": _SELECTION_SCHEMA_VERSION,
            "candidate_rows": semantic_rows,
        }
    )
    if board.get("selection_hash") != expected_selection_hash:
        raise ValueError("selection_hash_invalid")

    selection_field_set = set(_SELECTION_FIELDS)
    candidate_audit_rows = [
        {
            "candidate_id": row["candidate_id"],
            **{
                key: item
                for key, item in row.items()
                if key not in selection_field_set and key != "candidate_id"
            },
        }
        for row in normalized_rows
    ]
    candidate_audit_rows.sort(key=lambda row: row["candidate_id"])
    expected_audit_hash = _canonical_sha256(
        {
            "schema_version": _AUDIT_SCHEMA_VERSION,
            **{field: board[field] for field in _TOP_AUDIT_FIELDS},
            "candidate_audit_rows": candidate_audit_rows,
        }
    )
    if board.get("audit_hash") != expected_audit_hash:
        raise ValueError("audit_hash_invalid")
    body = {key: item for key, item in board.items() if key != "board_hash"}
    if board.get("board_hash") != _canonical_sha256(body):
        raise ValueError("board_hash_invalid")
    return copy.deepcopy(board)


def _valid_count_mapping(value: Any) -> bool:
    return bool(
        isinstance(value, Mapping)
        and all(
            isinstance(key, str) and key and key == key.strip()
            for key in value
        )
        and all(
            isinstance(count, int) and not isinstance(count, bool) and count > 0
            for count in value.values()
        )
    )


def _validate_candidate_row_v2(
    row: dict[str, Any],
) -> tuple[dt.date, set[str]]:
    if set(row) != _CANDIDATE_ROW_FIELDS:
        raise ValueError("candidate_row_fields_invalid")
    if row.get("schema_version") != LEARNING_CANDIDATE_SCHEMA_VERSION:
        raise ValueError("candidate_schema_invalid")
    for field in ("candidate_id", "candidate_family_key", "stable_cohort_hash"):
        if not _sha256_text(row.get(field)):
            raise ValueError(f"{field}_invalid")
    arbiter_input = row.get("arbiter_input")
    if not isinstance(arbiter_input, Mapping):
        raise ValueError("arbiter_input_invalid")
    if arbiter_input.get("schema_version") != ARBITER_INPUT_SCHEMA_VERSION:
        raise ValueError("arbiter_input_schema_invalid")
    if set(arbiter_input) != {
        "schema_version",
        "identity",
        "context_hashes",
        "cost_evidence",
        "quality",
        "evidence",
        "resource",
        "portfolio",
        "arbiter_input_hash",
    }:
        raise ValueError("arbiter_input_fields_invalid")
    arbiter_body = {
        key: item for key, item in arbiter_input.items() if key != "arbiter_input_hash"
    }
    if arbiter_input.get("arbiter_input_hash") != _canonical_sha256(arbiter_body):
        raise ValueError("arbiter_input_hash_invalid")
    _validate_arbiter_input_nested_fields(arbiter_input)
    target_date_raw = arbiter_input["identity"]["target_regime"].get("utc_date")
    try:
        target_date = dt.date.fromisoformat(target_date_raw)
    except (TypeError, ValueError):
        raise ValueError("candidate_identity_semantics_invalid") from None
    if target_date.isoformat() != target_date_raw:
        raise ValueError("candidate_identity_semantics_invalid")
    recorded_evaluation_date = target_date + dt.timedelta(days=1)
    _validate_arbiter_identity_semantics(
        arbiter_input["identity"],
        as_of_date=recorded_evaluation_date,
    )
    _validate_arbiter_input_semantics(arbiter_input)
    _validate_cost_evidence(
        arbiter_input["cost_evidence"],
        identity=arbiter_input["identity"],
        as_of_date=recorded_evaluation_date,
    )
    try:
        arbiter_identity = arbiter_input["identity"]
        target = arbiter_identity["target_regime"]
        context_hashes = arbiter_input["context_hashes"]
        raw_identity = {
            "strategy_name": arbiter_identity["strategy_name"],
            "strategy_version": arbiter_identity["strategy_version"],
            "strategy_config_hash": arbiter_identity["config_hash"],
            "symbol": arbiter_identity["symbol"],
            "side": arbiter_identity["side"],
            "horizon_minutes": arbiter_identity["horizon_minutes"],
            "venue": arbiter_identity["venue"],
            "product": arbiter_identity["product"],
            "evidence_engine_mode": arbiter_identity["evidence_engine_mode"],
        }
        target_context = {
            key: item for key, item in target.items() if key != "hash"
        }
        expected_candidate_identity = {
            **raw_identity,
            "target_regime_context": target_context,
            "target_regime_hash": target["hash"],
            "engine_mode": "shadow",
        }
        evidence = arbiter_input["evidence"]
        stable_projection = {
            "strategy_version": raw_identity["strategy_version"],
            "strategy_config_hash": raw_identity["strategy_config_hash"],
            "target_regime_context": {
                key: target_context[key] for key in ("label", "utc_date", "point_in_time")
            },
            "target_regime_hash": target["hash"],
            "venue": raw_identity["venue"],
            "product": raw_identity["product"],
            "evidence_engine_mode": raw_identity["evidence_engine_mode"],
            "context_hashes": context_hashes,
            "resource": arbiter_input["resource"],
            "portfolio": arbiter_input["portfolio"],
            "proof": {
                "proof_stage": evidence["proof_stage"],
                "completed_proof_stages": evidence["completed_proof_stages"],
                "next_gap": evidence["next_gap"],
            },
            "hidden_oos_consumed": arbiter_input["quality"]["hidden_oos_consumed"],
        }
    except (KeyError, TypeError) as exc:
        raise ValueError("candidate_identity_contract_invalid") from exc
    if not _exact_value_equal(row.get("candidate_identity"), expected_candidate_identity):
        raise ValueError("candidate_identity_mismatch")
    expected_candidate_id = _canonical_sha256(
        {
            "schema_version": LEARNING_CANDIDATE_SCHEMA_VERSION,
            "identity": arbiter_identity,
            "context_hashes": context_hashes,
        }
    )
    if row["candidate_id"] != expected_candidate_id:
        raise ValueError("candidate_id_invalid")
    if row["candidate_family_key"] != _candidate_family_key(raw_identity):
        raise ValueError("candidate_family_key_invalid")
    if row["stable_cohort_hash"] != _canonical_sha256(
        {"identity": raw_identity, "stable_projection": stable_projection}
    ):
        raise ValueError("stable_cohort_hash_invalid")
    flag_fields = {
        "arbiter_input_complete",
        "selection_eligible",
        "qualified_metrics_actionable",
        "zero_variance_suspect",
        "data_integrity_suspect",
        "cluster_variance_clean",
        "legacy_optimistic_cost_present",
        "hidden_oos_consumed",
    }
    if row.get("identity_complete") is not True or any(
        not isinstance(row.get(field), bool) for field in flag_fields
    ):
        raise ValueError("candidate_flags_invalid")
    if (
        not isinstance(row.get("blockers"), list)
        or not all(
            isinstance(code, str) and code and code == code.strip()
            for code in row["blockers"]
        )
        or row["blockers"] != sorted(set(row["blockers"]))
    ):
        raise ValueError("candidate_blockers_invalid")
    if not _valid_count_mapping(row.get("lineage_blocker_reason_counts")):
        raise ValueError("candidate_lineage_counts_invalid")
    if any(
        not _nonnegative_int_value(row.get(field))
        for field in _CANDIDATE_COUNT_FIELDS
    ):
        raise ValueError("candidate_count_invalid")
    if row.get("side_cell_key") != (
        f"{raw_identity['strategy_name']}|{raw_identity['symbol']}|{raw_identity['side']}"
    ) or row.get("horizon_minutes") != raw_identity["horizon_minutes"]:
        raise ValueError("candidate_outer_identity_invalid")
    if row["qualified_evaluator_input_count"] != (
        row["qualified_uncensored_outcome_count"]
        + row["qualified_censored_outcome_count"]
    ) or row["qualified_uncensored_outcome_count"] != (
        row["qualified_valid_uncensored_outcome_count"]
        + row["qualified_invalid_outcome_row_count"]
    ):
        raise ValueError("candidate_count_invariant_violation")
    accounted_qualified_rows = (
        row["qualified_evaluator_input_count"]
        + row["consistent_duplicate_event_hash_extra_row_count"]
    )
    if not accounted_qualified_rows <= row["qualified_raw_outcome_count"] <= (
        accounted_qualified_rows + row["conflicting_event_hash_row_count"]
    ):
        raise ValueError("candidate_board_count_invariant_violation")
    if row["n_eff"] > row["qualified_valid_uncensored_outcome_count"]:
        raise ValueError("candidate_n_eff_invalid")
    if row["conflicting_event_hash_row_count"] != (
        row["duplicate_event_hash_outcome_conflict_row_count"]
        + row["duplicate_event_hash_cohort_conflict_row_count"]
    ):
        raise ValueError("candidate_duplicate_event_counts_invalid")
    _validate_candidate_statistical_invariants(row)
    cost_evidence = arbiter_input["cost_evidence"]
    if row["cost_basis_main"] != cost_evidence["basis"]:
        raise ValueError("candidate_cost_evidence_binding_invalid")
    tail_source = cost_evidence["tail_source"]
    if (
        tail_source["tail_bps"] is None
        and row["tail_cost_recomputable_count"] != 0
        or row["tail_cost_recomputable_count"] > 0
        and row["tail_metric"] != tail_source["tail_metric"]
    ):
        raise ValueError("candidate_cost_evidence_binding_invalid")
    if row["expected_cost_recomputable_count"] > 0 and (
        row["avg_expected_cost_bps"]
        < cost_evidence["fee_floor_bps"]
        + 2.0 * cost_evidence["mean_abs_source"]["mean_abs_bps"]
    ):
        raise ValueError("candidate_cost_evidence_binding_invalid")
    if row["tail_cost_recomputable_count"] > 0 and (
        row["avg_tail_cost_bps"]
        < cost_evidence["fee_floor_bps"]
        + 2.0 * cost_evidence["tail_source"]["tail_bps"]
    ):
        raise ValueError("candidate_cost_evidence_binding_invalid")
    expected_lineage_counts = {}
    for field, code in (
        (
            "invalid_lineage_exact_cohort_row_count",
            "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT",
        ),
        (
            "invalid_lineage_identity_family_row_count",
            "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT",
        ),
        (
            "duplicate_event_hash_outcome_conflict_row_count",
            "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT",
        ),
        (
            "duplicate_event_hash_cohort_conflict_row_count",
            "DUPLICATE_EVENT_HASH_COHORT_CONFLICT",
        ),
    ):
        if row[field]:
            expected_lineage_counts[code] = row[field]
    if not _exact_value_equal(
        row["lineage_blocker_reason_counts"], expected_lineage_counts
    ) or any(code not in row["blockers"] for code in expected_lineage_counts):
        raise ValueError("candidate_lineage_counts_invalid")
    base_blockers = _validate_candidate_blockers(
        row, evidence, expected_lineage_counts
    )
    incomplete_codes = {
        "IDENTITY_LINEAGE_INCOMPLETE",
        "ARBITER_INPUT_CONTEXT_INCOMPLETE",
        *expected_lineage_counts,
    }
    expected_input_complete = not any(
        code in row["blockers"] for code in incomplete_codes
    )
    if row.get("arbiter_input_complete") is not expected_input_complete:
        raise ValueError("candidate_input_completeness_invalid")
    nonactionable_codes = incomplete_codes | {
        "INVALID_OUTCOME_ROWS_PRESENT",
        "DATA_INTEGRITY_SUSPECT",
        "ENTRY_TS_LINEAGE_INCOMPLETE",
        "CENSORING_EXCESS",
    }
    expected_actionable = not any(
        code in row["blockers"] for code in nonactionable_codes
    )
    if row.get("qualified_metrics_actionable") is not expected_actionable or row.get(
        "metrics_scope"
    ) != (
        "QUALIFIED_SUBSET_ACTIONABLE"
        if expected_actionable
        else "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"
    ):
        raise ValueError("candidate_metrics_scope_invalid")
    expected_evidence_bindings = {
        "n_eff": row["n_eff"],
        "utc_day_count": row["distinct_entry_utc_days"],
        "mean_net_e": row["mean_net_e"],
        "day_cluster_variance": row["day_cluster_variance"],
        "cluster_se": row["cluster_se"],
        "cluster_count": row["cluster_count"],
        "raw_attempt_count": row["qualified_evaluator_input_count"],
        "regime_entry_counts": row["regime_entry_counts"],
    }
    if any(
        not _exact_value_equal(evidence.get(field), expected)
        for field, expected in expected_evidence_bindings.items()
    ):
        raise ValueError("candidate_evidence_binding_invalid")
    quality = arbiter_input["quality"]
    expected_quality_bindings = {
        "hash_ok": True,
        "freshness_ok": True,
        "integrity_ok": bool(
            not expected_lineage_counts
            and not row["data_integrity_suspect"]
            and row["qualified_entry_ts_missing_row_count"] == 0
            and row["qualified_invalid_outcome_row_count"] == 0
            and row["cluster_variance_clean"]
        ),
        "censored_share": row["censored_share"],
        "cost_recomputable_share": row["cost_recomputable_share"],
        "unknown_regime_share": (
            row["regime_entry_counts"]["unknown"] / row["n_eff"]
            if row["n_eff"]
            else 1.0
        ),
        "replica_inconsistency_count": row["replica_inconsistent_group_count"],
        "cluster_variance_clean": row["cluster_variance_clean"],
        "legacy_optimistic_cost_present": row[
            "legacy_optimistic_cost_present"
        ],
        "hidden_oos_consumed": row["hidden_oos_consumed"] is True,
        "top_day_share": (
            row["top_entry_day_share"]
            if row["top_entry_day_share"] is not None
            else 1.0
        ),
    }
    if any(
        not _exact_value_equal(quality.get(field), expected)
        for field, expected in expected_quality_bindings.items()
    ):
        raise ValueError("candidate_quality_binding_invalid")
    return recorded_evaluation_date, base_blockers


def _validate_arbiter_input_nested_fields(arbiter_input: Mapping[str, Any]) -> None:
    identity = arbiter_input.get("identity")
    context_hashes = arbiter_input.get("context_hashes")
    quality = arbiter_input.get("quality")
    evidence = arbiter_input.get("evidence")
    resource = arbiter_input.get("resource")
    portfolio = arbiter_input.get("portfolio")
    cost_evidence = arbiter_input.get("cost_evidence")
    if (
        not isinstance(identity, Mapping)
        or set(identity) != _ARBITER_IDENTITY_FIELDS
        or not isinstance(identity.get("target_regime"), Mapping)
        or set(identity["target_regime"]) != _TARGET_REGIME_FIELDS
        or not isinstance(context_hashes, Mapping)
        or set(context_hashes) != _CONTEXT_HASH_FIELDS
        or not isinstance(quality, Mapping)
        or set(quality) != _QUALITY_FIELDS
        or not isinstance(evidence, Mapping)
        or set(evidence) != _EVIDENCE_FIELDS
        or not isinstance(evidence.get("next_gap"), Mapping)
        or set(evidence["next_gap"]) != _NEXT_GAP_FIELDS
        or not isinstance(resource, Mapping)
        or set(resource) != _RESOURCE_FIELDS
        or not isinstance(portfolio, Mapping)
        or set(portfolio) != _PORTFOLIO_FIELDS
        or not isinstance(cost_evidence, Mapping)
        or set(cost_evidence) != _COST_EVIDENCE_FIELDS
    ):
        raise ValueError("arbiter_input_nested_fields_invalid")
    buckets = resource.get("daily_buckets")
    if (
        not isinstance(buckets, list)
        or any(
            not isinstance(bucket, Mapping)
            or set(bucket) != _RESOURCE_BUCKET_FIELDS
            for bucket in buckets
        )
    ):
        raise ValueError("arbiter_input_nested_fields_invalid")


def _validate_cost_evidence(
    value: Mapping[str, Any],
    *,
    identity: Mapping[str, Any],
    as_of_date: dt.date,
) -> None:
    if (
        value.get("schema_version") != COST_EVIDENCE_SCHEMA_VERSION
        or type(value.get("max_age_hours")) is not int
        or value["max_age_hours"] != QUANTILE_ARTIFACT_MAX_AGE_HOURS
        or type(value.get("fee_floor_bps")) is not float
        or value["fee_floor_bps"] != FEE_FLOOR_BPS
    ):
        raise ValueError("cost_evidence_semantics_invalid")
    mean_source = value.get("mean_abs_source")
    tail_source = value.get("tail_source")
    if (
        not isinstance(mean_source, Mapping)
        or set(mean_source) != _MEAN_ABS_SOURCE_FIELDS
        or not isinstance(tail_source, Mapping)
        or set(tail_source) != _TAIL_SOURCE_FIELDS
    ):
        raise ValueError("cost_evidence_fields_invalid")

    if value.get("basis") == "conservative_v1":
        if not _exact_value_equal(
            {
                "source_asof_utc": value.get("source_asof_utc"),
                "source_payload_sha256": value.get("source_payload_sha256"),
                "normalized_projection_sha256": value.get(
                    "normalized_projection_sha256"
                ),
                "mean_abs_source": mean_source,
                "tail_source": tail_source,
            },
            {
                "source_asof_utc": None,
                "source_payload_sha256": None,
                "normalized_projection_sha256": None,
                "mean_abs_source": {
                    "scope": "NONE",
                    "symbol": None,
                    "sample_count": 0,
                    "mean_abs_bps": None,
                },
                "tail_source": {
                    "scope": "NONE",
                    "symbol": None,
                    "sample_count": 0,
                    "tail_bps": None,
                    "tail_metric": None,
                },
            },
        ):
            raise ValueError("cost_evidence_semantics_invalid")
        return

    if value.get("basis") != "expected_slippage_mean_abs_v1":
        raise ValueError("cost_evidence_semantics_invalid")
    try:
        source_asof = dt.datetime.fromisoformat(value["source_asof_utc"])
    except (TypeError, ValueError):
        raise ValueError("cost_evidence_semantics_invalid") from None
    if (
        not _sha256_text(value.get("source_payload_sha256"))
        or not _sha256_text(value.get("normalized_projection_sha256"))
        or source_asof.tzinfo is None
        or source_asof.utcoffset() != dt.timedelta(0)
        or value["source_asof_utc"] != source_asof.isoformat()
        or not as_of_date - dt.timedelta(days=2) <= source_asof.date() <= as_of_date
    ):
        raise ValueError("cost_evidence_semantics_invalid")
    for source, value_field, metric_field in (
        (mean_source, "mean_abs_bps", None),
        (tail_source, "tail_bps", "tail_metric"),
    ):
        scope = source.get("scope")
        symbol = source.get("symbol")
        count = source.get("sample_count")
        statistic = source.get(value_field)
        if (
            scope not in {"GLOBAL", "SYMBOL"}
            or type(count) is not int
            or count <= 0
            or (scope == "GLOBAL" and symbol is not None)
            or (
                scope == "SYMBOL"
                and (
                    symbol != identity.get("symbol")
                    or count < MIN_SYMBOL_FILLS_FOR_QUANTILE
                )
            )
            or statistic is not None
            and (
                type(statistic) is not float
                or not math.isfinite(statistic)
                or statistic < 0.0
            )
        ):
            raise ValueError("cost_evidence_semantics_invalid")
        if metric_field is None and statistic is None:
            raise ValueError("cost_evidence_semantics_invalid")
    tail_metric = tail_source.get("tail_metric")
    if (tail_source["tail_bps"] is None) is not (tail_metric is None) or (
        tail_metric is not None
        and tail_metric not in {"cvar90", "q90_fallback"}
    ):
        raise ValueError("cost_evidence_semantics_invalid")
    if (
        mean_source["scope"] == tail_source["scope"]
        and mean_source["symbol"] == tail_source["symbol"]
        and mean_source["sample_count"] != tail_source["sample_count"]
    ):
        raise ValueError("cost_evidence_semantics_invalid")


def _validate_candidate_blockers(
    row: Mapping[str, Any],
    evidence: Mapping[str, Any],
    lineage_counts: Mapping[str, int],
) -> set[str]:
    expected = set(lineage_counts)
    conditions = {
        "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT": (
            row["n_eff"] < _SELECTION_N_EFF_MIN
        ),
        "UTC_DAY_COVERAGE_INSUFFICIENT": (
            row["distinct_entry_utc_days"] < _SELECTION_UTC_DAYS_MIN
        ),
        "TOP_DAY_CONCENTRATION_EXCESS": (
            row["top_entry_day_share_pct"]
            if row["top_entry_day_share_pct"] is not None
            else 100.0
        )
        > _SELECTION_TOP_DAY_SHARE_MAX_PCT,
        "ENTRY_TS_LINEAGE_INCOMPLETE": (
            row["qualified_entry_ts_missing_row_count"] > 0
        ),
        "INVALID_OUTCOME_ROWS_PRESENT": (
            row["qualified_invalid_outcome_row_count"] > 0
        ),
        "DATA_INTEGRITY_SUSPECT": row["data_integrity_suspect"],
        "DAY_CLUSTER_VARIANCE_DEGENERATE": not row["cluster_variance_clean"],
        "CENSORING_EXCESS": row["censored_share"] > 0.30,
        "LEGACY_OPTIMISTIC_COST_UNBACKFILLED": row[
            "legacy_optimistic_cost_present"
        ],
        "EXPECTED_COST_NOT_FULLY_RECOMPUTABLE": (
            row["expected_cost_recomputable_share"] < 1.0
        ),
        "TAIL_COST_NOT_FULLY_RECOMPUTABLE": (
            row["tail_cost_recomputable_share"] < 1.0
        ),
        "PROOF_GAP_OPEN": evidence["next_gap"]["kind"] != "NONE",
        "HIDDEN_OOS_CONSUMED": row["hidden_oos_consumed"],
    }
    expected.update(code for code, active in conditions.items() if active)
    actual = set(row["blockers"]) - {_SIDE_CELL_AMBIGUITY_BLOCKER}
    if actual != expected:
        raise ValueError("candidate_blockers_invalid")
    return expected


def _validate_candidate_statistical_invariants(row: Mapping[str, Any]) -> None:
    entry_day_counts = row.get("entry_day_counts")
    regime_counts = row.get("regime_entry_counts")
    coverage = row.get("regime_coverage_inputs")
    variance = row.get("day_cluster_variance")
    cluster_se = row.get("cluster_se")
    n_eff = row["n_eff"]
    if row.get("data_integrity_suspect") is not (
        row["replica_inconsistent_group_count"] > 0
        or row.get("zero_variance_suspect") is True
    ):
        raise ValueError("candidate_statistical_invariant_violation")
    if row.get("cost_basis_main") not in {
        "conservative_v1",
        "expected_slippage_mean_abs_v1",
    }:
        raise ValueError("candidate_statistical_invariant_violation")
    if (
        not _nullable_finite_float(row.get("avg_net_bps"))
        or not _nullable_finite_float(row.get("mean_net_e"))
        or not _exact_value_equal(row.get("avg_net_bps"), row.get("mean_net_e"))
        or (n_eff == 0) is not (row.get("mean_net_e") is None)
    ):
        raise ValueError("candidate_statistical_invariant_violation")
    cost_basis = row["cost_basis_main"]
    if cost_basis == "conservative_v1":
        cost_contract_valid = bool(
            row["expected_cost_recomputable_count"] == 0
            and _same_float(row.get("expected_cost_recomputable_share"), 0.0)
            and _same_float(row.get("cost_recomputable_share"), 0.0)
            and row.get("avg_expected_cost_bps") is None
            and row["tail_cost_recomputable_count"] == 0
            and _same_float(row.get("tail_cost_recomputable_share"), 0.0)
            and row.get("avg_tail_cost_bps") is None
            and row.get("tail_metric") is None
        )
    else:
        expected_count = row["expected_cost_recomputable_count"]
        tail_count = row["tail_cost_recomputable_count"]
        cost_contract_valid = bool(
            0 <= tail_count <= expected_count <= n_eff
            and (
                expected_count == 0
                and row.get("avg_expected_cost_bps") is None
                or expected_count > 0
                and _fee_floor_float(row.get("avg_expected_cost_bps"))
            )
            and (
                tail_count == 0
                and row.get("avg_tail_cost_bps") is None
                and row.get("tail_metric") is None
                or tail_count > 0
                and _fee_floor_float(row.get("avg_tail_cost_bps"))
                and row.get("tail_metric")
                in {"cvar90", "q90_fallback", "mixed"}
            )
        )
    if not cost_contract_valid:
        raise ValueError("candidate_statistical_invariant_violation")
    if row.get("cluster_variance_clean") is True:
        if (
            type(variance) is not float
            or not math.isfinite(variance)
            or variance <= 0.0
            or type(cluster_se) is not float
            or not math.isfinite(cluster_se)
            or cluster_se <= 0.0
            or cluster_se != math.sqrt(variance)
        ):
            raise ValueError("candidate_cluster_algebra_invalid")
    elif cluster_se is not None or not (
        variance is None or type(variance) is float and variance == 0.0
    ):
        raise ValueError("candidate_cluster_algebra_invalid")
    if (
        not isinstance(entry_day_counts, Mapping)
        or any(
            not isinstance(day, str)
            or not _canonical_utc_date(day)
            or not _positive_int_value(count)
            for day, count in entry_day_counts.items()
        )
        or not isinstance(regime_counts, Mapping)
        or set(regime_counts) != {*_REGIME_BUCKETS, "unknown"}
        or any(not _nonnegative_int_value(count) for count in regime_counts.values())
        or not isinstance(coverage, Mapping)
        or set(coverage)
        != {
            "composite_bucket_universe_size",
            "observed_composite_bucket_count",
            "effective_entry_count",
            "unknown_regime_entry_count",
            "unknown_regime_share",
        }
    ):
        raise ValueError("candidate_statistical_invariant_violation")

    if (
        row["qualified_valid_uncensored_outcome_count"]
        != row["qualified_entry_ts_missing_row_count"]
        + row["qualified_distinct_entry_observation_count"]
        + row["qualified_duplicate_outcome_row_count"]
        or row["qualified_distinct_entry_observation_count"]
        != n_eff + row["qualified_window_overlap_excluded_entry_count"]
        or sum(entry_day_counts.values()) != n_eff
        or sum(regime_counts.values()) != n_eff
        or row["distinct_entry_utc_days"] != len(entry_day_counts)
        or row["cluster_count"] != len(entry_day_counts)
        or row["expected_cost_recomputable_count"] > n_eff
        or row["tail_cost_recomputable_count"] > n_eff
    ):
        raise ValueError("candidate_statistical_invariant_violation")

    expected_censored_share = (
        row["qualified_censored_outcome_count"]
        / row["qualified_evaluator_input_count"]
        if row["qualified_evaluator_input_count"]
        else 0.0
    )
    expected_cost_share = (
        row["expected_cost_recomputable_count"] / n_eff if n_eff else 0.0
    )
    expected_tail_share = (
        row["tail_cost_recomputable_count"] / n_eff if n_eff else 0.0
    )
    expected_unknown_share = regime_counts["unknown"] / n_eff if n_eff else 1.0
    if (
        not _same_float(row.get("censored_share"), expected_censored_share)
        or not _same_float(row.get("censored_pct"), expected_censored_share * 100.0)
        or not _same_float(
            row.get("expected_cost_recomputable_share"), expected_cost_share
        )
        or not _same_float(row.get("cost_recomputable_share"), expected_cost_share)
        or not _same_float(row.get("tail_cost_recomputable_share"), expected_tail_share)
    ):
        raise ValueError("candidate_statistical_invariant_violation")

    if n_eff:
        top_day, top_count = sorted(
            entry_day_counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        expected_top_share_pct = top_count / n_eff * 100.0
        expected_top_share = expected_top_share_pct / 100.0
        if (
            row.get("top_entry_utc_day") != top_day
            or not _same_float(row.get("top_entry_day_share"), expected_top_share)
            or not _same_float(
                row.get("top_entry_day_share_pct"), expected_top_share_pct
            )
        ):
            raise ValueError("candidate_statistical_invariant_violation")
    elif any(
        row.get(field) is not None
        for field in (
            "top_entry_utc_day",
            "top_entry_day_share",
            "top_entry_day_share_pct",
        )
    ):
        raise ValueError("candidate_statistical_invariant_violation")

    expected_coverage = {
        "composite_bucket_universe_size": len(_REGIME_BUCKETS),
        "observed_composite_bucket_count": sum(
            regime_counts[label] > 0 for label in _REGIME_BUCKETS
        ),
        "effective_entry_count": n_eff,
        "unknown_regime_entry_count": regime_counts["unknown"],
        "unknown_regime_share": expected_unknown_share,
    }
    if not _exact_value_equal(coverage, expected_coverage):
        raise ValueError("candidate_statistical_invariant_violation")


def _validate_arbiter_identity_semantics(
    identity: Mapping[str, Any],
    *,
    as_of_date: dt.date,
) -> None:
    target = identity["target_regime"]
    horizon = identity.get("horizon_minutes")
    symbol = identity.get("symbol")
    try:
        regime_date = dt.date.fromisoformat(str(target.get("utc_date")))
    except ValueError:
        raise ValueError("candidate_identity_semantics_invalid") from None
    target_body = {
        key: copy.deepcopy(value)
        for key, value in target.items()
        if key != "hash"
    }
    if (
        not _exact_text(identity.get("strategy_name"))
        or not _git_sha_text(identity.get("strategy_version"))
        or not _sha256_text(identity.get("config_hash"))
        or not _exact_text(symbol)
        or symbol != symbol.upper()
        or identity.get("side") not in {"Buy", "Sell"}
        or isinstance(horizon, bool)
        or not isinstance(horizon, int)
        or not 1 <= horizon <= 1_440
        or identity.get("engine_mode") != "shadow"
        or identity.get("evidence_engine_mode") not in {"demo", "live_demo"}
        or (identity.get("venue"), identity.get("product"))
        != ("bybit", "linear_perpetual")
        or target.get("label") not in _REGIME_BUCKETS
        or target.get("utc_date") != regime_date.isoformat()
        or regime_date != as_of_date - dt.timedelta(days=1)
        or target.get("point_in_time") != "D-1"
        or target.get("source_complete") is not True
        or not _sha256_text(target.get("source_hash"))
        or not _sha256_text(target.get("classifier_hash"))
        or target.get("hash") != _canonical_sha256(target_body)
    ):
        raise ValueError("candidate_identity_semantics_invalid")


def _validate_arbiter_input_semantics(arbiter_input: Mapping[str, Any]) -> None:
    context_hashes = arbiter_input["context_hashes"]
    quality = arbiter_input["quality"]
    evidence = arbiter_input["evidence"]
    resource = arbiter_input["resource"]
    portfolio = arbiter_input["portfolio"]
    if not all(_sha256_text(context_hashes[field]) for field in _CONTEXT_HASH_FIELDS):
        raise ValueError("arbiter_input_semantics_invalid")

    bool_quality_fields = {
        "hash_ok",
        "integrity_ok",
        "freshness_ok",
        "cluster_variance_clean",
        "legacy_optimistic_cost_present",
        "hidden_oos_consumed",
    }
    share_quality_fields = {
        "censored_share",
        "cost_recomputable_share",
        "unknown_regime_share",
        "top_day_share",
    }
    if (
        any(not isinstance(quality[field], bool) for field in bool_quality_fields)
        or any(
            not _bounded_float(quality[field]) for field in share_quality_fields
        )
        or not _nonnegative_int_value(quality["replica_inconsistency_count"])
    ):
        raise ValueError("arbiter_input_semantics_invalid")

    integer_evidence_fields = {
        "n_eff",
        "utc_day_count",
        "cluster_count",
        "proof_stage",
        "raw_attempt_count",
    }
    nullable_float_fields = {"mean_net_e", "day_cluster_variance", "cluster_se"}
    if (
        any(
            not _nonnegative_int_value(evidence[field])
            for field in integer_evidence_fields
        )
        or evidence["proof_stage"] > 6
        or evidence["completed_proof_stages"]
        != list(range(evidence["proof_stage"] + 1))
        or any(
            not _nullable_finite_float(evidence[field])
            for field in nullable_float_fields
        )
        or (
            evidence["day_cluster_variance"] is not None
            and evidence["day_cluster_variance"] < 0
        )
        or (evidence["cluster_se"] is not None and evidence["cluster_se"] < 0)
        or evidence["next_gap"].get("kind")
        not in {"NONE", "LOCAL_PASSIVE", "LOCAL_ENGINEERING", "EXTERNAL_OPERATOR"}
        or not _exact_text(evidence["next_gap"].get("code"))
    ):
        raise ValueError("arbiter_input_semantics_invalid")
    regime_counts = evidence["regime_entry_counts"]
    if (
        not isinstance(regime_counts, Mapping)
        or set(regime_counts) != {*_REGIME_BUCKETS, "unknown"}
        or any(not _nonnegative_int_value(value) for value in regime_counts.values())
        or sum(regime_counts.values()) != evidence["n_eff"]
    ):
        raise ValueError("arbiter_input_semantics_invalid")

    buckets = resource["daily_buckets"]
    target = arbiter_input["identity"]["target_regime"]
    target_date = dt.date.fromisoformat(target["utc_date"])
    expected_dates = [
        (target_date - dt.timedelta(days=offset)).isoformat()
        for offset in range(6, -1, -1)
    ]
    if (
        len(buckets) != 7
        or [bucket.get("utc_date") for bucket in buckets] != expected_dates
        or any(
            bucket.get("scan_complete") is not True
            or not _nonnegative_int_value(bucket.get("distinct_entries"))
            for bucket in buckets
        )
        or not _nonnegative_int_value(resource.get("estimated_rows_scanned"))
        or not _nonnegative_int_value(resource.get("predicted_canonical_bytes"))
        or not isinstance(resource.get("zero_resource_attested"), bool)
    ):
        raise ValueError("arbiter_input_semantics_invalid")
    rows = resource["estimated_rows_scanned"]
    byte_count = resource["predicted_canonical_bytes"]
    zero_attested = resource["zero_resource_attested"]
    if (
        (rows == 0) != (byte_count == 0)
        or (rows == 0 and (not zero_attested or any(bucket["distinct_entries"] for bucket in buckets)))
        or (rows > 0 and zero_attested)
    ):
        raise ValueError("arbiter_input_semantics_invalid")
    resource_body = {
        "daily_buckets": [dict(bucket) for bucket in buckets],
        "estimated_rows_scanned": rows,
        "predicted_canonical_bytes": byte_count,
        "zero_resource_attested": zero_attested,
    }
    if resource.get("resource_estimator_hash") != _canonical_sha256(resource_body):
        raise ValueError("arbiter_input_semantics_invalid")

    if any(not _canonical_decimal_text(portfolio[field]) for field in _PORTFOLIO_FIELDS):
        raise ValueError("arbiter_input_semantics_invalid")
    for field in ("sector_exposure_share", "strategy_active_target_share"):
        if not Decimal(0) <= Decimal(portfolio[field]) <= Decimal(1):
            raise ValueError("arbiter_input_semantics_invalid")


def _nonnegative_int_value(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _positive_int_value(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _canonical_utc_date(value: str) -> bool:
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError:
        return False
    return value == parsed.isoformat()


def _same_float(value: Any, expected: float) -> bool:
    return type(value) is float and math.isfinite(value) and value == expected


def _nullable_finite_float(value: Any) -> bool:
    return value is None or (
        isinstance(value, float) and not isinstance(value, bool) and math.isfinite(value)
    )


def _nonnegative_finite_float(value: Any) -> bool:
    return bool(
        isinstance(value, float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and value >= 0.0
    )


def _fee_floor_float(value: Any) -> bool:
    return bool(
        _nonnegative_finite_float(value)
        and value >= FEE_FLOOR_BPS
    )


def _bounded_float(value: Any) -> bool:
    return bool(
        isinstance(value, float)
        and not isinstance(value, bool)
        and math.isfinite(value)
        and 0.0 <= value <= 1.0
    )


def _canonical_decimal_text(value: Any) -> bool:
    if not isinstance(value, str) or not value:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    if not parsed.is_finite():
        return False
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if canonical in {"", "-0"}:
        canonical = "0"
    return value == canonical

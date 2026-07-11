"""Bounded immutable ingress for candidate-aware R3 evidence boards.

This adapter deliberately turns source defects into structured, hash-bound
abstentions.  It never falls back to ``top_side_cells`` or a mutable latest
alias and performs no database, exchange, or runtime action.
"""

from __future__ import annotations

import copy
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
import re
import stat
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ml_training.alr_safe_file import (
    AlrSafeFileError,
    CHANGED,
    NOT_REGULAR,
    SECURE_OPEN_UNAVAILABLE,
    SIZE_INVALID,
    read_bounded_regular_file,
)


OUTPUT_SCHEMA_VERSION = "alr_candidate_evidence_snapshot_v2"
SOURCE_SCHEMA_VERSION = "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
BOARD_SCHEMA_VERSION = "cost_gate_learning_candidate_board_v2"
_CANDIDATE_SCHEMA_VERSION = "cost_gate_learning_candidate_v2"
_ARBITER_INPUT_SCHEMA_VERSION = "alr_candidate_arbiter_input_v2"
_COST_EVIDENCE_SCHEMA_VERSION = "alr_candidate_cost_evidence_v2"
_CANDIDATE_FAMILY_SCHEMA_VERSION = "candidate_learning_family_v2"
_SELECTION_SCHEMA_VERSION = "cost_gate_learning_candidate_selection_v2"
_AUDIT_SCHEMA_VERSION = "cost_gate_learning_candidate_audit_v2"
# Frozen mirror of the no-discount round-trip taker-fee floor.  This ingress
# stays standalone from the research producer package by design.
FEE_FLOOR_BPS = 11.0
MIN_SYMBOL_FILLS_FOR_QUANTILE = 20
QUANTILE_ARTIFACT_MAX_AGE_HOURS = 48
_SLIPPAGE_MEAN_ABS_TOL_BPS = 1e-9
_SLIPPAGE_MEAN_REL_TOL = 1e-12
_SLIPPAGE_ARTIFACT_SCHEMA_VERSION = "cost_gate_slippage_quantile_artifact_v2"
_SLIPPAGE_PROJECTION_SCHEMA_VERSION = "cost_gate_expected_cost_projection_v2"
_SLIPPAGE_ARTIFACT_FIELDS = {
    "schema_version", "asof", "window_days", "n_total_global", "symbols",
    "global", "boundary",
}
_SLIPPAGE_STAT_FIELDS = {
    "n", "mean_abs", "mean_signed", "q50", "q75", "q90", "cvar90",
    "thin_sample",
}
_SLIPPAGE_SYMBOL_FIELDS = {*_SLIPPAGE_STAT_FIELDS, "symbol"}
_SLIPPAGE_BOUNDARY = (
    "slippage quantile artifact only; PG source is read-only SELECT-only; "
    "no PG write, Bybit call, order, config, risk, auth, or runtime mutation"
)
_COST_EVIDENCE_FIELDS = {
    "schema_version", "basis", "source_payload_sha256", "source_asof_utc",
    "normalized_projection_sha256", "max_age_hours", "fee_floor_bps",
    "mean_abs_source", "tail_source",
}
_MEAN_ABS_SOURCE_FIELDS = {"scope", "symbol", "sample_count", "mean_abs_bps"}
_TAIL_SOURCE_FIELDS = {"scope", "symbol", "sample_count", "tail_bps", "tail_metric"}
_UNQUALIFIED_EXCLUSION_REASONS = frozenset(
    {
        "UNQUALIFIED_CONTEXT_MISSING",
        "UNQUALIFIED_LEGACY_PROJECTION_ONLY",
        "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING",
        "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW",
    }
)
_INVALID_EXCLUSION_REASONS = frozenset(
    {
        "INVALID_LINEAGE_RAW_CONTEXT_INVALID",
        "INVALID_LINEAGE_IDENTITY_FAMILY",
        "INVALID_LINEAGE_EXACT_COHORT",
    }
)
_LINEAGE_EXCLUSION_REASONS = (
    _UNQUALIFIED_EXCLUSION_REASONS | _INVALID_EXCLUSION_REASONS
)
_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)
_ARBITER_IDENTITY_FIELDS = {
    "strategy_name", "strategy_version", "config_hash", "symbol", "side",
    "horizon_minutes", "target_regime", "engine_mode", "evidence_engine_mode",
    "venue", "product",
}
_TARGET_REGIME_FIELDS = {
    "label", "utc_date", "hash", "point_in_time", "source_complete",
    "source_hash", "classifier_hash",
}
_QUALITY_FIELDS = {
    "hash_ok", "integrity_ok", "freshness_ok", "censored_share",
    "cost_recomputable_share", "unknown_regime_share",
    "replica_inconsistency_count", "cluster_variance_clean",
    "hidden_oos_consumed", "legacy_optimistic_cost_present", "top_day_share",
}
_EVIDENCE_FIELDS = {
    "n_eff", "utc_day_count", "mean_net_e", "day_cluster_variance",
    "cluster_se", "cluster_count", "proof_stage", "completed_proof_stages",
    "next_gap", "raw_attempt_count", "regime_entry_counts",
}
_RESOURCE_FIELDS = {
    "daily_buckets", "estimated_rows_scanned", "predicted_canonical_bytes",
    "zero_resource_attested", "resource_estimator_hash",
}
_PORTFOLIO_FIELDS = {
    "sector_exposure_share", "strategy_active_target_share", "beta_to_portfolio",
}
_ARBITER_INPUT_FIELDS = {
    "schema_version",
    "identity",
    "context_hashes",
    "cost_evidence",
    "quality",
    "evidence",
    "resource",
    "portfolio",
    "arbiter_input_hash",
}
_LINEAGE_BLOCKER_COUNT_FIELDS = (
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
)
_CANDIDATE_COUNT_FIELDS = frozenset(
    {
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
)

_SELECTION_FIELDS = (
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
_TOP_AUDIT_FIELDS = (
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
_CANDIDATE_ROW_FIELDS = frozenset(
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

_IMMUTABLE_NAME_RE = re.compile(
    r"^blocked_outcome_review_(?P<stamp>[0-9]{8}T[0-9]{6}Z)\.json$"
)
_IMMUTABLE_STAMP_FORMAT = "%Y%m%dT%H%M%SZ"
_SOURCE_PREFIX = "blocked_outcome_review_"
_LATEST_NAME = "blocked_outcome_review_latest.json"


def load_candidate_evidence_snapshot(
    explicit_directory: str | Path,
    *,
    evaluated_at: str,
    max_age_seconds: int,
    max_files: int,
    max_bytes: int,
) -> dict[str, Any]:
    """Load the newest complete immutable board within explicit bounds.

    Missing, stale, malformed, raced, or incomplete evidence is a normal
    fail-closed result.  Invalid caller policy is a programming error and is
    rejected before any filesystem access.
    """
    evaluated = _parse_utc(evaluated_at, "evaluated_at_invalid")
    _positive_int(max_age_seconds, "max_age_seconds_invalid")
    _positive_int(max_files, "max_files_invalid")
    _positive_int(max_bytes, "max_bytes_invalid")
    canonical_evaluated_at = _utc_z(evaluated)
    root = Path(explicit_directory).expanduser()

    try:
        root_metadata = root.lstat()
    except FileNotFoundError:
        return _failure("DIRECTORY_MISSING", canonical_evaluated_at)
    except OSError:
        return _failure("DIRECTORY_IO_ERROR", canonical_evaluated_at)
    if stat.S_ISLNK(root_metadata.st_mode):
        return _failure("PATH_SYMLINK", canonical_evaluated_at)
    if not stat.S_ISDIR(root_metadata.st_mode):
        return _failure("PATH_NOT_DIRECTORY", canonical_evaluated_at)

    immutable: list[tuple[datetime, Path, os.stat_result]] = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return _failure("DIRECTORY_IO_ERROR", canonical_evaluated_at)
    for entry in entries:
        name = entry.name
        if name == _LATEST_NAME:
            return _failure("LATEST_ALIAS_PRESENT", canonical_evaluated_at)
        match = _IMMUTABLE_NAME_RE.fullmatch(name)
        if name.startswith(_SOURCE_PREFIX) and match is None:
            return _failure("UNSAFE_FILE_PRESENT", canonical_evaluated_at)
        if match is None:
            continue
        try:
            stamp = datetime.strptime(
                match.group("stamp"),
                _IMMUTABLE_STAMP_FORMAT,
            ).replace(tzinfo=timezone.utc)
        except ValueError:
            return _failure("UNSAFE_FILE_PRESENT", canonical_evaluated_at)
        try:
            metadata = entry.lstat()
        except OSError:
            return _failure("SOURCE_IO_ERROR", canonical_evaluated_at)
        if stat.S_ISLNK(metadata.st_mode):
            return _failure("SOURCE_SYMLINK", canonical_evaluated_at)
        if not stat.S_ISREG(metadata.st_mode):
            return _failure("SOURCE_NOT_REGULAR", canonical_evaluated_at)
        immutable.append((stamp, entry, metadata))

    if not immutable:
        return _failure("NO_IMMUTABLE_SNAPSHOT", canonical_evaluated_at)
    total_bytes = sum(item[2].st_size for item in immutable)
    if len(immutable) > max_files or total_bytes > max_bytes:
        return _failure(
            "UNIVERSE_TRUNCATED",
            canonical_evaluated_at,
            source_file_count=len(immutable),
            source_total_bytes=total_bytes,
        )

    immutable.sort(key=lambda item: item[0])
    selected_stamp, selected_path, selected_metadata = immutable[-1]
    if selected_stamp > evaluated:
        return _failure("SOURCE_FROM_FUTURE", canonical_evaluated_at)
    try:
        raw = read_bounded_regular_file(
            selected_path,
            max_bytes=max_bytes,
            require_nonempty=False,
            require_private_mode=False,
            expected_stat=selected_metadata,
        )
    except AlrSafeFileError as exc:
        status = {
            CHANGED: "SOURCE_CHANGED_DURING_READ",
            NOT_REGULAR: "SOURCE_NOT_REGULAR",
            SIZE_INVALID: "UNIVERSE_TRUNCATED",
            SECURE_OPEN_UNAVAILABLE: "SOURCE_SECURE_OPEN_UNAVAILABLE",
        }.get(exc.code, "SOURCE_IO_ERROR")
        return _failure(status, canonical_evaluated_at)

    content_hash = hashlib.sha256(raw).hexdigest()
    def reject_non_finite(value: str) -> None:
        raise ValueError(f"non_finite_json_constant:{value}")

    try:
        payload = json.loads(raw, parse_constant=reject_non_finite)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return _failure(
            "SOURCE_JSON_INVALID",
            canonical_evaluated_at,
            source_content_sha256=content_hash,
        )
    if not isinstance(payload, Mapping):
        return _failure("SOURCE_NOT_MAPPING", canonical_evaluated_at)
    if payload.get("schema_version") != SOURCE_SCHEMA_VERSION:
        return _failure("SOURCE_SCHEMA_INVALID", canonical_evaluated_at)

    generated_raw = payload.get("generated_at_utc")
    try:
        generated = _parse_utc(generated_raw, "SOURCE_GENERATED_AT_INVALID")
    except ValueError:
        return _failure("SOURCE_GENERATED_AT_INVALID", canonical_evaluated_at)
    if selected_stamp > generated:
        return _failure(
            "SOURCE_FILENAME_STAMP_AFTER_GENERATED_AT",
            canonical_evaluated_at,
        )
    age_seconds = (evaluated - generated).total_seconds()
    if age_seconds < 0:
        return _failure("SOURCE_FROM_FUTURE", canonical_evaluated_at)
    if age_seconds > max_age_seconds:
        return _failure("SOURCE_STALE", canonical_evaluated_at)

    board = payload.get("learning_candidate_board")
    if not isinstance(board, Mapping):
        return _failure("LEARNING_BOARD_MISSING", canonical_evaluated_at)
    if board.get("schema_version") != BOARD_SCHEMA_VERSION:
        return _failure("LEARNING_BOARD_SCHEMA_INVALID", canonical_evaluated_at)
    if board.get("candidate_universe_complete") is not True:
        return _failure("CANDIDATE_UNIVERSE_INCOMPLETE", canonical_evaluated_at)
    declared_board_hash = board.get("board_hash")
    if not _is_sha256(declared_board_hash):
        return _failure("BOARD_HASH_INVALID", canonical_evaluated_at)
    board_without_hash = {
        str(key): copy.deepcopy(value)
        for key, value in board.items()
        if key != "board_hash"
    }
    if declared_board_hash != _canonical_sha256(board_without_hash):
        return _failure("BOARD_HASH_MISMATCH", canonical_evaluated_at)
    expected_board_fields = {
        "schema_version",
        "as_of_utc_date",
        "candidate_universe_complete",
        *_TOP_AUDIT_FIELDS,
        "candidate_rows",
        "selection_hash",
        "audit_hash",
        "board_hash",
    }
    if set(board) != expected_board_fields:
        return _failure("LEARNING_BOARD_FIELDS_INVALID", canonical_evaluated_at)
    board_as_of = board.get("as_of_utc_date")
    if (
        not isinstance(board_as_of, str)
        or not _canonical_utc_date(board_as_of)
        or board_as_of != generated.date().isoformat()
    ):
        return _failure("BOARD_AS_OF_DATE_INVALID", canonical_evaluated_at)
    if not _board_count_invariants_hold(board):
        return _failure("BOARD_COUNT_INVARIANT_VIOLATION", canonical_evaluated_at)
    if not _board_reason_counts_hold(board):
        return _failure("BOARD_REASON_COUNTS_INVALID", canonical_evaluated_at)
    cost_status, cost_projection = _validate_outer_cost_contract(
        payload,
        generated=generated,
        evaluated=evaluated,
    )
    if cost_status is not None:
        return _failure(cost_status, canonical_evaluated_at)
    candidate_rows_raw = board.get("candidate_rows")
    if not isinstance(candidate_rows_raw, list) or not all(
        isinstance(row, Mapping) for row in candidate_rows_raw
    ):
        return _failure("CANDIDATE_ROWS_INVALID", canonical_evaluated_at)
    candidate_rows: list[dict[str, Any]] = []
    semantic_rows: list[dict[str, Any]] = []
    candidate_ids: set[str] = set()
    for raw_row in candidate_rows_raw:
        row = copy.deepcopy(dict(raw_row))
        status, semantic_row = _validate_candidate_row_contract(
            row,
            require_full_board_contract=True,
            as_of_date=generated.date(),
        )
        if status is not None or semantic_row is None:
            return _failure(status or "CANDIDATE_ROW_INVALID", canonical_evaluated_at)
        identity = row["arbiter_input"]["identity"]
        expected_cost_evidence = _candidate_cost_evidence_from_projection(
            cost_projection,
            symbol=identity["symbol"],
        )
        if (
            row.get("cost_basis_main") != payload.get("cost_basis_main")
            or not _exact_value_equal(
                row["arbiter_input"]["cost_evidence"],
                expected_cost_evidence,
            )
        ):
            return _failure(
                "CANDIDATE_COST_EVIDENCE_OUTER_MISMATCH",
                canonical_evaluated_at,
            )
        candidate_id = semantic_row["candidate_id"]
        if candidate_id in candidate_ids:
            return _failure("CANDIDATE_ID_DUPLICATE", canonical_evaluated_at)
        candidate_ids.add(candidate_id)
        candidate_rows.append(row)
        semantic_rows.append(semantic_row)
    if (
        sum(row["qualified_raw_outcome_count"] for row in candidate_rows)
        != board["qualified_lineage_outcome_row_count"]
        or sum(
            row["invalid_lineage_exact_cohort_row_count"]
            for row in candidate_rows
        )
        > board["invalid_exact_cohort_row_count"]
        or max(
            (
                row["invalid_lineage_identity_family_row_count"]
                for row in candidate_rows
            ),
            default=0,
        )
        > board["invalid_identity_family_row_count"]
    ):
        return _failure("BOARD_CANDIDATE_TOTALS_INVALID", canonical_evaluated_at)
    consistent_duplicate_total = sum(
        row["consistent_duplicate_event_hash_extra_row_count"]
        for row in candidate_rows
    )
    conflict_attribution_total = sum(
        row["conflicting_event_hash_row_count"] for row in candidate_rows
    )
    max_candidate_conflict_attribution = max(
        (row["conflicting_event_hash_row_count"] for row in candidate_rows),
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
        return _failure("BOARD_DUPLICATE_TOTALS_INVALID", canonical_evaluated_at)
    if not _exact_value_equal(
        candidate_rows,
        sorted(candidate_rows, key=_candidate_board_row_sort_key),
    ):
        return _failure("CANDIDATE_ROWS_ORDER_INVALID", canonical_evaluated_at)
    paired_rows = sorted(
        zip(semantic_rows, candidate_rows),
        key=lambda item: _candidate_sort_key(item[0]),
    )
    semantic_rows = [item[0] for item in paired_rows]
    candidate_rows = [item[1] for item in paired_rows]

    declared_selection_hash = board.get("selection_hash")
    if not _is_sha256(declared_selection_hash):
        return _failure("SELECTION_HASH_INVALID", canonical_evaluated_at)
    expected_selection_hash = _canonical_sha256(
        {
            "schema_version": _SELECTION_SCHEMA_VERSION,
            "candidate_rows": semantic_rows,
        }
    )
    if declared_selection_hash != expected_selection_hash:
        return _failure("SELECTION_HASH_MISMATCH", canonical_evaluated_at)

    declared_audit_hash = board.get("audit_hash")
    if not _is_sha256(declared_audit_hash):
        return _failure("AUDIT_HASH_INVALID", canonical_evaluated_at)
    try:
        candidate_audit_rows = sorted(
            (
                {
                    "candidate_id": row["candidate_id"],
                    **{
                        key: value
                        for key, value in row.items()
                        if key not in _SELECTION_FIELDS and key != "candidate_id"
                    },
                }
                for row in candidate_rows
            ),
            key=lambda row: row["candidate_id"],
        )
        expected_audit_hash = _canonical_sha256(
            {
                "schema_version": _AUDIT_SCHEMA_VERSION,
                **{field: copy.deepcopy(board[field]) for field in _TOP_AUDIT_FIELDS},
                "candidate_audit_rows": candidate_audit_rows,
            }
        )
    except (KeyError, TypeError, ValueError):
        return _failure("AUDIT_PAYLOAD_INVALID", canonical_evaluated_at)
    if declared_audit_hash != expected_audit_hash:
        return _failure("AUDIT_HASH_MISMATCH", canonical_evaluated_at)

    candidate_set_hash = _canonical_sha256(semantic_rows)

    result: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "source_status": "READY",
        "evaluated_at": canonical_evaluated_at,
        "generated_at": _utc_z(generated),
        "source_file": os.path.abspath(selected_path),
        "source_file_count": len(immutable),
        "source_total_bytes": total_bytes,
        "source_content_sha256": content_hash,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "board_schema_version": BOARD_SCHEMA_VERSION,
        "board_hash": declared_board_hash,
        "selection_hash": declared_selection_hash,
        "audit_hash": declared_audit_hash,
        "candidate_set_hash": candidate_set_hash,
        "candidate_universe_complete": True,
        "cost_basis_main": payload["cost_basis_main"],
        "cost_source_payload_sha256": (
            cost_projection["source_payload_sha256"]
            if cost_projection is not None
            else None
        ),
        "cost_normalized_projection_sha256": (
            cost_projection["normalized_projection_sha256"]
            if cost_projection is not None
            else None
        ),
        "cost_source_asof_utc": (
            cost_projection["source_asof_utc"]
            if cost_projection is not None
            else None
        ),
        "candidate_rows": candidate_rows,
        "selection_allowed": True,
        "latest_alias_used": False,
    }
    result["snapshot_hash"] = _canonical_sha256(result)
    return result


def _failure(
    status: str,
    evaluated_at: str,
    **details: Any,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "source_status": status,
        "evaluated_at": evaluated_at,
        "candidate_universe_complete": False,
        "candidate_rows": [],
        "selection_allowed": False,
        "latest_alias_used": False,
        **details,
    }
    result["snapshot_hash"] = _canonical_sha256(result)
    return result


def _validate_candidate_row_contract(
    row: Mapping[str, Any],
    *,
    require_full_board_contract: bool,
    as_of_date: date | None = None,
) -> tuple[str | None, dict[str, Any] | None]:
    if require_full_board_contract and set(row) != _CANDIDATE_ROW_FIELDS:
        return "CANDIDATE_FIELDS_INVALID", None
    if row.get("schema_version") != _CANDIDATE_SCHEMA_VERSION:
        return "CANDIDATE_SCHEMA_INVALID", None
    if any(field not in row for field in _SELECTION_FIELDS):
        return "CANDIDATE_FIELDS_MISSING", None
    candidate_id = row.get("candidate_id")
    if not _is_sha256(candidate_id):
        return "CANDIDATE_ID_INVALID", None
    if not _is_sha256(row.get("candidate_family_key")):
        return "CANDIDATE_FAMILY_KEY_INVALID", None
    if not _is_sha256(row.get("stable_cohort_hash")):
        return "STABLE_COHORT_HASH_INVALID", None
    if not isinstance(row.get("candidate_identity"), Mapping):
        return "CANDIDATE_IDENTITY_INVALID", None
    flag_fields = [
        "identity_complete",
        "arbiter_input_complete",
        "selection_eligible",
    ]
    if require_full_board_contract:
        flag_fields.extend(
            [
                "qualified_metrics_actionable",
                "zero_variance_suspect",
                "data_integrity_suspect",
                "cluster_variance_clean",
                "legacy_optimistic_cost_present",
                "hidden_oos_consumed",
            ]
        )
    for field in flag_fields:
        if not isinstance(row.get(field), bool):
            return "CANDIDATE_FLAGS_INVALID", None
    if row.get("identity_complete") is not True:
        return "CANDIDATE_FLAGS_INVALID", None
    blockers = row.get("blockers")
    if not isinstance(blockers, list) or not all(
        isinstance(item, str) and item and item == item.strip() for item in blockers
    ) or blockers != sorted(set(blockers)):
        return "CANDIDATE_BLOCKERS_INVALID", None
    if require_full_board_contract:
        if any(
            not _nonnegative_int(row.get(field))
            for field in _CANDIDATE_COUNT_FIELDS
        ):
            return "CANDIDATE_COUNT_INVALID", None
        if row["qualified_evaluator_input_count"] != (
            row["qualified_uncensored_outcome_count"]
            + row["qualified_censored_outcome_count"]
        ) or row["qualified_uncensored_outcome_count"] != (
            row["qualified_valid_uncensored_outcome_count"]
            + row["qualified_invalid_outcome_row_count"]
        ):
            return "CANDIDATE_COUNT_INVARIANT_INVALID", None
        accounted_qualified_rows = (
            row["qualified_evaluator_input_count"]
            + row["consistent_duplicate_event_hash_extra_row_count"]
        )
        if not accounted_qualified_rows <= row[
            "qualified_raw_outcome_count"
        ] <= accounted_qualified_rows + row["conflicting_event_hash_row_count"]:
            return "CANDIDATE_COUNT_INVARIANT_INVALID", None
        if row["n_eff"] > row["qualified_valid_uncensored_outcome_count"]:
            return "CANDIDATE_COUNT_INVARIANT_INVALID", None
        if row["conflicting_event_hash_row_count"] != (
            row["duplicate_event_hash_outcome_conflict_row_count"]
            + row["duplicate_event_hash_cohort_conflict_row_count"]
        ):
            return "CANDIDATE_COUNT_INVARIANT_INVALID", None
        if not _candidate_statistical_invariants_hold(row):
            return "CANDIDATE_STATISTICAL_INVARIANT_INVALID", None
    if row.get("selection_eligible") is not (not blockers):
        return "CANDIDATE_SELECTION_FLAGS_INVALID", None
    if row.get("selection_eligible") is True and (
        row.get("identity_complete") is not True
        or row.get("arbiter_input_complete") is not True
    ):
        return "CANDIDATE_SELECTION_FLAGS_INVALID", None

    arbiter_input = row.get("arbiter_input")
    if not isinstance(arbiter_input, Mapping):
        return "ARBITER_INPUT_INVALID", None
    if set(arbiter_input) != _ARBITER_INPUT_FIELDS:
        return "ARBITER_INPUT_FIELDS_INVALID", None
    if arbiter_input.get("schema_version") != _ARBITER_INPUT_SCHEMA_VERSION:
        return "ARBITER_INPUT_SCHEMA_INVALID", None
    declared_input_hash = arbiter_input.get("arbiter_input_hash")
    if not _is_sha256(declared_input_hash):
        return "ARBITER_INPUT_HASH_INVALID", None
    input_body = {
        str(key): copy.deepcopy(value)
        for key, value in arbiter_input.items()
        if key != "arbiter_input_hash"
    }
    if declared_input_hash != _canonical_sha256(input_body):
        return "ARBITER_INPUT_HASH_MISMATCH", None
    contract_status = _validate_arbiter_input_contract(
        arbiter_input,
        as_of_date=as_of_date,
    )
    if contract_status is not None:
        return contract_status, None
    if not _candidate_blockers_match_contract(blockers, arbiter_input, row):
        return "CANDIDATE_BLOCKER_SEMANTICS_INVALID", None
    identity = arbiter_input.get("identity")
    context_hashes = arbiter_input.get("context_hashes")
    if not isinstance(identity, Mapping) or not isinstance(context_hashes, Mapping):
        return "ARBITER_INPUT_IDENTITY_INVALID", None
    if set(context_hashes) != {"data", "evidence", "cost", "portfolio"} or not all(
        _is_sha256(value) for value in context_hashes.values()
    ):
        return "ARBITER_CONTEXT_HASHES_INVALID", None
    expected_candidate_id = _canonical_sha256(
        {
            "schema_version": _CANDIDATE_SCHEMA_VERSION,
            "identity": copy.deepcopy(dict(identity)),
            "context_hashes": copy.deepcopy(dict(context_hashes)),
        }
    )
    if candidate_id != expected_candidate_id:
        return "CANDIDATE_ID_MISMATCH", None
    try:
        family_identity = {
            "strategy_name": identity["strategy_name"],
            "strategy_version": identity["strategy_version"],
            "strategy_config_hash": identity["config_hash"],
            "symbol": identity["symbol"],
            "side": identity["side"],
            "horizon_minutes": identity["horizon_minutes"],
            "venue": identity["venue"],
            "product": identity["product"],
            "evidence_engine_mode": identity["evidence_engine_mode"],
        }
        target_regime = identity["target_regime"]
        target_context = {
            str(key): copy.deepcopy(value)
            for key, value in target_regime.items()
            if key != "hash"
        }
        stable_target_context = {
            key: copy.deepcopy(target_context[key])
            for key in ("label", "utc_date", "point_in_time")
        }
        evidence = arbiter_input["evidence"]
        stable_projection = {
            "strategy_version": family_identity["strategy_version"],
            "strategy_config_hash": family_identity["strategy_config_hash"],
            "target_regime_context": stable_target_context,
            "target_regime_hash": target_regime["hash"],
            "venue": family_identity["venue"],
            "product": family_identity["product"],
            "evidence_engine_mode": family_identity["evidence_engine_mode"],
            "context_hashes": copy.deepcopy(dict(context_hashes)),
            "resource": copy.deepcopy(arbiter_input["resource"]),
            "portfolio": copy.deepcopy(arbiter_input["portfolio"]),
            "proof": {
                "proof_stage": evidence["proof_stage"],
                "completed_proof_stages": evidence["completed_proof_stages"],
                "next_gap": evidence["next_gap"],
            },
            "hidden_oos_consumed": arbiter_input["quality"][
                "hidden_oos_consumed"
            ],
        }
    except KeyError:
        return "ARBITER_INPUT_IDENTITY_INVALID", None
    expected_family_key = _canonical_sha256(
        {
            "schema_version": _CANDIDATE_FAMILY_SCHEMA_VERSION,
            "identity": family_identity,
        }
    )
    if row.get("candidate_family_key") != expected_family_key:
        return "CANDIDATE_FAMILY_KEY_MISMATCH", None
    expected_stable_cohort_hash = _canonical_sha256(
        {
            "identity": family_identity,
            "stable_projection": stable_projection,
        }
    )
    if row.get("stable_cohort_hash") != expected_stable_cohort_hash:
        return "STABLE_COHORT_HASH_MISMATCH", None
    target_regime = identity.get("target_regime")
    if not isinstance(target_regime, Mapping) or "hash" not in target_regime:
        return "ARBITER_INPUT_IDENTITY_INVALID", None
    expected_candidate_identity = {
        "strategy_name": identity.get("strategy_name"),
        "strategy_version": identity.get("strategy_version"),
        "strategy_config_hash": identity.get("config_hash"),
        "symbol": identity.get("symbol"),
        "side": identity.get("side"),
        "horizon_minutes": identity.get("horizon_minutes"),
        "venue": identity.get("venue"),
        "product": identity.get("product"),
        "evidence_engine_mode": identity.get("evidence_engine_mode"),
        "target_regime_context": {
            str(key): copy.deepcopy(value)
            for key, value in target_regime.items()
            if key != "hash"
        },
        "target_regime_hash": target_regime.get("hash"),
        "engine_mode": identity.get("engine_mode"),
    }
    if not _exact_value_equal(
        row.get("candidate_identity"), expected_candidate_identity
    ):
        return "CANDIDATE_IDENTITY_MISMATCH", None
    if require_full_board_contract:
        binding_status = _validate_candidate_row_bindings(
            row,
            arbiter_input=arbiter_input,
            family_identity=family_identity,
        )
        if binding_status is not None:
            return binding_status, None

    semantic_row = {
        field: copy.deepcopy(row[field]) for field in _SELECTION_FIELDS
    }
    return None, semantic_row


def validate_candidate_selection_row_v2(
    row: Mapping[str, Any],
) -> tuple[str | None, dict[str, Any] | None]:
    """重驗一列 v2 selection 語義，供後續純 projection 共用。"""
    return _validate_candidate_row_contract(
        row,
        require_full_board_contract=False,
    )


def _candidate_blockers_match_contract(
    blockers: list[str],
    arbiter_input: Mapping[str, Any],
    row: Mapping[str, Any],
) -> bool:
    """重建 typed input 與必要 audit 可判定 blocker，避免 self-hash 洗白。"""
    quality = arbiter_input["quality"]
    evidence = arbiter_input["evidence"]
    entry_ts_missing = row.get("qualified_entry_ts_missing_row_count")
    invalid_outcomes = row.get("qualified_invalid_outcome_row_count")
    data_integrity_suspect = row.get("data_integrity_suspect")
    tail_share = row.get("tail_cost_recomputable_share")
    if (
        not _nonnegative_int(entry_ts_missing)
        or not _nonnegative_int(invalid_outcomes)
        or type(data_integrity_suspect) is not bool
        or not _bounded_float(tail_share)
    ):
        return False
    lineage_counts: dict[str, int] = {}
    for field, code in _LINEAGE_BLOCKER_COUNT_FIELDS:
        count = row.get(field)
        if not _nonnegative_int(count):
            return False
        if count:
            lineage_counts[code] = count
    declared_lineage_counts = row.get("lineage_blocker_reason_counts")
    if not isinstance(declared_lineage_counts, Mapping) or not _exact_value_equal(
        declared_lineage_counts,
        lineage_counts,
    ):
        return False
    expected_integrity_ok = bool(
        not lineage_counts
        and entry_ts_missing == 0
        and invalid_outcomes == 0
        and not data_integrity_suspect
        and quality["cluster_variance_clean"]
    )
    if (
        quality["hash_ok"] is not True
        or quality["freshness_ok"] is not True
        or (
            quality["replica_inconsistency_count"] > 0
            and data_integrity_suspect is not True
        )
        or quality["integrity_ok"] is not expected_integrity_ok
    ):
        return False
    expected: set[str] = set()
    conditions = {
        "EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT": evidence["n_eff"] < 30,
        "UTC_DAY_COVERAGE_INSUFFICIENT": evidence["utc_day_count"] < 5,
        "TOP_DAY_CONCENTRATION_EXCESS": quality["top_day_share"] > 0.5,
        "DATA_INTEGRITY_SUSPECT": data_integrity_suspect,
        "DAY_CLUSTER_VARIANCE_DEGENERATE": not quality[
            "cluster_variance_clean"
        ],
        "CENSORING_EXCESS": quality["censored_share"] > 0.3,
        "LEGACY_OPTIMISTIC_COST_UNBACKFILLED": quality[
            "legacy_optimistic_cost_present"
        ],
        "EXPECTED_COST_NOT_FULLY_RECOMPUTABLE": quality[
            "cost_recomputable_share"
        ] < 1.0,
        "PROOF_GAP_OPEN": evidence["next_gap"]["kind"] != "NONE",
        "HIDDEN_OOS_CONSUMED": quality["hidden_oos_consumed"],
        "ENTRY_TS_LINEAGE_INCOMPLETE": entry_ts_missing > 0,
        "INVALID_OUTCOME_ROWS_PRESENT": invalid_outcomes > 0,
        "TAIL_COST_NOT_FULLY_RECOMPUTABLE": tail_share < 1.0,
    }
    expected.update(code for code, active in conditions.items() if active)
    expected.update(lineage_counts)
    actual = set(blockers)
    return actual == expected


def _validate_candidate_row_bindings(
    row: Mapping[str, Any],
    *,
    arbiter_input: Mapping[str, Any],
    family_identity: Mapping[str, Any],
) -> str | None:
    if row.get("side_cell_key") != (
        f"{family_identity['strategy_name']}|{family_identity['symbol']}|"
        f"{family_identity['side']}"
    ) or row.get("horizon_minutes") != family_identity["horizon_minutes"]:
        return "CANDIDATE_OUTER_IDENTITY_INVALID"
    lineage_counts: dict[str, int] = {}
    for field, code in _LINEAGE_BLOCKER_COUNT_FIELDS:
        count = row[field]
        if count:
            lineage_counts[code] = count
    blockers = row["blockers"]
    incomplete_codes = {
        "IDENTITY_LINEAGE_INCOMPLETE",
        "ARBITER_INPUT_CONTEXT_INCOMPLETE",
        *lineage_counts,
    }
    expected_input_complete = not any(code in blockers for code in incomplete_codes)
    if row.get("arbiter_input_complete") is not expected_input_complete:
        return "CANDIDATE_INPUT_COMPLETENESS_INVALID"
    nonactionable_codes = incomplete_codes | {
        "INVALID_OUTCOME_ROWS_PRESENT",
        "DATA_INTEGRITY_SUSPECT",
        "ENTRY_TS_LINEAGE_INCOMPLETE",
        "CENSORING_EXCESS",
    }
    expected_actionable = not any(code in blockers for code in nonactionable_codes)
    if row.get("qualified_metrics_actionable") is not expected_actionable or row.get(
        "metrics_scope"
    ) != (
        "QUALIFIED_SUBSET_ACTIONABLE"
        if expected_actionable
        else "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"
    ):
        return "CANDIDATE_METRICS_SCOPE_INVALID"
    evidence = arbiter_input["evidence"]
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
        return "CANDIDATE_EVIDENCE_BINDING_INVALID"
    quality = arbiter_input["quality"]
    expected_quality_bindings = {
        "hash_ok": True,
        "freshness_ok": True,
        "integrity_ok": bool(
            not lineage_counts
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
        "replica_inconsistency_count": row[
            "replica_inconsistent_group_count"
        ],
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
        return "CANDIDATE_QUALITY_BINDING_INVALID"
    cost_evidence = arbiter_input["cost_evidence"]
    if row["cost_basis_main"] != cost_evidence["basis"]:
        return "CANDIDATE_COST_EVIDENCE_BINDING_INVALID"
    tail_source = cost_evidence["tail_source"]
    if (
        tail_source["tail_bps"] is None
        and row["tail_cost_recomputable_count"] != 0
        or row["tail_cost_recomputable_count"] > 0
        and row["tail_metric"] != tail_source["tail_metric"]
    ):
        return "CANDIDATE_COST_EVIDENCE_BINDING_INVALID"
    if row["expected_cost_recomputable_count"] > 0 and (
        row["avg_expected_cost_bps"]
        < cost_evidence["fee_floor_bps"]
        + 2.0 * cost_evidence["mean_abs_source"]["mean_abs_bps"]
    ):
        return "CANDIDATE_COST_EVIDENCE_BINDING_INVALID"
    if row["tail_cost_recomputable_count"] > 0 and (
        row["avg_tail_cost_bps"]
        < cost_evidence["fee_floor_bps"]
        + 2.0 * cost_evidence["tail_source"]["tail_bps"]
    ):
        return "CANDIDATE_COST_EVIDENCE_BINDING_INVALID"
    return None


def _candidate_sort_key(row: Mapping[str, Any]) -> tuple[str, str]:
    candidate_id = row.get("candidate_id")
    return (
        candidate_id if isinstance(candidate_id, str) else "",
        _canonical_sha256(row),
    )


def _candidate_board_row_sort_key(row: Mapping[str, Any]) -> tuple[Any, ...]:
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


def _candidate_statistical_invariants_hold(row: Mapping[str, Any]) -> bool:
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
        return False
    if row.get("cost_basis_main") not in {
        "conservative_v1",
        "expected_slippage_mean_abs_v1",
    }:
        return False
    if (
        not _finite_float_or_none(row.get("avg_net_bps"))
        or not _finite_float_or_none(row.get("mean_net_e"))
        or not _exact_value_equal(row.get("avg_net_bps"), row.get("mean_net_e"))
        or (n_eff == 0) is not (row.get("mean_net_e") is None)
    ):
        return False
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
        return False
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
            return False
    elif cluster_se is not None or not (
        variance is None or type(variance) is float and variance == 0.0
    ):
        return False
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
        or any(not _nonnegative_int(count) for count in regime_counts.values())
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
        return False
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
        return False
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
    expected_unknown_share = (
        regime_counts["unknown"] / n_eff if n_eff else 1.0
    )
    if (
        not _same_float(row.get("censored_share"), expected_censored_share)
        or not _same_float(
            row.get("censored_pct"), expected_censored_share * 100.0
        )
        or not _same_float(
            row.get("expected_cost_recomputable_share"), expected_cost_share
        )
        or not _same_float(row.get("cost_recomputable_share"), expected_cost_share)
        or not _same_float(
            row.get("tail_cost_recomputable_share"), expected_tail_share
        )
    ):
        return False
    if n_eff:
        top_day, top_count = sorted(
            entry_day_counts.items(), key=lambda item: (-item[1], item[0])
        )[0]
        expected_top_share_pct = top_count / n_eff * 100.0
        expected_top_share = expected_top_share_pct / 100.0
        if (
            row.get("top_entry_utc_day") != top_day
            or not _same_float(
                row.get("top_entry_day_share"), expected_top_share
            )
            or not _same_float(
                row.get("top_entry_day_share_pct"), expected_top_share_pct
            )
        ):
            return False
    elif any(
        row.get(field) is not None
        for field in (
            "top_entry_utc_day",
            "top_entry_day_share",
            "top_entry_day_share_pct",
        )
    ):
        return False
    expected_coverage = {
        "composite_bucket_universe_size": len(_REGIME_BUCKETS),
        "observed_composite_bucket_count": sum(
            regime_counts[label] > 0 for label in _REGIME_BUCKETS
        ),
        "effective_entry_count": n_eff,
        "unknown_regime_entry_count": regime_counts["unknown"],
        "unknown_regime_share": expected_unknown_share,
    }
    return _exact_value_equal(coverage, expected_coverage)


def _board_count_invariants_hold(board: Mapping[str, Any]) -> bool:
    count_fields = (
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
    )
    values = [board.get(field) for field in count_fields]
    if board.get("lineage_partition_complete") is not True or any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in values
    ):
        return False
    raw, qualified, unqualified, invalid, exact, family, unassigned, *_ = values
    reasons = board.get("lineage_exclusion_reason_counts")
    return bool(
        raw == qualified + unqualified + invalid
        and invalid == exact + family + unassigned
        and isinstance(reasons, Mapping)
        and all(
            isinstance(key, str)
            and key
            and not isinstance(value, bool)
            and isinstance(value, int)
            and value >= 0
            for key, value in reasons.items()
        )
    )


def _board_reason_counts_hold(board: Mapping[str, Any]) -> bool:
    reasons = board.get("lineage_exclusion_reason_counts")
    return bool(
        isinstance(reasons, Mapping)
        and set(reasons).issubset(_LINEAGE_EXCLUSION_REASONS)
        and all(
            isinstance(code, str)
            and code
            and code == code.strip()
            and _nonnegative_int(count)
            and count > 0
            for code, count in reasons.items()
        )
        and sum(reasons.values())
        == board.get("unqualified_lineage_outcome_row_count")
        + board.get("invalid_lineage_outcome_row_count")
        and sum(reasons.get(code, 0) for code in _UNQUALIFIED_EXCLUSION_REASONS)
        == board.get("unqualified_lineage_outcome_row_count")
        and sum(reasons.get(code, 0) for code in _INVALID_EXCLUSION_REASONS)
        == board.get("invalid_lineage_outcome_row_count")
        and reasons.get("INVALID_LINEAGE_EXACT_COHORT", 0)
        == board.get("invalid_exact_cohort_row_count")
        and reasons.get("INVALID_LINEAGE_IDENTITY_FAMILY", 0)
        == board.get("invalid_identity_family_row_count")
        and reasons.get("INVALID_LINEAGE_RAW_CONTEXT_INVALID", 0)
        == board.get("unassigned_invalid_lineage_outcome_row_count")
        and reasons.get("UNQUALIFIED_RAW_VALID_EVALUATION_MISSING", 0)
        == board.get("unqualified_raw_valid_evaluation_missing_row_count")
        and reasons.get("UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW", 0)
        == board.get("unqualified_event_outside_evaluation_window_row_count")
    )


def _producer_float_or_none(value: Any, *, nonnegative: bool) -> float | None:
    if value is None:
        return None
    if type(value) is not float or not math.isfinite(value):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    if nonnegative and value < 0.0:
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    return value


def _validate_slippage_stat_block(
    value: Any,
    *,
    symbol_row: bool,
) -> dict[str, Any]:
    expected_fields = _SLIPPAGE_SYMBOL_FIELDS if symbol_row else _SLIPPAGE_STAT_FIELDS
    if not isinstance(value, Mapping) or set(value) != expected_fields:
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    count = value["n"]
    if type(count) is not int or count <= 0:
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    mean_abs = _producer_float_or_none(value["mean_abs"], nonnegative=True)
    mean_signed = _producer_float_or_none(value["mean_signed"], nonnegative=False)
    q50 = _producer_float_or_none(value["q50"], nonnegative=True)
    q75 = _producer_float_or_none(value["q75"], nonnegative=True)
    q90 = _producer_float_or_none(value["q90"], nonnegative=True)
    cvar90 = _producer_float_or_none(value["cvar90"], nonnegative=True)
    if (
        mean_abs is None
        or mean_signed is None
        or q50 is None
        or q75 is None
        or q90 is None and cvar90 is not None
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    if abs(mean_signed) > mean_abs and not math.isclose(
        abs(mean_signed),
        mean_abs,
        rel_tol=_SLIPPAGE_MEAN_REL_TOL,
        abs_tol=_SLIPPAGE_MEAN_ABS_TOL_BPS,
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    quantiles = [item for item in (q50, q75, q90) if item is not None]
    if quantiles != sorted(quantiles) or (
        cvar90 is not None and q90 is not None and cvar90 < q90
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    thin_sample = value["thin_sample"]
    if type(thin_sample) is not bool or thin_sample is not (count < 100):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    result = {
        "n": count,
        "mean_abs": mean_abs,
        "mean_signed": mean_signed,
        "q50": q50,
        "q75": q75,
        "q90": q90,
        "cvar90": cvar90,
        "thin_sample": thin_sample,
    }
    if symbol_row:
        symbol = value["symbol"]
        if (
            not isinstance(symbol, str)
            or not symbol
            or symbol != symbol.strip()
            or symbol != symbol.upper()
        ):
            raise ValueError("EXPECTED_COST_SOURCE_INVALID")
        result["symbol"] = symbol
    return result


def _tail_projection(block: Mapping[str, Any]) -> tuple[float | None, str | None]:
    if block["cvar90"] is not None:
        return block["cvar90"], "cvar90"
    if block["q90"] is not None:
        return block["q90"], "q90_fallback"
    return None, None


def _project_embedded_slippage_v2(
    value: Any,
    *,
    generated: datetime,
    evaluated: datetime,
) -> dict[str, Any]:
    if (
        not isinstance(value, Mapping)
        or set(value) != _SLIPPAGE_ARTIFACT_FIELDS
        or value.get("schema_version") != _SLIPPAGE_ARTIFACT_SCHEMA_VERSION
        or type(value.get("window_days")) is not int
        or value["window_days"] != 90
        or value.get("boundary") != _SLIPPAGE_BOUNDARY
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    try:
        source_asof = datetime.fromisoformat(value["asof"])
    except (TypeError, ValueError):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID") from None
    if (
        source_asof.tzinfo is None
        or source_asof.utcoffset() != timedelta(0)
        or value["asof"] != source_asof.isoformat()
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    if source_asof > generated:
        raise ValueError("EXPECTED_COST_SOURCE_AFTER_BOARD_GENERATED")
    age_seconds = (evaluated - source_asof).total_seconds()
    if not 0.0 <= age_seconds <= QUANTILE_ARTIFACT_MAX_AGE_HOURS * 3600:
        raise ValueError("EXPECTED_COST_SOURCE_STALE")
    global_block = _validate_slippage_stat_block(value.get("global"), symbol_row=False)
    if (
        type(value.get("n_total_global")) is not int
        or value["n_total_global"] != global_block["n"]
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    raw_symbols = value.get("symbols")
    if not isinstance(raw_symbols, list):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    symbols = [
        _validate_slippage_stat_block(item, symbol_row=True)
        for item in raw_symbols
    ]
    symbol_names = [item["symbol"] for item in symbols]
    if (
        not symbols
        or symbol_names != sorted(symbol_names)
        or len(symbol_names) != len(set(symbol_names))
        or sum(item["n"] for item in symbols) != global_block["n"]
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    try:
        weighted_mean_abs = math.fsum(
            item["mean_abs"] * item["n"] for item in symbols
        ) / global_block["n"]
        weighted_mean_signed = math.fsum(
            item["mean_signed"] * item["n"] for item in symbols
        ) / global_block["n"]
    except (OverflowError, ValueError):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID") from None
    if (
        not math.isfinite(weighted_mean_abs)
        or not math.isfinite(weighted_mean_signed)
        or not math.isclose(
            global_block["mean_abs"],
            weighted_mean_abs,
            rel_tol=_SLIPPAGE_MEAN_REL_TOL,
            abs_tol=_SLIPPAGE_MEAN_ABS_TOL_BPS,
        )
        or not math.isclose(
            global_block["mean_signed"],
            weighted_mean_signed,
            rel_tol=_SLIPPAGE_MEAN_REL_TOL,
            abs_tol=_SLIPPAGE_MEAN_ABS_TOL_BPS,
        )
    ):
        raise ValueError("EXPECTED_COST_SOURCE_INVALID")
    global_tail, global_tail_metric = _tail_projection(global_block)
    normalized_symbols = []
    per_symbol: dict[str, dict[str, Any]] = {}
    for item in symbols:
        tail_bps, tail_metric = _tail_projection(item)
        normalized_symbols.append(
            {
                "symbol": item["symbol"],
                "n": item["n"],
                "mean_abs_bps": item["mean_abs"],
                "tail_bps": tail_bps,
                "tail_metric": tail_metric,
            }
        )
        per_symbol[item["symbol"]] = {
            "n": item["n"],
            "mean_abs": item["mean_abs"],
            "tail_bps": tail_bps,
            "tail_metric": tail_metric,
        }
    projection = {
        "schema_version": _SLIPPAGE_PROJECTION_SCHEMA_VERSION,
        "source_asof_utc": source_asof.isoformat(),
        "source_window_days": value["window_days"],
        "global": {
            "n": global_block["n"],
            "mean_abs_bps": global_block["mean_abs"],
            "tail_bps": global_tail,
            "tail_metric": global_tail_metric,
        },
        "symbols": normalized_symbols,
    }
    source_payload = copy.deepcopy(dict(value))
    return {
        "source_payload": source_payload,
        "source_payload_sha256": _canonical_sha256(source_payload),
        "source_asof_utc": source_asof.isoformat(),
        "normalized_projection": projection,
        "normalized_projection_sha256": _canonical_sha256(projection),
        "global_mean_abs": global_block["mean_abs"],
        "global_tail_bps": global_tail,
        "global_tail_metric": global_tail_metric,
        "n_total_global": global_block["n"],
        "per_symbol": per_symbol,
    }


def _candidate_cost_evidence_from_projection(
    projection: Mapping[str, Any] | None,
    *,
    symbol: str,
) -> dict[str, Any]:
    if projection is None:
        return {
            "schema_version": _COST_EVIDENCE_SCHEMA_VERSION,
            "basis": "conservative_v1",
            "source_payload_sha256": None,
            "source_asof_utc": None,
            "normalized_projection_sha256": None,
            "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
            "fee_floor_bps": FEE_FLOOR_BPS,
            "mean_abs_source": {
                "scope": "NONE", "symbol": None, "sample_count": 0,
                "mean_abs_bps": None,
            },
            "tail_source": {
                "scope": "NONE", "symbol": None, "sample_count": 0,
                "tail_bps": None, "tail_metric": None,
            },
        }
    symbol_entry = projection["per_symbol"].get(symbol)
    use_symbol = bool(
        isinstance(symbol_entry, Mapping)
        and symbol_entry["n"] >= MIN_SYMBOL_FILLS_FOR_QUANTILE
    )
    mean_source = {
        "scope": "SYMBOL" if use_symbol else "GLOBAL",
        "symbol": symbol if use_symbol else None,
        "sample_count": (
            symbol_entry["n"] if use_symbol else projection["n_total_global"]
        ),
        "mean_abs_bps": (
            symbol_entry["mean_abs"] if use_symbol else projection["global_mean_abs"]
        ),
    }
    use_symbol_tail = bool(use_symbol and symbol_entry["tail_bps"] is not None)
    tail_source = {
        "scope": "SYMBOL" if use_symbol_tail else "GLOBAL",
        "symbol": symbol if use_symbol_tail else None,
        "sample_count": (
            symbol_entry["n"]
            if use_symbol_tail
            else projection["n_total_global"]
        ),
        "tail_bps": (
            symbol_entry["tail_bps"]
            if use_symbol_tail
            else projection["global_tail_bps"]
        ),
        "tail_metric": (
            symbol_entry["tail_metric"]
            if use_symbol_tail
            else projection["global_tail_metric"]
        ),
    }
    return {
        "schema_version": _COST_EVIDENCE_SCHEMA_VERSION,
        "basis": "expected_slippage_mean_abs_v1",
        "source_payload_sha256": projection["source_payload_sha256"],
        "source_asof_utc": projection["source_asof_utc"],
        "normalized_projection_sha256": projection[
            "normalized_projection_sha256"
        ],
        "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
        "fee_floor_bps": FEE_FLOOR_BPS,
        "mean_abs_source": mean_source,
        "tail_source": tail_source,
    }


def _validate_outer_cost_contract(
    payload: Mapping[str, Any],
    *,
    generated: datetime,
    evaluated: datetime,
) -> tuple[str | None, dict[str, Any] | None]:
    basis = payload.get("cost_basis_main")
    if basis not in {"conservative_v1", "expected_slippage_mean_abs_v1"}:
        return "OUTER_COST_BASIS_INVALID", None
    outer = payload.get("expected_cost_artifact")
    if basis == "conservative_v1":
        expected_outer = {
            "available": False,
            "asof": None,
            "source_asof_utc": None,
            "source_payload_sha256": None,
            "source_payload": None,
            "normalized_projection": None,
            "normalized_projection_sha256": None,
            "global_mean_abs_bps": None,
            "global_tail_bps": None,
            "global_tail_metric": None,
            "n_total_global": 0,
            "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
        }
        return (
            (None, None)
            if _exact_value_equal(outer, expected_outer)
            else ("OUTER_COST_EVIDENCE_INVALID", None)
        )
    if not isinstance(outer, Mapping):
        return "OUTER_COST_EVIDENCE_INVALID", None
    try:
        projection = _project_embedded_slippage_v2(
            outer.get("source_payload"),
            generated=generated,
            evaluated=evaluated,
        )
    except ValueError as exc:
        return str(exc), None
    expected_outer = {
        "available": True,
        "asof": projection["source_asof_utc"],
        "source_asof_utc": projection["source_asof_utc"],
        "source_payload_sha256": projection["source_payload_sha256"],
        "source_payload": projection["source_payload"],
        "normalized_projection": projection["normalized_projection"],
        "normalized_projection_sha256": projection[
            "normalized_projection_sha256"
        ],
        "global_mean_abs_bps": projection["global_mean_abs"],
        "global_tail_bps": projection["global_tail_bps"],
        "global_tail_metric": projection["global_tail_metric"],
        "n_total_global": projection["n_total_global"],
        "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
    }
    return (
        (None, projection)
        if _exact_value_equal(outer, expected_outer)
        else ("OUTER_COST_EVIDENCE_INVALID", None)
    )


def _validate_cost_evidence_contract(
    value: Any,
    *,
    identity: Mapping[str, Any],
    as_of_date: date | None,
) -> str | None:
    if not isinstance(value, Mapping) or set(value) != _COST_EVIDENCE_FIELDS:
        return "COST_EVIDENCE_FIELDS_INVALID"
    if (
        value.get("schema_version") != _COST_EVIDENCE_SCHEMA_VERSION
        or type(value.get("max_age_hours")) is not int
        or value["max_age_hours"] != QUANTILE_ARTIFACT_MAX_AGE_HOURS
        or type(value.get("fee_floor_bps")) is not float
        or value["fee_floor_bps"] != FEE_FLOOR_BPS
    ):
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    mean_source = value.get("mean_abs_source")
    tail_source = value.get("tail_source")
    if (
        not isinstance(mean_source, Mapping)
        or set(mean_source) != _MEAN_ABS_SOURCE_FIELDS
        or not isinstance(tail_source, Mapping)
        or set(tail_source) != _TAIL_SOURCE_FIELDS
    ):
        return "COST_EVIDENCE_FIELDS_INVALID"
    if value.get("basis") == "conservative_v1":
        expected = {
            "source_payload_sha256": None,
            "source_asof_utc": None,
            "normalized_projection_sha256": None,
            "mean_abs_source": {
                "scope": "NONE", "symbol": None, "sample_count": 0,
                "mean_abs_bps": None,
            },
            "tail_source": {
                "scope": "NONE", "symbol": None, "sample_count": 0,
                "tail_bps": None, "tail_metric": None,
            },
        }
        actual = {key: copy.deepcopy(value.get(key)) for key in expected}
        return None if _exact_value_equal(actual, expected) else "COST_EVIDENCE_SEMANTICS_INVALID"
    if value.get("basis") != "expected_slippage_mean_abs_v1":
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    if (
        not _is_sha256(value.get("source_payload_sha256"))
        or not _is_sha256(value.get("normalized_projection_sha256"))
    ):
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    try:
        source_asof = datetime.fromisoformat(value["source_asof_utc"])
    except (TypeError, ValueError):
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    if (
        source_asof.tzinfo is None
        or source_asof.utcoffset() != timedelta(0)
        or value["source_asof_utc"] != source_asof.isoformat()
        or as_of_date is not None
        and not as_of_date - timedelta(days=2) <= source_asof.date() <= as_of_date
    ):
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    for source, value_field in (
        (mean_source, "mean_abs_bps"),
        (tail_source, "tail_bps"),
    ):
        scope = source.get("scope")
        count = source.get("sample_count")
        statistic = source.get(value_field)
        if (
            scope not in {"GLOBAL", "SYMBOL"}
            or type(count) is not int
            or count <= 0
            or scope == "GLOBAL" and source.get("symbol") is not None
            or scope == "SYMBOL"
            and (
                source.get("symbol") != identity.get("symbol")
                or count < MIN_SYMBOL_FILLS_FOR_QUANTILE
            )
            or statistic is not None
            and (
                type(statistic) is not float
                or not math.isfinite(statistic)
                or statistic < 0.0
            )
        ):
            return "COST_EVIDENCE_SEMANTICS_INVALID"
    if mean_source["mean_abs_bps"] is None:
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    tail_metric = tail_source.get("tail_metric")
    if (tail_source["tail_bps"] is None) is not (tail_metric is None) or (
        tail_metric is not None and tail_metric not in {"cvar90", "q90_fallback"}
    ):
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    if (
        mean_source["scope"] == tail_source["scope"]
        and mean_source["symbol"] == tail_source["symbol"]
        and mean_source["sample_count"] != tail_source["sample_count"]
    ):
        return "COST_EVIDENCE_SEMANTICS_INVALID"
    return None


def _validate_arbiter_input_contract(
    value: Mapping[str, Any],
    *,
    as_of_date: date | None,
) -> str | None:
    """重驗 producer v2 nested contract；外層重算 hash 不能替代語義驗證。"""
    identity = value.get("identity")
    if not isinstance(identity, Mapping) or set(identity) != _ARBITER_IDENTITY_FIELDS:
        return "ARBITER_INPUT_IDENTITY_INVALID"
    for field in ("strategy_name", "symbol"):
        item = identity.get(field)
        if not isinstance(item, str) or not item or item != item.strip():
            return "ARBITER_INPUT_IDENTITY_INVALID"
    if not isinstance(identity.get("strategy_version"), str) or not _GIT_SHA_RE.fullmatch(
        identity["strategy_version"]
    ):
        return "STRATEGY_VERSION_INVALID"
    if not _is_sha256(identity.get("config_hash")):
        return "CONFIG_HASH_INVALID"
    if identity.get("symbol") != str(identity.get("symbol")).upper():
        return "SYMBOL_INVALID"
    if identity.get("side") not in {"Buy", "Sell"}:
        return "SIDE_INVALID"
    horizon = identity.get("horizon_minutes")
    if type(horizon) is not int or not 1 <= horizon <= 1_440:
        return "HORIZON_INVALID"
    if (
        identity.get("engine_mode") != "shadow"
        or identity.get("evidence_engine_mode") not in {"demo", "live_demo"}
    ):
        return "ENGINE_IDENTITY_INVALID"
    if (identity.get("venue"), identity.get("product")) != (
        "bybit",
        "linear_perpetual",
    ):
        return "MARKET_IDENTITY_INVALID"

    target = identity.get("target_regime")
    if not isinstance(target, Mapping) or set(target) != _TARGET_REGIME_FIELDS:
        return "TARGET_REGIME_FIELDS_INVALID"
    if target.get("label") not in _REGIME_BUCKETS:
        return "TARGET_REGIME_LABEL_INVALID"
    if (
        target.get("point_in_time") != "D-1"
        or target.get("source_complete") is not True
        or not _is_sha256(target.get("source_hash"))
        or not _is_sha256(target.get("classifier_hash"))
    ):
        return "TARGET_REGIME_INVALID"
    try:
        target_date = datetime.fromisoformat(str(target["utc_date"])).date()
    except (KeyError, ValueError):
        return "TARGET_REGIME_INVALID"
    if target.get("utc_date") != target_date.isoformat():
        return "TARGET_REGIME_INVALID"
    if as_of_date is not None and target_date != as_of_date - timedelta(days=1):
        return "TARGET_REGIME_DATE_INVALID"
    target_body = {
        key: copy.deepcopy(target[key])
        for key in (
            "label", "utc_date", "point_in_time", "source_complete",
            "source_hash", "classifier_hash",
        )
    }
    if target.get("hash") != _canonical_sha256(target_body):
        return "TARGET_REGIME_HASH_INVALID"

    context_hashes = value.get("context_hashes")
    if not isinstance(context_hashes, Mapping) or set(context_hashes) != {
        "data", "evidence", "cost", "portfolio"
    } or not all(_is_sha256(item) for item in context_hashes.values()):
        return "ARBITER_CONTEXT_HASHES_INVALID"

    cost_status = _validate_cost_evidence_contract(
        value.get("cost_evidence"),
        identity=identity,
        as_of_date=as_of_date,
    )
    if cost_status is not None:
        return cost_status

    quality = value.get("quality")
    if not isinstance(quality, Mapping) or set(quality) != _QUALITY_FIELDS:
        return "ARBITER_QUALITY_FIELDS_INVALID"
    if not all(type(quality.get(key)) is bool for key in (
        "hash_ok", "integrity_ok", "freshness_ok", "cluster_variance_clean",
        "hidden_oos_consumed", "legacy_optimistic_cost_present",
    )) or not _nonnegative_int(quality.get("replica_inconsistency_count")):
        return "ARBITER_QUALITY_TYPES_INVALID"
    if not all(_bounded_float(quality.get(key)) for key in (
        "censored_share", "cost_recomputable_share", "unknown_regime_share",
        "top_day_share",
    )):
        return "ARBITER_QUALITY_TYPES_INVALID"

    evidence = value.get("evidence")
    if not isinstance(evidence, Mapping) or set(evidence) != _EVIDENCE_FIELDS:
        return "ARBITER_EVIDENCE_FIELDS_INVALID"
    integer_fields = (
        "n_eff", "utc_day_count", "cluster_count", "proof_stage",
        "raw_attempt_count",
    )
    if not all(_nonnegative_int(evidence.get(key)) for key in integer_fields):
        return "ARBITER_EVIDENCE_TYPES_INVALID"
    if not _finite_float_or_none(evidence.get("mean_net_e")) or not all(
        _nonnegative_float_or_none(evidence.get(key))
        for key in ("day_cluster_variance", "cluster_se")
    ):
        return "ARBITER_EVIDENCE_TYPES_INVALID"
    stages = evidence.get("completed_proof_stages")
    if (
        evidence["proof_stage"] > 6
        or not isinstance(stages, list)
        or stages != list(range(evidence["proof_stage"] + 1))
    ):
        return "ARBITER_EVIDENCE_TYPES_INVALID"
    next_gap = evidence.get("next_gap")
    if not isinstance(next_gap, Mapping) or set(next_gap) != {"kind", "code"}:
        return "ARBITER_EVIDENCE_FIELDS_INVALID"
    if (
        next_gap.get("kind")
        not in {"NONE", "LOCAL_PASSIVE", "LOCAL_ENGINEERING", "EXTERNAL_OPERATOR"}
        or not isinstance(next_gap.get("code"), str)
        or not next_gap["code"]
        or next_gap["code"] != next_gap["code"].strip()
    ):
        return "ARBITER_EVIDENCE_TYPES_INVALID"
    regimes = evidence.get("regime_entry_counts")
    if not isinstance(regimes, Mapping) or set(regimes) != {*_REGIME_BUCKETS, "unknown"}:
        return "ARBITER_EVIDENCE_FIELDS_INVALID"
    if not all(_nonnegative_int(item) for item in regimes.values()) or sum(
        regimes.values()
    ) != evidence["n_eff"]:
        return "ARBITER_EVIDENCE_TYPES_INVALID"
    variance = evidence["day_cluster_variance"]
    cluster_se = evidence["cluster_se"]
    cluster_clean = quality["cluster_variance_clean"]
    if (
        evidence["raw_attempt_count"] < evidence["n_eff"]
        or evidence["cluster_count"] != evidence["utc_day_count"]
        or evidence["cluster_count"] > evidence["n_eff"]
        or (evidence["n_eff"] == 0) is not (evidence["mean_net_e"] is None)
        or (
            cluster_clean
            and (
                variance is None
                or cluster_se is None
                or variance <= 0.0
                or cluster_se <= 0.0
                or cluster_se != math.sqrt(variance)
            )
        )
        or (
            not cluster_clean
            and (
                cluster_se is not None
                or variance is not None
                and variance != 0.0
            )
        )
    ):
        return "ARBITER_EVIDENCE_ALGEBRA_INVALID"

    resource = value.get("resource")
    if not isinstance(resource, Mapping) or set(resource) != _RESOURCE_FIELDS:
        return "ARBITER_RESOURCE_FIELDS_INVALID"
    buckets = resource.get("daily_buckets")
    if not isinstance(buckets, list) or len(buckets) != 7:
        return "ARBITER_RESOURCE_FIELDS_INVALID"
    expected_dates = [target_date - timedelta(days=offset) for offset in range(6, -1, -1)]
    for bucket, expected_date in zip(buckets, expected_dates):
        if not isinstance(bucket, Mapping) or set(bucket) != {
            "utc_date", "scan_complete", "distinct_entries"
        }:
            return "ARBITER_RESOURCE_FIELDS_INVALID"
        if (
            bucket.get("utc_date") != expected_date.isoformat()
            or bucket.get("scan_complete") is not True
            or not _nonnegative_int(bucket.get("distinct_entries"))
        ):
            return "ARBITER_RESOURCE_INVALID"
    rows_scanned = resource.get("estimated_rows_scanned")
    canonical_bytes = resource.get("predicted_canonical_bytes")
    zero_attested = resource.get("zero_resource_attested")
    if (
        not _nonnegative_int(rows_scanned)
        or not _nonnegative_int(canonical_bytes)
        or type(resource.get("zero_resource_attested")) is not bool
    ):
        return "ARBITER_RESOURCE_INVALID"
    if (
        (rows_scanned == 0) != (canonical_bytes == 0)
        or rows_scanned == 0
        and (zero_attested is not True or any(bucket["distinct_entries"] for bucket in buckets))
        or rows_scanned > 0
        and zero_attested is not False
    ):
        return "ARBITER_RESOURCE_INVALID"
    resource_body = {
        key: copy.deepcopy(resource[key])
        for key in (
            "daily_buckets", "estimated_rows_scanned",
            "predicted_canonical_bytes", "zero_resource_attested",
        )
    }
    if resource.get("resource_estimator_hash") != _canonical_sha256(resource_body):
        return "ARBITER_RESOURCE_INVALID"

    portfolio = value.get("portfolio")
    if not isinstance(portfolio, Mapping) or set(portfolio) != _PORTFOLIO_FIELDS:
        return "ARBITER_PORTFOLIO_FIELDS_INVALID"
    decimals = {
        key: _canonical_decimal(portfolio.get(key)) for key in _PORTFOLIO_FIELDS
    }
    if any(value is None for value in decimals.values()) or any(
        not Decimal(0) <= decimals[key] <= Decimal(1)
        for key in ("sector_exposure_share", "strategy_active_target_share")
    ):
        return "ARBITER_PORTFOLIO_TYPES_INVALID"
    return None


def _nonnegative_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def _positive_int_value(value: Any) -> bool:
    return type(value) is int and value > 0


def _canonical_utc_date(value: str) -> bool:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return value == parsed.isoformat()


def _same_float(value: Any, expected: float) -> bool:
    return type(value) is float and math.isfinite(value) and value == expected


def _bounded_float(value: Any) -> bool:
    return type(value) is float and math.isfinite(value) and 0.0 <= value <= 1.0


def _finite_float_or_none(value: Any) -> bool:
    return value is None or type(value) is float and math.isfinite(value)


def _nonnegative_float(value: Any) -> bool:
    return type(value) is float and math.isfinite(value) and value >= 0.0


def _fee_floor_float(value: Any) -> bool:
    return _nonnegative_float(value) and value >= FEE_FLOOR_BPS


def _nonnegative_float_or_none(value: Any) -> bool:
    return value is None or type(value) is float and math.isfinite(value) and value >= 0.0


def _canonical_decimal(value: Any) -> Decimal | None:
    if not isinstance(value, str):
        return None
    try:
        decimal = Decimal(value)
    except (InvalidOperation, ValueError):
        return None
    if not decimal.is_finite():
        return None
    if decimal == 0:
        rendered = "0"
    else:
        rendered = format(decimal.normalize(), "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
    return decimal if value == rendered else None


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


def _canonical_sha256(value: Any) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("canonical_json_invalid") from exc
    return hashlib.sha256(encoded).hexdigest()


def _parse_utc(value: Any, reason: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(reason)
    raw = value.strip()
    if raw.endswith("Z"):
        raw = f"{raw[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise ValueError(reason) from exc
    if parsed.tzinfo is None:
        raise ValueError(reason)
    return parsed.astimezone(timezone.utc)


def _utc_z(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc)
    if normalized.microsecond:
        return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _positive_int(value: Any, reason: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(reason)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9a-f]{64}", value))

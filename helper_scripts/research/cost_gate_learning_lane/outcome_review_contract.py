"""Stable configuration and no-authority projection for outcome review."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any


BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION = (
    "cost_gate_demo_learning_lane_blocked_outcome_review_v6"
)
BLOCKED_OUTCOME_REVIEW_RECORD_TYPE = "blocked_signal_outcome_review"
RESEARCH_COMPATIBILITY_BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION = (
    "cost_gate_blocked_outcome_research_compatibility_no_authority_v1"
)
RESEARCH_COMPATIBILITY_BLOCKED_OUTCOME_REVIEW_RECORD_TYPE = (
    "blocked_signal_outcome_research_compatibility_no_authority"
)
RESEARCH_COMPATIBILITY_NO_AUTHORITY_BOUNDARY = (
    "research-only compatibility statistics; not v6 production evidence; "
    "not authority eligible; not operator-review eligible; not promotion "
    "evidence; no PG, Bybit, order, config, risk, auth, runtime mutation, "
    "or main Cost Gate lowering"
)


@dataclass(frozen=True)
class BlockedOutcomeReviewConfig:
    """Fail-closed thresholds for blocked-signal review candidates."""

    min_outcomes_per_side_cell: int = 3
    min_avg_net_bps: float = 0.0
    min_net_positive_pct: float = 60.0
    fdr_q: float = 0.10
    sign_flip_b: int = 1000
    min_effective_entries_per_side_cell: int = 30
    min_distinct_entry_utc_days: int = 5
    max_top_entry_day_share_pct: float = 50.0


def validate_blocked_outcome_review_config(
    cfg: BlockedOutcomeReviewConfig,
) -> None:
    if cfg.min_outcomes_per_side_cell < 1 or cfg.min_outcomes_per_side_cell > 1_000:
        raise ValueError("--min-outcomes-per-side-cell must be in [1, 1000]")
    if (
        cfg.min_effective_entries_per_side_cell < 1
        or cfg.min_effective_entries_per_side_cell > 1_000
    ):
        raise ValueError("--min-effective-entries-per-side-cell must be in [1, 1000]")
    if cfg.min_distinct_entry_utc_days < 1 or cfg.min_distinct_entry_utc_days > 365:
        raise ValueError("--min-distinct-entry-utc-days must be in [1, 365]")
    if not (0.0 < cfg.max_top_entry_day_share_pct <= 100.0):
        raise ValueError("--max-top-entry-day-share-pct must be in (0, 100]")
    if cfg.min_avg_net_bps < -10_000.0 or cfg.min_avg_net_bps > 10_000.0:
        raise ValueError("--min-avg-net-bps must be in [-10000, 10000]")
    if cfg.min_net_positive_pct < 0.0 or cfg.min_net_positive_pct > 100.0:
        raise ValueError("--min-net-positive-pct must be in [0, 100]")
    if not (0.0 < cfg.fdr_q < 1.0):
        raise ValueError("--fdr-q must be in (0, 1)")
    if cfg.sign_flip_b < 1 or cfg.sign_flip_b > 100_000:
        raise ValueError("--sign-flip-b must be in [1, 100000]")


def project_research_compatibility_review_no_authority(
    source_review: dict[str, Any],
) -> dict[str, Any]:
    """Remove production authority semantics from one legacy-statistics review."""
    review = copy.deepcopy(source_review)
    legacy_status = review["status"]
    legacy_reason = review["reason"]
    legacy_next_trigger = review["next_trigger"]
    legacy_candidate_count = int(review.get("review_candidate_side_cell_count") or 0)
    legacy_top_candidate_fields = {
        key: review.get(key)
        for key in tuple(review)
        if key.startswith("top_review_candidate_")
    }

    sanitized_cells: list[dict[str, Any]] = []
    for source_cell in review.get("top_side_cells") or []:
        cell = copy.deepcopy(source_cell)
        cell["research_only_legacy_status"] = cell.get("status")
        cell["research_only_legacy_review_candidate"] = bool(
            cell.get("review_candidate")
        )
        if cell["research_only_legacy_review_candidate"]:
            cell["status"] = "RESEARCH_COMPATIBILITY_CANDIDATE_NO_AUTHORITY"
        cell["review_candidate"] = False
        cell["bounded_demo_probe_review_rank"] = None
        cell["authority_eligible"] = False
        cell["operator_review_eligible"] = False
        cell["promotion_evidence"] = False
        sanitized_cells.append(cell)

    candidate_board = review.pop("learning_candidate_board", {}) or {}
    qualified_count = int(
        candidate_board.get("qualified_lineage_outcome_row_count") or 0
    )
    invalid_count = int(
        candidate_board.get("invalid_lineage_outcome_row_count") or 0
    )
    unqualified_count = int(
        candidate_board.get("unqualified_lineage_outcome_row_count") or 0
    )
    review.pop("strict_side_cell_reviews_by_key", None)
    review.update(
        {
            "schema_version": (
                RESEARCH_COMPATIBILITY_BLOCKED_OUTCOME_REVIEW_SCHEMA_VERSION
            ),
            "record_type": (
                RESEARCH_COMPATIBILITY_BLOCKED_OUTCOME_REVIEW_RECORD_TYPE
            ),
            "status": (
                "RESEARCH_COMPATIBILITY_METRICS_AVAILABLE_NO_AUTHORITY"
                if review.get("blocked_signal_outcome_count")
                else "RESEARCH_COMPATIBILITY_NO_OUTCOMES_NO_AUTHORITY"
            ),
            "reason": "legacy_rows_evaluated_for_research_statistics_only",
            "next_trigger": (
                "add_valid_prospective_candidate_lineage_for_production_review"
            ),
            "require_qualified_lineage": False,
            "outcome_aggregation_policy": (
                "FULL_LEDGER_RESEARCH_COMPATIBILITY_NO_AUTHORITY"
            ),
            "authority_eligible": False,
            "operator_review_eligible": False,
            "promotion_evidence": False,
            "review_candidate_side_cell_count": 0,
            "top_side_cells": sanitized_cells,
            "top_side_cell_status": (
                sanitized_cells[0].get("status") if sanitized_cells else None
            ),
            "top_review_candidate_side_cell_key": None,
            "top_review_candidate_learning_diagnosis": None,
            "top_review_candidate_cost_gate_escape_recommendation": None,
            "top_review_candidate_wrongful_block_score": None,
            "top_review_candidate_net_cost_cushion_bps": None,
            "research_only_legacy_status": legacy_status,
            "research_only_legacy_reason": legacy_reason,
            "research_only_legacy_next_trigger": legacy_next_trigger,
            "research_only_legacy_review_candidate_side_cell_count": (
                legacy_candidate_count
            ),
            "research_only_legacy_top_review_candidate_fields": (
                legacy_top_candidate_fields
            ),
            "candidate_lineage_audit": {
                "source_schema_version": candidate_board.get("schema_version"),
                "status": candidate_board.get("status"),
                "count_unit": "outcome_rows",
                "qualified_lineage_outcome_row_count": qualified_count,
                "invalid_lineage_outcome_row_count": invalid_count,
                "unqualified_lineage_outcome_row_count": unqualified_count,
                "qualified_candidate_count": qualified_count,
                "invalid_lineage_count": invalid_count,
                "unqualified_lineage_count": unqualified_count,
            },
            "boundary": RESEARCH_COMPATIBILITY_NO_AUTHORITY_BOUNDARY,
        }
    )
    headline = review.get("headline_selection")
    if isinstance(headline, dict):
        headline["research_only_legacy_headline_edge_language_allowed"] = bool(
            headline.get("headline_edge_language_allowed")
        )
        headline["headline_edge_language_allowed"] = False
    return review

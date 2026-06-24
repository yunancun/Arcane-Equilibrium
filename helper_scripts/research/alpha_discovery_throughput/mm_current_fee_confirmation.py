#!/usr/bin/env python3
"""Build an MM current-fee confirmation packet.

This artifact separates three different claims that used to blur together:
latest current-fee-positive maker cell, repeated independent-window evidence,
and OOS / maker execution realism. It is artifact-only: no PG query/write,
Bybit call, order placement, config / risk / auth / runtime mutation, Cost Gate
lowering, probe authority, or promotion authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "mm_current_fee_confirmation_packet_v1"
BOUNDARY = (
    "artifact-only MM current-fee confirmation packet; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate "
    "lowering, probe authority, or promotion authority"
)


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _round(value: Any, ndigits: int = 4) -> float | None:
    out = _float(value)
    return round(out, ndigits) if out is not None else None


def _cell_key(source: str, cell: dict[str, Any]) -> str:
    source = _str(source or cell.get("source") or "fillsim")
    if cell.get("key"):
        return _str(cell.get("key"))
    if cell.get("candidate_key"):
        return _str(cell.get("candidate_key"))
    if cell.get("motif_key"):
        return _str(cell.get("motif_key"))
    name = _str(cell.get("name") or cell.get("condition") or cell.get("feature"))
    if name:
        return "|".join([source, name])
    scope = _str(cell.get("scope"))
    if not scope and source == "edge_scorecard" and _str(cell.get("symbol")):
        scope = "per_symbol_primary_queue"
    return "|".join([
        source,
        scope or "global",
        _str(cell.get("symbol") or "pooled"),
        _str(cell.get("queue_position")),
        _str(cell.get("policy")),
        _str(cell.get("track")),
    ])


def _cell_rank(cell: dict[str, Any]) -> tuple[float, float, int]:
    edge = _float(cell.get("edge_before_fees_bps"))
    net = _float(cell.get("net_bps") or cell.get("net_bps_at_fee"))
    fills = _int(cell.get("n_fill_only") or cell.get("n"))
    return (
        net if net is not None else -1e9,
        edge if edge is not None else -1e9,
        fills,
    )


def _append_positive_cell(
    cells: list[dict[str, Any]],
    raw: dict[str, Any],
    *,
    source: str,
    net_key: str = "net_bps",
    current_fee_round_trip_bps: float | None = None,
) -> None:
    if not isinstance(raw, dict):
        return
    cell = dict(raw)
    net = _float(cell.get(net_key))
    edge = _float(cell.get("edge_before_fees_bps"))
    if net is None and current_fee_round_trip_bps is not None and edge is not None:
        net = edge - current_fee_round_trip_bps
    if net is None or net <= 0.0:
        return
    cell.setdefault("source", source)
    cell["net_bps"] = _round(net)
    cell.setdefault("key", _cell_key(source, cell))
    cells.append(cell)


def _current_fee_round_trip(
    fillsim: dict[str, Any] | None,
    gross_edge_cost_decomposition: dict[str, Any] | None,
) -> float | None:
    gross = _dict(gross_edge_cost_decomposition)
    fee = _dict(_dict(fillsim).get("maker_fee_sensitivity_scorecard"))
    return (
        _float(gross.get("current_fee_round_trip_bps"))
        or _float(fee.get("current_fee_round_trip_bps"))
        or (
            2.0 * _float(fee.get("current_maker_fee_bps_per_side"))
            if _float(fee.get("current_maker_fee_bps_per_side")) is not None
            else None
        )
    )


def _current_fee_positive_cells(
    fillsim: dict[str, Any] | None,
    gross_edge_cost_decomposition: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    payload = _dict(fillsim)
    gross = _dict(gross_edge_cost_decomposition)
    current_fee = _current_fee_round_trip(payload, gross)
    cells: list[dict[str, Any]] = []

    _append_positive_cell(
        cells,
        _dict(gross.get("best_sample_gated_current_fee_cell")),
        source=_str(_dict(gross.get("best_sample_gated_current_fee_cell")).get("source"))
        or "gross_edge_cost_decomposition",
        current_fee_round_trip_bps=current_fee,
    )
    _append_positive_cell(
        cells,
        _dict(gross.get("best_sample_gated_gross_cell")),
        source=_str(_dict(gross.get("best_sample_gated_gross_cell")).get("source"))
        or "gross_edge_cost_decomposition",
        current_fee_round_trip_bps=current_fee,
    )

    for source, field in (
        ("edge_scorecard", "positive_fill_only_cells_with_sample_gate"),
        ("conditional_feature_scorecard", "positive_cells_with_sample_gate"),
    ):
        for raw in _list(_dict(payload.get(source)).get(field)):
            _append_positive_cell(
                cells,
                raw,
                source=source,
                current_fee_round_trip_bps=current_fee,
            )

    fee = _dict(payload.get("maker_fee_sensitivity_scorecard"))
    current_maker_fee = _float(fee.get("current_maker_fee_bps_per_side"))
    best_break_even = _dict(fee.get("best_sample_gated_break_even_cell"))
    _append_positive_cell(
        cells,
        best_break_even,
        source=_str(best_break_even.get("source")) or "maker_fee_sensitivity_current_fee",
        current_fee_round_trip_bps=current_fee,
    )
    for scenario in _list(fee.get("scenarios")):
        if not isinstance(scenario, dict):
            continue
        scenario_fee = _float(scenario.get("maker_fee_bps_per_side"))
        if (
            current_maker_fee is not None
            and scenario_fee is not None
            and abs(scenario_fee - current_maker_fee) > 1e-9
        ):
            continue
        for raw in _list(scenario.get("positive_sample_gate_cells")):
            _append_positive_cell(
                cells,
                raw,
                source=_str(_dict(raw).get("source"))
                or "maker_fee_sensitivity_current_fee",
                net_key="net_bps_at_fee",
                current_fee_round_trip_bps=current_fee,
            )

    merged: dict[str, dict[str, Any]] = {}
    for cell in cells:
        key = _cell_key(_str(cell.get("source")) or "fillsim", cell)
        cell["key"] = key
        previous = merged.get(key)
        if previous is None:
            merged[key] = cell
            continue
        if _cell_rank(cell) > _cell_rank(previous):
            primary, secondary = cell, previous
        else:
            primary, secondary = previous, cell
        enriched = dict(primary)
        for field, value in secondary.items():
            if enriched.get(field) in (None, "") and value not in (None, ""):
                enriched[field] = value
        merged[key] = enriched
    out = list(merged.values())
    out.sort(key=_cell_rank, reverse=True)
    return out


def _history_positive_cells(fillsim_history: dict[str, Any] | None) -> list[dict[str, Any]]:
    history = _dict(fillsim_history)
    cells: list[dict[str, Any]] = []
    for row in _list(history.get("repeated_positive_keys")):
        if not isinstance(row, dict):
            continue
        cell = _dict(row.get("best_cell"))
        if not cell:
            continue
        cell = dict(cell)
        cell.setdefault("source", _str(cell.get("source")) or "history_repeated_positive")
        cell.setdefault("key", _str(row.get("key")) or _cell_key(cell["source"], cell))
        cell["history_repeat_windows"] = row.get("windows")
        cell["history_distinct_window_dates"] = row.get("distinct_window_dates")
        cells.append(cell)
    best_window = _dict(history.get("best_sample_gated_break_even_window"))
    best_cell = _dict(best_window.get("cell") or best_window.get("best_cell"))
    if best_cell and (_float(best_cell.get("net_bps")) or 0.0) > 0.0:
        cell = dict(best_cell)
        cell.setdefault("source", _str(cell.get("source")) or "history_best_current_fee")
        cell.setdefault("key", _cell_key(cell["source"], cell))
        cells.append(cell)
    return cells


def _matching_repeated_key(
    fillsim_history: dict[str, Any] | None,
    candidate_key: str,
) -> dict[str, Any]:
    if not candidate_key:
        return {}
    for row in _list(_dict(fillsim_history).get("repeated_positive_keys")):
        if isinstance(row, dict) and _str(row.get("key")) == candidate_key:
            return row
    return {}


_AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "auth_mutated",
    "bybit_call_performed",
    "crontab_mutated",
    "deploy_performed",
    "global_cost_gate_lowering_recommended",
    "live_promotion",
    "order_authority_granted",
    "order_cancelled",
    "order_modified",
    "order_submitted",
    "pg_schema_mutated",
    "pg_write_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutated",
    "runtime_env_mutated",
    "runtime_mutation_performed",
    "runtime_mutated",
    "rust_writer_enabled",
    "service_restarted",
    "service_restart_performed",
    "strategy_mutated",
}

_AUTHORITY_NON_NONE_KEYS = {
    "active_authority",
    "active_runtime_authority",
    "auth_mutation",
    "bybit_call",
    "crontab_mutation",
    "live_authority",
    "main_cost_gate_adjustment",
    "operator_authorization",
    "order_authority",
    "order_mutation",
    "pg_write",
    "probe_authority",
    "risk_mutation",
    "runtime_authority",
    "runtime_mutation",
    "rust_writer",
    "service_mutation",
    "strategy_mutation",
}

_AUTHORITY_NONE_VALUES = {
    "",
    "0",
    "ABSENT",
    "FALSE",
    "N/A",
    "NO",
    "NONE",
    "NOT_APPLICABLE",
    "NOT_GRANTED",
    "NULL",
}


def _authority_value_present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().upper() not in _AUTHORITY_NONE_VALUES
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return bool(value)


def _contains_authority_signal(value: Any, path: str = "") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_str = str(key)
            key_path = f"{path}.{key_str}" if path else key_str
            key_lower = key_str.lower()
            if key_lower in _AUTHORITY_TRUE_KEYS and item is True:
                return key_path
            if (
                key_lower in _AUTHORITY_NON_NONE_KEYS
                and _authority_value_present(item)
            ):
                return key_path
            found = _contains_authority_signal(item, key_path)
            if found:
                return found
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            found = _contains_authority_signal(item, f"{path}[{idx}]")
            if found:
                return found
    return None


def _history_cell_is_valid_candidate_evidence(
    cell: dict[str, Any],
    candidate: dict[str, Any],
    candidate_key: str,
) -> bool:
    if _str(cell.get("key")) != candidate_key:
        return False
    if (_float(cell.get("net_bps") or cell.get("net_bps_at_fee")) or 0.0) <= 0.0:
        return False
    if _int(cell.get("n_fill_only") or cell.get("n")) <= 0:
        return False
    for field in ("source", "scope", "symbol", "queue_position", "policy", "track"):
        candidate_value = _str(candidate.get(field))
        if candidate_value and _str(cell.get(field)) != candidate_value:
            return False
    return True


def _candidate_history_observations(
    fillsim_history: dict[str, Any] | None,
    candidate: dict[str, Any],
    candidate_key: str,
) -> dict[str, Any]:
    history = _dict(fillsim_history)
    summaries = _list(history.get("window_summaries"))
    observations: list[dict[str, Any]] = []
    malformed_sources: list[str] = []
    seen_sources: set[str] = set()
    for idx, window in enumerate(summaries):
        if not isinstance(window, dict) or window.get("valid") is not True:
            continue
        matched_cell = None
        malformed_cell = None
        for cell in _list(window.get("current_fee_sample_gated_positive_cells")):
            if not isinstance(cell, dict) or _str(cell.get("key")) != candidate_key:
                continue
            if _history_cell_is_valid_candidate_evidence(
                cell,
                candidate,
                candidate_key,
            ):
                matched_cell = cell
                break
            malformed_cell = cell
        if matched_cell is None:
            if malformed_cell is not None:
                malformed_sources.append(
                    _str(window.get("source_path")) or f"window_index:{idx}"
                )
            continue
        source_path = _str(window.get("source_path"))
        dedupe_key = source_path or f"window_index:{idx}"
        if dedupe_key in seen_sources:
            continue
        seen_sources.add(dedupe_key)
        observations.append({
            "source_path": source_path or None,
            "generated_at": window.get("generated_at"),
            "window_date": window.get("window_date"),
            "net_bps": matched_cell.get("net_bps"),
            "edge_before_fees_bps": matched_cell.get("edge_before_fees_bps"),
            "n_fill_only": matched_cell.get("n_fill_only") or matched_cell.get("n"),
        })
    distinct_dates = sorted({
        _str(row.get("window_date"))
        for row in observations
        if _str(row.get("window_date"))
    })
    return {
        "history_window_summary_present": bool(summaries),
        "candidate_observed_windows": len(observations),
        "candidate_observed_distinct_dates": distinct_dates,
        "candidate_observed_independent_windows": len(distinct_dates),
        "candidate_observation_sources": [
            row.get("source_path")
            for row in observations
            if row.get("source_path")
        ],
        "candidate_observations": observations[:10],
        "candidate_malformed_window_cell_count": len(malformed_sources),
        "candidate_malformed_window_cell_sources": malformed_sources[:10],
    }


def _repeat_window_design(
    *,
    candidate_key: str,
    status: str,
    history: dict[str, Any],
    repeated: dict[str, Any],
    observations: dict[str, Any],
) -> dict[str, Any]:
    thresholds = _dict(history.get("thresholds"))
    min_repeat = max(2, _int(thresholds.get("min_repeat_positive_windows"), 2))
    observed_independent = _int(observations.get("candidate_observed_independent_windows"))
    observed_dates = _list(observations.get("candidate_observed_distinct_dates"))
    reported_repeat_windows = _int(repeated.get("windows"))
    reported_repeat_confirmed = reported_repeat_windows >= min_repeat
    observed_repeat_confirmed = observed_independent >= min_repeat
    if not candidate_key:
        design_status = "NO_CURRENT_FEE_CANDIDATE"
        consistency_status = "not_applicable"
        next_action = "continue_mm_signal_search_for_current_fee_positive_cell"
    elif not observations.get("history_window_summary_present"):
        design_status = "HISTORY_WINDOW_SUMMARIES_REQUIRED"
        consistency_status = "window_summaries_missing"
        next_action = "rebuild_fill_sim_history_scorecard_with_window_summaries"
    elif observations.get("candidate_malformed_window_cell_count"):
        design_status = "HISTORY_WINDOW_SUMMARIES_MALFORMED"
        consistency_status = "window_summaries_malformed"
        next_action = "rebuild_or_refresh_fill_sim_history_before_repeat_claim"
    elif reported_repeat_confirmed != observed_repeat_confirmed:
        design_status = "HISTORY_REBUILD_REQUIRED"
        consistency_status = "reported_repeats_disagree_with_window_summaries"
        next_action = "rebuild_or_refresh_fill_sim_history_before_repeat_claim"
    elif observed_repeat_confirmed:
        design_status = "REPEAT_WINDOW_CONFIRMED_ADVANCE_TO_NEXT_GATE"
        consistency_status = "consistent"
        next_action = "advance_to_oos_walk_forward_confirmation_without_order_authority"
    elif status == "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW":
        design_status = "REPEAT_WINDOW_SAFE_TEST_READY"
        consistency_status = "consistent"
        next_action = "accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell"
    else:
        design_status = "REPEAT_WINDOW_NOT_CURRENT_BLOCKER"
        consistency_status = "consistent"
        next_action = "follow_mm_current_fee_confirmation_packet_next_action"

    remaining = max(min_repeat - observed_independent, 0)
    return {
        "status": design_status,
        "consistency_status": consistency_status,
        "candidate_key": candidate_key or None,
        "candidate_observed_windows": observations.get("candidate_observed_windows"),
        "candidate_observed_independent_windows": observed_independent,
        "candidate_observed_distinct_dates": observed_dates,
        "candidate_observation_sources": observations.get("candidate_observation_sources"),
        "candidate_malformed_window_cell_count": (
            observations.get("candidate_malformed_window_cell_count")
        ),
        "candidate_malformed_window_cell_sources": (
            observations.get("candidate_malformed_window_cell_sources")
        ),
        "reported_candidate_repeat_windows": reported_repeat_windows,
        "required_same_candidate_independent_windows": min_repeat,
        "same_candidate_independent_windows_remaining": remaining,
        "required_distinct_dates_for_repeat": min_repeat,
        "same_candidate_distinct_dates_remaining": remaining,
        "history_window_summary_present": observations.get("history_window_summary_present"),
        "fastest_safe_test": (
            "wait_for_next_valid_fill_sim_refresh_or_run_isolated_read_only_replay_"
            "for_exact_candidate_key"
        ),
        "required_data": [
            "valid fill_sim report with non-empty fresh L1",
            "fill_sim_history_scorecard.window_summaries",
            "exact candidate_key match across independent window dates",
            "current fee round-trip cost preserved",
        ],
        "failure_condition": [
            "same candidate_key does not repeat across independent dates",
            "repeat evidence only matches symbol/policy but not exact key",
            "window_summaries missing or inconsistent with repeated_positive_keys",
            "exact-key window cell is missing positive net, sample, or identity fields",
            "future OOS or maker execution realism fails after repeat",
        ],
        "authority_required": (
            "none for read-only repeat-window evidence; operator review required "
            "before any future probe/order authority"
        ),
        "max_safe_next_action": next_action,
    }


def _maker_execution_realism_confirmed(payload: dict[str, Any] | None) -> bool:
    review = _dict(payload)
    answers = _dict(review.get("answers"))
    status = _str(review.get("status")).upper()
    if answers.get("maker_execution_realism_confirmed") is True:
        return True
    if answers.get("execution_realism_confirmed") is True:
        return True
    return status in {
        "MAKER_EXECUTION_REALISM_PASS",
        "MM_MAKER_EXECUTION_REALISM_PASS",
        "EXECUTION_REALISM_PASS",
    }


def _maker_execution_realism_status(
    *,
    repeated: bool,
    oos_confirmed: bool,
    maker_execution_realism: dict[str, Any] | None,
) -> str:
    if _maker_execution_realism_confirmed(maker_execution_realism):
        return "CONFIRMED"
    if not repeated:
        return "NOT_REACHED_REPEAT_WINDOW_REQUIRED"
    if not oos_confirmed:
        return "NOT_REACHED_OOS_REQUIRED"
    if maker_execution_realism:
        return _str(maker_execution_realism.get("status")) or "REVIEW_PRESENT_NOT_CONFIRMED"
    return "MISSING_MAKER_EXECUTION_REALISM_REVIEW"


def build_mm_current_fee_confirmation_packet(
    *,
    fillsim: dict[str, Any] | None = None,
    fillsim_history: dict[str, Any] | None = None,
    gross_edge_cost_decomposition: dict[str, Any] | None = None,
    maker_execution_realism: dict[str, Any] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    authority_violation = (
        _contains_authority_signal(fillsim, "fillsim")
        or _contains_authority_signal(fillsim_history, "fillsim_history")
        or _contains_authority_signal(
            gross_edge_cost_decomposition,
            "gross_edge_cost_decomposition",
        )
        or _contains_authority_signal(maker_execution_realism, "maker_execution_realism")
    )
    history = _dict(fillsim_history)
    cells = _current_fee_positive_cells(fillsim, gross_edge_cost_decomposition)
    cells.extend(_history_positive_cells(fillsim_history))
    cells = [cell for cell in cells if (_float(cell.get("net_bps")) or 0.0) > 0.0]
    cells.sort(key=_cell_rank, reverse=True)
    candidate = cells[0] if cells else {}
    candidate_key = _str(candidate.get("key"))
    repeated = _matching_repeated_key(history, candidate_key)
    observations = _candidate_history_observations(history, candidate, candidate_key)
    thresholds = _dict(history.get("thresholds"))
    min_repeat = max(2, _int(thresholds.get("min_repeat_positive_windows"), 2))
    repeated_key_count = len(_list(history.get("repeated_positive_keys")))
    candidate_repeat_windows = _int(
        repeated.get("windows") or candidate.get("history_repeat_windows")
    )
    candidate_observed_independent_windows = _int(
        observations.get("candidate_observed_independent_windows")
    )
    reported_repeat_confirmed = candidate_repeat_windows >= min_repeat
    observed_repeat_confirmed = candidate_observed_independent_windows >= min_repeat
    repeat_consistency_violation = bool(
        candidate_key
        and observations.get("history_window_summary_present")
        and reported_repeat_confirmed != observed_repeat_confirmed
    )
    malformed_window_summaries = bool(
        candidate_key and observations.get("candidate_malformed_window_cell_count")
    )
    current_fee_positive_windows = _int(
        history.get("current_fee_sample_gated_positive_windows")
    )
    walk_forward_holdout_windows = _int(
        history.get("walk_forward_holdout_confirmed_windows")
    )
    repeat_confirmed = bool(
        candidate_key
        and observations.get("history_window_summary_present")
        and observed_repeat_confirmed
        and not malformed_window_summaries
        and not repeat_consistency_violation
    )
    history_status = _str(history.get("status")).upper()
    oos_confirmed = bool(
        repeat_confirmed
        and (
            history_status == "HISTORY_REPEAT_HOLDOUT_OR_CURRENT_FEE_POSITIVE"
            or walk_forward_holdout_windows > 0
        )
    )
    maker_status = _maker_execution_realism_status(
        repeated=repeat_confirmed,
        oos_confirmed=oos_confirmed,
        maker_execution_realism=maker_execution_realism,
    )
    maker_confirmed = maker_status == "CONFIRMED"

    if authority_violation:
        status = "AUTHORITY_BOUNDARY_VIOLATION"
        reason = f"authority_or_proof_signal_in_input:{authority_violation}"
        next_action = "repair_inputs_remove_authority_bearing_mm_artifacts"
        next_gate = "no_authority_inputs_before_repeat_window_design"
    elif not candidate:
        status = "NO_CURRENT_FEE_POSITIVE_MM_CELL"
        reason = "no_current_fee_positive_sample_gated_mm_cell"
        next_action = "continue_mm_signal_search_for_current_fee_positive_cell"
        next_gate = "current_fee_positive_sample_gated_mm_cell"
    elif malformed_window_summaries:
        status = "MM_CURRENT_FEE_CONFIRMATION_HISTORY_REBUILD_REQUIRED"
        reason = "fill_sim_history_window_summaries_malformed_for_candidate"
        next_action = "rebuild_or_refresh_fill_sim_history_before_repeat_claim"
        next_gate = "valid_same_candidate_window_summaries"
    elif repeat_consistency_violation:
        status = "MM_CURRENT_FEE_CONFIRMATION_HISTORY_REBUILD_REQUIRED"
        reason = "repeated_positive_keys_disagree_with_window_summaries"
        next_action = "rebuild_or_refresh_fill_sim_history_before_repeat_claim"
        next_gate = "consistent_same_candidate_window_summaries"
    elif candidate_key and not observations.get("history_window_summary_present"):
        status = "MM_CURRENT_FEE_CONFIRMATION_HISTORY_WINDOW_SUMMARIES_REQUIRED"
        reason = "fill_sim_history_window_summaries_missing"
        next_action = "rebuild_fill_sim_history_scorecard_with_window_summaries"
        next_gate = "same_candidate_window_summary_evidence"
    elif not repeat_confirmed:
        status = "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_REPEAT_WINDOW"
        reason = "candidate_not_repeated_across_independent_history_windows"
        next_action = "accumulate_or_replay_independent_windows_for_same_current_fee_mm_cell"
        next_gate = "same_current_fee_positive_cell_repeats_across_independent_windows"
    elif not oos_confirmed:
        status = "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_OOS"
        reason = "repeated_current_fee_cell_lacks_walk_forward_holdout_confirmation"
        next_action = "build_oos_walk_forward_confirmation_for_repeated_current_fee_mm_cell"
        next_gate = "walk_forward_oos_confirmation_without_train_only_leakage"
    elif not maker_confirmed:
        status = "MM_CURRENT_FEE_CONFIRMATION_REQUIRES_MAKER_EXECUTION_REALISM"
        reason = "repeated_oos_current_fee_cell_lacks_maker_execution_realism"
        next_action = "measure_maker_fill_probability_adverse_selection_fee_and_inventory_risk"
        next_gate = "maker_execution_realism_confirms_capture_after_cost"
    else:
        status = "MM_CURRENT_FEE_CONFIRMATION_READY_FOR_OPERATOR_REVIEW"
        reason = "repeat_oos_and_maker_execution_realism_confirmed"
        next_action = "operator_review_mm_current_fee_confirmation_without_runtime_authority"
        next_gate = "operator_review_before_any_probe_or_order_authority"

    current_fee_round_trip = _current_fee_round_trip(
        fillsim,
        gross_edge_cost_decomposition,
    )
    summary = {
        "candidate_key": candidate_key or None,
        "candidate_source": candidate.get("source"),
        "candidate_symbol": candidate.get("symbol"),
        "candidate_policy": candidate.get("policy"),
        "candidate_queue_position": candidate.get("queue_position"),
        "candidate_track": candidate.get("track"),
        "candidate_n_fill_only": candidate.get("n_fill_only") or candidate.get("n"),
        "candidate_edge_before_fees_bps": _round(candidate.get("edge_before_fees_bps")),
        "candidate_net_bps": _round(candidate.get("net_bps") or candidate.get("net_bps_at_fee")),
        "candidate_break_even_maker_fee_bps_per_side": _round(
            candidate.get("break_even_maker_fee_bps_per_side")
        ),
        "current_fee_round_trip_bps": _round(current_fee_round_trip),
        "current_fee_positive_candidate_count": len(cells),
        "history_status": history.get("status"),
        "history_reason": history.get("reason"),
        "history_valid_windows": history.get("valid_windows"),
        "history_distinct_window_dates": history.get("distinct_window_dates"),
        "history_current_fee_sample_gated_positive_windows": current_fee_positive_windows,
        "history_repeated_positive_key_count": repeated_key_count,
        "history_walk_forward_holdout_confirmed_windows": walk_forward_holdout_windows,
        "candidate_repeated_windows": candidate_repeat_windows,
        "candidate_observed_windows": observations.get("candidate_observed_windows"),
        "candidate_observed_independent_windows": (
            candidate_observed_independent_windows
        ),
        "candidate_observed_distinct_dates": (
            observations.get("candidate_observed_distinct_dates")
        ),
        "candidate_malformed_window_cell_count": (
            observations.get("candidate_malformed_window_cell_count")
        ),
        "candidate_malformed_window_cell_sources": (
            observations.get("candidate_malformed_window_cell_sources")
        ),
        "repeat_window_design_status": None,
        "repeat_window_consistency_status": None,
        "same_candidate_independent_windows_remaining": None,
        "candidate_repeated_window_sources": repeated.get("window_sources"),
        "candidate_distinct_window_dates": (
            repeated.get("distinct_window_dates")
            or candidate.get("history_distinct_window_dates")
        ),
        "repeat_window_confirmed": repeat_confirmed,
        "oos_walk_forward_confirmed": oos_confirmed,
        "maker_execution_realism_status": maker_status,
        "maker_execution_realism_confirmed": maker_confirmed,
    }
    repeat_window_design = _repeat_window_design(
        candidate_key=candidate_key,
        status=status,
        history=history,
        repeated=repeated,
        observations=observations,
    )
    summary["repeat_window_design_status"] = repeat_window_design.get("status")
    summary["repeat_window_consistency_status"] = repeat_window_design.get(
        "consistency_status"
    )
    summary["same_candidate_independent_windows_remaining"] = (
        repeat_window_design.get("same_candidate_independent_windows_remaining")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_action": next_action,
        "next_gate": next_gate,
        "summary": summary,
        "candidate": candidate or None,
        "repeat_window_design": repeat_window_design,
        "top_current_fee_positive_cells": cells[:10],
        "answers": {
            "current_fee_positive_candidate_present": bool(candidate),
            "repeat_window_confirmed": repeat_confirmed,
            "oos_walk_forward_confirmed": oos_confirmed,
            "maker_execution_realism_confirmed": maker_confirmed,
            "ready_for_operator_review": status == "MM_CURRENT_FEE_CONFIRMATION_READY_FOR_OPERATOR_REVIEW",
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "order_authority_granted": False,
            "probe_authority_granted": False,
            "promotion_evidence": False,
        },
        "global_boundaries": {
            "order_authority": "NOT_GRANTED",
            "probe_authority": "NOT_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "runtime_mutation": "NONE",
            "promotion_evidence": False,
            "boundary": BOUNDARY,
        },
    }


def render_markdown(packet: dict[str, Any]) -> str:
    def cell(value: Any) -> str:
        return str(value).replace("|", "\\|")

    lines = [
        "# MM Current-Fee Confirmation Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Next action: `{packet.get('next_action')}`",
        "- Boundary: artifact-only; no order authority, no probe authority, no Cost Gate lowering.",
        "",
        "## Summary",
        "",
        "| field | value |",
        "|---|---|",
    ]
    for key, value in _dict(packet.get("summary")).items():
        lines.append(f"| {key} | `{cell(value)}` |")
    lines.extend([
        "",
        "## Top Cells",
        "",
        "| rank | key | source | symbol | net_bps | edge_bps | fills |",
        "|---:|---|---|---|---:|---:|---:|",
    ])
    for idx, row in enumerate(_list(packet.get("top_current_fee_positive_cells")), start=1):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| "
            f"{idx} | {cell(row.get('key'))} | {cell(row.get('source'))} | "
            f"{cell(row.get('symbol'))} | {row.get('net_bps')} | "
            f"{row.get('edge_before_fees_bps')} | "
            f"{row.get('n_fill_only') or row.get('n')} |"
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fillsim-json", type=Path)
    parser.add_argument("--fillsim-history-json", type=Path)
    parser.add_argument("--gross-edge-cost-decomposition-json", type=Path)
    parser.add_argument("--maker-execution-realism-json", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_mm_current_fee_confirmation_packet(
        fillsim=_read_json(args.fillsim_json),
        fillsim_history=_read_json(args.fillsim_history_json),
        gross_edge_cost_decomposition=_read_json(args.gross_edge_cost_decomposition_json),
        maker_execution_realism=_read_json(args.maker_execution_realism_json),
    )
    if args.output:
        _write_text(args.output, render_markdown(packet))
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not (args.output or args.json_output or args.print_json):
        print(render_markdown(packet), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

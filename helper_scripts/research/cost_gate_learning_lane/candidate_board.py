"""Build canonical candidate evidence boards from blocked-outcome ledger rows.

This Module owns candidate identity, board construction, and canonical hashing.
The frozen validation contract lives in ``candidate_board_validation``.
Statistical/cost methodology remains in
``outcome_review`` and enters through the narrow ``CandidateCohortEvaluator``
Interface, so this Module never imports its caller.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections.abc import Mapping
from typing import Any, Protocol, TypedDict

from cost_gate_learning_lane.candidate_evaluation_context import (
    CandidateEvaluationContextError,
    attach_candidate_evaluation_context,
    candidate_learning_context_projection,
    validate_candidate_event_context,
    validate_candidate_evaluation_context,
)
from cost_gate_learning_lane.candidate_board_validation import (
    ARBITER_INPUT_SCHEMA_VERSION,
    COST_EVIDENCE_SCHEMA_VERSION,
    LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION,
    LEARNING_CANDIDATE_SCHEMA_VERSION,
    _AUDIT_SCHEMA_VERSION,
    _CANDIDATE_FAMILY_SCHEMA_VERSION,
    _REGIME_BUCKETS,
    _SELECTION_FIELDS,
    _SELECTION_N_EFF_MIN,
    _SELECTION_SCHEMA_VERSION,
    _SELECTION_TOP_DAY_SHARE_MAX_PCT,
    _SELECTION_UTC_DAYS_MIN,
    validate_learning_candidate_board_v2,
)
from cost_gate_learning_lane.cost_model import (
    FEE_FLOOR_BPS,
    MIN_SYMBOL_FILLS_FOR_QUANTILE,
    QUANTILE_ARTIFACT_MAX_AGE_HOURS,
)
from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE


_DUPLICATE_EXACT_FIELDS = tuple("""
record_type attempt_id side_cell_key strategy_name symbol side event_ts_ms horizon_minutes
censored censor_reason entry_ts_ms exit_ts_ms last_observation_ts_ms outcome_source
cost_model_version cost_model_source funding_crossings exit_delay_ms entry_price exit_price
""".split())
_DUPLICATE_BPS_FIELDS = tuple("""
gross_bps cost_bps realized_net_bps cost_bps_optimistic net_bps_optimistic slippage_bps
funding_drag_bps
""".split())


class CandidateBoardConfig(Protocol):
    min_effective_entries_per_side_cell: int
    min_distinct_entry_utc_days: int
    max_top_entry_day_share_pct: float


class CandidateCohortEvaluation(TypedDict):
    censored_count: int
    uncensored_row_count: int
    metrics: dict[str, Any]
    entries: list[dict[str, Any]]


class CandidateCohortEvaluator(Protocol):
    def __call__(
        self,
        side_cell_key: str,
        rows: list[dict[str, Any]],
        *,
        cfg: CandidateBoardConfig,
        overlay: dict[str, dict[str, Any]],
        edge_estimates: dict[str, dict[str, Any]],
        expected_slippage: dict[str, Any] | None,
    ) -> CandidateCohortEvaluation: ...


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def candidate_learning_context(row: dict[str, Any]) -> dict[str, Any] | None:
    summary = row.get("candidate_summary")
    if not isinstance(summary, dict):
        return None
    context = summary.get("candidate_learning_context")
    return dict(context) if isinstance(context, dict) else None


def _exact_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _sha256_text(value: Any) -> bool:
    return bool(_exact_text(value) and len(value) == 64
                and all(char in "0123456789abcdef" for char in value))


def _git_sha_text(value: Any) -> bool:
    return bool(
        _exact_text(value)
        and len(value) == 40
        and all(char in "0123456789abcdef" for char in value)
    )


def _candidate_identity_blockers(
    identity: dict[str, Any], *, as_of_date: dt.date
) -> list[str]:
    blockers = []
    for key, code in (
        ("strategy_name", "STRATEGY_NAME_MISSING_OR_INVALID"),
        ("strategy_version", "STRATEGY_VERSION_MISSING_OR_INVALID"),
        ("symbol", "SYMBOL_MISSING_OR_INVALID"),
        ("venue", "VENUE_MISSING_OR_INVALID"),
        ("product", "PRODUCT_MISSING_OR_INVALID"),
    ):
        if not _exact_text(identity.get(key)):
            blockers.append(code)
    if not _sha256_text(identity.get("strategy_config_hash")):
        blockers.append("STRATEGY_CONFIG_HASH_MISSING_OR_INVALID")
    if not _sha256_text(identity.get("target_regime_hash")):
        blockers.append("TARGET_REGIME_HASH_MISSING_OR_INVALID")
    if identity.get("side") not in {"Buy", "Sell"}:
        blockers.append("SIDE_MISSING_OR_INVALID")
    if identity.get("engine_mode") != "shadow":
        blockers.append("ARBITER_ENGINE_MODE_NOT_SHADOW")
    if identity.get("evidence_engine_mode") not in {"demo", "live_demo"}:
        blockers.append("EVIDENCE_ENGINE_MODE_MISSING_OR_INVALID")
    horizon = identity.get("horizon_minutes")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or not 1 <= horizon <= 1440:
        blockers.append("HORIZON_MISSING_OR_INVALID")
    context = identity.get("target_regime_context")
    try:
        regime_date = dt.date.fromisoformat(str(context.get("utc_date")))
        valid_context = bool(isinstance(context, dict)
                             and _exact_text(context.get("label"))
                             and regime_date == as_of_date - dt.timedelta(days=1)
                             and context.get("point_in_time") == "D-1")
    except (AttributeError, ValueError):
        valid_context = False
    if not valid_context:
        blockers.append("TARGET_REGIME_CONTEXT_MISSING_OR_INVALID")
    return blockers


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _typed_context_parts(context: dict[str, Any] | None, *, as_of_date: dt.date
                         ) -> tuple[dict[str, Any], dict[str, Any] | None,
                                    dict[str, Any] | None, dict[str, Any], bool | None,
                                    list[str]]:
    """驗證 typed context 結構；缺欄原樣留空，不生成替代證據。"""
    source = context or {}
    blockers = [] if context is not None else ["CANDIDATE_LEARNING_CONTEXT_MISSING"]
    raw_hashes = source.get("context_hashes")
    raw_hashes = raw_hashes if isinstance(raw_hashes, dict) else {}
    hashes = {key: raw_hashes.get(key) for key in ("data", "evidence", "cost", "portfolio")}
    for key in hashes:
        if not _sha256_text(hashes[key]):
            blockers.append(f"{key.upper()}_CONTEXT_HASH_MISSING_OR_INVALID")

    resource = source.get("resource")
    resource = dict(resource) if isinstance(resource, dict) else None
    buckets = resource.get("daily_buckets") if resource else None
    valid_buckets = isinstance(buckets, list) and len(buckets) == 7
    if valid_buckets:
        seen_dates = set()
        observed_dates = []
        for bucket in buckets:
            try:
                date_value = dt.date.fromisoformat(str(bucket["utc_date"]))
                valid_bucket = bool(isinstance(bucket, dict)
                    and set(bucket) == {"utc_date", "scan_complete", "distinct_entries"}
                    and bucket.get("scan_complete") is True
                    and isinstance(bucket.get("distinct_entries"), int)
                    and not isinstance(bucket.get("distinct_entries"), bool)
                    and bucket["distinct_entries"] >= 0)
            except (KeyError, TypeError, ValueError):
                valid_bucket = False
                date_value = None
            if not valid_bucket or date_value in seen_dates:
                valid_buckets = False
                break
            seen_dates.add(date_value)
            observed_dates.append(date_value)
        expected_dates = [as_of_date - dt.timedelta(days=n) for n in range(7, 0, -1)]
        valid_buckets = valid_buckets and observed_dates == expected_dates
    if not valid_buckets:
        blockers.append("RESOURCE_DAILY_BUCKETS_INCOMPLETE")
    estimator_payload = {
        "daily_buckets": buckets,
        "estimated_rows_scanned": resource.get("estimated_rows_scanned") if resource else None,
        "predicted_canonical_bytes": resource.get("predicted_canonical_bytes") if resource else None,
        "zero_resource_attested": resource.get("zero_resource_attested") if resource else None,
    }
    resource_totals_valid = bool(
        resource
        and set(resource) == {"daily_buckets", "estimated_rows_scanned",
                              "predicted_canonical_bytes", "zero_resource_attested",
                              "resource_estimator_hash"}
        and isinstance(resource.get("estimated_rows_scanned"), int)
        and not isinstance(resource.get("estimated_rows_scanned"), bool)
        and resource["estimated_rows_scanned"] >= 0
        and isinstance(resource.get("predicted_canonical_bytes"), int)
        and not isinstance(resource.get("predicted_canonical_bytes"), bool)
        and resource["predicted_canonical_bytes"] >= 0
        and isinstance(resource.get("zero_resource_attested"), bool)
    )
    estimator_hash_valid = bool(resource_totals_valid and valid_buckets
        and _sha256_text(resource.get("resource_estimator_hash"))
        and resource["resource_estimator_hash"] == _canonical_sha256(estimator_payload))
    if not estimator_hash_valid:
        blockers.append("RESOURCE_ESTIMATOR_HASH_MISSING_OR_INVALID")

    portfolio = source.get("portfolio")
    portfolio = dict(portfolio) if isinstance(portfolio, dict) else None
    portfolio_values = [_float(portfolio.get(key)) if portfolio else None for key in
                        ("sector_exposure_share", "strategy_active_target_share",
                         "beta_to_portfolio")]
    if (any(value is None for value in portfolio_values)
            or not 0.0 <= portfolio_values[0] <= 1.0
            or not 0.0 <= portfolio_values[1] <= 1.0):
        blockers.append("PORTFOLIO_METRICS_MISSING_OR_INVALID")

    raw_proof = source.get("proof")
    raw_proof = raw_proof if isinstance(raw_proof, dict) else {}
    stage = raw_proof.get("proof_stage")
    stages = raw_proof.get("completed_proof_stages")
    prefix_ok = bool(isinstance(stage, int) and not isinstance(stage, bool)
                     and 0 <= stage <= 6 and isinstance(stages, list)
                     and stages == list(range(stage + 1)))
    if not prefix_ok:
        blockers.append("PROOF_PREFIX_MISSING_OR_INVALID")
    gap = raw_proof.get("next_gap")
    gap_ok = bool(isinstance(gap, dict) and gap.get("kind") in
                  {"NONE", "LOCAL_PASSIVE", "LOCAL_ENGINEERING", "EXTERNAL_OPERATOR"}
                  and _exact_text(gap.get("code")))
    if not gap_ok:
        blockers.append("NEXT_GAP_MISSING_OR_INVALID")
    hidden_oos_consumed = source.get("hidden_oos_consumed")
    if not isinstance(hidden_oos_consumed, bool):
        blockers.append("HIDDEN_OOS_STATUS_MISSING_OR_INVALID")
        hidden_oos_consumed = None
    proof = {
        "proof_stage": stage,
        "completed_proof_stages": list(stages) if isinstance(stages, list) else None,
        "next_gap": dict(gap) if isinstance(gap, dict) else None,
    }
    return hashes, resource, portfolio, proof, hidden_oos_consumed, blockers


def _day_cluster_stats(entries: list[dict[str, Any]], *, expected_track_on: bool
                       ) -> dict[str, Any]:
    key = "net_expected" if expected_track_on else "net_conservative"
    values = [entry[key] for entry in entries]
    if not values or any(value is None for value in values):
        return {"mean": None, "variance": None, "se": None, "g": 0, "clean": False}
    mean = sum(values) / len(values)
    sums: dict[str, float] = {}
    for value, entry in zip(values, entries):
        day = entry["entry_utc_day"]
        sums[day] = sums.get(day, 0.0) + value - mean
    g = len(sums)
    variance = ((g / (g - 1)) * sum(v * v for v in sums.values()) / len(values) ** 2
                if g >= 2 else None)
    clean = bool(variance is not None and math.isfinite(variance) and variance > 0.0)
    return {"mean": mean, "variance": variance,
            "se": math.sqrt(variance) if clean else None, "g": g, "clean": clean}


def _exact_value_equal(left: Any, right: Any) -> bool:
    """比較 JSON 值及其型別；bool/int 等 Python 寬鬆相等不可穿透 lineage gate。"""
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


def _raw_event_identity(event: Mapping[str, Any]) -> dict[str, Any]:
    horizon = event["horizon_policy"]["outcome_horizon_minutes"]
    return {
        "strategy_name": event["strategy_name"],
        "strategy_version": event["strategy_version"],
        "strategy_config_hash": event["strategy_config_hash"],
        "symbol": event["symbol"],
        "side": event["side"],
        "horizon_minutes": horizon,
        "venue": event["venue"],
        "product": event["product"],
        "evidence_engine_mode": event["evidence_engine_mode"],
    }


def _candidate_family_key(identity: dict[str, Any]) -> str:
    """以版本化 raw 9-field identity 建 family；不得混入動態 regime/context。"""
    return _canonical_sha256(
        {
            "schema_version": _CANDIDATE_FAMILY_SCHEMA_VERSION,
            "identity": identity,
        }
    )


def _stable_projection(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    projection = candidate_learning_context_projection(evaluation)
    projection.pop("evidence_regime_label", None)
    return projection


def _stable_cohort_hash(
    evaluation: Mapping[str, Any], projection: Mapping[str, Any]
) -> str:
    """每事件 hash/regime label 不得造成 cohort churn，其餘 typed 投影全數入 hash。"""
    return _canonical_sha256(
        {
            "identity": evaluation["identity"],
            "stable_projection": projection,
        }
    )


def _event_utc_date(event: Mapping[str, Any]) -> dt.date:
    return dt.datetime.fromtimestamp(
        event["captured_at_ms"] / 1_000,
        tz=dt.timezone.utc,
    ).date()


def _evaluation_window_dates(evaluation: Mapping[str, Any]) -> set[dt.date]:
    return {
        dt.date.fromisoformat(bucket["utc_date"])
        for bucket in evaluation["resource"]["daily_buckets"]
    }


def _outer_bindings_valid(
    row: Mapping[str, Any], event: Mapping[str, Any]
) -> bool:
    identity = _raw_event_identity(event)
    expected = {
        "strategy_name": identity["strategy_name"],
        "symbol": identity["symbol"],
        "side": identity["side"],
        "horizon_minutes": identity["horizon_minutes"],
        "event_ts_ms": event["captured_at_ms"],
        "attempt_id": event["context_id"],
        "side_cell_key": (
            f"{identity['strategy_name']}|{identity['symbol']}|{identity['side']}"
        ),
    }
    return all(
        key in row and _exact_value_equal(row[key], value)
        for key, value in expected.items()
    )


def _lineage_result(
    *,
    partition: str,
    reason: str,
    row: Mapping[str, Any],
    raw_event: Mapping[str, Any] | None = None,
    evaluation: Mapping[str, Any] | None = None,
    stable_projection: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw_identity = _raw_event_identity(raw_event) if raw_event is not None else None
    return {
        "partition": partition,
        "reason": reason,
        "row": dict(row),
        "raw_event": dict(raw_event) if raw_event is not None else None,
        "raw_identity": raw_identity,
        "raw_event_date": _event_utc_date(raw_event) if raw_event is not None else None,
        "event_hash": raw_event.get("event_hash") if raw_event is not None else None,
        "evaluation": dict(evaluation) if evaluation is not None else None,
        "stable_projection": (
            dict(stable_projection) if stable_projection is not None else None
        ),
        "stable_cohort_hash": (
            _stable_cohort_hash(evaluation, stable_projection)
            if evaluation is not None and stable_projection is not None
            else None
        ),
        "candidate_family_key": (
            _candidate_family_key(raw_identity) if raw_identity is not None else None
        ),
    }


def _classify_lineage(row: Mapping[str, Any]) -> dict[str, Any]:
    """在任何 cohort/statistics 之前，把一行唯一分到 QUALIFIED/UNQUALIFIED/INVALID。"""
    summary_value = row.get("candidate_summary")
    summary = dict(summary_value) if isinstance(summary_value, Mapping) else {}
    evaluation_claimed = any(
        field in summary
        for field in (
            "candidate_evaluation_context",
            "candidate_evaluation_context_status",
            "candidate_learning_context_projection",
        )
    )
    raw_payload_present = "candidate_event_context" in summary
    raw_status_present = "candidate_event_context_status" in summary
    try:
        raw_event = validate_candidate_event_context(
            summary.get("candidate_event_context")
        )
    except (CandidateEvaluationContextError, TypeError, ValueError):
        raw_status = summary.get("candidate_event_context_status")
        explicitly_unqualified_missing = bool(
            not raw_payload_present
            and not evaluation_claimed
            and (not raw_status_present or raw_status == "UNQUALIFIED_CONTEXT_MISSING")
        )
        if not explicitly_unqualified_missing:
            return _lineage_result(
                partition="INVALID",
                reason="INVALID_LINEAGE_RAW_CONTEXT_INVALID",
                row=row,
            )
        legacy_only = isinstance(summary.get("candidate_learning_context"), Mapping)
        return _lineage_result(
            partition="UNQUALIFIED",
            reason=(
                "UNQUALIFIED_LEGACY_PROJECTION_ONLY"
                if legacy_only
                else "UNQUALIFIED_CONTEXT_MISSING"
            ),
            row=row,
        )

    raw_status_valid = summary.get("candidate_event_context_status") == "VALID"
    if not evaluation_claimed:
        if not raw_status_valid:
            return _lineage_result(
                partition="INVALID",
                reason="INVALID_LINEAGE_IDENTITY_FAMILY",
                row=row,
                raw_event=raw_event,
            )
        return _lineage_result(
            partition="UNQUALIFIED",
            reason="UNQUALIFIED_RAW_VALID_EVALUATION_MISSING",
            row=row,
            raw_event=raw_event,
        )

    try:
        evaluation = validate_candidate_evaluation_context(
            summary.get("candidate_evaluation_context")
        )
    except (CandidateEvaluationContextError, TypeError, ValueError):
        return _lineage_result(
            partition="INVALID",
            reason="INVALID_LINEAGE_IDENTITY_FAMILY",
            row=row,
            raw_event=raw_event,
        )

    raw_identity = _raw_event_identity(raw_event)
    evaluation_bound = bool(
        _exact_value_equal(evaluation["identity"], raw_identity)
        and evaluation["event_hash"] == raw_event["event_hash"]
    )
    if not evaluation_bound:
        return _lineage_result(
            partition="INVALID",
            reason="INVALID_LINEAGE_IDENTITY_FAMILY",
            row=row,
            raw_event=raw_event,
        )

    projection = candidate_learning_context_projection(evaluation)
    stable_projection = dict(projection)
    stable_projection.pop("evidence_regime_label", None)
    required_projection_fields_present = all(
        field in summary
        for field in (
            "candidate_evaluation_context_status",
            "candidate_learning_context_projection",
            "candidate_learning_context",
        )
    )
    projection_exact = bool(
        required_projection_fields_present
        and summary.get("candidate_evaluation_context_status") == "VALID"
        and _exact_value_equal(
            summary.get("candidate_learning_context_projection"), projection
        )
        and _exact_value_equal(summary.get("candidate_learning_context"), projection)
    )
    try:
        attached = attach_candidate_evaluation_context(
            summary,
            candidate_evaluation_context=evaluation,
        )
        attachment_exact = all(
            _exact_value_equal(attached.get(field), summary.get(field))
            for field in (
                "candidate_evaluation_context",
                "candidate_evaluation_context_status",
                "candidate_learning_context_projection",
                "candidate_learning_context",
            )
        )
    except (CandidateEvaluationContextError, TypeError, ValueError):
        attachment_exact = False

    if not (
        raw_status_valid
        and projection_exact
        and attachment_exact
        and _outer_bindings_valid(row, raw_event)
    ):
        return _lineage_result(
            partition="INVALID",
            reason="INVALID_LINEAGE_EXACT_COHORT",
            row=row,
            raw_event=raw_event,
            evaluation=evaluation,
            stable_projection=stable_projection,
        )

    if _event_utc_date(raw_event) not in _evaluation_window_dates(evaluation):
        return _lineage_result(
            partition="UNQUALIFIED",
            reason="UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW",
            row=row,
            raw_event=raw_event,
            evaluation=evaluation,
            stable_projection=stable_projection,
        )
    return _lineage_result(
        partition="QUALIFIED",
        reason="QUALIFIED_LINEAGE",
        row=row,
        raw_event=raw_event,
        evaluation=evaluation,
        stable_projection=stable_projection,
    )


def _duplicate_semantic_projection(item: Mapping[str, Any]) -> dict[str, Any]:
    """投影 MIT 凍結欄位；presence bit 保證 missing 與 explicit null 不相等。"""
    row = item["row"]
    evaluation = item["evaluation"]
    return {
        "fields": {
            key: (
                {"present": True, "value": row[key]}
                if key in row
                else {"present": False}
            )
            for key in (*_DUPLICATE_EXACT_FIELDS, *_DUPLICATE_BPS_FIELDS)
        },
        "evaluation_semantic_body": {
            key: value
            for key, value in evaluation.items()
            if key != "candidate_evaluation_context_hash"
        },
    }


def _duplicate_semantics_equal(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    if not _duplicate_outcome_semantics_equal(left, right):
        return False
    left_evaluation = {
        key: value
        for key, value in left["evaluation"].items()
        if key != "candidate_evaluation_context_hash"
    }
    right_evaluation = {
        key: value
        for key, value in right["evaluation"].items()
        if key != "candidate_evaluation_context_hash"
    }
    return _exact_value_equal(left_evaluation, right_evaluation)


def _duplicate_outcome_semantics_equal(
    left: Mapping[str, Any], right: Mapping[str, Any]
) -> bool:
    """Compare outcome semantics when one member has no qualified evaluation."""
    left_row = left["row"]
    right_row = right["row"]
    for field in _DUPLICATE_EXACT_FIELDS:
        if (field in left_row) != (field in right_row):
            return False
        if field in left_row and not _exact_value_equal(left_row[field], right_row[field]):
            return False
    for field in _DUPLICATE_BPS_FIELDS:
        if (field in left_row) != (field in right_row):
            return False
        if field not in left_row:
            continue
        left_value = left_row[field]
        right_value = right_row[field]
        if type(left_value) is not type(right_value):
            return False
        if left_value is None:
            continue
        if isinstance(left_value, bool):
            return False
        if isinstance(left_value, (int, float)):
            if (
                not math.isfinite(left_value)
                or not math.isfinite(right_value)
                or abs(left_value - right_value) > 1e-9
            ):
                return False
        elif not _exact_value_equal(left_value, right_value):
            return False
    return True


def _duplicate_group_semantics_equal(
    qualified_members: list[dict[str, Any]],
    unqualified_members: list[dict[str, Any]],
) -> bool:
    """Validate one event-hash group in O(rows * frozen_fields)."""
    if not qualified_members:
        return False
    baseline = qualified_members[0]
    baseline_row = baseline["row"]
    numeric_bounds: dict[str, tuple[float | int, float | int]] = {}
    for field in _DUPLICATE_BPS_FIELDS:
        if field not in baseline_row:
            continue
        value = baseline_row[field]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(value):
                return False
            numeric_bounds[field] = (value, value)

    for item in qualified_members[1:]:
        if not _duplicate_semantics_equal(item, baseline):
            return False
        row = item["row"]
        for field, (minimum, maximum) in tuple(numeric_bounds.items()):
            value = row[field]
            numeric_bounds[field] = (min(minimum, value), max(maximum, value))
    for item in unqualified_members:
        if not _duplicate_outcome_semantics_equal(item, baseline):
            return False
        row = item["row"]
        for field, (minimum, maximum) in tuple(numeric_bounds.items()):
            value = row[field]
            numeric_bounds[field] = (min(minimum, value), max(maximum, value))
    return not any(
        maximum - minimum > 1e-9
        for minimum, maximum in numeric_bounds.values()
    )


def _gate_duplicate_event_hashes(
    qualified: list[dict[str, Any]],
    addressable_nonqualified: list[dict[str, Any]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, int]], int, int]:
    """event_hash gate 先於分鐘/重疊去重，衝突事件全部 quarantine。"""
    by_event: dict[str, list[dict[str, Any]]] = {}
    for item in qualified:
        gated = {**item, "event_gate_kind": "QUALIFIED",
                 "event_gate_cohorts": (item["stable_cohort_hash"],),
                 "event_gate_claimed_cohorts": (item["stable_cohort_hash"],)}
        by_event.setdefault(item["event_hash"], []).append(gated)
    for item in addressable_nonqualified:
        targets = tuple(item.get("event_gate_cohorts") or ())
        if item.get("event_hash") and targets:
            gated = {**item, "event_gate_kind": item["partition"],
                     "event_gate_cohorts": targets,
                     "event_gate_claimed_cohorts": tuple(
                         item.get("event_gate_claimed_cohorts") or ()
                     )}
            by_event.setdefault(item["event_hash"], []).append(gated)
    evaluator_rows: dict[str, list[dict[str, Any]]] = {}
    audits: dict[str, dict[str, int]] = {}
    consistent_extra_total = 0
    conflict_total = 0

    def audit(cohort: str) -> dict[str, int]:
        return audits.setdefault(
            cohort,
            {
                "consistent_extra": 0,
                "conflicting": 0,
                "outcome_conflict": 0,
                "cohort_conflict": 0,
            },
        )

    for event_hash in sorted(by_event):
        members = by_event[event_hash]
        claimed_cohorts = {
            cohort
            for item in members
            for cohort in item["event_gate_claimed_cohorts"]
        }
        qualified_members = [
            item for item in members if item["event_gate_kind"] == "QUALIFIED"
        ]
        invalid_members = [
            item for item in members if item["event_gate_kind"] == "INVALID"
        ]
        unqualified_members = [
            item for item in members if item["event_gate_kind"] == "UNQUALIFIED"
        ]
        if len(members) == 1 and invalid_members:
            continue
        if not claimed_cohorts:
            continue
        if len(claimed_cohorts) > 1:
            conflict_total += len(members)
            scoped_counts = {cohort: 0 for cohort in claimed_cohorts}
            for item in members:
                for cohort in set(item["event_gate_cohorts"]):
                    if cohort in scoped_counts:
                        scoped_counts[cohort] += 1
            for cohort in claimed_cohorts:
                scoped = audit(cohort)
                scoped["conflicting"] += scoped_counts[cohort]
                scoped["cohort_conflict"] += scoped_counts[cohort]
            continue
        cohort = next(iter(claimed_cohorts))
        if invalid_members:
            # 為什麼 fail-closed：同 event_hash 同時出現 valid 與 invalid lineage，
            # 無法證明哪個 outcome/evaluation 是原始語意，故 valid copy 亦不得進分母。
            conflict_total += len(members)
            scoped = audit(cohort)
            scoped["conflicting"] += len(members)
            scoped["outcome_conflict"] += len(members)
            continue
        if not _duplicate_group_semantics_equal(
            qualified_members,
            unqualified_members,
        ):
            conflict_total += len(members)
            scoped = audit(cohort)
            scoped["conflicting"] += len(members)
            scoped["outcome_conflict"] += len(members)
            continue
        representative = min(
            qualified_members,
            key=lambda item: _canonical_sha256(
                _duplicate_semantic_projection(item)
            ),
        )
        evaluator_rows.setdefault(cohort, []).append(representative["row"])
        extras = len(qualified_members) - 1
        if extras:
            consistent_extra_total += extras
            audit(cohort)["consistent_extra"] += extras
    return evaluator_rows, audits, consistent_extra_total, conflict_total


def _arbiter_identity(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    identity = evaluation["identity"]
    target = {
        **evaluation["target_regime_context"],
        "hash": evaluation["target_regime_hash"],
    }
    return {
        "strategy_name": identity["strategy_name"],
        "strategy_version": identity["strategy_version"],
        "config_hash": identity["strategy_config_hash"],
        "symbol": identity["symbol"],
        "side": identity["side"],
        "horizon_minutes": identity["horizon_minutes"],
        "target_regime": target,
        "engine_mode": "shadow",
        "evidence_engine_mode": identity["evidence_engine_mode"],
        "venue": identity["venue"],
        "product": identity["product"],
    }


def _candidate_identity(evaluation: Mapping[str, Any]) -> dict[str, Any]:
    identity = evaluation["identity"]
    return {
        **identity,
        "target_regime_context": evaluation["target_regime_context"],
        "target_regime_hash": evaluation["target_regime_hash"],
        "engine_mode": "shadow",
    }


def _validated_evaluation_as_of_date(evaluation: Mapping[str, Any]) -> dt.date:
    value = evaluation.get("as_of_utc_date")
    try:
        parsed = dt.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.isoformat() != value:
        raise ValueError("CANDIDATE_EVALUATION_AS_OF_DATE_INVALID")
    return parsed


def _candidate_source_contract_valid(item: Mapping[str, Any]) -> bool:
    """Return whether one lineage source can produce an exact current v2 row."""
    evaluation = item.get("evaluation")
    if not isinstance(evaluation, Mapping):
        return False
    try:
        as_of_date = _validated_evaluation_as_of_date(evaluation)
    except ValueError:
        return False
    identity = _candidate_identity(evaluation)
    if _candidate_identity_blockers(identity, as_of_date=as_of_date):
        return False
    projection = candidate_learning_context_projection(evaluation)
    *_, context_blockers = _typed_context_parts(
        dict(projection),
        as_of_date=as_of_date,
    )
    return not context_blockers


def _build_candidate_row(
    *,
    evaluation_context: Mapping[str, Any],
    projection: Mapping[str, Any],
    stable_cohort_hash: str,
    candidate_family_key: str,
    qualified_raw_count: int,
    evaluator_input_count: int,
    exact_invalid_count: int,
    family_invalid_count: int,
    duplicate_audit: Mapping[str, int],
    cohort_evaluation: CandidateCohortEvaluation,
    expected_slippage: dict[str, Any] | None,
) -> dict[str, Any]:
    """建立單一 stable cohort；lineage blocker 與描述統計分面輸出。"""
    as_of_date = _validated_evaluation_as_of_date(evaluation_context)
    identity = _candidate_identity(evaluation_context)
    identity_blockers = _candidate_identity_blockers(identity, as_of_date=as_of_date)
    context_hashes, resource, portfolio, proof, hidden_oos, context_blockers = (
        _typed_context_parts(dict(projection), as_of_date=as_of_date)
    )
    structural_blockers = list(identity_blockers) + list(context_blockers)
    if identity_blockers:
        structural_blockers.append("IDENTITY_LINEAGE_INCOMPLETE")
    if context_blockers:
        structural_blockers.append("ARBITER_INPUT_CONTEXT_INCOMPLETE")

    lineage_blocker_reason_counts: dict[str, int] = {}
    if exact_invalid_count:
        lineage_blocker_reason_counts[
            "INVALID_LINEAGE_EXACT_COHORT_ROWS_PRESENT"
        ] = exact_invalid_count
    if family_invalid_count:
        lineage_blocker_reason_counts[
            "INVALID_LINEAGE_IDENTITY_FAMILY_ROWS_PRESENT"
        ] = family_invalid_count
    if duplicate_audit["outcome_conflict"]:
        lineage_blocker_reason_counts[
            "DUPLICATE_EVENT_HASH_OUTCOME_CONFLICT"
        ] = duplicate_audit["outcome_conflict"]
    if duplicate_audit["cohort_conflict"]:
        lineage_blocker_reason_counts[
            "DUPLICATE_EVENT_HASH_COHORT_CONFLICT"
        ] = duplicate_audit["cohort_conflict"]
    lineage_blockers = list(lineage_blocker_reason_counts)
    blockers = [*structural_blockers, *lineage_blockers]

    censored_count = cohort_evaluation["censored_count"]
    uncensored_row_count = cohort_evaluation["uncensored_row_count"]
    metrics = cohort_evaluation["metrics"]
    entries = cohort_evaluation["entries"]
    n_eff = len(entries)
    regime_entry_counts = {key: 0 for key in (*_REGIME_BUCKETS, "unknown")}
    for entry in entries:
        label = entry.get("evidence_regime_label")
        bucket = label if label in _REGIME_BUCKETS else "unknown"
        regime_entry_counts[bucket] += 1
    cluster = _day_cluster_stats(
        entries,
        expected_track_on=expected_slippage is not None,
    )
    expected_cost_recomputable_count = sum(
        entry.get("expected_cost_bps") is not None for entry in entries
    )
    tail_cost_recomputable_count = sum(
        entry.get("tail_cost_bps") is not None for entry in entries
    )
    expected_cost_recomputable_share = (
        expected_cost_recomputable_count / n_eff if n_eff else 0.0
    )
    tail_cost_recomputable_share = (
        tail_cost_recomputable_count / n_eff if n_eff else 0.0
    )
    qualified_denominator = censored_count + uncensored_row_count
    censored_share = (
        censored_count / qualified_denominator if qualified_denominator else 0.0
    )
    invalid_outcome_row_count = uncensored_row_count - metrics["outcome_count"]
    top_entry_day_share = (
        metrics["top_entry_day_share_pct"] / 100.0
        if metrics["top_entry_day_share_pct"] is not None
        else None
    )

    if n_eff < _SELECTION_N_EFF_MIN:
        blockers.append("EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT")
    if metrics["distinct_entry_utc_days"] < _SELECTION_UTC_DAYS_MIN:
        blockers.append("UTC_DAY_COVERAGE_INSUFFICIENT")
    if (
        metrics["top_entry_day_share_pct"]
        if metrics["top_entry_day_share_pct"] is not None
        else 100.0
    ) > _SELECTION_TOP_DAY_SHARE_MAX_PCT:
        blockers.append("TOP_DAY_CONCENTRATION_EXCESS")
    if metrics["entry_ts_missing_row_count"] > 0:
        blockers.append("ENTRY_TS_LINEAGE_INCOMPLETE")
    if invalid_outcome_row_count > 0:
        blockers.append("INVALID_OUTCOME_ROWS_PRESENT")
    if metrics["data_integrity_suspect"]:
        blockers.append("DATA_INTEGRITY_SUSPECT")
    if not cluster["clean"]:
        blockers.append("DAY_CLUSTER_VARIANCE_DEGENERATE")
    if censored_share > 0.30:
        blockers.append("CENSORING_EXCESS")
    if metrics["legacy_optimistic_cost_present"]:
        blockers.append("LEGACY_OPTIMISTIC_COST_UNBACKFILLED")
    if expected_cost_recomputable_share < 1.0:
        blockers.append("EXPECTED_COST_NOT_FULLY_RECOMPUTABLE")
    if tail_cost_recomputable_share < 1.0:
        blockers.append("TAIL_COST_NOT_FULLY_RECOMPUTABLE")
    if isinstance(proof.get("next_gap"), dict) and proof["next_gap"].get("kind") != "NONE":
        blockers.append("PROOF_GAP_OPEN")
    if hidden_oos is True:
        blockers.append("HIDDEN_OOS_CONSUMED")
    blockers = sorted(set(blockers))

    arbiter_identity = _arbiter_identity(evaluation_context)
    integrity_ok = bool(
        not structural_blockers
        and not lineage_blockers
        and not metrics["data_integrity_suspect"]
        and metrics["entry_ts_missing_row_count"] == 0
        and invalid_outcome_row_count == 0
        and cluster["clean"]
    )
    unknown_regime_share = regime_entry_counts["unknown"] / n_eff if n_eff else 1.0
    cost_evidence = candidate_cost_evidence_v2(expected_slippage, symbol=identity["symbol"])
    arbiter_input_body = {
        "schema_version": ARBITER_INPUT_SCHEMA_VERSION,
        "identity": arbiter_identity,
        "context_hashes": context_hashes,
        "cost_evidence": cost_evidence,
        "quality": {
            "hash_ok": (
                not identity_blockers
                and not any("HASH_MISSING_OR_INVALID" in code for code in context_blockers)
            ),
            "integrity_ok": integrity_ok,
            "freshness_ok": "RESOURCE_DAILY_BUCKETS_INCOMPLETE" not in context_blockers,
            "censored_share": censored_share,
            "cost_recomputable_share": expected_cost_recomputable_share,
            "unknown_regime_share": unknown_regime_share,
            "replica_inconsistency_count": metrics["replica_inconsistent_group_count"],
            "cluster_variance_clean": cluster["clean"],
            "legacy_optimistic_cost_present": metrics[
                "legacy_optimistic_cost_present"
            ],
            "hidden_oos_consumed": hidden_oos is True,
            "top_day_share": (
                top_entry_day_share if top_entry_day_share is not None else 1.0
            ),
        },
        "evidence": {
            "n_eff": n_eff,
            "utc_day_count": metrics["distinct_entry_utc_days"],
            "mean_net_e": cluster["mean"],
            "day_cluster_variance": cluster["variance"],
            "cluster_se": cluster["se"],
            "cluster_count": cluster["g"],
            "proof_stage": proof.get("proof_stage"),
            "completed_proof_stages": proof.get("completed_proof_stages"),
            "next_gap": proof.get("next_gap"),
            "raw_attempt_count": evaluator_input_count,
            "regime_entry_counts": regime_entry_counts,
        },
        "resource": resource,
        "portfolio": portfolio,
    }
    arbiter_input = {
        **arbiter_input_body,
        "arbiter_input_hash": _canonical_sha256(arbiter_input_body),
    }
    candidate_id = _canonical_sha256(
        {
            "schema_version": LEARNING_CANDIDATE_SCHEMA_VERSION,
            "identity": arbiter_identity,
            "context_hashes": context_hashes,
        }
    )
    identity_complete = not identity_blockers
    arbiter_input_complete = not structural_blockers and not lineage_blockers
    metrics_actionable = not (
        structural_blockers
        or lineage_blockers
        or invalid_outcome_row_count
        or metrics["data_integrity_suspect"]
        or metrics["entry_ts_missing_row_count"]
        or censored_share > 0.30
    )
    return {
        "schema_version": LEARNING_CANDIDATE_SCHEMA_VERSION,
        "candidate_id": candidate_id,
        "candidate_family_key": candidate_family_key,
        "stable_cohort_hash": stable_cohort_hash,
        "candidate_identity": identity,
        "identity_complete": identity_complete,
        "arbiter_input": arbiter_input,
        "arbiter_input_complete": arbiter_input_complete,
        "selection_eligible": not blockers,
        "qualified_metrics_actionable": metrics_actionable,
        "metrics_scope": (
            "QUALIFIED_SUBSET_ACTIONABLE"
            if metrics_actionable
            else "QUALIFIED_SUBSET_DESCRIPTIVE_ONLY"
        ),
        "blockers": blockers,
        "side_cell_key": (
            f"{identity['strategy_name']}|{identity['symbol']}|{identity['side']}"
        ),
        "horizon_minutes": identity["horizon_minutes"],
        "qualified_raw_outcome_count": qualified_raw_count,
        "qualified_evaluator_input_count": evaluator_input_count,
        "qualified_uncensored_outcome_count": uncensored_row_count,
        "qualified_valid_uncensored_outcome_count": metrics["outcome_count"],
        "qualified_invalid_outcome_row_count": invalid_outcome_row_count,
        "qualified_censored_outcome_count": censored_count,
        "consistent_duplicate_event_hash_extra_row_count": duplicate_audit[
            "consistent_extra"
        ],
        "conflicting_event_hash_row_count": duplicate_audit["conflicting"],
        "duplicate_event_hash_outcome_conflict_row_count": duplicate_audit[
            "outcome_conflict"
        ],
        "duplicate_event_hash_cohort_conflict_row_count": duplicate_audit[
            "cohort_conflict"
        ],
        "invalid_lineage_exact_cohort_row_count": exact_invalid_count,
        "invalid_lineage_identity_family_row_count": family_invalid_count,
        "lineage_blocker_reason_counts": {
            key: lineage_blocker_reason_counts[key]
            for key in sorted(lineage_blocker_reason_counts)
        },
        "qualified_distinct_entry_observation_count": metrics[
            "distinct_entry_observation_count"
        ],
        "qualified_duplicate_outcome_row_count": metrics["duplicate_outcome_row_count"],
        "qualified_window_overlap_excluded_entry_count": metrics[
            "window_overlap_excluded_entry_count"
        ],
        "qualified_entry_ts_missing_row_count": metrics["entry_ts_missing_row_count"],
        "n_eff": n_eff,
        "distinct_entry_utc_days": metrics["distinct_entry_utc_days"],
        "entry_day_counts": metrics["entry_day_counts"],
        "top_entry_utc_day": metrics["top_entry_utc_day"],
        "top_entry_day_share": top_entry_day_share,
        "top_entry_day_share_pct": metrics["top_entry_day_share_pct"],
        "censored_share": censored_share,
        "censored_pct": censored_share * 100.0,
        "replica_inconsistent_group_count": metrics["replica_inconsistent_group_count"],
        "zero_variance_suspect": metrics["zero_variance_suspect"],
        "data_integrity_suspect": metrics["data_integrity_suspect"],
        "cluster_variance_clean": cluster["clean"],
        "day_cluster_variance": cluster["variance"],
        "cluster_se": cluster["se"],
        "cluster_count": cluster["g"],
        "legacy_optimistic_cost_present": metrics[
            "legacy_optimistic_cost_present"
        ],
        "avg_net_bps": metrics["avg_net_bps"],
        "mean_net_e": cluster["mean"],
        "cost_basis_main": metrics["cost_basis_main"],
        "expected_cost_recomputable_count": expected_cost_recomputable_count,
        "expected_cost_recomputable_share": expected_cost_recomputable_share,
        "cost_recomputable_share": expected_cost_recomputable_share,
        "tail_cost_recomputable_count": tail_cost_recomputable_count,
        "tail_cost_recomputable_share": tail_cost_recomputable_share,
        "avg_expected_cost_bps": metrics["avg_expected_cost_bps"],
        "avg_tail_cost_bps": metrics["avg_tail_cost_bps"],
        "tail_metric": metrics["tail_metric"],
        "regime_entry_counts": regime_entry_counts,
        "regime_coverage_inputs": {
            "composite_bucket_universe_size": len(_REGIME_BUCKETS),
            "observed_composite_bucket_count": sum(
                regime_entry_counts[label] > 0 for label in _REGIME_BUCKETS
            ),
            "effective_entry_count": n_eff,
            "unknown_regime_entry_count": regime_entry_counts["unknown"],
            "unknown_regime_share": unknown_regime_share,
        },
        "hidden_oos_consumed": hidden_oos,
    }


def candidate_cost_projection_for_recorded_date(
    expected_slippage: Mapping[str, Any] | None, *, as_of_date: dt.date) -> dict[str, Any] | None:
    """Keep normalized cost evidence only when it is canonical for one row date."""
    if (expected_slippage is None or type(as_of_date) is not dt.date
            or not isinstance(source_asof_raw := expected_slippage.get("asof"), str)):
        return None
    try:
        source_asof = dt.datetime.fromisoformat(source_asof_raw)
    except ValueError:
        return None
    if (source_asof.tzinfo is None or source_asof.utcoffset() != dt.timedelta(0)
            or source_asof.isoformat() != source_asof_raw
            or not as_of_date - dt.timedelta(days=2) <= source_asof.date() <= as_of_date):
        return None
    return dict(expected_slippage)


def _cost_source(scope: str, symbol: str | None, sample_count: int, **metrics: Any) -> dict[str, Any]:
    return {"scope": scope, "symbol": symbol, "sample_count": sample_count, **metrics}


def candidate_cost_evidence_v2(
    expected_slippage: Mapping[str, Any] | None, *, symbol: str) -> dict[str, Any]:
    """Bind compact selected-source provenance without duplicating full projection."""
    base = {"schema_version": COST_EVIDENCE_SCHEMA_VERSION, "max_age_hours": QUANTILE_ARTIFACT_MAX_AGE_HOURS,
            "fee_floor_bps": FEE_FLOOR_BPS}
    if expected_slippage is None:
        return {**base, "basis": "conservative_v1", "source_payload_sha256": None,
            "source_asof_utc": None, "normalized_projection_sha256": None,
            "mean_abs_source": _cost_source("NONE", None, 0, mean_abs_bps=None),
            "tail_source": _cost_source("NONE", None, 0, tail_bps=None, tail_metric=None)}
    symbol_entry = expected_slippage["per_symbol"].get(symbol)
    use_symbol = bool(isinstance(symbol_entry, Mapping)
                      and symbol_entry["n"] >= MIN_SYMBOL_FILLS_FOR_QUANTILE)
    use_symbol_tail = bool(use_symbol and symbol_entry["tail_bps"] is not None)
    mean_source = _cost_source("SYMBOL" if use_symbol else "GLOBAL", symbol if use_symbol else None,
        symbol_entry["n"] if use_symbol else expected_slippage["n_total_global"],
        mean_abs_bps=symbol_entry["mean_abs"] if use_symbol
        else expected_slippage["global_mean_abs"])
    tail_source = _cost_source("SYMBOL" if use_symbol_tail else "GLOBAL", symbol if use_symbol_tail else None,
        symbol_entry["n"] if use_symbol_tail else expected_slippage["n_total_global"],
        tail_bps=symbol_entry["tail_bps"] if use_symbol_tail
        else expected_slippage["global_tail_bps"],
        tail_metric=symbol_entry["tail_metric"] if use_symbol_tail
        else expected_slippage["global_tail_metric"])
    return {**base, "basis": "expected_slippage_mean_abs_v1",
        "source_payload_sha256": expected_slippage["source_payload_sha256"],
        "source_asof_utc": expected_slippage["asof"],
        "normalized_projection_sha256": expected_slippage["normalized_projection_sha256"],
        "mean_abs_source": mean_source, "tail_source": tail_source}


def build_learning_candidate_board(
    ledger_rows: list[dict[str, Any]],
    *,
    cfg: CandidateBoardConfig,
    overlay: dict[str, dict[str, Any]],
    edge_estimates: dict[str, dict[str, Any]],
    expected_slippage: dict[str, Any] | None,
    as_of_date: dt.date,
    cohort_evaluator: CandidateCohortEvaluator,
    eligible_evaluator_rows_by_cohort_sink: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """先完成 prospective lineage 分區，再建立 qualified-only candidate board。"""
    blocked_rows = [
        row
        for row in ledger_rows
        if isinstance(row, Mapping)
        and row.get("record_type") == BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE
    ]
    classified = []
    for row in blocked_rows:
        item = _classify_lineage(row)
        if item["partition"] == "QUALIFIED" and not _candidate_source_contract_valid(
            item
        ):
            item = {
                **item,
                "partition": "INVALID",
                "reason": "INVALID_LINEAGE_EXACT_COHORT",
            }
        classified.append(item)
    qualified = [item for item in classified if item["partition"] == "QUALIFIED"]
    unqualified = [item for item in classified if item["partition"] == "UNQUALIFIED"]
    invalid = [item for item in classified if item["partition"] == "INVALID"]
    invalid_exact = [
        item for item in invalid if item["reason"] == "INVALID_LINEAGE_EXACT_COHORT"
    ]
    invalid_family = [
        item for item in invalid if item["reason"] == "INVALID_LINEAGE_IDENTITY_FAMILY"
    ]
    invalid_unassigned = [
        item
        for item in invalid
        if item["reason"]
        not in {"INVALID_LINEAGE_EXACT_COHORT", "INVALID_LINEAGE_IDENTITY_FAMILY"}
    ]

    reasons: dict[str, int] = {}
    for item in (*unqualified, *invalid):
        reason = item["reason"]
        reasons[reason] = reasons.get(reason, 0) + 1

    cohort_sources: dict[str, list[dict[str, Any]]] = {}
    qualified_by_cohort: dict[str, list[dict[str, Any]]] = {}
    exact_by_cohort: dict[str, list[dict[str, Any]]] = {}
    for item in qualified:
        cohort_sources.setdefault(item["stable_cohort_hash"], []).append(item)
        qualified_by_cohort.setdefault(item["stable_cohort_hash"], []).append(item)
    # 為什麼：可精確歸屬的 invalid row 本身即可建立「零 metrics」候選，讓 blocker
    # 不會因缺 qualified 同伴而從 board 消失；family-only invalid 則不得創造 cohort。
    current_invalid_exact: list[dict[str, Any]] = []
    noncurrent_invalid_exact: list[dict[str, Any]] = []
    for item in invalid_exact:
        target = (
            current_invalid_exact
            if _candidate_source_contract_valid(item)
            else noncurrent_invalid_exact
        )
        target.append(item)
    for item in current_invalid_exact:
        cohort_sources.setdefault(item["stable_cohort_hash"], []).append(item)
        exact_by_cohort.setdefault(item["stable_cohort_hash"], []).append(item)

    addressable_nonqualified: list[dict[str, Any]] = []
    for item in current_invalid_exact:
        addressable_nonqualified.append(
            {
                **item,
                "event_gate_cohorts": (item["stable_cohort_hash"],),
                "event_gate_claimed_cohorts": (item["stable_cohort_hash"],),
            }
        )

    def existing_cohort_targets(item: Mapping[str, Any]) -> tuple[str, ...]:
        target_cohorts = []
        for cohort_hash, sources in cohort_sources.items():
            source = sources[0]
            if (
                source["candidate_family_key"] == item["candidate_family_key"]
                and item["raw_event_date"]
                in _evaluation_window_dates(source["evaluation"])
            ):
                target_cohorts.append(cohort_hash)
        return tuple(sorted(target_cohorts))

    for item in noncurrent_invalid_exact:
        target_cohorts = existing_cohort_targets(item)
        if target_cohorts:
            addressable_nonqualified.append(
                {
                    **item,
                    "event_gate_cohorts": target_cohorts,
                    "event_gate_claimed_cohorts": (),
                }
            )

    for item in invalid_family:
        target_cohorts = existing_cohort_targets(item)
        if target_cohorts:
            addressable_nonqualified.append(
                {
                    **item,
                    "event_gate_cohorts": target_cohorts,
                    "event_gate_claimed_cohorts": (),
                }
            )
    # Valid raw hashes from an UNQUALIFIED row still participate in the global
    # event gate. They may address an existing finite-window cohort, but never
    # create one or claim their unqualified evaluation as a candidate cohort.
    for item in unqualified:
        if item.get("event_hash") and item.get("candidate_family_key"):
            target_cohorts = existing_cohort_targets(item)
            if target_cohorts:
                addressable_nonqualified.append(
                    {
                        **item,
                        "event_gate_cohorts": target_cohorts,
                        "event_gate_claimed_cohorts": (),
                    }
                )
    evaluator_rows, duplicate_audits, consistent_extras, duplicate_conflicts = (
        _gate_duplicate_event_hashes(qualified, addressable_nonqualified)
    )

    candidate_rows: list[dict[str, Any]] = []
    for cohort_hash in sorted(cohort_sources):
        sources = sorted(
            cohort_sources[cohort_hash],
            key=lambda item: _canonical_sha256(
                {
                    "evaluation": item["evaluation"],
                    "stable_projection": item["stable_projection"],
                }
            ),
        )
        source = sources[0]
        evaluation_context = source["evaluation"]
        projection = candidate_learning_context_projection(evaluation_context)
        identity = _candidate_identity(evaluation_context)
        family_key = source["candidate_family_key"]
        side_cell_key = (
            f"{identity['strategy_name']}|{identity['symbol']}|{identity['side']}"
        )
        qualified_rows = qualified_by_cohort.get(cohort_hash, [])
        exact_count = len(exact_by_cohort.get(cohort_hash, []))
        window_dates = _evaluation_window_dates(evaluation_context)
        family_count = sum(
            item["candidate_family_key"] == family_key
            and item["raw_event_date"] in window_dates
            for item in invalid_family
        )
        duplicate = duplicate_audits.get(
            cohort_hash,
            {
                "consistent_extra": 0,
                "conflicting": 0,
                "outcome_conflict": 0,
                "cohort_conflict": 0,
            },
        )
        rows_for_evaluator = evaluator_rows.get(cohort_hash, [])
        cohort_expected_slippage = candidate_cost_projection_for_recorded_date(
            expected_slippage, as_of_date=_validated_evaluation_as_of_date(evaluation_context)
        )
        evaluation = cohort_evaluator(
            side_cell_key,
            rows_for_evaluator,
            cfg=cfg,
            overlay=overlay,
            edge_estimates=edge_estimates,
            expected_slippage=cohort_expected_slippage,
        )
        candidate_rows.append(
            _build_candidate_row(
                evaluation_context=evaluation_context,
                projection=projection,
                stable_cohort_hash=cohort_hash,
                candidate_family_key=family_key,
                qualified_raw_count=len(qualified_rows),
                evaluator_input_count=len(rows_for_evaluator),
                exact_invalid_count=exact_count,
                family_invalid_count=family_count,
                duplicate_audit=duplicate,
                cohort_evaluation=evaluation,
                expected_slippage=cohort_expected_slippage,
            )
        )

    eligible_by_side_cell: dict[str, list[dict[str, Any]]] = {}
    for row in candidate_rows:
        if row["selection_eligible"]:
            eligible_by_side_cell.setdefault(row["side_cell_key"], []).append(row)
    for rows in eligible_by_side_cell.values():
        if len(rows) > 1:
            for row in rows:
                row["blockers"] = sorted({
                    *row["blockers"],
                    "SIDE_CELL_STABLE_COHORT_AMBIGUITY",
                })
                row["selection_eligible"] = False

    candidate_rows.sort(
        key=lambda row: (
            row["candidate_identity"]["strategy_name"],
            row["candidate_identity"]["strategy_version"],
            row["candidate_identity"]["strategy_config_hash"],
            row["candidate_identity"]["symbol"],
            row["candidate_identity"]["side"],
            row["candidate_identity"]["horizon_minutes"],
            row["candidate_identity"]["target_regime_hash"],
            row["candidate_identity"]["venue"],
            row["candidate_identity"]["product"],
            row["candidate_identity"]["engine_mode"],
            row["candidate_id"],
            row["stable_cohort_hash"],
        )
    )
    if len({row["candidate_id"] for row in candidate_rows}) != len(candidate_rows):
        # 為什麼 fail-closed：candidate_id 是 downstream evaluation key；碰撞時繼續
        # 發布會把兩個不同 stable cohort 靜默池化成同一學習候選。
        raise ValueError("CANDIDATE_ID_COLLISION")
    if eligible_evaluator_rows_by_cohort_sink is not None:
        for row in candidate_rows:
            if row["selection_eligible"]:
                cohort_hash = row["stable_cohort_hash"]
                eligible_evaluator_rows_by_cohort_sink[cohort_hash] = list(
                    evaluator_rows.get(cohort_hash, [])
                )
    semantic_rows = [
        {field: row[field] for field in _SELECTION_FIELDS} for row in candidate_rows
    ]
    semantic_rows.sort(
        key=lambda row: (row["candidate_id"], _canonical_sha256(row))
    )
    selection_hash = _canonical_sha256(
        {
            "schema_version": _SELECTION_SCHEMA_VERSION,
            "candidate_rows": semantic_rows,
        }
    )
    lineage_partition_complete = (
        len(blocked_rows) == len(qualified) + len(unqualified) + len(invalid)
        and len(invalid)
        == len(invalid_exact) + len(invalid_family) + len(invalid_unassigned)
    )
    if not lineage_partition_complete:
        raise ValueError("CANDIDATE_BOARD_COUNT_INVARIANT_VIOLATION")
    top_audit = {
        "lineage_partition_complete": True,
        "raw_blocked_outcome_row_count": len(blocked_rows),
        "qualified_lineage_outcome_row_count": len(qualified),
        "unqualified_lineage_outcome_row_count": len(unqualified),
        "invalid_lineage_outcome_row_count": len(invalid),
        "invalid_exact_cohort_row_count": len(invalid_exact),
        "invalid_identity_family_row_count": len(invalid_family),
        "unassigned_invalid_lineage_outcome_row_count": len(invalid_unassigned),
        "unqualified_raw_valid_evaluation_missing_row_count": sum(
            item["reason"] == "UNQUALIFIED_RAW_VALID_EVALUATION_MISSING"
            for item in unqualified
        ),
        "unqualified_event_outside_evaluation_window_row_count": sum(
            item["reason"] == "UNQUALIFIED_EVENT_OUTSIDE_EVALUATION_WINDOW"
            for item in unqualified
        ),
        "consistent_duplicate_event_hash_extra_row_count": consistent_extras,
        "conflicting_duplicate_event_hash_row_count": duplicate_conflicts,
        "conflicting_duplicate_event_hash_attribution_row_count": sum(
            row["conflicting_event_hash_row_count"] for row in candidate_rows
        ),
        "lineage_exclusion_reason_counts": {
            key: reasons[key] for key in sorted(reasons)
        },
    }
    candidate_audit_rows = []
    selection_field_set = set(_SELECTION_FIELDS)
    for row in candidate_rows:
        candidate_audit_rows.append(
            {
                "candidate_id": row["candidate_id"],
                **{
                    key: value
                    for key, value in row.items()
                    if key not in selection_field_set and key != "candidate_id"
                },
            }
        )
    candidate_audit_rows.sort(key=lambda row: row["candidate_id"])
    audit_hash = _canonical_sha256(
        {
            "schema_version": _AUDIT_SCHEMA_VERSION,
            **top_audit,
            "candidate_audit_rows": candidate_audit_rows,
        }
    )
    board = {
        "schema_version": LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION,
        "as_of_utc_date": as_of_date.isoformat(),
        "candidate_universe_complete": True,
        **top_audit,
        "candidate_rows": candidate_rows,
        "selection_hash": selection_hash,
        "audit_hash": audit_hash,
    }
    board["board_hash"] = _canonical_sha256(board)
    return board

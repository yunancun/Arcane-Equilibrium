"""Build canonical candidate evidence boards from blocked-outcome ledger rows.

This Module owns candidate identity, typed evaluation context validation, board
construction, and canonical hashing.  Statistical/cost methodology remains in
``outcome_review`` and enters through the narrow ``CandidateCohortEvaluator``
Interface, so this Module never imports its caller.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from typing import Any, Protocol, TypedDict

from cost_gate_learning_lane.contract import BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE


LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION = "cost_gate_learning_candidate_board_v1"
ARBITER_INPUT_SCHEMA_VERSION = "alr_candidate_arbiter_input_v1"
_REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)


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


def _str(value: Any) -> str:
    return str(value or "").strip()


def _int(value: Any, default: int = 0) -> int:
    try:
        out = int(float(value))
    except (TypeError, ValueError):
        return default
    return out


def candidate_learning_context(row: dict[str, Any]) -> dict[str, Any] | None:
    summary = row.get("candidate_summary")
    if not isinstance(summary, dict):
        return None
    context = summary.get("candidate_learning_context")
    return dict(context) if isinstance(context, dict) else None


def _candidate_identity_from_ledger_row(row: dict[str, Any]) -> dict[str, Any]:
    """只讀 ledger 的 typed learning context；禁止從目前 HEAD/config 反推。"""
    context = candidate_learning_context(row) or {}
    regime_context = context.get("target_regime_context")
    raw_horizon_minutes = row.get("horizon_minutes")
    horizon_minutes = raw_horizon_minutes if (
        isinstance(raw_horizon_minutes, int)
        and not isinstance(raw_horizon_minutes, bool)
        and raw_horizon_minutes > 0
    ) else None
    return {
        "strategy_name": row.get("strategy_name"),
        "strategy_version": context.get("strategy_version"),
        "strategy_config_hash": context.get("strategy_config_hash"),
        "symbol": row.get("symbol"),
        "side": row.get("side"),
        "horizon_minutes": horizon_minutes,
        "target_regime_context": dict(regime_context) if isinstance(regime_context, dict) else None,
        "target_regime_hash": context.get("target_regime_hash"),
        "engine_mode": "shadow",
        "evidence_engine_mode": context.get("evidence_engine_mode"),
        "venue": context.get("venue"),
        "product": context.get("product"),
    }


def _exact_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and value == value.strip()


def _sha256_text(value: Any) -> bool:
    return bool(_exact_text(value) and len(value) == 64
                and all(char in "0123456789abcdef" for char in value))


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


def _candidate_family_key(identity: dict[str, Any]) -> str:
    return _canonical_sha256({key: value for key, value in identity.items()
                              if key not in {"target_regime_context", "target_regime_hash"}})


def build_learning_candidate_board(
    ledger_rows: list[dict[str, Any]],
    *,
    cfg: CandidateBoardConfig,
    overlay: dict[str, dict[str, Any]],
    edge_estimates: dict[str, dict[str, Any]],
    expected_slippage: dict[str, Any] | None,
    as_of_date: dt.date,
    cohort_evaluator: CandidateCohortEvaluator,
) -> dict[str, Any]:
    """從完整 ledger universe 建立候選板，不經 legacy top-16 投影。"""
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    identities: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    contexts: dict[tuple[str, str], dict[str, dict[str, Any] | None]] = {}
    for row in ledger_rows:
        if _str(row.get("record_type")) != BLOCKED_SIGNAL_OUTCOME_RECORD_TYPE:
            continue
        side_cell_key = _str(row.get("side_cell_key"))
        identity = _candidate_identity_from_ledger_row(row)
        context = candidate_learning_context(row)
        group_context = dict(context) if context is not None else None
        if group_context is not None:
            group_context.pop("evidence_regime_label", None)
        key = (side_cell_key, _canonical_json(identity))
        grouped.setdefault(key, []).append(row)
        identities.setdefault(key, {})[_canonical_json(identity)] = identity
        contexts.setdefault(key, {})[_canonical_json(group_context)] = group_context

    candidate_rows = []
    for key in sorted(grouped):
        side_cell_key, _ = key
        rows = grouped[key]
        identity = identities[key][sorted(identities[key])[0]]
        context = contexts[key][sorted(contexts[key])[0]]
        evaluation_context_conflict = len(contexts[key]) != 1
        identity_blockers = _candidate_identity_blockers(
            identity, as_of_date=as_of_date
        )
        identity_complete = not identity_blockers
        context_hashes, resource, portfolio, proof, hidden_oos, context_blockers = (
            _typed_context_parts(context, as_of_date=as_of_date)
        )
        if evaluation_context_conflict:
            context_blockers.append("CANDIDATE_EVALUATION_CONTEXT_CONFLICT")
        structural_blockers = list(identity_blockers) + context_blockers
        if identity_blockers:
            structural_blockers.append("IDENTITY_LINEAGE_INCOMPLETE")
        if context_blockers:
            structural_blockers.append("ARBITER_INPUT_CONTEXT_INCOMPLETE")
        blockers = list(structural_blockers)
        if not side_cell_key:
            blockers.append("SIDE_CELL_KEY_MISSING")
        evaluation = cohort_evaluator(
            side_cell_key,
            rows,
            cfg=cfg,
            overlay=overlay,
            edge_estimates=edge_estimates,
            expected_slippage=expected_slippage,
        )
        censored_count = evaluation["censored_count"]
        uncensored_row_count = evaluation["uncensored_row_count"]
        metrics = evaluation["metrics"]
        entries = evaluation["entries"]
        n_eff = len(entries)
        regime_entry_counts = {key: 0 for key in (*_REGIME_BUCKETS, "unknown")}
        for entry in entries:
            label = entry.get("evidence_regime_label")
            bucket = label if label in _REGIME_BUCKETS else "unknown"
            regime_entry_counts[bucket] += 1
        cluster = _day_cluster_stats(entries, expected_track_on=expected_slippage is not None)
        expected_cost_recomputable_count = sum(e.get("expected_cost_bps") is not None
                                               for e in entries)
        tail_cost_recomputable_count = sum(e.get("tail_cost_bps") is not None
                                           for e in entries)
        expected_cost_recomputable_share = (expected_cost_recomputable_count / n_eff
                                             if n_eff else 0.0)
        tail_cost_recomputable_share = (tail_cost_recomputable_count / n_eff
                                         if n_eff else 0.0)
        censored_share = metrics["censored_pct"] / 100.0
        invalid_outcome_row_count = uncensored_row_count - metrics["outcome_count"]
        top_entry_day_share = (metrics["top_entry_day_share_pct"] / 100.0
                               if metrics["top_entry_day_share_pct"] is not None else None)

        if n_eff < cfg.min_effective_entries_per_side_cell:
            blockers.append("EFFECTIVE_ENTRY_SAMPLE_INSUFFICIENT")
        if metrics["distinct_entry_utc_days"] < cfg.min_distinct_entry_utc_days:
            blockers.append("UTC_DAY_COVERAGE_INSUFFICIENT")
        if (
            metrics["top_entry_day_share_pct"] is not None
            and metrics["top_entry_day_share_pct"]
            > cfg.max_top_entry_day_share_pct
        ):
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

        family_key = _candidate_family_key(identity)
        regime_context = identity.get("target_regime_context")
        target_regime = ({**dict(regime_context), "hash": identity.get("target_regime_hash")}
                         if isinstance(regime_context, dict) else None)
        arbiter_identity = {
            "strategy_name": identity.get("strategy_name"),
            "strategy_version": identity.get("strategy_version"),
            "config_hash": identity.get("strategy_config_hash"),
            "symbol": identity.get("symbol"),
            "side": identity.get("side"),
            "horizon_minutes": identity.get("horizon_minutes"),
            "target_regime": target_regime,
            "engine_mode": "shadow",
            "evidence_engine_mode": identity.get("evidence_engine_mode"),
            "venue": identity.get("venue"),
            "product": identity.get("product"),
        }
        integrity_ok = bool(not metrics["data_integrity_suspect"]
                            and metrics["entry_ts_missing_row_count"] == 0
                            and invalid_outcome_row_count == 0 and cluster["clean"])
        unknown_regime_share = regime_entry_counts["unknown"] / n_eff if n_eff else 1.0
        arbiter_input = {
            "schema_version": ARBITER_INPUT_SCHEMA_VERSION,
            "identity": arbiter_identity,
            "context_hashes": context_hashes,
            "quality": {
                "hash_ok": identity_complete and not any(
                    "HASH_MISSING_OR_INVALID" in code for code in context_blockers),
                "integrity_ok": integrity_ok,
                "freshness_ok": "RESOURCE_DAILY_BUCKETS_INCOMPLETE" not in context_blockers,
                "censored_share": censored_share,
                "cost_recomputable_share": expected_cost_recomputable_share,
                "unknown_regime_share": unknown_regime_share,
                "replica_inconsistency_count": metrics["replica_inconsistent_group_count"],
                "cluster_variance_clean": cluster["clean"],
                "hidden_oos_consumed": hidden_oos is True,
                "top_day_share": top_entry_day_share if top_entry_day_share is not None else 1.0,
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
                "raw_attempt_count": len(rows),
                "regime_entry_counts": regime_entry_counts,
            },
            "resource": resource,
            "portfolio": portfolio,
        }
        candidate_rows.append(
            {
                "candidate_id": _canonical_sha256(
                    {"identity": arbiter_identity, "context_hashes": context_hashes}),
                "candidate_family_key": family_key,
                "candidate_identity": identity,
                "identity_complete": identity_complete,
                "arbiter_input": arbiter_input,
                "arbiter_input_complete": not structural_blockers,
                "selection_eligible": not blockers,
                "blockers": sorted(set(blockers)),
                "side_cell_key": side_cell_key,
                "horizon_minutes": identity.get("horizon_minutes"),
                "raw_outcome_count": len(rows),
                "uncensored_outcome_count": uncensored_row_count,
                "valid_uncensored_outcome_count": metrics["outcome_count"],
                "invalid_outcome_row_count": invalid_outcome_row_count,
                "distinct_entry_observation_count": metrics["distinct_entry_observation_count"],
                "duplicate_outcome_row_count": metrics["duplicate_outcome_row_count"],
                "window_overlap_excluded_entry_count": metrics["window_overlap_excluded_entry_count"],
                "entry_ts_missing_row_count": metrics["entry_ts_missing_row_count"],
                "n_eff": n_eff,
                "distinct_entry_utc_days": metrics["distinct_entry_utc_days"],
                "entry_day_counts": metrics["entry_day_counts"],
                "top_entry_utc_day": metrics["top_entry_utc_day"],
                "top_entry_day_share": top_entry_day_share,
                "top_entry_day_share_pct": metrics["top_entry_day_share_pct"],
                "censored_count": censored_count,
                "censored_share": censored_share,
                "censored_pct": metrics["censored_pct"],
                "replica_inconsistent_group_count": metrics["replica_inconsistent_group_count"],
                "zero_variance_suspect": metrics["zero_variance_suspect"],
                "data_integrity_suspect": metrics["data_integrity_suspect"],
                "cluster_variance_clean": cluster["clean"],
                "day_cluster_variance": cluster["variance"],
                "cluster_se": cluster["se"],
                "cluster_count": cluster["g"],
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
        )
    candidate_rows.sort(
        key=lambda row: (
            _str(row["candidate_identity"].get("strategy_name")),
            _str(row["candidate_identity"].get("strategy_version")),
            _str(row["candidate_identity"].get("strategy_config_hash")),
            _str(row["candidate_identity"].get("symbol")),
            _str(row["candidate_identity"].get("side")),
            _int(row["candidate_identity"].get("horizon_minutes")),
            _str(row["candidate_identity"].get("target_regime_hash")),
            _str(row["candidate_identity"].get("venue")),
            _str(row["candidate_identity"].get("product")),
            _str(row["candidate_identity"].get("engine_mode")),
            row["candidate_id"],
        )
    )
    board = {
        "schema_version": LEARNING_CANDIDATE_BOARD_SCHEMA_VERSION,
        "candidate_universe_complete": True,
        "candidate_rows": candidate_rows,
    }
    board["board_hash"] = _canonical_sha256(board)
    return board

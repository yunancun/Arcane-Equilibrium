"""MODULE_NOTE: WP2-A 純 candidate-aware learning arbiter。

本模組只回傳確定性的 shadow research 決策，不執行 I/O，也不持有訓練、
模型、serving、promotion 或下單權限。所有排序小數以 Decimal(prec=50,
ROUND_HALF_EVEN) 計算，對外固定為 q18 字串。
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext
from statistics import median
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "alr_candidate_learning_arbiter_v2"
ALGORITHM_VERSION = "candidate_learning_arbiter_v2"
TIE_BREAK_VERSION = "candidate_learning_tie_break_v1"
ARBITER_INPUT_SCHEMA_VERSION = "alr_candidate_arbiter_input_v2"
COST_EVIDENCE_SCHEMA_VERSION = "alr_candidate_cost_evidence_v2"
PRIOR_DECISION_SCHEMA_VERSION = "alr_candidate_learning_decision_v2"
_CANDIDATE_FAMILY_SCHEMA_VERSION = "candidate_learning_family_v2"
Q18_SCALE = 18
REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)
STATES = (
    "DECISION_READY",
    "COLLECT_DISTINCT_ENTRIES",
    "REPAIR_DATA_QUALITY",
    "WAIT_COOLDOWN",
    "EXTERNAL_GAP",
    "INELIGIBLE",
)

_Q18 = Decimal("0.000000000000000001")
_ZERO = Decimal(0)
_ONE = Decimal(1)
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_HEAD = re.compile(r"^[0-9a-f]{40}$")
_COST_EVIDENCE_FIELDS = {
    "schema_version", "basis", "source_payload_sha256", "source_asof_utc",
    "normalized_projection_sha256", "max_age_hours", "fee_floor_bps",
    "mean_abs_source", "tail_source",
}
_MEAN_ABS_SOURCE_FIELDS = {"scope", "symbol", "sample_count", "mean_abs_bps"}
_TAIL_SOURCE_FIELDS = {"scope", "symbol", "sample_count", "tail_bps", "tail_metric"}
_COST_EVIDENCE_MAX_AGE_HOURS = 48
_FEE_FLOOR_BPS = 11.0
_MIN_SYMBOL_FILLS = 20
_DIRECT_POLICY_FIELDS = {
    "decision_ts_s",
    "as_of_utc_date",
    "algorithm_version",
    "tie_break_version",
    "q18_scale",
    "thresholds",
    "row_budget",
    "byte_budget",
    "collection_window_days",
    "max_new_entries_per_window",
    "cooldown_seconds",
    "unknown_portfolio_penalty",
    "policy_config_hash",
}
_DIRECT_THRESHOLD_FIELDS = {
    "e1_n_eff_min",
    "e2_utc_days_min",
    "e3_top_day_share_max",
    "e4_censored_share_max",
}


class _InvalidCandidate(ValueError):
    """候選證據不完整；只在模組內轉成 fail-closed assessment。"""


def build_candidate_learning_decision(
    *,
    source_head: str,
    scanner_research_seeds: Sequence[Mapping[str, Any]],
    candidate_evidence_board: Sequence[Mapping[str, Any]],
    prior_decisions: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """建立一份無副作用、無交易權限的候選學習決策。"""

    policy_view = _validate_policy(policy)
    source_head_ok = isinstance(source_head, str) and bool(_SOURCE_HEAD.fullmatch(source_head))
    scanner_by_symbol = _scanner_context_by_symbol(scanner_research_seeds)

    assessments: list[dict[str, Any]] = []
    for candidate in candidate_evidence_board:
        try:
            candidate = _validate_arbiter_input(candidate)
            if policy_view is None:
                raise _InvalidCandidate("POLICY_INVALID")
            if not source_head_ok:
                raise _InvalidCandidate("SOURCE_HEAD_INVALID")
            assessment = _assess_candidate(
                candidate=candidate,
                source_head=source_head,
                scanner_by_symbol=scanner_by_symbol,
                policy=policy_view,
            )
            _apply_cooldown(
                assessment,
                prior_decisions=prior_decisions,
                decision_ts_s=policy_view["decision_ts_s"],
                cooldown_seconds=policy_view["cooldown_seconds"],
            )
        except _InvalidCandidate as exc:
            assessment = _ineligible_assessment(candidate, str(exc))
        assessments.append(assessment)

    assessments.sort(key=candidate_learning_assessment_rank_key_v2)
    for rank, assessment in enumerate(assessments, start=1):
        assessment["rank"] = rank

    ready = [item for item in assessments if item["state"] == "DECISION_READY"]
    collection = [
        item for item in assessments if item["state"] == "COLLECT_DISTINCT_ENTRIES"
    ]
    repair = [item for item in assessments if item["state"] == "REPAIR_DATA_QUALITY"]
    waiting = [item for item in assessments if item["state"] == "WAIT_COOLDOWN"]
    external = [item for item in assessments if item["state"] == "EXTERNAL_GAP"]
    selected = _selection_view(ready[0]) if ready else None
    selected_collection = _selection_view(collection[0]) if collection else None
    if selected is not None:
        decision = "QUALIFIED_CANDIDATE_SELECTED"
        state = "DECISION_READY"
    elif selected_collection is not None:
        decision = "NO_QUALIFIED_CANDIDATE_COLLECT"
        state = "COLLECT_DISTINCT_ENTRIES"
    elif repair:
        decision = "NO_QUALIFIED_CANDIDATE_REPAIR"
        state = "REPAIR_DATA_QUALITY"
    elif waiting:
        decision = "NO_QUALIFIED_CANDIDATE_WAIT"
        state = "WAIT_COOLDOWN"
    elif external:
        decision = "NO_QUALIFIED_CANDIDATE_EXTERNAL"
        state = "EXTERNAL_GAP"
    else:
        decision = "NO_QUALIFIED_CANDIDATE_ROTATE"
        state = "INELIGIBLE"
    result = _base_result()
    authority_counters = {
        key: value
        for key, value in result["authority"].items()
        if key.endswith("_count")
    }
    result.update(
        {
            "source_head": source_head,
            "policy_config_hash": (
                policy_view["policy_config_hash"] if policy_view else None
            ),
            "policy_hash": policy_view["policy_config_hash"] if policy_view else None,
            "decision": decision,
            "decision_code": decision,
            "state": state,
            "evaluated_at": (
                datetime.fromtimestamp(policy_view["decision_ts_s"], timezone.utc)
                .isoformat(timespec="seconds")
                .replace("+00:00", "Z")
                if policy_view
                else None
            ),
            "selected_candidate": selected,
            "selected_collection_target": selected_collection,
            "candidate_assessments": assessments,
            "evaluated_candidates": assessments,
            "candidate_count": len(assessments),
            "eligible_candidate_count": sum(
                1 for item in assessments if item["eligible"]
            ),
            "no_authority": {
                "training": False,
                "model": False,
                "serving": False,
                "promotion": False,
                "order": False,
            },
            "authority_counters": authority_counters,
        }
    )
    result["decision_hash"] = _canonical_sha256(result)
    return result


def _assess_candidate(
    *,
    candidate: Mapping[str, Any],
    source_head: str,
    scanner_by_symbol: Mapping[str, Mapping[str, str]],
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    identity = _validate_identity(candidate.get("identity"), policy["as_of_date"])
    context_hashes = _validate_context_hashes(candidate.get("context_hashes"))
    cost_evidence = _validate_cost_evidence(
        candidate.get("cost_evidence"),
        identity=identity,
        decision_ts_s=policy["decision_ts_s"],
    )
    quality = _validate_quality(candidate.get("quality"))
    if (
        cost_evidence["basis"] == "conservative_v1"
        and quality["cost_recomputable_share"] != _ZERO
    ):
        raise _InvalidCandidate("COST_EVIDENCE_QUALITY_MISMATCH")
    evidence = _validate_evidence(
        candidate.get("evidence"),
        cluster_variance_clean=quality["cluster_variance_clean"],
    )
    resource = _validate_resource(candidate.get("resource"), policy["as_of_date"])
    portfolio, portfolio_assumption = _validate_portfolio(
        candidate.get("portfolio"),
        allow_unknown=evidence["next_gap"]["kind"] == "LOCAL_PASSIVE",
        unknown_penalty=policy["unknown_portfolio_penalty"],
    )

    family_key = _canonical_sha256(
        {
            "schema_version": _CANDIDATE_FAMILY_SCHEMA_VERSION,
            "identity": {
                "strategy_name": identity["strategy_name"],
                "strategy_version": identity["strategy_version"],
                "strategy_config_hash": identity["config_hash"],
                "symbol": identity["symbol"],
                "side": identity["side"],
                "horizon_minutes": identity["horizon_minutes"],
                "venue": identity["venue"],
                "product": identity["product"],
                "evidence_engine_mode": identity["evidence_engine_mode"],
            },
        }
    )
    evaluation_id = _canonical_sha256(
        {
            "family_key": family_key,
            "target_regime_hash": identity["target_regime"]["hash"],
            "data_context_hash": context_hashes["data"],
            "evidence_context_hash": context_hashes["evidence"],
            "cost_context_hash": context_hashes["cost"],
            "portfolio_context_hash": context_hashes["portfolio"],
            "policy_config_hash": policy["policy_config_hash"],
        }
    )

    metrics = _evi_metrics(
        quality=quality,
        evidence=evidence,
        resource=resource,
        portfolio=portfolio,
        policy=policy,
    )
    scanner_context = scanner_by_symbol.get(
        identity["symbol"], {"novelty": _q18(_ZERO), "recurrence": _q18(_ZERO)}
    )
    state = "DECISION_READY"
    sample_blockers: list[str] = []
    quality_blockers: list[str] = []
    if evidence["n_eff"] < policy["n_eff_min"]:
        sample_blockers.append("N_EFF_BELOW_30")
    if evidence["utc_day_count"] < policy["utc_days_min"]:
        sample_blockers.append("UTC_DAY_COUNT_BELOW_5")
    if quality["top_day_share"] > policy["top_day_share_max"]:
        sample_blockers.append("TOP_DAY_SHARE_ABOVE_0_5")
    if quality["censored_share"] > policy["censored_share_max"]:
        quality_blockers.append("CENSORED_SHARE_ABOVE_0_3")
    if not quality["hash_ok"]:
        quality_blockers.append("HASH_CHECK_FAILED")
    if not quality["integrity_ok"]:
        quality_blockers.append("INTEGRITY_CHECK_FAILED")
    if not quality["freshness_ok"]:
        quality_blockers.append("FRESHNESS_CHECK_FAILED")
    if quality["cost_recomputable_share"] != _ONE:
        quality_blockers.append("COST_NOT_RECOMPUTABLE")
    if quality["replica_inconsistency_count"] != 0:
        quality_blockers.append("REPLICA_INCONSISTENT")
    if not quality["cluster_variance_clean"] or evidence["cluster_se"] <= _ZERO:
        quality_blockers.append("CLUSTER_VARIANCE_DEGENERATE")
    if quality["hidden_oos_consumed"]:
        quality_blockers.append("HIDDEN_OOS_CONSUMED")
    if quality["legacy_optimistic_cost_present"]:
        quality_blockers.append("LEGACY_OPTIMISTIC_COST_UNBACKFILLED")
    if quality["unknown_regime_share"] != evidence["unknown_regime_share"]:
        quality_blockers.append("UNKNOWN_REGIME_SHARE_MISMATCH")
    quality_blockers.extend(resource["blocker_codes"])
    if portfolio_assumption == "UNKNOWN":
        sample_blockers.append("PORTFOLIO_UNKNOWN")
    blocker_codes = quality_blockers + sample_blockers
    gap_kind = evidence["next_gap"]["kind"]
    if quality_blockers:
        state = "REPAIR_DATA_QUALITY"
    elif gap_kind == "EXTERNAL_OPERATOR":
        state = "EXTERNAL_GAP"
    elif gap_kind == "LOCAL_ENGINEERING":
        state = "REPAIR_DATA_QUALITY"
    elif sample_blockers:
        if resource["zero_resource"]:
            blocker_codes.append("ZERO_RESOURCE_NO_COLLECTION")
            state = "INELIGIBLE"
        else:
            state = "COLLECT_DISTINCT_ENTRIES"
    elif gap_kind == "LOCAL_PASSIVE":
        if resource["zero_resource"]:
            blocker_codes.append("ZERO_RESOURCE_NO_COLLECTION")
            state = "INELIGIBLE"
        else:
            state = "COLLECT_DISTINCT_ENTRIES"
    material_fingerprint = _canonical_sha256(
        {
            "algorithm_version": ALGORITHM_VERSION,
            "source_head": source_head,
            # The already-validated v2 input hash commits every exact identity,
            # context, cost-evidence, quality, evidence, resource, and portfolio
            # field.  Using
            # it as the material boundary avoids a hand-maintained field list
            # silently treating a decision-active delta as unchanged.
            "arbiter_input_hash": candidate["arbiter_input_hash"],
            "policy_config_hash": policy["policy_config_hash"],
            "scanner_context": dict(scanner_context),
        }
    )
    return {
        "family_key": family_key,
        "evaluation_id": evaluation_id,
        "material_fingerprint": material_fingerprint,
        "identity": identity,
        "context_hashes": context_hashes,
        "proof_stage": evidence["proof_stage"],
        "next_gap": evidence["next_gap"],
        "learning_only": evidence["bull_heavy"],
        "state": state,
        "eligible": state == "DECISION_READY",
        "blocker_codes": blocker_codes,
        "portfolio_assumption": portfolio_assumption,
        "scanner_context": dict(scanner_context),
        "metrics": metrics,
    }


def _validate_policy(policy: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        if not isinstance(policy, Mapping):
            return None
        if set(policy) != _DIRECT_POLICY_FIELDS:
            return None
        body = dict(policy)
        supplied_hash = body.pop("policy_config_hash")
        stable_config = {
            key: value
            for key, value in body.items()
            if key not in {"decision_ts_s", "as_of_utc_date"}
        }
        if (
            not _is_hash(supplied_hash)
            or supplied_hash != _canonical_sha256(stable_config)
            or body["algorithm_version"] != ALGORITHM_VERSION
            or body["tie_break_version"] != TIE_BREAK_VERSION
            or body["q18_scale"] != Q18_SCALE
        ):
            return None
        decision_ts_s = _positive_int(body["decision_ts_s"])
        as_of_date = date.fromisoformat(str(body["as_of_utc_date"]))
        if datetime.fromtimestamp(decision_ts_s, timezone.utc).date() != as_of_date:
            return None
        thresholds = body["thresholds"]
        if (
            not isinstance(thresholds, Mapping)
            or set(thresholds) != _DIRECT_THRESHOLD_FIELDS
        ):
            return None
        n_eff_min = _positive_int(thresholds["e1_n_eff_min"])
        utc_days_min = _positive_int(thresholds["e2_utc_days_min"])
        top_day_max = _bounded_decimal(thresholds["e3_top_day_share_max"])
        censored_max = _bounded_decimal(thresholds["e4_censored_share_max"])
        if (
            n_eff_min != 30
            or utc_days_min != 5
            or top_day_max != Decimal("0.5")
            or censored_max != Decimal("0.3")
        ):
            return None
        row_budget = _positive_int(body["row_budget"])
        byte_budget = _positive_int(body["byte_budget"])
        window_days = _positive_int(body["collection_window_days"])
        max_new = _positive_int(body["max_new_entries_per_window"])
        cooldown = _positive_int(body["cooldown_seconds"])
        if cooldown != 1_800:
            return None
        unknown_penalty_raw = body["unknown_portfolio_penalty"]
        if not isinstance(unknown_penalty_raw, str):
            return None
        unknown_penalty = _bounded_decimal(unknown_penalty_raw)
        if unknown_penalty_raw != _canonical_decimal_string(unknown_penalty):
            return None
    except (KeyError, TypeError, ValueError, InvalidOperation):
        return None
    return {
        "policy_config_hash": supplied_hash,
        "decision_ts_s": decision_ts_s,
        "as_of_date": as_of_date,
        "row_budget": row_budget,
        "byte_budget": byte_budget,
        "collection_window_days": window_days,
        "max_new_entries_per_window": max_new,
        "cooldown_seconds": cooldown,
        "unknown_portfolio_penalty": unknown_penalty,
        "n_eff_min": n_eff_min,
        "utc_days_min": utc_days_min,
        "top_day_share_max": top_day_max,
        "censored_share_max": censored_max,
    }


def _validate_arbiter_input(candidate: Any) -> Mapping[str, Any]:
    if not isinstance(candidate, Mapping):
        raise _InvalidCandidate("ARBITER_INPUT_NOT_MAPPING")
    if candidate.get("schema_version") != ARBITER_INPUT_SCHEMA_VERSION:
        raise _InvalidCandidate("ARBITER_INPUT_SCHEMA_INVALID")
    if set(candidate) != {
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
        raise _InvalidCandidate("ARBITER_INPUT_FIELDS_INVALID")
    supplied_hash = candidate.get("arbiter_input_hash")
    if not _is_hash(supplied_hash):
        raise _InvalidCandidate("ARBITER_INPUT_HASH_INVALID")
    body = {
        str(key): value
        for key, value in candidate.items()
        if key != "arbiter_input_hash"
    }
    try:
        expected_hash = _canonical_sha256(body)
    except (TypeError, ValueError):
        raise _InvalidCandidate("ARBITER_INPUT_CANONICAL_JSON_INVALID") from None
    if supplied_hash != expected_hash:
        raise _InvalidCandidate("ARBITER_INPUT_HASH_MISMATCH")
    return candidate


def _validate_identity(value: Any, as_of_date: date) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _InvalidCandidate("IDENTITY_INCOMPLETE")
    if set(value) != {
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
    }:
        raise _InvalidCandidate("IDENTITY_FIELDS_INVALID")
    required_text = ("strategy_name", "symbol", "engine_mode", "venue", "product")
    normalized: dict[str, Any] = {}
    for key in required_text:
        item = value.get(key)
        if (
            not isinstance(item, str)
            or not item
            or item != item.strip()
        ):
            raise _InvalidCandidate("IDENTITY_INCOMPLETE")
        normalized[key] = item
    strategy_version = value.get("strategy_version")
    if not isinstance(strategy_version, str) or not _SOURCE_HEAD.fullmatch(
        strategy_version
    ):
        raise _InvalidCandidate("STRATEGY_VERSION_INVALID")
    normalized["strategy_version"] = strategy_version
    if normalized["symbol"] != normalized["symbol"].upper():
        raise _InvalidCandidate("SYMBOL_INVALID")
    if (normalized["venue"], normalized["product"]) != (
        "bybit",
        "linear_perpetual",
    ):
        raise _InvalidCandidate("MARKET_IDENTITY_INVALID")
    if normalized["engine_mode"] != "shadow":
        raise _InvalidCandidate("ENGINE_MODE_NOT_SHADOW")
    evidence_engine_mode = value.get("evidence_engine_mode")
    if evidence_engine_mode not in {"demo", "live_demo"}:
        raise _InvalidCandidate("EVIDENCE_ENGINE_MODE_INVALID")
    normalized["evidence_engine_mode"] = evidence_engine_mode
    config_hash = value.get("config_hash")
    if not _is_hash(config_hash):
        raise _InvalidCandidate("CONFIG_HASH_INVALID")
    normalized["config_hash"] = config_hash
    side = value.get("side")
    if side not in {"Buy", "Sell"}:
        raise _InvalidCandidate("SIDE_INVALID")
    normalized["side"] = side
    try:
        normalized["horizon_minutes"] = _positive_int(value.get("horizon_minutes"))
    except ValueError:
        raise _InvalidCandidate("HORIZON_INVALID") from None
    if normalized["horizon_minutes"] > 1_440:
        raise _InvalidCandidate("HORIZON_INVALID")
    regime = value.get("target_regime")
    if not isinstance(regime, Mapping) or set(regime) != {
        "label",
        "utc_date",
        "hash",
        "point_in_time",
        "source_complete",
        "source_hash",
        "classifier_hash",
    }:
        raise _InvalidCandidate("TARGET_REGIME_INVALID")
    try:
        regime_date = date.fromisoformat(str(regime["utc_date"]))
    except (KeyError, ValueError):
        raise _InvalidCandidate("TARGET_REGIME_INVALID") from None
    if (
        regime.get("point_in_time") != "D-1"
        or regime_date != as_of_date - timedelta(days=1)
        or not _is_hash(regime.get("hash"))
        or regime.get("label") not in REGIME_BUCKETS
        or regime.get("utc_date") != regime_date.isoformat()
        or regime.get("source_complete") is not True
        or not _is_hash(regime.get("source_hash"))
        or not _is_hash(regime.get("classifier_hash"))
    ):
        raise _InvalidCandidate("TARGET_REGIME_INVALID")
    target_body = {
        key: regime[key]
        for key in (
            "label",
            "utc_date",
            "point_in_time",
            "source_complete",
            "source_hash",
            "classifier_hash",
        )
    }
    if regime["hash"] != _canonical_sha256(target_body):
        raise _InvalidCandidate("TARGET_REGIME_HASH_INVALID")
    normalized["target_regime"] = {
        "label": regime["label"],
        "utc_date": regime_date.isoformat(),
        "hash": regime["hash"],
        "point_in_time": "D-1",
        "source_complete": True,
        "source_hash": regime["source_hash"],
        "classifier_hash": regime["classifier_hash"],
    }
    return normalized


def _validate_context_hashes(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise _InvalidCandidate("CONTEXT_HASHES_INCOMPLETE")
    if set(value) != {"data", "evidence", "cost", "portfolio"}:
        raise _InvalidCandidate("CONTEXT_HASHES_FIELDS_INVALID")
    result: dict[str, str] = {}
    for key in ("data", "evidence", "cost", "portfolio"):
        item = value.get(key)
        if not _is_hash(item):
            raise _InvalidCandidate("CONTEXT_HASHES_INCOMPLETE")
        result[key] = item
    return result


def _validate_cost_evidence(
    value: Any,
    *,
    identity: Mapping[str, Any],
    decision_ts_s: int,
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != _COST_EVIDENCE_FIELDS:
        raise _InvalidCandidate("COST_EVIDENCE_FIELDS_INVALID")
    if (
        value.get("schema_version") != COST_EVIDENCE_SCHEMA_VERSION
        or type(value.get("max_age_hours")) is not int
        or value["max_age_hours"] != _COST_EVIDENCE_MAX_AGE_HOURS
        or type(value.get("fee_floor_bps")) is not float
        or value["fee_floor_bps"] != _FEE_FLOOR_BPS
    ):
        raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    mean_source = value.get("mean_abs_source")
    tail_source = value.get("tail_source")
    if (
        not isinstance(mean_source, Mapping)
        or set(mean_source) != _MEAN_ABS_SOURCE_FIELDS
        or not isinstance(tail_source, Mapping)
        or set(tail_source) != _TAIL_SOURCE_FIELDS
    ):
        raise _InvalidCandidate("COST_EVIDENCE_FIELDS_INVALID")
    basis = value.get("basis")
    if basis == "conservative_v1":
        if (
            value.get("source_payload_sha256") is not None
            or value.get("source_asof_utc") is not None
            or value.get("normalized_projection_sha256") is not None
            or type(mean_source.get("sample_count")) is not int
            or mean_source["sample_count"] != 0
            or type(tail_source.get("sample_count")) is not int
            or tail_source["sample_count"] != 0
            or dict(mean_source)
            != {
                "scope": "NONE",
                "symbol": None,
                "sample_count": 0,
                "mean_abs_bps": None,
            }
            or dict(tail_source)
            != {
                "scope": "NONE",
                "symbol": None,
                "sample_count": 0,
                "tail_bps": None,
                "tail_metric": None,
            }
        ):
            raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
        return dict(value)
    if basis != "expected_slippage_mean_abs_v1":
        raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    if (
        not _is_hash(value.get("source_payload_sha256"))
        or not _is_hash(value.get("normalized_projection_sha256"))
    ):
        raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    try:
        source_asof = datetime.fromisoformat(value["source_asof_utc"])
    except (TypeError, ValueError):
        raise _InvalidCandidate("COST_EVIDENCE_TIMESTAMP_INVALID") from None
    if (
        source_asof.tzinfo is None
        or source_asof.utcoffset() != timedelta(0)
        or value["source_asof_utc"] != source_asof.isoformat()
    ):
        raise _InvalidCandidate("COST_EVIDENCE_TIMESTAMP_INVALID")
    age_seconds = (
        datetime.fromtimestamp(decision_ts_s, timezone.utc) - source_asof
    ).total_seconds()
    if age_seconds < 0.0:
        raise _InvalidCandidate("COST_EVIDENCE_FROM_FUTURE")
    if age_seconds > value["max_age_hours"] * 3600:
        raise _InvalidCandidate("COST_EVIDENCE_STALE")
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
                source.get("symbol") != identity["symbol"]
                or count < _MIN_SYMBOL_FILLS
            )
            or statistic is not None
            and (
                type(statistic) is not float
                or not math.isfinite(statistic)
                or statistic < 0.0
            )
        ):
            raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    if mean_source["mean_abs_bps"] is None:
        raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    tail_metric = tail_source.get("tail_metric")
    if (tail_source["tail_bps"] is None) is not (tail_metric is None) or (
        tail_metric is not None
        and tail_metric not in {"cvar90", "q90_fallback"}
    ):
        raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    if (
        mean_source["scope"] == tail_source["scope"]
        and mean_source["symbol"] == tail_source["symbol"]
        and mean_source["sample_count"] != tail_source["sample_count"]
    ):
        raise _InvalidCandidate("COST_EVIDENCE_SEMANTICS_INVALID")
    return dict(value)


def _validate_quality(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _InvalidCandidate("QUALITY_INCOMPLETE")
    if set(value) != {
        "hash_ok",
        "integrity_ok",
        "freshness_ok",
        "censored_share",
        "cost_recomputable_share",
        "unknown_regime_share",
        "replica_inconsistency_count",
        "cluster_variance_clean",
        "hidden_oos_consumed",
        "legacy_optimistic_cost_present",
        "top_day_share",
    }:
        raise _InvalidCandidate("QUALITY_FIELDS_INVALID")
    try:
        result = {
            key: _strict_bool(value[key])
            for key in ("hash_ok", "integrity_ok", "freshness_ok")
        }
        result.update(
            {
                "censored_share": _strict_float_decimal(
                    value["censored_share"], bounded=True
                ),
                "cost_recomputable_share": _strict_float_decimal(
                    value["cost_recomputable_share"]
                    , bounded=True
                ),
                "unknown_regime_share": _strict_float_decimal(
                    value["unknown_regime_share"], bounded=True
                ),
                "replica_inconsistency_count": _nonnegative_int(
                    value["replica_inconsistency_count"]
                ),
                "cluster_variance_clean": _strict_bool(
                    value["cluster_variance_clean"]
                ),
                "hidden_oos_consumed": _strict_bool(value["hidden_oos_consumed"]),
                "legacy_optimistic_cost_present": _strict_bool(
                    value["legacy_optimistic_cost_present"]
                ),
                "top_day_share": _strict_float_decimal(
                    value["top_day_share"], bounded=True
                ),
            }
        )
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise _InvalidCandidate("QUALITY_TYPES_INVALID") from None
    return result


def _validate_evidence(
    value: Any,
    *,
    cluster_variance_clean: bool,
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _InvalidCandidate("EVIDENCE_INCOMPLETE")
    if set(value) != {
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
    }:
        raise _InvalidCandidate("EVIDENCE_FIELDS_INVALID")
    try:
        n_eff = _nonnegative_int(value["n_eff"])
        utc_day_count = _nonnegative_int(value["utc_day_count"])
        mean_net_e = _strict_nullable_float_decimal(value["mean_net_e"])
        day_cluster_variance = _strict_nullable_float_decimal(
            value["day_cluster_variance"]
        )
        cluster_se = _strict_nullable_float_decimal(value["cluster_se"])
        cluster_count = _nonnegative_int(value["cluster_count"])
        proof_stage = _nonnegative_int(value["proof_stage"])
        stages_raw = value["completed_proof_stages"]
        if not isinstance(stages_raw, list):
            raise _InvalidCandidate("PROOF_PREFIX_INVALID")
        stages = list(stages_raw)
        if proof_stage > 6 or stages != list(range(proof_stage + 1)):
            raise _InvalidCandidate("PROOF_PREFIX_INVALID")
        next_gap = value["next_gap"]
        if not isinstance(next_gap, Mapping) or set(next_gap) != {"kind", "code"}:
            raise _InvalidCandidate("NEXT_GAP_INVALID")
        gap_kind = next_gap.get("kind")
        gap_code = next_gap.get("code")
        if gap_kind not in {"NONE", "LOCAL_PASSIVE", "LOCAL_ENGINEERING", "EXTERNAL_OPERATOR"}:
            raise _InvalidCandidate("NEXT_GAP_INVALID")
        if (
            not isinstance(gap_code, str)
            or not gap_code
            or gap_code != gap_code.strip()
        ):
            raise _InvalidCandidate("NEXT_GAP_INVALID")
        regime_counts = value["regime_entry_counts"]
        if not isinstance(regime_counts, Mapping) or set(regime_counts) != {
            *REGIME_BUCKETS,
            "unknown",
        }:
            raise _InvalidCandidate("REGIME_COUNTS_INVALID")
        normalized_regimes = {
            key: _nonnegative_int(regime_counts[key])
            for key in (*REGIME_BUCKETS, "unknown")
        }
        if sum(normalized_regimes.values()) != n_eff:
            raise _InvalidCandidate("REGIME_COUNTS_N_EFF_MISMATCH")
        raw_attempt_count = _nonnegative_int(value["raw_attempt_count"])
        if (
            raw_attempt_count < n_eff
            or cluster_count != utc_day_count
            or cluster_count > n_eff
            or (n_eff == 0) is not (mean_net_e is None)
            or (
                cluster_variance_clean
                and (
                    day_cluster_variance is None
                    or cluster_se is None
                    or day_cluster_variance <= _ZERO
                    or cluster_se <= _ZERO
                    or cluster_se
                    != Decimal(str(math.sqrt(float(day_cluster_variance))))
                )
            )
            or (
                not cluster_variance_clean
                and (
                    cluster_se is not None
                    or day_cluster_variance not in {None, _ZERO}
                )
            )
        ):
            raise _InvalidCandidate("EVIDENCE_ALGEBRA_INVALID")
    except _InvalidCandidate:
        raise
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise _InvalidCandidate("EVIDENCE_TYPES_INVALID") from None
    regime_metrics = _regime_metrics(normalized_regimes, n_eff)
    return {
        "n_eff": n_eff,
        "utc_day_count": utc_day_count,
        "mean_net_e": mean_net_e,
        "day_cluster_variance": day_cluster_variance,
        "cluster_se": cluster_se,
        "cluster_count": cluster_count,
        "proof_stage": proof_stage,
        "completed_proof_stages": stages,
        "next_gap": {"kind": gap_kind, "code": gap_code},
        "raw_attempt_count": raw_attempt_count,
        "regime_entry_counts": normalized_regimes,
        **regime_metrics,
    }


def _regime_metrics(counts: Mapping[str, int], n_eff: int) -> dict[str, Any]:
    known_total = n_eff - counts["unknown"]
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        unknown_share = (
            _ZERO if n_eff == 0 else Decimal(counts["unknown"]) / Decimal(n_eff)
        )
        if known_total == 0:
            coverage = _ZERO
            bull_share = _ZERO
        else:
            probabilities = [
                Decimal(counts[key]) / Decimal(known_total)
                for key in REGIME_BUCKETS
                if counts[key] > 0
            ]
            entropy = -sum((probability * probability.ln() for probability in probabilities), _ZERO)
            coverage = entropy / Decimal(len(REGIME_BUCKETS)).ln()
            bull_count = sum(
                counts[key] for key in REGIME_BUCKETS if key.startswith("bull|")
            )
            bull_share = Decimal(bull_count) / Decimal(known_total)
    return {
        "unknown_regime_share": unknown_share,
        "regime_coverage": coverage,
        "bull_share": bull_share,
        "bull_heavy": bull_share > Decimal("0.6"),
    }


def _validate_resource(value: Any, as_of_date: date) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise _InvalidCandidate("RESOURCE_INCOMPLETE")
    if set(value) != {
        "daily_buckets",
        "estimated_rows_scanned",
        "predicted_canonical_bytes",
        "zero_resource_attested",
        "resource_estimator_hash",
    }:
        raise _InvalidCandidate("RESOURCE_FIELDS_INVALID")
    buckets = value.get("daily_buckets")
    if not isinstance(buckets, Sequence) or isinstance(buckets, (str, bytes)):
        raise _InvalidCandidate("RESOURCE_INCOMPLETE")
    expected_dates = [as_of_date - timedelta(days=offset) for offset in range(7, 0, -1)]
    normalized: list[dict[str, Any]] = []
    try:
        for expected_date, bucket in zip(expected_dates, buckets, strict=False):
            if not isinstance(bucket, Mapping):
                raise _InvalidCandidate("RESOURCE_INCOMPLETE")
            if set(bucket) != {"utc_date", "scan_complete", "distinct_entries"}:
                raise _InvalidCandidate("RESOURCE_BUCKET_FIELDS_INVALID")
            if date.fromisoformat(str(bucket["utc_date"])) != expected_date:
                raise _InvalidCandidate("RESOURCE_DAYS_INCOMPLETE")
            if _strict_bool(bucket["scan_complete"]) is not True:
                raise _InvalidCandidate("RESOURCE_DAYS_UNPROVEN")
            normalized.append(
                {
                    "utc_date": expected_date.isoformat(),
                    "scan_complete": True,
                    "distinct_entries": _nonnegative_int(bucket["distinct_entries"]),
                }
            )
        rows = _nonnegative_int(value["estimated_rows_scanned"])
        byte_count = _nonnegative_int(value["predicted_canonical_bytes"])
        zero_attested = _strict_bool(value["zero_resource_attested"])
    except _InvalidCandidate:
        raise
    except (KeyError, TypeError, ValueError):
        raise _InvalidCandidate("RESOURCE_INCOMPLETE") from None
    if len(buckets) != 7 or len(normalized) != 7:
        raise _InvalidCandidate("RESOURCE_DAYS_INCOMPLETE")
    estimator_payload = {
        "daily_buckets": normalized,
        "estimated_rows_scanned": rows,
        "predicted_canonical_bytes": byte_count,
        "zero_resource_attested": zero_attested,
    }
    if value.get("resource_estimator_hash") != _canonical_sha256(estimator_payload):
        raise _InvalidCandidate("RESOURCE_ESTIMATOR_HASH_INVALID")
    total_entries = sum(bucket["distinct_entries"] for bucket in normalized)
    if (
        (rows == 0) != (byte_count == 0)
        or rows == 0
        and (not zero_attested or total_entries > 0)
        or rows > 0
        and zero_attested
    ):
        raise _InvalidCandidate("RESOURCE_SEMANTICS_INVALID")
    return {
        **estimator_payload,
        "resource_estimator_hash": value["resource_estimator_hash"],
        "zero_resource": rows == 0 and byte_count == 0,
        "blocker_codes": [],
    }


def _validate_portfolio(
    value: Any, *, allow_unknown: bool, unknown_penalty: Decimal
) -> tuple[dict[str, Decimal], str]:
    if not isinstance(value, Mapping):
        if allow_unknown:
            return {
                "sector_exposure_share": unknown_penalty,
                "strategy_active_target_share": unknown_penalty,
                "beta_to_portfolio": unknown_penalty,
            }, "UNKNOWN"
        raise _InvalidCandidate("PORTFOLIO_INCOMPLETE")
    if set(value) != {
        "sector_exposure_share",
        "strategy_active_target_share",
        "beta_to_portfolio",
    }:
        raise _InvalidCandidate("PORTFOLIO_FIELDS_INVALID")
    try:
        result = {
            "sector_exposure_share": _canonical_decimal_input(
                value["sector_exposure_share"], bounded=True
            ),
            "strategy_active_target_share": _canonical_decimal_input(
                value["strategy_active_target_share"], bounded=True
            ),
            "beta_to_portfolio": _canonical_decimal_input(
                value["beta_to_portfolio"]
            ),
        }
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise _InvalidCandidate("PORTFOLIO_TYPES_INVALID") from None
    return result, "MEASURED"


def _evi_metrics(
    *,
    quality: Mapping[str, Any],
    evidence: Mapping[str, Any],
    resource: Mapping[str, Any],
    portfolio: Mapping[str, Decimal],
    policy: Mapping[str, Any],
) -> dict[str, str]:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        counts = [bucket["distinct_entries"] for bucket in resource["daily_buckets"]]
        rate = Decimal(median(counts))
        expected_new = min(
            policy["max_new_entries_per_window"],
            int(rate * policy["collection_window_days"]),
        )
        n_eff = evidence["n_eff"]
        information_gain = Decimal("0.5") * (
            (Decimal(1 + n_eff + expected_new) / Decimal(1 + n_eff)).ln()
        )
        n_eff_min = policy["n_eff_min"]
        gate_progress = (
            _ONE
            if n_eff >= n_eff_min
            else min(
                _ONE,
                Decimal(expected_new) / Decimal(max(1, n_eff_min - n_eff)),
            )
        )
        if quality["cluster_variance_clean"] and evidence["cluster_se"] != _ZERO:
            ratio = evidence["mean_net_e"] / evidence["cluster_se"]
            ambiguity = (Decimal("-0.5") * ratio * ratio).exp()
        else:
            ambiguity = _ONE
        quality_factor = (
            Decimal(int(quality["hash_ok"]))
            * Decimal(int(quality["integrity_ok"]))
            * Decimal(int(quality["freshness_ok"]))
            * (_ONE - quality["censored_share"])
            * quality["cost_recomputable_share"]
            * (_ONE - evidence["unknown_regime_share"])
        )
        rows = resource["estimated_rows_scanned"]
        byte_count = resource["predicted_canonical_bytes"]
        compute = min(_ONE, Decimal(rows) / Decimal(policy["row_budget"]))
        storage = min(_ONE, Decimal(byte_count) / Decimal(policy["byte_budget"]))
        resource_factor = (compute + storage) / Decimal(2)
        portfolio_factor = max(
            portfolio["sector_exposure_share"],
            portfolio["strategy_active_target_share"],
            abs(portfolio["beta_to_portfolio"]),
        )
        evi = (
            information_gain
            * gate_progress
            * ambiguity
            * quality_factor
            / ((_ONE + resource_factor) * (_ONE + portfolio_factor))
        )
    return {
        "n_eff": _q18(Decimal(n_eff)),
        "median_distinct_entries_7d": _q18(rate),
        "expected_new_entries": _q18(Decimal(expected_new)),
        "information_gain": _q18(information_gain),
        "gate_progress": _q18(gate_progress),
        "ambiguity": _q18(ambiguity),
        "quality": _q18(quality_factor),
        "compute": _q18(compute),
        "storage": _q18(storage),
        "resource": _q18(resource_factor),
        "portfolio_redundancy": _q18(portfolio_factor),
        "day_coverage": _q18(
            min(_ONE, Decimal(evidence["utc_day_count"]) / policy["utc_days_min"])
        ),
        "day_deficit": _q18(
            _ONE
            - min(_ONE, Decimal(evidence["utc_day_count"]) / policy["utc_days_min"])
        ),
        "regime_coverage": _q18(evidence["regime_coverage"]),
        "regime_deficit": _q18(_ONE - evidence["regime_coverage"]),
        "bull_share": _q18(evidence["bull_share"]),
        "evi": _q18(evi),
    }


def _scanner_context_by_symbol(
    seeds: Sequence[Mapping[str, Any]],
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for seed in seeds:
        if not isinstance(seed, Mapping):
            continue
        symbol = seed.get("symbol")
        if not isinstance(symbol, str) or not symbol:
            continue
        try:
            novelty = _decimal(seed.get("novelty", 0))
            recurrence = _decimal(seed.get("recurrence", 0))
        except (TypeError, ValueError, InvalidOperation):
            continue
        current = result.get(symbol)
        if current is None or (novelty, recurrence) > (
            Decimal(current["novelty"]),
            Decimal(current["recurrence"]),
        ):
            result[symbol] = {"novelty": _q18(novelty), "recurrence": _q18(recurrence)}
    return result


def _apply_cooldown(
    assessment: dict[str, Any],
    *,
    prior_decisions: Sequence[Mapping[str, Any]],
    decision_ts_s: int,
    cooldown_seconds: int,
) -> None:
    chronological: list[Mapping[str, Any]] = []
    for prior in prior_decisions:
        if not isinstance(prior, Mapping):
            continue
        if prior.get("decision_schema_version") != PRIOR_DECISION_SCHEMA_VERSION:
            continue
        prior_ts = prior.get("decision_ts_s")
        if isinstance(prior_ts, bool) or not isinstance(prior_ts, int):
            continue
        chronological.append(prior)
    if any(int(prior["decision_ts_s"]) > decision_ts_s for prior in chronological):
        assessment["state"] = "REPAIR_DATA_QUALITY"
        assessment["eligible"] = False
        assessment["blocker_codes"].append("PRIOR_DECISION_FROM_FUTURE")
        return
    if assessment["state"] not in {"DECISION_READY", "COLLECT_DISTINCT_ENTRIES"}:
        return
    if not chronological:
        return
    latest_global = max(
        chronological,
        key=lambda item: (int(item["decision_ts_s"]), _canonical_sha256(dict(item))),
    )
    consecutive_same_family = (
        latest_global.get("family_key") == assessment["family_key"]
        and latest_global.get("material_fingerprint")
        == assessment["material_fingerprint"]
    )
    matching = [
        prior
        for prior in chronological
        if prior.get("family_key") == assessment["family_key"]
        and prior.get("material_fingerprint") == assessment["material_fingerprint"]
    ]
    latest_matching = (
        max(
            matching,
            key=lambda item: (int(item["decision_ts_s"]), _canonical_sha256(dict(item))),
        )
        if matching
        else None
    )
    age = (
        decision_ts_s - int(latest_matching["decision_ts_s"])
        if latest_matching is not None
        else cooldown_seconds
    )
    if consecutive_same_family or age < cooldown_seconds:
        assessment["state"] = "WAIT_COOLDOWN"
        assessment["eligible"] = False
        assessment["blocker_codes"].append(
            "CONSECUTIVE_FAMILY_NO_MATERIAL_DELTA"
            if consecutive_same_family and age >= cooldown_seconds
            else "COOLDOWN_ACTIVE"
        )
        assessment["cooldown_remaining_seconds"] = max(0, cooldown_seconds - age)


def candidate_learning_assessment_rank_key_v2(
    item: Mapping[str, Any],
) -> tuple[Any, ...]:
    """Canonical v2 assessment order, reusable by durable decision validators."""
    state = item.get("state")
    state_priority = {
        "DECISION_READY": 0,
        "COLLECT_DISTINCT_ENTRIES": 1,
        "REPAIR_DATA_QUALITY": 2,
        "WAIT_COOLDOWN": 3,
        "EXTERNAL_GAP": 4,
        "INELIGIBLE": 5,
    }.get(state, 6)
    metrics = item.get("metrics")
    family_key = str(item.get("family_key", "~"))
    evaluation_id = str(item.get("evaluation_id", "~"))
    canonical_tie = _canonical_sha256(
        {key: value for key, value in item.items() if key != "rank"}
    )
    slots = [_ZERO] * 10
    metrics_missing = Decimal(1)
    if not isinstance(metrics, Mapping):
        return (
            state_priority,
            metrics_missing,
            *slots,
            family_key,
            evaluation_id,
            canonical_tie,
        )
    metrics_missing = _ZERO
    if state == "DECISION_READY":
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
    elif state == "COLLECT_DISTINCT_ENTRIES":
        scanner = item.get("scanner_context")
        recurrence = Decimal(scanner["recurrence"]) if isinstance(scanner, Mapping) else _ZERO
        novelty = Decimal(scanner["novelty"]) if isinstance(scanner, Mapping) else _ZERO
        slots[:7] = [
            -Decimal(metrics["evi"]),
            -Decimal(metrics["day_deficit"]),
            -Decimal(metrics["regime_deficit"]),
            Decimal(metrics["resource"]),
            Decimal(metrics["portfolio_redundancy"]),
            -recurrence,
            -novelty,
        ]
    else:
        scanner = item.get("scanner_context")
        novelty = Decimal(scanner["novelty"]) if isinstance(scanner, Mapping) else _ZERO
        slots[:2] = [-Decimal(metrics["evi"]), -novelty]
    return (
        state_priority,
        metrics_missing,
        *slots,
        family_key,
        evaluation_id,
        canonical_tie,
    )


def _selection_view(assessment: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "family_key": assessment["family_key"],
        "candidate_family_key": assessment["family_key"],
        "evaluation_id": assessment["evaluation_id"],
        "candidate_eval_id": assessment["evaluation_id"],
        "material_fingerprint": assessment["material_fingerprint"],
        "state": assessment["state"],
        "identity": assessment["identity"],
        "context_hashes": assessment["context_hashes"],
        "proof_stage": assessment["proof_stage"],
        "next_gap": assessment["next_gap"],
        "blocker_codes": list(assessment["blocker_codes"]),
        "metrics": assessment["metrics"],
        "portfolio_assumption": assessment["portfolio_assumption"],
        "learning_only": assessment["learning_only"],
        "evi": assessment["metrics"]["evi"],
    }


def _ineligible_assessment(candidate: Any, code: str) -> dict[str, Any]:
    identity = candidate.get("identity") if isinstance(candidate, Mapping) else None
    return {
        "family_key": None,
        "evaluation_id": None,
        "material_fingerprint": None,
        "identity": dict(identity) if isinstance(identity, Mapping) else None,
        "state": "INELIGIBLE",
        "eligible": False,
        "blocker_codes": [code],
        "portfolio_assumption": None,
        "scanner_context": {"novelty": _q18(_ZERO), "recurrence": _q18(_ZERO)},
        "metrics": None,
    }


def _base_result() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "tie_break_version": TIE_BREAK_VERSION,
        "decision": "NO_QUALIFIED_CANDIDATE_ROTATE",
        "state": "INELIGIBLE",
        "selected_candidate": None,
        "selected_collection_target": None,
        "candidate_assessments": [],
        "authority": {
            "has_training_authority": False,
            "has_model_authority": False,
            "has_serving_authority": False,
            "has_promotion_authority": False,
            "has_order_authority": False,
            "training_action_count": 0,
            "model_mutation_count": 0,
            "serving_mutation_count": 0,
            "promotion_action_count": 0,
            "order_attempt_count": 0,
        },
    }


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _q18(value: Decimal) -> str:
    with localcontext() as context:
        context.prec = 50
        context.rounding = ROUND_HALF_EVEN
        return format(value.quantize(_Q18), "f")


def _decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ValueError("not a decimal")
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError("decimal must be finite")
    return result


def _bounded_decimal(value: Any) -> Decimal:
    result = _decimal(value)
    if result < _ZERO or result > _ONE:
        raise ValueError("decimal outside [0,1]")
    return result


def _strict_float_decimal(value: Any, *, bounded: bool = False) -> Decimal:
    """只接受 producer JSON float；拒絕字串/整數 coercion 擴大 v2 ingress。"""
    if type(value) is not float:
        raise ValueError("producer float required")
    result = _decimal(value)
    if bounded and not _ZERO <= result <= _ONE:
        raise ValueError("decimal outside [0,1]")
    return result


def _strict_nullable_float_decimal(value: Any) -> Decimal | None:
    """producer 的退化 cluster 以 null 表示；非 null 仍須是 JSON float。"""
    return None if value is None else _strict_float_decimal(value)


def _canonical_decimal_input(value: Any, *, bounded: bool = False) -> Decimal:
    """portfolio 投影是 canonical decimal string；其他 JSON number 一律不收。"""
    if not isinstance(value, str):
        raise ValueError("canonical decimal string required")
    result = _decimal(value)
    if value != _canonical_decimal_string(result):
        raise ValueError("noncanonical decimal string")
    if bounded and not _ZERO <= result <= _ONE:
        raise ValueError("decimal outside [0,1]")
    return result


def _canonical_decimal_string(value: Decimal) -> str:
    if value == _ZERO:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered


def _positive_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError("positive integer required")
    return value


def _nonnegative_int(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("nonnegative integer required")
    return value


def _strict_bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("boolean required")
    return value


def _is_hash(value: Any) -> bool:
    return isinstance(value, str) and bool(_HEX64.fullmatch(value))

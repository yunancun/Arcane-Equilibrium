"""建立冷端 candidate_evaluation_context_v1；全程純函數且 fail-closed。"""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from decimal import Decimal, InvalidOperation
from typing import Any


SCHEMA_VERSION = "candidate_evaluation_context_v1"
EVENT_SCHEMA_VERSION = "candidate_event_context_v1"
EVENT_BOUNDARY = ("immutable learning evidence only; no training, serving, promotion, order, "
                  "lease, gate, config, broker, or runtime authority")
REGIME_BUCKETS = tuple(
    f"{trend}|{volatility}|{liquidity}"
    for trend in ("bear", "neutral", "bull")
    for volatility in ("low_vol", "mid_vol", "high_vol")
    for liquidity in ("liquid", "thin")
)

_GAP_KINDS = {"NONE", "LOCAL_PASSIVE", "LOCAL_ENGINEERING", "EXTERNAL_OPERATOR"}
_HIDDEN_OOS_STATES = {"sealed", "opened", "consumed", "invalidated"}
_RISK_STATES = {
    "NORMAL",
    "CAUTIOUS",
    "REDUCED",
    "DEFENSIVE",
    "MANUAL_REVIEW",
    "CIRCUIT_BREAKER",
}
_EVENT_FIELDS = set("""
schema_version captured_at_ms strategy_name strategy_version build_git_sha
strategy_params_json strategy_params_canonical_json conf_scale strategy_config_hash
symbol side horizon_policy evidence_engine_mode pipeline_kind endpoint_environment venue
product context_id signal_id scan_id scanner_inputs market_inputs risk_context
portfolio_snapshot portfolio_snapshot_ref portfolio_snapshot_hash capture_status
capture_blockers event_hash boundary
""".split())
_MARKET_INPUT_FIELDS = set("""
observed_at_ms last_price best_bid best_ask tick_size index_price funding_rate open_interest
atr_value
""".split())
_SCANNER_INPUT_FIELDS = set("""
authority_mode legacy_would_block legacy_block_reason scan_id best_strategy intent_strategy
market_regime trend_phase trend_score range_score shock_score close_alignment range_position
crowding_score reversal_risk_score directional_efficiency dir_pct signed_dir_pct range_pct
fr_bps f_ma f_grid f_bbrv f_bkout f_funding_arb edge_bps edge_n edge_status route_mode
market_status route_reason opportunity final_score raw_score
""".split())
_PORTFOLIO_SNAPSHOT_FIELDS = set("""
schema_version captured_at_ms balance accepted_demo_equity_usdt peak_balance drawdown_pct
position_count gross_mark_notional_usdt net_mark_notional_usdt total_realized_pnl total_fees
total_funding_pnl trade_count
""".split())
_IDENTITY_FIELDS = tuple("""
strategy_name strategy_version strategy_config_hash symbol side horizon_minutes venue product
evidence_engine_mode
""".split())

class CandidateEvaluationContextError(ValueError):
    """輸入無法形成可重建、無洩漏的冷端評估 context。"""

def canonical_sha256(value: Any) -> str:
    """以 Rust serde_json 位元相同的 sorted compact UTF-8 JSON 計算雜湊。"""
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()

def _rust_serde_float_str(value: float) -> str:
    """把 finite Python float 轉成 Rust serde_json/ryu 的 shortest 表示。"""
    if not math.isfinite(value):
        raise CandidateEvaluationContextError("CANONICAL_JSON_NONFINITE_FLOAT")
    if value == 0.0:
        return "-0.0" if math.copysign(1.0, value) < 0 else "0.0"
    negative = value < 0
    rendered = repr(-value if negative else value)
    if "e" in rendered or "E" in rendered:
        mantissa, exponent = rendered.lower().split("e", 1)
        exponent_10 = int(exponent)
    else:
        mantissa = rendered
        exponent_10 = 0
    integer, _, fraction = mantissa.partition(".")
    digits = (integer + fraction).lstrip("0") or "0"
    nonzero_integer = integer.lstrip("0")
    if nonzero_integer:
        scientific_exponent = len(nonzero_integer) - 1 + exponent_10
    else:
        leading_fraction_zeros = len(fraction) - len(fraction.lstrip("0"))
        scientific_exponent = -(leading_fraction_zeros + 1) + exponent_10
    significant = digits.rstrip("0") or "0"
    significant_count = len(significant)
    if -5 <= scientific_exponent < 16:
        if scientific_exponent >= 0:
            if significant_count <= scientific_exponent + 1:
                output = significant + "0" * (
                    scientific_exponent + 1 - significant_count
                ) + ".0"
            else:
                output = significant[: scientific_exponent + 1] + "." + (
                    significant[scientific_exponent + 1 :]
                )
        else:
            output = "0." + "0" * (-scientific_exponent - 1) + significant
    else:
        mantissa_output = significant if significant_count == 1 else (
            significant[0] + "." + significant[1:]
        )
        sign = "+" if scientific_exponent >= 0 else "-"
        output = mantissa_output + "e" + sign + str(abs(scientific_exponent))
    return ("-" if negative else "") + output

def _canonical(value: Any, output: list[str]) -> None:
    if value is None:
        output.append("null")
    elif value is True:
        output.append("true")
    elif value is False:
        output.append("false")
    elif isinstance(value, int):
        output.append(str(value))
    elif isinstance(value, float):
        output.append(_rust_serde_float_str(value))
    elif isinstance(value, str):
        output.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, (list, tuple)):
        output.append("[")
        for index, item in enumerate(value):
            if index:
                output.append(",")
            _canonical(item, output)
        output.append("]")
    elif isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise CandidateEvaluationContextError("CANONICAL_JSON_OBJECT_KEY_INVALID")
        output.append("{")
        for index, key in enumerate(sorted(value)):
            if index:
                output.append(",")
            output.append(json.dumps(key, ensure_ascii=False))
            output.append(":")
            _canonical(value[key], output)
        output.append("}")
    else:
        raise CandidateEvaluationContextError("CANONICAL_JSON_TYPE_INVALID")

def _canonical_bytes(value: Any) -> bytes:
    output: list[str] = []
    _canonical(value, output)
    return "".join(output).encode("utf-8")

def build_candidate_evaluation_context(
    *,
    candidate_event_context: Mapping[str, Any],
    as_of_utc_date: str,
    evidence_regime_label: str,
    regime_entry_counts: Mapping[str, Any],
    target_regime_context: Mapping[str, Any],
    context_hashes: Mapping[str, Any],
    resource: Mapping[str, Any],
    portfolio: Mapping[str, Any],
    proof: Mapping[str, Any],
    hidden_oos_state: Mapping[str, Any],
) -> dict[str, Any]:
    """從已封存 event context 與顯式冷端來源建立 immutable evaluation context。"""
    as_of = _utc_date(as_of_utc_date, "AS_OF_UTC_DATE_INVALID")
    identity, event_hash = _event_parts(candidate_event_context)
    evidence_regime, counts = _regime_parts(evidence_regime_label, regime_entry_counts)
    target, target_hash = _target_regime(target_regime_context, as_of=as_of)
    hashes = _context_hashes(context_hashes)
    normalized_resource = _resource(resource, as_of=as_of)
    normalized_portfolio = _portfolio(portfolio, require_canonical=False)
    normalized_proof = _proof(proof)
    normalized_hidden = _hidden_oos(hidden_oos_state)
    body = {
        "schema_version": SCHEMA_VERSION,
        "as_of_utc_date": as_of.isoformat(),
        "event_hash": event_hash,
        "identity": identity,
        "target_regime_context": target,
        "target_regime_hash": target_hash,
        "evidence_regime_label": evidence_regime,
        "regime_entry_counts": counts,
        "context_hashes": hashes,
        "resource": normalized_resource,
        "portfolio": normalized_portfolio,
        "proof": normalized_proof,
        "hidden_oos_state": normalized_hidden,
        "hidden_oos_consumed": normalized_hidden["state"] != "sealed",
    }
    return {**body, "candidate_evaluation_context_hash": canonical_sha256(body)}

def validate_candidate_evaluation_context(value: Mapping[str, Any]) -> dict[str, Any]:
    """驗證現成 context 的完整語意與 canonical evaluation hash。"""
    source = _mapping(value, "EVALUATION_CONTEXT_INVALID")
    if source.get("schema_version") != SCHEMA_VERSION:
        raise CandidateEvaluationContextError("EVALUATION_SCHEMA_INVALID")
    supplied_hash = source.get("candidate_evaluation_context_hash")
    if not _is_hash(supplied_hash):
        raise CandidateEvaluationContextError("EVALUATION_HASH_INVALID")
    body = {key: copy.deepcopy(item) for key, item in source.items()
            if key != "candidate_evaluation_context_hash"}
    if supplied_hash != canonical_sha256(body):
        raise CandidateEvaluationContextError("EVALUATION_HASH_MISMATCH")

    as_of = _utc_date(source.get("as_of_utc_date"), "AS_OF_UTC_DATE_INVALID")
    identity = _identity(source.get("identity"))
    if not _is_hash(source.get("event_hash")):
        raise CandidateEvaluationContextError("EVENT_CONTEXT_HASH_INVALID")
    target, target_hash = _target_regime(
        source.get("target_regime_context"), as_of=as_of
    )
    if source.get("target_regime_hash") != target_hash:
        raise CandidateEvaluationContextError("TARGET_REGIME_HASH_MISMATCH")
    evidence_regime, counts = _regime_parts(
        source.get("evidence_regime_label"),
        source.get("regime_entry_counts"),
    )
    hashes = _context_hashes(source.get("context_hashes"))
    normalized_resource = _resource(source.get("resource"), as_of=as_of)
    normalized_portfolio = _portfolio(source.get("portfolio"), require_canonical=True)
    normalized_proof = _proof(source.get("proof"))
    normalized_hidden = _hidden_oos(source.get("hidden_oos_state"))
    hidden_consumed = normalized_hidden["state"] != "sealed"
    if source.get("hidden_oos_consumed") is not hidden_consumed:
        raise CandidateEvaluationContextError("HIDDEN_OOS_CONSUMED_MISMATCH")
    expected = {
        "schema_version": SCHEMA_VERSION,
        "as_of_utc_date": as_of.isoformat(),
        "event_hash": source["event_hash"],
        "identity": identity,
        "target_regime_context": target,
        "target_regime_hash": target_hash,
        "evidence_regime_label": evidence_regime,
        "regime_entry_counts": counts,
        "context_hashes": hashes,
        "resource": normalized_resource,
        "portfolio": normalized_portfolio,
        "proof": normalized_proof,
        "hidden_oos_state": normalized_hidden,
        "hidden_oos_consumed": hidden_consumed,
        "candidate_evaluation_context_hash": supplied_hash,
    }
    if dict(source) != expected:
        raise CandidateEvaluationContextError("EVALUATION_CONTEXT_NONCANONICAL")
    return expected

def candidate_learning_context_projection(value: Mapping[str, Any]) -> dict[str, Any]:
    """投影到既有 candidate_learning_context seam，不混入 per-event hash。"""
    context = validate_candidate_evaluation_context(value)
    identity = context["identity"]
    target = context["target_regime_context"]
    return {
        "strategy_version": identity["strategy_version"],
        "strategy_config_hash": identity["strategy_config_hash"],
        "target_regime_context": {
            "label": target["label"],
            "utc_date": target["utc_date"],
            "point_in_time": "D-1",
        },
        "target_regime_hash": context["target_regime_hash"],
        "venue": identity["venue"],
        "product": identity["product"],
        "evidence_engine_mode": identity["evidence_engine_mode"],
        "evidence_regime_label": context["evidence_regime_label"],
        "context_hashes": copy.deepcopy(context["context_hashes"]),
        "resource": copy.deepcopy(context["resource"]),
        "portfolio": copy.deepcopy(context["portfolio"]),
        "proof": copy.deepcopy(context["proof"]),
        "hidden_oos_consumed": context["hidden_oos_consumed"],
    }

def _event_parts(value: Any) -> tuple[dict[str, Any], str]:
    """驗證 Rust 捕獲的 flat event；缺值時不得從目前狀態回填。"""
    source = _mapping(value, "EVENT_CONTEXT_MISSING_OR_INVALID")
    if set(source) != _EVENT_FIELDS:
        raise CandidateEvaluationContextError("EVENT_CONTEXT_FIELDS_INVALID")
    if source.get("schema_version") != EVENT_SCHEMA_VERSION:
        raise CandidateEvaluationContextError("EVENT_CONTEXT_SCHEMA_INVALID")
    supplied_hash = source.get("event_hash")
    if not _is_hash(supplied_hash):
        raise CandidateEvaluationContextError("EVENT_CONTEXT_HASH_INVALID")
    body = {
        key: copy.deepcopy(item)
        for key, item in source.items()
        if key != "event_hash"
    }
    if supplied_hash != canonical_sha256(body):
        raise CandidateEvaluationContextError("EVENT_CONTEXT_HASH_MISMATCH")
    if source.get("capture_status") != "CAPTURE_COMPLETE":
        raise CandidateEvaluationContextError("EVENT_CONTEXT_CAPTURE_INCOMPLETE")
    if source.get("capture_blockers") != []:
        raise CandidateEvaluationContextError("EVENT_CONTEXT_CAPTURE_BLOCKED")
    if _nonnegative_int(source.get("captured_at_ms"), "CAPTURED_AT_INVALID") == 0:
        raise CandidateEvaluationContextError("CAPTURED_AT_INVALID")

    strategy_name = _text(source.get("strategy_name"), "STRATEGY_NAME_INVALID")
    strategy_version = _git_sha(source.get("strategy_version"), "STRATEGY_VERSION_INVALID")
    build_git_sha = _git_sha(source.get("build_git_sha"), "BUILD_GIT_SHA_INVALID")
    if strategy_version != build_git_sha:
        raise CandidateEvaluationContextError("STRATEGY_VERSION_LINEAGE_MISMATCH")
    params_raw = _text(source.get("strategy_params_json"), "STRATEGY_PARAMS_INVALID")
    try:
        params = json.loads(params_raw)
    except (TypeError, ValueError) as exc:
        raise CandidateEvaluationContextError("STRATEGY_PARAMS_INVALID") from exc
    if not isinstance(params, dict):
        raise CandidateEvaluationContextError("STRATEGY_PARAMS_INVALID")
    canonical_params = _canonical_bytes(params).decode("utf-8")
    if source.get("strategy_params_canonical_json") != canonical_params:
        raise CandidateEvaluationContextError("STRATEGY_PARAMS_CANONICAL_MISMATCH")
    conf_scale = _finite_float(source.get("conf_scale"), "CONF_SCALE_INVALID")
    if not 0 <= conf_scale <= 2:
        raise CandidateEvaluationContextError("CONF_SCALE_INVALID")
    strategy_config_hash = source.get("strategy_config_hash")
    if not _is_hash(strategy_config_hash):
        raise CandidateEvaluationContextError("STRATEGY_CONFIG_HASH_INVALID")
    if strategy_config_hash != canonical_sha256(
        {"strategy_params": params, "conf_scale": conf_scale}
    ):
        raise CandidateEvaluationContextError("STRATEGY_CONFIG_HASH_MISMATCH")

    symbol = _text(source.get("symbol"), "SYMBOL_INVALID")
    if symbol != symbol.upper():
        raise CandidateEvaluationContextError("SYMBOL_INVALID")
    side = _text(source.get("side"), "SIDE_INVALID")
    if side not in {"Buy", "Sell"}:
        raise CandidateEvaluationContextError("SIDE_INVALID")
    horizon = _horizon_policy(source.get("horizon_policy"))
    evidence_mode = _text(
        source.get("evidence_engine_mode"), "EVIDENCE_ENGINE_MODE_INVALID"
    )
    pipeline_kind = _text(source.get("pipeline_kind"), "PIPELINE_KIND_INVALID")
    endpoint = _text(
        source.get("endpoint_environment"), "ENDPOINT_ENVIRONMENT_INVALID"
    )
    if (evidence_mode, pipeline_kind, endpoint) not in {
        ("demo", "demo", "demo"),
        ("live_demo", "live", "live_demo"),
        ("live_demo", "live", "demo"),
    }:
        raise CandidateEvaluationContextError("EVENT_ENVIRONMENT_TRIPLE_INVALID")
    venue = _text(source.get("venue"), "VENUE_INVALID")
    product = _text(source.get("product"), "PRODUCT_INVALID")
    if (venue, product) != ("bybit", "linear_perpetual"):
        raise CandidateEvaluationContextError("EVENT_MARKET_IDENTITY_INVALID")

    for field in ("context_id", "signal_id", "scan_id"):
        _text(source.get(field), f"{field.upper()}_INVALID")
    if source.get("boundary") != EVENT_BOUNDARY:
        raise CandidateEvaluationContextError("EVENT_BOUNDARY_INVALID")
    _scanner_inputs(
        source.get("scanner_inputs"),
        scan_id=source["scan_id"],
        strategy_name=strategy_name,
    )
    _market_inputs(source.get("market_inputs"), captured_at_ms=source["captured_at_ms"])
    _risk_context(source.get("risk_context"))
    _portfolio_snapshot(
        source.get("portfolio_snapshot"),
        supplied_hash=source.get("portfolio_snapshot_hash"),
        captured_at_ms=source["captured_at_ms"],
    )
    expected_ref = (
        f"paper_state:{evidence_mode}:{source['context_id']}:{source['captured_at_ms']}"
    )
    if source.get("portfolio_snapshot_ref") != expected_ref:
        raise CandidateEvaluationContextError("PORTFOLIO_SNAPSHOT_REF_INVALID")

    identity = _identity({
        "strategy_name": strategy_name,
        "strategy_version": strategy_version,
        "strategy_config_hash": strategy_config_hash,
        "symbol": symbol,
        "side": side,
        "horizon_minutes": horizon["outcome_horizon_minutes"],
        "venue": venue,
        "product": product,
        "evidence_engine_mode": evidence_mode,
    })
    return identity, supplied_hash

def validate_candidate_event_context(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """驗證 Rust 原始 event context，並回傳語義不變的 detached copy。

    為什麼：runtime propagation 只能攜帶已通過完整 hash/schema/semantic gate 的
    prospective lineage；此接口不得補值、投影或從目前狀態重建欄位。
    """
    source = _mapping(value, "EVENT_CONTEXT_MISSING_OR_INVALID")
    _event_parts(source)
    return copy.deepcopy(source)

def _identity(value: Any) -> dict[str, Any]:
    source = _mapping(value, "IDENTITY_INVALID")
    result: dict[str, Any] = {}
    for key in _IDENTITY_FIELDS:
        item = source.get(key)
        if key == "horizon_minutes":
            if isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 1440:
                raise CandidateEvaluationContextError("HORIZON_INVALID")
            result[key] = item
        elif key == "strategy_config_hash":
            if not _is_hash(item):
                raise CandidateEvaluationContextError("STRATEGY_CONFIG_HASH_INVALID")
            result[key] = item
        elif key == "strategy_version":
            result[key] = _git_sha(item, "STRATEGY_VERSION_INVALID")
        else:
            result[key] = _text(item, f"{key.upper()}_INVALID")
    if result["side"] not in {"Buy", "Sell"}:
        raise CandidateEvaluationContextError("SIDE_INVALID")
    if result["symbol"] != result["symbol"].upper():
        raise CandidateEvaluationContextError("SYMBOL_INVALID")
    if (result["venue"], result["product"]) != ("bybit", "linear_perpetual"):
        raise CandidateEvaluationContextError("EVENT_MARKET_IDENTITY_INVALID")
    if result["evidence_engine_mode"] not in {"demo", "live_demo"}:
        raise CandidateEvaluationContextError("EVIDENCE_ENGINE_MODE_INVALID")
    if set(source) != set(_IDENTITY_FIELDS):
        raise CandidateEvaluationContextError("IDENTITY_FIELDS_INVALID")
    return result

def _regime_parts(label: Any, value: Any) -> tuple[str, dict[str, int]]:
    if label not in {*REGIME_BUCKETS, "unknown"}:
        raise CandidateEvaluationContextError("EVIDENCE_REGIME_INVALID")
    source = _mapping(value, "REGIME_ENTRY_COUNTS_INVALID")
    ordered_keys = (*REGIME_BUCKETS, "unknown")
    if set(source) != set(ordered_keys):
        raise CandidateEvaluationContextError("REGIME_ENTRY_COUNTS_INVALID")
    counts = {
        key: _nonnegative_int(source.get(key), "REGIME_ENTRY_COUNT_INVALID")
        for key in ordered_keys
    }
    if sum(counts.values()) == 0 or counts[label] == 0:
        raise CandidateEvaluationContextError("EVIDENCE_REGIME_HAS_NO_ENTRIES")
    return label, counts

def _horizon_policy(value: Any) -> dict[str, Any]:
    source = _mapping(value, "HORIZON_POLICY_INVALID")
    if set(source) != {
        "schema_version", "source", "outcome_horizon_minutes", "default_applied"
    }:
        raise CandidateEvaluationContextError("HORIZON_POLICY_FIELDS_INVALID")
    if source.get("schema_version") != "candidate_horizon_policy_v1":
        raise CandidateEvaluationContextError("HORIZON_POLICY_SCHEMA_INVALID")
    minutes = _nonnegative_int(
        source.get("outcome_horizon_minutes"), "HORIZON_INVALID"
    )
    if not 1 <= minutes <= 1_440 or not isinstance(source.get("default_applied"), bool):
        raise CandidateEvaluationContextError("HORIZON_INVALID")
    if source["default_applied"]:
        if source.get("source") != "default_60_minutes" or minutes != 60:
            raise CandidateEvaluationContextError("HORIZON_DEFAULT_INVALID")
    elif source.get("source") != "OPENCLAW_COST_GATE_LEARNING_OUTCOME_HORIZON_MINUTES":
        raise CandidateEvaluationContextError("HORIZON_SOURCE_INVALID")
    return {
        "schema_version": "candidate_horizon_policy_v1",
        "source": source["source"],
        "outcome_horizon_minutes": minutes,
        "default_applied": source["default_applied"],
    }

def _scanner_inputs(value: Any, *, scan_id: str, strategy_name: str) -> None:
    source = _mapping(value, "SCANNER_INPUTS_INVALID")
    if (
        set(source) != _SCANNER_INPUT_FIELDS
        or source.get("scan_id") != scan_id
        or source.get("intent_strategy") != strategy_name
    ):
        raise CandidateEvaluationContextError("SCANNER_INPUTS_INVALID")
    for field in (
        "authority_mode", "scan_id", "best_strategy", "intent_strategy",
        "market_regime", "trend_phase", "edge_status", "route_mode",
        "market_status", "route_reason",
    ):
        _text(source.get(field), "SCANNER_INPUTS_INVALID")
    if not isinstance(source.get("legacy_would_block"), bool):
        raise CandidateEvaluationContextError("SCANNER_INPUTS_INVALID")
    legacy_reason = source.get("legacy_block_reason")
    if legacy_reason is not None:
        _text(legacy_reason, "SCANNER_INPUTS_INVALID")
    _nonnegative_int(source.get("edge_n"), "SCANNER_INPUTS_INVALID")
    float_fields = _SCANNER_INPUT_FIELDS - {
        "authority_mode", "legacy_would_block", "legacy_block_reason", "scan_id",
        "best_strategy", "intent_strategy", "market_regime", "trend_phase",
        "edge_bps", "edge_n", "edge_status", "route_mode", "market_status",
        "route_reason", "opportunity",
    }
    for field in float_fields:
        _finite_float(source.get(field), "SCANNER_INPUTS_INVALID")
    if source.get("edge_bps") is not None:
        _finite_float(source.get("edge_bps"), "SCANNER_INPUTS_INVALID")
    _canonical_bytes(source.get("opportunity"))

def _market_inputs(value: Any, *, captured_at_ms: int) -> None:
    source = _mapping(value, "MARKET_INPUTS_INVALID")
    if set(source) != _MARKET_INPUT_FIELDS:
        raise CandidateEvaluationContextError("MARKET_INPUTS_INVALID")
    if source.get("observed_at_ms") != captured_at_ms:
        raise CandidateEvaluationContextError("MARKET_INPUTS_INVALID")
    required_positive = ("last_price", "best_bid", "best_ask", "tick_size")
    positive_optional = ("index_price", "open_interest", "atr_value")
    for field in required_positive:
        if _finite_float(source.get(field), "MARKET_INPUTS_INVALID") <= 0:
            raise CandidateEvaluationContextError("MARKET_INPUTS_INVALID")
    if source["best_bid"] >= source["best_ask"]:
        raise CandidateEvaluationContextError("MARKET_BBO_CROSSED")
    for field in positive_optional:
        if source.get(field) is not None and (
            _finite_float(source[field], "MARKET_INPUTS_INVALID") <= 0
        ):
            raise CandidateEvaluationContextError("MARKET_INPUTS_INVALID")
    if source.get("funding_rate") is not None:
        _finite_float(source["funding_rate"], "MARKET_INPUTS_INVALID")

def _risk_context(value: Any) -> None:
    source = _mapping(value, "RISK_CONTEXT_INVALID")
    if set(source) != {"risk_state", "governance_profile", "risk_config_hash"}:
        raise CandidateEvaluationContextError("RISK_CONTEXT_INVALID")
    if source.get("risk_state") not in _RISK_STATES:
        raise CandidateEvaluationContextError("RISK_CONTEXT_INVALID")
    if source.get("governance_profile") != "Validation":
        raise CandidateEvaluationContextError("RISK_CONTEXT_INVALID")
    if not _is_hash(source.get("risk_config_hash")):
        raise CandidateEvaluationContextError("RISK_CONTEXT_INVALID")

def _portfolio_snapshot(
    value: Any,
    *,
    supplied_hash: Any,
    captured_at_ms: int,
) -> None:
    source = _mapping(value, "PORTFOLIO_SNAPSHOT_INVALID")
    if set(source) != _PORTFOLIO_SNAPSHOT_FIELDS:
        raise CandidateEvaluationContextError("PORTFOLIO_SNAPSHOT_INVALID")
    if source.get("schema_version") != "candidate_portfolio_snapshot_v1":
        raise CandidateEvaluationContextError("PORTFOLIO_SNAPSHOT_INVALID")
    for field in ("captured_at_ms", "position_count", "trade_count"):
        _nonnegative_int(source.get(field), "PORTFOLIO_SNAPSHOT_INVALID")
    for field in _PORTFOLIO_SNAPSHOT_FIELDS - {
        "schema_version", "captured_at_ms", "position_count", "trade_count"
    }:
        if source.get(field) is not None:
            _finite_float(source.get(field), "PORTFOLIO_SNAPSHOT_INVALID")
    if (
        source["captured_at_ms"] != captured_at_ms
        or source["balance"] <= 0
        or source.get("accepted_demo_equity_usdt") is None
        or source["accepted_demo_equity_usdt"] <= 0
        or source["peak_balance"] < source["balance"]
        or not 0 <= source["drawdown_pct"] <= 100
        or source["gross_mark_notional_usdt"] < 0
        or abs(source["net_mark_notional_usdt"])
        > source["gross_mark_notional_usdt"]
    ):
        raise CandidateEvaluationContextError("PORTFOLIO_SNAPSHOT_INVALID")
    if not _is_hash(supplied_hash) or supplied_hash != canonical_sha256(source):
        raise CandidateEvaluationContextError("PORTFOLIO_SNAPSHOT_HASH_INVALID")

def _target_regime(value: Any, *, as_of: dt.date) -> tuple[dict[str, Any], str]:
    source = _mapping(value, "TARGET_REGIME_INVALID")
    required = {
        "label", "utc_date", "point_in_time", "source_complete",
        "source_hash", "classifier_hash",
    }
    if set(source) != required:
        raise CandidateEvaluationContextError("TARGET_REGIME_FIELDS_INVALID")
    label = source.get("label")
    if label not in REGIME_BUCKETS:
        raise CandidateEvaluationContextError("TARGET_REGIME_LABEL_INVALID")
    regime_date = _utc_date(source.get("utc_date"), "TARGET_REGIME_DATE_INVALID")
    if regime_date != as_of - dt.timedelta(days=1) or source.get("point_in_time") != "D-1":
        raise CandidateEvaluationContextError("TARGET_REGIME_NOT_D_MINUS_1")
    if source.get("source_complete") is not True:
        raise CandidateEvaluationContextError("TARGET_REGIME_SOURCE_INCOMPLETE")
    if not _is_hash(source.get("source_hash")) or not _is_hash(source.get("classifier_hash")):
        raise CandidateEvaluationContextError("TARGET_REGIME_LINEAGE_INVALID")
    normalized = {
        "label": label,
        "utc_date": regime_date.isoformat(),
        "point_in_time": "D-1",
        "source_complete": True,
        "source_hash": source["source_hash"],
        "classifier_hash": source["classifier_hash"],
    }
    return normalized, canonical_sha256(normalized)

def _context_hashes(value: Any) -> dict[str, str]:
    source = _mapping(value, "CONTEXT_HASHES_INVALID")
    if set(source) != {"data", "evidence", "cost", "portfolio"}:
        raise CandidateEvaluationContextError("CONTEXT_HASHES_INVALID")
    if not all(_is_hash(source.get(key)) for key in source):
        raise CandidateEvaluationContextError("CONTEXT_HASHES_INVALID")
    return {key: source[key] for key in ("data", "evidence", "cost", "portfolio")}

def _resource(value: Any, *, as_of: dt.date) -> dict[str, Any]:
    source = _mapping(value, "RESOURCE_INVALID")
    required = {
        "daily_buckets", "estimated_rows_scanned", "predicted_canonical_bytes",
        "zero_resource_attested", "resource_estimator_hash",
    }
    if set(source) != required:
        raise CandidateEvaluationContextError("RESOURCE_FIELDS_INVALID")
    buckets = source.get("daily_buckets")
    if not isinstance(buckets, Sequence) or isinstance(buckets, (str, bytes)):
        raise CandidateEvaluationContextError("RESOURCE_DAILY_BUCKETS_INVALID")
    normalized = []
    for bucket in buckets:
        item = _mapping(bucket, "RESOURCE_DAILY_BUCKET_INVALID")
        if set(item) != {"utc_date", "scan_complete", "distinct_entries"}:
            raise CandidateEvaluationContextError("RESOURCE_DAILY_BUCKET_INVALID")
        day = _utc_date(item.get("utc_date"), "RESOURCE_DAILY_BUCKET_INVALID")
        count = _nonnegative_int(item.get("distinct_entries"), "RESOURCE_ENTRY_COUNT_INVALID")
        if item.get("scan_complete") is not True:
            raise CandidateEvaluationContextError("RESOURCE_SCAN_INCOMPLETE")
        normalized.append({
            "utc_date": day.isoformat(),
            "scan_complete": True,
            "distinct_entries": count,
        })
    normalized.sort(key=lambda item: item["utc_date"])
    expected = [(as_of - dt.timedelta(days=offset)).isoformat()
                for offset in range(7, 0, -1)]
    if len(normalized) != 7 or [item["utc_date"] for item in normalized] != expected:
        raise CandidateEvaluationContextError("RESOURCE_DAILY_BUCKETS_INCOMPLETE")
    rows = _nonnegative_int(source.get("estimated_rows_scanned"), "RESOURCE_ROWS_INVALID")
    byte_count = _nonnegative_int(source.get("predicted_canonical_bytes"), "RESOURCE_BYTES_INVALID")
    attested = source.get("zero_resource_attested")
    if not isinstance(attested, bool):
        raise CandidateEvaluationContextError("RESOURCE_ZERO_ATTESTATION_INVALID")
    if (rows == 0) != (byte_count == 0):
        raise CandidateEvaluationContextError("RESOURCE_ASYMMETRIC_ZERO")
    if rows == 0:
        if not attested or any(item["distinct_entries"] for item in normalized):
            raise CandidateEvaluationContextError("RESOURCE_ZERO_NOT_ATTESTED")
    elif attested:
        raise CandidateEvaluationContextError("RESOURCE_ZERO_ATTESTATION_CONTRADICTS_ESTIMATE")
    body = {
        "daily_buckets": normalized,
        "estimated_rows_scanned": rows,
        "predicted_canonical_bytes": byte_count,
        "zero_resource_attested": attested,
    }
    if source.get("resource_estimator_hash") != canonical_sha256(body):
        raise CandidateEvaluationContextError("RESOURCE_ESTIMATOR_HASH_INVALID")
    return {**body, "resource_estimator_hash": source["resource_estimator_hash"]}

def _portfolio(value: Any, *, require_canonical: bool) -> dict[str, str]:
    source = _mapping(value, "PORTFOLIO_INVALID")
    required = {"sector_exposure_share", "strategy_active_target_share", "beta_to_portfolio"}
    if set(source) != required:
        raise CandidateEvaluationContextError("PORTFOLIO_FIELDS_INVALID")
    normalized = {
        key: _decimal_string(source.get(key), key.upper(), require_canonical=require_canonical)
        for key in required
    }
    for key in ("sector_exposure_share", "strategy_active_target_share"):
        value_decimal = Decimal(normalized[key])
        if not Decimal(0) <= value_decimal <= Decimal(1):
            raise CandidateEvaluationContextError(f"{key.upper()}_OUT_OF_RANGE")
    return {key: normalized[key] for key in (
        "sector_exposure_share", "strategy_active_target_share", "beta_to_portfolio"
    )}

def _proof(value: Any) -> dict[str, Any]:
    source = _mapping(value, "PROOF_INVALID")
    if set(source) != {"proof_stage", "completed_proof_stages", "next_gap"}:
        raise CandidateEvaluationContextError("PROOF_FIELDS_INVALID")
    stage = _nonnegative_int(source.get("proof_stage"), "PROOF_STAGE_INVALID")
    stages = source.get("completed_proof_stages")
    if stage > 6 or not isinstance(stages, list) or stages != list(range(stage + 1)):
        raise CandidateEvaluationContextError("PROOF_PREFIX_INVALID")
    gap = _mapping(source.get("next_gap"), "PROOF_NEXT_GAP_INVALID")
    if set(gap) != {"kind", "code"} or gap.get("kind") not in _GAP_KINDS:
        raise CandidateEvaluationContextError("PROOF_NEXT_GAP_INVALID")
    code = _text(gap.get("code"), "PROOF_NEXT_GAP_INVALID")
    return {
        "proof_stage": stage,
        "completed_proof_stages": list(stages),
        "next_gap": {"kind": gap["kind"], "code": code},
    }

def _hidden_oos(value: Any) -> dict[str, Any]:
    source = _mapping(value, "HIDDEN_OOS_STATE_INVALID")
    required = {
        "schema_version", "state", "open_count", "opened_for_iteration",
        "consumed", "invalidated", "family_id", "split_hash", "state_hash",
    }
    if not required <= set(source):
        raise CandidateEvaluationContextError("HIDDEN_OOS_STATE_INVALID")
    if source.get("schema_version") != "hidden_oos_state_v1":
        raise CandidateEvaluationContextError("HIDDEN_OOS_STATE_INVALID")
    state = source.get("state")
    open_count = _nonnegative_int(
        source.get("open_count"), "HIDDEN_OOS_STATE_INVALID"
    )
    flags = {
        field: source.get(field)
        for field in ("opened_for_iteration", "consumed", "invalidated")
    }
    if state not in _HIDDEN_OOS_STATES or not all(
        isinstance(flag, bool) for flag in flags.values()
    ):
        raise CandidateEvaluationContextError("HIDDEN_OOS_STATE_INVALID")
    _text(source.get("family_id"), "HIDDEN_OOS_STATE_INVALID")
    if not _is_hash(source.get("split_hash")):
        raise CandidateEvaluationContextError("HIDDEN_OOS_STATE_INVALID")
    if state == "sealed":
        consistent = open_count == 0 and not any(flags.values())
    elif state == "opened":
        consistent = (
            open_count > 0
            and flags["opened_for_iteration"]
            and not flags["consumed"]
            and not flags["invalidated"]
        )
    elif state == "consumed":
        consistent = (
            open_count > 0
            and flags["opened_for_iteration"]
            and flags["consumed"]
            and not flags["invalidated"]
        )
    else:
        never_opened = open_count == 0 and not flags["opened_for_iteration"]
        previously_opened = open_count > 0 and flags["opened_for_iteration"]
        consistent = flags["invalidated"] and (
            (never_opened and not flags["consumed"]) or previously_opened
        )
    if not consistent:
        raise CandidateEvaluationContextError("HIDDEN_OOS_STATE_CONFLICT")
    body = {
        key: copy.deepcopy(source[key])
        for key in sorted(source)
        if key != "state_hash"
    }
    if source.get("state_hash") != canonical_sha256(body):
        raise CandidateEvaluationContextError("HIDDEN_OOS_STATE_HASH_INVALID")
    return {**body, "state_hash": source["state_hash"]}

def _decimal_string(value: Any, field: str, *, require_canonical: bool) -> str:
    if not isinstance(value, str) or not value:
        raise CandidateEvaluationContextError(f"{field}_INVALID")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise CandidateEvaluationContextError(f"{field}_INVALID") from exc
    if not parsed.is_finite():
        raise CandidateEvaluationContextError(f"{field}_INVALID")
    canonical = format(parsed, "f")
    if "." in canonical:
        canonical = canonical.rstrip("0").rstrip(".")
    if canonical in {"", "-0"}:
        canonical = "0"
    if require_canonical and value != canonical:
        raise CandidateEvaluationContextError(f"{field}_NONCANONICAL")
    return canonical

def _mapping(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidateEvaluationContextError(reason)
    return dict(value)

def _text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise CandidateEvaluationContextError(reason)
    return value

def _utc_date(value: Any, reason: str) -> dt.date:
    if not isinstance(value, str):
        raise CandidateEvaluationContextError(reason)
    try:
        parsed = dt.date.fromisoformat(value)
    except ValueError as exc:
        raise CandidateEvaluationContextError(reason) from exc
    if value != parsed.isoformat():
        raise CandidateEvaluationContextError(reason)
    return parsed

def _nonnegative_int(value: Any, reason: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CandidateEvaluationContextError(reason)
    return value

def _finite_float(value: Any, reason: str) -> float:
    if not isinstance(value, float) or not math.isfinite(value):
        raise CandidateEvaluationContextError(reason)
    return value

def _git_sha(value: Any, reason: str) -> str:
    if not (
        isinstance(value, str)
        and len(value) == 40
        and all(character in "0123456789abcdef" for character in value)
    ):
        raise CandidateEvaluationContextError(reason)
    return value

def _is_hash(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


__all__ = [
    "CandidateEvaluationContextError",
    "EVENT_SCHEMA_VERSION",
    "REGIME_BUCKETS",
    "SCHEMA_VERSION",
    "build_candidate_evaluation_context",
    "candidate_learning_context_projection",
    "canonical_sha256",
    "validate_candidate_event_context",
    "validate_candidate_evaluation_context",
]

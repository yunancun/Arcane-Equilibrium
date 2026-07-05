#!/usr/bin/env python3
"""Build a reviewed public quote capture packet without capturing quotes.

The packet is a source-only review artifact. It binds a future candidate-scoped
public BBO capture to exact GET-only request envelopes, no auth/private/order
paths, adapter handoff, and maker-policy economics. It does not call Bybit,
query or write PG, mutate runtime state, admit orders, lower gates, or grant
authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path
from typing import Any

# 共用純函數葉節點：以 alias-import 保持函數體內 _dict/_list/_str/_utc_now 引用逐字節不變。
from cost_gate_learning_lane._lane_common import (
    as_dict as _dict,
    as_list as _list,
    as_str as _str,
    utc_now as _utc_now,
)


SCHEMA_VERSION = "cost_gate_reviewed_public_quote_capture_packet_v1"
READY_STATUS = "REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY"
MAKER_POLICY_NOT_READY_STATUS = "MAKER_FIRST_POLICY_INPUT_NOT_READY"
FRESH_BBO_READINESS_NOT_READY_STATUS = "FRESH_BBO_READINESS_INPUT_NOT_READY"
CANDIDATE_MISSING_OR_MISMATCH_STATUS = "CANDIDATE_MISSING_OR_MISMATCH"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

MAKER_POLICY_SCHEMA_VERSION = "cost_gate_maker_first_micro_tier_placement_policy_v1"
MAKER_POLICY_READY_STATUS = "MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY"
FRESH_BBO_SCHEMA_VERSION = "cost_gate_fresh_bbo_readonly_readiness_path_v1"
FRESH_BBO_READY_STATUS = "FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY"
PUBLIC_QUOTE_CAPTURE_SCHEMA_VERSION = (
    "bounded_probe_bbo_freshness_public_quote_capture_v1"
)
PUBLIC_QUOTE_CAPTURE_READY_STATUS = "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER"
PUBLIC_QUOTE_MARKET_SNAPSHOT_SCHEMA_VERSION = "bounded_probe_candidate_market_snapshot_v1"
PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_STATUS = (
    "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER"
)
PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE = (
    "bybit_public_quote_capture:bbo_freshness_public_quote_capture_v1"
)

RECOMMENDED_BASE_URL = "https://api.bybit.com"
ALLOWED_BASE_URLS = ["https://api.bybit.com", "https://api-demo.bybit.com"]
TIME_PATH = "/v5/market/time"
TICKERS_PATH = "/v5/market/tickers"
INSTRUMENTS_PATH = "/v5/market/instruments-info"
USER_AGENT = "openclaw-bbo-public-quote-capture/1.0"
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,40}$")
DEFAULT_TIMEOUT_SECONDS = 2.0
CANONICAL_MAX_FRESH_BBO_AGE_MS = 1000

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

BOUNDARY = (
    "artifact-only reviewed public quote capture packet; no quote capture, "
    "network call, PG query/write, Bybit call, private/auth/order endpoint, "
    "order, config, risk, cap, auth, runtime mutation, Cost Gate lowering, "
    "freshness gate lowering, probe authority, order authority, live authority, "
    "order admission, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "network_call_performed",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_query_performed",
    "pg_write_performed",
    "placement_call_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "public_quote_capture_allowed_by_this_packet",
    "public_quote_capture_allowed_by_this_policy",
    "public_quote_capture_performed",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
            "enabled",
            "grant",
            "granted",
            "authorize",
            "authorized",
            "ready",
        }
    return False


def _authority_preserved(*payloads: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = list(payloads)
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(item)
            continue
        data = _dict(item)
        if not data:
            continue
        adjustment = data.get("main_cost_gate_adjustment")
        if adjustment not in (None, "", "NONE"):
            reasons.append("main_cost_gate_adjustment_not_none")
        for key in AUTHORITY_TRUE_KEYS:
            if _truthy(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _ready(payload: dict[str, Any], schema: str, status: str) -> bool:
    return payload.get("schema_version") == schema and payload.get("status") == status


def _candidate(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(payload.get("candidate"))
    return {key: candidate.get(key) for key in IDENTITY_FIELDS if candidate.get(key) is not None}


def _candidate_key(candidate: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(candidate.get(key) for key in IDENTITY_FIELDS)


def _candidate_match(candidates: list[dict[str, Any]]) -> bool:
    non_empty = [candidate for candidate in candidates if candidate]
    if len(non_empty) != len(candidates):
        return False
    first = _candidate_key(non_empty[0])
    return all(_candidate_key(candidate) == first for candidate in non_empty[1:])


def _normalized_horizon(value: Any) -> int | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not parsed.is_integer():
        return None
    return int(parsed)


def _candidate_identity_reasons(candidate: dict[str, Any]) -> list[str]:
    side_cell_key = _str(candidate.get("side_cell_key"))
    strategy = _str(candidate.get("strategy_name"))
    raw_symbol = _str(candidate.get("symbol"))
    symbol = raw_symbol.upper()
    side = _str(candidate.get("side"))
    horizon = _normalized_horizon(candidate.get("outcome_horizon_minutes"))
    reasons: list[str] = []
    if not side_cell_key or not strategy or not raw_symbol or not side or horizon is None:
        reasons.append("candidate_identity_incomplete")
    if raw_symbol and raw_symbol != symbol:
        reasons.append("candidate_symbol_not_uppercase")
    if symbol and SYMBOL_RE.fullmatch(symbol) is None:
        reasons.append("candidate_symbol_not_safe")
    if side and side not in {"Buy", "Sell"}:
        reasons.append("candidate_side_not_buy_sell")
    if horizon is not None and horizon <= 0:
        reasons.append("candidate_horizon_not_positive")
    if side_cell_key and strategy and symbol and side:
        if side_cell_key != f"{strategy}|{symbol}|{side}":
            reasons.append("candidate_side_cell_key_mismatch")
    return sorted(set(reasons))


def _request_spec(label: str, path: str, query: dict[str, str]) -> dict[str, Any]:
    return {
        "label": label,
        "method": "GET",
        "base_url_policy": {
            "recommended_base_url": RECOMMENDED_BASE_URL,
            "allowed_base_urls": ALLOWED_BASE_URLS,
        },
        "path": path,
        "query": query,
        "headers_allowlist": ["User-Agent"],
        "required_user_agent": USER_AGENT,
        "auth_or_cookie_headers_allowed": False,
        "private_or_order_paths_allowed": False,
        "redirects_allowed": False,
        "timeout_seconds": DEFAULT_TIMEOUT_SECONDS,
        "capture_permitted_by_this_packet": False,
    }


def _review_packet(
    *,
    candidate: dict[str, Any],
    maker_policy: dict[str, Any],
    fresh_bbo_readiness: dict[str, Any],
) -> dict[str, Any]:
    symbol = _str(candidate.get("symbol")).upper()
    maker_contract = _dict(maker_policy.get("contract"))
    bbo_contract = _dict(fresh_bbo_readiness.get("contract"))
    bbo_readiness = _dict(bbo_contract.get("public_quote_capture_readiness"))
    bbo_gates = _dict(bbo_contract.get("freshness_and_market_data_gates"))
    handoff = _dict(bbo_contract.get("handoff_contract"))
    tier_policy = _dict(maker_contract.get("tier_priority_policy"))
    tier_priorities = _list(tier_policy.get("tier_priorities"))
    primary_tier = _dict(tier_priorities[0]) if tier_priorities else {}
    spread_cost = _dict(maker_contract.get("spread_cost_skip_policy"))
    placement_rules = _dict(maker_contract.get("maker_first_placement_rules"))
    required_requests = [
        _request_spec("server_time", TIME_PATH, {}),
        _request_spec(
            "ticker",
            TICKERS_PATH,
            {"category": "linear", "symbol": symbol},
        ),
        _request_spec(
            "instrument",
            INSTRUMENTS_PATH,
            {"category": "linear", "symbol": symbol},
        ),
    ]
    return {
        "candidate_identity": {
            "required_exact_fields": {key: candidate.get(key) for key in IDENTITY_FIELDS},
            "identity_rule": "future quote, snapshot, construction, order, fill, and outcome artifacts must exact-match this side-cell",
        },
        "future_capture_source": {
            "source_helper": (
                "helper_scripts/research/cost_gate_learning_lane/"
                "bbo_freshness_public_quote_capture.py"
            ),
            "expected_output_schema_version": PUBLIC_QUOTE_CAPTURE_SCHEMA_VERSION,
            "expected_ready_status": PUBLIC_QUOTE_CAPTURE_READY_STATUS,
            "runtime_capture_allowed_by_this_packet": False,
            "network_call_performed_by_this_packet": False,
            "requires_separate_pm_e3_bb_review_before_runtime_capture": True,
            "requires_candidate_scoped_runtime_invocation_record": True,
            "requires_no_auth_cookie_or_private_endpoint_evidence": True,
        },
        "request_envelope_review": {
            "source_from_fresh_bbo_readiness": bbo_readiness.get("source_helper"),
            "method": "GET",
            "required_requests": required_requests,
            "allowed_base_urls": ALLOWED_BASE_URLS,
            "recommended_base_url": RECOMMENDED_BASE_URL,
            "headers_allowlist": ["User-Agent"],
            "auth_or_cookie_headers_allowed": False,
            "private_or_order_paths_allowed": False,
            "redirects_allowed": False,
            "timeout_seconds_default": DEFAULT_TIMEOUT_SECONDS,
            "exact_query_required": True,
            "additional_requests_allowed": False,
        },
        "future_capture_artifact_requirements": {
            "request_count": 3,
            "canonical_request_sha_required": True,
            "raw_response_sha_required": True,
            "normalized_response_sha_required": True,
            "request_start_end_timestamps_required": True,
            "duration_ms_required": True,
            "artifact_self_hash_required": True,
            "ret_code_must_be_zero": True,
            "transport_diagnostics_sanitized_if_failure": True,
            "stale_or_source_failure_is_no_order": True,
            "ready_status_alone_is_not_order_admission": True,
        },
        "freshness_and_market_data_gates": {
            "max_fresh_bbo_age_ms": bbo_gates.get(
                "max_fresh_bbo_age_ms",
                CANONICAL_MAX_FRESH_BBO_AGE_MS,
            ),
            "ticker_must_have_exactly_one_row": bbo_gates.get(
                "ticker_must_have_exactly_one_row"
            )
            is True,
            "instrument_must_have_exactly_one_row": bbo_gates.get(
                "instrument_must_have_exactly_one_row"
            )
            is True,
            "bid_ask_required": bbo_gates.get("bid_ask_required") is True,
            "bid_must_be_less_than_ask": bbo_gates.get("bid_must_be_less_than_ask")
            is True,
            "bid_ask_size_positive": bbo_gates.get("bid_ask_size_positive") is True,
            "spread_bps_must_be_recorded": bbo_gates.get("spread_bps_must_be_recorded")
            is True,
            "instrument_status_required": bbo_gates.get("instrument_status_required"),
            "instrument_category_required": bbo_gates.get("instrument_category_required"),
            "instrument_filters_required": bbo_gates.get("instrument_filters_required"),
            "raw_public_quote_is_not_construction_input": bbo_gates.get(
                "raw_public_quote_is_not_construction_input"
            )
            is True,
        },
        "maker_policy_context": {
            "mode": _dict(maker_policy.get("summary")).get("mode"),
            "primary_tier": {
                "tier_index": primary_tier.get("tier_index"),
                "qty": primary_tier.get("qty"),
                "notional_usdt": primary_tier.get("notional_usdt"),
            },
            "placement_mode": placement_rules.get("mode"),
            "time_in_force_required": placement_rules.get("time_in_force_required"),
            "taker_fallback_allowed": placement_rules.get("taker_fallback_allowed"),
            "spread_cost_skip_formula": spread_cost.get("skip_formula"),
            "skip_if_missing_any_required_cost_or_spread_input": spread_cost.get(
                "skip_if_missing_any_required_cost_or_spread_input"
            ),
        },
        "handoff_contract": {
            "public_quote_to_snapshot_adapter": _dict(
                handoff.get("public_quote_to_snapshot_adapter")
            )
            or {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "public_quote_market_snapshot_adapter.py"
                ),
                "output_schema_version": PUBLIC_QUOTE_MARKET_SNAPSHOT_SCHEMA_VERSION,
                "output_source": PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
                "ready_status": PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_STATUS,
                "requires_candidate_exact_match": True,
                "requires_cap_match": True,
                "requires_public_quote_path_sha": True,
            },
            "snapshot_to_construction_preview": _dict(
                handoff.get("snapshot_to_construction_preview")
            ),
            "raw_quote_can_feed_order_construction_directly": False,
        },
        "pm_e3_bb_review_checklist": [
            "confirm no auth/cookie/private/order endpoint in request envelope",
            "confirm base URL is allowlisted and method is GET for all requests",
            "confirm exact candidate-scoped linear ticker/instrument queries and server-time request",
            "confirm redirects are refused and timeout remains bounded",
            "confirm output artifact records request/response hashes and timestamps",
            "confirm fresh BBO max age remains 1000ms and is not relaxed",
            "confirm adapter handoff is path+sha backed before construction preview",
            "confirm maker policy spread/cost skip guard remains in force",
            "confirm capture review does not grant order/probe/live authority",
        ],
        "failure_conditions": [
            "auth_or_cookie_header_present",
            "private_or_order_endpoint_used",
            "non_get_method_or_query_not_exact",
            "base_url_not_allowlisted",
            "redirect_followed",
            "timeout_or_transport_failure_without_sanitized_diagnostics",
            "ret_code_nonzero_or_missing_response_hash",
            "public_quote_not_candidate_matched",
            "bbo_stale_or_bid_ask_invalid",
            "instrument_not_trading_or_filters_missing",
            "raw_quote_used_as_construction_input_without_adapter",
            "cost_gate_or_freshness_gate_lowered",
            "runtime_or_plan_or_risk_mutation_attempted",
            "order_admission_claimed_without_separate_authorization_review",
        ],
        "max_safe_next_action": "pm_e3_bb_review_public_quote_capture_runtime_invocation_or_wait_real_auth_delta",
    }


def build_reviewed_public_quote_capture_packet(
    *,
    maker_first_policy: dict[str, Any] | None,
    fresh_bbo_readiness: dict[str, Any] | None,
    maker_first_policy_path: Path | None = None,
    fresh_bbo_readiness_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    maker_policy = _dict(maker_first_policy)
    bbo_readiness = _dict(fresh_bbo_readiness)
    authority_ok, authority_reasons = _authority_preserved(maker_policy, bbo_readiness)
    maker_ready = _ready(maker_policy, MAKER_POLICY_SCHEMA_VERSION, MAKER_POLICY_READY_STATUS)
    bbo_ready = _ready(bbo_readiness, FRESH_BBO_SCHEMA_VERSION, FRESH_BBO_READY_STATUS)
    candidates = [_candidate(maker_policy), _candidate(bbo_readiness)]
    candidates_match = _candidate_match(candidates)
    candidate = candidates[0] if candidates_match else {}
    candidate_identity_reasons = _candidate_identity_reasons(candidate)
    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not maker_ready:
        status = MAKER_POLICY_NOT_READY_STATUS
        reason = "maker_first_policy_input_not_ready"
    elif not bbo_ready:
        status = FRESH_BBO_READINESS_NOT_READY_STATUS
        reason = "fresh_bbo_readiness_input_not_ready"
    elif not candidates_match or candidate_identity_reasons:
        status = CANDIDATE_MISSING_OR_MISMATCH_STATUS
        reason = "candidate_missing_or_mismatch_across_inputs"
    else:
        status = READY_STATUS
        reason = "reviewed_public_quote_capture_packet_ready_no_capture"

    review_packet = (
        _review_packet(
            candidate=candidate,
            maker_policy=maker_policy,
            fresh_bbo_readiness=bbo_readiness,
        )
        if status == READY_STATUS
        else {}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_inputs": {
            "maker_first_policy_path": (
                str(maker_first_policy_path) if maker_first_policy_path else None
            ),
            "maker_first_policy_schema_version": maker_policy.get("schema_version"),
            "maker_first_policy_status": maker_policy.get("status"),
            "fresh_bbo_readiness_path": (
                str(fresh_bbo_readiness_path) if fresh_bbo_readiness_path else None
            ),
            "fresh_bbo_readiness_schema_version": bbo_readiness.get("schema_version"),
            "fresh_bbo_readiness_status": bbo_readiness.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "candidate_match": candidates_match,
            "candidate_identity_reasons": candidate_identity_reasons,
        },
        "candidate": candidate if status == READY_STATUS else {},
        "review_packet": review_packet,
        "summary": {
            "reviewed_public_quote_capture_packet_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "runtime_capture_allowed_by_this_packet": False,
            "network_call_performed": False,
            "public_quote_capture_performed": False,
            "order_admission_ready": False,
            "p0_authorization_required_before_order": True,
            "pm_e3_bb_review_required_before_capture": status == READY_STATUS,
            "request_count": (
                len(_list(_dict(review_packet.get("request_envelope_review")).get("required_requests")))
                if status == READY_STATUS
                else 0
            ),
            "max_fresh_bbo_age_ms": (
                _dict(review_packet.get("freshness_and_market_data_gates")).get(
                    "max_fresh_bbo_age_ms"
                )
                if status == READY_STATUS
                else None
            ),
            "max_safe_next_action": (
                review_packet.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_inputs"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "reviewed_public_quote_capture_packet_ready": status == READY_STATUS,
            "runtime_capture_allowed_by_this_packet": False,
            "public_quote_capture_performed": False,
            "network_call_performed": False,
            "bybit_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "cookie_headers_present": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "cap_envelope_mutation_allowed": False,
            "cap_mutation_performed": False,
            "risk_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "order_admission_ready": False,
            "order_submission_performed": False,
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    summary = _dict(packet.get("summary"))
    review = _dict(packet.get("review_packet"))
    lines = [
        "# Reviewed Public Quote Capture Packet No-Capture",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Summary",
        "",
    ]
    for key, value in summary.items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Request Envelope Review", ""])
    request_review = _dict(review.get("request_envelope_review"))
    if request_review:
        lines.append("```json")
        lines.append(json.dumps(request_review, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
    lines.extend(["", "## Capture Artifact Requirements", ""])
    requirements = _dict(review.get("future_capture_artifact_requirements"))
    if requirements:
        lines.append("```json")
        lines.append(json.dumps(requirements, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
    lines.extend(["", "## E3/BB Review Checklist", ""])
    for item in _list(review.get("pm_e3_bb_review_checklist")):
        lines.append(f"- {item}")
    lines.extend(["", "## No-Authority Answers", ""])
    for key, value in _dict(packet.get("answers")).items():
        lines.append(f"- `{key}`: `{value}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--maker-first-policy-json", type=Path, required=True)
    parser.add_argument("--fresh-bbo-readiness-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_reviewed_public_quote_capture_packet(
        maker_first_policy=_read_json(args.maker_first_policy_json),
        fresh_bbo_readiness=_read_json(args.fresh_bbo_readiness_json),
        maker_first_policy_path=args.maker_first_policy_json,
        fresh_bbo_readiness_path=args.fresh_bbo_readiness_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        args.json_output.parent.mkdir(parents=True, exist_ok=True)
        args.json_output.write_text(
            json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(markdown, encoding="utf-8")
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True))
    elif not args.output and not args.json_output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

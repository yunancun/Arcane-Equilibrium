#!/usr/bin/env python3
"""Build a source-only fresh BBO read-only readiness path contract.

The contract fixes what a future public quote capture must prove before AVAX
can enter a later construction/order-admission review. It does not query PG,
call Bybit, read fills, submit orders, lower Cost Gate, or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_fresh_bbo_readonly_readiness_path_v1"
READY_STATUS = "FRESH_BBO_READONLY_READINESS_PATH_READY_NO_AUTHORITY"
FEE_SCHEMA_NOT_READY_STATUS = "FEE_SCHEMA_INPUT_NOT_READY"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
CANDIDATE_MISSING_STATUS = "FRESH_BBO_CANDIDATE_MISSING"

FEE_SCHEMA_VERSION = "cost_gate_fee_slippage_maker_taker_schema_contract_v1"
FEE_SCHEMA_READY_STATUS = "FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY"
PUBLIC_QUOTE_SCHEMA_VERSION = "bounded_probe_bbo_freshness_public_quote_capture_v1"
PUBLIC_QUOTE_READY_STATUS = "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER"
PUBLIC_QUOTE_MARKET_SNAPSHOT_SCHEMA_VERSION = "bounded_probe_candidate_market_snapshot_v1"
PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE = (
    "bybit_public_quote_capture:bbo_freshness_public_quote_capture_v1"
)
PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_STATUS = (
    "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER"
)
CONSTRUCTION_PREVIEW_SCHEMA_VERSION = (
    "bounded_demo_probe_candidate_construction_preview_v1"
)

CANONICAL_MAX_FRESH_BBO_AGE_MS = 1000
DEFAULT_TIMEOUT_SECONDS = 2.0
RECOMMENDED_BASE_URL = "https://api.bybit.com"
ALLOWED_BASE_URLS = ["https://api.bybit.com", "https://api-demo.bybit.com"]
TIME_PATH = "/v5/market/time"
TICKERS_PATH = "/v5/market/tickers"
INSTRUMENTS_PATH = "/v5/market/instruments-info"

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

BOUNDARY = (
    "artifact-only fresh BBO read-only readiness path; no PG query/write, "
    "Bybit call, private/auth/order endpoint, order, config, risk, auth, "
    "runtime mutation, Cost Gate lowering, cap mutation, probe authority, "
    "order authority, live authority, order admission, or promotion proof"
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
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "operator_authorization_object_emitted",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return str(value or "").strip()


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
        }
    return False


def _authority_preserved(payload: dict[str, Any] | None) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    stack: list[Any] = [payload]
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


def _fee_schema_ready(payload: dict[str, Any]) -> bool:
    return (
        payload.get("schema_version") == FEE_SCHEMA_VERSION
        and payload.get("status") == FEE_SCHEMA_READY_STATUS
    )


def _candidate(payload: dict[str, Any]) -> dict[str, Any]:
    candidate = _dict(payload.get("candidate"))
    return {key: candidate.get(key) for key in IDENTITY_FIELDS if candidate.get(key) is not None}


def _exact_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {key: candidate.get(key) for key in IDENTITY_FIELDS}


def _contract(candidate: dict[str, Any], fee_schema: dict[str, Any]) -> dict[str, Any]:
    fee_contract = _dict(fee_schema.get("contract"))
    risk_context = _dict(fee_contract.get("risk_and_cap_context"))
    symbol = _str(candidate.get("symbol")).upper()
    return {
        "candidate_identity": {
            "required_exact_fields": _exact_candidate(candidate),
            "identity_rule": "future quote, snapshot, and construction artifacts must exact-match the selected AVAX side cell",
        },
        "public_quote_capture_readiness": {
            "source_helper": (
                "helper_scripts/research/cost_gate_learning_lane/"
                "bbo_freshness_public_quote_capture.py"
            ),
            "expected_schema_version": PUBLIC_QUOTE_SCHEMA_VERSION,
            "ready_status": PUBLIC_QUOTE_READY_STATUS,
            "network_call_permitted_by_this_contract": False,
            "requires_separate_e3_bb_review_for_runtime_capture": True,
            "base_url_policy": {
                "recommended_base_url": RECOMMENDED_BASE_URL,
                "allowed_base_urls": ALLOWED_BASE_URLS,
            },
            "request_envelope": {
                "method": "GET",
                "headers_allowlist": ["User-Agent"],
                "auth_or_cookie_headers_allowed": False,
                "private_or_order_paths_allowed": False,
                "redirects_allowed": False,
                "timeout_seconds_default": DEFAULT_TIMEOUT_SECONDS,
                "timeout_seconds_must_be_positive": True,
            },
            "required_requests": [
                {
                    "label": "server_time",
                    "path": TIME_PATH,
                    "query": {},
                },
                {
                    "label": "ticker",
                    "path": TICKERS_PATH,
                    "query": {"category": "linear", "symbol": symbol},
                },
                {
                    "label": "instrument",
                    "path": INSTRUMENTS_PATH,
                    "query": {"category": "linear", "symbol": symbol},
                    "required": True,
                },
            ],
        },
        "freshness_and_market_data_gates": {
            "max_fresh_bbo_age_ms": CANONICAL_MAX_FRESH_BBO_AGE_MS,
            "freshness_rule": "bybit_server_time_offset_plus_request_durations",
            "ticker_must_have_exactly_one_row": True,
            "instrument_must_have_exactly_one_row": True,
            "bid_ask_required": True,
            "bid_ask_positive": True,
            "bid_must_be_less_than_ask": True,
            "bid_ask_size_positive": True,
            "spread_bps_must_be_recorded": True,
            "instrument_status_required": "Trading",
            "instrument_category_required": "linear",
            "instrument_filters_required": ["tick_size", "qty_step", "min_notional"],
            "instrument_filters_positive": True,
            "raw_public_quote_is_not_construction_input": True,
        },
        "handoff_contract": {
            "public_quote_to_snapshot_adapter": {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "public_quote_market_snapshot_adapter.py"
                ),
                "output_schema_version": PUBLIC_QUOTE_MARKET_SNAPSHOT_SCHEMA_VERSION,
                "output_source": PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
                "ready_status": PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_STATUS,
                "requires_public_quote_path_sha": True,
                "requires_reroute_review_path_sha": True,
                "requires_candidate_exact_match": True,
                "requires_cap_match": True,
            },
            "snapshot_to_construction_preview": {
                "source_helper": (
                    "helper_scripts/research/cost_gate_learning_lane/"
                    "bounded_probe_candidate_construction_preview.py"
                ),
                "expected_schema_version": CONSTRUCTION_PREVIEW_SCHEMA_VERSION,
                "requires_market_snapshot_source": PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
                "requires_fresh_bbo": True,
                "requires_instrument_trading": True,
                "order_admission_ready_from_this_contract": False,
            },
        },
        "risk_and_cap_context": {
            "per_order_cap_usdt": risk_context.get("per_order_cap_usdt"),
            "max_probe_orders_before_review": risk_context.get("max_probe_orders_before_review"),
            "max_total_demo_notional_before_review": risk_context.get(
                "max_total_demo_notional_before_review"
            ),
            "bbo_refresh_required_before_order_admission": True,
        },
        "failure_conditions": [
            "private_or_order_endpoint_used",
            "auth_or_cookie_header_present",
            "public_quote_not_candidate_matched",
            "public_quote_bbo_stale",
            "public_quote_bid_ask_invalid",
            "public_quote_bid_ask_size_invalid",
            "instrument_not_trading",
            "instrument_filters_missing_or_nonpositive",
            "raw_public_quote_used_as_construction_snapshot_without_adapter",
            "snapshot_or_construction_candidate_mismatch",
            "cost_gate_or_freshness_gate_lowered",
            "runtime_or_plan_or_risk_mutation_attempted",
            "order_admission_claimed_without_separate_review",
        ],
        "future_review_requirements": [
            "public quote capture artifact must be reviewed before adapter use",
            "adapter output must be path+sha backed and candidate matched",
            "construction preview must be rerun after fresh BBO snapshot",
            "bounded authorization is still required before any order path",
            "fee/slippage/maker-taker schema remains required for outcome proof",
        ],
        "max_safe_next_action": "prepare_reviewed_public_quote_capture_or_source_only_maker_tier_policy_no_order",
    }


def build_fresh_bbo_readonly_readiness_path(
    *,
    fee_slippage_schema: dict[str, Any] | None,
    fee_slippage_schema_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    fee_schema = _dict(fee_slippage_schema)
    authority_ok, authority_reasons = _authority_preserved(fee_schema)
    schema_ready = _fee_schema_ready(fee_schema)
    candidate = _candidate(fee_schema)
    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_fee_schema"
    elif not schema_ready:
        status = FEE_SCHEMA_NOT_READY_STATUS
        reason = "fee_slippage_schema_input_not_ready"
    elif not candidate:
        status = CANDIDATE_MISSING_STATUS
        reason = "candidate_missing_from_fee_schema"
    else:
        status = READY_STATUS
        reason = "fresh_bbo_readonly_readiness_path_ready"

    contract = _contract(candidate, fee_schema) if status == READY_STATUS else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_fee_slippage_schema": {
            "path": str(fee_slippage_schema_path) if fee_slippage_schema_path else None,
            "schema_version": fee_schema.get("schema_version"),
            "status": fee_schema.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
        },
        "candidate": candidate if status == READY_STATUS else {},
        "contract": contract,
        "summary": {
            "fresh_bbo_readonly_readiness_path_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "public_quote_capture_permitted_by_this_packet": False,
            "network_call_performed": False,
            "order_admission_ready": False,
            "p0_authorization_required_before_order": True,
            "max_fresh_bbo_age_ms": (
                CANONICAL_MAX_FRESH_BBO_AGE_MS if status == READY_STATUS else None
            ),
            "max_safe_next_action": (
                contract.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_fee_slippage_schema"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "fresh_bbo_readonly_readiness_path_ready": status == READY_STATUS,
            "public_quote_capture_performed": False,
            "bybit_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "cookie_headers_present": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
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
    contract = _dict(packet.get("contract"))
    capture = _dict(contract.get("public_quote_capture_readiness"))
    gates = _dict(contract.get("freshness_and_market_data_gates"))
    lines = [
        "# Fresh BBO Read-Only Readiness Path",
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
    lines.extend(["", "## Public Quote Readiness", ""])
    if capture:
        lines.append("```json")
        lines.append(json.dumps(capture, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
    lines.extend(["", "## Freshness Gates", ""])
    if gates:
        lines.append("```json")
        lines.append(json.dumps(gates, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
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
    parser.add_argument("--fee-slippage-schema-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_fresh_bbo_readonly_readiness_path(
        fee_slippage_schema=_read_json(args.fee_slippage_schema_json),
        fee_slippage_schema_path=args.fee_slippage_schema_json,
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

#!/usr/bin/env python3
"""Build a source-only fee-tier and maker-ratio evidence design.

The packet defines what future AVAX bounded Demo proof must carry to make
after-fee net PnL reconstructable. It does not call Bybit, read private fee
state, query or write PG, submit orders, lower gates, mutate runtime state, or
grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_fee_tier_maker_ratio_evidence_design_v1"
READY_STATUS = "FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_READY_NO_ORDER"
AUTH_PACKET_NOT_READY_STATUS = "AUTH_PACKET_INPUT_NOT_READY"
AUTH_PACKET_UNSAFE_STATUS = "AUTH_PACKET_TYPED_CONFIRM_UNSAFE"
FEE_SCHEMA_NOT_READY_STATUS = "FEE_SCHEMA_INPUT_NOT_READY"
MAKER_POLICY_NOT_READY_STATUS = "MAKER_POLICY_INPUT_NOT_READY"
CANDIDATE_MISMATCH_STATUS = "CANDIDATE_MISSING_OR_MISMATCH"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

AUTH_STATUS_ALLOWED = {
    "FALSE_NEGATIVE_PREFLIGHT_OPERATOR_REVIEW_REQUIRED",
    "FALSE_NEGATIVE_PREFLIGHT_NOT_READY",
}
FEE_SCHEMA_VERSION = "cost_gate_fee_slippage_maker_taker_schema_contract_v1"
FEE_SCHEMA_READY_STATUS = "FEE_SLIPPAGE_MAKER_TAKER_SCHEMA_READY_NO_AUTHORITY"
MAKER_POLICY_VERSION = "cost_gate_maker_first_micro_tier_placement_policy_v1"
MAKER_POLICY_READY_STATUS = "MAKER_FIRST_MICRO_TIER_POLICY_READY_NO_AUTHORITY"

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

BOUNDARY = (
    "source-only fee-tier/maker-ratio evidence design; no Bybit call, private "
    "fee read, PG query/write, order, cancel, modify, config, risk, auth, "
    "runtime, service, env, or crontab mutation, Cost Gate lowering, freshness "
    "gate lowering, probe authority, order authority, live authority, ledger "
    "append, promotion proof, or profit proof"
)

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "canonical_plan_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "cost_gate_lowering_recommended",
    "cost_gate_proof",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "private_fee_read_performed",
    "private_fee_tier_read_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "service_restart_performed",
    "writer_enabled",
}

FALSE_SAFE_STRINGS = {
    "0",
    "false",
    "n",
    "no",
    "off",
    "disabled",
    "none",
    "null",
    "absent",
    "missing",
    "deny",
    "denied",
    "not_enabled",
    "not enabled",
    "not_granted",
    "not granted",
    "not_authorized",
    "not authorized",
    "not_present",
    "not present",
    "not_ready",
    "not ready",
}

FEE_TIER_PROVENANCE_FIELDS = [
    "fee_schedule_source",
    "fee_schedule_source_hash",
    "fee_schedule_effective_at_utc",
    "fee_tier_account_scope",
    "maker_fee_bps",
    "taker_fee_bps",
    "fee_currency_policy",
    "captured_by",
    "captured_at_utc",
    "e3_bb_review_id",
]

MAKER_RATIO_FIELDS = [
    "candidate_side_cell_key",
    "attempt_id",
    "order_link_id",
    "exchange_order_id",
    "exec_id",
    "filled_notional_usdt",
    "maker_filled_notional_usdt",
    "taker_filled_notional_usdt",
    "liquidity_role",
    "time_in_force",
    "post_only",
    "fee_bps",
    "slippage_bps",
    "proof_exclusion_reasons",
]


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
        text = value.strip().lower()
        return bool(text) and text not in FALSE_SAFE_STRINGS
    return value is not None


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
        for key in FORBIDDEN_TRUE_KEYS:
            if _truthy(data.get(key)):
                reasons.append(f"{key}_true")
        stack.extend(value for value in data.values() if isinstance(value, (dict, list)))
    return not reasons, sorted(set(reasons))


def _candidate(payload: dict[str, Any]) -> dict[str, Any]:
    raw = _dict(payload.get("candidate"))
    candidate: dict[str, Any] = {}
    for key in IDENTITY_FIELDS:
        if key not in raw:
            return {}
        value = raw.get(key)
        if value is None:
            return {}
        if isinstance(value, str) and not value.strip():
            return {}
        candidate[key] = value
    return candidate


def _candidate_match(candidates: list[dict[str, Any]]) -> bool:
    present = [candidate for candidate in candidates if candidate]
    if len(present) != len(candidates):
        return False
    first = present[0]
    return all(candidate == first for candidate in present[1:])


def _ready(payload: dict[str, Any], schema_version: str, status: str) -> bool:
    return payload.get("schema_version") == schema_version and payload.get("status") == status


def _auth_packet_ready_for_no_order_design(auth_packet: dict[str, Any]) -> bool:
    if auth_packet.get("status") not in AUTH_STATUS_ALLOWED:
        return False
    if auth_packet.get("decision") != "defer":
        return False
    return bool(_candidate(auth_packet))


def _auth_packet_typed_confirm_safe(auth_packet: dict[str, Any]) -> bool:
    if auth_packet.get("typed_confirm_expected") is not None:
        return False
    if _truthy(auth_packet.get("typed_confirm_matches")):
        return False
    if auth_packet.get("authorization_id"):
        return False
    return True


def _evidence_contract(
    *,
    candidate: dict[str, Any],
    fee_schema: dict[str, Any],
    maker_policy: dict[str, Any],
) -> dict[str, Any]:
    fee_contract = _dict(fee_schema.get("contract"))
    maker_contract = _dict(maker_policy.get("contract"))
    maker_rules = _dict(maker_contract.get("maker_first_placement_rules"))
    spread_policy = _dict(maker_contract.get("spread_cost_skip_policy"))
    return {
        "candidate_identity": {
            "required_exact_fields": candidate,
            "identity_rule": "future fee evidence must exact-match side-cell, strategy, symbol, side, and horizon",
        },
        "fee_tier_provenance": {
            "purpose": "record the effective maker/taker fee schedule used for after-cost proof",
            "required_fields": FEE_TIER_PROVENANCE_FIELDS,
            "private_fee_read_status": "not_performed_by_this_packet",
            "future_private_read_authority_required": "PM -> E3 -> BB if account-specific fee tier read is opened",
            "proof_policy": "modeled or assumed fee tier cannot count as promotion or Cost Gate proof",
        },
        "maker_ratio_measurement": {
            "required_fields": MAKER_RATIO_FIELDS,
            "denominator": "sum filled_notional_usdt for attributed candidate-matched bounded Demo fills",
            "numerator": "sum maker_filled_notional_usdt for attributed candidate-matched bounded Demo fills",
            "formula": "maker_ratio = maker_filled_notional_usdt / filled_notional_usdt",
            "minimum_lineage": [
                "attempt_id",
                "order_link_id",
                "exchange_order_id",
                "exec_id",
                "decision_lease_id",
                "candidate_side_cell_key",
            ],
            "taker_policy": (
                "taker fills are measured for execution realism but do not count as "
                "maker-path success without QC/PM review"
            ),
        },
        "after_fee_pnl_reconstruction": {
            "formula": "net_bps_after_actual_cost = gross_bps - actual_fee_bps - actual_slippage_bps",
            "actual_fee_required": _dict(fee_contract.get("fee_slippage_policy")).get(
                "actual_fee_required"
            ),
            "actual_slippage_required": _dict(fee_contract.get("fee_slippage_policy")).get(
                "actual_slippage_required"
            ),
            "expected_liquidity_role": _dict(fee_contract.get("maker_taker_policy")).get(
                "expected_liquidity_role_for_bounded_probe"
            ),
        },
        "placement_cost_context": {
            "mode": maker_rules.get("mode"),
            "time_in_force_required": maker_rules.get("time_in_force_required"),
            "spread_cost_skip_policy": spread_policy,
            "placement_call_allowed_by_this_packet": False,
        },
        "proof_exclusions": [
            "unattributed_fill",
            "cleanup_or_risk_close_fill",
            "cross_symbol_control_as_candidate_proof",
            "modeled_fee_tier_without_provenance",
            "missing_maker_taker_label",
            "missing_fee_or_slippage",
            "manual_or_replay_only_result",
            "single_window_positive_without_repeat_or_oos",
        ],
        "fastest_safe_test": (
            "source-only review now; future private fee-tier read requires E3/BB "
            "read-only envelope; future maker ratio proof requires authorized "
            "candidate-matched Demo fills"
        ),
        "max_safe_next_action": "review_private_fee_tier_read_envelope_or_wait_for_real_p0_authorization_delta",
    }


def build_fee_tier_maker_ratio_evidence_design(
    *,
    auth_packet: dict[str, Any] | None,
    fee_slippage_schema: dict[str, Any] | None,
    maker_first_policy: dict[str, Any] | None,
    auth_packet_path: Path | None = None,
    fee_slippage_schema_path: Path | None = None,
    maker_first_policy_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    auth = _dict(auth_packet)
    fee_schema = _dict(fee_slippage_schema)
    maker_policy = _dict(maker_first_policy)
    authority_ok, authority_reasons = _authority_preserved(auth, fee_schema, maker_policy)
    auth_ready = _auth_packet_ready_for_no_order_design(auth)
    auth_typed_safe = _auth_packet_typed_confirm_safe(auth)
    fee_ready = _ready(fee_schema, FEE_SCHEMA_VERSION, FEE_SCHEMA_READY_STATUS)
    maker_ready = _ready(maker_policy, MAKER_POLICY_VERSION, MAKER_POLICY_READY_STATUS)
    candidates = [_candidate(auth), _candidate(fee_schema), _candidate(maker_policy)]
    candidates_match = _candidate_match(candidates)
    candidate = candidates[0] if candidates_match else {}

    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_inputs"
    elif not auth_ready:
        status = AUTH_PACKET_NOT_READY_STATUS
        reason = "auth_packet_input_not_ready_for_source_only_design"
    elif not auth_typed_safe:
        status = AUTH_PACKET_UNSAFE_STATUS
        reason = "auth_packet_typed_confirm_not_fail_closed"
    elif not fee_ready:
        status = FEE_SCHEMA_NOT_READY_STATUS
        reason = "fee_slippage_schema_input_not_ready"
    elif not maker_ready:
        status = MAKER_POLICY_NOT_READY_STATUS
        reason = "maker_first_policy_input_not_ready"
    elif not candidates_match:
        status = CANDIDATE_MISMATCH_STATUS
        reason = "candidate_missing_or_mismatch_across_inputs"
    else:
        status = READY_STATUS
        reason = "fee_tier_maker_ratio_evidence_design_ready"

    contract = (
        _evidence_contract(
            candidate=candidate,
            fee_schema=fee_schema,
            maker_policy=maker_policy,
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
            "auth_packet_path": str(auth_packet_path) if auth_packet_path else None,
            "auth_packet_status": auth.get("status"),
            "auth_packet_decision": auth.get("decision"),
            "auth_packet_authorization_id": auth.get("authorization_id"),
            "auth_packet_typed_confirm_expected": auth.get("typed_confirm_expected"),
            "auth_packet_typed_confirm_readiness": auth.get("typed_confirm_readiness"),
            "fee_slippage_schema_path": (
                str(fee_slippage_schema_path) if fee_slippage_schema_path else None
            ),
            "fee_slippage_schema_status": fee_schema.get("status"),
            "maker_first_policy_path": (
                str(maker_first_policy_path) if maker_first_policy_path else None
            ),
            "maker_first_policy_status": maker_policy.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "candidate_match": candidates_match,
        },
        "candidate": candidate if status == READY_STATUS else {},
        "contract": contract,
        "summary": {
            "fee_tier_maker_ratio_evidence_design_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "fee_tier_private_read_performed": False,
            "maker_ratio_proof_available_now": False,
            "requires_future_candidate_matched_fills": True,
            "requires_actual_fee_provenance": True,
            "requires_maker_taker_labels": True,
            "order_admission_ready": False,
            "p0_authorization_required_before_probe": True,
            "max_safe_next_action": (
                contract.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_inputs"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "fee_tier_maker_ratio_evidence_design_ready": status == READY_STATUS,
            "private_fee_read_performed": False,
            "private_fee_tier_read_performed": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "risk_mutation_performed": False,
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
    lines = [
        "# Fee-Tier Maker-Ratio Evidence Design",
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
    lines.extend(["", "## Evidence Contract", ""])
    for key in (
        "fee_tier_provenance",
        "maker_ratio_measurement",
        "after_fee_pnl_reconstruction",
        "proof_exclusions",
        "fastest_safe_test",
        "max_safe_next_action",
    ):
        value = contract.get(key)
        if value is None:
            continue
        lines.append(f"### `{key}`")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
        lines.append("```")
        lines.append("")
    lines.extend(["## No-Authority Answers", ""])
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
    parser.add_argument("--auth-packet-json", type=Path, required=True)
    parser.add_argument("--fee-slippage-schema-json", type=Path, required=True)
    parser.add_argument("--maker-first-policy-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_fee_tier_maker_ratio_evidence_design(
        auth_packet=_read_json(args.auth_packet_json),
        fee_slippage_schema=_read_json(args.fee_slippage_schema_json),
        maker_first_policy=_read_json(args.maker_first_policy_json),
        auth_packet_path=args.auth_packet_json,
        fee_slippage_schema_path=args.fee_slippage_schema_json,
        maker_first_policy_path=args.maker_first_policy_json,
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

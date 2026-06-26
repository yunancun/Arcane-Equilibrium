#!/usr/bin/env python3
"""Build a source-only private fee-tier read envelope design.

The packet defines how a future E3/BB-reviewed read-only fee-tier capture may
be performed and recorded. This helper itself does not call Bybit, read private
fee state, query or write PG, submit orders, lower gates, mutate runtime state,
or grant authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_private_fee_tier_read_envelope_design_v1"
READY_STATUS = "PRIVATE_FEE_TIER_READ_ENVELOPE_READY_NO_READ"
EVIDENCE_DESIGN_NOT_READY_STATUS = "FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_NOT_READY"
CANDIDATE_MISSING_STATUS = "CANDIDATE_IDENTITY_MISSING_OR_INCOMPLETE"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

EVIDENCE_DESIGN_SCHEMA_VERSION = "cost_gate_fee_tier_maker_ratio_evidence_design_v1"
EVIDENCE_DESIGN_READY_STATUS = "FEE_TIER_MAKER_RATIO_EVIDENCE_DESIGN_READY_NO_ORDER"

IDENTITY_FIELDS = [
    "side_cell_key",
    "strategy_name",
    "symbol",
    "side",
    "outcome_horizon_minutes",
]

FEE_ENDPOINT = "/v5/account/fee-rate"
FEE_CATEGORY = "linear"
ALLOWED_METHOD = "GET"

BOUNDARY = (
    "source-only private fee-tier read envelope design; no private fee read, "
    "Bybit call, signed request, credential load, PG query/write, order, "
    "cancel, modify, config, risk, auth, runtime, service, env, or crontab "
    "mutation, Cost Gate lowering, freshness gate lowering, probe authority, "
    "order authority, live authority, ledger append, promotion proof, or "
    "profit proof"
)

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_packet_authorization_id",
    "auth_packet_typed_confirm_expected",
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
    "credential_load_performed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "mainnet_authority_granted",
    "network_call_performed",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority",
    "order_authority_granted",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "cost_gate_lowering_performed",
    "credential_material_loaded",
    "fee_tier_private_read_performed",
    "private_read_performed",
    "private_fee_read_allowed_by_this_packet",
    "private_fee_read_performed",
    "private_fee_tier_read_performed",
    "private_read_allowed_by_this_packet",
    "private_signed_request_performed",
    "read_authority_granted",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_mutation_performed",
    "secret_material_persisted",
    "service_restart_performed",
    "typed_confirm_matches",
    "writer_enabled",
}

FORBIDDEN_ALIAS_RULES = {
    "authority_granted_alias": ("authority", "granted"),
    "credential_loaded_alias": ("credential", "loaded"),
    "cost_gate_lowering_alias": ("cost", "gate", "lowering"),
    "cost_gate_proof_alias": ("cost", "gate", "proof"),
    "order_authority_alias": ("order", "authority"),
    "private_read_allowed_alias": ("private", "read", "allowed"),
    "private_read_performed_alias": ("private", "read", "performed"),
    "signed_request_performed_alias": ("signed", "request", "performed"),
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

FUTURE_CAPTURE_REQUIRED_FIELDS = [
    "read_invocation_id",
    "candidate_side_cell_key",
    "environment_scope",
    "base_url_class",
    "method",
    "path",
    "category",
    "symbol_filter",
    "request_started_at_utc",
    "request_completed_at_utc",
    "ret_code",
    "ret_msg",
    "response_payload_sha256",
    "sanitized_response_artifact_path",
    "fee_schedule_observed_at_utc",
    "fee_schedule_effective_at_utc_if_exchange_provided",
    "fee_tier_account_scope",
    "maker_fee_bps",
    "taker_fee_bps",
    "fee_currency_policy",
    "captured_by",
    "captured_at_utc",
    "e3_bb_review_id",
]


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        text = value.strip().lower()
        return bool(text) and text not in FALSE_SAFE_STRINGS
    return value is not None


def _normalize_key(key: Any) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in str(key))


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
        if _truthy(data.get("authorization_id")):
            reasons.append("authorization_id_present")
        if data.get("typed_confirm_expected") is not None:
            reasons.append("typed_confirm_expected_present")
        for key, value in data.items():
            if not _truthy(value):
                continue
            normalized_key = _normalize_key(key)
            if key in FORBIDDEN_TRUE_KEYS:
                reasons.append(f"{key}_true")
            for label, tokens in FORBIDDEN_ALIAS_RULES.items():
                if all(token in normalized_key for token in tokens):
                    reasons.append(f"{key}_true_alias_{label}")
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


def _evidence_design_ready(payload: dict[str, Any]) -> bool:
    return (
        payload.get("schema_version") == EVIDENCE_DESIGN_SCHEMA_VERSION
        and payload.get("status") == EVIDENCE_DESIGN_READY_STATUS
        and _dict(payload.get("summary")).get("fee_tier_maker_ratio_evidence_design_ready")
        is True
    )


def _build_envelope(candidate: dict[str, Any]) -> dict[str, Any]:
    symbol = str(candidate.get("symbol") or "").upper()
    return {
        "future_read_scope": {
            "purpose": "capture account-specific maker/taker fee rates for after-cost reconstruction",
            "allowed_method": ALLOWED_METHOD,
            "allowed_path": FEE_ENDPOINT,
            "allowed_query": {"category": FEE_CATEGORY},
            "symbol_filter_required_after_response_parse": symbol,
            "post_put_delete_or_order_paths_allowed": False,
            "wallet_balance_or_position_paths_allowed": False,
            "private_read_allowed_by_this_packet": False,
            "requires_separate_runtime_review_before_execution": True,
            "review_chain_required": "PM -> E3 -> BB -> PM",
        },
        "credential_and_transport_policy": {
            "credential_material_may_be_loaded_by_this_helper": False,
            "future_invocation_must_run_on_runtime_host": True,
            "future_invocation_must_use_existing_secret_slot_or_runtime_auth_helper": True,
            "secrets_in_argv_allowed": False,
            "auth_headers_in_artifact_allowed": False,
            "cookie_headers_allowed": False,
            "raw_request_signature_persisted": False,
            "redirects_allowed": False,
            "bounded_timeout_required": True,
            "single_invocation_per_review_id": True,
        },
        "future_capture_required_fields": FUTURE_CAPTURE_REQUIRED_FIELDS,
        "response_validation_policy": {
            "ret_code_zero_required_for_fee_proof": True,
            "result_list_required": True,
            "maker_fee_rate_field": "makerFeeRate",
            "taker_fee_rate_field": "takerFeeRate",
            "symbol_field": "symbol",
            "candidate_symbol_exact_match_required": symbol,
            "numeric_fee_rates_required": True,
            "zero_or_negative_maker_fee_policy": (
                "allowed as captured account economics if returned by Bybit, but "
                "must be labeled rebate_or_zero_fee and cannot be extrapolated "
                "without BB/QC review"
            ),
            "demo_unsupported_endpoint_policy": (
                "record unsupported/no-proof status; conservative defaults may keep runtime "
                "fail-closed or conservative, but cannot count as fee-tier proof"
            ),
            "no_matching_symbol_policy": "fail_closed_no_fee_proof",
            "freshness_window_required_for_future_proof": True,
            "fee_schedule_effective_time_policy": (
                "use observed/captured time unless Bybit provides an explicit "
                "effective timestamp"
            ),
        },
        "artifact_redaction_policy": {
            "store_sanitized_response_only": True,
            "hash_raw_response_before_redaction": True,
            "redact_headers": [
                "X-BAPI-API-KEY",
                "X-BAPI-SIGN",
                "X-BAPI-TIMESTAMP",
                "X-BAPI-RECV-WINDOW",
                "Authorization",
                "Cookie",
            ],
            "redact_request_signature": True,
            "redact_secret_slot_paths": True,
            "store_ret_code_ret_msg_and_fee_rows": True,
        },
        "proof_attachment_policy": {
            "attaches_only_to_candidate": candidate,
            "must_join_future_fills_by": [
                "candidate_side_cell_key",
                "symbol",
                "fee_schedule_observed_at_utc",
                "fee_schedule_effective_at_utc_if_exchange_provided",
                "captured_at_utc",
                "e3_bb_review_id",
            ],
            "modeled_or_default_fee_tier_is_not_proof": True,
            "private_read_without_review_is_not_proof": True,
            "cross_symbol_fee_rows_are_context_only": True,
        },
        "failure_conditions": [
            "private read is performed without a fresh PM/E3/BB review id",
            "response contains no exact candidate symbol fee row",
            "retCode is nonzero or endpoint unsupported",
            "sanitized artifact lacks raw response hash or capture timestamps",
            "any auth header, signature, cookie, or secret material is persisted",
            "fee evidence is used for order admission, Cost Gate proof, or promotion before candidate-matched fills exist",
        ],
        "max_safe_next_action": "submit_envelope_for_e3_bb_review_or_wait_for_real_p0_authorization_delta",
    }


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_private_fee_tier_read_envelope_design(
    *,
    fee_tier_maker_ratio_design: dict[str, Any] | None,
    fee_tier_maker_ratio_design_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    design = _dict(fee_tier_maker_ratio_design)
    authority_ok, authority_reasons = _authority_preserved(design)
    evidence_ready = _evidence_design_ready(design)
    candidate = _candidate(design)

    if not authority_ok:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "authority_boundary_violation_in_input"
    elif not evidence_ready:
        status = EVIDENCE_DESIGN_NOT_READY_STATUS
        reason = "fee_tier_maker_ratio_evidence_design_input_not_ready"
    elif not candidate:
        status = CANDIDATE_MISSING_STATUS
        reason = "candidate_identity_missing_or_incomplete"
    else:
        status = READY_STATUS
        reason = "private_fee_tier_read_envelope_ready_no_read"

    envelope = _build_envelope(candidate) if status == READY_STATUS else {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "source_inputs": {
            "fee_tier_maker_ratio_design_path_record_policy": "basename_and_sha256_only",
            "fee_tier_maker_ratio_design_path_basename": (
                fee_tier_maker_ratio_design_path.name
                if fee_tier_maker_ratio_design_path
                else None
            ),
            "fee_tier_maker_ratio_design_sha256": _sha256(fee_tier_maker_ratio_design_path),
            "fee_tier_maker_ratio_design_status": design.get("status"),
            "authority_preserved": authority_ok,
            "authority_contamination_reasons": authority_reasons,
            "candidate_present": bool(candidate),
        },
        "candidate": candidate if status == READY_STATUS else {},
        "envelope": envelope,
        "summary": {
            "private_fee_tier_read_envelope_ready": status == READY_STATUS,
            "candidate_side_cell_key": candidate.get("side_cell_key") if candidate else None,
            "private_fee_read_performed": False,
            "bybit_private_call_performed": False,
            "credential_load_performed": False,
            "runtime_invocation_ready": False,
            "order_admission_ready": False,
            "p0_authorization_required_before_probe": True,
            "e3_bb_review_required_before_private_read": True,
            "max_safe_next_action": (
                envelope.get("max_safe_next_action")
                if status == READY_STATUS
                else "refresh_ready_no_authority_fee_tier_maker_ratio_design"
            ),
        },
        "answers": {
            "source_only_research_artifact": True,
            "private_fee_tier_read_envelope_ready": status == READY_STATUS,
            "private_fee_read_allowed_by_this_packet": False,
            "private_fee_read_performed": False,
            "private_fee_tier_read_performed": False,
            "private_signed_request_performed": False,
            "credential_load_performed": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "network_call_performed": False,
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
    envelope = _dict(packet.get("envelope"))
    lines = [
        "# Private Fee-Tier Read Envelope Design",
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
    lines.extend(["", "## Future Read Envelope", ""])
    for key in (
        "future_read_scope",
        "credential_and_transport_policy",
        "response_validation_policy",
        "artifact_redaction_policy",
        "proof_attachment_policy",
        "failure_conditions",
        "max_safe_next_action",
    ):
        value = envelope.get(key)
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
    parser.add_argument("--fee-tier-maker-ratio-design-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_private_fee_tier_read_envelope_design(
        fee_tier_maker_ratio_design=_read_json(args.fee_tier_maker_ratio_design_json),
        fee_tier_maker_ratio_design_path=args.fee_tier_maker_ratio_design_json,
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

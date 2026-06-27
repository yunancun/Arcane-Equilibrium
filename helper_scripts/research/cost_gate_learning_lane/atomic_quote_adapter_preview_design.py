#!/usr/bin/env python3
"""Build a source-only atomic quote->adapter->preview design packet.

The packet describes a future reviewed flow that captures one public quote and
immediately feeds it through the existing public quote adapter and no-order
construction preview. It does not perform capture, adapter execution,
construction preview, Bybit calls, PG access, runtime mutation, or authority
grants.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "cost_gate_atomic_quote_adapter_preview_design_v1"
READY_STATUS = "ATOMIC_QUOTE_ADAPTER_PREVIEW_DESIGN_READY_NO_CAPTURE_NO_AUTHORITY"
REVIEWED_PACKET_NOT_READY_STATUS = "REVIEWED_PUBLIC_QUOTE_PACKET_NOT_READY"
STALE_ADAPTER_EVIDENCE_MISSING_STATUS = "STALE_ADAPTER_EVIDENCE_MISSING"
FRESHNESS_GATE_INVALID_STATUS = "FRESHNESS_GATE_INVALID"
AUTHORITY_BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"

REVIEWED_PACKET_SCHEMA_VERSION = "cost_gate_reviewed_public_quote_capture_packet_v1"
REVIEWED_PACKET_READY_STATUS = (
    "REVIEWED_PUBLIC_QUOTE_CAPTURE_PACKET_READY_NO_CAPTURE_NO_AUTHORITY"
)
STALE_REVIEW_BLOCKER_ID = (
    "P1-AGGRESSIVE-ALPHA-QUOTE-TO-ADAPTER-FRESHNESS-REVIEW-NO-ORDER"
)
STALE_REVIEW_NEXT_BLOCKER_ID = (
    "P1-AGGRESSIVE-ALPHA-ATOMIC-QUOTE-ADAPTER-PREVIEW-DESIGN-NO-CAPTURE"
)
CANONICAL_MAX_FRESH_BBO_AGE_MS = 1000
SYMBOL_RE = re.compile(r"^[A-Z0-9]{3,40}$")

CAPTURE_HELPER = (
    "helper_scripts/research/cost_gate_learning_lane/"
    "bbo_freshness_public_quote_capture.py"
)
ADAPTER_HELPER = (
    "helper_scripts/research/cost_gate_learning_lane/"
    "public_quote_market_snapshot_adapter.py"
)
PREVIEW_HELPER = (
    "helper_scripts/research/cost_gate_learning_lane/"
    "bounded_probe_candidate_construction_preview.py"
)
MARKET_SNAPSHOT_SCHEMA_VERSION = "bounded_probe_candidate_market_snapshot_v1"
PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_STATUS = "PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_NO_ORDER"
PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE = (
    "bybit_public_quote_capture:bbo_freshness_public_quote_capture_v1"
)

BOUNDARY = (
    "source-only atomic quote-adapter-preview design; no quote capture, network "
    "call, Bybit call, adapter execution, construction preview execution, PG "
    "query/write, _latest overwrite, order, cancel, modify, config, risk, auth, "
    "runtime/service/env/crontab mutation, Cost Gate lowering, freshness gate "
    "lowering, probe authority, order authority, live/mainnet authority, ledger "
    "append, or promotion proof"
)

FORBIDDEN_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled",
    "auth_headers_present",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "canonical_plan_mutation_performed",
    "cap_envelope_mutation_allowed",
    "cap_mutation_performed",
    "config_mutation_performed",
    "cookie_headers_present",
    "cost_gate_lowering_recommended",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "exchange_call_performed",
    "freshness_gate_lowering_recommended",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_promotion_performed",
    "network_call_performed",
    "operator_authorization_object_emitted",
    "order_admission_ready",
    "order_authority_granted",
    "order_cancel_performed",
    "order_cancel_modify_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_query_performed",
    "pg_write_performed",
    "placement_call_performed",
    "plan_mutation_performed",
    "private_endpoint_called",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_proof",
    "public_quote_capture_allowed_by_this_packet",
    "public_quote_capture_performed",
    "review_grants_runtime_authority",
    "risk_mutation_performed",
    "runtime_env_mutation_performed",
    "runtime_mutation_performed",
    "runtime_order_authority_found",
    "runtime_order_authority_granted",
    "runtime_probe_authority_found",
    "runtime_probe_authority_granted",
    "service_restart_performed",
    "writer_enabled",
}
SEMANTIC_AUTHORITY_RE = re.compile(
    r"(?i)("
    r"\bsubmit[_ -]?orders?\b|"
    r"\b(?:may|can|allowed|authorized|permit(?:ted)?|permission)\s+"
    r"(?:to\s+)?(?:submit|place|create|cancel|modify)\s+orders?\b|"
    r"\b(?:order|probe|live|runtime[_ -]?order|runtime[_ -]?probe)[_ -]?"
    r"authority\s+(?:granted|enabled|allowed|authorized|present|true|found)\b|"
    r"\bbounded[_ -]?demo[_ -]?probe\s+(?:authorized|granted|enabled)\b|"
    r"\b(?:private[_ -]?endpoint|auth[_ -]?headers?|cookie[_ -]?headers?|"
    r"pg[_ -]?(?:query|write)|runtime[_ -]?mutation|service[_ -]?restart|"
    r"crontab[_ -]?mutation|risk[_ -]?mutation|cost[_ -]?gate[_ -]?lower(?:ing|ed)?|"
    r"freshness[_ -]?gate[_ -]?lower(?:ing|ed)?|promotion[_ -]?(?:evidence|proof)|"
    r"writer[_ -]?enabled|adapter[_ -]?enabled)\s*"
    r"(?:true|yes|allowed|enabled|performed|present|found)\b|"
    r"\b(?:place|create|cancel|modify)[_ -]?orders?\b"
    r")"
)
FORBIDDEN_OUTPUT_MARKERS = ("_latest", "latest.")
SEMANTIC_VALUE_KEYS = {
    "action",
    "actions",
    "allowed_actions",
    "authorization",
    "authority",
    "capabilities",
    "comment",
    "comments",
    "decision_details",
    "grant",
    "grants",
    "note",
    "notes",
    "operator_note",
    "operator_response",
    "permissions",
    "reason",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _str(value: Any) -> str:
    return str(value or "").strip()


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "none", "null"}
    if isinstance(value, (dict, list, tuple, set)):
        return len(value) > 0
    return True


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists() or not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iter_nodes(value: Any) -> list[Any]:
    out = [value]
    if isinstance(value, dict):
        for child in value.values():
            out.extend(_iter_nodes(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(_iter_nodes(child))
    return out


def _value_has_semantic_authority(value: Any) -> bool:
    if isinstance(value, str):
        return bool(SEMANTIC_AUTHORITY_RE.search(value))
    if isinstance(value, list):
        return any(_value_has_semantic_authority(item) for item in value)
    if isinstance(value, dict):
        return any(_value_has_semantic_authority(item) for item in value.values())
    return False


def _authority_contamination_reasons(*payloads: dict[str, Any] | None) -> list[str]:
    reasons: list[str] = []
    for payload in payloads:
        for node in _iter_nodes(payload):
            if not isinstance(node, dict):
                continue
            adjustment = node.get("main_cost_gate_adjustment")
            if adjustment not in (None, "", "NONE"):
                reasons.append("main_cost_gate_adjustment_not_none")
            for key in FORBIDDEN_TRUE_KEYS:
                if _truthy(node.get(key)):
                    reasons.append(f"{key}_contaminating")
            for key, value in node.items():
                key_text = _str(key)
                if key_text not in FORBIDDEN_TRUE_KEYS and SEMANTIC_AUTHORITY_RE.search(key_text):
                    if _truthy(value):
                        reasons.append(f"{key_text}_semantic_key_contaminating")
                if key_text in SEMANTIC_VALUE_KEYS and _value_has_semantic_authority(value):
                    reasons.append(f"{key_text}_semantic_value_contaminating")
    return sorted(set(reasons))


def _request_specs(reviewed_packet: dict[str, Any]) -> list[dict[str, Any]]:
    review = _dict(reviewed_packet.get("review_packet"))
    envelope = _dict(review.get("request_envelope_review"))
    return _list(envelope.get("required_requests"))


def _normalized_horizon(value: Any) -> int | None:
    parsed = _float(value)
    if parsed is None or not parsed.is_integer():
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


def _reviewed_packet_reasons(reviewed_packet: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if reviewed_packet.get("schema_version") != REVIEWED_PACKET_SCHEMA_VERSION:
        reasons.append("reviewed_packet_schema_mismatch")
    if reviewed_packet.get("status") != REVIEWED_PACKET_READY_STATUS:
        reasons.append("reviewed_packet_status_not_ready")
    candidate = _dict(reviewed_packet.get("candidate"))
    reasons.extend(_candidate_identity_reasons(candidate))
    symbol = _str(candidate.get("symbol")).upper()
    summary = _dict(reviewed_packet.get("summary"))
    if summary.get("runtime_capture_allowed_by_this_packet") is not False:
        reasons.append("runtime_capture_allowed_by_reviewed_packet")
    if summary.get("public_quote_capture_performed") is not False:
        reasons.append("reviewed_packet_already_captured_quote")
    if summary.get("network_call_performed") is not False:
        reasons.append("reviewed_packet_network_call_performed")
    if summary.get("request_count") != 3:
        reasons.append("reviewed_packet_request_count_not_three")

    review = _dict(reviewed_packet.get("review_packet"))
    future_capture = _dict(review.get("future_capture_source"))
    if future_capture.get("source_helper") != CAPTURE_HELPER:
        reasons.append("capture_helper_mismatch")
    if future_capture.get("requires_separate_pm_e3_bb_review_before_runtime_capture") is not True:
        reasons.append("pm_e3_bb_review_not_required")
    if future_capture.get("runtime_capture_allowed_by_this_packet") is not False:
        reasons.append("future_capture_runtime_allowed_by_packet")

    envelope = _dict(review.get("request_envelope_review"))
    if envelope.get("method") != "GET":
        reasons.append("request_method_not_get")
    if envelope.get("auth_or_cookie_headers_allowed") is not False:
        reasons.append("auth_or_cookie_headers_allowed")
    if envelope.get("private_or_order_paths_allowed") is not False:
        reasons.append("private_or_order_paths_allowed")
    if envelope.get("redirects_allowed") is not False:
        reasons.append("redirects_allowed")
    if envelope.get("additional_requests_allowed") is not False:
        reasons.append("additional_requests_allowed")
    required = _request_specs(reviewed_packet)
    expected_paths = {
        "server_time": ("/v5/market/time", {}),
        "ticker": ("/v5/market/tickers", {"category": "linear", "symbol": symbol}),
        "instrument": (
            "/v5/market/instruments-info",
            {"category": "linear", "symbol": symbol},
        ),
    }
    if len(required) != 3:
        reasons.append("required_request_specs_not_three")
    for request in required:
        label = request.get("label")
        expected = expected_paths.get(label)
        if expected is None:
            reasons.append(f"unexpected_request_label_{label}")
            continue
        path, query = expected
        if request.get("method") != "GET":
            reasons.append(f"{label}_method_not_get")
        if request.get("path") != path:
            reasons.append(f"{label}_path_mismatch")
        if request.get("query") != query:
            reasons.append(f"{label}_query_mismatch")
        if request.get("auth_or_cookie_headers_allowed") is not False:
            reasons.append(f"{label}_auth_cookie_allowed")
        if request.get("private_or_order_paths_allowed") is not False:
            reasons.append(f"{label}_private_or_order_allowed")
        if request.get("capture_permitted_by_this_packet") is not False:
            reasons.append(f"{label}_capture_permitted_by_packet")

    gates = _dict(review.get("freshness_and_market_data_gates"))
    freshness = _float(gates.get("max_fresh_bbo_age_ms"))
    if freshness is None or freshness <= 0:
        reasons.append("freshness_gate_missing")
    elif freshness > CANONICAL_MAX_FRESH_BBO_AGE_MS:
        reasons.append("freshness_gate_wider_than_canonical")
    if gates.get("raw_public_quote_is_not_construction_input") is not True:
        reasons.append("raw_quote_not_forbidden_as_construction_input")

    handoff = _dict(review.get("handoff_contract"))
    adapter = _dict(handoff.get("public_quote_to_snapshot_adapter"))
    preview = _dict(handoff.get("snapshot_to_construction_preview"))
    if handoff.get("raw_quote_can_feed_order_construction_directly") is not False:
        reasons.append("raw_quote_direct_construction_not_false")
    if adapter.get("source_helper") != ADAPTER_HELPER:
        reasons.append("adapter_helper_mismatch")
    if adapter.get("requires_public_quote_path_sha") is not True:
        reasons.append("adapter_quote_sha_not_required")
    if adapter.get("requires_candidate_exact_match") is not True:
        reasons.append("adapter_candidate_match_not_required")
    if preview.get("source_helper") != PREVIEW_HELPER:
        reasons.append("preview_helper_mismatch")
    if preview.get("requires_fresh_bbo") is not True:
        reasons.append("preview_fresh_bbo_not_required")
    if preview.get("order_admission_ready_from_this_contract") is not False:
        reasons.append("preview_order_admission_not_false")
    return sorted(set(reasons))


def _stale_evidence_reasons(session_state: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if session_state.get("active_blocker_id") != STALE_REVIEW_BLOCKER_ID:
        reasons.append("stale_review_blocker_mismatch")
    if session_state.get("next_blocker_id") != STALE_REVIEW_NEXT_BLOCKER_ID:
        reasons.append("stale_review_next_blocker_mismatch")
    evidence = _str(session_state.get("new_evidence_delta_found"))
    if "public_quote_stale_at_adapter_generation" not in evidence:
        reasons.append("stale_adapter_failure_reason_missing")
    if "no market snapshot or construction preview" not in evidence.lower():
        reasons.append("stale_adapter_no_output_statement_missing")
    anti_repeat = _str(session_state.get("anti_repeat_decision"))
    if anti_repeat != "PROCEED_SOURCE_ONLY_FRESHNESS_REVIEW_NO_SECOND_CAPTURE":
        reasons.append("stale_review_anti_repeat_mismatch")
    artifacts = _dict(session_state.get("artifact_mtimes"))
    quote = _dict(artifacts.get("local_public_quote_capture"))
    if quote.get("status") != "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER":
        reasons.append("stale_review_quote_capture_status_missing")
    if _str(quote.get("sha256")) == "":
        reasons.append("stale_review_quote_capture_sha_missing")
    if _float(quote.get("max_fresh_bbo_age_ms")) != CANONICAL_MAX_FRESH_BBO_AGE_MS:
        reasons.append("stale_review_quote_freshness_gate_mismatch")
    attempt = _dict(artifacts.get("adapter_cli_attempt"))
    if attempt.get("command_exit_code") in (None, 0, "0"):
        reasons.append("adapter_cli_attempt_nonzero_exit_missing")
    if attempt.get("fail_closed_reason") != "public_quote_stale_at_adapter_generation":
        reasons.append("adapter_cli_attempt_fail_closed_reason_missing")
    for key in (
        "json_output_exists",
        "markdown_output_exists",
        "market_snapshot_emitted",
        "construction_preview_emitted",
    ):
        if attempt.get(key) is not False:
            reasons.append(f"adapter_cli_attempt_{key}_not_false")
    return reasons


def _atomic_design(
    *,
    reviewed_packet: dict[str, Any],
    reviewed_packet_path: Path | None,
    stale_review_path: Path | None,
) -> dict[str, Any]:
    review = _dict(reviewed_packet.get("review_packet"))
    gates = _dict(review.get("freshness_and_market_data_gates"))
    candidate = _dict(reviewed_packet.get("candidate"))
    return {
        "mode": "future_single_reviewed_capture_immediate_adapter_immediate_no_order_preview",
        "design_only_no_capture": True,
        "candidate": candidate,
        "source_inputs": {
            "reviewed_public_quote_packet_path": str(reviewed_packet_path)
            if reviewed_packet_path
            else None,
            "reviewed_public_quote_packet_sha256": _sha256(reviewed_packet_path),
            "stale_adapter_review_session_path": str(stale_review_path)
            if stale_review_path
            else None,
            "stale_adapter_review_session_sha256": _sha256(stale_review_path),
        },
        "future_runtime_preconditions": [
            "open fresh session_loop_state before any capture",
            "rerun PM->E3->BB review for the exact runtime public quote invocation",
            "use one unique timestamped output directory only",
            "do not overwrite _latest artifacts",
            "record source head, runtime head, request hashes, response hashes, and timestamps",
            "stop on nonzero retCode, transport failure, stale BBO, adapter failure, or construction-preview non-ready status",
        ],
        "atomic_flow_steps": [
            {
                "step": 1,
                "name": "public_quote_capture",
                "helper": CAPTURE_HELPER,
                "runtime_or_exchange_facing": True,
                "requires_pm_e3_bb_review": True,
                "allowed_request_count": 3,
                "forbidden_flags": ["--skip-instruments-info"],
                "json_output_template": "$RUN_DIR/public_quote.json",
                "markdown_output_template": "$RUN_DIR/public_quote.md",
                "authority_granted_by_step": False,
            },
            {
                "step": 2,
                "name": "immediate_public_quote_to_market_snapshot_adapter",
                "helper": ADAPTER_HELPER,
                "runtime_or_exchange_facing": False,
                "requires_input_from_prior_step": "$RUN_DIR/public_quote.json",
                "requires_reroute_review_path_sha": True,
                "max_fresh_bbo_age_ms": CANONICAL_MAX_FRESH_BBO_AGE_MS,
                "generated_at_override_allowed": False,
                "json_output_template": "$RUN_DIR/market_snapshot.json",
                "markdown_output_template": "$RUN_DIR/market_snapshot.md",
                "authority_granted_by_step": False,
            },
            {
                "step": 3,
                "name": "immediate_no_order_construction_preview",
                "helper": PREVIEW_HELPER,
                "runtime_or_exchange_facing": False,
                "requires_input_from_prior_step": "$RUN_DIR/market_snapshot.json",
                "requires_market_snapshot_schema_version": MARKET_SNAPSHOT_SCHEMA_VERSION,
                "requires_market_snapshot_source": PUBLIC_QUOTE_MARKET_SNAPSHOT_SOURCE,
                "requires_adapter_status": PUBLIC_QUOTE_MARKET_SNAPSHOT_READY_STATUS,
                "requires_adapter_helper": ADAPTER_HELPER,
                "requires_adapter_public_quote_path_sha256": True,
                "requires_adapter_reroute_review_path_sha256": True,
                "requires_public_quote_artifact_status": "PUBLIC_QUOTE_CAPTURE_READY_NO_ORDER",
                "requires_fresh_bbo": True,
                "order_submission_allowed": False,
                "json_output_template": "$RUN_DIR/construction_preview.json",
                "markdown_output_template": "$RUN_DIR/construction_preview.md",
                "authority_granted_by_step": False,
            },
            {
                "step": 4,
                "name": "atomic_summary_packet",
                "helper": "source_only_summary_from_artifacts",
                "runtime_or_exchange_facing": False,
                "requires_all_prior_artifact_paths_and_sha256": True,
                "json_output_template": "$RUN_DIR/atomic_quote_adapter_preview_summary.json",
                "authority_granted_by_step": False,
            },
        ],
        "freshness_contract": {
            "max_fresh_bbo_age_ms": gates.get(
                "max_fresh_bbo_age_ms",
                CANONICAL_MAX_FRESH_BBO_AGE_MS,
            ),
            "must_not_lower_or_widen_freshness_gate": True,
            "adapter_must_fail_closed_if_quote_is_stale_at_adapter_generation": True,
            "raw_public_quote_may_not_feed_construction_directly": True,
            "adapter_generation_must_be_immediate_after_capture": True,
        },
        "failure_conditions": [
            "no_pm_e3_bb_review_for_future_capture",
            "second_capture_on_old_review_evidence",
            "auth_or_cookie_header_present",
            "private_or_order_endpoint_used",
            "skip_instruments_info_used",
            "ret_code_nonzero_or_response_hash_missing",
            "bbo_stale_at_capture_or_adapter_generation",
            "generated_at_override_or_freshness_gate_widening",
            "raw_quote_used_as_construction_input",
            "market_snapshot_missing_path_or_sha_provenance",
            "construction_preview_non_ready_or_order_admission_claimed",
            "pg_or_runtime_or_risk_or_plan_mutation_attempted",
        ],
        "proof_exclusions": [
            "public_quote_capture",
            "adapter_market_snapshot",
            "no_order_construction_preview",
            "source_smoke",
            "artifact_count",
            "unattributed_fills",
            "flash_dip_buy",
            "cleanup_or_risk_close_fills",
        ],
        "max_safe_next_action": (
            "pm_e3_bb_review_atomic_public_quote_capture_adapter_preview_runtime_invocation"
        ),
    }


def build_atomic_quote_adapter_preview_design(
    *,
    reviewed_public_quote_packet: dict[str, Any] | None,
    stale_adapter_review_session: dict[str, Any] | None,
    reviewed_public_quote_packet_path: Path | None = None,
    stale_adapter_review_session_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    reviewed = _dict(reviewed_public_quote_packet)
    stale = _dict(stale_adapter_review_session)
    authority_reasons = _authority_contamination_reasons(reviewed, stale)
    reviewed_reasons = _reviewed_packet_reasons(reviewed)
    stale_reasons = _stale_evidence_reasons(stale)

    status = READY_STATUS
    reason = "atomic_quote_adapter_preview_design_ready_no_capture"
    if authority_reasons:
        status = AUTHORITY_BOUNDARY_VIOLATION_STATUS
        reason = "input_contains_authority_or_mutation_contamination"
    elif reviewed_reasons:
        status = REVIEWED_PACKET_NOT_READY_STATUS
        reason = "reviewed_public_quote_packet_not_ready_for_atomic_design"
    elif stale_reasons:
        status = STALE_ADAPTER_EVIDENCE_MISSING_STATUS
        reason = "stale_adapter_failure_evidence_required"
    else:
        gates = _dict(_dict(reviewed.get("review_packet")).get("freshness_and_market_data_gates"))
        freshness = _float(gates.get("max_fresh_bbo_age_ms"))
        if freshness is None or freshness <= 0 or freshness > CANONICAL_MAX_FRESH_BBO_AGE_MS:
            status = FRESHNESS_GATE_INVALID_STATUS
            reason = "canonical_freshness_gate_required"

    design = (
        _atomic_design(
            reviewed_packet=reviewed,
            reviewed_packet_path=reviewed_public_quote_packet_path,
            stale_review_path=stale_adapter_review_session_path,
        )
        if status == READY_STATUS
        else {}
    )
    blocking_reasons = sorted(set(authority_reasons + reviewed_reasons + stale_reasons))
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": _dict(reviewed.get("candidate")) if status == READY_STATUS else {},
        "readiness": {
            "authority_preserved": not authority_reasons,
            "authority_contamination_reasons": authority_reasons,
            "reviewed_packet_ready": not reviewed_reasons,
            "reviewed_packet_reasons": reviewed_reasons,
            "stale_adapter_evidence_present": not stale_reasons,
            "stale_adapter_evidence_reasons": stale_reasons,
            "blocking_reasons": blocking_reasons,
            "blocking_reason_count": len(blocking_reasons),
            "design_ready_no_capture": status == READY_STATUS,
        },
        "design": design,
        "summary": {
            "atomic_design_ready": status == READY_STATUS,
            "candidate_side_cell_key": _dict(reviewed.get("candidate")).get("side_cell_key"),
            "future_capture_required": status == READY_STATUS,
            "capture_performed_by_this_packet": False,
            "adapter_performed_by_this_packet": False,
            "construction_preview_performed_by_this_packet": False,
            "order_admission_ready": False,
            "pm_e3_bb_required_before_future_capture": status == READY_STATUS,
            "max_fresh_bbo_age_ms": (
                _dict(_dict(reviewed.get("review_packet")).get("freshness_and_market_data_gates")).get(
                    "max_fresh_bbo_age_ms"
                )
                if status == READY_STATUS
                else None
            ),
            "max_safe_next_action": design.get("max_safe_next_action")
            if design
            else "refresh_ready_no_authority_inputs",
        },
        "answers": {
            "source_only_research_artifact": True,
            "atomic_design_ready": status == READY_STATUS,
            "public_quote_capture_performed": False,
            "adapter_execution_performed": False,
            "construction_preview_performed": False,
            "network_call_performed": False,
            "bybit_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "bybit_private_call_performed": False,
            "auth_headers_present": False,
            "cookie_headers_present": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "runtime_mutation_performed": False,
            "runtime_env_mutation_performed": False,
            "service_restart_performed": False,
            "crontab_mutation_performed": False,
            "config_mutation_performed": False,
            "risk_mutation_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "freshness_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "bounded_demo_probe_authorized": False,
            "operator_authorization_object_emitted": False,
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
    design = _dict(packet.get("design"))
    lines = [
        "# Atomic Quote Adapter Preview Design No-Capture",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Candidate: `{_dict(packet.get('candidate')).get('side_cell_key')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Atomic Flow Steps",
        "",
    ]
    for step in _list(design.get("atomic_flow_steps")):
        lines.append(
            f"- `{step.get('step')}` `{step.get('name')}` via `{step.get('helper')}`"
        )
    lines.extend(["", "## Failure Conditions", ""])
    for item in _list(design.get("failure_conditions")):
        lines.append(f"- `{item}`")
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _output_path_allowed(path: Path | None) -> tuple[bool, str | None]:
    if path is None:
        return True, None
    name = path.name
    if any(marker in name for marker in FORBIDDEN_OUTPUT_MARKERS):
        return False, "output_path_latest_overwrite_forbidden"
    resolved = path.resolve(strict=False)
    canonical_runtime = Path("/tmp/openclaw/cost_gate_learning_lane").resolve(
        strict=False
    )
    if resolved == canonical_runtime or canonical_runtime in resolved.parents:
        return False, "canonical_runtime_artifact_path_forbidden"
    return True, None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviewed-public-quote-packet-json", type=Path, required=True)
    parser.add_argument("--stale-adapter-review-session-json", type=Path, required=True)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    for path in (args.json_output, args.output):
        ok, reason = _output_path_allowed(path)
        if not ok:
            raise SystemExit(reason)
    packet = build_atomic_quote_adapter_preview_design(
        reviewed_public_quote_packet=_read_json(args.reviewed_public_quote_packet_json),
        stale_adapter_review_session=_read_json(args.stale_adapter_review_session_json),
        reviewed_public_quote_packet_path=args.reviewed_public_quote_packet_json,
        stale_adapter_review_session_path=args.stale_adapter_review_session_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, sort_keys=True, ensure_ascii=False))
    if not args.json_output and not args.output and not args.print_json:
        print(markdown, end="")
    return 0 if packet.get("status") == READY_STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())

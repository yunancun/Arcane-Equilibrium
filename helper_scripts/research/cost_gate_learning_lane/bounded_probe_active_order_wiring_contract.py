#!/usr/bin/env python3
"""Build the source-only active-order wiring contract for bounded Demo probes.

The contract is intentionally narrower than an exchange/order review. It
defines the Rust source seams that must exist before a candidate-matched
bounded Demo probe can move to E3/BB exchange-facing review.

It does not query PG, call Bybit, submit/cancel/modify orders, write plans or
ledgers, mutate runtime state, lower the Cost Gate, grant probe/order authority,
or create promotion proof.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cost_gate_learning_lane.bounded_probe_authority_patch_readiness import (
    _active_order_submission_readiness,
)


ACTIVE_ORDER_WIRING_CONTRACT_SCHEMA_VERSION = (
    "bounded_demo_probe_active_order_wiring_contract_v1"
)
READY_STATUS = "ACTIVE_ORDER_WIRING_CONTRACT_READY_FOR_E3_BB_REVIEW"
PATCH_REQUIRED_STATUS = "ACTIVE_ORDER_WIRING_SOURCE_PATCH_REQUIRED"
BOUNDARY_VIOLATION_STATUS = "AUTHORITY_BOUNDARY_VIOLATION"
BOUNDARY = (
    "source-only active bounded Demo order wiring contract; no PG query/write, "
    "Bybit call, order/cancel/modify, plan or ledger mutation, runtime/service/"
    "env/crontab mutation, Rust writer enablement, Cost Gate lowering, active "
    "probe/order/live authority, or promotion proof"
)


@dataclass(frozen=True)
class Requirement:
    check_id: str
    category: str
    description: str
    paths: tuple[str, ...]
    pattern_groups: tuple[tuple[str, ...], ...]
    missing_reason: str


SOURCE_REQUIREMENTS: tuple[Requirement, ...] = (
    Requirement(
        check_id="candidate_matched_active_order_module",
        category="new_active_order_module",
        description=(
            "A dedicated Rust module must build candidate-matched bounded Demo "
            "orders without using a Python/API side path."
        ),
        paths=("rust/openclaw_engine/src/bounded_probe_active_order.rs",),
        pattern_groups=(
            ("ActiveBoundedProbeOrderRequest",),
            ("ActiveBoundedProbeOrderDecision",),
            ("candidate_matched_bounded_probe_order",),
            ("bounded_probe_attempt",),
            ("side_cell_key",),
        ),
        missing_reason="bounded_probe_active_order_module_missing",
    ),
    Requirement(
        check_id="demo_only_bounded_limits",
        category="risk_boundary",
        description=(
            "The active module must constrain the path to demo/live_demo, one "
            "admitted order attempt, and explicit notional/probe-count bounds."
        ),
        paths=(
            "rust/openclaw_engine/src/bounded_probe_active_order.rs",
            "rust/openclaw_engine/src/demo_learning_lane.rs",
        ),
        pattern_groups=(
            ("demo_only", "learning_probe_admission_is_demo_only"),
            ("live_demo",),
            ("max_demo_notional_usdt_per_order",),
            ("max_probe_intents_before_review", "max_probe_orders"),
            ("one_order_per_admitted_attempt",),
        ),
        missing_reason="demo_only_bounded_order_limits_missing",
    ),
    Requirement(
        check_id="post_only_near_touch_order_envelope",
        category="execution_boundary",
        description=(
            "The order envelope must be post-only near-touch limit-or-skip, with "
            "fresh BBO and initial gap guards carried into the active path."
        ),
        paths=(
            "rust/openclaw_engine/src/bounded_probe_active_order.rs",
            "rust/openclaw_engine/src/bounded_probe_near_touch.rs",
            "rust/openclaw_engine/src/order_manager.rs",
        ),
        pattern_groups=(
            ("post_only_near_touch_or_skip",),
            ("TimeInForce::PostOnly", "TimeInForce { PostOnly }"),
            ("OrderType::Limit", "order_type: OrderType::Limit"),
            ("limit_price",),
            ("max_fresh_bbo_age_ms", "DEFAULT_MAX_FRESH_BBO_AGE_MS"),
            ("max_initial_passive_gap_bps", "DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS"),
        ),
        missing_reason="post_only_near_touch_order_envelope_missing",
    ),
    Requirement(
        check_id="guardian_decision_lease_rust_authority_gate",
        category="governance_boundary",
        description=(
            "Active wiring must stay inside the existing Rust admission, risk, "
            "operator authorization, and Decision Lease authority path."
        ),
        paths=(
            "rust/openclaw_engine/src/bounded_probe_active_order.rs",
            "rust/openclaw_engine/src/demo_learning_lane.rs",
            "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
        ),
        pattern_groups=(
            ("evaluate_probe_admission",),
            ("allowed_to_submit_order",),
            ("ORDER_AUTHORITY_GRANTED",),
            ("risk_state", "RiskStateNotNormal"),
            ("validate_operator_authorization",),
            ("LeaseOutcome::Consumed", "DecisionLease", "Decision Lease"),
            ("main_cost_gate_adjustment",),
        ),
        missing_reason="guardian_decision_lease_rust_authority_gate_missing",
    ),
    Requirement(
        check_id="tick_dispatch_exchange_wiring",
        category="dispatch_boundary",
        description=(
            "The on-tick dispatch path must forward only an admitted bounded "
            "probe order request to the existing exchange dispatch channel."
        ),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        pattern_groups=(
            ("dispatch_admitted_bounded_probe_order", "active_bounded_probe_order_submission"),
            ("candidate_matched_bounded_probe_order",),
            ("OrderDispatchRequest",),
            ("tx.send",),
            ("order_link_id",),
            ("context_id",),
            ("signal_id",),
        ),
        missing_reason="tick_dispatch_active_bounded_probe_exchange_wiring_missing",
    ),
    Requirement(
        check_id="reconstructable_lineage_and_outcome_hooks",
        category="audit_boundary",
        description=(
            "The active path must preserve attempt, order, fill, fee, slippage, "
            "and matched-control lineage so Demo evidence can later transfer to "
            "live review without losing reconstructability."
        ),
        paths=(
            "rust/openclaw_engine/src/bounded_probe_active_order.rs",
            "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",
            "rust/openclaw_engine/src/order_manager.rs",
        ),
        pattern_groups=(
            ("side_cell_key",),
            ("context_id",),
            ("signal_id",),
            ("bounded_probe_attempt",),
            ("order_id",),
            ("order_link_id",),
            ("fill_id",),
            ("fee", "exec_fee"),
            ("slippage_bps",),
            ("matched_blocked_control",),
        ),
        missing_reason="candidate_matched_order_fill_fee_slippage_lineage_missing",
    ),
)


AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "api_call_performed",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "canonical_plan_mutation_performed",
    "cost_gate_mutation_found",
    "crontab_edit_performed",
    "crontab_mutation_performed",
    "auth_mutation_performed",
    "env_mutation_performed",
    "ledger_append_performed",
    "live_execution_allowed",
    "global_cost_gate_lowering_recommended",
    "live_authority_granted",
    "order_authority_granted",
    "order_cancel_modify_performed",
    "order_cancel_performed",
    "order_modify_performed",
    "order_submission_performed",
    "pg_write_performed",
    "plan_mutation_performed",
    "probe_authority_granted",
    "promotion_evidence",
    "promotion_evidence_found",
    "promotion_proof",
    "risk_mutation_performed",
    "runtime_config_mutation_performed",
    "runtime_env_mutation_performed",
    "runtime_mutation_performed",
    "runtime_order_authority_found",
    "runtime_probe_authority_found",
    "rust_writer_enabled",
    "service_restart_performed",
    "service_mutation_performed",
    "writer_enablement_performed",
    "writer_enabled",
}
AUTHORITY_DENY_KEY_SUBSTRINGS = {
    "authority_granted",
    "authority_granted_in_object",
    "authority_found",
    "execution_authority",
    "live_authority",
    "mainnet_authority",
    "order_authority",
    "probe_authority",
    "bounded_demo_probe_authorized",
}
DANGEROUS_STATE_KEY_TOKENS = {
    "api",
    "bybit",
    "cancel",
    "config",
    "cost_gate",
    "crontab",
    "database",
    "db",
    "endpoint",
    "env",
    "environment",
    "live",
    "mainnet",
    "modify",
    "mutation",
    "order",
    "pg",
    "private",
    "probe",
    "promotion",
    "proof",
    "risk",
    "runtime",
    "service",
    "writer",
}
DANGEROUS_ACTION_KEY_TOKENS = {
    "adjustment",
    "adjusted",
    "allowed",
    "authorized",
    "called",
    "call",
    "enabled",
    "enable",
    "evidence",
    "found",
    "granted",
    "lowered",
    "lowering",
    "mutated",
    "mutation",
    "performed",
    "proof",
    "submitted",
    "write",
    "written",
}
AUTHORITY_ENUM_KEYS = {
    "execution_authority",
    "live_authority",
    "order_authority",
    "probe_authority",
}
AUTHORITY_ENUM_SAFE_VALUES = {
    None,
    "",
    "NONE",
    "NOT_GRANTED",
    "FALSE",
    "NO",
    "OFF",
    "DISABLED",
    False,
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "off", "none", "not_granted"}:
            return False
        return True
    return False


def _safe_authority_enum(value: Any) -> bool:
    try:
        if value in AUTHORITY_ENUM_SAFE_VALUES:
            return True
    except TypeError:
        return False
    if isinstance(value, str) and value.strip().upper() in AUTHORITY_ENUM_SAFE_VALUES:
        return True
    return False


def _is_dangerous_truthy_key(key: str) -> bool:
    normalized = key.strip().lower()
    if normalized in AUTHORITY_TRUE_KEYS:
        return True
    if any(fragment in normalized for fragment in AUTHORITY_DENY_KEY_SUBSTRINGS):
        return True
    return any(token in normalized for token in DANGEROUS_STATE_KEY_TOKENS) and any(
        token in normalized for token in DANGEROUS_ACTION_KEY_TOKENS
    )


def _strip_rust_comments_and_strings(text: str) -> str:
    def mask(segment: str) -> str:
        return "".join("\n" if char == "\n" else " " for char in segment)

    def mask_macro_invocations(code: str) -> str:
        out: list[str] = []
        idx = 0
        open_to_close = {"(": ")", "[": "]", "{": "}"}
        while idx < len(code):
            if code[idx].isalpha() or code[idx] == "_":
                start = idx
                idx += 1
                while idx < len(code) and (
                    code[idx].isalnum() or code[idx] in {"_", ":"}
                ):
                    idx += 1
                after_ident = idx
                lookahead = idx
                while lookahead < len(code) and code[lookahead].isspace():
                    lookahead += 1
                if lookahead < len(code) and code[lookahead] == "!":
                    lookahead += 1
                    while lookahead < len(code) and code[lookahead].isspace():
                        lookahead += 1
                    if lookahead < len(code) and code[lookahead] in open_to_close:
                        opener = code[lookahead]
                        closer = open_to_close[opener]
                        depth = 1
                        idx = lookahead + 1
                        while idx < len(code) and depth > 0:
                            if code[idx] == opener:
                                depth += 1
                            elif code[idx] == closer:
                                depth -= 1
                            idx += 1
                        out.append(mask(code[start:idx]))
                        continue
                out.append(code[start:after_ident])
                continue
            out.append(code[idx])
            idx += 1
        return "".join(out)

    def raw_string_end(start: int) -> int | None:
        if start > 0 and (text[start - 1].isalnum() or text[start - 1] == "_"):
            return None
        idx = start
        if idx < len(text) and text[idx] in {"b", "c"}:
            idx += 1
        if idx >= len(text) or text[idx] != "r":
            return None
        idx += 1
        hashes_start = idx
        while idx < len(text) and text[idx] == "#":
            idx += 1
        if idx >= len(text) or text[idx] != '"':
            return None
        hashes = text[hashes_start:idx]
        end_marker = '"' + hashes
        end = text.find(end_marker, idx + 1)
        return len(text) if end == -1 else end + len(end_marker)

    def quoted_end(start: int, quote: str) -> int:
        idx = start + 1
        while idx < len(text):
            if text[idx] == "\\":
                idx += 2
                continue
            if text[idx] == quote:
                return idx + 1
            idx += 1
        return len(text)

    out: list[str] = []
    idx = 0
    while idx < len(text):
        if text.startswith("//", idx):
            end = text.find("\n", idx)
            if end == -1:
                out.append(mask(text[idx:]))
                break
            out.append(mask(text[idx:end]))
            out.append("\n")
            idx = end + 1
            continue
        if text.startswith("/*", idx):
            level = 1
            end = idx + 2
            while end < len(text) and level > 0:
                if text.startswith("/*", end):
                    level += 1
                    end += 2
                elif text.startswith("*/", end):
                    level -= 1
                    end += 2
                else:
                    end += 1
            out.append(mask(text[idx:end]))
            idx = end
            continue
        raw_end = raw_string_end(idx)
        if raw_end is not None:
            out.append(mask(text[idx:raw_end]))
            idx = raw_end
            continue
        if text[idx] in {"b", "c"} and idx + 1 < len(text) and text[idx + 1] == '"':
            end = quoted_end(idx + 1, '"')
            out.append(mask(text[idx:end]))
            idx = end
            continue
        if text[idx] == '"':
            end = quoted_end(idx, '"')
            out.append(mask(text[idx:end]))
            idx = end
            continue
        if text[idx] == "'" and idx + 2 < len(text):
            end = quoted_end(idx, "'")
            if end < len(text) and "\n" not in text[idx:end] and end - idx <= 8:
                out.append(mask(text[idx:end]))
                idx = end
                continue
        if text[idx] == "b" and idx + 2 < len(text) and text[idx + 1] == "'":
            end = quoted_end(idx + 1, "'")
            if end < len(text) and "\n" not in text[idx:end] and end - idx <= 9:
                out.append(mask(text[idx:end]))
                idx = end
                continue
        out.append(text[idx])
        idx += 1
    def mask_cfg_test_items(code: str) -> str:
        chars = list(code)
        idx = 0
        marker = "#[cfg(test)]"
        while True:
            start = code.find(marker, idx)
            if start == -1:
                break
            cursor = start + len(marker)
            while cursor < len(code):
                while cursor < len(code) and code[cursor].isspace():
                    cursor += 1
                if code.startswith("#[", cursor):
                    end_attr = code.find("]", cursor + 2)
                    if end_attr == -1:
                        break
                    cursor = end_attr + 1
                    continue
                break
            item_end = None
            brace = code.find("{", cursor)
            semi = code.find(";", cursor)
            if brace != -1 and (semi == -1 or brace < semi):
                depth = 1
                end = brace + 1
                while end < len(code) and depth > 0:
                    if code[end] == "{":
                        depth += 1
                    elif code[end] == "}":
                        depth -= 1
                    end += 1
                item_end = end
            elif semi != -1:
                item_end = semi + 1
            if item_end is None:
                idx = cursor
                continue
            masked = mask(code[start:item_end])
            chars[start:item_end] = masked
            idx = item_end
        return "".join(chars)

    return mask_cfg_test_items(mask_macro_invocations("".join(out)))


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _load_files(repo_root: Path, rel_paths: tuple[str, ...]) -> tuple[list[dict[str, Any]], list[str]]:
    loaded: list[dict[str, Any]] = []
    missing: list[str] = []
    for rel_path in rel_paths:
        path = repo_root / rel_path
        if not path.is_file():
            missing.append(rel_path)
            continue
        text = _read_file(path)
        if text is None:
            missing.append(rel_path)
            continue
        loaded.append(
            {
                "path": rel_path,
                "text": text,
                "code_text": _strip_rust_comments_and_strings(text),
            }
        )
    return loaded, missing


def _find_pattern(files: list[dict[str, Any]], pattern: str) -> dict[str, Any] | None:
    for file in files:
        for line_no, line in enumerate(str(file["code_text"]).splitlines(), start=1):
            if pattern in line:
                return {
                    "pattern": pattern,
                    "path": file["path"],
                    "line": line_no,
                    "snippet": line.strip()[:220],
                }
    return None


def _evaluate_requirement(repo_root: Path, requirement: Requirement) -> dict[str, Any]:
    files, missing_paths = _load_files(repo_root, requirement.paths)
    group_rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    missing_groups: list[list[str]] = []
    for group in requirement.pattern_groups:
        group_evidence = None
        for pattern in group:
            group_evidence = _find_pattern(files, pattern)
            if group_evidence is not None:
                break
        if group_evidence is None:
            missing_groups.append(list(group))
            group_rows.append({"patterns": list(group), "present": False})
        else:
            evidence.append(group_evidence)
            group_rows.append(
                {
                    "patterns": list(group),
                    "present": True,
                    "matched_pattern": group_evidence["pattern"],
                    "path": group_evidence["path"],
                    "line": group_evidence["line"],
                }
            )
    present = bool(files) and not missing_paths and not missing_groups
    return {
        "check_id": requirement.check_id,
        "category": requirement.category,
        "description": requirement.description,
        "present": present,
        "missing_reason": None if present else requirement.missing_reason,
        "paths": list(requirement.paths),
        "missing_paths": missing_paths,
        "pattern_groups": [list(group) for group in requirement.pattern_groups],
        "missing_pattern_groups": missing_groups,
        "group_results": group_rows,
        "evidence": evidence,
    }


def _recursive_authority_violation(payload: Any) -> str | None:
    stack: list[Any] = [payload]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if _is_dangerous_truthy_key(str(key)) and _truthy(value):
                    return key
                if key in AUTHORITY_ENUM_KEYS and not _safe_authority_enum(value):
                    return key
                if key == "main_cost_gate_adjustment" and value not in (None, "", "NONE"):
                    return key
                stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return None


def _source_contract(repo_root: Path) -> dict[str, Any]:
    rows = [_evaluate_requirement(repo_root, req) for req in SOURCE_REQUIREMENTS]
    missing = [row["missing_reason"] for row in rows if row.get("present") is not True]
    return {
        "repo_root": str(repo_root),
        "requirements": rows,
        "all_requirements_present": not missing,
        "missing_requirements": missing,
    }


def _status(
    *,
    source_contract: dict[str, Any],
    active_readiness: dict[str, Any],
    authority_violation: str | None,
) -> tuple[str, str, list[str]]:
    if authority_violation:
        return (
            BOUNDARY_VIOLATION_STATUS,
            f"input_contains_authority_or_mutation_field:{authority_violation}",
            ["remove_authority_bearing_input_before_contract_review"],
        )
    if (
        source_contract.get("all_requirements_present") is True
        and active_readiness.get("active_order_submission_ready") is True
    ):
        return (
            READY_STATUS,
            "source_contains_required_active_order_wiring_contract_for_e3_bb_review",
            [
                "run_e3_bb_exchange_facing_review_before_any_demo_order",
                "keep_probe_order_authority_false_until_reviewed_runtime_envelope",
                "run_one_order_max_demo_probe_only_after_separate_approval_path",
            ],
        )
    return (
        PATCH_REQUIRED_STATUS,
        "current_source_lacks_machine_checkable_active_bounded_demo_order_wiring",
        [
            "implement_bounded_probe_active_order_rust_module",
            "wire_candidate_matched_admitted_probe_to_existing_order_dispatch",
            "preserve_post_only_near_touch_limits_and_full_lineage",
            "rerun_source_contract_before_e3_bb_exchange_facing_review",
        ],
    )


def build_bounded_probe_active_order_wiring_contract(
    *,
    repo_root: Path,
    authority_readiness_packet: dict[str, Any] | None = None,
    candidate: dict[str, Any] | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    repo_root = repo_root.resolve()
    source_contract = _source_contract(repo_root)
    active_readiness = _active_order_submission_readiness(repo_root)
    authority_violation = _recursive_authority_violation(authority_readiness_packet or {})
    status, reason, next_actions = _status(
        source_contract=source_contract,
        active_readiness=active_readiness,
        authority_violation=authority_violation,
    )
    source_patch_required = status == PATCH_REQUIRED_STATUS
    if status == READY_STATUS:
        max_safe_next_action = "e3_bb_exchange_facing_review_packet_only_no_order"
    elif status == BOUNDARY_VIOLATION_STATUS:
        max_safe_next_action = "remove_authority_bearing_input_before_any_next_review"
    else:
        max_safe_next_action = "source_only_rust_patch_for_active_order_wiring"
    return {
        "schema_version": ACTIVE_ORDER_WIRING_CONTRACT_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "candidate": dict(candidate or {}),
        "source_contract": source_contract,
        "active_order_submission_readiness": active_readiness,
        "authority_readiness_packet": {
            "provided": isinstance(authority_readiness_packet, dict),
            "schema_version": _dict(authority_readiness_packet).get("schema_version"),
            "status": _dict(authority_readiness_packet).get("status"),
            "authority_violation": authority_violation,
        },
        "required_before_any_order": [
            "source_contract_status_ready_for_e3_bb_review",
            "fresh_e3_bb_exchange_facing_review",
            "demo_only_runtime_envelope",
            "candidate_matched_one_order_max_authorization",
            "guardian_decision_lease_rust_authority_path_preserved",
            "post_only_near_touch_or_skip_order_shape",
            "candidate_matched_order_fill_fee_slippage_lineage",
            "matched_blocked_controls_defined_for_outcome_review",
        ],
        "max_safe_next_action": max_safe_next_action,
        "next_actions": next_actions,
        "answers": {
            "source_contract_ready_for_e3_bb_review": status == READY_STATUS,
            "source_patch_required": source_patch_required,
            "active_order_submission_ready": active_readiness.get(
                "active_order_submission_ready"
            )
            is True,
            "active_runtime_probe_authority": False,
            "active_runtime_order_authority": False,
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "live_authority_granted": False,
            "runtime_mutation_performed": False,
            "pg_write_performed": False,
            "order_submission_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "promotion_evidence": False,
            "promotion_proof": False,
        },
        "aggressive_profit_path": {
            "hypothesis": "candidate_matched_post_only_near_touch_demo_probe",
            "why_it_might_make_money": (
                "It converts high-upside Cost Gate false-negative cells into "
                "maker-biased, fee-aware Demo attempts without lowering the "
                "global Cost Gate."
            ),
            "fastest_safe_test": "source-only contract, then E3/BB one-order demo envelope review",
            "failure_condition": (
                "source cannot preserve active order lineage, post-only limits, "
                "risk gates, or matched-control outcome review"
            ),
            "authority_required": "E3/BB review before any runtime/exchange-facing action",
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    source = _dict(packet.get("source_contract"))
    active = _dict(packet.get("active_order_submission_readiness"))
    candidate = _dict(packet.get("candidate"))
    lines = [
        "# Bounded Demo Probe Active Order Wiring Contract",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{candidate.get('side_cell_key')}`",
        f"- Source requirements present: `{source.get('all_requirements_present')}`",
        f"- Missing source requirements: `{source.get('missing_requirements')}`",
        f"- Active order ready: `{active.get('active_order_submission_ready')}`",
        f"- Active order blockers: `{active.get('blockers')}`",
        f"- Max safe next action: `{packet.get('max_safe_next_action')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Required Before Any Order",
        "",
    ]
    for item in _list(packet.get("required_before_any_order")):
        lines.append(f"- `{item}`")
    lines.extend(["", "## Next Actions", ""])
    for item in _list(packet.get("next_actions")):
        lines.append(f"- `{item}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} did not contain a JSON object")
    return payload


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
        + "\n",
        encoding="utf-8",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--authority-readiness-json", type=Path)
    parser.add_argument("--candidate-side-cell-key")
    parser.add_argument("--candidate-strategy-name")
    parser.add_argument("--candidate-symbol")
    parser.add_argument("--candidate-side")
    parser.add_argument("--candidate-horizon-minutes", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    candidate = {
        "side_cell_key": args.candidate_side_cell_key,
        "strategy_name": args.candidate_strategy_name,
        "symbol": args.candidate_symbol,
        "side": args.candidate_side,
        "outcome_horizon_minutes": args.candidate_horizon_minutes,
    }
    candidate = {key: value for key, value in candidate.items() if value is not None}
    packet = build_bounded_probe_active_order_wiring_contract(
        repo_root=args.repo_root,
        authority_readiness_packet=_read_json(args.authority_readiness_json),
        candidate=candidate,
    )
    markdown = render_markdown(packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    if not args.output and not args.json_output and not args.print_json:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

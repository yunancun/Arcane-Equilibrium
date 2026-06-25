#!/usr/bin/env python3
"""Build a no-authority Rust patch-readiness packet for bounded Demo probes.

This artifact consumes the no-authority placement repair plan and statically
scans the source tree for the seams needed to turn a Cost Gate-blocked signal
into a bounded, near-touch Demo learning attempt.

It does not query PG, call Bybit, submit orders, lower the Cost Gate, grant
probe/order authority, or mutate runtime state.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PATCH_READINESS_SCHEMA_VERSION = "bounded_demo_probe_authority_patch_readiness_v1"
PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION = (
    "bounded_demo_probe_placement_repair_plan_v1"
)
READY_REPAIR_STATUS = "PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW"
BOUNDARY = (
    "artifact-only bounded Demo probe source-readiness scan; no PG query/write, "
    "Bybit call, order, config, risk, auth, runtime mutation, Cost Gate lowering, "
    "probe authority, order authority, or promotion proof"
)

AUTHORITY_TRUE_KEYS = {
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "actual_runtime_admission_enablement_ready",
    "adapter_enablement_performed",
    "adapter_enabled_by_this_packet",
    "allowed_to_submit_order",
    "allowed_to_submit_order_in_current_review",
    "api_call_performed",
    "auth_mutation_performed",
    "bybit_call_performed",
    "bybit_private_call_performed",
    "bybit_public_market_data_call_performed",
    "canonical_plan_mutation_performed",
    "cost_gate_mutation_found",
    "crontab_edit_performed",
    "crontab_mutation_performed",
    "env_mutation_performed",
    "global_cost_gate_lowering_recommended",
    "ledger_append_performed",
    "live_authority_granted",
    "live_execution_allowed",
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
    "runtime_adapter_enablement_performed",
    "runtime_admission_enablement_ready",
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


@dataclass(frozen=True)
class SourceCheck:
    check_id: str
    category: str
    description: str
    required_patterns: tuple[str, ...]
    paths: tuple[str, ...]
    missing_reason: str


EXISTING_SEAM_CHECKS: tuple[SourceCheck, ...] = (
    SourceCheck(
        check_id="demo_learning_lane_admission_policy",
        category="existing_authority_seam",
        description=(
            "Rust has a pure Cost Gate demo-learning admission Module that "
            "keeps main Cost Gate lowering disallowed."
        ),
        required_patterns=(
            "evaluate_probe_admission",
            "ORDER_AUTHORITY_GRANTED",
            "main_cost_gate_adjustment",
        ),
        paths=("rust/openclaw_engine/src/demo_learning_lane.rs",),
        missing_reason="demo_learning_lane_admission_policy_missing",
    ),
    SourceCheck(
        check_id="eligible_reject_hot_path_capture",
        category="existing_authority_seam",
        description=(
            "Eligible Demo/LiveDemo Cost Gate rejects can be normalized into "
            "learning-lane RejectEvent rows."
        ),
        required_patterns=("exchange_gate_reject_event", "ELIGIBLE_REJECT_REASON_CODE"),
        paths=("rust/openclaw_engine/src/demo_learning_lane_hot_path.rs",),
        missing_reason="eligible_cost_gate_reject_hot_path_capture_missing",
    ),
    SourceCheck(
        check_id="admission_ledger_writer",
        category="existing_authority_seam",
        description=(
            "The writer can persist admission and capture-error JSONL rows "
            "without submitting orders."
        ),
        required_patterns=(
            "ADMISSION_LEDGER_RECORD_TYPE",
            "CAPTURE_ERROR_LEDGER_RECORD_TYPE",
            "build_admission_ledger_record_with_placement",
            "build_capture_error_ledger_record",
            "allowed_to_submit_order",
        ),
        paths=(
            "rust/openclaw_engine/src/demo_learning_lane_writer.rs",
            "rust/openclaw_engine/src/demo_learning_lane_ledger.rs",
        ),
        missing_reason="admission_ledger_writer_missing",
    ),
    SourceCheck(
        check_id="order_intent_limit_tif_surface",
        category="existing_authority_seam",
        description=(
            "OrderIntent already carries limit_price and TimeInForce, so a "
            "bounded Adapter can alter placement shape without inventing a new "
            "order object."
        ),
        required_patterns=("limit_price", "time_in_force", "TimeInForce::PostOnly"),
        paths=(
            "rust/openclaw_engine/src/intent_processor/mod.rs",
            "rust/openclaw_engine/src/order_manager.rs",
        ),
        missing_reason="order_intent_limit_tif_surface_missing",
    ),
    SourceCheck(
        check_id="dispatch_bbo_reference_surface",
        category="existing_authority_seam",
        description=(
            "Tick dispatch exposes best_bid/best_ask and reference price data "
            "near the exchange dispatch point."
        ),
        required_patterns=("best_bid", "best_ask", "execution_reference"),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        missing_reason="dispatch_bbo_reference_surface_missing",
    ),
    SourceCheck(
        check_id="exchange_dispatch_limit_tif_forwarding",
        category="existing_authority_seam",
        description=(
            "Exchange dispatch already forwards order_type, limit_price, and "
            "TimeInForce to the downstream order request."
        ),
        required_patterns=("OrderDispatchRequest", "limit_price: intent.limit_price", "time_in_force: intent.time_in_force"),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        missing_reason="exchange_dispatch_limit_tif_forwarding_missing",
    ),
)

PATCH_REQUIREMENT_CHECKS: tuple[SourceCheck, ...] = (
    SourceCheck(
        check_id="bounded_probe_near_touch_adapter",
        category="adapter_module_seam",
        description=(
            "A pure Rust Adapter Module should apply the placement repair plan's "
            "post_only_near_touch_or_skip rule to the selected side-cell."
        ),
        required_patterns=(
            "post_only_near_touch_or_skip",
            "BoundedProbePlacementDecision",
        ),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="near_touch_or_skip_adapter_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="fresh_bbo_age_guard",
        category="adapter_module_seam",
        description=(
            "The Adapter should fail closed when the BBO snapshot is older than "
            "max_fresh_bbo_age_ms."
        ),
        required_patterns=("max_fresh_bbo_age_ms",),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="fresh_bbo_age_guard_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="max_initial_gap_guard",
        category="adapter_module_seam",
        description=(
            "The Adapter should compute initial touch gap bps and skip when it "
            "exceeds max_initial_passive_gap_bps."
        ),
        required_patterns=("max_initial_passive_gap_bps", "touch_gap_bps"),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="initial_touch_gap_guard_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="touchability_skip_record",
        category="adapter_module_seam",
        description=(
            "Skipped near-touch attempts should be recorded as "
            "bounded_probe_touchability_block rather than silently lost."
        ),
        required_patterns=("BoundedProbeTouchabilityBlock", "record_type"),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="touchability_skip_record_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="candidate_matched_attempt_lineage",
        category="adapter_module_seam",
        description=(
            "The Adapter output should name bounded_probe_attempt rows and carry "
            "side_cell_key lineage for later fill/fee/slippage review."
        ),
        required_patterns=("BoundedProbeAttemptPlacement", "side_cell_key"),
        paths=("rust/openclaw_engine/src/bounded_probe_near_touch.rs",),
        missing_reason="candidate_matched_attempt_lineage_missing_from_rust_authority_path",
    ),
    SourceCheck(
        check_id="authority_path_wiring",
        category="authority_path_wiring_seam",
        description=(
            "The tick/exchange authority path should call the Adapter before any "
            "future bounded probe order is submitted."
        ),
        required_patterns=(
            "post_only_near_touch_from_optional_bbo_or_skip",
            "BoundedProbeOptionalBboPlacementRequest",
            "BOUNDED_PROBE_ATTEMPT_RECORD_TYPE",
        ),
        paths=("rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs",),
        missing_reason="authority_path_wiring_missing_from_tick_dispatch",
    ),
)


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


def _float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _parse_dt(value: Any) -> dt.datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def _age_seconds(value: Any, *, now_utc: dt.datetime) -> float | None:
    parsed = _parse_dt(value)
    if parsed is None:
        return None
    age = (now_utc - parsed).total_seconds()
    return age if age >= 0.0 else None


def _artifact_status(
    payload: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    present = isinstance(payload, dict) and bool(payload)
    generated_at = (
        (payload or {}).get("generated_at_utc")
        or (payload or {}).get("generated")
        or (payload or {}).get("ts_utc")
    )
    age = _age_seconds(generated_at, now_utc=now_utc) if generated_at else None
    if not present:
        status = "MISSING"
    elif age is None:
        status = "PRESENT_UNKNOWN_AGE"
    elif age > max_age_seconds:
        status = "STALE"
    else:
        status = "FRESH"
    return {
        "status": status,
        "present": present,
        "generated_at_utc": generated_at,
        "age_seconds": age,
        "max_age_seconds": max_age_seconds,
        "schema_version": (payload or {}).get("schema_version") if present else None,
    }


def _authority_preserved(placement_repair_plan: dict[str, Any] | None) -> bool:
    return _recursive_authority_violation(_dict(placement_repair_plan)) is None


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


def _placement_plan_summary(
    placement_repair_plan: dict[str, Any] | None,
    *,
    now_utc: dt.datetime,
    max_age_seconds: int,
) -> dict[str, Any]:
    payload = _dict(placement_repair_plan)
    plan = _dict(payload.get("placement_repair_plan"))
    candidate = _dict(plan.get("candidate")) or _dict(payload.get("candidate"))
    artifact = _artifact_status(
        payload or None,
        now_utc=now_utc,
        max_age_seconds=max_age_seconds,
    )
    authority_preserved = _authority_preserved(payload)
    ready = (
        artifact.get("status") == "FRESH"
        and artifact.get("schema_version") == PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
        and payload.get("status") == READY_REPAIR_STATUS
        and plan.get("order_mode") == "post_only_near_touch_or_skip"
        and authority_preserved
    )
    return {
        "artifact": artifact,
        "status": payload.get("status"),
        "reason": payload.get("reason"),
        "ready_for_source_patch_review": ready,
        "authority_preserved": authority_preserved,
        "candidate": {
            "side_cell_key": candidate.get("side_cell_key"),
            "strategy_name": candidate.get("strategy_name"),
            "symbol": candidate.get("symbol"),
            "side": candidate.get("side"),
            "outcome_horizon_minutes": candidate.get("outcome_horizon_minutes"),
        },
        "order_mode": plan.get("order_mode"),
        "max_fresh_bbo_age_ms": plan.get("max_fresh_bbo_age_ms"),
        "max_initial_passive_gap_bps": _float(
            plan.get("max_initial_passive_gap_bps")
        ),
        "max_demo_notional_usdt_per_order": _dict(plan.get("probe_limits")).get(
            "max_demo_notional_usdt_per_order"
        ),
        "max_probe_intents_before_review": _dict(plan.get("probe_limits")).get(
            "max_probe_intents_before_review"
        ),
        "skip_record_type": _dict(plan.get("skip_record")).get("record_type"),
        "post_order_evidence": _list(plan.get("post_order_evidence")),
    }


def _iter_files(repo_root: Path, path_text: str) -> list[Path]:
    path = repo_root / path_text
    if path.is_file():
        return [path]
    if path.is_dir():
        return [
            item
            for item in sorted(path.rglob("*.rs"))
            if ".git" not in item.parts and item.is_file()
        ]
    return []


def _read_file(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _read_repo_text(repo_root: Path, rel_path: str) -> str:
    path = repo_root / rel_path
    return _read_file(path) or ""


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


def _repo_file_present(repo_root: Path, rel_path: str) -> bool:
    return (repo_root / rel_path).is_file()


def _find_pattern_evidence(
    files: list[tuple[str, str]], patterns: tuple[str, ...]
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for pattern in patterns:
        matched = False
        for rel_path, text in files:
            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern in line:
                    evidence.append(
                        {
                            "pattern": pattern,
                            "path": rel_path,
                            "line": idx,
                            "snippet": line.strip()[:220],
                        }
                    )
                    matched = True
                    break
            if matched:
                break
    return evidence


def _source_check_requires_code_scan(check: SourceCheck) -> bool:
    return check.category in {
        "adapter_module_seam",
        "authority_path_wiring_seam",
        "existing_authority_seam",
    }


def _evaluate_source_check(repo_root: Path, check: SourceCheck) -> dict[str, Any]:
    loaded_files: list[tuple[str, str]] = []
    missing_paths: list[str] = []
    code_scan = _source_check_requires_code_scan(check)
    for rel in check.paths:
        files = _iter_files(repo_root, rel)
        if not files:
            missing_paths.append(rel)
            continue
        for path in files:
            text = _read_file(path)
            if text is not None:
                scan_text = _strip_rust_comments_and_strings(text) if code_scan else text
                loaded_files.append((path.relative_to(repo_root).as_posix(), scan_text))
    text_by_pattern = {
        pattern: any(pattern in text for _, text in loaded_files)
        for pattern in check.required_patterns
    }
    present = bool(loaded_files) and all(text_by_pattern.values())
    return {
        "check_id": check.check_id,
        "category": check.category,
        "description": check.description,
        "present": present,
        "missing_reason": None if present else check.missing_reason,
        "paths": list(check.paths),
        "loaded_file_count": len(loaded_files),
        "missing_paths": missing_paths,
        "required_patterns": list(check.required_patterns),
        "missing_patterns": [
            pattern for pattern, found in text_by_pattern.items() if not found
        ],
        "scan_mode": "code_without_comments_or_strings" if code_scan else "raw_text",
        "evidence": _find_pattern_evidence(loaded_files, check.required_patterns),
    }


def _check_present(rows: list[dict[str, Any]], check_id: str) -> bool:
    return any(
        row.get("check_id") == check_id and row.get("present") is True
        for row in rows
    )


def _source_readiness(repo_root: Path) -> dict[str, Any]:
    existing = [
        _evaluate_source_check(repo_root, check) for check in EXISTING_SEAM_CHECKS
    ]
    required = [
        _evaluate_source_check(repo_root, check) for check in PATCH_REQUIREMENT_CHECKS
    ]
    missing_existing = [
        row["missing_reason"] for row in existing if row.get("present") is not True
    ]
    missing_required = [
        row["missing_reason"] for row in required if row.get("present") is not True
    ]
    return {
        "repo_root": str(repo_root),
        "existing_authority_seams": existing,
        "required_patch_seams": required,
        "existing_authority_seams_present": not missing_existing,
        "required_patch_seams_present": not missing_required,
        "adapter_module_present": _check_present(
            required,
            "bounded_probe_near_touch_adapter",
        ),
        "authority_path_wiring_present": _check_present(
            required,
            "authority_path_wiring",
        ),
        "missing_existing_seams": missing_existing,
        "missing_required_patch_seams": missing_required,
    }


def _active_order_submission_readiness(repo_root: Path) -> dict[str, Any]:
    writer_rel = "rust/openclaw_engine/src/demo_learning_lane_writer.rs"
    dispatch_rel = "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs"
    near_touch_rel = "rust/openclaw_engine/src/bounded_probe_near_touch.rs"
    writer_text = _read_repo_text(
        repo_root,
        writer_rel,
    )
    dispatch_text = _read_repo_text(
        repo_root,
        dispatch_rel,
    )
    near_touch_text = _read_repo_text(
        repo_root,
        near_touch_rel,
    )
    writer_code = _strip_rust_comments_and_strings(writer_text)
    dispatch_code = _strip_rust_comments_and_strings(dispatch_text)
    file_presence = {
        writer_rel: _repo_file_present(repo_root, writer_rel),
        dispatch_rel: _repo_file_present(repo_root, dispatch_rel),
        near_touch_rel: _repo_file_present(repo_root, near_touch_rel),
    }
    writer_no_order_contract = "does not submit orders" in writer_text
    dispatch_no_order_contract = "no order submitted" in dispatch_text
    near_touch_pure_no_order_contract = "submit\n//! orders" in near_touch_text or (
        "does not read plans, write ledgers, call Bybit, submit" in near_touch_text
    )
    adapter_enabled_hardcoded_false = re.search(
        r"evaluate_probe_admission\([\s\S]*?,\s*false\s*,\s*risk_state\s*,?\s*\)",
        writer_code,
    ) is not None
    runtime_writer_default_adapter_disabled = re.search(
        r"\blet\s+bounded_probe_adapter_enabled\s*=\s*false\s*;",
        writer_code,
    ) is not None
    positive_active_evidence = {
        "writer_submits_candidate_matched_probe_order": (
            "submit_candidate_matched_bounded_probe_order" in writer_code
            or "active_bounded_probe_order_submission" in writer_code
        ),
        "dispatch_forwards_admitted_bounded_probe_to_exchange": (
            "dispatch_admitted_bounded_probe_order" in dispatch_code
            or "active_bounded_probe_order_submission" in dispatch_code
        ),
        "adapter_enabled_by_runtime_bounded_probe_gate": (
            "bounded_probe_adapter_enabled" in writer_code
            or "OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED" in writer_code
        ),
    }
    blockers: list[str] = []
    for rel_path, present in file_presence.items():
        if not present:
            blockers.append(f"source_file_missing:{rel_path}")
    if writer_no_order_contract:
        blockers.append("demo_learning_lane_writer_contract_no_order_submission")
    if adapter_enabled_hardcoded_false:
        blockers.append("demo_learning_lane_writer_adapter_enabled_false")
    if dispatch_no_order_contract:
        blockers.append("tick_dispatch_records_preview_no_order_submitted")
    if near_touch_pure_no_order_contract:
        blockers.append("near_touch_adapter_contract_pure_no_order_math")
    missing_positive_evidence = [
        key for key, present in positive_active_evidence.items() if present is not True
    ]
    if missing_positive_evidence:
        blockers.append("positive_active_order_submission_evidence_missing")
    active_ready = (
        all(file_presence.values())
        and not missing_positive_evidence
        and not blockers
    )
    return {
        "status": (
            "ACTIVE_ORDER_SUBMISSION_WIRING_PRESENT"
            if active_ready
            else "ACTIVE_ORDER_SUBMISSION_WIRING_MISSING"
        ),
        "active_order_submission_ready": active_ready,
        "blockers": blockers,
        "evidence": {
            "file_presence": file_presence,
            "writer_no_order_contract": writer_no_order_contract,
            "adapter_enabled_hardcoded_false": adapter_enabled_hardcoded_false,
            "runtime_writer_default_adapter_disabled": runtime_writer_default_adapter_disabled,
            "dispatch_no_order_contract": dispatch_no_order_contract,
            "near_touch_pure_no_order_contract": near_touch_pure_no_order_contract,
            "positive_active_evidence": positive_active_evidence,
            "missing_positive_active_evidence": missing_positive_evidence,
        },
        "required_before_order": [
            "separate_source_patch_to_enable_active_bounded_demo_order_submission",
            "candidate_matched_attempt_fill_fee_slippage_lineage",
            "fresh_e3_bb_exchange_facing_order_envelope_review",
            "guardian_decision_lease_rust_authority_path_preserved",
        ],
        "boundary": "source scan only; this packet never grants active order authority",
    }


def _call_evidence(code: str, rel_path: str, symbol: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    call_re = re.compile(rf"\b{re.escape(symbol)}\s*\(")
    definition_re = re.compile(rf"\bfn\s+{re.escape(symbol)}\s*\(")
    for idx, line in enumerate(code.splitlines(), start=1):
        if not call_re.search(line):
            continue
        if definition_re.search(line):
            continue
        evidence.append(
            {
                "path": rel_path,
                "line": idx,
                "symbol": symbol,
            }
        )
    return evidence


def _function_body(code: str, fn_name: str) -> str:
    match = re.search(rf"\bfn\s+{re.escape(fn_name)}\s*\(", code)
    if match is None:
        return ""
    brace = code.find("{", match.end())
    if brace == -1:
        return ""
    depth = 1
    idx = brace + 1
    while idx < len(code) and depth > 0:
        if code[idx] == "{":
            depth += 1
        elif code[idx] == "}":
            depth -= 1
        idx += 1
    return code[brace:idx] if depth == 0 else code[brace:]


def _runtime_adapter_gate_feeds_admission(runtime_body: str) -> bool:
    if not runtime_body:
        return False
    assignment = re.search(
        r"\blet\s+bounded_probe_adapter_enabled(?:\s*:\s*[^=;]+)?\s*=\s*(?P<rhs>[^;]+);",
        runtime_body,
        flags=re.S,
    )
    if assignment is None:
        return False
    rhs = " ".join(assignment.group("rhs").split())
    if (
        re.match(
            r"^std::env::var\s*\(\s*OPENCLAW_BOUNDED_PROBE_ADAPTER_ENABLED\s*\)"
            r"(?:\s*\.[A-Za-z_][A-Za-z0-9_]*\s*\([^{};]*\))*$",
            rhs,
        )
        is None
    ):
        return False
    return (
        re.search(
            r"\bevaluate_probe_admission\s*\([^;]*\bbounded_probe_adapter_enabled\b[^;]*\)",
            runtime_body,
            flags=re.S,
        )
        is not None
    )


def _active_caller_enablement_review(
    repo_root: Path,
    active_order_summary: dict[str, Any],
) -> dict[str, Any]:
    writer_rel = "rust/openclaw_engine/src/demo_learning_lane_writer.rs"
    dispatch_rel = "rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs"
    writer_code = _strip_rust_comments_and_strings(
        _read_repo_text(repo_root, writer_rel)
    )
    dispatch_code = _strip_rust_comments_and_strings(
        _read_repo_text(repo_root, dispatch_rel)
    )
    runtime_body = _function_body(writer_code, "build_runtime_admission_record")
    writer_call_sites = (
        _call_evidence(
            runtime_body,
            writer_rel,
            "submit_candidate_matched_bounded_probe_order",
        )
        + _call_evidence(
            runtime_body,
            writer_rel,
            "active_bounded_probe_order_submission",
        )
    )
    dispatch_call_sites = _call_evidence(
        dispatch_code,
        dispatch_rel,
        "active_bounded_probe_order_submission",
    )
    production_active_caller_present = bool(writer_call_sites)
    runtime_adapter_enablement_gate_present = _runtime_adapter_gate_feeds_admission(
        runtime_body
    )
    runtime_writer_default_adapter_disabled = bool(
        _dict(active_order_summary.get("evidence")).get(
            "runtime_writer_default_adapter_disabled"
        )
    )
    source_blockers: list[str] = []
    if active_order_summary.get("active_order_submission_ready") is not True:
        source_blockers.append("active_order_submission_source_seam_not_ready")
    if runtime_writer_default_adapter_disabled:
        source_blockers.append("runtime_writer_default_adapter_disabled")
    if not production_active_caller_present:
        source_blockers.append("production_active_bounded_probe_caller_missing")
    if not runtime_adapter_enablement_gate_present:
        source_blockers.append("reviewed_runtime_adapter_enablement_gate_missing")
    source_ready = (
        active_order_summary.get("active_order_submission_ready") is True
        and production_active_caller_present
        and runtime_adapter_enablement_gate_present
        and not runtime_writer_default_adapter_disabled
        and not source_blockers
    )
    enablement_blockers = [
        "runtime_source_sync_not_verified",
        "post_restart_pending_order_reconciliation_not_proven",
        "runtime_adapter_enablement_not_performed_source_only_packet",
    ]
    if not source_ready:
        enablement_blockers.insert(0, "active_caller_source_review_not_ready")
    actual_ready = False
    blockers = source_blockers + enablement_blockers
    return {
        "status": (
            "ACTIVE_CALLER_SOURCE_READY_FOR_E3_BB_REVIEW"
            if source_ready
            else "ACTIVE_CALLER_ENABLEMENT_BLOCKED_SOURCE_ONLY"
        ),
        "active_caller_source_ready_for_review": source_ready,
        "actual_active_caller_enablement_ready": actual_ready,
        "active_caller_enablement_authority_granted": False,
        "blockers": blockers,
        "evidence": {
            "source_seam_ready": active_order_summary.get(
                "active_order_submission_ready"
            )
            is True,
            "runtime_writer_default_adapter_disabled": runtime_writer_default_adapter_disabled,
            "runtime_adapter_enablement_gate_present": runtime_adapter_enablement_gate_present,
            "production_active_caller_present": production_active_caller_present,
            "writer_call_sites": writer_call_sites,
            "tick_dispatch_call_sites": dispatch_call_sites,
            "runtime_gate_feeds_admission_scan": runtime_adapter_enablement_gate_present,
            "runtime_source_sync_verified": False,
            "post_restart_pending_order_reconciliation_proven": False,
        },
        "required_before_enablement": [
            "source_reviewed_production_active_caller",
            "reviewed_runtime_adapter_enablement_gate",
            "fresh_e3_bb_exchange_facing_order_envelope_review",
            "runtime_source_sync_and_readiness_probe",
            "post_restart_pending_order_reconciliation_review",
            "candidate_matched_result_and_execution_realism_review_after_probe",
        ],
        "boundary": (
            "source-only caller enablement review; this packet never enables the "
            "runtime adapter and never grants probe/order authority"
        ),
    }


def _runtime_admission_propagation_review(
    active_order_summary: dict[str, Any],
    active_caller_summary: dict[str, Any],
) -> dict[str, Any]:
    active_order_submission_ready = (
        active_order_summary.get("active_order_submission_ready") is True
    )
    active_caller_source_ready = (
        active_caller_summary.get("active_caller_source_ready_for_review") is True
    )
    review_ready = active_order_submission_ready and active_caller_source_ready
    runtime_source_sync_verified = False
    post_restart_pending_order_reconciliation_proven = False
    adapter_enablement_performed = False

    blockers: list[str] = []
    if not active_order_submission_ready:
        blockers.append("active_order_submission_source_seam_not_ready")
    if not active_caller_source_ready:
        blockers.append("active_caller_source_review_not_ready")
    if not runtime_source_sync_verified:
        blockers.append("runtime_source_sync_not_verified")
    if not post_restart_pending_order_reconciliation_proven:
        blockers.append("post_restart_pending_order_reconciliation_not_proven")
    if not adapter_enablement_performed:
        blockers.append("runtime_adapter_enablement_not_performed_source_only_packet")

    no_authority = {
        "actual_runtime_admission_enablement_ready": False,
        "runtime_source_sync_verified": runtime_source_sync_verified,
        "post_restart_pending_order_reconciliation_proven": (
            post_restart_pending_order_reconciliation_proven
        ),
        "runtime_adapter_enablement_performed": adapter_enablement_performed,
        "adapter_enablement_performed": adapter_enablement_performed,
        "adapter_enabled_by_this_packet": False,
        "allowed_to_submit_order": False,
        "allowed_to_submit_order_in_current_review": False,
        "active_order_submission_ready_is_order_authority": False,
        "active_caller_source_ready_for_review_is_order_authority": False,
        "active_runtime_order_authority": False,
        "active_runtime_probe_authority": False,
        "exchange_facing_order_authority_granted": False,
        "probe_authority_granted": False,
        "order_authority_granted": False,
        "runtime_order_authority_found": False,
        "runtime_probe_authority_found": False,
        "api_call_performed": False,
        "bybit_call_performed": False,
        "bybit_private_call_performed": False,
        "bybit_public_market_data_call_performed": False,
        "order_submission_performed": False,
        "order_cancel_modify_performed": False,
        "ledger_append_performed": False,
        "canonical_plan_mutation_performed": False,
        "plan_mutation_performed": False,
        "pg_write_performed": False,
        "pg_query_performed": False,
        "risk_mutation_performed": False,
        "auth_mutation_performed": False,
        "runtime_mutation_performed": False,
        "runtime_env_mutation_performed": False,
        "runtime_config_mutation_performed": False,
        "service_restart_performed": False,
        "service_mutation_performed": False,
        "crontab_edit_performed": False,
        "crontab_mutation_performed": False,
        "rust_writer_enabled": False,
        "writer_enablement_performed": False,
        "writer_enabled": False,
        "live_authority_granted": False,
        "live_execution_allowed": False,
        "global_cost_gate_lowering_recommended": False,
        "main_cost_gate_adjustment": "NONE",
        "promotion_evidence": False,
        "promotion_proof": False,
    }
    return {
        "status": (
            "RUNTIME_ADMISSION_PROPAGATION_SOURCE_READY_FOR_E3_BB_REVIEW_NO_RUNTIME_AUTHORITY"
            if review_ready
            else "RUNTIME_ADMISSION_PROPAGATION_BLOCKED_SOURCE_ONLY_NO_RUNTIME_AUTHORITY"
        ),
        "runtime_admission_propagation_ready_for_e3_bb_review": review_ready,
        "source_ready_sufficient_for_e3_bb_enablement_review": review_ready,
        "blockers": blockers,
        "evidence": {
            "active_order_submission_ready": active_order_submission_ready,
            "active_caller_source_ready_for_review": active_caller_source_ready,
            **no_authority,
        },
        "answers": {
            "runtime_admission_propagation_ready_for_e3_bb_review": review_ready,
            "source_ready_sufficient_for_e3_bb_enablement_review": review_ready,
            **no_authority,
        },
        "required_before_runtime_enablement": [
            "PM_E3_BB_runtime_source_admission_propagation_review_before_any_runtime_enablement",
            "runtime_source_sync_and_clean_head_verification",
            "post_restart_pending_order_reconciliation_review",
            "reviewed_runtime_adapter_enablement_gate",
            "fresh_candidate_scoped_authorization_and_admission",
            "separate_exchange_facing_order_envelope_review_before_any_demo_order",
        ],
        "max_safe_next_action": (
            "PM_E3_BB_runtime_source_admission_propagation_review_only"
        ),
        "boundary": (
            "source-only runtime/admission propagation review; source readiness "
            "is not adapter enablement, probe authority, order authority, or "
            "runtime/exchange authorization"
        ),
    }


def _profitability_improvement_lanes(
    placement_summary: dict[str, Any], source_summary: dict[str, Any]
) -> list[dict[str, Any]]:
    candidate = _dict(placement_summary.get("candidate"))
    return [
        {
            "lane": "execution_realism_first",
            "objective": (
                "convert selected Cost Gate-blocked side-cell signals into "
                "touchable maker Demo attempts before changing Cost Gate thresholds"
            ),
            "why_it_can_improve_profitability": (
                "Current evidence shows orders but no fills; without touchable "
                "attempts the system cannot learn fee, slippage, queue, or edge capture."
            ),
            "next_engineering_module": "bounded_demo_probe_near_touch_authority_adapter",
            "current_candidate": candidate.get("side_cell_key"),
            "machine_gate": "candidate_matched_fill_fee_slippage_lineage_recorded",
        },
        {
            "lane": "edge_amplification_by_side_cell_horizon",
            "objective": (
                "specialize probes to ranked strategy/symbol/side/horizon cells "
                "instead of lowering the global Cost Gate"
            ),
            "why_it_can_improve_profitability": (
                "It concentrates risk budget on blocked cells with observed net-cost "
                "cushion and avoids spending Demo budget on robust negative cells."
            ),
            "next_engineering_module": "multi_horizon_blocked_signal_control_loop",
            "current_candidate": candidate.get("side_cell_key"),
            "machine_gate": "matched_blocked_controls_positive_and_independent",
        },
        {
            "lane": "autonomous_learning_feedback",
            "objective": (
                "feed bounded probe results back into result-review and "
                "execution-realism review before any parameter or Cost Gate change"
            ),
            "why_it_can_improve_profitability": (
                "It separates alpha existence from realized edge capture, preventing "
                "positive-looking signals from being promoted when execution loses the edge."
            ),
            "next_engineering_module": "bounded_probe_result_and_execution_realism_review",
            "current_gap": source_summary.get("missing_required_patch_seams"),
            "machine_gate": "probe_edge_capture_ratio_and_matched_control_pass",
        },
    ]


def _status(
    *,
    placement_summary: dict[str, Any],
    source_summary: dict[str, Any],
) -> tuple[str, str, list[str]]:
    artifact_status = _dict(placement_summary.get("artifact")).get("status")
    if placement_summary.get("authority_preserved") is not True:
        return (
            "AUTHORITY_BOUNDARY_VIOLATION",
            "placement_repair_plan_contains_authority_granting_fields",
            ["remove_authority_granting_input_before_source_patch_review"],
        )
    if artifact_status != "FRESH":
        return (
            "PLACEMENT_REPAIR_PLAN_REQUIRED",
            "fresh_bounded_demo_probe_placement_repair_plan_v1_required",
            ["refresh_bounded_probe_placement_repair_plan_before_source_readiness"],
        )
    if (
        _dict(placement_summary.get("artifact")).get("schema_version")
        != PLACEMENT_REPAIR_PLAN_SCHEMA_VERSION
        or placement_summary.get("status") != READY_REPAIR_STATUS
        or placement_summary.get("ready_for_source_patch_review") is not True
    ):
        return (
            "PLACEMENT_REPAIR_PLAN_NOT_READY",
            "placement_repair_plan_is_not_ready_for_operator_source_patch_review",
            ["resolve_placement_repair_plan_status_before_rust_patch"],
        )
    if source_summary.get("existing_authority_seams_present") is not True:
        return (
            "SOURCE_SCAN_INCOMPLETE",
            "required_existing_authority_seams_missing_or_unreadable",
            ["repair_source_scan_or_existing_seam_before_rust_patch"],
        )
    if source_summary.get("adapter_module_present") is not True:
        return (
            "RUST_PATCH_REQUIRED_NEAR_TOUCH_PLACEMENT_ADAPTER_MISSING",
            "existing_source_lacks_required_near_touch_or_skip_authority_adapter",
            [
                "operator_review_existing_rust_authority_path_patch",
                "implement_bounded_demo_probe_near_touch_or_skip_adapter",
                "record_skip_and_candidate_matched_attempt_lineage_before_any_order",
            ],
        )
    if source_summary.get("authority_path_wiring_present") is not True:
        return (
            "RUST_PATCH_REQUIRED_AUTHORITY_PATH_WIRING_MISSING",
            "near_touch_adapter_exists_but_tick_dispatch_authority_path_is_not_wired",
            [
                "operator_review_tick_dispatch_authority_path_patch",
                "wire_bounded_demo_probe_adapter_before_any_probe_order_submission",
                "record_skip_and_candidate_matched_attempt_lineage_before_any_order",
            ],
        )
    if source_summary.get("required_patch_seams_present") is not True:
        return (
            "RUST_PATCH_REQUIRED_REQUIRED_SEAMS_MISSING",
            "adapter_and_dispatch_wiring_exist_but_required_guard_or_lineage_seams_are_missing",
            [
                "complete_required_bounded_probe_guard_and_lineage_seams",
                "rerun_source_readiness_before_any_authority_review",
                "record_skip_and_candidate_matched_attempt_lineage_before_any_order",
            ],
        )
    return (
        "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
        "source_contains_required_near_touch_authority_adapter_and_evidence_hooks",
        [
            "PM_E3_BB_runtime_source_admission_propagation_review_before_any_runtime_enablement",
            "separate_runtime_source_sync_and_post_restart_reconciliation_before_any_adapter_enablement",
            "separate_exchange_facing_order_envelope_review_before_any_demo_order",
        ],
    )


def build_bounded_demo_probe_authority_patch_readiness(
    *,
    placement_repair_plan: dict[str, Any] | None,
    repo_root: Path,
    now_utc: dt.datetime | None = None,
    max_artifact_age_hours: int = 24,
) -> dict[str, Any]:
    if max_artifact_age_hours < 1 or max_artifact_age_hours > 24 * 14:
        raise ValueError("max_artifact_age_hours must be in [1, 336]")

    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    repo_root = repo_root.resolve()
    placement_summary = _placement_plan_summary(
        placement_repair_plan,
        now_utc=now,
        max_age_seconds=max_artifact_age_hours * 3600,
    )
    source_summary = _source_readiness(repo_root)
    active_order_summary = _active_order_submission_readiness(repo_root)
    active_caller_summary = _active_caller_enablement_review(
        repo_root,
        active_order_summary,
    )
    runtime_propagation_summary = _runtime_admission_propagation_review(
        active_order_summary,
        active_caller_summary,
    )
    status, reason, next_actions = _status(
        placement_summary=placement_summary,
        source_summary=source_summary,
    )
    lanes = _profitability_improvement_lanes(placement_summary, source_summary)
    return {
        "schema_version": PATCH_READINESS_SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "placement_repair_plan": placement_summary,
        "source_readiness": source_summary,
        "active_order_submission_readiness": active_order_summary,
        "active_caller_enablement_review": active_caller_summary,
        "runtime_admission_propagation_review": runtime_propagation_summary,
        "profitability_improvement_lanes": lanes,
        "answers": {
            "placement_repair_plan_ready": placement_summary.get(
                "ready_for_source_patch_review"
            )
            is True,
            "source_scan_complete": source_summary.get(
                "existing_authority_seams_present"
            )
            is True,
            "existing_authority_seams_present": source_summary.get(
                "existing_authority_seams_present"
            )
            is True,
            "rust_near_touch_authority_adapter_present": source_summary.get(
                "adapter_module_present"
            )
            is True,
            "rust_authority_path_wiring_present": source_summary.get(
                "authority_path_wiring_present"
            )
            is True,
            "rust_active_order_submission_wiring_present": active_order_summary.get(
                "active_order_submission_ready"
            )
            is True,
            "active_order_submission_ready": active_order_summary.get(
                "active_order_submission_ready"
            )
            is True,
            "active_order_submission_authority_granted": False,
            "active_caller_enablement_ready": active_caller_summary.get(
                "actual_active_caller_enablement_ready"
            )
            is True,
            "active_caller_source_ready_for_review": active_caller_summary.get(
                "active_caller_source_ready_for_review"
            )
            is True,
            "active_caller_enablement_authority_granted": False,
            **_dict(runtime_propagation_summary.get("answers")),
            "runtime_admission_propagation_ready_for_e3_bb_review": runtime_propagation_summary.get(
                "runtime_admission_propagation_ready_for_e3_bb_review"
            )
            is True,
            "source_ready_sufficient_for_e3_bb_enablement_review": runtime_propagation_summary.get(
                "source_ready_sufficient_for_e3_bb_enablement_review"
            )
            is True,
            "actual_runtime_admission_enablement_ready": False,
            "runtime_source_sync_verified": False,
            "post_restart_pending_order_reconciliation_proven": False,
            "runtime_adapter_enablement_performed": False,
            "adapter_enablement_performed": False,
            "adapter_enabled_by_this_packet": False,
            "allowed_to_submit_order": False,
            "allowed_to_submit_order_in_current_review": False,
            "active_order_submission_ready_is_order_authority": False,
            "active_caller_source_ready_for_review_is_order_authority": False,
            "active_runtime_order_authority": False,
            "active_runtime_probe_authority": False,
            "exchange_facing_order_authority_granted": False,
            "bybit_call_performed": False,
            "bybit_private_call_performed": False,
            "bybit_public_market_data_call_performed": False,
            "order_submission_performed": False,
            "order_cancel_modify_performed": False,
            "pg_write_performed": False,
            "rust_writer_enabled": False,
            "writer_enablement_performed": False,
            "live_authority_granted": False,
            "live_execution_allowed": False,
            "rust_patch_required": status.startswith("RUST_PATCH_REQUIRED_"),
            "runtime_mutation_performed": False,
            "runtime_env_mutation_performed": False,
            "runtime_config_mutation_performed": False,
            "service_restart_performed": False,
            "crontab_edit_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    placement = _dict(packet.get("placement_repair_plan"))
    source = _dict(packet.get("source_readiness"))
    active_order = _dict(packet.get("active_order_submission_readiness"))
    active_caller = _dict(packet.get("active_caller_enablement_review"))
    runtime_propagation = _dict(packet.get("runtime_admission_propagation_review"))
    lines = [
        "# Bounded Demo Probe Authority Patch Readiness",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: {packet.get('reason')}",
        f"- Candidate: `{_dict(placement.get('candidate')).get('side_cell_key')}`",
        f"- Order mode: `{placement.get('order_mode')}`",
        f"- Existing authority seams present: `{source.get('existing_authority_seams_present')}`",
        f"- Required patch seams present: `{source.get('required_patch_seams_present')}`",
        f"- Near-touch Adapter present: `{source.get('adapter_module_present')}`",
        f"- Authority path wiring present: `{source.get('authority_path_wiring_present')}`",
        f"- Active order submission ready: `{active_order.get('active_order_submission_ready')}`",
        f"- Active order submission blockers: `{active_order.get('blockers')}`",
        f"- Active caller source ready for review: `{active_caller.get('active_caller_source_ready_for_review')}`",
        f"- Actual active caller enablement ready: `{active_caller.get('actual_active_caller_enablement_ready')}`",
        f"- Active caller enablement blockers: `{active_caller.get('blockers')}`",
        f"- Runtime/admission propagation review status: `{runtime_propagation.get('status')}`",
        f"- Runtime/admission propagation ready for E3/BB review: `{runtime_propagation.get('runtime_admission_propagation_ready_for_e3_bb_review')}`",
        f"- Actual runtime admission enablement ready: `{_dict(runtime_propagation.get('answers')).get('actual_runtime_admission_enablement_ready')}`",
        f"- Runtime/admission propagation blockers: `{runtime_propagation.get('blockers')}`",
        f"- Missing patch seams: `{source.get('missing_required_patch_seams')}`",
        f"- Boundary: {packet.get('boundary')}",
        "",
        "## Profitability Lanes",
        "",
    ]
    for lane in _list(packet.get("profitability_improvement_lanes")):
        lines.append(f"- `{lane.get('lane')}`: {lane.get('objective')}")
    lines.extend(["", "## Next Actions", ""])
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    return "\n".join(lines) + "\n"


def _read_json(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    if not path.exists():
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
    parser.add_argument("--placement-repair-plan-json", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--max-artifact-age-hours", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    packet = build_bounded_demo_probe_authority_patch_readiness(
        placement_repair_plan=_read_json(args.placement_repair_plan_json),
        repo_root=args.repo_root,
        max_artifact_age_hours=args.max_artifact_age_hours,
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

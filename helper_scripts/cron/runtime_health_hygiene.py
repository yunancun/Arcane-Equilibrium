#!/usr/bin/env python3
"""Build a source-only runtime health hygiene packet.

This packet reconciles two runtime hygiene surfaces without touching runtime:

1. installed demo-learning cron expected-head pins, and
2. Trading API process reachability versus service ownership.

It reads supplied text/JSON snapshots only. It does not call systemctl, inspect
processes, query PG, call Bybit, mutate crontab, restart services, deploy, or
grant trading/probe authority.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import shlex
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "runtime_health_hygiene_packet_v1"
BOUNDARY = (
    "source-only runtime health hygiene packet from supplied snapshots; no "
    "systemctl/ps/curl/PG/Bybit call, no crontab edit, no service restart, no "
    "deploy, no runtime mutation, no Cost Gate lowering, no probe/order/live "
    "authority, and no promotion proof"
)

STACK_CRON_MARKERS = {
    "demo_learning_evidence": "demo_learning_evidence_audit_cron.sh",
    "sealed_horizon_probe_preflight": "sealed_horizon_probe_preflight_cron.sh",
    "cost_gate_learning_lane": "cost_gate_learning_lane_cron.sh",
    "demo_learning_stack_healthcheck": "demo_learning_stack_healthcheck_cron.sh",
}
EXPECTED_HEAD_VARS_BY_COMPONENT = {
    "demo_learning_evidence": (
        "OPENCLAW_DEMO_LEARNING_EVIDENCE_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
    "sealed_horizon_probe_preflight": (
        "OPENCLAW_SEALED_HORIZON_PREFLIGHT_EXPECTED_HEAD",
        "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
    "cost_gate_learning_lane": (
        "OPENCLAW_COST_GATE_LEARNING_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
    "demo_learning_stack_healthcheck": (
        "OPENCLAW_DEMO_LEARNING_STACK_HEALTHCHECK_EXPECTED_HEAD",
        "OPENCLAW_DEMO_LEARNING_STACK_EXPECTED_HEAD",
        "OPENCLAW_EXPECTED_SOURCE_HEAD",
    ),
}
MM_CURRENT_FEE_REQUIRED_FIELDS = (
    "summary.candidate_observed_independent_windows",
    "summary.repeat_window_design_status",
    "summary.repeat_window_consistency_status",
    "summary.same_candidate_independent_windows_remaining",
    "repeat_window_design.max_safe_next_action",
)
FRICTION_SCORECARD_NAME = "false_negative_candidate_friction_scorecard_latest"
MM_CONFIRMATION_NAME = "mm_current_fee_confirmation_latest"
TRUTHY = {"1", "true", "yes", "on", "active", "running", "reachable", "ok"}
FALSEY = {"0", "false", "no", "off", "inactive", "dead", "failed", "unreachable"}
GIT_SHA_HEX = set("0123456789abcdefABCDEF")
MIN_GIT_SHA_LEN = 7
MAX_GIT_SHA_LEN = 40
AUTHORITY_TRUE_KEYS = {
    "active_runtime_authority",
    "active_runtime_order_authority",
    "active_runtime_probe_authority",
    "bounded_probe_authorized",
    "bounded_probe_operator_authorization_bounded_demo_probe_authorized",
    "bounded_probe_operator_authorization_object_emitted",
    "bounded_probe_operator_authorization_order_authority_granted_in_authorization_object",
    "bounded_probe_operator_authorization_probe_authority_granted_in_authorization_object",
    "bounded_probe_operator_authorization_writer_enabled",
    "bounded_demo_probe_authorized",
    "bybit_call_performed",
    "crontab_mutation_performed",
    "crontab_mutated",
    "demo_learning_stack_activation_packet_runtime_writer_enabled",
    "false_negative_candidate_friction_scorecard_bounded_demo_probe_authorized",
    "false_negative_candidate_friction_scorecard_operator_authorization_object_emitted",
    "global_cost_gate_lowering_recommended",
    "learning_loop_last_bounded_probe_operator_authorization_object_emitted",
    "learning_loop_last_false_negative_candidate_friction_scorecard_bounded_demo_probe_authorized",
    "learning_loop_last_false_negative_candidate_friction_scorecard_operator_authorization_object_emitted",
    "live_authority_granted",
    "live_promotion",
    "order_authority_granted",
    "order_authority_granted_in_authorization_object",
    "order_authority_granted_in_object",
    "order_submitted",
    "operator_auth_active_runtime_authority",
    "operator_authorization_object_emitted",
    "profitability_cost_gate_escape_operator_authorization_object_emitted",
    "pg_write_performed",
    "probe_authority_granted",
    "probe_authority_granted_in_authorization_object",
    "probe_authority_granted_in_object",
    "promotion_evidence",
    "promotion_proof",
    "runtime_mutation_performed",
    "runtime_mutated",
    "runtime_writer_enabled",
    "runtime_writer_process_enabled",
    "service_restart_performed",
    "sealed_horizon_operator_review_bounded_demo_probe_authorized",
    "writer_enabled",
    "writer_process_enabled",
}
AUTHORITY_TRUE_KEY_SUFFIXES = (
    "_active_runtime_order_authority",
    "_active_runtime_probe_authority",
    "_bounded_demo_probe_authorized",
    "_global_cost_gate_lowering_recommended",
    "_live_authority_granted",
    "_live_promotion",
    "_operator_authorization_object_emitted",
    "_order_authority_granted",
    "_order_authority_granted_in_authorization_object",
    "_order_authority_granted_in_object",
    "_order_submitted",
    "_probe_authority_granted",
    "_probe_authority_granted_in_authorization_object",
    "_probe_authority_granted_in_object",
    "_promotion_evidence",
    "_promotion_proof",
    "_runtime_writer_enabled",
    "_runtime_writer_process_enabled",
    "_writer_enabled",
    "_writer_process_enabled",
)
AUTHORITY_NON_NONE_KEYS = {
    "active_authority",
    "active_runtime_authority",
    "live_authority",
    "main_cost_gate_adjustment",
    "operator_authorization",
    "order_authority",
    "probe_authority",
    "runtime_authority",
    "runtime_mutation",
}
AUTHORITY_NON_NONE_KEY_SUFFIXES = (
    "_active_authority",
    "_live_authority",
    "_main_cost_gate_adjustment",
    "_order_authority",
    "_probe_authority",
    "_runtime_authority",
    "_runtime_mutation",
)
AUTHORITY_NONE_VALUES = {
    "",
    "0",
    "ABSENT",
    "FALSE",
    "N/A",
    "NO",
    "NONE",
    "NOT_APPLICABLE",
    "NOT_GRANTED",
    "NULL",
}


def _utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _str(value: Any) -> str:
    return str(value or "").strip()


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if not math.isfinite(float(value)):
            return None
        return bool(value)
    text = _str(value).lower()
    if text in TRUTHY:
        return True
    if text in FALSEY:
        return False
    return None


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _field_present(payload: dict[str, Any], field_path: str) -> bool:
    value: Any = payload
    for part in field_path.split("."):
        if not isinstance(value, dict) or part not in value:
            return False
        value = value[part]
    return value is not None


def _authority_value_present(value: Any) -> bool:
    if value is None or value is False:
        return False
    if value is True:
        return True
    if isinstance(value, str):
        return value.strip().upper() not in AUTHORITY_NONE_VALUES
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value != 0
    if isinstance(value, dict):
        return bool(value)
    if isinstance(value, list):
        return bool(value)
    return bool(value)


def _contains_authority_signal(value: Any, path: str = "") -> str | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_str = str(key)
            key_path = f"{path}.{key_str}" if path else key_str
            key_lower = key_str.lower()
            authority_true_key = key_lower in AUTHORITY_TRUE_KEYS or key_lower.endswith(
                AUTHORITY_TRUE_KEY_SUFFIXES
            )
            authority_non_none_key = (
                key_lower in AUTHORITY_NON_NONE_KEYS
                or key_lower.endswith(AUTHORITY_NON_NONE_KEY_SUFFIXES)
            )
            if authority_true_key and _authority_value_present(item):
                return key_path
            if authority_non_none_key and _authority_value_present(item):
                return key_path
            found = _contains_authority_signal(item, key_path)
            if found:
                return found
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            found = _contains_authority_signal(item, f"{path}[{idx}]")
            if found:
                return found
    return None


def _sha_validation_error(value: str | None) -> str | None:
    clean = _str(value)
    if not clean:
        return "missing"
    if len(clean) < MIN_GIT_SHA_LEN or len(clean) > MAX_GIT_SHA_LEN:
        return "invalid_length"
    if any(char not in GIT_SHA_HEX for char in clean):
        return "non_hex"
    return None


def _sha_prefix_matches(head: str | None, target: str | None) -> bool | None:
    clean_head = _str(head)
    clean_target = _str(target)
    if _sha_validation_error(clean_head) or _sha_validation_error(clean_target):
        return None
    return clean_head.startswith(clean_target) or clean_target.startswith(clean_head)


def _read_text(path: Path | None) -> tuple[str | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        return path.read_text(encoding="utf-8"), None
    except FileNotFoundError:
        return None, "missing"
    except OSError as exc:
        return None, f"{type(exc).__name__}:{exc}"


def _read_json(path: Path | None) -> tuple[dict[str, Any] | None, str | None]:
    if path is None:
        return None, "missing_path"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None, "missing"
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return None, f"{type(exc).__name__}:{exc}"
    if not isinstance(payload, dict):
        return None, "not_object"
    return payload, None


def _env_assignments(line: str) -> dict[str, str]:
    try:
        tokens = shlex.split(line, comments=False, posix=True)
    except ValueError:
        tokens = line.split()
    env: dict[str, str] = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key and key.replace("_", "").isalnum():
            env[key] = value
    return env


def _matching_cron_entries(crontab_text: str | None) -> list[dict[str, Any]]:
    if crontab_text is None:
        return []
    entries: list[dict[str, Any]] = []
    for raw_line in crontab_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        for component, marker in STACK_CRON_MARKERS.items():
            if marker not in line:
                continue
            env = _env_assignments(line)
            resolved = None
            resolved_var = None
            for name in EXPECTED_HEAD_VARS_BY_COMPONENT[component]:
                value = _str(env.get(name))
                if value:
                    resolved = value
                    resolved_var = name
                    break
            entries.append({
                "component": component,
                "marker": marker,
                "line": line,
                "expected_head": resolved,
                "expected_head_var": resolved_var,
                "expected_head_vars_present": {
                    name: env.get(name)
                    for name in EXPECTED_HEAD_VARS_BY_COMPONENT[component]
                    if name in env
                },
            })
            break
    return entries


def _cron_expected_head_summary(
    *,
    crontab_text: str | None,
    crontab_error: str | None,
    target_source_head: str | None,
) -> dict[str, Any]:
    entries = _matching_cron_entries(crontab_text)
    expected_heads = sorted({
        _str(entry.get("expected_head"))
        for entry in entries
        if _str(entry.get("expected_head"))
    })
    target_source_head_error = _sha_validation_error(target_source_head)
    missing_components = [
        component
        for component in STACK_CRON_MARKERS
        if not any(entry["component"] == component for entry in entries)
    ]
    missing_expected_head = [
        entry["component"] for entry in entries if not _str(entry.get("expected_head"))
    ]
    invalid_expected_head_entries = [
        {
            "component": entry["component"],
            "expected_head": entry.get("expected_head"),
            "validation_error": _sha_validation_error(entry.get("expected_head")),
            "expected_head_var": entry.get("expected_head_var"),
        }
        for entry in entries
        if _str(entry.get("expected_head"))
        and _sha_validation_error(entry.get("expected_head")) is not None
    ]
    mismatched_entries = [
        {
            "component": entry["component"],
            "expected_head": entry.get("expected_head"),
            "target_source_head": target_source_head,
            "expected_head_var": entry.get("expected_head_var"),
        }
        for entry in entries
        if target_source_head_error is None
        and _sha_validation_error(entry.get("expected_head")) is None
        and _sha_prefix_matches(entry.get("expected_head"), target_source_head) is False
    ]
    inconsistent = len(expected_heads) > 1
    drift = (
        bool(mismatched_entries)
        or inconsistent
        or bool(missing_expected_head)
        or bool(invalid_expected_head_entries)
    )
    if crontab_error:
        status = "CRONTAB_SNAPSHOT_UNAVAILABLE"
    elif target_source_head_error == "missing":
        status = "TARGET_SOURCE_HEAD_MISSING"
    elif target_source_head_error is not None:
        status = "TARGET_SOURCE_HEAD_INVALID"
    elif not entries:
        status = "DEMO_LEARNING_STACK_CRON_ENTRIES_MISSING"
    elif drift:
        status = "CRON_EXPECTED_HEAD_DRIFT"
    else:
        status = "CRON_EXPECTED_HEAD_CONSISTENT"
    return {
        "status": status,
        "crontab_error": crontab_error,
        "target_source_head": target_source_head,
        "target_source_head_error": target_source_head_error,
        "matching_entry_count": len(entries),
        "missing_components": missing_components,
        "expected_heads": expected_heads,
        "inconsistent_expected_heads": inconsistent,
        "missing_expected_head_components": missing_expected_head,
        "invalid_expected_head_entries": invalid_expected_head_entries,
        "mismatched_entries": mismatched_entries,
        "expected_head_drift_present": drift,
        "entries": entries,
    }


def _api_service_summary(api_status: dict[str, Any] | None, source_error: str | None) -> dict[str, Any]:
    data = _dict(api_status)
    api_reachable = _bool(
        data.get("api_reachable")
        if "api_reachable" in data
        else data.get("reachable")
    )
    uvicorn_present = _bool(
        data.get("uvicorn_process_present")
        if "uvicorn_process_present" in data
        else data.get("process_present")
    )
    service_active = _bool(
        data.get("openclaw_trading_api_service_active")
        if "openclaw_trading_api_service_active" in data
        else data.get("service_active")
    )
    service_status = (
        data.get("openclaw_trading_api_service_status")
        or data.get("service_status")
    )
    process_owner = data.get("process_owner") or data.get("owner")
    evidence_present = bool(data) and source_error is None
    service_ownership_drift = (
        (api_reachable is True or uvicorn_present is True)
        and service_active is False
    )
    evidence_incomplete = evidence_present and (
        api_reachable is None or uvicorn_present is None or service_active is None
    )
    if source_error:
        status = "API_SERVICE_SNAPSHOT_UNAVAILABLE"
    elif not evidence_present:
        status = "API_SERVICE_EVIDENCE_MISSING"
    elif service_ownership_drift:
        status = "API_SERVICE_OWNERSHIP_DRIFT"
    elif evidence_incomplete:
        status = "API_SERVICE_EVIDENCE_INCOMPLETE"
    elif service_active is True and (api_reachable is True or uvicorn_present is True):
        status = "API_SERVICE_OWNERSHIP_ALIGNED"
    else:
        status = "API_SERVICE_REVIEW_REQUIRED"
    return {
        "status": status,
        "source_error": source_error,
        "api_reachable": api_reachable,
        "uvicorn_process_present": uvicorn_present,
        "openclaw_trading_api_service_active": service_active,
        "openclaw_trading_api_service_status": service_status,
        "process_owner": process_owner,
        "service_ownership_drift_present": service_ownership_drift,
        "evidence_incomplete": evidence_incomplete,
        "raw": data,
    }


def _source_checkout_summary(
    source_status: dict[str, Any] | None,
    source_error: str | None,
    target_source_head: str | None,
    source_status_supplied: bool,
) -> dict[str, Any]:
    data = _dict(source_status)
    runtime_head = _str(
        data.get("git_head")
        or data.get("runtime_source_head")
        or data.get("head")
    )
    runtime_head_error = _sha_validation_error(runtime_head)
    target_error = _sha_validation_error(target_source_head)
    if source_error:
        status = "SOURCE_CHECKOUT_SNAPSHOT_UNAVAILABLE"
    elif source_status_supplied and not data:
        status = "SOURCE_CHECKOUT_EVIDENCE_MISSING"
    elif not data:
        status = "SOURCE_CHECKOUT_NOT_SUPPLIED"
    elif runtime_head_error == "missing":
        status = "RUNTIME_SOURCE_HEAD_MISSING"
    elif runtime_head_error is not None:
        status = "RUNTIME_SOURCE_HEAD_INVALID"
    elif target_error == "missing":
        status = "TARGET_SOURCE_HEAD_MISSING"
    elif target_error is not None:
        status = "TARGET_SOURCE_HEAD_INVALID"
    elif _sha_prefix_matches(runtime_head, target_source_head) is False:
        status = "RUNTIME_SOURCE_HEAD_MISMATCH"
    elif _bool(data.get("source_activation_ready")) is False:
        status = "RUNTIME_SOURCE_REVIEW_REQUIRED"
    else:
        status = "RUNTIME_SOURCE_ALIGNED"
    return {
        "status": status,
        "source_error": source_error,
        "target_source_head": target_source_head,
        "runtime_source_head": runtime_head or None,
        "runtime_source_head_error": runtime_head_error,
        "git_head": runtime_head or None,
        "git_head_short": data.get("git_head_short") or runtime_head[:8] or None,
        "expected_head_status": data.get("expected_head_status"),
        "source_activation_status": data.get("source_activation_status"),
        "source_activation_ready": data.get("source_activation_ready"),
        "runtime_source_drift_present": status in {
            "RUNTIME_SOURCE_HEAD_MISMATCH",
            "RUNTIME_SOURCE_HEAD_MISSING",
            "RUNTIME_SOURCE_HEAD_INVALID",
            "RUNTIME_SOURCE_REVIEW_REQUIRED",
        },
        "raw": data,
    }


def _artifact_rows(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    raw_rows = payload.get("artifacts")
    if isinstance(raw_rows, list):
        for row in raw_rows:
            if isinstance(row, dict) and _str(row.get("name")):
                rows[_str(row.get("name"))] = row
    for name, row in payload.items():
        if isinstance(row, dict) and name != "artifacts":
            rows.setdefault(name, row)
    return rows


def _missing_fields_for_artifact(row: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    explicit = row.get("missing_required_fields")
    if isinstance(explicit, list):
        return [_str(item) for item in explicit if _str(item)]
    payload = _dict(row.get("payload"))
    if not payload:
        payload = row
    return [field for field in fields if not _field_present(payload, field)]


def _friction_status_blocker(payload: dict[str, Any]) -> dict[str, Any]:
    current = _dict(
        payload.get("friction_scorecard_current_status")
        or payload.get("false_negative_candidate_friction_scorecard_current_status")
    )
    if not current:
        return {}
    rc = _int(current.get("rc") if "rc" in current else current.get("returncode"))
    status = _str(current.get("status")).upper()
    enabled = _bool(current.get("enabled"))
    blocked = (
        enabled is False
        or (rc is not None and rc != 0)
        or any(token in status for token in ("DISABLED", "SKIP", "ERROR", "FAILED"))
    )
    if not blocked:
        return {}
    return {
        "status": status or None,
        "rc": rc,
        "enabled": enabled,
        "reason": current.get("reason"),
    }


def _artifact_compatibility_summary(
    artifact_status: dict[str, Any] | None,
    artifact_error: str | None,
    artifact_status_supplied: bool,
) -> dict[str, Any]:
    data = _dict(artifact_status)
    rows = _artifact_rows(data)
    issues: list[dict[str, Any]] = []
    friction_blocker = _friction_status_blocker(data)
    mm = rows.get(MM_CONFIRMATION_NAME)
    if artifact_status_supplied and mm is None:
        issues.append({"artifact": MM_CONFIRMATION_NAME, "issue": "check_not_supplied"})
    if mm is not None:
        if mm.get("present") is False:
            issues.append({"artifact": MM_CONFIRMATION_NAME, "issue": "missing"})
        elif _str(mm.get("schema_version")) != "mm_current_fee_confirmation_packet_v1":
            issues.append({"artifact": MM_CONFIRMATION_NAME, "issue": "schema_mismatch"})
        else:
            missing = _missing_fields_for_artifact(mm, MM_CURRENT_FEE_REQUIRED_FIELDS)
            if missing:
                issues.append({
                    "artifact": MM_CONFIRMATION_NAME,
                    "issue": "missing_required_fields",
                    "missing_required_fields": missing,
                })
    friction = rows.get(FRICTION_SCORECARD_NAME)
    if artifact_status_supplied and friction is None:
        issues.append({"artifact": FRICTION_SCORECARD_NAME, "issue": "check_not_supplied"})
    if friction is not None:
        if friction.get("present") is False:
            issues.append({"artifact": FRICTION_SCORECARD_NAME, "issue": "missing"})
        elif not _str(friction.get("status")):
            issues.append({"artifact": FRICTION_SCORECARD_NAME, "issue": "status_missing"})
    if friction_blocker:
        issues.append({
            "artifact": FRICTION_SCORECARD_NAME,
            "issue": "current_status_not_clean",
            "current_status": friction_blocker,
        })
    if artifact_error:
        status = "ARTIFACT_COMPATIBILITY_SNAPSHOT_UNAVAILABLE"
    elif artifact_status_supplied and not data:
        status = "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    elif not data:
        status = "ARTIFACT_COMPATIBILITY_NOT_SUPPLIED"
    elif issues:
        status = "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT"
    else:
        status = "CANONICAL_ARTIFACT_COMPATIBILITY_CLEAN"
    return {
        "status": status,
        "source_error": artifact_error,
        "artifact_compatibility_drift_present": bool(issues),
        "issues": issues,
        "artifacts": rows,
        "raw": data,
    }


def _dedupe(items: list[Any]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = _str(item)
        if not text or text in seen:
            continue
        seen.add(text)
        out.append(text)
    return out


def _status(
    cron: dict[str, Any],
    api: dict[str, Any],
    source: dict[str, Any],
    artifacts: dict[str, Any],
    authority_violation: str | None,
) -> tuple[str, str, list[str]]:
    next_actions: list[str] = []
    if authority_violation:
        return (
            "RUNTIME_HEALTH_HYGIENE_BOUNDARY_VIOLATION",
            f"authority_or_proof_signal_in_supplied_snapshot:{authority_violation}",
            ["repair_supplied_runtime_health_hygiene_snapshots_before_review"],
        )
    cron_drift = cron.get("expected_head_drift_present") is True
    api_drift = api.get("service_ownership_drift_present") is True
    source_drift = source.get("runtime_source_drift_present") is True
    artifact_drift = artifacts.get("artifact_compatibility_drift_present") is True
    if cron_drift:
        next_actions.append("operator_reinstall_or_update_demo_learning_cron_expected_head_pins")
    if api_drift:
        next_actions.append("operator_choose_single_trading_api_service_owner_then_restart_under_that_owner")
    if source_drift:
        next_actions.append("operator_review_runtime_source_sync_to_target_head")
    if artifact_drift:
        next_actions.append("refresh_or_quarantine_stale_canonical_profit_learning_artifacts")
    if cron["status"] == "CRONTAB_SNAPSHOT_UNAVAILABLE":
        next_actions.append("capture_runtime_crontab_snapshot_before_hygiene_decision")
    if cron["status"] == "TARGET_SOURCE_HEAD_MISSING":
        next_actions.append("supply_target_source_head_before_hygiene_decision")
    if cron["status"] == "TARGET_SOURCE_HEAD_INVALID":
        next_actions.append("supply_valid_target_source_head_before_hygiene_decision")
    if cron["status"] == "DEMO_LEARNING_STACK_CRON_ENTRIES_MISSING":
        next_actions.append("operator_review_demo_learning_stack_cron_install_or_snapshot")
    if api["status"] in {"API_SERVICE_SNAPSHOT_UNAVAILABLE", "API_SERVICE_EVIDENCE_MISSING", "API_SERVICE_EVIDENCE_INCOMPLETE"}:
        next_actions.append("capture_read_only_trading_api_service_and_process_snapshot")
    if api["status"] == "API_SERVICE_REVIEW_REQUIRED":
        next_actions.append("operator_review_trading_api_service_ownership_snapshot")
    if source["status"] in {
        "SOURCE_CHECKOUT_SNAPSHOT_UNAVAILABLE",
        "SOURCE_CHECKOUT_EVIDENCE_MISSING",
        "RUNTIME_SOURCE_HEAD_MISSING",
        "RUNTIME_SOURCE_HEAD_INVALID",
        "TARGET_SOURCE_HEAD_MISSING",
        "TARGET_SOURCE_HEAD_INVALID",
    }:
        next_actions.append("capture_read_only_runtime_source_checkout_snapshot")
    if artifacts["status"] == "ARTIFACT_COMPATIBILITY_SNAPSHOT_UNAVAILABLE":
        next_actions.append("capture_canonical_profit_learning_artifact_status_snapshot")
    drift_count = sum(bool(item) for item in (cron_drift, api_drift, source_drift, artifact_drift))
    if drift_count > 1:
        return (
            "RUNTIME_HEALTH_HYGIENE_DRIFT",
            "multiple_runtime_health_hygiene_drifts_present",
            _dedupe(next_actions),
        )
    if cron_drift:
        return (
            "CRON_EXPECTED_HEAD_DRIFT",
            "installed_demo_learning_cron_expected_head_pins_do_not_match_target_source_head",
            _dedupe(next_actions),
        )
    if api_drift:
        return (
            "API_SERVICE_OWNERSHIP_DRIFT",
            "api_reachable_or_uvicorn_present_while_openclaw_trading_api_service_inactive",
            _dedupe(next_actions),
        )
    if source_drift:
        return (
            "RUNTIME_SOURCE_HEAD_MISMATCH",
            "runtime_source_head_does_not_match_target_source_head",
            _dedupe(next_actions),
        )
    if artifact_drift:
        return (
            "CANONICAL_ARTIFACT_COMPATIBILITY_DRIFT",
            "canonical_profit_learning_artifacts_missing_or_not_compatible_with_current_source_contract",
            _dedupe(next_actions),
        )
    if api["status"] == "API_SERVICE_REVIEW_REQUIRED":
        return (
            "API_SERVICE_REVIEW_REQUIRED",
            "api_service_snapshot_requires_operator_review_before_hygiene_clean",
            _dedupe(next_actions),
        )
    if next_actions:
        return (
            "RUNTIME_HEALTH_HYGIENE_EVIDENCE_INCOMPLETE",
            "read_only_snapshot_missing_or_incomplete",
            _dedupe(next_actions),
        )
    return (
        "RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY",
        "supplied_cron_and_api_snapshots_do_not_show_expected_head_or_service_ownership_drift",
        ["continue_profit_evidence_quality_operator_resolution_before_bounded_probe_selection"],
    )


def build_runtime_health_hygiene_packet(
    *,
    crontab_text: str | None,
    target_source_head: str | None,
    api_service_status: dict[str, Any] | None = None,
    source_status: dict[str, Any] | None = None,
    artifact_status: dict[str, Any] | None = None,
    crontab_error: str | None = None,
    api_service_status_error: str | None = None,
    source_status_error: str | None = None,
    artifact_status_error: str | None = None,
    crontab_text_path: Path | None = None,
    api_service_status_path: Path | None = None,
    source_status_path: Path | None = None,
    artifact_status_path: Path | None = None,
    now_utc: dt.datetime | None = None,
) -> dict[str, Any]:
    now = (now_utc or _utc_now()).astimezone(dt.timezone.utc)
    authority_violation = (
        _contains_authority_signal(api_service_status, "api_service_status")
        or _contains_authority_signal(source_status, "source_status")
        or _contains_authority_signal(artifact_status, "artifact_status")
    )
    cron = _cron_expected_head_summary(
        crontab_text=crontab_text,
        crontab_error=crontab_error,
        target_source_head=target_source_head,
    )
    api = _api_service_summary(api_service_status, api_service_status_error)
    source = _source_checkout_summary(
        source_status,
        source_status_error,
        target_source_head,
        source_status is not None
        or source_status_error is not None
        or source_status_path is not None,
    )
    artifacts = _artifact_compatibility_summary(
        artifact_status,
        artifact_status_error,
        artifact_status is not None
        or artifact_status_error is not None
        or artifact_status_path is not None,
    )
    status, reason, next_actions = _status(
        cron,
        api,
        source,
        artifacts,
        authority_violation,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": now.isoformat(),
        "status": status,
        "reason": reason,
        "next_actions": next_actions,
        "target_source_head": target_source_head,
        "cron_expected_head": cron,
        "api_service_ownership": api,
        "source_checkout": source,
        "artifact_compatibility": artifacts,
        "sources": {
            "crontab_text_path": str(crontab_text_path) if crontab_text_path else None,
            "api_service_status_path": (
                str(api_service_status_path) if api_service_status_path else None
            ),
            "source_status_path": (
                str(source_status_path) if source_status_path else None
            ),
            "artifact_status_path": (
                str(artifact_status_path) if artifact_status_path else None
            ),
        },
        "answers": {
            "cron_expected_head_drift_present": cron.get("expected_head_drift_present") is True,
            "api_service_ownership_drift_present": api.get("service_ownership_drift_present") is True,
            "runtime_source_drift_present": source.get("runtime_source_drift_present") is True,
            "artifact_compatibility_drift_present": (
                artifacts.get("artifact_compatibility_drift_present") is True
            ),
            "authority_boundary_violation_present": authority_violation is not None,
            "operator_action_required": status != "RUNTIME_HEALTH_HYGIENE_CLEAN_SOURCE_ONLY",
            "crontab_mutation_performed": False,
            "service_restart_performed": False,
            "runtime_mutation_performed": False,
            "pg_query_performed": False,
            "pg_write_performed": False,
            "bybit_call_performed": False,
            "global_cost_gate_lowering_recommended": False,
            "main_cost_gate_adjustment": "NONE",
            "probe_authority_granted": False,
            "order_authority_granted": False,
            "promotion_evidence": False,
        },
        "boundary": BOUNDARY,
    }


def render_markdown(packet: dict[str, Any]) -> str:
    cron = _dict(packet.get("cron_expected_head"))
    api = _dict(packet.get("api_service_ownership"))
    source = _dict(packet.get("source_checkout"))
    artifacts = _dict(packet.get("artifact_compatibility"))
    answers = _dict(packet.get("answers"))
    lines = [
        "# Runtime Health Hygiene Packet",
        "",
        f"- Generated: `{packet.get('generated_at_utc')}`",
        f"- Status: `{packet.get('status')}`",
        f"- Reason: `{packet.get('reason')}`",
        f"- Target source head: `{packet.get('target_source_head')}`",
        f"- Cron expected-head status: `{cron.get('status')}`",
        f"- API service status: `{api.get('status')}`",
        f"- Runtime source status: `{source.get('status')}`",
        f"- Artifact compatibility status: `{artifacts.get('status')}`",
        f"- Operator action required: `{answers.get('operator_action_required')}`",
        f"- Boundary: {BOUNDARY}.",
        "",
        "## Next Actions",
        "",
    ]
    for action in packet.get("next_actions") or []:
        lines.append(f"- `{action}`")
    lines.extend(["", "## Cron Entries", ""])
    for entry in cron.get("entries") or []:
        lines.append(
            "- `{component}` expected `{head}` via `{var}`".format(
                component=entry.get("component"),
                head=entry.get("expected_head"),
                var=entry.get("expected_head_var"),
            )
        )
    if artifacts.get("issues"):
        lines.extend(["", "## Artifact Issues", ""])
        for issue in artifacts.get("issues") or []:
            lines.append(f"- `{issue}`")
    return "\n".join(lines) + "\n"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--crontab-text-file", type=Path)
    parser.add_argument("--api-service-status-json", type=Path)
    parser.add_argument("--source-status-json", type=Path)
    parser.add_argument("--artifact-status-json", type=Path)
    parser.add_argument("--target-source-head")
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--print-json", action="store_true")
    return parser


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


def main() -> int:
    args = _build_parser().parse_args()
    crontab_text, crontab_error = _read_text(args.crontab_text_file)
    api_status, api_error = (
        _read_json(args.api_service_status_json)
        if args.api_service_status_json
        else (None, None)
    )
    source_status, source_error = (
        _read_json(args.source_status_json)
        if args.source_status_json
        else (None, None)
    )
    artifact_status, artifact_error = (
        _read_json(args.artifact_status_json)
        if args.artifact_status_json
        else (None, None)
    )
    packet = build_runtime_health_hygiene_packet(
        crontab_text=crontab_text,
        target_source_head=args.target_source_head,
        api_service_status=api_status,
        source_status=source_status,
        artifact_status=artifact_status,
        crontab_error=crontab_error,
        api_service_status_error=api_error,
        source_status_error=source_error,
        artifact_status_error=artifact_error,
        crontab_text_path=args.crontab_text_file,
        api_service_status_path=args.api_service_status_json,
        source_status_path=args.source_status_json,
        artifact_status_path=args.artifact_status_json,
    )
    markdown = render_markdown(packet)
    if args.json_output:
        _write_json(args.json_output, packet)
    if args.output:
        _write_text(args.output, markdown)
    if args.print_json:
        print(json.dumps(packet, ensure_ascii=False, sort_keys=True, default=str))
    elif not args.output:
        print(markdown, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

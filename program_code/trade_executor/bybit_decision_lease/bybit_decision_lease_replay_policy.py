#!/usr/bin/env python3
import hashlib
import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
SHADOW_PATH = BASE / "bybit_decision_lease_shadow_issue_latest.json"
CONSUME_GATE_PATH = BASE / "bybit_decision_lease_consume_gate_latest.json"
CONSUME_AUDIT_PATH = BASE / "bybit_decision_lease_consume_final_audit_latest.json"

STEM = "bybit_decision_lease_replay_policy"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    now_ms = int(time.time() * 1000)

    shadow = read_json(SHADOW_PATH)
    consume_gate = read_json(CONSUME_GATE_PATH)
    consume_audit = read_json(CONSUME_AUDIT_PATH)

    candidate = shadow.get("shadow_candidate") or {}
    consume_decision = consume_gate.get("consume_decision") or {}
    consume_summary = consume_audit.get("audit_summary") or {}
    request_summary = shadow.get("request_summary") or {}

    lease_id = str(candidate.get("lease_id") or "")
    issue_ts_ms = int(candidate.get("issue_ts_ms") or 0)
    expires_ts_ms = int(candidate.get("expires_ts_ms") or 0)
    ttl_ms = int(candidate.get("ttl_ms") or 0)
    symbol = str(candidate.get("symbol") or "unknown")
    route_plan = str(request_summary.get("route_plan") or "unknown")
    provider_target = str(request_summary.get("provider_target") or "unknown")
    model_name = str(request_summary.get("model_name") or "unknown")

    replay_identity_text = "|".join([
        lease_id,
        symbol,
        str(issue_ts_ms),
        str(expires_ts_ms),
        route_plan,
        provider_target,
        model_name,
    ])
    replay_key = sha256_text(replay_identity_text)
    revoke_key = sha256_text("revoke|" + replay_identity_text)
    replay_window_ms = ttl_ms
    revoke_window_ms = ttl_ms

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("shadow_issue_ok", shadow.get("shadow_issue_ok") is True, shadow.get("shadow_issue_ok"))
    add("consume_gate_ok", consume_gate.get("gate_ok") is True, consume_gate.get("gate_ok"))
    add("consume_audit_ok", consume_audit.get("overall_ok") is True, consume_audit.get("overall_ok"))
    add("lease_mode_shadow_only", candidate.get("lease_mode") == "shadow_only", candidate.get("lease_mode"))
    add("shadow_consume_only", consume_summary.get("shadow_consume_only") is True, consume_summary.get("shadow_consume_only"))
    add("consume_gate_open_live_false", consume_summary.get("consume_gate_open_live") is False, consume_summary.get("consume_gate_open_live"))
    add("decision_lease_consumed_false", consume_summary.get("decision_lease_consumed") is False, consume_summary.get("decision_lease_consumed"))
    add("replay_key_present", bool(replay_key), replay_key[:16] if replay_key else None)
    add("revoke_key_present", bool(revoke_key), revoke_key[:16] if revoke_key else None)
    add("replay_window_positive", replay_window_ms > 0, replay_window_ms)

    hard_fail_names = {
        "shadow_issue_ok",
        "consume_gate_ok",
        "consume_audit_ok",
        "lease_mode_shadow_only",
        "shadow_consume_only",
        "consume_gate_open_live_false",
        "decision_lease_consumed_false",
        "replay_key_present",
        "revoke_key_present",
        "replay_window_positive",
    }

    policy_ok = not any(name in hard_fail_names for name in failed_checks)

    warning_flags: List[str] = []
    warning_flags.extend(shadow.get("warning_flags") or [])
    warning_flags.extend(consume_gate.get("warning_flags") or [])
    warning_flags.extend(consume_audit.get("warning_flags") or [])
    warning_flags.append("decision_lease_replay_shadow_only_mode")
    warning_flags = uniq(warning_flags)

    replay_policy = {
        "lease_id": lease_id,
        "replay_key": replay_key,
        "revoke_key": revoke_key,
        "replay_window_ms": replay_window_ms,
        "revoke_window_ms": revoke_window_ms,
        "replay_guard_enabled": True,
        "revoke_supported_in_schema": True,
        "revoke_live_enabled": False,
        "replay_live_enforced": False,
        "shadow_only_mode": True,
        "first_consume_allowed_once": True,
        "duplicate_consume_must_be_rejected": True,
        "revoke_after_consume_supported_future": True,
        "consume_receipt_store_mode": "shadow_memory_model_only",
    }

    if not policy_ok:
        policy_state = "decision_lease_replay_policy_blocked"
        allow_progress = False
        recommended_action = "inspect_i4a_replay_policy_failures"
    elif warning_flags:
        policy_state = "decision_lease_replay_policy_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i4b_replay_guard"
    else:
        policy_state = "decision_lease_replay_policy_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i4b_replay_guard"

    report = {
        "policy_type": STEM,
        "policy_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I4-A",
        "policy_ok": policy_ok,
        "source_refs": {
            "decision_lease_shadow_issue_path": str(SHADOW_PATH),
            "decision_lease_consume_gate_path": str(CONSUME_GATE_PATH),
            "decision_lease_consume_audit_path": str(CONSUME_AUDIT_PATH),
        },
        "request_summary": request_summary,
        "replay_policy": replay_policy,
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not policy_ok else [],
        "policy_state": policy_state,
        "allow_progress_to_i4b_replay_guard": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I4-A replay policy complete. Lease replay and revoke identities are defined in shadow mode, without enabling live revoke or live replay enforcement.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()

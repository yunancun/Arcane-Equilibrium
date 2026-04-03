#!/usr/bin/env python3
import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
POLICY_PATH = BASE / "bybit_decision_lease_consume_policy_latest.json"
STEM = "bybit_decision_lease_consume_gate"


def main() -> None:
    now_ms = int(time.time() * 1000)
    policy = read_json(POLICY_PATH)
    view = policy.get("consume_policy_view") or {}

    simulated_before_expiry = bool(view.get("simulated_before_expiry"))
    simulated_within_recommended_window = bool(view.get("simulated_within_recommended_window"))
    simulated_freshness_ok = bool(view.get("simulated_freshness_ok"))

    now_before_expiry = bool(view.get("now_before_expiry"))
    now_within_recommended_window = bool(view.get("now_within_recommended_window"))
    now_freshness_ok = bool(view.get("now_freshness_ok"))

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("policy_ok", policy.get("policy_ok") is True, policy.get("policy_ok"))
    add("simulated_before_expiry", simulated_before_expiry, simulated_before_expiry)
    add("simulated_within_recommended_window", simulated_within_recommended_window, simulated_within_recommended_window)
    add("simulated_freshness_ok", simulated_freshness_ok, simulated_freshness_ok)
    add("shadow_mode_only", view.get("lease_mode") == "shadow_only", view.get("lease_mode"))
    add("consume_mode_expected", view.get("consume_mode") == "shadow_simulated_then_observe_now", view.get("consume_mode"))

    hard_fail_names = {
        "policy_ok",
        "simulated_before_expiry",
        "simulated_within_recommended_window",
        "simulated_freshness_ok",
        "shadow_mode_only",
        "consume_mode_expected",
    }

    gate_ok = not any(name in hard_fail_names for name in failed_checks)

    would_pass_if_now = (
        now_before_expiry and
        now_within_recommended_window and
        now_freshness_ok
    )

    consume_decision = {
        "consume_mode": "shadow_simulated_only",
        "consume_ts_basis": "issue_ts_plus_expected_issue_to_consume_ms",
        "simulated_consume_ts_ms": view.get("simulated_consume_ts_ms"),
        "recommended_consume_before_ts_ms": view.get("recommended_consume_before_ts_ms"),
        "expires_ts_ms": view.get("expires_ts_ms"),
        "would_pass_if_simulated": gate_ok,
        "would_pass_if_now": would_pass_if_now,
        "shadow_consume_ready": gate_ok,
        "consume_gate_open_live": False,
        "consume_authority": "not_granted",
        "decision_lease_consumed": False,
        "consume_receipt_emitted": False,
        "headroom_remaining_at_simulated_ms": (
            int(view.get("expires_ts_ms") or 0) - int(view.get("simulated_consume_ts_ms") or 0)
        ),
        "headroom_remaining_if_now_ms": (
            int(view.get("expires_ts_ms") or 0) - int(view.get("now_ts_ms") or 0)
        ),
    }

    warning_flags: List[str] = []
    warning_flags.extend(policy.get("warning_flags") or [])
    if not would_pass_if_now:
        warning_flags.append("consume_now_path_would_not_pass")
    warning_flags = uniq(warning_flags)

    if not gate_ok:
        gate_state = "decision_lease_consume_gate_blocked"
        allow_progress = False
        recommended_action = "inspect_i3b_consume_gate_failures"
    elif warning_flags:
        gate_state = "decision_lease_consume_gate_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i3c_final_audit"
    else:
        gate_state = "decision_lease_consume_gate_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i3c_final_audit"

    report = {
        "gate_type": STEM,
        "gate_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I3-B",
        "gate_ok": gate_ok,
        "source_refs": {
            "decision_lease_consume_policy_path": str(POLICY_PATH),
        },
        "request_summary": policy.get("request_summary") or {},
        "consume_decision": consume_decision,
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not gate_ok else [],
        "gate_state": gate_state,
        "allow_progress_to_i3c_final_audit": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I3-B consume gate complete. The lease consume path is validated in simulated shadow mode only, while the real-time now-path is recorded for friction observation.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()

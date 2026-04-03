#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
GOV_PATH = BASE / "bybit_ai_governed_decision_latest.json"
SCHEMA_PATH = BASE / "bybit_decision_lease_schema_latest.json"
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"

STEM = "bybit_decision_lease_preflight"


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def main() -> None:
    now_ms = int(time.time() * 1000)

    governed = read_json(GOV_PATH)
    schema = read_json(SCHEMA_PATH)
    invocation = read_json(INV_PATH)

    ttl_floor_ms = env_int("BYBIT_DECISION_LEASE_TTL_FLOOR_MS", 3000)
    ttl_target_ms = env_int("BYBIT_DECISION_LEASE_TTL_TARGET_MS", 12000)
    consume_slack_ms = env_int("BYBIT_DECISION_LEASE_CONSUME_SLACK_MS", 1500)
    expected_issue_to_consume_ms = env_int("BYBIT_DECISION_LEASE_EXPECTED_ISSUE_TO_CONSUME_MS", 800)
    freshness_grace_ms = env_int("BYBIT_DECISION_LEASE_FRESHNESS_GRACE_MS", 5000)
    shadow_only = os.getenv("BYBIT_DECISION_LEASE_SHADOW_ONLY", "1").strip() not in {"0", "false", "False"}

    latency_ms = ((invocation.get("attempt_result") or {}).get("latency_ms"))
    if not isinstance(latency_ms, int):
        latency_ms = 0

    issue_window_ok = ttl_target_ms > (expected_issue_to_consume_ms + consume_slack_ms)
    ttl_headroom_ms = ttl_target_ms - expected_issue_to_consume_ms - consume_slack_ms

    governance = governed.get("governance_guards") or {}
    observation = governed.get("governed_observation") or {}
    schema_runtime = schema.get("schema_runtime_view") or {}

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add_check(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add_check("governed_decision_ok", governed.get("decision_ok") is True, governed.get("decision_ok"))
    add_check("schema_ok", schema.get("schema_ok") is True, schema.get("schema_ok"))
    add_check("schema_only_mode_true", schema_runtime.get("schema_only_mode") is True, schema_runtime.get("schema_only_mode"))
    add_check("lease_emit_allowed_now_false", schema_runtime.get("lease_emit_allowed_now") is False, schema_runtime.get("lease_emit_allowed_now"))
    add_check("decision_lease_emitted_false", schema_runtime.get("decision_lease_emitted") is False, schema_runtime.get("decision_lease_emitted"))
    add_check("execution_authority_not_granted", governance.get("execution_authority") == "not_granted", governance.get("execution_authority"))
    add_check("live_execution_allowed_false", governance.get("live_execution_allowed") is False, governance.get("live_execution_allowed"))
    add_check("analysis_mode_observation_only", observation.get("analysis_mode") == "observation_only", observation.get("analysis_mode"))
    add_check("ttl_target_ge_floor", ttl_target_ms >= ttl_floor_ms, {"ttl_target_ms": ttl_target_ms, "ttl_floor_ms": ttl_floor_ms})
    add_check("issue_window_ok", issue_window_ok, {"ttl_target_ms": ttl_target_ms, "expected_issue_to_consume_ms": expected_issue_to_consume_ms, "consume_slack_ms": consume_slack_ms})

    hard_fail_names = {
        "governed_decision_ok",
        "schema_ok",
        "schema_only_mode_true",
        "lease_emit_allowed_now_false",
        "decision_lease_emitted_false",
        "execution_authority_not_granted",
        "live_execution_allowed_false",
        "analysis_mode_observation_only",
        "ttl_target_ge_floor",
        "issue_window_ok",
    }

    preflight_ok = not any(name in hard_fail_names for name in failed_checks)

    warning_flags = []
    warning_flags.extend(governed.get("warning_flags") or [])
    warning_flags.extend(schema.get("warning_flags") or [])
    warning_flags.extend(invocation.get("warning_flags") or [])

    if ttl_headroom_ms < consume_slack_ms:
        warning_flags.append("lease_ttl_headroom_low")
    if latency_ms >= ttl_target_ms:
        warning_flags.append("last_ai_latency_near_or_above_lease_ttl")
    if shadow_only:
        warning_flags.append("decision_lease_shadow_only_mode")

    warning_flags = uniq(warning_flags)

    if not preflight_ok:
        preflight_state = "decision_lease_preflight_blocked"
        allow_progress = False
        recommended_action = "inspect_decision_lease_preflight_failures"
    elif warning_flags:
        preflight_state = "decision_lease_preflight_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i2b_shadow_issue"
    else:
        preflight_state = "decision_lease_preflight_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i2b_shadow_issue"

    report = {
        "preflight_type": STEM,
        "preflight_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I2-A",
        "preflight_ok": preflight_ok,
        "source_refs": {
            "governed_decision_path": str(GOV_PATH),
            "decision_lease_schema_path": str(SCHEMA_PATH),
            "ai_invocation_attempt_path": str(INV_PATH),
        },
        "request_summary": {
            "provider_target": ((governed.get("request_summary") or {}).get("provider_target")),
            "model_name": ((governed.get("request_summary") or {}).get("model_name")),
            "selected_ai_tier": ((governed.get("request_summary") or {}).get("selected_ai_tier")),
            "route_plan": ((governed.get("request_summary") or {}).get("route_plan")),
        },
        "governance_snapshot": governance,
        "observation_snapshot": {
            "analysis_mode": observation.get("analysis_mode"),
            "market_regime": observation.get("market_regime"),
            "action_bias": observation.get("action_bias"),
            "confidence_0_to_1": observation.get("confidence_0_to_1"),
            "edge_assessment_bps": observation.get("edge_assessment_bps"),
        },
        "issue_timing_profile": {
            "ttl_floor_ms": ttl_floor_ms,
            "ttl_target_ms": ttl_target_ms,
            "consume_slack_ms": consume_slack_ms,
            "expected_issue_to_consume_ms": expected_issue_to_consume_ms,
            "freshness_grace_ms": freshness_grace_ms,
            "last_ai_latency_ms": latency_ms,
            "ttl_headroom_ms": ttl_headroom_ms,
            "issue_window_ok": issue_window_ok,
            "shadow_only_mode": shadow_only,
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not preflight_ok else [],
        "preflight_state": preflight_state,
        "allow_progress_to_i2b_shadow_issue": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I2-A decision lease preflight complete. This stage only evaluates whether a future execution lease could be issued late and consumed quickly, without emitting any live lease.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()

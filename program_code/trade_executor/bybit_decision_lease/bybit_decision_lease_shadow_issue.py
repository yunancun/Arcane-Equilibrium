#!/usr/bin/env python3
import hashlib
import json
import time
from pathlib import Path
import os
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
PREFLIGHT_PATH = BASE / "bybit_decision_lease_preflight_latest.json"
SCHEMA_PATH = BASE / "bybit_decision_lease_schema_latest.json"
GOV_PATH = BASE / "bybit_ai_governed_decision_latest.json"

STEM = "bybit_decision_lease_shadow_issue"


def main() -> None:
    now_ms = int(time.time() * 1000)

    preflight = read_json(PREFLIGHT_PATH)
    schema = read_json(SCHEMA_PATH)
    governed = read_json(GOV_PATH)

    issue_timing = preflight.get("issue_timing_profile") or {}
    schema_def = schema.get("lease_schema_definition") or {}
    schema_runtime = schema.get("schema_runtime_view") or {}
    governance = governed.get("governance_guards") or {}
    observation = governed.get("governed_observation") or {}

    ttl_ms = int(issue_timing.get("ttl_target_ms") or 0)
    consume_slack_ms = int(issue_timing.get("consume_slack_ms") or 0)

    valid_after_ts_ms = now_ms
    expires_ts_ms = now_ms + ttl_ms
    recommended_consume_before_ts_ms = expires_ts_ms - consume_slack_ms

    obs_fingerprint = hashlib.sha256(
        json.dumps(observation, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()

    lease_id = "shadow-" + hashlib.sha256(
        f"{now_ms}|{obs_fingerprint}".encode("utf-8")
    ).hexdigest()[:24]

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("preflight_ok", preflight.get("preflight_ok") is True, preflight.get("preflight_ok"))
    add("schema_only_mode_true", schema_runtime.get("schema_only_mode") is True, schema_runtime.get("schema_only_mode"))
    add("lease_emit_allowed_now_false", schema_runtime.get("lease_emit_allowed_now") is False, schema_runtime.get("lease_emit_allowed_now"))
    add("decision_lease_emitted_false", schema_runtime.get("decision_lease_emitted") is False, schema_runtime.get("decision_lease_emitted"))
    add("execution_authority_not_granted", governance.get("execution_authority") == "not_granted", governance.get("execution_authority"))
    add("live_execution_allowed_false", governance.get("live_execution_allowed") is False, governance.get("live_execution_allowed"))
    add("ttl_positive", ttl_ms > 0, ttl_ms)
    add("expires_after_issue", expires_ts_ms > valid_after_ts_ms, {"valid_after_ts_ms": valid_after_ts_ms, "expires_ts_ms": expires_ts_ms})
    add("recommended_consume_before_expiry", recommended_consume_before_ts_ms > valid_after_ts_ms, {"recommended_consume_before_ts_ms": recommended_consume_before_ts_ms, "valid_after_ts_ms": valid_after_ts_ms})

    hard_fail_names = {
        "preflight_ok",
        "schema_only_mode_true",
        "lease_emit_allowed_now_false",
        "decision_lease_emitted_false",
        "execution_authority_not_granted",
        "live_execution_allowed_false",
        "ttl_positive",
        "expires_after_issue",
        "recommended_consume_before_expiry",
    }
    shadow_issue_ok = not any(name in hard_fail_names for name in failed_checks)

    shadow_candidate = {
        "lease_id": lease_id,
        "lease_mode": "shadow_only",
        "lease_schema_version": schema.get("schema_version"),
        "execution_authority_required": schema_def.get("execution_authority_required"),
        "execution_authority_current": governance.get("execution_authority"),
        "issue_ts_ms": now_ms,
        "valid_after_ts_ms": valid_after_ts_ms,
        "expires_ts_ms": expires_ts_ms,
        "ttl_ms": ttl_ms,
        "consume_slack_ms": consume_slack_ms,
        "recommended_consume_before_ts_ms": recommended_consume_before_ts_ms,
        "observation_fingerprint": obs_fingerprint,
        "analysis_mode": observation.get("analysis_mode"),
        "market_regime": observation.get("market_regime"),
        "action_bias": observation.get("action_bias"),
        "confidence_0_to_1": observation.get("confidence_0_to_1"),
        "edge_assessment_bps": observation.get("edge_assessment_bps"),
        "required_fields_count": len(schema_def.get("required_fields") or []),
        "shadow_candidate_ready": shadow_issue_ok,
        "lease_emit_allowed_now": False,
        "decision_lease_emitted": False,
    }

    warning_flags = []
    warning_flags.extend(preflight.get("warning_flags") or [])
    warning_flags.extend(schema.get("warning_flags") or [])
    warning_flags = uniq(warning_flags)

    if not shadow_issue_ok:
        shadow_issue_state = "decision_lease_shadow_candidate_blocked"
        allow_progress = False
        recommended_action = "inspect_decision_lease_shadow_candidate_failures"
    elif warning_flags:
        shadow_issue_state = "decision_lease_shadow_candidate_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i2c_shadow_audit"
    else:
        shadow_issue_state = "decision_lease_shadow_candidate_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i2c_shadow_audit"

    report = {
        "shadow_issue_type": STEM,
        "shadow_issue_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I2-B",
        "shadow_issue_ok": shadow_issue_ok,
        "source_refs": {
            "decision_lease_preflight_path": str(PREFLIGHT_PATH),
            "decision_lease_schema_path": str(SCHEMA_PATH),
            "governed_decision_path": str(GOV_PATH),
        },
        "request_summary": {
            "provider_target": ((governed.get("request_summary") or {}).get("provider_target")),
            "model_name": ((governed.get("request_summary") or {}).get("model_name")),
            "selected_ai_tier": ((governed.get("request_summary") or {}).get("selected_ai_tier")),
            "route_plan": ((governed.get("request_summary") or {}).get("route_plan")),
        },
        "shadow_candidate": shadow_candidate,
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not shadow_issue_ok else [],
        "shadow_issue_state": shadow_issue_state,
        "allow_progress_to_i2c_shadow_audit": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I2-B decision lease shadow candidate built. A candidate execution lease shape now exists in shadow-only mode, but no live lease has been emitted.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()

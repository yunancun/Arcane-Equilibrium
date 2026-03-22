#!/usr/bin/env python3
import json
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
PREFLIGHT_PATH = BASE / "bybit_decision_lease_preflight_latest.json"
SHADOW_PATH = BASE / "bybit_decision_lease_shadow_issue_latest.json"
SCHEMA_PATH = BASE / "bybit_decision_lease_schema_latest.json"

STEM = "bybit_decision_lease_consume_policy"


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def uniq(items: List[str]) -> List[str]:
    return list(dict.fromkeys(items))


def save_report(obj: Dict[str, Any]) -> None:
    latest = BASE / f"{STEM}_latest.json"
    dated = BASE / f"{STEM}_{obj['ts_ms']}.json"
    latest.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


def main() -> None:
    now_ms = int(time.time() * 1000)

    preflight = read_json(PREFLIGHT_PATH)
    shadow = read_json(SHADOW_PATH)
    schema = read_json(SCHEMA_PATH)

    timing = preflight.get("issue_timing_profile") or {}
    candidate = shadow.get("shadow_candidate") or {}
    schema_runtime = schema.get("schema_runtime_view") or {}

    issue_ts_ms = int(candidate.get("issue_ts_ms") or 0)
    expires_ts_ms = int(candidate.get("expires_ts_ms") or 0)
    ttl_ms = int(candidate.get("ttl_ms") or 0)
    recommended_consume_before_ts_ms = int(candidate.get("recommended_consume_before_ts_ms") or 0)

    expected_issue_to_consume_ms = int(timing.get("expected_issue_to_consume_ms") or 0)
    freshness_grace_ms = int(timing.get("freshness_grace_ms") or 0)
    consume_slack_ms = int(timing.get("consume_slack_ms") or 0)

    simulated_consume_ts_ms = issue_ts_ms + expected_issue_to_consume_ms

    simulated_before_expiry = simulated_consume_ts_ms < expires_ts_ms
    simulated_within_recommended_window = (
        simulated_consume_ts_ms <= recommended_consume_before_ts_ms
        if recommended_consume_before_ts_ms > 0 else False
    )
    simulated_age_ms = simulated_consume_ts_ms - issue_ts_ms
    simulated_freshness_ok = simulated_age_ms <= freshness_grace_ms

    now_before_expiry = now_ms < expires_ts_ms
    now_within_recommended_window = (
        now_ms <= recommended_consume_before_ts_ms
        if recommended_consume_before_ts_ms > 0 else False
    )
    now_age_ms = now_ms - issue_ts_ms
    now_freshness_ok = now_age_ms <= freshness_grace_ms

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("preflight_ok", preflight.get("preflight_ok") is True, preflight.get("preflight_ok"))
    add("shadow_issue_ok", shadow.get("shadow_issue_ok") is True, shadow.get("shadow_issue_ok"))
    add("shadow_mode_only", candidate.get("lease_mode") == "shadow_only", candidate.get("lease_mode"))
    add("lease_emit_allowed_now_false", candidate.get("lease_emit_allowed_now") is False, candidate.get("lease_emit_allowed_now"))
    add("decision_lease_emitted_false", candidate.get("decision_lease_emitted") is False, candidate.get("decision_lease_emitted"))
    add("schema_only_mode_true", schema_runtime.get("schema_only_mode") is True, schema_runtime.get("schema_only_mode"))
    add("ttl_positive", ttl_ms > 0, ttl_ms)
    add("simulated_before_expiry", simulated_before_expiry, {"simulated_consume_ts_ms": simulated_consume_ts_ms, "expires_ts_ms": expires_ts_ms})
    add("simulated_within_recommended_window", simulated_within_recommended_window, {
        "simulated_consume_ts_ms": simulated_consume_ts_ms,
        "recommended_consume_before_ts_ms": recommended_consume_before_ts_ms,
    })

    hard_fail_names = {
        "preflight_ok",
        "shadow_issue_ok",
        "shadow_mode_only",
        "lease_emit_allowed_now_false",
        "decision_lease_emitted_false",
        "schema_only_mode_true",
        "ttl_positive",
        "simulated_before_expiry",
        "simulated_within_recommended_window",
    }

    policy_ok = not any(name in hard_fail_names for name in failed_checks)

    warning_flags: List[str] = []
    warning_flags.extend(preflight.get("warning_flags") or [])
    warning_flags.extend(shadow.get("warning_flags") or [])

    if not simulated_freshness_ok:
        warning_flags.append("simulated_consume_exceeds_freshness_grace")
    if not now_before_expiry:
        warning_flags.append("consume_now_would_be_expired")
    if not now_within_recommended_window:
        warning_flags.append("consume_now_outside_recommended_window")
    if not now_freshness_ok:
        warning_flags.append("consume_now_exceeds_freshness_grace")
    if ttl_ms <= consume_slack_ms:
        warning_flags.append("lease_ttl_too_close_to_consume_slack")

    warning_flags = uniq(warning_flags)

    if not policy_ok:
        policy_state = "decision_lease_consume_policy_blocked"
        allow_progress = False
        recommended_action = "inspect_i3a_consume_policy_failures"
    elif warning_flags:
        policy_state = "decision_lease_consume_policy_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i3b_consume_gate"
    else:
        policy_state = "decision_lease_consume_policy_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i3b_consume_gate"

    report = {
        "policy_type": STEM,
        "policy_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I3-A",
        "policy_ok": policy_ok,
        "source_refs": {
            "decision_lease_preflight_path": str(PREFLIGHT_PATH),
            "decision_lease_shadow_issue_path": str(SHADOW_PATH),
            "decision_lease_schema_path": str(SCHEMA_PATH),
        },
        "request_summary": {
            "provider_target": ((shadow.get("request_summary") or {}).get("provider_target")),
            "model_name": ((shadow.get("request_summary") or {}).get("model_name")),
            "selected_ai_tier": ((shadow.get("request_summary") or {}).get("selected_ai_tier")),
            "route_plan": ((shadow.get("request_summary") or {}).get("route_plan")),
        },
        "consume_policy_view": {
            "lease_mode": candidate.get("lease_mode"),
            "issue_ts_ms": issue_ts_ms,
            "expires_ts_ms": expires_ts_ms,
            "ttl_ms": ttl_ms,
            "recommended_consume_before_ts_ms": recommended_consume_before_ts_ms,
            "expected_issue_to_consume_ms": expected_issue_to_consume_ms,
            "freshness_grace_ms": freshness_grace_ms,
            "consume_slack_ms": consume_slack_ms,
            "simulated_consume_ts_ms": simulated_consume_ts_ms,
            "simulated_before_expiry": simulated_before_expiry,
            "simulated_within_recommended_window": simulated_within_recommended_window,
            "simulated_age_ms": simulated_age_ms,
            "simulated_freshness_ok": simulated_freshness_ok,
            "now_ts_ms": now_ms,
            "now_before_expiry": now_before_expiry,
            "now_within_recommended_window": now_within_recommended_window,
            "now_age_ms": now_age_ms,
            "now_freshness_ok": now_freshness_ok,
            "consume_mode": "shadow_simulated_then_observe_now",
        },
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not policy_ok else [],
        "policy_state": policy_state,
        "allow_progress_to_i3b_consume_gate": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I3-A consume policy complete. This stage evaluates whether the shadow lease would be consumable under intended runtime timing, while separately observing whether immediate manual consumption would now still be valid.",
    }
    save_report(report)


if __name__ == "__main__":
    main()

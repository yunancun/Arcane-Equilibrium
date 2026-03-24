#!/usr/bin/env python3
import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
INV_PATH = BASE / "bybit_ai_invocation_attempt_latest.json"
I2_PATH = BASE / "bybit_decision_lease_shadow_issue_latest.json"
I3_PATH = BASE / "bybit_decision_lease_consume_gate_latest.json"
I4_PATH = BASE / "bybit_decision_lease_replay_final_audit_latest.json"

STEM = "bybit_decision_lease_friction_metrics"


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

    inv = read_json(INV_PATH)
    i2 = read_json(I2_PATH)
    i3 = read_json(I3_PATH)
    i4 = read_json(I4_PATH)

    request_summary = inv.get("request_summary") or {}
    transport = inv.get("transport_summary") or {}
    usage = (inv.get("response_extract") or {}).get("usage_summary") or {}
    consume_decision = i3.get("consume_decision") or {}
    shadow_candidate = i2.get("shadow_candidate") or {}
    replay_summary = i4.get("audit_summary") or {}

    latency_ms = int((inv.get("attempt_result") or {}).get("latency_ms") or 0)
    ttl_ms = int(shadow_candidate.get("ttl_ms") or 0)
    consume_slack_ms = int(shadow_candidate.get("consume_slack_ms") or 0)
    simulated_headroom_ms = int(consume_decision.get("headroom_remaining_at_simulated_ms") or 0)
    now_headroom_ms = int(consume_decision.get("headroom_remaining_if_now_ms") or 0)

    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    reasoning_tokens = int((usage.get("output_tokens_details") or {}).get("reasoning_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or (input_tokens + output_tokens))

    ttl_to_latency_ratio = round(ttl_ms / latency_ms, 4) if latency_ms > 0 else None
    simulated_headroom_ratio = round(simulated_headroom_ms / ttl_ms, 4) if ttl_ms > 0 else None
    slack_to_ttl_ratio = round(consume_slack_ms / ttl_ms, 4) if ttl_ms > 0 else None

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("invocation_json_ready", request_summary.get("provider_target") is not None, request_summary.get("provider_target"))
    add("shadow_issue_present", i2.get("shadow_issue_ok") is True, i2.get("shadow_issue_ok"))
    add("consume_gate_present", i3.get("gate_ok") is True, i3.get("gate_ok"))
    add("replay_audit_present", i4.get("overall_ok") is True, i4.get("overall_ok"))
    add("ttl_positive", ttl_ms > 0, ttl_ms)
    add("latency_positive", latency_ms > 0, latency_ms)
    add("consume_slack_positive", consume_slack_ms > 0, consume_slack_ms)
    add("simulated_headroom_positive", simulated_headroom_ms > 0, simulated_headroom_ms)
    add("shadow_replay_only", replay_summary.get("shadow_replay_only") is True, replay_summary.get("shadow_replay_only"))

    hard_fail_names = {
        "invocation_json_ready",
        "shadow_issue_present",
        "consume_gate_present",
        "replay_audit_present",
        "ttl_positive",
        "latency_positive",
        "consume_slack_positive",
        "simulated_headroom_positive",
        "shadow_replay_only",
    }
    metrics_ok = not any(name in hard_fail_names for name in failed_checks)

    warning_flags: List[str] = []
    warning_flags.extend(inv.get("warning_flags") or [])
    warning_flags.extend(i2.get("warning_flags") or [])
    warning_flags.extend(i3.get("warning_flags") or [])
    warning_flags.extend(i4.get("warning_flags") or [])

    if now_headroom_ms <= 0:
        warning_flags.append("lease_now_path_negative_headroom")
    if latency_ms >= 3000:
        warning_flags.append("lease_friction_latency_elevated")
    if ttl_to_latency_ratio is not None and ttl_to_latency_ratio < 2.0:
        warning_flags.append("lease_ttl_latency_ratio_tight")
    if simulated_headroom_ratio is not None and simulated_headroom_ratio < 0.20:
        warning_flags.append("lease_simulated_headroom_ratio_low")

    warning_flags = uniq(warning_flags)

    friction_metrics = {
        "provider_target": request_summary.get("provider_target"),
        "model_name": request_summary.get("model_name"),
        "latency_ms": latency_ms,
        "ttl_ms": ttl_ms,
        "consume_slack_ms": consume_slack_ms,
        "simulated_headroom_ms": simulated_headroom_ms,
        "now_headroom_ms": now_headroom_ms,
        "ttl_to_latency_ratio": ttl_to_latency_ratio,
        "simulated_headroom_ratio": simulated_headroom_ratio,
        "slack_to_ttl_ratio": slack_to_ttl_ratio,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "reasoning_tokens": reasoning_tokens,
        "total_tokens": total_tokens,
        "simulated_before_expiry": consume_decision.get("simulated_before_expiry"),
        "simulated_within_recommended_window": consume_decision.get("simulated_within_recommended_window"),
        "would_pass_if_now": consume_decision.get("would_pass_if_now"),
    }

    if not metrics_ok:
        metrics_state = "decision_lease_friction_metrics_blocked"
        allow_progress = False
        recommended_action = "inspect_i5a_friction_metrics_failures"
    elif warning_flags:
        metrics_state = "decision_lease_friction_metrics_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i5b_adaptive_ttl"
    else:
        metrics_state = "decision_lease_friction_metrics_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i5b_adaptive_ttl"

    report = {
        "metrics_type": STEM,
        "metrics_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I5-A",
        "metrics_ok": metrics_ok,
        "source_refs": {
            "ai_invocation_attempt_path": str(INV_PATH),
            "decision_lease_shadow_issue_path": str(I2_PATH),
            "decision_lease_consume_gate_path": str(I3_PATH),
            "decision_lease_replay_audit_path": str(I4_PATH),
        },
        "request_summary": request_summary,
        "friction_metrics": friction_metrics,
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not metrics_ok else [],
        "metrics_state": metrics_state,
        "allow_progress_to_i5b_adaptive_ttl": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I5-A friction metrics complete. Lease timing is now quantified from live invocation latency, shadow consume timing, and replay-safe shadow flow.",
    }
    save_report(report)


if __name__ == "__main__":
    main()

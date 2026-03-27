#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MODULE_NOTE / 模块说明:
- role / 角色:
  Build I5-B adaptive TTL recommendation for the decision-lease chain.
  为 decision-lease 链构建 I5-B 自适应 TTL 建议。
- no-call semantics / 无调用语义:
  If the upstream cycle is a legal no-call path, keep the current TTL/slack as
  the shadow recommendation instead of blocking on missing latency.
  若上游周期属于合法 no-call 路径，则保持当前 TTL/slack 作为 shadow 建议，
  而不是因为缺少真实延迟而阻塞。
"""

import json
import math
import time
from pathlib import Path
from typing import Any, Dict, List
from bybit_decision_lease_common import read_json_required as read_json, save_report_stem, uniq

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
METRICS_PATH = BASE / "bybit_decision_lease_friction_metrics_latest.json"
I2_PATH = BASE / "bybit_decision_lease_shadow_issue_latest.json"

STEM = "bybit_decision_lease_adaptive_ttl"


def clamp(v: int, lo: int, hi: int) -> int:
    return max(lo, min(v, hi))


def main() -> None:
    now_ms = int(time.time() * 1000)

    metrics = read_json(METRICS_PATH)
    i2 = read_json(I2_PATH)

    fm = metrics.get("friction_metrics") or {}
    candidate = i2.get("shadow_candidate") or {}
    request_summary = metrics.get("request_summary") or i2.get("request_summary") or {}

    current_ttl_ms = int(candidate.get("ttl_ms") or 0)
    consume_slack_ms = int(candidate.get("consume_slack_ms") or 0)
    latency_ms = int(fm.get("latency_ms") or 0)
    simulated_headroom_ms = int(fm.get("simulated_headroom_ms") or 0)

    latency_available = bool(fm.get("latency_available"))
    legal_no_call_path = bool(fm.get("legal_no_call_path")) or (
        request_summary.get("should_call_ai") is False
        or request_summary.get("selected_ai_tier") == "none"
        or request_summary.get("route_plan") == "route_skip"
    )

    ttl_floor_ms = 8000
    ttl_cap_ms = 30000
    freshness_grace_ms = 2000

    recommended_formula_ms = int(math.ceil(
        (latency_ms * 2.0) + consume_slack_ms + freshness_grace_ms
    )) if latency_available else current_ttl_ms

    recommended_ttl_ms = clamp(max(current_ttl_ms, recommended_formula_ms), ttl_floor_ms, ttl_cap_ms)
    recommended_consume_slack_ms = (
        max(1500, int(math.ceil(latency_ms * 0.35)))
        if latency_available else
        consume_slack_ms
    )
    recommended_freshness_grace_ms = freshness_grace_ms

    ttl_delta_ms = recommended_ttl_ms - current_ttl_ms
    ttl_change_required = ttl_delta_ms != 0
    would_reduce_expiry_risk = recommended_ttl_ms >= current_ttl_ms
    shadow_apply_only = True

    checks: List[Dict[str, Any]] = []
    failed_checks: List[str] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})
        if not ok:
            failed_checks.append(name)

    add("metrics_ok", metrics.get("metrics_ok") is True, metrics.get("metrics_ok"))
    add("current_ttl_positive", current_ttl_ms > 0, current_ttl_ms)
    add(
        "latency_positive_or_legal_no_call",
        latency_available or legal_no_call_path,
        {
            "latency_ms": latency_ms,
            "latency_available": latency_available,
            "legal_no_call_path": legal_no_call_path,
        },
    )
    add("recommended_ttl_positive", recommended_ttl_ms > 0, recommended_ttl_ms)
    add("recommended_ttl_gte_current", recommended_ttl_ms >= current_ttl_ms, {"current": current_ttl_ms, "recommended": recommended_ttl_ms})
    add("shadow_apply_only", shadow_apply_only is True, shadow_apply_only)

    hard_fail_names = {
        "metrics_ok",
        "current_ttl_positive",
        "latency_positive_or_legal_no_call",
        "recommended_ttl_positive",
        "recommended_ttl_gte_current",
        "shadow_apply_only",
    }
    decision_ok = not any(name in hard_fail_names for name in failed_checks)

    warning_flags: List[str] = []
    warning_flags.extend(metrics.get("warning_flags") or [])
    warning_flags.append("decision_lease_adaptive_ttl_shadow_only_mode")

    if ttl_change_required:
        warning_flags.append("adaptive_ttl_recommendation_differs_from_current")
    if not latency_available and legal_no_call_path:
        warning_flags.append("adaptive_ttl_uses_current_ttl_under_legal_no_call")
    elif not latency_available:
        warning_flags.append("adaptive_ttl_latency_missing_or_zero")

    warning_flags = uniq(warning_flags)

    adaptive_ttl_decision = {
        "current_ttl_ms": current_ttl_ms,
        "recommended_ttl_ms": recommended_ttl_ms,
        "recommended_formula_ms": recommended_formula_ms,
        "ttl_floor_ms": ttl_floor_ms,
        "ttl_cap_ms": ttl_cap_ms,
        "ttl_delta_ms": ttl_delta_ms,
        "ttl_change_required": ttl_change_required,
        "recommended_consume_slack_ms": recommended_consume_slack_ms,
        "recommended_freshness_grace_ms": recommended_freshness_grace_ms,
        "latency_ms": latency_ms,
        "latency_available": latency_available,
        "legal_no_call_path": legal_no_call_path,
        "no_call_path_accepted": bool(legal_no_call_path and not latency_available),
        "simulated_headroom_ms": simulated_headroom_ms,
        "would_reduce_expiry_risk": would_reduce_expiry_risk,
        "shadow_apply_only": True,
        "live_apply_allowed_now": False,
        "applied_to_runtime": False,
    }

    if not decision_ok:
        decision_state = "decision_lease_adaptive_ttl_blocked"
        allow_progress = False
        recommended_action = "inspect_i5b_adaptive_ttl_failures"
    elif warning_flags:
        decision_state = "decision_lease_adaptive_ttl_ready_soft_warn"
        allow_progress = True
        recommended_action = "may_progress_to_i5c_final_audit"
    else:
        decision_state = "decision_lease_adaptive_ttl_ready"
        allow_progress = True
        recommended_action = "may_progress_to_i5c_final_audit"

    report = {
        "decision_type": STEM,
        "decision_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "I5-B",
        "decision_ok": decision_ok,
        "source_refs": {
            "decision_lease_friction_metrics_path": str(METRICS_PATH),
            "decision_lease_shadow_issue_path": str(I2_PATH),
        },
        "request_summary": request_summary,
        "adaptive_ttl_decision": adaptive_ttl_decision,
        "checks": checks,
        "failed_checks": failed_checks,
        "warning_flags": warning_flags,
        "blocking_reasons": failed_checks if not decision_ok else [],
        "decision_state": decision_state,
        "allow_progress_to_i5c_final_audit": allow_progress,
        "recommended_action": recommended_action,
        "operator_message": "I5-B adaptive TTL complete. A safer TTL and consume-slack recommendation is now computed from measured friction; legal no-call paths keep a shadow recommendation without treating missing latency as a hard failure.",
    }
    save_report_stem(report, BASE, STEM)


if __name__ == "__main__":
    main()

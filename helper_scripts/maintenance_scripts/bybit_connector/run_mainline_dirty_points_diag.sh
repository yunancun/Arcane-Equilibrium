#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

ROOT="$_SRV/program_code/exchange_connectors/bybit_connector"
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"
ENV1="$_SRV/settings/environment_files/trading_services.env"
ENV2="$_SRV/docker_projects/trading_services/.env"

echo "===== A. WARNING STRING -> SCRIPT EMITTERS ====="
for s in \
  provider_pricing_table_not_bound_in_mainline \
  last_call_latency_exceeds_deadline_hint \
  recent_trade_last_price_missing \
  recent_trade_last_ts_missing \
  last_trade_fields_missing \
  runtime_state_reference_old \
  freshness_soft_warning_present
do
  echo
  echo "----- $s -----"
  grep -Rns --exclude-dir='__pycache__' --exclude='*.bak_*' --exclude='*.pyc' "$s" "$ROOT/scripts" || true
done

echo
echo "===== B. CANDIDATE MAINLINE FILES ====="
ls -1 "$ROOT/scripts" | grep -E 'ai_cost|governance_audit|query_budget|model_router|compute_governor|thought_gate|prompt_prep|request_envelope|invocation_attempt|response_check|decision_lease|approval_bridge|authority_aggregator|manual_approval|operator_ack|system_snapshot|decision_packet|observer|runtime_state|failure_policy' | sort || true

echo
echo "===== C. ENV KEYS THAT MAY AFFECT LATENCY / COST / PRICING / DEADLINE ====="
grep -nE 'BYBIT_.*(TIMEOUT|RETRY|BUDGET|TOKEN|PRICE|PRICING|LATENCY|DEADLINE|ROUNDTRIP|FRESH|TTL|SLACK)' "$ENV1" "$ENV2" || true

echo
echo "===== D. LATEST JSON QUICK SNAPSHOT ====="
python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

targets = [
    "bybit_ai_request_envelope_latest.json",
    "bybit_ai_invocation_attempt_latest.json",
    "bybit_ai_prompt_prep_latest.json",
    "bybit_query_budget_policy_latest.json",
    "bybit_query_budget_gate_latest.json",
    "bybit_query_budget_runtime_latest.json",
    "bybit_model_router_policy_latest.json",
    "bybit_model_router_decision_latest.json",
    "bybit_model_router_runtime_latest.json",
    "bybit_compute_governor_policy_latest.json",
    "bybit_compute_governor_gate_latest.json",
    "bybit_compute_governor_runtime_latest.json",
    "bybit_ai_cost_log_latest.json",
    "bybit_ai_governance_audit_latest.json",
    "bybit_ai_cost_governance_final_audit_latest.json",
    "bybit_decision_lease_chapter_summary_latest.json",
    "bybit_decision_lease_chapter_final_audit_latest.json",
]

for name in targets:
    p = base / name
    if not p.exists():
        continue
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"\n--- {name} ---")
        print("read_error =", repr(e))
        continue

    print(f"\n--- {name} ---")
    for key in [
        "policy_state", "gate_state", "runtime_state", "decision_state",
        "summary_state", "handoff_state", "audit_state", "log_state",
        "overall_ok", "policy_ok", "gate_ok", "runtime_ok", "decision_ok",
        "summary_ok", "handoff_ok", "log_ok"
    ]:
        if key in obj:
            print(f"{key} =", obj.get(key))

    if "warning_flags" in obj:
        print("warning_flags =", obj.get("warning_flags"))

    for block_name in [
        "provider_runtime", "request_summary", "budget_context",
        "attempt_result", "response_extract", "runtime_summary",
        "cost_log", "chapter_summary", "audit_summary"
    ]:
        block = obj.get(block_name)
        if isinstance(block, dict):
            interesting = {}
            for k in [
                "provider_target", "model_name",
                "connect_timeout_sec", "read_timeout_sec", "max_retries",
                "ai_daily_budget_usd", "ai_per_call_budget_usd", "max_output_tokens",
                "latency_ms", "response_text_present", "parsed_json_present",
                "pricing_table_bound", "actual_cost_usd", "governed_cost_ceiling_usd",
                "i_chapter_closed", "shadow_control_plane_closed",
                "runtime_still_protected", "ready_for_future_live_design"
            ]:
                if k in block:
                    interesting[k] = block.get(k)
            if interesting:
                print(f"{block_name} =", interesting)

    # cost log deeper extract
    cost_log = obj.get("cost_log") or {}
    if isinstance(cost_log, dict):
        acct = cost_log.get("cost_accounting_summary") or {}
        budget = cost_log.get("budget_summary") or {}
        perf = cost_log.get("performance_summary") or {}
        usage = cost_log.get("usage_summary") or {}
        if acct or budget or perf or usage:
            print("usage_summary =", {
                k: usage.get(k) for k in ["input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"]
                if k in usage
            })
            print("performance_summary =", {
                k: perf.get(k) for k in ["latency_ms", "within_timeout_hint"]
                if k in perf
            })
            print("budget_summary =", {
                k: budget.get(k) for k in ["ai_daily_budget_usd", "ai_per_call_budget_usd", "governed_cost_ceiling_usd"]
                if k in budget
            })
            print("cost_accounting_summary =", {
                k: acct.get(k) for k in ["pricing_table_bound", "actual_cost_usd"]
                if k in acct
            })
PY

echo
echo "===== E. FILES CONTAINING FRESHNESS / LAST-TRADE FIELDS ====="
grep -Rns --exclude-dir='__pycache__' --exclude='*.bak_*' --exclude='*.pyc' -E \
'recent_trade_last_price|recent_trade_last_ts|last_trade_fields|freshness_soft_warning|runtime_state_reference_old|payload_time_summary|within_timeout_hint|pricing_table_bound|actual_cost_usd' \
"$ROOT/scripts" || true

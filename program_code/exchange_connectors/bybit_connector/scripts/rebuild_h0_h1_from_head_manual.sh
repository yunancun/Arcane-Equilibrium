#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

run_py() {
  local s="$1"
  if [ -f "$s" ]; then
    echo
    echo "RUN $s"
    ./scripts/run_with_trading_env.sh python3 "$s"
  else
    echo "SKIP missing $s"
  fi
}

echo "===== 0) REFRESH REAL H0 FINAL AUDIT ====="
run_py scripts/bybit_local_judgment_final_audit.py
run_py scripts/bybit_local_judgment_final_audit_contract_check.py

echo
echo "===== 1) REBUILD H1 FROM HEAD ====="
for s in \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_input_contract_check.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_thought_gate_policy_contract_check.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_thought_gate_decision_builder.py \
  scripts/bybit_thought_gate_decision_contract_check.py \
  scripts/bybit_ai_route_selector_builder.py \
  scripts/bybit_ai_prompt_prep_builder.py \
  scripts/bybit_ai_prompt_prep_contract_check.py \
  scripts/bybit_ai_prompt_prep_tighten.py \
  scripts/bybit_ai_request_envelope_builder.py \
  scripts/bybit_ai_request_envelope_contract_check.py \
  scripts/bybit_ai_invocation_attempt_builder.py \
  scripts/bybit_ai_invocation_attempt_contract_check.py \
  scripts/bybit_ai_response_check_builder.py \
  scripts/bybit_ai_response_check_contract_check.py \
  scripts/bybit_ai_governed_decision_builder.py \
  scripts/bybit_ai_governed_decision_contract_check.py \
  scripts/bybit_thought_gate_acceptance_suite.py \
  scripts/bybit_thought_gate_regression_summary.py \
  scripts/bybit_thought_gate_handoff.py \
  scripts/bybit_thought_gate_final_audit.py \
  scripts/bybit_thought_gate_contract_check.py
do
  run_py "$s"
done

echo
echo "===== 2) H1 TRUTH CHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

inp = read("bybit_thought_gate_input_latest.json")
pol = read("bybit_thought_gate_policy_latest.json")
env = read("bybit_ai_request_envelope_latest.json")
inv = read("bybit_ai_invocation_attempt_latest.json")
fin = read("bybit_thought_gate_final_audit_latest.json")

print("H1 input_state =", inp.get("input_state"))
print("H1 operator_flags =", inp.get("operator_flags"))
print("H1 policy_state =", pol.get("policy_state"))
print("H1 policy_warning_flags =", pol.get("warning_flags"))
print("H1 prep_state =", env.get("prep_state") or (env.get("request_summary") or {}).get("prep_state"))
print("H1 should_call_ai =", env.get("should_call_ai") if "should_call_ai" in env else (env.get("request_summary") or {}).get("should_call_ai"))
print("H1 provider_target =", env.get("provider_target") or (env.get("request_summary") or {}).get("provider_target"))
print("H1 model_name =", env.get("model_name") or (env.get("request_summary") or {}).get("model_name"))
print("H1 invocation_state =", inv.get("invocation_state"))
print("H1 final overall_ok =", fin.get("overall_ok"))
print("H1 final audit_summary =", fin.get("audit_summary"))
PY

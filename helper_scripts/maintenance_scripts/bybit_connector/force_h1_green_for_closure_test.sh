#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector

echo "===== 0) TEMP RELAX H1/H2 GATES FOR CHAPTER-CLOSURE TEST ====="

export BYBIT_THOUGHT_GATE_STANDARD_MAX_EXPECTED_ROUNDTRIP_MS=6000
export BYBIT_THOUGHT_GATE_LIGHT_MAX_EXPECTED_ROUNDTRIP_MS=2500

export BYBIT_H2_MIN_VOLATILITY_BPS=3
export BYBIT_H2_TRIGGER_SCORE_THRESHOLD=45
export BYBIT_H2_MIN_MARKET_QUALITY_SCORE=70

echo "BYBIT_THOUGHT_GATE_STANDARD_MAX_EXPECTED_ROUNDTRIP_MS=$BYBIT_THOUGHT_GATE_STANDARD_MAX_EXPECTED_ROUNDTRIP_MS"
echo "BYBIT_THOUGHT_GATE_LIGHT_MAX_EXPECTED_ROUNDTRIP_MS=$BYBIT_THOUGHT_GATE_LIGHT_MAX_EXPECTED_ROUNDTRIP_MS"
echo "BYBIT_H2_MIN_VOLATILITY_BPS=$BYBIT_H2_MIN_VOLATILITY_BPS"
echo "BYBIT_H2_TRIGGER_SCORE_THRESHOLD=$BYBIT_H2_TRIGGER_SCORE_THRESHOLD"
echo "BYBIT_H2_MIN_MARKET_QUALITY_SCORE=$BYBIT_H2_MIN_MARKET_QUALITY_SCORE"

echo
echo "===== 1) REBUILD H1 ONLY UNDER TEMP OVERRIDES ====="
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_input_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_input_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_policy_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_policy_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_local_trigger_model_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_local_trigger_model_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_decision_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_decision_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_route_selector_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_route_selector_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_prompt_prep_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_prompt_prep_tighten.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_prompt_prep_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_request_envelope_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_request_envelope_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_invocation_attempt_builder.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_invocation_attempt_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_response_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_response_check_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_governed_decision.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_ai_governed_decision_contract_check.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_acceptance_suite.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_regression_summary.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_handoff.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_final_audit.py
./scripts/run_with_trading_env.sh python3 scripts/bybit_thought_gate_contract_check.py

echo
echo "===== 2) H1 QUICK TRUTH ====="
python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

pol = read("bybit_thought_gate_policy_latest.json")
trg = json.loads(Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/trigger_model/bybit_local_trigger_model_latest.json").read_text(encoding="utf-8"))
dec = read("bybit_thought_gate_decision_latest.json")
env = read("bybit_ai_request_envelope_latest.json")
inv = read("bybit_ai_invocation_attempt_latest.json")
fin = read("bybit_thought_gate_final_audit_latest.json")

req = env.get("request_summary") or {}

print("policy_state =", pol.get("policy_state"))
print("policy_blocking_reasons =", pol.get("blocking_reasons"))
print("trigger_state =", trg.get("trigger_state"))
print("should_trigger_ai_review =", trg.get("should_trigger_ai_review"))
print("suggested_ai_tier =", trg.get("suggested_ai_tier"))
print("decision_state =", dec.get("decision_state"))
print("selected_ai_tier =", (dec.get("decision_result") or {}).get("selected_ai_tier"))
print("should_call_ai =", (dec.get("decision_result") or {}).get("should_call_ai"))
print("request provider_target =", req.get("provider_target"))
print("request model_name =", req.get("model_name"))
print("invocation_state =", inv.get("invocation_state"))
print("final overall_ok =", fin.get("overall_ok"))
print("final audit_summary =", fin.get("audit_summary"))
PY

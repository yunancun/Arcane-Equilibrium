#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector

python3 -m py_compile \
  scripts/bybit_h1_report_utils.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_thought_gate_decision_builder.py \
  scripts/bybit_ai_prompt_prep_builder.py \
  scripts/bybit_ai_route_selector_builder.py \
  scripts/bybit_ai_route_selector_contract_check.py \
  scripts/bybit_ai_request_envelope_builder.py \
  scripts/bybit_ai_invocation_attempt_builder.py \
  scripts/bybit_ai_response_check.py \
  scripts/bybit_ai_response_check_contract_check.py \
  scripts/bybit_ai_governed_decision.py \
  scripts/bybit_ai_governed_decision_contract_check.py \
  scripts/bybit_thought_gate_acceptance_suite.py \
  scripts/bybit_thought_gate_regression_summary.py \
  scripts/bybit_thought_gate_handoff.py \
  scripts/bybit_thought_gate_final_audit.py \
  scripts/bybit_thought_gate_contract_check.py

./scripts/run_with_trading_env.sh bash -lc '
cd $_SRV/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_thought_gate_input_builder.py
python3 scripts/bybit_thought_gate_policy_builder.py
python3 scripts/bybit_local_trigger_model_builder.py
python3 scripts/bybit_thought_gate_decision_builder.py
python3 scripts/bybit_ai_prompt_prep_builder.py
python3 scripts/bybit_ai_route_selector_builder.py
python3 scripts/bybit_ai_route_selector_contract_check.py
python3 scripts/bybit_ai_request_envelope_builder.py
python3 scripts/bybit_ai_invocation_attempt_builder.py

python3 scripts/bybit_ai_response_check.py
python3 scripts/bybit_ai_response_check_contract_check.py
python3 scripts/bybit_ai_governed_decision.py
python3 scripts/bybit_ai_governed_decision_contract_check.py
python3 scripts/bybit_thought_gate_acceptance_suite.py
python3 scripts/bybit_thought_gate_regression_summary.py
python3 scripts/bybit_thought_gate_handoff.py
python3 scripts/bybit_thought_gate_final_audit.py
python3 scripts/bybit_thought_gate_contract_check.py
'

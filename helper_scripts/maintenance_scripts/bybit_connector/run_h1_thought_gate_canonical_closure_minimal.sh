#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/exchange_connectors/bybit_connector/scripts:$ROOT/program_code/ai_agents/bybit_thought_gate"

python3 -m py_compile \
  program_code/exchange_connectors/bybit_connector/scripts/bybit_h1_report_utils.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_response_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_response_check_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_governed_decision.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_governed_decision_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_acceptance_suite.py \
  program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_regression_summary.py \
  program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_handoff.py \
  program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_final_audit.py \
  program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_contract_check.py

python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_response_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_response_check_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_governed_decision.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_governed_decision_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_acceptance_suite.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_regression_summary.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_handoff.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_final_audit.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_thought_gate_contract_check.py

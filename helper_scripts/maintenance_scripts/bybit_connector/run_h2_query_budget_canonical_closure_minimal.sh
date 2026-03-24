#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/exchange_connectors/bybit_connector/scripts:$ROOT/program_code/ai_agents/bybit_thought_gate"

python3 -m py_compile \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_policy.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_policy_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_runtime.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_runtime_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_final_audit.py \
  program_code/ai_agents/bybit_thought_gate/bybit_query_budget_final_audit_contract_check.py

python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_policy.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_policy_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_gate_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_runtime.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_runtime_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_final_audit.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_query_budget_final_audit_contract_check.py

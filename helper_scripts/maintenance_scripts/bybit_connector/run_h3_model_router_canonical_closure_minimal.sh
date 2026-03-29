#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/ai_agents/bybit_thought_gate"

python3 -m py_compile \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy.py \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision.py \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_runtime.py \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_runtime_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_model_router_final_audit.py

python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_policy_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_decision_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_runtime.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_runtime_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_model_router_final_audit.py

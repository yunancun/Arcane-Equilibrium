#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/exchange_connectors/bybit_connector/scripts:$ROOT/program_code/ai_agents/bybit_thought_gate"

python3 -m py_compile \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_governance_audit.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_governance_audit_contract_check.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_governance_final_audit.py \
  program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_governance_contract_check.py

python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_log_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_governance_audit.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_governance_audit_contract_check.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_governance_final_audit.py
python3 program_code/ai_agents/bybit_thought_gate/bybit_ai_cost_governance_contract_check.py

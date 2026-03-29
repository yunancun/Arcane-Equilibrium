#!/usr/bin/env bash
set -euo pipefail

# Canonical I3 runner / I3 规范 runner
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/ai_agents/bybit_thought_gate:$ROOT/program_code/trade_executor/bybit_decision_lease"

BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 -m py_compile \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_policy.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_policy_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_gate.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_gate_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_final_audit.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_contract_check.py

python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_policy.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_policy_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_gate.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_gate_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_final_audit.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_consume_contract_check.py

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

policy = json.loads((base / "bybit_decision_lease_consume_policy_latest.json").read_text(encoding="utf-8"))
gate = json.loads((base / "bybit_decision_lease_consume_gate_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_consume_final_audit_latest.json").read_text(encoding="utf-8"))

decision = gate.get("consume_decision") or {}
summary = audit.get("audit_summary") or {}

print("===== I3 CANONICAL CLEAN STATUS =====")
print("policy_state =", policy.get("policy_state"))
print("gate_state =", gate.get("gate_state"))
print("audit_state =", audit.get("audit_state"))
print("i3_stage_closed =", summary.get("i3_stage_closed"))
print("ready_for_i4 =", summary.get("ready_for_i4"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("shadow_consume_only =", summary.get("shadow_consume_only"))
print("consume_gate_open_live =", summary.get("consume_gate_open_live"))
print("decision_lease_consumed =", summary.get("decision_lease_consumed"))
print("headroom_remaining_at_simulated_ms =", decision.get("headroom_remaining_at_simulated_ms"))
print("headroom_remaining_if_now_ms =", decision.get("headroom_remaining_if_now_ms"))
print("warning_flags =", audit.get("warning_flags"))
PY

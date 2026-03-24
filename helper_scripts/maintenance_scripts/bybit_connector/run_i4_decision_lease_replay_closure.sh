#!/usr/bin/env bash
set -euo pipefail

# Canonical I4 runner / I4 规范 runner
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/exchange_connectors/bybit_connector/scripts:$ROOT/program_code/ai_agents/bybit_thought_gate:$ROOT/program_code/trade_executor/bybit_decision_lease"

BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 -m py_compile \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_policy.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_policy_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_guard.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_guard_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_final_audit.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_contract_check.py

python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_policy.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_policy_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_guard.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_guard_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_final_audit.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_replay_contract_check.py

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

policy = json.loads((base / "bybit_decision_lease_replay_policy_latest.json").read_text(encoding="utf-8"))
guard = json.loads((base / "bybit_decision_lease_replay_guard_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_replay_final_audit_latest.json").read_text(encoding="utf-8"))

gd = guard.get("guard_decision") or {}
summary = audit.get("audit_summary") or {}

print("===== I4 CANONICAL CLEAN STATUS =====")
print("policy_state =", policy.get("policy_state"))
print("gate_state =", guard.get("gate_state"))
print("audit_state =", audit.get("audit_state"))
print("i4_stage_closed =", summary.get("i4_stage_closed"))
print("ready_for_i5 =", summary.get("ready_for_i5"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("shadow_replay_only =", summary.get("shadow_replay_only"))
print("duplicate_replay_rejected =", summary.get("duplicate_replay_rejected"))
print("live_revoke_active =", summary.get("live_revoke_active"))
print("live_replay_block_active =", summary.get("live_replay_block_active"))
print("first_attempt =", (gd.get("first_attempt") or {}).get("result"))
print("second_attempt =", (gd.get("second_attempt") or {}).get("result"))
print("warning_flags =", audit.get("warning_flags"))
PY

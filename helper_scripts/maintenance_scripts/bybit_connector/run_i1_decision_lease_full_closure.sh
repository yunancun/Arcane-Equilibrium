#!/usr/bin/env bash
set -euo pipefail

# Canonical I1 runner / I1 规范 runner
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/ai_agents/bybit_thought_gate:$ROOT/program_code/trade_executor/bybit_decision_lease"

BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 -m py_compile \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_schema.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_schema_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_final_audit.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_contract_check.py

python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_schema.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_schema_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_final_audit.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_contract_check.py

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

schema = json.loads((base / "bybit_decision_lease_schema_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_final_audit_latest.json").read_text(encoding="utf-8"))

summary = audit.get("audit_summary") or {}

print("===== I1 CANONICAL CLEAN STATUS =====")
print("schema_state =", schema.get("schema_state"))
print("audit_state =", audit.get("audit_state"))
print("i1_stage_closed =", summary.get("i1_stage_closed"))
print("ready_for_future_i_stage =", summary.get("ready_for_future_i_stage"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("lease_emit_allowed_now =", summary.get("lease_emit_allowed_now"))
print("decision_lease_emitted =", summary.get("decision_lease_emitted"))
print("warning_flags =", audit.get("warning_flags"))
PY

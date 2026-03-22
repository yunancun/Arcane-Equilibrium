#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_query_budget_policy.py
python3 scripts/bybit_query_budget_policy_contract_check.py

python3 scripts/bybit_query_budget_gate.py
python3 scripts/bybit_query_budget_gate_contract_check.py

python3 scripts/bybit_query_budget_runtime.py
python3 scripts/bybit_query_budget_runtime_contract_check.py

python3 scripts/bybit_query_budget_final_audit.py
python3 scripts/bybit_query_budget_final_audit_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

a = json.loads((base / "bybit_query_budget_policy_latest.json").read_text(encoding="utf-8"))
b = json.loads((base / "bybit_query_budget_gate_latest.json").read_text(encoding="utf-8"))
c = json.loads((base / "bybit_query_budget_runtime_latest.json").read_text(encoding="utf-8"))
d = json.loads((base / "bybit_query_budget_final_audit_latest.json").read_text(encoding="utf-8"))

print("===== H2 FINAL CLEAN STATUS =====")
print("policy_state =", a.get("policy_state"))
print("gate_state =", b.get("gate_state"))
print("runtime_state =", c.get("runtime_state"))
print("audit_state =", d.get("audit_state"))
print("h2_stage_closed =", (d.get("audit_summary") or {}).get("h2_stage_closed"))
print("ready_for_h3 =", (d.get("audit_summary") or {}).get("ready_for_h3"))
print("runtime_still_protected =", (d.get("audit_summary") or {}).get("runtime_still_protected"))
print("warning_flags =", d.get("warning_flags"))
PY

#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_compute_governor_policy.py
python3 scripts/bybit_compute_governor_policy_contract_check.py

python3 scripts/bybit_compute_governor_gate.py
python3 scripts/bybit_compute_governor_gate_contract_check.py

python3 scripts/bybit_compute_governor_runtime.py
python3 scripts/bybit_compute_governor_runtime_contract_check.py

python3 scripts/bybit_compute_governor_final_audit.py
python3 scripts/bybit_compute_governor_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

policy = json.loads((base / "bybit_compute_governor_policy_latest.json").read_text(encoding="utf-8"))
gate = json.loads((base / "bybit_compute_governor_gate_latest.json").read_text(encoding="utf-8"))
runtime = json.loads((base / "bybit_compute_governor_runtime_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_compute_governor_final_audit_latest.json").read_text(encoding="utf-8"))

print("===== H4 FINAL CLEAN STATUS =====")
print("policy_state =", policy.get("policy_state"))
print("gate_state =", gate.get("gate_state"))
print("runtime_state =", runtime.get("runtime_state"))
print("audit_state =", audit.get("audit_state"))
print("h4_stage_closed =", (audit.get("audit_summary") or {}).get("h4_stage_closed"))
print("ready_for_h5 =", (audit.get("audit_summary") or {}).get("ready_for_h5"))
print("runtime_still_protected =", (audit.get("audit_summary") or {}).get("runtime_still_protected"))
print("warning_flags =", audit.get("warning_flags"))
PY

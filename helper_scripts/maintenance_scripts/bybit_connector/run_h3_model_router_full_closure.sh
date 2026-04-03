#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd $_SRV/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_model_router_policy.py
python3 scripts/bybit_model_router_policy_contract_check.py

python3 scripts/bybit_model_router_decision.py
python3 scripts/bybit_model_router_decision_contract_check.py

python3 scripts/bybit_model_router_runtime.py
python3 scripts/bybit_model_router_runtime_contract_check.py

python3 scripts/bybit_model_router_final_audit.py
python3 scripts/bybit_model_router_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

policy = json.loads((base / "bybit_model_router_policy_latest.json").read_text(encoding="utf-8"))
decision = json.loads((base / "bybit_model_router_decision_latest.json").read_text(encoding="utf-8"))
runtime = json.loads((base / "bybit_model_router_runtime_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_model_router_final_audit_latest.json").read_text(encoding="utf-8"))

print("===== H3 FINAL CLEAN STATUS =====")
print("policy_state =", policy.get("policy_state"))
print("decision_state =", decision.get("decision_state"))
print("runtime_state =", runtime.get("runtime_state"))
print("audit_state =", audit.get("audit_state"))
print("h3_stage_closed =", (audit.get("audit_summary") or {}).get("h3_stage_closed"))
print("ready_for_h4 =", (audit.get("audit_summary") or {}).get("ready_for_h4"))
print("runtime_still_protected =", (audit.get("audit_summary") or {}).get("runtime_still_protected"))
print("warning_flags =", audit.get("warning_flags"))
PY

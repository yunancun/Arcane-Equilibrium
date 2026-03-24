#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_ai_cost_log.py
python3 scripts/bybit_ai_cost_log_contract_check.py

python3 scripts/bybit_ai_governance_audit.py
python3 scripts/bybit_ai_governance_audit_contract_check.py

python3 scripts/bybit_ai_cost_governance_final_audit.py
python3 scripts/bybit_ai_cost_governance_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

print("===== H5 FINAL CLEAN STATUS =====")
print("log_state =", log.get("log_state"))
print("audit_state =", audit.get("audit_state"))
print("final_state =", final_audit.get("audit_state"))
print("h5_stage_closed =", (final_audit.get("audit_summary") or {}).get("h5_stage_closed"))
print("h_chapter_closed =", (final_audit.get("audit_summary") or {}).get("h_chapter_closed"))
print("ready_for_i1 =", (final_audit.get("audit_summary") or {}).get("ready_for_i1"))
print("runtime_still_protected =", (final_audit.get("audit_summary") or {}).get("runtime_still_protected"))
print("warning_flags =", final_audit.get("warning_flags"))
PY

#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_decision_lease_schema.py
python3 scripts/bybit_decision_lease_schema_contract_check.py

python3 scripts/bybit_decision_lease_final_audit.py
python3 scripts/bybit_decision_lease_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

schema = json.loads((base / "bybit_decision_lease_schema_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_final_audit_latest.json").read_text(encoding="utf-8"))

runtime = schema.get("schema_runtime_view") or {}
summary = audit.get("audit_summary") or {}

print("===== I1 FINAL CLEAN STATUS =====")
print("schema_state =", schema.get("schema_state"))
print("audit_state =", audit.get("audit_state"))
print("i1_stage_closed =", summary.get("i1_stage_closed"))
print("ready_for_future_i_stage =", summary.get("ready_for_future_i_stage"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("lease_emit_allowed_now =", summary.get("lease_emit_allowed_now"))
print("decision_lease_emitted =", summary.get("decision_lease_emitted"))
print("warning_flags =", audit.get("warning_flags"))
PY

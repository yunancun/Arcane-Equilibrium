#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_decision_lease_consume_policy.py
python3 scripts/bybit_decision_lease_consume_policy_contract_check.py

python3 scripts/bybit_decision_lease_consume_gate.py
python3 scripts/bybit_decision_lease_consume_gate_contract_check.py

python3 scripts/bybit_decision_lease_consume_final_audit.py
python3 scripts/bybit_decision_lease_consume_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

policy = json.loads((base / "bybit_decision_lease_consume_policy_latest.json").read_text(encoding="utf-8"))
gate = json.loads((base / "bybit_decision_lease_consume_gate_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_consume_final_audit_latest.json").read_text(encoding="utf-8"))

view = policy.get("consume_policy_view") or {}
decision = gate.get("consume_decision") or {}
summary = audit.get("audit_summary") or {}

print("===== I3 FINAL CLEAN STATUS =====")
print("policy_state =", policy.get("policy_state"))
print("gate_state =", gate.get("gate_state"))
print("audit_state =", audit.get("audit_state"))
print("i3_stage_closed =", summary.get("i3_stage_closed"))
print("ready_for_i4 =", summary.get("ready_for_i4"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("shadow_consume_only =", summary.get("shadow_consume_only"))
print("consume_gate_open_live =", summary.get("consume_gate_open_live"))
print("decision_lease_consumed =", summary.get("decision_lease_consumed"))
print("simulated_consume_ts_ms =", view.get("simulated_consume_ts_ms"))
print("simulated_before_expiry =", view.get("simulated_before_expiry"))
print("simulated_within_recommended_window =", view.get("simulated_within_recommended_window"))
print("would_pass_if_now =", decision.get("would_pass_if_now"))
print("headroom_remaining_at_simulated_ms =", decision.get("headroom_remaining_at_simulated_ms"))
print("headroom_remaining_if_now_ms =", decision.get("headroom_remaining_if_now_ms"))
print("warning_flags =", audit.get("warning_flags"))
PY

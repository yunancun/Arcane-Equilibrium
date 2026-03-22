#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_decision_lease_friction_metrics.py
python3 scripts/bybit_decision_lease_friction_metrics_contract_check.py

python3 scripts/bybit_decision_lease_adaptive_ttl.py
python3 scripts/bybit_decision_lease_adaptive_ttl_contract_check.py

python3 scripts/bybit_decision_lease_friction_final_audit.py
python3 scripts/bybit_decision_lease_friction_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

metrics = json.loads((base / "bybit_decision_lease_friction_metrics_latest.json").read_text(encoding="utf-8"))
adaptive = json.loads((base / "bybit_decision_lease_adaptive_ttl_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_friction_final_audit_latest.json").read_text(encoding="utf-8"))

fm = metrics.get("friction_metrics") or {}
ad = adaptive.get("adaptive_ttl_decision") or {}
summary = audit.get("audit_summary") or {}

print("===== I5 FINAL CLEAN STATUS =====")
print("metrics_state =", metrics.get("metrics_state"))
print("decision_state =", adaptive.get("decision_state"))
print("audit_state =", audit.get("audit_state"))
print("i5_stage_closed =", summary.get("i5_stage_closed"))
print("ready_for_i6 =", summary.get("ready_for_i6"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("shadow_adaptive_ttl_only =", summary.get("shadow_adaptive_ttl_only"))
print("current_ttl_ms =", ad.get("current_ttl_ms"))
print("recommended_ttl_ms =", ad.get("recommended_ttl_ms"))
print("ttl_delta_ms =", ad.get("ttl_delta_ms"))
print("recommended_consume_slack_ms =", ad.get("recommended_consume_slack_ms"))
print("latency_ms =", fm.get("latency_ms"))
print("simulated_headroom_ms =", fm.get("simulated_headroom_ms"))
print("now_headroom_ms =", fm.get("now_headroom_ms"))
print("ttl_to_latency_ratio =", fm.get("ttl_to_latency_ratio"))
print("simulated_headroom_ratio =", fm.get("simulated_headroom_ratio"))
print("warning_flags =", audit.get("warning_flags"))
PY

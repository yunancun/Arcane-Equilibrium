#!/usr/bin/env bash
set -euo pipefail

# Canonical I5 runner / I5 规范 runner
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/exchange_connectors/bybit_connector/scripts:$ROOT/program_code/ai_agents/bybit_thought_gate:$ROOT/program_code/trade_executor/bybit_decision_lease"

BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 -m py_compile \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_metrics.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_metrics_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_adaptive_ttl.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_adaptive_ttl_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_final_audit.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_contract_check.py

python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_metrics.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_metrics_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_adaptive_ttl.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_adaptive_ttl_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_final_audit.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_friction_contract_check.py

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

metrics = json.loads((base / "bybit_decision_lease_friction_metrics_latest.json").read_text(encoding="utf-8"))
adaptive = json.loads((base / "bybit_decision_lease_adaptive_ttl_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_friction_final_audit_latest.json").read_text(encoding="utf-8"))

fm = metrics.get("friction_metrics") or {}
ad = adaptive.get("adaptive_ttl_decision") or {}
summary = audit.get("audit_summary") or {}

print("===== I5 CANONICAL CLEAN STATUS =====")
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
print("latency_available =", fm.get("latency_available"))
print("legal_no_call_path =", fm.get("legal_no_call_path"))
print("simulated_headroom_ms =", fm.get("simulated_headroom_ms"))
print("now_headroom_ms =", fm.get("now_headroom_ms"))
print("ttl_to_latency_ratio =", fm.get("ttl_to_latency_ratio"))
print("simulated_headroom_ratio =", fm.get("simulated_headroom_ratio"))
print("warning_flags =", audit.get("warning_flags"))
PY

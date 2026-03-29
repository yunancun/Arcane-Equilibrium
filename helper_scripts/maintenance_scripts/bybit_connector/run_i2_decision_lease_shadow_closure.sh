#!/usr/bin/env bash
set -euo pipefail

# Canonical I2 runner / I2 规范 runner
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/program_code/exchange_connectors/bybit_connector/misc_tools:$ROOT/program_code/ai_agents/bybit_thought_gate:$ROOT/program_code/trade_executor/bybit_decision_lease"

BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 -m py_compile \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_preflight.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_preflight_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue_contract_check.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_audit.py \
  program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_contract_check.py

python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_preflight.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_preflight_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_issue_contract_check.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_audit.py
python3 program_code/trade_executor/bybit_decision_lease/bybit_decision_lease_shadow_contract_check.py

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

preflight = json.loads((base / "bybit_decision_lease_preflight_latest.json").read_text(encoding="utf-8"))
shadow = json.loads((base / "bybit_decision_lease_shadow_issue_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_shadow_audit_latest.json").read_text(encoding="utf-8"))

candidate = shadow.get("shadow_candidate") or {}
summary = audit.get("audit_summary") or {}

print("===== I2 CANONICAL CLEAN STATUS =====")
print("preflight_state =", preflight.get("preflight_state"))
print("shadow_issue_state =", shadow.get("shadow_issue_state"))
print("audit_state =", audit.get("audit_state"))
print("i2_stage_closed =", summary.get("i2_stage_closed"))
print("ready_for_i3 =", summary.get("ready_for_i3"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("shadow_candidate_only =", summary.get("shadow_candidate_only"))
print("lease_emit_allowed_now =", summary.get("lease_emit_allowed_now"))
print("decision_lease_emitted =", summary.get("decision_lease_emitted"))
print("ttl_ms =", candidate.get("ttl_ms"))
print("consume_slack_ms =", candidate.get("consume_slack_ms"))
print("warning_flags =", audit.get("warning_flags"))
PY

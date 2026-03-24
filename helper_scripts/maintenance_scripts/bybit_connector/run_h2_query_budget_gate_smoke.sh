#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
python3 scripts/bybit_query_budget_gate.py
python3 scripts/bybit_query_budget_gate_contract_check.py
'

./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

p = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_query_budget_gate_latest.json")
obj = json.loads(p.read_text(encoding="utf-8"))

print("===== H2-B QUERY BUDGET GATE SMOKE =====")
print("gate_state =", obj.get("gate_state"))
print("gate_ok =", obj.get("gate_ok"))
print("allow_progress_to_h2c_budget_runtime =", obj.get("allow_progress_to_h2c_budget_runtime"))
print("provider_target =", (obj.get("request_summary") or {}).get("provider_target"))
print("model_name =", (obj.get("request_summary") or {}).get("model_name"))
print("ai_daily_budget_usd =", (obj.get("budget_policy") or {}).get("ai_daily_budget_usd"))
print("ai_per_call_budget_usd =", (obj.get("budget_policy") or {}).get("ai_per_call_budget_usd"))
print("max_output_tokens =", (obj.get("budget_policy") or {}).get("max_output_tokens"))
print("max_retries =", (obj.get("budget_policy") or {}).get("max_retries"))
print("latency_ms =", (obj.get("observed_last_call") or {}).get("latency_ms"))
print("within_timeout_hint =", (obj.get("observed_last_call") or {}).get("within_timeout_hint"))
print("warning_flags =", obj.get("warning_flags"))
print("blocking_reasons =", obj.get("blocking_reasons"))
PY

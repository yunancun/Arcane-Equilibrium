#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

./scripts/run_with_trading_env.sh bash -lc '
set -euo pipefail
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

eval "$("./scripts/bybit_bind_active_route_env.sh")"

python3 scripts/bybit_ai_prompt_prep_builder.py
python3 scripts/bybit_ai_prompt_prep_tighten.py
python3 scripts/bybit_ai_prompt_prep_contract_check.py

python3 scripts/bybit_ai_request_envelope_builder.py
python3 scripts/bybit_ai_request_envelope_contract_check.py

BYBIT_AI_DRY_RUN="${BYBIT_AI_DRY_RUN:-0}" python3 scripts/bybit_ai_invocation_attempt_builder.py
python3 scripts/bybit_ai_invocation_attempt_contract_check.py

python3 - <<'"'"'PY'"'"'
import json
from pathlib import Path

prep = json.loads(Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_prompt_prep_latest.json").read_text(encoding="utf-8"))
inv  = json.loads(Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_ai_invocation_attempt_latest.json").read_text(encoding="utf-8"))

print("")
print("===== COMPACT AI SMOKE SUMMARY =====")
print("prompt_max_output_tokens_hint =", (prep.get("prompt_budget", {}) or {}).get("max_output_tokens_hint"))
print("fact_line_count =", len(prep.get("fact_lines", []) or []))
print("warning_flags =", prep.get("warning_flags", []))
print("invocation_state =", inv.get("invocation_state"))
print("parsed_json_present =", ((inv.get("attempt_result", {}) or {}).get("parsed_json_present")))
print("response_text_present =", ((inv.get("attempt_result", {}) or {}).get("response_text_present")))
print("raw_response_preview =", (inv.get("response_extract", {}) or {}).get("raw_response_preview"))
PY
'

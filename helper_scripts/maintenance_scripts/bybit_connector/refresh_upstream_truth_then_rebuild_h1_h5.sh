#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) PRE-REFRESH H1/H2/H4/H5 SNAPSHOT ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

h1 = read("bybit_thought_gate_input_latest.json")
h2 = read("bybit_query_budget_final_audit_latest.json")
h4 = read("bybit_compute_governor_final_audit_latest.json")
h5 = read("bybit_ai_cost_governance_final_audit_latest.json")

public_derived = h1.get("public_market_summary", {}) if isinstance(h1, dict) else {}
if not public_derived:
    public_derived = h1.get("trigger_feature_snapshot", {}) if isinstance(h1, dict) else {}

print("H1 operator_flags =", h1.get("operator_flags"))
print("H1 warning_flags =", h1.get("warning_flags"))
print("H1 public_derived_like =", public_derived)
print("")
print("H2 audit_state =", h2.get("audit_state"))
print("H2 audit_summary =", h2.get("audit_summary"))
print("")
print("H4 audit_state =", h4.get("audit_state"))
print("H4 audit_summary =", h4.get("audit_summary"))
print("")
print("H5 audit_state =", h5.get("audit_state"))
print("H5 final_state =", h5.get("final_state"))
print("H5 audit_summary =", h5.get("audit_summary"))
PY

echo
echo "===== 1) REFRESH UPSTREAM READONLY OBSERVER TRUTH ====="
./scripts/run_with_trading_env.sh bash -lc '
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV
cd $_SRV/program_code/exchange_connectors/bybit_connector
python3 scripts/bybit_full_readonly_observer_cycle.py
'

echo
echo "===== 1.5) REBUILD H0 FRONT CHAIN ====="
./scripts/run_with_trading_env.sh bash -lc '
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV
cd $_SRV/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_public_microstructure_builder.py
python3 scripts/bybit_public_microstructure_contract_check.py
python3 scripts/bybit_local_cost_model_builder.py
python3 scripts/bybit_local_market_friction_builder.py
python3 scripts/bybit_local_risk_envelope_gate.py
python3 scripts/bybit_local_risk_envelope_contract_check.py
python3 scripts/bybit_local_trade_eligibility_builder.py
python3 scripts/bybit_local_trade_eligibility_contract_check.py
python3 scripts/bybit_local_trade_eligibility_handoff_builder.py
python3 scripts/bybit_local_trade_eligibility_handoff_contract_check.py
python3 scripts/bybit_local_judgment_final_audit.py
python3 scripts/bybit_local_judgment_final_audit_contract_check.py
'

echo
echo "===== 2) REBUILD H1 FULL CLOSURE ====="
./scripts/run_with_trading_env.sh bash -lc '
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV
cd $_SRV/program_code/exchange_connectors/bybit_connector

python3 scripts/bybit_thought_gate_input_builder.py
python3 scripts/bybit_thought_gate_policy_builder.py
python3 scripts/bybit_local_trigger_model_builder.py
python3 scripts/bybit_thought_gate_decision_builder.py
python3 scripts/bybit_ai_prompt_prep_builder.py
python3 scripts/bybit_ai_route_selector_builder.py
python3 scripts/bybit_ai_route_selector_contract_check.py
python3 scripts/bybit_ai_request_envelope_builder.py
python3 scripts/bybit_ai_invocation_attempt_builder.py
'
./scripts/run_h1_thought_gate_full_closure.sh

echo
echo "===== 3) REBUILD H2 FULL CLOSURE ====="
./scripts/run_h2_query_budget_full_closure.sh

echo
echo "===== 4) REBUILD H4 FULL CLOSURE ====="
./scripts/run_h4_compute_governor_full_closure.sh

echo
echo "===== 5) REBUILD H5 FULL CLOSURE ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) FINAL CLEAN STATUS AFTER UPSTREAM REFRESH ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

h1_input = read("bybit_thought_gate_input_latest.json")
h1_policy = read("bybit_thought_gate_policy_latest.json")
h1_req = read("bybit_ai_request_envelope_latest.json")
h2 = read("bybit_query_budget_final_audit_latest.json")
h4 = read("bybit_compute_governor_final_audit_latest.json")
h5log = read("bybit_ai_cost_log_latest.json")
h5audit = read("bybit_ai_governance_audit_latest.json")
h5final = read("bybit_ai_cost_governance_final_audit_latest.json")

cost_log = h5log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== H1 =====")
print("input_state =", h1_input.get("input_state"))
print("operator_flags =", h1_input.get("operator_flags"))
print("policy_warning_flags =", h1_policy.get("warning_flags"))
print("request_warning_flags =", h1_req.get("warning_flags"))
print("")

print("===== H2 =====")
print("overall_ok =", h2.get("overall_ok"))
print("audit_state =", h2.get("audit_state"))
print("audit_summary =", h2.get("audit_summary"))
print("")

print("===== H4 =====")
print("overall_ok =", h4.get("overall_ok"))
print("audit_state =", h4.get("audit_state"))
print("audit_summary =", h4.get("audit_summary"))
print("")

print("===== H5 =====")
print("log_state =", h5log.get("log_state"))
print("audit_state =", h5audit.get("audit_state"))
print("final_state =", h5final.get("final_state"))
print("overall_ok =", h5final.get("overall_ok"))
print("audit_summary =", h5final.get("audit_summary"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("log_blocking_reasons =", h5log.get("blocking_reasons"))
print("audit_failed_checks =", h5audit.get("failed_checks"))
print("final_failed_checks =", h5final.get("failed_checks"))
print("warning_flags =", h5final.get("warning_flags"))
PY

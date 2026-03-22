#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

run_py() {
  local s="$1"
  if [ -f "$s" ]; then
    echo
    echo "RUN $s"
    ./scripts/run_with_trading_env.sh python3 "$s"
  else
    echo "SKIP missing $s"
  fi
}

run_pattern() {
  local pat="$1"
  mapfile -t matches < <(compgen -G "$pat" | grep -vE '\.orig$|\.bak_' | sort || true)
  if [ "${#matches[@]}" -eq 0 ]; then
    echo "SKIP no_match $pat"
    return 0
  fi
  for s in "${matches[@]}"; do
    run_py "$s"
  done
}

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_ai_cost_log.py
do
  cp "$f" "$f.bak_fix_h5_and_rebuild_real_h1_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) PATCH H5 NameError GUARD ====="
python3 - <<'PY'
from pathlib import Path

p = Path("scripts/bybit_ai_cost_log.py")
s = p.read_text(encoding="utf-8")
orig = s

needle = 'h2_observed_last_call = h2_runtime.get("observed_last_call") or {}'
guard = 'h2_runtime = locals().get("h2_runtime") or {}\n    h2_observed_last_call = h2_runtime.get("observed_last_call") or {}'

if needle in s and guard not in s:
    s = s.replace(needle, guard, 1)

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("patched:", p)
else:
    print("no_change:", p)
PY

echo
echo "===== 2) REFRESH H0 REAL BUILDERS ====="
run_py scripts/bybit_public_microstructure_builder.py
run_py scripts/bybit_public_microstructure_contract_check.py
run_py scripts/bybit_local_market_friction_builder.py
run_py scripts/bybit_local_market_friction_contract_check.py
run_py scripts/bybit_local_risk_envelope_gate.py
run_py scripts/bybit_local_risk_envelope_contract_check.py
run_py scripts/bybit_local_trade_eligibility_builder.py
run_py scripts/bybit_local_trade_eligibility_contract_check.py
run_py scripts/bybit_local_trade_eligibility_handoff_builder.py
run_py scripts/bybit_local_trade_eligibility_handoff_contract_check.py
run_py scripts/bybit_local_judgment_final_audit.py
run_py scripts/bybit_local_judgment_final_audit_contract_check.py

echo
echo "===== 3) REBUILD H1 FROM REAL HEAD SCRIPTS ====="
run_pattern 'scripts/bybit_thought_gate_input*.py'
run_pattern 'scripts/bybit_thought_gate_policy*.py'
run_pattern 'scripts/bybit_local_trigger_model*.py'
run_pattern 'scripts/bybit_thought_gate_decision*.py'
run_pattern 'scripts/bybit_ai_route_selector*.py'
run_pattern 'scripts/bybit_ai_prompt_prep*.py'
run_pattern 'scripts/bybit_ai_request_envelope*.py'
run_pattern 'scripts/bybit_ai_invocation_attempt*.py'
run_pattern 'scripts/bybit_ai_response_check*.py'
run_pattern 'scripts/bybit_ai_governed_decision*.py'
run_pattern 'scripts/bybit_thought_gate_acceptance_suite*.py'
run_pattern 'scripts/bybit_thought_gate_regression_summary*.py'
run_pattern 'scripts/bybit_thought_gate_handoff*.py'
run_pattern 'scripts/bybit_thought_gate_final_audit*.py'
run_pattern 'scripts/bybit_thought_gate_contract_check*.py'

echo
echo "===== 4) H1 TRUTH CHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

inp = read("bybit_thought_gate_input_latest.json")
pol = read("bybit_thought_gate_policy_latest.json")
env = read("bybit_ai_request_envelope_latest.json")
inv = read("bybit_ai_invocation_attempt_latest.json")
resp = read("bybit_ai_response_check_latest.json")
fin = read("bybit_thought_gate_final_audit_latest.json")

req = env.get("request_summary") or {}
prep_state = env.get("prep_state", req.get("prep_state"))
should_call_ai = env.get("should_call_ai", req.get("should_call_ai"))
provider_target = env.get("provider_target", req.get("provider_target"))
model_name = env.get("model_name", req.get("model_name"))

print("H1 input_state =", inp.get("input_state"))
print("H1 operator_flags =", inp.get("operator_flags"))
print("H1 policy_state =", pol.get("policy_state"))
print("H1 policy_warning_flags =", pol.get("warning_flags"))
print("H1 prep_state =", prep_state)
print("H1 should_call_ai =", should_call_ai)
print("H1 provider_target =", provider_target)
print("H1 model_name =", model_name)
print("H1 invocation_state =", inv.get("invocation_state"))
print("H1 response_overall_ok =", resp.get("overall_ok"))
print("H1 final_overall_ok =", fin.get("overall_ok"))
print("H1 final_audit_summary =", fin.get("audit_summary"))

bad = False
if not fin.get("overall_ok"):
    bad = True
if not provider_target:
    bad = True
if not model_name:
    bad = True

if bad:
    raise SystemExit("STOP: H1 still not green")
PY

echo
echo "===== 5) ONLY IF H1 GREEN: REBUILD H2-H5 ====="
./scripts/run_with_trading_env.sh bash scripts/run_h2_query_budget_full_closure.sh
./scripts/run_with_trading_env.sh bash scripts/run_h3_model_router_full_closure.sh
./scripts/run_with_trading_env.sh bash scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_with_trading_env.sh bash scripts/run_h5_ai_cost_governance_full_closure.sh

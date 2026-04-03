#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector
TG_BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

run_py() {
  ./scripts/run_with_trading_env.sh python3 "$1"
}

run_sh() {
  ./scripts/run_with_trading_env.sh bash -lc "$1"
}

run_if_found() {
  local f="$1"
  if [ -n "${f:-}" ] && [ -f "$f" ]; then
    echo
    echo "RUN $f"
    run_py "$f"
  else
    echo
    echo "SKIP missing file"
  fi
}

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_public_microstructure_builder.py \
  scripts/bybit_local_market_friction_builder.py \
  scripts/bybit_local_risk_envelope_builder.py \
  scripts/bybit_local_trade_eligibility_builder.py \
  scripts/bybit_local_trade_eligibility_handoff.py \
  scripts/bybit_local_judgment_final_audit.py
do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak_recover_h0_h1_$(date +%s)"
    echo "backed_up: $f"
  fi
done

echo
echo "===== 1) PATCH H5 NameError IN bybit_ai_cost_log.py ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("scripts/bybit_ai_cost_log.py")
s = p.read_text(encoding="utf-8")
orig = s

target = 'h2_observed_last_call = h2_runtime.get("observed_last_call") or {}'
if target in s:
    # 优先尝试替换成脚本里已有的 runtime 变量名
    candidate = None
    for m in re.finditer(r'^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*load_json\(([A-Za-z_][A-Za-z0-9_]*)\)\s*$', s, re.M):
        var, path = m.group(1), m.group(2)
        if "runtime" in var.lower() and ("H2" in path or "QUERY_BUDGET" in path.upper()):
            candidate = var
            break

    if candidate:
        s = s.replace(target, f'h2_observed_last_call = {candidate}.get("observed_last_call") or {{}}')
    elif 'h2_runtime = load_json(H2_RUNTIME_PATH)' not in s and 'H2_RUNTIME_PATH' in s and 'load_json' in s:
        s = s.replace(target, 'h2_runtime = load_json(H2_RUNTIME_PATH)\n    ' + target)

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("patched: scripts/bybit_ai_cost_log.py")
else:
    print("no_change: scripts/bybit_ai_cost_log.py")
PY

echo
echo "===== 2) DISCOVER H0 / PUBLIC MICROSTRUCTURE BUILDERS ====="
PM_BUILDER="$(find scripts -maxdepth 1 -type f -name '*public*microstructure*.py' ! -name '*contract*' | sort | head -n 1)"
PM_CONTRACT="$(find scripts -maxdepth 1 -type f -name '*public*microstructure*contract*.py' | sort | head -n 1)"
FRIC_BUILDER="$(find scripts -maxdepth 1 -type f -name '*local*market*friction*.py' ! -name '*contract*' | sort | head -n 1)"
FRIC_CONTRACT="$(find scripts -maxdepth 1 -type f -name '*local*market*friction*contract*.py' | sort | head -n 1)"
RISK_BUILDER="$(find scripts -maxdepth 1 -type f -name '*local*risk*envelope*.py' ! -name '*contract*' | sort | head -n 1)"
RISK_CONTRACT="$(find scripts -maxdepth 1 -type f -name '*local*risk*envelope*contract*.py' | sort | head -n 1)"
ELIG_BUILDER="$(find scripts -maxdepth 1 -type f -name '*local*trade*eligibility*.py' ! -name '*contract*' ! -name '*handoff*' | sort | head -n 1)"
ELIG_CONTRACT="$(find scripts -maxdepth 1 -type f -name '*local*trade*eligibility*contract*.py' ! -name '*handoff*' | sort | head -n 1)"
HANDOFF_BUILDER="$(find scripts -maxdepth 1 -type f -name '*trade*eligibility*handoff*.py' ! -name '*contract*' | sort | head -n 1)"
HANDOFF_CONTRACT="$(find scripts -maxdepth 1 -type f -name '*trade*eligibility*handoff*contract*.py' | sort | head -n 1)"
FINAL_AUDIT="$(find scripts -maxdepth 1 -type f -name '*local*judgment*final*audit*.py' | sort | head -n 1)"

echo "PM_BUILDER      = ${PM_BUILDER:-missing}"
echo "PM_CONTRACT     = ${PM_CONTRACT:-missing}"
echo "FRIC_BUILDER    = ${FRIC_BUILDER:-missing}"
echo "FRIC_CONTRACT   = ${FRIC_CONTRACT:-missing}"
echo "RISK_BUILDER    = ${RISK_BUILDER:-missing}"
echo "RISK_CONTRACT   = ${RISK_CONTRACT:-missing}"
echo "ELIG_BUILDER    = ${ELIG_BUILDER:-missing}"
echo "ELIG_CONTRACT   = ${ELIG_CONTRACT:-missing}"
echo "HANDOFF_BUILDER = ${HANDOFF_BUILDER:-missing}"
echo "HANDOFF_CONTRACT= ${HANDOFF_CONTRACT:-missing}"
echo "FINAL_AUDIT     = ${FINAL_AUDIT:-missing}"

echo
echo "===== 3) FORCE REFRESH PUBLIC MICROSTRUCTURE + H0 ====="
run_if_found "$PM_BUILDER"
run_if_found "$PM_CONTRACT"
run_if_found "$FRIC_BUILDER"
run_if_found "$FRIC_CONTRACT"
run_if_found "$RISK_BUILDER"
run_if_found "$RISK_CONTRACT"
run_if_found "$ELIG_BUILDER"
run_if_found "$ELIG_CONTRACT"
run_if_found "$HANDOFF_BUILDER"
run_if_found "$HANDOFF_CONTRACT"
run_if_found "$FINAL_AUDIT"

echo
echo "===== 4) CHECK FRESH PUBLIC MICROSTRUCTURE / H0 ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

lj = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment")
tg = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(p):
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

pm = read(lj / "bybit_public_microstructure_latest.json")
h0 = read(lj / "bybit_local_judgment_final_audit_latest.json")

print("public_microstructure.ts_ms =", pm.get("ts_ms"))
print("public_microstructure.state =", pm.get("microstructure_state"))
print("public_microstructure.last_trade_price =", ((pm.get("derived") or {}).get("last_trade_price")))
print("public_microstructure.last_trade_ts_ms =", ((pm.get("derived") or {}).get("last_trade_ts_ms")))
print("h0.overall_ok =", h0.get("overall_ok"))
print("h0.final_h0_state =", h0.get("final_h0_state"))
print("h0.recommended_action =", h0.get("recommended_action"))
PY

echo
echo "===== 5) REBUILD H1 ONLY ====="
run_sh "./scripts/run_h1_thought_gate_full_closure.sh"

echo
echo "===== 6) H1 TRUTH CHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json, os, sys
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

h1_input = read("bybit_thought_gate_input_latest.json")
h1_policy = read("bybit_thought_gate_policy_latest.json")
h1_env = read("bybit_ai_request_envelope_latest.json")
h1_inv = read("bybit_ai_invocation_attempt_latest.json")
h1_final = read("bybit_thought_gate_final_audit_latest.json")

print("H1 input_state =", h1_input.get("input_state"))
print("H1 operator_flags =", h1_input.get("operator_flags"))
print("H1 policy_state =", h1_policy.get("policy_state"))
print("H1 policy_warning_flags =", h1_policy.get("warning_flags"))
print("H1 request prep_state =", h1_env.get("prep_state"))
print("H1 request should_call_ai =", h1_env.get("should_call_ai"))
print("H1 request provider_target =", (h1_env.get("request_summary") or {}).get("provider_target"))
print("H1 request model_name =", (h1_env.get("request_summary") or {}).get("model_name"))
print("H1 invocation_state =", h1_inv.get("invocation_state"))
print("H1 final overall_ok =", h1_final.get("overall_ok"))
print("H1 final audit_summary =", h1_final.get("audit_summary"))

ok = bool(h1_final.get("overall_ok"))
provider = (h1_env.get("request_summary") or {}).get("provider_target")
model = (h1_env.get("request_summary") or {}).get("model_name")

if not ok:
    print("STOP: H1 still not closed")
    sys.exit(1)
if not provider or not model:
    print("STOP: H1 request envelope still missing provider/model")
    sys.exit(1)
PY

echo
echo "===== 7) REBUILD H2 -> H5 ====="
run_sh "./scripts/run_h2_query_budget_full_closure.sh"
run_sh "./scripts/run_h3_model_router_full_closure.sh"
run_sh "./scripts/run_h4_compute_governor_full_closure.sh"
run_sh "./scripts/run_h5_ai_cost_governance_full_closure.sh"

echo
echo "===== 8) FINAL STATUS ====="
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

h1 = read("bybit_thought_gate_final_audit_latest.json")
h2 = read("bybit_query_budget_final_audit_latest.json")
h3 = read("bybit_model_router_final_audit_latest.json")
h4 = read("bybit_compute_governor_final_audit_latest.json")
h5a = read("bybit_ai_cost_log_latest.json")
h5b = read("bybit_ai_governance_audit_latest.json")
h5c = read("bybit_ai_cost_governance_final_audit_latest.json")

print("===== H1 =====")
print("overall_ok =", h1.get("overall_ok"))
print("audit_summary =", h1.get("audit_summary"))

print("\n===== H2 =====")
print("overall_ok =", h2.get("overall_ok"))
print("audit_state =", h2.get("audit_state"))
print("failed_checks =", h2.get("failed_checks"))
print("audit_summary =", h2.get("audit_summary"))

print("\n===== H3 =====")
print("overall_ok =", h3.get("overall_ok"))
print("audit_state =", h3.get("audit_state"))
print("failed_checks =", h3.get("failed_checks"))
print("audit_summary =", h3.get("audit_summary"))

print("\n===== H4 =====")
print("overall_ok =", h4.get("overall_ok"))
print("audit_state =", h4.get("audit_state"))
print("failed_checks =", h4.get("failed_checks"))
print("audit_summary =", h4.get("audit_summary"))

print("\n===== H5 =====")
print("log_state =", h5a.get("log_state"))
print("audit_state =", h5b.get("audit_state"))
print("final_state =", h5c.get("final_state"))
print("overall_ok =", h5c.get("overall_ok"))
print("audit_summary =", h5c.get("audit_summary"))
print("warning_flags =", h5c.get("warning_flags"))
PY

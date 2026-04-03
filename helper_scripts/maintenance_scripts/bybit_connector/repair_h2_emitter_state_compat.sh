#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector

GATE_F="scripts/bybit_query_budget_gate.py"
AUDIT_F="scripts/bybit_query_budget_final_audit.py"

echo "===== 0) BACKUP ====="
cp "$GATE_F"  "$GATE_F.bak_h2_emitter_state_compat_$(date +%s)"
cp "$AUDIT_F" "$AUDIT_F.bak_h2_emitter_state_compat_$(date +%s)"
echo "backed_up: $GATE_F"
echo "backed_up: $AUDIT_F"

echo
echo "===== 1) LOCATE STATE STRINGS ====="
echo "--- GATE FILE ---"
grep -nE 'query_budget_gate_passed|query_budget_gate_pass_soft_warn|gate_state' "$GATE_F" || true
echo
echo "--- FINAL AUDIT FILE ---"
grep -nE 'query_budget_gate_passed|query_budget_gate_pass_soft_warn|h2b_gate_state_known|gate_state' "$AUDIT_F" || true

echo
echo "===== 2) PATCH H2-B EMITTER ONLY ====="
if grep -q 'query_budget_gate_passed' "$GATE_F"; then
  sed -i 's/query_budget_gate_passed/query_budget_gate_pass_soft_warn/g' "$GATE_F"
  echo "patched_emitter_state=True"
else
  echo "patched_emitter_state=False (string not found in gate file)"
fi

echo
echo "===== 3) VERIFY PATCH ====="
grep -nE 'query_budget_gate_passed|query_budget_gate_pass_soft_warn|gate_state' "$GATE_F" || true

echo
echo "===== 4) PY_COMPILE ====="
python3 -m py_compile \
  "$GATE_F" \
  "$AUDIT_F"

echo
echo "===== 5) RERUN H2 -> H4 -> H5 ====="
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) FINAL TRUTH DIAG AFTER H2 EMITTER COMPAT PATCH ====="
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

h2_gate = read("bybit_query_budget_gate_latest.json")
h2 = read("bybit_query_budget_final_audit_latest.json")
h4 = read("bybit_compute_governor_final_audit_latest.json")
h5log = read("bybit_ai_cost_log_latest.json")
h5audit = read("bybit_ai_governance_audit_latest.json")
h5final = read("bybit_ai_cost_governance_final_audit_latest.json")

cost_log = h5log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== H2 GATE =====")
print("gate_state =", h2_gate.get("gate_state"))
print("warning_flags =", h2_gate.get("warning_flags"))
print("blocking_reasons =", h2_gate.get("blocking_reasons"))
print("")

print("===== H2 =====")
print("overall_ok =", h2.get("overall_ok"))
print("audit_state =", h2.get("audit_state"))
print("failed_checks =", h2.get("failed_checks"))
print("audit_summary =", h2.get("audit_summary"))
print("")

print("===== H4 =====")
print("overall_ok =", h4.get("overall_ok"))
print("audit_state =", h4.get("audit_state"))
print("failed_checks =", h4.get("failed_checks"))
print("audit_summary =", h4.get("audit_summary"))
print("")

print("===== H5 =====")
print("log_state =", h5log.get("log_state"))
print("audit_state =", h5audit.get("audit_state"))
print("final_state =", h5final.get("final_state"))
print("overall_ok =", h5final.get("overall_ok"))
print("log_blocking_reasons =", h5log.get("blocking_reasons"))
print("audit_failed_checks =", h5audit.get("failed_checks"))
print("final_failed_checks =", h5final.get("failed_checks"))
print("audit_summary =", h5final.get("audit_summary"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("warning_flags =", h5final.get("warning_flags"))
PY

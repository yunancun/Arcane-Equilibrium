#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

F="scripts/bybit_query_budget_final_audit.py"

echo "===== 0) BACKUP ====="
cp "$F" "$F.bak_repair_h2_gate_state_only_v9_$(date +%s)"
echo "backed_up: $F"

echo
echo "===== 1) PATCH H2 FINAL AUDIT: NORMALIZE gate_state ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("scripts/bybit_query_budget_final_audit.py")
s = p.read_text(encoding="utf-8")
orig = s

# 如果已经有兼容逻辑，就不重复打
if 'if h2b_gate_state == "query_budget_gate_passed":' in s:
    print("already_normalized=True")
else:
    m = re.search(r'^(?P<indent>\s*)h2b_gate_state\s*=\s*(?P<rhs>.+)$', s, re.M)
    if not m:
        raise SystemExit("PATCH_ANCHOR_NOT_FOUND: h2b_gate_state assignment")

    indent = m.group("indent")
    rhs = m.group("rhs").rstrip()

    replacement = (
        f'{indent}h2b_gate_state = {rhs}\n'
        f'{indent}if h2b_gate_state == "query_budget_gate_passed":\n'
        f'{indent}    h2b_gate_state = "query_budget_gate_pass_soft_warn"'
    )

    s = s[:m.start()] + replacement + s[m.end():]

# 再补一层：如果 check 里是集合/元组，只含旧状态，则并入新状态
s = re.sub(
    r'(\bh2b_gate_state\b[^\n]*\bin\s*[\{\[\(]\s*)"query_budget_gate_pass_soft_warn"(\s*[\}\]\)])',
    r'\1"query_budget_gate_pass_soft_warn", "query_budget_gate_passed"\2',
    s
)

p.write_text(s, encoding="utf-8")
print("patched:", p)
print("changed =", s != orig)
PY

echo
echo "===== 2) VERIFY PATCH ====="
grep -nE 'h2b_gate_state|query_budget_gate_pass_soft_warn|query_budget_gate_passed' "$F" | sed -n '1,40p'

echo
echo "===== 3) PY_COMPILE ====="
python3 -m py_compile "$F"

echo
echo "===== 4) RERUN H2 -> H4 -> H5 ====="
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 5) FINAL TRUTH DIAG AFTER H2 STATE FIX ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

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
print("operator_flags =", h1_input.get("operator_flags"))
print("policy_warning_flags =", h1_policy.get("warning_flags"))
print("request_warning_flags =", h1_req.get("warning_flags"))
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

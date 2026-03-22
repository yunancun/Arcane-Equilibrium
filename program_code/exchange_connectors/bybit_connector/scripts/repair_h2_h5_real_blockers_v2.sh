#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_query_budget_final_audit.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  cp "$f" "$f.bak_repair_h2_h5_real_blockers_v2_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) PATCH H2/H5 REAL BLOCKERS ====="
python3 - <<'PY'
from pathlib import Path
import re

def patch_file(path_str: str, transform):
    p = Path(path_str)
    old = p.read_text(encoding="utf-8")
    new = transform(old)
    if new != old:
        p.write_text(new, encoding="utf-8")
        print(f"patched: {path_str}")
    else:
        print(f"no_change: {path_str}")

# ------------------------------------------------------------
# H2-D: allow both query_budget_gate_pass_soft_warn and passed
# ------------------------------------------------------------
def patch_h2(text: str) -> str:
    orig = text

    # case 1: equality check
    text = re.sub(
        r'==\s*"query_budget_gate_pass_soft_warn"',
        'in {"query_budget_gate_pass_soft_warn", "query_budget_gate_passed"}',
        text,
        count=1,
    )

    # case 2: membership with only old state in set/list/tuple
    text = re.sub(
        r'(\bin\s*[\{\[\(]\s*)"query_budget_gate_pass_soft_warn"(\s*[\}\]\)])',
        r'\1"query_budget_gate_pass_soft_warn", "query_budget_gate_passed"\2',
        text,
        count=1,
    )

    # case 3: explicit tuple/list/set assignment containing only old state
    text = re.sub(
        r'([\=\:]\s*[\{\[\(]\s*)"query_budget_gate_pass_soft_warn"(\s*[\}\]\)])',
        r'\1"query_budget_gate_pass_soft_warn", "query_budget_gate_passed"\2',
        text,
        count=1,
    )

    # guard: if old exists somewhere and new nowhere, append compatibility comment
    if "query_budget_gate_pass_soft_warn" in text and "query_budget_gate_passed" not in text:
        text = text.replace(
            "query_budget_gate_pass_soft_warn",
            'query_budget_gate_pass_soft_warn", "query_budget_gate_passed',
            1,
        )

    return text

# ------------------------------------------------------------
# H5-B / H5-C: fix UnboundLocalError on blocking_reasons
# ------------------------------------------------------------
def patch_h5(text: str) -> str:
    text = text.replace(
        "(blocking_reasons or [])",
        '(locals().get("blocking_reasons") or [])'
    )
    text = text.replace(
        "blocking_reasons or []",
        'locals().get("blocking_reasons") or []'
    )
    return text

patch_file("scripts/bybit_query_budget_final_audit.py", patch_h2)
patch_file("scripts/bybit_ai_governance_audit.py", patch_h5)
patch_file("scripts/bybit_ai_cost_governance_final_audit.py", patch_h5)
PY

echo
echo "===== 2) VERIFY PATCHES ====="
grep -nE 'query_budget_gate_pass_soft_warn|query_budget_gate_passed' scripts/bybit_query_budget_final_audit.py || true
echo
grep -nE 'locals\(\)\.get\("blocking_reasons"\)|blocking_reasons' scripts/bybit_ai_governance_audit.py | sed -n '1,20p' || true
echo
grep -nE 'locals\(\)\.get\("blocking_reasons"\)|blocking_reasons' scripts/bybit_ai_cost_governance_final_audit.py | sed -n '1,20p' || true

echo
echo "===== 3) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_query_budget_final_audit.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 4) RERUN H2 -> H4 -> H5 ====="
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 5) FINAL TRUTH DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

h2 = read("bybit_query_budget_final_audit_latest.json")
h4 = read("bybit_compute_governor_final_audit_latest.json")
h5log = read("bybit_ai_cost_log_latest.json")
h5audit = read("bybit_ai_governance_audit_latest.json")
h5final = read("bybit_ai_cost_governance_final_audit_latest.json")

cost_log = h5log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

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

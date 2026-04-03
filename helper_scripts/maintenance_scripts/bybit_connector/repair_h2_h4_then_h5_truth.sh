#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP CURRENT H2/H4/H5 RUNTIME JSON ====="
for f in \
  "$BASE/bybit_query_budget_final_audit_latest.json" \
  "$BASE/bybit_compute_governor_final_audit_latest.json" \
  "$BASE/bybit_ai_cost_log_latest.json" \
  "$BASE/bybit_ai_governance_audit_latest.json" \
  "$BASE/bybit_ai_cost_governance_final_audit_latest.json"
do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak_repair_h2_h4_h5_truth_$(date +%s)"
    echo "backed_up: $f"
  else
    echo "missing: $f"
  fi
done

echo
echo "===== 1) PRE-REPAIR TRUTH DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(name):
    p = base / name
    if not p.exists():
        return {"__missing__": True}
    return json.loads(p.read_text(encoding="utf-8"))

h2 = read("bybit_query_budget_final_audit_latest.json")
h4 = read("bybit_compute_governor_final_audit_latest.json")
h5 = read("bybit_ai_cost_governance_final_audit_latest.json")

print("H2 overall_ok =", h2.get("overall_ok"))
print("H2 audit_state =", h2.get("audit_state"))
print("H2 audit_summary =", h2.get("audit_summary"))
print("")
print("H4 overall_ok =", h4.get("overall_ok"))
print("H4 audit_state =", h4.get("audit_state"))
print("H4 audit_summary =", h4.get("audit_summary"))
print("")
print("H5 overall_ok =", h5.get("overall_ok"))
print("H5 audit_state =", h5.get("audit_state"))
print("H5 final_state =", h5.get("final_state"))
print("H5 audit_summary =", h5.get("audit_summary"))
PY

echo
echo "===== 2) RERUN H2 FULL CLOSURE ====="
./scripts/run_h2_query_budget_full_closure.sh

echo
echo "===== 3) RERUN H4 FULL CLOSURE ====="
./scripts/run_h4_compute_governor_full_closure.sh

echo
echo "===== 4) POST-H2/H4 TRUTH DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

h2 = json.loads((base / "bybit_query_budget_final_audit_latest.json").read_text(encoding="utf-8"))
h4 = json.loads((base / "bybit_compute_governor_final_audit_latest.json").read_text(encoding="utf-8"))

print("H2 overall_ok =", h2.get("overall_ok"))
print("H2 audit_state =", h2.get("audit_state"))
print("H2 audit_summary =", h2.get("audit_summary"))
print("")
print("H4 overall_ok =", h4.get("overall_ok"))
print("H4 audit_state =", h4.get("audit_state"))
print("H4 audit_summary =", h4.get("audit_summary"))
PY

echo
echo "===== 5) RERUN H5 FULL CLOSURE ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) FINAL H2/H4/H5 CLEAN STATUS ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

h2 = json.loads((base / "bybit_query_budget_final_audit_latest.json").read_text(encoding="utf-8"))
h4 = json.loads((base / "bybit_compute_governor_final_audit_latest.json").read_text(encoding="utf-8"))
log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
h5 = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

cost_log = log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

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
print("log_state =", log.get("log_state"))
print("audit_state =", audit.get("audit_state"))
print("final_state =", h5.get("final_state"))
print("overall_ok =", h5.get("overall_ok"))
print("audit_summary =", h5.get("audit_summary"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("log_blocking_reasons =", log.get("blocking_reasons"))
print("audit_failed_checks =", audit.get("failed_checks"))
print("final_failed_checks =", h5.get("failed_checks"))
print("warning_flags =", h5.get("warning_flags"))
PY

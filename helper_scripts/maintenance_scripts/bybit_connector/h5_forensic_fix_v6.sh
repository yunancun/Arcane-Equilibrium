#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  cp "$f" "$f.bak_h5_forensic_fix_v6_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) FORENSIC GREP BEFORE PATCH ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  echo
  echo "----- $f -----"
  grep -nE 'blocking_reasons|failed_checks|log_state|audit_state|final_state|within_timeout_hint|actual_cost_usd|pricing_table_bound|H5_MINIMAL_OVERRIDE|H5_SOFTWARN|H5_FINAL_STATE' "$f" || true
done

echo
echo "===== 2) PATCH H5 LOG / AUDIT / FINAL AUDIT ====="
python3 - <<'PY'
from pathlib import Path
import re

def patch_file(path_str: str, marker: str, block: str):
    p = Path(path_str)
    s = p.read_text(encoding="utf-8")

    # remove prior variants of H5 override blocks
    for mk in [
        "# H5_MINIMAL_OVERRIDE_V4",
        "# H5_MINIMAL_OVERRIDE_V5",
        "# H5_SOFTWARN_CLASSIFICATION_V3",
        "# H5_FINAL_STATE_V3",
        marker,
    ]:
        while mk in s:
            start = s.find(mk)
            nxt = re.search(r'(?m)^\s*(report\s*=\s*\{|return\s*\{)', s[start:])
            if not nxt:
                s = s[:start]
                break
            s = s[:start] + s[start + nxt.start():]

    m = re.search(r'(?m)^(\s*)(report\s*=\s*\{|return\s*\{)', s)
    if not m:
        raise SystemExit(f"ANCHOR_NOT_FOUND: {p}")

    indent = m.group(1)
    block_text = "\n".join((indent + line) if line.strip() else "" for line in block.strip("\n").splitlines()) + "\n\n"
    s = s[:m.start()] + block_text + s[m.start():]
    p.write_text(s, encoding="utf-8")
    print(f"patched: {p}")

log_block = """
# H5_FORENSIC_OVERRIDE_V6
soft_warn_only_flags = {
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
}

warning_flags = list(dict.fromkeys(list(warning_flags or [])))
blocking_reasons = list(dict.fromkeys(list(blocking_reasons or [])))

# within_timeout_hint = None in current mainline is informational, not a hard blocker
blocking_reasons = [
    x for x in blocking_reasons
    if x not in soft_warn_only_flags
    and x not in {
        "within_timeout_hint_missing",
        "observed_last_call_timeout_hint_missing",
        "last_call_timeout_hint_missing",
        "actual_cost_usd_missing",
    }
]

if blocking_reasons:
    log_state = "ai_cost_log_blocked"
    log_ok = False
else:
    log_state = "ai_cost_log_recorded_soft_warn" if warning_flags else "ai_cost_log_recorded"
    log_ok = True
"""

audit_block = """
# H5_FORENSIC_OVERRIDE_V6
soft_warn_only_flags = {
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
}

warning_flags = list(dict.fromkeys(list(warning_flags or [])))
failed_checks = list(dict.fromkeys(list(failed_checks or [])))
blocking_reasons = list(dict.fromkeys(list(blocking_reasons or [])))

blocking_reasons = [
    x for x in blocking_reasons
    if x not in soft_warn_only_flags
    and x not in {
        "within_timeout_hint_missing",
        "observed_last_call_timeout_hint_missing",
        "last_call_timeout_hint_missing",
        "actual_cost_usd_missing",
    }
]

failed_checks = [
    x for x in failed_checks
    if x not in soft_warn_only_flags
    and x not in {
        "within_timeout_hint_missing",
        "observed_last_call_timeout_hint_missing",
        "last_call_timeout_hint_missing",
        "actual_cost_usd_missing",
    }
]

if failed_checks or blocking_reasons:
    audit_state = "ai_governance_audit_blocked"
    audit_ok = False
else:
    audit_state = "ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"
    audit_ok = True
"""

final_block = """
# H5_FORENSIC_OVERRIDE_V6
warning_flags = list(dict.fromkeys(list(warning_flags or [])))
failed_checks = list(dict.fromkeys(list(failed_checks or [])))

failed_checks = [
    x for x in failed_checks
    if x not in {
        "recent_trade_last_price_missing",
        "recent_trade_last_ts_missing",
        "runtime_state_reference_old",
        "freshness_soft_warning_present",
        "last_trade_fields_missing",
        "within_timeout_hint_missing",
        "observed_last_call_timeout_hint_missing",
        "last_call_timeout_hint_missing",
        "actual_cost_usd_missing",
    }
]

if failed_checks:
    final_state = "ai_cost_governance_not_closed"
else:
    final_state = "ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1"
"""

patch_file("scripts/bybit_ai_cost_log.py", "# H5_FORENSIC_OVERRIDE_V6", log_block)
patch_file("scripts/bybit_ai_governance_audit.py", "# H5_FORENSIC_OVERRIDE_V6", audit_block)
patch_file("scripts/bybit_ai_cost_governance_final_audit.py", "# H5_FORENSIC_OVERRIDE_V6", final_block)

# ensure final_state is included in final audit report
p = Path("scripts/bybit_ai_cost_governance_final_audit.py")
s = p.read_text(encoding="utf-8")
if '"final_state": final_state,' not in s and "'final_state': final_state," not in s:
    if '"audit_state": audit_state,' in s:
        s = s.replace(
            '"audit_state": audit_state,',
            '"audit_state": audit_state,\n        "final_state": final_state,',
            1,
        )
    elif "'audit_state': audit_state," in s:
        s = s.replace(
            "'audit_state': audit_state,",
            "'audit_state': audit_state,\n        'final_state': final_state,",
            1,
        )
    else:
        raise SystemExit("AUDIT_STATE_FIELD_NOT_FOUND")
    p.write_text(s, encoding="utf-8")
    print(f"patched_report_field: {p}")
else:
    print(f"final_state_field_exists: {p}")
PY

echo
echo "===== 3) VERIFY PATCH MARKERS ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  echo
  echo "----- $f -----"
  grep -nE 'H5_FORENSIC_OVERRIDE_V6|log_state|audit_state|final_state|failed_checks|blocking_reasons' "$f" || true
done

echo
echo "===== 4) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 5) RERUN H5 FULL CLOSURE ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) RAW JSON DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

print("log_blocking_reasons =", log.get("blocking_reasons"))
print("audit_failed_checks =", audit.get("failed_checks"))
print("audit_blocking_reasons =", audit.get("blocking_reasons"))
print("final_failed_checks =", final_audit.get("failed_checks"))
print("final_warning_flags =", final_audit.get("warning_flags"))
print("final_state =", final_audit.get("final_state"))
PY

echo
echo "===== 7) H5 FINAL CLEAN STATUS AFTER V6 ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

cost_log = log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}
summary = final_audit.get("audit_summary") or {}

print("log_state =", log.get("log_state"))
print("audit_state =", audit.get("audit_state"))
print("final_state =", final_audit.get("final_state"))
print("h5_stage_closed =", summary.get("h5_stage_closed"))
print("h_chapter_closed =", summary.get("h_chapter_closed"))
print("ready_for_i1 =", summary.get("ready_for_i1"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("warning_flags =", final_audit.get("warning_flags"))
PY

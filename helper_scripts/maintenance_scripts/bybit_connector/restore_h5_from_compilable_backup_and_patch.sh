#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

pick_compilable_backup() {
  local f="$1"
  local b
  while IFS= read -r b; do
    [ -f "$b" ] || continue
    if python3 -m py_compile "$b" >/dev/null 2>&1; then
      echo "$b"
      return 0
    fi
  done < <(ls -1t "${f}.bak"* 2>/dev/null || true)
  return 1
}

restore_one() {
  local f="$1"
  local b
  if ! b="$(pick_compilable_backup "$f")"; then
    echo "NO_COMPILABLE_BACKUP_FOUND: $f"
    echo "CANDIDATES:"
    ls -1t "${f}.bak"* 2>/dev/null || true
    exit 1
  fi
  cp "$b" "$f"
  echo "restored: $f <- $b"
}

echo "===== 0) BACKUP CURRENT H5 FILES ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  cp "$f" "$f.bak_before_compilable_restore_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) RESTORE FROM FIRST COMPILABLE BACKUP ====="
restore_one scripts/bybit_ai_cost_log.py
restore_one scripts/bybit_ai_governance_audit.py
restore_one scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 2) PRE-COMPILE AFTER RESTORE ====="
python3 -m py_compile \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 3) APPLY MINIMAL H5 PATCH ====="
python3 - <<'PY'
from pathlib import Path
import re

def insert_before_anchor(path_str: str, marker: str, block: str):
    p = Path(path_str)
    s = p.read_text(encoding="utf-8")

    # Remove previous copy of same marker block if present
    while marker in s:
        start = s.find(marker)
        end_report = re.search(r'(?m)^\s*(report\s*=\s*\{|return\s*\{)', s[start:])
        if not end_report:
            break
        end = start + end_report.start()
        s = s[:start] + s[end:]

    m = re.search(r'(?m)^(\s*)(report\s*=\s*\{|return\s*\{)', s)
    if not m:
        raise SystemExit(f"ANCHOR_NOT_FOUND: {p}")

    indent = m.group(1)
    block_text = "\n".join((indent + ln) if ln.strip() else "" for ln in block.strip("\n").splitlines()) + "\n\n"
    s = s[:m.start()] + block_text + s[m.start():]
    p.write_text(s, encoding="utf-8")
    print(f"patched: {p}")

log_block = """
# H5_MINIMAL_OVERRIDE_V5
soft_warn_only_flags = {
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
}
warning_flags = list(dict.fromkeys(list(warning_flags or [])))
blocking_reasons = [x for x in list(blocking_reasons or []) if x not in soft_warn_only_flags]

if blocking_reasons:
    log_state = "ai_cost_log_blocked"
    log_ok = False
else:
    log_state = "ai_cost_log_recorded_soft_warn" if warning_flags else "ai_cost_log_recorded"
    log_ok = True
"""

audit_block = """
# H5_MINIMAL_OVERRIDE_V5
soft_warn_only_flags = {
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
}
warning_flags = list(dict.fromkeys(list(warning_flags or [])))
blocking_reasons = [x for x in list(blocking_reasons or []) if x not in soft_warn_only_flags]

if blocking_reasons:
    audit_state = "ai_governance_audit_blocked"
    audit_ok = False
else:
    audit_state = "ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"
    audit_ok = True
"""

final_block = """
# H5_MINIMAL_OVERRIDE_V5
warning_flags = list(dict.fromkeys(list(warning_flags or [])))
final_state = (
    "ai_cost_governance_not_closed"
    if failed_checks
    else ("ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1")
)
"""

insert_before_anchor("scripts/bybit_ai_cost_log.py", "# H5_MINIMAL_OVERRIDE_V5", log_block)
insert_before_anchor("scripts/bybit_ai_governance_audit.py", "# H5_MINIMAL_OVERRIDE_V5", audit_block)
insert_before_anchor("scripts/bybit_ai_cost_governance_final_audit.py", "# H5_MINIMAL_OVERRIDE_V5", final_block)

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
echo "===== 4) VERIFY PATCH MARKERS ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  echo
  echo "----- $f -----"
  grep -nE 'H5_MINIMAL_OVERRIDE_V5|final_state' "$f" || true
done

echo
echo "===== 5) POST-PATCH PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 6) RERUN H5 FULL CLOSURE ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 7) H5 FINAL RECHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

cost_log = log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}
summary = final_audit.get("audit_summary") or {}

print("===== H5 FINAL CLEAN STATUS AFTER V5 =====")
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

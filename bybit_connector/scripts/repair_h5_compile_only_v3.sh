#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  cp "$f" "$f.bak_repair_h5_compile_v3_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) CLEAN REINSERT H5 PATCH BLOCKS ====="
python3 - <<'PY'
from pathlib import Path
import re

def strip_marker_block(text: str, marker: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if marker in lines[i]:
            i += 1
            while i < len(lines):
                if re.match(r'^\s*report\s*=\s*\{$', lines[i]):
                    break
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out) + "\n"

def insert_before_report(path_str: str, marker: str, block: str):
    p = Path(path_str)
    s = p.read_text(encoding="utf-8")
    s = strip_marker_block(s, marker)

    m = re.search(r'(?m)^(\s*)report\s*=\s*\{$', s)
    if not m:
        raise SystemExit(f"REPORT_ANCHOR_NOT_FOUND: {p}")

    indent = m.group(1)
    block_lines = []
    for ln in block.strip("\n").splitlines():
        block_lines.append((indent + ln) if ln.strip() else "")
    block_text = "\n".join(block_lines) + "\n\n"

    s = s[:m.start()] + block_text + s[m.start():]
    p.write_text(s, encoding="utf-8")
    print(f"patched: {p}")

log_block = """
# H5_SOFTWARN_CLASSIFICATION_V3
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
# H5_SOFTWARN_CLASSIFICATION_V3
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
# H5_FINAL_STATE_V3
warning_flags = list(dict.fromkeys(list(warning_flags or [])))
if failed_checks:
    final_state = "ai_cost_governance_not_closed"
else:
    final_state = "ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1"
"""

insert_before_report(
    "scripts/bybit_ai_cost_log.py",
    "# H5_SOFTWARN_CLASSIFICATION_V3",
    log_block,
)
insert_before_report(
    "scripts/bybit_ai_governance_audit.py",
    "# H5_SOFTWARN_CLASSIFICATION_V3",
    audit_block,
)
insert_before_report(
    "scripts/bybit_ai_cost_governance_final_audit.py",
    "# H5_FINAL_STATE_V3",
    final_block,
)

# 确保 final_state 已写入 report
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
        raise SystemExit("AUDIT_STATE_FIELD_NOT_FOUND: bybit_ai_cost_governance_final_audit.py")
    p.write_text(s, encoding="utf-8")
    print(f"patched_report_field: {p}")
else:
    print(f"final_state_field_exists: {p}")
PY

echo
echo "===== 2) VERIFY PATCH BLOCKS ====="
for f in \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  echo
  echo "----- $f -----"
  grep -nE 'H5_SOFTWARN_CLASSIFICATION_V3|H5_FINAL_STATE_V3|final_state' "$f" || true
done

echo
echo "===== 3) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 4) RERUN H5 ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 5) H5 RECHECK ====="
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

print("===== H5 AFTER COMPILE REPAIR V3 =====")
print("log_state =", log.get("log_state"))
print("audit_state =", audit.get("audit_state"))
print("final_state =", final_audit.get("final_state"))
print("h5_stage_closed =", summary.get("h5_stage_closed"))
print("h_chapter_closed =", summary.get("h_chapter_closed"))
print("ready_for_i1 =", summary.get("ready_for_i1"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("warning_flags =", final_audit.get("warning_flags"))
print("runtime_still_protected =", summary.get("runtime_still_protected"))
PY

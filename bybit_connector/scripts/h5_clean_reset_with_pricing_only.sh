#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

pick_clean_compilable_backup() {
  local f="$1"
  local b

  # 1) 优先拿 dirty-cleanup 之前的备份（这是最后一批“主线还是绿的”版本）
  while IFS= read -r b; do
    [ -f "$b" ] || continue
    python3 -m py_compile "$b" >/dev/null 2>&1 || continue
    if grep -qE 'H5_FORENSIC_OVERRIDE|H5_MINIMAL_OVERRIDE|H5_SOFTWARN_CLASSIFICATION|H5_FINAL_STATE' "$b"; then
      continue
    fi
    echo "$b"
    return 0
  done < <(ls -1t "${f}.bak_mainline_dirty_cleanup_"* 2>/dev/null || true)

  # 2) 再从所有备份里找“可编译 + 无 H5 污染 marker”的
  while IFS= read -r b; do
    [ -f "$b" ] || continue
    python3 -m py_compile "$b" >/dev/null 2>&1 || continue
    if grep -qE 'H5_FORENSIC_OVERRIDE|H5_MINIMAL_OVERRIDE|H5_SOFTWARN_CLASSIFICATION|H5_FINAL_STATE' "$b"; then
      continue
    fi
    echo "$b"
    return 0
  done < <(ls -1t "${f}.bak"* 2>/dev/null || true)

  return 1
}

restore_one() {
  local f="$1"
  local b
  if ! b="$(pick_clean_compilable_backup "$f")"; then
    echo "NO_CLEAN_COMPILABLE_BACKUP_FOUND: $f"
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
  cp "$f" "$f.bak_before_h5_clean_reset_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) RESTORE CLEAN COMPILABLE BACKUPS ====="
restore_one scripts/bybit_ai_cost_log.py
restore_one scripts/bybit_ai_governance_audit.py
restore_one scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 2) PATCH ai_cost_log.py WITH PRICING ONLY ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("scripts/bybit_ai_cost_log.py")
s = p.read_text(encoding="utf-8")

import_line = "from bybit_mainline_cleanup_helpers import compute_usage_cost_usd, resolve_provider_pricing"
if import_line not in s:
    lines = s.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
            break
    while insert_at < len(lines) and (lines[insert_at].startswith("import ") or lines[insert_at].startswith("from ")):
        insert_at += 1
    lines.insert(insert_at, import_line)
    s = "\n".join(lines) + "\n"

old_block = """    actual_cost_usd = None
    pricing_table_bound = False"""
new_block = """    pricing = resolve_provider_pricing(
        provider_target=request_summary.get("provider_target"),
        model_name=request_summary.get("model_name"),
        usage_summary=usage_summary,
    )
    pricing_table_bound = bool(pricing.get("pricing_table_bound"))
    actual_cost_usd = compute_usage_cost_usd(usage_summary, pricing) if pricing_table_bound else None"""

if old_block in s:
    s = s.replace(old_block, new_block, 1)

s = s.replace(
    '+ ["provider_pricing_table_not_bound_in_mainline"]',
    '+ (["provider_pricing_table_not_bound_in_mainline"] if not pricing_table_bound else [])'
)

p.write_text(s, encoding="utf-8")
print("patched:", p)
PY

echo
echo "===== 3) VERIFY ai_cost_log PRICING PATCH ====="
grep -nE 'resolve_provider_pricing|compute_usage_cost_usd|pricing_table_bound|actual_cost_usd|provider_pricing_table_not_bound_in_mainline' \
  scripts/bybit_ai_cost_log.py || true

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
echo "===== 6) H5 RAW DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

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
echo "===== 7) H5 FINAL CLEAN STATUS ====="
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

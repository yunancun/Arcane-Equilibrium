#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector
BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py
do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak_repair_h1_h5_v2_$(date +%s)"
    echo "backed_up: $f"
  fi
done

echo
echo "===== 1) SURGICAL REPAIR: bybit_thought_gate_input_builder.py ====="
python3 - <<'PY'
from pathlib import Path
import re

p = Path("scripts/bybit_thought_gate_input_builder.py")
s = p.read_text(encoding="utf-8")

helper_import = "from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags"

# 1) import 去重并放到 __future__ 后面
lines = s.splitlines()
lines = [ln for ln in lines if ln.strip() != helper_import]
insert_at = 0
for i, ln in enumerate(lines):
    if ln.startswith("from __future__ import "):
        insert_at = i + 1
        break
lines.insert(insert_at, helper_import)
s = "\n".join(lines) + "\n"

# 2) 删掉所有裸插入的 prune 语句（无论缩进）
prune_stmt = "operator_flags = prune_freshness_warning_flags(locals(), operator_flags)"
lines = s.splitlines()
lines = [ln for ln in lines if ln.strip() != prune_stmt]
s = "\n".join(lines) + "\n"

# 3) 如果还没做 recent-trade rehydrate，则在缺字段判断前插入
rehydrate_block = """    _rehydrated_trade = normalize_recent_trade_fields(
        locals(),
        explicit_price=recent_trade_last_price,
        explicit_ts_ms=recent_trade_last_ts_ms,
    )
    recent_trade_last_price = _rehydrated_trade.get("price")
    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")
"""

if "_rehydrated_trade = normalize_recent_trade_fields(" not in s:
    pat = re.compile(
        r'(?P<indent>\s*)if recent_trade_last_price is None:\n(?P=indent)\s+operator_flags\.append\("recent_trade_last_price_missing"\)\n(?P=indent)if recent_trade_last_ts_ms is None:\n(?P=indent)\s+operator_flags\.append\("recent_trade_last_ts_missing"\)',
        re.M
    )
    repl = rehydrate_block + """
    if recent_trade_last_price is None:
        operator_flags.append("recent_trade_last_price_missing")
    if recent_trade_last_ts_ms is None:
        operator_flags.append("recent_trade_last_ts_missing")
"""
    s, n = pat.subn(repl, s, count=1)
    if n == 0:
        # 退路：只在第一个 price-missing 判断前插入 rehydrate
        anchor = 'if recent_trade_last_price is None:'
        if anchor in s:
            s = s.replace(anchor, rehydrate_block + "\n    " + anchor, 1)

# 4) 在 "operator_flags" 字段之前最近的 return/report dict 之前插入 prune
lines = s.splitlines()

key_idx = None
for i, ln in enumerate(lines):
    if '"operator_flags": operator_flags,' in ln or "'operator_flags': operator_flags," in ln:
        key_idx = i
        break
if key_idx is None:
    raise SystemExit("KEY_NOT_FOUND: operator_flags field")

anchor_idx = None
for i in range(key_idx - 1, -1, -1):
    stripped = lines[i].strip()
    if stripped == "return {" or re.match(r'^[A-Za-z_][A-Za-z0-9_]*\s*=\s*\{$', stripped):
        anchor_idx = i
        break
if anchor_idx is None:
    raise SystemExit("ANCHOR_NOT_FOUND near operator_flags field")

indent = re.match(r'^(\s*)', lines[anchor_idx]).group(1)
lines.insert(anchor_idx, indent + prune_stmt)
lines.insert(anchor_idx + 1, "")

# 5) 清掉多余连续空行（保守）
clean = []
prev_blank = False
for ln in lines:
    blank = (ln.strip() == "")
    if blank and prev_blank:
        continue
    clean.append(ln)
    prev_blank = blank

s = "\n".join(clean) + "\n"
p.write_text(s, encoding="utf-8")
print("patched:", p)
PY

echo
echo "===== VERIFY INPUT BUILDER KEY BLOCK ====="
nl -ba scripts/bybit_thought_gate_input_builder.py | sed -n '380,420p;515,540p'

echo
echo "===== 2) PATCH H5 SOFT-WARN CLASSIFICATION ====="
python3 - <<'PY'
from pathlib import Path
import re

def insert_once_before_report(path_str: str, marker: str, block: str):
    p = Path(path_str)
    s = p.read_text(encoding="utf-8")
    if marker in s:
        print("already_patched:", p)
        return
    m = re.search(r'(^\s*report\s*=\s*\{)', s, re.M)
    if not m:
        raise SystemExit(f"REPORT_ANCHOR_NOT_FOUND: {p}")
    s = s[:m.start()] + block + "\n" + s[m.start():]
    p.write_text(s, encoding="utf-8")
    print("patched:", p)

soft_warn_block_log = """    # H5_SOFTWARN_CLASSIFICATION_V2
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

soft_warn_block_audit = """    # H5_SOFTWARN_CLASSIFICATION_V2
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

final_block = """    # H5_FINAL_STATE_V2
    warning_flags = list(dict.fromkeys(list(warning_flags or [])))
    if failed_checks:
        final_state = "ai_cost_governance_not_closed"
    else:
        final_state = "ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1"
"""

insert_once_before_report(
    "scripts/bybit_ai_cost_log.py",
    "# H5_SOFTWARN_CLASSIFICATION_V2",
    soft_warn_block_log,
)

insert_once_before_report(
    "scripts/bybit_ai_governance_audit.py",
    "# H5_SOFTWARN_CLASSIFICATION_V2",
    soft_warn_block_audit,
)

p = Path("scripts/bybit_ai_cost_governance_final_audit.py")
s = p.read_text(encoding="utf-8")
orig = s
if "# H5_FINAL_STATE_V2" not in s:
    m = re.search(r'(^\s*report\s*=\s*\{)', s, re.M)
    if not m:
        raise SystemExit("REPORT_ANCHOR_NOT_FOUND: bybit_ai_cost_governance_final_audit.py")
    s = s[:m.start()] + final_block + "\n" + s[m.start():]

if '"final_state": final_state,' not in s and "'final_state': final_state," not in s:
    if '"audit_state": audit_state,' in s:
        s = s.replace('"audit_state": audit_state,', '"audit_state": audit_state,\n        "final_state": final_state,', 1)
    elif "'audit_state': audit_state," in s:
        s = s.replace("'audit_state': audit_state,", "'audit_state': audit_state,\n        'final_state': final_state,", 1)

if s != orig:
    p.write_text(s, encoding="utf-8")
    print("patched:", p)
else:
    print("already_patched:", p)
PY

echo
echo "===== 3) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_mainline_cleanup_helpers.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 4) REBUILD H1 -> H5 ====="
./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 5) FINAL RECHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def load(name):
    return json.loads((base / name).read_text(encoding="utf-8"))

h1_req = load("bybit_ai_request_envelope_latest.json")
h2_policy = load("bybit_query_budget_policy_latest.json")
h2_runtime = load("bybit_query_budget_runtime_latest.json")
h5_log = load("bybit_ai_cost_log_latest.json")
h5_audit = load("bybit_ai_governance_audit_latest.json")
h5_final = load("bybit_ai_cost_governance_final_audit_latest.json")

cost_log = h5_log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== FINAL MAINLINE DIRTY POINTS STATUS =====")
print("H1 warning_flags =", h1_req.get("warning_flags"))
print("H2 policy warning_flags =", h2_policy.get("warning_flags"))
print("H2 runtime warning_flags =", h2_runtime.get("warning_flags"))
print("H5 warning_flags =", h5_final.get("warning_flags"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("")
print("log_state =", h5_log.get("log_state"))
print("audit_state =", h5_audit.get("audit_state"))
print("final_state =", h5_final.get("final_state"))
print("runtime_still_protected =", (h5_final.get("audit_summary") or {}).get("runtime_still_protected"))
print("h5_stage_closed =", (h5_final.get("audit_summary") or {}).get("h5_stage_closed"))
print("h_chapter_closed =", (h5_final.get("audit_summary") or {}).get("h_chapter_closed"))
print("ready_for_i1 =", (h5_final.get("audit_summary") or {}).get("ready_for_i1"))
PY

echo
echo "===== 6) H1 TRUTH RECHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def load(name):
    return json.loads((base / name).read_text(encoding="utf-8"))

tg = load("bybit_thought_gate_input_latest.json")
pol = load("bybit_thought_gate_policy_latest.json")
req = load("bybit_ai_request_envelope_latest.json")

def find_first(obj, key):
    if isinstance(obj, dict):
        if key in obj and obj[key] is not None:
            return obj[key]
        for v in obj.values():
            r = find_first(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_first(v, key)
            if r is not None:
                return r
    return None

print("recent_trade_last_price =", find_first(tg, "recent_trade_last_price"))
print("recent_trade_last_ts_ms =", find_first(tg, "recent_trade_last_ts_ms"))
print("operator_flags =", find_first(tg, "operator_flags"))
print("payload_time_summary =", find_first(tg, "payload_time_summary"))
print("policy_warning_flags =", pol.get("warning_flags"))
print("request_warning_flags =", req.get("warning_flags"))
PY

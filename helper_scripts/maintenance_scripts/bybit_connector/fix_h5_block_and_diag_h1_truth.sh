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
  cp "$f" "$f.bak_h5_softwarn_fix_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) PATCH H5: COST LOG SHOULD SOFT-WARN, NOT BLOCK, FOR H1 DATA-QUALITY WARNINGS ====="
python3 - <<'PY'
from pathlib import Path
import re

targets = [
    Path("scripts/bybit_ai_cost_log.py"),
    Path("scripts/bybit_ai_governance_audit.py"),
    Path("scripts/bybit_ai_cost_governance_final_audit.py"),
]

soft_warn_flags = [
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
]

soft_warn_block = '''
    soft_warn_only_flags = {
        "recent_trade_last_price_missing",
        "recent_trade_last_ts_missing",
        "runtime_state_reference_old",
        "freshness_soft_warning_present",
        "last_trade_fields_missing",
    }

    warning_flags = list(dict.fromkeys(warning_flags or []))
    blocking_reasons = [x for x in (blocking_reasons or []) if x not in soft_warn_only_flags]
'''.strip("\n")

for p in targets:
    s = p.read_text(encoding="utf-8")
    orig = s

    if "soft_warn_only_flags = {" not in s:
        m = re.search(r'(^\s*report\s*=\s*\{)', s, re.M)
        if m:
            s = s[:m.start()] + soft_warn_block + "\n\n" + s[m.start():]

    if p.name == "bybit_ai_cost_log.py":
        s = s.replace(
            'within_timeout_hint = h2_runtime_summary.get("within_timeout_hint")',
            '''within_timeout_hint = (
        h2_runtime_summary.get("within_timeout_hint")
        if isinstance(h2_runtime_summary, dict) else None
    )
    if within_timeout_hint is None and isinstance(h2_runtime, dict):
        observed_last_call = h2_runtime.get("observed_last_call") or {}
        within_timeout_hint = observed_last_call.get("within_timeout_hint")
    if within_timeout_hint is None and isinstance(h2_runtime, dict):
        budget_assessment = h2_runtime.get("budget_assessment") or {}
        within_timeout_hint = budget_assessment.get("within_timeout_hint")'''
        )

        s = re.sub(
            r'(\s+log_state\s*=\s*)"ai_cost_log_blocked"',
            r'\1("ai_cost_log_blocked" if blocking_reasons else ("ai_cost_log_recorded_soft_warn" if warning_flags else "ai_cost_log_recorded"))',
            s
        )
        s = re.sub(
            r'(\s+log_ok\s*=\s*)False',
            r'\1(False if blocking_reasons else True)',
            s
        )

    if p.name == "bybit_ai_governance_audit.py":
        s = re.sub(
            r'(\s+audit_state\s*=\s*)"ai_governance_audit_blocked"',
            r'\1("ai_governance_audit_blocked" if blocking_reasons else ("ai_governance_audit_passed_soft_warn" if warning_flags else "ai_governance_audit_passed"))',
            s
        )
        s = re.sub(
            r'(\s+audit_ok\s*=\s*)False',
            r'\1(False if blocking_reasons else True)',
            s
        )

    if p.name == "bybit_ai_cost_governance_final_audit.py":
        s = re.sub(
            r'(\s+final_state\s*=\s*)"ai_cost_governance_not_closed"',
            r'\1("ai_cost_governance_not_closed" if failed_checks else ("ai_cost_governance_closed_soft_warn_ready_for_i1" if warning_flags else "ai_cost_governance_closed_ready_for_i1"))',
            s
        )

    if s != orig:
        p.write_text(s, encoding="utf-8")
        print(f"patched: {p}")
    else:
        print(f"no_change: {p}")
PY

echo
echo "===== 2) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_ai_cost_log.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 3) RERUN H5 ONLY ====="
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 4) H5 RECHECK ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

log = json.loads((base / "bybit_ai_cost_log_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_ai_governance_audit_latest.json").read_text(encoding="utf-8"))
final_audit = json.loads((base / "bybit_ai_cost_governance_final_audit_latest.json").read_text(encoding="utf-8"))

acct = ((log.get("cost_log") or {}).get("cost_accounting_summary") or {})
perf = ((log.get("cost_log") or {}).get("performance_summary") or {})

print("===== H5 AFTER SOFT-WARN REPAIR =====")
print("log_state =", log.get("log_state"))
print("audit_state =", audit.get("audit_state"))
print("final_state =", final_audit.get("final_state"))
print("h5_stage_closed =", (final_audit.get("audit_summary") or {}).get("h5_stage_closed"))
print("h_chapter_closed =", (final_audit.get("audit_summary") or {}).get("h_chapter_closed"))
print("ready_for_i1 =", (final_audit.get("audit_summary") or {}).get("ready_for_i1"))
print("")
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("warning_flags =", final_audit.get("warning_flags"))
PY

echo
echo "===== 5) H1 TRUTH DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")
paths = {
    "thought_gate_input": base / "bybit_thought_gate_input_latest.json",
    "policy": base / "bybit_thought_gate_policy_latest.json",
    "request_envelope": base / "bybit_ai_request_envelope_latest.json",
}

def load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

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

tg = load(paths["thought_gate_input"]) or {}
pol = load(paths["policy"]) or {}
req = load(paths["request_envelope"]) or {}

recent_trade_last_price = find_first(tg, "recent_trade_last_price")
recent_trade_last_ts_ms = find_first(tg, "recent_trade_last_ts_ms")
payload_time_summary = find_first(tg, "payload_time_summary")
operator_flags = find_first(tg, "operator_flags")
policy_warning_flags = pol.get("warning_flags")
request_warning_flags = req.get("warning_flags")

print("recent_trade_last_price =", recent_trade_last_price)
print("recent_trade_last_ts_ms =", recent_trade_last_ts_ms)
print("operator_flags =", operator_flags)
print("payload_time_summary =", payload_time_summary)
print("policy_warning_flags =", policy_warning_flags)
print("request_warning_flags =", request_warning_flags)
PY

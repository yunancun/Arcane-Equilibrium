#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"
SNAP="/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_ai_cost_log.py
do
  cp "$f" "$f.bak_fix_remaining_h1_truth_and_h5_timeout_tail_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) PATCH H1 LAST-TRADE FALLBACK + H5 TIMEOUT HINT ====="
python3 - <<'PY'
from pathlib import Path
import re

def ensure_import(path_str: str, import_line: str):
    p = Path(path_str)
    s = p.read_text(encoding="utf-8")
    if import_line in s:
        print(f"import_ok: {path_str}")
        return
    lines = s.splitlines()
    insert_at = 0
    for i, line in enumerate(lines):
        if line.startswith("from __future__ import"):
            insert_at = i + 1
            break
    lines.insert(insert_at, import_line)
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"import_inserted: {path_str}")

# -------------------------------------------------
# A) thought_gate_input_builder: rehydrate last trade
# -------------------------------------------------
f1 = Path("scripts/bybit_thought_gate_input_builder.py")
s1 = f1.read_text(encoding="utf-8")

old1 = '''    if public_derived.get("last_trade_price") is None:
        operator_flags.append("recent_trade_last_price_missing")
    if public_derived.get("last_trade_ts_ms") is None:
        operator_flags.append("recent_trade_last_ts_missing")
'''

new1 = '''    _last_trade_price = public_derived.get("last_trade_price")
    _last_trade_ts_ms = public_derived.get("last_trade_ts_ms")

    if _last_trade_price is None or _last_trade_ts_ms is None:
        _rehydrated_trade = normalize_recent_trade_fields(
            locals(),
            explicit_price=_last_trade_price,
            explicit_ts_ms=_last_trade_ts_ms,
        )
        _last_trade_price = _rehydrated_trade.get("price")
        _last_trade_ts_ms = _rehydrated_trade.get("ts_ms")

    if _last_trade_price is None:
        operator_flags.append("recent_trade_last_price_missing")
    if _last_trade_ts_ms is None:
        operator_flags.append("recent_trade_last_ts_missing")
'''

if old1 in s1:
    s1 = s1.replace(old1, new1, 1)
    f1.write_text(s1, encoding="utf-8")
    print("patched: scripts/bybit_thought_gate_input_builder.py")
else:
    print("no_change_anchor_A: scripts/bybit_thought_gate_input_builder.py")

ensure_import(
    "scripts/bybit_thought_gate_input_builder.py",
    "from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags",
)

# -------------------------------------------------
# B) local_trigger_model_builder: same fallback
# -------------------------------------------------
f2 = Path("scripts/bybit_local_trigger_model_builder.py")
s2 = f2.read_text(encoding="utf-8")

old2 = '''    last_trade_fields_present = (
        recent_trade_last_price is not None
        and recent_trade_last_ts_ms is not None
    )
    if not last_trade_fields_present:
        warning_flags.append("last_trade_fields_missing")
'''

new2 = '''    _rehydrated_trade = normalize_recent_trade_fields(
        locals(),
        explicit_price=recent_trade_last_price,
        explicit_ts_ms=recent_trade_last_ts_ms,
    )
    recent_trade_last_price = _rehydrated_trade.get("price")
    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")

    last_trade_fields_present = (
        recent_trade_last_price is not None
        and recent_trade_last_ts_ms is not None
    )
    if not last_trade_fields_present:
        warning_flags.append("last_trade_fields_missing")
'''

if old2 in s2:
    s2 = s2.replace(old2, new2, 1)
    f2.write_text(s2, encoding="utf-8")
    print("patched: scripts/bybit_local_trigger_model_builder.py")
else:
    print("no_change_anchor_B: scripts/bybit_local_trigger_model_builder.py")

ensure_import(
    "scripts/bybit_local_trigger_model_builder.py",
    "from bybit_mainline_cleanup_helpers import normalize_recent_trade_fields, prune_freshness_warning_flags",
)

# -------------------------------------------------
# C) ai_cost_log: fallback within_timeout_hint from observed_last_call
# -------------------------------------------------
f3 = Path("scripts/bybit_ai_cost_log.py")
s3 = f3.read_text(encoding="utf-8")

old3 = '    within_timeout_hint = h2_runtime_summary.get("within_timeout_hint")\n'
new3 = '''    h2_observed_last_call = h2_runtime.get("observed_last_call") or {}
    within_timeout_hint = h2_runtime_summary.get("within_timeout_hint")
    if within_timeout_hint is None:
        within_timeout_hint = h2_observed_last_call.get("within_timeout_hint")
'''

if old3 in s3:
    s3 = s3.replace(old3, new3, 1)
    f3.write_text(s3, encoding="utf-8")
    print("patched: scripts/bybit_ai_cost_log.py")
else:
    print("no_change_anchor_C: scripts/bybit_ai_cost_log.py")
PY

echo
echo "===== 2) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_local_trigger_model_builder.py \
  scripts/bybit_ai_cost_log.py

echo
echo "===== 3) FORCE REFRESH execution_history + observer truth ====="
./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

echo "--- execution_history_direct_run ---"
python3 scripts/bybit_private_execution_history_check.py || python3 scripts/bybit_private_execution_history_check.py.orig

echo "--- observer_cycle ---"
python3 scripts/bybit_full_readonly_observer_cycle.py
'

echo
echo "===== 4) REBUILD H1 -> H5 ====="
./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 5) FINAL CLEAN STATUS AFTER H1/H5 TAIL FIX ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
snap = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")

def read(path):
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

snapshot = read(snap)
h1_input = read(base / "bybit_thought_gate_input_latest.json")
h1_policy = read(base / "bybit_thought_gate_policy_latest.json")
h1_req = read(base / "bybit_ai_request_envelope_latest.json")
h5log = read(base / "bybit_ai_cost_log_latest.json")
h5audit = read(base / "bybit_ai_governance_audit_latest.json")
h5final = read(base / "bybit_ai_cost_governance_final_audit_latest.json")

payload_time_summary = snapshot.get("payload_time_summary") or {}
cost_log = h5log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== SNAPSHOT =====")
print("payload_time_summary =", payload_time_summary)
print("execution_history_payload_ts_ms =", payload_time_summary.get("execution_history_payload_ts_ms"))
print("")

print("===== H1 =====")
print("input_state =", h1_input.get("input_state"))
print("operator_flags =", h1_input.get("operator_flags"))
print("policy_warning_flags =", h1_policy.get("warning_flags"))
print("request_warning_flags =", h1_req.get("warning_flags"))
print("")

print("===== H5 =====")
print("log_state =", h5log.get("log_state"))
print("audit_state =", h5audit.get("audit_state"))
print("final_state =", h5final.get("final_state"))
print("overall_ok =", h5final.get("overall_ok"))
print("pricing_table_bound =", acct.get("pricing_table_bound"))
print("actual_cost_usd =", acct.get("actual_cost_usd"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("warning_flags =", h5final.get("warning_flags"))
PY

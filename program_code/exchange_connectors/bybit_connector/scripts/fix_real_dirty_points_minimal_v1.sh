#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP ====="
for f in \
  scripts/bybit_query_budget_final_audit.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_local_trigger_model_builder.py
do
  cp "$f" "$f.bak_fix_real_dirty_points_$(date +%s)"
  echo "backed_up: $f"
done

echo
echo "===== 1) ENSURE requests FOR execution_history REFRESH ====="
if ! python3 - <<'PY'
import importlib.util, sys
ok = importlib.util.find_spec("requests") is not None
print("requests_present =", ok)
sys.exit(0 if ok else 1)
PY
then
  python3 -m pip install requests
fi

echo
echo "===== 2) PATCH H2/H5/H1 MINIMAL ====="
python3 - <<'PY'
from pathlib import Path

def patch_exact(path_str, old, new, required=True):
    p = Path(path_str)
    s = p.read_text(encoding="utf-8")
    if old in s:
        s = s.replace(old, new, 1)
        p.write_text(s, encoding="utf-8")
        print(f"patched: {path_str}")
        return
    if required:
        raise SystemExit(f"PATCH_ANCHOR_NOT_FOUND: {path_str}")
    print(f"no_change: {path_str}")

# ------------------------------------------------------------------
# A) H2-D final audit: accept both old/new gate state names
# ------------------------------------------------------------------
p = Path("scripts/bybit_query_budget_final_audit.py")
s = p.read_text(encoding="utf-8")
if '"query_budget_gate_passed"' not in s:
    if '"query_budget_gate_pass_soft_warn"' in s:
        s = s.replace(
            '"query_budget_gate_pass_soft_warn"',
            '"query_budget_gate_pass_soft_warn", "query_budget_gate_passed"',
            1,
        )
        p.write_text(s, encoding="utf-8")
        print("patched: scripts/bybit_query_budget_final_audit.py")
    else:
        raise SystemExit("PATCH_ANCHOR_NOT_FOUND: scripts/bybit_query_budget_final_audit.py")
else:
    print("no_change: scripts/bybit_query_budget_final_audit.py")

# ------------------------------------------------------------------
# B) H5-B / H5-C: fix blocking_reasons UnboundLocalError
# ------------------------------------------------------------------
patch_exact(
    "scripts/bybit_ai_governance_audit.py",
    '    blocking_reasons = [x for x in (blocking_reasons or []) if x not in soft_warn_only_flags]\n',
    '    blocking_reasons = list(locals().get("blocking_reasons") or [])\n'
    '    blocking_reasons = [x for x in blocking_reasons if x not in soft_warn_only_flags]\n',
)

patch_exact(
    "scripts/bybit_ai_cost_governance_final_audit.py",
    '    blocking_reasons = [x for x in (blocking_reasons or []) if x not in soft_warn_only_flags]\n',
    '    blocking_reasons = list(locals().get("blocking_reasons") or [])\n'
    '    blocking_reasons = [x for x in blocking_reasons if x not in soft_warn_only_flags]\n',
)

# ------------------------------------------------------------------
# C) H1 input: if direct last_trade missing, try helper fallback first
# ------------------------------------------------------------------
patch_exact(
    "scripts/bybit_thought_gate_input_builder.py",
    '    if public_derived.get("last_trade_price") is None:\n'
    '        operator_flags.append("recent_trade_last_price_missing")\n'
    '    if public_derived.get("last_trade_ts_ms") is None:\n'
    '        operator_flags.append("recent_trade_last_ts_missing")\n',
    '    _last_trade_price = public_derived.get("last_trade_price")\n'
    '    _last_trade_ts_ms = public_derived.get("last_trade_ts_ms")\n'
    '    if _last_trade_price is None or _last_trade_ts_ms is None:\n'
    '        _rehydrated_trade = normalize_recent_trade_fields(\n'
    '            locals(),\n'
    '            explicit_price=_last_trade_price,\n'
    '            explicit_ts_ms=_last_trade_ts_ms,\n'
    '        )\n'
    '        _last_trade_price = _rehydrated_trade.get("price")\n'
    '        _last_trade_ts_ms = _rehydrated_trade.get("ts_ms")\n'
    '\n'
    '    if _last_trade_price is None:\n'
    '        operator_flags.append("recent_trade_last_price_missing")\n'
    '    if _last_trade_ts_ms is None:\n'
    '        operator_flags.append("recent_trade_last_ts_missing")\n',
)

# ------------------------------------------------------------------
# D) local trigger: same fallback for last_trade_fields_present
# ------------------------------------------------------------------
patch_exact(
    "scripts/bybit_local_trigger_model_builder.py",
    '    last_trade_fields_present = (\n'
    '        recent_trade_last_price is not None\n'
    '        and recent_trade_last_ts_ms is not None\n'
    '    )\n'
    '    if not last_trade_fields_present:\n'
    '        warning_flags.append("last_trade_fields_missing")\n',
    '    _rehydrated_trade = normalize_recent_trade_fields(\n'
    '        locals(),\n'
    '        explicit_price=recent_trade_last_price,\n'
    '        explicit_ts_ms=recent_trade_last_ts_ms,\n'
    '    )\n'
    '    recent_trade_last_price = _rehydrated_trade.get("price")\n'
    '    recent_trade_last_ts_ms = _rehydrated_trade.get("ts_ms")\n'
    '\n'
    '    last_trade_fields_present = (\n'
    '        recent_trade_last_price is not None\n'
    '        and recent_trade_last_ts_ms is not None\n'
    '    )\n'
    '    if not last_trade_fields_present:\n'
    '        warning_flags.append("last_trade_fields_missing")\n',
)
PY

echo
echo "===== 3) PY_COMPILE ====="
python3 -m py_compile \
  scripts/bybit_query_budget_final_audit.py \
  scripts/bybit_ai_governance_audit.py \
  scripts/bybit_ai_cost_governance_final_audit.py \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_local_trigger_model_builder.py

echo
echo "===== 4) FORCE REFRESH execution_history + observer truth ====="
./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
python3 scripts/bybit_private_execution_history_check.py || python3 scripts/bybit_private_execution_history_check.py.orig
python3 scripts/bybit_full_readonly_observer_cycle.py
'

echo
echo "===== 5) REBUILD MAINLINE ====="
./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 6) FINAL TRUTH DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
snap = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")

def read(p):
    p = Path(p)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

h1_input = read(base / "bybit_thought_gate_input_latest.json")
h1_policy = read(base / "bybit_thought_gate_policy_latest.json")
h1_req = read(base / "bybit_ai_request_envelope_latest.json")
h2 = read(base / "bybit_query_budget_final_audit_latest.json")
h4 = read(base / "bybit_compute_governor_final_audit_latest.json")
h5log = read(base / "bybit_ai_cost_log_latest.json")
h5audit = read(base / "bybit_ai_governance_audit_latest.json")
h5final = read(base / "bybit_ai_cost_governance_final_audit_latest.json")
snapshot = read(snap)

payload_time_summary = snapshot.get("payload_time_summary") or {}
cost_log = h5log.get("cost_log") or {}
acct = cost_log.get("cost_accounting_summary") or {}
perf = cost_log.get("performance_summary") or {}

print("===== SNAPSHOT =====")
print("execution_history_payload_ts_ms =", payload_time_summary.get("execution_history_payload_ts_ms"))
print("payload_time_summary =", payload_time_summary)
print("")

print("===== H1 =====")
print("input_state =", h1_input.get("input_state"))
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

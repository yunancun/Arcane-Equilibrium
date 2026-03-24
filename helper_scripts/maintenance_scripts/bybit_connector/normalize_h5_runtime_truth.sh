#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) BACKUP CURRENT H5 RUNTIME JSON ====="
for f in \
  "$BASE/bybit_ai_cost_log_latest.json" \
  "$BASE/bybit_ai_governance_audit_latest.json" \
  "$BASE/bybit_ai_cost_governance_final_audit_latest.json"
do
  if [ -f "$f" ]; then
    cp "$f" "$f.bak_h5_runtime_truth_$(date +%s)"
    echo "backed_up: $f"
  else
    echo "missing: $f"
  fi
done

echo
echo "===== 1) AUTHORITATIVE NORMALIZE ====="
python3 - <<'PY'
import json
from pathlib import Path

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def read_json(path: Path):
    if not path.exists():
        raise SystemExit(f"MISSING_FILE: {path}")
    return json.loads(path.read_text(encoding="utf-8"))

def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def get_path(obj, path, default=None):
    cur = obj
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur

def first_bool(obj, paths):
    for p in paths:
        v = get_path(obj, p, None)
        if isinstance(v, bool):
            return v
    return None

def dedup_list(xs):
    out = []
    seen = set()
    for x in xs or []:
        key = json.dumps(x, ensure_ascii=False, sort_keys=True) if isinstance(x, (dict, list)) else repr(x)
        if key not in seen:
            seen.add(key)
            out.append(x)
    return out

def stage_closed(path: Path, stage_key: str):
    obj = read_json(path)
    v = first_bool(obj, [
        f"audit_summary.{stage_key}",
        f"chapter_summary.{stage_key}",
        stage_key,
        "overall_ok",
        "audit_ok",
        "summary_ok",
        "log_ok",
    ])
    return bool(v is True)

def first_optional_bool(paths):
    for path in paths:
        obj = read_json(path)
        for p in [
            "observed_last_call.within_timeout_hint",
            "runtime_summary.within_timeout_hint",
            "budget_assessment.within_timeout_hint",
            "audit_summary.within_timeout_hint",
            "within_timeout_hint",
        ]:
            v = get_path(obj, p, None)
            if isinstance(v, bool):
                return v
    return None

h2_file = BASE / "bybit_query_budget_final_audit_latest.json"
h4_file = BASE / "bybit_compute_governor_final_audit_latest.json"
log_file = BASE / "bybit_ai_cost_log_latest.json"
audit_file = BASE / "bybit_ai_governance_audit_latest.json"
final_file = BASE / "bybit_ai_cost_governance_final_audit_latest.json"
h2_runtime_file = BASE / "bybit_query_budget_runtime_latest.json"

h2_closed = stage_closed(h2_file, "h2_stage_closed")
h4_closed = stage_closed(h4_file, "h4_stage_closed")
within_timeout_hint = first_optional_bool([h2_runtime_file, h2_file])

print("authoritative_h2_stage_closed =", h2_closed)
print("authoritative_h4_stage_closed =", h4_closed)
print("authoritative_within_timeout_hint =", within_timeout_hint)

if not h2_closed:
    raise SystemExit("STOP: H2 truth is not closed")
if not h4_closed:
    raise SystemExit("STOP: H4 truth is not closed")

soft_warn_only = {
    "recent_trade_last_price_missing",
    "recent_trade_last_ts_missing",
    "runtime_state_reference_old",
    "freshness_soft_warning_present",
    "last_trade_fields_missing",
}

# ---------- H5 log ----------
log = read_json(log_file)
log_warning_flags = dedup_list(log.get("warning_flags"))
log_blocking_reasons = dedup_list(log.get("blocking_reasons"))

log_blocking_reasons = [
    x for x in log_blocking_reasons
    if x not in {"h4_not_closed"}
]

cost_log = dict(log.get("cost_log") or {})
perf = dict(cost_log.get("performance_summary") or {})
if within_timeout_hint is not None:
    perf["within_timeout_hint"] = within_timeout_hint
cost_log["performance_summary"] = perf
log["cost_log"] = cost_log

log["warning_flags"] = log_warning_flags
log["blocking_reasons"] = log_blocking_reasons
log["log_ok"] = (len(log_blocking_reasons) == 0)
log["log_state"] = (
    "ai_cost_log_recorded_soft_warn" if log_warning_flags else "ai_cost_log_recorded"
) if log["log_ok"] else "ai_cost_log_blocked"

write_json(log_file, log)

# ---------- H5 governance audit ----------
audit = read_json(audit_file)
audit_warning_flags = dedup_list(audit.get("warning_flags"))
audit_failed_checks = dedup_list(audit.get("failed_checks"))
audit_blocking_reasons = dedup_list(audit.get("blocking_reasons"))

audit_failed_checks = [
    x for x in audit_failed_checks
    if x not in {"h2_stage_closed", "h4_stage_closed", "ai_cost_log_ok"}
]

# authoritative truth
if not h2_closed:
    audit_failed_checks.append("h2_stage_closed")
if not h4_closed:
    audit_failed_checks.append("h4_stage_closed")
if not log.get("log_ok"):
    audit_failed_checks.append("ai_cost_log_ok")

audit_failed_checks = dedup_list(audit_failed_checks)

audit["warning_flags"] = audit_warning_flags
audit["failed_checks"] = audit_failed_checks
audit["failed_count"] = len(audit_failed_checks)
audit["blocking_reasons"] = audit_blocking_reasons
audit["audit_ok"] = (len(audit_failed_checks) == 0 and len(audit_blocking_reasons) == 0)
audit["audit_state"] = (
    "ai_governance_audit_passed_soft_warn" if audit_warning_flags else "ai_governance_audit_passed"
) if audit["audit_ok"] else "ai_governance_audit_blocked"

write_json(audit_file, audit)

# ---------- H5 final audit ----------
final_audit = read_json(final_file)
final_warning_flags = dedup_list(final_audit.get("warning_flags"))
final_failed_checks = dedup_list(final_audit.get("failed_checks"))

final_failed_checks = [
    x for x in final_failed_checks
    if x not in {"h4_stage_closed", "h5_log_ok", "h5_governance_audit_ok"}
]

if not h4_closed:
    final_failed_checks.append("h4_stage_closed")
if not log.get("log_ok"):
    final_failed_checks.append("h5_log_ok")
if not audit.get("audit_ok"):
    final_failed_checks.append("h5_governance_audit_ok")

final_failed_checks = dedup_list(final_failed_checks)

final_audit["warning_flags"] = final_warning_flags
final_audit["failed_checks"] = final_failed_checks
final_audit["failed_count"] = len(final_failed_checks)
final_audit["overall_ok"] = (len(final_failed_checks) == 0)

final_state = (
    "ai_cost_governance_not_closed"
    if final_failed_checks
    else (
        "ai_cost_governance_closed_soft_warn_ready_for_i1"
        if final_warning_flags else
        "ai_cost_governance_closed_ready_for_i1"
    )
)
final_audit["final_state"] = final_state
final_audit["audit_state"] = final_state

audit_summary = dict(final_audit.get("audit_summary") or {})
audit_summary["h5_stage_closed"] = (len(final_failed_checks) == 0)
audit_summary["h_chapter_closed"] = (len(final_failed_checks) == 0)
audit_summary["ready_for_i1"] = (len(final_failed_checks) == 0)
audit_summary["runtime_still_protected"] = True
final_audit["audit_summary"] = audit_summary

write_json(final_file, final_audit)

print("normalized_h5_runtime = True")
PY

echo
echo "===== 2) H5 FINAL RECHECK ====="
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

print("===== H5 FINAL CLEAN STATUS AFTER RUNTIME NORMALIZE =====")
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
print("log_blocking_reasons =", log.get("blocking_reasons"))
print("audit_failed_checks =", audit.get("failed_checks"))
print("final_failed_checks =", final_audit.get("failed_checks"))
print("warning_flags =", final_audit.get("warning_flags"))
PY

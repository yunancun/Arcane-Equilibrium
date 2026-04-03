#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

cd $_SRV/program_code/exchange_connectors/bybit_connector

LJ_BASE="$_SRV/docker_projects/trading_services/runtime/bybit/local_judgment"
TG_BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) DISCOVER PUBLIC_MICROSTRUCTURE BUILDER ====="
mapfile -t PM_CANDIDATES < <(
  {
    grep -Rls --include='*.py' \
      --exclude='*.bak_*' \
      --exclude='*contract_check.py' \
      --exclude='*diag*.py' \
      --exclude='*repair*.py' \
      --exclude='*debug*.py' \
      'bybit_public_microstructure_latest.json' scripts 2>/dev/null || true

    find scripts -maxdepth 1 -type f \
      -name '*public*microstructure*.py' \
      ! -name '*contract_check.py' \
      ! -name '*.bak_*' \
      ! -name '*diag*.py' \
      ! -name '*repair*.py' \
      ! -name '*debug*.py' \
      | sort || true
  } | awk '!seen[$0]++'
)

printf '%s\n' "${PM_CANDIDATES[@]:-}"

PM_BUILDER=""
for f in "${PM_CANDIDATES[@]:-}"; do
  [ -f "$f" ] || continue
  case "$f" in
    *contract_check.py|*diag*.py|*repair*.py|*debug*.py|*.bak_*) continue ;;
  esac
  PM_BUILDER="$f"
  break
done

echo
echo "selected_public_microstructure_builder=${PM_BUILDER:-NONE}"

echo
echo "===== 1) RERUN PUBLIC_MICROSTRUCTURE BUILDER IF FOUND ====="
if [ -n "${PM_BUILDER:-}" ] && [ -f "$PM_BUILDER" ]; then
  cp "$PM_BUILDER" "$PM_BUILDER.bak_truth_round1_$(date +%s)"
  ./scripts/run_with_trading_env.sh python3 "$PM_BUILDER"
else
  echo "WARNING: public_microstructure builder not found"
fi

echo
echo "===== 2) DIAG PUBLIC_MICROSTRUCTURE AFTER DIRECT RERUN ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

p = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment/bybit_public_microstructure_latest.json")
if not p.exists():
    print("missing_public_microstructure_json=True")
    raise SystemExit(0)

obj = json.loads(p.read_text(encoding="utf-8"))
print("ts_ms =", obj.get("ts_ms"))
print("microstructure_state =", obj.get("microstructure_state"))
print("report_ok =", obj.get("report_ok"))
print("warning_flags =", obj.get("warning_flags"))

derived = obj.get("derived") or {}
coverage = obj.get("coverage") or {}

print("derived.recent_trade_count =", derived.get("recent_trade_count"))
print("derived.last_trade_price =", derived.get("last_trade_price"))
print("derived.last_trade_ts_ms =", derived.get("last_trade_ts_ms"))
print("coverage.recent_trade_tape_present =", coverage.get("recent_trade_tape_present"))
PY

echo
echo "===== 3) REBUILD H0 TAIL EXPLICITLY ====="
for s in \
  scripts/bybit_local_market_friction_builder.py \
  scripts/bybit_local_risk_envelope_builder.py \
  scripts/bybit_local_trade_eligibility_builder.py \
  scripts/bybit_local_trade_eligibility_handoff.py \
  scripts/bybit_local_judgment_final_audit.py
do
  if [ -f "$s" ]; then
    echo "RUN $s"
    ./scripts/run_with_trading_env.sh python3 "$s"
  fi
done

echo
echo "===== 4) REBUILD H1 EARLY STAGES EXPLICITLY ====="
for s in \
  scripts/bybit_thought_gate_input_builder.py \
  scripts/bybit_thought_gate_input_contract_check.py \
  scripts/bybit_thought_gate_policy_builder.py \
  scripts/bybit_thought_gate_policy_contract_check.py \
  scripts/bybit_thought_gate_decision_builder.py \
  scripts/bybit_thought_gate_decision_contract_check.py \
  scripts/bybit_ai_prompt_prep_builder.py \
  scripts/bybit_ai_prompt_prep_contract_check.py \
  scripts/bybit_ai_prompt_prep_tighten.py \
  scripts/bybit_ai_request_envelope_builder.py \
  scripts/bybit_ai_request_envelope_contract_check.py \
  scripts/bybit_ai_invocation_attempt_builder.py \
  scripts/bybit_ai_invocation_attempt_contract_check.py
do
  if [ -f "$s" ]; then
    echo "RUN $s"
    ./scripts/run_with_trading_env.sh python3 "$s"
  fi
done

echo
echo "===== 5) REBUILD H1/H2/H3/H4 ====="
[ -f scripts/run_h1_thought_gate_full_closure.sh ] && bash scripts/run_h1_thought_gate_full_closure.sh
[ -f scripts/run_h2_query_budget_full_closure.sh ] && bash scripts/run_h2_query_budget_full_closure.sh
[ -f scripts/run_h3_model_router_full_closure.sh ] && bash scripts/run_h3_model_router_full_closure.sh
[ -f scripts/run_h4_compute_governor_full_closure.sh ] && bash scripts/run_h4_compute_governor_full_closure.sh

echo
echo "===== 6) MINIMAL PATCH: FIX H5 NameError (h2_runtime) ====="
F="scripts/bybit_ai_cost_log.py"
if [ -f "$F" ]; then
  cp "$F" "$F.bak_h5_nameerror_truth_round1_$(date +%s)"

  if grep -q 'h2_observed_last_call = h2_runtime.get("observed_last_call") or {}' "$F"; then
    if ! grep -qE '^[[:space:]]*h2_runtime[[:space:]]*=' "$F"; then
      HELPER=""
      PATHVAR=""

      if grep -q 'load_json(' "$F"; then
        HELPER="load_json"
      elif grep -q 'read_json(' "$F"; then
        HELPER="read_json"
      fi

      if grep -q 'QUERY_BUDGET_RUNTIME_PATH' "$F"; then
        PATHVAR="QUERY_BUDGET_RUNTIME_PATH"
      elif grep -q 'H2_RUNTIME_PATH' "$F"; then
        PATHVAR="H2_RUNTIME_PATH"
      fi

      if [ -n "$HELPER" ] && [ -n "$PATHVAR" ]; then
        awk \
          -v needle='h2_observed_last_call = h2_runtime.get("observed_last_call") or {}' \
          -v ins="    h2_runtime = ${HELPER}(${PATHVAR})" '
          index($0, needle) && !done { print ins; done=1 }
          { print }
        ' "$F" > "$F.tmp"
        mv "$F.tmp" "$F"
        echo "patched_h5_nameerror=True helper=$HELPER pathvar=$PATHVAR"
      else
        echo "WARNING: could_not_auto_patch_h5_nameerror helper=$HELPER pathvar=$PATHVAR"
      fi
    else
      echo "h5_nameerror_patch_not_needed=True"
    fi
  else
    echo "h5_nameerror_pattern_not_found=True"
  fi
fi

echo
echo "===== 7) PY_COMPILE H5 ====="
python3 -m py_compile scripts/bybit_ai_cost_log.py
python3 -m py_compile scripts/bybit_ai_governance_audit.py
python3 -m py_compile scripts/bybit_ai_cost_governance_final_audit.py

echo
echo "===== 8) RERUN H5 ====="
[ -f scripts/run_h5_ai_cost_governance_full_closure.sh ] && bash scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 9) FINAL TRUTH STATUS ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
import os
from pathlib import Path

lj = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/local_judgment")
tg = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(p):
    p = Path(p)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

pm = read(lj / "bybit_public_microstructure_latest.json")
h0 = read(lj / "bybit_local_judgment_final_audit_latest.json")
h1i = read(tg / "bybit_thought_gate_input_latest.json")
h1p = read(tg / "bybit_thought_gate_policy_latest.json")
h1req = read(tg / "bybit_ai_request_envelope_latest.json")
h5log = read(tg / "bybit_ai_cost_log_latest.json")
h5 = read(tg / "bybit_ai_cost_governance_final_audit_latest.json")

derived = pm.get("derived") or {}
cost_log = h5log.get("cost_log") or {}
perf = cost_log.get("performance_summary") or {}

print("===== PUBLIC_MICROSTRUCTURE =====")
print("ts_ms =", pm.get("ts_ms"))
print("report_ok =", pm.get("report_ok"))
print("microstructure_state =", pm.get("microstructure_state"))
print("recent_trade_count =", derived.get("recent_trade_count"))
print("last_trade_price =", derived.get("last_trade_price"))
print("last_trade_ts_ms =", derived.get("last_trade_ts_ms"))
print("warning_flags =", pm.get("warning_flags"))

print("")
print("===== H0 =====")
print("overall_ok =", h0.get("overall_ok"))
print("final_h0_state =", h0.get("final_h0_state"))
print("progression_ready =", h0.get("progression_ready"))

print("")
print("===== H1 =====")
print("input_state =", h1i.get("input_state"))
print("operator_flags =", h1i.get("operator_flags"))
print("policy_warning_flags =", h1p.get("warning_flags"))
print("request_warning_flags =", h1req.get("warning_flags"))

print("")
print("===== H5 =====")
print("overall_ok =", h5.get("overall_ok"))
print("audit_state =", h5.get("audit_state"))
print("final_state =", h5.get("final_state"))
print("within_timeout_hint =", perf.get("within_timeout_hint"))
print("warning_flags =", h5.get("warning_flags"))
PY

#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

LJ_BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment"
TG_BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) DISCOVER H0 / LOCAL-JUDGMENT RUN SCRIPTS ====="
find scripts -maxdepth 1 -type f \
  \( -name 'run_h0*' -o -name 'run_*local*judgment*full*closure*.sh' -o -name 'run_*local*judgment*.sh' \) \
  | sort || true

echo
echo "===== 1) TRY FULL H0 / LOCAL-JUDGMENT REFRESH ====="
set +e

FULL_SCRIPT="$(find scripts -maxdepth 1 -type f \
  \( -name 'run_h0*full*closure*.sh' -o -name 'run_*local*judgment*full*closure*.sh' \) \
  | sort | head -n 1)"

if [ -n "${FULL_SCRIPT:-}" ]; then
  echo "using_full_script=$FULL_SCRIPT"
  bash "$FULL_SCRIPT"
  RC=$?
  echo "full_refresh_rc=$RC"
else
  echo "no_full_closure_script_found -> fallback to emitter discovery"

  python3 - <<'PY'
import subprocess
from pathlib import Path

targets = [
    "bybit_public_microstructure_latest.json",
    "bybit_local_cost_model_latest.json",
    "bybit_local_market_friction_latest.json",
    "bybit_local_risk_envelope_latest.json",
    "bybit_local_trade_eligibility_latest.json",
    "bybit_local_trade_eligibility_handoff_latest.json",
    "bybit_local_judgment_final_audit_latest.json",
]

scripts_dir = Path("scripts")
chosen = []

for target in targets:
    hits = []
    for p in scripts_dir.glob("*.py"):
        name = p.name
        if any(x in name for x in [
            "contract_check", ".bak_", "repair_", "diag_", "debug_", "smoke", "test_"
        ]):
            continue
        try:
            txt = p.read_text(encoding="utf-8")
        except Exception:
            continue
        if target in txt:
            hits.append(p)
    if hits:
        chosen.append(hits[0])

seen = set()
ordered = []
for p in chosen:
    if str(p) not in seen:
        seen.add(str(p))
        ordered.append(p)

print("fallback_emitters =")
for p in ordered:
    print(str(p))

for p in ordered:
    print(f"\n===== RUN {p} =====")
    r = subprocess.run(["python3", str(p)], text=True)
    print(f"rc={r.returncode}")
PY
fi

set -e

echo
echo "===== 2) DIAG PUBLIC_MICROSTRUCTURE + H0 FINAL AUDIT ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

files = {
    "public_microstructure": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/bybit_public_microstructure_latest.json"),
    "local_judgment_final_audit": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/bybit_local_judgment_final_audit_latest.json"),
    "trade_eligibility": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment/bybit_local_trade_eligibility_latest.json"),
    "thought_gate_input": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json"),
}

def read(p):
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def scan_last_trade(obj, path="root", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            lk = k.lower()
            if any(n in lk for n in [
                "last_trade", "recent_trade", "trade_tape", "trades", "last_price"
            ]):
                out.append((p, v))
            scan_last_trade(v, p, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:5]):
            scan_last_trade(v, f"{path}[{i}]", out)
    return out

for name, path in files.items():
    print(f"\n--- {name} ---")
    obj = read(path)
    if obj is None:
        print("missing")
        continue

    if name == "public_microstructure":
        for key in [
            "ts_ms", "microstructure_state", "report_ok", "warning_flags",
            "recent_trade_count", "last_trade_price", "last_trade_ts_ms"
        ]:
            if key in obj:
                print(f"{key} = {obj.get(key)}")

    if name == "local_judgment_final_audit":
        print("overall_ok =", obj.get("overall_ok"))
        print("audit_state =", obj.get("audit_state"))
        print("audit_summary =", obj.get("audit_summary"))
        print("warning_flags =", obj.get("warning_flags"))

    if name == "thought_gate_input":
        print("input_state =", obj.get("input_state"))
        print("operator_flags =", obj.get("operator_flags"))
        market_context = obj.get("market_context") or {}
        print("market_context.last_trade_price =", market_context.get("last_trade_price"))
        print("market_context.last_trade_ts_ms =", market_context.get("last_trade_ts_ms"))
        print("freshness =", obj.get("freshness"))

    hits = scan_last_trade(obj)
    if not hits:
        print("no_trade_like_hits")
    else:
        print("trade_like_hits_preview =")
        for p, v in hits[:20]:
            sv = str(v)
            if len(sv) > 220:
                sv = sv[:220] + "..."
            print(f"{p} = {sv}")
PY

echo
echo "===== 3) REBUILD H1 -> H5 AFTER H0 REFRESH ====="
./scripts/run_h1_thought_gate_full_closure.sh
./scripts/run_h2_query_budget_full_closure.sh
./scripts/run_h3_model_router_full_closure.sh
./scripts/run_h4_compute_governor_full_closure.sh
./scripts/run_h5_ai_cost_governance_full_closure.sh

echo
echo "===== 4) FINAL STATUS ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

tg = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")
lj = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/local_judgment")

def read(p):
    p = Path(p)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

h0 = read(lj / "bybit_local_judgment_final_audit_latest.json")
h1i = read(tg / "bybit_thought_gate_input_latest.json")
h1p = read(tg / "bybit_thought_gate_policy_latest.json")
h1req = read(tg / "bybit_ai_request_envelope_latest.json")
h5 = read(tg / "bybit_ai_cost_governance_final_audit_latest.json")
h5log = read(tg / "bybit_ai_cost_log_latest.json")

cost_log = h5log.get("cost_log") or {}
perf = cost_log.get("performance_summary") or {}

print("H0 overall_ok =", h0.get("overall_ok"))
print("H0 audit_state =", h0.get("audit_state"))
print("H0 audit_summary =", h0.get("audit_summary"))
print("")
print("H1 input_state =", h1i.get("input_state"))
print("H1 operator_flags =", h1i.get("operator_flags"))
print("H1 policy_warning_flags =", h1p.get("warning_flags"))
print("H1 request_warning_flags =", h1req.get("warning_flags"))
print("")
print("H5 overall_ok =", h5.get("overall_ok"))
print("H5 audit_state =", h5.get("audit_state"))
print("H5 warning_flags =", h5.get("warning_flags"))
print("H5 within_timeout_hint =", perf.get("within_timeout_hint"))
PY

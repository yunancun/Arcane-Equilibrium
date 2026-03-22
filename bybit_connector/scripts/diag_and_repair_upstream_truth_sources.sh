#!/usr/bin/env bash
set -euo pipefail

cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector

CANON_EXEC="/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_private_execution_history_latest.json"
SNAP="/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json"
TG_BASE="/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate"

echo "===== 0) RUN execution_history DIRECTLY ====="
set +e
python3 scripts/bybit_private_execution_history_check.py
RC1=$?
python3 scripts/bybit_private_execution_history_check.py.orig
RC2=$?
set -e
echo "direct_rc = $RC1"
echo "orig_rc   = $RC2"

echo
echo "===== 1) FIND ALL execution_history CANDIDATE FILES ====="
python3 - <<'PY'
import json
from pathlib import Path

roots = [
    Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit"),
    Path("/home/ncyu/srv/log_files/connector_logs"),
    Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit"),
]

patterns = [
    "*execution*history*latest.json",
    "*execution*history*.json",
]

seen = set()
candidates = []

def extract_ts(obj):
    vals = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"time", "ts_ms", "payload_ts_ms"} and isinstance(v, int):
                vals.append(v)
            elif isinstance(v, dict):
                vals.extend(extract_ts(v))
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        vals.extend(extract_ts(x))
    return vals

for root in roots:
    if not root.exists():
        continue
    for pat in patterns:
        for p in root.rglob(pat):
            if p in seen or not p.is_file():
                continue
            seen.add(p)
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            ts_values = extract_ts(obj)
            best_ts = max(ts_values) if ts_values else None
            candidates.append((best_ts or -1, str(p)))

candidates.sort(reverse=True)

print("candidate_count =", len(candidates))
for ts, path in candidates[:25]:
    print(f"ts={ts} path={path}")
PY

echo
echo "===== 2) REPAIR CANONICAL execution_history LATEST IF A FRESHER CANDIDATE EXISTS ====="
python3 - <<'PY'
import json
import shutil
from pathlib import Path

canon = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_private_execution_history_latest.json")
roots = [
    Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit"),
    Path("/home/ncyu/srv/log_files/connector_logs"),
    Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit"),
]

patterns = [
    "*execution*history*latest.json",
    "*execution*history*.json",
]

def extract_ts(obj):
    vals = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {"time", "ts_ms", "payload_ts_ms"} and isinstance(v, int):
                vals.append(v)
            elif isinstance(v, dict):
                vals.extend(extract_ts(v))
            elif isinstance(v, list):
                for x in v:
                    if isinstance(x, dict):
                        vals.extend(extract_ts(x))
    return vals

def read_json(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None

canon_obj = read_json(canon) if canon.exists() else None
canon_ts = max(extract_ts(canon_obj)) if canon_obj else -1

best_path = None
best_ts = canon_ts

for root in roots:
    if not root.exists():
        continue
    for pat in patterns:
        for p in root.rglob(pat):
            if not p.is_file():
                continue
            obj = read_json(p)
            if obj is None:
                continue
            ts_values = extract_ts(obj)
            ts = max(ts_values) if ts_values else -1
            if ts > best_ts:
                best_ts = ts
                best_path = p

print("canon_before_ts =", canon_ts)
print("best_candidate_ts =", best_ts)
print("best_candidate_path =", str(best_path) if best_path else None)

if best_path and best_path != canon:
    canon.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(best_path, canon)
    print("repaired_canonical = True")
else:
    print("repaired_canonical = False")
PY

echo
echo "===== 3) REBUILD SNAPSHOT + H1 INPUT ONLY ====="
./scripts/run_with_trading_env.sh bash -lc '
cd /home/ncyu/srv/program_code/exchange_connectors/bybit_connector
python3 scripts/bybit_snapshot_to_postgres.py
python3 scripts/bybit_full_readonly_observer_cycle.py
python3 scripts/bybit_thought_gate_input_builder.py
python3 scripts/bybit_thought_gate_policy_builder.py
'

echo
echo "===== 4) SEARCH REAL LAST-TRADE FIELDS IN UPSTREAM JSON ====="
python3 - <<'PY'
import json
from pathlib import Path

files = [
    Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json"),
    Path("/home/ncyu/srv/docker_projects/trading_services/decision_packets/bybit/bybit_decision_packet_latest.json"),
    Path("/home/ncyu/srv/docker_projects/trading_services/verdicts/bybit/bybit_observer_verdict_latest.json"),
    Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate/bybit_thought_gate_input_latest.json"),
]

needles = [
    "last_trade_price",
    "last_trade_ts_ms",
    "recent_trade_last_price",
    "recent_trade_last_ts_ms",
    "trade_price",
    "trade_ts_ms",
    "last_price",
]

def scan(obj, path="root", out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}"
            for n in needles:
                if n in k:
                    out.append((p, v))
            scan(v, p, out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:10]):
            scan(v, f"{path}[{i}]", out)
    return out

for f in files:
    print(f"\n--- {f} ---")
    if not f.exists():
        print("missing")
        continue
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:
        print("json_error =", e)
        continue
    hits = scan(obj)
    if not hits:
        print("no_last_trade_like_fields_found")
    else:
        for p, v in hits[:40]:
            print(f"{p} = {v}")
PY

echo
echo "===== 5) FINAL DIAG ====="
./scripts/run_with_trading_env.sh python3 - <<'PY'
import json
from pathlib import Path

snap = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_system_snapshot_latest.json")
base = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/thought_gate")

def read(p):
    p = Path(p)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))

snapshot = read(snap)
h1 = read(base / "bybit_thought_gate_input_latest.json")
h1p = read(base / "bybit_thought_gate_policy_latest.json")

pts = snapshot.get("payload_time_summary") or {}
print("payload_time_summary =", pts)
print("execution_history_payload_ts_ms =", pts.get("execution_history_payload_ts_ms"))
print("")
print("input_state =", h1.get("input_state"))
print("operator_flags =", h1.get("operator_flags"))
print("policy_warning_flags =", h1p.get("warning_flags"))
PY

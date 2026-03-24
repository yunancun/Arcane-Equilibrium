#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

files = {
    "H1": "bybit_thought_gate_final_audit_latest.json",
    "H2": "bybit_query_budget_final_audit_latest.json",
    "H3": "bybit_model_router_final_audit_latest.json",
    "H4": "bybit_compute_governor_final_audit_latest.json",
    "H5": "bybit_ai_cost_governance_final_audit_latest.json",
}

def load(name: str):
    p = base / name
    if not p.exists():
        return None, {"missing": True, "path": str(p)}
    return p, json.loads(p.read_text(encoding="utf-8"))

loaded = {}
for stage, fname in files.items():
    loaded[stage] = load(fname)

def summary_of(obj):
    return obj.get("audit_summary") if isinstance(obj, dict) else {}

h1 = loaded["H1"][1]
h2 = loaded["H2"][1]
h3 = loaded["H3"][1]
h4 = loaded["H4"][1]
h5 = loaded["H5"][1]

h1s = summary_of(h1)
h2s = summary_of(h2)
h3s = summary_of(h3)
h4s = summary_of(h4)
h5s = summary_of(h5)

stage_ok = {
    "H1": h1.get("overall_ok") is True and h1s.get("h1_stage_closed") is True,
    "H2": h2.get("overall_ok") is True and h2s.get("h2_stage_closed") is True,
    "H3": h3.get("overall_ok") is True and h3s.get("h3_stage_closed") is True,
    "H4": h4.get("overall_ok") is True and h4s.get("h4_stage_closed") is True,
    "H5": h5.get("overall_ok") is True and h5s.get("h5_stage_closed") is True,
}

canonical_h_chain_ok = all(stage_ok.values())
runtime_still_protected = all([
    h1s.get("runtime_still_protected") is True,
    h2s.get("runtime_still_protected") is True,
    h3s.get("runtime_still_protected") is True,
    h4s.get("runtime_still_protected") is True,
    h5s.get("runtime_still_protected") is True,
])

no_call_path_accepted = all([
    h1s.get("no_call_terminal_accepted") is True,
    h2s.get("no_call_path_accepted") is True,
    h3s.get("no_call_path_accepted") is True,
    h4s.get("no_call_path_accepted") is True,
    h5s.get("no_call_path_accepted") is True,
])

ready_for_i1 = h5s.get("ready_for_i1") is True
h_chapter_closed = h5s.get("h_chapter_closed") is True

print("===== I10 CANONICAL H-CHAIN RECHECK =====")
print("")

for stage in ["H1", "H2", "H3", "H4", "H5"]:
    obj = loaded[stage][1]
    s = summary_of(obj)
    print(f"--- {stage} ---")
    print("overall_ok =", obj.get("overall_ok"))
    print("audit_state =", obj.get("audit_state"))
    print("audit_summary =", s)
    print("")

print("canonical_h_chain_ok =", canonical_h_chain_ok)
print("h_chapter_closed =", h_chapter_closed)
print("ready_for_i1 =", ready_for_i1)
print("runtime_still_protected =", runtime_still_protected)
print("no_call_path_accepted =", no_call_path_accepted)
print("")
print("stage_ok =", stage_ok)

sys.exit(0 if canonical_h_chain_ok else 1)
PY

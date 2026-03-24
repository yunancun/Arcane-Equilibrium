#!/usr/bin/env bash
set -euo pipefail

# Canonical I10 recheck / I10 规范总复查
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE="$ROOT/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 - "$BASE" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])

files = {
    "I1": "bybit_decision_lease_final_audit_latest.json",
    "I2": "bybit_decision_lease_shadow_audit_latest.json",
    "I3": "bybit_decision_lease_consume_final_audit_latest.json",
    "I4": "bybit_decision_lease_replay_final_audit_latest.json",
    "I5": "bybit_decision_lease_friction_final_audit_latest.json",
    "I6": "bybit_decision_lease_approval_bridge_final_audit_latest.json",
    "I7": "bybit_execution_authority_aggregator_final_audit_latest.json",
    "I8": "bybit_manual_approval_packet_final_audit_latest.json",
    "I9": "bybit_operator_ack_shadow_final_audit_latest.json",
    "I10_summary": "bybit_decision_lease_chapter_summary_latest.json",
    "I10_handoff": "bybit_decision_lease_chapter_handoff_latest.json",
    "I10_audit": "bybit_decision_lease_chapter_final_audit_latest.json",
}

loaded = {}
for k, v in files.items():
    p = base / v
    loaded[k] = json.loads(p.read_text(encoding="utf-8"))

stage_status = (loaded["I10_summary"].get("stage_status") or {})
chapter_summary = (loaded["I10_summary"].get("chapter_summary") or {})
audit_summary = (loaded["I10_audit"].get("audit_summary") or {})

print("===== I10 CANONICAL DECISION-LEASE RECHECK =====")
print("")
for stage in ["I1","I2","I3","I4","I5","I6","I7","I8","I9"]:
    obj = loaded[stage]
    print(f"--- {stage} ---")
    print("overall_ok =", obj.get("overall_ok"))
    print("audit_state =", obj.get("audit_state"))
    print("audit_summary =", obj.get("audit_summary"))
    print("")

print("--- I10 summary ---")
print("summary_ok =", loaded["I10_summary"].get("summary_ok"))
print("summary_state =", loaded["I10_summary"].get("summary_state"))
print("chapter_summary =", chapter_summary)
print("")

print("--- I10 handoff ---")
print("handoff_ok =", loaded["I10_handoff"].get("handoff_ok"))
print("handoff_state =", loaded["I10_handoff"].get("handoff_state"))
print("")

print("--- I10 final audit ---")
print("overall_ok =", loaded["I10_audit"].get("overall_ok"))
print("audit_state =", loaded["I10_audit"].get("audit_state"))
print("audit_summary =", audit_summary)
print("")

print("stage_status =", stage_status)
print("i_chapter_closed =", audit_summary.get("i_chapter_closed"))
print("shadow_control_plane_closed =", audit_summary.get("shadow_control_plane_closed"))
print("runtime_still_protected =", audit_summary.get("runtime_still_protected"))
print("ready_for_future_live_design =", audit_summary.get("ready_for_future_live_design"))
PY

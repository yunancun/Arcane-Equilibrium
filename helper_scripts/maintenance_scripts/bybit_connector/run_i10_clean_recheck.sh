#!/usr/bin/env bash
set -euo pipefail
# XP-1: portable path / 可移植路径
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)}"
export _SRV

echo "===== LEGACY I10 NOTICE ====="
echo "This runner is a legacy decision_lease-oriented observer."
echo "It is NOT the authoritative checker for the repaired canonical H1-H5 chain."
echo "For current canonical H-chain status, use:"
echo "  helper_scripts/maintenance_scripts/bybit_connector/run_i10_canonical_h_chain_recheck.sh"
echo ""

BASE="$_SRV/docker_projects/trading_services/runtime/bybit/thought_gate"

python3 - <<'PY'
import json
import os
from pathlib import Path

base = Path(os.environ.get("_SRV", ".") + "/docker_projects/trading_services/runtime/bybit/thought_gate")

summary = json.loads((base / "bybit_decision_lease_chapter_summary_latest.json").read_text(encoding="utf-8"))
handoff = json.loads((base / "bybit_decision_lease_chapter_handoff_latest.json").read_text(encoding="utf-8"))
audit = json.loads((base / "bybit_decision_lease_chapter_final_audit_latest.json").read_text(encoding="utf-8"))

source_integrity = summary.get("source_integrity") or {}
chapter_summary = summary.get("chapter_summary") or {}
audit_summary = audit.get("audit_summary") or {}

print("===== I10 CLEAN RECHECK =====")
print("summary_state =", summary.get("summary_state"))
print("handoff_state =", handoff.get("handoff_state"))
print("audit_state =", audit.get("audit_state"))
print("")

print("i_chapter_closed =", audit_summary.get("i_chapter_closed"))
print("shadow_control_plane_closed =", audit_summary.get("shadow_control_plane_closed"))
print("runtime_still_protected =", audit_summary.get("runtime_still_protected"))
print("ready_for_future_live_design =", audit_summary.get("ready_for_future_live_design"))
print("")

print("execution_authority =", chapter_summary.get("execution_authority"))
print("decision_lease_emitted =", chapter_summary.get("decision_lease_emitted"))
print("live_operator_ack_enabled =", chapter_summary.get("live_operator_ack_enabled"))
print("")

print("source_errors =", source_integrity.get("source_errors"))
print("discovered_latest_file_count =", source_integrity.get("discovered_latest_file_count"))
print("stage_sources =", source_integrity.get("stage_sources"))
print("stage_discovery_mode =", source_integrity.get("stage_discovery_mode"))
print("stage_status =", summary.get("stage_status"))
print("")

print("warning_flags =", audit.get("warning_flags"))
PY

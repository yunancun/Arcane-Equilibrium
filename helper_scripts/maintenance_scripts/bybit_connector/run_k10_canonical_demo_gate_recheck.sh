#!/usr/bin/env bash
set -euo pipefail

# Canonical K10 recheck / K10 规范总复查
# 中文：
# - 读取 K 章 demo_gate latest 产物
# - 汇总 contract / readiness / summary / handoff / final audit / chapter consistency
# - 明确 K 章闭环仅代表 design-only gate closed，不代表 paper/live execution 开放
#
# English:
# - Read latest K chapter demo_gate artifacts
# - Summarize contract / readiness / summary / handoff / final audit / chapter consistency
# - K closure here means design-only gate closed, not paper/live execution enabled

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE="$ROOT/docker_projects/trading_services/runtime/bybit/demo_gate"
RUNTIME="$ROOT/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"

python3 - "$BASE" "$RUNTIME" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])
runtime_path = Path(sys.argv[2])

files = {
    "contract": "bybit_demo_gate_contract_latest.json",
    "readiness": "bybit_demo_gate_readiness_latest.json",
    "adapter": "bybit_demo_paper_adapter_skeleton_latest.json",
    "lifecycle": "bybit_paper_order_lifecycle_skeleton_latest.json",
    "projection": "bybit_paper_position_balance_projection_skeleton_latest.json",
    "risk": "bybit_pretrade_risk_integration_skeleton_latest.json",
    "summary": "bybit_demo_gate_summary_latest.json",
    "handoff": "bybit_demo_gate_handoff_latest.json",
    "final_audit": "bybit_demo_gate_final_audit_latest.json",
    "chapter_consistency": "bybit_demo_gate_chapter_consistency_latest.json",
}

loaded = {}
missing = []
for key, name in files.items():
    path = base / name
    if not path.exists():
        missing.append(str(path))
    else:
        loaded[key] = json.loads(path.read_text(encoding="utf-8"))

if not runtime_path.exists():
    missing.append(str(runtime_path))
else:
    loaded["runtime"] = json.loads(runtime_path.read_text(encoding="utf-8"))

print("===== K10 CANONICAL DEMO-GATE RECHECK =====")
print("")
if missing:
    print("missing_required_files = True")
    for item in missing:
        print("missing:", item)
    raise SystemExit(1)

contract = loaded["contract"]
readiness = loaded["readiness"]
adapter = loaded["adapter"]
lifecycle = loaded["lifecycle"]
projection = loaded["projection"]
risk = loaded["risk"]
summary = loaded["summary"]
handoff = loaded["handoff"]
final_audit = loaded["final_audit"]
chapter_consistency = loaded["chapter_consistency"]
runtime = loaded["runtime"]

print("--- K core layers ---")
print("contract =", contract.get("gate_state"))
print("gate_open =", contract.get("gate_open"))
print("readiness_state =", readiness.get("readiness_state"))
print("adapter_state =", adapter.get("adapter_state"))
print("lifecycle_state =", lifecycle.get("lifecycle_state"))
print("projection_state =", projection.get("projection_state"))
print("risk_state =", risk.get("risk_state"))
print("")

print("--- K summary ---")
print("summary_ok =", summary.get("summary_ok"))
print("summary_state =", summary.get("summary_state"))
print("gate_can_open =", summary.get("gate_can_open"))
print("operator_can_enable =", summary.get("operator_can_enable"))
print("missing_prerequisite_count =", len(summary.get("missing_prerequisites") or []))
print("")

print("--- K handoff ---")
current_status = handoff.get("current_status") or {}
print("summary_ok =", current_status.get("summary_ok"))
print("gate_can_open =", current_status.get("gate_can_open"))
print("operator_can_enable =", current_status.get("operator_can_enable"))
print("readonly_lock_ok =", current_status.get("readonly_lock_ok"))
print("")

print("--- K final audit ---")
audit_summary = final_audit.get("audit_summary") or {}
print("overall_ok =", final_audit.get("overall_ok"))
print("design_layers_defined =", audit_summary.get("design_layers_defined"))
print("gate_still_closed =", audit_summary.get("gate_still_closed"))
print("operator_still_locked =", audit_summary.get("operator_still_locked"))
print("runtime_still_readonly =", audit_summary.get("runtime_still_readonly"))
print("execution_still_disabled =", audit_summary.get("execution_still_disabled"))
print("")

print("--- K chapter consistency ---")
chapter_summary = chapter_consistency.get("chapter_summary") or {}
print("overall_ok =", chapter_consistency.get("overall_ok"))
print("contract_defined_and_closed =", chapter_summary.get("contract_defined_and_closed"))
print("readiness_still_locked =", chapter_summary.get("readiness_still_locked"))
print("final_audit_ok =", chapter_summary.get("final_audit_ok"))
print("runtime_still_protected =", chapter_summary.get("runtime_still_protected"))
print("")

print("--- main runtime ---")
print("system_mode =", runtime.get("system_mode"))
print("execution_state =", runtime.get("execution_state"))
print("business_event_state =", runtime.get("business_event_state"))
print("")

print("design_only_gate_closed =", (
    contract.get("gate_state") == "closed_contract_defined"
    and contract.get("gate_open") is False
    and summary.get("summary_ok") is True
    and summary.get("summary_state") == "design_layers_defined_gate_closed"
    and final_audit.get("overall_ok") is True
    and chapter_consistency.get("overall_ok") is True
    and runtime.get("system_mode") == "read_only"
    and runtime.get("execution_state") == "disabled"
))
print("paper_execution_open =", summary.get("gate_can_open"))
print("live_execution_open =", False)
PY

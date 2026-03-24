#!/usr/bin/env bash
set -euo pipefail

# Canonical J10 recheck / J10 规范总复查
# 中文：
# - 读取 J 章 transition_engine latest 产物
# - 汇总 matrix / audit / rule / graph / summary / handoff / final audit / chapter consistency
# - 明确 J 章闭环仅代表 skeleton / shadow-only closed，不代表 demo/live execution 开放
#
# English:
# - Read latest J chapter transition_engine artifacts
# - Summarize matrix / audit / rule / graph / summary / handoff / final audit / chapter consistency
# - J closure here means skeleton / shadow-only closed, not demo/live execution enabled

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE="$ROOT/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine"
RUNTIME="$ROOT/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"

python3 - "$BASE" "$RUNTIME" <<'PY'
import json
import sys
from pathlib import Path

base = Path(sys.argv[1])
runtime_path = Path(sys.argv[2])

files = {
    "matrix": "bybit_transition_engine_replay_matrix_latest.json",
    "audit": "bybit_transition_engine_audit_trail_latest.json",
    "rule": "bybit_transition_rule_layer_latest.json",
    "graph": "bybit_transition_state_graph_latest.json",
    "graph_consistency": "bybit_transition_state_graph_consistency_latest.json",
    "summary": "bybit_transition_engine_summary_latest.json",
    "handoff": "bybit_transition_engine_handoff_latest.json",
    "final_audit": "bybit_transition_engine_final_audit_latest.json",
    "chapter_consistency": "bybit_transition_engine_chapter_consistency_latest.json",
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

print("===== J10 CANONICAL TRANSITION-ENGINE RECHECK =====")
print("")
if missing:
    print("missing_required_files = True")
    for item in missing:
        print("missing:", item)
    raise SystemExit(1)

matrix = loaded["matrix"]
audit = loaded["audit"]
rule = loaded["rule"]
graph = loaded["graph"]
graph_consistency = loaded["graph_consistency"]
summary = loaded["summary"]
handoff = loaded["handoff"]
final_audit = loaded["final_audit"]
chapter_consistency = loaded["chapter_consistency"]
runtime = loaded["runtime"]

summary_final = summary.get("final_status") or {}
handoff_current = handoff.get("current_status") or {}
matrix_verdict = matrix.get("matrix_verdict") or {}
trail_summary = audit.get("trail_summary") or {}
layer_summary = rule.get("layer_summary") or {}
graph_summary = graph.get("graph_summary") or {}
graph_consistency_summary = graph_consistency.get("consistency_summary") or {}
chapter_summary = chapter_consistency.get("chapter_summary") or {}

runtime_still_protected = (
    runtime.get("system_mode") == "read_only"
    and runtime.get("execution_state") == "disabled"
    and summary_final.get("execution_permitted") is False
    and summary_final.get("demo_gate_open") is False
    and summary_final.get("live_execution_open") is False
)

j_chapter_closed = all([
    matrix_verdict.get("matrix_ok") is True,
    trail_summary.get("trail_ok") is True,
    layer_summary.get("skeleton_rules_ready") is True,
    graph_summary.get("graph_ready") is True,
    graph_consistency.get("overall_ok") is True,
    summary_final.get("transition_engine_skeleton_ready") is True,
    handoff_current.get("transition_engine_skeleton_ready") is True,
    final_audit.get("overall_ok") is True,
    chapter_consistency.get("overall_ok") is True,
    runtime_still_protected,
])

print("--- J1 matrix ---")
print("matrix_ok =", matrix_verdict.get("matrix_ok"))
print("positive_path_open =", matrix_verdict.get("positive_path_open"))
print("negative_path_blocked =", matrix_verdict.get("negative_path_blocked"))
print("readonly_context_ok =", matrix_verdict.get("readonly_context_ok"))
print("")

print("--- J2 audit trail ---")
print("trail_ok =", trail_summary.get("trail_ok"))
print("positive_case_verdict =", trail_summary.get("positive_case_verdict"))
print("negative_case_verdict =", trail_summary.get("negative_case_verdict"))
print("execution_forbidden_confirmed =", trail_summary.get("execution_forbidden_confirmed"))
print("")

print("--- J3 rule layer ---")
print("rule_layer_state =", rule.get("rule_layer_state"))
print("candidate_transition_supported =", rule.get("candidate_transition_supported"))
print("negative_blocking_supported =", rule.get("negative_blocking_supported"))
print("execution_permitted =", rule.get("execution_permitted"))
print("demo_gate_open =", rule.get("demo_gate_open"))
print("live_execution_open =", rule.get("live_execution_open"))
print("")

print("--- J4 graph ---")
print("graph_status =", graph.get("graph_status"))
print("graph_ready =", graph_summary.get("graph_ready"))
print("positive_path_mapped =", graph_summary.get("positive_path_mapped"))
print("negative_path_mapped =", graph_summary.get("negative_path_mapped"))
print("execution_path_closed =", graph_summary.get("execution_path_closed"))
print("graph_consistency_ok =", graph_consistency.get("overall_ok"))
print("graph_consistency_summary =", graph_consistency_summary)
print("")

print("--- J5 summary ---")
print("transition_engine_skeleton_ready =", summary_final.get("transition_engine_skeleton_ready"))
print("candidate_transition_supported =", summary_final.get("candidate_transition_supported"))
print("negative_blocking_supported =", summary_final.get("negative_blocking_supported"))
print("execution_permitted =", summary_final.get("execution_permitted"))
print("demo_gate_open =", summary_final.get("demo_gate_open"))
print("live_execution_open =", summary_final.get("live_execution_open"))
print("")

print("--- J6 handoff ---")
print("transition_engine_skeleton_ready =", handoff_current.get("transition_engine_skeleton_ready"))
print("candidate_transition_supported =", handoff_current.get("candidate_transition_supported"))
print("negative_blocking_supported =", handoff_current.get("negative_blocking_supported"))
print("execution_permitted =", handoff_current.get("execution_permitted"))
print("")

print("--- J7 final audit ---")
print("overall_ok =", final_audit.get("overall_ok"))
print("failed_checks =", final_audit.get("failed_checks"))
print("")

print("--- J8 chapter consistency ---")
print("overall_ok =", chapter_consistency.get("overall_ok"))
print("chapter_summary =", chapter_summary)
print("failed_checks =", chapter_consistency.get("failed_checks"))
print("")

print("--- main runtime ---")
print("system_mode =", runtime.get("system_mode"))
print("execution_state =", runtime.get("execution_state"))
print("business_event_state =", runtime.get("business_event_state"))
print("")

print("j_chapter_closed =", j_chapter_closed)
print("runtime_still_protected =", runtime_still_protected)
print("execution_permitted =", summary_final.get("execution_permitted"))
print("demo_gate_open =", summary_final.get("demo_gate_open"))
print("live_execution_open =", summary_final.get("live_execution_open"))

if not j_chapter_closed:
    raise SystemExit(1)
PY

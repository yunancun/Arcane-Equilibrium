#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_transition_engine_chapter_consistency_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / chapter consistency
- 这一层的白话解释:
  对 J 章现有 skeleton 产物做章节级一致性检查，
  确认 matrix / audit / rule / graph / summary / handoff / final audit / checkpoint 语义一致，
  且主系统仍未被污染。

Role:
- 汇总 J 章所有关键 latest 文件
- 做章节级 consistency check
- 输出 J 章 chapter consistency latest

Purpose in system:
- 给 J 章补齐章节级测试/审计层
- 为后续全量回归测试提供更稳定的统一检查点

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前仍只是 J skeleton consistency check
'''
"""

import json
import time
from pathlib import Path

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")

PATHS = {
    "matrix": BASE / "bybit_transition_engine_replay_matrix_latest.json",
    "matrix_contract": BASE / "bybit_transition_engine_replay_matrix_contract_latest.json",
    "audit": BASE / "bybit_transition_engine_audit_trail_latest.json",
    "audit_contract": BASE / "bybit_transition_engine_audit_trail_contract_latest.json",
    "rule_layer": BASE / "bybit_transition_rule_layer_latest.json",
    "rule_contract": BASE / "bybit_transition_rule_layer_contract_latest.json",
    "graph": BASE / "bybit_transition_state_graph_latest.json",
    "graph_contract": BASE / "bybit_transition_state_graph_contract_latest.json",
    "graph_consistency": BASE / "bybit_transition_state_graph_consistency_latest.json",
    "graph_consistency_contract": BASE / "bybit_transition_state_graph_consistency_contract_latest.json",
    "summary": BASE / "bybit_transition_engine_summary_latest.json",
    "summary_contract": BASE / "bybit_transition_engine_summary_contract_latest.json",
    "handoff": BASE / "bybit_transition_engine_handoff_latest.json",
    "handoff_contract": BASE / "bybit_transition_engine_handoff_contract_latest.json",
    "final_audit": BASE / "bybit_transition_engine_final_audit_latest.json",
    "final_audit_contract": BASE / "bybit_transition_engine_final_audit_contract_latest.json",
    "checkpoint": BASE / "bybit_transition_engine_checkpoint_latest.json",
    "checkpoint_contract": BASE / "bybit_transition_engine_checkpoint_contract_latest.json",
    "runtime": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"),
}

OUT_LATEST = BASE / "bybit_transition_engine_chapter_consistency_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def save(report):
    ts_ms = report["ts_ms"]
    dated = BASE / f"bybit_transition_engine_chapter_consistency_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    missing = []
    for key, path in PATHS.items():
        exists = path.exists()
        add_check(checks, f"{key}_exists", exists, str(path))
        if not exists:
            missing.append(key)

    if missing:
        report = {
            "report_type": "bybit_transition_engine_chapter_consistency_check",
            "report_version": "v1",
            "ts_ms": ts_ms,
            "overall_ok": False,
            "failed_count": sum(1 for x in checks if not x["ok"]),
            "checks": checks,
            "failed_checks": [x for x in checks if not x["ok"]],
            "reason": "required files missing",
            "missing_keys": missing,
        }
        dated = save(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"saved_latest={OUT_LATEST}")
        print(f"saved_dated={dated}")
        return

    matrix = load_json(PATHS["matrix"])
    matrix_contract = load_json(PATHS["matrix_contract"])
    audit = load_json(PATHS["audit"])
    audit_contract = load_json(PATHS["audit_contract"])
    rule = load_json(PATHS["rule_layer"])
    rule_contract = load_json(PATHS["rule_contract"])
    graph = load_json(PATHS["graph"])
    graph_contract = load_json(PATHS["graph_contract"])
    graph_consistency = load_json(PATHS["graph_consistency"])
    graph_consistency_contract = load_json(PATHS["graph_consistency_contract"])
    summary = load_json(PATHS["summary"])
    summary_contract = load_json(PATHS["summary_contract"])
    handoff = load_json(PATHS["handoff"])
    handoff_contract = load_json(PATHS["handoff_contract"])
    final_audit = load_json(PATHS["final_audit"])
    final_audit_contract = load_json(PATHS["final_audit_contract"])
    checkpoint = load_json(PATHS["checkpoint"])
    checkpoint_contract = load_json(PATHS["checkpoint_contract"])
    runtime = load_json(PATHS["runtime"])

    add_check(checks, "matrix_contract_ok", matrix_contract.get("overall_ok") is True, matrix_contract.get("failed_count"))
    add_check(checks, "audit_contract_ok", audit_contract.get("overall_ok") is True, audit_contract.get("failed_count"))
    add_check(checks, "rule_contract_ok", rule_contract.get("overall_ok") is True, rule_contract.get("failed_count"))
    add_check(checks, "graph_contract_ok", graph_contract.get("overall_ok") is True, graph_contract.get("failed_count"))
    add_check(checks, "graph_consistency_contract_ok", graph_consistency_contract.get("overall_ok") is True, graph_consistency_contract.get("failed_count"))
    add_check(checks, "summary_contract_ok", summary_contract.get("overall_ok") is True, summary_contract.get("failed_count"))
    add_check(checks, "handoff_contract_ok", handoff_contract.get("overall_ok") is True, handoff_contract.get("failed_count"))
    add_check(checks, "final_audit_contract_ok", final_audit_contract.get("overall_ok") is True, final_audit_contract.get("failed_count"))
    add_check(checks, "checkpoint_contract_ok", checkpoint_contract.get("overall_ok") is True, checkpoint_contract.get("failed_count"))

    add_check(checks, "matrix_ok", matrix.get("matrix_verdict", {}).get("matrix_ok") is True, matrix.get("matrix_verdict", {}))
    add_check(checks, "matrix_positive_path_open", matrix.get("matrix_verdict", {}).get("positive_path_open") is True, matrix.get("matrix_verdict", {}))
    add_check(checks, "matrix_negative_path_blocked", matrix.get("matrix_verdict", {}).get("negative_path_blocked") is True, matrix.get("matrix_verdict", {}))
    add_check(checks, "matrix_readonly_context_ok", matrix.get("matrix_verdict", {}).get("readonly_context_ok") is True, matrix.get("matrix_verdict", {}))

    add_check(checks, "audit_trail_ok", audit.get("trail_summary", {}).get("trail_ok") is True, audit.get("trail_summary", {}))
    add_check(checks, "audit_positive_case_open", audit.get("trail_summary", {}).get("positive_case_open") is True, audit.get("trail_summary", {}))
    add_check(checks, "audit_negative_case_blocked", audit.get("trail_summary", {}).get("negative_case_blocked") is True, audit.get("trail_summary", {}))
    add_check(checks, "audit_execution_forbidden_confirmed", audit.get("trail_summary", {}).get("execution_forbidden_confirmed") is True, audit.get("trail_summary", {}))

    add_check(checks, "rule_skeleton_ready", rule.get("rule_layer_state") == "skeleton_rules_ready", rule.get("rule_layer_state"))
    add_check(checks, "rule_positive_supported", rule.get("candidate_transition_supported") is True, rule.get("candidate_transition_supported"))
    add_check(checks, "rule_negative_supported", rule.get("negative_blocking_supported") is True, rule.get("negative_blocking_supported"))
    add_check(checks, "rule_execution_forbidden", rule.get("execution_permitted") is False, rule.get("execution_permitted"))

    add_check(checks, "graph_ready", graph.get("graph_summary", {}).get("graph_ready") is True, graph.get("graph_summary", {}))
    add_check(checks, "graph_positive_mapped", graph.get("graph_summary", {}).get("positive_path_mapped") is True, graph.get("graph_summary", {}))
    add_check(checks, "graph_negative_mapped", graph.get("graph_summary", {}).get("negative_path_mapped") is True, graph.get("graph_summary", {}))
    add_check(checks, "graph_execution_closed", graph.get("graph_summary", {}).get("execution_path_closed") is True, graph.get("graph_summary", {}))
    add_check(checks, "graph_consistency_ok", graph_consistency.get("overall_ok") is True, graph_consistency.get("failed_count"))

    add_check(checks, "summary_transition_engine_ready", summary.get("final_status", {}).get("transition_engine_skeleton_ready") is True, summary.get("final_status", {}))
    add_check(checks, "summary_candidate_supported", summary.get("final_status", {}).get("candidate_transition_supported") is True, summary.get("final_status", {}))
    add_check(checks, "summary_negative_supported", summary.get("final_status", {}).get("negative_blocking_supported") is True, summary.get("final_status", {}))
    add_check(checks, "summary_execution_forbidden", summary.get("final_status", {}).get("execution_permitted") is False, summary.get("final_status", {}))

    add_check(checks, "handoff_transition_engine_ready", handoff.get("current_status", {}).get("transition_engine_skeleton_ready") is True, handoff.get("current_status", {}))
    add_check(checks, "handoff_candidate_supported", handoff.get("current_status", {}).get("candidate_transition_supported") is True, handoff.get("current_status", {}))
    add_check(checks, "handoff_negative_supported", handoff.get("current_status", {}).get("negative_blocking_supported") is True, handoff.get("current_status", {}))
    add_check(checks, "handoff_execution_forbidden", handoff.get("current_status", {}).get("execution_permitted") is False, handoff.get("current_status", {}))

    add_check(checks, "checkpoint_ready", checkpoint.get("checkpoint_conclusion", {}).get("checkpoint_ready") is True, checkpoint.get("checkpoint_conclusion", {}))
    add_check(checks, "checkpoint_execution_forbidden", checkpoint.get("checkpoint_conclusion", {}).get("execution_still_forbidden") is True, checkpoint.get("checkpoint_conclusion", {}))
    add_check(checks, "checkpoint_demo_gate_closed", checkpoint.get("checkpoint_conclusion", {}).get("demo_gate_still_closed") is True, checkpoint.get("checkpoint_conclusion", {}))
    add_check(checks, "checkpoint_live_gate_closed", checkpoint.get("checkpoint_conclusion", {}).get("live_execution_still_closed") is True, checkpoint.get("checkpoint_conclusion", {}))

    add_check(checks, "final_audit_ok", final_audit.get("overall_ok") is True, final_audit.get("failed_count"))

    add_check(checks, "runtime_still_read_only", runtime.get("system_mode") == "read_only", runtime.get("system_mode"))
    add_check(checks, "runtime_execution_disabled", runtime.get("execution_state") == "disabled", runtime.get("execution_state"))
    add_check(checks, "runtime_business_event_unchanged",
              runtime.get("business_event_state") == "healthy_no_business_events_yet" and runtime.get("business_event_healthy") is True,
              {"business_event_state": runtime.get("business_event_state"), "business_event_healthy": runtime.get("business_event_healthy")})

    overall_ok = all(x["ok"] for x in checks)

    report = {
        "report_type": "bybit_transition_engine_chapter_consistency_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "J.chapter",
        "overall_ok": overall_ok,
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
        "chapter_summary": {
            "matrix_ok": matrix.get("matrix_verdict", {}).get("matrix_ok"),
            "audit_trail_ok": audit.get("trail_summary", {}).get("trail_ok"),
            "rule_layer_ready": rule.get("rule_layer_state") == "skeleton_rules_ready",
            "graph_ready": graph.get("graph_summary", {}).get("graph_ready"),
            "summary_ready": summary.get("final_status", {}).get("transition_engine_skeleton_ready"),
            "handoff_ready": handoff.get("current_status", {}).get("transition_engine_skeleton_ready"),
            "checkpoint_ready": checkpoint.get("checkpoint_conclusion", {}).get("checkpoint_ready"),
            "final_audit_ok": final_audit.get("overall_ok"),
            "runtime_still_protected": runtime.get("system_mode") == "read_only" and runtime.get("execution_state") == "disabled",
        },
    }

    dated = save(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

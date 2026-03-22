#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_final_audit.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / final audit
- 这一层的白话解释:
  对 J 章 skeleton 做总审计，确认语义一致且主系统未被污染。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 final audit 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.6
- 该临时编号现已废弃
- 后续以 Revision 2 正式章节树为准

Maintenance notes:
- 本批修正只改头部注释归位，不改文件名、latest 路径、JSON stage 字段
- 如后续要改 stage / 输出字段，必须单独做兼容性修订
\'\'\'
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
    "rule_layer_contract": BASE / "bybit_transition_rule_layer_contract_latest.json",
    "summary": BASE / "bybit_transition_engine_summary_latest.json",
    "summary_contract": BASE / "bybit_transition_engine_summary_contract_latest.json",
    "handoff": BASE / "bybit_transition_engine_handoff_latest.json",
    "handoff_contract": BASE / "bybit_transition_engine_handoff_contract_latest.json",
    "main_runtime": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"),
}

OUT_LATEST = BASE / "bybit_transition_engine_final_audit_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_transition_engine_final_audit_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    missing = [k for k, p in PATHS.items() if not p.exists()]
    add("all_required_files_exist", len(missing) == 0, missing)

    if not missing:
        objs = {k: load_json(v) for k, v in PATHS.items()}

        matrix = objs["matrix"]
        audit = objs["audit"]
        rule_layer = objs["rule_layer"]
        summary = objs["summary"]
        handoff = objs["handoff"]
        runtime = objs["main_runtime"]

        add("matrix_contract_ok", objs["matrix_contract"].get("overall_ok") is True, objs["matrix_contract"].get("overall_ok"))
        add("audit_contract_ok", objs["audit_contract"].get("overall_ok") is True, objs["audit_contract"].get("overall_ok"))
        add("rule_layer_contract_ok", objs["rule_layer_contract"].get("overall_ok") is True, objs["rule_layer_contract"].get("overall_ok"))
        add("summary_contract_ok", objs["summary_contract"].get("overall_ok") is True, objs["summary_contract"].get("overall_ok"))
        add("handoff_contract_ok", objs["handoff_contract"].get("overall_ok") is True, objs["handoff_contract"].get("overall_ok"))

        add("matrix_ok_true", matrix.get("matrix_verdict", {}).get("matrix_ok") is True, matrix.get("matrix_verdict", {}))
        add("audit_trail_ok_true", audit.get("trail_summary", {}).get("trail_ok") is True, audit.get("trail_summary", {}))
        add("rule_layer_ready_true", rule_layer.get("rule_layer_state") == "skeleton_rules_ready", rule_layer.get("rule_layer_state"))
        add("summary_ready_true", summary.get("final_status", {}).get("transition_engine_skeleton_ready") is True, summary.get("final_status", {}))
        add("handoff_ready_true", handoff.get("current_status", {}).get("transition_engine_skeleton_ready") is True, handoff.get("current_status", {}))

        add(
            "summary_matches_rule_layer_candidate",
            summary.get("final_status", {}).get("candidate_transition_supported") == rule_layer.get("candidate_transition_supported"),
            {
                "summary": summary.get("final_status", {}).get("candidate_transition_supported"),
                "rule_layer": rule_layer.get("candidate_transition_supported"),
            }
        )

        add(
            "handoff_matches_summary_execution_flag",
            handoff.get("current_status", {}).get("execution_permitted") == summary.get("final_status", {}).get("execution_permitted"),
            {
                "handoff": handoff.get("current_status", {}).get("execution_permitted"),
                "summary": summary.get("final_status", {}).get("execution_permitted"),
            }
        )

        add("main_runtime_readonly", runtime.get("system_mode") == "read_only", runtime.get("system_mode"))
        add("main_runtime_execution_disabled", runtime.get("execution_state") == "disabled", runtime.get("execution_state"))
        add("main_runtime_still_unpolluted", runtime.get("business_event_state") == "healthy_no_business_events_yet", runtime.get("business_event_state"))

    failed = [x for x in checks if not x["ok"]]
    report = {
        "audit_type": "bybit_transition_engine_final_audit",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

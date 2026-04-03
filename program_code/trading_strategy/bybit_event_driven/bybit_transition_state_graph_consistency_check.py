#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_state_graph_consistency_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章一致性层 / graph consistency
- 这一层的白话解释:
  检查 transition state graph 与 summary / handoff / final audit 之间的语义是否一致。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 state graph 骨架
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.7 / G4.8
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
import os

GRAPH_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_state_graph_latest.json")
SUMMARY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_summary_latest.json")
HANDOFF_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_handoff_latest.json")
FINAL_AUDIT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_final_audit_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_transition_state_graph_consistency_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_transition_state_graph_consistency_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    graph = load_json(GRAPH_PATH)
    summary = load_json(SUMMARY_PATH)
    handoff = load_json(HANDOFF_PATH)
    final_audit = load_json(FINAL_AUDIT_PATH)
    runtime = load_json(RUNTIME_PATH)

    graph_summary = graph.get("graph_summary", {})
    summary_status = summary.get("final_status", {})
    handoff_status = handoff.get("current_status", {})

    checks = []

    checks.append(check("graph_exists", GRAPH_PATH.exists(), str(GRAPH_PATH)))
    checks.append(check("summary_exists", SUMMARY_PATH.exists(), str(SUMMARY_PATH)))
    checks.append(check("handoff_exists", HANDOFF_PATH.exists(), str(HANDOFF_PATH)))
    checks.append(check("final_audit_exists", FINAL_AUDIT_PATH.exists(), str(FINAL_AUDIT_PATH)))
    checks.append(check("runtime_exists", RUNTIME_PATH.exists(), str(RUNTIME_PATH)))

    checks.append(check(
        "graph_positive_matches_summary_candidate",
        graph_summary.get("positive_path_mapped") == summary_status.get("candidate_transition_supported"),
        {
            "graph": graph_summary.get("positive_path_mapped"),
            "summary": summary_status.get("candidate_transition_supported"),
        }
    ))

    checks.append(check(
        "graph_negative_matches_summary_blocking",
        graph_summary.get("negative_path_mapped") == summary_status.get("negative_blocking_supported"),
        {
            "graph": graph_summary.get("negative_path_mapped"),
            "summary": summary_status.get("negative_blocking_supported"),
        }
    ))

    checks.append(check(
        "summary_matches_handoff_candidate",
        summary_status.get("candidate_transition_supported") == handoff_status.get("candidate_transition_supported"),
        {
            "summary": summary_status.get("candidate_transition_supported"),
            "handoff": handoff_status.get("candidate_transition_supported"),
        }
    ))

    checks.append(check(
        "summary_matches_handoff_negative_blocking",
        summary_status.get("negative_blocking_supported") == handoff_status.get("negative_blocking_supported"),
        {
            "summary": summary_status.get("negative_blocking_supported"),
            "handoff": handoff_status.get("negative_blocking_supported"),
        }
    ))

    checks.append(check(
        "graph_execution_closed_matches_runtime",
        graph_summary.get("execution_path_closed") == (
            runtime.get("system_mode") == "read_only" and runtime.get("execution_state") == "disabled"
        ),
        {
            "graph_execution_path_closed": graph_summary.get("execution_path_closed"),
            "runtime_system_mode": runtime.get("system_mode"),
            "runtime_execution_state": runtime.get("execution_state"),
        }
    ))

    checks.append(check(
        "summary_execution_permitted_false",
        summary_status.get("execution_permitted") is False,
        summary_status.get("execution_permitted"),
    ))

    checks.append(check(
        "handoff_execution_permitted_false",
        handoff_status.get("execution_permitted") is False,
        handoff_status.get("execution_permitted"),
    ))

    checks.append(check(
        "graph_demo_gate_closed_matches_summary",
        graph_summary.get("demo_gate_open") == summary_status.get("demo_gate_open"),
        {
            "graph": graph_summary.get("demo_gate_open"),
            "summary": summary_status.get("demo_gate_open"),
        }
    ))

    checks.append(check(
        "graph_live_gate_closed_matches_summary",
        graph_summary.get("live_execution_open") == summary_status.get("live_execution_open"),
        {
            "graph": graph_summary.get("live_execution_open"),
            "summary": summary_status.get("live_execution_open"),
        }
    ))

    checks.append(check(
        "final_audit_overall_ok_true",
        final_audit.get("overall_ok") is True,
        final_audit.get("overall_ok"),
    ))

    checks.append(check(
        "runtime_still_read_only",
        runtime.get("system_mode") == "read_only",
        runtime.get("system_mode"),
    ))

    checks.append(check(
        "runtime_execution_disabled",
        runtime.get("execution_state") == "disabled",
        runtime.get("execution_state"),
    ))

    checks.append(check(
        "runtime_business_event_state_unchanged",
        runtime.get("business_event_state") == "healthy_no_business_events_yet",
        runtime.get("business_event_state"),
    ))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_transition_state_graph_consistency_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

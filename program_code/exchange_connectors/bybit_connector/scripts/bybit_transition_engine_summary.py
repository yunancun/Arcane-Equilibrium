#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_summary.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / summary
- 这一层的白话解释:
  把 J 章各层统一汇总成人工可读总状态。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 summary 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.4
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

MATRIX_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_replay_matrix_latest.json")
AUDIT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_audit_trail_latest.json")
RULE_LAYER_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_rule_layer_latest.json")
RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = MATRIX_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_transition_engine_summary_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_summary_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    matrix = load_json(MATRIX_PATH)
    audit = load_json(AUDIT_PATH)
    rule_layer = load_json(RULE_LAYER_PATH)
    runtime = load_json(RUNTIME_PATH)

    matrix_verdict = matrix.get("matrix_verdict", {})
    trail_summary = audit.get("trail_summary", {})
    layer_summary = rule_layer.get("layer_summary", {})

    skeleton_ready = (
        matrix_verdict.get("matrix_ok") is True
        and trail_summary.get("trail_ok") is True
        and layer_summary.get("skeleton_rules_ready") is True
    )

    report = {
        "summary_type": "bybit_transition_engine_summary",
        "summary_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G4.4",
        "revision_tree_context": {
            "section": "G",
            "subsection": "G4.4",
            "section_meaning": "隔离 replay / transition engine skeleton 验证层",
            "current_focus": "transition engine skeleton summary"
        },
        "system_context": {
            "system_mode": runtime.get("system_mode"),
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy")
        },
        "final_status": {
            "transition_engine_skeleton_ready": skeleton_ready,
            "candidate_transition_supported": rule_layer.get("candidate_transition_supported") is True,
            "negative_blocking_supported": rule_layer.get("negative_blocking_supported") is True,
            "execution_permitted": False,
            "demo_gate_open": False,
            "live_execution_open": False
        },
        "matrix_layer": {
            "report_version": matrix.get("report_version"),
            "matrix_ok": matrix_verdict.get("matrix_ok"),
            "positive_path_open": matrix_verdict.get("positive_path_open"),
            "negative_path_blocked": matrix_verdict.get("negative_path_blocked"),
            "readonly_context_ok": matrix_verdict.get("readonly_context_ok")
        },
        "audit_layer": {
            "audit_version": audit.get("audit_version"),
            "trail_ok": trail_summary.get("trail_ok"),
            "positive_case_verdict": trail_summary.get("positive_case_verdict"),
            "negative_case_verdict": trail_summary.get("negative_case_verdict"),
            "execution_forbidden_confirmed": trail_summary.get("execution_forbidden_confirmed")
        },
        "rule_layer": {
            "layer_version": rule_layer.get("layer_version"),
            "rule_layer_state": rule_layer.get("rule_layer_state"),
            "candidate_transition_supported": rule_layer.get("candidate_transition_supported"),
            "negative_blocking_supported": rule_layer.get("negative_blocking_supported"),
            "failed_rule_count": layer_summary.get("failed_rule_count")
        },
        "summary_explainer": {
            "transition_engine_skeleton_ready": "说明 G4.1/G4.2/G4.3 已组成可维护的 skeleton 闭环",
            "candidate_transition_supported": "说明正向 replay 已被识别为 candidate open，但仍只是隔离验证语义",
            "negative_blocking_supported": "说明负向 replay 仍会被正确阻断",
            "execution_permitted": "这里必须保持 false；当前阶段仍不是 demo/live execution"
        }
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

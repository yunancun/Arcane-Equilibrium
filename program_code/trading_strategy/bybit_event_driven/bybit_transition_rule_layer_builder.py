#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_rule_layer_builder.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J1. transition rules
- 这一层的白话解释:
  定义 transition rule layer 骨架，用来统一表达哪些 candidate path 在隔离验证里可开、哪些必须阻断。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 transition rules 骨架
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.3
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

AUDIT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_audit_trail_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_transition_rule_layer_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_rule_layer_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)

    audit = load_json(AUDIT_PATH)
    runtime = load_json(RUNTIME_PATH)

    entries = audit.get("audit_entries", [])
    positive = next((x for x in entries if x.get("case_name") == "positive_replay_path"), {})
    negative = next((x for x in entries if x.get("case_name") == "negative_replay_path"), {})

    readonly_lock_active = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    positive_candidate_recognized = (
        positive.get("audit_verdict") == "candidate_open_but_execution_forbidden"
        and positive.get("candidate_available") is True
    )

    negative_candidate_blocked = (
        negative.get("audit_verdict") == "candidate_blocked"
        and negative.get("candidate_available") is False
    )

    execution_still_forbidden = (
        positive.get("execution_still_forbidden") is True
        and negative.get("execution_still_forbidden") is True
        and runtime.get("execution_state") == "disabled"
    )

    audit_trail_ok = audit.get("trail_summary", {}).get("trail_ok") is True

    demo_gate_open = False
    live_execution_open = False

    rule_results = [
        {
            "rule_name": "readonly_lock_must_remain_active",
            "passed": readonly_lock_active,
            "detail": {
                "system_mode": runtime.get("system_mode"),
                "execution_state": runtime.get("execution_state"),
            },
        },
        {
            "rule_name": "positive_replay_candidate_must_be_recognized",
            "passed": positive_candidate_recognized,
            "detail": positive,
        },
        {
            "rule_name": "negative_replay_candidate_must_remain_blocked",
            "passed": negative_candidate_blocked,
            "detail": negative,
        },
        {
            "rule_name": "execution_must_remain_forbidden",
            "passed": execution_still_forbidden,
            "detail": {
                "positive_execution_still_forbidden": positive.get("execution_still_forbidden"),
                "negative_execution_still_forbidden": negative.get("execution_still_forbidden"),
                "runtime_execution_state": runtime.get("execution_state"),
            },
        },
        {
            "rule_name": "audit_trail_must_be_ok",
            "passed": audit_trail_ok,
            "detail": audit.get("trail_summary", {}),
        },
        {
            "rule_name": "demo_gate_must_remain_closed",
            "passed": demo_gate_open is False,
            "detail": {"demo_gate_open": demo_gate_open},
        },
        {
            "rule_name": "live_execution_must_remain_closed",
            "passed": live_execution_open is False,
            "detail": {"live_execution_open": live_execution_open},
        },
    ]

    failed_rules = [x for x in rule_results if not x["passed"]]

    skeleton_rules_ready = (
        len(failed_rules) == 0
        and positive_candidate_recognized
        and negative_candidate_blocked
        and execution_still_forbidden
    )

    report = {
        "layer_type": "bybit_transition_rule_layer",
        "layer_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G4.3",
        "revision_tree_context": {
            "section": "G",
            "subsection": "G4.3",
            "section_meaning": "隔离 replay / transition engine skeleton 验证层",
            "current_focus": "transition rule layer skeleton",
        },
        "source_refs": {
            "audit_ts_ms": audit.get("ts_ms"),
            "runtime_ts_ms": runtime.get("ts_ms"),
            "audit_version": audit.get("audit_version"),
            "runtime_version": runtime.get("state_version"),
        },
        "runtime_safety_context": {
            "system_mode": runtime.get("system_mode"),
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
        },
        "rule_layer_state": "skeleton_rules_ready" if skeleton_rules_ready else "skeleton_rules_not_ready",
        "candidate_transition_supported": positive_candidate_recognized,
        "negative_blocking_supported": negative_candidate_blocked,
        "execution_permitted": False,
        "demo_gate_open": demo_gate_open,
        "live_execution_open": live_execution_open,
        "rule_results": rule_results,
        "failed_rules": failed_rules,
        "layer_summary": {
            "rule_count": len(rule_results),
            "failed_rule_count": len(failed_rules),
            "skeleton_rules_ready": skeleton_rules_ready,
            "positive_candidate_recognized": positive_candidate_recognized,
            "negative_candidate_blocked": negative_candidate_blocked,
            "execution_still_forbidden": execution_still_forbidden,
        },
        "rule_layer_explainer": {
            "skeleton_rules_ready": "说明 replay-based transition skeleton 已具备规则层表达能力，但 execution 仍严格禁止",
            "candidate_transition_supported": "说明正向 replay 已可被规则层识别为 candidate open",
            "negative_blocking_supported": "说明负向 replay 仍会被规则层正确阻断",
            "execution_permitted": "当前必须始终为 false；这里不是 execution gate"
        }
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

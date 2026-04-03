#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_handoff_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / handoff
- 这一层的白话解释:
  把 K 章当前状态、限制、下一步施工顺序整理成交接文件。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 handoff 层

Historical note:
- 开发过程中曾临时标为 G5.8
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

SUMMARY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_summary_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_handoff_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_handoff_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    summary = load_json(SUMMARY_PATH)
    runtime = load_json(RUNTIME_PATH)

    missing_prereqs = summary.get("missing_prerequisites", [])
    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    obj = {
        "handoff_type": "bybit_demo_gate_handoff",
        "handoff_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.8",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.8",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "demo gate handoff / 交接层",
        },
        "current_status": {
            "summary_state": summary.get("summary_state"),
            "summary_ok": summary.get("summary_ok"),
            "gate_can_open": summary.get("gate_can_open"),
            "operator_can_enable": summary.get("operator_can_enable"),
            "missing_prerequisite_count": len(missing_prereqs),
            "readonly_lock_ok": readonly_lock_ok,
        },
        "runtime_safety_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "system_mode": runtime.get("system_mode"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
        },
        "layer_status": summary.get("layer_status", {}),
        "missing_prerequisites": missing_prereqs,
        "hard_safety_boundaries": [
            "主系统当前必须继续保持 read_only",
            "execution_state 必须继续保持 disabled",
            "demo gate 即使后续逐步完善，也不等于 live execution gate 开启",
            "在 simulator / lifecycle / projection / risk / audit / operator enable 补齐前，不能放行任何 paper order",
        ],
        "recommended_next_build_order": [
            "1. simulator adapter implementation",
            "2. paper order lifecycle detail expansion",
            "3. paper position / balance projection detail expansion",
            "4. pretrade risk integration implementation",
            "5. paper audit trail skeleton",
            "6. explicit operator enable switch skeleton",
            "7. demo gate acceptance layer",
        ],
        "known_limitations": [
            "当前 demo gate 仍是设计层，不是可运行 execution gate",
            "adapter / lifecycle / projection / risk 均仍是 skeleton_defined_not_active",
            "当前还不能接 paper order",
            "当前还没有形成 simulator + lifecycle + risk + audit 的闭环",
            "当前仍绝不能进入 live execution",
        ],
        "operator_guidance": [
            "下一步应该按 recommended_next_build_order 逐层补齐，而不是跳过中间层直接尝试开 gate",
            "当前 handoff 的价值是固定施工顺序与边界，不是提供执行能力",
            "后续任何人接手时，都应先看 missing_prerequisites 与 hard_safety_boundaries",
        ],
        "operator_message": "Current system has a defined demo-gate design stack, but the gate remains closed and no paper execution is permitted.",
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

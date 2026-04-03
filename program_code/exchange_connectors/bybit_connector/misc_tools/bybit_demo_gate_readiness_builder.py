#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_readiness_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / readiness evaluator
- 这一层的白话解释:
  判断 demo/paper gate 目前还缺哪些 prerequisite，为什么现在不能打开。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 K章骨架层

Historical note:
- 开发过程中曾临时标为 G5.2
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

CONTRACT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_contract_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_readiness_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_readiness_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    contract = load_json(CONTRACT_PATH)
    runtime = load_json(RUNTIME_PATH)

    prereq = contract.get("prerequisite_matrix", {})
    readiness_rows = []
    missing = []

    for name, value in prereq.items():
        row = {
            "prerequisite": name,
            "ready": bool(value),
        }
        readiness_rows.append(row)
        if not value:
            missing.append(name)

    readonly_lock_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    gate_can_open = len(missing) == 0 and readonly_lock_ok and contract.get("gate_open") is True
    operator_can_enable = len(missing) == 0 and readonly_lock_ok

    if len(missing) == 0 and operator_can_enable:
        readiness_state = "ready_but_operator_locked"
        readiness_reason = "all technical prerequisites are satisfied, but operator enable is still required before demo gate can open"
    else:
        readiness_state = "not_ready_missing_prerequisites"
        readiness_reason = "demo/paper gate remains closed because required simulator / lifecycle / risk / audit / operator control prerequisites are still incomplete"

    obj = {
        "readiness_type": "bybit_demo_gate_readiness",
        "readiness_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.2",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.2",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "demo/paper gate readiness evaluator",
        },
        "readiness_state": readiness_state,
        "gate_can_open": gate_can_open,
        "operator_can_enable": operator_can_enable,
        "readiness_reason": readiness_reason,
        "source_contract_ref": {
            "contract_version": contract.get("contract_version"),
            "contract_ts_ms": contract.get("ts_ms"),
            "gate_state": contract.get("gate_state"),
            "gate_open": contract.get("gate_open"),
            "gate_ready": contract.get("gate_ready"),
        },
        "runtime_safety_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "system_mode": runtime.get("system_mode"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "readonly_lock_ok": readonly_lock_ok,
        },
        "prerequisite_evaluation": readiness_rows,
        "missing_prerequisites": missing,
        "readiness_summary": {
            "total_prerequisites": len(prereq),
            "ready_count": sum(1 for x in prereq.values() if x is True),
            "missing_count": len(missing),
            "gate_can_open_now": gate_can_open,
            "operator_can_enable_now": operator_can_enable,
        },
        "readiness_explainer": {
            "not_ready_missing_prerequisites": "基础 contract 已定义，但 prerequisite 仍未补齐，不能开启 demo/paper gate",
            "ready_but_operator_locked": "技术 prerequisite 已满足，但仍需 operator 明确放行",
            "gate_open_for_demo_only": "demo/paper gate 已开启，但仍不允许 live execution",
        },
        "operator_guidance": [
            "当前最重要的是逐项补齐 missing_prerequisites，而不是尝试绕过 gate",
            "即使 readiness 未来变成 ready_but_operator_locked，也仍然只代表 demo/paper 候选，不代表 live execution",
            "主 runtime 仍必须保持 read_only / execution disabled，直到更高阶段明确修改边界",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

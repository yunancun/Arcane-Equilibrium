#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_contract_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / gate contract
- 这一层的白话解释:
  定义 demo/paper gate 的总合同边界，说明 gate 为什么当前必须关闭。

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
- 开发过程中曾临时标为 G5.1
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

CHECKPOINT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_checkpoint_latest.json")
RUNTIME_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    checkpoint = load_json(CHECKPOINT_PATH)
    runtime = load_json(RUNTIME_PATH)

    checkpoint_conclusion = checkpoint.get("checkpoint_conclusion", {})
    runtime_ok = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    prerequisites = {
        "isolated_transition_checkpoint_ready": checkpoint_conclusion.get("checkpoint_ready") is True,
        "simulator_adapter_ready": False,
        "paper_order_lifecycle_ready": False,
        "paper_position_balance_projection_ready": False,
        "pretrade_risk_gate_integrated": False,
        "paper_audit_trail_ready": False,
        "explicit_operator_enable_switch_ready": False,
        "demo_gate_acceptance_ready": False,
    }

    obj = {
        "contract_type": "bybit_demo_gate_contract",
        "contract_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "exchange": "bybit",
        "stage": "G5.1",
        "revision_tree_context": {
            "section": "G5",
            "subsection": "G5.1",
            "section_meaning": "demo/paper gate 设计层",
            "current_focus": "demo/paper gate contract skeleton",
        },
        "gate_state": "closed_contract_defined",
        "gate_open": False,
        "gate_ready": False,
        "gate_reason": "isolated replay proved transition candidate semantics only in sandbox context; demo/paper gate must remain closed until simulator, paper lifecycle, risk, audit, and explicit operator controls are implemented and validated",
        "source_refs": {
            "transition_checkpoint_version": checkpoint.get("checkpoint_version"),
            "transition_checkpoint_ts_ms": checkpoint.get("ts_ms"),
            "runtime_state_version": runtime.get("state_version"),
            "runtime_ts_ms": runtime.get("ts_ms"),
        },
        "transition_engine_context": {
            "positive_candidate_path_proven_in_isolation": checkpoint_conclusion.get("positive_candidate_path_proven_in_isolation"),
            "negative_blocking_path_proven_in_isolation": checkpoint_conclusion.get("negative_blocking_path_proven_in_isolation"),
            "execution_still_forbidden": checkpoint_conclusion.get("execution_still_forbidden"),
            "checkpoint_ready": checkpoint_conclusion.get("checkpoint_ready"),
        },
        "runtime_safety_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "system_mode": runtime.get("system_mode"),
            "observer_state": runtime.get("observer_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "readonly_lock_ok": runtime_ok,
        },
        "prerequisite_matrix": prerequisites,
        "gate_summary": {
            "prerequisite_count": len(prerequisites),
            "prerequisites_currently_true": sum(1 for v in prerequisites.values() if v is True),
            "prerequisites_currently_false": sum(1 for v in prerequisites.values() if v is False),
            "gate_contract_defined": True,
            "gate_can_open_now": False,
        },
        "gate_explainer": {
            "closed_contract_defined": "gate 已定义，但当前明确关闭，不能进入 demo/paper execution",
            "ready_but_operator_locked": "技术条件满足，但仍需显式 operator enable 才能打开",
            "gate_open_for_demo_only": "只允许 demo/paper，不允许 live execution",
        },
        "operator_constraints": [
            "主系统当前仍必须保持 read_only",
            "execution_state 必须继续保持 disabled",
            "demo/paper gate 打开前，必须先完成 simulator / paper lifecycle / 风控 / 审计链路",
            "demo gate 即使未来开启，也不等于 live execution gate 开启",
        ],
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_handoff.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / handoff
- 这一层的白话解释:
  把 J 章当前状态、限制、下一步施工顺序整理成交接文件。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 handoff 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.5
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

SUMMARY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_summary_latest.json")

OUT_DIR = SUMMARY_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_handoff_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_handoff_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    summary = load_json(SUMMARY_PATH)
    status = summary.get("final_status", {})

    report = {
        "handoff_type": "bybit_transition_engine_handoff",
        "handoff_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G4.5",
        "revision_tree_context": {
            "section": "G",
            "subsection": "G4.5",
            "section_meaning": "隔离 replay / transition engine skeleton 验证层",
            "current_focus": "transition engine skeleton handoff"
        },
        "current_status": {
            "transition_engine_skeleton_ready": status.get("transition_engine_skeleton_ready"),
            "candidate_transition_supported": status.get("candidate_transition_supported"),
            "negative_blocking_supported": status.get("negative_blocking_supported"),
            "execution_permitted": status.get("execution_permitted"),
            "demo_gate_open": status.get("demo_gate_open"),
            "live_execution_open": status.get("live_execution_open")
        },
        "what_has_been_proven": [
            "正向 replay path 可在隔离上下文中到达 candidate_transition_open",
            "负向 replay path 会在隔离上下文中保持 blocked",
            "transition-engine skeleton 已具备 matrix / audit / rule / summary 闭环",
            "即使正向 candidate 成立，execution 仍被严格禁止"
        ],
        "hard_safety_boundaries": [
            "主系统仍必须保持 read_only",
            "execution_state 必须保持 disabled",
            "demo gate 必须保持关闭",
            "live execution 必须保持关闭",
            "不能把 replay candidate 误当成真实交易放行"
        ],
        "recommended_next_build_order": [
            "1. transition rule detail expansion",
            "2. transition state graph skeleton",
            "3. transition audit enrichment",
            "4. demo/paper gate contract design",
            "5. simulator-facing pretrade guard integration"
        ],
        "known_limitations": [
            "当前仍是 skeleton，不是正式 transition engine",
            "当前 candidate 来自隔离 replay，而不是真实线上业务流",
            "尚未与 demo/paper gate 打通",
            "尚未与 pretrade risk gate 打通",
            "尚未进入任何 live execution 路径"
        ],
        "operator_message": "Transition-engine skeleton is structurally validated in isolated replay tests, but the production system remains strictly observe-only."
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

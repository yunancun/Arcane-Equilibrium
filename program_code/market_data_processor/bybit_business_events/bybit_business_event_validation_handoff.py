#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_validation_handoff.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4.3 handoff
- 这一层的白话解释:
  把 G 章当前验证结果、主系统边界、后续施工建议整理成交接文件，
  方便后续明确“G 已收口到什么程度、接下来该先做什么”。

Role:
- 汇总 G4.1 acceptance suite + G4.2 regression summary + 主 runtime 边界
- 输出 G 章 handoff latest

Purpose in system:
- 给 G 章提供正式 handoff 层
- 为后续接回 H/I 主线提供稳定交接依据

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 当前不会放开真实下单
- 这里只负责 G 章交接说明
'''
"""

import json
import time
from pathlib import Path
import os

ACCEPTANCE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_acceptance_suite_latest.json")
SUMMARY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_regression_summary_latest.json")
SUMMARY_CONTRACT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_regression_contract_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_validation_handoff_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ts_ms = int(time.time() * 1000)

    acceptance = load_json(ACCEPTANCE_PATH)
    summary = load_json(SUMMARY_PATH)
    summary_contract = load_json(SUMMARY_CONTRACT_PATH)
    runtime = load_json(RUNTIME_PATH)

    handoff_state = (
        "g_validation_closed_ready_to_return_h_i"
        if (
            acceptance.get("overall_ok") is True
            and summary.get("summary_ok") is True
            and summary_contract.get("overall_ok") is True
        )
        else "g_validation_not_yet_closed"
    )

    report = {
        "handoff_type": "bybit_business_event_validation_handoff",
        "handoff_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "G4.3",
        "handoff_state": handoff_state,
        "handoff_ok": handoff_state == "g_validation_closed_ready_to_return_h_i",
        "current_status": {
            "acceptance_ok": acceptance.get("overall_ok"),
            "summary_ok": summary.get("summary_ok"),
            "summary_state": summary.get("summary_state"),
            "runtime_protected": summary.get("runtime_protection", {}).get("protected"),
        },
        "g_validation_summary": {
            "positive_nonempty_path_verified": acceptance.get("summary", {}).get("positive_nonempty_path_verified"),
            "negative_blocked_path_verified": acceptance.get("summary", {}).get("negative_blocked_path_verified"),
            "runtime_protection_preserved": acceptance.get("summary", {}).get("runtime_protection_preserved"),
        },
        "runtime_safety_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "system_mode": runtime.get("system_mode"),
            "execution_state": runtime.get("execution_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
        },
        "hard_safety_boundaries": [
            "主系统当前必须继续保持 read_only",
            "execution_state 必须继续保持 disabled",
            "G 章 replay / negative / regression 输出不得污染主 runtime",
            "J/K 即使继续提前补结构层，也不等于 H/I 可以跳过",
            "在 H/I 正式回补前，不应把 J/K 视为正式完工章节"
        ],
        "recommended_next_build_order": summary.get("recommended_next_build_order", []),
        "important_strategy_note": summary.get("important_strategy_note", {}),
        "operator_guidance": [
            "G 章当前应视为已完成本轮验证收口，可以把主线切回 H/I",
            "后续若继续补 J/K，也应限定在结构层、测试层、审计层",
            "如果后面有人接手，应先看 hard_safety_boundaries，再看 recommended_next_build_order"
        ],
        "operator_message": (
            "G-stage validation is now closed enough to return to H/I, while keeping main runtime read_only and allowing only structural hardening for J/K."
            if handoff_state == "g_validation_closed_ready_to_return_h_i"
            else "G-stage validation is not fully closed yet."
        )
    }

    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_validation_handoff_{ts_ms}.json"
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

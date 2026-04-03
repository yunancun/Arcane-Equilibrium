#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_regression_summary.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4.2 regression summary
- 这一层的白话解释:
  把 G1/G2/G3/G4.1 的结果收口成人工一眼可读的回归总结，
  方便后续确认 G 章是否已可视为正式收口。

Role:
- 汇总 acceptance suite、主 runtime 保护状态、以及后续建议施工顺序

Purpose in system:
- 给 G 章提供正式 summary 层
- 为后续工作记录、handoff、以及回到 H/I 主线提供稳定依据

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 当前不会放开真实下单
- 这里只负责 G 章回归总结
'''
"""

import json
import time
from pathlib import Path
import os

ACCEPTANCE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_acceptance_suite_latest.json")
ACCEPTANCE_CONTRACT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_acceptance_contract_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_regression_summary_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    ts_ms = int(time.time() * 1000)

    acceptance = load_json(ACCEPTANCE_PATH)
    acceptance_contract = load_json(ACCEPTANCE_CONTRACT_PATH)
    runtime = load_json(RUNTIME_PATH)

    runtime_protected = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
        and runtime.get("overall_runtime_state") == "ready_readonly_observer"
    )

    acceptance_ok = acceptance.get("overall_ok") is True and acceptance_contract.get("overall_ok") is True
    positive_ok = acceptance.get("summary", {}).get("positive_nonempty_path_verified") is True
    negative_ok = acceptance.get("summary", {}).get("negative_blocked_path_verified") is True

    summary_state = "g_validation_complete_ready_for_h_i" if (acceptance_ok and positive_ok and negative_ok and runtime_protected) else "g_validation_incomplete"

    report = {
        "summary_type": "bybit_business_event_regression_summary",
        "summary_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "G4.2",
        "summary_state": summary_state,
        "summary_ok": summary_state == "g_validation_complete_ready_for_h_i",
        "high_level_reason": (
            "G1/G2/G3/G4 acceptance paths are in place, positive non-empty path and negative blocked path are both verified, and main runtime remains protected"
            if summary_state == "g_validation_complete_ready_for_h_i"
            else "some G-stage acceptance or runtime-protection checks are still incomplete"
        ),
        "acceptance_layer": {
            "report_version": acceptance.get("report_version"),
            "overall_ok": acceptance.get("overall_ok"),
            "failed_count": acceptance.get("failed_count"),
            "positive_nonempty_path_verified": acceptance.get("summary", {}).get("positive_nonempty_path_verified"),
            "negative_blocked_path_verified": acceptance.get("summary", {}).get("negative_blocked_path_verified"),
            "runtime_protection_preserved": acceptance.get("summary", {}).get("runtime_protection_preserved"),
        },
        "runtime_protection": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "system_mode": runtime.get("system_mode"),
            "execution_state": runtime.get("execution_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "protected": runtime_protected,
        },
        "important_strategy_note": {
            "g_now_should_be_closed_first": True,
            "j_k_can_continue_structural_hardening": True,
            "h_i_should_not_be_skipped_for_formal_completion": True,
            "reason": "J/K 可以继续补结构层、测试层、审计层，但在 H/I 回补前，不应视为正式完工章节"
        },
        "recommended_next_build_order": [
            "H1. thought_gate",
            "H2. query_budget",
            "H3. model_router v2",
            "I1. decision lease schema",
            "I2. lease freshness / validity"
        ],
        "summary_explainer": {
            "g_validation_complete_ready_for_h_i": "G 章验证层已基本收口，后续正式主线应回到 H/I",
            "g_validation_incomplete": "G 章仍有缺口，暂不应把后续主线切到 H/I"
        }
    }

    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_regression_summary_{ts_ms}.json"
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

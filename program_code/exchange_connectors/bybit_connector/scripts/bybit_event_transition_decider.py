#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_transition_decider.py

Role:
- 读取 D23.3 的 transition input
- 输出统一的 transition decision
- 当前阶段只做“是否允许进入未来 transition engine”的决策外壳

Purpose in system:
- 这是 D23.4 的决策壳层
- 先标准化 transition decision contract
- 为后续真正状态跃迁引擎提供稳定上游

Current behavior:
- input_ready_but_empty -> keep_observe_only
- input_ready_for_transition_engine -> allow_transition_engine
- input_not_ready -> block_transition_engine

Downstream:
- future transition engine
- future demo/paper gate
- future event-driven audit / consistency checks

Maintenance notes:
- 当前不能输出任何 execution 许可
- 当前 allow_transition_engine 仅代表“可以进入后续状态跃迁模块”，不代表可以交易
'''
"""

import json
import time
from pathlib import Path

INPUT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_input_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_transition_decision_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_event_transition_decision_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    inp = load_json(INPUT_PATH)

    readiness = inp.get("transition_readiness")
    transition_allowed = bool(inp.get("transition_allowed"))

    if readiness == "input_ready_but_empty":
        decision_code = "keep_observe_only"
        decision_allowed = False
        decision_reason = "transition input is healthy but empty, so stay in observe-only state"
    elif readiness == "input_ready_for_transition_engine" and transition_allowed:
        decision_code = "allow_transition_engine"
        decision_allowed = True
        decision_reason = "transition input is healthy and contains real business-event flow"
    else:
        decision_code = "block_transition_engine"
        decision_allowed = False
        decision_reason = "transition input is not ready enough for downstream transition processing"

    result = {
        "decision_type": "bybit_event_transition_decision",
        "decision_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "D23.4",
        "decision_code": decision_code,
        "decision_allowed": decision_allowed,
        "decision_reason": decision_reason,
        "source_input_ref": {
            "input_version": inp.get("input_version"),
            "input_ts_ms": inp.get("ts_ms"),
            "transition_readiness": readiness,
            "transition_allowed": transition_allowed,
        },
        "transition_context": {
            "runtime_context": inp.get("runtime_context", {}),
            "business_event_context": inp.get("business_event_context", {}),
            "event_driven_state_context": inp.get("event_driven_state_context", {}),
            "event_driven_phase_context": inp.get("event_driven_phase_context", {}),
        },
        "decision_explainer": {
            "keep_observe_only": "输入健康但仍为空，继续保持观察态",
            "allow_transition_engine": "输入健康且已有真实业务事件，可进入后续 transition engine",
            "block_transition_engine": "输入仍不满足要求，阻止进入后续 transition engine",
        }
    }

    dated = save_json(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

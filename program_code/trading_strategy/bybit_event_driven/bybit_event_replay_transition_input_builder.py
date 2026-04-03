#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_transition_input_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / transition input
- 这一层的白话解释:
  验证当 replay 输入完整且非空时，transition input 会变成 ready-for-transition-engine。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 replay harness
- 所有 replay / negative / consistency 输出都应与主 runtime 隔离

Maintenance notes:
- 本批修正主要增强白话说明，不改变 G 章归属
- 本批修正不改文件名、latest 路径、JSON stage 字段
- 如后续要把 replay 结果真正接到更高层，必须显式经过 J / K 章节边界
\'\'\'
"""
import json
import time
from pathlib import Path
import os

STATE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_state_latest.json")
PHASE_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_phase_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = STATE_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_event_replay_transition_input_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)

    state = load_json(STATE_PATH)
    phase = load_json(PHASE_PATH)
    runtime = load_json(RUNTIME_PATH)

    positive = (
        state.get("event_driven_readiness") == "event_flow_present"
        and phase.get("phase_code") == "observer_event_flow_seen"
        and phase.get("phase_ready") is True
        and runtime.get("overall_runtime_state") == "ready_readonly_observer"
    )

    if positive:
        transition_readiness = "input_ready_for_transition_engine"
        transition_allowed = True
        transition_reason = "inputs are healthy, consistent, and replay business events are present"
    else:
        transition_readiness = "input_not_ready"
        transition_allowed = False
        transition_reason = "replay-driven inputs are not ready"

    report = {
        "input_type": "bybit_event_replay_transition_input",
        "input_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G2.3",
        "transition_readiness": transition_readiness,
        "transition_allowed": transition_allowed,
        "transition_reason": transition_reason,
        "source_refs": {
            "runtime_ts_ms": runtime.get("ts_ms"),
            "replay_state_ts_ms": state.get("ts_ms"),
            "replay_phase_ts_ms": phase.get("ts_ms"),
        },
        "runtime_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
        },
        "replay_state_context": {
            "event_driven_readiness": state.get("event_driven_readiness"),
            "has_business_events": state.get("has_business_events"),
            "normalized_count": state.get("normalized_count"),
            "topic_observation": state.get("topic_observation", {}),
        },
        "replay_phase_context": {
            "phase_code": phase.get("phase_code"),
            "phase_ready": phase.get("phase_ready"),
            "phase_reason": phase.get("phase_reason"),
        },
        "transition_input_explainer": {
            "input_ready_for_transition_engine": "输入完整且 replay 已有真实业务事件，可进入 transition engine 隔离验证",
            "input_not_ready": "输入层仍存在缺口或状态不一致，不能进入 transition engine",
        },
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_transition_input")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

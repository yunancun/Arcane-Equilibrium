#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_phase_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / phase
- 这一层的白话解释:
  验证 phase 层会从空 feed 观察态切换到 observer_event_flow_seen。

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

OUT_DIR = STATE_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_replay_phase_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_event_replay_phase_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    state = load_json(STATE_PATH)

    state_readiness = state.get("event_driven_readiness", "unknown")
    has_business_events = bool(state.get("has_business_events"))
    normalized_count = int(state.get("normalized_count", 0) or 0)

    if state_readiness == "event_flow_present" and has_business_events and normalized_count > 0:
        phase_code = "observer_event_flow_seen"
        phase_ready = True
        phase_reason = "replayed business events are present and phase is no longer empty-feed observer state"
        allow_future_transition_engine = True
        allow_demo_gate_consideration = False
        allow_live_execution = False
    elif state_readiness in ("healthy_but_empty", "healthy_no_business_events_yet") or (not has_business_events and normalized_count == 0):
        phase_code = "observer_only_empty_feed"
        phase_ready = False
        phase_reason = "event-driven replay feed is healthy but still empty"
        allow_future_transition_engine = False
        allow_demo_gate_consideration = False
        allow_live_execution = False
    else:
        phase_code = "observer_feed_not_ready"
        phase_ready = False
        phase_reason = "event-driven replay side is not trustworthy enough for downstream phase advancement"
        allow_future_transition_engine = False
        allow_demo_gate_consideration = False
        allow_live_execution = False

    report = {
        "phase_type": "bybit_event_replay_phase",
        "phase_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G2.2",
        "phase_code": phase_code,
        "phase_ready": phase_ready,
        "phase_reason": phase_reason,
        "source_state_ref": {
            "state_version": state.get("state_version"),
            "state_ts_ms": state.get("ts_ms"),
            "event_driven_readiness": state_readiness,
            "business_event_state_code": state.get("business_event_state_code"),
            "has_business_events": has_business_events,
            "normalized_count": normalized_count,
        },
        "runtime_context": state.get("runtime_context", {}),
        "state_machine_hint": {
            "allow_future_transition_engine": allow_future_transition_engine,
            "allow_demo_gate_consideration": allow_demo_gate_consideration,
            "allow_live_execution": allow_live_execution,
        },
        "phase_explainer": {
            "observer_only_empty_feed": "事件驱动 replay 链健康但为空，只能继续观察",
            "observer_event_flow_seen": "已观察到 replay 注入的真实业务事件，可作为后续 transition engine 输入",
            "observer_feed_not_ready": "事件驱动 replay 侧当前不可信，不能用于下游推进",
        },
    }

    dated = save_json(report)

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_state_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / state
- 这一层的白话解释:
  验证当 replay 中真的出现业务事件时，状态层会从空态切到 event_flow_present。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 state 语义切换
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

REPLAY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/replay/bybit_business_event_replay_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_replay_state_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)

    replay = load_json(REPLAY_PATH)
    runtime = load_json(RUNTIME_PATH)

    has_business_events = bool(replay.get("has_business_events"))
    normalized_count = int(replay.get("normalized_count", 0))
    topic_counts = replay.get("topic_counts") or {}
    event_type_counts = replay.get("event_type_counts") or {}
    events = replay.get("events") or []

    topic_observation = {
        "wallet": int(topic_counts.get("wallet", 0)),
        "order": int(topic_counts.get("order", 0)),
        "execution": int(topic_counts.get("execution", 0)),
        "position": int(topic_counts.get("position", 0)),
    }

    last_event_ts_ms = max((int(e.get("event_ts_ms", 0)) for e in events), default=0) or None
    last_event_age_ms = (now_ms - last_event_ts_ms) if last_event_ts_ms else None

    if has_business_events and normalized_count > 0:
        readiness = "event_flow_present"
    elif replay.get("report_type") == "bybit_business_event_replay_harness":
        readiness = "healthy_but_empty"
    else:
        readiness = "not_ready"

    report = {
        "state_type": "bybit_event_replay_state",
        "state_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G2.1",
        "event_driven_readiness": readiness,
        "has_business_events": has_business_events,
        "normalized_count": normalized_count,
        "topic_observation": topic_observation,
        "topic_counts": topic_counts,
        "event_type_counts": event_type_counts,
        "last_event_ts_ms": last_event_ts_ms,
        "last_event_age_ms": last_event_age_ms,
        "source_replay_ref": {
            "report_version": replay.get("report_version"),
            "report_ts_ms": replay.get("ts_ms"),
            "replayed_count": replay.get("replayed_count"),
            "normalized_count": replay.get("normalized_count"),
        },
        "runtime_context": {
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "observer_state": runtime.get("observer_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "ws_signal_strength": runtime.get("ws_signal_strength"),
        },
        "state_explainer": {
            "event_flow_present": "replay 中已经有真实非空业务事件样本，语义上可视为 event-flow-present",
            "healthy_but_empty": "replay 结构正常，但当前事件为空",
            "not_ready": "replay 输入层不满足使用条件",
        },
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_state")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

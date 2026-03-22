#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_transition_decider.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / decision
- 这一层的白话解释:
  验证正向 replay 会把决策推进到 allow_transition_engine，但仍只发生在隔离验证上下文。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 decision 语义切换
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

INPUT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_input_latest.json")

OUT_DIR = INPUT_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_event_replay_transition_decision_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)
    inp = load_json(INPUT_PATH)

    if inp.get("transition_allowed") is True:
        decision_code = "allow_transition_engine"
        decision_allowed = True
        decision_reason = "transition input is healthy and replay event flow is present"
    else:
        decision_code = "block_transition_engine"
        decision_allowed = False
        decision_reason = "transition input is not ready"

    report = {
        "decision_type": "bybit_event_replay_transition_decision",
        "decision_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G2.4",
        "decision_code": decision_code,
        "decision_allowed": decision_allowed,
        "decision_reason": decision_reason,
        "source_input_ref": {
            "input_version": inp.get("input_version"),
            "input_ts_ms": inp.get("ts_ms"),
            "transition_readiness": inp.get("transition_readiness"),
            "transition_allowed": inp.get("transition_allowed"),
        },
        "transition_context": {
            "runtime_context": inp.get("runtime_context", {}),
            "replay_state_context": inp.get("replay_state_context", {}),
            "replay_phase_context": inp.get("replay_phase_context", {}),
        },
        "decision_explainer": {
            "allow_transition_engine": "replay 正向语义已成立，可进入下一层 transition engine 设计验证",
            "block_transition_engine": "replay 正向语义未成立，阻止进入下一层",
        },
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_transition_decision")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

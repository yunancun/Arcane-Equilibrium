#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_transition_outcome_builder.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / outcome
- 这一层的白话解释:
  验证正向 replay 的最终 outcome 会进入 transition_engine_entry_allowed 语义。

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

DECISION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_decision_latest.json")

OUT_DIR = DECISION_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_event_replay_transition_outcome_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)
    decision = load_json(DECISION_PATH)

    if decision.get("decision_allowed") is True:
        outcome_code = "transition_engine_entry_allowed"
        outcome_ok = True
        outcome_reason = "isolated replay validation passed the positive transition path"
    else:
        outcome_code = "transition_engine_blocked"
        outcome_ok = False
        outcome_reason = "isolated replay validation did not pass the positive transition path"

    report = {
        "outcome_type": "bybit_event_replay_transition_outcome",
        "outcome_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G2.5",
        "outcome_code": outcome_code,
        "outcome_ok": outcome_ok,
        "outcome_reason": outcome_reason,
        "source_decision_ref": {
            "decision_version": decision.get("decision_version"),
            "decision_ts_ms": decision.get("ts_ms"),
            "decision_code": decision.get("decision_code"),
            "decision_allowed": decision.get("decision_allowed"),
        },
        "decision_context": decision.get("transition_context", {}),
        "outcome_explainer": {
            "transition_engine_entry_allowed": "在 replay 隔离验证上下文中，已证明正向 transition path 可达",
            "transition_engine_blocked": "在 replay 隔离验证上下文中，正向 transition path 不可达",
        },
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_transition_outcome")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

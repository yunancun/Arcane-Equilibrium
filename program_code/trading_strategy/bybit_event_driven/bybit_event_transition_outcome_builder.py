#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_event_transition_outcome_builder.py

Role:
- 读取 D23.4 transition decision
- 输出统一 transition outcome
- 当前阶段只做 outcome/stub，不做真正状态切换执行

Purpose in system:
- 给后续真正 transition engine 提供稳定 outcome contract
- 给未来 demo gate / audit / consistency check 提供标准结果层

Current behavior:
- keep_observe_only -> outcome=observe_only_retained
- allow_transition_engine -> outcome=transition_engine_entry_allowed
- block_transition_engine -> outcome=transition_engine_blocked

Maintenance notes:
- 当前 outcome 仍然不能产生任何 execution 权限
- 这里只是在 event-driven 链路中建立一层“结果标准化”
'''
"""

import json
import time
from pathlib import Path
import os

DECISION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/bybit_event_transition_decision_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_transition_outcome_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_event_transition_outcome_{ts_ms}.json"
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    OUT_LATEST.write_text(text, encoding="utf-8")
    dated.write_text(text, encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    decision = load_json(DECISION_PATH)

    decision_code = decision.get("decision_code")
    decision_allowed = bool(decision.get("decision_allowed"))

    if decision_code == "keep_observe_only":
        outcome_code = "observe_only_retained"
        outcome_ok = True
        outcome_reason = "system intentionally remains in observe-only state"
    elif decision_code == "allow_transition_engine" and decision_allowed:
        outcome_code = "transition_engine_entry_allowed"
        outcome_ok = True
        outcome_reason = "inputs are healthy enough for future transition engine entry"
    else:
        outcome_code = "transition_engine_blocked"
        outcome_ok = False
        outcome_reason = "downstream transition engine remains blocked by current decision state"

    result = {
        "outcome_type": "bybit_event_transition_outcome",
        "outcome_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "D23.5",
        "outcome_code": outcome_code,
        "outcome_ok": outcome_ok,
        "outcome_reason": outcome_reason,
        "source_decision_ref": {
            "decision_version": decision.get("decision_version"),
            "decision_ts_ms": decision.get("ts_ms"),
            "decision_code": decision_code,
            "decision_allowed": decision_allowed,
        },
        "decision_context": decision.get("transition_context", {}),
        "outcome_explainer": {
            "observe_only_retained": "系统明确保持观察态，不推进 transition engine",
            "transition_engine_entry_allowed": "允许未来 transition engine 接管下一层状态推进",
            "transition_engine_blocked": "当前仍阻止进入 transition engine",
        }
    }

    dated = save_json(result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

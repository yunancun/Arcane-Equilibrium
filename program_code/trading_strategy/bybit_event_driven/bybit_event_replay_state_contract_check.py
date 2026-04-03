#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_state_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / state
- 这一层的白话解释:
  验证当 replay 中真的出现业务事件时，状态层会从空态切到 event_flow_present。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 G 章验证输出在后续维护时发生结构漂移，给 regression / consistency / handoff 提供稳定依据。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 contract check 层
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
OUT_LATEST = OUT_DIR / "bybit_event_replay_state_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    now_ms = int(time.time() * 1000)
    state = load_json(STATE_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("state_exists", state is not None, str(STATE_PATH))

    if state is not None:
        add("state_type_expected", state.get("state_type") == "bybit_event_replay_state", state.get("state_type"))
        add("state_version_v1", state.get("state_version") == "v1", state.get("state_version"))
        add("exchange_bybit", state.get("exchange") == "bybit", state.get("exchange"))
        add("stage_g2_1", state.get("stage") == "G2.1", state.get("stage"))
        add("event_driven_readiness_positive", state.get("event_driven_readiness") == "event_flow_present", state.get("event_driven_readiness"))
        add("has_business_events_true", state.get("has_business_events") is True, state.get("has_business_events"))
        add("normalized_count_ge_4", int(state.get("normalized_count", 0)) >= 4, state.get("normalized_count"))

        topic_obs = state.get("topic_observation") or {}
        add("topic_observation_wallet_gt_0", int(topic_obs.get("wallet", 0)) > 0, topic_obs)
        add("topic_observation_order_gt_0", int(topic_obs.get("order", 0)) > 0, topic_obs)
        add("topic_observation_execution_gt_0", int(topic_obs.get("execution", 0)) > 0, topic_obs)
        add("topic_observation_position_gt_0", int(topic_obs.get("position", 0)) > 0, topic_obs)

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_event_replay_state_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_state_contract")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

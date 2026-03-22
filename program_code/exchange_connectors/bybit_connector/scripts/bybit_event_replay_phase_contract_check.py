#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_phase_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / phase
- 这一层的白话解释:
  验证 phase 层会从空 feed 观察态切换到 observer_event_flow_seen。

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

PHASE_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_phase_latest.json")

OUT_DIR = PHASE_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_event_replay_phase_contract_latest.json"


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
    phase = load_json(PHASE_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("phase_exists", phase is not None, str(PHASE_PATH))

    if phase is not None:
        add("phase_type_expected", phase.get("phase_type") == "bybit_event_replay_phase", phase.get("phase_type"))
        add("phase_version_v1", phase.get("phase_version") == "v1", phase.get("phase_version"))
        add("exchange_bybit", phase.get("exchange") == "bybit", phase.get("exchange"))
        add("stage_g2_2", phase.get("stage") == "G2.2", phase.get("stage"))
        add("phase_code_positive", phase.get("phase_code") == "observer_event_flow_seen", phase.get("phase_code"))
        add("phase_ready_true", phase.get("phase_ready") is True, phase.get("phase_ready"))

        hint = phase.get("state_machine_hint") or {}
        add("allow_future_transition_engine_true", hint.get("allow_future_transition_engine") is True, hint)

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_event_replay_phase_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_phase_contract")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

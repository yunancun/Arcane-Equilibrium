#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_transition_consistency_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4. acceptance / regression / consistency
- 这一层的白话解释:
  对正向 replay 链做一致性回归校验，确保 state / phase / input / decision / outcome 语义联动正确。

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

CHECK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_consistency_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_replay_transition_consistency_contract_latest.json"


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
    obj = load_json(CHECK_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("report_exists", obj is not None, str(CHECK_PATH))

    if obj is not None:
        add("report_type_expected", obj.get("report_type") == "bybit_event_replay_transition_consistency_check", obj.get("report_type"))
        add("report_version_v1", obj.get("report_version") == "v1", obj.get("report_version"))
        add("overall_ok_true", obj.get("overall_ok") is True, obj.get("overall_ok"))
        add("failed_count_zero", int(obj.get("failed_count", -1)) == 0, obj.get("failed_count"))
        add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__)
        add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__)

    failed = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_event_replay_transition_consistency_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    dated = save_report(report, OUT_LATEST, "bybit_event_replay_transition_consistency_contract")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

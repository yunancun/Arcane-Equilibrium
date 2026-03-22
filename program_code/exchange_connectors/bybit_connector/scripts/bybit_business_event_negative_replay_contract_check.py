#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_negative_replay_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G3. 负向阻断验证 / negative replay
- 这一层的白话解释:
  把不完整负向样本重放成业务事件，验证缺失 topic 时仍应保持阻断。

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

REPLAY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay_negative/bybit_business_event_negative_replay_latest.json")
OUT_DIR = REPLAY_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_business_event_negative_replay_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_negative_replay_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(REPLAY_PATH)
    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("replay_exists", obj is not None, str(REPLAY_PATH))
    if obj is not None:
        add("report_type_expected", obj.get("report_type") == "bybit_business_event_negative_replay_harness", obj.get("report_type"))
        add("report_version_v1", obj.get("report_version") == "v1", obj.get("report_version"))
        add("exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
        add("stage_g3_1", obj.get("stage") == "G3.1", obj.get("stage"))
        add("normalized_count_eq_1", obj.get("normalized_count") == 1, obj.get("normalized_count"))
        add("has_business_events_true", obj.get("has_business_events") is True, obj.get("has_business_events"))
        tc = obj.get("topic_counts") or {}
        add("wallet_present", tc.get("wallet", 0) == 1, tc)
        add("order_missing", tc.get("order", 0) == 0, tc)
        add("execution_missing", tc.get("execution", 0) == 0, tc)
        add("position_missing", tc.get("position", 0) == 0, tc)

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_business_event_negative_replay_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }
    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

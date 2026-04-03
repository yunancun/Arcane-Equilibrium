#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_summary_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / summary
- 这一层的白话解释:
  把 J 章各层统一汇总成人工可读总状态。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 J 章脚本在后续维护时发生结构漂移，给 summary / handoff / final audit / checkpoint 提供稳定上游。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 contract check 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.4
- 该临时编号现已废弃
- 后续以 Revision 2 正式章节树为准

Maintenance notes:
- 本批修正只改头部注释归位，不改文件名、latest 路径、JSON stage 字段
- 如后续要改 stage / 输出字段，必须单独做兼容性修订
\'\'\'
"""
import json
import time
from pathlib import Path
import os

SUMMARY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_summary_latest.json")

OUT_DIR = SUMMARY_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_summary_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_summary_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(SUMMARY_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("summary_exists", obj is not None, str(SUMMARY_PATH))

    if obj is not None:
        final_status = obj.get("final_status", {})
        add("summary_type_expected", obj.get("summary_type") == "bybit_transition_engine_summary", obj.get("summary_type"))
        add("summary_version_v1", obj.get("summary_version") == "v1", obj.get("summary_version"))
        add("stage_g4_4", obj.get("stage") == "G4.4", obj.get("stage"))
        add("transition_engine_skeleton_ready_true", final_status.get("transition_engine_skeleton_ready") is True, final_status)
        add("candidate_transition_supported_true", final_status.get("candidate_transition_supported") is True, final_status)
        add("negative_blocking_supported_true", final_status.get("negative_blocking_supported") is True, final_status)
        add("execution_permitted_false", final_status.get("execution_permitted") is False, final_status.get("execution_permitted"))
        add("demo_gate_open_false", final_status.get("demo_gate_open") is False, final_status.get("demo_gate_open"))
        add("live_execution_open_false", final_status.get("live_execution_open") is False, final_status.get("live_execution_open"))

    failed = [x for x in checks if not x["ok"]]
    report = {
        "report_type": "bybit_transition_engine_summary_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

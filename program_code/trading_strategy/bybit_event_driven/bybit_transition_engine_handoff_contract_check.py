#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_handoff_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / handoff
- 这一层的白话解释:
  把 J 章当前状态、限制、下一步施工顺序整理成交接文件。

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
- 开发过程中曾临时标为 G4.5
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

HANDOFF_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_handoff_latest.json")

OUT_DIR = HANDOFF_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_handoff_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_handoff_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(HANDOFF_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("handoff_exists", obj is not None, str(HANDOFF_PATH))

    if obj is not None:
        status = obj.get("current_status", {})
        add("handoff_type_expected", obj.get("handoff_type") == "bybit_transition_engine_handoff", obj.get("handoff_type"))
        add("handoff_version_v1", obj.get("handoff_version") == "v1", obj.get("handoff_version"))
        add("stage_g4_5", obj.get("stage") == "G4.5", obj.get("stage"))
        add("current_status_present", isinstance(status, dict), type(status).__name__)
        add("transition_engine_skeleton_ready_true", status.get("transition_engine_skeleton_ready") is True, status)
        add("execution_permitted_false", status.get("execution_permitted") is False, status.get("execution_permitted"))
        add("demo_gate_open_false", status.get("demo_gate_open") is False, status.get("demo_gate_open"))
        add("live_execution_open_false", status.get("live_execution_open") is False, status.get("live_execution_open"))
        add("hard_safety_boundaries_list", isinstance(obj.get("hard_safety_boundaries"), list), type(obj.get("hard_safety_boundaries")).__name__)
        add("recommended_next_build_order_list", isinstance(obj.get("recommended_next_build_order"), list), type(obj.get("recommended_next_build_order")).__name__)
        add("known_limitations_list", isinstance(obj.get("known_limitations"), list), type(obj.get("known_limitations")).__name__)

    failed = [x for x in checks if not x["ok"]]
    report = {
        "report_type": "bybit_transition_engine_handoff_contract_check",
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

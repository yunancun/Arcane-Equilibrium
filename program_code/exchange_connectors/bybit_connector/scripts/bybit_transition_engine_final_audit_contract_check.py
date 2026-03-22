#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_final_audit_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / final audit
- 这一层的白话解释:
  对 J 章 skeleton 做总审计，确认语义一致且主系统未被污染。

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
- 开发过程中曾临时标为 G4.6
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

AUDIT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_final_audit_latest.json")

OUT_DIR = AUDIT_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_final_audit_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_final_audit_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(AUDIT_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("audit_exists", obj is not None, str(AUDIT_PATH))

    if obj is not None:
        add("audit_type_expected", obj.get("audit_type") == "bybit_transition_engine_final_audit", obj.get("audit_type"))
        add("audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version"))
        add("overall_ok_true", obj.get("overall_ok") is True, obj.get("overall_ok"))
        add("failed_count_zero", obj.get("failed_count") == 0, obj.get("failed_count"))
        add("total_checks_reasonable", isinstance(obj.get("total_checks"), int) and obj.get("total_checks") >= 10, obj.get("total_checks"))
        add("checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__)
        add("failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__)

    failed = [x for x in checks if not x["ok"]]
    report = {
        "report_type": "bybit_transition_engine_final_audit_contract_check",
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

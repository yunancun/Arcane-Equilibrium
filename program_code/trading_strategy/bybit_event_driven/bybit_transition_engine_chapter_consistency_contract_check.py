#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_transition_engine_chapter_consistency_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J章总控层 / contract check
- 这一层的白话解释:
  校验 J 章 chapter consistency 输出结构是否稳定。
'''
"""

import json
import time
from pathlib import Path

CHECK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_chapter_consistency_latest.json")
OUT_DIR = CHECK_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_chapter_consistency_contract_latest.json"


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    exists = CHECK_PATH.exists()
    add_check(checks, "report_exists", exists, str(CHECK_PATH))

    obj = {}
    if exists:
        obj = json.loads(CHECK_PATH.read_text(encoding="utf-8"))
        add_check(checks, "report_type_expected", obj.get("report_type") == "bybit_transition_engine_chapter_consistency_check", obj.get("report_type"))
        add_check(checks, "report_version_v1", obj.get("report_version") == "v1", obj.get("report_version"))
        add_check(checks, "overall_ok_bool", isinstance(obj.get("overall_ok"), bool), obj.get("overall_ok"))
        add_check(checks, "failed_count_int", isinstance(obj.get("failed_count"), int), obj.get("failed_count"))
        add_check(checks, "checks_list", isinstance(obj.get("checks"), list), type(obj.get("checks")).__name__)
        add_check(checks, "failed_checks_list", isinstance(obj.get("failed_checks"), list), type(obj.get("failed_checks")).__name__)
        add_check(checks, "chapter_summary_present", isinstance(obj.get("chapter_summary"), dict), type(obj.get("chapter_summary")).__name__)

    report = {
        "report_type": "bybit_transition_engine_chapter_consistency_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": all(x["ok"] for x in checks),
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
    }

    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_chapter_consistency_contract_{ts_ms}.json"
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_final_audit_contract_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / final audit
- 这一层的白话解释:
  对 K 章设计层做总审计，确认语义一致且主系统未被污染。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 K 章脚本在后续维护时发生结构漂移，给 summary / handoff / final audit 提供稳定上游。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 contract check 层

Historical note:
- 开发过程中曾临时标为 G5.9
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

CHECK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_final_audit_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_final_audit_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_final_audit_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)

    checks = []
    checks.append(check("audit_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("audit_type_expected", report.get("audit_type") == "bybit_demo_gate_final_audit", report.get("audit_type")))
    checks.append(check("audit_version_v1", report.get("audit_version") == "v1", report.get("audit_version")))
    checks.append(check("overall_ok_bool", isinstance(report.get("overall_ok"), bool), report.get("overall_ok")))
    checks.append(check("failed_count_int", isinstance(report.get("failed_count"), int), report.get("failed_count")))
    checks.append(check("total_checks_int", isinstance(report.get("total_checks"), int), report.get("total_checks")))
    checks.append(check("checks_list", isinstance(report.get("checks"), list), type(report.get("checks")).__name__))
    checks.append(check("failed_checks_list", isinstance(report.get("failed_checks"), list), type(report.get("failed_checks")).__name__))
    checks.append(check("audit_summary_present", isinstance(report.get("audit_summary"), dict), type(report.get("audit_summary")).__name__))
    checks.append(check("audit_explainer_present", isinstance(report.get("audit_explainer"), dict), type(report.get("audit_explainer")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_demo_gate_final_audit_contract_check",
        "report_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_handoff_contract_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / handoff
- 这一层的白话解释:
  把 K 章当前状态、限制、下一步施工顺序整理成交接文件。

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
- 开发过程中曾临时标为 G5.8
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

CHECK_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_handoff_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_handoff_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_handoff_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)
    current_status = report.get("current_status", {})

    checks = []
    checks.append(check("handoff_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("handoff_type_expected", report.get("handoff_type") == "bybit_demo_gate_handoff", report.get("handoff_type")))
    checks.append(check("handoff_version_v1", report.get("handoff_version") == "v1", report.get("handoff_version")))
    checks.append(check("stage_g5_8", report.get("stage") == "G5.8", report.get("stage")))
    checks.append(check("exchange_bybit", report.get("exchange") == "bybit", report.get("exchange")))

    checks.append(check("current_status_present", isinstance(current_status, dict), type(current_status).__name__))
    checks.append(check("gate_can_open_false", current_status.get("gate_can_open") is False, current_status.get("gate_can_open")))
    checks.append(check("operator_can_enable_false", current_status.get("operator_can_enable") is False, current_status.get("operator_can_enable")))

    checks.append(check("runtime_safety_context_present", isinstance(report.get("runtime_safety_context"), dict), type(report.get("runtime_safety_context")).__name__))
    checks.append(check("layer_status_present", isinstance(report.get("layer_status"), dict), type(report.get("layer_status")).__name__))
    checks.append(check("missing_prerequisites_list", isinstance(report.get("missing_prerequisites"), list), type(report.get("missing_prerequisites")).__name__))
    checks.append(check("hard_safety_boundaries_list", isinstance(report.get("hard_safety_boundaries"), list), type(report.get("hard_safety_boundaries")).__name__))
    checks.append(check("recommended_next_build_order_list", isinstance(report.get("recommended_next_build_order"), list), type(report.get("recommended_next_build_order")).__name__))
    checks.append(check("known_limitations_list", isinstance(report.get("known_limitations"), list), type(report.get("known_limitations")).__name__))
    checks.append(check("operator_guidance_list", isinstance(report.get("operator_guidance"), list), type(report.get("operator_guidance")).__name__))
    checks.append(check("operator_message_present", isinstance(report.get("operator_message"), str), type(report.get("operator_message")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_demo_gate_handoff_contract_check",
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

#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_readiness_contract_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / readiness evaluator
- 这一层的白话解释:
  判断 demo/paper gate 目前还缺哪些 prerequisite，为什么现在不能打开。

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
- 开发过程中曾临时标为 G5.2
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

CHECK_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_readiness_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_readiness_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_readiness_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)
    checks = []

    checks.append(check("readiness_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("readiness_type_expected", report.get("readiness_type") == "bybit_demo_gate_readiness", report.get("readiness_type")))
    checks.append(check("readiness_version_v1", report.get("readiness_version") == "v1", report.get("readiness_version")))
    checks.append(check("stage_g5_2", report.get("stage") == "G5.2", report.get("stage")))
    checks.append(check("exchange_bybit", report.get("exchange") == "bybit", report.get("exchange")))
    checks.append(check("readiness_state_allowed", report.get("readiness_state") in {
        "not_ready_missing_prerequisites",
        "ready_but_operator_locked",
        "gate_open_for_demo_only",
    }, report.get("readiness_state")))

    checks.append(check("gate_can_open_bool", isinstance(report.get("gate_can_open"), bool), report.get("gate_can_open")))
    checks.append(check("operator_can_enable_bool", isinstance(report.get("operator_can_enable"), bool), report.get("operator_can_enable")))
    checks.append(check("source_contract_ref_present", isinstance(report.get("source_contract_ref"), dict), type(report.get("source_contract_ref")).__name__))
    checks.append(check("runtime_safety_context_present", isinstance(report.get("runtime_safety_context"), dict), type(report.get("runtime_safety_context")).__name__))
    checks.append(check("prerequisite_evaluation_list", isinstance(report.get("prerequisite_evaluation"), list), type(report.get("prerequisite_evaluation")).__name__))
    checks.append(check("missing_prerequisites_list", isinstance(report.get("missing_prerequisites"), list), type(report.get("missing_prerequisites")).__name__))
    checks.append(check("readiness_summary_present", isinstance(report.get("readiness_summary"), dict), type(report.get("readiness_summary")).__name__))
    checks.append(check("readiness_explainer_present", isinstance(report.get("readiness_explainer"), dict), type(report.get("readiness_explainer")).__name__))
    checks.append(check("operator_guidance_list", isinstance(report.get("operator_guidance"), list), type(report.get("operator_guidance")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_demo_gate_readiness_contract_check",
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

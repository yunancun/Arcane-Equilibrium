#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_pretrade_risk_integration_skeleton_contract_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K2. pretrade risk gate integration
- 这一层的白话解释:
  定义 demo/paper 进入前的风险检查边界，但当前不能真正评估或放行订单。

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
- 开发过程中曾临时标为 G5.6
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

CHECK_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_pretrade_risk_integration_skeleton_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_pretrade_risk_integration_skeleton_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_pretrade_risk_integration_skeleton_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)
    surface = report.get("risk_surface")

    checks = []
    checks.append(check("risk_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("risk_type_expected", report.get("risk_type") == "bybit_pretrade_risk_integration_skeleton", report.get("risk_type")))
    checks.append(check("risk_version_v1", report.get("risk_version") == "v1", report.get("risk_version")))
    checks.append(check("stage_g5_6", report.get("stage") == "G5.6", report.get("stage")))
    checks.append(check("exchange_bybit", report.get("exchange") == "bybit", report.get("exchange")))
    checks.append(check("risk_state_expected", report.get("risk_state") == "skeleton_defined_not_active", report.get("risk_state")))
    checks.append(check("risk_ready_false", report.get("risk_ready") is False, report.get("risk_ready")))
    checks.append(check("risk_can_evaluate_orders_false", report.get("risk_can_evaluate_orders") is False, report.get("risk_can_evaluate_orders")))

    checks.append(check("source_refs_present", isinstance(report.get("source_refs"), dict), type(report.get("source_refs")).__name__))
    checks.append(check("runtime_safety_context_present", isinstance(report.get("runtime_safety_context"), dict), type(report.get("runtime_safety_context")).__name__))
    checks.append(check("demo_gate_context_present", isinstance(report.get("demo_gate_context"), dict), type(report.get("demo_gate_context")).__name__))
    checks.append(check("adapter_context_present", isinstance(report.get("adapter_context"), dict), type(report.get("adapter_context")).__name__))
    checks.append(check("lifecycle_context_present", isinstance(report.get("lifecycle_context"), dict), type(report.get("lifecycle_context")).__name__))
    checks.append(check("projection_context_present", isinstance(report.get("projection_context"), dict), type(report.get("projection_context")).__name__))
    checks.append(check("risk_surface_present", isinstance(surface, dict), type(surface).__name__))
    checks.append(check("risk_surface_nonempty", isinstance(surface, dict) and len(surface) >= 6, len(surface) if isinstance(surface, dict) else None))
    checks.append(check("risk_summary_present", isinstance(report.get("risk_summary"), dict), type(report.get("risk_summary")).__name__))
    checks.append(check("risk_explainer_present", isinstance(report.get("risk_explainer"), dict), type(report.get("risk_explainer")).__name__))
    checks.append(check("operator_guidance_list", isinstance(report.get("operator_guidance"), list), type(report.get("operator_guidance")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_pretrade_risk_integration_skeleton_contract_check",
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

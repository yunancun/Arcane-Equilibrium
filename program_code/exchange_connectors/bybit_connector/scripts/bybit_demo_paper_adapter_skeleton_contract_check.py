#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_paper_adapter_skeleton_contract_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K1. paper execution adapter
- 这一层的白话解释:
  定义 paper/demo adapter 外壳，但当前仍不能接任何 paper order。

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
- 开发过程中曾临时标为 G5.3
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

CHECK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_paper_adapter_skeleton_latest.json")

OUT_DIR = CHECK_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_paper_adapter_skeleton_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_paper_adapter_skeleton_contract_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def main():
    report = load_json(CHECK_PATH)
    checks = []

    checks.append(check("adapter_exists", CHECK_PATH.exists(), str(CHECK_PATH)))
    checks.append(check("adapter_type_expected", report.get("adapter_type") == "bybit_demo_paper_adapter_skeleton", report.get("adapter_type")))
    checks.append(check("adapter_version_v1", report.get("adapter_version") == "v1", report.get("adapter_version")))
    checks.append(check("stage_g5_3", report.get("stage") == "G5.3", report.get("stage")))
    checks.append(check("exchange_bybit", report.get("exchange") == "bybit", report.get("exchange")))
    checks.append(check("adapter_state_expected", report.get("adapter_state") == "skeleton_defined_not_active", report.get("adapter_state")))
    checks.append(check("adapter_active_false", report.get("adapter_active") is False, report.get("adapter_active")))
    checks.append(check("adapter_ready_false", report.get("adapter_ready") is False, report.get("adapter_ready")))
    checks.append(check("adapter_can_accept_orders_false", report.get("adapter_can_accept_orders") is False, report.get("adapter_can_accept_orders")))

    checks.append(check("source_refs_present", isinstance(report.get("source_refs"), dict), type(report.get("source_refs")).__name__))
    checks.append(check("runtime_safety_context_present", isinstance(report.get("runtime_safety_context"), dict), type(report.get("runtime_safety_context")).__name__))
    checks.append(check("demo_gate_context_present", isinstance(report.get("demo_gate_context"), dict), type(report.get("demo_gate_context")).__name__))
    checks.append(check("missing_prerequisites_list", isinstance(report.get("missing_prerequisites"), list), type(report.get("missing_prerequisites")).__name__))
    checks.append(check("interface_surface_present", isinstance(report.get("interface_surface"), dict), type(report.get("interface_surface")).__name__))
    checks.append(check("adapter_summary_present", isinstance(report.get("adapter_summary"), dict), type(report.get("adapter_summary")).__name__))
    checks.append(check("adapter_explainer_present", isinstance(report.get("adapter_explainer"), dict), type(report.get("adapter_explainer")).__name__))
    checks.append(check("operator_guidance_list", isinstance(report.get("operator_guidance"), list), type(report.get("operator_guidance")).__name__))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "report_type": "bybit_demo_paper_adapter_skeleton_contract_check",
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

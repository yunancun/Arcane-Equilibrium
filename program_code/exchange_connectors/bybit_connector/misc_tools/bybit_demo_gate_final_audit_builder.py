#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_demo_gate_final_audit_builder.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / final audit
- 这一层的白话解释:
  对 K 章设计层做总审计，确认语义一致且主系统未被污染。

Role:
- 生成本脚本对应的 K 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 K. Paper / Demo Gate 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 K 章内定义/校验 final audit 层

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
import os

BASE = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/demo_gate")

CONTRACT_PATH = BASE / "bybit_demo_gate_contract_latest.json"
READINESS_PATH = BASE / "bybit_demo_gate_readiness_latest.json"
ADAPTER_PATH = BASE / "bybit_demo_paper_adapter_skeleton_latest.json"
LIFECYCLE_PATH = BASE / "bybit_paper_order_lifecycle_skeleton_latest.json"
PROJECTION_PATH = BASE / "bybit_paper_position_balance_projection_skeleton_latest.json"
RISK_PATH = BASE / "bybit_pretrade_risk_integration_skeleton_latest.json"
SUMMARY_PATH = BASE / "bybit_demo_gate_summary_latest.json"
HANDOFF_PATH = BASE / "bybit_demo_gate_handoff_latest.json"
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = BASE
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_demo_gate_final_audit_latest.json"


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def check(name, ok, detail):
    return {"name": name, "ok": bool(ok), "detail": detail}


def save_json(obj):
    ts_ms = obj["ts_ms"]
    dated = OUT_DIR / f"bybit_demo_gate_final_audit_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(OUT_LATEST), str(dated)


def main():
    contract = load_json(CONTRACT_PATH)
    readiness = load_json(READINESS_PATH)
    adapter = load_json(ADAPTER_PATH)
    lifecycle = load_json(LIFECYCLE_PATH)
    projection = load_json(PROJECTION_PATH)
    risk = load_json(RISK_PATH)
    summary = load_json(SUMMARY_PATH)
    handoff = load_json(HANDOFF_PATH)
    runtime = load_json(RUNTIME_PATH)

    checks = []

    checks.append(check("contract_exists", CONTRACT_PATH.exists(), str(CONTRACT_PATH)))
    checks.append(check("readiness_exists", READINESS_PATH.exists(), str(READINESS_PATH)))
    checks.append(check("adapter_exists", ADAPTER_PATH.exists(), str(ADAPTER_PATH)))
    checks.append(check("lifecycle_exists", LIFECYCLE_PATH.exists(), str(LIFECYCLE_PATH)))
    checks.append(check("projection_exists", PROJECTION_PATH.exists(), str(PROJECTION_PATH)))
    checks.append(check("risk_exists", RISK_PATH.exists(), str(RISK_PATH)))
    checks.append(check("summary_exists", SUMMARY_PATH.exists(), str(SUMMARY_PATH)))
    checks.append(check("handoff_exists", HANDOFF_PATH.exists(), str(HANDOFF_PATH)))
    checks.append(check("runtime_exists", RUNTIME_PATH.exists(), str(RUNTIME_PATH)))

    checks.append(check("contract_stage_g5_1", contract.get("stage") == "G5.1", contract.get("stage")))
    checks.append(check("readiness_stage_g5_2", readiness.get("stage") == "G5.2", readiness.get("stage")))
    checks.append(check("adapter_stage_g5_3", adapter.get("stage") == "G5.3", adapter.get("stage")))
    checks.append(check("lifecycle_stage_g5_4", lifecycle.get("stage") == "G5.4", lifecycle.get("stage")))
    checks.append(check("projection_stage_g5_5", projection.get("stage") == "G5.5", projection.get("stage")))
    checks.append(check("risk_stage_g5_6", risk.get("stage") == "G5.6", risk.get("stage")))
    checks.append(check("summary_stage_g5_7", summary.get("stage") == "G5.7", summary.get("stage")))
    checks.append(check("handoff_stage_g5_8", handoff.get("stage") == "G5.8", handoff.get("stage")))

    checks.append(check("contract_gate_closed", contract.get("gate_open") is False, contract.get("gate_open")))
    checks.append(check("readiness_not_ready", readiness.get("readiness_state") == "not_ready_missing_prerequisites", readiness.get("readiness_state")))
    checks.append(check("adapter_not_active", adapter.get("adapter_state") == "skeleton_defined_not_active", adapter.get("adapter_state")))
    checks.append(check("lifecycle_not_active", lifecycle.get("lifecycle_state") == "skeleton_defined_not_active", lifecycle.get("lifecycle_state")))
    checks.append(check("projection_not_active", projection.get("projection_state") == "skeleton_defined_not_active", projection.get("projection_state")))
    checks.append(check("risk_not_active", risk.get("risk_state") == "skeleton_defined_not_active", risk.get("risk_state")))

    checks.append(check(
        "summary_state_expected",
        summary.get("summary_state") == "design_layers_defined_gate_closed",
        summary.get("summary_state"),
    ))
    checks.append(check(
        "handoff_gate_can_open_false",
        handoff.get("current_status", {}).get("gate_can_open") is False,
        handoff.get("current_status", {}).get("gate_can_open"),
    ))
    checks.append(check(
        "handoff_operator_can_enable_false",
        handoff.get("current_status", {}).get("operator_can_enable") is False,
        handoff.get("current_status", {}).get("operator_can_enable"),
    ))

    checks.append(check("runtime_still_read_only", runtime.get("system_mode") == "read_only", runtime.get("system_mode")))
    checks.append(check("runtime_execution_disabled", runtime.get("execution_state") == "disabled", runtime.get("execution_state")))
    checks.append(check(
        "runtime_business_event_state_unchanged",
        runtime.get("business_event_state") == "healthy_no_business_events_yet",
        runtime.get("business_event_state"),
    ))

    missing_prereqs = summary.get("missing_prerequisites", [])
    handoff_missing_count = handoff.get("current_status", {}).get("missing_prerequisite_count")
    checks.append(check(
        "summary_missing_count_matches_handoff",
        len(missing_prereqs) == handoff_missing_count,
        {"summary": len(missing_prereqs), "handoff": handoff_missing_count},
    ))

    failed_checks = [c for c in checks if not c["ok"]]

    obj = {
        "audit_type": "bybit_demo_gate_final_audit",
        "audit_version": "v1",
        "ts_ms": int(time.time() * 1000),
        "overall_ok": len(failed_checks) == 0,
        "failed_count": len(failed_checks),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": failed_checks,
        "audit_summary": {
            "design_layers_defined": len(failed_checks) == 0,
            "gate_still_closed": contract.get("gate_open") is False and summary.get("gate_can_open") is False,
            "operator_still_locked": summary.get("operator_can_enable") is False,
            "runtime_still_readonly": runtime.get("system_mode") == "read_only",
            "execution_still_disabled": runtime.get("execution_state") == "disabled",
        },
        "audit_explainer": {
            "design_layer_passed_but_gate_closed": "G5 设计层已形成完整骨架并通过总审计，但 demo gate 仍关闭",
            "runtime_still_protected": "主系统仍保持 read_only / execution disabled，未被 demo gate 设计层污染",
        },
    }

    latest, dated = save_json(obj)
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    print(f"saved_latest={latest}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

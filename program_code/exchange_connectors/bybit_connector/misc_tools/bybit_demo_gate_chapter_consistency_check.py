#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_demo_gate_chapter_consistency_check.py

Formal chapter placement:
- 正式章节: K. Paper / Demo Gate
- 当前定位: K章总控层 / chapter consistency
- 这一层的白话解释:
  对 K 章当前 design/skeleton 产物做章节级一致性检查，
  确认 contract / readiness / adapter / lifecycle / projection / risk / summary / handoff / final audit 语义一致，
  且 gate 仍关闭、主系统仍未被污染。

Role:
- 汇总 K 章所有关键 latest 文件
- 做章节级 consistency check
- 输出 K 章 chapter consistency latest

Purpose in system:
- 给 K 章补齐章节级测试/审计层
- 为后续全量回归测试提供更稳定的统一检查点

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前仍只是 K design/skeleton consistency check
'''
"""

import json
import time
from pathlib import Path

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate")

PATHS = {
    "contract": BASE / "bybit_demo_gate_contract_latest.json",
    "contract_contract": BASE / "bybit_demo_gate_contract_contract_latest.json",
    "readiness": BASE / "bybit_demo_gate_readiness_latest.json",
    "readiness_contract": BASE / "bybit_demo_gate_readiness_contract_latest.json",
    "adapter": BASE / "bybit_demo_paper_adapter_skeleton_latest.json",
    "adapter_contract": BASE / "bybit_demo_paper_adapter_skeleton_contract_latest.json",
    "lifecycle": BASE / "bybit_paper_order_lifecycle_skeleton_latest.json",
    "lifecycle_contract": BASE / "bybit_paper_order_lifecycle_skeleton_contract_latest.json",
    "projection": BASE / "bybit_paper_position_balance_projection_skeleton_latest.json",
    "projection_contract": BASE / "bybit_paper_position_balance_projection_skeleton_contract_latest.json",
    "risk": BASE / "bybit_pretrade_risk_integration_skeleton_latest.json",
    "risk_contract": BASE / "bybit_pretrade_risk_integration_skeleton_contract_latest.json",
    "summary": BASE / "bybit_demo_gate_summary_latest.json",
    "summary_contract": BASE / "bybit_demo_gate_summary_contract_latest.json",
    "handoff": BASE / "bybit_demo_gate_handoff_latest.json",
    "handoff_contract": BASE / "bybit_demo_gate_handoff_contract_latest.json",
    "final_audit": BASE / "bybit_demo_gate_final_audit_latest.json",
    "final_audit_contract": BASE / "bybit_demo_gate_final_audit_contract_latest.json",
    "runtime": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"),
}

OUT_LATEST = BASE / "bybit_demo_gate_chapter_consistency_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def save(report):
    ts_ms = report["ts_ms"]
    dated = BASE / f"bybit_demo_gate_chapter_consistency_{ts_ms}.json"
    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    missing = []
    for key, path in PATHS.items():
        exists = path.exists()
        add_check(checks, f"{key}_exists", exists, str(path))
        if not exists:
            missing.append(key)

    if missing:
        report = {
            "report_type": "bybit_demo_gate_chapter_consistency_check",
            "report_version": "v1",
            "ts_ms": ts_ms,
            "overall_ok": False,
            "failed_count": sum(1 for x in checks if not x["ok"]),
            "checks": checks,
            "failed_checks": [x for x in checks if not x["ok"]],
            "reason": "required files missing",
            "missing_keys": missing,
        }
        dated = save(report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"saved_latest={OUT_LATEST}")
        print(f"saved_dated={dated}")
        return

    contract = load_json(PATHS["contract"])
    contract_contract = load_json(PATHS["contract_contract"])
    readiness = load_json(PATHS["readiness"])
    readiness_contract = load_json(PATHS["readiness_contract"])
    adapter = load_json(PATHS["adapter"])
    adapter_contract = load_json(PATHS["adapter_contract"])
    lifecycle = load_json(PATHS["lifecycle"])
    lifecycle_contract = load_json(PATHS["lifecycle_contract"])
    projection = load_json(PATHS["projection"])
    projection_contract = load_json(PATHS["projection_contract"])
    risk = load_json(PATHS["risk"])
    risk_contract = load_json(PATHS["risk_contract"])
    summary = load_json(PATHS["summary"])
    summary_contract = load_json(PATHS["summary_contract"])
    handoff = load_json(PATHS["handoff"])
    handoff_contract = load_json(PATHS["handoff_contract"])
    final_audit = load_json(PATHS["final_audit"])
    final_audit_contract = load_json(PATHS["final_audit_contract"])
    runtime = load_json(PATHS["runtime"])

    add_check(checks, "contract_contract_ok", contract_contract.get("overall_ok") is True, contract_contract.get("failed_count"))
    add_check(checks, "readiness_contract_ok", readiness_contract.get("overall_ok") is True, readiness_contract.get("failed_count"))
    add_check(checks, "adapter_contract_ok", adapter_contract.get("overall_ok") is True, adapter_contract.get("failed_count"))
    add_check(checks, "lifecycle_contract_ok", lifecycle_contract.get("overall_ok") is True, lifecycle_contract.get("failed_count"))
    add_check(checks, "projection_contract_ok", projection_contract.get("overall_ok") is True, projection_contract.get("failed_count"))
    add_check(checks, "risk_contract_ok", risk_contract.get("overall_ok") is True, risk_contract.get("failed_count"))
    add_check(checks, "summary_contract_ok", summary_contract.get("overall_ok") is True, summary_contract.get("failed_count"))
    add_check(checks, "handoff_contract_ok", handoff_contract.get("overall_ok") is True, handoff_contract.get("failed_count"))
    add_check(checks, "final_audit_contract_ok", final_audit_contract.get("overall_ok") is True, final_audit_contract.get("failed_count"))

    add_check(checks, "gate_contract_closed",
              contract.get("gate_state") == "closed_contract_defined" and contract.get("gate_open") is False,
              {"gate_state": contract.get("gate_state"), "gate_open": contract.get("gate_open")})
    add_check(checks, "readiness_not_ready_yet",
              readiness.get("readiness_state") == "not_ready_missing_prerequisites" and readiness.get("gate_can_open") is False and readiness.get("operator_can_enable") is False,
              {"readiness_state": readiness.get("readiness_state"), "gate_can_open": readiness.get("gate_can_open"), "operator_can_enable": readiness.get("operator_can_enable")})
    add_check(checks, "adapter_not_active",
              adapter.get("adapter_state") == "skeleton_defined_not_active" and adapter.get("adapter_can_accept_orders") is False,
              {"adapter_state": adapter.get("adapter_state"), "adapter_can_accept_orders": adapter.get("adapter_can_accept_orders")})
    add_check(checks, "lifecycle_not_ready",
              lifecycle.get("lifecycle_state") == "skeleton_defined_not_active" and lifecycle.get("lifecycle_can_accept_new_orders") is False,
              {"lifecycle_state": lifecycle.get("lifecycle_state"), "lifecycle_can_accept_new_orders": lifecycle.get("lifecycle_can_accept_new_orders")})
    add_check(checks, "projection_not_ready",
              projection.get("projection_state") == "skeleton_defined_not_active" and projection.get("projection_can_drive_paper_ledger") is False,
              {"projection_state": projection.get("projection_state"), "projection_can_drive_paper_ledger": projection.get("projection_can_drive_paper_ledger")})
    add_check(checks, "risk_not_ready",
              risk.get("risk_state") == "skeleton_defined_not_active" and risk.get("risk_can_evaluate_orders") is False,
              {"risk_state": risk.get("risk_state"), "risk_can_evaluate_orders": risk.get("risk_can_evaluate_orders")})

    add_check(checks, "summary_ok", summary.get("summary_ok") is True, summary.get("summary_state"))
    add_check(checks, "summary_gate_closed",
              summary.get("gate_can_open") is False and summary.get("operator_can_enable") is False,
              {"gate_can_open": summary.get("gate_can_open"), "operator_can_enable": summary.get("operator_can_enable")})
    add_check(checks, "handoff_gate_closed",
              handoff.get("current_status", {}).get("gate_can_open") is False and handoff.get("current_status", {}).get("operator_can_enable") is False,
              handoff.get("current_status", {}))
    add_check(checks, "final_audit_ok", final_audit.get("overall_ok") is True, final_audit.get("failed_count"))
    add_check(checks, "final_audit_gate_still_closed", final_audit.get("audit_summary", {}).get("gate_still_closed") is True, final_audit.get("audit_summary", {}))
    add_check(checks, "final_audit_runtime_protected",
              final_audit.get("audit_summary", {}).get("runtime_still_readonly") is True and final_audit.get("audit_summary", {}).get("execution_still_disabled") is True,
              final_audit.get("audit_summary", {}))

    add_check(checks, "runtime_still_read_only", runtime.get("system_mode") == "read_only", runtime.get("system_mode"))
    add_check(checks, "runtime_execution_disabled", runtime.get("execution_state") == "disabled", runtime.get("execution_state"))
    add_check(checks, "runtime_business_event_unchanged",
              runtime.get("business_event_state") == "healthy_no_business_events_yet" and runtime.get("business_event_healthy") is True,
              {"business_event_state": runtime.get("business_event_state"), "business_event_healthy": runtime.get("business_event_healthy")})

    overall_ok = all(x["ok"] for x in checks)

    report = {
        "report_type": "bybit_demo_gate_chapter_consistency_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "K.chapter",
        "overall_ok": overall_ok,
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
        "chapter_summary": {
            "contract_defined_and_closed": contract.get("gate_state") == "closed_contract_defined",
            "readiness_still_locked": readiness.get("readiness_state") == "not_ready_missing_prerequisites",
            "adapter_defined": adapter.get("adapter_state") == "skeleton_defined_not_active",
            "lifecycle_defined": lifecycle.get("lifecycle_state") == "skeleton_defined_not_active",
            "projection_defined": projection.get("projection_state") == "skeleton_defined_not_active",
            "risk_defined": risk.get("risk_state") == "skeleton_defined_not_active",
            "summary_ok": summary.get("summary_ok"),
            "handoff_present": handoff.get("current_status", {}).get("summary_ok"),
            "final_audit_ok": final_audit.get("overall_ok"),
            "runtime_still_protected": runtime.get("system_mode") == "read_only" and runtime.get("execution_state") == "disabled",
        },
    }

    dated = save(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

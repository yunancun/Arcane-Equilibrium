#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_revision2_master_regression_check.py

Formal placement:
- 这不是产品正式章节的一部分
- 这是 Revision 2 跨章节总回归工具
- 用于把 D / G / J / K 当前关键结果统一检查一遍

Plain explanation:
- D = Readonly Observer 主链
- G = 真实业务事件验证层
- J = Transition Engine Skeleton
- K = Paper / Demo Gate

This script checks:
- D 主链是否仍健康且只读
- G 是否已正式收口
- J 是否已通过章节级一致性
- K 是否已通过章节级一致性
- 主 runtime 是否始终未被污染

Not this:
- 不是 live execution
- 不是放开主系统权限
- 不是修改 runtime
- 只做跨章节回归检查
'''
"""

import json
import time
from pathlib import Path

PATHS = {
    "runtime": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"),
    "readonly_summary": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_readonly_final_summary_latest.json"),
    "readonly_audit": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_readonly_audit_latest.json"),
    "readonly_consistency": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/bybit_latest_consistency_latest.json"),

    "g_summary": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_regression_summary_latest.json"),
    "g_handoff": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_validation_handoff_latest.json"),
    "g_final_audit": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_final_audit_latest.json"),

    "j_consistency": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_chapter_consistency_latest.json"),
    "j_contract": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_chapter_consistency_contract_latest.json"),

    "k_consistency": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_chapter_consistency_latest.json"),
    "k_contract": Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/demo_gate/bybit_demo_gate_chapter_consistency_contract_latest.json"),
}

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/regression")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_revision2_master_regression_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def save(report):
    ts_ms = report["ts_ms"]
    dated = OUT_DIR / f"bybit_revision2_master_regression_{ts_ms}.json"
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
            "report_type": "bybit_revision2_master_regression_check",
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

    runtime = load_json(PATHS["runtime"])
    readonly_summary = load_json(PATHS["readonly_summary"])
    readonly_audit = load_json(PATHS["readonly_audit"])
    readonly_consistency = load_json(PATHS["readonly_consistency"])

    g_summary = load_json(PATHS["g_summary"])
    g_handoff = load_json(PATHS["g_handoff"])
    g_final_audit = load_json(PATHS["g_final_audit"])

    j_consistency = load_json(PATHS["j_consistency"])
    j_contract = load_json(PATHS["j_contract"])

    k_consistency = load_json(PATHS["k_consistency"])
    k_contract = load_json(PATHS["k_contract"])

    # D layer
    add_check(checks, "runtime_ready_readonly_observer",
              runtime.get("overall_runtime_state") == "ready_readonly_observer",
              runtime.get("overall_runtime_state"))
    add_check(checks, "runtime_system_mode_read_only",
              runtime.get("system_mode") == "read_only",
              runtime.get("system_mode"))
    add_check(checks, "runtime_execution_disabled",
              runtime.get("execution_state") == "disabled",
              runtime.get("execution_state"))
    add_check(checks, "runtime_business_event_empty_healthy",
              runtime.get("business_event_state") == "healthy_no_business_events_yet" and runtime.get("business_event_healthy") is True,
              {
                  "business_event_state": runtime.get("business_event_state"),
                  "business_event_healthy": runtime.get("business_event_healthy"),
              })

    add_check(checks, "readonly_summary_ready",
              readonly_summary.get("final_status", {}).get("readonly_observer_ready") is True,
              readonly_summary.get("final_status", {}))
    add_check(checks, "readonly_audit_ok",
              readonly_audit.get("overall_ok") is True,
              readonly_audit.get("failed_count"))
    add_check(checks, "readonly_consistency_ok",
              readonly_consistency.get("overall_ok") is True,
              readonly_consistency.get("failed_count"))

    # G layer
    add_check(checks, "g_summary_ok",
              g_summary.get("summary_ok") is True,
              g_summary.get("summary_state"))
    add_check(checks, "g_summary_ready_to_return_h_i",
              g_summary.get("summary_state") == "g_validation_complete_ready_for_h_i",
              g_summary.get("summary_state"))
    add_check(checks, "g_handoff_ok",
              g_handoff.get("handoff_ok") is True,
              g_handoff.get("handoff_state"))
    add_check(checks, "g_handoff_ready_to_return_h_i",
              g_handoff.get("handoff_state") == "g_validation_closed_ready_to_return_h_i",
              g_handoff.get("handoff_state"))
    add_check(checks, "g_final_audit_ok",
              g_final_audit.get("overall_ok") is True,
              g_final_audit.get("failed_count"))
    add_check(checks, "g_final_audit_closed",
              g_final_audit.get("audit_summary", {}).get("g_stage_closed") is True,
              g_final_audit.get("audit_summary", {}))
    add_check(checks, "g_strategy_note_preserved",
              g_summary.get("important_strategy_note", {}).get("h_i_should_not_be_skipped_for_formal_completion") is True,
              g_summary.get("important_strategy_note", {}))

    # J layer
    add_check(checks, "j_consistency_ok",
              j_consistency.get("overall_ok") is True,
              j_consistency.get("failed_count"))
    add_check(checks, "j_contract_ok",
              j_contract.get("overall_ok") is True,
              j_contract.get("failed_count"))
    add_check(checks, "j_summary_matrix_ok",
              j_consistency.get("chapter_summary", {}).get("matrix_ok") is True,
              j_consistency.get("chapter_summary", {}))
    add_check(checks, "j_summary_final_audit_ok",
              j_consistency.get("chapter_summary", {}).get("final_audit_ok") is True,
              j_consistency.get("chapter_summary", {}))
    add_check(checks, "j_runtime_still_protected",
              j_consistency.get("chapter_summary", {}).get("runtime_still_protected") is True,
              j_consistency.get("chapter_summary", {}))

    # K layer
    add_check(checks, "k_consistency_ok",
              k_consistency.get("overall_ok") is True,
              k_consistency.get("failed_count"))
    add_check(checks, "k_contract_ok",
              k_contract.get("overall_ok") is True,
              k_contract.get("failed_count"))
    add_check(checks, "k_summary_contract_defined_and_closed",
              k_consistency.get("chapter_summary", {}).get("contract_defined_and_closed") is True,
              k_consistency.get("chapter_summary", {}))
    add_check(checks, "k_summary_final_audit_ok",
              k_consistency.get("chapter_summary", {}).get("final_audit_ok") is True,
              k_consistency.get("chapter_summary", {}))
    add_check(checks, "k_runtime_still_protected",
              k_consistency.get("chapter_summary", {}).get("runtime_still_protected") is True,
              k_consistency.get("chapter_summary", {}))

    overall_ok = all(x["ok"] for x in checks)

    report = {
        "report_type": "bybit_revision2_master_regression_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": overall_ok,
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
        "regression_summary": {
            "d_readonly_chain_ok": all(
                x["ok"] for x in checks if x["name"] in [
                    "runtime_ready_readonly_observer",
                    "runtime_system_mode_read_only",
                    "runtime_execution_disabled",
                    "runtime_business_event_empty_healthy",
                    "readonly_summary_ready",
                    "readonly_audit_ok",
                    "readonly_consistency_ok",
                ]
            ),
            "g_stage_closed": all(
                x["ok"] for x in checks if x["name"].startswith("g_")
            ),
            "j_stage_structural_consistency_ok": all(
                x["ok"] for x in checks if x["name"].startswith("j_")
            ),
            "k_stage_structural_consistency_ok": all(
                x["ok"] for x in checks if x["name"].startswith("k_")
            ),
            "runtime_still_protected": (
                runtime.get("system_mode") == "read_only"
                and runtime.get("execution_state") == "disabled"
                and runtime.get("overall_runtime_state") == "ready_readonly_observer"
            ),
        },
        "next_step_hint": {
            "current_best_next_step": "write_march_19_supplement_record_then_return_to_H_I",
            "reason": "G 已正式收口，J/K 结构层检查通过；后续正式主线应回到 H/I，而不是把 J/K 误判为正式完工章节"
        }
    }

    dated = save(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

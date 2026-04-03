#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_final_audit.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G4.4 final audit
- 这一层的白话解释:
  对 G 章做最终总审计，确认 G1/G2/G3/G4 已形成完整验证闭环，
  且主 runtime 仍保持只读安全边界。

Role:
- 对 G 章本轮所有关键产物做最终总审计
- 输出 final audit latest

Purpose in system:
- 作为 G 章本轮“正式收口”依据
- 防止只看 summary/handoff 时漏掉底层链路问题
'''
"""

import json
import time
from pathlib import Path
import os

ROOTS = {
    "fixture_pack": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/fixtures/bybit_business_event_fixture_pack_latest.json"),
    "replay": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/replay/bybit_business_event_replay_latest.json"),
    "replay_contract": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/replay/bybit_business_event_replay_contract_latest.json"),
    "positive_state": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_state_latest.json"),
    "positive_phase": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_phase_latest.json"),
    "positive_input": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_input_latest.json"),
    "positive_decision": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_decision_latest.json"),
    "positive_outcome": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_outcome_latest.json"),
    "positive_consistency": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_consistency_latest.json"),
    "negative_fixture": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/fixtures_negative/bybit_business_event_negative_fixture_pack_latest.json"),
    "negative_replay": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/replay_negative/bybit_business_event_negative_replay_latest.json"),
    "negative_replay_contract": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/replay_negative/bybit_business_event_negative_replay_contract_latest.json"),
    "block_chain_contract": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test/bybit_event_replay_block_chain_contract_latest.json"),
    "acceptance": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_acceptance_suite_latest.json"),
    "acceptance_contract": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_acceptance_contract_latest.json"),
    "regression_summary": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_regression_summary_latest.json"),
    "regression_contract": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_regression_contract_latest.json"),
    "handoff": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_validation_handoff_latest.json"),
    "handoff_contract": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation/bybit_business_event_validation_handoff_contract_latest.json"),
    "runtime": Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json"),
}

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/validation")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_final_audit_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    missing = []
    for key, path in ROOTS.items():
        exists = path.exists()
        add_check(checks, f"{key}_exists", exists, str(path))
        if not exists:
            missing.append(key)

    if missing:
        report = {
            "audit_type": "bybit_business_event_final_audit",
            "audit_version": "v1",
            "ts_ms": ts_ms,
            "overall_ok": False,
            "failed_count": sum(1 for x in checks if not x["ok"]),
            "total_checks": len(checks),
            "checks": checks,
            "failed_checks": [x for x in checks if not x["ok"]],
            "reason": "required files missing",
            "missing_keys": missing,
        }
        OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        dated = OUT_DIR / f"bybit_business_event_final_audit_{ts_ms}.json"
        dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        print(f"saved_latest={OUT_LATEST}")
        print(f"saved_dated={dated}")
        return

    acceptance = load_json(ROOTS["acceptance"])
    acceptance_contract = load_json(ROOTS["acceptance_contract"])
    regression = load_json(ROOTS["regression_summary"])
    regression_contract = load_json(ROOTS["regression_contract"])
    handoff = load_json(ROOTS["handoff"])
    handoff_contract = load_json(ROOTS["handoff_contract"])
    runtime = load_json(ROOTS["runtime"])

    add_check(checks, "acceptance_overall_ok", acceptance.get("overall_ok") is True, acceptance.get("failed_count"))
    add_check(checks, "acceptance_contract_ok", acceptance_contract.get("overall_ok") is True, acceptance_contract.get("failed_count"))
    add_check(checks, "regression_summary_ok", regression.get("summary_ok") is True, regression.get("summary_state"))
    add_check(checks, "regression_contract_ok", regression_contract.get("overall_ok") is True, regression_contract.get("failed_count"))
    add_check(checks, "handoff_ok", handoff.get("handoff_ok") is True, handoff.get("handoff_state"))
    add_check(checks, "handoff_contract_ok", handoff_contract.get("overall_ok") is True, handoff_contract.get("failed_count"))

    add_check(
        checks,
        "positive_nonempty_path_verified",
        acceptance.get("summary", {}).get("positive_nonempty_path_verified") is True,
        acceptance.get("summary", {}).get("positive_nonempty_path_verified"),
    )
    add_check(
        checks,
        "negative_blocked_path_verified",
        acceptance.get("summary", {}).get("negative_blocked_path_verified") is True,
        acceptance.get("summary", {}).get("negative_blocked_path_verified"),
    )
    add_check(
        checks,
        "runtime_protection_preserved",
        acceptance.get("summary", {}).get("runtime_protection_preserved") is True,
        acceptance.get("summary", {}).get("runtime_protection_preserved"),
    )

    add_check(checks, "runtime_still_read_only", runtime.get("system_mode") == "read_only", runtime.get("system_mode"))
    add_check(checks, "runtime_execution_disabled", runtime.get("execution_state") == "disabled", runtime.get("execution_state"))
    add_check(checks, "runtime_state_ready_observer", runtime.get("overall_runtime_state") == "ready_readonly_observer", runtime.get("overall_runtime_state"))
    add_check(
        checks,
        "runtime_business_event_empty_healthy",
        runtime.get("business_event_state") == "healthy_no_business_events_yet" and runtime.get("business_event_healthy") is True,
        {"business_event_state": runtime.get("business_event_state"), "business_event_healthy": runtime.get("business_event_healthy")},
    )

    add_check(
        checks,
        "strategy_note_preserved",
        regression.get("important_strategy_note", {}).get("h_i_should_not_be_skipped_for_formal_completion") is True,
        regression.get("important_strategy_note", {}),
    )

    overall_ok = all(x["ok"] for x in checks)

    report = {
        "audit_type": "bybit_business_event_final_audit",
        "audit_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": overall_ok,
        "failed_count": sum(1 for x in checks if not x["ok"]),
        "total_checks": len(checks),
        "checks": checks,
        "failed_checks": [x for x in checks if not x["ok"]],
        "audit_summary": {
            "g_stage_closed": overall_ok,
            "positive_nonempty_path_verified": acceptance.get("summary", {}).get("positive_nonempty_path_verified"),
            "negative_blocked_path_verified": acceptance.get("summary", {}).get("negative_blocked_path_verified"),
            "runtime_still_protected": acceptance.get("summary", {}).get("runtime_protection_preserved"),
            "ready_to_return_h_i": regression.get("summary_state") == "g_validation_complete_ready_for_h_i",
        },
        "audit_explainer": {
            "g_stage_closed": "G 章验证层已形成完整收口，后续正式主线应回到 H/I",
            "runtime_still_protected": "主系统仍保持 read_only / execution disabled，未被 G 章验证输出污染"
        }
    }

    OUT_LATEST.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_final_audit_{ts_ms}.json"
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

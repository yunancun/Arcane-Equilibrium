#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_audit_trail_builder.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J3. transition audit trail
- 这一层的白话解释:
  定义 transition audit trail，记录正向 candidate 和负向阻断路径在隔离验证中的审计结果。

Role:
- 生成本脚本对应的 J 章骨架 / 汇总 / 审计输出。

Purpose in system:
- 把 J. Transition Engine Skeleton 的对应子层固定下来，方便后续继续施工，同时不触碰 live execution。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 transition audit trail
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.2
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

MATRIX_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_replay_matrix_latest.json")
RUNTIME_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/bybit_runtime_state_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_transition_engine_audit_trail_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_audit_trail_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def build_entry(case_name: str, path_obj: dict):
    candidate_state = path_obj.get("transition_candidate_state")
    candidate_available = path_obj.get("candidate_available")
    execution_still_forbidden = path_obj.get("execution_still_forbidden")

    if candidate_state == "candidate_transition_open":
        audit_verdict = "candidate_open_but_execution_forbidden"
    elif candidate_state == "candidate_transition_blocked":
        audit_verdict = "candidate_blocked"
    else:
        audit_verdict = "candidate_unknown"

    return {
        "case_name": case_name,
        "source_decision_ts_ms": path_obj.get("source_decision_ts_ms"),
        "source_outcome_ts_ms": path_obj.get("source_outcome_ts_ms"),
        "transition_candidate_state": candidate_state,
        "candidate_available": candidate_available,
        "execution_still_forbidden": execution_still_forbidden,
        "audit_verdict": audit_verdict,
        "reason": path_obj.get("reason"),
    }


def main():
    now_ms = int(time.time() * 1000)

    matrix = load_json(MATRIX_PATH)
    runtime = load_json(RUNTIME_PATH)

    positive = matrix.get("positive_replay_path", {})
    negative = matrix.get("negative_replay_path", {})
    matrix_verdict = matrix.get("matrix_verdict", {})

    audit_entries = [
        build_entry("positive_replay_path", positive),
        build_entry("negative_replay_path", negative),
    ]

    execution_forbidden_confirmed = (
        runtime.get("system_mode") == "read_only"
        and runtime.get("execution_state") == "disabled"
    )

    report = {
        "audit_type": "bybit_transition_engine_audit_trail",
        "audit_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G4.2",
        "skeleton_context": {
            "source_matrix_version": matrix.get("report_version"),
            "source_matrix_ts_ms": matrix.get("ts_ms"),
            "matrix_ok": matrix_verdict.get("matrix_ok"),
        },
        "runtime_safety_snapshot": {
            "system_mode": runtime.get("system_mode"),
            "overall_runtime_state": runtime.get("overall_runtime_state"),
            "execution_state": runtime.get("execution_state"),
            "ai_state": runtime.get("ai_state"),
            "business_event_state": runtime.get("business_event_state"),
            "business_event_healthy": runtime.get("business_event_healthy"),
            "execution_forbidden_confirmed": execution_forbidden_confirmed,
        },
        "audit_entries": audit_entries,
        "trail_summary": {
            "entry_count": len(audit_entries),
            "positive_case_verdict": audit_entries[0]["audit_verdict"],
            "negative_case_verdict": audit_entries[1]["audit_verdict"],
            "positive_case_open": matrix_verdict.get("positive_path_open"),
            "negative_case_blocked": matrix_verdict.get("negative_path_blocked"),
            "execution_forbidden_confirmed": execution_forbidden_confirmed,
            "trail_ok": bool(
                len(audit_entries) == 2
                and matrix_verdict.get("positive_path_open") is True
                and matrix_verdict.get("negative_path_blocked") is True
                and execution_forbidden_confirmed
            ),
        },
        "audit_explainer": {
            "candidate_open_but_execution_forbidden": "正向 replay 在 skeleton 中被识别为可进入下一层候选，但当前仍绝不允许 execution",
            "candidate_blocked": "负向 replay 被明确识别为阻断路径",
            "trail_ok": "说明 skeleton 判定结果已经被稳定记录，可用于后续 transition rule layer"
        }
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

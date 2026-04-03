#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_replay_matrix_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J4. transition replay
- 这一层的白话解释:
  把正向 replay 路径和负向 replay 路径做成统一矩阵，用来证明 transition skeleton 的语义成立。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 J 章脚本在后续维护时发生结构漂移，给 summary / handoff / final audit / checkpoint 提供稳定上游。

Not this:
- 不是 live execution
- 不是主 runtime 放权
- 当前不会放开真实下单
- 当前只是在 J 章内定义/校验 contract check 层
- 当前仍只是 skeleton，不是完整 transition engine

Historical note:
- 开发过程中曾临时标为 G4.1
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
OUT_DIR = MATRIX_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_replay_matrix_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_replay_matrix_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(MATRIX_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("matrix_exists", obj is not None, str(MATRIX_PATH))

    if obj is not None:
        add("report_type_expected", obj.get("report_type") == "bybit_transition_engine_replay_matrix", obj.get("report_type"))
        add("report_version_v1", obj.get("report_version") == "v1", obj.get("report_version"))
        add("stage_g4_1", obj.get("stage") == "G4.1", obj.get("stage"))
        add("engine_mode_skeleton", obj.get("engine_mode") == "simulation_only_skeleton", obj.get("engine_mode"))

        safety = obj.get("safety_boundaries", {})
        add("execution_allowed_false", safety.get("execution_allowed") is False, safety)
        add("readonly_required_true", safety.get("readonly_required") is True, safety)
        add("readonly_context_ok_true", safety.get("readonly_context_ok") is True, safety)

        pos = obj.get("positive_replay_path", {})
        add("positive_candidate_open", pos.get("transition_candidate_state") == "candidate_transition_open", pos)
        add("positive_candidate_available_true", pos.get("candidate_available") is True, pos)

        neg = obj.get("negative_replay_path", {})
        add("negative_candidate_blocked", neg.get("transition_candidate_state") == "candidate_transition_blocked", neg)
        add("negative_candidate_available_false", neg.get("candidate_available") is False, neg)

        verdict = obj.get("matrix_verdict", {})
        add("matrix_positive_open_true", verdict.get("positive_path_open") is True, verdict)
        add("matrix_negative_blocked_true", verdict.get("negative_path_blocked") is True, verdict)
        add("matrix_ok_true", verdict.get("matrix_ok") is True, verdict)

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_transition_engine_replay_matrix_contract_check",
        "report_version": "v1",
        "ts_ms": now_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

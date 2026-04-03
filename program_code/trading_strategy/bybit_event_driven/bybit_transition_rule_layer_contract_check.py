#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_rule_layer_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J1. transition rules
- 这一层的白话解释:
  定义 transition rule layer 骨架，用来统一表达哪些 candidate path 在隔离验证里可开、哪些必须阻断。

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
- 开发过程中曾临时标为 G4.3
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

LAYER_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_rule_layer_latest.json")

OUT_DIR = LAYER_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_rule_layer_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_rule_layer_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(LAYER_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("layer_exists", obj is not None, str(LAYER_PATH))

    if obj is not None:
        add("layer_type_expected", obj.get("layer_type") == "bybit_transition_rule_layer", obj.get("layer_type"))
        add("layer_version_v1", obj.get("layer_version") == "v1", obj.get("layer_version"))
        add("stage_g4_3", obj.get("stage") == "G4.3", obj.get("stage"))
        add("rule_layer_state_ready", obj.get("rule_layer_state") == "skeleton_rules_ready", obj.get("rule_layer_state"))
        add("candidate_transition_supported_true", obj.get("candidate_transition_supported") is True, obj.get("candidate_transition_supported"))
        add("negative_blocking_supported_true", obj.get("negative_blocking_supported") is True, obj.get("negative_blocking_supported"))
        add("execution_permitted_false", obj.get("execution_permitted") is False, obj.get("execution_permitted"))
        add("demo_gate_open_false", obj.get("demo_gate_open") is False, obj.get("demo_gate_open"))
        add("live_execution_open_false", obj.get("live_execution_open") is False, obj.get("live_execution_open"))

        summary = obj.get("layer_summary", {})
        add("skeleton_rules_ready_true", summary.get("skeleton_rules_ready") is True, summary)
        add("failed_rule_count_zero", summary.get("failed_rule_count") == 0, summary)

        rule_results = obj.get("rule_results", [])
        add("rule_results_nonempty", isinstance(rule_results, list) and len(rule_results) >= 5, len(rule_results) if isinstance(rule_results, list) else type(rule_results).__name__)

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_transition_rule_layer_contract_check",
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

#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_transition_decision_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G2. 非空业务事件语义验证 / decision
- 这一层的白话解释:
  验证正向 replay 会把决策推进到 allow_transition_engine，但仍只发生在隔离验证上下文。

Role:
- 校验本脚本对应输出文件的结构、版本与基础字段是否稳定。

Purpose in system:
- 防止 G 章验证输出在后续维护时发生结构漂移，给 regression / consistency / handoff 提供稳定依据。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 contract check 层
- 所有 replay / negative / consistency 输出都应与主 runtime 隔离

Maintenance notes:
- 本批修正主要增强白话说明，不改变 G 章归属
- 本批修正不改文件名、latest 路径、JSON stage 字段
- 如后续要把 replay 结果真正接到更高层，必须显式经过 J / K 章节边界
\'\'\'
"""
import json
import time
from pathlib import Path
import os

DECISION_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/event_driven/replay_test/bybit_event_replay_transition_decision_latest.json")

OUT_DIR = DECISION_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_event_replay_transition_decision_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_event_replay_transition_decision_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(DECISION_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("decision_exists", obj is not None, str(DECISION_PATH))

    if obj is not None:
        add("decision_type_expected", obj.get("decision_type") == "bybit_event_replay_transition_decision", obj.get("decision_type"))
        add("decision_version_v1", obj.get("decision_version") == "v1", obj.get("decision_version"))
        add("exchange_bybit", obj.get("exchange") == "bybit", obj.get("exchange"))
        add("stage_g2_4", obj.get("stage") == "G2.4", obj.get("stage"))

        allowed_codes = {
            "keep_observe_only",
            "allow_transition_engine",
            "block_transition_engine",
        }
        decision_code = obj.get("decision_code")
        add("decision_code_allowed", decision_code in allowed_codes, decision_code)
        add("decision_allowed_bool", isinstance(obj.get("decision_allowed"), bool), obj.get("decision_allowed"))
        add("decision_reason_present", bool(obj.get("decision_reason")), obj.get("decision_reason"))
        add("source_input_ref_present", isinstance(obj.get("source_input_ref"), dict), obj.get("source_input_ref"))
        add("transition_context_present", isinstance(obj.get("transition_context"), dict), obj.get("transition_context"))

        if decision_code == "allow_transition_engine":
            add("allow_transition_engine_consistent", obj.get("decision_allowed") is True, obj.get("decision_allowed"))
        elif decision_code in {"keep_observe_only", "block_transition_engine"}:
            add("non_allow_decision_consistent", obj.get("decision_allowed") is False, obj.get("decision_allowed"))

    failed = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_event_replay_transition_decision_contract_check",
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

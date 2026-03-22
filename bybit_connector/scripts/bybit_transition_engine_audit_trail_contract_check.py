#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_transition_engine_audit_trail_contract_check.py

Formal chapter placement:
- 正式章节: J. Transition Engine Skeleton
- 当前定位: J3. transition audit trail
- 这一层的白话解释:
  定义 transition audit trail，记录正向 candidate 和负向阻断路径在隔离验证中的审计结果。

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

AUDIT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/transition_engine/bybit_transition_engine_audit_trail_latest.json")
OUT_DIR = AUDIT_PATH.parent
OUT_LATEST = OUT_DIR / "bybit_transition_engine_audit_trail_contract_latest.json"


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_transition_engine_audit_trail_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    obj = load_json(AUDIT_PATH)

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add("audit_exists", obj is not None, str(AUDIT_PATH))

    if obj is not None:
        add("audit_type_expected", obj.get("audit_type") == "bybit_transition_engine_audit_trail", obj.get("audit_type"))
        add("audit_version_v1", obj.get("audit_version") == "v1", obj.get("audit_version"))
        add("stage_g4_2", obj.get("stage") == "G4.2", obj.get("stage"))

        snapshot = obj.get("runtime_safety_snapshot", {})
        add("system_mode_read_only", snapshot.get("system_mode") == "read_only", snapshot)
        add("execution_state_disabled", snapshot.get("execution_state") == "disabled", snapshot)
        add("execution_forbidden_confirmed_true", snapshot.get("execution_forbidden_confirmed") is True, snapshot)

        entries = obj.get("audit_entries", [])
        add("audit_entries_len_2", isinstance(entries, list) and len(entries) == 2, len(entries) if isinstance(entries, list) else type(entries).__name__)

        if isinstance(entries, list) and len(entries) == 2:
            pos = entries[0]
            neg = entries[1]
            add("positive_case_open_but_forbidden", pos.get("audit_verdict") == "candidate_open_but_execution_forbidden", pos)
            add("negative_case_blocked", neg.get("audit_verdict") == "candidate_blocked", neg)

        summary = obj.get("trail_summary", {})
        add("positive_case_open_true", summary.get("positive_case_open") is True, summary)
        add("negative_case_blocked_true", summary.get("negative_case_blocked") is True, summary)
        add("trail_ok_true", summary.get("trail_ok") is True, summary)

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_transition_engine_audit_trail_contract_check",
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

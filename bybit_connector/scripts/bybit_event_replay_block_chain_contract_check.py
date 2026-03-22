#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_event_replay_block_chain_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G3/G4. 负向阻断链 + regression check
- 这一层的白话解释:
  把负向 replay 的 blocked path 串起来，证明 input / decision / outcome 会一致地保持阻断。

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

BASE = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/event_driven/replay_block_test")
OUT_LATEST = BASE / "bybit_event_replay_block_chain_contract_latest.json"

PATHS = {
    "state": BASE / "bybit_event_replay_block_state_latest.json",
    "phase": BASE / "bybit_event_replay_block_phase_latest.json",
    "input": BASE / "bybit_event_replay_block_transition_input_latest.json",
    "decision": BASE / "bybit_event_replay_block_transition_decision_latest.json",
    "outcome": BASE / "bybit_event_replay_block_transition_outcome_latest.json",
    "consistency": BASE / "bybit_event_replay_block_transition_consistency_latest.json",
}


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = BASE / f"bybit_event_replay_block_chain_contract_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    objs = {k: load_json(v) for k, v in PATHS.items()}

    checks = []

    def add(name, ok, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    for k, p in PATHS.items():
        add(f"{k}_exists", objs[k] is not None, str(p))

    if all(objs.values()):
        add("state_not_ready", objs["state"].get("event_driven_readiness") == "not_ready", objs["state"].get("event_driven_readiness"))
        add("phase_blocked", objs["phase"].get("phase_code") == "observer_feed_not_ready" and objs["phase"].get("phase_ready") is False, {"phase_code": objs["phase"].get("phase_code"), "phase_ready": objs["phase"].get("phase_ready")})
        add("input_blocked", objs["input"].get("transition_readiness") == "input_not_ready" and objs["input"].get("transition_allowed") is False, {"transition_readiness": objs["input"].get("transition_readiness"), "transition_allowed": objs["input"].get("transition_allowed")})
        add("decision_blocked", objs["decision"].get("decision_code") == "block_transition_engine" and objs["decision"].get("decision_allowed") is False, {"decision_code": objs["decision"].get("decision_code"), "decision_allowed": objs["decision"].get("decision_allowed")})
        add("outcome_blocked", objs["outcome"].get("outcome_code") == "transition_engine_blocked" and objs["outcome"].get("outcome_ok") is True, {"outcome_code": objs["outcome"].get("outcome_code"), "outcome_ok": objs["outcome"].get("outcome_ok")})
        add("consistency_ok", objs["consistency"].get("overall_ok") is True, objs["consistency"].get("overall_ok"))

    failed = [c for c in checks if not c["ok"]]
    report = {
        "report_type": "bybit_event_replay_block_chain_contract_check",
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

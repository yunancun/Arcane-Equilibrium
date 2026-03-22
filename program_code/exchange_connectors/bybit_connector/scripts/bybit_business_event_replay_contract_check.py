#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_replay_contract_check.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G1. replay harness
- 这一层的白话解释:
  把 fixture pack 重放成标准化业务事件，用来验证 event ingest / normalize 语义。

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

REPLAY_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay/bybit_business_event_replay_latest.json")

OUT_DIR = REPLAY_PATH.parent
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_replay_contract_latest.json"

REQUIRED_TOPICS = {"wallet", "order", "execution", "position"}
REQUIRED_EVENT_TYPES = {
    "bybit_private_wallet_event",
    "bybit_private_order_event",
    "bybit_private_execution_event",
    "bybit_private_position_event",
}


def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def main():
    ts_ms = int(time.time() * 1000)
    replay = load_json(REPLAY_PATH)

    checks = []

    def add_check(name: str, ok: bool, detail):
        checks.append({"name": name, "ok": ok, "detail": detail})

    add_check("replay_exists", replay is not None, str(REPLAY_PATH))

    if replay is not None:
        add_check("report_type_expected", replay.get("report_type") == "bybit_business_event_replay_harness", replay.get("report_type"))
        add_check("report_version_v1", replay.get("report_version") == "v1", replay.get("report_version"))
        add_check("exchange_bybit", replay.get("exchange") == "bybit", replay.get("exchange"))
        add_check("stage_g1_1", replay.get("stage") == "G1.1", replay.get("stage"))

        normalized_count = int(replay.get("normalized_count", 0))
        replayed_count = int(replay.get("replayed_count", 0))
        add_check("normalized_count_eq_replayed_count", normalized_count == replayed_count, {"normalized": normalized_count, "replayed": replayed_count})
        add_check("normalized_count_ge_4", normalized_count >= 4, normalized_count)
        add_check("has_business_events_true", replay.get("has_business_events") is True, replay.get("has_business_events"))

        topic_counts = replay.get("topic_counts") or {}
        event_type_counts = replay.get("event_type_counts") or {}
        add_check("required_topics_present", REQUIRED_TOPICS.issubset(set(topic_counts.keys())), topic_counts)
        add_check("required_event_types_present", REQUIRED_EVENT_TYPES.issubset(set(event_type_counts.keys())), event_type_counts)

        events = replay.get("events") or []
        fingerprints = [e.get("event_fingerprint", "") for e in events]
        add_check("fingerprints_unique", len(fingerprints) == len(set(fingerprints)) and all(fingerprints), {"count": len(fingerprints), "unique": len(set(fingerprints))})

        all_schema_v1 = all(e.get("event_schema_version") == "v1" for e in events)
        add_check("all_event_schema_v1", all_schema_v1, all_schema_v1)

    overall_ok = all(c["ok"] for c in checks)
    failed_checks = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_business_event_replay_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": overall_ok,
        "failed_count": len(failed_checks),
        "checks": checks,
        "failed_checks": failed_checks,
    }

    dated = save_report(report, OUT_LATEST, "bybit_business_event_replay_contract")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

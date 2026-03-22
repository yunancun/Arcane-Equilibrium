#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_negative_replay_harness.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G3. 负向阻断验证 / negative replay
- 这一层的白话解释:
  把不完整负向样本重放成业务事件，验证缺失 topic 时仍应保持阻断。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 negative replay
- 所有 replay / negative / consistency 输出都应与主 runtime 隔离

Maintenance notes:
- 本批修正主要增强白话说明，不改变 G 章归属
- 本批修正不改文件名、latest 路径、JSON stage 字段
- 如后续要把 replay 结果真正接到更高层，必须显式经过 J / K 章节边界
\'\'\'
"""
import hashlib
import json
import time
from pathlib import Path

PACK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/fixtures_negative/bybit_business_event_negative_fixture_pack_latest.json")
OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay_negative")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_negative_replay_latest.json"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha1_obj(obj) -> str:
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def normalize_wallet(msg, item, ingest_ts_ms, seq):
    event_ts_ms = item.get("updatedTime") or msg.get("ts")
    raw = {
        "coin": item.get("coin", ""),
        "walletBalance": item.get("walletBalance", ""),
        "equity": item.get("equity", ""),
        "availableToWithdraw": item.get("availableToWithdraw", ""),
        "updatedTime": item.get("updatedTime"),
    }
    event = {
        "event_schema_version": "v1",
        "exchange": "bybit",
        "ingestion_stage": "G3.1_replay_negative",
        "event_type": "bybit_private_wallet_event",
        "topic": "wallet",
        "topic_root": "wallet",
        "symbol": item.get("coin", ""),
        "event_ts_ms": event_ts_ms,
        "ingest_ts_ms": ingest_ts_ms,
        "source_conn_id": "fixture-negative-wallet",
        "source_message_ts_ms": msg.get("ts"),
        "source_sequence_hint": seq,
        "normalized_payload": {
            "symbol": item.get("coin", ""),
            "side": "",
            "order_id": "",
            "exec_id": "",
            "coin": item.get("coin", ""),
            "wallet_balance": item.get("walletBalance", ""),
            "equity": item.get("equity", ""),
            "available_to_withdraw": item.get("availableToWithdraw", ""),
        },
        "raw_payload": raw,
    }
    event["event_fingerprint"] = sha1_obj(event)
    return event


def save_json(obj: dict):
    OUT_LATEST.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated = OUT_DIR / f"bybit_business_event_negative_replay_{obj['ts_ms']}.json"
    dated.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated


def main():
    now_ms = int(time.time() * 1000)
    pack = load_json(PACK_PATH)
    fixtures = pack.get("fixtures") or []

    events = []
    for fx in fixtures:
        msg = fx.get("source_message") or {}
        data = msg.get("data") or []
        for item in data:
            if fx.get("topic") == "wallet":
                events.append(normalize_wallet(msg, item, now_ms, fx.get("source_sequence_hint", 0)))

    topic_counts = {}
    event_type_counts = {}
    for ev in events:
        topic_counts[ev["topic"]] = topic_counts.get(ev["topic"], 0) + 1
        event_type_counts[ev["event_type"]] = event_type_counts.get(ev["event_type"], 0) + 1

    report = {
        "report_type": "bybit_business_event_negative_replay_harness",
        "report_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G3.1",
        "source_fixture_pack_path": str(PACK_PATH),
        "source_fixture_pack_ts_ms": pack.get("ts_ms"),
        "fixture_count": len(fixtures),
        "replayed_count": len(events),
        "normalized_count": len(events),
        "has_business_events": len(events) > 0,
        "topic_counts": topic_counts,
        "event_type_counts": event_type_counts,
        "events": events,
    }

    dated = save_json(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

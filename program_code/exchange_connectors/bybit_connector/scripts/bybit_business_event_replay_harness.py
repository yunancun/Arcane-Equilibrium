#!/usr/bin/env python3
"""
MODULE_NOTE = \'\'\'
[Maintainer Note]
Script: bybit_business_event_replay_harness.py

Formal chapter placement:
- 正式章节: G. 真实业务事件验证层
- 当前定位: G1. replay harness
- 这一层的白话解释:
  把 fixture pack 重放成标准化业务事件，用来验证 event ingest / normalize 语义。

Role:
- 生成本脚本对应的 G 章验证输出。

Purpose in system:
- 把 G. 真实业务事件验证层的对应子层固定下来，证明真实业务事件相关语义是否成立，同时不污染主 runtime。

Not this:
- 不是 J. Transition Engine Skeleton 本体
- 不是 K. Paper / Demo Gate
- 不是主 runtime 放权
- 当前只是在 G 章内定义/校验 replay harness
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

PACK_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/fixtures/bybit_business_event_fixture_pack_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/replay")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LATEST = OUT_DIR / "bybit_business_event_replay_latest.json"

EVENT_TYPE_MAP = {
    "wallet": "bybit_private_wallet_event",
    "order": "bybit_private_order_event",
    "execution": "bybit_private_execution_event",
    "position": "bybit_private_position_event",
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save_report(obj: dict, latest_path: Path, dated_prefix: str) -> Path:
    latest_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path = latest_path.parent / f"{dated_prefix}_{obj['ts_ms']}.json"
    dated_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    return dated_path


def build_normalized_payload(topic: str, raw: dict) -> dict:
    if topic == "wallet":
        coin = raw.get("coin", "")
        return {
            "symbol": coin,
            "side": "",
            "order_id": "",
            "exec_id": "",
            "coin": coin,
            "wallet_balance": raw.get("walletBalance", ""),
            "equity": raw.get("equity", ""),
            "available_to_withdraw": raw.get("availableToWithdraw", ""),
        }

    if topic == "order":
        return {
            "symbol": raw.get("symbol", ""),
            "side": raw.get("side", ""),
            "order_id": raw.get("orderId", ""),
            "exec_id": "",
            "order_link_id": raw.get("orderLinkId", ""),
            "order_status": raw.get("orderStatus", ""),
            "qty": raw.get("qty", ""),
            "price": raw.get("price", ""),
        }

    if topic == "execution":
        return {
            "symbol": raw.get("symbol", ""),
            "side": raw.get("side", ""),
            "order_id": raw.get("orderId", ""),
            "exec_id": raw.get("execId", ""),
            "exec_qty": raw.get("execQty", ""),
            "exec_price": raw.get("execPrice", ""),
        }

    if topic == "position":
        return {
            "symbol": raw.get("symbol", ""),
            "side": raw.get("side", ""),
            "order_id": "",
            "exec_id": "",
            "size": raw.get("size", ""),
            "entry_price": raw.get("entryPrice", ""),
            "position_value": raw.get("positionValue", ""),
        }

    return {
        "symbol": "",
        "side": "",
        "order_id": "",
        "exec_id": "",
    }


def extract_event_ts_ms(topic: str, raw: dict, source_message: dict) -> int:
    if topic == "wallet":
        return int(raw.get("updatedTime") or source_message.get("ts") or 0)
    if topic == "order":
        return int(raw.get("updatedTime") or raw.get("createdTime") or source_message.get("ts") or 0)
    if topic == "execution":
        return int(raw.get("execTime") or source_message.get("ts") or 0)
    if topic == "position":
        return int(raw.get("updatedTime") or source_message.get("ts") or 0)
    return int(source_message.get("ts") or 0)


def fingerprint_for(topic: str, event_ts_ms: int, raw_payload: dict, source_conn_id: str, source_sequence_hint: int) -> str:
    base = {
        "topic": topic,
        "event_ts_ms": event_ts_ms,
        "raw_payload": raw_payload,
        "source_conn_id": source_conn_id,
        "source_sequence_hint": source_sequence_hint,
    }
    return hashlib.sha1(json.dumps(base, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def main():
    now_ms = int(time.time() * 1000)
    pack = load_json(PACK_PATH)

    fixtures = pack.get("fixtures") or []
    events = []

    for fixture in fixtures:
        topic = fixture.get("topic", "")
        source_message = fixture.get("source_message") or {}
        source_conn_id = fixture.get("source_conn_id", "fixture-conn")
        base_seq = int(fixture.get("source_sequence_hint", 0))

        for idx, raw in enumerate(source_message.get("data") or []):
            event_ts_ms = extract_event_ts_ms(topic, raw, source_message)
            normalized_payload = build_normalized_payload(topic, raw)

            event = {
                "event_schema_version": "v1",
                "exchange": "bybit",
                "ingestion_stage": "G1.1_replay",
                "event_type": EVENT_TYPE_MAP.get(topic, "unknown"),
                "topic": topic,
                "topic_root": topic.split(".")[0] if topic else "",
                "symbol": normalized_payload.get("symbol", ""),
                "event_ts_ms": event_ts_ms,
                "ingest_ts_ms": now_ms + idx,
                "source_conn_id": source_conn_id,
                "source_message_ts_ms": int(source_message.get("ts") or event_ts_ms),
                "source_sequence_hint": base_seq + idx,
                "normalized_payload": normalized_payload,
                "raw_payload": raw,
            }
            event["event_fingerprint"] = fingerprint_for(
                topic=topic,
                event_ts_ms=event["event_ts_ms"],
                raw_payload=raw,
                source_conn_id=event["source_conn_id"],
                source_sequence_hint=event["source_sequence_hint"],
            )
            events.append(event)

    topic_counts = {}
    event_type_counts = {}
    for event in events:
        topic = event.get("topic", "")
        event_type = event.get("event_type", "")
        topic_counts[topic] = topic_counts.get(topic, 0) + 1
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

    report = {
        "report_type": "bybit_business_event_replay_harness",
        "report_version": "v1",
        "ts_ms": now_ms,
        "exchange": "bybit",
        "stage": "G1.1",
        "source_fixture_pack_path": str(PACK_PATH),
        "source_fixture_pack_ts_ms": pack.get("ts_ms"),
        "fixture_count": int(pack.get("fixture_count", 0)),
        "replayed_count": len(events),
        "normalized_count": len(events),
        "has_business_events": len(events) > 0,
        "topic_counts": topic_counts,
        "event_type_counts": event_type_counts,
        "events": events,
    }

    dated = save_report(report, OUT_LATEST, "bybit_business_event_replay")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"saved_latest={OUT_LATEST}")
    print(f"saved_dated={dated}")


if __name__ == "__main__":
    main()

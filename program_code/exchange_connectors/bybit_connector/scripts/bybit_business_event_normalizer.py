#!/usr/bin/env python3
import json
import hashlib
import time
from typing import Any, Dict, List


BUSINESS_TOPICS = {"wallet", "position", "order", "execution"}


def now_ms() -> int:
    return int(time.time() * 1000)


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha1_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def extract_topic(raw: Dict[str, Any]) -> str:
    topic = raw.get("topic")
    if isinstance(topic, str) and topic.strip():
        return topic.strip()
    return "unknown"


def extract_topic_root(topic: str) -> str:
    if not topic:
        return "unknown"
    return topic.split(".")[0].strip()


def extract_event_ts_ms(raw: Dict[str, Any], item: Dict[str, Any]) -> int:
    # 优先取 item 级别时间，再退化到 message 级别时间
    candidates = [
        item.get("creationTime"),
        item.get("updatedTime"),
        item.get("execTime"),
        item.get("ts"),
        raw.get("creationTime"),
        raw.get("updatedTime"),
        raw.get("ts"),
    ]
    for v in candidates:
        if v is None:
            continue
        try:
            return int(v)
        except Exception:
            pass
    return now_ms()


def extract_symbol(item: Dict[str, Any]) -> str:
    for k in ("symbol", "s", "coin"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_side(item: Dict[str, Any]) -> str:
    for k in ("side", "S"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_order_id(item: Dict[str, Any]) -> str:
    for k in ("orderId", "orderID", "i"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_exec_id(item: Dict[str, Any]) -> str:
    for k in ("execId", "execID"):
        v = item.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


def extract_conn_id(raw: Dict[str, Any]) -> str:
    v = raw.get("conn_id") or raw.get("connId")
    if isinstance(v, str) and v.strip():
        return v.strip()
    return ""


def build_normalized_payload(topic_root: str, item: Dict[str, Any]) -> Dict[str, Any]:
    out = {
        "symbol": extract_symbol(item),
        "side": extract_side(item),
        "order_id": extract_order_id(item),
        "exec_id": extract_exec_id(item),
    }

    if topic_root == "wallet":
        out.update({
            "coin": item.get("coin") if isinstance(item.get("coin"), str) else "",
            "wallet_balance": item.get("walletBalance"),
            "equity": item.get("equity"),
            "available_to_withdraw": item.get("availableToWithdraw"),
        })
    elif topic_root == "position":
        out.update({
            "size": item.get("size"),
            "position_idx": item.get("positionIdx"),
            "avg_price": item.get("avgPrice"),
            "unrealised_pnl": item.get("unrealisedPnl"),
        })
    elif topic_root == "order":
        out.update({
            "order_status": item.get("orderStatus"),
            "order_type": item.get("orderType"),
            "price": item.get("price"),
            "qty": item.get("qty"),
        })
    elif topic_root == "execution":
        out.update({
            "exec_price": item.get("execPrice"),
            "exec_qty": item.get("execQty"),
            "exec_fee": item.get("execFee"),
            "exec_type": item.get("execType"),
        })

    return out


def normalize_one_message(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    topic = extract_topic(raw)
    topic_root = extract_topic_root(topic)

    if topic_root not in BUSINESS_TOPICS:
        return []

    data = raw.get("data")
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = [data]
    else:
        items = []

    normalized_events: List[Dict[str, Any]] = []

    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue

        event_ts_ms = extract_event_ts_ms(raw, item)
        normalized_payload = build_normalized_payload(topic_root, item)

        event_core = {
            "event_schema_version": "v1",
            "exchange": "bybit",
            "ingestion_stage": "D22.1",
            "event_type": f"bybit_private_{topic_root}_event",
            "topic": topic,
            "topic_root": topic_root,
            "symbol": extract_symbol(item),
            "event_ts_ms": event_ts_ms,
            "ingest_ts_ms": now_ms(),
            "source_conn_id": extract_conn_id(raw),
            "source_message_ts_ms": raw.get("ts"),
            "source_sequence_hint": idx,
            "normalized_payload": normalized_payload,
            "raw_payload": item,
        }

        fingerprint_basis = {
            "topic": topic,
            "topic_root": topic_root,
            "symbol": event_core["symbol"],
            "event_ts_ms": event_core["event_ts_ms"],
            "normalized_payload": normalized_payload,
            "raw_payload": item,
        }
        event_core["event_fingerprint"] = sha1_text(stable_json_dumps(fingerprint_basis))

        normalized_events.append(event_core)

    return normalized_events


def normalize_many_messages(raw_messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for raw in raw_messages:
        if not isinstance(raw, dict):
            continue
        out.extend(normalize_one_message(raw))
    return out


def main():
    import sys

    raw_text = sys.stdin.read().strip()
    if not raw_text:
        print(json.dumps({
            "ok": False,
            "error": "empty_stdin",
            "normalized_count": 0
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    obj = json.loads(raw_text)
    if isinstance(obj, list):
        raw_messages = obj
    else:
        raw_messages = [obj]

    normalized = normalize_many_messages(raw_messages)

    print(json.dumps({
        "ok": True,
        "normalizer_version": "v1",
        "input_message_count": len(raw_messages),
        "normalized_count": len(normalized),
        "events": normalized
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

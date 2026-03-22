#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_extract_from_ws_jsonl.py
Role:
- 从 WS jsonl 日志中提取真正的 business-topic 消息
- 排除 auth / subscribe 等 control-plane 消息

Purpose in system:
- 属于 D22.2 的第一步
- 为 from_ws ingestion 提供更纯净输入

Maintenance notes:
- 当前 business_row_count = 0 可以是正常健康状态
- 不应把没有业务行直接判断为代码故障
'''

"""

import json
import time
from pathlib import Path

WS_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws")
OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

BUSINESS_TOPICS = {"wallet", "position", "order", "execution"}


def load_jsonl(path: Path):
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def find_latest_jsonl():
    files = sorted(WS_DIR.glob("bybit_private_ws_events_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    return files[0] if files else None


def is_business_message(obj):
    topic = obj.get("topic")
    if not isinstance(topic, str):
        return False
    root = topic.split(".")[0].strip()
    return root in BUSINESS_TOPICS


def main():
    ts_ms = int(time.time() * 1000)
    src = find_latest_jsonl()

    if not src:
        print(json.dumps({
            "ok": False,
            "error": "no_ws_jsonl_found",
            "search_dir": str(WS_DIR)
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    rows = load_jsonl(src)
    business_rows = [r for r in rows if isinstance(r, dict) and is_business_message(r)]

    out = {
        "report_type": "bybit_business_event_extract_from_ws_jsonl",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "source_jsonl": str(src),
        "source_row_count": len(rows),
        "business_row_count": len(business_rows),
        "messages": business_rows,
    }

    latest = OUT_DIR / "bybit_ws_business_messages_latest.json"
    dated = OUT_DIR / f"bybit_ws_business_messages_{ts_ms}.json"
    latest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "report_version": "v1",
        "source_jsonl": str(src),
        "source_row_count": len(rows),
        "business_row_count": len(business_rows),
        "latest_path": str(latest),
        "dated_path": str(dated),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

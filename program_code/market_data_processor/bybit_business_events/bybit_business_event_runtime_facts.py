#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_runtime_facts.py
Role:
- 根据 from_ws business events 生成统一 runtime facts
- 输出 topic_counts / event_type_counts / has_business_events / last_event_ts_ms

Purpose in system:
- 为 business event state resolver 提供事实层

Downstream:
- bybit_business_event_runtime_contract_check.py
- bybit_business_event_state_resolver.py

Maintenance notes:
- 这是业务事件的事实聚合层，不负责最终健康结论
'''

"""

import json
import time
from pathlib import Path
import os

INPUT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_events_from_ws_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LATEST_PATH = OUT_DIR / "bybit_business_event_runtime_facts_latest.json"


def count_by(items, key):
    out = {}
    for x in items:
        k = x.get(key) or "unknown"
        out[k] = out.get(k, 0) + 1
    return out


def main():
    ts_ms = int(time.time() * 1000)

    if not INPUT_PATH.exists():
        print(json.dumps({
            "ok": False,
            "error": "input_missing",
            "input_path": str(INPUT_PATH),
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    obj = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    events = obj.get("events") or []

    topic_counts = count_by(events, "topic_root")
    event_type_counts = count_by(events, "event_type")

    last_event_ts_ms = None
    if events:
        try:
            last_event_ts_ms = max(int(e.get("event_ts_ms")) for e in events if e.get("event_ts_ms") is not None)
        except Exception:
            last_event_ts_ms = None

    report = {
        "facts_type": "bybit_business_event_runtime_facts",
        "facts_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "D22.2",
        "source_report_type": obj.get("report_type"),
        "source_report_version": obj.get("report_version"),
        "source_ts_ms": obj.get("ts_ms"),
        "normalized_count": len(events),
        "topic_counts": topic_counts,
        "event_type_counts": event_type_counts,
        "last_event_ts_ms": last_event_ts_ms,
        "last_event_age_ms": (ts_ms - last_event_ts_ms) if last_event_ts_ms else None,
        "has_business_events": len(events) > 0,
    }

    dated = OUT_DIR / f"bybit_business_event_runtime_facts_{ts_ms}.json"
    LATEST_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

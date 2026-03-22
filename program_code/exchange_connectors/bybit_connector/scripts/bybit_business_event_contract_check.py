#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_contract_check.py
Role:
- 检查 D22.1 business event smoke 输出契约
- 校验字段、schema version、fingerprint、payload

Purpose in system:
- 保障 business event 归一化基础格式稳定

Maintenance notes:
- 适合在 schema 字段调整后优先跑
'''

"""

import json
import time
from pathlib import Path

INPUT_PATH = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_events_latest.json")
OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LATEST_OUT = OUT_DIR / "bybit_business_event_contract_latest.json"


def add(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    if not INPUT_PATH.exists():
        report = {
            "report_type": "bybit_business_event_contract_check",
            "report_version": "v1",
            "ts_ms": ts_ms,
            "overall_ok": False,
            "failed_count": 1,
            "checks": [{"name": "input_exists", "ok": False, "detail": str(INPUT_PATH)}],
            "failed_checks": [{"name": "input_exists", "ok": False, "detail": str(INPUT_PATH)}],
        }
        LATEST_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    obj = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    events = obj.get("events") or []

    add(checks, "report_type_expected", obj.get("report_type") == "bybit_business_event_ingestion_smoke", obj.get("report_type"))
    add(checks, "report_version_v1", obj.get("report_version") == "v1", obj.get("report_version"))
    add(checks, "events_nonempty", len(events) > 0, len(events))

    required_fields = [
        "event_schema_version",
        "exchange",
        "ingestion_stage",
        "event_type",
        "topic",
        "topic_root",
        "event_ts_ms",
        "ingest_ts_ms",
        "event_fingerprint",
        "normalized_payload",
        "raw_payload",
    ]

    if events:
        first = events[0]
        for f in required_fields:
            add(checks, f"field_present:{f}", f in first, first.get(f))

        add(checks, "exchange_bybit", first.get("exchange") == "bybit", first.get("exchange"))
        add(checks, "schema_version_v1", first.get("event_schema_version") == "v1", first.get("event_schema_version"))
        add(checks, "ingestion_stage_d22_1", first.get("ingestion_stage") == "D22.1", first.get("ingestion_stage"))
        add(checks, "fingerprint_nonempty", bool(first.get("event_fingerprint")), first.get("event_fingerprint"))

    failed = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_business_event_contract_check",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "overall_ok": len(failed) == 0,
        "failed_count": len(failed),
        "checks": checks,
        "failed_checks": failed,
    }

    LATEST_OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

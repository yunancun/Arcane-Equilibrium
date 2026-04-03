#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_runtime_contract_check.py
Role:
- 检查 business_event_ingestion_from_ws 与 runtime_facts 的契约一致性

Purpose in system:
- 防止 business event 链路上下游字段脱节

Maintenance notes:
- 字段变更后建议第一时间重跑本脚本
'''

"""

import json
import time
from pathlib import Path
import os

INGEST_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_events_from_ws_latest.json")
FACTS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events/bybit_business_event_runtime_facts_latest.json")
OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LATEST_OUT = OUT_DIR / "bybit_business_event_runtime_contract_latest.json"


def add(checks, name, ok, detail):
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def main():
    ts_ms = int(time.time() * 1000)
    checks = []

    add(checks, "ingest_exists", INGEST_PATH.exists(), str(INGEST_PATH))
    add(checks, "facts_exists", FACTS_PATH.exists(), str(FACTS_PATH))

    ingest = json.loads(INGEST_PATH.read_text(encoding="utf-8")) if INGEST_PATH.exists() else {}
    facts = json.loads(FACTS_PATH.read_text(encoding="utf-8")) if FACTS_PATH.exists() else {}

    add(checks, "ingest_report_type_expected", ingest.get("report_type") == "bybit_business_event_ingestion_from_ws", ingest.get("report_type"))
    add(checks, "facts_type_expected", facts.get("facts_type") == "bybit_business_event_runtime_facts", facts.get("facts_type"))
    add(checks, "facts_version_v1", facts.get("facts_version") == "v1", facts.get("facts_version"))
    add(checks, "exchange_bybit", facts.get("exchange") == "bybit", facts.get("exchange"))

    normalized_count = ingest.get("normalized_count")
    facts_count = facts.get("normalized_count")
    add(checks, "normalized_count_match", normalized_count == facts_count, {"ingest": normalized_count, "facts": facts_count})

    add(checks, "topic_counts_present", isinstance(facts.get("topic_counts"), dict), facts.get("topic_counts"))
    add(checks, "event_type_counts_present", isinstance(facts.get("event_type_counts"), dict), facts.get("event_type_counts"))
    add(checks, "has_business_events_field", "has_business_events" in facts, facts.get("has_business_events"))

    failed = [c for c in checks if not c["ok"]]

    report = {
        "report_type": "bybit_business_event_runtime_contract_check",
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

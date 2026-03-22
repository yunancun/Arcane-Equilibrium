#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_ingestion_smoke.py
Role:
- 用 fixture / smoke 数据验证 business event 归一化逻辑
- 证明基础 schema 能通

Purpose in system:
- 属于 D22.1 的基础验证
- 不依赖真实业务事件出现

Downstream:
- bybit_business_event_contract_check.py

Maintenance notes:
- 这是 schema smoke，不代表真实 ws 已经产生活动事件
'''

"""

import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path("/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts")
FIXTURE_SCRIPT = SCRIPT_DIR / "bybit_business_event_fixture_generator.py"
NORMALIZER_SCRIPT = SCRIPT_DIR / "bybit_business_event_normalizer.py"

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

OUT_LATEST = OUT_DIR / "bybit_business_events_latest.json"


def run_py(script: Path, stdin_text: str | None = None):
    proc = subprocess.run(
        [sys.executable, str(script)],
        input=stdin_text,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def main():
    ts_ms = int(time.time() * 1000)

    fixture_run = run_py(FIXTURE_SCRIPT)
    if fixture_run["returncode"] != 0:
        print(json.dumps({
            "ok": False,
            "stage": "fixture_generation",
            "fixture_run": fixture_run
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    fixture_obj = json.loads(fixture_run["stdout"])
    messages = fixture_obj.get("messages") or []

    normalizer_input = json.dumps(messages, ensure_ascii=False)
    norm_run = run_py(NORMALIZER_SCRIPT, stdin_text=normalizer_input)
    if norm_run["returncode"] != 0:
        print(json.dumps({
            "ok": False,
            "stage": "normalization",
            "normalizer_run": norm_run
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    norm_obj = json.loads(norm_run["stdout"])

    report = {
        "report_type": "bybit_business_event_ingestion_smoke",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "D22.1",
        "ok": True,
        "fixture_message_count": fixture_obj.get("message_count"),
        "normalized_count": norm_obj.get("normalized_count"),
        "events": norm_obj.get("events") or [],
    }

    dated_path = OUT_DIR / f"bybit_business_events_{ts_ms}.json"
    write_json(OUT_LATEST, report)
    write_json(dated_path, report)

    print(json.dumps({
        "ok": True,
        "report_type": report["report_type"],
        "report_version": report["report_version"],
        "normalized_count": report["normalized_count"],
        "latest_path": str(OUT_LATEST),
        "dated_path": str(dated_path),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

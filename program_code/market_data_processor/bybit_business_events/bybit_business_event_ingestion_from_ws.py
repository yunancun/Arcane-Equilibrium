#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_business_event_ingestion_from_ws.py
Role:
- 将 extract 出来的业务行归一化成 business events
- 生成 from_ws latest / dated 报告

Purpose in system:
- 构建真实业务事件接入层
- 为 runtime facts 和 state resolver 提供输入

Downstream:
- bybit_business_event_runtime_facts.py
- bybit_business_event_runtime_contract_check.py

Maintenance notes:
- normalized_count = 0 在当前阶段是允许状态
'''

"""

import json
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path("/home/ncyu/srv/program_code/market_data_processor/bybit_business_events")
EXTRACT_SCRIPT = SCRIPT_DIR / "bybit_business_event_extract_from_ws_jsonl.py"
NORMALIZER_SCRIPT = SCRIPT_DIR / "bybit_business_event_normalizer.py"

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/runtime/bybit/business_events")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LATEST_PATH = OUT_DIR / "bybit_business_events_from_ws_latest.json"


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


def main():
    ts_ms = int(time.time() * 1000)

    extract_run = run_py(EXTRACT_SCRIPT)
    if extract_run["returncode"] != 0:
        print(json.dumps({
            "ok": False,
            "stage": "extract_ws_messages",
            "extract_run": extract_run,
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    extract_latest = OUT_DIR / "bybit_ws_business_messages_latest.json"
    extract_obj = json.loads(extract_latest.read_text(encoding="utf-8"))
    messages = extract_obj.get("messages") or []

    norm_run = run_py(NORMALIZER_SCRIPT, stdin_text=json.dumps(messages, ensure_ascii=False))
    if norm_run["returncode"] != 0:
        print(json.dumps({
            "ok": False,
            "stage": "normalize_ws_messages",
            "normalizer_run": norm_run,
        }, ensure_ascii=False, indent=2))
        raise SystemExit(1)

    norm_obj = json.loads(norm_run["stdout"])

    report = {
        "report_type": "bybit_business_event_ingestion_from_ws",
        "report_version": "v1",
        "ts_ms": ts_ms,
        "exchange": "bybit",
        "stage": "D22.2",
        "source_jsonl": extract_obj.get("source_jsonl"),
        "source_row_count": extract_obj.get("source_row_count"),
        "business_row_count": extract_obj.get("business_row_count"),
        "normalized_count": norm_obj.get("normalized_count"),
        "events": norm_obj.get("events") or [],
    }

    dated = OUT_DIR / f"bybit_business_events_from_ws_{ts_ms}.json"
    LATEST_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    dated.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "report_type": report["report_type"],
        "report_version": report["report_version"],
        "business_row_count": report["business_row_count"],
        "normalized_count": report["normalized_count"],
        "latest_path": str(LATEST_PATH),
        "dated_path": str(dated),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

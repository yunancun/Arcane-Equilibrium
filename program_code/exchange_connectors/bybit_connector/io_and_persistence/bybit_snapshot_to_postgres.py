#!/usr/bin/env python3
"""
MODULE_NOTE = '''
[Maintainer Note]
Script: bybit_snapshot_to_postgres.py
Role:
- 汇总 account / positions / order_history / execution_history
- 生成统一 snapshot 文件
- 写出 payload_time_summary
- 将 snapshot 相关内容落库

Purpose in system:
- 是 observer packet / runtime / summary / audit 的关键基础输入

Upstream:
- REST checks
- preflight guard

Downstream:
- bybit_normalize_latest_snapshot_to_postgres.py
- bybit_build_decision_packet.py
- bybit_observer_acceptance_check.py
- bybit_runtime_state_resolver.py
- bybit_readonly_audit.py

Maintenance notes:
- snapshot 文件里当前主时间字段是 ts_ms
- 如果改 snapshot 顶层字段，务必同步 audit / final summary / packet ref 校验
'''

"""

import json
import subprocess
import sys
import time
from pathlib import Path
import os

ACCOUNT_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/log_files/connector_logs/bybit_private_account_check_latest.json")
POSITIONS_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/log_files/connector_logs/bybit_private_positions_check_latest.json")
ORDER_HISTORY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/log_files/connector_logs/bybit_private_order_history_check_latest.json")
EXECUTION_HISTORY_PATH = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/connector_logs/bybit/bybit_private_execution_history_latest.json")

OUT_DIR = Path(os.environ.get("OPENCLAW_SRV_ROOT", ".") + "/docker_projects/trading_services/connector_logs/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

LATEST_SNAPSHOT = OUT_DIR / "bybit_system_snapshot_latest.json"

def load_json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def extract_payload_ts_ms(name, payload):
    if not isinstance(payload, dict):
        return None

    if name in ("account", "positions", "order_history"):
        return (((payload.get("response") or {}).get("time")))

    if name == "execution_history":
        if payload.get("ts_ms") is not None:
            return payload.get("ts_ms")
        spot = payload.get("spot") or {}
        linear = payload.get("linear") or {}
        for v in (spot.get("time"), linear.get("time")):
            if v is not None:
                return v

    return None

def source_meta(name, path: Path, payload):
    present = payload is not None
    meta = {
        "name": name,
        "present": present,
        "ok": False,
        "path": str(path),
        "error": None,
        "retCode": None,
        "retMsg": None,
        "count": None,
        "payload_ts_ms": None,
    }

    if not present:
        meta["error"] = "missing"
        return meta

    meta["payload_ts_ms"] = extract_payload_ts_ms(name, payload)

    if name == "execution_history":
        spot = payload.get("spot") or {}
        linear = payload.get("linear") or {}
        meta["ok"] = bool(spot.get("ok")) and bool(linear.get("ok"))
        meta["retCode"] = {
            "spot": spot.get("retCode"),
            "linear": linear.get("retCode"),
        }
        meta["retMsg"] = {
            "spot": spot.get("retMsg"),
            "linear": linear.get("retMsg"),
        }
        meta["count"] = int(spot.get("count") or 0) + int(linear.get("count") or 0)
        return meta

    meta["ok"] = bool(payload.get("ok"))
    meta["retCode"] = payload.get("retCode")
    meta["retMsg"] = payload.get("retMsg")

    if name == "positions":
        meta["count"] = len((((payload.get("response") or {}).get("result") or {}).get("list") or []))
    elif name == "order_history":
        meta["count"] = len((((payload.get("response") or {}).get("result") or {}).get("list") or []))
    else:
        meta["count"] = None

    return meta

def main():
    ts_ms = int(time.time() * 1000)

    account = load_json(ACCOUNT_PATH)
    positions = load_json(POSITIONS_PATH)
    order_history = load_json(ORDER_HISTORY_PATH)
    execution_history = load_json(EXECUTION_HISTORY_PATH)

    payload = {
        "account": account,
        "positions": positions,
        "order_history": order_history,
        "execution_history": execution_history,
    }

    sources = {
        "account": source_meta("account", ACCOUNT_PATH, account),
        "positions": source_meta("positions", POSITIONS_PATH, positions),
        "order_history": source_meta("order_history", ORDER_HISTORY_PATH, order_history),
        "execution_history": source_meta("execution_history", EXECUTION_HISTORY_PATH, execution_history),
    }

    payload_time_summary = {
        "account_payload_ts_ms": sources["account"]["payload_ts_ms"],
        "positions_payload_ts_ms": sources["positions"]["payload_ts_ms"],
        "order_history_payload_ts_ms": sources["order_history"]["payload_ts_ms"],
        "execution_history_payload_ts_ms": sources["execution_history"]["payload_ts_ms"],
    }

    snapshot = {
        "snapshot_type": "bybit_system_snapshot",
        "snapshot_version": "v2",
        "ts_ms": ts_ms,
        "payload_time_summary": payload_time_summary,
        "sources": sources,
        "payload": payload,
    }

    dated = OUT_DIR / f"bybit_system_snapshot_{ts_ms}.json"
    normalized = json.dumps(snapshot, ensure_ascii=False, indent=2)
    LATEST_SNAPSHOT.write_text(normalized + "\n", encoding="utf-8")
    dated.write_text(normalized + "\n", encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "returncode": 0,
        "latest_snapshot": str(LATEST_SNAPSHOT),
        "dated_snapshot": str(dated),
        "sources": sources,
        "payload_time_summary": payload_time_summary,
        "stdout": "snapshot_json_written",
        "stderr": ""
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

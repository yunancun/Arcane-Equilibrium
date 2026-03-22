#!/usr/bin/env python3
import json
import time
from pathlib import Path

SRC_ACCOUNT = Path("/home/ncyu/srv/log_files/connector_logs/bybit_private_account_check_latest.json")
SRC_POSITIONS = Path("/home/ncyu/srv/log_files/connector_logs/bybit_private_positions_check_latest.json")
SRC_ORDER_HISTORY = Path("/home/ncyu/srv/log_files/connector_logs/bybit_private_order_history_check_latest.json")
SRC_EXECUTION_HISTORY = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/bybit_private_execution_history_latest.json")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def load_json(path: Path):
    if not path.exists():
        return {
            "present": False,
            "path": str(path),
            "error": "file_missing",
            "data": None,
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            "present": True,
            "path": str(path),
            "error": None,
            "data": data,
        }
    except Exception as e:
        return {
            "present": True,
            "path": str(path),
            "error": f"json_load_failed: {e}",
            "data": None,
        }

def summarize_section(name: str, wrapped: dict):
    if not wrapped["present"] or wrapped["data"] is None:
        return {
            "name": name,
            "present": wrapped["present"],
            "ok": False,
            "path": wrapped["path"],
            "error": wrapped["error"],
        }

    data = wrapped["data"]

    ok = None
    count = None
    ret_code = None
    ret_msg = None

    if isinstance(data, dict):
        if "ok" in data:
            ok = data.get("ok")
        if "retCode" in data:
            ret_code = data.get("retCode")
        if "retMsg" in data:
            ret_msg = data.get("retMsg")
        if "count" in data:
            count = data.get("count")

        if name == "execution_history":
            spot = data.get("spot", {})
            linear = data.get("linear", {})
            ok = bool(spot.get("ok")) and bool(linear.get("ok"))
            count = (spot.get("count", 0) or 0) + (linear.get("count", 0) or 0)
            ret_code = {
                "spot": spot.get("retCode"),
                "linear": linear.get("retCode"),
            }
            ret_msg = {
                "spot": spot.get("retMsg"),
                "linear": linear.get("retMsg"),
            }

    return {
        "name": name,
        "present": True,
        "ok": ok,
        "path": wrapped["path"],
        "error": wrapped["error"],
        "retCode": ret_code,
        "retMsg": ret_msg,
        "count": count,
    }

def main():
    ts_ms = int(time.time() * 1000)

    account = load_json(SRC_ACCOUNT)
    positions = load_json(SRC_POSITIONS)
    order_history = load_json(SRC_ORDER_HISTORY)
    execution_history = load_json(SRC_EXECUTION_HISTORY)

    snapshot = {
        "snapshot_type": "bybit_system_snapshot",
        "ts_ms": ts_ms,
        "sources": {
            "account": summarize_section("account", account),
            "positions": summarize_section("positions", positions),
            "order_history": summarize_section("order_history", order_history),
            "execution_history": summarize_section("execution_history", execution_history),
        },
        "payload": {
            "account": account["data"],
            "positions": positions["data"],
            "order_history": order_history["data"],
            "execution_history": execution_history["data"],
        }
    }

    latest_path = OUT_DIR / "bybit_system_snapshot_latest.json"
    dated_path = OUT_DIR / f"bybit_system_snapshot_{ts_ms}.json"

    latest_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    dated_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(snapshot["sources"], ensure_ascii=False, indent=2))
    print()
    print(f"saved_latest={latest_path}")
    print(f"saved_dated={dated_path}")

if __name__ == "__main__":
    main()

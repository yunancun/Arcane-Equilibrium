#!/usr/bin/env python3
import json
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

BASE_URL = "https://api.bybit.com"

def fetch_json(url: str) -> dict:
    start = time.time()
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        latency_ms = int((time.time() - start) * 1000)
        return {"json": json.loads(body), "latency_ms": latency_ms}

def main() -> None:
    results = {
        "check_time_utc": datetime.now(timezone.utc).isoformat(),
        "exchange_name": "bybit",
        "connectivity": {},
        "issues": [],
    }

    time_url = f"{BASE_URL}/v5/market/time"
    try:
        r = fetch_json(time_url)
        payload = r["json"]
        results["connectivity"]["server_time"] = {
            "ok": payload.get("retCode") == 0,
            "latency_ms": r["latency_ms"],
            "retCode": payload.get("retCode"),
            "retMsg": payload.get("retMsg"),
            "timeSecond": payload.get("result", {}).get("timeSecond"),
            "timeNano": payload.get("result", {}).get("timeNano"),
        }
        if payload.get("retCode") != 0:
            results["issues"].append("server_time_endpoint_returned_nonzero_retCode")
    except Exception as e:
        results["connectivity"]["server_time"] = {"ok": False, "error": str(e)}
        results["issues"].append("server_time_endpoint_failed")

    query = urllib.parse.urlencode({"category": "spot", "symbol": "BTCUSDT"})
    ticker_url = f"{BASE_URL}/v5/market/tickers?{query}"
    try:
        r = fetch_json(ticker_url)
        payload = r["json"]
        items = payload.get("result", {}).get("list", [])
        first = items[0] if items else {}
        results["connectivity"]["ticker_snapshot"] = {
            "ok": payload.get("retCode") == 0 and len(items) > 0,
            "latency_ms": r["latency_ms"],
            "retCode": payload.get("retCode"),
            "retMsg": payload.get("retMsg"),
            "symbol": first.get("symbol"),
            "lastPrice": first.get("lastPrice"),
            "bid1Price": first.get("bid1Price"),
            "ask1Price": first.get("ask1Price"),
        }
        if payload.get("retCode") != 0 or len(items) == 0:
            results["issues"].append("ticker_snapshot_failed_or_empty")
    except Exception as e:
        results["connectivity"]["ticker_snapshot"] = {"ok": False, "error": str(e)}
        results["issues"].append("ticker_snapshot_endpoint_failed")

    print(json.dumps(results, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
─────────────────────────────────────────────────────────────────────────
MODULE_NOTE — Bybit public endpoint connectivity check (read-only smoke probe)

模組目的：
    對 Bybit 公開（public）REST endpoint 跑兩個輕量探針 —
    `/v5/market/time`（伺服器時間）+ `/v5/market/tickers`（BTCUSDT spot
    snapshot）— 並把結果以單一 JSON 物件印到 stdout，供 operator 與
    cron／observer 流水線判斷「公開 API 是否可達」。

    本工具**完全唯讀**：不帶 API key、不帶 HMAC 簽名、不打 private endpoint，
    因此可在任何環境（Mac dev / Linux trade-core / CI）安全跑，不會干擾真實
    交易管線。

Module purpose:
    Run two lightweight probes against Bybit public REST endpoints —
    `/v5/market/time` (server time) + `/v5/market/tickers` (BTCUSDT spot
    snapshot) — and print a single JSON envelope to stdout for operator /
    cron / observer pipeline to assess "is the public API reachable".

    This tool is **strictly read-only**: no API key, no HMAC signature, no
    private endpoint hits. Safe to run in any environment (Mac dev / Linux
    trade-core / CI) without disturbing the live trading pipeline.

關聯文件 / Related:
    - CLAUDE.md §七 ★★ 跨平台兼容性原則「路徑/URL 不硬編碼」(cross-platform
      compliance: no hardcoded URL literals)
    - TODO.md L385 Wave 4 G9 series + BB Wave 4 audit batch（finding =
      硬編碼 base URL，違 §七 ★★ 第 1 條）

環境變數契約 / Env var contract:
    `OPENCLAW_BYBIT_PUBLIC_BASE_URL` — Bybit public REST root.
        - 未設定 → fallback `https://api.bybit.com`（mainnet 公開 API，與
          歷史行為等價，向後兼容不破現行為）
        - 設 `https://api-demo.bybit.com` → 走 demo public
        - 設 `https://api-testnet.bybit.com` → 走 testnet public
        - default 永遠保留：避免「忘 export env」就讓 healthcheck 整片紅
        - If unset → fallback `https://api.bybit.com` (mainnet public,
          equivalent to prior hardcoded behaviour, back-compat preserved)

  本工具不讀 `OPENCLAW_BYBIT_*_API_KEY*` 等私鑰類 env var（純公開）；env var
  命名空間 `OPENCLAW_BYBIT_PUBLIC_*` 與既有 private endpoint base URL 邏輯
  顯式區分，避免 operator 誤把 demo private secret 對到 mainnet public 流量。

  This tool does NOT read any `OPENCLAW_BYBIT_*_API_KEY*` or other private
  credentials. The `OPENCLAW_BYBIT_PUBLIC_*` namespace is intentionally
  distinct from private-endpoint base URL handling to prevent operators
  from accidentally pairing demo private secrets with mainnet public flows.

CLI / 跑法:
    # default (no env var) → mainnet public
    python3 bybit_public_connectivity_check.py

    # override → testnet public
    OPENCLAW_BYBIT_PUBLIC_BASE_URL='https://api-testnet.bybit.com' \\
        python3 bybit_public_connectivity_check.py

不變量 / Invariants:
    - exit code 永遠 0（即使 endpoint FAIL，仍輸出 JSON 含 issues 陣列；
      上游 cron/observer 由 issues 長度判定）
    - stdout 只有一個 single-line / multi-line JSON 物件，不雜 log 訊息
─────────────────────────────────────────────────────────────────────────
"""

import json
import os
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone

# Bybit public REST base URL（環境變數覆寫 + mainnet default 向後兼容）
# Bybit public REST base URL: env var override + mainnet default for back-compat.
# 為什麼 default 不刪 / Why default kept:
#   先前版本硬編碼 `https://api.bybit.com`；改為 env var 後若 default 拿掉，
#   operator 忘 export 即整體 healthcheck 破。default 保留 = 失敗默認等同
#   舊行為（DOC-01 §5.6 失敗默認收縮 — 此 case 收縮 = 不破現行為）。
#   Removing the default would silently break healthcheck for any operator
#   who forgets to export the env. Keep default = fail-soft to historical
#   behaviour (DOC-01 §5.6 conservative-fallback principle).
BASE_URL = os.environ.get(
    "OPENCLAW_BYBIT_PUBLIC_BASE_URL",
    "https://api.bybit.com",
)


def fetch_json(url: str) -> dict:
    """
    HTTP GET + JSON decode + 延遲量測 / HTTP GET + JSON decode + latency timing.

    回傳 / Returns:
        {"json": <decoded payload>, "latency_ms": <int>}

    例外 / Raises:
        urllib.error.URLError / json.JSONDecodeError 由 caller 捕獲
        (caller catches network or decode errors and records issue tag).
    """
    start = time.time()
    with urllib.request.urlopen(url, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        latency_ms = int((time.time() - start) * 1000)
        return {"json": json.loads(body), "latency_ms": latency_ms}


def main() -> None:
    """
    執行兩個探針並印出 JSON 報告 / Run both probes and print JSON report.

    報告結構 / Report shape:
        {
          "check_time_utc": ISO-8601,
          "exchange_name": "bybit",
          "base_url": <實際使用的 base URL，便於 audit 確認 env 生效>,
          "connectivity": {
              "server_time": {...},
              "ticker_snapshot": {...}
          },
          "issues": [<short tag list, empty == healthy>]
        }

    `base_url` 欄位（新加）：當 operator 跑時不確定 env var 是否生效，可
    直接從 JSON 輸出讀回實際 base，免猜。
    `base_url` field (new): lets operators verify the env var actually
    propagated into this run, no need to guess from logs.
    """
    results = {
        "check_time_utc": datetime.now(timezone.utc).isoformat(),
        "exchange_name": "bybit",
        "base_url": BASE_URL,
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

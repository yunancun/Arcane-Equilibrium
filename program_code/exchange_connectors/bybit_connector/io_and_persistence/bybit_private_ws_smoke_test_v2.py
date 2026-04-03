#!/usr/bin/env python3
import json
import time
import hmac
import hashlib
import threading
import argparse
from pathlib import Path

import os
import websocket

WS_URL = "wss://stream.bybit.com/v5/private"

_SRV = os.environ.get("OPENCLAW_SRV_ROOT", ".")
API_KEY_PATH = Path(_SRV + "/settings/secret_files/bybit/read_only/api_key")
API_SECRET_PATH = Path(_SRV + "/settings/secret_files/bybit/read_only/api_secret")

OUT_DIR = Path(_SRV + "/docker_projects/trading_services/connector_logs/bybit/ws")
OUT_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TOPICS = ["wallet", "position", "order", "execution"]


def read_secret(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def build_auth_args(api_key: str, api_secret: str):
    expires = int((time.time() + 10) * 1000)
    payload = f"GET/realtime{expires}"
    signature = hmac.new(
        api_secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()
    return [api_key, expires, signature]


def append_jsonl(path: Path, obj: dict):
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-seconds", type=int, default=40)
    parser.add_argument("--topics", nargs="*", default=DEFAULT_TOPICS)
    args = parser.parse_args()

    api_key = read_secret(API_KEY_PATH)
    api_secret = read_secret(API_SECRET_PATH)

    ts_ms = int(time.time() * 1000)
    jsonl_path = OUT_DIR / f"bybit_private_ws_events_{ts_ms}.jsonl"
    summary_path = OUT_DIR / "bybit_private_ws_smoke_latest.json"

    state = {
        "ts_ms": ts_ms,
        "ws_url": WS_URL,
        "topics_requested": args.topics,
        "auth_ok": False,
        "subscribe_ok": False,
        "subscribed_topics": [],
        "message_count": 0,
        "topic_message_count": {},
        "events_preview": [],
        "errors": [],
        "opened": False,
        "closed": False,
    }

    lock = threading.Lock()

    def on_open(ws):
        with lock:
            state["opened"] = True
        auth_msg = {"op": "auth", "args": build_auth_args(api_key, api_secret)}
        ws.send(json.dumps(auth_msg))
        append_jsonl(jsonl_path, {"kind": "client_send", "data": auth_msg, "ts_ms": int(time.time() * 1000)})

    def on_message(ws, message):
        now_ms = int(time.time() * 1000)
        try:
            data = json.loads(message)
        except Exception:
            data = {"raw": message}

        append_jsonl(jsonl_path, {"kind": "server_msg", "data": data, "ts_ms": now_ms})

        with lock:
            state["message_count"] += 1

            if isinstance(data, dict):
                if data.get("op") == "auth" and data.get("success") is True:
                    state["auth_ok"] = True
                    sub_msg = {"op": "subscribe", "args": args.topics}
                    ws.send(json.dumps(sub_msg))
                    append_jsonl(jsonl_path, {"kind": "client_send", "data": sub_msg, "ts_ms": int(time.time() * 1000)})

                if data.get("op") == "subscribe" and data.get("success") is True:
                    state["subscribe_ok"] = True
                    state["subscribed_topics"] = list(args.topics)

                topic = data.get("topic")
                if topic:
                    state["topic_message_count"][topic] = state["topic_message_count"].get(topic, 0) + 1

                if len(state["events_preview"]) < 12:
                    state["events_preview"].append(data)

    def on_error(ws, error):
        with lock:
            state["errors"].append(str(error))
        append_jsonl(jsonl_path, {"kind": "error", "data": str(error), "ts_ms": int(time.time() * 1000)})

    def on_close(ws, code, msg):
        with lock:
            state["closed"] = True
            state["close_code"] = code
            state["close_msg"] = msg
        append_jsonl(jsonl_path, {"kind": "close", "data": {"code": code, "msg": msg}, "ts_ms": int(time.time() * 1000)})

    ws = websocket.WebSocketApp(
        WS_URL,
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )

    t = threading.Thread(
        target=lambda: ws.run_forever(ping_interval=20, ping_timeout=10),
        daemon=True,
    )
    t.start()

    deadline = time.time() + args.run_seconds
    while time.time() < deadline:
        time.sleep(1)

    try:
        ws.close()
    except Exception as e:
        with lock:
            state["errors"].append(f"close_failed: {e}")

    time.sleep(2)

    summary_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(state, ensure_ascii=False, indent=2))
    print(f"jsonl_log={jsonl_path}")
    print(f"summary={summary_path}")


if __name__ == "__main__":
    main()

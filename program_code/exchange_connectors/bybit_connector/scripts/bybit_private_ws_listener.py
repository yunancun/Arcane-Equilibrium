#!/usr/bin/env python3
import json
import time
import hmac
import hashlib
import threading
import signal
from pathlib import Path

import websocket

WS_URL = "wss://stream.bybit.com/v5/private"

API_KEY_PATH = Path("/home/ncyu/srv/settings/secret_files/bybit/read_only/api_key")
API_SECRET_PATH = Path("/home/ncyu/srv/settings/secret_files/bybit/read_only/api_secret")

OUT_DIR = Path("/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws_persistent")
OUT_DIR.mkdir(parents=True, exist_ok=True)

TOPICS = ["wallet", "position", "order", "execution"]
PING_INTERVAL = 20
PING_TIMEOUT = 10
RECONNECT_DELAY_SEC = 5
STATUS_WRITE_INTERVAL_SEC = 5

stop_flag = False
active_ws = None


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
    global stop_flag, active_ws

    api_key = read_secret(API_KEY_PATH)
    api_secret = read_secret(API_SECRET_PATH)

    session_ts_ms = int(time.time() * 1000)
    events_path = OUT_DIR / f"bybit_private_ws_listener_events_{session_ts_ms}.jsonl"
    status_path = OUT_DIR / "bybit_private_ws_listener_status_latest.json"

    state = {
        "listener_type": "bybit_private_ws_listener",
        "listener_version": "v2",
        "session_ts_ms": session_ts_ms,
        "started_ts_ms": session_ts_ms,
        "ws_url": WS_URL,
        "topics_requested": TOPICS,
        "running": True,
        "stop_requested": False,
        "shutdown_reason": None,
        "connection_attempts": 0,
        "connection_open_count": 0,
        "auth_ok_count": 0,
        "subscribe_ok_count": 0,
        "message_count": 0,
        "topic_message_count": {},
        "last_error": None,
        "last_close": None,
        "last_conn_id": None,
        "last_event_ts_ms": None,
    }

    lock = threading.Lock()

    def write_status():
        with lock:
            snapshot = dict(state)
        status_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    def periodic_status_writer():
        while not stop_flag:
            write_status()
            time.sleep(STATUS_WRITE_INTERVAL_SEC)
        write_status()

    def request_stop(reason: str):
        global stop_flag, active_ws
        stop_flag = True
        with lock:
            state["stop_requested"] = True
            state["running"] = False
            state["shutdown_reason"] = reason
        write_status()

        ws = active_ws
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass

    def sig_handler(signum, frame):
        request_stop(f"signal_{signum}")

    signal.signal(signal.SIGINT, sig_handler)
    signal.signal(signal.SIGTERM, sig_handler)

    status_thread = threading.Thread(target=periodic_status_writer, daemon=True)
    status_thread.start()

    append_jsonl(events_path, {
        "kind": "listener_start",
        "ts_ms": int(time.time() * 1000),
        "data": {"session_ts_ms": session_ts_ms, "topics": TOPICS}
    })

    while not stop_flag:
        with lock:
            state["connection_attempts"] += 1

        def on_open(ws):
            with lock:
                state["connection_open_count"] += 1
            auth_msg = {"op": "auth", "args": build_auth_args(api_key, api_secret)}
            ws.send(json.dumps(auth_msg))
            append_jsonl(events_path, {"kind": "client_send", "ts_ms": int(time.time() * 1000), "data": auth_msg})

        def on_message(ws, message):
            now_ms = int(time.time() * 1000)
            try:
                data = json.loads(message)
            except Exception:
                data = {"raw": message}

            append_jsonl(events_path, {"kind": "server_msg", "ts_ms": now_ms, "data": data})

            with lock:
                state["message_count"] += 1
                state["last_event_ts_ms"] = now_ms

                if isinstance(data, dict):
                    if data.get("op") == "auth" and data.get("success") is True:
                        state["auth_ok_count"] += 1
                        state["last_conn_id"] = data.get("conn_id")
                        sub_msg = {"op": "subscribe", "args": TOPICS}
                        ws.send(json.dumps(sub_msg))
                        append_jsonl(events_path, {"kind": "client_send", "ts_ms": int(time.time() * 1000), "data": sub_msg})

                    elif data.get("op") == "subscribe" and data.get("success") is True:
                        state["subscribe_ok_count"] += 1
                        state["last_conn_id"] = data.get("conn_id")

                    topic = data.get("topic")
                    if topic:
                        state["topic_message_count"][topic] = state["topic_message_count"].get(topic, 0) + 1

        def on_error(ws, error):
            with lock:
                state["last_error"] = str(error)
            append_jsonl(events_path, {"kind": "error", "ts_ms": int(time.time() * 1000), "data": str(error)})

        def on_close(ws, code, msg):
            with lock:
                state["last_close"] = {"code": code, "msg": msg, "ts_ms": int(time.time() * 1000)}
            append_jsonl(events_path, {"kind": "close", "ts_ms": int(time.time() * 1000), "data": {"code": code, "msg": msg}})

        ws = websocket.WebSocketApp(
            WS_URL,
            on_open=on_open,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
        )
        active_ws = ws

        try:
            ws.run_forever(ping_interval=PING_INTERVAL, ping_timeout=PING_TIMEOUT)
        except Exception as e:
            with lock:
                state["last_error"] = f"run_forever_exception: {e}"
            append_jsonl(events_path, {"kind": "exception", "ts_ms": int(time.time() * 1000), "data": str(e)})

        active_ws = None

        if stop_flag:
            break

        time.sleep(RECONNECT_DELAY_SEC)

    with lock:
        state["running"] = False
        state["stop_requested"] = True
        if state["shutdown_reason"] is None:
            state["shutdown_reason"] = "loop_exit"

    append_jsonl(events_path, {
        "kind": "listener_stop",
        "ts_ms": int(time.time() * 1000),
        "data": {"shutdown_reason": state["shutdown_reason"]}
    })

    write_status()

    print(json.dumps({
        "ok": True,
        "status_path": str(status_path),
        "events_path": str(events_path),
        "shutdown_reason": state["shutdown_reason"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

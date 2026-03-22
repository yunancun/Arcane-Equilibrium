#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="/home/ncyu/srv/venvs/trading_ws/bin/python"
SCRIPT_PATH="/home/ncyu/srv/program_code/exchange_connectors/bybit_connector/scripts/bybit_private_ws_listener.py"
LOG_DIR="/home/ncyu/srv/docker_projects/trading_services/connector_logs/bybit/ws_persistent"
PID_FILE="$LOG_DIR/bybit_private_ws_listener.pid"
OUT_FILE="$LOG_DIR/bybit_private_ws_listener.out"
STATUS_FILE="$LOG_DIR/bybit_private_ws_listener_status_latest.json"

mkdir -p "$LOG_DIR"

is_running() {
  if [[ -f "$PID_FILE" ]]; then
    PID="$(cat "$PID_FILE" 2>/dev/null || true)"
    if [[ -n "${PID:-}" ]] && kill -0 "$PID" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

start_listener() {
  if is_running; then
    echo "listener already running, pid=$(cat "$PID_FILE")"
    exit 0
  fi

  nohup "$PYTHON_BIN" "$SCRIPT_PATH" >> "$OUT_FILE" 2>&1 &
  PID=$!
  echo "$PID" > "$PID_FILE"
  sleep 3

  if kill -0 "$PID" 2>/dev/null; then
    echo "listener started, pid=$PID"
  else
    echo "listener failed to start"
    exit 1
  fi
}

stop_listener() {
  if ! is_running; then
    echo "listener not running"
    rm -f "$PID_FILE"
    exit 0
  fi

  PID="$(cat "$PID_FILE")"
  kill "$PID" 2>/dev/null || true

  for _ in $(seq 1 10); do
    if kill -0 "$PID" 2>/dev/null; then
      sleep 1
    else
      break
    fi
  done

  if kill -0 "$PID" 2>/dev/null; then
    echo "listener still running after graceful stop, sending SIGKILL"
    kill -9 "$PID" 2>/dev/null || true
  fi

  rm -f "$PID_FILE"
  echo "listener stopped"
}

status_listener() {
  if is_running; then
    echo "listener running, pid=$(cat "$PID_FILE")"
  else
    echo "listener not running"
  fi

  echo
  echo "===== status file ====="
  if [[ -f "$STATUS_FILE" ]]; then
    cat "$STATUS_FILE"
  else
    echo "status file missing: $STATUS_FILE"
  fi

  echo
  echo "===== ps ====="
  ps -ef | grep bybit_private_ws_listener.py | grep -v grep || true
}

restart_listener() {
  stop_listener || true
  sleep 1
  start_listener
}

case "${1:-}" in
  start)
    start_listener
    ;;
  stop)
    stop_listener
    ;;
  restart)
    restart_listener
    ;;
  status)
    status_listener
    ;;
  *)
    echo "usage: $0 {start|stop|restart|status}"
    exit 1
    ;;
esac

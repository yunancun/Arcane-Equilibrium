#!/bin/bash
# stop_all.sh — 停止 Rust 引擎 + 設置 maintenance flag 阻止 watchdog 自動重啟
# MODULE_NOTE (CN): 優雅停止 Rust 引擎並建立 maintenance flag，讓 engine_watchdog.py
#   偵測到引擎死亡時不會自動重啟。operator 顯式意圖停機時必須走此腳本，否則
#   watchdog 會把引擎拉回來。移除 flag 需要 `rm /tmp/openclaw/engine_maintenance.flag`
#   或呼叫 restart_all.sh（會自動清除 flag）。
# MODULE_NOTE (EN): Gracefully stops the Rust engine and creates a maintenance
#   flag so engine_watchdog.py does NOT auto-restart. Operator MUST use this
#   script for explicit stops; otherwise the watchdog will rescue the engine.
#   Remove flag with `rm /tmp/openclaw/engine_maintenance.flag` or by running
#   restart_all.sh (which clears the flag automatically).
#
# Usage: bash helper_scripts/stop_all.sh [scope]
#   scope: --engine-only | --api-only | (none = both)
#
# 使用範例：
#   bash helper_scripts/stop_all.sh                  # 停引擎+API，設 flag
#   bash helper_scripts/stop_all.sh --engine-only    # 只停引擎
#   rm /tmp/openclaw/engine_maintenance.flag         # 解除維護模式

set -e
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# Runtime data dir (env var for Mac compatibility).
# Mac dev recommendation: export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"
# Runtime 資料目錄（支援 Mac env var 部署）。
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
ENGINE_BIN_REL="rust/target/release/openclaw-engine"
ENGINE_BIN_ABS="$REPO_ROOT/$ENGINE_BIN_REL"

SCOPE="${1:-all}"
case "$SCOPE" in
    --engine-only|--api-only|all|"") ;;
    *)
        echo "Unknown argument: $SCOPE" >&2
        echo "Usage: bash helper_scripts/stop_all.sh [--engine-only|--api-only]" >&2
        exit 1
        ;;
esac

process_cwd() {
    local pid="$1"
    if command -v pwdx >/dev/null 2>&1; then
        pwdx "$pid" 2>/dev/null | sed 's/^[^:]*: //'
    elif command -v lsof >/dev/null 2>&1; then
        lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -1
    fi
}

is_openclaw_engine_pid() {
    local pid="$1"
    local cmd cwd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(process_cwd "$pid" || true)"
    if [[ "$cmd" == *"$ENGINE_BIN_ABS"* ]]; then
        return 0
    fi
    [[ "$cwd" == "$REPO_ROOT" ]] || return 1
    [[ "$cmd" == *"$ENGINE_BIN_REL"* || "$cmd" == *"/openclaw-engine"* ]]
}

engine_pids() {
    local pid
    for pid in $(pgrep -f "openclaw-engine" 2>/dev/null || true); do
        if is_openclaw_engine_pid "$pid"; then
            printf '%s\n' "$pid"
        else
            echo "WARN: skip non-OpenClaw engine pid -> $pid" >&2
        fi
    done
}

engine_running() {
    [[ -n "$(engine_pids)" ]]
}

signal_engine_pids() {
    local signal="$1"
    local pid
    for pid in $(engine_pids); do
        kill "-$signal" "$pid" 2>/dev/null || true
    done
}

stop_engine() {
    # Fix 2 (2026-04-14): create maintenance flag BEFORE killing engine so
    # watchdog sees the flag on its next poll and will not restart. Flag
    # lives in $DATA_DIR/ (default /tmp/openclaw/) to match runtime data dir.
    # 修復 2：kill 引擎前先建立 maintenance flag，watchdog 下次 poll 時看到
    # flag 就不會重啟。flag 放於 $DATA_DIR/（預設 /tmp/openclaw/）與其他 runtime 資料對齊。
    mkdir -p "$DATA_DIR"
    touch "$DATA_DIR/engine_maintenance.flag"
    echo ">>> Created maintenance flag → watchdog will NOT auto-restart"
    echo ">>> Stopping Rust engine (graceful SIGTERM)..."
    if ! engine_running; then
        echo ">>> (no running engine to stop)"
        return 0
    fi
    signal_engine_pids TERM
    local waited=0
    while [[ "$waited" -lt 10 ]]; do
        if ! engine_running; then
            echo ">>> Engine exited cleanly after ${waited}x500ms"
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    echo "WARN: engine still alive after 5s SIGTERM → SIGKILL" >&2
    signal_engine_pids KILL
    sleep 1
}

is_openclaw_api_pid() {
    local pid="$1"
    local cmd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ "$cmd" == *"uvicorn"* && "$cmd" == *"app.main:app"* && "$cmd" == *"control_api_v1"* ]]
}

stop_api() {
    echo ">>> Stopping API server..."
    local pid
    for pid in $(lsof -ti :8000 2>/dev/null || true); do
        if is_openclaw_api_pid "$pid"; then
            kill -TERM "$pid" 2>/dev/null || true
        else
            echo "WARN: skip non-OpenClaw pid on :8000 -> $pid" >&2
        fi
    done
    local waited=0
    while [[ "$waited" -lt 10 ]]; do
        local alive=0
        for pid in $(lsof -ti :8000 2>/dev/null || true); do
            if is_openclaw_api_pid "$pid"; then
                alive=1
                break
            fi
        done
        if [[ "$alive" -eq 0 ]]; then
            echo ">>> API exited cleanly"
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    echo "WARN: API still alive after 5s → SIGKILL" >&2
    for pid in $(lsof -ti :8000 2>/dev/null || true); do
        if is_openclaw_api_pid "$pid"; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
}

case "$SCOPE" in
    --engine-only) stop_engine ;;
    --api-only)    stop_api ;;
    all|"")        stop_engine; stop_api ;;
esac

echo ""
echo "=== Status ==="
echo "Engine maintenance flag: $(ls -la "$DATA_DIR/engine_maintenance.flag" 2>/dev/null || echo 'NONE')"
echo "Remove with: rm \"$DATA_DIR/engine_maintenance.flag\""
echo "Or: bash helper_scripts/restart_all.sh (auto-clears flag)"

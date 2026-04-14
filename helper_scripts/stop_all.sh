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

SCOPE="${1:-all}"
case "$SCOPE" in
    --engine-only|--api-only|all|"") ;;
    *)
        echo "Unknown argument: $SCOPE" >&2
        echo "Usage: bash helper_scripts/stop_all.sh [--engine-only|--api-only]" >&2
        exit 1
        ;;
esac

stop_engine() {
    # Fix 2 (2026-04-14): create maintenance flag BEFORE killing engine so
    # watchdog sees the flag on its next poll and will not restart. Flag
    # lives in /tmp/openclaw/ to match the rest of the runtime data dir.
    # 修復 2：kill 引擎前先建立 maintenance flag，watchdog 下次 poll 時看到
    # flag 就不會重啟。flag 放於 /tmp/openclaw/ 與其他 runtime 資料對齊。
    mkdir -p /tmp/openclaw
    touch /tmp/openclaw/engine_maintenance.flag
    echo ">>> Created maintenance flag → watchdog will NOT auto-restart"
    echo ">>> Stopping Rust engine (graceful SIGTERM)..."
    if ! pgrep -f "openclaw-engine" > /dev/null 2>&1; then
        echo ">>> (no running engine to stop)"
        return 0
    fi
    pkill -TERM -f "openclaw-engine" 2>/dev/null || true
    local waited=0
    while [[ "$waited" -lt 10 ]]; do
        if ! pgrep -f "openclaw-engine" > /dev/null 2>&1; then
            echo ">>> Engine exited cleanly after ${waited}x500ms"
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    echo "WARN: engine still alive after 5s SIGTERM → SIGKILL" >&2
    pkill -KILL -f "openclaw-engine" 2>/dev/null || true
    sleep 1
}

stop_api() {
    echo ">>> Stopping API server..."
    lsof -ti :8000 | xargs kill -TERM 2>/dev/null || true
    local waited=0
    while [[ "$waited" -lt 10 ]]; do
        if ! lsof -ti :8000 > /dev/null 2>&1; then
            echo ">>> API exited cleanly"
            return 0
        fi
        sleep 0.5
        waited=$((waited + 1))
    done
    echo "WARN: API still alive after 5s → SIGKILL" >&2
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
}

case "$SCOPE" in
    --engine-only) stop_engine ;;
    --api-only)    stop_api ;;
    all|"")        stop_engine; stop_api ;;
esac

echo ""
echo "=== Status ==="
echo "Engine maintenance flag: $(ls -la /tmp/openclaw/engine_maintenance.flag 2>/dev/null || echo 'NONE')"
echo "Remove with: rm /tmp/openclaw/engine_maintenance.flag"
echo "Or: bash helper_scripts/restart_all.sh (auto-clears flag)"

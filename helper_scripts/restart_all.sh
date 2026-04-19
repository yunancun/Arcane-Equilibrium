#!/bin/bash
# restart_all.sh — 重啟 Rust 引擎 + API server
# MODULE_NOTE (CN): 一鍵重啟 Rust 引擎 + API server；可選 --rebuild 重建 PyO3 .so
#   **以及** `rust/target/release/openclaw-engine` binary（2026-04-14 FA-PHANTOM-1
#   部署事故後修正 — 原 --rebuild 只重 PyO3 wheel，不動 engine binary，導致
#   部署 engine 修復時仍跑舊 binary）。
# MODULE_NOTE (EN): One-shot restart of Rust engine + API server. Optional --rebuild
#   refreshes BOTH the PyO3 wheel (.so into both venvs) AND the openclaw-engine
#   binary (2026-04-14 FA-PHANTOM-1 deploy incident fix — --rebuild previously
#   only rebuilt the wheel, leaving the engine binary stale).
#
# Usage: bash helper_scripts/restart_all.sh [scope] [--rebuild]
#   scope: --engine-only | --api-only | (none = both)
#   --rebuild: rebuild PyO3 wheel + openclaw-engine binary before starting services
#              (exits if either build fails)
#
# 使用範例：
#   bash helper_scripts/restart_all.sh                     # 重啟引擎+API
#   bash helper_scripts/restart_all.sh --rebuild           # 先 rebuild 再重啟
#   bash helper_scripts/restart_all.sh --api-only          # 只重啟 API
#   bash helper_scripts/restart_all.sh --engine-only --rebuild  # 先 rebuild 再只重啟引擎

set -e
cd "$(dirname "$0")/.."
WORKERS="${OPENCLAW_API_WORKERS:-4}"

# ── Parse flags / 解析旗標 ──
# Accept --rebuild in any position; SCOPE is the remaining positional.
# 接受 --rebuild 出現在任意位置；SCOPE 為剩餘的位置參數。
REBUILD=0
SCOPE="all"
for arg in "$@"; do
    case "$arg" in
        --rebuild)
            REBUILD=1
            ;;
        --engine-only|--api-only)
            SCOPE="$arg"
            ;;
        all|"")
            SCOPE="all"
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: bash helper_scripts/restart_all.sh [--engine-only|--api-only] [--rebuild]" >&2
            exit 1
            ;;
    esac
done

rebuild_pyo3() {
    # Rebuild + dual-write PyO3 .so before starting services.
    # 啟動服務前重建並雙寫 PyO3 .so。
    echo ">>> Rebuilding PyO3 (.so) into all venvs..."
    if ! bash helper_scripts/build_pyo3.sh; then
        echo "ERROR: build_pyo3.sh failed — not starting services" >&2
        exit 2
    fi
}

rebuild_engine_binary() {
    # Rebuild rust/target/release/openclaw-engine.
    # 2026-04-14 FA-PHANTOM-1 deploy incident: --rebuild used to only refresh
    # PyO3 wheel, so engine-code fixes required a separate manual
    # `cargo build --release -p openclaw_engine` or they'd silently run the
    # previous binary. Now bundled into --rebuild so operator intent
    # "refresh everything" actually refreshes everything.
    # 2026-04-14 FA-PHANTOM-1 部署事故：原 --rebuild 只刷 PyO3 wheel，
    # 部署 engine 修復時仍跑舊 binary 而操作者無感。現併入 --rebuild。
    echo ">>> Rebuilding openclaw-engine release binary..."
    if ! cargo build --release -p openclaw_engine --manifest-path rust/Cargo.toml; then
        echo "ERROR: cargo build openclaw_engine failed — not starting services" >&2
        exit 2
    fi
}

rotate_engine_log() {
    # Fix 2 (2026-04-14): preserve engine.log on restart so post-mortem
    # analysis of a crash is possible. The 2026-04-14 incident lost the
    # death logs because restart_all.sh used `>` which truncated the file.
    # Keep last 10 logs under /tmp/openclaw/engine_logs/.
    # 修復 2：重啟時保留 engine.log 以便崩潰事後分析。2026-04-14 事故中死前
    # 日誌全遺失，因為 restart_all.sh 用 `>` 截斷檔案。保留最近 10 份於
    # /tmp/openclaw/engine_logs/。
    local logs_dir="/tmp/openclaw/engine_logs"
    mkdir -p "$logs_dir"
    if [[ -f /tmp/openclaw/engine.log ]] && [[ -s /tmp/openclaw/engine.log ]]; then
        local ts
        ts=$(date +%s)
        mv /tmp/openclaw/engine.log "$logs_dir/engine-${ts}.log"
        echo ">>> Archived previous engine.log → $logs_dir/engine-${ts}.log"
    fi
    # Keep only 10 most recent archived logs.
    # 只保留最新 10 份歸檔日誌。
    local count
    count=$(ls -1 "$logs_dir"/engine-*.log 2>/dev/null | wc -l)
    if [[ "$count" -gt 10 ]]; then
        ls -1t "$logs_dir"/engine-*.log | tail -n +11 | xargs rm -f 2>/dev/null || true
    fi
}

write_restart_sentinel() {
    # PIPELINE-SLOT-1 Phase 1 (2026-04-19): mark this shutdown as operator-
    # initiated ("manual") so the engine, on next boot, clears
    # authorization.json and forces Operator to re-approve Live via GUI.
    # Crashes / watchdog bounces / systemd auto-restart never run this
    # script, so they leave the authorization intact — correct behaviour:
    # engine resumes on already-approved session after a simple death.
    # Atomic write: tmp + mv so a partial write cannot be observed.
    # PIPELINE-SLOT-1 Phase 1：標記本次關機為 operator 主動（"manual"），讓
    # 引擎下次啟動時清空 authorization.json 並強迫 operator 經 GUI 重新批准
    # Live。崩潰 / watchdog / systemd 自動重啟都不跑本 shell，授權留存 —
    # 這是正確行為：引擎只是死了一下，應回到已批准 session。
    # 原子寫入：tmp + mv，避免半寫入狀態被讀到。
    local settings_runtime="${PWD}/settings/runtime"
    mkdir -p "$settings_runtime" 2>/dev/null || true
    if [[ ! -d "$settings_runtime" ]]; then
        echo "WARN: cannot create $settings_runtime — restart sentinel not written" >&2
        return 0
    fi
    local tmp_file
    tmp_file=$(mktemp "${settings_runtime}/.last_shutdown_kind.XXXXXX" 2>/dev/null) || {
        echo "WARN: mktemp failed under $settings_runtime — restart sentinel not written" >&2
        return 0
    }
    printf 'manual' > "$tmp_file"
    if mv "$tmp_file" "${settings_runtime}/last_shutdown_kind" 2>/dev/null; then
        echo ">>> Restart sentinel written: ${settings_runtime}/last_shutdown_kind = manual"
    else
        echo "WARN: atomic rename of restart sentinel failed" >&2
        rm -f "$tmp_file" 2>/dev/null || true
    fi
}

graceful_stop_engine() {
    # Fix 2 (2026-04-14): SIGTERM-first shutdown with 5s graceful window, then
    # escalate to SIGKILL only if the process is still alive. pkill -f was too
    # blunt — if the engine was in the middle of writing paper_state.json it
    # would be killed mid-atomic-rename producing a corrupted tmp file that
    # the watchdog then misreads as "engine dead" → spurious restart loop.
    # 修復 2：SIGTERM 先行 + 5s 優雅窗口，仍存活才 SIGKILL。pkill -f 太粗暴 —
    # 若引擎正在寫 paper_state.json 中途被 kill，會留下損毀的 tmp 檔，watchdog
    # 誤讀為「引擎死亡」→ 虛假重啟循環。
    #
    # PIPELINE-SLOT-1 Phase 1: write the restart sentinel BEFORE any SIGTERM so
    # a slow operator-kill cannot race the engine restart. Written even when
    # no engine is running (fresh install / post-crash bounce) because
    # operator intent on running this script is still "Manual".
    # PIPELINE-SLOT-1 Phase 1：SIGTERM 前先寫 sentinel，避免 kill 與 engine 重啟
    # 競態。即使沒有在跑的 engine 也要寫（初次安裝 / 崩潰後重啟都算 Manual 意圖）。
    write_restart_sentinel
    if ! pgrep -f "openclaw-engine" > /dev/null 2>&1; then
        echo ">>> (no running engine to stop)"
        return 0
    fi
    echo ">>> Sending SIGTERM to engine (graceful shutdown)..."
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
    echo "WARN: engine still alive after 5s SIGTERM → escalating to SIGKILL" >&2
    pkill -KILL -f "openclaw-engine" 2>/dev/null || true
    sleep 1
}

restart_engine() {
    echo ">>> Stopping Rust engine..."
    graceful_stop_engine
    rotate_engine_log
    # Clear maintenance flag on explicit restart — operator wants it running.
    # 明確重啟時清除 maintenance flag — operator 意圖是讓引擎跑起來。
    rm -f /tmp/openclaw/engine_maintenance.flag 2>/dev/null || true
    echo ">>> Starting Rust engine..."
    # Load PG password from secrets (cross-platform: no hardcoded credentials)
    local pg_pass
    pg_pass=$(grep POSTGRES_PASSWORD "$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
    # Load IPC HMAC secret for Live pipeline authentication
    # 載入 IPC HMAC 密鑰（Live 管線 HMAC 認證必需）
    local ipc_secret
    ipc_secret=$(cat "$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt" 2>/dev/null || echo "")
    OPENCLAW_DATA_DIR=/tmp/openclaw OPENCLAW_CANARY_MODE=1 \
        OPENCLAW_DATABASE_URL="postgresql://redacted@127.0.0.1:5432/trading_ai" \
        OPENCLAW_IPC_SECRET="${ipc_secret}" \
        nohup rust/target/release/openclaw-engine > /tmp/openclaw/engine.log 2>&1 &
    echo "    PID: $!"
}

restart_api() {
    echo ">>> Stopping API server..."
    lsof -ti :8000 | xargs kill -9 2>/dev/null || true
    sleep 2
    echo ">>> Starting API server ($WORKERS workers)..."
    # Pass DB URL to API server for metrics DB fallback (fills query).
    # 傳遞 DB URL 給 API 以支持指標 DB 降級（成交查詢）。
    local pg_pass
    pg_pass=$(grep POSTGRES_PASSWORD "$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
    cd program_code/exchange_connectors/bybit_connector/control_api_v1
    # Load IPC HMAC secret for API-side HMAC verification
    # 載入 IPC HMAC 密鑰（API 端 HMAC 驗證）
    local ipc_secret
    ipc_secret=$(cat "$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt" 2>/dev/null || echo "")
    OPENCLAW_DATABASE_URL="postgresql://redacted@127.0.0.1:5432/trading_ai" \
        OPENCLAW_IPC_SECRET="${ipc_secret}" \
        .venv/bin/python3 .venv/bin/uvicorn app.main:app \
        --host 0.0.0.0 --port 8000 --workers "$WORKERS" &
    cd - > /dev/null
}

ensure_docker_network() {
    # Ensure Grafana can reach PG (different Docker networks by default)
    # 確保 Grafana 能訪問 PG（默認在不同 Docker 網絡）
    if docker inspect trading_postgres >/dev/null 2>&1 && docker inspect trading_grafana >/dev/null 2>&1; then
        docker network connect basic_system_services_default trading_postgres 2>/dev/null || true
    fi
}

wait_and_verify() {
    ensure_docker_network
    echo ">>> Waiting 10s for startup..."
    sleep 10
    echo "=== Engine ==="
    python3 helper_scripts/canary/engine_watchdog.py \
        --data-dir /tmp/openclaw --stale-threshold 45 --grace-period 120 --status 2>&1 || true
    echo "=== Ticks ==="
    python3 -c "import json;s=json.load(open('/tmp/openclaw/pipeline_snapshot.json'));print('ticks:', s['stats']['total_ticks'], 'fills:', s['stats']['total_fills'], 'paused:', s.get('paper_paused'))" 2>&1 || true
}

# ── Pre-flight rebuild (if requested) / 啟動前重建（如有請求） ──
# Must run BEFORE any service start — rebuild failure aborts the whole restart.
# 必須在啟動任何服務前執行——rebuild 失敗則整個 restart 中止。
# Order: engine binary first (longer compile), then PyO3 wheel — if either
# fails, exit before killing the running services.
# 順序：先編 engine binary（較慢），再編 PyO3 wheel — 任一失敗則在 kill
# 現行服務之前退出，避免「killed but nothing to start」的窗口。
if [[ "$REBUILD" -eq 1 ]]; then
    if [[ "$SCOPE" == "all" || "$SCOPE" == "--engine-only" ]]; then
        rebuild_engine_binary
    fi
    rebuild_pyo3
fi

case "$SCOPE" in
    --engine-only) restart_engine; wait_and_verify ;;
    --api-only)    restart_api; sleep 3; echo "API server restarted" ;;
    all)           restart_engine; restart_api; wait_and_verify ;;
esac

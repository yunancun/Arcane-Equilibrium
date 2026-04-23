#!/bin/bash
# restart_all.sh — 重啟 Rust 引擎 + API server
# MODULE_NOTE (CN): 一鍵重啟 Rust 引擎 + API server；可選 --rebuild 重建
#   `rust/target/release/openclaw-engine` binary（PYO3-ELIMINATE-1 Phase 3 後，
#   PyO3 wheel 已消失，--rebuild 只剩 engine binary）。
# MODULE_NOTE (EN): One-shot restart of Rust engine + API server. Optional --rebuild
#   refreshes the openclaw-engine binary (PyO3-ELIMINATE-1 Phase 3 removed the
#   PyO3 cdylib — --rebuild is now a single-artifact cargo build).
#
# Usage: bash helper_scripts/restart_all.sh [scope] [--rebuild]
#   scope: --engine-only | --api-only | (none = both)
#   --rebuild: rebuild openclaw-engine binary before starting services
#              (exits if build fails)
#
# 使用範例：
#   bash helper_scripts/restart_all.sh                     # 重啟引擎+API
#   bash helper_scripts/restart_all.sh --rebuild           # 先 rebuild 再重啟
#   bash helper_scripts/restart_all.sh --api-only          # 只重啟 API
#   bash helper_scripts/restart_all.sh --engine-only --rebuild  # 先 rebuild 再只重啟引擎

set -e
cd "$(dirname "$0")/.."
WORKERS="${OPENCLAW_API_WORKERS:-4}"
# Runtime data dir (env var for Mac compatibility).
# Mac dev recommendation: export OPENCLAW_DATA_DIR="$HOME/.openclaw_runtime"
# Runtime 資料目錄（支援 Mac env var 部署）。
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
# Secrets root (env var for Mac / non-HOME deployment).
# Mac dev recommendation: export OPENCLAW_SECRETS_ROOT="$HOME/.openclaw_secrets"
# Secrets 根目錄（支援 Mac / 非 $HOME 路徑部署）。
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
# Postgres port (Linux native on 5432; Mac dev's dockerised PG on 15432).
# Set OPENCLAW_PG_PORT=15432 on Mac dev or any host that dockerises PG to
# avoid colliding with a system / Homebrew Postgres on 5432.
# Postgres 埠（Linux 原生 5432；Mac dev dockerised PG 在 15432）。
# Mac dev 或任何 dockerised PG 的主機請 export OPENCLAW_PG_PORT=15432。
PG_PORT="${OPENCLAW_PG_PORT:-5432}"
# API venv path. Relative paths resolve against program_code/.../control_api_v1
# (where the script cd's before invoking uvicorn). Absolute paths let Mac dev
# point at a shared venv outside the per-service tree (e.g. srv/venvs/mac_dev).
# API venv 路徑。相對路徑以 control_api_v1 為基準（script 會 cd 進去再跑 uvicorn）。
# 絕對路徑讓 Mac dev 指向共用 venv（例：srv/venvs/mac_dev）。
API_VENV="${OPENCLAW_API_VENV:-.venv}"

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

rebuild_engine_binary() {
    # Rebuild rust/target/release/openclaw-engine.
    # 2026-04-14 FA-PHANTOM-1 deploy incident: --rebuild used to only refresh
    # PyO3 wheel, so engine-code fixes required a separate manual
    # `cargo build --release -p openclaw_engine` or they'd silently run the
    # previous binary. PYO3-ELIMINATE-1 Phase 3 removed the PyO3 wheel, so
    # --rebuild now refreshes only this binary — still the right "refresh
    # everything" behaviour because the binary is the only build artifact.
    # 2026-04-14 FA-PHANTOM-1 部署事故：原 --rebuild 只刷 PyO3 wheel，
    # 部署 engine 修復時仍跑舊 binary 而操作者無感。PYO3-ELIMINATE-1 Phase 3
    # 移除 PyO3 wheel 後，--rebuild 只需重建此 binary（唯一建構產物）。
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
    # Keep last 10 logs under $DATA_DIR/engine_logs/.
    # 修復 2：重啟時保留 engine.log 以便崩潰事後分析。2026-04-14 事故中死前
    # 日誌全遺失，因為 restart_all.sh 用 `>` 截斷檔案。保留最近 10 份於
    # $DATA_DIR/engine_logs/（預設 /tmp/openclaw/engine_logs/）。
    local logs_dir="$DATA_DIR/engine_logs"
    mkdir -p "$logs_dir"
    if [[ -f "$DATA_DIR/engine.log" ]] && [[ -s "$DATA_DIR/engine.log" ]]; then
        local ts
        ts=$(date +%s)
        mv "$DATA_DIR/engine.log" "$logs_dir/engine-${ts}.log"
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
    rm -f "$DATA_DIR/engine_maintenance.flag" 2>/dev/null || true
    echo ">>> Starting Rust engine..."
    # Load PG password from secrets (cross-platform: no hardcoded credentials)
    local pg_pass
    pg_pass=$(grep POSTGRES_PASSWORD "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
    # Load IPC HMAC secret for Live pipeline authentication
    # 載入 IPC HMAC 密鑰（Live 管線 HMAC 認證必需）
    local ipc_secret
    ipc_secret=$(cat "$SECRETS_ROOT/environment_files/ipc_secret.txt" 2>/dev/null || echo "")
    OPENCLAW_DATA_DIR="$DATA_DIR" OPENCLAW_CANARY_MODE=1 \
        OPENCLAW_DATABASE_URL="postgresql://redacted@127.0.0.1:${PG_PORT}/trading_ai" \
        OPENCLAW_IPC_SECRET="${ipc_secret}" \
        nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 &
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
    pg_pass=$(grep POSTGRES_PASSWORD "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2-)
    cd program_code/exchange_connectors/bybit_connector/control_api_v1
    # Load IPC HMAC secret for API-side HMAC verification
    # 載入 IPC HMAC 密鑰（API 端 HMAC 驗證）
    local ipc_secret
    ipc_secret=$(cat "$SECRETS_ROOT/environment_files/ipc_secret.txt" 2>/dev/null || echo "")
    # RESTART-ALL-UVICORN-LOG-1 (2026-04-23): redirect uvicorn stdout/stderr to
    # $DATA_DIR/api.log with nohup, mirroring engine startup pattern (L200).
    # Previously uvicorn had no redirect, so api.log stayed frozen at the
    # 2026-04-19 PIPELINE-SLOT-1 Phase 1 restart — any API error / traceback
    # was lost to the shell that launched restart_all.sh.
    # RESTART-ALL-UVICORN-LOG-1：uvicorn 加 nohup + stdout/stderr 重定向到
    # $DATA_DIR/api.log，與 engine 啟動模式（L200）對齊。原本 uvicorn 無
    # redirect，api.log 自 2026-04-19 PIPELINE-SLOT-1 Phase 1 重啟後不再更新，
    # 任何 API 錯誤 / traceback 隨啟動 shell 散失。
    OPENCLAW_DATABASE_URL="postgresql://redacted@127.0.0.1:${PG_PORT}/trading_ai" \
        OPENCLAW_IPC_SECRET="${ipc_secret}" \
        nohup "$API_VENV/bin/python3" "$API_VENV/bin/uvicorn" app.main:app \
        --host 0.0.0.0 --port 8000 --workers "$WORKERS" \
        > "$DATA_DIR/api.log" 2>&1 &
    echo "    PID: $!"
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
        --data-dir "$DATA_DIR" --stale-threshold 45 --grace-period 120 --status 2>&1 || true
    echo "=== Ticks ==="
    python3 -c "import json;s=json.load(open('$DATA_DIR/pipeline_snapshot.json'));print('ticks:', s['stats']['total_ticks'], 'fills:', s['stats']['total_fills'], 'paused:', s.get('paper_paused'))" 2>&1 || true
}

# ── Pre-flight rebuild (if requested) / 啟動前重建（如有請求） ──
# Must run BEFORE any service start — rebuild failure aborts the whole restart.
# 必須在啟動任何服務前執行——rebuild 失敗則整個 restart 中止。
# PYO3-ELIMINATE-1 Phase 3: PyO3 wheel rebuild removed — only engine binary.
# API server runs on pure Python source; no build step needed.
# PYO3-ELIMINATE-1 Phase 3：已移除 PyO3 wheel 重建；API 純 Python 無需 build。
if [[ "$REBUILD" -eq 1 ]]; then
    if [[ "$SCOPE" == "all" || "$SCOPE" == "--engine-only" ]]; then
        rebuild_engine_binary
    fi
fi

case "$SCOPE" in
    --engine-only) restart_engine; wait_and_verify ;;
    --api-only)    restart_api; sleep 3; echo "API server restarted" ;;
    all)           restart_engine; restart_api; wait_and_verify ;;
esac

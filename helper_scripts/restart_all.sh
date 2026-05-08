#!/bin/bash
# restart_all.sh — 重啟 Rust 引擎 + API server
# MODULE_NOTE (CN): 一鍵重啟 Rust 引擎 + API server；可選 --rebuild 重建
#   `rust/target/release/openclaw-engine` binary（PYO3-ELIMINATE-1 Phase 3 後，
#   PyO3 wheel 已消失，--rebuild 只剩 engine binary）。
# MODULE_NOTE (EN): One-shot restart of Rust engine + API server. Optional --rebuild
#   refreshes the openclaw-engine binary (PyO3-ELIMINATE-1 Phase 3 removed the
#   PyO3 cdylib — --rebuild is now a single-artifact cargo build).
#
# Usage: bash helper_scripts/restart_all.sh [scope] [--rebuild] [--keep-auth]
#   scope: --engine-only | --api-only | (none = both)
#   --rebuild: rebuild openclaw-engine binary before starting services
#              (exits if build fails)
#   --keep-auth: skip writing the `last_shutdown_kind=manual` sentinel so the
#              engine on next boot does NOT clear `authorization.json`. Use for
#              planned deploys / hotfixes where operator has already approved
#              live and does not want to re-approve after every restart.
#              Default behaviour (sentinel written) is per CLAUDE.md §四 Gate
#              #5 design: operator-initiated restart = security event = force
#              re-approve. `--keep-auth` is a deliberate ergonomic opt-out.
#              Crash / watchdog / systemd auto-restart paths never run this
#              shell, so they always preserve auth regardless of this flag.
#
# 使用範例：
#   bash helper_scripts/restart_all.sh                     # 重啟引擎+API
#   bash helper_scripts/restart_all.sh --rebuild           # 先 rebuild 再重啟（清 auth）
#   bash helper_scripts/restart_all.sh --rebuild --keep-auth  # rebuild 不清 auth（部署常用）
#   bash helper_scripts/restart_all.sh --api-only          # 只重啟 API
#   bash helper_scripts/restart_all.sh --engine-only --rebuild  # rebuild 只重啟引擎

set -e
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd -P)"
cd "$REPO_ROOT"
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
RUNTIME_SECRET_DIR="$DATA_DIR/runtime_secrets"
OPENCLAW_DATABASE_URL_FILE="$RUNTIME_SECRET_DIR/openclaw_database_url"
OPENCLAW_IPC_SECRET_FILE="$SECRETS_ROOT/environment_files/ipc_secret.txt"
ENGINE_BIN_REL="rust/target/release/openclaw-engine"
ENGINE_BIN_ABS="$REPO_ROOT/$ENGINE_BIN_REL"
API_WORKDIR="$REPO_ROOT/program_code/exchange_connectors/bybit_connector/control_api_v1"

prepare_runtime_secret_files() {
    mkdir -p "$RUNTIME_SECRET_DIR"
    chmod 700 "$RUNTIME_SECRET_DIR" 2>/dev/null || true

    local pg_pass
    pg_pass=$(grep '^POSTGRES_PASSWORD=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2- || true)
    if [ -z "$pg_pass" ]; then
        echo "ERROR: POSTGRES_PASSWORD missing in $SECRETS_ROOT/environment_files/basic_system_services.env" >&2
        exit 1
    fi
    printf 'postgresql://trading_admin:%s@127.0.0.1:%s/trading_ai\n' "$pg_pass" "$PG_PORT" > "$OPENCLAW_DATABASE_URL_FILE"
    chmod 600 "$OPENCLAW_DATABASE_URL_FILE" 2>/dev/null || true
    if [ -f "$OPENCLAW_IPC_SECRET_FILE" ]; then
        chmod 600 "$OPENCLAW_IPC_SECRET_FILE" 2>/dev/null || true
    fi
}

is_openclaw_api_pid() {
    local pid="$1"
    local cmd cwd
    cmd="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    cwd="$(readlink "/proc/$pid/cwd" 2>/dev/null || true)"

    if [[ "$cmd" == *"uvicorn"* && "$cmd" == *"app.main:app"* ]]; then
        [[ "$cmd" == *"control_api_v1"* || "$cwd" == "$API_WORKDIR" ]]
        return
    fi

    [[ "$cwd" == "$API_WORKDIR" && "$cmd" == *"python"* && "$cmd" == *"multiprocessing-fork"* ]]
}

stop_api_safe() {
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
        [[ "$alive" -eq 0 ]] && return 0
        sleep 0.5
        waited=$((waited + 1))
    done
    for pid in $(lsof -ti :8000 2>/dev/null || true); do
        if is_openclaw_api_pid "$pid"; then
            kill -KILL "$pid" 2>/dev/null || true
        fi
    done
}

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

# ── Parse flags / 解析旗標 ──
# Accept --rebuild in any position; SCOPE is the remaining positional.
# 接受 --rebuild 出現在任意位置；SCOPE 為剩餘的位置參數。
REBUILD=0
KEEP_AUTH=0
SCOPE="all"
for arg in "$@"; do
    case "$arg" in
        --rebuild)
            REBUILD=1
            ;;
        --keep-auth)
            # EDGE-DIAG-2-FUP (2026-04-28): bypass the manual-restart auth wipe
            # so planned deploys / hotfixes don't force operator to re-approve
            # live every time. Default is still WIPE (CLAUDE.md §四 Gate #5).
            # EDGE-DIAG-2-FUP（2026-04-28）：跳過 manual-restart 的 auth 清除，
            # 讓計劃性部署 / hotfix 不再強迫每次重啟都重批 live。
            # 預設仍為清除（CLAUDE.md §四 Gate #5）。
            KEEP_AUTH=1
            ;;
        --engine-only|--api-only)
            SCOPE="$arg"
            ;;
        all|"")
            SCOPE="all"
            ;;
        *)
            echo "Unknown argument: $arg" >&2
            echo "Usage: bash helper_scripts/restart_all.sh [--engine-only|--api-only] [--rebuild] [--keep-auth]" >&2
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
    #
    # EDGE-DIAG-2-FUP (2026-04-28): operator may pass --keep-auth to skip the
    # sentinel write for planned deploys / hotfixes. Default unchanged.
    # EDGE-DIAG-2-FUP（2026-04-28）：--keep-auth 跳過寫入；預設行為不變。
    if [[ "$KEEP_AUTH" -eq 1 ]]; then
        echo ">>> --keep-auth: skipping sentinel write (authorization.json will survive this restart)"
        # Defensive: if a stale `last_shutdown_kind=manual` sentinel exists
        # from a previous restart that didn't use --keep-auth, the engine on
        # next boot would still consume it and wipe auth. Pre-emptively
        # remove any pre-existing sentinel so --keep-auth's promise holds.
        # 防禦性：先前 restart 留下的 manual sentinel 仍會被新 engine 讀並擦
        # auth；--keep-auth 必須先清掉殘留 sentinel 才能兌現「auth 保留」承諾。
        rm -f "${PWD}/settings/runtime/last_shutdown_kind" 2>/dev/null || true
        return 0
    fi
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
    # escalate to SIGKILL only if the process is still alive. Pattern kills were too
    # blunt — if the engine was in the middle of writing paper_state.json it
    # would be killed mid-atomic-rename producing a corrupted tmp file that
    # the watchdog then misreads as "engine dead" → spurious restart loop.
    # 修復 2：SIGTERM 先行 + 5s 優雅窗口，仍存活才 SIGKILL。pattern kill 太粗暴 —
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
    if ! engine_running; then
        echo ">>> (no running engine to stop)"
        return 0
    fi
    echo ">>> Sending SIGTERM to engine (graceful shutdown)..."
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
    echo "WARN: engine still alive after 5s SIGTERM → escalating to SIGKILL" >&2
    signal_engine_pids KILL
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
    # Phase 2 auto-migrate opt-in (V023 postmortem 2026-04-24): pass through
    # OPENCLAW_AUTO_MIGRATE + OPENCLAW_BASE_DIR so the engine's migration
    # runner can locate sql/migrations/ and honor the env toggle. Defaults
    # preserve legacy behavior (flag unset → runner disabled → 0 impact).
    # Phase 2 自動遷移 opt-in：從 env file 取 OPENCLAW_AUTO_MIGRATE 與 base dir
    # 傳給引擎，讓 runner 能找到 sql/migrations/ 並遵守 opt-in 旗標；預設不
    # 設則維持舊行為（runner 關閉，零影響）。
    local auto_migrate
    auto_migrate=$(grep '^OPENCLAW_AUTO_MIGRATE=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2- || echo "")
    # PAPER-ENABLE-ENV-1 (2026-05-06): make paper runtime opt-in durable across
    # restart_all invocations by reading OPENCLAW_ENABLE_PAPER from the operator
    # env first, then the secrets env file. A one-shot
    # `OPENCLAW_ENABLE_PAPER=1 bash restart_all.sh` still wins, while Linux
    # runtime can persist the choice in basic_system_services.env.
    # PAPER-ENABLE-ENV-1：先讀 operator env，再讀 secrets env，使 paper runtime
    # 啟用狀態可跨 restart_all 持久保存；臨時命令列 override 仍優先。
    local enable_paper
    enable_paper="${OPENCLAW_ENABLE_PAPER:-$(grep '^OPENCLAW_ENABLE_PAPER=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2- || echo "")}"
    # W-B Agent Decision Spine runtime rollout mode. Operator env wins for
    # one-shot tests; otherwise persist the runtime choice in the secrets env
    # file so a later plain restart_all keeps the same shadow/canary/primary
    # setting instead of silently falling back to disabled.
    local agent_spine_runtime_mode
    agent_spine_runtime_mode="${OPENCLAW_AGENT_SPINE_RUNTIME_MODE:-$(grep '^OPENCLAW_AGENT_SPINE_RUNTIME_MODE=' "$SECRETS_ROOT/environment_files/basic_system_services.env" 2>/dev/null | cut -d= -f2- || echo "")}"
    local base_dir
    base_dir="${OPENCLAW_BASE_DIR:-$(pwd)}"
    OPENCLAW_DATA_DIR="$DATA_DIR" OPENCLAW_CANARY_MODE=1 \
        OPENCLAW_DATABASE_URL_FILE="$OPENCLAW_DATABASE_URL_FILE" \
        OPENCLAW_IPC_SECRET_FILE="$OPENCLAW_IPC_SECRET_FILE" \
        OPENCLAW_AUTO_MIGRATE="${auto_migrate}" \
        OPENCLAW_ENABLE_PAPER="${enable_paper}" \
        OPENCLAW_AGENT_SPINE_RUNTIME_MODE="${agent_spine_runtime_mode}" \
        OPENCLAW_BASE_DIR="${base_dir}" \
        nohup rust/target/release/openclaw-engine > "$DATA_DIR/engine.log" 2>&1 &
    echo "    PID: $!"
}

restart_api() {
    echo ">>> Stopping API server..."
    stop_api_safe
    echo ">>> Starting API server ($WORKERS workers)..."
    cd "$API_WORKDIR"
    # RESTART-ALL-UVICORN-LOG-1 (2026-04-23): redirect uvicorn stdout/stderr to
    # $DATA_DIR/api.log with nohup, mirroring engine startup pattern (L200).
    # Previously uvicorn had no redirect, so api.log stayed frozen at the
    # 2026-04-19 PIPELINE-SLOT-1 Phase 1 restart — any API error / traceback
    # was lost to the shell that launched restart_all.sh.
    # RESTART-ALL-UVICORN-LOG-1：uvicorn 加 nohup + stdout/stderr 重定向到
    # $DATA_DIR/api.log，與 engine 啟動模式（L200）對齊。原本 uvicorn 無
    # redirect，api.log 自 2026-04-19 PIPELINE-SLOT-1 Phase 1 重啟後不再更新，
    # 任何 API 錯誤 / traceback 隨啟動 shell 散失。
    #
    # REF-20 Sprint A R1-T2 (2026-05-04): explicitly export OPENCLAW_BASE_DIR
    # + OPENCLAW_DATA_DIR before spawning uvicorn so the API process inherits
    # the resolved repo root + runtime directory regardless of caller env.
    # The legacy implementation relied on `nohup` shell-inherit semantics,
    # which silently broke when restart_all.sh was wrapped by systemd /
    # launchd / pm2 (those re-pack env and may strip vars not in their unit
    # spec). Without OPENCLAW_BASE_DIR, replay_routes resolve_replay_runner_bin
    # falls back to PATH-relative "replay_runner" → 503 binary_not_found
    # despite the binary existing under rust/target/release/. This export
    # mirrors restart_engine() (line 347-352) which already wires both vars.
    # REF-20 Sprint A R1-T2（2026-05-04）：在 spawn uvicorn 前顯式 export
    # OPENCLAW_BASE_DIR + OPENCLAW_DATA_DIR，使 API process 不論 caller env
    # 都能繼承 repo root + runtime dir。舊實作依賴 nohup shell-inherit 語意，
    # systemd / launchd / pm2 包裹 restart_all.sh 時會重新打包 env 而漏掉這
    # 兩個 var，導致 resolve_replay_runner_bin fall back 到 PATH 相對的
    # "replay_runner" → 503 binary_not_found（即使 binary 真實存在於
    # rust/target/release/）。本 export 對齊 restart_engine() (line 347-352)
    # 既有的 env 接線。
    local base_dir
    base_dir="${OPENCLAW_BASE_DIR:-$REPO_ROOT}"
    # REF-20 Sprint A R3 round 4 infra fix (2026-05-04): inject the openclaw-engine
    # binary SHA-256 into the API process env so /api/v1/replay/experiments/register
    # can satisfy the M-3 fail-closed gate (linux_trade_core runtime requires
    # OPENCLAW_ENGINE_BINARY_SHA per V049 chk_replay_experiments_engine_sha_linux).
    # Without this env, the register handler returns 503 with reason_code
    # ``replay_engine_binary_sha_not_provisioned``, which silently blocks every
    # smoke E2E even though the binary itself is healthy on disk. Empty string
    # fallback is acceptable: the register handler's M-3 branch will surface a
    # clear 503 with the same reason_code rather than a confusing AttributeError,
    # so operator can see the gap immediately. The sha computation is deliberately
    # portable — sha256sum (Linux) is preferred, shasum -a 256 (Mac) is the
    # fallback so this script remains cross-platform per CLAUDE.md §七 ★★.
    # REF-20 Sprint A R3 round 4 infra fix（2026-05-04）：注入 openclaw-engine
    # 二進制 SHA-256 至 API process env，使 /api/v1/replay/experiments/register
    # 能通過 M-3 fail-closed 門控（linux_trade_core runtime 強制要求
    # OPENCLAW_ENGINE_BINARY_SHA per V049 chk_replay_experiments_engine_sha_linux）。
    # 沒有此 env 時 register handler 回 503 reason_code
    # ``replay_engine_binary_sha_not_provisioned``，靜默阻塞每次 smoke E2E（即使
    # binary 本身在磁碟上健康）。空字串 fallback 可接受：register handler M-3
    # 分支會回明確 503 + 相同 reason_code，不會炸 AttributeError，operator 立即
    # 看到差異。SHA 計算刻意 portable — sha256sum（Linux）優先，shasum -a 256
    # （Mac）為 fallback，確保此 script 跨平台符合 CLAUDE.md §七 ★★。
    local engine_sha
    if [ -f "$ENGINE_BIN_ABS" ]; then
        engine_sha="$( (sha256sum "$ENGINE_BIN_ABS" 2>/dev/null || shasum -a 256 "$ENGINE_BIN_ABS" 2>/dev/null) | cut -d ' ' -f 1)"
    else
        engine_sha=""
    fi
    # REF-20 Sprint A R3 Round 6 P2-A-NEW (2026-05-05): inject default
    # replay fixture path env so /api/v1/replay/experiments/register payload
    # (R4 UI) and CLI smoke runs can omit explicit fixture_uri and fall
    # through to the in-tree synthetic fixture used by Sprint A smoke
    # E2E. Production operator OVERRIDES with absolute path or supplies
    # the fixture via register payload's manifest_jsonb.fixture_uri (the
    # latter preempts this env in route_helpers.build_default_manifest_payload's
    # fallback chain). Empty string fallback is acceptable when the
    # in-tree fixture is absent (older deploy snapshot) — the register
    # handler's body validator will surface 400 fixture_uri_missing instead
    # of leaking a confusing path-not-found from the runner.
    # REF-20 Sprint A R3 Round 6 P2-A-NEW（2026-05-05）：注入 default replay
    # fixture path env，使 /experiments/register payload（R4 UI）與 CLI smoke
    # 可省略 fixture_uri 走 in-tree synthetic fixture。Production operator
    # 必 override 或於 register payload 顯式提供（後者優先）。空字串 fallback
    # 可接受（舊 deploy snapshot 沒此 fixture 時，register 會 400 回明確
    # fixture_uri_missing，不會散失）。
    local replay_fixture_default
    replay_fixture_default="$base_dir/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/synthetic_btcusdt.json"
    if [ ! -f "$replay_fixture_default" ]; then
        replay_fixture_default=""
    fi

    # REF-20 Sprint A R3 Round 8 P0-NEW-2 (2026-05-05): inject signing key file
    # env so /run handler write_manifest_fixture can pass _resolve_manifest_signing_key
    # step 1 (env override). Reuses in-tree S3 dev key.hex; live profile blocks
    # this override per Round 7 FINDING-1, so production must rely on
    # $OPENCLAW_SECRETS_DIR/<env>/replay_signing_key (R2-T3 secrets dir path).
    # REF-20 Sprint A R3 Round 8 P0-NEW-2（2026-05-05）：注入 signing key file
    # env 使 /run handler write_manifest_fixture 通過 _resolve_manifest_signing_key
    # step 1（env override）。重用 in-tree S3 dev key.hex；live profile 由
    # Round 7 FINDING-1 阻擋此 override，production 必走 $OPENCLAW_SECRETS_DIR/
    # <env>/replay_signing_key（R2-T3 secrets dir path）。
    local replay_signing_key_file
    replay_signing_key_file="$base_dir/rust/openclaw_engine/tests/fixtures/replay_runner_e2e/key.hex"
    if [ ! -f "$replay_signing_key_file" ]; then
        replay_signing_key_file=""
    fi

    OPENCLAW_BASE_DIR="$base_dir" \
        OPENCLAW_DATA_DIR="$DATA_DIR" \
        OPENCLAW_DATABASE_URL_FILE="$OPENCLAW_DATABASE_URL_FILE" \
        OPENCLAW_IPC_SECRET_FILE="$OPENCLAW_IPC_SECRET_FILE" \
        OPENCLAW_ENGINE_BINARY_SHA="$engine_sha" \
        OPENCLAW_REPLAY_FIXTURE_DEFAULT="$replay_fixture_default" \
        OPENCLAW_REPLAY_SIGNING_KEY_FILE="$replay_signing_key_file" \
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

prepare_runtime_secret_files

case "$SCOPE" in
    --engine-only) restart_engine; wait_and_verify ;;
    --api-only)    restart_api; sleep 3; echo "API server restarted" ;;
    all)           restart_engine; restart_api; wait_and_verify ;;
esac

#!/bin/bash
# clean_restart.sh — 乾淨重啟腳本
#
# MODULE_NOTE (EN): Full clean-reset of the trading stack. Stops engine+API,
#   flattens every exchange position (demo + optional live) via the httpx
#   BybitClient, archives runtime state + damaged DB tables, verifies the Rust
#   binary is current (rebuilds if source is newer), then restarts engine +
#   API and validates via watchdog. Re-opens Paper/Demo/Live engines cleanly.
# MODULE_NOTE (中): 交易棧完整乾淨重設。停止引擎+API，透過 httpx BybitClient
#   清空所有交易所持倉（demo + 可選 live），歸檔運行期狀態 + 污染 DB 表，
#   驗證 Rust 二進制為最新（若源碼更新則重編），重啟引擎+API 並以 watchdog
#   驗證。乾淨地重新啟動 Paper/Demo/Live 三引擎。
#
# Usage:
#   bash helper_scripts/clean_restart.sh [OPTIONS]
#
# Options:
#   --yes                 Skip all interactive confirmations
#   --mark-damaged        Archive DB fills/intents/orders/risk_verdicts to
#                         damaged_<ts> tables and truncate the originals.
#                         Without this flag, DB tables are left untouched.
#   --include-live        Also flatten mainnet positions (requires
#                         OPENCLAW_ALLOW_MAINNET=1 and live credentials)
#   --skip-build-check    Skip source-vs-binary freshness comparison
#   --skip-flatten        Skip exchange flatten (use when positions already 0)
#   --help                Show this help and exit

set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

# ── Defaults ──────────────────────────────────────────────────────────────
YES=0
MARK_DAMAGED=0
INCLUDE_LIVE=0
SKIP_BUILD_CHECK=0
SKIP_FLATTEN=0

# ── Parse args ────────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --yes) YES=1 ;;
        --mark-damaged) MARK_DAMAGED=1 ;;
        --include-live) INCLUDE_LIVE=1 ;;
        --skip-build-check) SKIP_BUILD_CHECK=1 ;;
        --skip-flatten) SKIP_FLATTEN=1 ;;
        --help|-h)
            sed -n '2,/^set -euo/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0 ;;
        *) echo "[ERR] unknown arg: $arg" >&2; exit 1 ;;
    esac
done

TS="$(date +%Y%m%d_%H%M%S)"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
# Secrets root + archive dir (env vars for Mac / non-HOME deployment).
# Mac dev recommendation: export OPENCLAW_SECRETS_ROOT / OPENCLAW_ARCHIVE_DIR.
# Secrets 根 + 歸檔目錄（支援 Mac / 非 $HOME 路徑部署）。
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ARCHIVE_DIR="${OPENCLAW_ARCHIVE_DIR:-$HOME/BybitOpenClaw/archive}"
ARCHIVE_ROOT="$ARCHIVE_DIR/damaged_${TS}"
BIN="rust/target/release/openclaw-engine"
API_VENV="program_code/exchange_connectors/bybit_connector/control_api_v1/.venv"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"
IPC_SECRET_FILE="$SECRETS_ROOT/environment_files/ipc_secret.txt"

# Colors for readability
C_HDR='\033[1;36m'  # cyan bold
C_OK='\033[1;32m'   # green bold
C_WARN='\033[1;33m' # yellow bold
C_ERR='\033[1;31m'  # red bold
C_END='\033[0m'

hdr()  { echo -e "${C_HDR}══ $* ══${C_END}"; }
ok()   { echo -e "${C_OK}✓${C_END} $*"; }
warn() { echo -e "${C_WARN}⚠${C_END} $*"; }
err()  { echo -e "${C_ERR}✗${C_END} $*" >&2; }

confirm() {
    [ "$YES" -eq 1 ] && return 0
    read -r -p "$1 [yes/NO]: " r
    # Portable lowercase match (macOS bash 3.2 has no ${var,,}).
    # 可攜式大小寫匹配（macOS bash 3.2 不支援 ${var,,}）。
    case "$r" in [Yy][Ee][Ss]) return 0 ;; *) return 1 ;; esac
}

# ── Step 1: Pre-flight report ─────────────────────────────────────────────
hdr "Step 1/7 — Pre-flight report"

if [ ! -f "$SECRETS_ENV" ]; then
    err "secrets env file not found: $SECRETS_ENV"
    exit 1
fi

PG_PASS="$(grep POSTGRES_PASSWORD "$SECRETS_ENV" | cut -d= -f2-)"
IPC_SECRET="$(cat "$IPC_SECRET_FILE" 2>/dev/null || echo '')"

echo "  data_dir:       $DATA_DIR"
echo "  archive_target: $ARCHIVE_ROOT"
echo "  timestamp:      $TS"
echo "  options:        yes=$YES mark_damaged=$MARK_DAMAGED include_live=$INCLUDE_LIVE"
echo "                  skip_build_check=$SKIP_BUILD_CHECK skip_flatten=$SKIP_FLATTEN"
echo ""

# Show current process state
echo "  running processes:"
pgrep -af "openclaw-engine" 2>/dev/null | head -3 | sed 's/^/    /' || echo "    (no engine)"
pgrep -af "uvicorn app.main" 2>/dev/null | head -3 | sed 's/^/    /' || echo "    (no api)"
echo ""

# Show DB row counts
echo "  DB row counts:"
PGPASSWORD="$PG_PASS" psql -h 127.0.0.1 -U trading_admin -d trading_ai -t -A -F $'\t' <<'SQL' 2>/dev/null | sed 's/^/    /'
SELECT 'fills' || E'\t' || COUNT(*) FROM trading.fills
UNION ALL SELECT 'intents' || E'\t' || COUNT(*) FROM trading.intents
UNION ALL SELECT 'orders' || E'\t' || COUNT(*) FROM trading.orders
UNION ALL SELECT 'risk_verdicts' || E'\t' || COUNT(*) FROM trading.risk_verdicts;
SQL
echo ""

if ! confirm "Proceed with clean restart?"; then
    err "Aborted by operator"
    exit 1
fi

# ── Step 2: Stop engine + API ─────────────────────────────────────────────
hdr "Step 2/7 — Stop engine + API"

echo "  stopping Rust engine..."
pkill -f "openclaw-engine" 2>/dev/null || true
echo "  stopping API (port 8000)..."
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
sleep 2

# Verify
if pgrep -f "openclaw-engine" >/dev/null; then
    warn "engine still running, force-killing"
    pkill -9 -f "openclaw-engine" 2>/dev/null || true
    sleep 1
fi
ok "engine + API stopped"

# ── Step 3: Flatten exchange positions ────────────────────────────────────
hdr "Step 3/7 — Flatten exchange positions"

if [ "$SKIP_FLATTEN" -eq 1 ]; then
    warn "skipping flatten (--skip-flatten)"
else
    if [ ! -x "$API_VENV/bin/python3" ]; then
        err "API venv python not found: $API_VENV/bin/python3"
        exit 1
    fi

    FLATTEN_ARGS=""
    [ "$YES" -eq 1 ] && FLATTEN_ARGS="--yes"

    echo "  [demo] flattening..."
    "$API_VENV/bin/python3" helper_scripts/clean_restart_flatten.py \
        --env demo $FLATTEN_ARGS || {
        err "demo flatten failed (exit=$?)"
        exit 1
    }

    if [ "$INCLUDE_LIVE" -eq 1 ]; then
        if [ "${OPENCLAW_ALLOW_MAINNET:-0}" != "1" ]; then
            warn "--include-live set but OPENCLAW_ALLOW_MAINNET != 1, skipping live"
        else
            echo "  [mainnet] flattening..."
            OPENCLAW_ALLOW_MAINNET=1 "$API_VENV/bin/python3" \
                helper_scripts/clean_restart_flatten.py \
                --env mainnet $FLATTEN_ARGS || {
                err "mainnet flatten failed (exit=$?)"
                exit 1
            }
        fi
    else
        echo "  [mainnet] skipped (pass --include-live to enable)"
    fi
    ok "exchange flatten complete"
fi

# ── Step 4: Archive damaged runtime + DB data ─────────────────────────────
hdr "Step 4/7 — Archive damaged data"

mkdir -p "$ARCHIVE_ROOT/snapshots" "$ARCHIVE_ROOT/state_files" "$ARCHIVE_ROOT/canary"

# Move runtime snapshots + state files (keep engine.sock/ai_service.sock — regenerated)
if [ -d "$DATA_DIR" ]; then
    # snapshots
    for f in "$DATA_DIR"/pipeline_snapshot*.json; do
        [ -f "$f" ] && mv "$f" "$ARCHIVE_ROOT/snapshots/" 2>/dev/null || true
    done
    # per-engine state files — paper_state.json 不歸檔（paper 為純虛擬、
    # paper_state.json 是唯一權威；archive 掉會導致冷啟動以 demo wallet 當
    # initial_balance，但 realized/fees 仍從 trading.fills 還原，產生虛假虧損）
    for f in "$DATA_DIR"/demo_state.json "$DATA_DIR"/live_state.json; do
        [ -f "$f" ] && mv "$f" "$ARCHIVE_ROOT/state_files/" 2>/dev/null || true
    done
    # canary + audit
    for f in "$DATA_DIR"/engine_results.jsonl "$DATA_DIR"/demo_audit.jsonl "$DATA_DIR"/watchdog.log; do
        [ -f "$f" ] && mv "$f" "$ARCHIVE_ROOT/canary/" 2>/dev/null || true
    done
    # fallback dir (if present)
    if [ -d "$DATA_DIR/fallback" ]; then
        mv "$DATA_DIR/fallback" "$ARCHIVE_ROOT/" 2>/dev/null || true
    fi
    ok "runtime files archived → $ARCHIVE_ROOT"
else
    warn "data dir $DATA_DIR did not exist"
fi

# Archive edge estimates (paper + demo), then reset to empty
for f in settings/edge_estimates.json settings/edge_estimates_paper.json; do
    if [ -f "$f" ] && [ -s "$f" ] && [ "$(cat "$f")" != "{}" ]; then
        cp "$f" "$ARCHIVE_ROOT/$(basename "$f").backup"
        echo "{}" > "$f"
        ok "reset $f (backup saved)"
    fi
done

# DB archive (opt-in)
if [ "$MARK_DAMAGED" -eq 1 ]; then
    echo "  archiving DB tables → trading.{fills,intents,orders,risk_verdicts}_damaged_${TS}..."
    PGPASSWORD="$PG_PASS" psql -h 127.0.0.1 -U trading_admin -d trading_ai <<SQL 2>&1 | tail -10
BEGIN;
CREATE TABLE trading.fills_damaged_${TS} AS SELECT * FROM trading.fills;
CREATE TABLE trading.intents_damaged_${TS} AS SELECT * FROM trading.intents;
CREATE TABLE trading.orders_damaged_${TS} AS SELECT * FROM trading.orders;
CREATE TABLE trading.risk_verdicts_damaged_${TS} AS SELECT * FROM trading.risk_verdicts;
TRUNCATE trading.fills;
TRUNCATE trading.intents;
TRUNCATE trading.orders;
TRUNCATE trading.risk_verdicts;
COMMIT;
SQL
    ok "DB archived + truncated (damaged_${TS} tables preserved)"
else
    echo "  DB archive skipped (pass --mark-damaged to enable)"
fi

# ── Step 5: Binary freshness check ────────────────────────────────────────
hdr "Step 5/7 — Binary freshness check"

if [ "$SKIP_BUILD_CHECK" -eq 1 ]; then
    warn "skipping build check"
elif [ ! -f "$BIN" ]; then
    warn "binary missing → building"
    cargo build --release -p openclaw-engine --manifest-path rust/Cargo.toml
    ok "binary built"
else
    SRC_DIRS="rust/openclaw_engine/src rust/openclaw_core/src rust/openclaw_types/src"
    MANIFEST_FILES="Cargo.toml rust/Cargo.toml"
    # Build list of existing paths only (find errors on missing dirs abort pipefail)
    # 只用存在的路徑（find 對缺失目錄報錯會觸發 pipefail）
    EXIST_PATHS=""
    for p in $SRC_DIRS $MANIFEST_FILES; do [ -e "$p" ] && EXIST_PATHS="$EXIST_PATHS $p"; done
    NEWER_COUNT=$(find $EXIST_PATHS -type f \( -name '*.rs' -o -name '*.toml' \) \
                       -newer "$BIN" 2>/dev/null | wc -l)
    if [ "$NEWER_COUNT" -gt 0 ]; then
        warn "$NEWER_COUNT source file(s) newer than binary → rebuilding"
        find $EXIST_PATHS -type f \( -name '*.rs' -o -name '*.toml' \) \
             -newer "$BIN" 2>/dev/null | head -5 | sed 's/^/    /'
        cargo build --release -p openclaw-engine --manifest-path rust/Cargo.toml
        ok "binary rebuilt"
    else
        ok "binary is current ($(stat -c '%y' "$BIN" | cut -d. -f1))"
    fi
fi

# ── Step 6: Restart engine + API ──────────────────────────────────────────
hdr "Step 6/7 — Restart engine + API"

mkdir -p "$DATA_DIR"

echo "  starting Rust engine..."
OPENCLAW_DATA_DIR="$DATA_DIR" \
OPENCLAW_CANARY_MODE=1 \
OPENCLAW_DATABASE_URL="postgresql://trading_admin:${PG_PASS}@127.0.0.1:5432/trading_ai" \
OPENCLAW_IPC_SECRET="${IPC_SECRET}" \
    nohup "$BIN" > "$DATA_DIR/engine.log" 2>&1 &
ENGINE_PID=$!
echo "    engine PID: $ENGINE_PID"

echo "  starting API (4 workers)..."
cd program_code/exchange_connectors/bybit_connector/control_api_v1
OPENCLAW_DATABASE_URL="postgresql://trading_admin:${PG_PASS}@127.0.0.1:5432/trading_ai" \
OPENCLAW_IPC_SECRET="${IPC_SECRET}" \
    nohup .venv/bin/python3 .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --workers 4 \
    > "$DATA_DIR/api.log" 2>&1 &
API_PID=$!
echo "    API PID: $API_PID"
cd "$REPO_ROOT"

echo "  waiting 12s for startup..."
sleep 12
ok "restart initiated"

# ── Step 7: Verify watchdog ───────────────────────────────────────────────
hdr "Step 7/7 — Verify watchdog"

STATUS_JSON=$(python3 helper_scripts/canary/engine_watchdog.py \
    --data-dir "$DATA_DIR" --stale-threshold 45 --grace-period 120 --status 2>&1 || true)
echo "$STATUS_JSON" | head -20

ALIVE=$(echo "$STATUS_JSON" | python3 -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print('1' if d.get('engine_alive') else '0')
except Exception:
    print('0')
")

if [ "$ALIVE" = "1" ]; then
    ok "all engines alive"
    echo ""
    hdr "CLEAN RESTART COMPLETE ✓"
    echo "  archive:       $ARCHIVE_ROOT"
    echo "  engine PID:    $ENGINE_PID"
    echo "  API PID:       $API_PID"
    echo "  engine log:    $DATA_DIR/engine.log"
    echo ""
    exit 0
else
    err "one or more engines failed watchdog check — inspect $DATA_DIR/engine.log"
    tail -20 "$DATA_DIR/engine.log" 2>/dev/null | sed 's/^/    /'
    exit 2
fi

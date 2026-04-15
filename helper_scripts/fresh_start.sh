#!/bin/bash
# fresh_start.sh — 開發完整重置腳本（DB 指標清零 + 乾淨重啟）
#
# MODULE_NOTE (EN): Complete dev-stage reset. In addition to what clean_restart.sh
#   does (stop/flatten/restart), this script WIPES all PnL / fees / win-rate /
#   experience data from Postgres (via fresh_start_reset.py) so the engine
#   cold-starts with zero trading history. Preserves: market data (klines,
#   funding, OI, LSR, liquidations, regime, news), learning.model_registry,
#   linucb_state_archive, linucb_migrations, features.versions, ai_budget_config.
# MODULE_NOTE (中): 開發完整重置腳本。在 clean_restart.sh 的基礎上，額外清空
#   Postgres 中所有 PnL / 手續費 / 勝率 / 經驗數據（透過 fresh_start_reset.py），
#   讓引擎從零交易歷史冷啟動。保留：市場數據（klines/funding/OI/LSR/liquidations/
#   regime/news）、model_registry、linucb_state_archive、linucb_migrations、
#   features.versions、ai_budget_config。
#
# Usage:
#   bash helper_scripts/fresh_start.sh [OPTIONS]
#
# Options:
#   --yes                 Skip all interactive confirmations
#   --include-live        Also flatten mainnet positions (OPENCLAW_ALLOW_MAINNET=1)
#   --skip-flatten        Skip exchange flatten (when positions already 0)
#   --skip-build-check    Skip source-vs-binary freshness check
#   --help                Show this help and exit
#
# Note: LinUCB bandit state is always archived to learning.linucb_state_archive
#       before wipe (recoverable if needed). See fresh_start_reset.py.
#
# WARNING: This DESTROYS all trading history. Market data + trained models
#          are preserved. Run clean_restart.sh for light reset (just flatten).

set -euo pipefail
cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd)"

YES=0
INCLUDE_LIVE=0
SKIP_FLATTEN=0
SKIP_BUILD_CHECK=0

for arg in "$@"; do
    case "$arg" in
        --yes) YES=1 ;;
        --include-live) INCLUDE_LIVE=1 ;;
        --skip-flatten) SKIP_FLATTEN=1 ;;
        --skip-build-check) SKIP_BUILD_CHECK=1 ;;
        --help|-h)
            sed -n '2,/^set -euo/p' "$0" | head -n -1 | sed 's/^# \?//'
            exit 0 ;;
        *) echo "[ERR] unknown arg: $arg" >&2; exit 1 ;;
    esac
done

TS="$(date +%Y%m%d_%H%M%S)"
CONFIRM_CODE="FRESH_START_$(date +%Y_%m_%d)"
ARCHIVE_ROOT="$HOME/BybitOpenClaw/archive/fresh_start_${TS}"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
BIN="rust/target/release/openclaw-engine"
API_VENV="program_code/exchange_connectors/bybit_connector/control_api_v1/.venv"
SECRETS_ENV="$HOME/BybitOpenClaw/secrets/environment_files/basic_system_services.env"
IPC_SECRET_FILE="$HOME/BybitOpenClaw/secrets/environment_files/ipc_secret.txt"
MAINT_FLAG="$DATA_DIR/engine_maintenance.flag"

C_HDR='\033[1;36m'; C_OK='\033[1;32m'; C_WARN='\033[1;33m'; C_ERR='\033[1;31m'; C_END='\033[0m'
hdr()  { echo -e "${C_HDR}══ $* ══${C_END}"; }
ok()   { echo -e "${C_OK}✓${C_END} $*"; }
warn() { echo -e "${C_WARN}⚠${C_END} $*"; }
err()  { echo -e "${C_ERR}✗${C_END} $*" >&2; }
confirm() {
    [ "$YES" -eq 1 ] && return 0
    read -r -p "$1 [yes/NO]: " r
    [ "${r,,}" = "yes" ]
}

# ── Step 1: Pre-flight ────────────────────────────────────────────────────
hdr "Step 1/8 — Pre-flight"

[ -f "$SECRETS_ENV" ] || { err "secrets env missing: $SECRETS_ENV"; exit 1; }
PG_PASS="$(grep POSTGRES_PASSWORD "$SECRETS_ENV" | cut -d= -f2-)"
IPC_SECRET="$(cat "$IPC_SECRET_FILE" 2>/dev/null || echo '')"

echo "  data_dir:       $DATA_DIR"
echo "  archive_target: $ARCHIVE_ROOT"
echo "  confirm_code:   $CONFIRM_CODE"
echo "  options:        yes=$YES include_live=$INCLUDE_LIVE skip_flatten=$SKIP_FLATTEN"
echo "                  skip_build_check=$SKIP_BUILD_CHECK"
echo ""
echo "  ⚠  This will WIPE all trading history (fills/orders/intents/signals/"
echo "     outcomes/agent activity/learning state). Market data + models preserved."
echo ""
echo "  DB row counts (pre-wipe):"
PGPASSWORD="$PG_PASS" psql -h 127.0.0.1 -U trading_admin -d trading_ai -t -A -F $'\t' <<'SQL' 2>/dev/null | sed 's/^/    /'
SELECT 'fills' || E'\t' || COUNT(*) FROM trading.fills
UNION ALL SELECT 'intents' || E'\t' || COUNT(*) FROM trading.intents
UNION ALL SELECT 'orders' || E'\t' || COUNT(*) FROM trading.orders
UNION ALL SELECT 'risk_verdicts' || E'\t' || COUNT(*) FROM trading.risk_verdicts
UNION ALL SELECT 'decision_outcomes' || E'\t' || COUNT(*) FROM trading.decision_outcomes
UNION ALL SELECT 'signals' || E'\t' || COUNT(*) FROM trading.signals
UNION ALL SELECT 'agent.messages' || E'\t' || COUNT(*) FROM agent.messages
UNION ALL SELECT 'learning.rl_transitions' || E'\t' || COUNT(*) FROM learning.rl_transitions;
SQL
echo ""

confirm "Proceed with FRESH START (destroys trading history)?" || { err "Aborted"; exit 1; }

# ── Step 2: Stop engine + API + set maintenance flag ─────────────────────
hdr "Step 2/8 — Stop engine + API"

mkdir -p "$DATA_DIR"
touch "$MAINT_FLAG"
ok "maintenance flag set (watchdog won't auto-restart)"

pkill -f "openclaw-engine" 2>/dev/null || true
lsof -ti :8000 | xargs kill -9 2>/dev/null || true
sleep 2
pgrep -f "openclaw-engine" >/dev/null && { pkill -9 -f "openclaw-engine" 2>/dev/null || true; sleep 1; }
ok "engine + API stopped"

# ── Step 3: Flatten exchange ──────────────────────────────────────────────
hdr "Step 3/8 — Flatten exchange positions"

if [ "$SKIP_FLATTEN" -eq 1 ]; then
    warn "skipping flatten (--skip-flatten)"
else
    [ -x "$API_VENV/bin/python3" ] || { err "API venv not found"; rm -f "$MAINT_FLAG"; exit 1; }
    FLATTEN_ARGS=""; [ "$YES" -eq 1 ] && FLATTEN_ARGS="--yes"
    echo "  [demo] flattening..."
    "$API_VENV/bin/python3" helper_scripts/clean_restart_flatten.py \
        --env demo $FLATTEN_ARGS || { err "demo flatten failed"; rm -f "$MAINT_FLAG"; exit 1; }

    if [ "$INCLUDE_LIVE" -eq 1 ]; then
        if [ "${OPENCLAW_ALLOW_MAINNET:-0}" != "1" ]; then
            warn "--include-live set but OPENCLAW_ALLOW_MAINNET != 1, skipping live"
        else
            echo "  [mainnet] flattening..."
            OPENCLAW_ALLOW_MAINNET=1 "$API_VENV/bin/python3" \
                helper_scripts/clean_restart_flatten.py --env mainnet $FLATTEN_ARGS || {
                err "mainnet flatten failed"; rm -f "$MAINT_FLAG"; exit 1; }
        fi
    fi
    ok "exchange flatten complete"
fi

# ── Step 4: Archive runtime + reset edge estimates ────────────────────────
hdr "Step 4/8 — Archive runtime files"

mkdir -p "$ARCHIVE_ROOT/snapshots" "$ARCHIVE_ROOT/state_files" "$ARCHIVE_ROOT/canary"

if [ -d "$DATA_DIR" ]; then
    for f in "$DATA_DIR"/pipeline_snapshot*.json; do
        [ -f "$f" ] && mv "$f" "$ARCHIVE_ROOT/snapshots/" 2>/dev/null || true
    done
    # fresh_start archives paper_state too (vs clean_restart.sh which preserves it)
    # fresh_start 會歸檔 paper_state（clean_restart.sh 則保留）— 因為 DB 也要清
    for f in "$DATA_DIR"/paper_state.json "$DATA_DIR"/demo_state.json "$DATA_DIR"/live_state.json; do
        [ -f "$f" ] && mv "$f" "$ARCHIVE_ROOT/state_files/" 2>/dev/null || true
    done
    for f in "$DATA_DIR"/engine_results.jsonl "$DATA_DIR"/paper_audit.jsonl \
             "$DATA_DIR"/demo_audit.jsonl "$DATA_DIR"/canary_events.jsonl \
             "$DATA_DIR"/watchdog.log "$DATA_DIR"/watchdog_state.json; do
        [ -f "$f" ] && mv "$f" "$ARCHIVE_ROOT/canary/" 2>/dev/null || true
    done
    [ -d "$DATA_DIR/fallback" ] && mv "$DATA_DIR/fallback" "$ARCHIVE_ROOT/" 2>/dev/null || true
    ok "runtime files archived → $ARCHIVE_ROOT"
fi

# Reset edge estimates (per-mode)
for f in settings/edge_estimates.json settings/edge_estimates_paper.json \
         settings/edge_estimates_demo.json settings/edge_estimates_live.json; do
    if [ -f "$f" ] && [ -s "$f" ] && [ "$(cat "$f")" != "{}" ]; then
        cp "$f" "$ARCHIVE_ROOT/$(basename "$f").backup"
        echo "{}" > "$f"
        ok "reset $f"
    fi
done

# ── Step 5: DB wipe via fresh_start_reset.py ──────────────────────────────
hdr "Step 5/8 — DB wipe (experience data)"

# fresh_start_reset.py reads POSTGRES_* from environment
set -a; source "$SECRETS_ENV"; set +a

"$API_VENV/bin/python3" helper_scripts/db/fresh_start_reset.py \
    --execute --confirm "$CONFIRM_CODE" || {
    err "DB wipe failed"; rm -f "$MAINT_FLAG"; exit 1
}
ok "DB wiped (trading/agent/learning/observability/risk experience data)"

# ── Step 6: Binary freshness ──────────────────────────────────────────────
hdr "Step 6/8 — Binary freshness"

if [ "$SKIP_BUILD_CHECK" -eq 1 ]; then
    warn "skipping build check"
elif [ ! -f "$BIN" ]; then
    warn "binary missing → building"
    cargo build --release -p openclaw-engine --manifest-path rust/Cargo.toml
    ok "binary built"
else
    SRC_DIRS="rust/openclaw_engine/src rust/openclaw_core/src rust/openclaw_types/src rust/openclaw_pyo3/src"
    MANIFEST_FILES="Cargo.toml rust/Cargo.toml"
    EXIST_PATHS=""
    for p in $SRC_DIRS $MANIFEST_FILES; do [ -e "$p" ] && EXIST_PATHS="$EXIST_PATHS $p"; done
    NEWER=$(find $EXIST_PATHS -type f \( -name '*.rs' -o -name '*.toml' \) -newer "$BIN" 2>/dev/null | wc -l)
    if [ "$NEWER" -gt 0 ]; then
        warn "$NEWER source file(s) newer → rebuilding"
        cargo build --release -p openclaw-engine --manifest-path rust/Cargo.toml
        ok "binary rebuilt"
    else
        ok "binary current ($(stat -c '%y' "$BIN" | cut -d. -f1))"
    fi
fi

# ── Step 7: Restart ───────────────────────────────────────────────────────
hdr "Step 7/8 — Restart"

rm -f "$MAINT_FLAG"
ok "maintenance flag cleared"

echo "  starting Rust engine..."
OPENCLAW_DATA_DIR="$DATA_DIR" \
OPENCLAW_CANARY_MODE=1 \
OPENCLAW_DATABASE_URL="postgresql://redacted@127.0.0.1:5432/trading_ai" \
OPENCLAW_IPC_SECRET="${IPC_SECRET}" \
    nohup "$BIN" > "$DATA_DIR/engine.log" 2>&1 &
ENGINE_PID=$!
echo "    engine PID: $ENGINE_PID"

echo "  starting API (4 workers)..."
cd program_code/exchange_connectors/bybit_connector/control_api_v1
OPENCLAW_DATABASE_URL="postgresql://redacted@127.0.0.1:5432/trading_ai" \
OPENCLAW_IPC_SECRET="${IPC_SECRET}" \
    nohup .venv/bin/python3 .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 --port 8000 --workers 4 \
    > /tmp/openclaw/api.log 2>&1 &
API_PID=$!
echo "    API PID: $API_PID"
cd "$REPO_ROOT"

echo "  waiting 12s for startup..."
sleep 12
ok "restart initiated"

# ── Step 8: Verify ────────────────────────────────────────────────────────
hdr "Step 8/8 — Verify watchdog"

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
    hdr "FRESH START COMPLETE ✓"
    echo "  archive:    $ARCHIVE_ROOT"
    echo "  engine PID: $ENGINE_PID"
    echo "  API PID:    $API_PID"
    echo "  engine log: $DATA_DIR/engine.log"
    echo ""
    exit 0
else
    err "watchdog check failed — inspect $DATA_DIR/engine.log"
    tail -20 "$DATA_DIR/engine.log" 2>/dev/null | sed 's/^/    /'
    exit 2
fi

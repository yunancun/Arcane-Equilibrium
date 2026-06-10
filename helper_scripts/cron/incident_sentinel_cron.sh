#!/usr/bin/env bash
# incident_sentinel_cron.sh — L2 Mesh P2p 哨兵 5min cron wrapper
#   （mirror halt_audit_pg_writer_cron.sh 模式：mkdir lock + secrets env + heartbeat）。
#
# 建議 cron entry（由 install_incident_sentinel_cron.sh idempotent 安裝）：
#   */5 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/incident_sentinel_cron.sh
#
# 為什麼 fail-soft exit 0：cron mail spam 防護——哨兵自身故障不該再造一層噪音；
# 失敗已寫 log，下輪 cron 乾淨重跑（crash 自癒，設計 §5.1）。
# 為什麼 env file 缺失不致命（與 halt_audit 的 FATAL 不同）：sentinel 的 file/HTTP
# 軸（A1/A1b/A2/A3）零 DB 依賴，必須在「PG down / secrets 缺」時也能告警；
# DB 軸缺憑證自走 db_unreachable WARN（其本身就是 incident 信號）。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/incident_sentinel_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/incident_sentinel_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 讀 secret env file（DB 軸 POSTGRES_* 用；與 sibling cron 對齊的 grep-parse，不裸 source）
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ -f "$ENV_FILE" ]]; then
    PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
    if [[ -n "$PG_PASS" && -n "$PG_USER" && -n "$PG_DB" ]]; then
        export POSTGRES_USER="$PG_USER" POSTGRES_PASSWORD="$PG_PASS" POSTGRES_DB="$PG_DB"
        export POSTGRES_HOST="${PG_HOST:-127.0.0.1}" POSTGRES_PORT="${PG_PORT:-5432}"
    else
        echo "[$(ts)] WARN: PG creds incomplete in $ENV_FILE — DB 軸將走 db_unreachable" >> "$LOG"
    fi
else
    echo "[$(ts)] WARN: env file missing: $ENV_FILE — DB 軸將走 db_unreachable" >> "$LOG"
fi

export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"

# stale lock 自清：上輪 hang 死（mtime > 15min）→ 清掉避免永久 skip（設計 §9）。
if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +15 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>15min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

# 鎖：避免 overrun（5min interval + 上輪未跑完）。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: incident_sentinel already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# heartbeat sentinel（cron_heartbeat 慣例，供 passive_wait/巡檢驗 cron 真有 fire）。
touch "$HEARTBEAT_DIR/incident_sentinel.last_fire"

SCRIPT="$BASE/helper_scripts/canary/incident_sentinel.py"
if [[ ! -f "$SCRIPT" ]]; then
    echo "[$(ts)] ERROR: incident_sentinel.py not found under BASE=$BASE" >> "$LOG"
    exit 0
fi

# venv python 優先（psycopg2 在 venv；缺則退 python3，DB 軸自走 db_unreachable）。
PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

echo "[$(ts)] === incident_sentinel start ===" >> "$LOG"
rc=0
"$PYBIN" "$SCRIPT" --once --data-dir "$DATA" --base-dir "$BASE" >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === incident_sentinel end rc=${rc} ===" >> "$LOG"

# fail-soft：rc 已落 log（0=all-pass / 1=軸 FAIL / 2=connect error），
# 哨兵 verdict 由 alert + 審計 jsonl 傳達，不靠 cron mail。
exit 0

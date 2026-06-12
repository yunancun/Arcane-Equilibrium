#!/usr/bin/env bash
# l2_memory_distill_cron.sh — L2 記憶蒸餾管線 daily cron wrapper
#   （mirror incident_sentinel_cron.sh 模式：mkdir lock + secrets grep-parse +
#     heartbeat + fail-soft exit 0；外加 size-based 日誌輪轉）。
#
# 建議 cron entry（由 install_l2_memory_distill_cron.sh idempotent 安裝）：
#   23 5 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       OPENCLAW_L2_MEMORY_PIPELINE=0 \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/l2_memory_distill_cron.sh
#
# 為什麼 05:23 UTC：避撞既有 cron 表（03:00 pg_dump / 03:17 ml_training /
# 04:00 m11_replay / 04:41 feature_baseline / 06:00 counterfactual，PA spec G10）。
# 為什麼 fail-soft exit 0：cron mail spam 防護——失敗已寫 log，游標「成功才推進」
# 保證失敗日下輪自動補跑（spec §6.1），不靠 cron mail 傳達。
# 為什麼 flag 默認 0：安裝後行為中性（inert）——CLI 殼在連 DB 前檢查
# OPENCLAW_L2_MEMORY_PIPELINE，off ⇒ 一行 log + exit 0（spec §10）。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/l2_memory_distill_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/l2_memory_distill_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
# 5MB 上限、保留一代（.1）：daily 殼正常每日數行，輪轉只防 runaway 失敗迴圈灌爆磁碟。
LOG_MAX_BYTES=5242880

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# ── 日誌輪轉（size-based，先於本輪任何寫入）──
# wc -c 取檔案大小：macOS 無 GNU stat -c，wc -c 雙平台可用（feedback_cross_platform）。
if [[ -f "$LOG" ]]; then
    LOG_SIZE=$(wc -c < "$LOG" | tr -d '[:space:]' || echo 0)
    if [[ "${LOG_SIZE:-0}" -gt "$LOG_MAX_BYTES" ]]; then
        mv -f "$LOG" "${LOG}.1"
        echo "[$(ts)] INFO: log rotated (size ${LOG_SIZE} > ${LOG_MAX_BYTES}) -> ${LOG}.1" >> "$LOG"
    fi
fi

# ── 讀 secret env file（POSTGRES_*；與 sibling cron 對齊的 grep-parse，不裸 source）──
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
        echo "[$(ts)] WARN: PG creds incomplete in $ENV_FILE — flag=1 時 distill 將以 config-error 結束" >> "$LOG"
    fi
else
    echo "[$(ts)] WARN: env file missing: $ENV_FILE — flag=1 時 distill 將以 config-error 結束" >> "$LOG"
fi

export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"
# flag passthrough：默認 0（inert）。真開關位置在 CLI 殼（連 DB 前 gate）。
export OPENCLAW_L2_MEMORY_PIPELINE="${OPENCLAW_L2_MEMORY_PIPELINE:-0}"
export OPENCLAW_L2_MEMORY_EMBED_BACKFILL="${OPENCLAW_L2_MEMORY_EMBED_BACKFILL:-0}"

# ── stale lock 自清：上輪 hang 死（mtime > 180min）→ 清掉避免永久 skip ──
# 為什麼 180min：daily 窗最多 7 日 × 2 次本地 LLM call（單 call 估 30-120s），
# 遠小於 3h；超過必為 hang 死非正常 overrun（daily interval=24h，誤清風險極低）。
if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +180 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>180min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

# ── 鎖：防重入（手動觸發與 cron 撞期、或上輪未跑完）──
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: l2_memory_distill already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# heartbeat（cron_heartbeat 慣例，供 passive_wait/巡檢驗 cron 真有 fire）。
touch "$HEARTBEAT_DIR/l2_memory_distill.last_fire"

SCRIPT="$BASE/helper_scripts/cron/l2_memory_distill.py"
if [[ ! -f "$SCRIPT" ]]; then
    echo "[$(ts)] ERROR: l2_memory_distill.py not found under BASE=$BASE" >> "$LOG"
    exit 0
fi

# venv python 優先（psycopg2 在 venv；缺則退 python3——flag=0 路徑零第三方依賴仍可跑）。
PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

echo "[$(ts)] === l2_memory_distill start (flag=${OPENCLAW_L2_MEMORY_PIPELINE}) ===" >> "$LOG"
rc=0
"$PYBIN" "$SCRIPT" --base-dir "$BASE" --data-dir "$DATA" >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === l2_memory_distill end rc=${rc} ===" >> "$LOG"

# fail-soft：rc 已落 log（0=成功/inert、1=runtime 失敗、2=配置錯誤）；
# 失敗日由游標機制下輪補跑，不靠 cron mail。
exit 0

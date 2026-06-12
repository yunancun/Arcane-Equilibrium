#!/usr/bin/env bash
# bybit_announcement_sentinel_cron.sh — Bybit 公告增量哨兵 30min cron wrapper
#   （mirror incident_sentinel_cron.sh 模式：mkdir lock + heartbeat + fail-soft）。
#
# 建議 cron entry（由 install_bybit_announcement_sentinel_cron.sh idempotent 安裝）：
#   7,37 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/bybit_announcement_sentinel_cron.sh
#   （分鐘 offset :07/:37 避整點，BB 裁決 §3 輪詢紀律）
#
# 為什麼 fail-soft exit 0：cron mail spam 防護——哨兵自身故障不該再造一層噪音；
# 失敗已寫 log，下輪 cron 乾淨重跑（fail-quiet + 哨兵自帶連續失敗 meta-alert）。
# 為什麼無 PG secrets 段（與 incident_sentinel 不同）：本哨兵零 DB 依賴、零 credential
# 面（plain GET 公開 API），唯一寫入 = state json + 告警。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/bybit_announcement_sentinel_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/bybit_announcement_sentinel_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

export OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$BASE}"
export OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-$DATA}"

# stale lock 自清：上輪 hang 死（mtime > 45min = 1.5× interval）→ 清掉避免永久 skip。
if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +45 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>45min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

# 鎖：避免 overrun（30min interval + 上輪未跑完）。
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: bybit_announcement_sentinel already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# heartbeat sentinel（cron_heartbeat 慣例，供 passive_wait/巡檢驗 cron 真有 fire）。
touch "$HEARTBEAT_DIR/bybit_announcement_sentinel.last_fire"

SCRIPT="$BASE/helper_scripts/canary/bybit_announcement_sentinel.py"
if [[ ! -f "$SCRIPT" ]]; then
    echo "[$(ts)] ERROR: bybit_announcement_sentinel.py not found under BASE=$BASE" >> "$LOG"
    exit 0
fi

# 純 stdlib 腳本：python3 即足；尊重 OPENCLAW_PYTHON_BIN / venv（與 sibling 一致）。
PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

echo "[$(ts)] === bybit_announcement_sentinel start ===" >> "$LOG"
rc=0
"$PYBIN" "$SCRIPT" --once --data-dir "$DATA" >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === bybit_announcement_sentinel end rc=${rc} ===" >> "$LOG"

# fail-soft：rc 已落 log；哨兵 verdict 由告警 + state json 傳達，不靠 cron mail。
exit 0

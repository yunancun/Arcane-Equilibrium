#!/usr/bin/env bash
# polymarket_axis_cron.sh — Polymarket 數據軸採集 cron wrapper
#   （mirror incident_sentinel_cron.sh 模式：mkdir lock + heartbeat + fail-soft）。
#
# 用法：polymarket_axis_cron.sh [daily|hourly-topn]   （默認 daily）
#
# 建議 cron entries（由 install_polymarket_axis_cron.sh idempotent 安裝）：
#   41 4 * * *  → daily 全量 sweep（04:41 UTC，與 residual producer 03:17 同型錯峰）
#   7  * * * *  → hourly-topn volume top-50（默認註釋停用；活化 = operator 決策，
#                 QC memo §3：cron 排程與活化是 operator 域）
#
# 為什麼 fail-soft exit 0：cron mail spam 防護——採集器自身故障不該再造噪音；
# 失敗已落 log + 下輪乾淨重跑。snapshot 丟一輪少一輪（QC memo §2），但 wrapper
# 崩潰連 log 都沒有更糟。
# 為什麼零 secrets / 零 PG env：本軸 R-0 紅線（零 auth、零 PG）——wrapper 刻意
# 不 source 任何 secrets env file，採集只打公開唯讀 API。
set -euo pipefail

MODE="${1:-daily}"
case "$MODE" in
    daily|hourly-topn) ;;
    *)
        echo "ERROR: unknown mode '$MODE' (expect daily|hourly-topn)" >&2
        exit 0  # fail-soft：壞參數也不炸 cron mail，error 留 stderr 落 cron log。
        ;;
esac

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/polymarket_axis_cron.log"
LOCK_ROOT="${DATA}/locks"
# 兩模式共用一把鎖：daily 與 hourly 同時跑會交錯寫同一 state 檔（read-modify-write
# 競態），單鎖序列化是最小安全解。
LOCK_DIR="${LOCK_ROOT}/polymarket_axis_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR"

ts() { date -u '+%Y-%m-%d %H:%M:%S'; }

export OPENCLAW_BASE_DIR="$BASE"
export OPENCLAW_DATA_DIR="$DATA"

# stale lock 自清：上輪 hang 死（mtime > 50min）→ 清掉避免永久 skip。
# 50min：daily 全量 sweep（枚舉+keyword+follow-up @2req/s）正常 <10min，
# 50min 已是異常；且 < hourly 間隔，不會吃掉下一輪 hourly。
if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +50 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>50min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: polymarket_axis already running (lock held), mode=$MODE" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# heartbeat（cron_heartbeat 慣例，供 passive-wait healthcheck 驗 cron 真有 fire）。
touch "$HEARTBEAT_DIR/polymarket_axis_${MODE}.last_fire"

CLI="$BASE/helper_scripts/research/polymarket_axis/cli.py"
if [[ ! -f "$CLI" ]]; then
    echo "[$(ts)] ERROR: cli.py not found under BASE=$BASE" >> "$LOG"
    exit 0
fi

# venv python 優先（duckdb parquet 鏡像在 venv；缺則退 python3，鏡像自動 skip）。
PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

echo "[$(ts)] === polymarket_axis start mode=$MODE ===" >> "$LOG"
rc=0
"$PYBIN" "$CLI" --mode "$MODE" --created-by-role cron >> "$LOG" 2>&1 || rc=$?
echo "[$(ts)] === polymarket_axis end mode=$MODE rc=${rc} ===" >> "$LOG"

# fail-soft：rc 已落 log；採集結果由 run dir manifest 傳達，不靠 cron mail。
exit 0

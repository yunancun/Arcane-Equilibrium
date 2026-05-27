#!/usr/bin/env bash
# verify_pg_dump.sh — P0-OPS-4 GAP-D auxiliary verify wrapper（Bash sidecar）。
#
# 為什麼保留 Bash 版（而非只用 Python healthcheck）：
#   operator SSH ad-hoc 場景下 Bash 比 Python 快（不需 venv），方便 14-step drill
#   或一次性 audit。Python 版 `check_pg_dump_freshness.py` 才是 healthcheck pipeline
#   主要入口（passive_wait_healthcheck.shell 6h cron 集成）。
#
# Checks:
#   1. backup dir 存在 + 可寫
#   2. 最新 trading_ai_*.dump mtime < 26h（cron daily 03:00 UTC + 2h grace）
#   3. dump 大小 > 1 MB（防 zero-byte partial-fail）
#   4. md5sum 對齊當日 JSONL log entry
#   5. retention policy 真正生效（最舊 dump ≤ retention+1d）
#
# Exit:
#   0 = PASS（5 check 全綠）
#   1 = WARN（1-2 非致命）
#   2 = FAIL（≥3 fail OR 致命 check 2/3 fail）
#
# 平台守門：Linux only（per MIT draft pattern）。

set -euo pipefail

# ----- 平台守門 -----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: verify_pg_dump.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 check 走 stat -c / find -mtime；Mac BSD stat 不兼容；ssh trade-core 跑。" >&2
    exit 2
fi

OPENCLAW_BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-$HOME/pg_backups}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
# 預設 30d（per operator 2026-05-27 拍板）。
OPENCLAW_BACKUP_RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-30}"
GRACE_HOURS="${OPENCLAW_BACKUP_GRACE_HOURS:-2}"

JSONL="${OPENCLAW_DATA_DIR}/logs/trading_ai_pg_dump_cron.jsonl"
FAIL_COUNT=0
WARN_COUNT=0
declare -a NOTES=()

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

note() { NOTES+=("$1"); }

# Check 1: backup dir
if [[ ! -d "$OPENCLAW_BACKUP_ROOT" ]]; then
    note "FAIL[1]: backup dir missing: $OPENCLAW_BACKUP_ROOT"
    FAIL_COUNT=$((FAIL_COUNT+1))
elif [[ ! -w "$OPENCLAW_BACKUP_ROOT" ]]; then
    note "FAIL[1]: backup dir not writable"
    FAIL_COUNT=$((FAIL_COUNT+1))
else
    note "PASS[1]: backup dir OK ($OPENCLAW_BACKUP_ROOT)"
fi

# Check 2: latest dump freshness
LATEST_DUMP=$(ls -1t "$OPENCLAW_BACKUP_ROOT"/trading_ai_*.dump 2>/dev/null | head -1 || true)
if [[ -z "$LATEST_DUMP" ]]; then
    note "FAIL[2]: no trading_ai_*.dump found in $OPENCLAW_BACKUP_ROOT"
    FAIL_COUNT=$((FAIL_COUNT+1))
else
    MTIME_EPOCH=$(stat -c '%Y' "$LATEST_DUMP")
    NOW_EPOCH=$(date -u +%s)
    AGE_HOURS=$(( (NOW_EPOCH - MTIME_EPOCH) / 3600 ))
    MAX_AGE=$(( 24 + GRACE_HOURS ))
    if [[ $AGE_HOURS -gt $MAX_AGE ]]; then
        note "FAIL[2]: latest dump stale ${AGE_HOURS}h > ${MAX_AGE}h: $LATEST_DUMP"
        FAIL_COUNT=$((FAIL_COUNT+1))
    else
        note "PASS[2]: latest dump fresh ${AGE_HOURS}h: $LATEST_DUMP"
    fi
fi

# Check 3: dump size sanity（> 1 MB；trading_ai compressed estimate 6-9 GB 所以 >1MB 為 min sanity）
if [[ -n "${LATEST_DUMP:-}" && -f "$LATEST_DUMP" ]]; then
    SIZE_BYTES=$(stat -c '%s' "$LATEST_DUMP")
    if [[ $SIZE_BYTES -lt 1048576 ]]; then
        note "FAIL[3]: dump too small ${SIZE_BYTES}B < 1MB (partial?)"
        FAIL_COUNT=$((FAIL_COUNT+1))
    else
        note "PASS[3]: dump size $(numfmt --to=iec "$SIZE_BYTES" 2>/dev/null || echo "${SIZE_BYTES}B")"
    fi
fi

# Check 4: md5 對齊 JSONL 末尾 entry（jq 或 JSONL 缺則 WARN-skip）
if [[ -f "$JSONL" ]] && command -v jq >/dev/null 2>&1 && [[ -n "${LATEST_DUMP:-}" ]]; then
    JSONL_MD5=$(tail -50 "$JSONL" | jq -r --arg f "$LATEST_DUMP" 'select(.dump_file==$f and .status=="ok") | .md5' 2>/dev/null | tail -1)
    if [[ -n "$JSONL_MD5" ]]; then
        ACTUAL_MD5=$(md5sum "$LATEST_DUMP" | cut -d' ' -f1)
        if [[ "$JSONL_MD5" == "$ACTUAL_MD5" ]]; then
            note "PASS[4]: md5 match $JSONL_MD5"
        else
            note "FAIL[4]: md5 drift recorded=$JSONL_MD5 actual=$ACTUAL_MD5"
            FAIL_COUNT=$((FAIL_COUNT+1))
        fi
    else
        note "WARN[4]: no recent ok JSONL entry for $LATEST_DUMP"
        WARN_COUNT=$((WARN_COUNT+1))
    fi
else
    note "WARN[4]: JSONL md5 check skipped (jq/JSONL missing)"
    WARN_COUNT=$((WARN_COUNT+1))
fi

# Check 5: retention 真正生效
OLDEST_DUMP=$(ls -1tr "$OPENCLAW_BACKUP_ROOT"/trading_ai_*.dump 2>/dev/null | head -1 || true)
if [[ -n "$OLDEST_DUMP" ]]; then
    OLD_EPOCH=$(stat -c '%Y' "$OLDEST_DUMP")
    AGE_DAYS=$(( (NOW_EPOCH - OLD_EPOCH) / 86400 ))
    MAX_DAYS=$(( OPENCLAW_BACKUP_RETENTION_DAYS + 1 ))
    if [[ $AGE_DAYS -gt $MAX_DAYS ]]; then
        note "WARN[5]: oldest dump ${AGE_DAYS}d > retention ${OPENCLAW_BACKUP_RETENTION_DAYS}d (prune not running?)"
        WARN_COUNT=$((WARN_COUNT+1))
    else
        note "PASS[5]: oldest dump ${AGE_DAYS}d (retention ${OPENCLAW_BACKUP_RETENTION_DAYS}d)"
    fi
fi

# Emit
echo "[$(ts)] verify_pg_dump.sh fail=$FAIL_COUNT warn=$WARN_COUNT"
for n in "${NOTES[@]}"; do echo "  $n"; done

if [[ $FAIL_COUNT -ge 3 ]]; then exit 2; fi
# 致命個別 check（2 freshness or 3 size）auto-FAIL
if echo "${NOTES[@]}" | grep -qE 'FAIL\[2\]|FAIL\[3\]'; then exit 2; fi
if [[ $FAIL_COUNT -ge 1 || $WARN_COUNT -ge 2 ]]; then exit 1; fi
exit 0

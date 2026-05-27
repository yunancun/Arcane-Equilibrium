#!/usr/bin/env bash
# trading_ai_pg_dump_cron.sh — P0-OPS-4 GAP-D daily PG dump 包裝（cron target）。
#
# 配對 install script：
#   $HOME/BybitOpenClaw/srv/helper_scripts/cron/install_pg_dump_cron.sh
#
# 配對 healthcheck：
#   $HOME/BybitOpenClaw/srv/helper_scripts/canary/healthchecks/check_pg_dump_freshness.py
#   passive_wait_healthcheck.checks_pg_dump_freshness（Python package）
#
# Spec 來源：
#   docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md
#     §2.3 / §7.2 / §10 GAP-D
#   MIT empirical report:
#     docs/CCAgentWorkSpace/MIT/workspace/reports/2026-05-27--ops_4_gap_bd_pg_backup_restore_research.md
#     §1.1 Tier 0+1 dump / §1.2 pg_dump -Fc 主路徑 / §1.5 disk budget
#
# 設計重點（per operator 2026-05-27 拍板）：
#   1. EXCLUDE `learning.decision_features_evaluations`（182 GB / 17d / 無 retention /
#      無 consumer，按 MIT §1.1 Tier-3 拒入 dump，避 D+30 接近 disk 紅線）
#   2. EXCLUDE *_damaged_* 表（2026-04-14 quarantine 殘留）
#   3. Retention 30d（per operator 拍板；MIT §1.5 估 6-9 GB/day × 30d = 180-270 GB
#      可 fit local 842 GB free 約 25-32%）
#   4. 完成/失敗均寫 `learning.governance_audit_log`，event_type
#      `pg_dump_completed` / `pg_dump_failed`（CHECK enum 由 V113 補登）
#   5. local-only `$HOME/pg_backups`（per operator 拍板；MIT §1.7 Phase 1 plan A）
#
# 鏡 outcome_backfiller_live_cron.sh 風格（lock dir / ts() / log path / cron heartbeat）。
#
# 硬邊界：
#   - 跨平台：僅 Linux 跑（uname Linux check）；Mac dev refuse exit 2
#   - 路徑不硬編碼 `/home/ncyu`（per memory feedback_cross_platform）
#   - 不改 PG schema、不 touch trading.* 寫；INSERT 僅限 learning.governance_audit_log
#   - 失敗不重試：寫 audit row 後 exit non-zero，由 cron / healthcheck 觸發 alarm

set -euo pipefail

# ----- 平台守門：僅 Linux 執行（per MIT draft pattern）。Mac dev 顯式拒絕。 -----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: trading_ai_pg_dump_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-$HOME/pg_backups}"
RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-30}"

LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/trading_ai_pg_dump_cron.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/trading_ai_pg_dump_cron.lock.d"
JSONL="${LOG_DIR}/trading_ai_pg_dump_cron.jsonl"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$BACKUP_ROOT"

# Cron heartbeat sentinel — P1-CRON-INSTALL-WAVE-1 同模式。
# touch-at-start：「cron 被排程觸發」的證據；由 [check_pg_dump_freshness] healthcheck 順帶監測。
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
mkdir -p "$HEARTBEAT_DIR" 2>/dev/null || true
touch "$HEARTBEAT_DIR/trading_ai_pg_dump.last_fire" 2>/dev/null || true

ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep   '^POSTGRES_DB='       "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT='     "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"

if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

export PGPASSWORD="$PG_PASS"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: trading_ai pg_dump already running (lock held)" >> "$LOG"
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

DATESTAMP=$(date -u '+%Y-%m-%d')
DUMP_FILE="$BACKUP_ROOT/trading_ai_${DATESTAMP}.dump"
SENTINEL="$BACKUP_ROOT/.last_pg_dump"

START_EPOCH=$(date -u +%s)
echo "[$(ts)] START pg_dump $PG_DB -> $DUMP_FILE (retention=${RETENTION_DAYS}d)" >> "$LOG"

# pg_dump 設計選擇（per MIT §1.2 + §1.3）：
#   -Fc                     custom format（compressed, parallel-restorable, 跨 PG version safe）
#   --no-owner              跨環境 role 兼容
#   --no-privileges         跨環境 grant 兼容
#   --no-publications       不帶 logical replication 設定
#   --no-subscriptions      同上
#   --exclude-table=A       MIT §1.1 Tier-3：evaluations 182 GB 無 retention 無 consumer，拒入 dump
#   --exclude-table=*_damaged_* 2026-04-14 incident quarantine 殘留
#
# 注意：不指定 --schema 改用「whole DB minus exclude」策略；schema-level allow-list
# 在 spec §7.2 已被 MIT push back #2 揭風險（evaluations 在 learning schema 內，
# allow-list 無法避免）。本 wrapper 改採 deny-list 模式精準排除單表。
if pg_dump -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -Fc \
        --no-owner --no-privileges \
        --no-publications --no-subscriptions \
        --exclude-table='learning.decision_features_evaluations' \
        --exclude-table='*_damaged_*' \
        -f "$DUMP_FILE" 2>>"$LOG"; then
    DUMP_RC=0
else
    DUMP_RC=$?
fi

END_EPOCH=$(date -u +%s)
DUR=$(( END_EPOCH - START_EPOCH ))

# ─── 內嵌 helper：寫 governance_audit_log row（per FA §C audit trail requirement）。 ───
# 為什麼用內嵌 psql heredoc：避免新增 Python 依賴；cron 環境最小化攻擊面。
# 為什麼 SECURITY INVOKER：sentinel insert 走 cron user，學 V054/V098 寫入語法。
# audit row 失敗本身不阻 cron 主流（dump 已成；audit failure 走 stderr + log）。
emit_governance_audit() {
    local event_type="$1"
    local payload_json="$2"
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
        -v ON_ERROR_STOP=1 \
        -c "INSERT INTO learning.governance_audit_log (
                ts, event_type, decided_by, payload, rule_failures, lease_revoke_triggers
            ) VALUES (
                NOW(), '${event_type}', 'pg_dump_cron',
                \$payload\$${payload_json}\$payload\$::jsonb,
                ARRAY[]::TEXT[], ARRAY[]::TEXT[]
            );" >> "$LOG" 2>&1 || {
        echo "[$(ts)] WARN: governance_audit_log INSERT failed (event=${event_type})" >> "$LOG"
        return 1
    }
    return 0
}

if [[ $DUMP_RC -eq 0 && -s "$DUMP_FILE" ]]; then
    SIZE_BYTES=$(stat -c '%s' "$DUMP_FILE" 2>/dev/null || echo 0)
    MD5=$(md5sum "$DUMP_FILE" | cut -d' ' -f1)
    echo "[$(ts)] OK  $DUMP_FILE size=$SIZE_BYTES md5=$MD5 dur=${DUR}s" >> "$LOG"
    printf '{"ts":"%s","status":"ok","dump_file":"%s","size_bytes":%s,"md5":"%s","duration_sec":%s,"retention_days":%s}\n' \
        "$(ts)" "$DUMP_FILE" "$SIZE_BYTES" "$MD5" "$DUR" "$RETENTION_DAYS" >> "$JSONL"
    # sentinel for healthcheck
    date -u '+%Y-%m-%dT%H:%M:%SZ' > "$SENTINEL"

    # governance_audit_log: pg_dump_completed
    PAYLOAD_OK=$(printf '{"dump_file":"%s","size_bytes":%s,"md5":"%s","duration_sec":%s,"retention_days":%s,"datestamp":"%s","db":"%s","host":"%s"}' \
        "$DUMP_FILE" "$SIZE_BYTES" "$MD5" "$DUR" "$RETENTION_DAYS" "$DATESTAMP" "$PG_DB" "$PG_HOST")
    emit_governance_audit 'pg_dump_completed' "$PAYLOAD_OK" || true
else
    echo "[$(ts)] FAIL pg_dump rc=$DUMP_RC dur=${DUR}s" >> "$LOG"
    printf '{"ts":"%s","status":"fail","dump_file":"%s","rc":%s,"duration_sec":%s}\n' \
        "$(ts)" "$DUMP_FILE" "$DUMP_RC" "$DUR" >> "$JSONL"
    # remove zero-byte file
    [[ -f "$DUMP_FILE" && ! -s "$DUMP_FILE" ]] && rm -f "$DUMP_FILE"

    # governance_audit_log: pg_dump_failed
    PAYLOAD_FAIL=$(printf '{"dump_file":"%s","rc":%s,"duration_sec":%s,"datestamp":"%s","db":"%s","host":"%s"}' \
        "$DUMP_FILE" "$DUMP_RC" "$DUR" "$DATESTAMP" "$PG_DB" "$PG_HOST")
    emit_governance_audit 'pg_dump_failed' "$PAYLOAD_FAIL" || true
    exit "$DUMP_RC"
fi

# ----- Retention（per operator 30d 拍板）-----
RETENTION_PRUNED=$(find "$BACKUP_ROOT" -maxdepth 1 -name 'trading_ai_*.dump' -mtime "+${RETENTION_DAYS}" -print -delete 2>/dev/null | wc -l)
if [[ "$RETENTION_PRUNED" -gt 0 ]]; then
    echo "[$(ts)] PRUNED $RETENTION_PRUNED dump(s) older than ${RETENTION_DAYS}d" >> "$LOG"
fi

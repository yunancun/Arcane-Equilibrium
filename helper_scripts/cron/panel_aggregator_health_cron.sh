#!/usr/bin/env bash
# panel_aggregator_health_cron.sh — W1 sub-task 3 (E1-γ, 2026-05-11)
#
# 5min cadence health check for the W-AUDIT-8a Phase B Tier 2 panel collector:
#   1. engine alive (pgrep openclaw-engine)
#   2. panel.funding_rates_panel last snapshot freshness (max(snapshot_ts_ms) vs now)
#   3. panel.oi_delta_panel last snapshot freshness
#
# Suggested cron entry (operator-installed):
#   */5 * * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv \
#       OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/panel_aggregator_health_cron.sh
#
# Threshold convention（與 [66] healthcheck 對齊）:
#   < 5min   → PASS
#   5-15min  → WARN
#   > 15min  → FAIL
# Engine not running → FAIL（boot 期 first 60s 預期；多 cycle 仍 FAIL = real outage）
#
# Exit code:
#   0 = all PASS
#   1 = any WARN
#   2 = any FAIL or engine dead
#
# Output: append to $LOG_DIR/panel_aggregator_health_cron.log

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/panel_aggregator_health_cron.log"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# 1. PG creds — read from environment_files (same pattern as edge_estimate_snapshots_cycle_cron.sh)
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"

if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi

export PGPASSWORD="$PG_PASS"

# 2. Engine alive check（pgrep；exit 0 = found）
engine_alive="DEAD"
if pgrep -f openclaw-engine >/dev/null 2>&1; then
    engine_alive="ALIVE"
fi

# 3. PG freshness query — 對 panel.funding_rates_panel + panel.oi_delta_panel
#    取 max(snapshot_ts_ms)，計算與 now() 的 diff。schema 不存在 → freshness=ABSENT。
freshness_query() {
    local table="$1"
    psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -t -A -c "
        SELECT CASE
            WHEN NOT EXISTS (SELECT 1 FROM information_schema.tables
                             WHERE table_schema='panel' AND table_name='${table}')
            THEN 'ABSENT'
            ELSE COALESCE(
                (extract(epoch FROM now())*1000 - max(snapshot_ts_ms))::bigint::text,
                'NO_ROWS'
            )
        END
        FROM panel.${table};
    " 2>/dev/null || echo "ABSENT"
}

funding_age_ms=$(freshness_query "funding_rates_panel" | tr -d ' ')
oi_age_ms=$(freshness_query "oi_delta_panel" | tr -d ' ')

# 4. 三狀態 verdict per table
classify() {
    local age_ms="$1"
    if [[ "$age_ms" == "ABSENT" || "$age_ms" == "NO_ROWS" ]]; then
        echo "ABSENT"
    elif [[ "$age_ms" -lt 300000 ]]; then
        echo "PASS"
    elif [[ "$age_ms" -lt 900000 ]]; then
        echo "WARN"
    else
        echo "FAIL"
    fi
}

funding_status=$(classify "$funding_age_ms")
oi_status=$(classify "$oi_age_ms")

# 5. Aggregate verdict
overall="PASS"
exit_code=0
if [[ "$engine_alive" == "DEAD" ]]; then
    overall="FAIL"
    exit_code=2
fi
for s in "$funding_status" "$oi_status"; do
    case "$s" in
        FAIL|ABSENT)
            if [[ "$exit_code" -lt 2 ]]; then
                overall="FAIL"
                exit_code=2
            fi
            ;;
        WARN)
            if [[ "$exit_code" -lt 1 ]]; then
                overall="WARN"
                exit_code=1
            fi
            ;;
    esac
done

# 6. Log line（grep-friendly）
echo "[$(ts)] panel_aggregator_health overall=${overall} engine=${engine_alive} funding=${funding_status}(${funding_age_ms}ms) oi=${oi_status}(${oi_age_ms}ms)" >> "$LOG"

exit "$exit_code"

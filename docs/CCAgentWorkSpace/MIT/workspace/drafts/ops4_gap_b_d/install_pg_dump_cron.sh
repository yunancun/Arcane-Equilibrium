#!/usr/bin/env bash
# install_pg_dump_cron.sh — OPS-4 GAP-D: install PG dump + 15d retention cron
#
# Spec source: docs/execution_plan/specs/2026-05-26--p0-ops-4-first-day-live-runbook.md §2.3 + §7.2 + §10 GAP-D
#
# DRAFT / spec-only. This script is NOT installed by default; operator runs it manually
# after dry-run + sign-off per CLAUDE.md §七 cron install policy.
#
# What it installs (single crontab entry):
#   - daily 03:00 UTC: pg_dump trading_ai (custom format, gzip) → $OPENCLAW_BACKUP_ROOT
#   - 15d retention via find -mtime +15 -delete (operator-tunable; spec says 15d minimum)
#   - per-run JSONL log with dump size, duration, exit code, file md5sum
#
# Cross-platform: Linux runtime only. Mac dev refuses (no docker PG container).
#
# Hard boundaries:
#   - Does NOT mutate $HOME/BybitOpenClaw/secrets
#   - Does NOT modify trading_ai schema
#   - Does NOT install if a pg_dump entry already exists in crontab (idempotent guard)

set -euo pipefail

# ----- platform gate (Linux only; Mac dev refuse) -----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_pg_dump_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       Run via 'ssh trade-core' on the runtime host." >&2
    exit 2
fi

# ----- env -----
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
OPENCLAW_BACKUP_ROOT="${OPENCLAW_BACKUP_ROOT:-$HOME/pg_backups}"
OPENCLAW_BACKUP_RETENTION_DAYS="${OPENCLAW_BACKUP_RETENTION_DAYS:-15}"
OPENCLAW_BACKUP_HOUR_UTC="${OPENCLAW_BACKUP_HOUR_UTC:-3}"   # default 03:00 UTC

# ----- pre-flight -----
if ! command -v pg_dump >/dev/null 2>&1; then
    echo "ERROR: pg_dump not found on PATH. Install postgresql-client matching PG 16.x." >&2
    exit 3
fi
if [[ ! -f "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" ]]; then
    echo "ERROR: secrets env file missing: $OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" >&2
    exit 4
fi
mkdir -p "$OPENCLAW_BACKUP_ROOT"
mkdir -p "$OPENCLAW_DATA_DIR/logs"

# ----- idempotent guard: refuse if cron already has pg_dump entry -----
if crontab -l 2>/dev/null | grep -qE '(pg_dump|trading_ai_pg_dump_cron\.sh)'; then
    echo "SKIP: existing pg_dump cron entry detected; not installing (manually remove first)." >&2
    crontab -l | grep -E '(pg_dump|trading_ai_pg_dump_cron\.sh)' >&2
    exit 0
fi

# ----- propose crontab entry -----
WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/trading_ai_pg_dump_cron.sh"
ENTRY="0 ${OPENCLAW_BACKUP_HOUR_UTC} * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_SECRETS_ROOT=${OPENCLAW_SECRETS_ROOT} OPENCLAW_BACKUP_ROOT=${OPENCLAW_BACKUP_ROOT} OPENCLAW_BACKUP_RETENTION_DAYS=${OPENCLAW_BACKUP_RETENTION_DAYS} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/trading_ai_pg_dump_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"

if [[ "${OPENCLAW_BACKUP_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_BACKUP_CRON_APPLY=1 to actually install."
    exit 0
fi

# ----- actually install (only when explicit apply flag set) -----
( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: pg_dump cron entry added. Verify with: crontab -l | grep pg_dump"

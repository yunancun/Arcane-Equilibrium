#!/usr/bin/env bash
# Linux trade-core DB migration applier — loops sql/migrations/V*.sql on the live
# Postgres DB. Mirror of helper_scripts/mac_bootstrap_db.sh migration loop
# (lines 104-114) minus the Docker / role / DB bootstrap prelude (Linux already
# has trading_admin + trading_ai + timescaledb from early 2026-04-07 setup).
#
# Linux trade-core DB migration 應用器 — 套 sql/migrations/V*.sql 到正式 PG。
# 對應 mac_bootstrap_db.sh 的 migration 迴圈，扣掉 Docker/role/DB 建置前置
# （Linux 2026-04-07 設置就已有 trading_admin + trading_ai + timescaledb）。
#
# Why this exists: V023__model_registry.sql 於 2026-04-23 landed 但 Linux 上從未
# 執行（operator 沒跑過 manual apply），`CREATE TABLE IF NOT EXISTS` 被 V004
# legacy 表擋下靜默 no-op；同樣風險對所有未來 migration 皆存在。這腳本 = Linux
# 端的 migration 應用標準路徑，避免再度靠 operator 記得手動執行。
#
# Usage:
#   bash helper_scripts/linux_bootstrap_db.sh              # dry-run: list what would apply
#   bash helper_scripts/linux_bootstrap_db.sh --apply      # actually run
#   bash helper_scripts/linux_bootstrap_db.sh --apply V023 # apply only V023
#
# Idempotency: 所有 V*.sql 使用 CREATE IF NOT EXISTS / ADD COLUMN IF NOT EXISTS。
# 若某 migration 包含 pre-existing table drift（如 V023 撞 V004 legacy），
# migration 會 silent no-op 不報錯 → 需搭配 helper_scripts/db/audit_migrations.py
# 檢查實際 schema。本腳本不替代 audit。
#
# Env file: $OPENCLAW_BASE_DIR/settings/environment_files/basic_system_services.env
# 必含: POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB / POSTGRES_HOST / POSTGRES_PORT

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
ENV_FILE="$BASE/settings/environment_files/basic_system_services.env"
MIG_DIR="$BASE/sql/migrations"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found" >&2
    echo "       Set OPENCLAW_BASE_DIR or run from repo root" >&2
    exit 1
fi

PG_USER="$(grep '^POSTGRES_USER=' "$ENV_FILE" | cut -d= -f2-)"
PG_PASS="$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
PG_DB="$(grep '^POSTGRES_DB=' "$ENV_FILE" | cut -d= -f2-)"
PG_HOST="$(grep '^POSTGRES_HOST=' "$ENV_FILE" | cut -d= -f2- || echo '127.0.0.1')"
PG_PORT="$(grep '^POSTGRES_PORT=' "$ENV_FILE" | cut -d= -f2- || echo '5432')"
[[ -z "$PG_HOST" ]] && PG_HOST="127.0.0.1"
[[ -z "$PG_PORT" ]] && PG_PORT="5432"

if [[ -z "$PG_USER" || -z "$PG_PASS" || -z "$PG_DB" ]]; then
    echo "ERROR: POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB must be set in $ENV_FILE" >&2
    exit 1
fi

# Parse CLI
APPLY=0
ONLY_MIGRATIONS=()
for arg in "$@"; do
    case "$arg" in
        --apply) APPLY=1 ;;
        V*) ONLY_MIGRATIONS+=("$arg") ;;
        --help|-h)
            sed -n '2,25p' "$0"
            exit 0
            ;;
        *)
            echo "Unknown arg: $arg (use --help)" >&2
            exit 1
            ;;
    esac
done

# Build migration list
cd "$MIG_DIR"
if [[ ${#ONLY_MIGRATIONS[@]} -gt 0 ]]; then
    MIGRATIONS=()
    for m in "${ONLY_MIGRATIONS[@]}"; do
        # Find matching file (user may pass "V023" or "V023__model_registry.sql")
        if [[ -f "$m" ]]; then
            MIGRATIONS+=("$m")
        else
            MATCH="$(ls ${m}*.sql 2>/dev/null | grep -v rollback | head -1 || true)"
            if [[ -z "$MATCH" ]]; then
                echo "ERROR: migration $m not found in $MIG_DIR" >&2
                exit 1
            fi
            MIGRATIONS+=("$MATCH")
        fi
    done
else
    # All V*.sql excluding rollback and V999 test fixture
    mapfile -t MIGRATIONS < <(ls V*.sql | grep -v rollback | grep -v '^V999' | sort)
fi

echo "[bootstrap] Linux migration applier"
echo "[bootstrap] PG target: $PG_USER@$PG_HOST:$PG_PORT/$PG_DB"
echo "[bootstrap] migration dir: $MIG_DIR"
echo "[bootstrap] mode: $([[ $APPLY -eq 1 ]] && echo 'APPLY (will execute SQL)' || echo 'DRY-RUN (use --apply to execute)')"
echo "[bootstrap] migrations in scope (${#MIGRATIONS[@]}):"
for f in "${MIGRATIONS[@]}"; do
    echo "  - $f"
done

if [[ $APPLY -eq 0 ]]; then
    echo ""
    echo "[bootstrap] dry-run complete. Re-run with --apply to execute."
    exit 0
fi

echo ""
echo "[bootstrap] running migrations..."
FAILED=""
SUCCEEDED=()
SKIPPED_SILENT=()  # files that ran without error but may be no-op due to pre-existing tables
for f in "${MIGRATIONS[@]}"; do
    echo "[migrate] === $f ==="
    if PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
            -v ON_ERROR_STOP=1 -q -f "$f" 2>&1; then
        SUCCEEDED+=("$f")
        echo "[migrate] OK: $f"
    else
        FAILED="$f"
        break
    fi
done

if [[ -n "$FAILED" ]]; then
    echo ""
    echo "[bootstrap] FAILED at migration $FAILED" >&2
    echo "[bootstrap] ${#SUCCEEDED[@]} migrations succeeded before failure" >&2
    exit 2
fi

echo ""
echo "[bootstrap] all ${#SUCCEEDED[@]} migrations applied"
echo "[verify] schemas:"
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    -c "\dn" 2>/dev/null
echo "[verify] hypertables:"
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" \
    -c "SELECT count(*) AS hypertable_count FROM timescaledb_information.hypertables" 2>/dev/null
echo ""
echo "[bootstrap] DONE. Run helper_scripts/db/audit_migrations.py to verify no silent no-ops."

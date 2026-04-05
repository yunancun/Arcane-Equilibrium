#!/usr/bin/env bash
# Setup test database: run migrations V001-V005 against test PG.
# 設置測試數據庫：對測試 PG 執行 V001-V005 遷移。
#
# Usage: ./scripts/setup_test_db.sh
# Requires: docker compose up (test-pg running on port 15432)

set -euo pipefail

DB_HOST="${OPENCLAW_TEST_DB_HOST:-127.0.0.1}"
DB_PORT="${OPENCLAW_TEST_DB_PORT:-15432}"
DB_NAME="${OPENCLAW_TEST_DB_NAME:-openclaw_test}"
DB_USER="${OPENCLAW_TEST_DB_USER:-test_user}"
PGPASSWORD="${OPENCLAW_TEST_DB_PASS:-test_pass}"
export PGPASSWORD

MIGRATION_DIR="$(cd "$(dirname "$0")/../sql/migrations" && pwd)"

echo "=== OpenClaw Test DB Setup ==="
echo "Host: ${DB_HOST}:${DB_PORT}  DB: ${DB_NAME}  User: ${DB_USER}"
echo "Migrations: ${MIGRATION_DIR}"

# Wait for PG to be ready / 等待 PG 就緒
echo "Waiting for PostgreSQL..."
for i in $(seq 1 30); do
    if pg_isready -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" >/dev/null 2>&1; then
        echo "PostgreSQL ready."
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: PostgreSQL not ready after 30s. Is docker compose up?"
        exit 1
    fi
    sleep 1
done

# Enable TimescaleDB extension / 啟用 TimescaleDB 擴展
psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" -c \
    "CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;" 2>/dev/null || true

# Run migrations in order / 按順序執行遷移
for sql_file in "${MIGRATION_DIR}"/V*.sql; do
    if [ -f "$sql_file" ]; then
        fname="$(basename "$sql_file")"
        echo "  Running: ${fname}"
        psql -h "${DB_HOST}" -p "${DB_PORT}" -U "${DB_USER}" -d "${DB_NAME}" \
            -f "$sql_file" -v ON_ERROR_STOP=1 >/dev/null 2>&1
    fi
done

echo "=== Test DB setup complete ==="
echo "Export: OPENCLAW_TEST_DATABASE_URL=postgresql://redacted@${DB_HOST}:${DB_PORT}/${DB_NAME}"

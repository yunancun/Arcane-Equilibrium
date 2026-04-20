#!/usr/bin/env bash
# Mac dev DB bootstrap — create trading_admin / trading_ai / timescaledb + run migrations.
# Mac dev 資料庫引導 — 建 trading_admin / trading_ai / timescaledb 並跑 migrations。
#
# Assumes: colima running, openclaw-test-pg container up on localhost:15432,
#          $OPENCLAW_BASE_DIR / $OPENCLAW_SECRETS_ROOT exported.
# 前提: colima 已起、openclaw-test-pg 容器跑在 15432、env 已 export。
#
# Idempotent: re-runnable. CREATE IF NOT EXISTS + ALTER ROLE re-binds password.
# 冪等：可重跑；CREATE IF NOT EXISTS + ALTER ROLE 重綁密碼。

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:?OPENCLAW_BASE_DIR not set}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:?OPENCLAW_SECRETS_ROOT not set}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
MIG_DIR="$BASE/sql/migrations"
CONTAINER="openclaw-test-pg"
PG_HOST="127.0.0.1"
PG_PORT="15432"

if [[ ! -f "$ENV_FILE" ]]; then
    echo "ERROR: $ENV_FILE not found" >&2
    exit 1
fi

PG_PASS="$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" | cut -d= -f2-)"
if [[ -z "$PG_PASS" ]]; then
    echo "ERROR: POSTGRES_PASSWORD empty in $ENV_FILE" >&2
    exit 1
fi
echo "[bootstrap] PG_PASS loaded (len=${#PG_PASS})"

if ! docker ps --filter "name=$CONTAINER" --format '{{.Names}}' | grep -q "^$CONTAINER$"; then
    echo "ERROR: container $CONTAINER not running. Run: docker-compose -f docker/docker-compose.test.yml up -d" >&2
    exit 1
fi
echo "[bootstrap] container $CONTAINER is running"

TMP_SQL="/tmp/oc_bootstrap_$$.sql"
cleanup() { rm -f "$TMP_SQL"; }
trap cleanup EXIT

cat > "$TMP_SQL" <<SQL_TEMPLATE
DO \$\$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='trading_admin') THEN
        CREATE ROLE trading_admin WITH LOGIN SUPERUSER;
    END IF;
END\$\$;
SQL_TEMPLATE

printf "ALTER ROLE trading_admin WITH PASSWORD '%s';\n" "$PG_PASS" >> "$TMP_SQL"

cat >> "$TMP_SQL" <<'SQL_TEMPLATE'
SELECT 'trading_ai exists' WHERE EXISTS (SELECT 1 FROM pg_database WHERE datname='trading_ai');
SQL_TEMPLATE

docker cp "$TMP_SQL" "$CONTAINER:/tmp/oc_bootstrap.sql"
docker exec "$CONTAINER" psql -U test_user -d postgres -v ON_ERROR_STOP=1 -f /tmp/oc_bootstrap.sql
echo "[bootstrap] role ready"

DB_EXISTS="$(docker exec "$CONTAINER" psql -U test_user -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='trading_ai'")"
if [[ -z "$DB_EXISTS" ]]; then
    docker exec "$CONTAINER" psql -U test_user -d postgres -c "CREATE DATABASE trading_ai OWNER trading_admin;"
    echo "[bootstrap] trading_ai database created"
else
    echo "[bootstrap] trading_ai database already exists"
fi

docker exec "$CONTAINER" psql -U test_user -d trading_ai -c "CREATE EXTENSION IF NOT EXISTS timescaledb;"
echo "[bootstrap] timescaledb extension ensured"

echo "[bootstrap] testing trading_admin login..."
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U trading_admin -d trading_ai -c "SELECT current_user, current_database();"

# -----------------------------------------------------------------------------
# Pre-migration: legacy public.* tables must exist before V005 can RENAME them.
# Linux deploys run monitoring_services/init_trading_schema.sql first via
# docker-compose init; Mac dev bootstraps a fresh DB without that entrypoint,
# so V005 fails on the compat views. init script is pure CREATE TABLE IF NOT
# EXISTS → idempotent and safe to run on any state.
#
# 預遷移：V005 需要 public.* 舊表已存在才能 RENAME。Linux 走 docker-compose
# 會先跑 init_trading_schema.sql，Mac dev 新建 DB 沒有這條路徑，V005 會在
# compat view 那步炸。init 全是 CREATE TABLE IF NOT EXISTS，任何狀態重跑都安全。
# -----------------------------------------------------------------------------
INIT_SQL="$BASE/docker_projects/monitoring_services/init_trading_schema.sql"
if [[ -f "$INIT_SQL" ]]; then
    LEGACY_PRESENT="$(PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U trading_admin -d trading_ai -tAc \
        "SELECT 1 FROM pg_tables WHERE schemaname='public' AND tablename IN ('account_snapshots','account_snapshots_legacy') LIMIT 1")"
    if [[ -z "$LEGACY_PRESENT" ]]; then
        echo "[bootstrap] running init_trading_schema.sql (pre-migration legacy tables)"
        PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U trading_admin -d trading_ai \
            -v ON_ERROR_STOP=1 -q -f "$INIT_SQL"
        echo "[bootstrap] init_trading_schema.sql applied"
    else
        echo "[bootstrap] legacy tables already present — skipping init_trading_schema.sql"
    fi
else
    echo "[bootstrap] WARN: $INIT_SQL not found; V005 may fail if legacy tables are absent" >&2
fi

echo "[bootstrap] running migrations from $MIG_DIR"
cd "$MIG_DIR"
FAILED=""
for f in $(ls V*.sql | grep -v rollback | sort); do
    echo "[migrate] === $f ==="
    if ! PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U trading_admin -d trading_ai \
            -v ON_ERROR_STOP=1 -q -f "$f"; then
        FAILED="$f"
        break
    fi
done

if [[ -n "$FAILED" ]]; then
    echo "[bootstrap] FAILED at migration $FAILED" >&2
    exit 2
fi

echo "[bootstrap] all migrations applied"
echo "[verify] schemas:"
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U trading_admin -d trading_ai -c "\dn"
echo "[verify] hypertables:"
PGPASSWORD="$PG_PASS" psql -h "$PG_HOST" -p "$PG_PORT" -U trading_admin -d trading_ai -c "SELECT count(*) AS hypertable_count FROM timescaledb_information.hypertables;"

echo "[bootstrap] DONE"

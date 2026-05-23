#!/usr/bin/env bash
# =============================================================================
# ac1b_monthly_healthcheck.sh
#
# 用途：Sprint 5+ Wave 1 §4.4.4 production hardening — Sprint 4+ §4.1.4
#      AC-1b production verify monthly cron。
#
# 為什麼 monthly（per PA report §5.2.1 + Stage F §8.6 PM phase 3e 拍板）:
#   - Sprint 4+ Phase 3c AC-1b 30 min sample wait 一次性 PASS（5 active
#     domain × 20-264 row）；monthly cron 是 sustained verification cadence。
#   - 對齊 operator 「§4.4 全部進 hardening (4 項) + AC-1b monthly cron (不
#     defer)」拍板（2026-05-23 PM phase 3e sign-off）。
#   - 6 active domain × ≥5 row in 30 min window = monthly cron PASS;
#     emitter scheduler resilience 自動驗（engine restart/rebuild/OOM kill
#     後仍能 30 min 內回填即 PASS）。
#
# Crontab spec（per PA report §5.2.3）:
#   30 3 1 * * /home/ncyu/BybitOpenClaw/srv/helper_scripts/db/ac1b_monthly_healthcheck.sh
#   月初 03:30 UTC（避撞 passive_wait_healthcheck 0/6/12/18:00 UTC 6h cron）
#
# Usage:
#   bash helper_scripts/db/ac1b_monthly_healthcheck.sh           # full output
#   bash helper_scripts/db/ac1b_monthly_healthcheck.sh --quiet   # only FAIL
#
# Exit codes:
#   0 = PASS — 6/6 active domain ≥ 5 row in 30 min window
#   1 = FAIL — ≥1 active domain < 5 row (operator alert)
#   2 = DB connection error
#
# Environment overrides:
#   OPENCLAW_BASE_DIR        repo root (default: $HOME/BybitOpenClaw/srv)
#   OPENCLAW_SECRETS_ROOT    secrets dir (default: $HOME/BybitOpenClaw/secrets)
#   OPENCLAW_PG_CONTAINER    PG container (default: trading_postgres)
#   OPENCLAW_HEARTBEAT_DIR   sentinel mtime dir (default: /tmp/openclaw/cron_heartbeat)
#   POSTGRES_DB / POSTGRES_USER / POSTGRES_HOST / POSTGRES_PORT fallback
# =============================================================================

set -u

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"
PG_CONT="${OPENCLAW_PG_CONTAINER:-trading_postgres}"
SENTINEL_DIR="${OPENCLAW_HEARTBEAT_DIR:-/tmp/openclaw/cron_heartbeat}"

QUIET=0
for arg in "$@"; do
  if [[ "$arg" == "--quiet" ]]; then
    QUIET=1
  fi
done

# ─── 1. Load Postgres env (mirrors passive_wait_healthcheck.sh:79-88) ────────
if [[ -f "$SECRETS_ENV" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_ENV"
  set +a
else
  echo "[FATAL] secrets env not found: $SECRETS_ENV" >&2
  exit 2
fi

export POSTGRES_DB="${POSTGRES_DB:-trading_ai}"
export POSTGRES_USER="${POSTGRES_USER:-trading_admin}"
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"
export PGPASSWORD="${POSTGRES_PASSWORD:-}"

if [[ -z "$PGPASSWORD" ]]; then
  echo "[FATAL] POSTGRES_PASSWORD not loaded from $SECRETS_ENV" >&2
  exit 2
fi

# ─── 2. AC-1b query: 30 min window × 6 active domain × ≥5 row ─────────────
# 為什麼 LEFT JOIN expected：缺 domain 也須出現結果（count=0 才能 alert）;
# 否則 GROUP BY domain 缺 row → loop 漏 domain → 偽 PASS。
SQL=$(cat <<'EOF'
WITH domain_counts AS (
  SELECT domain, COUNT(*) AS row_count
  FROM learning.health_observations
  WHERE observed_at > NOW() - INTERVAL '30 minutes'
  GROUP BY domain
),
expected AS (
  SELECT UNNEST(ARRAY[
    'engine_runtime',
    'pipeline_throughput',
    'api_latency',
    'database_pool',
    'risk_envelope',
    'strategy_quality'
  ]) AS domain
)
SELECT e.domain, COALESCE(d.row_count, 0) AS row_count
FROM expected e
LEFT JOIN domain_counts d ON e.domain = d.domain
ORDER BY row_count ASC;
EOF
)

# ─── 3. Run query (containerized PG) ──────────────────────────────────────
OUTPUT=$(docker exec -i \
  -e PGPASSWORD="$PGPASSWORD" \
  "$PG_CONT" \
  psql \
    -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" \
    -v ON_ERROR_STOP=1 \
    -F'|' -A -t \
    -c "$SQL" 2>&1)
RC=$?

if (( RC != 0 )); then
  echo "[FATAL] PG query failed (rc=$RC):"
  echo "$OUTPUT"
  exit 2
fi

# ─── 4. Parse + alert ─────────────────────────────────────────────────────
FAIL_COUNT=0
while IFS='|' read -r domain count; do
  [[ -z "${domain// }" ]] && continue
  if [[ "$count" -lt 5 ]] 2>/dev/null; then
    echo "[ALERT] domain=$domain count=$count < 5 (AC-1b FAIL)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  else
    (( QUIET == 0 )) && echo "[OK] domain=$domain count=$count >= 5"
  fi
done <<<"$OUTPUT"

# ─── 5. Sentinel mtime touch (per checks_cron_heartbeat.py 範式) ───────────
# 為什麼 sentinel：passive_wait_healthcheck.py [75]-[79] 透過 sentinel mtime
# 推斷 cron 是否按時 fire；本 cron 加入該 family（per PA spec §5.2.2）。
mkdir -p "$SENTINEL_DIR"
touch "$SENTINEL_DIR/ac1b_monthly_healthcheck.last_run"

# ─── 6. Verdict ────────────────────────────────────────────────────────────
if (( FAIL_COUNT > 0 )); then
  echo "[FAIL] AC-1b monthly healthcheck FAIL ($FAIL_COUNT domain < 5 row)"
  exit 1
fi

(( QUIET == 0 )) && echo "[PASS] AC-1b monthly healthcheck PASS (6/6 active domain ≥ 5 row in 30 min window)"
exit 0

#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# 2026-05-16_funding_arb_14d_audit.sh — venv-aware wrapper
# 載入正確 venv + Postgres env 後跑 funding_arb 14d 樣本累積審計（read-only）
#
# Why this wrapper / 為何要 wrapper：
#   Mirror passive_wait_healthcheck.sh 的 venv-resolution + secrets-loading 模式
#   （與 restart_all.sh:212 / fresh_start.sh:188 同源），讓 operator
#   2026-05-16 一行 `bash 2026-05-16_funding_arb_14d_audit.sh` 即可。
#
#   Mirrors passive_wait_healthcheck.sh venv-resolution + secrets-loading
#   pattern (same source as restart_all.sh:212 / fresh_start.sh:188).
#   Operator on 2026-05-16 just runs one line.
#
# Usage / 用法：
#   bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh
#   bash helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.sh --quiet
#
# Exit codes (passthrough from .py):
#   0 = decision rendered (DEPRECATE / INSUFFICIENT / JUDGEMENT / CONTINUE)
#   1 = anomalous data (SL gate bug — fills > 5% notional)
#   2 = DB connect / fatal error
# ═══════════════════════════════════════════════════════════════════════

set -u

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"
AUDIT_PY="$BASE_DIR/helper_scripts/db/audit/2026-05-16_funding_arb_14d_audit.py"

# ─── 1. Locate venv with psycopg2 ──────────────────────────────────────
PROJECT_VENV="$BASE_DIR/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3"
USER_VENV="$HOME/.venv/bin/python3"

if [[ -x "$PROJECT_VENV" ]]; then
    PY="$PROJECT_VENV"
elif [[ -x "$USER_VENV" ]]; then
    PY="$USER_VENV"
else
    PY="python3"
fi

if ! "$PY" -c 'import psycopg2' 2>/dev/null; then
    echo "[FATAL] psycopg2 unavailable in $PY" >&2
    echo "        Tried: $PROJECT_VENV, $USER_VENV, system python3" >&2
    exit 2
fi

# ─── 2. Load Postgres env ──────────────────────────────────────────────
if [[ -f "$SECRETS_ENV" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    set +a
else
    echo "[WARN] secrets env not found: $SECRETS_ENV" >&2
    echo "       POSTGRES_PASSWORD likely unset → DB connect will fail (exit 2)." >&2
fi

export POSTGRES_DB="${POSTGRES_DB:-trading_ai}"
export POSTGRES_USER="${POSTGRES_USER:-ncyu}"
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

# ─── 3. Run audit, forwarding all CLI args ────────────────────────────
exec "$PY" "$AUDIT_PY" "$@"

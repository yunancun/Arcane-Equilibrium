#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# 2026-05-09_3c_7d_audit.sh — venv-aware wrapper for 3C 7d follow-up audit
# 載入正確 venv + Postgres env 後跑 3C 7d 對比審計（read-only）
#
# Why this wrapper / 為何要 wrapper：
#   Mirror passive_wait_healthcheck.sh:1-95 所建立的 venv-resolution +
#   secrets-loading 模式（restart_all.sh:212 / fresh_start.sh:188 同源）。
#   讓 operator 在 2026-05-09 一行 `bash 2026-05-09_3c_7d_audit.sh`
#   即可，不必手動 source env、選 venv、設 PYTHONPATH。
#
#   Mirrors the venv-resolution + secrets-loading pattern established in
#   passive_wait_healthcheck.sh:1-95 (same source as restart_all.sh:212 /
#   fresh_start.sh:188). Operator on 2026-05-09 just runs one line.
#
# Usage / 用法：
#   bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh           # full Markdown
#   bash helper_scripts/db/audit/2026-05-09_3c_7d_audit.sh --quiet   # 只印非 PASS
#
# Exit codes (passthrough from .py):
#   0 = all PASS (or only WARN)
#   1 = ≥1 metric FAIL — operator decision needed
#   2 = DB connect / fatal error
# ═══════════════════════════════════════════════════════════════════════

set -u

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"
AUDIT_PY="$BASE_DIR/helper_scripts/db/audit/2026-05-09_3c_7d_audit.py"

# ─── 1. Locate venv with psycopg2 ──────────────────────────────────────
# Project venv (canonical, used by uvicorn) ＞ user venv ＞ system python.
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

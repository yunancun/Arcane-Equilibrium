#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# passive_wait_healthcheck.sh — venv-aware wrapper for the .py healthcheck
# 載入正確 venv + Postgres env 後跑被動等待健康檢查
#
# Why this wrapper exists / 為何要這個 wrapper:
#   2026-04-23 接手檢查時發現直接跑 `python3 helper_scripts/db/passive_wait_healthcheck.py`
#   會立刻 `[FATAL] DB connect failed: No module named 'psycopg2'`，原因是系統 python3
#   不在 control_api_v1/.venv 內、且 POSTGRES_USER/PASSWORD/DB 環境變數未載入。本 wrapper
#   把 venv 解析、env 載入、密碼引用樣板封裝起來，讓 `passive_wait_healthcheck.sh` 一鍵
#   能跑（與 helper_scripts/restart_all.sh:212 / fresh_start.sh:188 同套來源）。
#
#   Without this wrapper, running the .py directly fails with
#   "No module named 'psycopg2'" because the OS python3 is not the project venv,
#   and POSTGRES_* env vars are never loaded. This wrapper reuses the same
#   secrets-loading pattern as restart_all.sh / fresh_start.sh so that
#   `bash helper_scripts/db/passive_wait_healthcheck.sh` just works.
#
# Usage / 用法:
#   bash helper_scripts/db/passive_wait_healthcheck.sh           # full output
#   bash helper_scripts/db/passive_wait_healthcheck.sh --quiet   # only non-PASS
#
# Exit codes (passthrough from .py):
#   0 = all checks PASS
#   1 = ≥1 FAIL
#   2 = DB connection error (env/credentials issue, fix and retry)
#
# Environment overrides / 可覆寫的環境變數:
#   OPENCLAW_BASE_DIR     repo root (defaults: $HOME/BybitOpenClaw/srv)
#   OPENCLAW_SECRETS_ROOT secrets dir (defaults: $BASE_DIR/secrets)
#   POSTGRES_DB           defaults to "trading_ai" if unset after env load
#   POSTGRES_USER         defaults to "ncyu" if unset after env load
#   POSTGRES_HOST         defaults to "127.0.0.1" if unset
#   POSTGRES_PORT         defaults to "5432" if unset
#
# ═══════════════════════════════════════════════════════════════════════

set -u

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
# Mirror restart_all.sh:31 + fresh_start.sh:60 — secrets sit *next to* srv,
# not inside it. Don't change this default; it must match the canonical layout.
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"
HEALTHCHECK_PY="$BASE_DIR/helper_scripts/db/passive_wait_healthcheck.py"

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

# Sanity: confirm psycopg2 importable; bail with actionable message if not.
if ! "$PY" -c 'import psycopg2' 2>/dev/null; then
    echo "[FATAL] psycopg2 unavailable in $PY" >&2
    echo "        Tried: $PROJECT_VENV, $USER_VENV, system python3" >&2
    echo "        Fix: install via the canonical venv —" >&2
    echo "        $PROJECT_VENV -m pip install psycopg2-binary" >&2
    exit 2
fi

# ─── 1.5 將 BASE_DIR 加入 PYTHONPATH ──────────────────────────────────
# 原因：[20] check_h_state_gateway_freshness 用 importlib 動態 import
# `program_code....h_state_invalidator`；Python 起 .py 時 sys.path[0] 是腳本
# 所在目錄（helper_scripts/db/），不含 BASE_DIR 根。cron wrapper 因為跑相對
# 路徑 `python3 helper_scripts/db/...` 才意外靠 cwd 補上，但 .sh 用絕對路徑
# `exec "$PY" "$HEALTHCHECK_PY"` 不享這個 fallback → 觸發
# `No module named 'program_code'` FAIL。顯式 export PYTHONPATH 讓兩條入口
# 一致且跨 Mac/Linux portable，不依賴呼叫端 cwd。
export PYTHONPATH="$BASE_DIR${PYTHONPATH:+:$PYTHONPATH}"

# ─── 2. Load Postgres env (mirrors restart_all.sh:212 + fresh_start.sh:188) ──
if [[ -f "$SECRETS_ENV" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    set +a
else
    echo "[WARN] secrets env not found: $SECRETS_ENV" >&2
    echo "       POSTGRES_PASSWORD likely unset → DB connect will fail with code 2." >&2
fi

# Sane defaults for non-secret fields (mirrors .py:54-58 fallbacks).
export POSTGRES_DB="${POSTGRES_DB:-trading_ai}"
export POSTGRES_USER="${POSTGRES_USER:-ncyu}"
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

# ─── 3. Run the .py with all forwarded args ───────────────────────────
exec "$PY" "$HEALTHCHECK_PY" "$@"

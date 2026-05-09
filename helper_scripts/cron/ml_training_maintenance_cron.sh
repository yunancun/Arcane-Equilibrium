#!/usr/bin/env bash
# ml_training_maintenance_cron.sh - F-08 ML training maintenance wrapper
#
# Suggested cron entry, installed manually by the operator:
#   17 3 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/ml_training_maintenance_cron.sh
#
# This wrapper schedules operational MLDE maintenance plus the five legacy ML
# scripts flagged as silent-unscheduled by the 2026-05-08 audit:
# thompson_sampling, optuna_optimizer, cpcv_validator, dl3_foundation, and
# weekly_report_generator. It does not install itself.

set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/ml_training_maintenance_cron.log"
STATUS_DIR="${DATA}/status"
STATUS_JSON="${STATUS_DIR}/ml_training_maintenance_status.json"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/ml_training_maintenance_cron.lock.d"

mkdir -p "$LOG_DIR" "$STATUS_DIR" "$LOCK_ROOT"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

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

export PG_HOST PG_PORT PG_DB PG_USER PG_PASSWORD="$PG_PASS"
export OPENCLAW_DATABASE_URL="postgresql://${PG_USER}:${PG_PASS}@${PG_HOST}:${PG_PORT}/${PG_DB}"
export PYTHONPATH="${BASE}/program_code:${BASE}:${PYTHONPATH:-}"

# 注入 IPC secret 路徑 — engine 在 OPENCLAW_IPC_SECRET 設置時要求 __auth 握手
# optuna_optimizer 呼叫 IPC `get_param_ranges` 需要先帶 HMAC-SHA256 token；
# 沒帶 = engine 拒收 first message must be __auth → param_ranges_unavailable
# 對齊 restart_all.sh 的 path：$SECRETS_ROOT/environment_files/ipc_secret.txt
IPC_SECRET_FILE_DEFAULT="$SECRETS_ROOT/environment_files/ipc_secret.txt"
if [[ -z "${OPENCLAW_IPC_SECRET_FILE:-}" && -f "$IPC_SECRET_FILE_DEFAULT" ]]; then
    export OPENCLAW_IPC_SECRET_FILE="$IPC_SECRET_FILE_DEFAULT"
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: ML training maintenance already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

if [[ ! -f "${BASE}/helper_scripts/cron/ml_training_maintenance.py" ]]; then
    echo "[$(ts)] ERROR: ml_training_maintenance.py not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

JOBS="${OPENCLAW_ML_CRON_JOBS:-linucb_trainer,mlde_shadow_advisor,mlde_demo_applier,scorer_trainer,quantile_trainer,thompson_sampling,optuna_optimizer,cpcv_validator,dl3_foundation,weekly_report_generator}"
STRATEGIES="${OPENCLAW_ML_CRON_STRATEGIES:-grid_trading,ma_crossover,bb_breakout,bb_reversion,funding_arb}"
TRAINING_ENGINE_MODES="${OPENCLAW_ML_CRON_TRAINING_ENGINE_MODES:-demo}"
SHADOW_ENGINE_MODES="${OPENCLAW_ML_CRON_SHADOW_ENGINE_MODES:-demo,live_demo}"
LINUCB_ENGINE_MODE="${OPENCLAW_MLDE_LINUCB_ENGINE_MODE:-demo_live_demo}"
AUDIT_ENGINE_MODES="${OPENCLAW_ML_CRON_AUDIT_ENGINE_MODES:-demo,live_demo}"
AUDIT_WEEKDAY="${OPENCLAW_ML_CRON_AUDIT_WEEKDAY:-6}"
MIN_SAMPLES="${OPENCLAW_ML_CRON_MIN_SAMPLES:-200}"
MAX_AGE_DAYS="${OPENCLAW_ML_CRON_MAX_AGE_DAYS:-90}"
OUTPUT_DIR="${OPENCLAW_ML_CRON_OUTPUT_DIR:-${DATA}/models/ml_training_maintenance}"
ONNX_VALIDATE_SAMPLES="${OPENCLAW_ML_CRON_ONNX_VALIDATE_SAMPLES:-1000}"

DRY_RUN_ARGS=()
case "${OPENCLAW_ML_CRON_DRY_RUN:-0}" in
    1|true|TRUE|yes|YES|on|ON)
        DRY_RUN_ARGS=(--dry-run)
        ;;
esac

cd "$BASE"

echo "[$(ts)] === ML training maintenance start (BASE=$BASE JOBS=$JOBS) ===" >> "$LOG"

if python3 helper_scripts/cron/ml_training_maintenance.py \
        --base-dir "$BASE" \
        --dsn "$OPENCLAW_DATABASE_URL" \
        --jobs "$JOBS" \
        --strategies "$STRATEGIES" \
        --training-engine-modes "$TRAINING_ENGINE_MODES" \
        --shadow-engine-modes "$SHADOW_ENGINE_MODES" \
        --audit-engine-modes "$AUDIT_ENGINE_MODES" \
        --audit-weekday "$AUDIT_WEEKDAY" \
        --linucb-engine-mode "$LINUCB_ENGINE_MODE" \
        --min-samples "$MIN_SAMPLES" \
        --max-age-days "$MAX_AGE_DAYS" \
        --output-dir "$OUTPUT_DIR" \
        --onnx-validate-samples "$ONNX_VALIDATE_SAMPLES" \
        --status-json "$STATUS_JSON" \
        ${DRY_RUN_ARGS[@]+"${DRY_RUN_ARGS[@]}"} >> "$LOG" 2>&1; then
    echo "[$(ts)] === ML training maintenance end OK ===" >> "$LOG"
    exit 0
fi

rc=$?
echo "[$(ts)] === ML training maintenance end FAIL rc=${rc} ===" >> "$LOG"
exit "$rc"

#!/usr/bin/env bash
# flash_dip_execution_realism_cron.sh - read-only FlashDip shallow-K execution realism.
#
# Suggested Linux cron:
#   29 6 * * * OPENCLAW_BASE_DIR=$HOME/BybitOpenClaw/srv OPENCLAW_DATA_DIR=/tmp/openclaw \
#       $HOME/BybitOpenClaw/srv/helper_scripts/cron/flash_dip_execution_realism_cron.sh
#
# Hard boundary:
#   read-only PG via libpq PGOPTIONS plus helper-side readonly session. Writes
#   are limited to local research artifacts, status logs, heartbeat, and lock
#   files under OPENCLAW_DATA_DIR. No order, auth, risk, strategy flag, or
#   runtime mutation.
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/flash_dip_execution_realism_cron.log"
STATUS_LOG="${LOG_DIR}/flash_dip_execution_realism.log"
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/flash_dip_execution_realism_cron.lock.d"
HEARTBEAT_DIR="${DATA}/cron_heartbeat"
ARTIFACT_DIR="${DATA}/research/tail_dislocation_meanrev"

K_PCT="${OPENCLAW_FLASH_DIP_EXEC_REALISM_K_PCT:-6}"
HOLD="${OPENCLAW_FLASH_DIP_EXEC_REALISM_HOLD:-2}"
CAP="${OPENCLAW_FLASH_DIP_EXEC_REALISM_CAP:-3}"
NOTIONAL_FRAC="${OPENCLAW_FLASH_DIP_EXEC_REALISM_NOTIONAL_FRAC:-0.005}"
TIMEFRAME="${OPENCLAW_FLASH_DIP_EXEC_REALISM_TIMEFRAME:-1m}"
BUFFER_BPS="${OPENCLAW_FLASH_DIP_EXEC_REALISM_BUFFER_BPS:-0,5,10,25,50}"
MARKOUT_MINUTES="${OPENCLAW_FLASH_DIP_EXEC_REALISM_MARKOUT_MINUTES:-5,15,30,60,240}"
GATE_BUFFER_BPS="${OPENCLAW_FLASH_DIP_EXEC_REALISM_GATE_BUFFER_BPS:-10}"
MIN_FILLED="${OPENCLAW_FLASH_DIP_EXEC_REALISM_MIN_FILLED:-30}"
MIN_DAYS="${OPENCLAW_FLASH_DIP_EXEC_REALISM_MIN_DAYS:-20}"
STALE_LOCK_MIN="${OPENCLAW_FLASH_DIP_EXEC_REALISM_STALE_LOCK_MIN:-180}"

mkdir -p "$LOG_DIR" "$LOCK_ROOT" "$HEARTBEAT_DIR" "$ARTIFACT_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

PYBIN="${OPENCLAW_PYTHON_BIN:-}"
if [[ -z "$PYBIN" ]]; then
    if [[ -x "$HOME/.venv/bin/python" ]]; then
        PYBIN="$HOME/.venv/bin/python"
    else
        PYBIN="python3"
    fi
fi

touch "$HEARTBEAT_DIR/flash_dip_execution_realism.last_fire" 2>/dev/null || true

validate_numeric() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be numeric: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_int() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be an integer: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_csv_numeric() {
    local name="$1"
    local value="$2"
    if [[ ! "$value" =~ ^[0-9]+([.][0-9]+)?(,[0-9]+([.][0-9]+)?)*$ ]]; then
        echo "[$(ts)] FATAL: ${name} must be comma-separated numeric values: ${value}" | tee -a "$LOG" >&2
        exit 2
    fi
}

validate_numeric "OPENCLAW_FLASH_DIP_EXEC_REALISM_K_PCT" "$K_PCT"
validate_int "OPENCLAW_FLASH_DIP_EXEC_REALISM_HOLD" "$HOLD"
if [[ "$CAP" != "none" && "$CAP" != "unlimited" && "$CAP" != "all" ]]; then
    validate_int "OPENCLAW_FLASH_DIP_EXEC_REALISM_CAP" "$CAP"
fi
validate_numeric "OPENCLAW_FLASH_DIP_EXEC_REALISM_NOTIONAL_FRAC" "$NOTIONAL_FRAC"
validate_csv_numeric "OPENCLAW_FLASH_DIP_EXEC_REALISM_BUFFER_BPS" "$BUFFER_BPS"
validate_csv_numeric "OPENCLAW_FLASH_DIP_EXEC_REALISM_MARKOUT_MINUTES" "$MARKOUT_MINUTES"
validate_numeric "OPENCLAW_FLASH_DIP_EXEC_REALISM_GATE_BUFFER_BPS" "$GATE_BUFFER_BPS"
validate_int "OPENCLAW_FLASH_DIP_EXEC_REALISM_MIN_FILLED" "$MIN_FILLED"
validate_int "OPENCLAW_FLASH_DIP_EXEC_REALISM_MIN_DAYS" "$MIN_DAYS"

if [[ -d "$LOCK_DIR" ]] && [[ -n "$(find "$LOCK_DIR" -maxdepth 0 -mmin +"$STALE_LOCK_MIN" 2>/dev/null)" ]]; then
    echo "[$(ts)] WARN: stale lock (>${STALE_LOCK_MIN}min) cleared: $LOCK_DIR" >> "$LOG"
    rmdir "$LOCK_DIR" 2>/dev/null || true
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: FlashDip execution realism already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    local rc=$?
    rmdir "$LOCK_DIR" 2>/dev/null || true
    return "$rc"
}
trap release_lock EXIT INT TERM

SCRIPT="$BASE/helper_scripts/research/tail_dislocation_meanrev/shallow_retune_execution_realism.py"
if [[ ! -f "$SCRIPT" ]]; then
    echo "[$(ts)] FATAL: execution realism helper missing: $SCRIPT" | tee -a "$LOG" >&2
    exit 2
fi

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

export PGHOST="$PG_HOST" PGPORT="$PG_PORT" PGDATABASE="$PG_DB" PGUSER="$PG_USER" PGPASSWORD="$PG_PASS"
export PGOPTIONS="-c default_transaction_read_only=on"

STAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
OUT="${ARTIFACT_DIR}/shallow_retune_execution_realism_${STAMP}.json"
LATEST="${ARTIFACT_DIR}/shallow_retune_execution_realism_latest.json"

ARGS=(
    "$SCRIPT"
    --out "$OUT"
    --k-pct "$K_PCT"
    --hold "$HOLD"
    --cap "$CAP"
    --notional-frac "$NOTIONAL_FRAC"
    --timeframe "$TIMEFRAME"
    --buffer-bps "$BUFFER_BPS"
    --markout-minutes "$MARKOUT_MINUTES"
    --gate-buffer-bps "$GATE_BUFFER_BPS"
    --min-filled "$MIN_FILLED"
    --min-days "$MIN_DAYS"
)

echo "[$(ts)] === FlashDip execution realism start (k_pct=${K_PCT} hold=${HOLD} cap=${CAP} gate_buffer=${GATE_BUFFER_BPS}bps) ===" >> "$LOG"
rc=0
(
    cd "$BASE"
    export PYTHONPATH="$BASE/helper_scripts/research/tail_dislocation_meanrev${PYTHONPATH:+:$PYTHONPATH}"
    "$PYBIN" "${ARGS[@]}"
) >> "$LOG" 2>&1 || rc=$?

STATUS_JSON=$(REALISM_OUT="$OUT" REALISM_RC="$rc" REALISM_LATEST="$LATEST" "$PYBIN" - <<'PY' 2>>"$LOG" || true
import datetime
import hashlib
import json
import os
import shutil

out = os.environ["REALISM_OUT"]
latest = os.environ["REALISM_LATEST"]
rc = int(os.environ["REALISM_RC"])
status = {
    "ts_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "check": "flash_dip_execution_realism",
    "rc": rc,
    "artifact_path": out,
    "latest_path": latest,
    "parse_ok": False,
    "verdict_status": None,
    "fail_reasons": [],
    "candidate_label": None,
    "k_pct": None,
    "gate_buffer_bps": None,
    "gate_filled": None,
    "gate_distinct_days": None,
    "gate_annret": None,
    "gate_maxdd": None,
    "short_exit_status": None,
    "best_short_exit_buffer_bps": None,
    "best_short_exit_horizon": None,
    "best_short_exit_annret": None,
    "best_short_exit_maxdd": None,
    "best_short_exit_n_filled": None,
    "best_short_exit_days": None,
    "boundary": "counterfactual_only_not_promotion_evidence",
}
try:
    with open(out, "rb") as f:
        blob = f.read()
    report = json.loads(blob.decode("utf-8"))
    sha = hashlib.sha256(blob).hexdigest()
    status["sha256"] = sha
    verdict = report.get("verdict") or {}
    params = report.get("params") or {}
    daily = report.get("daily_candidate") or {}
    short_exit = report.get("short_exit_opportunity") or {}
    best_short = short_exit.get("best") or {}
    status.update({
        "parse_ok": True,
        "version": report.get("version"),
        "generated_utc": report.get("generated_utc"),
        "verdict_status": verdict.get("status"),
        "fail_reasons": verdict.get("fail_reasons") or [],
        "candidate_label": params.get("candidate_label"),
        "k_pct": params.get("k_pct"),
        "gate_buffer_bps": verdict.get("gate_buffer_bps"),
        "daily_n_raw": daily.get("n_raw"),
        "daily_n_kept_after_cap": daily.get("n_kept_after_cap"),
        "daily_n_kept_with_intraday_day": daily.get("n_kept_with_intraday_day"),
        "intraday_coverage_rate_vs_kept": daily.get("intraday_coverage_rate_vs_kept"),
        "short_exit_status": short_exit.get("status"),
        "best_short_exit_buffer_bps": best_short.get("execution_buffer_bps"),
        "best_short_exit_horizon": best_short.get("horizon"),
        "best_short_exit_annret": best_short.get("annualized_return"),
        "best_short_exit_maxdd": best_short.get("max_drawdown"),
        "best_short_exit_n_filled": best_short.get("n_filled_proxy"),
        "best_short_exit_days": best_short.get("n_distinct_filled_days"),
    })
    gate_buffer = verdict.get("gate_buffer_bps")
    for row in report.get("buffer_sensitivity") or []:
        try:
            if abs(float(row.get("execution_buffer_bps")) - float(gate_buffer)) > 1e-12:
                continue
        except (TypeError, ValueError):
            continue
        fn = row.get("fixed_notional") or {}
        status["gate_filled"] = row.get("n_filled_proxy")
        status["gate_distinct_days"] = row.get("n_distinct_filled_days")
        status["gate_annret"] = fn.get("annualized_return")
        status["gate_maxdd"] = fn.get("max_drawdown")
        break
    shutil.copyfile(out, latest)
    with open(latest + ".sha256", "w", encoding="utf-8") as f:
        f.write(f"{sha}  {os.path.basename(latest)}\n")
except FileNotFoundError:
    status["error"] = "artifact_missing"
except Exception as exc:
    status["error"] = exc.__class__.__name__

print(json.dumps(status, separators=(",", ":"), sort_keys=True))
PY
)

if [[ -z "$STATUS_JSON" ]]; then
    echo "[$(ts)] === FlashDip execution realism end FAIL rc=${rc} (status synthesis empty) ===" >> "$LOG"
    exit 1
fi

echo "$STATUS_JSON" >> "$STATUS_LOG"
echo "[$(ts)] status: $STATUS_JSON" >> "$LOG"
echo "[$(ts)] === FlashDip execution realism end rc=${rc} ===" >> "$LOG"
exit "$rc"

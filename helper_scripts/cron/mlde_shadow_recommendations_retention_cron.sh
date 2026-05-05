#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# mlde_shadow_recommendations_retention_cron.sh — REF-20 Sprint D R8
# Daily cron: prune mlde_shadow_recommendations replay-derived 30d / real_outcome 90d
# 每日 cron：清 learning.mlde_shadow_recommendations replay-derived 30d / real_outcome 90d
# ═══════════════════════════════════════════════════════════════════════════
#
# MODULE_NOTE (中):
#   REF-20 Sprint D R8 maintenance pass。MIT §2.4 推薦：replay-derived row
#   30-60d 保留，real_outcome row 90d 保留，避免 ML training surface 被
#   stale row 拉低 signal。本 cron 透過 V056 land 的 PL/pgSQL 函數
#   `learning.prune_mlde_shadow_recommendations` 執行，dry-run 模式為預設
#   保護。
#
#   設計：
#   - dry-run 模式為預設：環境變數 `OPENCLAW_MLDE_RETENTION_APPLY=1` 才真
#     DELETE。先 cron 一週驗候選計數穩定再 flip apply。
#   - 保留期可調：
#       OPENCLAW_MLDE_REPLAY_RETENTION_DAYS  (default 30)
#       OPENCLAW_MLDE_REAL_RETENTION_DAYS    (default 90)
#   - 每 cycle DELETE 上限 100k（V056 hard cap）；防長鎖。
#   - V056 不存在時 cron 乾淨 exit 0（pre-deploy graceful fallback）。
#
#   Idempotent：read-only dry-run 永遠回相同 candidate count；apply 模式第
#   二次跑 candidate count 應減為 0（除新 row 落地）。
#
# MODULE_NOTE (EN):
#   REF-20 Sprint D R8 maintenance pass. MIT §2.4 recommends replay-derived
#   30-60d retention + real_outcome 90d retention, avoiding ML training
#   surface dilution by stale rows. This cron drives V056 PL/pgSQL function
#   `learning.prune_mlde_shadow_recommendations`; dry-run mode default for
#   safety.
#
#   Design:
#   - Dry-run default: env var `OPENCLAW_MLDE_RETENTION_APPLY=1` flips to
#     real DELETE. Run cron 1 week to verify candidate count stable before
#     flipping apply.
#   - Retention tunable:
#       OPENCLAW_MLDE_REPLAY_RETENTION_DAYS  (default 30)
#       OPENCLAW_MLDE_REAL_RETENTION_DAYS    (default 90)
#   - Per-cycle DELETE capped at 100k rows (V056 hard cap); avoids long lock.
#   - V056 absent → cron exits 0 cleanly (pre-deploy graceful fallback).
#
#   Idempotent: read-only dry-run yields same candidate count; apply-mode
#   second run yields 0 candidates (modulo new rows landing).
#
# Spec source / 規格來源:
#   - REF-20 Sprint D R8 plan §6.R8 §1.2 retention policy
#   - sql/migrations/V056__mlde_shadow_recommendations_retention_policy.sql
#   - docs/CCAgentWorkSpace/MIT/.../2026-05-05--ref20_r6_r7_capability_risk.md §2.4
#
# Suggested cron entry (operator manually adds via `crontab -e`):
# 建議 cron 條目（operator `crontab -e` 加）：
#   0 4 * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/mlde_shadow_recommendations_retention_cron.sh"
#
# Exit codes:
#   0  Success (dry-run completed OR apply-mode completed OR V056 absent fallback)
#   1  PG connection / function execution error
#   2  PG creds incomplete in secrets env file
#
# Healthcheck cover / 健康檢查覆蓋：
#   `[46] mlde_shadow_retention_status` reads candidate count + last apply
#   age；候選數異常增長 / cron 死亡 / V056 缺均會被 sentinel 偵測。
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration / 配置 ───────────────────────────────────────────
BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/mlde_shadow_recommendations_retention_cron.log"

REPLAY_RETENTION_DAYS="${OPENCLAW_MLDE_REPLAY_RETENTION_DAYS:-30}"
REAL_RETENTION_DAYS="${OPENCLAW_MLDE_REAL_RETENTION_DAYS:-90}"
APPLY_FLAG="${OPENCLAW_MLDE_RETENTION_APPLY:-0}"
MAX_ROWS="${OPENCLAW_MLDE_RETENTION_MAX_ROWS:-100000}"

mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# ─── PG creds sourcing (mirror edge_label_backfill_cron.sh pattern) ──
# 對齊 edge_label_backfill_cron.sh 從 secrets env file 抓 PG creds。
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
export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"

# ─── Overlap lock ───────────────────────────────────────────────────
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/mlde_shadow_recommendations_retention_cron.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: retention cron already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

cd "$BASE"

# ─── Determine apply mode / 決定 apply 模式 ────────────────────────
APPLY_BOOL="false"
if [[ "$APPLY_FLAG" == "1" ]]; then
    APPLY_BOOL="true"
fi

echo "[$(ts)] === retention cron start (BASE=$BASE replay=${REPLAY_RETENTION_DAYS}d real=${REAL_RETENTION_DAYS}d apply=$APPLY_BOOL max_rows=$MAX_ROWS) ===" >> "$LOG"

# ─── V056 graceful absent check ─────────────────────────────────────
# V056 land 前 graceful exit 0；不阻塞 cron schedule install.
# Pre-V056 deploy graceful exit 0; does not block cron install timing.
V056_PRESENT=$(psql "$OPENCLAW_DATABASE_URL" -tAc "SELECT EXISTS (SELECT 1 FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname='learning' AND p.proname='prune_mlde_shadow_recommendations');" 2>>"$LOG" || echo "false")

if [[ "$V056_PRESENT" != "t" ]]; then
    echo "[$(ts)] SKIP: V056 prune_mlde_shadow_recommendations function absent (pre-deploy)" >> "$LOG"
    exit 0
fi

# ─── Run V056 retention function / 跑 V056 保留期函數 ─────────────
RC=0
psql "$OPENCLAW_DATABASE_URL" -tA -F '|' -c \
    "SELECT * FROM learning.prune_mlde_shadow_recommendations(${REPLAY_RETENTION_DAYS}, ${REAL_RETENTION_DAYS}, ${APPLY_BOOL}, ${MAX_ROWS});" \
    >> "$LOG" 2>&1 || RC=$?

if [[ $RC -eq 0 ]]; then
    echo "[$(ts)] === retention cron OK (apply=$APPLY_BOOL) ===" >> "$LOG"
    # Touch sentinel timestamp file for healthcheck [46] consumer.
    # 觸碰 sentinel 時間戳檔，供 healthcheck [46] 消費。
    touch "${DATA}/mlde_shadow_recommendations_retention_last_run"
else
    echo "[$(ts)] === retention cron FAIL (rc=$RC apply=$APPLY_BOOL) ===" >> "$LOG"
fi

exit $RC

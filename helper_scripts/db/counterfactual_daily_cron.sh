#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# counterfactual_daily_cron.sh — EDGE-DIAG-1 Phase 4 daily refresh wrapper
# 反事實退場回放每日定時 wrapper（Phase 4 被動等待 healthcheck 的 WRITE 端）
#
# Why this wrapper exists / 為何要這個 wrapper:
#   EDGE-DIAG-1 Phase 3（strategy-scoped Gate 1 fallback deploy）因 post-P013-clean
#   bucket 僅 74 rows / 37 cf_fired（2026-04-24 PM Phase 2 rerun）未達 FM
#   bootstrap-CI 門檻 ≥200 rows 而延後。CLAUDE.md §七「被動等待 TODO 必附
#   healthcheck」強制要求：此 wrapper 負責每日重跑 counterfactual_exit_replay.py
#   刷新 `counterfactual_exit_replay_latest.json`，讓
#   `passive_wait_healthcheck.py check[11]` 可讀到當日最新 post-P013-clean 樣本數。
#
#   Phase 4 分工：本 wrapper = WRITE 端（每日 06:00 UTC 刷新 latest JSON）；
#   passive_wait_healthcheck.py check[11] = READ 端（任意時刻讀 latest JSON +
#   判 PASS / WARN / FAIL + 寫 audit/daily/YYYYMMDD.json trend 歷史）。
#
#   EDGE-DIAG-1 Phase 3 (strategy-scoped Gate 1 fallback deploy) was deferred
#   2026-04-24 because the post-P013-clean bucket had only 74 rows / 37 cf_fired
#   (2026-04-24 PM Phase 2 rerun) — below the FM bootstrap-CI threshold of
#   ≥200 rows per strategy. CLAUDE.md §七 rule "any passive-wait TODO must
#   ship a healthcheck" mandates this wrapper: it refreshes the latest
#   counterfactual_exit_replay JSON daily so `check_counterfactual_clean_window_growth`
#   (check [11]) can read a fresh sample.
#
# Why --days 2 / 為何 --days 2:
#   Picks up the last 48 hours of exits, skipping the historical vacuum/pre-P013
#   buckets for faster iteration. The split-window bucket logic still tags each
#   row to its correct window (pre-T3 / T3-T4-vacuum / post-T4-pre-P013 /
#   post-P013-clean), so 2-day window naturally accumulates only post-P013-clean
#   rows. For full historical re-audit use a longer --days manually.
#   取最近 48 小時資料，歷史 vacuum/pre-P013 bucket 跳過以加快迭代；
#   split-window 仍依時間 tag 每 row 到正確 bucket，2 日窗自然只累 post-P013-clean。
#
# Usage / 用法:
#   Operator crontab entry / 建議 crontab:
#       0 6 * * * /full/path/to/srv/helper_scripts/db/counterfactual_daily_cron.sh
#
#   Manual one-shot test / 手動測試（Linux trade-core）:
#       bash helper_scripts/db/counterfactual_daily_cron.sh
#
# Exit codes / 退出碼:
#   Mirrors python3 counterfactual_exit_replay.py — 0 on success, non-zero on
#   DB connect failure / SQL error / bucket assertion failure.
#
# Environment / 環境變數:
#   OPENCLAW_BASE_DIR       repo root (default: $HOME/BybitOpenClaw/srv)
#   OPENCLAW_DATA_DIR       runtime dir (default: /tmp/openclaw) — audit/ lives here
#   OPENCLAW_SECRETS_ROOT   secrets dir (default: $HOME/BybitOpenClaw/secrets)
#   POSTGRES_*              loaded from $SECRETS_ROOT/environment_files/basic_system_services.env
#
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
SECRETS_ENV="$SECRETS_ROOT/environment_files/basic_system_services.env"

# SW-006 (Batch E): overlap lock — prevent concurrent daily runs.
# SW-006（Batch E）：重疊鎖，避免每日任務重入。
LOCK_ROOT="$DATA_DIR/locks"
LOCK_DIR="$LOCK_ROOT/counterfactual_daily_cron.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[SKIP] counterfactual_daily_cron already running (lock held)" >&2
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# ─── 1. Load Postgres env (mirrors passive_wait_healthcheck.sh:70-78) ───
if [[ -f "$SECRETS_ENV" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    set +a
else
    echo "[WARN] secrets env not found: $SECRETS_ENV" >&2
    echo "       relying on POSTGRES_* already exported — DB connect may fail." >&2
fi

# Sane defaults for non-secret fields.
export POSTGRES_DB="${POSTGRES_DB:-trading_ai}"
export POSTGRES_USER="${POSTGRES_USER:-ncyu}"
export POSTGRES_HOST="${POSTGRES_HOST:-127.0.0.1}"
export POSTGRES_PORT="${POSTGRES_PORT:-5432}"

# ─── 2. Activate venv ──────────────────────────────────────────────────
# Primary venv path per operator convention ($HOME/.venv/bin/activate).
# 主 venv 路徑按 operator 慣例（$HOME/.venv/bin/activate）。
VENV_ACTIVATE="${VENV_ACTIVATE:-$HOME/.venv/bin/activate}"
if [[ -f "$VENV_ACTIVATE" ]]; then
    # shellcheck disable=SC1090
    source "$VENV_ACTIVATE"
else
    echo "[WARN] venv activate script not found: $VENV_ACTIVATE" >&2
    echo "       falling back to system python3 — psycopg2 must be globally importable." >&2
fi

# ─── 3. cd to repo root ────────────────────────────────────────────────
if [[ ! -d "$BASE_DIR" ]]; then
    echo "[FATAL] OPENCLAW_BASE_DIR does not exist: $BASE_DIR" >&2
    exit 2
fi
cd "$BASE_DIR"

# ─── 4. Ensure audit dir exists (log destination) ──────────────────────
mkdir -p "$DATA_DIR/audit"
LOG="$DATA_DIR/audit/counterfactual_daily_cron.log"

# ─── 5. Invoke counterfactual_exit_replay.py ───────────────────────────
# --days 2           : last 48h window (post-P013-clean bucket only, fast)
# --v2-parity        : Rust v2 4-Gate parity instead of v1 linear
# --split-window     : 3-bucket aggregation (required for by_window in JSON)
# --cost-model fee_only : empirically meaningful cost model (proxy is degenerate)
# --bootstrap-ci     : FM bootstrap CI (for Phase 3 gate)
# --per-strategy-median : robust aggregation hint
# --trimmed-mean-pct 5  : trim top/bottom 5% per strategy
echo "==== counterfactual_daily_cron.sh $(date -u +%Y-%m-%dT%H:%M:%SZ) ====" | tee -a "$LOG"
python3 helper_scripts/db/counterfactual_exit_replay.py \
    --days 2 \
    --v2-parity \
    --split-window \
    --cost-model fee_only \
    --bootstrap-ci \
    --per-strategy-median \
    --trimmed-mean-pct 5 2>&1 | tee -a "$LOG"

# `set -o pipefail` above means tee failure does not mask python failure:
# exit status is python3's via PIPESTATUS[0].
# `set -o pipefail` 令 python 失敗不被 tee 遮蔽，PIPESTATUS[0] = python 的 exit code。
exit "${PIPESTATUS[0]}"

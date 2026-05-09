#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════
# edge_label_backfill_cron.sh — periodic edge label backfill wrapper
# 邊緣標籤回填周期任務（cron 用 wrapper）
#
# MODULE_NOTE (EN): LG5-W3-FUP-2 Fix 1 (2026-05-02). MIT diagnosis traced
#   `[42b]` healthcheck FAIL → `attribution_chain_ok=false 86%+` →
#   `program_code/ml_training/edge_label_backfill.py` was on-demand only,
#   no cron schedule. Production 7d window showed grid_trading 75% /
#   ma_crossover 45% rows with NULL `label_net_edge_bps`. This wrapper
#   runs the backfill against demo + live_demo every 30 minutes so the
#   downstream `attribution_chain_ok` ratio recovers within ~24h.
#
#   Design:
#   - Two engine_mode passes per cron tick (demo + live_demo) to mirror
#     the producer (`mlde_demo_applier._compute_attribution_chain_ratio_by_strategy`
#     reads `engine_mode IN ('demo','live_demo')`, see checks_governance.py).
#   - fail-loud: any pass returning non-zero aborts the cron tick (exit 1)
#     so the cron mailer / journald surfaces the failure. The backfill
#     itself wraps DB ops in try/conn.rollback so partial state is safe.
#   - log to `$OPENCLAW_DATA_DIR/logs/edge_label_backfill_cron.log` for
#     manual triage; healthcheck `[43]` reads `max(label_filled_at)` from
#     the DB rather than parsing this log so log loss != silent failure.
#
# MODULE_NOTE (中): LG5-W3-FUP-2 Fix 1（2026-05-02）。MIT diagnosis 追蹤
#   `[42b]` healthcheck FAIL → `attribution_chain_ok=false 86%+` →
#   `edge_label_backfill.py` 純 on-demand 無 cron。生產 7d window 顯示
#   grid_trading 75% / ma_crossover 45% rows `label_net_edge_bps` 為 NULL。
#   本 wrapper 每 30 分鐘對 demo + live_demo 各跑一次，使下游
#   `attribution_chain_ok` ratio ~24h 內恢復。
#
#   設計：
#   - 每 cron tick 跑 2 個 engine_mode（demo + live_demo），對齊 producer
#     `mlde_demo_applier` 用的 `engine_mode IN ('demo','live_demo')`。
#   - fail-loud：任一 pass 非零 exit 即整個 cron tick 退出 1，cron mailer
#     / journald 立刻看到。backfill 本身內部 try/rollback，部分狀態安全。
#   - log 寫 `$OPENCLAW_DATA_DIR/logs/edge_label_backfill_cron.log`，僅供
#     手動 triage；healthcheck `[43]` 直接讀 DB `max(label_filled_at)`，
#     log 丟失不會掩蓋失敗（DB 真值優先）。
#
# Suggested cron entry (operator manually adds via `crontab -e`).
# Use the absolute path to this script under the operator's repo root —
# Linux trade-core convention is "$HOME/BybitOpenClaw/srv/helper_scripts/cron/...";
# Mac dev convention follows OPENCLAW_BASE_DIR (see CLAUDE.md §六).
# 建議 cron 條目（operator `crontab -e` 加）。用本 script 在 operator
# repo root 下的絕對路徑；Linux trade-core 慣例為
# "$HOME/BybitOpenClaw/srv/helper_scripts/cron/..."；Mac dev 從
# OPENCLAW_BASE_DIR 推（見 CLAUDE.md §六）。
#   */30 * * * * "$OPENCLAW_BASE_DIR/helper_scripts/cron/edge_label_backfill_cron.sh"
#
# Suggested env vars (crontab uses literal values not shell expansion, so
# operator must inline the resolved paths in crontab itself):
# 建議環境變量（crontab 不會做 shell 展開，operator 須直接在 crontab 內
# 寫已解析的 literal 路徑）：
#   OPENCLAW_BASE_DIR=<repo root>           # e.g. $HOME/BybitOpenClaw/srv on Linux
#   OPENCLAW_DATA_DIR=<runtime root>        # e.g. /tmp/openclaw on Linux
#   OPENCLAW_LG5_LABEL_BACKFILL_BATCH_LIMIT=5000
#
# Healthcheck cover:
# 健康檢查覆蓋：
#   `[43] label_backfill_freshness` reads max(label_filled_at) every cron
#   pass; PASS <2h, WARN <6h, FAIL >=6h — silent cron death detected
#   without parsing this wrapper's log.
#   `[43] label_backfill_freshness` 每次 cron 跑 healthcheck 時讀
#   max(label_filled_at)；PASS <2h、WARN <6h、FAIL >=6h — 不依賴 log
#   即可偵測 cron 靜默死亡。
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

# ─── Configuration / 配置 ───────────────────────────────────────────
# Base dir defaults to Linux operator's repo root; Mac dev sets
# OPENCLAW_BASE_DIR explicitly per CLAUDE.md §六 cross-platform path policy.
# Mac dev 須顯式設 OPENCLAW_BASE_DIR；Linux 預設 ~/BybitOpenClaw/srv。
BASE="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
BATCH="${OPENCLAW_LG5_LABEL_BACKFILL_BATCH_LIMIT:-5000}"
LOG_DIR="${DATA}/logs"
LOG="${LOG_DIR}/edge_label_backfill_cron.log"

# Need LOG_DIR ready before any `echo >> "$LOG"` so the FATAL branches below
# don't lose their message to a missing parent dir.
# 在後面任何 `echo >> "$LOG"` 之前先確保 LOG_DIR 存在，避免 FATAL 訊息因
# 父目錄不存在而消失。
mkdir -p "$LOG_DIR"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

# ─── PG creds sourcing (LG5-W3-FUP-3-CRON-ENV) ──────────────────────
# Cron has a barebones environment (no shell rc, no operator login env) so
# OPENCLAW_DATABASE_URL / POSTGRES_* are NOT inherited from the operator's
# interactive shell. The downstream consumer
# `program_code/ml_training/edge_label_backfill.py:_open_conn` requires either
# OPENCLAW_DATABASE_URL or the full set of POSTGRES_* env vars; without them
# psycopg2 raises `OperationalError: fe_sendauth: no password supplied` and
# the cron tick fails silently from the operator's shell perspective.
#
# Mirror `helper_scripts/linux_bootstrap_db.sh:41-45` (the more complete
# sibling pattern — `passive_wait_healthcheck_cron.sh:43-44` only sources
# PG_PASS and hardcodes user/db/host/port, which couples it to one slot).
# This wrapper sources all 5 POSTGRES_* keys from the secrets env file with
# HOST/PORT fallbacks (the env file does not always include them).
#
# cron 的 environment 極簡（無 shell rc，無 operator login env），所以
# OPENCLAW_DATABASE_URL / POSTGRES_* 不會從 operator 互動 shell 繼承。下游
# `edge_label_backfill.py:_open_conn` 需要 OPENCLAW_DATABASE_URL 或完整
# POSTGRES_* env vars，缺失則 psycopg2 拋
# `OperationalError: fe_sendauth: no password supplied`，從 operator shell
# 看是 cron tick 靜默失敗。
#
# 對齊 `linux_bootstrap_db.sh:41-45` 完整 sibling pattern（
# `passive_wait_healthcheck_cron.sh:43-44` 只抓 PG_PASS 並 hardcode
# user/db/host/port，把它綁定到一個 slot）。本 wrapper 從 secrets env file
# 抓 5 個 POSTGRES_* keys，HOST/PORT 缺失時 fallback（env file 不一定含）。
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_FILE="$SECRETS_ROOT/environment_files/basic_system_services.env"
if [[ ! -f "$ENV_FILE" ]]; then
    echo "[$(ts)] FATAL: env file missing: $ENV_FILE" | tee -a "$LOG" >&2
    exit 2
fi
# Note: `grep | cut` exits non-zero when the key is absent; under `set -e` that
# would short-circuit *before* the explicit empty-check below, masking the
# FATAL message. Trail `|| true` per command so missing keys reach the check.
# 注意：`grep | cut` 在 key 不存在時 exit 非零，set -e 會在下方明確空檢查
# 之前先 short-circuit、淹沒 FATAL 訊息。每行加 `|| true` 讓缺失 key 走
# 到後面的明確檢查。
PG_PASS=$(grep '^POSTGRES_PASSWORD=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_USER=$(grep '^POSTGRES_USER=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_DB=$(grep '^POSTGRES_DB=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_HOST=$(grep '^POSTGRES_HOST=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
PG_PORT=$(grep '^POSTGRES_PORT=' "$ENV_FILE" 2>/dev/null | cut -d= -f2- || true)
# Fallback when env file omits HOST/PORT (Mac + Linux both observed lacking
# POSTGRES_HOST in `basic_system_services.env`) — defaults match
# `helper_scripts/linux_bootstrap_db.sh:44-45`.
# env file 不一定含 HOST/PORT（Mac + Linux `basic_system_services.env` 兩端
# 實測都缺 POSTGRES_HOST）— 預設對齊 `linux_bootstrap_db.sh:44-45`。
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
if [[ -z "$PG_PASS" || -z "$PG_USER" || -z "$PG_DB" ]]; then
    echo "[$(ts)] FATAL: PG creds incomplete in $ENV_FILE (require POSTGRES_PASSWORD, POSTGRES_USER, POSTGRES_DB)" | tee -a "$LOG" >&2
    exit 2
fi
export OPENCLAW_DATABASE_URL="postgresql://redacted@${PG_HOST}:${PG_PORT}/${PG_DB}"

# ─── Overlap lock (mirror cron_observer_cycle.sh SW-006 pattern) ────
# 防止 30min cron 與長跑 backfill 互疊（SQL 兩 pass × 5000 row 偶可 >30s）。
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/edge_label_backfill_cron.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(ts)] SKIP: edge_label_backfill cron already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# ─── Sanity: BASE must contain the backfill module / BASE 須含 module ─
if [[ ! -f "${BASE}/program_code/ml_training/edge_label_backfill.py" ]]; then
    echo "[$(ts)] ERROR: edge_label_backfill.py not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

cd "$BASE"

echo "[$(ts)] === edge_label_backfill cron start (BASE=$BASE BATCH=$BATCH) ===" >> "$LOG"

# ─── Two engine_mode passes / 兩 engine_mode 連跑 ───────────────────
# Order: demo first (more rows / faster signal), live_demo second.
# Failure in either aborts the tick — operator alarm via cron mail.
# 順序：demo 先（資料量較大 / 訊號較快），live_demo 次之。
# 任一失敗即中止 tick，cron mailer 觸發 operator 告警。
#
# W-AUDIT-4b-M2 (2026-05-09): each pass now includes
# `--backfill-fill-entry-context-id` which runs the new trading.fills
# entry_context_id backfill BEFORE backfill_labels. Order matters:
# entry_context_id must be populated first so backfill_labels' EXISTS
# JOIN (trading.fills.entry_context_id = decision_features.context_id)
# can find the matched close fills.
#
# Acceptance per PA spec §2.5 B-M2: 24h fill writer entry_context_id
# 非 NULL ratio ≥ 95%（observability.fills_entry_context_id_health view 監控）。
#
# Window: fill entry_context_id backfill 用 30d window；backfill_labels
# 默認 abandon_after_days=30d 對齊。
#
# W-AUDIT-4b-M2（2026-05-09）：新增 --backfill-fill-entry-context-id flag，
# 先跑 fill writer 端 entry_context_id 回填，再跑 label backfill。順序關鍵：
# entry_context_id 必先補齊，否則 backfill_labels 的 EXISTS JOIN 找不到目標。
RC=0
for MODE in demo live_demo; do
    echo "[$(ts)] running --engine-mode $MODE --batch-limit $BATCH (M2 + label backfill)" >> "$LOG"
    if ! python3 -m program_code.ml_training.edge_label_backfill \
            --engine-mode "$MODE" \
            --batch-limit "$BATCH" \
            --backfill-fill-entry-context-id \
            --fill-entry-context-window-days 30 >> "$LOG" 2>&1; then
        echo "[$(ts)] ERROR: backfill --engine-mode $MODE failed (non-zero exit)" >> "$LOG"
        RC=1
        # fail-loud: stop the cron tick now so cron mail surfaces the issue
        # immediately instead of masking with a partial second pass.
        # fail-loud：立即終止 cron tick，避免後一 pass 掩蓋訊號。
        break
    fi
    echo "[$(ts)] --engine-mode $MODE OK" >> "$LOG"
done

if [[ $RC -eq 0 ]]; then
    echo "[$(ts)] === cron end OK ===" >> "$LOG"
else
    echo "[$(ts)] === cron end FAIL (rc=$RC) ===" >> "$LOG"
fi

exit $RC

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

# ─── Overlap lock (mirror cron_observer_cycle.sh SW-006 pattern) ────
# 防止 30min cron 與長跑 backfill 互疊（SQL 兩 pass × 5000 row 偶可 >30s）。
LOCK_ROOT="${DATA}/locks"
LOCK_DIR="${LOCK_ROOT}/edge_label_backfill_cron.lock.d"
mkdir -p "$LOCK_ROOT" "$LOG_DIR"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] SKIP: edge_label_backfill cron already running (lock held)" >> "$LOG"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

# ─── Sanity: BASE must contain the backfill module / BASE 須含 module ─
if [[ ! -f "${BASE}/program_code/ml_training/edge_label_backfill.py" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: edge_label_backfill.py not found under BASE=${BASE}" >> "$LOG"
    exit 1
fi

cd "$BASE"

ts() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(ts)] === edge_label_backfill cron start (BASE=$BASE BATCH=$BATCH) ===" >> "$LOG"

# ─── Two engine_mode passes / 兩 engine_mode 連跑 ───────────────────
# Order: demo first (more rows / faster signal), live_demo second.
# Failure in either aborts the tick — operator alarm via cron mail.
# 順序：demo 先（資料量較大 / 訊號較快），live_demo 次之。
# 任一失敗即中止 tick，cron mailer 觸發 operator 告警。
RC=0
for MODE in demo live_demo; do
    echo "[$(ts)] running --engine-mode $MODE --batch-limit $BATCH" >> "$LOG"
    if ! python3 -m program_code.ml_training.edge_label_backfill \
            --engine-mode "$MODE" \
            --batch-limit "$BATCH" >> "$LOG" 2>&1; then
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

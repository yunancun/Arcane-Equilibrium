#!/usr/bin/env bash
# =============================================================================
# health_f2_sanitize_monitor.sh
#
# 用途：Sprint 5+ Wave 1 §4.4.3 production hardening — F-2 NaN/inf sanitize
#      fire log monitoring（grep-based heartbeat）。
#
# DISABLED-BY-DEFAULT 直到 Sprint 5+ §4.2.2 wireup PaperState SSOT 後 enable。
# Sprint 4+ Wave B placeholder no-op 階段 F-2 fire 必 0；過早 enable 等同
# 永遠 PASS 沒實質監測價值。
#
# 為什麼 grep-based 而非 PG-based（per PA report §4.3.1）:
#   - F-2 sanitize 在 in-process tracing::warn 觸發，不寫 V106 row；
#     engine.log 是唯一 source of truth。
#   - V106 row 是 fail-soft（state=HEALTH_OK 維持）；如 cache push 全 skip
#     表示 PaperState 餵 NaN 但 health row 不會反映；operator 看 health
#     WARN dashboard 不會看到 F-2 issue → 需獨立 grep cron。
#
# Source fire 點（per risk_envelope_probe_impl.rs:194-241 + PA report §4.1）:
#   - "PortfolioStateCache: skip NaN/inf realized_pnl fill (F-2 sanitize)"
#   - "PortfolioStateCache: skip NaN/inf equity sample (F-2 sanitize)"
#   - "PortfolioStateCache: filter NaN/inf notional exposure (F-2 sanitize)"
#   - target = m3.health.risk_envelope + m3.health.strategy_quality
#
# Usage:
#   bash helper_scripts/db/health_f2_sanitize_monitor.sh           # full output
#   bash helper_scripts/db/health_f2_sanitize_monitor.sh --quiet   # only ALERT
#
# Exit codes:
#   0 = OK — fire count ≤ threshold
#   1 = ALERT — fire count > threshold (operator alert)
#   2 = engine.log unreadable
#
# Environment overrides:
#   OPENCLAW_ENGINE_LOG       engine log path (default: /tmp/openclaw/engine.log)
#   OPENCLAW_F2_THRESHOLD     fire count > N → alert (default: 0)
#   OPENCLAW_F2_WINDOW_HOURS  scan window in hours (default: 1)
# =============================================================================

set -u

LOG_FILE="${OPENCLAW_ENGINE_LOG:-/tmp/openclaw/engine.log}"
THRESHOLD="${OPENCLAW_F2_THRESHOLD:-0}"
WINDOW_HOURS="${OPENCLAW_F2_WINDOW_HOURS:-1}"

QUIET=0
for arg in "$@"; do
  if [[ "$arg" == "--quiet" ]]; then
    QUIET=1
  fi
done

# ─── 1. Sanity check engine log ────────────────────────────────────────────
if [[ ! -r "$LOG_FILE" ]]; then
  echo "[FATAL] engine.log not readable: $LOG_FILE" >&2
  exit 2
fi

# ─── 2. Compute cutoff timestamp（cross-platform: prefer GNU date）─────────
# 為什麼 cross-platform：trade-core (Linux) 用 GNU date `-d` flag；
# Mac BSD date 用 `-v -1H` flag。本 script 必須兩端跑（per profile §硬約束
# 跨平台兼容性）。
if date -u -d "${WINDOW_HOURS} hour ago" +%Y-%m-%dT%H:%M:%S >/dev/null 2>&1; then
  # GNU date (Linux)
  CUTOFF=$(date -u -d "${WINDOW_HOURS} hour ago" +%Y-%m-%dT%H:%M:%S)
elif date -u -v "-${WINDOW_HOURS}H" +%Y-%m-%dT%H:%M:%S >/dev/null 2>&1; then
  # BSD date (Mac)
  CUTOFF=$(date -u -v "-${WINDOW_HOURS}H" +%Y-%m-%dT%H:%M:%S)
else
  echo "[FATAL] cannot compute cutoff: neither GNU date -d nor BSD date -v available" >&2
  exit 2
fi

# ─── 3. Grep F-2 fire log ─────────────────────────────────────────────────
# 為什麼 awk + $1 >= cutoff：tracing log 格式
# `2026-05-23T10:30:25.381002Z INFO m3.health.risk_envelope: ...`；$1 是
# ISO8601 timestamp，字串比較與時間序列 monotonic 對齊（per awk-default
# lexicographic string compare）。
FIRE_LINES=$(awk -v cutoff="$CUTOFF" '$0 ~ /F-2 sanitize/ && $1 >= cutoff' "$LOG_FILE")
FIRE_COUNT=$(echo -n "$FIRE_LINES" | grep -c . || true)

# ─── 4. Verdict + sample fire log ──────────────────────────────────────────
if (( FIRE_COUNT > THRESHOLD )); then
  echo "[ALERT] F-2 sanitize fire count $FIRE_COUNT in last ${WINDOW_HOURS}h > threshold $THRESHOLD"
  echo "$FIRE_LINES" | tail -5
  exit 1
fi

(( QUIET == 0 )) && echo "[OK] F-2 sanitize fire count $FIRE_COUNT in last ${WINDOW_HOURS}h ≤ threshold $THRESHOLD"
exit 0

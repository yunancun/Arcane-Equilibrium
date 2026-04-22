#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# OpenClaw TRACK-P-V2-SWAP-1 24h Post-Deploy Observation / 24h 部署後觀察
#
# Purpose / 用途：
#   2026-04-22 20:55 CEST `restart_all.sh --rebuild` 部署 TRACK-P-V2-SWAP-1
#   （commit `306993e`）後，每小時採集 1 次 v2 non-linear giveback 的 runtime
#   觀察指標，持續 24 小時，寫入 `/tmp/openclaw/v2_swap_24h_observation.log`
#   供 operator / 下次 session 回顧。
#
#   After 2026-04-22 20:55 CEST `--rebuild` deployment of TRACK-P-V2-SWAP-1
#   (commit `306993e`), collect v2 non-linear giveback runtime observation
#   metrics hourly for 24 hours, appending to
#   `/tmp/openclaw/v2_swap_24h_observation.log` for operator/future-session review.
#
# 採集指標 / Metrics:
#   1. engine_watchdog 狀態（engine_alive + snapshot_age_seconds）
#   2. engine.log 內 `phys_lock` 累計出現次數（gate4_giveback / gate4_stale 分別計）
#   3. engine PID 是否仍為啟動時快照（穩定性檢查）
#   4. edge_estimates populate 狀態（是否已過冷啟動期）
#
#   SQL fills 分布（`risk_close:phys_lock_%` GROUP BY）刻意不在本腳本自動跑，
#   因 DB 需 credentials；operator 可 ad-hoc 執行：
#     psql -d trading_ai -c "SELECT exit_reason, COUNT(*) FROM trading.fills
#       WHERE ts_ms >= <deploy_ms> AND exit_reason LIKE 'risk_close:phys_lock_%'
#       GROUP BY 1;"
#
# 使用 / Usage:
#   nohup bash ~/BybitOpenClaw/srv/helper_scripts/v2_swap_24h_observation.sh \
#     > /tmp/openclaw/v2_swap_24h_observation.log 2>&1 &
#   disown
#
# 停止 / Stop:
#   pkill -f v2_swap_24h_observation.sh
#
# ═══════════════════════════════════════════════════════════════════════

set -u

# ─── Configuration / 配置 ──────────────────────────────────────────────

# Start-of-window timestamp (ms). Use script invocation time as lower bound
# for SQL fills filter. 啟動時刻 ms 作為 SQL fills 下界。
DEPLOY_MS="$(date +%s000)"
START_ISO="$(date -Iseconds)"

# Observation loop config / 觀察循環配置
HOURS="${HOURS:-24}"                           # total iterations / 總循環數
INTERVAL_SECS="${INTERVAL_SECS:-3600}"         # 1 hour between ticks / 每 tick 間隔

# Paths / 路徑（Linux trade-core hard-coded，cross-plat 由 operator 按需調整）
BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
ENGINE_LOG="${DATA_DIR}/engine.log"
WATCHDOG_PY="${BASE_DIR}/helper_scripts/canary/engine_watchdog.py"

# Capture baseline engine PID at script start / 啟動時固定引擎 PID 作為穩定性錨
BASELINE_PID="$(pgrep -f 'openclaw-engine' | head -1)"

# ─── Functions / 函數 ──────────────────────────────────────────────────

print_header() {
    echo "═══════════════════════════════════════════════════════════════════════"
    echo "TRACK-P-V2-SWAP-1 24h observation · start=${START_ISO} · deploy_ms=${DEPLOY_MS}"
    echo "baseline engine PID=${BASELINE_PID} · interval=${INTERVAL_SECS}s · hours=${HOURS}"
    echo "═══════════════════════════════════════════════════════════════════════"
}

run_tick() {
    local tick="$1"
    local now_iso
    now_iso="$(date -Iseconds)"
    echo ""
    echo "─── tick ${tick}/${HOURS} · ${now_iso} ─────────────────────────────────"

    # 1. engine_watchdog
    echo "[watchdog]"
    if [[ -x "$(command -v python3)" ]] && [[ -f "${WATCHDOG_PY}" ]]; then
        python3 "${WATCHDOG_PY}" --data-dir "${DATA_DIR}" \
            --stale-threshold 45 --grace-period 120 --status 2>&1 \
            | grep -E 'engine_alive|snapshot_age_seconds|alive|age_seconds' \
            | head -12
    else
        echo "  watchdog unavailable"
    fi

    # 2. engine PID drift check
    local current_pid
    current_pid="$(pgrep -f 'openclaw-engine' | head -1)"
    if [[ "${current_pid}" == "${BASELINE_PID}" ]]; then
        echo "[pid] stable · ${current_pid}"
    else
        echo "[pid] ⚠️ DRIFT · baseline=${BASELINE_PID} current=${current_pid}"
    fi

    # 3. phys_lock occurrences in engine.log
    # grep -c 無匹配時 exit=1（count=0），需 `|| true` 吸住失敗且抓乾淨數字。
    # grep -c exits 1 on zero matches; suppress with `|| true` and take a clean integer.
    if [[ -f "${ENGINE_LOG}" ]]; then
        local phys_total phys_gate4_giveback phys_gate4_stale
        phys_total="$({ grep -c 'phys_lock' "${ENGINE_LOG}" 2>/dev/null || true; } | head -1)"
        phys_gate4_giveback="$({ grep -c 'phys_lock_gate4_giveback' "${ENGINE_LOG}" 2>/dev/null || true; } | head -1)"
        phys_gate4_stale="$({ grep -c 'phys_lock_gate4_stale_roc_neg' "${ENGINE_LOG}" 2>/dev/null || true; } | head -1)"
        echo "[phys_lock] total=${phys_total:-0} gate4_giveback=${phys_gate4_giveback:-0} gate4_stale_roc_neg=${phys_gate4_stale:-0}"
    else
        echo "[phys_lock] engine.log missing"
    fi

    # 4. edge_estimates populate status (via settings/edge_estimates.json mtime)
    local edge_json="${BASE_DIR}/settings/edge_estimates.json"
    if [[ -f "${edge_json}" ]]; then
        local edge_mtime cell_count
        edge_mtime="$(stat -c '%y' "${edge_json}" 2>/dev/null | cut -d. -f1 || echo unknown)"
        cell_count="$(python3 -c "import json; d=json.load(open('${edge_json}')); print(len(d.get('cells',[])))" 2>/dev/null || echo ?)"
        echo "[edge_estimates] mtime=${edge_mtime} cells=${cell_count}"
    else
        echo "[edge_estimates] file missing"
    fi

    # 5. SQL fills 分布刻意不在本腳本跑（DB 需 credentials，不在自動化範圍）。
    # SQL fills distribution intentionally not automated here (needs DB credentials);
    # operator runs ad-hoc. See header comment for template.
    echo "[fills SQL] skip — operator ad-hoc (ts_ms >= ${DEPLOY_MS})"
}

# ─── Main / 主循環 ──────────────────────────────────────────────────────

print_header

for i in $(seq 1 "${HOURS}"); do
    run_tick "${i}"
    if [[ "${i}" -lt "${HOURS}" ]]; then
        sleep "${INTERVAL_SECS}"
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════════════════"
echo "24h observation complete · end=$(date -Iseconds)"
echo "═══════════════════════════════════════════════════════════════════════"

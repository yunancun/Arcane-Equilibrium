#!/usr/bin/env bash
# MODULE_NOTE (English):
#   Rollback Drill Script (R07-5) — rehearses a full rollback from Rust+Python
#   dual-process mode to Python-only mode. Target SLA: < 10 minutes.
#   Records timing for each step.
#
# MODULE_NOTE (中文):
#   回滾演練腳本（R07-5）— 演練從 Rust+Python 雙進程模式到純 Python 模式的完全回滾。
#   目標 SLA：< 10 分鐘。記錄每步計時。
#
# Usage:
#   bash rollback_drill.sh [--dry-run]

set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# Configuration / 配置
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
LOG_FILE="${PROJECT_ROOT}/trading_services/rollback_drill_$(date +%Y%m%d_%H%M%S).log"
DRY_RUN=false
SLA_SECONDS=600  # 10 minutes

# Platform guard: this drill uses systemctl (Linux-only). On macOS, the
# service-management steps are logged as skipped because launchd plists are
# not wired up yet (deferred to M5 Ultra prod migration). The rest of the
# drill (git checks, snapshot staleness, API health) still runs so operators
# can rehearse the non-service parts on Mac dev.
# 平台守衛：本演練使用 systemctl（Linux 專屬）。macOS 上服務管理步驟記為 skip，
# 因為 launchd plist 尚未建立（延後到 M5 Ultra prod 遷移處理）。其他步驟
# （git 檢查 / snapshot 過期 / API 健康）在 Mac 上照樣跑，供 operator
# 在 dev 機上演練非服務部分。
IS_MAC=0
if [[ "$(uname -s)" == "Darwin" ]]; then
    IS_MAC=1
fi

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "=== DRY RUN MODE — no actual service changes ==="
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers / 輔助函數
# ═══════════════════════════════════════════════════════════════════════════════

START_TIME=$(date +%s)

log() {
    local elapsed=$(( $(date +%s) - START_TIME ))
    local msg="[+${elapsed}s] $1"
    echo "$msg" | tee -a "$LOG_FILE"
}

step() {
    log "──── STEP: $1 ────"
}

check_sla() {
    local elapsed=$(( $(date +%s) - START_TIME ))
    if [[ $elapsed -gt $SLA_SECONDS ]]; then
        log "⚠ WARNING: SLA exceeded! ${elapsed}s > ${SLA_SECONDS}s"
    else
        log "✓ Within SLA: ${elapsed}s / ${SLA_SECONDS}s"
    fi
}

# ═══════════════════════════════════════════════════════════════════════════════
# Pre-flight Checks / 飛行前檢查
# ═══════════════════════════════════════════════════════════════════════════════

mkdir -p "$(dirname "$LOG_FILE")"
log "Rollback drill started at $(date -Iseconds)"
log "Project root: $PROJECT_ROOT"
log "Log file: $LOG_FILE"

step "1. Pre-flight checks / 飛行前檢查"

# Check git status / 檢查 git 狀態
cd "$PROJECT_ROOT"
if ! git diff --quiet HEAD; then
    log "⚠ WARNING: Uncommitted changes detected. Stash or commit before real rollback."
fi

# Check for pre-rust-cleanup tag / 檢查回滾標籤
if git tag -l | grep -q "pre-rust-cleanup"; then
    log "✓ Tag 'pre-rust-cleanup' exists"
else
    log "⚠ Tag 'pre-rust-cleanup' not found — will be created during R07-7"
    log "  (For drill purposes, we'll simulate with current HEAD)"
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 2: Stop Rust Engine / 停止 Rust 引擎
# ═══════════════════════════════════════════════════════════════════════════════

step "2. Stop Rust engine / 停止 Rust 引擎"

if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY RUN] Would stop openclaw-engine service"
elif [[ "$IS_MAC" == "1" ]]; then
    log "ℹ macOS: skipping systemctl stop (launchd plist not wired — deferred to M5 Ultra prod migration)"
else
    if systemctl is-active --quiet openclaw-engine.service 2>/dev/null; then
        sudo systemctl stop openclaw-engine.service
        log "✓ openclaw-engine.service stopped"
    else
        log "ℹ openclaw-engine.service not running (OK for drill)"
    fi
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 3: Stop Shadow Process / 停止影子進程
# ═══════════════════════════════════════════════════════════════════════════════

step "3. Stop shadow process (if running) / 停止影子進程"

if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY RUN] Would stop openclaw-shadow service"
elif [[ "$IS_MAC" == "1" ]]; then
    log "ℹ macOS: skipping systemctl stop (launchd plist not wired — deferred to M5 Ultra prod migration)"
else
    if systemctl is-active --quiet openclaw-shadow.service 2>/dev/null; then
        sudo systemctl stop openclaw-shadow.service
        log "✓ openclaw-shadow.service stopped"
    else
        log "ℹ openclaw-shadow.service not running (OK)"
    fi
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 4: Verify IPC Fallback Active / 驗證 IPC 降級啟動
# ═══════════════════════════════════════════════════════════════════════════════

step "4. Verify IPC fallback active / 驗證 IPC 降級啟動"

SNAPSHOT_PATH="${OPENCLAW_DATA_DIR:-/tmp/openclaw}/pipeline_snapshot.json"
if [[ -f "$SNAPSHOT_PATH" ]]; then
    AGE=$(( $(date +%s) - $(stat -c %Y "$SNAPSHOT_PATH" 2>/dev/null || stat -f %m "$SNAPSHOT_PATH" 2>/dev/null) ))
    log "Snapshot age: ${AGE}s"
    if [[ $AGE -gt 60 ]]; then
        log "✓ Snapshot stale (${AGE}s > 60s) — IPC reader will fallback to Python"
    else
        log "⚠ Snapshot still fresh — may need to wait or delete"
        if [[ "$DRY_RUN" == "false" ]]; then
            rm -f "$SNAPSHOT_PATH"
            log "  Deleted snapshot to force fallback"
        fi
    fi
else
    log "✓ No snapshot file — IPC reader already in fallback mode"
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 5: Verify Python API Healthy / 驗證 Python API 正常
# ═══════════════════════════════════════════════════════════════════════════════

step "5. Verify Python API healthy / 驗證 Python API 正常"

API_URL="${OPENCLAW_API_URL:-http://localhost:8000}"
if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY RUN] Would check ${API_URL}/api/v1/status"
else
    if curl -sf "${API_URL}/api/v1/status" > /dev/null 2>&1; then
        log "✓ Python API responding at ${API_URL}"
    else
        log "⚠ Python API not responding — may need restart"
    fi
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 6: Git Checkout (simulated in drill) / Git 切換
# ═══════════════════════════════════════════════════════════════════════════════

step "6. Git checkout pre-rust-cleanup (simulated) / Git 切換到回滾點"

if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY RUN] Would run: git checkout pre-rust-cleanup"
    log "[DRY RUN] Would run: pip install -r requirements.txt"
else
    log "ℹ Drill mode: skipping actual git checkout (would run: git checkout pre-rust-cleanup)"
    log "  In real rollback, this would restore Python-only codebase"
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 7: Restart Python Services / 重啟 Python 服務
# ═══════════════════════════════════════════════════════════════════════════════

step "7. Restart Python services / 重啟 Python 服務"

if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY RUN] Would restart openclaw-api service"
elif [[ "$IS_MAC" == "1" ]]; then
    log "ℹ macOS: skipping systemctl restart (launchd plist not wired — deferred to M5 Ultra prod migration)"
else
    if systemctl is-active --quiet openclaw-api.service 2>/dev/null; then
        sudo systemctl restart openclaw-api.service
        log "✓ openclaw-api.service restarted"
    else
        log "ℹ openclaw-api.service not managed by systemd (OK for dev)"
    fi
fi

check_sla

# ═══════════════════════════════════════════════════════════════════════════════
# Step 8: Final Health Check / 最終健康檢查
# ═══════════════════════════════════════════════════════════════════════════════

step "8. Final health check / 最終健康檢查"

if [[ "$DRY_RUN" == "true" ]]; then
    log "[DRY RUN] Would verify all endpoints responding"
else
    # Check key endpoints / 檢查關鍵端點
    ENDPOINTS=(
        "/api/v1/status"
        "/api/v1/paper/session/status"
    )
    for ep in "${ENDPOINTS[@]}"; do
        if curl -sf "${API_URL}${ep}" -H "Authorization: Bearer ${OPENCLAW_API_TOKEN:-test}" > /dev/null 2>&1; then
            log "✓ ${ep} — OK"
        else
            log "⚠ ${ep} — FAILED (may need token or service not running)"
        fi
    done
fi

# ═══════════════════════════════════════════════════════════════════════════════
# Summary / 摘要
# ═══════════════════════════════════════════════════════════════════════════════

TOTAL_TIME=$(( $(date +%s) - START_TIME ))
log ""
log "════════════════════════════════════════════"
log "ROLLBACK DRILL COMPLETE"
log "Total time: ${TOTAL_TIME}s"
if [[ $TOTAL_TIME -lt $SLA_SECONDS ]]; then
    log "SLA: ✓ PASS (${TOTAL_TIME}s < ${SLA_SECONDS}s)"
else
    log "SLA: ✗ FAIL (${TOTAL_TIME}s >= ${SLA_SECONDS}s)"
fi
log "Log: $LOG_FILE"
log "════════════════════════════════════════════"

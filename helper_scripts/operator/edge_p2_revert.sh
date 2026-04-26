#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# EDGE-P2-revert Operator SOP — emergency rollback shadow_enabled true → false
# EDGE-P2-revert Operator SOP — 緊急回滾 shadow_enabled true → false
#
# MODULE_NOTE (English):
#   90-second emergency rollback wrapper per PA RFC §4.2. Unlike edge_p2_flip.sh
#   this script has NO confirmation prompt — when the operator decides to revert
#   they need it to happen NOW (e.g. healthcheck [15] FAIL pattern, writer
#   silent-dead, or operator judgment).
#
#   Three steps:
#     1. send IPC patch_risk_config { exit: { shadow_enabled: false } }
#     2. wait 5s, verify get_risk_config().exit.shadow_enabled == false
#     3. log RCA pointer for follow-up post-mortem
#
#   Per memory `feedback_shell_paste_safety` — paste-safe one-liners only.
#   依 memory `feedback_shell_paste_safety` —— paste-safe one-liner。
#
# MODULE_NOTE (中文):
#   90 秒緊急回滾 wrapper（per PA RFC §4.2）。與 edge_p2_flip.sh 不同，本 script
#   **無**確認提示 —— operator 決定回滾時必須立即發生（例如 healthcheck [15]
#   FAIL 圖樣、writer silent-dead、或 operator 判斷）。
#
#   3 步驟：
#     1. 送 IPC patch_risk_config { exit: { shadow_enabled: false } }
#     2. 等 5s，驗證 get_risk_config().exit.shadow_enabled == false
#     3. log RCA 指標供後續事後 post-mortem
#
# Reference / 參考:
#   - PA RFC: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md §4.2
#   - Re-flip after fix: bash helper_scripts/operator/edge_p2_flip.sh
#
# Usage / 用法:
#   bash helper_scripts/operator/edge_p2_revert.sh [--engine-mode <demo|live_demo>]
#
# Exit codes / 退出碼:
#   0 — revert succeeded; shadow_enabled now false
#   1 — IPC patch failed (engine state unknown — run again or escalate)
#   2 — post-revert verification failed (state mismatch — manual TOML edit needed)
#   3 — env precondition missing (no python3 / no engine.sock / etc)
# ═══════════════════════════════════════════════════════════════════════════════

set -u

# ─── Defaults / 預設 ─────────────────────────────────────────────────────────

ENGINE_MODE="demo"

# ─── Args parsing / 解析參數 ─────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine-mode) ENGINE_MODE="$2"; shift 2 ;;
        -h|--help)
            echo "Usage: $0 [--engine-mode <demo|live_demo>]"
            echo "  Emergency rollback — flips shadow_enabled true → false."
            echo "  No confirmation prompt; runs IMMEDIATELY."
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 3
            ;;
    esac
done

case "$ENGINE_MODE" in
    paper|demo|live|live_demo) : ;;
    *) echo "Invalid --engine-mode: $ENGINE_MODE" >&2; exit 3 ;;
esac

# ─── Path setup / 路徑設置 ────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOG_FILE="$DATA_DIR/edge_p2_revert.log"

mkdir -p "$DATA_DIR"

# ─── Source env files if available / 自動 source env file（IPC auth）──────────
# Same pattern as edge_p2_flip.sh — OPENCLAW_IPC_SECRET (from ipc_secret.txt)
# must be in env. Idempotent if already set (systemd / pre-sourced shell).
# Mirrors restart_all.sh:191-196 / 230 secret load pattern.
# 與 flip.sh 同範式（與 restart_all.sh:191-196 / 230 對齊）。
# SECRETS_ROOT defaults match restart_all.sh:31. Mac dev override via
# OPENCLAW_SECRETS_ROOT env var.
# SECRETS_ROOT 預設與 restart_all.sh 對齊；Mac dev 由 operator export 覆寫。
SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
ENV_BASE="$SECRETS_ROOT/environment_files/basic_system_services.env"
ENV_TRADING="$SECRETS_ROOT/environment_files/trading_services.env"
ENV_IPC_SECRET="$SECRETS_ROOT/environment_files/ipc_secret.txt"
if [[ -f "$ENV_BASE" ]]; then set -a; . "$ENV_BASE" 2>/dev/null || true; set +a; fi
if [[ -f "$ENV_TRADING" ]]; then set -a; . "$ENV_TRADING" 2>/dev/null || true; set +a; fi
if [[ -z "${OPENCLAW_IPC_SECRET:-}" ]] && [[ -r "$ENV_IPC_SECRET" ]]; then
    OPENCLAW_IPC_SECRET="$(cat "$ENV_IPC_SECRET" 2>/dev/null || true)"
    export OPENCLAW_IPC_SECRET
fi

# Paste-safe single-line logger.
# Paste-safe 單行 logger。
log() { local ts; ts="$(date -Iseconds)"; printf "%s [edge_p2_revert] %s\n" "$ts" "$*" | tee -a "$LOG_FILE" >&2; }

log "═══════════════════════════════════════════════════════════════════"
log "EDGE-P2-revert START · engine_mode=$ENGINE_MODE · EMERGENCY ROLLBACK"

# ─── Env preconditions / 環境前置條件 ────────────────────────────────────────

if ! command -v python3 >/dev/null 2>&1; then
    log "FATAL: python3 not found in PATH"
    exit 3
fi

SOCKET_PATH="${OPENCLAW_IPC_SOCKET:-$DATA_DIR/engine.sock}"
if [[ ! -S "$SOCKET_PATH" ]]; then
    log "FATAL: engine socket missing at $SOCKET_PATH"
    log "  manual fallback: edit settings/risk_control_rules/risk_config_${ENGINE_MODE}.toml,"
    log "  set [exit].shadow_enabled = false, then restart engine"
    exit 3
fi

# Dry-run helper provides the _sync_ipc_call function. Required.
# Dry-run helper 提供 _sync_ipc_call 函數，必需。
DRY_RUN_PY="$SRV_ROOT/helper_scripts/canary/edge_p2_flip_dry_run.py"
if [[ ! -f "$DRY_RUN_PY" ]]; then
    log "FATAL: dry-run helper missing at $DRY_RUN_PY (provides _sync_ipc_call)"
    exit 3
fi

# ─── Step 1: Send revert patch / 送回滾 patch ───────────────────────────────

log "STEP 1: sending IPC patch_risk_config (exit.shadow_enabled=false)"
PATCH_OUTPUT="$(
    OPENCLAW_BASE_DIR="$SRV_ROOT" \
    OPENCLAW_IPC_SOCKET="$SOCKET_PATH" \
    PYTHONPATH="$SRV_ROOT" \
    python3 -c "
import json,sys
sys.path.insert(0, '$SRV_ROOT/helper_scripts/canary')
from edge_p2_flip_dry_run import _sync_ipc_call
try:
    r = _sync_ipc_call('patch_risk_config', params={'engine': '$ENGINE_MODE', 'source': 'operator', 'patch': {'exit': {'shadow_enabled': False}}})
    if isinstance(r, dict) and r.get('ok') is True:
        print('PASS version=%s source=%s' % (r.get('version', '?'), r.get('source', '?')))
        sys.exit(0)
    print('FAIL response=%s' % json.dumps(r))
    sys.exit(1)
except Exception as e:
    print('FAIL exception=%s' % e)
    sys.exit(1)
" 2>&1
)"
PATCH_RC=$?
log "STEP 1: patch result: $PATCH_OUTPUT (rc=$PATCH_RC)"
if [[ "$PATCH_RC" != "0" ]]; then
    log "STEP 1: IPC patch FAILED — try again immediately or fall back to TOML edit"
    log "  manual fallback: edit settings/risk_control_rules/risk_config_${ENGINE_MODE}.toml"
    log "  set [exit].shadow_enabled = false (engine reads on next config reload)"
    exit 1
fi

# ─── Step 2: Verify revert / 驗證回滾 ────────────────────────────────────────

log "STEP 2: waiting 5s for hot-reload propagation..."
sleep 5
log "STEP 2: verifying get_risk_config().exit.shadow_enabled == false"
VERIFY_OUTPUT="$(
    OPENCLAW_BASE_DIR="$SRV_ROOT" \
    OPENCLAW_IPC_SOCKET="$SOCKET_PATH" \
    PYTHONPATH="$SRV_ROOT" \
    python3 -c "
import sys
sys.path.insert(0, '$SRV_ROOT/helper_scripts/canary')
from edge_p2_flip_dry_run import _sync_ipc_call
try:
    r = _sync_ipc_call('get_risk_config', params={'engine': '$ENGINE_MODE'})
    val = r.get('config', {}).get('exit', {}).get('shadow_enabled')
    if val is False:
        print('PASS shadow_enabled=False version=%s' % r.get('version', '?'))
        sys.exit(0)
    print('FAIL shadow_enabled=%s (expected False)' % val)
    sys.exit(2)
except Exception as e:
    print('FAIL exception=%s' % e)
    sys.exit(2)
" 2>&1
)"
VERIFY_RC=$?
log "STEP 2: verify result: $VERIFY_OUTPUT (rc=$VERIFY_RC)"
if [[ "$VERIFY_RC" != "0" ]]; then
    log "STEP 2: post-revert verification FAILED — manual TOML edit required"
    log "  edit settings/risk_control_rules/risk_config_${ENGINE_MODE}.toml"
    log "  set [exit].shadow_enabled = false, then trigger config reload"
    exit 2
fi

# ─── Step 3: RCA pointer / RCA 指標 ────────────────────────────────────────

log "STEP 3: revert COMPLETE — shadow_enabled now false; data plane dormant"
log "STEP 3: RCA SOP — operator next steps:"
log "  1. capture disagreement_reason distribution from learning.decision_shadow_exits"
log "     (rows from the flipped window remain for offline analysis)"
log "  2. file lessons.md entry: docs/lessons.md (RFC §4.2 mentions log path)"
log "  3. reproduce in dry-run if possible (helper_scripts/canary/edge_p2_flip_dry_run.py)"
log "  4. only re-flip after RCA root cause identified + dry-run PASS"
log "═══════════════════════════════════════════════════════════════════"
exit 0

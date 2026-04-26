#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# EDGE-P2-flip Operator SOP — flip Combine Layer shadow_enabled false → true
# EDGE-P2-flip Operator SOP — 翻轉 Combine Layer shadow_enabled false → true
#
# MODULE_NOTE (English):
#   Operator-runnable SOP wrapper to safely execute the EDGE-P2-flip:
#     1. run dry-run smoke test (helper_scripts/canary/edge_p2_flip_dry_run.py)
#     2. require operator to type "yes" to confirm
#     3. send IPC patch_risk_config { exit: { shadow_enabled: true } }
#     4. wait 5s, verify get_risk_config().exit.shadow_enabled == true
#     5. wait 60s, run healthcheck [15] for early signal
#     6. log all steps to $OPENCLAW_DATA_DIR/edge_p2_flip.log
#
#   Per memory `feedback_shell_paste_safety` — paste-safe one-liners only;
#   complex logic delegated to Python helper, no heredoc, no multi-line for.
#   依 memory `feedback_shell_paste_safety` —— paste-safe one-liner；複雜邏輯
#   委派給 Python helper，無 heredoc，無多行 for。
#
# MODULE_NOTE (中文):
#   Operator 可執行 SOP wrapper，安全執行 EDGE-P2-flip：
#     1. 跑 dry-run smoke test（helper_scripts/canary/edge_p2_flip_dry_run.py）
#     2. 要求 operator 輸入 "yes" 確認
#     3. 送 IPC patch_risk_config { exit: { shadow_enabled: true } }
#     4. 等 5s，驗證 get_risk_config().exit.shadow_enabled == true
#     5. 等 60s，跑 healthcheck [15] 取早期訊號
#     6. 全步驟記錄至 $OPENCLAW_DATA_DIR/edge_p2_flip.log
#
# Reference / 參考:
#   - PA RFC: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--edge_p2_flip_sop_rfc.md
#   - Dry-run: srv/helper_scripts/canary/edge_p2_flip_dry_run.py
#   - Revert:  srv/helper_scripts/operator/edge_p2_revert.sh (90s emergency rollback)
#
# Usage / 用法:
#   bash helper_scripts/operator/edge_p2_flip.sh [--engine-mode <demo|live_demo>]
#                                                 [--skip-dry-run]
#                                                 [--skip-confirm]
#
#   --engine-mode  default demo
#   --skip-dry-run skip step 1 (NOT recommended; only for re-flip after revert)
#   --skip-confirm skip step 2 confirm (DANGEROUS; reserved for cron/auto)
#
# Exit codes / 退出碼:
#   0 — flip succeeded; shadow_enabled now true
#   1 — dry-run FAIL or operator did not confirm
#   2 — IPC patch failed or post-flip verification failed (engine state unknown,
#       run revert.sh immediately to be safe)
#   3 — env precondition missing (no python3 / no engine.sock / etc)
# ═══════════════════════════════════════════════════════════════════════════════

set -u

# ─── Defaults / 預設 ─────────────────────────────────────────────────────────

ENGINE_MODE="demo"
SKIP_DRY_RUN=0
SKIP_CONFIRM=0

# ─── Args parsing (paste-safe single-line / 單行解析) ────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine-mode) ENGINE_MODE="$2"; shift 2 ;;
        --skip-dry-run) SKIP_DRY_RUN=1; shift ;;
        --skip-confirm) SKIP_CONFIRM=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--engine-mode <demo|live_demo>] [--skip-dry-run] [--skip-confirm]"
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 3
            ;;
    esac
done

# Validate engine mode (defensive — reject typos before sending IPC).
# 驗證 engine mode（防禦性 —— 送 IPC 前擋打字錯誤）。
case "$ENGINE_MODE" in
    paper|demo|live|live_demo) : ;;
    *) echo "Invalid --engine-mode: $ENGINE_MODE (must be paper|demo|live|live_demo)" >&2; exit 3 ;;
esac

# ─── Path setup / 路徑設置 ────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
DRY_RUN_PY="$SRV_ROOT/helper_scripts/canary/edge_p2_flip_dry_run.py"
HEALTHCHECK_PY="$SRV_ROOT/helper_scripts/db/passive_wait_healthcheck.py"
LOG_FILE="$DATA_DIR/edge_p2_flip.log"

mkdir -p "$DATA_DIR"

# ─── Source env files if available / 自動 source env file（避免 IPC auth 缺失）──
# OPENCLAW_IPC_SECRET (from ipc_secret.txt) / POSTGRES_* (from
# basic_system_services.env) must be in env for IPC + DB checks. When running
# outside systemd context, we source preemptively (idempotent if already set).
# Mirrors restart_all.sh:191-196 / 230 secret load pattern.
# OPENCLAW_IPC_SECRET (從 ipc_secret.txt) / POSTGRES_* (從 basic_system_services.env)
# 必須在 env；不在 systemd context 時自動 source（已 set 時 idempotent）。
# 與 restart_all.sh:191-196 / 230 對齊。
# SECRETS_ROOT defaults match restart_all.sh:31 ($HOME/BybitOpenClaw/secrets).
# Operator may override via OPENCLAW_SECRETS_ROOT env var (Mac dev typically
# uses $HOME/.openclaw_secrets per CLAUDE.md §六 cross-platform table).
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

# Single-line logger that tees to log file and stderr (paste-safe).
# 單行 logger（同時寫 log file + stderr，paste-safe）。
log() { local ts; ts="$(date -Iseconds)"; printf "%s [edge_p2_flip] %s\n" "$ts" "$*" | tee -a "$LOG_FILE" >&2; }

# Write a separator banner.
# 寫入分隔 banner。
log "═══════════════════════════════════════════════════════════════════"
log "EDGE-P2-flip START · engine_mode=$ENGINE_MODE · skip_dry_run=$SKIP_DRY_RUN · skip_confirm=$SKIP_CONFIRM"

# ─── Env preconditions / 環境前置條件 ────────────────────────────────────────

# python3 must be available (system, no venv per PA spec).
# python3 必須可用（system，per PA spec 不依 venv）。
if ! command -v python3 >/dev/null 2>&1; then
    log "FATAL: python3 not found in PATH"
    exit 3
fi

# Engine socket must exist (else the flip cannot reach the engine).
# Engine socket 必須存在（否則 flip 到不了 engine）。
SOCKET_PATH="${OPENCLAW_IPC_SOCKET:-$DATA_DIR/engine.sock}"
if [[ ! -S "$SOCKET_PATH" ]]; then
    log "FATAL: engine socket missing at $SOCKET_PATH (engine down?)"
    exit 3
fi

# Dry-run helper must exist.
# Dry-run helper 必須存在。
if [[ ! -f "$DRY_RUN_PY" ]]; then
    log "FATAL: dry-run script missing at $DRY_RUN_PY"
    exit 3
fi

# ─── Step 1: Dry-run smoke test / Dry-run 煙霧測試 ──────────────────────────

if [[ "$SKIP_DRY_RUN" == "1" ]]; then
    log "STEP 1: dry-run SKIPPED (--skip-dry-run set; not recommended)"
else
    log "STEP 1: running dry-run smoke test (engine=$ENGINE_MODE)"
    # Run dry-run, capture exit code separately to avoid set -e early exit.
    # 跑 dry-run，獨立捕獲 exit code 避免 set -e 提前 exit。
    if python3 "$DRY_RUN_PY" --engine-mode "$ENGINE_MODE" --mock-events 100 >> "$LOG_FILE" 2>&1; then
        log "STEP 1: dry-run PASS (all 5 pre-flight checks green)"
    else
        DRY_RUN_RC=$?
        log "STEP 1: dry-run FAIL (exit=$DRY_RUN_RC) — see $LOG_FILE for details"
        log "STEP 1: ABORT — flip NOT executed"
        exit 1
    fi
fi

# ─── Step 2: Operator confirmation / Operator 確認 ──────────────────────────

if [[ "$SKIP_CONFIRM" == "1" ]]; then
    log "STEP 2: confirm SKIPPED (--skip-confirm set; reserved for cron/auto)"
else
    log "STEP 2: requesting operator confirmation"
    printf "\n" >&2
    printf "═══════════════════════════════════════════════════════════════════\n" >&2
    printf "  EDGE-P2-flip CONFIRMATION REQUIRED\n" >&2
    printf "═══════════════════════════════════════════════════════════════════\n" >&2
    printf "  About to flip RiskConfig.exit.shadow_enabled to TRUE\n" >&2
    printf "  on engine: %s\n" "$ENGINE_MODE" >&2
    printf "\n" >&2
    printf "  Effect:\n" >&2
    printf "    - Combine Layer starts emitting decision_shadow_exits rows\n" >&2
    printf "    - Pure observation; ml_override_high=2.0 sentinel preserved\n" >&2
    printf "    - Phase 2 healthcheck [15] starts producing agreement metric\n" >&2
    printf "\n" >&2
    printf "  Rollback (90s): bash %s/helper_scripts/operator/edge_p2_revert.sh\n" "$SRV_ROOT" >&2
    printf "\n" >&2
    printf "  Type \"yes\" to proceed, anything else to abort: " >&2
    read -r CONFIRM_INPUT
    if [[ "$CONFIRM_INPUT" != "yes" ]]; then
        log "STEP 2: operator did not confirm (input='$CONFIRM_INPUT') — ABORT"
        exit 1
    fi
    log "STEP 2: operator confirmed"
fi

# ─── Step 3: Send IPC patch_risk_config / 送 IPC patch_risk_config ──────────

log "STEP 3: sending IPC patch_risk_config (exit.shadow_enabled=true)"
# Inline-Python one-liner: import sync_ipc_call, send the flip patch.
# Outputs a single status line (PASS/FAIL + version) to stdout that we tee.
# Inline-Python 一行：import sync_ipc_call 送 flip patch；輸出 PASS/FAIL + version。
PATCH_OUTPUT="$(
    OPENCLAW_BASE_DIR="$SRV_ROOT" \
    OPENCLAW_IPC_SOCKET="$SOCKET_PATH" \
    PYTHONPATH="$SRV_ROOT" \
    python3 -c "
import json,sys
sys.path.insert(0, '$SRV_ROOT/helper_scripts/canary')
from edge_p2_flip_dry_run import _sync_ipc_call
try:
    r = _sync_ipc_call('patch_risk_config', params={'engine': '$ENGINE_MODE', 'source': 'operator', 'patch': {'exit': {'shadow_enabled': True}}})
    if isinstance(r, dict) and r.get('ok') is True:
        print('PASS version=%s source=%s' % (r.get('version', '?'), r.get('source', '?')))
        sys.exit(0)
    print('FAIL response=%s' % json.dumps(r))
    sys.exit(2)
except Exception as e:
    print('FAIL exception=%s' % e)
    sys.exit(2)
" 2>&1
)"
PATCH_RC=$?
log "STEP 3: patch result: $PATCH_OUTPUT (rc=$PATCH_RC)"
if [[ "$PATCH_RC" != "0" ]]; then
    log "STEP 3: IPC patch FAILED — engine state unknown; run edge_p2_revert.sh now"
    exit 2
fi

# ─── Step 4: Verify post-flip / 驗證翻轉後狀態 ───────────────────────────────

log "STEP 4: waiting 5s for hot-reload propagation..."
sleep 5
log "STEP 4: verifying get_risk_config().exit.shadow_enabled == true"
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
    if val is True:
        print('PASS shadow_enabled=True version=%s' % r.get('version', '?'))
        sys.exit(0)
    print('FAIL shadow_enabled=%s (expected True)' % val)
    sys.exit(1)
except Exception as e:
    print('FAIL exception=%s' % e)
    sys.exit(1)
" 2>&1
)"
VERIFY_RC=$?
log "STEP 4: verify result: $VERIFY_OUTPUT (rc=$VERIFY_RC)"
if [[ "$VERIFY_RC" != "0" ]]; then
    log "STEP 4: post-flip verification FAILED — run edge_p2_revert.sh to be safe"
    exit 2
fi

# ─── Step 5: Run healthcheck [15] for early signal / 跑 healthcheck [15] ───

log "STEP 5: waiting 60s for first close events to land in decision_shadow_exits..."
sleep 60
log "STEP 5: running healthcheck (focus on [8] shadow_exits + [15] agreement)"
if [[ -f "$HEALTHCHECK_PY" ]]; then
    # Pipe healthcheck output through grep to extract [8] + [15] only.
    # healthcheck 輸出僅留 [8] + [15] 行（其他 check 與本流程無關）。
    python3 "$HEALTHCHECK_PY" 2>&1 | grep -E '\[8\]|\[15\]|FATAL' >> "$LOG_FILE" || true
    log "STEP 5: healthcheck samples appended to log (not gated on PASS — too early)"
else
    log "STEP 5: healthcheck script missing at $HEALTHCHECK_PY — skip"
fi

# ─── Done / 完成 ─────────────────────────────────────────────────────────────

log "EDGE-P2-flip COMPLETE · engine=$ENGINE_MODE · shadow_enabled=true · monitor [15] over next 24h"
log "Rollback if needed: bash $SRV_ROOT/helper_scripts/operator/edge_p2_revert.sh --engine-mode $ENGINE_MODE"
log "═══════════════════════════════════════════════════════════════════"
exit 0

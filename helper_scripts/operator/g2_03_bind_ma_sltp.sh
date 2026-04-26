#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# G2-03 ma_crossover SL/TP per-strategy binding SOP wrapper.
# G2-03 ma_crossover SL/TP 每策略 binding SOP wrapper.
#
# MODULE_NOTE (English):
#   Operator-runnable SOP wrapper to safely bind ma_crossover SL/TP per_strategy
#   override values via IPC `patch_risk_config`. Per PA RFC §4.2 binding SOP:
#     1. require operator to confirm + pass QC report path (G2-02 counterfactual)
#     2. dry-run diff: read current overrides + show before/after JSON
#     3. confirmation prompt — operator types "yes" + supplies report path
#     4. send IPC patch_risk_config (mutating)
#     5. wait 5s for hot-reload, then verify get_risk_config returns 4 expected fields
#     6. log all steps to $OPENCLAW_DATA_DIR/g2_03_bind_ma_sltp.log
#
#   Per memory `feedback_shell_paste_safety` — paste-safe one-liners only;
#   complex IPC + JSON math delegated to `helper_scripts/canary/g2_03_bind_helper.py`.
#   No heredoc, no multi-line for-loop, no inline complex variables.
#
#   Per memory `feedback_minimal_confirmation` + project_agent_p2_dynamic_sl_tp.md
#   §three-line defense — defense lines A (validate) and B (runtime cap) live in
#   Rust; this SOP wrapper is line C (offline manual review + dry-run before write).
#
# MODULE_NOTE (中文):
#   Operator 可執行的 SOP wrapper，透過 IPC patch_risk_config 安全綁定
#   ma_crossover SL/TP per_strategy 覆蓋值。依 PA RFC §4.2 binding SOP：
#     1. 要求 operator 確認 + 提供 QC report path（G2-02 counterfactual）
#     2. dry-run diff：讀現有 override，輸出 before/after JSON
#     3. 確認提示 —— operator 輸 "yes" + 提供 report path
#     4. 真送 IPC patch_risk_config
#     5. 等 5s hot-reload，verify get_risk_config 4 欄位匹配
#     6. 全步驟記錄至 $OPENCLAW_DATA_DIR/g2_03_bind_ma_sltp.log
#
#   依 memory feedback_shell_paste_safety —— paste-safe one-liner，
#   IPC + JSON 邏輯委派 g2_03_bind_helper.py，無 heredoc / 多行 for / 複雜變數。
#
#   依 memory project_agent_p2_dynamic_sl_tp.md 三道防線 —— A(validate) + B(runtime
#   cap) 在 Rust，本 SOP 為防線 C（離線人工審查 + dry-run 後寫入）。
#
# Reference / 參考:
#   PA RFC: srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-04-26--g2_03_option_b_rfc.md
#   helper:  srv/helper_scripts/canary/g2_03_bind_helper.py
#   IPC:     srv/program_code/exchange_connectors/.../control_api_v1/app/ipc_client.py
#
# Usage / 用法:
#   bash helper_scripts/operator/g2_03_bind_ma_sltp.sh \\
#        --engine-mode <paper|demo|live|live_demo> \\
#        --sl-pct <f> --tp-pct <f> \\
#        --trail-act-pct <f> --trail-dist-pct <f> \\
#        --qc-report-path <path> \\
#        [--skip-confirm]
#
#   --engine-mode      target engine
#   --sl-pct           stop_loss_max_pct_override (must <= P1 limits.stop_loss_max_pct)
#   --tp-pct           take_profit_max_pct_override (must <= P1 limits.take_profit_max_pct)
#   --trail-act-pct    trailing_activation_pct_override
#   --trail-dist-pct   trailing_distance_pct_override
#   --qc-report-path   path to QC + FA reviewed counterfactual report (REQUIRED)
#   --skip-confirm     skip operator confirmation (DANGEROUS; cron / auto only)
#
# Exit codes / 退出碼:
#   0 — bind succeeded; 4 override fields verified post-flip
#   1 — diff/apply/verify FAILED, or operator did not confirm
#   2 — IPC connect failure (engine likely down)
#   3 — env / argument precondition missing
# ═══════════════════════════════════════════════════════════════════════════════

set -u

# ─── Defaults / 預設 ────────────────────────────────────────────────────────────

ENGINE_MODE=""
SL_PCT=""
TP_PCT=""
TRAIL_ACT_PCT=""
TRAIL_DIST_PCT=""
QC_REPORT_PATH=""
SKIP_CONFIRM=0

# ─── Args parsing (paste-safe single-line / 單行解析) ───────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --engine-mode) ENGINE_MODE="$2"; shift 2 ;;
        --sl-pct) SL_PCT="$2"; shift 2 ;;
        --tp-pct) TP_PCT="$2"; shift 2 ;;
        --trail-act-pct) TRAIL_ACT_PCT="$2"; shift 2 ;;
        --trail-dist-pct) TRAIL_DIST_PCT="$2"; shift 2 ;;
        --qc-report-path) QC_REPORT_PATH="$2"; shift 2 ;;
        --skip-confirm) SKIP_CONFIRM=1; shift ;;
        -h|--help)
            echo "Usage: $0 --engine-mode <env> --sl-pct <f> --tp-pct <f> --trail-act-pct <f> --trail-dist-pct <f> --qc-report-path <path> [--skip-confirm]"
            exit 0
            ;;
        *)
            echo "Unknown arg: $1" >&2
            exit 3
            ;;
    esac
done

# Validate engine mode (defensive: reject typos before IPC).
# 驗證 engine mode（防禦性 —— 送 IPC 前擋打字錯）。
case "$ENGINE_MODE" in
    paper|demo|live|live_demo) : ;;
    *) echo "Invalid --engine-mode: '$ENGINE_MODE' (must be paper|demo|live|live_demo)" >&2; exit 3 ;;
esac

# Validate required floats present (Python helper does the strict numeric check).
# 驗證必要參數存在（嚴格數值檢查交給 Python helper）。
if [[ -z "$SL_PCT" || -z "$TP_PCT" || -z "$TRAIL_ACT_PCT" || -z "$TRAIL_DIST_PCT" ]]; then
    echo "Missing one of --sl-pct / --tp-pct / --trail-act-pct / --trail-dist-pct" >&2
    exit 3
fi
if [[ -z "$QC_REPORT_PATH" ]]; then
    echo "--qc-report-path REQUIRED (PA RFC §4.2 binding SOP needs G2-02 counterfactual review)" >&2
    exit 3
fi
if [[ ! -f "$QC_REPORT_PATH" ]]; then
    echo "QC report not found at: $QC_REPORT_PATH" >&2
    exit 3
fi

# ─── Path setup / 路徑設置 ──────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
HELPER_PY="$SRV_ROOT/helper_scripts/canary/g2_03_bind_helper.py"
LOG_FILE="$DATA_DIR/g2_03_bind_ma_sltp.log"

mkdir -p "$DATA_DIR"

# ─── Source env files if available / 自動 source env files（per restart_all.sh）──
# OPENCLAW_IPC_SECRET (from ipc_secret.txt) needs to be in env for IPC HMAC.
# OPENCLAW_IPC_SECRET（從 ipc_secret.txt）需在 env 為 IPC HMAC 所用。
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

# Single-line logger (paste-safe).
# 單行 logger（paste-safe）。
log() { local ts; ts="$(date -Iseconds)"; printf "%s [g2_03_bind] %s\n" "$ts" "$*" | tee -a "$LOG_FILE" >&2; }

# Banner.
log "═══════════════════════════════════════════════════════════════════"
log "G2-03 BIND START · engine=$ENGINE_MODE · sl=$SL_PCT tp=$TP_PCT trail_act=$TRAIL_ACT_PCT trail_dist=$TRAIL_DIST_PCT"
log "QC report: $QC_REPORT_PATH"

# ─── Env preconditions / 環境前置條件 ───────────────────────────────────────────

if ! command -v python3 >/dev/null 2>&1; then
    log "FATAL: python3 not found in PATH"
    exit 3
fi

SOCKET_PATH="${OPENCLAW_IPC_SOCKET:-$DATA_DIR/engine.sock}"
if [[ ! -S "$SOCKET_PATH" ]]; then
    log "FATAL: engine socket missing at $SOCKET_PATH (engine down?)"
    exit 3
fi

if [[ ! -f "$HELPER_PY" ]]; then
    log "FATAL: helper script missing at $HELPER_PY"
    exit 3
fi

# Common env for helper invocations (single-line export, paste-safe).
# helper invocation 的共通 env（單行 export，paste-safe）。
HELPER_ENV="OPENCLAW_BASE_DIR=\"$SRV_ROOT\" OPENCLAW_IPC_SOCKET=\"$SOCKET_PATH\" PYTHONPATH=\"$SRV_ROOT\""

# ─── Step 1: Dry-run diff / Dry-run diff ────────────────────────────────────────

log "STEP 1: dry-run diff (read current overrides + compose candidate)"
DIFF_OUTPUT="$(env OPENCLAW_BASE_DIR="$SRV_ROOT" OPENCLAW_IPC_SOCKET="$SOCKET_PATH" PYTHONPATH="$SRV_ROOT" python3 "$HELPER_PY" diff --engine-mode "$ENGINE_MODE" --sl-pct "$SL_PCT" --tp-pct "$TP_PCT" --trail-act-pct "$TRAIL_ACT_PCT" --trail-dist-pct "$TRAIL_DIST_PCT" --qc-report-path "$QC_REPORT_PATH" 2>&1)"
DIFF_RC=$?
log "STEP 1: diff rc=$DIFF_RC"
printf "%s\n" "$DIFF_OUTPUT" | tee -a "$LOG_FILE" >&2
if [[ "$DIFF_RC" != "0" ]]; then
    log "STEP 1: dry-run diff FAILED (rc=$DIFF_RC) — ABORT"
    exit "$DIFF_RC"
fi

# ─── Step 2: Operator confirmation / Operator 確認 ──────────────────────────────

if [[ "$SKIP_CONFIRM" == "1" ]]; then
    log "STEP 2: confirm SKIPPED (--skip-confirm; reserved for cron/auto)"
else
    log "STEP 2: requesting operator confirmation"
    printf "\n" >&2
    printf "═══════════════════════════════════════════════════════════════════\n" >&2
    printf "  G2-03 BIND CONFIRMATION REQUIRED\n" >&2
    printf "═══════════════════════════════════════════════════════════════════\n" >&2
    printf "  About to bind ma_crossover SL/TP per_strategy override on engine: %s\n" "$ENGINE_MODE" >&2
    printf "    sl_override         = %s\n" "$SL_PCT" >&2
    printf "    tp_override         = %s\n" "$TP_PCT" >&2
    printf "    trail_act_override  = %s\n" "$TRAIL_ACT_PCT" >&2
    printf "    trail_dist_override = %s\n" "$TRAIL_DIST_PCT" >&2
    printf "  QC counterfactual report: %s\n" "$QC_REPORT_PATH" >&2
    printf "\n" >&2
    printf "  Reminder (PA RFC §4.2 + §3.1):\n" >&2
    printf "    - QC + FA must have signed off on the counterfactual\n" >&2
    printf "    - validate() defense line A enforces override <= P1 limits\n" >&2
    printf "    - runtime defense line B clamps any survivor at P1\n" >&2
    printf "\n" >&2
    printf "  Type \"yes\" to send IPC patch, anything else to abort: " >&2
    read -r CONFIRM_INPUT
    if [[ "$CONFIRM_INPUT" != "yes" ]]; then
        log "STEP 2: operator did not confirm (input='$CONFIRM_INPUT') — ABORT"
        exit 1
    fi
    log "STEP 2: operator confirmed"
fi

# ─── Step 3: Apply IPC patch_risk_config / 真送 IPC patch_risk_config ───────────

log "STEP 3: sending IPC patch_risk_config (mutating)"
APPLY_OUTPUT="$(env OPENCLAW_BASE_DIR="$SRV_ROOT" OPENCLAW_IPC_SOCKET="$SOCKET_PATH" PYTHONPATH="$SRV_ROOT" python3 "$HELPER_PY" apply --engine-mode "$ENGINE_MODE" --sl-pct "$SL_PCT" --tp-pct "$TP_PCT" --trail-act-pct "$TRAIL_ACT_PCT" --trail-dist-pct "$TRAIL_DIST_PCT" --qc-report-path "$QC_REPORT_PATH" 2>&1)"
APPLY_RC=$?
log "STEP 3: apply rc=$APPLY_RC"
printf "%s\n" "$APPLY_OUTPUT" | tee -a "$LOG_FILE" >&2
if [[ "$APPLY_RC" != "0" ]]; then
    log "STEP 3: IPC apply FAILED (rc=$APPLY_RC) — engine state unknown"
    log "STEP 3: investigate $LOG_FILE; engine MAY still be in pre-patch state"
    exit "$APPLY_RC"
fi

# ─── Step 4: Wait for hot-reload + verify / 等熱重載 + 驗證 ─────────────────────

log "STEP 4: waiting 5s for ArcSwap hot-reload propagation..."
sleep 5
log "STEP 4: verifying 4 override fields landed via get_risk_config()"
VERIFY_OUTPUT="$(env OPENCLAW_BASE_DIR="$SRV_ROOT" OPENCLAW_IPC_SOCKET="$SOCKET_PATH" PYTHONPATH="$SRV_ROOT" python3 "$HELPER_PY" verify --engine-mode "$ENGINE_MODE" --sl-pct "$SL_PCT" --tp-pct "$TP_PCT" --trail-act-pct "$TRAIL_ACT_PCT" --trail-dist-pct "$TRAIL_DIST_PCT" --qc-report-path "$QC_REPORT_PATH" 2>&1)"
VERIFY_RC=$?
log "STEP 4: verify rc=$VERIFY_RC"
printf "%s\n" "$VERIFY_OUTPUT" | tee -a "$LOG_FILE" >&2
if [[ "$VERIFY_RC" != "0" ]]; then
    log "STEP 4: post-bind verification FAILED — engine may have rejected patch silently"
    log "STEP 4: investigate $LOG_FILE; consider IPC patch_risk_config to revert"
    exit "$VERIFY_RC"
fi

# ─── Done / 完成 ─────────────────────────────────────────────────────────────────

log "G2-03 BIND COMPLETE · engine=$ENGINE_MODE · 4 override fields verified live"
log "Monitor ma_crossover behaviour over next 14d (PA RFC §5.1 shadow observation)"
log "Rollback if needed: re-run this script with original (or default None) values"
log "═══════════════════════════════════════════════════════════════════"
exit 0

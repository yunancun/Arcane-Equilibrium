#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════
# W-AUDIT-8a C1 v2 resilient harness — operator-facing wrapper
#
# 用途：
#   包裝 `liquidation_topic_probe_v2.py` 的 24h proof 與 60s smoke 啟動命令，
#   讓 operator 一行指令就跑（避免 SSH oneliner 過長違反
#   `feedback_shell_paste_safety.md` 規則 D >120 char 容易軟折行 +
#   $(date ...) × 2 動態變數雙重展開 race）。
#
# v1 (`liquidation_topic_probe.py`) 是凍結 baseline 對照；本 wrapper 只跑 v2。
#
# 設計權威：docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md
# A3 review WARN-1：oneliner 過長 / dynamic $(date) 雙展開 race → 改用 wrapper
#
# 使用：
#   1. 24h proof (預設)：
#        ssh trade-core 'bash ~/BybitOpenClaw/srv/helper_scripts/bybit/run_c1_v2_proof.sh'
#   2. 60s smoke：
#        ssh trade-core 'bash ~/BybitOpenClaw/srv/helper_scripts/bybit/run_c1_v2_proof.sh --smoke-60s'
#   3. 顯示 help：
#        bash helper_scripts/bybit/run_c1_v2_proof.sh --help
#
# Output：
#   - 啟動後 echo PID + log_path + checkpoint_path（operator 拷貝紀錄用）
#   - Progress check 隨時透過：
#        ssh trade-core 'jq . /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json'
# ═══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 解析 flag ───────────────────────────────────────────────────────────
MODE="proof"          # proof (24h) | smoke (60s)
MIDNIGHT_ALIGN="yes"  # yes (預設等 UTC midnight) | no (立即開始 24h proof)

usage() {
    cat <<'USAGE'
W-AUDIT-8a C1 v2 resilient harness wrapper

Usage:
  bash run_c1_v2_proof.sh                # 24h proof (default, UTC midnight alignment)
  bash run_c1_v2_proof.sh --no-midnight  # 24h proof, 立即開始（不等 midnight）
  bash run_c1_v2_proof.sh --smoke-60s    # 60s smoke (verify tooling reachable)
  bash run_c1_v2_proof.sh --help

Flags:
  --no-midnight  Skip UTC midnight alignment; 立即啟 24h proof（24h window 不對齊
                 funding cycle，但 wall-clock 提前 ~9h）。預設啟用 alignment
                 是為 BB sign-off 24h window 覆蓋 3 個完整 8h funding cycle。
  --smoke-60s    Run 60s smoke mode (non-blocking; immediate result)
  --help, -h     Show this help

Output:
  - PID, log path, checkpoint path echo to stdout
  - Background process nohup-detached (24h proof) or foreground (60s smoke)

Status check (24h proof):
  ssh trade-core 'jq . /tmp/openclaw/audit/liquidation_topic_probe/c1_proof_progress.json'

Design SoT:
  docs/execution_plan/2026-05-16--w_audit_8a_c1_v2_resilient_proof.md
USAGE
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --smoke-60s)
            MODE="smoke"
            shift
            ;;
        --no-midnight)
            MIDNIGHT_ALIGN="no"
            shift
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo "Unknown flag: $1" >&2
            usage
            exit 2
            ;;
    esac
done

# ── 路徑常量 ─────────────────────────────────────────────────────────────
# 統一 session_id：用一次 date 不要兩次 $(date) 避免 nanosecond 不一致
SESSION_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
AUDIT_DIR="${OPENCLAW_DATA_DIR}/audit/liquidation_topic_probe"
mkdir -p "${AUDIT_DIR}"

# 自動定位 v2 probe path：以本 script 所在目錄為基準
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROBE_PY="${SCRIPT_DIR}/liquidation_topic_probe_v2.py"

if [[ ! -f "${PROBE_PY}" ]]; then
    echo "ERROR: probe script not found at ${PROBE_PY}" >&2
    exit 2
fi

# ── 模式分支 ─────────────────────────────────────────────────────────────
if [[ "${MODE}" == "smoke" ]]; then
    # 60s smoke：前景跑，retcode 立即可見；checkpoint 60s 後寫一次
    SESSION_ID="c1_v2_smoke_${SESSION_STAMP}"
    echo "[run_c1_v2_proof.sh] mode=smoke session_id=${SESSION_ID}"
    echo "[run_c1_v2_proof.sh] expected duration=60s + ~5s final report write"
    exec python3 "${PROBE_PY}" \
        --duration-sec 60 \
        --enable-reconnect \
        --max-restart 3 \
        --checkpoint-interval-sec 60 \
        --ping-interval-sec 10 \
        --session-id "${SESSION_ID}" \
        --output-dir "${AUDIT_DIR}"
fi

# 預設：24h proof（背景 nohup）
SESSION_ID="c1_v2_${SESSION_STAMP}"
NOHUP_LOG="${AUDIT_DIR}/nohup_c1_v2_${SESSION_STAMP}.log"
CHECKPOINT_PATH="${AUDIT_DIR}/c1_proof_progress.json"

# 組合 probe 額外 flag：midnight alignment 條件啟用
EXTRA_FLAGS=()
if [[ "${MIDNIGHT_ALIGN}" == "yes" ]]; then
    EXTRA_FLAGS+=(--start-utc-midnight)
    ALIGNMENT_DESC="UTC midnight alignment (等下次 UTC 00:00 才啟 24h proof)"
else
    ALIGNMENT_DESC="immediate start (no midnight alignment; 立即 24h proof)"
fi

echo "[run_c1_v2_proof.sh] mode=proof session_id=${SESSION_ID}"
echo "[run_c1_v2_proof.sh] target_duration=86400s (24h) + ${ALIGNMENT_DESC}"
echo "[run_c1_v2_proof.sh] nohup_log=${NOHUP_LOG}"
echo "[run_c1_v2_proof.sh] checkpoint=${CHECKPOINT_PATH}"

# nohup background；2>&1 redirect 全部 stdout/stderr 到 log；`&` 後 echo $!
nohup python3 "${PROBE_PY}" \
    --topic allLiquidation.BTCUSDT \
    --duration-sec 86400 \
    --enable-reconnect \
    --max-restart 3 \
    --checkpoint-interval-sec 3600 \
    --ping-interval-sec 10 \
    "${EXTRA_FLAGS[@]}" \
    --session-id "${SESSION_ID}" \
    --output-dir "${AUDIT_DIR}" \
    > "${NOHUP_LOG}" 2>&1 &

PROBE_PID=$!
echo "[run_c1_v2_proof.sh] PID=${PROBE_PID}"
echo "[run_c1_v2_proof.sh] Status check oneliner:"
echo "  jq . ${CHECKPOINT_PATH}"
echo "[run_c1_v2_proof.sh] To early abort:"
echo "  kill ${PROBE_PID} && touch ${AUDIT_DIR}/ABORTED_${SESSION_STAMP}.flag"

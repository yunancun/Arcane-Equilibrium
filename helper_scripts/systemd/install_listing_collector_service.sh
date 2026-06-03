#!/usr/bin/env bash
# install_listing_collector_service.sh — Linux systemd installer for listing capture collector
#
# MODULE_NOTE
# 模塊用途：將 helper_scripts/systemd/openclaw-listing-collector.service 模板
#   sed-replace 占位符後安裝到 /etc/systemd/system/，並 daemon-reload。
#   對應 COLLECTOR-LISTING-CAPTURE-PROD（OQ-2 systemd 常駐）。比照 install_engine
#   _service.sh 範式。
# 硬邊界：
#   1. Linux only — macOS 跑此腳本立即 exit 1
#   2. 必須 sudo / root 跑（寫 /etc/systemd/system/）
#   3. 不自動 enable / start — 寫完 unit + daemon-reload 即停；operator 手動 enable+start
#   4. collector 必須以非 root 身份跑
#   5. --dry-run：只 sed + 占位符殘留檢查 + syntax verify，不寫 /etc/systemd/system/
#      （DoD #10：可在無 sudo 下驗證模板 render 正確）
#
# 使用（正式安裝）：
#   sudo OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
#        OPENCLAW_DATA_DIR=/tmp/openclaw \
#        OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets \
#        COLLECTOR_USER=ncyu COLLECTOR_GROUP=ncyu \
#        PYTHON_BIN=/usr/bin/python3 \
#        bash helper_scripts/systemd/install_listing_collector_service.sh
#
# 使用（dry-run 驗證，免 sudo）：
#   OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
#   OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets \
#   COLLECTOR_USER=ncyu PYTHON_BIN=/usr/bin/python3 \
#   bash helper_scripts/systemd/install_listing_collector_service.sh --dry-run

set -euo pipefail

DRY_RUN=0
if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=1
fi

# 跨平台 guard — Linux only
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[install][FAIL] systemd unit 只在 Linux 安裝；當前 $(uname -s)" >&2
    exit 1
fi

# Root guard（dry-run 免）
if [[ "$DRY_RUN" -eq 0 && "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "[install][FAIL] 需 sudo / root 權限寫 /etc/systemd/system/（或加 --dry-run 免 sudo 驗證）" >&2
    exit 2
fi

# 必填 env
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:?OPENCLAW_BASE_DIR 未設定 (例: /home/ncyu/BybitOpenClaw/srv)}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:?OPENCLAW_SECRETS_ROOT 未設定 (例: /home/ncyu/BybitOpenClaw/secrets)}"
COLLECTOR_USER="${COLLECTOR_USER:-${SUDO_USER:-$(id -un)}}"
COLLECTOR_GROUP="${COLLECTOR_GROUP:-$COLLECTOR_USER}"
PYTHON_BIN="${PYTHON_BIN:-/usr/bin/python3}"

UNIT_NAME="openclaw-listing-collector.service"
TEMPLATE="${OPENCLAW_BASE_DIR}/helper_scripts/systemd/${UNIT_NAME}"
TARGET="/etc/systemd/system/${UNIT_NAME}"

# 前置條件檢查（fail-closed）
[[ -f "$TEMPLATE" ]] || { echo "[install][FAIL] 模板不存在: $TEMPLATE" >&2; exit 3; }
[[ -f "$OPENCLAW_BASE_DIR/helper_scripts/collectors/listing_capture/daemon.py" ]] || { echo "[install][FAIL] collector daemon 入口不存在" >&2; exit 4; }
[[ -d "$OPENCLAW_SECRETS_ROOT/environment_files" ]] || { echo "[install][FAIL] secrets env 目錄不存在: $OPENCLAW_SECRETS_ROOT/environment_files" >&2; exit 5; }
[[ -s "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" ]] || { echo "[install][FAIL] basic_system_services.env 不存在或為空" >&2; exit 6; }

# 確認 user 存在
if ! id -u "$COLLECTOR_USER" >/dev/null 2>&1; then
    echo "[install][FAIL] user 不存在: $COLLECTOR_USER" >&2
    exit 7
fi

# 拒絕 root user
if [[ "$COLLECTOR_USER" == "root" ]]; then
    echo "[install][FAIL] 不允許 COLLECTOR_USER=root；collector 必須以非 root 身份跑" >&2
    exit 8
fi

echo "[install] $( [[ "$DRY_RUN" -eq 1 ]] && echo "(DRY-RUN) " )安裝 $UNIT_NAME"
echo "  COLLECTOR_USER    = $COLLECTOR_USER"
echo "  COLLECTOR_GROUP   = $COLLECTOR_GROUP"
echo "  OPENCLAW_BASE_DIR = $OPENCLAW_BASE_DIR"
echo "  OPENCLAW_DATA_DIR = $OPENCLAW_DATA_DIR"
echo "  OPENCLAW_SECRETS_ROOT = $OPENCLAW_SECRETS_ROOT"
echo "  PYTHON_BIN        = $PYTHON_BIN"
echo "  TARGET            = $TARGET"

# 用 tmp file + atomic mv 避半成型 unit
TMP_UNIT="$(mktemp /tmp/openclaw-listing-collector.service.XXXXXX)"
trap 'rm -f "$TMP_UNIT"' EXIT

sed \
    -e "s|__COLLECTOR_USER__|${COLLECTOR_USER}|g" \
    -e "s|__COLLECTOR_GROUP__|${COLLECTOR_GROUP}|g" \
    -e "s|__OPENCLAW_BASE_DIR__|${OPENCLAW_BASE_DIR}|g" \
    -e "s|__OPENCLAW_DATA_DIR__|${OPENCLAW_DATA_DIR}|g" \
    -e "s|__OPENCLAW_SECRETS_ROOT__|${OPENCLAW_SECRETS_ROOT}|g" \
    -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    "$TEMPLATE" > "$TMP_UNIT"

# 占位符殘留檢查（防 sed 漏 replace）
if grep -E '__(COLLECTOR_USER|COLLECTOR_GROUP|OPENCLAW_BASE_DIR|OPENCLAW_DATA_DIR|OPENCLAW_SECRETS_ROOT|PYTHON_BIN)__' "$TMP_UNIT" >/dev/null; then
    echo "[install][FAIL] 占位符未完全替換" >&2
    grep -nE '__[A-Z_]+__' "$TMP_UNIT" >&2 || true
    exit 9
fi

# systemd unit syntax 驗證 — 區分 warn vs error
if command -v systemd-analyze >/dev/null 2>&1; then
    set +e
    verify_output="$(systemd-analyze verify "$TMP_UNIT" 2>&1)"
    verify_rc=$?
    set -e
    if [[ -n "$verify_output" ]]; then
        echo "$verify_output" >&2
    fi
    if [[ $verify_rc -ne 0 ]]; then
        if echo "$verify_output" | grep -qi 'Error'; then
            echo "[install][FAIL] systemd-analyze verify 報 Error；拒絕安裝半成型 unit" >&2
            exit 10
        fi
        echo "[install][WARN] systemd-analyze verify 報 warning；繼續" >&2
    fi
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[install][DRY-RUN OK] 模板 render + 占位符檢查 + syntax verify 全過；未寫 $TARGET"
    echo "[install][DRY-RUN] 預覽 unit 內容："
    sed 's/^/    /' "$TMP_UNIT"
    exit 0
fi

install -m 644 "$TMP_UNIT" "$TARGET"
echo "[install][OK] 寫入 $TARGET"

systemctl daemon-reload
echo "[install][OK] systemctl daemon-reload 完成"

echo ""
echo "下一步（operator 手動）："
echo "  sudo systemctl enable openclaw-listing-collector    # 開機自啟"
echo "  sudo systemctl start openclaw-listing-collector     # 啟動服務"
echo "  sudo systemctl status openclaw-listing-collector    # 確認狀態"
echo "  sudo journalctl -u openclaw-listing-collector -f    # 跟蹤日誌"
echo ""
echo "[install][DONE]"

#!/usr/bin/env bash
# install_watchdog_service.sh — Linux systemd unit installer for openclaw-watchdog
#
# MODULE_NOTE
# 模塊用途：將 helper_scripts/systemd/openclaw-watchdog.service 模板
#   sed-replace 占位符後安裝到 /etc/systemd/system/。
#   per P0-OPS-4 §10 GAP A runbook 要求。
# 硬邊界：
#   1. Linux only — macOS exit 1（請用 launchd plist）
#   2. 必須 sudo / root 跑
#   3. 自動偵測 python venv 位置（PYTHON_BIN env 可覆寫）；
#      預設順序：$PYTHON_BIN > $HOME/.venv/bin/python3 > /usr/bin/python3
#   4. install 後不啟動服務 — 留 operator 手動 enable + start
#
# 使用：
#   sudo OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
#        OPENCLAW_DATA_DIR=/tmp/openclaw \
#        OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets \
#        ENGINE_USER=ncyu ENGINE_GROUP=ncyu \
#        PYTHON_BIN=/home/ncyu/.venv/bin/python3 \
#        bash helper_scripts/systemd/install_watchdog_service.sh

set -euo pipefail

# 跨平台 guard
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[install][FAIL] systemd unit 只在 Linux 安裝；當前 $(uname -s) — Mac 請用 helper_scripts/deploy/com.openclaw.engine-watchdog.plist" >&2
    exit 1
fi

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "[install][FAIL] 需 sudo / root 權限寫 /etc/systemd/system/" >&2
    exit 2
fi

OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:?OPENCLAW_BASE_DIR 未設定}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:?OPENCLAW_SECRETS_ROOT 未設定}"
ENGINE_USER="${ENGINE_USER:-${SUDO_USER:-$(id -un)}}"
ENGINE_GROUP="${ENGINE_GROUP:-$ENGINE_USER}"

# Python venv 偵測 — operator 顯式設定 > engine_user $HOME/.venv > 系統 python3
detect_python_bin() {
    if [[ -n "${PYTHON_BIN:-}" ]]; then
        echo "$PYTHON_BIN"; return 0
    fi
    # 取 ENGINE_USER 的 $HOME（非 root user 跑 sudo 時 $HOME 已切換）
    local engine_home
    engine_home="$(getent passwd "$ENGINE_USER" | cut -d: -f6 || true)"
    if [[ -n "$engine_home" && -x "$engine_home/.venv/bin/python3" ]]; then
        echo "$engine_home/.venv/bin/python3"; return 0
    fi
    if [[ -x /usr/bin/python3 ]]; then
        echo "/usr/bin/python3"; return 0
    fi
    return 1
}

if ! PYTHON_BIN="$(detect_python_bin)"; then
    echo "[install][FAIL] 找不到 python3 binary；請顯式 export PYTHON_BIN=/abs/path/to/python3" >&2
    exit 3
fi

UNIT_NAME="openclaw-watchdog.service"
TEMPLATE="${OPENCLAW_BASE_DIR}/helper_scripts/systemd/${UNIT_NAME}"
TARGET="/etc/systemd/system/${UNIT_NAME}"

[[ -f "$TEMPLATE" ]] || { echo "[install][FAIL] 模板不存在: $TEMPLATE" >&2; exit 4; }
[[ -x "$PYTHON_BIN" ]] || { echo "[install][FAIL] python binary 不可執行: $PYTHON_BIN" >&2; exit 5; }
[[ -f "$OPENCLAW_BASE_DIR/helper_scripts/canary/engine_watchdog.py" ]] || { echo "[install][FAIL] engine_watchdog.py 不存在" >&2; exit 6; }
[[ -s "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" ]] || { echo "[install][FAIL] basic_system_services.env 不存在或為空" >&2; exit 7; }

if ! id -u "$ENGINE_USER" >/dev/null 2>&1; then
    echo "[install][FAIL] user 不存在: $ENGINE_USER" >&2
    exit 8
fi

echo "[install] 安裝 $UNIT_NAME"
echo "  ENGINE_USER           = $ENGINE_USER"
echo "  ENGINE_GROUP          = $ENGINE_GROUP"
echo "  PYTHON_BIN            = $PYTHON_BIN"
echo "  OPENCLAW_BASE_DIR     = $OPENCLAW_BASE_DIR"
echo "  OPENCLAW_DATA_DIR     = $OPENCLAW_DATA_DIR"
echo "  OPENCLAW_SECRETS_ROOT = $OPENCLAW_SECRETS_ROOT"
echo "  TARGET                = $TARGET"

TMP_UNIT="$(mktemp /tmp/openclaw-watchdog.service.XXXXXX)"
trap 'rm -f "$TMP_UNIT"' EXIT

sed \
    -e "s|__ENGINE_USER__|${ENGINE_USER}|g" \
    -e "s|__ENGINE_GROUP__|${ENGINE_GROUP}|g" \
    -e "s|__OPENCLAW_BASE_DIR__|${OPENCLAW_BASE_DIR}|g" \
    -e "s|__OPENCLAW_DATA_DIR__|${OPENCLAW_DATA_DIR}|g" \
    -e "s|__OPENCLAW_SECRETS_ROOT__|${OPENCLAW_SECRETS_ROOT}|g" \
    -e "s|__PYTHON_BIN__|${PYTHON_BIN}|g" \
    "$TEMPLATE" > "$TMP_UNIT"

if grep -E '__(ENGINE_USER|ENGINE_GROUP|OPENCLAW_BASE_DIR|OPENCLAW_DATA_DIR|OPENCLAW_SECRETS_ROOT|PYTHON_BIN)__' "$TMP_UNIT" >/dev/null; then
    echo "[install][FAIL] 占位符未完全替換" >&2
    grep -nE '__[A-Z_]+__' "$TMP_UNIT" >&2 || true
    exit 9
fi

if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze verify "$TMP_UNIT" 2>&1 || \
        echo "[install][WARN] systemd-analyze verify 報 warning；繼續" >&2
fi

install -m 644 "$TMP_UNIT" "$TARGET"
echo "[install][OK] 寫入 $TARGET"

systemctl daemon-reload
echo "[install][OK] systemctl daemon-reload 完成"

echo ""
echo "下一步（operator 手動）："
echo "  sudo systemctl enable openclaw-watchdog   # 開機自啟"
echo "  sudo systemctl start openclaw-watchdog    # 啟動 watchdog"
echo "  sudo systemctl status openclaw-watchdog   # 確認狀態"
echo "  sudo journalctl -u openclaw-watchdog -f   # 跟蹤日誌"
echo ""
echo "  # 驗 watchdog 確實在跑 + 看 engine 狀態："
echo "  python3 $OPENCLAW_BASE_DIR/helper_scripts/canary/engine_watchdog.py --data-dir $OPENCLAW_DATA_DIR --status"
echo ""
echo "[install][DONE]"

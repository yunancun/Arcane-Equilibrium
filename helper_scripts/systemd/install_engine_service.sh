#!/usr/bin/env bash
# install_engine_service.sh — Linux systemd unit installer for openclaw-engine
#
# MODULE_NOTE
# 模塊用途：將 helper_scripts/systemd/openclaw-engine.service 模板
#   sed-replace 占位符後安裝到 /etc/systemd/system/，並 daemon-reload。
#   per P0-OPS-4 §10 GAP F runbook 要求；對應 macOS launchd_preflight.sh。
# 硬邊界：
#   1. Linux only — macOS 跑此腳本立即 exit 1（請用 launchd plist）
#   2. 必須 sudo / root 跑（寫 /etc/systemd/system/）
#   3. 不自動 enable / start — 寫完 unit + daemon-reload 即停；
#      operator 走 5-gate launch sequence（per runbook §1.3）後手動
#      systemctl enable + start
#   4. install 後不啟動服務 — 留給 operator 後續 `systemctl start` 控制
#
# 使用：
#   sudo OPENCLAW_BASE_DIR=/home/ncyu/BybitOpenClaw/srv \
#        OPENCLAW_DATA_DIR=/tmp/openclaw \
#        OPENCLAW_SECRETS_ROOT=/home/ncyu/BybitOpenClaw/secrets \
#        ENGINE_USER=ncyu ENGINE_GROUP=ncyu \
#        bash helper_scripts/systemd/install_engine_service.sh

set -euo pipefail

# 跨平台 guard — Linux only
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[install][FAIL] systemd unit 只在 Linux 安裝；當前 $(uname -s) — 請用 helper_scripts/deploy/launchd_preflight.sh + launchd plist" >&2
    exit 1
fi

# Root guard
if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
    echo "[install][FAIL] 需 sudo / root 權限寫 /etc/systemd/system/" >&2
    exit 2
fi

# 必填 env
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:?OPENCLAW_BASE_DIR 未設定 (例: /home/ncyu/BybitOpenClaw/srv)}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:?OPENCLAW_SECRETS_ROOT 未設定 (例: /home/ncyu/BybitOpenClaw/secrets)}"
ENGINE_USER="${ENGINE_USER:-${SUDO_USER:-$(id -un)}}"
ENGINE_GROUP="${ENGINE_GROUP:-$ENGINE_USER}"

UNIT_NAME="openclaw-engine.service"
TEMPLATE="${OPENCLAW_BASE_DIR}/helper_scripts/systemd/${UNIT_NAME}"
TARGET="/etc/systemd/system/${UNIT_NAME}"

# 前置條件檢查（fail-closed）
[[ -f "$TEMPLATE" ]] || { echo "[install][FAIL] 模板不存在: $TEMPLATE" >&2; exit 3; }
[[ -d "$OPENCLAW_BASE_DIR/rust/target/release" ]] || { echo "[install][WARN] engine binary 目錄不存在: $OPENCLAW_BASE_DIR/rust/target/release（先跑 restart_all.sh --rebuild）"; }
[[ -d "$OPENCLAW_SECRETS_ROOT/environment_files" ]] || { echo "[install][FAIL] secrets env 目錄不存在: $OPENCLAW_SECRETS_ROOT/environment_files" >&2; exit 4; }
[[ -s "$OPENCLAW_SECRETS_ROOT/environment_files/basic_system_services.env" ]] || { echo "[install][FAIL] basic_system_services.env 不存在或為空" >&2; exit 5; }

# 確認 user 存在（防 sed 出非法 unit）
if ! id -u "$ENGINE_USER" >/dev/null 2>&1; then
    echo "[install][FAIL] user 不存在: $ENGINE_USER" >&2
    exit 6
fi

# 拒絕 root user — engine 必須以非 root 身份跑（per README 反模式「不寫 User=root」）
# 防護 `su - root` 啟 install 時 SUDO_USER 缺失 → fallback id -un=root 的場景
if [[ "$ENGINE_USER" == "root" ]]; then
    echo "[install][FAIL] 不允許 ENGINE_USER=root；engine 必須以非 root 身份跑（per systemd README §反模式）" >&2
    echo "[install] 提示：顯式 export ENGINE_USER=<非 root 帳號> 後重跑" >&2
    exit 12
fi

echo "[install] 安裝 $UNIT_NAME"
echo "  ENGINE_USER       = $ENGINE_USER"
echo "  ENGINE_GROUP      = $ENGINE_GROUP"
echo "  OPENCLAW_BASE_DIR = $OPENCLAW_BASE_DIR"
echo "  OPENCLAW_DATA_DIR = $OPENCLAW_DATA_DIR"
echo "  OPENCLAW_SECRETS_ROOT = $OPENCLAW_SECRETS_ROOT"
echo "  TARGET            = $TARGET"

# 用 tmp file + atomic mv 避半成型 unit
TMP_UNIT="$(mktemp /tmp/openclaw-engine.service.XXXXXX)"
trap 'rm -f "$TMP_UNIT"' EXIT

sed \
    -e "s|__ENGINE_USER__|${ENGINE_USER}|g" \
    -e "s|__ENGINE_GROUP__|${ENGINE_GROUP}|g" \
    -e "s|__OPENCLAW_BASE_DIR__|${OPENCLAW_BASE_DIR}|g" \
    -e "s|__OPENCLAW_DATA_DIR__|${OPENCLAW_DATA_DIR}|g" \
    -e "s|__OPENCLAW_SECRETS_ROOT__|${OPENCLAW_SECRETS_ROOT}|g" \
    "$TEMPLATE" > "$TMP_UNIT"

# 占位符殘留檢查（防 sed 漏 replace）
if grep -E '__(ENGINE_USER|ENGINE_GROUP|OPENCLAW_BASE_DIR|OPENCLAW_DATA_DIR|OPENCLAW_SECRETS_ROOT)__' "$TMP_UNIT" >/dev/null; then
    echo "[install][FAIL] 占位符未完全替換，請檢查模板" >&2
    grep -nE '__[A-Z_]+__' "$TMP_UNIT" >&2 || true
    exit 7
fi

# systemd unit syntax 驗證 — 區分 warn vs error
# verify 退出碼非 0 但 stdout/stderr 只含 Warning → 繼續安裝
# 退出碼非 0 且含 Error → exit 11 拒絕半成型 unit
if command -v systemd-analyze >/dev/null 2>&1; then
    verify_output="$(systemd-analyze verify "$TMP_UNIT" 2>&1 || true)"
    verify_rc=$?
    if [[ -n "$verify_output" ]]; then
        echo "$verify_output" >&2
    fi
    if [[ $verify_rc -ne 0 ]]; then
        if echo "$verify_output" | grep -qi 'Error'; then
            echo "[install][FAIL] systemd-analyze verify 報 Error；拒絕安裝半成型 unit" >&2
            exit 11
        fi
        echo "[install][WARN] systemd-analyze verify 報 warning（可能因 Documentation file:// 路徑檢查）；繼續安裝" >&2
    fi
fi

install -m 644 "$TMP_UNIT" "$TARGET"
echo "[install][OK] 寫入 $TARGET"

systemctl daemon-reload
echo "[install][OK] systemctl daemon-reload 完成"

echo ""
echo "下一步（operator 手動）："
echo "  sudo systemctl enable openclaw-engine     # 開機自啟"
echo "  sudo systemctl start openclaw-engine      # 啟動服務"
echo "  sudo systemctl status openclaw-engine     # 確認狀態"
echo "  sudo journalctl -u openclaw-engine -f     # 跟蹤日誌"
echo ""
echo "[install][DONE]"

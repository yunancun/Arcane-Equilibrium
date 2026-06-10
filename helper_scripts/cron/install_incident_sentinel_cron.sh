#!/usr/bin/env bash
# install_incident_sentinel_cron.sh — L2 Mesh P2p 哨兵 cron idempotent installer
#   （mirror install_pg_dump_cron.sh 模式：Linux only / dry-run 預設 /
#     OPENCLAW_SENTINEL_CRON_APPLY=1 才寫 crontab / 偵測既有條目 / 支援 --remove）。
#
# 安裝內容（單一 crontab entry）：
#   */5 * * * * → incident_sentinel_cron.sh（6 軸唯讀監測 + alert-only，設計 §5.1）
#
# rollback = 本 script --remove（或手動 crontab -e 刪行）→ 系統回到 P2p 前狀態，
# 零殘留（state/audit 檔為 inert 資料，可留可刪）。
#
# 硬邊界：
#   - 不寫 secrets；不改 PG schema；不觸 engine/app
#   - idempotent guard：crontab 已有 incident_sentinel 條目 → refuse install
#   - 路徑不硬編碼（per memory feedback_cross_platform）

set -euo pipefail

# ----- 平台守門：僅 Linux 跑（mirror install_pg_dump_cron.sh）-----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_incident_sentinel_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/incident_sentinel_cron.sh"
MARKER="incident_sentinel_cron.sh"

# ----- --remove 模式：移除既有條目（同樣受 APPLY gate 保護）-----
if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no incident_sentinel cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_SENTINEL_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_SENTINEL_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: incident_sentinel cron entry. Verify with: crontab -l | grep incident_sentinel"
    exit 0
fi

# ----- pre-flight -----
if [[ ! -x "$WRAPPER" ]]; then
    echo "ERROR: wrapper not executable: $WRAPPER" >&2
    echo "       chmod +x \"$WRAPPER\" 後再跑 install。" >&2
    exit 5
fi
mkdir -p "$OPENCLAW_DATA_DIR/logs"

# ----- idempotent guard：已有條目 → refuse，強制 operator 顯式 --remove -----
if crontab -l 2>/dev/null | grep -q "$MARKER"; then
    echo "SKIP: existing incident_sentinel cron entry detected; not installing (use --remove first)." >&2
    crontab -l | grep "$MARKER" >&2
    exit 0
fi

# ----- env value validation：防 cron 特殊字 / 空格 / 過長 entry 解析錯亂 -----
# cron 對 `%` 解為 stdin 換行；space 拆 token 破解析；control char 直接 corrupt
# crontab；長度 > 200 通常是 ENV 污染。任一不合即 abort（mirror install_pg_dump）。
_validate_cron_env_value() {
    local name="$1"
    local value="$2"
    if [[ -z "$value" ]]; then
        echo "ERROR: cron env value empty: ${name}" >&2
        exit 6
    fi
    if [[ ${#value} -gt 200 ]]; then
        echo "ERROR: cron env value too long (>200 chars): ${name}=${value}" >&2
        exit 6
    fi
    if [[ "$value" =~ [[:space:]%[:cntrl:]\"\'\\\$\`] ]]; then
        echo "ERROR: cron-conflict character in ${name}=${value}" >&2
        echo "       Disallowed: space / % / control / quote / backslash / \$ / backtick" >&2
        exit 6
    fi
}

_validate_cron_env_value "OPENCLAW_BASE_DIR" "$OPENCLAW_BASE_DIR"
_validate_cron_env_value "OPENCLAW_DATA_DIR" "$OPENCLAW_DATA_DIR"
_validate_cron_env_value "OPENCLAW_SECRETS_ROOT" "$OPENCLAW_SECRETS_ROOT"
_validate_cron_env_value "WRAPPER" "$WRAPPER"

# 為什麼 plain 組裝不用 printf %q：cron 不跑 full shell parser，唯一可靠路徑是
# 上面 validation reject special char（mirror install_pg_dump_cron.sh 同理由）。
ENTRY="*/5 * * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_SECRETS_ROOT=${OPENCLAW_SECRETS_ROOT} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/incident_sentinel_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule: */5 * * * * (every 5 minutes)"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/incident_sentinel.last_fire"
echo "Audit: $OPENCLAW_DATA_DIR/incident_sentinel_events.jsonl"
echo "Rollback: $0 --remove (with OPENCLAW_SENTINEL_CRON_APPLY=1)"

if [[ "${OPENCLAW_SENTINEL_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_SENTINEL_CRON_APPLY=1 to actually install."
    echo
    echo "預檢建議（apply 前）："
    echo "  1. 手動跑一輪：${WRAPPER}（看 $OPENCLAW_DATA_DIR/logs/incident_sentinel_cron.log）"
    echo "  2. 通道演練：python3 $OPENCLAW_BASE_DIR/helper_scripts/canary/incident_sentinel.py --probe-alert"
    echo "  3. 合成軸演練：--data-dir /tmp/sentinel_drill --dry-run（不碰真 data_dir、不發送）"
    exit 0
fi

# ----- 實際 install（僅 OPENCLAW_SENTINEL_CRON_APPLY=1 才走到）-----
( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: incident_sentinel cron entry added. Verify with: crontab -l | grep incident_sentinel"

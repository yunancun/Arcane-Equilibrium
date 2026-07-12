#!/usr/bin/env bash
# install_bybit_announcement_sentinel_cron.sh — Bybit 公告哨兵 cron idempotent installer
#   （mirror install_incident_sentinel_cron.sh 模式：Linux only / dry-run 預設 /
#     OPENCLAW_BB_SENTINEL_CRON_APPLY=1 才寫 crontab / 偵測既有條目 / 支援 --remove）。
#
# 安裝內容（單一 crontab entry）：
#   7,37 * * * * → bybit_announcement_sentinel_cron.sh
#   （30min cadence + 分鐘 offset 避整點，BB 裁決 §3 輪詢紀律）
#
# rollback = 本 script --remove（或手動 crontab -e 刪行）→ 系統回到哨兵前狀態，
# 零殘留（state json / alerts.jsonl 為 inert 資料，可留可刪）。
#
# 硬邊界：
#   - 零 credential 面：不需 OPENCLAW_SECRETS_ROOT（plain GET 公開 API，與
#     incident_sentinel installer 的差異點）；不寫 secrets；不改 PG；不觸 engine/app
#   - idempotent guard：crontab 已有 bybit_announcement_sentinel 條目 → refuse install
#   - APPLY gate 用獨立 env（OPENCLAW_BB_SENTINEL_CRON_APPLY，非復用
#     OPENCLAW_SENTINEL_CRON_APPLY）：防 operator 同 shell 裝 incident_sentinel 時
#     殘留的 APPLY=1 連帶誤裝本哨兵
#   - 路徑不硬編碼（per memory feedback_cross_platform）

#
# crontab 治理（P0-2④）：live crontab 的正本是同目錄 crontab.trade-core.template，
# 唯一被授權的 live crontab 寫入入口是 install_crontab_from_repo.sh；本檔條目的
# 任何增刪或 cadence/env 變更必須同步 template 正本，避免 render 安裝時被覆蓋。
set -euo pipefail

# ----- 平台守門：僅 Linux 跑（mirror install_incident_sentinel_cron.sh）-----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_bybit_announcement_sentinel_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/bybit_announcement_sentinel_cron.sh"
MARKER="bybit_announcement_sentinel_cron.sh"

# ----- --remove 模式：移除既有條目（同樣受 APPLY gate 保護）-----
if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no bybit_announcement_sentinel cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_BB_SENTINEL_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_BB_SENTINEL_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: bybit_announcement_sentinel cron entry. Verify with: crontab -l | grep bybit_announcement"
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
    echo "SKIP: existing bybit_announcement_sentinel cron entry detected; not installing (use --remove first)." >&2
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
_validate_cron_env_value "WRAPPER" "$WRAPPER"

# 為什麼 plain 組裝不用 printf %q：cron 不跑 full shell parser，唯一可靠路徑是
# 上面 validation reject special char（mirror install_pg_dump_cron.sh 同理由）。
ENTRY="7,37 * * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/bybit_announcement_sentinel_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule: 7,37 * * * * (every 30 minutes, offset to avoid the top of the hour)"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/bybit_announcement_sentinel.last_fire"
echo "State: $OPENCLAW_DATA_DIR/bybit_announcements_state.json"
echo "Rollback: $0 --remove (with OPENCLAW_BB_SENTINEL_CRON_APPLY=1)"

if [[ "${OPENCLAW_BB_SENTINEL_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_BB_SENTINEL_CRON_APPLY=1 to actually install."
    echo
    echo "預檢建議（apply 前）："
    echo "  1. dry-run 一輪（1 次真 API call，不發送、state 寫 scratch dir）："
    echo "     python3 $OPENCLAW_BASE_DIR/helper_scripts/canary/bybit_announcement_sentinel.py --once --dry-run --data-dir /tmp/bb_sentinel_drill"
    echo "  2. 手動跑 wrapper：${WRAPPER}（看 $OPENCLAW_DATA_DIR/logs/bybit_announcement_sentinel_cron.log）"
    echo "  3. 注意首輪 = baseline 模式（全標 seen 不告警，防首跑洪水）；第二輪起才增量告警。"
    exit 0
fi

# ----- 實際 install（僅 OPENCLAW_BB_SENTINEL_CRON_APPLY=1 才走到）-----
( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: bybit_announcement_sentinel cron entry added. Verify with: crontab -l | grep bybit_announcement"

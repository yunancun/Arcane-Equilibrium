#!/usr/bin/env bash
# install_polymarket_axis_cron.sh — Polymarket 數據軸 cron idempotent installer
#   （mirror install_incident_sentinel_cron.sh 模式：Linux only / dry-run 預設 /
#     OPENCLAW_POLYMARKET_CRON_APPLY=1 才寫 crontab / 偵測既有條目 / 支援 --remove）。
#
# 安裝內容（兩行）：
#   41 4 * * *  → polymarket_axis_cron.sh daily（04:41 UTC baseline 全量 sweep）
#   #7 * * * *  → polymarket_axis_cron.sh hourly-topn（默認「註釋停用」安裝——
#                 QC memo §3：cron 活化 = operator 決策；operator 設
#                 OPENCLAW_POLYMARKET_CRON_HOURLY=1 重裝才寫成活行）
#
# rollback = 本 script --remove（兩行一併移除）→ 系統回到安裝前狀態，零殘留
# （run dir / state 檔為 inert 研究資料，可留可刪）。
#
# 硬邊界：
#   - 不寫 secrets；不碰 PG / engine / app（本軸 R-0 紅線）
#   - idempotent guard：crontab 已有 polymarket_axis 條目 → refuse install
#   - 路徑不硬編碼（per memory feedback_cross_platform）

set -euo pipefail

# ----- 平台守門：僅 Linux 跑（mirror install_incident_sentinel_cron.sh）-----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_polymarket_axis_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/polymarket_axis_cron.sh"
MARKER="polymarket_axis_cron.sh"

# ----- --remove 模式：移除既有條目（含註釋停用行；同受 APPLY gate 保護）-----
if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no polymarket_axis cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_POLYMARKET_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_POLYMARKET_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: polymarket_axis cron entries. Verify with: crontab -l | grep polymarket_axis"
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
    echo "SKIP: existing polymarket_axis cron entry detected; not installing (use --remove first)." >&2
    crontab -l | grep "$MARKER" >&2
    exit 0
fi

# ----- env value validation：防 cron 特殊字 / 空格 / 過長 entry 解析錯亂 -----
# cron 對 `%` 解為 stdin 換行；space 拆 token 破解析；control char 直接 corrupt
# crontab；長度 > 200 通常是 ENV 污染（mirror install_incident_sentinel_cron.sh）。
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
# 上面 validation reject special char（mirror install_incident_sentinel_cron.sh）。
ENV_PREFIX="OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR}"
ENTRY_DAILY="41 4 * * * ${ENV_PREFIX} ${WRAPPER} daily >> ${OPENCLAW_DATA_DIR}/logs/polymarket_axis_cron.cron.log 2>&1"
ENTRY_HOURLY_ACTIVE="7 * * * * ${ENV_PREFIX} ${WRAPPER} hourly-topn >> ${OPENCLAW_DATA_DIR}/logs/polymarket_axis_cron.cron.log 2>&1"
# hourly 默認以註釋行安裝（crontab 合法註釋）：保留完整 entry 供 operator 一鍵
# 取消註釋活化，亦讓 --remove 的 MARKER grep 能一併清掉。
if [[ "${OPENCLAW_POLYMARKET_CRON_HOURLY:-0}" == "1" ]]; then
    ENTRY_HOURLY="$ENTRY_HOURLY_ACTIVE"
    HOURLY_STATE="ACTIVE"
else
    ENTRY_HOURLY="#${ENTRY_HOURLY_ACTIVE}"
    HOURLY_STATE="DISABLED (commented; operator 活化：取消註釋或 OPENCLAW_POLYMARKET_CRON_HOURLY=1 重裝)"
fi

echo "------- proposed crontab entries -------"
echo "$ENTRY_DAILY"
echo "$ENTRY_HOURLY"
echo "----------------------------------------"
echo "Daily:  41 4 * * * UTC（與 residual producer 03:17 錯峰）"
echo "Hourly: $HOURLY_STATE"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/polymarket_axis_daily.last_fire"
echo "Artifacts: $OPENCLAW_DATA_DIR/polymarket_axis_runs/<run_id>/"
echo "Rollback: $0 --remove (with OPENCLAW_POLYMARKET_CRON_APPLY=1)"

if [[ "${OPENCLAW_POLYMARKET_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_POLYMARKET_CRON_APPLY=1 to actually install."
    echo
    echo "預檢建議（apply 前）："
    echo "  1. 手動跑一輪：${WRAPPER} daily（看 $OPENCLAW_DATA_DIR/logs/polymarket_axis_cron.log）"
    echo "  2. 驗 artifact：ls $OPENCLAW_DATA_DIR/polymarket_axis_runs/ + manifest.json sha256 index"
    exit 0
fi

# ----- 實際 install（僅 OPENCLAW_POLYMARKET_CRON_APPLY=1 才走到）-----
( crontab -l 2>/dev/null; echo "$ENTRY_DAILY"; echo "$ENTRY_HOURLY" ) | crontab -
echo "INSTALLED: polymarket_axis cron entries added. Verify with: crontab -l | grep polymarket_axis"

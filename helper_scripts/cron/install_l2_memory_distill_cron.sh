#!/usr/bin/env bash
# install_l2_memory_distill_cron.sh — L2 記憶蒸餾 cron idempotent installer
#   （mirror install_incident_sentinel_cron.sh 模式：Linux only / dry-run 預設 /
#     OPENCLAW_L2_MEMORY_CRON_APPLY=1 才寫 crontab / 偵測既有條目 / 支援 --remove）。
#
# 安裝內容（單一 crontab entry）：
#   23 5 * * * → l2_memory_distill_cron.sh（daily 蒸餾，05:23 UTC 避撞既有 cron 表）
#
# 安裝後行為中性：cron entry 內 OPENCLAW_L2_MEMORY_PIPELINE 默認 0 ⇒ 每日啟動
# 即 exit 0（一行 log + heartbeat），inert（PA spec §10）。啟用 = 帶
# OPENCLAW_L2_MEMORY_PIPELINE=1 重裝（--remove 後 re-install）或手動 crontab -e 改值。
#
# rollback = 本 script --remove（+ OPENCLAW_L2_MEMORY_CRON_APPLY=1）→ 回到安裝前
# 狀態；游標/log 為 inert 資料可留可刪；V139 表 additive 不需回滾（spec §10）。
#
# 硬邊界：
#   - 不寫 secrets；不改 PG schema；不觸 engine/app
#   - idempotent guard：crontab 已有 l2_memory_distill 條目 → refuse install
#   - 路徑不硬編碼（per memory feedback_cross_platform）

#
# crontab 治理（P0-2④）：live crontab 的正本是同目錄 crontab.trade-core.template，
# 唯一被授權的 live crontab 寫入入口是 install_crontab_from_repo.sh；本檔條目的
# 任何增刪或 cadence/env 變更必須同步 template 正本，避免 render 安裝時被覆蓋。
set -euo pipefail

# ----- 平台守門：僅 Linux 跑（mirror install_incident_sentinel_cron.sh）-----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: install_l2_memory_distill_cron.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑；Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
OPENCLAW_SECRETS_ROOT="${OPENCLAW_SECRETS_ROOT:-$HOME/BybitOpenClaw/secrets}"
# pipeline flag 進 cron entry（默認 0=inert）；只接受 0/1，防 env 污染進 crontab。
L2_MEMORY_PIPELINE_FLAG="${OPENCLAW_L2_MEMORY_PIPELINE:-0}"

WRAPPER="$OPENCLAW_BASE_DIR/helper_scripts/cron/l2_memory_distill_cron.sh"
MARKER="l2_memory_distill_cron.sh"

# ----- --remove 模式：移除既有條目（同樣受 APPLY gate 保護）-----
if [[ "${1:-}" == "--remove" ]]; then
    if ! crontab -l 2>/dev/null | grep -q "$MARKER"; then
        echo "NO-OP: no l2_memory_distill cron entry found."
        exit 0
    fi
    echo "------- entries to remove -------"
    crontab -l | grep "$MARKER"
    echo "---------------------------------"
    if [[ "${OPENCLAW_L2_MEMORY_CRON_APPLY:-0}" != "1" ]]; then
        echo "DRY-RUN: not modifying crontab. Set OPENCLAW_L2_MEMORY_CRON_APPLY=1 to actually remove."
        exit 0
    fi
    crontab -l | grep -v "$MARKER" | crontab -
    echo "REMOVED: l2_memory_distill cron entry. Verify with: crontab -l | grep l2_memory_distill"
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
    echo "SKIP: existing l2_memory_distill cron entry detected; not installing (use --remove first)." >&2
    crontab -l | grep "$MARKER" >&2
    exit 0
fi

# ----- env value validation：防 cron 特殊字 / 空格 / 過長 entry 解析錯亂 -----
# cron 對 `%` 解為 stdin 換行；space 拆 token 破解析；control char 直接 corrupt
# crontab；長度 > 200 通常是 ENV 污染。任一不合即 abort（mirror install_incident_sentinel）。
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

# flag 值只容許 0/1：crontab 是持久面，任何其他值一律 abort（fail-closed）。
if [[ "$L2_MEMORY_PIPELINE_FLAG" != "0" && "$L2_MEMORY_PIPELINE_FLAG" != "1" ]]; then
    echo "ERROR: OPENCLAW_L2_MEMORY_PIPELINE must be 0 or 1 (got: ${L2_MEMORY_PIPELINE_FLAG})" >&2
    exit 6
fi

# 為什麼 plain 組裝不用 printf %q：cron 不跑 full shell parser，唯一可靠路徑是
# 上面 validation reject special char（mirror install_incident_sentinel_cron.sh 同理由）。
ENTRY="23 5 * * * OPENCLAW_BASE_DIR=${OPENCLAW_BASE_DIR} OPENCLAW_DATA_DIR=${OPENCLAW_DATA_DIR} OPENCLAW_SECRETS_ROOT=${OPENCLAW_SECRETS_ROOT} OPENCLAW_L2_MEMORY_PIPELINE=${L2_MEMORY_PIPELINE_FLAG} ${WRAPPER} >> ${OPENCLAW_DATA_DIR}/logs/l2_memory_distill_cron.cron.log 2>&1"

echo "------- proposed crontab entry -------"
echo "$ENTRY"
echo "--------------------------------------"
echo "Schedule: 23 5 * * * (daily 05:23 UTC; 避撞 03:00/03:17/04:00/04:41/06:00/09:00 既有槽)"
echo "Pipeline flag: OPENCLAW_L2_MEMORY_PIPELINE=${L2_MEMORY_PIPELINE_FLAG} (0=inert：每日 exit 0 一行 log + heartbeat)"
echo "Heartbeat: $OPENCLAW_DATA_DIR/cron_heartbeat/l2_memory_distill.last_fire"
echo "Cursor:    $OPENCLAW_DATA_DIR/cron_state/l2_memory_distill_cursor.json"
echo "Rollback:  $0 --remove (with OPENCLAW_L2_MEMORY_CRON_APPLY=1)"

if [[ "${OPENCLAW_L2_MEMORY_CRON_APPLY:-0}" != "1" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab."
    echo "Set OPENCLAW_L2_MEMORY_CRON_APPLY=1 to actually install."
    echo
    echo "預檢建議（apply 前）："
    echo "  1. 手動跑一輪：${WRAPPER}（看 $OPENCLAW_DATA_DIR/logs/l2_memory_distill_cron.log，flag=0 應一行 inert log）"
    echo "  2. V139 已 apply 後才考慮 OPENCLAW_L2_MEMORY_PIPELINE=1（否則 pipeline 寫入無表可落）"
    exit 0
fi

# ----- 實際 install（僅 OPENCLAW_L2_MEMORY_CRON_APPLY=1 才走到）-----
( crontab -l 2>/dev/null; echo "$ENTRY" ) | crontab -
echo "INSTALLED: l2_memory_distill cron entry added. Verify with: crontab -l | grep l2_memory_distill"

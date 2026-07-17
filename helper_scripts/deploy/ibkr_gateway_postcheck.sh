#!/usr/bin/env bash
# ============================================================================
# ibkr_gateway_postcheck.sh — IB Gateway dormant 簽名驗證(W9a source-ready)
# ----------------------------------------------------------------------------
# MODULE_NOTE
# 模塊用途:唯讀驗證 IB Gateway 處於 dormant 姿態並輸出 JSON 報告——
#   ① 零 Gateway 進程(ibgateway / $HOME/Jts 下 java);
#   ② unit 姿態(ibkr-gateway.service:masked / disabled / absent 可接受,
#      enabled/active = FAIL;--require-unit-masked 時只認 masked);
#   ③ 4001/4002/7496/7497 四埠零 listener(IB 官方端口語義:Gateway
#      live=4001 / paper=4002,TWS live=7496 / paper=7497;全屬 denylist
#      驗證面,本 lane 配置面只允許 4002 且僅 EA2+ 才可能出現 listener)。
# 用途:安裝腳本的 before/after 快照(RM-1)+ dormant 簽名遷移證據
#   (IBKR_TODO.md §5 W9a DoD:安裝後「~/Jts 不存在」簽名失效,新簽名 =
#   ~/Jts 存在但零進程 + unit masked + 四埠零 listener);OPS 亦可獨立跑
#   作日常 dormant 復核。
# 依賴:pgrep / systemctl --user / ss(缺 ss 退 netstat;兩者皆缺 = FAIL,
#   fail-closed:驗不到 listener 面不得謊稱 dormant)。
# 硬邊界:唯讀(唯一寫入=--output 報告檔);不 start/stop/enable/mask 任何
#   unit、不連 broker、不碰 PG/engine/auth/risk。
# exit code:0 = dormant 簽名成立;1 = 簽名不成立(報告內列 fail 項);
#   2 = 平台守門(非 Linux)。
# ============================================================================

set -euo pipefail

# ----- 平台守門:listener/進程/unit 檢查只在 Linux runtime 有意義 -----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: ibkr_gateway_postcheck.sh requires Linux runtime (current: $(uname -s))." >&2
    exit 2
fi

REQUIRE_UNIT_MASKED=0
OUTPUT=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --require-unit-masked) REQUIRE_UNIT_MASKED=1; shift ;;
        --output)
            [[ $# -ge 2 ]] || { echo "ERROR: --output 需要檔案參數。" >&2; exit 1; }
            OUTPUT="$2"; shift 2 ;;
        *) echo "ERROR: unknown argument: $1(支援 --require-unit-masked / --output <file>)" >&2; exit 1 ;;
    esac
done

INSTALL_DIR="${IBKR_GATEWAY_INSTALL_DIR:-$HOME/Jts}"
UNIT_NAME="ibkr-gateway.service"
# IB 官方端口全家桶 denylist(live 4001 歸 EA7,paper 4002 歸 EA2+;現階段四埠
# 任何 listener 都是 dormant 破功)。
PORTS=(4001 4002 7496 7497)

FAILS=()

# ----- ① 進程面:零 Gateway 進程 -----
# pgrep -c 無匹配時 exit 1,|| true 吞掉只留計數;-f 全命令行匹配。
# 兩鏡頭:程式名 ibgateway + 安裝目錄路徑(Jts 下 java 啟動命令行必含該路徑;
# 不裸匹配 "Jts" 避免誤傷無關進程)。
PROC_IBGATEWAY="$(pgrep -c -f 'ibgateway' || true)"
PROC_INSTALL_DIR="$(pgrep -c -f "$INSTALL_DIR/" || true)"
PROC_IBGATEWAY="${PROC_IBGATEWAY:-0}"
PROC_INSTALL_DIR="${PROC_INSTALL_DIR:-0}"
if [[ "$PROC_IBGATEWAY" -gt 0 || "$PROC_INSTALL_DIR" -gt 0 ]]; then
    FAILS+=("gateway_process_running(ibgateway=$PROC_IBGATEWAY, install_dir=$PROC_INSTALL_DIR)")
fi

# ----- ② unit 姿態 -----
# is-enabled 輸出:masked/disabled/enabled/…;unit 不存在時非零退出且 stderr 報錯。
UNIT_STATE="$(systemctl --user is-enabled "$UNIT_NAME" 2>/dev/null || true)"
if [[ -z "$UNIT_STATE" ]]; then
    UNIT_STATE="absent"
fi
UNIT_ACTIVE="$(systemctl --user is-active "$UNIT_NAME" 2>/dev/null || true)"
if [[ -z "$UNIT_ACTIVE" ]]; then
    UNIT_ACTIVE="inactive"
fi
if [[ "$UNIT_ACTIVE" == "active" || "$UNIT_ACTIVE" == "activating" ]]; then
    FAILS+=("unit_active($UNIT_ACTIVE)")
fi
if [[ "$REQUIRE_UNIT_MASKED" -eq 1 ]]; then
    # 安裝後鏡頭:只認 masked(install 契約=cp unit 後立即 mask)。
    if [[ "$UNIT_STATE" != "masked" ]]; then
        FAILS+=("unit_not_masked(state=$UNIT_STATE)")
    fi
else
    # 獨立/before 鏡頭:masked/disabled/absent 都是 dormant;enabled 即破功
    # (enable 屬 EA2,現階段出現=治理外行為)。
    case "$UNIT_STATE" in
        masked|disabled|absent|static) : ;;
        *) FAILS+=("unit_state_not_dormant(state=$UNIT_STATE)") ;;
    esac
fi

# ----- ③ listener 面:四埠零 listener -----
# fail-closed:ss/netstat 皆缺時不得謊稱零 listener → FAIL。
PORT_REGEX=':(4001|4002|7496|7497)$'
LISTENER_LINES=""
LISTENER_TOOL=""
if command -v ss >/dev/null 2>&1; then
    LISTENER_TOOL="ss"
    LISTENER_LINES="$(ss -Hltn 2>/dev/null | awk '{print $4}' | grep -E "$PORT_REGEX" || true)"
elif command -v netstat >/dev/null 2>&1; then
    LISTENER_TOOL="netstat"
    LISTENER_LINES="$(netstat -ltn 2>/dev/null | awk '{print $4}' | grep -E "$PORT_REGEX" || true)"
else
    FAILS+=("listener_probe_unavailable(no ss/netstat)")
fi
LISTENER_COUNT=0
if [[ -n "$LISTENER_LINES" ]]; then
    LISTENER_COUNT="$(printf '%s\n' "$LISTENER_LINES" | grep -c . || true)"
    FAILS+=("port_listener_present(count=$LISTENER_COUNT: $(printf '%s' "$LISTENER_LINES" | tr '\n' ' '))")
fi

JTS_PRESENT=false
[[ -d "$INSTALL_DIR" ]] && JTS_PRESENT=true

VERDICT="PASS"
[[ ${#FAILS[@]} -gt 0 ]] && VERDICT="FAIL"

# fail 清單組 JSON 陣列(元素受控字元,無需完整轉義;引號不會出現在 FAILS 項)。
FAILS_JSON=""
for f in ${FAILS[@]+"${FAILS[@]}"}; do
    [[ -n "$FAILS_JSON" ]] && FAILS_JSON+=", "
    FAILS_JSON+="\"${f//\"/\\\"}\""
done

REPORT="$(cat <<EOF
{
  "schema": "ibkr_gateway_dormant_postcheck_v1",
  "utc": "$(date -u +%Y%m%dT%H%M%SZ)",
  "host": "$(hostname -s 2>/dev/null || hostname)",
  "verdict": "$VERDICT",
  "require_unit_masked": $([[ "$REQUIRE_UNIT_MASKED" -eq 1 ]] && echo true || echo false),
  "install_dir": "$INSTALL_DIR",
  "jts_present": $JTS_PRESENT,
  "gateway_process_count_ibgateway": $PROC_IBGATEWAY,
  "gateway_process_count_install_dir": $PROC_INSTALL_DIR,
  "unit_name": "$UNIT_NAME",
  "unit_enabled_state": "$UNIT_STATE",
  "unit_active_state": "$UNIT_ACTIVE",
  "listener_tool": "${LISTENER_TOOL:-none}",
  "denylist_ports": "4001 4002 7496 7497",
  "denylist_listener_count": $LISTENER_COUNT,
  "fails": [$FAILS_JSON]
}
EOF
)"

if [[ -n "$OUTPUT" ]]; then
    mkdir -p "$(dirname "$OUTPUT")"
    printf '%s\n' "$REPORT" > "$OUTPUT"
fi
printf '%s\n' "$REPORT"

if [[ "$VERDICT" != "PASS" ]]; then
    exit 1
fi

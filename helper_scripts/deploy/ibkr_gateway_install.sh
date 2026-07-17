#!/usr/bin/env bash
# ============================================================================
# ibkr_gateway_install.sh — IB Gateway 安裝腳本(W9a source-ready 交付)
# ----------------------------------------------------------------------------
# MODULE_NOTE
# 模塊用途:從 IBKR 官方來源下載 IB Gateway stable standalone Linux x64
#   installer,經「TOFU sha256 + 官方 metadata 三元組漂移偵測」釘定校驗後
#   靜默安裝到 ~/Jts,並安裝(但絕不 enable)配套 user unit 模板,install 後
#   立即 `systemctl --user mask ibkr-gateway.service`。
# 主要流程:守門(host/args)→ metadata 漂移偵測(HEAD 三元組 + version.json)
#   → RM-1 before 快照 → 兩段式 manifest(applied:false)→ 下載 + sha256
#   pin 校驗(首窗 TOFU 落 pin)→ 靜默安裝 → unit 安裝+mask → postcheck
#   (dormant 簽名)→ 全綠才改寫 applied:true。
# 依賴:同目錄 ibkr-gateway.service / ibkr-gateway-restart.service /
#   ibkr-gateway-restart.timer / ibkr_gateway_postcheck.sh。
#
# 接觸語義定界(IBKR_TODO.md §5 W9a):「接觸」= AMD-2026-07-11-01 語義的
#   broker API/session/資料/訂單效果;本腳本從官方來源下載 installer 屬
#   **供應鏈動作**,僅限 operator 批准窗內執行(pin-by-reference,承 DOC-06
#   RM-4)。安裝不產生任何接觸:**從不啟動 Gateway、從不登入、從不 enable
#   unit**;enable/登入/socket 全屬 EA2+,live 4001 配置屬 EA7,均在範圍外。
#
# 供應鏈釘定模型(IB 現勘 2026-07-17 定案):
#   - channel 固定 stable(IB 裁決;官方語義=低頻更新+不自動更新,與
#     envelope-gated 活化模型對齊)。latest channel 存在
#     (…/latest-standalone/ibgateway-latest-standalone-linux-x64.sh)但僅
#     operator 顯式裁決才換用,本腳本不提供 channel 參數。
#   - 官方**無 checksum 發布 channel(CONFIRMED-ABSENT,IB 現勘 2026-07-17)**
#     → 無法 pin 官方公布 sha256。改用 TOFU(trust-on-first-use):首窗下載
#     後本地 sha256 落 pin 檔+receipt;之後每次執行先 HEAD 比對官方 metadata
#     三元組(Content-Length / Last-Modified / ETag 輔助)+ GET 同目錄
#     version.json(buildVersion/buildDateTime),任一漂移 = fail-closed 退
#     operator 重批(IB 發了新版,舊 TOFU pin 必須作廢重釘)。
#   - ETag 前 32-hex 疑似 MD5 只作輔助信號記錄於 receipt,不替代 sha256 gate。
#
# 三重防護(全部 fail-closed):
#   ① 主機守門:非 trade-core(IBKR_GATEWAY_EXPECTED_HOST)拒跑;非 Linux 拒跑。
#   ② 顯式批准:必須帶 --operator-approved 且 --approval-record <dir>
#      (RM-1:before/after 快照+兩段式 manifest 落該目錄);缺一即拒。
#   ③ postcheck:安裝完成後自動驗證「零 Gateway 進程 + unit masked +
#      4001/4002/7496/7497 零 listener」並輸出 postcheck 報告——這是
#      dormant 簽名遷移證據(安裝後「~/Jts 不存在」簽名失效,新簽名 =
#      ~/Jts 存在但零進程+unit masked+四埠零 listener)。
#
# 端口契約(IB 官方原文:Gateway live=4001 / paper=4002;TWS live=7496 /
#   paper=7497):本 lane 配置面只允許出現 4002(paper);4001/7496/7497 屬
#   denylist——僅在 postcheck 零 listener 驗證與注釋中出現,任何配置檔/unit/
#   env 不得引入,live 4001 歸 EA7。
#
# 執行者:operator 親手,或 OPS agent 於批准窗內代跑(批准紀錄按 RM-1 落檔)。
# exit code:0 成功/dry-run;2 平台或主機守門;3 參數;4 metadata 漂移或
#   pin 檔壞;5 下載/HEAD/version.json 取得失敗;6 sha256 與 pin 不符;
#   7 installer 執行失敗;8 unit 安裝失敗;9 postcheck 失敗(manifest 維持
#   applied:false)。
#
# 硬邊界:
#   - 絕不 systemctl start / enable / unmask;絕不寫入任何登入材料。
#   - 不連 broker API、不開任何 socket、不碰 PG/engine/auth/risk/Cost Gate。
#   - 路徑走 env($HOME / IBKR_GATEWAY_INSTALL_DIR),不硬編碼 runtime 機器路徑。
# ============================================================================

set -euo pipefail

# ----- pin-by-reference 配置(channel 固定 stable,IB 現勘 2026-07-17) -----
IBKR_GATEWAY_INSTALLER_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/ibgateway-stable-standalone-linux-x64.sh"
IBKR_GATEWAY_VERSION_JSON_URL="https://download2.interactivebrokers.com/installers/ibgateway/stable-standalone/version.json"

# 官方 metadata 基線常數(IB 現勘 2026-07-17 HEAD/GET 實測;stable channel):
#   buildVersion   = 10.45.1h
#   buildDateTime  = 20260624(prefix 比對:version.json 可能帶時分)
#   Content-Length = 335674728
#   Last-Modified  = 2026-06-25(HTTP 頭為 RFC 1123 格式,比對正規化後日期)
# 任一與線上現值不符 = IB 已發新版 → fail-closed 退 operator 重批准+重釘基線。
# env 覆寫僅供 operator 於新批准窗內重釘;窗後應回填本常數(follow-up commit)。
BASELINE_BUILD_VERSION="${IBKR_GATEWAY_BASELINE_BUILD_VERSION:-10.45.1h}"
BASELINE_BUILD_DATETIME_PREFIX="${IBKR_GATEWAY_BASELINE_BUILD_DATETIME_PREFIX:-20260624}"
BASELINE_CONTENT_LENGTH="${IBKR_GATEWAY_BASELINE_CONTENT_LENGTH:-335674728}"
BASELINE_LAST_MODIFIED_DATE="${IBKR_GATEWAY_BASELINE_LAST_MODIFIED_DATE:-2026-06-25}"

# TOFU sha256 pin 檔:首窗下載後寫入;之後每次 apply 必比對。壞 JSON/空值=拒。
PIN_FILE="${IBKR_GATEWAY_PIN_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/ibkr-gateway/installer_pin.json}"

# ----- 安裝面配置 -----
IBKR_GATEWAY_INSTALL_DIR="${IBKR_GATEWAY_INSTALL_DIR:-$HOME/Jts}"
# 主機守門正本值;覆寫僅供測試(tmp 目標),真安裝面仍被 ②③ 擋住。
IBKR_GATEWAY_EXPECTED_HOST="${IBKR_GATEWAY_EXPECTED_HOST:-trade-core}"
SYSTEMD_USER_DIR="${IBKR_GATEWAY_SYSTEMD_USER_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_FILES=(ibkr-gateway.service ibkr-gateway-restart.service ibkr-gateway-restart.timer)
POSTCHECK="$SCRIPT_DIR/ibkr_gateway_postcheck.sh"

# ----- ① 平台+主機守門:僅 Linux trade-core 跑 -----
if [[ "$(uname -s)" != "Linux" ]]; then
    echo "ERROR: ibkr_gateway_install.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本安裝腳本必在 Linux runtime host (trade-core) 於 operator 批准窗內跑。" >&2
    exit 2
fi
CURRENT_HOST="$(hostname -s 2>/dev/null || hostname)"
if [[ "$CURRENT_HOST" != "$IBKR_GATEWAY_EXPECTED_HOST" ]]; then
    echo "ERROR: host guard tripped — current host '$CURRENT_HOST' != expected '$IBKR_GATEWAY_EXPECTED_HOST'." >&2
    echo "       非 trade-core 主機拒跑(供應鏈動作只允許落在指定 runtime 機)。" >&2
    exit 2
fi

# ----- ② 參數:預設 dry-run;真安裝必須 --operator-approved + --approval-record -----
MODE="dry-run"
OPERATOR_APPROVED=0
APPROVAL_RECORD_DIR=""
usage() {
    cat >&2 <<'EOF'
用法:
  ibkr_gateway_install.sh --dry-run
      只輸出安裝計畫(URL/基線/pin 狀態/目標路徑/unit 清單),零下載零寫入。
  ibkr_gateway_install.sh --operator-approved --approval-record <dir>
      operator 批准窗內真安裝;<dir> 為批准紀錄目錄(RM-1 before/after
      快照 + 兩段式 manifest 落此)。兩參數缺一即拒。
EOF
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) MODE="dry-run"; shift ;;
        --operator-approved) OPERATOR_APPROVED=1; MODE="apply"; shift ;;
        --approval-record)
            [[ $# -ge 2 ]] || { echo "ERROR: --approval-record 需要目錄參數。" >&2; usage; exit 3; }
            APPROVAL_RECORD_DIR="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage; exit 3 ;;
    esac
done
if [[ "$MODE" == "apply" ]]; then
    if [[ "$OPERATOR_APPROVED" -ne 1 || -z "$APPROVAL_RECORD_DIR" ]]; then
        echo "ERROR: 真安裝必須同時帶 --operator-approved 與 --approval-record <dir>(RM-1)。" >&2
        usage
        exit 3
    fi
fi

_sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}
# JSON 字串轉義(mirror install_logrotate_from_repo.sh:自然語言/路徑不得毒化 receipt;
# 反斜線必最先轉義)。
_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    printf '%s' "$s"
}
# 從簡單扁平 JSON 抽字串值(pin 檔/version.json 專用;非通用 parser,鍵名受控)。
_json_field() {
    # $1=file $2=key → stdout 值(找不到輸出空)
    grep -o "\"$2\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" "$1" 2>/dev/null \
        | head -n 1 | sed 's/.*:[[:space:]]*"\(.*\)"/\1/' || true
}

# ----- TOFU pin 現況(dry-run 也展示) -----
PIN_SHA256=""
PIN_STATE="absent(TOFU 首窗)"
if [[ -f "$PIN_FILE" ]]; then
    PIN_SHA256="$(_json_field "$PIN_FILE" "sha256")"
    if [[ "$PIN_SHA256" =~ ^[0-9a-fA-F]{64}$ ]]; then
        PIN_STATE="pinned(${PIN_SHA256:0:12}…)"
    else
        echo "ERROR: pin 檔存在但 sha256 欄位壞/缺:$PIN_FILE" >&2
        echo "       pin 檔只能由本腳本首窗 TOFU 寫入;壞檔=治理外改動,拒跑退 operator。" >&2
        exit 4
    fi
fi

echo "------- IB Gateway install plan -------"
echo "installer URL  : $IBKR_GATEWAY_INSTALLER_URL"
echo "version.json   : $IBKR_GATEWAY_VERSION_JSON_URL"
echo "baseline       : buildVersion=$BASELINE_BUILD_VERSION buildDateTime~=$BASELINE_BUILD_DATETIME_PREFIX"
echo "                 Content-Length=$BASELINE_CONTENT_LENGTH Last-Modified=$BASELINE_LAST_MODIFIED_DATE"
echo "sha256 pin     : $PIN_STATE ($PIN_FILE)"
echo "install dir    : $IBKR_GATEWAY_INSTALL_DIR"
echo "systemd user   : $SYSTEMD_USER_DIR (${UNIT_FILES[*]})"
echo "unit posture   : install 後 mask ibkr-gateway.service;絕不 enable/start"
echo "port contract  : 配置面僅 4002(paper);4001/7496/7497 denylist(postcheck 驗零 listener)"
echo "mode           : $MODE"
echo "----------------------------------------"

if [[ "$MODE" != "apply" ]]; then
    echo
    echo "DRY-RUN: 零下載零寫入。operator 批准窗內以 --operator-approved --approval-record <dir> 真跑。"
    exit 0
fi

# ----- metadata 三元組漂移偵測(下載前;任一漂移 fail-closed 退 operator) -----
HEAD_OUT="$(curl -fsSI --proto '=https' --tlsv1.2 "$IBKR_GATEWAY_INSTALLER_URL")" || {
    echo "ERROR: HEAD 取 metadata 失敗:$IBKR_GATEWAY_INSTALLER_URL" >&2
    exit 5
}
# HTTP 頭鍵大小寫不敏感;\r 必剝(curl 原樣保留 CRLF)。頭缺時輸出空(|| true
# 吞 pipefail 下 grep 無匹配的非零,讓「absent」流進漂移偵測而非 set -e 硬死)。
_head_field() {
    printf '%s\n' "$HEAD_OUT" | tr -d '\r' | grep -i "^$1:" | head -n 1 | sed "s/^[^:]*:[[:space:]]*//" || true
}
GOT_CONTENT_LENGTH="$(_head_field 'Content-Length')"
GOT_LAST_MODIFIED="$(_head_field 'Last-Modified')"
GOT_ETAG="$(_head_field 'ETag')"

VERSION_JSON_TMP="$(mktemp)"
trap 'rm -f "$VERSION_JSON_TMP"' EXIT
curl -fsSL --proto '=https' --tlsv1.2 -o "$VERSION_JSON_TMP" "$IBKR_GATEWAY_VERSION_JSON_URL" || {
    echo "ERROR: version.json 取得失敗:$IBKR_GATEWAY_VERSION_JSON_URL" >&2
    exit 5
}
GOT_BUILD_VERSION="$(_json_field "$VERSION_JSON_TMP" "buildVersion")"
GOT_BUILD_DATETIME="$(_json_field "$VERSION_JSON_TMP" "buildDateTime")"

DRIFT=()
if [[ "$GOT_CONTENT_LENGTH" != "$BASELINE_CONTENT_LENGTH" ]]; then
    DRIFT+=("Content-Length: got=${GOT_CONTENT_LENGTH:-absent} baseline=$BASELINE_CONTENT_LENGTH")
fi
# Last-Modified 為 RFC 1123(如 "Thu, 25 Jun 2026 08:00:00 GMT");GNU date 正規化
# 成 %Y-%m-%d 再比。parse 失敗=fail-closed(供應鏈 gate 不容含糊)。
GOT_LM_DATE="$(date -u -d "$GOT_LAST_MODIFIED" +%Y-%m-%d 2>/dev/null || true)"
if [[ -z "$GOT_LM_DATE" || "$GOT_LM_DATE" != "$BASELINE_LAST_MODIFIED_DATE" ]]; then
    DRIFT+=("Last-Modified: got=${GOT_LAST_MODIFIED:-absent}(→${GOT_LM_DATE:-unparsable}) baseline=$BASELINE_LAST_MODIFIED_DATE")
fi
if [[ "$GOT_BUILD_VERSION" != "$BASELINE_BUILD_VERSION" ]]; then
    DRIFT+=("buildVersion: got=${GOT_BUILD_VERSION:-absent} baseline=$BASELINE_BUILD_VERSION")
fi
if [[ "${GOT_BUILD_DATETIME:0:${#BASELINE_BUILD_DATETIME_PREFIX}}" != "$BASELINE_BUILD_DATETIME_PREFIX" ]]; then
    DRIFT+=("buildDateTime: got=${GOT_BUILD_DATETIME:-absent} baseline-prefix=$BASELINE_BUILD_DATETIME_PREFIX")
fi
if [[ ${#DRIFT[@]} -gt 0 ]]; then
    echo "ERROR: 官方 metadata 漂移偵測命中(IB 疑已發新 stable 版)——fail-closed 拒安裝:" >&2
    printf '       %s\n' "${DRIFT[@]}" >&2
    echo "       請 operator 重開批准窗:核對官方 channel 後以 IBKR_GATEWAY_BASELINE_* env" >&2
    echo "       重釘基線(舊 TOFU pin 同步作廢:刪 $PIN_FILE 重 TOFU),窗後回填腳本常數。" >&2
    exit 4
fi
# ETag 僅輔助信號(前 32-hex 疑似 MD5,IB 未文檔化)——記錄進 receipt,不作 gate。

# ----- RM-1 批准紀錄目錄 + before 快照 -----
mkdir -p "$APPROVAL_RECORD_DIR"
UTC_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ACTOR="${IBKR_GATEWAY_ACTOR:-${USER:-unknown}}"
REASON="${IBKR_GATEWAY_REASON:-unspecified}"

# before 快照:安裝前 dormant 簽名(unit 尚未安裝,允許 absent;fail-loud 若已有活信號)。
if ! bash "$POSTCHECK" --output "$APPROVAL_RECORD_DIR/before.postcheck.json"; then
    echo "ERROR: before 快照發現活信號(進程/listener/unit 非 dormant)——拒絕安裝。" >&2
    echo "       詳見 $APPROVAL_RECORD_DIR/before.postcheck.json;請先排查再開窗。" >&2
    exit 9
fi

# ----- 兩段式 manifest:先落 applied:false;postcheck 全綠才改寫 applied:true -----
MANIFEST="$APPROVAL_RECORD_DIR/manifest.json"
_write_manifest() {
    # 參數:$1=applied(true/false) $2=installer_sha256(下載後) $3=applied_utc(僅 true)
    local applied="$1" got_sha="${2:-}" applied_utc="${3:-}"
    local tail_fields=""
    if [[ "$applied" == "true" ]]; then
        tail_fields="$(printf ',\n  "applied_utc": "%s"' "$applied_utc")"
    fi
    cat > "$MANIFEST" <<EOF
{
  "utc": "$UTC_STAMP",
  "applied": $applied,
  "actor": "$(_json_escape "$ACTOR")",
  "reason": "$(_json_escape "$REASON")",
  "host": "$(_json_escape "$CURRENT_HOST")",
  "installer_url": "$(_json_escape "$IBKR_GATEWAY_INSTALLER_URL")",
  "build_version": "$(_json_escape "$GOT_BUILD_VERSION")",
  "build_datetime": "$(_json_escape "$GOT_BUILD_DATETIME")",
  "content_length": "$(_json_escape "$GOT_CONTENT_LENGTH")",
  "last_modified": "$(_json_escape "$GOT_LAST_MODIFIED")",
  "etag_auxiliary_only": "$(_json_escape "$GOT_ETAG")",
  "pin_state_at_start": "$(_json_escape "$PIN_STATE")",
  "downloaded_sha256": "$(_json_escape "$got_sha")",
  "install_dir": "$(_json_escape "$IBKR_GATEWAY_INSTALL_DIR")",
  "systemd_user_dir": "$(_json_escape "$SYSTEMD_USER_DIR")",
  "unit_files": "$(_json_escape "${UNIT_FILES[*]}")",
  "before_snapshot": "before.postcheck.json",
  "after_snapshot": "after.postcheck.json"$tail_fields
}
EOF
}
_write_manifest false

# ----- 下載 + sha256 pin 校驗(pinned 比對;首窗 TOFU 落 pin) -----
INSTALLER_FILE="$APPROVAL_RECORD_DIR/ibgateway-stable-standalone-linux-x64.sh"
TMP_DL="$INSTALLER_FILE.part"
trap 'rm -f "$TMP_DL" "$VERSION_JSON_TMP"' EXIT
# --proto '=https' + --tlsv1.2:供應鏈下載強制 TLS,拒任何降級/重導向出 https。
if ! curl -fSL --proto '=https' --tlsv1.2 -o "$TMP_DL" "$IBKR_GATEWAY_INSTALLER_URL"; then
    echo "ERROR: installer 下載失敗:$IBKR_GATEWAY_INSTALLER_URL" >&2
    exit 5
fi
GOT_SHA256="$(_sha256_file "$TMP_DL")"
if [[ -n "$PIN_SHA256" ]]; then
    if [[ "${GOT_SHA256,,}" != "${PIN_SHA256,,}" ]]; then
        rm -f "$TMP_DL"
        echo "ERROR: sha256 與 TOFU pin 不符 — got $GOT_SHA256, pinned $PIN_SHA256。" >&2
        echo "       metadata 三元組未漂移但位元組變了=強烈供應鏈警訊;下載物已刪除,退 operator 調查。" >&2
        exit 6
    fi
else
    # TOFU 首窗:operator 批准在場(② 已 gate),本地 sha256 + 三元組 + version.json
    # 全量落 pin 檔;之後任何一次重跑都以此 pin 為準。
    mkdir -p "$(dirname "$PIN_FILE")"
    cat > "$PIN_FILE" <<EOF
{
  "pinned_utc": "$UTC_STAMP",
  "tofu_note": "官方無 checksum channel(IB 現勘 2026-07-17 CONFIRMED-ABSENT);本 pin 為首窗 TOFU 本地 sha256",
  "installer_url": "$(_json_escape "$IBKR_GATEWAY_INSTALLER_URL")",
  "sha256": "$GOT_SHA256",
  "build_version": "$(_json_escape "$GOT_BUILD_VERSION")",
  "build_datetime": "$(_json_escape "$GOT_BUILD_DATETIME")",
  "content_length": "$(_json_escape "$GOT_CONTENT_LENGTH")",
  "last_modified": "$(_json_escape "$GOT_LAST_MODIFIED")",
  "etag_auxiliary_only": "$(_json_escape "$GOT_ETAG")"
}
EOF
    echo "TOFU: 首窗 pin 已落 $PIN_FILE (sha256 ${GOT_SHA256:0:12}…)。"
fi
mv -f "$TMP_DL" "$INSTALLER_FILE"
_write_manifest false "$GOT_SHA256"

# ----- 靜默安裝(install4j:-q 無人值守,不啟動程式;-dir 指定目標) -----
if ! sh "$INSTALLER_FILE" -q -dir "$IBKR_GATEWAY_INSTALL_DIR"; then
    echo "ERROR: installer 執行失敗(manifest 維持 applied:false)。" >&2
    exit 7
fi

# ----- unit 安裝 + mask(絕不 enable/start;mask=default-off 的機器強制) -----
mkdir -p "$SYSTEMD_USER_DIR"
for unit in "${UNIT_FILES[@]}"; do
    if [[ ! -f "$SCRIPT_DIR/$unit" ]]; then
        echo "ERROR: unit 模板缺失:$SCRIPT_DIR/$unit" >&2
        exit 8
    fi
    cp "$SCRIPT_DIR/$unit" "$SYSTEMD_USER_DIR/$unit"
done
if ! systemctl --user daemon-reload; then
    echo "ERROR: systemctl --user daemon-reload 失敗。" >&2
    exit 8
fi
# 為什麼 mask 而非只留 disabled:disabled 仍可被 systemctl start 手滑點火;
# mask(symlink /dev/null)使 start 結構性失敗——enable 屬 EA2,由 operator
# 屆時顯式 unmask + 活化紀錄支撐,本腳本階段任何啟動路徑都必須死。
if ! systemctl --user mask ibkr-gateway.service; then
    echo "ERROR: systemctl --user mask ibkr-gateway.service 失敗。" >&2
    exit 8
fi
# timer 保持 default disabled(不 enable 即不生效);不 mask——EA2 開窗時 timer
# 屬 operator 校準面,mask 主 service 已足以封死一切啟動路徑。

# ----- ③ postcheck:dormant 簽名遷移證據(零進程+unit masked+四埠零 listener) -----
if ! bash "$POSTCHECK" --require-unit-masked --output "$APPROVAL_RECORD_DIR/after.postcheck.json"; then
    echo "ERROR: postcheck 失敗——manifest 維持 applied:false;詳見 after.postcheck.json。" >&2
    exit 9
fi

APPLIED_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
_write_manifest true "$GOT_SHA256" "$APPLIED_UTC"
echo "INSTALLED: IB Gateway 安裝完成(sha256 ${GOT_SHA256:0:12};零啟動零登入零 enable)。"
echo "           unit=masked;dormant 新簽名證據:$APPROVAL_RECORD_DIR/after.postcheck.json"
echo "           manifest: $MANIFEST (applied:true)"

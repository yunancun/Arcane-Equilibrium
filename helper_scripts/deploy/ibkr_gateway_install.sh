#!/usr/bin/env bash
# ============================================================================
# ibkr_gateway_install.sh — IB Gateway 安裝腳本(W9a source-ready 交付)
# ----------------------------------------------------------------------------
# MODULE_NOTE
# 模塊用途:從 IBKR 官方來源下載 IB Gateway stable standalone Linux x64
#   installer,經「TOFU sha256 + 官方 metadata 三元組漂移偵測 + 落地位元組
#   數校驗」釘定後靜默安裝到 ~/Jts,並以兩層 systemd 佈局安裝(但絕不
#   enable)配套 user unit:真檔落 data 層,mask symlink 落 config 層。
# 主要流程:守門(host/args)→ preflight(模板/磁盤)→ metadata 漂移偵測
#   (HEAD 三元組 + version.json;dry-run 也跑)→ user bus 探測 → RM-1
#   before 快照 → 兩段式 manifest(applied:false)→ 下載 + 位元組數 +
#   sha256 pin 校驗(首窗 TOFU 落 pin)→ 靜默安裝 → unit 兩層安裝+mask →
#   postcheck(dormant 簽名+Jts 在位斷言)→ 全綠才改寫 applied:true。
# 依賴:同目錄 ibkr-gateway.service / ibkr-gateway-restart.service /
#   ibkr-gateway-restart.timer / ibkr_gateway_postcheck.sh。
#
# 接觸語義定界(IBKR_TODO.md §5 W9a):「接觸」= AMD-2026-07-11-01 語義的
#   broker API/session/資料/訂單效果;本腳本從官方來源下載 installer 屬
#   **供應鏈動作**,僅限 operator 批准窗內執行(pin-by-reference,承 DOC-06
#   RM-4)。安裝不產生任何接觸:**從不啟動 Gateway、從不登入、從不 enable
#   unit**;enable/登入/socket 全屬 EA2+,live 4001 配置屬 EA7,均在範圍外。
#
# 官方文檔事實出典(查閱日 2026-07-17;以下皆官方語義轉述,非原文引用):
#   - channel 語義(stable=低頻更新+不自動更新):
#     https://www.interactivebrokers.com/en/trading/ibgateway-latest.php
#   - 端口語義(Gateway live=4001/paper=4002;TWS live=7496/paper=7497):
#     https://www.interactivebrokers.com/campus/trading-lessons/installing-configuring-tws-for-the-api/
#   - headless(無 GUI)運行不受官方支持(IBC/Xvfb=社群方案):
#     https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/
#
# 供應鏈釘定模型(IB 現勘 2026-07-17 定案):
#   - channel 固定 stable(IB 裁決,與 envelope-gated 活化模型對齊)。latest
#     channel 存在(…/latest-standalone/ibgateway-latest-standalone-linux-x64.sh)
#     但僅 operator 顯式裁決才換用,本腳本不提供 channel 參數。
#   - 官方**無 checksum 發布 channel(CONFIRMED-ABSENT,IB 現勘 2026-07-17)**
#     → 無法 pin 官方公布 sha256。改用 TOFU(trust-on-first-use):首窗下載
#     後本地 sha256 落 pin 檔+receipt;之後每次執行先 HEAD 比對官方 metadata
#     三元組(Content-Length / Last-Modified / ETag 輔助)+ GET 同目錄
#     version.json(buildVersion/buildDateTime),任一漂移 = fail-closed 退
#     operator 重批(IB 發了新版,舊 TOFU pin 必須作廢重釘)。
#   - 下載完成後 stat 位元組數必須 == baseline Content-Length 才准進 sha
#     比對/落 TOFU pin(E2-F2:封 HEAD 過檢→GET 取件之間的替換窗)。
#   - ETag 前 32-hex 疑似 MD5 只作輔助信號記錄於 receipt,不替代 sha256 gate。
#
# 三重防護(全部 fail-closed):
#   ① 主機守門:非 trade-core(IBKR_GATEWAY_EXPECTED_HOST)拒跑;非 Linux 拒跑。
#   ② 顯式批准:必須帶 --operator-approved 且 --approval-record <dir>
#      (RM-1:before/after 快照+兩段式 manifest 落該目錄的 UTC 時戳子目錄,
#      append-only 不 clobber)+ 非空 IBKR_GATEWAY_REASON;缺一即拒。
#   ③ postcheck:安裝完成後自動驗證「零 Gateway 進程 + unit masked +
#      4001/4002/7496/7497 零 listener + ~/Jts 在位」並輸出 postcheck 報告
#      ——這是 dormant 簽名遷移證據(安裝後「~/Jts 不存在」簽名失效,新簽名
#      = ~/Jts 存在但零進程+unit masked+四埠零 listener)。
#
# systemd 兩層佈局(E2-F1/OPS-B1,為什麼):unit 真檔落 data 層
#   ${XDG_DATA_HOME:-~/.local/share}/systemd/user/(查找優先序較低),mask
#   symlink 由 systemctl --user mask 落 config 層 ~/.config/systemd/user/
#   (優先序較高,蓋過 data 層)。若真檔與 mask 同層:重跑安裝時 cp 會撞
#   mask symlink(絕不可穿透 /dev/null 寫入)、mask 會撞既有真檔 File-exists
#   → applied:true 永不可達。兩層分離使 cp(data 層)與 mask(config 層)
#   結構性不相撞;EA2 unmask 移除 config 層鏈後,data 層 unit 以 disabled
#   姿態浮現。**禁用 mask --force**(--force 會把既有檔換成 /dev/null 鏈,
#   EA2 unmask 後 unit 蒸發)。
#
# 端口契約(官方語義轉述,出典見上):本 lane 配置面只允許出現 4002(paper);
#   4001/7496/7497 屬 denylist——僅在 postcheck 零 listener 驗證與注釋中
#   出現,任何配置檔/unit/env 不得引入,live 4001 歸 EA7。
#
# 手動回退 runbook(manifest revert_path 指向本節;全部 operator 窗內動作):
#   1. systemctl --user unmask ibkr-gateway.service   # 移除 config 層 mask 殘鏈
#   2. rm -f ${XDG_DATA_HOME:-$HOME/.local/share}/systemd/user/ibkr-gateway.service \
#            ${XDG_DATA_HOME:-$HOME/.local/share}/systemd/user/ibkr-gateway-restart.service \
#            ${XDG_DATA_HOME:-$HOME/.local/share}/systemd/user/ibkr-gateway-restart.timer
#   3. systemctl --user daemon-reload
#   4. rm -rf ~/Jts                                   # Gateway 安裝目錄
#   5. pin 處置:預設保留 ~/.config/ibkr-gateway/installer_pin.json 供追溯;
#      確認供應鏈事件時刪除並於下一批准窗重 TOFU。
#   6. 回退動作與理由落 approval 紀錄目錄(append-only,新 UTC 時戳子目錄)。
#
# 執行者:operator 親手,或 OPS agent 於批准窗內代跑(批准紀錄按 RM-1 落檔)。
# exit code:0 成功/dry-run 通過;2 平台或主機守門;3 參數/REASON 空/既有
#   ~/Jts 未帶 --allow-existing-jts/approval dir 不合規;4 metadata 漂移或
#   pin 檔壞;5 網路(HEAD/version.json/下載)失敗;6 位元組數或 sha256 與
#   pin 不符;7 installer 執行失敗;8 環境面(模板缺/磁盤不足/user bus 不可
#   達/unit 層衝突/daemon-reload/mask 失敗);9 postcheck 失敗(before 非
#   dormant 或探測面不可用/after 新簽名不成立;manifest 維持 applied:false)。
#
# 硬邊界:
#   - 絕不 systemctl start / enable / unmask;絕不 mask --force;絕不寫入
#     任何登入材料。
#   - 不連 broker API、不開任何 socket、不碰 PG/engine/auth/risk/Cost Gate。
#   - 路徑走 env($HOME / IBKR_GATEWAY_INSTALL_DIR),不硬編碼 runtime 機器路徑。
#   - env 覆寫面(IBKR_GATEWAY_BASELINE_* / *_EXPECTED_HOST / *_UNIT_DIR /
#     *_MASK_DIR / *_PIN_FILE)= 宣告 gate 非認證(已申報,E2-F7/E3 記錄);
#     真安裝面仍被 ②③ 擋住。
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
# env 覆寫僅供 operator 於新批准窗內重釘(manifest 記 baseline_source=env:*);
# 窗後應回填本常數(follow-up commit)。
BASELINE_BUILD_VERSION="${IBKR_GATEWAY_BASELINE_BUILD_VERSION:-10.45.1h}"
BASELINE_BUILD_DATETIME_PREFIX="${IBKR_GATEWAY_BASELINE_BUILD_DATETIME_PREFIX:-20260624}"
BASELINE_CONTENT_LENGTH="${IBKR_GATEWAY_BASELINE_CONTENT_LENGTH:-335674728}"
BASELINE_LAST_MODIFIED_DATE="${IBKR_GATEWAY_BASELINE_LAST_MODIFIED_DATE:-2026-06-25}"

# baseline_source 申報(E3-LOW-2):任何 baseline env 覆寫在位 → manifest 記 env 名單。
BASELINE_SOURCE="constant"
_BASELINE_ENV_OVERRIDES=""
for _v in IBKR_GATEWAY_BASELINE_BUILD_VERSION IBKR_GATEWAY_BASELINE_BUILD_DATETIME_PREFIX \
          IBKR_GATEWAY_BASELINE_CONTENT_LENGTH IBKR_GATEWAY_BASELINE_LAST_MODIFIED_DATE; do
    if [[ -n "${!_v:-}" ]]; then
        _BASELINE_ENV_OVERRIDES+="${_BASELINE_ENV_OVERRIDES:+,}$_v"
    fi
done
if [[ -n "$_BASELINE_ENV_OVERRIDES" ]]; then
    BASELINE_SOURCE="env:$_BASELINE_ENV_OVERRIDES"
fi

# TOFU sha256 pin 檔:首窗下載後寫入;之後每次 apply 必比對。壞 JSON/空值=拒。
PIN_FILE="${IBKR_GATEWAY_PIN_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/ibkr-gateway/installer_pin.json}"

# ----- 安裝面配置 -----
IBKR_GATEWAY_INSTALL_DIR="${IBKR_GATEWAY_INSTALL_DIR:-$HOME/Jts}"
# 主機守門正本值;覆寫僅供測試(tmp 目標),真安裝面仍被 ②③ 擋住。
IBKR_GATEWAY_EXPECTED_HOST="${IBKR_GATEWAY_EXPECTED_HOST:-trade-core}"
# 兩層佈局(見頭注「systemd 兩層佈局」):真檔=data 層;mask symlink=config 層。
UNIT_INSTALL_DIR="${IBKR_GATEWAY_UNIT_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/systemd/user}"
MASK_DIR="${IBKR_GATEWAY_MASK_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_FILES=(ibkr-gateway.service ibkr-gateway-restart.service ibkr-gateway-restart.timer)
POSTCHECK="$SCRIPT_DIR/ibkr_gateway_postcheck.sh"
# curl 統一硬化(E2-F4/E3-LOW-3):連線/總時限 + 重導向上限(供應鏈 URL 不應多跳)
# + 強制 TLS(拒任何降級/重導向出 https)。
CURL_HARDENING=(--connect-timeout 15 --max-time 300 --max-redirs 2 --proto '=https' --tlsv1.2)
# 磁盤 guard:installer ~336MB + 解壓安裝面,保守要求 $HOME 檔案系統 ≥2GB 可用。
MIN_FREE_KB=$((2 * 1024 * 1024))

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
ALLOW_EXISTING_JTS=0
usage() {
    cat >&2 <<'EOF'
用法:
  ibkr_gateway_install.sh --dry-run
      preflight:unit 模板/postcheck 存在性、磁盤 guard(≥2GB)、官方
      metadata 漂移偵測(HEAD+version.json)。零 installer 下載、零安裝面寫入。
  ibkr_gateway_install.sh --operator-approved --approval-record <dir> [--allow-existing-jts]
      operator 批准窗內真安裝;<dir> 為批准紀錄父目錄(絕對路徑、拒 /tmp、
      拒 world-writable;每次跑落新 UTC 時戳子目錄,append-only;RM-1
      before/after 快照 + 兩段式 manifest)。另需非空 env
      IBKR_GATEWAY_REASON(批准理由)。既有 ~/Jts 在位時必須顯式帶
      --allow-existing-jts(申報覆蓋/升級語義)。
EOF
}
while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) MODE="dry-run"; shift ;;
        --operator-approved) OPERATOR_APPROVED=1; MODE="apply"; shift ;;
        --approval-record)
            [[ $# -ge 2 ]] || { echo "ERROR: --approval-record 需要目錄參數。" >&2; usage; exit 3; }
            APPROVAL_RECORD_DIR="$2"; shift 2 ;;
        --allow-existing-jts) ALLOW_EXISTING_JTS=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) echo "ERROR: unknown argument: $1" >&2; usage; exit 3 ;;
    esac
done
REASON="${IBKR_GATEWAY_REASON:-}"
if [[ "$MODE" == "apply" ]]; then
    if [[ "$OPERATOR_APPROVED" -ne 1 || -z "$APPROVAL_RECORD_DIR" ]]; then
        echo "ERROR: 真安裝必須同時帶 --operator-approved 與 --approval-record <dir>(RM-1)。" >&2
        usage
        exit 3
    fi
    # OPS-B3:批准理由必須非空落 manifest——「unspecified」不是可審計的批准紀錄。
    if [[ -z "$REASON" ]]; then
        echo "ERROR: apply 模式必須設非空 IBKR_GATEWAY_REASON(批准理由,落 manifest)。" >&2
        exit 3
    fi
    # 既有 ~/Jts 顯式 gate:重裝/升級必須顯式申報,不得隱式覆蓋。
    if [[ -d "$IBKR_GATEWAY_INSTALL_DIR" && "$ALLOW_EXISTING_JTS" -ne 1 ]]; then
        echo "ERROR: $IBKR_GATEWAY_INSTALL_DIR 已存在——重裝/升級必須顯式帶 --allow-existing-jts。" >&2
        echo "       覆蓋語義:install4j 就地安裝進既有目錄(升級);既有 jts.ini/設定檔保留。" >&2
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

# ----- preflight(dry-run 與 apply 共用):模板/postcheck 存在性 + 磁盤 guard -----
for f in "${UNIT_FILES[@]}" "$(basename "$POSTCHECK")"; do
    if [[ ! -f "$SCRIPT_DIR/$f" ]]; then
        echo "ERROR: 交付面檔案缺失:$SCRIPT_DIR/$f(unit 模板/postcheck 必須與本腳本同目錄)。" >&2
        exit 8
    fi
done
AVAIL_KB="$(df -Pk "$HOME" | awk 'NR==2{print $4}')"
if [[ -z "$AVAIL_KB" || "$AVAIL_KB" -lt "$MIN_FREE_KB" ]]; then
    echo "ERROR: 磁盤 guard — \$HOME 檔案系統可用 ${AVAIL_KB:-unknown}KB < ${MIN_FREE_KB}KB(2GB)。" >&2
    exit 8
fi

# ----- metadata 三元組漂移偵測(dry-run 也跑;任一漂移 fail-closed 退 operator) -----
HEAD_OUT="$(curl -fsSI "${CURL_HARDENING[@]}" "$IBKR_GATEWAY_INSTALLER_URL")" || {
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
curl -fsSL "${CURL_HARDENING[@]}" -o "$VERSION_JSON_TMP" "$IBKR_GATEWAY_VERSION_JSON_URL" || {
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

echo "------- IB Gateway install plan -------"
echo "installer URL  : $IBKR_GATEWAY_INSTALLER_URL"
echo "version.json   : $IBKR_GATEWAY_VERSION_JSON_URL"
echo "baseline       : buildVersion=$BASELINE_BUILD_VERSION buildDateTime~=$BASELINE_BUILD_DATETIME_PREFIX"
echo "                 Content-Length=$BASELINE_CONTENT_LENGTH Last-Modified=$BASELINE_LAST_MODIFIED_DATE"
echo "baseline source: $BASELINE_SOURCE"
echo "drift check    : PASS(HEAD 三元組 + version.json 全符)"
echo "sha256 pin     : $PIN_STATE ($PIN_FILE)"
echo "install dir    : $IBKR_GATEWAY_INSTALL_DIR $( [[ -d "$IBKR_GATEWAY_INSTALL_DIR" ]] && echo '[已存在:apply 需 --allow-existing-jts]' || echo '[不存在:全新安裝]' )"
echo "unit data 層   : $UNIT_INSTALL_DIR (${UNIT_FILES[*]})"
echo "mask config 層 : $MASK_DIR (mask symlink 落此;禁 --force)"
echo "unit posture   : install 後 mask ibkr-gateway.service;絕不 enable/start"
echo "port contract  : 配置面僅 4002(paper);4001/7496/7497 denylist(postcheck 驗零 listener)"
echo "disk guard     : PASS(\$HOME 可用 ${AVAIL_KB}KB ≥ 2GB)"
echo "mode           : $MODE"
echo "----------------------------------------"

if [[ "$MODE" != "apply" ]]; then
    echo
    echo "DRY-RUN PASS: preflight+漂移偵測全綠;零 installer 下載、零安裝面寫入。"
    echo "              operator 批准窗內以 --operator-approved --approval-record <dir> 真跑。"
    exit 0
fi

# ----- user bus 探測(前移到下載前:335MB 下載後才發現 bus 不可達=浪費+殘留) -----
if ! systemctl --user show-environment >/dev/null 2>&1; then
    echo "ERROR: systemd user bus 不可達(systemctl --user show-environment 失敗)。" >&2
    echo "       unit 安裝/mask 需 user bus;請確認 linger/登入 session 後重跑。" >&2
    exit 8
fi

# ----- RM-1 批准紀錄目錄:拒 /tmp、拒 world-writable、每次跑新 UTC 子目錄 -----
if [[ "$APPROVAL_RECORD_DIR" != /* ]]; then
    echo "ERROR: --approval-record 必須是絕對路徑(got: $APPROVAL_RECORD_DIR)。" >&2
    exit 3
fi
case "$APPROVAL_RECORD_DIR" in
    /tmp|/tmp/*)
        echo "ERROR: 批准紀錄目錄拒 /tmp 前綴(重開機蒸發=RM-1 紀錄不耐久)。" >&2
        exit 3
        ;;
esac
mkdir -p "$APPROVAL_RECORD_DIR"
PARENT_PERMS="$(stat -c %a "$APPROVAL_RECORD_DIR")"
_OTHERS_DIGIT="${PARENT_PERMS: -1}"
case "$_OTHERS_DIGIT" in
    2|3|6|7)
        echo "ERROR: 批准紀錄目錄 world-writable(mode $PARENT_PERMS)——RM-1 紀錄可被任意進程篡改,拒。" >&2
        exit 3
        ;;
esac
UTC_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
# append-only:每次跑落新 UTC 子目錄防 clobber;同秒碰撞加 PID 後綴
# (mirror install_logrotate_from_repo.sh)。
RUN_DIR="$APPROVAL_RECORD_DIR/$UTC_STAMP"
if [[ -e "$RUN_DIR" ]]; then
    RUN_DIR="$RUN_DIR.$$"
fi
mkdir -p "$RUN_DIR"
ACTOR="${IBKR_GATEWAY_ACTOR:-${USER:-unknown}}"

# ----- before 快照(RM-1):安裝前 dormant 簽名(unit 未裝允許 absent) -----
BEFORE_SHA=""
if ! bash "$POSTCHECK" --output "$RUN_DIR/before.postcheck.json"; then
    echo "ERROR: before 快照 FAIL——dormant 簽名不成立(有活信號),或探測面不可用" >&2
    echo "       (pgrep/ss 缺席、user bus 異常等 fail-closed 項)。拒絕安裝。" >&2
    echo "       詳見 $RUN_DIR/before.postcheck.json;請先排查再開窗。" >&2
    exit 9
fi
BEFORE_SHA="$(_sha256_file "$RUN_DIR/before.postcheck.json")"

# ----- 兩段式 manifest:先落 applied:false;postcheck 全綠才改寫 applied:true -----
MANIFEST="$RUN_DIR/manifest.json"
GOT_SHA256=""
DOWNLOADED_BYTES=""
MISMATCH_SHA256=""
MISMATCH_NOTE=""
AFTER_SHA=""
_write_manifest() {
    # 參數:$1=applied(true/false) $2=applied_utc(僅 true);其餘欄位讀全局變數
    # (GOT_*/BEFORE_SHA/AFTER_SHA/MISMATCH_*,多階段補寫同一 manifest)。
    local applied="$1" applied_utc="${2:-}"
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
  "baseline_source": "$(_json_escape "$BASELINE_SOURCE")",
  "pin_file": "$(_json_escape "$PIN_FILE")",
  "pin_state_at_start": "$(_json_escape "$PIN_STATE")",
  "downloaded_sha256": "$(_json_escape "$GOT_SHA256")",
  "downloaded_bytes": "$(_json_escape "$DOWNLOADED_BYTES")",
  "mismatch_sha256": "$(_json_escape "$MISMATCH_SHA256")",
  "mismatch_note": "$(_json_escape "$MISMATCH_NOTE")",
  "install_dir": "$(_json_escape "$IBKR_GATEWAY_INSTALL_DIR")",
  "allow_existing_jts": $([[ "$ALLOW_EXISTING_JTS" -eq 1 ]] && echo true || echo false),
  "unit_install_dir": "$(_json_escape "$UNIT_INSTALL_DIR")",
  "mask_dir": "$(_json_escape "$MASK_DIR")",
  "unit_files": "$(_json_escape "${UNIT_FILES[*]}")",
  "revert_path": "helper_scripts/deploy/ibkr_gateway_install.sh 頭注「手動回退 runbook」節",
  "before_snapshot": "before.postcheck.json",
  "before_sha256": "$(_json_escape "$BEFORE_SHA")",
  "after_snapshot": "after.postcheck.json",
  "after_sha256": "$(_json_escape "$AFTER_SHA")"$tail_fields
}
EOF
}
_write_manifest false

# ----- 下載 + 位元組數校驗(E2-F2)+ sha256 pin 校驗(pinned 比對;首窗 TOFU) -----
INSTALLER_FILE="$RUN_DIR/ibgateway-stable-standalone-linux-x64.sh"
TMP_DL="$INSTALLER_FILE.part"
trap 'rm -f "$TMP_DL" "$VERSION_JSON_TMP"' EXIT
if ! curl -fSL "${CURL_HARDENING[@]}" -o "$TMP_DL" "$IBKR_GATEWAY_INSTALLER_URL"; then
    echo "ERROR: installer 下載失敗:$IBKR_GATEWAY_INSTALLER_URL" >&2
    exit 5
fi
# 位元組數 == baseline Content-Length 才准進 sha 比對/落 pin(封 HEAD→GET 替換窗:
# HEAD 過檢後 GET 若被換內容,尺寸多半先露餡;尺寸同、內容異則由 sha pin 擋)。
DOWNLOADED_BYTES="$(stat -c %s "$TMP_DL")"
if [[ "$DOWNLOADED_BYTES" != "$BASELINE_CONTENT_LENGTH" ]]; then
    MISMATCH_NOTE="content_length_mismatch(downloaded=$DOWNLOADED_BYTES baseline=$BASELINE_CONTENT_LENGTH)"
    _write_manifest false
    rm -f "$TMP_DL"
    echo "ERROR: 落地位元組數 $DOWNLOADED_BYTES != baseline Content-Length $BASELINE_CONTENT_LENGTH。" >&2
    echo "       HEAD→GET 之間內容疑被替換;下載物已刪除(mismatch 已記 manifest),退 operator 調查。" >&2
    exit 6
fi
GOT_SHA256="$(_sha256_file "$TMP_DL")"
if [[ -n "$PIN_SHA256" ]]; then
    if [[ "${GOT_SHA256,,}" != "${PIN_SHA256,,}" ]]; then
        # E3-LOW-5:先把 mismatch sha 落 manifest 再刪檔——證據不得隨下載物蒸發。
        MISMATCH_SHA256="$GOT_SHA256"
        MISMATCH_NOTE="sha256_pin_mismatch(pinned=$PIN_SHA256)"
        _write_manifest false
        rm -f "$TMP_DL"
        echo "ERROR: sha256 與 TOFU pin 不符 — got $GOT_SHA256, pinned $PIN_SHA256。" >&2
        echo "       metadata 三元組未漂移但位元組變了=強烈供應鏈警訊;下載物已刪除" >&2
        echo "       (mismatch_sha256 已記 manifest),退 operator 調查。" >&2
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
  "downloaded_bytes": "$(_json_escape "$DOWNLOADED_BYTES")",
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
_write_manifest false

# ----- 靜默安裝(install4j:-q 無人值守,不啟動程式;-dir 指定目標) -----
if ! sh "$INSTALLER_FILE" -q -dir "$IBKR_GATEWAY_INSTALL_DIR"; then
    echo "ERROR: installer 執行失敗(manifest 維持 applied:false)。" >&2
    exit 7
fi

# ----- unit 兩層安裝 + mask(絕不 enable/start;絕不 mask --force) -----
mkdir -p "$UNIT_INSTALL_DIR"
for unit in "${UNIT_FILES[@]}"; do
    target="$UNIT_INSTALL_DIR/$unit"
    # 絕不穿透 symlink 寫入(cp 會 follow symlink 把內容寫進鏈目標——若目標是
    # /dev/null 即靜默蒸發,若是他處檔案即越界寫)。data 層出現 symlink=治理外
    # 狀態,拒並退 operator 排查。
    if [[ -L "$target" ]]; then
        echo "ERROR: $target 是 symlink(→$(readlink "$target"))——拒絕穿透寫入;請 operator 排查後重跑。" >&2
        exit 8
    fi
    cp "$SCRIPT_DIR/$unit" "$target"
done
if ! systemctl --user daemon-reload; then
    echo "ERROR: systemctl --user daemon-reload 失敗。" >&2
    exit 8
fi
# 為什麼 mask 而非只留 disabled:disabled 仍可被 systemctl start 手滑點火;
# mask(config 層 symlink → /dev/null,蓋過 data 層真檔)使 start 結構性失敗
# ——enable 屬 EA2,由 operator 屆時顯式 unmask + 活化紀錄支撐,本腳本階段
# 任何啟動路徑都必須死。兩層佈局使重跑安裝時 cp(data 層)與 mask(config 層)
# 結構性不相撞;**禁 mask --force**(會把既有檔換成 /dev/null 鏈,EA2 unmask
# 後 unit 蒸發)。
MASK_LINK="$MASK_DIR/ibkr-gateway.service"
if [[ -L "$MASK_LINK" ]]; then
    _LINK_TARGET="$(readlink "$MASK_LINK")"
    if [[ "$_LINK_TARGET" == "/dev/null" ]]; then
        echo "NOTE: ibkr-gateway.service 已是 masked(config 層既有 /dev/null 鏈),跳過 mask。"
    else
        echo "ERROR: $MASK_LINK 是非 mask symlink(→$_LINK_TARGET)——拒;請 operator 排查後重跑。" >&2
        exit 8
    fi
elif [[ -e "$MASK_LINK" ]]; then
    echo "ERROR: $MASK_LINK 已存在且非 symlink——mask 會 File-exists 失敗;禁用 --force,請 operator 排查。" >&2
    exit 8
else
    mkdir -p "$MASK_DIR"
    if ! systemctl --user mask ibkr-gateway.service; then
        echo "ERROR: systemctl --user mask ibkr-gateway.service 失敗。" >&2
        exit 8
    fi
fi
# timer 保持 default disabled(不 enable 即不生效);不 mask——EA2 開窗時 timer
# 屬 operator 校準面,mask 主 service 已足以封死一切啟動路徑。

# ----- ③ postcheck:dormant 簽名遷移證據(零進程+unit masked+四埠零 listener+Jts 在位) -----
if ! bash "$POSTCHECK" --require-unit-masked --require-jts-present --output "$RUN_DIR/after.postcheck.json"; then
    echo "ERROR: after postcheck FAIL——dormant 新簽名不成立(活信號/unit 非 masked/" >&2
    echo "       Jts 缺位)或探測面不可用;manifest 維持 applied:false。" >&2
    echo "       詳見 $RUN_DIR/after.postcheck.json。" >&2
    exit 9
fi
AFTER_SHA="$(_sha256_file "$RUN_DIR/after.postcheck.json")"

APPLIED_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
_write_manifest true "$APPLIED_UTC"
echo "INSTALLED: IB Gateway 安裝完成(sha256 ${GOT_SHA256:0:12};零啟動零登入零 enable)。"
echo "           unit=masked(data 層真檔 $UNIT_INSTALL_DIR;config 層 mask 鏈 $MASK_DIR)"
echo "           dormant 新簽名證據:$RUN_DIR/after.postcheck.json"
echo "           manifest: $MANIFEST (applied:true)"

#!/usr/bin/env bash
# install_logrotate_from_repo.sh — 從 repo 正本 logrotate-openclaw.conf 安裝 runtime conf
# ----------------------------------------------------------------------------
# 為什麼有此檔（PR#24 [95] 哨兵已知限制收口:logrotate 治理唯一安裝入口）：
#   2026-07-15 logrotate drift 事故:runtime 副本漂回只蓋 /tmp 死路徑,var 真
#   engine.log 輪替自 06-27 起空轉、cron log 裸奔到 4.5GB 才被人工發現。[95] 哨兵
#   首版以檔案 mtime max() 當 drift 時鐘 proxy,內生漏洞=反覆手改 runtime 副本可
#   不斷刷新 24h 容忍窗。本 installer 是唯一被授權寫 runtime logrotate conf 的
#   入口,把每次 mutation 變成「canonical → diff → 快照 → shrink-guard →
#   logrotate -d validation → 兩段式 manifest」的可追溯序列;[95] 哨兵改以最新
#   applied:true manifest 的 mtime 為 drift 起點,任何繞過此入口的裸 cp / 手編
#   都是治理外行為——mismatch 將以「無合規 manifest」直接視為超 24h 窗。
#
# 執行流程:
#   1. pre-flight:canonical 缺失拒絕;空 canonical（0 active 行）一律拒絕。
#   2. shrink-guard:canonical stanza 數 *2 < runtime stanza 數 → 拒絕,除非
#      OPENCLAW_LOGROTATE_ALLOW_SHRINK=1 顯式豁免（封殺「蓋掉現有輪替面」事故;
#      runtime 缺失/空=首裝,guard 不適用）。
#   3. validation gate:`logrotate -d <canonical>` 非 0 → 拒絕（dry-run 也擋——
#      plan 本身壞）;真 Linux 無 logrotate binary 同拒（輪替本已死）。
#   4. 落檔:before/after/diff/manifest 寫持久路徑
#      $OPENCLAW_DATA_DIR/logrotate_mutations/<UTC>Z/。
#   5. manifest 兩段式:先落 "applied": false;--apply 原子安裝（同目錄 tmp 檔 +
#      mv -f）且 post-verify sha256 平價通過後,才改寫為 "applied": true +
#      post_apply_sha256（[95] 只認 applied:true 為合規安裝,dry-run 不刷時鐘）。
#   6. install:預設 --dry-run 不寫;顯式 --apply 才落 runtime 路徑。
#
# 硬邊界:
#   - 本 script = 唯一授權寫 runtime logrotate conf 的入口;繞過（裸 cp/手編）=
#     治理外行為,[95] 哨兵將以「無合規 manifest」視為超窗。
#   - 不寫 secrets;不改 PG/schema;不觸 engine/app/env/risk/Cost Gate。
#   - 空 canonical 一律拒絕,不論任何 flag。
#   - 路徑走 env（OPENCLAW_DATA_DIR / $HOME）,不硬編碼 runtime 機器路徑
#     （per feedback_cross_platform）。

set -euo pipefail

# ----- 平台守門:僅 Linux runtime 跑（mirror install_crontab_from_repo.sh）-----
# OPENCLAW_LOGROTATE_SKIP_PLATFORM_GUARD=1 僅供 Mac dev 測試繞過平台檢查,在 tmp_path
# 目標上跑完整流程(含 --apply 的原子安裝/post-verify)。真 runtime 寫入面仍由顯式
# --apply 旗+路徑 env(canonical/runtime/data 全可覆寫,測試一律指 tmp)控制;此旗
# 本身不改變任何寫入語意,故不弱化 live/安全邊界。
if [[ "$(uname -s)" != "Linux" && "${OPENCLAW_LOGROTATE_SKIP_PLATFORM_GUARD:-0}" != "1" ]]; then
    echo "ERROR: install_logrotate_from_repo.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑;Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# repo root = helper_scripts/cron 的上兩層;優先 OPENCLAW_BASE_DIR。
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
CANONICAL="${OPENCLAW_LOGROTATE_CANONICAL:-$OPENCLAW_BASE_DIR/helper_scripts/logrotate-openclaw.conf}"
# runtime 路徑走 $HOME（trade-core 上即 crontab Tier 0 整點 logrotate 行引用的同一路徑）,
# 禁硬編機器 home 絕對路徑;測試以 env 覆寫指 tmp,絕不真寫 $HOME。
RUNTIME_CONF="${OPENCLAW_LOGROTATE_RUNTIME_CONF:-$HOME/logrotate-openclaw.conf}"
SHRINK_ALLOWED="${OPENCLAW_LOGROTATE_ALLOW_SHRINK:-0}"

# ----- 參數:預設 dry-run,--apply 才實寫 -----
MODE="dry-run"
for arg in "$@"; do
    case "$arg" in
        --apply)   MODE="apply" ;;
        --dry-run) MODE="dry-run" ;;
        *)
            echo "ERROR: unknown argument: $arg (支援 --dry-run[預設] / --apply)" >&2
            exit 3
            ;;
    esac
done

# ----- pre-flight:canonical 必在 -----
if [[ ! -f "$CANONICAL" ]]; then
    echo "ERROR: canonical not found: $CANONICAL" >&2
    exit 4
fi

# head sha 僅溯源用（無 render,不是 pin 派生鏈）:git 失敗記 "unknown",不 hard-fail。
HEAD_SHA="$(git -C "$OPENCLAW_BASE_DIR" rev-parse --short HEAD 2>/dev/null || true)"
if [[ -z "$HEAD_SHA" ]]; then
    HEAD_SHA="unknown"
fi

# ----- helper:數非空非註釋行 / stanza 數 / 整檔 sha256 -----
# active 行只看真正會被 logrotate 讀的行,註釋與空行不計入（空 canonical 守衛用）。
_count_active_lines() {
    grep -vE '^[[:space:]]*(#|$)' | grep -c . || true
}
# stanza 數以「非註釋行且以 '{' 結尾」計（opener-idiom 近似;shrink-guard 用）:
# logrotate stanza opener 慣式=`<path...> {` 行尾開括號。不用裸 grep -c '{':
# postrotate 內的 awk '{print}' / 註釋裡的 ${HOME} 等行內大括號會誤計,虛胖
# runtime 數還可能誤觸 shrink-guard。
_count_stanzas() {
    grep -v '^[[:space:]]*#' "$1" | grep -cE '\{[[:space:]]*$' || true
}
# 整檔 sha256:與 [95] 哨兵同口徑（位元組平價即安裝契約 machine-check）。
# sha256sum 優先,無則退 shasum -a 256（Mac dev 測試面;真 Linux runtime 兩者必有其一）。
_sha256_file() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}
# JSON 字串轉義:manifest 欄位含自然語言（REASON/ACTOR）與任意路徑,引號/反斜線/
# 控制字元未轉義會產壞 JSON → [95] 視同無合規安裝,之後任何 mismatch 零 grace 立即
# 超窗——合法輸入不得毒化 receipt。順序關鍵:反斜線必最先轉義,否則後續轉義產物
# 會被二次轉義。
_json_escape() {
    local s="$1"
    s="${s//\\/\\\\}"
    s="${s//\"/\\\"}"
    s="${s//$'\n'/\\n}"
    s="${s//$'\t'/\\t}"
    s="${s//$'\r'/\\r}"
    printf '%s' "$s"
}

# ----- 1. 空 canonical 守衛（不論任何 flag 一律拒絕）-----
CANONICAL_ACTIVE="$(_count_active_lines < "$CANONICAL")"
if [[ "$CANONICAL_ACTIVE" -eq 0 ]]; then
    echo "ERROR: canonical has 0 active lines — refusing to install empty logrotate conf." >&2
    echo "       （空 conf 安裝 = 清空整機輪替面,一律拒絕,無豁免 flag）。" >&2
    exit 6
fi
AFTER_STANZAS="$(_count_stanzas "$CANONICAL")"
AFTER_SHA="$(_sha256_file "$CANONICAL")"

# ----- 2. runtime 現況快照 + stanza 數 -----
RUNTIME_PRESENT=0
BEFORE_STANZAS=0
BEFORE_SHA="absent"
if [[ -f "$RUNTIME_CONF" ]]; then
    RUNTIME_PRESENT=1
    BEFORE_STANZAS="$(_count_stanzas "$RUNTIME_CONF")"
    BEFORE_SHA="$(_sha256_file "$RUNTIME_CONF")"
fi

# ----- 3. stanza shrink-guard:canonical stanza *2 < runtime stanza → 拒絕（除非顯式豁免）-----
# 為什麼 50%:直接封殺「新 conf 蓋掉大半現有輪替面」事故（crontab 屠殺同型防護）;
# 正常增刪個別 stanza 不會觸發。runtime 缺失/空（0 stanza）=首裝,guard 不適用。
SHRINK_TRIGGERED=0
if [[ "$RUNTIME_PRESENT" -eq 1 && "$BEFORE_STANZAS" -gt 0 ]]; then
    if [[ $(( AFTER_STANZAS * 2 )) -lt "$BEFORE_STANZAS" ]]; then
        SHRINK_TRIGGERED=1
    fi
fi
SHRINK_OVERRIDE_JSON=0
if [[ "$SHRINK_ALLOWED" == "1" ]]; then
    SHRINK_OVERRIDE_JSON=1
fi

# ----- 4. validation gate:logrotate -d 讀 canonical（plan 壞則 dry-run 也拒）-----
# binary 尋找序:PATH 上的 logrotate → /usr/sbin/logrotate（trade-core crontab 行同路徑）。
LOGROTATE_BIN=""
if command -v logrotate >/dev/null 2>&1; then
    LOGROTATE_BIN="$(command -v logrotate)"
elif [[ -x /usr/sbin/logrotate ]]; then
    LOGROTATE_BIN="/usr/sbin/logrotate"
fi
VALIDATION=""
VALIDATION_OUTPUT=""
if [[ -n "$LOGROTATE_BIN" ]]; then
    if VALIDATION_OUTPUT="$("$LOGROTATE_BIN" -d "$CANONICAL" 2>&1)"; then
        VALIDATION="passed"
    else
        VALIDATION="failed"
    fi
else
    if [[ "${OPENCLAW_LOGROTATE_SKIP_PLATFORM_GUARD:-0}" == "1" ]]; then
        # Mac dev 測試面:無 binary 記錄後續走純邏輯（不放行任何真寫入面）。
        VALIDATION="skipped_no_binary"
    else
        # 真 Linux runtime 無 logrotate = 每小時輪替 cron 本已死,fail-closed。
        VALIDATION="no_binary"
    fi
fi

# ----- 5. 落檔:before/after/diff/manifest 寫持久路徑 -----
UTC_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MUT_DIR="$OPENCLAW_DATA_DIR/logrotate_mutations/$UTC_STAMP"
# 同秒碰撞防護:同一秒內二次執行（如 dry-run 緊接 --apply）會共用 UTC 目錄名,
# 後者會覆蓋前者的 receipt——目錄已存在即追加 .$$（PID）後綴保唯一。
if [[ -e "$MUT_DIR" ]]; then
    MUT_DIR="$MUT_DIR.$$"
fi
mkdir -p "$MUT_DIR"
if [[ "$RUNTIME_PRESENT" -eq 1 ]]; then
    cp "$RUNTIME_CONF" "$MUT_DIR/conf.before.txt"
else
    # runtime 缺=首裝:before 快照落空檔,manifest before_sha256 記 "absent"。
    : > "$MUT_DIR/conf.before.txt"
fi
cp "$CANONICAL" "$MUT_DIR/conf.after.txt"
# diff 只做記錄,退出碼非 0 不代表失敗（有差異是常態）。
diff -u "$MUT_DIR/conf.before.txt" "$MUT_DIR/conf.after.txt" > "$MUT_DIR/conf.diff.txt" 2>/dev/null || true

ACTOR="${OPENCLAW_LOGROTATE_ACTOR:-${USER:-unknown}}"
REASON="${OPENCLAW_LOGROTATE_REASON:-unspecified}"
# 自然語言/路徑欄位一律過 _json_escape 再內插 heredoc（REASON 含引號是常態非欺詐,
# 不得因此產壞 JSON manifest）。
ACTOR_JSON="$(_json_escape "$ACTOR")"
REASON_JSON="$(_json_escape "$REASON")"
CANONICAL_JSON="$(_json_escape "$CANONICAL")"
RUNTIME_CONF_JSON="$(_json_escape "$RUNTIME_CONF")"

# manifest 兩段式（關鍵設計,[95] 只認 applied:true）:先落 applied:false;--apply
# post-verify 通過後才改寫 applied:true + post_apply_sha256。dry-run / 中途拒絕的
# manifest 永遠停在 applied:false,不刷 [95] drift 時鐘。
_write_manifest() {
    # 參數:$1=applied(true/false) $2=post_apply_sha256(僅 applied=true) $3=applied_utc(同)
    local applied="$1" post_sha="${2:-}" applied_utc="${3:-}"
    local tail_fields=""
    if [[ "$applied" == "true" ]]; then
        tail_fields="$(printf ',\n  "post_apply_sha256": "%s",\n  "applied_utc": "%s"' "$post_sha" "$applied_utc")"
    fi
    cat > "$MUT_DIR/manifest.json" <<EOF
{
  "utc": "$UTC_STAMP",
  "mode": "$MODE",
  "applied": $applied,
  "actor": "$ACTOR_JSON",
  "reason": "$REASON_JSON",
  "canonical": "$CANONICAL_JSON",
  "runtime_conf": "$RUNTIME_CONF_JSON",
  "head_sha": "$HEAD_SHA",
  "before_sha256": "$BEFORE_SHA",
  "after_sha256": "$AFTER_SHA",
  "before_stanzas": $BEFORE_STANZAS,
  "after_stanzas": $AFTER_STANZAS,
  "shrink_guard_triggered": $SHRINK_TRIGGERED,
  "shrink_guard_override": $SHRINK_OVERRIDE_JSON,
  "validation": "$VALIDATION"$tail_fields
}
EOF
}
_write_manifest false

echo "------- logrotate install plan -------"
echo "canonical       : $CANONICAL"
echo "runtime conf    : $RUNTIME_CONF"
echo "head sha        : $HEAD_SHA"
echo "before stanzas  : $BEFORE_STANZAS (sha256 $BEFORE_SHA)"
echo "after  stanzas  : $AFTER_STANZAS (sha256 $AFTER_SHA)"
echo "validation      : $VALIDATION"
echo "mutation dir    : $MUT_DIR"
echo "mode            : $MODE"
echo "---------------------------------------"

# ----- 6. shrink-guard 執行（manifest 已落,拒絕本身有追溯紀錄）-----
if [[ "$SHRINK_TRIGGERED" -eq 1 ]]; then
    if [[ "$SHRINK_ALLOWED" != "1" ]]; then
        echo "ERROR: stanza shrink-guard tripped — canonical stanzas ($AFTER_STANZAS) * 2 < runtime stanzas ($BEFORE_STANZAS)." >&2
        echo "       （縮面事故防護:新 conf 蓋掉大半現有輪替面即本型事故。）" >&2
        echo "       如確為有意縮減 stanza,set OPENCLAW_LOGROTATE_ALLOW_SHRINK=1 顯式覆寫。" >&2
        echo "       manifest 已落 $MUT_DIR/manifest.json（shrink_guard_triggered=1）供追溯。" >&2
        exit 7
    fi
    echo "WARN: stanza shrink-guard tripped but OPENCLAW_LOGROTATE_ALLOW_SHRINK=1 override active — proceeding." >&2
fi

# ----- 7. validation gate 執行（dry-run 也擋:plan 本身壞不落地）-----
if [[ "$VALIDATION" == "failed" ]]; then
    echo "ERROR: logrotate -d validation failed for canonical: $CANONICAL" >&2
    echo "       plan 本身壞——dry-run 也拒絕;logrotate -d 輸出:" >&2
    printf '%s\n' "$VALIDATION_OUTPUT" | tail -n 20 >&2
    exit 8
fi
if [[ "$VALIDATION" == "no_binary" ]]; then
    echo "ERROR: logrotate binary not found (PATH 與 /usr/sbin/logrotate 皆無)。" >&2
    echo "       真 Linux runtime 無 logrotate = 每小時輪替本已死,fail-closed 拒絕安裝。" >&2
    exit 8
fi

# ----- 8. install:預設 dry-run 不寫;--apply 才原子落 runtime 路徑 -----
if [[ "$MODE" != "apply" ]]; then
    echo
    echo "DRY-RUN: not modifying runtime conf. before/after/diff/manifest 已落 ${MUT_DIR}（applied:false,不計為合規安裝）。"
    echo "         確認 after 內容無誤後,加 --apply 實際安裝。"
    exit 0
fi

# 原子安裝:先 cp 到 runtime 同目錄 tmp 檔,再 mv -f 就位（同 FS rename,無半寫窗）。
# EXIT trap 清殘檔:cp 後 mv 前若進程死亡不留 .tmp.$$;mv 成功後 rm -f 為 no-op。
TMP_CONF="$(dirname "$RUNTIME_CONF")/.$(basename "$RUNTIME_CONF").tmp.$$"
trap 'rm -f "$TMP_CONF"' EXIT
cp "$CANONICAL" "$TMP_CONF"
mv -f "$TMP_CONF" "$RUNTIME_CONF"

# post-verify:runtime 整檔 sha256 必須等於 canonical（與 [95] 哨兵同口徑）。
POST_SHA="$(_sha256_file "$RUNTIME_CONF")"
if [[ "$POST_SHA" != "$AFTER_SHA" ]]; then
    echo "ERROR: post-verify failed — sha256(runtime)=$POST_SHA != sha256(canonical)=$AFTER_SHA。" >&2
    echo "       manifest 維持 applied:false（不計為合規安裝）;請檢查 runtime 路徑寫入面。" >&2
    exit 9
fi

APPLIED_UTC="$(date -u +%Y%m%dT%H%M%SZ)"
_write_manifest true "$POST_SHA" "$APPLIED_UTC"
echo "INSTALLED: runtime logrotate conf replaced from repo canonical (sha256 ${POST_SHA:0:12})."
echo "           manifest: $MUT_DIR/manifest.json (applied:true — [95] 哨兵合規安裝紀錄)"

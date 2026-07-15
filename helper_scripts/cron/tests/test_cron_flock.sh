#!/usr/bin/env bash
# test_cron_flock.sh — cron_flock.sh 反疊加 flock 鎖的 standalone 自測。
#
# 跑法：bash helper_scripts/cron/tests/test_cron_flock.sh
#   exit 0 = PASS（含環境性 SKIP：如 Mac 無 flock 二進位時 case 2-5 自動跳過）
#   exit 1 = FAIL
#
# Case 一覽：
#   1. 無 flock 二進位（PATH 剝離子 shell）→ return 2 + ERROR log 行（fail-safe skip）。
#   2. 取鎖成功 → return 0 + 鎖檔含 pid= 持鎖者診斷行。
#   3. 持鎖中第二取鎖 → return 1 + SKIP log；鎖檔持鎖者診斷行未被截斷。
#   4. 核心反疊加性質：kill -9 持鎖進程 → 立即重取鎖成功
#      （不等任何閾值；kernel 關 fd 自動放鎖）。
#   5. 長跑告警：把持有中的鎖檔 mtime 動態調舊 → 第二取鎖 log 出 WARN 超齡行，
#      且 return 1 不搶佔。
#   6. flock 缺席的機器（如 Mac dev）自動 SKIP case 2-5 與 7（輸出 SKIPPED 原因，
#      exit 0），case 1 照跑。case 2-5/7 另依賴 bash>=4.1 的 {var}> fd 分配語法，
#      bash 過舊時同樣 SKIP。
#   7. 鎖檔目錄不可寫（open-fail 分支）→ return 2 + ERROR log + 呼叫方
#      set -euo pipefail shell 存活（哨兵行驗法；E2 P2-1，比照 E4 gate #3）。
#      open-fail 分支位於 command -v flock 檢查之後——Mac 無 flock 會先在
#      missing-binary 分支 return 2、測不到本分支，故 case 7 與 2-5 同屬
#      flock-gated；root 不受目錄權限限制（mode 500 失效）亦 SKIP。
#
# 紀律：不硬編日期/機器路徑（mtime 調舊為動態計算）；kill 後一律 wait 收屍，
# 避免殭屍/晚死進程干擾斷言；holder 阻塞在 read builtin（不 spawn 子進程），
# 使 kill -9 後鎖的釋放是同步確定的。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/cron_flock.sh"

if [[ ! -f "$LIB" ]]; then
    echo "FAIL: lib 不存在：$LIB"
    exit 1
fi

PASS=0
FAIL=0
SKIP=0
pass() { PASS=$((PASS + 1)); echo "PASS: $1"; }
fail() { FAIL=$((FAIL + 1)); echo "FAIL: $1"; }
skip() { SKIP=$((SKIP + 1)); echo "SKIP: $1"; }

TMP="$(mktemp -d)" || { echo "FAIL: mktemp -d 失敗"; exit 1; }
HOLDER_PIDS=()
cleanup() {
    local p
    for p in "${HOLDER_PIDS[@]:-}"; do
        [[ -n "$p" ]] || continue
        kill -9 "$p" 2>/dev/null || true
        wait "$p" 2>/dev/null || true
    done
    rm -rf "$TMP"
}
trap cleanup EXIT

# ---- case 1：無 flock 二進位 → return 2 + ERROR log（fail-safe skip）----
# 受限 PATH 只放 date（log 時戳用），故意不放 flock。此 case 只走
# command -v 檢查分支，不觸及 {var}> 語法，故任何 bash 版本都可跑。
NOBIN="$TMP/nobin"
mkdir -p "$NOBIN"
ln -s "$(command -v date)" "$NOBIN/date"
LOCK1="$TMP/t1.lock"
LOG1="$TMP/t1.log"
rc=0
PATH="$NOBIN" "$BASH" -c 'source "$1" && acquire_cron_flock "$2" 20 "$3" "t1_lane"' _ "$LIB" "$LOCK1" "$LOG1" || rc=$?
if [[ "$rc" -eq 2 ]] && grep -q "ERROR" "$LOG1" 2>/dev/null && grep -q "flock" "$LOG1" 2>/dev/null; then
    pass "case1 無 flock 二進位 → return 2 + ERROR log（絕不無鎖硬跑）"
else
    fail "case1 rc=$rc（期望 2）；log=$(cat "$LOG1" 2>/dev/null || true)"
fi

# ---- case 6（gate）：flock 缺席 / bash 過舊 → case 2-5 與 7 自動 SKIP ----
FLOCK_OK=1
if ! command -v flock >/dev/null 2>&1; then
    FLOCK_OK=0
    skip "case2-5+7 SKIPPED：本機無 flock 二進位（如 Mac dev；Linux runtime 必有，由 E4/Linux 側補跑）"
elif (( BASH_VERSINFO[0] < 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] < 1) )); then
    FLOCK_OK=0
    skip "case2-5+7 SKIPPED：bash ${BASH_VERSION} 過舊（{var}> fd 分配語法需 >=4.1）"
fi

# start_holder <lock> <log> <lane> <ready_file> <fifo>
# 背景 holder：取鎖成功 → touch ready → 阻塞在 read builtin（不 spawn 子進程）。
# 喚醒＝向 fifo 寫一行；kill -9＝模擬 OOM SIGKILL。
HOLDER_PID=""
start_holder() {
    local lock="$1" log="$2" lane="$3" ready="$4" fifo="$5"
    (
        source "$LIB" || exit 97
        acquire_cron_flock "$lock" 20 "$log" "$lane" || exit 96
        : > "$ready"
        read -r _ < "$fifo" || true
    ) &
    HOLDER_PID=$!
    HOLDER_PIDS+=("$HOLDER_PID")
}

# wait_ready <ready_file>：等 holder 完成取鎖（上限 ~5s）。
wait_ready() {
    local ready="$1"
    for _ in $(seq 1 50); do
        [[ -f "$ready" ]] && return 0
        sleep 0.1
    done
    return 1
}

# stop_holder <pid> <fifo>：正常喚醒並收屍（僅 holder 尚存活時開 fifo 寫端，
# 避免無讀者時 open 阻塞）。
stop_holder() {
    local pid="$1" fifo="$2"
    if kill -0 "$pid" 2>/dev/null; then
        echo > "$fifo" 2>/dev/null || true
    fi
    wait "$pid" 2>/dev/null || true
}

# touch_old <file> <seconds_ago>：把 mtime 動態調舊（禁硬編日期）。
# GNU date 用 -d @epoch；BSD date 用 -r epoch。date 與 touch -t 同用本地時區。
touch_old() {
    local f="$1" ago="$2" past fmt
    past=$(( $(date +%s) - ago ))
    if fmt="$(date -d "@$past" '+%Y%m%d%H%M.%S' 2>/dev/null)"; then
        :
    elif fmt="$(date -r "$past" '+%Y%m%d%H%M.%S' 2>/dev/null)"; then
        :
    else
        return 1
    fi
    touch -t "$fmt" "$f"
}

if (( FLOCK_OK == 1 )); then
    # ---- case 2：取鎖成功 → return 0 + 鎖檔含 pid 診斷行 ----
    LOCK2="$TMP/t2.lock"
    LOG2="$TMP/t2.log"
    rc=0
    ( source "$LIB" && acquire_cron_flock "$LOCK2" 20 "$LOG2" "t2_lane" ) || rc=$?
    if [[ "$rc" -eq 0 ]] && grep -q "pid=" "$LOCK2" 2>/dev/null && grep -q "lane=t2_lane" "$LOCK2" 2>/dev/null; then
        pass "case2 取鎖成功 → return 0 + 鎖檔含 pid/lane 診斷行"
    else
        fail "case2 rc=$rc（期望 0）；lock=$(cat "$LOCK2" 2>/dev/null || true)"
    fi

    # ---- case 3：持鎖中第二取鎖 → return 1 + SKIP log；診斷行未被截斷 ----
    LOCK3="$TMP/t3.lock"; LOG3="$TMP/t3.log"; FIFO3="$TMP/t3.fifo"; READY3="$TMP/t3.ready"
    mkfifo "$FIFO3"
    start_holder "$LOCK3" "$LOG3" "t3_holder" "$READY3" "$FIFO3"
    T3_HOLDER="$HOLDER_PID"
    if ! wait_ready "$READY3"; then
        fail "case3 前置失敗：holder 未能取鎖；log=$(cat "$LOG3" 2>/dev/null || true)"
    else
        rc=0
        ( source "$LIB" && acquire_cron_flock "$LOCK3" 20 "$LOG3" "t3_second" ) || rc=$?
        if [[ "$rc" -eq 1 ]] && grep -q "SKIP" "$LOG3" 2>/dev/null && grep -q "lane=t3_holder" "$LOCK3" 2>/dev/null; then
            pass "case3 持鎖中第二取鎖 → return 1 + SKIP log + 持鎖者診斷行未被截斷"
        else
            fail "case3 rc=$rc（期望 1）；log=$(cat "$LOG3" 2>/dev/null || true)；lock=$(cat "$LOCK3" 2>/dev/null || true)"
        fi
    fi
    stop_holder "$T3_HOLDER" "$FIFO3"

    # ---- case 4：核心反疊加性質——kill -9 持鎖者 → 立即重取鎖成功 ----
    LOCK4="$TMP/t4.lock"; LOG4="$TMP/t4.log"; FIFO4="$TMP/t4.fifo"; READY4="$TMP/t4.ready"
    mkfifo "$FIFO4"
    start_holder "$LOCK4" "$LOG4" "t4_holder" "$READY4" "$FIFO4"
    T4_HOLDER="$HOLDER_PID"
    if ! wait_ready "$READY4"; then
        fail "case4 前置失敗：holder 未能取鎖；log=$(cat "$LOG4" 2>/dev/null || true)"
    else
        kill -9 "$T4_HOLDER" 2>/dev/null || true
        wait "$T4_HOLDER" 2>/dev/null || true
        rc=0
        ( source "$LIB" && acquire_cron_flock "$LOCK4" 20 "$LOG4" "t4_second" ) || rc=$?
        if [[ "$rc" -eq 0 ]] && grep -q "lane=t4_second" "$LOCK4" 2>/dev/null; then
            pass "case4 kill -9 持鎖者 → 立即重取鎖成功（kernel 關 fd 放鎖，無 stale 態）"
        else
            fail "case4 rc=$rc（期望 0）；log=$(cat "$LOG4" 2>/dev/null || true)；lock=$(cat "$LOCK4" 2>/dev/null || true)"
        fi
    fi

    # ---- case 5：長跑告警——超齡持鎖只 WARN、return 1 不搶佔 ----
    LOCK5="$TMP/t5.lock"; LOG5="$TMP/t5.log"; FIFO5="$TMP/t5.fifo"; READY5="$TMP/t5.ready"
    mkfifo "$FIFO5"
    start_holder "$LOCK5" "$LOG5" "t5_holder" "$READY5" "$FIFO5"
    T5_HOLDER="$HOLDER_PID"
    if ! wait_ready "$READY5"; then
        fail "case5 前置失敗：holder 未能取鎖；log=$(cat "$LOG5" 2>/dev/null || true)"
    elif ! touch_old "$LOCK5" 7200; then
        skip "case5 SKIPPED：本機 date/touch 不支援動態舊 mtime 構造"
    else
        rc=0
        ( source "$LIB" && acquire_cron_flock "$LOCK5" 30 "$LOG5" "t5_second" ) || rc=$?
        if [[ "$rc" -eq 1 ]] && grep -q "WARN" "$LOG5" 2>/dev/null && grep -q "NOT taking over" "$LOG5" 2>/dev/null; then
            pass "case5 超齡持鎖 → WARN 長跑觀測告警 + return 1 不搶佔"
        else
            fail "case5 rc=$rc（期望 1）；log=$(cat "$LOG5" 2>/dev/null || true)"
        fi
    fi
    stop_holder "$T5_HOLDER" "$FIFO5"

    # ---- case 7：不可寫目錄下的 lock path → return 2 + ERROR log + 呼叫方存活 ----
    # open-fail 分支（E2 P2-1）：log 檔放在可寫的 $TMP，只有鎖檔目錄不可寫，
    # 才能既觸發 open-fail 又留下 ERROR log 供斷言。root 不受 mode 500 限制 → SKIP。
    if [[ "$(id -u)" -eq 0 ]]; then
        skip "case7 SKIPPED：root 不受目錄權限限制，無法構造不可寫 lock path"
    else
        RO_DIR="$TMP/t7_ro"
        mkdir -p "$RO_DIR"
        chmod 500 "$RO_DIR"
        LOCK7="$RO_DIR/t7.lock"
        LOG7="$TMP/t7.log"
        rc=0
        out=""
        # 比照 E4 gate #3 驗法：set -euo pipefail 子 shell 內呼叫（|| 承接 rc），
        # 事後仍能印哨兵行＝open-fail 不反殺呼叫方（exec 開檔失敗 shell 存活）。
        out="$("$BASH" -c 'set -euo pipefail; source "$1"; rc=0; acquire_cron_flock "$2" 20 "$3" "t7_lane" || rc=$?; echo "SENTINEL_ALIVE rc=${rc}"' _ "$LIB" "$LOCK7" "$LOG7")" || rc=$?
        if [[ "$rc" -eq 0 ]] && [[ "$out" == *"SENTINEL_ALIVE rc=2"* ]] && grep -q "ERROR" "$LOG7" 2>/dev/null && grep -q "cannot open lock file" "$LOG7" 2>/dev/null; then
            pass "case7 不可寫 lock path → return 2 + ERROR log + set -euo pipefail 呼叫方存活"
        else
            fail "case7 rc=$rc（期望 0）out=${out}；log=$(cat "$LOG7" 2>/dev/null || true)"
        fi
        chmod 700 "$RO_DIR" 2>/dev/null || true
    fi
fi

echo "== test_cron_flock 結果：PASS=$PASS FAIL=$FAIL SKIP=$SKIP =="
if (( FAIL > 0 )); then
    exit 1
fi
exit 0

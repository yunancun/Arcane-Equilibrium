#!/usr/bin/env bash
# test_cron_oom_victim.sh — cron_oom_victim.sh 自標 OOM victim 的 standalone 自測。
#
# 跑法：bash helper_scripts/cron/tests/test_cron_oom_victim.sh
#   exit 0 = PASS（含環境性 SKIP：Mac 無 /proc/self/oom_score_adj 時 case1-4 自動跳過）
#   exit 1 = FAIL
#
# Case 一覽：
#   1. 默認值：mark_cron_oom_victim 後自身 oom_score_adj == 800（需 /proc）。
#   2. 自定值：mark_cron_oom_victim 500 → == 500（需 /proc）。
#   3. 環境覆蓋：OPENCLAW_CRON_OOM_VICTIM_SCORE=650（不傳參）→ == 650（需 /proc）。
#   4. 子孫進程繼承：mark 700 後 fork 出的 bash→cat 讀自身 == 700（需 /proc；
#      驗 oom_score_adj 跨 fork+exec 繼承 → cron spawn 的 python 子/孫全是 victim）。
#   5. fail-soft：寫入失敗（非法值被 kernel 拒／或 Mac 無 /proc）→ 函數 return 0
#      不崩、set -euo pipefail 呼叫方存活（哨兵行驗法，參照 test_cron_flock case7）。
#      本 case 不需 /proc：Mac 上正是真實 fail-soft 路徑，照跑。
#
# 紀律：不硬編日期/機器路徑。oom_score_adj 是 per-process 且 fork 繼承，故「寫」與
#   「讀回」必須在同一進程樹內完成（子 bash 內 source→mark→讀）——不能在父 harness
#   寫子 shell、再回父讀（父讀到的是父自己的值）。故 case1-4 全走單一 `bash -c`
#   內 source+mark+讀。需 /proc 的 case 由 PROC_OK 統一 gate；Mac dev 自動 SKIP。
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIB="$SCRIPT_DIR/../lib/cron_oom_victim.sh"

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

BASH="${BASH:-bash}"

# 本測不建鎖檔/背景進程，但仍給 tempdir 收容任何意外落檔並統一清理。
TMP="$(mktemp -d)" || { echo "FAIL: mktemp -d 失敗"; exit 1; }
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# /proc/self/oom_score_adj 可寫＝Linux runtime；缺席（Mac dev）時 case1-4 SKIP。
# 用 -w（不僅 -e）：既要存在也要可寫，才是「期望成功」case 的前提。
PROC_OK=0
if [[ -w /proc/self/oom_score_adj ]]; then
    PROC_OK=1
fi
if (( PROC_OK == 0 )); then
    skip "case1-4 SKIPPED：本機無可寫 /proc/self/oom_score_adj（如 Mac dev；Linux runtime 由 E4/Linux 側補跑）。case5 fail-soft 照跑（Mac 上即真實無-/proc 路徑）"
fi

# ---- case 1：默認值 → 自身 oom_score_adj == 800 ----
# 單一 bash：source lib、mark（不傳參）、再用 $(< ) 由本 bash 自身開檔讀
# /proc/self（即該 bash 進程），確保讀到的是剛被 mark 設過的同一進程的值。
if (( PROC_OK == 1 )); then
    rc=0
    val="$("$BASH" -c 'source "$1"; mark_cron_oom_victim; printf "%s" "$(< /proc/self/oom_score_adj)"' _ "$LIB")" || rc=$?
    if [[ "$rc" -eq 0 && "$val" == "800" ]]; then
        pass "case1 默認值 → 自身 oom_score_adj == 800"
    else
        fail "case1 rc=$rc val=$val（期望 800）"
    fi
fi

# ---- case 2：自定值 500 → == 500 ----
if (( PROC_OK == 1 )); then
    rc=0
    val="$("$BASH" -c 'source "$1"; mark_cron_oom_victim 500; printf "%s" "$(< /proc/self/oom_score_adj)"' _ "$LIB")" || rc=$?
    if [[ "$rc" -eq 0 && "$val" == "500" ]]; then
        pass "case2 自定值 500 → == 500"
    else
        fail "case2 rc=$rc val=$val（期望 500）"
    fi
fi

# ---- case 3：環境覆蓋 OPENCLAW_CRON_OOM_VICTIM_SCORE=650（不傳參）→ == 650 ----
if (( PROC_OK == 1 )); then
    rc=0
    val="$(OPENCLAW_CRON_OOM_VICTIM_SCORE=650 "$BASH" -c 'source "$1"; mark_cron_oom_victim; printf "%s" "$(< /proc/self/oom_score_adj)"' _ "$LIB")" || rc=$?
    if [[ "$rc" -eq 0 && "$val" == "650" ]]; then
        pass "case3 環境覆蓋 OPENCLAW_CRON_OOM_VICTIM_SCORE=650 → == 650"
    else
        fail "case3 rc=$rc val=$val（期望 650）"
    fi
fi

# ---- case 4：子孫進程繼承——mark 700 後 fork 的 bash→cat 讀自身 == 700 ----
# 內層 `bash -c "cat ..."` 是子 bash（繼承 700），cat 又是孫（繼承 700），驗
# oom_score_adj 跨 fork+exec 傳遞 → cron 標一次、python 子/孫全 victim。
if (( PROC_OK == 1 )); then
    rc=0
    val="$("$BASH" -c 'source "$1"; mark_cron_oom_victim 700; bash -c "cat /proc/self/oom_score_adj"' _ "$LIB")" || rc=$?
    val="${val//[[:space:]]/}"   # cat 帶換行，去空白再比對
    if [[ "$rc" -eq 0 && "$val" == "700" ]]; then
        pass "case4 子孫進程繼承 → fork 的 bash→cat 讀自身 == 700（fork+exec 繼承）"
    else
        fail "case4 rc=$rc val=$val（期望 700）"
    fi
fi

# ---- case 5：fail-soft——寫入失敗 → return 0 不崩 + set -euo pipefail 呼叫方存活 ----
# 傳非法值 "not_a_number"：Linux 上 kernel 拒寫（EINVAL）→ fail-soft；Mac 上
# /proc 根本不存在 → 開檔失敗 → 同一 fail-soft 路徑。兩者皆須：函數 return 0、
# 哨兵行印得出（比照 test_cron_flock case7：set -euo pipefail 子 shell 內呼叫，
# 事後仍能印哨兵行＝write 失敗不反殺呼叫方）。本 case 不 gate PROC_OK。
rc=0
out="$("$BASH" -c 'set -euo pipefail; source "$1"; mark_cron_oom_victim "not_a_number"; echo "SENTINEL_ALIVE rc=$?"' _ "$LIB")" || rc=$?
if [[ "$rc" -eq 0 && "$out" == *"SENTINEL_ALIVE rc=0"* ]]; then
    pass "case5 fail-soft：寫入失敗 → return 0 不崩 + set -euo pipefail 呼叫方存活"
else
    fail "case5 rc=$rc out=${out}（期望 rc=0 + SENTINEL_ALIVE rc=0）"
fi

echo "== test_cron_oom_victim 結果：PASS=$PASS FAIL=$FAIL SKIP=$SKIP =="
if (( FAIL > 0 )); then
    exit 1
fi
exit 0

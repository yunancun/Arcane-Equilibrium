#!/usr/bin/env bash
# cron_flock.sh — cron shell 反疊加 flock 鎖的單一接線點（正本）。
#
# MODULE_NOTE
# 模塊用途：取代各 cron shell 手寫的「mkdir-dir 鎖 + stale 超時 rmdir 清鎖照跑」
#   模式。舊模式在單輪任務真實耗時超過閾值時只清鎖、不殺舊進程，每個 cron 週期
#   淨疊一個新實例——2026-07-15 全機 OOM 風暴的主放大器（每 15min 疊一個 20-25GB
#   python，kernel OOM 連環殺 16 次）。flock 綁定的是 fd 的 open file description：
#   持鎖進程死亡（含 OOM SIGKILL——trap 根本攔不到的那種）時 kernel 關 fd 自動
#   放鎖，「stale lock」狀態結構性不可能存在，也就不再有「清 stale」這條危險路徑。
# 主要函數：acquire_cron_flock。
# 設計裁決（PM 已裁，flock 方案；不做 kill-takeover）：
#   - 不 kill-takeover：① PID 重用可誤殺無辜進程；② 任務真實耗時已超閾值
#     （實測 40min+）時，每次接手都殺掉做到一半的舊進程 → 沒有任何一輪能跑完
#     （livelock）。flock 讓慢跑自然完成，把 */15 型排程有效降頻為
#     「一輪跑完才下一輪」。
#   - 舊「stale 接手」語意廢止，換成「長跑觀測告警」：鎖被活進程持有超過
#     stale_warn_min 只 log WARN，絕不搶佔。
# 鐵則：
#   - 鎖檔常駐，任何路徑都不得 unlink/rm 鎖檔。刪檔會造成「舊持鎖者握著已刪
#     inode 上的鎖、新來者對新建檔取鎖」的雙持鎖競態——互斥直接失效。
#   - 絕不 rmdir-and-run、絕不搶佔活進程。
#   - fd 由子進程繼承是特性：python 子進程活著＝鎖活著，即使父 shell 先死，
#     互斥仍成立；子進程全滅後由 kernel 自動放鎖，無需任何 trap/清理。
# 硬邊界：只寫 <lock_file> 一行持鎖者診斷行 + <log_file> log 行；不下單、不連
#   PG/Bybit、不改 auth/risk/runtime。flock 二進位缺失時 fail-safe skip
#   （return 2），絕不無鎖硬跑。
# bash 版本：`{var}>` fd 自動分配語法需 bash >= 4.1（Linux runtime bash 5.x
#   滿足；Mac 系統 /bin/bash 3.2 只能 parse 不能執行取鎖路徑，dev 驗證走
#   tests/test_cron_flock.sh 的自動 SKIP）。

# 私有 UTC 時戳（ISO-8601、尾綴 Z 明示 UTC）：消費者腳本自帶的 ts() 有的是本地
# 時間（如 alpha wrapper）、有的是 UTC（如 cost_gate），同一 log 檔混寫時 lib 行
# 帶 Z 免 RCA 對時間軸混淆（E2 P2-2）；獨立命名亦避免與 ts() 衝突。
_cron_flock_ts() { date -u '+%Y-%m-%dT%H:%M:%SZ'; }

# 私有 log helper：log 寫失敗不得反殺主腳本（消費者都是 set -e 環境）。
_cron_flock_log() {
    local log_file="$1"
    local line="$2"
    echo "[$(_cron_flock_ts)] ${line}" >> "$log_file" 2>/dev/null || true
}

# acquire_cron_flock <lock_file> <stale_warn_min> <log_file> <lane_name>
#   return 0：取鎖成功。鎖生命週期＝本進程（含繼承 fd 的子進程）生命週期，
#             無需 trap/清理；鎖檔已被截斷重寫為持鎖者診斷行
#             （mtime＝取鎖時刻，供非持鎖者計齡）。
#   return 1：鎖被活進程持有 → 本輪 skip（反疊加）；持有超過 stale_warn_min
#             分鐘時額外 log WARN（長跑觀測告警，取代舊接手語意），仍不搶佔。
#   return 2：flock 二進位缺失或鎖檔無法開啟 → fail-safe skip（絕不無鎖硬跑）。
#   消費端慣用法：acquire_cron_flock "$LOCK_FILE" 20 "$LOG" "lane" || exit 0
#   注意：CRON_FLOCK_FD 是全域變數（bash 自動分配的 fd 號，>=10），函數內
#   不得 local——fd 必須存活到進程結束才能持鎖。
acquire_cron_flock() {
    local lock_file="$1"
    local stale_warn_min="$2"
    local log_file="$3"
    local lane_name="$4"

    if ! command -v flock >/dev/null 2>&1; then
        _cron_flock_log "$log_file" "ERROR: flock binary missing; fail-safe skip lane=${lane_name}（絕不無鎖硬跑）"
        return 2
    fi

    # append 模式開 fd、不截斷——失敗方（非持鎖者）不得清掉活持鎖者的診斷行。
    # 外層 {} 2>/dev/null 只在本行暫時靜音 stderr（開檔失敗的 bash 報錯），
    # exec 分配出的 CRON_FLOCK_FD 是永久的、不受該暫時重導向影響。
    if ! { exec {CRON_FLOCK_FD}>>"$lock_file"; } 2>/dev/null; then
        _cron_flock_log "$log_file" "ERROR: cannot open lock file: ${lock_file}; fail-safe skip lane=${lane_name}"
        return 2
    fi

    if ! flock -n "$CRON_FLOCK_FD"; then
        _cron_flock_log "$log_file" "SKIP: ${lane_name} already running (lock held): ${lock_file}"
        # 判齡：鎖檔 mtime＝持鎖者取鎖時刻（見成功路徑）。超齡只告警、絕不接手。
        if [[ -n "$(find "$lock_file" -maxdepth 0 -mmin +"$stale_warn_min" 2>/dev/null)" ]]; then
            local holder_line
            holder_line="$(head -n 1 "$lock_file" 2>/dev/null || true)"
            _cron_flock_log "$log_file" "WARN: lock held >${stale_warn_min}min by live process (holder: ${holder_line}); NOT taking over (anti-OOM-stacking)——這是長跑觀測告警，取代舊接手語意"
        fi
        exec {CRON_FLOCK_FD}>&-
        return 1
    fi

    # 取鎖成功：另開截斷式寫入持鎖者診斷行。flock 綁的是持鎖 fd 的
    # open file description，這裡另開一個短命 fd 寫同一 inode 不影響鎖；
    # 同時把 mtime 刷新為取鎖時刻，供之後的非持鎖者計齡。
    printf '[%s] pid=%s lane=%s\n' "$(_cron_flock_ts)" "$$" "$lane_name" > "$lock_file" 2>/dev/null || true
    return 0
}

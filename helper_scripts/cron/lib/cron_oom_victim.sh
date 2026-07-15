#!/usr/bin/env bash
# cron_oom_victim.sh — cron 重活進程自標 OOM victim 的單一接線點（正本）。
#
# MODULE_NOTE
# 模塊用途：讓「已取到鎖、即將跑重活」的 cron 進程主動把自己的 oom_score_adj
#   往正拉高（默認 800），使系統記憶體耗盡時 kernel OOM killer 優先殺這些 cron
#   hog、而非交易引擎 / watchdog。2026-07-15 全機 OOM 風暴實證：cron 側 python
#   （alpha_discovery_throughput.runtime_runner / cost_gate_learning_lane 全量物化
#   probe_ledger）單進程失控達 79–85GB anon-rss，free 一度剩 984MB；引擎（裸進程、
#   watchdog spawn）與 watchdog（user unit）都繼承 user manager 的
#   DefaultOOMScoreAdjust=200，16:35 引擎因 adj=200 被 OOM 連坐殺。survival>profit
#   的直接落地：OOM 時先讓 hog 死、保交易大腦活。
# 主要函數：mark_cron_oom_victim [score]。
# 權限背景（為何是「往正拉 hog」而非「往負降引擎」——後者才是理想解，但零特權辦不到）：
#   - user systemd 設 OOMScoreAdjust 被拒（Unknown assignment）——user manager 不吃
#     這個 directive，改不了引擎/watchdog 繼承的 200。
#   - choom / 寫「別的進程」的 oom_score_adj 往負（降低被殺機率）需 CAP_SYS_RESOURCE，
#     uid 1000 沒有 → 降引擎/watchdog 的 adj 只能 root 辦（operator 另辦：root 改
#     user manager DefaultOOMScoreAdjust，或把引擎轉成 system unit）。
#   - 但進程「提高自己」的 oom_score_adj（往正、更易被殺）零特權可行（實測
#     `echo 800 > /proc/self/oom_score_adj` 成功）。故本 lib 走唯一零特權可行路徑：
#     讓 hog 自標高分、恆高於引擎的 200 → OOM 時 hog 的 oom_score 恆排在引擎前面。
# 繼承特性：oom_score_adj 跨 fork + exec 繼承。cron wrapper（bash）標一次，其 spawn
#   的 python 子進程、python 再 spawn 的孫進程全部繼承同一分數 → 無需逐個標，真正
#   吃 80GB 的那個 python 也是 victim。
# 值 800 的取捨：< 1000（保留 1000 給極端 / 未來更該優先死的目標）、>> 200（引擎與
#   watchdog 繼承的 DefaultOOMScoreAdjust）。oom_score_adj 直接加進 badness 分數，
#   800 與 200 的差距足以在任何合理 RSS 配比下讓 hog 排在引擎前面。
# 可調：環境變數 OPENCLAW_CRON_OOM_VICTIM_SCORE 覆蓋默認 800（operator 便於調），
#   顯式傳參 score 又優先於 env（解析序 arg > env > 800）。非法值（非整數 / 越界
#   [-1000,1000]）會被 kernel 拒 → fail-soft 靜默 no-op（該進程當輪無保護、但不崩），
#   故 operator 調 env 後宜自行讀回 /proc/self/oom_score_adj 確認生效。
# 硬邊界：只寫本進程的 /proc/self/oom_score_adj 一行；不寫別的進程、不下單、不連
#   PG/Bybit、不碰 auth/risk/鎖/業務/排程/heartbeat/日誌。全程 fail-soft：非 Linux
#   （Mac 無 /proc/self/oom_score_adj）、/proc 不可寫、任何 write 錯誤都吞掉並
#   return 0，絕不反殺 set -euo pipefail 的呼叫方。
# 與 cron_flock.sh 互補（兩者正交、各擋一種 OOM 放大機制，缺一不可）：
#   - flock：擋「同一 lane 每 15min 疊一個新實例」的縱向疊加（反疊加鎖）。
#   - 本 lib：當單一進程自身失控吃爆記憶體（跨 lane 同時吃、或 flock 也擋不住的
#     單進程 RSS 尖峰）時，確保 OOM 連坐殺的是 hog 自己、不是無辜的交易引擎。
# 消費端慣用法（放在 acquire_cron_flock ... || exit 0 之後、業務之前；lib 缺失
#   不擋跑——少一層保護 ≠ 不能跑，與 flock 的 fail-safe-skip 語意刻意不同）：
#   OOM_VICTIM_LIB="$BASE/helper_scripts/cron/lib/cron_oom_victim.sh"
#   [[ -f "$OOM_VICTIM_LIB" ]] && source "$OOM_VICTIM_LIB" && mark_cron_oom_victim || true

# mark_cron_oom_victim [score]
#   score 解析序：顯式傳參 > 環境變數 OPENCLAW_CRON_OOM_VICTIM_SCORE > 默認 800。
#   行為：把分數寫進本進程 /proc/self/oom_score_adj，全程 fail-soft、永遠 return 0。
#   繼承：本進程之後 fork/exec 出的子孫進程全部繼承此分數（見 MODULE_NOTE）。
mark_cron_oom_victim() {
    local score="${1:-${OPENCLAW_CRON_OOM_VICTIM_SCORE:-800}}"
    # 只寫 /proc/self（自標）：往正拉高＝更易被 OOM 殺，零特權可行。用 { } 群組包住
    # 重導向再 2>/dev/null，確保「開檔失敗」訊息（非 Linux 時 bash 會對 > 目標報
    # No such file or directory）也被吞掉——裸 `> f 2>/dev/null` 因重導向先於
    # 2>/dev/null 求值會漏訊息，群組包法比照 cron_flock.sh 的 exec 開檔慣例。
    # write 失敗（非 Linux / 不可寫 / 非法值被 kernel 拒）一律吞掉，不影響業務。
    { printf '%s\n' "$score" > /proc/self/oom_score_adj; } 2>/dev/null || true
    return 0
}

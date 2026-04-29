#!/usr/bin/env bash
# cron_observer_cycle.sh — Run full observer cycle + auto-bridge to runtime snapshot
# 運行完整觀察者循環 + 自動橋接到運行時快照
#
# Add to crontab: */5 * * * * bash $OPENCLAW_SRV_ROOT/helper_scripts/cron_observer_cycle.sh >> $OPENCLAW_SRV_ROOT/log_files/observer_cron.log 2>&1
#
# OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26):
# Previous wrapper used `if $VENV ... ; then ... else echo "non-fatal" ; fi`
# which silently mapped failure exit codes to log lines while exiting 0.
# Cron then saw a "successful" cycle, masking 100% step failure for 3 days.
# Fix: drop `set -euo pipefail` (cycle non-zero now real signal) and capture
# each stage's exit code explicitly so cron + healthcheck both see truth.
# 本 ticket 修復前的 wrapper 用 `if ... ; then ... else echo "non-fatal" ; fi`
# 把失敗 exit code 默默吞成 log 文字並 exit 0，cron 看到「成功」掩蓋連續 3 天
# 100% step 失敗。修復：cycle exit code 直接代表真實狀態，wrapper 顯式捕捉
# observer + bridge 兩段 exit code 各自上報，cron + healthcheck 都看到真值。

# Note: We deliberately do NOT use `set -e` here — we want the script to run
# both observer + bridge segments even if observer fails, but we still
# return non-zero overall when any segment fails so cron sees the true state.
# 注：刻意不用 `set -e`，因為要讓 observer 失敗時仍跑 bridge（不互相阻塞）；
# 但任一段失敗整體仍 exit 1，cron 見真實狀態。
set -uo pipefail

# XP-1: Use env var with auto-detection fallback / 環境變量優先，回退自動推導
REPO="${OPENCLAW_SRV_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
# Export so observer_cycle.py + bridge subprocesses inherit it.
# OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26): cron's default cwd is
# $HOME (not REPO), so without this export observer_cycle.py's
# `OPENCLAW_SRV_ROOT="."` fallback resolves cycle JSON paths under $HOME
# instead of REPO, which cron-time but breaks healthcheck [19] reading the
# canonical path. Eagerly set here so the env propagates to all children.
# 顯式 export 讓 observer_cycle.py + bridge 子程序繼承。本 ticket 修復前 cron
# 預設 cwd 是 $HOME（非 REPO），observer_cycle.py 內 OPENCLAW_SRV_ROOT="." fallback
# 把 cycle JSON 寫到 $HOME/docker_projects/ 而非 REPO/docker_projects/，
# 導致 healthcheck [19] 讀 canonical path 看不到新鮮 JSON。
export OPENCLAW_SRV_ROOT="$REPO"
VENV="$REPO/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/python3"
OBSERVER="$REPO/program_code/exchange_connectors/bybit_connector/readonly_observer_pipeline/bybit_full_readonly_observer_cycle.py"
BRIDGE="$REPO/program_code/exchange_connectors/bybit_connector/control_api_v1/app/auto_bridge_observer_to_runtime_snapshot.py"

TS=$(date '+%Y-%m-%d %H:%M:%S')

# SW-006 (Batch E): overlap lock so 5-min cron cannot stack runs.
# SW-006（Batch E）：重疊鎖，避免 5 分鐘 cron 疊跑。
LOCK_ROOT="${OPENCLAW_DATA_DIR:-/tmp/openclaw}/locks"
LOCK_DIR="$LOCK_ROOT/cron_observer_cycle.lock.d"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    echo "[$TS] SKIP: observer cron already running (lock held)"
    exit 0
fi
release_lock() {
    rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap release_lock EXIT INT TERM

echo "[$TS] Starting observer cycle..."

# Run observer cycle. Exit code now reflects overall_ok per
# OBSERVER-PIPELINE-POST-F42FACE-CLEANUP (2026-04-26).
# observer cycle 的 exit code 自本 ticket 起代表 overall_ok 真值。
"$VENV" "$OBSERVER" 2>&1
OBSERVER_RC=$?
if [[ $OBSERVER_RC -eq 0 ]]; then
    echo "[$TS] Observer cycle complete (exit=$OBSERVER_RC)"
else
    echo "[$TS] Observer cycle FAILED (exit=$OBSERVER_RC) — investigate latest cycle JSON + healthcheck [19] observer_pipeline_alive"
fi

# Run auto-bridge if the script exists.
# 跑 auto-bridge（若檔存在）。
BRIDGE_RC=0
if [[ -f "$BRIDGE" ]]; then
    "$VENV" "$BRIDGE" 2>&1
    BRIDGE_RC=$?
    if [[ $BRIDGE_RC -eq 0 ]]; then
        echo "[$TS] Auto-bridge complete (exit=$BRIDGE_RC)"
    else
        echo "[$TS] Auto-bridge FAILED (exit=$BRIDGE_RC)"
    fi
fi

echo "[$TS] Cron cycle done"

# Aggregate exit code: any non-zero segment → wrapper exits non-zero.
# This is what cron sees in /var/log/cron + what healthcheck [19] reads
# from log_files/observer_cron.log mtime + tail.
# 彙總 exit code：任一段非零 → wrapper 整體非零。cron + healthcheck [19]
# 從 log_files/observer_cron.log 的 mtime + tail 讀此真值。
#
# TIER4-OBSERVER-LOW-1 (Tier 6 Track 1, 2026-04-26): preserve BRIDGE_RC in
# the log line when OBSERVER also fails. Previously a both-fail scenario
# would log only OBSERVER_RC and silently drop BRIDGE_RC because the early
# `exit $OBSERVER_RC` skipped the final exit line — log triage couldn't
# tell whether bridge ran or what happened. Cron exit code semantics are
# unchanged (still propagates OBSERVER_RC when non-zero, BRIDGE_RC when
# observer succeeded), but the log now surfaces the full RC pair so a
# future operator / postmortem reading observer_cron.log sees both.
# TIER4-OBSERVER-LOW-1（Tier 6 Track 1，2026-04-26）：observer 失敗時也
# 在 log 行保留 BRIDGE_RC。先前雙段都失敗時只 log OBSERVER_RC 並默默丟
# 掉 BRIDGE_RC（早 exit 跳過最後 exit 行），log triage 無法判斷 bridge
# 是否跑或結果如何。cron exit code 語意不變（observer 失敗時 propagate
# OBSERVER_RC，observer 成功時 propagate BRIDGE_RC），但 log 現在表面
# 完整 RC 對給 future operator / postmortem 讀 observer_cron.log。
if [[ $OBSERVER_RC -ne 0 ]]; then
    echo "[$TS] Cron exit aggregation: OBSERVER_RC=$OBSERVER_RC BRIDGE_RC=$BRIDGE_RC → exit $OBSERVER_RC (observer failure dominates)"
    exit $OBSERVER_RC
fi
echo "[$TS] Cron exit aggregation: OBSERVER_RC=$OBSERVER_RC BRIDGE_RC=$BRIDGE_RC → exit $BRIDGE_RC"
exit $BRIDGE_RC

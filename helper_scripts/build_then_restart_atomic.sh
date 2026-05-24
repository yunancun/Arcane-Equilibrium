#!/usr/bin/env bash
# build_then_restart_atomic.sh — 原子化 build → SHA snapshot → restart → verify
# MODULE_NOTE
# 模塊用途：把 cargo build + restart engine 包成單原子鏈，杜絕 multi-session
#   cargo race（隔壁 sub-agent 同時跑 `cargo test --release` / `cargo build` 觸
#   incremental rebuild 覆蓋同一 release binary inode，導致 `/proc/$PID/exe`
#   指向 deleted artifact，且 on-disk binary 與 process image SHA 不一致）。
# 主要函數：(無函數,單一線性 7-phase 流程)
# 依賴：flock(util-linux) / sha256sum / pgrep / restart_all.sh / cargo
# 硬邊界：
#   - 任一 phase 失敗 → set -e abort,不繼續往下;避免 partial deploy。
#   - lock 取不到立刻 exit 1,不阻塞等待（要等就由 operator 決定再試）。
#   - 不關心 API server;此 script 只負責 engine 原子 deploy。
#
# 觸發背景：
#   - PA sub-agent a6326f17 hygiene 修法 Option B（同 sprint build lock）。
#   - root cause (per memory `project_multi_session_memory_race`)：
#     QA Stage 0R / E4 regression sub-agent 在 engine startup 後 8s 觸
#     `cargo test --release` incremental rebuild,覆蓋 inode。
#   - 防範核心：deploy chain 必 atomic —
#     build → SHA snapshot → restart → verify atomic SHA equality;
#     任何階段失敗即 abort,不留 half-deployed engine。
#
# 預期使用流程（operator 下次 deploy）：
#   bash helper_scripts/build_then_restart_atomic.sh
#   → 取 lock → 拍 SHA → cargo build → 拍 SHA → restart engine（--keep-auth）→ 驗 /proc/$PID/exe SHA
#   單條命令完成原子化 deploy。
#
# 多 session 防護：
#   - flock(/tmp/openclaw/build_window.lock) 持有期間,第二 instance 立刻 exit 1。
#   - lock 在 script exit 時由 kernel 自動釋放（exec 200>FILE + flock -n 200）。
#   - 配合 `restart_all.sh --require-clean-build-window` 做雙保險:
#     即使誰繞過本 script 直接呼 restart_all.sh,只要帶 flag 也會 abort。
#
# Exit codes:
#   0  全鏈 atomic verified
#   1  任何 phase 失敗（含 lock 取不到 / build / restart / SHA mismatch）
#
# Usage:
#   bash helper_scripts/build_then_restart_atomic.sh
#   （不接 flag;atomic 流程是固定的,不開放局部覆寫）

set -euo pipefail

# ssh non-interactive 不自動 source ~/.profile / ~/.bashrc，cargo 不在 PATH。
# 為什麼：本腳本必經 ssh trade-core 觸發（Mac dev → Linux runtime atomic deploy），
# 沒有此 source 則 Phase 3 立刻 `cargo: command not found` abort。
# fail-soft：env 檔不存在則跳過（Mac dev 或無 rustup 環境會有 cargo 在 PATH，
# 此情況 source 失敗也不影響）。
if [[ -f "$HOME/.cargo/env" ]]; then
    # shellcheck disable=SC1091
    source "$HOME/.cargo/env"
fi

# ── Phase 0：路徑解析 ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
LOCK_DIR="$DATA_DIR"
LOCK_FILE="$LOCK_DIR/build_window.lock"
BINARY_PATH="$SRV_DIR/rust/target/release/openclaw-engine"

mkdir -p "$LOCK_DIR"

# ── Phase 1：取 build window lock（防 multi-session race）──
# 用 fcntl flock 而非檔案存在性 check；flock 是 kernel 級互斥,
# script 退出時 fd 自動關閉 → lock 自動釋放,不會有殘留 stale lock。
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "ERROR: another build_then_restart_atomic.sh instance is holding the build window lock" >&2
    echo "       lock file: $LOCK_FILE" >&2
    echo "       fix: wait for the other instance to finish, or inspect with 'fuser $LOCK_FILE'" >&2
    exit 1
fi

echo ">>> Phase 1: build window lock acquired (fd 200 → $LOCK_FILE)"

# ── Phase 2：pre-build SHA snapshot ──
# 為什麼：build 前先拍 SHA,後續可對照 build 是否真的產生新 binary（debug 用）。
# 不存在則記 NEW（首次建置）。
if [[ -f "$BINARY_PATH" ]]; then
    PRE_SHA=$(sha256sum "$BINARY_PATH" | awk '{print $1}')
else
    PRE_SHA="NEW"
fi
echo ">>> Phase 2: pre-build SHA = $PRE_SHA"

# ── Phase 3：cargo build release ──
# 鎖在 engine binary,避免額外觸 PyO3 / 其他 crate incremental rebuild。
echo ">>> Phase 3: cargo build --release -p openclaw_engine ..."
cd "$SRV_DIR/rust"
if ! cargo build --release -p openclaw_engine 2>&1 | tail -10; then
    echo "ERROR: cargo build failed; aborting atomic deploy" >&2
    exit 1
fi

# ── Phase 4：post-build SHA snapshot ──
# 不變量：build 成功後 binary 必存在,否則 cargo 行為異常。
if [[ ! -f "$BINARY_PATH" ]]; then
    echo "ERROR: cargo build reported success but binary missing: $BINARY_PATH" >&2
    exit 1
fi
POST_SHA=$(sha256sum "$BINARY_PATH" | awk '{print $1}')
echo ">>> Phase 4: post-build SHA = $POST_SHA"

# ── Phase 5：restart engine（帶 --require-clean-build-window 雙保險）──
# --keep-auth：原子 deploy 通常承襲 operator 已批的 live auth,不應強迫重批。
# --require-clean-build-window：restart_all.sh 入口檢查是否仍有其他 cargo 在跑,
#   若 lock 是本 script 持有但別處仍有 cargo build 進行（極少數場景）會 abort。
echo ">>> Phase 5: restart engine via restart_all.sh --engine-only --keep-auth --require-clean-build-window"
if ! bash "$SCRIPT_DIR/restart_all.sh" --engine-only --keep-auth --require-clean-build-window; then
    echo "ERROR: restart_all.sh failed; engine state unclear, manual inspection required" >&2
    exit 1
fi

# ── Phase 6：verify /proc/$PID/exe SHA == post-build SHA ──
# 為什麼 5s sleep：restart_all.sh 已等過 readiness gate,但 PID 寫入 / proc fs
# 反映需要極短延遲。實測 5s 足夠;若 readiness 已 PASS 通常 1-2s 就 OK。
sleep 5
NEW_PID=$(pgrep -f 'target/release/openclaw-engine' | head -1 || true)
if [[ -z "$NEW_PID" ]]; then
    echo "ERROR: Phase 6 — no openclaw-engine process detected after restart" >&2
    exit 1
fi
echo ">>> Phase 6: new engine PID = $NEW_PID"

# Linux 才有 /proc/$PID/exe;Mac 沒有 procfs,verify 降級為純 disk SHA 對照。
if [[ -L "/proc/$NEW_PID/exe" ]]; then
    PROC_EXE_LINK=$(readlink "/proc/$NEW_PID/exe" 2>&1 || true)
    if [[ "$PROC_EXE_LINK" == *"(deleted)"* ]]; then
        echo "ERROR: Phase 6 — /proc/$NEW_PID/exe link shows (deleted) → multi-session race condition triggered post-restart" >&2
        echo "       link target: $PROC_EXE_LINK" >&2
        exit 1
    fi
    PROC_SHA=$(sha256sum "/proc/$NEW_PID/exe" | awk '{print $1}')
    if [[ "$PROC_SHA" != "$POST_SHA" ]]; then
        echo "ERROR: Phase 6 — SHA mismatch between running process and on-disk binary" >&2
        echo "       proc SHA = $PROC_SHA" >&2
        echo "       disk SHA = $POST_SHA" >&2
        exit 1
    fi
    echo ">>> Phase 6: /proc/$NEW_PID/exe SHA == post-build SHA == $PROC_SHA"
else
    # Mac dev path：無 procfs;只能驗 disk binary SHA 不變（沒被偷換）。
    DISK_SHA_NOW=$(sha256sum "$BINARY_PATH" | awk '{print $1}')
    if [[ "$DISK_SHA_NOW" != "$POST_SHA" ]]; then
        echo "ERROR: Phase 6 (mac path) — disk binary SHA changed after restart" >&2
        echo "       post-build SHA = $POST_SHA" >&2
        echo "       current SHA    = $DISK_SHA_NOW" >&2
        exit 1
    fi
    echo ">>> Phase 6 (mac path, no /proc): disk SHA stable = $DISK_SHA_NOW"
fi

# ── Phase 7：summary + lock 自動釋放 ──
# flock fd 200 在 script exit 時由 kernel 釋放（exec 200> 持有的 fd）。
echo ">>> DEPLOY-ATOMIC-VERIFIED: NEW_PID=$NEW_PID POST_SHA=$POST_SHA"
echo ">>> build window lock will release on exit"
exit 0

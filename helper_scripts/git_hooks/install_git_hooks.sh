#!/usr/bin/env bash
# install_git_hooks.sh — 把版控內的 git hook 裝進 .git/hooks/（P2-OPS-2-GITLEAKS）
#
# MODULE_NOTE
# 模塊用途：把 helper_scripts/git_hooks/pre-commit 複製進本 repo 的
#   .git/hooks/pre-commit 並 chmod +x。.git/hooks/ 不入版控，所以 canonical
#   hook 放版控、用本 installer 落地。鏡像 helper_scripts/systemd/install_*.sh
#   與 helper_scripts/cron/install_*.sh 的風格（set -euo pipefail / [install][OK|FAIL|WARN]
#   前綴 / refuse 無聲覆蓋 / 退出碼分級）。
# 依賴：git（用 rev-parse 定位 repo，不硬編碼路徑）；cp / chmod。
# 硬邊界：
#   - 只動本 repo 的 .git/hooks/pre-commit；不裝 gitleaks 本體、不改其他檔。
#   - 既有 .git/hooks/pre-commit 非本 repo 管理版本時，refuse 無聲覆蓋：
#     backup 成 .pre-commit.bak 後再裝；除非加 --force 顯式覆寫。
#   - 跨平台：用 git rev-parse 解析 .git 目錄；不假設 /Users 或 /home 路徑。
#
# 使用：
#   bash helper_scripts/git_hooks/install_git_hooks.sh           # 裝；遇衝突會 refuse
#   bash helper_scripts/git_hooks/install_git_hooks.sh --force   # 強制覆寫既有 hook

set -euo pipefail

FORCE=0
for arg in "$@"; do
    case "$arg" in
        --force) FORCE=1 ;;
        -h|--help)
            echo "用法：bash helper_scripts/git_hooks/install_git_hooks.sh [--force]"
            echo "  --force  覆寫既有 .git/hooks/pre-commit（預設遇非本 repo 版本會 refuse + backup）"
            exit 0
            ;;
        *)
            echo "[install][FAIL] 未知參數：$arg（僅支援 --force / --help）" >&2
            exit 2
            ;;
    esac
done

# ----- 定位 repo root 與 .git/hooks（用 git rev-parse，不硬編碼路徑）-----
if ! command -v git >/dev/null 2>&1; then
    echo "[install][FAIL] 找不到 git；無法定位 .git/hooks/。" >&2
    exit 3
fi

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$REPO_ROOT" ]]; then
    echo "[install][FAIL] 不在 git work tree 內（git rev-parse --show-toplevel 無輸出）。" >&2
    echo "[install][FAIL] 請在 repo 內跑本 installer。" >&2
    exit 4
fi

# --git-dir 可能是相對路徑（相對 cwd）；用 -C "$REPO_ROOT" 取得相對 repo root 的值再正規化。
GIT_DIR_RAW="$(git -C "$REPO_ROOT" rev-parse --git-dir 2>/dev/null || true)"
if [[ -z "$GIT_DIR_RAW" ]]; then
    echo "[install][FAIL] 無法解析 .git 目錄（git rev-parse --git-dir 無輸出）。" >&2
    exit 4
fi
if [[ "$GIT_DIR_RAW" = /* ]]; then
    GIT_DIR="$GIT_DIR_RAW"
else
    GIT_DIR="$REPO_ROOT/$GIT_DIR_RAW"
fi

HOOKS_DIR="$GIT_DIR/hooks"
SRC_HOOK="$REPO_ROOT/helper_scripts/git_hooks/pre-commit"
DEST_HOOK="$HOOKS_DIR/pre-commit"

# ----- 來源 hook 必須存在 -----
if [[ ! -f "$SRC_HOOK" ]]; then
    echo "[install][FAIL] 來源 hook 不存在：$SRC_HOOK" >&2
    exit 5
fi

mkdir -p "$HOOKS_DIR"

echo "[install] repo root  = $REPO_ROOT"
echo "[install] hooks dir   = $HOOKS_DIR"
echo "[install] source hook = $SRC_HOOK"
echo "[install] dest hook   = $DEST_HOOK"

# ----- 衝突處理：既有 pre-commit 是否本 repo 管理版本？-----
# 用「內容是否與來源一致」判定是否本 repo 版本。
# - 一致 → 已裝對版本，直接重裝（idempotent，無害）。
# - 不一致 → 是 operator 自訂 / 他來源 hook：
#     --force → backup 成 .pre-commit.bak 後覆寫；
#     否則    → refuse + 提示，避免無聲覆蓋 operator 既有 hook。
if [[ -e "$DEST_HOOK" ]]; then
    if cmp -s "$SRC_HOOK" "$DEST_HOOK"; then
        echo "[install] 既有 .git/hooks/pre-commit 與來源一致；重裝（idempotent）。"
    else
        if [[ "$FORCE" -eq 1 ]]; then
            BAK="$HOOKS_DIR/.pre-commit.bak"
            cp -p "$DEST_HOOK" "$BAK"
            echo "[install][WARN] 既有 pre-commit 非本 repo 版本；已 backup 至 $BAK 後覆寫（--force）。" >&2
        else
            echo "[install][FAIL] 既有 .git/hooks/pre-commit 非本 repo 管理版本（內容不一致）。" >&2
            echo "[install][FAIL] 為避免無聲覆蓋你的自訂 hook，已 refuse。" >&2
            echo "[install][FAIL] 確認可覆寫後重跑：bash helper_scripts/git_hooks/install_git_hooks.sh --force" >&2
            echo "[install][FAIL]   （--force 會先 backup 成 $HOOKS_DIR/.pre-commit.bak）" >&2
            exit 6
        fi
    fi
fi

# ----- 落地 + 可執行位 -----
cp "$SRC_HOOK" "$DEST_HOOK"
chmod +x "$DEST_HOOK"

echo "[install][OK] 已安裝 pre-commit secret-scan hook → $DEST_HOOK"
echo ""
if command -v gitleaks >/dev/null 2>&1; then
    echo "[install][OK] 偵測到 gitleaks（$(command -v gitleaks)）；commit 時會掃 staged diff。"
else
    echo "[install][WARN] gitleaks 未安裝；hook 已就位但 commit 時會 SKIP 掃描並印 WARN。" >&2
    echo "[install][WARN] 安裝：brew install gitleaks  或  https://github.com/gitleaks/gitleaks" >&2
fi
echo ""
echo "[install][DONE]"

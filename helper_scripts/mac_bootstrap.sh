#!/usr/bin/env bash
# mac_bootstrap.sh — macOS (Apple Silicon) 冷裝引導腳本
# MODULE_NOTE (CN): Linux→macOS 遷移時一鍵裝依賴 / 建 runtime / 寫 .zshrc patch。
#   搭配 docs/references/2026-04-20--cross_platform_redeploy_dependencies.md。
#   三段式獨立旗標：--check（只讀）/ --install-deps / --init-runtime。
#   無旗標時印 usage。每段可各自跑，不會互相干擾。
# MODULE_NOTE (EN): macOS cold-bootstrap companion to the cross-platform redeploy
#   reference doc. Three independent phases: --check (read-only diagnostic),
#   --install-deps (brew + rustup + pip), --init-runtime (env dirs + .zshrc).
#   No-flag invocation prints usage. Safe to re-run each phase.
#
# Usage:
#   bash helper_scripts/mac_bootstrap.sh --check         # 只診斷，不動手
#   bash helper_scripts/mac_bootstrap.sh --install-deps  # brew + rustup + pip
#   bash helper_scripts/mac_bootstrap.sh --init-runtime  # runtime dir + zshrc patch
#   bash helper_scripts/mac_bootstrap.sh --all           # 依序跑三段
#
# 旗標（flags）可組合：
#   --all                          # check → install-deps → init-runtime
#   --no-ollama                    # install-deps 時跳過 Ollama（適用低記憶體 Mac）
#   --no-postgres                  # install-deps 時跳過 postgresql@16（走 Docker 路徑時）
#   --venv-name <name>             # 指定 venv 目錄名（預設 mac_dev）
#   --zshrc-path <path>            # 指定 .zshrc（預設 $HOME/.zshrc）
#   --yes                          # init-runtime 不互動確認

set -euo pipefail

# ───────────────────────────────────────────────────────────────
# 可配置參數（env var 覆蓋）
# ───────────────────────────────────────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VENV_NAME="${MAC_BOOTSTRAP_VENV_NAME:-mac_dev}"
ZSHRC_PATH="${MAC_BOOTSTRAP_ZSHRC:-$HOME/.zshrc}"
DEFAULT_OC_DATA_DIR="$HOME/.openclaw_runtime"
DEFAULT_OC_BASE_DIR="$REPO_ROOT"
DEFAULT_OC_SECRETS_DIR="$REPO_ROOT/settings/secret_files/bybit"

DO_CHECK=0
DO_INSTALL=0
DO_INIT=0
SKIP_OLLAMA=0
SKIP_POSTGRES=0
NONINTERACTIVE=0

# ───────────────────────────────────────────────────────────────
# 顏色輸出（TTY only）
# ───────────────────────────────────────────────────────────────
if [ -t 1 ]; then
    C_RED=$'\033[31m'; C_GRN=$'\033[32m'; C_YLW=$'\033[33m'; C_BLU=$'\033[34m'; C_DIM=$'\033[2m'; C_RST=$'\033[0m'
else
    C_RED=''; C_GRN=''; C_YLW=''; C_BLU=''; C_DIM=''; C_RST=''
fi

info()  { echo "${C_BLU}[INFO]${C_RST} $*"; }
ok()    { echo "${C_GRN}[ OK ]${C_RST} $*"; }
warn()  { echo "${C_YLW}[WARN]${C_RST} $*"; }
fail()  { echo "${C_RED}[FAIL]${C_RST} $*"; }
head1() { echo; echo "${C_BLU}━━━ $* ━━━${C_RST}"; }

# ───────────────────────────────────────────────────────────────
# Usage
# ───────────────────────────────────────────────────────────────
usage() {
    cat <<'EOF'
mac_bootstrap.sh — macOS (Apple Silicon) 冷裝引導腳本

Usage:
  bash helper_scripts/mac_bootstrap.sh [flags]

Phases (組合或單獨跑):
  --check              只診斷當前系統已裝 / 未裝什麼（不動手）
  --install-deps       安裝 brew 套件 + rustup + Python venv + pip install
  --init-runtime       建 $OPENCLAW_DATA_DIR、清舊 socket、寫 .zshrc env 段
  --all                依序跑 --check → --install-deps → --init-runtime

Options:
  --no-ollama          跳過 Ollama 安裝（低記憶體 Mac / 不跑 LLM）
  --no-postgres        跳過 postgresql@16（改走 Docker timescaledb）
  --venv-name <name>   Python venv 目錄名（預設：mac_dev）
  --zshrc-path <path>  .zshrc 路徑（預設：$HOME/.zshrc）
  --yes                init-runtime 不互動確認
  -h, --help           這段說明

完整文件：docs/references/2026-04-20--cross_platform_redeploy_dependencies.md
EOF
}

# ───────────────────────────────────────────────────────────────
# 旗標解析
# ───────────────────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    usage
    exit 0
fi

while [ $# -gt 0 ]; do
    case "$1" in
        --check)         DO_CHECK=1 ;;
        --install-deps)  DO_INSTALL=1 ;;
        --init-runtime)  DO_INIT=1 ;;
        --all)           DO_CHECK=1; DO_INSTALL=1; DO_INIT=1 ;;
        --no-ollama)     SKIP_OLLAMA=1 ;;
        --no-postgres)   SKIP_POSTGRES=1 ;;
        --venv-name)     VENV_NAME="$2"; shift ;;
        --zshrc-path)    ZSHRC_PATH="$2"; shift ;;
        --yes)           NONINTERACTIVE=1 ;;
        -h|--help)       usage; exit 0 ;;
        *)               fail "未知旗標: $1"; usage; exit 2 ;;
    esac
    shift
done

# ───────────────────────────────────────────────────────────────
# 平台守衛：僅 macOS
# ───────────────────────────────────────────────────────────────
if [ "$(uname -s)" != "Darwin" ]; then
    fail "此腳本只適用 macOS。當前系統：$(uname -s)"
    fail "Linux 部署使用 helper_scripts/restart_all.sh。"
    exit 1
fi

ARCH="$(uname -m)"
if [ "$ARCH" != "arm64" ]; then
    warn "偵測到非 Apple Silicon 架構：$ARCH（預期 arm64）"
    warn "Intel Mac 可繼續，但需額外 rustup target add x86_64-apple-darwin"
fi

# ───────────────────────────────────────────────────────────────
# Phase 1 — diagnostic check（--check）
# ───────────────────────────────────────────────────────────────
phase_check() {
    head1 "Phase 1: 系統診斷"

    # Xcode CLT
    if xcode-select -p >/dev/null 2>&1; then
        ok "Xcode Command Line Tools 已安裝（$(xcode-select -p)）"
    else
        warn "Xcode Command Line Tools 未安裝 → 需跑 xcode-select --install"
    fi

    # Homebrew
    if command -v brew >/dev/null 2>&1; then
        ok "Homebrew 已安裝（$(brew --version | head -1)）"
        BREW_OK=1
    else
        fail "Homebrew 未安裝 → 見 https://brew.sh"
        BREW_OK=0
    fi

    # Rust
    if command -v rustc >/dev/null 2>&1; then
        ok "Rust 已安裝（$(rustc --version)）"
        if rustup target list --installed 2>/dev/null | grep -q aarch64-apple-darwin; then
            ok "  target aarch64-apple-darwin 已安裝"
        else
            warn "  target aarch64-apple-darwin 未安裝 → rustup target add aarch64-apple-darwin"
        fi
    else
        fail "Rust 未安裝 → 需 brew install rustup-init && rustup-init -y"
    fi

    # Python
    if command -v python3.12 >/dev/null 2>&1; then
        ok "Python 3.12 已安裝（$(python3.12 --version)）"
    elif command -v python3 >/dev/null 2>&1; then
        PYVER="$(python3 --version 2>&1 | awk '{print $2}')"
        case "$PYVER" in
            3.12*|3.13*) ok "Python ${PYVER} 可用（python3 指向）" ;;
            *)           warn "Python ${PYVER}（需要 3.12+）→ brew install python@3.12" ;;
        esac
    else
        fail "Python 未安裝 → brew install python@3.12"
    fi

    # Ollama
    if command -v ollama >/dev/null 2>&1; then
        ok "Ollama 已安裝（$(ollama --version 2>&1 | head -1)）"
    else
        warn "Ollama 未安裝 → brew install ollama（可選，跳過則啟發式降級）"
    fi

    # PostgreSQL
    if command -v psql >/dev/null 2>&1; then
        ok "PostgreSQL client 已安裝（$(psql --version)）"
    else
        warn "PostgreSQL 未安裝 → brew install postgresql@16 或走 Docker 路徑"
    fi

    # Docker
    if command -v docker >/dev/null 2>&1; then
        ok "Docker 已安裝（$(docker --version)）"
    else
        warn "Docker 未安裝 → brew install --cask docker（可選，跑測試容器時需要）"
    fi

    # Git
    if command -v git >/dev/null 2>&1; then
        ok "Git 已安裝（$(git --version)）"
    else
        fail "Git 未安裝 → brew install git"
    fi

    # Runtime 目錄狀態
    head1 "Runtime 目錄狀態"
    if [ -d "${OPENCLAW_DATA_DIR:-$DEFAULT_OC_DATA_DIR}" ]; then
        ok "OPENCLAW_DATA_DIR 存在：${OPENCLAW_DATA_DIR:-$DEFAULT_OC_DATA_DIR}"
        local STALE
        STALE=$(ls "${OPENCLAW_DATA_DIR:-$DEFAULT_OC_DATA_DIR}"/*.sock 2>/dev/null | wc -l | tr -d ' ')
        if [ "$STALE" -gt 0 ]; then
            warn "  有 $STALE 個舊 socket 殘留 → init-runtime 會清"
        fi
        if [ -f "${OPENCLAW_DATA_DIR:-$DEFAULT_OC_DATA_DIR}/engine_maintenance.flag" ]; then
            warn "  engine_maintenance.flag 存在 → init-runtime 會清"
        fi
    else
        warn "OPENCLAW_DATA_DIR 不存在：${OPENCLAW_DATA_DIR:-$DEFAULT_OC_DATA_DIR}"
    fi

    # .zshrc env 段
    if grep -q "OPENCLAW_DATA_DIR" "$ZSHRC_PATH" 2>/dev/null; then
        ok ".zshrc 已有 OPENCLAW_* env 段"
    else
        warn ".zshrc 無 OPENCLAW_* env 段 → init-runtime 會追加"
    fi

    echo
    info "診斷完成。若全綠，可直接 --init-runtime；若有 warn/fail，跑 --install-deps。"
}

# ───────────────────────────────────────────────────────────────
# Phase 2 — install dependencies（--install-deps）
# ───────────────────────────────────────────────────────────────
phase_install_deps() {
    head1 "Phase 2: 安裝依賴"

    # Xcode CLT
    if ! xcode-select -p >/dev/null 2>&1; then
        info "觸發 Xcode Command Line Tools 安裝（會彈 GUI 對話框）"
        xcode-select --install || true
        warn "請完成 GUI 安裝後再繼續。按 Enter 繼續..."
        [ "$NONINTERACTIVE" -eq 0 ] && read -r _
    fi

    # Homebrew
    if ! command -v brew >/dev/null 2>&1; then
        fail "Homebrew 未安裝。請先跑："
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
        exit 1
    fi

    # brew 套件
    info "安裝核心 brew 套件..."
    brew install git python@3.12 rustup-init

    if [ "$SKIP_POSTGRES" -eq 0 ]; then
        info "安裝 postgresql@16..."
        brew install postgresql@16
    else
        info "跳過 postgresql（--no-postgres）"
    fi

    if [ "$SKIP_OLLAMA" -eq 0 ]; then
        info "安裝 Ollama..."
        brew install ollama
    else
        info "跳過 Ollama（--no-ollama）"
    fi

    # Rust toolchain
    if ! command -v rustc >/dev/null 2>&1; then
        info "初始化 rustup..."
        rustup-init -y --default-toolchain stable
        # 載入 cargo env（當前 shell session）
        # shellcheck disable=SC1091
        [ -f "$HOME/.cargo/env" ] && source "$HOME/.cargo/env"
    fi
    rustup component add rustfmt clippy
    rustup target add aarch64-apple-darwin
    ok "Rust toolchain 就緒（$(rustc --version)）"

    # Python venv + pip
    local VENV_DIR="$REPO_ROOT/venvs/$VENV_NAME"
    if [ ! -d "$VENV_DIR" ]; then
        info "建立 Python venv: $VENV_DIR"
        python3.12 -m venv "$VENV_DIR"
    else
        info "Python venv 已存在：$VENV_DIR"
    fi
    # shellcheck disable=SC1091
    source "$VENV_DIR/bin/activate"
    pip install --quiet --upgrade pip wheel
    info "安裝 requirements-ml.txt..."
    pip install -r "$REPO_ROOT/requirements-ml.txt"

    local CONTROL_API_REQ="$REPO_ROOT/program_code/exchange_connectors/bybit_connector/control_api_v1/requirements.txt"
    if [ -f "$CONTROL_API_REQ" ]; then
        info "安裝 control_api_v1 requirements..."
        pip install -r "$CONTROL_API_REQ"
    else
        warn "未找到 ${CONTROL_API_REQ}，跳過"
    fi
    deactivate
    ok "Python venv 就緒（${VENV_DIR}）"

    head1 "Phase 2 完成"
    info "下一步：bash helper_scripts/mac_bootstrap.sh --init-runtime"
}

# ───────────────────────────────────────────────────────────────
# Phase 3 — init runtime（--init-runtime）
# ───────────────────────────────────────────────────────────────
phase_init_runtime() {
    head1 "Phase 3: 初始化 Runtime"

    local OC_DATA_DIR="${OPENCLAW_DATA_DIR:-$DEFAULT_OC_DATA_DIR}"
    local OC_BASE_DIR="${OPENCLAW_BASE_DIR:-$DEFAULT_OC_BASE_DIR}"
    local OC_SECRETS_DIR="${OPENCLAW_SECRETS_DIR:-$DEFAULT_OC_SECRETS_DIR}"

    info "將建立 runtime 目錄：$OC_DATA_DIR"
    info "將寫入 env 段到：    $ZSHRC_PATH"

    if [ "$NONINTERACTIVE" -eq 0 ]; then
        echo -n "${C_YLW}確認？ [y/N] ${C_RST}"
        read -r ANS
        case "$ANS" in
            y|Y|yes|YES) ;;
            *) info "取消"; exit 0 ;;
        esac
    fi

    # 建 runtime 目錄
    mkdir -p "$OC_DATA_DIR"
    ok "目錄已建：$OC_DATA_DIR"

    # 清舊 socket / maintenance flag
    local CLEANED=0
    for f in "$OC_DATA_DIR"/*.sock "$OC_DATA_DIR/engine_maintenance.flag"; do
        if [ -e "$f" ]; then
            rm -f "$f"
            CLEANED=$((CLEANED + 1))
        fi
    done
    if [ "$CLEANED" -gt 0 ]; then
        ok "清理舊檔 $CLEANED 個"
    else
        info "無舊檔需清"
    fi

    # .zshrc env 段（idempotent：有 marker 就跳過）
    local MARKER_BEGIN="# >>> OpenClaw Mac bootstrap >>>"
    local MARKER_END="# <<< OpenClaw Mac bootstrap <<<"

    if grep -qF "$MARKER_BEGIN" "$ZSHRC_PATH" 2>/dev/null; then
        info ".zshrc 已有 OpenClaw env 段（marker 偵測到），跳過寫入"
        info "若要更新，手動編輯 $ZSHRC_PATH 的 $MARKER_BEGIN 區塊"
    else
        info "追加 env 段到 $ZSHRC_PATH"
        # 保險：不存在則建立
        touch "$ZSHRC_PATH"
        cat >>"$ZSHRC_PATH" <<EOF

$MARKER_BEGIN
# 由 helper_scripts/mac_bootstrap.sh 於 $(date '+%Y-%m-%d %H:%M:%S') 追加
# 詳見 docs/references/2026-04-20--cross_platform_redeploy_dependencies.md
export OPENCLAW_BASE_DIR="$OC_BASE_DIR"
export OPENCLAW_DATA_DIR="$OC_DATA_DIR"
export OPENCLAW_SECRETS_DIR="$OC_SECRETS_DIR"

# 別名：清舊 socket / maintenance flag
alias oc-clean-runtime='rm -f "\$OPENCLAW_DATA_DIR"/*.sock "\$OPENCLAW_DATA_DIR/engine_maintenance.flag"'

# Live Mainnet 硬鎖（只在真實部署時打開，見 CLAUDE.md §四）
# export OPENCLAW_ALLOW_MAINNET=1

# Paper pipeline（預設關閉，見 project_paper_pipeline_disabled_by_default）
# export OPENCLAW_ENABLE_PAPER=1

# IPC HMAC secret（Python↔Rust 綁定契約，Linux↔Mac 必須同值或重簽 authorization.json）
# export OPENCLAW_IPC_SECRET="<與 Linux 同一值>"
$MARKER_END
EOF
        ok ".zshrc env 段已追加"
        warn "須重新載入 shell：source $ZSHRC_PATH"
    fi

    head1 "Phase 3 完成"
    cat <<EOF

下一步：
  1. ${C_BLU}source "$ZSHRC_PATH"${C_RST}                              # 載入新 env
  2. ${C_BLU}cd "$REPO_ROOT/rust" && cargo build --release${C_RST}     # 構建引擎
  3. ${C_BLU}source "$REPO_ROOT/venvs/$VENV_NAME/bin/activate"${C_RST} # 啟用 Python venv
  4. ${C_BLU}bash helper_scripts/restart_all.sh --rebuild${C_RST}      # 啟動服務

若是從 Linux 主機遷移 live 憑證：${C_YLW}authorization.json 不能直接 cp${C_RST}
  → 須在 Mac 上 Python 啟動後走 /api/v1/system/approve_live_authorization 路由重簽
  → 詳見 docs/references/2026-04-20--cross_platform_redeploy_dependencies.md §7
EOF
}

# ───────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────
[ "$DO_CHECK"   -eq 1 ] && phase_check
[ "$DO_INSTALL" -eq 1 ] && phase_install_deps
[ "$DO_INIT"    -eq 1 ] && phase_init_runtime

exit 0

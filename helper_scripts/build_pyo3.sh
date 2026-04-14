#!/usr/bin/env bash
# MODULE_NOTE (CN): 統一自動化 PyO3 (.so) 部署到所有專案 venv。
#   - 修復 Rust struct 改動後需手動 maturin develop 到多個 venv 的問題。
#   - 預設雙寫：~/.venv（系統預設）+ control_api_v1/.venv（API server）。
#   - 使用 maturin build 生成 wheel + pip install --force-reinstall，
#     比逐個 venv 跑 maturin develop 更乾淨且免重複編譯。
# MODULE_NOTE (EN): Unified PyO3 (.so) build+deploy to all project venvs.
#   - Fixes manual per-venv `maturin develop` after Rust struct changes.
#   - Default dual-write: ~/.venv (system default) + control_api_v1/.venv (API server).
#   - Builds wheel once via `maturin build` + `pip install --force-reinstall`,
#     cleaner and avoids duplicate compilation vs per-venv `maturin develop`.
#
# Usage:
#   ./helper_scripts/build_pyo3.sh                 # dual-write (release)
#   ./helper_scripts/build_pyo3.sh --debug         # debug profile
#   ./helper_scripts/build_pyo3.sh --venv <path>   # single-target mode
#   ./helper_scripts/build_pyo3.sh -n              # dry-run (show plan, no action)
#   ./helper_scripts/build_pyo3.sh --help          # show help
#
# Exit codes:
#   0  success
#   1  usage / arg error
#   2  build failure (maturin build)
#   3  install failure (pip install)
#   4  verification failure (.so missing or size mismatch)

set -euo pipefail

# ── Cross-platform bash guard / 跨平台 bash 保護 ──
# 要求 bash 4+ (macOS 預設 3.2，需 brew install bash 或 /opt/homebrew/bin/bash)
if [[ -z "${BASH_VERSION:-}" ]]; then
    echo "ERROR: must run under bash (not sh/dash)" >&2
    exit 1
fi

# ── Resolve project root / 解析專案根目錄 ──
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYO3_CRATE_DIR="${PROJECT_ROOT}/rust/openclaw_pyo3"
MODULE_NAME="openclaw_core"

# ── Default target venvs / 預設目標 venv 列表 ──
DEFAULT_VENVS=(
    "${HOME}/.venv"
    "${PROJECT_ROOT}/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv"
)

# ── Parse flags / 解析旗標 ──
PROFILE="release"
SINGLE_VENV=""
DRY_RUN=0
SHOW_HELP=0

show_help() {
    cat <<'EOF'
build_pyo3.sh — Unified PyO3 build+deploy / 統一 PyO3 建構部署

Usage:
  build_pyo3.sh [--release|--debug] [--venv <path>] [-n|--dry-run] [--help]

Options:
  --release        Build in release profile (default / 預設)
  --debug          Build in debug profile (faster compile, slower runtime)
  --venv <path>    Install into a single venv only; bypasses dual-write.
                   單一 venv 安裝，繞過雙寫預設。
  -n, --dry-run    Show planned actions without executing. / 僅顯示計劃，不執行。
  -h, --help       Show this help. / 顯示說明。

Default dual-write targets / 預設雙寫目標：
  ~/.venv
  <project>/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv

Exit codes: 0 ok | 1 args | 2 build | 3 install | 4 verify
EOF
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --release)    PROFILE="release"; shift ;;
        --debug)      PROFILE="debug"; shift ;;
        --venv)
            if [[ $# -lt 2 ]]; then
                echo "ERROR: --venv requires a path argument" >&2
                exit 1
            fi
            SINGLE_VENV="$2"
            shift 2
            ;;
        -n|--dry-run) DRY_RUN=1; shift ;;
        -h|--help)    SHOW_HELP=1; shift ;;
        *)
            echo "ERROR: unknown argument: $1" >&2
            show_help >&2
            exit 1
            ;;
    esac
done

if [[ "${SHOW_HELP}" -eq 1 ]]; then
    show_help
    exit 0
fi

# ── Log helpers / 日誌工具 ──
log()  { echo "[build_pyo3] $*"; }
warn() { echo "[build_pyo3][WARN] $*" >&2; }
err()  { echo "[build_pyo3][ERROR] $*" >&2; }

# ── Resolve target venvs / 解析目標 venv ──
# NOTE: we include any venv that actually has a python3 binary, whether it
#       already contains openclaw_core or not (fresh installs supported).
# 注意：保留 python3 存在的 venv 即可，不要求已有 openclaw_core（支援全新安裝）。
if [[ -n "${SINGLE_VENV}" ]]; then
    TARGET_VENVS=("${SINGLE_VENV}")
else
    TARGET_VENVS=("${DEFAULT_VENVS[@]}")
fi

# ── Validate venvs / 驗證 venv 路徑 ──
validate_venv() {
    local venv="$1"
    local py="${venv}/bin/python3"
    if [[ ! -x "${py}" ]]; then
        err "venv python3 not found: ${py}"
        return 1
    fi
    return 0
}

# ── Locate maturin / 定位 maturin ──
# 優先：control_api_v1/.venv/bin/maturin (較可能為最新)；退回 PATH 中的 maturin。
MATURIN_BIN=""
CANDIDATE_MATURIN=(
    "${PROJECT_ROOT}/program_code/exchange_connectors/bybit_connector/control_api_v1/.venv/bin/maturin"
    "${HOME}/.venv/bin/maturin"
    "${HOME}/.cargo/bin/maturin"
)
for m in "${CANDIDATE_MATURIN[@]}"; do
    if [[ -x "${m}" ]]; then
        MATURIN_BIN="${m}"
        break
    fi
done
if [[ -z "${MATURIN_BIN}" ]]; then
    if command -v maturin >/dev/null 2>&1; then
        MATURIN_BIN="$(command -v maturin)"
    fi
fi
if [[ -z "${MATURIN_BIN}" ]]; then
    err "maturin not found. Install via: pip install maturin (or cargo install maturin)."
    exit 2
fi

# ── Build plan summary / 計劃摘要 ──
log "PROJECT_ROOT = ${PROJECT_ROOT}"
log "PyO3 crate    = ${PYO3_CRATE_DIR}"
log "Module name   = ${MODULE_NAME}"
log "Profile       = ${PROFILE}"
log "Maturin       = ${MATURIN_BIN}"
log "Target venvs:"
for v in "${TARGET_VENVS[@]}"; do
    log "  - ${v}"
done

# ── Dry-run short-circuit / Dry-run 提前退出 ──
if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "DRY-RUN: would validate venvs, build wheel, pip install --force-reinstall, verify .so."
    for v in "${TARGET_VENVS[@]}"; do
        if validate_venv "${v}"; then
            log "  venv OK: ${v}"
        else
            warn "  venv INVALID: ${v}"
        fi
    done
    log "DRY-RUN complete. No changes made."
    exit 0
fi

# ── Pre-validate every target venv before doing work / 執行前先全部驗證 ──
for v in "${TARGET_VENVS[@]}"; do
    if ! validate_venv "${v}"; then
        err "abort: invalid venv ${v}"
        exit 1
    fi
done

# ── Build wheel / 建構 wheel ──
# 輸出到專用暫存目錄，避免污染 target/wheels 或與 maturin develop 衝突。
# Output to dedicated scratch dir to avoid polluting target/wheels.
WHEEL_DIR="$(mktemp -d -t openclaw_pyo3_wheel.XXXXXX)"
# cleanup on exit (keep on explicit failure for debugging? -- remove always for determinism)
trap 'rm -rf "${WHEEL_DIR}"' EXIT

log "Building wheel into ${WHEEL_DIR} (profile=${PROFILE})..."
MATURIN_BUILD_ARGS=(build -m "${PYO3_CRATE_DIR}/Cargo.toml" -o "${WHEEL_DIR}")
if [[ "${PROFILE}" == "release" ]]; then
    MATURIN_BUILD_ARGS+=(--release)
fi

if ! "${MATURIN_BIN}" "${MATURIN_BUILD_ARGS[@]}"; then
    err "maturin build failed"
    exit 2
fi

# Find the produced wheel / 找出產出的 wheel
WHEEL_FILE="$(find "${WHEEL_DIR}" -maxdepth 1 -type f -name "${MODULE_NAME}-*.whl" | head -n 1)"
if [[ -z "${WHEEL_FILE}" ]]; then
    err "no wheel produced in ${WHEEL_DIR}"
    exit 2
fi
log "Wheel built: $(basename "${WHEEL_FILE}")"

# ── Install into each target venv / 安裝至每個目標 venv ──
install_into_venv() {
    local venv="$1"
    local py="${venv}/bin/python3"
    log "Installing into ${venv} ..."
    if ! "${py}" -m pip install --quiet --force-reinstall --no-deps "${WHEEL_FILE}"; then
        err "pip install failed for ${venv}"
        return 1
    fi
    return 0
}

for v in "${TARGET_VENVS[@]}"; do
    if ! install_into_venv "${v}"; then
        exit 3
    fi
done

# ── Verify .so presence + timestamps / 驗證 .so 存在並比對 ──
# Python version may differ per-venv; discover .so via glob.
# Python 版本可能各 venv 不同，用 glob 搜尋 .so。
verify_venv_so() {
    local venv="$1"
    # shellcheck disable=SC2207  # we want word-splitting here (no spaces in paths expected).
    local found=( $(find "${venv}/lib" -maxdepth 5 -type f -name "${MODULE_NAME}*.so" 2>/dev/null) )
    if [[ ${#found[@]} -eq 0 ]]; then
        err "no ${MODULE_NAME}*.so found under ${venv}/lib"
        return 1
    fi
    for so in "${found[@]}"; do
        local sz mtime
        sz=$(stat -c "%s" "${so}" 2>/dev/null || stat -f "%z" "${so}")
        mtime=$(stat -c "%y" "${so}" 2>/dev/null || stat -f "%Sm" "${so}")
        log "  ${so}"
        log "    size=${sz}B  mtime=${mtime}"
    done
    return 0
}

log "Verifying deployed .so files:"
for v in "${TARGET_VENVS[@]}"; do
    if ! verify_venv_so "${v}"; then
        exit 4
    fi
done

# ── Cross-venv sanity check (if dual-write) / 雙寫一致性檢查 ──
if [[ "${#TARGET_VENVS[@]}" -ge 2 ]]; then
    log "Cross-venv size check:"
    SIZES=()
    for v in "${TARGET_VENVS[@]}"; do
        first_so="$(find "${v}/lib" -maxdepth 5 -type f -name "${MODULE_NAME}*.so" 2>/dev/null | head -n 1)"
        if [[ -n "${first_so}" ]]; then
            sz=$(stat -c "%s" "${first_so}" 2>/dev/null || stat -f "%z" "${first_so}")
            SIZES+=("${sz}")
        fi
    done
    first_size="${SIZES[0]:-}"
    mismatch=0
    for s in "${SIZES[@]}"; do
        if [[ "${s}" != "${first_size}" ]]; then
            mismatch=1
        fi
    done
    if [[ "${mismatch}" -eq 1 ]]; then
        warn "deployed .so sizes differ across venvs: ${SIZES[*]}"
        warn "this may indicate divergent Python ABIs; verify interpreter versions."
    else
        log "  all ${#SIZES[@]} deployed .so have identical size (${first_size}B)."
    fi
fi

log "Done. PyO3 module '${MODULE_NAME}' deployed to ${#TARGET_VENVS[@]} venv(s)."

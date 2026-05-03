#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# replay_runner_symbol_audit.sh — REF-20 Wave 3 R20-P2b-S10
# replay_runner symbol 稽核（縱深防禦 / defense in depth）
#
# MODULE_NOTE (EN):
#   Validate that the compiled `replay_runner` Rust binary contains zero
#   forbidden symbols (Decision Lease / IPC server / exchange pipeline /
#   exchange connector / live authorization / DB writer / order placement)
#   that would violate REF-20 V3 §6.2 forbidden-path contract or §3 G7/G8
#   crate boundary.
#
#   Three-layer defense (this script is layer 3):
#     L1 compile-time   : Cargo `replay_isolated` feature gate (P0-T2)
#     L2 runtime        : `ReplayProfile::Isolated` enum guard (P2b-S7)
#     L3 binary symbols : nm/objdump grep on stripped release artifact (THIS)
#
#   Cross-platform split (per Wave 2 dispatch §2 ambiguity #5):
#     - macOS (Darwin / aarch64-apple-darwin)  → primary CI target
#         use `nm -gU` (BSD nm, list externally-visible defined symbols only)
#     - Linux (x86_64-unknown-linux-gnu)        → secondary CI target
#         use `nm --extern-only --defined-only` (GNU binutils equivalent)
#     Both branches must produce a 0 forbidden symbol verdict.
#
#   Exit codes:
#     0  AUDIT PASS — no forbidden symbol detected
#     1  AUDIT FAIL — at least one forbidden symbol class hit
#     2  BUILD FAIL — `cargo build` failed
#     3  NM NOT FOUND — `nm` toolchain absent on $PATH
#     4  BINARY NOT FOUND — expected `target/release/replay_runner` missing
#
#   Spec source:
#     - docs/execution_plan/2026-05-03--ref20_paper_replay_lab_dev_plan_v3.md
#       §3 G7 (runner decision) / G8 (fail-closed isolation)
#       §6.1 (canonical implementation choice) / §6.2 (forbidden list)
#       §12 #8 (resource_isolation acceptance)
#     - docs/CCAgentWorkSpace/PA/workspace/reports/
#       2026-05-03--replay_runner_crate_boundary_allowlist.md §6 (symbol allowlist)
#     - docs/execution_plan/2026-05-03--ref20_implementation_workplan_v1.md
#       §4 Wave 3 R20-P2b-S10 row
#     - docs/execution_plan/2026-05-03--ref20_wave2_dispatch_v1.md §2 #5
#       (macOS primary / Linux secondary CI runner platform)
#
# MODULE_NOTE (中):
#   驗證已編譯的 `replay_runner` Rust binary 不含任何禁用 symbol
#   （Decision Lease / IPC server / exchange pipeline / 交易所連線 /
#   live 授權寫入 / DB writer / 下單 / 撤單），違反 = REF-20 V3 §6.2
#   forbidden-path 契約或 §3 G7/G8 crate 邊界。
#
#   三層縱深防禦（本 script 為第三層）：
#     L1 編譯期   ：Cargo `replay_isolated` feature gate（P0-T2）
#     L2 runtime  ：`ReplayProfile::Isolated` enum guard（P2b-S7）
#     L3 binary 層：nm/objdump grep 已剝離 release artifact（本 script）
#
#   跨平台分支（依 Wave 2 dispatch §2 ambiguity #5）：
#     - macOS (Darwin / aarch64-apple-darwin)  → CI 主軸
#         用 `nm -gU`（BSD nm，僅列 external + defined）
#     - Linux (x86_64-unknown-linux-gnu)        → CI 次軸
#         用 `nm --extern-only --defined-only`（GNU binutils 等價）
#     兩分支都必須回 0 forbidden symbol。
#
#   Exit code：
#     0  AUDIT PASS — 0 forbidden symbol
#     1  AUDIT FAIL — ≥1 個 forbidden symbol class 命中
#     2  BUILD FAIL — `cargo build` 失敗
#     3  NM NOT FOUND — 環境無 `nm` 工具鏈
#     4  BINARY NOT FOUND — 找不到 `target/release/replay_runner`
#
#   契約來源：見 EN 區段 Spec source 列。
# ─────────────────────────────────────────────────────────────────────────────
# Strict bash mode / 嚴格模式
#   -e: exit on error / 任意命令失敗即離開
#   -u: undefined var = error / 未宣告變數視為錯誤
#   -o pipefail: pipe 任一段失敗 → 整 pipe 失敗
#   IFS=$'\n\t': 不依賴空白 split / 防 word-splitting 漂移
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────────────────────────────
# Section 1 — Path resolution / 路徑解析
# ──────────────────────────────────────────────────────────────────────
# 解析 srv/ root（不依賴 cwd）：本 script 位於 srv/helper_scripts/ci/，
# 故 srv/ root = $(dirname "$0")/../..
# Resolve srv/ root (cwd-independent): this script lives at
# srv/helper_scripts/ci/, so srv/ root = $(dirname "$0")/../..
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUST_CRATE_DIR="$SRV_ROOT/rust/openclaw_engine"
BIN_NAME="replay_runner"
# release artifact 的標準 cargo 輸出路徑 / Standard cargo release artifact path
BIN_PATH_DEFAULT="$RUST_CRATE_DIR/target/release/$BIN_NAME"
# 允許 caller 透過 $REPLAY_RUNNER_BIN env var 覆寫（測試 / CI matrix 用）
# Allow caller to override via $REPLAY_RUNNER_BIN env var (test / CI matrix)
BIN_PATH="${REPLAY_RUNNER_BIN:-$BIN_PATH_DEFAULT}"

# ──────────────────────────────────────────────────────────────────────
# Section 2 — Logging helper / 日誌輔助
# ──────────────────────────────────────────────────────────────────────
log() {
    # 輸出到 stderr，避免污染 stdout（CI artefact 可能 grep stdout）
    # Write to stderr so stdout stays clean for CI artefact grep.
    printf '[replay_runner_symbol_audit] %s\n' "$*" >&2
}

# ──────────────────────────────────────────────────────────────────────
# Section 3 — Build phase / 建置階段
# ──────────────────────────────────────────────────────────────────────
# 預設策略：若 binary 已存在且 caller 設定 SKIP_BUILD=1 跳過 cargo build
# Default policy: skip cargo build if binary exists AND caller set SKIP_BUILD=1
# 否則 force rebuild 確保 audit 對最新 source 生效
# Otherwise force rebuild to ensure audit reflects latest source.
build_binary() {
    if [[ "${SKIP_BUILD:-0}" == "1" && -f "$BIN_PATH" ]]; then
        log "SKIP_BUILD=1 + binary exists → skip cargo build"
        return 0
    fi

    log "cargo build --release --bin $BIN_NAME --features replay_isolated ..."
    # cd 到 crate dir 跑 cargo（cargo 對工作目錄敏感）
    # cd into crate dir for cargo (cargo is cwd-sensitive).
    if ! (
        cd "$RUST_CRATE_DIR" && \
        cargo build --release \
            --package openclaw_engine \
            --bin "$BIN_NAME" \
            --features replay_isolated
    ); then
        log "BUILD FAIL: cargo build returned non-zero"
        exit 2
    fi
    log "build OK"
}

# ──────────────────────────────────────────────────────────────────────
# Section 4 — Tooling probe / 工具偵測
# ──────────────────────────────────────────────────────────────────────
# 確認 nm 在 PATH；若無 → exit 3（不 fall-through 到 false-PASS）
# Verify nm in PATH; if absent → exit 3 (no false-PASS fall-through).
probe_nm() {
    if ! command -v nm >/dev/null 2>&1; then
        log "NM NOT FOUND: 'nm' command absent in \$PATH"
        log "  install: macOS → comes with Xcode CLI tools (xcode-select --install)"
        log "  install: Linux → 'apt install binutils' or 'yum install binutils'"
        exit 3
    fi
    log "nm available: $(command -v nm)"
}

# ──────────────────────────────────────────────────────────────────────
# Section 5 — Binary existence check / 二進位存在性檢查
# ──────────────────────────────────────────────────────────────────────
check_binary() {
    if [[ ! -f "$BIN_PATH" ]]; then
        log "BINARY NOT FOUND: $BIN_PATH"
        log "  hint: rerun without SKIP_BUILD or adjust REPLAY_RUNNER_BIN"
        exit 4
    fi
    log "binary path: $BIN_PATH"
}

# ──────────────────────────────────────────────────────────────────────
# Section 6 — Cross-platform symbol dump / 跨平台 symbol dump
# ──────────────────────────────────────────────────────────────────────
# Darwin = macOS（含 Apple Silicon aarch64-apple-darwin）→ 用 BSD-style flags
# Linux  = GNU/Linux（含 x86_64 + linux-arm64）→ 用 GNU binutils flags
# 注：Apple llvm-nm 同時相容 GNU flag，但本分支以「OS 慣用 flag」為主軸，
#     確保 raw BSD nm（例如 macOS classic toolchain 無 llvm-nm 時）也能 work。
# Note: Apple llvm-nm also accepts GNU flags, but we pick OS-conventional
#       flags so raw BSD nm (macOS classic toolchain w/o llvm-nm) still works.
dump_symbols() {
    local os
    os="$(uname -s)"
    case "$os" in
        Darwin)
            # macOS / aarch64-apple-darwin
            #   -g: 僅外部 symbol（external only）
            #   -U: 僅 defined（已定義，不含 undefined / extern reference）
            # macOS / aarch64-apple-darwin
            #   -g: external symbols only
            #   -U: defined only (no undefined / extern references)
            log "platform=Darwin → nm -gU"
            nm -gU "$BIN_PATH"
            ;;
        Linux)
            # Linux / GNU binutils
            #   --extern-only: external only
            #   --defined-only: defined only
            log "platform=Linux → nm --extern-only --defined-only"
            nm --extern-only --defined-only "$BIN_PATH"
            ;;
        *)
            # 不支援的 OS 不 false-PASS；fail-closed exit 3
            # Unsupported OS does not false-PASS; fail-closed exit 3.
            log "UNSUPPORTED OS: $os (only Darwin / Linux supported)"
            exit 3
            ;;
    esac
}

# ──────────────────────────────────────────────────────────────────────
# Section 7 — Forbidden symbol patterns / 禁用 symbol 模式
# ──────────────────────────────────────────────────────────────────────
# 來自 PA boundary report §6.1 + V3 §6.2 + 16 根原則 §四 hard 邊界。
# 每個 pattern 對應一個 violation class；任一 hit ≥ 1 → AUDIT FAIL。
# Patterns sourced from PA boundary report §6.1 + V3 §6.2 + CLAUDE §4 hard
# boundary. Each pattern maps to one violation class; any class hit ≥ 1
# triggers AUDIT FAIL.
#
# 設計說明：
#   - 用 ERE alternation；避免 PCRE/Perl-only 語法（POSIX grep -E 即可）
#   - 中括號鎖定 namespace 邊界（::），避免誤殺其他無關 symbol
#   - bybit_(rest|ws|api) 用 group capture 包蓋三 connector 路徑
#   - 模式選擇遵循「false-positive 寧多勿少」原則 — replay binary 本就不該
#     含這些 symbol；若誤殺說明 build graph 有意外漂移，需人工 review
#
# Design notes:
#   - Use ERE alternation; no PCRE/Perl-only syntax (POSIX grep -E enough)
#   - :: lock onto Rust namespace boundary, avoid clobbering unrelated symbols
#   - bybit_(rest|ws|api) group-captures three connector paths
#   - We err toward false-positive: replay binary should never contain
#     these symbols; an unexpected hit indicates build graph drift
#     and warrants human review.
declare -a FORBIDDEN_PATTERNS=(
    # Decision Lease — 16#3 AI ≠ 命令；replay 永不取 lease
    # Decision Lease — origin §3; replay never acquires lease
    'acquire_lease|release_lease'

    # GovernanceHub bridge — Python 端唯一 lease caller；Rust binary 不得 import
    # GovernanceHub bridge — Python is the only legitimate lease caller
    'GovernanceHub'

    # IPC server — Rust↔Python JSON-RPC pipeline；replay 不開 IPC
    # IPC server — Rust↔Python JSON-RPC pipeline; replay opens no IPC
    'ipc_server::|ipc_dispatch|ipc_handler'

    # Exchange pipeline bootstrap — startup::build_exchange_pipeline 含 live dispatch wiring
    # Exchange pipeline bootstrap — startup::build_exchange_pipeline carries live dispatch wiring
    'build_exchange_pipeline'

    # Decision lease lifetime objects — lease.rs API
    # Decision lease lifetime objects — lease.rs API surface
    'decision_lease|DecisionLease'

    # Exchange dispatch — live order routing path
    # Exchange dispatch — live order routing path
    'exchange_dispatch'

    # Bybit connectors — REST / WS / API client (no exchange comm in replay)
    # Bybit connectors — REST / WS / API client (replay does not call exchange)
    'bybit_(rest|ws|api)'

    # Live authorization write path — must go through Python renew/approve route
    # Live authorization write path — must go through Python renew/approve route
    'live_authorization|_write_signed_live_authorization'

    # Order placement / cancellation / amend — single write entry §1
    # Order placement / cancellation / amend — single write entry §1
    'place_order|cancel_order|amend_order'

    # DB writer channels — replay must not write trading.* / learning.* directly
    # DB writer channels — replay must not write trading.* / learning.* directly
    'canary_writer::write|database::writer'
)

# ──────────────────────────────────────────────────────────────────────
# Section 8 — Audit phase / 稽核階段
# ──────────────────────────────────────────────────────────────────────
audit_symbols() {
    # 一次 dump 全 symbol，後續多次 grep 同一份 input（避免重跑 nm）
    # Dump symbols once, grep multiple times against same input
    # (avoid repeated nm invocations).
    local symbols
    if ! symbols="$(dump_symbols)"; then
        log "BUILD FAIL: nm dump failed (binary may be corrupt)"
        exit 2
    fi

    local total_lines
    total_lines="$(printf '%s\n' "$symbols" | wc -l | tr -d ' ')"
    log "symbol count: $total_lines"

    local fail_count=0
    local pattern label hits sample

    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        # 先 count hit 數，再決定是否 sample echo
        # First count hits, then decide whether to sample-echo
        # 注：grep 找不到時 exit 1（POSIX），用 || true 防 set -e 中止整 script
        # Note: grep returns 1 when no match (POSIX); use || true to prevent
        #       set -e from aborting the whole script.
        hits="$(printf '%s\n' "$symbols" | grep -E "$pattern" | wc -l | tr -d ' ' || true)"

        if [[ "${hits:-0}" -gt 0 ]]; then
            label="$(printf '%s' "$pattern" | tr '|' ',' | head -c 60)"
            log "FORBIDDEN HIT [$label]: $hits symbol(s)"
            # sample 前 5 行作 evidence；不 dump 全部以避免 log 爆炸
            # Sample top-5 as evidence; don't dump all to keep log small
            sample="$(printf '%s\n' "$symbols" | grep -E "$pattern" | head -5)"
            printf '%s\n' "$sample" | while IFS= read -r line; do
                log "  | $line"
            done
            fail_count=$((fail_count + 1))
        fi
    done

    if [[ "$fail_count" -gt 0 ]]; then
        log "AUDIT FAIL: $fail_count forbidden symbol class(es) detected"
        log "  → REF-20 V3 §6.2 forbidden-path contract violated"
        log "  → REF-20 V3 §3 G7/G8 crate boundary breach"
        log "  → fix: remove offending dependency from replay_runner build graph"
        exit 1
    fi

    log "AUDIT PASS: 0 forbidden symbol detected ($total_lines symbols scanned)"
    exit 0
}

# ──────────────────────────────────────────────────────────────────────
# Section 9 — Main entry / 主入口
# ──────────────────────────────────────────────────────────────────────
main() {
    log "=== replay_runner symbol audit start ==="
    log "srv root: $SRV_ROOT"
    log "platform: $(uname -s) $(uname -m)"

    probe_nm
    build_binary
    check_binary
    audit_symbols
}

# 若被 source 而非執行 → 不跑 main（讓 test harness 可以 source 後測 helper）
# When sourced (not executed) → don't run main (lets test harness source
# this file and invoke individual helpers directly).
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

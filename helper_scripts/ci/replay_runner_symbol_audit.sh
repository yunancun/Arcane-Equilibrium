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
#     L3 binary symbols : 掃描保留符號的 debug 產物（本腳本）
#
#   Cross-platform split (per Wave 2 dispatch §2 ambiguity #5):
#     - macOS (Darwin / aarch64-apple-darwin)  → primary CI target
#         使用 `nm --demangle` 掃描完整符號表，包含非對外符號
#     - Linux (x86_64-unknown-linux-gnu)        → secondary CI target
#         使用 `nm --demangle` 掃描完整符號表，包含非對外符號
#     Both branches must produce a 0 forbidden symbol verdict.
#
#   Exit codes:
#     0  AUDIT PASS — no forbidden symbol detected
#     1  AUDIT FAIL — at least one forbidden symbol class hit
#     2  BUILD FAIL — `cargo build` failed
#     3  NM NOT FOUND — `nm` toolchain absent on $PATH
#     4  BINARY NOT FOUND — expected `target/debug/replay_runner` missing
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
#     L3 binary 層：nm 掃描未剝除的 debug 產物（本 script）
#
#   跨平台分支（依 Wave 2 dispatch §2 ambiguity #5）：
#     - macOS (Darwin / aarch64-apple-darwin)  → CI 主軸
#         用 `nm --demangle`（完整符號表）
#     - Linux (x86_64-unknown-linux-gnu)        → CI 次軸
#         用 `nm --demangle`（完整符號表）
#     兩分支都必須回 0 forbidden symbol。
#
#   Exit code：
#     0  AUDIT PASS — 0 forbidden symbol
#     1  AUDIT FAIL — ≥1 個 forbidden symbol class 命中
#     2  BUILD FAIL — `cargo build` 失敗
#     3  NM NOT FOUND — 環境無 `nm` 工具鏈
#     4  BINARY NOT FOUND — 找不到 `target/debug/replay_runner`
#     5  INCONCLUSIVE — 空表、已剝除、缺定位符號、無法讀取符號表、樣式無法評估，
#                        或無法確定建置產物的位置
#     64 USAGE — 不認得的參數（只接受 `--self-test`）
#
#   正向控制：`--self-test` 逐類確認每一條禁用樣式都能命中自己的樣本，確認乾淨
#   樣本不被命中，並確認泛型參數形式（`a..b`）的禁用路徑也會被命中；全部成立回 0，
#   否則回 5。不建置、不讀執行檔。
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
# REF-20 Sprint A R1-T4 (2026-05-04): cargo workspace (post 2026-04-15 root
# Cargo.toml workspace consolidation) emits release artifacts to
# $SRV_ROOT/rust/target/release/, NOT to the legacy crate-local
# $SRV_ROOT/rust/openclaw_engine/target/release/. The legacy default caused
# this audit to fail BIN PATH check (exit 4) on Linux runtime even when the
# binary existed under the workspace target. RUST_CRATE_DIR remains pinned
# for `cargo build` cwd-sensitivity (cargo still resolves crate-local
# Cargo.toml relative to the crate dir we cd into).
# REF-20 Sprint A R1-T4（2026-05-04）：cargo workspace（2026-04-15 root
# Cargo.toml workspace 合併後）將 release artifact emit 到
# $SRV_ROOT/rust/target/release/，**不**是 legacy 的 crate-local
# $SRV_ROOT/rust/openclaw_engine/target/release/。舊預設導致 Linux runtime
# 即使 binary 存在於 workspace target，audit 仍報 BIN PATH 找不到（exit 4）。
# RUST_CRATE_DIR 仍保留供 `cargo build` cwd 使用（cargo 仍以 crate dir 為
# 基準解析 crate-local Cargo.toml）。
# 詳見 PA report：docs/CCAgentWorkSpace/PA/workspace/reports/
#                 2026-05-04--ref20_sprint_a_task_dag.md §1 R1-T4 / §5 H1。
RUST_TARGET_DIR="$SRV_ROOT/rust/target/debug"
BIN_NAME="replay_runner"
# debug artifact 的標準 cargo workspace 輸出路徑（2026-04-15 workspace 合併後）。
# release 產物已剝除符號，稽核沒有偵測力，因此改掃 debug 產物。
BIN_PATH_DEFAULT="$RUST_TARGET_DIR/$BIN_NAME"
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
# 預設每次都建置，確保稽核對象是目前的源碼。SKIP_BUILD=1 時一律不建置，
# 執行檔是否存在由 check_binary 另行檢查；此時受審檔是否對應目前源碼由呼叫端負責。
build_binary() {
    if [[ "${SKIP_BUILD:-0}" == "1" ]]; then
        log "SKIP_BUILD=1 → skip cargo build; check binary separately"
        return 0
    fi

    # 這三個變數會改變 cargo 的輸出位置；此時預設路徑上若留有舊產物，稽核它等於誤報通過。
    # （cargo 設定檔裡的 target-dir 偵測不到，屬已知限制。）
    if [[ -z "${REPLAY_RUNNER_BIN:-}" && ( -n "${CARGO_TARGET_DIR:-}" || -n "${CARGO_BUILD_TARGET_DIR:-}" || -n "${CARGO_BUILD_TARGET:-}" ) ]]; then
        log "INCONCLUSIVE: CARGO_TARGET_DIR, CARGO_BUILD_TARGET_DIR or CARGO_BUILD_TARGET is set; cannot locate the artifact this build produces"
        log "  hint: unset them, or point REPLAY_RUNNER_BIN at the artifact that was just built"
        exit 5
    fi

    log "cargo build --bin $BIN_NAME --features replay_isolated (unstripped debug) ..."
    # cd 到 crate dir 跑 cargo（cargo 對工作目錄敏感）
    # cd into crate dir for cargo (cargo is cwd-sensitive).
    # 不寫死離線旗標：沒有套件快取的機器仍須能建置；需要離線時由呼叫端設
    # CARGO_NET_OFFLINE=true，cargo 原生支援。
    if ! (
        cd "$RUST_CRATE_DIR" && \
        CARGO_PROFILE_DEV_STRIP=none cargo build \
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
    # 記下受審檔的雜湊，事後才能對出稽核的是哪一份產物。
    # 雜湊只供事後對照；算不出來時照實記錄並繼續，讀不到的檔案會在傾印符號時回 5。
    local digest="unavailable"
    if command -v sha256sum >/dev/null 2>&1; then
        digest="$(sha256sum "$BIN_PATH" | cut -d' ' -f1)" || digest="unavailable"
    elif command -v shasum >/dev/null 2>&1; then
        digest="$(shasum -a 256 "$BIN_PATH" | cut -d' ' -f1)" || digest="unavailable"
    fi
    log "binary sha256: ${digest:-unavailable}"
}

# ──────────────────────────────────────────────────────────────────────
# Section 6 — Cross-platform symbol dump / 跨平台 symbol dump
# ──────────────────────────────────────────────────────────────────────
# Darwin 與 Linux 都用 `nm --demangle` 傾印完整符號表（含非對外與未定義符號）。
# 本函式在指令替換的子殼裡執行；任何非零結束都由 audit_symbols 統一回 5（無法判定）。
dump_symbols() {
    local os
    os="$(uname -s)"
    case "$os" in
        Darwin|Linux)
            # 保留全部符號（含 local 與 undefined），解碼名稱供既有 namespace 樣式檢查。
            log "platform=$os → nm --demangle (full symbol table)"
            nm --demangle "$BIN_PATH"
            ;;
        *)
            # 不支援的作業系統不得誤報通過；回非零，由呼叫端回 5。
            log "UNSUPPORTED OS: $os (only Darwin / Linux supported)"
            return 1
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

# 正向控制樣本：與 FORBIDDEN_PATTERNS 同序、一類一筆，每筆只會被自己那一類命中。
# 新增或調整樣式時必須同步這裡；數量不一致時 --self-test 回 5。
declare -a SELF_TEST_SAMPLES=(
    '0 t governance_hub::acquire_lease'
    '0 t control::GovernanceHub::new'
    '0 t ipc_server::start'
    '0 t startup::build_exchange_pipeline'
    '0 t lease::DecisionLease::drop'
    '0 t exchange_dispatch::send'
    '0 t bybit_rest::get'
    '0 t live_authorization::load'
    '0 t orders::place_order'
    '0 t database::writer::flush'
)

# 泛型參數形式的樣本。llvm-nm 對泛型參數與 trait 實作裡的路徑輸出 `a..b..c`（舊式編碼的
# `..` 沒有被還原成 `::`），帶 `::` 的禁用樣式必須在正規化之後仍能命中這種形式。
declare -a SELF_TEST_GENERIC_SAMPLES=(
    '0 t core::ptr::drop_in_place$LT$openclaw_engine..ipc_server..Server$GT$::h0123456789abcdef'
    '0 t core::ops::function::FnOnce::call_once$LT$openclaw_engine..canary_writer..write$GT$'
    '0 t core::ptr::drop_in_place$LT$openclaw_engine..database..writer..Handle$GT$::h0123456789abcdef'
)

# 定位符號：解碼後的引擎與入口命名空間。必須帶 `::`；未解碼的函式名稱不含它，
# 所以這項檢查能證明 `nm --demangle` 對一般函式名稱生效。它以原始輸出比對，不用正規化後的文字：
# 未解碼的名稱在泛型參數裡同樣帶 `..`，正規化後會被誤認成已解碼。
declare -a ANCHOR_SYMBOLS=('openclaw_engine::' 'replay_runner::')

# ──────────────────────────────────────────────────────────────────────
# Section 8 — Audit phase / 稽核階段
# ──────────────────────────────────────────────────────────────────────
audit_symbols() {
    # 一次 dump 全 symbol，後續多次 grep 同一份 input（避免重跑 nm）
    # Dump symbols once, grep multiple times against same input
    # (avoid repeated nm invocations).
    local symbols
    if [[ "${#FORBIDDEN_PATTERNS[@]}" -eq 0 ]]; then
        log "INCONCLUSIVE: no forbidden pattern is defined"
        exit 5
    fi
    if [[ "$#" -gt 0 ]]; then
        symbols="$1"
    elif ! symbols="$(dump_symbols)"; then
        log "INCONCLUSIVE: nm dump failed"
        exit 5
    fi

    local total_lines
    total_lines="$(printf '%s\n' "$symbols" | grep -c '[^[:space:]]' || true)"
    if [[ "${total_lines:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: empty symbol table (stripped or empty binary)"
        exit 5
    fi
    # 引擎與入口兩個定位符號均需存在；標頭單一符號或未解碼的符號表不能形成通過證據。
    local anchor
    for anchor in "${ANCHOR_SYMBOLS[@]}"; do
        if ! grep -qF -- "$anchor" <<< "$symbols"; then
            log "INCONCLUSIVE: missing anchor $anchor ($total_lines symbols)"
            exit 5
        fi
    done
    log "symbol count: $total_lines; anchors present"

    # 樣式比對用正規化後的文字：把泛型參數與 trait 實作裡的 `..` 統一成 `::`，
    # 否則只以這種形式出現的禁用路徑不會被帶 `::` 的樣式命中。
    local normalised
    if ! normalised="$(printf '%s\n' "$symbols" | sed 's/\.\./::/g')"; then
        log "INCONCLUSIVE: could not normalise the symbol table"
        exit 5
    fi

    local fail_count=0
    local pattern label hits sample status

    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        # grep 的結束碼：0 有命中、1 無命中、2 以上是樣式或讀取錯誤。
        # 錯誤不得當成「無命中」，否則壞掉的樣式會讓該類永遠乾淨。
        status=0
        hits="$(grep -cE -- "$pattern" <<< "$normalised")" || status=$?
        # 結束碼 1 而命中數不是 0，代表 grep 根本沒有正常執行（例如輸入重導向失敗）。
        if [[ "$status" -ge 2 || ( "$status" -eq 1 && "$hits" != "0" ) ]]; then
            log "INCONCLUSIVE: pattern could not be evaluated (grep exit $status): $pattern"
            exit 5
        fi

        if [[ "${hits:-0}" -gt 0 ]]; then
            label="$(printf '%s' "$pattern" | tr '|' ',' | head -c 60)"
            log "FORBIDDEN HIT [$label]: $hits symbol(s)"
            # 保留完整命中清單；不接 head，避免大符號表的 SIGPIPE 蓋掉 exit 1。
            sample="$(grep -E -- "$pattern" <<< "$normalised" || true)"
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
# 正向控制。對外回 0 才代表偵測有效；其餘一律回 5，呼叫端不必反轉結束碼。
self_test() {
    log "positive control: every forbidden class must detect its own sample"
    if [[ "${#SELF_TEST_SAMPLES[@]}" -ne "${#FORBIDDEN_PATTERNS[@]}" ]]; then
        log "INCONCLUSIVE: ${#SELF_TEST_SAMPLES[@]} samples for ${#FORBIDDEN_PATTERNS[@]} pattern classes"
        exit 5
    fi
    # 一、逐類：每條樣式必須命中同序的樣本（不靠別的類代為命中）。
    local index status
    for index in "${!FORBIDDEN_PATTERNS[@]}"; do
        status=0
        grep -qE -- "${FORBIDDEN_PATTERNS[$index]}" <<< "${SELF_TEST_SAMPLES[$index]}" || status=$?
        if [[ "$status" -ne 0 ]]; then
            log "INCONCLUSIVE: class $index did not detect its sample (grep exit $status): ${FORBIDDEN_PATTERNS[$index]}"
            exit 5
        fi
    done
    # 二、乾淨樣本（只有定位符號）走完整流程必須通過，確認沒有任何一類命中過寬。
    local clean=$'0 t openclaw_engine::replay::runner\n0 t replay_runner::main'
    local control_exit=0
    log "self-test: clean control (the next verdict line is expected to be AUDIT PASS)"
    ( audit_symbols "$clean" ) || control_exit=$?
    if [[ "$control_exit" -ne 0 ]]; then
        log "INCONCLUSIVE: clean control did not pass (inner exit $control_exit)"
        exit 5
    fi
    # 三、全部樣本走完整流程必須判定失敗（內層 exit 1）。
    local injected="$clean" sample
    for sample in "${SELF_TEST_SAMPLES[@]}"; do
        injected+=$'\n'"$sample"
    done
    control_exit=0
    log "self-test: injected control (the next verdict line is expected to be AUDIT FAIL)"
    ( audit_symbols "$injected" ) || control_exit=$?
    if [[ "$control_exit" -ne 1 ]]; then
        log "INCONCLUSIVE: positive control was not detected (inner exit $control_exit)"
        exit 5
    fi
    # 四、泛型參數形式的樣本逐筆走完整流程，各自必須判定失敗（確認正規化有效）。
    for sample in "${SELF_TEST_GENERIC_SAMPLES[@]}"; do
        control_exit=0
        ( audit_symbols "$clean"$'\n'"$sample" ) || control_exit=$?
        if [[ "$control_exit" -ne 1 ]]; then
            log "INCONCLUSIVE: generic-argument form was not detected (inner exit $control_exit): $sample"
            exit 5
        fi
    done
    log "SELF-TEST PASS: ${#FORBIDDEN_PATTERNS[@]} classes detected their samples; clean control passed; ${#SELF_TEST_GENERIC_SAMPLES[@]} generic-argument forms detected"
    exit 0
}

main() {
    # 不認得的參數不得被默默忽略：打錯的 --self-test 會變成跑完整稽核並可能回 0。
    if [[ "$#" -gt 1 || ( "$#" -eq 1 && "$1" != "--self-test" ) ]]; then
        log "USAGE: unknown argument(s): $*"
        log "  usage: $(basename "$0") [--self-test]"
        exit 64
    fi
    if [[ "${1:-}" == "--self-test" ]]; then
        self_test
    fi
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

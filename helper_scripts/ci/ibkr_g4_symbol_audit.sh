#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ibkr_g4_symbol_audit.sh — IBKR B1 G4 首次接觸 symbol 稽核（縱深防禦 / defense in depth）
#
# MODULE_NOTE (中):
#   驗證 **default `cargo build`（debug，無 --features）的 `openclaw-engine` 引擎 artifact**
#   不含任何 IBKR B1 只讀 TWS 連接器符號。B1 的唯一具體 `TcpStream::connect`
#   （`g4_operator_triggered_first_contact`）與 G4 觸發 bin（`ibkr_g4_first_contact`）均在
#   `ibkr_g4_contact` feature 之後；且整個 `ibkr_readonly_tws_client` 模塊在 default build
#   裡 **0 production caller → 被 linker DCE**（E4 Linux 實證：符號數=0）。任一符號出現 =
#   有人誤接 production caller 或漏 feature-gate，把 G4 接觸面拉進 live 引擎，違反 CLAUDE §一
#   「IBKR read-only/paper/shadow，gated」+ ADR-0048 / AMD-2026-07-08-01 惰性接觸邊界。
#
#   **主保證不是本 script**：L1 = Cargo `ibkr_g4_contact` feature-gate（gated fn / bin 於
#   default build 根本不編譯）+ 0-caller DCE（整模塊不進 artifact）。本 script 是 **L3
#   回歸 gate**——若未來有人誤接 production caller，符號會出現在 debug default artifact →
#   本 script fail。
#
#   **為什麼審 debug 而非 release**（E4 RETURN 修正 vacuous-PASS）：
#   `rust/Cargo.toml [profile.release] strip="symbols"` 會把 release artifact 全 strip →
#   `nm` 讀到 0 符號 → 舊版誤報「PASS (1 symbols scanned)」= 無鑑別力的 fail-open。改審
#   **unstripped debug** artifact 才有真 symtab 可鑑別；release 的 strip 是刻意的部署瘦身，
#   不該當作安全信號。
#
#   **fail-closed on inconclusive**：安全 gate 無法驗證時必 fail-closed。若被審 binary 是
#   stripped（.symtab 空）**或** 總符號數=0 **或** 缺 `openclaw_engine` anchor 符號（無法
#   證明 symtab 有料）→ **exit 5**（不得報 PASS）。
#
#   三層縱深防禦（本 script 為第三層）：
#     L1 編譯期   ：Cargo `ibkr_g4_contact` feature gate + 0-caller DCE（**主保證**）
#     L2 runtime  ：g4_operator_triggered_first_contact 內 env/sealed/approval/host/
#                   envelope（EA3 活化閘,nonce 原子消費,R16）五閘
#     L3 binary 層：nm grep default **debug** `openclaw-engine` artifact（本 script）
#
#   正控（E4 驗 script 有牙）：對 unstripped g4 bin（`cargo build --features ibkr_g4_contact`
#   → `target/debug/ibkr_g4_first_contact`）以 `IBKR_G4_AUDIT_BIN=… SKIP_BUILD=1` 跑本
#   script → pattern 命中 → AUDIT FAIL（exit 1）；證明 pattern 非死。
#
#   Exit code：
#     0  AUDIT PASS       — symtab 有料且 0 forbidden symbol
#     1  AUDIT FAIL       — ≥1 個 forbidden symbol class 命中
#     2  BUILD FAIL       — `cargo` 缺席或 `cargo build` 失敗
#     3  NM NOT FOUND     — 環境無 `nm` 工具鏈
#     4  BINARY NOT FOUND — 找不到 `target/debug/openclaw-engine`
#     5  INCONCLUSIVE     — binary stripped / symtab 空 / 缺 anchor（fail-closed，不報 PASS）
#
#   契約來源：
#     - CLAUDE.md §一 Product Boundary（IBKR read-only/paper/shadow, gated）
#     - docs/adr/ADR-0048 + AMD-2026-07-08-01（Phase 2 read-only external contact）
#     - 仿 helper_scripts/ci/replay_runner_symbol_audit.sh（symbol-audit 範式）
# ─────────────────────────────────────────────────────────────────────────────
# 嚴格模式（-e 失敗即離開 / -u 未宣告變數視為錯誤 / -o pipefail pipe 任一段失敗即失敗）。
set -euo pipefail
IFS=$'\n\t'

# ──────────────────────────────────────────────────────────────────────
# Section 1 — 路徑解析（不依賴 cwd）
# ──────────────────────────────────────────────────────────────────────
# 本 script 位於 srv/helper_scripts/ci/，故 srv/ root = $(dirname)/../..
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUST_CRATE_DIR="$SRV_ROOT/rust/openclaw_engine"
# cargo workspace（2026-04-15 合併後）artifact emit 到 rust/target/<profile>/。
# 審 **debug**（unstripped）——release 被 [profile.release] strip="symbols" 中和。
RUST_TARGET_DIR="$SRV_ROOT/rust/target/debug"
BIN_NAME="openclaw-engine"
BIN_PATH_DEFAULT="$RUST_TARGET_DIR/$BIN_NAME"
# 允許 caller 以 $IBKR_G4_AUDIT_BIN 覆寫（正控 / CI matrix 用：指向 g4 bin 驗 pattern 有牙）。
BIN_PATH="${IBKR_G4_AUDIT_BIN:-$BIN_PATH_DEFAULT}"

# ──────────────────────────────────────────────────────────────────────
# Section 2 — 日誌輔助（輸出到 stderr，保持 stdout 乾淨供 CI grep）
# ──────────────────────────────────────────────────────────────────────
log() {
    printf '[ibkr_g4_symbol_audit] %s\n' "$*" >&2
}

# ──────────────────────────────────────────────────────────────────────
# Section 3 — cargo 解析（非 login shell 找不到 bare `cargo` → 誤報 exit 2）
# ──────────────────────────────────────────────────────────────────────
# 依序：顯式 $CARGO env → $HOME/.cargo/bin/cargo（rustup 標準安裝）→ PATH 上的 cargo。
resolve_cargo() {
    if [[ -n "${CARGO:-}" && -x "${CARGO:-}" ]]; then
        printf '%s' "$CARGO"
        return 0
    fi
    if [[ -x "$HOME/.cargo/bin/cargo" ]]; then
        printf '%s' "$HOME/.cargo/bin/cargo"
        return 0
    fi
    if command -v cargo >/dev/null 2>&1; then
        command -v cargo
        return 0
    fi
    return 1
}

# ──────────────────────────────────────────────────────────────────────
# Section 4 — 建置階段（**default debug build，無 --release、無 --features**）
# ──────────────────────────────────────────────────────────────────────
build_binary() {
    if [[ "${SKIP_BUILD:-0}" == "1" && -f "$BIN_PATH" ]]; then
        log "SKIP_BUILD=1 + binary exists → skip cargo build"
        return 0
    fi

    local cargo_bin
    if ! cargo_bin="$(resolve_cargo)"; then
        log "BUILD FAIL: cargo not found (set \$CARGO or install rustup ~/.cargo/bin)"
        exit 2
    fi
    log "using cargo: $cargo_bin"

    log "$cargo_bin build --package openclaw_engine --bin $BIN_NAME (debug, NO --features) ..."
    # 關鍵：**絕不**帶 --release（會 strip）也不帶 --features ibkr_g4_contact。
    if ! (
        cd "$RUST_CRATE_DIR" && \
        "$cargo_bin" build \
            --package openclaw_engine \
            --bin "$BIN_NAME"
    ); then
        log "BUILD FAIL: cargo build returned non-zero"
        exit 2
    fi
    log "build OK"
}

# ──────────────────────────────────────────────────────────────────────
# Section 5 — 工具偵測（nm 缺席 → exit 3，不 fall-through 到 false-PASS）
# ──────────────────────────────────────────────────────────────────────
probe_nm() {
    if ! command -v nm >/dev/null 2>&1; then
        log "NM NOT FOUND: 'nm' command absent in \$PATH"
        log "  install: macOS → xcode-select --install / Linux → apt install binutils"
        exit 3
    fi
    log "nm available: $(command -v nm)"
}

# ──────────────────────────────────────────────────────────────────────
# Section 6 — 二進位存在性檢查
# ──────────────────────────────────────────────────────────────────────
check_binary() {
    if [[ ! -f "$BIN_PATH" ]]; then
        log "BINARY NOT FOUND: $BIN_PATH"
        log "  hint: rerun without SKIP_BUILD or adjust IBKR_G4_AUDIT_BIN"
        exit 4
    fi
    log "binary path: $BIN_PATH"
}

# ──────────────────────────────────────────────────────────────────────
# Section 7 — symbol dump（**全 symtab**，含 local；跨平台 plain `nm`）
# ──────────────────────────────────────────────────────────────────────
# 為什麼 plain `nm`（非 `nm -gU` / `--extern-only`）：需完整 .symtab 才能（a）鑑別
# stripped/empty（conclusive gate）與（b）抓 pub(crate)/local 連接器符號。BSD nm 與 GNU nm
# 的 plain 形式皆列 .symtab 全部符號；stripped binary 則 nm 無輸出（非零退出，2>/dev/null 吞）。
dump_symbols() {
    nm "$BIN_PATH" 2>/dev/null || true
}

# ──────────────────────────────────────────────────────────────────────
# Section 8 — 禁用 symbol 模式（IBKR B1 連接器接觸面）
# ──────────────────────────────────────────────────────────────────────
# 每個 pattern 對應一個 violation class；任一 hit ≥ 1 → AUDIT FAIL。ERE（POSIX grep -E）。
declare -a FORBIDDEN_PATTERNS=(
    # [主] 唯一具體 TcpStream::connect 的 gated 函數；default build 必 absent。
    'g4_operator_triggered_first_contact'

    # [主] G4 觸發 bin 符號（required-features gated；引擎 artifact 內必 absent）。
    'ibkr_g4_first_contact'

    # [模塊級回歸 gate] 整個只讀 TWS 連接器模塊。default build 因 0 production caller 被 DCE
    # → 0 hits（honest PASS）。若未來誤接 production caller（driver / codec / gate 任一被
    # 引用），模塊符號即現身 → fail。取代舊版恆 0 的死 pattern `ibkr_readonly_tws_client.*connect`
    # （真 connect 符號是 `tokio::net::...connect`，無此模塊前綴，故舊 pattern 永不命中）。
    'ibkr_readonly_tws_client'
)

# ──────────────────────────────────────────────────────────────────────
# Section 9 — 稽核階段（先 conclusive gate，再 forbidden grep）
# ──────────────────────────────────────────────────────────────────────
audit_symbols() {
    local symbols
    symbols="$(dump_symbols)"

    # conclusive gate #1：總符號數（非空行）。0 = stripped / 空 symtab → fail-closed。
    local total
    total="$(printf '%s\n' "$symbols" | grep -c . || true)"
    if [[ "${total:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: 0 symbols in .symtab (binary stripped or empty)"
        log "  → security gate cannot discriminate → fail-closed (do NOT report PASS)"
        log "  → ensure you audit an UNSTRIPPED artifact (debug build, not release)"
        exit 5
    fi

    # conclusive gate #2：anchor。debug 引擎 artifact 必含大量 `openclaw_engine` 前綴符號；
    # 若 0 = stripped / 錯 binary → 無法證明 symtab 有料 → fail-closed。
    local anchor
    anchor="$(printf '%s\n' "$symbols" | grep -c 'openclaw_engine' || true)"
    if [[ "${anchor:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: no 'openclaw_engine' anchor symbols (stripped / wrong binary)"
        log "  → cannot prove symtab is populated → fail-closed (do NOT report PASS)"
        exit 5
    fi
    log "conclusive: total_symbols=$total anchor(openclaw_engine)=$anchor"

    local fail_count=0
    local pattern label hits sample

    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        # grep 無命中回 exit 1（POSIX），用 || true 防 set -e 中止。
        hits="$(printf '%s\n' "$symbols" | grep -E -c "$pattern" || true)"

        if [[ "${hits:-0}" -gt 0 ]]; then
            label="$(printf '%s' "$pattern" | tr '|' ',' | head -c 60)"
            log "FORBIDDEN HIT [$label]: $hits symbol(s)"
            # grep -m5 自限 5 條（不用 `| head -5`，避免 head 提早關管道致上游 SIGPIPE）；
            # `|| true` 吸收「大符號表下 printf 仍可能 SIGPIPE(141)」殘餘，確保賦值成功、
            # 迴圈走完所有 pattern 並抵達 `exit 1`（修 E4 抓的 exit-141-vs-1 契約 bug）。
            sample="$(printf '%s\n' "$symbols" | grep -E -m5 "$pattern" || true)"
            printf '%s\n' "$sample" | while IFS= read -r line; do
                log "  | $line"
            done
            fail_count=$((fail_count + 1))
        fi
    done

    if [[ "$fail_count" -gt 0 ]]; then
        log "AUDIT FAIL: $fail_count forbidden symbol class(es) detected"
        log "  → IBKR B1 TWS connector surface leaked into default engine artifact"
        log "  → fix: keep gated fn + G4 bin behind ibkr_g4_contact feature; add NO production caller"
        exit 1
    fi

    log "AUDIT PASS: 0 forbidden symbol ($total symbols scanned, anchor=$anchor)"
    exit 0
}

# ──────────────────────────────────────────────────────────────────────
# Section 10 — 主入口
# ──────────────────────────────────────────────────────────────────────
main() {
    log "=== ibkr g4 symbol audit start ==="
    log "srv root: $SRV_ROOT"
    log "platform: $(uname -s) $(uname -m)"

    probe_nm
    build_binary
    check_binary
    audit_symbols
}

# 被 source（非執行）時不跑 main（讓 test harness 可 source 後測 helper）。
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ibkr_fake_tws_absence_audit.sh — IBKR-CI-3 (b) fake-TWS 缺席審計（縱深防禦）。
#
# MODULE_NOTE (中):
#   兩道機器斷言,對齊 helper_scripts/ci/ibkr_g4_symbol_audit.sh 的 fail-closed / 正控 範式:
#
#   Part 1 — **default engine artifact 零 fake_tws 符號**（nm）:
#     `openclaw_fake_tws` 是 engine 的 **dev-dependency**（見 tests/structure/
#     test_ibkr_fake_tws_devdep_only.py 斷言）→ default `cargo build` **根本不編譯它** → 引擎
#     artifact 內零 `fake_tws` 符號（結構性缺席,非屬性標註）。任一符號出現 = 有人誤把 fake crate
#     接進 production dep,把測試 harness 拉進 live 引擎。審 **unstripped debug** artifact（release
#     被 [profile.release] strip="symbols" 中和 → 無鑑別力）。
#
#   Part 2 — **fake crate 自身零真實 socket 符號**（源級掃描,conclusive）:
#     fake crate 純 in-process 記憶體雙工,絕不引用任何真實網路連線型別。掃 rust/openclaw_fake_tws/
#     src/ 全源:任一真 socket token（TCP 連線/監聽 struct、標準庫 net 家族、tokio net 家族、Unix
#     socket 家族）出現 → FAIL。源級掃描為 conclusive（不依 nm 對 rlib 的 vacuous-absence）;in-crate
#     `#[test] source_has_no_real_socket_symbols` 為第一道,本 script 為 CI 層第二道。
#
#   **fail-closed on inconclusive**：安全 gate 無法驗證時必 fail-closed。binary stripped（.symtab
#   空）/ 總符號=0 / 缺 openclaw_engine anchor / fake src 目錄缺 → exit 5（不報 PASS）。
#
#   正控（驗 script 有牙,IBKR_FAKE_TWS_AUDIT_BIN 覆寫）：必須指向 **engine 的 lib-test binary**
#   （`openclaw_engine-<hash>`,dev-dep 連入 fake,同時含 `openclaw_engine` anchor + `openclaw_fake_tws`
#   符號）跑 Part 1 → pattern 命中 → AUDIT FAIL（exit 1）;證 pattern 非死。**勿指 fake crate 自身的
#   standalone unittest bin**——它 engine-independent、無 `openclaw_engine` anchor,會先觸 fail-closed
#   exit 5（INCONCLUSIVE）而非 exit 1,只證 anchor 守衛有牙、證不了 fake 符號偵測有牙（E4 2026-07-16 實證）。
#
#   Exit code：
#     0  AUDIT PASS       — engine 零 fake 符號 且 fake src 零 socket token
#     1  AUDIT FAIL       — ≥1 fake 符號於 engine artifact,或 fake src 含真 socket token
#     2  BUILD FAIL       — cargo 缺席 / cargo build 失敗
#     3  NM NOT FOUND     — 環境無 nm
#     4  BINARY NOT FOUND — 找不到 target/debug/openclaw-engine
#     5  INCONCLUSIVE     — stripped / 空 symtab / 缺 anchor / fake src 缺（fail-closed）
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
IFS=$'\n\t'

# ── Section 1 — 路徑解析（不依賴 cwd;本 script 於 srv/helper_scripts/ci/）─────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUST_CRATE_DIR="$SRV_ROOT/rust/openclaw_engine"
RUST_TARGET_DIR="$SRV_ROOT/rust/target/debug"
BIN_NAME="openclaw-engine"
BIN_PATH_DEFAULT="$RUST_TARGET_DIR/$BIN_NAME"
BIN_PATH="${IBKR_FAKE_TWS_AUDIT_BIN:-$BIN_PATH_DEFAULT}"
FAKE_SRC_DIR="$SRV_ROOT/rust/openclaw_fake_tws/src"

log() { printf '[ibkr_fake_tws_absence_audit] %s\n' "$*" >&2; }

# ── Section 2 — cargo 解析（非 login shell 找不到 bare cargo）──────────────────
resolve_cargo() {
    if [[ -n "${CARGO:-}" && -x "${CARGO:-}" ]]; then printf '%s' "$CARGO"; return 0; fi
    if [[ -x "$HOME/.cargo/bin/cargo" ]]; then printf '%s' "$HOME/.cargo/bin/cargo"; return 0; fi
    if command -v cargo >/dev/null 2>&1; then command -v cargo; return 0; fi
    return 1
}

# ── Section 3 — 建置（default debug,無 --release、無 --features）────────────────
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
    if ! ( cd "$RUST_CRATE_DIR" && "$cargo_bin" build --package openclaw_engine --bin "$BIN_NAME" ); then
        log "BUILD FAIL: cargo build returned non-zero"
        exit 2
    fi
    log "build OK"
}

probe_nm() {
    if ! command -v nm >/dev/null 2>&1; then
        log "NM NOT FOUND: 'nm' absent in \$PATH (macOS: xcode-select --install / Linux: binutils)"
        exit 3
    fi
    log "nm available: $(command -v nm)"
}

check_binary() {
    if [[ ! -f "$BIN_PATH" ]]; then
        log "BINARY NOT FOUND: $BIN_PATH (rerun without SKIP_BUILD or set IBKR_FAKE_TWS_AUDIT_BIN)"
        exit 4
    fi
    log "binary path: $BIN_PATH"
}

dump_symbols() { nm "$BIN_PATH" 2>/dev/null || true; }

# ── Section 4 — Part 1:nm engine artifact 零 fake_tws 符號 ─────────────────────
# fake crate 符號類別（任一 hit ≥1 → FAIL）。ERE。
declare -a FORBIDDEN_PATTERNS=(
    'openclaw_fake_tws'
    'fake_tws'
)

audit_engine_symbols() {
    local symbols total anchor
    symbols="$(dump_symbols)"
    total="$(printf '%s\n' "$symbols" | grep -c . || true)"
    if [[ "${total:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: 0 symbols in .symtab (binary stripped or empty) → fail-closed"
        exit 5
    fi
    anchor="$(printf '%s\n' "$symbols" | grep -c 'openclaw_engine' || true)"
    if [[ "${anchor:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: no 'openclaw_engine' anchor symbols (stripped / wrong binary) → fail-closed"
        exit 5
    fi
    log "conclusive: total_symbols=$total anchor(openclaw_engine)=$anchor"

    local fail_count=0 pattern hits sample
    for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        hits="$(printf '%s\n' "$symbols" | grep -E -c "$pattern" || true)"
        if [[ "${hits:-0}" -gt 0 ]]; then
            log "FORBIDDEN HIT [$pattern]: $hits symbol(s)"
            sample="$(printf '%s\n' "$symbols" | grep -E -m5 "$pattern" || true)"
            printf '%s\n' "$sample" | while IFS= read -r line; do log "  | $line"; done
            fail_count=$((fail_count + 1))
        fi
    done
    if [[ "$fail_count" -gt 0 ]]; then
        log "AUDIT FAIL (Part 1): $fail_count fake_tws symbol class(es) in default engine artifact"
        log "  → fake harness leaked into live engine (someone made it a production dep?)"
        exit 1
    fi
    log "Part 1 PASS: 0 fake_tws symbol in default engine artifact ($total scanned)"
}

# ── Section 5 — Part 2:fake crate src 零真實 socket token（源級 conclusive）─────
# needle 以拆段拼接,令本 script 源碼不含 verbatim token（避免 self-scan;雖本 script 不被掃,守慣例）。
audit_fake_src_no_socket() {
    if [[ ! -d "$FAKE_SRC_DIR" ]]; then
        log "INCONCLUSIVE: fake crate src dir absent: $FAKE_SRC_DIR → fail-closed"
        exit 5
    fi
    local files
    files="$(find "$FAKE_SRC_DIR" -name '*.rs' -type f 2>/dev/null || true)"
    if [[ -z "$files" ]]; then
        log "INCONCLUSIVE: no .rs under $FAKE_SRC_DIR → fail-closed"
        exit 5
    fi
    # 真實 socket token（ERE,拆段拼接防 self-match）。
    local t1="Tcp""Stream" t2="Tcp""Listener" t3="Unix""Stream" t4="Unix""Listener"
    local t5="std""::net" t6="tokio""::net"
    local pattern="$t1|$t2|$t3|$t4|$t5|$t6"
    local hits
    hits="$(grep -R -E -n "$pattern" $files 2>/dev/null || true)"
    if [[ -n "$hits" ]]; then
        log "AUDIT FAIL (Part 2): fake crate src contains real socket token(s):"
        printf '%s\n' "$hits" | head -5 | while IFS= read -r line; do log "  | $line"; done
        exit 1
    fi
    log "Part 2 PASS: fake crate src has 0 real socket token ($(printf '%s\n' "$files" | grep -c . ) file(s))"
}

main() {
    log "=== ibkr fake-tws absence audit start ==="
    log "srv root: $SRV_ROOT"
    log "platform: $(uname -s) $(uname -m)"
    probe_nm
    build_binary
    check_binary
    audit_engine_symbols
    # 正控模式（IBKR_FAKE_TWS_AUDIT_BIN 指向 fake 測試 binary）只驗 Part 1 有牙,跳過 Part 2 源掃描。
    if [[ -z "${IBKR_FAKE_TWS_AUDIT_BIN:-}" ]]; then
        audit_fake_src_no_socket
    else
        log "Part 2 skipped (positive-control mode: IBKR_FAKE_TWS_AUDIT_BIN set)"
    fi
    log "AUDIT PASS: fake-tws absent from engine artifact + fake src socket-free"
    exit 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# ibkr_driver_absence_audit.sh — IBKR W4 driver-absence 稽核（縱深防禦 / defense in depth）。
#
# MODULE_NOTE (中):
#   驗證 **default `cargo build`（debug，無 --features）的 `openclaw-engine` artifact** 的
#   **W4 移交邊界**（設計 §5）：
#
#     W4 接的是 **health 狀態查詢管線**（manager-only）,**非 driver 真啟動**。W4 emitter 的
#     production caller 只到 `TwsSessionManager`（`ibkr_tws_session` + `ibkr_tws_pacing`）——
#     此二模塊在 W4 **首度有 production caller,移出 DCE**（正向存在）。但 driver
#     （`ibkr_tws_driver`：`SessionDriver`/`TransportFactory`/`send_framed`）需注入
#     `TransportFactory`＝W8 TCP factory（真 socket）,W4 不具備 → driver **仍 production-DCE**
#     （負向缺席）。真 transport＝真 socket＝W4 禁止。
#
#   兩道機器斷言：
#     Part A（正向存在 / conclusive）：`ibkr_tws_session` 符號 **≥1**——證 W4 已把 manager 接進
#       production（否則 W4 接線regress → manager 又被 DCE → 本 audit 無鑑別力 → fail-closed）。
#     Part B（負向缺席 / 主保證）：`ibkr_tws_driver` 符號 **=0**——driver 面（driver/factory/
#       serve-loop/send_framed）於 default artifact 缺席。任一符號出現 = 有人誤把 driver 接進
#       production caller（把真 transport / serve loop 拉進 live 引擎）→ FAIL。
#
#   **主保證不是本 script**：L1 = 0-caller DCE（manager 不引用 driver → 構造 manager 不把 driver
#   拉出 DCE）+ driver 需 `ibkr_transport_tcp` feature 的 TCP factory（W8）。本 script 為 L3
#   回歸 gate——誤接 production driver caller 時符號現身 → 本 script fail。審 **unstripped debug**
#   （release 被 [profile.release] strip="symbols" 中和 → 無鑑別力）。
#
#   **fail-closed on inconclusive**：安全 gate 無法驗證時必 fail-closed。stripped / 總符號=0 /
#   缺 openclaw_engine anchor / **缺 ibkr_tws_session anchor（W4 manager 未接）** → exit 5。
#
#   正控（驗 script 有牙,IBKR_DRIVER_AUDIT_BIN 覆寫）：指向 engine lib-test binary
#   （`openclaw_engine-<hash>`,#[cfg(test)] 連入 driver 測試 → 含 `ibkr_tws_driver` 符號 +
#   `openclaw_engine`/`ibkr_tws_session` anchor）跑 Part B → pattern 命中 → AUDIT FAIL（exit 1）;
#   證 pattern 非死。
#
#   Exit code：
#     0  AUDIT PASS       — session 存在（W4 已接）且 0 driver 符號
#     1  AUDIT FAIL       — ≥1 driver 符號於 default engine artifact
#     2  BUILD FAIL       — cargo 缺席 / cargo build 失敗
#     3  NM NOT FOUND     — 環境無 nm
#     4  BINARY NOT FOUND — 找不到 target/debug/openclaw-engine
#     5  INCONCLUSIVE     — stripped / 空 symtab / 缺 engine anchor / 缺 session anchor（fail-closed）
#
#   契約來源：
#     - docs/execution_plan/ibkr_live_capability/2026-07-16--w4_connection_health_ipc_design.md §5
#     - 仿 helper_scripts/ci/ibkr_fake_tws_absence_audit.sh / ibkr_g4_symbol_audit.sh（symbol-audit 範式）
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
BIN_PATH="${IBKR_DRIVER_AUDIT_BIN:-$BIN_PATH_DEFAULT}"

log() { printf '[ibkr_driver_absence_audit] %s\n' "$*" >&2; }

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
        log "BINARY NOT FOUND: $BIN_PATH (rerun without SKIP_BUILD or set IBKR_DRIVER_AUDIT_BIN)"
        exit 4
    fi
    log "binary path: $BIN_PATH"
}

dump_symbols() { nm "$BIN_PATH" 2>/dev/null || true; }

# ── Section 4 — 稽核（先 conclusive gates,再 Part A 正向存在 + Part B 負向缺席）──
# driver 符號類別（任一 hit ≥1 → FAIL）。ERE。module 路徑前綴 catch 全 driver 符號
# （SessionDriver / TransportFactory / send_framed 皆在 ibkr_tws_driver 模塊）。
declare -a FORBIDDEN_PATTERNS=(
    'ibkr_tws_driver'
)

audit_symbols() {
    local symbols total anchor session_anchor
    symbols="$(dump_symbols)"

    # conclusive gate #1：總符號數。0 = stripped / 空 symtab → fail-closed。
    total="$(printf '%s\n' "$symbols" | grep -c . || true)"
    if [[ "${total:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: 0 symbols in .symtab (binary stripped or empty) → fail-closed"
        exit 5
    fi

    # conclusive gate #2：openclaw_engine anchor。
    anchor="$(printf '%s\n' "$symbols" | grep -c 'openclaw_engine' || true)"
    if [[ "${anchor:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: no 'openclaw_engine' anchor symbols (stripped / wrong binary) → fail-closed"
        exit 5
    fi

    # Part A（正向存在 / conclusive gate #3）：ibkr_tws_session 必存在——證 W4 已把 manager
    # 接進 production;若為 0 = W4 接線regress（manager 又被 DCE）→ 本 audit 無鑑別力 → fail-closed。
    session_anchor="$(printf '%s\n' "$symbols" | grep -c 'ibkr_tws_session' || true)"
    if [[ "${session_anchor:-0}" -eq 0 ]]; then
        log "INCONCLUSIVE: no 'ibkr_tws_session' symbols — W4 manager caller absent (wiring regressed?)"
        log "  → cannot prove driver-absence is meaningful → fail-closed (do NOT report PASS)"
        exit 5
    fi
    log "conclusive: total=$total engine_anchor=$anchor session_anchor(Part A)=$session_anchor"

    # Part B（負向缺席 / 主保證）：ibkr_tws_driver 必缺席。
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
        log "AUDIT FAIL (Part B): $fail_count driver symbol class(es) in default engine artifact"
        log "  → W4 must stay manager-only; driver needs W8 TCP factory (real socket) → keep DCE"
        exit 1
    fi

    log "AUDIT PASS: session present (W4 wired) + 0 driver symbol ($total scanned, session=$session_anchor)"
    exit 0
}

main() {
    log "=== ibkr driver-absence audit start ==="
    log "srv root: $SRV_ROOT"
    log "platform: $(uname -s) $(uname -m)"
    probe_nm
    build_binary
    check_binary
    audit_symbols
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

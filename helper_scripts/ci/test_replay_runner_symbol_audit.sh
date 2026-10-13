#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# test_replay_runner_symbol_audit.sh — REF-20 Wave 3 R20-P2b-S10 test harness
# replay_runner symbol audit 測試套
#
# MODULE_NOTE (EN):
#   Mock-based bash test harness for `replay_runner_symbol_audit.sh`.
#
#   Why mock instead of real cargo build:
#     - cargo build --release for replay_runner is slow (~30-60s on Mac M-series)
#     - real audit verification belongs to CI matrix; this harness only proves
#       the audit script's logic correctness given known symbol input
#     - mocking nm + binary file allows deterministic test cases
#       (clean symbol set / forbidden symbol injected / nm absent / etc.)
#
#   Test cases (5 total):
#     T1 clean binary    : mock nm output WITHOUT forbidden symbols → exit 0
#     T2 forbidden hit   : mock nm output WITH 'acquire_lease' symbol → exit 1
#     T3 nm absent       : PATH stripped of nm → exit 3
#     T4 binary missing  : REPLAY_RUNNER_BIN points to non-existent file → exit 4
#     T5 multi-class hit : mock nm output WITH 3 forbidden classes → exit 1
#
#   Convention: each test prints "T<N> PASS" / "T<N> FAIL <reason>" and exits
#   non-zero on any failure. Final summary prints PASS / FAIL count.
#
# MODULE_NOTE (中):
#   `replay_runner_symbol_audit.sh` 的 mock-based bash 測試套。
#
#   為什麼用 mock 而非真 cargo build：
#     - cargo build --release replay_runner 很慢（Mac M 系列約 30-60 秒）
#     - 真 audit 驗證應在 CI matrix 完成；本 harness 只證 audit script 邏輯
#       對特定 symbol input 的判斷正確性
#     - mock nm + binary 檔讓測試 case 可決定論
#       （乾淨 symbol set / 注入 forbidden symbol / nm 缺席 / 等）
#
#   測試 case（共 5）：
#     T1 乾淨 binary    : mock nm 輸出無 forbidden symbol → exit 0
#     T2 命中 forbidden : mock nm 輸出含 'acquire_lease' → exit 1
#     T3 nm 缺席        : PATH 剝離 nm → exit 3
#     T4 binary 不存在  : REPLAY_RUNNER_BIN 指向不存在檔 → exit 4
#     T5 多 class 命中  : mock nm 輸出含 3 種 forbidden class → exit 1
#
#   慣例：每個 test 印 "T<N> PASS" / "T<N> FAIL <原因>"，任一失敗整體 exit 非 0。
#         最後印 PASS / FAIL 總數。
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIT_SCRIPT="$SCRIPT_DIR/replay_runner_symbol_audit.sh"

PASS_COUNT=0
FAIL_COUNT=0
FAILED_TESTS=()

# ──────────────────────────────────────────────────────────────────────
# Section 1 — Test infrastructure / 測試基礎設施
# ──────────────────────────────────────────────────────────────────────
# tmpdir per test 隔離 mock；trap EXIT 確保清理
# Per-test tmpdir for mock isolation; trap EXIT for cleanup
make_tmpdir() {
    mktemp -d -t replay_audit_test.XXXXXX
}

# 構造 mock nm shim：寫入 tmpdir/bin/nm，輸出固定 symbol set
# Build mock nm shim: write tmpdir/bin/nm, emit fixed symbol set
make_mock_nm() {
    local tmpdir="$1"
    local symbol_payload="$2"
    local mock_bin="$tmpdir/bin"
    mkdir -p "$mock_bin"
    cat >"$mock_bin/nm" <<EOF
#!/usr/bin/env bash
# Mock nm shim for test_replay_runner_symbol_audit.sh
# Mock nm shim — 測試用，回固定 symbol set
cat <<'SYMS'
$symbol_payload
SYMS
EOF
    chmod 0755 "$mock_bin/nm"
    printf '%s' "$mock_bin"
}

# 構造空 mock binary 檔（audit script 只 stat 存在性，不解析內容）
# Create empty mock binary (audit script only stats existence, doesn't parse)
make_mock_binary() {
    local tmpdir="$1"
    local mock_bin_path="$tmpdir/replay_runner_mock"
    : > "$mock_bin_path"
    chmod 0755 "$mock_bin_path"
    printf '%s' "$mock_bin_path"
}

# 跑 audit script + 比對 expected exit code
# Run audit script, compare to expected exit code
# 用法：run_audit <expected_exit> <mock_PATH> <REPLAY_RUNNER_BIN>
# Usage: run_audit <expected_exit> <mock_PATH> <REPLAY_RUNNER_BIN>
run_audit() {
    local expected_exit="$1"
    local mock_path="$2"
    local mock_bin="$3"

    # 透過 SKIP_BUILD=1 跳過 cargo（測試 layer 不需 real build）
    # SKIP_BUILD=1 skips cargo (test layer doesn't need real build)
    local actual_exit=0
    SKIP_BUILD=1 \
    REPLAY_RUNNER_BIN="$mock_bin" \
    PATH="$mock_path:$PATH" \
        bash "$AUDIT_SCRIPT" >/dev/null 2>&1 || actual_exit=$?

    if [[ "$actual_exit" -eq "$expected_exit" ]]; then
        return 0
    else
        printf '  expected exit=%s actual exit=%s\n' "$expected_exit" "$actual_exit" >&2
        return 1
    fi
}

# Test runner with PASS / FAIL accounting
# 測試 runner（PASS / FAIL 統計）
record_test() {
    local name="$1"
    local outcome="$2"  # 0=PASS / non-0=FAIL
    if [[ "$outcome" -eq 0 ]]; then
        PASS_COUNT=$((PASS_COUNT + 1))
        printf '%s PASS\n' "$name"
    else
        FAIL_COUNT=$((FAIL_COUNT + 1))
        FAILED_TESTS+=("$name")
        printf '%s FAIL\n' "$name"
    fi
}

# ──────────────────────────────────────────────────────────────────────
# Section 2 — Symbol fixtures / Symbol 樣本資料
# ──────────────────────────────────────────────────────────────────────
# 乾淨 symbol set（典型 Rust release binary 含的合法 symbol）
# Clean symbol set (typical Rust release binary's legitimate symbols)
CLEAN_SYMBOLS='0000000100001234 T _main
0000000100001900 t _openclaw_engine::replay::runner::IsolatedPipeline
0000000100002000 T _replay_runner::main
0000000100002500 T _replay_runner::ReplayProfile::Isolated
0000000100003000 T _hmac::Mac::sign
0000000100003500 T _serde_json::from_str
0000000100004000 T _chrono::DateTime::now
0000000100004500 T _tracing::event
0000000100005000 T _std::io::Write
0000000100005500 T _std::panicking::begin_panic
0000000100006000 T _alloc::vec::Vec::push'

# 含 acquire_lease 的 symbol set（單一 forbidden class hit）
# Symbol set containing acquire_lease (single forbidden class hit)
ACQUIRE_LEASE_SYMBOLS="$CLEAN_SYMBOLS
0000000100099000 T _governance_hub::acquire_lease"

# 含 3 種 forbidden class（multi-hit）
# Multi-hit: contains 3 forbidden classes
MULTI_FORBIDDEN_SYMBOLS="$CLEAN_SYMBOLS
0000000100099000 T _governance_hub::acquire_lease
0000000100099100 T _ipc_server::dispatch::handle
0000000100099200 T _bybit_rest::place_order"

# ──────────────────────────────────────────────────────────────────────
# Section 3 — Test cases / 測試案例
# ──────────────────────────────────────────────────────────────────────

# T1 — 乾淨 binary：mock nm 回 clean symbol → exit 0
# T1 — clean binary: mock nm returns clean symbols → exit 0
test_t1_clean() {
    local tmpdir mock_path mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN

    mock_path="$(make_mock_nm "$tmpdir" "$CLEAN_SYMBOLS")"
    mock_bin="$(make_mock_binary "$tmpdir")"

    run_audit 0 "$mock_path" "$mock_bin"
}

# T2 — 命中 forbidden：mock nm 回 acquire_lease → exit 1
# T2 — forbidden hit: mock nm returns acquire_lease → exit 1
test_t2_forbidden_hit() {
    local tmpdir mock_path mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN

    mock_path="$(make_mock_nm "$tmpdir" "$ACQUIRE_LEASE_SYMBOLS")"
    mock_bin="$(make_mock_binary "$tmpdir")"

    run_audit 1 "$mock_path" "$mock_bin"
}

# T3 — nm 缺席：PATH 只含 essentials（wc/grep/tr/cat 等），故意排除 nm → exit 3
# T3 — nm absent: PATH contains essentials only (wc/grep/tr/cat etc.),
#                 deliberately excluding nm → exit 3
test_t3_nm_absent() {
    local tmpdir mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN

    mock_bin="$(make_mock_binary "$tmpdir")"

    # 構造 isolated bin dir：symlink essential 工具的真實 binary path 進來但不含 nm
    # 注：用 `type -P` 而非 `command -v`，後者對 shell function/alias 也回 match
    #     audit script 內部用了 wc / grep / tr / cat / printf / dirname / mktemp / uname / mkdir
    #     這些必須在 PATH 上才能跑；nm 缺席讓 `command -v nm` 失敗 → exit 3
    #     Bash 本身不需在此 PATH；我們呼叫時用 absolute path /bin/bash
    # Build isolated bin dir: symlink real binary path of essential tools, exclude nm.
    # Note: use `type -P` (returns binary path) instead of `command -v`
    #       (returns function/alias if shadowed). audit script uses
    #       wc / grep / tr / cat / printf / dirname / mktemp / uname / mkdir
    #       These must be on PATH; nm absent → command -v nm fail → audit exit 3
    #       bash itself doesn't need to be on this PATH; we invoke via absolute /bin/bash
    local isolated_bin="$tmpdir/bin_no_nm"
    mkdir -p "$isolated_bin"
    local tool tool_path
    for tool in wc grep tr cat dirname mktemp uname mkdir ln rm head; do
        # type -P 強制回傳磁碟 binary path；shell function/alias 回空
        # type -P forces disk binary path; shell function/alias returns empty
        tool_path="$(type -P "$tool" 2>/dev/null || true)"
        if [[ -n "$tool_path" && -x "$tool_path" ]]; then
            ln -sf "$tool_path" "$isolated_bin/$tool"
        fi
    done
    # 注意：故意不 symlink nm；讓 audit script's command -v nm 失敗
    # Note: deliberately do NOT symlink nm; let audit script command -v nm fail

    # 用 absolute /bin/bash 呼叫，避免 PATH 隔離後找不到 bash
    # Use absolute /bin/bash to avoid bash-not-found under isolated PATH
    local bash_bin
    bash_bin="$(type -P bash 2>/dev/null || echo /bin/bash)"

    local actual_exit=0
    SKIP_BUILD=1 \
    REPLAY_RUNNER_BIN="$mock_bin" \
    PATH="$isolated_bin" \
        "$bash_bin" "$AUDIT_SCRIPT" >/dev/null 2>&1 || actual_exit=$?

    if [[ "$actual_exit" -eq 3 ]]; then
        return 0
    else
        printf '  expected exit=3 actual exit=%s\n' "$actual_exit" >&2
        return 1
    fi
}

# T4 — binary 不存在：REPLAY_RUNNER_BIN 指向不存在檔 → exit 4
# T4 — binary missing: REPLAY_RUNNER_BIN points to non-existent file → exit 4
test_t4_binary_missing() {
    local tmpdir mock_path
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN

    mock_path="$(make_mock_nm "$tmpdir" "$CLEAN_SYMBOLS")"
    # 故意指 not-exist 檔
    # Intentionally point to non-existent file
    local nonexistent="$tmpdir/this_file_does_not_exist"

    run_audit 4 "$mock_path" "$nonexistent"
}

# T5 — 多 class hit：mock nm 回 3 種 forbidden → exit 1
# T5 — multi-class hit: mock nm returns 3 forbidden classes → exit 1
test_t5_multi_hit() {
    local tmpdir mock_path mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN

    mock_path="$(make_mock_nm "$tmpdir" "$MULTI_FORBIDDEN_SYMBOLS")"
    mock_bin="$(make_mock_binary "$tmpdir")"

    run_audit 1 "$mock_path" "$mock_bin"
}

# 新案例只擴充覆蓋，不改既有五個案例的斷言。
test_symbol_table_rejected() {
    local payload="$1" tmpdir mock_path mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN
    mock_path="$(make_mock_nm "$tmpdir" "$payload")"
    mock_bin="$(make_mock_binary "$tmpdir")"
    run_audit 5 "$mock_path" "$mock_bin"
}
test_positive_control() {
    local output actual_exit=0
    output="$(bash "$AUDIT_SCRIPT" --self-test 2>&1)" || actual_exit=$?
    # 偵測有效時對外回 0，且輸出必須同時含命中紀錄與通過標記。
    [[ "$actual_exit" -eq 0 && "$output" == *"FORBIDDEN HIT"* && "$output" == *"SELF-TEST PASS"* ]]
}
test_full_symbols_platform() {
    local platform="$1" tmpdir mock_path mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN
    mock_path="$(make_mock_nm "$tmpdir" "$CLEAN_SYMBOLS")"
    mock_bin="$(make_mock_binary "$tmpdir")"
    cat >"$mock_path/uname" <<EOF
#!/bin/bash
printf '%s\n' '$platform'
EOF
    chmod +x "$mock_path/uname"
    # 若仍只掃外部符號，模擬 nm 必須拒絕，不能把分支測試寫成恆真。
    cat >"$mock_path/nm" <<EOF
#!/bin/bash
for arg in "\$@"; do
    case "\$arg" in -g*|-U|--extern-only|--defined-only) exit 19 ;; esac
done
cat <<'SYMS'
$CLEAN_SYMBOLS
SYMS
EOF
    run_audit 0 "$mock_path" "$mock_bin"
}

# 未解碼的符號表：兩個名稱都含 openclaw_engine／replay_runner 字樣，但沒有 `::`。
# 解碼沒有生效時，帶 `::` 的禁用樣式全部失效，稽核不得回報通過。
MANGLED_ONLY_SYMBOLS='0000000100001900 t __ZN15openclaw_engine6replay6runner16IsolatedPipeline7execute17h0123456789abcdefE
0000000100002000 T __ZN13replay_runner4main17h0123456789abcdefE
0000000100003000 T __ZN4hmac3Mac4sign17h0123456789abcdefE'

# 不經 SKIP_BUILD／REPLAY_RUNNER_BIN 的呼叫；用於建置前就該結束的案例。
test_cargo_output_override_is_inconclusive() {
    local variable="$1" tmpdir mock_path actual_exit=0
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN
    mock_path="$(make_mock_nm "$tmpdir" "$CLEAN_SYMBOLS")"
    # 模擬 cargo 一被呼叫就留下記號：防護必須在建置之前結束。
    printf '#!/bin/bash\n: > %q\nexit 0\n' "$tmpdir/cargo_was_called" >"$mock_path/cargo"
    chmod +x "$mock_path/cargo"
    env -u REPLAY_RUNNER_BIN -u SKIP_BUILD -u CARGO_TARGET_DIR -u CARGO_BUILD_TARGET_DIR -u CARGO_BUILD_TARGET \
        "$variable=$tmpdir/elsewhere" PATH="$mock_path:$PATH" \
        bash "$AUDIT_SCRIPT" >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 && ! -e "$tmpdir/cargo_was_called" ]]
}
test_unknown_argument_is_usage_error() {
    local actual_exit=0
    bash "$AUDIT_SCRIPT" "$@" >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 64 ]]
}
# 以 source 載入後覆寫內部陣列，驗證錯誤路徑；每個案例都在子殼內執行。
# 每個案例先跑一次未覆寫的對照（必須回 0），確認結束碼 5 來自覆寫而不是載入方式本身。
sourced_audit_passes_unmodified() {
    local control_exit=0
    ( source "$AUDIT_SCRIPT"; audit_symbols "$CLEAN_SYMBOLS" ) >/dev/null 2>&1 || control_exit=$?
    [[ "$control_exit" -eq 0 ]]
}
sourced_self_test_passes_unmodified() {
    local control_exit=0
    ( source "$AUDIT_SCRIPT"; main --self-test ) >/dev/null 2>&1 || control_exit=$?
    [[ "$control_exit" -eq 0 ]]
}
test_unusable_pattern_is_inconclusive() {
    local actual_exit=0
    sourced_audit_passes_unmodified || return 1
    ( source "$AUDIT_SCRIPT"; FORBIDDEN_PATTERNS=('('); audit_symbols "$CLEAN_SYMBOLS" ) >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 ]]
}
test_self_test_detects_broken_class() {
    local index="$1" actual_exit=0
    sourced_self_test_passes_unmodified || return 1
    ( source "$AUDIT_SCRIPT"; FORBIDDEN_PATTERNS[$index]='zzz_never_matches'; main --self-test ) >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 ]]
}
test_self_test_detects_overbroad_class() {
    local actual_exit=0
    sourced_self_test_passes_unmodified || return 1
    ( source "$AUDIT_SCRIPT"; FORBIDDEN_PATTERNS[1]='GovernanceHub|runner'; main --self-test ) >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 ]]
}
test_self_test_requires_one_sample_per_class() {
    local actual_exit=0
    sourced_self_test_passes_unmodified || return 1
    ( source "$AUDIT_SCRIPT"; FORBIDDEN_PATTERNS+=('new_forbidden_class'); main --self-test ) >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 ]]
}

# 未解碼、但泛型參數裡帶 `..` 的符號表：正規化後會出現 `openclaw_engine::` 字樣，
# 定位檢查必須仍以原始輸出判定為未解碼。
MANGLED_GENERIC_SYMBOLS='0000000100001900 t __ZN4core3ptr70drop_in_place$LT$openclaw_engine..replay..runner..IsolatedPipeline$GT$17h0123456789abcdefE
0000000100002000 T __ZN4core3ptr50drop_in_place$LT$replay_runner..cli..Args$GT$17h0123456789abcdefE'

# 禁用路徑只以泛型參數形式出現（`a..b`）：必須命中。
GENERIC_FORM_FORBIDDEN_SYMBOLS="$CLEAN_SYMBOLS"'
0000000100099300 t core::ptr::drop_in_place$LT$openclaw_engine..ipc_server..Server$GT$::h0123456789abcdef'

test_generic_form_is_detected() {
    local tmpdir mock_path mock_bin
    tmpdir="$(make_tmpdir)"
    trap "rm -rf '$tmpdir'" RETURN
    mock_path="$(make_mock_nm "$tmpdir" "$GENERIC_FORM_FORBIDDEN_SYMBOLS")"
    mock_bin="$(make_mock_binary "$tmpdir")"
    run_audit 1 "$mock_path" "$mock_bin"
}
test_empty_pattern_list_is_inconclusive() {
    local actual_exit=0
    sourced_audit_passes_unmodified || return 1
    ( source "$AUDIT_SCRIPT"; FORBIDDEN_PATTERNS=(); audit_symbols "$CLEAN_SYMBOLS" ) >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 ]]
}
test_self_test_detects_ineffective_normalisation() {
    local actual_exit=0
    sourced_self_test_passes_unmodified || return 1
    # 把 sed 換成原樣輸出：正規化失效時，泛型參數形式的樣本不再被命中。
    ( source "$AUDIT_SCRIPT"; sed() { cat; }; main --self-test ) >/dev/null 2>&1 || actual_exit=$?
    [[ "$actual_exit" -eq 5 ]]
}

# ──────────────────────────────────────────────────────────────────────
# Section 4 — Run all tests / 執行全部測試
# ──────────────────────────────────────────────────────────────────────
main() {
    printf '=== replay_runner_symbol_audit.sh test harness ===\n'
    printf 'audit script: %s\n\n' "$AUDIT_SCRIPT"

    if [[ ! -x "$AUDIT_SCRIPT" ]]; then
        printf 'FATAL: audit script not executable: %s\n' "$AUDIT_SCRIPT" >&2
        exit 99
    fi

    # subshell 跑每個 test 隔離 trap / RETURN cleanup
    # Run each test in subshell to isolate trap / RETURN cleanup
    local outcome

    outcome=0; ( test_t1_clean ) || outcome=$?
    record_test "T1 clean_symbols → exit 0" "$outcome"

    outcome=0; ( test_t2_forbidden_hit ) || outcome=$?
    record_test "T2 acquire_lease hit → exit 1" "$outcome"

    outcome=0; ( test_t3_nm_absent ) || outcome=$?
    record_test "T3 nm absent → exit 3" "$outcome"

    outcome=0; ( test_t4_binary_missing ) || outcome=$?
    record_test "T4 binary missing → exit 4" "$outcome"

    outcome=0; ( test_t5_multi_hit ) || outcome=$?
    record_test "T5 multi-class hit → exit 1" "$outcome"

    outcome=0; ( test_symbol_table_rejected "" ) || outcome=$?
    record_test "T6 empty symbols → exit 5" "$outcome"
    outcome=0; ( test_symbol_table_rejected '0000000100000000 T __mh_execute_header' ) || outcome=$?
    record_test "T7 stripped symbols → exit 5" "$outcome"
    outcome=0; ( test_symbol_table_rejected '0000000100000000 t unrelated::function' ) || outcome=$?
    record_test "T8 missing anchors → exit 5" "$outcome"
    outcome=0; ( test_positive_control ) || outcome=$?
    record_test "T9 positive control → forbidden hit" "$outcome"
    outcome=0; ( test_full_symbols_platform Darwin ) || outcome=$?
    record_test "T10 Darwin includes local symbols" "$outcome"
    outcome=0; ( test_full_symbols_platform Linux ) || outcome=$?
    record_test "T11 Linux includes local symbols (mock)" "$outcome"
    outcome=0; ( test_symbol_table_rejected "$MANGLED_ONLY_SYMBOLS" ) || outcome=$?
    record_test "T12 mangled-only symbols (demangle ineffective) → exit 5" "$outcome"
    outcome=0; ( test_symbol_table_rejected '0000000100001900 t _openclaw_engine::replay::runner::IsolatedPipeline' ) || outcome=$?
    record_test "T13 only the engine anchor → exit 5" "$outcome"
    outcome=0; ( test_symbol_table_rejected '0000000100002000 T _replay_runner::main' ) || outcome=$?
    record_test "T14 only the entry anchor → exit 5" "$outcome"
    outcome=0; ( test_cargo_output_override_is_inconclusive CARGO_TARGET_DIR ) || outcome=$?
    record_test "T15 CARGO_TARGET_DIR set → exit 5 before building" "$outcome"
    outcome=0; ( test_cargo_output_override_is_inconclusive CARGO_BUILD_TARGET ) || outcome=$?
    record_test "T16 CARGO_BUILD_TARGET set → exit 5 before building" "$outcome"
    outcome=0; ( test_unknown_argument_is_usage_error --selftest ) || outcome=$?
    record_test "T17 misspelled option → exit 64" "$outcome"
    outcome=0; ( test_unknown_argument_is_usage_error --self-test extra ) || outcome=$?
    record_test "T18 extra argument → exit 64" "$outcome"
    outcome=0; ( test_unusable_pattern_is_inconclusive ) || outcome=$?
    record_test "T19 unusable pattern → exit 5" "$outcome"
    outcome=0; ( test_self_test_detects_broken_class 0 ) || outcome=$?
    record_test "T20 self-test: first class broken → exit 5" "$outcome"
    outcome=0; ( test_self_test_detects_broken_class 9 ) || outcome=$?
    record_test "T21 self-test: last class broken → exit 5" "$outcome"
    outcome=0; ( test_self_test_detects_overbroad_class ) || outcome=$?
    record_test "T22 self-test: over-broad class hits clean control → exit 5" "$outcome"
    outcome=0; ( test_self_test_requires_one_sample_per_class ) || outcome=$?
    record_test "T23 self-test: class without a sample → exit 5" "$outcome"
    outcome=0; ( test_cargo_output_override_is_inconclusive CARGO_BUILD_TARGET_DIR ) || outcome=$?
    record_test "T24 CARGO_BUILD_TARGET_DIR set → exit 5 before building" "$outcome"
    outcome=0; ( test_generic_form_is_detected ) || outcome=$?
    record_test "T25 forbidden path only in generic-argument form → exit 1" "$outcome"
    outcome=0; ( test_symbol_table_rejected "$MANGLED_GENERIC_SYMBOLS" ) || outcome=$?
    record_test "T26 mangled table with generic-argument paths → exit 5" "$outcome"
    outcome=0; ( test_empty_pattern_list_is_inconclusive ) || outcome=$?
    record_test "T27 empty pattern list → exit 5" "$outcome"
    outcome=0; ( test_self_test_detects_ineffective_normalisation ) || outcome=$?
    record_test "T28 self-test: normalisation ineffective → exit 5" "$outcome"

    # Summary / 結尾總結
    printf '\n--- summary ---\n'
    printf 'PASS: %d / FAIL: %d / total: 28\n' \
        "$PASS_COUNT" "$FAIL_COUNT"

    if [[ "$FAIL_COUNT" -gt 0 ]]; then
        printf 'failed tests:\n'
        for t in "${FAILED_TESTS[@]}"; do
            printf '  - %s\n' "$t"
        done
        exit 1
    fi

    printf 'ALL TESTS PASS\n'
    exit 0
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi

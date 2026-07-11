#!/bin/bash
# 檔案：test_deploy_drift_detection.sh
# 目的（中文為主）：回歸測試 restart_all.sh 的 report_build_deploy_drift()——
#   Item 11「部署漂移偵測（deployed-vs-running drift healthcheck）」。核心斷言：
#     1) 以 mock boot_history.jsonl（build_sha = HEAD 的祖先 commit）餵入，
#        半部署（half-deploy）drift 訊號必須觸發。
#     2) detection-only 硬邊界：整個偵測流程**絕不呼叫任何 rebuild/restart 指令**
#        （nohup / cargo / systemctl / pkill / uvicorn / engine binary）。以 PATH
#        stub + sentinel 檔證明——任一被叫到就寫 sentinel，測試即失敗。
#   附帶覆蓋：in-sync、indeterminate（未知/分叉 sha）、無 boot_history、
#   無可用 build_sha、以及「repo_head 記錄須被略過、只取最後帶 build_sha 者」。
# Purpose (EN): Mac-runnable regression test for the Item 11 deploy-drift detector.
#   Asserts the half-deploy WARN fires on an ancestor build_sha AND that the
#   detection-only contract holds — no rebuild/restart command is ever invoked
#   (guarded by PATH stubs writing a sentinel; git/python3 stay real).
#
# 用法 / Usage:  bash helper_scripts/test_deploy_drift_detection.sh
# 依賴 / Deps:   僅 bash(3.2+) + git + python3(純標準庫)；不需 PG / engine / 網路。
#               測試不修改任何 repo 檔、不觸發服務、不下單、不重啟(read-only git)。

set -u

# ── 路徑解析：相對 script 位置推導 REPO_ROOT，不硬編碼絕對路徑（跨平台守則）──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
RESTART_SCRIPT="$REPO_ROOT/helper_scripts/restart_all.sh"

if [[ ! -f "$RESTART_SCRIPT" ]]; then
    echo "FATAL: restart_all.sh not found at $RESTART_SCRIPT" >&2
    exit 2
fi

# ── 臨時工作區（ephemeral；trap 清理，永不落在 repo 內）──
WORK="$(mktemp -d "${TMPDIR:-/tmp}/e4_item11.XXXXXX")"
FUNC_FILE="$(mktemp "${TMPDIR:-/tmp}/e4_item11_func.XXXXXX")"
STUB_BIN="$WORK/stub_bin"
export RESTART_SENTINEL="$WORK/RESTART_FIRED"
mkdir -p "$STUB_BIN"
trap 'rm -rf "$WORK" "$FUNC_FILE"' EXIT

# ── 抽取「真正」的被測函數（不複製業務邏輯 → mock 不得掩蓋真實實作）──
#   從 report_build_deploy_drift() 起，到第一個頂層 "}" 止（heredoc 內無獨立 "}"）。
awk '/^report_build_deploy_drift\(\) \{/{f=1} f{print} f&&/^\}$/{exit}' \
    "$RESTART_SCRIPT" > "$FUNC_FILE"
if ! grep -q '^report_build_deploy_drift() {' "$FUNC_FILE"; then
    echo "FATAL: could not extract report_build_deploy_drift from restart_all.sh" >&2
    exit 2
fi
# 語法先過關再 source，避免半截函數污染測試。
bash -n "$FUNC_FILE" || { echo "FATAL: extracted function failed syntax check" >&2; exit 2; }
# shellcheck source=/dev/null
. "$FUNC_FILE"

# ── PATH stub：任何 rebuild/restart 家族指令被呼叫 → 寫 sentinel（測試將失敗）──
#   注意：只 stub「重啟/重建」相關指令；git 與 python3 保持真實，偵測邏輯需要它們。
for cmd in nohup cargo systemctl pkill uvicorn openclaw-engine build_then_restart_atomic.sh; do
    cat > "$STUB_BIN/$cmd" <<'STUB'
#!/bin/bash
# 禁區 stub：偵測函數若呼叫任何重啟/重建指令即記錄，證明 detection-only 被違反。
echo "FORBIDDEN_RESTART_CALL: $(basename "$0") $*" >> "$RESTART_SENTINEL"
exit 0
STUB
    chmod +x "$STUB_BIN/$cmd"
done
export PATH="$STUB_BIN:$PATH"   # stub 置前;偵測函數若誤觸重啟即被攔截

# ── 真 commit sha：以 fixwt worktree 的真實歷史當 fixture（純 read-only git）──
HEAD_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
ANCESTOR_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD~1)"
UNKNOWN_SHA="deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"  # 40-hex 但非真 object → indeterminate

echo "== fixtures =="
echo "   REPO_ROOT   = $REPO_ROOT"
echo "   HEAD_SHA    = $HEAD_SHA"
echo "   ANCESTOR_SHA= $ANCESTOR_SHA (= HEAD~1, real ancestor)"
echo

# ── 斷言工具 ──────────────────────────────────────────────────────────────
PASS=0; FAIL=0
_ok()   { echo "  PASS: $1"; PASS=$((PASS+1)); }
_bad()  { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
assert_contains()     { case "$1" in (*"$2"*) _ok "$3";; (*) _bad "$3 -- missing: [$2]";; esac; }
assert_not_contains() { case "$1" in (*"$2"*) _bad "$3 -- unexpected: [$2]";; (*) _ok "$3";; esac; }
assert_rc()           { if [[ "$1" == "$2" ]]; then _ok "$3 (rc=$1)"; else _bad "$3 (rc=$1 != $2)"; fi; }
assert_no_restart()   {
    if [[ -e "$RESTART_SENTINEL" ]]; then
        _bad "$1 -- RESTART/REBUILD command WAS invoked: $(cat "$RESTART_SENTINEL")"
    else
        _ok "$1 (no rebuild/restart command invoked)"
    fi
}

# 每個案例前重置沙盒。
reset_case() { rm -f "$RESTART_SENTINEL" "$WORK/boot_history.jsonl"; }

# 以真被測函數跑一次,DATA_DIR/REPO_ROOT 為函數所需 shell 變數。
run_detector() {
    local out rc
    DATA_DIR="$WORK"
    out="$( { report_build_deploy_drift; } 2>&1 )"; rc=$?
    LAST_OUT="$out"; LAST_RC="$rc"
}

# ── Case A（核心）：build_sha = 祖先 → 半部署 drift 觸發 + 零重啟 ────────────
echo "== Case A: ancestor build_sha -> half-deploy drift fires, no restart =="
reset_case
printf '{"event":"engine_boot","build_sha":"%s","ts":"2026-07-11T00:00:00Z"}\n' "$ANCESTOR_SHA" > "$WORK/boot_history.jsonl"
run_detector
echo "$LAST_OUT" | sed 's/^/    | /'
assert_contains "$LAST_OUT" "DEPLOY-DRIFT (half-deploy)" "A1 half-deploy WARN fires"
assert_contains "$LAST_OUT" "ANCESTOR"                    "A2 message names ANCESTOR relation"
assert_contains "$LAST_OUT" "$ANCESTOR_SHA"               "A3 reports the running(ancestor) build_sha"
assert_contains "$LAST_OUT" "will NOT auto-rebuild"       "A4 states detection-only(no auto rebuild/restart)"
assert_rc       "$LAST_RC" "0"                            "A5 detector returns 0 (non-fatal)"
assert_no_restart                                         "A6 NO restart/rebuild side-effect"
echo

# ── Case B：build_sha = HEAD → in-sync,不發 WARN,零重啟 ─────────────────────
echo "== Case B: in-sync build_sha (== HEAD) -> no WARN, no restart =="
reset_case
printf '{"event":"engine_boot","build_sha":"%s","ts":"2026-07-11T00:05:00Z"}\n' "$HEAD_SHA" > "$WORK/boot_history.jsonl"
run_detector
echo "$LAST_OUT" | sed 's/^/    | /'
assert_contains     "$LAST_OUT" "in sync with HEAD" "B1 reports in-sync"
assert_not_contains "$LAST_OUT" "DEPLOY-DRIFT"      "B2 no drift WARN when in sync"
assert_rc           "$LAST_RC" "0"                  "B3 returns 0"
assert_no_restart                                   "B4 NO restart/rebuild side-effect"
echo

# ── Case C：未知/分叉 sha → indeterminate 訊號(非半部署),零重啟 ──────────────
echo "== Case C: unknown/diverged build_sha -> indeterminate drift, no restart =="
reset_case
printf '{"event":"engine_boot","build_sha":"%s","ts":"2026-07-11T00:10:00Z"}\n' "$UNKNOWN_SHA" > "$WORK/boot_history.jsonl"
run_detector
echo "$LAST_OUT" | sed 's/^/    | /'
assert_contains     "$LAST_OUT" "DEPLOY-DRIFT (indeterminate)" "C1 indeterminate WARN fires"
assert_not_contains "$LAST_OUT" "half-deploy"                  "C2 not mislabeled as half-deploy"
assert_rc           "$LAST_RC" "0"                             "C3 returns 0"
assert_no_restart                                              "C4 NO restart/rebuild side-effect"
echo

# ── Case D：無 boot_history → 安靜跳過,零重啟 ───────────────────────────────
echo "== Case D: missing boot_history.jsonl -> skip, no restart =="
reset_case   # 不建立檔案
run_detector
echo "$LAST_OUT" | sed 's/^/    | /'
assert_contains     "$LAST_OUT" "no boot_history.jsonl yet" "D1 skips when file absent"
assert_not_contains "$LAST_OUT" "DEPLOY-DRIFT"              "D2 no false drift on absent file"
assert_rc           "$LAST_RC" "0"                          "D3 returns 0"
assert_no_restart                                           "D4 NO restart/rebuild side-effect"
echo

# ── Case E：有紀錄但無可用 build_sha(缺欄位 + "unknown") → 誠實跳過,零重啟 ────
echo "== Case E: records without usable build_sha -> honest skip, no restart =="
reset_case
{
  printf '{"event":"api_boot","repo_head":"%s","ts":"2026-07-11T00:12:00Z"}\n' "$HEAD_SHA"
  printf '{"event":"engine_boot","build_sha":"unknown","ts":"2026-07-11T00:13:00Z"}\n'
} > "$WORK/boot_history.jsonl"
run_detector
echo "$LAST_OUT" | sed 's/^/    | /'
assert_contains     "$LAST_OUT" "no usable engine build_sha" "E1 skips when only unknown/absent build_sha"
assert_not_contains "$LAST_OUT" "DEPLOY-DRIFT"               "E2 no false drift (avoids observability false-positive)"
assert_rc           "$LAST_RC" "0"                           "E3 returns 0"
assert_no_restart                                            "E4 NO restart/rebuild side-effect"
echo

# ── Case F：混合紀錄——repo_head(=HEAD) 須被略過,只取最後 build_sha(=祖先) ────
#   證明:偵測用「最後一筆帶 build_sha 的引擎紀錄」,control_api 的 repo_head 不參與,
#   故 build_sha=祖先 仍正確判為半部署(不被後面的 repo_head=HEAD 洗白)。
echo "== Case F: repo_head record ignored; last build_sha(ancestor) -> half-deploy =="
reset_case
{
  printf '{"event":"engine_boot","build_sha":"%s","ts":"2026-07-11T00:20:00Z"}\n' "$ANCESTOR_SHA"
  printf '{"event":"api_boot","repo_head":"%s","ts":"2026-07-11T00:21:00Z"}\n' "$HEAD_SHA"
} > "$WORK/boot_history.jsonl"
run_detector
echo "$LAST_OUT" | sed 's/^/    | /'
assert_contains "$LAST_OUT" "DEPLOY-DRIFT (half-deploy)" "F1 still half-deploy (repo_head ignored)"
assert_contains "$LAST_OUT" "$ANCESTOR_SHA"              "F2 uses last build_sha-bearing record"
assert_rc       "$LAST_RC" "0"                           "F3 returns 0"
assert_no_restart                                        "F4 NO restart/rebuild side-effect"
echo

# ── 匯總 ────────────────────────────────────────────────────────────────────
echo "=================================================="
echo "RESULT: PASS=$PASS  FAIL=$FAIL"
echo "=================================================="
if [[ "$FAIL" -ne 0 ]]; then
    exit 1
fi
exit 0

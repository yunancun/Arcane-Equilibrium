#!/usr/bin/env bash
# MODULE_NOTE
# 模塊用途：P0-LG-3 non-training surface invariant 的 CI/pre-deploy grep guard（spec §6.1）。
#           learning.supervised_live_audit（V104）是合規 audit 表，不是 ML feature store /
#           label 表。本 guard 防 ML/training pipeline 誤讀此表，並防 append-only 被破壞
#           （writer 之外不得 UPDATE/DELETE 此表）。
# 依賴：ripgrep（rg）優先，fallback grep。
# 硬邊界：
#   1) 偵測到違規 exit 1（fail-loud），CI 必須紅燈（spec §6.1 Expected 0 hit）。
#   2) 不硬編碼路徑：REPO_ROOT 從 script 位置回推（跨平台可遷移）。
#   3) allowlist 限 healthcheck / reconciler / tests / writer 本體 / migration。

set -euo pipefail

# 專案根目錄（不硬編碼，從 script 位置回推 helper_scripts/healthchecks -> repo root）。
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

EXIT_CODE=0

# rg 或 grep 抽象（rg 優先；無則退回 grep -rn）。
_search() {
    local pattern="$1"
    if command -v rg >/dev/null 2>&1; then
        rg -n --no-heading -e "${pattern}" -g '!*.md' -g '!*.lock' . 2>/dev/null || true
    else
        grep -rn -E "${pattern}" \
            --include='*.rs' --include='*.py' --include='*.sql' --include='*.sh' \
            . 2>/dev/null || true
    fi
}

# ============================================================
# Rule 1：non-training surface — 禁 ML/training pipeline 讀 supervised_live_audit
# 為什麼：本表是 audit 不是 feature/label store；ML 接管會污染 training surface
#   並違 root principle §7（學習不直接改 live state）。
# allowlist：healthcheck / reconciler / tests / writer 本體 / migration 合法引用。
# ============================================================
READ_PATTERN='(SELECT|FROM)[[:space:]].*learning\.supervised_live_audit'
ALLOWLIST_RE='(helper_scripts/healthchecks|position_reconciler|reconciler|/tests?/|/test_|supervised_live_audit_writer|sql/migrations/)'
ML_SURFACE_RE='(/ml/|/training/|/learning/|ml_|train_|feature_store)'

R1_HITS="$(_search "${READ_PATTERN}")"
if [[ -n "${R1_HITS}" ]]; then
    # 先去 allowlist，再過濾出落在 ML/training surface 的引用。
    R1_VIOL="$(echo "${R1_HITS}" | grep -vE "${ALLOWLIST_RE}" | grep -E "${ML_SURFACE_RE}" || true)"
    if [[ -n "${R1_VIOL}" ]]; then
        echo "[e3-grep] Rule 1 違規：ML/training surface 讀 learning.supervised_live_audit（non-training invariant）。" >&2
        echo "${R1_VIOL}" >&2
        EXIT_CODE=1
    fi
fi

# ============================================================
# Rule 2：append-only — writer/migration 之外禁 UPDATE/DELETE supervised_live_audit
# 為什麼：audit 必須不可變（root principle §8 可重建可解釋）；任何 UPDATE/DELETE
#   破壞稽核完整性。migration（V104 建表）與 writer 本體允許出現表名。
# ============================================================
MUTATE_PATTERN='(UPDATE|DELETE[[:space:]]+FROM)[[:space:]].*supervised_live_audit'
R2_HITS="$(_search "${MUTATE_PATTERN}")"
if [[ -n "${R2_HITS}" ]]; then
    R2_VIOL="$(echo "${R2_HITS}" | grep -vE "${ALLOWLIST_RE}" || true)"
    if [[ -n "${R2_VIOL}" ]]; then
        echo "[e3-grep] Rule 2 違規：偵測 UPDATE/DELETE supervised_live_audit（append-only 被破壞）。" >&2
        echo "${R2_VIOL}" >&2
        EXIT_CODE=1
    fi
fi

# ============================================================
# Rule 3：forbidden ML column 不得在 supervised_live_audit DDL 出現
# 為什麼：與 V104 Guard A part 3 對齊（DB 端 RAISE 之外，CI 端再加一層靜態防護）。
# ============================================================
FORBIDDEN_COL_PATTERN='(ml_label|training_label|feature_vector|signal_id)'
R3_HITS="$(_search "supervised_live_audit")"
if [[ -n "${R3_HITS}" ]]; then
    # 僅在同時提及 supervised_live_audit 與 forbidden column 的 SQL/migration 檔報警。
    R3_VIOL="$(echo "${R3_HITS}" | grep -E '\.sql:' | grep -E "${FORBIDDEN_COL_PATTERN}" || true)"
    if [[ -n "${R3_VIOL}" ]]; then
        echo "[e3-grep] Rule 3 違規：supervised_live_audit DDL 含 forbidden ML column。" >&2
        echo "${R3_VIOL}" >&2
        EXIT_CODE=1
    fi
fi

if [[ "${EXIT_CODE}" -eq 0 ]]; then
    echo "[e3-grep] non-training surface invariant guard PASS（0 violation）"
fi
exit "${EXIT_CODE}"

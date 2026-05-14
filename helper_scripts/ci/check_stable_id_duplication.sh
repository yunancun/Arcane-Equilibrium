#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# check_stable_id_duplication.sh - W-D MAG-083 P1-1 follow-up guard
#
# MODULE_NOTE (EN):
#   Fast CI grep guard for accidental literal reimplementation of Agent Spine
#   stable_id seed formatting. W-D MAG-083 P1-1 centralized the entry/fill id
#   calculation behind compute_spine_ids() / compute_filled_report_id(); this
#   script fails if a Rust source file outside the canonical helper/caller files
#   contains the legacy-looking `format!("{}:{}:{}:{}"...` seed pattern together
#   with stable-id-like variable names.
#
# MODULE_NOTE (中):
#   Agent Spine stable_id seed 字面複製的快速 CI grep guard。W-D MAG-083 P1-1
#   已把 entry/fill id 計算集中到 compute_spine_ids() /
#   compute_filled_report_id()；若 canonical helper/caller 以外的 Rust 檔案
#   再出現 `format!("{}:{}:{}:{}"...` seed pattern 且同檔含 stable-id-like
#   變數名，本腳本即 fail，避免未來 audit chain silent drift。
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail
IFS=$'\n\t'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRV_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# The user-facing requirement names runtime_shadow.rs as the canonical source
# file. In current source, the helper itself lives in spine_ids.rs and
# runtime_shadow.rs is the historical lineage caller, so both are allowed.
declare -a ALLOWLISTED_FILES=(
    "rust/openclaw_engine/src/agent_spine/runtime_shadow.rs"
    "rust/openclaw_engine/src/agent_spine/spine_ids.rs"
)

SIGNATURE='format!("{}:{}:{}:{}'
STABLE_ID_NAME_RE='stable[_-]?id|decision_id|order_plan_id|stub_report_id|filled_report_id|execution_report_id|spine_(decision|order|stub|report)|shadow_planned|shadow_filled'

log() {
    printf '[stable_id_duplication_check] %s\n' "$*" >&2
}

is_allowlisted() {
    local rel_path="$1"
    local allowed
    for allowed in "${ALLOWLISTED_FILES[@]}"; do
        if [[ "$rel_path" == "$allowed" ]]; then
            return 0
        fi
    done
    return 1
}

tmp_hits="$(mktemp -t stable_id_duplication_hits.XXXXXX)"
trap 'rm -f "$tmp_hits"' EXIT

while IFS= read -r -d '' file_path; do
    rel_path="${file_path#"$SRV_ROOT"/}"

    if is_allowlisted "$rel_path"; then
        continue
    fi

    if ! grep -Fq "$SIGNATURE" "$file_path"; then
        continue
    fi

    # The exact format string alone can be legitimate for unrelated tuple keys.
    # Require stable-id-like identifiers in the same Rust source file before
    # reporting a violation.
    if ! grep -Eq "$STABLE_ID_NAME_RE" "$file_path"; then
        continue
    fi

    while IFS= read -r hit; do
        printf '%s:%s\n' "$rel_path" "$hit" >>"$tmp_hits"
    done < <(grep -nF "$SIGNATURE" "$file_path")
done < <(
    find "$SRV_ROOT" \
        \( \
            -path "$SRV_ROOT/.git" -o \
            -path "$SRV_ROOT/target" -o \
            -path "$SRV_ROOT/rust/target" -o \
            -path "$SRV_ROOT/.claude/worktrees" \
        \) -prune -o \
        -type f -name '*.rs' -print0
)

if [[ -s "$tmp_hits" ]]; then
    log "FAIL: possible literal stable_id computation duplication found"
    log "signature: $SIGNATURE + stable-id-like identifiers"
    log "allowed files:"
    for allowed in "${ALLOWLISTED_FILES[@]}"; do
        log "  - $allowed"
    done
    log "offending locations:"
    sort -u "$tmp_hits" >&2
    exit 1
fi

log "PASS: no stable_id literal duplication pattern found"
exit 0

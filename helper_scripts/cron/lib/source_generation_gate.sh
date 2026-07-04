#!/usr/bin/env bash
# source_generation_gate.sh — learning-lane 世代判準的 cron shell 側單一接線點。
#
# MODULE_NOTE
# 模塊用途：把 P1-4 公共庫 source_generation.py 的四態判準（MATCH / DRIFT_EXEMPT /
#   DRIFT_ROTATED / INDETERMINATE）暴露成一個 shell 函數，供 evidence_audit /
#   healthcheck / alpha_discovery / sealed_horizon 四個 cron 共用，避免各腳本
#   複製 lib 調用邏輯（豁免判準只有一份 SSOT，見 §4.C）。
# 主要函數：resolve_effective_expected_head。
# 硬邊界：source-only；只讀 git + pin 檔，只寫 OPENCLAW_DATA_DIR 下 audit artifact；
#   不下單、不改 auth/risk/runtime/Cost Gate。DRIFT_EXEMPT 只代表「豁免面前進不
#   凍結 lane」，其餘態沿各 lane 既有 mismatch/unknown fail-close 語意不變。

# resolve_effective_expected_head <base_dir> <data_dir> <lane> <raw_expected_head>
#   讀公共庫，輸出「effective expected head」到 stdout（供下游 --expected-head）。
#   - MATCH：回原 pin（行為與割接前逐位一致）。
#   - DRIFT_EXEMPT：回當前 HEAD，讓下游 exact-compare 綠（docs/tests/.codex 前進
#     不再凍 lane）；完整分類已由 lib 落 artifact（放行必留痕）。
#   - DRIFT_ROTATED：回原 pin，下游對當前 HEAD 必 MISMATCH → fail-close（真代碼漂移）。
#   - INDETERMINATE：回非 hex sentinel，下游 exact-compare 必紅 → fail-close
#     （pin 檔壞 / git 失敗，不退化成「未配置=綠」）。
#   - PIN_NOT_PROVIDED：回空字串，沿各 lane 既有「expected head 未提供」行為。
#   lib 調用本身失敗（缺 python / import 崩）時：回 raw_expected_head 原值，
#   維持割接前既有行為（env 鏈 inline pin 仍生效），不引入新放行邊。
resolve_effective_expected_head() {
    local base_dir="$1"
    local data_dir="$2"
    local lane="$3"
    local raw_expected="$4"
    local pybin="${OPENCLAW_PYTHON_BIN:-}"
    if [[ -z "$pybin" ]]; then
        if [[ -x "$HOME/.venv/bin/python" ]]; then
            pybin="$HOME/.venv/bin/python"
        else
            pybin="python3"
        fi
    fi

    # 為什麼不用變量名 status：zsh 的 $status 是唯讀特殊變量，Mac dev 若在 zsh
    # source 本 lib 會 read-only 報錯；用 gen_status 避開。
    local line gen_status effective
    if ! line="$(
        cd "$base_dir/helper_scripts/research" 2>/dev/null &&
        PYTHONDONTWRITEBYTECODE=1 "$pybin" -m cost_gate_learning_lane.source_generation \
            --repo-root "$base_dir" \
            --data-dir "$data_dir" \
            --expected-head "$raw_expected" \
            --lane "$lane" 2>/dev/null | head -n 1
    )"; then
        # lib 調用失敗：沿用 raw expected（割接前行為），fail-close 由下游既有比對負責。
        printf '%s' "$raw_expected"
        return 0
    fi
    gen_status="${line%%$'\t'*}"
    effective="${line#*$'\t'}"
    if [[ -z "$gen_status" ]]; then
        printf '%s' "$raw_expected"
        return 0
    fi
    # PIN_NOT_PROVIDED 時 effective 為空字串，直接回傳（下游 -n 判定為未提供）。
    printf '%s' "$effective"
    return 0
}

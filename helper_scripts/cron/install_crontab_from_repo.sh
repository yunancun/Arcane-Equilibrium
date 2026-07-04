#!/usr/bin/env bash
# install_crontab_from_repo.sh — 從 repo 正本 crontab.trade-core.template 安裝 live crontab
# ----------------------------------------------------------------------------
# 為什麼有此檔（P0-2④ crontab 治理唯一安裝入口）：
#   2026-06-27 一次無記錄、無快照、無 manifest 的 REPLACE 把 70 行 crontab 清空
#   （FA 2026-07-04 §一）。本 installer 是唯一被授權寫 live crontab 的入口,把每次
#   mutation 變成「render 正本 → diff → 快照 → shrink-guard → 落 manifest」的
#   可追溯序列。任何繞過此入口的 `crontab -`/`crontab <file>` 都是治理外行為。
#
# 執行流程:
#   1. render:讀 crontab.trade-core.template,把 {{HEAD}} 換成
#      `git -C <repo> rev-parse --short HEAD`（pin-by-reference,不手寫字面）。
#   2. diff:`crontab -l` 快照現表 vs render 產物。
#   3. 空表守衛:render 後 active 行數 == 0 → 一律拒絕（本事故類型的直接封殺面之一）。
#   4. shrink-guard:render active 行數 < 現表 active 行數 * 50% → 拒絕,除非
#      OPENCLAW_CRONTAB_ALLOW_SHRINK=1 顯式豁免（直接封殺 70→空 這類縮表事故）。
#   5. 落檔:before/after/diff/manifest 寫持久路徑
#      $OPENCLAW_DATA_DIR/crontab_mutations/<UTC>Z/（本案教訓:快照落 /tmp 能活
#      下來純屬僥倖,必須落 var/openclaw 持久面）。
#   6. install:預設 --dry-run 不寫;顯式 --apply 才 `crontab -` 寫入。
#
# 硬邊界:
#   - 不寫 secrets;不改 PG/schema;不觸 engine/app/env/risk/Cost Gate。
#   - 不做任何 live 下單 / authorization.json 相關動作（模板本身零 live 行）。
#   - 空 render / 空 stdin 一律拒絕,不論任何 flag。
#   - 路徑走 OPENCLAW_DATA_DIR env,不硬編碼 runtime 機器路徑（per feedback_cross_platform）。

set -euo pipefail

# ----- 平台守門:僅 Linux runtime 跑（mirror install_pg_dump_cron.sh）-----
# OPENCLAW_CRONTAB_SKIP_PLATFORM_GUARD=1 僅供 Mac dev 上的負向測試繞過平台檢查跑
# render/shrink-guard/空表守衛等純邏輯;它不放行任何寫入面(實寫仍需 --apply,測試
# 從不傳 --apply),故不弱化任何 live/安全邊界。
if [[ "$(uname -s)" != "Linux" && "${OPENCLAW_CRONTAB_SKIP_PLATFORM_GUARD:-0}" != "1" ]]; then
    echo "ERROR: install_crontab_from_repo.sh requires Linux runtime (current: $(uname -s))." >&2
    echo "       本 install script 必在 Linux runtime host (trade-core) 跑;Mac dev 走 ssh trade-core。" >&2
    exit 2
fi

# ----- env / 預設值 -----
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# repo root = helper_scripts/cron 的上兩層;優先 OPENCLAW_BASE_DIR。
OPENCLAW_BASE_DIR="${OPENCLAW_BASE_DIR:-$(cd "$SCRIPT_DIR/../.." && pwd)}"
OPENCLAW_DATA_DIR="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"
TEMPLATE="${OPENCLAW_CRONTAB_TEMPLATE:-$SCRIPT_DIR/crontab.trade-core.template}"
SHRINK_ALLOWED="${OPENCLAW_CRONTAB_ALLOW_SHRINK:-0}"

# ----- 參數:預設 dry-run,--apply 才實寫 -----
MODE="dry-run"
for arg in "$@"; do
    case "$arg" in
        --apply)   MODE="apply" ;;
        --dry-run) MODE="dry-run" ;;
        *)
            echo "ERROR: unknown argument: $arg (支援 --dry-run[預設] / --apply)" >&2
            exit 3
            ;;
    esac
done

# ----- pre-flight -----
if [[ ! -f "$TEMPLATE" ]]; then
    echo "ERROR: template not found: $TEMPLATE" >&2
    exit 4
fi
if ! command -v git >/dev/null 2>&1; then
    echo "ERROR: git not found on PATH (需派生 EXPECTED_SOURCE_HEAD pin)。" >&2
    exit 5
fi

HEAD_SHA="$(git -C "$OPENCLAW_BASE_DIR" rev-parse --short HEAD 2>/dev/null || true)"
if [[ -z "$HEAD_SHA" ]]; then
    echo "ERROR: cannot resolve git HEAD in $OPENCLAW_BASE_DIR (pin-by-reference 失敗)。" >&2
    exit 5
fi

# ----- helper:數非空非註釋行（active cron 行數）-----
# 為什麼:shrink-guard / 空表守衛只看真正會跑的行,註釋與空行不計入。
_count_active_lines() {
    grep -vE '^[[:space:]]*(#|$)' | grep -c . || true
}

# ----- 1. render:{{HEAD}} → HEAD_SHA -----
# 為什麼用 sed 全局替換:模板僅在 pin 欄位出現 {{HEAD}},無其他 {{...}} 佔位。
RENDERED="$(sed "s/{{HEAD}}/${HEAD_SHA}/g" "$TEMPLATE")"

# ----- 2. 空 render 守衛（不論任何 flag 一律拒絕）-----
RENDER_ACTIVE="$(printf '%s\n' "$RENDERED" | _count_active_lines)"
if [[ "$RENDER_ACTIVE" -eq 0 ]]; then
    echo "ERROR: rendered crontab has 0 active lines — refusing to install empty table." >&2
    echo "       （空表安裝 = 2026-06-27 屠殺事故類型,一律拒絕,無豁免 flag）。" >&2
    exit 6
fi

# ----- 3. 現表快照 + active 行數 -----
CURRENT="$(crontab -l 2>/dev/null || true)"
CURRENT_ACTIVE="$(printf '%s\n' "$CURRENT" | _count_active_lines)"

# ----- 4. shrink-guard:新表 active < 現表 active * 50% → 拒絕（除非顯式豁免）-----
# 為什麼 50%:直接封殺 70→空 / 大幅縮表這類事故;正常增刪個別 lane 不會觸發。
# 現表為空（首裝 / 屠殺後）時 CURRENT_ACTIVE=0,shrink-guard 不適用（無可縮之表）。
SHRINK_TRIGGERED=0
if [[ "$CURRENT_ACTIVE" -gt 0 ]]; then
    # 整數比較:2 * RENDER_ACTIVE < CURRENT_ACTIVE  ⇔  RENDER_ACTIVE < CURRENT_ACTIVE * 0.5
    if [[ $(( RENDER_ACTIVE * 2 )) -lt "$CURRENT_ACTIVE" ]]; then
        SHRINK_TRIGGERED=1
    fi
fi

# ----- 5. 落檔:before/after/diff/manifest 寫持久路徑 -----
UTC_STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
MUT_DIR="$OPENCLAW_DATA_DIR/crontab_mutations/$UTC_STAMP"
mkdir -p "$MUT_DIR"
printf '%s\n' "$CURRENT"  > "$MUT_DIR/crontab.before.txt"
printf '%s\n' "$RENDERED" > "$MUT_DIR/crontab.after.txt"
# diff 只做記錄,退出碼非 0 不代表失敗（有差異是常態）。
diff -u "$MUT_DIR/crontab.before.txt" "$MUT_DIR/crontab.after.txt" > "$MUT_DIR/crontab.diff.txt" 2>/dev/null || true

BEFORE_SHA="$(printf '%s\n' "$CURRENT"  | sha256sum | awk '{print $1}')"
AFTER_SHA="$(printf '%s\n' "$RENDERED" | sha256sum | awk '{print $1}')"
ACTOR="${OPENCLAW_CRONTAB_ACTOR:-${USER:-unknown}}"
REASON="${OPENCLAW_CRONTAB_REASON:-unspecified}"

# manifest:actor/reason/pre-post sha256/行數 delta/pin/mode（P0-2④ 變更留檔強制）。
cat > "$MUT_DIR/manifest.json" <<EOF
{
  "utc": "$UTC_STAMP",
  "mode": "$MODE",
  "actor": "$ACTOR",
  "reason": "$REASON",
  "template": "$TEMPLATE",
  "expected_source_head": "$HEAD_SHA",
  "before_active_lines": $CURRENT_ACTIVE,
  "after_active_lines": $RENDER_ACTIVE,
  "before_sha256": "$BEFORE_SHA",
  "after_sha256": "$AFTER_SHA",
  "shrink_guard_triggered": $SHRINK_TRIGGERED,
  "shrink_guard_override": ${SHRINK_ALLOWED:-0}
}
EOF

echo "------- crontab install plan -------"
echo "template          : $TEMPLATE"
echo "EXPECTED_HEAD pin : $HEAD_SHA"
echo "before active     : $CURRENT_ACTIVE"
echo "after  active     : $RENDER_ACTIVE"
echo "mutation dir      : $MUT_DIR"
echo "mode              : $MODE"
echo "------------------------------------"

if [[ "$SHRINK_TRIGGERED" -eq 1 ]]; then
    if [[ "$SHRINK_ALLOWED" != "1" ]]; then
        echo "ERROR: shrink-guard tripped — after active ($RENDER_ACTIVE) < before active ($CURRENT_ACTIVE) * 50%." >&2
        echo "       （縮表事故防護:2026-06-27 屠殺即 70→空。）" >&2
        echo "       如確為有意大幅縮表,set OPENCLAW_CRONTAB_ALLOW_SHRINK=1 顯式覆寫。" >&2
        echo "       manifest 已落 $MUT_DIR/manifest.json（shrink_guard_triggered=1）供追溯。" >&2
        exit 7
    fi
    echo "WARN: shrink-guard tripped but OPENCLAW_CRONTAB_ALLOW_SHRINK=1 override active — proceeding." >&2
fi

# ----- 6. install:預設 dry-run 不寫;--apply 才 `crontab -` 寫入 -----
if [[ "$MODE" != "apply" ]]; then
    echo
    echo "DRY-RUN: not modifying crontab. before/after/diff/manifest 已落 ${MUT_DIR}。"
    echo "         確認 after 表無誤後,加 --apply 實際安裝。"
    exit 0
fi

# render 走 stdin 給 crontab -;set -e 下若 crontab 失敗會非 0 退出。
printf '%s\n' "$RENDERED" | crontab -
echo "INSTALLED: crontab replaced from repo template (pin=$HEAD_SHA). Verify: crontab -l | grep -vc '^#'"
echo "           manifest: $MUT_DIR/manifest.json"

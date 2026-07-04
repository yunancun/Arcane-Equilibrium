#!/usr/bin/env bash
# derive_expected_source_head.sh — 部署後派生 learning-lane 世代 pin 檔。
#
# MODULE_NOTE
# 模塊用途：把當前 checkout 的 git HEAD 原子寫進 pin SSOT 檔
#   $OPENCLAW_DATA_DIR/runtime_generation/expected_source_head.json（P1-4 §4.C
#   兩個合法寫者之一；另一個是 restart_all.sh 成功啟動後）。source-only 部署
#   （learning lane 是 Python，git pull 即部署、無 engine 重啟）時，pull SOP 尾
#   接本腳本一行即可讓 pin 隨部署自動前進，去除「部署後忘改 crontab inline SHA」
#   的復發保證（FA F4「06-24 已修類別復發」根因）。
# 用法：
#   OPENCLAW_BASE_DIR=<repo> OPENCLAW_DATA_DIR=<data> \
#       bash helper_scripts/deploy/derive_expected_source_head.sh
# 硬邊界：只讀 git、只寫 pin 檔（原子 temp+rename，0600）；不下單、不連
#   runtime/Bybit/PG、不改 auth/risk/service/env/Cost Gate。pin 只是「部署世代」
#   的可觀測快照，本身不授權任何 runtime action。
set -euo pipefail

BASE="${OPENCLAW_BASE_DIR:-$(cd "$(dirname "$0")/../.." && pwd -P)}"
DATA="${OPENCLAW_DATA_DIR:-/tmp/openclaw}"

HEAD_SHA="$(git -C "$BASE" rev-parse HEAD 2>/dev/null || true)"
if [[ -z "$HEAD_SHA" ]]; then
    echo "ERROR: git rev-parse HEAD failed under BASE=$BASE; pin file not written." >&2
    exit 2
fi

PIN_DIR="$DATA/runtime_generation"
PIN_FILE="$PIN_DIR/expected_source_head.json"
mkdir -p "$PIN_DIR"

DERIVED_AT="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
# 為什麼原子 temp+rename+0600：pin 檔是消費 lane（evidence_audit/healthcheck/
# alpha_discovery/sealed_horizon）的世代判準來源，半寫入的 JSON 會被解析為
# pin_file_json_invalid → 各 lane fail-close（安全），但為避免不必要的凍結，
# 寫入必須原子。0600 與其他 runtime secret/artifact 檔一致。
TMP_FILE="$(mktemp "${PIN_DIR}/.expected_source_head.XXXXXX")"
printf '{\n  "head": "%s",\n  "derived_at_utc": "%s",\n  "writer": "derive_expected_source_head.sh",\n  "base_dir": "%s"\n}\n' \
    "$HEAD_SHA" "$DERIVED_AT" "$BASE" > "$TMP_FILE"
chmod 600 "$TMP_FILE"
mv -f "$TMP_FILE" "$PIN_FILE"

echo "Derived expected source head pin: head=$HEAD_SHA -> $PIN_FILE"

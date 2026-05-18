#!/usr/bin/env bash
# compute_sri_hashes.sh — Compute SHA-384 SRI integrity attributes for pinned CDN URLs.
# P2-WP05-CSP-UNSAFE-INLINE（2026-05-18）— 為 control_api_v1 GUI 的 pinned CDN
# 計算 SRI integrity hash（SHA-384 base64），列印 `integrity="sha384-..."` 行給
# operator 直接複製進對應 HTML <script> / <link>。
#
# MODULE_NOTE：
#   CDN 供應鏈攻擊（unpkg / jsdelivr / cdnjs 任一域被入侵時）會把無 integrity
#   的 <script src=...> 載入篡改 JS。SRI 強制瀏覽器以加密 hash 驗證 byte
#   identity，hash 不符時 console error + 拒絕執行。CDN URL 必須 pin 到具體
#   版本（@x.y.z），否則 hash 會在 CDN 自動升版時失效。
#
#   為什麼用 SHA-384 而非 SHA-256/SHA-512：W3C SRI Level 2 建議 SHA-384 為
#   primary（balance security vs hash length；W3C 規格列三者都接受）。
#   程式碼 / GUI 一致就好，無 cross-spec 強約束。
#
# 使用方式：
#   bash helper_scripts/security/compute_sri_hashes.sh
#   bash helper_scripts/security/compute_sri_hashes.sh https://unpkg.com/lib@1.2.3/dist/lib.min.js
#
# 退出碼：
#   0 = all URLs OK
#   1 = at least one URL fetch / hash 失敗
#   2 = missing dependency (curl / openssl)

set -euo pipefail

# 預設掃的 CDN URL 清單。新增 GUI CDN 依賴時加在這裡，使 helper 自動覆蓋。
# 同時對應 GUI HTML 內的 integrity attribute；任一邊修改另一邊也要同步。
DEFAULT_URLS=(
    "https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.production.js"
)

# ─── Dependency check ────────────────────────────────────────────────
for bin in curl openssl; do
    if ! command -v "$bin" >/dev/null 2>&1; then
        echo "FATAL: missing dependency: $bin" >&2
        exit 2
    fi
done

# 接 stdin 或 CLI 參數覆蓋 DEFAULT_URLS。
if [[ $# -gt 0 ]]; then
    URLS=("$@")
else
    URLS=("${DEFAULT_URLS[@]}")
fi

EXIT_CODE=0
echo "P2-WP05-CSP-UNSAFE-INLINE — SHA-384 SRI integrity attributes"
echo "================================================================"
echo

for url in "${URLS[@]}"; do
    # 版本 pin 啟發式檢查：要求 URL 含 `@<version>/`。
    # 為什麼：unpkg/jsdelivr/cdnjs 未 pin 時會自動指向 latest，hash 計完即失效。
    if [[ "$url" != *"@"*"/"* ]]; then
        echo "URL: $url"
        echo "  WARNING: version pin not detected (no '@<ver>/' segment);"
        echo "           SRI hash will silently break when CDN updates latest tag"
        echo "           — operator must decide on a fixed version before pinning."
        echo
        EXIT_CODE=1
        continue
    fi

    # 抓檔 → SHA-384 → base64。三段獨立失敗都 surface。
    if hash=$(curl -sf --max-time 30 "$url" \
                 | openssl dgst -sha384 -binary \
                 | openssl base64 -A 2>/dev/null) \
       && [[ -n "$hash" ]]; then
        echo "URL: $url"
        echo "  integrity=\"sha384-${hash}\""
        echo "  crossorigin=\"anonymous\""
        echo
    else
        echo "URL: $url"
        echo "  ERROR: failed to fetch or hash"
        echo
        EXIT_CODE=1
    fi
done

if [[ $EXIT_CODE -eq 0 ]]; then
    echo "All URLs hashed OK. Paste integrity / crossorigin attributes into the"
    echo "matching <script> / <link> tag in app/static/*.html."
else
    echo "One or more URLs failed; review WARNING / ERROR lines above."
fi

exit $EXIT_CODE

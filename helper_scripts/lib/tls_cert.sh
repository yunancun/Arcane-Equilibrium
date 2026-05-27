#!/bin/bash
# tls_cert.sh — OPS-1 Track A：跨平台 Tailscale cert 路徑與 renewal helper。
#
# MODULE_NOTE (CN)：
#   集中抽象「拿到當前平台的 Tailscale cert 路徑」與「判定 cert 是否快到期」。
#   為什麼跨平台：CLAUDE.md §六 ★ 新代碼必須隨時可部署 Mac；Linux + macOS 兩平台
#   cert 預設位置不同，硬編碼 `/var/lib/tailscale/certs` 在 macOS 失效。
#
# 函數 / Functions:
#   resolve_openclaw_tls_cert_dir   — 解析 OPENCLAW_TLS_CERT_DIR；缺省看平台
#   resolve_openclaw_tls_cert_host  — 解析 OPENCLAW_TLS_CERT_HOST（Tailnet 主機名）
#   tls_cert_days_remaining         — 計算指定 .crt 距到期還剩幾天
#   tls_cert_should_renew           — 剩餘天數 < threshold（預設 14）回 0
#
# 硬邊界：
#   - 不寫死 operator-specific home 路徑（CLAUDE.md §六 portability rule）
#   - cert 路徑只讀 env / 平台預設，不 fallback 到 PATH 探測（防誤用 wrong cert）

_openclaw_tls_uname() {
    uname -s 2>/dev/null
}

# 解析 cert 目錄：env > 平台預設。
# Linux: /var/lib/tailscale/certs
# Darwin (macOS): $HOME/Library/Application Support/Tailscale/certs
resolve_openclaw_tls_cert_dir() {
    if [ -n "${OPENCLAW_TLS_CERT_DIR:-}" ]; then
        printf '%s\n' "$OPENCLAW_TLS_CERT_DIR"
        return 0
    fi
    case "$(_openclaw_tls_uname)" in
        Linux)
            printf '%s\n' "/var/lib/tailscale/certs"
            ;;
        Darwin)
            printf '%s\n' "$HOME/Library/Application Support/Tailscale/certs"
            ;;
        *)
            echo "ERROR: tls_cert.sh: unsupported platform $(_openclaw_tls_uname)" >&2
            return 2
            ;;
    esac
}

# 解析 Tailnet 主機名（cert SAN）：env > 推算（tailscale status --json）。
# 為什麼必須顯式：tail358794.ts.net 是 operator-specific tailnet；不寫死。
resolve_openclaw_tls_cert_host() {
    if [ -n "${OPENCLAW_TLS_CERT_HOST:-}" ]; then
        printf '%s\n' "$OPENCLAW_TLS_CERT_HOST"
        return 0
    fi
    if command -v tailscale >/dev/null 2>&1; then
        local self
        self="$(tailscale status --json 2>/dev/null | python3 -c '
import json, sys
try:
    payload = json.load(sys.stdin)
    print(payload.get("Self", {}).get("DNSName", "").rstrip("."))
except Exception:
    pass
' 2>/dev/null)"
        if [ -n "$self" ]; then
            printf '%s\n' "$self"
            return 0
        fi
    fi
    echo "ERROR: tls_cert.sh: OPENCLAW_TLS_CERT_HOST not set and tailscale status failed" >&2
    return 2
}

# 計算 cert 還剩幾天。輸出 stdout 整數（負數代表已過期），非 0 exit 表錯誤。
tls_cert_days_remaining() {
    local cert_path="$1"
    if [ -z "$cert_path" ] || [ ! -f "$cert_path" ]; then
        echo "ERROR: tls_cert.sh: cert file missing: $cert_path" >&2
        return 2
    fi
    # openssl x509 -enddate -noout → "notAfter=MMM DD HH:MM:SS YYYY GMT"
    local end_date end_epoch now_epoch
    end_date="$(openssl x509 -enddate -noout -in "$cert_path" 2>/dev/null | sed 's/^notAfter=//')"
    if [ -z "$end_date" ]; then
        echo "ERROR: tls_cert.sh: openssl failed to read $cert_path" >&2
        return 2
    fi
    case "$(_openclaw_tls_uname)" in
        Linux)
            end_epoch="$(date -u -d "$end_date" +%s 2>/dev/null)"
            ;;
        Darwin)
            # BSD date 需要 -f 指定格式
            end_epoch="$(date -j -u -f '%b %d %H:%M:%S %Y %Z' "$end_date" +%s 2>/dev/null)"
            ;;
        *)
            return 2
            ;;
    esac
    if [ -z "$end_epoch" ]; then
        echo "ERROR: tls_cert.sh: unable to parse date '$end_date'" >&2
        return 2
    fi
    now_epoch="$(date -u +%s)"
    echo $(( (end_epoch - now_epoch) / 86400 ))
}

# 是否應該續期？剩餘天數 < threshold（預設 14）回 exit 0，否則 exit 1。
# 為什麼預設 14d：spec §2.2 systemd timer 14d 提前 renew + 7d alert。
tls_cert_should_renew() {
    local cert_path="$1"
    local threshold="${2:-14}"
    local days
    days="$(tls_cert_days_remaining "$cert_path")" || return 2
    if [ "$days" -lt "$threshold" ]; then
        return 0
    fi
    return 1
}

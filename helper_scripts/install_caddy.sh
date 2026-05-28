#!/bin/bash
# install_caddy.sh — OPS-1 Track A：在 Linux trade-core 安裝 Caddy + Tailscale cert。
#
# MODULE_NOTE (CN)：
#   一次性 deploy 腳本：
#   1. 確認 Tailscale 已 up 並能解析 Tailnet DNS
#   2. 拉 Caddy（apt / brew）
#   3. 從 Caddyfile.template 產生 /etc/caddy/Caddyfile（envsubst）
#   4. 第一次 `tailscale cert` 拉 cert + 設定權限
#   5. 拉 systemd unit / timer（Linux）或印出 launchd plist 指引（macOS）
#   6. enable + start，curl -kI 驗證
#
# 使用：
#   sudo bash helper_scripts/install_caddy.sh
#
# 必要 env（未設則 fail-loud）：
#   OPENCLAW_TLS_CERT_HOST     — 例：trade-core.tail358794.ts.net
#   OPENCLAW_API_BACKEND_PORT  — 預設 8000
#
# 為什麼 dry-run 預設：避免 operator 誤跑覆蓋現有 /etc/caddy/Caddyfile。
# 加 `--apply` 才實際寫檔 + enable service。

set -euo pipefail

cd "$(dirname "$0")/.."
REPO_ROOT="$(pwd -P)"

# shellcheck source=lib/tls_cert.sh
source "$REPO_ROOT/helper_scripts/lib/tls_cert.sh"

APPLY=0
for arg in "$@"; do
    case "$arg" in
        --apply) APPLY=1 ;;
        --dry-run) APPLY=0 ;;
        -h|--help)
            sed -n '1,30p' "$0"
            exit 0
            ;;
        *)
            echo "ERROR: unknown arg: $arg" >&2
            exit 2
            ;;
    esac
done

UNAME="$(uname -s)"

# ── Step 1：驗 Tailscale 可用 ───────────────────────────────────────────────
if ! command -v tailscale >/dev/null 2>&1; then
    echo "ERROR: tailscale not installed; aborting (cert depends on it)" >&2
    exit 1
fi

CERT_HOST="$(resolve_openclaw_tls_cert_host)" || exit 2
CERT_DIR="$(resolve_openclaw_tls_cert_dir)" || exit 2
BACKEND_PORT="${OPENCLAW_API_BACKEND_PORT:-8000}"

# F-12：CERT_HOST 來自 tailscale CLI / env，理論上限 DNS 字符；明確校驗只允許
# `[A-Za-z0-9.-]` 防未來 user-provided 帶引號 / 空格 / shell metachar 注入 envsubst。
if ! printf '%s' "$CERT_HOST" | grep -qE '^[A-Za-z0-9][A-Za-z0-9.-]*$'; then
    echo "ERROR: invalid CERT_HOST '$CERT_HOST' — expected DNS-name characters only" >&2
    exit 2
fi
# BACKEND_PORT 必須是純數字
if ! printf '%s' "$BACKEND_PORT" | grep -qE '^[0-9]+$'; then
    echo "ERROR: invalid BACKEND_PORT '$BACKEND_PORT' — expected digits only" >&2
    exit 2
fi

echo "===== OPS-1 install_caddy.sh ====="
echo "platform        : $UNAME"
echo "cert host       : $CERT_HOST"
echo "cert dir        : $CERT_DIR"
echo "backend port    : $BACKEND_PORT"
echo "mode            : $([ "$APPLY" -eq 1 ] && echo APPLY || echo DRY-RUN)"
echo

# ── Step 2：Caddy 安裝（platform-aware） ─────────────────────────────────────
if ! command -v caddy >/dev/null 2>&1; then
    echo ">>> Caddy not found; installing..."
    case "$UNAME" in
        Linux)
            if [ "$APPLY" -eq 1 ]; then
                # 官方 apt repo（Debian/Ubuntu）
                sudo apt update
                sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https curl
                curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | \
                    sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
                curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | \
                    sudo tee /etc/apt/sources.list.d/caddy-stable.list
                sudo apt update
                sudo apt install -y caddy
            else
                echo "DRY-RUN: would install caddy via apt (Debian/Ubuntu official repo)"
            fi
            ;;
        Darwin)
            if [ "$APPLY" -eq 1 ]; then
                brew install caddy
            else
                echo "DRY-RUN: would run 'brew install caddy'"
            fi
            ;;
        *)
            echo "ERROR: unsupported platform for auto-install: $UNAME" >&2
            exit 1
            ;;
    esac
else
    echo ">>> Caddy already installed: $(caddy version 2>/dev/null | head -1)"
fi

# ── Step 3：產生 Caddyfile ───────────────────────────────────────────────────
TEMPLATE="$REPO_ROOT/helper_scripts/Caddyfile.template"
if [ ! -f "$TEMPLATE" ]; then
    echo "ERROR: template missing: $TEMPLATE" >&2
    exit 1
fi

case "$UNAME" in
    Linux)  CADDYFILE_DEST="/etc/caddy/Caddyfile" ;;
    Darwin) CADDYFILE_DEST="$(brew --prefix 2>/dev/null)/etc/Caddyfile" ;;
esac

echo ">>> Will write Caddyfile to: $CADDYFILE_DEST"
TMP_CADDYFILE="$(mktemp)"
OPENCLAW_TLS_CERT_HOST="$CERT_HOST" \
OPENCLAW_TLS_CERT_DIR="$CERT_DIR" \
OPENCLAW_API_BACKEND_PORT="$BACKEND_PORT" \
    envsubst < "$TEMPLATE" > "$TMP_CADDYFILE"

echo "--- generated Caddyfile preview ---"
cat "$TMP_CADDYFILE"
echo "--- end preview ---"

if [ "$APPLY" -eq 1 ]; then
    sudo mkdir -p "$(dirname "$CADDYFILE_DEST")"
    sudo mv "$TMP_CADDYFILE" "$CADDYFILE_DEST"
    sudo caddy validate --config "$CADDYFILE_DEST"
else
    rm -f "$TMP_CADDYFILE"
fi

# ── Step 4：取得 Tailscale cert ──────────────────────────────────────────────
CERT_CRT="$CERT_DIR/$CERT_HOST.crt"
CERT_KEY="$CERT_DIR/$CERT_HOST.key"

if [ ! -f "$CERT_CRT" ] || [ ! -f "$CERT_KEY" ]; then
    echo ">>> Tailscale cert missing; fetching..."
    if [ "$APPLY" -eq 1 ]; then
        sudo mkdir -p "$CERT_DIR"
        cd "$CERT_DIR"
        sudo tailscale cert "$CERT_HOST"
        # F-6：只在 caddy user 存在時才 chown；Linux apt 安裝會自建，macOS brew
        # 不會（brew 預設用呼叫者 user），盲跑 chown 會 silent fail 留 cert 給 root only。
        if id caddy >/dev/null 2>&1; then
            sudo chown root:caddy "$CERT_CRT" "$CERT_KEY"
        else
            echo ">>> caddy user not present; skip chown (Mac brew / non-systemd setup)"
        fi
        sudo chmod 640 "$CERT_CRT" "$CERT_KEY"
        cd "$REPO_ROOT"
    else
        echo "DRY-RUN: would run 'sudo tailscale cert $CERT_HOST'"
    fi
else
    echo ">>> Tailscale cert present"
    days="$(tls_cert_days_remaining "$CERT_CRT" 2>/dev/null || echo "?")"
    echo ">>> cert days remaining: $days"
fi

# ── Step 5：systemd unit / launchd plist ─────────────────────────────────────
case "$UNAME" in
    Linux)
        UNIT_SRC="$REPO_ROOT/helper_scripts/systemd/openclaw-caddy.service"
        TIMER_SRC="$REPO_ROOT/helper_scripts/systemd/openclaw-tls-renew.timer"
        RENEW_SRC="$REPO_ROOT/helper_scripts/systemd/openclaw-tls-renew.service"
        if [ "$APPLY" -eq 1 ]; then
            sudo cp "$UNIT_SRC" /etc/systemd/system/
            sudo cp "$TIMER_SRC" /etc/systemd/system/
            sudo cp "$RENEW_SRC" /etc/systemd/system/
            sudo systemctl daemon-reload
            sudo systemctl enable --now openclaw-caddy.service
            sudo systemctl enable --now openclaw-tls-renew.timer
            echo ">>> services enabled + started"
        else
            echo "DRY-RUN: would copy systemd units + enable openclaw-caddy + openclaw-tls-renew.timer"
        fi
        ;;
    Darwin)
        echo ">>> macOS detected — launchd plist 部署指引（手動）："
        echo "    1) 建 ~/Library/LaunchAgents/com.openclaw.caddy.plist 引用 brew Caddyfile"
        echo "    2) launchctl load com.openclaw.caddy.plist"
        echo "    3) cert renewal cron 用 StartCalendarInterval (Hour=3 Minute=0)"
        ;;
esac

# ── Step 6：驗證 ────────────────────────────────────────────────────────────
if [ "$APPLY" -eq 1 ]; then
    sleep 2
    echo ">>> probing https://$CERT_HOST/api/v1/healthz ..."
    if curl --max-time 5 -kI "https://$CERT_HOST/api/v1/healthz" 2>/dev/null | head -3; then
        echo ">>> healthcheck OK"
    else
        echo "WARN: healthcheck failed; check 'systemctl status openclaw-caddy.service'" >&2
    fi
fi

cat <<EOF
>>> first-use HTTPS cert trust checkpoint
    Open the GUI with the certificate hostname only:
      https://$CERT_HOST/
    Do not use the tailnet IP or short hostname for browser verification.
    On first Mac Chrome/Safari access, treat any certificate/privacy warning as
    a deployment checkpoint: inspect the certificate subject/SAN first. It must
    match $CERT_HOST. If it does not match, stop and fix OPENCLAW_TLS_CERT_HOST
    or DNS before proceeding. Do not click through a hostname mismatch.
    Runbook: docs/runbooks/2026-05-28--ops_1_cert_trust_first_use.md
EOF

echo "===== install_caddy.sh DONE ($([ "$APPLY" -eq 1 ] && echo APPLY || echo DRY-RUN)) ====="

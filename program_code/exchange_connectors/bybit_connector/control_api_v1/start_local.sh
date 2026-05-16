#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# OpenClaw / Bybit Control API v1 — 本地一键启动脚本
# OpenClaw / Bybit Control API v1 — One-click local startup script
#
# 用法 / Usage:
#   bash start_local.sh              # 默认端口 8710
#   bash start_local.sh 8100         # 自定义端口
#   PORT=8100 bash start_local.sh    # 环境变量方式
#
# 前提条件 / Prerequisites:
#   - Python 3.10+
#   - 当前目录为 control_api_v1/
#
# 功能 / Features:
#   - 自动创建 venv（如不存在）/ Auto-creates venv if not present
#   - 自动安装依赖 / Auto-installs dependencies
#   - 设置默认环境变量 / Sets default env vars
#   - 启动 uvicorn 并开启 reload 模式 / Starts uvicorn with auto-reload
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
cd "$SCRIPT_DIR"

# 端口：命令行参数 > 环境变量 > 默认 8710
# Port: CLI arg > env var > default 8710
PORT="${1:-${PORT:-8710}}"

# API 綁定地址：預設 auto（Tailscale IPv4 可用時使用，否則 loopback），允許
# OPENCLAW_BIND_HOST override；拒絕 0.0.0.0 / ::。
# API bind host: default auto (Tailscale IPv4 when available, otherwise
# loopback), with OPENCLAW_BIND_HOST override and all-interface rejection.
source "$REPO_ROOT/helper_scripts/lib/api_bind_host.sh"
API_BIND_HOST="$(resolve_openclaw_api_bind_host)"

echo "═══════════════════════════════════════════════════"
echo " OpenClaw / Bybit Control API v1 — 本地启动"
echo " Local Startup"
echo "═══════════════════════════════════════════════════"

# ── 1. 检查 / 创建 venv ──────────────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "[1/3] 创建虚拟环境 / Creating virtual environment..."
    python3 -m venv .venv
else
    echo "[1/3] 虚拟环境已存在 / Virtual environment exists."
fi

# ── 2. 安装依赖 ──────────────────────────────────────────────────────────
echo "[2/3] 安装依赖 / Installing dependencies..."
.venv/bin/pip install -q -r requirements.txt

# ── 3. 设置环境变量（仅当未设置时）────────────────────────────────────────
# 中文：本地开发若未显式提供 token，则生成 0600 token 文件并通过
# OPENCLAW_API_TOKEN_FILE 传入；不在终端打印 token。
# English: For local dev, generate a 0600 token file when no explicit token is
# provided and pass it via OPENCLAW_API_TOKEN_FILE; never print the token.
if [ -z "${OPENCLAW_API_TOKEN:-}" ] && [ -z "${OPENCLAW_API_TOKEN_FILE:-}" ]; then
    mkdir -p .secrets
    chmod 700 .secrets
    if [ ! -s ".secrets/api_token" ]; then
        umask 077
        .venv/bin/python3 - <<'PY' > .secrets/api_token
import secrets
print(secrets.token_urlsafe(32))
PY
        chmod 600 .secrets/api_token
    fi
    export OPENCLAW_API_TOKEN_FILE="$SCRIPT_DIR/.secrets/api_token"
fi
export OPENCLAW_STATE_FILE="${OPENCLAW_STATE_FILE:-runtime/openclaw_bybit_control_state.json}"

# 确保 runtime 目录存在 / Ensure runtime directory exists
mkdir -p "$(dirname "$OPENCLAW_STATE_FILE")"

echo "[3/3] 启动服务 / Starting service..."
echo ""
echo "  Auth:   token configured (value hidden)"
echo "  Bind:   ${API_BIND_HOST}"
echo "  State:  ${OPENCLAW_STATE_FILE}"
echo "  Port:   ${PORT}"
echo ""
echo "  GUI:    http://${API_BIND_HOST}:${PORT}/"
echo "  API:    http://${API_BIND_HOST}:${PORT}/docs"
echo ""
echo "  Token 值不打印；如需 API bearer，读取 0600 token 文件。"
echo "  Token value is hidden; read the 0600 token file only when API bearer access is needed."
echo ""
echo "═══════════════════════════════════════════════════"

exec .venv/bin/uvicorn app.main:app \
    --host "$API_BIND_HOST" \
    --port "$PORT" \
    --reload

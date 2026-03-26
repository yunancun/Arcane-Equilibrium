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
cd "$SCRIPT_DIR"

# 端口：命令行参数 > 环境变量 > 默认 8710
# Port: CLI arg > env var > default 8710
PORT="${1:-${PORT:-8710}}"

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
export OPENCLAW_API_TOKEN="${OPENCLAW_API_TOKEN:-change-me}"
export OPENCLAW_STATE_FILE="${OPENCLAW_STATE_FILE:-runtime/openclaw_bybit_control_state.json}"

# 确保 runtime 目录存在 / Ensure runtime directory exists
mkdir -p "$(dirname "$OPENCLAW_STATE_FILE")"

echo "[3/3] 启动服务 / Starting service..."
echo ""
echo "  Token:  ${OPENCLAW_API_TOKEN}"
echo "  State:  ${OPENCLAW_STATE_FILE}"
echo "  Port:   ${PORT}"
echo ""
echo "  GUI:    http://127.0.0.1:${PORT}/"
echo "  API:    http://127.0.0.1:${PORT}/docs"
echo ""
echo "  输入 Token \"${OPENCLAW_API_TOKEN}\" 后点击「连接」"
echo "  Enter token \"${OPENCLAW_API_TOKEN}\" then click Connect"
echo ""
echo "═══════════════════════════════════════════════════"

exec .venv/bin/uvicorn app.main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --reload

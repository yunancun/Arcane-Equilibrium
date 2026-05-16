#!/bin/bash
# ═══════════════════════════════════════════════════════════════════════════════
# OpenClaw Paper Trading Beta 快速启动脚本
# Beta Quick Start: Observer Bridge + Control API + Market Feed
#
# 用法 / Usage:
#   bash scripts/beta_quickstart.sh
#
# 此脚本做三件事 / This script does three things:
#   1. 运行 auto-bridge 生成 runtime snapshot（从 observer 输出）
#   2. 启动 Control API 服务器（含 Paper Trading + Market Feed 路由）
#   3. 打印启动后的操作指引
#
# 安全说明 / Safety:
#   system_mode=read_only, execution_state=disabled, execution_authority=not_granted
#   所有交易均为纸上模拟 / All trades are paper-simulated
# ═══════════════════════════════════════════════════════════════════════════════

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$PROJECT_DIR/.venv/bin"
# XP-1: Use env var with auto-detection fallback / 环境变量优先，回退自动推导
_SRV="${OPENCLAW_SRV_ROOT:-$(cd "$SCRIPT_DIR/../../../../.." && pwd)}"
RUNTIME_DIR="$_SRV/docker_projects/trading_services/runtime/bybit"
SNAPSHOT_PATH="$RUNTIME_DIR/runtime_snapshot_generated.json"

# API 綁定地址：預設 auto（Tailscale IPv4 可用時使用，否則 loopback），允許
# OPENCLAW_BIND_HOST override；拒絕 0.0.0.0 / ::。
# API bind host: default auto (Tailscale IPv4 when available, otherwise
# loopback), with OPENCLAW_BIND_HOST override and all-interface rejection.
source "$_SRV/helper_scripts/lib/api_bind_host.sh"
API_BIND_HOST="$(resolve_openclaw_api_bind_host)"

echo "═══════════════════════════════════════════════════════════════"
echo "  OpenClaw Paper Trading Beta — 快速启动 / Quick Start"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# ── Step 1: Run auto-bridge / 第一步：运行自动桥接 ──
echo "[1/3] 运行 Observer → Runtime Snapshot 桥接..."
echo "      Running auto-bridge..."
"$VENV/python3" "$SCRIPT_DIR/auto_bridge_observer_to_runtime_snapshot.py" \
    --output "$SNAPSHOT_PATH" \
    --quiet || {
    echo "[WARN] Bridge produced warnings, but continuing..."
}
echo "      ✓ Runtime snapshot generated: $SNAPSHOT_PATH"
echo ""

# ── Step 2: Set environment / 第二步：设置环境变量 ──
export OPENCLAW_RUNTIME_SNAPSHOT_FILE="$SNAPSHOT_PATH"
export OPENCLAW_PAPER_STATE_FILE="$RUNTIME_DIR/paper_trading_state.json"

echo "[2/3] 环境变量已设置 / Environment set:"
echo "      OPENCLAW_RUNTIME_SNAPSHOT_FILE=$SNAPSHOT_PATH"
echo "      OPENCLAW_PAPER_STATE_FILE=$OPENCLAW_PAPER_STATE_FILE"
echo ""

# ── Step 3: Start API server / 第三步：启动 API 服务器 ──
echo "[3/3] 启动 Control API 服务器..."
echo "      Starting Control API server..."
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Beta 操作指南 / Beta Operation Guide"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo "  1. 打开浏览器访问 / Open browser:"
echo "     http://${API_BIND_HOST}:8000/static/index.html"
echo ""
echo "  2. 输入 Token 并连接 / Enter token and connect"
echo "     Token 在: $PROJECT_DIR/.secrets/api_token"
echo ""
echo "  3. 在 Paper Trading 区块中:"
echo "     a. 点击「启动行情流 / Start Feed」连接 Bybit WebSocket"
echo "     b. 点击「开始交易 / Start」启动 paper session"
echo "     c. 提交订单（market/limit）测试成交模拟"
echo ""
echo "  4. 停止: Ctrl+C"
echo "═══════════════════════════════════════════════════════════════"
echo ""

cd "$PROJECT_DIR"
"$VENV/uvicorn" app.main:app --host "$API_BIND_HOST" --port 8000

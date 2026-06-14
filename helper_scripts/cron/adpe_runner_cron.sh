#!/usr/bin/env bash
# MODULE_NOTE (CN): Adaptive Demo Profit Engine 閉環 runner cron。每次：讀近窗 realized demo PnL
#   (learning.mlde_edge_training_rows, post-fee) → regime-conditional Thompson bandit allocate →
#   寫 explore overlay 進 edge_estimates.json（reloader 起後引擎 ≤300s 自動 reload）+ set_strategy_active
#   保 explore-eligible 策略 active 供 demo explore-gate 放行收集探索數據。
#   demo 沙盒 only（runner engine_mode 硬鎖 demo, fail-closed）；真錢 / mainnet 5-gate 完全不碰。
#   有界探索（explore_budget=30/arm，耗盡即停）。誠實鐵則：全負 EV → allocator 歸 flat（不硬湊正）。
# MODULE_NOTE (EN): ADPE closed-loop runner cron (demo sandbox only; never touches live/mainnet).
set -euo pipefail
REPO="${OPENCLAW_BASE_DIR:-$HOME/BybitOpenClaw/srv}"
cd "$REPO"
export PYTHONPATH="$REPO/program_code:$REPO"
# DSN：預設本機 trading_ai，密碼走 ~/.pgpass（passwordless）。
DSN="${OPENCLAW_DATABASE_URL:-postgresql://trading_admin@127.0.0.1:5432/trading_ai}"
exec /usr/bin/python3 -m program_code.ml_training.adaptive_demo_profit_engine.runner \
  --config settings/adaptive_demo_profit.toml --apply --dsn "$DSN"

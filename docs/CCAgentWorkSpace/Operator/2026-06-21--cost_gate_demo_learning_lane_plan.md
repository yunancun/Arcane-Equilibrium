# Cost-Gate Demo-Learning Lane Plan

已把 cost-gate blocked-signal scorecard 轉成 bounded demo-learning plan，並接入 alpha-discovery killboard。

關鍵結果：

- Plan: `/tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json`
- Plan sha256: `66d07781be9885b777c6dd0cd2e5add5823514ac4b9a90dee9ef710f42859b7b`
- Status: `READY_FOR_DEMO_LEARNING_PROBE`
- Main cost gate: `NONE`（不全局降低）
- Order authority: `NOT_GRANTED`
- Selected side-cells: `ma_crossover ETH/NEAR Sell`, `grid_trading LTC/ATOM Sell`
- Alpha-discovery: `ACTIONABLE_PROBE_READY`, but `actionable_alpha_found=false` and `promotion_ready_count=0`

這代表系統現在知道「哪幾個被擋 side-cell 值得進 demo 學習」，但還沒有授權下單。下一步是寫 demo-only runtime adapter：消費這份 plan、限制 side-cell/budget/cooldown、記錄 probe attempts/outcomes、回灌 edge estimates。

Boundary：只改 source/test/docs，同步 Linux source，寫 `/tmp/openclaw` artifacts；沒有 PG 寫入、沒有 Bybit private/trading call、沒有重啟、沒有改 auth/risk/order/strategy。

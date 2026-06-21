# Cost-Gate Profit Opportunity Ranking

本次改動不是再補 cron/preflight，而是把 Cost Gate reject counterfactual 直接變成 profit-learning ranking。

`cost_gate_reject_counterfactual.py` 現在輸出 `cost_gate_profit_opportunity_ranking_v1`。每個 side-cell 都有 priority score、tier、next action，並明確固定：

- `order_authority=NOT_GRANTED`
- `main_cost_gate_adjustment=NONE`
- `promotion_evidence=false`

用現有 runtime latest JSON 只讀試算，Top candidate 是：

1. `ma_crossover|ETHUSDT|Sell`：score `74.4954`, avg net `97.9788bp`, net-positive `86.01%`
2. `ma_crossover|NEARUSDT|Sell`：score `58.5825`, avg net `16.2197bp`, net-positive `99.95%`
3. `grid_trading|LTCUSDT|Sell`：score `26.3149`
4. `grid_trading|ATOMUSDT|Sell`：score `21.7214`

`grid_trading|FILUSDT|Buy` 分數高但 n=57，仍小於 sample gate，所以只能繼續收集，不是 probe-ready。

操作含義：下一個硬決策應是是否對 `ma_crossover|ETHUSDT|Sell` 做 operator-reviewed bounded demo-learning lane，而不是全局降低 Cost Gate。

驗證：focused smoke 64 passed；py_compile PASS；diff-check PASS；runtime JSON 只讀處理 PASS。沒有 runtime 寫入、沒有下單、沒有降低 Cost Gate。

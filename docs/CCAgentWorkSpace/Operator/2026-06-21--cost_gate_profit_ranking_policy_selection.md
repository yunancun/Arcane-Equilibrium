# Cost-Gate Profit Ranking Policy Selection

我把 v335 的 profit-opportunity ranking 接進 bounded demo-learning plan。

效果：當 counterfactual scorecard 刷新後帶有 `cost_gate_profit_opportunity_ranking_v1`，`cost_gate_learning_lane.policy` 會按 ranking `top_side_cells` 選 candidate，不再只靠 legacy avg-net sorting。

安全邊界沒變：candidate 仍必須是 `LEARNING_PROBE_CANDIDATE`、過 sample gate，且 row 上明確是：

- `order_authority=NOT_GRANTED`
- `main_cost_gate_adjustment=NONE`
- `promotion_evidence=false`

current runtime latest artifact 還沒刷新，所以直接讀 runtime JSON 時 plan 還是 `legacy_scorecard_candidates`。我用同一份 JSON 本地注入 ranking 後試算，plan 會切到 `profit_opportunity_ranking`，並保留 ETH/NEAR/LTC/ATOM 的 priority score/tier。

驗證：focused smoke 96 passed；py_compile PASS；diff-check PASS；runtime JSON 只讀試算 PASS。沒有 runtime 寫入、沒有下單、沒有降低 Cost Gate。

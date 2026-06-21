# Cost-Gate Profit Opportunity Ranking

## 結論

這次不再補 wrapper / installer / preflight，而是把已有 Cost Gate reject counterfactual 直接轉成可決策 ranking。

`helper_scripts/db/audit/cost_gate_reject_counterfactual.py` 現在在既有 `learning_lane_scorecard` 內輸出 `cost_gate_profit_opportunity_ranking_v1`。它把每個 blocked side-cell 轉成：

- `side_cell_key`
- priority score / tier
- sample、avg net、median margin、hit-rate margin
- next action
- 明確邊界：`order_authority=NOT_GRANTED`、`main_cost_gate_adjustment=NONE`、`promotion_evidence=false`

## Ranking 邏輯

透明 capped scoring：

- sample：`min(log10(n+1)/4,1)*25`
- avg net：`clamp((avg_net_bps-min_probe_avg_net_bps)/100,0,1)*25`
- median margin：`clamp((p50_gross_bps-friction_bps)/50,0,1)*25`
- hit-rate：`clamp((net_positive_pct-50)/50,0,1)*25`

這不是 alpha promotion score，也不授權 demo order。它只回答下一步該把 bounded demo-learning review 放在哪些 side-cell 上。

## Runtime Read-Only Trial

我用本地新邏輯只讀處理現有 runtime artifact：

- source：`/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json`
- access：`ssh trade-core` read-only `cat`，本地處理 JSON
- status：`PROFIT_LEARNING_CANDIDATES_PRESENT`
- next trigger：`operator_review_top_ranked_side_cells_for_bounded_demo_learning_lane`

Top ranked rows：

| rank | side_cell | tier | score | n | avg_net | p50 | net+% | action |
|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | `ma_crossover|ETHUSDT|Sell` | `HIGH_PRIORITY_BOUNDED_DEMO_LEARNING` | 74.4954 | 13487 | 97.9788 | 17.9914 | 86.01 | operator review |
| 2 | `ma_crossover|NEARUSDT|Sell` | `LOW_PRIORITY_BOUNDED_DEMO_LEARNING` | 58.5825 | 2125 | 16.2197 | 21.5106 | 99.95 | operator review |
| 3 | `grid_trading|LTCUSDT|Sell` | `LOW_PRIORITY_BOUNDED_DEMO_LEARNING` | 26.3149 | 132 | 9.5123 | 10.1755 | 65.15 | operator review |
| 4 | `grid_trading|ATOMUSDT|Sell` | `LOW_PRIORITY_BOUNDED_DEMO_LEARNING` | 21.7214 | 166 | 3.5169 | 11.8803 | 56.02 | operator review |
| 5 | `grid_trading|ETHUSDT|Sell` | `TAIL_ONLY_WATCH_NO_PROBE` | 16.2923 | 342 | 1.7867 | -9.8168 | 27.49 | watch only |
| 6 | `grid_trading|FILUSDT|Buy` | `COLLECT_MORE_SAMPLE` | 63.4720 | 57 | 58.9223 | 81.5493 | 75.44 | collect sample |

## 判斷

現在最值得 review 的不是「全局 lower Cost Gate」，而是 `ma_crossover|ETHUSDT|Sell` 的 bounded demo-learning lane。

`FILUSDT Buy` 分數高但 n=57，小於 min sample 100，所以仍然 sample-gated。這是 ranking 和 admission gate 分離的原因：ranking 可以提示「值得收集」，但不能繞過樣本門檻。

## 邊界

- Source/test/docs + read-only runtime artifact inspection only。
- 不寫 runtime artifact。
- 不安裝 cron。
- 不啟 writer。
- 不 append ledger。
- 不連 PG。
- 不連 Bybit private/signed/trading API。
- 不下單。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不授權 demo order。

## 驗證

- `python3 -m pytest helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/db/audit/test_demo_learning_evidence_audit.py -q`：64 passed
- `python3 -m py_compile helper_scripts/db/audit/cost_gate_reject_counterfactual.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py`：PASS
- `git diff --check`：PASS
- Runtime latest JSON read-only processed locally via `ssh trade-core`：PASS

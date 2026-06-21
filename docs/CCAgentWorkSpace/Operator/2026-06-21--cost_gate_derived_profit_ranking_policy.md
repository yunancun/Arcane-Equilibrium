# Cost-Gate Derived Profit Ranking Policy

## 結論

這次改動消除了「必須先刷新 runtime counterfactual artifact，demo-learning plan 才能吃到 profit ranking」的依賴。

現在 `cost_gate_learning_lane.policy` 在 current runtime latest JSON 沒有 embedded ranking 時，會直接從 existing scorecard rows 派生 ranking。只讀測試顯示當前 artifact 已能選出排名候選：

- `ma_crossover|ETHUSDT|Sell`：score `74.4954`，HIGH
- `ma_crossover|NEARUSDT|Sell`：score `58.5825`
- `grid_trading|LTCUSDT|Sell`：score `26.3149`
- `grid_trading|ATOMUSDT|Sell`：score `21.7214`

## 對決策的意義

下一步不應再卡在「重新產生 artifact 才能排序」。目前已經足夠支撐 operator-reviewed bounded demo-learning activation 的討論：小範圍、side-cell 級、demo-only、以實際後續市場結果驗證 Cost Gate 是否過度阻擋。

## 邊界

本次沒有：

- 降低 main Cost Gate
- 授權 demo/live order
- 啟用 writer
- append ledger
- 安裝 cron
- 寫 PG
- 連 Bybit private/signed/trading API
- deploy / rebuild / restart / runtime source sync

所有候選仍是 `order_authority=NOT_GRANTED`、`main_cost_gate_adjustment=NONE`、`promotion_evidence=false`。

## 驗證

- Policy / alpha-discovery / counterfactual adjacent tests：96 passed
- Python compile：PASS
- Diff whitespace check：PASS
- Current runtime latest JSON：read-only SSH 讀取，本地 transform 成功，source=`derived_from_scorecard_rows`

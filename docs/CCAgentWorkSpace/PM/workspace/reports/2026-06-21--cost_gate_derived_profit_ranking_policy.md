# Cost-Gate Derived Profit Ranking Policy

## 結論

v336 已經讓 bounded demo-learning plan 優先吃 `cost_gate_profit_opportunity_ranking_v1`，但 current runtime latest artifact 尚未刷新，所以仍會落回 legacy selection。

這次補上缺口：`helper_scripts/research/cost_gate_learning_lane/policy.py` 現在可以在 embedded `profit_opportunity_ranking` 缺失時，直接從 legacy `cost_gate_reject_counterfactual_v2` scorecard `rows` 派生同 schema ranking。這讓現有 runtime artifact 也能產生 profit-ranked demo-learning plan，不需要先刷新 `/tmp/openclaw` artifact。

## 行為

派生 ranking 使用和 audit ranking 相同的透明 scoring 維度：

- sample size
- average net bps
- median gross margin over friction
- net-positive hit rate

Selected plan rows 仍需通過原本全部邊界：

- `learning_lane_action=LEARNING_PROBE_CANDIDATE`
- sample gate
- `order_authority=NOT_GRANTED`
- `main_cost_gate_adjustment=NONE`
- `promotion_evidence=false`

Plan source 會記錄：

- `probe_candidate_ranking_source=derived_from_scorecard_rows`
- `profit_opportunity_ranking_status=PROFIT_LEARNING_CANDIDATES_PRESENT`

## Runtime Read-Only Trial

以 read-only SSH 讀取 current runtime latest JSON，並只在 Mac 本地 transform：

- input：`/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json`
- plan status：`READY_FOR_DEMO_LEARNING_PROBE`
- ranking source：`derived_from_scorecard_rows`
- top selected candidate：`ma_crossover|ETHUSDT|Sell`
- ETH Sell score：`74.4954`
- ETH tier：`HIGH_PRIORITY_BOUNDED_DEMO_LEARNING`
- following candidates：`ma_crossover|NEARUSDT|Sell`、`grid_trading|LTCUSDT|Sell`、`grid_trading|ATOMUSDT|Sell`

這證明下一步不是等待 artifact refresh，而是 operator-reviewed bounded activation / evidence accumulation。

## 邊界

- Source/test/docs + read-only runtime artifact inspection only。
- 不刷新 runtime artifact。
- 不同步 runtime source。
- 不安裝 cron。
- 不啟 writer。
- 不 append ledger。
- 不連 PG。
- 不連 Bybit private/signed/trading API。
- 不下單。
- 不改 auth / risk / strategy / runtime config。
- 不降低 main Cost Gate。
- 不授權 demo order。
- 不構成 execution proof 或 promotion proof。

## 驗證

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py -q`：96 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/policy.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/db/audit/cost_gate_reject_counterfactual.py`：PASS
- `git diff --check`：PASS
- Runtime current JSON read-only derived-ranking trial：PASS

# Cost-Gate Profit Ranking Policy Selection

## 結論

v335 讓 counterfactual audit 產生 profit-opportunity ranking；這次把 ranking 接進 bounded demo-learning policy plan。

`helper_scripts/research/cost_gate_learning_lane/policy.py` 現在優先使用：

`learning_lane_scorecard.profit_opportunity_ranking.top_side_cells`

作為 selected probe candidate source。沒有 ranking 的舊 scorecard 仍 fallback 到原本 `probe_candidates` / `rows` 的 avg-net sorting。

## 行為

Ranking source 只有在以下條件全滿足時才可進 plan：

- ranking schema = `cost_gate_profit_opportunity_ranking_v1`
- row action = `LEARNING_PROBE_CANDIDATE`
- `n >= min_candidate_sample`
- `order_authority=NOT_GRANTED`
- `main_cost_gate_adjustment=NONE`
- `promotion_evidence=false`

被選中的 plan row 會保留：

- `profit_priority_score`
- `profit_priority_tier`
- `profit_priority_components`
- `profit_priority_next_action`

Plan source 也會記錄：

- `profit_opportunity_ranking_schema_version`
- `profit_opportunity_ranking_status`
- `profit_opportunity_ranking_next_trigger`
- `probe_candidate_ranking_source`

## Runtime Read-Only Trial

current runtime latest artifact 還沒由 v335 source 刷新，所以直接讀 `/tmp/openclaw/cost_gate_counterfactual/cost_gate_reject_counterfactual_latest.json` 生成 plan 時：

- `probe_candidate_ranking_source=legacy_scorecard_candidates`
- priority score/tier 為 null

同一份 runtime JSON 若本地注入 v335 ranking 後再進 policy：

- `probe_candidate_ranking_source=profit_opportunity_ranking`
- selected candidates 保留 priority score/tier
- selected order：ETH / NEAR / LTC / ATOM Sell

這證明 source chain 已接通，但 runtime artifact refresh 尚未執行。

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

## 驗證

- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/research/tests/test_alpha_discovery_throughput.py helper_scripts/db/audit/test_cost_gate_reject_counterfactual.py -q`：96 passed
- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/policy.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py helper_scripts/db/audit/cost_gate_reject_counterfactual.py`：PASS
- `git diff --check`：PASS
- Runtime current JSON read-only fallback trial：PASS
- Runtime current JSON + local injected ranking selection trial：PASS

# Operator Note — MM Gross-Edge Cost Decomposition

日期：2026-06-20

這批是診斷修正，不是交易變更。

MM 目前不是「完全沒有毛邊際」；最新 fill_sim evidence 顯示有 sample-gated gross edge，但現行 maker fee 仍吃掉它：

- MM verdict status-line sha256 `6e1cfda2a71fa17079b5dd9194135986641a274006feedcf0231e0b7b28b65af`
- status `GROSS_EDGE_BELOW_CURRENT_FEE_COST_WALL`
- gross-positive sample-gated cells = 38
- current-fee-positive sample-gated cells = 0
- best cell `LABUSDT` / back / informed_skip
- gross `2.27bp`, current-fee net `-1.73bp`
- break-even maker fee `1.135bp/side`
- fee reduction needed `0.865bp/side`
- best walk-forward holdout gross candidate `symbol=ADAUSDT`: gross `2.002bp`, net `-1.998bp`

Alpha discovery latest sha256 `187e21bdf45b35d1f57677707743e483bd7244390d4b17099b713ed12898b6d8` still says `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, ready/probe=0. MM top blocker is now `cost_wall:gross_edge_below_current_fee_no_current_fee_walk_forward_positive`.

Operator implication：no live/demo retune, no strategy promotion, no probe. The next useful work is either real lower-fee eligibility proof or a new low-friction MM signal that clears current-fee walk-forward gates.

驗證：Mac/Linux alpha focused tests `25 passed`，cron static `11 passed`，py_compile、shell syntax、diff-check、MM verdict smoke、alpha discovery smoke passed。邊界：source/test/docs + `/tmp/openclaw` artifact/status writes only；沒有 PG write、Bybit private/signed/trading call、engine/API restart、strategy/risk/order/auth mutation。

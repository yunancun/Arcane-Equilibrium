# Candidate-Matched Touchability Gate

Date: 2026-06-24

本輪修正一個會污染 Demo learning 的 source-only 問題：`demo_order_to_fill_gap` 的 aggregate `FILL_FLOW_PRESENT` 不能再讓 bounded probe touchability 直接 ready，除非成交行本身匹配 active candidate 的 `strategy_name + symbol + side`。

## Operator Meaning

- 目前選中的高 upside candidate 仍是 `grid_trading|AVAXUSDT|Sell`。
- runtime artifact 裡確實有 4 筆 Demo fills，但它們是 SOL/ETH/XRP risk-close 或 XRP flash-dip，不是 `grid_trading|AVAXUSDT|Sell`。
- 因此這些 fill 可以作為系統健康/執行流資料，但不能作為 bounded probe touchability proof、Cost Gate proof、或 promotion proof。
- 新 gate 用同一批 runtime artifacts 重算後會得到：
  - touchability `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
  - candidate-matched orders `0`
  - candidate-matched fills `0`
  - non-candidate fills `4`
  - placement repair `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
  - defer-only authorization review-ready，但 `operator_authorization=null`

## Runtime Refresh

Source fix `98e34a90` was pushed and Linux `trade-core` was fast-forwarded clean to it. The runtime `/tmp/openclaw` latest artifacts were refreshed artifact-only:

- false-negative review: `APPROVED_COST_GATE_FALSE_NEGATIVE_FOR_BOUNDED_DEMO_PROBE_PREFLIGHT`
- false-negative preflight: `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`
- touchability: `TOUCHABILITY_REPAIR_REQUIRED_BEFORE_BOUNDED_DEMO_PROBE`
- placement: `PLACEMENT_REPAIR_PLAN_READY_FOR_OPERATOR_REVIEW`
- authority readiness: `AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW`
- authorization: `READY_FOR_OPERATOR_AUTHORIZATION_REVIEW`, defer-only, no emitted authorization object

Concern: recurring default-defer false-negative review refresh can overwrite the explicit approval artifact. It fails closed rather than granting authority, but it can erase review progress. The next safe source-only step is to preserve explicit approvals or write defer refreshes to a separate artifact.

## Live-Portability Boundary

你的 Demo 授權可以讓我們建立 review packets 和 bounded Demo design，但不能被寫成不可重建的隱式 order authority。若要讓 Demo 經驗後續可 apply live，必須保留：

- exact candidate identity：strategy / symbol / side / horizon
- exact bounded authorization id / expiry / budget / typed confirm
- order-to-fill lineage
- fee/slippage / maker-taker classification
- matched blocked controls
- execution-realism review

本輪沒有下單、沒有撤單、沒有 Bybit signed call、沒有 PG write、沒有改 crontab/service、沒有降低 Cost Gate、沒有 live promotion、沒有授權 probe/order。

## Verification

- focused touchability/placement tests: `18 passed`
- alpha/authorization/scorecard tests: `106 passed`
- cron static tests: `14 passed`
- adjacent bounded suite: `27 passed`
- `py_compile` and `git diff --check`: passed
- Linux focused tests after source sync: `18 passed`
- Linux alpha/authorization/scorecard: `106 passed`

PM report: `docs/CCAgentWorkSpace/PM/workspace/reports/2026-06-24--candidate_matched_touchability_gate.md`

# Operator Summary - NEAR Buy Fresh Window Refresh Request

Status: `READY_FOR_PM_E3_DISPATCH`

PM completed three-way sync and restarted from current dynamic runtime truth. Current candidate is still `ma_crossover|NEARUSDT|Buy` with `avg_net_bps=64.983`; current latest runtime `outcome_count` is `5058`.

What changed:

- Canonical runtime soak plan was materialized to the reviewed NEAR Buy plan under the prior E3/BB-approved plan-materialization scope.
- Active order source contract is now READY for E3/BB review, but it grants no runtime/order authority.
- Strict scan found zero candidate-matched actual order/fill evidence.
- The next order-capable packet is blocked only because the old no-order BBO/lease window is stale and was approved at old checkpoint `08f7e957...`, not current checkpoint `c66338e8...`.

New request:

- `docs/CCAgentWorkSpace/PM/workspace/reports/2026-07-08--profit_first_near_buy_order_capable_fresh_window_refresh_request.json`

This request is no-order only: E3/BB review for a fresh same-window public BBO/instrument refresh and short no-order Decision Lease acquire/release. It does not authorize order/probe/private endpoint use.

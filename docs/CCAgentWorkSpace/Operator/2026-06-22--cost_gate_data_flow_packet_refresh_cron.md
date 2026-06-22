# 2026-06-22 Cost Gate Data-Flow Packet Refresh Cron

## Operator Summary

v413 makes the Cost Gate learning cron refresh the demo data-flow monitor and profit-learning decision packet automatically. The loop can now answer whether rejects are recorded, whether signals are silently dropped, and whether a blocked side-cell is ready for operator review.

Current runtime answer:

- data is flowing;
- Cost Gate rejects are recorded;
- silent-drop risk is `false`;
- broad window has `58968` Cost Gate rejects;
- broad window has `3` demo orders and `0` fills;
- top learning task is still operator review of `ma_crossover|ETHUSDT|Sell` before any bounded demo probe.

## Decision Point

Do not globally lower Cost Gate from this evidence. The next real blocker is order-to-fill/execution realism: demo orders exist but fills do not.

The next operator-gated path is:

1. review the blocked side-cell evidence;
2. authorize a bounded demo probe only if accepted;
3. require matched-control result review and execution-realism review before any Cost Gate change.

## Boundary

No CI, no cron install, no deploy/restart, no PG writes, no Bybit private/trading call, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.

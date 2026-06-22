# 2026-06-22 Demo Order-To-Fill Gap Touchability Audit

## Operator Summary

v414 explains why Demo has orders but no fills.

Runtime read-only audit over the last 48h:

- 6 Demo orders reviewed;
- 6/6 are PostOnly Buy;
- 0 fills;
- 6/6 `orders.price` is missing but effective limit price is recoverable from `intents.details.limit_price`;
- 0 orders were touched by BBO;
- all 6 were deep passive no-touch orders, with best touch gaps around `1156-1531bp`.

Conclusion: current no-fill evidence points to order placement being too deep, not to silent signal loss and not to a proven broken fill recorder.

## Decision Point

Do not globally lower Cost Gate from this evidence.

The next profitable path is a touchability-aware bounded Demo probe design: operator-reviewed, small, side-cell/horizon-specific, and measurable by matched-control result review plus execution-realism review.

## Boundary

No CI, no cron install, no deploy/restart, no PG writes, no Bybit private/trading call, no env/auth/risk/order/strategy mutation, no Cost Gate lowering, no probe/order authority, and no promotion proof.

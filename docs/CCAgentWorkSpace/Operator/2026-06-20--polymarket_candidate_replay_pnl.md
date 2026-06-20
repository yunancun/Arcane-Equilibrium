# 2026-06-20 Polymarket Candidate Replay PnL

## Operator Read

Polymarket `price_target|SOLUSDT|15m` now has paper replay PnL evidence, but it is not tradable authority.

- Replay sample: `32`.
- Gross mean: `4.771bp`.
- Diagnostic cost: `4.0bp`.
- Net mean: `0.771bp`.
- Holdout net mean: `6.829bp`.
- Evidence span: `n_days=1`.
- Candidate metrics: `FAIL` due `n_days_below_30` and `missing_pbo`.
- Execution realism: `UNMEASURED`.
- Formal matrix: `insufficient evidence`.
- Alpha scorecard: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`, promotion_ready `0`.

## Action

No operator action, no strategy change, no probe, no live/demo order.

Next research trigger is to keep collecting dated replay samples and build real execution/breadth evidence before any promotion discussion.

## Boundary

This checkpoint only wrote research artifacts under `/tmp/openclaw` plus repo docs/source/tests. No PG write, Bybit private/signed/trading call, engine/API rebuild/restart, credential/auth/risk/order/strategy mutation, or promotion proof.

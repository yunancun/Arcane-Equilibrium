# Cost Gate Downstream Effective-Sample Guard

Date: 2026-06-22

## Summary

I closed a downstream sample-inflation gap. The bounded learning plan and historical review now use the same effective sample definition as the Cost Gate counterfactual scorecard.

Concretely, `sample_count_for_gate` / `distinct_ts` now controls sample qualification before raw row count. A candidate with `n=500` but only `sample_count_for_gate=3` is rejected from bounded demo-probe planning and historical review, even if its priority score is high.

## Verified

- py_compile passed
- `test_cost_gate_learning_lane_policy.py` = `65 passed`
- decision-packet + alpha focused tests = `53 passed`

## Boundary

This does not lower Cost Gate, does not grant probe/order authority, and does not prove execution profitability. It only prevents duplicated reject rows from making a bounded learning candidate look sample-qualified.

Runtime source sync is separately operator-authorized after this checkpoint; sync should not include deploy/rebuild/restart, cron install, env edit, PG write, Bybit call, or strategy/risk/order mutation unless separately authorized.

# Cost Gate Downstream Effective-Sample Guard

Date: 2026-06-22

## Verdict

`DONE_WITH_BOUNDARIES`.

The upstream Cost Gate reject counterfactual now emits effective sample fields, and the downstream bounded learning consumers now honor the same sample definition. A duplicate-inflated side-cell can no longer re-enter bounded demo-probe planning through policy or historical-review fallbacks.

## Why This Was Needed

The v381 counterfactual source correctly made `distinct_ts` / `sample_count_for_gate` the sample gate for classifying reject side-cells. Downstream consumers still had raw `n` checks in:

- `helper_scripts/research/cost_gate_learning_lane/policy.py`
- `helper_scripts/research/cost_gate_learning_lane/historical_review.py`

That meant an artifact with `n=500` but only a few independent timestamps could be excluded upstream yet still look sample-qualified in bounded plan or historical review paths.

## Changes

- Added effective sample helpers to policy and historical review:
  - prefer `sample_count_for_gate`
  - then `distinct_ts`
  - then raw `n` as compatibility fallback
- Applied effective sample to sample gates, sample-score ranking, and tie-breaking.
- Preserved raw rows and effective sample fields in compact outputs:
  - `n`
  - `sample_count_for_gate`
  - `distinct_ts`
  - `rows_per_distinct_ts`
  - `timespan_minutes`
- Updated decision-packet Markdown to display `sample_n` and raw rows separately.
- Added regression: `n=500` / `sample_count_for_gate=3` / high priority score does not enter bounded demo plan or historical review.

## Verification

- `python3 -m py_compile helper_scripts/research/cost_gate_learning_lane/policy.py helper_scripts/research/cost_gate_learning_lane/historical_review.py helper_scripts/research/cost_gate_learning_lane/decision_packet.py helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_policy.py -q` = `65 passed`
- `python3 -m pytest helper_scripts/research/tests/test_cost_gate_learning_lane_decision_packet.py helper_scripts/research/tests/test_alpha_discovery_throughput.py -q` = `53 passed`

## Boundary

No runtime source sync, cron install, env edit, deploy/rebuild/restart, PG write/schema migration, Bybit private/signed/trading call, credential/auth/risk/order/strategy mutation, writer enablement, Cost Gate lowering, order/probe authority, or promotion proof is granted by this source checkpoint.

After the operator's later runtime source-sync authorization, sync should target the pushed commit that contains this checkpoint; true apply still must not include deploy/rebuild/restart or cron/env activation unless separately authorized.

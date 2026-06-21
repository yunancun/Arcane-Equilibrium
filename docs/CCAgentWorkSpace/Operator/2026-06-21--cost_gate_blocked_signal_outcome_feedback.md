# Cost-Gate Blocked-Signal Outcome Feedback

## Status

Implemented source-only support for counterfactual outcomes on recorded cost-gate rejects.

No deploy, restart, DB write, or Bybit call was performed.

## What Changed

- `runtime_adapter.py` now supports `--record-blocked-outcomes`.
- It creates `blocked_signal_outcome` rows for recorded rejects where `allowed_to_submit_order=false`.
- These rows use local price observations to compute side-aware markout net bps.
- Alpha-discovery now summarizes the probe ledger and shows whether it is missing, empty, admission-only, or has blocked-signal outcomes.

## Important Boundary

`blocked_signal_outcome` is not a trade result.

- It is not `probe_outcome`.
- It does not feed probe auto-disable.
- It does not grant order authority.
- It does not lower the main cost gate.
- It remains `promotion_evidence=false`.

## Verification

- Cost-gate learning lane tests: 15 passed.
- Alpha-discovery focused tests: 34 passed.
- Python compile: passed.
- `git diff --check`: passed.

## Operator Next Step

After runtime writer deploy/enablement produces `probe_admission_decision` rows, run blocked-signal outcome recording against local price observations. Review whether `ORDER_AUTHORITY_NOT_GRANTED` rows were actually profitable before considering any demo probe authority.

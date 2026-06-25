# PM Report: False-Negative Preflight Construction Bridge

Date: 2026-06-25
Status: DONE_WITH_CONCERNS
Active blocker: `P0-BOUNDED-PROBE-FALSE-NEGATIVE-PREFLIGHT-CONSTRUCTION-BRIDGE-DEMO-ONLY`

## Decision

Closed the source-only bridge that lets the current top false-negative bounded preflight candidate enter the no-order construction preview gate.

The immediate profit target is `grid_trading|ETHUSDT|Buy`: latest evidence ranks it first with avg net `258.3905bps` after cost and 7/7 net-positive blocked outcomes. That is not profit proof. It is now eligible for the same construction checks as the older AVAX reroute path.

## Source Change

- `bounded_probe_candidate_construction_preview.py` now accepts exactly one candidate source:
  - legacy `--reroute-review-json`, or
  - new `--bounded-probe-preflight-json`.
- The false-negative preflight source is accepted only with exact schema `cost_gate_false_negative_bounded_demo_probe_preflight_v1`, status `READY_FOR_OPERATOR_BOUNDED_DEMO_PROBE_AUTHORIZATION`, exact candidate identity match against the market snapshot including horizon, and explicit no-authority answers.
- Missing authority fields, string `"false"`, non-`NONE` Cost Gate adjustment, both sources, or no source fail closed.
- Truthy authority/mutation/proof contamination still returns `AUTHORITY_BOUNDARY_VIOLATION`.
- A stale wall-clock CLI fixture in lower-price reroute tests was repaired to use fresh timestamps.

## Reviews

- PA/E1: PASS with requirement to make false-negative preflight authority fields explicit, not just non-truthy. Fixed.
- E2: no fail-open implementation bug; requested full parametrized explicit-field coverage plus horizon mismatch. Fixed.
- E4: PASS; no reroute or adjacent caller regression.

## Verification

- `PYTHONPATH=helper_scripts/research python3 -m pytest -q ...` for construction/BBO/public-quote/plan-inclusion and false-negative/touchability/placement/authorization/reroute adjacent suites: `152 passed`.
- `python3 -m py_compile` for changed helper/tests: PASS.
- `git diff --check`: PASS.

## Boundary

Source/test/docs only. No runtime sync, no `/tmp/openclaw` runtime artifact refresh, no PG query/write, no Bybit call, no order/cancel/modify, no crontab/service/env mutation, no Cost Gate lowering, no probe/order/live authority, no Rust writer enablement, and no promotion proof.

## Next Safe Action

Generate or refresh a candidate-matched ETHUSDT Buy market snapshot and no-order construction preview, then proceed to candidate-matched touchability evidence. Do not treat non-candidate fills, unattributed fills, source patches, or construction preview readiness as profit proof.

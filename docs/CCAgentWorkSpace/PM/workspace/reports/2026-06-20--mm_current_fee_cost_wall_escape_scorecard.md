# MM Current-Fee Cost-Wall Escape Scorecard

Date: 2026-06-20

## Summary

MM is still the only immediate engineering-actionable alpha blocker, but the previous next trigger was too broad: "validate lower fee or new low-friction signal path" did not say how much edge is missing.

This checkpoint adds `mm_cost_wall_escape_v1` to the alpha-discovery MM blocker. It makes the no-profit diagnosis numeric: at the current maker fee, sample-gated gross edge must clear the 4.0bp round trip. The best observed sample-gated gross edge is 2.27bp, so the current gap is 1.73bp.

## Runtime Evidence

Linux read-only alpha-discovery smoke:

- Latest alpha SHA256: `7a9f0e5005b4906ecbb6db3e4775d2cb2769654f5eac3310b4bdb8438bcff6bb`
- Created: `2026-06-20T19:13:02.300670+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- `engineering_actionable_count`: 1
- Blocker counts: `cost_wall=1`, `data_coverage=2`, `event_wait=2`, `rejected_no_edge=1`, `robustness_wait=1`, `sample_gate=1`

MM blocker:

- blocker class: `cost_wall`
- primary blocker: `gross_edge_below_current_fee_no_current_fee_walk_forward_positive`
- escape status: `CURRENT_FEE_GROSS_EDGE_GAP_REQUIRES_NEW_LOW_FRICTION_SIGNAL`
- reason: `lower_fee_path_scale_or_capital_gated_at_current_account_state`
- required current-fee gross edge: 4.0bp
- best sample-gated gross edge: 2.27bp
- gross-edge gap to current fee: 1.73bp
- gross-edge multiple to clear current fee: 1.7621
- lower-fee path: `STANDARD_FEE_TIER_CLEARS_BUT_SCALE_OR_CAPITAL_GATED`
- next trigger: `search_new_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`

## Interpretation

This is not a signal and not promotion proof. It is a sharper rejection boundary for the current MM family.

The current family has measurable gross edge, but it is too small for current fees. Since the fee path requires VIP5-scale volume/capital and lower-fee stability is not yet distinct-date proven, the next engineering path is not more in-family threshold tweaking. A new MM signal family must show sample-gated gross edge at or above the current round-trip fee before it deserves deeper walk-forward and AEG work.

## Verification

- Mac: regression first failed on missing `cost_wall_escape_status`.
- Mac: `test_alpha_discovery_throughput.py` = 28 passed after the reducer fix.
- Mac: py_compile for `discovery_loop.py` and `runtime_runner.py` passed.
- Mac: `git diff --check` passed.
- Linux selective source sync: same focused suite = 28 passed.
- Linux py_compile passed.
- Linux read-only alpha-discovery cron smoke refreshed the evidence above.

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes only. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, no credential/auth/risk/order/trading mutation, and no live/demo strategy parameter change.

This is not promotion proof and not a trading signal.

## Next Trigger

Search for a low-friction MM signal whose sample-gated gross edge is at least the current fee round trip, then require walk-forward confirmation and AEG/QC/MIT review before any promotion path.

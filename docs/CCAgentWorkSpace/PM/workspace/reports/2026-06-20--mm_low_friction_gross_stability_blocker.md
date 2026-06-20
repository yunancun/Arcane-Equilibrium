# MM low-friction gross stability blocker

Date: 2026-06-20

## Decision

Add a fail-closed stability blocker for the current MM low-friction near miss. The best holdout gross edge is not enough: the same candidate must also confirm on the train half before it can be treated as a real low-friction signal candidate.

## Runtime evidence

- Alpha latest sha256: `d6e3a94c94919a564bc0d2667d3e8f229bc4a39e7c3c57cbc1efb6300990f5c2`
- `created_at_utc`: `2026-06-20T21:00:20.631087+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- MM escape schema: `mm_cost_wall_escape_v2`
- Low-friction stability status: `LOW_FRICTION_HOLDOUT_GROSS_NOT_TRAIN_CONFIRMED`
- Candidate: `quoted_half_spread_bps_train_p90_and_side_touch_size_delta_frac_30s_train_p90`
- Train gross: `-0.225bp`, n=74
- Holdout gross: `2.838bp`, n=81
- Holdout-minus-train gross: `3.063bp`

## Read

The 2.838bp holdout gross near miss is not a stable edge. It is below the 4.0bp current-fee round trip and the train half is negative. The correct next trigger is now `search_train_confirmed_low_friction_mm_signal_with_sample_gated_gross_edge_ge_current_fee_round_trip`.

## Verification

- Mac alpha focused: `31 passed`
- Linux alpha focused: `31 passed`
- `py_compile`: passed
- `git diff --check`: passed
- Linux recorder latest inspection and read-only alpha runtime smoke: passed

## Boundary

Artifact-only source/test/docs plus selective Linux source sync and `/tmp/openclaw` alpha artifact write. No PG write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, and no credential/auth/risk/order/strategy mutation. Not signal, execution, or promotion proof.

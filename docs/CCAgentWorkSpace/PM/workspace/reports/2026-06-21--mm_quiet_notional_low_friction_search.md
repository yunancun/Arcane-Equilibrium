# 2026-06-21 -- MM quiet-notional low-friction search

## Decision

The current no-profit blocker is still MM current-fee cost wall. The only engineering-actionable next trigger was to search for a train-confirmed low-friction MM signal whose sample-gated gross edge can clear the current 4.0bp maker round trip.

This pass added existing point-in-time `recent_trade_abs_qty_10s/30s` features to the fill_sim low-friction search. The new search surface covers:

- single-feature quiet-notional quantiles,
- high quoted spread x quiet-notional combos,
- high quoted spread x quiet-notional x favorable same-side touch/flow interactions, marked as `spread_quiet_abs_qty_interaction_v1`.

## Runtime Result

Linux forced 2h fill_sim refresh:

- fill_sim sha256: `a605ead7588d58fdca3554f27c2683394216c588e3af17af1f297e53705f7c2a`
- generated: `2026-06-21T09:29:47.989372+00:00`
- L1 rows post-filter: `1,073,504`
- trades rows: `787,734`
- symbols: `31`
- low-friction candidates: `284`
- interaction candidates: `172`
- train-confirmed status: `LOW_FRICTION_TRAIN_CONFIRMED_GROSS_BELOW_CURRENT_FEE`
- current-fee-confirmed train/holdout candidates: `0`

Best train-confirmed candidate remains below current fee:

- candidate: `quoted_half_spread_bps_train_p90_and_side_touch_size_delta_frac_30s_train_p75`
- min(train, holdout) gross: `1.521bp`
- gap to 4.0bp round trip: `2.479bp`

Best quiet-notional train-confirmed interaction also remains below current fee:

- candidate: `quoted_half_spread_bps_train_p90_and_recent_trade_abs_qty_30s_train_p25_and_side_touch_size_delta_frac_30s_train_p75`
- candidate shape: `spread_quiet_abs_qty_interaction_v1`
- min(train, holdout) gross: `1.234bp`
- gap to 4.0bp round trip: `2.766bp`

Latest MM verdict / alpha refresh:

- alpha sha256: `da105c37b2ba0c6565bfeebeb974a865df486685d4368d71ccedcac49c4030d4`
- created: `2026-06-21T09:36:11.433679+00:00`
- status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- best sample-gated gross cell: `2.647bp`, net `-1.353bp`, n=33
- break-even maker fee: `1.3235bp/side`
- blocker: holdout gross exists, but train leg is not sample-gated (`0.541bp`, n=28)

## PM Read

The implementation was worth doing because it closed a real search gap: quiet trade notional was already computed point-in-time but not used by the low-friction candidate generator.

It did not solve profitability. The strongest refreshed current-fee path is still L1-quiet/touch, not abs-qty, and it remains holdout-only. The correct next trigger is unchanged: find a train-confirmed sample-gated low-friction MM surface with gross edge >= 4.0bp, or move to a different alpha family with real execution evidence.

Polymarket should not be the active engineering target right now. Latest lead-lag moved past price catch-up into `IC_READY_NO_SIGNIFICANT_EDGE`, candidate_count `0`, joined rows `1701`, max overlap-adjusted points `46`.

## Verification

- Mac: `python3 -m pytest -q program_code/research/tests/test_fill_sim_cost_wall.py` -> `23 passed`
- Mac: `python3 -m pytest -q program_code/research/tests/test_fill_sim_history.py helper_scripts/research/tests/test_alpha_discovery_throughput.py` -> `41 passed`
- Mac: `python3 -m py_compile program_code/research/microstructure/fill_sim.py`
- Mac: `git diff --check`
- Linux: focused abs-qty regression -> `1 passed`
- Linux: full cost-wall suite -> `23 passed`
- Linux: artifact-only fill_sim refresh + recorder MM verdict + alpha discovery runtime smoke passed

## Boundary

Artifact-only research/source/test/docs change plus selective Linux source sync and `/tmp/openclaw` artifact/status writes. Existing wrappers used read-only PG. No PG table write or schema migration. No Bybit private/signed/trading call. No engine/API rebuild or restart. No credential, auth, risk, order, or strategy mutation. Not signal, execution proof, or promotion proof.

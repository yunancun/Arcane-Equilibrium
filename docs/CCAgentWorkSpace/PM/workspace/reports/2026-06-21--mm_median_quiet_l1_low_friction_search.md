# 2026-06-21 -- MM median quiet L1 low-friction search

## Decision

The prior MM low-friction search used p10/p25 quiet tape/L1 thresholds. This left a real search gap: median-quiet L1/tape regimes could be sample-rich enough to test, while p10/p25 were either too sparse or below the current-fee gross threshold.

This pass added train-only p50 thresholds for existing quiet tape/L1 columns and included them in high-spread x quiet-context combos plus three-way `spread_quiet_touch_interaction_v1` candidates.

## Runtime Result

Forced read-only Linux 2h fill_sim refresh:

- fill_sim sha256: `ec5f9de633142755fcc19ae272890c484c043b1d4e63d75374a94661006602ad`
- generated: `2026-06-21T09:48:54.081227+00:00`
- L1 rows post-filter: `1,086,395`
- trades rows: `786,875`
- symbols: `31`
- low-friction candidates: `394`
- interaction candidates: `266`
- status: `LOW_FRICTION_SIGNAL_TRAIN_ONLY_CURRENT_FEE`
- current-fee-confirmed train/holdout candidates: `0`

Best train-confirmed candidate:

- `quoted_half_spread_bps_train_p90_and_side_touch_size_delta_frac_30s_train_p90`
- train gross: `4.416bp`, n=69
- holdout gross: `2.269bp`, n=74
- min gross: `2.269bp`
- gap to 4.0bp maker round trip: `1.731bp`

p50 interaction examples are now visible, but remain sub-fee. The best observed p50 quiet examples have min gross near `1.260bp` / `1.136bp`, not current-fee promotion proof.

## PM Read

The median quiet-L1 branch was worth testing because it closes a real candidate-surface gap and the deterministic regression proves the branch can restore sample-gated train evidence.

It did not create a profitable MM edge. Runtime still fails holdout current-fee confirmation, and the same spread/quiet/touch family is now sufficiently explored for this evidence window. The next profitable path should not be more threshold expansion in this family; it should be a new signal/regime family, a fee path, or a non-MM candidate with formal evidence.

## Verification

- Mac median regression: `1 passed, 23 deselected`
- Mac full cost-wall suite: `24 passed`
- Mac fill_sim history + alpha discovery: `41 passed`
- Mac py_compile passed
- Linux median regression: `1 passed, 23 deselected`
- Linux full cost-wall suite: `24 passed`
- Linux read-only fill_sim refresh + recorder MM verdict + alpha runtime smoke passed

## Boundary

Source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact/status writes. Existing wrappers used read-only PG. No PG table write or schema migration. No Bybit private/signed/trading call. No engine/API rebuild or restart. No credential, auth, risk, order, or strategy mutation. Not signal, execution proof, or promotion proof.

# MM low-friction interaction search

Date: 2026-06-20

## Decision

Add a bounded interaction search to MM low-friction fill_sim: high quoted spread × quiet immediate tape/L1 context × favorable same-side touch/flow. This tests the next plausible escape from the current fee wall without opening unstructured combinatorial mining.

## Runtime evidence

- FillSim latest sha256: `d453ea298f1b2b427b6558d659fdcbeaf6f7db7e9fe40d52d2183a672b1e1518`
- FillSim generated: `2026-06-20T21:34:16.560106+00:00`
- L1 rows post-filter: `767419`
- Trades rows: `468167`
- Low-friction candidates evaluated: `224`
- Interaction candidates evaluated: `128`
- Train-confirmed positive-gross candidates: `71`
- Train-confirmed current-fee candidates: `0`
- Best train-confirmed interaction: `quoted_half_spread_bps_train_p90_and_recent_trade_count_30s_train_p25_and_side_recent_trade_imbalance_30s_train_p90`
- Best train gross: `1.871bp`, n=159
- Best holdout gross: `2.831bp`, n=91
- Best min(train, holdout) gross: `1.871bp`
- Gap to current 4.0bp fee round trip: `2.129bp`

## Alpha evidence

- Alpha latest sha256: `4902cbcbc6a0c8cbf19255553954a50a4b68ec176669c8df79cab85c4ccb1433`
- `created_at_utc`: `2026-06-20T21:40:15.253543+00:00`
- Global status: `NO_ACTIONABLE_ALPHA_RESEARCH_BLOCKED`
- MM blocker class: `cost_wall`
- MM primary blocker: `gross_edge_below_current_fee_no_current_fee_walk_forward_positive`
- Cost-wall escape status: `CURRENT_FEE_GROSS_EDGE_GAP_REQUIRES_NEW_LOW_FRICTION_SIGNAL`

## Read

The interaction surface moved the best train-confirmed low-friction gross edge from the prior 1.658bp baseline to 1.871bp, but it did not find a current-fee-clearing candidate. The best holdout gross near miss is `3.813bp` and still net negative by `0.187bp`; its train gross is only `1.857bp`.

Conclusion: this narrows the MM no-profit root cause. Simple spread × quiet × touch/flow interactions are not enough at the current 4.0bp round-trip fee. Short-term engineering should not keep blind-expanding the same surface; the next profitable path needs either materially different edge features/execution assumptions or actual lower-fee access.

## Verification

- Mac focused: `54 passed`
- Linux focused: `54 passed`
- `py_compile`: passed
- `git diff --check`: passed
- Selective Linux source sync: passed
- Linux read-only fill_sim refresh, MM verdict, and alpha runtime smoke: passed

## Boundary

Artifact-only source/test/docs plus selective Linux source sync and `/tmp/openclaw` artifact writes. Read-only PG SELECT via fill_sim/MM verdict wrappers. No PG table write/schema migration, no Bybit private/signed/trading call, no engine/API rebuild/restart, and no credential/auth/risk/order/strategy mutation. Not signal, execution, or promotion proof.

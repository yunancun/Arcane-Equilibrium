# BBO Freshness Refresh, Diagnosis, And Repair Proposal

## Session Loop State

- `active_blocker_id`: `P0-BOUNDED-PROBE-REROUTE-FRESH-BBO-CONSTRUCTION-REFRESH-DEMO-ONLY` -> `P0-BOUNDED-PROBE-BBO-FRESHNESS-DIAGNOSIS-DEMO-ONLY` -> `P0-BOUNDED-PROBE-BBO-FRESHNESS-REPAIR-PROPOSAL-DEMO-ONLY`
- `blocker_goal`: Refresh AVAX BBO evidence, diagnose freshness failures, and emit a no-authority repair proposal before any demo order admission.
- `profit_relevance`: AVAX is cap-feasible and historically high-edge, but stale BBO prevents live-applicable demo probe evidence. The fastest safe profit path is reducing freshness latency without changing risk gates or granting order authority.
- `operator_action_required`: false for these artifacts. Direct public quote capture remains proposal-only and requires PM->E3->BB before any exchange-facing call.
- `next_blocker_id`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-SOURCE-DESIGN-DEMO-ONLY`

## Anti-Repeat Decision

`PROCEED_WITH_READ_ONLY_EVIDENCE_DELTA`.

The previous AVAX construction preview was complete and stale-BBO blocked. This checkpoint created fresh-BBO-specific artifacts, then diagnosed the source of the blocker rather than rerunning the same stale preview indefinitely.

## Runtime Artifacts

Fresh-BBO market snapshot:

- `/tmp/openclaw/cost_gate_learning_lane/candidate_market_snapshot_avax_sell_fresh_bbo_latest.json`
- sha256 `0212b7452ad383b33b856d7ebe360d5ebacbca5be78af92f97ef5fd77d8f7e8d`
- read-only PG source
- snapshot BBO age `3152.877ms`
- best bid/ask `6.063 / 6.064`

Fresh-BBO construction preview:

- `/tmp/openclaw/cost_gate_learning_lane/bounded_probe_candidate_construction_preview_avax_sell_fresh_bbo_latest.json`
- sha256 `cf5acebf01ff4a4fe32cdbf9f3ca8fd396cd09599fa47f11fa4868f855b51cf6`
- status `CANDIDATE_CONSTRUCTION_BBO_STALE`
- blocking gates `["bbo_freshness"]`
- effective BBO age `4935.735ms`
- limit `6.064`
- rounded qty `1.6`
- rounded notional `9.7024 USDT`

BBO freshness diagnosis:

- `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_diagnosis_avax_sell_latest.json`
- sha256 `9b32d64fc1b6e3076fd32835c8b947ae31a038235008b0a7683ea5f5d4706e9e`
- status `BBO_FRESHNESS_DIAGNOSIS_TRANSIENT_STALE`
- latest AVAX lag `2088.428ms`
- AVAX 15m ticker gap p50 `900ms`
- sampled latest symbol lags: `0 <=1000ms`, `164 >1000ms`

Repair proposal:

- `/tmp/openclaw/cost_gate_learning_lane/bbo_freshness_repair_proposal_avax_sell_latest.json`
- sha256 `6a6149719db6f1454eddb1379cea2222b564984187e31080abcd5b6aa7487ca8`
- status `BBO_FRESHNESS_REPAIR_PROPOSAL_READY_NO_AUTHORITY`

## Proposal Result

Rank 1 recommendation:

- `co_located_read_only_pg_snapshot_preview_runner`
- Source-only design first.
- Query PG read-only and run construction preview in one process on trade-core.
- Do not admit orders unless effective BBO age is <= `1000ms`.

Rank 2 fallback:

- `direct_public_quote_capture_before_admission`
- Requires PM->E3->BB before any exchange-facing call.
- No private endpoint, no order endpoint, no auth/order mutation.

Rank 3 not recommended now:

- `freshness_gate_change_review`
- Do not change the `1000ms` gate without QC/risk review and fill/markout sensitivity evidence.

## Verification

- Runtime artifacts are JSON-readable and hashed.
- Local source tree remained clean before docs update.
- No source helper or trading logic changed in this checkpoint.

## Aggressive Profit Hypotheses

1. `co_located_pg_snapshot_preview`
   - `why_it_might_make_money`: removes local scp/helper delay and may catch AVAX within the 1000ms BBO freshness gate without changing risk settings.
   - `fastest_safe_test`: source-only runner that performs read-only PG snapshot and preview in one process.
   - `required_data`: latest AVAX ticker, instrument filters, reroute review, helper source hash, generated preview artifact.
   - `failure_condition`: effective BBO age remains > `1000ms` or requires runtime mutation beyond review boundary.
   - `authority_required`: none for source-only design; PM/E3 if runtime source sync or helper installation is needed.
   - `max_safe_next_action`: `P0-BOUNDED-PROBE-BBO-FRESHNESS-COLOCATED-RUNNER-SOURCE-DESIGN-DEMO-ONLY`.

2. `direct_public_quote_capture`
   - `why_it_might_make_money`: bypasses PG collector lag and better approximates live order placement conditions.
   - `fastest_safe_test`: E3/BB-reviewed public market-data capture only; no private/order endpoints.
   - `required_data`: quote response timestamp, request timestamp, instrument filters, construction preview hash.
   - `failure_condition`: cannot reconstruct quote timing or quote age still exceeds `1000ms`.
   - `authority_required`: PM->E3->BB before exchange-facing call.
   - `max_safe_next_action`: proposal remains inactive until reviewed.

3. `bbo_age_sensitivity_study`
   - `why_it_might_make_money`: identifies whether the 1000ms gate is economically justified by slippage/markout.
   - `fastest_safe_test`: research-only fill/markout by BBO-age buckets.
   - `required_data`: historical BBO lag, fills, fee/slippage, markout.
   - `failure_condition`: older BBO buckets degrade net PnL after fees/slippage.
   - `authority_required`: none for study; QC/risk required for any gate change.
   - `max_safe_next_action`: do not mutate gate.

## Status

`DONE_WITH_CONCERNS`.

The repair proposal is ready, but it does not authorize order admission. The next checkpoint is a source-only co-located runner design.

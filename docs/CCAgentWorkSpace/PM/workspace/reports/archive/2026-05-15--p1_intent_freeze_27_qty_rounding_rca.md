# P1-INTENT-FREEZE-27 RCA — Exchange Qty Rounding

**Date**: 2026-05-15  
**Owner chain**: PM -> local E1-equivalent implementation -> local E4 verification -> PM  
**Scope**: source/test fix only; no runtime deploy, no auth/config/risk mutation

## Boundary

This checkpoint does not authorize demo canary, paper promotion, Stage 1, or true-live work. It does not rebuild or restart `trade-core`.

Sub-agent roles were not dispatched in this Codex turn because the current app tool policy only permits spawned agents when the operator explicitly asks for delegation. PM kept the scope local and still preserved the E1/E4 separation in the work shape: implementation first, then targeted verification.

## Runtime Facts

Latest TODO v25 hard FAIL came from `[27] intents_counter_freeze` at `2026-05-15 15:47 UTC`: demo/live_demo had no recent `trading.intents` while approved risk verdicts and DCS rows continued.

Direct read-only runtime probes after the later engine restart showed `[27]` currently PASSing under fresh-restart grace:

```text
demo: stale=21.6m, 30min_n=15
live_demo: stale=94.8m, 30min_n=0 — engine restarted 18.4m ago
live: never produced an intent
```

The historical FAIL window was still reproducible from DB/log evidence. Approved BTCUSDT risk verdicts such as `vrd-demo-BTCUSDT-1778859000022` / `vrd-live_demo-BTCUSDT-1778859000022` had no matching `trading.intents` row. Compressed engine logs showed the matching hot-path warning:

```text
2026-05-15T15:30:00Z exchange order skipped: qty=0 after rounding symbol=BTCUSDT
```

Conclusion: this was not a whole `trading_writer` outage. The exchange branch wrote an Approved risk verdict before exchange precision rounding, then skipped order dispatch and intent persistence when `final_qty <= 0`.

## Source Fix

Changed `rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs`:

- Non-approved gate verdicts are still persisted immediately.
- Approved exchange verdicts are now persisted only after exchange precision rounding leaves `final_qty > 0`.
- If `final_qty <= 0`, the branch writes the explicit rejected qty=0 audit shape via the existing rejected-intent path:
  - `trading.intents` qty=0 audit row
  - `trading.risk_verdicts` `Rejected` verdict
  - decision-feature rejected label
  - reason `qty_zero: exchange_precision_rounding_to_zero ...`

This preserves fail-closed behavior: no order is dispatched when exchange precision rounds the quantity to zero.

## Verification

Passed:

```text
python3 -m pytest helper_scripts/db/test_f7_new_healthchecks.py -q
43 passed

rustfmt --check src/tick_pipeline/on_tick/step_4_5_dispatch.rs
PASS

cargo test -q -p openclaw_engine tick_pipeline::tests::dual_rail_dispatch
15 passed

cargo test -q -p openclaw_engine tick_pipeline::tests::fast_track_reduce
19 passed
```

`cargo fmt --check` at crate scope still reports broad pre-existing formatting drift outside the touched file; it was not applied to avoid unrelated churn.

## Remaining Gate

Runtime remains pending. Close `P1-INTENT-FREEZE-27` only after this source fix is deployed/rebuilt on `trade-core` and `[27]` passes outside fresh-restart grace. Current watchdog probe after the later restart showed demo alive and paper/live not alive, so runtime status should be rechecked before any deploy or canary-sensitive action.

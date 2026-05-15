# P1-INTENT-FREEZE-27 RCA — Exchange Qty Rounding

**Date**: 2026-05-15  
**Runtime authority**: none; source/test checkpoint only

## Verdict

`[27] intents_counter_freeze` was traced to a narrow audit-shape bug, not a whole `trading_writer` outage.

BTCUSDT approved risk verdicts were persisted before exchange precision rounding. When the final exchange quantity rounded to zero, the exchange branch skipped order dispatch and intent persistence, leaving an `Approved` verdict with no matching `trading.intents` row. `[27]` correctly flagged that shape as dangerous, but this specific branch was a fail-closed min-qty skip.

## Source Fix

`rust/openclaw_engine/src/tick_pipeline/on_tick/step_4_5_dispatch.rs` now:

- persists approved exchange verdicts only after `final_qty > 0`;
- records `final_qty <= 0` as a rejected qty=0 audit intent/verdict;
- emits a rejected decision-feature label with reason
  `qty_zero: exchange_precision_rounding_to_zero ...`;
- still dispatches no order when the exchange quantity rounds to zero.

## Verification

Passed:

```text
python3 -m pytest helper_scripts/db/test_f7_new_healthchecks.py -q
rustfmt --check src/tick_pipeline/on_tick/step_4_5_dispatch.rs
cargo test -q -p openclaw_engine tick_pipeline::tests::dual_rail_dispatch
cargo test -q -p openclaw_engine tick_pipeline::tests::fast_track_reduce
```

Runtime deploy/rebuild is still pending. Do not close `P1-INTENT-FREEZE-27` until `[27]` passes on `trade-core` outside fresh-restart grace.

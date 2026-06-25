# Operator Summary: Bounded Probe Cron Expected-Head Sync

Date: 2026-06-25
Status: DONE_WITH_CONCERNS

## What Changed

Linux source checkout and learning cron expected-head pins now both point to `d2971aa5`.

## Current Result

- Linux checkout is clean at `d2971aa5`.
- Crontab remains 70 lines.
- Old expected-head `bdc1e156` count is `0`; new `d2971aa5` count is `11`.
- `OPENCLAW_COST_GATE_LEARNING_RECORD_PROBE_OUTCOMES=0` remains present; `=1` is absent.
- No mainnet, adapter, writer, probe, or order authority was enabled.
- Engine was not rebuilt or restarted.

## Boundary

No Bybit call, no PG write, no order/cancel/modify, no service restart, no Cost Gate lowering, no live/mainnet, no Rust writer/adapter enablement, no probe/order authority, and no promotion proof.

## Next Safe Action

No-order artifact refresh review, then post-restart bounded-probe reconciliation proof before adapter enablement or Demo order action.

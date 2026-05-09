# Post-Rebuild BILLUSDT Grid Negative Cell Guard

Date: 2026-05-09
Role: PM/E1 local execution
Scope: W-AUDIT-6 / edge healthcheck follow-up

## Trigger

After syncing and rebuilding the MA R:R checkpoint, passive healthcheck returned `SUMMARY: FAIL` with one hard FAIL:

- `[40] realized_edge_acceptance`
- active negative cell: `grid_trading/BILLUSDT`
- 24h sample: `n=11`, `avg=-49.67bps`

The rebuild itself succeeded and engine/API were alive. This was an edge healthcheck failure, not a process failure.

## Change

`BILLUSDT` was added to `grid_trading.blocked_symbols` in:

- `settings/strategy_params_paper.toml`
- `settings/strategy_params_demo.toml`
- `settings/strategy_params_live.toml`

This blocks new grid entries only. Existing positions can still close/reduce normally.

## Verification

- Strategy params Rust test now asserts all paper/demo/live configs keep `BILLUSDT` in `grid_trading.blocked_symbols`.
- Follow-up rebuild/restart is required to load the blocklist.

## Runtime Note

The `[40]` 24h rolling window may remain FAIL until historical BILLUSDT rows age out; this checkpoint prevents fresh grid entries from extending the negative cell.

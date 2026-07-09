# Dust Residual Prevention — Operator Brief (2026-04-30)

## What Happened

- Demo `APEUSDT` is a true below-minNotional residue: `size=0.1`, notional about `0.016 USDT`, while Bybit minimum notional is `5 USDT`.
- It appeared as no visible strategy because the local dust reaper could remove the paper-state row while the exchange REST position still existed.
- PnL looked like `0` because the GUI rounded sub-cent PnL to two decimals.

## Fix

- Full closes in Demo/Live exchange pipelines now dispatch Bybit's full-position close form: `qty=0 + reduceOnly=true + closeOnTrigger=true`.
- Normal `qty=0` orders are still rejected unless they are exactly that reduce-only full-close form.
- Fast-track half-reduce now skips a partial reduce when the rounded leftover would become below-minNotional dust.
- `orphan_frozen` / `DUST_FROZEN` positions are no longer evicted from paper state, so known exchange dust remains visible and explainable.
- Demo API/GUI labels REST-only below-minNotional rows as `orphan_frozen` and shows tiny nonzero PnL with four decimals.

## Verification

- Rust full library suite: `2381 passed / 0 failed`.
- Rust targeted tests covered full-close `qty=0`, partial-reduce dust prevention, order validation, and dust-frozen preservation.
- Python owner-strategy enrichment tests: `34 passed`.
- `cargo check --workspace` passed.
- `git diff --check` passed.

## Runtime Note

- Linux is to be fast-forward synced only.
- No Linux rebuild/restart is part of this checkpoint.
- Therefore the running Linux services will not load the new Rust/API behavior until the next approved rebuild/restart.

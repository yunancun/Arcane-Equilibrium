# Dust Residual Prevention Engineering Log — 2026-04-30

## Scope

- Task: diagnose why Demo/Live sometimes show positions with no visible strategy and long-lived near-zero PnL, using current Demo `APEUSDT` as the concrete case.
- Goal: reduce future exchange-side dust residue, keep unavoidable dust visible/attributed, and avoid hiding it from the GUI.
- Workflow used in-session: `PM -> PA/E1(local implementation) -> E2(local review) -> E4(local verification) -> QA/PM sign-off`.
- Runtime boundary: Linux sync is allowed, but Linux rebuild/restart is explicitly out of scope for this checkpoint.

## Root Cause

- Fact: current Demo `APEUSDT` exchange REST position was `Sell size=0.1`, about `0.016 USDT` notional, while Bybit instrument rules had `qtyStep=0.1`, `minOrderQty=0.1`, and `minNotionalValue=5`.
- Fact: this is below Bybit's minimum notional, so a normal explicit reduce-only close for that remaining step can be rejected or become operationally unclosable through the local sizing path.
- Inference: these residues are mainly created when full-close or partial-reduce logic relies on locally rounded explicit quantities and exchange execution leaves one lot step behind.
- Fact: boot/status dust reaper previously evicted dust-sized positions from `paper_state`. If the exchange still had the residue, the GUI saw a REST-only position without an owner strategy, so it looked like `--` strategy and PnL `0`.
- Fact: PnL was not always truly zero; sub-cent PnL was rounded to two decimals in the Demo table.

## Changes Implemented

1. Primary exchange full closes now use Bybit's full-position close form: `qty=0`, `reduceOnly=true`, `closeOnTrigger=true`.
   - Added `TickPipeline::close_dispatch_qty_for_full_close()`.
   - Applied to strategy/risk full close dispatch, `ipc_close_all`, and `ipc_close_symbol`.
   - Paper and shadow paths still keep explicit quantities.

2. Normal zero-quantity orders remain invalid.
   - `event_consumer::dispatch` only permits `qty=0` when the request is a close.
   - `OrderManager::validate_and_round()` only bypasses normal qty/min-notional validation for `qty=0 + reduceOnly + closeOnTrigger`.
   - All other order paths continue through existing minQty/minNotional validation.

3. Fast-track partial reduce now avoids creating below-minNotional residues.
   - Added `TickPipeline::partial_reduce_dust_residual()`.
   - `risk_close:fast_track_reduce_half` checks instrument step/minNotional before reducing.
   - If the rounded partial reduce would leave a dust residual, the partial reduce is skipped instead of manufacturing an untradeable remainder.

4. Known dust-frozen positions are preserved instead of hidden.
   - `PaperState::evict_if_dust()` and `evict_all_dust()` no longer evict `DUST_FROZEN_STRATEGY` (`orphan_frozen`) positions.
   - This keeps exchange residues explainable in state/API/GUI rather than making them REST-only ghosts.

5. GUI/API explain unavoidable REST-only dust.
   - Demo backend enriches REST-only below-minNotional rows as `owner_strategy=orphan_frozen`, `frozen_reason=dust_below_min_notional`, with `min_notional` and `est_notional`.
   - Demo table displays sub-cent nonzero PnL with four decimals, so tiny PnL is not shown as false zero.

## Verification

- `python3 -m pytest program_code/exchange_connectors/bybit_connector/control_api_v1/tests/test_owner_strategy_enrichment.py -q`
  - Result: `34 passed` with existing Pydantic deprecation warnings.
- `cargo test -p openclaw_engine --lib test_primary_exchange_full_close_dispatches_qty_zero`
  - Result: passed.
- `cargo test -p openclaw_engine --lib test_partial_reduce_dust_residual_blocks_below_min_notional_leftover`
  - Result: passed.
- `cargo test -p openclaw_engine --lib test_validate_and_round_allows_qty_zero_reduce_only_close_on_trigger`
  - Result: passed.
- `cargo test -p openclaw_engine --lib evict_on_dust_preserves_dust_frozen_owner`
  - Result: passed.
- `cargo test -p openclaw_engine --lib`
  - Result: `2381 passed / 0 failed`, existing warnings only.
- `cargo check --workspace`
  - Result: passed, existing warnings only.
- `git diff --check`
  - Result: passed.

## Deploy / Sync Notes

- This checkpoint is safe to sync to Git and Linux by fast-forward only.
- Per operator instruction, Linux must not run `restart_all.sh`, rebuild, or restart services in this checkpoint.
- Runtime implication: after Linux fast-forward, source files on disk contain the fix, but the running engine/API process will keep old loaded code until the next approved rebuild/restart.

## Residual Risk

- The Bybit `qty=0 + reduceOnly + closeOnTrigger` path should be observed on Demo first after the next rebuild.
- It prevents full-close dust caused by stale/rounded explicit local size, but cannot retroactively remove already existing below-minNotional exchange residues.
- Existing dust residues should remain visible as `orphan_frozen` until manually or exchange-mechanically resolved.

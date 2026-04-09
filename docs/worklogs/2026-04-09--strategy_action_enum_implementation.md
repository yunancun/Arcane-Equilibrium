# StrategyAction Enum — First-Class Close/Exit for Strategies

**Date**: 2026-04-09
**Commits**: `fc51439` (initial impl) + QC/FA follow-up commit (pending)
**Test baseline**: 769 → 830 passed, 0 failed

---

## Problem

Engine deadlocked 20+ hours: 3 positions opened in first 4 minutes, then zero trades. Root causes:
1. Strategy exit intents sent as opposite-direction `OrderIntent` → Guardian rejected as `direction_conflict`
2. New opens on BTC/ETH blocked by `cost_gate` ATR cold-start
3. StopManager (only working close path) hasn't triggered — 5% hard SL, volatility insufficient

Result: complete trading paralysis. Positions can't close, new positions can't open.

## Solution: StrategyAction Enum

Replaced `Vec<OrderIntent>` return type with `Vec<StrategyAction>`:

```rust
pub enum StrategyAction {
    Open(OrderIntent),        // full governance pipeline
    Close { symbol, confidence, reason },  // lightweight path, bypasses governance
}
```

Close bypasses Guardian/cost_gate/Kelly/P1 (risk-reducing, not risk-increasing), while retaining: fee accounting, Kelly stats, shadow orders, audit trail (recent_fills + recent_intents).

---

## Completed Work

### Phase 1: Core Implementation (`fc51439`)

| File | Change |
|------|--------|
| `strategies/mod.rs` | `StrategyAction` enum + `on_external_close` trait method |
| `strategies/ma_crossover.rs` | Exit → `Close(ma_reverse_cross)`, entry → `Open` |
| `strategies/bb_reversion.rs` | Exit → `Close(bb_mean_revert)`, entry → `Open` |
| `strategies/bb_breakout.rs` | 4 exits → `Close(trailing_stop/regime_shift/pctb_revert/bw_squeeze)` |
| `strategies/grid_trading.rs` | Inventory-aware `Open`/`Close` via `net_inventory` sign |
| `strategies/funding_arb.rs` | Return type change (still returns `vec![]`) |
| `orchestrator.rs` | `dispatch_tick` return type → `Vec<StrategyAction>` |
| `tick_pipeline.rs` | Deferred close execution: paper + exchange mode paths |

**Deferred execution pattern**: Close actions collected in `pending_strategy_closes: Vec<(String, String)>` inside strategy loop, executed after loop ends — required by Rust borrow checker (`strategies_mut()` borrows `self` exclusively).

### Phase 2: QC/FA Review Fixes

Parallel QC (risk) + FA (functional) review identified 1 P1 + 3 P2 findings. All fixed:

| # | Severity | Finding | Fix |
|---|----------|---------|-----|
| 1 | **P1** | Grid `net_inventory` drift on skipped close — grid adjusted inventory eagerly, but if pipeline skips close (no position), inventory is wrong | Added `on_close_confirmed` / `on_close_skipped` trait callbacks; grid defers inventory adjustment to `on_close_confirmed`, rolls back cross state on `on_close_skipped` |
| 2 | P2 | Exchange-mode Kelly stats gap — `apply_exchange_fill` never called `record_trade` | Added `record_trade` for non-zero `realized_pnl` in `apply_exchange_fill` |
| 3 | P2 | `funding_arb` missing `on_external_close` — could desync if position state tracked | Added override: `position = None` |
| 4 | P2 | Pipeline integration test missing (spec called for it) | Added `test_strategy_close_action_closes_position` + `test_strategy_close_no_position_is_noop` |

**Bonus fix**: Scanner `remove_symbol` compile error — `last_persisted_signal` uses `(String, String)` key, `remove(symbol)` type mismatch → changed to `retain`.

### Phase 2 P1 Fix Detail: Grid Deferred Inventory

New trait methods in `strategies/mod.rs`:
- `on_close_confirmed(&mut self, symbol: &str)` — pipeline calls after successful close
- `on_close_skipped(&mut self, symbol: &str)` — pipeline calls when close was no-op

Grid implementation:
- `on_close_confirmed`: adjusts `net_inventory` based on `prev_inventory` sign (direction)
- `on_close_skipped`: rolls back `last_cross_idx` and `last_trade_ms` to prev snapshot
- `on_tick`: only adjusts `net_inventory` for `Open` actions, NOT for `Close` (deferred)

Pipeline wiring: after deferred close loop, calls `on_close_confirmed` / `on_close_skipped` on all strategies for each symbol.

---

## Test Coverage Added

| Strategy | Test | Assertion |
|----------|------|-----------|
| ma_crossover | `test_exit_on_reverse` | `Close { reason: "ma_reverse_cross" }` |
| bb_reversion | `test_exit_mean` | `Close { reason: "bb_mean_revert" }` |
| bb_breakout | `test_atr_trailing_stop_long_exit` | `Close { reason: "trailing_stop", confidence: 0.7 }` |
| bb_breakout | `test_atr_trailing_stop_short_exit` | `Close { reason: "trailing_stop" }` |
| bb_breakout | `test_regime_exit` | `Close { reason: "regime_shift", confidence: 0.6 }` |
| bb_breakout | `test_pctb_revert_exit` | `Close { reason: "pctb_revert", confidence: 0.55 }` |
| bb_breakout | `test_bw_squeeze_exit` | `Close { reason: "bw_squeeze", confidence: 0.45 }` |
| grid_trading | `test_grid_close_on_inventory_reduction` | `Close { reason: "grid_close_long" }` + deferred confirm |
| grid_trading | `test_grid_close_skipped_rolls_back` | `on_close_skipped` rolls back cross state |
| tick_pipeline | `test_strategy_close_action_closes_position` | Open → Close → position gone + pnl positive |
| tick_pipeline | `test_strategy_close_no_position_is_noop` | Close on empty = None, safe no-op |

---

## Decisions & Rationale

1. **No `Reverse` variant**: No strategy currently reverses. Reverse = `[Close, Open]` in same tick. Add when needed.
2. **No `is_long`/`qty` on Close**: Pipeline looks up from `paper_state` — strategy's qty belief unreliable after Kelly/P1 sizing.
3. **Deferred execution**: Borrow checker requires it. Same pattern as existing Step 6 risk checks.
4. **`on_close_confirmed` vs adjusting in strategy**: Grid's OU model is stateful (net_inventory drives Open/Close classification). Must be accurate. Other strategies are simpler (position = Some/None).

## Gates Bypassed by Close (by design)

- Guardian `direction_conflict` — **this was THE root cause bug**
- `cost_gate` — close doesn't need positive edge estimate
- Kelly sizing — close qty = full position, not Kelly-rescaled
- P1 hard cap — limits new risk, not exits
- Gate 1.5 (duplicate position) — N/A for close

## What Close Retains

- Fee accounting (`emit_close_fill`)
- Shadow order (mirror to Demo API)
- Kelly stats (`record_trade`) for future sizing
- Audit trail (`recent_fills` + `recent_intents` ring buffers)
- Consecutive loss tracking (risk evaluator)

---

## QC Safety Verification (all P0 safe)

- **Halt guard**: `paper_paused` gate returns before strategy dispatch — Close cannot execute during halt
- **Over-close protection**: qty from `paper_state.get_position()`, not strategy-supplied
- **Race (stop vs close)**: `close_position` returns None if already gone — safe no-op
- **Path separation**: `match` is exhaustive, Open/Close paths never cross

---

## Next Steps

- Engine rebuild + redeploy to pick up StrategyAction changes
- Monitor for: Close fills appearing, `fills` counter incrementing past frozen 7, new positions opening after closes free slots
- 7d observation period continues in parallel

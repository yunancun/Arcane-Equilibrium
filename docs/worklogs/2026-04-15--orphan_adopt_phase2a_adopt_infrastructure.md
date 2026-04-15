---
title: ORPHAN-ADOPT-1 Phase 2A — deterministic adopt infrastructure
date: 2026-04-15
phase: ORPHAN-ADOPT-1 Phase 2A
status: implemented (merged pending)
---

# Context

Phase 1 (merged 2026-04-14) plus FUP side-car mirror (merged 2026-04-15) solved the
"detect-but-do-nothing orphan" and "engine self-kill" bugs, but left every genuinely
foreign exchange-origin orphan on a `close-everything` degrade path (Stage C
`SoftConservative`). Phase 2 was deferred pending:

1. A `strategy_id` identity for `PaperPosition` rows.
2. An AI Strategist (G-1 R-02, scheduled W22–W23) for "would a strategy want this
   position?" semantics.
3. PaperState injection + StopManager binding for an adopted position.

Phase 2A is the **non-agentic** sub-option: use the existing `edge_estimates` table
as an objective, deterministic proxy for "a strategy would have taken this symbol."
The rule is: **if any `KNOWN_STRATEGY` has positive shrunk edge on the orphan's
symbol, adopt it.** Edge sign is a per-symbol metric, NOT a directional signal;
the exchange-reported side is preserved and StopManager bounds downside.

This unblocks the adopt path today without waiting on G-1 R-02, and leaves a clean
integration point for the Strategist agent to later layer "same-direction signal"
semantics on top.

# Changes

## 1. Schema — `PaperPosition.owner_strategy`

Added a required `owner_strategy: String` field to `PaperPosition`. Without this,
there was no way to distinguish a `ma_crossover` position from an adopted orphan
from a Bybit cold-restart import.

- Strategy-driven fills write `intent.strategy` (e.g. `"ma_crossover"`).
- `import_positions` + `upsert_position_from_exchange` insert branches write
  `"bybit_sync"` (represents "this row originated from an exchange reconcile, not
  a tracked strategy intent").
- `adopt_orphan` writes `ORPHAN_ADOPTED_STRATEGY = "orphan_adopted"`.
- `upsert_position_from_exchange` update branch **preserves** existing
  `owner_strategy` — so a ma_crossover position that receives a WS size/avg_price
  update does not get rewritten to `"bybit_sync"`.
- `apply_fill` gained a 7th positional `owner_strategy: &str` argument. Same-
  direction accumulate is **first-write-wins** (preserve original owner).
- `#[serde(default)]` on the new field so pre-Phase-2A snapshot files load cleanly.

File: `rust/openclaw_engine/src/paper_state.rs` (+ 29 test-call-site updates in
`tick_pipeline/tests.rs`, `stress_integration.rs`, `tick_pipeline/commands.rs`,
`on_tick.rs`, `ipc_server/tests.rs`).

## 2. Orphan decision — Stage B2 adopt rule

Added `OrphanStage::AdoptPositiveEdge` and changed `OrphanDecision::Adopt` shape
to `{ reason, stage, triggering_strategy }`. Inside `handle_orphan()` the B1/B2
branch is now:

1. If ANY known strategy has `shrunk_bps > 0` on `pos.symbol` → **B2: Adopt**,
   record the first-found (per `KNOWN_STRATEGY_NAMES` order) as
   `triggering_strategy` for downstream PnL attribution.
2. Else if `unrealised_pnl > 0` → **B1: SoftLockProfit close** (unchanged).
3. Else fall through to **Stage C: SoftConservative close** (原則 #6).

Stage A (liq distance / CB / notional cap / scanner universe) still strictly
precedes B — safety checks never defer to adopt.

File: `rust/openclaw_engine/src/position_reconciler/orphan_handler.rs`.

## 3. Injection path — `PaperState::adopt_orphan` + `PipelineCommand::AdoptOrphan`

Added `PaperState::adopt_orphan(symbol, is_long, qty, entry_price, ts_ms) -> bool`:
- Idempotent: same-direction position already present → no-op (`false`).
- Rejects invalid `qty <= 0` / non-finite / `entry_price <= 0`.
- Seeds `latest_prices` with `entry_price` so StopManager has an immediate tick.
- Calls `positions_insert` helper so the FUP side-car mirror auto-updates,
  preventing the next reconcile cycle from re-classifying as an orphan.
- Writes `owner_strategy = ORPHAN_ADOPTED_STRATEGY`.

Added fire-and-forget `PipelineCommand::AdoptOrphan { symbol, is_long, qty,
entry_price, ts_ms }` + handler arm in `event_consumer/handlers.rs` that calls
`pipeline.paper_state.adopt_orphan(...)` and force-writes a snapshot on insert.

Added `dispatch_orphan_adopt(decision, pos, cmd_tx)` sibling of
`dispatch_orphan_close`. Uses `pos.avg_price` (Bybit's per-position average cost)
as the adoption `entry_price` — StopManager bounds downside from this reference.
Both dispatchers reject the wrong decision variant with a warn log and
`return false` (no silent misroute).

Split the dispatch branching in `position_reconciler/mod.rs:635`:
```rust
let sent = match &decision {
    OrphanDecision::Close { .. } => dispatch_orphan_close(&decision, pos, cmd_tx),
    OrphanDecision::Adopt { .. } => dispatch_orphan_adopt(&decision, pos, cmd_tx),
};
```

## 4. Audit extension

`spawn_orphan_audit` V014 JSON payload now includes:
- `owner_strategy` — `"orphan_adopted"` for Adopt, `null` for Close.
- `triggering_strategy` — the positive-edge strategy name for Adopt, `null` for Close.

Downstream analytics can attribute adopted PnL back to the edge that authorised
the adoption without parsing `reason` text.

## 5. Test matrix (8 new tests)

`orphan_handler.rs` tests (5 new):
- `stage_b2_positive_edge_adopts_long` — Buy + ma_crossover positive edge → Adopt.
- `stage_b2_positive_edge_adopts_short` — Sell + bb_reversion positive edge → Adopt.
- `stage_b2_no_positive_edge_losing_falls_through` — no positive edge + losing →
  SoftConservative (strict `> 0` gate, not `>= 0`).
- `stage_b2_first_positive_edge_wins` — multiple positive edges → first by
  `KNOWN_STRATEGY_NAMES` order; deterministic selection.
- `stage_a_precedence_over_b2_adopt` — liq_close fires even when B2 would adopt.

`paper_state.rs` tests (3 new):
- `test_adopt_orphan_inserts_and_mirrors` — new position + `owner_strategy` +
  `latest_prices` + mirror sync.
- `test_adopt_orphan_idempotent_same_direction` — no-op + owner preserved.
- `test_adopt_orphan_rejects_invalid_inputs` — qty/entry guards.

Also updated the legacy `stage_b1_positive_edge_skips_lock_profit` test that
asserted the Phase 1 `SoftConservative` fall-through — under Phase 2A it is
renamed/reframed as `stage_b2_positive_edge_adopts_long`.

# Side-effects / pre-existing WIP

`PipelineCommand::DisableEdgePredictorAll` had an uncommitted WIP in the working
tree (Step 7e hardening — added `operator_token` + `reason` fields but the
handler was not updated). To unblock the build I added minimal handler
destructuring with a `FIXME(Step 7e)` pointer and a length-validated token check
(`len >= 32`). Full two-phase commit + audit writeback remains pending as Step 7e.

# Test results

```
cargo test --lib           → 1293 passed, 0 failed   (was 1285; +8)
cargo test --tests         →   35 passed, 0 failed   (e2e / stress_integration)
cargo test --lib -p core   →  372 passed, 0 failed
```

Total: **1700 passed, 0 failed** (vs prior baseline 1692).

# Follow-ups

- **Deploy**: `bash helper_scripts/restart_all.sh --rebuild` to land the new
  engine binary. Adopt path is inert until `edge_estimates.json` is populated
  AND a known-strategy row has `shrunk_bps > 0` on an orphaned symbol — so a
  deploy without live edge data defaults to Phase 1 close-only behavior.
- **Strategist agent (G-1 R-02, W22–W23)**: When the AI Strategist lands, the
  adopt rule can be upgraded from "positive shrunk edge" to "Strategist would
  have opened this position right now." `KNOWN_STRATEGY_NAMES` + `EdgeEstimates`
  probe becomes a fast-path short-circuit; Strategist `would_take(symbol, side)`
  becomes the slow-path final word.
- **Step 7e completion**: The `DisableEdgePredictorAll` handler needs the full
  two-phase commit (TOML fsync → ArcSwap → clear_all) and
  `observability.engine_events` audit row as originally spec'd.

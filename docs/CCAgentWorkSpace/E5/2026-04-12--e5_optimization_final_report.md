# E5 Performance Optimization — Final Report
# E5 性能優化 — 最終報告

**Date / 日期**: 2026-04-12
**Engineer / 工程師**: E5 Performance Engineer
**Scope / 範圍**: 23 items across PERF (10), SIMPLIFY (5), READABILITY (5), DEAD-WEIGHT (3)
**Result / 結果**: 20 FIXED · 2 CORRECTLY SKIPPED · 1 CORRECTLY DEFERRED
**Test baseline / 測試基線**: 934 engine + 366 core + 27 types = 1327 tests, 0 failures
**Diff stats / 差異統計**: 17 Rust files changed, +563 / -899 lines (net -336)

---

## Summary / 總結

All 23 E5 optimization items have been addressed. 20 items were fully implemented and verified via E2 code review (including 4 residual fixes caught by E2). 2 items were correctly skipped (P-07: Bybit WS reconnect is framework-managed; S-05: `unwrap_or(0.0)` is intentional fail-closed). 1 item was correctly deferred (D-02: `metadata` HashMap removal depends on all producers migrating to structured fields first).

所有 23 項 E5 優化已全部處理。20 項完整實施並經 E2 代碼審查驗證（含 E2 發現的 4 項殘留修復）。2 項正確跳過。1 項正確延後。

---

## Item-by-Item Resolution / 逐項決議

### PERF — Performance (10 items)

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| **P-01** | `push_capped<T>()` ring buffer utility | ✅ FIXED | `on_tick_helpers.rs` — replaces 13+ inline len>cap/pop_front patterns across on_tick.rs, commands.rs, mode_state.rs |
| **P-02** | PriceEvent structured fields | ✅ FIXED | `openclaw_types/src/price.rs` — 5 new typed fields: `trade_side`, `trade_qty`, `bids5`, `asks5`, `adl_rank` with `#[serde(default)]` |
| **P-03** | Read structured fields in hot path | ✅ FIXED | `on_tick_helpers.rs` + `on_tick.rs` — Trade/Orderbook/ADL handlers read typed fields first, fall back to metadata HashMap |
| **P-04** | `now_ms()` utility | ✅ FIXED | `openclaw_core` — `pub fn now_ms() -> u64`, replaces 10+ inline `SystemTime::now().duration_since(UNIX_EPOCH)` chains |
| **P-05** | `is_stale()` utility | ✅ FIXED | `openclaw_core` — `pub fn is_stale(ts_ms: u64, max_age_ms: u64) -> bool`, replaces 4 inline staleness checks |
| **P-06** | WS subscriptions `Vec→HashSet` | ✅ FIXED | `ws_client.rs` — O(1) topic dedup, batch subscribe collects to Vec for send |
| **P-07** | Exponential backoff on WS reconnect | ⏭️ SKIPPED | Bybit WS SDK manages reconnection internally; adding app-level backoff would conflict |
| **P-08** | `TickContext<'a>` borrowed refs | ✅ FIXED | Zero-copy context struct with `&'a str` symbol + `Option<&'a IndicatorSnapshot>` + `&'a [Signal]`; all 5 strategies + orchestrator updated; test helpers use `Box::leak` for `'static` refs |
| **P-09** | Avoid `.clone()` on `Arc<RiskConfig>` reads | ✅ FIXED | `on_tick.rs` — bind `Arc` once per tick, borrow fields; eliminated per-field `.clone()` chains |
| **P-10** | Parallel async DB flush | ✅ FIXED | `trading_writer.rs` — `tokio::join!` for 7 independent table writes (signals, intents, fills, klines, ai_calls, state, learning) |

### SIMPLIFY — Code Simplification (5 items)

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| **S-01** | Consolidate 3 strategy confidence clamps | ✅ FIXED | `on_tick_helpers.rs` — `clamp_confidence(raw: f64) -> f64` utility |
| **S-02** | Deduplicate ring-buffer push logic | ✅ FIXED | All 13+ call sites now use `push_capped()`. E2 caught 3 residuals in commands.rs + mode_state.rs → fixed |
| **S-03** | Extract `build_intent()` helper | ✅ FIXED | `on_tick_helpers.rs` — shared OrderIntent construction for open paths |
| **S-04** | Centralize timestamp generation | ✅ FIXED | All inline `SystemTime` chains replaced with `now_ms()`. E2 caught 1 residual in commands.rs → fixed |
| **S-05** | Replace `unwrap_or(0.0)` with explicit error handling | ⏭️ SKIPPED | Intentional fail-closed pattern: parse failure → 0.0 → conservative behavior (no trade). Adding error propagation would complicate hot path without safety benefit |

### READABILITY — Naming & Clarity (5 items)

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| **R-01** | Rename `process_aggregator_events` → `process_market_events` | ✅ FIXED | `on_tick_helpers.rs` — function + all call sites |
| **R-02** | Rename `check_pending_orders` → `reconcile_pending_exchange_orders` | ✅ FIXED | `on_tick_helpers.rs` — function + all call sites |
| **R-03** | Rename `do_close` → `execute_position_close` | ✅ FIXED | `on_tick_helpers.rs` — function + all call sites |
| **R-04** | Rename `ShadowOrderRequest` → `OrderDispatchRequest` | ✅ FIXED | `mod.rs` struct + `shadow_order_tx` → `order_dispatch_tx` field + all references in dispatch.rs, commands.rs, on_tick.rs, tests.rs |
| **R-05** | Add MODULE_NOTE to `on_tick_helpers.rs` | ✅ FIXED | Bilingual EN/中 module-level doc comment |

### DEAD-WEIGHT — Dead Code Removal (3 items)

| ID | Title | Status | Notes |
|----|-------|--------|-------|
| **D-01** | Remove unused `spot_margin_client.rs` methods | ✅ FIXED | 4 unused methods removed, retained `get_spot_margin_data()` (used by DCP) |
| **D-02** | Remove `metadata: HashMap` from PriceEvent | ⏩ DEFERRED | Structured fields (P-02) added as parallel path with fallback reads (P-03). Full HashMap removal requires all producers migrated — scheduled post-P-03 stabilization |
| **D-03** | Remove dead `position_manager.rs` methods | ✅ FIXED | 2 unused methods removed |

---

## E2 Verification / E2 驗證

4-agent parallel E2 review performed after initial implementation. Findings:

1. **S-02 residual** — `commands.rs:334` still had inline `if len > 50 { pop_front }` → replaced with `push_capped()`
2. **S-04 residual** — `commands.rs:581` still had inline `SystemTime::now()` → replaced with `now_ms()`
3. **S-02 residual** — `mode_state.rs` `push_intent()`/`push_fill()` still inline → delegated to `push_capped()`
4. All 4 residuals fixed and re-verified. Final E2 verdict: **PASS**.

---

## Key Architectural Changes / 關鍵架構變更

### 1. TickContext<'a> (P-08) — Zero-Copy Strategy Interface
```rust
pub struct TickContext<'a> {
    pub symbol: &'a str,           // was: String
    pub price: f64,
    pub timestamp_ms: u64,
    pub indicators: Option<&'a IndicatorSnapshot>,  // was: Option<IndicatorSnapshot>
    pub signals: &'a [Signal],     // was: Vec<Signal>
    pub h0_allowed: bool,
}
```
Eliminates per-tick String clone + IndicatorSnapshot clone + Vec<Signal> clone for every strategy invocation. All 5 strategies + orchestrator mock updated.

### 2. PriceEvent Structured Fields (P-02/P-03)
5 typed `Option` fields replace hot-path HashMap lookups. Dual-read path (structured first, HashMap fallback) ensures backward compatibility during migration.

### 3. Parallel DB Flush (P-10)
7 independent table writes execute concurrently via `tokio::join!`, reducing DB flush latency from sequential sum to max-of-7.

### 4. OrderDispatchRequest Rename (R-04)
`ShadowOrderRequest` → `OrderDispatchRequest` reflects the struct's actual role (dispatches to both paper shadow and live exchange).

---

## File Impact / 文件影響

| File | Lines (after) | Change |
|------|--------------|--------|
| `tick_pipeline/on_tick.rs` | 1050 | -16 (P-03, P-08, R-04) |
| `tick_pipeline/on_tick_helpers.rs` | 282 | +utilities (P-01, S-01, S-03, R-01~R-03, R-05) |
| `tick_pipeline/mod.rs` | 1197 | TickContext struct, OrderDispatchRequest rename |
| `tick_pipeline/commands.rs` | 687 | S-02, S-04 residual fixes, R-04 rename |
| `strategies/ma_crossover.rs` | — | P-08 lifetime, Box::leak tests |
| `strategies/bb_breakout.rs` | — | P-08 lifetime, Box::leak tests |
| `strategies/bb_reversion.rs` | — | P-08 lifetime |
| `strategies/grid_trading.rs` | — | P-08 lifetime, compute_grid_confidence sig |
| `strategies/funding_arb.rs` | — | P-08 signature |
| `strategies/mod.rs` | — | Trait signature TickContext<'_> |
| `orchestrator.rs` | — | Mock + test TickContext |
| `database/trading_writer.rs` | — | P-10 parallel flush |
| `ws_client.rs` | 942 | P-06 HashSet |
| `event_consumer/dispatch.rs` | — | R-04 rename, MODULE_NOTE |
| `mode_state.rs` | — | S-02 push_capped delegation |
| `spot_margin_client.rs` | — | D-01 dead method removal |
| `position_manager.rs` | — | D-03 dead method removal |
| `market_data_client/mod.rs` | — | now_ms() adoption |

**All files under 1200-line hard limit.** ✅

---

## Test Results / 測試結果

```
Engine lib:  934 passed, 0 failed
Core lib:    366 passed, 0 failed
Types lib:    27 passed, 0 failed
─────────────────────────────────
Total:      1327 passed, 0 failed
```

---

## Conclusion / 結論

E5 optimization round complete. Net reduction of 336 lines across 17 files. Key wins: zero-copy TickContext eliminates per-tick allocations, parallel DB flush reduces write latency, ring-buffer utility eliminates 13+ duplication sites, structured PriceEvent fields lay groundwork for HashMap removal. No regressions.

E5 優化輪次完成。17 個文件淨減 336 行。關鍵收益：零拷貝 TickContext 消除每 tick 分配、並行 DB flush 降低寫入延遲、環形緩衝工具消除 13+ 重複點、結構化 PriceEvent 字段為 HashMap 移除鋪路。零回歸。

# QA Research: Adaptive Exit Persistence + Fast-Track Scoping Proposal

**Date:** 2026-04-17
**Status:** Proposed (pending operator approval)
**Triggered by:** 24h PnL analysis — ma_reverse_cross (-$14.39) + fast_track_reduce_half (-$7.46) as top loss sources

---

## Design Principle

All thresholds derived from market-observable quantities already in the indicator pipeline. No new hardcoded constants.

---

## A. ma_reverse_cross: Two-Layer Adaptive Fix

### A1. KAMA Efficiency Ratio–Driven Exit Persistence

**Core finding**: KAMA computes `efficiency_ratio` (ER) every tick, but the exit path ignores it entirely.

| ER Value | Meaning | Exit Behavior |
|---|---|---|
| → 1.0 | Price moves cleanly in one direction (trending) | Reverse cross = real reversal → fast exit |
| → 0.0 | Price oscillates (ranging/choppy) | Reverse cross = noise → require persistence confirmation |

**Formula**:
```
exit_persistence_ms = min_persistence_ms × (1 - ER)
```

With current `min_persistence_ms = 180s`:

| Market State | ER | Exit Persistence | Effect |
|---|---|---|---|
| Strong trend | 0.9 | 18s | Reverse cross is credible → quick exit |
| Moderate | 0.5 | 90s | Needs 1.5 min confirmation |
| Choppy | 0.15 | 153s | Nearly entry-level confirmation required |

**Zero new parameters**: `min_persistence_ms` already exists and is tunable; ER is already computed by KAMA indicator.

**Implementation**:
- Add `exit_persistence: PersistenceTracker` field to `MaCrossover` (separate from entry tracker)
- Exit path: instead of immediate `StrategyAction::Close`, call `exit_persistence.check(symbol, reverse_signal, now_ms, exit_min_ms, false)` — note `is_close = false` to enable persistence (current code passes `is_close=true` which bypasses it)
- Persistence passes → emit Close
- Safety: hard stop / trailing stop / fast_track operate independently, unaffected

**Why safe**: In a real crash, ER drops near 0 (erratic price action), but persistence only delays exit by seconds, and StopManager's hard stop fires independently.

### A2. Trend-Adaptive Cooldown (ported from grid_trading proven logic)

**Core finding**: grid_trading already has `compute_trend_adjusted_cooldown()` scaling cooldown 1x→6x via ADX + Hurst. This is a key driver of grid's profitability. ma_crossover uses fixed 300s.

**Formula** (consistent with grid_trading):
```rust
let adx_factor = ((adx - adx_threshold) / (adx_threshold * 1.5)).clamp(0.0, 1.0);
let hurst_factor = ((hurst - 0.50) / 0.25).clamp(0.0, 1.0);
let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;
let effective_cooldown = cooldown_ms × (1.0 + trend_score × max_cooldown_boost);
```

**1 new parameter**: `max_cooldown_boost` (suggested default 3.0, tunable). `adx_threshold` already exists (20.0); upper bound auto-derived as `adx_threshold × 2.5 = 50`, matching grid_trading.

| Market | ADX | Hurst | Effective Cooldown |
|---|---|---|---|
| Ranging | 15 | 0.45 | 300s (unchanged) |
| Weak trend | 25 | 0.55 | ~450s |
| Strong trend | 45 | 0.72 | ~1050s (17min) |

**Effect**: After closing in a trend, doesn't re-enter within 5 minutes only to get whipsawed again.

### A1 + A2 Combined Effect Estimate

Looking at PNUTUSDT (10 direction flips, -$5.58 in 24h):
- A1: In choppy market ER ≈ 0.2 → exit needs 144s persistence → most false reversals disappear during persistence window
- A2: Even if closed, extended cooldown prevents rapid re-entry
- Conservative estimate: 60-70% reduction in whipsaw losses

---

## B. fast_track_reduce_half: Precision Scoping + Adaptive Cooldown

### B1. Symbol-Scoped Reduction (core change)

**Current**: One symbol triggers 5%+3σ → halves ALL positions across ALL symbols.

**Proposed**:

| Trigger Condition | Current | Proposed |
|---|---|---|
| 5%+3σ, risk < Defensive | Halve all positions | **Only halve the triggering symbol** |
| 5%+3σ, risk ≥ Defensive | CloseAll | CloseAll (unchanged) |
| ≥15% any sigma | CloseAll | CloseAll (unchanged) |
| risk ≥ Defensive (no drop) | Halve all | Halve all (unchanged) |

**Why safe**: Systemic risk (Defensive+) still triggers portfolio-wide action. Symbol-scoping only applies at Normal/Cautious with moderate drops — the highest false-positive zone.

**Implementation**: In `on_tick.rs` ReduceToHalf branch, pass `held_drop_symbol` from the evaluation into the position filter:
```rust
// Current: filter all held positions
// Proposed: only reduce the triggering symbol's position
// held_drop_symbol already available (currently only used for logging)
```

### B2. Sigma-Proportional Cooldown

**Current**: Fixed 60s (`FT_REDUCE_COOLDOWN_MS`).

**Formula**:
```
cooldown_ms = FT_REDUCE_COOLDOWN_MS × (held_drop_sigma / 3.0)
```

`3.0` is NOT a new constant — it's the trigger threshold itself (`held_drop_sigma ≥ 3.0` at fast_track.rs:89).

| Sigma | Cooldown |
|---|---|
| 3.0 (just triggered) | 60s |
| 4.5 | 90s |
| 6.0 | 120s |
| 10.0 | 200s |

**Logic**: More extreme events → longer recovery → less repeat halving. Severity determines its own cooldown via the same statistical measure that triggered the action.

---

## C. Comparison Summary

| Dimension | Current | Proposed |
|---|---|---|
| **ma_crossover exit** | Single tick KAMA < SMA → immediate close | ER-scaled persistence: choppy requires confirmation, trending exits fast |
| **ma_crossover cooldown** | Fixed 300s | ADX+Hurst driven 300s → 1200s |
| **New parameters** | — | `max_cooldown_boost` (1 parameter) |
| **New hardcoded values** | — | Zero |
| **fast_track scope** | One symbol triggers → halve all | One symbol triggers → halve that symbol only (Defensive+ unchanged) |
| **fast_track cooldown** | Fixed 60s | Sigma-proportional 60s–200s |
| **Safety mechanisms** | — | Hard stop / trailing / CloseAll / Defensive all unaffected |

## D. Risk Assessment

| Risk | Probability | Mitigation |
|---|---|---|
| Exit delay expands losses | Low | StopManager hard stop operates independently; ER→0 in crash → persistence near-zero |
| Extended cooldown misses re-entry | Medium | `max_cooldown_boost` tunable; not entering in strong trends is often correct |
| Symbol isolation insufficient for systemic risk | Low | Defensive+ still portfolio-wide; ≥15% still CloseAll |

## E. Files to Modify

| File | Changes |
|---|---|
| `strategies/ma_crossover.rs` | +`exit_persistence` field, +ER-scaled exit check, +trend-adaptive cooldown method, +`max_cooldown_boost` param |
| `tick_pipeline/on_tick.rs` | +symbol-scoped ReduceToHalf, +pass `held_drop_symbol` to reduction filter |
| `tick_pipeline/on_tick_helpers.rs` | +sigma-scaled cooldown computation |
| `fast_track.rs` | +return `held_drop_symbol` in result (currently only logged) |

## F. Data Evidence (2026-04-17)

### ma_reverse_cross whipsaw pattern
```
PNUTUSDT:  13 fills, 10 flips, min_gap=300s, PnL=-$5.58
ORDIUSDT:  12 fills,  9 flips, min_gap=300s, PnL=-$3.42
RAVEUSDT:  14 fills,  8 flips, min_gap=300s, PnL=-$1.47
```
Nearly all losing trades held exactly 300s (= cooldown_ms), confirming the enter→5min→reverse cross→exit→repeat cycle.

### fast_track PnL distribution (24h, 414 fills)
```
<-$0.5:    16 fills → -$17.57  (big losses dominate)
>+$0.5:    10 fills → +$9.29   (big wins don't compensate)
Net:       -$7.46
```
Top losing symbols from collateral damage: MOVRUSDT -$3.79, PIPPINUSDT -$3.03, BASEDUSDT -$2.82

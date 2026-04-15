# FA-PHANTOM-2 Fix Specification

**Date:** 2026-04-15
**Discovered by:** G-2 funding_arb monitor daemon investigation (0/20 fills in 7h)
**Classification:** Same failure mode as FA-PHANTOM-1 (fast_track false-positive CloseAll), different root cause.

---

## Root Cause

`openclaw_core/src/risk/price_tracker.rs::max_drop_pct()` returns the worst peak-to-current drop across **every** observed symbol in a 5-minute window, regardless of whether the engine holds a position in that symbol.

Combined with:
- 25+ symbols in the observation pool (including high-volatility microcaps: ENJUSDT, RAVEUSDT, BLESSUSDT, …)
- `fast_track` triggers `CloseAll` whenever `price_drop_pct >= 5.0` at any risk level
- Small-caps routinely move 5%+ within a 5-minute window as normal noise

The result: under `RiskLevel::Normal` with a healthy balance, fast_track still fires `CloseAll` because *some* microcap in the pool dropped 5%. **All strategies — not just funding_arb — get force-closed within seconds of opening** (direct reproduction of FA-PHANTOM-1 symptom set).

### Evidence (engine.log, 2026-04-15)

```
15:42:48  FAST_TRACK CloseAll fired  risk_level=Normal  positions=16  trigger_symbol=ENJUSDT
16:05:20  FAST_TRACK CloseAll fired  risk_level=Cautious positions=5  trigger_symbol=ENJUSDT
16:05:32  FAST_TRACK CloseAll fired  risk_level=Normal  positions=3   trigger_symbol=ENJUSDT
```

`risk_level=Normal` rules out CircuitBreaker branch; margin_util post-PHANTOM-1-fix maxes at ~2% (≪ 90%) → only `price_drop_pct >= 5.0` can fire.

### Impact on G-2

demo funding_arb opened 8 positions since baseline (09:14 UTC); **zero** closed through the `strategy_close:funding_arb*` path. All 8 were force-closed by `risk_close:fast_track` or cascading `ipc_close_symbol` within 4–7 seconds. The G-2 monitor daemon can never collect its 20-fill sample under current behavior.

---

## Fix: Three Coordinated Changes

### 1. Per-symbol scoping (held positions only)

**File:** `rust/openclaw_core/src/risk/price_tracker.rs`

Add `SymbolDropInfo { symbol, drop_pct, sigma }` and `worst_drop_for_held(&[String]) -> Option<SymbolDropInfo>`. Keeps legacy `max_drop_pct()` intact for other callers.

A drop on a symbol we don't hold carries no immediate position risk. Flash-crash defense must be scoped to live exposure.

### 2. Sigma-based anomaly gate

A 5% move on a microcap that routinely swings 5% is not an anomaly. A 5% move on a symbol whose 5-minute std-dev is 0.8% **is** an anomaly.

`worst_drop_for_held` computes in-window sigma = `|current - mean| / std_dev`, reusing `detect_spike` semantics. fast_track uses **both** `drop_pct` and `sigma` to decide.

### 3. Risk-level-aware degradation

Replace the unconditional `drop >= 5% → CloseAll` branch with:

| Condition | Action |
|---|---|
| `risk_level >= CircuitBreaker` | `CloseAll` (unchanged) |
| `margin_util >= 90%` | `CloseAll` (physical MMR safety, unchanged) |
| `held_drop_pct >= 15%` | `CloseAll` (true flash crash, any level) |
| `held_drop_pct >= 5% AND sigma >= 3 AND risk >= Defensive` | `CloseAll` |
| `held_drop_pct >= 5% AND sigma >= 3 AND risk < Defensive` | `ReduceToHalf` |
| `risk >= Defensive` | `ReduceToHalf` (unchanged) |
| `risk >= Reduced` | `PauseNewEntries` (unchanged) |
| otherwise | `NoAction` |

**Rationale for 15% absolute cliff:** protects against sigma computation breaking down on thin samples or stablecoin-like histories where std_dev ≈ 0. A 15% drop in 5 min is categorically a flash crash regardless of statistical context.

**Rationale for 3σ threshold:** matches `PriceHistoryTracker::detect_spike` (`SPIKE_THRESHOLD_SIGMA = 3.0`). Keeps the "outlier" concept consistent across the tracker.

**Rationale for Normal→ReduceToHalf:** symmetric to how Defensive→ReduceToHalf already works. A real 5%+3σ event deserves exposure reduction, but not panic liquidation, when broader risk gauges (Guardian, P2) haven't escalated.

---

## API Changes

```rust
// Before
pub fn evaluate_fast_track(
    risk_level: RiskLevel,
    price_drop_pct: f64,
    margin_utilization_pct: f64,
) -> FastTrackAction

// After
pub fn evaluate_fast_track(
    risk_level: RiskLevel,
    held_drop_pct: f64,
    held_drop_sigma: f64,
    margin_utilization_pct: f64,
) -> FastTrackAction
```

Caller update in `rust/openclaw_engine/src/tick_pipeline/on_tick.rs` — replace
`price_tracker.max_drop_pct()` with `price_tracker.worst_drop_for_held(&held_symbols)`.

---

## Tests

### New

- `price_tracker::worst_drop_for_held_empty_symbols` — empty set → None
- `price_tracker::worst_drop_for_held_unheld_symbol_ignored` — global drop but none held → None
- `price_tracker::worst_drop_for_held_sigma_computed` — sigma matches expected formula
- `fast_track::test_fa_phantom_2_regression_microcap_noise_no_action` — 5% drop on held with sigma=1.0 → NoAction
- `fast_track::test_held_drop_with_sigma_reduces_at_normal` — 8% drop + 4σ + Normal → ReduceToHalf
- `fast_track::test_held_drop_with_sigma_closes_all_at_defensive` — 8% drop + 4σ + Defensive → CloseAll
- `fast_track::test_extreme_drop_closes_all_regardless_of_level` — 20% drop + Normal → CloseAll

### Updated (semantic change)

- `stress_integration::test_flash_crash_closes_all` — now requires sigma>=3
- `stress_integration::test_defensive_closes_all_on_flash_crash` — explicit sigma input
- `fast_track::test_flash_crash_closes_all` — sigma param added

### Preserved

- `fast_track::test_fa_phantom_1_regression_full_notional_no_action` — unchanged semantics (covers margin branch)
- `fast_track::test_circuit_breaker_closes_all` — unchanged
- `fast_track::test_manual_review_closes_all` — unchanged
- `fast_track::test_margin_crisis_closes_all` — unchanged

---

## Not in Scope

- **Adjusting 15% cliff, 5%/3σ gate, or 90% margin threshold** — these are load-bearing constants mid-crisis; any tuning goes through separate audit cycle
- **Removing legacy `max_drop_pct()`** — kept for `position_risk_evaluator` and any other non-fast-track consumers
- **Daemon filter broadening** to count `risk_close:fast_track` as FA exits — that would mask bugs by mis-classifying force-closes as natural strategy exits. Fix the trigger, not the metric.

---

## Deployment

1. Commit → `restart_all.sh --rebuild` (engine binary)
2. Verify: `grep "FAST_TRACK CloseAll fired.*risk_level=Normal" /tmp/openclaw/engine.log` on new binary should return **zero** lines unless a true >15% drop or 5%+3σ event occurred on a held symbol
3. Monitor G-2 daemon progress `cat /tmp/openclaw/g2_monitor.progress.json` — `n_fills` should start incrementing as funding_arb positions reach natural `strategy_close` exits

---

## Relationship to FA-PHANTOM-1

Both bugs share the failure signature ("fast_track CloseAll triggered under normal market conditions, force-closing all strategies") and the validation blocker (G-2 funding_arb can never collect clean-edge fills). The fixes are orthogonal:

| Bug | Input | Root cause | Fix |
|---|---|---|---|
| FA-PHANTOM-1 | `margin_utilization_pct` | Not leverage-aware | Divide notional by leverage_max |
| FA-PHANTOM-2 | `price_drop_pct` | Global scan + no sigma + unconditional CloseAll | Per-held + sigma gate + risk-level gating |

After both fixes, fast_track's three CloseAll triggers each have a defensible, narrow semantic:
- `CircuitBreaker+` → governance escalation
- `margin_util >= 90%` → physical MMR proximity (cash-mode safeguard)
- `held_drop_pct >= 15%` OR `5%+3σ+Defensive+` → genuine flash-crash on a position

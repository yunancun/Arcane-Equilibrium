# G-SR-1 Signal Tightening + R-02 Agent Wiring — Implementation Plan v2.5
# G-SR-1 信號收緊 + R-02 Agent 接線 — 實施計劃 v2.5

**Status**: FINAL — reviewed through 5 rounds (52 findings, all addressed). Ready for E1.
**Created**: 2026-04-12, updated 2026-04-13
**Supersedes**: v2 (same date)
**Review fixes incorporated**: R1 (12) + R2 (15) + R3 (13) + R4 (7) + R5 (5 cosmetic)

---

## 1. Problem Diagnosis (Confirmed / 問題診斷)

**Root cause**: 90% engineering in governance pipeline, 10% in signal source, but 100% of profit comes from signal quality.

- **45.5% of fills occur on signal tick 1** (fragment signals) — source of all losses
- Persistence-based filtering (≥120s signal hold) flips system from net negative to net positive
- Grid accumulates losses in trending markets (inventory drift)
- 5 Python Agents instantiated on MessageBus but output disconnected (PipelineBridge=None)
- ai_service.py 5 stub handlers are R-02 integration target; Rust side has no IPC client yet
- StrategistAgent.judge_edge() is real working code (Ollama Qwen3.5), not stub

**Data basis**: 8717 fills / 46.9 hours / 24 symbols (trading_ai DB, 2026-04-11~12)

**R2 critical correction**: on_tick() fires per PriceEvent (sub-second, ~10/s for BTC),
NOT per kline close. The DB analysis "ticks" were ~60s signal intervals. All persistence
logic must use wall-clock time (milliseconds), not tick counts.

---

## 2. Design Principles (設計原則)

1. **Filter at signal source** — inside strategy on_tick(), no new governance layers
2. **Strategist = configurator** — periodic analysis → IPC param patch, not per-trade gate
3. **Existing governance unchanged** — Guardian 4-check + cost_gate + Kelly + P1 all stay
4. **Grid frequency reduction, not stop** — trend cooldown multiplier, never disable
5. **All new params TOML-configurable** — hot-reloadable via IPC UpdateStrategyParams
6. **Rust first** — signal filtering in Rust strategies; Python only for AI inference
7. **Primary signal is mandatory gate** — confluence scoring only adjusts qty AFTER signal fires (R2 fix C-3)
8. **Graceful degradation** — missing indicators → fallback mode, never silent zeroing (R2 fix H-1)

---

## 3. Architecture Overview (架構總覽)

```
┌──────────────────────────────────────────────────────────────────────┐
│                     Rust openclaw_engine                             │
│                                                                      │
│  strategies/confluence.rs  ← shared module (~250 lines)             │
│    ├─ PersistenceTracker    (time-based, ms window)                  │
│    ├─ compute_score()       (4 conditions, 65-point, Option<f64>)   │
│    ├─ score_to_qty_pct()    (smooth interpolation, no cliffs)        │
│    └─ indicators_ready()    (cold-start fallback check)              │
│                                                                      │
│  strategies/grid_helpers.rs ← extracted from grid_trading.rs (~130L) │
│                                                                      │
│  TickContext → Strategy.on_tick()                                     │
│       │                                                              │
│       ├─ ⓪ Indicator readiness check (cold-start fallback)          │
│       │     If ADX/Hurst/RSI all None → skip confluence, use         │
│       │     primary signal + cooldown only                           │
│       │                                                              │
│       ├─ ① Time-Based Persistence Filter                             │
│       │     Tracks signal TRANSITION timestamp (state onset)         │
│       │     Must hold ≥ min_persistence_ms (default 120_000 = 2min) │
│       │     Close signals EXEMPT                                     │
│       │                                                              │
│       ├─ ② Confluence Score (primary signal = mandatory gate)        │
│       │     Signal must fire → then 4 conditions scored (65-point):  │
│       │     Trend:     ADX=25 regime=20 vol=12 RSI=8                │
│       │     Reversion: ADX=15inv regime=30 vol=10 RSI=10            │
│       │     BB Breakout: confluence = qty modifier only              │
│       │     ADX floor: < 8 → score 0                                │
│       │     Smooth sizing: 0% (≤30) / 0-10% (30-35) / 10-50% (35-45) │
│       │                    50-100% (45-55) / 100% (≥55)             │
│       │     Min order size guard: qty < MIN_NOTIONAL → skip         │
│       │                                                              │
│       ├─ ③ Grid Trend Cooldown (grid only, no confluence)            │
│       │     trend_score = 0.6×adx_factor + 0.4×hurst_factor         │
│       │     hurst_factor = (H-0.50)/0.25, capped at H=0.75         │
│       │     effective_cooldown = base × (1 + trend_score × 5.0)     │
│       │     Range: 1x – 6x, per-symbol                              │
│       │                                                              │
│       └─ StrategyAction::Open(intent)                                │
│              intent.qty = default_qty × confluence_pct               │
│              intent.confidence = confluence_score (reuse existing)   │
│              │                                                       │
│              ▼  existing governance (UNCHANGED)                      │
│    Guardian 4-check → Kelly sizing → P1 cap → cost_gate → Fill      │
│    (Kelly is multiplicative with confluence_pct — serial chain)      │
│                                                                      │
│  ── Strategist Scheduler (tokio background task, R3 fix) ──         │
│    Every 5 min: IPC call to ai_service.sock → strategist_evaluate   │
│    → receive param recommendation → local Rust validation            │
│    (range + diff ≤±30% + weight sum = 65) → apply directly          │
│    Single instance guaranteed (owned by engine, not API workers)     │
│    Top-10 pairs per cycle (not all 96)                               │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ IPC: ai_service.sock (R-02)
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Python AI Layer                                   │
│                                                                      │
│  ai_service.py (JSON-RPC listener, fail-closed)                     │
│    Connection timeout: 100ms (socket connect only)                   │
│    Handler TTL: strategist=15s, guardian=5s (per-method)             │
│    ├─ strategist_evaluate → StrategistAgent._ai_evaluate() [R-02]   │
│    ├─ guardian_check     → GuardianAgent L1 event classify [R-02]   │
│    ├─ analyst_evaluate   → AnalystAgent round-trip attrib. [R-06]   │
│    ├─ scout_scan         → ScoutAgent news+market scan [R-06]       │
│    └─ conductor_evaluate → Conductor priority orchestration [R-06]  │
│                                                                      │
│  MessageBus — Agent inter-communication (event-driven, coexists)    │
│  H1-H5 governance — ThoughtGate/Budget/Router/Governor/CostLog      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase A — Signal Source Tightening (Rust Strategy Layer)

### A0. File Size Prerequisite — Extract & Refactor

**Problem**: grid_trading.rs=1234 lines (>1200 hard limit), ma_crossover.rs=834 lines (>800 warning).

**A0-a: Extract grid_helpers.rs from grid_trading.rs**
Move ~130 lines of pure grid computation helpers (build_linear_levels, build_geometric_levels,
build_levels, nearest_grid_idx, compute_ou_step, rebalance) to `strategies/grid_helpers.rs`.
Target: grid_trading.rs ≤ 1104 lines. (R3-5: verified only ~130 lines are cleanly extractable
as pure functions without &self access, not 200 as originally estimated.)
This is independent of confluence and must happen first.

**A0-b: Create confluence.rs shared module**
New file `rust/openclaw_engine/src/strategies/confluence.rs` (~250 lines).
Each strategy adds ~12 call-site lines, does NOT inline confluence logic.
Must add `pub mod confluence;` and `pub mod grid_helpers;` in strategies/mod.rs.

**A0-c: ConfluenceConfig initialization path** (R3-6, R4-7)
Each strategy Params struct (MaCrossoverParams, BbReversionParams, BbBreakoutParams) gains
confluence fields with `#[serde(default = "...")]` for backward TOML compatibility (R3-11).
StrategyFactory::create_for_engine() builds ConfluenceConfig from Params during construction.
PersistenceTracker initialized as empty HashMap in strategy::new().

**R4-7 Param update rebuild path**: When `update_params_json()` receives new confluence
fields (weights, thresholds) from StrategistScheduler, the strategy must rebuild its
internal `ConfluenceConfig` from the updated Params struct. Implementation:
`update_params()` deserializes JSON → updates Params → calls `self.confluence_config = ConfluenceConfig::from(&self.params)`.
This is a cheap struct copy (~10 fields), no allocation.

**File impact after A0**:
- grid_trading.rs: 1234 → ~1104 (after grid_helpers extraction + ~12 confluence call lines)
- ma_crossover.rs: 834 → ~846 (add ~12 confluence call lines, still under warning with margin)
- bb_reversion.rs: 558 → ~570
- bb_breakout.rs: 752 → ~764
- NEW grid_helpers.rs: ~130 lines
- NEW confluence.rs: ~250 lines
- strategies/mod.rs: +2 lines (pub mod declarations)

### A1. Time-Based Signal Persistence Filter (R2 fix C-1, C-2)

**R2 critical change**: Persistence is TIME-BASED (milliseconds), not tick-count.
on_tick() fires per PriceEvent (~10/s for BTC). Tick counting would give ~20ms, not 2 minutes.

**Location**: `PersistenceTracker` in confluence.rs, called from each strategy's on_tick()

**Data structure**:
```rust
/// Time-based signal persistence tracker.
/// 基於時間的信號持續性追蹤器。
pub struct PersistenceTracker {
    /// Per-symbol: (direction, first_signal_ts_ms)
    /// Records when a signal TRANSITION occurred (state onset).
    /// 記錄信號轉換時間（狀態起始時間）。
    state: HashMap<String, (bool, u64)>,
}

impl PersistenceTracker {
    /// Check if signal has persisted long enough.
    /// 檢查信號是否已持續足夠長時間。
    ///
    /// Tracks signal TRANSITIONS, not states:
    /// - New signal appears (None→Some or direction change) → record timestamp
    /// - Same signal continues → check elapsed time
    /// - Signal disappears → clear entry
    /// - Close signals → always pass (exempt, reduces risk)
    /// 追蹤信號轉換，非狀態：
    /// - 新信號出現（None→Some 或方向改變）→ 記錄時間戳
    /// - 同方向信號持續 → 檢查經過時間
    /// - 信號消失 → 清除記錄
    /// - Close 信號 → 始終通過（免檢，降低風險）
    pub fn check(
        &mut self,
        symbol: &str,
        signal: Option<bool>,  // None=no signal, Some(true)=long, Some(false)=short
        now_ms: u64,
        min_persistence_ms: u64,
        is_close: bool,
    ) -> bool {
        if is_close {
            return true;  // Close always exempt
        }

        match signal {
            None => {
                self.state.remove(symbol);
                false
            }
            Some(is_long) => {
                let entry = self.state.get(symbol);
                match entry {
                    Some(&(prev_dir, first_ts)) if prev_dir == is_long => {
                        // Same direction — check elapsed time
                        now_ms.saturating_sub(first_ts) >= min_persistence_ms
                    }
                    _ => {
                        // New signal or direction change — start timer
                        self.state.insert(symbol.to_string(), (is_long, now_ms));
                        // First appearance — min_persistence_ms=0 would pass immediately
                        min_persistence_ms == 0
                    }
                }
            }
        }
    }
}
```

**Key semantics**:
- Tracks **signal onset** (when state first becomes true), not state duration
- Direction change resets timer completely
- `min_persistence_ms = 120_000` (2 minutes) means signal must be continuously present for 2 min
- Engine restart → cold start, max 2 minutes lost. Acceptable, no DB persistence needed.
- Duplicate position check in router.rs already prevents re-entering same direction

**TOML params** (per strategy, hot-reloadable):
```toml
[ma_crossover]
min_persistence_ms = 120000     # 2 minutes

[bb_reversion]
min_persistence_ms = 120000

[bb_breakout]
min_persistence_ms = 60000      # 1 minute (triple gate already strict)
```

### A2. Weighted Confluence Scoring (R2 fixes C-3, C-5, H-2, M-1)

**R2 critical changes**:
- Primary signal is **mandatory gate** (not a weighted component) — fixes score-without-signal bug
- Scoring scale: 4 conditions sum to **65 points** (not 100)
- RSI momentum for shorts: 30-50 (not 20-45) — fixes oversold-bounce confirmation error
- Smooth interpolation eliminates cliff at threshold boundary
- Grid does NOT get confluence scoring — only trend cooldown (A3)

**Scoring formula**:
```rust
/// Compute confluence score. Returns None if indicators insufficient (cold-start fallback).
/// Returns Some(0.0) if primary signal is false (mandatory gate).
/// 計算匯流分數。指標不足時返回 None（冷啟動退化）。主信號未觸發時返回 Some(0.0)。
///
/// Score range: [0, 65] (4 conditions, signal is gate not component).
/// 分數範圍：[0, 65]（4 個條件，信號是門控非分量）。
///
/// R3-3: Returns Option<f64> instead of NaN sentinel. Rust's type system forces
/// callers to handle the None case explicitly, preventing NaN propagation bugs
/// (NaN < x is always false, which silently zeroes qty without the intended fallback).
/// R3-3：返回 Option<f64> 替代 NaN 哨兵。Rust 類型系統強制 caller 顯式處理 None，
/// 防止 NaN 傳播 bug。
pub fn compute_score(
    config: &ConfluenceConfig,
    primary_signal: bool,
    adx: Option<f64>,
    hurst_regime: &str,
    volume_ratio: Option<f64>,    // R2 fix: Option, not bare f64
    rsi: Option<f64>,
    is_long: bool,
) -> Option<f64> {
    // ── Gate: primary signal MUST fire ──
    if !primary_signal {
        return Some(0.0);
    }

    // ── Cold-start fallback: if key indicators missing, return None ──
    // 冷啟動退化：關鍵指標缺失時返回 None
    // R3-3: Option<f64> forces caller to handle fallback explicitly
    if adx.is_none() && rsi.is_none() {
        return None;  // Caller: None → fallback mode (full qty, skip confluence)
    }

    // ── ADX component ──
    let adx_val = adx.unwrap_or(0.0);
    let adx_score = if adx_val < config.adx_floor {
        0.0  // Insufficient data
    } else if config.invert_adx {
        // Mean-reversion: high ADX = low score, ADX=50→0.0, ADX=8→0.84
        (1.0 - (adx_val / 50.0)).clamp(0.0, 1.0)
    } else {
        // Trend-following: ADX/25, ADX=25→1.0
        (adx_val / 25.0).clamp(0.0, 1.0)
    };

    // ── Regime component ──
    let regime_score = match (config.invert_adx, hurst_regime) {
        (false, "trending") => 1.0,
        (true,  "mean_reverting") => 1.0,
        (false, "mean_reverting") | (true, "trending") => 0.3,
        _ => 0.6,  // "uncertain" or missing
    };

    // ── Volume component (R2 fix: handle None) ──
    let vol_score = match volume_ratio {
        Some(vr) => (vr / 1.2).clamp(0.0, 1.0),
        None => 0.5,  // Neutral when unavailable
    };

    // ── Momentum component (R2 fix C-5: short=30-50, not 20-45) ──
    let rsi_val = rsi.unwrap_or(50.0);
    let momentum_score = match (is_long, rsi_val) {
        (true,  r) if (55.0..=80.0).contains(&r) => 0.9,  // Long + rising momentum
        (false, r) if (30.0..=50.0).contains(&r) => 0.9,  // Short + declining, not oversold
        (_, r) if (40.0..=60.0).contains(&r) => 0.6,       // Neutral zone
        _ => 0.3,  // Over-extended or misaligned
    };

    // ── Weighted sum (4 conditions, max 65) ──
    Some(
        adx_score * config.weight_adx
            + regime_score * config.weight_regime
            + vol_score * config.weight_volume
            + momentum_score * config.weight_momentum
    )
}
```

**Weight allocation** (4 conditions, sum = 65):

| Condition | Trend (MA) | Reversion (BB Rev) | BB Breakout | Grid |
|-----------|:----------:|:------------------:|:-----------:|:----:|
| Signal    | **GATE**   | **GATE**           | **GATE**    | N/A  |
| ADX       | 25         | 15 (inverted)      | 25          | N/A  |
| Regime    | 20         | 30                 | 20          | N/A  |
| Volume    | 12         | 10                 | 12          | N/A  |
| Momentum  | 8          | 10                 | 8           | N/A  |
| **Max**   | **65**     | **65**             | **65**      | —    |

Note: bb_reversion momentum weight adjusted from 15→10 so max matches 65 consistently.
(R3-8: Confirmed intentional. Original R1 had ADX=15+regime=30+vol=10+momentum=15=70,
exceeding 65-point cap. Volume and momentum are comparably important for reversion —
both confirm reversal conditions — so both set to 10. Regime at 30 remains dominant
as intended for mean-reversion strategies.)

**Position sizing — smooth interpolation (R2 fix H-2)**:
```rust
/// Convert score to qty percentage. Smooth curve, no cliffs.
/// 分數→倉位百分比。平滑曲線，無斷崖。
///
/// R3-3: Accepts Option<f64>. None → 1.0 (fallback mode, confluence skipped).
/// R3-3：接受 Option<f64>。None → 1.0（退化模式，跳過 confluence）。
pub fn score_to_qty_pct(score: Option<f64>, config: &ConfluenceConfig) -> f64 {
    let score = match score {
        Some(s) => s,
        None => return 1.0,  // Fallback mode: full qty (confluence skipped)
    };
    if score < config.threshold_no_trade {
        // Below floor: linear ramp 0→10% in bottom band (soft floor, no hard cliff)
        // 低於底線：底部帶線性升坡 0→10%（軟底線，無硬斷崖）
        let ramp_start = config.threshold_no_trade - 5.0;  // e.g., 30
        if score <= ramp_start {
            0.0
        } else {
            0.10 * (score - ramp_start) / 5.0
        }
    } else if score < config.threshold_light {
        // 35→45: linear 10%→50%
        0.10 + 0.40 * (score - config.threshold_no_trade)
            / (config.threshold_light - config.threshold_no_trade)
    } else if score < config.threshold_full {
        // 45→55: linear 50%→100%
        0.50 + 0.50 * (score - config.threshold_light)
            / (config.threshold_full - config.threshold_light)
    } else {
        1.0
    }
}
```

**Threshold tiers** (adjusted for 65-point scale):
```
Score < 30  → 0% (hard floor, effectively unreachable with signal gate)
30 – 35     → 0-10% soft ramp (smooths boundary)
35 – 45     → 10-50% light entry
45 – 55     → 50-100% standard entry
≥ 55        → 100% full entry
```

**BB Breakout special handling**: Triple gate is primary filter. Confluence score
acts as **qty modifier only**. If triple gate passes, BB Breakout always trades,
but qty scales with confluence. `confluence_as_gate = false` in config.

**Kelly interaction**: Serial chain, multiplicative.
```
final_qty = default_qty × confluence_pct × kelly_fraction
                          ↑ strategy layer  ↑ router.rs Gate 2.5
```

**Higher-TF confirmation**: MA crossover's existing `higher_tf_alpha` is PRESERVED
alongside confluence. It remains a separate entry condition in on_tick(), not replaced.

**Strategy call site** (~15 lines per strategy):
```rust
// In ma_crossover on_tick():
let signal: Option<bool> = if fast > slow { Some(true) }
                           else if fast < slow { Some(false) }
                           else { None };

// A1: Time-based persistence
if !self.persistence.check(sym, signal, ctx.timestamp_ms,
                            self.min_persistence_ms, false) {
    return vec![];
}

// A2: Confluence scoring (signal is gate, returns Option<f64>)
// R3-3: Option<f64> — None means cold-start fallback (full qty)
let score = confluence::compute_score(
    &self.confluence_config,
    signal.is_some(),  // primary_signal (already passed persistence)
    ctx.indicators.and_then(|i| i.adx.as_ref().map(|a| a.adx)),
    ctx.indicators.and_then(|i| i.hurst.as_ref().map(|h| &*h.regime))
        .unwrap_or("uncertain"),
    ctx.indicators.and_then(|i| i.volume_ratio),
    ctx.indicators.and_then(|i| i.rsi_14),
    signal.unwrap(),
);
let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
if qty_pct <= 0.0 { return vec![]; }

let qty = self.default_qty * qty_pct;
// R3-9: Min order size guard — skip if notional < exchange minimum
if qty * ctx.price < self.min_notional_usd {
    return vec![];
}

// R3-2: Reuse existing confidence field for confluence score (no struct change)
// ... build intent with intent.qty = qty, intent.confidence = score.unwrap_or(0.0)
```

**TOML params** (all hot-reloadable, agent_adjustable=true, added to each Params struct):

R3-11: All new fields MUST use `#[serde(default = "default_xxx")]` in Rust struct
so that old TOML files without these fields still load correctly (backward compat).
Each default function returns the values shown below.

```toml
[ma_crossover]
min_persistence_ms = 120000           # default: 120000
min_notional_usd = 10.0               # R3-9: min order size guard
confluence_threshold_no_trade = 35.0   # 65-point scale
confluence_threshold_light = 45.0
confluence_threshold_full = 55.0
weight_adx = 25.0
weight_regime = 20.0
weight_volume = 12.0
weight_momentum = 8.0
adx_floor = 8.0

[bb_reversion]
min_persistence_ms = 120000
min_notional_usd = 10.0
confluence_threshold_no_trade = 35.0
confluence_threshold_light = 45.0
confluence_threshold_full = 55.0
weight_adx = 15.0
weight_regime = 30.0
weight_volume = 10.0
weight_momentum = 10.0
adx_floor = 8.0
adx_inverted = true

[bb_breakout]
min_persistence_ms = 60000
min_notional_usd = 10.0
confluence_as_gate = false         # qty modifier only, triple gate is primary
confluence_threshold_no_trade = 35.0
confluence_threshold_light = 45.0
confluence_threshold_full = 55.0
weight_adx = 25.0
weight_regime = 20.0
weight_volume = 12.0
weight_momentum = 8.0
adx_floor = 8.0
```

**Param validation** (enforced in update_params and on load):
- `weight_adx + weight_regime + weight_volume + weight_momentum` must equal 65.0 (±0.1 tolerance)
- All weights ≥ 0
- `threshold_no_trade < threshold_light < threshold_full`
- `threshold_full ≤ 65.0`
- `adx_floor ≥ 0`
- `min_persistence_ms` within param_ranges (0..600_000)
- `min_notional_usd ≥ 1.0` (Bybit minimum ~5 USDT, 10 USDT is safe default)

### A3. Grid Trend-Adaptive Cooldown

**Grid does NOT get confluence scoring** (R2 fix M-1). Grid trades are price-level triggers,
not directional signals. Only trend-based cooldown scaling applies.

**Formula** (unchanged from v2):
```rust
fn compute_trend_adjusted_cooldown(&self, snap: Option<&IndicatorSnapshot>) -> u64 {
    let Some(ind) = snap else { return self.cooldown_ms; };

    let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
    let hurst_val = ind.hurst.as_ref().map(|h| h.hurst).unwrap_or(0.5);

    // ADX factor: 20→50 maps to 0→1
    let adx_factor = ((adx_val - self.adx_low_threshold)
                     / (self.adx_high_threshold - self.adx_low_threshold))
                    .clamp(0.0, 1.0);

    // Hurst factor: 0.50→0.75 maps to 0→1
    let hurst_factor = ((hurst_val - 0.50) / 0.25).clamp(0.0, 1.0);

    // Blend 60/40 (ADX reacts faster than Hurst)
    let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;

    // Multiplier range: 1x to 6x
    let multiplier = 1.0 + (trend_score * self.max_cooldown_boost);

    (self.cooldown_ms as f64 * multiplier) as u64
}
```

**Effect** (R4-1 fix: corrected arithmetic):
- Ranging (ADX=15, H=0.35) → 1.0x → 120s (unchanged)
- Mild trend (ADX=30, H=0.55) → ~2.4x → 288s
  (adx_factor=(30-20)/30=0.33, hurst_factor=(0.55-0.50)/0.25=0.20,
   trend_score=0.6×0.33+0.4×0.20=0.28, multiplier=1+0.28×5.0=2.4)
- Strong trend (ADX=50, H=0.70) → ~5.6x → 672s
  (adx_factor=(50-20)/30=1.0, hurst_factor=(0.70-0.50)/0.25=0.80,
   trend_score=0.6×1.0+0.4×0.80=0.92, multiplier=1+0.92×5.0=5.6)
- Extreme (ADX=60+, H=0.75+) → ~6.0x → 720s (capped)

**Cooldown scope**: Per-symbol, not per-direction.

**TOML params** (added to GridTradingParams struct):
```toml
[grid_trading]
adx_low_threshold = 20.0
adx_high_threshold = 50.0
max_cooldown_boost = 5.0
```

---

## 5. Phase B — R-02 Agent Wiring

### B0. Strategist Scheduler — Rust-side tokio task (R3-1 fix)

**R3-1 critical fix**: Scheduler moved from Python FastAPI to Rust engine.
Problem: uvicorn runs with --workers 4 (default). `app.on_event("startup")` fires
once PER WORKER PROCESS, creating 4 concurrent schedulers racing on IPC writes.
Solution: Single tokio::spawn background task in the Rust engine. Engine is single-
process, guaranteeing exactly one scheduler instance.

**Lifecycle**: tokio background task spawned in engine main(). Runs forever with
try/catch + 5-min sleep. If task panics, tokio runtime logs error; engine continues.

**Flow**:
1. Every 5 min: Rust scheduler sends JSON-RPC `strategist_evaluate` to ai_service.sock
   - Payload: aggregated metrics (from Rust-side paper_state or direct DB query)
   - Selects top-10 pairs by absolute deviation from target metrics (R2 H-5)
2. Python ai_service.py receives request → routes to `STRATEGIST_AGENT._ai_evaluate()`
   - judge_edge() via Ollama (~8s per pair, max 10 × 8s = 80s per cycle)
   - Returns param recommendations as JSON
3. Rust scheduler receives response → **local validation in Rust**:
   - All values within param_ranges() min/max
   - Weight sum = 65.0 (±0.1)
   - Delta from current params ≤ ±30% per field (R3-4: was ±20%, raised for regime shifts)
   - Weight params exempt from delta cap (sum=65 validation sufficient) (R3-4)
   - If validation fails → tracing::warn!, skip apply, retain current params
4. Apply directly: scheduler has Arc reference to strategy instances, calls update_params()

**Interface (R2 AI-E-1 fix)**: StrategistAgent's real chain is `_ai_evaluate(intel)` →
`_ollama.judge_edge(context_str)`. Python side builds IntelObject from the JSON params
received over IPC, NOT from raw DB stats.

```rust
// In rust/openclaw_engine/src/strategist_scheduler.rs (NEW file)

/// Strategist periodic configurator — Rust-side tokio background task.
/// 策略師定時配置器 — Rust 側 tokio 後台任務。
///
/// R3-1: Moved from Python FastAPI to Rust engine to guarantee single instance.
/// uvicorn --workers=4 would create 4 concurrent schedulers; Rust engine is single-process.
pub struct StrategistScheduler {
    ai_client: AiServiceClient,
    strategies: Arc<Mutex<Vec<Box<dyn Strategy>>>>,  // R5-2: Mutex (on_tick needs &mut, RwLock gives no benefit)
    interval: Duration,  // 5 min
    consecutive_failures: AtomicU32,  // R4-2: IPC failure backoff counter
}

impl StrategistScheduler {
    const MAX_EVALS_PER_CYCLE: usize = 10;
    const MAX_PARAM_DELTA_PCT: f64 = 0.30;  // R3-4: ±30% (was ±20%)

    pub async fn run_forever(&self) {
        loop {
            if let Err(e) = self.evaluate_cycle().await {
                let fails = self.consecutive_failures.fetch_add(1, Ordering::Relaxed) + 1;
                // R4-2: Exponential backoff on IPC failure — 5m → 30m → 60m, cap 4h
                let backoff = Duration::from_secs(match fails {
                    1 => 300,         // 5 min (normal interval)
                    2 => 1_800,       // 30 min
                    3 => 3_600,       // 60 min
                    _ => 14_400,      // 4h cap — prevents error spam
                });
                tracing::error!("StrategistScheduler cycle failed ({fails} consecutive): {e}");
                tokio::time::sleep(backoff).await;
                continue;
            }
            self.consecutive_failures.store(0, Ordering::Relaxed);
            tokio::time::sleep(self.interval).await;
        }
    }

    async fn evaluate_cycle(&self) -> Result<(), Box<dyn std::error::Error>> {
        // 1. Gather per-strategy×symbol metrics via DB query (R4-6 fix, R5-3 column names)
        //    paper_state lacks historical aggregates; query fills table:
        //    SELECT strategy_name, symbol, count(*), avg(pnl),
        //           sum(CASE WHEN pnl>0 THEN 1 END)::float/count(*) AS win_rate
        //    FROM trading.fills WHERE ts > now()-interval '7 days'
        //    GROUP BY strategy_name, symbol HAVING count(*) >= 30  -- R5-4: min sample guard
        let metrics = self.gather_strategy_metrics().await?;

        // 2. Rank and select top-10 pairs needing adjustment
        let top_pairs = self.rank_by_deviation(&metrics);

        // 3. For each, call Python strategist via IPC
        for pair in top_pairs.iter().take(Self::MAX_EVALS_PER_CYCLE) {
            let params = serde_json::json!({
                "intel": { "symbol": pair.symbol, "strategy": pair.strategy,
                           "win_rate": pair.win_rate, "avg_pnl": pair.avg_pnl },
                "model_tier": "l1_9b",
            });
            if let Some(response) = self.ai_client.request("strategist_evaluate", params).await {
                if self.validate_recommendation(pair, &response) {
                    self.apply_params(pair.strategy, &response);
                }
            }
        }
        Ok(())
    }

    fn validate_recommendation(&self, pair: &PairMetrics, rec: &Value) -> bool {
        // Range check + weight sum = 65 ± 0.1 + delta ≤ ±30%
        // Weight params (weight_adx etc.) exempt from delta cap (R3-4)
        // ...
        true
    }
}
```

**Note on H1-H5** (unchanged from v2.5): Strategist param changes do NOT go through
H1-H5 ThoughtGate. H1-H5 governs AI inference requests (model selection, budget).
Param changes are validated locally (range + delta + weight sum) which is more
appropriate than ThoughtGate for config tuning.

### B1. Rust AiServiceClient

**New file**: `rust/openclaw_engine/src/ai_client.rs`

**Timeout clarification (R2 AI-E fix)**: Two separate timeouts:
- **Socket connection timeout**: 100ms — if Python ai_service is down, fail immediately
- **Handler TTL**: per-method (strategist=15s, guardian=5s) — for actual inference time
- The 100ms is for the TCP/socket connect only, NOT the full request. Ollama's 2-8s
  inference runs within the 15s handler TTL.

```rust
pub struct AiServiceClient {
    socket_path: PathBuf,
    connect_timeout: Duration,  // 100ms — socket connect only
}

impl AiServiceClient {
    /// Non-blocking request. Spawns tokio task.
    /// Background task: connect (100ms timeout) → send → wait (per-method TTL).
    /// If connect fails: log + return None (fail-closed).
    /// 非阻塞請求。衍生 tokio 任務。
    /// 連接失敗：記錄 + 返回 None（fail-closed）。
    pub fn request_async(&self, method: &str, params: Value)
        -> tokio::sync::oneshot::Receiver<Option<Value>>;
}
```

### B1.5 AIServiceListener Startup Hook (R4-3 fix)

**R4-3 critical blocker**: `AIServiceListener` is defined in ai_service.py but NEVER started
in production. Without it, Rust AiServiceClient connects to a dead socket.

**Required wiring**: ai_service.py `AIServiceListener.start()` must be called during
API server startup. Two options:
1. **Preferred**: `app.on_event("startup")` in control_api main.py — listener runs in
   the API process, socket lifecycle tied to API server (only needs 1 worker to bind).
2. **Alternative**: Standalone systemd/launchd service (separate process).

The listener binds `ai_service.sock` and dispatches JSON-RPC calls to agent handlers.
Phase B implementation must verify socket is live before StrategistScheduler's first cycle.

### B2. ai_service.py Stub → Real Wiring

**Interface mapping (R2 AI-E-1 fix)**:

| Handler | Phase | Real method call | Notes |
|---------|-------|------------------|-------|
| strategist_evaluate | R-02 | `STRATEGIST_AGENT._ai_evaluate(intel)` | Builds IntelObject from params |
| guardian_check | R-02 | `GUARDIAN_AGENT.classify_event(event)` | Informational, not gate |
| analyst_evaluate | R-06 | `ANALYST_AGENT.analyze(trade_data)` | |
| scout_scan | R-06 | `SCOUT_AGENT.scan(symbols)` | |
| conductor_evaluate | R-06 | `CONDUCTOR.orchestrate(state)` | |

### B3. Strategist as Configurator

Strategist does NOT gate individual trades. It periodically tunes the system.

**Every 5 minutes** (via Rust StrategistScheduler, see B0):
1. Rust gathers metrics from paper_state (fill stats, signal frequency per strategy×symbol)
2. Rank pairs by deviation → select top-10
3. IPC call to Python: `strategist_evaluate` → judge_edge() via Ollama (max 80s)
4. Rust-side local validation: range + delta ±30% + weight sum = 65
5. Direct apply to strategy instances (no IPC roundtrip needed — scheduler owns Arc refs)

### B4. Guardian Agent: L1 Information Layer

Rust Guardian = sole production gate (4-check). Python GuardianAgent:
- **Event classification**: abnormal market events via Ollama L1 (~100ms, $0 cost)
- **Information relay**: MessageBus → notify Strategist and other agents
- **No trade blocking** — blocking authority stays entirely in Rust Guardian

---

## 6. Phase C — Learning Loop (Post Phase B)

### C1. Analyst Attribution
- Periodic analysis of round-trip results
- Write outcomes to `trading.decision_outcomes` (currently all NULL)
- Feed back to Strategist for next evaluation cycle

### C2. Scout Intelligence
- 3 news sources already wired (A2 NewsPipeline)
- Funding rate monitoring
- High-severity events → MessageBus → Guardian → Strategist

---

## 7. Complete Data Flow (完整數據流)

```
Market Data (WS/REST)
    ↓
TickContext (price + 16 indicators, all Option<T>)
    ↓
Strategy.on_tick()
    ├─ [A0] Indicator readiness check
    │     ADX+RSI both None? → confluence returns None → fallback: full qty
    │                                                              
    ├─ [A1] Time-based persistence (≥ min_persistence_ms? Close exempt)
    │     Tracks signal TRANSITION onset (timestamp), not state ticks
    │     Uses ctx.timestamp_ms (exchange event time)
    │                                                              
    ├─ [A2] Confluence score (Option<f64>)
    │     Signal = mandatory gate, then 4 conditions / 65 pts
    │     BB Breakout: qty modifier only (triple gate is primary)
    │     Grid: NOT scored — uses A3 cooldown only
    │     funding_arb: NOT scored — stub, excluded until R-06
    │                                                              
    ├─ [A3] Grid: trend-adjusted cooldown (1x-6x)
    │                                                              
    ├─ [R3-9] Min notional guard: qty × price < min_notional → skip
    │                                                              
    └─ StrategyAction::Open(intent)
         intent.qty = default × confluence_pct
         intent.confidence = confluence_score (reuse existing field, R3-2)
         DB write: confidence as FLOAT8 NULLABLE (R4-4: None→SQL NULL, not 0.0,
                   to distinguish cold-start fallback from zero-score)
         ↓
    IntentProcessor.process()  ← UNCHANGED
    ├─ Gov auth check
    ├─ Duplicate check (Gate 1.5, catches redundant persistent-state intents)
    ├─ Guardian 4-check (Rust, sole gate)
    ├─ Kelly sizing (multiplicative with confluence_pct)
    ├─ P1 cap
    ├─ Global position cap
    ├─ Cost gate (edge_estimate - fee)
    └─ Fill → DB
         ↓
    [ASYNC, non-blocking, R-06]
    Analyst → attribution → trading.decision_outcomes
         ↓
    [Every 5 min, Rust StrategistScheduler tokio task (R3-1)]
    Metrics from paper_state → IPC strategist_evaluate → Python judge_edge()
    → Rust local validation (range + delta ±30% + weight sum = 65)
    → direct apply to strategy instances
```

---

## 8. Implementation Schedule (實施排程)

| Phase | Content | Est. Time | Dependency |
|-------|---------|-----------|------------|
| **A0-a** | Extract grid_helpers.rs (~130 lines from grid_trading.rs) | 2h | None |
| **A0-b** | Create confluence.rs shared module (PersistenceTracker + scoring) | 3h | None (parallel w/ A0-a) |
| **A0-c** | ConfluenceConfig init path + serde(default) on all new fields | 2h | A0-b |
| **A1** | Time-based persistence filter + integration into 3 strategies | 3h | A0-b |
| **A3** | Grid trend cooldown | 2h | A0-a |
| **A2** | Weighted confluence scoring (Option<f64>) + integration into 3 strategies | 4h | A0-b, A1 |
| **A-PARAMS** | Expand 3 Params structs + param_ranges() + TOML defaults + validation | 3h | A1+A2 |
| **A-TEST** | Unit tests: confluence scoring + persistence + grid cooldown (~35 tests) | 4h | A-PARAMS |
| **A-E2** | E2 code review | — | A-TEST |
| **A-E4** | E4 test regression (engine lib + e2e baseline) | — | A-E2 |
| **B0+B1** | Rust StrategistScheduler + AiServiceClient (tokio tasks, R3-1, R4-2 backoff) | 6h | A complete |
| **B1.5** | AIServiceListener startup hook (R4-3) | 1h | B1 |
| **B2** | ai_service.py real wiring (strategist + guardian) | 3h | B1.5 |
| **B3** | Strategist validation layer (Rust-side, range+delta+weight) | 3h | B0+B2 |
| **B4** | Guardian L1 info layer | 2h | B2 |
| **C1-C2** | Learning + Scout loop | W23 | B complete |

**Phase A total**: ~23h (including tests, param expansion, serde compat)
**Phase B total**: ~18h (scheduler in Rust + AIServiceListener hook + DB query + validation; buffered from 15h per PA R5 review)

---

## 9. Test Plan (A-TEST detail)

### Unit tests for confluence.rs (~22 tests):
- `test_signal_gate_required` — signal=false → Some(0.0) regardless of other conditions
- `test_adx_floor` — ADX < 8 → adx_score = 0
- `test_adx_trend_scaling` — ADX 0/10/25/40 → correct scores
- `test_adx_inverted` — reversion mode: high ADX = low score
- `test_adx_inverted_floor` — reversion mode: ADX < 8 → 0 (not 1.0)
- `test_regime_matching` — trend+trending=1.0, trend+MR=0.3, etc.
- `test_volume_none` — volume=None → 0.5 neutral
- `test_momentum_long` — RSI 55-80 = 0.9, others lower
- `test_momentum_short` — RSI 30-50 = 0.9 (NOT 20-45, R2 fix C-5)
- `test_momentum_short_oversold` — RSI 20 → 0.3 (NOT 0.9, confirms R2 fix)
- `test_score_max` — all conditions perfect → Some(65.0)
- `test_score_min` — signal=true but all conditions zero → low score
- `test_score_returns_option` — verify return type is Option<f64>, not f64 (R3-3)
- `test_cold_start_returns_none` — ADX=None + RSI=None → None (R3-3)
- `test_qty_pct_smooth` — verify no discontinuity at thresholds (R2 fix H-2)
- `test_qty_pct_soft_ramp` — score 30-35 → 0-10% linear interpolation
- `test_qty_pct_none_fallback` — None input → 1.0 (fallback mode, R3-3)
- `test_weight_validation` — sum ≠ 65 → error
- `test_min_notional_guard` — qty × price < min → skipped (R3-9)
- `test_bb_reversion_trending_blocked` — anti-regime score ~28 < 35 → no trade (M-5)
- `test_bb_reversion_mean_reverting_passes` — correct regime score ~59 > 55 → full
- `test_marginal_conditions` — ADX=8, uncertain regime → score ~35, barely no-trade

### Unit tests for PersistenceTracker (~10 tests):
- `test_first_signal_no_pass` — new signal, persistence > 0ms → false
- `test_signal_persists_pass` — same direction after min_ms elapsed → true
- `test_direction_change_resets` — long→short resets timer to new timestamp
- `test_signal_disappears_clears` — None clears state
- `test_close_always_exempt` — is_close=true → always true
- `test_zero_persistence_immediate` — min_ms=0 → passes immediately
- `test_cold_start` — empty tracker, first call → false (unless min_ms=0)
- `test_time_based_not_tick_based` — verify ms semantics (R2 fix C-1)
- `test_state_onset_tracking` — same direction on multiple calls doesn't reset timer (R2 C-2)
- `test_persistence_after_cooldown` — signal held through cooldown period passes immediately

### Integration tests (in strategy test modules, ~5 tests):
- `test_ma_crossover_with_confluence` — verify qty scaling via confidence field (R3-2)
- `test_bb_breakout_confluence_not_gate` — triple gate passes, confluence only modifies qty
- `test_grid_no_confluence` — grid uses cooldown only, no confluence
- `test_indicators_none_fallback` — missing indicators → full qty (fallback, Option None)
- `test_funding_arb_no_confluence` — funding_arb excluded from confluence (R3-7)

---

## 10. Explicit Exclusions (不做的事)

1. ~~New Guardian checks~~ — Rust Guardian 4-check sufficient
2. ~~Strategist per-tick gate~~ — violates original design, adds latency
3. ~~Delete any Agent~~ — Principle #15 prohibits
4. ~~DB as Agent communication~~ — MessageBus + IPC are correct channels
5. ~~Complicate governance pipeline~~ — problem is signal source, not governance
6. ~~Grid complete stop~~ — frequency reduction only
7. ~~Signal persistence DB persistence~~ — 2-min cold start acceptable
8. ~~Grid confluence scoring~~ — grid uses trend cooldown only (R2 fix M-1)
9. ~~H1-H5 for param changes~~ — local validation more appropriate (R2 fix H-3)
10. ~~Evaluate all 96 pairs~~ — top-10 per cycle, others carry forward (R2 fix H-5)
11. ~~Python-side StrategistScheduler~~ — Rust tokio task, no multi-worker race (R3-1)
12. ~~New OrderIntent field~~ — reuse existing `confidence` for confluence score (R3-2)
13. ~~NaN sentinel~~ — Option<f64> for type safety (R3-3)
14. ~~funding_arb confluence~~ — excluded, stub active=false, add when R-06 activates (R3-7)

---

## 11. Review Fixes Applied

### Round 1 (12 items from AI-E/PA/FA/QC/MIT):
| # | Source | Fix | Section |
|---|--------|-----|---------|
| 1 | PA | Extract confluence.rs (file size) | §4 A0 |
| 2 | QC | ADX < 8 → score 0 (data floor) | §4 A2 |
| 3 | QC | min_persistence adjustable | §4 A1 |
| 4 | QC | Thresholds raised (was 50/65/80) | §4 A2 |
| 5 | QC | max_cooldown_boost=5.0 (was 3.0) | §4 A3 |
| 6 | QC | Hurst factor /0.25 cap H=0.75 | §4 A3 |
| 7 | FA | BB Breakout: confluence=qty modifier not gate | §4 A2 |
| 8 | FA | Kelly × confluence = serial multiply | §4 A2 |
| 9 | FA | Grid cooldown per-symbol | §4 A3 |
| 10 | AI-E | New strategist_scheduler.py | §5 B0 |
| 11 | MIT | IPC schema: expand Params structs | §4 A-PARAMS |
| 12 | MIT | Signal state: no DB persist, cold start OK | §4 A1 |

### Round 2 (15 items, CRITICAL/HIGH/MEDIUM):
| # | ID | Source | Fix | Section |
|---|-----|--------|-----|---------|
| 1 | C-1 | FA | Persistence: time-based ms (not tick count) | §4 A1 |
| 2 | C-2 | FA | Persistence: tracks signal TRANSITION onset | §4 A1 |
| 3 | C-3 | QC | Primary signal = mandatory gate, 65-point scale | §4 A2 |
| 4 | C-4 | AI-E | New params added to Params structs (not unknown fields) | §4 A-PARAMS |
| 5 | C-5 | FA | RSI short momentum: 30-50 (not 20-45) | §4 A2 |
| 6 | H-1 | PA | Cold-start fallback: None indicators → skip confluence | §4 A2 |
| 7 | H-2 | QC | Smooth interpolation, no cliffs at thresholds | §4 A2 |
| 8 | H-3 | AI-E | Strategist validation: range + delta cap + weight sum | §5 B0 |
| 9 | H-4 | PA | grid_trading.rs: extract grid_helpers.rs first | §4 A0-a |
| 10 | H-5 | MIT | Ollama: top-10 pairs per cycle (not all 96) | §5 B0 |
| 11 | M-1 | FA | Grid: no confluence scoring, trend cooldown only | §4 A3 |
| 12 | M-2 | PA | TOML weight sum validation = 65.0 | §4 A2 |
| 13 | M-3 | FA | Volume None → neutral 0.5 | §4 A2 |
| 14 | M-4 | QC | ADX /25 retained, thresholds adjusted to 65 scale | §4 A2 |
| 15 | M-5 | QC | bb_reversion in anti-regime: max ~34/65, below threshold | §4 A2 |

### Round 3 (13 items, 4 FAIL + 8 CONCERN + 1 PASS):
| # | ID | Source | Fix | Section |
|---|-----|--------|-----|---------|
| 1 | R3-1 | AI-E | **Scheduler moved to Rust** (uvicorn --workers=4 race condition) | §5 B0 |
| 2 | R3-2 | PA | **Reuse OrderIntent.confidence** for confluence score (no struct change) | §7, call site |
| 3 | R3-3 | AI-E | **Option<f64> replaces NaN sentinel** (type-safe fallback) | §4 A2 |
| 4 | R3-4 | AI-E | Delta cap raised ±30%; weight params exempt from delta cap | §5 B0 |
| 5 | R3-5 | PA | grid_helpers extractable ~130 lines (not 200); grid→~1104 lines | §4 A0-a |
| 6 | R3-6 | PA | ConfluenceConfig init path: from Params struct in StrategyFactory | §4 A0-c |
| 7 | R3-7 | FA | funding_arb explicitly excluded (stub, active=false, add at R-06) | §10 #14 |
| 8 | R3-8 | FA | bb_reversion momentum 15→10 confirmed intentional (sum=65 constraint) | §4 A2 weight table |
| 9 | R3-9 | QC | Min notional guard: qty × price < min_notional_usd → skip | §4 A2 call site |
| 10 | R3-10 | QC | Confluence at T+120s is correct (current market, not stale onset) | No change needed |
| 11 | R3-11 | MIT | All new TOML fields use #[serde(default)] for backward compat | §4 A0-c, TOML section |
| 12 | R3-12 | PA | timestamp_ms = exchange event time (PriceEvent.ts_ms), confirmed OK | §7 data flow |
| 13 | R3-W | MIT | Workers race: resolved by R3-1 (scheduler in Rust, not Python API) | §5 B0 |

### Round 4 (7 items, final round — 1 arithmetic + 2 FAIL + 4 CONCERN):
| # | ID | Source | Fix | Section |
|---|-----|--------|-----|---------|
| 1 | R4-1 | QC | Effect table arithmetic: 4.2x→5.6x for ADX=50,H=0.70 | §4 A3 |
| 2 | R4-2 | AI-E | **IPC exponential backoff** on failure: 5m→30m→60m→4h cap | §5 B0 |
| 3 | R4-3 | AI-E/MIT | **AIServiceListener startup hook** (never started in prod) | §5 B1.5 (NEW) |
| 4 | R4-4 | AI-E | confidence DB column: NULLABLE FLOAT8, None→SQL NULL (not 0.0) | §7 data flow |
| 5 | R4-5 | AI-E | ~~Arc\<Mutex\>→Arc\<RwLock\>~~ reverted R5-2 (on_tick needs &mut) | §5 B0 struct |
| 6 | R4-6 | MIT | Scheduler metrics from DB query (paper_state lacks per-strategy×symbol stats) | §5 B0 evaluate_cycle |
| 7 | R4-7 | PA | update_params_json() triggers ConfluenceConfig rebuild from updated Params | §4 A0-c |

### Round 5 (5 cosmetic items, all PASS — final polish):
| # | ID | Source | Fix | Section |
|---|-----|--------|-----|---------|
| 1 | R5-1 | QC | Effect table Row 2: ~2.0x→~2.4x (288s) with worked example | §4 A3 |
| 2 | R5-2 | AI-E | Revert RwLock→Mutex (on_tick needs &mut, RwLock gives no benefit) | §5 B0 struct |
| 3 | R5-3 | MIT | DB query column names: created_at→ts, strategy→strategy_name | §5 B0 evaluate_cycle |
| 4 | R5-4 | MIT | Min sample guard: HAVING count(*) >= 30 (skip low-fill pairs) | §5 B0 evaluate_cycle |
| 5 | R5-5 | PA | Phase B buffer: 15h→18h (realistic estimate) | §8 schedule |

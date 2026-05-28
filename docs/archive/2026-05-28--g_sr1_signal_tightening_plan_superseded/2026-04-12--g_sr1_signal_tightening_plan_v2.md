# G-SR-1 Signal Tightening + R-02 Agent Wiring — Implementation Plan v2
# G-SR-1 信號收緊 + R-02 Agent 接線 — 實施計劃 v2

**Status**: DRAFT — pending final review
**Created**: 2026-04-12
**Supersedes**: Conversation-only v1 (same date)
**Review round 1 fixes**: 12 items from AI-E/PA/FA/QC/MIT incorporated

---

## 1. Problem Diagnosis (Confirmed / 問題診斷)

**Root cause**: 90% engineering in governance pipeline, 10% in signal source, but 100% of profit comes from signal quality.

- **45.5% of fills occur on signal tick 1** (fragment signals) — source of all losses
- min_persistence=2 flips system from -$884 to +$5.53 net; =3 yields +$291
- Grid accumulates losses in trending markets (inventory drift)
- 5 Python Agents instantiated on MessageBus but output disconnected (PipelineBridge=None)
- ai_service.py 5 stub handlers are R-02 integration target; Rust side has no IPC client yet
- StrategistAgent.judge_edge() is real working code (Ollama Qwen3.5), not stub

**Data basis**: 8717 fills / 46.9 hours / 24 symbols (trading_ai DB, 2026-04-11~12)

---

## 2. Design Principles (設計原則)

1. **Filter at signal source** — inside strategy on_tick(), no new governance layers
2. **Strategist = configurator** — periodic analysis → IPC param patch, not per-trade gate
3. **Existing governance unchanged** — Guardian 4-check + cost_gate + Kelly + P1 all stay
4. **Grid frequency reduction, not stop** — trend cooldown multiplier, never disable
5. **All new params TOML-configurable** — hot-reloadable via IPC UpdateStrategyParams
6. **Rust first** — signal filtering in Rust strategies; Python only for AI inference

---

## 3. Architecture Overview (架構總覽)

```
                        ┌─────────────────────────────────┐
                        │     Strategist Agent (Python)    │
                        │  5min scheduler → DB analysis    │
                        │  judge_edge() via Ollama L1      │
                        │  + event-driven via MessageBus   │
                        └──────────┬──────────────────────┘
                                   │ IPC: UpdateStrategyParams
                                   │ (weights, persistence, cooldown, active symbols)
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Rust openclaw_engine                             │
│                                                                      │
│  strategies/confluence.rs  ← NEW shared module (A0 file size fix)   │
│    ├─ check_persistence()   (consecutive tick counter)               │
│    ├─ compute_score()       (weighted 5-condition scoring)           │
│    └─ score_to_qty_pct()    (graduated position sizing)             │
│                                                                      │
│  TickContext → Strategy.on_tick()                                     │
│       │                                                              │
│       ├─ ① Persistence Filter  (min_persistence=2, TOML adjustable) │
│       │     Close signals EXEMPT (reduce risk, no persistence req)  │
│       │                                                              │
│       ├─ ② Confluence Score  (5 weighted conditions)                 │
│       │     Trend:     signal=35 ADX=25 regime=20 vol=12 RSI=8     │
│       │     Reversion: signal=30 ADX=15inv regime=30 vol=10 RSI=15 │
│       │     BB Breakout: score → qty modifier only, NOT hard gate   │
│       │     ADX floor: < 8 → score 0 (insufficient data)           │
│       │     Thresholds: <55 no-trade / 55-69 light / 70-84 std / ≥85 full │
│       │     qty = default_qty × confluence_pct (then Kelly downstream) │
│       │                                                              │
│       ├─ ③ Grid Trend Cooldown                                       │
│       │     trend_score = 0.6×adx_factor + 0.4×hurst_factor         │
│       │     hurst_factor = (H-0.50)/0.25, capped at H=0.75         │
│       │     effective_cooldown = base × (1 + trend_score × 5.0)     │
│       │     Range: 1x – 6x, per-symbol (not per-direction)          │
│       │                                                              │
│       └─ StrategyAction::Open(intent) ──→ existing governance (unchanged) │
│              │                                                       │
│              ▼                                                       │
│    Guardian 4-check → Kelly → P1 cap → cost_gate → Fill             │
│    (Kelly is multiplicative with confluence_pct, serial chain)       │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ IPC: ai_service.sock (R-02)
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Python AI Layer                                   │
│                                                                      │
│  ai_service.py (JSON-RPC over Unix socket, <100ms fail-closed)      │
│    ├─ strategist_evaluate → StrategistAgent.judge_edge() [R-02]     │
│    ├─ guardian_check     → GuardianAgent L1 event classify [R-02]   │
│    ├─ analyst_evaluate   → AnalystAgent round-trip attribution [R-06]│
│    ├─ scout_scan         → ScoutAgent news+market scan [R-06]       │
│    └─ conductor_evaluate → Conductor priority orchestration [R-06]  │
│                                                                      │
│  strategist_scheduler.py (NEW, 5min timer)                          │
│    → DB read (fills/signals stats per strategy×symbol)              │
│    → judge_edge() → param recommendation                            │
│    → decision_lease (TTL 15s) → local validation → IPC patch        │
│                                                                      │
│  MessageBus — Agent inter-communication (event-driven, coexists)    │
│  H1-H5 governance — ThoughtGate/Budget/Router/Governor/CostLog      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 4. Phase A — Signal Source Tightening (Rust Strategy Layer)

### A0. Extract Shared Confluence Module (PA file size fix)

**Problem**: grid_trading.rs=1234 lines (>1200 hard limit), ma_crossover.rs=834 lines (>800 warning).
Adding persistence+confluence inline would make them unmaintainable.

**Solution**: New file `rust/openclaw_engine/src/strategies/confluence.rs`

```rust
// strategies/confluence.rs — shared signal filtering logic
// 策略共享信號過濾邏輯

pub struct ConfluenceConfig {
    pub min_persistence: u32,          // default 2
    pub threshold_no_trade: f64,       // default 55.0
    pub threshold_light: f64,          // default 70.0
    pub threshold_full: f64,           // default 85.0
    pub weight_signal: f64,            // strategy-type dependent
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,               // default 8.0 (below = score 0)
    pub invert_adx: bool,             // true for mean-reversion
}

pub struct PersistenceTracker {
    state: HashMap<String, (bool, u32)>,  // (direction, consecutive_count)
}

impl PersistenceTracker {
    /// Track signal persistence. Returns true if signal held ≥ min ticks.
    /// Close signals always return true (exempt from persistence).
    /// 追蹤信號持續性。Close 信號免檢。
    pub fn check(&mut self, symbol: &str, signal: Option<bool>,
                 min_persistence: u32, is_close: bool) -> bool;

    /// Reset on direction change or signal disappearance.
    /// 方向改變或信號消失時重置。
}

/// Compute weighted confluence score [0, 100].
/// 計算加權匯流分數 [0, 100]。
pub fn compute_score(
    config: &ConfluenceConfig,
    primary_signal: bool,
    adx: Option<f64>,
    hurst_regime: &str,        // "trending" | "mean_reverting" | "uncertain"
    volume_ratio: f64,
    rsi: Option<f64>,
    is_long: bool,
) -> f64 {
    // ADX floor: below config.adx_floor → 0.0 (insufficient data)
    // ADX floor: 低於門檻 → 0.0（數據不足）
    let adx_val = adx.unwrap_or(0.0);
    let adx_score = if adx_val < config.adx_floor {
        0.0
    } else if config.invert_adx {
        // Mean-reversion: high ADX = low score
        (1.0 - (adx_val / 50.0)).clamp(0.0, 1.0)
    } else {
        // Trend-following: ADX/25, scaling to 1.0 at ADX=25+
        (adx_val / 25.0).clamp(0.0, 1.0)
    };

    let regime_score = match (config.invert_adx, hurst_regime) {
        (false, "trending") => 1.0,          // trend strategy in trend
        (true,  "mean_reverting") => 1.0,    // reversion strategy in MR
        (false, "mean_reverting") | (true, "trending") => 0.3,
        _ => 0.6,  // uncertain
    };

    let vol_score = (volume_ratio / 1.2).clamp(0.0, 1.0);

    let momentum_score = match (is_long, rsi.unwrap_or(50.0)) {
        (true,  r) if (55.0..=80.0).contains(&r) => 0.9,
        (false, r) if (20.0..=45.0).contains(&r) => 0.9,
        (_, r) if (40.0..=60.0).contains(&r) => 0.6,
        _ => 0.4,
    };

    let signal_score = if primary_signal { 1.0 } else { 0.0 };

    signal_score * config.weight_signal
        + adx_score * config.weight_adx
        + regime_score * config.weight_regime
        + vol_score * config.weight_volume
        + momentum_score * config.weight_momentum
}

/// Convert confluence score to position size percentage.
/// Confluence 分數 → 倉位百分比。
pub fn score_to_qty_pct(score: f64, config: &ConfluenceConfig) -> f64 {
    if score < config.threshold_no_trade {
        0.0
    } else if score < config.threshold_light {
        // Linear interpolation 25-50%
        0.25 + (score - config.threshold_no_trade)
            / (config.threshold_light - config.threshold_no_trade) * 0.25
    } else if score < config.threshold_full {
        // Linear interpolation 50-100%
        0.50 + (score - config.threshold_light)
            / (config.threshold_full - config.threshold_light) * 0.50
    } else {
        1.0
    }
}
```

Each strategy calls ~5 lines:
```rust
// In ma_crossover on_tick():
if !self.persistence.check(sym, signal, self.min_persistence, false) {
    return vec![];
}
let score = confluence::compute_score(&self.confluence_config, ...);
let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
if qty_pct == 0.0 { return vec![]; }
intent.qty = self.default_qty * qty_pct;
```

**File impact**: confluence.rs ~200 lines. Each strategy adds ~10 lines, removes 0.

### A1. Signal Persistence Filter

**Location**: `PersistenceTracker` in confluence.rs, called from each strategy's on_tick()
**Mechanism**: HashMap<String, (bool, u32)> tracks (direction, consecutive_ticks) per symbol

**Behavior**:
- Signal appears (Long) → counter = 1
- Same signal next tick → counter = 2 → passes min_persistence=2
- Signal disappears → counter reset to 0
- Direction changes (Long→Short) → counter reset to 1 for new direction
- **Close signals exempt** — StrategyAction::Close never requires persistence (reduces risk)
- Engine restart → cold start, max 2 ticks (~2 min) lost. Acceptable — no DB persistence needed.

**TOML params** (per strategy, hot-reloadable):
```toml
[ma_crossover]
min_persistence = 2

[bb_reversion]
min_persistence = 2

[bb_breakout]
min_persistence = 2
```

### A2. Weighted Confluence Scoring

**Weight allocation by strategy type**:

| Condition | Trend (MA) | Reversion (BB Rev) | BB Breakout | Notes |
|-----------|:----------:|:------------------:|:-----------:|-------|
| Signal    | 35         | 30                 | 35          | Primary trigger, necessary |
| ADX       | 25         | 15 (inverted)      | 25          | Floor: ADX < 8 → 0 |
| Regime    | 20         | 30                 | 20          | Hurst regime match |
| Volume    | 12         | 10                 | 12          | Breakout conviction |
| Momentum  | 8          | 15                 | 8           | RSI directional |
| **Total** | **100**    | **100**            | **100**     | |

**ADX component specifics**:
- **Trend strategies**: `(adx / 25.0).clamp(0, 1)` — ADX=25 = full score (R1 fix: was /40)
- **Reversion**: `(1.0 - adx / 50.0).clamp(0, 1)` with floor: ADX < 8 → score 0 (R1 fix)
- **All**: ADX < 8 → score 0 regardless of strategy type (insufficient data guard)

**Hurst component** (no change from v1 except grid):
- Trend + "trending" → 1.0; Trend + "mean_reverting" → 0.3
- Reversion inverted

**Threshold tiers** (R1 fix: raised from 50/65/80):
```
Score < 55  → DO NOT TRADE (0%)
55 – 69     → Light entry (25-50% qty)
70 – 84     → Standard entry (50-100% qty)
≥ 85        → Full entry (100% qty)
```

**BB Breakout special handling** (R1 fix): Triple gate (squeeze→expansion + volume + Donchian) is the primary filter. Confluence score acts as **qty modifier only**, not additional hard gate. BB Breakout always passes if triple gate passes, but qty scales with confluence.

**Kelly interaction** (R1 fix): Serial chain, multiplicative.
```
final_qty = default_qty × confluence_pct × kelly_fraction
                          ↑ strategy layer  ↑ router.rs Gate 2.5
```
Confluence reduces qty before it reaches Kelly. Kelly further reduces. No conflict.

**TOML params** (all hot-reloadable, agent_adjustable=true):
```toml
[ma_crossover]
confluence_threshold_no_trade = 55.0
confluence_threshold_light = 70.0
confluence_threshold_full = 85.0
weight_signal = 35.0
weight_adx = 25.0
weight_regime = 20.0
weight_volume = 12.0
weight_momentum = 8.0
adx_floor = 8.0

[bb_reversion]
confluence_threshold_no_trade = 55.0
confluence_threshold_light = 70.0
confluence_threshold_full = 85.0
weight_signal = 30.0
weight_adx = 15.0
weight_regime = 30.0
weight_volume = 10.0
weight_momentum = 15.0
adx_floor = 8.0
adx_inverted = true

[bb_breakout]
# Confluence is qty modifier only (triple gate is primary filter)
confluence_as_gate = false
weight_signal = 35.0
weight_adx = 25.0
weight_regime = 20.0
weight_volume = 12.0
weight_momentum = 8.0
adx_floor = 8.0
```

### A3. Grid Trend-Adaptive Cooldown

**Formula** (R1 fixes: boost 3→5, hurst denominator 0.15→0.25):
```rust
fn compute_trend_adjusted_cooldown(&self, snap: Option<&IndicatorSnapshot>) -> u64 {
    let Some(ind) = snap else { return self.cooldown_ms; };

    let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
    let hurst_val = ind.hurst.as_ref().map(|h| h.hurst).unwrap_or(0.5);

    // ADX factor: 20→50 maps to 0→1
    let adx_factor = ((adx_val - self.adx_low_threshold)
                     / (self.adx_high_threshold - self.adx_low_threshold))
                    .clamp(0.0, 1.0);

    // Hurst factor: 0.50→0.75 maps to 0→1 (R1 fix: was 0.50→0.65)
    let hurst_factor = ((hurst_val - 0.50) / 0.25).clamp(0.0, 1.0);

    // Blend 60/40 (ADX reacts faster)
    let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;

    // Multiplier range: 1x to 6x (R1 fix: was 1x to 4x)
    let multiplier = 1.0 + (trend_score * self.max_cooldown_boost);

    (self.cooldown_ms as f64 * multiplier) as u64
}
```

**Effect**:
- Ranging (ADX=15, H=0.35) → 1.0x → 120s
- Mild trend (ADX=30, H=0.55) → ~2.0x → 240s
- Strong trend (ADX=50, H=0.70) → ~4.2x → 504s
- Extreme (ADX=60+, H=0.75+) → ~6.0x → 720s

**Cooldown scope**: Per-symbol, not per-direction. Grid is symmetric; trending market suppresses both sides equally.

**TOML params**:
```toml
[grid_trading]
adx_low_threshold = 20.0
adx_high_threshold = 50.0
max_cooldown_boost = 5.0
```

---

## 5. Phase B — R-02 Agent Wiring

### B0. Strategist Scheduler (NEW, R1 fix)

**Problem**: StrategistAgent is event-driven (MessageBus), but configurator role needs periodic execution.
**Solution**: New `strategist_scheduler.py` — 5-minute timer, coexists with event-driven path.

```python
# strategist_scheduler.py — periodic Strategist configurator
# 策略師定時配置器

class StrategistScheduler:
    """5-minute periodic evaluator — reads DB, calls judge_edge(), pushes IPC params."""

    async def periodic_evaluate(self):
        """
        1. Query DB: fills/signals stats per (strategy, symbol) last 30 min
        2. Call STRATEGIST_AGENT.judge_edge() for each active pair
        3. Produce param recommendations (weights, persistence, active symbols)
        4. Validate: all params within param_ranges()
        5. Push via IPC UpdateStrategyParams (with decision_lease TTL=15s)
        """
```

### B1. Rust AiServiceClient

**New file**: `rust/openclaw_engine/src/ai_client.rs`
- Async Unix socket JSON-RPC client → `/tmp/openclaw/ai_service.sock`
- **Fail-closed timeout: 100ms** (R1 fix) — if Python unreachable, skip AI call, use defaults
- Non-blocking: spawns tokio task, returns immediately via oneshot channel
- Not on tick hot path — called from background task only

### B2. ai_service.py Stub → Real Wiring

| Handler | Phase | Target | Status |
|---------|-------|--------|--------|
| strategist_evaluate | R-02 | StrategistAgent.judge_edge() | Real Ollama code exists |
| guardian_check | R-02 | GuardianAgent L1 event classify | Informational, not gate |
| analyst_evaluate | R-06 | AnalystAgent round-trip attribution | |
| scout_scan | R-06 | ScoutAgent news+market | |
| conductor_evaluate | R-06 | Conductor priority orchestration | |

### B3. Strategist as Configurator

Strategist does NOT gate individual trades. It periodically tunes the system:

**Every 5 minutes**:
1. DB query: per-(strategy, symbol) fill stats, signal frequency, win rate
2. judge_edge() via Ollama: evaluate current market conditions per pair
3. Output: parameter recommendations
   - Which symbols should be active/paused per strategy
   - Whether confluence weights need adjustment
   - Whether min_persistence should change
4. Decision lease (TTL 15s, Principle #3 compliance)
5. Local validation: all params within param_ranges()
6. IPC UpdateStrategyParams → Rust engine hot-reload

### B4. Guardian Agent: L1 Information Layer

Rust Guardian = sole production gate (4-check). Python GuardianAgent role:
- **Event classification**: abnormal market events (flash crash, volume spike, funding spike)
- **Information relay**: MessageBus → notify Strategist and other agents
- **No trade blocking** — blocking authority stays entirely in Rust Guardian

---

## 6. Phase C — Learning Loop (Post Phase B)

### C1. Analyst Attribution
- Periodic analysis of round-trip results
- Write outcomes to `trading.decision_outcomes` (currently all NULL — MIT finding)
- Feed back to Strategist for next evaluation cycle

### C2. Scout Intelligence
- 3 news sources (CryptoPanic + CoinTelegraph + Google News) already wired (A2 NewsPipeline)
- Funding rate monitoring
- High-severity events → MessageBus → Guardian → Strategist

---

## 7. Complete Data Flow (完整數據流)

```
Market Data (WS/REST)
    ↓
TickContext (price + 16 indicators)
    ↓
Strategy.on_tick()
    ├─ [A1] Persistence check (≥ min_persistence ticks? Close exempt)
    ├─ [A2] Confluence score (≥ threshold? BB Breakout: qty modifier only)
    ├─ [A3] Grid: trend-adjusted cooldown (1x-6x)
    └─ StrategyAction::Open(intent)  [intent.qty = default × confluence_pct]
         ↓
    IntentProcessor.process()  ← UNCHANGED
    ├─ Gov auth check
    ├─ Duplicate check
    ├─ Guardian 4-check (Rust, sole gate)
    ├─ Kelly sizing (multiplicative with confluence_pct)
    ├─ P1 cap
    ├─ Global position cap
    ├─ Cost gate (edge_estimate - fee)
    └─ Fill → DB (confluence_score in intents.details JSONB)
         ↓
    [ASYNC, non-blocking]
    ai_service.sock → analyst_evaluate (R-06)
         ↓
    Analyst → attribution → trading.decision_outcomes
         ↓
    [Every 5 min]
    StrategistScheduler → DB read → judge_edge() → IPC UpdateStrategyParams
    (min_persistence / weights / cooldown / active symbols)
```

---

## 8. Implementation Schedule (實施排程)

| Phase | Content | Est. Time | Dependency |
|-------|---------|-----------|------------|
| **A0** | Extract confluence.rs shared module | 2h | None |
| **A1** | Signal persistence filter | 3h | A0 |
| **A3** | Grid trend cooldown | 3h | A0 (parallel with A1) |
| **A2** | Weighted confluence scoring | 4h | A0 |
| **A-E2** | E2 code review | — | A0+A1+A2+A3 |
| **A-E4** | E4 test regression | — | A-E2 |
| **B0** | strategist_scheduler.py | 3h | A complete |
| **B1** | Rust AiServiceClient | 4h | A complete |
| **B2** | ai_service.py real wiring | 4h | B1 |
| **B3** | Strategist configurator logic | 4h | B0+B2 |
| **B4** | Guardian L1 info layer | 2h | B2 |
| **C1-C2** | Learning + Scout loop | W23 | B complete |

---

## 9. Explicit Exclusions (不做的事)

1. ~~New Guardian checks~~ — Rust Guardian 4-check sufficient
2. ~~Strategist per-tick gate~~ — violates original design, adds latency
3. ~~Delete any Agent~~ — Principle #15 prohibits
4. ~~DB as Agent communication~~ — MessageBus + IPC are correct channels
5. ~~Complicate governance pipeline~~ — problem is signal source, not governance
6. ~~Grid complete stop~~ — frequency reduction only
7. ~~Signal persistence DB persistence~~ — 2-tick cold start acceptable
8. ~~IPC strict versioning~~ — Option<T> + unknown-key-ignore sufficient

---

## 10. Round 1 Review Fixes Applied (第一輪審核修正)

| # | Source | Fix | Section |
|---|--------|-----|---------|
| 1 | PA | Extract confluence.rs (file size) | §4 A0 |
| 2 | QC | ADX < 8 → score 0 (data floor) | §4 A2 |
| 3 | QC | min_persistence=2, TOML adjustable | §4 A1 |
| 4 | QC | Thresholds raised: 55/70/85 (was 50/65/80) | §4 A2 |
| 5 | QC | max_cooldown_boost=5.0 (was 3.0) | §4 A3 |
| 6 | QC | Hurst factor /0.25 cap H=0.75 (was /0.15 H=0.65) | §4 A3 |
| 7 | FA | BB Breakout: confluence=qty modifier not gate | §4 A2 |
| 8 | FA | Kelly × confluence = serial multiply | §4 A2 |
| 9 | FA | Grid cooldown per-symbol (not per-direction) | §4 A3 |
| 10 | AI-E | New strategist_scheduler.py for 5min cycle | §5 B0 |
| 11 | MIT | IPC schema: Option<T> + ignore unknown keys | §9 #8 |
| 12 | MIT | Signal state: no DB persist, cold start OK | §9 #7 |

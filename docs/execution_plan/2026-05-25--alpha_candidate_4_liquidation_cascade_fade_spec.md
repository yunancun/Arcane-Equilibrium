# Alpha Tournament Candidate #4 — Microstructure Liquidation Cascade Fade

**Date**: 2026-05-25
**Author**: PA（W1-A sub-agent task）
**Source SoT**: dispatch packet `srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` §2.2 candidate #4 + §2.4 dispatch design
**Predecessor infrastructure**: BB C6 PROOF PASS (`market.liquidations` 31,473 rows accumulated) + LiquidationPulseAggregator (W-AUDIT-8a C1) + LiquidationPulsePanel (alpha_surface.rs:436) + ADR-0038 §Decision 1 self-hosted PG only
**Status**: ⚠️ NO-GO / 请勿实作（记于 2026-07-18 文档审计）— 原文 "PA SPEC — IMPL-ready 給 W2-B E1 sub-agent"（见下方 NO-GO banner）。
**Scope**: Stream A candidate #4 「microstructure liquidation cascade fade」 IMPL-ready specification

> ⚠️ **NO-GO — 请勿实作（记于 2026-07-18 文档审计）**
>
> `liquidation_cascade_fade` 未通过验证，非当前 build 目标：
> - 执行可达性 reject：`docs/audits/2026-05-31--p0_edge_cost_wall_investigation.md`（"A2 liquidation cascade fade"：maker-fill 49% < 50%、R:R < 1、avg_net −2.45 bps）。
> - 统计 NO-GO（2026-06-03）：280 事件全 |t| < 1.3，信号被 down-beta regime 伪装（memory `project_2026_06_03_blocked_signal_and_cascade_fade_nogo`）。
>
> 本 spec 仅保留设计 lineage；revive 须新证据 + `TODO.md` gate。本文档中的「IMPL-ready」措辞已失效。

---

## §0 TL;DR — Verdict

**新策略名稱**：`liquidation_cascade_fade`（短倉 fade，5min liquidation window > threshold 後 fade against dominant side）

**核心 thesis**:

per Bybit V5 微結構觀察 + W-AUDIT-8a C1 LiquidationPulseAggregator 既有 IMPL：
- 5min rolling window 內 long_notional_5m ≥ threshold 表示 mass long liquidation cascade event
- 級聯強平 = forced market sell pressure → price 短期 overshoot 下行 → mean-revert 機會
- **Fade dominant side**：long liquidation 主導 → take long entry 做 mean-revert（counter to cascade）
- **Self-fills 必剔除**：own fills 不參與 cluster_notional_5m 計算（per ADR-0038 self-hosted PG only 且 self-fills 不寫 market.liquidations writer，因該 writer 訂閱 allLiquidation Bybit-wide stream，但本 spec 必 IMPL `intent.strategy_name != "liquidation_cascade_fade"` filter 作 defensive layer）

**核心差異 vs 其他 microstructure 策略**:

| 維度 | bb_breakout (existing) | liquidation_cascade_fade (new) |
|---|---|---|
| Trigger source | rolling Bollinger band breakout | liquidation cluster magnitude threshold |
| Direction | breakout follow-through | **fade against dominant cascade side** |
| Window | 1m kline indicator | **5min rolling liquidation notional** |
| Look-ahead bias risk | rolling(N).max() 含 current bar pattern（per memory feedback_indicator_lookahead_bias）| **無 rolling stat 作 breach signal**；用 LiquidationPulsePanel snapshot value 直接判定（pulse aggregator 內 5m window 已 strict timestamp-based trim） |
| Data source | `ctx.indicators` (Tier 1 TA) | `surface.liquidation_pulse` (Tier 3 microstructure) |
| Self-fills 風險 | 無（kline 不含 self trade） | **必剔除**（market.liquidations writer subscribes Bybit-wide allLiquidation, but: (i) our positions 不太可能進入 liquidations stream because demo 風控 P0 hardstop 在 liquidation 之前已平；(ii) IMPL 仍 enforce defensive filter） |

---

## §1 Algorithm Specification

### §1.1 Entry conditions（5 條件 ALL true 才入場）

```
Entry gate (5 conditions ALL true):
  1. surface.liquidation_pulse.is_some() AND pulse_for(symbol).is_some()
     [LiquidationPulsePanel available + symbol in cohort]
  2. dominant_notional_5m > threshold_usd
     [where dominant_notional = max(long_notional_5m, short_notional_5m)]
     [threshold default = $500_000 (BTC/ETH) / $100_000 (alt)]
  3. event_count_5m >= min_events
     [防 single-large-event 假訊號；default min_events = 3]
  4. dominant_side != LiquidationSide::Mixed
     [Mixed 表示 long/short 都被 liquidate（chop event），無 directional thesis；reject]
  5. h0_allowed && cooldown_expired (per symbol, 30min cooldown)
     [防同一 cascade 重複入場]
```

**入場方向決定**：
```rust
let entry_is_long = match pulse.dominant_side {
    LiquidationSide::LongLiquidated => true,   // long 被強平 → price overshoot 下行 → take long fade
    LiquidationSide::ShortLiquidated => false, // short 被強平 → price overshoot 上行 → take short fade
    LiquidationSide::Mixed => return vec![],   // Mixed 不入場（已在 gate 4 reject）
};
```

**為什麼 fade 而非 follow-through**：
- liquidation cascade 是 forced order flow（非 informed alpha）；事件後 price 短期 overshoot → 提供 mean-revert entry
- 對比「breakout follow-through」thesis：cascade 是 panic event，follow-through 反向直接 long short squeeze 風險高
- per crypto microstructure 文獻：1-5min liquidation cascade window 後 price 平均 reversion 30-60min（exit window 對齊）

### §1.2 Exit conditions（OR 邏輯）

```
Exit triggers (4 conditions, ANY true → close):
  1. now_ms - entry_ms > max_hold_ms (default 60min)
     [time-stop exit; 1h 後 mean-revert thesis 失效]
  2. Take profit hit: pnl_pct >= take_profit_pct (default 1.5%)
     [tight TP; cascade mean-revert 期望短期內 1-2% gain]
  3. Stop loss hit (P1 per_strategy stop_loss_max_pct_override; default 2.0%)
     [tight SL；超越 2% 表示 cascade 是 informed selling 而非 panic]
  4. Reverse cascade detected:
     - pulse.dominant_side flips (LongLiquidated → ShortLiquidated 或反之)
     - dominant_notional_5m > entry_notional × 1.5
     [二次 cascade 反向 → 立即出場避雙重 hit]
```

### §1.3 Threshold model — per-symbol calibrated（per ADR-0036 §Decision 4 block bootstrap）

```rust
// liquidation_cascade_fade threshold model（per-symbol）
// 預設 hard-coded for Stage 1; Sprint 3+ 走 V109 anomaly_events table walk-forward calibrated threshold
fn dominant_notional_threshold(&self, symbol: &str) -> f64 {
    self.per_symbol_threshold
        .get(symbol)
        .copied()
        .unwrap_or(self.default_threshold_usd)  // fallback $100k for non-BTC/ETH
}

// Stage 1 預設值（per spec §2.1 BTC/ETH only）：
// BTCUSDT: $500_000 5m notional（per historical Bybit Q1 2026 liquidation distribution percentile 80%）
// ETHUSDT: $300_000 5m notional
// (其他 symbol 不在 Stage 1 cohort，threshold N/A)
```

**Why per-symbol threshold**：
- BTC liquidation notional 自然遠高於 ALT（BTC 單筆強平 USD 量級 100x of ALT）
- 全 cohort uniform threshold 對 BTC 過鬆（噪音 signal）對 ALT 過緊（漏 alpha）
- Stage 1 hard-coded（per dispatch packet §2.2 BTC/ETH cohort）；Sprint 3+ V109 anomaly_events table 走 block bootstrap walk-forward calibration（per ADR-0036 §Decision 4 cadence 30d re-estimate）

### §1.4 Self-fills 剔除（defensive layer）

```rust
// liquidation_cascade_fade self-fills 剔除
// LiquidationPulsePanel 由 LiquidationPulseAggregator 從 Bybit allLiquidation WS event 餵入
// 我方 fills 不主動寫 market.liquidations table（market_writer 路徑只訂閱 Bybit 推送）
// → 結構上 self-fills 不會進入 panel
// 但 IMPL 仍 enforce defensive filter（防 future Bybit WS 行為變更 / 我方倉位被強平場景）

fn is_self_origin_event(pulse: &LiquidationPulse) -> bool {
    // 防衛性檢查：5m window 內 event_count = 1 且 notional 落在我方 typical position size range
    // 因為：(a) market.liquidations writer 是 Bybit-wide stream consumer，理論不會混 self；
    //       (b) 但若我方倉位在 demo 被 liquidate（per 風控失效場景），event 仍可能進入 panel；
    //       (c) typical demo position $100-500 notional；event 落在此範圍 + count=1 → suspicious
    // 此 filter 預設 disabled（per Stage 1 normal demo balance > $500 too low to trigger）；
    // Sprint 3+ V109 anomaly_events 加 metadata.source = "own_position" 後 enable hard filter
    false  // Stage 1 stub；Sprint 3+ wire 真正 filter
}
```

**Why Stage 1 stub**:
- per BB C6 PROOF PASS evidence：market.liquidations 31,473 rows 中無 self-origin row（writer 訂閱 Bybit-wide stream，不含本 demo 倉位）
- Stage 1 demo balance（$1000 typical）強平閾值 90%+ margin loss 之前 P0 hardstop 已強平倉位（reduceOnly close）；不會走 Bybit liquidation engine 路徑
- defensive filter Sprint 3+ V109 schema land 後加 hard enforcement（per AC-S2-A-C4-7）

### §1.5 Look-Ahead Bias Protection（per memory `feedback_indicator_lookahead_bias`）

**結構性論證 — liquidation_cascade_fade 不踩 look-ahead bias 陷阱**：

| Signal source | look-ahead bias 風險 | mitigation |
|---|---|---|
| `pulse.cluster_notional_5m` | **無** — LiquidationPulseAggregator 內 5m window trim 用 `current_ts - WINDOW_5M_MS` cutoff，**不含 current event 之外的 future event**（per `srv/rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs:177`）| ✅ 直接使用 |
| `pulse.event_count_5m` | **無** — 同上，5m sliding window 嚴格 timestamp-based | ✅ 直接使用 |
| `pulse.dominant_side` | **無** — 即時 snapshot 計算 based on current window cluster | ✅ 直接使用 |
| `entry threshold comparison` | **無** — 直接比較當前 pulse value 與 threshold；無 rolling extreme | ✅ 直接使用 |

**Why no `rolling(N).max()` pattern**：
- liquidation_cascade_fade entry signal = `dominant_notional_5m > threshold_usd`（**直接閾值比較**）
- 不依賴「current bar 是 N-bar max」的 selection bias pattern（G1-01 Donchian pre-bug）
- 5min window 為 panel aggregator 內部 trim window，**非 entry 信號 rolling window**

**強制 SOP — 如 Sprint 3+ 加入 rolling stat 作 confidence weight 或 dynamic threshold**：

per memory `feedback_indicator_lookahead_bias` 規則：
- 任何 `rolling(N).max() / .min()` 作 breach signal 必先檢查含/不含 current bar
- 必並列計算 engine-faithful（含 current bar）+ leak-free（`shift(1)` 排除 current bar）
- **強制 shift(1) 為 production version**
- Test fixture 必含 leak-free 對比樣本

**例**：若 W2-B IMPL 後 Sprint 3+ 加入「dominant_notional rolling 7d z-score」作 dynamic threshold：

```rust
// CORRECT pattern (leak-free)
let historical_window = self.notional_history.iter()
    .filter(|(ts, _)| *ts < now_ms - 60_000)  // ← shift(1) equivalent: exclude last 1min
    .map(|(_, n)| n)
    .collect();
let z_score = compute_z_score(&historical_window, current_notional);

// WRONG pattern (含 current bar look-ahead bias)
let all_window = self.notional_history.iter()
    .map(|(_, n)| n)
    .chain(std::iter::once(&current_notional))  // ← 含 current → bias
    .collect();
let z_score = compute_z_score(&all_window, current_notional);
```

**Production version 必走 CORRECT pattern**；test fixture 必含兩版 comparison 顯示 leak-free 結果為 production source of truth.

---

## §2 Symbol Universe Constraint

### §2.1 Stage 1 Demo 限定

```toml
# srv/settings/strategy_params_demo.toml
[liquidation_cascade_fade]
active = false  # default disabled fail-closed
allowed_symbols = ["BTCUSDT", "ETHUSDT"]  # Stage 1 BTC/ETH only
# Stage 2+ 擴 ["SOLUSDT", "BNBUSDT"]；ALT 因 thin orderbook + fake cascade 風險暫不開
```

對齊 dispatch packet §2.2 BTC/ETH cohort focus

### §2.2 Cohort intersection with LiquidationPulseAggregator existing cohort

per `srv/rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs:88`：
- LiquidationPulseAggregator 接受 `cohort_symbols: Vec<String>` 建構參數
- 既有 cohort（W-AUDIT-8a C1 spec）：與 funding_curve / oi_delta 共享 hardcoded cohort
- liquidation_cascade_fade 從 panel `pulse_for(symbol)` 讀取；自動繼承 cohort 限制（non-cohort symbol → None → skip）

確認：`pulse_for("BTCUSDT")` / `pulse_for("ETHUSDT")` 必存在於既有 cohort（W-AUDIT-8a C1 設計含 BTC/ETH）。

---

## §3 Risk Configuration TOML Spec

### §3.1 strategy_params_demo.toml block

```toml
# srv/settings/strategy_params_demo.toml — Sprint 2 W2-B IMPL append
# liquidation_cascade_fade — Alpha Tournament Candidate #4（per Sprint 2 dispatch packet §2.2）
# Sprint 2 demo-only；live deployment 須 5-gate green + P0-EDGE-1 closure
# 不依賴 Bybit historical liquidations REST API（per ADR-0038 §Decision 1 self-hosted PG only）
# 上游 LiquidationPulseAggregator（W-AUDIT-8a C1）已 land；本策略消費 AlphaSurface.liquidation_pulse
[liquidation_cascade_fade]
active = false                                # default disabled fail-closed
cooldown_ms = 1_800_000                       # 30min cooldown per symbol（防同一 cascade 重複入場）
allowed_symbols = ["BTCUSDT", "ETHUSDT"]      # Stage 1 BTC/ETH only
default_threshold_usd = 100_000.0             # 預設 5m notional 閾值
btc_threshold_usd = 500_000.0                 # BTC 5m notional 閾值
eth_threshold_usd = 300_000.0                 # ETH 5m notional 閾值
min_events = 3                                # min event_count_5m
max_hold_ms = 3_600_000                       # 60min hard time-stop
take_profit_pct = 1.5                         # TP at 1.5% mean-revert
reverse_cascade_ratio = 1.5                   # 反向 cascade > 入場時 1.5x → 立即出場
```

### §3.2 risk_config_demo.toml per_strategy block

```toml
# srv/settings/risk_control_rules/risk_config_demo.toml — Sprint 2 W2-B IMPL append
# liquidation_cascade_fade Stage 1 per-strategy override block。
# - enabled=false: 與 strategy_params_demo.toml [liquidation_cascade_fade].active=false 雙保險
# - max_concurrent_positions=2: BTC + ETH 各 1 倉位
# - stop_loss_max_pct_override=2.0: 單筆 fade 最大 SL 2%（緊 — cascade 反向直接出場避雙重 hit）
# - take_profit_max_pct_override=1.5: TP 對齊 strategy 內 take_profit_pct
# - trailing_activation_pct_override=0.8: 0.8% 浮盈啟動 trailing
# - trailing_distance_pct_override=0.4: trailing 距離 0.4%
[per_strategy.liquidation_cascade_fade]
enabled = false
max_concurrent_positions = 2
stop_loss_max_pct_override = 2.0
take_profit_max_pct_override = 1.5
take_profit_enforced_override = true
trailing_activation_pct_override = 0.8
trailing_distance_pct_override = 0.4
```

**Why tight SL 2%**:
- cascade fade thesis 期望 1-2% mean-revert；SL > 2% = thesis 失效（cascade 是 informed selling 非 panic）
- 對比 grid_trading / ma_crossover stop_loss_max_pct_override = 2.5（trend follow）；fade 策略 SL 更緊（thesis 失效快）
- 對齊 funding_short_v2 SL 3%（funding mean-revert 較慢）vs liquidation_cascade_fade SL 2%（cascade mean-revert 較快）

### §3.3 Position sizing

per memory `feedback_position_sizing` 3% risk/trade + Kelly：
- `default_qty = 1e9` sentinel triggers Kelly/risk sizing
- Kelly sizing 用 strategy edge estimate（cascade fade per-trade expected 1.5% TP × ~50% win rate vs 2% SL × ~50% loss rate → 期望 -0.25%）
  - **注意**：上述 baseline expected return 為負；strategy thesis 需 demo 14d 累積驗證 win_rate / avg_win / avg_loss empirical distribution
  - Sprint 2 demo 階段 W2-F MIT post-IMPL 必估算實證期望
- 3% account risk per trade × SL 2% → notional ≈ account_balance × 1.5（150% leverage on single position）
- max_concurrent_positions = 2 ⇒ total exposure ≤ 300% notional

---

## §4 5-Gate Auto Path Inheritance Contract（per CR-15）

### §4.1 IMPL-time invariants（same as funding_short_v2 spec §4.1）

| Gate | liquidation_cascade_fade inheritance | IMPL responsibility |
|---|---|---|
| **5-gate-A**: Python `live_reserved` | 不繞 | 外層 IntentProcessor 強制 |
| **5-gate-B**: Python Operator role | 不繞 | 同上 |
| **5-gate-C**: `OPENCLAW_ALLOW_MAINNET=1` | 不繞 | 同上 |
| **5-gate-D**: Valid secret slot | 不繞 | 同上 |
| **5-gate-E**: Signed `authorization.json` | 不繞 | 同上 |

**Strategy internal invariant**：
- `active = false` default in TOML（per §3.1）
- `enabled = false` default in risk_config（per §3.2）
- live entry path 必經 `IntentProcessor.submit_intent` → Guardian → Decision Lease → P1/P2 risk envelope

### §4.2 LAL inheritance（per ADR-0034）

- liquidation_cascade_fade 不引入新 LAL；經 LAL 1 intra-strategy reparam（threshold_usd / cooldown_ms / take_profit_pct 可 Strategist agent IPC tune）
- `active = false → true` 是 LAL 2 cross-strategy reweight；Sprint 2 demo 階段 operator 顯式 IPC active=true 才啟（**不**走 auto-activate path）

---

## §5 Liquidations Source Constraint（per ADR-0038 §Decision 1）

### §5.1 Self-hosted PG only — Bybit historical API 不依賴

per ADR-0038 §Decision 1：
- 規則：M11 nightly replay 所有 historical `market.*` query 限制到 self-hosted PG namespace
- **本 spec 對齊**：liquidation_cascade_fade runtime entry signal **不**走 historical query；只走 LiquidationPulsePanel snapshot（in-memory IPC slot）
- **本 spec 對齊**：14d demo accumulation evidence path（per §7）SQL 走 self-hosted `trading.fills` + `market.liquidations` table（既有 V095 schema）
- **本 spec 不違反**：完全不依賴 Bybit historical liquidations REST API（per BB push back: 該 API 不存在）

### §5.2 LiquidationPulsePanel 依賴契約

```rust
// liquidation_cascade_fade 依賴 surface.liquidation_pulse 提供 panel snapshot
// 若 panel 不可用（pre-warmup / WS revival fail）→ surface.liquidation_pulse = None
// strategy 必 fail-closed skip entry（per AlphaSurface 設計約束 §設計約束）

fn on_tick(&mut self, ctx, surface) -> Vec<StrategyAction> {
    // ... position state check ...

    // Liquidation panel must be available
    let panel = match surface.liquidation_pulse {
        Some(p) => p,
        None => return vec![],  // ← fail-closed: panel unavailable → skip
    };

    let pulse = match panel.pulse_for(sym) {
        Some(p) => p,
        None => return vec![],  // ← fail-closed: symbol not in cohort → skip
    };

    // pulse contains 5m window snapshot
    // event_count_5m, dominant_side, long_notional_5m, short_notional_5m, cluster_notional_5m
    // ...
}
```

**為什麼 fail-closed**：
- per AlphaSurface 設計約束（`src/rust/openclaw_core/src/alpha_surface.rs:592`）：「`surface.<field>` 為 None → fail-closed signal」
- liquidation cascade fade thesis 依賴 5m window cluster magnitude；panel 不可用時無法驗證 thesis → 不入場
- 對比 funding_short_v2 fail-closed for `ctx.funding_rate = None`（同 pattern）

---

## §6 Rust IMPL Hint — Strategy Struct Skeleton

### §6.1 File location

```
srv/rust/openclaw_engine/src/strategies/liquidation_cascade_fade/
  ├── mod.rs           # LiquidationCascadeFade struct + Strategy trait impl
  ├── params.rs        # LiquidationCascadeFadeParams + LiquidationCascadeFadeUpdateParams
  └── tests.rs         # unit tests + 1e-4 cross-language fixture
```

### §6.2 Struct skeleton

```rust
// srv/rust/openclaw_engine/src/strategies/liquidation_cascade_fade/mod.rs
//! liquidation_cascade_fade — microstructure liquidation cascade mean-revert fade
//! (Sprint 2 Alpha Tournament Candidate #4).
//!
//! MODULE_NOTE：
//!   入場：5m liquidation cluster > threshold + dominant_side != Mixed + event_count >= min_events
//!   出場：time-stop 60min / TP 1.5% / SL 2% / reverse cascade > 1.5x
//!   方向：fade against dominant cascade side
//!     - LongLiquidated → entry_is_long = true (price overshoot 下行 → fade buy)
//!     - ShortLiquidated → entry_is_long = false (price overshoot 上行 → fade sell)
//!     - Mixed → reject entry
//!   依賴：surface.liquidation_pulse（LiquidationPulsePanel；W-AUDIT-8a C1 既有 IMPL）
//!   per-symbol threshold：BTC $500k / ETH $300k 5m notional
//!   Stage 1 Demo BTC/ETH only；Stage 2+ 擴 SOLUSDT/BNBUSDT 依據 demo evidence

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{
    AlphaSourceTag, AlphaSurface, LiquidationPulse, LiquidationSide,
};

pub mod params;

#[cfg(test)]
mod tests;

pub use params::LiquidationCascadeFadeParams;

const LCF_MAKER_OFFSET_BPS: f64 = 1.0;
const LCF_MAKER_BUFFER_TICKS: u32 = 1;
const LCF_MAKER_TIMEOUT_MS: u64 = 45_000;

pub struct LiquidationCascadeFade {
    active: bool,
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,
    pub allowed_symbols: Vec<String>,
    /// per-symbol threshold map（key: symbol, value: 5m notional threshold USD）
    pub per_symbol_threshold: HashMap<String, f64>,
    pub default_threshold_usd: f64,
    pub min_events: u32,
    pub max_hold_ms: u64,
    pub take_profit_pct: f64,
    pub reverse_cascade_ratio: f64,
    default_qty: f64,
    /// 入場時 cascade notional 快照（用於 reverse cascade 判定 1.5x ratio）
    entry_notional: HashMap<String, f64>,
    prev_last_trade_ms: HashMap<String, u64>,
}

impl LiquidationCascadeFade {
    pub fn new() -> Self {
        let mut per_symbol = HashMap::new();
        per_symbol.insert("BTCUSDT".into(), 500_000.0);
        per_symbol.insert("ETHUSDT".into(), 300_000.0);
        Self {
            active: false,
            cooldown: TrendCooldown::new(1_800_000),  // 30min
            cooldown_ms: 1_800_000,
            allowed_symbols: vec!["BTCUSDT".into(), "ETHUSDT".into()],
            per_symbol_threshold: per_symbol,
            default_threshold_usd: 100_000.0,
            min_events: 3,
            max_hold_ms: 3_600_000,  // 60min
            take_profit_pct: 1.5,
            reverse_cascade_ratio: 1.5,
            default_qty: 1e9,
            entry_notional: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
        }
    }

    fn threshold_for(&self, symbol: &str) -> f64 {
        self.per_symbol_threshold
            .get(symbol)
            .copied()
            .unwrap_or(self.default_threshold_usd)
    }

    /// Entry gate check
    fn should_enter(&self, pulse: &LiquidationPulse, symbol: &str) -> Option<bool> {
        // Gate 2: dominant_notional > threshold
        let dominant_notional = pulse.long_notional_5m.max(pulse.short_notional_5m);
        if dominant_notional < self.threshold_for(symbol) {
            return None;
        }
        // Gate 3: event_count >= min_events
        if pulse.event_count_5m < self.min_events {
            return None;
        }
        // Gate 4: dominant_side != Mixed
        match pulse.dominant_side {
            LiquidationSide::LongLiquidated => Some(true),    // fade → long entry
            LiquidationSide::ShortLiquidated => Some(false),  // fade → short entry
            LiquidationSide::Mixed => None,                    // reject
        }
    }

    /// Exit decision
    fn should_exit(
        &self,
        symbol: &str,
        pulse: &LiquidationPulse,
        is_long_position: bool,
        entry_price: f64,
        current_price: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> Option<&'static str> {
        // 1. time-stop
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return Some("time_stop");
        }
        // 2. TP（per_strategy override 由 P1 強制；strategy 內亦判斷 early exit signal）
        let pnl_pct = if is_long_position {
            ((current_price - entry_price) / entry_price) * 100.0
        } else {
            ((entry_price - current_price) / entry_price) * 100.0
        };
        if pnl_pct >= self.take_profit_pct {
            return Some("take_profit");
        }
        // 3. reverse cascade detected
        let entry_n = self.entry_notional.get(symbol).copied().unwrap_or(0.0);
        let current_dominant = pulse.long_notional_5m.max(pulse.short_notional_5m);
        let expected_dominant_side = if is_long_position {
            LiquidationSide::LongLiquidated  // 入場時 long 被強平
        } else {
            LiquidationSide::ShortLiquidated
        };
        if pulse.dominant_side != expected_dominant_side
            && current_dominant > entry_n * self.reverse_cascade_ratio
        {
            return Some("reverse_cascade");
        }
        // 4. SL 由 P1 per_strategy stop_loss_max_pct_override 處理（strategy 內不再判定）
        None
    }

    fn snapshot_prev_cooldown(&mut self, sym: &str) {
        self.prev_last_trade_ms
            .insert(sym.to_string(), self.cooldown.last_ms(sym).unwrap_or(0));
    }

    // update_params / get_params / IPC schema 同 funding_arb pattern
}

impl Strategy for LiquidationCascadeFade {
    fn name(&self) -> &str {
        "liquidation_cascade_fade"
    }

    fn is_active(&self) -> bool {
        self.active
    }

    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// Tier 3 microstructure alpha source
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::LiquidationCascade];
        TAGS
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        let sym = ctx.symbol;
        let now_ms = ctx.timestamp_ms;

        // Stage 1 cohort gate
        if !self.allowed_symbols.iter().any(|s| s == sym) {
            return vec![];
        }

        // fail-closed: panel + pulse must be available
        let panel = match surface.liquidation_pulse {
            Some(p) => p,
            None => return vec![],
        };
        let pulse = match panel.pulse_for(sym) {
            Some(p) => p,
            None => return vec![],
        };

        // Position SSoT 判定（Option A-Lite 範式）
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            Some(pos) => {
                // Exit 分支
                if let Some(reason) = self.should_exit(
                    sym,
                    pulse,
                    pos.is_long,
                    pos.entry_price,
                    ctx.price,
                    now_ms,
                    pos.entry_ts_ms,
                ) {
                    self.snapshot_prev_cooldown(sym);
                    self.cooldown.record_signal(sym, now_ms);
                    self.entry_notional.remove(sym);
                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence: 0.8,
                        reason: format!("liquidation_cascade_fade_exit: {}", reason),
                    }];
                }
                return vec![];
            }
            None if ctx.position_state.is_some() => {
                return vec![];
            }
            None => {}
        }

        // Entry gate
        if !ctx.h0_allowed {
            return vec![];
        }
        if !self.cooldown.is_cooled_down(sym, now_ms) {
            return vec![];
        }

        let entry_is_long = match self.should_enter(pulse, sym) {
            Some(b) => b,
            None => return vec![],
        };

        // confidence scales with notional magnitude over threshold
        let dominant_notional = pulse.long_notional_5m.max(pulse.short_notional_5m);
        let threshold = self.threshold_for(sym);
        let magnitude_ratio = (dominant_notional / threshold).min(3.0);  // cap at 3x
        let confidence = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
            (magnitude_ratio / 3.0 * 0.5 + 0.4).clamp(0.4, 0.9),
        );

        let maker_inputs = MakerPriceInputs {
            last_price: ctx.price,
            best_bid: ctx.best_bid,
            best_ask: ctx.best_ask,
            tick_size: ctx.tick_size,
        };
        let limit_price = match compute_post_only_price(
            entry_is_long,
            maker_inputs,
            LCF_MAKER_OFFSET_BPS,
            LCF_MAKER_BUFFER_TICKS,
            self.name(),
            sym,
        ) {
            Some(price) => price,
            None => return vec![],
        };

        self.snapshot_prev_cooldown(sym);
        self.cooldown.record_signal(sym, now_ms);
        self.entry_notional.insert(sym.to_string(), dominant_notional);

        vec![StrategyAction::Open(OrderIntent::new_trade(
            sym.to_string(),
            entry_is_long,
            self.default_qty,
            confidence,
            self.name().into(),
            "limit".into(),
            Some(limit_price),
            None,
            None,
            Some(TimeInForce::PostOnly),
            Some(LCF_MAKER_TIMEOUT_MS),
        ))]
    }

    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
        self.entry_notional.remove(sym);
    }

    fn on_external_close(&mut self, symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        self.entry_notional.remove(symbol);
    }

    fn on_close_confirmed(&mut self, symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        self.entry_notional.remove(symbol);
    }

    // 其他 trait method 用 default no-op
}
```

### §6.3 StrategyFactory registration（registry.rs append）

```rust
// srv/rust/openclaw_engine/src/strategies/registry.rs — append after funding_short_v2 block
// liquidation_cascade_fade — Sprint 2 Alpha Tournament Candidate #4
let mut lcf = liquidation_cascade_fade::LiquidationCascadeFade::new();
lcf.cooldown_ms = p.liquidation_cascade_fade.cooldown_ms;
lcf.cooldown.set_duration(p.liquidation_cascade_fade.cooldown_ms);
lcf.allowed_symbols = p.liquidation_cascade_fade.allowed_symbols.clone();
lcf.default_threshold_usd = p.liquidation_cascade_fade.default_threshold_usd;
// per-symbol threshold map 從 TOML 建構（BTC + ETH 兩 key）
lcf.per_symbol_threshold.insert("BTCUSDT".into(), p.liquidation_cascade_fade.btc_threshold_usd);
lcf.per_symbol_threshold.insert("ETHUSDT".into(), p.liquidation_cascade_fade.eth_threshold_usd);
lcf.min_events = p.liquidation_cascade_fade.min_events;
lcf.max_hold_ms = p.liquidation_cascade_fade.max_hold_ms;
lcf.take_profit_pct = p.liquidation_cascade_fade.take_profit_pct;
lcf.reverse_cascade_ratio = p.liquidation_cascade_fade.reverse_cascade_ratio;
lcf.set_active(p.liquidation_cascade_fade.active);
strategies.push(Box::new(lcf));
```

### §6.4 strategies/params.rs append

```rust
// srv/rust/openclaw_engine/src/strategies/params.rs — append
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct LiquidationCascadeFadeParams {
    pub active: bool,
    pub cooldown_ms: u64,
    pub allowed_symbols: Vec<String>,
    pub default_threshold_usd: f64,
    pub btc_threshold_usd: f64,
    pub eth_threshold_usd: f64,
    pub min_events: u32,
    pub max_hold_ms: u64,
    pub take_profit_pct: f64,
    pub reverse_cascade_ratio: f64,
}

impl Default for LiquidationCascadeFadeParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: 1_800_000,
            allowed_symbols: vec!["BTCUSDT".into(), "ETHUSDT".into()],
            default_threshold_usd: 100_000.0,
            btc_threshold_usd: 500_000.0,
            eth_threshold_usd: 300_000.0,
            min_events: 3,
            max_hold_ms: 3_600_000,
            take_profit_pct: 1.5,
            reverse_cascade_ratio: 1.5,
        }
    }
}
```

### §6.5 WS subscription verification（LiquidationPulseAggregator wiring）

per `srv/rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs:4-8`：
- LiquidationPulseAggregator 接收 `PriceEventKind::Liquidation` events from ws_client/dispatch
- production WS subscription enabled per commit 0e8a8ae8（per BB C6 PROOF PASS notes）
- panel snapshot 寫入 LiquidationPulsePanelSlot（per `srv/rust/openclaw_engine/src/panel_aggregator/mod.rs:507`）
- step_4_5_dispatch.rs 注入 `surface.liquidation_pulse = panel_slot.snapshot()`

**Verification for IMPL**:
- W2-B IMPL 不需新增 WS subscription（panel aggregator 既有）
- W2-B 只需確認 `step_4_5_dispatch.rs` 已 inject `liquidation_pulse` 到 AlphaSurface（Phase B-REM-7 既有 wiring）
- 若 wiring 未 land → W2-B 需先補 inject path（依賴 Phase B-REM 既有 IMPL）

---

## §7 14d Demo Data Accumulation Hook（per CR-6 + AC-S2-A-2）

### §7.1 Attribution chain（per ADR-0025）

liquidation_cascade_fade fills 經 `trading.fills`：
- `strategy_name = "liquidation_cascade_fade"`
- `track = 'direct_exploit'`（per V101 strategy_track ENUM + ADR-0026：hand-coded Rust strategy 必 = `direct_exploit`，Track A bypass CPCV；非新 track 命名空間）
- `engine_mode IN ('demo', 'live_demo')`

**Empirical V101 ENUM verified**（2026-05-25 SSH read-only probe）：
```
SELECT enum_range(NULL::strategy_track);
=> {direct_exploit, asds_factory, baseline}
```
非 `alpha_microstructure_fade`（不存在 ENUM 命名空間）。

### §7.2 14d demo SQL bucket-split monitor

```sql
-- Sprint 2 W2-F QA 14d daily evidence accumulation
-- per AC-S2-A-2 minimum bar n_fills ≥ 30
WITH lcf_demo AS (
  SELECT
    DATE(filled_at AT TIME ZONE 'UTC') AS trade_date,
    symbol,
    COUNT(*) AS n_fills,
    AVG(net_pnl_bps) AS avg_net_bps,
    -- Wilson CI lower bound（z=1.96 for 95% CI）
    (AVG(net_pnl_bps) - 1.96 * STDDEV(net_pnl_bps) / SQRT(COUNT(*))) AS wilson_lower_bps
  FROM trading.fills
  WHERE strategy_name = 'liquidation_cascade_fade'
    AND engine_mode IN ('demo', 'live_demo')
    AND filled_at > NOW() - INTERVAL '14 days'
  GROUP BY trade_date, symbol
)
SELECT
  trade_date,
  SUM(n_fills) AS total_fills,
  AVG(avg_net_bps) AS avg_net_bps_overall,
  MIN(wilson_lower_bps) AS wilson_lower_overall_bps
FROM lcf_demo
GROUP BY trade_date
ORDER BY trade_date DESC;
```

### §7.3 對齊 market.liquidations evidence（per ADR-0038）

per ADR-0038 §Decision 1 + BB C6 PROOF PASS：
- `market.liquidations` 31,473 rows 已累積
- W2-F MIT post-IMPL audit 可走 self-hosted PG join 比對：
  ```sql
  -- liquidation_cascade_fade entry vs 同期 market.liquidations event 統計
  SELECT
    f.symbol,
    DATE_TRUNC('hour', f.filled_at) AS entry_hour,
    COUNT(*) AS lcf_entries,
    (SELECT SUM(qty * price) FROM market.liquidations l
     WHERE l.symbol = f.symbol
       AND l.ts BETWEEN f.filled_at - INTERVAL '5 minutes' AND f.filled_at) AS prior_5min_liq_notional
  FROM trading.fills f
  WHERE f.strategy_name = 'liquidation_cascade_fade'
    AND f.engine_mode IN ('demo', 'live_demo')
    AND f.filled_at > NOW() - INTERVAL '14 days'
  GROUP BY f.symbol, entry_hour
  ORDER BY entry_hour DESC;
  ```
- 驗證 thesis: entry hour 前 5min 的 market.liquidations notional 應顯著高於 baseline（threshold check empirical）

### §7.4 DRAFT writeback to V103 EXTEND hypotheses（per AC-S2-A-4）

**Schema 真相**（per V100 base + V103 EXTEND actual spec `srv/docs/execution_plan/2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`）：
- 目標 table = `learning.hypotheses`（**非** `learning.m4_hypotheses_extended` — 該 table 不存在）
- V103 EXTEND 6 column 為 ALTER ADD 到 `learning.hypotheses`：
  1. `hypothesis_source_module` (TEXT, 3 enum: `M4_AUTO`/`OPERATOR`/`HISTORIC`)
  2. `leakage_scan_pass` (BOOLEAN, DEFAULT FALSE)
  3. `bonferroni_corrected_p` (NUMERIC(10,8), [0,1])
  4. `replicability_score` (NUMERIC(5,4), [0,1])
  5. `decision_lease_draft_id` (UUID)
  6. `cowork_review_status` (TEXT, 4 enum: `NONE`/`PENDING`/`APPROVED`/`REJECTED`)

per CR-6 minimum bar 6 attribute（同 funding_short_v2 spec §7.3 mapping）：
- N ≥ 30 → `learning.hypotheses.min_sample_size`
- Bonferroni p < 0.05/K（K = 2 candidate → α = 0.025）→ V103 `bonferroni_corrected_p`
- effect size ≥ 0.2 → V103 `replicability_score` (composite)
- 6mo sub-period stability → V103 `replicability_score` (composite)
- leakage scan pass → V103 `leakage_scan_pass`
- cluster K silhouette → V103 `replicability_score` (composite)

W2-F MIT post-IMPL audit 寫 V103 EXTEND DRAFT row（**正確 schema**）：

```sql
INSERT INTO learning.hypotheses (
  -- V100 base required column
  strategy_name,
  state,                       -- 'draft' Sprint 2
  hypothesis_text,
  null_hypothesis,
  acceptance_criteria,
  min_sample_size,             -- N (per CR-6 #1)
  max_drawdown_pct,
  -- V103 EXTEND 6 column
  hypothesis_source_module,    -- 'M4_AUTO'
  leakage_scan_pass,           -- per CR-6 #5
  bonferroni_corrected_p,      -- per CR-6 #2; K=2 → α=0.025
  replicability_score,         -- composite (#3 + #4 + #6)
  decision_lease_draft_id,     -- STRATEGY_TRIAL lease UUID
  cowork_review_status         -- 'NONE'
) VALUES (
  'liquidation_cascade_fade',
  'draft',
  'Liquidation cascade > $500k 5m + dominant_side fade entry (Sprint 2 Alpha Tournament Candidate #4)',
  'Mean net_pnl_bps in demo over 14d <= 0',
  '14d demo avg_net_pnl_bps > 5 + Wilson CI lower > 0 + n_fills ≥ 30',
  /* n_fills */ ?::int,
  2.0,                         -- per_strategy SL 2% 對齊 strategy_params
  'M4_AUTO',
  /* leakage_scan_pass */ TRUE,
  /* bonferroni p */ ?::numeric(10,8),
  /* replicability composite */ ?::numeric(5,4),
  /* lease_draft_id */ ?::uuid,
  'NONE'
);
```

**W2-B E1 IMPL 必 honor**：
- 不可寫 `learning.m4_hypotheses_extended`（該 table 不存在）
- 不可寫 W1-A 原 spec 虛構 column（`attribute_n` / `attribute_p_value` / `attribute_effect_size` / `attribute_subperiod_stable` / `attribute_graveyard_flag` / `attribute_cluster_silhouette`）
- 必走 V100 base + V103 EXTEND actual 6 column
- W2-E E2 review grep `m4_hypotheses_extended` / `attribute_n` / `attribute_p_value` 必 0 hit

---

## §8 Acceptance Criteria

| AC | 內容 | Verification path |
|---|---|---|
| **AC-S2-A-C4-1** | liquidation_cascade_fade strategy struct land in Rust + StrategyFactory registered | W2-B E1 IMPL DONE + cargo test |
| **AC-S2-A-C4-2** | `declared_alpha_sources` 包含 `AlphaSourceTag::LiquidationCascade` | unit test |
| **AC-S2-A-C4-3** | `surface.liquidation_pulse = None` → fail-closed skip entry | unit test with None panel |
| **AC-S2-A-C4-4** | `dominant_side == Mixed` → reject entry（無 directional thesis） | unit test |
| **AC-S2-A-C4-5** | per-symbol threshold BTC $500k / ETH $300k；non-cohort symbol → default_threshold $100k | unit test |
| **AC-S2-A-C4-6** | should_enter / should_exit 各 gate 獨立觸發測試（4 entry + 4 exit conditions） | unit test |
| **AC-S2-A-C4-7** | self-fills filter Stage 1 stub；Sprint 3+ V109 anomaly_events wire 真正 filter | spec note + Stage 1 stub returns false |
| **AC-S2-A-C4-8** | 14d demo accumulation hook works（fills 寫入 + bucket-split SQL fire） | W2-F QA 14d empirical |
| **AC-S2-A-C4-9** | n_fills ≥ 30 over 14d（per CR-6 minimum bar） | Sprint 2 末 W3-A review |
| **AC-S2-A-C4-10** | 14d avg_net > 5bps + Wilson CI lower > 0（Sprint 3+ verdict path） | Sprint 3+ Stage 0R verdict |
| **AC-S2-A-C4-11** | DRAFT writeback to V103 hypotheses | W2-F MIT audit |
| **AC-S2-A-C4-12** | 5-gate 0 觸碰 | E2 review grep |

---

## §9 對抗式 Review Focus（W2-E E2 + W2-F MIT post-IMPL audit 重點）

1. **Look-ahead bias scan** — liquidation_cascade_fade 不引入 `rolling(N).max()` pattern；若 IMPL 加入 dynamic threshold via rolling z-score → 強制並列 leak-free shift(1) 對比（per memory `feedback_indicator_lookahead_bias`）
2. **Self-fills 剔除 defensive layer** — `is_self_origin_event` Stage 1 stub returns false；Sprint 3+ V109 wire 加 hard filter；W2-E E2 確認 stub 不誤判 true（誤判 true 會錯失所有合法 cascade entry）
3. **5-gate inheritance integrity** — diff grep `execution_state|execution_authority|live_execution_allowed|decision_lease_emitted|max_retries|live_reserved`；0 hit 預期
4. **黑名單 method 0 hit** — `grep -nri 'hmm|markov_switching|garch' src/strategies/liquidation_cascade_fade/` 必 0 hit（per ADR-0036 Decision 1）
5. **Liquidations source compliance** — strategy runtime 只走 `surface.liquidation_pulse`（in-memory IPC slot）；不走 Bybit historical REST；對齊 ADR-0038 §Decision 1
6. **fade direction logic** — `LongLiquidated → entry_is_long=true` / `ShortLiquidated → entry_is_long=false` 為核心 thesis；W2-E E2 unit test 此映射不可寫反（寫反 = alpha 反向 = trade loss）
7. **per-symbol threshold cohort** — BTC $500k / ETH $300k hardcoded Stage 1；non-cohort fallback $100k；W2-E E2 確認 cohort gate 在 allowed_symbols filter 後立即生效（防 ALT 走 default threshold）
8. **Cross-language fixture harness 1e-4 tolerance**（per H-18）— Python 對應測試 fixture 必 1e-4 對齊 Rust output

---

## §10 References

- dispatch packet: `srv/docs/execution_plan/2026-05-25--sprint_2_business_dispatch_packet.md` §2.2 candidate #4
- memory: `feedback_indicator_lookahead_bias` (rolling shift(1) 強制) / `feedback_position_sizing` (3% risk/trade) / `feedback_demo_loose_live_strict_policy`
- ADR-0036 §Decision 1 HMM/Markov-switching/GARCH 黑名單
- ADR-0038 §Decision 1 M11 self-hosted PG historical source（liquidations source 限制）
- ADR-0034 Decision Lease LAL
- ADR-0024-lite Cowork operator-assistant
- ADR-0005 engine_mode tag
- ADR-0029 trade tape and orderbook L2 storage policy（market.liquidations V095 既有 schema 基礎）
- v5.8 §11.5 5-Gate Auto Path Inheritance Hard Invariant
- CR-15 5-gate auto path inheritance contract
- CR-6 M4 hypothesis miner minimum bar 6 attribute
- existing infrastructure: `srv/rust/openclaw_engine/src/panel_aggregator/liquidation_pulse.rs` (LiquidationPulseAggregator W-AUDIT-8a C1)
- existing infrastructure: `srv/rust/openclaw_core/src/alpha_surface.rs:401-461` (LiquidationPulse + LiquidationPulsePanel schema)
- BB C6 PROOF PASS: `market.liquidations` 31,473 rows accumulated (per memory `project_decision_outcomes_not_dead`)
- production WS revival: commit 0e8a8ae8 (allLiquidation subscription enabled)
- existing strategy IMPL reference: `srv/rust/openclaw_engine/src/strategies/funding_arb.rs` (Option A-Lite Strategy trait pattern)
- skills: `quant-strategy-design`, `math-model-audit`, `crypto-microstructure-knowledge`

---

## §11 Conclusion

**liquidation_cascade_fade IMPL-ready verdict**: **READY for W2-B E1 IMPL**

- 4 conditions all met: algorithm spec ✅ / TOML spec ✅ / Rust struct skeleton ✅ / AC + adversarial review focus ✅
- 不踩 look-ahead bias 陷阱（pulse 5m window 為 aggregator 內部 trim，**非** entry signal rolling stat；entry 直接閾值比較）
- 不繞 5-gate / Decision Lease（per §4.1 + active=false default + per_strategy override 雙保險）
- 不違反 ADR-0038 §Decision 1（strategy runtime 走 in-memory panel；不走 Bybit historical REST）
- 不踩 ADR-0036 黑名單（無 HMM / GARCH 依賴）
- 上游 infrastructure 已 land：LiquidationPulseAggregator + LiquidationPulsePanel + WS subscription（W-AUDIT-8a C1 + commit 0e8a8ae8）
- self-fills 剔除 defensive layer 預留（Stage 1 stub；Sprint 3+ V109 wire）

**派發 readiness**：W2-B E1 sub-agent 可直接 IMPL；W2-E E2 review 對抗式檢查 8 點 + W2-F MIT post-IMPL audit 14d empirical evidence + market.liquidations join SQL 驗證 thesis。

---

**Report END**

PA SPEC DONE: spec path: `/Users/ncyu/Projects/TradeBot/srv/docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md`

---

## Changelog
- 2026-05-25 v1.1: inline amend by PA per W2-A 2 CRITICAL catch + PM Option A decision
  - §7.1 strategy_track `'alpha_microstructure_fade'` → `'direct_exploit'` (per V101 ENUM empirical verified `{direct_exploit, asds_factory, baseline}` + ADR-0026 hand-coded Rust = direct_exploit)
  - §7.4 INSERT target table `learning.m4_hypotheses_extended` → `learning.hypotheses` (V100 base + V103 EXTEND actual schema per `2026-05-21--v103_extend_m4_hypothesis_columns_schema_spec.md`)
  - §7.4 INSERT 6 column 名稱 (`attribute_n` / `attribute_p_value` / `attribute_effect_size` / `attribute_subperiod_stable` / `attribute_graveyard_flag` / `attribute_cluster_silhouette`) → V103 EXTEND 6 real column (`hypothesis_source_module` / `leakage_scan_pass` / `bonferroni_corrected_p` / `replicability_score` / `decision_lease_draft_id` / `cowork_review_status`)
  - 加 W2-E E2 review grep guard: `m4_hypotheses_extended` / `attribute_n` / `attribute_p_value` / `alpha_microstructure_fade` 必 0 hit
  - W2-A finalize report path: `srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md`
  - W2-B E1 IMPL dispatch verdict: NEEDS-MORE-DESIGN → DISPATCH-READY

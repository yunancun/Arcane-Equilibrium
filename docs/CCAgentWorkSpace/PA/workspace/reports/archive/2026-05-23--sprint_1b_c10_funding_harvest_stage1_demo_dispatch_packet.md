---
report: PA — Sprint 1B Pending 3.1 C10 funding harvest Stage 1 Demo dispatch packet
date: 2026-05-23
author: PA (Project Architect)
phase: Sprint 1B late · Pending 3.1 dispatch design
status: DISPATCH-PACKET-READY / NOT-YET-DISPATCHED
parent reports:
  - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-23--sprint_1b_remaining_3_sections_audit.md §1 §4.1
  - srv/docs/CCAgentWorkSpace/FA/workspace/reports/2026-05-21--v57_business_consolidation.md §2 (C10) + §3 (Stage gate) + §6 (5×Stage matrix) + §7 (capital flow)
  - srv/docs/CCAgentWorkSpace/BB/workspace/reports/2026-05-21--v57_c4_c5_c6_bybit_verdict.md Part A (Earn) — for spot-leg paper emulation precedent
  - srv/docs/governance_dev/amendments/2026-05-15--AMD-2026-05-15-01-canary-rebase-replay-preflight-demo-micro-canary.md §3 §4 §7
  - srv/docs/adr/0018-funding-arb-v2-deprecation-watch.md (funding_arb V2 retire ≠ C10 new strategy)
  - srv/docs/execution_plan/2026-05-21--sprint_1a_dispatch_packet.md §1 (Stage matrix scheduling)
existing code touchpoints:
  - srv/rust/openclaw_engine/src/strategies/mod.rs (Strategy trait / StrategyAction / pub mod 註冊點)
  - srv/rust/openclaw_engine/src/strategies/registry.rs (StrategyFactory::create_with_params 唯一入口)
  - srv/rust/openclaw_engine/src/strategies/bb_breakout/mod.rs (Rust strategy 範式 1000 LOC + sub-module split)
  - srv/rust/openclaw_engine/src/strategies/funding_arb.rs (V2 dormant marker 保留)
  - srv/rust/openclaw_engine/src/intent_processor/mod.rs §60 (OrderIntent 結構)
  - srv/rust/openclaw_engine/src/paper_state.rs (PaperState SSoT / owner_strategy gate)
  - srv/settings/strategy_params_demo.toml line 165-173 ([funding_arb] block 範式)
  - srv/settings/risk_control_rules/risk_config_demo.toml (cost_gate + min_n_trades_for_block 範式)
  - srv/helper_scripts/canary/replay_runner.py (既有 replay engine 擴展點)
not in scope:
  - 不 IMPL Rust strategy code
  - 不改 既有 funding_arb.rs / bb_breakout/ / intent_processor
  - 不 commit
  - 不派下游 sub-agent（dispatch 由 PM 拍板後執行）
  - Stage 4 LIVE spot order 接 IntentProcessor 路徑 → Sprint 5+ cascade window，本 packet 僅留 spec stub
---

# PA — Sprint 1B Pending 3.1 C10 funding harvest Stage 1 Demo dispatch packet

## §0 TL;DR

C10 funding harvest 是 v5.7 §6 5-strategy roster 第 1 條 Sprint 1B-deployable strategy。Stage 1 Demo gate 為 `1 strategy × 1 symbol (BTCUSDT) × Environment::Demo × 7d` per AMD-2026-05-15-01 §4.1。

**核心設計**：
- 新建 `rust/openclaw_engine/src/strategies/funding_harvest/` module（與既有 `bb_breakout/` 結構對齊；保留 `funding_arb.rs` dormant marker 不動）
- delta-neutral 二腿：perp short BTCUSDT（Bybit demo perp 真實 fill）+ spot long BTCUSDT（demo endpoint 不支援 spot lending → paper-only synthetic accounting）
- 入場：annualized funding rate > 5% AND basis_pct < 0.5%（v5.7 §2 C10 + entry_basis_ratio 0.8 safety）
- 平倉：annualized funding < 2% OR |basis_pct| drift > 0.5% OR 72h max hold
- size：Stage 1 cap $100 absolute（per FA §6 Stage 1 matrix），perp matched notional 1:1 hedge
- rebalance：每 2h tick 檢查 delta drift > 2% → 重新對沖
- 異常退出：D2 portfolio cum loss trip / SM-04 escalate L3 / `[55]` fill-lineage invariant FAIL / replay-vs-live PnL 偏離 > 5% → demote Stage 0

**dispatch readiness**：READY-TO-DISPATCH（不阻塞 Sprint 4+ §4.1.1 base table audit；可即刻並行）。

**effort estimate**：PA spec 8-12 hr + E1 IMPL 18-26 hr + Stage 0R replay harness 8-12 hr + risk_config TOML 1-2 hr + E2/E4/QA/PM 5-7 hr = **41-62 hr core / wall-clock 3-4 day with 3-5 parallel sub-agents**。

---

## §1 C10 spec + delta-neutral 數學原理

### §1.1 業務目標

對 BTCUSDT 永續合約資金費率高位（annualized > 5%）的時段做 funding capture：
- spot long BTCUSDT 收 spot price exposure
- perp short BTCUSDT matched notional 對沖 price exposure，同時收取資金費率（funding 正 = 多方付空方）
- 理論上 delta = (spot_qty × spot_price) - (perp_qty × perp_price) ≈ 0 → price 波動 P&L 互抵，淨收益 = 累積 funding payment - 雙腿 fee - basis drift loss

### §1.2 delta-neutral 數學

**理想 delta-neutral 條件**：
```
spot_notional ≈ perp_notional
spot_qty × spot_price ≈ perp_qty × perp_price
```

**漂移容忍**：
- 開倉時 `hedge_ratio = perp_qty / spot_qty = 1.0`（matched notional）
- 隨時間 spot price 與 perp price 略偏（basis），但二者高度相關 → delta drift 可控
- 監控 `delta_pct = abs(spot_notional - perp_notional) / spot_notional`，> 2% → rebalance trigger

**funding 收益 vs cost trade-off**：
```
net_edge_bps_per_period = (funding_rate × 10000) - amortized_total_cost_bps
amortized_total_cost_bps = total_cost_bps / expected_periods
total_cost_bps = perp_fee_bps (11) + spot_fee_bps (20) + slippage_bps (3) + basis_drift_loss_bps (~3) ≈ 37 bps
expected_periods = 3.0 (3 個 8h funding window，即 24h 內預期填倉)
```

入場條件 `compute_edge(funding_rate) > 0` 即 `funding_rate × 10000 > amortized_total_cost_bps`：
```
funding_rate > 37 / 3 / 10000 ≈ 0.00123 (per 8h period)
annualized > 0.00123 × 3 × 365 ≈ 1.35  (= 135% APR 連續高 funding)
```

但 v5.7 §2 entry threshold = annualized > 5%（即 `funding_rate per 8h > 0.0114%`，遠低於 break-even），因此實際 break-even 條件 = `funding_rate > 0.00123 per 8h` ≈ annualized 134%；現實中 annualized 5-30% 區間單 8h funding payment 攤銷不過 cost ⇒ **需多 period 累積攤平 fee**。

**Stage 1 Demo 7d window 預期 funding event 數**：BTCUSDT 8h funding cycle × 21 events / 7d；annualized > 5% 滿足 funding/period > 0.000114 entry threshold 約 30-50% 時段 ≈ 6-10 入場機會 ⇒ Stage 1 Demo `fills ≥ 5` gate 可達。

### §1.3 入場條件（完整）

per FA §2 C10 + 既有 `funding_arb.rs` 範式：

| Condition | Threshold | Source |
|---|---|---|
| Annualized funding rate | > 5% (即 `funding_rate per 8h > 0.0001141`) | v5.7 §2 + FA §2 |
| Cost-edge guard | `funding_rate.abs() > total_cost_bps / expected_periods / 10000` (即 net edge > 0) | 既有 funding_arb compute_edge() 範式 |
| Basis pct | `abs(perp_price / spot_price - 1) × 100 < max_basis_pct × entry_basis_ratio` (= 0.5 × 0.8 = 0.4%) | v5.7 §2 + 既有 funding_arb entry_basis_ratio |
| Funding direction | funding > 0 (預期收 funding) → spot LONG + perp SHORT | v5.7 §2 delta-neutral 描述 |
| Spot price WS freshness | last update < 5s | ARCH-04 freshness gate |
| Perp price WS freshness | last update < 5s | ARCH-04 freshness gate |
| Funding rate WS freshness | last snapshot < 8h × 1.5 = 12h | Bybit 8h funding cycle |
| Position cap | 當前 funding_harvest 倉位數 < 1（Stage 1 限定 1 symbol = BTCUSDT） | AMD-2026-05-15-01 §4.1 |
| Cooldown | 上次 funding_harvest 入場/平倉 > 1h | 既有 funding_arb cooldown_ms 範式 |
| `eligible_for_demo_canary=true` | Stage 0R replay preflight PASS | AMD §3.2 |
| size cap | new_position_notional ≤ $100 absolute | Stage 1 matrix |

### §1.4 平倉條件（完整）

per v5.7 §2 + AMD §4.4 rollback：

| Condition | Trigger | Action |
|---|---|---|
| Funding decay | annualized funding < 2% (即 `funding_rate per 8h < 0.0000457`) | Close both legs (perp + spot synthetic) |
| Basis drift | `abs(perp_price / spot_price - 1) × 100 > 0.5%` | Close both legs |
| Max hold | now_ms - entry_ms > 72h | Close both legs |
| Funding flip | funding_rate < 0 (反向) | Close both legs |
| External close | external risk-close on perp leg → on_external_close hook | Close synthetic spot leg + clear strategy state |
| SM-04 escalate ≥ L3 | governance escalation | demote Stage 0 + halt new entries |
| Replay-vs-live PnL drift | runtime PnL vs Stage 0R replay baseline 偏離 > 5% | strategy demote + 24h cooldown |
| `[55]` fill-lineage FAIL | invariant breach | rollback per AMD §4.4 |

### §1.5 rebalance 機制

每 2h tick：
```
if (delta_pct > 2.0%) {
    // 不開新單，只調整既有 spot leg synthetic accounting 跟隨 perp leg
    sync_spot_leg_notional(target = perp_leg_notional);
    log(strategy="funding_harvest", action="rebalance", delta_pct=...);
}
```

Stage 1 不做 perp leg 加減倉（避免被誤判 new entry 過 governance gate）；只調整 synthetic spot leg book-keeping。

---

## §2 strategies/funding_harvest/ Rust module 設計

### §2.1 directory layout（與 bb_breakout/ 對齊）

```
rust/openclaw_engine/src/strategies/funding_harvest/
├── mod.rs               # Strategy trait impl + on_tick core (~400 LOC)
├── params.rs            # FundingHarvestParams + StrategyParams impl + ranges + validate (~150 LOC)
├── runtime_params.rs    # update_params / get_params IPC hook (~80 LOC)
├── synthetic_spot.rs    # spot leg paper-only synthetic accounting state machine (~200 LOC)
├── tests.rs             # core entry/exit + basis math + delta drift (~250 LOC)
└── tests_synthetic.rs   # synthetic spot leg state machine 邊界 (~150 LOC)
```

**Total ~1230 LOC**（拆 4 主檔 + 2 測試檔；每檔 ≤ 800 soft warn / 不超 1200 hard cap）。

### §2.2 mod.rs — FundingHarvest struct + Strategy trait impl

```rust
//! C10 funding harvest 策略 — delta-neutral spot long + perp short matched notional。
//! per v5.7 §2 + AMD-2026-05-15-01 + FA §6 Stage 1 Demo matrix。
//!
//! 與既有 funding_arb V2（directional, ADR-0018 dormant retire）並列：
//!   - funding_arb 保留為 R-02 重設計 slot marker，active=false 三環境鎖死
//!   - funding_harvest 為新策略，Stage 0R 通過後 demo Stage 1 開啟
//!
//! Stage 1 Demo 限定：
//!   - 1 symbol = BTCUSDT
//!   - size cap $100 absolute
//!   - spot leg = synthetic_spot::SyntheticSpotLedger（paper-only；Bybit demo 不支援 spot lending）
//!   - perp leg = Bybit demo perp 真實 fill（既有 IntentProcessor + Guardian + Decision Lease 全經過）

use std::collections::HashMap;
use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::TrendCooldown;
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

mod params;
mod runtime_params;
mod synthetic_spot;

#[cfg(test)]
mod tests;
#[cfg(test)]
mod tests_synthetic;

pub use params::{FundingHarvestParams};
use params::{
    DEFAULT_FUNDING_THRESHOLD_ANNUALIZED, DEFAULT_FUNDING_EXIT_ANNUALIZED,
    DEFAULT_MAX_BASIS_PCT, DEFAULT_ENTRY_BASIS_RATIO, DEFAULT_MAX_HOLD_MS,
    DEFAULT_TOTAL_COST_BPS, DEFAULT_EXPECTED_PERIODS,
    DEFAULT_REBALANCE_CHECK_MS, DEFAULT_DELTA_DRIFT_THRESHOLD,
    DEFAULT_POSITION_CAP_USD,
};

pub struct FundingHarvest {
    active: bool,
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,
    /// Stage 1 Demo BTCUSDT only；其他 symbol 直接 skip。
    pub allowed_symbols: Vec<String>,
    pub funding_threshold_annualized: f64,   // 0.05 = 5%
    pub funding_exit_annualized: f64,        // 0.02 = 2%
    pub max_basis_pct: f64,                  // 0.5
    pub entry_basis_ratio: f64,              // 0.8 (entry 用 0.5 × 0.8 = 0.4% gate)
    pub max_hold_ms: u64,                    // 72h
    pub total_cost_bps: f64,                 // 37 (perp+spot+slippage+basis_drift)
    pub expected_periods: f64,               // 3.0
    pub rebalance_check_ms: u64,             // 2h
    pub delta_drift_threshold: f64,          // 0.02 = 2%
    pub position_cap_usd: f64,               // $100 Stage 1
    /// 每 symbol synthetic spot ledger（Stage 1 只 BTCUSDT 一條）。
    pub(crate) synthetic_spot:
        HashMap<String, synthetic_spot::SyntheticSpotLedger>,
    /// 每 symbol entry timestamp（per paper_state.entry_ts_ms 但本地快照避 lookup）。
    pub(crate) entry_ms: HashMap<String, u64>,
    /// 每 symbol last rebalance check timestamp。
    pub(crate) last_rebalance_check_ms: HashMap<String, u64>,
    /// rejection rollback 用的 cooldown 快照（既有 funding_arb 範式）。
    prev_last_trade_ms: HashMap<String, u64>,
}

impl FundingHarvest {
    pub fn new() -> Self {
        Self {
            active: false,  // 默認 OFF；TOML 或 IPC active=true 開啟
            cooldown: TrendCooldown::new(3_600_000),
            cooldown_ms: 3_600_000,
            allowed_symbols: vec!["BTCUSDT".to_string()],
            funding_threshold_annualized: DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            funding_exit_annualized: DEFAULT_FUNDING_EXIT_ANNUALIZED,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            rebalance_check_ms: DEFAULT_REBALANCE_CHECK_MS,
            delta_drift_threshold: DEFAULT_DELTA_DRIFT_THRESHOLD,
            position_cap_usd: DEFAULT_POSITION_CAP_USD,
            synthetic_spot: HashMap::new(),
            entry_ms: HashMap::new(),
            last_rebalance_check_ms: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
        }
    }

    /// 將 8h funding_rate 折算 annualized。
    /// per Bybit V5 funding cycle = 3 × 8h windows / day × 365 days.
    fn annualized_funding(funding_rate_8h: f64) -> f64 {
        funding_rate_8h * 3.0 * 365.0
    }

    fn compute_basis_pct(perp_price: f64, spot_price: f64) -> f64 {
        if spot_price > 0.0 {
            ((perp_price / spot_price) - 1.0).abs() * 100.0
        } else {
            f64::MAX  // 缺 spot price → fail-closed (skip entry)
        }
    }

    fn compute_net_edge_bps_per_period(&self, funding_rate_8h: f64) -> f64 {
        let amortized_cost = self.total_cost_bps / self.expected_periods;
        funding_rate_8h.abs() * 10_000.0 - amortized_cost
    }

    fn should_enter(
        &self,
        funding_rate_8h: f64,
        basis_pct: f64,
    ) -> bool {
        let annualized = Self::annualized_funding(funding_rate_8h);
        annualized > self.funding_threshold_annualized
            && self.compute_net_edge_bps_per_period(funding_rate_8h) > 0.0
            && basis_pct < self.max_basis_pct * self.entry_basis_ratio
            && funding_rate_8h > 0.0  // funding 正 = perp 多方付空方 → 我們 spot long + perp short
    }

    fn should_exit(
        &self,
        funding_rate_8h: f64,
        basis_pct: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> bool {
        let annualized = Self::annualized_funding(funding_rate_8h);
        // Funding decay 或反向
        if annualized < self.funding_exit_annualized || funding_rate_8h < 0.0 {
            return true;
        }
        // Basis drift
        if basis_pct > self.max_basis_pct {
            return true;
        }
        // Max hold
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return true;
        }
        false
    }
}

impl Strategy for FundingHarvest {
    fn name(&self) -> &str { "funding_harvest" }
    fn is_active(&self) -> bool { self.active }
    fn set_active(&mut self, active: bool) { self.active = active; }
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::FundingSkew, AlphaSourceTag::Basis];
        TAGS
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if !self.active { return vec![]; }

        let sym = ctx.symbol;
        // Stage 1 Demo: only BTCUSDT
        if !self.allowed_symbols.iter().any(|s| s.as_str() == sym) {
            return vec![];
        }

        // 必有 funding_rate + index_price (spot proxy) + perp price
        let funding_rate = match ctx.funding_rate { Some(f) => f, None => return vec![] };
        let perp_price = ctx.last_price;
        let spot_price = match ctx.index_price { Some(p) => p, None => return vec![] };
        let basis_pct = Self::compute_basis_pct(perp_price, spot_price);

        // 是否已持倉（owner_strategy gate per W7-2 範式）
        let pos = ctx.position_state.position(sym);
        let has_position = pos.map(|p| p.owner_strategy == self.name()).unwrap_or(false);

        if has_position {
            // 平倉判斷
            let entry_ms = self.entry_ms.get(sym).copied().unwrap_or(0);
            if self.should_exit(funding_rate, basis_pct, ctx.timestamp_ms, entry_ms) {
                // Close perp leg via StrategyAction::Close（lightweight path）
                // synthetic spot leg 同步在 on_close_confirmed hook 中關閉
                return vec![StrategyAction::Close {
                    symbol: sym.to_string(),
                    confidence: 0.8,
                    reason: format!(
                        "funding_harvest_exit: funding={:.6} basis={:.3}% hold_ms={}",
                        funding_rate, basis_pct,
                        ctx.timestamp_ms.saturating_sub(entry_ms)
                    ),
                }];
            }
            // 既有倉位 + 不平倉 → 檢查 rebalance（2h tick）
            let last_check = self.last_rebalance_check_ms.get(sym).copied().unwrap_or(0);
            if ctx.timestamp_ms.saturating_sub(last_check) > self.rebalance_check_ms {
                // synthetic_spot.rebalance(perp_notional)（內部 mutate；無 StrategyAction emit）
                if let Some(ledger) = self.synthetic_spot.get_mut(sym) {
                    if let Some(p) = pos {
                        ledger.rebalance(
                            p.qty * p.entry_price,
                            spot_price,
                            ctx.timestamp_ms,
                        );
                    }
                }
                self.last_rebalance_check_ms.insert(sym.to_string(), ctx.timestamp_ms);
            }
            return vec![];
        }

        // 無倉位 → 入場判斷
        if !self.cooldown.is_cooled_down(sym, ctx.timestamp_ms) {
            return vec![];
        }
        if !self.should_enter(funding_rate, basis_pct) {
            return vec![];
        }

        // 入場：perp SHORT BTCUSDT (real demo fill)，synthetic spot LONG (paper-only)
        // size = $100 cap / perp_price
        let qty_perp = self.position_cap_usd / perp_price;
        let intent = OrderIntent {
            symbol: sym.to_string(),
            is_long: false,  // perp SHORT
            qty: qty_perp,
            confidence: 0.7,
            strategy: self.name().to_string(),
            order_type: "market".to_string(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        };
        // synthetic spot leg 在 on_fill hook 開啟（fill confirmed 後才寫 ledger）
        self.cooldown.record_signal(sym, ctx.timestamp_ms);
        info!(
            strategy = "funding_harvest",
            symbol = sym,
            funding_rate, basis_pct,
            qty_perp,
            "entry intent emitted (perp short + synthetic spot long pending fill)"
        );
        vec![StrategyAction::Open(intent)]
    }

    fn on_fill(&mut self, intent: &OrderIntent, fill: &openclaw_core::execution::FillResult) {
        // perp leg 真實 fill → 開 synthetic spot leg
        let sym = &intent.symbol;
        let now_ms = fill.fill_ts_ms;  // FillResult::fill_ts_ms
        let perp_notional = fill.fill_qty * fill.fill_price;
        let mut ledger = synthetic_spot::SyntheticSpotLedger::new();
        // spot leg LONG matched notional；用 fill_price 當 spot 近似（demo 期間驗 BB consensus）
        // Stage 4 LIVE 升級時，spot leg 走 IntentProcessor real spot order（Sprint 5+ cascade）
        ledger.open_long(perp_notional, fill.fill_price, now_ms);
        self.synthetic_spot.insert(sym.to_string(), ledger);
        self.entry_ms.insert(sym.to_string(), now_ms);
        self.last_rebalance_check_ms.insert(sym.to_string(), now_ms);
    }

    fn on_external_close(&mut self, symbol: &str) {
        // 風控止損 / SM-04 escalate 強制平 perp → 同步清 synthetic spot leg
        self.synthetic_spot.remove(symbol);
        self.entry_ms.remove(symbol);
        self.last_rebalance_check_ms.remove(symbol);
    }

    fn on_close_confirmed(&mut self, symbol: &str) {
        // 策略自發平倉成功 → 清 synthetic spot leg
        // 必同時將 synthetic spot leg PnL realize 寫 attribution 鏈
        if let Some(mut ledger) = self.synthetic_spot.remove(symbol) {
            ledger.close(/* spot_price_at_close */);
            // log + write attribution row（透過 ctx 在 on_tick 內已寫 trading.fills.track）
        }
        self.entry_ms.remove(symbol);
        self.last_rebalance_check_ms.remove(symbol);
    }

    fn import_positions(&mut self, paper_state: &crate::paper_state::PaperState) {
        for pos in paper_state.positions() {
            if pos.owner_strategy == self.name() {
                let mut ledger = synthetic_spot::SyntheticSpotLedger::new();
                ledger.open_long(pos.qty * pos.entry_price, pos.entry_price, pos.entry_ts_ms);
                self.synthetic_spot.insert(pos.symbol.clone(), ledger);
                self.entry_ms.insert(pos.symbol.clone(), pos.entry_ts_ms);
                self.last_rebalance_check_ms.insert(pos.symbol.clone(), pos.entry_ts_ms);
            }
        }
    }

    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        // 既有 funding_arb 範式：cooldown rollback
        let sym = &intent.symbol;
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.cooldown.clear(sym); }
            else { self.cooldown.record_signal(sym, ts); }
        }
    }

    // Phase 3a runtime tuning hooks → 在 runtime_params.rs
    // ...
}
```

### §2.3 funding_harvest vs funding_arb 對比表

| 維度 | funding_arb V2 (dormant) | funding_harvest (new) |
|---|---|---|
| 設計 | directional single-leg perp | delta-neutral spot + perp |
| 二腿 | 否（perp only）| 是（perp real + spot synthetic）|
| ADR | ADR-0018 retire | new (本 packet design) |
| TOML key | `[funding_arb]` | `[funding_harvest]` |
| Strategy.name() | "funding_arb" | "funding_harvest" |
| owner_strategy in paper_state | "funding_arb" | "funding_harvest" |
| Risk source | directional perp price 暴露 | delta drift + basis drift |
| Symbol scope | dormant | Stage 1: BTCUSDT only;  Stage 2+: 擴 ETHUSDT |
| LeaseScope | TradeEntry / TradeExit / PositionAdjust | 相同（不新增 LeaseScope variant）|
| IntentType | 既有 OrderIntent 不擴 IntentType field | 相同 |
| Stage 4 LIVE 升級 | dormant | spot leg synthetic → IntentProcessor real spot order（Sprint 5+ cascade）|

**結論**：funding_harvest **不擴 governance 表面**（不新增 LeaseScope / IntentType / lease_type），純策略層新增；既有 governance pipeline 對 perp leg 一視同仁處理。

### §2.4 registry.rs 接線

在 `StrategyFactory::create_with_params` 加 FundingHarvest 構造（與 5 既有策略並列）：

```rust
// FundingHarvest (C10) — Stage 1 Demo BTCUSDT only
let mut fh = funding_harvest::FundingHarvest::new();
fh.active = p.funding_harvest.active;
fh.cooldown_ms = p.funding_harvest.cooldown_ms;
fh.allowed_symbols = p.funding_harvest.allowed_symbols.clone();
fh.funding_threshold_annualized = p.funding_harvest.funding_threshold_annualized;
fh.funding_exit_annualized = p.funding_harvest.funding_exit_annualized;
fh.max_basis_pct = p.funding_harvest.max_basis_pct;
fh.entry_basis_ratio = p.funding_harvest.entry_basis_ratio;
fh.max_hold_ms = p.funding_harvest.max_hold_ms;
fh.total_cost_bps = p.funding_harvest.total_cost_bps;
fh.expected_periods = p.funding_harvest.expected_periods;
fh.rebalance_check_ms = p.funding_harvest.rebalance_check_ms;
fh.delta_drift_threshold = p.funding_harvest.delta_drift_threshold;
fh.position_cap_usd = p.funding_harvest.position_cap_usd;
strategies.push(Box::new(fh));
```

並在 `strategies/mod.rs` 加 `pub mod funding_harvest;`。

### §2.5 params.rs — FundingHarvestParams

```rust
/// FundingHarvest TOML schema + Strategy params surface。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FundingHarvestParams {
    pub active: bool,
    pub cooldown_ms: u64,
    pub allowed_symbols: Vec<String>,
    pub funding_threshold_annualized: f64,
    pub funding_exit_annualized: f64,
    pub max_basis_pct: f64,
    pub entry_basis_ratio: f64,
    pub max_hold_ms: u64,
    pub total_cost_bps: f64,
    pub expected_periods: f64,
    pub rebalance_check_ms: u64,
    pub delta_drift_threshold: f64,
    pub position_cap_usd: f64,
}

pub const DEFAULT_FUNDING_THRESHOLD_ANNUALIZED: f64 = 0.05;  // 5%
pub const DEFAULT_FUNDING_EXIT_ANNUALIZED: f64 = 0.02;       // 2%
pub const DEFAULT_MAX_BASIS_PCT: f64 = 0.5;
pub const DEFAULT_ENTRY_BASIS_RATIO: f64 = 0.8;
pub const DEFAULT_MAX_HOLD_MS: u64 = 72 * 3_600_000;
pub const DEFAULT_TOTAL_COST_BPS: f64 = 37.0;  // perp(11)+spot(20)+slip(3)+basis(3)
pub const DEFAULT_EXPECTED_PERIODS: f64 = 3.0;
pub const DEFAULT_REBALANCE_CHECK_MS: u64 = 2 * 3_600_000;  // 2h
pub const DEFAULT_DELTA_DRIFT_THRESHOLD: f64 = 0.02;        // 2%
pub const DEFAULT_POSITION_CAP_USD: f64 = 100.0;            // Stage 1 cap

impl Default for FundingHarvestParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: 3_600_000,
            allowed_symbols: vec!["BTCUSDT".to_string()],
            funding_threshold_annualized: DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            funding_exit_annualized: DEFAULT_FUNDING_EXIT_ANNUALIZED,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            rebalance_check_ms: DEFAULT_REBALANCE_CHECK_MS,
            delta_drift_threshold: DEFAULT_DELTA_DRIFT_THRESHOLD,
            position_cap_usd: DEFAULT_POSITION_CAP_USD,
        }
    }
}

impl StrategyParams for FundingHarvestParams {
    fn param_ranges() -> Vec<ParamRange> {
        // funding_threshold_annualized [0.01, 0.5]
        // funding_exit_annualized [0.005, 0.05]
        // max_basis_pct [0.1, 2.0]
        // entry_basis_ratio [0.5, 1.0]
        // max_hold_ms [3600000, 30*24*3600000]
        // total_cost_bps [10, 200]
        // rebalance_check_ms [600000, 14400000]
        // delta_drift_threshold [0.005, 0.10]
        // position_cap_usd [10, 1000]
        // allowed_symbols / active 不入 search space
        vec![ /* 完整 ParamRange list */ ]
    }
    fn validate(&self) -> Result<(), String> {
        if self.funding_exit_annualized >= self.funding_threshold_annualized {
            return Err("funding_exit must < funding_threshold".into());
        }
        if !(0.01..=0.5).contains(&self.funding_threshold_annualized) {
            return Err("funding_threshold_annualized must be in [0.01, 0.5]".into());
        }
        if self.position_cap_usd > 100.0 {
            return Err("Stage 1 Demo position_cap_usd hard ceiling = 100".into());
        }
        // ... 其餘 9 條 range check
        Ok(())
    }
}
```

**StrategyParamsConfig 擴展**（`strategies/params.rs`）：加 `pub funding_harvest: FundingHarvestParams` field（與 5 既有策略並列）。

---

## §3 spot leg paper-only synthetic accounting 機制

### §3.1 設計動機

Bybit demo endpoint 不支援 spot lending / spot subscribe（per BB C4 verdict §2 + memory `project_funding_arb_v2_deprecation_path`），但 delta-neutral 策略**必有 spot 腿**才能對沖 perp 方向。

Stage 1-3 Demo 灰度方案：
- perp leg = Bybit demo perp 真實 fill（既有 IntentProcessor → Guardian → Decision Lease → bybit_rest_client::place_order 路徑全經過）
- spot leg = **engine-internal SyntheticSpotLedger**（純 in-process state machine，不寫 PG balance，不發 Bybit order）
- attribution 計算時兩腿 PnL **獨立計算 + 統一寫 trading.fills.track + strategy="funding_harvest"**，但 spot leg fill 來源標記 `synthetic=true`

### §3.2 SyntheticSpotLedger struct（synthetic_spot.rs）

```rust
//! C10 Stage 1-3 Demo synthetic spot leg ledger。
//! Bybit demo 不支援 spot lending → 內部 mock spot fill；不打 Bybit API；不寫 PG balance。
//! Stage 4 LIVE 升級時，本 module retire；spot leg 走 IntentProcessor real spot order（Sprint 5+ cascade）。

use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SyntheticSpotLedger {
    /// 'open' / 'closed'
    pub state: SyntheticSpotState,
    pub entry_notional_usd: f64,
    pub entry_price: f64,
    pub entry_ts_ms: u64,
    /// quantity in BTC（spot leg 是 LONG 方向）
    pub qty: f64,
    /// 累積 rebalance 次數
    pub rebalance_count: u32,
    /// 最後 rebalance 時 spot price
    pub last_rebalance_price: f64,
    pub last_rebalance_ts_ms: u64,
    /// realized PnL at close（USD）
    pub realized_pnl_usd: Option<f64>,
    /// close timestamp（None if still open）
    pub close_ts_ms: Option<u64>,
    /// close price（None if still open）
    pub close_price: Option<f64>,
}

#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub enum SyntheticSpotState {
    Open,
    Closed,
}

impl SyntheticSpotLedger {
    pub fn new() -> Self {
        Self {
            state: SyntheticSpotState::Closed,
            entry_notional_usd: 0.0,
            entry_price: 0.0,
            entry_ts_ms: 0,
            qty: 0.0,
            rebalance_count: 0,
            last_rebalance_price: 0.0,
            last_rebalance_ts_ms: 0,
            realized_pnl_usd: None,
            close_ts_ms: None,
            close_price: None,
        }
    }

    /// 開 long spot leg，匹配 perp short 的 notional。
    /// fill_price 用 perp fill price 作為 spot 近似（demo 不真打 spot 單）；
    /// 真實 Bybit demo spot WS price feed 是有的（per audit §1.5 spot price WS READY），
    /// 因此「真實 spot price」可在 on_tick 內傳入此函式以更精確。
    pub fn open_long(&mut self, notional_usd: f64, spot_price: f64, ts_ms: u64) {
        self.state = SyntheticSpotState::Open;
        self.entry_notional_usd = notional_usd;
        self.entry_price = spot_price;
        self.qty = notional_usd / spot_price;
        self.entry_ts_ms = ts_ms;
        self.last_rebalance_price = spot_price;
        self.last_rebalance_ts_ms = ts_ms;
        self.rebalance_count = 0;
    }

    /// rebalance：跟隨 perp leg notional 變動調整 spot leg book-keeping。
    /// Stage 1 不做 spot leg 加減倉（避免被誤判 new entry）；只更新 ledger 內部數字。
    pub fn rebalance(&mut self, target_notional_usd: f64, spot_price: f64, ts_ms: u64) {
        if self.state != SyntheticSpotState::Open { return; }
        // 計算新 qty 但保留 entry_price 不變（PnL 計算基準）
        self.qty = target_notional_usd / spot_price;
        self.last_rebalance_price = spot_price;
        self.last_rebalance_ts_ms = ts_ms;
        self.rebalance_count += 1;
    }

    /// close 平倉：計算 realized PnL = (close_price - entry_price) × qty。
    /// 注意：spot LONG → close_price > entry_price 則賺；< 則虧。
    pub fn close(&mut self, close_price: f64, ts_ms: u64) -> f64 {
        let pnl = (close_price - self.entry_price) * self.qty;
        self.state = SyntheticSpotState::Closed;
        self.realized_pnl_usd = Some(pnl);
        self.close_ts_ms = Some(ts_ms);
        self.close_price = Some(close_price);
        pnl
    }

    /// 當前 mark-to-market unrealized PnL。
    pub fn unrealized_pnl_usd(&self, current_spot_price: f64) -> f64 {
        if self.state != SyntheticSpotState::Open { return 0.0; }
        (current_spot_price - self.entry_price) * self.qty
    }

    /// 與 perp leg 的 delta drift。
    pub fn delta_drift_pct(&self, perp_notional_usd: f64, current_spot_price: f64) -> f64 {
        let current_spot_notional = self.qty * current_spot_price;
        if current_spot_notional <= 0.0 { return 0.0; }
        ((current_spot_notional - perp_notional_usd) / current_spot_notional).abs()
    }
}
```

### §3.3 Synthetic ledger 寫 attribution

per ARCH-04 cross-strategy attribution invariant，每個 fill 必有 trading.fills.track row。spot leg 因不打 Bybit API，必走以下路徑：

```rust
// 在 FundingHarvest::on_fill (perp leg confirmed 後) emit 一條 synthetic spot fill
// 透過 ctx.synthetic_fill_writer（新接口）或既有 paper_state.apply_fill but flagged synthetic=true
let synthetic_fill = FillResult {
    fill_qty: ledger.qty,
    fill_price: ledger.entry_price,
    fill_ts_ms: ledger.entry_ts_ms,
    side: "BUY".to_string(),   // spot LONG
    is_synthetic_spot: true,   // 新 field！per attribution v3 spec
    parent_perp_fill_id: Some(perp_fill_id),  // cross-leg reference
    // ...
};
paper_state.apply_synthetic_spot_fill(synthetic_fill);
```

**Critical**：`is_synthetic_spot=true` 必傳到 V101 trading.fills.track schema（per Sprint 4+ §4.1.1 base table audit closure 後新增 column）— 區分真實 demo perp fill vs synthetic spot fill，**避免 ML training 集 mis-label**。

### §3.4 邊界：Synthetic ledger 不違反什麼

- **不違反原則 1**（單一寫入口）：synthetic ledger 不發 Bybit order，不經過 IntentProcessor；spot leg 入賬純 in-memory accounting
- **不違反原則 4**（策略不繞風控）：perp leg **完整**經過 Guardian + Decision Lease + cost_gate；spot leg synthetic 不繞 governance 因為它根本不是 trade event（沒打 Bybit）
- **不違反原則 8**（交易可解釋）：spot leg 每次 open / rebalance / close 寫 trading.fills.track + `is_synthetic_spot=true` flag；audit 可重建
- **不違反 AMD-2026-05-15-01 §4.3**（Stage 1 demo evidence requirement）：perp leg 提供 real demo path + fill lineage + Decision Lease 全鏈；synthetic spot leg 補足 delta-neutral 數學完整性

**唯一例外**（接受）：spot leg PnL 不是 real-money（內部 mock），所以 cumulative PnL 報告必雙列：
1. perp leg real PnL（demo USDT 變動，真的會反映在 demo balance）
2. synthetic spot leg notional PnL（純內部 book-keeping）

Total strategy PnL = #1 + #2，但對 demo balance 的影響只有 #1。

### §3.4.1 Stage 1 Demo 真實 synthetic spot PnL accounting（2026-05-25 Round 1+2 IMPL amend）

**Bug 1 HYBRID-BUG 揭露**：Round 1 dispatch packet 原 §3.4 寫「synthetic spot leg close 用 `ledger.entry_price`」，但 round 1 audit 發現 — 若 close 時用 entry_price 結算，synthetic spot leg PnL **結構性永遠 = 0**（entry == close → notional delta = 0），導致 delta-neutral 數學從根本不成立、drift gate 在 cold-start 以外場景也永真。Round 1+2 IMPL（commit `015b9735`）落地對應修正：

**Strategy trait sig 升級**：
- 既有 `on_close_confirmed(symbol)` → 新 `on_close_confirmed(symbol, close_price: f64, close_ts_ms: u64)`
- 新增 `on_external_close(symbol, close_price: f64, close_ts_ms: u64)` — StopManager 強平 / lease revoke / SM-04 cancel 等外部 close 路徑統一入口
- 5 既有 strategy override 全 trait sig migrate：`bb_breakout` / `bb_reversion` / `ma_crossover` / `grid_trading` / `funding_arb`（既有 close path 直接吸收新 args，accounting 不變只是 sig 對齊）
- `funding_harvest` SyntheticSpotLedger.close() 改吃 `close_price` arg — 真實 close-time spot price 入賬，spot leg PnL = `(close_price - entry_price) * qty` 真實非零

**close_price source（dispatch path fallback chain）**：
- `engine/openclaw_engine/src/execution_pipeline/step_4_5_dispatch.rs:1657-1662`（normal exit dispatch）
- `engine/openclaw_engine/src/execution_pipeline/step_6_risk_checks.rs:603-605`（external close / risk forced close dispatch）
- Fallback chain semantics：`latest_price (BBO mid from WS) → entry_price (cold-start fallback) → 0.0 (last-resort sentinel)`
- Cold-start corner case（latest_price WS 尚未到位 + entry_price 退到 0.0）→ PnL=0 觸發 drift gate **acceptable**，非結構性永真

**Round 1+2 sign-off lineage**：
- IMPL commit: `015b9735` (feat sprint1b-audit-fix: C10 PnL fallback + IntentType direction 2-round IMPL)
- E2 round 2 inline return verdict: sub-agent `a015830b`（RETURN → PA spec amend；本 §3.4.1 即回應）
- E4 round 2 inline return PASS: sub-agent `a314d88a`（regression 4135/1/5 GREEN）

**保持不變**：本 §3.4 §3.3 既有「不違反原則 1/4/8 + 不違反 AMD §4.3」全部論證**繼續成立** — trait sig 升級不改變「synthetic spot 不發 Bybit order / 不繞 Guardian / 寫 trading.fills.track 可審計」三層邊界。

---

## §4 entry/exit/size/rebalance/異常退出設計

### §4.1 完整觸發矩陣

| Trigger | Type | Action | Lease | Risk gate |
|---|---|---|---|---|
| `funding_rate per 8h > 0.0001141` AND `basis_pct < 0.4%` AND no position AND cooldown OK AND `eligible_for_demo_canary=true` | Entry | Emit `StrategyAction::Open(perp_short_intent)` qty=$100/perp_price | TradeEntry | Guardian + cost_gate + Kelly sizing + P1 cap |
| Perp fill confirmed (`on_fill` hook) | Synthetic spot entry | Open SyntheticSpotLedger long; write trading.fills.track row with `is_synthetic_spot=true` | None (内部) | None |
| Every tick with position | Monitor | Compute basis_pct + delta_drift_pct + annualized_funding | None | None |
| Every 2h with position | Rebalance check | If `delta_drift_pct > 2%` → SyntheticSpotLedger.rebalance() | None | None |
| `annualized_funding < 2%` OR `basis_pct > 0.5%` OR `hold_time > 72h` OR `funding_rate < 0` | Exit | Emit `StrategyAction::Close{...}` | TradeExit | Lightweight close path |
| Perp Close confirmed (`on_close_confirmed`) | Synthetic spot close | SyntheticSpotLedger.close() + write trading.fills.track row | None | None |
| External perp close (`on_external_close`, e.g., StopManager 強平) | Synthetic spot orphan close | SyntheticSpotLedger.close(price=current_spot_price) | None | None |
| SM-04 escalate ≥ L3 | Demote | Strategy set_active(false) + halt new entries; existing position 等下一 exit trigger 自然平 | None | Governance level |
| Stage 0R replay PnL vs runtime PnL drift > 5% | Demote | Strategy demote Stage 0 + 24h cooldown | None | per AMD §4.4（**2026-05-25 amend**：fallback chain semantics — runtime synthetic spot PnL 真實採用 close-time spot price (`latest_price → entry_price → 0.0` chain per §3.4.1)；drift gate 不再結構性永真；cold-start corner case (latest_price 空 + entry_price 退 = PnL=0) 觸發 drift gate **acceptable not structural**；ref commit `015b9735` + round 1+2 IMPL report + E2 sub-agent `a015830b` RETURN verdict + E4 sub-agent `a314d88a` PASS 4135/1/5）|

### §4.2 異常退出 fail-closed 清單

per AMD-2026-05-15-01 §4.4 + 16 root principles §6:

1. WS funding rate stale > 12h → skip tick（既有 freshness gate）
2. spot price WS stale > 5s → skip tick
3. Bybit retCode != 0 on perp order → fail-closed，rollback cooldown（既有 on_rejection）
4. SyntheticSpotLedger open 失敗（notional 計算 NaN / Inf）→ skip + log + audit
5. delta_drift_pct > 5%（超過 rebalance threshold 2.5x）→ 強制 Close（不等 normal exit gate）
6. governance lease deny → strategy emit retry counter；連續 3 次 deny → strategy set_active(false) demote
7. `[55]` fill-lineage invariant FAIL → strategy demote Stage 0 + 24h cooldown
8. `[58]` canary invariant FAIL → 整 cohort demote Stage 0

### §4.3 size 上限與 P0/P1 風控 cross-ref

- Stage 1 hard cap = **$100 USD per single funding_harvest position**（in `position_cap_usd` param + `validate()` 強制 ≤ 100.0）
- P1 cap (`risk_config_demo.toml` `[risk_envelope]`) 對 funding_harvest 設 override：`max_position_notional_usd = 100`
- P0 portfolio cum loss trip = `$25` Stage 1 max（per AMD-2026-05-15-01 §4.2 conservative 因子）
- Kelly sizing 對 funding_harvest 預期 edge 多輸入 → sized qty 仍受 $100 cap 限制（取 min）

### §4.4 rebalance frequency 校準

per FA §2 + §6 + 既有 Bybit 8h funding cycle：

- **2h rebalance check**：1/4 funding cycle，足夠捕捉 intra-cycle spot/perp 漂移
- 太短（< 30 min）→ rebalance noise > signal
- 太長（> 8h）→ 跨 funding cycle 漂移已實現
- 2h 與 既有 funding_arb cooldown_ms (1h) 順序對齊：cooldown < rebalance_check < funding cycle

---

## §5 risk_config TOML 設計

### §5.1 strategy_params_demo.toml 新增 [funding_harvest] block

在既有 `[funding_arb]` block 之後新增：

```toml
# C10 funding harvest — delta-neutral spot long + perp short matched notional。
# Stage 1 Demo 限定 BTCUSDT 1 symbol + size cap $100 absolute。
# spot leg = synthetic_spot::SyntheticSpotLedger (paper-only; Bybit demo 不支援 spot lending)。
# Stage 4 LIVE 升級時 spot leg → IntentProcessor real spot order (Sprint 5+ cascade)。
# per v5.7 §2 + AMD-2026-05-15-01 + FA §6 Stage 1 Demo matrix。
[funding_harvest]
active = false   # Stage 0R replay preflight PASS 後 operator 顯式開啟
cooldown_ms = 3600000  # 1h between entries
allowed_symbols = ["BTCUSDT"]  # Stage 1 限定；Stage 2 擴 ETHUSDT
funding_threshold_annualized = 0.05  # entry: annualized > 5%
funding_exit_annualized = 0.02       # exit: annualized < 2%
max_basis_pct = 0.5  # entry basis ≤ 0.4% (× entry_basis_ratio 0.8); exit basis > 0.5%
entry_basis_ratio = 0.8
max_hold_ms = 259200000  # 72h
total_cost_bps = 37.0  # perp(11) + spot(20) + slip(3) + basis_drift(3)
expected_periods = 3.0
rebalance_check_ms = 7200000  # 2h tick rebalance check
delta_drift_threshold = 0.02  # 2% delta drift → SyntheticSpotLedger.rebalance()
position_cap_usd = 100.0      # Stage 1 hard ceiling absolute USD
```

**注意**：`active = false` 默認，必 operator 顯式 IPC `update_strategy_params(strategy="funding_harvest", active=true)` 或修 TOML + restart 才啟。

### §5.2 strategy_params_live.toml + strategy_params_paper.toml 對齊

per memory `feedback_env_config_independence`，三環境 config 故意分開。本 Stage：
- `strategy_params_demo.toml` [funding_harvest] active=false（待 Stage 0R PASS 開啟）
- `strategy_params_live.toml` [funding_harvest] active=false（live 永鎖；待 Stage 4 升級）
- `strategy_params_paper.toml` [funding_harvest] active=false（paper 不啟 per AMD-2026-05-15-01 §2.2 BLOCKED）

### §5.3 risk_control_rules/risk_config_demo.toml override

新增 `[strategy_overrides.funding_harvest]` block：

```toml
# C10 funding harvest Stage 1 Demo: tighter per-strategy overrides。
# 雙腿 delta-neutral 但 perp leg 仍打 real demo perp endpoint → 必有 stop loss override。
[strategy_overrides.funding_harvest]
# 單筆最大 notional cap = $100 (Stage 1 absolute)
max_position_notional_usd = 100.0
# 單筆 stop loss = entry notional × 5% (= $5 max loss per trade Stage 1)
stop_loss_pct = 0.05
# 不允 add to position（Stage 1 BTCUSDT 1 倉位 only）
max_positions_per_symbol = 1
max_positions_total = 1
# cost_gate fail-closed: edge_estimate cell empty → 允入場（探索期）
# Stage 1-2 期間還沒有 demo edge_estimate cell，cost_gate fall through 預設 path
cost_gate_min_n_trades_for_block = 5  # Stage 1 conservative; Stage 2 改 15+ 對齊既有
```

### §5.4 risk_config_live.toml + risk_config_paper.toml

per `feedback_env_config_independence`：
- live：[funding_harvest] active=false（不需 override，因為 active=false 不會 entry）
- paper：[funding_harvest] active=false（per AMD §2.2 BLOCKED）

但為審計 trace，三檔仍寫 [strategy_overrides.funding_harvest] block（空值 / inherit），這樣 audit grep 一致。

### §5.5 budget_config.toml（AI cost）

新增 entry 評估 LLM 不必要（C10 純規則策略）；budget_config 不動。

---

## §6 Stage 0R replay preflight harness 設計

### §6.1 業務目標

per AMD §3 + FA §6 Stage 0R row：
- Replay 30d 歷史 BTCUSDT funding rate + perp price + spot price feed
- 對 funding_harvest 策略走 on_tick simulation → 模擬 entry/exit/synthetic spot ledger
- 計算 replay PnL = perp leg P&L + synthetic spot leg P&L
- 比對 historical demo path PnL（如有）or 純理論 PnL
- 輸出 `eligible_for_demo_canary = true | false` per AMD §3.2

### §6.2 既有 replay_runner.py 擴展點

`helper_scripts/canary/replay_runner.py` 既有架構：
- `fetch_klines()` 從 Bybit V5 REST 拿 1m kline
- `synthesize_ticks()` 4 ticks/bar
- 通過 Python PipelineBridge + simulated Rust engine → JSONL output

擴展點：
1. **新增 `fetch_funding_rates(symbol, days)`**：拉 30d 歷史 funding rate（Bybit V5 `/v5/market/funding/history`）— 8h cycle × 90 events
2. **新增 `fetch_spot_klines(symbol, days)`**：拉 30d BTCUSDT spot 1m kline（既有 fetch_klines 改 category='spot'）
3. **新增 `replay_funding_harvest(perp_ticks, spot_ticks, funding_events)`**：merge 三流 → 對 funding_harvest 走 on_tick simulation
4. **新增 `compute_synthetic_pnl(positions, spot_price_at_close)`**：synthetic spot leg P&L
5. **新增 `output_preflight_verdict(replay_metrics) -> dict`**：寫 `funding_harvest_stage0r_<date>.json` 含 `eligible_for_demo_canary` + reasons + evidence_refs

### §6.3 preflight 驗證項目（per AMD §3.3）

| Check | Pass criteria | Fail action |
|---|---|---|
| Leak / lookahead | `compute_edge` 用 `funding_rate.abs() > amortized_cost`，**只用當前 funding period 值**，無 forward-looking | FAIL → fix code → re-run |
| Selection bias | replay 30d 全 BTCUSDT funding event，不 cherry-pick | PASS by design |
| DSR / PSR | `Sharpe(replay_pnl_series) > 0` AND PSR(Sharpe) > 0.6 deflated for 1 strategy | FAIL → strategy retire |
| PBO / bootstrap | 1000-sample bootstrap; lower 5% tail > -$5 cum PnL（即 ≤ Stage 1 stop loss）| FAIL → too risky |
| Replay data tier | replay PnL 與 historical demo path PnL（若有）偏離 < 1% | FAIL → strategy demote |
| Runtime boundary | replay 不 claim 替代 demo fill-lineage | PASS by design |

### §6.4 preflight output schema

```json
{
  "strategy": "funding_harvest",
  "symbol": "BTCUSDT",
  "replay_window_days": 30,
  "replay_start_ts_ms": ...,
  "replay_end_ts_ms": ...,
  "funding_events_total": 90,
  "entry_events": 12,
  "exit_events": 12,
  "max_concurrent_positions": 1,
  "replay_pnl_perp_leg_usd": -3.42,
  "replay_pnl_synthetic_spot_leg_usd": +4.18,
  "replay_pnl_net_usd": +0.76,
  "sharpe": 0.42,
  "deflated_psr": 0.65,
  "bootstrap_lower_5pct_pnl_usd": -2.10,
  "attribution_chain_ok_pct": 100.0,
  "leak_lookahead_check": "PASS",
  "selection_bias_check": "PASS",
  "dsr_psr_check": "PASS",
  "pbo_bootstrap_check": "PASS",
  "replay_data_tier_check": "PASS",
  "runtime_boundary_check": "PASS",
  "eligible_for_demo_canary": true,
  "reasons": ["all 6 sanity checks PASS"],
  "evidence_refs": [
    "helper_scripts/canary/output/funding_harvest_stage0r_2026-05-XX.jsonl",
    "helper_scripts/canary/output/funding_harvest_stage0r_metrics_2026-05-XX.json"
  ]
}
```

### §6.5 harness LOC + 工時

- `replay_funding_harvest.py` 新檔 ~350 LOC（與既有 replay_runner.py 並列；可 import 共用 fetch_klines）
- Bybit funding rate REST 接 ~80 LOC
- Bybit spot kline REST 接 ~50 LOC（既有 fetch_klines 加 category 參數）
- Synthetic spot leg P&L 計算 ~80 LOC（mirror SyntheticSpotLedger 邏輯，Python 版）
- 6 sanity check ~100 LOC
- Output JSON writer ~60 LOC
- QC 接 PSR / bootstrap 統計 ~80 LOC（與既有 canary_comparator.py 對齊）
- **Total ~800 LOC / 估 8-12 hr E1 + QC 並行**

### §6.6 Carry-over non-blocking follow-up（next sprint）

**OrderIntent struct encapsulation hardening**（per E2 round 2 a015830b inline note carry-over）：
- 當前 `OrderIntent` struct 多個 field 為 `pub`（外部 crate 可直接構造），round 1+2 IMPL 為對齊既有 mutation pattern 暫保留
- Follow-up scope：`pub` → `pub(crate)` + 引入 builder pattern 強制 invariant（如 `direction` ↔ `qty.sign()` 不可錯配）
- 影響面：4 既有 integration test cross-crate 直接構造 OrderIntent；需 PA spec design（新 builder API surface） + E1 重構 + E2 review
- 評級：**non-blocking**（current sprint demo path 已 PASS；屬結構優化非正確性問題）
- 派發時點：next sprint 起點 PM triage 決定要否插入

---

## §7 5 Acceptance Criteria（per FA §6 Stage 1 Demo gate）

per AMD §4.3 demo evidence requirement + FA §6 row 1：

| # | AC | Required | Source of truth |
|---|---|---|---|
| 1 | **fills ≥ 5** | Real demo perp fills (excludes synthetic spot fills which auto-paired) | `trading.fills` WHERE strategy='funding_harvest' AND engine_mode IN ('demo', 'live_demo') AND is_synthetic_spot=false AND ts > stage1_start |
| 2 | **7d cumulative PnL ≥ -0.5%** (即 ≥ -$5 absolute on $100 cap) | perp leg real PnL + synthetic spot leg P&L 累加 | `trading.fills.track` aggregate strategy='funding_harvest' window=7d |
| 3 | **P0 breach=0** | 0 portfolio cum loss trip / 0 SM-04 ≥ L3 escalate | `governance.escalations` + `risk.p0_breaches` empty |
| 4 | **size $100** | 每筆 perp leg notional ≤ $100 absolute | `trading.fills` WHERE notional_usd > 100 AND strategy='funding_harvest' = 0 rows |
| 5 | **Stage 0R replay preflight PASS** | `eligible_for_demo_canary=true` + 6 sanity check 全 PASS | `helper_scripts/canary/output/funding_harvest_stage0r_*.json` |

**additional invariant**：
- attribution_chain_ok = 100%（per Sprint N+0 closure invariant；既有 GUI metric）
- decision_lease coverage = 100%（per AMD §4.3 every executable intent has Decision Lease lineage）
- replay-vs-runtime PnL drift < 5%（per AMD §4.4 rollback）

---

## §8 8-step IMPL dispatch chain

### §8.1 Wave A — PA spec + Stage 0R harness spec（並行；wall-clock 0.5-1 day）

| # | Owner | Task | Estimate | Output |
|---|---|---|---|---|
| A1 | PA | C10 funding_harvest strategy 完整 spec（本 packet § 1-5 + 補充 6 sanity check formula + 異常 fail-closed 矩陣完整化） | 8-12 hr | `docs/execution_plan/2026-05-XX--c10_funding_harvest_strategy_spec.md` |
| A2 | PA | Stage 0R replay preflight harness 設計（本 packet §6 + Python 接 Bybit funding history + spot kline + PSR / PBO 算法） | 6-8 hr included in A1 | same file §6 |
| A3 | QC | replay PnL formula + bootstrap LOC 校驗 + PSR threshold 校準（並行 A1）| 2-4 hr | review note |

### §8.2 Wave B — E1 IMPL（並行；wall-clock 1.5-2 day）

| # | Owner | Task | Estimate | Output |
|---|---|---|---|---|
| B1 | E1a | `strategies/funding_harvest/` 新 module IMPL（mod.rs + params.rs + runtime_params.rs + synthetic_spot.rs + tests.rs + tests_synthetic.rs）| 18-26 hr | 6 .rs file 約 1230 LOC + 2 ADR cross-ref note |
| B2 | E1b | `strategies/mod.rs` 加 `pub mod funding_harvest;` + `strategies/registry.rs` `StrategyFactory::create_with_params` 接線 + `strategies/params.rs` `StrategyParamsConfig.funding_harvest` field 加 | 2-3 hr | 3 file mutation |
| B3 | E1c | TOML 接線：`settings/strategy_params_demo.toml` `[funding_harvest]` block + `risk_control_rules/risk_config_demo.toml` `[strategy_overrides.funding_harvest]` + live + paper TOML 對齊 | 1-2 hr | 6 TOML files |
| B4 | E1d | Stage 0R replay preflight harness IMPL（`helper_scripts/canary/replay_funding_harvest.py` 新檔 ~800 LOC + 接既有 fetch_klines + canary_schema.py 接 sanity check + output JSON）| 8-12 hr | 1 .py + 1 sample output JSON |
| B5 | E1e | V### migration（如需）為 `trading.fills.track` 加 `is_synthetic_spot BOOLEAN DEFAULT false` + `parent_perp_fill_id TEXT NULL` column；per Sprint 4+ §4.1.1 base table audit 對齊 | 2-3 hr (depends on §4.1.1 closure) | V107 or successor V### sql file |

**注意 B5 阻塞性**：若 V101 trading.fills.track schema 已預留 `is_synthetic_spot` 則 B5 跳過；若無，需先 Sprint 4+ §4.1.1 V99-V102 base table audit 完成。可 PA 預先諮詢 MIT verdict（W+0 0.5 hr）決定 B5 是否能與 B1 並行。

### §8.3 Wave C — E2 adversarial review（sequential 0.5 day）

| # | Owner | Task | Estimate | Output |
|---|---|---|---|---|
| C1 | E2 | adversarial review of funding_harvest IMPL；focus on: (a) delta-neutral 數學正確性 (b) synthetic spot leg accounting 邊界 (c) 16 root principles §1/§4/§5/§8 (d) AMD-2026-05-15-01 §4.3/§4.4 demo evidence + rollback (e) `[55]` fill-lineage invariant (f) freshness gate 接線 | 2-3 hr | E2 review note |
| C2 | A3 | UI / GUI 是否需要 funding_harvest tab 顯示（Stage 1 Demo 限定 BTCUSDT，建議 reuse strategy_performance tab，不單獨開）| 0.5-1 hr | confirm reuse or 新建 |

### §8.4 Wave D — Round 2 fix + E4 regression（並行；wall-clock 0.5 day）

| # | Owner | Task | Estimate |
|---|---|---|---|
| D1 | E1 | Round 2 fix per E2 verdict | 0-4 hr |
| D2 | E4 | cargo test + pytest replay_funding_harvest tests + integration test + cross-strategy attribution_chain_ok regression | 1-2 hr |

### §8.5 Wave E — QA + PM signoff（並行；wall-clock 0.5-1 day）

| # | Owner | Task | Estimate |
|---|---|---|---|
| E1 | QA | Stage 0R replay preflight Acceptance run（執行 replay harness + verify 5 AC + 6 sanity check）| 2-3 hr |
| E2 | QA | Stage 1 Demo Acceptance pre-fly checklist（per AMD §7 required pre-launch gates 6 條） | 1 hr |
| E3 | PM | Phase 3e sign-off + Stage 1 Demo cohort 開啟（修 `strategy_params_demo.toml` active=true + restart engine + 7d 觀察期啟動） | 1 hr |

### §8.6 完整 dispatch chain 圖

```
W+0 ──→ Wave A: PA spec (8-12 hr) // 並行 QC review (2-4 hr)
        PA 諮詢 MIT V101 schema verdict (0.5 hr) → 決定 B5 並行性

W+0.5 ─→ Wave B (1.5-2 day, 5 並行 sub-agent):
        B1 (E1a Rust strategy module 18-26 hr)
        B2 (E1b registry 2-3 hr)
        B3 (E1c TOML 1-2 hr)
        B4 (E1d replay harness 8-12 hr)
        B5 (E1e V### migration, conditional)

W+2.5 ─→ Wave C: E2 review (2-3 hr)
W+3 ──→ Wave D: round 2 fix + E4 regression (1-4 hr 並行)
W+3.5 ─→ Wave E: QA Stage 0R Acceptance + Stage 1 Demo Acceptance + PM signoff (3-5 hr)
W+4 ──→ Stage 1 Demo cohort 開啟 (7d 觀察期啟動)
W+11 ─→ Stage 1 7d closure verdict (PASS → Stage 2 14d / FAIL → demote Stage 0)
```

**Wall-clock total**：~4 day to Stage 1 cohort open + 7d observation = ~11 day to Stage 1 verdict。

---

## §9 Estimate split

| Wave | Owner | Task | Hours |
|---|---|---|---|
| A | PA | spec + harness design | 8-12 |
| A | QC | replay formula + PSR review | 2-4 |
| B1 | E1a | Rust strategy module IMPL | 18-26 |
| B2 | E1b | registry + mod.rs 接線 | 2-3 |
| B3 | E1c | TOML 接線 6 files | 1-2 |
| B4 | E1d | Python replay harness IMPL | 8-12 |
| B5 | E1e | V### migration (conditional) | 0-3 |
| C1 | E2 | adversarial review | 2-3 |
| C2 | A3 | UI reuse confirmation | 0.5-1 |
| D1 | E1 | round 2 fix | 0-4 |
| D2 | E4 | regression | 1-2 |
| E1 | QA | Stage 0R Acceptance | 2-3 |
| E2 | QA | Stage 1 Demo pre-fly check | 1 |
| E3 | PM | Phase 3e sign-off | 1 |
| **TOTAL** | | | **46.5-79 hr** |

**Compressed估算 41-62 hr**（per audit §1.3 + 並行壓縮 30-40% wall-clock saving）。

**並行壓縮 effective wall-clock**：~4 day to cohort open + 7d 觀察。

---

## §10 E2 重點審查 3 條

per audit `engineering:architecture` 範式 + 本 packet 高風險點：

### §10.1 Delta-neutral 數學正確性

E2 必驗 4 條：
1. `compute_basis_pct(perp_price, spot_price)` 用 `abs((perp/spot - 1) × 100)`，**不是 simple difference** — 已確認 §1.2 公式對齊既有 `funding_arb.rs:88-94`
2. `compute_net_edge_bps_per_period(funding_rate_8h)` 用 `funding_rate.abs() × 10000 - amortized_cost`，**not 用 funding_rate × 10000 直接**（負 funding 也應視為機會但本策略 design choice = funding > 0 only）
3. `Self::annualized_funding(funding_rate_8h)` × 3.0 × 365.0 — verify Bybit 確實是 3 × 8h/day（per BB C4 dictionary line 1092 cross-check funding cycle = 8h）
4. `delta_drift_pct = abs((spot_notional - perp_notional) / spot_notional)`，**not divide by perp_notional**（保證 spot leg 視角；不對稱選擇有意義）

### §10.2 SyntheticSpotLedger 邊界與 attribution

E2 必驗 5 條：
1. SyntheticSpotLedger 不發 Bybit order — grep `bybit_rest_client::place_order` 在 `funding_harvest/` module 0 hit
2. `is_synthetic_spot=true` flag 必傳到 V101 trading.fills.track — grep `is_synthetic_spot` 在 paper_state + V101 schema cross-check
3. `parent_perp_fill_id` cross-leg reference 在 audit query 可 JOIN 兩腿 fill — schema example query in spec
4. SyntheticSpotLedger.close() 用 **current spot price**，**not entry price**（避 PnL hard-coded 0）
5. `on_external_close` hook 對 synthetic spot leg orphan handling — strategy state cleanup 完整

### §10.3 16 root principles 合規 + AMD-2026-05-15-01 §4.4 rollback

E2 必驗 6 條：
1. 原則 1（單一寫入口）：perp leg 經 IntentProcessor / synthetic spot 不發 Bybit order；spot leg ledger 不開 alternative write path — grep `place_order` outside IntentProcessor = 0
2. 原則 4（策略不繞風控）：perp leg `StrategyAction::Open(intent)` 完整經 Guardian + Decision Lease + cost_gate — IntentResult 拒絕鏈條完整
3. 原則 5（生存 > 利潤）：`stop_loss_pct = 0.05` override 在 risk_config_demo.toml；perp leg 觸 stop_loss → `on_external_close` 清 synthetic spot leg
4. 原則 8（交易可解釋）：synthetic spot leg 每 open / rebalance / close 寫 trading.fills.track row；audit reconstructible
5. AMD-2026-05-15-01 §4.3 — Stage 1 demo evidence 6 條全經過（nonzero decision / fill / Decision Lease lineage / Guardian verdict / ExecutionReport / no boundary violation）
6. AMD §4.4 rollback — replay PnL drift > 5% / `[55]` FAIL / `[58]` FAIL / SM-04 ≥ L3 → strategy demote Stage 0

---

## §11 Sprint 4 LIVE 路徑（forward-looking spec stub）

per Sprint 4+ PM Phase 3e §5.3 cascade window + FA §6 + AMD-2026-05-15-01 §4-5：

### §11.1 Stage 2 → Stage 3 升級路徑

| Stage | Window | Symbol expansion | Size | Rebalance | Spot leg |
|---|---|---|---|---|---|
| Stage 1 Demo | 7d | BTCUSDT | $100 | 2h | synthetic ledger |
| Stage 2 Demo Extended | 14d | BTCUSDT only (per AMD §4.1 不擴 symbol; capital 翻倍) | $200 | 2h | synthetic ledger |
| Stage 3 Demo Full | 21d | BTCUSDT + ETHUSDT | $500 | 1h | synthetic ledger |
| Stage 4 LIVE Pending | indefinite | BTCUSDT + ETHUSDT | $2000 initial (per v5.7 §1 capital flow) | 1h | **REAL spot order** via IntentProcessor (Sprint 5+ cascade) |

### §11.2 Sprint 5+ cascade: spot leg synthetic → real path

Stage 4 LIVE 升級 prerequisites（Sprint 5+ design + IMPL window）：
1. Spot order path 接 IntentProcessor：新建 `IntentProcessor::submit_spot_intent`（與既有 perp `submit_intent` 並列）
2. Bybit spot V5 endpoint 接 `bybit_rest_client::place_spot_order`（既有 12 個 `/v5/spot-*` rate limit 已預留 path detection per BB C4）
3. `LeaseScope` 是否需新增 `SpotEntry / SpotExit` variant — 評估期 PA + E2
4. `risk_config_live.toml` `[strategy_overrides.funding_harvest]` spot leg 風控 override
5. SyntheticSpotLedger retire / 改為 audit-only shadow 對照

### §11.3 Sprint 5+ effort estimate（forward-look only）

- PA spec ~6-8 hr（Spot intent / LeaseScope / Bybit spot endpoint 接線）
- E1 IMPL ~15-25 hr（spot intent path + bybit_rest_client extension + paper_state spot order book）
- E2 + BB + E3 + QA ~5-8 hr
- **Total ~25-40 hr** + Sprint 5+ wall-clock 1 week

### §11.4 forward-looking risk

- Bybit spot demo endpoint 是否支援 spot subscribe — 已驗 0/12 endpoint，**Stage 4 LIVE 必走 real spot**，no demo fallback；Stage 4 LIVE 前需 BB curl smoke verify
- Stage 4 LIVE 升級時 spot leg fee 結構不同 — `total_cost_bps` 重新校準（perp 11 bps + spot **0.1% maker / 0.1% taker** ≈ 20 bps spot fee per leg；Stage 4 LIVE `total_cost_bps` 估 11 + 20 + 3 + 3 = 37 bps 與 Stage 1 預設一致；無需改 param）
- Spot leg PnL 必反映 demo / live USDT balance — Stage 1-3 synthetic ledger PnL **只 book-keeping**；Stage 4 LIVE 必反映 wallet balance reconciliation

---

## §12 dispatch readiness verdict

### §12.1 verdict

**READY-TO-DISPATCH**（per audit §4.1）

### §12.2 前置條件 status

| 前置 | 狀態 |
|---|---|
| C10 spec 完整化 | ✅ 本 packet § 1-5 |
| Stage 0R harness 設計 | ✅ 本 packet §6 |
| 5 AC + Stage 0R sanity check | ✅ 本 packet §7 |
| E1 dispatch chain 設計 | ✅ 本 packet §8 |
| Estimate breakdown | ✅ 本 packet §9 |
| E2 重點審查 3 條 | ✅ 本 packet §10 |
| Sprint 4 LIVE 路徑 spec stub | ✅ 本 packet §11 |
| V101 trading.fills.track schema `is_synthetic_spot` 預留 | ⏳ 待 Sprint 4+ §4.1.1 base table audit 諮詢 MIT 0.5 hr 結論；不阻塞 B1-B4 並行（B5 conditional） |
| AMD-2026-05-15-01 Stage 1 pre-launch gate 6 條 | ✅ 已對齊本 packet §4 + §7 |

### §12.3 阻塞性 dependency

**0 hard blocker**。可即刻 Wave A dispatch。

**1 soft 諮詢**：PA 派 MIT 0.5 hr quick query — V101 schema 是否預留 `is_synthetic_spot` column；結論決定 B5 是否須與 §4.1.1 base table audit 並行。

### §12.4 operator decision points

**0 個** — C10 strategy IMPL 純內部設計 + IMPL。

偶有 PA + QC adversarial verdict 衝突時 operator 仲裁 1 次 ~10 min。

### §12.5 PM 路徑建議

per audit §5.2 路徑 A：
1. **W+0**：PM 拍板 Wave A dispatch + PA 諮詢 MIT V101 schema 0.5 hr
2. **W+0.5**：Wave B 5 並行 sub-agent dispatch
3. **W+2.5**：Wave C E2 review
4. **W+3-3.5**：Wave D round 2 fix + E4 + QA
5. **W+4**：PM Phase 3e sign-off + Stage 1 Demo cohort 開啟（修 TOML active=true + restart engine）
6. **W+11**：Stage 1 Demo 7d 觀察期 closure verdict

---

## §13 PA 11 條 packet 完成確認

per 任務 brief §11 section + 完成回報 5 條 mapping：

1. ✅ C10 spec + delta-neutral design — §1
2. ✅ strategies/funding_harvest/ Rust module 設計 — §2
3. ✅ spot leg paper-only emulation 機制 — §3
4. ✅ entry/exit/size/rebalance/異常退出設計 — §4
5. ✅ risk_config TOML 設計 — §5
6. ✅ Stage 0R replay preflight harness 設計 — §6
7. ✅ 5 AC — §7
8. ✅ 8-step IMPL dispatch chain — §8
9. ✅ estimate split (41-62 hr) — §9
10. ✅ E2 重點審查 3 條 — §10
11. ✅ Sprint 4 LIVE 路徑 — §11

---

**END OF PA — Sprint 1B Pending 3.1 C10 funding harvest Stage 1 Demo dispatch packet**

//! C10 funding harvest — delta-neutral spot long + perp short matched notional。
//!
//! MODULE_NOTE：
//!   模塊用途：以 perp 短倉收取 funding payment，同時用 synthetic spot 長倉對沖
//!     price 方向暴露達成 delta-neutral；per v5.7 §2 + AMD-2026-05-15-01 +
//!     FA §6 Stage 1 Demo matrix。
//!   主要類函數：FundingHarvest、on_tick（三分支 entry/exit/rebalance）、on_fill
//!     （fill confirmed 後 open synthetic spot ledger）、on_close_confirmed
//!     （strategy 自主平倉後 realize synthetic spot PnL）、on_external_close
//!     （風控強平後同步清 ledger）。
//!   依賴：super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown}、
//!     intent_processor::OrderIntent、tick_pipeline::TickContext、
//!     openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface}、
//!     sibling synthetic_spot::SyntheticSpotLedger（paper-only ledger）。
//!   硬邊界：
//!     - 不變量（原則 1）：spot 腿不發 Bybit order；ledger 為 in-memory accounting。
//!     - 不變量（原則 4）：perp 腿走 `StrategyAction::Open(intent)` → Guardian +
//!       cost_gate + Kelly sizing + P1 cap，無繞行路徑。
//!     - 不變量：active=false 預設；TOML 或 IPC active=true 才啟（fail-closed）。
//!     - Stage 1 限定 BTCUSDT；validate 在 params 層先擋；on_tick 再 fence 防 IPC
//!       直接 patch 結構繞 validate。
//!     - position_cap_usd 在 strategy 內 floor 上限 $100；validate 強制 ≤ 100。
//!   funding_harvest vs funding_arb（ADR-0018 dormant）：
//!     - funding_arb：directional single-leg perp，dormant 不動；
//!     - funding_harvest：本模組，delta-neutral 雙腿，新 strategy slot。

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};
use openclaw_core::execution::FillResult;

pub mod params;
pub mod synthetic_spot;

#[cfg(test)]
mod tests;
#[cfg(test)]
mod tests_synthetic;

pub use params::FundingHarvestParams;
use params::{
    DEFAULT_COOLDOWN_MS, DEFAULT_DELTA_DRIFT_THRESHOLD, DEFAULT_ENTRY_BASIS_RATIO,
    DEFAULT_EXPECTED_PERIODS, DEFAULT_FUNDING_EXIT_ANNUALIZED,
    DEFAULT_FUNDING_THRESHOLD_ANNUALIZED, DEFAULT_MAX_BASIS_PCT, DEFAULT_MAX_HOLD_MS,
    DEFAULT_POSITION_CAP_USD, DEFAULT_REBALANCE_CHECK_MS, DEFAULT_TOTAL_COST_BPS,
};
use synthetic_spot::SyntheticSpotLedger;

// PostOnly maker 入場參數（與 funding_arb 範式對齊）。
// 為什麼固定常量：funding harvest 入場單需 PostOnly 取 maker fee（cost edge gate
// 假設 perp fee=11 bps；taker 約 5.5 bps×2，maker 約 1 bps×2 才達 cost 預設）。
const FUNDING_HARVEST_MAKER_OFFSET_BPS: f64 = 1.0;
const FUNDING_HARVEST_MAKER_BUFFER_TICKS: u32 = 1;
const FUNDING_HARVEST_MAKER_TIMEOUT_MS: u64 = 45_000;

// ──────────────────────────────────────────────────────────────────────────
// FundingHarvest strategy struct
// ──────────────────────────────────────────────────────────────────────────

pub struct FundingHarvest {
    active: bool,
    /// per-symbol cooldown（同 funding_arb 範式；rollback 用 prev_last_trade_ms）。
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,

    /// Stage 1 只 BTCUSDT；Stage 2+ 才擴 ETHUSDT。
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

    /// 每 symbol synthetic spot 腿 ledger（Stage 1 只 BTCUSDT 1 條）。
    pub(crate) synthetic_spot: HashMap<String, SyntheticSpotLedger>,

    /// 每 symbol 入場時戳（與 paper_state.entry_ts_ms 同步快照，避 lookup）。
    pub(crate) entry_ms: HashMap<String, u64>,

    /// 每 symbol 上次 rebalance 檢查時戳（避免每 tick 重算 drift）。
    pub(crate) last_rebalance_check_ms: HashMap<String, u64>,

    /// rejection rollback 用的 cooldown 快照（funding_arb 範式）。
    prev_last_trade_ms: HashMap<String, u64>,

    /// CONF-D：策略 confidence 縮放係數（預設 1.0）。
    conf_scale: f64,
}

impl Default for FundingHarvest {
    fn default() -> Self {
        Self::new()
    }
}

impl FundingHarvest {
    pub fn new() -> Self {
        Self {
            active: false,
            cooldown: TrendCooldown::new(DEFAULT_COOLDOWN_MS),
            cooldown_ms: DEFAULT_COOLDOWN_MS,
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
            conf_scale: 1.0,
        }
    }

    /// 把單期 funding rate 折算成 annualized。
    ///
    /// 為什麼硬編 3×365（OOS-8 誠實化）：`× 3 × 365` 假設 fundingInterval = 8h
    /// （每日 3 期）。這**不是**所有 Bybit perp 的普適常數——部分合約為 1h/4h
    /// fundingInterval，套此係數會嚴重低估年化。本策略 `allowed_symbols` 由
    /// Stage 1 fence 限定為 8h-interval 的 BTCUSDT / ETHUSDT，故此處成立。
    /// 擴充到非-8h symbol 前，必須先把實際 fundingInterval 接入（見
    /// `should_enter` / `should_exit` 呼叫點註釋，屬另立 ticket 的級別 2 wiring），
    /// 不可只放寬 allowed_symbols。
    /// 不變量：純函數，無 self 依賴；負 funding 直接乘出負 annualized（caller 判斷方向）。
    pub(crate) fn annualized_funding(funding_rate_8h: f64) -> f64 {
        funding_rate_8h * 3.0 * 365.0
    }

    /// basis 百分比 = |perp / index − 1| × 100。
    /// 用 index_price 作 spot 近似（與 funding_arb 範式一致；Bybit demo 不支援
    /// 真實 spot WS，OC-5 index_price 已是 spot oracle）。
    /// 不變量：index_price 缺失或 ≤ 0 回 f64::MAX → 入場/出場 gate 必跳過（fail-closed）。
    pub(crate) fn compute_basis_pct(perp_price: f64, index_price: Option<f64>) -> f64 {
        match index_price {
            Some(ip) if ip > 0.0 => ((perp_price / ip) - 1.0).abs() * 100.0,
            _ => f64::MAX,
        }
    }

    /// per-period net edge after amortized 雙腿 cost（bps，可正可負）。
    /// 不變量：expected_periods 由 validate 保 > 0；total_cost_bps 由 validate 保 [10, 200]。
    pub(crate) fn compute_net_edge_bps_per_period(&self, funding_rate_8h: f64) -> f64 {
        let amortized_cost = self.total_cost_bps / self.expected_periods;
        funding_rate_8h.abs() * 10_000.0 - amortized_cost
    }

    /// 是否滿足入場條件（純函數，便於 unit test）。
    pub(crate) fn should_enter(&self, funding_rate_8h: f64, basis_pct: f64) -> bool {
        // annualized 折算鎖定 8h fundingInterval（見 annualized_funding 註釋）。
        // allowed_symbols 必為 8h-interval symbol（Stage 1 fence + is_allowed_symbol
        // 雙重 enforce）；擴非-8h symbol 前須先接真實 fundingInterval（級別 2 ticket）。
        let annualized = Self::annualized_funding(funding_rate_8h);
        annualized > self.funding_threshold_annualized
            && self.compute_net_edge_bps_per_period(funding_rate_8h) > 0.0
            && basis_pct < self.max_basis_pct * self.entry_basis_ratio
            // funding harvest design = funding > 0 收取（perp 多方付空方 → 我們 perp SHORT）。
            && funding_rate_8h > 0.0
    }

    /// 是否滿足平倉條件（純函數）。
    pub(crate) fn should_exit(
        &self,
        funding_rate_8h: f64,
        basis_pct: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> bool {
        // annualized 折算鎖定 8h fundingInterval（見 annualized_funding 註釋）。
        // 同 should_enter：allowed_symbols 必為 8h-interval symbol。
        let annualized = Self::annualized_funding(funding_rate_8h);
        // funding decay or 反向。
        if annualized < self.funding_exit_annualized || funding_rate_8h < 0.0 {
            return true;
        }
        // basis drift。
        if basis_pct > self.max_basis_pct {
            return true;
        }
        // max hold。
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return true;
        }
        false
    }

    /// Stage 1 fence：必 BTCUSDT。其他 symbol fail-closed skip。
    /// 為什麼：TOML validate 已擋越級，但 IPC update_params_json 路徑可能 patch
    /// allowed_symbols 進 ["BTCUSDT", "SOLUSDT"]，這裡再次 enforce。
    fn is_allowed_symbol(&self, sym: &str) -> bool {
        self.allowed_symbols.iter().any(|s| s.as_str() == sym)
    }

    /// rejection rollback 用的 cooldown 快照（同 funding_arb 範式）。
    fn snapshot_prev_cooldown(&mut self, sym: &str) {
        self.prev_last_trade_ms
            .insert(sym.to_string(), self.cooldown.last_ms(sym).unwrap_or(0));
    }

    /// IPC `update_strategy_params` 熱更新；同步 active + 全範圍。
    /// active 包含在 update 路徑（與 funding_arb 設計對齊）讓 operator / Strategist
    /// 可在不重啟 engine 的情況下暫停 / 啟動策略。
    pub fn update_params(&mut self, params: FundingHarvestUpdateParams) -> Result<(), String> {
        params.validate()?;
        self.active = params.active;
        self.cooldown_ms = params.cooldown_ms;
        self.cooldown.set_duration(params.cooldown_ms);
        self.allowed_symbols = params.allowed_symbols.clone();
        self.funding_threshold_annualized = params.funding_threshold_annualized;
        self.funding_exit_annualized = params.funding_exit_annualized;
        self.max_basis_pct = params.max_basis_pct;
        self.entry_basis_ratio = params.entry_basis_ratio;
        self.max_hold_ms = params.max_hold_ms;
        self.total_cost_bps = params.total_cost_bps;
        self.expected_periods = params.expected_periods;
        self.rebalance_check_ms = params.rebalance_check_ms;
        self.delta_drift_threshold = params.delta_drift_threshold;
        self.position_cap_usd = params.position_cap_usd;
        info!(
            strategy = "funding_harvest",
            active = self.active,
            position_cap_usd = self.position_cap_usd,
            "params updated via IPC"
        );
        Ok(())
    }

    /// 將當前 tunable 狀態快照成 IPC payload。
    pub fn get_params(&self) -> FundingHarvestUpdateParams {
        FundingHarvestUpdateParams {
            active: self.active,
            cooldown_ms: self.cooldown_ms,
            allowed_symbols: self.allowed_symbols.clone(),
            funding_threshold_annualized: self.funding_threshold_annualized,
            funding_exit_annualized: self.funding_exit_annualized,
            max_basis_pct: self.max_basis_pct,
            entry_basis_ratio: self.entry_basis_ratio,
            max_hold_ms: self.max_hold_ms,
            total_cost_bps: self.total_cost_bps,
            expected_periods: self.expected_periods,
            rebalance_check_ms: self.rebalance_check_ms,
            delta_drift_threshold: self.delta_drift_threshold,
            position_cap_usd: self.position_cap_usd,
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FundingHarvestUpdateParams (IPC payload；與 FundingHarvestParams 同 schema
// 但作為 update payload 獨立)
// ──────────────────────────────────────────────────────────────────────────

/// IPC `update_strategy_params` 的 funding_harvest payload schema。
/// 與 `FundingHarvestParams`（TOML schema）刻意保持結構鏡像 + 同 validate，
/// 但類型分離避免 TOML-load schema 與 IPC-patch schema 耦合（funding_arb 範式）。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FundingHarvestUpdateParams {
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

impl Default for FundingHarvestUpdateParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: DEFAULT_COOLDOWN_MS,
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

impl StrategyParams for FundingHarvestUpdateParams {
    /// 等同 `FundingHarvestParams::param_ranges`；委派以保單一定義。
    fn param_ranges() -> Vec<ParamRange> {
        FundingHarvestParams::param_ranges()
    }

    fn validate(&self) -> Result<(), String> {
        // 委派到 FundingHarvestParams::validate 保 invariant 唯一。
        let mirror = FundingHarvestParams {
            active: self.active,
            cooldown_ms: self.cooldown_ms,
            allowed_symbols: self.allowed_symbols.clone(),
            funding_threshold_annualized: self.funding_threshold_annualized,
            funding_exit_annualized: self.funding_exit_annualized,
            max_basis_pct: self.max_basis_pct,
            entry_basis_ratio: self.entry_basis_ratio,
            max_hold_ms: self.max_hold_ms,
            total_cost_bps: self.total_cost_bps,
            expected_periods: self.expected_periods,
            rebalance_check_ms: self.rebalance_check_ms,
            delta_drift_threshold: self.delta_drift_threshold,
            position_cap_usd: self.position_cap_usd,
        };
        mirror.validate()
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Strategy trait impl
// ──────────────────────────────────────────────────────────────────────────

impl Strategy for FundingHarvest {
    fn name(&self) -> &str {
        "funding_harvest"
    }

    fn is_active(&self) -> bool {
        self.active
    }

    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// W-AUDIT-8a Phase A：funding harvest 聲明消費 FundingSkew + Basis（與 funding_arb
    /// 一致；Stage 4 LIVE 升級時可考慮加 CrossAsset BTC lead-lag 但本 Wave 不擴）。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::FundingSkew, AlphaSourceTag::Basis];
        TAGS
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if !self.active {
            return vec![];
        }

        let sym = ctx.symbol;
        let now_ms = ctx.timestamp_ms;

        // Stage 1 fence：只允 allowed_symbols。
        if !self.is_allowed_symbol(sym) {
            return vec![];
        }

        // 必有 funding_rate；缺則跳過（freshness gate 由 WS layer 保證）。
        let funding_rate = match ctx.funding_rate {
            Some(fr) if fr.is_finite() && fr.abs() > f64::EPSILON => fr,
            _ => return vec![],
        };

        let perp_price = ctx.price;
        if !perp_price.is_finite() || perp_price <= 0.0 {
            return vec![];
        }

        let basis_pct = Self::compute_basis_pct(perp_price, ctx.index_price);

        // ── 三分支（funding_arb Option A-Lite 範式）──
        // 1. 自家倉位（owner == self.name()）→ exit/rebalance branch
        // 2. 他家倉位（cross-strategy occupied）→ skip
        // 3. 無倉位 → entry branch
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            Some(pos) => {
                // entry_ms 優先用 strategy 自家快照（fill 時記錄）；缺則用 paper_state。
                let entry_ms = self
                    .entry_ms
                    .get(sym)
                    .copied()
                    .unwrap_or(pos.entry_ts_ms);

                if self.should_exit(funding_rate, basis_pct, now_ms, entry_ms) {
                    self.snapshot_prev_cooldown(sym);
                    self.cooldown.record_signal(sym, now_ms);

                    let mut confidence = 0.8 * self.conf_scale;
                    confidence = confidence.clamp(0.0, 1.0);

                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence,
                        reason: format!(
                            "funding_harvest_exit: funding={:.6} basis={:.3}% hold_ms={}",
                            funding_rate,
                            basis_pct,
                            now_ms.saturating_sub(entry_ms)
                        ),
                    }];
                }

                // 不平倉 → 檢查是否該 rebalance（每 rebalance_check_ms 一次）。
                let last_check = self
                    .last_rebalance_check_ms
                    .get(sym)
                    .copied()
                    .unwrap_or(0);
                if now_ms.saturating_sub(last_check) >= self.rebalance_check_ms {
                    if let Some(ledger) = self.synthetic_spot.get_mut(sym) {
                        // 用 paper_state 的 qty × entry_price 估 perp notional 目標。
                        let perp_notional = pos.qty * pos.entry_price;
                        let spot_price_approx = ctx.index_price.unwrap_or(perp_price);
                        let drift = ledger.delta_drift_pct(perp_notional, spot_price_approx);
                        if drift > self.delta_drift_threshold {
                            ledger.rebalance(perp_notional, spot_price_approx, now_ms);
                            info!(
                                strategy = "funding_harvest",
                                symbol = sym,
                                drift,
                                rebalance_count = ledger.rebalance_count,
                                "synthetic spot leg rebalanced"
                            );
                        }
                    }
                    self.last_rebalance_check_ms.insert(sym.to_string(), now_ms);
                }
                vec![]
            }
            None if ctx.position_state.is_some() => {
                // cross-strategy 占用同 symbol（owner != self）→ skip，不動 cooldown。
                tracing::debug!(
                    strategy = "funding_harvest",
                    symbol = %sym,
                    cross_owner = %ctx
                        .position_state
                        .map(|p| p.owner_strategy.as_str())
                        .unwrap_or(""),
                    "skip entry: cross-strategy holds position"
                );
                vec![]
            }
            None => {
                // ── Entry 分支 ──
                if !ctx.h0_allowed {
                    return vec![];
                }

                if !self.cooldown.is_cooled_down(sym, now_ms) {
                    return vec![];
                }

                if !self.should_enter(funding_rate, basis_pct) {
                    return vec![];
                }

                // notional cap = position_cap_usd；qty = cap / perp_price。
                // 不變量：position_cap_usd 由 validate 保 (0, 100]。
                let qty_perp = self.position_cap_usd / perp_price;
                if !qty_perp.is_finite() || qty_perp <= 0.0 {
                    return vec![];
                }

                // PostOnly maker 入場（cost edge 假設 maker fee）。
                let maker_inputs = MakerPriceInputs {
                    last_price: perp_price,
                    best_bid: ctx.best_bid,
                    best_ask: ctx.best_ask,
                    tick_size: ctx.tick_size,
                };
                let limit_price = match compute_post_only_price(
                    false, // perp SHORT
                    maker_inputs,
                    FUNDING_HARVEST_MAKER_OFFSET_BPS,
                    FUNDING_HARVEST_MAKER_BUFFER_TICKS,
                    self.name(),
                    sym,
                ) {
                    Some(p) => p,
                    None => return vec![], // BBO 不完整 → fail-closed skip
                };

                // confidence scale：funding 越高、edge 越強 → 信心越高。
                let edge_bps = self.compute_net_edge_bps_per_period(funding_rate);
                let raw_conf = (edge_bps / 10.0).clamp(0.3, 0.9);
                let confidence =
                    crate::tick_pipeline::on_tick_helpers::clamp_confidence(raw_conf * self.conf_scale);

                // 入場前 snapshot cooldown，供 rejection rollback。
                self.snapshot_prev_cooldown(sym);
                self.cooldown.record_signal(sym, now_ms);

                info!(
                    strategy = "funding_harvest",
                    symbol = sym,
                    funding_rate,
                    basis_pct,
                    qty_perp,
                    limit_price,
                    "perp short entry intent emitted; synthetic spot leg pending fill"
                );

                // Round 2 finding 1：emit 改走 OrderIntent::new_trade helper。
                // funding_harvest perp 腿 always SHORT（is_long=false）；helper 自動
                // 派生 IntentType::OpenShort，消除 inline struct literal 路徑。
                vec![StrategyAction::Open(OrderIntent::new_trade(
                    sym.to_string(),
                    false, // perp SHORT
                    qty_perp,
                    confidence,
                    self.name().to_string(),
                    "limit".to_string(),
                    Some(limit_price),
                    None,
                    None,
                    Some(TimeInForce::PostOnly),
                    Some(FUNDING_HARVEST_MAKER_TIMEOUT_MS),
                ))]
            }
        }
    }

    /// perp fill confirmed → 開 synthetic spot 腿 ledger。
    /// 為什麼在 fill confirmed 才開：避免 perp fill 失敗時 spot ledger 殘留
    /// （fill-confirm 是唯一同步點）。
    fn on_fill(&mut self, intent: &OrderIntent, fill: &FillResult) {
        if intent.strategy != self.name() {
            return;
        }
        let sym = &intent.symbol;
        let perp_notional = fill.fill_qty * fill.fill_price;
        // spot price 近似用 perp fill price（demo 期間 OK；Stage 4 LIVE 升 real spot price）。
        // 不變量：notional > 0 才 open；防 0 / negative fill 導致 ledger 異常。
        if perp_notional <= 0.0 || fill.fill_price <= 0.0 {
            return;
        }
        // 注意 FillResult 結構不含 ts_ms 欄位；用當前 entry_ms HashMap 已有的
        // last_trade_ms（cooldown.last_ms）作為 entry timestamp 近似。
        // 為什麼不擴 FillResult：本 Wave 範圍只接 funding_harvest，避免改 core schema。
        let ts_ms = self
            .cooldown
            .last_ms(sym)
            .unwrap_or(0);

        let mut ledger = SyntheticSpotLedger::new();
        ledger.open_long(perp_notional, fill.fill_price, ts_ms);
        self.synthetic_spot.insert(sym.to_string(), ledger);
        self.entry_ms.insert(sym.to_string(), ts_ms);
        self.last_rebalance_check_ms.insert(sym.to_string(), ts_ms);
        info!(
            strategy = "funding_harvest",
            symbol = %sym,
            perp_notional,
            fill_price = fill.fill_price,
            ts_ms,
            "synthetic spot long opened on perp fill confirmation"
        );
    }

    /// strategy 自主 Close confirmed → realize synthetic spot 腿 PnL。
    ///
    /// Sprint 1B Bug 1 fix（C10 HYBRID-BUG）：
    /// 改用 caller 傳入的真實 close fill price + ts 結算，取代舊 `entry_price`
    /// fallback。舊行為 PnL ≡ 0 → spec §4.1 line 765「runtime PnL vs Stage 0R
    /// replay drift > 5%」對 nonzero replay PnL 結構性永真 → C10 永遠 demote。
    /// 新行為：synthetic spot 腿用真實價結算，runtime vs replay drift gate 才能
    /// 正常運作（drift < 5% 不 demote / drift ≥ 5% 才 demote）。
    fn on_close_confirmed(&mut self, symbol: &str, close_price: f64, close_ts_ms: u64) {
        if let Some(mut ledger) = self.synthetic_spot.remove(symbol) {
            let pnl = ledger.close(close_price, close_ts_ms);
            info!(
                strategy = "funding_harvest",
                symbol = %symbol,
                pnl_usd = pnl,
                close_price,
                close_ts_ms,
                rebalance_count = ledger.rebalance_count,
                "synthetic spot leg closed on perp close_confirmed"
            );
        }
        self.entry_ms.remove(symbol);
        self.last_rebalance_check_ms.remove(symbol);
    }

    /// 風控強平 perp → 同步清 synthetic spot 腿。
    /// 不變量：external close 必同步消 ledger，避免 orphan ledger 累積。
    ///
    /// Sprint 1B Bug 1 fix（C10 HYBRID-BUG）：同 `on_close_confirmed`，用真實
    /// close fill price + ts 結算 PnL。
    fn on_external_close(&mut self, symbol: &str, close_price: f64, close_ts_ms: u64) {
        if let Some(mut ledger) = self.synthetic_spot.remove(symbol) {
            let pnl = ledger.close(close_price, close_ts_ms);
            info!(
                strategy = "funding_harvest",
                symbol = %symbol,
                pnl_usd = pnl,
                close_price,
                close_ts_ms,
                "synthetic spot leg closed on external (risk) close"
            );
        }
        self.entry_ms.remove(symbol);
        self.last_rebalance_check_ms.remove(symbol);
    }

    /// strategy 自發的 Close 被跳過（paper_state 找不到倉位）→ 清 ledger。
    fn on_close_skipped(&mut self, symbol: &str) {
        self.synthetic_spot.remove(symbol);
        self.entry_ms.remove(symbol);
        self.last_rebalance_check_ms.remove(symbol);
    }

    /// W7-5 part 2：bootstrap 階段從 paper_state 重建 synthetic spot 腿 ledger。
    /// 為什麼：重啟後 paper_state 已由 bybit_sync 載入既有 perp 倉位；
    /// 本 strategy 對應 owner=funding_harvest 的 paper 倉位必須重新建 ledger，
    /// 否則 first tick 入 exit/rebalance 分支時 ledger 為空（noop）造成
    /// PnL 計算盲區。
    fn import_positions(&mut self, paper_state: &crate::paper_state::PaperState) {
        let mut imported = 0_usize;
        for pos in paper_state.positions() {
            if pos.owner_strategy == self.name() {
                let perp_notional = pos.qty * pos.entry_price;
                let mut ledger = SyntheticSpotLedger::new();
                // spot price 近似用 entry_price（重啟時無 live spot tick）；
                // 首次 rebalance check 時會用真實 spot price 修正。
                ledger.open_long(perp_notional, pos.entry_price, pos.entry_ts_ms);
                self.synthetic_spot.insert(pos.symbol.clone(), ledger);
                self.entry_ms.insert(pos.symbol.clone(), pos.entry_ts_ms);
                self.last_rebalance_check_ms
                    .insert(pos.symbol.clone(), pos.entry_ts_ms);
                imported += 1;
            }
        }
        if imported > 0 {
            info!(
                strategy = "funding_harvest",
                imported, "rebuilt synthetic spot ledgers from paper_state"
            );
        }
    }

    /// rejection rollback：funding_arb 範式 — 只回滾 cooldown，paper_state 不動。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        if intent.strategy != self.name() {
            return;
        }
        let sym = &intent.symbol;
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    // ── Phase 3a runtime tuning IPC ──

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: FundingHarvestUpdateParams =
            serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&FundingHarvestUpdateParams::param_ranges()).unwrap_or_default()
    }

    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }

    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}

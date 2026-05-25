//! Sprint 2 Alpha Tournament Candidate #1 — funding_short_v2 directional capture。
//!
//! MODULE_NOTE：
//!   模塊用途：funding rate > 30% annualized + short-only hard enforcement
//!     directional carry capture 策略，per W1-A spec v1.1 +
//!     W2-A finalize §3 schema 修正。
//!   入場條件（5 條件 ALL true）：
//!     1. funding_rate_8h_annualized > funding_threshold_annualized (default 30%)
//!     2. funding_rate_8h > 0（positive funding；負 funding hard reject 不轉 long）
//!     3. basis_pct < max_basis_pct × entry_basis_ratio (default 0.3%)
//!     4. compute_edge(funding_rate) > 0
//!     5. h0_allowed && cooldown_expired (per symbol, 8h)
//!   出場條件（OR 任一觸發）：
//!     1. funding_rate_annualized < funding_exit_annualized OR funding < 0
//!     2. compute_edge <= 0
//!     3. basis_pct > max_basis_pct
//!     4. now_ms - entry_ms > max_hold_ms (default 24h)
//!     5. P1 per_strategy stop_loss override (3% tight SL)
//!   方向：**short-only hard enforcement**（const IS_LONG: bool = false）。
//!   主要類函數：FundingShortV2、on_tick (Option A-Lite 三分支)、should_enter/exit、
//!     compute_edge、annualized_funding (pure helper)、FundingShortV2UpdateParams。
//!   依賴：super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown}、
//!     intent_processor::OrderIntent、tick_pipeline::TickContext、
//!     openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface}。
//!   硬邊界：
//!     - 不變量（spec §1.4 + §9 #1）：`const IS_LONG: bool = false` compile-time invariant；
//!       任何試圖 long 入場路徑必 fail-closed（never reached）。
//!     - 不變量（spec §0 + §1.3）：funding_threshold_annualized 預設 0.30 = 30%；
//!       params.rs validate floor 0.20 防 IPC 誤 patch break-even 以下。
//!     - 不變量（spec §0 + ADR-0018）：本 strategy 與 funding_arb V2 (dormant) 並列；
//!       不繞 V2 dormant 結論；不重啟 V2 directional path（V2 active=false 不動）。
//!     - 不變量（spec §1.4）：與 funding_arb 同 alpha source declaration
//!       (FundingSkew + Basis)；不引入新 source / 不依賴 Tier 3 microstructure。
//!     - 不變量（ADR-0036 Decision 1）：本 module 0 HMM / Markov-switching / GARCH 依賴。
//!     - Stage 1 限定 BTCUSDT / ETHUSDT；TOML validate 已擋；on_tick 再 fence 防 IPC
//!       直接 patch 結構繞 validate（per funding_harvest is_allowed_symbol 範式）。
//!     - active=false 預設；TOML 或 IPC active=true 才啟（fail-closed + 5-gate inherit）。
//!   spec ref:
//!     - srv/docs/execution_plan/2026-05-25--alpha_candidate_1_funding_short_v2_spec.md v1.1
//!     - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

pub mod params;

#[cfg(test)]
mod tests;

pub use params::FundingShortV2Params;
use params::{
    DEFAULT_COOLDOWN_MS, DEFAULT_ENTRY_BASIS_RATIO, DEFAULT_EXPECTED_PERIODS,
    DEFAULT_FUNDING_EXIT_ANNUALIZED, DEFAULT_FUNDING_THRESHOLD_ANNUALIZED, DEFAULT_MAX_BASIS_PCT,
    DEFAULT_MAX_HOLD_MS, DEFAULT_TOTAL_COST_BPS, FUNDING_THRESHOLD_FLOOR,
};

// ──────────────────────────────────────────────────────────────────────────
// 硬編碼不變量
// ──────────────────────────────────────────────────────────────────────────

/// **hard side enforcement**：funding_short_v2 永遠 short perp（never long）。
/// 為什麼 compile-time const：spec §1.4 + §9 #1 對抗式 review focus；
/// ADR-0018 V2 directional dormant 教訓 = bi-side 不可重啟。
/// 任何 IPC update / config patch 都無法翻轉此 const；保證 alpha thesis 不被退化為 V2。
const IS_LONG: bool = false;

/// funding_rate_8h → annualized 折算因子（Bybit V5：每日 3 × 8h funding cycles）。
/// 對齊 funding_harvest::annualized_funding 範式（3 × 365 = 1095 cycles/year）。
const CYCLES_PER_YEAR: f64 = 1095.0;

// PostOnly maker 入場參數（與 funding_arb / funding_harvest 範式對齊）。
// 為什麼固定常量：spec §6.2 maker entry pattern；cost edge gate 假設 perp 11 bps
// (entry maker 1bp + exit taker 5.5bp + slip 3bp + variability 12.5bp = 22 bps total)。
const FUNDING_SHORT_V2_MAKER_OFFSET_BPS: f64 = 1.0;
const FUNDING_SHORT_V2_MAKER_BUFFER_TICKS: u32 = 1;
const FUNDING_SHORT_V2_MAKER_TIMEOUT_MS: u64 = 45_000;

// ──────────────────────────────────────────────────────────────────────────
// FundingShortV2 strategy struct
// ──────────────────────────────────────────────────────────────────────────

pub struct FundingShortV2 {
    active: bool,
    /// per-symbol cooldown（同 funding_arb 範式；rollback 用 prev_last_trade_ms）。
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,

    /// Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
    pub allowed_symbols: Vec<String>,

    pub funding_threshold_annualized: f64,
    pub funding_exit_annualized: f64,
    pub max_basis_pct: f64,
    pub entry_basis_ratio: f64,
    pub max_hold_ms: u64,
    pub total_cost_bps: f64,
    pub expected_periods: f64,

    /// sentinel qty → IntentProcessor 套用 Kelly/risk sizing；
    /// 與 funding_arb 同範式（1e9 sentinel 不會作真實 qty 下單）。
    default_qty: f64,

    /// rejection rollback 用的 cooldown 快照（funding_arb 範式）。
    prev_last_trade_ms: HashMap<String, u64>,

    /// CONF-D：策略 confidence 縮放係數（預設 1.0）。
    conf_scale: f64,
}

impl Default for FundingShortV2 {
    fn default() -> Self {
        Self::new()
    }
}

impl FundingShortV2 {
    pub fn new() -> Self {
        Self {
            active: false,
            cooldown: TrendCooldown::new(DEFAULT_COOLDOWN_MS),
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            funding_threshold_annualized: DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            funding_exit_annualized: DEFAULT_FUNDING_EXIT_ANNUALIZED,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            default_qty: 1e9, // sentinel → IntentProcessor Kelly sizing
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// 8h funding rate → annualized 折算（Bybit V5：每日 3 cycles × 365 day）。
    /// 不變量：純函數，無 self 依賴；負 funding 折算為負 annualized
    /// （caller 用於 short-only reject path）。
    pub(crate) fn annualized_funding(funding_rate_8h: f64) -> f64 {
        funding_rate_8h * CYCLES_PER_YEAR
    }

    /// basis 百分比 = |perp / index − 1| × 100。
    /// 用 index_price 作 spot 近似（與 funding_arb / funding_harvest 範式一致）。
    /// 不變量：index_price 缺失或 ≤ 0 回 f64::MAX → 入場/出場 gate 必跳過（fail-closed）。
    pub(crate) fn compute_basis_pct(perp_price: f64, index_price: Option<f64>) -> f64 {
        match index_price {
            Some(ip) if ip > 0.0 => ((perp_price / ip) - 1.0).abs() * 100.0,
            _ => f64::MAX,
        }
    }

    /// Per-cycle net edge after amortized cost（純 funding rate scale，非 bps）。
    /// per spec §1.3：edge = |funding| - (total_cost_bps / 10000 / expected_periods)。
    /// 不變量：expected_periods 由 validate 保 ≥ 0.5；total_cost_bps 由 validate 保 [10, 100]。
    pub(crate) fn compute_edge(&self, funding_rate_8h: f64) -> f64 {
        let amortized_cost = self.total_cost_bps / 10_000.0 / self.expected_periods;
        funding_rate_8h.abs() - amortized_cost
    }

    /// 是否滿足入場條件（純函數，便於 unit test）。
    /// 不變量：funding_rate_8h <= 0 必 false（short-only hard side enforcement）。
    pub(crate) fn should_enter(&self, funding_rate_8h: f64, basis_pct: f64) -> bool {
        // hard side enforcement: 負 funding 必 reject（不轉 long）。
        if funding_rate_8h <= 0.0 {
            return false;
        }
        let annualized = Self::annualized_funding(funding_rate_8h);
        annualized > self.funding_threshold_annualized
            && self.compute_edge(funding_rate_8h) > 0.0
            && basis_pct < self.max_basis_pct * self.entry_basis_ratio
    }

    /// 是否滿足平倉條件（純函數）。
    pub(crate) fn should_exit(
        &self,
        funding_rate_8h: f64,
        basis_pct: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> bool {
        let annualized = Self::annualized_funding(funding_rate_8h);
        // 1. funding decay or 反轉。
        if annualized < self.funding_exit_annualized || funding_rate_8h < 0.0 {
            return true;
        }
        // 2. edge degradation。
        if self.compute_edge(funding_rate_8h) <= 0.0 {
            return true;
        }
        // 3. basis blowout。
        if basis_pct > self.max_basis_pct {
            return true;
        }
        // 4. time-stop。
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return true;
        }
        false
    }

    /// Stage 1 cohort fence：必 BTCUSDT / ETHUSDT。其他 symbol fail-closed skip。
    /// 為什麼：TOML validate 已擋越級，但 IPC update_params_json 路徑可能 patch
    /// allowed_symbols 進 ["BTCUSDT", "SOLUSDT"]，這裡再次 enforce（funding_harvest 範式）。
    fn is_allowed_symbol(&self, sym: &str) -> bool {
        self.allowed_symbols.iter().any(|s| s.as_str() == sym)
    }

    /// rejection rollback 用的 cooldown 快照（同 funding_arb 範式）。
    fn snapshot_prev_cooldown(&mut self, sym: &str) {
        self.prev_last_trade_ms
            .insert(sym.to_string(), self.cooldown.last_ms(sym).unwrap_or(0));
    }

    /// IPC `update_strategy_params` 熱更新；同步 active + 全範圍。
    /// active 包含在 update 路徑（與 funding_arb / funding_harvest 設計對齊）讓
    /// operator / Strategist 可在不重啟 engine 的情況下暫停 / 啟動策略。
    pub fn update_params(&mut self, params: FundingShortV2UpdateParams) -> Result<(), String> {
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
        info!(
            strategy = "funding_short_v2",
            active = self.active,
            funding_threshold_annualized = self.funding_threshold_annualized,
            "params updated via IPC"
        );
        Ok(())
    }

    /// 將當前 tunable 狀態快照成 IPC payload。
    pub fn get_params(&self) -> FundingShortV2UpdateParams {
        FundingShortV2UpdateParams {
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
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// FundingShortV2UpdateParams (IPC payload；與 FundingShortV2Params 同 schema
// 但作為 update payload 獨立)
// ──────────────────────────────────────────────────────────────────────────

/// IPC `update_strategy_params` 的 funding_short_v2 payload schema。
/// 與 `FundingShortV2Params`（TOML schema）刻意保持結構鏡像 + 同 validate，
/// 但類型分離避免 TOML-load schema 與 IPC-patch schema 耦合（funding_arb / funding_harvest 範式）。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FundingShortV2UpdateParams {
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
}

impl Default for FundingShortV2UpdateParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            funding_threshold_annualized: DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            funding_exit_annualized: DEFAULT_FUNDING_EXIT_ANNUALIZED,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
        }
    }
}

impl StrategyParams for FundingShortV2UpdateParams {
    /// 等同 `FundingShortV2Params::param_ranges`；委派以保單一定義。
    fn param_ranges() -> Vec<ParamRange> {
        FundingShortV2Params::param_ranges()
    }

    fn validate(&self) -> Result<(), String> {
        // 委派到 FundingShortV2Params::validate 保 invariant 唯一。
        // 不變量：funding_threshold_annualized 必 ≥ FUNDING_THRESHOLD_FLOOR (0.20)，
        // 防 IPC 誤 patch break-even 以下（spec §9 #2）。
        let mirror = FundingShortV2Params {
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
        };
        // Floor double-check（防 unused import warning + 文檔化此 invariant）。
        debug_assert!(
            mirror.funding_threshold_annualized >= FUNDING_THRESHOLD_FLOOR || mirror.validate().is_err(),
            "funding_threshold_annualized below floor must reject in validate"
        );
        mirror.validate()
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Strategy trait impl
// ──────────────────────────────────────────────────────────────────────────

impl Strategy for FundingShortV2 {
    fn name(&self) -> &str {
        "funding_short_v2"
    }

    fn is_active(&self) -> bool {
        self.active
    }

    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// W-AUDIT-8a Phase A：funding_short_v2 聲明消費 FundingSkew + Basis（與 funding_arb /
    /// funding_harvest 一致）。Tier 3 LiquidationCascade / OI 不依賴。
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

        // Stage 1 cohort fence：只允 allowed_symbols。
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

        // ── 三分支（funding_arb / funding_harvest Option A-Lite 範式）──
        // 1. 自家倉位（owner == self.name()）→ exit branch
        // 2. 他家倉位（cross-strategy occupied）→ skip
        // 3. 無倉位 → entry branch
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            Some(pos) => {
                // Exit 分支
                if self.should_exit(funding_rate, basis_pct, now_ms, pos.entry_ts_ms) {
                    self.snapshot_prev_cooldown(sym);
                    self.cooldown.record_signal(sym, now_ms);

                    let mut confidence = 0.8 * self.conf_scale;
                    confidence = confidence.clamp(0.0, 1.0);

                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence,
                        reason: format!(
                            "funding_short_v2_exit: annualized={:.4} basis={:.3}% hold_ms={}",
                            Self::annualized_funding(funding_rate),
                            basis_pct,
                            now_ms.saturating_sub(pos.entry_ts_ms)
                        ),
                    }];
                }
                vec![]
            }
            None if ctx.position_state.is_some() => {
                // cross-strategy 占用同 symbol → skip entry，不動 cooldown。
                tracing::debug!(
                    strategy = "funding_short_v2",
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

                // 5 entry conditions 全交給 should_enter 純函式（含 short-only hard reject）。
                if !self.should_enter(funding_rate, basis_pct) {
                    return vec![];
                }

                // confidence scale：annualized 越高、edge 越強 → 信心越高
                // (30%→0.4, 60%+→0.9)。
                let annualized = Self::annualized_funding(funding_rate);
                let raw_conf = ((annualized - self.funding_threshold_annualized) / 0.30 + 0.4)
                    .clamp(0.4, 0.9);
                let confidence = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
                    raw_conf * self.conf_scale,
                );

                let maker_inputs = MakerPriceInputs {
                    last_price: perp_price,
                    best_bid: ctx.best_bid,
                    best_ask: ctx.best_ask,
                    tick_size: ctx.tick_size,
                };

                // short-only hard enforcement：IS_LONG 為 compile-time const false。
                // 任何 IPC / config patch 都無法翻轉；保證 alpha thesis 不退化為 V2 bi-side。
                let limit_price = match compute_post_only_price(
                    IS_LONG, // const false
                    maker_inputs,
                    FUNDING_SHORT_V2_MAKER_OFFSET_BPS,
                    FUNDING_SHORT_V2_MAKER_BUFFER_TICKS,
                    self.name(),
                    sym,
                ) {
                    Some(price) => price,
                    None => return vec![], // BBO 不完整 → fail-closed skip
                };

                // 入場前 snapshot cooldown，供 rejection rollback。
                self.snapshot_prev_cooldown(sym);
                self.cooldown.record_signal(sym, now_ms);

                info!(
                    strategy = "funding_short_v2",
                    symbol = sym,
                    funding_rate,
                    annualized,
                    basis_pct,
                    edge = self.compute_edge(funding_rate),
                    limit_price,
                    "short perp entry intent emitted (hard side enforcement)"
                );

                // emit 走 OrderIntent::new_trade helper；is_long=false → 自動派生 OpenShort。
                vec![StrategyAction::Open(OrderIntent::new_trade(
                    sym.to_string(),
                    IS_LONG, // const false — short-only
                    self.default_qty,
                    confidence,
                    self.name().to_string(),
                    "limit".to_string(),
                    Some(limit_price),
                    None,
                    None,
                    Some(TimeInForce::PostOnly),
                    Some(FUNDING_SHORT_V2_MAKER_TIMEOUT_MS),
                ))]
            }
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

    // on_external_close / on_fill / import_positions：
    // funding_short_v2 不持有 strategy-local position state（Option A-Lite），
    // 全部由 ctx.position_state 從 paper_state 注入；3 個 hook 用 trait default no-op。

    // ── Phase 3a runtime tuning IPC ──

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: FundingShortV2UpdateParams =
            serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&FundingShortV2UpdateParams::param_ranges()).unwrap_or_default()
    }

    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }

    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}

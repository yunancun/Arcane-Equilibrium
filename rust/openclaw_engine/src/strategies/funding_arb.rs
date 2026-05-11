//! 資金費率套利策略 V2 — 方向性資金費率捕獲（dormant per ADR-0018 / AMD-2026-05-09-02）。
//!
//! MODULE_NOTE：入場：|資金費率| > 閾值 + 扣除成本後 edge > 0 + 基差 < 上限。
//!   正資金費率 → 做空永續（收取資金費率），負資金費率 → 做多永續。
//!   出場：費率反轉 | edge ≤ 0 | 基差 > 上限 | 最大持有 72h。
//!   使用 TickContext.funding_rate（WS tickers）+ TickContext.index_price 計算基差。
//!
//! P0 Option A-Lite Wave 1（2026-05-11）：以 paper_state 為 position SSoT。
//!   - 移除 `self.positions: PerSymbolState<FundingPosition>`
//!   - on_tick 透過 `ctx.position_state.owner_strategy == self.name()` 判斷自家倉位
//!   - FundingPosition 兩欄位均可從 PaperPosition 推導（`is_positive_funding = !is_long`，
//!     `entry_ms = entry_ts_ms`），不需保留任何 strategy-internal position state。
//!   - 對比 bb_breakout：funding_arb 無 trailing_stop / squeeze_detected_ms / oi_buffer 等
//!     必保留的 strategy-internal state，可全套 Option A-Lite 模式。
//!   - dormant active=false 不變；本 wave 為純結構同步，零 runtime 影響。
//!
//! 保留：`cooldown` + `prev_last_trade_ms`（用作拒絕回滾 cooldown，與 positions 解耦）。

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

// QC-H10: Constants retained as defaults only — runtime uses struct fields.
// QC-H10：常量僅作為默認值保留 — 運行時使用 struct 欄位。
const DEFAULT_TOTAL_COST_BPS: f64 = 34.0; // perp(11) + spot(20) + slippage(3)
const DEFAULT_EXPECTED_PERIODS: f64 = 3.0; // 8h funding periods
const DEFAULT_FUNDING_THRESHOLD: f64 = 0.0005; // 5 bps
const DEFAULT_MAX_BASIS_PCT: f64 = 0.5;
const DEFAULT_MAX_HOLD_MS: u64 = 72 * 3_600_000;
const DEFAULT_ENTRY_BASIS_RATIO: f64 = 0.8;
const FUNDING_ARB_MAKER_OFFSET_BPS: f64 = 1.0;
const FUNDING_ARB_MAKER_BUFFER_TICKS: u32 = 1;
const FUNDING_ARB_MAKER_TIMEOUT_MS: u64 = 45_000;

pub struct FundingArb {
    active: bool,
    /// 逐幣種冷卻時間。Option A-Lite 後：cooldown 與 positions 解耦，純粹防 re-entry。
    /// 未見 symbol 視為 "cooled"，`saturating_sub` 防時鐘回退。
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,
    default_qty: f64,
    // QC-H10：參數化常量（原為模組級常量）。
    pub(crate) total_cost_bps: f64,
    pub(crate) expected_periods: f64,
    pub(crate) funding_threshold: f64,
    pub(crate) max_basis_pct: f64,
    pub(crate) max_hold_ms: u64,
    // 入場基差 = max_basis_pct * entry_basis_ratio；遲滯防止瞬間出場。
    pub(crate) entry_basis_ratio: f64,
    // RC-04 + Option A-Lite：僅保留 cooldown rollback 所需的前一次 trade_ms 快照。
    // positions rollback 已移除（paper_state 為 SSoT，rejection 不撤銷 paper_state）。
    prev_last_trade_ms: HashMap<String, u64>,
}

impl FundingArb {
    pub fn new() -> Self {
        Self {
            active: false,
            cooldown: TrendCooldown::new(3_600_000),
            cooldown_ms: 3_600_000, // 1h cooldown
            default_qty: 1e9,       // sentinel → IntentProcessor applies risk sizing
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            funding_threshold: DEFAULT_FUNDING_THRESHOLD,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            prev_last_trade_ms: HashMap::new(),
        }
    }

    /// Compute net edge after amortized costs.
    /// 計算扣除攤銷成本後的淨 edge。
    fn compute_edge(&self, funding_rate: f64) -> f64 {
        let amortized_fee = self.total_cost_bps / 10_000.0 / self.expected_periods;
        funding_rate.abs() - amortized_fee
    }

    /// Compute basis (perp vs index price divergence) as percentage.
    /// 計算基差（永續 vs 指數價格偏離）百分比。
    fn compute_basis_pct(perp_price: f64, index_price: Option<f64>) -> f64 {
        match index_price {
            Some(ip) if ip > 0.0 => ((perp_price / ip) - 1.0).abs() * 100.0,
            _ => 0.0, // no index price → assume no basis risk
        }
    }

    /// Option A-Lite：以 ctx.position_state 作為持倉 SSoT，由 on_tick 傳入 `is_long` + `entry_ms`。
    /// 之前簽名 `(symbol, ...)` 帶 self.positions lookup；現改為純函式風格。
    ///
    /// Args:
    /// - `is_long_position`：是否持多。對應原 `is_positive_funding = !is_long`，這裡反向折算回來，
    ///   `is_positive_funding = !is_long_position`（與 on_tick 入場時 `is_long = !is_positive` 一致）。
    /// - `entry_ms`：對應 PaperPosition.entry_ts_ms。
    fn should_exit(
        &self,
        is_long_position: bool,
        funding_rate: f64,
        basis_pct: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> bool {
        // 反推 funding direction：is_long=true ⇔ 進場時 funding<0（is_positive_funding=false）
        // 與 on_tick 入場規則 `is_long = !is_positive` 一致。
        let is_positive_funding = !is_long_position;

        // 費率翻轉
        if is_positive_funding && funding_rate < 0.0 {
            return true;
        }
        if !is_positive_funding && funding_rate > 0.0 {
            return true;
        }

        // Edge 不再為正 — 與入場邏輯一致。
        if self.compute_edge(funding_rate) <= 0.0 {
            return true;
        }

        // 基差風險
        if basis_pct > self.max_basis_pct {
            return true;
        }

        // 超過最大持有時間
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return true;
        }

        false
    }

    /// Option A-Lite：僅快照 cooldown，positions 由 paper_state SSoT 管理。
    /// 將 TrendCooldown 未記錄的 symbol 映射為 0，保留原先「未見 → 0」的哨兵慣例。
    fn snapshot_prev_cooldown(&mut self, sym: &str) {
        self.prev_last_trade_ms
            .insert(sym.to_string(), self.cooldown.last_ms(sym).unwrap_or(0));
    }

    // ── Phase 3a: Runtime parameter tuning (AGT-1) / 運行時參數調參 ──

    /// Apply a validated param bundle to the live strategy instance.
    /// Unlike peer strategies, this path also honors `active` so IPC can pause
    /// the strategy without an engine restart (G-2 v2 NEGATIVE EDGE 2026-04-18).
    /// 將已驗證的參數包套用到運行中的策略實例。
    /// 與其他策略不同，此路徑同時處理 `active` 欄位，讓 IPC 能在不重啟引擎的
    /// 情況下暫停該策略（G-2 v2 判決 NEGATIVE EDGE 2026-04-18）。
    pub fn update_params(&mut self, params: FundingArbUpdateParams) -> Result<(), String> {
        params.validate()?;
        self.active = params.active;
        self.cooldown_ms = params.cooldown_ms;
        // E1-P0-2: Hot-reload TrendCooldown's duration in lockstep with
        // cooldown_ms so future `is_cooled_down` calls honor the new value
        // without clearing existing per-symbol timestamps.
        // E1-P0-2：熱更新 TrendCooldown 時長，不清空既有時戳。
        self.cooldown.set_duration(params.cooldown_ms);
        self.total_cost_bps = params.total_cost_bps;
        self.expected_periods = params.expected_periods;
        self.funding_threshold = params.funding_threshold;
        self.max_basis_pct = params.max_basis_pct;
        self.max_hold_ms = params.max_hold_ms;
        self.entry_basis_ratio = params.entry_basis_ratio;
        info!(
            strategy = "funding_arb",
            active = self.active,
            "params updated via IPC / 參數已通過 IPC 更新"
        );
        Ok(())
    }

    /// Snapshot the current tunable state as a params bundle.
    /// 將當前可調狀態快照為參數包。
    pub fn get_params(&self) -> FundingArbUpdateParams {
        FundingArbUpdateParams {
            active: self.active,
            cooldown_ms: self.cooldown_ms,
            total_cost_bps: self.total_cost_bps,
            expected_periods: self.expected_periods,
            funding_threshold: self.funding_threshold,
            max_basis_pct: self.max_basis_pct,
            max_hold_ms: self.max_hold_ms,
            entry_basis_ratio: self.entry_basis_ratio,
        }
    }
}

/// Tunable parameters for FundingArb, exposed via `update_strategy_params` IPC.
/// Intentionally includes `active` so operator/Strategist can pause the strategy
/// without an engine restart — funding_arb peer strategies (ma_crossover,
/// bb_reversion, …) keep `active` out of their update_params payloads because
/// TOML is the source of truth there. For FundingArb the asymmetry is deliberate
/// and documented in `update_params`. Distinct from `crate::strategies::
/// FundingArbParams`, which is the TOML-load schema owned by `StrategyParamsConfig`.
/// FundingArb 可通過 `update_strategy_params` IPC 調整的參數。
/// 有意包含 `active`，讓 operator/Strategist 可在不重啟引擎的情況下暫停該策略 —
/// 其他策略（ma_crossover、bb_reversion、…）不含 `active`，因為 TOML 是權威。
/// 此處 funding_arb 的不對稱是刻意的，並記錄在 `update_params`。
/// 與 `crate::strategies::FundingArbParams`（TOML 載入 schema）為兩個獨立結構。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct FundingArbUpdateParams {
    pub active: bool,
    pub cooldown_ms: u64,
    pub total_cost_bps: f64,
    pub expected_periods: f64,
    pub funding_threshold: f64,
    pub max_basis_pct: f64,
    pub max_hold_ms: u64,
    pub entry_basis_ratio: f64,
}

impl Default for FundingArbUpdateParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: 3_600_000,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            funding_threshold: DEFAULT_FUNDING_THRESHOLD,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
        }
    }
}

impl StrategyParams for FundingArbUpdateParams {
    fn param_ranges() -> Vec<ParamRange> {
        // `active` deliberately omitted: it's a binary gate, not a tunable,
        // so it's not exposed to Optuna/Strategist search spaces.
        // `active` 故意省略：它是二元閘門而非可調參數，不進入自動調參搜索空間。
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 60_000.0,
                max: 24.0 * 3_600_000.0,
                step: Some(60_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "total_cost_bps".into(),
                min: 1.0,
                max: 200.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "expected_periods".into(),
                min: 0.5,
                max: 30.0,
                step: Some(0.5),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "funding_threshold".into(),
                min: 0.0001,
                max: 0.01,
                step: Some(0.0001),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_basis_pct".into(),
                min: 0.05,
                max: 2.0,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_hold_ms".into(),
                min: 60_000.0,
                max: 30.0 * 24.0 * 3_600_000.0,
                step: Some(3_600_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "entry_basis_ratio".into(),
                min: 0.0,
                max: 1.0,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.cooldown_ms < 60_000 || self.cooldown_ms > 24 * 3_600_000 {
            return Err("cooldown_ms must be in [60s, 24h]".into());
        }
        if !(1.0..=200.0).contains(&self.total_cost_bps) {
            return Err("total_cost_bps must be in [1, 200]".into());
        }
        // expected_periods must stay strictly positive; compute_edge divides by it.
        // expected_periods 必須嚴格為正；compute_edge 用它做除數。
        if !(0.5..=30.0).contains(&self.expected_periods) {
            return Err("expected_periods must be in [0.5, 30]".into());
        }
        if !(0.0001..=0.01).contains(&self.funding_threshold) {
            return Err("funding_threshold must be in [0.0001, 0.01]".into());
        }
        if !(0.05..=2.0).contains(&self.max_basis_pct) {
            return Err("max_basis_pct must be in [0.05, 2.0]".into());
        }
        if self.max_hold_ms < 60_000 || self.max_hold_ms > 30 * 24 * 3_600_000 {
            return Err("max_hold_ms must be in [60s, 30d]".into());
        }
        if !(0.0..=1.0).contains(&self.entry_basis_ratio) {
            return Err("entry_basis_ratio must be in [0, 1]".into());
        }
        Ok(())
    }
}

impl Strategy for FundingArb {
    fn name(&self) -> &str {
        "funding_arb"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// W-AUDIT-8a Phase A spec §3 Phase A Deliverable #3：
    /// `funding_arb`：`[FundingSkew, Basis]`（已退休但保留 declare 以對齊 spec）。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::FundingSkew, AlphaSourceTag::Basis];
        TAGS
    }

    /// Option A-Lite：拒絕時僅回滾 cooldown（positions 由 paper_state SSoT 管理，無需回滾）。
    ///
    /// 與舊版差異：
    /// - 移除 `prev_positions` rollback 路徑（self.positions 已不存在）
    /// - 保留 cooldown rollback：rejection 後 cooldown 應回到入場前的「未見」/前次狀態，
    ///   讓策略有機會在 cooldown 邊界附近重新嘗試（與 ma_crossover / bb_reversion 風格一致）
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                // 哨兵 0 → 原本無紀錄；清掉 cooldown 條目回到「未見」狀態。
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    // on_external_close / on_fill / import_positions：
    // Option A-Lite 後 funding_arb 不再持有 strategy-local position state，
    // 全部由 ctx.position_state 從 paper_state 注入，這 3 個 hook 改用 trait default no-op。
    // 對比 bb_breakout：funding_arb 無 trailing_stop / squeeze_detected_ms / oi_buffer 等
    // 必保留的 strategy-internal lifecycle 欄位，可乾淨退化為 trait default。

    /// OC-5：資金費率捕獲 — edge > 0 時入場，費率翻轉/基差/超時出場。
    ///
    /// Option A-Lite：以 ctx.position_state 為 SSoT 判斷自家持倉。
    /// 三分支：
    ///   1. 自家倉位（owner=self.name()）→ exit logic
    ///   2. 他家倉位（cross-strategy occupied）→ skip entry，不動 cooldown
    ///   3. 無倉位（None）→ entry logic
    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        let sym = ctx.symbol;
        let now_ms = ctx.timestamp_ms;

        // 必須有資金費率數據
        let funding_rate = match ctx.funding_rate {
            Some(fr) if fr.abs() > f64::EPSILON => fr,
            _ => return vec![],
        };

        let basis_pct = Self::compute_basis_pct(ctx.price, ctx.index_price);

        // ── Position SSoT 判定（Option A-Lite）──
        // 過濾 owner_strategy == self.name()：只有「自家」倉位才走 exit 分支；
        // bybit_sync / orphan_adopted / 其他策略 owner 視為 cross-strategy occupied。
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            // ── Exit 分支：自家倉位，評估出場 ──
            Some(pos) => {
                if self.should_exit(pos.is_long, funding_rate, basis_pct, now_ms, pos.entry_ts_ms) {
                    // 出場前快照 cooldown（rejection 時可回滾）
                    self.snapshot_prev_cooldown(sym);
                    self.cooldown.record_signal(sym, now_ms);

                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence: 0.8,
                        reason: format!(
                            "funding_arb_exit: rate={:.6} basis={:.3}%",
                            funding_rate, basis_pct
                        ),
                    }];
                }
                // 持倉中，無出場信號
                return vec![];
            }
            // ── Cross-strategy 占用：跳過入場（避免 router gate 1.5 duplicate_position 撞）──
            None if ctx.position_state.is_some() => {
                tracing::debug!(
                    strategy = "funding_arb",
                    symbol = %sym,
                    cross_owner = %ctx.position_state.map(|p| p.owner_strategy.as_str()).unwrap_or(""),
                    "skip entry: cross-strategy holds position"
                );
                return vec![];
            }
            // ── Entry 分支：無持倉，評估入場 ──
            None => {}
        }

        // H0 門控
        if !ctx.h0_allowed {
            return vec![];
        }

        // 冷卻期（E1-P0-2：委派給 TrendCooldown，語意不變）
        if !self.cooldown.is_cooled_down(sym, now_ms) {
            return vec![];
        }

        // Funding rate must exceed threshold / 資金費率必須超過閾值
        if funding_rate.abs() < self.funding_threshold {
            return vec![];
        }

        // Edge must be positive after cost / 扣除成本後 edge 必須為正
        let edge = self.compute_edge(funding_rate);
        if edge <= 0.0 {
            return vec![];
        }

        // Entry basis tighter than exit — hysteresis prevents instant exit.
        // 入場基差比出場更嚴格 — 遲滯防止瞬間出場。
        if basis_pct > self.max_basis_pct * self.entry_basis_ratio {
            return vec![];
        }

        // Direction: positive funding → short perp (shorts receive funding payment),
        //            negative funding → long perp (longs receive funding payment).
        // 方向：正資金費率 → 做空永續（空頭收取費率），負 → 做多永續。
        let is_positive = funding_rate > 0.0;
        let is_long = !is_positive;

        // Confidence scales with edge magnitude (3bps→0.3, 9+bps→0.9).
        // 信心隨 edge 幅度縮放。
        let edge_bps = edge * 10_000.0;
        let confidence = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
            (edge_bps / 10.0).clamp(0.3, 0.9),
        );

        let maker_inputs = MakerPriceInputs {
            last_price: ctx.price,
            best_bid: ctx.best_bid,
            best_ask: ctx.best_ask,
            tick_size: ctx.tick_size,
        };
        let limit_price = match compute_post_only_price(
            is_long,
            maker_inputs,
            FUNDING_ARB_MAKER_OFFSET_BPS,
            FUNDING_ARB_MAKER_BUFFER_TICKS,
            self.name(),
            sym,
        ) {
            Some(price) => price,
            None => return vec![],
        };

        // 入場前快照 cooldown（rejection 時可回滾，與 ma_crossover / bb_reversion 一致）
        self.snapshot_prev_cooldown(sym);

        // Option A-Lite：不再寫 self.positions；paper_state 由 IntentProcessor 在 fill 後寫入。
        // 在 fill confirm 前 cooldown 已 record，防 same-tick re-emit。
        self.cooldown.record_signal(sym, now_ms);

        vec![StrategyAction::Open(OrderIntent {
            symbol: sym.to_string(),
            is_long,
            qty: self.default_qty, // sentinel → IntentProcessor applies Kelly/risk sizing
            confidence,
            strategy: self.name().into(),
            order_type: "limit".into(),
            limit_price: Some(limit_price),
            // FundingArb has no confluence scoring / persistence tracker; leave
            // features unset so feature_builder fills 0.0 placeholders.
            // FundingArb 無 confluence/persistence；feature_builder 會填 0。
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(FUNDING_ARB_MAKER_TIMEOUT_MS),
        })]
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: FundingArbUpdateParams =
            serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&FundingArbUpdateParams::param_ranges()).unwrap_or_default()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_ctx(
        symbol: &'static str,
        price: f64,
        ts: u64,
        funding_rate: Option<f64>,
        index_price: Option<f64>,
    ) -> TickContext<'static> {
        TickContext {
            symbol,
            price,
            timestamp_ms: ts,
            indicators: None,
            indicators_5m: None,
            signals: &[],
            h0_allowed: true,
            funding_rate,
            index_price,
            open_interest: None,
            best_bid: Some(price * 0.9999),
            best_ask: Some(price * 1.0001),
            tick_size: Some((price * 0.000001).max(0.0001)),
            alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
            position_state: None,
            is_pinned: true,
        }
    }

    /// Option A-Lite test helper：以 PaperPosition 建立 ctx 模擬「自家持倉」
    /// `is_positive_funding=true` ⇔ `is_long=false`（與 on_tick 入場規則一致）。
    /// 注意：呼叫端若需要其他 ctx 欄位，請直接構造 TickContext，不要依賴此 helper。
    fn make_position(
        symbol: String,
        is_positive_funding: bool,
        entry_ms: u64,
        owner: &str,
    ) -> crate::paper_state::containers::PaperPosition {
        crate::paper_state::containers::PaperPosition {
            symbol,
            is_long: !is_positive_funding,
            qty: 1.0,
            entry_price: 50_000.0,
            best_price: 50_000.0,
            entry_fee: 0.0,
            entry_ts_ms: entry_ms,
            unrealized_pnl: 0.0,
            entry_context_id: String::new(),
            owner_strategy: owner.to_string(),
            entry_notional: 50_000.0,
            peak_reached_ts_ms: entry_ms as i64,
            max_favorable_pnl_pct: 0.0,
        }
    }

    /// 構造 ctx 並附帶自家持倉（owner=funding_arb），便於測試 exit 分支。
    fn ctx_with_owned_position<'a>(
        base: TickContext<'a>,
        position: &'a crate::paper_state::containers::PaperPosition,
    ) -> TickContext<'a> {
        TickContext {
            position_state: Some(position),
            ..base
        }
    }

    // ═════════════════════════════════════════════════════════════════════
    // Edge computation / Edge 計算
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_edge_positive() {
        let s = FundingArb::new();
        let edge = s.compute_edge(0.005); // 50 bps — well above amortized cost
        assert!(edge > 0.0);
    }

    #[test]
    fn test_edge_negative_small_rate() {
        let s = FundingArb::new();
        let edge = s.compute_edge(0.0001); // 1 bps, below amortized cost
        assert!(edge < 0.0);
    }

    #[test]
    fn test_edge_at_threshold() {
        let s = FundingArb::new();
        // amortized_fee = 34/10000/3 = 0.001133...
        let edge = s.compute_edge(0.001133);
        assert!(edge.abs() < 0.0001, "edge near zero at threshold");
    }

    // ═════════════════════════════════════════════════════════════════════
    // Basis calculation / 基差計算
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_basis_pct_normal() {
        // perp=60300, index=60000 → basis = |60300/60000 - 1| * 100 = 0.5%
        let bp = FundingArb::compute_basis_pct(60300.0, Some(60000.0));
        assert!((bp - 0.5).abs() < 0.01);
    }

    #[test]
    fn test_basis_pct_no_index() {
        let bp = FundingArb::compute_basis_pct(60000.0, None);
        assert!(bp.abs() < f64::EPSILON, "no index → 0 basis");
    }

    #[test]
    fn test_basis_pct_zero_index() {
        let bp = FundingArb::compute_basis_pct(60000.0, Some(0.0));
        assert!(bp.abs() < f64::EPSILON, "zero index → 0 basis");
    }

    // ═════════════════════════════════════════════════════════════════════
    // Exit conditions / 出場條件
    // ═════════════════════════════════════════════════════════════════════

    // Option A-Lite：should_exit 簽名改為 (is_long_position, rate, basis, now, entry_ms)。
    // is_positive_funding=true ⇔ is_long_position=false（short perp）。

    #[test]
    fn test_should_exit_rate_flip() {
        let s = FundingArb::new();
        // 原 insert_position(true, ..) ⇔ is_long_position=false（short perp / positive funding）
        assert!(s.should_exit(false, -0.001, 0.1, 1000, 0));
    }

    #[test]
    fn test_should_exit_max_hold() {
        let s = FundingArb::new();
        assert!(s.should_exit(false, 0.001, 0.1, DEFAULT_MAX_HOLD_MS + 1, 0));
    }

    #[test]
    fn test_should_exit_basis_risk() {
        let s = FundingArb::new();
        // basis > 0.5%
        assert!(s.should_exit(false, 0.001, 0.6, 1000, 0));
    }

    #[test]
    fn test_no_exit_normal() {
        let s = FundingArb::new();
        // Rate 0.005 → edge = 0.005 - 0.001133 = 0.00387 > 0 → no exit
        assert!(!s.should_exit(false, 0.005, 0.1, 1000, 0));
    }

    #[test]
    fn test_multi_symbol_positions() {
        let s = FundingArb::new();
        // BTC short（positive_funding=true ⇔ is_long=false）rate flip → exit
        assert!(s.should_exit(false, -0.001, 0.1, 1000, 0));
        // ETH long（positive_funding=false ⇔ is_long=true）rate -0.003 仍負 → no flip → no exit
        assert!(!s.should_exit(true, -0.003, 0.1, 1000, 0));
    }

    // ═════════════════════════════════════════════════════════════════════
    // on_tick entry / 入場邏輯
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_on_tick_no_funding_rate_no_action() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let ctx = make_ctx("BTC", 50000.0, 0, None, None);
        assert!(s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(), "no funding rate → no action");
    }

    #[test]
    fn test_on_tick_below_threshold_no_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // 1 bps = 0.0001, below default threshold 5 bps
        let ctx = make_ctx("BTC", 50000.0, 0, Some(0.0001), Some(50000.0));
        assert!(s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(), "below threshold → no entry");
    }

    #[test]
    fn test_on_tick_positive_edge_entry_short() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // 50 bps funding rate, well above cost → positive edge → short entry
        let ctx = make_ctx("BTCUSDT", 50000.0, 100_000, Some(0.005), Some(50000.0));
        let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Open(intent) => {
                assert!(!intent.is_long, "positive funding → short");
                assert_eq!(intent.symbol, "BTCUSDT");
                assert_eq!(intent.strategy, "funding_arb");
                assert_eq!(intent.order_type, "limit");
                assert!(intent.limit_price.is_some());
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                assert_eq!(intent.maker_timeout_ms, Some(FUNDING_ARB_MAKER_TIMEOUT_MS));
                assert!(intent.confidence >= 0.3 && intent.confidence <= 0.9);
            }
            other => panic!("expected Open, got {:?}", other),
        }
        // Option A-Lite：策略不再持有 self.positions；改驗 cooldown 已記錄。
        assert!(
            s.cooldown.last_ms("BTCUSDT").is_some(),
            "cooldown recorded after entry"
        );
    }

    #[test]
    fn test_on_tick_negative_funding_entry_long() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // -50 bps → long entry
        let ctx = make_ctx("ETHUSDT", 3000.0, 100_000, Some(-0.005), Some(3000.0));
        let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Open(intent) => {
                assert!(intent.is_long, "negative funding → long");
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_on_tick_missing_bbo_skips_maker_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let ctx = TickContext {
            symbol: "BTCUSDT",
            price: 50000.0,
            timestamp_ms: 100_000,
            indicators: None,
            indicators_5m: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: Some(0.005),
            index_price: Some(50000.0),
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: Some(0.1),
            alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
            position_state: None,
            is_pinned: true,
        };
        assert!(
            s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(),
            "funding_arb must not fall back to market entry when BBO is missing"
        );
        // Option A-Lite：maker skip 不應記錄 cooldown（snapshot_prev_cooldown + record_signal
        // 在 maker price 計算後才執行，這裡 limit_price=None 提前 return 故 cooldown 未動）。
        assert!(
            s.cooldown.last_ms("BTCUSDT").is_none(),
            "maker skip must not record cooldown"
        );
    }

    #[test]
    fn test_on_tick_cooldown_blocks_re_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let ctx1 = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(50000.0));
        assert_eq!(s.on_tick(&ctx1, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).len(), 1, "first entry");

        // Option A-Lite：策略本地無 positions，cooldown 在 entry 後已 record。
        // 第二 tick 無持倉（position_state=None）走 entry 分支但被 cooldown 擋住。

        // Within cooldown (1h = 3_600_000ms)
        let ctx2 = make_ctx("BTC", 50000.0, 200_000, Some(0.005), Some(50000.0));
        assert!(s.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(), "cooldown blocks re-entry");

        // After cooldown
        let ctx3 = make_ctx(
            "BTC",
            50000.0,
            100_000 + 3_600_001,
            Some(0.005),
            Some(50000.0),
        );
        assert_eq!(s.on_tick(&ctx3, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).len(), 1, "after cooldown → entry");
    }

    #[test]
    fn test_on_tick_h0_blocked_no_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let ctx = TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: 100_000,
            indicators: None,
            indicators_5m: None,
            signals: &[],
            h0_allowed: false, // H0 blocks
            funding_rate: Some(0.005),
            index_price: Some(50000.0),
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
            alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
            position_state: None,
            is_pinned: true,
        };
        assert!(s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(), "H0 blocked → no entry");
    }

    #[test]
    fn test_on_tick_basis_too_wide_blocks_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // index=49750 → basis ≈ 0.503% > entry limit 0.4% → blocked
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(49750.0));
        assert!(s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(), "wide basis → no entry");
    }

    // ═════════════════════════════════════════════════════════════════════
    // on_tick exit / 出場邏輯
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_on_tick_exit_on_rate_flip() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // Option A-Lite：以 ctx.position_state 模擬自家持倉（positive funding=true ⇔ is_long=false）。
        let pos = make_position("BTC".to_string(), true, 0, "funding_arb");
        let base = make_ctx("BTC", 50000.0, 100_000, Some(-0.001), Some(50000.0));
        let ctx = ctx_with_owned_position(base, &pos);

        // Rate flipped negative → exit
        let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Close { symbol, reason, .. } => {
                assert_eq!(symbol, "BTC");
                assert!(reason.contains("funding_arb_exit"));
            }
            other => panic!("expected Close, got {:?}", other),
        }
        // Option A-Lite：策略不再清 self.positions；paper_state 由 IntentProcessor close 後 mutate。
        // 此測試驗證 close 已 emit + cooldown 已 record。
        assert!(s.cooldown.last_ms("BTC").is_some(), "cooldown stamped on exit");
    }

    #[test]
    fn test_on_tick_no_exit_while_profitable() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let pos = make_position("BTC".to_string(), true, 0, "funding_arb");
        let base = make_ctx("BTC", 50000.0, 1000, Some(0.005), Some(50000.0));
        let ctx = ctx_with_owned_position(base, &pos);

        // Rate still positive and strong → no exit
        assert!(
            s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(),
            "no exit while profitable"
        );
    }

    // ═════════════════════════════════════════════════════════════════════
    // RC-04 rejection rollback（cooldown only）/ 拒絕回滾
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_rejection_rollback_cooldown_only() {
        let mut s = FundingArb::new();
        s.set_active(true);

        // 進場前 cooldown 為「未見」
        assert!(s.cooldown.last_ms("BTC").is_none());

        // Entry — 寫入 cooldown + snapshot prev=0（未見）
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(50000.0));
        let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
        assert_eq!(actions.len(), 1);
        assert!(
            s.cooldown.last_ms("BTC").is_some(),
            "cooldown recorded after entry"
        );

        // Simulate rejection → rollback cooldown 回到「未見」狀態
        if let StrategyAction::Open(ref intent) = actions[0] {
            s.on_rejection(intent, "max_drawdown");
        }
        // Option A-Lite：strategy 不再撤 paper_state；只回滾 cooldown。
        assert!(
            s.cooldown.last_ms("BTC").is_none(),
            "cooldown cleared back to unseen state via prev_last_trade_ms=0 sentinel"
        );
    }

    // Option A-Lite：on_external_close 已退化為 trait default no-op
    // （funding_arb 無 strategy-internal lifecycle 欄位需清理；paper_state 由 PaperState SSoT 管理）。
    // 對應舊 test_on_external_close 移除，由 trait-level 行為涵蓋。

    // ═════════════════════════════════════════════════════════════════════
    // Hysteresis: entry/exit basis gap / 遲滯：進出場基差間距
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_basis_hysteresis_blocks_entry_allows_hold() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // basis ≈ 0.45%: above entry limit (0.4%) but below exit limit (0.5%)
        // index = perp / (1 + basis/100) → 50000 / 1.0045 ≈ 49776
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(49776.0));
        assert!(
            s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(),
            "0.45% basis blocks entry (> 0.4%)"
        );

        // But if already holding, 0.45% does NOT trigger exit
        // Option A-Lite：positive_funding=true ⇔ is_long_position=false
        assert!(
            !s.should_exit(false, 0.005, 0.45, 1000, 0),
            "0.45% basis allows hold (< 0.5%)"
        );
    }

    #[test]
    fn test_entry_allowed_under_tight_basis() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // basis ≈ 0.3%: below entry limit (0.4%)
        // index = 50000 / 1.003 ≈ 49850
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(49850.0));
        assert_eq!(s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).len(), 1, "0.3% basis allows entry (< 0.4%)");
    }

    #[test]
    fn test_exit_edge_zero_consistent_with_entry() {
        let s = FundingArb::new();
        // amortized_fee = 34/10000/3 ≈ 0.001133
        // rate = 0.0011 → edge = 0.0011 - 0.001133 < 0 → should exit
        assert!(s.should_exit(false, 0.0011, 0.1, 1000, 0), "edge <= 0 → exit");
    }

    #[test]
    fn test_no_exit_edge_positive() {
        let s = FundingArb::new();
        // rate = 0.002 → edge = 0.002 - 0.001133 ≈ 0.000867 > 0 → no exit
        assert!(!s.should_exit(false, 0.002, 0.1, 1000, 0), "edge > 0 → hold");
    }

    // ═════════════════════════════════════════════════════════════════════
    // AGT-1 IPC tunable param surface / 可調參數 IPC 接口
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_update_params_json_toggles_active() {
        let mut s = FundingArb::new();
        s.set_active(true);
        assert!(s.is_active());
        let payload = serde_json::to_string(&FundingArbUpdateParams {
            active: false,
            ..FundingArbUpdateParams::default()
        })
        .unwrap();
        s.update_params_json(&payload).expect("valid payload");
        assert!(!s.is_active(), "active=false should disarm the strategy");
    }

    #[test]
    fn test_update_params_json_roundtrip_preserves_values() {
        let mut s = FundingArb::new();
        let custom = FundingArbUpdateParams {
            active: true,
            cooldown_ms: 7_200_000,
            total_cost_bps: 42.0,
            expected_periods: 4.0,
            funding_threshold: 0.0008,
            max_basis_pct: 0.4,
            max_hold_ms: 48 * 3_600_000,
            entry_basis_ratio: 0.65,
        };
        s.update_params_json(&serde_json::to_string(&custom).unwrap())
            .expect("valid payload");
        let echoed: FundingArbUpdateParams = serde_json::from_str(&s.get_params_json()).unwrap();
        assert!(echoed.active);
        assert_eq!(echoed.cooldown_ms, 7_200_000);
        assert!((echoed.total_cost_bps - 42.0).abs() < f64::EPSILON);
        assert!((echoed.expected_periods - 4.0).abs() < f64::EPSILON);
        assert!((echoed.funding_threshold - 0.0008).abs() < f64::EPSILON);
        assert!((echoed.max_basis_pct - 0.4).abs() < f64::EPSILON);
        assert_eq!(echoed.max_hold_ms, 48 * 3_600_000);
        assert!((echoed.entry_basis_ratio - 0.65).abs() < f64::EPSILON);
    }

    #[test]
    fn test_update_params_validates_out_of_range() {
        let mut s = FundingArb::new();
        // cooldown_ms below 60s floor
        let bad = FundingArbUpdateParams {
            cooldown_ms: 1_000,
            ..FundingArbUpdateParams::default()
        };
        let err = s
            .update_params_json(&serde_json::to_string(&bad).unwrap())
            .unwrap_err();
        assert!(
            err.contains("cooldown_ms"),
            "err should flag cooldown_ms: {err}"
        );

        // expected_periods below 0.5 floor — protects compute_edge divisor
        let bad2 = FundingArbUpdateParams {
            expected_periods: 0.1,
            ..FundingArbUpdateParams::default()
        };
        let err2 = s
            .update_params_json(&serde_json::to_string(&bad2).unwrap())
            .unwrap_err();
        assert!(
            err2.contains("expected_periods"),
            "err should flag expected_periods: {err2}"
        );
    }

    #[test]
    fn test_inactive_blocks_entry_after_ipc_toggle() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // Entry payload would normally open a position; toggle active=false first
        s.update_params_json(
            &serde_json::to_string(&FundingArbUpdateParams {
                active: false,
                ..FundingArbUpdateParams::default()
            })
            .unwrap(),
        )
        .unwrap();
        // Sanity: strategy is now inactive
        assert!(!s.is_active());
        // Note: tick-level active check lives in orchestrator (not on_tick itself),
        // so we assert the flag rather than re-running the pipeline here. The
        // integration path is covered by ipc_server tests.
        // 注意：tick 層的 active 檢查在 orchestrator，不在 on_tick，因此這裡驗證 flag。
    }

    #[test]
    fn test_param_ranges_json_well_formed() {
        let s = FundingArb::new();
        let ranges: Vec<ParamRange> =
            serde_json::from_str(&s.param_ranges_json()).expect("valid JSON");
        let names: std::collections::HashSet<_> = ranges.iter().map(|r| r.name.as_str()).collect();
        for required in [
            "cooldown_ms",
            "total_cost_bps",
            "expected_periods",
            "funding_threshold",
            "max_basis_pct",
            "max_hold_ms",
            "entry_basis_ratio",
        ] {
            assert!(names.contains(required), "missing param range: {required}");
        }
        // `active` intentionally omitted from agent-tunable search space.
        assert!(!names.contains("active"), "active should not be a tunable");
    }

    // ─────────────────────────────────────────────────────────────────────────
    // P0 Option A-Lite Wave 1 — Cross-strategy ownership / Race acceptance
    // ─────────────────────────────────────────────────────────────────────────

    /// Option A-Lite §3.2 #4：cross-strategy occupied 時跳過 entry，不誤觸 exit。
    /// 模擬 paper_state 已被 ma_crossover 開倉，funding_arb 在同 tick 看到正費率仍應 skip。
    #[test]
    fn test_funding_arb_skips_entry_on_cross_strategy_position() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // 他家持倉（owner=ma_crossover），funding_arb 不應當作自家視之
        let pos = make_position("BTC".to_string(), true, 0, "ma_crossover");
        let base = make_ctx("BTC", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
        let ctx = ctx_with_owned_position(base, &pos);

        let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
        assert!(
            actions.is_empty(),
            "cross-strategy occupancy must skip entry (no Open, no Close)"
        );
        // cooldown 不應因為 cross-strategy 影響而 record
        assert!(
            s.cooldown.last_ms("BTC").is_none(),
            "cross-strategy skip must not record cooldown"
        );
    }

    /// Option A-Lite §7 #5：bybit_sync owner 視為 cross-strategy（skip entry, no exit）。
    /// boot 後 bybit_sync 寫入的倉位 owner="bybit_sync" 不對應任何策略；
    /// funding_arb 應 backoff 等下個 fill 自然 attribute。
    #[test]
    fn test_funding_arb_treats_bybit_sync_owner_as_cross_strategy() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let pos = make_position("BTC".to_string(), true, 0, "bybit_sync");
        let base = make_ctx("BTC", 50_000.0, 100_000, Some(0.005), Some(50_000.0));
        let ctx = ctx_with_owned_position(base, &pos);

        let actions = s.on_tick(&ctx, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
        assert!(actions.is_empty(), "bybit_sync occupancy must skip entry");
    }

    /// Option A-Lite：on_external_close 預設 trait no-op。funding_arb 移除 override 後
    /// 呼叫此 hook 應不 panic，且 cooldown 與其他內部狀態保持不變。
    #[test]
    fn test_funding_arb_on_external_close_is_noop() {
        let mut s = FundingArb::new();
        // 預先記錄 cooldown，確認 hook 不會誤動
        s.cooldown.record_signal("BTC", 100_000);
        let before = s.cooldown.last_ms("BTC");

        s.on_external_close("BTC");

        assert_eq!(
            s.cooldown.last_ms("BTC"),
            before,
            "on_external_close trait default no-op 不應動 cooldown / 其他內部狀態"
        );
    }

    /// Option A-Lite：on_fill 預設 trait no-op。funding_arb 移除 override 後
    /// 呼叫此 hook 應不 panic，且不寫入任何策略本地 position state（已不存在）。
    #[test]
    fn test_funding_arb_on_fill_is_noop_no_local_state() {
        let mut s = FundingArb::new();
        let intent = OrderIntent {
            symbol: "BTC".to_string(),
            is_long: false,
            qty: 1.0,
            confidence: 0.5,
            strategy: "funding_arb".to_string(),
            order_type: "limit".to_string(),
            limit_price: Some(50_000.0),
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: Some(TimeInForce::PostOnly),
            maker_timeout_ms: Some(45_000),
        };
        let fill = openclaw_core::execution::FillResult {
            fill_price: 50_000.0,
            fill_qty: 1.0,
            fee: 0.5,
            slippage_bps: 1.0,
            is_taker: false,
        };

        // trait default no-op：不 panic、不寫任何 local state（self.positions 已不存在）。
        s.on_fill(&intent, &fill);
    }

    /// Option A-Lite：import_positions 預設 trait no-op。funding_arb 不再持有
    /// strategy-local positions；bootstrap 後策略直接從 ctx.position_state 讀取
    /// paper_state SSoT，不需自行重建。
    #[test]
    fn test_funding_arb_import_positions_is_noop() {
        use crate::paper_state::PaperState;

        let mut paper = PaperState::new(10_000.0);
        paper.apply_fill("BTC", false, 1.0, 50_000.0, 0.5, 1_000, "funding_arb");

        let mut s = FundingArb::new();
        // trait default no-op：不 panic、無策略本地 state 需重建。
        s.import_positions(&paper);
    }
}

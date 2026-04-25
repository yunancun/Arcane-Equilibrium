//! Funding Rate Arbitrage Strategy V2 — directional funding rate capture.
//! 資金費率套利策略 V2 — 方向性資金費率捕獲。
//!
//! MODULE_NOTE (EN): Entry: |funding_rate| > threshold + edge > 0 after cost
//!   amortization + basis < max_basis_pct. Positive funding → short perp (receive
//!   funding), negative funding → long perp. Exit: rate flipped | rate < exit_threshold
//!   | basis > max_basis_pct | max hold 72h. Uses TickContext.funding_rate (WS tickers)
//!   + TickContext.index_price (WS tickers) for basis calculation.
//! MODULE_NOTE (中): 入場：|資金費率| > 閾值 + 扣除成本後 edge > 0 + 基差 < 上限。
//!   正資金費率 → 做空永續（收取資金費率），負資金費率 → 做多永續。
//!   出場：費率反轉 | 費率 < 退出閾值 | 基差 > 上限 | 最大持有 72h。
//!   使用 TickContext.funding_rate（WS tickers）+ TickContext.index_price 計算基差。

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{PerSymbolState, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

// QC-H10: Constants retained as defaults only — runtime uses struct fields.
// QC-H10：常量僅作為默認值保留 — 運行時使用 struct 欄位。
const DEFAULT_TOTAL_COST_BPS: f64 = 34.0; // perp(11) + spot(20) + slippage(3)
const DEFAULT_EXPECTED_PERIODS: f64 = 3.0; // 8h funding periods
const DEFAULT_FUNDING_THRESHOLD: f64 = 0.0005; // 5 bps
const DEFAULT_MAX_BASIS_PCT: f64 = 0.5;
const DEFAULT_MAX_HOLD_MS: u64 = 72 * 3_600_000;
const DEFAULT_ENTRY_BASIS_RATIO: f64 = 0.8;

pub struct FundingArb {
    active: bool,
    /// #17: Per-symbol position tracking (was single Option<FundingPosition>).
    /// E1-P0-2: Migrated from `HashMap<String, FundingPosition>` to
    /// `PerSymbolState<FundingPosition>` (semantic-preserving wrapper).
    /// #17：每幣種持倉追蹤（原為單一 Option<FundingPosition>）。
    /// E1-P0-2：改用 `PerSymbolState<FundingPosition>` 包裝器（語意不變）。
    positions: PerSymbolState<FundingPosition>,
    /// E1-P0-2: Per-symbol last-signal time. Migrated from `HashMap<String, u64>`
    /// to `TrendCooldown`. Semantics preserved: unseen symbol is "cooled",
    /// `saturating_sub` guards backward clock skew.
    /// E1-P0-2：逐幣種最後信號時間，改用 `TrendCooldown`，語意完全相同。
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,
    default_qty: f64,
    // QC-H10: Parameterized constants (was module-level consts).
    // QC-H10：參數化常量（原為模組級常量）。
    pub(crate) total_cost_bps: f64,
    pub(crate) expected_periods: f64,
    pub(crate) funding_threshold: f64,
    pub(crate) max_basis_pct: f64,
    pub(crate) max_hold_ms: u64,
    // Entry basis = max_basis_pct * entry_basis_ratio; hysteresis prevents instant exit.
    // 入場基差 = max_basis_pct * entry_basis_ratio；遲滯防止瞬間出場。
    pub(crate) entry_basis_ratio: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_positions: HashMap<String, Option<FundingPosition>>,
    prev_last_trade_ms: HashMap<String, u64>,
}

#[derive(Debug, Clone)]
struct FundingPosition {
    is_positive_funding: bool, // true = short perp (funding > 0)
    entry_ms: u64,
    entry_funding_rate: f64,
}

impl FundingArb {
    pub fn new() -> Self {
        Self {
            active: false,
            positions: PerSymbolState::new(),
            cooldown: TrendCooldown::new(3_600_000),
            cooldown_ms: 3_600_000, // 1h cooldown
            default_qty: 1e9,       // sentinel → IntentProcessor applies risk sizing
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            funding_threshold: DEFAULT_FUNDING_THRESHOLD,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            prev_positions: HashMap::new(),
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

    /// #17: Per-symbol exit check (was single-position).
    /// #17：每幣種出場檢查（原為單一持倉）。
    fn should_exit(&self, symbol: &str, funding_rate: f64, basis_pct: f64, now_ms: u64) -> bool {
        let pos = match self.positions.get(symbol) {
            Some(p) => p,
            None => return false,
        };

        // Rate flipped sign / 費率翻轉
        if pos.is_positive_funding && funding_rate < 0.0 {
            return true;
        }
        if !pos.is_positive_funding && funding_rate > 0.0 {
            return true;
        }

        // Edge no longer positive — consistent with entry logic.
        // Edge 不再為正 — 與入場邏輯一致。
        if self.compute_edge(funding_rate) <= 0.0 {
            return true;
        }

        // Basis risk — QC-H10: uses struct field / 基差風險
        if basis_pct > self.max_basis_pct {
            return true;
        }

        // Max hold time — QC-H10: uses struct field / 超過最大持有時間
        if now_ms.saturating_sub(pos.entry_ms) > self.max_hold_ms {
            return true;
        }

        false
    }

    /// RC-04: Snapshot current state before mutation for rejection rollback.
    /// Preserves the pre-extraction "unseen → 0" sentinel convention by mapping
    /// `TrendCooldown::last_ms(sym) == None` to 0.
    /// RC-04：突變前快照當前狀態，用於拒絕回滾。
    /// 將 TrendCooldown 未記錄的 symbol 映射為 0，保留原先「未見 → 0」的哨兵慣例。
    fn snapshot_prev(&mut self, sym: &str) {
        self.prev_positions
            .insert(sym.to_string(), self.positions.get(sym).cloned());
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

    /// RC-04: Revert per-symbol position and last_trade_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 position 和 last_trade_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_positions.get(sym) {
            match prev {
                Some(p) => {
                    self.positions.insert(sym.clone(), p.clone());
                }
                None => {
                    self.positions.remove(sym);
                }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                // Sentinel 0 → symbol had no prior record; clear cooldown entry
                // to restore "unseen" state (matches pre-extraction HashMap.remove).
                // 哨兵 0 → 原本無紀錄；清掉 cooldown 條目回到「未見」狀態。
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    /// Reset internal position on external close (risk-stop/halt).
    /// 外部平倉時重置內部倉位（風控止損/暫停）。
    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
    }

    /// OC-5: Funding rate capture — entry when edge > 0, exit on rate flip/basis/max hold.
    /// OC-5：資金費率捕獲 — edge > 0 時入場，費率翻轉/基差/超時出場。
    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let sym = ctx.symbol;
        let now_ms = ctx.timestamp_ms;

        // Must have funding rate data / 必須有資金費率數據
        let funding_rate = match ctx.funding_rate {
            Some(fr) if fr.abs() > f64::EPSILON => fr,
            _ => return vec![],
        };

        let basis_pct = Self::compute_basis_pct(ctx.price, ctx.index_price);

        // ── Exit check: if holding a position, evaluate exit conditions ──
        // ── 出場檢查：持有倉位時評估出場條件 ──
        if self.positions.contains_key(sym) {
            if self.should_exit(sym, funding_rate, basis_pct, now_ms) {
                // RC-04: snapshot before mutation
                self.snapshot_prev(sym);

                self.positions.remove(sym);
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
            // Holding, no exit signal → do nothing / 持倉中，無出場信號
            return vec![];
        }

        // ── Entry evaluation: no position, check if we should open ──
        // ── 入場評估：無持倉，判斷是否開倉 ──

        // H0 gate / H0 門控
        if !ctx.h0_allowed {
            return vec![];
        }

        // Cooldown / 冷卻期 (E1-P0-2: delegated to TrendCooldown, semantics preserved)
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

        // RC-04: snapshot before mutation
        self.snapshot_prev(sym);

        // Record entry / 記錄入場
        self.positions.insert(
            sym.to_string(),
            FundingPosition {
                is_positive_funding: is_positive,
                entry_ms: now_ms,
                entry_funding_rate: funding_rate,
            },
        );
        self.cooldown.record_signal(sym, now_ms);

        vec![StrategyAction::Open(OrderIntent {
            symbol: sym.to_string(),
            is_long,
            qty: self.default_qty, // sentinel → IntentProcessor applies Kelly/risk sizing
            confidence,
            strategy: self.name().into(),
            order_type: "market".into(),
            limit_price: None,
            // FundingArb has no confluence scoring / persistence tracker; leave
            // features unset so feature_builder fills 0.0 placeholders.
            // FundingArb 無 confluence/persistence；feature_builder 會填 0。
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
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
            signals: &[],
            h0_allowed: true,
            funding_rate,
            index_price,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
        }
    }

    fn insert_position(
        s: &mut FundingArb,
        symbol: &str,
        is_positive: bool,
        entry_ms: u64,
        rate: f64,
    ) {
        s.positions.insert(
            symbol.to_string(),
            FundingPosition {
                is_positive_funding: is_positive,
                entry_ms,
                entry_funding_rate: rate,
            },
        );
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

    #[test]
    fn test_should_exit_rate_flip() {
        let mut s = FundingArb::new();
        insert_position(&mut s, "BTC", true, 0, 0.001);
        assert!(s.should_exit("BTC", -0.001, 0.1, 1000));
    }

    #[test]
    fn test_should_exit_max_hold() {
        let mut s = FundingArb::new();
        insert_position(&mut s, "BTC", true, 0, 0.001);
        assert!(s.should_exit("BTC", 0.001, 0.1, DEFAULT_MAX_HOLD_MS + 1));
    }

    #[test]
    fn test_should_exit_basis_risk() {
        let mut s = FundingArb::new();
        insert_position(&mut s, "BTC", true, 0, 0.001);
        assert!(s.should_exit("BTC", 0.001, 0.6, 1000)); // basis > 0.5%
    }

    #[test]
    fn test_no_exit_normal() {
        let mut s = FundingArb::new();
        insert_position(&mut s, "BTC", true, 0, 0.005);
        // Rate 0.005 → edge = 0.005 - 0.001133 = 0.00387 > 0 → no exit
        assert!(!s.should_exit("BTC", 0.005, 0.1, 1000));
    }

    #[test]
    fn test_multi_symbol_positions() {
        let mut s = FundingArb::new();
        insert_position(&mut s, "BTC", true, 0, 0.001);
        insert_position(&mut s, "ETH", false, 0, 0.002);
        assert_eq!(s.positions.len(), 2);
        // BTC rate flip → exit; ETH unaffected
        assert!(s.should_exit("BTC", -0.001, 0.1, 1000));
        assert!(!s.should_exit("ETH", -0.003, 0.1, 1000));
        // External close BTC
        s.positions.remove("BTC");
        assert_eq!(s.positions.len(), 1);
        assert!(!s.should_exit("BTC", -0.001, 0.1, 1000)); // no position → no exit
    }

    // ═════════════════════════════════════════════════════════════════════
    // on_tick entry / 入場邏輯
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_on_tick_no_funding_rate_no_action() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let ctx = make_ctx("BTC", 50000.0, 0, None, None);
        assert!(s.on_tick(&ctx).is_empty(), "no funding rate → no action");
    }

    #[test]
    fn test_on_tick_below_threshold_no_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // 1 bps = 0.0001, below default threshold 5 bps
        let ctx = make_ctx("BTC", 50000.0, 0, Some(0.0001), Some(50000.0));
        assert!(s.on_tick(&ctx).is_empty(), "below threshold → no entry");
    }

    #[test]
    fn test_on_tick_positive_edge_entry_short() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // 50 bps funding rate, well above cost → positive edge → short entry
        let ctx = make_ctx("BTCUSDT", 50000.0, 100_000, Some(0.005), Some(50000.0));
        let actions = s.on_tick(&ctx);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Open(intent) => {
                assert!(!intent.is_long, "positive funding → short");
                assert_eq!(intent.symbol, "BTCUSDT");
                assert_eq!(intent.strategy, "funding_arb");
                assert!(intent.confidence >= 0.3 && intent.confidence <= 0.9);
            }
            other => panic!("expected Open, got {:?}", other),
        }
        assert!(s.positions.contains_key("BTCUSDT"), "position recorded");
    }

    #[test]
    fn test_on_tick_negative_funding_entry_long() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // -50 bps → long entry
        let ctx = make_ctx("ETHUSDT", 3000.0, 100_000, Some(-0.005), Some(3000.0));
        let actions = s.on_tick(&ctx);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Open(intent) => {
                assert!(intent.is_long, "negative funding → long");
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_on_tick_cooldown_blocks_re_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        let ctx1 = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(50000.0));
        assert_eq!(s.on_tick(&ctx1).len(), 1, "first entry");

        // Manually close position but last_trade_ms still set
        s.positions.remove("BTC");

        // Within cooldown (1h = 3_600_000ms)
        let ctx2 = make_ctx("BTC", 50000.0, 200_000, Some(0.005), Some(50000.0));
        assert!(s.on_tick(&ctx2).is_empty(), "cooldown blocks re-entry");

        // After cooldown
        let ctx3 = make_ctx(
            "BTC",
            50000.0,
            100_000 + 3_600_001,
            Some(0.005),
            Some(50000.0),
        );
        assert_eq!(s.on_tick(&ctx3).len(), 1, "after cooldown → entry");
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
            signals: &[],
            h0_allowed: false, // H0 blocks
            funding_rate: Some(0.005),
            index_price: Some(50000.0),
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
        };
        assert!(s.on_tick(&ctx).is_empty(), "H0 blocked → no entry");
    }

    #[test]
    fn test_on_tick_basis_too_wide_blocks_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // index=49750 → basis ≈ 0.503% > entry limit 0.4% → blocked
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(49750.0));
        assert!(s.on_tick(&ctx).is_empty(), "wide basis → no entry");
    }

    // ═════════════════════════════════════════════════════════════════════
    // on_tick exit / 出場邏輯
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_on_tick_exit_on_rate_flip() {
        let mut s = FundingArb::new();
        s.set_active(true);
        insert_position(&mut s, "BTC", true, 0, 0.005);

        // Rate flipped negative → exit
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(-0.001), Some(50000.0));
        let actions = s.on_tick(&ctx);
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Close { symbol, reason, .. } => {
                assert_eq!(symbol, "BTC");
                assert!(reason.contains("funding_arb_exit"));
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(!s.positions.contains_key("BTC"), "position cleared");
    }

    #[test]
    fn test_on_tick_no_exit_while_profitable() {
        let mut s = FundingArb::new();
        s.set_active(true);
        insert_position(&mut s, "BTC", true, 0, 0.005);

        // Rate still positive and strong → no exit
        let ctx = make_ctx("BTC", 50000.0, 1000, Some(0.005), Some(50000.0));
        assert!(s.on_tick(&ctx).is_empty(), "no exit while profitable");
        assert!(s.positions.contains_key("BTC"), "position still held");
    }

    // ═════════════════════════════════════════════════════════════════════
    // RC-04 rejection rollback / 拒絕回滾
    // ═════════════════════════════════════════════════════════════════════

    #[test]
    fn test_rejection_rollback_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);

        // Entry
        let ctx = make_ctx("BTC", 50000.0, 100_000, Some(0.005), Some(50000.0));
        let actions = s.on_tick(&ctx);
        assert_eq!(actions.len(), 1);
        assert!(s.positions.contains_key("BTC"));

        // Simulate rejection → rollback
        if let StrategyAction::Open(ref intent) = actions[0] {
            s.on_rejection(intent, "max_drawdown");
        }
        assert!(!s.positions.contains_key("BTC"), "position rolled back");
    }

    #[test]
    fn test_on_external_close() {
        let mut s = FundingArb::new();
        insert_position(&mut s, "BTC", true, 0, 0.005);
        s.on_external_close("BTC");
        assert!(!s.positions.contains_key("BTC"));
    }

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
            s.on_tick(&ctx).is_empty(),
            "0.45% basis blocks entry (> 0.4%)"
        );

        // But if already holding, 0.45% does NOT trigger exit
        insert_position(&mut s, "BTC", true, 0, 0.005);
        assert!(
            !s.should_exit("BTC", 0.005, 0.45, 1000),
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
        assert_eq!(s.on_tick(&ctx).len(), 1, "0.3% basis allows entry (< 0.4%)");
    }

    #[test]
    fn test_exit_edge_zero_consistent_with_entry() {
        let mut s = FundingArb::new();
        // amortized_fee = 34/10000/3 ≈ 0.001133
        // rate = 0.0011 → edge = 0.0011 - 0.001133 < 0 → should exit
        insert_position(&mut s, "BTC", true, 0, 0.005);
        assert!(s.should_exit("BTC", 0.0011, 0.1, 1000), "edge <= 0 → exit");
    }

    #[test]
    fn test_no_exit_edge_positive() {
        let mut s = FundingArb::new();
        // rate = 0.002 → edge = 0.002 - 0.001133 ≈ 0.000867 > 0 → no exit
        insert_position(&mut s, "BTC", true, 0, 0.005);
        assert!(!s.should_exit("BTC", 0.002, 0.1, 1000), "edge > 0 → hold");
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
}

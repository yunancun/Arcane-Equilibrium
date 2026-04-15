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

use super::{Strategy, StrategyAction};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

// QC-H10: Constants retained as defaults only — runtime uses struct fields.
// QC-H10：常量僅作為默認值保留 — 運行時使用 struct 欄位。
const DEFAULT_TOTAL_COST_BPS: f64 = 34.0; // perp(11) + spot(20) + slippage(3)
const DEFAULT_EXPECTED_PERIODS: f64 = 3.0; // 8h funding periods
const DEFAULT_FUNDING_THRESHOLD: f64 = 0.0005; // 5 bps
const DEFAULT_MAX_BASIS_PCT: f64 = 0.5;
const DEFAULT_MAX_HOLD_MS: u64 = 72 * 3_600_000;

pub struct FundingArb {
    active: bool,
    /// #17: Per-symbol position tracking (was single Option<FundingPosition>).
    /// #17：每幣種持倉追蹤（原為單一 Option<FundingPosition>）。
    positions: HashMap<String, FundingPosition>,
    last_trade_ms: HashMap<String, u64>,
    pub cooldown_ms: u64,
    default_qty: f64,
    // QC-H10: Parameterized constants (was module-level consts).
    // QC-H10：參數化常量（原為模組級常量）。
    pub(crate) total_cost_bps: f64,
    pub(crate) expected_periods: f64,
    pub(crate) funding_threshold: f64,
    pub(crate) max_basis_pct: f64,
    pub(crate) max_hold_ms: u64,
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
            positions: HashMap::new(),
            last_trade_ms: HashMap::new(),
            cooldown_ms: 3_600_000, // 1h cooldown
            default_qty: 1e9,       // sentinel → IntentProcessor applies risk sizing
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            funding_threshold: DEFAULT_FUNDING_THRESHOLD,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
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

        // Rate too small — QC-H10: uses struct fields
        // 費率太小 — 不足以覆蓋成本
        let exit_threshold = self.total_cost_bps / 10_000.0 / 2.0;
        if funding_rate.abs() < exit_threshold {
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
    /// RC-04：突變前快照當前狀態，用於拒絕回滾。
    fn snapshot_prev(&mut self, sym: &str) {
        self.prev_positions.insert(
            sym.to_string(),
            self.positions.get(sym).cloned(),
        );
        self.prev_last_trade_ms.insert(
            sym.to_string(),
            self.last_trade_ms.get(sym).copied().unwrap_or(0),
        );
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
                Some(p) => { self.positions.insert(sym.clone(), p.clone()); }
                None => { self.positions.remove(sym); }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.last_trade_ms.remove(sym); } else { self.last_trade_ms.insert(sym.clone(), ts); }
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
                self.last_trade_ms.insert(sym.to_string(), now_ms);

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

        // Cooldown / 冷卻期
        if let Some(&last_ms) = self.last_trade_ms.get(sym) {
            if now_ms.saturating_sub(last_ms) < self.cooldown_ms {
                return vec![];
            }
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

        // Basis must be within tolerance at entry / 入場時基差必須在容忍範圍內
        if basis_pct > self.max_basis_pct {
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
        self.last_trade_ms.insert(sym.to_string(), now_ms);

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
        })]
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
        }
    }

    fn insert_position(s: &mut FundingArb, symbol: &str, is_positive: bool, entry_ms: u64, rate: f64) {
        s.positions.insert(symbol.to_string(), FundingPosition {
            is_positive_funding: is_positive,
            entry_ms,
            entry_funding_rate: rate,
        });
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
        // Rate 0.005 (50 bps) > exit_threshold 0.0017 → no exit
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
        let ctx3 = make_ctx("BTC", 50000.0, 100_000 + 3_600_001, Some(0.005), Some(50000.0));
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
        };
        assert!(s.on_tick(&ctx).is_empty(), "H0 blocked → no entry");
    }

    #[test]
    fn test_on_tick_basis_too_wide_blocks_entry() {
        let mut s = FundingArb::new();
        s.set_active(true);
        // index=49750 → basis = |50000/49750 - 1| * 100 = ~0.503% > 0.5%
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
}

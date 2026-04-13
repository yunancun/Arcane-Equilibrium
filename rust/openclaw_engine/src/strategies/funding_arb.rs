//! Funding Rate Arbitrage Strategy V2 — delta-neutral paired execution.
//! 資金費率套利策略 V2 — delta 中性配對執行。
//!
//! MODULE_NOTE (EN): Entry: |funding_rate| > threshold + edge > 0 after cost
//!   amortization. Exit: rate flipped | rate < exit_threshold | basis > 0.5% |
//!   max hold 72h. Currently stub (on_tick returns vec![]), pending OC-5 REST wiring.
//! MODULE_NOTE (中): 入場：|資金費率| > 閾值 + 扣除成本後 edge > 0。
//!   出場：費率反轉 | 費率 < 退出閾值 | 基差 > 0.5% | 最大持有 72h。
//!   當前為 stub（on_tick 返回 vec![]），待 OC-5 REST 接線。

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
    #[allow(dead_code)] // used when funding rate IPC is wired in R-06
    default_qty: f64,
    // QC-H10: Parameterized constants (was module-level consts).
    // QC-H10：參數化常量（原為模組級常量）。
    #[allow(dead_code)]
    pub(crate) total_cost_bps: f64,
    #[allow(dead_code)]
    pub(crate) expected_periods: f64,
    #[allow(dead_code)]
    pub(crate) funding_threshold: f64,
    #[allow(dead_code)]
    pub(crate) max_basis_pct: f64,
    #[allow(dead_code)]
    pub(crate) max_hold_ms: u64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_positions: HashMap<String, Option<FundingPosition>>,
    prev_last_trade_ms: HashMap<String, u64>,
}

#[derive(Debug, Clone)]
#[allow(dead_code)]
struct FundingPosition {
    is_positive_funding: bool, // true = short perp + long spot
    entry_ms: u64,
    entry_funding_rate: f64,
}

impl FundingArb {
    pub fn new() -> Self {
        Self {
            active: false, // FIX-23: inactive by default — pending OC-5/R-06 data wiring
            positions: HashMap::new(),
            last_trade_ms: HashMap::new(),
            cooldown_ms: 3_600_000, // 1h cooldown
            default_qty: 1e9,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            funding_threshold: DEFAULT_FUNDING_THRESHOLD,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            prev_positions: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
        }
    }

    /// QC-H10: compute_edge uses struct field instead of module const.
    #[allow(dead_code)]
    fn compute_edge(&self, funding_rate: f64) -> f64 {
        let amortized_fee = self.total_cost_bps / 10_000.0 / self.expected_periods;
        funding_rate.abs() - amortized_fee
    }

    /// #17: Per-symbol exit check (was single-position).
    #[allow(dead_code)]
    fn should_exit(&self, symbol: &str, funding_rate: f64, basis_pct: f64, now_ms: u64) -> bool {
        let pos = match self.positions.get(symbol) {
            Some(p) => p,
            None => return false,
        };

        // Rate flipped sign
        if pos.is_positive_funding && funding_rate < 0.0 {
            return true;
        }
        if !pos.is_positive_funding && funding_rate > 0.0 {
            return true;
        }

        // Rate too small — QC-H10: uses struct fields
        let exit_threshold = self.total_cost_bps / 10_000.0 / 2.0;
        if funding_rate.abs() < exit_threshold {
            return true;
        }

        // Basis risk — QC-H10: uses struct field
        if basis_pct > self.max_basis_pct {
            return true;
        }

        // Max hold time — QC-H10: uses struct field
        if now_ms - pos.entry_ms > self.max_hold_ms {
            return true;
        }

        false
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

    fn on_tick(&mut self, _ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        // TODO(R-06): When real funding rate logic is wired, add prev_* snapshot
        // before mutation here (same pattern as other strategies).
        // TODO(R-06)：接入真實資金費率邏輯時，在此處突變前添加 prev_* 快照。

        // Funding arb uses external funding rate data, not indicators
        // For now, check if any signal contains funding info
        // In production, funding rate comes via WS or REST polling
        // 資金費率套利使用外部資金費率數據，非指標
        // 目前暫時不產生信號，等 R-06 Python IPC 提供資金費率

        // Placeholder: funding_arb needs external data not available in tick context
        // Will be wired in R-06 when Python IPC provides funding rate

        vec![]
    }
}

#[cfg(test)]
mod tests {
    use super::*;

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

    fn insert_position(s: &mut FundingArb, symbol: &str, is_positive: bool, entry_ms: u64, rate: f64) {
        s.positions.insert(symbol.to_string(), FundingPosition {
            is_positive_funding: is_positive,
            entry_ms,
            entry_funding_rate: rate,
        });
    }

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

    #[test]
    fn test_on_tick_placeholder() {
        let mut s = FundingArb::new();
        let ctx = TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
        };
        assert!(s.on_tick(&ctx).is_empty());
    }
}

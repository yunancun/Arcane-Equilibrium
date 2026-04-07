//! P2 refactor (2026-04-07): per-position risk evaluation extracted from
//! tick_pipeline.rs Step 6. Pure-function decision layer; the mutating
//! dispatch (close, halt, cooldown) stays inline in tick_pipeline.
//!
//! P2 重構（2026-04-07）：tick_pipeline.rs Step 6 的逐倉風控評估抽出。
//! 純函數決策層；變動性派發（平倉/暫停/冷卻）保留在 tick_pipeline 內聯。
//!
//! MODULE_NOTE (EN): Splits "policy" (compute the action) from "mechanism"
//!   (apply the action). The split is behavior-preserving because the
//!   original code already snapshotted all positions into a Vec BEFORE the
//!   dispatch loop, so reading-then-acting in two phases gives identical
//!   semantics. The dispatch loop in tick_pipeline.rs still uses `break` on
//!   HaltSession, so subsequent decisions in this batch are silently dropped
//!   exactly as before.
//! MODULE_NOTE (中)：將「政策」（計算 action）與「機制」（套用 action）拆開。
//!   行為保持不變：原始程式碼已在派發迴圈之前把所有 position 快照進 Vec，
//!   兩階段的讀取再動作語義完全相同。tick_pipeline.rs 的派發迴圈遇 HaltSession
//!   仍 `break`，本批次後續 decision 與之前一樣被靜默丟棄。

use openclaw_core::risk::{check_position_on_tick, RiskAction, RiskManagerConfig};

/// Per-position immutable input row, built upstream from `PaperState` +
/// `IndicatorSnapshot` + `PriceHistoryTracker` + `consecutive_losses`.
/// 由上游從 `PaperState` + `IndicatorSnapshot` + `PriceHistoryTracker`
/// + `consecutive_losses` 構造的逐倉 immutable 輸入。
#[derive(Debug, Clone)]
pub struct PositionRow {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_price: f64,
    pub entry_ts_ms: u64,
    pub peak_price: f64,
    pub current_price: f64,
    pub atr_pct: Option<f64>,
    pub fee_rate: f64,
    pub regime: String,
    pub consecutive_losses: u32,
}

/// Per-position decision returned to the dispatch loop. Holds enough info
/// to update `consecutive_losses` and emit close/halt/cooldown side-effects.
/// 回給派發迴圈的逐倉決策。攜帶足夠資訊以更新 `consecutive_losses` 並
/// 觸發平倉/暫停/冷卻副作用。
#[derive(Debug, Clone)]
pub struct PositionDecision {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_ts_ms: u64,
    pub pnl_pct: f64,
    pub action: RiskAction,
}

/// Compute pnl% with fail-closed entry_price=0 → -999% (forces hard stop).
/// 計算 pnl%；entry_price=0 時 fail-closed 回 -999%（觸發硬止損）。
#[inline]
fn pnl_pct(price: f64, entry_price: f64, is_long: bool) -> f64 {
    if entry_price <= 0.0 {
        return -999.0;
    }
    if is_long {
        (price - entry_price) / entry_price * 100.0
    } else {
        (entry_price - price) / entry_price * 100.0
    }
}

/// GAP-2: live cost_ratio = round-trip fees / unrealized profit.
/// For positive pnl_pct, cost_ratio ≈ 200 × fee_rate / pnl_pct (price ≈ entry
/// near the close threshold so the approximation is exact at the boundary).
/// Returns 0 when not in profit (short-circuits the cost-edge check).
/// GAP-2：實時 cost_ratio = 來回手續費 / 浮盈。非盈利時回 0。
#[inline]
fn compute_cost_ratio(pnl_pct: f64, fee_rate: f64) -> f64 {
    if pnl_pct > 0.0 {
        (2.0 * fee_rate * 100.0) / pnl_pct
    } else {
        0.0
    }
}

/// Evaluate a single position row, returning the action the dispatch loop
/// should take. Pure function — no I/O, no mutation, no logging.
/// 評估單一 position row，回傳派發迴圈該執行的 action。純函數。
pub(crate) fn evaluate_position(
    row: &PositionRow,
    daily_loss: f64,
    session_drawdown: f64,
    now_ts_ms: u64,
    config: &RiskManagerConfig,
) -> PositionDecision {
    let pnl = pnl_pct(row.current_price, row.entry_price, row.is_long);
    let peak_pnl = pnl_pct(row.peak_price, row.entry_price, row.is_long);
    let holding_hours = (now_ts_ms.saturating_sub(row.entry_ts_ms)) as f64 / 3_600_000.0;
    let cost_ratio = compute_cost_ratio(pnl, row.fee_rate);
    let action = check_position_on_tick(
        pnl,
        peak_pnl,
        holding_hours,
        cost_ratio,
        &row.regime,
        row.atr_pct,
        &row.symbol,
        row.entry_ts_ms,
        row.consecutive_losses,
        daily_loss,
        session_drawdown,
        config,
    );
    PositionDecision {
        symbol: row.symbol.clone(),
        is_long: row.is_long,
        qty: row.qty,
        entry_ts_ms: row.entry_ts_ms,
        pnl_pct: pnl,
        action,
    }
}

/// Evaluate a batch of position rows in order, returning one decision per row.
/// 依序評估一批 position row，每行回傳一個決策。
pub(crate) fn evaluate_positions(
    rows: &[PositionRow],
    daily_loss: f64,
    session_drawdown: f64,
    now_ts_ms: u64,
    config: &RiskManagerConfig,
) -> Vec<PositionDecision> {
    rows.iter()
        .map(|r| evaluate_position(r, daily_loss, session_drawdown, now_ts_ms, config))
        .collect()
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn mk_row(symbol: &str, current: f64, entry: f64) -> PositionRow {
        PositionRow {
            symbol: symbol.into(),
            is_long: true,
            qty: 1.0,
            entry_price: entry,
            entry_ts_ms: 0,
            peak_price: current.max(entry),
            current_price: current,
            atr_pct: Some(1.0),
            fee_rate: 0.0006,
            regime: "ranging".into(),
            consecutive_losses: 0,
        }
    }

    /// Long position in profit → Hold (no stop triggered).
    /// 多單盈利 → Hold（無止損觸發）。
    #[test]
    fn test_pnl_pct_long_profit() {
        assert!((pnl_pct(110.0, 100.0, true) - 10.0).abs() < 1e-9);
    }

    /// Short position in profit (price down) → positive pnl%.
    /// 空單盈利（價跌）→ 正 pnl%。
    #[test]
    fn test_pnl_pct_short_profit() {
        assert!((pnl_pct(90.0, 100.0, false) - 10.0).abs() < 1e-9);
    }

    /// entry_price = 0 fail-closed → -999% (forces hard stop).
    /// entry_price = 0 fail-closed → -999%（強制硬止損）。
    #[test]
    fn test_pnl_pct_zero_entry_fail_closed() {
        assert_eq!(pnl_pct(123.0, 0.0, true), -999.0);
    }

    /// cost_ratio is 0 when not in profit (short-circuits cost-edge check).
    /// 非盈利時 cost_ratio = 0（短路 cost-edge 檢查）。
    #[test]
    fn test_cost_ratio_not_in_profit_zero() {
        assert_eq!(compute_cost_ratio(-1.0, 0.0006), 0.0);
        assert_eq!(compute_cost_ratio(0.0, 0.0006), 0.0);
    }

    /// cost_ratio formula sanity check at small profit + fee 0.0006.
    /// cost_ratio 公式於小盈利 + 費率 0.0006 的健全性檢查。
    #[test]
    fn test_cost_ratio_formula() {
        // pnl 0.5%, fee 0.0006 → 200 * 0.0006 / 0.5 = 0.24
        let r = compute_cost_ratio(0.5, 0.0006);
        assert!((r - 0.24).abs() < 1e-9);
    }

    /// evaluate_position smoke: row in profit, default config → Hold or close
    /// (depends on threshold), but always returns a valid decision with
    /// pnl_pct echoed and same identity fields.
    /// evaluate_position 煙霧測試：盈利倉 + 預設 config → 一定回有效決策。
    #[test]
    fn test_evaluate_position_smoke() {
        let row = mk_row("BTCUSDT", 105.0, 100.0);
        let cfg = RiskManagerConfig::default();
        let decision = evaluate_position(&row, 0.0, 0.0, 1_000_000, &cfg);
        assert_eq!(decision.symbol, "BTCUSDT");
        assert_eq!(decision.is_long, true);
        assert!((decision.pnl_pct - 5.0).abs() < 1e-9);
    }

    /// Hard-stop trigger: long with -50% pnl on a config with max_stop=20%
    /// must close.
    /// 硬止損觸發：多單 -50% pnl 對 max_stop=20% 的 config → 必平倉。
    #[test]
    fn test_evaluate_position_hard_stop_close() {
        let row = mk_row("BTCUSDT", 50.0, 100.0); // -50% pnl
        let cfg = RiskManagerConfig::default();
        let decision = evaluate_position(&row, 0.0, 0.0, 1_000_000, &cfg);
        assert!(matches!(decision.action, RiskAction::ClosePosition(_)));
    }

    /// evaluate_positions empty input → empty output, no panic.
    /// 空輸入 → 空輸出，不 panic。
    #[test]
    fn test_evaluate_positions_empty() {
        let cfg = RiskManagerConfig::default();
        let out = evaluate_positions(&[], 0.0, 0.0, 0, &cfg);
        assert!(out.is_empty());
    }

    /// evaluate_positions preserves order across rows.
    /// 多行情況下保持順序。
    #[test]
    fn test_evaluate_positions_preserves_order() {
        let rows = vec![
            mk_row("AAA", 105.0, 100.0),
            mk_row("BBB", 95.0, 100.0),
            mk_row("CCC", 100.0, 100.0),
        ];
        let cfg = RiskManagerConfig::default();
        let out = evaluate_positions(&rows, 0.0, 0.0, 1_000_000, &cfg);
        assert_eq!(out.len(), 3);
        assert_eq!(out[0].symbol, "AAA");
        assert_eq!(out[1].symbol, "BBB");
        assert_eq!(out[2].symbol, "CCC");
    }
}

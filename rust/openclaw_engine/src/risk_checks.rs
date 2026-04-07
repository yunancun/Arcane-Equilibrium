//! Order admission and tick-level position risk checks (ARCH-RC1).
//! 訂單准入及 tick 級持倉風控檢查（ARCH-RC1）。
//!
//! MODULE_NOTE (中文):
//!   1C-1 從 openclaw_core::risk::checks 遷移過來，改讀新 RiskConfig。
//!   - 熱路徑使用 `&RiskConfig` lock-free 快照讀（ArcSwap）
//!   - cost_edge_max_ratio 為跨 Config 讀（契約允許執行時讀，禁止校準耦合），
//!     由 caller 從 BudgetConfig.attention_tax.cost_edge_max_ratio 取出後傳入
//!   - 風控檢查 fail-closed — 未知狀態 → 拒絕
//!
//! MODULE_NOTE (English):
//!   Migrated from openclaw_core::risk::checks in 1C-1; reads new RiskConfig.
//!   - Hot path uses `&RiskConfig` via ArcSwap lock-free snapshot
//!   - cost_edge_max_ratio is a cross-Config read (contract allows runtime reads,
//!     only forbids calibration coupling) — passed in by caller from
//!     BudgetConfig.attention_tax.cost_edge_max_ratio
//!   - Risk checks are fail-closed — unknown state → reject

use crate::config::RiskConfig;
use openclaw_core::risk::{compute_dynamic_stop_pct, regime_multipliers};

// ---------------------------------------------------------------------------
// Order admission / 訂單准入
// ---------------------------------------------------------------------------

/// Result of an order admission check / 訂單准入檢查結果
#[derive(Debug, Clone)]
pub struct PositionCheck {
    pub allowed: bool,
    pub reason: String,
}

impl PositionCheck {
    fn allow() -> Self {
        Self { allowed: true, reason: "passed all checks".into() }
    }
    fn reject(reason: String) -> Self {
        Self { allowed: false, reason }
    }
}

/// Check whether a new order should be allowed, based on position sizing and risk limits.
/// 基於持倉大小和風控限制，檢查是否應允許新訂單。
///
/// Priority order: daily loss → leverage → single position size → total exposure → correlated.
/// 優先級：日損 → 槓桿 → 單一持倉 → 總曝險 → 相關曝險。
/// Reducing orders always pass (原則 #5: 生存 > 利潤).
#[allow(clippy::too_many_arguments)]
pub fn check_order_allowed(
    qty: f64,
    price: f64,
    balance: f64,
    current_exposure_pct: f64,
    correlated_exposure_pct: f64,
    leverage: f64,
    daily_loss_pct: f64,
    is_reducing: bool,
    config: &RiskConfig,
) -> PositionCheck {
    if is_reducing {
        return PositionCheck::allow();
    }

    let limits = &config.limits;

    if daily_loss_pct >= limits.daily_loss_max_pct {
        return PositionCheck::reject(format!(
            "daily loss {:.2}% >= limit {:.2}%",
            daily_loss_pct, limits.daily_loss_max_pct
        ));
    }

    if leverage > limits.leverage_max {
        return PositionCheck::reject(format!(
            "leverage {:.1}x > limit {:.1}x",
            leverage, limits.leverage_max
        ));
    }

    if balance > 0.0 {
        let position_value = qty * price;
        let position_pct = position_value / balance * 100.0;
        if position_pct > limits.position_size_max_pct {
            return PositionCheck::reject(format!(
                "position {:.2}% > limit {:.2}%",
                position_pct, limits.position_size_max_pct
            ));
        }
    }

    if current_exposure_pct >= limits.total_exposure_max_pct {
        return PositionCheck::reject(format!(
            "total exposure {:.2}% >= limit {:.2}%",
            current_exposure_pct, limits.total_exposure_max_pct
        ));
    }

    if correlated_exposure_pct >= limits.correlated_exposure_max_pct {
        return PositionCheck::reject(format!(
            "correlated exposure {:.2}% >= limit {:.2}%",
            correlated_exposure_pct, limits.correlated_exposure_max_pct
        ));
    }

    PositionCheck::allow()
}

// ---------------------------------------------------------------------------
// Tick-level position checks / Tick 級持倉檢查
// ---------------------------------------------------------------------------

/// Action to take after a tick-level risk check / Tick 級風控檢查後的動作
#[derive(Debug, Clone)]
pub enum RiskAction {
    Hold,
    ClosePosition(String),
    HaltSession(String),
    SetCooldown(u64),
}

/// Tick-level risk check for a single position. See priority order in MODULE_NOTE.
/// Tick 級持倉風控檢查。優先級：hard stop → dyn stop → TP → trailing → time → cost_edge → drawdown → consec loss → daily loss。
///
/// `cost_edge_max_ratio` is sourced from BudgetConfig.attention_tax.cost_edge_max_ratio
/// (cross-Config read per ARCH-RC1 contract). Pass 1.0 to effectively disable the check.
#[allow(clippy::too_many_arguments)]
pub fn check_position_on_tick(
    pnl_pct: f64,
    peak_pnl_pct: f64,
    holding_hours: f64,
    cost_ratio: f64,
    regime: &str,
    atr_pct: Option<f64>,
    symbol: &str,
    entry_ts_ms: u64,
    consecutive_losses: u32,
    daily_loss_pct: f64,
    session_drawdown_pct: f64,
    cost_edge_max_ratio: f64,
    config: &RiskConfig,
) -> RiskAction {
    let rm = regime_multipliers(regime);
    let limits = &config.limits;
    let agent = &config.agent;
    let dyn_cfg = &config.dynamic_stop;

    // 1. Hard stop
    if pnl_pct <= -limits.stop_loss_max_pct {
        return RiskAction::ClosePosition(format!(
            "HARD STOP: pnl {:.2}% <= -{:.2}%",
            pnl_pct, limits.stop_loss_max_pct
        ));
    }

    // 2. Dynamic stop
    let dyn_stop = compute_dynamic_stop_pct(
        limits.stop_loss_max_pct * dyn_cfg.base_ratio,
        atr_pct,
        symbol,
        entry_ts_ms,
        regime,
        limits.stop_loss_max_pct,
        dyn_cfg.cap_ratio,
    );
    if pnl_pct <= -dyn_stop {
        return RiskAction::ClosePosition(format!(
            "DYNAMIC STOP: pnl {:.2}% <= -{:.2}% (regime={}, atr={:?})",
            pnl_pct, dyn_stop, regime, atr_pct
        ));
    }

    // 3. Take profit (if enforced)
    if limits.take_profit_enforced {
        let tp_target = limits.take_profit_max_pct * rm.tp;
        if pnl_pct >= tp_target {
            return RiskAction::ClosePosition(format!(
                "TAKE PROFIT: pnl {:.2}% >= {:.2}% (regime={})",
                pnl_pct, tp_target, regime
            ));
        }
    }

    // 4. Trailing stop
    if agent.trailing_enabled && peak_pnl_pct >= agent.trailing_activation_pct {
        let drawdown_from_peak = peak_pnl_pct - pnl_pct;
        let min_locked_profit = dyn_stop * dyn_cfg.trailing_min_rr;
        if drawdown_from_peak >= agent.trailing_distance_pct && pnl_pct >= min_locked_profit {
            return RiskAction::ClosePosition(format!(
                "TRAILING STOP: peak {:.2}% - current {:.2}% = {:.2}% >= distance {:.2}% (locked {:.2}% >= floor {:.2}%)",
                peak_pnl_pct, pnl_pct, drawdown_from_peak,
                agent.trailing_distance_pct, pnl_pct, min_locked_profit
            ));
        }
    }

    // 5. Time stop
    let max_hours = limits.holding_hours_max * rm.time;
    if holding_hours >= max_hours {
        return RiskAction::ClosePosition(format!(
            "TIME STOP: held {:.1}h >= limit {:.1}h (regime={})",
            holding_hours, max_hours, regime
        ));
    }

    // 6. Cost edge ratio — cross-Config read from BudgetConfig
    if cost_ratio >= cost_edge_max_ratio && pnl_pct > 0.0 {
        return RiskAction::ClosePosition(format!(
            "COST EDGE: ratio {:.2} >= {:.2}, pnl {:.2}% (suggest close while profitable)",
            cost_ratio, cost_edge_max_ratio, pnl_pct
        ));
    }

    // 7. Session drawdown
    if session_drawdown_pct >= limits.session_drawdown_max_pct {
        return RiskAction::HaltSession(format!(
            "SESSION DRAWDOWN: {:.2}% >= {:.2}%",
            session_drawdown_pct, limits.session_drawdown_max_pct
        ));
    }

    // 8. Consecutive losses cooldown
    if consecutive_losses >= limits.consec_loss_cooldown_count {
        let cooldown_ms = u64::from(limits.consec_loss_cooldown_min) * 60 * 1000;
        return RiskAction::SetCooldown(cooldown_ms);
    }

    // 9. Daily loss limit
    if daily_loss_pct >= limits.daily_loss_max_pct {
        return RiskAction::HaltSession(format!(
            "DAILY LOSS: {:.2}% >= {:.2}%",
            daily_loss_pct, limits.daily_loss_max_pct
        ));
    }

    RiskAction::Hold
}

// ===========================================================================
// Tests / 測試
// ===========================================================================
#[cfg(test)]
mod tests {
    use super::*;

    /// Default BudgetConfig.attention_tax.cost_edge_max_ratio is 0.8.
    const COST_EDGE_DEFAULT: f64 = 0.8;

    fn default_config() -> RiskConfig {
        RiskConfig::default()
    }

    // -- check_order_allowed tests --

    #[test]
    fn test_order_reducing_always_passes() {
        let cfg = default_config();
        let res = check_order_allowed(100.0, 50.0, 1000.0, 95.0, 70.0, 50.0, 10.0, true, &cfg);
        assert!(res.allowed, "reducing order must always pass: {}", res.reason);
    }

    #[test]
    fn test_order_daily_loss_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 10.0, 10.0, 5.0, 5.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("daily loss"));
    }

    #[test]
    fn test_order_leverage_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 10.0, 10.0, 25.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("leverage"));
    }

    #[test]
    fn test_order_single_position_exceeded() {
        let cfg = default_config();
        // qty * price / balance = 30*100/10000 = 30% > default 20%
        let res = check_order_allowed(30.0, 100.0, 10000.0, 10.0, 10.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("position"));
    }

    #[test]
    fn test_order_total_exposure_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 100.0, 10.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("total exposure"));
    }

    #[test]
    fn test_order_correlated_exposure_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 50.0, 60.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed);
        assert!(res.reason.contains("correlated"));
    }

    #[test]
    fn test_order_all_within_limits() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 30.0, 20.0, 5.0, 1.0, false, &cfg);
        assert!(res.allowed, "should pass: {}", res.reason);
    }

    #[test]
    fn test_order_zero_balance_position_check() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 0.0, 0.0, 0.0, 5.0, 0.0, false, &cfg);
        assert!(res.allowed, "zero balance should skip position check");
    }

    // -- check_position_on_tick tests --

    fn call_tick(
        pnl: f64, peak: f64, hold: f64, cost: f64, regime: &str,
        atr: Option<f64>, consec: u32, daily: f64, dd: f64, cfg: &RiskConfig,
    ) -> RiskAction {
        check_position_on_tick(
            pnl, peak, hold, cost, regime, atr, "BTCUSDT", 1000,
            consec, daily, dd, COST_EDGE_DEFAULT, cfg,
        )
    }

    #[test]
    fn test_tick_hard_stop() {
        let cfg = default_config();
        let action = call_tick(-5.0, 0.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
    }

    #[test]
    fn test_tick_dynamic_stop() {
        let cfg = default_config();
        let action = call_tick(-4.0, 0.0, 1.0, 0.0, "trending", Some(2.0), 0, 0.0, 0.0, &cfg);
        assert!(
            matches!(action, RiskAction::ClosePosition(ref r) if r.contains("DYNAMIC STOP")),
            "expected dynamic stop, got {:?}", action
        );
    }

    #[test]
    fn test_tick_take_profit_disabled() {
        let cfg = default_config(); // take_profit_enforced = false by default
        let action = call_tick(25.0, 25.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
            "TP should be disabled"
        );
    }

    #[test]
    fn test_tick_take_profit_enabled() {
        let mut cfg = default_config();
        cfg.limits.take_profit_enforced = true;
        cfg.limits.take_profit_max_pct = 10.0;
        // trending TP mult = 1.5 -> target = 15%
        let action = call_tick(16.0, 16.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")));
    }

    #[test]
    fn test_tick_trailing_stop() {
        let cfg = default_config();
        // peak=3 current=2 drawdown=1 >= distance=0.8; locked 2% > 3*0.5=1.5 floor
        let action = call_tick(2.0, 3.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING")));
    }

    #[test]
    fn test_tick_trailing_stop_not_activated() {
        let cfg = default_config();
        let action = call_tick(0.1, 0.5, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING")),
            "trailing should not trigger below activation"
        );
    }

    #[test]
    fn test_tick_time_stop() {
        let cfg = default_config();
        // max_holding 72 * trending time 1.5 = 108h
        let action = call_tick(1.0, 1.0, 110.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TIME STOP")));
    }

    #[test]
    fn test_tick_cost_edge_ratio() {
        let cfg = default_config();
        let action = call_tick(0.5, 0.5, 1.0, 0.85, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("COST EDGE")));
    }

    #[test]
    fn test_tick_cost_edge_not_profitable() {
        let cfg = default_config();
        let action = call_tick(-0.5, 0.0, 1.0, 0.9, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("COST EDGE")),
            "cost edge should not trigger when not profitable"
        );
    }

    #[test]
    fn test_tick_session_drawdown() {
        let cfg = default_config();
        let action = call_tick(0.0, 0.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 15.0, &cfg);
        assert!(matches!(action, RiskAction::HaltSession(_)));
    }

    #[test]
    fn test_tick_consecutive_losses_cooldown() {
        let cfg = default_config();
        let action = call_tick(0.0, 0.0, 1.0, 0.0, "trending", Some(1.0), 3, 0.0, 0.0, &cfg);
        match action {
            RiskAction::SetCooldown(ms) => assert_eq!(ms, 30 * 60 * 1000),
            _ => panic!("expected SetCooldown, got {:?}", action),
        }
    }

    #[test]
    fn test_tick_daily_loss_halt() {
        let cfg = default_config();
        let action = call_tick(0.0, 0.0, 1.0, 0.0, "trending", Some(1.0), 0, 5.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::HaltSession(ref r) if r.contains("DAILY LOSS")));
    }

    #[test]
    fn test_tick_hold_all_ok() {
        let cfg = default_config();
        let action = call_tick(0.5, 0.8, 2.0, 0.3, "trending", Some(1.0), 0, 1.0, 5.0, &cfg);
        assert!(matches!(action, RiskAction::Hold));
    }

    #[test]
    fn test_tick_priority_hard_stop_over_trailing() {
        let cfg = default_config();
        let action = call_tick(-5.0, 3.0, 1.0, 0.0, "trending", Some(1.0), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
    }

    #[test]
    fn test_pnl6_trailing_blocked_below_rr_floor() {
        // peak 1.1 current 0.2 drawdown 0.9 > 0.8, but locked 0.2 < dyn*0.5 floor
        let cfg = default_config();
        let action = call_tick(0.2, 1.1, 0.5, 0.0, "trending", Some(0.5), 0, 0.0, 0.0, &cfg);
        assert!(matches!(action, RiskAction::Hold), "expected Hold, got {:?}", action);
    }

    #[test]
    fn test_pnl6_trailing_fires_above_rr_floor() {
        // locked 2% > 1.5% floor -> fires
        let cfg = default_config();
        let action = call_tick(2.0, 3.0, 0.5, 0.0, "trending", Some(0.5), 0, 0.0, 0.0, &cfg);
        assert!(
            matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING STOP")),
            "expected trailing close, got {:?}", action
        );
    }
}

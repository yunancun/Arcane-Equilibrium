//! Order admission and tick-level position risk checks.
//! 訂單准入及 tick 級持倉風控檢查。
//!
//! MODULE_NOTE (中文):
//!   負責 8 項優先級排序的持倉風控檢查和訂單准入檢查。
//!   風控檢查為 fail-closed — 未知狀態 → 拒絕。
//!
//! MODULE_NOTE (English):
//!   Responsible for 8 priority-ordered position risk checks and order admission checks.
//!   Risk checks are fail-closed — unknown state → reject.

use super::config::{regime_multipliers, RiskManagerConfig};
use super::stops::compute_dynamic_stop_pct;

// ---------------------------------------------------------------------------
// Order admission / 訂單准入
// ---------------------------------------------------------------------------

/// Result of an order admission check / 訂單准入檢查結果
#[derive(Debug, Clone)]
pub struct PositionCheck {
    /// Whether the order is allowed / 是否允許下單
    pub allowed: bool,
    /// Human-readable reason / 人類可讀原因
    pub reason: String,
}

impl PositionCheck {
    fn allow() -> Self {
        Self {
            allowed: true,
            reason: "passed all checks".into(),
        }
    }

    fn reject(reason: String) -> Self {
        Self {
            allowed: false,
            reason,
        }
    }
}

/// Check whether a new order should be allowed, based on position sizing and risk limits.
/// 基於持倉大小和風控限制，檢查是否應允許新訂單。
///
/// Checks (in priority order) / 檢查（按優先級）:
/// 1. Daily loss limit / 日損限制
/// 2. Leverage limit / 槓桿限制
/// 3. Single position size limit / 單一持倉大小限制
/// 4. Total exposure limit / 總曝險限制
/// 5. Correlated exposure limit / 相關曝險限制
///
/// Position-reducing orders always pass (allow closing).
/// 減倉訂單永遠通過（允許平倉）。
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
    config: &RiskManagerConfig,
) -> PositionCheck {
    // Reducing orders always pass (principle #5: survival > profit — let positions close)
    // 減倉訂單永遠通過（原則 #5：生存 > 利潤 — 允許平倉）
    if is_reducing {
        return PositionCheck::allow();
    }

    // 1. Daily loss limit / 日損限制
    if daily_loss_pct >= config.max_daily_loss_pct {
        return PositionCheck::reject(format!(
            "daily loss {:.2}% >= limit {:.2}%",
            daily_loss_pct, config.max_daily_loss_pct
        ));
    }

    // 2. Leverage limit / 槓桿限制
    if leverage > config.max_leverage {
        return PositionCheck::reject(format!(
            "leverage {:.1}x > limit {:.1}x",
            leverage, config.max_leverage
        ));
    }

    // 3. Single position size limit / 單一持倉大小限制
    if balance > 0.0 {
        let position_value = qty * price;
        let position_pct = position_value / balance * 100.0;
        if position_pct > config.max_single_position_pct {
            return PositionCheck::reject(format!(
                "position {:.2}% > limit {:.2}%",
                position_pct, config.max_single_position_pct
            ));
        }
    }

    // 4. Total exposure limit / 總曝險限制
    if current_exposure_pct >= config.max_total_exposure_pct {
        return PositionCheck::reject(format!(
            "total exposure {:.2}% >= limit {:.2}%",
            current_exposure_pct, config.max_total_exposure_pct
        ));
    }

    // 5. Correlated exposure limit / 相關曝險限制
    if correlated_exposure_pct >= config.max_correlated_exposure_pct {
        return PositionCheck::reject(format!(
            "correlated exposure {:.2}% >= limit {:.2}%",
            correlated_exposure_pct, config.max_correlated_exposure_pct
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
    /// No action needed / 無需動作
    Hold,
    /// Close the position with given reason / 以指定原因平倉
    ClosePosition(String),
    /// Halt the entire session (circuit breaker) / 暫停整個會話（熔斷）
    HaltSession(String),
    /// Enter cooldown for specified milliseconds / 進入指定毫秒的冷卻期
    SetCooldown(u64),
}

/// Check a single position on each tick against all risk rules.
/// 在每個 tick 對單一持倉執行所有風控規則檢查。
///
/// Priority order (first match wins) / 優先級（第一個匹配即生效）:
/// 1. Hard stop: pnl <= -max_stop_loss_pct / 硬止損
/// 2. Dynamic stop: computed from ATR + regime / 動態止損（ATR + regime）
/// 3. Take profit (if enabled): pnl >= tp x regime_mult / 止盈（若啟用）
/// 4. Trailing stop: peak - current >= distance / 追蹤止損
/// 5. Time stop: holding_hours >= max x time_mult / 時間止損
/// 6. Cost edge ratio: cost_ratio >= 0.8 AND profitable / 成本邊際比率
/// 7. Session drawdown: >= max_session_drawdown_pct / 會話回撤
/// 8. Consecutive losses: >= cooldown_count / 連續虧損
///
/// Returns `RiskAction::Hold` if no rule triggers.
/// 若無規則觸發則回傳 `RiskAction::Hold`。
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
    config: &RiskManagerConfig,
) -> RiskAction {
    let rm = regime_multipliers(regime);

    // 1. Hard stop — unconditional, non-negotiable
    //    硬止損 — 無條件，不可協商
    if pnl_pct <= -config.max_stop_loss_pct {
        return RiskAction::ClosePosition(format!(
            "HARD STOP: pnl {:.2}% <= -{:.2}%",
            pnl_pct, config.max_stop_loss_pct
        ));
    }

    // 2. Dynamic stop — ATR-adaptive with anti-cluster offset
    //    動態止損 — ATR 自適應 + 反聚集偏移
    // PNL-7: dynamic_stop_base_ratio + dynamic_stop_cap_ratio now configurable.
    // PNL-7：base/cap 比例已從寫死的 0.6/0.8 提取為配置。
    let dyn_stop = compute_dynamic_stop_pct(
        config.max_stop_loss_pct * config.dynamic_stop_base_ratio,
        atr_pct,
        symbol,
        entry_ts_ms,
        regime,
        config.max_stop_loss_pct,
        config.dynamic_stop_cap_ratio,
    );
    if pnl_pct <= -dyn_stop {
        return RiskAction::ClosePosition(format!(
            "DYNAMIC STOP: pnl {:.2}% <= -{:.2}% (regime={}, atr={:?})",
            pnl_pct, dyn_stop, regime, atr_pct
        ));
    }

    // 3. Take profit (if enabled) — with regime multiplier
    //    止盈（若啟用）— 含 regime 乘數
    if config.tp_enabled {
        let tp_target = config.max_take_profit_pct * rm.tp;
        if pnl_pct >= tp_target {
            return RiskAction::ClosePosition(format!(
                "TAKE PROFIT: pnl {:.2}% >= {:.2}% (regime={})",
                pnl_pct, tp_target, regime
            ));
        }
    }

    // 4. Trailing stop — only if enabled and activation threshold met
    //    追蹤止損 — 僅在啟用且達到啟動門檻時
    // PNL-6: enforce a minimum RR floor — locked-in pnl must be at least
    // half of the dynamic stop distance, so winners cannot be cut at
    // near-breakeven while losers run to the full stop. Guarantees ~1:2 RR.
    // PNL-6：強制 RR 下限 — 鎖定盈利必須 ≥ dynamic stop 的一半，避免贏 0.2%/輸 3% 倒掛。
    if config.trailing_stop_enabled && peak_pnl_pct >= config.trailing_stop_activation_pct {
        let drawdown_from_peak = peak_pnl_pct - pnl_pct;
        // PNL-7: trailing_min_rr_ratio configurable (was hardcoded 0.5)
        let min_locked_profit = dyn_stop * config.trailing_min_rr_ratio;
        if drawdown_from_peak >= config.trailing_stop_distance_pct
            && pnl_pct >= min_locked_profit
        {
            return RiskAction::ClosePosition(format!(
                "TRAILING STOP: peak {:.2}% - current {:.2}% = {:.2}% >= distance {:.2}% (locked {:.2}% >= floor {:.2}%)",
                peak_pnl_pct, pnl_pct, drawdown_from_peak,
                config.trailing_stop_distance_pct, pnl_pct, min_locked_profit
            ));
        }
    }

    // 5. Time stop — with regime multiplier
    //    時間止損 — 含 regime 乘數
    let max_hours = config.max_holding_hours * rm.time;
    if holding_hours >= max_hours {
        return RiskAction::ClosePosition(format!(
            "TIME STOP: held {:.1}h >= limit {:.1}h (regime={})",
            holding_hours, max_hours, regime
        ));
    }

    // 6. Cost edge ratio — close if cost is eating the edge AND position is profitable
    //    成本邊際比率 — 若成本侵蝕優勢且持倉有利潤則平倉
    if cost_ratio >= config.max_cost_edge_ratio && pnl_pct > 0.0 {
        return RiskAction::ClosePosition(format!(
            "COST EDGE: ratio {:.2} >= {:.2}, pnl {:.2}% (suggest close while profitable)",
            cost_ratio, config.max_cost_edge_ratio, pnl_pct
        ));
    }

    // 7. Session drawdown — circuit breaker
    //    會話回撤 — 熔斷
    if session_drawdown_pct >= config.max_session_drawdown_pct {
        return RiskAction::HaltSession(format!(
            "SESSION DRAWDOWN: {:.2}% >= {:.2}%",
            session_drawdown_pct, config.max_session_drawdown_pct
        ));
    }

    // 8. Consecutive losses — cooldown
    //    連續虧損 — 冷卻期
    if consecutive_losses >= config.consecutive_loss_cooldown_count {
        let cooldown_ms = u64::from(config.consecutive_loss_cooldown_minutes) * 60 * 1000;
        return RiskAction::SetCooldown(cooldown_ms);
    }

    // 9. Daily loss limit — halt if breached
    //    日損限制 — 超限則暫停
    if daily_loss_pct >= config.max_daily_loss_pct {
        return RiskAction::HaltSession(format!(
            "DAILY LOSS: {:.2}% >= {:.2}%",
            daily_loss_pct, config.max_daily_loss_pct
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

    fn default_config() -> RiskManagerConfig {
        RiskManagerConfig::default()
    }

    // -- check_order_allowed tests / 訂單准入測試 --

    #[test]
    fn test_order_reducing_always_passes() {
        let cfg = default_config();
        let res = check_order_allowed(100.0, 50.0, 1000.0, 95.0, 70.0, 50.0, 10.0, true, &cfg);
        assert!(
            res.allowed,
            "reducing order must always pass: {}",
            res.reason
        );
    }

    #[test]
    fn test_order_daily_loss_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 10.0, 10.0, 5.0, 5.0, false, &cfg);
        assert!(!res.allowed, "should reject on daily loss");
        assert!(res.reason.contains("daily loss"));
    }

    #[test]
    fn test_order_leverage_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 10.0, 10.0, 25.0, 0.0, false, &cfg);
        assert!(!res.allowed, "should reject on leverage");
        assert!(res.reason.contains("leverage"));
    }

    #[test]
    fn test_order_single_position_exceeded() {
        let cfg = default_config();
        // qty=30, price=100 -> 3000 / 10000 = 30% > 20% limit
        let res = check_order_allowed(30.0, 100.0, 10000.0, 10.0, 10.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed, "should reject on position size");
        assert!(res.reason.contains("position"));
    }

    #[test]
    fn test_order_total_exposure_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 100.0, 10.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed, "should reject on total exposure");
        assert!(res.reason.contains("total exposure"));
    }

    #[test]
    fn test_order_correlated_exposure_exceeded() {
        let cfg = default_config();
        let res = check_order_allowed(1.0, 100.0, 10000.0, 50.0, 60.0, 5.0, 0.0, false, &cfg);
        assert!(!res.allowed, "should reject on correlated exposure");
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
        // Zero balance -> skip position % check (avoid division by zero)
        let res = check_order_allowed(1.0, 100.0, 0.0, 0.0, 0.0, 5.0, 0.0, false, &cfg);
        assert!(res.allowed, "zero balance should skip position check");
    }

    // -- check_position_on_tick tests / Tick 級檢查測試 --

    #[test]
    fn test_tick_hard_stop() {
        let cfg = default_config();
        let action = check_position_on_tick(
            -5.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
    }

    #[test]
    fn test_tick_dynamic_stop() {
        let cfg = default_config();
        // pnl = -4.0% should trigger dynamic stop (base = 5.0*0.6=3.0, with ATR and offset)
        let action = check_position_on_tick(
            -4.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(2.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            matches!(action, RiskAction::ClosePosition(ref r) if r.contains("DYNAMIC STOP")),
            "expected dynamic stop, got {:?}",
            action
        );
    }

    #[test]
    fn test_tick_take_profit_disabled() {
        let cfg = default_config(); // tp_enabled = false
        let action = check_position_on_tick(
            25.0,
            25.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")),
            "TP should be disabled"
        );
    }

    #[test]
    fn test_tick_take_profit_enabled() {
        let mut cfg = default_config();
        cfg.tp_enabled = true;
        cfg.max_take_profit_pct = 10.0;
        // trending TP mult = 1.5 -> target = 15%
        let action = check_position_on_tick(
            16.0,
            16.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TAKE PROFIT")));
    }

    #[test]
    fn test_tick_trailing_stop() {
        let cfg = default_config(); // trailing enabled, activation=1.0%, distance=0.8%
                                    // peak=3.0%, current=2.0% -> drawdown=1.0% > distance=0.8%
        let action = check_position_on_tick(
            2.0,
            3.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING")));
    }

    #[test]
    fn test_tick_trailing_stop_not_activated() {
        let cfg = default_config(); // activation=1.0%
                                    // peak=0.5% < activation threshold -> trailing stop should NOT trigger
        let action = check_position_on_tick(
            0.1,
            0.5,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING")),
            "trailing should not trigger below activation"
        );
    }

    #[test]
    fn test_tick_time_stop() {
        let cfg = default_config(); // max_holding_hours=72.0
                                    // trending time mult = 1.5 -> limit = 108h
        let action = check_position_on_tick(
            1.0,
            1.0,
            110.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TIME STOP")));
    }

    #[test]
    fn test_tick_cost_edge_ratio() {
        let cfg = default_config(); // max_cost_edge_ratio=0.8
        let action = check_position_on_tick(
            0.5,
            0.5,
            1.0,
            0.85,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("COST EDGE")));
    }

    #[test]
    fn test_tick_cost_edge_not_profitable() {
        let cfg = default_config();
        // cost_ratio high BUT pnl negative -> should NOT trigger cost edge
        let action = check_position_on_tick(
            -0.5,
            0.0,
            1.0,
            0.9,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(
            !matches!(action, RiskAction::ClosePosition(ref r) if r.contains("COST EDGE")),
            "cost edge should not trigger when not profitable"
        );
    }

    #[test]
    fn test_tick_session_drawdown() {
        let cfg = default_config(); // max_session_drawdown=15.0%
        let action = check_position_on_tick(
            0.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            15.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::HaltSession(_)));
    }

    #[test]
    fn test_tick_consecutive_losses_cooldown() {
        let cfg = default_config(); // cooldown_count=3, cooldown_minutes=30
        let action = check_position_on_tick(
            0.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            3,
            0.0,
            0.0,
            &cfg,
        );
        match action {
            RiskAction::SetCooldown(ms) => {
                assert_eq!(ms, 30 * 60 * 1000, "cooldown should be 30 minutes");
            }
            _ => panic!("expected SetCooldown, got {:?}", action),
        }
    }

    #[test]
    fn test_tick_daily_loss_halt() {
        let cfg = default_config(); // max_daily_loss=5.0%
        let action = check_position_on_tick(
            0.0,
            0.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            5.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::HaltSession(ref r) if r.contains("DAILY LOSS")));
    }

    #[test]
    fn test_tick_hold_all_ok() {
        let cfg = default_config();
        let action = check_position_on_tick(
            0.5,
            0.8,
            2.0,
            0.3,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            1.0,
            5.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::Hold));
    }

    #[test]
    fn test_tick_priority_hard_stop_over_trailing() {
        let mut cfg = default_config();
        cfg.trailing_stop_enabled = true;
        // pnl = -5.0 triggers BOTH hard stop and trailing (peak=3, current=-5, drawdown=8)
        // Hard stop should win (higher priority)
        let action = check_position_on_tick(
            -5.0,
            3.0,
            1.0,
            0.0,
            "trending",
            Some(1.0),
            "BTCUSDT",
            1000,
            0,
            0.0,
            0.0,
            &cfg,
        );
        assert!(matches!(action, RiskAction::ClosePosition(ref r) if r.contains("HARD STOP")));
    }

    #[test]
    fn test_pnl6_trailing_blocked_below_rr_floor() {
        // PNL-6: peak 1.1%, pulled back to 0.2% — drawdown 0.9% > distance 0.8%,
        // but locked profit 0.2% < dyn_stop_floor (3% × 0.5 = 1.5%) → no trailing stop.
        // PNL-6：鎖定盈利 < dyn_stop × 0.5 → 不允許追蹤止損平倉。
        let mut cfg = RiskManagerConfig::default();
        cfg.trailing_stop_enabled = true;
        cfg.trailing_stop_activation_pct = 1.0;
        cfg.trailing_stop_distance_pct = 0.8;
        cfg.max_stop_loss_pct = 5.0; // dyn base = 3.0
        let action = check_position_on_tick(
            0.2, 1.1, 0.5, 0.0, "trending", Some(0.5),
            "BTCUSDT", 1000, 0, 0.0, 0.0, &cfg,
        );
        assert!(matches!(action, RiskAction::Hold), "expected Hold, got {:?}", action);
    }

    #[test]
    fn test_pnl6_trailing_fires_above_rr_floor() {
        // Locked 2% > dyn_stop × 0.5 = 1.5% → trailing stop fires normally.
        let mut cfg = RiskManagerConfig::default();
        cfg.trailing_stop_enabled = true;
        cfg.trailing_stop_activation_pct = 1.0;
        cfg.trailing_stop_distance_pct = 0.8;
        cfg.max_stop_loss_pct = 5.0;
        let action = check_position_on_tick(
            2.0, 3.0, 0.5, 0.0, "trending", Some(0.5),
            "BTCUSDT", 1000, 0, 0.0, 0.0, &cfg,
        );
        assert!(
            matches!(action, RiskAction::ClosePosition(ref r) if r.contains("TRAILING STOP")),
            "expected trailing close, got {:?}", action
        );
    }
}

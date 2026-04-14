//! Stop Manager — hard/trailing/time stops + ATR position sizing.
//! 止損管理器 — 硬止損/追蹤止損/時間止損 + ATR 倉位計算。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Config / 配置
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StopConfig {
    pub hard_stop_pct: f64,
    pub trailing_stop_pct: Option<f64>,
    pub time_stop_hours: Option<f64>,
    pub atr_multiplier: Option<f64>,
    /// Take profit percentage (None = disabled). 止盈百分比（None = 禁用）。
    #[serde(default)]
    pub take_profit_pct: Option<f64>,
    /// Trailing stop activation threshold (% profit required before trailing engages).
    /// Textbook trailing stop: "once profit reaches X%, start trailing by Y% off peak".
    /// None → defaults to `trailing_stop_pct` (worst-case lock-in ~ trail² of entry ≈ trivial).
    /// For strict profit-locking set this above `trailing_stop_pct` (e.g. activation=3%, trail=2%
    /// → worst-case trail_price ≥ entry × 1.0094, guaranteed ≥0.9% locked profit).
    /// 跟蹤止損啟動閾值。None 時預設等於 `trailing_stop_pct`（最差僅鎖定 ~trail² 微小虧損）。
    /// 嚴格鎖利請設高於 `trailing_stop_pct`（例如 activation=3%, trail=2%）。
    #[serde(default)]
    pub trailing_activation_pct: Option<f64>,
}

impl Default for StopConfig {
    fn default() -> Self {
        Self {
            hard_stop_pct: 5.0,
            trailing_stop_pct: None,
            time_stop_hours: None,
            atr_multiplier: Some(2.0),
            take_profit_pct: None,
            trailing_activation_pct: None,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Position State / 持倉狀態
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone)]
pub struct PositionState {
    pub entry_price: f64,
    pub best_price: f64,
    pub is_long: bool,
    pub entry_ts_ms: u64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Stop Check / 止損檢查
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum StopType {
    /// Take profit target reached / 止盈目標達到
    TakeProfit,
    Hard,
    Trailing,
    Time,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StopTrigger {
    pub stop_type: StopType,
    pub trigger_price: Option<f64>,
    pub reason: String,
}

/// Check all stop conditions for a position.
/// 檢查持倉的所有止損條件。
pub fn check_stops(
    config: &StopConfig,
    pos: &PositionState,
    current_price: f64,
    now_ms: u64,
) -> Option<StopTrigger> {
    // Priority 0: Take profit (highest priority — lock in gains)
    // 優先級 0：止盈（最高優先級 — 鎖定收益）
    if let Some(trigger) = check_take_profit(config, pos, current_price) {
        return Some(trigger);
    }

    // Priority 1: Hard stop
    if let Some(trigger) = check_hard_stop(config, pos, current_price) {
        return Some(trigger);
    }

    // Priority 2: Trailing stop
    if let Some(trigger) = check_trailing_stop(config, pos, current_price) {
        return Some(trigger);
    }

    // Priority 3: Time stop
    if let Some(trigger) = check_time_stop(config, pos, now_ms) {
        return Some(trigger);
    }

    None
}

fn check_take_profit(config: &StopConfig, pos: &PositionState, price: f64) -> Option<StopTrigger> {
    let tp_pct = config.take_profit_pct?;
    let tp_price = if pos.is_long {
        pos.entry_price * (1.0 + tp_pct / 100.0)
    } else {
        pos.entry_price * (1.0 - tp_pct / 100.0)
    };
    let triggered = if pos.is_long {
        price >= tp_price
    } else {
        price <= tp_price
    };
    if triggered {
        Some(StopTrigger {
            stop_type: StopType::TakeProfit,
            trigger_price: Some(tp_price),
            reason: format!("take_profit: price {price:.2} crossed {tp_price:.2}"),
        })
    } else {
        None
    }
}

fn check_hard_stop(config: &StopConfig, pos: &PositionState, price: f64) -> Option<StopTrigger> {
    let stop_price = if pos.is_long {
        pos.entry_price * (1.0 - config.hard_stop_pct / 100.0)
    } else {
        pos.entry_price * (1.0 + config.hard_stop_pct / 100.0)
    };

    let triggered = if pos.is_long {
        price <= stop_price
    } else {
        price >= stop_price
    };

    if triggered {
        Some(StopTrigger {
            stop_type: StopType::Hard,
            trigger_price: Some(stop_price),
            reason: format!("hard_stop: price {price:.2} crossed {stop_price:.2}"),
        })
    } else {
        None
    }
}

fn check_trailing_stop(
    config: &StopConfig,
    pos: &PositionState,
    price: f64,
) -> Option<StopTrigger> {
    let trail_pct = config.trailing_stop_pct?;
    // Activation threshold — default to trail_pct so trail_price is never below entry.
    // 啟動閾值預設等於 trail_pct，保證 trail_price 不會落於 entry 下方（鎖損 bug 修復）。
    let activation_pct = config.trailing_activation_pct.unwrap_or(trail_pct);

    // Gate 1: best_price must reach the activation threshold (real profit, not a single tick above entry).
    // 閘門 1：best_price 必須達到啟動閾值（真實利潤，而非剛過 entry 一個 tick）。
    let activation_price = if pos.is_long {
        pos.entry_price * (1.0 + activation_pct / 100.0)
    } else {
        pos.entry_price * (1.0 - activation_pct / 100.0)
    };
    let activated = if pos.is_long {
        pos.best_price >= activation_price
    } else {
        pos.best_price <= activation_price
    };
    if !activated {
        return None;
    }

    let trail_price = if pos.is_long {
        pos.best_price * (1.0 - trail_pct / 100.0)
    } else {
        pos.best_price * (1.0 + trail_pct / 100.0)
    };

    let triggered = if pos.is_long {
        price <= trail_price
    } else {
        price >= trail_price
    };

    if triggered {
        // Structured logging for trailing-stop triggers. Used to diagnose PnL asymmetry
        // (unrealized gross-positive vs realized gross-negative) and verify activation gating.
        // 結構化日誌：用於診斷 PnL 非對稱（未實現正/已實現負）及驗證 activation 閘門。
        let pnl_pct = if pos.is_long {
            (price - pos.entry_price) / pos.entry_price * 100.0
        } else {
            (pos.entry_price - price) / pos.entry_price * 100.0
        };
        tracing::info!(
            event = "trailing_stop_triggered",
            is_long = pos.is_long,
            entry_price = pos.entry_price,
            best_price = pos.best_price,
            trigger_price = price,
            trail_price = trail_price,
            activation_pct = activation_pct,
            trail_pct = trail_pct,
            pnl_pct_approx = pnl_pct,
            entry_ts_ms = pos.entry_ts_ms,
            "trailing stop triggered / 跟蹤止損觸發"
        );
        Some(StopTrigger {
            stop_type: StopType::Trailing,
            trigger_price: Some(trail_price),
            reason: format!(
                "trailing_stop: price {price:.2}, trail from best {:.2} (activation {activation_pct}%, trail {trail_pct}%)",
                pos.best_price
            ),
        })
    } else {
        None
    }
}

fn check_time_stop(config: &StopConfig, pos: &PositionState, now_ms: u64) -> Option<StopTrigger> {
    let hours = config.time_stop_hours?;
    let max_hold_ms = (hours * 3_600_000.0) as u64;
    let held_ms = now_ms.saturating_sub(pos.entry_ts_ms);

    if held_ms >= max_hold_ms {
        Some(StopTrigger {
            stop_type: StopType::Time,
            trigger_price: None,
            reason: format!(
                "time_stop: held {:.1}h >= {hours:.1}h",
                held_ms as f64 / 3_600_000.0
            ),
        })
    } else {
        None
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// ATR Position Sizing / ATR 倉位計算
// ═══════════════════════════════════════════════════════════════════════════════

/// Compute position size based on ATR.
/// 根據 ATR 計算倉位大小。
pub fn compute_atr_position_size(
    balance: f64,
    risk_per_trade_pct: f64,
    atr: f64,
    atr_multiplier: f64,
    min_qty: f64,
    max_qty: f64,
) -> f64 {
    if atr <= 0.0 || atr_multiplier <= 0.0 {
        return min_qty;
    }
    let risk_amount = balance * (risk_per_trade_pct / 100.0);
    let stop_distance = atr * atr_multiplier;
    let qty = risk_amount / stop_distance;
    qty.clamp(min_qty, max_qty)
}

/// Update best price for trailing stop tracking.
/// 更新追蹤止損的最佳價格。
pub fn update_best_price(pos: &mut PositionState, current_price: f64) {
    if pos.is_long {
        pos.best_price = pos.best_price.max(current_price);
    } else {
        pos.best_price = pos.best_price.min(current_price);
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn long_pos(entry: f64, best: f64) -> PositionState {
        PositionState {
            entry_price: entry,
            best_price: best,
            is_long: true,
            entry_ts_ms: 0,
        }
    }

    fn short_pos(entry: f64, best: f64) -> PositionState {
        PositionState {
            entry_price: entry,
            best_price: best,
            is_long: false,
            entry_ts_ms: 0,
        }
    }

    #[test]
    fn test_hard_stop_long_triggered() {
        let config = StopConfig::default(); // 5%
        let pos = long_pos(50000.0, 50000.0);
        let r = check_stops(&config, &pos, 47000.0, 0);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Hard);
    }

    #[test]
    fn test_hard_stop_long_not_triggered() {
        let config = StopConfig::default();
        let pos = long_pos(50000.0, 50000.0);
        assert!(check_stops(&config, &pos, 48000.0, 0).is_none());
    }

    #[test]
    fn test_hard_stop_short_triggered() {
        let config = StopConfig::default();
        let pos = short_pos(50000.0, 50000.0);
        let r = check_stops(&config, &pos, 53000.0, 0);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Hard);
    }

    #[test]
    fn test_trailing_stop_long() {
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            ..StopConfig::default()
        };
        let pos = long_pos(50000.0, 55000.0); // profitable
                                              // trail = 55000 * 0.98 = 53900
        let r = check_stops(&config, &pos, 53800.0, 0);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Trailing);
    }

    #[test]
    fn test_trailing_stop_not_profitable_skip() {
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            ..StopConfig::default()
        };
        let pos = long_pos(50000.0, 49000.0); // not profitable → activation gate blocks
        assert!(check_trailing_stop(&config, &pos, 48000.0).is_none());
    }

    // Regression: pre-fix behaviour let trailing fire below entry when best_price was
    // only a tick above entry (activation gate missing). With default activation=trail_pct,
    // best must reach entry*(1+trail_pct/100) before trailing engages. Protects against
    // the "unrealized gross-positive / realized gross-negative" PnL asymmetry.
    // 回歸測試：修復前 best_price 剛過 entry 就能觸發 trailing，導致在虧損位鎖損。
    #[test]
    fn test_trailing_stop_below_activation_skip_long() {
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            ..StopConfig::default() // activation defaults to trail (2%)
        };
        // best 50500 = +1% (below activation at +2% = 51000) → no trail
        let pos = long_pos(50000.0, 50500.0);
        // pre-fix bug: trail_price would be 50500*0.98=49490, and price 49400 would fire
        assert!(check_trailing_stop(&config, &pos, 49400.0).is_none(),
            "trailing must not fire below activation threshold (regression guard)");
    }

    #[test]
    fn test_trailing_stop_below_activation_skip_short() {
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            ..StopConfig::default()
        };
        // short: best 49500 = +1% profit; activation at 49000 (-2%) not yet reached
        let pos = short_pos(50000.0, 49500.0);
        assert!(check_trailing_stop(&config, &pos, 50100.0).is_none());
    }

    #[test]
    fn test_trailing_stop_explicit_activation_threshold() {
        // activation=5%, trail=2% — trail only engages after best_price reaches +5%
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            trailing_activation_pct: Some(5.0),
            ..StopConfig::default()
        };
        // best at +4% — below 5% activation → no trail
        let pos1 = long_pos(50000.0, 52000.0);
        assert!(check_trailing_stop(&config, &pos1, 51000.0).is_none());
        // best at +5% exactly — activation met, trail_price = 52500*0.98 = 51450
        let pos2 = long_pos(50000.0, 52500.0);
        let r = check_trailing_stop(&config, &pos2, 51400.0);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Trailing);
    }

    #[test]
    fn test_trailing_with_higher_activation_locks_profit() {
        // activation=3%, trail=2% — worst-case trail_price at activation moment
        // = entry * 1.03 * 0.98 = entry * 1.0094, i.e. ≥0.94% profit guaranteed.
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            trailing_activation_pct: Some(3.0),
            ..StopConfig::default()
        };
        let pos = long_pos(100.0, 103.0); // just hit activation
        let trail_price_at_activation = 103.0 * 0.98;
        assert!(trail_price_at_activation > 100.0,
            "activation > trail_pct guarantees profit at trail moment");
        // triggered slightly below trail_price
        let r = check_trailing_stop(&config, &pos, trail_price_at_activation - 0.01);
        assert!(r.is_some());
    }

    #[test]
    fn test_trailing_activation_zero_fires_at_entry() {
        // activation=0% → gate opens the moment best_price >= entry (pre-fix semantic).
        // Documents that explicit 0.0 reproduces the old behaviour — new deployments
        // should omit the field or pass `None` to default to `trail_pct`.
        // 顯式 0% 啟動閾值 = 舊行為；新部署應省略或傳 None 以獲得安全預設。
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            trailing_activation_pct: Some(0.0),
            ..StopConfig::default()
        };
        // best = entry + $0.01 → gate passes; trail_price = 100.01 * 0.98 ≈ 98.01 (below entry!)
        let pos = long_pos(100.0, 100.01);
        let r = check_trailing_stop(&config, &pos, 98.00);
        assert!(r.is_some(), "activation=0 lets trail fire on any tiny uptick");
        assert_eq!(r.unwrap().stop_type, StopType::Trailing);
    }

    #[test]
    fn test_trailing_short_higher_activation_locks_profit() {
        // Short mirror of test_trailing_with_higher_activation_locks_profit.
        // activation=5%, trail=2% — at activation (best = entry*0.95),
        // trail_price = 0.95 * entry * 1.02 = 0.969 * entry, i.e. ≥3.1% profit locked.
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            trailing_activation_pct: Some(5.0),
            ..StopConfig::default()
        };
        // best only at -2% — below 5% activation → no trail
        let pos1 = short_pos(100.0, 98.0);
        assert!(check_trailing_stop(&config, &pos1, 99.5).is_none());
        // best at -5% exactly → activation met, trail_price = 95 * 1.02 = 96.9
        let pos2 = short_pos(100.0, 95.0);
        let trail_price = 95.0 * 1.02;
        assert!(trail_price < 100.0, "activation > trail_pct locks short-side profit");
        let r = check_trailing_stop(&config, &pos2, trail_price + 0.01);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Trailing);
    }

    #[test]
    fn test_trailing_stop_short() {
        let config = StopConfig {
            trailing_stop_pct: Some(2.0),
            ..StopConfig::default()
        };
        let pos = short_pos(50000.0, 45000.0); // profitable short
                                               // trail = 45000 * 1.02 = 45900
        let r = check_stops(&config, &pos, 46000.0, 0);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Trailing);
    }

    #[test]
    fn test_time_stop() {
        let config = StopConfig {
            time_stop_hours: Some(24.0),
            ..StopConfig::default()
        };
        let pos = PositionState {
            entry_price: 50000.0,
            best_price: 50000.0,
            is_long: true,
            entry_ts_ms: 0,
        };
        let ms_25h = 25 * 3_600_000;
        let r = check_stops(&config, &pos, 50000.0, ms_25h);
        assert!(r.is_some());
        assert_eq!(r.unwrap().stop_type, StopType::Time);
    }

    #[test]
    fn test_time_stop_not_triggered() {
        let config = StopConfig {
            time_stop_hours: Some(24.0),
            ..StopConfig::default()
        };
        let pos = PositionState {
            entry_price: 50000.0,
            best_price: 50000.0,
            is_long: true,
            entry_ts_ms: 0,
        };
        assert!(check_stops(&config, &pos, 50000.0, 10_000_000).is_none()); // ~2.7h
    }

    #[test]
    fn test_atr_position_size() {
        let qty = compute_atr_position_size(10000.0, 3.0, 500.0, 2.0, 0.001, 10.0);
        // risk = 300, stop = 1000, qty = 0.3
        assert!((qty - 0.3).abs() < 0.001);
    }

    #[test]
    fn test_atr_position_size_clamped() {
        let qty = compute_atr_position_size(10000.0, 3.0, 1.0, 2.0, 0.001, 10.0);
        // risk = 300, stop = 2, qty = 150 → clamped to 10
        assert_eq!(qty, 10.0);
    }

    #[test]
    fn test_atr_zero_returns_min() {
        assert_eq!(
            compute_atr_position_size(10000.0, 3.0, 0.0, 2.0, 0.001, 10.0),
            0.001
        );
    }

    #[test]
    fn test_update_best_price_long() {
        let mut pos = long_pos(50000.0, 51000.0);
        update_best_price(&mut pos, 52000.0);
        assert_eq!(pos.best_price, 52000.0);
        update_best_price(&mut pos, 51500.0);
        assert_eq!(pos.best_price, 52000.0); // doesn't decrease
    }

    #[test]
    fn test_update_best_price_short() {
        let mut pos = short_pos(50000.0, 49000.0);
        update_best_price(&mut pos, 48000.0);
        assert_eq!(pos.best_price, 48000.0);
        update_best_price(&mut pos, 48500.0);
        assert_eq!(pos.best_price, 48000.0); // doesn't increase
    }

    #[test]
    fn test_hard_stop_priority_over_trailing() {
        // Both hard and trailing triggered, hard should win (priority 1)
        let config = StopConfig {
            hard_stop_pct: 5.0,
            trailing_stop_pct: Some(2.0),
            ..StopConfig::default()
        };
        let pos = long_pos(50000.0, 55000.0);
        // Hard stop at 47500, trailing at 53900. Price 47000 triggers both.
        let r = check_stops(&config, &pos, 47000.0, 0).unwrap();
        assert_eq!(r.stop_type, StopType::Hard);
    }
}

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
}

impl Default for StopConfig {
    fn default() -> Self {
        Self {
            hard_stop_pct: 5.0,
            trailing_stop_pct: None,
            time_stop_hours: None,
            atr_multiplier: Some(2.0),
            take_profit_pct: None,
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

    // Only trail if position is profitable
    let is_profitable = if pos.is_long {
        pos.best_price > pos.entry_price
    } else {
        pos.best_price < pos.entry_price
    };

    if !is_profitable {
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
        Some(StopTrigger {
            stop_type: StopType::Trailing,
            trigger_price: Some(trail_price),
            reason: format!(
                "trailing_stop: price {price:.2}, trail from best {:.2}",
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
        let pos = long_pos(50000.0, 49000.0); // not profitable
        assert!(check_trailing_stop(&config, &pos, 48000.0).is_none());
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

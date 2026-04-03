//! Golden Dataset — Extreme scenarios for R-03 modules.
//! 黃金數據集 — R-03 模組的極端場景測試。
//!
//! Tests SM cascade under stress, execution edge cases,
//! stop manager boundary conditions, portfolio correlation limits.
//! 測試 SM 級聯壓力、執行邊界情況、止損邊界條件、組合相關性極限。

use openclaw_core::backtest::{self, Bar, Signal, SignalGenerator};
use openclaw_core::execution;
use openclaw_core::governance_core::GovernanceCore;
use openclaw_core::guardian::{
    ExistingPosition, Guardian, PortfolioContext, TradeIntentCheck, Verdict,
};
use openclaw_core::portfolio;
use openclaw_core::sm::risk_gov::{RiskEvent, RiskLevel};
use openclaw_core::stop_manager::{self, PositionState, StopConfig};

// ═══════════════════════════════════════════════════════════════════════════════
// Extreme SM Cascade Tests / 極端 SM 級聯測試
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_cascade_rapid_escalation_to_circuit_breaker() {
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();
    assert!(core.is_authorized());

    // Simulate rapid market crash: drawdown 20%
    let result = core.evaluate_and_cascade(
        0.95, 20.0, 6.0, 12, true, true,
    );
    let r = result.unwrap();
    assert!(r.success);
    assert_eq!(r.risk_level, RiskLevel::CircuitBreaker);
    assert!(r.auth_frozen);
    assert!(!core.is_authorized());
}

#[test]
fn test_cascade_with_multiple_leases_and_orders() {
    let mut core = GovernanceCore::new();
    core.grant_paper_authorization(None).unwrap();

    // Create 10 leases
    for _ in 0..10 {
        let idx = core.lease.create_draft(serde_json::json!({"s": "BTC"}), "s", None);
        core.lease.register(idx).unwrap();
        core.lease.activate(idx).unwrap();
    }
    assert_eq!(core.lease.get_live().len(), 10);

    // Create 5 OMS orders
    for i in 0..5 {
        core.oms.create_order(&format!("SYM{i}"), "Buy", 0.1, "limit", Some(50000.0), "agent");
    }

    // Circuit break
    let result = core.execute_risk_cascade(
        RiskLevel::CircuitBreaker,
        RiskEvent::IncidentTriggered,
        "flash crash",
    );
    assert!(result.success);
    assert_eq!(result.leases_revoked, 10);
    assert_eq!(core.lease.get_live().len(), 0);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Extreme Execution Tests / 極端執行測試
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_zero_price_fill() {
    let fill = execution::compute_market_fill_price(0.0, true, 1e9);
    assert_eq!(fill, 0.0);
}

#[test]
fn test_very_small_qty_fee() {
    let fee = execution::compute_fee(0.0001, 50000.0, true);
    // 0.0001 * 50000 * 0.00055 = 0.00275
    assert!(fee > 0.0);
    assert!(fee < 0.01);
}

#[test]
fn test_high_volume_low_slippage() {
    let rate = execution::slippage_rate(10_000_000_000.0); // $10B
    assert_eq!(rate, 0.0001); // 1 bps
}

#[test]
fn test_illiquid_market_high_slippage() {
    let rate = execution::slippage_rate(100_000.0); // $100K
    assert_eq!(rate, 0.0030); // 30 bps
}

#[test]
fn test_avg_fill_price_many_partials() {
    let mut filled = 0.0;
    let mut avg = 0.0;
    let prices = [50000.0, 50100.0, 50200.0, 49900.0, 50050.0];
    let qtys = [0.1, 0.2, 0.15, 0.05, 0.5];

    for (&p, &q) in prices.iter().zip(qtys.iter()) {
        avg = execution::compute_avg_fill_price(filled, avg, q, p);
        filled += q;
    }
    // Manual: (0.1*50000 + 0.2*50100 + 0.15*50200 + 0.05*49900 + 0.5*50050) / 1.0
    let expected = (5000.0 + 10020.0 + 7530.0 + 2495.0 + 25025.0) / 1.0;
    assert!((avg - expected).abs() < 0.01);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Extreme Stop Manager Tests / 極端止損測試
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_flash_crash_hard_stop() {
    let config = StopConfig { hard_stop_pct: 5.0, ..StopConfig::default() };
    let pos = PositionState {
        entry_price: 50000.0, best_price: 55000.0, is_long: true, entry_ts_ms: 0,
    };
    // Flash crash to 30000 — well below hard stop
    let trigger = stop_manager::check_stops(&config, &pos, 30000.0, 1000);
    assert!(trigger.is_some());
}

#[test]
fn test_price_exactly_at_stop() {
    let config = StopConfig { hard_stop_pct: 5.0, ..StopConfig::default() };
    let pos = PositionState {
        entry_price: 100.0, best_price: 100.0, is_long: true, entry_ts_ms: 0,
    };
    // Stop at 95.0, price exactly 95.0
    let trigger = stop_manager::check_stops(&config, &pos, 95.0, 0);
    assert!(trigger.is_some());
}

#[test]
fn test_trailing_and_time_stop_interaction() {
    let config = StopConfig {
        hard_stop_pct: 10.0,
        trailing_stop_pct: Some(2.0),
        time_stop_hours: Some(1.0),
        atr_multiplier: Some(2.0),
    };
    let pos = PositionState {
        entry_price: 100.0, best_price: 110.0, is_long: true, entry_ts_ms: 0,
    };
    // Time stop at 1h = 3_600_000ms, price is fine
    let trigger = stop_manager::check_stops(&config, &pos, 108.0, 4_000_000);
    assert!(trigger.is_some());
    // Trailing at 107.8, price 108 → no trailing trigger
    // But time exceeded → time stop triggers
    assert_eq!(trigger.unwrap().stop_type, stop_manager::StopType::Time);
}

#[test]
fn test_atr_position_sizing_extreme_atr() {
    // Very high ATR → very small position
    let qty = stop_manager::compute_atr_position_size(10000.0, 3.0, 10000.0, 2.0, 0.001, 100.0);
    // risk = 300, stop = 20000, qty = 0.015
    assert!((qty - 0.015).abs() < 0.001);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Extreme Portfolio Tests / 極端組合測試
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_portfolio_zero_balance() {
    let config = portfolio::PortfolioConfig::default();
    let result = portfolio::check_portfolio_risk(
        &config, 0.0, &[], 1000.0, "crypto", "Buy", &[],
    );
    assert!(!result.allowed); // zero balance → reserve check fails
}

#[test]
fn test_portfolio_highly_correlated_positions() {
    let config = portfolio::PortfolioConfig::default();
    let returns = (0..20).map(|i| i as f64 * 0.01).collect::<Vec<_>>();
    let mut holdings = Vec::new();
    for i in 0..5 {
        holdings.push(portfolio::Holding {
            symbol: format!("SYM{i}"),
            sector: "crypto".into(),
            side: "Buy".into(),
            notional: 500.0,
            returns: returns.clone(),
        });
    }
    let result = portfolio::check_portfolio_risk(
        &config, 100_000.0, &holdings, 500.0, "crypto", "Buy", &returns,
    );
    assert!(!result.allowed);
    assert!((result.max_correlation - 1.0).abs() < 0.01);
}

#[test]
fn test_portfolio_anti_correlated_passes() {
    let config = portfolio::PortfolioConfig::default();
    let returns_a = vec![0.01, -0.01, 0.02, -0.02, 0.01];
    let returns_b = vec![-0.01, 0.01, -0.02, 0.02, -0.01]; // anti-correlated
    let holdings = vec![portfolio::Holding {
        symbol: "BTC".into(), sector: "crypto".into(), side: "Buy".into(),
        notional: 1000.0, returns: returns_a,
    }];
    let result = portfolio::check_portfolio_risk(
        &config, 100_000.0, &holdings, 1000.0, "crypto", "Buy", &returns_b,
    );
    assert!(result.allowed);
    // Correlation should be negative or at least below threshold
    assert!(result.max_correlation < 0.7);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Extreme Guardian Tests / 極端守護者測試
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_guardian_all_checks_fail() {
    let g = Guardian::default();
    let ctx = PortfolioContext {
        drawdown_pct: 20.0,
        positions: vec![
            ExistingPosition { symbol: "BTCUSDT".into(), side: "Sell".into() },
            ExistingPosition { symbol: "A".into(), side: "Buy".into() },
            ExistingPosition { symbol: "B".into(), side: "Buy".into() },
            ExistingPosition { symbol: "C".into(), side: "Buy".into() },
        ],
    };
    let intent = TradeIntentCheck {
        symbol: "BTCUSDT".into(), side: "Buy".into(), leverage: 15.0, qty: 1.0,
    };
    let r = g.review(&intent, &ctx);
    assert_eq!(r.verdict, Verdict::Rejected);
    assert_eq!(r.risk_score, 1.0); // capped
    assert!(r.reasons.len() >= 3);
}

// ═══════════════════════════════════════════════════════════════════════════════
// Extreme Backtest Tests / 極端回測測試
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn test_backtest_empty_bars() {
    struct NoSig;
    impl SignalGenerator for NoSig {
        fn on_bar(&mut self, _: &Bar) -> Signal { Signal::None }
    }
    let mut engine = backtest::BacktestEngine::new(backtest::BacktestConfig::default());
    let result = engine.run(&[], &mut NoSig);
    assert_eq!(result.trade_count, 0);
    assert_eq!(result.total_pnl, 0.0);
}

#[test]
fn test_backtest_single_bar() {
    struct LongOnce { fired: bool }
    impl SignalGenerator for LongOnce {
        fn on_bar(&mut self, _: &Bar) -> Signal {
            if !self.fired { self.fired = true; Signal::Long } else { Signal::None }
        }
    }
    let mut engine = backtest::BacktestEngine::new(backtest::BacktestConfig::default());
    let bars = vec![Bar { timestamp_ms: 0, open: 100.0, high: 101.0, low: 99.0, close: 100.0, volume: 1000.0 }];
    let result = engine.run(&bars, &mut LongOnce { fired: false });
    // Opens but never closes — equity includes unrealized
    assert!(result.equity_curve.len() == 2);
}

#[test]
fn test_sharpe_negative_returns() {
    let returns = vec![-0.01, -0.02, -0.01, -0.015, -0.005];
    let s = backtest::compute_sharpe(&returns);
    assert!(s < 0.0);
}

#[test]
fn test_max_drawdown_v_shape() {
    let equity = vec![100.0, 90.0, 80.0, 70.0, 80.0, 90.0, 100.0, 110.0];
    let dd = backtest::compute_max_drawdown(&equity);
    // Peak 100, trough 70 → 30%
    assert!((dd - 30.0).abs() < 0.1);
}

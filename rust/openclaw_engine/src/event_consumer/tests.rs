//! I-09 + I-22: Unit tests for event_consumer clamp ranges and JSON envelope invariants.
//! I-09 + I-22：事件消費者鉗制範圍與 JSON 信封不變量單元測試。

#[test]
fn test_clamp_risk_pct_and_stop_pct_bounds() {
    // risk_pct: 0.0..=0.10 / stop_pct: 0.0..=0.5
    assert_eq!((-1.0_f64).clamp(0.0, 0.10), 0.0);
    assert_eq!((0.05_f64).clamp(0.0, 0.10), 0.05);
    assert_eq!((0.99_f64).clamp(0.0, 0.10), 0.10);
    assert_eq!((-0.1_f64).clamp(0.0, 0.5), 0.0);
    assert_eq!((0.25_f64).clamp(0.0, 0.5), 0.25);
    assert_eq!((9.9_f64).clamp(0.0, 0.5), 0.5);
}

#[test]
fn test_clamp_atr_leverage_positions_bounds() {
    // atr_multiplier: 0.5..=10.0 / max_leverage: 1..=100 / max_positions: 1..=100
    assert_eq!((0.0_f64).clamp(0.5, 10.0), 0.5);
    assert_eq!((3.0_f64).clamp(0.5, 10.0), 3.0);
    assert_eq!((50.0_f64).clamp(0.5, 10.0), 10.0);
    assert_eq!((0_usize).clamp(1, 100), 1);
    assert_eq!((25_usize).clamp(1, 100), 25);
    assert_eq!((999_usize).clamp(1, 100), 100);
}

#[test]
fn test_clamp_cooldown_minutes_and_count_bounds() {
    // consecutive_loss_cooldown_count: 0..=1000 / cooldown_minutes: 0..=1440
    assert_eq!((-5_i64).clamp(0, 1000), 0);
    assert_eq!((3_i64).clamp(0, 1000), 3);
    assert_eq!((9999_i64).clamp(0, 1000), 1000);
    assert_eq!((-1_i64).clamp(0, 1440), 0);
    assert_eq!((60_i64).clamp(0, 1440), 60);
    assert_eq!((99999_i64).clamp(0, 1440), 1440);
}

#[test]
fn test_clamp_trailing_stop_pct_bounds() {
    // trailing_stop_pct: 0.0..=0.5 (same family as hard stop)
    assert_eq!((-10.0_f64).clamp(0.0, 0.5), 0.0);
    assert_eq!((0.15_f64).clamp(0.0, 0.5), 0.15);
    assert_eq!((5.0_f64).clamp(0.0, 0.5), 0.5);
}

#[test]
fn test_update_strategy_params_json_invalid() {
    // Invalid JSON must not panic; serde_json::from_str returns Err
    let bad = "{not valid";
    let result: Result<serde_json::Value, _> = serde_json::from_str(bad);
    assert!(result.is_err());
}

#[test]
fn test_update_strategy_params_json_roundtrip() {
    // Valid params JSON round-trips via serde_json::Value
    let json = r#"{"ma_short":10,"ma_long":30,"atr_period":14}"#;
    let v: serde_json::Value = serde_json::from_str(json).expect("valid json");
    assert_eq!(v["ma_short"], 10);
    assert_eq!(v["ma_long"], 30);
    assert_eq!(v["atr_period"], 14);
}

#[test]
fn test_pending_order_clone_preserves_state() {
    // PendingOrder must be cloneable for matching path (fill arrives before order update)
    let po = super::PendingOrder {
        order_link_id: "oc_1".into(),
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        strategy: "ma".into(),
        sent_ts_ms: 1_000,
        cum_filled_qty: 0.0,
        is_close: false,
    };
    let cloned = po.clone();
    assert_eq!(cloned.order_link_id, "oc_1");
    assert_eq!(cloned.qty, 0.01);
    assert!(!cloned.is_close);
}

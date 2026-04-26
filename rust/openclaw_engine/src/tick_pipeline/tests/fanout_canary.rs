// G5-09 sibling: 3E D10/D20 fan-out + canary mode + IndicatorSnapshot mapping.
// Covers Arc<PriceEvent> fan-out delivery, lag-detection guard, canary record
// schema, and the snapshot_to_input bridge.
// G5-09 sibling：3E D10/D20 扇出 + canary 模式 + IndicatorSnapshot 映射。

use super::super::*;

/// 3E D10/D20: Verify Arc<PriceEvent> fan-out delivers to multiple receivers.
/// 3E D10/D20：驗證 Arc<PriceEvent> 扇出可向多個接收端投遞。
#[tokio::test]
async fn test_fanout_arc_price_event() {
    use std::sync::Arc;
    use tokio::sync::mpsc;
    let (tx1, mut rx1) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(16);
    let (tx2, mut rx2) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(16);
    let event = openclaw_types::PriceEvent::new("BTCUSDT".into(), 50000.0, 1000);
    let arc_event = Arc::new(event);
    tx1.try_send(Arc::clone(&arc_event)).unwrap();
    tx2.try_send(arc_event).unwrap();
    let e1 = rx1.recv().await.unwrap();
    let e2 = rx2.recv().await.unwrap();
    assert_eq!(e1.symbol, "BTCUSDT");
    assert_eq!(e2.symbol, "BTCUSDT");
    assert_eq!(e1.last_price, e2.last_price);
}

/// 3E D10: Verify try_send returns Err when channel is full (lag detection).
/// 3E D10：驗證通道滿時 try_send 返回 Err（延遲檢測）。
#[tokio::test]
async fn test_fanout_lag_detection() {
    use std::sync::Arc;
    use tokio::sync::mpsc;
    // Buffer size 1 — second send should fail
    let (tx, _rx) = mpsc::channel::<Arc<openclaw_types::PriceEvent>>(1);
    let e1 = Arc::new(openclaw_types::PriceEvent::new("A".into(), 1.0, 1));
    let e2 = Arc::new(openclaw_types::PriceEvent::new("B".into(), 2.0, 2));
    assert!(tx.try_send(e1).is_ok());
    assert!(tx.try_send(e2).is_err()); // channel full → lag detected
}

#[test]
fn test_canary_mode_off_returns_none() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert!(!pipeline.canary_mode);
    let record = pipeline.on_tick(&super::make_event("BTCUSDT", 50000.0, 1000));
    assert!(record.is_none());
}

#[test]
fn test_canary_mode_on_returns_record() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.canary_mode = true;
    let record = pipeline.on_tick(&super::make_event("BTCUSDT", 50000.0, 1000));
    assert!(record.is_some());
    let r = record.unwrap();
    assert_eq!(r.schema_version, "1.0.0");
    assert_eq!(r.source, "rust_engine");
    assert_eq!(r.tick_number, 1);
    assert_eq!(r.symbol, "BTCUSDT");
    assert_eq!(r.price, 50000.0);
    assert_eq!(r.timestamp_ms, 1000);
}

#[test]
fn test_canary_record_serializable() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.canary_mode = true;
    let record = pipeline
        .on_tick(&super::make_event("BTCUSDT", 50000.0, 1000))
        .unwrap();
    let json = serde_json::to_string(&record).unwrap();
    assert!(json.contains("\"schema_version\":\"1.0.0\""));
    assert!(json.contains("\"source\":\"rust_engine\""));
    // Deserialize back / 反序列化
    let r2: CanaryRecord = serde_json::from_str(&json).unwrap();
    assert_eq!(r2.tick_number, record.tick_number);
}

#[test]
fn test_snapshot_to_input() {
    let snap = IndicatorSnapshot {
        sma_20: Some(50000.0),
        sma_50: None,
        ema_12: Some(50100.0),
        ema_26: None,
        rsi_14: Some(55.0),
        macd: None,
        bollinger: None,
        atr_14: None,
        atr_5: None,
        stochastic: None,
        kama: None,
        adx: None,
        hurst: None,
        ewma_vol: None,
        volume_ratio: Some(1.2),
        donchian: None,
    };
    let input = snapshot_to_input(&snap);
    assert_eq!(input.sma, Some(50000.0));
    assert_eq!(input.rsi, Some(55.0));
    assert_eq!(input.volume_ratio, Some(1.2));
}

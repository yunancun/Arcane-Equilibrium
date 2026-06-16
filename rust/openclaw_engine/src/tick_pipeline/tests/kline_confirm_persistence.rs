// R1（2026-06-16）：WS-confirmed-candle 直寫持久化路徑回歸測試。
//
// 被測意圖（step_1_2_klines_indicators.rs::persist_confirmed_kline + on_tick 早退）：
//   - PriceEventKind::KlineConfirm 事件 = Bybit 推送的權威整根 OHLCV+turnover，
//     必須以**完整真實 OHLC**（非退化 open≈close）發 MarketDataMsg::KlineClose
//     到 market_data_tx，timeframe 由 interval 正確映射（240→4h 等）。
//   - tick-synth aggregator（kline_manager.on_tick）**不再對 market writer 發
//     KlineClose**：非 KlineConfirm 的 Trade/Ticker tick 即使觸發 bar 收盤，也
//     不應有任何 MarketDataMsg 流向 channel（DB 真值單一源 = WS confirmed）。
//   - KlineConfirm 早退：不驅動信號/風控（on_tick 回 None，不參與下游 step）。
//
// 這些測試走真實 `TickPipeline::on_tick` 路徑（非 mock 業務邏輯），透過真正接上
// 的 mpsc channel 讀回發出的 MarketDataMsg 驗證 OHLCV 真值。

use super::super::*;
use crate::database::MarketDataMsg;

const BASE_TS: u64 = 1_704_067_200_000; // 2024-01-01 00:00:00 UTC，對齊分鐘邊界

/// 構造一個 KlineConfirm 事件，攜帶完整權威 OHLCV+turnover + interval + start/end。
fn kline_confirm(
    symbol: &str,
    interval: &str,
    open: f64,
    high: f64,
    low: f64,
    close: f64,
    volume: f64,
    turnover: f64,
    start_ms: u64,
    end_ms: u64,
) -> PriceEvent {
    let mut e = PriceEvent::new(symbol.to_string(), close, start_ms);
    e.event_kind = Some(PriceEventKind::KlineConfirm);
    e.volume_24h = volume; // close 走 last_price，volume 走 volume_24h（與 parser 一致）
    e.kline_open = Some(open);
    e.kline_high = Some(high);
    e.kline_low = Some(low);
    e.kline_turnover = Some(turnover);
    e.kline_interval = Some(interval.to_string());
    e.kline_start_ms = Some(start_ms);
    e.kline_close_ms = Some(end_ms);
    e
}

/// KlineConfirm → 發出帶**完整真實 OHLCV** 的 KlineClose，timeframe 正確映射。
#[tokio::test]
async fn test_kline_confirm_persists_full_ohlcv() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<MarketDataMsg>(8);
    p.set_market_data_channel(tx);

    // 真實整根：open=64500, high=65100, low=64400, close=65000（range=700，非退化）。
    let ev = kline_confirm(
        "BTCUSDT",
        "1",
        64_500.0,
        65_100.0,
        64_400.0,
        65_000.0,
        100.5,
        6_512_345.0,
        BASE_TS,
        BASE_TS + 60_000,
    );
    let out = p.on_tick(&ev);
    // KlineConfirm 早退：不產生信號/CanaryRecord。
    assert!(out.is_none(), "KlineConfirm must early-return (not drive signals)");

    let msg = rx.try_recv().expect("expected a KlineClose message");
    match msg {
        MarketDataMsg::KlineClose {
            symbol,
            timeframe,
            bar,
        } => {
            assert_eq!(symbol, "BTCUSDT");
            assert_eq!(timeframe, "1m", "interval 1 → timeframe 1m");
            // 權威 OHLC 全保留（這正是根因修復：不再 open≈close、range≈0）。
            assert!((bar.open - 64_500.0).abs() < 1e-6);
            assert!((bar.high - 65_100.0).abs() < 1e-6);
            assert!((bar.low - 64_400.0).abs() < 1e-6);
            assert!((bar.close - 65_000.0).abs() < 1e-6);
            assert!((bar.volume - 100.5).abs() < 1e-6);
            assert!((bar.turnover - 6_512_345.0).abs() < 1e-3);
            // range 非退化（修復前 tick-synth 會給 ~0）。
            assert!(bar.high - bar.low > 600.0, "wick range must be real, not dead");
            assert_eq!(bar.open_time_ms, BASE_TS);
            assert_eq!(bar.close_time_ms, BASE_TS + 60_000);
            assert!(bar.is_closed);
        }
        other => panic!("expected KlineClose, got {other:?}"),
    }
    // 只應有一筆（單一 confirmed candle）。
    assert!(rx.try_recv().is_err(), "exactly one KlineClose expected");
}

/// interval 240 → timeframe 4h（R1 新覆蓋的 4h）。
#[tokio::test]
async fn test_kline_confirm_240_maps_to_4h() {
    let mut p = TickPipeline::new(&["ETHUSDT"]);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<MarketDataMsg>(8);
    p.set_market_data_channel(tx);

    let ev = kline_confirm(
        "ETHUSDT",
        "240",
        100.0,
        115.0,
        95.0,
        110.0,
        1.0,
        110.0,
        BASE_TS,
        BASE_TS + 14_400_000,
    );
    p.on_tick(&ev);

    let msg = rx.try_recv().expect("expected a KlineClose message");
    if let MarketDataMsg::KlineClose { timeframe, bar, .. } = msg {
        assert_eq!(timeframe, "4h", "interval 240 → timeframe 4h");
        assert!((bar.high - 115.0).abs() < 1e-6);
        assert!((bar.low - 95.0).abs() < 1e-6);
    } else {
        panic!("expected KlineClose");
    }
}

/// 未知 interval → fail-closed，不發任何 KlineClose。
#[tokio::test]
async fn test_kline_confirm_unknown_interval_fail_closed() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<MarketDataMsg>(8);
    p.set_market_data_channel(tx);

    let mut ev = kline_confirm(
        "BTCUSDT",
        "999", // 無對應 timeframe
        1.0,
        2.0,
        0.5,
        1.5,
        1.0,
        1.5,
        BASE_TS,
        BASE_TS + 60_000,
    );
    ev.kline_interval = Some("999".to_string());
    p.on_tick(&ev);

    assert!(
        rx.try_recv().is_err(),
        "unknown interval must fail-closed (no KlineClose emitted)"
    );
}

/// R2 鐵證：tick-synth 路徑（Trade/Ticker tick）即使觸發 bar 收盤，也**不再**
/// 對 market writer 發 KlineClose。DB 持久化單一源 = WS confirmed。
#[tokio::test]
async fn test_tick_synth_no_longer_emits_kline_close() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<MarketDataMsg>(8);
    p.set_market_data_channel(tx);

    // 兩筆 Trade 跨分鐘 → tick-synth aggregator 會收盤首根 1m bar（記憶體 buffer 內）。
    let mut t1 = PriceEvent::new("BTCUSDT".into(), 50_000.0, BASE_TS + 1_000);
    t1.event_kind = Some(PriceEventKind::Trade);
    t1.volume_24h = 0.5;
    p.on_tick(&t1);

    let mut t2 = PriceEvent::new("BTCUSDT".into(), 50_100.0, BASE_TS + 61_000);
    t2.event_kind = Some(PriceEventKind::Trade);
    t2.volume_24h = 0.1;
    p.on_tick(&t2);

    // 記憶體 buffer 仍有收盤 bar（R2：indicator 源不變）。
    let buffered = p
        .kline_manager
        .get_buffer("BTCUSDT", "1m")
        .map(|b| b.len())
        .unwrap_or(0);
    assert!(buffered >= 1, "tick-synth aggregator still feeds in-memory buffer (R2)");

    // 但 market writer channel 必須空（tick-synth 不再落盤）。
    assert!(
        rx.try_recv().is_err(),
        "tick-synth must NOT emit KlineClose to DB writer anymore (single-source = WS confirmed)"
    );
}

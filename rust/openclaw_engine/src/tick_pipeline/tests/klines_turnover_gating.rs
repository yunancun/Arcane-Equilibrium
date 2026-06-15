// QUOTE-VOL-FIX（2026-06-15）：step_1_2 K 線聚合的 per-event-kind 量/額 gating 回歸測試。
//
// 被測意圖（step_1_2_klines_indicators.rs）：
//   只有 PriceEventKind::Trade 事件貢獻真實 base 量(volume) 與 price×qty(turnover)；
//   其餘事件（Ticker/Orderbook/None 等）對 volume/turnover 貢獻 0，但仍傳價驅動 OHLC。
//   修復前 bug：turnover 硬編碼 0.0（intraday turnover 列 100% 為 0），且非 Trade 事件
//   把 ticker 的 24h 累計量 volume_24h 逐 tick 累加污染 per-bar 量。
//
// 這些測試走真實 `TickPipeline::on_tick` → `on_tick_step_1_2_klines_indicators` 路徑
// （非 mock 業務邏輯），透過 `kline_manager` 公開欄位讀回已關閉 K 線驗證。
// 不依賴 DB writer channel（market_data_tx 未掛接時聚合仍照常進行）。

use super::super::*;

/// 構造一個帶 event_kind + base-qty 的 Trade 事件（volume_24h 欄位在 Trade 事件
/// 語義下承載 base 數量，鏡像於 trade_qty——對齊 step_1_2 的取值約定）。
fn trade_event(symbol: &str, price: f64, qty: f64, ts: u64) -> PriceEvent {
    let mut e = PriceEvent::new(symbol.to_string(), price, ts);
    e.event_kind = Some(PriceEventKind::Trade);
    e.volume_24h = qty; // publicTrade `v`（base 數量）
    e.trade_qty = Some(qty);
    e
}

/// 構造一個 Ticker 事件，volume_24h 故意塞入「24h 累計量」這種會污染 per-bar 的值。
fn ticker_event(symbol: &str, price: f64, vol_24h: f64, ts: u64) -> PriceEvent {
    let mut e = PriceEvent::new(symbol.to_string(), price, ts);
    e.event_kind = Some(PriceEventKind::Ticker);
    e.volume_24h = vol_24h; // 24h 累計量——非 Trade 不得進 per-bar volume/turnover
    e
}

/// 讀回指定 symbol+timeframe 最近一根已關閉 K 線（無則 None）。
fn last_closed_bar(
    pipeline: &TickPipeline,
    symbol: &str,
    tf: &str,
) -> Option<openclaw_core::klines::KlineBar> {
    pipeline
        .kline_manager
        .get_buffer(symbol, tf)
        .and_then(|b| b.latest_cloned(1).into_iter().next())
}

const BASE_TS: u64 = 1_704_067_200_000; // 2024-01-01 00:00:00 UTC，對齊分鐘邊界

/// 單個 Trade 事件 → 該 tick 進 1m bar 後，turnover == price×qty 且 volume == qty。
/// 用「下一分鐘再來一筆 Trade 觸發收盤」讀回首根已關閉 1m bar 的累積量/額。
#[test]
fn test_trade_event_contributes_volume_and_turnover() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);

    // 第一分鐘：單筆 Trade，price=50_000, qty=0.5 → turnover 應為 25_000.0。
    p.on_tick(&trade_event("BTCUSDT", 50_000.0, 0.5, BASE_TS + 1_000));
    // 下一分鐘的 Trade 觸發前一根 1m bar 收盤。
    p.on_tick(&trade_event("BTCUSDT", 50_100.0, 0.1, BASE_TS + 61_000));

    let bar = last_closed_bar(&p, "BTCUSDT", "1m").expect("expected one closed 1m bar");
    assert!(bar.is_closed, "bar should be closed");
    // volume == 該分鐘內 Trade 的 base 量（單筆 0.5）
    assert!(
        (bar.volume - 0.5).abs() < 1e-9,
        "Trade volume mismatch: got {}, expected 0.5",
        bar.volume
    );
    // turnover == price × qty = 50_000 × 0.5 = 25_000
    assert!(
        (bar.turnover - 25_000.0).abs() < 1e-6,
        "Trade turnover mismatch: got {}, expected 25000.0 (=price*qty)",
        bar.turnover
    );
    // OHLC 由價驅動仍正確
    assert!((bar.open - 50_000.0).abs() < 1e-9);
    assert!((bar.close - 50_000.0).abs() < 1e-9);
}

/// 非 Trade 事件（Ticker）→ 不貢獻 volume/turnover（保持 0），但價仍驅動 OHLC。
/// 全分鐘只餵 Ticker（volume_24h 帶大數），下一分鐘 Ticker 觸發收盤。
#[test]
fn test_ticker_event_does_not_contribute_volume_or_turnover() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);

    // 第一分鐘：兩筆 Ticker，volume_24h=1_000_000（24h 累計量，絕不能進 per-bar）。
    p.on_tick(&ticker_event("BTCUSDT", 50_000.0, 1_000_000.0, BASE_TS + 1_000));
    p.on_tick(&ticker_event("BTCUSDT", 50_200.0, 1_000_000.0, BASE_TS + 30_000));
    // 下一分鐘 Ticker 觸發前一根 1m bar 收盤。
    p.on_tick(&ticker_event("BTCUSDT", 50_100.0, 1_000_000.0, BASE_TS + 61_000));

    let bar = last_closed_bar(&p, "BTCUSDT", "1m").expect("expected one closed 1m bar");
    assert!(bar.is_closed);
    // 非 Trade 事件 volume/turnover 必須為 0（修復前會被 24h 量污染 / turnover 硬編碼 0）
    assert!(
        bar.volume.abs() < 1e-12,
        "Ticker must NOT contribute volume; got {} (24h-vol contamination bug?)",
        bar.volume
    );
    assert!(
        bar.turnover.abs() < 1e-12,
        "Ticker must NOT contribute turnover; got {}",
        bar.turnover
    );
    // 但價仍驅動 OHLC：open=首筆、high=50_200、close=末筆同分鐘價(50_200)
    assert!((bar.open - 50_000.0).abs() < 1e-9, "OHLC open should still track price");
    assert!((bar.high - 50_200.0).abs() < 1e-9, "OHLC high should still track price");
}

/// 混合：同一分鐘內 Trade + Ticker → 只有 Trade 部分計入 volume/turnover，
/// Ticker 不污染。多筆 Trade 累加（驗 step→aggregator Kahan turnover 求和正確）。
#[test]
fn test_mixed_events_only_trades_accumulate() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);

    // 第一分鐘：Trade(0.2 @ 100) + Ticker(24h=999_999) + Trade(0.3 @ 110)。
    // 預期 volume = 0.2 + 0.3 = 0.5；turnover = 100*0.2 + 110*0.3 = 20 + 33 = 53。
    p.on_tick(&trade_event("BTCUSDT", 100.0, 0.2, BASE_TS + 1_000));
    p.on_tick(&ticker_event("BTCUSDT", 105.0, 999_999.0, BASE_TS + 2_000));
    p.on_tick(&trade_event("BTCUSDT", 110.0, 0.3, BASE_TS + 3_000));
    // 下一分鐘 tick 觸發收盤。
    p.on_tick(&trade_event("BTCUSDT", 108.0, 0.1, BASE_TS + 61_000));

    let bar = last_closed_bar(&p, "BTCUSDT", "1m").expect("expected one closed 1m bar");
    assert!(bar.is_closed);
    assert!(
        (bar.volume - 0.5).abs() < 1e-9,
        "mixed volume mismatch: got {}, expected 0.5 (only Trades)",
        bar.volume
    );
    assert!(
        (bar.turnover - 53.0).abs() < 1e-9,
        "mixed turnover mismatch: got {}, expected 53.0 (=100*0.2+110*0.3, Ticker excluded)",
        bar.turnover
    );
    // tick_count 應計入所有 tick（Trade + Ticker 都驅動 OHLC/週期滾動）= 3
    assert_eq!(bar.tick_count, 3, "all events drive OHLC/period roll");
    assert!((bar.high - 110.0).abs() < 1e-9);
}

/// event_kind = None（舊式無類型事件）→ 視為非 Trade，不貢獻 volume/turnover。
/// make_event 工廠產的事件 event_kind 即為 None。
#[test]
fn test_untyped_event_does_not_contribute() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);

    let mut e1 = super::make_event("BTCUSDT", 200.0, BASE_TS + 1_000);
    e1.volume_24h = 500_000.0; // 即便帶量也不該進 per-bar
    assert!(e1.event_kind.is_none(), "make_event should produce untyped event");
    p.on_tick(&e1);

    let mut e2 = super::make_event("BTCUSDT", 201.0, BASE_TS + 61_000);
    e2.volume_24h = 500_000.0;
    p.on_tick(&e2);

    let bar = last_closed_bar(&p, "BTCUSDT", "1m").expect("expected one closed 1m bar");
    assert!(bar.volume.abs() < 1e-12, "untyped event must NOT contribute volume; got {}", bar.volume);
    assert!(bar.turnover.abs() < 1e-12, "untyped event must NOT contribute turnover; got {}", bar.turnover);
}

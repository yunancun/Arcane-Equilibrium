// G5-09 sibling: PNL-FIX-1 per-symbol latest_price + entry-price fallback
// + P1-16 HaltSession price-corruption regression. These tests guard the
// 2026-04-12 paper anomaly fix (no cross-symbol price contamination on close)
// and the 2026-04-18 P1-16 follow-up (halt path can't borrow triggering tick).
// G5-09 sibling：PNL-FIX-1 跨 symbol 價格隔離 + P1-16 HaltSession 修復。

use super::super::*;

/// PNL-FIX-1 regression: each position must close at its OWN symbol's
/// latest_price, not the price of whichever tick happened to fire the
/// close path. The 2026-04-12 paper anomaly produced ~$497K fake PnL
/// from 8 fast_track fills because every close used `event.last_price`
/// (the triggering tick's price) for ALL symbols regardless of their
/// real prices (FFUSDT closed at $2301 instead of ~$0.50, etc.).
/// PNL-FIX-1 回歸：每個倉位平倉時必須使用該交易對自己的 latest_price，
/// 禁止借用觸發 tick 的價格。鎖定 2026-04-12 paper 異常的修復。
#[test]
fn test_close_position_at_symbol_market_uses_per_symbol_price() {
    let mut pipeline = TickPipeline::with_kind(
        &["BTCUSDT", "ETHUSDT", "FFUSDT", "DOGEUSDT"],
        10_000.0,
        PipelineKind::Paper,
    );
    // Open four long positions at very different real-world price scales.
    // 在四個價格相差幾個數量級的交易對上各開一個多倉。
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("ETHUSDT", true, 0.10, 3_000.0, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("FFUSDT", true, 100.0, 0.50, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("DOGEUSDT", true, 1_000.0, 0.20, 0.0, 1_000, "test");

    // Set per-symbol latest prices — each at a small +1% gain over entry.
    // The triggering tick (in production) would carry only ONE of these prices,
    // but the close MUST use each symbol's own latest_price.
    // 為每個交易對設定獨立的最新價（各 +1%）。觸發 tick 只會帶其中一個價格，
    // 但平倉必須各自使用自己的 latest_price。
    pipeline.paper_state.set_latest_price("BTCUSDT", 50_500.0);
    pipeline.paper_state.set_latest_price("ETHUSDT", 3_030.0);
    pipeline.paper_state.set_latest_price("FFUSDT", 0.505);
    pipeline.paper_state.set_latest_price("DOGEUSDT", 0.202);

    // Close each position via the helper. Returned close_price MUST equal
    // that symbol's latest_price, NEVER another symbol's.
    // 通過 helper 平倉，返回的 close_price 必須等於該交易對的 latest_price。
    let (_il, _q, btc_px, btc_pnl) = pipeline
        .close_position_at_symbol_market("BTCUSDT", 2_000)
        .unwrap();
    let (_il, _q, eth_px, eth_pnl) = pipeline
        .close_position_at_symbol_market("ETHUSDT", 2_000)
        .unwrap();
    let (_il, _q, ff_px, ff_pnl) = pipeline
        .close_position_at_symbol_market("FFUSDT", 2_000)
        .unwrap();
    let (_il, _q, doge_px, doge_pnl) = pipeline
        .close_position_at_symbol_market("DOGEUSDT", 2_000)
        .unwrap();

    // Each close uses the right symbol's price. (The bug closed
    // FFUSDT at $50,500 — BTCUSDT's price — producing -$5,049,950 PnL.)
    // 每個平倉都用了正確的價格。修復前 FFUSDT 會被以 BTC 的 50500 平倉。
    assert!(
        (btc_px - 50_500.0).abs() < 1e-9,
        "BTC close at wrong price: {btc_px}"
    );
    assert!(
        (eth_px - 3_030.0).abs() < 1e-9,
        "ETH close at wrong price: {eth_px}"
    );
    assert!(
        (ff_px - 0.505).abs() < 1e-9,
        "FF close at wrong price: {ff_px}"
    );
    assert!(
        (doge_px - 0.202).abs() < 1e-9,
        "DOGE close at wrong price: {doge_px}"
    );

    // PnL = (close_price - entry_price) * qty for longs.
    // Each position should show a small +1% gain in proportion to notional.
    // PnL = (close - entry) * qty。每個都應該是小幅正收益。
    assert!((btc_pnl - 5.0).abs() < 1e-9, "BTC PnL: {btc_pnl}"); // (50500-50000)*0.01
    assert!((eth_pnl - 3.0).abs() < 1e-9, "ETH PnL: {eth_pnl}"); // (3030-3000)*0.1
    assert!((ff_pnl - 0.5).abs() < 1e-9, "FF PnL: {ff_pnl}"); // (0.505-0.5)*100
    assert!((doge_pnl - 2.0).abs() < 1e-9, "DOGE PnL: {doge_pnl}"); // (0.202-0.2)*1000

    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "all positions should be closed"
    );
}

/// PNL-FIX-1 fallback: when no latest_price is recorded for a symbol,
/// the helper must fall back to the position's entry_price (yielding zero
/// PnL), NEVER to the triggering tick's price.
/// PNL-FIX-1 退路：無 latest_price 時必須回退到 entry_price（pnl=0），
/// 絕不能借用觸發 tick 的價格。
#[test]
fn test_close_position_at_symbol_market_fallback_to_entry_when_no_latest_price() {
    let mut pipeline = TickPipeline::with_kind(&["FFUSDT"], 10_000.0, PipelineKind::Paper);
    // Open position WITHOUT setting latest_price.
    // 開倉但不設定 latest_price。
    pipeline
        .paper_state
        .apply_fill("FFUSDT", true, 100.0, 0.50, 0.0, 1_000, "test");
    // apply_fill seeds latest_prices via its internal book-keeping; clear it
    // explicitly to simulate a position whose price has not been observed yet.
    // apply_fill 內部會種入 latest_price，這裡強制清掉模擬「未觀測過價格」的情境。
    pipeline.paper_state.set_latest_price("FFUSDT", f64::NAN);

    let (_il, _q, close_px, pnl) = pipeline
        .close_position_at_symbol_market("FFUSDT", 2_000)
        .unwrap();

    // Falls back to entry_price (0.50), producing zero PnL — the safe choice.
    // 回退到入場價，pnl 為零。
    assert!(
        (close_px - 0.50).abs() < 1e-9,
        "fallback should be entry price, got {close_px}"
    );
    assert!(
        pnl.abs() < 1e-9,
        "fallback close should produce zero PnL, got {pnl}"
    );
}

/// P1-16 regression: when `RiskAction::HaltSession` fires (e.g. session
/// drawdown breach) the close-fill loop must use **each position's own**
/// latest_price — with fallback to that symbol's entry_price — NEVER the
/// triggering tick's `event.last_price`. The pre-fix code open-coded
/// `latest_prices.get(sym).unwrap_or(event.last_price)`, which stamped the
/// one triggering symbol's tick price across every other symbol's close fill
/// and produced `-17,617,373 bps` realized edge rows in
/// `learning.decision_features` (ETHUSDT's $2357.94 smeared onto DOT/HIGH/IP).
/// Fix switches halt_session to the safe helper `close_position_at_symbol_market`.
///
/// P1-16 回歸：HaltSession 平倉迴圈必須用各交易對自己的 latest_price（無則
/// 回退自己的 entry_price），**絕不能**用觸發 tick 的 `event.last_price`。
/// 修復前 halt 路徑 open-code `latest_prices.get(sym).unwrap_or(event.last_price)`，
/// 會把觸發交易對的價蓋到所有其他交易對的平倉 fill，正是 decision_features 中
/// ETHUSDT $2357.94 污染 DOT/HIGH/IP 並產生 -17M bps 髒列的根因。
#[test]
fn test_halt_session_uses_per_symbol_price_not_triggering_tick() {
    use crate::database::TradingMsg;
    let mut pipeline = TickPipeline::with_kind(
        &["BTCUSDT", "ETHUSDT", "DOGEUSDT"],
        10_000.0,
        PipelineKind::Paper,
    );
    // 固定 taker fee 為 0 以隔離 price 檢驗（close fee = qty × price × 0 = 0）。
    pipeline.intent_processor.set_fee_rate(0.0);

    let (tx, mut rx) = tokio::sync::mpsc::channel::<TradingMsg>(32);
    pipeline.set_trading_channel(tx);

    // 開三個 long 倉，各自獨立的 entry price（scale 跨 5 個數量級）。
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("ETHUSDT", true, 0.10, 3_000.0, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("DOGEUSDT", true, 1_000.0, 0.20, 0.0, 1_000, "test");

    // apply_fill 會把 latest_prices 種到 entry price；非觸發交易對強制清為 NAN
    // 以模擬 P1-16 實況：orphan-adopted 倉位在首個 tick 前就被 halt_session
    // 掃進來，那時 paper_state.latest_prices 裡沒有它們的項。
    pipeline.paper_state.set_latest_price("ETHUSDT", f64::NAN);
    pipeline.paper_state.set_latest_price("DOGEUSDT", f64::NAN);

    // 把餘額從 10_000 扣到 7_500 → drawdown = 25%（超過 default 15%）。
    // 觸發 RiskAction::HaltSession(SESSION DRAWDOWN)。
    pipeline.paper_state.charge_fee(2_500.0);
    assert!(
        pipeline.paper_state.drawdown_pct() >= 20.0,
        "drawdown must exceed default 15% cap; got {:.2}%",
        pipeline.paper_state.drawdown_pct()
    );

    // 觸發 tick 只針對 BTCUSDT，價 50_500。ETH/DOGE 不會收到自己的 tick，
    // 所以在 halt loop 裡只能靠 per-symbol fallback（entry price）存活。
    let _ = pipeline.on_tick(&super::make_event("BTCUSDT", 50_500.0, 2_000));

    // 消費所有 Fill 訊息，按 symbol 聚合每筆 close 的 price。
    let mut close_prices: std::collections::HashMap<String, f64> = std::collections::HashMap::new();
    while let Ok(msg) = rx.try_recv() {
        if let TradingMsg::Fill {
            symbol,
            price,
            strategy_name,
            ..
        } = msg
        {
            if strategy_name == "risk_close:halt_session" {
                close_prices.insert(symbol, price);
            }
        }
    }
    assert_eq!(
        close_prices.len(),
        3,
        "expected 3 halt_session close fills, got {}: {:?}",
        close_prices.len(),
        close_prices
    );

    // BTC 有自己的 latest_price 50_500（經 on_tick 寫入）→ close @ 50_500.
    // BTC 有自己的 latest_price → close 使用 50_500.
    let btc = close_prices.get("BTCUSDT").copied().expect("BTC fill");
    assert!(
        (btc - 50_500.0).abs() < 1e-9,
        "BTCUSDT close should use its own tick price 50_500, got {btc}"
    );

    // ETH/DOGE 的 latest_price 是 NAN → 回退到 entry_price。
    // 修復前兩者都會變 50_500（BTC 的 tick），污染 realized edge。
    let eth = close_prices.get("ETHUSDT").copied().expect("ETH fill");
    assert!(
        (eth - 3_000.0).abs() < 1e-9,
        "ETHUSDT close MUST fall back to entry 3000, NOT borrow BTC's 50_500; got {eth}"
    );
    let doge = close_prices.get("DOGEUSDT").copied().expect("DOGE fill");
    assert!(
        (doge - 0.20).abs() < 1e-9,
        "DOGEUSDT close MUST fall back to entry 0.20, NOT borrow BTC's 50_500; got {doge}"
    );

    // 所有倉位都已關掉，session 已標記為 halted。
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "all positions should be closed after halt_session"
    );
    assert!(
        pipeline.session_halted,
        "session_halted flag must be set after HaltSession fires"
    );
}

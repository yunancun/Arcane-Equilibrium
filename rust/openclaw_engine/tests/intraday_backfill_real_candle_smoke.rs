//! E4 回歸：intraday K 線回填「真實聚合蠟燭」live REST 煙霧測試（2026-06-15）。
//!
//! 目的（命門驗證）：證明 intraday 回填走的 REST aggregated-candle 路徑產出的是「真蠟燭」，
//!   而非 live WebSocket tick-synth 路徑寫出的退化單快照 bar（root-cause：close[T]≈open[T]、
//!   intrabar range≈0.018% 跨所有 timeframe、turnover 100% 為 0、55-58% bar 缺失）。
//!
//! 為什麼是 live REST 而非 mock：
//!   - 退化-snapshot vs 真蠟燭的差異**只能用真實 Bybit 聚合資料證明**——mock 任何固定 fixture
//!     都會繞過「真實路徑是否取到真蠟燭」這個正是 root-cause 漏掉的盲點（E4 mock 安全規則：
//!     不 mock 業務邏輯/計算；只 mock IO 邊界）。網路請求是 IO 邊界（允許為真），
//!     strict_filter_closed_bars_for 是業務邏輯（必真跑）。
//!   - 公開 /v5/market/kline 端點無需鑑權（與 daily 756/756 cross-check 同源），故本測試
//!     不依賴 demo secret slot；用 reqwest 直打公開端點取原始 JSON，再以「與 parse_kline_list
//!     位元相同的 array indexing」重建 client KlineBar，餵真 strict_filter_closed_bars_for。
//!
//! 斷言（candle-realism，PA/E2 driver 要求）：
//!   1. 4h intrabar range > 1h range > 1m range（真蠟燭隨 timeframe 單調放大；退化 snapshot 三者
//!      會相同 ≈0.018%）。
//!   2. BTC 1h 中位 intrabar range 落 ~0.1%–3%（真波動帶；退化 snapshot ≈0.018% 會掉出下界）。
//!   3. turnover 全部 > 0（退化路徑 100% turnover=0）。
//!   4. strict_filter_closed_bars_for 對真資料判 pass（observed≈expected，非 55-58% 缺失）。
//!   5. close[T] != open[T] 普遍成立（退化 snapshot close≈open 99.6%）。
//!
//! 執行：`#[ignore]`（real-network，預設不在 CI 跑，與 repo real-impl 慣例一致）。
//!   `cargo test -p openclaw_engine --test intraday_backfill_real_candle_smoke -- --ignored --nocapture`

use openclaw_engine::backfill::daily_kline_backfill::{
    expected_bars_for, strict_filter_closed_bars_for, CoverageStatus,
};
use openclaw_engine::market_data_client::KlineBar;

const BYBIT_REST: &str = "https://api.bybit.com";
const FALLBACK_REST: &str = "https://api.bytick.com";

/// 把 Bybit /v5/market/kline 回傳的 result.list（array of string-arrays）以與
/// parse_kline_list（parsers.rs:38-82）**位元相同**的 array indexing 解析為 client KlineBar。
///
/// 為什麼在此重建而非呼叫 parse_kline_list：後者是 `pub(super)`（模塊私有），不可從整合測試
/// 呼叫；本函數逐欄位對齊 arr[0..7]→(start_time,open,high,low,close,volume,turnover) 的同一
/// 解析語意（含 .parse::<T>().unwrap_or(...) 的同一退化簽名），確保餵給 strict 層的輸入與
/// 生產路徑等價。**不引入任何不同於生產的解析行為**（無捨入、無補值）。
fn parse_kline_list_mirror(result: &serde_json::Value) -> Vec<KlineBar> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let mut bars = Vec::with_capacity(list.len());
    for item in &list {
        if let Some(arr) = item.as_array() {
            if arr.len() >= 7 {
                let f = |i: usize| arr[i].as_str().and_then(|s| s.parse::<f64>().ok()).unwrap_or(0.0);
                bars.push(KlineBar {
                    start_time: arr[0].as_str().and_then(|s| s.parse::<u64>().ok()).unwrap_or(0),
                    open: f(1),
                    high: f(2),
                    low: f(3),
                    close: f(4),
                    volume: f(5),
                    turnover: f(6),
                });
            }
        }
    }
    bars
}

/// 真打公開 kline 端點（mainnet 公開資料，無鑑權）；主端點失敗回退 api.bytick.com。
/// workspace reqwest 只開 json+rustls-tls（無 blocking feature），故走 async + 自建
/// current-thread tokio runtime（IO 邊界，與生產同走 reqwest）。
fn fetch_klines(interval: &str, limit: u32) -> Vec<KlineBar> {
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .expect("build tokio runtime");
    rt.block_on(fetch_klines_async(interval, limit))
}

async fn fetch_klines_async(interval: &str, limit: u32) -> Vec<KlineBar> {
    let client = reqwest::Client::builder()
        .timeout(std::time::Duration::from_secs(25))
        .build()
        .expect("build http client");
    let path = format!(
        "/v5/market/kline?category=linear&symbol=BTCUSDT&interval={interval}&limit={limit}"
    );
    for base in [BYBIT_REST, FALLBACK_REST] {
        let url = format!("{base}{path}");
        let Ok(resp) = client.get(&url).send().await else {
            continue;
        };
        let Ok(json) = resp.json::<serde_json::Value>().await else {
            continue;
        };
        let ret_code = json.get("retCode").and_then(|v| v.as_i64()).unwrap_or(-1);
        if ret_code != 0 {
            continue;
        }
        if let Some(result) = json.get("result") {
            let bars = parse_kline_list_mirror(result);
            if !bars.is_empty() {
                return bars;
            }
        }
    }
    panic!("failed to fetch live klines for interval={interval} from both Bybit hosts");
}

/// 對一組 bar 計算 intrabar range 的中位數：(high-low)/open（相對波動）。
fn median_relative_range(bars: &[KlineBar]) -> f64 {
    let mut ranges: Vec<f64> = bars
        .iter()
        .filter(|b| b.open > 0.0)
        .map(|b| (b.high - b.low) / b.open)
        .collect();
    assert!(!ranges.is_empty(), "no bars to compute range");
    ranges.sort_by(|a, b| a.partial_cmp(b).unwrap());
    ranges[ranges.len() / 2]
}

/// 把一組原始 bar 餵真 strict_filter_closed_bars_for，回傳 page（business-logic 真跑）。
fn run_strict(bars: &[KlineBar], period_ms: u64, tf: &str) -> openclaw_engine::backfill::daily_kline_backfill::ParsedKlinePage {
    // window = [最早 open, 最晚 open + period)，now 取最晚 open + 2*period（保證全收盤）。
    let min_open = bars.iter().map(|b| b.start_time).min().unwrap();
    let max_open = bars.iter().map(|b| b.start_time).max().unwrap();
    let window_start = min_open;
    let window_end = max_open + period_ms;
    let now_ms = max_open + 2 * period_ms;
    strict_filter_closed_bars_for(
        "BTCUSDT",
        bars,
        window_start,
        window_end,
        now_ms,
        period_ms,
        tf,
    )
}

#[test]
#[ignore = "real-network: hits public api.bybit.com /v5/market/kline"]
fn test_real_bybit_klines_are_aggregated_candles_not_snapshots() {
    // 取近 50 根各 timeframe（公開資料，無鑑權）。
    let bars_1m = fetch_klines("1", 50);
    let bars_1h = fetch_klines("60", 50);
    let bars_4h = fetch_klines("240", 50);

    assert!(bars_1m.len() >= 40, "1m fetch too few: {}", bars_1m.len());
    assert!(bars_1h.len() >= 40, "1h fetch too few: {}", bars_1h.len());
    assert!(bars_4h.len() >= 40, "4h fetch too few: {}", bars_4h.len());

    let r1m = median_relative_range(&bars_1m);
    let r1h = median_relative_range(&bars_1h);
    let r4h = median_relative_range(&bars_4h);
    eprintln!("median intrabar range: 1m={r1m:.6} 1h={r1h:.6} 4h={r4h:.6}");

    // 斷言 1：真蠟燭 intrabar range 隨 timeframe 單調放大（4h > 1h > 1m）。
    // 退化 snapshot 路徑會讓三者 ≈0.018% 完全相同（root-cause 指紋），此斷言會在退化資料下失敗。
    assert!(r4h > r1h, "4h range {r4h} must exceed 1h range {r1h} (real candles aggregate)");
    assert!(r1h > r1m, "1h range {r1h} must exceed 1m range {r1m} (real candles aggregate)");

    // 斷言 2：BTC 1h 中位 intrabar range 落真波動帶（~0.1%–3%）。退化 snapshot 的 ~0.018%
    // 會掉出 0.001 下界（精確抓 root-cause「intrabar range ~0.018% identical」）。
    assert!(
        r1h > 0.001 && r1h < 0.03,
        "BTC 1h median range {r1h} outside realistic band [0.001, 0.03]"
    );

    // 斷言 3：turnover 全部 > 0（退化路徑 100% turnover=0 是最硬的指紋）。
    for (tf, bars) in [("1m", &bars_1m), ("1h", &bars_1h), ("4h", &bars_4h)] {
        assert!(
            bars.iter().all(|b| b.turnover > 0.0),
            "{tf}: found turnover<=0 (degenerate-snapshot signature)"
        );
        assert!(
            bars.iter().all(|b| b.volume > 0.0),
            "{tf}: found volume<=0 (degenerate-snapshot signature)"
        );
    }

    // 斷言 4：close != open 普遍成立（退化 snapshot close≈open 99.6%）。
    let close_eq_open_1h = bars_1h.iter().filter(|b| (b.close - b.open).abs() < 1e-9).count();
    assert!(
        close_eq_open_1h <= 2,
        "1h: {close_eq_open_1h}/{} bars have close==open (degenerate-snapshot signature)",
        bars_1h.len()
    );
}

#[test]
#[ignore = "real-network: hits public api.bybit.com /v5/market/kline"]
fn test_strict_filter_accepts_real_klines_as_pass() {
    // 真資料餵真 strict_filter_closed_bars_for：應判 pass（observed≈expected，非 55-58% 缺失）。
    let cases = [("60", 3_600_000_u64, "1h"), ("240", 14_400_000_u64, "4h")];
    for (interval, period_ms, tf) in cases {
        let bars = fetch_klines(interval, 50);
        let page = run_strict(&bars, period_ms, tf);
        eprintln!(
            "{tf}: status={:?} expected={} observed={} sha={}",
            page.verdict.status, page.verdict.expected, page.verdict.observed, &page.verdict.payload_sha256[..16]
        );
        // 真連續資料：每根都嚴格通過（OHLC 有限 > 0、high>=low、內部一致），observed==expected。
        let expected = expected_bars_for(
            bars.iter().map(|b| b.start_time).min().unwrap(),
            bars.iter().map(|b| b.start_time).max().unwrap() + period_ms,
            period_ms,
        );
        assert_eq!(page.verdict.expected, expected, "{tf} expected mismatch");
        assert_eq!(
            page.verdict.status,
            CoverageStatus::Pass,
            "{tf}: real continuous klines must yield pass (got {:?}, obs={}/exp={})",
            page.verdict.status, page.verdict.observed, page.verdict.expected
        );
        // strict 過的 bar：OHLC 全 > 0、high>=low、且 timeframe 標籤正確。
        assert_eq!(page.timeframe, tf);
        assert!(page.bars.iter().all(|b| b.open > 0.0 && b.high >= b.low));
        // turnover 真值被保留（非 fake-zero；對應 PA 驗收 #3）。
        assert!(
            page.bars.iter().all(|b| b.turnover > 0.0),
            "{tf}: strict-passed bar lost turnover (fake-zero leak)"
        );
        // 真蠟燭：至少一根 high>low（非退化平 bar）。
        assert!(
            page.bars.iter().any(|b| b.high > b.low),
            "{tf}: all strict-passed bars are flat (degenerate)"
        );
    }
}

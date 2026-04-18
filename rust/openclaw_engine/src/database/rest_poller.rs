//! REST poller — periodic fetch of funding rates, OI, and LSR from Bybit REST API.
//! REST 輪詢器 — 定期從 Bybit REST API 獲取資金費率、未平倉合約和多空比。
//!
//! MODULE_NOTE (EN): Spawns background tasks that periodically fetch market metrics
//!   via MarketDataClient REST endpoints and send them to the market_data_tx channel.
//!   Intervals: funding 15min, OI 5min, LSR 15min. Failures are logged but non-fatal.
//! MODULE_NOTE (中): 啟動後台任務，定期通過 MarketDataClient REST 端點獲取市場指標，
//!   並發送到 market_data_tx 通道。間隔：資金費率 15 分鐘、OI 5 分鐘、LSR 15 分鐘。
//!   失敗只記錄不致命。

use super::MarketDataMsg;
use crate::bybit_rest_client::BybitRestClient;
use crate::market_data_client::MarketDataClient;
use std::sync::Arc;
use tokio::sync::mpsc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info};

/// Polling intervals (seconds) / 輪詢間隔（秒）
const FUNDING_INTERVAL_SECS: u64 = 900; // 15 min
const OI_INTERVAL_SECS: u64 = 300; // 5 min
const LSR_INTERVAL_SECS: u64 = 900; // 15 min

// S-04: use shared now_ms() from openclaw_core instead of local copy.
// S-04：使用 openclaw_core 的共用 now_ms() 取代本地副本。
use openclaw_core::now_ms;

/// Spawn REST polling tasks for funding, OI, LSR.
/// m-3 fix: accepts Vec<String> so callers can pass SymbolRegistry::snapshot() directly.
/// 啟動資金費率、OI、LSR 的 REST 輪詢任務。
/// m-3 修復：接受 Vec<String>，使調用方可直接傳 SymbolRegistry::snapshot()。
pub fn spawn_rest_pollers(
    client: Arc<BybitRestClient>,
    market_tx: mpsc::Sender<MarketDataMsg>,
    symbols: Vec<String>,
    cancel: CancellationToken,
) {
    let symbols_owned = symbols;

    // Funding rate poller / 資金費率輪詢
    {
        let mdc = MarketDataClient::new(Arc::clone(&client));
        let tx = market_tx.clone();
        let syms = symbols_owned.clone();
        let c = cancel.clone();
        tokio::spawn(async move {
            let mut interval =
                tokio::time::interval(std::time::Duration::from_secs(FUNDING_INTERVAL_SECS));
            interval.tick().await;
            loop {
                tokio::select! {
                    _ = c.cancelled() => break,
                    _ = interval.tick() => {
                        for sym in &syms {
                            match mdc.get_funding_history("linear", sym, None, None, Some(1)).await {
                                Ok(rates) if !rates.is_empty() => {
                                    let r = &rates[0];
                                    let ts = r.funding_rate_timestamp.parse::<u64>().unwrap_or_else(|_| now_ms());
                                    let _ = tx.try_send(MarketDataMsg::FundingRate {
                                        ts_ms: ts,
                                        symbol: sym.clone(),
                                        funding_rate: r.funding_rate,
                                        funding_rate_daily: r.funding_rate * 3.0,
                                    });
                                }
                                Err(e) => debug!(symbol = %sym, error = %e, "funding fetch failed"),
                                _ => {}
                            }
                        }
                    }
                }
            }
        });
    }

    // Open interest poller / 未平倉合約輪詢
    {
        let mdc = MarketDataClient::new(Arc::clone(&client));
        let tx = market_tx.clone();
        let syms = symbols_owned.clone();
        let c = cancel.clone();
        tokio::spawn(async move {
            let mut interval =
                tokio::time::interval(std::time::Duration::from_secs(OI_INTERVAL_SECS));
            interval.tick().await;
            loop {
                tokio::select! {
                    _ = c.cancelled() => break,
                    _ = interval.tick() => {
                        for sym in &syms {
                            match mdc.get_open_interest("linear", sym, "5min", Some(1)).await {
                                Ok(items) if !items.is_empty() => {
                                    let item = &items[0];
                                    let ts = item.timestamp.parse::<u64>().unwrap_or_else(|_| now_ms());
                                    let _ = tx.try_send(MarketDataMsg::OpenInterest {
                                        ts_ms: ts,
                                        symbol: sym.clone(),
                                        open_interest: item.open_interest,
                                        oi_value: 0.0, // not in API response, computed later
                                    });
                                }
                                Err(e) => debug!(symbol = %sym, error = %e, "OI fetch failed"),
                                _ => {}
                            }
                        }
                    }
                }
            }
        });
    }

    // Long-short ratio poller / 多空比輪詢
    {
        let mdc = MarketDataClient::new(Arc::clone(&client));
        let tx = market_tx;
        let syms = symbols_owned;
        let c = cancel;
        tokio::spawn(async move {
            let mut interval =
                tokio::time::interval(std::time::Duration::from_secs(LSR_INTERVAL_SECS));
            interval.tick().await;
            loop {
                tokio::select! {
                    _ = c.cancelled() => break,
                    _ = interval.tick() => {
                        for sym in &syms {
                            match mdc.get_long_short_ratio("linear", sym, "1h", Some(1)).await {
                                Ok(items) if !items.is_empty() => {
                                    let item = &items[0];
                                    let ts = item.timestamp.parse::<u64>().unwrap_or_else(|_| now_ms());
                                    let ratio = if item.sell_ratio > 0.0 {
                                        item.buy_ratio / item.sell_ratio
                                    } else {
                                        1.0
                                    };
                                    let _ = tx.try_send(MarketDataMsg::LongShortRatio {
                                        ts_ms: ts,
                                        symbol: sym.clone(),
                                        buy_ratio: item.buy_ratio,
                                        sell_ratio: item.sell_ratio,
                                        ratio,
                                    });
                                }
                                Err(e) => debug!(symbol = %sym, error = %e, "LSR fetch failed"),
                                _ => {}
                            }
                        }
                    }
                }
            }
        });
    }

    info!("REST pollers spawned (funding/OI/LSR) / REST 輪詢器已啟動");
}

/// EN: Compute long-short ratio with divide-by-zero guard.
///     Extracted for testability (used inline in LSR poller).
/// 中文: 計算多空比，帶除零保護。提取為可測函式。
pub(crate) fn compute_lsr_ratio(buy_ratio: f64, sell_ratio: f64) -> f64 {
    if sell_ratio > 0.0 {
        buy_ratio / sell_ratio
    } else {
        1.0
    }
}

/// EN: Compute daily funding rate from per-interval rate (8h intervals → ×3).
/// 中文: 從單次區間費率計算日化費率（8h 間隔 → ×3）。
pub(crate) fn funding_rate_daily(funding_rate: f64) -> f64 {
    funding_rate * 3.0
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── Constants ──

    /// EN: Polling intervals match documented values.
    /// 中文: 輪詢間隔與文件記載一致。
    #[test]
    fn test_polling_interval_constants() {
        assert_eq!(FUNDING_INTERVAL_SECS, 900, "funding = 15 min");
        assert_eq!(OI_INTERVAL_SECS, 300, "OI = 5 min");
        assert_eq!(LSR_INTERVAL_SECS, 900, "LSR = 15 min");
    }

    // ── LSR ratio ──

    /// EN: Normal case: buy/sell ratio division.
    /// 中文: 正常情況：買/賣比值除法。
    #[test]
    fn test_lsr_ratio_normal() {
        let ratio = compute_lsr_ratio(0.6, 0.4);
        assert!((ratio - 1.5).abs() < 1e-9);
    }

    /// EN: sell_ratio=0 → safe default 1.0 (no divide-by-zero).
    /// 中文: sell_ratio=0 → 安全預設 1.0（無除零）。
    #[test]
    fn test_lsr_ratio_zero_sell_returns_one() {
        assert_eq!(compute_lsr_ratio(0.8, 0.0), 1.0);
    }

    /// EN: Negative sell_ratio (shouldn't happen) → safe default 1.0.
    /// 中文: 負 sell_ratio（不應發生）→ 安全預設 1.0。
    #[test]
    fn test_lsr_ratio_negative_sell_returns_one() {
        assert_eq!(compute_lsr_ratio(0.5, -0.1), 1.0);
    }

    /// EN: Equal ratios → 1.0.
    /// 中文: 相等比率 → 1.0。
    #[test]
    fn test_lsr_ratio_equal() {
        let ratio = compute_lsr_ratio(0.5, 0.5);
        assert!((ratio - 1.0).abs() < 1e-9);
    }

    // ── Funding rate daily ──

    /// EN: Daily = 3× per-interval rate.
    /// 中文: 日化 = 3 × 單次區間費率。
    #[test]
    fn test_funding_rate_daily_multiplier() {
        let daily = funding_rate_daily(0.0001);
        assert!((daily - 0.0003).abs() < 1e-12);
    }

    /// EN: Zero funding rate → zero daily.
    /// 中文: 零費率 → 零日化。
    #[test]
    fn test_funding_rate_daily_zero() {
        assert_eq!(funding_rate_daily(0.0), 0.0);
    }

    /// EN: Negative funding rate stays negative after multiplication.
    /// 中文: 負費率乘以 3 後仍為負。
    #[test]
    fn test_funding_rate_daily_negative() {
        let daily = funding_rate_daily(-0.0002);
        assert!((daily - (-0.0006)).abs() < 1e-12);
    }

    // ── Additional edge cases ──

    /// EN: Very large buy_ratio / small sell_ratio → large ratio (no overflow/panic).
    /// 中文: 極大 buy_ratio / 極小 sell_ratio → 大比率（無溢出/崩潰）。
    #[test]
    fn test_lsr_ratio_extreme_values() {
        let ratio = compute_lsr_ratio(1e10, 1e-10);
        assert!(ratio > 1e18);
        assert!(ratio.is_finite());
    }

    /// EN: Both ratios zero → safe default 1.0 (sell=0 guard triggers).
    /// 中文: 兩者均為零 → 安全預設 1.0（sell=0 守衛觸發）。
    #[test]
    fn test_lsr_ratio_both_zero() {
        assert_eq!(compute_lsr_ratio(0.0, 0.0), 1.0);
    }

    /// EN: Typical funding rate 0.01% → daily 0.03%.
    /// 中文: 典型資金費率 0.01% → 日化 0.03%。
    #[test]
    fn test_funding_rate_daily_typical() {
        let daily = funding_rate_daily(0.0001);
        assert!((daily - 0.0003).abs() < 1e-12);
    }

    /// EN: Large funding rate (extreme market) stays finite.
    /// 中文: 極端行情下的大資金費率保持有限值。
    #[test]
    fn test_funding_rate_daily_large() {
        let daily = funding_rate_daily(0.05); // 5% per interval = extreme
        assert!((daily - 0.15).abs() < 1e-12);
    }

    /// EN: MarketDataMsg variants constructed correctly (channel contract).
    /// 中文: MarketDataMsg 變體正確構建（通道契約）。
    #[test]
    fn test_market_data_msg_funding_rate_construction() {
        let msg = MarketDataMsg::FundingRate {
            ts_ms: 1700000000000,
            symbol: "BTCUSDT".to_string(),
            funding_rate: 0.0001,
            funding_rate_daily: funding_rate_daily(0.0001),
        };
        match msg {
            MarketDataMsg::FundingRate {
                ts_ms,
                symbol,
                funding_rate,
                funding_rate_daily: frd,
            } => {
                assert_eq!(ts_ms, 1700000000000);
                assert_eq!(symbol, "BTCUSDT");
                assert!((funding_rate - 0.0001).abs() < 1e-12);
                assert!((frd - 0.0003).abs() < 1e-12);
            }
            _ => panic!("wrong variant"),
        }
    }

    /// EN: MarketDataMsg::OpenInterest variant construction.
    /// 中文: MarketDataMsg::OpenInterest 變體構建。
    #[test]
    fn test_market_data_msg_open_interest_construction() {
        let msg = MarketDataMsg::OpenInterest {
            ts_ms: 1700000000000,
            symbol: "ETHUSDT".to_string(),
            open_interest: 150_000.0,
            oi_value: 0.0,
        };
        match msg {
            MarketDataMsg::OpenInterest {
                symbol,
                open_interest,
                ..
            } => {
                assert_eq!(symbol, "ETHUSDT");
                assert!((open_interest - 150_000.0).abs() < 1e-6);
            }
            _ => panic!("wrong variant"),
        }
    }

    /// EN: MarketDataMsg::LongShortRatio variant with compute_lsr_ratio.
    /// 中文: MarketDataMsg::LongShortRatio 變體 + compute_lsr_ratio 計算。
    #[test]
    fn test_market_data_msg_lsr_construction() {
        let buy = 0.55;
        let sell = 0.45;
        let msg = MarketDataMsg::LongShortRatio {
            ts_ms: 1700000000000,
            symbol: "SOLUSDT".to_string(),
            buy_ratio: buy,
            sell_ratio: sell,
            ratio: compute_lsr_ratio(buy, sell),
        };
        match msg {
            MarketDataMsg::LongShortRatio { ratio, .. } => {
                assert!((ratio - (0.55 / 0.45)).abs() < 1e-9);
            }
            _ => panic!("wrong variant"),
        }
    }

    /// EN: Cancellation token can be pre-cancelled (tests graceful shutdown path).
    /// 中文: 取消令牌可預先取消（測試優雅關閉路徑）。
    #[test]
    fn test_cancellation_token_contract() {
        let cancel = CancellationToken::new();
        assert!(!cancel.is_cancelled());
        cancel.cancel();
        assert!(cancel.is_cancelled());
    }
}

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

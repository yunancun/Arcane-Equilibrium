//! Bybit V5 market data client — all public market data REST endpoints (R-05).
//! Bybit V5 市場數據客戶端 — 所有公開市場數據 REST 端點。
//!
//! MODULE_NOTE (EN): Comprehensive market data client covering klines (standard, mark-price,
//!   premium-index), tickers, orderbook snapshots, open interest, funding rate history,
//!   long/short ratios, risk limit tiers, ADL alerts, recent trades, historical volatility,
//!   price limits, and server time. All methods return strongly-typed structs parsed from
//!   Bybit's string-encoded JSON responses. Thread-safe via Arc<BybitRestClient>.
//!   Split into submodules: `types` (response structs) and `parsers` (JSON helpers).
//! MODULE_NOTE (中): 全面的市場數據客戶端，涵蓋 K 線（標準/標記價格/溢價指數）、
//!   行情快照、訂單簿、持倉量、資金費率歷史、多空比、風險限額、ADL 警報、
//!   近期成交、歷史波動率、價格限制和服務器時間。所有方法返回強類型結構體，
//!   從 Bybit 的字串編碼 JSON 回應中解析。通過 Arc<BybitRestClient> 線程安全。
//!   拆分為子模組：`types`（回應結構體）和 `parsers`（JSON 輔助）。

mod parsers;
pub mod types;

pub use types::{
    AdlAlert, DeliveryPrice, FundingRecord, InsuranceRecord, KlineBar, LongShortRecord,
    OpenInterestRecord, OrderbookSnapshot, PriceLimit, RecentTrade, RiskLimitTier, ServerTime,
    TickerInfo, VolatilityRecord,
};

use crate::bybit_rest_client::{BybitRestClient, BybitResult};
use parsers::{parse_kline_list, parse_orderbook, parse_str, parse_str_f64, parse_ticker_list};
use std::sync::Arc;
use tracing::debug;

// ---------------------------------------------------------------------------
// MarketDataClient / 市場數據客戶端
// ---------------------------------------------------------------------------

/// Client for all Bybit V5 public market data endpoints.
/// 所有 Bybit V5 公開市場數據端點的客戶端。
///
/// Thread-safe: wraps BybitRestClient in Arc.
/// 線程安全：通過 Arc 包裝 BybitRestClient。
pub struct MarketDataClient {
    client: Arc<BybitRestClient>,
}

impl MarketDataClient {
    /// Create a new MarketDataClient wrapping a shared REST client.
    /// 創建新的 MarketDataClient，包裝共享的 REST 客戶端。
    pub fn new(client: Arc<BybitRestClient>) -> Self {
        Self { client }
    }

    // -----------------------------------------------------------------------
    // Server time / 服務器時間
    // -----------------------------------------------------------------------

    /// Get Bybit server time — for clock sync and latency detection.
    /// 獲取 Bybit 服務器時間 — 用於時鐘同步和延遲檢測。
    ///
    /// GET /v5/market/time
    pub async fn get_server_time(&self) -> BybitResult<ServerTime> {
        debug!("fetching server time / 獲取服務器時間");
        let resp = self.client.get_checked("/v5/market/time", &[]).await?;
        let time_second = resp
            .result
            .get("timeSecond")
            .and_then(|v| v.as_str())
            .and_then(|s| s.parse::<u64>().ok())
            .unwrap_or(0);
        let time_nano = resp
            .result
            .get("timeNano")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        Ok(ServerTime {
            time_second,
            time_nano,
        })
    }

    // -----------------------------------------------------------------------
    // Klines / K 線
    // -----------------------------------------------------------------------

    /// Get historical klines (candlesticks) — for backfill and backtesting.
    /// 獲取歷史 K 線 — 用於回填和回測。
    ///
    /// GET /v5/market/kline
    pub async fn get_klines(
        &self,
        category: &str,
        symbol: &str,
        interval: &str,
        start: Option<u64>,
        end: Option<u64>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<KlineBar>> {
        debug!(
            symbol = symbol,
            interval = interval,
            "fetching klines / 獲取 K 線"
        );
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
            ("interval", interval.to_string()),
        ];
        if let Some(s) = start {
            params.push(("start", s.to_string()));
        }
        if let Some(e) = end {
            params.push(("end", e.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/kline", &param_refs)
            .await?;
        parse_kline_list(&resp.result)
    }

    /// Get mark price klines — needed for funding arb (mark vs last price divergence).
    /// 獲取標記價格 K 線 — 用於資金費率套利（標記價格 vs 最新價格偏離）。
    ///
    /// GET /v5/market/mark-price-kline
    pub async fn get_mark_price_klines(
        &self,
        category: &str,
        symbol: &str,
        interval: &str,
        start: Option<u64>,
        end: Option<u64>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<KlineBar>> {
        debug!(
            symbol = symbol,
            "fetching mark price klines / 獲取標記價格 K 線"
        );
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
            ("interval", interval.to_string()),
        ];
        if let Some(s) = start {
            params.push(("start", s.to_string()));
        }
        if let Some(e) = end {
            params.push(("end", e.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/mark-price-kline", &param_refs)
            .await?;
        parse_kline_list(&resp.result)
    }

    /// Get premium index klines — for funding rate prediction.
    /// 獲取溢價指數 K 線 — 用於資金費率預測。
    ///
    /// GET /v5/market/premium-index-price-kline
    pub async fn get_premium_index_klines(
        &self,
        category: &str,
        symbol: &str,
        interval: &str,
        limit: Option<u32>,
    ) -> BybitResult<Vec<KlineBar>> {
        debug!(
            symbol = symbol,
            "fetching premium index klines / 獲取溢價指數 K 線"
        );
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
            ("interval", interval.to_string()),
        ];
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/premium-index-price-kline", &param_refs)
            .await?;
        parse_kline_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Tickers / 行情
    // -----------------------------------------------------------------------

    /// Get 24-hour tickers — snapshot of all (or one) symbols.
    /// 獲取 24 小時行情 — 所有（或單個）交易對快照。
    ///
    /// GET /v5/market/tickers
    pub async fn get_tickers(
        &self,
        category: &str,
        symbol: Option<&str>,
    ) -> BybitResult<Vec<TickerInfo>> {
        debug!(category = category, "fetching tickers / 獲取行情");
        let mut params: Vec<(&str, &str)> = vec![("category", category)];
        if let Some(s) = symbol {
            params.push(("symbol", s));
        }
        let resp = self
            .client
            .get_checked("/v5/market/tickers", &params)
            .await?;
        parse_ticker_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Orderbook / 訂單簿
    // -----------------------------------------------------------------------

    /// Get L2 orderbook snapshot.
    /// 獲取 L2 訂單簿快照。
    ///
    /// GET /v5/market/orderbook
    pub async fn get_orderbook(
        &self,
        category: &str,
        symbol: &str,
        limit: Option<u32>,
    ) -> BybitResult<OrderbookSnapshot> {
        debug!(symbol = symbol, "fetching orderbook / 獲取訂單簿");
        let limit_str = limit.unwrap_or(50).to_string();
        let params: Vec<(&str, &str)> = vec![
            ("category", category),
            ("symbol", symbol),
            ("limit", &limit_str),
        ];
        let resp = self
            .client
            .get_checked("/v5/market/orderbook", &params)
            .await?;
        parse_orderbook(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Open interest / 持倉量
    // -----------------------------------------------------------------------

    /// Get open interest history — aggregate market sentiment.
    /// 獲取持倉量歷史 — 市場整體情緒。
    ///
    /// GET /v5/market/open-interest
    pub async fn get_open_interest(
        &self,
        category: &str,
        symbol: &str,
        interval: &str,
        limit: Option<u32>,
    ) -> BybitResult<Vec<OpenInterestRecord>> {
        debug!(symbol = symbol, "fetching open interest / 獲取持倉量");
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
            ("intervalTime", interval.to_string()),
        ];
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/open-interest", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(OpenInterestRecord {
                open_interest: parse_str_f64(item, "openInterest"),
                timestamp: parse_str(item, "timestamp"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Funding rate / 資金費率
    // -----------------------------------------------------------------------

    /// Get funding rate history — for funding arb strategy.
    /// 獲取資金費率歷史 — 用於資金費率套利策略。
    ///
    /// GET /v5/market/funding/history
    pub async fn get_funding_history(
        &self,
        category: &str,
        symbol: &str,
        start: Option<u64>,
        end: Option<u64>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<FundingRecord>> {
        debug!(
            symbol = symbol,
            "fetching funding history / 獲取資金費率歷史"
        );
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
        ];
        if let Some(s) = start {
            params.push(("startTime", s.to_string()));
        }
        if let Some(e) = end {
            params.push(("endTime", e.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/funding/history", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(FundingRecord {
                symbol: parse_str(item, "symbol"),
                funding_rate: parse_str_f64(item, "fundingRate"),
                funding_rate_timestamp: parse_str(item, "fundingRateTimestamp"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Long/short ratio / 多空比
    // -----------------------------------------------------------------------

    /// Get long/short account ratio — contrarian signal.
    /// 獲取多空帳戶比例 — 逆向信號。
    ///
    /// GET /v5/market/account-ratio
    pub async fn get_long_short_ratio(
        &self,
        category: &str,
        symbol: &str,
        period: &str,
        limit: Option<u32>,
    ) -> BybitResult<Vec<LongShortRecord>> {
        debug!(symbol = symbol, "fetching long/short ratio / 獲取多空比");
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
            ("period", period.to_string()),
        ];
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/account-ratio", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(LongShortRecord {
                buy_ratio: parse_str_f64(item, "buyRatio"),
                sell_ratio: parse_str_f64(item, "sellRatio"),
                timestamp: parse_str(item, "timestamp"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Risk limit / 風險限額
    // -----------------------------------------------------------------------

    /// Get risk limit tiers — max position size per tier.
    /// 獲取風險限額層級 — 每層級最大倉位。
    ///
    /// GET /v5/market/risk-limit
    pub async fn get_risk_limit(
        &self,
        category: &str,
        symbol: &str,
    ) -> BybitResult<Vec<RiskLimitTier>> {
        debug!(symbol = symbol, "fetching risk limits / 獲取風險限額");
        let params: Vec<(&str, &str)> = vec![("category", category), ("symbol", symbol)];
        let resp = self
            .client
            .get_checked("/v5/market/risk-limit", &params)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut tiers = Vec::with_capacity(list.len());
        for item in &list {
            tiers.push(RiskLimitTier {
                id: item.get("id").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                symbol: parse_str(item, "symbol"),
                risk_limit_value: parse_str_f64(item, "riskLimitValue"),
                max_leverage: parse_str_f64(item, "maxLeverage"),
                initial_margin: parse_str_f64(item, "initialMargin"),
                maintenance_margin: parse_str_f64(item, "maintenanceMargin"),
            });
        }
        Ok(tiers)
    }

    // -----------------------------------------------------------------------
    // Insurance pool / 保險基金
    // -----------------------------------------------------------------------

    /// Get insurance pool data — fund backing for auto-deleveraging.
    /// 獲取保險基金數據 — 支撐自動減倉的資金池。
    ///
    /// GET /v5/market/insurance
    pub async fn get_insurance(&self, coin: Option<&str>) -> BybitResult<Vec<InsuranceRecord>> {
        debug!("fetching insurance pool / 獲取保險基金");
        let mut params: Vec<(&str, &str)> = vec![];
        if let Some(c) = coin {
            params.push(("coin", c));
        }
        let resp = self
            .client
            .get_checked("/v5/market/insurance", &params)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(InsuranceRecord {
                coin: parse_str(item, "coin"),
                balance: parse_str_f64(item, "balance"),
                value: parse_str_f64(item, "value"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // ADL alert / 自動減倉警報
    // -----------------------------------------------------------------------

    /// Get ADL ranking alerts — early warning of auto-deleveraging risk.
    /// 獲取 ADL 排名警報 — 自動減倉風險預警。
    ///
    /// GET /v5/market/adl-alert
    ///
    /// Returns symbols with high ADL risk. Critical for position survival (Principle #5).
    /// 返回高 ADL 風險的交易對。對倉位生存至關重要（原則 #5）。
    pub async fn get_adl_alert(
        &self,
        category: &str,
        symbol: Option<&str>,
    ) -> BybitResult<Vec<AdlAlert>> {
        debug!(category = category, "fetching ADL alerts / 獲取 ADL 警報");
        let mut params: Vec<(&str, &str)> = vec![("category", category)];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }
        let resp = self
            .client
            .get_checked("/v5/market/adl-alert", &params)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut alerts = Vec::with_capacity(list.len());
        for item in &list {
            alerts.push(AdlAlert {
                symbol: parse_str(item, "symbol"),
                side: parse_str(item, "side"),
                adl_rank_indicator: item
                    .get("adlRankIndicator")
                    .and_then(|v| {
                        v.as_i64()
                            .or_else(|| v.as_str().and_then(|s| s.parse().ok()))
                    })
                    .unwrap_or(0) as i32,
            });
        }
        Ok(alerts)
    }

    // -----------------------------------------------------------------------
    // Recent trades / 近期成交
    // -----------------------------------------------------------------------

    /// Get recent trades — for microstructure analysis.
    /// 獲取近期成交 — 用於微觀結構分析。
    ///
    /// GET /v5/market/recent-trade
    pub async fn get_recent_trades(
        &self,
        category: &str,
        symbol: &str,
        limit: Option<u32>,
    ) -> BybitResult<Vec<RecentTrade>> {
        debug!(symbol = symbol, "fetching recent trades / 獲取近期成交");
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
        ];
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/recent-trade", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut trades = Vec::with_capacity(list.len());
        for item in &list {
            trades.push(RecentTrade {
                exec_id: parse_str(item, "execId"),
                symbol: parse_str(item, "symbol"),
                price: parse_str_f64(item, "price"),
                size: parse_str_f64(item, "size"),
                side: parse_str(item, "side"),
                time: parse_str(item, "time"),
                is_block_trade: item
                    .get("isBlockTrade")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false),
            });
        }
        Ok(trades)
    }

    // -----------------------------------------------------------------------
    // Historical volatility / 歷史波動率
    // -----------------------------------------------------------------------

    /// Get historical volatility — for options market analysis.
    /// 獲取歷史波動率 — 用於期權市場分析。
    ///
    /// GET /v5/market/historical-volatility
    pub async fn get_historical_volatility(
        &self,
        category: &str,
        period: Option<u32>,
    ) -> BybitResult<Vec<VolatilityRecord>> {
        debug!(
            category = category,
            "fetching historical volatility / 獲取歷史波動率"
        );
        let mut params: Vec<(&str, String)> = vec![("category", category.to_string())];
        if let Some(p) = period {
            params.push(("period", p.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/historical-volatility", &param_refs)
            .await?;
        // Response is a direct array in result, not nested in "list"
        // 回應是 result 中的直接數組，不嵌套在 "list" 中
        let list = resp.result.as_array().cloned().unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(VolatilityRecord {
                period: item.get("period").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
                value: parse_str(item, "value"),
                time: parse_str(item, "time"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Delivery price / 交割價格
    // -----------------------------------------------------------------------

    /// Get futures delivery prices — for settlement analysis.
    /// 獲取期貨交割價格 — 用於結算分析。
    ///
    /// GET /v5/market/delivery-price
    pub async fn get_delivery_price(
        &self,
        category: &str,
        symbol: Option<&str>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<DeliveryPrice>> {
        debug!(
            category = category,
            "fetching delivery prices / 獲取交割價格"
        );
        let mut params: Vec<(&str, String)> = vec![("category", category.to_string())];
        if let Some(s) = symbol {
            params.push(("symbol", s.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/delivery-price", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(DeliveryPrice {
                symbol: parse_str(item, "symbol"),
                delivery_price: parse_str_f64(item, "deliveryPrice"),
                delivery_time: parse_str(item, "deliveryTime"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Index price kline / 指數價格 K 線
    // -----------------------------------------------------------------------

    /// Get index price klines — index tracking for basis analysis.
    /// 獲取指數價格 K 線 — 用於基差分析的指數追蹤。
    ///
    /// GET /v5/market/index-price-kline
    pub async fn get_index_price_klines(
        &self,
        category: &str,
        symbol: &str,
        interval: &str,
        start: Option<u64>,
        end: Option<u64>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<KlineBar>> {
        debug!(
            symbol = symbol,
            interval = interval,
            "fetching index price klines / 獲取指數價格 K 線"
        );
        let mut params: Vec<(&str, String)> = vec![
            ("category", category.to_string()),
            ("symbol", symbol.to_string()),
            ("interval", interval.to_string()),
        ];
        if let Some(s) = start {
            params.push(("start", s.to_string()));
        }
        if let Some(e) = end {
            params.push(("end", e.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/market/index-price-kline", &param_refs)
            .await?;
        parse_kline_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Price limit / 價格限制
    // -----------------------------------------------------------------------

    /// Get order price limits — max buy / min sell for a symbol.
    /// 獲取下單價格限制 — 交易對最高買入 / 最低賣出。
    ///
    /// GET /v5/market/price-limit  (undocumented on some versions; falls back gracefully)
    /// Note: Not all Bybit API versions expose this. Returns zeros on error.
    /// 注意：並非所有 Bybit API 版本都暴露此端點。錯誤時返回零。
    // This endpoint doesn't exist as a standalone; the info is in instruments-info.
    // We provide it here for convenience by querying instruments-info and extracting.
    // 此端點不作為獨立存在；信息在 instruments-info 中。
    // 我們通過查詢 instruments-info 並提取來提供便利方法。
    pub async fn get_price_limit(&self, category: &str, symbol: &str) -> BybitResult<PriceLimit> {
        debug!(symbol = symbol, "fetching price limits / 獲取價格限制");
        let params: Vec<(&str, &str)> = vec![("category", category), ("symbol", symbol)];
        let resp = self
            .client
            .get_checked("/v5/market/instruments-info", &params)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        if let Some(item) = list.first() {
            let price_filter = item.get("priceFilter").unwrap_or(&serde_json::Value::Null);
            Ok(PriceLimit {
                symbol: parse_str(item, "symbol"),
                buy_limit_price: parse_str_f64(price_filter, "maxPrice"),
                sell_limit_price: parse_str_f64(price_filter, "minPrice"),
            })
        } else {
            Ok(PriceLimit {
                symbol: symbol.to_string(),
                buy_limit_price: 0.0,
                sell_limit_price: 0.0,
            })
        }
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use parsers::{
        parse_kline_list, parse_orderbook, parse_price_levels, parse_str, parse_str_f64,
        parse_ticker_list,
    };

    /// Test parsing kline list from Bybit response format.
    /// 測試從 Bybit 回應格式解析 K 線列表。
    #[test]
    fn test_parse_kline_list() {
        let result = serde_json::json!({
            "list": [
                ["1700000000000", "65000.5", "66000", "64000", "65500.25", "100.5", "6500000"],
                ["1700003600000", "65500.25", "67000", "65000", "66800", "200", "13200000"]
            ]
        });
        let bars = parse_kline_list(&result).unwrap();
        assert_eq!(bars.len(), 2);
        assert_eq!(bars[0].start_time, 1700000000000);
        assert!((bars[0].open - 65000.5).abs() < 1e-10);
        assert!((bars[0].high - 66000.0).abs() < 1e-10);
        assert!((bars[0].low - 64000.0).abs() < 1e-10);
        assert!((bars[0].close - 65500.25).abs() < 1e-10);
        assert!((bars[0].volume - 100.5).abs() < 1e-10);
        assert!((bars[0].turnover - 6500000.0).abs() < 1e-10);
        assert_eq!(bars[1].start_time, 1700003600000);
    }

    /// Test parsing kline with empty list.
    /// 測試解析空 K 線列表。
    #[test]
    fn test_parse_kline_empty() {
        let result = serde_json::json!({"list": []});
        let bars = parse_kline_list(&result).unwrap();
        assert!(bars.is_empty());
    }

    /// Test parsing kline with missing list field.
    /// 測試解析缺少 list 欄位的 K 線。
    #[test]
    fn test_parse_kline_missing_list() {
        let result = serde_json::json!({});
        let bars = parse_kline_list(&result).unwrap();
        assert!(bars.is_empty());
    }

    /// Test parsing kline with short arrays (graceful skip).
    /// 測試解析短數組的 K 線（優雅跳過）。
    #[test]
    fn test_parse_kline_short_array() {
        let result = serde_json::json!({
            "list": [
                ["1700000000000", "65000"],
                ["1700003600000", "65500.25", "67000", "65000", "66800", "200", "13200000"]
            ]
        });
        let bars = parse_kline_list(&result).unwrap();
        assert_eq!(bars.len(), 1); // First item skipped due to < 7 elements
    }

    /// Test parsing ticker list.
    /// 測試解析行情列表。
    #[test]
    fn test_parse_ticker_list() {
        let result = serde_json::json!({
            "list": [{
                "symbol": "BTCUSDT",
                "lastPrice": "65000.50",
                "bid1Price": "65000.00",
                "ask1Price": "65001.00",
                "volume24h": "50000.5",
                "turnover24h": "3250000000",
                "highPrice24h": "66000",
                "lowPrice24h": "64000",
                "prevPrice24h": "64500",
                "openInterest": "120000",
                "fundingRate": "0.0001",
                "nextFundingTime": "1700006400000"
            }]
        });
        let tickers = parse_ticker_list(&result).unwrap();
        assert_eq!(tickers.len(), 1);
        assert_eq!(tickers[0].symbol, "BTCUSDT");
        assert!((tickers[0].last_price - 65000.50).abs() < 1e-10);
        assert!((tickers[0].bid1_price - 65000.0).abs() < 1e-10);
        assert!((tickers[0].ask1_price - 65001.0).abs() < 1e-10);
        assert!((tickers[0].volume_24h - 50000.5).abs() < 1e-10);
        assert!((tickers[0].funding_rate - 0.0001).abs() < 1e-10);
        assert_eq!(tickers[0].next_funding_time, "1700006400000");
    }

    /// Test parsing orderbook snapshot.
    /// 測試解析訂單簿快照。
    #[test]
    fn test_parse_orderbook() {
        let result = serde_json::json!({
            "s": "BTCUSDT",
            "b": [["65000.0", "1.5"], ["64999.5", "2.0"]],
            "a": [["65001.0", "0.8"], ["65002.0", "1.2"]],
            "ts": 1700000000000_u64,
            "u": 12345_u64
        });
        let ob = parse_orderbook(&result).unwrap();
        assert_eq!(ob.symbol, "BTCUSDT");
        assert_eq!(ob.bids.len(), 2);
        assert_eq!(ob.asks.len(), 2);
        assert!((ob.bids[0][0] - 65000.0).abs() < 1e-10);
        assert!((ob.bids[0][1] - 1.5).abs() < 1e-10);
        assert!((ob.asks[0][0] - 65001.0).abs() < 1e-10);
        assert_eq!(ob.ts, 1700000000000);
        assert_eq!(ob.update_id, 12345);
    }

    /// Test parsing orderbook with empty sides.
    /// 測試解析空側的訂單簿。
    #[test]
    fn test_parse_orderbook_empty() {
        let result = serde_json::json!({"s": "ETHUSDT", "b": [], "a": [], "ts": 0, "u": 0});
        let ob = parse_orderbook(&result).unwrap();
        assert_eq!(ob.symbol, "ETHUSDT");
        assert!(ob.bids.is_empty());
        assert!(ob.asks.is_empty());
    }

    /// Test parsing funding records.
    /// 測試解析資金費率記錄。
    #[test]
    fn test_parse_funding_record() {
        let item = serde_json::json!({
            "symbol": "BTCUSDT",
            "fundingRate": "0.00015",
            "fundingRateTimestamp": "1700006400000"
        });
        let record = FundingRecord {
            symbol: parse_str(&item, "symbol"),
            funding_rate: parse_str_f64(&item, "fundingRate"),
            funding_rate_timestamp: parse_str(&item, "fundingRateTimestamp"),
        };
        assert_eq!(record.symbol, "BTCUSDT");
        assert!((record.funding_rate - 0.00015).abs() < 1e-10);
    }

    /// Test parsing long/short ratio record.
    /// 測試解析多空比記錄。
    #[test]
    fn test_parse_long_short_record() {
        let item = serde_json::json!({
            "buyRatio": "0.55",
            "sellRatio": "0.45",
            "timestamp": "1700000000"
        });
        let record = LongShortRecord {
            buy_ratio: parse_str_f64(&item, "buyRatio"),
            sell_ratio: parse_str_f64(&item, "sellRatio"),
            timestamp: parse_str(&item, "timestamp"),
        };
        assert!((record.buy_ratio - 0.55).abs() < 1e-10);
        assert!((record.sell_ratio - 0.45).abs() < 1e-10);
    }

    /// Test parsing risk limit tier.
    /// 測試解析風險限額層級。
    #[test]
    fn test_parse_risk_limit_tier() {
        let item = serde_json::json!({
            "id": 1,
            "symbol": "BTCUSDT",
            "riskLimitValue": "2000000",
            "maxLeverage": "100",
            "initialMargin": "0.01",
            "maintenanceMargin": "0.005"
        });
        let tier = RiskLimitTier {
            id: item.get("id").and_then(|v| v.as_u64()).unwrap_or(0) as u32,
            symbol: parse_str(&item, "symbol"),
            risk_limit_value: parse_str_f64(&item, "riskLimitValue"),
            max_leverage: parse_str_f64(&item, "maxLeverage"),
            initial_margin: parse_str_f64(&item, "initialMargin"),
            maintenance_margin: parse_str_f64(&item, "maintenanceMargin"),
        };
        assert_eq!(tier.id, 1);
        assert_eq!(tier.symbol, "BTCUSDT");
        assert!((tier.risk_limit_value - 2000000.0).abs() < 1e-10);
        assert!((tier.max_leverage - 100.0).abs() < 1e-10);
    }

    /// Test parsing recent trade.
    /// 測試解析近期成交。
    #[test]
    fn test_parse_recent_trade() {
        let item = serde_json::json!({
            "execId": "abc123",
            "symbol": "BTCUSDT",
            "price": "65000.50",
            "size": "0.01",
            "side": "Buy",
            "time": "1700000000000",
            "isBlockTrade": false
        });
        let trade = RecentTrade {
            exec_id: parse_str(&item, "execId"),
            symbol: parse_str(&item, "symbol"),
            price: parse_str_f64(&item, "price"),
            size: parse_str_f64(&item, "size"),
            side: parse_str(&item, "side"),
            time: parse_str(&item, "time"),
            is_block_trade: item
                .get("isBlockTrade")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
        };
        assert_eq!(trade.exec_id, "abc123");
        assert!((trade.price - 65000.50).abs() < 1e-10);
        assert!(!trade.is_block_trade);
    }

    /// Test helper parse_str_f64 with various inputs.
    /// 測試輔助函數 parse_str_f64 的各種輸入。
    #[test]
    fn test_parse_str_f64_various() {
        let obj = serde_json::json!({"a": "123.45", "b": "bad", "c": 999, "d": ""});
        assert!((parse_str_f64(&obj, "a") - 123.45).abs() < 1e-10);
        assert!((parse_str_f64(&obj, "b") - 0.0).abs() < 1e-10);
        assert!((parse_str_f64(&obj, "c") - 0.0).abs() < 1e-10); // not a string
        assert!((parse_str_f64(&obj, "d") - 0.0).abs() < 1e-10); // empty string
        assert!((parse_str_f64(&obj, "missing") - 0.0).abs() < 1e-10);
    }

    /// Test helper parse_str with missing field.
    /// 測試輔助函數 parse_str 處理缺失欄位。
    #[test]
    fn test_parse_str_missing() {
        let obj = serde_json::json!({"a": "hello"});
        assert_eq!(parse_str(&obj, "a"), "hello");
        assert_eq!(parse_str(&obj, "missing"), "");
    }

    /// Test price level parsing for orderbook.
    /// 測試訂單簿價格層級解析。
    #[test]
    fn test_parse_price_levels() {
        let obj = serde_json::json!({
            "levels": [["100.5", "2.0"], ["99.5", "3.0"], ["bad", "1.0"]]
        });
        let levels = parse_price_levels(&obj, "levels");
        // "bad" entry is filtered out / "bad" 條目被過濾
        assert_eq!(levels.len(), 2);
        assert!((levels[0][0] - 100.5).abs() < 1e-10);
        assert!((levels[1][1] - 3.0).abs() < 1e-10);
    }

    /// Test struct serialization round-trip (KlineBar).
    /// 測試結構體序列化往返（KlineBar）。
    #[test]
    fn test_kline_bar_serde() {
        let bar = KlineBar {
            start_time: 1700000000000,
            open: 65000.0,
            high: 66000.0,
            low: 64000.0,
            close: 65500.0,
            volume: 100.0,
            turnover: 6500000.0,
        };
        let json = serde_json::to_string(&bar).unwrap();
        let deser: KlineBar = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.start_time, bar.start_time);
        assert!((deser.open - bar.open).abs() < 1e-10);
    }

    /// Test TickerInfo default fields when JSON has missing values.
    /// 測試 JSON 缺失值時 TickerInfo 的默認欄位。
    #[test]
    fn test_ticker_partial_fields() {
        let result = serde_json::json!({
            "list": [{"symbol": "XRPUSDT", "lastPrice": "0.55"}]
        });
        let tickers = parse_ticker_list(&result).unwrap();
        assert_eq!(tickers.len(), 1);
        assert_eq!(tickers[0].symbol, "XRPUSDT");
        assert!((tickers[0].last_price - 0.55).abs() < 1e-10);
        // Missing fields default to 0.0 / 缺失欄位默認為 0.0
        assert!((tickers[0].bid1_price - 0.0).abs() < 1e-10);
        assert!((tickers[0].funding_rate - 0.0).abs() < 1e-10);
    }

    // -- DeliveryPrice tests / 交割價格測試 --

    /// Test DeliveryPrice struct serde round-trip.
    /// 測試 DeliveryPrice 結構體序列化往返。
    #[test]
    fn test_delivery_price_serde() {
        let dp = DeliveryPrice {
            symbol: "BTCUSDT-20261231".to_string(),
            delivery_price: 70000.0,
            delivery_time: "1735689600000".to_string(),
        };
        let json = serde_json::to_string(&dp).unwrap();
        let deser: DeliveryPrice = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT-20261231");
        assert!((deser.delivery_price - 70000.0).abs() < 1e-10);
    }

    /// Test parsing delivery price list.
    /// 測試解析交割價格列表。
    #[test]
    fn test_parse_delivery_price_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "symbol": "BTCUSDT-20261231",
                    "deliveryPrice": "70000.50",
                    "deliveryTime": "1735689600000"
                },
                {
                    "symbol": "ETHUSDT-20261231",
                    "deliveryPrice": "4500.25",
                    "deliveryTime": "1735689600000"
                }
            ]
        });
        let list = result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        assert_eq!(list.len(), 2);
        let dp0 = DeliveryPrice {
            symbol: parse_str(&list[0], "symbol"),
            delivery_price: parse_str_f64(&list[0], "deliveryPrice"),
            delivery_time: parse_str(&list[0], "deliveryTime"),
        };
        assert_eq!(dp0.symbol, "BTCUSDT-20261231");
        assert!((dp0.delivery_price - 70000.50).abs() < 1e-10);
    }
}

//! Response types for Bybit V5 market data endpoints.
//! Bybit V5 市場數據端點回應類型。
//!
//! MODULE_NOTE (EN): Strongly-typed response structs parsed from Bybit's string-encoded
//!   JSON responses. Extracted from market_data_client.rs for file size compliance.
//! MODULE_NOTE (中): 從 Bybit 字串編碼 JSON 回應中解析的強類型結構體。
//!   從 market_data_client.rs 中提取以符合文件大小限制。

/// Server time from Bybit.
/// Bybit 服務器時間。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ServerTime {
    /// Unix timestamp in seconds / Unix 時間戳（秒）
    pub time_second: u64,
    /// Nanosecond-precision timestamp as string / 納秒精度時間戳字串
    pub time_nano: String,
}

/// Single kline (candlestick) bar.
/// 單根 K 線（蠟燭圖）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct KlineBar {
    /// Bar open time in milliseconds / K 線開始時間（毫秒）
    pub start_time: u64,
    /// Open price / 開盤價
    pub open: f64,
    /// High price / 最高價
    pub high: f64,
    /// Low price / 最低價
    pub low: f64,
    /// Close price / 收盤價
    pub close: f64,
    /// Volume / 成交量
    pub volume: f64,
    /// Turnover (quote currency volume) / 成交額（計價貨幣成交量）
    pub turnover: f64,
}

/// 24-hour ticker info for a symbol.
/// 交易對 24 小時行情。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TickerInfo {
    /// Symbol name / 交易對名稱
    pub symbol: String,
    /// Last traded price / 最新成交價
    pub last_price: f64,
    /// Best bid price / 最佳買價
    pub bid1_price: f64,
    /// Best ask price / 最佳賣價
    pub ask1_price: f64,
    /// 24h trading volume / 24 小時成交量
    pub volume_24h: f64,
    /// 24h turnover / 24 小時成交額
    pub turnover_24h: f64,
    /// 24h high / 24 小時最高價
    pub high_price_24h: f64,
    /// 24h low / 24 小時最低價
    pub low_price_24h: f64,
    /// Previous 24h price / 前 24 小時價格
    pub prev_price_24h: f64,
    /// Current open interest / 當前持倉量
    pub open_interest: f64,
    /// Current funding rate / 當前資金費率
    pub funding_rate: f64,
    /// Next funding time / 下次資金費率時間
    pub next_funding_time: String,
    /// 24h price change percentage (from Bybit price24hPcnt, e.g. 0.0077 = +0.77%)
    /// 24 小時價格漲跌幅（來自 Bybit price24hPcnt，例如 0.0077 = +0.77%）
    pub price_change_24h_pct: f64,
}

/// Level-2 orderbook snapshot.
/// L2 訂單簿快照。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct OrderbookSnapshot {
    /// Symbol / 交易對
    pub symbol: String,
    /// Bid levels: [price, size] / 買盤：[價格, 數量]
    pub bids: Vec<[f64; 2]>,
    /// Ask levels: [price, size] / 賣盤：[價格, 數量]
    pub asks: Vec<[f64; 2]>,
    /// Timestamp (ms) / 時間戳（毫秒）
    pub ts: u64,
    /// Orderbook update sequence ID / 訂單簿更新序列 ID
    pub update_id: u64,
}

/// Open interest data point.
/// 持倉量數據點。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct OpenInterestRecord {
    /// Open interest value / 持倉量
    pub open_interest: f64,
    /// Timestamp string / 時間戳字串
    pub timestamp: String,
}

/// Historical funding rate record.
/// 歷史資金費率記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FundingRecord {
    /// Symbol / 交易對
    pub symbol: String,
    /// Funding rate / 資金費率
    pub funding_rate: f64,
    /// Funding rate timestamp / 資金費率時間戳
    pub funding_rate_timestamp: String,
}

/// Long/short account ratio record.
/// 多空帳戶比例記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LongShortRecord {
    /// Buy (long) ratio / 多頭比例
    pub buy_ratio: f64,
    /// Sell (short) ratio / 空頭比例
    pub sell_ratio: f64,
    /// Timestamp / 時間戳
    pub timestamp: String,
}

/// Risk limit tier for a symbol.
/// 交易對風險限額層級。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RiskLimitTier {
    /// Tier ID / 層級 ID
    pub id: u32,
    /// Symbol / 交易對
    pub symbol: String,
    /// Risk limit value (position notional cap) / 風險限額值（持倉名義上限）
    pub risk_limit_value: f64,
    /// Max leverage for this tier / 此層級最大槓桿
    pub max_leverage: f64,
    /// Initial margin rate / 初始保證金率
    pub initial_margin: f64,
    /// Maintenance margin rate / 維持保證金率
    pub maintenance_margin: f64,
}

/// Insurance pool record.
/// 保險基金記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct InsuranceRecord {
    /// Coin name / 幣種名稱
    pub coin: String,
    /// Insurance fund balance / 保險基金餘額
    pub balance: f64,
    /// Insurance fund value in USD / 保險基金 USD 價值
    pub value: f64,
}

/// Single recent trade.
/// 單筆近期成交。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RecentTrade {
    /// Execution ID / 成交 ID
    pub exec_id: String,
    /// Symbol / 交易對
    pub symbol: String,
    /// Trade price / 成交價
    pub price: f64,
    /// Trade size / 成交量
    pub size: f64,
    /// Trade side: "Buy" or "Sell" / 成交方向
    pub side: String,
    /// Timestamp string / 時間戳字串
    pub time: String,
    /// Whether this is a block trade / 是否為大宗交易
    pub is_block_trade: bool,
}

/// Historical volatility record (options market).
/// 歷史波動率記錄（期權市場）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct VolatilityRecord {
    /// Period in days / 週期（天）
    pub period: u32,
    /// Volatility value / 波動率值
    pub value: String,
    /// Timestamp / 時間戳
    pub time: String,
}

/// Price limit (max buy / min sell) for a symbol.
/// 交易對價格限制（最高買入 / 最低賣出）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct PriceLimit {
    /// Symbol / 交易對
    pub symbol: String,
    /// Maximum buy price allowed / 允許的最高買入價
    pub buy_limit_price: f64,
    /// Minimum sell price allowed / 允許的最低賣出價
    pub sell_limit_price: f64,
}

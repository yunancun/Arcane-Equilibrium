//! Bybit V5 spot margin client — spot margin trading operations (R-05).
//! Bybit V5 現貨保證金客戶端 — 現貨保證金交易操作。
//!
//! MODULE_NOTE (EN): Manages spot margin trading on Bybit V5: query margin data,
//!   toggle margin mode, set leverage, query margin state, list borrowable tokens,
//!   and query repayment history. All methods are async and use Arc<BybitRestClient>.
//! MODULE_NOTE (中): 管理 Bybit V5 上的現貨保證金交易：查詢保證金數據、
//!   切換保證金模式、設置槓桿、查詢保證金狀態、列出可借幣種、
//!   查詢還款歷史。所有方法為異步，使用 Arc<BybitRestClient>。

use crate::bybit_rest_client::{BybitRestClient, BybitResult};
use std::sync::Arc;
use tracing::{debug, info};

// ---------------------------------------------------------------------------
// Structs / 結構體
// ---------------------------------------------------------------------------

/// Spot margin trading data for a symbol.
/// 交易對的現貨保證金交易數據。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SpotMarginData {
    /// Symbol name / 交易對名稱
    pub symbol: String,
    /// Whether margin trading is enabled / 是否啟用保證金交易
    pub margin_trading_enabled: bool,
    /// Max leverage for this symbol / 此交易對最大槓桿
    pub max_leverage: f64,
}

/// Spot margin state for the account.
/// 帳戶的現貨保證金狀態。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SpotMarginState {
    /// Whether spot margin mode is enabled / 是否啟用現貨保證金模式
    pub spot_margin_mode: bool,
    /// Current leverage / 當前槓桿
    pub leverage: f64,
    /// Account equity / 帳戶權益
    pub equity: f64,
}

/// Borrowable token information for cross margin.
/// 全倉保證金可借幣種信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct BorrowableToken {
    /// Token name, e.g. "USDT" / 幣種名稱
    pub token: String,
    /// Maximum borrowable amount / 最大可借數量
    pub max_borrowable: f64,
    /// Hourly borrow rate / 每小時借幣利率
    pub hourly_borrow_rate: f64,
    /// Current borrowed amount / 當前已借數量
    pub borrowed_amount: f64,
}

/// Repayment history record.
/// 還款歷史記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct RepaymentRecord {
    /// Token name / 幣種名稱
    pub token: String,
    /// Repayment amount / 還款數量
    pub amount: f64,
    /// Interest paid / 支付利息
    pub interest: f64,
    /// Repayment timestamp / 還款時間戳
    pub timestamp: String,
    /// Transaction ID / 交易 ID
    pub transaction_id: String,
}

// ---------------------------------------------------------------------------
// SpotMarginClient / 現貨保證金客戶端
// ---------------------------------------------------------------------------

/// Client for Bybit V5 spot margin trading operations.
/// Bybit V5 現貨保證金交易操作客戶端。
///
/// Thread-safe: uses Arc<BybitRestClient>.
/// 線程安全：使用 Arc<BybitRestClient>。
pub struct SpotMarginClient {
    /// Shared REST client / 共享 REST 客戶端
    client: Arc<BybitRestClient>,
}

impl SpotMarginClient {
    /// Create a new SpotMarginClient.
    /// 創建新的現貨保證金客戶端。
    pub fn new(client: Arc<BybitRestClient>) -> Self {
        Self { client }
    }

    // -----------------------------------------------------------------------
    // Margin data / 保證金數據
    // -----------------------------------------------------------------------

    /// Get spot margin trading data for symbols.
    /// 獲取交易對的現貨保證金交易數據。
    ///
    /// GET /v5/spot-margin-trade/data
    pub async fn get_margin_data(&self, symbol: Option<&str>) -> BybitResult<Vec<SpotMarginData>> {
        debug!("fetching spot margin data / 獲取現貨保證金數據");
        let mut params: Vec<(&str, &str)> = vec![];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }
        let resp = self
            .client
            .get_checked("/v5/spot-margin-trade/data", &params)
            .await?;
        parse_margin_data_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Switch mode / 切換模式
    // -----------------------------------------------------------------------

    /// Toggle spot margin trading mode on/off.
    /// 開啟/關閉現貨保證金交易模式。
    ///
    /// POST /v5/spot-margin-uta/switch-mode (UTA account)
    ///
    /// spot_margin_mode: "1" = on, "0" = off
    /// spot_margin_mode: "1" = 開啟, "0" = 關閉
    pub async fn switch_mode(&self, spot_margin_mode: bool) -> BybitResult<()> {
        let mode_str = if spot_margin_mode { "1" } else { "0" };
        let body = serde_json::json!({
            "spotMarginMode": mode_str,
        });

        info!(
            enabled = spot_margin_mode,
            "switching spot margin mode / 切換現貨保證金模式"
        );

        self.client
            .post_checked("/v5/spot-margin-uta/switch-mode", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Set leverage / 設置槓桿
    // -----------------------------------------------------------------------

    /// Set spot margin leverage.
    /// 設置現貨保證金槓桿。
    ///
    /// POST /v5/spot-margin-uta/set-leverage (UTA account)
    pub async fn set_leverage(&self, leverage: f64) -> BybitResult<()> {
        let body = serde_json::json!({
            "leverage": format!("{}", leverage),
        });

        info!(
            leverage = leverage,
            "setting spot margin leverage / 設置現貨保證金槓桿"
        );

        self.client
            .post_checked("/v5/spot-margin-uta/set-leverage", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Margin state / 保證金狀態
    // -----------------------------------------------------------------------

    /// Query current spot margin state.
    /// 查詢當前現貨保證金狀態。
    ///
    /// GET /v5/spot-margin-uta/status (UTA account)
    pub async fn get_margin_state(&self) -> BybitResult<SpotMarginState> {
        debug!("fetching spot margin state / 獲取現貨保證金狀態");
        let resp = self
            .client
            .get_checked("/v5/spot-margin-uta/status", &[])
            .await?;
        parse_margin_state(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Borrowable tokens / 可借幣種
    // -----------------------------------------------------------------------

    /// Get max borrowable amount for spot margin (UTA account).
    /// 獲取現貨保證金最大可借金額（UTA 帳戶）。
    ///
    /// GET /v5/spot-margin-uta/max-borrowable
    pub async fn get_borrowable_tokens(
        &self,
        token: Option<&str>,
    ) -> BybitResult<Vec<BorrowableToken>> {
        debug!("fetching borrowable tokens / 獲取可借幣種");
        let mut params: Vec<(&str, &str)> = vec![];
        if let Some(t) = token {
            params.push(("coin", t));
        }
        let resp = self
            .client
            .get_checked("/v5/spot-margin-uta/max-borrowable", &params)
            .await?;
        parse_borrowable_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Repayment available / 可還款金額
    // -----------------------------------------------------------------------

    /// Get available amount to repay for spot margin (UTA account).
    /// 獲取現貨保證金可還款金額（UTA 帳戶）。
    ///
    /// GET /v5/spot-margin-uta/repayment-available-amount
    pub async fn get_repay_history(
        &self,
        token: Option<&str>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<RepaymentRecord>> {
        debug!("fetching repayment history / 獲取還款歷史");
        let limit_str = limit.unwrap_or(50).to_string();
        let mut params: Vec<(&str, &str)> = vec![("limit", &limit_str)];
        if let Some(t) = token {
            params.push(("coin", t));
        }
        let resp = self
            .client
            .get_checked("/v5/spot-margin-uta/repayment-available-amount", &params)
            .await?;
        parse_repay_history(&resp.result)
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse a string field from JSON / 從 JSON 解析字串欄位
fn parse_str(obj: &serde_json::Value, field: &str) -> String {
    obj.get(field)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

/// Parse a string-encoded f64 field / 解析字串編碼的 f64 欄位
fn parse_str_f64(obj: &serde_json::Value, field: &str) -> f64 {
    obj.get(field)
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0)
}

/// Parse a bool field (handles string "1"/"0" and native bool).
/// 解析布爾欄位（處理字串 "1"/"0" 和原生布爾值）。
fn parse_bool(obj: &serde_json::Value, field: &str) -> bool {
    obj.get(field)
        .map(|v| {
            v.as_bool()
                .unwrap_or_else(|| v.as_str().map_or(false, |s| s == "1" || s == "true"))
        })
        .unwrap_or(false)
}

/// Parse margin data list from Bybit response.
/// 從 Bybit 回應中解析保證金數據列表。
fn parse_margin_data_list(result: &serde_json::Value) -> BybitResult<Vec<SpotMarginData>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut items = Vec::with_capacity(list.len());
    for item in &list {
        items.push(SpotMarginData {
            symbol: parse_str(item, "symbol"),
            margin_trading_enabled: parse_bool(item, "marginTrading"),
            max_leverage: parse_str_f64(item, "maxLeverage"),
        });
    }
    Ok(items)
}

/// Parse margin state from Bybit response.
/// 從 Bybit 回應中解析保證金狀態。
fn parse_margin_state(result: &serde_json::Value) -> BybitResult<SpotMarginState> {
    Ok(SpotMarginState {
        spot_margin_mode: parse_bool(result, "spotMarginMode"),
        leverage: parse_str_f64(result, "spotLeverage"),
        equity: parse_str_f64(result, "effectiveEquity"),
    })
}

/// Parse borrowable token list from Bybit response.
/// 從 Bybit 回應中解析可借幣種列表。
fn parse_borrowable_list(result: &serde_json::Value) -> BybitResult<Vec<BorrowableToken>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut items = Vec::with_capacity(list.len());
    for item in &list {
        items.push(BorrowableToken {
            token: parse_str(item, "coin"),
            max_borrowable: parse_str_f64(item, "maxBorrowingAmount"),
            hourly_borrow_rate: parse_str_f64(item, "hourlyBorrowRate"),
            borrowed_amount: parse_str_f64(item, "borrowedAmount"),
        });
    }
    Ok(items)
}

/// Parse repayment history from Bybit response.
/// 從 Bybit 回應中解析還款歷史。
fn parse_repay_history(result: &serde_json::Value) -> BybitResult<Vec<RepaymentRecord>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut records = Vec::with_capacity(list.len());
    for item in &list {
        records.push(RepaymentRecord {
            token: parse_str(item, "coin"),
            amount: parse_str_f64(item, "repaidAmount"),
            interest: parse_str_f64(item, "interest"),
            timestamp: parse_str(item, "createdTime"),
            transaction_id: parse_str(item, "transactionId"),
        });
    }
    Ok(records)
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_margin_data_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "symbol": "BTCUSDT",
                    "marginTrading": "1",
                    "maxLeverage": "10"
                },
                {
                    "symbol": "ETHUSDT",
                    "marginTrading": "0",
                    "maxLeverage": "5"
                }
            ]
        });
        let data = parse_margin_data_list(&result).unwrap();
        assert_eq!(data.len(), 2);
        assert_eq!(data[0].symbol, "BTCUSDT");
        assert!(data[0].margin_trading_enabled);
        assert!((data[0].max_leverage - 10.0).abs() < 1e-10);
        assert_eq!(data[1].symbol, "ETHUSDT");
        assert!(!data[1].margin_trading_enabled);
    }

    #[test]
    fn test_parse_margin_data_empty() {
        let result = serde_json::json!({"list": []});
        let data = parse_margin_data_list(&result).unwrap();
        assert!(data.is_empty());
    }

    #[test]
    fn test_parse_margin_state() {
        let result = serde_json::json!({
            "spotMarginMode": "1",
            "spotLeverage": "5",
            "effectiveEquity": "10000.50"
        });
        let state = parse_margin_state(&result).unwrap();
        assert!(state.spot_margin_mode);
        assert!((state.leverage - 5.0).abs() < 1e-10);
        assert!((state.equity - 10000.50).abs() < 1e-10);
    }

    #[test]
    fn test_parse_margin_state_disabled() {
        let result = serde_json::json!({
            "spotMarginMode": "0",
            "spotLeverage": "1",
            "effectiveEquity": "5000"
        });
        let state = parse_margin_state(&result).unwrap();
        assert!(!state.spot_margin_mode);
        assert!((state.leverage - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_parse_borrowable_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "coin": "USDT",
                    "maxBorrowingAmount": "100000",
                    "hourlyBorrowRate": "0.0000125",
                    "borrowedAmount": "5000"
                },
                {
                    "coin": "BTC",
                    "maxBorrowingAmount": "1.5",
                    "hourlyBorrowRate": "0.0000098",
                    "borrowedAmount": "0"
                }
            ]
        });
        let tokens = parse_borrowable_list(&result).unwrap();
        assert_eq!(tokens.len(), 2);
        assert_eq!(tokens[0].token, "USDT");
        assert!((tokens[0].max_borrowable - 100000.0).abs() < 1e-10);
        assert!((tokens[0].hourly_borrow_rate - 0.0000125).abs() < 1e-12);
        assert!((tokens[0].borrowed_amount - 5000.0).abs() < 1e-10);
        assert_eq!(tokens[1].token, "BTC");
    }

    #[test]
    fn test_parse_borrowable_empty() {
        let result = serde_json::json!({"list": []});
        let tokens = parse_borrowable_list(&result).unwrap();
        assert!(tokens.is_empty());
    }

    #[test]
    fn test_parse_repay_history() {
        let result = serde_json::json!({
            "list": [
                {
                    "coin": "USDT",
                    "repaidAmount": "1000.50",
                    "interest": "2.35",
                    "createdTime": "1700000000000",
                    "transactionId": "tx-001"
                }
            ]
        });
        let records = parse_repay_history(&result).unwrap();
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].token, "USDT");
        assert!((records[0].amount - 1000.50).abs() < 1e-10);
        assert!((records[0].interest - 2.35).abs() < 1e-10);
        assert_eq!(records[0].timestamp, "1700000000000");
        assert_eq!(records[0].transaction_id, "tx-001");
    }

    #[test]
    fn test_parse_repay_history_empty() {
        let result = serde_json::json!({"list": []});
        let records = parse_repay_history(&result).unwrap();
        assert!(records.is_empty());
    }

    #[test]
    fn test_parse_bool_variants() {
        let obj = serde_json::json!({"a": "1", "b": "0", "c": true, "d": false, "e": "true"});
        assert!(parse_bool(&obj, "a"));
        assert!(!parse_bool(&obj, "b"));
        assert!(parse_bool(&obj, "c"));
        assert!(!parse_bool(&obj, "d"));
        assert!(parse_bool(&obj, "e"));
        assert!(!parse_bool(&obj, "missing"));
    }

    // -- Serde round-trip tests / 序列化往返測試 --

    #[test]
    fn test_spot_margin_data_serde() {
        let data = SpotMarginData {
            symbol: "BTCUSDT".to_string(),
            margin_trading_enabled: true,
            max_leverage: 10.0,
        };
        let json = serde_json::to_string(&data).unwrap();
        let deser: SpotMarginData = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT");
        assert!(deser.margin_trading_enabled);
    }

    #[test]
    fn test_spot_margin_state_serde() {
        let state = SpotMarginState {
            spot_margin_mode: true,
            leverage: 5.0,
            equity: 10000.0,
        };
        let json = serde_json::to_string(&state).unwrap();
        let deser: SpotMarginState = serde_json::from_str(&json).unwrap();
        assert!(deser.spot_margin_mode);
        assert!((deser.leverage - 5.0).abs() < 1e-10);
    }

    #[test]
    fn test_borrowable_token_serde() {
        let token = BorrowableToken {
            token: "USDT".to_string(),
            max_borrowable: 100000.0,
            hourly_borrow_rate: 0.0000125,
            borrowed_amount: 5000.0,
        };
        let json = serde_json::to_string(&token).unwrap();
        let deser: BorrowableToken = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.token, "USDT");
        assert!((deser.max_borrowable - 100000.0).abs() < 1e-10);
    }

    #[test]
    fn test_repayment_record_serde() {
        let record = RepaymentRecord {
            token: "BTC".to_string(),
            amount: 0.5,
            interest: 0.001,
            timestamp: "1700000000000".to_string(),
            transaction_id: "tx-abc".to_string(),
        };
        let json = serde_json::to_string(&record).unwrap();
        let deser: RepaymentRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.token, "BTC");
        assert!((deser.amount - 0.5).abs() < 1e-10);
    }
}

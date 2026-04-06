//! Bybit V5 leverage token (ETP) client — spot leverage token operations (R-05).
//! Bybit V5 槓桿代幣（ETP）客戶端 — 現貨槓桿代幣操作。
//!
//! MODULE_NOTE (EN): Manages Bybit V5 spot leverage tokens (ETPs): query token info,
//!   reference data, purchase, and redeem. Leverage tokens provide leveraged exposure
//!   without managing margin or liquidation risk.
//! MODULE_NOTE (中): 管理 Bybit V5 現貨槓桿代幣（ETP）：查詢代幣信息、參考數據、
//!   購買和贖回。槓桿代幣提供槓桿敞口，無需管理保證金或清算風險。

use crate::bybit_rest_client::{BybitRestClient, BybitResult};
use std::sync::Arc;
use tracing::{debug, info};

// ---------------------------------------------------------------------------
// Structs / 結構體
// ---------------------------------------------------------------------------

/// Leverage token basic information.
/// 槓桿代幣基本信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LeverageTokenInfo {
    /// Token abbreviation, e.g. "BTC3L" / 代幣縮寫
    pub lt_coin: String,
    /// Token full name / 代幣全稱
    pub lt_name: String,
    /// Max purchase amount per order / 每單最大購買數量
    pub max_purchase: f64,
    /// Min purchase amount per order / 每單最小購買數量
    pub min_purchase: f64,
    /// Max purchase daily limit / 每日最大購買限額
    pub max_purchase_daily: f64,
    /// Max redeem amount per order / 每單最大贖回數量
    pub max_redeem: f64,
    /// Min redeem amount per order / 每單最小贖回數量
    pub min_redeem: f64,
    /// Max redeem daily limit / 每日最大贖回限額
    pub max_redeem_daily: f64,
    /// Purchase fee rate / 購買手續費率
    pub purchase_fee_rate: f64,
    /// Redeem fee rate / 贖回手續費率
    pub redeem_fee_rate: f64,
    /// Token status: "1" = active / 代幣狀態："1" = 活躍
    pub lt_status: String,
    /// Fund fee (management fee rate) / 基金費用（管理費率）
    pub fund_fee: f64,
    /// Fund fee timestamp / 基金費用時間戳
    pub fund_fee_time: String,
}

/// Leverage token reference data (NAV, value, etc.).
/// 槓桿代幣參考數據（淨值、價值等）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LeverageTokenReference {
    /// Token abbreviation / 代幣縮寫
    pub lt_coin: String,
    /// Net asset value per token / 每個代幣的淨資產價值
    pub nav: f64,
    /// Total circulating supply / 總流通量
    pub circulation: f64,
    /// Basket (underlying asset value) / 底層資產價值
    pub basket: f64,
    /// Target leverage / 目標槓桿
    pub leverage: f64,
    /// NAV timestamp / 淨值時間戳
    pub nav_time: String,
}

/// Result of a leverage token purchase.
/// 槓桿代幣購買結果。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LtPurchaseResult {
    /// Token abbreviation / 代幣縮寫
    pub lt_coin: String,
    /// Order status / 訂單狀態
    pub lt_order_status: String,
    /// Executed quantity / 成交數量
    pub exec_qty: f64,
    /// Executed amount (cost in quote) / 成交金額（計價貨幣成本）
    pub exec_amt: f64,
    /// Purchase order ID / 購買訂單 ID
    pub lt_order_id: String,
}

/// Result of a leverage token redemption.
/// 槓桿代幣贖回結果。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct LtRedeemResult {
    /// Token abbreviation / 代幣縮寫
    pub lt_coin: String,
    /// Order status / 訂單狀態
    pub lt_order_status: String,
    /// Redeemed quantity / 贖回數量
    pub quantity: f64,
    /// Redeemed value in quote / 贖回價值（計價貨幣）
    pub exec_amt: f64,
    /// Redeem order ID / 贖回訂單 ID
    pub lt_order_id: String,
}

// ---------------------------------------------------------------------------
// LeverageTokenClient / 槓桿代幣客戶端
// ---------------------------------------------------------------------------

/// Client for Bybit V5 spot leverage token (ETP) operations.
/// Bybit V5 現貨槓桿代幣（ETP）操作客戶端。
///
/// Thread-safe: uses Arc<BybitRestClient>.
/// 線程安全：使用 Arc<BybitRestClient>。
pub struct LeverageTokenClient {
    /// Shared REST client / 共享 REST 客戶端
    client: Arc<BybitRestClient>,
}

impl LeverageTokenClient {
    /// Create a new LeverageTokenClient.
    /// 創建新的槓桿代幣客戶端。
    pub fn new(client: Arc<BybitRestClient>) -> Self {
        Self { client }
    }

    // -----------------------------------------------------------------------
    // Token info / 代幣信息
    // -----------------------------------------------------------------------

    /// Get leverage token information.
    /// 獲取槓桿代幣信息。
    ///
    /// GET /v5/spot-lever-token/info
    pub async fn get_token_info(
        &self,
        lt_coin: Option<&str>,
    ) -> BybitResult<Vec<LeverageTokenInfo>> {
        debug!("fetching leverage token info / 獲取槓桿代幣信息");
        let mut params: Vec<(&str, &str)> = vec![];
        if let Some(coin) = lt_coin {
            params.push(("ltCoin", coin));
        }
        let resp = self
            .client
            .get_checked("/v5/spot-lever-token/info", &params)
            .await?;
        parse_token_info_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Reference data / 參考數據
    // -----------------------------------------------------------------------

    /// Get leverage token reference data (NAV, circulation, etc.).
    /// 獲取槓桿代幣參考數據（淨值、流通量等）。
    ///
    /// GET /v5/spot-lever-token/reference
    pub async fn get_reference(
        &self,
        lt_coin: Option<&str>,
    ) -> BybitResult<Vec<LeverageTokenReference>> {
        debug!("fetching leverage token reference / 獲取槓桿代幣參考數據");
        let mut params: Vec<(&str, &str)> = vec![];
        if let Some(coin) = lt_coin {
            params.push(("ltCoin", coin));
        }
        let resp = self
            .client
            .get_checked("/v5/spot-lever-token/reference", &params)
            .await?;
        parse_reference_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Purchase / 購買
    // -----------------------------------------------------------------------

    /// Purchase (buy) a leverage token.
    /// 購買槓桿代幣。
    ///
    /// POST /v5/spot-lever-token/purchase
    pub async fn purchase(&self, lt_coin: &str, amount: f64) -> BybitResult<LtPurchaseResult> {
        let body = serde_json::json!({
            "ltCoin": lt_coin,
            "ltAmount": format!("{}", amount),
        });

        info!(
            lt_coin = lt_coin,
            amount = amount,
            "purchasing leverage token / 購買槓桿代幣"
        );

        let resp = self
            .client
            .post_checked("/v5/spot-lever-token/purchase", &body)
            .await?;
        parse_purchase_result(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Redeem / 贖回
    // -----------------------------------------------------------------------

    /// Redeem (sell back) a leverage token.
    /// 贖回槓桿代幣。
    ///
    /// POST /v5/spot-lever-token/redeem
    pub async fn redeem(&self, lt_coin: &str, quantity: f64) -> BybitResult<LtRedeemResult> {
        let body = serde_json::json!({
            "ltCoin": lt_coin,
            "ltAmount": format!("{}", quantity),
        });

        info!(
            lt_coin = lt_coin,
            quantity = quantity,
            "redeeming leverage token / 贖回槓桿代幣"
        );

        let resp = self
            .client
            .post_checked("/v5/spot-lever-token/redeem", &body)
            .await?;
        parse_redeem_result(&resp.result)
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

/// Parse leverage token info list from Bybit response.
/// 從 Bybit 回應中解析槓桿代幣信息列表。
fn parse_token_info_list(result: &serde_json::Value) -> BybitResult<Vec<LeverageTokenInfo>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut items = Vec::with_capacity(list.len());
    for item in &list {
        items.push(LeverageTokenInfo {
            lt_coin: parse_str(item, "ltCoin"),
            lt_name: parse_str(item, "ltName"),
            max_purchase: parse_str_f64(item, "maxPurchase"),
            min_purchase: parse_str_f64(item, "minPurchase"),
            max_purchase_daily: parse_str_f64(item, "maxPurchaseDaily"),
            max_redeem: parse_str_f64(item, "maxRedeem"),
            min_redeem: parse_str_f64(item, "minRedeem"),
            max_redeem_daily: parse_str_f64(item, "maxRedeemDaily"),
            purchase_fee_rate: parse_str_f64(item, "purchaseFeeRate"),
            redeem_fee_rate: parse_str_f64(item, "redeemFeeRate"),
            lt_status: parse_str(item, "ltStatus"),
            fund_fee: parse_str_f64(item, "fundFee"),
            fund_fee_time: parse_str(item, "fundFeeTime"),
        });
    }
    Ok(items)
}

/// Parse leverage token reference list from Bybit response.
/// 從 Bybit 回應中解析槓桿代幣參考數據列表。
fn parse_reference_list(result: &serde_json::Value) -> BybitResult<Vec<LeverageTokenReference>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut items = Vec::with_capacity(list.len());
    for item in &list {
        items.push(LeverageTokenReference {
            lt_coin: parse_str(item, "ltCoin"),
            nav: parse_str_f64(item, "nav"),
            circulation: parse_str_f64(item, "circulation"),
            basket: parse_str_f64(item, "basket"),
            leverage: parse_str_f64(item, "leverage"),
            nav_time: parse_str(item, "navTime"),
        });
    }
    Ok(items)
}

/// Parse purchase result from Bybit response.
/// 從 Bybit 回應中解析購買結果。
fn parse_purchase_result(result: &serde_json::Value) -> BybitResult<LtPurchaseResult> {
    Ok(LtPurchaseResult {
        lt_coin: parse_str(result, "ltCoin"),
        lt_order_status: parse_str(result, "ltOrderStatus"),
        exec_qty: parse_str_f64(result, "execQty"),
        exec_amt: parse_str_f64(result, "execAmt"),
        lt_order_id: parse_str(result, "ltOrderId"),
    })
}

/// Parse redeem result from Bybit response.
/// 從 Bybit 回應中解析贖回結果。
fn parse_redeem_result(result: &serde_json::Value) -> BybitResult<LtRedeemResult> {
    Ok(LtRedeemResult {
        lt_coin: parse_str(result, "ltCoin"),
        lt_order_status: parse_str(result, "ltOrderStatus"),
        quantity: parse_str_f64(result, "quantity"),
        exec_amt: parse_str_f64(result, "execAmt"),
        lt_order_id: parse_str(result, "ltOrderId"),
    })
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_token_info_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "ltCoin": "BTC3L",
                    "ltName": "BTC 3x Long",
                    "maxPurchase": "50000",
                    "minPurchase": "10",
                    "maxPurchaseDaily": "200000",
                    "maxRedeem": "50000",
                    "minRedeem": "10",
                    "maxRedeemDaily": "200000",
                    "purchaseFeeRate": "0.0005",
                    "redeemFeeRate": "0.0005",
                    "ltStatus": "1",
                    "fundFee": "0.0001",
                    "fundFeeTime": "1700000000000"
                }
            ]
        });
        let infos = parse_token_info_list(&result).unwrap();
        assert_eq!(infos.len(), 1);
        assert_eq!(infos[0].lt_coin, "BTC3L");
        assert_eq!(infos[0].lt_name, "BTC 3x Long");
        assert!((infos[0].max_purchase - 50000.0).abs() < 1e-10);
        assert!((infos[0].min_purchase - 10.0).abs() < 1e-10);
        assert!((infos[0].purchase_fee_rate - 0.0005).abs() < 1e-10);
        assert_eq!(infos[0].lt_status, "1");
    }

    #[test]
    fn test_parse_token_info_empty() {
        let result = serde_json::json!({"list": []});
        let infos = parse_token_info_list(&result).unwrap();
        assert!(infos.is_empty());
    }

    #[test]
    fn test_parse_reference_list() {
        let result = serde_json::json!({
            "list": [
                {
                    "ltCoin": "BTC3L",
                    "nav": "15.234",
                    "circulation": "1000000",
                    "basket": "15234000",
                    "leverage": "3",
                    "navTime": "1700000000000"
                },
                {
                    "ltCoin": "ETH3S",
                    "nav": "8.567",
                    "circulation": "500000",
                    "basket": "4283500",
                    "leverage": "-3",
                    "navTime": "1700000000000"
                }
            ]
        });
        let refs = parse_reference_list(&result).unwrap();
        assert_eq!(refs.len(), 2);
        assert_eq!(refs[0].lt_coin, "BTC3L");
        assert!((refs[0].nav - 15.234).abs() < 1e-10);
        assert!((refs[0].circulation - 1000000.0).abs() < 1e-10);
        assert!((refs[0].leverage - 3.0).abs() < 1e-10);
        assert_eq!(refs[1].lt_coin, "ETH3S");
        assert!((refs[1].leverage - (-3.0)).abs() < 1e-10);
    }

    #[test]
    fn test_parse_purchase_result() {
        let result = serde_json::json!({
            "ltCoin": "BTC3L",
            "ltOrderStatus": "2",
            "execQty": "100",
            "execAmt": "1523.40",
            "ltOrderId": "lt-purchase-001"
        });
        let purchase = parse_purchase_result(&result).unwrap();
        assert_eq!(purchase.lt_coin, "BTC3L");
        assert_eq!(purchase.lt_order_status, "2");
        assert!((purchase.exec_qty - 100.0).abs() < 1e-10);
        assert!((purchase.exec_amt - 1523.40).abs() < 1e-10);
        assert_eq!(purchase.lt_order_id, "lt-purchase-001");
    }

    #[test]
    fn test_parse_redeem_result() {
        let result = serde_json::json!({
            "ltCoin": "ETH3S",
            "ltOrderStatus": "2",
            "quantity": "50",
            "execAmt": "428.35",
            "ltOrderId": "lt-redeem-001"
        });
        let redeem = parse_redeem_result(&result).unwrap();
        assert_eq!(redeem.lt_coin, "ETH3S");
        assert_eq!(redeem.lt_order_status, "2");
        assert!((redeem.quantity - 50.0).abs() < 1e-10);
        assert!((redeem.exec_amt - 428.35).abs() < 1e-10);
        assert_eq!(redeem.lt_order_id, "lt-redeem-001");
    }

    // -- Serde round-trip tests / 序列化往返測試 --

    #[test]
    fn test_leverage_token_info_serde() {
        let info = LeverageTokenInfo {
            lt_coin: "BTC3L".to_string(),
            lt_name: "BTC 3x Long".to_string(),
            max_purchase: 50000.0,
            min_purchase: 10.0,
            max_purchase_daily: 200000.0,
            max_redeem: 50000.0,
            min_redeem: 10.0,
            max_redeem_daily: 200000.0,
            purchase_fee_rate: 0.0005,
            redeem_fee_rate: 0.0005,
            lt_status: "1".to_string(),
            fund_fee: 0.0001,
            fund_fee_time: "1700000000000".to_string(),
        };
        let json = serde_json::to_string(&info).unwrap();
        let deser: LeverageTokenInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.lt_coin, "BTC3L");
        assert!((deser.max_purchase - 50000.0).abs() < 1e-10);
    }

    #[test]
    fn test_leverage_token_reference_serde() {
        let reference = LeverageTokenReference {
            lt_coin: "BTC3L".to_string(),
            nav: 15.234,
            circulation: 1000000.0,
            basket: 15234000.0,
            leverage: 3.0,
            nav_time: "1700000000000".to_string(),
        };
        let json = serde_json::to_string(&reference).unwrap();
        let deser: LeverageTokenReference = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.lt_coin, "BTC3L");
        assert!((deser.nav - 15.234).abs() < 1e-10);
    }

    #[test]
    fn test_lt_purchase_result_serde() {
        let result = LtPurchaseResult {
            lt_coin: "BTC3L".to_string(),
            lt_order_status: "2".to_string(),
            exec_qty: 100.0,
            exec_amt: 1523.40,
            lt_order_id: "lt-001".to_string(),
        };
        let json = serde_json::to_string(&result).unwrap();
        let deser: LtPurchaseResult = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.lt_coin, "BTC3L");
        assert!((deser.exec_qty - 100.0).abs() < 1e-10);
    }

    #[test]
    fn test_lt_redeem_result_serde() {
        let result = LtRedeemResult {
            lt_coin: "ETH3S".to_string(),
            lt_order_status: "2".to_string(),
            quantity: 50.0,
            exec_amt: 428.35,
            lt_order_id: "lt-002".to_string(),
        };
        let json = serde_json::to_string(&result).unwrap();
        let deser: LtRedeemResult = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.lt_coin, "ETH3S");
        assert!((deser.quantity - 50.0).abs() < 1e-10);
    }
}

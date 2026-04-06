//! Bybit V5 batch order manager — batch place/amend/cancel up to 10 orders (R-05).
//! Bybit V5 批量訂單管理器 — 批量下單/修改/取消最多 10 個訂單。
//!
//! MODULE_NOTE (EN): Manages batch order operations on Bybit V5: create up to 10 orders,
//!   amend up to 10 orders, cancel up to 10 orders in a single API call.
//!   Reuses CreateOrderRequest and AmendOrderRequest from order_manager.
//!   All methods are async and use Arc<BybitRestClient> for thread-safe sharing.
//! MODULE_NOTE (中): 管理 Bybit V5 上的批量訂單操作：單次 API 調用中創建最多 10 個訂單、
//!   修改最多 10 個訂單、取消最多 10 個訂單。
//!   復用 order_manager 中的 CreateOrderRequest 和 AmendOrderRequest。
//!   所有方法為異步，使用 Arc<BybitRestClient> 線程安全共享。

use crate::bybit_rest_client::{BybitApiError, BybitRestClient, BybitResult};
use crate::order_manager::{AmendOrderRequest, CreateOrderRequest, OrderCategory, OrderType};
use std::sync::Arc;
use tracing::info;

// ---------------------------------------------------------------------------
// Constants / 常量
// ---------------------------------------------------------------------------

/// Maximum orders per batch call (Bybit limit).
/// 每次批量調用的最大訂單數（Bybit 限制）。
const MAX_BATCH_SIZE: usize = 10;

// ---------------------------------------------------------------------------
// Batch response structs / 批量回應結構
// ---------------------------------------------------------------------------

/// Result for a single order within a batch operation.
/// 批量操作中單個訂單的結果。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct BatchOrderResult {
    /// Bybit-assigned order ID / Bybit 分配的訂單 ID
    pub order_id: String,
    /// Client-assigned order link ID / 客戶端分配的訂單連結 ID
    pub order_link_id: String,
    /// Return code for this specific order (0 = success)
    /// 此訂單的返回碼（0 = 成功）
    pub ret_code: i64,
    /// Return message for this specific order / 此訂單的返回消息
    pub ret_msg: String,
}

/// Response from a batch order operation.
/// 批量訂單操作的回應。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct BatchOrderResponse {
    /// Results for each order in the batch / 批量中每個訂單的結果
    pub results: Vec<BatchOrderResult>,
    /// Number of successfully processed orders / 成功處理的訂單數
    pub success_count: usize,
    /// Number of failed orders / 失敗的訂單數
    pub fail_count: usize,
}

/// Request to cancel a single order within a batch.
/// 批量取消中單個訂單的請求。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CancelOrderItem {
    /// Trading pair / 交易對
    pub symbol: String,
    /// Bybit order ID (one of order_id or order_link_id required)
    /// Bybit 訂單 ID（order_id 或 order_link_id 至少填一個）
    pub order_id: Option<String>,
    /// Client order ID / 客戶端訂單 ID
    pub order_link_id: Option<String>,
}

// ---------------------------------------------------------------------------
// BatchOrderManager / 批量訂單管理器
// ---------------------------------------------------------------------------

/// Manages batch order operations on Bybit V5 (up to 10 per call).
/// 管理 Bybit V5 上的批量訂單操作（每次最多 10 個）。
///
/// Thread-safe: uses Arc<BybitRestClient>.
/// 線程安全：使用 Arc<BybitRestClient>。
pub struct BatchOrderManager {
    /// Shared REST client / 共享 REST 客戶端
    client: Arc<BybitRestClient>,
}

impl BatchOrderManager {
    /// Create a new BatchOrderManager.
    /// 創建新的批量訂單管理器。
    pub fn new(client: Arc<BybitRestClient>) -> Self {
        Self { client }
    }

    // -----------------------------------------------------------------------
    // Batch place / 批量下單
    // -----------------------------------------------------------------------

    /// Place up to 10 orders in a single batch call.
    /// 單次批量調用中下最多 10 個訂單。
    ///
    /// POST /v5/order/create-batch
    ///
    /// All orders must belong to the same category.
    /// 所有訂單必須屬於同一品類。
    pub async fn batch_place(
        &self,
        category: OrderCategory,
        orders: Vec<CreateOrderRequest>,
    ) -> BybitResult<BatchOrderResponse> {
        if orders.is_empty() {
            return Ok(BatchOrderResponse {
                results: vec![],
                success_count: 0,
                fail_count: 0,
            });
        }
        if orders.len() > MAX_BATCH_SIZE {
            return Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: format!(
                    "Batch size {} exceeds max {} / 批量大小 {} 超過最大 {}",
                    orders.len(),
                    MAX_BATCH_SIZE,
                    orders.len(),
                    MAX_BATCH_SIZE
                ),
                response: serde_json::json!(null),
            });
        }

        let request_items: Vec<serde_json::Value> = orders
            .iter()
            .map(|req| {
                let mut item = serde_json::json!({
                    "symbol": req.symbol,
                    "side": req.side.as_str(),
                    "orderType": req.order_type.as_str(),
                    "qty": format_qty(req.qty),
                });
                if let Some(p) = req.price {
                    item["price"] = serde_json::Value::String(format_price(p));
                }
                if let Some(ref tif) = req.time_in_force {
                    item["timeInForce"] = serde_json::Value::String(tif.as_str().to_string());
                } else if req.order_type == OrderType::Limit {
                    item["timeInForce"] = serde_json::Value::String("GTC".to_string());
                }
                if let Some(ro) = req.reduce_only {
                    item["reduceOnly"] = serde_json::Value::Bool(ro);
                }
                if let Some(ref link_id) = req.order_link_id {
                    item["orderLinkId"] = serde_json::Value::String(link_id.clone());
                }
                if let Some(tp) = req.take_profit {
                    item["takeProfit"] = serde_json::Value::String(format_price(tp));
                }
                if let Some(sl) = req.stop_loss {
                    item["stopLoss"] = serde_json::Value::String(format_price(sl));
                }
                item
            })
            .collect();

        let body = serde_json::json!({
            "category": category.as_str(),
            "request": request_items,
        });

        info!(
            category = category.as_str(),
            count = orders.len(),
            "batch placing orders / 批量下單"
        );

        let resp = self
            .client
            .post_checked("/v5/order/create-batch", &body)
            .await?;
        parse_batch_response(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Batch amend / 批量修改
    // -----------------------------------------------------------------------

    /// Amend up to 10 orders in a single batch call.
    /// 單次批量調用中修改最多 10 個訂單。
    ///
    /// POST /v5/order/amend-batch
    ///
    /// All orders must belong to the same category.
    /// 所有訂單必須屬於同一品類。
    pub async fn batch_amend(
        &self,
        category: OrderCategory,
        amends: Vec<AmendOrderRequest>,
    ) -> BybitResult<BatchOrderResponse> {
        if amends.is_empty() {
            return Ok(BatchOrderResponse {
                results: vec![],
                success_count: 0,
                fail_count: 0,
            });
        }
        if amends.len() > MAX_BATCH_SIZE {
            return Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: format!(
                    "Batch size {} exceeds max {} / 批量大小 {} 超過最大 {}",
                    amends.len(),
                    MAX_BATCH_SIZE,
                    amends.len(),
                    MAX_BATCH_SIZE
                ),
                response: serde_json::json!(null),
            });
        }

        let request_items: Vec<serde_json::Value> = amends
            .iter()
            .map(|req| {
                let mut item = serde_json::json!({
                    "symbol": req.symbol,
                });
                if let Some(ref oid) = req.order_id {
                    item["orderId"] = serde_json::Value::String(oid.clone());
                }
                if let Some(ref link_id) = req.order_link_id {
                    item["orderLinkId"] = serde_json::Value::String(link_id.clone());
                }
                if let Some(q) = req.qty {
                    item["qty"] = serde_json::Value::String(format_qty(q));
                }
                if let Some(p) = req.price {
                    item["price"] = serde_json::Value::String(format_price(p));
                }
                if let Some(tp) = req.trigger_price {
                    item["triggerPrice"] = serde_json::Value::String(format_price(tp));
                }
                if let Some(tp) = req.take_profit {
                    item["takeProfit"] = serde_json::Value::String(format_price(tp));
                }
                if let Some(sl) = req.stop_loss {
                    item["stopLoss"] = serde_json::Value::String(format_price(sl));
                }
                item
            })
            .collect();

        let body = serde_json::json!({
            "category": category.as_str(),
            "request": request_items,
        });

        info!(
            category = category.as_str(),
            count = amends.len(),
            "batch amending orders / 批量修改訂單"
        );

        let resp = self
            .client
            .post_checked("/v5/order/amend-batch", &body)
            .await?;
        parse_batch_response(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Batch cancel / 批量取消
    // -----------------------------------------------------------------------

    /// Cancel up to 10 orders in a single batch call.
    /// 單次批量調用中取消最多 10 個訂單。
    ///
    /// POST /v5/order/cancel-batch
    ///
    /// All orders must belong to the same category.
    /// 所有訂單必須屬於同一品類。
    pub async fn batch_cancel(
        &self,
        category: OrderCategory,
        cancels: Vec<CancelOrderItem>,
    ) -> BybitResult<BatchOrderResponse> {
        if cancels.is_empty() {
            return Ok(BatchOrderResponse {
                results: vec![],
                success_count: 0,
                fail_count: 0,
            });
        }
        if cancels.len() > MAX_BATCH_SIZE {
            return Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: format!(
                    "Batch size {} exceeds max {} / 批量大小 {} 超過最大 {}",
                    cancels.len(),
                    MAX_BATCH_SIZE,
                    cancels.len(),
                    MAX_BATCH_SIZE
                ),
                response: serde_json::json!(null),
            });
        }

        let request_items: Vec<serde_json::Value> = cancels
            .iter()
            .map(|item| {
                let mut obj = serde_json::json!({
                    "symbol": item.symbol,
                });
                if let Some(ref oid) = item.order_id {
                    obj["orderId"] = serde_json::Value::String(oid.clone());
                }
                if let Some(ref link_id) = item.order_link_id {
                    obj["orderLinkId"] = serde_json::Value::String(link_id.clone());
                }
                obj
            })
            .collect();

        let body = serde_json::json!({
            "category": category.as_str(),
            "request": request_items,
        });

        info!(
            category = category.as_str(),
            count = cancels.len(),
            "batch cancelling orders / 批量取消訂單"
        );

        let resp = self
            .client
            .post_checked("/v5/order/cancel-batch", &body)
            .await?;
        parse_batch_response(&resp.result)
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse batch order response from Bybit result JSON.
/// 從 Bybit 結果 JSON 解析批量訂單回應。
///
/// Bybit batch response format:
///   { "list": [{ "orderId": "...", "orderLinkId": "..." }],
///     "retExtInfo": { "list": [{ "code": 0, "msg": "OK" }] } }
fn parse_batch_response(result: &serde_json::Value) -> BybitResult<BatchOrderResponse> {
    let order_list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let ext_list = result
        .get("retExtInfo")
        .and_then(|v| v.get("list"))
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut results = Vec::with_capacity(order_list.len());
    let mut success_count = 0;
    let mut fail_count = 0;

    for (i, item) in order_list.iter().enumerate() {
        let order_id = item
            .get("orderId")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        let order_link_id = item
            .get("orderLinkId")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();

        // Get per-order error info from retExtInfo / 從 retExtInfo 取得每訂單錯誤信息
        let (ret_code, ret_msg) = if let Some(ext) = ext_list.get(i) {
            let code = ext.get("code").and_then(|v| v.as_i64()).unwrap_or(0);
            let msg = ext
                .get("msg")
                .and_then(|v| v.as_str())
                .unwrap_or("OK")
                .to_string();
            (code, msg)
        } else {
            (0, "OK".to_string())
        };

        if ret_code == 0 {
            success_count += 1;
        } else {
            fail_count += 1;
        }

        results.push(BatchOrderResult {
            order_id,
            order_link_id,
            ret_code,
            ret_msg,
        });
    }

    Ok(BatchOrderResponse {
        results,
        success_count,
        fail_count,
    })
}

// ---------------------------------------------------------------------------
// Format helpers / 格式化輔助函數
// ---------------------------------------------------------------------------

/// Format qty as a string (no trailing zeros) / 格式化 qty 為字串（無尾零）
fn format_qty(qty: f64) -> String {
    let s = format!("{:.8}", qty);
    let trimmed = s.trim_end_matches('0').trim_end_matches('.');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}

/// Format price as a string (no trailing zeros) / 格式化 price 為字串（無尾零）
fn format_price(price: f64) -> String {
    let s = format!("{:.8}", price);
    let trimmed = s.trim_end_matches('0').trim_end_matches('.');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_batch_response_success() {
        let result = serde_json::json!({
            "list": [
                {"orderId": "ord-001", "orderLinkId": "link-001"},
                {"orderId": "ord-002", "orderLinkId": "link-002"}
            ],
            "retExtInfo": {
                "list": [
                    {"code": 0, "msg": "OK"},
                    {"code": 0, "msg": "OK"}
                ]
            }
        });
        let resp = parse_batch_response(&result).unwrap();
        assert_eq!(resp.results.len(), 2);
        assert_eq!(resp.success_count, 2);
        assert_eq!(resp.fail_count, 0);
        assert_eq!(resp.results[0].order_id, "ord-001");
        assert_eq!(resp.results[0].order_link_id, "link-001");
        assert_eq!(resp.results[0].ret_code, 0);
    }

    #[test]
    fn test_parse_batch_response_partial_fail() {
        let result = serde_json::json!({
            "list": [
                {"orderId": "ord-001", "orderLinkId": "link-001"},
                {"orderId": "", "orderLinkId": "link-002"}
            ],
            "retExtInfo": {
                "list": [
                    {"code": 0, "msg": "OK"},
                    {"code": 110001, "msg": "insufficient balance"}
                ]
            }
        });
        let resp = parse_batch_response(&result).unwrap();
        assert_eq!(resp.results.len(), 2);
        assert_eq!(resp.success_count, 1);
        assert_eq!(resp.fail_count, 1);
        assert_eq!(resp.results[1].ret_code, 110001);
        assert_eq!(resp.results[1].ret_msg, "insufficient balance");
    }

    #[test]
    fn test_parse_batch_response_empty() {
        let result = serde_json::json!({"list": [], "retExtInfo": {"list": []}});
        let resp = parse_batch_response(&result).unwrap();
        assert_eq!(resp.results.len(), 0);
        assert_eq!(resp.success_count, 0);
        assert_eq!(resp.fail_count, 0);
    }

    #[test]
    fn test_parse_batch_response_missing_ext() {
        let result = serde_json::json!({
            "list": [{"orderId": "ord-001", "orderLinkId": ""}]
        });
        let resp = parse_batch_response(&result).unwrap();
        assert_eq!(resp.results.len(), 1);
        assert_eq!(resp.results[0].ret_code, 0); // default success
        assert_eq!(resp.success_count, 1);
    }

    #[test]
    fn test_batch_order_result_serde() {
        let result = BatchOrderResult {
            order_id: "ord-123".to_string(),
            order_link_id: "link-456".to_string(),
            ret_code: 0,
            ret_msg: "OK".to_string(),
        };
        let json = serde_json::to_string(&result).unwrap();
        let deser: BatchOrderResult = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.order_id, "ord-123");
        assert_eq!(deser.ret_code, 0);
    }

    #[test]
    fn test_batch_order_response_serde() {
        let resp = BatchOrderResponse {
            results: vec![BatchOrderResult {
                order_id: "o1".to_string(),
                order_link_id: "l1".to_string(),
                ret_code: 0,
                ret_msg: "OK".to_string(),
            }],
            success_count: 1,
            fail_count: 0,
        };
        let json = serde_json::to_string(&resp).unwrap();
        let deser: BatchOrderResponse = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.results.len(), 1);
        assert_eq!(deser.success_count, 1);
    }

    #[test]
    fn test_cancel_order_item_serde() {
        let item = CancelOrderItem {
            symbol: "BTCUSDT".to_string(),
            order_id: Some("ord-001".to_string()),
            order_link_id: None,
        };
        let json = serde_json::to_string(&item).unwrap();
        let deser: CancelOrderItem = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.symbol, "BTCUSDT");
        assert_eq!(deser.order_id, Some("ord-001".to_string()));
        assert!(deser.order_link_id.is_none());
    }

    #[test]
    fn test_format_qty() {
        assert_eq!(format_qty(0.01), "0.01");
        assert_eq!(format_qty(1.0), "1");
        assert_eq!(format_qty(0.00100000), "0.001");
        assert_eq!(format_qty(100.0), "100");
    }

    #[test]
    fn test_format_price() {
        assert_eq!(format_price(65000.50), "65000.5");
        assert_eq!(format_price(65000.0), "65000");
        assert_eq!(format_price(0.00012345), "0.00012345");
    }

    #[test]
    fn test_max_batch_size_constant() {
        assert_eq!(MAX_BATCH_SIZE, 10);
    }
}

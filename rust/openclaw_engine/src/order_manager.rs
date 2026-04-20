//! Bybit V5 order manager — full order lifecycle (R-05 exchange infra).
//! Bybit V5 訂單管理器 — 完整訂單生命週期。
//!
//! MODULE_NOTE (EN): Manages the complete order lifecycle on Bybit V5: create, amend,
//!   cancel, query active/history, and fetch executions. Validates orders against
//!   InstrumentInfoCache before submission (qty/price precision, min notional).
//!   Supports all Bybit order types: market, limit, conditional, TP/SL on order.
//!   All methods are async and use Arc<BybitRestClient> for thread-safe sharing.
//! MODULE_NOTE (中): 管理 Bybit V5 上的完整訂單生命週期：創建、修改、取消、查詢
//!   活躍/歷史訂單、獲取成交記錄。提交前通過 InstrumentInfoCache 驗證訂單
//!   （qty/price 精度、最小名義值）。支持所有 Bybit 訂單類型：市價、限價、
//!   條件單、訂單附帶 TP/SL。所有方法為異步，使用 Arc<BybitRestClient> 線程安全共享。

use crate::bybit_rest_client::{BybitApiError, BybitRestClient, BybitResult};
use crate::instrument_info::InstrumentInfoCache;
use std::sync::Arc;
use tracing::{debug, info};

// ---------------------------------------------------------------------------
// Enums / 枚舉
// ---------------------------------------------------------------------------

/// Order side: Buy or Sell.
/// 訂單方向：買入或賣出。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum OrderSide {
    Buy,
    Sell,
}

impl OrderSide {
    /// Convert to Bybit API string / 轉換為 Bybit API 字串
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Buy => "Buy",
            Self::Sell => "Sell",
        }
    }
}

/// Order type: Market or Limit.
/// 訂單類型：市價或限價。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum OrderType {
    Market,
    Limit,
}

impl OrderType {
    /// Convert to Bybit API string / 轉換為 Bybit API 字串
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Market => "Market",
            Self::Limit => "Limit",
        }
    }
}

/// Time-in-force for limit orders.
/// 限價訂單的有效期類型。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum TimeInForce {
    /// Good Till Cancelled / 撤銷前有效
    GTC,
    /// Immediate Or Cancel / 立即成交或取消
    IOC,
    /// Fill Or Kill / 全部成交或取消
    FOK,
    /// Post Only (maker only) / 只做 Maker
    PostOnly,
}

impl TimeInForce {
    /// Convert to Bybit API string / 轉換為 Bybit API 字串
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::GTC => "GTC",
            Self::IOC => "IOC",
            Self::FOK => "FOK",
            Self::PostOnly => "PostOnly",
        }
    }
}

/// Trigger direction for conditional orders.
/// 條件單的觸發方向。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum TriggerDirection {
    /// Trigger when price rises to trigger_price / 價格上漲到觸發價時觸發
    Rise = 1,
    /// Trigger when price falls to trigger_price / 價格下跌到觸發價時觸發
    Fall = 2,
}

/// Order category (Bybit product type).
/// 訂單品類（Bybit 產品類型）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub enum OrderCategory {
    Linear,
    Spot,
    Inverse,
}

impl OrderCategory {
    /// Convert to Bybit API string / 轉換為 Bybit API 字串
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Linear => "linear",
            Self::Spot => "spot",
            Self::Inverse => "inverse",
        }
    }
}

// ---------------------------------------------------------------------------
// Request / Response structs / 請求/回應結構
// ---------------------------------------------------------------------------

/// Request to create a new order on Bybit V5.
/// 在 Bybit V5 上創建新訂單的請求。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CreateOrderRequest {
    /// Product category / 產品品類
    pub category: OrderCategory,
    /// Trading pair, e.g. "BTCUSDT" / 交易對
    pub symbol: String,
    /// Buy or Sell / 買入或賣出
    pub side: OrderSide,
    /// Market or Limit / 市價或限價
    pub order_type: OrderType,
    /// Order quantity / 訂單數量
    pub qty: f64,
    /// Limit price (required for Limit orders) / 限價（限價單必填）
    pub price: Option<f64>,
    /// Time-in-force (default GTC for limit) / 有效期類型
    pub time_in_force: Option<TimeInForce>,
    /// Reduce-only flag / 只減倉標記
    pub reduce_only: Option<bool>,
    /// Close on trigger flag / 觸發後平倉標記
    pub close_on_trigger: Option<bool>,
    /// Client order ID for idempotency / 客戶端訂單 ID（冪等）
    pub order_link_id: Option<String>,
    // -- Conditional order fields / 條件單欄位 --
    /// Trigger price for conditional orders / 條件單觸發價
    pub trigger_price: Option<f64>,
    /// Trigger direction (Rise or Fall) / 觸發方向
    pub trigger_direction: Option<TriggerDirection>,
    // -- TP/SL on order / 訂單附帶止盈止損 --
    /// Take profit price / 止盈價
    pub take_profit: Option<f64>,
    /// Stop loss price / 止損價
    pub stop_loss: Option<f64>,
    /// TP trigger by: "LastPrice" | "MarkPrice" / 止盈觸發依據
    pub tp_trigger_by: Option<String>,
    /// SL trigger by: "LastPrice" | "MarkPrice" / 止損觸發依據
    pub sl_trigger_by: Option<String>,
}

/// Request to amend (modify) an existing order.
/// 修改現有訂單的請求。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AmendOrderRequest {
    /// Product category / 產品品類
    pub category: OrderCategory,
    /// Trading pair / 交易對
    pub symbol: String,
    /// Bybit order ID (one of order_id or order_link_id required)
    /// Bybit 訂單 ID（order_id 或 order_link_id 至少填一個）
    pub order_id: Option<String>,
    /// Client order ID / 客戶端訂單 ID
    pub order_link_id: Option<String>,
    /// New quantity / 新數量
    pub qty: Option<f64>,
    /// New price / 新價格
    pub price: Option<f64>,
    /// New trigger price / 新觸發價
    pub trigger_price: Option<f64>,
    /// New take profit / 新止盈價
    pub take_profit: Option<f64>,
    /// New stop loss / 新止損價
    pub stop_loss: Option<f64>,
}

/// Response from order create/cancel/amend operations.
/// 訂單創建/取消/修改操作的回應。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct OrderResponse {
    /// Bybit-assigned order ID / Bybit 分配的訂單 ID
    pub order_id: String,
    /// Client-assigned order link ID / 客戶端分配的訂單連結 ID
    pub order_link_id: String,
}

/// Detailed order information from queries.
/// 查詢返回的詳細訂單信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct OrderInfo {
    /// Bybit order ID / Bybit 訂單 ID
    pub order_id: String,
    /// Client order link ID / 客戶端訂單連結 ID
    pub order_link_id: String,
    /// Trading pair / 交易對
    pub symbol: String,
    /// Side: "Buy" | "Sell" / 方向
    pub side: String,
    /// Order type: "Market" | "Limit" / 訂單類型
    pub order_type: String,
    /// Order price (0.0 for conditional market orders) / 訂單價格（條件市價單為 0.0）
    pub price: f64,
    /// Trigger price for conditional orders (stop-loss/take-profit).
    /// 條件單觸發價（止損/止盈）。
    pub trigger_price: f64,
    /// Order quantity / 訂單數量
    pub qty: f64,
    /// Cumulative executed quantity / 累計成交數量
    pub cum_exec_qty: f64,
    /// Cumulative executed value / 累計成交金額
    pub cum_exec_value: f64,
    /// Average fill price / 平均成交價
    pub avg_price: f64,
    /// Order status: "New", "PartiallyFilled", "Filled", "Cancelled", etc.
    /// 訂單狀態
    pub order_status: String,
    /// Creation timestamp / 創建時間戳
    pub created_time: String,
    /// Last update timestamp / 最後更新時間戳
    pub updated_time: String,
}

/// Execution (fill) information.
/// 成交記錄信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ExecutionInfo {
    /// Execution ID / 成交 ID
    pub exec_id: String,
    /// Trading pair / 交易對
    pub symbol: String,
    /// Side: "Buy" | "Sell" / 方向
    pub side: String,
    /// Execution price / 成交價格
    pub exec_price: f64,
    /// Execution quantity / 成交數量
    pub exec_qty: f64,
    /// Execution value (price * qty) / 成交金額
    pub exec_value: f64,
    /// Execution fee / 成交手續費
    pub exec_fee: f64,
    /// Fee currency / 手續費幣種
    pub fee_currency: String,
    /// Order ID / 訂單 ID
    pub order_id: String,
    /// Order link ID / 客戶端訂單 ID
    pub order_link_id: String,
    /// Execution type: "Trade", "Funding", etc. / 成交類型
    pub exec_type: String,
    /// Execution timestamp / 成交時間戳
    pub exec_time: String,
    /// Realized PnL reported by Bybit on this fill. "0" for opens, non-zero
    /// for closes (reduce_only). Required by GUI to colour the P&L column.
    /// Bybit 在此筆成交回傳的已實現盈虧；開倉為 0，平倉（reduce_only）非 0。
    pub closed_pnl: f64,
}

// ---------------------------------------------------------------------------
// OrderManager / 訂單管理器
// ---------------------------------------------------------------------------

/// 1B-5 FUP-3: shared cancel-by-orderLinkId REST helper. The canonical
/// implementation of `POST /v5/order/cancel { category, symbol, orderLinkId }`.
/// Both `OrderManager::cancel_order_by_link_id` (typed caller for `create →
/// cancel` flows) and the `event_consumer` non-blocking PostOnly maker timeout
/// sweep route through this function so the Bybit endpoint / body shape /
/// log fields stay single-sourced. Instruments cache is not needed — cancel
/// does not validate qty / price.
///
/// 1B-5 FUP-3：共用的 orderLinkId 取消 REST 輔助函數。 `POST /v5/order/cancel
/// { category, symbol, orderLinkId }` 的唯一實作點，`OrderManager::
/// cancel_order_by_link_id` 與 `event_consumer` 的非阻塞 PostOnly 掛單超時
/// sweep 皆走此處，維持 endpoint / body / 日誌欄位單一來源。取消不需 instruments。
pub(crate) async fn cancel_by_link_id_raw(
    client: &BybitRestClient,
    category: OrderCategory,
    symbol: &str,
    order_link_id: &str,
) -> BybitResult<OrderResponse> {
    let body = serde_json::json!({
        "category": category.as_str(),
        "symbol": symbol,
        "orderLinkId": order_link_id,
    });

    info!(
        symbol = symbol,
        order_link_id = order_link_id,
        "cancelling order by link id / 通過 link id 取消訂單"
    );

    let resp = client.post_checked("/v5/order/cancel", &body).await?;
    parse_order_response(&resp.result)
}

/// Manages order lifecycle on Bybit V5.
/// 管理 Bybit V5 上的訂單生命週期。
///
/// Thread-safe: uses Arc for shared client and instrument cache.
/// 線程安全：使用 Arc 共享客戶端和合約信息緩存。
pub struct OrderManager {
    /// Shared REST client / 共享 REST 客戶端
    client: Arc<BybitRestClient>,
    /// Shared instrument info cache for validation / 共享合約信息緩存用於驗證
    instruments: Arc<InstrumentInfoCache>,
}

impl OrderManager {
    /// Create a new OrderManager.
    /// 創建新的訂單管理器。
    pub fn new(client: Arc<BybitRestClient>, instruments: Arc<InstrumentInfoCache>) -> Self {
        Self {
            client,
            instruments,
        }
    }

    // -----------------------------------------------------------------------
    // Place order / 下單
    // -----------------------------------------------------------------------

    /// Place a new order on Bybit V5.
    /// 在 Bybit V5 上下新訂單。
    ///
    /// Validates qty/price against InstrumentInfoCache before sending.
    /// Pre-rounds qty and price to exchange precision.
    /// 發送前通過 InstrumentInfoCache 驗證並取整 qty/price。
    ///
    /// POST /v5/order/create
    pub async fn place_order(&self, req: CreateOrderRequest) -> BybitResult<OrderResponse> {
        // --- Pre-validation via instrument cache / 通過合約信息緩存預驗證 ---
        let (qty, price) = self.validate_and_round(&req)?;

        // --- Build JSON body / 構建 JSON body ---
        let mut body = serde_json::json!({
            "category": req.category.as_str(),
            "symbol": req.symbol,
            "side": req.side.as_str(),
            "orderType": req.order_type.as_str(),
            "qty": format_qty(qty),
        });

        // Limit order requires price / 限價單需要價格
        if let Some(p) = price {
            body["price"] = serde_json::Value::String(format_price(p));
        }

        // Time-in-force: default GTC for Limit, IOC for Market
        // 有效期：限價默認 GTC，市價默認 IOC
        if let Some(tif) = &req.time_in_force {
            body["timeInForce"] = serde_json::Value::String(tif.as_str().to_string());
        } else if req.order_type == OrderType::Limit {
            body["timeInForce"] = serde_json::Value::String("GTC".to_string());
        }

        // Optional fields / 可選欄位
        if let Some(ro) = req.reduce_only {
            body["reduceOnly"] = serde_json::Value::Bool(ro);
        }
        if let Some(cot) = req.close_on_trigger {
            body["closeOnTrigger"] = serde_json::Value::Bool(cot);
        }
        if let Some(ref link_id) = req.order_link_id {
            body["orderLinkId"] = serde_json::Value::String(link_id.clone());
        }

        // Conditional order fields / 條件單欄位
        if let Some(tp) = req.trigger_price {
            body["triggerPrice"] = serde_json::Value::String(format_price(tp));
        }
        if let Some(dir) = req.trigger_direction {
            body["triggerDirection"] =
                serde_json::Value::Number(serde_json::Number::from(dir as i32));
        }

        // TP/SL on order / 訂單附帶止盈止損
        if let Some(tp) = req.take_profit {
            body["takeProfit"] = serde_json::Value::String(format_price(tp));
        }
        if let Some(sl) = req.stop_loss {
            body["stopLoss"] = serde_json::Value::String(format_price(sl));
        }
        if let Some(ref tptb) = req.tp_trigger_by {
            body["tpTriggerBy"] = serde_json::Value::String(tptb.clone());
        }
        if let Some(ref sltb) = req.sl_trigger_by {
            body["slTriggerBy"] = serde_json::Value::String(sltb.clone());
        }

        info!(
            symbol = req.symbol.as_str(),
            side = req.side.as_str(),
            order_type = req.order_type.as_str(),
            qty = qty,
            "placing order / 下單"
        );

        let resp = self.client.post_checked("/v5/order/create", &body).await?;
        parse_order_response(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Cancel order / 取消訂單
    // -----------------------------------------------------------------------

    /// Cancel a single order by order ID.
    /// 通過訂單 ID 取消單個訂單。
    ///
    /// POST /v5/order/cancel
    pub async fn cancel_order(
        &self,
        category: OrderCategory,
        symbol: &str,
        order_id: &str,
    ) -> BybitResult<OrderResponse> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
            "orderId": order_id,
        });

        info!(
            symbol = symbol,
            order_id = order_id,
            "cancelling order / 取消訂單"
        );

        let resp = self.client.post_checked("/v5/order/cancel", &body).await?;
        parse_order_response(&resp.result)
    }

    /// Cancel a single order by client-minted `orderLinkId`.
    /// 通過客戶端自訂的 orderLinkId 取消單個訂單。
    ///
    /// Bybit V5 natively accepts either `orderId` or `orderLinkId` on the
    /// cancel endpoint. Using orderLinkId is the idempotency-safe path for
    /// resting PostOnly maker orders because the client mint survives restart
    /// and WS lag, while orderId is only known after the REST create round-trip.
    ///
    /// Bybit V5 的取消端點原生同時接受 orderId 或 orderLinkId。對於 PostOnly
    /// 掛單採用 orderLinkId 取消是冪等安全路徑——客戶端鑄造的 id 可跨重啟/WS
    /// 延遲存活，而 orderId 必須等 REST 下單回傳後才知道。
    ///
    /// 1B-5 FUP-3: delegates the actual REST path + body construction to
    /// `cancel_by_link_id_raw` so other call sites (e.g. the non-blocking
    /// maker timeout cancel spawned from event_consumer) share one endpoint
    /// definition and do not drift apart on category / body shape.
    /// 1B-5 FUP-3：實際 REST 呼叫委託到 `cancel_by_link_id_raw`，使其他呼叫點
    /// （如 event_consumer 非阻塞掛單超時取消）共用單一端點定義，避免發散。
    ///
    /// POST /v5/order/cancel
    pub async fn cancel_order_by_link_id(
        &self,
        category: OrderCategory,
        symbol: &str,
        order_link_id: &str,
    ) -> BybitResult<OrderResponse> {
        cancel_by_link_id_raw(&self.client, category, symbol, order_link_id).await
    }

    /// Cancel all active orders for a symbol.
    /// 取消某交易對的所有活躍訂單。
    ///
    /// POST /v5/order/cancel-all
    pub async fn cancel_all(
        &self,
        category: OrderCategory,
        symbol: &str,
    ) -> BybitResult<Vec<OrderResponse>> {
        let body = serde_json::json!({
            "category": category.as_str(),
            "symbol": symbol,
        });

        info!(symbol = symbol, "cancelling all orders / 取消所有訂單");

        let resp = self
            .client
            .post_checked("/v5/order/cancel-all", &body)
            .await?;
        parse_order_response_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Amend order / 修改訂單
    // -----------------------------------------------------------------------

    /// Amend (modify) an existing order's price, qty, TP/SL, or trigger price.
    /// 修改現有訂單的價格、數量、止盈止損或觸發價。
    ///
    /// POST /v5/order/amend
    pub async fn amend_order(&self, req: AmendOrderRequest) -> BybitResult<OrderResponse> {
        if req.order_id.is_none() && req.order_link_id.is_none() {
            return Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: "amend_order requires order_id or order_link_id".to_string(),
                response: serde_json::json!(null),
            });
        }

        let mut body = serde_json::json!({
            "category": req.category.as_str(),
            "symbol": req.symbol,
        });

        if let Some(ref oid) = req.order_id {
            body["orderId"] = serde_json::Value::String(oid.clone());
        }
        if let Some(ref link_id) = req.order_link_id {
            body["orderLinkId"] = serde_json::Value::String(link_id.clone());
        }
        if let Some(q) = req.qty {
            // Round qty if instrument info available / 有合約信息時取整
            let rounded = self.instruments.round_qty(&req.symbol, q).unwrap_or(q);
            body["qty"] = serde_json::Value::String(format_qty(rounded));
        }
        if let Some(p) = req.price {
            let rounded = self.instruments.round_price(&req.symbol, p).unwrap_or(p);
            body["price"] = serde_json::Value::String(format_price(rounded));
        }
        if let Some(tp) = req.trigger_price {
            body["triggerPrice"] = serde_json::Value::String(format_price(tp));
        }
        if let Some(tp) = req.take_profit {
            body["takeProfit"] = serde_json::Value::String(format_price(tp));
        }
        if let Some(sl) = req.stop_loss {
            body["stopLoss"] = serde_json::Value::String(format_price(sl));
        }

        debug!(
            symbol = req.symbol.as_str(),
            order_id = req.order_id.as_deref().unwrap_or(""),
            "amending order / 修改訂單"
        );

        let resp = self.client.post_checked("/v5/order/amend", &body).await?;
        parse_order_response(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Query orders / 查詢訂單
    // -----------------------------------------------------------------------

    /// Get active (open) orders.
    /// 查詢活躍（未完成）訂單。
    ///
    /// GET /v5/order/realtime
    pub async fn get_active_orders(
        &self,
        category: OrderCategory,
        symbol: Option<&str>,
    ) -> BybitResult<Vec<OrderInfo>> {
        let mut params: Vec<(&str, &str)> = vec![("category", category.as_str())];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }

        let resp = self
            .client
            .get_checked("/v5/order/realtime", &params)
            .await?;
        parse_order_info_list(&resp.result)
    }

    /// Get order history.
    /// 查詢歷史訂單。
    ///
    /// GET /v5/order/history
    pub async fn get_order_history(
        &self,
        category: OrderCategory,
        symbol: Option<&str>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<OrderInfo>> {
        let limit_str = limit.unwrap_or(50).to_string();
        let mut params: Vec<(&str, &str)> =
            vec![("category", category.as_str()), ("limit", &limit_str)];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }

        let resp = self
            .client
            .get_checked("/v5/order/history", &params)
            .await?;
        parse_order_info_list(&resp.result)
    }

    /// Get execution (fill) records.
    /// 查詢成交記錄。
    ///
    /// GET /v5/execution/list
    pub async fn get_executions(
        &self,
        category: OrderCategory,
        symbol: Option<&str>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<ExecutionInfo>> {
        let limit_str = limit.unwrap_or(50).to_string();
        let mut params: Vec<(&str, &str)> =
            vec![("category", category.as_str()), ("limit", &limit_str)];
        if let Some(sym) = symbol {
            params.push(("symbol", sym));
        }

        let resp = self
            .client
            .get_checked("/v5/execution/list", &params)
            .await?;
        parse_execution_list(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Internal validation / 內部驗證
    // -----------------------------------------------------------------------

    /// Validate and round qty/price using instrument cache.
    /// 使用合約信息緩存驗證並取整 qty/price。
    ///
    /// Returns (rounded_qty, rounded_price_opt).
    /// 返回 (取整後的 qty, 取整後的 price 或 None)。
    ///
    /// M-1 (2026-04-11) audit fix: fail-closed when spec missing instead of bypassing
    /// rounding/validation. Previously a missing spec silently passed raw qty/price
    /// to Bybit, which then rejected with `retCode=10001 Qty invalid`.
    /// M-1 審計修復：缺少品種規格時 fail-closed，而非繞過取整/驗證。先前缺失規格
    /// 會將原始 qty/price 直接送往 Bybit，導致 `retCode=10001 Qty invalid` 拒絕。
    fn validate_and_round(&self, req: &CreateOrderRequest) -> BybitResult<(f64, Option<f64>)> {
        let spec = self
            .instruments
            .get(&req.symbol)
            .ok_or_else(|| BybitApiError::Business {
                ret_code: -1,
                ret_msg: format!(
                    "instrument spec missing for {} — fail-closed / 缺少品種規格 {} — 拒絕下單",
                    req.symbol, req.symbol
                ),
                response: serde_json::json!(null),
            })?;

        let qty = spec.round_qty(req.qty);

        let price = match (req.order_type, req.price) {
            (OrderType::Limit, Some(p)) => Some(spec.round_price(p)),
            (OrderType::Limit, None) => {
                return Err(BybitApiError::Business {
                    ret_code: -1,
                    ret_msg: "Limit order requires price / 限價單需要價格".to_string(),
                    response: serde_json::json!(null),
                });
            }
            _ => req.price.map(|p| spec.round_price(p)),
        };

        let check_price = price.unwrap_or(0.0);
        let (valid, reason) = spec.validate_order(qty, check_price);
        if !valid {
            return Err(BybitApiError::Business {
                ret_code: -1,
                ret_msg: format!("Order validation failed: {reason} / 訂單驗證失敗：{reason}"),
                response: serde_json::json!(null),
            });
        }

        Ok((qty, price))
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse OrderResponse from Bybit result JSON.
/// 從 Bybit 結果 JSON 解析 OrderResponse。
fn parse_order_response(result: &serde_json::Value) -> BybitResult<OrderResponse> {
    Ok(OrderResponse {
        order_id: result
            .get("orderId")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
        order_link_id: result
            .get("orderLinkId")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string(),
    })
}

/// Parse a list of OrderResponse from cancel-all result.
/// 從 cancel-all 結果解析 OrderResponse 列表。
fn parse_order_response_list(result: &serde_json::Value) -> BybitResult<Vec<OrderResponse>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut responses = Vec::with_capacity(list.len());
    for item in &list {
        responses.push(OrderResponse {
            order_id: item
                .get("orderId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
            order_link_id: item
                .get("orderLinkId")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string(),
        });
    }
    Ok(responses)
}

/// Public wrapper for parse_order_info_list (used by PyO3 bridge).
/// parse_order_info_list 的公開包裝器（供 PyO3 橋接使用）。
pub fn parse_order_info_list_pub(result: &serde_json::Value) -> BybitResult<Vec<OrderInfo>> {
    parse_order_info_list(result)
}

/// Parse a list of OrderInfo from Bybit order query result.
/// 從 Bybit 訂單查詢結果解析 OrderInfo 列表。
fn parse_order_info_list(result: &serde_json::Value) -> BybitResult<Vec<OrderInfo>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut orders = Vec::with_capacity(list.len());
    for item in &list {
        orders.push(parse_order_info_item(item));
    }
    Ok(orders)
}

/// Parse a single OrderInfo item.
/// 解析單個 OrderInfo 項目。
fn parse_order_info_item(item: &serde_json::Value) -> OrderInfo {
    OrderInfo {
        order_id: str_field(item, "orderId"),
        order_link_id: str_field(item, "orderLinkId"),
        symbol: str_field(item, "symbol"),
        side: str_field(item, "side"),
        order_type: str_field(item, "orderType"),
        price: f64_field(item, "price"),
        trigger_price: f64_field(item, "triggerPrice"),
        qty: f64_field(item, "qty"),
        cum_exec_qty: f64_field(item, "cumExecQty"),
        cum_exec_value: f64_field(item, "cumExecValue"),
        avg_price: f64_field(item, "avgPrice"),
        order_status: str_field(item, "orderStatus"),
        created_time: str_field(item, "createdTime"),
        updated_time: str_field(item, "updatedTime"),
    }
}

/// Public wrapper for parse_execution_list (used by PyO3 bridge).
/// parse_execution_list 的公開包裝器（供 PyO3 橋接使用）。
pub fn parse_execution_list_pub(result: &serde_json::Value) -> BybitResult<Vec<ExecutionInfo>> {
    parse_execution_list(result)
}

/// Parse a list of ExecutionInfo from Bybit execution query result.
/// 從 Bybit 成交查詢結果解析 ExecutionInfo 列表。
fn parse_execution_list(result: &serde_json::Value) -> BybitResult<Vec<ExecutionInfo>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut execs = Vec::with_capacity(list.len());
    for item in &list {
        execs.push(ExecutionInfo {
            exec_id: str_field(item, "execId"),
            symbol: str_field(item, "symbol"),
            side: str_field(item, "side"),
            exec_price: f64_field(item, "execPrice"),
            exec_qty: f64_field(item, "execQty"),
            exec_value: f64_field(item, "execValue"),
            exec_fee: f64_field(item, "execFee"),
            fee_currency: str_field(item, "feeCurrency"),
            order_id: str_field(item, "orderId"),
            order_link_id: str_field(item, "orderLinkId"),
            exec_type: str_field(item, "execType"),
            exec_time: str_field(item, "execTime"),
            closed_pnl: f64_field(item, "closedPnl"),
        });
    }
    Ok(execs)
}

// ---------------------------------------------------------------------------
// Field extraction helpers / 欄位提取輔助函數
// ---------------------------------------------------------------------------

/// Extract a string field from JSON, defaulting to "" / 提取字串欄位，默認 ""
fn str_field(obj: &serde_json::Value, field: &str) -> String {
    obj.get(field)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

/// Extract a numeric-string field as f64, defaulting to 0.0 / 提取數字字串欄位為 f64，默認 0.0
fn f64_field(obj: &serde_json::Value, field: &str) -> f64 {
    obj.get(field)
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0)
}

/// Format qty as a string for Bybit API (no trailing zeros).
/// 將 qty 格式化為 Bybit API 字串（無尾零）。
fn format_qty(qty: f64) -> String {
    // Use enough precision then trim / 使用足夠精度後裁剪
    let s = format!("{:.8}", qty);
    let trimmed = s.trim_end_matches('0').trim_end_matches('.');
    if trimmed.is_empty() {
        "0".to_string()
    } else {
        trimmed.to_string()
    }
}

/// Format price as a string for Bybit API (no trailing zeros).
/// 將 price 格式化為 Bybit API 字串（無尾零）。
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
    use crate::instrument_info::{InstrumentInfoCache, SymbolSpec};

    /// Helper: build a sample InstrumentInfoCache with BTCUSDT.
    /// 輔助：構建含 BTCUSDT 的測試合約信息緩存。
    fn sample_cache() -> InstrumentInfoCache {
        let cache = InstrumentInfoCache::new();
        {
            let mut map = cache.cache.write();
            map.insert(
                "BTCUSDT".to_string(),
                SymbolSpec {
                    symbol: "BTCUSDT".to_string(),
                    base_currency: "BTC".to_string(),
                    quote_currency: "USDT".to_string(),
                    contract_type: "LinearPerpetual".to_string(),
                    qty_step: 0.001,
                    min_qty: 0.001,
                    max_qty: 100.0,
                    tick_size: 0.10,
                    min_price: 0.10,
                    max_price: 999999.0,
                    min_notional: 5.0,
                    qty_decimals: 3,
                    price_decimals: 1,
                },
            );
        }
        cache
    }

    // -- Enum serialization tests / 枚舉序列化測試 --

    #[test]
    fn test_order_side_as_str() {
        assert_eq!(OrderSide::Buy.as_str(), "Buy");
        assert_eq!(OrderSide::Sell.as_str(), "Sell");
    }

    #[test]
    fn test_order_type_as_str() {
        assert_eq!(OrderType::Market.as_str(), "Market");
        assert_eq!(OrderType::Limit.as_str(), "Limit");
    }

    #[test]
    fn test_time_in_force_as_str() {
        assert_eq!(TimeInForce::GTC.as_str(), "GTC");
        assert_eq!(TimeInForce::IOC.as_str(), "IOC");
        assert_eq!(TimeInForce::FOK.as_str(), "FOK");
        assert_eq!(TimeInForce::PostOnly.as_str(), "PostOnly");
    }

    #[test]
    fn test_order_category_as_str() {
        assert_eq!(OrderCategory::Linear.as_str(), "linear");
        assert_eq!(OrderCategory::Spot.as_str(), "spot");
        assert_eq!(OrderCategory::Inverse.as_str(), "inverse");
    }

    #[test]
    fn test_trigger_direction_values() {
        assert_eq!(TriggerDirection::Rise as i32, 1);
        assert_eq!(TriggerDirection::Fall as i32, 2);
    }

    // -- Formatting tests / 格式化測試 --

    #[test]
    fn test_format_qty() {
        assert_eq!(format_qty(0.001), "0.001");
        assert_eq!(format_qty(1.0), "1");
        assert_eq!(format_qty(0.10), "0.1");
        assert_eq!(format_qty(123.45600), "123.456");
    }

    #[test]
    fn test_format_price() {
        assert_eq!(format_price(65000.0), "65000");
        assert_eq!(format_price(65000.10), "65000.1");
        assert_eq!(format_price(0.00012345), "0.00012345");
    }

    // -- Response parsing tests / 回應解析測試 --

    #[test]
    fn test_parse_order_response() {
        let result = serde_json::json!({
            "orderId": "1234567890",
            "orderLinkId": "my-custom-id-001"
        });
        let resp = parse_order_response(&result).unwrap();
        assert_eq!(resp.order_id, "1234567890");
        assert_eq!(resp.order_link_id, "my-custom-id-001");
    }

    #[test]
    fn test_parse_order_response_empty() {
        let result = serde_json::json!({});
        let resp = parse_order_response(&result).unwrap();
        assert_eq!(resp.order_id, "");
        assert_eq!(resp.order_link_id, "");
    }

    #[test]
    fn test_parse_order_response_list() {
        let result = serde_json::json!({
            "list": [
                {"orderId": "aaa", "orderLinkId": "link-a"},
                {"orderId": "bbb", "orderLinkId": "link-b"}
            ]
        });
        let list = parse_order_response_list(&result).unwrap();
        assert_eq!(list.len(), 2);
        assert_eq!(list[0].order_id, "aaa");
        assert_eq!(list[1].order_id, "bbb");
    }

    #[test]
    fn test_parse_order_info_list() {
        let result = serde_json::json!({
            "list": [{
                "orderId": "ord-001",
                "orderLinkId": "link-001",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "orderType": "Limit",
                "price": "65000.0",
                "qty": "0.01",
                "cumExecQty": "0.005",
                "cumExecValue": "325.0",
                "avgPrice": "65000.0",
                "orderStatus": "PartiallyFilled",
                "createdTime": "1700000000000",
                "updatedTime": "1700000001000"
            }]
        });
        let orders = parse_order_info_list(&result).unwrap();
        assert_eq!(orders.len(), 1);
        let o = &orders[0];
        assert_eq!(o.order_id, "ord-001");
        assert_eq!(o.symbol, "BTCUSDT");
        assert_eq!(o.side, "Buy");
        assert!((o.price - 65000.0).abs() < 1e-10);
        assert!((o.qty - 0.01).abs() < 1e-10);
        assert!((o.cum_exec_qty - 0.005).abs() < 1e-10);
        assert_eq!(o.order_status, "PartiallyFilled");
    }

    #[test]
    fn test_parse_execution_list() {
        let result = serde_json::json!({
            "list": [{
                "execId": "exec-001",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "execPrice": "65000.0",
                "execQty": "0.001",
                "execValue": "65.0",
                "execFee": "0.0358",
                "feeCurrency": "USDT",
                "orderId": "ord-001",
                "orderLinkId": "link-001",
                "execType": "Trade",
                "execTime": "1700000000000",
                "closedPnl": "12.5"
            }]
        });
        let execs = parse_execution_list(&result).unwrap();
        assert_eq!(execs.len(), 1);
        let e = &execs[0];
        assert_eq!(e.exec_id, "exec-001");
        assert!((e.exec_price - 65000.0).abs() < 1e-10);
        assert!((e.exec_fee - 0.0358).abs() < 1e-10);
        assert_eq!(e.exec_type, "Trade");
        assert!((e.closed_pnl - 12.5).abs() < 1e-10, "closedPnl must parse");
    }

    #[test]
    fn test_parse_execution_missing_closed_pnl_is_zero() {
        // Older fills / open legs may omit closedPnl — parser must not fail.
        // 缺 closedPnl（開倉腿）時解析器不應失敗，回傳 0.0。
        let result = serde_json::json!({
            "list": [{
                "execId": "exec-open",
                "symbol": "BTCUSDT",
                "side": "Buy",
                "execPrice": "65000.0",
                "execQty": "0.001",
                "execValue": "65.0",
                "execFee": "0.0358",
                "feeCurrency": "USDT",
                "orderId": "ord-open",
                "orderLinkId": "",
                "execType": "Trade",
                "execTime": "1700000000000"
            }]
        });
        let execs = parse_execution_list(&result).unwrap();
        assert_eq!(execs[0].closed_pnl, 0.0);
    }

    #[test]
    fn test_parse_empty_lists() {
        // Empty result should return empty vec, not error
        // 空結果應返回空向量，不是錯誤
        let result = serde_json::json!({"list": []});
        assert_eq!(parse_order_info_list(&result).unwrap().len(), 0);
        assert_eq!(parse_execution_list(&result).unwrap().len(), 0);
        assert_eq!(parse_order_response_list(&result).unwrap().len(), 0);

        // Missing "list" key also returns empty / 缺少 "list" 鍵也返回空
        let result = serde_json::json!({});
        assert_eq!(parse_order_info_list(&result).unwrap().len(), 0);
    }

    // -- Validation tests / 驗證測試 --

    #[test]
    fn test_validate_and_round_limit_no_price() {
        let cache = Arc::new(sample_cache());
        let client = Arc::new(
            BybitRestClient::new(
                crate::bybit_rest_client::BybitEnvironment::Demo,
                Some("test_key".to_string()),
                Some("test_secret".to_string()),
            )
            .unwrap(),
        );
        let mgr = OrderManager::new(client, cache);

        let req = CreateOrderRequest {
            category: OrderCategory::Linear,
            symbol: "BTCUSDT".to_string(),
            side: OrderSide::Buy,
            order_type: OrderType::Limit,
            qty: 0.01,
            price: None, // missing price for limit
            time_in_force: None,
            reduce_only: None,
            close_on_trigger: None,
            order_link_id: None,
            trigger_price: None,
            trigger_direction: None,
            take_profit: None,
            stop_loss: None,
            tp_trigger_by: None,
            sl_trigger_by: None,
        };

        let result = mgr.validate_and_round(&req);
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_and_round_qty_too_small() {
        let cache = Arc::new(sample_cache());
        let client = Arc::new(
            BybitRestClient::new(
                crate::bybit_rest_client::BybitEnvironment::Demo,
                Some("test_key".to_string()),
                Some("test_secret".to_string()),
            )
            .unwrap(),
        );
        let mgr = OrderManager::new(client, cache);

        let req = CreateOrderRequest {
            category: OrderCategory::Linear,
            symbol: "BTCUSDT".to_string(),
            side: OrderSide::Buy,
            order_type: OrderType::Market,
            qty: 0.0001, // below min_qty 0.001 after rounding to 0
            price: None,
            time_in_force: None,
            reduce_only: None,
            close_on_trigger: None,
            order_link_id: None,
            trigger_price: None,
            trigger_direction: None,
            take_profit: None,
            stop_loss: None,
            tp_trigger_by: None,
            sl_trigger_by: None,
        };

        let result = mgr.validate_and_round(&req);
        assert!(result.is_err());
    }

    #[test]
    fn test_validate_and_round_success() {
        let cache = Arc::new(sample_cache());
        let client = Arc::new(
            BybitRestClient::new(
                crate::bybit_rest_client::BybitEnvironment::Demo,
                Some("test_key".to_string()),
                Some("test_secret".to_string()),
            )
            .unwrap(),
        );
        let mgr = OrderManager::new(client, cache);

        let req = CreateOrderRequest {
            category: OrderCategory::Linear,
            symbol: "BTCUSDT".to_string(),
            side: OrderSide::Buy,
            order_type: OrderType::Limit,
            qty: 0.0156,           // should round to 0.015
            price: Some(65000.55), // should round to 65000.6
            time_in_force: None,
            reduce_only: None,
            close_on_trigger: None,
            order_link_id: None,
            trigger_price: None,
            trigger_direction: None,
            take_profit: None,
            stop_loss: None,
            tp_trigger_by: None,
            sl_trigger_by: None,
        };

        let (qty, price) = mgr.validate_and_round(&req).unwrap();
        assert!((qty - 0.015).abs() < 1e-10);
        assert!((price.unwrap() - 65000.6).abs() < 1e-10);
    }

    // -- Field helpers tests / 欄位輔助函數測試 --

    #[test]
    fn test_str_field() {
        let obj = serde_json::json!({"a": "hello", "b": 123});
        assert_eq!(str_field(&obj, "a"), "hello");
        assert_eq!(str_field(&obj, "b"), ""); // not a string
        assert_eq!(str_field(&obj, "missing"), "");
    }

    #[test]
    fn test_f64_field() {
        let obj = serde_json::json!({"a": "123.45", "b": "bad", "c": 999});
        assert!((f64_field(&obj, "a") - 123.45).abs() < 1e-10);
        assert!((f64_field(&obj, "b") - 0.0).abs() < 1e-10);
        assert!((f64_field(&obj, "missing") - 0.0).abs() < 1e-10);
    }

    // -- Serde round-trip tests / 序列化往返測試 --

    #[test]
    fn test_order_info_serde_roundtrip() {
        let info = OrderInfo {
            order_id: "oid".to_string(),
            order_link_id: "link".to_string(),
            symbol: "BTCUSDT".to_string(),
            side: "Buy".to_string(),
            order_type: "Limit".to_string(),
            price: 65000.0,
            trigger_price: 0.0,
            qty: 0.01,
            cum_exec_qty: 0.0,
            cum_exec_value: 0.0,
            avg_price: 0.0,
            order_status: "New".to_string(),
            created_time: "1700000000000".to_string(),
            updated_time: "1700000000000".to_string(),
        };
        let json = serde_json::to_string(&info).unwrap();
        let deser: OrderInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.order_id, "oid");
        assert!((deser.price - 65000.0).abs() < 1e-10);
    }

    #[test]
    fn test_execution_info_serde_roundtrip() {
        let exec = ExecutionInfo {
            exec_id: "e1".to_string(),
            symbol: "ETHUSDT".to_string(),
            side: "Sell".to_string(),
            exec_price: 3500.0,
            exec_qty: 1.0,
            exec_value: 3500.0,
            exec_fee: 1.925,
            fee_currency: "USDT".to_string(),
            order_id: "o1".to_string(),
            order_link_id: "l1".to_string(),
            exec_type: "Trade".to_string(),
            exec_time: "1700000000000".to_string(),
            closed_pnl: -5.25,
        };
        let json = serde_json::to_string(&exec).unwrap();
        let deser: ExecutionInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.exec_id, "e1");
        assert!((deser.exec_fee - 1.925).abs() < 1e-10);
        assert!((deser.closed_pnl + 5.25).abs() < 1e-10);
    }
}

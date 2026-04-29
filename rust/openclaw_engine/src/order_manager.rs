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
#[cfg(test)]
use std::sync::atomic::AtomicU64;
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

    /// INSTR-WIRE-TEST-STRENGTHEN-1 (2026-04-23): test-only observability
    /// counter. Incremented by `validate_and_round` when it takes the
    /// `ensure_symbol` lazy-fetch branch (positive-cache miss). Tests
    /// assert the counter directly to verify whether the fast path or
    /// lazy-fetch path executed, replacing the old "completion implies
    /// fast path" indirect inference.
    ///
    /// Zero runtime cost in release (gated by #[cfg(test)]).
    ///
    /// INSTR-WIRE-TEST-STRENGTHEN-1：#[cfg(test)] 計數器，專供 test 直接驗證
    /// validate_and_round 是否進 ensure 分支。release build 不存在。
    #[cfg(test)]
    pub(crate) ensure_call_count: Arc<AtomicU64>,
}

impl OrderManager {
    /// Create a new OrderManager.
    /// 創建新的訂單管理器。
    pub fn new(client: Arc<BybitRestClient>, instruments: Arc<InstrumentInfoCache>) -> Self {
        Self {
            client,
            instruments,
            #[cfg(test)]
            ensure_call_count: Arc::new(AtomicU64::new(0)),
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
        let (qty, price) = self.validate_and_round(&req).await?;

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
    ///
    /// INSTR-WIRE-1 (2026-04-23): on positive-cache miss, call
    /// `InstrumentInfoCache::ensure_symbol` to attempt a lazy single-symbol fetch
    /// before falling through to M-1 fail-closed. This self-heals the case where
    /// `refresh()` missed a symbol (pre-pagination bug or race) without bypassing
    /// M-1 — if the lazy fetch also fails, the reject path is unchanged.
    /// INSTR-WIRE-1：正緩存 miss 時先嘗試 ensure_symbol 按需拉取自癒；若仍 miss
    /// 則保留 M-1 fail-closed 拒單語意不變。
    async fn validate_and_round(
        &self,
        req: &CreateOrderRequest,
    ) -> BybitResult<(f64, Option<f64>)> {
        let spec = match self.instruments.get(&req.symbol) {
            Some(s) => s,
            None => {
                // INSTR-WIRE-1 lazy fetch attempt — bounded by ensure_symbol's
                // 2s timeout + neg cache, so this does NOT extend the hot path
                // unboundedly on persistent failure.
                // INSTR-WIRE-1 按需拉取 — 2s 超時 + neg cache，熱路徑上界有界。
                //
                // INSTR-WIRE-TEST-STRENGTHEN-1: bump test-only counter so
                // tests can directly assert whether this branch ran.
                // INSTR-WIRE-TEST-STRENGTHEN-1：測試計數器 +1。
                #[cfg(test)]
                self.ensure_call_count
                    .fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                let category = req.category.as_str();
                match self
                    .instruments
                    .ensure_symbol(&self.client, category, &req.symbol)
                    .await
                {
                    Ok(Some(spec)) => spec,
                    Ok(None) => {
                        return Err(BybitApiError::Business {
                            ret_code: -1,
                            ret_msg: format!(
                                "instrument spec missing for {} — fail-closed (lazy fetch exhausted) / 缺少品種規格 {} — 拒絕下單（按需拉取亦失敗）",
                                req.symbol, req.symbol
                            ),
                            response: serde_json::json!(null),
                        });
                    }
                    Err(e) => {
                        return Err(BybitApiError::Business {
                            ret_code: -1,
                            ret_msg: format!(
                                "instrument spec missing for {} — fail-closed (lazy fetch error: {e}) / 缺少品種規格 {} — 拒絕下單（按需拉取錯：{e}）",
                                req.symbol, req.symbol
                            ),
                            response: serde_json::json!(null),
                        });
                    }
                }
            }
        };

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
#[path = "order_manager_tests.rs"]
mod tests;

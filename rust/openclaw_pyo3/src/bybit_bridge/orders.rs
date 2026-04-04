//! Order management PyO3 methods for BybitClient.
//! BybitClient 的訂單管理 PyO3 方法。
//!
//! MODULE_NOTE (EN): Adds order-related #[pymethods] to BybitClient: place, cancel,
//!   amend, query active/history, and fetch executions. Uses InstrumentInfoCache for
//!   pre-validation and qty/price rounding.
//! MODULE_NOTE (中): 為 BybitClient 添加訂單相關 #[pymethods]：下單、取消、修改、
//!   查詢活躍/歷史訂單、獲取成交記錄。使用 InstrumentInfoCache 進行預驗證和精度取整。

use super::{bybit_err_to_pyerr, rust_to_py};
use super::client::BybitClient;
use openclaw_engine::order_manager::{
    CreateOrderRequest, OrderCategory, OrderSide, OrderType, TimeInForce,
    TriggerDirection,
};
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// Helper: parse category/side/type strings / 解析品類/方向/類型字串
// ---------------------------------------------------------------------------

pub(crate) fn parse_category(s: &str) -> PyResult<OrderCategory> {
    match s.to_lowercase().as_str() {
        "linear" => Ok(OrderCategory::Linear),
        "spot" => Ok(OrderCategory::Spot),
        "inverse" => Ok(OrderCategory::Inverse),
        _ => Err(pyo3::exceptions::PyValueError::new_err(
            format!("Invalid category: '{s}'. Use 'linear', 'spot', or 'inverse'"),
        )),
    }
}

fn parse_side(s: &str) -> PyResult<OrderSide> {
    match s {
        "Buy" | "buy" | "BUY" => Ok(OrderSide::Buy),
        "Sell" | "sell" | "SELL" => Ok(OrderSide::Sell),
        _ => Err(pyo3::exceptions::PyValueError::new_err(
            format!("Invalid side: '{s}'. Use 'Buy' or 'Sell'"),
        )),
    }
}

fn parse_order_type(s: &str) -> PyResult<OrderType> {
    match s {
        "Market" | "market" | "MARKET" => Ok(OrderType::Market),
        "Limit" | "limit" | "LIMIT" => Ok(OrderType::Limit),
        _ => Err(pyo3::exceptions::PyValueError::new_err(
            format!("Invalid order_type: '{s}'. Use 'Market' or 'Limit'"),
        )),
    }
}

fn parse_tif(s: &str) -> PyResult<TimeInForce> {
    match s {
        "GTC" | "gtc" => Ok(TimeInForce::GTC),
        "IOC" | "ioc" => Ok(TimeInForce::IOC),
        "FOK" | "fok" => Ok(TimeInForce::FOK),
        "PostOnly" | "postonly" | "POSTONLY" => Ok(TimeInForce::PostOnly),
        _ => Err(pyo3::exceptions::PyValueError::new_err(
            format!("Invalid time_in_force: '{s}'. Use 'GTC', 'IOC', 'FOK', or 'PostOnly'"),
        )),
    }
}

// ---------------------------------------------------------------------------
// Order methods on BybitClient / BybitClient 上的訂單方法
// ---------------------------------------------------------------------------

#[pymethods]
impl BybitClient {
    /// Place a new order on Bybit V5.
    /// 在 Bybit V5 上下新訂單。
    ///
    /// Args:
    ///   symbol: Trading pair, e.g. "BTCUSDT"
    ///   side: "Buy" or "Sell"
    ///   order_type: "Market" or "Limit"
    ///   qty: Order quantity
    ///   price: Limit price (required for Limit orders)
    ///   category: "linear" (default), "spot", "inverse"
    ///   reduce_only: If True, only reduces position
    ///   time_in_force: "GTC", "IOC", "FOK", "PostOnly"
    ///   order_link_id: Client order ID for idempotency
    ///   trigger_price: Trigger price for conditional orders
    ///   trigger_direction: 1=Rise, 2=Fall (for conditional)
    ///   take_profit: TP price on order
    ///   stop_loss: SL price on order
    /// Returns: dict with order_id and order_link_id
    #[pyo3(signature = (symbol, side, order_type, qty, price=None, category="linear",
                        reduce_only=None, time_in_force=None, order_link_id=None,
                        trigger_price=None, trigger_direction=None,
                        take_profit=None, stop_loss=None))]
    #[allow(clippy::too_many_arguments)]
    fn place_order(
        &self,
        py: Python<'_>,
        symbol: &str,
        side: &str,
        order_type: &str,
        qty: f64,
        price: Option<f64>,
        category: &str,
        reduce_only: Option<bool>,
        time_in_force: Option<&str>,
        order_link_id: Option<String>,
        trigger_price: Option<f64>,
        trigger_direction: Option<i32>,
        take_profit: Option<f64>,
        stop_loss: Option<f64>,
    ) -> PyResult<PyObject> {
        let req = CreateOrderRequest {
            category: parse_category(category)?,
            symbol: symbol.to_string(),
            side: parse_side(side)?,
            order_type: parse_order_type(order_type)?,
            qty,
            price,
            time_in_force: time_in_force.map(parse_tif).transpose()?,
            reduce_only,
            close_on_trigger: None,
            order_link_id,
            trigger_price,
            trigger_direction: trigger_direction.map(|d| match d {
                2 => TriggerDirection::Fall,
                _ => TriggerDirection::Rise,
            }),
            take_profit,
            stop_loss,
            tp_trigger_by: None,
            sl_trigger_by: None,
        };

        let resp = self.rt
            .block_on(self.orders().place_order(req))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &resp)
    }

    /// Cancel a single order by order ID.
    /// 通過訂單 ID 取消單個訂單。
    #[pyo3(signature = (symbol, order_id, category="linear"))]
    fn cancel_order(
        &self,
        py: Python<'_>,
        symbol: &str,
        order_id: &str,
        category: &str,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        let resp = self.rt
            .block_on(self.orders().cancel_order(cat, symbol, order_id))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &resp)
    }

    /// Cancel all active orders for a symbol.
    /// 取消某交易對的所有活躍訂單。
    #[pyo3(signature = (symbol, category="linear"))]
    fn cancel_all_orders(
        &self,
        py: Python<'_>,
        symbol: &str,
        category: &str,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        let resp = self.rt
            .block_on(self.orders().cancel_all(cat, symbol))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &resp)
    }

    /// Get active (open) orders.
    /// 查詢活躍（未完成）訂單。
    ///
    /// If no symbol given, uses settle_coin (default "USDT") for Bybit query.
    /// 若未指定 symbol，使用 settle_coin（默認 "USDT"）查詢。
    #[pyo3(signature = (category="linear", symbol=None, settle_coin="USDT"))]
    fn get_active_orders(
        &self,
        py: Python<'_>,
        category: &str,
        symbol: Option<&str>,
        settle_coin: &str,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        if symbol.is_some() {
            let orders = self.rt
                .block_on(self.orders().get_active_orders(cat, symbol))
                .map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &orders)
        } else {
            let cat_str = cat.as_str();
            let rest = self.rest.clone();
            let orders: Vec<openclaw_engine::order_manager::OrderInfo> = self.rt.block_on(async move {
                let params = vec![
                    ("category", cat_str),
                    ("settleCoin", settle_coin),
                ];
                let resp = rest.get_checked("/v5/order/realtime", &params).await?;
                openclaw_engine::order_manager::parse_order_info_list_pub(&resp.result)
            }).map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &orders)
        }
    }

    /// Get order history.
    /// 查詢歷史訂單。
    #[pyo3(signature = (category="linear", symbol=None, limit=None, settle_coin="USDT"))]
    fn get_order_history(
        &self,
        py: Python<'_>,
        category: &str,
        symbol: Option<&str>,
        limit: Option<u32>,
        settle_coin: &str,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        let limit_str = limit.unwrap_or(50).to_string();
        if symbol.is_some() {
            let orders = self.rt
                .block_on(self.orders().get_order_history(cat, symbol, limit))
                .map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &orders)
        } else {
            let cat_str = cat.as_str();
            let rest = self.rest.clone();
            let orders: Vec<openclaw_engine::order_manager::OrderInfo> = self.rt.block_on(async move {
                let params = vec![
                    ("category", cat_str),
                    ("settleCoin", settle_coin),
                    ("limit", &limit_str),
                ];
                let resp = rest.get_checked("/v5/order/history", &params).await?;
                openclaw_engine::order_manager::parse_order_info_list_pub(&resp.result)
            }).map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &orders)
        }
    }

    /// Get execution (fill) records.
    /// 查詢成交記錄。
    #[pyo3(signature = (category="linear", symbol=None, limit=None, settle_coin="USDT"))]
    fn get_executions(
        &self,
        py: Python<'_>,
        category: &str,
        symbol: Option<&str>,
        limit: Option<u32>,
        settle_coin: &str,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        let limit_str = limit.unwrap_or(50).to_string();
        if symbol.is_some() {
            let fills = self.rt
                .block_on(self.orders().get_executions(cat, symbol, limit))
                .map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &fills)
        } else {
            let cat_str = cat.as_str();
            let rest = self.rest.clone();
            let fills: Vec<openclaw_engine::order_manager::ExecutionInfo> = self.rt.block_on(async move {
                let params = vec![
                    ("category", cat_str),
                    ("settleCoin", settle_coin),
                    ("limit", &limit_str),
                ];
                let resp = rest.get_checked("/v5/execution/list", &params).await?;
                openclaw_engine::order_manager::parse_execution_list_pub(&resp.result)
            }).map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &fills)
        }
    }
}

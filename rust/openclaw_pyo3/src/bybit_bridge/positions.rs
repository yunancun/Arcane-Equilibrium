//! Position management PyO3 methods for BybitClient.
//! BybitClient 的持倉管理 PyO3 方法。
//!
//! MODULE_NOTE (EN): Adds position-related #[pymethods] to BybitClient: get positions,
//!   set leverage, set trading stop (TP/SL/trailing), and get closed PnL.
//! MODULE_NOTE (中): 為 BybitClient 添加持倉相關 #[pymethods]：查詢持倉、
//!   設置槓桿、設置交易止損（止盈/止損/追蹤止損）、獲取已平倉盈虧。

use super::{bybit_err_to_pyerr, rust_to_py};
use super::client::BybitClient;
use super::orders::parse_category;
use openclaw_engine::position_manager::TradingStopRequest;
use pyo3::prelude::*;

#[pymethods]
impl BybitClient {
    /// Get all positions for a category, optionally filtered by symbol.
    /// 查詢某品類的所有持倉，可選按交易對過濾。
    ///
    /// If no symbol is given, uses settle_coin (default "USDT") to query all positions.
    /// 若未指定 symbol，使用 settle_coin（默認 "USDT"）查詢所有持倉。
    #[pyo3(signature = (category="linear", symbol=None, settle_coin="USDT"))]
    fn get_positions(
        &self,
        py: Python<'_>,
        category: &str,
        symbol: Option<&str>,
        settle_coin: &str,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        // If symbol provided, use PositionManager directly.
        // Otherwise, add settleCoin param via raw REST call.
        // 若提供 symbol，直接使用 PositionManager。
        // 否則，通過原始 REST 調用添加 settleCoin 參數。
        if symbol.is_some() {
            let pm = self.positions();
            let positions = self.rt
                .block_on(pm.get_positions(cat, symbol))
                .map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &positions)
        } else {
            // Raw REST call with settleCoin / 帶 settleCoin 的原始 REST 調用
            let cat_str = cat.as_str();
            let rest = self.rest.clone();
            let positions = self.rt.block_on(async move {
                let params = vec![
                    ("category", cat_str),
                    ("settleCoin", settle_coin),
                ];
                let resp = rest.get_checked("/v5/position/list", &params).await?;
                openclaw_engine::position_manager::parse_position_list_pub(&resp.result)
            }).map_err(bybit_err_to_pyerr)?;
            rust_to_py(py, &positions)
        }
    }

    /// Set leverage for a symbol (buy and sell sides).
    /// 設置交易對的槓桿（買賣兩側）。
    ///
    /// Idempotent: returns success if already set to requested value.
    /// 冪等：如果已設置為請求值，返回成功。
    #[pyo3(signature = (symbol, buy_leverage, sell_leverage, category="linear"))]
    fn set_leverage(
        &self,
        symbol: &str,
        buy_leverage: f64,
        sell_leverage: f64,
        category: &str,
    ) -> PyResult<()> {
        let cat = parse_category(category)?;
        self.rt
            .block_on(self.positions().set_leverage(cat, symbol, buy_leverage, sell_leverage))
            .map_err(bybit_err_to_pyerr)
    }

    /// Set trading stop (TP/SL/trailing stop) on a position.
    /// 在持倉上設置交易止損（止盈/止損/追蹤止損）。
    #[pyo3(signature = (symbol, category="linear", take_profit=None, stop_loss=None,
                        trailing_stop=None, active_price=None, position_idx=None))]
    #[allow(clippy::too_many_arguments)]
    fn set_trading_stop(
        &self,
        symbol: &str,
        category: &str,
        take_profit: Option<f64>,
        stop_loss: Option<f64>,
        trailing_stop: Option<f64>,
        active_price: Option<f64>,
        position_idx: Option<i32>,
    ) -> PyResult<()> {
        let req = TradingStopRequest {
            category: parse_category(category)?,
            symbol: symbol.to_string(),
            take_profit,
            stop_loss,
            tp_trigger_by: None,
            sl_trigger_by: None,
            trailing_stop,
            active_price,
            position_idx,
        };
        self.rt
            .block_on(self.positions().set_trading_stop(req))
            .map_err(bybit_err_to_pyerr)
    }

    /// Get closed PnL history.
    /// 獲取已平倉盈虧歷史。
    #[pyo3(signature = (category="linear", symbol=None, limit=None))]
    fn get_closed_pnl(
        &self,
        py: Python<'_>,
        category: &str,
        symbol: Option<&str>,
        limit: Option<u32>,
    ) -> PyResult<PyObject> {
        let cat = parse_category(category)?;
        let pnl = self.rt
            .block_on(self.positions().get_closed_pnl(cat, symbol, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &pnl)
    }
}

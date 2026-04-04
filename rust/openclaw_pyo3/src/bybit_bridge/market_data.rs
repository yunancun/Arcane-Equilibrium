//! Market data + Instrument info PyO3 methods for BybitClient.
//! BybitClient 的市場數據 + 合約信息 PyO3 方法。
//!
//! MODULE_NOTE (EN): Adds market data and instrument info #[pymethods] to BybitClient.
//!   MarketDataClient methods use &str category (not OrderCategory enum).
//! MODULE_NOTE (中): 為 BybitClient 添加市場數據和合約信息 #[pymethods]。
//!   MarketDataClient 方法使用 &str category（非 OrderCategory 枚舉）。

use super::{bybit_err_to_pyerr, rust_to_py};
use super::client::BybitClient;
use openclaw_engine::market_data_client::MarketDataClient;
use pyo3::prelude::*;

impl BybitClient {
    pub(crate) fn market_data(&self) -> MarketDataClient {
        MarketDataClient::new(self.rest.clone())
    }
}

#[pymethods]
impl BybitClient {
    /// Get kline (candlestick) bars.
    /// 獲取 K 線數據。
    #[pyo3(signature = (category, symbol, interval, limit=None, start=None, end=None))]
    fn get_klines(
        &self, py: Python<'_>,
        category: &str, symbol: &str, interval: &str,
        limit: Option<u32>, start: Option<u64>, end: Option<u64>,
    ) -> PyResult<PyObject> {
        let bars = self.rt
            .block_on(self.market_data().get_klines(category, symbol, interval, start, end, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &bars)
    }

    /// Get 24h ticker info.
    /// 獲取 24 小時行情。
    #[pyo3(signature = (category, symbol=None))]
    fn get_tickers(&self, py: Python<'_>, category: &str, symbol: Option<&str>) -> PyResult<PyObject> {
        let tickers = self.rt
            .block_on(self.market_data().get_tickers(category, symbol))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &tickers)
    }

    /// Get L2 orderbook snapshot.
    /// 獲取 L2 訂單簿快照。
    #[pyo3(signature = (category, symbol, limit=None))]
    fn get_orderbook(&self, py: Python<'_>, category: &str, symbol: &str, limit: Option<u32>) -> PyResult<PyObject> {
        let ob = self.rt
            .block_on(self.market_data().get_orderbook(category, symbol, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &ob)
    }

    /// Get funding rate history.
    /// 獲取資金費率歷史。
    #[pyo3(signature = (category, symbol, limit=None, start_time=None, end_time=None))]
    fn get_funding_history(
        &self, py: Python<'_>,
        category: &str, symbol: &str,
        limit: Option<u32>, start_time: Option<u64>, end_time: Option<u64>,
    ) -> PyResult<PyObject> {
        let records = self.rt
            .block_on(self.market_data().get_funding_history(category, symbol, start_time, end_time, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &records)
    }

    /// Get open interest history.
    /// 獲取持倉量歷史。
    #[pyo3(signature = (category, symbol, interval_time, limit=None))]
    fn get_open_interest(
        &self, py: Python<'_>,
        category: &str, symbol: &str, interval_time: &str, limit: Option<u32>,
    ) -> PyResult<PyObject> {
        let records = self.rt
            .block_on(self.market_data().get_open_interest(category, symbol, interval_time, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &records)
    }

    /// Get long/short account ratio.
    /// 獲取多空帳戶比。
    #[pyo3(signature = (category, symbol, period, limit=None))]
    fn get_long_short_ratio(
        &self, py: Python<'_>,
        category: &str, symbol: &str, period: &str, limit: Option<u32>,
    ) -> PyResult<PyObject> {
        let records = self.rt
            .block_on(self.market_data().get_long_short_ratio(category, symbol, period, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &records)
    }

    /// Get recent trades.
    /// 獲取近期成交記錄。
    #[pyo3(signature = (category, symbol, limit=None))]
    fn get_recent_trades(&self, py: Python<'_>, category: &str, symbol: &str, limit: Option<u32>) -> PyResult<PyObject> {
        let trades = self.rt
            .block_on(self.market_data().get_recent_trades(category, symbol, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &trades)
    }

    /// Get server time.
    /// 獲取服務器時間。
    fn get_server_time(&self, py: Python<'_>) -> PyResult<PyObject> {
        let time = self.rt
            .block_on(self.market_data().get_server_time())
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &time)
    }

    // -----------------------------------------------------------------------
    // Instrument Info / 合約信息
    // -----------------------------------------------------------------------

    /// Refresh instrument info cache from Bybit.
    /// 從 Bybit 刷新合約信息緩存。返回載入數量。
    #[pyo3(signature = (category="linear"))]
    fn refresh_instruments(&self, category: &str) -> PyResult<usize> {
        self.rt
            .block_on(self.instruments.refresh(&self.rest, category))
            .map_err(bybit_err_to_pyerr)
    }

    /// Get instrument spec for a symbol (from cache).
    /// 獲取交易對規格（從緩存）。先調用 refresh_instruments()。
    fn get_instrument(&self, py: Python<'_>, symbol: &str) -> PyResult<Option<PyObject>> {
        match self.instruments.get(symbol) {
            Some(spec) => Ok(Some(rust_to_py(py, &spec)?)),
            None => Ok(None),
        }
    }

    /// Round quantity to exchange precision.
    /// 將數量取整到交易所精度。
    fn round_qty(&self, symbol: &str, qty: f64) -> Option<f64> {
        self.instruments.round_qty(symbol, qty)
    }

    /// Round price to exchange precision.
    /// 將價格取整到交易所精度。
    fn round_price(&self, symbol: &str, price: f64) -> Option<f64> {
        self.instruments.round_price(symbol, price)
    }

    /// Validate order against exchange limits. Returns (valid, reason).
    /// 驗證訂單。返回 (是否有效, 原因)。
    fn validate_order(&self, symbol: &str, qty: f64, price: f64) -> (bool, String) {
        match self.instruments.get(symbol) {
            Some(spec) => spec.validate_order(qty, price),
            None => (true, "no instrument info cached".to_string()),
        }
    }

    /// List all cached symbol names.
    /// 列出所有緩存的交易對。
    fn instrument_symbols(&self) -> Vec<String> {
        self.instruments.symbols()
    }

    /// Get number of cached instruments.
    /// 獲取緩存的合約數量。
    fn instrument_count(&self) -> usize {
        self.instruments.len()
    }
}

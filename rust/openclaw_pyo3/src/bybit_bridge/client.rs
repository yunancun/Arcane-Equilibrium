//! BybitClient — PyO3 wrapper for Bybit V5 REST API operations.
//! BybitClient — Bybit V5 REST API 操作的 PyO3 包裝器。
//!
//! MODULE_NOTE (EN): Single #[pyclass] wrapping BybitRestClient + AccountManager +
//!   OrderManager + PositionManager + MarketDataClient + InstrumentInfoCache.
//!   Uses a dedicated tokio::Runtime for async→sync bridging (independent from
//!   Python's asyncio event loop — no deadlock risk with FastAPI).
//! MODULE_NOTE (中): 單個 #[pyclass] 包裝 BybitRestClient + AccountManager +
//!   OrderManager + PositionManager + MarketDataClient + InstrumentInfoCache。
//!   使用專用 tokio::Runtime 進行 async→sync 橋接（獨立於 Python 的 asyncio
//!   事件循環 — 與 FastAPI 無死鎖風險）。

use super::{bybit_err_to_pyerr, parse_environment, rust_to_py};
use openclaw_engine::account_manager::AccountManager;
use openclaw_engine::bybit_rest_client::BybitRestClient;
use openclaw_engine::instrument_info::InstrumentInfoCache;
use openclaw_engine::order_manager::OrderManager;
use openclaw_engine::position_manager::PositionManager;
use pyo3::prelude::*;
use std::sync::Arc;

// ---------------------------------------------------------------------------
// BybitClient / Bybit 客戶端
// ---------------------------------------------------------------------------

/// Python-facing Bybit V5 API client.
/// 面向 Python 的 Bybit V5 API 客戶端。
///
/// Usage from Python:
/// ```python
/// from openclaw_core import BybitClient
/// client = BybitClient()  # reads credentials from env/files
/// client.refresh_balance()
/// print(client.usdt_equity())
/// snapshot = client.wallet_snapshot()  # returns dict
/// ```
#[pyclass]
pub struct BybitClient {
    /// Shared REST client (thread-safe, Arc-wrapped).
    /// 共享 REST 客戶端（線程安全，Arc 包裝）。
    pub(crate) rest: Arc<BybitRestClient>,
    /// Dedicated tokio runtime for async→sync bridging.
    /// 專用 tokio 運行時，用於 async→sync 橋接。
    pub(crate) rt: tokio::runtime::Runtime,
    /// Account manager (balance, fees, account info).
    /// 帳戶管理器（餘額、手續費、帳戶信息）。
    account: AccountManager,
    /// Instrument info cache (symbol specs, qty/price rounding).
    /// 合約信息緩存（品種規格、數量/價格取整）。
    pub(crate) instruments: Arc<InstrumentInfoCache>,
}

// ---------------------------------------------------------------------------
// Internal helpers (not exposed to Python) / 內部輔助方法（不暴露給 Python）
// ---------------------------------------------------------------------------

impl BybitClient {
    /// Create an OrderManager backed by this client's REST + instruments.
    /// 創建基於此客戶端 REST + 合約信息的 OrderManager。
    pub(crate) fn orders(&self) -> OrderManager {
        OrderManager::new(self.rest.clone(), self.instruments.clone())
    }

    /// Create a PositionManager backed by this client's REST.
    /// 創建基於此客戶端 REST 的 PositionManager。
    pub(crate) fn positions(&self) -> PositionManager {
        PositionManager::new(self.rest.clone())
    }
}

#[pymethods]
impl BybitClient {
    /// Create a new BybitClient.
    /// 創建新的 BybitClient。
    ///
    /// Args:
    ///   api_key: API key (optional — reads from env/files if empty)
    ///   api_secret: API secret (optional — reads from env/files if empty)
    ///   environment: "demo" (default), "testnet", or "mainnet"
    ///
    /// 參數：
    ///   api_key: API 金鑰（可選 — 為空時從環境變量/文件讀取）
    ///   api_secret: API 密鑰（可選 — 為空時從環境變量/文件讀取）
    ///   environment: "demo"（默認）、"testnet" 或 "mainnet"
    #[new]
    #[pyo3(signature = (api_key=None, api_secret=None, environment="demo"))]
    fn new(
        api_key: Option<String>,
        api_secret: Option<String>,
        environment: &str,
    ) -> PyResult<Self> {
        let env = parse_environment(environment);
        let rest = BybitRestClient::new(env, api_key, api_secret)
            .map_err(bybit_err_to_pyerr)?;

        let rt = tokio::runtime::Builder::new_multi_thread()
            .worker_threads(2)
            .enable_all()
            .build()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(
                format!("Failed to create tokio runtime: {e}")
            ))?;

        Ok(Self {
            rest: Arc::new(rest),
            rt,
            account: AccountManager::new(),
            instruments: Arc::new(InstrumentInfoCache::new()),
        })
    }

    /// Check if API credentials are configured.
    /// 檢查 API 憑證是否已配置。
    fn has_credentials(&self) -> bool {
        self.rest.has_credentials()
    }

    /// Get the configured base URL.
    /// 取得配置的基礎 URL。
    fn base_url(&self) -> String {
        self.rest.base_url().to_string()
    }

    /// Get current rate limit remaining count.
    /// 取得當前限流剩餘計數。
    fn rate_limit_remaining(&self) -> i64 {
        self.rest.rate_limit_remaining()
    }

    // -----------------------------------------------------------------------
    // Account Manager / 帳戶管理器
    // -----------------------------------------------------------------------

    /// Fetch and cache wallet balance from Bybit.
    /// 從 Bybit 獲取並緩存錢包餘額。
    ///
    /// Returns: wallet state dict with keys: account_type, total_equity,
    ///   total_wallet_balance, total_available_balance, coins, updated_at_ms
    /// 返回：錢包狀態字典
    fn refresh_balance(&self, py: Python<'_>) -> PyResult<PyObject> {
        self.rt
            .block_on(self.account.refresh_balance(&self.rest))
            .map_err(bybit_err_to_pyerr)?;
        let snap = self.account.wallet_snapshot();
        rust_to_py(py, &snap)
    }

    /// Get cached USDT equity (total including unrealized PnL).
    /// 取得緩存的 USDT 權益（含未實現盈虧）。
    fn usdt_equity(&self) -> f64 {
        self.account.usdt_equity()
    }

    /// Get cached USDT wallet balance (without unrealized PnL).
    /// 取得緩存的 USDT 錢包餘額（不含未實現盈虧）。
    fn usdt_wallet_balance(&self) -> f64 {
        self.account.usdt_wallet_balance()
    }

    /// Get cached USDT available balance (withdrawable).
    /// 取得緩存的 USDT 可用餘額（可提取）。
    fn usdt_available(&self) -> f64 {
        self.account.usdt_available()
    }

    /// Get full cached wallet state snapshot as dict.
    /// 取得完整的緩存錢包狀態快照（dict）。
    fn wallet_snapshot(&self, py: Python<'_>) -> PyResult<PyObject> {
        let snap = self.account.wallet_snapshot();
        rust_to_py(py, &snap)
    }

    /// Fetch and cache fee rates from Bybit.
    /// 從 Bybit 獲取並緩存手續費率。
    ///
    /// Args:
    ///   category: "linear" (default), "spot", "inverse"
    /// Returns: number of symbols loaded
    /// 參數：
    ///   category: "linear"（默認）、"spot"、"inverse"
    /// 返回：載入的交易對數量
    #[pyo3(signature = (category="linear"))]
    fn refresh_fee_rates(&self, category: &str) -> PyResult<usize> {
        self.rt
            .block_on(self.account.refresh_fee_rates(&self.rest, category))
            .map_err(bybit_err_to_pyerr)
    }

    /// Get fee rate for a symbol as dict.
    /// 取得交易對的手續費率（dict）。
    fn get_fee_rate(&self, py: Python<'_>, symbol: &str) -> PyResult<PyObject> {
        let rate = self.account.get_fee_rate(symbol);
        rust_to_py(py, &rate)
    }

    /// Get taker fee rate for a symbol (convenience).
    /// 取得交易對的 taker 手續費率（便捷方法）。
    fn taker_fee(&self, symbol: &str) -> f64 {
        self.account.taker_fee(symbol)
    }

    /// Get maker fee rate for a symbol (convenience).
    /// 取得交易對的 maker 手續費率（便捷方法）。
    fn maker_fee(&self, symbol: &str) -> f64 {
        self.account.maker_fee(symbol)
    }

    /// Get account info (margin mode, hedging, UTA status).
    /// 獲取帳戶信息（保證金模式、對沖、UTA 狀態）。
    fn get_account_info(&self, py: Python<'_>) -> PyResult<PyObject> {
        let info = self.rt
            .block_on(self.account.get_account_info(&self.rest))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &info)
    }

    /// Get margin borrow history.
    /// 獲取保證金借幣歷史。
    #[pyo3(signature = (currency=None, limit=None))]
    fn get_borrow_history(
        &self,
        py: Python<'_>,
        currency: Option<&str>,
        limit: Option<u32>,
    ) -> PyResult<PyObject> {
        let records = self.rt
            .block_on(self.account.get_borrow_history(&self.rest, currency, limit))
            .map_err(bybit_err_to_pyerr)?;
        rust_to_py(py, &records)
    }

    /// String representation for debugging.
    /// 調試用字串表示。
    fn __repr__(&self) -> String {
        format!(
            "BybitClient(url={}, credentials={})",
            self.rest.base_url(),
            if self.rest.has_credentials() { "yes" } else { "no" }
        )
    }
}

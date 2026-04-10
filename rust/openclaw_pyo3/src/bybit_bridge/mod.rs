//! PyO3 bridge for Bybit V5 API — exposes Rust Bybit modules to Python.
//! Bybit V5 API 的 PyO3 橋接 — 將 Rust Bybit 模組暴露給 Python。
//!
//! MODULE_NOTE (EN): This module wraps openclaw_engine's Bybit API clients as #[pyclass]
//!   objects callable from Python. Each BybitClient instance owns an Arc<BybitRestClient>
//!   and a tokio::Runtime for async→sync bridging. Serialization uses pythonize for
//!   zero-copy Serialize→PyObject conversion.
//! MODULE_NOTE (中): 此模組將 openclaw_engine 的 Bybit API 客戶端包裝為 #[pyclass] 對象，
//!   可從 Python 調用。每個 BybitClient 實例持有 Arc<BybitRestClient> 和 tokio::Runtime
//!   用於 async→sync 橋接。序列化使用 pythonize 進行零拷貝 Serialize→PyObject 轉換。

use openclaw_engine::bybit_rest_client::{BybitApiError, BybitEnvironment};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

mod client;
mod market_data;
mod orders;
mod positions;

pub use client::BybitClient;

// ---------------------------------------------------------------------------
// Error conversion / 錯誤轉換
// ---------------------------------------------------------------------------

/// Convert BybitApiError to PyErr with meaningful message.
/// 將 BybitApiError 轉換為有意義消息的 PyErr。
pub(crate) fn bybit_err_to_pyerr(e: BybitApiError) -> PyErr {
    match &e {
        BybitApiError::Business {
            ret_code, ret_msg, ..
        } => PyRuntimeError::new_err(format!(
            "Bybit API error: retCode={ret_code}, retMsg={ret_msg}"
        )),
        _ => PyRuntimeError::new_err(format!("Bybit error: {e}")),
    }
}

// ---------------------------------------------------------------------------
// Serialization helper / 序列化輔助
// ---------------------------------------------------------------------------

/// Convert any Serialize type to a Python object via pythonize.
/// 通過 pythonize 將任何 Serialize 類型轉換為 Python 對象。
pub(crate) fn rust_to_py<T: serde::Serialize>(py: Python<'_>, value: &T) -> PyResult<PyObject> {
    pythonize::pythonize(py, value)
        .map(|obj| obj.into())
        .map_err(|e| PyRuntimeError::new_err(format!("Serialization error: {e}")))
}

// ---------------------------------------------------------------------------
// Environment parsing / 環境解析
// ---------------------------------------------------------------------------

/// Parse environment string to BybitEnvironment.
/// 解析環境字串為 BybitEnvironment。
///
/// Accepts: "demo", "testnet", "mainnet" (case-insensitive).
/// Default: Demo (safe default — never accidentally hit mainnet).
/// 接受："demo"、"testnet"、"mainnet"（不區分大小寫）。
/// 默認：Demo（安全默認 — 永不意外連接主網）。
pub(crate) fn parse_environment(env: &str) -> BybitEnvironment {
    match env.to_lowercase().as_str() {
        "testnet" => BybitEnvironment::Testnet,
        "mainnet" | "live" => BybitEnvironment::Mainnet,
        // live_demo: live slot key (GBR) against demo server — matches engine LiveDemo mode.
        // live_demo：使用 live 槽 key（GBR）連 demo 伺服器，對應引擎 LiveDemo 模式。
        "live_demo" => BybitEnvironment::LiveDemo,
        _ => BybitEnvironment::Demo,
    }
}

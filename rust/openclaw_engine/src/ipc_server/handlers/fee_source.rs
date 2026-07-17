//! LG-2 T3 (2026-05-11) — `query_fee_source` IPC handler。
//!
//! MODULE_NOTE：
//!   單一 method `query_fee_source`，由 healthcheck [45] `checks_pricing_binding.py`
//!   呼叫做 dual-source compare（Rust enum 真值 vs PG proxy 推斷）。
//!
//!   讀延後注入的 [`AccountManagerSlot`]，slot 為 None 時（main_instruments
//!   尚未注入，或當前 build 無任何 exchange binding）回結構化 `uninitialized`
//!   payload，對齊 `cost_edge_advisor` / `h_state_cache` 既有 pattern，**不**
//!   回 JSON-RPC error；Python 端可走 silent-dead branch。
//!
//!   Phase A 純唯讀，無 side-effect：純讀 RwLock<HashMap>。Hot path 不走 IPC
//!   （tick path 直接呼 `AccountManager::fee_source` 持有 binding Arc），本
//!   handler 是 observability-only。
//!
//! CLAUDE.md §二 #2 讀寫分離：本 handler 純唯讀，不對 fee cache / wallet /
//! refresh ts 產生任何 side-effect。
//!
//! 對齊契約：
//!   request  = {"jsonrpc":"2.0","method":"query_fee_source",
//!               "params":{"symbol":"BTCUSDT"},"id":N}
//!   response = {"jsonrpc":"2.0","result":{
//!                  "status":"ok",
//!                  "symbol":"BTCUSDT",
//!                  "fee_source":"bybit_api"|"demo_conservative_default"|"cold_default",
//!                  "last_refresh_ms":1700000000000,
//!                  "fee_rate_count":25
//!              },"id":N}
//!
//!   uninjected → {"status":"uninitialized","symbol":...,
//!                 "fee_source":"cold_default","last_refresh_ms":0,
//!                 "fee_rate_count":0,"note":"..."}

use super::super::slots::AccountManagerSlot;
use super::super::*;
use crate::account_manager::FeeSource;

/// `query_fee_source` IPC — 回 AccountManager.fee_source(symbol) 的真值快照。
/// AccountManager slot 未注入時 fail-soft 回 `uninitialized` payload。
pub(in crate::ipc_server) async fn handle_query_fee_source(
    id: serde_json::Value,
    params: &serde_json::Value,
    account_manager_slot: &AccountManagerSlot,
) -> JsonRpcResponse {
    // 解析 params.symbol；缺欄位 fail-closed 回 invalid request 比較合適，
    // 但本 IPC 對齊 cost_edge_advisor / h_state pattern 不爆 error，回
    // structured 錯 payload 讓 Python 端不 raise。
    let symbol = params
        .get("symbol")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();

    if symbol.is_empty() {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "invalid_params",
                "symbol": "",
                "fee_source": FeeSource::ColdDefault.as_str(),
                "last_refresh_ms": 0_u64,
                "fee_rate_count": 0_usize,
                "note": "missing required param: symbol",
            }),
        );
    }

    let guard = account_manager_slot.read().await;
    let am = match guard.as_ref() {
        Some(am) => am,
        None => {
            // env 沒任何 exchange binding 或 main_instruments 尚未注入 →
            // 回結構化 uninitialized；Python healthcheck 視作 silent-dead 分支。
            return uninitialized_response(id, &symbol, "account_manager not injected");
        }
    };

    let source = am.fee_source(&symbol);
    let last_refresh_ms = am.last_fee_refresh_ms();
    let fee_rate_count = am.fee_rate_count();

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "symbol": symbol,
            "fee_source": source.as_str(),
            "last_refresh_ms": last_refresh_ms,
            "fee_rate_count": fee_rate_count,
        }),
    )
}

/// AccountManager slot 未注入時的標準 payload；`status="uninitialized"` 字串
/// 穩定供 Python 分支。fee_source 一律 fallback `cold_default` — 因為 slot 未
/// 注入意味著本進程沒任何真實 fee runtime，與「從未 refresh」語意一致。
fn uninitialized_response(
    id: serde_json::Value,
    symbol: &str,
    note: &str,
) -> JsonRpcResponse {
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "uninitialized",
            "symbol": symbol,
            "fee_source": FeeSource::ColdDefault.as_str(),
            "last_refresh_ms": 0_u64,
            "fee_rate_count": 0_usize,
            "note": note,
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::account_manager::AccountManager;
    use std::sync::Arc;
    use tokio::sync::RwLock;

    fn empty_slot() -> AccountManagerSlot {
        Arc::new(RwLock::new(None))
    }

    fn populated_slot(am: Arc<AccountManager>) -> AccountManagerSlot {
        Arc::new(RwLock::new(Some(am)))
    }

    #[tokio::test]
    async fn query_uninjected_returns_uninitialized_shape() {
        // slot=None → uninitialized + cold_default + 0 ts/count，不 raise error。
        let slot = empty_slot();
        let resp = handle_query_fee_source(
            serde_json::json!(1),
            &serde_json::json!({"symbol": "BTCUSDT"}),
            &slot,
        )
        .await;
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "uninitialized");
        assert_eq!(r["symbol"], "BTCUSDT");
        assert_eq!(r["fee_source"], "cold_default");
        assert_eq!(r["last_refresh_ms"].as_u64(), Some(0));
        assert_eq!(r["fee_rate_count"].as_u64(), Some(0));
        assert!(r["note"].as_str().is_some());
    }

    #[tokio::test]
    async fn query_missing_symbol_returns_invalid_params_shape() {
        // params 沒 symbol → invalid_params；不 raise error；fee_source fallback。
        let slot = empty_slot();
        let resp = handle_query_fee_source(
            serde_json::json!(2),
            &serde_json::json!({}),
            &slot,
        )
        .await;
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "invalid_params");
        assert_eq!(r["fee_source"], "cold_default");
    }

    #[tokio::test]
    async fn query_cold_default_when_never_refreshed() {
        // AccountManager 注入但 last_fee_refresh_ms=0 → cold_default。
        let am = Arc::new(AccountManager::new());
        let slot = populated_slot(Arc::clone(&am));
        let resp = handle_query_fee_source(
            serde_json::json!(3),
            &serde_json::json!({"symbol": "BTCUSDT"}),
            &slot,
        )
        .await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["fee_source"], "cold_default");
        assert_eq!(r["last_refresh_ms"].as_u64(), Some(0));
        assert_eq!(r["fee_rate_count"].as_u64(), Some(0));
    }

    #[tokio::test]
    async fn query_demo_conservative_default_after_seed() {
        // seed_default_fee_rates 注入後 → demo_conservative_default。
        let am = Arc::new(AccountManager::new());
        let count = am.seed_default_fee_rates(["BTCUSDT", "ETHUSDT"]);
        assert_eq!(count, 2);
        let slot = populated_slot(Arc::clone(&am));
        let resp = handle_query_fee_source(
            serde_json::json!(4),
            &serde_json::json!({"symbol": "BTCUSDT"}),
            &slot,
        )
        .await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["fee_source"], "demo_conservative_default");
        assert!(r["last_refresh_ms"].as_u64().unwrap_or(0) > 0);
        assert_eq!(r["fee_rate_count"].as_u64(), Some(2));
    }
}

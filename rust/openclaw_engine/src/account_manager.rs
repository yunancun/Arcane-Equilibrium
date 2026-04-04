//! Bybit account manager — wallet balance and fee rate queries (R-05).
//! Bybit 帳戶管理器 — 錢包餘額和手續費率查詢。
//!
//! MODULE_NOTE (EN): Queries Bybit V5 account endpoints for wallet balance (UNIFIED account)
//!   and fee rates. Caches last known state for fast access. Provides USDT equity/balance
//!   extraction from the complex Bybit wallet response.
//! MODULE_NOTE (中): 查詢 Bybit V5 帳戶端點獲取錢包餘額（統一帳戶）和手續費率。
//!   緩存最後已知狀態供快速存取。從複雜的 Bybit 錢包回應中提取 USDT 權益/餘額。

use crate::bybit_rest_client::{BybitApiError, BybitRestClient, BybitResult};
use std::collections::HashMap;
use std::sync::RwLock;
use tracing::info;

// ---------------------------------------------------------------------------
// WalletBalance — parsed wallet state / 解析後的錢包狀態
// ---------------------------------------------------------------------------

/// Parsed wallet balance for a single coin.
/// 單幣種的解析後錢包餘額。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CoinBalance {
    /// Coin name, e.g. "USDT" / 幣種名稱
    pub coin: String,
    /// Wallet balance (deposited + realized PnL) / 錢包餘額
    pub wallet_balance: f64,
    /// Available balance for new orders / 可用餘額（可下新單）
    pub available_to_withdraw: f64,
    /// Total equity (wallet + unrealized PnL) / 總權益
    pub equity: f64,
    /// Unrealized PnL / 未實現盈虧
    pub unrealised_pnl: f64,
    /// Cumulative realized PnL / 累計已實現盈虧
    pub cum_realised_pnl: f64,
}

/// Parsed account wallet state (all coins).
/// 解析後的帳戶錢包狀態（所有幣種）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct WalletState {
    /// Account type: "UNIFIED", "CONTRACT", etc.
    /// 帳戶類型
    pub account_type: String,
    /// Total equity across all coins (in USD equivalent)
    /// 所有幣種的總權益（USD 等值）
    pub total_equity: f64,
    /// Total wallet balance / 總錢包餘額
    pub total_wallet_balance: f64,
    /// Total available balance / 總可用餘額
    pub total_available_balance: f64,
    /// Total unrealised PnL / 總未實現盈虧
    pub total_unrealised_pnl: f64,
    /// Per-coin balances / 各幣種餘額
    pub coins: HashMap<String, CoinBalance>,
    /// Timestamp of last update (ms) / 最後更新時間戳（毫秒）
    pub updated_at_ms: u64,
}

impl Default for WalletState {
    fn default() -> Self {
        Self {
            account_type: "UNIFIED".to_string(),
            total_equity: 0.0,
            total_wallet_balance: 0.0,
            total_available_balance: 0.0,
            total_unrealised_pnl: 0.0,
            coins: HashMap::new(),
            updated_at_ms: 0,
        }
    }
}

// ---------------------------------------------------------------------------
// FeeRate — per-symbol fee rate / 每交易對手續費率
// ---------------------------------------------------------------------------

/// Fee rate for a symbol.
/// 交易對的手續費率。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct FeeRate {
    /// Symbol name / 交易對名稱
    pub symbol: String,
    /// Maker fee rate (e.g. 0.0001 = 0.01%) / Maker 手續費率
    pub maker_fee_rate: f64,
    /// Taker fee rate (e.g. 0.0006 = 0.06%) / Taker 手續費率
    pub taker_fee_rate: f64,
}

// ---------------------------------------------------------------------------
// Default fee rates (safe fallback) / 預設手續費率（安全回退）
// ---------------------------------------------------------------------------

/// Default Bybit linear taker fee rate / Bybit linear 默認 taker 手續費率
const DEFAULT_TAKER_FEE: f64 = 0.00055;
/// Default Bybit linear maker fee rate / Bybit linear 默認 maker 手續費率
const DEFAULT_MAKER_FEE: f64 = 0.0002;

// ---------------------------------------------------------------------------
// AccountManager / 帳戶管理器
// ---------------------------------------------------------------------------

/// Manages Bybit account state: balance, fees, account info.
/// 管理 Bybit 帳戶狀態：餘額、手續費、帳戶信息。
pub struct AccountManager {
    /// Cached wallet state / 緩存的錢包狀態
    wallet: RwLock<WalletState>,
    /// Cached fee rates per symbol / 緩存的每交易對手續費率
    fee_rates: RwLock<HashMap<String, FeeRate>>,
}

impl AccountManager {
    /// Create a new AccountManager with empty state.
    /// 創建新的 AccountManager（空狀態）。
    pub fn new() -> Self {
        Self {
            wallet: RwLock::new(WalletState::default()),
            fee_rates: RwLock::new(HashMap::new()),
        }
    }

    // -----------------------------------------------------------------------
    // Wallet balance / 錢包餘額
    // -----------------------------------------------------------------------

    /// Fetch and cache wallet balance from Bybit.
    /// 從 Bybit 獲取並緩存錢包餘額。
    ///
    /// GET /v5/account/wallet-balance?accountType=UNIFIED
    pub async fn refresh_balance(&self, client: &BybitRestClient) -> BybitResult<&Self> {
        let resp = client
            .get("/v5/account/wallet-balance", &[("accountType", "UNIFIED")])
            .await?;

        if resp.ret_code != 0 {
            let ret_msg = resp.ret_msg.clone();
            return Err(BybitApiError::Business {
                ret_code: resp.ret_code,
                ret_msg,
                response: serde_json::to_value(&resp).unwrap_or_default(),
            });
        }

        let state = parse_wallet_response(&resp.result)?;

        info!(
            usdt_equity = format!("{:.2}", state.coins.get("USDT").map_or(0.0, |c| c.equity)),
            total_equity = format!("{:.2}", state.total_equity),
            coins = state.coins.len(),
            "wallet balance refreshed / 錢包餘額已刷新"
        );

        *self.wallet.write().unwrap() = state;
        Ok(self)
    }

    /// Get cached USDT equity (total including unrealized PnL).
    /// 取得緩存的 USDT 權益（含未實現盈虧）。
    pub fn usdt_equity(&self) -> f64 {
        self.wallet
            .read()
            .unwrap()
            .coins
            .get("USDT")
            .map_or(0.0, |c| c.equity)
    }

    /// Get cached USDT wallet balance (without unrealized PnL).
    /// 取得緩存的 USDT 錢包餘額（不含未實現盈虧）。
    pub fn usdt_wallet_balance(&self) -> f64 {
        self.wallet
            .read()
            .unwrap()
            .coins
            .get("USDT")
            .map_or(0.0, |c| c.wallet_balance)
    }

    /// Get cached USDT available balance (withdrawable).
    /// 取得緩存的 USDT 可用餘額（可提取）。
    pub fn usdt_available(&self) -> f64 {
        self.wallet
            .read()
            .unwrap()
            .coins
            .get("USDT")
            .map_or(0.0, |c| c.available_to_withdraw)
    }

    /// Get full cached wallet state snapshot.
    /// 取得完整的緩存錢包狀態快照。
    pub fn wallet_snapshot(&self) -> WalletState {
        self.wallet.read().unwrap().clone()
    }

    // -----------------------------------------------------------------------
    // Fee rates / 手續費率
    // -----------------------------------------------------------------------

    /// Fetch and cache fee rates from Bybit.
    /// 從 Bybit 獲取並緩存手續費率。
    ///
    /// GET /v5/account/fee-rate?category=linear
    pub async fn refresh_fee_rates(
        &self,
        client: &BybitRestClient,
        category: &str,
    ) -> BybitResult<usize> {
        let resp = client
            .get("/v5/account/fee-rate", &[("category", category)])
            .await?;

        if resp.ret_code != 0 {
            let ret_msg = resp.ret_msg.clone();
            return Err(BybitApiError::Business {
                ret_code: resp.ret_code,
                ret_msg,
                response: serde_json::to_value(&resp).unwrap_or_default(),
            });
        }

        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();

        let mut count = 0;
        let mut cache = self.fee_rates.write().unwrap();

        for item in &list {
            if let Some(rate) = parse_fee_rate_item(item) {
                cache.insert(rate.symbol.clone(), rate);
                count += 1;
            }
        }

        info!(
            category = category,
            symbols = count,
            "fee rates refreshed / 手續費率已刷新"
        );

        Ok(count)
    }

    /// Get fee rate for a symbol. Falls back to default if not cached.
    /// 取得交易對的手續費率。未緩存時使用默認值。
    pub fn get_fee_rate(&self, symbol: &str) -> FeeRate {
        self.fee_rates
            .read()
            .unwrap()
            .get(symbol)
            .cloned()
            .unwrap_or(FeeRate {
                symbol: symbol.to_string(),
                maker_fee_rate: DEFAULT_MAKER_FEE,
                taker_fee_rate: DEFAULT_TAKER_FEE,
            })
    }

    /// Get taker fee rate for a symbol (the most common case).
    /// 取得交易對的 taker 手續費率（最常見情況）。
    pub fn taker_fee(&self, symbol: &str) -> f64 {
        self.fee_rates
            .read()
            .unwrap()
            .get(symbol)
            .map_or(DEFAULT_TAKER_FEE, |r| r.taker_fee_rate)
    }

    /// Get maker fee rate for a symbol.
    /// 取得交易對的 maker 手續費率。
    pub fn maker_fee(&self, symbol: &str) -> f64 {
        self.fee_rates
            .read()
            .unwrap()
            .get(symbol)
            .map_or(DEFAULT_MAKER_FEE, |r| r.maker_fee_rate)
    }
}

impl Default for AccountManager {
    fn default() -> Self {
        Self::new()
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse Bybit wallet-balance response into WalletState.
/// 解析 Bybit wallet-balance 回應為 WalletState。
///
/// Response structure:
///   { "list": [{ "accountType": "UNIFIED", "totalEquity": "10000",
///     "coin": [{ "coin": "USDT", "equity": "9500", ... }] }] }
fn parse_wallet_response(result: &serde_json::Value) -> BybitResult<WalletState> {
    let accounts = result
        .get("list")
        .and_then(|v| v.as_array())
        .ok_or_else(|| BybitApiError::Business {
            ret_code: -1,
            ret_msg: "wallet response missing list field".to_string(),
            response: result.clone(),
        })?;

    // Take the first account (UNIFIED) / 取第一個帳戶（UNIFIED）
    let account = accounts.first().ok_or_else(|| BybitApiError::Business {
        ret_code: -1,
        ret_msg: "wallet response has empty list".to_string(),
        response: result.clone(),
    })?;

    let account_type = account
        .get("accountType")
        .and_then(|v| v.as_str())
        .unwrap_or("UNIFIED")
        .to_string();
    let total_equity = parse_f64(account, "totalEquity");
    let total_wallet_balance = parse_f64(account, "totalWalletBalance");
    let total_available_balance = parse_f64(account, "totalAvailableBalance");

    let coins_array = account
        .get("coin")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut coins = HashMap::new();
    for coin_item in &coins_array {
        let coin_name = coin_item
            .get("coin")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        if coin_name.is_empty() {
            continue;
        }
        coins.insert(
            coin_name.clone(),
            CoinBalance {
                coin: coin_name,
                wallet_balance: parse_f64(coin_item, "walletBalance"),
                available_to_withdraw: parse_f64(coin_item, "availableToWithdraw"),
                equity: parse_f64(coin_item, "equity"),
                unrealised_pnl: parse_f64(coin_item, "unrealisedPnl"),
                cum_realised_pnl: parse_f64(coin_item, "cumRealisedPnl"),
            },
        );
    }

    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64;

    Ok(WalletState {
        account_type,
        total_equity,
        total_wallet_balance,
        total_available_balance,
        total_unrealised_pnl: coins.values().map(|c| c.unrealised_pnl).sum(),
        coins,
        updated_at_ms: now_ms,
    })
}

/// Parse a fee-rate item from Bybit response.
/// 從 Bybit 回應中解析手續費率項目。
fn parse_fee_rate_item(item: &serde_json::Value) -> Option<FeeRate> {
    let symbol = item.get("symbol")?.as_str()?.to_string();
    let maker = parse_f64(item, "makerFeeRate");
    let taker = parse_f64(item, "takerFeeRate");
    Some(FeeRate {
        symbol,
        maker_fee_rate: maker,
        taker_fee_rate: taker,
    })
}

/// Parse a string field as f64, returning 0.0 on failure.
/// 將字串欄位解析為 f64，失敗時返回 0.0。
fn parse_f64(obj: &serde_json::Value, field: &str) -> f64 {
    obj.get(field)
        .and_then(|v| v.as_str())
        .and_then(|s| s.parse::<f64>().ok())
        .unwrap_or(0.0)
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_wallet_response() {
        let result = serde_json::json!({
            "list": [{
                "accountType": "UNIFIED",
                "totalEquity": "10500.50",
                "totalWalletBalance": "10000.00",
                "totalAvailableBalance": "8000.00",
                "coin": [
                    {
                        "coin": "USDT",
                        "equity": "9500.25",
                        "walletBalance": "9000.00",
                        "availableToWithdraw": "7500.00",
                        "unrealisedPnl": "500.25",
                        "cumRealisedPnl": "1200.50"
                    },
                    {
                        "coin": "BTC",
                        "equity": "0.015",
                        "walletBalance": "0.01",
                        "availableToWithdraw": "0.005",
                        "unrealisedPnl": "0.005",
                        "cumRealisedPnl": "0.002"
                    }
                ]
            }]
        });

        let state = parse_wallet_response(&result).unwrap();
        assert_eq!(state.account_type, "UNIFIED");
        assert!((state.total_equity - 10500.50).abs() < 1e-10);
        assert!((state.total_wallet_balance - 10000.0).abs() < 1e-10);
        assert_eq!(state.coins.len(), 2);

        let usdt = state.coins.get("USDT").unwrap();
        assert!((usdt.equity - 9500.25).abs() < 1e-10);
        assert!((usdt.wallet_balance - 9000.0).abs() < 1e-10);
        assert!((usdt.unrealised_pnl - 500.25).abs() < 1e-10);
    }

    #[test]
    fn test_parse_wallet_empty_list() {
        let result = serde_json::json!({"list": []});
        assert!(parse_wallet_response(&result).is_err());
    }

    #[test]
    fn test_parse_wallet_missing_list() {
        let result = serde_json::json!({});
        assert!(parse_wallet_response(&result).is_err());
    }

    #[test]
    fn test_parse_fee_rate_item() {
        let item = serde_json::json!({
            "symbol": "BTCUSDT",
            "makerFeeRate": "0.0002",
            "takerFeeRate": "0.00055"
        });
        let rate = parse_fee_rate_item(&item).unwrap();
        assert_eq!(rate.symbol, "BTCUSDT");
        assert!((rate.maker_fee_rate - 0.0002).abs() < 1e-10);
        assert!((rate.taker_fee_rate - 0.00055).abs() < 1e-10);
    }

    #[test]
    fn test_parse_fee_rate_missing_symbol() {
        let item = serde_json::json!({"makerFeeRate": "0.0002"});
        assert!(parse_fee_rate_item(&item).is_none());
    }

    #[test]
    fn test_account_manager_defaults() {
        let mgr = AccountManager::new();
        assert!((mgr.usdt_equity() - 0.0).abs() < 1e-10);
        assert!((mgr.usdt_wallet_balance() - 0.0).abs() < 1e-10);
        assert!((mgr.usdt_available() - 0.0).abs() < 1e-10);

        // Default fee rates / 默認手續費率
        let fee = mgr.get_fee_rate("BTCUSDT");
        assert!((fee.taker_fee_rate - DEFAULT_TAKER_FEE).abs() < 1e-10);
        assert!((fee.maker_fee_rate - DEFAULT_MAKER_FEE).abs() < 1e-10);
    }

    #[test]
    fn test_account_manager_fee_cache() {
        let mgr = AccountManager::new();
        {
            let mut cache = mgr.fee_rates.write().unwrap();
            cache.insert(
                "ETHUSDT".to_string(),
                FeeRate {
                    symbol: "ETHUSDT".to_string(),
                    maker_fee_rate: 0.0001,
                    taker_fee_rate: 0.0004,
                },
            );
        }
        assert!((mgr.taker_fee("ETHUSDT") - 0.0004).abs() < 1e-10);
        assert!((mgr.maker_fee("ETHUSDT") - 0.0001).abs() < 1e-10);
        // Unknown symbol falls back to default / 未知交易對回退到默認值
        assert!((mgr.taker_fee("UNKNOWN") - DEFAULT_TAKER_FEE).abs() < 1e-10);
    }

    #[test]
    fn test_wallet_state_snapshot() {
        let mgr = AccountManager::new();
        {
            let mut wallet = mgr.wallet.write().unwrap();
            wallet.total_equity = 12345.67;
            wallet.coins.insert(
                "USDT".to_string(),
                CoinBalance {
                    coin: "USDT".to_string(),
                    wallet_balance: 10000.0,
                    available_to_withdraw: 8000.0,
                    equity: 11000.0,
                    unrealised_pnl: 1000.0,
                    cum_realised_pnl: 500.0,
                },
            );
        }
        let snap = mgr.wallet_snapshot();
        assert!((snap.total_equity - 12345.67).abs() < 1e-10);
        assert!((mgr.usdt_equity() - 11000.0).abs() < 1e-10);
        assert!((mgr.usdt_wallet_balance() - 10000.0).abs() < 1e-10);
        assert!((mgr.usdt_available() - 8000.0).abs() < 1e-10);
    }

    #[test]
    fn test_default_fee_constants() {
        // Verify defaults match current Bybit VIP-0 rates (approximately)
        // 驗證默認值大約匹配當前 Bybit VIP-0 費率
        assert!(DEFAULT_TAKER_FEE > 0.0 && DEFAULT_TAKER_FEE < 0.01);
        assert!(DEFAULT_MAKER_FEE > 0.0 && DEFAULT_MAKER_FEE < 0.01);
        assert!(DEFAULT_TAKER_FEE > DEFAULT_MAKER_FEE);
    }

    #[test]
    fn test_parse_f64_various() {
        let obj = serde_json::json!({"a": "123.45", "b": "bad", "c": 999});
        assert!((parse_f64(&obj, "a") - 123.45).abs() < 1e-10);
        assert!((parse_f64(&obj, "b") - 0.0).abs() < 1e-10); // unparseable
        assert!((parse_f64(&obj, "c") - 0.0).abs() < 1e-10); // not a string
        assert!((parse_f64(&obj, "missing") - 0.0).abs() < 1e-10);
    }
}

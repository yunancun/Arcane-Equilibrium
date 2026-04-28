//! Bybit account manager — wallet balance and fee rate queries (R-05).
//! Bybit 帳戶管理器 — 錢包餘額和手續費率查詢。
//!
//! MODULE_NOTE (EN): Queries Bybit V5 account endpoints for wallet balance (UNIFIED account)
//!   and fee rates. Caches last known state for fast access. Provides USDT equity/balance
//!   extraction from the complex Bybit wallet response.
//! MODULE_NOTE (中): 查詢 Bybit V5 帳戶端點獲取錢包餘額（統一帳戶）和手續費率。
//!   緩存最後已知狀態供快速存取。從複雜的 Bybit 錢包回應中提取 USDT 權益/餘額。

use crate::bybit_rest_client::{BybitApiError, BybitRestClient, BybitResult};
use parking_lot::RwLock;
use std::collections::HashMap;
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
// AccountInfo — account configuration / 帳戶配置
// ---------------------------------------------------------------------------

/// Account configuration information.
/// 帳戶配置信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AccountInfo {
    /// Margin mode: "REGULAR_MARGIN", "PORTFOLIO_MARGIN"
    /// 保證金模式
    pub margin_mode: String,
    /// Updated timestamp / 更新時間戳
    pub updated_time: String,
    /// Unified margin status: 1=Regular, 2=Unified(trade), 3=Unified(fund), 4=UTA Pro
    /// 統一保證金狀態
    pub unified_margin_status: i32,
    /// Whether SMP (Self-Match Prevention) group is set / 是否設置了 SMP 群組
    pub smp_group: i32,
    /// Whether hedging mode is enabled / 是否啟用對沖模式
    pub is_master_trader: bool,
}

// ---------------------------------------------------------------------------
// BorrowRecord — margin borrow history / 保證金借幣歷史
// ---------------------------------------------------------------------------

/// Margin borrow history record.
/// 保證金借幣歷史記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct BorrowRecord {
    /// Currency / 幣種
    pub currency: String,
    /// Borrow amount / 借幣數量
    pub borrow_amount: f64,
    /// Cost (interest) amount / 利息金額
    pub cost_amount: f64,
    /// Borrow timestamp / 借幣時間戳
    pub created_time: String,
    /// Borrow type / 借幣類型
    pub borrow_type: String,
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
    /// Last successful fee_rate refresh timestamp (ms since epoch).
    /// 0 = never refreshed; used by quality monitor for staleness alerts.
    /// 上次成功刷新費率的時間戳（毫秒），0=從未刷新。
    last_fee_refresh_ms: std::sync::atomic::AtomicU64,
}

impl AccountManager {
    /// Create a new AccountManager with empty state.
    /// 創建新的 AccountManager（空狀態）。
    pub fn new() -> Self {
        Self {
            wallet: RwLock::new(WalletState::default()),
            fee_rates: RwLock::new(HashMap::new()),
            last_fee_refresh_ms: std::sync::atomic::AtomicU64::new(0),
        }
    }

    /// Last successful fee-rate refresh timestamp (ms since epoch). 0 = never.
    /// 上次成功刷新費率的時間戳（毫秒），0=從未刷新。
    pub fn last_fee_refresh_ms(&self) -> u64 {
        self.last_fee_refresh_ms
            .load(std::sync::atomic::Ordering::Relaxed)
    }

    #[cfg(test)]
    pub(crate) fn set_last_fee_refresh_ms_for_test(&self, ts_ms: u64) {
        self.last_fee_refresh_ms
            .store(ts_ms, std::sync::atomic::Ordering::Relaxed);
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

        *self.wallet.write() = state;
        Ok(self)
    }

    /// Get cached USDT equity (total including unrealized PnL).
    /// 取得緩存的 USDT 權益（含未實現盈虧）。
    pub fn usdt_equity(&self) -> f64 {
        self.wallet
            .read()
            .coins
            .get("USDT")
            .map_or(0.0, |c| c.equity)
    }

    /// Get cached USDT wallet balance (without unrealized PnL).
    /// 取得緩存的 USDT 錢包餘額（不含未實現盈虧）。
    pub fn usdt_wallet_balance(&self) -> f64 {
        self.wallet
            .read()
            .coins
            .get("USDT")
            .map_or(0.0, |c| c.wallet_balance)
    }

    /// Get cached USDT available balance (withdrawable).
    /// 取得緩存的 USDT 可用餘額（可提取）。
    pub fn usdt_available(&self) -> f64 {
        self.wallet
            .read()
            .coins
            .get("USDT")
            .map_or(0.0, |c| c.available_to_withdraw)
    }

    /// Get full cached wallet state snapshot.
    /// 取得完整的緩存錢包狀態快照。
    pub fn wallet_snapshot(&self) -> WalletState {
        self.wallet.read().clone()
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
        let mut cache = self.fee_rates.write();

        for item in &list {
            if let Some(rate) = parse_fee_rate_item(item) {
                cache.insert(rate.symbol.clone(), rate);
                count += 1;
            }
        }

        // Stamp success timestamp for staleness monitoring.
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;
        self.last_fee_refresh_ms
            .store(now_ms, std::sync::atomic::Ordering::Relaxed);

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
            .get(symbol)
            .map_or(DEFAULT_TAKER_FEE, |r| r.taker_fee_rate)
    }

    /// Get maker fee rate for a symbol.
    /// 取得交易對的 maker 手續費率。
    pub fn maker_fee(&self, symbol: &str) -> f64 {
        self.fee_rates
            .read()
            .get(symbol)
            .map_or(DEFAULT_MAKER_FEE, |r| r.maker_fee_rate)
    }

    // -----------------------------------------------------------------------
    // Account info / 帳戶信息
    // -----------------------------------------------------------------------

    /// Get account info (margin mode, etc.).
    /// 獲取帳戶信息（保證金模式等）。
    ///
    /// GET /v5/account/info
    pub async fn get_account_info(&self, client: &BybitRestClient) -> BybitResult<AccountInfo> {
        let resp = client.get_checked("/v5/account/info", &[]).await?;
        parse_account_info(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Hedge mode / 對沖模式
    // -----------------------------------------------------------------------

    /// Enable or disable hedge mode for the account.
    /// 啟用或禁用帳戶的對沖模式。
    ///
    /// POST /v5/account/set-hedging-mode
    /// FIX-55/BB-A2: Pre-wired, not on trading path. Path verified per Bybit V5 docs.
    ///
    /// hedging: "ON" = enable, "OFF" = disable
    /// hedging: "ON" = 啟用, "OFF" = 禁用
    #[allow(dead_code)]
    pub async fn set_hedging_mode(
        &self,
        client: &BybitRestClient,
        hedging: &str,
    ) -> BybitResult<()> {
        let body = serde_json::json!({
            "setHedgingMode": hedging,
        });

        info!(hedging = hedging, "setting hedging mode / 設置對沖模式");

        client
            .post_checked("/v5/account/set-hedging-mode", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Borrow history / 借幣歷史
    // -----------------------------------------------------------------------

    /// Get margin borrow history.
    /// 獲取保證金借幣歷史。
    ///
    /// GET /v5/account/borrow-history
    pub async fn get_borrow_history(
        &self,
        client: &BybitRestClient,
        currency: Option<&str>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<BorrowRecord>> {
        let limit_str = limit.unwrap_or(50).to_string();
        let mut params: Vec<(&str, &str)> = vec![("limit", &limit_str)];
        if let Some(c) = currency {
            params.push(("currency", c));
        }

        let resp = client
            .get_checked("/v5/account/borrow-history", &params)
            .await?;
        parse_borrow_history(&resp.result)
    }

    // -----------------------------------------------------------------------
    // Repayment / 還款
    // -----------------------------------------------------------------------

    /// Repay margin borrow.
    /// 還款保證金借幣。
    ///
    /// POST /v5/account/repay
    /// FIX-55/BB-A3: Pre-wired, not on trading path. Path verified per Bybit V5 docs.
    #[allow(dead_code)]
    pub async fn repay(&self, client: &BybitRestClient, coin: &str) -> BybitResult<()> {
        let body = serde_json::json!({
            "coin": coin,
        });

        info!(coin = coin, "repaying margin / 還款保證金");

        client.post_checked("/v5/account/repay", &body).await?;
        Ok(())
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

/// Parse a string field from JSON / 從 JSON 解析字串欄位
fn parse_str(obj: &serde_json::Value, field: &str) -> String {
    obj.get(field)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

/// Parse AccountInfo from Bybit response.
/// 從 Bybit 回應中解析帳戶信息。
fn parse_account_info(result: &serde_json::Value) -> BybitResult<AccountInfo> {
    Ok(AccountInfo {
        margin_mode: parse_str(result, "marginMode"),
        updated_time: parse_str(result, "updatedTime"),
        unified_margin_status: result
            .get("unifiedMarginStatus")
            .and_then(|v| v.as_i64())
            .unwrap_or(0) as i32,
        smp_group: result.get("smpGroup").and_then(|v| v.as_i64()).unwrap_or(0) as i32,
        is_master_trader: result
            .get("isMasterTrader")
            .and_then(|v| v.as_bool())
            .unwrap_or(false),
    })
}

/// Parse borrow history from Bybit response.
/// 從 Bybit 回應中解析借幣歷史。
fn parse_borrow_history(result: &serde_json::Value) -> BybitResult<Vec<BorrowRecord>> {
    let list = result
        .get("list")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();

    let mut records = Vec::with_capacity(list.len());
    for item in &list {
        records.push(BorrowRecord {
            currency: parse_str(item, "currency"),
            borrow_amount: parse_f64(item, "borrowAmount"),
            cost_amount: parse_f64(item, "costAmount"),
            created_time: parse_str(item, "createdTime"),
            borrow_type: parse_str(item, "borrowType"),
        });
    }
    Ok(records)
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
            let mut cache = mgr.fee_rates.write();
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
            let mut wallet = mgr.wallet.write();
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

    // -- AccountInfo tests / 帳戶信息測試 --

    #[test]
    fn test_parse_account_info() {
        let result = serde_json::json!({
            "marginMode": "REGULAR_MARGIN",
            "updatedTime": "1700000000000",
            "unifiedMarginStatus": 3,
            "smpGroup": 0,
            "isMasterTrader": false
        });
        let info = parse_account_info(&result).unwrap();
        assert_eq!(info.margin_mode, "REGULAR_MARGIN");
        assert_eq!(info.updated_time, "1700000000000");
        assert_eq!(info.unified_margin_status, 3);
        assert_eq!(info.smp_group, 0);
        assert!(!info.is_master_trader);
    }

    #[test]
    fn test_parse_account_info_defaults() {
        let result = serde_json::json!({});
        let info = parse_account_info(&result).unwrap();
        assert_eq!(info.margin_mode, "");
        assert_eq!(info.unified_margin_status, 0);
        assert!(!info.is_master_trader);
    }

    #[test]
    fn test_account_info_serde() {
        let info = AccountInfo {
            margin_mode: "PORTFOLIO_MARGIN".to_string(),
            updated_time: "1700000000000".to_string(),
            unified_margin_status: 4,
            smp_group: 1,
            is_master_trader: true,
        };
        let json = serde_json::to_string(&info).unwrap();
        let deser: AccountInfo = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.margin_mode, "PORTFOLIO_MARGIN");
        assert_eq!(deser.unified_margin_status, 4);
        assert!(deser.is_master_trader);
    }

    // -- BorrowRecord tests / 借幣記錄測試 --

    #[test]
    fn test_parse_borrow_history() {
        let result = serde_json::json!({
            "list": [
                {
                    "currency": "USDT",
                    "borrowAmount": "5000.50",
                    "costAmount": "12.35",
                    "createdTime": "1700000000000",
                    "borrowType": "auto"
                },
                {
                    "currency": "BTC",
                    "borrowAmount": "0.5",
                    "costAmount": "0.0001",
                    "createdTime": "1700000001000",
                    "borrowType": "manual"
                }
            ]
        });
        let records = parse_borrow_history(&result).unwrap();
        assert_eq!(records.len(), 2);
        assert_eq!(records[0].currency, "USDT");
        assert!((records[0].borrow_amount - 5000.50).abs() < 1e-10);
        assert!((records[0].cost_amount - 12.35).abs() < 1e-10);
        assert_eq!(records[1].currency, "BTC");
    }

    #[test]
    fn test_parse_borrow_history_empty() {
        let result = serde_json::json!({"list": []});
        let records = parse_borrow_history(&result).unwrap();
        assert!(records.is_empty());
    }

    #[test]
    fn test_borrow_record_serde() {
        let record = BorrowRecord {
            currency: "USDT".to_string(),
            borrow_amount: 5000.0,
            cost_amount: 12.0,
            created_time: "1700000000000".to_string(),
            borrow_type: "auto".to_string(),
        };
        let json = serde_json::to_string(&record).unwrap();
        let deser: BorrowRecord = serde_json::from_str(&json).unwrap();
        assert_eq!(deser.currency, "USDT");
        assert!((deser.borrow_amount - 5000.0).abs() < 1e-10);
    }
}

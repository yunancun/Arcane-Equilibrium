//! Bybit V5 platform client — account management and platform endpoints (R-05).
//! Bybit V5 平台客戶端 — 帳戶管理和平台端點。
//!
//! MODULE_NOTE (EN): Platform-level operations beyond trading: margin mode, collateral,
//!   DCP (Disconnected Cancel Protection), inter-account transfers, transaction log,
//!   system status, and demo fund requests. These endpoints are critical for account
//!   safety (DCP), audit trail (transaction log), and capital management (transfers).
//! MODULE_NOTE (中): 超越交易的平台級操作：保證金模式、抵押品、DCP（斷連取消保護）、
//!   帳戶間轉帳、交易日誌、系統狀態和 Demo 資金申請。這些端點對帳戶安全（DCP）、
//!   審計追蹤（交易日誌）和資金管理（轉帳）至關重要。

use crate::bybit_rest_client::{BybitRestClient, BybitResult};
use std::sync::Arc;
use tracing::debug;

// ---------------------------------------------------------------------------
// Response structs / 回應結構體
// ---------------------------------------------------------------------------

/// System maintenance status record.
/// 系統維護狀態記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct SystemStatus {
    /// Title of the event / 事件標題
    pub title: String,
    /// Start time of maintenance / 維護開始時間
    pub start_time: String,
    /// End time of maintenance / 維護結束時間
    pub end_time: String,
    /// Status: "completed", "ongoing", "upcoming" / 狀態
    pub status: String,
}

/// Transaction log record — full audit trail.
/// 交易日誌記錄 — 完整審計追蹤。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TransactionRecord {
    /// Transaction ID / 交易 ID
    pub id: String,
    /// Symbol (if applicable) / 交易對
    pub symbol: String,
    /// Category: "linear", "spot", etc. / 品類
    pub category: String,
    /// Transaction type: "TRADE", "SETTLEMENT", "TRANSFER", etc.
    /// 交易類型
    pub r#type: String,
    /// Quantity / 數量
    pub qty: String,
    /// Cash flow amount / 現金流金額
    pub cash_flow: String,
    /// Currency / 幣種
    pub currency: String,
    /// Transaction time / 交易時間
    pub transaction_time: String,
}

/// Collateral info for a coin.
/// 幣種抵押品信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CollateralInfo {
    /// Currency / 幣種
    pub currency: String,
    /// Whether this coin can be used as collateral / 是否可用作抵押品
    pub collateral_switch: bool,
    /// Borrowable or not / 是否可借
    pub borrowable: bool,
    /// Collateral ratio / 抵押率
    pub collateral_ratio: String,
    /// Free amount available as collateral / 可用作抵押的空閒金額
    pub free_collateral: String,
}

/// DCP (Disconnected Cancel Protection) info.
/// DCP（斷連取消保護）信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DcpInfo {
    /// Whether DCP is enabled / DCP 是否啟用
    pub dcp_status: String,
    /// Time window in seconds / 時間窗口（秒）
    pub time_window: u32,
}

/// Inter-account transfer record.
/// 帳戶間轉帳記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct TransferRecord {
    /// Transfer ID / 轉帳 ID
    pub transfer_id: String,
    /// Coin / 幣種
    pub coin: String,
    /// Amount / 金額
    pub amount: String,
    /// From account type / 來源帳戶類型
    pub from_account_type: String,
    /// To account type / 目標帳戶類型
    pub to_account_type: String,
    /// Timestamp / 時間戳
    pub timestamp: String,
    /// Status / 狀態
    pub status: String,
}

/// Account coin balance (for asset queries).
/// 帳戶幣種餘額（資產查詢用）。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct AccountCoinBalance {
    /// Coin name / 幣種名稱
    pub coin: String,
    /// Wallet balance / 錢包餘額
    pub wallet_balance: String,
    /// Transfer balance (available for transfer) / 可轉帳餘額
    pub transfer_balance: String,
}

/// Coin information record.
/// 幣種信息記錄。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct CoinInfoRecord {
    /// Coin name / 幣種名稱
    pub coin: String,
    /// Full coin name / 幣種全名
    pub name: String,
    /// Remaining amount available for withdrawal / 剩餘可提取金額
    pub remain_amount: String,
    /// Chain information / 鏈信息
    pub chains: Vec<ChainInfo>,
}

/// Chain information for a coin.
/// 幣種的鏈信息。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ChainInfo {
    /// Chain name, e.g. "ETH" / 鏈名稱
    pub chain: String,
    /// Chain type / 鏈類型
    pub chain_type: String,
    /// Required confirmations / 所需確認數
    pub confirmation: String,
    /// Minimum precision / 最小精度
    pub min_accuracy: String,
    /// Deposit status: "0"=off, "1"=on / 充值狀態
    pub chain_deposit: String,
    /// Withdraw status: "0"=off, "1"=on / 提現狀態
    pub chain_withdraw: String,
}

/// Demo fund request item.
/// Demo 資金申請項目。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct DemoFundRequest {
    /// Coin to request / 申請幣種
    pub coin: String,
    /// Amount to request as string / 申請金額字串
    pub amount: String,
}

// ---------------------------------------------------------------------------
// PlatformClient / 平台客戶端
// ---------------------------------------------------------------------------

/// Client for Bybit V5 platform and account management endpoints.
/// Bybit V5 平台和帳戶管理端點的客戶端。
///
/// Thread-safe: wraps BybitRestClient in Arc.
/// 線程安全：通過 Arc 包裝 BybitRestClient。
pub struct PlatformClient {
    client: Arc<BybitRestClient>,
}

impl PlatformClient {
    /// Create a new PlatformClient wrapping a shared REST client.
    /// 創建新的 PlatformClient，包裝共享的 REST 客戶端。
    pub fn new(client: Arc<BybitRestClient>) -> Self {
        Self { client }
    }

    // -----------------------------------------------------------------------
    // Transaction log / 交易日誌
    // -----------------------------------------------------------------------

    /// Get transaction log — full audit trail of account activity.
    /// 獲取交易日誌 — 帳戶活動的完整審計追蹤。
    ///
    /// GET /v5/account/transaction-log
    pub async fn get_transaction_log(
        &self,
        account_type: &str,
        category: Option<&str>,
        start: Option<u64>,
        end: Option<u64>,
        limit: Option<u32>,
    ) -> BybitResult<Vec<TransactionRecord>> {
        debug!("fetching transaction log / 獲取交易日誌");
        let mut params: Vec<(&str, String)> = vec![("accountType", account_type.to_string())];
        if let Some(c) = category {
            params.push(("category", c.to_string()));
        }
        if let Some(s) = start {
            params.push(("startTime", s.to_string()));
        }
        if let Some(e) = end {
            params.push(("endTime", e.to_string()));
        }
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/account/transaction-log", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(TransactionRecord {
                id: parse_str(item, "id"),
                symbol: parse_str(item, "symbol"),
                category: parse_str(item, "category"),
                r#type: parse_str(item, "type"),
                qty: parse_str(item, "qty"),
                cash_flow: parse_str(item, "cashFlow"),
                currency: parse_str(item, "currency"),
                transaction_time: parse_str(item, "transactionTime"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Margin mode / 保證金模式
    // -----------------------------------------------------------------------

    /// Set margin mode — isolated, cross, or portfolio margin.
    /// 設置保證金模式 — 逐倉、全倉或組合保證金。
    ///
    /// POST /v5/account/set-margin-mode
    pub async fn set_margin_mode(&self, mode: &str) -> BybitResult<()> {
        debug!(mode = mode, "setting margin mode / 設置保證金模式");
        let body = serde_json::json!({"setMarginMode": mode});
        self.client
            .post_checked("/v5/account/set-margin-mode", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // Collateral / 抵押品
    // -----------------------------------------------------------------------

    /// Get collateral info — which coins are configured as collateral.
    /// 獲取抵押品信息 — 哪些幣種被配置為抵押品。
    ///
    /// GET /v5/account/collateral-info
    pub async fn get_collateral_info(
        &self,
        currency: Option<&str>,
    ) -> BybitResult<Vec<CollateralInfo>> {
        debug!("fetching collateral info / 獲取抵押品信息");
        let mut params: Vec<(&str, &str)> = Vec::new();
        if let Some(c) = currency {
            params.push(("currency", c));
        }
        let resp = self
            .client
            .get_checked("/v5/account/collateral-info", &params)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut infos = Vec::with_capacity(list.len());
        for item in &list {
            infos.push(CollateralInfo {
                currency: parse_str(item, "currency"),
                collateral_switch: item
                    .get("collateralSwitch")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false),
                borrowable: item
                    .get("borrowable")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false),
                collateral_ratio: parse_str(item, "collateralRatio"),
                free_collateral: parse_str(item, "freeCollateral"),
            });
        }
        Ok(infos)
    }

    /// Set collateral switch for a coin — enable/disable as collateral.
    /// 設置幣種抵押品開關 — 啟用/禁用作為抵押品。
    ///
    /// POST /v5/account/set-collateral
    pub async fn set_collateral_switch(&self, coin: &str, switch: bool) -> BybitResult<()> {
        debug!(
            coin = coin,
            switch = switch,
            "setting collateral switch / 設置抵押品開關"
        );
        let body = serde_json::json!({
            "coin": coin,
            "collateralSwitch": if switch { "ON" } else { "OFF" }
        });
        self.client
            .post_checked("/v5/account/set-collateral", &body)
            .await?;
        Ok(())
    }

    // -----------------------------------------------------------------------
    // DCP — Disconnected Cancel Protection / 斷連取消保護
    // -----------------------------------------------------------------------

    /// Set DCP (Disconnected Cancel All) — safety net for connection loss.
    /// 設置 DCP（斷連取消所有）— 連接中斷的安全網。
    ///
    /// POST /v5/order/disconnected-cancel-all
    pub async fn set_dcp(&self, time_window: u32) -> BybitResult<()> {
        debug!(time_window = time_window, "setting DCP / 設置 DCP");
        let body = serde_json::json!({"timeWindow": time_window});
        self.client
            .post_checked("/v5/order/disconnected-cancel-all", &body)
            .await?;
        Ok(())
    }

    /// Query DCP info — current DCP configuration.
    /// 查詢 DCP 信息 — 當前 DCP 配置。
    ///
    /// GET /v5/account/dcp-info
    pub async fn get_dcp_info(&self) -> BybitResult<DcpInfo> {
        debug!("fetching DCP info / 獲取 DCP 信息");
        let resp = self.client.get_checked("/v5/account/dcp-info", &[]).await?;
        Ok(DcpInfo {
            dcp_status: parse_str(&resp.result, "dcpStatus"),
            time_window: resp
                .result
                .get("timeWindow")
                .and_then(|v| v.as_u64())
                .unwrap_or(0) as u32,
        })
    }

    // -----------------------------------------------------------------------
    // Order pre-check / 訂單預檢
    // -----------------------------------------------------------------------

    /// Pre-check order — validate order params without submitting.
    // FIX-20: pre_check_order() removed — it called the real /v5/order/create
    // endpoint (Bybit has no dry-run), risking accidental order placement in Live.
    // FIX-20：pre_check_order() 已移除 — 它調用真實下單端點（Bybit 無 dry-run），
    // Live 模式下有意外下單風險。

    // -----------------------------------------------------------------------
    // Inter-account transfers / 帳戶間轉帳
    // -----------------------------------------------------------------------

    /// Inter-account transfer — move funds between account types.
    /// 帳戶間轉帳 — 在帳戶類型之間移動資金。
    ///
    /// POST /v5/asset/transfer/inter-transfer
    pub async fn inter_transfer(
        &self,
        coin: &str,
        amount: f64,
        from_account: &str,
        to_account: &str,
    ) -> BybitResult<String> {
        debug!(
            coin = coin,
            amount = amount,
            from = from_account,
            to = to_account,
            "inter-account transfer / 帳戶間轉帳"
        );
        // Generate a UUID-like transfer ID from timestamp
        // 從時間戳生成 UUID-like 轉帳 ID
        let transfer_id = format!(
            "oc-{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_nanos()
        );
        let body = serde_json::json!({
            "transferId": transfer_id,
            "coin": coin,
            "amount": format!("{amount}"),
            "fromAccountType": from_account,
            "toAccountType": to_account
        });
        let resp = self
            .client
            .post_checked("/v5/asset/transfer/inter-transfer", &body)
            .await?;
        let result_id = resp
            .result
            .get("transferId")
            .and_then(|v| v.as_str())
            .unwrap_or(&transfer_id)
            .to_string();
        Ok(result_id)
    }

    /// Get transfer list — query inter-account transfer history.
    /// 獲取轉帳列表 — 查詢帳戶間轉帳歷史。
    ///
    /// GET /v5/asset/transfer/query-inter-transfer-list
    pub async fn get_transfer_list(&self, limit: Option<u32>) -> BybitResult<Vec<TransferRecord>> {
        debug!("fetching transfer list / 獲取轉帳列表");
        let mut params: Vec<(&str, String)> = Vec::new();
        if let Some(l) = limit {
            params.push(("limit", l.to_string()));
        }
        let param_refs: Vec<(&str, &str)> = params.iter().map(|(k, v)| (*k, v.as_str())).collect();
        let resp = self
            .client
            .get_checked("/v5/asset/transfer/query-inter-transfer-list", &param_refs)
            .await?;
        let list = resp
            .result
            .get("list")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(list.len());
        for item in &list {
            records.push(TransferRecord {
                transfer_id: parse_str(item, "transferId"),
                coin: parse_str(item, "coin"),
                amount: parse_str(item, "amount"),
                from_account_type: parse_str(item, "fromAccountType"),
                to_account_type: parse_str(item, "toAccountType"),
                timestamp: parse_str(item, "timestamp"),
                status: parse_str(item, "status"),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Asset balances / 資產餘額
    // -----------------------------------------------------------------------

    /// Get all account coin balances — comprehensive view of all assets.
    /// 獲取所有帳戶幣種餘額 — 所有資產的全面視圖。
    ///
    /// GET /v5/asset/transfer/query-account-coins-balance
    pub async fn get_all_account_balances(
        &self,
        account_type: &str,
    ) -> BybitResult<Vec<AccountCoinBalance>> {
        debug!(
            account_type = account_type,
            "fetching all account balances / 獲取所有帳戶餘額"
        );
        let params: Vec<(&str, &str)> = vec![("accountType", account_type)];
        let resp = self
            .client
            .get_checked("/v5/asset/transfer/query-account-coins-balance", &params)
            .await?;
        let list = resp
            .result
            .get("balance")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut balances = Vec::with_capacity(list.len());
        for item in &list {
            balances.push(AccountCoinBalance {
                coin: parse_str(item, "coin"),
                wallet_balance: parse_str(item, "walletBalance"),
                transfer_balance: parse_str(item, "transferBalance"),
            });
        }
        Ok(balances)
    }

    // -----------------------------------------------------------------------
    // Coin info / 幣種信息
    // -----------------------------------------------------------------------

    /// Get coin information — chain details, precision, deposit/withdrawal status.
    /// 獲取幣種信息 — 鏈詳情、精度、充提狀態。
    ///
    /// GET /v5/asset/coin-info
    pub async fn get_coin_info(&self, coin: Option<&str>) -> BybitResult<Vec<CoinInfoRecord>> {
        debug!("fetching coin info / 獲取幣種信息");
        let mut params: Vec<(&str, &str)> = vec![];
        if let Some(c) = coin {
            params.push(("coin", c));
        }
        let resp = self
            .client
            .get_checked("/v5/asset/coin-info", &params)
            .await?;
        let rows = resp
            .result
            .get("rows")
            .and_then(|v| v.as_array())
            .cloned()
            .unwrap_or_default();
        let mut records = Vec::with_capacity(rows.len());
        for item in &rows {
            records.push(CoinInfoRecord {
                coin: parse_str(item, "coin"),
                name: parse_str(item, "name"),
                remain_amount: parse_str(item, "remainAmount"),
                chains: item
                    .get("chains")
                    .and_then(|v| v.as_array())
                    .map(|arr| {
                        arr.iter()
                            .map(|c| ChainInfo {
                                chain: parse_str(c, "chain"),
                                chain_type: parse_str(c, "chainType"),
                                confirmation: parse_str(c, "confirmation"),
                                min_accuracy: parse_str(c, "minAccuracy"),
                                chain_deposit: parse_str(c, "chainDeposit"),
                                chain_withdraw: parse_str(c, "chainWithdraw"),
                            })
                            .collect()
                    })
                    .unwrap_or_default(),
            });
        }
        Ok(records)
    }

    // -----------------------------------------------------------------------
    // Demo funds / Demo 資金
    // -----------------------------------------------------------------------

    /// Apply for demo/testnet funds — for testing purposes only.
    /// 申請 Demo/測試網資金 — 僅用於測試。
    ///
    /// POST /v5/account/demo-apply-money
    pub async fn apply_demo_funds(&self, coins: Vec<DemoFundRequest>) -> BybitResult<()> {
        debug!(count = coins.len(), "applying demo funds / 申請 Demo 資金");
        let utc_list: Vec<serde_json::Value> = coins
            .iter()
            .map(|c| {
                serde_json::json!({
                    "coin": c.coin,
                    "amountStr": c.amount
                })
            })
            .collect();
        let body = serde_json::json!({"utaList": utc_list});
        self.client
            .post_checked("/v5/account/demo-apply-money", &body)
            .await?;
        Ok(())
    }
}

// ---------------------------------------------------------------------------
// Parsing helpers / 解析輔助函數
// ---------------------------------------------------------------------------

/// Parse a string field from a JSON value, returning empty string on failure.
/// 從 JSON 值中解析字串欄位，失敗時返回空字串。
fn parse_str(obj: &serde_json::Value, field: &str) -> String {
    obj.get(field)
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string()
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Test parsing transaction log records.
    /// 測試解析交易日誌記錄。
    #[test]
    fn test_parse_transaction_record() {
        let item = serde_json::json!({
            "id": "txn-001",
            "symbol": "BTCUSDT",
            "category": "linear",
            "type": "TRADE",
            "qty": "0.01",
            "cashFlow": "-650.00",
            "currency": "USDT",
            "transactionTime": "1700000000000"
        });
        let rec = TransactionRecord {
            id: parse_str(&item, "id"),
            symbol: parse_str(&item, "symbol"),
            category: parse_str(&item, "category"),
            r#type: parse_str(&item, "type"),
            qty: parse_str(&item, "qty"),
            cash_flow: parse_str(&item, "cashFlow"),
            currency: parse_str(&item, "currency"),
            transaction_time: parse_str(&item, "transactionTime"),
        };
        assert_eq!(rec.id, "txn-001");
        assert_eq!(rec.symbol, "BTCUSDT");
        assert_eq!(rec.r#type, "TRADE");
        assert_eq!(rec.cash_flow, "-650.00");
    }

    /// Test CollateralInfo struct construction.
    /// 測試 CollateralInfo 結構體構造。
    #[test]
    fn test_collateral_info() {
        let info = CollateralInfo {
            currency: "USDT".to_string(),
            collateral_switch: true,
            borrowable: false,
            collateral_ratio: "0.95".to_string(),
            free_collateral: "10000".to_string(),
        };
        assert!(info.collateral_switch);
        assert!(!info.borrowable);
        assert_eq!(info.currency, "USDT");
    }

    /// Test DcpInfo defaults.
    /// 測試 DcpInfo 默認值。
    #[test]
    fn test_dcp_info() {
        let info = DcpInfo {
            dcp_status: "ON".to_string(),
            time_window: 10,
        };
        assert_eq!(info.dcp_status, "ON");
        assert_eq!(info.time_window, 10);
    }

    /// Test TransferRecord struct.
    /// 測試 TransferRecord 結構體。
    #[test]
    fn test_transfer_record() {
        let rec = TransferRecord {
            transfer_id: "xfer-001".to_string(),
            coin: "USDT".to_string(),
            amount: "1000".to_string(),
            from_account_type: "UNIFIED".to_string(),
            to_account_type: "CONTRACT".to_string(),
            timestamp: "1700000000000".to_string(),
            status: "SUCCESS".to_string(),
        };
        assert_eq!(rec.transfer_id, "xfer-001");
        assert_eq!(rec.from_account_type, "UNIFIED");
        assert_eq!(rec.status, "SUCCESS");
    }

    /// Test AccountCoinBalance struct.
    /// 測試 AccountCoinBalance 結構體。
    #[test]
    fn test_account_coin_balance() {
        let bal = AccountCoinBalance {
            coin: "BTC".to_string(),
            wallet_balance: "0.5".to_string(),
            transfer_balance: "0.3".to_string(),
        };
        assert_eq!(bal.coin, "BTC");
        assert_eq!(bal.wallet_balance, "0.5");
    }

    /// Test DemoFundRequest struct and JSON serialization.
    /// 測試 DemoFundRequest 結構體和 JSON 序列化。
    #[test]
    fn test_demo_fund_request_serde() {
        let req = DemoFundRequest {
            coin: "USDT".to_string(),
            amount: "10000".to_string(),
        };
        let json = serde_json::to_value(&req).unwrap();
        assert_eq!(json["coin"], "USDT");
        assert_eq!(json["amount"], "10000");
        let deser: DemoFundRequest = serde_json::from_value(json).unwrap();
        assert_eq!(deser.coin, "USDT");
    }

    /// Test SystemStatus struct.
    /// 測試 SystemStatus 結構體。
    #[test]
    fn test_system_status() {
        let status = SystemStatus {
            title: "Scheduled maintenance".to_string(),
            start_time: "2026-04-03T00:00:00Z".to_string(),
            end_time: "2026-04-03T02:00:00Z".to_string(),
            status: "upcoming".to_string(),
        };
        assert_eq!(status.status, "upcoming");
        assert!(status.title.contains("maintenance"));
    }

    /// Test parse_str helper with edge cases.
    /// 測試 parse_str 輔助函數的邊界情況。
    #[test]
    fn test_parse_str_edge_cases() {
        let obj = serde_json::json!({"a": "value", "b": 123, "c": null});
        assert_eq!(parse_str(&obj, "a"), "value");
        assert_eq!(parse_str(&obj, "b"), ""); // number, not string
        assert_eq!(parse_str(&obj, "c"), ""); // null
        assert_eq!(parse_str(&obj, "missing"), "");
    }
}

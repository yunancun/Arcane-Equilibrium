//! IBKR **W5-S1 executions row 契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W5-S1 交付的**行契約層**：`reqExecutions`（execDetails 回報）單筆成交行的
//! typed 承載 shape,供 W5-S3 消化層填值——「先契約後消化,禁裸 map」。不開 socket、
//! 不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO;純資料 + 純函數。
//!
//! **side 白名單紀律（fail-closed）**：wire side 字串按 IBKR 官方 Execution.side 慣例
//! （`"BOT"`=買/`"SLD"`=賣;出典:官方 TWS API executions_commissions 文檔,
//! https://interactivebrokers.github.io/tws-api/executions_commissions.html）;表外一律
//! `UnknownDenied` 拒。W5-S3 消化接線前由 IB 現勘腿覆核逐字串。
//!
//! **id 語義紀律**：`exec_id` 為與 commissions-row 的關聯鍵（非空必填）;`order_id`/
//! `perm_id` 為 wire 原值 i64 承載——其取值域（如他端 client 訂單的 order_id 形態）屬
//! UNVERIFIED 外部語義,**本契約不鑄其不變量**,由 W5-S3 消化現勘後再 pin（loop §2）。
//!
//! **時間欄保真**：`exec_time` 承 wire 原字串（非空);其格式/時區慣例不在本契約 pin
//! （UNVERIFIED 不升格為斷言）,解析歸 W5-S3 消化層帶現勘出典落地。數量/價格一律定點
//! 字串,禁 f64。
//!
//! **instrument identity 束**：execDetails wire 回報同時攜帶 Contract 物件——本契約
//! 承其 con_id/symbol/sec_type/currency 四欄,沿 positions-row 同款 STK-only secType
//! 白名單與 symbol 規範化（margin/options/cfd 的型別層投影拒;E2 F2 補齊）。

use serde::{Deserialize, Serialize};

use crate::ibkr_account_summary_row::is_positive_decimal_string;
use crate::ibkr_positions_row::{is_normalized_symbol, IbkrSecTypeV1};
use crate::stock_etf_instrument_identity::StockEtfCurrency;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_EXECUTIONS_ROW_CONTRACT_ID: &str = "ibkr_executions_row_v1";

/// 成交方向白名單枚舉（wire `"BOT"`/`"SLD"`;表外 fail-closed 拒）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrExecutionSideV1 {
    /// 買入（wire `"BOT"`）。
    Bought,
    /// 賣出（wire `"SLD"`;本 lane 僅平多——short 拒斥由 positions/order 面把守,
    /// 成交行誠實承載方向本身）。
    Sold,
    /// 契約 default / 白名單外 side 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrExecutionSideV1 {
    fn default() -> Self {
        // fail-closed 預設＝未知拒。
        Self::UnknownDenied
    }
}

impl IbkrExecutionSideV1 {
    /// wire side 字串 → 白名單枚舉（**大小寫敏感精確匹配**;表外一律 `UnknownDenied`）。
    pub fn classify_wire_side(raw: &str) -> Self {
        match raw {
            "BOT" => Self::Bought,
            "SLD" => Self::Sold,
            _ => Self::UnknownDenied,
        }
    }

    /// 白名單枚舉 → wire side 字串（`UnknownDenied` 無 wire 對應 → `None`）。
    pub fn as_wire_side(&self) -> Option<&'static str> {
        match self {
            Self::Bought => Some("BOT"),
            Self::Sold => Some("SLD"),
            Self::UnknownDenied => None,
        }
    }
}

/// `reqExecutions` 單筆成交行 typed 契約（W5-S3 消化層的唯一合法承載;禁裸 map）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrExecutionsRowV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// 帳戶 id（非空;DU*/live 判定歸 W5-S4 attestation）。
    pub account_id: String,
    /// 成交唯一鍵（非空;與 commissions-row 的關聯鍵）。
    pub exec_id: String,
    // ---- instrument identity 束（execDetails wire 的 Contract 物件投影）----
    /// IBKR contract id（con_id;正整數）。
    pub con_id: i64,
    /// 標的代碼（非空;規範化規則同 positions-row）。
    pub symbol: String,
    /// secType 白名單（STK-only,同 positions-row;`UnknownDenied` 即 blocker）。
    pub sec_type: IbkrSecTypeV1,
    /// 幣別（lane 白名單=USD）。
    pub currency: StockEtfCurrency,
    /// client 側訂單 id（wire 原值承載;取值域不變量由 W5-S3 現勘後 pin,見模組註解）。
    pub order_id: i64,
    /// 跨 session 穩定訂單 id（wire 原值承載;同上不鑄 UNVERIFIED 不變量）。
    pub perm_id: i64,
    /// 成交時間 wire 原字串（非空;格式/時區不在本契約 pin,解析歸 W5-S3）。
    pub exec_time: String,
    /// 成交方向白名單（`UnknownDenied` 即 blocker——fail-closed）。
    pub side: IbkrExecutionSideV1,
    /// 成交數量（定點字串;嚴格正）。
    pub shares_decimal: String,
    /// 成交價（定點字串;嚴格正;禁 f64）。
    pub price_decimal: String,
    /// 成交交易所（非空;wire 原字串保真）。
    pub exchange: String,
    // ---- 負空間安全束（row 為唯讀事實,恆 false）----
    /// row 承載過程永不路由訂單。
    pub order_routed: bool,
    /// row 永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrExecutionsRowV1 {
    /// fail-closed 預設（空鍵 / 未知 side / 空 decimal——校驗必拒）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            account_id: String::new(),
            exec_id: String::new(),
            con_id: 0,
            symbol: String::new(),
            sec_type: IbkrSecTypeV1::UnknownDenied,
            currency: StockEtfCurrency::UnknownDenied,
            order_id: 0,
            perm_id: 0,
            exec_time: String::new(),
            side: IbkrExecutionSideV1::UnknownDenied,
            shares_decimal: String::new(),
            price_decimal: String::new(),
            exchange: String::new(),
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrExecutionsRowV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;`exec_time` 為占位樣式字串,
    /// 不含牆鐘依賴,格式不被本契約斷言）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_EXECUTIONS_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            account_id: "DU0000001".to_string(),
            exec_id: "0000e0d5.0001.01".to_string(),
            con_id: 756733,
            symbol: "SPY".to_string(),
            sec_type: IbkrSecTypeV1::Stk,
            currency: StockEtfCurrency::Usd,
            order_id: 7,
            perm_id: 1_000_001,
            exec_time: "fixture_exec_time".to_string(),
            side: IbkrExecutionSideV1::Bought,
            shares_decimal: "100".to_string(),
            price_decimal: "412.35".to_string(),
            exchange: "ARCA".to_string(),
            ..Self::default()
        }
    }

    /// 行級校驗（零副作用;fail-closed:未知 side、空鍵、非正 decimal 一律拒）。
    pub fn validate(&self) -> IbkrExecutionsRowVerdict {
        use IbkrExecutionsRowBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_EXECUTIONS_ROW_CONTRACT_ID {
            blockers.push(B::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(B::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(B::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(B::WrongBroker);
        }
        if self.account_id.trim().is_empty() {
            blockers.push(B::AccountIdMissing);
        }
        if self.exec_id.trim().is_empty() {
            blockers.push(B::ExecIdMissing);
        }
        // instrument identity 束（沿 positions-row 同款 fail-closed 白名單）。
        if self.con_id <= 0 {
            blockers.push(B::ConIdInvalid);
        }
        if !is_normalized_symbol(&self.symbol) {
            blockers.push(B::SymbolInvalid);
        }
        if self.sec_type == IbkrSecTypeV1::UnknownDenied {
            blockers.push(B::SecTypeUnknownDenied);
        }
        if self.currency != StockEtfCurrency::Usd {
            blockers.push(B::CurrencyDenied);
        }
        if self.exec_time.trim().is_empty() {
            blockers.push(B::ExecTimeMissing);
        }
        if self.side == IbkrExecutionSideV1::UnknownDenied {
            blockers.push(B::SideUnknownDenied);
        }
        if !is_positive_decimal_string(&self.shares_decimal) {
            blockers.push(B::SharesDecimalInvalid);
        }
        if !is_positive_decimal_string(&self.price_decimal) {
            blockers.push(B::PriceDecimalInvalid);
        }
        if self.exchange.trim().is_empty() {
            blockers.push(B::ExchangeMissing);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrExecutionsRowVerdict::new(blockers)
    }
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrExecutionsRowVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrExecutionsRowBlocker>,
}

impl IbkrExecutionsRowVerdict {
    pub fn new(blockers: Vec<IbkrExecutionsRowBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrExecutionsRowBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    AccountIdMissing,
    ExecIdMissing,
    ConIdInvalid,
    SymbolInvalid,
    SecTypeUnknownDenied,
    CurrencyDenied,
    ExecTimeMissing,
    SideUnknownDenied,
    SharesDecimalInvalid,
    PriceDecimalInvalid,
    ExchangeMissing,
    OrderRouted,
    SecretContentSerialized,
}

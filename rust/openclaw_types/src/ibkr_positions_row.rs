//! IBKR **W5-S1 positions row 契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W5-S1 交付的**行契約層**：`reqPositions` 回報行（account/contract 識別/
//! position/avgCost）的 typed 承載 shape,供 W5-S2 消化層填值——「先契約後消化,禁裸 map」。
//! 不開 socket、不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO;純資料 + 純函數。
//!
//! **secType 白名單紀律（fail-closed）**：本 lane 只承 STK/ETF 範疇——按 IBKR 官方 API
//! 慣例 ETF 於 wire 上以 secType `"STK"` 表示（無獨立 "ETF" secType）,故 wire 白名單=
//! `"STK"` 單值;其餘 secType（OPT/FUT/CASH/CFD/BOND…）一律 `UnknownDenied` 拒
//! （margin/short/options/cfd 永久 denied 的型別層投影）。出典:官方 TWS API 文檔慣例
//! （https://interactivebrokers.github.io/tws-api/）;W5-S2 消化接線前由 IB 現勘腿覆核。
//!
//! **short 拒斥**：`position_decimal` 只承非負（short 永久 denied;負倉即 blocker）;
//! 零倉允許（平倉後 flat row 的誠實表示）。money/數量一律定點字串,禁 f64。

use serde::{Deserialize, Serialize};

use crate::ibkr_account_summary_row::is_nonnegative_decimal_string;
use crate::stock_etf_instrument_identity::StockEtfCurrency;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_POSITIONS_ROW_CONTRACT_ID: &str = "ibkr_positions_row_v1";

/// secType 白名單枚舉（本 lane 只 STK/ETF 範疇;wire 上兩者皆 `"STK"`,見模組註解）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrSecTypeV1 {
    /// 股票/ETF（wire `"STK"`;IBKR 慣例 ETF 亦為 STK）。
    Stk,
    /// 契約 default / 白名單外 secType 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrSecTypeV1 {
    fn default() -> Self {
        // fail-closed 預設＝未知拒。
        Self::UnknownDenied
    }
}

impl IbkrSecTypeV1 {
    /// wire secType 字串 → 白名單枚舉（**大小寫敏感精確匹配**;表外一律 `UnknownDenied`）。
    pub fn classify_wire_sec_type(raw: &str) -> Self {
        match raw {
            "STK" => Self::Stk,
            _ => Self::UnknownDenied,
        }
    }

    /// 白名單枚舉 → wire secType 字串（`UnknownDenied` 無 wire 對應 → `None`）。
    pub fn as_wire_sec_type(&self) -> Option<&'static str> {
        match self {
            Self::Stk => Some("STK"),
            Self::UnknownDenied => None,
        }
    }
}

/// `reqPositions` 單行 typed 契約（W5-S2 消化層的唯一合法承載;禁裸 map）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPositionsRowV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// 帳戶 id（非空;DU*/live 判定歸 W5-S4 attestation,本契約不自判）。
    pub account_id: String,
    /// IBKR contract id（con_id;正整數）。
    pub con_id: i64,
    /// 標的代碼（非空;規範化:大寫/數字/`.`/`-`,長度 ≤24,沿 paper-order 契約同款規則）。
    pub symbol: String,
    /// secType 白名單（`UnknownDenied` 即 blocker——fail-closed）。
    pub sec_type: IbkrSecTypeV1,
    /// 幣別（lane 白名單=USD）。
    pub currency: StockEtfCurrency,
    /// 交易所欄（非空;wire 原字串保真,venue 白名單語義歸 instrument-identity 契約）。
    pub exchange: String,
    /// 持倉數量（定點字串;**非負**——short 永久 denied,負倉即 blocker;零倉允許）。
    pub position_decimal: String,
    /// 平均成本（定點字串;非負;禁 f64）。
    pub avg_cost_decimal: String,
    // ---- 負空間安全束（row 為唯讀事實,恆 false）----
    /// row 承載過程永不路由訂單。
    pub order_routed: bool,
    /// row 永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrPositionsRowV1 {
    /// fail-closed 預設（空 id / 未知 secType / 未知幣別——校驗必拒）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            account_id: String::new(),
            con_id: 0,
            symbol: String::new(),
            sec_type: IbkrSecTypeV1::UnknownDenied,
            currency: StockEtfCurrency::UnknownDenied,
            exchange: String::new(),
            position_decimal: String::new(),
            avg_cost_decimal: String::new(),
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrPositionsRowV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_POSITIONS_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            account_id: "DU0000001".to_string(),
            con_id: 756733,
            symbol: "SPY".to_string(),
            sec_type: IbkrSecTypeV1::Stk,
            currency: StockEtfCurrency::Usd,
            exchange: "ARCA".to_string(),
            position_decimal: "100".to_string(),
            avg_cost_decimal: "412.35".to_string(),
            ..Self::default()
        }
    }

    /// 行級校驗（零副作用;fail-closed:未知 secType/幣別、負倉、非法 decimal 一律拒）。
    pub fn validate(&self) -> IbkrPositionsRowVerdict {
        use IbkrPositionsRowBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_POSITIONS_ROW_CONTRACT_ID {
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
        if self.exchange.trim().is_empty() {
            blockers.push(B::ExchangeMissing);
        }
        // 非負檢查即 short 拒斥:負倉字串（前導 `-`）在此必然失敗。
        if !is_nonnegative_decimal_string(&self.position_decimal) {
            if self.position_decimal.starts_with('-') {
                blockers.push(B::ShortPositionDenied);
            } else {
                blockers.push(B::PositionDecimalInvalid);
            }
        }
        if !is_nonnegative_decimal_string(&self.avg_cost_decimal) {
            blockers.push(B::AvgCostDecimalInvalid);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrPositionsRowVerdict::new(blockers)
    }
}

/// 規範化 symbol 檢查（沿 paper-order 契約同款規則:非空、≤24、無前後空白、
/// 僅大寫字母/數字/`.`/`-`;W5-S1 row 家族共用,executions-row 亦消費）。
pub fn is_normalized_symbol(symbol: &str) -> bool {
    let trimmed = symbol.trim();
    !trimmed.is_empty()
        && trimmed.len() <= 24
        && trimmed == symbol
        && trimmed
            .bytes()
            .all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || matches!(b, b'.' | b'-'))
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrPositionsRowVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrPositionsRowBlocker>,
}

impl IbkrPositionsRowVerdict {
    pub fn new(blockers: Vec<IbkrPositionsRowBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrPositionsRowBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    AccountIdMissing,
    ConIdInvalid,
    SymbolInvalid,
    SecTypeUnknownDenied,
    CurrencyDenied,
    ExchangeMissing,
    ShortPositionDenied,
    PositionDecimalInvalid,
    AvgCostDecimalInvalid,
    OrderRouted,
    SecretContentSerialized,
}

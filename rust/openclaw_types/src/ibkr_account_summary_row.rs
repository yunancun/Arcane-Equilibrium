//! IBKR **W5-S1 account-summary row 契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W5-S1 交付的**行契約層**：`reqAccountSummary` 回報行（tag/value/currency/account）
//! 的 typed 承載 shape,供 W5-S2 消化層填值——「先契約後消化,禁裸 map」。不開 socket、
//! 不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO；純資料 + 純函數（`validate()` 零副作用）。
//!
//! **tag 白名單紀律（fail-closed）**：tag 用枚舉白名單而非裸字串;現勘表外的 wire tag 一律
//! 分類為 `UnknownDenied` 並在 `validate()` 觸 blocker。wire tag 字串按 IBKR 官方
//! AccountSummaryTags 慣例鑄造（出典:官方 TWS API account_summary 文檔,
//! https://interactivebrokers.github.io/tws-api/account_summary.html）;**W5-S2 消化接線前
//! 由 IB 現勘腿覆核逐字串**（loop §2:UNVERIFIED 不升格為斷言——本白名單只做「認得才收」,
//! 不對表外 tag 賦予任何語義）。
//!
//! **money 保真紀律**：`value_decimal` 用定點十進位**字串**承載(禁 f64 裸承 money)。
//!
//! **per-tag 符號紀律（E2 F3;cash 帳戶結構性定界,逐 tag 見枚舉注釋）**：
//! - **可負（簽名保真）**：NetLiquidation / TotalCashValue / SettledCash / AccruedCash /
//!   ExcessLiquidity / EquityWithLoanValue——帳戶淨值/現金/應計項在虧損、費用、利息下
//!   可為負,拒負即失真。
//! - **結構性非負（負值=blocker）**：GrossPositionValue（定義=持倉市值絕對值總和）/
//!   BuyingPower（購買力下界 0）/ AvailableFunds（cash 帳戶結構性非負）——負值只可能
//!   來自消化層錯誤,fail-closed 拒。
//!
//! **時間戳/序列語義**：IBKR wire 的 accountSummary 回報行**不自帶** per-row 時間戳——
//! `captured_at_ms`/`snapshot_seq` 為**消化層 client 側**捕捉時鐘與快照單調序列（快照 vs
//! 流式一致性歸 W5-S2/S5 語義,本契約只要求兩者非零存在）。

use serde::{Deserialize, Serialize};

use crate::stock_etf_instrument_identity::StockEtfCurrency;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID: &str = "ibkr_account_summary_row_v1";

/// 現勘白名單 wire tag 全集（測試窮舉面;與 `classify_wire_tag` 單一對應）。
pub const IBKR_ACCOUNT_SUMMARY_WIRE_TAG_WHITELIST: [&str; 9] = [
    "NetLiquidation",
    "TotalCashValue",
    "SettledCash",
    "BuyingPower",
    "AvailableFunds",
    "ExcessLiquidity",
    "GrossPositionValue",
    "AccruedCash",
    "EquityWithLoanValue",
];

/// `reqAccountSummary` tag 白名單枚舉（fail-closed:表外一律 `UnknownDenied`）。
/// wire 字串出典見模組註解;每變體對應一個官方 AccountSummaryTags 慣例 tag。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrAccountSummaryTagV1 {
    /// 淨清算價值（"NetLiquidation";符號紀律=**可負**,深度虧損下淨值可為負）。
    NetLiquidation,
    /// 現金總值（"TotalCashValue";符號紀律=**可負**,費用/借方餘額可致負）。
    TotalCashValue,
    /// 已結算現金（"SettledCash";符號紀律=**可負**,同上保真承載）。
    SettledCash,
    /// 購買力（"BuyingPower";符號紀律=**結構性非負**,下界 0——負值=blocker）。
    BuyingPower,
    /// 可用資金（"AvailableFunds";符號紀律=**結構性非負**,cash 帳戶下——負值=blocker）。
    AvailableFunds,
    /// 超額流動性（"ExcessLiquidity";符號紀律=**可負**,margin 語義下可為負,保真承載）。
    ExcessLiquidity,
    /// 總持倉市值（"GrossPositionValue";符號紀律=**結構性非負**,定義=絕對值總和——
    /// 負值=blocker）。
    GrossPositionValue,
    /// 應計現金（"AccruedCash";符號紀律=**可負**,應計利息/股息可為負）。
    AccruedCash,
    /// 含貸款權益（"EquityWithLoanValue";符號紀律=**可負**,同 NetLiquidation 保真）。
    EquityWithLoanValue,
    /// 契約 default / 現勘表外 wire tag 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrAccountSummaryTagV1 {
    fn default() -> Self {
        // fail-closed 預設＝未知拒（須顯式白名單 tag 才可通過校驗）。
        Self::UnknownDenied
    }
}

impl IbkrAccountSummaryTagV1 {
    /// wire tag 字串 → 白名單枚舉（**大小寫敏感精確匹配**;表外一律 `UnknownDenied`）。
    pub fn classify_wire_tag(raw: &str) -> Self {
        match raw {
            "NetLiquidation" => Self::NetLiquidation,
            "TotalCashValue" => Self::TotalCashValue,
            "SettledCash" => Self::SettledCash,
            "BuyingPower" => Self::BuyingPower,
            "AvailableFunds" => Self::AvailableFunds,
            "ExcessLiquidity" => Self::ExcessLiquidity,
            "GrossPositionValue" => Self::GrossPositionValue,
            "AccruedCash" => Self::AccruedCash,
            "EquityWithLoanValue" => Self::EquityWithLoanValue,
            _ => Self::UnknownDenied,
        }
    }

    /// per-tag 符號紀律表（模組註解定界）:`true`=結構性非負,負值即 blocker;
    /// `false`=簽名保真承載。`UnknownDenied` 取 `true`（fail-closed;其 tag blocker 先行）。
    pub fn is_structurally_non_negative(&self) -> bool {
        matches!(
            self,
            Self::GrossPositionValue
                | Self::BuyingPower
                | Self::AvailableFunds
                | Self::UnknownDenied
        )
    }

    /// 白名單枚舉 → wire tag 字串（`UnknownDenied` 無 wire 對應 → `None`;round-trip 測試面）。
    pub fn as_wire_tag(&self) -> Option<&'static str> {
        match self {
            Self::NetLiquidation => Some("NetLiquidation"),
            Self::TotalCashValue => Some("TotalCashValue"),
            Self::SettledCash => Some("SettledCash"),
            Self::BuyingPower => Some("BuyingPower"),
            Self::AvailableFunds => Some("AvailableFunds"),
            Self::ExcessLiquidity => Some("ExcessLiquidity"),
            Self::GrossPositionValue => Some("GrossPositionValue"),
            Self::AccruedCash => Some("AccruedCash"),
            Self::EquityWithLoanValue => Some("EquityWithLoanValue"),
            Self::UnknownDenied => None,
        }
    }
}

// ===========================================================================
// 定點十進位字串 helper（W5-S1 row 家族共用;禁 f64 承 money）
// ===========================================================================

/// 簽名定點十進位字串:可選單一前導 `-`,至少一位數字,至多一個 `.`;**拒** `+`、空白、
/// 指數記法、NaN/Inf、空字串（比既有 `is_positive_decimal` 更嚴:不 trim,前後空白即拒）。
/// 允許零與負值（帳戶值/realizedPnL 語義需要簽名保真）。
pub fn is_signed_decimal_string(raw: &str) -> bool {
    let digits = raw.strip_prefix('-').unwrap_or(raw);
    if digits.is_empty() || digits.matches('.').count() > 1 {
        return false;
    }
    let mut saw_digit = false;
    for b in digits.bytes() {
        match b {
            b'0'..=b'9' => saw_digit = true,
            b'.' => {}
            _ => return false,
        }
    }
    saw_digit
}

/// 非負定點十進位字串（禁前導 `-`;允許零）。
pub fn is_nonnegative_decimal_string(raw: &str) -> bool {
    !raw.starts_with('-') && is_signed_decimal_string(raw)
}

/// 嚴格正定點十進位字串（非負且至少一位非零數字）。
pub fn is_positive_decimal_string(raw: &str) -> bool {
    is_nonnegative_decimal_string(raw) && raw.bytes().any(|b| (b'1'..=b'9').contains(&b))
}

// ===========================================================================
// row 契約本體
// ===========================================================================

/// `reqAccountSummary` 單行 typed 契約（W5-S2 消化層的唯一合法承載;禁裸 map）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrAccountSummaryRowV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`;錯 lane 即 blocker）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// 帳戶 id（非空;DU* 白名單/live 判定歸 W5-S4 attestation,本契約不自判）。
    pub account_id: String,
    /// 白名單 tag（`UnknownDenied` 即 blocker——fail-closed）。
    pub tag: IbkrAccountSummaryTagV1,
    /// 定點十進位字串承載的值（簽名允許;禁 f64）。
    pub value_decimal: String,
    /// 幣別（lane 白名單=USD;`UnknownDenied` 即 blocker）。
    pub currency: StockEtfCurrency,
    /// 消化層 client 側捕捉時間戳（epoch ms;非零;wire 不自帶 per-row 時間戳,見模組註解）。
    pub captured_at_ms: u64,
    /// 消化層快照單調序列（非零;快照 vs 流式一致性語義歸 W5-S2/S5）。
    pub snapshot_seq: u64,
    // ---- 負空間安全束（row 為唯讀事實,恆 false）----
    /// row 承載過程永不路由訂單。
    pub order_routed: bool,
    /// row 永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrAccountSummaryRowV1 {
    /// fail-closed 預設（空 id / 未知 tag / 未知幣別 / 零時間戳——校驗必拒）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            account_id: String::new(),
            tag: IbkrAccountSummaryTagV1::UnknownDenied,
            value_decimal: String::new(),
            currency: StockEtfCurrency::UnknownDenied,
            captured_at_ms: 0,
            snapshot_seq: 0,
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrAccountSummaryRowV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;時間戳為任意非零占位,無牆鐘依賴）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            account_id: "DU0000001".to_string(),
            tag: IbkrAccountSummaryTagV1::NetLiquidation,
            value_decimal: "100000.25".to_string(),
            currency: StockEtfCurrency::Usd,
            captured_at_ms: 123_456_789,
            snapshot_seq: 1,
            ..Self::default()
        }
    }

    /// 行級校驗（零副作用;fail-closed:未知 tag/幣別、空 id、非法 decimal 一律拒）。
    pub fn validate(&self) -> IbkrAccountSummaryRowVerdict {
        use IbkrAccountSummaryRowBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_ACCOUNT_SUMMARY_ROW_CONTRACT_ID {
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
        if self.tag == IbkrAccountSummaryTagV1::UnknownDenied {
            blockers.push(B::TagUnknownDenied);
        }
        if !is_signed_decimal_string(&self.value_decimal) {
            blockers.push(B::ValueDecimalInvalid);
        } else if self.tag.is_structurally_non_negative() && self.value_decimal.starts_with('-') {
            // per-tag 符號紀律:結構性非負 tag 帶負值=消化層錯誤,fail-closed 拒。
            blockers.push(B::NegativeValueForNonNegativeTag);
        }
        if self.currency != StockEtfCurrency::Usd {
            blockers.push(B::CurrencyDenied);
        }
        if self.captured_at_ms == 0 {
            blockers.push(B::CapturedAtMissing);
        }
        if self.snapshot_seq == 0 {
            blockers.push(B::SnapshotSeqMissing);
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrAccountSummaryRowVerdict::new(blockers)
    }
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrAccountSummaryRowVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrAccountSummaryRowBlocker>,
}

impl IbkrAccountSummaryRowVerdict {
    pub fn new(blockers: Vec<IbkrAccountSummaryRowBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrAccountSummaryRowBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    AccountIdMissing,
    TagUnknownDenied,
    ValueDecimalInvalid,
    NegativeValueForNonNegativeTag,
    CurrencyDenied,
    CapturedAtMissing,
    SnapshotSeqMissing,
    OrderRouted,
    SecretContentSerialized,
}

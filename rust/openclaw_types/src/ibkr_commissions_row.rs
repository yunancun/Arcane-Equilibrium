//! IBKR **W5-S1 commissions row 契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W5-S1 交付的**行契約層**：commissionReport 回報行的 typed 承載 shape,供
//! W5-S3 消化層填值——「先契約後消化,禁裸 map」。不開 socket、不啟 Gateway、不路由訂單、
//! 不讀 secret、不做任何 IO;純資料 + 純函數。
//!
//! **關聯鍵**：`exec_id` 與 executions-row（`ibkr_executions_row_v1`）同鍵關聯,非空必填。
//!
//! **缺席語義紀律（禁默認 0 假值）**：`realized_pnl_decimal` 用 `Option` 承載——
//! 按 IBKR 官方 API 慣例,commissionReport 的 realizedPNL 在不適用時以極大 double 哨兵
//! 值表示「缺席」（出典:官方 TWS API executions_commissions 文檔,
//! https://interactivebrokers.github.io/tws-api/executions_commissions.html;哨兵精確值屬
//! UNVERIFIED 外部細節,**本契約不鑄其常數**,消化層 W5-S3 帶現勘出典把哨兵映為 `None`）。
//! `None`=誠實缺席;**禁**把缺席寫成 `Some("0")`——0 是合法實現損益值,語義不可混用。
//!
//! **money 保真**：commission/realizedPnL 一律定點十進位字串（簽名允許——realizedPnL
//! 可為負,commission 亦以簽名承載保真,不假設 broker 側恆正）,禁 f64。

use serde::{Deserialize, Serialize};

use crate::ibkr_account_summary_row::is_signed_decimal_string;
use crate::stock_etf_instrument_identity::StockEtfCurrency;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_COMMISSIONS_ROW_CONTRACT_ID: &str = "ibkr_commissions_row_v1";

/// commissionReport 單行 typed 契約（W5-S3 消化層的唯一合法承載;禁裸 map）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrCommissionsRowV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// 與 executions-row 的關聯鍵（非空必填）。
    pub exec_id: String,
    /// 佣金（定點字串;簽名允許保真;禁 f64）。
    pub commission_decimal: String,
    /// 幣別（lane 白名單=USD）。
    pub currency: StockEtfCurrency,
    /// 實現損益（`None`=IBKR 缺席語義的誠實承載,**禁默認 0 假值**;`Some` 時必為合法
    /// 簽名定點字串——`Some("")` 亦拒）。
    pub realized_pnl_decimal: Option<String>,
    // ---- 負空間安全束（row 為唯讀事實,恆 false）----
    /// row 承載過程永不路由訂單。
    pub order_routed: bool,
    /// row 永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrCommissionsRowV1 {
    /// fail-closed 預設（空關聯鍵 / 空 decimal / 未知幣別——校驗必拒;
    /// `realized_pnl_decimal` 預設 `None`=缺席,非 0）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            exec_id: String::new(),
            commission_decimal: String::new(),
            currency: StockEtfCurrency::UnknownDenied,
            realized_pnl_decimal: None,
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrCommissionsRowV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;realizedPnL 以 `None` 示範缺席合法）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_COMMISSIONS_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            exec_id: "0000e0d5.0001.01".to_string(),
            commission_decimal: "1.25".to_string(),
            currency: StockEtfCurrency::Usd,
            realized_pnl_decimal: None,
            ..Self::default()
        }
    }

    /// 行級校驗（零副作用;fail-closed:空關聯鍵、非法 decimal、`Some` 空值一律拒）。
    pub fn validate(&self) -> IbkrCommissionsRowVerdict {
        use IbkrCommissionsRowBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_COMMISSIONS_ROW_CONTRACT_ID {
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
        if self.exec_id.trim().is_empty() {
            blockers.push(B::ExecIdMissing);
        }
        if !is_signed_decimal_string(&self.commission_decimal) {
            blockers.push(B::CommissionDecimalInvalid);
        }
        if self.currency != StockEtfCurrency::Usd {
            blockers.push(B::CurrencyDenied);
        }
        // `None`=誠實缺席（合法）;`Some` 時必為合法簽名定點字串。
        if let Some(raw) = &self.realized_pnl_decimal {
            if !is_signed_decimal_string(raw) {
                blockers.push(B::RealizedPnlDecimalInvalid);
            }
        }
        if self.order_routed {
            blockers.push(B::OrderRouted);
        }
        if self.secret_content_serialized {
            blockers.push(B::SecretContentSerialized);
        }

        IbkrCommissionsRowVerdict::new(blockers)
    }
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrCommissionsRowVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrCommissionsRowBlocker>,
}

impl IbkrCommissionsRowVerdict {
    pub fn new(blockers: Vec<IbkrCommissionsRowBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrCommissionsRowBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    ExecIdMissing,
    CommissionDecimalInvalid,
    CurrencyDenied,
    RealizedPnlDecimalInvalid,
    OrderRouted,
    SecretContentSerialized,
}

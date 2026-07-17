//! IBKR **W6-S1 instrument identity row 契約**（source-only,Rust 為 authority）。
//!
//! 本檔是 W6-S1 交付的**行契約層**：`reqContractDetails`（IN 10 CONTRACT_DATA）回報行的
//! typed 承載 shape,供 W6-S1 消化層（`ibkr_tws_contract_data`）填值——「先契約後消化,
//! 禁裸 map」。不開 socket、不啟 Gateway、不路由訂單、不讀 secret、不做任何 IO;
//! 純資料 + 純函數（`validate()` 零副作用）。
//!
//! **secType 白名單紀律（fail-closed）**：沿 W5-S1 `IbkrSecTypeV1`——本 lane 只承 STK/ETF
//! 範疇（IBKR 慣例 ETF 於 wire 亦為 `"STK"`）;表外 secType 一律 `UnknownDenied` 拒。
//!
//! **stockType 封閉枚舉（W6 現勘 2026-07-17,sv≥152 欄）**：STK wire 值不分 ETF/普通股,
//! contractDetails 的 `stockType` 欄才是判別源——白名單=`ETF`/`COMMON` 兩值,表外
//! （PREFERRED/ADR/…）與 sv<152 缺席一律 `UnknownDenied` 拒（lane 的 ETF/普通股判別是
//! 承載義務,不可未知即過）。
//!
//! **venue 白名單紀律**：W5-S1 positions row 明言「venue 白名單語義歸 instrument-identity
//! 契約」——由本檔承接。白名單以既有 `StockEtfListingVenue`（MIC 域）覆蓋集的 IB wire 名
//! 投影為準:`NYSE`/`NASDAQ`/`ISLAND`/`ARCA`/`BATS`/`AMEX`;`exchange` 欄額外允許 `SMART`
//! （路由聚合層）,`primaryExchange` 不允許 SMART(主上市地必為真實 venue)。表外 venue 拒;
//! 白名單為 v1 保守集,擴充須 IB 現勘/EA 跑道校準,禁順手加值。
//!
//! **原字串保真紀律**：`time_zone_id` 為 IB legacy 時區名（**非 IANA**,如 `EST5EDT`）——
//! 本契約原字串保真,**禁默認 America/New_York**,legacy→IANA 映射歸 W6-S2 日曆切片;
//! `trading_hours`/`liquid_hours` 同為原字串保真（`;` 分段雙 grammar 解析歸 S2）;
//! `long_name`/`order_types`/`valid_exchanges`/`multiplier`/`md_size_multiplier` 保真承載,
//! 不對其內容賦語義。money/刻度一律定點字串,禁 f64（`min_tick_decimal` 嚴格正）。
//!
//! **identity_hash（PIT 可重建）**：sha256（64 lowercase hex）over `identity_hash_preimage()`
//! 的規範化身份欄序——preimage 為本檔純函數（單一定義點,消化層/重放端共用),雜湊計算歸
//! 消化層（本 crate 無雜湊依賴,契約只驗 shape `is_sha256_hex`）。身份欄集刻意**排除**
//! 會話性/展示性欄（tradingHours/liquidHours 逐日變、longName/marketName 可改名、minTick/
//! orderTypes/validExchanges 屬市場參數）——PIT 身份=「這是哪個 instrument」,非「今天怎麼交易它」。
//!
//! **時間戳/序列語義**：IBKR wire 的 contractDetails 回報**不自帶** per-row 時間戳——
//! `captured_at_ms`/`snapshot_seq` 為消化層 client 側捕捉時鐘與快照單調序列;
//! `validate(now_ms)` 注入時鐘校驗 captured_at 非零且不在未來（PIT 紀律:身份快照不可
//! 聲稱來自未來;fixture 用相對時鐘,禁硬編當前日期）。

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::ibkr_positions_row::{is_normalized_symbol, IbkrSecTypeV1};
use crate::stock_etf_instrument_identity::StockEtfCurrency;
use crate::stock_etf_lane::{AssetLane, Broker};

/// 契約 id（消化層 / cross-surface parity 對齊）。
pub const IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID: &str = "ibkr_instrument_identity_row_v1";

/// primaryExchange 的 IB wire 名白名單（v1 保守集;對齊 `StockEtfListingVenue` MIC 覆蓋:
/// XNYS/XNAS/ARCX/BATS/XASE——`ISLAND` 為 NASDAQ 的 IB 舊名,同屬 XNAS 投影）。
/// 擴充須 IB 現勘/EA 校準,禁順手加值。
pub const IBKR_INSTRUMENT_PRIMARY_EXCHANGE_WHITELIST: [&str; 6] =
    ["NYSE", "NASDAQ", "ISLAND", "ARCA", "BATS", "AMEX"];

/// exchange 欄是否白名單 venue（primaryExchange 白名單 ∪ `SMART` 路由聚合層）。
pub fn is_whitelisted_instrument_exchange(raw: &str) -> bool {
    raw == "SMART" || is_whitelisted_primary_exchange(raw)
}

/// primaryExchange 欄是否白名單 venue（**不含 SMART**——主上市地必為真實 venue）。
pub fn is_whitelisted_primary_exchange(raw: &str) -> bool {
    IBKR_INSTRUMENT_PRIMARY_EXCHANGE_WHITELIST.contains(&raw)
}

/// contractDetails `stockType` 白名單枚舉（sv≥152 欄;fail-closed:表外/缺席一律
/// `UnknownDenied`——lane 的 ETF/普通股判別是承載義務）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrStockTypeV1 {
    /// ETF（wire `"ETF"`）。
    Etf,
    /// 普通股（wire `"COMMON"`）。
    CommonStock,
    /// 契約 default / 表外 wire 值 / sv<152 缺席 的 fail-closed 分類（`validate()` 必拒）。
    UnknownDenied,
}

impl Default for IbkrStockTypeV1 {
    fn default() -> Self {
        // fail-closed 預設＝未知拒。
        Self::UnknownDenied
    }
}

impl IbkrStockTypeV1 {
    /// wire stockType 字串 → 白名單枚舉（**大小寫敏感精確匹配**;表外一律 `UnknownDenied`）。
    pub fn classify_wire_stock_type(raw: &str) -> Self {
        match raw {
            "ETF" => Self::Etf,
            "COMMON" => Self::CommonStock,
            _ => Self::UnknownDenied,
        }
    }

    /// 白名單枚舉 → wire 字串（`UnknownDenied` 無 wire 對應 → `None`;round-trip 測試面）。
    pub fn as_wire_stock_type(&self) -> Option<&'static str> {
        match self {
            Self::Etf => Some("ETF"),
            Self::CommonStock => Some("COMMON"),
            Self::UnknownDenied => None,
        }
    }
}

/// `reqContractDetails` 單行 typed 契約（W6-S1 消化層的唯一合法承載;禁裸 map）。
/// conId 為主鍵;欄序/出典見消化層（IB 現勘 2026-07-17,官方 TWS API 9.81.1.post1 sdist）。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrInstrumentIdentityRowV1 {
    pub contract_id: String,
    pub source_version: u32,
    /// lane 綁定（恆 `StockEtfCash`）。
    pub asset_lane: AssetLane,
    /// broker 綁定（恆 `Ibkr`）。
    pub broker: Broker,
    /// IBKR contract id（主鍵;正整數）。
    pub con_id: i64,
    /// 標的代碼（規範化:大寫/數字/`.`/`-`,≤24,沿 W5-S1 row 家族同款規則）。
    pub symbol: String,
    /// secType 白名單（STK-only;`UnknownDenied` 即 blocker）。
    pub sec_type: IbkrSecTypeV1,
    /// 交易所欄（wire 原字串保真;白名單=primaryExchange 集 ∪ SMART,表外拒）。
    pub exchange: String,
    /// 主上市交易所（wire 原字串保真;白名單見模組註解,**不含 SMART**,表外拒）。
    pub primary_exchange: String,
    /// 幣別（lane 白名單=USD）。
    pub currency: StockEtfCurrency,
    /// 本地代碼（非空;wire 原字串保真——IB localSymbol 可含空格如 `"BRK B"`,不套規範化）。
    pub local_symbol: String,
    /// tradingClass（非空;wire 原字串保真）。
    pub trading_class: String,
    /// marketName（非空;wire 原字串保真）。
    pub market_name: String,
    /// 最小報價刻度（**嚴格正**定點字串;禁 f64——刻度=0/負/非法皆消化層錯誤）。
    pub min_tick_decimal: String,
    /// mdSizeMultiplier（sv≥110 欄;wire 原字串保真,語義歸行情面,不在此賦格式義務）。
    pub md_size_multiplier: String,
    /// multiplier（STK 慣例為空;wire 原字串保真）。
    pub multiplier: String,
    /// 支援訂單型別 csv（wire 原字串保真;白名單語義歸 W7 order lifecycle）。
    pub order_types: String,
    /// 有效交易所 csv（非空;wire 原字串保真）。
    pub valid_exchanges: String,
    /// priceMagnifier（正整數;IB 慣例 1）。
    pub price_magnifier: i64,
    /// longName（wire 原字串保真;sv≥153 已由消化層 unicode-escape 解碼;可空,展示欄）。
    pub long_name: String,
    /// 時區 id（非空;**IB legacy 名非 IANA,原字串保真,禁默認 America/New_York**——
    /// 映射歸 W6-S2 日曆切片）。
    pub time_zone_id: String,
    /// 交易時段原字串（非空;`;` 分段 grammar 解析歸 W6-S2）。
    pub trading_hours: String,
    /// 流動時段原字串（非空;解析歸 W6-S2）。
    pub liquid_hours: String,
    /// stockType 白名單（ETF/COMMON;表外與 sv<152 缺席=`UnknownDenied` 即 blocker）。
    pub stock_type: IbkrStockTypeV1,
    /// 身份雜湊（sha256 64 lowercase hex over `identity_hash_preimage()`;PIT 可重建——
    /// 計算歸消化層,本契約驗 shape）。
    pub identity_hash: String,
    /// 消化層 client 側捕捉時間戳（epoch ms;非零且 ≤ validate 注入的 now_ms）。
    pub captured_at_ms: u64,
    /// 消化層快照單調序列（非零）。
    pub snapshot_seq: u64,
    // ---- 負空間安全束（row 為唯讀事實,恆 false）----
    /// row 承載過程永不路由訂單。
    pub order_routed: bool,
    /// row 永不承載 secret 內容。
    pub secret_content_serialized: bool,
}

impl Default for IbkrInstrumentIdentityRowV1 {
    /// fail-closed 預設（空 id / 未知 secType/stockType/幣別 / 零時間戳——校驗必拒）。
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            con_id: 0,
            symbol: String::new(),
            sec_type: IbkrSecTypeV1::UnknownDenied,
            exchange: String::new(),
            primary_exchange: String::new(),
            currency: StockEtfCurrency::UnknownDenied,
            local_symbol: String::new(),
            trading_class: String::new(),
            market_name: String::new(),
            min_tick_decimal: String::new(),
            md_size_multiplier: String::new(),
            multiplier: String::new(),
            order_types: String::new(),
            valid_exchanges: String::new(),
            price_magnifier: 0,
            long_name: String::new(),
            time_zone_id: String::new(),
            trading_hours: String::new(),
            liquid_hours: String::new(),
            stock_type: IbkrStockTypeV1::UnknownDenied,
            identity_hash: String::new(),
            captured_at_ms: 0,
            snapshot_seq: 0,
            order_routed: false,
            secret_content_serialized: false,
        }
    }
}

impl IbkrInstrumentIdentityRowV1 {
    /// 可通過校驗的代表 fixture（acceptance 基線;時間戳為任意非零占位,無牆鐘依賴——
    /// `validate(now_ms)` 以 ≥ 此值的注入時鐘呼叫）。
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            con_id: 756733,
            symbol: "SPY".to_string(),
            sec_type: IbkrSecTypeV1::Stk,
            exchange: "SMART".to_string(),
            primary_exchange: "ARCA".to_string(),
            currency: StockEtfCurrency::Usd,
            local_symbol: "SPY".to_string(),
            trading_class: "SPY".to_string(),
            market_name: "SPY".to_string(),
            min_tick_decimal: "0.01".to_string(),
            md_size_multiplier: "100".to_string(),
            multiplier: String::new(),
            order_types: "LMT,MKT".to_string(),
            valid_exchanges: "SMART,ARCA".to_string(),
            price_magnifier: 1,
            long_name: "SPDR S&P 500 ETF TRUST".to_string(),
            time_zone_id: "US/Eastern".to_string(),
            trading_hours: "20260102:0400-20260102:2000;20260103:0400-20260103:2000".to_string(),
            liquid_hours: "20260102:0930-20260102:1600;20260103:0930-20260103:1600".to_string(),
            stock_type: IbkrStockTypeV1::Etf,
            identity_hash: placeholder_hash('a'),
            captured_at_ms: 123_456_789,
            snapshot_seq: 1,
            ..Self::default()
        }
    }

    /// **identity_hash 規範化 preimage**（單一定義點;PIT 可重建的契約錨）。
    ///
    /// 為什麼取這個欄集:PIT 身份=「這是哪個 instrument」——conId 主鍵 + 代碼/類別/venue/
    /// 幣別的規範化投影;**排除**會話性欄（tradingHours/liquidHours 逐日變）、展示欄
    /// （longName/marketName 可改名不改身份）與市場參數欄（minTick/orderTypes/
    /// validExchanges/mdSizeMultiplier/multiplier/priceMagnifier/timeZoneId）——身份不因
    /// 交易參數調整而漂移,重放端以同 row 重建必得同 hash。
    /// 不變量:欄序固定、`\n` 定界、域前綴防跨契約碰撞;枚舉以 wire 白名單字串投影
    /// （`UnknownDenied` 以固定哨兵串投影,保 preimage 全域確定性）。
    pub fn identity_hash_preimage(&self) -> String {
        [
            IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID,
            &self.con_id.to_string(),
            &self.symbol,
            self.sec_type.as_wire_sec_type().unwrap_or("UNKNOWN_DENIED"),
            &self.exchange,
            &self.primary_exchange,
            match self.currency {
                StockEtfCurrency::Usd => "USD",
                StockEtfCurrency::UnknownDenied => "UNKNOWN_DENIED",
            },
            &self.local_symbol,
            &self.trading_class,
            self.stock_type
                .as_wire_stock_type()
                .unwrap_or("UNKNOWN_DENIED"),
        ]
        .join("\n")
    }

    /// 行級校驗（零副作用;fail-closed:未知 secType/stockType/venue/幣別、非法刻度、
    /// 零/未來時間戳一律拒）。`now_ms` 為注入時鐘（PIT 紀律:captured_at 不得在未來;
    /// fixture 用相對時鐘,禁硬編當前日期）。
    pub fn validate(&self, now_ms: u64) -> IbkrInstrumentIdentityRowVerdict {
        use IbkrInstrumentIdentityRowBlocker as B;
        let mut blockers = Vec::new();

        if self.contract_id != IBKR_INSTRUMENT_IDENTITY_ROW_CONTRACT_ID {
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
        if self.con_id <= 0 {
            blockers.push(B::ConIdInvalid);
        }
        if !is_normalized_symbol(&self.symbol) {
            blockers.push(B::SymbolInvalid);
        }
        if self.sec_type == IbkrSecTypeV1::UnknownDenied {
            blockers.push(B::SecTypeUnknownDenied);
        }
        if !is_whitelisted_instrument_exchange(&self.exchange) {
            blockers.push(B::ExchangeVenueDenied);
        }
        if !is_whitelisted_primary_exchange(&self.primary_exchange) {
            blockers.push(B::PrimaryExchangeVenueDenied);
        }
        if self.currency != StockEtfCurrency::Usd {
            blockers.push(B::CurrencyDenied);
        }
        if self.local_symbol.trim().is_empty() {
            blockers.push(B::LocalSymbolMissing);
        }
        if self.trading_class.trim().is_empty() {
            blockers.push(B::TradingClassMissing);
        }
        if self.market_name.trim().is_empty() {
            blockers.push(B::MarketNameMissing);
        }
        // 嚴格正:刻度 0/負/空/指數記法皆非法（0 刻度會令下游價格對齊除以零語義崩壞）。
        if !crate::ibkr_account_summary_row::is_positive_decimal_string(&self.min_tick_decimal) {
            blockers.push(B::MinTickInvalid);
        }
        if self.valid_exchanges.trim().is_empty() {
            blockers.push(B::ValidExchangesMissing);
        }
        if self.price_magnifier <= 0 {
            blockers.push(B::PriceMagnifierInvalid);
        }
        if self.time_zone_id.trim().is_empty() {
            blockers.push(B::TimeZoneIdMissing);
        }
        if self.trading_hours.trim().is_empty() {
            blockers.push(B::TradingHoursMissing);
        }
        if self.liquid_hours.trim().is_empty() {
            blockers.push(B::LiquidHoursMissing);
        }
        if self.stock_type == IbkrStockTypeV1::UnknownDenied {
            blockers.push(B::StockTypeUnknownDenied);
        }
        if !is_sha256_hex(&self.identity_hash) {
            blockers.push(B::IdentityHashInvalid);
        }
        if self.captured_at_ms == 0 {
            blockers.push(B::CapturedAtMissing);
        } else if self.captured_at_ms > now_ms {
            blockers.push(B::CapturedAtInFuture);
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

        IbkrInstrumentIdentityRowVerdict::new(blockers)
    }
}

/// 行級校驗裁決。
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct IbkrInstrumentIdentityRowVerdict {
    pub accepted: bool,
    pub blockers: Vec<IbkrInstrumentIdentityRowBlocker>,
}

impl IbkrInstrumentIdentityRowVerdict {
    pub fn new(blockers: Vec<IbkrInstrumentIdentityRowBlocker>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

/// 行級 blocker（typed;封閉枚舉）。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum IbkrInstrumentIdentityRowBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    ConIdInvalid,
    SymbolInvalid,
    SecTypeUnknownDenied,
    ExchangeVenueDenied,
    PrimaryExchangeVenueDenied,
    CurrencyDenied,
    LocalSymbolMissing,
    TradingClassMissing,
    MarketNameMissing,
    MinTickInvalid,
    ValidExchangesMissing,
    PriceMagnifierInvalid,
    TimeZoneIdMissing,
    TradingHoursMissing,
    LiquidHoursMissing,
    StockTypeUnknownDenied,
    IdentityHashInvalid,
    CapturedAtMissing,
    CapturedAtInFuture,
    SnapshotSeqMissing,
    OrderRouted,
    SecretContentSerialized,
}

/// fixture 用 64 hex 占位（沿 `stock_etf_instrument_identity::hash` 慣例;真 hash 由消化層鑄）。
fn placeholder_hash(fill: char) -> String {
    fill.to_string().repeat(64)
}
